# Open limitations

The current milestone implements contracts, pure planning, exact-version approval,
fail-closed publication eligibility, deterministic replay, and transactional PostgreSQL
event, graph snapshot, replay snapshot, approval and outbox persistence, including a
retryable Neo4j projection, authenticated FastAPI boundary and tenant-scoped
authorization, not a complete production service. Interactive identity management,
project-scoped roles, uploads and malicious document handling, executor timeouts, and
any external publication remain later gates. The planner receives a
scoped graph; scope matching and a `ReviewerIdentity` value are not authentication.
No real client data or paid model calls are used. The R1.1 pilot records planning-time
measurements for five authored synthetic cases, but no independently reviewed gold
labels, adequately sized benchmark, usability findings, or novelty claims exist.

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

Phase 2E adds a repeatable synthetic seed and a live HTTP smoke path. The seed uses
stable IDs for the baseline graph and sample artifact; bearer tokens are random and
short-lived, stored as digests in PostgreSQL, and held in a git-ignored local file. Keep
that file private and remove it after the demo. Seeding refuses to change a role or reset
an advanced baseline project. Smoke-created projects and audit rows are append-only and
remain in the database, so assign unique run IDs or use a disposable database.

The live authenticated API integration now runs with PostgreSQL 16.15 and Neo4j. It
checks reviewer approval, stale-artifact denial after a confirmed requirement update,
concurrent idempotent requests, tenant/revocation denials, and Neo4j rebuild without
changing PostgreSQL authority. Two network HTTP smoke runs ran with the outbox worker process
active. Compose health metadata remains unverified because the Docker CLI is not
available in this shell; direct PostgreSQL and Neo4j connectivity checks succeeded.
This does not establish production hardening, universal safety, or research performance.

Phase 3A adds a responsive read-only React explorer. Active tenant memberships,
project artifacts, and approval history are exposed through newly added authenticated
read routes; the routes use the existing tenant-wide roles and require no migration.
The client uses `docs/api/openapi.json` to generate static types. The development token
is held in React memory and is not persisted. This is not a browser identity provider:
operators must provision the token separately and deliver it securely. The UI does not
perform graph writes, approval transitions, artifact creation, executions, or
publication. Eligibility and approval states are read from PostgreSQL-backed API
responses; failed reads are shown as unavailable. The graph has no historical revision
picker, artifact diff view, or pagination. API route tests for the new reads and CORS
used the existing isolated SQLite route fixture; no new live PostgreSQL run was
performed specifically for these read-only endpoints. Frontend tests and production
build are engineering checks only; no browser-level E2E against live services or
usability study ran. These checks are not a benchmark or proof of universal safety.

## Student research scope reset (2026-10-14)

Orcify is a high-school research prototype for the Kazakhstan Republican Scientific
Projects Competition. The existing API, PostgreSQL event store, Neo4j projection,
and React explorer exceed the minimum scientific demonstration and are now treated as
frozen support infrastructure. Their presence does not make this a SaaS product or a
production-ready service. Future work should focus on the GAMO-CA hypothesis, simple
fair baselines, independently reviewed synthetic cases, reproducible measurements,
and limitations. Product expansion, enterprise administration, paid provider
integration, external publication, and UI polish are out of scope.

No independently reviewed scientific dataset or adequately sized benchmark has been
completed. The R1.1 five-scenario pilot is an initial measured engineering experiment,
not generalizable performance evidence. Planned case counts and engineering test
results must not be described as research findings. The next task is independent
review of the pilot's scenarios, oracle, and baseline fairness before any larger
campaign. See [ADR-012](../adr/012-student-research-scope.md) and
[`r1_1-pilot/README.md`](r1_1-pilot/README.md).

## R1.2 audit limitations

The audit preserves the R1.1 results, but shows why the immediate 12-versus-21
recomputation comparison overstates demonstrated savings. Eight GAMO-CA output nodes
are held for review in four uncertain SOFT branches; each branch has a HARD child.
No review outcomes or follow-up plans were run. If all branches are confirmed
material, the accounting count rises from 12 to 20, close to DAG's 21. The other
immediate difference is one field-disjoint SOFT asset retained by GAMO-CA.

No listed mandatory HARD recomputation was replaced with REVIEW. However, four HARD
descendants of review-gated items do remain in REVIEW pending a human decision and
replanning. The R1.1 correctness check validates the current fail-closed hold, but not
the later transition from review to recomputation. This follow-up is still a required
test.

