# Orcify 2.0 — final research presentation

Run `npm run dev` from the repository root. The default view is a research overview
with navigation to the deterministic graph demo and saved experiment results. It needs
no token or backend. The presentation is clearly labeled SIMULATED / OFFLINE and does
not execute creative work, approve content, or publish.

`src/research/` contains the showcase, a small CSV parser, and direct Vite imports of
the original R1.1–R1.3 data. The generated `demo.json` is exported from the existing
Python slogan fixture and checked against saved R1.1 node decisions. Run
`.venv/Scripts/python scripts/export_presentation.py --check` from the root to verify
fixture and preserved-file integrity. Counts and timings come from saved files; the
sensitivity controls select hypothetical cost rows, not new measurements.

Graph & impact → Live API reuses the authenticated explorer below. Offline and live
modes are explicitly selected; API errors are never replaced with saved data. The
presentation needs no new dependency or endpoint. See
[`docs/final-presentation/`](../../docs/final-presentation/startup.md) for the judge's
guide, exact startup, methodology, and limitations. Independent human validation is
pending; no superiority or novelty is established.

## Existing authenticated explorer (Phase 3A)

Read-only React/TypeScript application. It uses Vite, Tailwind CSS, local shadcn-style
accessible primitives, TanStack Query, and React Flow. The generated OpenAPI types in
`src/api/generated.ts` come from `docs/api/openapi.json`; regenerate them from the
repository root with `npm run web:types`. Run the API and its databases using the
root README instructions, then launch the explorer with `npm run web:dev`.

The Vite development server proxies `/api` to `http://127.0.0.1:8000`. Override the
server-side target with `ORCIFY_API_PROXY` when needed. For a separately hosted API,
set `VITE_API_BASE_URL` before building and allow the web origin in
`ORCIFY_WEB_ORIGINS` on the API. API access and tenant selection are derived from a
server-provisioned bearer token and live memberships. The token exists only in React
memory for the current tab; it is not persisted or written to a URL or log.

This milestone can read graph snapshots, plans, artifacts, approval history, and
eligibility. The only write-like action is a non-mutating plan preview. Approval,
graph mutation, artifact creation, and publication controls are not present.
