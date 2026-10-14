"""Transactional artifact and execution provenance persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from gamo_ca.approvals import PublicationDecision, publication_eligibility
from gamo_ca.fingerprints import fingerprint
from gamo_ca.graph import Graph
from gamo_ca.models import Approval, AssetVersion, InputRef
from gamo_ca.planner import Plan
from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from services.api.app.artifact_schemas import (
    ArtifactCreateRequest,
    ArtifactEligibilityResult,
    DependencyVersion,
    ExecutionAttemptStartRequest,
    ExecutionRunCreateRequest,
    ExecutionTransitionRequest,
)
from services.api.app.event_store import (
    ProjectNotFound,
    _deserialize_graph,
    load_current_graph,
)
from services.api.app.models import (
    ApprovalRecord,
    ArtifactProvenanceRecord,
    ArtifactVersionRecord,
    ExecutionAttemptRecord,
    ExecutionEventRecord,
    ExecutionRunRecord,
    ProjectRecord,
    ProjectSnapshotRecord,
)


class ArtifactStoreError(RuntimeError):
    """Base error for an artifact or execution write rejected by authority checks."""


class ArtifactConflict(ArtifactStoreError):
    """An identifier or idempotency key was reused with conflicting data."""


class StaleArtifactSource(ArtifactStoreError):
    """The requested graph revision, node, or dependencies are no longer authoritative."""


class ExecutionTransitionConflict(ArtifactStoreError):
    """An execution lifecycle transition is invalid or out of order."""


@dataclass(frozen=True, slots=True)
class ArtifactWriteResult:
    artifact_version_id: str
    artifact_id: str
    version: int
    content_hash: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class ExecutionWriteResult:
    run_id: str
    status: str
    replayed: bool


def create_artifact_version(
    session: Session,
    *,
    tenant_id: str,
    project_id: str,
    command: ArtifactCreateRequest,
) -> ArtifactWriteResult:
    """Append one content-addressed artifact after validating current PostgreSQL graph state."""
    request_hash = fingerprint(command.model_dump(mode="json"))
    with session.begin():
        project = _lock_project(session, tenant_id, project_id)
        duplicate = session.scalar(
            select(ArtifactVersionRecord).where(
                ArtifactVersionRecord.tenant_id == tenant_id,
                ArtifactVersionRecord.project_id == project_id,
                ArtifactVersionRecord.idempotency_key == command.idempotency_key,
            )
        )
        if duplicate is not None:
            if duplicate.request_hash != request_hash:
                raise ArtifactConflict("artifact idempotency key has conflicting payload")
            return _artifact_result(duplicate, replayed=True)
        version_id_conflict = session.scalar(
            select(ArtifactVersionRecord).where(
                ArtifactVersionRecord.tenant_id == tenant_id,
                ArtifactVersionRecord.project_id == project_id,
                ArtifactVersionRecord.artifact_version_id == command.artifact_version_id,
            )
        )
        if version_id_conflict is not None:
            raise ArtifactConflict("artifact version identifier already exists")
        if project.revision != command.expected_project_revision:
            raise StaleArtifactSource("project revision changed before artifact commit")
        graph = load_current_graph(session, tenant_id, project_id)
        source_snapshot = _current_graph_snapshot(session, tenant_id, project_id)
        if (
            source_snapshot.revision != command.graph_revision
            or source_snapshot.snapshot_hash != command.graph_snapshot_hash
            or graph.snapshot_hash != command.graph_snapshot_hash
        ):
            raise StaleArtifactSource("artifact source graph snapshot is not current")
        if (command.planner_decision.tenant_id, command.planner_decision.project_id) != (
            tenant_id,
            project_id,
        ) or command.planner_decision.snapshot_hash != graph.snapshot_hash:
            raise StaleArtifactSource("artifact planner decision does not match source graph")
        try:
            node = graph.node(command.node_id)
        except ValueError as error:
            raise StaleArtifactSource("artifact node is absent from the source graph") from error
        if not isinstance(node, AssetVersion) or node.version != command.node_version:
            raise StaleArtifactSource("artifact must bind the exact current asset node version")
        if command.content != node.content:
            raise StaleArtifactSource("artifact content must match the exact graph asset version")
        expected_dependencies = _dependency_bindings(graph, node.inputs)
        if (
            tuple(sorted(command.dependencies, key=lambda item: item.node_id))
            != expected_dependencies
        ):
            raise StaleArtifactSource("artifact dependency versions do not match graph inputs")

        current = session.scalar(
            select(func.max(ArtifactVersionRecord.version)).where(
                ArtifactVersionRecord.tenant_id == tenant_id,
                ArtifactVersionRecord.project_id == project_id,
                ArtifactVersionRecord.artifact_id == command.artifact_id,
            )
        )
        next_version = int(current or 0) + 1
        content_hash = sha256(command.content.encode("utf-8")).hexdigest()
        record = ArtifactVersionRecord(
            tenant_id=tenant_id,
            project_id=project_id,
            artifact_version_id=command.artifact_version_id,
            artifact_id=command.artifact_id,
            version=next_version,
            node_id=command.node_id,
            node_version=command.node_version,
            graph_revision=source_snapshot.revision,
            graph_snapshot_hash=graph.snapshot_hash,
            dependencies=[item.model_dump(mode="json") for item in expected_dependencies],
            content=command.content,
            content_hash=content_hash,
            planner_decision=TypeAdapter(Plan).dump_python(command.planner_decision, mode="json"),
            provider_id=command.provider_id,
            model_id=command.model_id,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
        )
        session.add(record)
        session.flush()
        for source in command.provenance:
            try:
                graph.node(source.source_id)
            except ValueError as error:
                raise StaleArtifactSource(
                    f"provenance source {source.source_id} is absent from graph"
                ) from error
            session.add(
                ArtifactProvenanceRecord(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    provenance_id=source.provenance_id,
                    artifact_version_id=record.artifact_version_id,
                    source_kind=source.source_kind,
                    source_id=source.source_id,
                    details=source.details,
                )
            )
        session.flush()
        return _artifact_result(record, replayed=False)


def create_execution_run(
    session: Session,
    *,
    tenant_id: str,
    project_id: str,
    command: ExecutionRunCreateRequest,
) -> ExecutionWriteResult:
    """Create a pending run and its first immutable lifecycle event atomically."""
    request_hash = fingerprint(command.model_dump(mode="json"))
    with session.begin():
        project = _lock_project(session, tenant_id, project_id)
        prior = session.scalar(
            select(ExecutionRunRecord).where(
                ExecutionRunRecord.tenant_id == tenant_id,
                ExecutionRunRecord.project_id == project_id,
                ExecutionRunRecord.idempotency_key == command.idempotency_key,
            )
        )
        if prior is not None:
            if prior.request_hash != request_hash:
                raise ArtifactConflict("execution run idempotency key has conflicting payload")
            return ExecutionWriteResult(prior.run_id, prior.status, True)
        same_run = session.scalar(
            select(ExecutionRunRecord).where(
                ExecutionRunRecord.tenant_id == tenant_id,
                ExecutionRunRecord.project_id == project_id,
                ExecutionRunRecord.run_id == command.run_id,
            )
        )
        if same_run is not None:
            raise ArtifactConflict("execution run identifier already exists")
        if project.revision != command.expected_project_revision:
            raise StaleArtifactSource("project revision changed before run commit")
        graph = load_current_graph(session, tenant_id, project_id)
        source = _current_graph_snapshot(session, tenant_id, project_id)
        if (source.revision, source.snapshot_hash) != (
            command.graph_revision,
            command.graph_snapshot_hash,
        ) or graph.snapshot_hash != command.graph_snapshot_hash:
            raise StaleArtifactSource("execution run graph snapshot is not current")
        if (command.planner_decision.tenant_id, command.planner_decision.project_id) != (
            tenant_id,
            project_id,
        ) or command.planner_decision.snapshot_hash != graph.snapshot_hash:
            raise StaleArtifactSource("execution plan does not match graph snapshot")
        run = ExecutionRunRecord(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=command.run_id,
            graph_revision=source.revision,
            graph_snapshot_hash=graph.snapshot_hash,
            plan=TypeAdapter(Plan).dump_python(command.planner_decision, mode="json"),
            status="pending",
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
        )
        session.add(run)
        session.flush()
        session.add(
            ExecutionEventRecord(
                tenant_id=tenant_id,
                project_id=project_id,
                event_id=f"{command.run_id}:pending",
                run_id=command.run_id,
                idempotency_key=f"{command.idempotency_key}:pending",
                request_hash=fingerprint((request_hash, "pending")),
                status="pending",
            )
        )
        session.flush()
        return ExecutionWriteResult(command.run_id, run.status, False)


def start_execution_attempt(
    session: Session,
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    command: ExecutionAttemptStartRequest,
) -> ExecutionWriteResult:
    """Append an attempt start only after checking pinned dependency versions."""
    request_hash = fingerprint((run_id, command.model_dump(mode="json")))
    with session.begin():
        _lock_project(session, tenant_id, project_id)
        run = _lock_run(session, tenant_id, project_id, run_id)
        prior_delivery = session.scalar(
            select(ExecutionEventRecord).where(
                ExecutionEventRecord.tenant_id == tenant_id,
                ExecutionEventRecord.project_id == project_id,
                ExecutionEventRecord.idempotency_key == command.idempotency_key,
            )
        )
        if prior_delivery is not None:
            if (
                prior_delivery.attempt_id == command.attempt_id
                and prior_delivery.request_hash == request_hash
                and prior_delivery.status == "running"
            ):
                return ExecutionWriteResult(run_id, run.status, True)
            raise ArtifactConflict("execution attempt idempotency key has conflicting payload")
        existing = session.scalar(
            select(ExecutionAttemptRecord).where(
                ExecutionAttemptRecord.tenant_id == tenant_id,
                ExecutionAttemptRecord.project_id == project_id,
                ExecutionAttemptRecord.attempt_id == command.attempt_id,
            )
        )
        if existing is not None:
            prior_event = session.scalar(
                select(ExecutionEventRecord).where(
                    ExecutionEventRecord.tenant_id == tenant_id,
                    ExecutionEventRecord.project_id == project_id,
                    ExecutionEventRecord.attempt_id == command.attempt_id,
                    ExecutionEventRecord.status == "running",
                )
            )
            if (
                existing.request_hash != request_hash
                or prior_event is None
                or prior_event.idempotency_key != command.idempotency_key
            ):
                raise ArtifactConflict("attempt identifier was reused with conflicting payload")
            return ExecutionWriteResult(run_id, run.status, True)
        if run.status not in ("pending", "retryable_failure"):
            raise ExecutionTransitionConflict("run cannot start another attempt from current state")
        expected_number = (
            int(
                session.scalar(
                    select(func.max(ExecutionAttemptRecord.attempt_number)).where(
                        ExecutionAttemptRecord.tenant_id == tenant_id,
                        ExecutionAttemptRecord.project_id == project_id,
                        ExecutionAttemptRecord.run_id == run_id,
                    )
                )
                or 0
            )
            + 1
        )
        if command.attempt_number != expected_number:
            raise ExecutionTransitionConflict("attempt number is stale or out of order")
        graph = _load_graph_snapshot(session, tenant_id, project_id, run.graph_revision)
        try:
            task_node = graph.node(command.node_id)
        except ValueError as error:
            raise StaleArtifactSource("attempt node is absent from pinned graph") from error
        expected = _dependency_bindings(graph, task_node.inputs)
        if tuple(sorted(command.dependencies, key=lambda item: item.node_id)) != expected:
            raise StaleArtifactSource("attempt dependency versions differ from pinned graph")
        now = datetime.now(UTC)
        attempt = ExecutionAttemptRecord(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            attempt_id=command.attempt_id,
            attempt_number=command.attempt_number,
            request_hash=request_hash,
            status="running",
            dependencies=[item.model_dump(mode="json") for item in expected],
            provider_id=command.provider_id,
            model_id=command.model_id,
            prompt_version=command.prompt_version,
            started_at=now,
        )
        session.add(attempt)
        run.status = "running"
        session.add(
            ExecutionEventRecord(
                tenant_id=tenant_id,
                project_id=project_id,
                event_id=f"{command.attempt_id}:running",
                run_id=run_id,
                attempt_id=command.attempt_id,
                idempotency_key=command.idempotency_key,
                request_hash=request_hash,
                status="running",
            )
        )
        session.flush()
        return ExecutionWriteResult(run_id, run.status, False)


def record_execution_transition(
    session: Session,
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    attempt_id: str | None,
    command: ExecutionTransitionRequest,
) -> ExecutionWriteResult:
    """Append a terminal/retryable attempt event and advance current status transactionally."""
    event_hash = fingerprint((run_id, attempt_id, command.model_dump(mode="json")))
    with session.begin():
        _lock_project(session, tenant_id, project_id)
        run = _lock_run(session, tenant_id, project_id, run_id)
        attempt = None
        if attempt_id is not None:
            attempt = session.scalar(
                select(ExecutionAttemptRecord)
                .where(
                    ExecutionAttemptRecord.tenant_id == tenant_id,
                    ExecutionAttemptRecord.project_id == project_id,
                    ExecutionAttemptRecord.run_id == run_id,
                    ExecutionAttemptRecord.attempt_id == attempt_id,
                )
                .with_for_update()
            )
            if attempt is None:
                raise ArtifactConflict("execution attempt not found in project scope")
        duplicate = session.scalar(
            select(ExecutionEventRecord).where(
                ExecutionEventRecord.tenant_id == tenant_id,
                ExecutionEventRecord.project_id == project_id,
                ExecutionEventRecord.idempotency_key == command.idempotency_key,
            )
        )
        if duplicate is not None:
            if (
                duplicate.event_id != command.event_id
                or duplicate.request_hash != event_hash
                or duplicate.status != command.status
            ):
                raise ArtifactConflict("execution event idempotency key has conflicting payload")
            return ExecutionWriteResult(run_id, run.status, True)
        duplicate_event_id = session.scalar(
            select(ExecutionEventRecord).where(
                ExecutionEventRecord.tenant_id == tenant_id,
                ExecutionEventRecord.project_id == project_id,
                ExecutionEventRecord.event_id == command.event_id,
            )
        )
        if duplicate_event_id is not None:
            raise ArtifactConflict("execution event identifier already exists")
        pending_cancel = (
            attempt_id is None and run.status == "pending" and command.status == "cancelled"
        )
        if not pending_cancel and (
            run.status != "running" or attempt is None or attempt.status != "running"
        ):
            raise ExecutionTransitionConflict(
                "only a pending run can be cancelled without an attempt"
            )
        if command.status == "succeeded" and command.artifact_version_id is not None:
            artifact = session.scalar(
                select(ArtifactVersionRecord).where(
                    ArtifactVersionRecord.tenant_id == tenant_id,
                    ArtifactVersionRecord.project_id == project_id,
                    ArtifactVersionRecord.artifact_version_id == command.artifact_version_id,
                )
            )
            if artifact is None or artifact.graph_snapshot_hash != run.graph_snapshot_hash:
                raise StaleArtifactSource(
                    "successful attempt output is absent or from another graph"
                )
        elif command.status != "succeeded" and command.artifact_version_id is not None:
            raise ExecutionTransitionConflict("failed/cancelled attempts cannot attach output")
        if command.status in ("failed", "retryable_failure") and not command.error_classification:
            raise ExecutionTransitionConflict("failed execution requires an error classification")
        finished_at = datetime.now(UTC)
        if attempt is not None:
            attempt.status = command.status
            attempt.finished_at = finished_at
        run.status = command.status
        metric_values = _metric_columns(command)
        session.add(
            ExecutionEventRecord(
                tenant_id=tenant_id,
                project_id=project_id,
                event_id=command.event_id,
                run_id=run_id,
                attempt_id=attempt_id,
                idempotency_key=command.idempotency_key,
                request_hash=event_hash,
                status=command.status,
                error_classification=command.error_classification,
                error_message=command.error_message,
                artifact_version_id=command.artifact_version_id,
                **metric_values,
            )
        )
        session.flush()
        if fingerprint((run_id, attempt_id, command.model_dump(mode="json"))) != event_hash:
            raise ArtifactStoreError("execution event payload changed during transaction")
        return ExecutionWriteResult(run_id, run.status, False)


def check_artifact_eligibility(
    session: Session,
    *,
    tenant_id: str,
    project_id: str,
    artifact_version_id: str,
) -> ArtifactEligibilityResult:
    """Evaluate publication eligibility from authoritative graph and approval rows."""
    with session.begin():
        _lock_project(session, tenant_id, project_id)
        artifact = session.scalar(
            select(ArtifactVersionRecord).where(
                ArtifactVersionRecord.tenant_id == tenant_id,
                ArtifactVersionRecord.project_id == project_id,
                ArtifactVersionRecord.artifact_version_id == artifact_version_id,
            )
        )
        if artifact is None:
            raise ArtifactConflict("artifact version not found in project scope")
        graph = load_current_graph(session, tenant_id, project_id)
        if graph.snapshot_hash != artifact.graph_snapshot_hash:
            return ArtifactEligibilityResult(
                eligible=False,
                reasons=("artifact source graph snapshot is no longer current",),
                artifact_version_id=artifact_version_id,
            )
        plan = TypeAdapter(Plan).validate_python(artifact.planner_decision)
        history_rows = session.scalars(
            select(ApprovalRecord).where(
                ApprovalRecord.tenant_id == tenant_id,
                ApprovalRecord.project_id == project_id,
                ApprovalRecord.asset_version_id == artifact.node_id,
            )
        ).all()
        history = tuple(TypeAdapter(Approval).validate_python(row.payload) for row in history_rows)
        asset = graph.node(artifact.node_id)
        if not isinstance(asset, AssetVersion) or asset.version != artifact.node_version:
            return ArtifactEligibilityResult(
                eligible=False,
                reasons=("artifact node version is not current",),
                artifact_version_id=artifact_version_id,
            )
        if (
            sha256(artifact.content.encode("utf-8")).hexdigest() != artifact.content_hash
            or artifact.content != asset.content
        ):
            return ArtifactEligibilityResult(
                eligible=False,
                reasons=("artifact content hash or graph content binding is inconsistent",),
                artifact_version_id=artifact_version_id,
            )
        expected_dependencies = _dependency_bindings(graph, asset.inputs)
        stored_dependencies = [item.model_dump(mode="json") for item in expected_dependencies]
        if artifact.dependencies != stored_dependencies:
            return ArtifactEligibilityResult(
                eligible=False,
                reasons=("artifact dependency provenance is inconsistent",),
                artifact_version_id=artifact_version_id,
            )
        decision: PublicationDecision = publication_eligibility(
            graph,
            artifact.node_id,
            history,
            plan,
            policy_version=asset.policy_version,
        )
        return ArtifactEligibilityResult(
            eligible=decision.eligible,
            reasons=decision.reasons,
            artifact_version_id=artifact_version_id,
        )


def _lock_project(session: Session, tenant_id: str, project_id: str) -> ProjectRecord:
    project = session.scalar(
        select(ProjectRecord)
        .where(ProjectRecord.tenant_id == tenant_id, ProjectRecord.project_id == project_id)
        .with_for_update()
    )
    if project is None:
        raise ProjectNotFound("project not found in authorized tenant scope")
    return project


def _lock_run(session: Session, tenant_id: str, project_id: str, run_id: str) -> ExecutionRunRecord:
    run = session.scalar(
        select(ExecutionRunRecord)
        .where(
            ExecutionRunRecord.tenant_id == tenant_id,
            ExecutionRunRecord.project_id == project_id,
            ExecutionRunRecord.run_id == run_id,
        )
        .with_for_update()
    )
    if run is None:
        raise ArtifactConflict("execution run not found in project scope")
    return run


def _current_graph_snapshot(
    session: Session, tenant_id: str, project_id: str
) -> ProjectSnapshotRecord:
    snapshot = session.scalar(
        select(ProjectSnapshotRecord)
        .where(
            ProjectSnapshotRecord.tenant_id == tenant_id,
            ProjectSnapshotRecord.project_id == project_id,
            ProjectSnapshotRecord.snapshot_kind == "graph",
        )
        .order_by(ProjectSnapshotRecord.revision.desc())
        .limit(1)
    )
    if snapshot is None:
        raise StaleArtifactSource("project has no authoritative graph snapshot")
    return snapshot


def _load_graph_snapshot(session: Session, tenant_id: str, project_id: str, revision: int) -> Graph:
    snapshot = session.scalar(
        select(ProjectSnapshotRecord).where(
            ProjectSnapshotRecord.tenant_id == tenant_id,
            ProjectSnapshotRecord.project_id == project_id,
            ProjectSnapshotRecord.revision == revision,
            ProjectSnapshotRecord.snapshot_kind == "graph",
        )
    )
    if snapshot is None:
        raise StaleArtifactSource("pinned graph snapshot is missing")
    return _deserialize_graph(snapshot.payload)


def _dependency_bindings(
    graph: Graph, inputs: tuple[InputRef, ...]
) -> tuple[DependencyVersion, ...]:
    if len({reference.source_id for reference in inputs}) != len(inputs):
        raise StaleArtifactSource("dependency node IDs must be unique")
    bindings = []
    for reference in inputs:
        node_id = reference.source_id
        try:
            node = graph.node(node_id)
        except ValueError as error:
            raise StaleArtifactSource(f"dependency {node_id} is absent from graph") from error
        if node.version != reference.version or node.content_hash != reference.content_hash:
            raise StaleArtifactSource(f"dependency reference {node_id} is stale in graph")
        bindings.append(
            DependencyVersion(
                node_id=node_id,
                node_version=reference.version,
                content_hash=reference.content_hash,
            )
        )
    return tuple(sorted(bindings, key=lambda item: item.node_id))


def _artifact_result(record: ArtifactVersionRecord, *, replayed: bool) -> ArtifactWriteResult:
    return ArtifactWriteResult(
        artifact_version_id=record.artifact_version_id,
        artifact_id=record.artifact_id,
        version=record.version,
        content_hash=record.content_hash,
        replayed=replayed,
    )


def _metric_columns(command: ExecutionTransitionRequest) -> dict[str, Any]:
    elapsed = command.elapsed
    tokens = command.tokens
    cost = command.cost_usd
    if elapsed.value is not None and not isinstance(elapsed.value, int):
        raise ExecutionTransitionConflict("elapsed time must be a whole number of milliseconds")
    if tokens.value is not None and not isinstance(tokens.value, int):
        raise ExecutionTransitionConflict("token count must be an integer")
    return {
        "elapsed_ms": elapsed.value,
        "elapsed_status": elapsed.status.value,
        "token_count": tokens.value,
        "token_status": tokens.status.value,
        "cost_usd": cost.value,
        "cost_status": cost.status.value,
    }
