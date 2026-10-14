# ADR-004: Strength, relationship kind and active-time impact

Status: accepted for schema v1; 2026-10-14.

Edges are oriented upstream → dependent in the in-memory planner (Cypher
DEPENDS_ON may reverse this in the adapter). Strength is HARD, SOFT or
INFORMATIONAL, distinct from DERIVED_FROM/EVIDENCE/APPROVAL/SUPERSEDES/ownership
relationships. Approval and provenance records are not informational substitutes
for mandatory consumed inputs. Active edges use `[valid_from, valid_to)`.

HARD propagates recomputation. SOFT with no explicit, human-confirmed field
relevance is REVIEW. Explicit matching fields recompute; disjoint fields KEEP with
trace. An uncertain upstream result puts its HARD descendants on REVIEW too;
retaining an old downstream result as safe would conceal uncertainty.
INFORMATIONAL retains and records the edge reason; missing consumed HARD
fingerprints recompute even for unrelated events. No signature bypass of a
changed HARD version in this milestone. Unconfirmed sources fail closed.

Only current versions appear in a graph snapshot. Historical version records and
provenance remain immutable; full as-of retrieval is a later persistence feature.
No learned relevance model, global cost optimization or output-sensitive pruning
is claimed. Edge metadata and human confirmation of relevance are open protocol
work. Source B2 (p.9) is versioned graph + DAG without approval/risk classification;
README's retrieval-only name is insufficient: implement the source definition.

Alternative: all downstream edges invalidated equally. Kept as baseline/ablation,
not as treatment. Complexity includes full graph validation and stable ordering.
