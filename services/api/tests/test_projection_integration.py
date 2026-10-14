"""Live PostgreSQL + Neo4j projection checks; both services are explicitly opt-in."""

import os
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from gamo_ca.events import EventReplayState, GraphChangeIdentity, GraphChangePayload
from gamo_ca.fixtures import NOW, toy_graph
from gamo_ca.graph import Graph
from gamo_ca.models import Requirement
from neo4j import GraphDatabase
from sqlalchemy import create_engine, delete, text
from sqlalchemy.orm import sessionmaker

from services.api.app.event_store import append_graph_change, create_project
from services.api.app.models import (
    ApprovalRecord,
    ChangeEventRecord,
    EventOutboxRecord,
    ProjectionCheckpointRecord,
    ProjectRecord,
    ProjectSnapshotRecord,
)
from services.api.app.neo4j_projection import Neo4jGraphProjection, StaleProjectionEvent
from services.api.app.projection_worker import process_next, reconcile_project

TEST_DATABASE_URL = os.getenv("ORCIFY_TEST_DATABASE_URL")
TEST_NEO4J_URI = os.getenv("ORCIFY_TEST_NEO4J_URI")
TEST_NEO4J_USER = os.getenv("ORCIFY_TEST_NEO4J_USER")
TEST_NEO4J_PASSWORD = os.getenv("ORCIFY_TEST_NEO4J_PASSWORD")
pytestmark = pytest.mark.skipif(
    not all((TEST_DATABASE_URL, TEST_NEO4J_URI, TEST_NEO4J_USER, TEST_NEO4J_PASSWORD)),
    reason="set PostgreSQL and ORCIFY_TEST_NEO4J_* variables for live projection tests",
)


def test_live_postgres_outbox_projects_and_reconciles_authoritative_snapshot() -> None:
    assert TEST_DATABASE_URL and TEST_NEO4J_URI and TEST_NEO4J_USER and TEST_NEO4J_PASSWORD
    engine = create_engine(TEST_DATABASE_URL, pool_size=3, max_overflow=0)
    sessions = sessionmaker(engine, expire_on_commit=False)
    driver = GraphDatabase.driver(TEST_NEO4J_URI, auth=(TEST_NEO4J_USER, TEST_NEO4J_PASSWORD))
    projection = Neo4jGraphProjection(driver)
    token = uuid4().hex
    tenant_id, project_id = f"projection-tenant-{token}", f"projection-project-{token}"
    base = toy_graph()
    graph = Graph(
        tenant_id,
        project_id,
        base.as_of,
        tuple(replace(node, tenant_id=tenant_id, project_id=project_id) for node in base.nodes),
        tuple(replace(edge, tenant_id=tenant_id, project_id=project_id) for edge in base.edges),
    )
    occurred_at = max(NOW, graph.as_of + timedelta(seconds=1))
    nodes = tuple(
        replace(
            node,
            version=node.version + 1,
            content="Live Neo4j projection test",
            valid_from=occurred_at,
            confirmed_by="producer-1",
        )
        if isinstance(node, Requirement) and node.id == "slogan"
        else node
        for node in graph.nodes
    )
    changed_graph = Graph(tenant_id, project_id, occurred_at, nodes, graph.edges)
    change = GraphChangePayload(
        f"projection-event-{token}",
        tenant_id,
        project_id,
        "producer-1",
        occurred_at,
        0,
        graph.snapshot_hash,
        changed_graph,
    )
    projection.ensure_schema()
    try:
        with sessions() as session:
            create_project(
                session,
                tenant_id,
                project_id,
                EventReplayState.from_graph(graph),
                initial_graph=graph,
            )
            append_graph_change(
                session,
                change=change,
                identity=GraphChangeIdentity("producer-1", tenant_id, project_id, "producer", True),
                idempotency_key=f"projection-key-{token}",
            )
        result = process_next(sessions, projection)
        assert result.succeeded and result.source_revision == 1
        projected = projection.inspect(tenant_id, project_id)
        assert projected is not None
        assert (
            projected.source_revision == 1 and projected.graph_hash == changed_graph.snapshot_hash
        )
        assert len(projected.node_hashes) == len(changed_graph.nodes)
        assert len(projected.edge_hashes) == len(changed_graph.edges)

        exact_retry = projection.apply_graph_change(
            changed_graph,
            source_revision=1,
            event_id=change.event_id,
            expected_revision=0,
            expected_graph_hash=graph.snapshot_hash,
        )
        assert exact_retry.graph_hash == changed_graph.snapshot_hash
        with pytest.raises(StaleProjectionEvent):
            projection.apply_graph_change(
                graph,
                source_revision=1,
                event_id=f"conflicting-{token}",
                expected_revision=0,
                expected_graph_hash=graph.snapshot_hash,
            )

        counts = driver.execute_query(
            "MATCH (n:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id}) "
            "RETURN count(n) AS count",
            tenant_id=tenant_id,
            project_id=project_id,
            database_="neo4j",
        )
        assert counts.records[0]["count"] == len(changed_graph.nodes)
        foreign_counts = driver.execute_query(
            "MATCH (n:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id}) "
            "RETURN count(n) AS count",
            tenant_id=f"foreign-{tenant_id}",
            project_id=project_id,
            database_="neo4j",
        )
        assert foreign_counts.records[0]["count"] == 0
        assert reconcile_project(sessions, projection, tenant_id, project_id).consistent

        with driver.session(database="neo4j") as session:
            session.run(
                "MATCH (n:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id, "
                "node_id: 'note'}) "
                "DETACH DELETE n",
                tenant_id=tenant_id,
                project_id=project_id,
            ).consume()
        repaired = reconcile_project(sessions, projection, tenant_id, project_id)
        assert repaired.rebuilt and not repaired.consistent
        assert projection.inspect(tenant_id, project_id).graph_hash == changed_graph.snapshot_hash
    finally:
        with driver.session(database="neo4j") as session:
            session.run(
                "MATCH (a:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id}) "
                "-[r:DEPENDS_ON {tenant_id: $tenant_id, project_id: $project_id}]-> "
                "(b:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id}) DELETE r",
                tenant_id=tenant_id,
                project_id=project_id,
            ).consume()
            session.run(
                "MATCH (n:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id}) "
                "DETACH DELETE n",
                tenant_id=tenant_id,
                project_id=project_id,
            ).consume()
            session.run(
                "MATCH (p:OrcifyProjection {tenant_id: $tenant_id, project_id: $project_id}) "
                "DELETE p",
                tenant_id=tenant_id,
                project_id=project_id,
            ).consume()
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
            connection.execute(
                delete(ProjectionCheckpointRecord).where(
                    ProjectionCheckpointRecord.tenant_id == tenant_id
                )
            )
            connection.execute(delete(ProjectRecord).where(ProjectRecord.tenant_id == tenant_id))
            for table in ("change_events", "project_snapshots", "approvals"):
                connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))
        driver.close()
        engine.dispose()
