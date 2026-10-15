# R1.1 — Minimal scientific pilot

Status: run once on five hand-authored synthetic scenarios. This is a small pilot,
not a statistically powered benchmark and not evidence of universal safety or research
novelty. Review the correctness obligations and scenario assumptions before starting a
larger study.

## Reproduce

From the repository root, with the project's Python environment installed:

```powershell
.venv/Scripts/python scripts/r1_1_pilot.py --seed 20261014 --timing-repeats 101
.venv/Scripts/python -m pytest -q tests/test_r1_1_pilot.py
```

The script uses only Python's standard library and the existing pure `gamo_ca` package.
It makes no API, database, provider, or network calls. The seed selects one of three
synthetic slogan strings; the generated graph/event hashes and oracle sets are saved
in `manifest.json`. All three methods receive the same immutable graph and change
event for each scenario.

## Decisions and operation meanings

- **KEEP:** retain the current computed node. It does not assert that a human approved
  the content, that an approval remains current, or that publication is permitted.
- **REVIEW:** pause the affected item for a human relevance/safety check. It is not
  regenerated until that review resolves the uncertainty.
- **RECOMPUTE:** regenerate an affected derived creative asset from its current inputs.
  A newly generated version has no inherited approval and needs a new human review.
- **BLOCK:** fail closed because a required input, evidence item, or safety condition
  is not satisfied. A blocked item cannot be published.

One recomputation operation is one `AssetVersion` node scheduled for regeneration.
One review operation is one distinct node that needs impact review, exact-version
approval after regeneration, or renewed approval after requirement-snapshot
invalidation. Review and recomputation are separate counts, not combined into a single
weighted score. Neither count measures human minutes, GPU time, API tokens, or money.

## Algorithms

The two baselines below are implemented independently of `gamo_ca.planner` in
`scripts/r1_1_pilot.py`.

```text
Full Recompute:
  mark every derived creative asset for recomputation, except the externally changed source

Conventional DAG Incremental:
  start at the changed node
  follow every downstream HARD or SOFT dependency
  recompute every derived asset reached
  ignore INFORMATIONAL links

GAMO-CA:
  call the existing pure plan_change(graph, event, policy)
  preserve its KEEP / REVIEW / RECOMPUTE / BLOCK actions and explanations
```

This DAG baseline treats HARD and SOFT edges as ordinary dependencies and recomputes
both, a conservative conventional-cache policy. The GAMO-CA planner can use typed
strength and explicit changed-field relevance to distinguish recomputation from review
or retention. The pilot does not include the research proposal's separate graph-context
retrieval baseline because retrieval is not part of this change-impact question.

## Independent correctness oracle

Before any planner is called, each scenario declares by hand:

1. the nodes whose stale HARD input requires recomputation;
2. the nodes with uncertain SOFT impact that must not be silently kept;
3. every initially approved exact asset version and the approvals invalidated by the
   event.

The oracle accepts `RECOMPUTE` for a listed uncertain SOFT node as a conservative
response; `REVIEW` and `BLOCK` are also safe. It accepts no action except `RECOMPUTE`
for a listed stale HARD node. It independently applies the exact-approval rule: an
approval is unusable after the asset version changes, after its requirement fingerprint
changes, or while the item is in REVIEW/BLOCK. The checker assumes no new approval is
granted during an algorithm run. It counts an approval as eligible only when the old
asset version and requirement fingerprint both remain exact and the plan has no hold.
No external publication is performed.

This is an implementation-independent, scenario-authored oracle, but it has not been
reviewed by a second human. It checks the five stated workloads; it is not a general
formal proof.

## Scenarios

| Scenario | Change | Predeclared correctness obligations |
| --- | --- | --- |
| `slogan_change` | Confirmed slogan text changes | Copy, captions, storyboard recompute; an unknown SOFT path and its export are reviewed |
| `brand_guideline_change` | Confirmed brand color changes | Explicitly relevant visual assets recompute; unknown layout relevance is reviewed |
| `asset_version_update` | A source photo advances to a new version | Hard-dependent crops recompute; caption path is reviewed; unrelated copy can retain its exact approval |
| `approval_invalidation` | Legal requirement text changes | Compliance copy recomputes; uncertain legal montage path is reviewed; old approvals tied to the global requirement snapshot expire |
| `all_hard_fanout_no_advantage` | Slogan changes and every output is HARD-dependent | Every output recomputes; selective planning has no work to avoid |

