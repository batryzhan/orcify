# Orcify 2.0 — Codex Master Execution Plan

> This is an implementation backlog, not a claim that any code or experiments already exist. Work in order. Check a box only after verifying its acceptance criteria. Keep an execution log under `docs/research/`.

## Global rules
- Read `README.md`, `SKILL.md`, and `docs/research/Orcify_2_0_Research_Concept_2026.pdf` first.
- Default to zero-cost mock providers and seeded synthetic data.
- Never trade off safety invariants for performance.
- At the end of every phase: update docs, run tests, record results and produce a runnable demonstration.
- Preserve experimental reproducibility and distinguish simulated from measured values.

## Mandatory student-research scope (2026-10-14)
- Orcify is a high-school scientific research prototype for the Kazakhstan Republican Scientific Projects Competition, not a SaaS business or production service.
- Prioritize the hypothesis, understandable GAMO-CA logic, fair baselines, reproducible experiments, measured results, and limitations.
- Treat existing PostgreSQL, Neo4j, FastAPI, and React components as frozen demonstration infrastructure. Reuse them; extend only when essential to a research experiment or existing safety invariant.
- Do not add commercial features, enterprise administration/authentication, production-only infrastructure, broad UI work, paid providers, or external publishing.
- Keep experiments small and student-explainable. Before adding a dependency, service, abstraction, or table, document the research need and simpler alternatives.
- Engineering milestones and tests are not scientific results. A planned dataset size, feature, or metric is not complete until its artifact and execution evidence exist.

## Phase 0 — Source alignment and architecture (P0)
- [x] Inspect the research PDF; extract requirements, six invariants, algorithm, experiment design, risks and scope into `docs/research/spec-mapping.md` with page references. **Done:** no requirement silently dropped; ambiguities marked open.
- [x] Review existing incremental computation, DAG caching, GraphRAG and workflow literature; maintain `docs/research/related-work.md` with verifiable links and differences. **Done:** no unsupported novelty claims.
- [x] Create ADR-001 domain boundaries, ADR-002 event log/projection consistency, ADR-003 provider abstraction, ADR-004 dependency semantics, ADR-005 approval invalidation. **Done:** trade-offs recorded.
- [x] Create repo skeleton, editorconfig, license placeholder, gitignore, `.env.example`, AGENTS.md bridge, Makefile or task runner. **Done:** fresh checkout has documented commands.
- [x] Set up CI for Python/TS formatting, lint, typechecking and tests. **Done:** CI fails on deliberate broken test. Local equivalent and rejection gate verified; hosted CI awaits Git/remote setup.

## Phase 1 — Pure domain and GAMO-CA kernel (P0; do before UI)
- [x] Define typed entities: Tenant, Campaign, Brief, Requirement, Evidence, Task, AssetVersion, Feedback, Approval, ChangeEvent, ExecutionRecord, DependencyEdge. **Done:** JSON schemas and round-trip tests.
- [x] Implement immutable version snapshots, stable IDs, timestamps, requirement fingerprints, input fingerprints. **Done:** same inputs produce same hash.
- [x] Implement typed graph representation and cycle detection; enforce tenant boundary. **Done:** unit tests cover disconnected graph, DAG, cycle and cross-tenant edge.
- [x] Implement conservative impact closure across HARD edges; SOFT relevance policy and INFORMATIONAL handling. **Done:** traceable decisions for each edge.
- [x] Implement `plan_change(graph, event, policy) -> Plan` as pure deterministic function. Plan includes `KEEP/RECOMPUTE/REVIEW/BLOCK`, explanation, dependency ordering, expected cost and snapshot hash. **Done:** identical inputs yield identical plan.
- [x] Implement exact-version approval state machine: draft → review → approved/rejected; change invalidates approval eligibility. **Done:** immutable submission/review/approve/reject/revoke chain, actor authorization claims and exact asset/requirement/policy binding; version or requirement changes make old approvals ineligible.
- [x] Implement safe publication eligibility predicate and all six invariants as tests. **Done:** fail-closed check requires an exact current approval and confirmed evidence/requirements; KEEP alone cannot pass. Regression and Hypothesis tests cover scope, version, policy, stale/revoked approval, unresolved dependencies and replay.
- [x] Implement replay/idempotency handling for repeated change IDs and stale snapshots. **Done:** deterministic in-memory reducer returns the original receipt for an exact duplicate and rejects conflicting, stale, gapped, old-version and out-of-order events. Durable effects are not implemented yet.
- [x] Add deterministic toy graph fixtures with a slogan change and an unrelated note change. **Done:** hard changes rerun only affected nodes; unrelated nodes retained.
- [x] Produce `docs/research/algorithm.md`: pseudocode, complexity assumptions, known failure modes and diagrams. **Done:** algorithm, approval/replay contracts, complexity assumptions and limitations documented without LLM output.

