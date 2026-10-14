"""Live PostgreSQL tests for durable artifact and execution records."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import pytest
from gamo_ca.events import EventReplayState
from gamo_ca.fingerprints import requirement_fingerprint
from gamo_ca.fixtures import change_event, toy_graph
from gamo_ca.models import AssetVersion, Requirement
from gamo_ca.planner import Policy, plan_change
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from services.api.app.artifact_schemas import (
    ArtifactCreateRequest,
    DependencyVersion,
    ExecutionAttemptStartRequest,
    ExecutionMetric,
    ExecutionRunCreateRequest,
    ExecutionTransitionRequest,
    MetricStatus,
    ProvenanceInput,
)
from services.api.app.artifact_store import (
    ArtifactConflict,
    StaleArtifactSource,
    create_artifact_version,
    create_execution_run,
    record_execution_transition,
    start_execution_attempt,
)
from services.api.app.event_store import ProjectNotFound, create_project
from services.api.app.models import (
    ApprovalRecord,
    ArtifactProvenanceRecord,
    ArtifactVersionRecord,
    Base,
    ChangeEventRecord,
    EventOutboxRecord,
    ExecutionAttemptRecord,
    ExecutionEventRecord,
    ExecutionRunRecord,
    ProjectRecord,
    ProjectSnapshotRecord,
)

TEST_DATABASE_URL = os.getenv("ORCIFY_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="set ORCIFY_TEST_DATABASE_URL to a disposable migrated PostgreSQL database",
)


def test_postgres_artifact_execution_atomicity_idempotency_and_immutability() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    token = uuid4().hex
    tenant_id = f"artifact-tenant-{token}"
    project_id = f"artifact-project-{token}"
    graph = _scoped_graph(tenant_id, project_id)
    with Session(engine) as session:
        create_project(
            session,
            tenant_id,
            project_id,
            EventReplayState.from_graph(graph),
            initial_graph=graph,
        )
    artifact_command = _artifact_command(graph, token)
    try:
        barrier = Barrier(2)

        def write_artifact():
            barrier.wait(timeout=10)
            with Session(engine) as session:
                return create_artifact_version(
                    session,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    command=artifact_command,
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: write_artifact(), range(2)))
        assert sum(not result.replayed for result in results) == 1
        assert sum(result.replayed for result in results) == 1

        with Session(engine) as session, pytest.raises(StaleArtifactSource, match="revision"):
            create_artifact_version(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
                command=artifact_command.model_copy(
                    update={
                        "expected_project_revision": 1,
                        "idempotency_key": f"stale-{token}",
                        "artifact_version_id": f"stale-version-{token}",
                        "artifact_id": f"stale-artifact-{token}",
                    }
                ),
            )
        with Session(engine) as session, pytest.raises(ProjectNotFound):
            create_artifact_version(
                session,
                tenant_id=f"other-{tenant_id}",
                project_id=project_id,
                command=artifact_command,
            )

        conflicting = artifact_command.model_copy(update={"content": "different"})
        with Session(engine) as session, pytest.raises(ArtifactConflict, match="conflicting"):
            create_artifact_version(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
                command=conflicting,
            )

        run = ExecutionRunCreateRequest(
            run_id=f"run-{token}",
            expected_project_revision=0,
            graph_revision=0,
            graph_snapshot_hash=graph.snapshot_hash,
            planner_decision=plan_change(graph, change_event("note", graph), Policy()),
            idempotency_key=f"run-key-{token}",
        )
        with Session(engine) as session:
            assert (
                create_execution_run(
                    session, tenant_id=tenant_id, project_id=project_id, command=run
                ).status
                == "pending"
            )
            assert create_execution_run(
                session, tenant_id=tenant_id, project_id=project_id, command=run
            ).replayed

        asset = next(node for node in graph.nodes if isinstance(node, AssetVersion))
        attempt = ExecutionAttemptStartRequest(
            attempt_id=f"attempt-{token}",
            node_id=asset.id,
            attempt_number=1,
            dependencies=tuple(
                DependencyVersion(
                    node_id=reference.source_id,
                    node_version=reference.version,
                    content_hash=reference.content_hash,
                )
                for reference in asset.inputs
            ),
            idempotency_key=f"attempt-key-{token}",
            provider_id="offline-mock",
            model_id="fixture-v1",
            prompt_version="fixture-prompt-v1",
        )
        with Session(engine) as session:
            start_execution_attempt(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run.run_id,
                command=attempt,
            )
            transition = ExecutionTransitionRequest(
                event_id=f"finish-{token}",
                idempotency_key=f"finish-key-{token}",
                status="succeeded",
                elapsed=ExecutionMetric(status=MetricStatus.MEASURED, value=0),
            )
            record_execution_transition(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run.run_id,
                attempt_id=attempt.attempt_id,
                command=transition,
            )

        with engine.connect() as connection:
            transaction = connection.begin()
            with pytest.raises(DBAPIError):
                connection.execute(
                    text(
                        "UPDATE artifact_versions SET content = content WHERE tenant_id = :tenant"
                    ),
                    {"tenant": tenant_id},
                )
            transaction.rollback()
            transaction = connection.begin()
            with pytest.raises(DBAPIError):
                connection.execute(
                    text("UPDATE execution_events SET status = status WHERE tenant_id = :tenant"),
                    {"tenant": tenant_id},
                )
            transaction.rollback()
            transaction = connection.begin()
            with pytest.raises(DBAPIError):
                connection.execute(
                    text("UPDATE execution_runs SET plan = plan WHERE tenant_id = :tenant"),
                    {"tenant": tenant_id},
                )
            transaction.rollback()

        rollback_artifact = _artifact_command(graph, f"rollback-{token}").model_copy(
            update={
                "artifact_version_id": f"rollback-version-{token}",
                "artifact_id": f"rollback-artifact-{token}",
                "idempotency_key": f"rollback-key-{token}",
                "provenance": (
                    ProvenanceInput(
                        provenance_id=f"rollback-provenance-{token}",
                        source_kind="graph_node",
                        source_id="missing-node",
                    ),
                ),
            }
        )
        with Session(engine) as session:
            with pytest.raises(StaleArtifactSource):
                create_artifact_version(
                    session,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    command=rollback_artifact,
                )
            session.rollback()
        with Session(engine) as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ArtifactVersionRecord)
                    .where(ArtifactVersionRecord.tenant_id == tenant_id)
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ArtifactProvenanceRecord)
                    .where(ArtifactProvenanceRecord.tenant_id == tenant_id)
                )
                == 1
            )
    finally:
        _cleanup_tenant(engine, tenant_id)
        engine.dispose()


def _scoped_graph(tenant_id: str, project_id: str):
    base = toy_graph()
    nodes = tuple(replace(node, tenant_id=tenant_id, project_id=project_id) for node in base.nodes)
    req_hash = requirement_fingerprint(
        tuple(node for node in nodes if isinstance(node, Requirement))
    )
    nodes = tuple(
        replace(node, requirement_fingerprint=req_hash) if isinstance(node, AssetVersion) else node
        for node in nodes
    )
    return replace(
        base,
        tenant_id=tenant_id,
        project_id=project_id,
        nodes=nodes,
        edges=tuple(
            replace(edge, tenant_id=tenant_id, project_id=project_id) for edge in base.edges
        ),
    )


def _artifact_command(graph, token: str) -> ArtifactCreateRequest:
    asset = next(node for node in graph.nodes if isinstance(node, AssetVersion))
    return ArtifactCreateRequest(
        artifact_version_id=f"artifact-version-{token}",
        artifact_id=f"artifact-{token}",
        node_id=asset.id,
        node_version=asset.version,
        expected_project_revision=0,
        graph_revision=0,
        graph_snapshot_hash=graph.snapshot_hash,
        dependencies=tuple(
            DependencyVersion(
                node_id=ref.source_id,
                node_version=ref.version,
                content_hash=ref.content_hash,
            )
            for ref in asset.inputs
        ),
        content=asset.content,
        planner_decision=plan_change(graph, change_event("note", graph), Policy()),
        idempotency_key=f"artifact-key-{token}",
        provider_id="offline-mock",
        model_id="fixture-v1",
        provenance=(
            ProvenanceInput(
                provenance_id=f"provenance-{token}",
                source_kind="graph_node",
                source_id=asset.inputs[0].source_id,
                details={"source": "verified graph input"},
            ),
        ),
    )


def _cleanup_tenant(engine: Engine, tenant_id: str) -> None:
    with engine.begin() as connection:
        immutable_tables = (
            "change_events",
            "project_snapshots",
            "approvals",
            "artifact_versions",
            "execution_events",
            "artifact_provenance",
            "execution_runs",
            "execution_attempts",
        )
        for table in immutable_tables:
            connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
        connection.execute(
            delete(ArtifactProvenanceRecord).where(ArtifactProvenanceRecord.tenant_id == tenant_id)
        )
        connection.execute(
            delete(ExecutionEventRecord).where(ExecutionEventRecord.tenant_id == tenant_id)
        )
        connection.execute(
            delete(ExecutionAttemptRecord).where(ExecutionAttemptRecord.tenant_id == tenant_id)
        )
        connection.execute(
            delete(ExecutionRunRecord).where(ExecutionRunRecord.tenant_id == tenant_id)
        )
        connection.execute(
            delete(ArtifactVersionRecord).where(ArtifactVersionRecord.tenant_id == tenant_id)
        )
        connection.execute(
            delete(EventOutboxRecord).where(EventOutboxRecord.tenant_id == tenant_id)
        )
        connection.execute(
            delete(ChangeEventRecord).where(ChangeEventRecord.tenant_id == tenant_id)
        )
        connection.execute(delete(ApprovalRecord).where(ApprovalRecord.tenant_id == tenant_id))
        connection.execute(
            delete(ProjectSnapshotRecord).where(ProjectSnapshotRecord.tenant_id == tenant_id)
        )
        connection.execute(delete(ProjectRecord).where(ProjectRecord.tenant_id == tenant_id))
        for table in immutable_tables:
            connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))
