# Open limitations

The current milestone implements contracts, pure planning, exact-version approval,
fail-closed publication eligibility, deterministic replay, and transactional PostgreSQL
event, graph snapshot, replay snapshot, approval and outbox persistence, including a
retryable Neo4j projection, authenticated FastAPI boundary and tenant-scoped
authorization, not a complete production service. Interactive identity management,
project-scoped roles, uploads and malicious document handling, executor timeouts, and
any external publication remain later gates. The planner receives a
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
replay verifies the current graph hash. Migration `0005_artifacts_execution` now stores
immutable artifact versions, append-only source provenance, execution run/attempt
current indexes, append-only lifecycle events, and `0006_execution_header_guards` for
immutable run/attempt headers. Artifact rows are pinned to complete
graph snapshot hashes and exact asset/dependency versions; stored content must match
the graph asset content. Artifact eligibility re-reads PostgreSQL graph and approval
history and invokes the pure publication predicate. API authentication now uses opaque
bearer tokens and PostgreSQL membership records; persistence helpers still do not
establish authentication themselves.
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

Phase 2C's live PostgreSQL integration test covers concurrent duplicate artifact
writes, conflicting idempotency payloads, append-only triggers, execution lifecycle
records, metric provenance labels and rollback of a partially constructed artifact.
Offline tests cover stale dependency checks, retry transitions, cancellation, failed
event insertion rollback and fail-closed artifact eligibility. No real provider
integration, object storage, retention policy, measured model usage or benchmark is
included. Run/attempt status columns are mutable current-state
indexes; append-only execution events hold the provenance history. No universal safety
claim is made.

Phase 2D's MVP authentication uses high-entropy opaque bearer tokens, SHA-256 token
digests in PostgreSQL, and expiry/revocation checks against tenant-wide role
memberships. Identity provisioning is an operator/database action; there is no login,
SSO, MFA, automatic token rotation, membership administration endpoint, or project-
scoped role assignment. Production use still needs TLS, secure one-time token delivery,
secret management, database least-privilege roles, rate limiting, and security
monitoring. Route security tests ran in SQLite; a live PostgreSQL test covered
credential lookup and membership revocation. Eligibility continues to use the
PostgreSQL store's project lock and current graph/approval state; Neo4j is not an
authority source. These finite tests do not establish universal security or safety.
Docker Compose health and live Neo4j projection were not retested in the Phase 2D
verification run.

Hosted CI was not run in this local verification session.
License ownership/terms are deliberately unresolved.