## Phase 2 — Persistence and API (P0)
- [ ] Compose local PostgreSQL + Neo4j, health checks and migrations. PostgreSQL 16.15 and Neo4j services responded to live probes earlier; Alembic is now applied through `0007_authenticated_api`. Docker Compose health metadata remains unverified because `docker` is not available in this shell.
- [x] Persist immutable events, snapshots, approvals, artifacts and run logs. Complete graph-change events carry typed snapshot content; graph/replay snapshots, project pointers, revision, outbox, immutable artifact versions, provenance history, and transactional execution lifecycle records are implemented and tested. See ADR-008 and the Phase 2C execution log.
- [x] Build Neo4j projection adapter and reconcile from event log. **Done:** leased ordered outbox delivery, bounded exponential retries/dead-letter status, PostgreSQL checkpoints, tenant-qualified atomic Neo4j snapshot writes, crash-idempotent replay, and authoritative rebuild/reconciliation. Deterministic failure tests and a live PostgreSQL + Neo4j integration test passed; see the Phase 2B experiment entry. Neo4j remains a rebuildable projection.
- [x] Add authenticated FastAPI v1 project, graph snapshot/change, planning, approval transition, artifact, execution history, and eligibility routes. **Done:** typed OpenAPI contract and API tests; campaigns, briefs, requirement confirmation, uploads, and audit endpoints remain separate work.
- [x] Implement verified bearer authentication with tenant isolation and role permissions (tenant_admin/producer/editor/reviewer/researcher). **Done:** credential digests and active memberships are PostgreSQL-authoritative; expiry, revocation, forged identity, 403 and concealed 404 cases tested.
- [ ] Upload and document sanitization endpoints are deferred; they are unnecessary for the synthetic local research study.
- [x] Add idempotency key and optimistic concurrency to graph-change application. **Done:** exact duplicate graph requests replay; conflicting payloads and stale revisions fail closed through the transaction store.
- [x] Provide a deterministic synthetic API seed and real HTTP smoke-test script. The baseline artifact remains unapproved; reviewer approval occurs only in the explicit smoke workflow. See Phase 2E and ADR-010.

### Phase 2D — authenticated API boundary (2026-10-14)

- [x] Establish opaque expiring bearer credentials and server-verified actor identity; persist only token digests.
- [x] Resolve tenant roles from active PostgreSQL membership on each request; reject expired credentials and hide cross-tenant or revoked-membership resources.
- [x] Enforce role checks for project, graph, approval, artifact, execution, planning, and eligibility operations.
- [x] Add typed OpenAPI schemas and endpoints for project create/list/get, authoritative graph read/change, planning, approval submission/approve/reject/revoke, artifact create/read, execution run/attempt lifecycle/history, and eligibility.
- [x] Preserve existing transactions, exact-version approval, idempotency, revision checks, and PostgreSQL-only eligibility. No external publishing path is exposed.
- [x] Verify offline security/route tests and live PostgreSQL migration/auth tests; exact commands and skipped checks are in the Phase 2D experiment log.
- [x] Seeded API smoke demo exists (see Phase 2E). Interactive identity management, per-project roles, uploads, and additional campaign APIs are out of scope under ADR-012.

## Phase 3 — Deterministic demonstration support (existing prototype)
- [x] Use deterministic mock fixtures and confirmed context for the small workflow demonstration. No real model provider is required.
- [x] Preserve explicit human approval and exact-version safety checks in the existing API prototype.
- [ ] Avoid expanding execution/provider infrastructure unless the benchmark requires it; real-provider integration is out of scope for the student study.

### Phase 3A — Authenticated read-only Graph & Impact Explorer (2026-10-14)

- [x] Inspect the current frontend package and OpenAPI contract before implementation; identify and add only required reads for active tenant memberships, project artifacts, and approval history.
- [x] Generate strict TypeScript API types from `docs/api/openapi.json`; use typed API methods for tenant/project scope, graph, planning, artifacts, approval history, and authoritative eligibility.
- [x] Build a responsive React/Vite/Tailwind/React Flow explorer with deterministic graph layout, typed dependency edges, zoom/pan/fit, node selection, and version/provenance/requirement inspection.
- [x] Add in-memory-only development bearer authentication; derive tenant choices from active server memberships and handle unauthorized/expired credentials.
- [x] Add a non-mutating proposed-change planner preview and render actual `KEEP`, `REVIEW`, `RECOMPUTE`, and `BLOCK` planner decisions/reasons; explicitly state that KEEP is not approval.
- [x] Display artifact exact node-version approval history and eligibility from PostgreSQL-backed API responses; failed reads are represented as unavailable.
- [x] Keep graph mutation, artifact creation, approval transition, execution, and publishing controls absent; preserve backend and domain invariants.
- [x] Add web tests for graph mapping/rendering, decision explanations, bearer handling, and authorization errors; wire production build and tests into CI.
- [x] Update OpenAPI, developer startup instructions, ADR-011, experiment log, and limitations. No database migration was required.

