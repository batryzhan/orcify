"""Tenant-scoped, transactional Neo4j projection for authoritative snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from gamo_ca.fingerprints import canonical, fingerprint
from gamo_ca.graph import Graph


class ProjectionError(RuntimeError):
    """Projection state is stale, inconsistent, or could not be safely changed."""


class StaleProjectionEvent(ProjectionError):
    """A duplicate conflicting, stale, or out-of-order event was rejected."""


@dataclass(frozen=True, slots=True)
class ProjectionState:
    tenant_id: str
    project_id: str
    source_revision: int
    graph_hash: str
    last_event_id: str | None
    node_hashes: tuple[tuple[str, str], ...]
    edge_hashes: tuple[tuple[str, str], ...]


class Neo4jGraphProjection:
    """Store project graph records with a tenant/project-qualified key on every query."""

    def __init__(self, driver: Any, *, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    def ensure_schema(self) -> None:
        statements = (
            "CREATE CONSTRAINT orcify_projection_scope IF NOT EXISTS "
            "FOR (p:OrcifyProjection) REQUIRE (p.tenant_id, p.project_id) IS UNIQUE",
            "CREATE CONSTRAINT orcify_entity_scope IF NOT EXISTS "
            "FOR (n:OrcifyEntity) REQUIRE (n.tenant_id, n.project_id, n.node_id) IS UNIQUE",
        )
        with self._driver.session(database=self._database) as session:
            for statement in statements:
                session.run(statement).consume()

    def inspect(self, tenant_id: str, project_id: str) -> ProjectionState | None:
        with self._driver.session(database=self._database) as session:
            result = session.execute_read(
                self._inspect_tx, tenant_id=tenant_id, project_id=project_id
            )
        return cast(ProjectionState | None, result)

    @staticmethod
    def _inspect_tx(tx: Any, *, tenant_id: str, project_id: str) -> ProjectionState | None:
        result = tx.run(
            "MATCH (p:OrcifyProjection {tenant_id: $tenant_id, project_id: $project_id}) "
            "OPTIONAL MATCH (n:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id}) "
            "WITH p, collect(DISTINCT {id: n.node_id, hash: n.record_hash}) AS nodes "
            "OPTIONAL MATCH (a:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id}) "
            "-[r:DEPENDS_ON {tenant_id: $tenant_id, project_id: $project_id}]-> "
            "(b:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id}) "
            "RETURN p.source_revision AS source_revision, p.graph_hash AS graph_hash, "
            "p.last_event_id AS last_event_id, nodes, "
            "collect(DISTINCT {id: r.edge_id, hash: r.record_hash}) AS edges",
            tenant_id=tenant_id,
            project_id=project_id,
        ).single()
        if result is None:
            return None
        if result["source_revision"] is None:
            return None
        node_hashes = tuple(
            sorted((str(item["id"]), str(item["hash"])) for item in result["nodes"] if item["id"])
        )
        edge_hashes = tuple(
            sorted((str(item["id"]), str(item["hash"])) for item in result["edges"] if item["id"])
        )
        return ProjectionState(
            tenant_id,
            project_id,
            int(result["source_revision"]),
            str(result["graph_hash"]),
            result["last_event_id"],
            node_hashes,
            edge_hashes,
        )

    def initialize(self, graph: Graph) -> ProjectionState:
        """Create revision-zero projection only when it is absent or already exact."""
        return self._write_snapshot(
            graph,
            source_revision=0,
            event_id=f"initial:{graph.snapshot_hash}",
            expected_revision=None,
            expected_graph_hash=None,
            allow_existing_exact=True,
            force=False,
        )

    def apply_graph_change(
        self,
        graph: Graph,
        *,
        source_revision: int,
        event_id: str,
        expected_revision: int,
        expected_graph_hash: str,
    ) -> ProjectionState:
        return self._write_snapshot(
            graph,
            source_revision=source_revision,
            event_id=event_id,
            expected_revision=expected_revision,
            expected_graph_hash=expected_graph_hash,
            allow_existing_exact=True,
            force=False,
        )

    def advance_checkpoint(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_revision: int,
        event_id: str,
        expected_revision: int,
        graph_hash: str,
    ) -> ProjectionState:
        """Advance a no-graph-change source revision without modifying graph content."""
        with self._driver.session(database=self._database) as session:
            result = session.execute_write(
                self._advance_tx,
                tenant_id=tenant_id,
                project_id=project_id,
                source_revision=source_revision,
                event_id=event_id,
                expected_revision=expected_revision,
                graph_hash=graph_hash,
            )
        return cast(ProjectionState, result)

    @staticmethod
    def _advance_tx(
        tx: Any,
        *,
        tenant_id: str,
        project_id: str,
        source_revision: int,
        event_id: str,
        expected_revision: int,
        graph_hash: str,
    ) -> ProjectionState:
        tx.run(
            "MATCH (p:OrcifyProjection {tenant_id: $tenant_id, project_id: $project_id}) "
            "SET p.lock_nonce = randomUUID()",
            tenant_id=tenant_id,
            project_id=project_id,
        ).consume()
        state = Neo4jGraphProjection._inspect_tx(tx, tenant_id=tenant_id, project_id=project_id)
        if state is None:
            raise StaleProjectionEvent("projection must be initialized from revision zero first")
        if state.source_revision == source_revision:
            if state.last_event_id == event_id and state.graph_hash == graph_hash:
                return state
            raise StaleProjectionEvent("same projection revision has a different event")
        if state.source_revision != expected_revision or source_revision != expected_revision + 1:
            raise StaleProjectionEvent("projection update is stale or out of order")
        if state.graph_hash != graph_hash:
            raise StaleProjectionEvent("no-op event cannot change the projected graph hash")
        tx.run(
            "MATCH (p:OrcifyProjection {tenant_id: $tenant_id, project_id: $project_id}) "
            "SET p.source_revision = $source_revision, p.last_event_id = $event_id",
            tenant_id=tenant_id,
            project_id=project_id,
            source_revision=source_revision,
            event_id=event_id,
        ).consume()
        updated = Neo4jGraphProjection._inspect_tx(tx, tenant_id=tenant_id, project_id=project_id)
        if updated is None:
            raise ProjectionError("projection checkpoint disappeared during update")
        return updated

    def rebuild(self, graph: Graph, *, source_revision: int, event_id: str) -> ProjectionState:
        """Replace a projection atomically from a verified PostgreSQL graph snapshot."""
        return self._write_snapshot(
            graph,
            source_revision=source_revision,
            event_id=event_id,
            expected_revision=None,
            expected_graph_hash=None,
            allow_existing_exact=True,
            force=True,
        )

    def _write_snapshot(
        self,
        graph: Graph,
        *,
        source_revision: int,
        event_id: str,
        expected_revision: int | None,
        expected_graph_hash: str | None,
        allow_existing_exact: bool,
        force: bool,
    ) -> ProjectionState:
        nodes = [_node_row(node) for node in sorted(graph.nodes, key=lambda item: item.id)]
        edges = [_edge_row(edge) for edge in sorted(graph.edges, key=lambda item: item.id)]
        with self._driver.session(database=self._database) as session:
            result = session.execute_write(
                self._replace_tx,
                tenant_id=graph.tenant_id,
                project_id=graph.project_id,
                source_revision=source_revision,
                event_id=event_id,
                graph_hash=graph.snapshot_hash,
                expected_revision=expected_revision,
                expected_graph_hash=expected_graph_hash,
                allow_existing_exact=allow_existing_exact,
                force=force,
                nodes=nodes,
                edges=edges,
            )
        return cast(ProjectionState, result)

    @staticmethod
    def _replace_tx(tx: Any, **params: Any) -> ProjectionState:
        tx.run(
            "MERGE (p:OrcifyProjection {tenant_id: $tenant_id, project_id: $project_id}) "
            "SET p.lock_nonce = randomUUID()",
            tenant_id=params["tenant_id"],
            project_id=params["project_id"],
        ).consume()
        state = Neo4jGraphProjection._inspect_tx(
            tx, tenant_id=params["tenant_id"], project_id=params["project_id"]
        )
        if state is not None:
            if (
                params["allow_existing_exact"]
                and state.source_revision == params["source_revision"]
                and state.graph_hash == params["graph_hash"]
                and state.last_event_id == params["event_id"]
            ):
                return state
            if params["force"] is False:
                if state.source_revision != params["expected_revision"]:
                    raise StaleProjectionEvent("projection update is stale or out of order")
                if state.graph_hash != params["expected_graph_hash"]:
                    raise StaleProjectionEvent("projection base graph hash differs")
                if params["source_revision"] != params["expected_revision"] + 1:
                    raise StaleProjectionEvent("projection revision must advance exactly once")
        elif params["force"] is False and params["source_revision"] != 0:
            raise StaleProjectionEvent("projection must be initialized at revision zero")

        tx.run(
            "MATCH (a:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id}) "
            "-[r:DEPENDS_ON {tenant_id: $tenant_id, project_id: $project_id}]-> "
            "(b:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id}) DELETE r",
            tenant_id=params["tenant_id"],
            project_id=params["project_id"],
        ).consume()
        tx.run(
            "MATCH (n:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id}) "
            "DETACH DELETE n",
            tenant_id=params["tenant_id"],
            project_id=params["project_id"],
        ).consume()
        tx.run(
            "UNWIND $nodes AS row "
            "CREATE (:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id, "
            "node_id: row.id, entity_type: row.entity_type, version: row.version, "
            "content_hash: row.content_hash, record_hash: row.record_hash, "
            "payload_json: row.payload_json})",
            tenant_id=params["tenant_id"],
            project_id=params["project_id"],
            nodes=params["nodes"],
        ).consume()
        tx.run(
            "UNWIND $edges AS row "
            "MATCH (a:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id, "
            "node_id: row.upstream_id}) "
            "MATCH (b:OrcifyEntity {tenant_id: $tenant_id, project_id: $project_id, "
            "node_id: row.dependent_id}) "
            "CREATE (a)-[:DEPENDS_ON {tenant_id: $tenant_id, project_id: $project_id, "
            "edge_id: row.id, strength: row.strength, record_hash: row.record_hash, "
            "payload_json: row.payload_json}]->(b)",
            tenant_id=params["tenant_id"],
            project_id=params["project_id"],
            edges=params["edges"],
        ).consume()
        tx.run(
            "MERGE (p:OrcifyProjection {tenant_id: $tenant_id, project_id: $project_id}) "
            "SET p.source_revision = $source_revision, p.graph_hash = $graph_hash, "
            "p.last_event_id = $event_id",
            tenant_id=params["tenant_id"],
            project_id=params["project_id"],
            source_revision=params["source_revision"],
            graph_hash=params["graph_hash"],
            event_id=params["event_id"],
        ).consume()
        updated = Neo4jGraphProjection._inspect_tx(
            tx, tenant_id=params["tenant_id"], project_id=params["project_id"]
        )
        if updated is None:
            raise ProjectionError("projection checkpoint missing after snapshot replacement")
        return updated


def _node_row(node: Any) -> dict[str, Any]:
    value = canonical(node)
    assert isinstance(value, dict)
    return {
        "id": node.id,
        "entity_type": type(node).__name__,
        "version": node.version,
        "content_hash": node.content_hash,
        "record_hash": fingerprint(node),
        "payload_json": json.dumps(value, sort_keys=True, separators=(",", ":")),
    }


def _edge_row(edge: Any) -> dict[str, Any]:
    value = canonical(edge)
    assert isinstance(value, dict)
    return {
        "id": edge.id,
        "upstream_id": edge.upstream_id,
        "dependent_id": edge.dependent_id,
        "strength": edge.strength.value,
        "record_hash": fingerprint(edge),
        "payload_json": json.dumps(value, sort_keys=True, separators=(",", ":")),
    }
