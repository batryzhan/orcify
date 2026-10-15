# Methodology, evidence, and limits

This final presentation reuses R1.1–R1.4. It performs no new experiment and collects
no reviewer response. Preserved source-file hashes are recorded in
`research-artifact-lock.json`; `scripts/export_presentation.py --check` checks them.

| Artifact | What it contains | How the dashboard uses it |
| --- | --- | --- |
| R1.1 `results.csv` | 15 rows, three methods × five cases | Recompute/review totals and per-case planner medians |
| R1.1 `node_decisions.csv` | Per-node decisions and reasons | Checks the exported demo against the current pure planner |
| R1.2 `cost-sensitivity.csv` | Selected cost assumptions and model totals | Dropdowns select original saved rows; no cost is measured in the browser |
| R1.3 `synthetic-workflow-results.csv` | 64 rows, four methods × 16 outcomes | Four binary toggles select saved recompute, review, replan, and timing values |
| R1.4 guide and importer | Preparation for actual independent labeling | Validation remains pending; no human scores displayed |

R1.1's oracle obligations were defined independently of the planner implementation,
but authored by the same project team. They are not independently validated gold
labels. All algorithms receive the same graph and change events. Conventional DAG
conservatively recomputes reachable HARD and SOFT descendants; Field-aware DAG also
uses the existing field metadata. Thus the latter is a stronger information-matched
comparison for impact decisions. It still omits broader graph and safety validation.

Operation counts are planned actions, not completed generations. R1.1 review proxies
count distinct assets needing review/approval work. R1.3 counts SOFT resolution and
exact-version approval operations separately; one asset may need both. Do not compare
those review counts as if they had identical definitions. No human review happened.

In R1.3, each of four uncertain roots has a HARD child. Synthetic material resolution
makes both recompute; non-material resolution lets both remain KEEP. Initial workflow
planning makes five calls; the four resolved cases add four replanning rounds. The
all-HARD fifth case needs no review resolution. A reviewer remaining uncertain is not
represented by this binary model and would still need a hold.

R1.1 timing values are medians of repeated calls on the same tiny cases. When all
cases are selected, the dashboard reports the median of five case medians. R1.2 uses
the sum of those case medians in its cost model. R1.3 saves medians of complete
workflow initial/replan/total call durations. These summaries answer different
questions and should not be silently merged. Repetitions are not independent workload
samples. Timing excludes generation, human effort, and external I/O. The algorithms
perform different amounts of validation, so runtime is not a fair complexity test.

The final source-data check found a historical prose discrepancy: R1.1's README
states aggregate medians of 0.0027 / 0.0078 / 3.1627 ms, whereas the actual preserved
CSV rows give 0.0019 / 0.0059 / 2.9535 ms (Full / Conventional DAG / GAMO-CA).
The dashboard calculates the latter from CSV. The R1.2 cost rows use the correct
CSV sums, 0.0107 / 0.0352 / 13.4922 ms, so their model is not recomputed or changed.
Original prose, CSVs, figures, and hashes remain preserved; this note records the
discrepancy instead of silently rewriting the historical record. No new timing trial
was run for the final presentation.

The R1.2 model is `C = c_compute R + c_review H + c_plan T`, with GAMO's conditional
recomputations modeled as `12 + 8q`. The weights and q are assumptions, not money or
observed probabilities. R1.3 separates initial planning from replanning. A cost model
cannot establish real savings without measured generation and human-work costs.

Limitations include five authored synthetic scenarios, one seed, no independent
human labels, uncertain edge semantics, global requirement-fingerprint invalidation,
unequal implementation work, and no real provider execution. Finite engineering
tests are not a proof of universal safety. No significance or novelty claim is made.

The next scientific step is receiving and inspecting real blinded reviewer worksheets,
including unresolved disagreements. A later comparison should give a simple DAG the
same exact-version approval, provenance, and recovery safeguards before attributing
a benefit to GAMO-CA. That work is outside this final presentation build.