Verification evidence is recorded in `docs/research/experiment-log.md`; the explorer
is a read-only engineering prototype, not an evaluated research result.

## Final presentation build — complete existing work, no new research phase

- [x] Inspect the existing UI, API, pure planner, and R1.1–R1.4 artifacts; preserve the research scope and original outputs.
- [x] Add coherent research overview, reusable graph explorer, and saved-results pages with accessible light/purple styling and responsive navigation.
- [x] Export one deterministic existing slogan fixture, verify its decisions against R1.1, and provide explicit offline preview plus repeatable Reset demo. Keep live API mode explicit and authenticated.
- [x] Read original CSVs for pilot counts/reviews/timing, hypothetical sensitivity, and all 16 review/replan outcomes; disclose field-aware DAG equivalence and higher/asymmetric planning overhead.
- [x] Prepare project overview, methodology, three-minute demonstration, ten jury questions, and local startup under `docs/final-presentation/`.
- [x] Finish frontend/Python gates, production build, actual browser visual/behavior checks, and verify all preserved research hashes; record exact results in the experiment log. **Verified:** 112 Python passed / 7 live skips; 3 contract + 15 web tests passed; headless Chrome production-preview checks passed including all 16 outcome settings. See `docs/final-presentation/verification.md`.

This is the final presentation of existing work, not R1.5/R2. Human-validation and
equal-safeguard comparison gates below remain open; no research finding is invented
to complete a presentation checklist.

## Phase 4 — Product expansion (deferred and out of scope)
No campaign dashboard, onboarding wizard, upload/review suite, broad run-monitor UI, or design-polish sprint is planned. The existing read-only explorer is sufficient for the minimal demonstration. Reopen this phase only if a specific experiment cannot be shown or audited with existing tools; document that research need first.

## Phase 5 — Benchmark and baselines (P0 for scientific claim)
- [x] Phase R1.1 minimal pilot: define a scenario-authored oracle before planner execution, implement Full Recompute and Conventional DAG Incremental independently, compare all three methods on five identical synthetic workloads, and save CSV/SVG outputs. **Done:** 15/15 plans passed the limited oracle; operation counts and descriptive plan timings are recorded in `docs/research/r1_1-pilot/README.md` and `docs/research/experiment-log.md`. This is not a statistical benchmark.
- [x] Phase R1.2 audit of R1.1: assess oracle independence and input/safety comparability; explain the 12-versus-21 count; identify review-gated work; report all five scenario reasons and unfavorable planning time; add a clearly hypothetical, separated cost model and sensitivity table. R1.1 artifacts remain unchanged. See `docs/research/r1_2-audit/README.md` and the R1.2 experiment entry.
- [x] Phase R1.3 preparation: create a blinded, blank worksheet for all five synthetic cases; document independent labeling, approval-label separation, and disagreement handling. No human responses were created. See `docs/research/r1_3-workflow/review-worksheet.csv` and `human-review-protocol.md`.
- [x] Evaluate all 16 synthetic outcomes for the four unresolved SOFT branches; rerun the pure planner after updating field evidence and snapshot binding; record final planned recomputations, reviews, replanning calls, and timing. Add an independent field-aware DAG baseline using the same relevance metadata and update the four-part hypothetical cost model. See the R1.3 report and CSVs.
- [ ] Obtain and preserve an actual second human's blinded worksheet before claiming independent labels or beginning a larger benchmark. R1.3's material/non-material outcomes are synthetic test inputs only.
- [ ] Have a second human review the scenario graph labels, oracle obligations, global approval-fingerprint assumption, and baseline fairness. Do not scale the dataset until this review is complete.
- [x] Phase R1.4 preparation: add a student-friendly reviewer guide and a strict importer that requires two complete, distinct worksheets, records source hashes, reports disagreements without adjudication, and compares algorithm outputs against each reviewer and agreement-only rows. Engineering tests use temporary synthetic rows only; no human responses are present. See `docs/research/r1_4-independent-review/`.
- [ ] Collect two actual blinded worksheets and inspect disagreements before reporting independent accuracy or beginning a larger benchmark. The importer has not been run on human data.
- [ ] Reassess approval, provenance, and recovery benefits against an ordinary DAG with equivalent safeguards; existing evidence does not isolate an algorithmic advantage.
- [x] Synthetic regression verifies that each of the four review-gated HARD descendants recomputes after a material resolution and remains KEEP after a non-material resolution. This does not replace the independent human-label gate above.
- [ ] Define a small JSONL experiment format, annotation guide, and independent ground-truth review process; document label disagreements.
- [ ] Create a bounded synthetic pilot (start with 5 workflows × 4 changes = 20 only if student review time allows); save the actual dataset version and seed. The proposed 24 × 6 dataset is not required or complete.
- [ ] Implement and explain simple baseline A (full replay) and baseline B (ordinary DAG caching) on identical inputs.
- [ ] Run GAMO-CA on the same cases and confirm each approach receives equivalent information.
- [ ] Record raw per-case impact correctness, recomputations, safety outcomes, and measured runtime; leave unavailable cost/token values missing.
- [ ] Repeat a small paired experiment with a fixed seed; report actual distributions and uncertainty only when supported by data.
- [ ] Run a small number of ablations only when they answer a stated hypothesis and remain student-explainable.
- [ ] Write `docs/research/results.md` only after experiments have run; include failures and negative findings.

