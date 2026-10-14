"""SQLAlchemy persistence models; PostgreSQL is the system of record."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    event as sqlalchemy_event,
)
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Metadata root for Alembic and database tests."""


class ProjectRecord(Base):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint("revision >= 0", name="ck_projects_revision_nonnegative"),)

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    current_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    current_graph_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    replay_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChangeEventRecord(Base):
    __tablename__ = "change_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.project_id"],
            ondelete="RESTRICT",
            name="fk_change_events_project",
        ),
        UniqueConstraint("tenant_id", "project_id", "event_id", name="uq_change_events_event"),
        UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_change_events_idempotency"
        ),
        UniqueConstraint("tenant_id", "project_id", "revision", name="uq_change_events_revision"),
        CheckConstraint("revision > 0", name="ck_change_events_revision_positive"),
        Index("ix_change_events_scope_revision", "tenant_id", "project_id", "revision"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)
    receipt: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ImmutableEventMutation(RuntimeError):
    """Raised when application code tries to edit or delete an event record."""


@sqlalchemy_event.listens_for(ChangeEventRecord, "before_update")
@sqlalchemy_event.listens_for(ChangeEventRecord, "before_delete")
def _reject_event_mutation(*args: object) -> None:
    raise ImmutableEventMutation("change event records are append-only")


