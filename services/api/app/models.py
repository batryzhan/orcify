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
        Index("ix_event_outbox_pending", "processed_at", "id"),
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


class ImmutableRecordMutation(RuntimeError):
    """Raised when application code tries to edit or delete immutable history."""


@sqlalchemy_event.listens_for(ProjectSnapshotRecord, "before_update")
@sqlalchemy_event.listens_for(ProjectSnapshotRecord, "before_delete")
@sqlalchemy_event.listens_for(ApprovalRecord, "before_update")
@sqlalchemy_event.listens_for(ApprovalRecord, "before_delete")
def _reject_immutable_mutation(*args: object) -> None:
    raise ImmutableRecordMutation("snapshot and approval records are append-only")


def utc_now() -> datetime:
    """Return an aware timestamp for application-created records."""
    return datetime.now(UTC)
