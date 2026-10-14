"""Add opaque API credentials and authoritative tenant memberships."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007_authenticated_api"
down_revision: str | None = "0006_execution_header_guards"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "api_credentials",
        sa.Column("credential_id", sa.String(128), primary_key=True),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("token_digest", name="uq_api_credentials_digest"),
    )
    op.create_table(
        "tenant_memberships",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("actor_id", sa.String(128), primary_key=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('tenant_admin', 'producer', 'editor', 'reviewer', 'researcher')",
            name="ck_tenant_memberships_role",
        ),
    )


def downgrade() -> None:
    op.drop_table("tenant_memberships")
    op.drop_table("api_credentials")
