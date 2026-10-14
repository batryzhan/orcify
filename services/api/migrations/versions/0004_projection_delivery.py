"""Track retry leases and authoritative projection checkpoints."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004_projection_delivery"
down_revision: str | None = "0003_authoritative_graph_hash"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    with op.batch_alter_table("event_outbox") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
            )
        )
        batch_op.add_column(
            sa.Column(
                "next_attempt_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("lease_token", sa.String(length=64), nullable=True))
        batch_op.create_check_constraint(
            "ck_outbox_status",
            "status IN ('pending', 'processing', 'retry', 'succeeded', 'dead', 'superseded')",
        )
        batch_op.create_index("ix_event_outbox_dispatch", ["status", "next_attempt_at", "id"])
    op.execute("UPDATE event_outbox SET status = 'succeeded' WHERE processed_at IS NOT NULL")

    op.create_table(
        "projection_checkpoints",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("destination", sa.String(length=64), nullable=False),
        sa.Column("source_revision", sa.BigInteger(), nullable=False),
        sa.Column("graph_hash", sa.String(length=64), nullable=False),
        sa.Column("last_event_id", sa.String(length=128), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'healthy'"), nullable=False
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("source_revision >= 0", name="ck_projection_revision_nonnegative"),
        sa.CheckConstraint(
            "status IN ('healthy', 'error', 'rebuilding')", name="ck_projection_status"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.project_id"],
            name="fk_projection_checkpoints_project",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "project_id", "destination", name="pk_projection_checkpoints"
        ),
    )


def downgrade() -> None:
    op.drop_table("projection_checkpoints")
    with op.batch_alter_table("event_outbox") as batch_op:
        batch_op.drop_index("ix_event_outbox_dispatch")
        batch_op.drop_constraint("ck_outbox_status", type_="check")
        batch_op.drop_column("lease_token")
        batch_op.drop_column("lease_until")
        batch_op.drop_column("next_attempt_at")
        batch_op.drop_column("status")
