# Execution log

## 2026-10-14 — foundation and pure-kernel milestone

Observation category: MEASURED local engineering checks, **not research benchmark
results**. All demonstration content and estimates are SIMULATED synthetic fixtures.

Environment: Windows PowerShell, Python 3.14.6, Node 24.18.1, pytest 9.1.1.
Exact Python versions: `requirements-dev.lock`; JS versions: `package-lock.json`.
Git SHA unavailable: the input folder is not a Git repository. No remote was
configured, no hosted CI was run, no paid APIs were called. Raw local console
observations are summarized below; no latency/cost effectiveness measurements.

Source PDF was read across all 13 pages and visually inspected. Reference copy
SHA-256 matches original: `2b64557eb4073706c2d2263c6db35a78f06afedd8b5b8929011b17254f7d51d5`.
Source differences (invariants, B2, objective and ablations) are in spec-mapping.
Initial prior-art browser review is in related-work; failed publisher accesses
are explicitly recorded rather than treated as verified citations.

Tests were authored before the implementation. First collection failed while
fixtures were absent. After implementation, explicit safety regression tests
failed for review/recompute merge, stale SOFT inputs and unconfirmed change
targets; fixes made these fail-closed. These are engineering observations, not
performance comparisons or proof of universal safety.

| Executed command | Observed result |
| --- | --- |
| `python -m venv .venv`; `.venv/Scripts/python -m pip install -e '.[dev]'` | Environment created, developer dependencies installed |
| `npm install --save-dev typescript @types/node eslint typescript-eslint prettier` | Packages installed and lockfile generated |
| `npm ci`; `.venv/Scripts/python -m pip install -r requirements-dev.lock`; `.venv/Scripts/python -m pip install --no-deps -e .` | Documented lockfile setup commands verified locally |
| `.venv/Scripts/python scripts/tasks.py check-python` | Ruff lint/format passed, strict mypy passed (11 Python files), 25 pytest tests passed |
| `.venv/Scripts/python scripts/tasks.py schemas --check` | All 12 entity schemas + Plan and shared Python→TS plan fixture match source |
| `.venv/Scripts/python scripts/tasks.py verify-test-gate` | Deliberate broken test rejected with exit 1; temporary test removed |
| `npm run format:check` | Prettier check passed |
| `npm run lint` | ESLint passed |
| `npm run typecheck` | Strict TypeScript check passed |
| `npm test` | 3 Node/TypeScript contract tests passed |
| `.venv/Scripts/python scripts/tasks.py demo` | Both JSON plan previews ran without keys/databases; publication explicitly NOT_IMPLEMENTED |

25 Python tests include property-based DAG reachability against an independent
fixed-point oracle, stable topological order, scope violations, cycles, immutable
JSON round trips, fingerprints, stale snapshots, missing provenance, unconfirmed
requirements, temporal edge expiry and review holds. They do not cover the yet
unimplemented approval state machine, authenticated access, external-side-effect
idempotency, transactional races, provider failures or publication predicate.

Synthetic demo: slogan change rebuild candidates are copy/storyboard; visual and
visual_export await review; logo is retained. Unrelated note has no rebuild
candidates. KEEP grants no approval; previews perform no side effects. Serial
latency/cost estimates are fixture constants, not measured trials.

Next: Phase 1 exact-version approval state machine with rejected/revoked decisions,
requirement snapshot and human actor checks; then publication eligibility and full
invariant tests. Gate A remains open. API/persistence/React are subsequent phases.
