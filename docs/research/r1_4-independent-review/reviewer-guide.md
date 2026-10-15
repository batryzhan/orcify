# Quick guide for the independent reviewer

Thank you for reviewing a small fictional advertising workflow. This is a school
research exercise, not a test of your expertise. There are no right answers hidden in
the file, and the project team will not show you the algorithms' decisions until your
first review is saved.

For each row describing a derived asset, decide what should happen after the listed
change:

- **RECOMPUTE** — the change affects an input the asset depends on, so make a new
  version before using it.
- **REVIEW** — you cannot tell from the listed information; pause and inspect it.
- **KEEP** — the existing version is still suitable for this change.

Then answer a different question about approval. Choose **REAPPROVE** if this version
needs a new approval, **UNCHANGED** if its approval still applies, or **UNCERTAIN** if
the worksheet does not provide enough information. An asset can be safe to KEEP while
still needing approval. KEEP is not approval.

Use the “typed inputs” column to follow the links. HARD means a changed input normally
requires a new asset. SOFT means the effect may depend on which field changed.
INFORMATIONAL means the link records context. Base your answer on the details shown;
do not add a dependency that is not listed. For example, if a changed slogan reaches
an asset through a HARD text link, RECOMPUTE may fit. If only the palette changed and
the listed SOFT link concerns text, KEEP may fit if you are confident the asset is
unaffected. If the link or evidence is unclear, use REVIEW or UNCERTAIN rather than
guessing.

Write one short reason naming the changed field and the path you followed. Set
confidence from 1 (not confident) to 5 (very confident). Work alone; do not compare
answers with the other reviewer or search for previous algorithm results. Save a
separate copy of the CSV and return it through the method agreed with your supervisor.
Do not edit your first answers after seeing another review or algorithm output. Any
later discussion should be recorded as a new annotation, preserving your original.

All cases and assets are synthetic. Your labels are useful feedback on these examples,
not a claim about every real creative workflow.
