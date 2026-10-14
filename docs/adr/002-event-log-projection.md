# ADR-002: PostgreSQL authority, Neo4j query projection

Status: accepted design, implementation deferred to Phase 2; 2026-10-14.

One PostgreSQL transaction will append an event, immutable snapshots/approval
decisions, optimistic campaign revision, and an outbox row. Unique
`(tenant_id, project_id, event_id)` and idempotency-key/payload hashes will reject
conflicting replay; identical replay returns the original receipt. No dual write
to Neo4j within a request. A projection consumer applies ordered outbox entries
idempotently and records its offset. Query responses expose projection revision.
Safety decisions read authoritative state, never a lagging graph projection.

Rebuild Neo4j from the log, verify revision/content hashes, then switch a complete
projection. Failed delivery remains pending for retry with a recorded error;
reconciliation checks offsets and drift. Crash after graph write but before offset
is handled by event-ID deduplication. Transaction/recovery tests are Phase 2 gates.

Alternative: Neo4j authority or synchronous dual write. Rejected because atomic
approval/event consistency across two databases is otherwise fragile. Trade-off:
eventual query consistency and projection operations must be visible and tested.
