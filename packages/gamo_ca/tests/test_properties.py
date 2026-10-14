from dataclasses import replace

from gamo_ca.fixtures import change_event, toy_graph
from gamo_ca.graph import Graph
from gamo_ca.models import Action, DependencyType, InputRef, Task
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
