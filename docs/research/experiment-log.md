# Execution log

## 2026-10-14 — foundation and pure-kernel milestone

Observation category: MEASURED local engineering checks, **not research benchmark
results**. All demonstration content and estimates are SIMULATED synthetic fixtures.

Environment: Windows PowerShell, Python 3.14.6, Node 24.18.1, pytest 9.1.1.
Exact Python versions: `requirements-dev.lock`; JS versions: `package-lock.json`.
Git SHA unavailable: the input folder is not a Git repository. No remote was
configured, no hosted CI was run, no paid APIs were called. Raw local console
observations are summarized below; no latency/cost effectiveness measurements.

Source PDF was read across all 13 pages and visually inspected. Reference copy
SHA-256 matches original: `2b64557eb4073706c2d2263c6db35a78f06afedd8b5b8929011b17254f7d51d5`.
Source differences (invariants, B2, objective and ablations) are in spec-mapping.
Initial prior-art browser review is in related-work; failed publisher accesses
are explicitly recorded rather than treated as verified citations.

Tests were authored before the implementation. First collection failed while
fixtures were absent. After implementation, explicit safety regression tests
failed for review/recompute merge, stale SOFT inputs and unconfirmed change
targets; fixes made these fail-closed. These are engineering observations, not
performance comparisons or proof of universal safety.

| Executed command | Observed result |
| --- | --- |
| `python -m venv .venv`; `.venv/Scripts/python -m pip install -e '.[dev]'` | Environment created, developer dependencies installed |
| `npm install --save-dev typescript @types/node eslint typescript-eslint prettier` | Packages installed and lockfile generated |
| `npm ci`; `.venv/Scripts/python -m pip install -r requirements-dev.lock`; `.venv/Scripts/python -m pip install --no-deps -e .` | Documented lockfile setup commands verified locally |
| `.venv/Scripts/python scripts/tasks.py check-python` | Ruff lint/format passed, strict mypy passed (11 Python files), 25 pytest tests passed |
| `.venv/Scripts/python scripts/tasks.py schemas --check` | All 12 entity schemas + Plan and shared Python→TS plan fixture match source |
| `.venv/Scripts/python scripts/tasks.py verify-test-gate` | Deliberate broken test rejected with exit 1; temporary test removed |
| `npm run format:check` | Prettier check passed |
| `npm run lint` | ESLint passed |
| `npm run typecheck` | Strict TypeScript check passed |
| `npm test` | 3 Node/TypeScript contract tests passed |
| `.venv/Scripts/python scripts/tasks.py demo` | Both JSON plan previews ran without keys/databases; publication explicitly NOT_IMPLEMENTED |

25 Python tests include property-based DAG reachability against an independent
fixed-point oracle, stable topological order, scope violations, cycles, immutable
JSON round trips, fingerprints, stale snapshots, missing provenance, unconfirmed
requirements, temporal edge expiry and review holds. They do not cover the yet
unimplemented approval state machine, authenticated access, external-side-effect
idempotency, transactional races, provider failures or publication predicate.

Synthetic demo: slogan change rebuild candidates are copy/storyboard; visual and
visual_export await review; logo is retained. Unrelated note has no rebuild
candidates. KEEP grants no approval; previews perform no side effects. Serial
latency/cost estimates are fixture constants, not measured trials.

At the close of this first milestone, the next work was the Phase 1 exact-version
approval state machine, publication eligibility and invariant tests. That work is
recorded in the following entry. Gate A remained open at that earlier checkpoint;
API/persistence/React were and remain subsequent phases.

## 2026-10-14 — Phase 1 approval and replay safety kernel

Observation category: MEASURED local engineering checks only. These results are
test outcomes, not research benchmark measurements or a proof of universal safety.
No benchmark cases, latency comparisons, cost measurements, novelty finding, paid
provider call, or external publication were performed.

Implemented the immutable draft/submitted/approved/rejected/revoked approval chain.
Each record binds the exact asset version ID and number, confirmed requirement
fingerprint, human actor claim, policy version, idempotency key, expected revision,
and superseded record. Rejection is terminal for that version; revocation appends a
reasoned record; re-review after revocation requires explicit resubmission. The
publication predicate denies missing/malformed/stale approvals, stale plans,
unconfirmed requirements/evidence, non-KEEP assets, and ancestors under REVIEW,
RECOMPUTE or BLOCK. KEEP alone never yields an approval. Event replay is a pure
in-memory version-pointer reducer: exact duplicates return the original receipt;
conflicts, stale snapshots, version gaps/rollback and out-of-order timestamps fail.

Regression and Hypothesis tests cover human reviewer scope/role, tenant isolation,
requirement and policy changes, exact-version non-transfer, rejection and
revocation, confirmed evidence requirements, KEEP-without-approval, REVIEW and
RECOMPUTE dependencies, duplicate/conflicting/stale/out-of-order event handling,
and HARD reachability. Authentication, atomic persistence and cross-request races
remain unimplemented and must be enforced in the future API/database boundary.

| Executed command | Observed result |
| --- | --- |
| `.venv/Scripts/python -m pytest packages/gamo_ca/tests/test_approval.py packages/gamo_ca/tests/test_events.py packages/gamo_ca/tests/test_properties.py -q` | 23 passed |
| `.venv/Scripts/python scripts/tasks.py check-python` | Ruff lint and format passed; strict mypy passed (15 source files); 46 pytest tests passed |
| `.venv/Scripts/python scripts/tasks.py schemas` then `.venv/Scripts/python scripts/tasks.py schemas --check` | Generated the new `SUBMITTED` contract; schema and shared fixture consistency passed |
| `.venv/Scripts/python scripts/tasks.py verify-test-gate` | Deliberately broken test rejected with exit 1; command passed |
| `npm run format:check` | Prettier check passed after formatting regenerated plan fixture |
| `npm run lint` | ESLint passed |
| `npm run typecheck` | Strict TypeScript check passed |
| `npm test` | 3 Node/TypeScript contract tests passed |
| `.venv/Scripts/python scripts/tasks.py demo` | Offline synthetic plan demo exited 0; response labeled SIMULATED and publication NOT_IMPLEMENTED |

Gate A is reached for this current automated pure-kernel suite. This label means
the checked-in gate passes; finite tests do not establish universal safety. Phase 1
is complete. Phase 2 persistence/API/authentication remains the next blocker for
durable approvals and atomic event idempotency. Full raw output is not archived;
the exact commands and summaries above are the recorded local observations.

## 2026-10-14 — Phase 2A transactional event-store slice

Observation category: MEASURED local engineering verification. This checks code,
SQLite behavior and migration compilation only; it does not verify PostgreSQL
throughput or row-lock behavior. No research benchmark or performance measurement
was run. The local environment has Python 3.14.6, SQLAlchemy 2.1.4, Alembic 1.20.0,
psycopg 3.3.6, and no Docker, PostgreSQL, or Neo4j executable/runtime available.

