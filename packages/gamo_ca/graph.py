"""Scoped, immutable current-version graph with deterministic ordering."""

import heapq
from dataclasses import dataclass
from datetime import datetime

from gamo_ca.fingerprints import fingerprint
from gamo_ca.models import DependencyEdge, Evidence, Node, Requirement, require_id, require_time


class GraphError(ValueError):
    """Invalid snapshot; caller must not execute a plan."""


@dataclass(frozen=True, slots=True)
class Graph:
    tenant_id: str
    project_id: str
    as_of: datetime
    nodes: tuple[Node, ...]
    edges: tuple[DependencyEdge, ...]

    def __post_init__(self) -> None:
        require_id(self.tenant_id)
        require_id(self.project_id)
        require_time(self.as_of)
        if not isinstance(self.nodes, tuple) or not isinstance(self.edges, tuple):
            raise TypeError("graph collections must be immutable")
        ids = {node.id for node in self.nodes}
        if len(ids) != len(self.nodes) or len({edge.id for edge in self.edges}) != len(self.edges):
            raise GraphError("duplicate graph identifier")
        for record in (*self.nodes, *self.edges):
            if (record.tenant_id, record.project_id) != (self.tenant_id, self.project_id):
                raise GraphError("record scope does not match graph")
        by_id = {n.id: n for n in self.nodes}
        for node in self.nodes:
            if not node.active_at(self.as_of):
                raise GraphError("graph contains inactive node version")
            for ref in node.inputs:
                if ref.source_id not in ids:
                    raise GraphError("consumed input endpoint missing")
            for evidence_id in node.evidence_ids:
                if not isinstance(by_id.get(evidence_id), Evidence):
                    raise GraphError("evidence endpoint missing or wrong type")
            if isinstance(node, Requirement) and not isinstance(
                by_id.get(node.source_id), Evidence
            ):
                raise GraphError("requirement source evidence missing")
        for edge in self.edges:
            if edge.upstream_id not in ids or edge.dependent_id not in ids:
                raise GraphError("dependency endpoint missing")
        self.topological_order()

    def node(self, node_id: str) -> Node:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise GraphError("node not present in scoped snapshot")

    @property
    def requirements(self) -> tuple[Requirement, ...]:
        return tuple(n for n in self.nodes if isinstance(n, Requirement))

    @property
    def active_edges(self) -> tuple[DependencyEdge, ...]:
        return tuple(
            sorted(
                (edge for edge in self.edges if edge.active_at(self.as_of)),
                key=lambda edge: edge.id,
            )
        )

    @property
    def snapshot_hash(self) -> str:
        return fingerprint(
            {
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "as_of": self.as_of,
                "nodes": sorted(self.nodes, key=lambda n: n.id),
                "edges": sorted(self.edges, key=lambda e: e.id),
            }
        )

    def topological_order(self) -> tuple[str, ...]:
        incoming = {node.id: 0 for node in self.nodes}
        outgoing: dict[str, list[str]] = {node.id: [] for node in self.nodes}
        for edge in self.active_edges:
            incoming[edge.dependent_id] += 1
            outgoing[edge.upstream_id].append(edge.dependent_id)
        ready = [node_id for node_id, count in incoming.items() if count == 0]
        heapq.heapify(ready)
        order: list[str] = []
        while ready:
            upstream = heapq.heappop(ready)
            order.append(upstream)
            for dependent in sorted(outgoing[upstream]):
                incoming[dependent] -= 1
                if incoming[dependent] == 0:
                    heapq.heappush(ready, dependent)
        if len(order) != len(self.nodes):
            raise GraphError("dependency cycle detected")
        return tuple(order)
