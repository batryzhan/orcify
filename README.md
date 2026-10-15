# Orcify 2.0 — Student Research Prototype

> Status: A high-school scientific research prototype for Kazakhstan's Republican Scientific Projects Competition. This repository is not a SaaS product or production-ready service. Its success depends on explainable algorithms and reproducible measurements, not feature count.

## Final presentation build

Start the existing React application from this repository:

```powershell
npm ci
npm run dev
```

Open the Vite URL (normally `http://127.0.0.1:5173/`). The presentation opens without
credentials and provides **Research overview**, **Graph & impact**, and
**Experiments & results**. The default graph demo is explicitly **SIMULATED / OFFLINE**:
it uses the original slogan-change fixture and verified saved Python planner output,
has a Reset demo action, and performs no generation, approval, publication, or database
write. Live API remains available as an explicit mode with the existing bearer login.

Results are loaded directly from preserved R1.1–R1.3 CSVs, including unfavorable
planning overhead and the field-aware DAG match. R1.4 independent human validation
remains incomplete. This build is presentation completion, not a new research phase.

See [`docs/final-presentation/startup.md`](docs/final-presentation/startup.md), the
[three-minute demo script](docs/final-presentation/demo-script.md),
[methodology](docs/final-presentation/methodology.md), and
[jury questions](docs/final-presentation/jury-questions.md). Check that the demo still
matches the planner and all 22 preserved research files with:

```powershell
.venv/Scripts/python scripts/export_presentation.py --check
```

No dependency, backend service, API endpoint, or database migration was added for the
presentation. The existing backend and pure safety kernel remain the research support.

## 1. Mission
Build a small, reproducible high-school research prototype that studies whether **GAMO-CA (Graph-Aware Memory Orchestration — Change & Approval)** can reduce unnecessary recomputation compared with full replay and ordinary DAG caching while preserving explicit approval constraints in a creative workflow. The student should be able to explain the problem, algorithm, experiments, and limitations independently.

This repository is **not** a generic chatbot, AI content generator, or no-code automation clone. The research engine and reproducible benchmark are the core; the UI is an explanation and demonstration layer.

## 2. Source of truth and scientific boundaries
Primary specification: `Orcify_2_0_Research_Concept_2026.pdf` in `docs/research/`. This README operationalizes its conceptual design, but where ambiguous, create an ADR and do not invent findings. Scientific novelty is a **hypothesis**, not an established claim. Incremental recomputation, graph databases, workflow scheduling, and RAG are pre-existing ideas; the student must compare fairly and discuss limitations.

Research scenario: one small synthetic advertising workflow, such as brief → confirmed requirement → copy → storyboard → review. Keep the example small enough to explain at a school competition; no real customer data or publication side effect is needed.

## 3. Research demonstration
The demonstration uses one small synthetic creative workflow: change a confirmed requirement or asset, inspect the graph impact, and compare GAMO-CA decisions (`KEEP`, `REVIEW`, `RECOMPUTE`) with simple baseline algorithms. Approval checks illustrate the safety constraint; no external publication occurs. The existing authenticated API and read-only graph explorer are supporting demonstration tools, not commercial product surfaces.

## 4. Strict student-project scope
**In:** an understandable Python GAMO-CA kernel; a small typed dependency graph; immutable version and approval examples; deterministic synthetic fixtures; simple baselines; experiment scripts; raw results and analysis; focused automated tests; and a minimal read-only graph/impact demonstration.

**Frozen supporting infrastructure:** the existing FastAPI, PostgreSQL, Neo4j projection, and React explorer may be used to run and show the research. Keep them stable. Make changes only when required to demonstrate the hypothesis, protect an existing safety invariant, or make an experiment reproducible.

**Out of scope:** SaaS/commercial features, billing, subscriptions, onboarding, organization administration, enterprise identity, real-time collaboration, complex deployment, new infrastructure layers, production hardening unrelated to the local study, broad UI work, paid AI APIs, and external publication. Do not add a dependency, service, abstraction, or database table without stating its direct research need and simpler alternatives.

## 5. Small research architecture
```text
Small Python graph fixtures -> pure GAMO-CA planner -> baseline comparison -> raw experiment records
                                      |
                     existing API / graph explorer for demonstration only
```
Keep the algorithm independent from web, database, and model frameworks. Reuse existing infrastructure; prefer local scripts and straightforward data structures for experiments. Do not add workers or distributed services for hypothetical scale.

