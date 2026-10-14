# ADR-007: Ordered, retryable Neo4j projection from the PostgreSQL outbox

Status: accepted and implemented for Phase 2B; 2026-10-14.

PostgreSQL remains the sole authority. A background consumer claims only the earliest
unfinished Neo4j outbox row for a project using a lease and row-level `SKIP LOCKED`.
The worker holds the authoritative project row lock while verifying the source event
and applying the projection, preventing a reconciliation or graph write from racing
with a newer committed project revision. No-op pointer events advance the projection
checkpoint without changing graph content. Complete graph-change events replace the
project's nodes and dependency edges in one Neo4j transaction.

Neo4j keys and every node/relationship lookup include both tenant and project IDs.
Each project projection records its source revision, graph hash and last event ID.
Compare checks reject stale and out-of-order events; an exact event/revision/hash retry
is idempotent. Snapshot replacement, relationship changes and checkpoint advancement
commit atomically in Neo4j. If the process crashes after that commit and before the
PostgreSQL acknowledgement, the worker recognizes the exact projected event and
completes the checkpoint without duplicating data.

PostgreSQL stores mutable delivery state separately from immutable event history:
pending/processing/retry/succeeded/dead/superseded status, attempt count, next attempt,
lease, last error, and per-project source revision/hash/status checkpoint. Retries use
deterministic capped exponential backoff and a bounded attempt count. A dead row blocks
later events for that project until reconciliation or operator repair. Reconciliation
compares the Neo4j revision, graph hash, node record hashes and dependency-edge hashes
with a graph snapshot and project revision read from PostgreSQL under a project lock.
Missing, old or inconsistent projections are atomically rebuilt from PostgreSQL and
covered pending outbox entries are marked superseded.

The driver applies bounded connection and transaction retry timeouts. The PostgreSQL
project lock is held across the Neo4j call to serialize a worker with ingestion and
reconciliation; network stalls therefore delay project writes until the bounded call
returns. Projection failures remain visible in outbox/checkpoint state. This design
does not make Neo4j suitable for publication or approval decisions. No external
publication integration is part of this worker.

Finite SQLite failure-injection tests and a live PostgreSQL + Neo4j integration test
cover retries, crash recovery, duplicate delivery, stale updates, scope isolation,
reconciliation and rebuild. These are engineering checks, not safety proofs or
scientific performance results.
