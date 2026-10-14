# API boundary

The Phase 2 first slice adds SQLAlchemy 2.x persistence and Alembic migrations.
`app/event_store.py` accepts a tenant/project scope only as trusted service input;
the authenticated FastAPI boundary derives scope and actor identity from a verified
bearer credential and PostgreSQL membership rather than request JSON. It reduces events through `packages/gamo_ca.events` and appends
the event, replay state, immutable replay snapshot, project revision and Neo4j
outbox row in one transaction. Project creation also persists the full typed
initial graph snapshot. Approval writes invoke `packages/gamo_ca.approvals` under
the project lock and append exact-version records. PostgreSQL row locks serialize
updates; unique constraints and append-only triggers protect history. SQLite tests
cover offline behavior. Live PostgreSQL integration tests are gated by
`ORCIFY_TEST_DATABASE_URL` and have passed against PostgreSQL 16.15.

FastAPI v1 routes now live in `app/http.py`. Authentication uses opaque random bearer
credentials with only SHA-256 digests stored in PostgreSQL; actors and tenant roles
are resolved from `api_credentials` and `tenant_memberships` on each request. Client
tenant/project/actor/reviewer claims do not grant access. See ADR-009. Provision an
identity from a trusted operator shell after migrations using
`python scripts/provision_api_identity.py --tenant TENANT --actor ACTOR --role tenant_admin`.
The command prints its credential once. Keep it in a secret manager and send it over
a secure channel. Run the service with `uvicorn services.api.app.http:app`; OpenAPI
is available at `/docs` and the committed contract is `docs/api/openapi.json`.

The API exposes project create/list/get, authoritative current graph retrieval,
graph-change submission, plan preview, exact-version approval transitions, artifact
create/retrieval/eligibility, and execution run/attempt history and transitions. It
recomputes planning decisions against PostgreSQL before approvals, artifacts, and
execution runs. Eligibility delegates to the current-state transaction in the artifact
store; Neo4j is not consulted. No publishing endpoint or real model provider exists.
Tenant roles are currently tenant-wide; interactive login, SSO and scoped project
roles remain limitations. API auth and OpenAPI tests use SQLite; a separate opt-in
test checks authentication and revocation against PostgreSQL via
`ORCIFY_TEST_DATABASE_URL`.

Artifact versions and append-only provenance now live in `app/artifact_store.py`. They bind exact graph snapshots, asset node versions,
dependency versions, source provenance, and a content hash. Execution runs/attempts
have transactionally updated status indexes and immutable lifecycle events; missing,
estimated, and measured values are explicitly distinguished. Artifact eligibility
re-reads authoritative graph and approval rows and calls the pure publication predicate.
Migration `0005_artifacts_execution` adds these tables and append-only triggers;
`0006_execution_header_guards` protects run/attempt metadata. The
Neo4j projection
worker lives in `app/projection_worker.py`, uses `app/neo4j_projection.py`, and can be
run with `scripts/run_projection_worker.py`. It consumes full graph events from the
PostgreSQL outbox, tracks retry/checkpoint state in PostgreSQL, applies ordered scoped
Neo4j transactions, and periodically reconciles from authoritative snapshots. The
pure domain under
`packages/gamo_ca` imports none of these frameworks. Generated domain JSON contracts
are under `docs/api/schemas`; the HTTP contract is generated separately as
`docs/api/openapi.json`.

## Phase 2E live validation and demo

`python scripts/seed_demo.py` provisions the deterministic `demo-tenant` identities,
`demo-project` graph, and an unapproved synthetic `demo-copy-v1` artifact. It writes
random two-day tokens to `var/demo-tokens.json` (git-ignored, never printed) and rotates
prior active credentials on reseed. The revoked-token fixture is included for denial
checks. Do not commit or share the token file. The sample project must still match its
baseline graph; use a fresh database if it has already advanced.

For a production-like local run, start PostgreSQL and Neo4j with
`docker compose -f infra/compose.yaml up -d --wait`, apply Alembic migrations, and set
`DATABASE_URL`, `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` in each process
environment. Run the API with
`python -m uvicorn services.api.app.http:app --host 127.0.0.1 --port 8000`, and run the outbox projection consumer separately with
`python scripts/run_projection_worker.py`. Then run
`python scripts/run_api_smoke.py --run-id <unique-id>` against the API. The script uses
real HTTP requests, explicitly approves the exact artifact version as the reviewer,
changes a confirmed requirement, checks fail-closed eligibility, submits two concurrent
idempotent graph requests, and forces Neo4j reconciliation from PostgreSQL. Each run
creates a new synthetic project and retains its immutable audit records for inspection.

Live database tests are opt-in. Set `ORCIFY_TEST_DATABASE_URL` and the four
`ORCIFY_TEST_NEO4J_*` values before running
`python -m pytest -q services/api/tests/test_phase2e_live_e2e.py services/api/tests/test_projection_integration.py`. Without them pytest marks those
live integration tests skipped. The Phase 2E experiment log records the exact result
from this environment. No publishing route is present; the smoke workflow never sends
an external side effect.
