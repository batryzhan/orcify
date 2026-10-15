# Final presentation verification — 2026-10-15

This is engineering verification of the existing research showcase, not an additional
scientific experiment, independent validation, or a performance benchmark.

## Scope delivered

The existing app now has Research overview, Graph & impact, and Experiments & results.
The default deterministic offline demo uses the original slogan-change graph and a
Python-exported plan whose actions match saved R1.1 decisions. It supports selection,
zoom/pan, exact node/dependency inspection, impact colors/reasons, and reset/repeat.
Live API remains an explicitly selected authenticated view with its original backend.

R1.1 counts/reviews/timings, R1.2 hypothetical sensitivity, and all 16 R1.3 review/replan
outcomes load from original CSVs. Field-aware DAG equivalence and higher asymmetric
GAMO-CA planning overhead are disclosed. The 22 original R1.1–R1.4 files are unchanged
under the preservation lock. A historical R1.1 prose-versus-CSV timing discrepancy is
recorded in `methodology.md`; the dashboard uses CSV values.

No backend endpoint, database migration, service, paid provider, external publication,
or new project dependency was added. No new experiment or human response was created.

## Executed checks

| Check | Result |
| --- | --- |
| `npm run format:check` | Passed |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm test` | 3 contract tests and 15 web tests passed (4 web test files) |
| `npm run web:build` | Passed; Vite production assets generated |
| `.venv/Scripts/python scripts/tasks.py check-python` | Ruff passed; 101 files formatted; mypy passed for 36 source files; 112 passed, 7 skipped, 1 existing deprecation warning |
| `.venv/Scripts/python scripts/tasks.py schemas --check` | Passed; no contract drift |
| `.venv/Scripts/python scripts/export_presentation.py --check` | All 22 research-file hashes unchanged; fixture matches current planner and saved node actions |
| `.venv/Scripts/python scripts/tasks.py verify-test-gate` | Deliberately broken temporary test rejected with expected pytest exit 1; verification command passed |
| `.venv/Scripts/python scripts/tasks.py demo` | Existing two pure-kernel scenarios ran with explicit SIMULATED / publication NOT_IMPLEMENTED labels |
| `git diff --check` and frontend bearer-pattern scan | No whitespace errors; no provisioned `orc_` bearer-token patterns found in frontend source or built assets |
| `node scripts/check_presentation_browser.cjs` with the available Playwright module and Chrome | Passed on development server, then production preview `http://127.0.0.1:4173/` |

Python ran locally on Python 3.14.6 / Windows. The seven skipped tests require unset
PostgreSQL and/or Neo4j test connection variables: artifact PostgreSQL, authenticated
API PostgreSQL, Phase 2E live HTTP, three concurrency tests, and live projection.
Those services were not revalidated by this presentation build. The warning is
Starlette's existing test-client/httpx deprecation. Hosted CI was not run.

The actual browser was headless installed Chrome 154.0.8037.98, driven by an already
available Playwright runtime. The desktop viewport was 1440×1000, laptop 1280×800,
and mobile 390×844. Screenshots were visually inspected and the graph's source order,
inspector text, contrast, and immediate impact counts were refined.

Browser assertions covered navigation, actual rendered graph actions and returned
reasons, reset/repeat, all 16 saved outcome controls, a sensitivity setting favoring
conventional DAG, byte-identical original CSV download, responsive overflow checks,
and explicit switching to the live login. The offline flow made no API requests and
raised no browser page errors. No actual live bearer authentication was exercised
by this browser script. Screenshots/download evidence is local under ignored
`var/presentation-qa/`.

## Completion and limits

The requested presentation implementation is complete: coherent pages, resettable
demo, sourced charts, build/tests, local startup, three-minute script, jury questions,
and honest limitations. The 30-second understanding and three-minute delivery are
presentation design goals, not measured user-study outcomes; a student should rehearse.
Independent human validation remains pending, no equal-safeguard advantage is isolated,
and real-world usefulness, cost savings, statistical significance, and scientific
novelty have not been established. This ready-to-demonstrate prototype does not close
those scientific gates.

## Files changed for the presentation

- `apps/web/src/research/`: showcase pages, CSV-derived results, generated fixture,
  styling, and data/interaction tests.
- `apps/web/src/main.tsx`, `apps/web/index.html`: app entry and research metadata.
- `apps/web/src/app/App.tsx`: reuse/export inspector, research-oriented local login,
  remove unused help control, and accurate API connection status.
- `apps/web/src/graph/GraphCanvas.tsx`, `model.ts`: optional display labels/actions
  and layout ordering for clearer typed-graph presentation.
- `scripts/export_presentation.py`, `tests/test_final_presentation.py`: preservation
  lock and domain-to-presentation fixture checks.
- `scripts/check_presentation_browser.cjs`: optional browser verification.
- `docs/final-presentation/`, `docs/adr/013-final-research-showcase.md`, root/web
  READMEs, `TASK.md`, experiment log, limitations, and `.gitignore` for local QA output.

Other pre-existing uncommitted repository work was preserved.