Added PostgreSQL 16 / Neo4j 5 Compose definitions with health checks, Alembic
configuration and the first schema migration. The SQLAlchemy event-store slice
locks the authoritative project row, validates scope/revision and the pure
`EventReplayState`, then commits the immutable event payload/receipt, replay state,
project revision, and Neo4j outbox record together. Scoped unique constraints
protect event IDs, idempotency keys, revisions, and outbox delivery. Exact retries
return the persisted receipt; conflicting keys/IDs, stale revision/snapshot and
cross-scope requests fail closed. ORM guards and a PostgreSQL trigger protect event
rows from mutation. Deterministic outbox failure injection confirms transaction
rollback.

| Executed command | Observed result |
| --- | --- |
| `.venv/Scripts/python -m pip install -e .`; `.venv/Scripts/python -m pip install -r requirements-dev.lock` | Installed the locked SQLAlchemy 2.1.4, Alembic 1.20.0, psycopg 3.3.6 and psycopg-binary 3.3.6 dependencies; API package files are included in editable distribution |
| `.venv/Scripts/python -m pytest services/api/tests -q` | 8 passed; PostgreSQL concurrency test skipped because `ORCIFY_TEST_DATABASE_URL` is unset |
| Alembic `upgrade head` twice against temporary SQLite URL via migration test | Migration is repeatable; project/event/outbox tables and scoped uniqueness constraints present |
| `.venv/Scripts/python -m alembic -c services/api/alembic.ini upgrade head --sql` | PostgreSQL 16 dialect migration SQL compiled successfully offline; no live server was contacted |
| `.venv/Scripts/python scripts/tasks.py check-python` | Ruff passed; strict mypy passed across 18 source files; full suite 54 passed, 1 PostgreSQL-only test skipped |
| `.venv/Scripts/python scripts/tasks.py schemas --check`; `.venv/Scripts/python scripts/tasks.py verify-test-gate` | Schema check passed; deliberate broken test rejected as expected |
| `npm run format:check`; `npm run lint`; `npm run typecheck`; `npm test` | All passed; 3 Node/TypeScript contract tests passed |
| `.venv/Scripts/python scripts/tasks.py demo` | Offline deterministic demo exited 0; still labels outcome SIMULATED and publication NOT_IMPLEMENTED |

The PostgreSQL race test is committed and will exercise project-row serialization
when a disposable service is available. No PostgreSQL/Neo4j startup or live database
test is claimed in this environment. Full immutable graph-content snapshots,
approvals/artifacts, FastAPI routes, verified auth, projection delivery/recovery and
authoritative publication checks remain unfinished. Phase 2 task 1 remains
unchecked until Compose startup/health can be exercised; the first event-store
slice is partial progress toward task 2.

## 2026-10-14 — Phase 2A snapshot and approval persistence continuation

Observation category: MEASURED local engineering checks. Live database behaviors
below are distinguished from offline checks; no performance or research benchmark
claim is made. The user reported Docker Desktop is available, but this PowerShell
execution environment cannot resolve `docker`, and the standard executable paths
checked were absent. PostgreSQL and Neo4j service ports nevertheless responded.
PostgreSQL reported 16.15 and Alembic migration was applied live. Neo4j accepted
configured local credentials and returned `1` to an authenticated Cypher query.
The Docker Compose health metadata itself could not be inspected from this shell.

Added Alembic migration `0002_snapshots_approvals`: PostgreSQL JSONB tables for
immutable project snapshots and approvals, with tenant/project foreign keys,
uniqueness constraints, and append-only triggers. Project creation persists a
typed initial graph snapshot plus reducer state; each committed event appends its
new replay-state snapshot in the same transaction as the event, revision and
Neo4j outbox entry. Approval persistence takes the project row lock, verifies the
graph matches the stored current hash, invokes the pure `apply_approval` domain
transition, then appends the exact actor/version/requirement/policy decision. Exact
retries return the original result and payload conflicts fail. This repository
method requires a server-created reviewer identity and is not an authentication
boundary or API route. Event-only changes do not contain replacement graph content,
so they cannot advance a full graph snapshot; graph ingestion remains necessary.

| Executed command | Observed result |
| --- | --- |
| `.venv/Scripts/python -m pytest services/api/tests -q` (without test DB URL) | 11 passed, 1 PostgreSQL-only test skipped; SQLite/offline evidence only |
| `.venv/Scripts/python -m alembic -c services/api/alembic.ini upgrade head` with configured local PostgreSQL URL | Applied migrations `0001_event_authority` and `0002_snapshots_approvals` to live PostgreSQL 16.15; `current` reported `0002_snapshots_approvals (head)` |
| `.venv/Scripts/python -m pytest services/api/tests/test_postgres_concurrency.py -q` with `ORCIFY_TEST_DATABASE_URL` | 2 passed against live PostgreSQL; concurrent revision race and transaction/idempotency/trigger/rollback checks |
| `.venv/Scripts/python scripts/tasks.py check-python` with `ORCIFY_TEST_DATABASE_URL` | Ruff lint/format passed; strict mypy passed (18 source files); full suite 59 passed, including both live PostgreSQL integration tests |
| `.venv/Scripts/python scripts/tasks.py schemas --check` | Passed |
| `.venv/Scripts/python scripts/tasks.py verify-test-gate` | Passed; deliberately broken test rejected with exit 1 |
| `.venv/Scripts/python -m alembic -c services/api/alembic.ini upgrade head --sql` | PostgreSQL dialect SQL compiled successfully, including snapshot and approval append-only triggers; offline compilation only |
| `npm run format:check`; `npm run lint`; `npm run typecheck`; `npm test` | All passed; 3 TypeScript contract tests passed |
| `.venv/Scripts/python scripts/tasks.py demo` | Exited 0 with SIMULATED output and publication NOT_IMPLEMENTED |
| Authenticated Neo4j HTTP transactional Cypher probe to `http://localhost:7474/db/neo4j/tx/commit` | Live query `RETURN 1 AS ok` succeeded and returned `1` |
| `docker compose --env-file .env.example -f infra/compose.yaml version`; `docker info` | Could not run: PowerShell reports `docker` is not recognized; container health metadata remains unverified |

## 2026-10-14 — Phase 2A authoritative graph ingestion

Observation category: MEASURED local engineering checks. This is not a scientific
benchmark and says nothing about universal safety. Added schema-version-1 graph change
events containing the full typed node and edge content, the expected graph hash and
revision, scoped human actor, and event timestamp. The pure validator checks graph
scope and DAG validity, temporal progression, exact node version increments, edge
immutability with explicit temporal closure, known input provenance, and confirmation
requirements. The event store now keeps the reducer hash and graph hash separately,
locks the project row, validates the current complete snapshot, and atomically appends
the event, replay receipt, graph snapshot, replay snapshot, revision, authority pointers
and Neo4j outbox entry. Replay reconstructs from revision zero and verifies the result
against PostgreSQL's current graph hash. Failures roll back all writes.

