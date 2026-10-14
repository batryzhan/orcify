from dataclasses import replace

import pytest
from gamo_ca.fixtures import toy_graph
from gamo_ca.graph import Graph, GraphError
from gamo_ca.models import DependencyEdge, DependencyType
from hypothesis import given
from hypothesis import strategies as st


def test_disconnected_graph_and_stable_topological_order() -> None:
    graph = toy_graph()
    order = graph.topological_order()
    assert set(order) == {node.id for node in graph.nodes}
    assert order.index("copy") < order.index("storyboard")
    reordered = replace(
        graph, nodes=tuple(reversed(graph.nodes)), edges=tuple(reversed(graph.edges))
    )
    assert reordered.topological_order() == order
    assert reordered.snapshot_hash == graph.snapshot_hash
    assert Graph("tenant", "project", graph.as_of, (), ()).topological_order() == ()


@pytest.mark.parametrize("scope", ["tenant_id", "project_id"])
def test_cross_scope_nodes_and_edges_are_rejected(scope: str) -> None:
    graph = toy_graph()
    node = (
        replace(graph.nodes[0], tenant_id="other")
        if scope == "tenant_id"
        else replace(graph.nodes[0], project_id="other")
    )
    with pytest.raises(GraphError, match="scope"):
        replace(graph, nodes=(node, *graph.nodes[1:]))
    edge = (
        replace(graph.edges[0], tenant_id="other")
        if scope == "tenant_id"
        else replace(graph.edges[0], project_id="other")
    )
    with pytest.raises(GraphError, match="scope"):
        replace(graph, edges=(edge, *graph.edges[1:]))


def test_cycles_dangling_edges_and_duplicate_ids_are_rejected() -> None:
    graph = toy_graph()
    edge = replace(graph.edges[0], id="cycle", upstream_id="storyboard", dependent_id="slogan")
    with pytest.raises(GraphError, match="cycle"):
        replace(graph, edges=(*graph.edges, edge))
    with pytest.raises(GraphError, match="endpoint"):
        replace(graph, edges=(replace(edge, dependent_id="missing"),))
    with pytest.raises(GraphError, match="duplicate"):
        replace(graph, nodes=(*graph.nodes, graph.nodes[0]))


@given(st.integers(min_value=1, max_value=30))
def test_random_chain_respects_every_dependency(size: int) -> None:
    graph = toy_graph()
    prototype = graph.node("note")
    nodes = tuple(replace(prototype, id=f"n{i}") for i in range(size))
    edges = tuple(
        DependencyEdge(
            id=f"e{i}",
            tenant_id=graph.tenant_id,
            project_id=graph.project_id,
            created_at=graph.as_of,
            valid_from=graph.as_of,
            upstream_id=f"n{i}",
            dependent_id=f"n{i + 1}",
            strength=DependencyType.HARD,
        )
        for i in range(size - 1)
    )
    order = Graph(graph.tenant_id, graph.project_id, graph.as_of, nodes, edges).topological_order()
    assert order == tuple(f"n{i}" for i in range(size))
