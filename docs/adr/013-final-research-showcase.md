# ADR-013 — Final research showcase using preserved data

Status: accepted for the final presentation build, 2026-10-15.

The judging demonstration must run reliably without requiring local database services
or credentials. Extend the existing React app with overview, graph, and results
sections. Reuse the existing graph canvas, inspector, and authenticated explorer.
No backend, service, database, or domain-algorithm changes are needed.

The default mode is explicitly SIMULATED / OFFLINE. A small Python exporter calls the
pure planner on the original R1.1 slogan fixture, verifies every action against saved
node decisions, and serializes the graph/plan. The browser previews that saved plan;
it does not pretend to execute the algorithm on arbitrary new inputs, generate content,
advance authoritative versions, approve, or publish. Reset clears local presentation
state. Live API is a separate explicitly selected mode with the existing in-memory
bearer flow. There is no automatic fallback between the two.

Vite imports the preserved CSVs directly. A dependency-free CSV reader converts them
to typed records; charts derive operation totals and descriptive medians or select
saved sensitivity/outcome rows. CSV downloads return original data. No new chart,
router, AI-provider, or UI dependency is added. Hash navigation is sufficient for
three pages. `research-artifact-lock.json` and the exporter check freeze the original
22 R1.1–R1.4 files without rewriting them or rerunning timings.

The showcase distinguishes synthetic inputs, measured planner timing, planned action
counts, and hypothetical cost units. It states that field-aware DAG matched GAMO-CA
on R1.3, current timing work is asymmetric, and independent review is incomplete.
Human validation and a fair equal-safeguard comparison remain research gates. A
completed presentation is not evidence of superiority or novelty.

The optional browser smoke script uses an already available Playwright runtime and
browser through environment-configured paths. It adds no project dependency. Screenshot
and download evidence stays under the ignored local `var/presentation-qa/` directory.
