# ADR-005: Exact snapshot approvals, eligibility derived from authority

Status: accepted design; state machine due Phase 1; 2026-10-14.

An approval is an immutable human decision bound to an exact asset version and
confirmed requirement fingerprint. Rejection/revocation is a subsequent record,
not a mutation of history. A new version never inherits approval. A current HARD
change or pending SOFT review blocks eligibility even if an old decision exists.
KEEP means retain computation, not grant publication. A version-specific
requirement snapshot must be checked again transactionally at final handoff.

The pure planner emits invalidated asset IDs and review holds; it does not approve,
execute, revoke records or publish. Authentication/role checks and concurrent
state transitions are application responsibilities. Plan hashes are integrity
identifiers, not cryptographic proof of actor authority.

Alternative: transferable asset-level approvals or overwriting approved flags.
Rejected: they erase exact human intent and can publish stale results. Trade-off:
more explicit review work and immutable decision records. No publication endpoint
will exist before the state machine and authorization invariants are tested.
