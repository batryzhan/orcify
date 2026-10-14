"""Transactional append-only event storage and project replay state."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from gamo_ca.approvals import ApprovalError, ApprovalResult, ReviewerIdentity, apply_approval
from gamo_ca.events import (
    EventReceipt,
    EventReplayState,
    GraphChangeIdentity,
    GraphChangePayload,
    VersionPointer,
    apply_change_event,
    apply_graph_snapshot_change,
    graph_change_payload,
    replay_graph_changes,
)
from gamo_ca.fingerprints import canonical, fingerprint
from gamo_ca.graph import Graph
from gamo_ca.models import (
    Approval,
    AssetVersion,
    Brief,
    ChangeEvent,
    DependencyEdge,
    Evidence,
    Requirement,
    Task,
    require_id,
)
from gamo_ca.planner import Plan
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.app.models import (
    ApprovalRecord,
    ChangeEventRecord,
    EventOutboxRecord,
    ProjectRecord,
    ProjectSnapshotRecord,
)


class EventStoreError(RuntimeError):
    """Base error for a rejected or inconsistent event-store operation."""


class EventConflict(EventStoreError):
    """An event or idempotency key was reused with different request data."""


class StaleProjectRevision(EventStoreError):
    """The expected project revision is no longer current."""


class ProjectNotFound(EventStoreError):
    """No project exists within the authenticated scope."""


class ProjectStateCorrupt(EventStoreError):
    """Stored replay state disagrees with its revision or snapshot hash."""


@dataclass(frozen=True, slots=True)
class EventWriteResult:
    receipt: EventReceipt
    revision: int
    snapshot_hash: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class GraphChangeWriteResult:
    receipt: EventReceipt
    revision: int
    snapshot_hash: str
    replayed: bool


def create_project(
    session: Session,
    tenant_id: str,
    project_id: str,
    initial_state: EventReplayState,
    *,
    initial_graph: Graph,
) -> ProjectRecord:
    """Create a project and persist its immutable graph and replay snapshots."""
    require_id(tenant_id)
    require_id(project_id)
    if (initial_state.tenant_id, initial_state.project_id) != (tenant_id, project_id):
        raise EventConflict("initial state scope mismatch")
    if (initial_graph.tenant_id, initial_graph.project_id) != (tenant_id, project_id):
        raise EventConflict("initial graph scope mismatch")
    if initial_graph.snapshot_hash != initial_state.snapshot_hash:
        raise EventConflict("initial graph and reducer snapshot hashes differ")
    if initial_state.revision != 0 or initial_state.receipts:
        raise EventConflict("project must start at revision zero")
    with session.begin():
        existing = session.get(ProjectRecord, (tenant_id, project_id))
        if existing is not None:
            raise EventConflict("project already exists")
        record = ProjectRecord(
            tenant_id=tenant_id,
            project_id=project_id,
            revision=0,
            current_snapshot_hash=initial_state.snapshot_hash,
            current_graph_hash=initial_graph.snapshot_hash,
            replay_state=_serialize_state(initial_state),
        )
        session.add(record)
        session.add(
            ProjectSnapshotRecord(
                tenant_id=tenant_id,
                project_id=project_id,
                revision=0,
                snapshot_kind="replay_state",
                snapshot_hash=initial_state.snapshot_hash,
                payload=_serialize_state(initial_state),
            )
        )
        session.add(
            ProjectSnapshotRecord(
                tenant_id=tenant_id,
                project_id=project_id,
                revision=0,
                snapshot_kind="graph",
                snapshot_hash=initial_graph.snapshot_hash,
                payload=_serialize_graph(initial_graph),
            )
        )
    return record


def load_project(session: Session, tenant_id: str, project_id: str) -> ProjectRecord:
    """Load project only by a scope derived from the authenticated principal."""
    record = session.get(ProjectRecord, (tenant_id, project_id))
    if record is None:
        raise ProjectNotFound("project not found in authorized tenant scope")
    return record


def append_change_event(
    session: Session,
    *,
    tenant_id: str,
    project_id: str,
    event: ChangeEvent,
    idempotency_key: str,
    expected_revision: int,
) -> EventWriteResult:
    """Reduce and append one event, revision, and projection outbox row atomically.

    Callers must supply tenant/project scope from a verified server-side principal,
    never directly from request fields. The project row lock serializes writes on
    PostgreSQL; uniqueness constraints remain a second line of defense.
    """
    require_id(tenant_id)
    require_id(project_id)
    require_id(idempotency_key)
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("expected revision must be a nonnegative integer")
    if (event.tenant_id, event.project_id) != (tenant_id, project_id):
        raise EventConflict("event scope differs from authorized project scope")
    request_hash = fingerprint(
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "event": event,
            "expected_revision": expected_revision,
        }
    )

    with session.begin():
        project = session.scalar(
            select(ProjectRecord)
            .where(ProjectRecord.tenant_id == tenant_id, ProjectRecord.project_id == project_id)
            .with_for_update()
        )
        if project is None:
            raise ProjectNotFound("project not found in authorized tenant scope")
        prior_key = session.scalar(
            select(ChangeEventRecord).where(
                ChangeEventRecord.tenant_id == tenant_id,
                ChangeEventRecord.project_id == project_id,
                ChangeEventRecord.idempotency_key == idempotency_key,
            )
        )
        if prior_key is not None:
            if prior_key.payload_hash != request_hash:
                raise EventConflict("idempotency key reused with conflicting request payload")
            return EventWriteResult(
                _deserialize_receipt(prior_key.receipt),
                prior_key.revision,
                str(prior_key.receipt["snapshot_hash"]),
                True,
            )

        prior_event = session.scalar(
            select(ChangeEventRecord).where(
                ChangeEventRecord.tenant_id == tenant_id,
                ChangeEventRecord.project_id == project_id,
                ChangeEventRecord.event_id == event.id,
            )
        )
        if prior_event is not None:
            raise EventConflict("event ID already exists with a different idempotency key")
        if project.revision != expected_revision:
            raise StaleProjectRevision(
                f"expected revision {expected_revision}; current revision is {project.revision}"
            )

        state = _deserialize_state(project.replay_state)
        if (
            state.revision != project.revision
            or state.snapshot_hash != project.current_snapshot_hash
        ):
            raise ProjectStateCorrupt("stored replay state does not match project authority fields")
        try:
            reduced = apply_change_event(state, event)
        except ValueError as error:
            raise EventConflict(str(error)) from error
        if reduced.replayed:
            # State and event history must advance together; a missing receipt row is corruption.
            raise ProjectStateCorrupt("replay state contains an event absent from the event log")

        revision = reduced.state.revision
        receipt_payload = _serialize_receipt(reduced.receipt)
        payload = canonical(event)
        assert isinstance(payload, dict)
        project.revision = revision
        project.current_snapshot_hash = reduced.state.snapshot_hash
        project.replay_state = _serialize_state(reduced.state)
        session.add(
            ChangeEventRecord(
                tenant_id=tenant_id,
                project_id=project_id,
                event_id=event.id,
                idempotency_key=idempotency_key,
                payload_hash=request_hash,
                revision=revision,
                payload=payload,
                receipt=receipt_payload,
                occurred_at=event.occurred_at,
            )
        )
        session.add(
            ProjectSnapshotRecord(
                tenant_id=tenant_id,
                project_id=project_id,
                revision=revision,
                snapshot_kind="replay_state",
                snapshot_hash=reduced.state.snapshot_hash,
                payload=_serialize_state(reduced.state),
            )
        )
        _insert_outbox(session, tenant_id, project_id, event.id, revision, payload)
        return EventWriteResult(reduced.receipt, revision, reduced.state.snapshot_hash, False)


def append_graph_change(
    session: Session,
    *,
    change: GraphChangePayload,
    identity: GraphChangeIdentity,
    idempotency_key: str,
) -> GraphChangeWriteResult:
    """Validate and atomically append a complete authoritative graph replacement."""
    require_id(idempotency_key)
    if (identity.tenant_id, identity.project_id) != (change.tenant_id, change.project_id):
        raise EventConflict("graph writer scope differs from authorized project scope")
    if identity.actor_id != change.actor_id or not identity.is_human:
        raise EventConflict("graph change requires the authorized human actor")
    if identity.role not in {"producer", "editor", "reviewer"}:
        raise EventConflict("graph writer role is not authorized")
    request_payload = graph_change_payload(change)
    request_hash = fingerprint(request_payload)

    with session.begin():
        project = session.scalar(
            select(ProjectRecord)
            .where(
                ProjectRecord.tenant_id == identity.tenant_id,
                ProjectRecord.project_id == identity.project_id,
            )
            .with_for_update()
        )
        if project is None:
            raise ProjectNotFound("project not found in authorized tenant scope")
        prior_key = session.scalar(
            select(ChangeEventRecord).where(
                ChangeEventRecord.tenant_id == identity.tenant_id,
                ChangeEventRecord.project_id == identity.project_id,
                ChangeEventRecord.idempotency_key == idempotency_key,
            )
        )
        if prior_key is not None:
            if prior_key.payload_hash != request_hash:
                raise EventConflict("graph idempotency key has conflicting request payload")
            return GraphChangeWriteResult(
                _deserialize_receipt(prior_key.receipt),
                prior_key.revision,
                str(prior_key.payload["snapshot"]["snapshot_hash"]),
                True,
            )
        prior_event = session.scalar(
            select(ChangeEventRecord).where(
                ChangeEventRecord.tenant_id == identity.tenant_id,
                ChangeEventRecord.project_id == identity.project_id,
                ChangeEventRecord.event_id == change.event_id,
            )
        )
        if prior_event is not None:
            raise EventConflict("graph event ID already exists with another idempotency key")
        if project.revision != change.expected_revision:
            raise StaleProjectRevision(
                f"expected revision {change.expected_revision}; "
                f"current revision is {project.revision}"
            )

        state = _deserialize_state(project.replay_state)
        if (
            state.revision != project.revision
            or state.snapshot_hash != project.current_snapshot_hash
        ):
            raise ProjectStateCorrupt("stored replay state disagrees with project revision/hash")
        current_graph = _load_current_graph_locked(session, project)
        history_rows = session.scalars(
            select(ProjectSnapshotRecord).where(
                ProjectSnapshotRecord.tenant_id == identity.tenant_id,
                ProjectSnapshotRecord.project_id == identity.project_id,
                ProjectSnapshotRecord.snapshot_kind == "graph",
            )
        )
        known_versions = frozenset(
            (node.id, node.version, node.content_hash)
            for row in history_rows
            for node in _deserialize_graph(row.payload).nodes
        )
        try:
            updated = apply_graph_snapshot_change(
                state,
                current_graph,
                change,
                identity,
                known_versions=known_versions,
            )
        except ValueError as error:
            raise EventConflict(str(error)) from error

        revision = updated.state.revision
        receipt_payload = _serialize_receipt(updated.receipt)
        project.revision = revision
        project.current_snapshot_hash = updated.state.snapshot_hash
        project.current_graph_hash = updated.snapshot.snapshot_hash
        project.replay_state = _serialize_state(updated.state)
        session.add(
            ChangeEventRecord(
                tenant_id=identity.tenant_id,
                project_id=identity.project_id,
                event_id=change.event_id,
                idempotency_key=idempotency_key,
                payload_hash=request_hash,
                revision=revision,
                payload=request_payload,
                receipt=receipt_payload,
                occurred_at=change.occurred_at,
            )
        )
        session.add(
            ProjectSnapshotRecord(
                tenant_id=identity.tenant_id,
                project_id=identity.project_id,
                revision=revision,
                snapshot_kind="graph",
                snapshot_hash=updated.snapshot.snapshot_hash,
                payload=_serialize_graph(updated.snapshot),
            )
        )
        session.add(
            ProjectSnapshotRecord(
                tenant_id=identity.tenant_id,
                project_id=identity.project_id,
                revision=revision,
                snapshot_kind="replay_state",
                snapshot_hash=updated.state.snapshot_hash,
                payload=_serialize_state(updated.state),
            )
        )
        _insert_outbox(
            session,
            identity.tenant_id,
            identity.project_id,
            change.event_id,
            revision,
            request_payload,
        )
        return GraphChangeWriteResult(
            updated.receipt, revision, updated.snapshot.snapshot_hash, False
        )


def load_current_graph(session: Session, tenant_id: str, project_id: str) -> Graph:
    """Load and verify the authoritative current graph snapshot from PostgreSQL."""
    project = load_project(session, tenant_id, project_id)
    return _load_current_graph_locked(session, project)


def replay_project_graph(session: Session, tenant_id: str, project_id: str) -> Graph:
    """Rebuild the current graph by replaying full graph events from revision zero."""
    project = load_project(session, tenant_id, project_id)
    initial_row = session.scalar(
        select(ProjectSnapshotRecord).where(
            ProjectSnapshotRecord.tenant_id == tenant_id,
            ProjectSnapshotRecord.project_id == project_id,
            ProjectSnapshotRecord.revision == 0,
            ProjectSnapshotRecord.snapshot_kind == "graph",
        )
    )
    if initial_row is None:
        raise ProjectStateCorrupt("initial graph snapshot is missing")
    initial_graph = _deserialize_graph(initial_row.payload)
    records = session.scalars(
        select(ChangeEventRecord)
        .where(ChangeEventRecord.tenant_id == tenant_id, ChangeEventRecord.project_id == project_id)
        .order_by(ChangeEventRecord.revision)
    )
    graph_changes: list[GraphChangePayload] = []
    for record in records:
        if record.payload.get("event_type") == "GRAPH_SNAPSHOT_CHANGE":
            graph_changes.append(_deserialize_graph_change(record.payload))
    rebuilt = replay_graph_changes(initial_graph, tuple(graph_changes))
    if rebuilt.snapshot_hash != project.current_graph_hash:
        raise ProjectStateCorrupt("replayed graph hash differs from current project authority")
    return rebuilt


def _load_current_graph_locked(session: Session, project: ProjectRecord) -> Graph:
    row = session.scalar(
        select(ProjectSnapshotRecord)
        .where(
            ProjectSnapshotRecord.tenant_id == project.tenant_id,
            ProjectSnapshotRecord.project_id == project.project_id,
            ProjectSnapshotRecord.snapshot_kind == "graph",
        )
        .order_by(ProjectSnapshotRecord.revision.desc())
        .limit(1)
    )
    if row is None or row.snapshot_hash != project.current_graph_hash:
        raise ProjectStateCorrupt("current graph pointer has no matching immutable snapshot")
    graph = _deserialize_graph(row.payload)
    if graph.snapshot_hash != project.current_graph_hash:
        raise ProjectStateCorrupt("stored graph payload does not match its snapshot hash")
    return graph


def append_approval(
    session: Session,
    *,
    command: Approval,
    identity: ReviewerIdentity,
    graph: Graph,
    plan: Plan,
) -> ApprovalResult:
    """Validate with the pure GAMO-CA transition then append under the project lock.

    `identity` must be created by a verified server-side authorization boundary. This
    repository helper deliberately cannot establish authentication by itself.
    """
    if (command.tenant_id, command.project_id) != (identity.tenant_id, identity.project_id):
        raise EventConflict("approval actor scope differs from authorized identity")
    payload = canonical(command)
    if not isinstance(payload, dict):
        raise TypeError("approval payload must serialize to an object")
    payload_hash = fingerprint(payload)
    with session.begin():
        project = session.scalar(
            select(ProjectRecord)
            .where(
                ProjectRecord.tenant_id == identity.tenant_id,
                ProjectRecord.project_id == identity.project_id,
            )
            .with_for_update()
        )
        if project is None:
            raise ProjectNotFound("project not found in authorized tenant scope")
        if project.current_graph_hash != graph.snapshot_hash:
            raise StaleProjectRevision("approval graph is not the authoritative current snapshot")
        if identity.actor_id != command.actor_id or not identity.is_human:
            raise ApprovalError("approval requires the authenticated human actor")
        prior = session.scalar(
            select(ApprovalRecord).where(
                ApprovalRecord.tenant_id == identity.tenant_id,
                ApprovalRecord.project_id == identity.project_id,
                ApprovalRecord.idempotency_key == command.idempotency_key,
            )
        )
        if prior is not None:
            if prior.payload_hash != payload_hash:
                raise EventConflict("approval idempotency key has conflicting payload")
            history = _approval_history(session, identity.tenant_id, identity.project_id)
            chain = tuple(
                item for item in history if item.asset_version_id == command.asset_version_id
            )
            return ApprovalResult(chain, command, True)
        history = _approval_history(session, identity.tenant_id, identity.project_id)
        validated = apply_approval(history, command, identity, graph, plan)
        session.add(
            ApprovalRecord(
                tenant_id=identity.tenant_id,
                project_id=identity.project_id,
                approval_id=command.id,
                asset_version_id=command.asset_version_id,
                revision=command.expected_revision + 1,
                idempotency_key=command.idempotency_key,
                payload_hash=payload_hash,
                requirement_fingerprint=command.requirement_fingerprint,
                policy_version=command.policy_version,
                actor_id=command.actor_id,
                decision=command.decision.value,
                payload=payload,
                created_at=command.created_at,
            )
        )
        return validated


def _approval_history(session: Session, tenant_id: str, project_id: str) -> tuple[Approval, ...]:
    rows = session.scalars(
        select(ApprovalRecord)
        .where(ApprovalRecord.tenant_id == tenant_id, ApprovalRecord.project_id == project_id)
        .order_by(ApprovalRecord.asset_version_id, ApprovalRecord.revision)
    )
    return tuple(_approval_from_payload(row.payload) for row in rows.all())


def _approval_from_payload(payload: dict[str, Any]) -> Approval:
    from datetime import datetime

    from gamo_ca.models import ApprovalDecision

    return Approval(
        id=str(payload["id"]),
        tenant_id=str(payload["tenant_id"]),
        project_id=str(payload["project_id"]),
        created_at=datetime.fromisoformat(str(payload["created_at"])),
        schema_version=int(payload["schema_version"]),
        asset_version_id=str(payload["asset_version_id"]),
        asset_version=int(payload["asset_version"]),
        requirement_fingerprint=str(payload["requirement_fingerprint"]),
        actor_id=str(payload["actor_id"]),
        decision=ApprovalDecision(str(payload["decision"])),
        policy_version=str(payload["policy_version"]),
        idempotency_key=str(payload["idempotency_key"]),
        expected_revision=int(payload["expected_revision"]),
        reason=payload.get("reason"),
        supersedes_id=payload.get("supersedes_id"),
    )


def list_project_events(
    session: Session, tenant_id: str, project_id: str
) -> tuple[ChangeEventRecord, ...]:
    """Return an ordered immutable view of events in one authorized scope."""
    load_project(session, tenant_id, project_id)
    rows = session.scalars(
        select(ChangeEventRecord)
        .where(
            ChangeEventRecord.tenant_id == tenant_id,
            ChangeEventRecord.project_id == project_id,
        )
        .order_by(ChangeEventRecord.revision)
    )
    return tuple(rows.all())


def _insert_outbox(
    session: Session,
    tenant_id: str,
    project_id: str,
    event_id: str,
    revision: int,
    payload: dict[str, Any],
) -> None:
    session.add(
        EventOutboxRecord(
            tenant_id=tenant_id,
            project_id=project_id,
            event_id=event_id,
            revision=revision,
            destination="neo4j",
            payload=payload,
            attempt_count=0,
        )
    )


def _serialize_state(state: EventReplayState) -> dict[str, Any]:
    return {
        "tenant_id": state.tenant_id,
        "project_id": state.project_id,
        "base_snapshot_hash": state.base_snapshot_hash,
        "revision": state.revision,
        "versions": [
            {
                "node_id": pointer.node_id,
                "version": pointer.version,
                "content_hash": pointer.content_hash,
            }
            for pointer in state.versions
        ],
        "receipts": [_serialize_receipt(receipt) for receipt in state.receipts],
        "last_event_at": (
            state.last_event_at.isoformat() if state.last_event_at is not None else None
        ),
        "confirmed_evidence_ids": sorted(state.confirmed_evidence_ids),
    }


def _serialize_graph(graph: Graph) -> dict[str, Any]:
    """Store all typed node and edge fields; the graph hash binds canonical content."""
    nodes = []
    for node in sorted(graph.nodes, key=lambda item: item.id):
        payload = canonical(node)
        assert isinstance(payload, dict)
        nodes.append({"type": type(node).__name__, **payload})
    edges = []
    for edge in sorted(graph.edges, key=lambda item: item.id):
        payload = canonical(edge)
        assert isinstance(payload, dict)
        edges.append({"type": type(edge).__name__, **payload})
    return {
        "schema_version": 1,
        "tenant_id": graph.tenant_id,
        "project_id": graph.project_id,
        "as_of": graph.as_of.isoformat(),
        "snapshot_hash": graph.snapshot_hash,
        "nodes": nodes,
        "edges": edges,
    }


def _deserialize_graph(payload: dict[str, Any]) -> Graph:
    """Decode a complete versioned snapshot and verify its content hash."""
    try:
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported graph snapshot schema")
        node_types = {
            cls.__name__: cls for cls in (Brief, Requirement, Evidence, Task, AssetVersion)
        }
        nodes = tuple(_decode_typed_record(item, node_types) for item in payload["nodes"])
        edges = tuple(
            _decode_typed_record(item, {"DependencyEdge": DependencyEdge})
            for item in payload["edges"]
        )
        graph = Graph(
            tenant_id=str(payload["tenant_id"]),
            project_id=str(payload["project_id"]),
            as_of=datetime.fromisoformat(str(payload["as_of"])),
            nodes=nodes,
            edges=edges,
        )
        if graph.snapshot_hash != payload["snapshot_hash"]:
            raise ValueError("graph payload hash mismatch")
        return graph
    except (KeyError, TypeError, ValueError) as error:
        raise ProjectStateCorrupt("stored graph snapshot is malformed") from error


def _decode_typed_record(payload: dict[str, Any], types: Mapping[str, type[Any]]) -> Any:
    if not isinstance(payload, dict):
        raise TypeError("typed graph record must be an object")
    type_name = payload.get("type")
    if not isinstance(type_name, str):
        raise ValueError("missing graph record type")
    cls = types.get(type_name)
    if cls is None:
        raise ValueError("unknown graph record type")
    raw = {key: value for key, value in payload.items() if key != "type"}
    record: Any = TypeAdapter(cls).validate_python(raw)
    normalized = canonical(record)
    if normalized != raw:
        raise ValueError("graph record has noncanonical or unrecognized fields")
    return record


def _deserialize_graph_change(payload: dict[str, Any]) -> GraphChangePayload:
    try:
        if payload.get("event_type") != "GRAPH_SNAPSHOT_CHANGE":
            raise ValueError("unsupported event type")
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported graph event schema")
        return GraphChangePayload(
            event_id=str(payload["event_id"]),
            tenant_id=str(payload["tenant_id"]),
            project_id=str(payload["project_id"]),
            actor_id=str(payload["actor_id"]),
            occurred_at=datetime.fromisoformat(str(payload["occurred_at"])),
            expected_revision=int(payload["expected_revision"]),
            expected_snapshot_hash=str(payload["expected_snapshot_hash"]),
            snapshot=_deserialize_graph(payload["snapshot"]),
            schema_version=int(payload["schema_version"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ProjectStateCorrupt("stored graph change event is malformed") from error


def _deserialize_state(payload: dict[str, Any]) -> EventReplayState:
    try:
        return EventReplayState(
            tenant_id=str(payload["tenant_id"]),
            project_id=str(payload["project_id"]),
            base_snapshot_hash=str(payload["base_snapshot_hash"]),
            revision=int(payload["revision"]),
            versions=tuple(
                VersionPointer(
                    str(item["node_id"]), int(item["version"]), str(item["content_hash"])
                )
                for item in payload["versions"]
            ),
            receipts=tuple(_deserialize_receipt(item) for item in payload["receipts"]),
            last_event_at=(
                datetime.fromisoformat(payload["last_event_at"])
                if payload["last_event_at"] is not None
                else None
            ),
            confirmed_evidence_ids=frozenset(
                str(item) for item in payload["confirmed_evidence_ids"]
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ProjectStateCorrupt("stored project replay state is malformed") from error


def _serialize_receipt(receipt: EventReceipt) -> dict[str, Any]:
    return {
        "event_id": receipt.event_id,
        "payload_hash": receipt.payload_hash,
        "revision": receipt.revision,
        "snapshot_hash": receipt.snapshot_hash,
    }


def _deserialize_receipt(payload: dict[str, Any]) -> EventReceipt:
    return EventReceipt(
        event_id=str(payload["event_id"]),
        payload_hash=str(payload["payload_hash"]),
        revision=int(payload["revision"]),
        snapshot_hash=str(payload["snapshot_hash"]),
    )
