# ADR-011: Read-only authenticated graph and impact explorer

Status: accepted for the Phase 3A prototype; 2026-10-14.

## Context

The Phase 2E API had project and graph reads, planner preview, artifact detail, and
per-artifact eligibility. A client could not enumerate the authenticated actor's
active tenant memberships, project artifacts, or approval history, so it could not
present safe tenant selection or explain the exact-version approval state from API
authority.

## Decision

Add three authenticated, read-only API capabilities: list active tenant memberships
for the actor resolved from the bearer credential, list immutable artifacts within an
authorized tenant/project, and list append-only approval records within that same
scope. No tenant/actor claims are accepted from the client. Artifact eligibility
continues to use the existing PostgreSQL current-state transaction and pure domain
predicate. The additions require no schema migration and do not consult Neo4j.

The web client types are generated from `docs/api/openapi.json` with
`openapi-typescript`. Tenant and project choices come from API responses after
authentication. A server-provisioned opaque bearer token is held in React memory for
the current tab only; it is never placed in persistent browser storage, URLs, or
application logs. Local development uses the Vite same-origin `/api` proxy. Optional
cross-origin deployment uses an explicit `ORCIFY_WEB_ORIGINS` allow-list with no
wildcard and no cookie credentials.

The React Flow view is read-only: graph layout is deterministically derived from the
authoritative snapshot, nodes cannot be dragged or connected, and active typed edges
are rendered by their strength. The proposal form sends only the existing planner
preview request. It does not append a graph event, create an artifact, transition an
approval, execute a provider, or publish. Planner explanations are rendered from the
returned decision reasons. `KEEP` is explicitly labeled as reuse information and
never as approval. Eligibility and exact-version approval history are shown from
their respective PostgreSQL-backed API responses; failed reads remain unavailable,
not inferred.

## Consequences and limitations

The API now exposes active tenant IDs/roles and project artifact/approval metadata to
active members, consistent with the existing tenant-wide role model. The UI is an MVP
explorer, not a complete creative workflow. The API still lacks artifact diffs,
historical graph retrieval, pagination, and a browser login/SSO flow. Local CSS
variables and small shadcn-style primitives are used with Tailwind, rather than a
generated shadcn component library. No scientific benchmark, usability study, or
performance result is claimed. See the Phase 3A experiment log and limitations.
