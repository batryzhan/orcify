from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta

import pytest
from gamo_ca.approvals import ReviewerIdentity
from gamo_ca.events import (
    EventReplayState,
    GraphChangeIdentity,
    GraphChangePayload,
)
from gamo_ca.fingerprints import requirement_fingerprint
from gamo_ca.fixtures import NOW, change_event, toy_graph
from gamo_ca.models import Approval, ApprovalDecision, AssetVersion, Requirement
from gamo_ca.planner import Policy, plan_change
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from services.api.app.event_store import (
    EventConflict,
    ProjectNotFound,
    StaleProjectRevision,
    append_approval,
    append_change_event,
    append_graph_change,
    create_project,
    list_project_events,
    load_current_graph,
    load_project,
    replay_project_graph,
)
from services.api.app.models import (
    ApprovalRecord,
    Base,
    ChangeEventRecord,
    EventOutboxRecord,
    ImmutableEventMutation,
    ImmutableRecordMutation,
    ProjectSnapshotRecord,
)


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session(db_engine: Engine) -> Iterator[Session]:
    with Session(db_engine) as db:
        yield db


def setup_project(session: Session) -> tuple[str, str]:
    graph = toy_graph()
    create_project(
        session,
        graph.tenant_id,
        graph.project_id,
        EventReplayState.from_graph(graph),
        initial_graph=graph,
    )
    return graph.tenant_id, graph.project_id


def graph_change(graph):
    instant = max(NOW, graph.as_of + timedelta(seconds=1))
    nodes = tuple(
        replace(
            node,
            version=node.version + 1,
            content="Updated requirement",
            valid_from=instant,
            confirmed_by="producer-1",
        )
        if isinstance(node, Requirement) and node.id == "slogan"
        else node
        for node in graph.nodes
    )
    snapshot = type(graph)(graph.tenant_id, graph.project_id, instant, nodes, graph.edges)
    return GraphChangePayload(
        "graph-event-1",
        graph.tenant_id,
        graph.project_id,
        "producer-1",
        instant,
        0,
        graph.snapshot_hash,
        snapshot,
    )


def graph_identity(graph):
    return GraphChangeIdentity("producer-1", graph.tenant_id, graph.project_id, "producer", True)


def test_graph_event_persists_typed_snapshot_and_replays_from_immutable_history(session: Session):
    graph = toy_graph()
    create_project(
        session,
        graph.tenant_id,
        graph.project_id,
        EventReplayState.from_graph(graph),
        initial_graph=graph,
    )
    change = graph_change(graph)
    first = append_graph_change(
        session, change=change, identity=graph_identity(graph), idempotency_key="graph-key"
    )
    duplicate = append_graph_change(
        session, change=change, identity=graph_identity(graph), idempotency_key="graph-key"
    )

    assert first.revision == 1 and not first.replayed
    assert duplicate.replayed and duplicate.receipt == first.receipt
    assert first.snapshot_hash == change.snapshot.snapshot_hash
    assert (
        load_current_graph(session, graph.tenant_id, graph.project_id).snapshot_hash
        == change.snapshot.snapshot_hash
    )
    assert (
        replay_project_graph(session, graph.tenant_id, graph.project_id).snapshot_hash
        == change.snapshot.snapshot_hash
    )
    assert (
        len(
            session.scalars(
                select(ProjectSnapshotRecord).where(ProjectSnapshotRecord.snapshot_kind == "graph")
            ).all()
        )
        == 2
    )
    assert len(session.scalars(select(EventOutboxRecord)).all()) == 1
    session.rollback()
    with pytest.raises(EventConflict, match="conflicting request payload"):
        append_graph_change(
            session,
            change=replace(change, event_id="different-graph-event"),
            identity=graph_identity(graph),
            idempotency_key="graph-key",
        )
    session.rollback()
    with pytest.raises(StaleProjectRevision):
        append_graph_change(
            session,
            change=replace(change, event_id="stale-graph-event"),
            identity=graph_identity(graph),
            idempotency_key="stale-graph-key",
        )
    session.rollback()
    with pytest.raises(EventConflict, match="another idempotency key"):
        append_graph_change(
            session,
            change=change,
            identity=graph_identity(graph),
            idempotency_key="second-graph-key",
        )


def test_graph_event_outbox_failure_rolls_back_snapshot_pointer_and_event(
    session: Session, monkeypatch
):
    graph = toy_graph()
    create_project(
        session,
        graph.tenant_id,
        graph.project_id,
        EventReplayState.from_graph(graph),
        initial_graph=graph,
    )
    change = graph_change(graph)

    def fail_outbox(*args, **kwargs):
        raise RuntimeError("injected graph outbox failure")

    monkeypatch.setattr("services.api.app.event_store._insert_outbox", fail_outbox)
    with pytest.raises(RuntimeError, match="injected graph"):
        append_graph_change(
            session, change=change, identity=graph_identity(graph), idempotency_key="graph-key"
        )
    session.rollback()
    assert load_project(session, graph.tenant_id, graph.project_id).revision == 0
    assert (
        load_current_graph(session, graph.tenant_id, graph.project_id).snapshot_hash
        == graph.snapshot_hash
    )
    assert session.scalars(select(ChangeEventRecord)).all() == []
    assert session.scalars(select(EventOutboxRecord)).all() == []
    assert (
        len(
            session.scalars(
                select(ProjectSnapshotRecord).where(ProjectSnapshotRecord.snapshot_kind == "graph")
            ).all()
        )
        == 1
    )


