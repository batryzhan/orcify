"""Keep run/attempt headers immutable while allowing lifecycle index updates."""

from __future__ import annotations

from alembic import op

revision: str = "0006_execution_header_guards"
down_revision: str | None = "0005_artifacts_execution"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "CREATE FUNCTION reject_execution_header_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'execution header metadata is immutable'; END; "
        "$$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_execution_runs_header_immutable BEFORE UPDATE OF "
        "tenant_id, project_id, run_id, graph_revision, snapshot_kind, graph_snapshot_hash, "
        "plan, idempotency_key, request_hash, created_at ON execution_runs "
        "FOR EACH ROW EXECUTE FUNCTION reject_execution_header_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_execution_attempts_header_immutable BEFORE UPDATE OF "
        "tenant_id, project_id, run_id, attempt_id, attempt_number, request_hash, "
        "dependencies, provider_id, model_id, prompt_version, started_at ON execution_attempts "
        "FOR EACH ROW EXECUTE FUNCTION reject_execution_header_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_execution_runs_no_delete BEFORE DELETE ON execution_runs "
        "FOR EACH ROW EXECUTE FUNCTION reject_execution_header_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_execution_attempts_no_delete BEFORE DELETE ON execution_attempts "
        "FOR EACH ROW EXECUTE FUNCTION reject_execution_header_mutation()"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER trg_execution_attempts_no_delete ON execution_attempts")
    op.execute("DROP TRIGGER trg_execution_runs_no_delete ON execution_runs")
    op.execute("DROP TRIGGER trg_execution_attempts_header_immutable ON execution_attempts")
    op.execute("DROP TRIGGER trg_execution_runs_header_immutable ON execution_runs")
    op.execute("DROP FUNCTION reject_execution_header_mutation()")
