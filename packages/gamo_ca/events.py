"""Deterministic in-memory event reducer; PostgreSQL remains the durable authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from gamo_ca.fingerprints import canonical, fingerprint, requirement_fingerprint
from gamo_ca.graph import Graph
from gamo_ca.models import (
    AssetVersion,
    ChangeEvent,
    Evidence,
    Requirement,
    RequirementStatus,
    require_hash,
    require_id,
    require_time,
)


class EventConflict(ValueError):
    """Event ID or scope conflicts with current replay state."""


class EventStaleSnapshot(EventConflict):
    """Expected projection hash no longer matches current state."""


class EventOutOfOrder(EventConflict):
    """Event timestamp or target version is behind current state."""


class GraphChangeConflict(EventConflict):
    """A full graph snapshot change is stale, incomplete, or unsafe."""


@dataclass(frozen=True, slots=True)
class GraphChangePayload:
    """Versioned, self-contained authoritative snapshot change event."""

    event_id: str
    tenant_id: str
    project_id: str
    actor_id: str
    occurred_at: datetime
    expected_revision: int
    expected_snapshot_hash: str
    snapshot: Graph
    schema_version: int = 1

    def __post_init__(self) -> None:
        for value in (self.event_id, self.tenant_id, self.project_id, self.actor_id):
            require_id(value)
        require_time(self.occurred_at)
        require_hash(self.expected_snapshot_hash)
        if type(self.expected_revision) is not int or self.expected_revision < 0:
            raise ValueError("graph change revision must be nonnegative")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unsupported graph change schema version")
        if not isinstance(self.snapshot, Graph):
            raise TypeError("graph change must contain a typed complete Graph snapshot")
        if (self.tenant_id, self.project_id) != (self.snapshot.tenant_id, self.snapshot.project_id):
            raise ValueError("graph change scope differs from its snapshot")


@dataclass(frozen=True, slots=True)
class GraphChangeIdentity:
    """Server-authorized project writer; request claims must never instantiate this."""

    actor_id: str
    tenant_id: str
    project_id: str
    role: str
    is_human: bool

    def __post_init__(self) -> None:
        for value in (self.actor_id, self.tenant_id, self.project_id, self.role):
            require_id(value)
        if type(self.is_human) is not bool:
            raise TypeError("graph writer human flag must be boolean")


@dataclass(frozen=True, slots=True)
class GraphChangeResult:
    snapshot: Graph
    state: EventReplayState
    receipt: EventReceipt
    replayed: bool


@dataclass(frozen=True, slots=True)
class VersionPointer:
    node_id: str
    version: int
    content_hash: str


@dataclass(frozen=True, slots=True)
class EventReceipt:
    event_id: str
    payload_hash: str
    revision: int
    snapshot_hash: str


@dataclass(frozen=True, slots=True)
class EventReplayState:
    tenant_id: str
    project_id: str
    base_snapshot_hash: str
    revision: int
    versions: tuple[VersionPointer, ...]
    receipts: tuple[EventReceipt, ...]
    last_event_at: datetime | None = None
    confirmed_evidence_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        require_id(self.tenant_id)
        require_id(self.project_id)
        require_hash(self.base_snapshot_hash)
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("revision must be nonnegative")
        if len({pointer.node_id for pointer in self.versions}) != len(self.versions):
            raise ValueError("duplicate version pointer")
        if len({receipt.event_id for receipt in self.receipts}) != len(self.receipts):
            raise ValueError("duplicate event receipt")
        if self.revision != len(self.receipts):
            raise ValueError("event revision and receipt count disagree")
        if not isinstance(self.versions, tuple) or not isinstance(self.receipts, tuple):
            raise TypeError("event replay state must be immutable")
        if not isinstance(self.confirmed_evidence_ids, frozenset):
            raise TypeError("confirmed evidence IDs must be immutable")

    @classmethod
    def from_graph(cls, graph: Graph) -> EventReplayState:
        return cls(
            tenant_id=graph.tenant_id,
            project_id=graph.project_id,
            base_snapshot_hash=graph.snapshot_hash,
            revision=0,
            versions=tuple(
                sorted(
                    (
                        VersionPointer(node.id, node.version, node.content_hash)
                        for node in graph.nodes
                    ),
                    key=lambda pointer: pointer.node_id,
                )
            ),
            receipts=(),
            confirmed_evidence_ids=frozenset(
                node.id for node in graph.nodes if isinstance(node, Evidence) and node.confirmed_by
            ),
        )

    @property
    def snapshot_hash(self) -> str:
        if self.revision == 0:
            return self.base_snapshot_hash
        return fingerprint(
            (
                self.base_snapshot_hash,
                self.revision,
                self.versions,
                tuple((receipt.event_id, receipt.payload_hash) for receipt in self.receipts),
            )
        )

    def current(self, node_id: str) -> VersionPointer:
        for pointer in self.versions:
            if pointer.node_id == node_id:
                return pointer
        raise EventConflict("event target is missing from replay scope")


@dataclass(frozen=True, slots=True)
class ReplayResult:
    state: EventReplayState
    receipt: EventReceipt
    replayed: bool


def apply_change_event(state: EventReplayState, event: ChangeEvent) -> ReplayResult:
    """Apply one ordered version pointer, or return the original receipt on exact replay."""
    if (event.tenant_id, event.project_id) != (state.tenant_id, state.project_id):
        raise EventConflict("event scope mismatch")

    payload_hash = fingerprint(event)
    prior = next((receipt for receipt in state.receipts if receipt.event_id == event.id), None)
    if prior is not None:
        if prior.payload_hash != payload_hash:
            raise EventConflict("event ID was reused with a different payload")
        return ReplayResult(state, prior, True)

    if event.expected_snapshot_hash != state.snapshot_hash:
        raise EventStaleSnapshot("event expected a stale snapshot")
    if state.last_event_at is not None and event.occurred_at <= state.last_event_at:
        raise EventOutOfOrder("event timestamp does not advance replay order")
    target = state.current(event.target_id)
    if (event.old_version, event.old_hash) != (target.version, target.content_hash):
        raise EventOutOfOrder("event target version is stale or out of order")
    if event.new_version != event.old_version + 1:
        raise EventOutOfOrder("event must advance exactly one version")

    state.current(event.source_id)
    if event.source_id not in state.confirmed_evidence_ids:
        raise EventConflict("change source evidence is missing or unconfirmed")

    versions = tuple(
        sorted(
            (
                VersionPointer(pointer.node_id, event.new_version, event.new_hash)
                if pointer.node_id == target.node_id
                else pointer
                for pointer in state.versions
            ),
            key=lambda pointer: pointer.node_id,
        )
    )
    revision = state.revision + 1
    receipt = EventReceipt(event.id, payload_hash, revision, "0" * 64)
    provisional = EventReplayState(
        state.tenant_id,
        state.project_id,
        state.base_snapshot_hash,
        revision,
        versions,
        (*state.receipts, receipt),
        event.occurred_at,
        state.confirmed_evidence_ids,
    )
    receipt = EventReceipt(event.id, payload_hash, revision, provisional.snapshot_hash)
    receipts = (*state.receipts, receipt)
    updated = EventReplayState(
        state.tenant_id,
        state.project_id,
        state.base_snapshot_hash,
        revision,
        versions,
        receipts,
        event.occurred_at,
        state.confirmed_evidence_ids,
    )
    return ReplayResult(updated, receipt, False)


def graph_change_payload(change: GraphChangePayload) -> dict[str, object]:
    """Serialize a graph event with type tags and complete node/edge data."""
    snapshot = {
        "schema_version": 1,
        "tenant_id": change.snapshot.tenant_id,
        "project_id": change.snapshot.project_id,
        "as_of": canonical(change.snapshot.as_of),
        "snapshot_hash": change.snapshot.snapshot_hash,
        "nodes": [
            _typed_payload(node) for node in sorted(change.snapshot.nodes, key=lambda n: n.id)
        ],
        "edges": [
            _typed_payload(edge) for edge in sorted(change.snapshot.edges, key=lambda e: e.id)
        ],
    }
    return {
        "event_type": "GRAPH_SNAPSHOT_CHANGE",
        "schema_version": change.schema_version,
        "event_id": change.event_id,
        "tenant_id": change.tenant_id,
        "project_id": change.project_id,
        "actor_id": change.actor_id,
        "occurred_at": canonical(change.occurred_at),
        "expected_revision": change.expected_revision,
        "expected_snapshot_hash": change.expected_snapshot_hash,
        "snapshot": snapshot,
    }


def validate_graph_change(
    current_graph: Graph,
    change: GraphChangePayload,
    *,
    current_revision: int,
    known_versions: frozenset[tuple[str, int, str]] | None = None,
) -> Graph:
    """Validate the complete next graph without trusting a claimed new hash."""
    if (change.tenant_id, change.project_id) != (
        current_graph.tenant_id,
        current_graph.project_id,
    ):
        raise GraphChangeConflict("graph change scope mismatch")
    if change.expected_revision != current_revision:
        raise GraphChangeConflict("graph change expected a stale project revision")
    if change.expected_snapshot_hash != current_graph.snapshot_hash:
        raise GraphChangeConflict("graph change expected a stale snapshot")
    if change.snapshot.snapshot_hash == current_graph.snapshot_hash:
        raise GraphChangeConflict("graph change does not advance the snapshot")
    if change.occurred_at <= current_graph.as_of:
        raise GraphChangeConflict("graph change timestamp must advance snapshot time")
    if change.snapshot.as_of < change.occurred_at:
        raise GraphChangeConflict("new snapshot predates its graph change event")

    old_nodes = {node.id: node for node in current_graph.nodes}
    new_nodes = {node.id: node for node in change.snapshot.nodes}
    if not old_nodes.keys() <= new_nodes.keys():
        raise GraphChangeConflict("graph change is incomplete: current nodes cannot disappear")
    changed_node_ids: set[str] = set()
    for node_id, old_node in old_nodes.items():
        new_node = new_nodes[node_id]
        if type(old_node) is not type(new_node):
            raise GraphChangeConflict("graph change cannot change an entity type in place")
        if old_node != new_node:
            changed_node_ids.add(node_id)
            if new_node.version != old_node.version + 1:
                raise GraphChangeConflict("changed node version must advance exactly once")
            if new_node.valid_from <= old_node.valid_from:
                raise GraphChangeConflict("changed node validity must advance")
    for node_id, new_node in new_nodes.items():
        if node_id not in old_nodes:
            if new_node.version != 1 or new_node.valid_from <= current_graph.as_of:
                raise GraphChangeConflict("new node must start at version 1 after current time")

    old_edges = {edge.id: edge for edge in current_graph.edges}
    new_edges = {edge.id: edge for edge in change.snapshot.edges}
    for edge_id, old_edge in old_edges.items():
        new_edge = new_edges.get(edge_id)
        if new_edge is None:
            if old_edge.active_at(current_graph.as_of):
                raise GraphChangeConflict(
                    "active dependency edges require explicit temporal closure"
                )
            continue
        if old_edge != new_edge:
            closure = old_edge.valid_to is None and new_edge.valid_to is not None
            if (
                not closure
                or new_edge.upstream_id != old_edge.upstream_id
                or new_edge.dependent_id != old_edge.dependent_id
                or new_edge.strength != old_edge.strength
                or new_edge.valid_from != old_edge.valid_from
                or new_edge.relevant_fields != old_edge.relevant_fields
                or new_edge.valid_to is None
                or new_edge.valid_to <= current_graph.as_of
            ):
                raise GraphChangeConflict("dependency edges are immutable except temporal closure")
    for edge_id, edge in new_edges.items():
        if edge_id not in old_edges and edge.valid_from <= current_graph.as_of:
            raise GraphChangeConflict("new dependency edge cannot be retroactive")

    for node_id in changed_node_ids | (new_nodes.keys() - old_nodes.keys()):
        node = new_nodes[node_id]
        if isinstance(node, Requirement) and node.status == RequirementStatus.CONFIRMED:
            if node.confirmed_by != change.actor_id:
                raise GraphChangeConflict("confirmed requirement must name confirming actor")
        if isinstance(node, Evidence) and node.confirmed_by is not None:
            if node.confirmed_by != change.actor_id:
                raise GraphChangeConflict("new evidence confirmation must name confirming actor")
        if isinstance(node, AssetVersion):
            requirement_hash = requirement_fingerprint(change.snapshot.requirements)
            if node.requirement_fingerprint != requirement_hash:
                raise GraphChangeConflict(
                    "changed asset does not bind current requirement snapshot"
                )
            if any(
                requirement.status != RequirementStatus.CONFIRMED or not requirement.confirmed_by
                for requirement in change.snapshot.requirements
            ):
                raise GraphChangeConflict("changed asset requires confirmed requirements")
            evidence_is_unconfirmed = False
            for evidence_id in node.evidence_ids:
                evidence = change.snapshot.node(evidence_id)
                if not isinstance(evidence, Evidence) or not evidence.confirmed_by:
                    evidence_is_unconfirmed = True
                    break
            if evidence_is_unconfirmed:
                raise GraphChangeConflict("changed asset requires confirmed evidence provenance")

    versions = set(known_versions or ())
    for graph in (current_graph, change.snapshot):
        versions.update((node.id, node.version, node.content_hash) for node in graph.nodes)
    for node in change.snapshot.nodes:
        for input_ref in node.inputs:
            if (input_ref.source_id, input_ref.version, input_ref.content_hash) not in versions:
                raise GraphChangeConflict("graph change contains unavailable input provenance")
    return change.snapshot


def _typed_payload(value: object) -> dict[str, object]:
    payload = canonical(value)
    if not isinstance(payload, dict):
        raise TypeError("graph record did not serialize to an object")
    return {"type": type(value).__name__, **payload}


def apply_graph_snapshot_change(
    state: EventReplayState,
    current_graph: Graph,
    change: GraphChangePayload,
    identity: GraphChangeIdentity,
    *,
    known_versions: frozenset[tuple[str, int, str]] | None = None,
) -> GraphChangeResult:
    """Authorize and apply one full graph snapshot to deterministic replay state."""
    if (identity.tenant_id, identity.project_id) != (state.tenant_id, state.project_id):
        raise GraphChangeConflict("graph writer scope mismatch")
    if identity.actor_id != change.actor_id or not identity.is_human:
        raise GraphChangeConflict("graph change requires the authorized human actor")
    if identity.role not in {"producer", "editor", "reviewer"}:
        raise GraphChangeConflict("graph writer role is not authorized")

    payload_hash = fingerprint(graph_change_payload(change))
    prior = next(
        (receipt for receipt in state.receipts if receipt.event_id == change.event_id), None
    )
    if prior is not None:
        if prior.payload_hash != payload_hash:
            raise GraphChangeConflict("graph event ID has conflicting payload")
        return GraphChangeResult(current_graph, state, prior, True)
    if state.revision != change.expected_revision:
        raise GraphChangeConflict("graph change expected a stale replay revision")
    last_event_at = state.last_event_at
    if last_event_at is not None and change.occurred_at <= last_event_at:
        raise GraphChangeConflict("graph change event is out of order")

    updated_graph = validate_graph_change(
        current_graph,
        change,
        current_revision=state.revision,
        known_versions=known_versions,
    )
    prior_nodes = {node.id: node for node in current_graph.nodes}
    changed_ids = {
        node.id
        for node in updated_graph.nodes
        if node.id not in prior_nodes or node != prior_nodes[node.id]
    }
    for _node_id in {
        node.id
        for node in updated_graph.requirements
        if node.id in changed_ids
        and node.status == RequirementStatus.CONFIRMED
        and node.confirmed_by == change.actor_id
    }:
        if identity.role not in {"producer", "reviewer"}:
            raise GraphChangeConflict("requirement confirmation requires producer or reviewer role")
    revision = state.revision + 1
    versions = tuple(
        sorted(
            (
                VersionPointer(node.id, node.version, node.content_hash)
                for node in updated_graph.nodes
            ),
            key=lambda pointer: pointer.node_id,
        )
    )
    confirmations = frozenset(
        node.id for node in updated_graph.nodes if isinstance(node, Evidence) and node.confirmed_by
    )
    receipt = EventReceipt(change.event_id, payload_hash, revision, "0" * 64)
    provisional = EventReplayState(
        state.tenant_id,
        state.project_id,
        state.base_snapshot_hash,
        revision,
        versions,
        (*state.receipts, receipt),
        change.occurred_at,
        confirmations,
    )
    receipt = EventReceipt(change.event_id, payload_hash, revision, provisional.snapshot_hash)
    updated_state = EventReplayState(
        state.tenant_id,
        state.project_id,
        state.base_snapshot_hash,
        revision,
        versions,
        (*state.receipts, receipt),
        change.occurred_at,
        confirmations,
    )
    return GraphChangeResult(updated_graph, updated_state, receipt, False)


def replay_graph_changes(
    initial_graph: Graph,
    changes: tuple[GraphChangePayload, ...],
    *,
    initial_revision: int = 0,
) -> Graph:
    """Reconstruct the final graph from the initial snapshot and ordered full events."""
    if not isinstance(changes, tuple):
        raise TypeError("graph change history must be immutable")
    graph = initial_graph
    current_revision = initial_revision
    known: set[tuple[str, int, str]] = {
        (node.id, node.version, node.content_hash) for node in initial_graph.nodes
    }
    seen_event_ids: set[str] = set()
    for change in changes:
        if change.event_id in seen_event_ids:
            raise GraphChangeConflict("duplicate graph event in replay history")
        seen_event_ids.add(change.event_id)
        if change.expected_revision < current_revision:
            raise GraphChangeConflict("graph event history is out of order")
        graph = validate_graph_change(
            graph,
            change,
            current_revision=change.expected_revision,
            known_versions=frozenset(known),
        )
        current_revision = change.expected_revision + 1
        known.update((node.id, node.version, node.content_hash) for node in graph.nodes)
    return graph
