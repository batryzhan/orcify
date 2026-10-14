"""Deterministic plan preview. Does not execute, authorize or approve anything."""

from dataclasses import dataclass
from typing import Literal

from gamo_ca.fingerprints import fingerprint, input_fingerprint
from gamo_ca.graph import Graph
from gamo_ca.models import (
    Action,
    AssetVersion,
    ChangeEvent,
    DependencyEdge,
    DependencyType,
    Evidence,
    Requirement,
    RequirementStatus,
    require_id,
)


class PlanningError(ValueError):
    """Change cannot be planned safely against supplied snapshot."""


@dataclass(frozen=True, slots=True)
class Policy:
    version: str = "v1"

    def __post_init__(self) -> None:
        require_id(self.version)


@dataclass(frozen=True, slots=True)
class Decision:
    node_id: str
    action: Action
    reasons: tuple[str, ...]
    input_fingerprint: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EdgeTrace:
    edge_id: str
    upstream_id: str
    dependent_id: str
    strength: DependencyType
    action: Action
    reason: str


@dataclass(frozen=True, slots=True)
class Plan:
    event_id: str
    tenant_id: str
    project_id: str
    snapshot_hash: str
    policy_version: str
    decisions: tuple[Decision, ...]
    traces: tuple[EdgeTrace, ...]
    execution_order: tuple[str, ...]
    non_publishable_ids: tuple[str, ...]
    expected_cost_usd: float | None
    expected_latency_s: float | None
    estimate_status: Literal["SIMULATED"] = "SIMULATED"
    plan_hash: str = ""

    def decision(self, node_id: str) -> Decision:
        return next(d for d in self.decisions if d.node_id == node_id)


_PRIORITY = {Action.KEEP: 0, Action.RECOMPUTE: 1, Action.REVIEW: 2, Action.BLOCK: 3}


