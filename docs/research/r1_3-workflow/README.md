# R1.3 — Human review protocol and complete workflow test

Status: deterministic validation with explicitly synthetic review outcomes. No second
human has completed the worksheet, so this is not independent validation. R1.3 is a
small exhaustive check of four binary review outcomes (16 combinations), not a larger
benchmark. R1.1 and R1.2 outputs were not edited.

## Run

From the repository root:

```powershell
.venv/Scripts/python scripts/r1_3_workflow.py --seed 20261014 --timing-repeats 21
.venv/Scripts/python -m pytest -q tests/test_r1_3_workflow.py
```

The script creates a blank review worksheet plus synthetic outcome, workflow, cost,
and run-manifest files in this directory. The worksheet is generated from scenario
requirements, event fields, assets, and typed edges. It does not read saved GAMO-CA
decisions or oracle labels. It has 25 asset rows across five anonymized case codes;
impact and approval labels, rationale, confidence, and notes are blank. Give the
reviewer the worksheet and [`review protocol`](human-review-protocol.md) only; keep
R1.1/R1.2 results hidden until labels are saved. No response is filled or simulated in
the worksheet.

## Synthetic resolution and replanning

The four review roots are `social_export`, `layout_review`, `caption`, and
`legal_montage`; each has one HARD child. The script enumerates all 2^4 combinations.
In these test-only cases, a `MATERIAL_SYNTHETIC` outcome adds the event's changed
fields to that SOFT edge, and `NON_MATERIAL_SYNTHETIC` uses a distinct field. The
updated graph gets a new snapshot hash, the event is bound to that snapshot, and the
existing pure planner is called again. Material roots and HARD children must both
be `RECOMPUTE`; non-material pairs must both be `KEEP`. The worksheet remains
unmodified by this fixture logic.

There are 16 outcome combinations and 64 branch rows. Each complete five-scenario
workflow makes five initial plans. GAMO-CA and the field-aware DAG make four more
plans, one for each changed scenario with a resolved review; that is four replan
rounds and nine planning calls total. The all-HARD scenario has no review branch.
Full Recompute and the original eager DAG need no replan because they already
regenerate their candidate assets.

The observed final **planned** GAMO-CA recomputation counts are:

| Number of branches marked material (assumption) | Outcome combinations | Final recomputations |
| ---: | ---: | ---: |
| 0 | 1 | 12 |
| 1 | 4 | 14 |
| 2 | 6 | 16 |
| 3 | 4 | 18 |
| 4 | 1 | 20 |

Each material branch adds two planned regenerations: the SOFT root and its HARD
child. The baseline counts are 21 for the original eager Conventional DAG and 24
for Full Recompute in every outcome combination. These are operation counts from
plans; no creative asset was actually generated.

## Reviews and approvals are separate work

Every completed GAMO-CA workflow requires four SOFT relevance reviews, represented by
synthetic outcomes in this test. Exact-version approval or renewal work is separately
counted from the set of stale approvals and final
recomputed versions. It is 22 when the `caption` branch is non-material and 24 when
that branch is material. The other three uncertain branches are in requirement-change
scenarios: this prototype binds approvals to the global requirement fingerprint, so
those assets need approval review even if their branch is ultimately non-material.
The projected required review-operation count in this R1.3 two-stage counting is
therefore 26 or 28; none was actually performed.
There are 23 or 24 distinct assets touched by review; a node may receive both an
impact decision and a later approval decision. This differs from R1.1's single
distinct-node counter and is reported separately rather than silently merged.

These are counts, not human minutes. The test does not create approval records or
claim that an approval happened. The second reviewer has not provided any of the
synthetic outcomes.

## The DAG baseline can use the same fields

The original R1.1 Conventional DAG baseline traverses HARD and SOFT edges without
using `relevant_fields`. That is one reasonable conservative policy, but it leaves
information unused. The graph already contains `relevant_fields`, and the event
contains `changed_fields`; an ordinary DAG traversal can inspect their intersection.

R1.3 adds an independently coded **Field-aware DAG** comparison. It uses the same
edge fields and the same synthetic resolutions, follows topological order, and uses
the simple rules: changed HARD input recomputes, disjoint SOFT fields keep, relevant
SOFT fields recompute, unknown SOFT impact reviews, and a HARD child of REVIEW waits.
Across all 16 combinations it produced the same final actions and recomputation
counts as GAMO-CA. This small fixture therefore does not show a unique recomputation
benefit for GAMO-CA over a straightforward field-aware DAG. The baseline assumes
valid, trusted fixtures and omits GAMO-CA's graph validation, provenance, and broader
safety checks; matching these action labels is not proof of equal safety.

## Planning overhead and cost model

Timing repeats each complete plan-only workflow 21 times per outcome set and reports
the median. Across the 16 outcome sets, median workflow planning times were:

| Method | Initial planning median | Replanning median | Total planning median |
| --- | ---: | ---: | ---: |
| GAMO-CA | 31.9357 ms | 25.8518 ms | 58.7511 ms |
| Field-aware DAG | 0.2641 ms | 0.1804 ms | 0.4525 ms |
| Conventional DAG | 0.0917 ms | 0 ms | 0.0917 ms |
| Full Recompute | 0.0278 ms | 0 ms | 0.0278 ms |

Each timing column is summarized separately across the 16 outcome sets; medians of
the initial, replanning, and combined durations need not add exactly because they are
computed from repeated samples.

These are local plan-only timings for tiny graphs. They exclude human review duration,
asset generation, database access, and application overhead. The Field-aware DAG
baseline performs much less graph validation and explanation work; its timing is not
a like-for-like implementation benchmark. The current measured GAMO-CA total is about
130 times the field-aware DAG and 641 times the eager DAG total, on this run. This is
an unfavorable result for the current GAMO-CA code path, not a general claim about
algorithm runtime. The all-HARD scenario still has no recomputation advantage, so the
extra planning and review work makes the simpler policy preferable for that workload.

The updated transparent model is:

```text
C = c_final * final_recomputations
  + c_human * (SOFT_resolution_reviews + exact_version_approval_reviews)
  + c_initial * initial_planning_ms
  + c_replan * replanning_ms
```

The CSV keeps all four measured counts/time components separate. Cost conversion
weights are assumptions: one abstract work unit per planned recomputation; human
review weights of 0.5, 1, or 4 units per review; and initial/replanning rates of
0.01 or 0.1 units per millisecond. The work unit is not money, and no human time,
generation time, or currency was measured. All cost rows are labeled hypothetical.

## What this does and does not show

The test shows, for these five authored synthetic workflows, that review holds are
conditional work: a material outcome triggers the root and HARD child on replan; a
non-material outcome safely keeps that pair. It also shows that ordinary DAG code can
use the same field-level information and match the GAMO-CA actions on these fixtures.
GAMO-CA's computed work ranges from 12 to 20 planned assets, not from 12 to 12 in all
completed workflows. The original eager DAG uses 21 and does no human relevance
review; Full Recompute uses 24.

It does not establish which outcomes a real reviewer would choose, that scenario
labels match creative practice, that the algorithms are equally safe, that review or
generation is cheaper, or that GAMO-CA is scientifically novel. The binary outcome
test also does not cover a human remaining uncertain after review; that state would
need another `REVIEW` or a `BLOCK` and a later decision. The small, authored fixtures
and asymmetric planner implementations remain serious limitations.

**Gate recommendation: do not start a larger benchmark until an actual second human
completes the blinded worksheet and the team records disagreements.** Until then,
keep the results labeled synthetic and do not describe them as independent validation.
