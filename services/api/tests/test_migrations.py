import subprocess
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[3]


def test_initial_migration_creates_authority_and_outbox_tables(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "migration-test.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(ROOT / "services" / "api" / "alembic.ini"))

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        schema = inspect(engine)
        project_columns = {column["name"]: column for column in schema.get_columns("projects")}
        assert project_columns["current_graph_hash"]["nullable"] is False
        assert {
            "projects",
            "change_events",
            "event_outbox",
            "project_snapshots",
            "approvals",
            "projection_checkpoints",
            "artifact_versions",
            "execution_runs",
            "execution_attempts",
            "execution_events",
            "artifact_provenance",
            "api_credentials",
            "tenant_memberships",
            "alembic_version",
        } <= set(schema.get_table_names())
        assert {
            "uq_change_events_event",
            "uq_change_events_idempotency",
            "uq_change_events_revision",
        } <= {constraint["name"] for constraint in schema.get_unique_constraints("change_events")}
        assert "uq_outbox_delivery" in {
            constraint["name"] for constraint in schema.get_unique_constraints("event_outbox")
        }
        assert {
            "status",
            "next_attempt_at",
            "lease_until",
            "lease_token",
        } <= {column["name"] for column in schema.get_columns("event_outbox")}
        assert {
            "uq_artifact_version",
            "uq_artifact_idempotency",
        } <= {
            constraint["name"] for constraint in schema.get_unique_constraints("artifact_versions")
        }
        assert {
            "elapsed_status",
            "token_status",
            "cost_status",
            "request_hash",
        } <= {column["name"] for column in schema.get_columns("execution_events")}
    finally:
        engine.dispose()


def test_postgresql_migration_compiles_append_only_trigger(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "services/api/alembic.ini",
            "upgrade",
            "head",
            "--sql",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "JSONB" in result.stdout
    assert "CREATE TRIGGER trg_change_events_append_only" in result.stdout
    assert "CREATE TRIGGER trg_artifact_versions_append_only" in result.stdout
    assert "CREATE TRIGGER trg_execution_events_append_only" in result.stdout
    assert "CREATE TRIGGER trg_execution_runs_header_immutable" in result.stdout
