# Open limitations

This first milestone implements contracts and pure planning, not a complete
production service. Authenticated confirmation, approval transitions, transactional
idempotency/concurrency, persistence, projection rebuilding, executor timeouts,
malicious document handling and publication checks remain mandatory later gates.
The planner receives a scoped graph; scope matching is not user authentication.
No real client data or paid model calls are used. There are no measured benchmark
results, independently reviewed gold labels, usability findings or novelty claims.

Current snapshots select versions externally; historical resolution and future
changes are not supported by the kernel until an explicit as-of snapshot exists.
SOFT field relevance is a deterministic explicit rule, not semantic inference.
No hard-stale node is reused based only on a coincidentally equal content hash.
Estimates are optional and explicitly SIMULATED; planner CPU cost is not estimated.
Review and recomputation eligibility are separate from publication eligibility.

This folder did not have `.git` when work began. Local checks can be run, but
hosted CI execution and Git SHA evidence require a Git repository and remote.
License ownership/terms are deliberately unresolved.