def test_event_and_outbox_commit_atomically_with_project_revision(session: Session) -> None:
    tenant_id, project_id = setup_project(session)
    graph = toy_graph()
    event = change_event(graph=graph)

    result = append_change_event(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        event=event,
        idempotency_key="request-1",
        expected_revision=0,
    )

    project = load_project(session, tenant_id, project_id)
    assert result.replayed is False
    assert result.revision == 1
    assert project.revision == 1
    assert project.current_snapshot_hash == result.snapshot_hash
    assert len(list_project_events(session, tenant_id, project_id)) == 1
    outbox = session.scalars(select(EventOutboxRecord)).all()
    assert len(outbox) == 1
    assert outbox[0].event_id == event.id


def test_exact_duplicate_returns_original_receipt_without_duplicate_outbox(
    session: Session,
) -> None:
    tenant_id, project_id = setup_project(session)
    event = change_event(graph=toy_graph())
    first = append_change_event(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        event=event,
        idempotency_key="request-1",
        expected_revision=0,
    )

    replay = append_change_event(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        event=event,
        idempotency_key="request-1",
        expected_revision=0,
    )

    assert replay.replayed is True
    assert replay.receipt == first.receipt
    assert replay.revision == 1
    assert len(list_project_events(session, tenant_id, project_id)) == 1
    assert session.scalar(select(EventOutboxRecord.id)) is not None
    assert len(session.scalars(select(EventOutboxRecord)).all()) == 1


def test_idempotency_and_event_id_payload_conflicts_are_rejected(session: Session) -> None:
    tenant_id, project_id = setup_project(session)
    event = change_event(graph=toy_graph())
    append_change_event(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        event=event,
        idempotency_key="request-1",
        expected_revision=0,
    )

    with pytest.raises(EventConflict, match="idempotency"):
        append_change_event(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            event=replace(event, actor_id="different-actor"),
            idempotency_key="request-1",
            expected_revision=0,
        )
    with pytest.raises(EventConflict, match="event ID"):
        append_change_event(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            event=event,
            idempotency_key="another-key",
            expected_revision=1,
        )


def test_stale_revision_and_cross_tenant_access_fail_closed(session: Session) -> None:
    tenant_id, project_id = setup_project(session)
    event = change_event(graph=toy_graph())
    with pytest.raises(StaleProjectRevision):
        append_change_event(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            event=event,
            idempotency_key="request-1",
            expected_revision=1,
        )
    with pytest.raises(EventConflict, match="stale snapshot"):
        append_change_event(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            event=replace(event, expected_snapshot_hash="0" * 64),
            idempotency_key="request-stale-snapshot",
            expected_revision=0,
        )
    assert load_project(session, tenant_id, project_id).revision == 0
    with pytest.raises(ProjectNotFound):
        load_project(session, "foreign-tenant", project_id)
    with pytest.raises(EventConflict, match="scope"):
        append_change_event(
            session,
            tenant_id="foreign-tenant",
            project_id=project_id,
            event=event,
            idempotency_key="request-1",
            expected_revision=0,
        )


def test_outbox_failure_rolls_back_event_and_revision(session: Session, monkeypatch) -> None:
    tenant_id, project_id = setup_project(session)
    event = change_event(graph=toy_graph())

    def fail_outbox(*args, **kwargs) -> None:
        raise RuntimeError("injected outbox failure")

    monkeypatch.setattr("services.api.app.event_store._insert_outbox", fail_outbox)
    with pytest.raises(RuntimeError, match="injected"):
        append_change_event(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            event=event,
            idempotency_key="request-1",
            expected_revision=0,
        )

    session.rollback()
    assert load_project(session, tenant_id, project_id).revision == 0
    assert list_project_events(session, tenant_id, project_id) == ()
    assert session.scalars(select(EventOutboxRecord)).all() == []


def test_persisted_event_records_cannot_be_mutated_or_deleted(session: Session) -> None:
    tenant_id, project_id = setup_project(session)
    event = change_event(graph=toy_graph())
    append_change_event(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        event=event,
        idempotency_key="request-1",
        expected_revision=0,
    )
    record = session.scalar(select(ChangeEventRecord))
    assert record is not None
    record.payload["actor_id"] = "mutated"

    with pytest.raises(ImmutableEventMutation, match="append-only"):
        session.flush()
    session.rollback()
    stored = list_project_events(session, tenant_id, project_id)
    assert stored[0].payload["actor_id"] == event.actor_id
    session.delete(stored[0])
    with pytest.raises(ImmutableEventMutation, match="append-only"):
        session.flush()
    session.rollback()
    assert len(list_project_events(session, tenant_id, project_id)) == 1


