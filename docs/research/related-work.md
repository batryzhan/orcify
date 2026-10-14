# Related work: initial verified review

Reviewed 2026-10-14. This is a focused initial review, not proof of novelty or an
exhaustive survey. No source's reported gains are Orcify measurements.

| Primary source | Existing capability | Orcify hypothesis / limit of comparison |
| --- | --- | --- |
| [Acar, Self-Adjusting Computation (2005)](https://www.cs.cmu.edu/~rwh/students/acar.pdf), [experimental analysis (2009)](https://www.cs.cmu.edu/afs/cs.cmu.edu/Web/People/guyb/papers/ABBHT09.pdf) | Dynamic dependence tracking and change propagation recompute affected work | Incremental recomputation is established; study creative temporal constraints and approval decisions |
| [Bazel remote caching](https://bazel.build/remote/caching) | Explicit action inputs, content hashes, action-result cache; non-hermetic inputs/concurrent changes threaten correctness | B1 must have fair complete fingerprints, rather than an intentionally weak cache |
| [Edge et al., GraphRAG (2024, rev.2025)](https://arxiv.org/abs/2404.16130) | Entity graphs and community summaries for corpus-level question answering | Retrieval quality does not establish safe selective replanning; retrieval study remains separate |
| [Fan et al., WorkflowLLM](https://arxiv.org/abs/2411.05451) | LLM workflow orchestration capability | Generating a workflow is distinct from approval-safe revision of existing versions |
| [W3C PROV-O (2013)](https://www.w3.org/TR/prov-o/) | Entity/activity/agent provenance, derivation and attribution | Provenance itself is established; test how traced versions constrain reuse |
| [Temporal workflows](https://docs.temporal.io/workflows) | Durable event history and deterministic replay; recorded activities reused | Event sourcing/replay are established; small synchronous kernel initially avoids runtime overhead |

## Source bibliography needing further verification

The source PDF also lists [Cała & Missier](https://doi.org/10.1016/j.bdr.2018.06.001),
[Musubito](https://www.sciencedirect.com/science/article/pii/S0167642326001371), and
[graph-aware scheduling](https://doi.org/10.3390/fi18050265). Direct publisher/DOI
pages failed in the research browser on this date. Their details and specific claims
remain unverified here; no argument for novelty relies on them. The
[SodaMem abstract](https://arxiv.org/abs/2608.08055) was reachable; full methodological
comparison is still open. LangGraph overlap also needs a deeper review before
any contribution claim. The initial review is sufficient to recognize prior art,
not to certify a publication-ready novelty claim.

Contribution remains a falsifiable hypothesis: under equal inputs/provider/prompt
and safety constraints, does combining version validity, typed impact, human
approval and trace improve some creative revision workloads enough to cover
its maintenance and review costs? Negative findings must be reported.
