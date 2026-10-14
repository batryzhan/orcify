# ADR-008: Immutable artifact versions and append-only execution provenance

Status: accepted and implemented for Phase 2C; 2026-10-14.

PostgreSQL stores the authoritative creative artifacts and execution history.
`artifact_versions` is append-only and binds content plus its SHA-256 hash to tenant,
project, a complete graph snapshot revision/hash, exact `AssetVersion` node/version,
dependency versions/hashes, and the recorded planner decision. The artifact payload
must equal the content of that exact graph asset. A database foreign key scopes the
artifact to the immutable graph snapshot; the service verifies JSON graph semantics
and dependencies under the project row lock. Provenance source rows are append-only
and commit with the artifact, so a failed source or constraint check leaves no artifact.

Execution run and attempt rows are current-state indexes updated transactionally while
`execution_events` is the append-only lifecycle history. Idempotency keys and request
hashes reject conflicting retries; project/run row locks and uniqueness constraints
serialize concurrent transitions. A run records its graph snapshot and complete plan;
each attempt records pinned input versions and optional provider/model/prompt IDs.
Pending, running, succeeded, failed, cancelled and retryable-failure states are
represented in lifecycle events. A retryable failure permits a new, monotonically
numbered attempt; terminal states reject further transitions. Every event is committed
in the same transaction as its current-state index update.

Run/attempt headers are immutable after creation. Application listeners reject header
field changes, and migration `0006_execution_header_guards` adds PostgreSQL triggers
that protect header columns and prevent deletion while allowing only run status and
attempt status/finish-time updates.

Elapsed time, token count and estimated cost are nullable values with explicit
`missing`, `estimated` or `measured` status, enforced by database constraints. No
provider is integrated in this milestone and absent usage/cost data stays missing.
The persistence layer does not create approvals. Artifact eligibility reads the
current graph and append-only approval history from PostgreSQL and invokes the pure
GAMO-CA publication predicate; stale source snapshots or node versions fail closed.
No external publication side effect is provided.

Live PostgreSQL tests cover transaction idempotency under concurrent duplicate writes,
append-only/header guards, provenance rollback, run/attempt lifecycle writes, and exact
measurement status. SQLite tests provide deterministic lifecycle and failure-injection
coverage. These engineering tests are not a scientific benchmark or a universal safety
proof. Current run and attempt statuses are mutable indexes; their immutable event
history remains the reconstruction record. Blob storage, retention, artifact diffing,
and authenticated HTTP access remain future work.
