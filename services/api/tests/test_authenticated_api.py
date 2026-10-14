from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from gamo_ca.events import EventReplayState
from gamo_ca.fingerprints import requirement_fingerprint
from gamo_ca.fixtures import change_event, toy_graph
from gamo_ca.models import ApprovalDecision, AssetVersion
from gamo_ca.planner import Policy, plan_change
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from services.api.app.artifact_schemas import (
    ArtifactCreateRequest,
    DependencyVersion,
    ExecutionRunCreateRequest,
    ProvenanceInput,
)
from services.api.app.event_store import create_project
from services.api.app.http import create_app
from services.api.app.models import (
    ApiCredentialRecord,
    Base,
    TenantMembershipRecord,
)


@pytest.fixture
def api_fixture():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    graph = toy_graph()
    with Session(engine) as session:
        create_project(
            session,
            graph.tenant_id,
            graph.project_id,
            EventReplayState.from_graph(graph),
            initial_graph=graph,
        )
        session.add(
            TenantMembershipRecord(
                tenant_id=graph.tenant_id, actor_id="actor-reviewer", role="reviewer"
            )
        )
        session.add(
            TenantMembershipRecord(
                tenant_id=graph.tenant_id, actor_id="actor-reader", role="researcher"
            )
        )
        session.add(
            TenantMembershipRecord(
                tenant_id=graph.tenant_id, actor_id="actor-producer", role="producer"
            )
        )
        session.add(
            TenantMembershipRecord(
                tenant_id=graph.tenant_id, actor_id="actor-admin", role="tenant_admin"
            )
        )
        session.add(
            TenantMembershipRecord(
                tenant_id=graph.tenant_id,
                actor_id="actor-revoked",
                role="producer",
                revoked_at=datetime.now(UTC),
            )
        )
        for actor, token, expires in (
            (
                "actor-reviewer",
                "orc_review-token-secret-value-000000000000",
                datetime.now(UTC) + timedelta(days=1),
            ),
            (
                "actor-reader",
                "orc_reader-token-secret-value-000000000000",
                datetime.now(UTC) + timedelta(days=1),
            ),
            (
                "actor-producer",
                "orc_producer-token-secret-value-000000000000",
                datetime.now(UTC) + timedelta(days=1),
            ),
            (
                "actor-admin",
                "orc_admin-token-secret-value-000000000000",
                datetime.now(UTC) + timedelta(days=1),
            ),
            (
                "actor-revoked",
                "orc_revoked-token-secret-value-000000000000",
                datetime.now(UTC) + timedelta(days=1),
            ),
            (
                "actor-reviewer",
                "orc_expired-token-secret-value-000000000000",
                datetime.now(UTC) - timedelta(seconds=1),
            ),
        ):
            session.add(
                ApiCredentialRecord(
                    credential_id=actor + token[4:10],
                    actor_id=actor,
                    token_digest=sha256(token.encode()).hexdigest(),
                    expires_at=expires,
                )
            )
        session.commit()
    app = create_app(engine)
    return TestClient(app), engine, graph


def test_openapi_exposes_versioned_typed_api_and_bearer_auth(api_fixture) -> None:
    client, _, _ = api_fixture
    schema = client.get("/openapi.json").json()
    assert "/api/v1/tenants/{tenant_id}/projects/{project_id}/graph" in schema["paths"]
    assert "HTTPBearer" in schema["components"]["securitySchemes"]
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_tenant_admin_can_create_project_with_validated_graph_scope(api_fixture) -> None:
    client, _, graph = api_fixture
    project_id = "api-created-project"
    initial_graph = replace(
        graph,
        project_id=project_id,
        nodes=tuple(replace(node, project_id=project_id) for node in graph.nodes),
        edges=tuple(replace(edge, project_id=project_id) for edge in graph.edges),
    )
    response = client.post(
        f"/api/v1/tenants/{graph.tenant_id}/projects",
        headers={"Authorization": "Bearer orc_admin-token-secret-value-000000000000"},
        json={"project_id": project_id, "initial_graph": jsonable_encoder(initial_graph)},
    )
    assert response.status_code == 201, response.text
    assert response.json()["current_graph_hash"] == initial_graph.snapshot_hash


def test_missing_expired_and_invalid_credentials_are_401(api_fixture) -> None:
    client, _, graph = api_fixture
    url = f"/api/v1/tenants/{graph.tenant_id}/projects/{graph.project_id}"
    assert client.get(url).status_code == 401
    assert (
        client.get(
            url, headers={"Authorization": "Bearer orc_expired-token-secret-value-000000000000"}
        ).status_code
        == 401
    )
    assert (
        client.get(
            url, headers={"Authorization": "Bearer forged-token-secret-value-000000000000"}
        ).status_code
        == 401
    )


