# API boundary

The Phase 2 first slice adds SQLAlchemy 2.x persistence and Alembic migrations.
`app/event_store.py` accepts a tenant/project scope only as trusted service input;
the future HTTP dependency must derive it from verified authentication rather
than request JSON. It reduces events through `packages/gamo_ca.events` and appends
the event, replay state, immutable replay snapshot, project revision and Neo4j
outbox row in one transaction. Project creation also persists the full typed
initial graph snapshot. Approval writes invoke `packages/gamo_ca.approvals` under
the project lock and append exact-version records. PostgreSQL row locks serialize
updates; unique constraints and append-only triggers protect history. SQLite tests
cover offline behavior. Live PostgreSQL integration tests are gated by
`ORCIFY_TEST_DATABASE_URL` and have passed against PostgreSQL 16.15.

FastAPI routes, authenticated identity construction, full graph snapshot
advancement, artifact/run-log persistence and the Neo4j projection worker remain
later Phase 2 tasks. The pure domain under
`packages/gamo_ca` imports none of these frameworks. Generated JSON contracts are
under `docs/api/schemas`; they are not OpenAPI routes.
