# ADR-010: Reproducible authenticated API demo and live validation

Status: accepted and implemented for Phase 2E; 2026-10-14.

## Context

The authenticated routes had isolated SQLite route tests and separate persistence and
projection integration tests. Reviewers needed one documented scenario that exercises
the real API boundary, authoritative PostgreSQL transactions, and the rebuildable
Neo4j projection without requiring a paid provider or an external publishing account.

## Decision

The demo data is generated from fixed synthetic GAMO-CA fixtures. `scripts/seed_demo.py`
uses stable tenant, actor, project, graph, artifact and provenance IDs; it refuses to
silently replace a demo membership with another role or overwrite an advanced baseline
project. The sample artifact is never pre-approved. The script creates random short-lived
bearer credentials, stores token digests in PostgreSQL, rotates prior active credentials,
and writes the raw tokens only to a git-ignored local file with restrictive permissions
where supported. Token values are not printed or committed.

`scripts/run_api_smoke.py` uses HTTP against a running API. It creates a new synthetic
project, obtains a GAMO-CA impact plan, stores an immutable artifact, submits it for
review, and requires a reviewer credential to approve that exact version. It then
changes a confirmed requirement, checks recomputation and stale eligibility, exercises
concurrent idempotent graph writes, and invokes Neo4j reconciliation from PostgreSQL.
No external provider or publication endpoint is called. Smoke-run IDs allow repeatable
project IDs on a fresh database; append-only history is retained for inspection.

A live pytest integration test covers the same critical authenticated workflow against
PostgreSQL and Neo4j and cleans its unique synthetic tenant after completion. The
projection integration test separately continues to cover outbox delivery, stale
updates, scope isolation and reconciliation. PostgreSQL remains authoritative for
eligibility and projection rebuild input.

## Consequences and limitations

The smoke workflow exercises local engineering integration, not scientific performance
or universal safety. Seed credentials are bearer secrets and the local token file must
be protected and removed after use. The baseline seed project is intentionally immutable;
a clean database is needed to reseed after it has advanced. Each smoke run leaves
append-only rows, so use unique IDs or a disposable database. Compose health metadata
requires Docker Desktop and was not inspected in shells where the Docker CLI was
unavailable. The live HTTP smoke uses local services and does not establish production
readiness, SSO/MFA, rate limits, or multi-user operational recovery.
