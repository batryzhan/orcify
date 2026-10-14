"""Provision deterministic synthetic API demo data and short-lived operator tokens."""

from __future__ import annotations

import json
import os
import secrets
import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from gamo_ca.events import EventReplayState
from gamo_ca.fixtures import change_event, toy_graph
from gamo_ca.models import AssetVersion
from gamo_ca.planner import Policy, plan_change
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from services.api.app.artifact_schemas import (
    ArtifactCreateRequest,
    DependencyVersion,
    ProvenanceInput,
)
from services.api.app.artifact_store import ArtifactConflict, create_artifact_version
from services.api.app.event_store import EventConflict, create_project, load_current_graph
from services.api.app.models import (
    ApiCredentialRecord,
    ProjectRecord,
    TenantMembershipRecord,
)

DEMO_IDENTITIES = {
    "admin": ("demo-admin", "tenant_admin"),
    "producer": ("demo-producer", "producer"),
    "reviewer": ("demo-reviewer", "reviewer"),
    "revoked": ("demo-revoked-credential", "producer"),
}


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "DATABASE_URL must point to the migrated authoritative PostgreSQL database"
        )
    token_path = Path(os.environ.get("ORCIFY_DEMO_TOKEN_FILE", "var/demo-tokens.json"))
    token_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, pool_pre_ping=True)
    tokens: dict[str, str] = {}
    now = datetime.now(UTC)
    try:
        with Session(engine) as session, session.begin():
            for name, (actor_id, role) in DEMO_IDENTITIES.items():
                membership = session.get(TenantMembershipRecord, ("demo-tenant", actor_id))
                if membership is None:
                    session.add(
                        TenantMembershipRecord(
                            tenant_id="demo-tenant", actor_id=actor_id, role=role
                        )
                    )
                elif membership.role != role or membership.revoked_at is not None:
                    raise EventConflict(
                        f"demo membership {actor_id} exists with a different or revoked role"
                    )
                session.execute(
                    update(ApiCredentialRecord)
                    .where(ApiCredentialRecord.actor_id == actor_id)
                    .where(ApiCredentialRecord.credential_id.like(f"demo-{name}-%"))
                    .where(ApiCredentialRecord.revoked_at.is_(None))
                    .values(revoked_at=now)
                )
                token = f"orc_{secrets.token_urlsafe(40)}"
                tokens[name] = token
                session.add(
                    ApiCredentialRecord(
                        credential_id=f"demo-{name}-{secrets.token_hex(12)}",
                        actor_id=actor_id,
                        token_digest=sha256(token.encode("utf-8")).hexdigest(),
                        expires_at=now + timedelta(days=2),
                        revoked_at=now if name == "revoked" else None,
                    )
                )

        graph = toy_graph()
        with Session(engine) as session:
            existing = session.get(ProjectRecord, (graph.tenant_id, graph.project_id))
            if existing is not None:
                current = load_current_graph(session, graph.tenant_id, graph.project_id)
                if current.snapshot_hash != graph.snapshot_hash:
                    raise EventConflict(
                        "demo-project already advanced; retain it as history and choose a fresh "
                        "database or project ID for a clean seeded run"
                    )
        if existing is None:
            with Session(engine) as session:
                create_project(
                    session,
                    graph.tenant_id,
                    graph.project_id,
                    EventReplayState.from_graph(graph),
                    initial_graph=graph,
                )

        artifact = graph.node("copy")
        if not isinstance(artifact, AssetVersion):
            raise TypeError("the deterministic demo graph must contain the copy asset")
        event = change_event("note", graph)
        event = replace(event, actor_id="demo-producer")
        plan = plan_change(graph, event, Policy())
        command = ArtifactCreateRequest(
            artifact_version_id="demo-copy-v1",
            artifact_id="demo-copy",
            node_id=artifact.id,
            node_version=artifact.version,
            expected_project_revision=0,
            graph_revision=0,
            graph_snapshot_hash=graph.snapshot_hash,
            dependencies=tuple(
                DependencyVersion(
                    node_id=item.source_id,
                    node_version=item.version,
                    content_hash=item.content_hash,
                )
                for item in artifact.inputs
            ),
            content=artifact.content,
            planner_decision=plan,
            idempotency_key="demo-copy-v1-seed",
            provider_id="deterministic-mock",
            model_id="fixture-v1",
            provenance=(
                ProvenanceInput(
                    provenance_id="demo-copy-v1-source",
                    source_kind="graph_node",
                    source_id=artifact.inputs[0].source_id,
                    details={"label": "synthetic seed fixture; not generated by a live model"},
                ),
            ),
        )
        with Session(engine) as session:
            create_artifact_version(
                session,
                tenant_id=graph.tenant_id,
                project_id=graph.project_id,
                command=command,
            )

        token_document = {
            "label": "synthetic local demo credentials; do not commit or share",
            "tenant_id": "demo-tenant",
            "expires_at": (now + timedelta(days=2)).isoformat(),
            "tokens": tokens,
        }
        token_path.write_text(json.dumps(token_document, indent=2) + "\n", encoding="utf-8")
        try:
            token_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            # Windows ACLs govern access; the file remains excluded by .gitignore.
            pass
        print(
            json.dumps(
                {
                    "status": "SEEDED_SYNTHETIC_DEMO",
                    "tenant_id": graph.tenant_id,
                    "project_id": graph.project_id,
                    "artifact_version_id": "demo-copy-v1",
                    "artifact_approval": "none; explicit human review is required",
                    "token_file": str(token_path),
                    "token_expires_at": token_document["expires_at"],
                    "token_values_printed": False,
                },
                indent=2,
            )
        )
    except ArtifactConflict as error:
        raise SystemExit(
            f"demo artifact conflicts with existing immutable data: {error}"
        ) from error
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
