# Orcify 2.0 — Research-first Creative Workflow Orchestration

> Status: **Phase 0, Phase 1, and Phase 2A–2E backend milestones are implemented and locally validated.** Real provider execution and UI remain unfinished. Never present simulated outcomes as measured results.

## 1. Mission
Build a reproducible research prototype for small creative agencies that coordinate AI services while tracking changing briefs, brand rules, asset versions, feedback and human approvals. The research question is whether **GAMO-CA (Graph-Aware Memory Orchestration — Change & Approval)** can reduce unnecessary recomputation relative to full replay and ordinary DAG caching **without violating safety/approval constraints**.

This repository is **not** a generic chatbot, AI content generator, or no-code automation clone. The research engine and reproducible benchmark are the core; the UI is an explanation and demonstration layer.

## 2. Source of truth and scientific boundaries
Primary specification: `Orcify_2_0_Research_Concept_2026.pdf` (place a copy in `docs/research/`). This README operationalizes its conceptual design, but where ambiguous, create an ADR and do not invent findings. Scientific novelty is a **hypothesis**: combining temporal/versioned evidence, typed dependencies, approval-aware invalidation and safe selective replanning in creative workflows. Incremental recomputation, graph databases, workflow scheduling and RAG are pre-existing ideas. Literature review and baselines must reflect this.

Research scenarios: advertising campaign creation, e.g. client brief → brand rules → concept → copy → storyboard → revision → approval → publication eligibility. Keep a human responsible for publication.

## 3. Users and MVP journeys
- **Producer:** creates a campaign, uploads a brief, sees parsed requirements and confirms them.
- **Creative editor:** generates or edits copy/storyboard draft, sees provenance and version differences.
- **Reviewer:** requests changes, approves a specific immutable version, can reject or revoke approval.
- **Researcher:** injects change events, views GAMO-CA decisions and compares benchmark runs.

Demo journey: create campaign from sample brief; approve extracted requirements; generate a draft; approve version 1; change a brand rule; observe affected nodes, invalidated approval and targeted re-execution; inspect audit trail and comparison with full replay/DAG cache. Publication must remain blocked until new version is approved.

## 4. Scope
**In:** versioned campaign graph; provenance; typed change impact; rule-based GAMO-CA; durable execution log; mock AI provider; real provider adapter behind configuration; approval gate; visualization; benchmark harness; CSV/JSON reports; tests.

**Out of MVP:** automated publishing to social platforms; payments; collaborative real-time editing; model training from private customer data; arbitrary user-defined executable code; fully autonomous approval; complicated multi-cloud deployment.

## 5. Architecture
```text
React + TypeScript + Vite + Tailwind + shadcn/ui + React Flow
                   | REST / WebSocket
             FastAPI / Pydantic
                   |
        Application / domain services
       /           |               \
Versioned graph  GAMO-CA planner   Workflow executor
Neo4j adapter    pure Python       mock/LLM adapters
       \           |               /
        PostgreSQL event log + approvals
                   |
        Artifact storage (local in dev)
                   |
      Benchmark runner / report exporter
```
Keep the domain and algorithm independent from web, database and LLM frameworks. Prefer simple synchronous execution for initial MVP; introduce Redis/worker only after demonstrable need.

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
Four modes on identical cases: **full replay**, **ordinary DAG cache**, **graph-context only**, **GAMO-CA**. Optional manual workflow is a separate human usability study, not directly comparable as algorithm runtime.

Pilot: 5 campaigns × 4 change events = 20. Main planned benchmark: 24 campaigns × 6 change events = **144** events. These are target dataset sizes, **not completed experiments**. Construct gold impacted nodes with independently reviewed annotations. Include changes to slogans, budget, brand color, legal disclaimers, approvals, unrelated notes and cross-client distractors. Randomize case order and repeat runs; fix model versions, prompts, data and budget.

Metrics: impacted-node precision/recall (HARD recall prioritized), unnecessary rerun count, total execution time, model tokens and monetary cost, approval/publishing safety violations, provenance completeness, reviewer workload, recovery from failed provider calls. Report distributions and uncertainty (bootstrap confidence intervals); analyze paired differences. Include ablations: no typed edges, no temporal versioning, no approval-aware planning. Never invent scores or charts.

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
Target: Python 3.12+, Node 22+, Docker Compose. Provide `make setup`, `make dev`, `make test`, `make lint`, `make benchmark-pilot`, `make seed-demo` (or cross-platform equivalents). `.env.example` contains placeholders only. Default to mock LLM mode with deterministic fixtures so no API key or billing is required to demonstrate the project. Document Windows PowerShell commands as well as Bash. Supply database migrations, sample data, OpenAPI docs and health endpoints.

## 12. API boundary

Phases 2D–2E provide an authenticated FastAPI v1 prototype and live PostgreSQL/Neo4j validation for tenant-scoped project,
graph, planning, approval, artifact, execution, and eligibility operations. The API
uses expiring opaque bearer credentials whose digests and tenant role assignments are
stored in PostgreSQL. It does not accept client-supplied actor or reviewer identity as
authority. See [ADR-009](docs/adr/009-authenticated-api-boundary.md),
[`services/api/README.md`](services/api/README.md), and the generated
[OpenAPI contract](docs/api/openapi.json). Tenant roles are currently shared across
projects in that tenant. There is no interactive login, SSO, or public token issuance.

## 13. Definition of done
A fresh clone boots from documented commands; seeded demo runs without paid API; a rule change triggers explainable targeted recomputation; stale approval cannot publish; all invariants have passing automated tests; benchmark outputs raw observations plus reproducible scripts; research report distinguishes hypotheses from results; UI is accessible, responsive and shows errors honestly.

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
