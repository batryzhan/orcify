"""Persist immutable artifacts and append-only execution provenance."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0005_artifacts_execution"
down_revision: str | None = "0004_projection_delivery"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    json_type: Any = sa.JSON()
    if op.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB

        json_type = JSONB()

    op.create_table(
        "artifact_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("artifact_version_id", sa.String(128), nullable=False),
        sa.Column("artifact_id", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(128), nullable=False),
        sa.Column("node_version", sa.Integer(), nullable=False),
        sa.Column("graph_revision", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_kind", sa.String(32), server_default="graph", nullable=False),
        sa.Column("graph_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("dependencies", json_type, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("planner_decision", json_type, nullable=False),
        sa.Column("provider_id", sa.String(128)),
        sa.Column("model_id", sa.String(128)),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version > 0", name="ck_artifact_version_positive"),
        sa.CheckConstraint("node_version > 0", name="ck_artifact_node_version_positive"),
        sa.CheckConstraint("snapshot_kind = 'graph'", name="ck_artifact_graph_snapshot_kind"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.project_id"],
            ondelete="RESTRICT",
            name="fk_artifact_versions_project",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "graph_revision", "snapshot_kind"],
            [
                "project_snapshots.tenant_id",
                "project_snapshots.project_id",
                "project_snapshots.revision",
                "project_snapshots.snapshot_kind",
            ],
            ondelete="RESTRICT",
            name="fk_artifact_versions_graph_snapshot",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_artifact_versions"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "artifact_id", "version", name="uq_artifact_version"
        ),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_artifact_idempotency"
        ),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "artifact_version_id", name="uq_artifact_version_id"
        ),
    )
    op.create_index(
        "ix_artifact_scope_node",
        "artifact_versions",
        ["tenant_id", "project_id", "node_id", "node_version"],
    )

    op.create_table(
        "execution_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("graph_revision", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_kind", sa.String(32), server_default="graph", nullable=False),
        sa.Column("graph_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("plan", json_type, nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("snapshot_kind = 'graph'", name="ck_execution_run_snapshot_kind"),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','cancelled','retryable_failure')",
            name="ck_execution_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.project_id"],
            ondelete="RESTRICT",
            name="fk_execution_runs_project",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "graph_revision", "snapshot_kind"],
            [
                "project_snapshots.tenant_id",
                "project_snapshots.project_id",
                "project_snapshots.revision",
                "project_snapshots.snapshot_kind",
            ],
            ondelete="RESTRICT",
            name="fk_execution_runs_graph_snapshot",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_execution_runs"),
        sa.UniqueConstraint("tenant_id", "project_id", "run_id", name="uq_execution_run_id"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_execution_run_idempotency"
        ),
    )

    op.create_table(
        "execution_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("attempt_id", sa.String(128), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("dependencies", json_type, nullable=False),
        sa.Column("provider_id", sa.String(128)),
        sa.Column("model_id", sa.String(128)),
        sa.Column("prompt_version", sa.String(128)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("attempt_number > 0", name="ck_execution_attempt_number_positive"),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed','cancelled','retryable_failure')",
            name="ck_execution_attempt_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "run_id"],
            ["execution_runs.tenant_id", "execution_runs.project_id", "execution_runs.run_id"],
            ondelete="RESTRICT",
            name="fk_execution_attempts_run",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_execution_attempts"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "attempt_id", name="uq_execution_attempt_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "run_id",
            "attempt_number",
            name="uq_execution_attempt_number",
        ),
    )

    op.create_table(
        "execution_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("attempt_id", sa.String(128)),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_classification", sa.String(128)),
        sa.Column("error_message", sa.Text()),
        sa.Column("elapsed_ms", sa.BigInteger()),
        sa.Column("elapsed_status", sa.String(16), server_default="missing", nullable=False),
        sa.Column("token_count", sa.BigInteger()),
        sa.Column("token_status", sa.String(16), server_default="missing", nullable=False),
        sa.Column("cost_usd", sa.Float()),
        sa.Column("cost_status", sa.String(16), server_default="missing", nullable=False),
        sa.Column("artifact_version_id", sa.String(128)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','cancelled','retryable_failure')",
            name="ck_execution_event_status",
        ),
        sa.CheckConstraint(
            "elapsed_status IN ('missing','estimated','measured') AND "
            "((elapsed_status = 'missing' AND elapsed_ms IS NULL) OR "
            "(elapsed_status <> 'missing' AND elapsed_ms IS NOT NULL AND elapsed_ms >= 0))",
            name="ck_execution_event_elapsed_measurement",
        ),
        sa.CheckConstraint(
            "token_status IN ('missing','estimated','measured') AND "
            "((token_status = 'missing' AND token_count IS NULL) OR "
            "(token_status <> 'missing' AND token_count IS NOT NULL AND token_count >= 0))",
            name="ck_execution_event_token_measurement",
        ),
        sa.CheckConstraint(
            "cost_status IN ('missing','estimated','measured') AND "
            "((cost_status = 'missing' AND cost_usd IS NULL) OR "
            "(cost_status <> 'missing' AND cost_usd IS NOT NULL AND cost_usd >= 0))",
            name="ck_execution_event_cost_measurement",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "run_id"],
            ["execution_runs.tenant_id", "execution_runs.project_id", "execution_runs.run_id"],
            ondelete="RESTRICT",
            name="fk_execution_events_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "attempt_id"],
            [
                "execution_attempts.tenant_id",
                "execution_attempts.project_id",
                "execution_attempts.attempt_id",
            ],
            ondelete="RESTRICT",
            name="fk_execution_events_attempt",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "artifact_version_id"],
            [
                "artifact_versions.tenant_id",
                "artifact_versions.project_id",
                "artifact_versions.artifact_version_id",
            ],
            ondelete="RESTRICT",
            name="fk_execution_events_artifact",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_execution_events"),
        sa.UniqueConstraint("tenant_id", "project_id", "event_id", name="uq_execution_event_id"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_execution_event_idempotency"
        ),
    )
    op.create_index(
        "ix_execution_events_run",
        "execution_events",
        ["tenant_id", "project_id", "run_id", "created_at"],
    )

    op.create_table(
        "artifact_provenance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("provenance_id", sa.String(128), nullable=False),
        sa.Column("artifact_version_id", sa.String(128), nullable=False),
        sa.Column("source_kind", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("details", json_type, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "artifact_version_id"],
            [
                "artifact_versions.tenant_id",
                "artifact_versions.project_id",
                "artifact_versions.artifact_version_id",
            ],
            ondelete="RESTRICT",
            name="fk_artifact_provenance_artifact",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_artifact_provenance"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "provenance_id", name="uq_artifact_provenance_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "artifact_version_id",
            "source_id",
            "source_kind",
            name="uq_artifact_provenance_source",
        ),
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("artifact_versions", "execution_events", "artifact_provenance"):
            function = f"reject_{table}_mutation"
            trigger = f"trg_{table}_append_only"
            op.execute(
                f"CREATE FUNCTION {function}() RETURNS trigger AS $$ BEGIN "
                f"RAISE EXCEPTION '{table} is append-only'; END; $$ LANGUAGE plpgsql"
            )
            op.execute(
                f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION {function}()"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("artifact_provenance", "execution_events", "artifact_versions"):
            op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
            op.execute(f"DROP FUNCTION reject_{table}_mutation()")
    op.drop_table("artifact_provenance")
    op.drop_index("ix_execution_events_run", table_name="execution_events")
    op.drop_table("execution_events")
    op.drop_table("execution_attempts")
    op.drop_table("execution_runs")
    op.drop_index("ix_artifact_scope_node", table_name="artifact_versions")
    op.drop_table("artifact_versions")