## 6. Domain model
Nodes: Tenant, Client, Brand, Campaign, Brief, Requirement, Task, Asset, AssetVersion, Feedback, Approval, Evidence, Execution, ChangeEvent. Every persisted node has `tenant_id`, `project_id` where applicable, `id`, timestamps and schema version. Relationships: `OWNS`, `HAS_BRIEF`, `DEFINES`, `DEPENDS_ON`, `PRODUCES`, `REVISES`, `REFERENCES`, `APPROVES`, `INVALIDATES`, `DERIVED_FROM`, `AFFECTS`.

Use immutable `AssetVersion` and immutable `Approval` records. Approvals apply to **exact version + exact requirement snapshot**. A new asset version does not inherit approval. Provenance records source IDs, extracted spans, timestamps, producer/model and input fingerprint. Never confuse unverified model extraction with a confirmed requirement.

### Dependency semantics
- **HARD:** changed upstream version must invalidate/recompute dependent result.
- **SOFT:** inspect relevance; retain with explanation or mark for review.
- **INFORMATIONAL:** retain; record why no recomputation is necessary.

Changes must carry type, old/new values or hashes, source, actor, time, scope, and a stable event ID. Invalidation is conservative where relevance is uncertain.

## 7. GAMO-CA planning contract
Input: current versioned graph `G`, change event `e`, available execution policies and cost estimates.
Output: deterministic plan with action per affected node (`KEEP`, `RECOMPUTE`, `REVIEW`, `BLOCK`), causal explanation, expected cost/latency, provenance and plan hash.

1. Validate tenant/project boundaries, permissions and change schema.
2. Resolve impacted source versions and typed downstream edges.
3. Compute conservative candidate impact set.
4. For each node, compare actual consumed input fingerprints with current required versions.
5. Propagate HARD invalidation; inspect SOFT dependencies using explicit deterministic rules (optional learned predictor must be separately evaluated).
6. Invalidate stale approvals and mark publication eligibility as blocked.
7. Build dependency-respecting execution plan; preserve reusable results only when evidence supports reuse.
8. Record plan, execution, errors, retries and reviewer decisions in append-only audit history.

Safety is a hard constraint, not a term traded away for token savings. A simple exploratory objective for feasible plans is `J = α normalized_cost + β normalized_latency + γ normalized_recomputation`, subject to all invariants; report individual metrics separately. Do not pretend this optimization is solved globally unless actually implemented.

## 8. Mandatory invariants
1. No cross-tenant retrieval or execution.
2. No publication without explicit approval of the exact current asset version and relevant requirement snapshot.
3. Changed HARD dependency never silently reuses a stale derived result.
4. Approval never automatically transfers to a revised asset.
5. Every derived output links to its input versions and evidence/provenance.
6. Replays and retries are idempotent: same event ID does not duplicate irreversible actions.

Design property-based and adversarial tests for each invariant.

## 9. Baselines and research protocol
The first executed pilot compares **Full Recompute**, **Conventional DAG Incremental**, and **GAMO-CA** on identical small synthetic scenarios. A graph-context retrieval condition is a separate question and is not included. The R1.1 pilot has five authored scenarios, not an independently annotated benchmark. Its oracle obligations, counts, measured plan timings, and limitations are documented in [`docs/research/r1_1-pilot/README.md`](docs/research/r1_1-pilot/README.md). Do not start a larger campaign until a second human reviews the cases and oracle.

The proposed 5×4 and 24×6 dataset sizes in the research concept remain planning targets, not completed studies. Future experiments should use independently reviewed impacted-node labels and equal information access; record runtime, recomputation and review work separately. Report actual distributions and failure cases. Do not claim statistical significance from the small R1.1 pilot, and do not fabricate scores, costs, or charts.

## 10. Suggested repository structure
```text
orcify/
  README.md TASK.md SKILL.md AGENTS.md
  docs/research/ docs/adr/ docs/api/
  apps/web/src/{app,components,features,lib}
  services/api/app/{api,domain,schemas,services,adapters,security}
  packages/gamo_ca/{model,planner,policies,explain,tests}
  packages/benchmark/{datasets,baselines,runner,metrics,reports}
  infra/{docker,sql}
  tests/{integration,e2e,security}
  scripts/ .github/workflows/
```
`AGENTS.md` can be a small bridge pointing Codex to the three authoritative files.

## 11. Local developer experience
Local tools: Python 3.12+, Node 22+, and the existing Docker Compose setup for the API demonstration. Keep deterministic fixtures as the default; no API key, paid service, or real customer data is required. Prefer a simple script and saved configuration for research runs. Do not build new deployment infrastructure for scale that this study does not need.

## 12. API boundary

