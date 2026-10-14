# Infrastructure boundary

`compose.yaml` defines local PostgreSQL 16 and Neo4j 5 services with health checks
and named data volumes. Credentials are local development defaults only; set
unique values in `.env` before exposing either service beyond localhost.

From the repository root, copy `.env.example` to `.env`, then run:

```powershell
docker compose -f infra/compose.yaml up -d --wait
.venv/Scripts/python -m alembic -c services/api/alembic.ini upgrade head
```

Use `docker compose -f infra/compose.yaml ps` to inspect health and `down` to stop
services while retaining volumes. No database is required for the offline GAMO-CA
preview. PostgreSQL is authoritative; Neo4j is reserved for the rebuildable
projection. Migrations create immutable project snapshots/events, retryable outbox
delivery state and per-project projection checkpoints. See ADR-002 and ADR-007.
Migrations `0005_artifacts_execution` and `0006_execution_header_guards` add immutable
artifact versions, artifact provenance, execution run/attempt indexes, append-only
execution lifecycle events, and database guards for immutable run/attempt metadata.
These rows are PostgreSQL authority records; they do not invoke AI providers or
external publication. See ADR-008 for transaction and eligibility rules.

Run the outbox consumer from the repository root after migrations. Provide the same
database and Neo4j values used by Compose through the process environment; the worker
does not read credentials from request payloads or graph data.

```powershell
$env:DATABASE_URL = "postgresql+psycopg://orcify:YOUR_PASSWORD@localhost:5432/orcify"
$env:NEO4J_URI = "bolt://localhost:7687"
$env:NEO4J_USER = "neo4j"
$env:NEO4J_PASSWORD = "YOUR_PASSWORD"
.venv/Scripts/python scripts/run_projection_worker.py
```

The worker performs an authoritative reconciliation at startup and every 60 seconds,
then consumes ordered outbox rows. Retry limits and backoff are defined in
`WorkerConfig`; exhausted deliveries stay dead-lettered and block later events for
that project until reconciliation rebuilds the projection. Stop the process with
Ctrl+C. The worker only projects internal graph data and does not publish content.

Set `ORCIFY_TEST_DATABASE_URL` to a disposable migrated PostgreSQL database to run
the real row-lock/concurrent-update integration tests. To include the live projection
test, also set `ORCIFY_TEST_NEO4J_URI`, `ORCIFY_TEST_NEO4J_USER`, and
`ORCIFY_TEST_NEO4J_PASSWORD`. SQLite tests cover failure injection and migration shape
but do not verify PostgreSQL locking or Neo4j transaction semantics.
