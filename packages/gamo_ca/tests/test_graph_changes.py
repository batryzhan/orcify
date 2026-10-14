from dataclasses import replace
from datetime import timedelta

import pytest
from gamo_ca.events import (
    EventReplayState,
    GraphChangeConflict,
    GraphChangeIdentity,
    GraphChangePayload,
    apply_graph_snapshot_change,
    replay_graph_changes,
)
from gamo_ca.fingerprints import requirement_fingerprint
from gamo_ca.fixtures import NOW, toy_graph
from gamo_ca.graph import Graph, GraphError
from gamo_ca.models import AssetVersion, InputRef, Requirement


def _change(graph: Graph, *, actor_id: str = "producer-1") -> GraphChangePayload:
    instant = max(NOW, graph.as_of + timedelta(seconds=1))
    nodes = tuple(
        replace(
            node,
            version=node.version + 1,
            content="Revised confirmed slogan",
            valid_from=instant,
            confirmed_by=actor_id,
        )
        if isinstance(node, Requirement) and node.id == "slogan"
        else node
        for node in graph.nodes
    )
    updated = Graph(graph.tenant_id, graph.project_id, instant, nodes, graph.edges)
    return GraphChangePayload(
        event_id="graph-change-1",
        tenant_id=graph.tenant_id,
        project_id=graph.project_id,
        actor_id=actor_id,
        occurred_at=instant,
        expected_revision=0,
        expected_snapshot_hash=graph.snapshot_hash,
        snapshot=updated,
    )


def _identity(
    graph: Graph, *, actor_id: str = "producer-1", role: str = "producer"
) -> GraphChangeIdentity:
    return GraphChangeIdentity(actor_id, graph.tenant_id, graph.project_id, role, True)


def test_graph_change_advances_full_snapshot_and_replay_pointers() -> None:
    graph = toy_graph()
    command = _change(graph)
    result = apply_graph_snapshot_change(
        EventReplayState.from_graph(graph), graph, command, _identity(graph)
    )
    assert result.snapshot == command.snapshot
    assert result.snapshot.snapshot_hash != graph.snapshot_hash
    assert result.state.revision == 1
    assert result.state.current("slogan").version == 2
    assert result.state.snapshot_hash == result.receipt.snapshot_hash


def test_graph_change_replay_reconstructs_same_graph_deterministically() -> None:
    graph = toy_graph()
    first = _change(graph)
    replayed = replay_graph_changes(graph, (first,))
    assert replayed == first.snapshot
    assert replayed.snapshot_hash == first.snapshot.snapshot_hash
    assert replay_graph_changes(graph, (first,)) == replayed


def test_graph_change_rejects_stale_scope_and_unverified_requirement_confirmation() -> None:
    graph = toy_graph()
    command = _change(graph)
    state = EventReplayState.from_graph(graph)
    with pytest.raises(GraphChangeConflict, match="stale"):
        apply_graph_snapshot_change(
            state,
            graph,
            replace(command, expected_snapshot_hash="0" * 64),
            _identity(graph),
        )
    with pytest.raises(GraphChangeConflict, match="scope"):
        apply_graph_snapshot_change(
            state,
            graph,
            command,
            GraphChangeIdentity("producer-1", "foreign-tenant", graph.project_id, "producer", True),
        )
    wrong_requirement = next(
        node for node in command.snapshot.nodes if isinstance(node, Requirement)
    )
    unverified_snapshot = Graph(
        graph.tenant_id,
        graph.project_id,
        command.snapshot.as_of,
        tuple(
            replace(node, confirmed_by="somebody-else")
            if isinstance(node, Requirement) and node.id == wrong_requirement.id
            else node
            for node in command.snapshot.nodes
        ),
        command.snapshot.edges,
    )
    with pytest.raises(GraphChangeConflict, match="confirming actor"):
        apply_graph_snapshot_change(
            state,
            graph,
            replace(command, snapshot=unverified_snapshot),
            _identity(graph),
        )


def test_graph_change_requires_all_entity_versions_and_exact_provenance() -> None:
    graph = toy_graph()
    command = _change(graph)
    state = EventReplayState.from_graph(graph)
    with pytest.raises(GraphChangeConflict, match="incomplete"):
        apply_graph_snapshot_change(
            state,
            graph,
            replace(
                command,
                snapshot=replace(
                    command.snapshot,
                    nodes=tuple(node for node in command.snapshot.nodes if node.id != "note"),
                ),
            ),
            _identity(graph),
        )

    asset = next(node for node in graph.nodes if isinstance(node, AssetVersion))
    bad_asset = replace(
        asset,
        version=asset.version + 1,
        valid_from=command.occurred_at,
        inputs=(InputRef("slogan", 99, "a" * 64),),
    )
    nodes = tuple(bad_asset if node.id == asset.id else node for node in graph.nodes)
    with pytest.raises(GraphChangeConflict, match="provenance"):
        bad_graph = Graph(
            graph.tenant_id, graph.project_id, command.occurred_at, nodes, graph.edges
        )
        apply_graph_snapshot_change(
            state,
            graph,
            replace(command, snapshot=bad_graph),
            _identity(graph),
        )


def test_graph_change_rejects_cycles_and_wrong_authorization_role() -> None:
    graph = toy_graph()
    command = _change(graph)
    with pytest.raises(GraphError, match="cycle"):
        Graph(
            graph.tenant_id,
            graph.project_id,
            command.occurred_at,
            command.snapshot.nodes,
            (
                *graph.edges,
                replace(graph.edges[0], id="cycle-edge", upstream_id="copy", dependent_id="slogan"),
            ),
        )
    with pytest.raises(GraphChangeConflict, match="role"):
        apply_graph_snapshot_change(
            EventReplayState.from_graph(graph), graph, command, _identity(graph, role="researcher")
        )


def test_changed_asset_requires_current_confirmed_requirement_snapshot() -> None:
    graph = toy_graph()
    command = _change(graph)
    asset = next(node for node in command.snapshot.nodes if isinstance(node, AssetVersion))
    requirement = next(node for node in command.snapshot.nodes if isinstance(node, Requirement))
    with pytest.raises(GraphChangeConflict, match="confirmed requirements"):
        unconfirmed = replace(
            requirement, status=type(requirement.status).UNCONFIRMED, confirmed_by=None
        )
        nodes = tuple(
            unconfirmed if node.id == requirement.id else node for node in command.snapshot.nodes
        )
        updated_asset = replace(
            asset,
            version=asset.version + 1,
            valid_from=command.occurred_at,
            requirement_fingerprint=requirement_fingerprint((unconfirmed,)),
        )
        nodes = tuple(updated_asset if node.id == asset.id else node for node in nodes)
        new_graph = Graph(
            graph.tenant_id, graph.project_id, command.occurred_at, nodes, command.snapshot.edges
        )
        apply_graph_snapshot_change(
            EventReplayState.from_graph(graph),
            graph,
            replace(command, snapshot=new_graph),
            _identity(graph),
        )
