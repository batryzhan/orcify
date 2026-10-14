"""Run a real HTTP Phase 2E scenario against the local API and configured databases."""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi.encoders import jsonable_encoder
from gamo_ca.fingerprints import fingerprint, requirement_fingerprint
from gamo_ca.fixtures import toy_graph
from gamo_ca.graph import Graph
from gamo_ca.models import AssetVersion, Requirement
from gamo_ca.planner import Plan
from neo4j import GraphDatabase
from pydantic import TypeAdapter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from services.api.app.artifact_schemas import (
    ArtifactCreateRequest,
    DependencyVersion,
    ProvenanceInput,
)
from services.api.app.models import ProjectRecord
from services.api.app.neo4j_projection import Neo4jGraphProjection
from services.api.app.projection_worker import reconcile_project


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        default="local-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
        help="unique project suffix; use a fixed value to reproduce on a fresh seeded database",
    )
    parser.add_argument(
        "--token-file", default=os.getenv("ORCIFY_DEMO_TOKEN_FILE", "var/demo-tokens.json")
    )
    parser.add_argument("--api-url", default=os.getenv("ORCIFY_API_URL", "http://127.0.0.1:8000"))
    args = parser.parse_args()

    token_data = json.loads(Path(args.token_file).read_text(encoding="utf-8"))
    tokens = token_data["tokens"]
    database_url = os.environ.get("DATABASE_URL")
    neo_uri = os.environ.get("NEO4J_URI")
    neo_user = os.environ.get("NEO4J_USER")
    neo_password = os.environ.get("NEO4J_PASSWORD")
    if not all((database_url, neo_uri, neo_user, neo_password)):
        parser.error("DATABASE_URL and NEO4J_URI/USER/PASSWORD must point to the local services")
    assert database_url and neo_uri and neo_user and neo_password

    tenant_id = "demo-tenant"
    producer_id = "demo-producer"
    project_id = f"demo-smoke-{args.run_id}"
    base_graph = toy_graph()
    raw_nodes = tuple(
        replace(node, tenant_id=tenant_id, project_id=project_id) for node in base_graph.nodes
    )
    req_hash = requirement_fingerprint(
        tuple(node for node in raw_nodes if isinstance(node, Requirement))
    )
    scoped_nodes = tuple(
        replace(node, requirement_fingerprint=req_hash) if isinstance(node, AssetVersion) else node
        for node in raw_nodes
    )
    graph = replace(
        base_graph,
        tenant_id=tenant_id,
        project_id=project_id,
        nodes=scoped_nodes,
        edges=tuple(
            replace(edge, tenant_id=tenant_id, project_id=project_id) for edge in base_graph.edges
        ),
    )
    headers = {
        "admin": {"Authorization": f"Bearer {tokens['admin']}"},
        "producer": {"Authorization": f"Bearer {tokens['producer']}"},
        "reviewer": {"Authorization": f"Bearer {tokens['reviewer']}"},
    }
    base_url = f"/api/v1/tenants/{tenant_id}/projects/{project_id}"

    with httpx.Client(base_url=args.api_url.rstrip("/"), timeout=20) as client:
        created = client.post(
            f"/api/v1/tenants/{tenant_id}/projects",
            headers=headers["admin"],
            json={"project_id": project_id, "initial_graph": jsonable_encoder(graph)},
        )
        _expect(created, 201, "create project")
        _expect(client.get(base_url, headers=headers["admin"]), 200, "retrieve project")
        graph_read = client.get(f"{base_url}/graph", headers=headers["producer"])
        _expect(graph_read, 200, "retrieve authoritative graph")

        # A cross-tenant path remains concealed, and a revoked bearer is rejected.
        cross_tenant = client.get(
            f"/api/v1/tenants/another-tenant/projects/{project_id}",
            headers=headers["admin"],
        )
        _expect(cross_tenant, 404, "cross-tenant denial")
        revoked = client.get(base_url, headers={"Authorization": f"Bearer {tokens['revoked']}"})
        _expect(revoked, 401, "revoked credential denial")

        note = graph.node("note")
        note_plan_request = _plan_request(
            event_id=f"smoke-plan-note-{args.run_id}",
            target_id=note.id,
            old_version=note.version,
            old_hash=note.content_hash,
            new_hash=fingerprint(f"synthetic planned note {args.run_id}"),
        )
        planned = client.post(
            f"{base_url}/plans", headers=headers["producer"], json=note_plan_request
        )
        _expect(planned, 200, "GAMO-CA plan")
        note_plan = planned.json()
        assert any(item["action"] == "KEEP" for item in note_plan["decisions"])

        asset = graph.node("copy")
        assert isinstance(asset, AssetVersion)
        artifact = ArtifactCreateRequest(
            artifact_version_id=f"smoke-artifact-v1-{args.run_id}",
            artifact_id=f"smoke-artifact-{args.run_id}",
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
            planner_decision=TypeAdapter(Plan).validate_python(note_plan),
            idempotency_key=f"smoke-artifact-key-{args.run_id}",
            provider_id="deterministic-mock",
            model_id="fixture-v1",
            provenance=(
                ProvenanceInput(
                    provenance_id=f"smoke-provenance-{args.run_id}",
                    source_kind="graph_node",
                    source_id=asset.inputs[0].source_id,
                    details={"label": "synthetic smoke fixture"},
                ),
            ),
        )
        artifact_payload = {
            "artifact": artifact.model_dump(mode="json"),
            "planning_event": note_plan_request,
        }
        artifact_created = client.post(
            f"{base_url}/artifacts", headers=headers["producer"], json=artifact_payload
        )
        _expect(artifact_created, 201, "create artifact version")
        artifact_id = artifact_created.json()["artifact"]["artifact_version_id"]
        artifact_url = f"{base_url}/artifacts/{artifact_id}"
        eligibility_url = f"{artifact_url}/eligibility"
        assert client.get(eligibility_url, headers=headers["producer"]).json()["eligible"] is False

        approval_common: dict[str, Any] = {
            "asset_version_id": asset.id,
            "asset_version": asset.version,
            "requirement_fingerprint": req_hash,
            "policy_version": asset.policy_version,
            "planning_event": note_plan_request,
        }
        submitted = {
            **approval_common,
            "approval_id": f"smoke-submitted-{args.run_id}",
            "decision": "SUBMITTED",
            "idempotency_key": f"smoke-submitted-key-{args.run_id}",
            "expected_revision": 0,
        }
        _expect(
            client.post(f"{base_url}/approvals", headers=headers["producer"], json=submitted),
            201,
            "submit exact artifact for human review",
        )
        approved = {
            **approval_common,
            "approval_id": f"smoke-approved-{args.run_id}",
            "decision": "APPROVED",
            "idempotency_key": f"smoke-approved-key-{args.run_id}",
            "expected_revision": 1,
            "supersedes_id": submitted["approval_id"],
        }
        approved_result = client.post(
            f"{base_url}/approvals", headers=headers["reviewer"], json=approved
        )
        _expect(approved_result, 201, "reviewer approval")
        assert approved_result.json()["approval"]["actor_id"] == "demo-reviewer"
        assert client.get(eligibility_url, headers=headers["reviewer"]).json()["eligible"] is True

        # Plan and apply an explicitly confirmed upstream requirement change.
        slogan = graph.node("slogan")
        assert isinstance(slogan, Requirement)
        proposed = replace(
            slogan,
            version=slogan.version + 1,
            content="Synthetic revised slogan",
            valid_from=graph.as_of + timedelta(seconds=1),
            confirmed_by=producer_id,
        )
        changed_graph = Graph(
            tenant_id,
            project_id,
            graph.as_of + timedelta(seconds=1),
            tuple(proposed if node.id == slogan.id else node for node in graph.nodes),
            graph.edges,
        )
        requirement_plan_request = _plan_request(
            event_id=f"smoke-plan-requirement-{args.run_id}",
            target_id=slogan.id,
            old_version=slogan.version,
            old_hash=slogan.content_hash,
            new_hash=proposed.content_hash,
        )
        requirement_plan = client.post(
            f"{base_url}/plans",
            headers=headers["producer"],
            json=requirement_plan_request,
        )
        _expect(requirement_plan, 200, "requirement-change impact plan")
        decisions = {
            item["node_id"]: item["action"] for item in requirement_plan.json()["decisions"]
        }
        assert decisions.get("copy") == "RECOMPUTE"
        assert decisions.get("storyboard") == "RECOMPUTE"

        graph_change_payload = {
            "event_id": f"smoke-graph-change-{args.run_id}",
            "expected_revision": 0,
            "expected_snapshot_hash": graph.snapshot_hash,
            "snapshot": jsonable_encoder(changed_graph),
            "idempotency_key": f"smoke-graph-key-{args.run_id}",
        }

        def retry_graph_change() -> httpx.Response:
            with httpx.Client(base_url=args.api_url.rstrip("/"), timeout=20) as retry_client:
                return retry_client.post(
                    f"{base_url}/graph-changes",
                    headers=headers["producer"],
                    json=graph_change_payload,
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            retry_results = tuple(executor.map(lambda _: retry_graph_change(), range(2)))
        for response in retry_results:
            _expect(response, 200, "concurrent idempotent graph-change retry")
        assert {response.json()["replayed"] for response in retry_results} == {False, True}
        current_graph = client.get(f"{base_url}/graph", headers=headers["producer"])
        _expect(current_graph, 200, "re-read changed graph")
        assert current_graph.json()["snapshot_hash"] == changed_graph.snapshot_hash
        stale_eligibility = client.get(eligibility_url, headers=headers["producer"])
        _expect(stale_eligibility, 200, "current-state eligibility check")
        assert stale_eligibility.json()["eligible"] is False
        assert "snapshot" in " ".join(stale_eligibility.json()["reasons"]).lower()

    # Repair a deliberately missing projection entity from the authoritative snapshot.
    engine = create_engine(database_url, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    driver = GraphDatabase.driver(neo_uri, auth=(neo_user, neo_password))
    projection = Neo4jGraphProjection(driver)
    try:
        with Session(engine) as session:
            project = session.get(ProjectRecord, (tenant_id, project_id))
            if project is None:
                raise RuntimeError("authoritative project disappeared before reconciliation")
            authority_before_rebuild = (
                project.revision,
                project.current_graph_hash,
                project.current_snapshot_hash,
            )
        with driver.session(database="neo4j") as neo_session:
            neo_session.run(
                "MATCH (n:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id, "
                "node_id: 'note'}) DETACH DELETE n",
                tenant_id=tenant_id,
                project_id=project_id,
            ).consume()
        rebuilt = reconcile_project(sessions, projection, tenant_id, project_id)
        if rebuilt.error is not None:
            raise RuntimeError(f"Neo4j reconciliation failed: {rebuilt.error}")
        if not rebuilt.rebuilt:
            # A running worker may already have projected this snapshot. Verify consistency.
            if not rebuilt.consistent:
                raise RuntimeError("Neo4j did not rebuild or reconcile to the current snapshot")
        with Session(engine) as session:
            project = session.get(ProjectRecord, (tenant_id, project_id))
            if project is None:
                raise RuntimeError("authoritative project disappeared")
            authority_after_rebuild = (
                project.revision,
                project.current_graph_hash,
                project.current_snapshot_hash,
            )
        if authority_after_rebuild != authority_before_rebuild:
            raise RuntimeError("projection rebuild changed or disagreed with PostgreSQL authority")
    finally:
        driver.close()
        engine.dispose()

    print(
        json.dumps(
            {
                "status": "PASS",
                "data_label": "SYNTHETIC",
                "execution_label": "DETERMINISTIC_MOCK; NO PROVIDER INVOKED",
                "project_id": project_id,
                "approval_before_change": "EXACT_VERSION_APPROVED_BY_REVIEWER",
                "eligibility_after_change": "BLOCKED_AS_STALE",
                "duplicate_http_retries": "ONE_WRITE_ONE_REPLAY",
                "projection_rebuild": "REBUILT_OR_VERIFIED_FROM_POSTGRESQL",
                "postgres_revision_after_projection": authority_after_rebuild[0],
                "external_publication_invoked": False,
            },
            indent=2,
        )
    )


def _plan_request(
    *, event_id: str, target_id: str, old_version: int, old_hash: str, new_hash: str
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "target_id": target_id,
        "source_id": "evidence",
        "change_type": "CONTENT_REVISION",
        "old_version": old_version,
        "new_version": old_version + 1,
        "old_hash": old_hash,
        "new_hash": new_hash,
        "changed_fields": ["content"],
    }


def _expect(response: httpx.Response, status: int, operation: str) -> None:
    if response.status_code != status:
        raise RuntimeError(
            f"{operation} expected HTTP {status}, got {response.status_code}: {response.text}"
        )


if __name__ == "__main__":
    main()
