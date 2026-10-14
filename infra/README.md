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
projection. The initial migration creates project replay state, immutable change
events, uniqueness constraints and the transactional outbox. See ADR-002.

Set `ORCIFY_TEST_DATABASE_URL` to a disposable migrated PostgreSQL database to run
the real row-lock/concurrent-update integration test. SQLite tests cover reducer,
rollback, migration shape and idempotency behavior but do not verify PostgreSQL
locking semantics.
