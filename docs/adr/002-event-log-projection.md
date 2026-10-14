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
falls back to a stale projection. The Phase 2B worker claims events with PostgreSQL
leases and `SKIP LOCKED`, preserves per-project revision order, and uses bounded
exponential retry before dead-lettering. Neo4j applies a complete snapshot and its
checkpoint atomically with tenant/project-scoped keys and revision/hash compare checks.
PostgreSQL tracks delivery state, retry time, errors, checkpoint revision, graph hash
and event ID. Reconciliation compares revision, graph hash, node hashes and edge hashes
with the current PostgreSQL snapshot; any missing, stale or inconsistent projection is
replaced from that authority. Rebuild is atomic in Neo4j and supersedes covered pending
outbox rows in PostgreSQL. A crash between Neo4j commit and PostgreSQL acknowledgement
retries safely using event/revision/hash idempotency.

PostgreSQL is migrated through `0004_projection_delivery`. The live test passed against
both PostgreSQL and Neo4j, verifying outbox projection, exact duplicate delivery,
stale-event rejection, tenant-scoped reads, reconciliation and repair of a deleted
projected node. Deterministic SQLite tests cover retry/backoff, dead-letter handling,
crash recovery and rebuild. Docker Compose health metadata remains unavailable because
the Docker CLI is not discoverable in this shell.

Alternative: Neo4j authority or synchronous dual writes. Rejected because atomic
approval/event consistency across two databases is fragile. The trade-off is eventual
query consistency; projection lag and failures are visible and recoverable. Holding the
PostgreSQL project lock while applying one bounded Neo4j transaction can delay graph
ingestion during network stalls; driver and connection timeouts bound that interval.
