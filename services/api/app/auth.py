"""Server-verified bearer authentication and tenant role resolution."""

# ruff: noqa: B008 -- FastAPI dependency defaults are its declared injection mechanism.

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.app.models import ApiCredentialRecord, TenantMembershipRecord

bearer = HTTPBearer(auto_error=False)


def get_session(request: Request) -> Iterator[Session]:
    """Yield one request-scoped SQLAlchemy session from the configured app factory."""
    factory = request.app.state.session_factory
    with factory() as session:
        yield session


@dataclass(frozen=True, slots=True)
class Principal:
    """Actor identity obtained only from a live server-side credential row."""

    actor_id: str
    credential_id: str


def authenticate(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> Principal:
    """Resolve an opaque token digest to an unexpired, non-revoked actor."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    token = credentials.credentials
    if len(token) < 32 or len(token) > 256:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credential")
    digest = sha256(token.encode("utf-8")).hexdigest()
    row = session.scalar(
        select(ApiCredentialRecord).where(ApiCredentialRecord.token_digest == digest)
    )
    now = datetime.now(UTC)
    expires_at = row.expires_at if row is not None else now
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if row is None or row.revoked_at is not None or expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credential")
    return Principal(row.actor_id, row.credential_id)


def require_membership(
    session: Session, *, principal: Principal, tenant_id: str, roles: set[str]
) -> TenantMembershipRecord:
    """Authorize from the current PostgreSQL membership, never request claims."""
    membership = session.scalar(
        select(TenantMembershipRecord).where(
            TenantMembershipRecord.tenant_id == tenant_id,
            TenantMembershipRecord.actor_id == principal.actor_id,
        )
    )
    if membership is None or membership.revoked_at is not None:
        # A nonmember must not learn whether the tenant or project exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource not found")
    if membership.role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="role is not authorized")
    return membership


def require_existing_project_membership(
    session: Session, *, principal: Principal, tenant_id: str, project_id: str, roles: set[str]
) -> TenantMembershipRecord:
    """Check project existence and tenant membership without cross-tenant disclosure."""
    from services.api.app.event_store import ProjectNotFound, load_project

    try:
        load_project(session, tenant_id, project_id)
    except ProjectNotFound as error:
        raise HTTPException(status_code=404, detail="resource not found") from error
    return require_membership(session, principal=principal, tenant_id=tenant_id, roles=roles)
