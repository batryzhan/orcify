# Orcify 2.0 — a student research prototype

## The problem, in 30 seconds

A creative campaign contains connected work: requirements, copy, images, storyboards,
and exports. When a requirement changes, rebuilding everything may waste work, while
keeping the wrong version can cause a mistake. Orcify explores how to identify the
work that must change and the work that needs a person to inspect it.

## The research question

Can typed dependencies, input versions, and explicit human review reduce unnecessary
recomputation while respecting exact-version approval? This is a hypothesis to test,
not a demonstrated general advantage.

## How GAMO-CA works

Think of each asset as a recipe and each dependency as an ingredient. The planner
follows changed inputs through the graph:

- **HARD:** a changed mandatory input requires recomputation.
- **SOFT:** compare the changed fields with the fields relevant to that link. If
  relevance is unknown, ask for review.
- **INFORMATIONAL:** record context without invalidating the asset just for that link.

The decisions are **RECOMPUTE** (make a new version), **REVIEW** (pause for a person),
and **KEEP** (reuse the current version for this change). Invalid inputs can be
**BLOCK**ed. A HARD child of an unresolved review must also wait. The planner visits
the graph in dependency order and records reasons for its decisions.

Approval is a different question. An approval is tied to an exact asset version,
requirement snapshot, human actor, and policy. KEEP never grants approval. The
presentation preview does not generate, approve, or publish anything.

## What the pilot found

R1.1 uses five authored synthetic changes: slogan, brand guidelines, asset version,
approval invalidation, and an all-HARD example with no recomputation advantage.
Initial recomputation totals were 24 for Full Recompute, 21 for Conventional DAG,
and 12 for GAMO-CA. Eight operations in that apparent difference were deferred
behind review, rather than shown to be permanently avoided.

R1.3 tests all 16 material/non-material combinations of four uncertain SOFT branches.
GAMO-CA's final planned recomputations range from 12 to 20. A straightforward
Field-aware DAG using the same field information matches its final actions and
recomputation counts across these outcomes. This pilot does not establish GAMO-CA
superiority or scientific novelty.

GAMO-CA planning is substantially slower in the current code. Timing work is unequal:
GAMO-CA validates and hashes graphs and constructs explanations, while the simple
baselines do less. The results dashboard reads saved timing values directly from CSVs.
No AI generation, human duration, real-world savings, or statistical significance
was measured. R1.2 cost weights are explicitly hypothetical work units.

## What is complete, and what remains open

The deterministic algorithm, engineering safety tests, reproducible small pilot,
read-only graph demonstration, saved-results dashboard, and presentation materials
are available. R1.4 prepares a blinded worksheet and import tools; real independent
human validation has not been completed. No larger benchmark is started by this build.

The practical engineering value is traceability and explicit safety gates. Their
measurable advantage over a simpler DAG with equivalent approval, provenance, and
recovery safeguards remains an open question. A clear negative or limited result
is still a useful scientific finding.

Read [methodology.md](methodology.md), [demo-script.md](demo-script.md),
[jury-questions.md](jury-questions.md), and [startup.md](startup.md) for preparation.
