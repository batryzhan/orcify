"""Persist immutable project replay snapshots and approval decisions."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0002_snapshots_approvals"
down_revision: str | None = "0001_event_authority"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    json_type: Any = sa.JSON()
    if op.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB

        json_type = JSONB()
    op.create_table(
        "project_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_kind", sa.String(length=32), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision >= 0", name="ck_project_snapshots_revision_nonnegative"),
        sa.CheckConstraint(
            "snapshot_kind IN ('graph', 'replay_state')", name="ck_project_snapshots_kind"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.project_id"],
            name="fk_project_snapshots_project",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_snapshots"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "revision",
            "snapshot_kind",
            name="uq_project_snapshots_revision_kind",
        ),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("approval_id", sa.String(length=128), nullable=False),
        sa.Column("asset_version_id", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("requirement_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision > 0", name="ck_approvals_revision_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.project_id"],
            name="fk_approvals_project",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approvals"),
        sa.UniqueConstraint("tenant_id", "project_id", "approval_id", name="uq_approvals_id"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_approvals_idempotency"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "asset_version_id",
            "revision",
            name="uq_approvals_asset_revision",
        ),
    )
    if op.get_bind().dialect.name == "postgresql":
        for table in ("project_snapshots", "approvals"):
            function = f"reject_{table}_mutation"
            trigger = f"trg_{table}_append_only"
            op.execute(
                f"""CREATE FUNCTION {function}() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION '{table} is append-only'; END;
                $$ LANGUAGE plpgsql"""
            )
            op.execute(
                f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION {function}()"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("project_snapshots", "approvals"):
            op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
            op.execute(f"DROP FUNCTION reject_{table}_mutation()")
    op.drop_table("approvals")
    op.drop_table("project_snapshots")