def test_cross_tenant_and_revoked_membership_are_hidden_as_404(api_fixture) -> None:
    client, _, graph = api_fixture
    other_tenant_url = f"/api/v1/tenants/other-tenant/projects/{graph.project_id}"
    valid = {"Authorization": "Bearer orc_review-token-secret-value-000000000000"}
    assert client.get(other_tenant_url, headers=valid).status_code == 404
    revoked = {"Authorization": "Bearer orc_revoked-token-secret-value-000000000000"}
    url = f"/api/v1/tenants/{graph.tenant_id}/projects/{graph.project_id}"
    assert client.get(url, headers=revoked).status_code == 404


def test_role_denial_and_client_identity_claims_cannot_forge_reviewer(api_fixture) -> None:
    client, _, graph = api_fixture
    headers = {"Authorization": "Bearer orc_reader-token-secret-value-000000000000"}
    # Producer/editor/reviewer roles may submit graph changes; researcher is read-only.
    response = client.post(
        f"/api/v1/tenants/{graph.tenant_id}/projects/{graph.project_id}/graph-changes",
        headers=headers,
        json={
            "event_id": "event",
            "expected_revision": 0,
            "expected_snapshot_hash": graph.snapshot_hash,
            "snapshot": jsonable_encoder(graph),
            "idempotency_key": "idem",
        },
    )
    assert response.status_code == 403

    # Strict schema rejects forged actor/scope assertions before domain transitions.
    body = {
        "approval_id": "a1",
        "asset_version_id": "asset",
        "asset_version": 1,
        "requirement_fingerprint": "0" * 64,
        "decision": "APPROVED",
        "policy_version": "v1",
        "idempotency_key": "approval-key",
        "expected_revision": 0,
        "actor_id": "victim",
        "tenant_id": graph.tenant_id,
        "project_id": graph.project_id,
        "planning_event": {
            "event_id": "e",
            "target_id": "t",
            "source_id": "s",
            "change_type": "edit",
            "old_version": 1,
            "new_version": 2,
            "old_hash": "0" * 64,
            "new_hash": "1" * 64,
            "changed_fields": ["content"],
        },
    }
    response = client.post(
        f"/api/v1/tenants/{graph.tenant_id}/projects/{graph.project_id}/approvals",
        headers={"Authorization": "Bearer orc_review-token-secret-value-000000000000"},
        json=body,
    )
    assert response.status_code == 422


def test_authenticated_reviewer_can_read_authoritative_graph(api_fixture) -> None:
    client, _, graph = api_fixture
    response = client.get(
        f"/api/v1/tenants/{graph.tenant_id}/projects/{graph.project_id}/graph",
        headers={"Authorization": "Bearer orc_review-token-secret-value-000000000000"},
    )
    assert response.status_code == 200
    assert response.json()["snapshot_hash"] == graph.snapshot_hash
    assert response.json()["revision"] == 0