| Executed command | Observed result |
| --- | --- |
| `.venv/Scripts/python -m pytest packages/gamo_ca/tests/test_graph_changes.py services/api/tests/test_event_store.py -q` | 17 passed (offline domain and SQLite coverage for typed graph advance, validation, duplicate replay, replay/hash consistency and rollback) |
| `.venv/Scripts/alembic -c services/api/alembic.ini upgrade head` against local PostgreSQL | Applied `0003_authoritative_graph_hash`; `alembic current` reported `0003_authoritative_graph_hash (head)` |
| `.venv/Scripts/python -m pytest services/api/tests/test_postgres_concurrency.py -q` with `ORCIFY_TEST_DATABASE_URL` set to local PostgreSQL | 3 passed live: concurrent project update, concurrent graph update with one winner and immutable snapshot replay/hash, plus append-only/idempotency/rollback suite |
| `.venv/Scripts/python scripts/tasks.py check-python` with live PostgreSQL URL | Ruff format/lint and strict mypy passed; 68 tests passed, including the 3 live PostgreSQL tests |
| `.venv/Scripts/python scripts/tasks.py schemas --check`; `.venv/Scripts/python scripts/tasks.py verify-test-gate` | Both passed; deliberate broken test rejected with exit 1 |
| `npm run format:check`; `npm run lint`; `npm run typecheck`; `npm test` | Formatting, lint, typecheck and 3 TypeScript contract tests passed |
| `.venv/Scripts/python scripts/tasks.py demo` | Exited 0; deterministic output remains explicitly SIMULATED and publication NOT_IMPLEMENTED |
| `.venv/Scripts/python -m alembic -c services/api/alembic.ini upgrade head --sql` | PostgreSQL migration SQL compiled offline successfully |

Offline SQLite tests verify migration repeatability, current graph hash schema,
idempotent writes, immutable snapshots, deterministic replay, and injected rollback.
Live PostgreSQL verifies the third migration, row-lock races, graph advancement and
reconstruction, stored snapshot hash consistency, append-only triggers, exact retries,
stale revision rejection and outbox rollback. No benchmark result is claimed. The
current shell cannot query Docker Compose health metadata; a previously tested live
authenticated Neo4j `RETURN 1` query establishes connectivity only, not projection
behavior. No Neo4j projection worker exists yet. The next Phase 2 task is to implement
that retryable and idempotent outbox worker and reconciliation against the PostgreSQL
event log.

## 2026-10-14 — Phase 2B retryable Neo4j projection worker

Observation category: MEASURED local engineering checks. This is not a scientific benchmark and makes no universal safety or performance claim. PostgreSQL remains authoritative. Migration `0004_projection_delivery` adds bounded retry state, delivery leases, dead-letter state and per-project projection checkpoints. The worker consumes committed outbox rows in project revision order, scopes Neo4j writes by tenant and project, and uses revision/hash checks for duplicate and stale delivery handling. Reconciliation rebuilds from complete PostgreSQL snapshots and detects revision, hash, node and edge drift. A crash after Neo4j commit but before the PostgreSQL checkpoint is recovered idempotently. Exhausted deliveries block later events until authoritative reconciliation. No external publication path was added.

| Executed command | Observed result |
| --- | --- |
| `.venv/Scripts/alembic -c services/api/alembic.ini upgrade head` with local PostgreSQL URL; then `current` | Applied `0004_projection_delivery`; PostgreSQL reports `0004_projection_delivery (head)` |
| `.venv/Scripts/python scripts/tasks.py check-python` with PostgreSQL and Neo4j test environment variables | Ruff lint/format passed; strict mypy passed for 22 source files; all 75 tests passed, including live PostgreSQL concurrency and live projection integration tests |
| `.venv/Scripts/python -m pytest services/api/tests/test_projection_integration.py -q` with both live services | 1 passed against local PostgreSQL and Neo4j in 2.62s |
| `.venv/Scripts/python scripts/tasks.py schemas --check` | Passed; no schema drift |
| `.venv/Scripts/python -m pip check` | Passed; no broken requirements |
| `.venv/Scripts/python -m ruff format --check .`; `git diff --check` | Passed; 57 files formatted and no whitespace errors |

Deterministic tests cover exponential backoff, bounded retries, dead-letter ordering, pointer-only events, payload scope mismatch, reconciliation and crash recovery. Live integration covers projection, duplicate delivery, stale event rejection, tenant isolation and rebuilding after a deleted node. Compose health metadata remains unverified because Docker CLI is unavailable. The worker holds a PostgreSQL project row lock across a bounded Neo4j transaction, which can increase write latency during Neo4j stalls. Multi-worker throughput, alerting and long-duration recovery remain unmeasured. No research benchmark was run.

## 2026-10-14 — Phase 2C artifact and execution provenance persistence

Observation category: MEASURED local engineering checks, not a scientific benchmark.
PostgreSQL is authoritative for artifact content, graph/approval state, and execution
history. Alembic migrations `0005_artifacts_execution` and
`0006_execution_header_guards` add immutable artifact versions, append-only artifact
provenance and execution lifecycle events, current run/attempt indexes, scoped
constraints, and run/attempt header guards. Artifact records bind tenant/project,
source graph revision/hash, exact asset node/version, captured input node versions and
hashes, content SHA-256, planner decision, and optional provider/model labels. Artifact
content must match the referenced graph asset content. Eligibility reads the current
PostgreSQL graph and approval records and invokes the pure publication predicate.

Execution runs pin a complete planner decision and source graph snapshot. Attempts
record dependency versions and optional provider/model/prompt identifiers. Lifecycle
changes are append-only events and include pending, running, succeeded, failed,
cancelled and retryable-failure states. Project/run locks, request hashes and scoped
uniqueness provide transactional idempotency and reject conflicting/out-of-order
updates. Retryable failure permits a higher attempt number; terminal states do not
restart. Elapsed time, token count and cost remain null with `missing` status unless a
caller provides a value labeled `estimated` or `measured`. No AI provider was invoked,
and no latency, token count, cost saving, or research benchmark is claimed.

