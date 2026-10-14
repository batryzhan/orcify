# ADR-009: Server-verified authentication and tenant-scoped API

Status: accepted for the Phase 2D prototype.

## Context

The event and artifact stores accept tenant, project and human actor identity as
trusted service arguments. A network API must authenticate those values before it
calls the domain and persistence layers. Client headers and JSON fields cannot
establish an actor, tenant role, reviewer identity or authorization decision.

## Decision

Use opaque, high-entropy bearer tokens for the MVP. The provisioning utility creates
a token once and stores only its SHA-256 digest in PostgreSQL. Every protected request resolves
the digest to a credential row, rejects expired or revoked credentials, then loads an
active actor/tenant role from `tenant_memberships`. Membership is checked on each
tenant/project operation. Tenant IDs in paths select a scope; they never grant it.
Unauthorized access to resources outside the caller's tenant returns 404 to avoid
resource-existence disclosure. Authenticated roles that lack an operation permission
receive 403.

Roles are `tenant_admin`, `producer`, `editor`, `reviewer`, and `researcher`. Roles
are tenant-wide in this MVP and are applied consistently to each project in that
tenant. Project reads allow all active roles; graph writes allow producer, editor,
and reviewer; approval submission allows those roles; approve/reject/revoke requires
reviewer; artifact/execution writes allow tenant admin, producer, and editor. The
domain `ReviewerIdentity` and `GraphChangeIdentity` objects are created only after
credential and membership checks. Actor, tenant, and project claims are omitted from
write request schemas and derived by the server.

The HTTP API recomputes a plan against the current PostgreSQL graph before accepting
an approval, artifact, or execution run. A submitted plan must equal that result.
Graph changes, approvals, artifact/run writes and eligibility delegate to existing
transactional services. Eligibility reads and locks PostgreSQL project state and
approval history; Neo4j is never consulted for authority decisions. Writes use the
existing idempotency and optimistic-concurrency contracts. No publishing side
effects are exposed.

`api_credentials` and `tenant_memberships` are added in migration
`0007_authenticated_api`. The provisioning script requires `DATABASE_URL`, enforces
finite token expiry, refuses to silently replace an existing membership, and prints
the raw credential once. Operators must provision identities through a trusted
administrative environment and deliver tokens through a secure channel. `.env.example`
contains no token or production secret.

## Consequences and limitations

Opaque bearer credentials are simple to revoke and do not require a paid identity
provider, but do not provide interactive login, SSO, key rotation automation, scoped
project roles, or built-in multi-factor authentication. Membership is tenant-wide.
Credential and membership administration is currently an operator/database task;
there is no public self-service identity API. Requests are stateless and do not
refresh credentials. Production deployment still requires TLS, secret-safe token
delivery, database role separation, rate limits, audit/alerting, and operational
credential rotation procedures. Security tests validate these implemented cases but
do not establish universal security.

Phase 2E validates this boundary through a live HTTP smoke scenario and a live PostgreSQL + Neo4j test; see [ADR-010](010-reproducible-api-demo.md) and the experiment log. The demo uses only synthetic identities and data.
