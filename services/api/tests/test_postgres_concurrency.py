"""Real PostgreSQL serialization test; enabled with ORCIFY_TEST_DATABASE_URL."""

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from gamo_ca.approvals import ReviewerIdentity
from gamo_ca.events import EventReplayState, GraphChangeIdentity, GraphChangePayload
from gamo_ca.fingerprints import requirement_fingerprint
from gamo_ca.fixtures import NOW, change_event, toy_graph
from gamo_ca.graph import Graph
from gamo_ca.models import Approval, ApprovalDecision, AssetVersion, Requirement
from gamo_ca.planner import Policy, plan_change
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from services.api.app.event_store import (
    EventConflict,
    StaleProjectRevision,
    append_approval,
    append_change_event,
    append_graph_change,
    create_project,
    load_current_graph,
    replay_project_graph,
)
from services.api.app.models import (
    ApprovalRecord,
    Base,
    ChangeEventRecord,
    EventOutboxRecord,
    ProjectRecord,
    ProjectSnapshotRecord,
)

TEST_DATABASE_URL = os.getenv("ORCIFY_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="set ORCIFY_TEST_DATABASE_URL to a disposable migrated PostgreSQL database",
)


def test_concurrent_expected_revision_allows_one_authoritative_event() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    token = uuid4().hex
    tenant_id, project_id = f"test-tenant-{token}", f"test-project-{token}"
    base = toy_graph()
    graph = replace(
        base,
        tenant_id=tenant_id,
        project_id=project_id,
        nodes=tuple(
            replace(node, tenant_id=tenant_id, project_id=project_id) for node in base.nodes
        ),
        edges=tuple(
            replace(edge, tenant_id=tenant_id, project_id=project_id) for edge in base.edges
        ),
    )
    event_a = change_event(graph=graph)
    event_b = replace(event_a, id=f"event-b-{token}")
    with Session(engine) as session:
        create_project(
            session,
            tenant_id,
            project_id,
            EventReplayState.from_graph(graph),
            initial_graph=graph,
        )

    gate = Barrier(2)

    def write(event_payload):
        gate.wait(timeout=10)
        with Session(engine) as session:
            try:
                return append_change_event(
                    session,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    event=event_payload,
                    idempotency_key=f"key-{event_payload.id}",
                    expected_revision=0,
                )
            except StaleProjectRevision as error:
                return error

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(write, (event_a, event_b)))
        assert sum(not isinstance(item, StaleProjectRevision) for item in outcomes) == 1
        assert sum(isinstance(item, StaleProjectRevision) for item in outcomes) == 1
        with Session(engine) as session:
            project = session.get(ProjectRecord, (tenant_id, project_id))
            assert project is not None and project.revision == 1
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChangeEventRecord)
                    .where(
                        ChangeEventRecord.tenant_id == tenant_id,
                        ChangeEventRecord.project_id == project_id,
                    )
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(EventOutboxRecord)
                    .where(
                        EventOutboxRecord.tenant_id == tenant_id,
                        EventOutboxRecord.project_id == project_id,
                    )
                )
                == 1
            )
    finally:
        _cleanup_tenant(engine, tenant_id)
        engine.dispose()