The scenario labels and oracle were authored by the same team and have not had
independent human review. Safe-action checks on these five cases are not independent
gold labels or a general correctness proof. The baselines receive the same graphs and
events, but their action vocabularies differ: the eager DAG baseline has no REVIEW
action and regenerates unknown SOFT descendants. The shared scorer checks exact
approval eligibility; it does not make the baseline an approval-aware planner.

Measured planner times are unfavorable to the current GAMO-CA implementation and are
not like-for-like: GAMO-CA performs graph validation, hashing and explanation work
that the small baseline functions omit. The run measured no human minutes, generation
time, tokens or money. R1.2 cost weights and the fraction of branches that might be
material are hypothetical sensitivity inputs, not empirical estimates. These limits
block a larger campaign until a second human reviews the labels and baseline policy.
See [`r1_2-audit/README.md`](r1_2-audit/README.md).

## R1.3 workflow validation limitations

R1.3 enumerates all 16 material/non-material combinations for four hand-authored
uncertain SOFT branches. Those outcomes are synthetic labels used to test the code
path that updates edge relevance, advances the snapshot binding, and replans. They are
not human responses and do not estimate how often real creative dependencies are
material. The blinded reviewer worksheet is still blank; no independent human labels
or adjudication exist.

Under these fixtures, GAMO-CA's final planned recomputations range from 12 to 20,
depending on how many branches prove material in the synthetic input. The 8 possible
extra operations were conditional work, not permanently removed work. The independent
field-aware DAG baseline uses the same field data and outcomes and matches GAMO-CA's
actions on all 16 combinations. Therefore the current pilot does not isolate a unique
algorithmic benefit for GAMO-CA over an ordinary DAG with field-level invalidation.
That baseline assumes already validated inputs and does not implement the rest of the
safety kernel.

Replanning/initial planning wall times are measured only around planner calls on small
local fixtures. The field-aware baseline has far less validation and explanation code,
so the large timing difference is an implementation comparison and is not
like-for-like algorithm performance. Neither human review duration nor actual asset
generation was measured. The four-part cost model uses abstract assumptions, not
currency or labor data. Do not start a larger benchmark or claim independent
validation until a second human reviews the worksheet and the graph/edge labels.
Details and exact outputs are in [`r1_3-workflow/README.md`](r1_3-workflow/README.md).

## R1.4 human-validation status

R1.4 adds a reviewer guide and a two-file importer, but no actual reviewer data has
been collected. The importer rejects incomplete worksheets and preserves reviewer
disagreement; agreement-only metrics exclude contested rows without resolving them.
Its engineering tests use temporary synthetic fixtures, not research observations.
The field-aware DAG has no approval eligibility implementation, so it cannot support
an approval-safety comparison. Existing eligibility fields allow only a narrow check
against human approval labels, not evidence of an actual prevented publication. The
five scenario labels remain hand-authored and cannot establish novelty, practical
usefulness, or universal safety. Do not start a larger benchmark until two actual
blinded worksheets are collected and disagreements are inspected. See
[`r1_4-independent-review/README.md`](r1_4-independent-review/README.md).

## Final presentation build limits (2026-10-15)

The final React showcase is a presentation of existing work, not a new research phase.
Its default graph demonstration is a saved, explicitly SIMULATED planning preview
of the existing R1.1 slogan fixture. It does not execute arbitrary proposed changes,
advance authoritative versions, generate assets, approve, or publish. The separately
selected authenticated API view still requires local services and a valid token.

The results dashboard reads preserved CSVs and selects saved R1.2 assumptions/R1.3
synthetic outcomes. The historical R1.1 prose lists different aggregate timing medians
from the actual CSV; the dashboard uses CSV calculations and the discrepancy is
documented under `docs/final-presentation/methodology.md`. All 22 original R1.1–R1.4
files remain preserved. No timing experiment or human response was generated here.

Actual headless Chrome checks passed for the production-built offline flow, including
graph reset, all 16 outcome settings, downloads, and responsive overflow checks.
This is engineering browser evidence, not usability validation or a safety proof.
Seven Python live PostgreSQL/Neo4j tests skipped because their test connection
variables were unset; those services were not retested in this build. The scripted
live-mode browser check verifies the login boundary only, not live authentication.
The three-minute student script has not been evaluated as a timed presentation with
judges. Independent human validation, measurable benefits over equally safeguarded
DAGs, real human effort/cost, and scientific novelty remain unresolved.
