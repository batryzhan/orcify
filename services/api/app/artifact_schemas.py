"""Typed persistence commands for artifacts and execution provenance."""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Literal

from gamo_ca.models import require_hash
from gamo_ca.planner import Plan
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DependencyVersion(StrictModel):
    node_id: str = Field(min_length=1, max_length=128)
    node_version: int = Field(gt=0)
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        require_hash(value)
        return value


class ProvenanceInput(StrictModel):
    provenance_id: str = Field(min_length=1, max_length=128)
    source_kind: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)
    details: dict[str, object] = Field(default_factory=dict)


class ArtifactCreateRequest(StrictModel):
    artifact_version_id: str = Field(min_length=1, max_length=128)
    artifact_id: str = Field(min_length=1, max_length=128)
    node_id: str = Field(min_length=1, max_length=128)
    node_version: int = Field(gt=0)
    expected_project_revision: int = Field(ge=0)
    graph_revision: int = Field(ge=0)
    graph_snapshot_hash: str
    dependencies: tuple[DependencyVersion, ...]
    content: str
    planner_decision: Plan
    idempotency_key: str = Field(min_length=1, max_length=256)
    provider_id: str | None = Field(default=None, max_length=128)
    model_id: str | None = Field(default=None, max_length=128)
    provenance: tuple[ProvenanceInput, ...]

    @field_validator("graph_snapshot_hash")
    @classmethod
    def validate_graph_hash(cls, value: str) -> str:
        require_hash(value)
        return value

    @field_validator("dependencies")
    @classmethod
    def unique_dependencies(
        cls, value: tuple[DependencyVersion, ...]
    ) -> tuple[DependencyVersion, ...]:
        if len({dependency.node_id for dependency in value}) != len(value):
            raise ValueError("dependency node IDs must be unique")
        return value

    @field_validator("provenance")
    @classmethod
    def unique_provenance(cls, value: tuple[ProvenanceInput, ...]) -> tuple[ProvenanceInput, ...]:
        keys = {(record.source_kind, record.source_id) for record in value}
        if len(keys) != len(value):
            raise ValueError("provenance sources must be unique")
        return value


class ExecutionRunCreateRequest(StrictModel):
    run_id: str = Field(min_length=1, max_length=128)
    expected_project_revision: int = Field(ge=0)
    graph_revision: int = Field(ge=0)
    graph_snapshot_hash: str
    planner_decision: Plan
    idempotency_key: str = Field(min_length=1, max_length=256)

    @field_validator("graph_snapshot_hash")
    @classmethod
    def validate_graph_hash(cls, value: str) -> str:
        require_hash(value)
        return value


class ExecutionAttemptStartRequest(StrictModel):
    attempt_id: str = Field(min_length=1, max_length=128)
    node_id: str = Field(min_length=1, max_length=128)
    attempt_number: int = Field(gt=0)
    dependencies: tuple[DependencyVersion, ...]
    idempotency_key: str = Field(min_length=1, max_length=256)
    provider_id: str | None = Field(default=None, max_length=128)
    model_id: str | None = Field(default=None, max_length=128)
    prompt_version: str | None = Field(default=None, max_length=128)


class MetricStatus(StrEnum):
    MISSING = "missing"
    ESTIMATED = "estimated"
    MEASURED = "measured"


class ExecutionMetric(StrictModel):
    status: MetricStatus = MetricStatus.MISSING
    value: int | float | None = None

    @field_validator("value")
    @classmethod
    def validate_nonnegative(cls, value: int | float | None) -> int | float | None:
        if value is not None and (value < 0 or not isfinite(value)):
            raise ValueError("metric values must be finite and nonnegative")
        return value

    def model_post_init(self, __context: object) -> None:
        if (self.status == MetricStatus.MISSING) != (self.value is None):
            raise ValueError("missing metrics must have no value; estimated/measured need a value")


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYABLE_FAILURE = "retryable_failure"


class ExecutionTransitionRequest(StrictModel):
    event_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=256)
    status: Literal["succeeded", "failed", "cancelled", "retryable_failure"]
    error_classification: str | None = Field(default=None, max_length=128)
    error_message: str | None = None
    elapsed: ExecutionMetric = Field(default_factory=ExecutionMetric)
    tokens: ExecutionMetric = Field(default_factory=ExecutionMetric)
    cost_usd: ExecutionMetric = Field(default_factory=ExecutionMetric)
    artifact_version_id: str | None = Field(default=None, max_length=128)


class ArtifactEligibilityResult(StrictModel):
    eligible: bool
    reasons: tuple[str, ...]
    artifact_version_id: str