def test_postgres_idempotency_append_only_and_outbox_rollback(monkeypatch) -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    token = uuid4().hex
    tenant_id, project_id = f"pg-tenant-{token}", f"pg-project-{token}"
    graph = _scoped_graph(tenant_id, project_id)
    with Session(engine) as session:
        create_project(
            session, tenant_id, project_id, EventReplayState.from_graph(graph), initial_graph=graph
        )
    try:
        asset = next(node for node in graph.nodes if isinstance(node, AssetVersion))
        approval = Approval(
            id=f"approval-{token}",
            tenant_id=tenant_id,
            project_id=project_id,
            created_at=NOW + timedelta(seconds=2),
            asset_version_id=asset.id,
            asset_version=asset.version,
            requirement_fingerprint=requirement_fingerprint(graph.requirements),
            actor_id="reviewer-1",
            decision=ApprovalDecision.SUBMITTED,
            policy_version=asset.policy_version,
            idempotency_key=f"approval-key-{token}",
            expected_revision=0,
        )
        identity = ReviewerIdentity("reviewer-1", tenant_id, project_id, "reviewer", True)
        plan = plan_change(graph, change_event("note", graph), Policy())
        with Session(engine) as session:
            append_approval(session, command=approval, identity=identity, graph=graph, plan=plan)
            replay = append_approval(
                session, command=approval, identity=identity, graph=graph, plan=plan
            )
            assert replay.replayed is True

        event_payload = change_event(graph=graph)
        with Session(engine) as session:
            first = append_change_event(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
                event=event_payload,
                idempotency_key=f"event-key-{token}",
                expected_revision=0,
            )
            duplicate = append_change_event(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
                event=event_payload,
                idempotency_key=f"event-key-{token}",
                expected_revision=0,
            )
            assert duplicate.replayed is True and duplicate.receipt == first.receipt
            with pytest.raises(EventConflict, match="idempotency"):
                append_change_event(
                    session,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    event=replace(event_payload, actor_id="other-actor"),
                    idempotency_key=f"event-key-{token}",
                    expected_revision=0,
                )
            with pytest.raises(StaleProjectRevision):
                append_change_event(
                    session,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    event=replace(event_payload, id=f"stale-{token}"),
                    idempotency_key=f"stale-key-{token}",
                    expected_revision=0,
                )

        for table in ("change_events", "project_snapshots", "approvals"):
            with engine.connect() as connection:
                transaction = connection.begin()
                with pytest.raises(DBAPIError):
                    connection.execute(
                        text(f"UPDATE {table} SET payload = payload WHERE tenant_id = :tenant"),
                        {"tenant": tenant_id},
                    )
                transaction.rollback()

        rollback_project_id = f"rollback-{token}"
        rollback_graph = _scoped_graph(tenant_id, rollback_project_id)
        with Session(engine) as session:
            create_project(
                session,
                tenant_id,
                rollback_project_id,
                EventReplayState.from_graph(rollback_graph),
                initial_graph=rollback_graph,
            )

        def fail_outbox(*args, **kwargs) -> None:
            raise RuntimeError("injected PostgreSQL outbox failure")

        monkeypatch.setattr("services.api.app.event_store._insert_outbox", fail_outbox)
        with Session(engine) as session:
            with pytest.raises(RuntimeError, match="injected PostgreSQL"):
                append_change_event(
                    session,
                    tenant_id=tenant_id,
                    project_id=rollback_project_id,
                    event=change_event(graph=rollback_graph),
                    idempotency_key=f"rollback-key-{token}",
                    expected_revision=0,
                )
            session.rollback()
        with Session(engine) as session:
            assert session.get(ProjectRecord, (tenant_id, rollback_project_id)).revision == 0
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChangeEventRecord)
                    .where(
                        ChangeEventRecord.tenant_id == tenant_id,
                        ChangeEventRecord.project_id == rollback_project_id,
                    )
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ProjectSnapshotRecord)
                    .where(
                        ProjectSnapshotRecord.tenant_id == tenant_id,
                        ProjectSnapshotRecord.project_id == rollback_project_id,
                    )
                )
                == 2
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(EventOutboxRecord)
                    .where(
                        EventOutboxRecord.tenant_id == tenant_id,
                        EventOutboxRecord.project_id == rollback_project_id,
                    )
                )
                == 0
            )
    finally:
        _cleanup_tenant(engine, tenant_id)
        engine.dispose()