All inputs are synthetic, fixed in the source, and generated from the recorded seed.
All evidence/requirements begin confirmed to avoid mixing missing-evidence behavior
into this first pilot. The approval-invalidation case models the current domain's
global requirement fingerprint: changing any requirement invalidates approvals bound
to that requirement snapshot, even for graph-unrelated assets.

## Measurements

The run writes `results.csv` (one row per scenario and method), `node_decisions.csv`
(one row per node decision), `manifest.json`, and three dependency-free SVG plots.
Correctness is a per-case PASS/FAIL against the obligations above. Planning time is
the median of 101 repeated plan-only calls on Python 3.14.6 on the machine that ran
this pilot. It excludes creative generation and human review time. For GAMO-CA it
includes the current planner's graph validation, hashing, decision construction, and
explanation generation; it does not include application or database overhead.

Observed operation counts from this run:

| Scenario | Full recompute ops | DAG incremental ops | GAMO-CA ops | Review ops (Full / DAG / GAMO-CA) |
| --- | ---: | ---: | ---: | ---: |
| Slogan change | 6 | 6 | 3 | 6 / 6 / 6 |
| Brand guideline change | 5 | 4 | 2 | 5 / 5 / 5 |
| Asset version update | 5 | 4 | 2 | 6 / 5 / 5 |
| Approval invalidation | 4 | 3 | 1 | 4 / 4 / 4 |
| All-HARD fanout | 4 | 4 | 4 | 4 / 4 / 4 |
| **Total across these five authored cases** | **24** | **21** | **12** | **25 / 24 / 24** |

All 15 scenario-method combinations passed the predeclared pilot oracle with zero
stale-approval leaks. Across the five scenario medians, planning-time medians were
0.0027 ms (Full Recompute), 0.0078 ms (DAG Incremental), and 3.1627 ms (GAMO-CA).
These very small timing numbers are implementation-specific and sensitive to timer,
interpreter, graph validation, hashing, and output explanation work. In this run the
GAMO-CA planner was slower while scheduling fewer regenerations in several scenarios.
Do not interpret this as statistical significance or a general performance result.

The counts suggest the expected trade-off for these authored examples: typed decisions
can avoid some regeneration, while exact approval invalidation still creates reviewer
work. In the all-HARD case GAMO-CA has no recomputation advantage. These observations
demonstrate that the pilot can exercise the algorithm and baselines; they do not show
that GAMO-CA is generally superior, that its labels match real creative practice, or
that any human review is faster.

## Limitations and next gate

- Five synthetic scenarios are too few and too deliberately constructed for inference,
  statistical significance, or claims about real creative teams.
- The oracle and graph labels were authored by the same project team and lack independent
  expert annotation; a second reviewer should examine them before enlarging the study.
- The operation counters are transparent work proxies. No monetary cost, content
  generation duration, reviewer duration, or token use was measured.
- Full replay and DAG baselines are intentionally simple. The DAG baseline conservatively
  recomputes every non-informational descendant; other fair caching policies may differ.
- Current approval fingerprints cover the whole confirmed requirement set, which can
  create review work for unrelated assets. A narrower binding requires an explicit
  scientific/domain decision and must not be changed just to improve this result.
- Planning time compares tiny Python methods and does not measure application-level
  end-to-end latency. The pure GAMO-CA implementation does more validation/explanation.
- The timing repetitions measure timer stability, not independent scenario samples.

Do not begin a larger benchmark campaign until the scenario graph labels, oracle,
approval-binding assumption, and baseline fairness have been reviewed by a second
human. See `results.csv`, `node_decisions.csv`, and `manifest.json` for the raw outputs.
