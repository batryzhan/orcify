"""Typed HTTP contracts. Identity and authorization claims are deliberately absent."""

from __future__ import annotations

from datetime import datetime

from gamo_ca.graph import Graph
from gamo_ca.models import Approval
from gamo_ca.models import ApprovalDecision as Decision
from gamo_ca.planner import Plan
from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.api.app.artifact_schemas import (
    ArtifactCreateRequest,
    ArtifactEligibilityResult,
    DependencyVersion,
    ExecutionAttemptStartRequest,
    ExecutionRunCreateRequest,
    ExecutionTransitionRequest,
)


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectCreateRequest(StrictRequest):
    project_id: str = Field(min_length=1, max_length=128)
    initial_graph: Graph


class ProjectResponse(StrictRequest):
    tenant_id: str
    project_id: str
    revision: int
    current_graph_hash: str
    current_snapshot_hash: str


class GraphResponse(StrictRequest):
    revision: int
    snapshot_hash: str
    graph: Graph


class GraphChangeRequest(StrictRequest):
    event_id: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=0)
    expected_snapshot_hash: str
    snapshot: Graph
    idempotency_key: str = Field(min_length=1, max_length=256)


class GraphChangeResponse(StrictRequest):
    event_id: str
    revision: int
    snapshot_hash: str
    replayed: bool


class ChangePlanRequest(StrictRequest):
    event_id: str = Field(min_length=1, max_length=128)
    target_id: str
    source_id: str
    change_type: str
    old_version: int = Field(gt=0)
    new_version: int = Field(gt=0)
    old_hash: str
    new_hash: str
    changed_fields: tuple[str, ...]


class ApprovalRequest(StrictRequest):
    approval_id: str = Field(min_length=1, max_length=128)
    asset_version_id: str
    asset_version: int = Field(gt=0)
    requirement_fingerprint: str
    decision: Decision
    policy_version: str
    idempotency_key: str = Field(min_length=1, max_length=256)
    expected_revision: int = Field(ge=0)
    reason: str | None = None
    supersedes_id: str | None = None
    planning_event: ChangePlanRequest


class ArtifactCreateHttpRequest(StrictRequest):
    artifact: ArtifactCreateRequest
    planning_event: ChangePlanRequest

    @field_validator("artifact", mode="before")
    @classmethod
    def parse_artifact_command(cls, value: object) -> ArtifactCreateRequest:
        if isinstance(value, ArtifactCreateRequest):
            return value
        return ArtifactCreateRequest.model_validate(value, strict=False)


class ExecutionRunCreateHttpRequest(StrictRequest):
    run: ExecutionRunCreateRequest
    planning_event: ChangePlanRequest

    @field_validator("run", mode="before")
    @classmethod
    def parse_run_command(cls, value: object) -> ExecutionRunCreateRequest:
        if isinstance(value, ExecutionRunCreateRequest):
            return value
        return ExecutionRunCreateRequest.model_validate(value, strict=False)


class ArtifactResponse(StrictRequest):
    artifact_version_id: str
    artifact_id: str
    version: int
    node_id: str
    node_version: int
    graph_revision: int
    graph_snapshot_hash: str
    dependencies: tuple[DependencyVersion, ...]
    content: str
    content_hash: str
    planner_decision: Plan


class ExecutionRunView(StrictRequest):
    run_id: str
    graph_revision: int
    graph_snapshot_hash: str
    plan: Plan
    status: str
    idempotency_key: str
    created_at: datetime


class ExecutionAttemptView(StrictRequest):
    run_id: str
    attempt_id: str
    attempt_number: int
    request_hash: str
    status: str
    dependencies: tuple[DependencyVersion, ...]
    provider_id: str | None
    model_id: str | None
    prompt_version: str | None
    started_at: datetime
    finished_at: datetime | None


class ExecutionEventView(StrictRequest):
    event_id: str
    run_id: str
    attempt_id: str | None
    idempotency_key: str
    status: str
    error_classification: str | None
    error_message: str | None
    elapsed_ms: int | None
    elapsed_status: str
    token_count: int | None
    token_status: str
    cost_usd: float | None
    cost_status: str
    artifact_version_id: str | None
    created_at: datetime


class RunHistoryResponse(StrictRequest):
    run: ExecutionRunView
    attempts: tuple[ExecutionAttemptView, ...]
    events: tuple[ExecutionEventView, ...]


class ApprovalResponse(StrictRequest):
    approval: Approval
    replayed: bool


class ArtifactCreateResponse(StrictRequest):
    artifact: ArtifactResponse
    replayed: bool


class ExecutionWriteResponse(StrictRequest):
    run_id: str
    status: str
    replayed: bool


class ApiError(StrictRequest):
    detail: str


# Keep imports used by OpenAPI/schema consumers explicit and stable.
__all__ = [
    "ApprovalRequest",
    "ApprovalResponse",
    "ArtifactCreateHttpRequest",
    "ArtifactCreateRequest",
    "ArtifactCreateResponse",
    "ArtifactEligibilityResult",
    "ArtifactResponse",
    "ChangePlanRequest",
    "ExecutionAttemptStartRequest",
    "ExecutionAttemptView",
    "ExecutionEventView",
    "ExecutionRunCreateHttpRequest",
    "ExecutionRunCreateRequest",
    "ExecutionRunView",
    "ExecutionTransitionRequest",
    "ExecutionWriteResponse",
    "GraphChangeRequest",
    "GraphChangeResponse",
    "GraphResponse",
    "ProjectCreateRequest",
    "ProjectResponse",
    "RunHistoryResponse",
]
