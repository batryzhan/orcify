# Simple local startup

## Presentation mode (recommended for judging)

From the existing repository root, with Node 22+:

```powershell
npm ci
npm run dev
```

Open the URL printed by Vite (normally `http://127.0.0.1:5173/`). Start on Research
overview, then Graph & impact, then Experiments & results. The default offline mode
loads the committed graph/plan fixture and original CSVs. No token, database, paid
provider, or external publishing service is needed. It is labeled SIMULATED and does
not mutate backend state. Use Reset demo to clear the preview and recenter the graph.

The production frontend can be built with `npm run web:build`. For a local preview:

```powershell
npm --workspace apps/web exec -- vite preview --host 127.0.0.1
```

## Verification

With the existing `.venv` and locked Python dependencies installed:

```powershell
.venv/Scripts/python scripts/export_presentation.py --check
.venv/Scripts/python scripts/tasks.py check-python
npm run format:check
npm run lint
npm run typecheck
npm test
npm run web:build
```

The fixture exporter verifies current Python planner decisions against saved R1.1
node decisions and checks hashes for all 22 R1.1–R1.4 files. It does not rerun timed
experiments or overwrite those results. Live database tests skip when the documented
test connection variables are unset; a skip is not a live pass.

Optional browser QA is in `scripts/check_presentation_browser.cjs`. If Playwright
and a browser are already available locally, set `ORCIFY_PLAYWRIGHT_MODULE` to that
module path and `ORCIFY_BROWSER_EXECUTABLE` to the browser executable, then run
`node scripts/check_presentation_browser.cjs` with Vite running. Set
`ORCIFY_PRESENTATION_URL` to a production preview URL when checking the built app.
This needs no new project dependency. Screenshots and the checked CSV download are
saved locally under ignored `var/presentation-qa/`.

## Optional authenticated API explorer

Choose Graph & impact → Live API to reuse the existing authorized explorer. Start
PostgreSQL, apply existing Alembic migrations, provision a local token, and start the
FastAPI server following the repository README's Phase 2E instructions. Neo4j and
the projection worker are optional support for the existing live projection demo;
PostgreSQL remains authoritative. This presentation build adds no backend endpoint,
migration, or service.

Paste the server-provisioned token only into the password field locally. It remains
in memory; never add it to source code, URLs, persistent browser storage, or shared
logs. The offline demonstration is explicitly selected, never a silent fallback for
a failed live request. If port 5173 is occupied, use the URL printed by Vite or stop
your earlier dev server.

If the saved interface fails, run the verification commands and inspect the actual
error. Do not manufacture replacement data. Human-validation results are unavailable
until real worksheets are received and inspected through the R1.4 process.
