"""Authenticated API, PostgreSQL and Neo4j end-to-end checks (opt-in live services)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from gamo_ca.fingerprints import fingerprint, requirement_fingerprint
from gamo_ca.fixtures import toy_graph
from gamo_ca.graph import Graph
from gamo_ca.models import ApprovalDecision, AssetVersion, Requirement
from gamo_ca.planner import Plan
from neo4j import GraphDatabase
from pydantic import TypeAdapter
from sqlalchemy import Engine, create_engine, delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from services.api.app.artifact_schemas import (
    ArtifactCreateRequest,
    DependencyVersion,
    ProvenanceInput,
)
from services.api.app.event_store import load_current_graph
from services.api.app.http import create_app
from services.api.app.models import (
    ApiCredentialRecord,
    ApprovalRecord,
    ArtifactProvenanceRecord,
    ArtifactVersionRecord,
    ChangeEventRecord,
    EventOutboxRecord,
    ExecutionAttemptRecord,
    ExecutionEventRecord,
    ExecutionRunRecord,
    ProjectionCheckpointRecord,
    ProjectRecord,
    ProjectSnapshotRecord,
    TenantMembershipRecord,
)
from services.api.app.neo4j_projection import Neo4jGraphProjection
from services.api.app.projection_worker import process_next, reconcile_project

DATABASE_URL = os.getenv("ORCIFY_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
NEO4J_URI = os.getenv("ORCIFY_TEST_NEO4J_URI") or os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("ORCIFY_TEST_NEO4J_USER") or os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("ORCIFY_TEST_NEO4J_PASSWORD") or os.getenv("NEO4J_PASSWORD")
pytestmark = pytest.mark.skipif(
    not all((DATABASE_URL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)),
    reason="live Phase 2E scenario requires PostgreSQL and Neo4j connection settings",
)


def test_live_authenticated_http_approval_invalidation_and_projection_rebuild() -> None:
    assert DATABASE_URL and NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD
    engine = create_engine(DATABASE_URL, pool_size=6, max_overflow=0, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    projection = Neo4jGraphProjection(driver)
    projection.ensure_schema()

    suffix = uuid4().hex
    tenant_id, project_id = f"phase2e-tenant-{suffix}", f"phase2e-project-{suffix}"
    actors = {
        "admin": f"phase2e-admin-{suffix}",
        "producer": f"phase2e-producer-{suffix}",
        "reviewer": f"phase2e-reviewer-{suffix}",
        "revoked": f"phase2e-revoked-{suffix}",
        "credential_revoked": f"phase2e-credential-revoked-{suffix}",
    }
    tokens = {name: f"orc_{uuid4().hex}{uuid4().hex}" for name in actors}
    credentials = {name: f"phase2e-cred-{suffix}-{name}" for name in actors}
    now = datetime.now(UTC)
    roles = {
        "admin": "tenant_admin",
        "producer": "producer",
        "reviewer": "reviewer",
        "revoked": "producer",
        "credential_revoked": "producer",
    }
    with Session(engine) as session, session.begin():
        for name, actor_id in actors.items():
            session.add(
                TenantMembershipRecord(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    role=roles[name],
                    revoked_at=now if name == "revoked" else None,
                )
            )
            session.add(
                ApiCredentialRecord(
                    credential_id=credentials[name],
                    actor_id=actor_id,
                    token_digest=sha256(tokens[name].encode()).hexdigest(),
                    expires_at=now + timedelta(hours=1),
                    revoked_at=now if name == "credential_revoked" else None,
                )
            )

    base = toy_graph()
    nodes = tuple(replace(node, tenant_id=tenant_id, project_id=project_id) for node in base.nodes)
    req_hash = requirement_fingerprint(
        tuple(node for node in nodes if isinstance(node, Requirement))
    )
    nodes = tuple(
        replace(node, requirement_fingerprint=req_hash) if isinstance(node, AssetVersion) else node
        for node in nodes
    )
    graph = replace(
        base,
        tenant_id=tenant_id,
        project_id=project_id,
        nodes=nodes,
        edges=tuple(
            replace(edge, tenant_id=tenant_id, project_id=project_id) for edge in base.edges
        ),
    )
    client = TestClient(create_app(engine))
    admin = {"Authorization": f"Bearer {tokens['admin']}"}
    producer = {"Authorization": f"Bearer {tokens['producer']}"}
    reviewer = {"Authorization": f"Bearer {tokens['reviewer']}"}
    project_url = f"/api/v1/tenants/{tenant_id}/projects/{project_id}"
    try:
        # Server-provisioned credentials authorize project creation and retrieval.
        created = client.post(
            f"/api/v1/tenants/{tenant_id}/projects",
            headers=admin,
            json={"project_id": project_id, "initial_graph": jsonable_encoder(graph)},
        )
        assert created.status_code == 201, created.text
        assert client.get(project_url, headers=admin).status_code == 200
        assert (
            client.get(
                f"/api/v1/tenants/foreign-{tenant_id}/projects/{project_id}", headers=admin
            ).status_code
            == 404
        )
        revoked_response = client.get(
            project_url, headers={"Authorization": f"Bearer {tokens['revoked']}"}
        )
        assert revoked_response.status_code == 404
        revoked_credential = client.get(
            project_url,
            headers={"Authorization": f"Bearer {tokens['credential_revoked']}"},
        )
        assert revoked_credential.status_code == 401

        initial = client.get(f"{project_url}/graph", headers=producer).json()
        assert initial["snapshot_hash"] == graph.snapshot_hash

        # Planning is a preview; a KEEP action does not create an approval.
        note = graph.node("note")
        plan_body = _planning_request(
            event_id=f"phase2e-plan-note-{suffix}",
            target_id=note.id,
            source_id="evidence",
            old_version=note.version,
            old_hash=note.content_hash,
            new_hash=fingerprint(f"planned note {suffix}"),
        )
        plan_response = client.post(f"{project_url}/plans", headers=producer, json=plan_body)
        assert plan_response.status_code == 200, plan_response.text
        assert any(item["action"] == "KEEP" for item in plan_response.json()["decisions"])

        # Create the exact graph-bound sample artifact, then explicitly submit and approve it.
        asset = graph.node("copy")
        assert isinstance(asset, AssetVersion)
        artifact_command = ArtifactCreateRequest(
            artifact_version_id=f"artifact-v1-{suffix}",
            artifact_id=f"artifact-{suffix}",
            node_id=asset.id,
            node_version=asset.version,
            expected_project_revision=0,
            graph_revision=0,
            graph_snapshot_hash=graph.snapshot_hash,
            dependencies=tuple(
                DependencyVersion(
                    node_id=item.source_id,
                    node_version=item.version,
                    content_hash=item.content_hash,
                )
                for item in asset.inputs
            ),
            content=asset.content,
            planner_decision=TypeAdapter(Plan).validate_python(plan_response.json()),
            idempotency_key=f"artifact-key-{suffix}",
            provenance=(
                ProvenanceInput(
                    provenance_id=f"provenance-{suffix}",
                    source_kind="graph_node",
                    source_id=asset.inputs[0].source_id,
                    details={"label": "synthetic demo artifact"},
                ),
            ),
        )
        artifact_body = {
            "artifact": artifact_command.model_dump(mode="json"),
            "planning_event": plan_body,
        }
        artifact_response = client.post(
            f"{project_url}/artifacts", headers=producer, json=artifact_body
        )
        assert artifact_response.status_code == 201, artifact_response.text
        artifact_id = artifact_response.json()["artifact"]["artifact_version_id"]
        eligibility_url = f"{project_url}/artifacts/{artifact_id}/eligibility"
        assert client.get(eligibility_url, headers=producer).json()["eligible"] is False

        common_approval = {
            "asset_version_id": asset.id,
            "asset_version": asset.version,
            "requirement_fingerprint": req_hash,
            "policy_version": asset.policy_version,
            "planning_event": plan_body,
        }
        submitted = {
            **common_approval,
            "approval_id": f"approval-submit-{suffix}",
            "decision": ApprovalDecision.SUBMITTED.value,
            "idempotency_key": f"approval-submit-key-{suffix}",
            "expected_revision": 0,
        }
        approval_url = f"{project_url}/approvals"
        submit_result = client.post(approval_url, headers=producer, json=submitted)
        assert submit_result.status_code == 201, submit_result.text
        approved = {
            **common_approval,
            "approval_id": f"approval-approved-{suffix}",
            "decision": ApprovalDecision.APPROVED.value,
            "idempotency_key": f"approval-approved-key-{suffix}",
            "expected_revision": 1,
            "supersedes_id": submitted["approval_id"],
        }
        approve_result = client.post(approval_url, headers=reviewer, json=approved)
        assert approve_result.status_code == 201, approve_result.text
        assert approve_result.json()["approval"]["actor_id"] == actors["reviewer"]
        assert client.get(eligibility_url, headers=reviewer).json()["eligible"] is True

        # Preview a confirmed upstream requirement change and verify conservative recompute.
        slogan = graph.node("slogan")
        assert isinstance(slogan, Requirement)
        proposed = replace(
            slogan,
            version=slogan.version + 1,
            content="Synthetic revised slogan",
            valid_from=graph.as_of + timedelta(seconds=1),
            confirmed_by=actors["producer"],
        )
        changed_nodes = tuple(proposed if item.id == slogan.id else item for item in graph.nodes)
        changed_graph = Graph(
            tenant_id,
            project_id,
            graph.as_of + timedelta(seconds=1),
            changed_nodes,
            graph.edges,
        )
        requirement_plan_request = _planning_request(
            event_id=f"phase2e-plan-requirement-{suffix}",
            target_id=slogan.id,
            source_id="evidence",
            old_version=slogan.version,
            old_hash=slogan.content_hash,
            new_hash=proposed.content_hash,
        )
        requirement_plan = client.post(
            f"{project_url}/plans", headers=producer, json=requirement_plan_request
        )
        assert requirement_plan.status_code == 200, requirement_plan.text
        actions = {item["node_id"]: item["action"] for item in requirement_plan.json()["decisions"]}
        assert actions.get("copy") == "RECOMPUTE"
        assert actions.get("storyboard") == "RECOMPUTE"

        graph_change = {
            "event_id": f"phase2e-graph-event-{suffix}",
            "expected_revision": 0,
            "expected_snapshot_hash": graph.snapshot_hash,
            "snapshot": jsonable_encoder(changed_graph),
            "idempotency_key": f"phase2e-graph-key-{suffix}",
        }
        graph_change_url = f"{project_url}/graph-changes"

        def submit_graph_change() -> Any:
            return client.post(graph_change_url, headers=producer, json=graph_change)

        with ThreadPoolExecutor(max_workers=2) as executor:
            first, second = tuple(executor.map(lambda _: submit_graph_change(), range(2)))
        assert first.status_code == second.status_code == 200, (first.text, second.text)
        assert {first.json()["replayed"], second.json()["replayed"]} == {False, True}
        current = client.get(f"{project_url}/graph", headers=producer).json()
        assert current["revision"] == 1
        assert current["snapshot_hash"] == changed_graph.snapshot_hash
        stale = client.get(eligibility_url, headers=producer)
        assert stale.status_code == 200
        assert stale.json()["eligible"] is False
        assert "snapshot" in " ".join(stale.json()["reasons"]).lower()
        with Session(engine) as session:
            approved_record = session.scalar(
                select(ApprovalRecord).where(
                    ApprovalRecord.tenant_id == tenant_id,
                    ApprovalRecord.project_id == project_id,
                    ApprovalRecord.approval_id == approved["approval_id"],
                )
            )
            assert approved_record is not None
            assert approved_record.decision == ApprovalDecision.APPROVED.value
            assert approved_record.requirement_fingerprint == req_hash

        # Consume committed outbox rows, then force reconciliation rebuild and prove PG authority
        # did not move while Neo4j was repaired from the PostgreSQL snapshot.
        delivered = process_next(sessions, projection)
        assert delivered.succeeded and delivered.source_revision == 1, delivered
        with Session(engine) as session:
            project = session.get(ProjectRecord, (tenant_id, project_id))
            assert project is not None
            authoritative = (
                project.revision,
                project.current_graph_hash,
                project.current_snapshot_hash,
            )
            authoritative_graph = load_current_graph(session, tenant_id, project_id)
            assert authoritative_graph.snapshot_hash == changed_graph.snapshot_hash
        with driver.session(database="neo4j") as neo_session:
            neo_session.run(
                "MATCH (n:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id, "
                "node_id: 'note'}) DETACH DELETE n",
                tenant_id=tenant_id,
                project_id=project_id,
            ).consume()
        rebuilt = reconcile_project(sessions, projection, tenant_id, project_id)
        assert rebuilt.rebuilt and not rebuilt.consistent
        projected = projection.inspect(tenant_id, project_id)
        assert projected is not None and projected.graph_hash == changed_graph.snapshot_hash
        with Session(engine) as session:
            project = session.get(ProjectRecord, (tenant_id, project_id))
            assert project is not None
            assert (
                project.revision,
                project.current_graph_hash,
                project.current_snapshot_hash,
            ) == authoritative

        # The API has no external publication route; only authoritative eligibility is exposed.
        assert not any(
            "publish" in path.lower() for path in client.get("/openapi.json").json()["paths"]
        )
    finally:
        _cleanup_scope(engine, tenant_id)
        with driver.session(database="neo4j") as neo_session:
            neo_session.run(
                "MATCH (n:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id}) "
                "DETACH DELETE n",
                tenant_id=tenant_id,
                project_id=project_id,
            ).consume()
            neo_session.run(
                "MATCH (p:OrcifyProjection {tenant_id: $tenant_id, project_id: $project_id}) "
                "DELETE p",
                tenant_id=tenant_id,
                project_id=project_id,
            ).consume()
        driver.close()
        engine.dispose()


def _planning_request(
    *, event_id: str, target_id: str, source_id: str, old_version: int, old_hash: str, new_hash: str
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "target_id": target_id,
        "source_id": source_id,
        "change_type": "CONTENT_REVISION",
        "old_version": old_version,
        "new_version": old_version + 1,
        "old_hash": old_hash,
        "new_hash": new_hash,
        "changed_fields": ["content"],
    }


def _cleanup_scope(engine: Engine, tenant_id: str) -> None:
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
    with engine.begin() as connection:
        for table in immutable_tables:
            connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
        for model in (
            ArtifactProvenanceRecord,
            ExecutionEventRecord,
            ExecutionAttemptRecord,
            ExecutionRunRecord,
            ArtifactVersionRecord,
            EventOutboxRecord,
            ChangeEventRecord,
            ApprovalRecord,
            ProjectSnapshotRecord,
            ProjectionCheckpointRecord,
        ):
            connection.execute(delete(model).where(model.tenant_id == tenant_id))
        actor_ids = select(TenantMembershipRecord.actor_id).where(
            TenantMembershipRecord.tenant_id == tenant_id
        )
        connection.execute(
            delete(ApiCredentialRecord).where(ApiCredentialRecord.actor_id.in_(actor_ids))
        )
        connection.execute(
            delete(TenantMembershipRecord).where(TenantMembershipRecord.tenant_id == tenant_id)
        )
        connection.execute(delete(ProjectRecord).where(ProjectRecord.tenant_id == tenant_id))
        for table in immutable_tables:
            connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))