Phases 2D–2E provide an authenticated FastAPI v1 prototype and live PostgreSQL/Neo4j validation for tenant-scoped project,
graph, planning, approval, artifact, execution, and eligibility operations. The API
uses expiring opaque bearer credentials whose digests and tenant role assignments are
stored in PostgreSQL. It does not accept client-supplied actor or reviewer identity as
authority. See [ADR-009](docs/adr/009-authenticated-api-boundary.md),
[`services/api/README.md`](services/api/README.md), and the generated
[OpenAPI contract](docs/api/openapi.json). Tenant roles are currently shared across
projects in that tenant. There is no interactive login, SSO, or public token issuance.

## 13. Definition of research success
A student can explain the question and GAMO-CA in two minutes, walk through a small creative graph, explain each decision and formula, fairly compare it with existing approaches, reproduce the recorded measurements from the saved data and scripts, discuss limitations, and defend the work independently. Engineering tests demonstrate code behavior; they are not scientific performance results.

## 14. Phase 1 pure-kernel milestone (historical)

Requires Python 3.12+ and Node 22+. This milestone is a pure offline plan preview;
it does not start a web app, approve content or publish. No Docker, API key or `.env`
is needed. Python 3.14.6 / Node 24.18.1 were checked locally; CI targets Python
3.12/3.14 and Node 22. Hosted CI has not run (this folder had no Git repository).

PowerShell setup and verification from this directory:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.lock
.venv/Scripts/python -m pip install --no-deps -e .
npm ci
.venv/Scripts/python scripts/tasks.py check-python
.venv/Scripts/python scripts/tasks.py schemas --check
.venv/Scripts/python scripts/tasks.py verify-test-gate
npm run format:check
npm run lint
npm run typecheck
npm test
.venv/Scripts/python scripts/tasks.py demo
```

Bash uses `.venv/bin/python` in place of `.venv/Scripts/python`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
npm ci
.venv/bin/python scripts/tasks.py check-python
.venv/bin/python scripts/tasks.py schemas --check
.venv/bin/python scripts/tasks.py verify-test-gate
npm run format:check
npm run lint
npm run typecheck
npm test
.venv/bin/python scripts/tasks.py demo
```

Developer runner also provides `test`, `lint`, `format`, and `schemas` (regenerate
contracts, then `npm run format`). The demo prints both synthetic scenarios as
JSON: slogan change rebuilds copy/storyboard and holds visual outputs for review;
unrelated note retains results. All estimates are SIMULATED, not timed trials.
Generated schemas are under `docs/api/schemas`, and the same Python plan fixture
is consumed by TypeScript tests. `schemas --check` detects cross-language drift.

The scientific source is mapped in `docs/research/spec-mapping.md`; decisions live
in `docs/adr/001` through `005` (full filenames in that directory). The source's
six invariants and the README's six invariants are both required. Baseline B2 will
follow the PDF's **versioned graph + DAG without approval/risk policy**; graph
retrieval comparisons are a separate study. No benchmark or independent gold
annotation has been completed. Phase 1 includes an immutable exact-version
approval chain, fail-closed publication eligibility, and deterministic in-memory
event replay. These pure functions do not provide authenticated sessions, durable
database transactions, or external publishing. See `docs/research/limitations.md`
and `TASK.md` for remaining gates.

## 15. Authenticated API prototype

After applying migrations, provision an identity from an operator-controlled shell.
The provisioning command prints a random token once; store it in a secret manager and
pass it as a Bearer credential. The server stores only its SHA-256 digest.

```powershell
.venv/Scripts/python -m alembic -c services/api/alembic.ini upgrade head
.venv/Scripts/python scripts/provision_api_identity.py --tenant demo-tenant --actor operator-1 --role tenant_admin
.venv/Scripts/python -m uvicorn services.api.app.http:app --host 127.0.0.1 --port 8000
```

OpenAPI and interactive documentation are served at `/openapi.json` and `/docs`.
The API checks current membership on each request, hides cross-tenant resources,
recomputes plans before approval/artifact/run writes, and evaluates eligibility from
PostgreSQL within the existing project lock. Do not expose the development database
credentials or token output from provisioning in shared logs. See ADR-009 for the
authentication assumptions and deployment limitations.

## 17. Phase 3A Graph & Impact Explorer

The read-only browser explorer uses the authenticated API and generated contract in
`apps/web/src/api/generated.ts`. From the repository root, install the locked workspace
dependencies, start the API as above, then run:

```powershell
npm ci
npm run web:dev
```

