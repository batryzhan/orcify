# ADR-002: PostgreSQL authority, Neo4j query projection

Status: accepted; complete graph-change events and PostgreSQL event/outbox, graph/replay snapshot and approval persistence implemented; projection-worker gates remain open; 2026-10-14.

PostgreSQL is the authority for projects, graph snapshots, event receipts, approvals,
replay state and the transactional outbox. One transaction appends the graph-change
event, immutable graph and replay snapshots, replay pointers, project revision, graph
hash and outbox record. A project-row lock and scoped unique constraints provide
optimistic concurrency and idempotency. Exact retries return the stored receipt;
conflicting payloads and stale revisions fail closed. ORM guards and PostgreSQL
triggers enforce append-only event, snapshot and approval history.

Graph changes use a versioned, self-contained event envelope with typed node and edge
content. Replaying the event log therefore reconstructs graph content; hashes verify
that content but do not replace it. Before persistence, the pure GAMO-CA validator
checks project scope, temporal validity, acyclicity, version advancement, provenance,
authorized human actor and confirmed requirements. The project stores separate graph
and reducer-state hashes because legacy pointer-only events do not contain full graph
content. Safety decisions load and verify the authoritative PostgreSQL snapshot.

Neo4j is a rebuildable projection. Requests never dual-write it, and no safety decision
falls back to a stale projection. A retryable, idempotent outbox consumer, projection
offsets and reconciliation are the next implementation task. The PostgreSQL service
was migrated through `0003_authoritative_graph_hash`; three live integration tests
passed for graph advancement/replay, row-lock serialization, trigger enforcement,
idempotency and rollback. Neo4j accepted an authenticated `RETURN 1` probe. Docker
Compose health metadata remains unavailable because the Docker CLI is not discoverable
in this shell.

Alternative: Neo4j authority or synchronous dual writes. Rejected because atomic
approval/event consistency across two databases is fragile. The trade-off is eventual
query consistency; projection lag and failures must be visible and recoverable.