def test_concurrent_graph_changes_advance_one_immutable_snapshot() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL, pool_size=4, max_overflow=0)
    token = uuid4().hex
    tenant_id, project_id = f"graph-tenant-{token}", f"graph-project-{token}"
    graph = _scoped_graph(tenant_id, project_id)
    instant = max(NOW, graph.as_of + timedelta(seconds=1))
    nodes = tuple(
        replace(
            node,
            version=node.version + 1,
            content="PostgreSQL concurrent snapshot test",
            valid_from=instant,
            confirmed_by="producer-1",
        )
        if isinstance(node, Requirement) and node.id == "slogan"
        else node
        for node in graph.nodes
    )
    changed_graph = Graph(tenant_id, project_id, instant, nodes, graph.edges)
    identity = GraphChangeIdentity("producer-1", tenant_id, project_id, "producer", True)
    change_a = GraphChangePayload(
        f"graph-event-a-{token}",
        tenant_id,
        project_id,
        "producer-1",
        instant,
        0,
        graph.snapshot_hash,
        changed_graph,
    )
    change_b = replace(change_a, event_id=f"graph-event-b-{token}")
    with Session(engine) as session:
        create_project(
            session, tenant_id, project_id, EventReplayState.from_graph(graph), initial_graph=graph
        )
    gate = Barrier(2)

    def write(change):
        gate.wait(timeout=10)
        with Session(engine) as session:
            try:
                return append_graph_change(
                    session, change=change, identity=identity, idempotency_key=change.event_id
                )
            except StaleProjectRevision as error:
                return error

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(write, (change_a, change_b)))
        assert sum(not isinstance(item, StaleProjectRevision) for item in outcomes) == 1
        assert sum(isinstance(item, StaleProjectRevision) for item in outcomes) == 1
        with Session(engine) as session:
            project = session.get(ProjectRecord, (tenant_id, project_id))
            assert project is not None and project.revision == 1
            assert project.current_graph_hash == changed_graph.snapshot_hash
            assert (
                load_current_graph(session, tenant_id, project_id).snapshot_hash
                == changed_graph.snapshot_hash
            )
            assert (
                replay_project_graph(session, tenant_id, project_id).snapshot_hash
                == changed_graph.snapshot_hash
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(EventOutboxRecord)
                    .where(
                        EventOutboxRecord.tenant_id == tenant_id,
                        EventOutboxRecord.project_id == project_id,
                    )
                )
                == 1
            )
    finally:
        _cleanup_tenant(engine, tenant_id)
        engine.dispose()


def _scoped_graph(tenant_id: str, project_id: str) -> Graph:
    base = toy_graph()
    scoped_nodes = tuple(
        replace(node, tenant_id=tenant_id, project_id=project_id) for node in base.nodes
    )
    req_fingerprint = requirement_fingerprint(
        tuple(node for node in scoped_nodes if isinstance(node, Requirement))
    )
    scoped_nodes = tuple(
        replace(node, requirement_fingerprint=req_fingerprint)
        if isinstance(node, AssetVersion)
        else node
        for node in scoped_nodes
    )
    return replace(
        base,
        tenant_id=tenant_id,
        project_id=project_id,
        nodes=scoped_nodes,
        edges=tuple(
            replace(edge, tenant_id=tenant_id, project_id=project_id) for edge in base.edges
        ),
    )


def _cleanup_tenant(engine: Engine, tenant_id: str) -> None:
    # Test fixtures are isolated by tenant; production history stays append-only.
    with engine.begin() as connection:
        for table in ("change_events", "project_snapshots", "approvals"):
            connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
        connection.execute(
            delete(EventOutboxRecord).where(EventOutboxRecord.tenant_id == tenant_id)
        )
        connection.execute(
            delete(ChangeEventRecord).where(ChangeEventRecord.tenant_id == tenant_id)
        )
        connection.execute(
            delete(ProjectSnapshotRecord).where(ProjectSnapshotRecord.tenant_id == tenant_id)
        )
        connection.execute(delete(ApprovalRecord).where(ApprovalRecord.tenant_id == tenant_id))
        connection.execute(delete(ProjectRecord).where(ProjectRecord.tenant_id == tenant_id))
        for table in ("change_events", "project_snapshots", "approvals"):
            connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))