## Phase 6 — Research communication and bounded checks
- [ ] Re-run existing safety regressions for the actual experiment code and report command and result.
- [ ] Measure planner runtime on the pilot only when it answers the research question; record machine and graph size.
- [ ] Document synthetic-data limits, label review, consent boundaries, and threats to validity.
- [ ] Prepare a short student-led explanation and reproduction guide; the student must explain each formula and result independently.
- [ ] Draft the Kazakh research report from verified observations; leave results planned until data exists.

## Milestones / gates
**Gate A:** domain planner + invariants proven by automated tests (before serious UI).  
**Gate B:** API + persistence + offline demo.  
**Gate C:** complete reviewer workflow and graph visualization.  
**Gate D:** paired benchmark + ablations + real measured report.  
**Gate E:** reproducible scientific report and student-led defense; no product polish requirement.

## First Codex work session — execute now
1. Read all project docs and the research PDF.
2. Summarize exact source-aligned requirements and open decisions.
3. Scaffold repo, pure domain package, pytest and CI.
4. Implement the typed entities, HARD/SOFT/INFORMATIONAL graph, toy fixtures and initial failing invariant tests.
5. Run tests; update this file with actual status; report blockers and next step.

**Do not build a landing page first. Do not skip algorithm tests to generate visual polish.**

## Verified execution status — 2026-10-14

Phase 0 and all Phase 1 tasks are complete for the pure offline kernel. Evidence and
exact commands are in `docs/research/experiment-log.md`. Gate A's automated kernel
check is reached for the current test suite; this is not a proof of universal safety.
Phase 2 persistence now includes SQLAlchemy/Alembic authority storage, immutable graph
and replay snapshots, pure-kernel-validated approvals, typed graph changes, a retryable
Neo4j projection worker, immutable artifact versions/provenance, and transactional
execution lifecycle history. PostgreSQL persistence was verified against live local
PostgreSQL; `0007_authenticated_api` is current. Phases 2D–2E provide authenticated
typed routes for projects, graph snapshots and changes, planning, approvals, artifacts,
executions, and eligibility. The API uses opaque bearer-token digests and current
tenant membership records. Live PostgreSQL and Neo4j integration plus the seeded HTTP
demo passed; the smallest useful React milestone is ready to scope. Compose health
metadata remains unverified because no Docker CLI is discoverable in this shell. See
the Phase 2B–2E experiment-log entries.

### Phase 2E — live API validation and seeded demo (2026-10-14)

- [x] Exercise authenticated FastAPI project, planning, graph, artifact, approval, and eligibility routes against live PostgreSQL.
- [x] Revalidate the PostgreSQL transactional outbox, Neo4j projection, and reconciliation/rebuild path against live services.
- [x] Add deterministic synthetic tenant/user/project/graph/requirement/artifact seed data with expiring server-provisioned credentials; keep the sample artifact unapproved.
- [x] Add a real HTTP smoke workflow for exact-version approval, confirmed requirement change, invalidation, recomputation, and fail-closed stale eligibility.
- [x] Check cross-tenant concealment, revoked credentials, and concurrent idempotent HTTP retries.
- [x] Verify Neo4j reconciliation rebuild does not change PostgreSQL revision or snapshot pointers.
- [x] Document PostgreSQL, Neo4j, API, and projection worker startup; no external publishing/provider is invoked.
- [x] Record live, offline, skipped, and unavailable-tool evidence in the Phase 2E experiment entry.
- [ ] Inspect Docker Compose container health metadata in an environment with Docker CLI available.

The live HTTP scenario passed with PostgreSQL 16.15 and Neo4j reachable. These checks are
engineering integration evidence, not a scientific benchmark or universal safety proof.
