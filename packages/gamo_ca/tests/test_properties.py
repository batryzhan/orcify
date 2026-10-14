from dataclasses import replace

import pytest
from gamo_ca.approvals import (
    ApprovalError,
    ReviewerIdentity,
    apply_approval,
    publication_eligibility,
)
from gamo_ca.events import EventReplayState, apply_change_event
from gamo_ca.fingerprints import requirement_fingerprint
from gamo_ca.fixtures import change_event, toy_graph
from gamo_ca.graph import Graph
from gamo_ca.models import Action, Approval, ApprovalDecision, DependencyType, InputRef, Task
from gamo_ca.planner import Policy, plan_change
from hypothesis import given
from hypothesis import strategies as st


@given(st.sets(st.tuples(st.integers(0, 7), st.integers(1, 8)), max_size=30))
def test_hard_reachability_never_silently_reuses(random_pairs: set[tuple[int, int]]) -> None:
    base = toy_graph()
    prototype = base.node("note")
    pairs = sorted((a, b) for a, b in random_pairs if a < b)
    raw = tuple(replace(prototype, id=f"n{i}") for i in range(9))
    nodes = tuple(
        replace(
            n,
            inputs=tuple(
                InputRef(raw[a].id, raw[a].version, raw[a].content_hash) for a, b in pairs if b == i
            ),
        )
        for i, n in enumerate(raw)
    )
    evidence = base.node("evidence")
    edges = tuple(
        replace(
            base.edges[0],
            id=f"edge-{a}-{b}",
            upstream_id=f"n{a}",
            dependent_id=f"n{b}",
            strength=DependencyType.HARD,
        )
        for a, b in pairs
    )
    graph = Graph(base.tenant_id, base.project_id, base.as_of, (*nodes, evidence), edges)
    plan = plan_change(graph, change_event("n0", graph), Policy())
    # Independent fixed-point oracle, distinct from planner's topological walk.
    reachable = {0}
    while True:
        expanded = reachable | {b for a, b in pairs if a in reachable}
        if expanded == reachable:
            break
        reachable = expanded
    for i in range(1, 9):
        assert plan.decision(f"n{i}").action == (
            Action.RECOMPUTE if i in reachable else Action.KEEP
        )
    position = {node_id: index for index, node_id in enumerate(plan.execution_order)}
    for a, b in pairs:
        if f"n{a}" in position and f"n{b}" in position:
            assert position[f"n{a}"] < position[f"n{b}"]


def test_missing_task_input_is_recomputed_without_fabricating_provenance() -> None:
    base = toy_graph()
    task = Task(
        id="task",
        tenant_id=base.tenant_id,
        project_id=base.project_id,
        created_at=base.as_of,
        valid_from=base.as_of,
        version=1,
        content="Unexecuted draft task",
        task_type="copy",
    )
    edge = replace(base.edges[0], id="slogan-task", dependent_id=task.id)
    graph = replace(base, nodes=(*base.nodes, task), edges=(*base.edges, edge))
    plan = plan_change(graph, change_event("note", graph), Policy())
    assert plan.decision(task.id).action == Action.RECOMPUTE


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12))
def test_tenant_boundary_property_never_accepts_a_different_reviewer_scope(scope: str) -> None:
    base = toy_graph()
    if scope == base.tenant_id:
        return
    asset = base.node("copy")
    command = Approval(
        id="approval",
        tenant_id=base.tenant_id,
        project_id=base.project_id,
        created_at=base.as_of,
        asset_version_id=asset.id,
        asset_version=asset.version,
        requirement_fingerprint=requirement_fingerprint(base.requirements),
        actor_id="reviewer",
        decision=ApprovalDecision.APPROVED,
        policy_version=asset.policy_version,
        idempotency_key="key",
        expected_revision=0,
    )
    identity = ReviewerIdentity("reviewer", scope, base.project_id, "reviewer", True)
    with pytest.raises(ApprovalError):
        apply_approval(
            (), command, identity, base, plan_change(base, change_event("note", base), Policy())
        )


@given(st.integers(min_value=2, max_value=100))
def test_exact_version_approval_property_never_transfers(version: int) -> None:
    base = toy_graph()
    asset = base.node("copy")
    approval = Approval(
        id="approval",
        tenant_id=base.tenant_id,
        project_id=base.project_id,
        created_at=base.as_of,
        asset_version_id=asset.id,
        asset_version=asset.version,
        requirement_fingerprint=requirement_fingerprint(base.requirements),
        actor_id="reviewer",
        decision=ApprovalDecision.APPROVED,
        policy_version=asset.policy_version,
        idempotency_key="key",
        expected_revision=0,
    )
    base_plan = plan_change(base, change_event("note", base), Policy())
    current = replace(asset, version=version)
    graph = replace(
        base, nodes=tuple(current if node.id == asset.id else node for node in base.nodes)
    )
    plan = plan_change(graph, change_event("note", graph), Policy())
    identity = ReviewerIdentity(
        actor_id="reviewer",
        tenant_id=base.tenant_id,
        project_id=base.project_id,
        role="reviewer",
        is_human=True,
    )
    submission = replace(
        approval,
        id="submission",
        decision=ApprovalDecision.SUBMITTED,
        idempotency_key="submission-key",
        created_at=base.as_of,
    )
    submitted = apply_approval((), submission, identity, base, base_plan)
    approval = replace(
        approval,
        expected_revision=1,
        supersedes_id=submission.id,
        created_at=base.as_of.replace(second=2),
    )
    approved = apply_approval(submitted.history, approval, identity, base, base_plan)
    outcome = publication_eligibility(
        graph, current.id, approved.history, plan, policy_version=asset.policy_version
    )
    assert not outcome.eligible
    assert outcome.approval_id is None


@given(st.sampled_from(tuple(Action)))
def test_keep_or_any_other_plan_action_never_substitutes_for_approval(
    action: Action,
) -> None:
    graph = toy_graph()
    plan = plan_change(graph, change_event("note", graph), Policy())
    altered = replace(
        plan,
        decisions=tuple(
            replace(decision, action=action) if decision.node_id == "copy" else decision
            for decision in plan.decisions
        ),
    )
    result = publication_eligibility(graph, "copy", (), altered, policy_version="v1")
    assert not result.eligible
    assert result.approval_id is None
    assert any("approval" in reason for reason in result.reasons)


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10))
def test_unknown_soft_relevance_property_always_requests_review(changed_field: str) -> None:
    graph = toy_graph()
    event = replace(change_event(graph=graph), changed_fields=(changed_field,))
    plan = plan_change(graph, event, Policy())
    assert plan.decision("visual").action == Action.REVIEW
    assert plan.decision("visual_export").action == Action.REVIEW


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=10))
def test_event_replay_property_returns_identical_receipt_for_duplicate_ids(
    event_suffix: str,
) -> None:
    graph = toy_graph()
    state = EventReplayState.from_graph(graph)
    event = replace(change_event(graph=graph), id=f"event-{event_suffix}")
    first = apply_change_event(state, event)
    replay = apply_change_event(first.state, event)
    assert replay.replayed
    assert replay.state == first.state
    assert replay.receipt == first.receipt