| Executed command | Observed result |
| --- | --- |
| `.venv/Scripts/alembic -c services/api/alembic.ini upgrade head`; then `current` with live PostgreSQL 16.15 | Applied `0005_artifacts_execution` and `0006_execution_header_guards`; current head is `0006_execution_header_guards` |
| `.venv/Scripts/python scripts/tasks.py check-python` with live PostgreSQL and Neo4j test environment | Ruff lint/format passed; strict mypy passed for 24 source files; all 82 tests passed |
| Full test suite live-service subset | Four PostgreSQL integration tests passed (artifact/execution transaction test plus three persistence concurrency tests); one PostgreSQL + Neo4j projection integration test passed |
| `.venv/Scripts/python scripts/tasks.py schemas`; then `schemas --check` | Passed; artifact, execution and provenance JSON schemas generated and checked |
| `.venv/Scripts/python scripts/tasks.py verify-test-gate` | Passed; deliberate broken test was rejected with exit 1 |
| `.venv/Scripts/alembic -c services/api/alembic.ini upgrade head --sql` | Full PostgreSQL migration chain through `0006_execution_header_guards` compiled offline |
| `.venv/Scripts/python -m pip check`; `git diff --check` | Passed; no broken requirements or whitespace errors |
| `npm run format:check`; `npm run lint`; `npm run typecheck`; `npm test` | All passed; 3 TypeScript contract tests passed |
| `.venv/Scripts/python scripts/tasks.py demo` | Exited 0; output remains SIMULATED and publication NOT_IMPLEMENTED |

Offline tests cover immutable artifact versions, content/dependency binding, stale graph
and dependency rejection, approval-dependent eligibility, idempotency conflicts,
execution retries/cancellation, missing-vs-estimated-vs-measured values, append-only
history, and injected rollback. Live PostgreSQL covers concurrent duplicate artifact
requests, tenant and stale revision rejection, append-only/header triggers, lifecycle
writes and artifact provenance rollback. The current-state status columns on runs and
attempts are mutable indexes guarded so header metadata cannot change; append-only
execution events provide the durable history. Object/blob storage, retention and
artifact diffing remain open. Docker Compose health metadata remains unverified because
the Docker CLI is unavailable. No external publisher or provider integration exists.

## 2026-10-14 — Phase 2D authenticated FastAPI boundary

Observation category: MEASURED local engineering and security checks, not a scientific
benchmark. ADR-009 selects expiring opaque bearer tokens for the MVP. Token digests and
tenant memberships live in PostgreSQL; the token is printed only once by the operator
provisioning command. The server derives actor identity and tenant role from those
records. Request schemas reject actor/reviewer claims. Cross-tenant and revoked
membership resources return 404, role denials return 403, and absent/invalid/expired
credentials return 401. Roles are tenant-wide in this prototype.

Migration `0007_authenticated_api` adds `api_credentials` and `tenant_memberships`.
FastAPI exposes project create/list/get, PostgreSQL graph snapshot read/change, plan
preview, approval submit/approve/reject/revoke transitions, artifact create/read and
eligibility, execution run/attempt transitions and history. Approval, artifact, and
run creation recompute the submitted planning event against the current PostgreSQL
graph. Eligibility continues through the existing current-state PostgreSQL project
lock and pure predicate. PostgreSQL remains authoritative; no publication side effect,
real AI provider, or frontend was added. OpenAPI is generated into `docs/api/openapi.json`.

| Executed command | Observed result |
| --- | --- |
| `.venv/Scripts/python -m alembic -c services/api/alembic.ini upgrade head` with local PostgreSQL | Applied `0007_authenticated_api` after `0006_execution_header_guards` |
| `.venv/Scripts/python -m alembic -c services/api/alembic.ini current` | `0007_authenticated_api (head)` |
| `.venv/Scripts/python -m alembic -c services/api/alembic.ini upgrade head --sql` | Full PostgreSQL migration chain through `0007_authenticated_api` compiled offline |
| `.venv/Scripts/python scripts/tasks.py check-python` with `ORCIFY_TEST_DATABASE_URL` set to local PostgreSQL | Ruff checks/format passed; strict mypy passed for 29 source files; 92 passed, 1 skipped out of 93 tests |
| PostgreSQL integration tests within the full suite | 5 passed: artifact/execution persistence, API credential/membership revocation, and 3 PostgreSQL concurrency tests |
| SQLite FastAPI security/route tests | 10 passed: project creation, auth expiry/invalidity, tenant and role denial, forged identity rejection, graph duplicate replay, approval transitions, artifact creation/retrieval, and execution history |
| `services/api/tests/test_projection_integration.py` in the full suite | 1 skipped because `ORCIFY_TEST_NEO4J_*` variables were not configured; no live Neo4j claim for this phase |
| `.venv/Scripts/python scripts/export_openapi.py`; `.venv/Scripts/python scripts/tasks.py schemas --check` | OpenAPI regenerated; domain schemas remained consistent |
| `.venv/Scripts/python scripts/tasks.py verify-test-gate`; `.venv/Scripts/python -m pip check`; `git diff --check` | All passed; deliberately broken test was rejected; no dependency conflicts or whitespace errors |
| `npm run format:check`; `npm run lint`; `npm run typecheck`; `npm test` | All passed; 3 TypeScript contract tests passed |

One Starlette deprecation warning is emitted by its test client recommending `httpx2`;
it does not fail tests. Live PostgreSQL exercised authentication and the existing
transactional persistence suites; the complete API route suite used isolated SQLite.
The prototype still lacks interactive login/SSO/MFA, per-project membership roles,
membership administration endpoints, rate limiting, production key rotation, and
security alerting. TLS and secure one-time token delivery are deployment requirements.
Neo4j projection and Docker Compose health were not revalidated in this phase. The
finite tests establish these observed checks only; they do not establish universal
security or scientific results.

## 2026-10-14 — Phase 2E live API validation and seeded demo

Observation category: local engineering integration checks, not a scientific benchmark.
Phase 2E adds a deterministic seed for the synthetic `demo-tenant`, fixed role identities,
`demo-project` graph and unapproved `demo-copy-v1` artifact. Credentials are random,
short-lived bearer secrets whose SHA-256 digests are stored in PostgreSQL. Raw values are
written to the ignored local `var/demo-tokens.json` file and never printed. Reseeding was
run twice; the second run rotated only this demo's seed credentials and replayed the same
immutable artifact successfully. Smoke runs use a separate project ID and retain their
append-only records for review.

A live authenticated FastAPI integration test now spans PostgreSQL 16.15 and Neo4j.
It creates a project through the tenant-admin API, verifies project and graph reads,
checks concealed cross-tenant access, revoked membership and revoked credential denial,
requests a GAMO-CA plan, persists a synthetic artifact, and requires a distinct reviewer
credential to approve the exact asset version and requirement fingerprint. Eligibility
was false before approval, true after exact-version approval, then false after a confirmed
upstream requirement change. The old immutable approval row remained recorded against
its original requirement fingerprint. The new plan marked dependent copy/storyboard
nodes for recomputation. Two simultaneous HTTP requests with an identical graph-change
idempotency key yielded one write and one replay. Neo4j was made inconsistent and rebuilt
from the PostgreSQL snapshot; PostgreSQL revision and graph/snapshot hashes were unchanged.
The API exposes no publishing route.