def test_producer_graph_change_is_idempotent_and_uses_verified_actor(api_fixture) -> None:
    from datetime import timedelta

    client, _, graph = api_fixture
    instant = graph.as_of + timedelta(seconds=1)
    nodes = tuple(
        replace(node, version=node.version + 1, content="Updated note", valid_from=instant)
        if node.id == "note"
        else node
        for node in graph.nodes
    )
    updated = type(graph)(graph.tenant_id, graph.project_id, instant, nodes, graph.edges)
    url = f"/api/v1/tenants/{graph.tenant_id}/projects/{graph.project_id}/graph-changes"
    headers = {"Authorization": "Bearer orc_producer-token-secret-value-000000000000"}
    body = {
        "event_id": "api-event-1",
        "expected_revision": 0,
        "expected_snapshot_hash": graph.snapshot_hash,
        "snapshot": jsonable_encoder(updated),
        "idempotency_key": "api-key-1",
    }
    first = client.post(url, headers=headers, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == 1
    assert first.json()["replayed"] is False
    replay = client.post(url, headers=headers, json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    current = client.get(
        f"/api/v1/tenants/{graph.tenant_id}/projects/{graph.project_id}/graph",
        headers=headers,
    )
    assert current.status_code == 200
    assert current.json()["snapshot_hash"] == updated.snapshot_hash


def test_artifact_api_recomputes_plan_and_returns_typed_authoritative_record(api_fixture) -> None:
    client, _, graph = api_fixture
    asset = graph.node("copy")
    assert isinstance(asset, AssetVersion)
    planning_event = replace(
        change_event("note", graph), actor_id="actor-producer", created_at=graph.as_of
    )
    plan = plan_change(graph, planning_event, Policy())
    command = ArtifactCreateRequest(
        artifact_version_id="api-artifact-v1",
        artifact_id="api-artifact",
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
        planner_decision=plan,
        idempotency_key="api-artifact-key",
        provenance=(
            ProvenanceInput(
                provenance_id="api-artifact-provenance",
                source_kind="graph_node",
                source_id=asset.inputs[0].source_id,
                details={"reason": "captured input"},
            ),
        ),
    )
    body = {
        "artifact": command.model_dump(mode="json"),
        "planning_event": {
            "event_id": planning_event.id,
            "target_id": planning_event.target_id,
            "source_id": planning_event.source_id,
            "change_type": planning_event.change_type,
            "old_version": planning_event.old_version,
            "new_version": planning_event.new_version,
            "old_hash": planning_event.old_hash,
            "new_hash": planning_event.new_hash,
            "changed_fields": list(planning_event.changed_fields),
        },
    }
    response = client.post(
        f"/api/v1/tenants/{graph.tenant_id}/projects/{graph.project_id}/artifacts",
        headers={"Authorization": "Bearer orc_producer-token-secret-value-000000000000"},
        json=body,
    )
    assert response.status_code == 201, response.text
    assert (
        response.json()["artifact"]["content_hash"]
        == sha256(asset.content.encode("utf-8")).hexdigest()
    )
    assert (
        client.get(
            f"/api/v1/tenants/{graph.tenant_id}/projects/{graph.project_id}/artifacts/api-artifact-v1",
            headers={"Authorization": "Bearer orc_producer-token-secret-value-000000000000"},
        ).status_code
        == 200
    )


def test_execution_api_persists_and_reads_run_history(api_fixture) -> None:
    client, _, graph = api_fixture
    event = replace(change_event("note", graph), actor_id="actor-producer", created_at=graph.as_of)
    plan = plan_change(graph, event, Policy())
    command = ExecutionRunCreateRequest(
        run_id="api-run-1",
        expected_project_revision=0,
        graph_revision=0,
        graph_snapshot_hash=graph.snapshot_hash,
        planner_decision=plan,
        idempotency_key="api-run-key",
    )
    body = {
        "run": command.model_dump(mode="json"),
        "planning_event": {
            "event_id": event.id,
            "target_id": event.target_id,
            "source_id": event.source_id,
            "change_type": event.change_type,
            "old_version": event.old_version,
            "new_version": event.new_version,
            "old_hash": event.old_hash,
            "new_hash": event.new_hash,
            "changed_fields": list(event.changed_fields),
        },
    }
    headers = {"Authorization": "Bearer orc_producer-token-secret-value-000000000000"}
    base = f"/api/v1/tenants/{graph.tenant_id}/projects/{graph.project_id}/runs"
    response = client.post(base, headers=headers, json=body)
    assert response.status_code == 201, response.text
    history = client.get(f"{base}/api-run-1", headers=headers)
    assert history.status_code == 200, history.text
    assert history.json()["run"]["status"] == "pending"
    assert history.json()["attempts"] == []


def test_approval_transitions_use_membership_actor_and_exact_snapshots(api_fixture) -> None:
    client, _, graph = api_fixture
    asset = graph.node("copy")
    assert isinstance(asset, AssetVersion)
    event = change_event("note", graph)
    planning_event = {
        "event_id": event.id,
        "target_id": event.target_id,
        "source_id": event.source_id,
        "change_type": event.change_type,
        "old_version": event.old_version,
        "new_version": event.new_version,
        "old_hash": event.old_hash,
        "new_hash": event.new_hash,
        "changed_fields": list(event.changed_fields),
    }
    base = f"/api/v1/tenants/{graph.tenant_id}/projects/{graph.project_id}/approvals"
    common = {
        "asset_version_id": asset.id,
        "asset_version": asset.version,
        "requirement_fingerprint": requirement_fingerprint(graph.requirements),
        "policy_version": asset.policy_version,
        "planning_event": planning_event,
    }
    submitted = {
        **common,
        "approval_id": "api-approval-submit",
        "decision": ApprovalDecision.SUBMITTED.value,
        "idempotency_key": "api-approval-submit-key",
        "expected_revision": 0,
    }
    response = client.post(
        base,
        headers={"Authorization": "Bearer orc_producer-token-secret-value-000000000000"},
        json=submitted,
    )
    assert response.status_code == 201, response.text
    assert response.json()["approval"]["actor_id"] == "actor-producer"
    replay = client.post(
        base,
        headers={"Authorization": "Bearer orc_producer-token-secret-value-000000000000"},
        json=submitted,
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["replayed"] is True

    approved = {
        **common,
        "approval_id": "api-approval-approved",
        "decision": ApprovalDecision.APPROVED.value,
        "idempotency_key": "api-approval-approved-key",
        "expected_revision": 1,
        "supersedes_id": "api-approval-submit",
    }
    response = client.post(
        base,
        headers={"Authorization": "Bearer orc_review-token-secret-value-000000000000"},
        json=approved,
    )
    assert response.status_code == 201, response.text
    assert response.json()["approval"]["actor_id"] == "actor-reviewer"
    assert response.json()["approval"]["decision"] == ApprovalDecision.APPROVED.value
