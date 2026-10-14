"""PostgreSQL auth-boundary smoke coverage (requires a migrated test database)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from services.api.app.http import create_app
from services.api.app.models import ApiCredentialRecord, TenantMembershipRecord

DATABASE_URL = os.environ.get("ORCIFY_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="ORCIFY_TEST_DATABASE_URL is not set")


def test_live_postgres_authentication_and_revocation() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    tenant_id = f"auth-test-{uuid4().hex}"
    actor_id = f"actor-{uuid4().hex}"
    token = f"orc_{uuid4().hex}{uuid4().hex}"
    credential_id = uuid4().hex
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.add(
            TenantMembershipRecord(tenant_id=tenant_id, actor_id=actor_id, role="researcher")
        )
        session.add(
            ApiCredentialRecord(
                credential_id=credential_id,
                actor_id=actor_id,
                token_digest=sha256(token.encode()).hexdigest(),
                expires_at=now + timedelta(minutes=5),
            )
        )

    client = TestClient(create_app(engine))
    projects_url = f"/api/v1/tenants/{tenant_id}/projects"
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(projects_url, headers=headers).status_code == 200
    assert client.get(projects_url).status_code == 401

    with Session(engine) as session, session.begin():
        membership = session.get(TenantMembershipRecord, (tenant_id, actor_id))
        assert membership is not None
        membership.revoked_at = datetime.now(UTC)
    assert client.get(projects_url, headers=headers).status_code == 404

    with Session(engine) as session, session.begin():
        session.execute(
            delete(ApiCredentialRecord).where(ApiCredentialRecord.credential_id == credential_id)
        )
        session.execute(
            delete(TenantMembershipRecord).where(
                TenantMembershipRecord.tenant_id == tenant_id,
                TenantMembershipRecord.actor_id == actor_id,
            )
        )
    engine.dispose()
