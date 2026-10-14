"""Immutable domain records. No infrastructure libraries or implicit clock/ID use."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite


def require_id(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("identifier must be non-empty")


def require_time(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp requires timezone")


def require_hash(value: str) -> None:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("expected lowercase SHA-256 hash")


class DependencyType(StrEnum):
    HARD = "HARD"
    SOFT = "SOFT"
    INFORMATIONAL = "INFORMATIONAL"


class Action(StrEnum):
    KEEP = "KEEP"
    RECOMPUTE = "RECOMPUTE"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class RequirementStatus(StrEnum):
    UNCONFIRMED = "UNCONFIRMED"
    CONFIRMED = "CONFIRMED"


class ApprovalDecision(StrEnum):
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True, kw_only=True)
class Entity:
    id: str
    tenant_id: str
    project_id: str
    created_at: datetime
    schema_version: int = 1

    def __post_init__(self) -> None:
        for value in (self.id, self.tenant_id, self.project_id):
            require_id(value)
        require_time(self.created_at)
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unsupported schema version")


@dataclass(frozen=True, slots=True)
class InputRef:
    source_id: str
    version: int
    content_hash: str

    def __post_init__(self) -> None:
        require_id(self.source_id)
        require_hash(self.content_hash)
        if type(self.version) is not int or self.version < 1:
            raise ValueError("version must be positive")


@dataclass(frozen=True, slots=True, kw_only=True)
class Snapshot(Entity):
    version: int
    content: str
    valid_from: datetime
    valid_to: datetime | None = None
    inputs: tuple[InputRef, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    provider: str = "none"
    model_version: str = "none"
    prompt_version: str = "none"
    policy_version: str = "v1"
    estimated_cost_usd: float | None = None
    estimated_latency_s: float | None = None

    def __post_init__(self) -> None:
        Entity.__post_init__(self)
        if type(self.version) is not int or self.version < 1:
            raise ValueError("version must be positive")
        require_time(self.valid_from)
        if self.valid_to is not None:
            require_time(self.valid_to)
            if self.valid_to <= self.valid_from:
                raise ValueError("invalid validity interval")
        if not isinstance(self.inputs, tuple) or not isinstance(self.evidence_ids, tuple):
            raise TypeError("snapshot collections must be immutable tuples")
        if not isinstance(self.content, str) or any(
            not isinstance(ref, InputRef) for ref in self.inputs
        ):
            raise TypeError("snapshot content/input types are invalid")
        if len({ref.source_id for ref in self.inputs}) != len(self.inputs):
            raise ValueError("duplicate consumed input")
        for value in (self.provider, self.model_version, self.prompt_version, self.policy_version):
            require_id(value)
        for value in self.evidence_ids:
            require_id(value)
        for estimate in (self.estimated_cost_usd, self.estimated_latency_s):
            if estimate is not None and (not isfinite(estimate) or estimate < 0):
                raise ValueError("estimate must be finite and nonnegative")

    @property
    def content_hash(self) -> str:
        from gamo_ca.fingerprints import fingerprint

        return fingerprint(self.content)

    def active_at(self, instant: datetime) -> bool:
        return self.valid_from <= instant and (self.valid_to is None or instant < self.valid_to)


@dataclass(frozen=True, slots=True, kw_only=True)
class Tenant(Entity):
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Campaign(Entity):
    title: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Brief(Snapshot):
    filename: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Requirement(Snapshot):
    source_id: str
    status: RequirementStatus = RequirementStatus.UNCONFIRMED
    confirmed_by: str | None = None

    def __post_init__(self) -> None:
        Snapshot.__post_init__(self)
        require_id(self.source_id)
        if not isinstance(self.status, RequirementStatus):
            raise ValueError("invalid requirement status")
        if self.status == RequirementStatus.CONFIRMED and not self.confirmed_by:
            raise ValueError("confirmed requirement requires human actor")
        if self.status == RequirementStatus.UNCONFIRMED and self.confirmed_by is not None:
            raise ValueError("unconfirmed requirement cannot claim confirmation")


@dataclass(frozen=True, slots=True, kw_only=True)
class Evidence(Snapshot):
    source_id: str
    extracted_span: str
    confirmed_by: str | None = None

    def __post_init__(self) -> None:
        Snapshot.__post_init__(self)
        require_id(self.source_id)
        if not isinstance(self.extracted_span, str):
            raise TypeError("evidence span must be text")
        if self.confirmed_by is not None:
            require_id(self.confirmed_by)


@dataclass(frozen=True, slots=True, kw_only=True)
class Task(Snapshot):
    task_type: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetVersion(Snapshot):
    asset_id: str
    requirement_fingerprint: str

    def __post_init__(self) -> None:
        Snapshot.__post_init__(self)
        require_id(self.asset_id)
        require_hash(self.requirement_fingerprint)
        if not self.inputs or not self.evidence_ids or self.provider == "none":
            raise ValueError("derived asset requires input and provider provenance")


@dataclass(frozen=True, slots=True, kw_only=True)
class Feedback(Entity):
    asset_version_id: str
    actor_id: str
    comment: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Approval(Entity):
    asset_version_id: str
    asset_version: int
    requirement_fingerprint: str
    actor_id: str
    decision: ApprovalDecision
    policy_version: str
    idempotency_key: str
    expected_revision: int
    reason: str | None = None
    supersedes_id: str | None = None

    def __post_init__(self) -> None:
        Entity.__post_init__(self)
        require_id(self.asset_version_id)
        require_id(self.actor_id)
        require_hash(self.requirement_fingerprint)
        require_id(self.policy_version)
        require_id(self.idempotency_key)
        if type(self.asset_version) is not int or self.asset_version < 1:
            raise ValueError("approval asset version must be positive")
        if type(self.expected_revision) is not int or self.expected_revision < 0:
            raise ValueError("approval revision must be nonnegative")
        if not isinstance(self.decision, ApprovalDecision):
            raise ValueError("invalid approval decision")
        if self.decision in (ApprovalDecision.REJECTED, ApprovalDecision.REVOKED):
            if not isinstance(self.reason, str) or not self.reason.strip():
                raise ValueError("rejection/revocation requires reason")
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("approval reason must be text")
        if self.supersedes_id is not None:
            require_id(self.supersedes_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeEvent(Entity):
    target_id: str
    source_id: str
    actor_id: str
    change_type: str
    old_version: int
    new_version: int
    old_hash: str
    new_hash: str
    changed_fields: tuple[str, ...]
    occurred_at: datetime
    expected_snapshot_hash: str

    def __post_init__(self) -> None:
        Entity.__post_init__(self)
        for value in (self.target_id, self.source_id, self.actor_id, self.change_type):
            require_id(value)
        for value in (self.old_hash, self.new_hash, self.expected_snapshot_hash):
            require_hash(value)
        require_time(self.occurred_at)
        if self.old_version < 1 or self.new_version <= self.old_version:
            raise ValueError("change must advance version")
        if not isinstance(self.changed_fields, tuple) or not self.changed_fields:
            raise ValueError("change requires immutable changed fields")
        for value in self.changed_fields:
            require_id(value)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionRecord(Entity):
    event_id: str
    task_id: str
    input_fingerprint: str
    output_hash: str | None
    provider: str
    model_version: str
    prompt_version: str
    status: str
    error_code: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DependencyEdge(Entity):
    upstream_id: str
    dependent_id: str
    strength: DependencyType
    valid_from: datetime
    valid_to: datetime | None = None
    relevant_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        Entity.__post_init__(self)
        require_id(self.upstream_id)
        require_id(self.dependent_id)
        require_time(self.valid_from)
        if not isinstance(self.strength, DependencyType):
            raise ValueError("invalid dependency strength")
        if self.valid_to is not None:
            require_time(self.valid_to)
            if self.valid_to <= self.valid_from:
                raise ValueError("invalid edge validity interval")
        if not isinstance(self.relevant_fields, tuple):
            raise TypeError("relevance fields must be immutable")
        for field in self.relevant_fields:
            require_id(field)

    def active_at(self, instant: datetime) -> bool:
        return self.valid_from <= instant and (self.valid_to is None or instant < self.valid_to)


type Node = Brief | Requirement | Evidence | Task | AssetVersion
DOMAIN_TYPES = (
    Tenant,
    Campaign,
    Brief,
    Requirement,
    Evidence,
    Task,
    AssetVersion,
    Feedback,
    Approval,
    ChangeEvent,
    ExecutionRecord,
    DependencyEdge,
)
