# Ten likely jury questions

1. **What is your scientific problem?** Determining which connected creative assets
   require recomputation after a change, while representing uncertainty and keeping
   exact-version human approval separate from reuse.
2. **What is new?** Novelty is unproven. Typed graphs, incremental computation, and
   versioned approvals have prior work. Our proposal studies their joint behavior in
   a small creative-workflow setting; the current evidence does not establish an
   original algorithmic contribution.
3. **How is this different from an ordinary DAG?** The current GAMO-CA implementation
   adds explicit review holds, graph checks, version checks, and decision traces. A
   field-aware DAG can make the same impact decisions in our cases. Equivalent
   safeguards must be compared before attributing a benefit to GAMO-CA.
4. **Why did you report 12 versus 21?** Those were initial plans over five cases.
   Eight operations were held behind unresolved review. Depending on four synthetic
   resolutions, the final GAMO count becomes 12–20. We explicitly show the deferral.
5. **Who decided the correct answers?** The team authored the original oracle before
   running the algorithms. It is implementation-independent in a limited sense but
   not independently annotated. A real second review has not been completed. The
   worksheet is blinded and the importer preserves disagreement.
6. **Why is the planner slower?** Our GAMO-CA code validates and hashes the graph and
   constructs explanations. The baseline functions do less work. These tiny timings
   show current implementation overhead, not fair algorithmic complexity or end-to-end
   production latency.
7. **Does KEEP mean approved?** No. Approval binds an exact asset version, requirement
   snapshot, policy, and verified human actor. A changed version never automatically
   inherits approval. An unresolved review blocks eligibility.
8. **Did you measure money, tokens, or human effort?** No. We measured operation counts
   and planner wall time. The cost model uses explicitly hypothetical work units.
   No paid AI provider or real content generation was involved.
9. **What happens when the dependency labels are wrong?** The planner can produce a
   wrong impact plan even with correct code. Provenance helps inspect an assumption
   but does not make it true. Independent edge/field review and adversarial cases are
   necessary; these finite tests cannot establish universal safety.
10. **What is the defensible conclusion?** The prototype demonstrates transparent
    change planning and explicit safety constraints. The current synthetic pilot
    does not demonstrate superiority over field-aware DAG or scientific novelty.
    The honest next step is real independent annotation and equal-safeguard comparisons,
    not a claim based on a larger feature count.
