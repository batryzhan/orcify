# Orcify 2.0 — Codex Master Execution Plan

> This is an implementation backlog, not a claim that any code or experiments already exist. Work in order. Check a box only after verifying its acceptance criteria. Keep an execution log under `docs/research/`.

## Global rules
- Read `README.md`, `SKILL.md`, and `docs/research/Orcify_2_0_Research_Concept_2026.pdf` first.
- Default to zero-cost mock providers and seeded synthetic data.
- Never trade off safety invariants for performance.
- At the end of every phase: update docs, run tests, record results and produce a runnable demonstration.
- Preserve experimental reproducibility and distinguish simulated from measured values.

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
- [ ] Implement exact-version approval state machine: draft → review → approved/rejected; change invalidates approval eligibility. **Done:** no implicit approval inheritance.
- [ ] Implement safe publication eligibility predicate and all six invariants as tests. **Done:** adversarial and property-based tests pass.
- [ ] Implement replay/idempotency handling for repeated change IDs and stale snapshots. **Done:** no duplicated side effects.
- [ ] Add deterministic toy graph fixtures with a slogan change and an unrelated note change. **Done:** hard changes rerun only affected nodes; unrelated nodes retained.
- [ ] Produce `docs/research/algorithm.md`: pseudocode, complexity assumptions, known failure modes and diagrams. **Done:** every action can be explained without LLM output.

## Phase 2 — Persistence and API (P0)
- [ ] Compose local PostgreSQL + Neo4j, health checks and migrations. **Done:** one command starts dependencies.
- [ ] Persist immutable events, snapshots, approvals, artifacts and run logs. **Done:** restart retains all state.
- [ ] Build Neo4j projection adapter and reconcile from event log. **Done:** projection can be rebuilt and checked for drift.
- [ ] Add FastAPI v1 routes for campaign creation, brief upload, requirement confirmation, graph query, preview/apply change, plan inspection, approval and audit. **Done:** OpenAPI + integration tests.
- [ ] Implement authorization with tenant isolation and role permissions (producer/editor/reviewer/researcher). **Done:** 403/404 semantics tested for unauthorized access.
- [ ] Add upload size/type validation, content sanitization and audit logging. **Done:** malformed uploads fail safely.
- [ ] Add idempotency key and optimistic concurrency to change application. **Done:** parallel updates cannot silently overwrite approvals.
- [ ] Provide seeded demo data, migrations and API smoke-test script. **Done:** from clean DB, demo works without credentials.

## Phase 3 — Execution and AI integration (P1)
- [ ] Define provider interface `generate(task, confirmed_context, limits) -> result+usage+provenance` and deterministic MockProvider. **Done:** offline integration tests.
- [ ] Implement context assembly from **confirmed** requirement versions only, with source IDs and tenant filter. **Done:** unverified extraction excluded.
- [ ] Implement draft content task types: campaign concept, ad copy, storyboard outline. **Done:** mock fixtures exercise versioning and dependencies.
- [ ] Implement dependency-ordered executor with bounded concurrency, retry/backoff, timeout and failure recording. **Done:** partial failure does not mark plan complete.
- [ ] Implement optional real LLM adapter using environment secrets; no paid calls in CI. **Done:** contract tests mocked and cost limit enforced.
- [ ] Implement human review and explicit approval endpoint; publication remains simulation-only. **Done:** no automatic approval via model.
- [ ] Record input hashes, model/prompt versions, output hashes, token usage, latency and cost when available. **Done:** full trace reconstructible.

## Phase 4 — Research-grade UI (P1)
- [ ] Set up React/TS/Vite/Tailwind/shadcn/ui app with design tokens and responsive shell. **Done:** mobile and desktop layouts work.
- [ ] Implement campaigns dashboard, new campaign wizard, upload brief and requirement confirmation view. **Done:** validation and accessibility tested.
- [ ] Implement graph explorer in React Flow with typed edge legend, versions, evidence, selection and filter. **Done:** graph matches API and supports keyboard inspection.
- [ ] Implement change-event editor and side-by-side plan preview. **Done:** shows `KEEP/RECOMPUTE/REVIEW/BLOCK` and reasons.
- [ ] Implement asset version history, diff, feedback, review and approval. **Done:** exact-version approval clearly visible.
- [ ] Implement run monitor, timeline, error states and audit trail. **Done:** failed executions never appear successful.
- [ ] Implement research dashboard with measured/simulated labels and CSV export. **Done:** no placeholder metrics misrepresented.
- [ ] E2E test three demo flows (slogan change, unrelated note, approval invalidation). **Done:** tests run headless in CI.

