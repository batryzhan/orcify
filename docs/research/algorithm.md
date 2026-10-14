# Kernel v1: deterministic conservative preview

Status: implemented preview; approval state machine, event application and executor
are subsequent Phase 1–3 tasks. This is not a validated performance result.

`plan_change(graph, event, policy)` consumes immutable explicit inputs, reads no
clock or random source and performs no network/database calls. Graph scope is
structural isolation, not authenticated authorization. The application must load
the scope from verified identity and authorize the human actor before planning.

1. Reject cross-scope event, stale snapshot hash, mismatched event/as-of time,
   missing/unconfirmed evidence, old version/hash mismatch or unconfirmed target.
2. Verify existing consumed HARD inputs against active upstream version/content
   hashes; missing/stale inputs require recomputation. Stale SOFT inputs require
   review. Unconfirmed mandatory requirements/evidence block derived outputs.
3. Walk the whole active dependency DAG in stable topological order. A changed
   target or previously stale node is an impact source.
4. HARD change propagates RECOMPUTE; HARD downstream of REVIEW retains a review
   hold; blocked dependencies propagate BLOCK. SOFT unknown fields require REVIEW;
   explicit relevant target fields recompute and disjoint fields retain. Fields of
   changed derived nodes are unknown, so their SOFT dependents require review.
   INFORMATIONAL edges retain with a machine-readable trace.
5. Combine incoming decisions with BLOCK > REVIEW > RECOMPUTE > KEEP. A node that
   needs recomputation but also depends on unresolved review must wait. Reasons
   preserve the mandatory recomputation cause even when execution is deferred.
6. Emit ordered affected-node rebuild candidates, per-node consumed-input signature,
   evidence references and edge reasons, non-publishable affected asset IDs,
   optional simulated serial cost/latency sum, snapshot hash and plan hash.

KEEP corresponds to PDF REUSE and means computational retention only. The preview
does not mutate current versions/approval history; it must be applied atomically
by a later service. `non_publishable_ids` identifies change-induced holds, not the
complete set of assets lacking approval. No publication capability exists yet.
Rebuild candidates may be tasks or derived asset nodes; the executor must resolve
each asset to its producing task before executing. This contract is provisional
until the executor schema is finalized; previews do not generate asset versions.

```mermaid
flowchart LR
    Event --> Scope[Scope / source / snapshot checks]
    Scope --> Stale[Consumed-version checks]
    Stale --> Traverse[Typed topological propagation]
    Traverse --> Hold[Merge safety holds]
    Hold --> Plan[Plan + edge traces + hashes]
```

## Complexity and limitations

The implementation validates and visits the full graph, not only an affected
subgraph. Heap ordering costs O(V log V + E), with sorting edges/reasons and hashing
serialized snapshot bytes adding O(E log E + payload size) work. It keeps O(V+E)
state plus the serialized content. Node lookup used outside the core is linear;
the planner builds a map. These are code-level bounds, not measured timings.

No global optimization or unchanged-output pruning is implemented. All changed
HARD paths invalidate conservatively even when content is equal across versions.
Wrong but human-confirmed edge labels can still produce wrong impact; independently
reviewed gold data remains necessary. Full historical queries, time-scheduled changes,
authentication, approval/revoke race safety, replay deduplication, provider failures
and publication eligibility remain open gates. The supplied graph represents
current versions at exactly the event timestamp; future/backdated events reject.