class EventOutboxRecord(Base):
    __tablename__ = "event_outbox"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id", "event_id"],
            [
                "change_events.tenant_id",
                "change_events.project_id",
                "change_events.event_id",
            ],
            ondelete="RESTRICT",
            name="fk_outbox_event",
        ),
        UniqueConstraint(
            "tenant_id", "project_id", "event_id", "destination", name="uq_outbox_delivery"
        ),
        CheckConstraint("attempt_count >= 0", name="ck_outbox_attempts_nonnegative"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'retry', 'succeeded', 'dead', 'superseded')",
            name="ck_outbox_status",
        ),
        Index("ix_event_outbox_pending", "processed_at", "id"),
        Index("ix_event_outbox_dispatch", "status", "next_attempt_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    destination: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(64))


class ProjectionCheckpointRecord(Base):
    """PostgreSQL checkpoint for the rebuildable graph projection."""

    __tablename__ = "projection_checkpoints"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.project_id"],
            ondelete="RESTRICT",
            name="fk_projection_checkpoints_project",
        ),
        CheckConstraint("source_revision >= 0", name="ck_projection_revision_nonnegative"),
        CheckConstraint(
            "status IN ('healthy', 'error', 'rebuilding')", name="ck_projection_status"
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    destination: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    graph_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    last_event_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'healthy'")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProjectSnapshotRecord(Base):
    """Immutable versioned graph/replay snapshots retained by the authority store."""

    __tablename__ = "project_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.project_id"],
            ondelete="RESTRICT",
            name="fk_project_snapshots_project",
        ),
        UniqueConstraint(
            "tenant_id",
            "project_id",
            "revision",
            "snapshot_kind",
            name="uq_project_snapshots_revision_kind",
        ),
        CheckConstraint("revision >= 0", name="ck_project_snapshots_revision_nonnegative"),
        CheckConstraint(
            "snapshot_kind IN ('graph', 'replay_state')", name="ck_project_snapshots_kind"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ApprovalRecord(Base):
    """Append-only persistence for domain-validated exact-version decisions."""

    __tablename__ = "approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.project_id"],
            ondelete="RESTRICT",
            name="fk_approvals_project",
        ),
        UniqueConstraint("tenant_id", "project_id", "approval_id", name="uq_approvals_id"),
        UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_approvals_idempotency"
        ),
        UniqueConstraint(
            "tenant_id",
            "project_id",
            "asset_version_id",
            "revision",
            name="uq_approvals_asset_revision",
        ),
        CheckConstraint("revision > 0", name="ck_approvals_revision_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    approval_id: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requirement_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ArtifactVersionRecord(Base):
    """Immutable creative output bound to an exact graph and dependency snapshot."""

    __tablename__ = "artifact_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.project_id"],
            ondelete="RESTRICT",
            name="fk_artifact_versions_project",
        ),
        ForeignKeyConstraint(
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
        UniqueConstraint(
            "tenant_id", "project_id", "artifact_id", "version", name="uq_artifact_version"
        ),
        UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_artifact_idempotency"
        ),
        UniqueConstraint(
            "tenant_id", "project_id", "artifact_version_id", name="uq_artifact_version_id"
        ),
        CheckConstraint("version > 0", name="ck_artifact_version_positive"),
        CheckConstraint("node_version > 0", name="ck_artifact_node_version_positive"),
        CheckConstraint("snapshot_kind = 'graph'", name="ck_artifact_graph_snapshot_kind"),
        Index("ix_artifact_scope_node", "tenant_id", "project_id", "node_id", "node_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    node_version: Mapped[int] = mapped_column(Integer, nullable=False)
    graph_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'graph'")
    )
    graph_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dependencies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    planner_decision: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provider_id: Mapped[str | None] = mapped_column(String(128))
    model_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExecutionRunRecord(Base):
    """Run header; current status is advanced with append-only execution events."""

    __tablename__ = "execution_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.project_id"],
            ondelete="RESTRICT",
            name="fk_execution_runs_project",
        ),
        ForeignKeyConstraint(
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
        UniqueConstraint("tenant_id", "project_id", "run_id", name="uq_execution_run_id"),
        UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_execution_run_idempotency"
        ),
        CheckConstraint("snapshot_kind = 'graph'", name="ck_execution_run_snapshot_kind"),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled', "
            "'retryable_failure')",
            name="ck_execution_run_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'graph'")
    )
    graph_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'pending'")
    )
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExecutionAttemptRecord(Base):
    """Current index for one immutable attempt identity and captured dependencies."""

    __tablename__ = "execution_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id", "run_id"],
            ["execution_runs.tenant_id", "execution_runs.project_id", "execution_runs.run_id"],
            ondelete="RESTRICT",
            name="fk_execution_attempts_run",
        ),
        UniqueConstraint("tenant_id", "project_id", "attempt_id", name="uq_execution_attempt_id"),
        UniqueConstraint(
            "tenant_id",
            "project_id",
            "run_id",
            "attempt_number",
            name="uq_execution_attempt_number",
        ),
        CheckConstraint("attempt_number > 0", name="ck_execution_attempt_number_positive"),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'cancelled', 'retryable_failure')",
            name="ck_execution_attempt_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_id: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    dependencies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    provider_id: Mapped[str | None] = mapped_column(String(128))
    model_id: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExecutionEventRecord(Base):
    """Append-only execution lifecycle/provenance event with honest metric status."""

    __tablename__ = "execution_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id", "run_id"],
            ["execution_runs.tenant_id", "execution_runs.project_id", "execution_runs.run_id"],
            ondelete="RESTRICT",
            name="fk_execution_events_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id", "attempt_id"],
            [
                "execution_attempts.tenant_id",
                "execution_attempts.project_id",
                "execution_attempts.attempt_id",
            ],
            ondelete="RESTRICT",
            name="fk_execution_events_attempt",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id", "artifact_version_id"],
            [
                "artifact_versions.tenant_id",
                "artifact_versions.project_id",
                "artifact_versions.artifact_version_id",
            ],
            ondelete="RESTRICT",
            name="fk_execution_events_artifact",
        ),
        UniqueConstraint("tenant_id", "project_id", "event_id", name="uq_execution_event_id"),
        UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_execution_event_idempotency"
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled', "
            "'retryable_failure')",
            name="ck_execution_event_status",
        ),
        CheckConstraint(
            "elapsed_status IN ('missing', 'estimated', 'measured') AND "
            "((elapsed_status = 'missing' AND elapsed_ms IS NULL) OR "
            "(elapsed_status <> 'missing' AND elapsed_ms IS NOT NULL AND elapsed_ms >= 0))",
            name="ck_execution_event_elapsed_measurement",
        ),
        CheckConstraint(
            "token_status IN ('missing', 'estimated', 'measured') AND "
            "((token_status = 'missing' AND token_count IS NULL) OR "
            "(token_status <> 'missing' AND token_count IS NOT NULL AND token_count >= 0))",
            name="ck_execution_event_token_measurement",
        ),
        CheckConstraint(
            "cost_status IN ('missing', 'estimated', 'measured') AND "
            "((cost_status = 'missing' AND cost_usd IS NULL) OR "
            "(cost_status <> 'missing' AND cost_usd IS NOT NULL AND cost_usd >= 0))",
            name="ck_execution_event_cost_measurement",
        ),
        Index("ix_execution_events_run", "tenant_id", "project_id", "run_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_classification: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    elapsed_ms: Mapped[int | None] = mapped_column(BigInteger)
    elapsed_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'missing'")
    )
    token_count: Mapped[int | None] = mapped_column(BigInteger)
    token_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'missing'")
    )
    cost_usd: Mapped[float | None] = mapped_column()
    cost_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'missing'")
    )
    artifact_version_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ArtifactProvenanceRecord(Base):
    """Append-only source and generation provenance attached to an artifact version."""

    __tablename__ = "artifact_provenance"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id", "artifact_version_id"],
            [
                "artifact_versions.tenant_id",
                "artifact_versions.project_id",
                "artifact_versions.artifact_version_id",
            ],
            ondelete="RESTRICT",
            name="fk_artifact_provenance_artifact",
        ),
        UniqueConstraint(
            "tenant_id", "project_id", "provenance_id", name="uq_artifact_provenance_id"
        ),
        UniqueConstraint(
            "tenant_id",
            "project_id",
            "artifact_version_id",
            "source_id",
            "source_kind",
            name="uq_artifact_provenance_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provenance_id: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ImmutableRecordMutation(RuntimeError):
    """Raised when application code tries to edit or delete immutable history."""


@sqlalchemy_event.listens_for(ProjectSnapshotRecord, "before_update")
@sqlalchemy_event.listens_for(ProjectSnapshotRecord, "before_delete")
@sqlalchemy_event.listens_for(ApprovalRecord, "before_update")
@sqlalchemy_event.listens_for(ApprovalRecord, "before_delete")
@sqlalchemy_event.listens_for(ArtifactVersionRecord, "before_update")
@sqlalchemy_event.listens_for(ArtifactVersionRecord, "before_delete")
@sqlalchemy_event.listens_for(ExecutionEventRecord, "before_update")
@sqlalchemy_event.listens_for(ExecutionEventRecord, "before_delete")
@sqlalchemy_event.listens_for(ArtifactProvenanceRecord, "before_update")
@sqlalchemy_event.listens_for(ArtifactProvenanceRecord, "before_delete")
def _reject_immutable_mutation(*args: object) -> None:
    raise ImmutableRecordMutation(
        "snapshot, approval, artifact, and provenance records are append-only"
    )


@sqlalchemy_event.listens_for(ExecutionRunRecord, "before_update")
def _protect_execution_run_header(
    mapper: object, connection: object, target: ExecutionRunRecord
) -> None:
    changed = {
        attribute.key
        for attribute in sqlalchemy_inspect(target).attrs
        if attribute.history.has_changes()
    }
    if changed - {"status"}:
        raise ImmutableRecordMutation("execution run metadata is immutable")


@sqlalchemy_event.listens_for(ExecutionAttemptRecord, "before_update")
def _protect_execution_attempt_header(
    mapper: object, connection: object, target: ExecutionAttemptRecord
) -> None:
    changed = {
        attribute.key
        for attribute in sqlalchemy_inspect(target).attrs
        if attribute.history.has_changes()
    }
    if changed - {"status", "finished_at"}:
        raise ImmutableRecordMutation("execution attempt metadata is immutable")


def utc_now() -> datetime:
    """Return an aware timestamp for application-created records."""
    return datetime.now(UTC)