def test_event_replay_snapshots_are_immutable_and_revisioned(session: Session) -> None:
    tenant_id, project_id = setup_project(session)
    event_payload = change_event(graph=toy_graph())
    append_change_event(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        event=event_payload,
        idempotency_key="snapshot-event",
        expected_revision=0,
    )
    rows = session.scalars(
        select(ProjectSnapshotRecord).order_by(ProjectSnapshotRecord.revision)
    ).all()
    assert [(row.revision, row.snapshot_kind) for row in rows] == [
        (0, "replay_state"),
        (0, "graph"),
        (1, "replay_state"),
    ]
    graph_snapshot = next(row for row in rows if row.snapshot_kind == "graph")
    assert graph_snapshot.payload["snapshot_hash"] == toy_graph().snapshot_hash
    assert len(graph_snapshot.payload["nodes"]) == len(toy_graph().nodes)
    rows[-1].payload["revision"] = 80
    with pytest.raises(ImmutableRecordMutation, match="append-only"):
        session.flush()
    session.rollback()


def test_approval_persistence_uses_pure_transition_and_is_idempotent(session: Session) -> None:
    graph = toy_graph()
    tenant_id, project_id = graph.tenant_id, graph.project_id
    create_project(
        session,
        tenant_id,
        project_id,
        EventReplayState.from_graph(graph),
        initial_graph=graph,
    )
    asset = next(node for node in graph.nodes if isinstance(node, AssetVersion))
    command = Approval(
        id="persisted-approval",
        tenant_id=tenant_id,
        project_id=project_id,
        created_at=NOW + timedelta(seconds=2),
        asset_version_id=asset.id,
        asset_version=asset.version,
        requirement_fingerprint=requirement_fingerprint(graph.requirements),
        actor_id="reviewer-1",
        decision=ApprovalDecision.SUBMITTED,
        policy_version=asset.policy_version,
        idempotency_key="approval-request-1",
        expected_revision=0,
    )
    identity = ReviewerIdentity("reviewer-1", tenant_id, project_id, "reviewer", True)
    plan = plan_change(graph, change_event("note", graph), Policy())
    first = append_approval(
        session,
        command=command,
        identity=identity,
        graph=graph,
        plan=plan,
    )
    duplicate = append_approval(
        session,
        command=replace(command, created_at=NOW + timedelta(seconds=3)),
        identity=identity,
        graph=graph,
        plan=plan,
    )
    assert first.latest == command and first.replayed is False
    assert duplicate.latest == first.latest and duplicate.replayed is True
    assert len(session.scalars(select(ApprovalRecord)).all()) == 1
    record = session.scalar(select(ApprovalRecord))
    assert record is not None
    record.payload["decision"] = ApprovalDecision.REVOKED.value
    with pytest.raises(ImmutableRecordMutation, match="append-only"):
        session.flush()
    session.rollback()


def test_approval_store_rejects_wrong_tenant_and_payload_reuse(session: Session) -> None:
    graph = toy_graph()
    create_project(
        session,
        graph.tenant_id,
        graph.project_id,
        EventReplayState.from_graph(graph),
        initial_graph=graph,
    )
    asset = next(node for node in graph.nodes if isinstance(node, AssetVersion))
    command = Approval(
        id="scope-approval",
        tenant_id=graph.tenant_id,
        project_id=graph.project_id,
        created_at=NOW + timedelta(seconds=2),
        asset_version_id=asset.id,
        asset_version=asset.version,
        requirement_fingerprint=requirement_fingerprint(graph.requirements),
        actor_id="reviewer-1",
        decision=ApprovalDecision.SUBMITTED,
        policy_version=asset.policy_version,
        idempotency_key="approval-scope-key",
        expected_revision=0,
    )
    identity = ReviewerIdentity("reviewer-1", graph.tenant_id, graph.project_id, "reviewer", True)
    plan = plan_change(graph, change_event("note", graph), Policy())
    with pytest.raises(EventConflict, match="scope"):
        append_approval(
            session,
            command=command,
            identity=ReviewerIdentity("reviewer-1", "other", graph.project_id, "reviewer", True),
            graph=graph,
            plan=plan,
        )
    append_approval(session, command=command, identity=identity, graph=graph, plan=plan)
    conflict = replace(command, actor_id="different-reviewer")
    with pytest.raises(EventConflict, match="conflicting payload"):
        append_approval(
            session,
            command=conflict,
            identity=replace(identity, actor_id="different-reviewer"),
            graph=graph,
            plan=plan,
        )