The real HTTP smoke script was run three times against Uvicorn and live PostgreSQL/Neo4j. The
second run had the projection worker running separately. Both reported `PASS`, labeled
data `SYNTHETIC` and execution `DETERMINISTIC_MOCK`, confirmed stale eligibility was
blocked, and reported `external_publication_invoked: false`. No paid provider, fabricated
usage/cost value, or scientific metric was involved.

| Executed command/check | Observed result |
| --- | --- |
| PostgreSQL direct connectivity query and port check | PostgreSQL 16.15 responded; local PostgreSQL and Neo4j ports were reachable |
| `.venv/Scripts/python -m alembic -c services/api/alembic.ini upgrade head`; `current` | Upgrade was a no-op at `0007_authenticated_api (head)` |
| `.venv/Scripts/python -m alembic -c services/api/alembic.ini upgrade head --sql` | Full PostgreSQL migration chain through `0007_authenticated_api` compiled offline; Phase 2E adds no migration |
| `.venv/Scripts/python -m pytest -q services/api/tests/test_phase2e_live_e2e.py services/api/tests/test_projection_integration.py` with PostgreSQL and Neo4j variables set | 2 passed, 0 skipped; one Starlette/httpx deprecation warning |
| `.venv/Scripts/python scripts/tasks.py check-python` with all PostgreSQL and Neo4j test variables set | Ruff passed; 77 Python files formatted; strict mypy passed for 31 source files; 94 passed, 0 skipped |
| `.venv/Scripts/python scripts/tasks.py check-python` without live service variables | 87 passed, 7 skipped (the 5 PostgreSQL-only test cases and 2 PostgreSQL/Neo4j integration cases); one test-client deprecation warning |
| `scripts/seed_demo.py`, first and repeated invocation | Both exited 0; stable synthetic project/artifact, active demo credentials rotated and revoked fixture remains invalid |
| `scripts/run_api_smoke.py --run-id phase2e-local-001/002/003` | All three real HTTP scenarios passed; runs 002 and 003 executed while Uvicorn and the projection worker were running |
| `scripts/export_openapi.py`; `scripts/tasks.py schemas --check` | OpenAPI contract generated; domain schema and cross-language plan fixture check passed |
| `npm run format:check`; `npm run lint`; `npm run typecheck`; `npm test` | All passed; 3 TypeScript contract tests passed |
| `scripts/tasks.py verify-test-gate`; `python -m pip check`; `git diff --check` | Deliberate broken test was rejected; dependencies and final diff checks passed |

The Docker CLI was not discoverable, so Compose container health metadata was not
inspected in this shell. Direct service probes and live integration tests passed. The
smoke workflow retains test projects and append-only records, so use a disposable local
database or unique run IDs. The seed baseline refuses to overwrite an advanced project.
These finite engineering checks do not prove universal safety, production readiness,
scientific novelty, or performance improvement.

## 2026-10-14 — Phase 3A authenticated read-only Graph & Impact Explorer

Observation category: local engineering and UI checks, not a scientific benchmark or
usability study. The existing API contract was inspected before frontend work. The
contract already had authenticated project listing, PostgreSQL graph snapshot reads,
planner preview, artifact detail, and authoritative artifact eligibility. Three
minimal read capabilities were missing for a usable authorized explorer: list active
tenant memberships of the credential's server-verified actor, list immutable
project-scoped artifacts, and list project-scoped append-only approval history. These
routes use the existing membership check and database scope; no migration was needed.
FastAPI OpenAPI was regenerated and used to generate the frontend's TypeScript
contracts.

The React application holds its development bearer token only in component memory and
uses it only in the `Authorization` header. It does not write browser storage, URLs,
or application logs. Tenant/project selection is populated from authorized API reads.
React Flow displays deterministic positions for the authoritative graph snapshot,
active typed dependencies, versions, evidence/provenance, and confirmed requirement
state. The change form permits only a non-mutating planner preview and only offers
confirmed requirements and confirmed evidence. Decision labels and explanations are
rendered from API output. The interface explicitly says KEEP is a reuse decision and
does not grant approval. Artifact approval history is matched to exact node/version
and displays its requirement fingerprint/policy binding; eligibility is read from
PostgreSQL-backed API responses. Failed eligibility or approval reads display as
unavailable. There are no graph-write, artifact-write, approval-transition,
execution, or publication controls.

| Executed command/check | Observed result |
| --- | --- |
| `.venv/Scripts/python scripts/export_openapi.py`; `npm run web:types` | OpenAPI contract regenerated; TypeScript client types generated from `docs/api/openapi.json` |
| `.venv/Scripts/python scripts/tasks.py check-python` | Ruff passed; 78 Python files formatted; strict mypy passed for 31 source files; 89 passed, 7 skipped from 96 tests; one Starlette TestClient deprecation warning |
| `services/api/tests/test_authenticated_api.py` within the full suite | 12 passed, including active tenant membership selection, allow-listed CORS, artifact listing, and approval history reads; these route tests use the isolated SQLite fixture |
| `npm ci --no-audit --no-fund` | Passed; 323 packages installed. npm reported the esbuild post-install script was blocked by its install-script allow-list; the subsequent tests and production build still passed |
| `npm run format:check`; `npm run lint`; `npm run typecheck`; `npm test` | All passed. The root contract runner passed 3 tests; Vitest passed 7 tests across 2 files for graph layout/rendering, active edges, API auth/errors, decision explanations, and exact-version artifact binding/eligibility |
| `npm run web:build` | Production Vite build passed; JavaScript output split into application, graph-vendor, and react-vendor chunks; no chunk-size warning |
| `.venv/Scripts/python scripts/tasks.py schemas --check`; `scripts/tasks.py verify-test-gate`; `python -m pip check`; `git diff --check` | Passed; the deliberate broken-test probe was rejected as expected; no dependency conflicts or whitespace errors |
| `.venv/Scripts/python scripts/tasks.py demo` | Exited 0; output labeled `SIMULATED`, publication `NOT_IMPLEMENTED`; offline demonstration output only |

The 7 PostgreSQL/Neo4j tests were skipped because this session did not configure
`ORCIFY_TEST_DATABASE_URL` or `ORCIFY_TEST_NEO4J_*`; no live database run is claimed
for the new read routes. The frontend calls through Vite's same-origin API proxy in
development. Cross-origin hosting requires an explicit `ORCIFY_WEB_ORIGINS` allow-list.
The UI has no historical graph picker, artifact diff, pagination, interactive login,
SSO/MFA, or usability evaluation. These engineering checks do not establish universal
safety, production readiness, scientific novelty, or performance improvement.

## 2026-10-14 — Student research scope reset

