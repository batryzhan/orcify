from dataclasses import replace
from datetime import timedelta

import pytest
from gamo_ca.fixtures import change_event, toy_graph
from gamo_ca.graph import GraphError
from gamo_ca.models import Action, DependencyType, Requirement, RequirementStatus
from gamo_ca.planner import PlanningError, Policy, plan_change


def actions() -> dict[str, Action]:
    return {
        d.node_id: d.action for d in plan_change(toy_graph(), change_event(), Policy()).decisions
    }


def test_hard_change_and_uncertain_soft_block_stale_outputs() -> None:
    result = actions()
    assert result["copy"] == Action.RECOMPUTE
    assert result["storyboard"] == Action.RECOMPUTE
    assert result["visual"] == Action.REVIEW
    assert result["visual_export"] == Action.REVIEW
    assert result["logo"] == Action.KEEP
    plan = plan_change(toy_graph(), change_event(), Policy())
    assert plan.execution_order == ("copy", "storyboard")
    assert set(plan.non_publishable_ids) == {"copy", "storyboard", "visual", "visual_export"}
    assert all(trace.reason for trace in plan.traces)
    assert set(t.edge_id for t in plan.traces) >= {"slogan-copy", "slogan-visual", "slogan-logo"}


def test_unrelated_note_is_retained_and_plan_is_deterministic() -> None:
    graph = toy_graph()
    event = change_event("note")
    plan = plan_change(graph, event, Policy())
    assert all(d.action == Action.KEEP for d in plan.decisions)
    assert plan.execution_order == ()
    assert plan == plan_change(graph, event, Policy())
    reordered = replace(
        graph, nodes=tuple(reversed(graph.nodes)), edges=tuple(reversed(graph.edges))
    )
    assert plan == plan_change(reordered, event, Policy())
    assert plan.plan_hash != plan_change(graph, event, Policy(version="v2")).plan_hash


def test_soft_relevance_is_explicit_and_informational_never_recomputes() -> None:
    graph = toy_graph()
    edges = tuple(
        replace(e, relevant_fields=("slogan",)) if e.id == "slogan-visual" else e
        for e in graph.edges
    )
    changed = replace(graph, edges=edges)
    plan = plan_change(changed, change_event(graph=changed), Policy())
    assert plan.decision("visual").action == Action.RECOMPUTE
    assert plan.decision("visual_export").action == Action.RECOMPUTE
    edges = tuple(
        replace(e, relevant_fields=("brand_color",)) if e.id == "slogan-visual" else e
        for e in graph.edges
    )
    changed = replace(graph, edges=edges)
    plan = plan_change(changed, change_event(graph=changed), Policy())
    assert plan.decision("visual").action == Action.KEEP
    assert plan.decision("logo").action == Action.KEEP


@pytest.mark.parametrize("field", ["tenant_id", "project_id"])
def test_cross_scope_events_are_rejected(field: str) -> None:
    event = (
        replace(change_event(), tenant_id="other")
        if field == "tenant_id"
        else replace(change_event(), project_id="other")
    )
    with pytest.raises(PlanningError, match="scope"):
        plan_change(toy_graph(), event, Policy())


def test_stale_snapshot_missing_verified_source_and_future_events_are_rejected() -> None:
    graph = toy_graph()
    with pytest.raises(PlanningError, match="snapshot"):
        plan_change(graph, replace(change_event(), expected_snapshot_hash="0" * 64), Policy())
    with pytest.raises(PlanningError, match="source"):
        plan_change(graph, replace(change_event(), source_id="missing"), Policy())
    with pytest.raises(PlanningError, match="version"):
        plan_change(graph, replace(change_event(), old_version=2, new_version=3), Policy())
    with pytest.raises(PlanningError, match="time"):
        plan_change(
            graph, replace(change_event(), occurred_at=graph.as_of + timedelta(days=1)), Policy()
        )


