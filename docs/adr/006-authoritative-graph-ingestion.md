# ADR-006: Complete graph-change events advance immutable snapshots

Status: accepted; implemented for Phase 2A on 2026-10-14.

Graph ingestion accepts a typed `GraphChangePayload` with an explicit schema version,
event ID, tenant/project scope, authorized human actor, event time, expected project
revision, expected graph hash and the complete next `Graph`. The canonical event stores
all typed node and edge fields. The full snapshot is required so replay can reconstruct
authoritative content and independently verify its hash.

The repository locks the PostgreSQL project row, validates the identity and expected
revision, loads the current immutable snapshot and historical node versions, then calls
the pure `apply_graph_snapshot_change` transition. A successful write advances the
graph and replay hashes, project revision, append-only graph/replay snapshots, event
receipt and Neo4j outbox entry in one transaction. Any validator, insert or outbox
failure rolls the transaction back. A duplicate idempotency key with the same payload
returns the original receipt; key reuse with changed content and stale/concurrent writes
fail closed.

The validator preserves tenant/project scope, requires event and version times to
advance, disallows node deletion and in-place type changes, requires exact version
increments, enforces immutable temporal dependency edges except explicit closure,
relies on the typed `Graph` constructor for endpoint validity and DAG acyclicity, checks
input provenance against known versions, and requires actor-attributed confirmations
and confirmed requirements for changed assets. The schema is versioned and currently
accepts version 1 only. PostgreSQL remains authoritative; Neo4j is only an asynchronous
projection.

Verification is finite engineering evidence, not proof of universal safety or a
scientific benchmark. Live PostgreSQL race/rollback/replay tests and offline domain and
SQLite tests are recorded in `docs/research/experiment-log.md`. Authentication wiring,
projection delivery/reconciliation, artifacts, run logs and API routes remain open.
