# Source alignment (2026-10-14)

Primary source: `Orcify_2_0_Research_Concept_2026.pdf`, 13 pages. Page numbers
below are the printed PDF pages. Read all pages and visually inspected the page
layout/figures. The original root copy is retained; the reference copy under
`docs/research/` is byte-identical. This is a proposal, not empirical evidence.

## Requirements and implementation map

| Pages / section | Source requirement | Implementation destination / gate |
| --- | --- | --- |
| 1–2, abstracts | Method proposed; novelty and utility unproven | README status; experiment log; no fabricated results |
| 3, §1 | Creative brief → content → revision → approval; text and storyboard metadata first | Domain kernel (Phase 1); API (2); mock execution (3) |
| 3–4, §1.4–2 | Compare incremental computation, graph retrieval, workflow and provenance prior art; examine overhead and boundary conditions | related-work.md; benchmark B0–B3 (5); scaling (6) |
| 4–5, §3 | H1 cost, H2 safety, H3 explanation time, H4 graph size/change-depth boundary | Paired experiments; separate human study; no claimed findings |
| 5, §4.1 | Typed, versioned graph; tenant/project; source/status/validity interval | Immutable scoped snapshots; active-time traversal; schema v1 |
| 5, §4.1 | Signature includes input content hashes and versions, model/tool and policy | Canonical input fingerprint; provider/prompt/policy identity |
| 5, §4.2 | HARD, SOFT, DERIVED_FROM, APPROVES_VERSION, SUPERSEDES, BELONGS_TO | ADR-004 separates dependency strength from relationship kind |
| 6, §4.3 | Event includes old/new version, actor, time, source, changed fields | ChangeEvent; snapshot preconditions; stable event IDs |
| 6, §4.3–4 | REUSE/RECOMPUTE/REVIEW/BLOCK, safe feasible plans before cost; no global optimum claim | KEEP is wire alias for REUSE; policy and plan trace; no optimizer claimed |
| 6, §4.5 | Six PDF invariants | Explicit crosswalk below; Gate A tests |
| 7, §5.1 | Confirm source, diff versions, impact traversal, invalidate, signature/validity checks, ordered execution, validate output, immutable history | Kernel (1), authenticated confirmation / transactions (2), executor (3) |
| 7, §5.2–3 | Account for graph maintenance/provenance; traversal and ordering assumptions | algorithm.md; Phase 5–6 measurements include overhead |
| 8, §5.4 | HARD price restriction invalidates copy/subtitles, uncertain color impact requires review, unrelated logo retained; export blocked | Synthetic toy fixtures and later reviewer demo |
| 8, §6 | React/TS/shadcn/React Flow; FastAPI/Pydantic; Neo4j (NetworkX allowed initially); PostgreSQL; provider-neutral mock/local/API; workers deferred | ADRs 001–003; modules reserved, no UI first |
| 8, §6.2 | Upload/extract/confirm brief; draft assets with dependencies; explain change decisions | Gates B/C, no unconfirmed extraction treated as requirement |
| 8, §6.3 | Untrusted brief data; forged approval, cross-tenant, stale source, replay, timeout tests; private data permission | Security/adversarial tests across Phases 1–3,6 |
| 9, §7.1 | PLANNED pilot 5×4=20; main 24×6=144; 6–12 tasks, 3–6 requirements, 2–4 versions, ≥1 approval; 3 complexity levels; language labels | Versioned dataset schema/rubric (5); not collected yet |
| 9, §7.1 | Two independent human annotators, adjudication; authorized anonymous real scenario optional | Human annotation gate; no automatic gold approval |
| 9, §7.2 | B0 full replay; B1 DAG/content hash; B2 versioned graph+DAG without approval/risk policy; B3 GAMO-CA | Baselines (5); ADR-004 preserves source definition |
| 9, §7.2 | Keyword/vector/graph retrieval is separate sub-study | Do not combine retrieval and replan effectiveness metrics |
| 9–10, §7.3 | HARD recall, recompute precision, safety violations, reuse, full cost, latency, explanation accuracy, review load | Raw event observations; CPU/indexing/human minutes included |
| 10, §7.4 | Fixed seed/model/temperature; identical initial snapshots; randomized condition order; ≥3 runs/condition; median/IQR/mean/CI | Reproducibility manifest; paired campaign-level 95% bootstrap |
| 10, §7.5 | Ablate temporal versions, approval gate, SOFT-review, provenance trace | All four source ablations retained; no-typed-edge backlog ablation additional |
| 10, §7.6 | HARD detection, complete logs, prevent unauthorized publication; negative performance findings acceptable | Safety hard gates; no invented percent improvement target |
| 11, §8 | 12-week proposal schedule; risk/ethics: synthetic validity, inferred edge errors, graph costs, unfair baselines, time, prior art | TASK order is engineering schedule; limitations.md; consent before real data |
| 11–12, §9 | Testable contribution only after implementation/fair benchmark | No novelty or superiority claim |
| 12, references | Verify prior-art bibliography; unavailable user original/competition attachments | related-work.md; unverified items clearly marked |
| 12–13, Appendix A | Source authorization/verification, active-time closure, signature/approval-safe reuse, topo order, budget, output validation, immutable log | Pure planning first; side effects and authorization in later application layer |
| 13, Appendix B/C | CSV campaign/event/method/seed/gold/predicted/safety/cost/latency/review; readiness checklist | Phase 5 schema and actual execution manifests; blanks until measured |

## Invariant crosswalk (both sets retained)

| PDF invariant (p.6) | README invariant | Required evidence |
| --- | --- | --- |
| I1 tenant/project isolation | 1 no cross-tenant retrieval/execution | Scope validation, authenticated server filtering, malicious edges |
| I2 exact-version approval | 2 exact asset + requirement snapshot; 4 no inheritance | Revision, forged decision, revoke, mismatch tests |
| I3 current HARD requirements | 3 no stale HARD reuse | Transitive invalidation; active-time/stale-input tests |
| I4 evidence trace | 5 derived output provenance | Version/source/provider/reason trace, missing provenance rejection |
| I5 unknown → review | Additional source invariant | SOFT uncertainty cannot silently KEEP; downstream hold |
| I6 human gate | 2 publication approval; explicit human final handoff | No model approval/publication capability; authorization tests |
| Additional README rule | 6 idempotent replay/retries | Duplicate IDs, stale snapshot, race and external-side-effect tests |

## Resolved interpretations and open questions

Resolved in ADRs: KEEP means computational retention, never publication approval;
EVIDENCE/APPROVAL are relationship roles, not dependency strengths; unknown SOFT
requires REVIEW and conservatively holds HARD descendants; PostgreSQL owns truth.
Source B2 means versioned graph+DAG, not retrieval-only. Rnorm in the PDF is
residual rework/review risk; README calls it normalized recomputation. No objective
optimization is implemented in this milestone; metrics will be reported separately.

Open: verified change-field taxonomy and SOFT relevance annotation rubric;
requirement snapshot relevance scope; future-dated/superseding temporal conflict
resolution; budgets/cost tables; annotation personnel and consent; human explanation
study protocol; prior-art completeness. Dependencies default conservatively until
human-confirmed. Temporal graph snapshots initially represent current versions at
an explicit instant; historical queries/projection recovery are Phase 2 work.

The PDF's abstract says four baselines; §7.2 defines three baselines plus treatment.
Use explicit B0–B3 names. Its schedule differs from TASK.md: follow TASK execution
order, retaining all scientific requirements. Original 22-page concept and contest
attachments listed on p.12 are absent and cannot be claimed reviewed.