def test_stale_consumed_hard_input_cannot_be_hidden_by_unrelated_event() -> None:
    graph = toy_graph()
    copy = graph.node("copy")
    bad_input = replace(copy.inputs[0], version=9)
    nodes = tuple(replace(n, inputs=(bad_input,)) if n.id == "copy" else n for n in graph.nodes)
    graph = replace(graph, nodes=nodes)
    plan = plan_change(graph, change_event("note", graph), Policy())
    assert plan.decision("copy").action == Action.RECOMPUTE
    assert plan.decision("storyboard").action == Action.RECOMPUTE


def test_expired_hard_edge_is_not_traversed() -> None:
    graph = toy_graph()
    edges = tuple(
        replace(e, valid_to=graph.as_of) if e.upstream_id == "slogan" else e for e in graph.edges
    )
    graph = replace(graph, edges=edges)
    plan = plan_change(graph, change_event(graph=graph), Policy())
    assert plan.decision("copy").action == Action.KEEP


def test_unknown_cost_is_null_not_fake_measurement() -> None:
    graph = toy_graph()
    nodes = tuple(replace(n, estimated_cost_usd=None) if n.id == "copy" else n for n in graph.nodes)
    graph = replace(graph, nodes=nodes)
    plan = plan_change(graph, change_event(graph=graph), Policy())
    assert plan.expected_cost_usd is None
    assert plan.estimate_status == "SIMULATED"


def test_missing_inputs_and_unconfirmed_requirements_fail_closed() -> None:
    graph = toy_graph()
    with pytest.raises(ValueError, match="provenance"):
        replace(graph.node("copy"), inputs=())
    nodes = tuple(
        replace(n, status=RequirementStatus.UNCONFIRMED, confirmed_by=None)
        if isinstance(n, Requirement)
        else n
        for n in graph.nodes
    )
    graph = replace(graph, nodes=nodes)
    plan = plan_change(graph, change_event("note", graph), Policy())
    assert plan.decision("copy").action == Action.BLOCK
    assert plan.decision("storyboard").action == Action.BLOCK
    with pytest.raises(GraphError):
        replace(graph, edges=(*graph.edges, replace(graph.edges[0], id="foreign", tenant_id="x")))
    assert DependencyType.HARD.value == "HARD"


def test_review_prevents_execution_even_with_another_hard_change() -> None:
    graph = toy_graph()
    extra = replace(
        graph.edges[0], id="visual-storyboard", upstream_id="visual", dependent_id="storyboard"
    )
    storyboard = graph.node("storyboard")
    visual = graph.node("visual")
    from gamo_ca.models import InputRef

    nodes = tuple(
        replace(
            n, inputs=(*storyboard.inputs, InputRef(visual.id, visual.version, visual.content_hash))
        )
        if n.id == "storyboard"
        else n
        for n in graph.nodes
    )
    graph = replace(graph, nodes=nodes, edges=(*graph.edges, extra))
    plan = plan_change(graph, change_event(graph=graph), Policy())
    assert plan.decision("storyboard").action == Action.REVIEW
    assert "storyboard" not in plan.execution_order


def test_stale_soft_input_requires_review_on_unrelated_change() -> None:
    graph = toy_graph()
    visual = graph.node("visual")
    nodes = tuple(
        replace(n, inputs=(replace(visual.inputs[0], version=8),)) if n.id == "visual" else n
        for n in graph.nodes
    )
    graph = replace(graph, nodes=nodes)
    plan = plan_change(graph, change_event("note", graph), Policy())
    assert plan.decision("visual").action == Action.REVIEW
    assert plan.decision("visual_export").action == Action.REVIEW


def test_unconfirmed_change_target_is_rejected() -> None:
    graph = toy_graph()
    nodes = tuple(
        replace(n, status=RequirementStatus.UNCONFIRMED, confirmed_by=None)
        if isinstance(n, Requirement)
        else n
        for n in graph.nodes
    )
    graph = replace(graph, nodes=nodes)
    with pytest.raises(PlanningError, match="unconfirmed"):
        plan_change(graph, change_event(graph=graph), Policy())