Open the Vite URL shown in the terminal. The development server proxies `/api` to
`http://127.0.0.1:8000`; override this server-side with `ORCIFY_API_PROXY` if the API
is elsewhere. The login form accepts a server-provisioned bearer token. The seeded
demo token is stored in the ignored local `var/demo-tokens.json` file. Paste it into
the form locally; the browser keeps it only in memory until sign-out or tab close.
Do not copy the token into a URL, source file, or shared terminal log.

For a separately hosted web origin, set `VITE_API_BASE_URL` at build time and configure
the API `ORCIFY_WEB_ORIGINS` to the exact allowed origins. The default allow-list is
limited to local Vite origins. OpenAPI types can be regenerated with `npm run web:types`.
The UI reads authorized tenant memberships and project lists from FastAPI, retrieves
the authoritative PostgreSQL graph snapshot, previews plans, and reads exact-version
approval history and eligibility. Its planner form does not mutate the graph; approval,
artifact creation, execution, and publication controls are not included. See
[ADR-011](docs/adr/011-read-only-graph-explorer.md) and the Phase 3A experiment entry.

## 16. Phase 2E local API demo

The API demo uses deterministic synthetic graph and artifact fixtures, local PostgreSQL,
and a rebuildable Neo4j projection. It calls no paid provider and has no publishing
route. The seeded `demo-copy-v1` artifact is deliberately unapproved; the smoke scenario
creates a separate project and submits an exact version to a reviewer explicitly.
Generated demo credentials are random, expire after two days, and are written to the
git-ignored `var/demo-tokens.json` file. The seed script rotates active demo credentials
when re-run. Keep this file local and remove it when finished.

In PowerShell, start PostgreSQL and Neo4j with Docker Desktop, apply migrations, and
seed the demo tenant, users, baseline project and unapproved sample artifact:

```powershell
docker compose -f infra/compose.yaml up -d --wait
$env:DATABASE_URL = "postgresql+psycopg://orcify:orcify-local-dev@localhost:5432/orcify"
$env:NEO4J_URI = "bolt://localhost:7687"
$env:NEO4J_USER = "neo4j"
$env:NEO4J_PASSWORD = "orcify-local-dev"
.venv/Scripts/python -m alembic -c services/api/alembic.ini upgrade head
.venv/Scripts/python scripts/seed_demo.py
```

Run the API and projection worker in separate PowerShell terminals. Set the same four
database variables in each terminal before launching the process:

```powershell
.venv/Scripts/python -m uvicorn services.api.app.http:app --host 127.0.0.1 --port 8000
```

```powershell
.venv/Scripts/python scripts/run_projection_worker.py
```

With the API and worker running, execute the network HTTP smoke scenario from another
terminal. Use a unique `--run-id` for each run; a fixed value reproduces the same
synthetic records on a fresh database. The smoke scenario leaves its project and
append-only audit records in PostgreSQL for inspection:

```powershell
.venv/Scripts/python scripts/run_api_smoke.py --run-id demo-001
```

The command checks bearer authentication, project create/read, impact planning, artifact
creation and exact-version human approval, concurrent idempotent graph writes,
requirement-change recomputation, stale artifact eligibility, cross-tenant and revoked
credential denial, and Neo4j reconciliation from PostgreSQL. It reports synthetic and
deterministic-mock labels explicitly. To run the pytest integration against the live
services, set `ORCIFY_TEST_DATABASE_URL`, `ORCIFY_TEST_NEO4J_URI`,
`ORCIFY_TEST_NEO4J_USER`, and `ORCIFY_TEST_NEO4J_PASSWORD`, then run:

```powershell
.venv/Scripts/python -m pytest -q services/api/tests/test_phase2e_live_e2e.py services/api/tests/test_projection_integration.py
```

The smoke command intentionally does not create a publication request or contact an
external service. PostgreSQL alone decides current artifact eligibility. A passed
engineering smoke check is not a scientific benchmark or universal safety proof.

## 18. R1.1 minimal scientific pilot

The next research step is a local Python-only comparison with three algorithms and
five small synthetic workflow changes. It uses the pure GAMO-CA planner and two
independently implemented baselines. To reproduce the pilot from the repository root:

```powershell
.venv/Scripts/python scripts/r1_1_pilot.py --seed 20261014 --timing-repeats 101
.venv/Scripts/python -m pytest -q tests/test_r1_1_pilot.py
```

Results are saved under `docs/research/r1_1-pilot/` as CSV, a run manifest, and SVG
plots. The oracle and operation definitions, actual observations, and limitations are
in that folder's README. These five hand-authored synthetic cases are a methodology
pilot, not a statistically meaningful benchmark or an independently reviewed study.
