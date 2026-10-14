"""Provision one API token and tenant membership; print the raw token once."""

from __future__ import annotations

import argparse
import os
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from services.api.app.models import ApiCredentialRecord, TenantMembershipRecord


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument(
        "--role",
        required=True,
        choices=("tenant_admin", "producer", "editor", "reviewer", "researcher"),
    )
    parser.add_argument("--expires-days", type=int, default=30)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL must point to the migrated authoritative PostgreSQL database")
    if args.expires_days < 1 or args.expires_days > 365:
        parser.error("--expires-days must be between 1 and 365")

    token = f"orc_{secrets.token_urlsafe(40)}"
    now = datetime.now(UTC)
    engine = create_engine(database_url, pool_pre_ping=True)
    with Session(engine) as session, session.begin():
        if session.get(TenantMembershipRecord, (args.tenant, args.actor)) is not None:
            parser.error(
                "membership already exists; use an approved administrative process to change it"
            )
        credential_id = secrets.token_hex(16)
        session.add(
            TenantMembershipRecord(tenant_id=args.tenant, actor_id=args.actor, role=args.role)
        )
        session.add(
            ApiCredentialRecord(
                credential_id=credential_id,
                actor_id=args.actor,
                token_digest=sha256(token.encode("utf-8")).hexdigest(),
                expires_at=now + timedelta(days=args.expires_days),
            )
        )
    engine.dispose()
    print("Store this token securely. It cannot be retrieved again:")
    print(token)


if __name__ == "__main__":
    main()
