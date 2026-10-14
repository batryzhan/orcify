# Open limitations

The current milestone implements contracts, pure planning, exact-version approval,
fail-closed publication eligibility, deterministic replay, and transactional PostgreSQL
event, graph snapshot, replay snapshot, approval and outbox persistence, not a complete
production service. Authenticated API actor authorization wiring, artifact/run-log
persistence, projection rebuilding, executor timeouts, malicious document handling
and any external publication remain mandatory later gates. The planner receives a
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
the reachable local PostgreSQL 16.15 instance, migration `0003_authoritative_graph_hash`
was applied and three live integration tests passed for concurrent pointer and graph
updates, graph replay/hash consistency, idempotency, database triggers and injected
rollback. A live authenticated Neo4j Cypher probe returned successfully. Docker CLI is
not discoverable in this shell, so Compose container health metadata was not inspected.
SQLite verifies migration repeatability and failure rollback; finite tests are not
evidence of universal safety.

This folder did not have `.git` when work began. Local checks can be run, but
hosted CI execution and Git SHA evidence require a Git repository and remote.
License ownership/terms are deliberately unresolved.
