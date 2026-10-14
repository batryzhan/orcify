from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest
from gamo_ca.events import EventReplayState, GraphChangeIdentity, GraphChangePayload
from gamo_ca.fingerprints import fingerprint
from gamo_ca.fixtures import NOW, change_event, toy_graph
from gamo_ca.graph import Graph
from gamo_ca.models import Requirement
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from services.api.app.event_store import append_change_event, append_graph_change, create_project
from services.api.app.models import (
    Base,
    EventOutboxRecord,
    ProjectionCheckpointRecord,
)
from services.api.app.neo4j_projection import (
    ProjectionState,
    StaleProjectionEvent,
)
from services.api.app.projection_worker import (
    WorkerConfig,
    process_next,
    reconcile_all,
)


@pytest.fixture
def db_sessions() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()


@dataclass
class _FakeProject:
    graph: Graph
    revision: int
    event_id: str

    @property
    def state(self) -> ProjectionState:
        return ProjectionState(
            self.graph.tenant_id,
            self.graph.project_id,
            self.revision,
            self.graph.snapshot_hash,
            self.event_id,
            tuple(sorted((node.id, fingerprint(node)) for node in self.graph.nodes)),
            tuple(sorted((edge.id, fingerprint(edge)) for edge in self.graph.edges)),
        )


class _FakeProjection:
    def __init__(self) -> None:
        self.projects: dict[tuple[str, str], _FakeProject] = {}
        self.failures = 0

    def inspect(self, tenant_id: str, project_id: str) -> ProjectionState | None:
        project = self.projects.get((tenant_id, project_id))
        return project.state if project else None

    def initialize(self, graph: Graph) -> ProjectionState:
        key = graph.tenant_id, graph.project_id
        prior = self.projects.get(key)
        event_id = f"initial:{graph.snapshot_hash}"
        if prior is not None:
            if prior.revision != 0 or prior.graph.snapshot_hash != graph.snapshot_hash:
                raise StaleProjectionEvent("initial projection conflicts")
            return prior.state
        self.projects[key] = _FakeProject(graph, 0, event_id)
        return self.projects[key].state

    def apply_graph_change(
        self,
        graph: Graph,
        *,
        source_revision: int,
        event_id: str,
        expected_revision: int,
        expected_graph_hash: str,
    ) -> ProjectionState:
        key = graph.tenant_id, graph.project_id
        prior = self.projects[key]
        if self.failures:
            self.failures -= 1
            raise OSError("injected Neo4j unavailable")
        if prior.revision == source_revision:
            if prior.event_id == event_id and prior.graph.snapshot_hash == graph.snapshot_hash:
                return prior.state
            raise StaleProjectionEvent("revision conflict")
        if prior.revision != expected_revision or prior.graph.snapshot_hash != expected_graph_hash:
            raise StaleProjectionEvent("base checkpoint mismatch")
        self.projects[key] = _FakeProject(graph, source_revision, event_id)
        return self.projects[key].state

    def advance_checkpoint(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_revision: int,
        event_id: str,
        expected_revision: int,
        graph_hash: str,
    ) -> ProjectionState:
        prior = self.projects[(tenant_id, project_id)]
        if prior.revision == source_revision and prior.event_id == event_id:
            return prior.state
        if prior.revision != expected_revision or prior.graph.snapshot_hash != graph_hash:
            raise StaleProjectionEvent("base checkpoint mismatch")
        self.projects[(tenant_id, project_id)] = _FakeProject(
            prior.graph, source_revision, event_id
        )
        return self.projects[(tenant_id, project_id)].state

    def rebuild(self, graph: Graph, *, source_revision: int, event_id: str) -> ProjectionState:
        self.projects[(graph.tenant_id, graph.project_id)] = _FakeProject(
            graph, source_revision, event_id
        )
        return self.projects[(graph.tenant_id, graph.project_id)].state