## Phase 5 — Benchmark and baselines (P0 for scientific claim)
- [ ] Define benchmark JSONL schema and annotation rubric for gold impacted nodes, approval outcomes and evidence. **Done:** schema validated.
- [ ] Create **pilot**: 5 synthetic campaigns × 4 changes = 20 cases. **Done:** independent review of labels and saved dataset version.
- [ ] Create **main planned benchmark**: 24 campaigns × 6 changes = 144 cases. **Done:** dataset published internally with seed, splits and gold labels; report actual count.
- [ ] Implement baseline A full replay. **Done:** all eligible downstream tasks re-executed; correct output state.
- [ ] Implement baseline B ordinary DAG caching. **Done:** standard fingerprint-based cache without approval-aware policy.
- [ ] Implement baseline C graph-context-only orchestration. **Done:** retrieval advantages isolated from replanning policy.
- [ ] Implement GAMO-CA treatment on identical scenarios and model fixtures. **Done:** equal input access and logged exceptions.
- [ ] Measure impact precision/recall, HARD recall, reruns, latency, cost, approval violations, provenance completeness and failure recovery. **Done:** raw per-event CSV and aggregation script.
- [ ] Run repeated paired experiments with pinned seed/config; bootstrap confidence intervals and uncertainty. **Done:** reproducible outputs from raw data.
- [ ] Perform ablations (remove typed edges, temporal versioning, approval awareness). **Done:** explain what each removal changes.
- [ ] Include negative/failure cases and overhead at small graph sizes. **Done:** honest limitations documented.
- [ ] Write `docs/research/results.md` only from recorded observations. **Done:** all plots regenerated by script, with provenance.

## Phase 6 — Security, performance and research packaging (P1)
- [ ] Run tenant-isolation, prompt-injection, stale-approval, race-condition and replay attack tests. **Done:** all critical tests pass.
- [ ] Measure planner time/memory as graph size grows; identify complexity/overhead limits. **Done:** raw data and plot included.
- [ ] Improve accessibility, error recovery and UI performance; profile before optimizing. **Done:** recorded before/after measurements.
- [ ] Document data protection, consent and human evaluation protocol; use only synthetic/authorized data. **Done:** ethics checklist complete.
- [ ] Produce a 3-minute demo script and reproducibility guide for judges. **Done:** fresh machine can replay the demo offline.
- [ ] Produce research paper outline in Kazakh: abstract, introduction, related work, method, hypotheses, experiment, results, limitations, conclusion, references. **Done:** no unmeasured claims.

## Milestones / gates
**Gate A:** domain planner + invariants proven by automated tests (before serious UI).  
**Gate B:** API + persistence + offline demo.  
**Gate C:** complete reviewer workflow and graph visualization.  
**Gate D:** paired benchmark + ablations + real measured report.  
**Gate E:** polished presentation and scientific manuscript.

## First Codex work session — execute now
1. Read all project docs and the research PDF.
2. Summarize exact source-aligned requirements and open decisions.
3. Scaffold repo, pure domain package, pytest and CI.
4. Implement the typed entities, HARD/SOFT/INFORMATIONAL graph, toy fixtures and initial failing invariant tests.
5. Run tests; update this file with actual status; report blockers and next step.

**Do not build a landing page first. Do not skip algorithm tests to generate visual polish.**

## Verified execution status — 2026-10-14

Phase 0 and the first five Phase 1 tasks are complete. Evidence and exact commands:
`docs/research/experiment-log.md`. Next sequential task: exact-version approval
state machine, followed by publication eligibility/invariant coverage and replay.
Toy fixtures and provisional algorithm notes are already used to test the kernel;
their later checkboxes remain unchecked until preceding safety tasks are verified.
Gate A has **not** been reached. No benchmark run, human gold review, paid provider,
production API, database migration or UI is claimed complete.
