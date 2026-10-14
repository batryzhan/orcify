# Open limitations

The current milestone implements contracts, pure planning, exact-version approval,
fail-closed publication eligibility, deterministic replay, and transactional PostgreSQL
event, graph snapshot, replay snapshot, approval and outbox persistence, including a
retryable Neo4j projection and reconciliation path, not a complete production service.
Authenticated API actor authorization wiring, artifact/run-log persistence, executor
timeouts, malicious document handling and any external publication remain mandatory
later gates. The planner receives a
scoped graph; scope matching and a `ReviewerIdentity` value are not authentication.
No real client data or paid model calls are used. There are no measured benchmark
results, independently reviewed gold labels, usability findings or novelty claims.

Current snapshots select versions externally; historical resolution and future
changes are not supported by the kernel until an explicit as-of snapshot exists.
SOFT field relevance is a deterministic explicit rule, not semantic inference.
No hard-stale node is reused based only on a coincidentally equal content hash.
Estimates are optional and explicitly SIMULATED; planner CPU cost is not estimated.
Review and recomputation eligibility are separate from publication eligibility.
The original reducer still stores version pointers and receipts. Typed
`GraphChangePayload` events now carry full graph content, and PostgreSQL stores the
immutable graph and replay snapshots with separate authority hashes. Historical graph
replay verifies the current graph hash. Artifact/run-log persistence and API-level
authentication remain unimplemented. Repository identities must be created by a
verified server boundary; the helpers do not establish authentication themselves.
The event store uses PostgreSQL row locks and database uniqueness constraints. Against
the reachable local PostgreSQL 16.15 instance, migration `0004_projection_delivery`
was applied and three live integration tests passed for concurrent pointer and graph
updates, graph replay/hash consistency, idempotency, database triggers and injected
rollback. A live PostgreSQL + Neo4j integration test applied a graph event through the
outbox, verified duplicate/stale handling and tenant-scoped visibility, then detected
and repaired a deleted projected node from PostgreSQL. Deterministic SQLite tests
cover capped retries, exponential backoff, dead-letter blocking and crash recovery
after a Neo4j commit. Docker CLI is not discoverable in this shell, so Compose container
health metadata was not inspected. Neo4j's eventual consistency means query clients
must inspect checkpoint status before relying on a projection; authority decisions must
continue to read PostgreSQL. Holding the PostgreSQL project lock during the bounded
Neo4j transaction can delay writes during service stalls. Finite tests are not evidence
of universal safety or performance improvement. The projection worker is currently a
single-process runnable prototype; multi-worker throughput, production alerting and
long-duration recovery have not been evaluated. Projection status must be checked by
readers, and all authority decisions must continue to use PostgreSQL.

This folder did not have `.git` when work began. Local checks can be run, but
hosted CI execution and Git SHA evidence require a Git repository and remote.
License ownership/terms are deliberately unresolved.