def plan_change(graph: Graph, event: ChangeEvent, policy: Policy) -> Plan:
    if (event.tenant_id, event.project_id) != (graph.tenant_id, graph.project_id):
        raise PlanningError("event scope differs from graph")
    if event.expected_snapshot_hash != graph.snapshot_hash:
        raise PlanningError("stale snapshot")
    if event.occurred_at != graph.as_of:
        raise PlanningError("event time requires matching as-of snapshot")
    by_id = {n.id: n for n in graph.nodes}
    source = by_id.get(event.source_id)
    if not isinstance(source, Evidence) or not source.confirmed_by:
        raise PlanningError("change source is missing or unconfirmed")
    target = by_id.get(event.target_id)
    if (
        target is None
        or target.version != event.old_version
        or target.content_hash != event.old_hash
    ):
        raise PlanningError("target version/hash precondition failed")
    if isinstance(target, Requirement) and target.status != RequirementStatus.CONFIRMED:
        raise PlanningError("change target is an unconfirmed requirement")

    state = {node.id: Action.KEEP for node in graph.nodes}
    reasons: dict[str, set[str]] = {node.id: set() for node in graph.nodes}
    traces: list[EdgeTrace] = []
    changed: set[str] = {target.id}
    outgoing: dict[str, list[DependencyEdge]] = {node.id: [] for node in graph.nodes}
    incoming: dict[str, list[DependencyEdge]] = {node.id: [] for node in graph.nodes}
    for edge in graph.active_edges:
        outgoing[edge.upstream_id].append(edge)
        incoming[edge.dependent_id].append(edge)

    def mark(node_id: str, action: Action, reason: str) -> None:
        if _PRIORITY[action] > _PRIORITY[state[node_id]]:
            state[node_id] = action
        reasons[node_id].add(reason)

    # Existing stale inputs must not be concealed by an unrelated event.
    for node in graph.nodes:
        refs = {ref.source_id: ref for ref in node.inputs}
        for edge in incoming[node.id]:
            upstream = by_id[edge.upstream_id]
            consumed = refs.get(upstream.id)
            stale = consumed is None or (consumed.version, consumed.content_hash) != (
                upstream.version,
                upstream.content_hash,
            )
            if edge.strength == DependencyType.HARD:
                if stale:
                    mark(node.id, Action.RECOMPUTE, f"stale/missing HARD input: {edge.id}")
                if (
                    isinstance(upstream, Requirement)
                    and upstream.status != RequirementStatus.CONFIRMED
                ):
                    mark(node.id, Action.BLOCK, f"unconfirmed mandatory requirement: {upstream.id}")
            elif edge.strength == DependencyType.SOFT and stale:
                mark(node.id, Action.REVIEW, f"stale/missing SOFT input: {edge.id}")
        if isinstance(node, AssetVersion):
            for evidence_id in node.evidence_ids:
                evidence = by_id[evidence_id]
                if not isinstance(evidence, Evidence) or not evidence.confirmed_by:
                    mark(node.id, Action.BLOCK, f"unconfirmed evidence: {evidence_id}")

    for node_id in graph.topological_order():
        upstream_action = state[node_id]
        impacted = node_id in changed or upstream_action != Action.KEEP
        for edge in outgoing[node_id]:
            action = Action.KEEP
            reason = "upstream unchanged; retain"
            if impacted:
                if edge.strength == DependencyType.INFORMATIONAL:
                    reason = "informational edge; does not require recomputation"
                elif upstream_action == Action.BLOCK:
                    action, reason = Action.BLOCK, "upstream blocked; dependent cannot proceed"
                elif edge.strength == DependencyType.HARD:
                    if upstream_action == Action.REVIEW:
                        action, reason = Action.REVIEW, "HARD input pending human review"
                    else:
                        action, reason = Action.RECOMPUTE, "changed HARD input/version"
                elif upstream_action == Action.REVIEW or not edge.relevant_fields:
                    action, reason = Action.REVIEW, "SOFT impact unknown; human review required"
                elif node_id != target.id:
                    action, reason = (
                        Action.REVIEW,
                        "derived change fields unknown; SOFT review required",
                    )
                elif set(edge.relevant_fields).intersection(event.changed_fields):
                    action, reason = Action.RECOMPUTE, "SOFT relevant field changed"
                else:
                    reason = "SOFT fields explicitly disjoint from changed fields"
            mark(edge.dependent_id, action, f"{edge.id}: {reason}")
            traces.append(
                EdgeTrace(edge.id, node_id, edge.dependent_id, edge.strength, action, reason)
            )

    decisions = tuple(
        Decision(
            node.id,
            state[node.id],
            tuple(sorted(reasons[node.id] or {"no affected dependency"})),
            input_fingerprint(
                node.inputs,
                node.provider,
                node.model_version,
                node.prompt_version,
                node.policy_version,
                tenant_id=graph.tenant_id,
                project_id=graph.project_id,
            ),
            tuple(sorted(node.evidence_ids)),
        )
        for node in sorted(graph.nodes, key=lambda n: n.id)
    )
    order = tuple(n for n in graph.topological_order() if state[n] == Action.RECOMPUTE)
    costs = [by_id[n].estimated_cost_usd for n in order]
    latencies = [by_id[n].estimated_latency_s for n in order]
    payload = {
        "event_id": event.id,
        "event_hash": fingerprint(event),
        "tenant_id": graph.tenant_id,
        "project_id": graph.project_id,
        "snapshot_hash": graph.snapshot_hash,
        "policy_version": policy.version,
        "decisions": decisions,
        "traces": tuple(sorted(traces, key=lambda t: t.edge_id)),
        "execution_order": order,
        "non_publishable_ids": tuple(
            sorted(
                n.id
                for n in graph.nodes
                if isinstance(n, AssetVersion) and state[n.id] != Action.KEEP
            )
        ),
        "expected_cost_usd": None
        if any(c is None for c in costs)
        else sum(c for c in costs if c is not None),
        "expected_latency_s": None
        if any(t is None for t in latencies)
        else sum(t for t in latencies if t is not None),
        "estimate_status": "SIMULATED",
    }
    return Plan(
        event_id=event.id,
        tenant_id=graph.tenant_id,
        project_id=graph.project_id,
        snapshot_hash=graph.snapshot_hash,
        policy_version=policy.version,
        decisions=decisions,
        traces=tuple(sorted(traces, key=lambda t: t.edge_id)),
        execution_order=order,
        non_publishable_ids=tuple(
            sorted(
                n.id
                for n in graph.nodes
                if isinstance(n, AssetVersion) and state[n.id] != Action.KEEP
            )
        ),
        expected_cost_usd=None
        if any(c is None for c in costs)
        else sum(c for c in costs if c is not None),
        expected_latency_s=None
        if any(t is None for t in latencies)
        else sum(t for t in latencies if t is not None),
        plan_hash=fingerprint(payload),
    )