def _graph_change(graph: Graph, event_id: str = "projection-graph-event") -> GraphChangePayload:
    instant = max(NOW, graph.as_of + timedelta(seconds=1))
    nodes = tuple(
        replace(
            node,
            version=node.version + 1,
            content="Projection worker requirement",
            valid_from=instant,
            confirmed_by="producer-1",
        )
        if isinstance(node, Requirement) and node.id == "slogan"
        else node
        for node in graph.nodes
    )
    changed_graph = Graph(graph.tenant_id, graph.project_id, instant, nodes, graph.edges)
    return GraphChangePayload(
        event_id,
        graph.tenant_id,
        graph.project_id,
        "producer-1",
        instant,
        0,
        graph.snapshot_hash,
        changed_graph,
    )


def _project_with_graph_event(
    sessions: sessionmaker[Session], tenant_id: str, project_id: str
) -> Graph:
    base = toy_graph()
    graph = Graph(
        tenant_id,
        project_id,
        base.as_of,
        tuple(replace(n, tenant_id=tenant_id, project_id=project_id) for n in base.nodes),
        tuple(replace(e, tenant_id=tenant_id, project_id=project_id) for e in base.edges),
    )
    with sessions() as session:
        create_project(
            session, tenant_id, project_id, EventReplayState.from_graph(graph), initial_graph=graph
        )
        append_graph_change(
            session,
            change=_graph_change(graph),
            identity=GraphChangeIdentity("producer-1", tenant_id, project_id, "producer", True),
            idempotency_key=f"idempotency-{project_id}",
        )
    return graph


def test_worker_retries_with_bounded_exponential_backoff_and_then_projects(db_sessions):
    initial = _project_with_graph_event(db_sessions, "tenant-a", "project-a")
    projection = _FakeProjection()
    projection.failures = 2
    start = datetime.now(UTC)
    config = WorkerConfig(max_attempts=3, base_backoff_seconds=2, max_backoff_seconds=10)

    first = process_next(db_sessions, projection, config, now=start)
    assert first.status == "retry" and first.retry_at == start + timedelta(seconds=2)
    assert process_next(db_sessions, projection, config, now=start).status == "idle"
    second = process_next(db_sessions, projection, config, now=first.retry_at)
    assert second.status == "retry" and second.retry_at == first.retry_at + timedelta(seconds=4)
    third = process_next(db_sessions, projection, config, now=second.retry_at)

    assert third.succeeded and third.source_revision == 1
    projected = projection.inspect("tenant-a", "project-a")
    assert projected is not None and projected.source_revision == 1
    assert projected.graph_hash != initial.snapshot_hash
    with db_sessions.begin() as session:
        outbox = session.scalar(select(EventOutboxRecord))
        checkpoint = session.get(ProjectionCheckpointRecord, ("tenant-a", "project-a", "neo4j"))
        assert outbox is not None and outbox.status == "succeeded" and outbox.attempt_count == 3
        assert checkpoint is not None and checkpoint.status == "healthy"
        assert checkpoint.source_revision == 1 and checkpoint.graph_hash == projected.graph_hash


def test_worker_dead_letters_after_retry_limit_and_blocks_later_events(db_sessions):
    _project_with_graph_event(db_sessions, "tenant-b", "project-b")
    projection = _FakeProjection()
    projection.failures = 10
    start = datetime.now(UTC)
    config = WorkerConfig(max_attempts=2, base_backoff_seconds=1)
    first = process_next(db_sessions, projection, config, now=start)
    second = process_next(db_sessions, projection, config, now=first.retry_at)
    assert first.status == "retry" and second.status == "dead"
    with db_sessions.begin() as session:
        outbox = session.scalar(select(EventOutboxRecord))
        checkpoint = session.get(ProjectionCheckpointRecord, ("tenant-b", "project-b", "neo4j"))
        assert outbox is not None and outbox.status == "dead" and outbox.attempt_count == 2
        assert checkpoint is not None and checkpoint.status == "error"
        assert "injected Neo4j unavailable" in (outbox.last_error or "")
    assert (
        process_next(db_sessions, projection, config, now=start + timedelta(days=1)).status
        == "idle"
    )