This is a project-scope decision, not an experiment or research result. The intended
project is a high-school scientific research prototype for Kazakhstan's Republican
Scientific Projects Competition. Existing API, PostgreSQL, Neo4j, and React components
are retained as demonstration infrastructure and are frozen against feature expansion.
The next work is to create a bounded, reproducible synthetic pilot and compare the pure
GAMO-CA planner with simple full-replay and ordinary-DAG-cache baselines using identical
inputs. Student annotation capacity should set the pilot size; the earlier proposed
144-case count remains a planning target only.

No scientific measurements, independent annotation, benchmark run, or result was
produced by this scope change. Existing tests and live service checks remain engineering
evidence only. Future dependencies or infrastructure require a documented direct need
for the research question and an explanation of the simpler option considered. This
decision is recorded in [ADR-012](../adr/012-student-research-scope.md).

## 2026-10-14 — Phase R1.1 minimal scientific pilot

Observation category: five hand-authored synthetic cases; small exploratory pilot. The
independent (of the algorithms) correctness oracle was written as scenario obligations
before the algorithm runs: specified HARD descendants must recompute, specified
uncertain SOFT descendants must not be silently kept, and exact asset-version plus
requirement-snapshot approvals must not be treated as current after invalidation. It
has not been independently reviewed by a second human. All methods received the same
immutable graph and change event per scenario. Full Recompute and Conventional DAG
Incremental were implemented independently in `scripts/r1_1_pilot.py`; GAMO-CA reused
the existing pure `plan_change` function. The DAG baseline invalidates HARD and SOFT
descendants and ignores INFORMATIONAL links.

| Scenario | Full recomputes | DAG recomputes | GAMO-CA recomputes | Review operations Full / DAG / GAMO-CA |
| --- | ---: | ---: | ---: | ---: |
| slogan change | 6 | 6 | 3 | 6 / 6 / 6 |
| brand guideline change | 5 | 4 | 2 | 5 / 5 / 5 |
| asset version update | 5 | 4 | 2 | 6 / 5 / 5 |
| approval invalidation | 4 | 3 | 1 | 4 / 4 / 4 |
| all-HARD fanout (no advantage) | 4 | 4 | 4 | 4 / 4 / 4 |
| **Total over these five authored cases** | **24** | **21** | **12** | **25 / 24 / 24** |

All 15 scenario-method plans passed the predeclared oracle; zero stale approvals were
accepted. Requirement changes invalidate all modeled approvals because the current
domain binds them to the full requirement fingerprint. The unrelated moodboard in the
approval-invalidation scenario was kept computationally but still required review;
this directly tests that KEEP does not grant approval. In the all-HARD scenario all
methods recomputed the same four outputs.

Planning time was measured with `time.perf_counter_ns`, 101 calls per method/scenario,
and reported as each scenario's median. The medians across the five scenario medians
were 0.0027 ms for Full Recompute, 0.0078 ms for DAG Incremental, and 3.1627 ms for
GAMO-CA, on Python 3.14.6 in the local Windows environment. This times plan creation
only: no content generation, database/API overhead, or human review time. GAMO-CA's
time includes graph validation, hashing, decisions, and explanations, which the simple
baselines do less work to produce. These tiny timing values are descriptive only and
do not support statistical or general performance claims.

| Executed command/check | Observed result |
| --- | --- |
| `.venv/Scripts/python scripts/r1_1_pilot.py --seed 20261014 --timing-repeats 101` | 15 scenario-method results; 15/15 correctness PASS; outputs written to `docs/research/r1_1-pilot/` |
| `.venv/Scripts/python -m pytest -q tests/test_r1_1_pilot.py` | 7 passed after adding fixed-seed, stale-approval, HARD/SOFT, and no-advantage regressions |

Raw results are in `r1_1-pilot/results.csv` and `node_decisions.csv`; exact input
hashes, oracle obligations, seed, and environment are in `manifest.json`. Three SVG
plots separately display recomputation operations, review operations, and planning
time. Operation counts are distinct workload proxies; monetary and human-time costs
were not measured. The pilot uses synthetic, author-labeled cases and one seed; no
second annotator, significance testing, or larger benchmark was run. The next gate is
human review of the cases, oracle, and baseline assumptions before expanding the
dataset. See [`r1_1-pilot/README.md`](r1_1-pilot/README.md).

## 2026-10-14 — Phase R1.2 audit of the saved R1.1 pilot

Observation category: reproducible accounting audit of existing R1.1 artifacts. No
planner was rerun, no synthetic workload was expanded, and the R1.1 CSVs and plots
were left unchanged. `scripts/audit_r1_1.py` reads the saved results and node decisions,
checks the expected 15 result rows, 114 node rows, method labels and PASS states, and
writes only under `docs/research/r1_2-audit/`. Its manifest records SHA-256 hashes of
the two input CSVs.

The oracle is implementation-independent in a narrow sense: authored scenario
obligations are checked without calling GAMO-CA. It is not independently annotated:
the same team authored the scenarios, edges, labels and checker, and no second human
review has occurred. The checker enforces 12 listed HARD recomputations and safe
actions for uncertain SOFT items, but allows three different safe actions for SOFT
cases. It does not establish complete ground truth, future review resolution or
general correctness. All methods received each scenario's same graph and event, but
the two baselines do not produce a REVIEW action; the common scorer still checks
approval eligibility and counts regenerated items as needing new exact-version review.

| Scenario | DAG immediate recomputes | GAMO-CA immediate recomputes | Audit classification |
| --- | ---: | ---: | --- |
| Slogan change | 6 | 3 | Three required HARD assets recompute; `social_visual` is kept because its SOFT edge names palette while the event changes text; `social_export` and its HARD child `logo` wait for review. |
| Brand guideline change | 4 | 2 | Two color-relevant outputs recompute; unknown `layout_review` and HARD child `final_export` wait. |
| Asset version update | 4 | 2 | Two HARD crops recompute; uncertain `caption` and HARD child `caption_export` wait; unrelated copy is kept. |
| Approval invalidation | 3 | 1 | Required compliance copy recomputes; `legal_montage` and HARD child `legal_export` wait; unrelated moodboard content is kept but its approval is stale under the global requirement fingerprint. |
| All-HARD fanout | 4 | 4 | All methods recompute all four outputs; no advantage. |

Across cases, all 12 nodes listed as mandatory HARD recomputations were in fact
`RECOMPUTE`; none was incorrectly substituted with `REVIEW`. Four other HARD
descendants (`logo`, `final_export`, `caption_export`, `legal_export`) were `REVIEW`
because their upstream SOFT asset was unresolved. This is a fail-closed hold, but it
requires human resolution followed by replanning. Together with the four uncertain
SOFT roots, these represent eight conditional future recomputations. Therefore nine
fewer immediate GAMO-CA recomputations than DAG means eight deferred behind review
and one field-specific KEEP, not nine demonstrated eliminated tasks. If all four
branches later prove material, the conservative GAMO-CA count is 20 versus DAG's 21;
if none proves material, the eight may remain reusable. No human outcomes were
observed.

