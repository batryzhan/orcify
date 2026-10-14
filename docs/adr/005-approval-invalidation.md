# ADR-005: Exact snapshot approvals, eligibility derived from authority

Status: accepted; pure Phase 1 transitions are now append-persisted in the Phase 2A PostgreSQL schema, while verified API authentication and live database checks remain open. 2026-10-14.

An approval is an immutable human decision bound to an exact asset version and
confirmed requirement fingerprint. Rejection/revocation is a subsequent record,
not a mutation of history. A new version never inherits approval. A current HARD
change or pending SOFT review blocks eligibility even if an old decision exists.
KEEP means retain computation, not grant publication. A version-specific
requirement snapshot must be checked again transactionally at final handoff.

`packages/gamo_ca/approvals.py` models draft as an empty chain, then appends
submission, approval/rejection, revocation, and explicit resubmission after
revocation. It checks legal transitions, optimistic per-version revision,
supersession links, idempotency keys, and append-only timestamps, then derives
publication eligibility from the exact active plan. Rejected decisions are
terminal for that immutable version. It rejects a plan
with a stale graph hash or an asset/dependency action other than KEEP. The human
reviewer identity parameter must come from the future API's authenticated server
authorization. Constructing that value directly in Python is not authentication.
PostgreSQL transactions and cross-request races remain Phase 2 responsibilities.
Plan hashes are integrity identifiers, not cryptographic proof of actor authority.

`packages/gamo_ca/events.py` deterministically replays version-pointer events in
memory. Exact duplicate IDs return the original receipt; conflicting IDs, stale
snapshot hashes, old versions, version gaps and non-advancing event times fail.
This reducer does not replace the PostgreSQL append-only log or its atomic
idempotency constraint.

The Phase 2A repository helper calls `apply_approval` inside a locked project
transaction, stores exact-version/requirement/policy/actor/decision fields and a
canonical payload hash, and rejects idempotency-key payload conflicts. It requires
a server-created `ReviewerIdentity`; this helper is not itself an authentication
boundary and is not exposed as a client route. Approval and snapshot tables are
append-only in ORM listeners and PostgreSQL triggers. On 2026-10-14, live
PostgreSQL integration passed exact approval retry and direct SQL trigger checks;
the PostgreSQL schema was migrated through `0002_snapshots_approvals`. Docker
Compose container health metadata was unavailable from this shell, while the
PostgreSQL and authenticated Neo4j service probes succeeded. Full graph
replacement/advancement and transactionally derived publication eligibility await
authoritative graph ingestion and authenticated API work.

Alternative: transferable asset-level approvals or overwriting approved flags.
Rejected: they erase exact human intent and can publish stale results. Trade-off:
more explicit review work and immutable decision records. No publication endpoint
will exist before the state machine and authorization invariants are tested.
