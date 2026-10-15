# R1.4 — Independent human validation

## Purpose and status

This phase prepares a small comparison against real independent labels. It does not
create reviewer responses. As of this document's creation, the R1.3 worksheet is
blank and there are no human-validation results. The existing R1.1, R1.2, and R1.3
artifacts remain the original reproducibility record.

## Reviewer guide

Give each of two reviewers the same blank worksheet and the short guide
[`reviewer-guide.md`](reviewer-guide.md), separately. Do not show them algorithm
names, prior decisions, the R1.1 oracle, or each other's labels. Each person should
make their own copy named with a neutral reviewer code and complete all 24 derived
asset rows. Do not fill the changed source row as an impact decision.

For every derived asset, choose exactly one impact label:

- `RECOMPUTE`: this change makes the current asset version unsuitable; regenerate it
  before use.
- `REVIEW`: the listed evidence cannot settle whether the asset is affected; hold it
  until a human inspects it.
- `KEEP`: the current asset remains valid for this change based on the listed fields
  and typed inputs.

Separately choose approval status `REAPPROVE`, `UNCHANGED`, or `UNCERTAIN`. Impact
`KEEP` never implies approval. Give a short reason that points to the changed field
and dependency path, and a confidence from 1 to 5. Do not infer missing edges. Save
the completed files as immutable copies; retain each original file hash and received
date. Discuss neither labels nor algorithm outputs until both first-pass files are
frozen.

## Import and analysis

Run only after two real, independent reviewers have completed separate copies:

```powershell
.venv/Scripts/python scripts/import_r1_4_reviews.py `
  --reviewer-1 path/to/reviewer-a.csv `
  --reviewer-2 path/to/reviewer-b.csv `
  --reviewer-1-code R-A `
  --reviewer-2-code R-B `
  --output-dir docs/research/r1_4-independent-review/import-2026-XX-XX
```

The output directory must be new. The importer verifies exact row coverage, unique
asset keys, allowed impact/approval values, reason text, and confidence. It writes
source SHA-256 hashes, a JSON report, and `disagreements.csv`; it never edits its
inputs or prior result directories. If the files are blank/incomplete, duplicated,
or malformed, it stops without producing a scored report.

Reviewer codes must differ, but the importer cannot verify that different people
completed the files. The student and supervisor must arrange independent completion
and retain any receipt or consent record separately.

Metrics are calculated separately against reviewer 1, reviewer 2, and the rows on
which both reviewers agree. Contested rows are listed as unresolved and excluded from
the agreement-only score. The importer does not pick a consensus, overwrite either
label, or adjudicate. Preserve disagreement and ask a supervisor and reviewers to
resolve it only as a new, separately recorded annotation if needed. Do not begin a
larger benchmark while disagreement remains material to the comparison.

Reported impact metrics are exact action agreement, recomputations on reviewer-`KEEP`
rows (the definition of unnecessary), recomputations on reviewer-`REVIEW` rows
(reported separately because necessity is unresolved), and missed required
recomputations (reviewer says `RECOMPUTE`, algorithm does not). Approval-safety violations are a separate count:
the shared R1.1 correctness-oracle eligibility output marked true while the reviewer
marks approval `REAPPROVE` or `UNCERTAIN`. This checks the saved oracle output; it
does not mean a publication was attempted. The field-aware DAG intentionally has no approval system,
so its approval-safety rows are reported as unassessed rather than assumed safe.
`REVIEW` is not automatically counted as a missed recomputation: it is a distinct
hold label, and exact-action accuracy shows the difference. The counts remain
descriptive for five authored synthetic workflows.

## Three separate questions

**Algorithmic novelty:** these results do not establish that GAMO-CA is novel. The
R1.3 field-aware DAG matched its final actions and recomputation counts over the 16
synthetic review outcomes. R1.4 can show agreement with independent labels on these
cases only; it cannot establish novelty.

**System engineering:** PostgreSQL persistence, immutable approvals, provenance,
replay, and recovery are engineering properties of the larger demonstration. Their
presence is not evidence of algorithmic superiority. A fair future comparison should
give a simpler DAG the same exact-version approval, provenance, and recovery
safeguards, then test whether the additional GAMO-CA decisions change measured
outcomes. The current five cases do not isolate such a benefit.

**Practical usefulness:** explicit review holds and exact-version approval can make
the workflow easier to inspect and safer to operate, but this study has no usability
measure, reviewer-time measure, production data, or publication attempt. It cannot
show that the full system is practically better or universally safe.

## Stop rule and current recommendation

No reviewer response has been collected in this repository. Therefore the import
script has not been run on human data, no accuracy values are available, and R1.4
independent validation is incomplete. Do not start a larger benchmark until both
worksheets are received, completeness is verified, disagreements are inspected, and
the student/supervisor accepts the annotation protocol. No statistical significance
or universal safety claim is appropriate for five authored cases.

The source worksheets and all R1.1–R1.3 output files are preserved. Engineering tests
for the importer use temporary synthetic fixtures only; they are not reviewer data.