Review operations total Full 25, DAG 24, GAMO-CA 24; counts are distinct review or
approval-work proxies, not person-minutes. The cost sensitivity keeps three terms
separate: recomputations, review operations and planner milliseconds. Unit weights
and `q` (the assumed fraction of uncertain branches later found material) are
hypothetical. From the saved five per-case timing medians, GAMO-CA sums to 13.4922 ms,
DAG to 0.0352 ms, a 13.4570 ms difference. The measured R1.1 median-of-case-medians
values were Full 0.0027 ms, DAG 0.0078 ms, and GAMO-CA 3.1627 ms. This unfavorable
GAMO-CA result is disclosed. It is not a like-for-like runtime benchmark: the simple
baselines do less validation and explanation work than GAMO-CA, and the tiny
plan-only timings omit generation, human review and I/O.

The break-even sensitivity is `(9 - 8q) / 13.457` assumed planner work units per ms
per recomputation work unit: 0.669 at `q=0`, 0.372 at `q=0.5`, and 0.074 at `q=1`.
Below the threshold GAMO-CA has lower hypothetical total cost; above it, DAG does.
This does not estimate real costs or `q`; the audit CSV includes the assumptions
and separate cost components. See [`r1_2-audit/README.md`](r1_2-audit/README.md),
`scenario-accounting.csv`, `cost-sensitivity.csv`, `break-even.csv`, and
`break-even.svg`.

| Executed command | Observed result |
| --- | --- |
| `.venv/Scripts/python scripts/audit_r1_1.py` | Accepted the 15 saved R1.1 rows; reported GAMO-CA 12, DAG 21, eight review-gated asset versions; wrote five R1.2 audit outputs without writing under R1.1. |
| `.venv/Scripts/python -m pytest -q tests/test_r1_1_pilot.py tests/test_r1_2_audit.py` | 11 passed, including checks for mandatory HARD nodes, conditional-work accounting, sensitivity thresholds and shared scenarios. |

Recommendation: no-go for a larger benchmark until a second human reviews the graph
labels, oracle, global approval-fingerprint assumption and baseline fairness. The
follow-up test for review resolution and replanning also remains open. No statistical
significance, scientific novelty, actual review savings or real-world cost benefit is
claimed.

## 2026-10-15 — Phase R1.3 synthetic workflow and blinded review preparation

Observation category: a small deterministic workflow test with synthetic outcome
inputs, plus preparation of a blank independent-review worksheet. No second reviewer
has completed the worksheet. No human response, probability, or review duration was
generated. The R1.1 and R1.2 directories were not modified by the R1.3 script.

The worksheet has 25 blank asset-label rows for five anonymized scenarios. It shows
original confirmed requirements, the change and fields, asset inputs and typed edges,
and separate blank impact and approval labels. It contains no algorithm names or
decisions. The written protocol says to provide only that worksheet before unblinding
the R1.1/R1.2 results, save the response separately, record disagreements, and not
silently overwrite labels.

Four unresolved SOFT branches each have two modeled outcomes. The script enumerated
all 16 combinations. A material outcome set the edge's relevant fields to the changed
fields; a non-material outcome set them to a non-overlapping field. It created a new
snapshot hash and event binding, then called the pure GAMO-CA planner again. Each
material root and HARD child became RECOMPUTE; each non-material pair became KEEP.
These are explicitly synthetic fixture outcomes, not human judgments.

Across the 16 combinations, GAMO-CA final planned recomputations were 12, 14, 16, 18,
and 20 when respectively 0, 1, 2, 3, or 4 branches were material. Each combination
requires four SOFT resolution reviews and uses four separate replan rounds after five
initial scenario plans (nine plan calls total). Projected exact-version approval or
renewal reviews were 22 or 24, depending on whether the S03 photo-caption branch was
material; the three requirement-change cases invalidate approvals through the current
global requirement fingerprint. Projected total review requirements were 26 or 28.
These are count proxies under synthetic outcomes, not performed human reviews or
measured effort; no approval records were created. Conventional DAG stayed at 21
recomputations and Full Recompute at 24.

R1.3 also implemented an independent field-aware DAG traversal using the same
`relevant_fields` and event `changed_fields`. It followed the same 16 resolved inputs
and matched GAMO-CA's final actions and recomputation counts on all five tiny fixtures.
This shows that a conventional DAG can use the field metadata already present and
that these cases do not demonstrate a unique recomputation advantage for GAMO-CA.
The field-aware implementation assumes valid fixtures and omits GAMO-CA's graph,
provenance, and safety validation; action matching is not safety equivalence.

Plan-only timing used 21 complete workflow repetitions per outcome set. Across the
16 outcome sets, medians of the initial, replanning, and combined durations were
31.9357 ms, 25.8518 ms, and 58.7511 ms for GAMO-CA; 0.2641 ms, 0.1804 ms, and
0.4525 ms for the field-aware DAG; 0.0917 ms initial for eager DAG; and 0.0278 ms
initial for Full Recompute. The combined median is computed per repeated sample, so
it need not equal the sum of the separate medians. These unfavorable timing gaps
disclose unequal code work: GAMO-CA validates/hashes/explains while the short
baselines assume trusted fixtures. In this run, GAMO-CA's total is about 130 times
the field-aware DAG and 641 times the eager DAG. Timing excludes human review and
asset generation; it is not a fair algorithm-complexity comparison.

The cost CSV separates final planned recomputations, SOFT resolution reviews,
approval/renewal reviews, initial planner milliseconds, and replanning milliseconds.
Per-operation weights are hypothetical work units only; no money or human minutes
were measured. All cost rows and all material/non-material outcomes are marked as
assumptions.

| Executed command | Observed result |
| --- | --- |
| `.venv/Scripts/python scripts/r1_3_workflow.py --seed 20261014 --timing-repeats 21` | 25 blank worksheet rows; 64 branch rows covering 16 combinations; 64 method/workflow summaries; 768 hypothetical cost rows. Python 3.14.6 on Windows 11. No human responses. |
| `.venv/Scripts/python -m pytest -q tests/test_r1_3_workflow.py` | 3 passed; all 16 synthetic transitions, approval/review counts, and worksheet blinding were checked. |

The report and raw files are under [`r1_3-workflow/`](r1_3-workflow/). The binary test
does not model a reviewer who remains uncertain after a review; a real workflow must
keep that asset under REVIEW or BLOCK. Independent validation and the larger benchmark
remain blocked on a real second human completing the worksheet and review of the
labels. No significance, novelty, universal safety, or real-world savings claim is
made.

## 2026-10-15 — Phase R1.4 independent-review preparation

