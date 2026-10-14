"""Retryable ordered delivery from PostgreSQL's transactional outbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import aliased

from services.api.app.event_store import (
    ProjectNotFound,
    ProjectStateCorrupt,
    _deserialize_graph,
    _deserialize_graph_change,
)
from services.api.app.models import (
    ChangeEventRecord,
    EventOutboxRecord,
    ProjectionCheckpointRecord,
    ProjectRecord,
    ProjectSnapshotRecord,
)
from services.api.app.neo4j_projection import (
    ProjectionError,
    ProjectionState,
    StaleProjectionEvent,
)


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    max_attempts: int = 5
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    lease_seconds: int = 120

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.lease_seconds < 1:
            raise ValueError("worker attempts and lease must be positive")
        if self.base_backoff_seconds <= 0 or self.max_backoff_seconds <= 0:
            raise ValueError("worker backoff must be positive")


class ProjectionPort(Protocol):
    def inspect(self, tenant_id: str, project_id: str) -> ProjectionState | None: ...

    def initialize(self, graph: Any) -> ProjectionState: ...

    def apply_graph_change(
        self,
        graph: Any,
        *,
        source_revision: int,
        event_id: str,
        expected_revision: int,
        expected_graph_hash: str,
    ) -> ProjectionState: ...

    def advance_checkpoint(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_revision: int,
        event_id: str,
        expected_revision: int,
        graph_hash: str,
    ) -> ProjectionState: ...

    def rebuild(self, graph: Any, *, source_revision: int, event_id: str) -> ProjectionState: ...


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    claimed: bool
    succeeded: bool
    outbox_id: int | None = None
    status: str | None = None
    source_revision: int | None = None
    retry_at: datetime | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    tenant_id: str
    project_id: str
    consistent: bool
    rebuilt: bool
    source_revision: int
    graph_hash: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _Claim:
    outbox_id: int
    tenant_id: str
    project_id: str
    event_id: str
    revision: int
    payload: dict[str, Any]
    attempt_count: int
    lease_token: str
    terminal: bool = False
    error: str | None = None


def process_next(
    session_factory: Any,
    projection: ProjectionPort,
    config: WorkerConfig | None = None,
    *,
    now: datetime | None = None,
) -> DeliveryResult:
    """Claim one in-order delivery and project it with bounded retry semantics."""
    instant = now or datetime.now(UTC)
    config = config or WorkerConfig()
    claim = _claim_next(session_factory, config, instant)
    if claim is None:
        return DeliveryResult(False, False, status="idle")
    if claim.terminal:
        return DeliveryResult(
            True, False, claim.outbox_id, "dead", claim.revision, error=claim.error
        )

    try:
        _project_claim(session_factory, projection, claim, instant)
    except StaleProjectionEvent as error:
        message = _safe_error(error)
        _finish_failure(session_factory, claim, config, instant, message, terminal=True)
        return DeliveryResult(True, False, claim.outbox_id, "dead", claim.revision, error=message)
    except Exception as error:  # adapter/network failures are retried, then made visible as dead
        message = _safe_error(error)
        retry_at = _finish_failure(session_factory, claim, config, instant, message)
        status = "dead" if retry_at is None else "retry"
        return DeliveryResult(
            True, False, claim.outbox_id, status, claim.revision, retry_at, message
        )
    return DeliveryResult(True, True, claim.outbox_id, "succeeded", claim.revision)


def _claim_next(session_factory: Any, config: WorkerConfig, now: datetime) -> _Claim | None:
    # Alias the predecessor table so a failed delivery blocks later project revisions.
    predecessor = aliased(EventOutboxRecord)
    older_unfinished = (
        select(predecessor.id)
        .where(
            predecessor.tenant_id == EventOutboxRecord.tenant_id,
            predecessor.project_id == EventOutboxRecord.project_id,
            predecessor.destination == EventOutboxRecord.destination,
            predecessor.id < EventOutboxRecord.id,
            predecessor.status.notin_(("succeeded", "superseded")),
        )
        .exists()
    )
    ready = or_(
        and_(
            EventOutboxRecord.status.in_(("pending", "retry")),
            EventOutboxRecord.next_attempt_at <= now,
        ),
        and_(EventOutboxRecord.status == "processing", EventOutboxRecord.lease_until <= now),
    )
    with session_factory() as session, session.begin():
        record = session.scalar(
            select(EventOutboxRecord)
            .where(
                EventOutboxRecord.destination == "neo4j",
                ready,
                ~older_unfinished,
            )
            .order_by(EventOutboxRecord.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if record is None:
            return None
        token = uuid4().hex
        if record.status == "processing" and record.attempt_count >= config.max_attempts:
            message = "worker lease expired at retry limit"
            record.status = "dead"
            record.processed_at = now
            record.last_error = message
            record.lease_token = None
            record.lease_until = None
            checkpoint = session.get(
                ProjectionCheckpointRecord,
                (record.tenant_id, record.project_id, "neo4j"),
            )
            if checkpoint is not None:
                checkpoint.status = "error"
                checkpoint.last_error = message
            return _Claim(
                record.id,
                record.tenant_id,
                record.project_id,
                record.event_id,
                record.revision,
                dict(record.payload),
                record.attempt_count,
                token,
                True,
                message,
            )
        record.status = "processing"
        record.attempt_count += 1
        record.lease_token = token
        record.lease_until = now + timedelta(seconds=config.lease_seconds)
        return _Claim(
            record.id,
            record.tenant_id,
            record.project_id,
            record.event_id,
            record.revision,
            dict(record.payload),
            record.attempt_count,
            token,
        )


def _project_claim(
    session_factory: Any,
    projection: ProjectionPort,
    claim: _Claim,
    now: datetime,
) -> None:
    with session_factory() as session, session.begin():
        record = session.scalar(
            select(EventOutboxRecord)
            .where(EventOutboxRecord.id == claim.outbox_id)
            .with_for_update()
        )
        if (
            record is None
            or record.lease_token != claim.lease_token
            or record.status != "processing"
        ):
            return
        project = session.scalar(
            select(ProjectRecord)
            .where(
                ProjectRecord.tenant_id == claim.tenant_id,
                ProjectRecord.project_id == claim.project_id,
            )
            .with_for_update()
        )
        if project is None:
            raise ProjectNotFound("outbox project is missing from PostgreSQL authority")
        event = session.scalar(
            select(ChangeEventRecord).where(
                ChangeEventRecord.tenant_id == claim.tenant_id,
                ChangeEventRecord.project_id == claim.project_id,
                ChangeEventRecord.event_id == claim.event_id,
            )
        )
        if event is None or event.revision != claim.revision or event.payload != claim.payload:
            raise ProjectionError("outbox payload disagrees with immutable PostgreSQL event")
        graph_change = None
        if claim.payload.get("event_type") == "GRAPH_SNAPSHOT_CHANGE":
            graph_change = _deserialize_graph_change(claim.payload)
            if (
                graph_change.tenant_id != claim.tenant_id
                or graph_change.project_id != claim.project_id
                or graph_change.event_id != claim.event_id
            ):
                raise ProjectionError("graph event scope or identity is inconsistent")
        checkpoint = session.get(
            ProjectionCheckpointRecord,
            (claim.tenant_id, claim.project_id, "neo4j"),
        )
        if checkpoint is None:
            initial_row = session.scalar(
                select(ProjectSnapshotRecord).where(
                    ProjectSnapshotRecord.tenant_id == claim.tenant_id,
                    ProjectSnapshotRecord.project_id == claim.project_id,
                    ProjectSnapshotRecord.revision == 0,
                    ProjectSnapshotRecord.snapshot_kind == "graph",
                )
            )
            if initial_row is None:
                raise ProjectStateCorrupt(
                    "initial graph snapshot is missing for projection bootstrap"
                )
            initial_graph = _deserialize_graph(initial_row.payload)
            existing_projection = projection.inspect(claim.tenant_id, claim.project_id)
            recovered_graph = graph_change.snapshot if graph_change is not None else initial_graph
            if existing_projection is not None:
                if (
                    existing_projection.source_revision == claim.revision
                    and existing_projection.last_event_id == claim.event_id
                    and existing_projection.graph_hash == recovered_graph.snapshot_hash
                    and existing_projection.node_hashes == _expected_node_hashes(recovered_graph)
                    and existing_projection.edge_hashes == _expected_edge_hashes(recovered_graph)
                ):
                    checkpoint = ProjectionCheckpointRecord(
                        tenant_id=claim.tenant_id,
                        project_id=claim.project_id,
                        destination="neo4j",
                        source_revision=claim.revision,
                        graph_hash=recovered_graph.snapshot_hash,
                        last_event_id=claim.event_id,
                        status="healthy",
                    )
                    session.add(checkpoint)
                    _mark_succeeded(record, now)
                    return
                if graph_change is not None and graph_change.expected_revision != 0:
                    raise StaleProjectionEvent(
                        "projection bootstrap cannot recover a noninitial graph event"
                    )
            state = projection.initialize(initial_graph)
            _verify_projection_state(
                state,
                initial_graph,
                claim.tenant_id,
                claim.project_id,
                0,
                state.last_event_id,
                initial_graph.snapshot_hash,
            )
            checkpoint = ProjectionCheckpointRecord(
                tenant_id=claim.tenant_id,
                project_id=claim.project_id,
                destination="neo4j",
                source_revision=0,
                graph_hash=initial_graph.snapshot_hash,
                last_event_id=state.last_event_id,
                status="healthy",
            )
            session.add(checkpoint)
            session.flush()

        if claim.revision <= checkpoint.source_revision:
            if (
                claim.revision == checkpoint.source_revision
                and checkpoint.last_event_id == claim.event_id
            ):
                _mark_succeeded(record, now)
                return
            # A deliberate authoritative rebuild may supersede an older queued item.
            record.status = "superseded"
            record.processed_at = now
            record.lease_until = None
            record.lease_token = None
            return
        if claim.revision != checkpoint.source_revision + 1:
            raise StaleProjectionEvent("outbox delivery is ahead of its project checkpoint")

        if graph_change is not None:
            if (
                graph_change.expected_revision != checkpoint.source_revision
                or graph_change.expected_snapshot_hash != checkpoint.graph_hash
            ):
                raise ProjectionError("graph event scope or base checkpoint is inconsistent")
            state = projection.apply_graph_change(
                graph_change.snapshot,
                source_revision=claim.revision,
                event_id=claim.event_id,
                expected_revision=checkpoint.source_revision,
                expected_graph_hash=checkpoint.graph_hash,
            )
        else:
            if (
                claim.payload.get("tenant_id") != claim.tenant_id
                or claim.payload.get("project_id") != claim.project_id
                or claim.payload.get("id") != claim.event_id
            ):
                raise ProjectionError("pointer event scope or identity is inconsistent")
            state = projection.advance_checkpoint(
                tenant_id=claim.tenant_id,
                project_id=claim.project_id,
                source_revision=claim.revision,
                event_id=claim.event_id,
                expected_revision=checkpoint.source_revision,
                graph_hash=checkpoint.graph_hash,
            )
        expected_graph = graph_change.snapshot if graph_change is not None else None
        expected_hash = (
            expected_graph.snapshot_hash if expected_graph is not None else checkpoint.graph_hash
        )
        _verify_projection_state(
            state,
            expected_graph,
            claim.tenant_id,
            claim.project_id,
            claim.revision,
            claim.event_id,
            expected_hash,
        )
        checkpoint.source_revision = claim.revision
        checkpoint.graph_hash = state.graph_hash
        checkpoint.last_event_id = claim.event_id
        checkpoint.status = "healthy"
        checkpoint.last_error = None
        _mark_succeeded(record, now)


def _mark_succeeded(record: EventOutboxRecord, now: datetime) -> None:
    record.status = "succeeded"
    record.processed_at = now
    record.lease_until = None
    record.lease_token = None
    record.last_error = None


def _finish_failure(
    session_factory: Any,
    claim: _Claim,
    config: WorkerConfig,
    now: datetime,
    message: str,
    *,
    terminal: bool = False,
) -> datetime | None:
    with session_factory() as session, session.begin():
        record = session.scalar(
            select(EventOutboxRecord)
            .where(EventOutboxRecord.id == claim.outbox_id)
            .with_for_update()
        )
        if record is None or record.lease_token != claim.lease_token:
            return None
        dead = terminal or record.attempt_count >= config.max_attempts
        if dead:
            record.status = "dead"
            record.processed_at = now
            record.next_attempt_at = now
            retry_at = None
        else:
            delay = min(
                config.max_backoff_seconds,
                config.base_backoff_seconds * 2 ** (record.attempt_count - 1),
            )
            retry_at = now + timedelta(seconds=delay)
            record.status = "retry"
            record.next_attempt_at = retry_at
        record.last_error = message[:2000]
        record.lease_token = None
        record.lease_until = None
        checkpoint = session.get(
            ProjectionCheckpointRecord,
            (claim.tenant_id, claim.project_id, "neo4j"),
        )
        if checkpoint is None:
            initial_row = session.scalar(
                select(ProjectSnapshotRecord).where(
                    ProjectSnapshotRecord.tenant_id == claim.tenant_id,
                    ProjectSnapshotRecord.project_id == claim.project_id,
                    ProjectSnapshotRecord.revision == 0,
                    ProjectSnapshotRecord.snapshot_kind == "graph",
                )
            )
            if initial_row is not None:
                checkpoint = ProjectionCheckpointRecord(
                    tenant_id=claim.tenant_id,
                    project_id=claim.project_id,
                    destination="neo4j",
                    source_revision=0,
                    graph_hash=initial_row.snapshot_hash,
                    status="error",
                    last_error=message[:2000],
                )
                session.add(checkpoint)
        elif checkpoint is not None:
            checkpoint.status = "error"
            checkpoint.last_error = message[:2000]
        return retry_at


def reconcile_project(
    session_factory: Any,
    projection: ProjectionPort,
    tenant_id: str,
    project_id: str,
    *,
    now: datetime | None = None,
) -> ReconcileResult:
    """Compare Neo4j with current PostgreSQL authority and rebuild if any drift exists."""
    instant = now or datetime.now(UTC)
    with session_factory() as session, session.begin():
        project = session.scalar(
            select(ProjectRecord)
            .where(ProjectRecord.tenant_id == tenant_id, ProjectRecord.project_id == project_id)
            .with_for_update()
        )
        if project is None:
            raise ProjectNotFound("project not found in authoritative tenant scope")
        row = session.scalar(
            select(ProjectSnapshotRecord)
            .where(
                ProjectSnapshotRecord.tenant_id == tenant_id,
                ProjectSnapshotRecord.project_id == project_id,
                ProjectSnapshotRecord.snapshot_kind == "graph",
            )
            .order_by(ProjectSnapshotRecord.revision.desc())
            .limit(1)
        )
        if row is None:
            raise ProjectStateCorrupt("authoritative graph snapshot is missing")
        graph = _deserialize_graph(row.payload)
        if graph.snapshot_hash != project.current_graph_hash:
            raise ProjectStateCorrupt("authoritative graph pointer does not match snapshot")
        checkpoint = session.get(ProjectionCheckpointRecord, (tenant_id, project_id, "neo4j"))
        try:
            current = projection.inspect(tenant_id, project_id)
        except Exception:
            current = None
        expected_node_hashes = tuple(sorted((node.id, _record_hash(node)) for node in graph.nodes))
        expected_edge_hashes = tuple(sorted((edge.id, _record_hash(edge)) for edge in graph.edges))
        consistent = (
            current is not None
            and current.source_revision == project.revision
            and current.graph_hash == graph.snapshot_hash
            and current.node_hashes == expected_node_hashes
            and current.edge_hashes == expected_edge_hashes
            and checkpoint is not None
            and checkpoint.source_revision == project.revision
            and checkpoint.graph_hash == graph.snapshot_hash
            and checkpoint.status == "healthy"
        )
        if consistent:
            return ReconcileResult(
                tenant_id, project_id, True, False, project.revision, graph.snapshot_hash
            )
        try:
            state = projection.rebuild(
                graph,
                source_revision=project.revision,
                event_id=f"rebuild:{project.revision}:{graph.snapshot_hash}",
            )
        except Exception as error:
            message = _safe_error(error)
            if checkpoint is None:
                checkpoint = ProjectionCheckpointRecord(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    destination="neo4j",
                    source_revision=0,
                    graph_hash=graph.snapshot_hash,
                    status="error",
                    last_error=message[:2000],
                )
                session.add(checkpoint)
            else:
                checkpoint.status = "error"
                checkpoint.last_error = message[:2000]
            return ReconcileResult(
                tenant_id, project_id, False, False, project.revision, graph.snapshot_hash, message
            )
        if checkpoint is None:
            checkpoint = ProjectionCheckpointRecord(
                tenant_id=tenant_id,
                project_id=project_id,
                destination="neo4j",
                source_revision=project.revision,
                graph_hash=graph.snapshot_hash,
                last_event_id=state.last_event_id,
                status="healthy",
            )
            session.add(checkpoint)
        else:
            checkpoint.source_revision = project.revision
            checkpoint.graph_hash = graph.snapshot_hash
            checkpoint.last_event_id = state.last_event_id
            checkpoint.status = "healthy"
            checkpoint.last_error = None
        session.execute(
            update(EventOutboxRecord)
            .where(
                EventOutboxRecord.tenant_id == tenant_id,
                EventOutboxRecord.project_id == project_id,
                EventOutboxRecord.destination == "neo4j",
                EventOutboxRecord.revision <= project.revision,
                EventOutboxRecord.status.in_(("pending", "retry", "processing")),
            )
            .values(
                status="superseded",
                processed_at=instant,
                lease_until=None,
                lease_token=None,
                last_error=None,
            )
        )
        return ReconcileResult(
            tenant_id, project_id, False, True, project.revision, graph.snapshot_hash
        )


def reconcile_all(
    session_factory: Any,
    projection: ProjectionPort,
    *,
    now: datetime | None = None,
) -> tuple[ReconcileResult, ...]:
    """Reconcile every project present in PostgreSQL, the sole authority list."""
    with session_factory() as session:
        scopes = tuple(
            session.execute(
                select(ProjectRecord.tenant_id, ProjectRecord.project_id).order_by(
                    ProjectRecord.tenant_id, ProjectRecord.project_id
                )
            ).all()
        )
    return tuple(
        reconcile_project(session_factory, projection, tenant_id, project_id, now=now)
        for tenant_id, project_id in scopes
    )


def _record_hash(value: Any) -> str:
    from gamo_ca.fingerprints import fingerprint

    return fingerprint(value)


def _expected_node_hashes(graph: Any) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((node.id, _record_hash(node)) for node in graph.nodes))


def _expected_edge_hashes(graph: Any) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((edge.id, _record_hash(edge)) for edge in graph.edges))


def _verify_projection_state(
    state: ProjectionState,
    graph: Any | None,
    tenant_id: str,
    project_id: str,
    source_revision: int,
    event_id: str | None,
    graph_hash: str,
) -> None:
    if (
        state.tenant_id != tenant_id
        or state.project_id != project_id
        or state.source_revision != source_revision
        or state.graph_hash != graph_hash
        or (event_id is not None and state.last_event_id != event_id)
    ):
        raise ProjectionError("Neo4j returned a mismatched projection checkpoint")
    if graph is not None and (
        state.node_hashes != _expected_node_hashes(graph)
        or state.edge_hashes != _expected_edge_hashes(graph)
    ):
        raise ProjectionError("Neo4j snapshot contents differ from PostgreSQL payload")


def _safe_error(error: Exception) -> str:
    message = " ".join(str(error).split())
    return f"{type(error).__name__}: {message}"[:2000]
