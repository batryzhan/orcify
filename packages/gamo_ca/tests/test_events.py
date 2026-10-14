from dataclasses import replace

import pytest
from gamo_ca.events import (
    EventConflict,
    EventOutOfOrder,
    EventReplayState,
    EventStaleSnapshot,
    apply_change_event,
)
from gamo_ca.fingerprints import fingerprint
from gamo_ca.fixtures import NOW, change_event, toy_graph
from gamo_ca.models import Evidence
from hypothesis import given
from hypothesis import strategies as st


def test_event_replay_is_deterministic_and_does_not_advance_revision() -> None:
    graph = toy_graph()
    state = EventReplayState.from_graph(graph)
    event = change_event(graph=graph)
    first = apply_change_event(state, event)
    replay = apply_change_event(first.state, event)
    assert replay.replayed
    assert replay.receipt == first.receipt
    assert replay.state == first.state
    assert replay.state.revision == 1
    assert replay.state.current("slogan").version == 2


def test_same_event_id_with_different_payload_and_stale_snapshot_conflict() -> None:
    graph = toy_graph()
    state = EventReplayState.from_graph(graph)
    event = change_event(graph=graph)
    first = apply_change_event(state, event)
    with pytest.raises(EventConflict, match="event ID"):
        apply_change_event(first.state, replace(event, actor_id="other-actor"))
    second = replace(
        change_event("note", graph),
        id="change-note-next",
        expected_snapshot_hash=state.snapshot_hash,
    )
    with pytest.raises(EventStaleSnapshot):
        apply_change_event(first.state, second)


def test_out_of_order_version_or_timestamp_is_rejected() -> None:
    graph = toy_graph()
    state = EventReplayState.from_graph(graph)
    event = change_event(graph=graph)
    first = apply_change_event(state, event)
    duplicate_version = replace(
        event,
        id="next",
        old_version=1,
        new_version=2,
        expected_snapshot_hash=first.state.snapshot_hash,
    )
    with pytest.raises(EventOutOfOrder):
        apply_change_event(first.state, duplicate_version)
    next_event = replace(
        change_event("note", graph),
        id="next",
        expected_snapshot_hash=first.state.snapshot_hash,
        occurred_at=NOW.replace(year=2026, month=10, day=13),
    )
    with pytest.raises(EventOutOfOrder):
        apply_change_event(first.state, next_event)


def test_tenant_project_and_unconfirmed_change_source_are_rejected() -> None:
    graph = toy_graph()
    state = EventReplayState.from_graph(graph)
    event = change_event(graph=graph)
    with pytest.raises(EventConflict, match="scope"):
        apply_change_event(state, replace(event, tenant_id="another-tenant"))
    with pytest.raises(EventConflict, match="scope"):
        apply_change_event(state, replace(event, project_id="another-project"))
    evidence = graph.node("evidence")
    assert isinstance(evidence, Evidence)
    changed = replace(
        graph,
        nodes=tuple(
            replace(n, confirmed_by=None) if isinstance(n, Evidence) and n.id == evidence.id else n
            for n in graph.nodes
        ),
    )
    with pytest.raises(EventConflict, match="source"):
        apply_change_event(EventReplayState.from_graph(changed), change_event(graph=changed))


@given(st.integers(min_value=1, max_value=20))
def test_duplicate_event_replay_preserves_original_state(revision: int) -> None:
    graph = toy_graph()
    state = EventReplayState.from_graph(graph)
    event = replace(change_event(graph=graph), id=f"event-{revision}")
    first = apply_change_event(state, event)
    replay = apply_change_event(first.state, event)
    assert replay.state == first.state
    assert replay.state.revision == 1
    assert replay.receipt.payload_hash == fingerprint(event)