def test_worker_recovers_neo4j_commit_before_postgres_checkpoint_crash(db_sessions):
    initial = _project_with_graph_event(db_sessions, "tenant-crash", "project-crash")
    change = _graph_change(initial)
    projection = _FakeProjection()
    projection.initialize(initial)
    # Simulate Neo4j committing while the worker crashes before its PostgreSQL commit.
    projection.apply_graph_change(
        change.snapshot,
        source_revision=1,
        event_id=change.event_id,
        expected_revision=0,
        expected_graph_hash=initial.snapshot_hash,
    )

    recovered = process_next(db_sessions, projection, now=datetime.now(UTC))

    assert recovered.succeeded
    state = projection.inspect("tenant-crash", "project-crash")
    assert state is not None and state.graph_hash == change.snapshot.snapshot_hash
    with db_sessions() as session:
        checkpoint = session.get(
            ProjectionCheckpointRecord, ("tenant-crash", "project-crash", "neo4j")
        )
        assert checkpoint is not None
        assert checkpoint.source_revision == 1 and checkpoint.last_event_id == change.event_id


def test_reconciliation_rebuilds_missing_or_inconsistent_projection(db_sessions):
    graph = _project_with_graph_event(db_sessions, "tenant-c", "project-c")
    projection = _FakeProjection()
    rebuilt = reconcile_all(db_sessions, projection, now=datetime.now(UTC))
    assert len(rebuilt) == 1 and rebuilt[0].rebuilt
    state = projection.inspect("tenant-c", "project-c")
    assert state is not None and state.source_revision == 1
    assert state.graph_hash != graph.snapshot_hash
    with db_sessions() as session:
        outbox = session.scalar(select(EventOutboxRecord))
        checkpoint = session.get(ProjectionCheckpointRecord, ("tenant-c", "project-c", "neo4j"))
        assert outbox is not None and outbox.status == "superseded"
        assert checkpoint is not None and checkpoint.status == "healthy"

    projection.projects["tenant-c", "project-c"].graph = graph
    repaired = reconcile_all(db_sessions, projection, now=datetime.now(UTC))
    assert repaired[0].rebuilt
    assert projection.inspect("tenant-c", "project-c").graph_hash == state.graph_hash


def test_pointer_event_advances_ordered_checkpoint_without_changing_graph(db_sessions):
    graph = toy_graph()
    with db_sessions() as session:
        create_project(
            session,
            graph.tenant_id,
            graph.project_id,
            EventReplayState.from_graph(graph),
            initial_graph=graph,
        )
        append_change_event(
            session,
            tenant_id=graph.tenant_id,
            project_id=graph.project_id,
            event=change_event(graph=graph),
            idempotency_key="pointer-event-key",
            expected_revision=0,
        )
    projection = _FakeProjection()
    result = process_next(db_sessions, projection, now=datetime.now(UTC))
    state = projection.inspect(graph.tenant_id, graph.project_id)
    assert result.succeeded and state is not None
    assert state.source_revision == 1 and state.graph_hash == graph.snapshot_hash


def test_projection_payload_scope_is_checked_before_adapter_mutation(db_sessions):
    _project_with_graph_event(db_sessions, "tenant-d", "project-d")
    projection = _FakeProjection()
    with db_sessions.begin() as session:
        outbox = session.scalar(select(EventOutboxRecord))
        assert outbox is not None
        outbox.payload = {**outbox.payload, "tenant_id": "foreign-tenant"}
    result = process_next(db_sessions, projection, now=datetime.now(UTC))
    assert not result.succeeded
    assert projection.inspect("tenant-d", "project-d") is None