Observation category: reviewer instructions, validation/import tooling, and importer
engineering tests. **No completed human worksheets were present or generated.** The
R1.1, R1.2, and R1.3 source artifacts were not edited. The blank R1.3 worksheet
remains the template.

Added a student-friendly guide defining `RECOMPUTE`, `REVIEW`, and `KEEP`, separating
impact from approval, and instructing reviewers to work independently before
unblinding. Added `scripts/import_r1_4_reviews.py` to require two distinct complete
worksheet files, validate expected asset rows, labels, reasons, confidence values,
and duplicate keys, then write source hashes, separate reviewer scores,
agreement-only scores, and unresolved disagreements into a new output directory. It
does not adjudicate, rewrite, or silently choose among labels.

The descriptive measures are exact action agreement, recomputations on reviewer-`KEEP`
rows (unnecessary under this comparison), recomputations on reviewer-`REVIEW` rows
(reported separately because necessity is unresolved), missed required
recomputations, and approval-safety violations. The last measure flags a shared R1.1
correctness-oracle eligibility result marked true while the reviewer says
`REAPPROVE` or `UNCERTAIN`; it is not an observed publication attempt. Field-aware DAG has no approval or
eligibility implementation, so its safety rows are unassessed. Disagreements remain
unresolved; agreement-only metrics exclude contested rows without assigning a label.

R1.3 found Field-aware DAG matched GAMO-CA actions and recomputation counts across 16
synthetic outcome combinations. These five workflows cannot establish algorithmic
novelty or superiority. PostgreSQL approvals, provenance, and recovery are system
engineering capabilities. A fair future comparison would give an ordinary DAG the
same safeguards and test whether GAMO-CA changes outcomes or human effort. No such
measured benefit is available; practical usefulness and usability were not evaluated.

| Executed command | Observed result |
| --- | --- |
| `.venv/Scripts/python -m pytest -q tests/test_r1_4_review_import.py` | 6 passed; temporary synthetic rows exercised validation, comparison, and disagreement export only. |
| `.venv/Scripts/python scripts/tasks.py check-python` | Ruff passed; 93 files formatted; mypy passed for 35 source files; full Python suite: 110 passed, 7 skipped, 1 deprecation warning. The seven skips require live PostgreSQL and/or Neo4j connection variables, which were unset. |
| `.venv/Scripts/python scripts/import_r1_4_reviews.py --help` | CLI inspection only; no import or scoring of human data. |
| `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run web:build` | All passed as unchanged-workspace regression checks. The npm test command passed 3 contract tests and 7 web tests; production build completed. No frontend files were changed for R1.4. |
| `git diff --check` | Passed; Git reported only existing LF/CRLF conversion notices for tracked files. |

Independent validation is incomplete. Do not report reviewer accuracy or begin a
larger benchmark until two real worksheets are received, validated, and inspected.
No statistical significance, novelty, or universal safety claim is made.

## 2026-10-15 — Final research presentation build

Observation category: frontend completion, preservation checks, and engineering QA.
No new research phase, timed trial, benchmark, AI generation, or human annotation was
run. Existing R1.1–R1.4 files were frozen by hashes before implementation; all 22
still match the final preservation check. Backend services, APIs, database schemas,
and the pure GAMO-CA kernel were not changed.

Extended the existing React app with Research overview, Graph & impact, and Experiments
& results. Reused its canvas, inspector, in-memory bearer login, and live API explorer.
The default mode is explicitly SIMULATED / OFFLINE, using the original slogan fixture
and an exported Python plan verified against saved R1.1 node actions. Reset clears
the local preview; no version advance, generation, approval, or publication occurs.
Live mode is explicit, retains API errors, and has no automatic offline fallback.

Results read original CSVs directly for initial counts/review proxies/timing,
hypothetical cost sensitivity, and all 16 synthetic review/replan outcomes. The
showcase states that Field-aware DAG matched GAMO-CA's final actions and counts,
planning overhead is higher/asymmetric, and human validation is incomplete. The final
data check identified a historical R1.1 prose discrepancy: the CSV yields aggregate
medians 0.0019 / 0.0059 / 2.9535 ms (Full / DAG / GAMO), while its README states
0.0027 / 0.0078 / 3.1627 ms. The dashboard uses CSV values; original files are unchanged.
R1.2's saved model uses the matching CSV sums, so it is retained as recorded.

Added `docs/final-presentation/` with judge overview, methodology, three-minute demo,
ten jury questions, startup, preservation lock, and verification report. ADR-013
records the explicit offline/live boundary. No project dependency was added.

| Executed command | Actual result |
| --- | --- |
| `npm run format:check`, `npm run lint`, `npm run typecheck` | Passed |
| `npm test` | 3 contract tests + 15 web tests passed (4 web test files) |
| `npm run web:build` | Passed; Vite production assets built |
| `.venv/Scripts/python scripts/tasks.py check-python` | Ruff passed; 101 files formatted; mypy passed for 36 source files; 112 passed, 7 skipped, 1 existing Starlette/httpx deprecation warning |
| `.venv/Scripts/python scripts/tasks.py schemas --check` | Passed; contracts unchanged |
| `.venv/Scripts/python scripts/export_presentation.py --check` | 22 preserved file hashes matched; fixture matched pure planner and original R1.1 decisions |
| `.venv/Scripts/python scripts/tasks.py verify-test-gate` | Verified deliberately broken temporary test is rejected with pytest exit 1; gate command passed |
| `.venv/Scripts/python scripts/tasks.py demo` | Existing two-scenario pure-kernel demo executed with SIMULATED / publication NOT_IMPLEMENTED labels |
| `node scripts/check_presentation_browser.cjs` with available Playwright and installed Chrome | Passed on dev and production preview; final production run checked all 16 outcome settings, reset/repeat, actual graph reasons, sensitivity, byte-identical source CSV download, responsive overflow, explicit live login, no offline API requests, and no page errors |

The seven skips were live artifact PostgreSQL, authenticated API PostgreSQL, Phase 2E
live HTTP, three PostgreSQL concurrency cases, and Neo4j projection integration.
Required test connection variables were unset. These skips are not live passes;
PostgreSQL/Neo4j integration was not revalidated in this build. Browser QA used
headless Chrome 154.0.8037.98 at desktop 1440×1000, laptop 1280×800, and mobile
390×844. Screenshots were actually inspected and UI readability/layout refined.
The production preview ran at `http://127.0.0.1:4173/`; local screenshots and the
download are under ignored `var/presentation-qa/`. Hosted CI was not run.

The presentation implementation is ready to demonstrate. Student/judge comprehension
and the three-minute delivery have not been measured with humans. Independent
validation and equally safeguarded baseline comparisons remain open. No superiority,
novelty, significance, universal safety, real generation, or real savings claim is
made. See [`../final-presentation/verification.md`](../final-presentation/verification.md).
