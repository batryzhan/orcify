"""Create scoped projects, immutable change log and transactional outbox."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_event_authority"
down_revision = None
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("current_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("replay_state", json_type, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision >= 0", name="ck_projects_revision_nonnegative"),
        sa.PrimaryKeyConstraint("tenant_id", "project_id", name="pk_projects"),
    )
    op.create_table(
        "change_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("receipt", json_type, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision > 0", name="ck_change_events_revision_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.project_id"],
            name="fk_change_events_project",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_change_events"),
        sa.UniqueConstraint("tenant_id", "project_id", "event_id", name="uq_change_events_event"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_change_events_idempotency"
        ),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "revision", name="uq_change_events_revision"
        ),
    )
    op.create_index(
        "ix_change_events_scope_revision",
        "change_events",
        ["tenant_id", "project_id", "revision"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_change_event_mutation() RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'change_events is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_change_events_append_only
            BEFORE UPDATE OR DELETE ON change_events
            FOR EACH ROW EXECUTE FUNCTION reject_change_event_mutation()
            """
        )
    op.create_table(
        "event_outbox",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("destination", sa.String(length=64), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint("attempt_count >= 0", name="ck_outbox_attempts_nonnegative"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "event_id"],
            ["change_events.tenant_id", "change_events.project_id", "change_events.event_id"],
            name="fk_outbox_event",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_event_outbox"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "event_id", "destination", name="uq_outbox_delivery"
        ),
    )
    op.create_index("ix_event_outbox_pending", "event_outbox", ["processed_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_event_outbox_pending", table_name="event_outbox")
    op.drop_table("event_outbox")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER trg_change_events_append_only ON change_events")
        op.execute("DROP FUNCTION reject_change_event_mutation()")
    op.drop_index("ix_change_events_scope_revision", table_name="change_events")
    op.drop_table("change_events")
    op.drop_table("projects")
