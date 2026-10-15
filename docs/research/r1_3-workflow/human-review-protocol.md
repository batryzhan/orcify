# R1.3 independent human review protocol

## Purpose and status

This protocol asks a second human to independently annotate the five existing
synthetic workflows. No reviewer has completed it as of 2026-10-15. Provide the
reviewer this protocol and the blank [`review-worksheet.csv`](review-worksheet.csv).
Neither file contains GAMO-CA, baseline, oracle, or earlier planner decisions. Do not
give the reviewer R1.1/R1.2 result files or the R1.3 analysis report until their
labels are submitted and frozen. The supplied data is synthetic; the review is not a
real agency or customer study.

## Reviewer instructions

For each `case_code` and asset row, read the original confirmed requirements, the
change summary and changed fields, and the typed input links. Label the changed source
row `SOURCE_CHANGE`. For each derived asset choose exactly one:

- `RECOMPUTE`: the changed input makes the current derived version invalid and a new
  version should be produced before use.
- `REVIEW`: the available information is not enough to decide safely; a person should
  inspect the asset or its evidence before the workflow proceeds.
- `KEEP`: the current derived version remains valid for this change based on the
  listed fields and links.

Then label approval separately as `REAPPROVE`, `UNCHANGED`, or `UNCERTAIN`. A `KEEP`
impact label does not assert that an approval is current. If approval status cannot
be judged from the worksheet, select `UNCERTAIN` and explain what information is
missing. Use the reason field to cite the changed field and dependency path. Use the
confidence field from 1 (low) to 5 (high). Do not infer an unlisted dependency.

Review each row independently before discussing any disagreement. Leave the provided
case codes unchanged. Record a reviewer code rather than a full name in the shared
worksheet; the project supervisor may keep identity and consent records separately.
Return the completed copy to the project team through their approved local method.
The project team must preserve the original blank worksheet and submitted copy
separately and record its SHA-256 hash and receipt date. Do not edit prior labels after
seeing algorithm output; log any adjudication as a new annotation with the reviewer
and reason recorded.

## Analysis after submission

Only after the second reviewer returns the worksheet should the student unblind the
R1.1/R1.2 outputs. Compare reviewer labels with the original hand-authored obligations
and GAMO-CA, report every disagreement, and ask the reviewer to adjudicate only after
their first labels are saved. Do not replace labels silently or select a policy because
it improves recomputation counts. If the reviewer disagrees with a typed edge, record
the proposed change and rerun the same small workflow checks as a separately versioned
dataset. Do not scale to a larger benchmark until the supervisor agrees that the
scenario labels and comparison rules are usable.

## Boundaries

The 16 combinations in `synthetic-workflow-results.csv` are deterministic test
fixtures for both possible synthetic answers on each of four uncertain branches. They
are not reviewer responses, probability estimates, or substitutes for this protocol.
No human time is measured by the current worksheet or script. The worksheet must
remain blank until an actual reviewer completes it.
