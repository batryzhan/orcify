"""Pure approval state transitions and fail-closed publication eligibility."""

from dataclasses import dataclass
from enum import StrEnum

from gamo_ca.fingerprints import fingerprint, requirement_fingerprint
from gamo_ca.graph import Graph
from gamo_ca.models import (
    Action,
    Approval,
    ApprovalDecision,
    AssetVersion,
    Evidence,
    RequirementStatus,
    require_id,
)
from gamo_ca.planner import Plan


class ApprovalError(ValueError):
    """Approval rejected because actor, state or snapshots are unsafe."""


class ApprovalConflict(ApprovalError):
    """Same approval key/identifier was reused with conflicting content."""


class ApprovalState(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class ReviewerIdentity:
    """Identity/role claim constructed from authenticated server-side authorization."""

    actor_id: str
    tenant_id: str
    project_id: str
    role: str
    is_human: bool

    def __post_init__(self) -> None:
        for value in (self.actor_id, self.tenant_id, self.project_id, self.role):
            require_id(value)


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    history: tuple[Approval, ...]
    latest: Approval
    replayed: bool


@dataclass(frozen=True, slots=True)
class PublicationDecision:
    eligible: bool
    asset_version_id: str
    reasons: tuple[str, ...]
    approval_id: str | None


def _semantic_hash(approval: Approval) -> str:
    return fingerprint(
        (
            approval.tenant_id,
            approval.project_id,
            approval.asset_version_id,
            approval.asset_version,
            approval.requirement_fingerprint,
            approval.actor_id,
            approval.decision,
            approval.policy_version,
            approval.expected_revision,
            approval.reason,
            approval.supersedes_id,
        )
    )


def _history_for(
    history: tuple[Approval, ...], tenant_id: str, project_id: str, asset_version_id: str
) -> tuple[Approval, ...]:
    seen_ids: set[str] = set()
    seen_keys: dict[tuple[str, str, str], Approval] = {}
    for record in history:
        if (record.tenant_id, record.project_id) != (tenant_id, project_id):
            raise ApprovalError("approval history scope mismatch")
        if record.id in seen_ids:
            raise ApprovalConflict("duplicate approval identifier")
        seen_ids.add(record.id)
        key = (record.tenant_id, record.project_id, record.idempotency_key)
        previous = seen_keys.get(key)
        if previous is not None and _semantic_hash(previous) != _semantic_hash(record):
            raise ApprovalConflict("idempotency key has conflicting approvals")
        if previous is not None:
            raise ApprovalConflict("duplicate approval idempotency record")
        seen_keys[key] = record
    return tuple(record for record in history if record.asset_version_id == asset_version_id)


def apply_approval(
    history: tuple[Approval, ...],
    command: Approval,
    identity: ReviewerIdentity,
    graph: Graph,
    plan: Plan,
) -> ApprovalResult:
    """Append a human decision after checking exact snapshots and optimistic revision."""
    if not isinstance(history, tuple):
        raise TypeError("approval history must be immutable")
    if (identity.tenant_id, identity.project_id) != (graph.tenant_id, graph.project_id):
        raise ApprovalError("reviewer scope mismatch")
    if (command.tenant_id, command.project_id) != (graph.tenant_id, graph.project_id):
        raise ApprovalError("approval scope mismatch")
    if (plan.tenant_id, plan.project_id) != (graph.tenant_id, graph.project_id):
        raise ApprovalError("approval plan scope mismatch")
    if plan.snapshot_hash != graph.snapshot_hash:
        raise ApprovalError("approval plan is stale")
    if plan.policy_version != command.policy_version:
        raise ApprovalError("approval policy does not match current plan policy")
    plan_actions = {decision.node_id: decision.action for decision in plan.decisions}
    if len(plan_actions) != len(plan.decisions) or set(plan_actions) != {
        node.id for node in graph.nodes
    }:
        raise ApprovalError("approval plan is incomplete")
    if identity.actor_id != command.actor_id:
        raise ApprovalError("approval actor does not match authenticated identity")
    if not identity.is_human:
        raise ApprovalError("authorized human identity required")
    if command.decision in (
        ApprovalDecision.APPROVED,
        ApprovalDecision.REJECTED,
        ApprovalDecision.REVOKED,
    ):
        if identity.role != "reviewer":
            raise ApprovalError("authorized human reviewer role required")
    elif command.decision == ApprovalDecision.SUBMITTED:
        if identity.role not in ("producer", "editor", "reviewer"):
            raise ApprovalError("authorized human submitter role required")

    chain = _history_for(history, graph.tenant_id, graph.project_id, command.asset_version_id)
    chains_by_asset: dict[str, list[Approval]] = {}
    for record in history:
        chains_by_asset.setdefault(record.asset_version_id, []).append(record)
    for records in chains_by_asset.values():
        _validate_chain(tuple(records))
    replay = next(
        (
            record
            for record in history
            if record.idempotency_key == command.idempotency_key
            and record.tenant_id == command.tenant_id
            and record.project_id == command.project_id
        ),
        None,
    )
    if replay is not None:
        if _semantic_hash(replay) != _semantic_hash(command):
            raise ApprovalConflict("idempotency key has conflicting approval payload")
        replay_chain = tuple(
            record for record in history if record.asset_version_id == replay.asset_version_id
        )
        return ApprovalResult(history, _latest(replay_chain), True)
    if any(record.id == command.id for record in history):
        raise ApprovalConflict("approval identifier already exists")

    latest = chain[-1] if chain else None
    if command.expected_revision != len(chain):
        raise ApprovalError("stale approval revision")
    if (command.supersedes_id if latest else None) != (latest.id if latest else None):
        raise ApprovalError("approval must supersede the latest decision")
    allowed_next = {
        None: {ApprovalDecision.SUBMITTED},
        ApprovalDecision.SUBMITTED: {ApprovalDecision.APPROVED, ApprovalDecision.REJECTED},
        ApprovalDecision.APPROVED: {ApprovalDecision.REVOKED},
        ApprovalDecision.REJECTED: set(),
        ApprovalDecision.REVOKED: {ApprovalDecision.SUBMITTED},
    }
    if command.decision not in allowed_next[latest.decision if latest else None]:
        raise ApprovalError("invalid approval state transition")
    if latest and command.created_at <= latest.created_at:
        raise ApprovalError("approval transition time must advance")
    if latest and latest.requirement_fingerprint != command.requirement_fingerprint:
        raise ApprovalError("approval chain cannot cross requirement snapshots")
    if latest and latest.policy_version != command.policy_version:
        raise ApprovalError("approval chain cannot cross policy versions")

    if command.decision == ApprovalDecision.REVOKED:
        if latest is None or latest.decision != ApprovalDecision.APPROVED:
            raise ApprovalError("only a current approved decision can be revoked")
        if (command.asset_version, command.requirement_fingerprint, command.policy_version) != (
            latest.asset_version,
            latest.requirement_fingerprint,
            latest.policy_version,
        ):
            raise ApprovalError("revocation must name the approved exact snapshot")
    else:
        try:
            asset = graph.node(command.asset_version_id)
        except ValueError as error:
            raise ApprovalError("approval target is not a current asset version") from error
        if not isinstance(asset, AssetVersion):
            raise ApprovalError("approval target is not an asset version")
        if not isinstance(asset, AssetVersion) or asset.version != command.asset_version:
            raise ApprovalError("approval asset version is not current")
        if asset.policy_version != command.policy_version:
            raise ApprovalError("approval policy does not match asset policy")
        if command.decision == ApprovalDecision.APPROVED and (
            plan_actions.get(asset.id) != Action.KEEP
            or any(
                plan_actions.get(node_id) in (Action.REVIEW, Action.RECOMPUTE, Action.BLOCK)
                for node_id in _ancestors(graph, asset.id)
            )
        ):
            raise ApprovalError(
                "asset has unresolved review, recomputation or blocking dependencies"
            )
        current_requirements = requirement_fingerprint(graph.requirements)
        if command.requirement_fingerprint != current_requirements:
            raise ApprovalError("approval requirement snapshot is stale")
        if asset.requirement_fingerprint != current_requirements:
            raise ApprovalError("asset was derived from a stale requirement snapshot")
        if any(
            req.status != RequirementStatus.CONFIRMED or not req.confirmed_by
            for req in graph.requirements
        ):
            raise ApprovalError("all current requirements require human confirmation")
        for evidence_id in asset.evidence_ids:
            evidence = graph.node(evidence_id)
            if not isinstance(evidence, Evidence) or not evidence.confirmed_by:
                raise ApprovalError("all asset evidence must be human confirmed")
    updated = (*history, command)
    return ApprovalResult(updated, command, False)


def _latest(chain: tuple[Approval, ...]) -> Approval:
    if not chain:
        raise ApprovalError("approval history is empty")
    return chain[-1]


def publication_eligibility(
    graph: Graph,
    asset_version_id: str,
    history: tuple[Approval, ...],
    plan: Plan,
    *,
    policy_version: str,
) -> PublicationDecision:
    """Return eligibility only if every current state check passes; KEEP is not approval."""
    reasons: set[str] = set()
    asset: AssetVersion | None = None
    try:
        candidate = graph.node(asset_version_id)
        if isinstance(candidate, AssetVersion):
            asset = candidate
        else:
            reasons.add("publication target is not an asset version")
    except ValueError:
        reasons.add("asset version is missing from scoped graph")

    if (plan.tenant_id, plan.project_id) != (graph.tenant_id, graph.project_id):
        reasons.add("plan scope mismatch")
    if plan.snapshot_hash != graph.snapshot_hash:
        reasons.add("plan snapshot is stale")
    if plan.policy_version != policy_version:
        reasons.add("plan policy does not match requested policy")
    decisions = {decision.node_id: decision.action for decision in plan.decisions}
    if len(decisions) != len(plan.decisions) or set(decisions) != {node.id for node in graph.nodes}:
        reasons.add("plan decisions do not cover the current graph exactly")
    try:
        scoped = _history_for(history, graph.tenant_id, graph.project_id, asset_version_id)
        chain = _validate_chain(scoped)
        latest = chain[-1] if chain else None
    except ApprovalError as error:
        latest = None
        reasons.add(f"invalid approval history: {error}")

    if asset is not None:
        same_asset = [
            n for n in graph.nodes if isinstance(n, AssetVersion) and n.asset_id == asset.asset_id
        ]
        if len(same_asset) != 1 or same_asset[0].id != asset.id:
            reasons.add("asset version is not the unique current version")
        if asset.id not in decisions:
            reasons.add("plan lacks an asset decision")
        elif decisions[asset.id] != Action.KEEP:
            reasons.add(f"asset plan action is {decisions[asset.id].value}")
        if not graph.requirements or any(
            req.status != RequirementStatus.CONFIRMED or not req.confirmed_by
            for req in graph.requirements
        ):
            reasons.add("current requirements are missing or unconfirmed")
        current_requirements = requirement_fingerprint(graph.requirements)
        if asset.requirement_fingerprint != current_requirements:
            reasons.add("asset requirement snapshot is stale")
        if asset.policy_version != policy_version:
            reasons.add("requested policy does not match asset policy")
        for evidence_id in asset.evidence_ids:
            evidence = graph.node(evidence_id)
            if not isinstance(evidence, Evidence) or not evidence.confirmed_by:
                reasons.add(f"asset evidence is missing or unconfirmed: {evidence_id}")
        for dependency_id in _ancestors(graph, asset.id):
            action = decisions.get(dependency_id)
            if action in (Action.REVIEW, Action.RECOMPUTE, Action.BLOCK):
                reasons.add(f"dependency {dependency_id} is {action.value}")
        if latest is None:
            reasons.add("exact asset version has no human approval")
        elif latest.decision != ApprovalDecision.APPROVED:
            reasons.add(f"latest approval decision is {latest.decision.value}")
        else:
            if (latest.asset_version, latest.requirement_fingerprint, latest.policy_version) != (
                asset.version,
                asset.requirement_fingerprint,
                asset.policy_version,
            ):
                reasons.add("approval does not match exact asset, requirement or policy snapshot")

    return PublicationDecision(
        eligible=not reasons,
        asset_version_id=asset_version_id,
        reasons=tuple(sorted(reasons)),
        approval_id=(
            latest.id
            if not reasons and latest and latest.decision == ApprovalDecision.APPROVED
            else None
        ),
    )


def _validate_chain(chain: tuple[Approval, ...]) -> tuple[Approval, ...]:
    if not isinstance(chain, tuple):
        raise TypeError("approval chain must be immutable")
    previous: Approval | None = None
    for record in chain:
        if previous is None:
            if (
                record.expected_revision != 0
                or record.supersedes_id is not None
                or record.decision != ApprovalDecision.SUBMITTED
            ):
                raise ApprovalError("invalid initial approval chain")
        elif (
            record.expected_revision != previous.expected_revision + 1
            or record.supersedes_id != previous.id
            or record.created_at <= previous.created_at
            or record.requirement_fingerprint != previous.requirement_fingerprint
            or record.policy_version != previous.policy_version
        ):
            raise ApprovalError("broken approval supersession chain")
        elif (
            record.decision
            not in {
                ApprovalDecision.SUBMITTED: {ApprovalDecision.APPROVED, ApprovalDecision.REJECTED},
                ApprovalDecision.APPROVED: {ApprovalDecision.REVOKED},
                ApprovalDecision.REJECTED: set(),
                ApprovalDecision.REVOKED: {ApprovalDecision.SUBMITTED},
            }[previous.decision]
        ):
            raise ApprovalError("invalid approval state transition in history")
        previous = record
    return chain


def approval_state(
    history: tuple[Approval, ...],
    asset_version_id: str,
    *,
    tenant_id: str,
    project_id: str,
) -> ApprovalState:
    """Derive workflow state from the validated immutable decision chain."""
    if not isinstance(history, tuple):
        raise TypeError("approval history must be immutable")
    chain = _validate_chain(_history_for(history, tenant_id, project_id, asset_version_id))
    if not chain:
        return ApprovalState.DRAFT
    return {
        ApprovalDecision.SUBMITTED: ApprovalState.IN_REVIEW,
        ApprovalDecision.APPROVED: ApprovalState.APPROVED,
        ApprovalDecision.REJECTED: ApprovalState.REJECTED,
        ApprovalDecision.REVOKED: ApprovalState.REVOKED,
    }[chain[-1].decision]


def _ancestors(graph: Graph, node_id: str) -> frozenset[str]:
    incoming: dict[str, list[str]] = {node.id: [] for node in graph.nodes}
    for edge in graph.active_edges:
        incoming[edge.dependent_id].append(edge.upstream_id)
    found: set[str] = set()
    pending = list(incoming[node_id])
    while pending:
        upstream = pending.pop()
        if upstream not in found:
            found.add(upstream)
            pending.extend(incoming[upstream])
    return frozenset(found)
