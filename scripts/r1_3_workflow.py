"""Run a small synthetic review-resolution and replanning workflow study.

This script evaluates all 16 combinations of four explicitly synthetic SOFT-review
outcomes. It generates a blank, decision-blinded reviewer worksheet and never records
or claims real human responses. The original R1.1/R1.2 artifacts are read-only.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import platform
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from gamo_ca.graph import Graph  # noqa: E402
from gamo_ca.models import (  # noqa: E402
    Action,
    AssetVersion,
    ChangeEvent,
    DependencyEdge,
    DependencyType,
    Requirement,
)
from gamo_ca.planner import Plan, Policy, plan_change  # noqa: E402
from r1_1_pilot import Scenario, dag_incremental, full_recompute, make_scenarios  # noqa: E402

OUTPUT_DIR = ROOT / "docs" / "research" / "r1_3-workflow"
POLICY = Policy(version="pilot-policy-v1")
TIMING_REPEATS = 21
BRANCHES = (
    ("slogan_change", "edge-req_slogan-social_export", "social_export", "S01"),
    ("brand_guideline_change", "edge-req_palette-layout_review", "layout_review", "S02"),
    ("asset_version_update", "edge-source_photo-caption", "caption", "S03"),
    ("approval_invalidation", "edge-req_legal-legal_montage", "legal_montage", "S04"),
)
CASE_CODES = {
    "slogan_change": "S01",
    "brand_guideline_change": "S02",
    "asset_version_update": "S03",
    "approval_invalidation": "S04",
    "all_hard_fanout_no_advantage": "S05",
}
CHANGE_SUMMARIES = {
    "slogan_change": "A confirmed slogan requirement changes.",
    "brand_guideline_change": "The confirmed brand color guidance changes.",
    "asset_version_update": "The source photo advances to a new version.",
    "approval_invalidation": "The confirmed legal disclaimer requirement changes.",
    "all_hard_fanout_no_advantage": "The confirmed slogan changes in an all-HARD workflow.",
}
NEW_CONTENT = {
    "brand_guideline_change": "cobalt and ivory",
    "asset_version_update": "Synthetic replacement photo v2",
    "approval_invalidation": "Include the updated local disclaimer",
}


def action_map(plan: Plan) -> dict[str, Action]:
    return {decision.node_id: decision.action for decision in plan.decisions}


def gamo_plan(
    scenario: Scenario,
    graph: Graph | None = None,
    event: ChangeEvent | None = None,
) -> Plan:
    return plan_change(graph or scenario.graph, event or scenario.event, POLICY)


def field_aware_dag_plan(
    scenario: Scenario,
    graph: Graph | None = None,
    event: ChangeEvent | None = None,
) -> dict[str, Action]:
    """Independent DAG baseline that uses the same changed-field metadata as GAMO-CA."""
    graph = graph or scenario.graph
    event = event or scenario.event
    outgoing: dict[str, list[DependencyEdge]] = {node.id: [] for node in graph.nodes}
    state = {node.id: Action.KEEP for node in graph.nodes}
    priority = {Action.KEEP: 0, Action.RECOMPUTE: 1, Action.REVIEW: 2, Action.BLOCK: 3}

    def mark(node_id: str, action: Action) -> None:
        if priority[action] > priority[state[node_id]]:
            state[node_id] = action

    for edge in graph.active_edges:
        outgoing[edge.upstream_id].append(edge)
    for node_id in graph.topological_order():
        upstream_action = state[node_id]
        impacted = node_id == event.target_id or upstream_action != Action.KEEP
        for edge in outgoing[node_id]:
            action = Action.KEEP
            if impacted:
                if edge.strength == DependencyType.INFORMATIONAL:
                    action = Action.KEEP
                elif upstream_action == Action.BLOCK:
                    action = Action.BLOCK
                elif edge.strength == DependencyType.HARD:
                    action = Action.REVIEW if upstream_action == Action.REVIEW else Action.RECOMPUTE
                elif upstream_action == Action.REVIEW or not edge.relevant_fields:
                    action = Action.REVIEW
                elif node_id != event.target_id:
                    action = Action.REVIEW
                elif set(edge.relevant_fields).intersection(event.changed_fields):
                    action = Action.RECOMPUTE
            mark(edge.dependent_id, action)
    return state


def resolved_case(scenario: Scenario, edge_id: str, material: bool) -> tuple[Graph, ChangeEvent]:
    """Encode one synthetic review result as explicit relevant-field metadata."""
    changed_fields = scenario.event.changed_fields
    if material:
        relevant_fields = changed_fields
    else:
        # A non-overlapping synthetic field records the hypothetical no-impact result.
        relevant_fields = ("reviewed_non_overlapping_field",)
    new_edges = tuple(
        replace(edge, relevant_fields=relevant_fields) if edge.id == edge_id else edge
        for edge in scenario.graph.edges
    )
    if all(edge.id != edge_id for edge in scenario.graph.edges):
        raise ValueError(f"review edge not found: {edge_id}")
    graph = replace(scenario.graph, edges=new_edges)
    event = replace(scenario.event, expected_snapshot_hash=graph.snapshot_hash)
    return graph, event


def _asset_recomputes(scenario: Scenario, actions: dict[str, Action]) -> set[str]:
    asset_ids = {node.id for node in scenario.graph.nodes if isinstance(node, AssetVersion)}
    return {node_id for node_id in asset_ids if actions.get(node_id) == Action.RECOMPUTE}


def final_actions(
    scenarios: tuple[Scenario, ...], outcomes: tuple[bool, ...], *, aware: bool
) -> tuple[dict[str, dict[str, Action]], dict[str, dict[str, Action]]]:
    initial: dict[str, dict[str, Action]] = {}
    final: dict[str, dict[str, Action]] = {}
    for scenario in scenarios:
        if aware:
            actions = field_aware_dag_plan(scenario)
        else:
            actions = action_map(gamo_plan(scenario))
        initial[scenario.name] = actions
        final[scenario.name] = dict(actions)
    for (scenario_name, edge_id, root_id, _), material in zip(BRANCHES, outcomes, strict=True):
        scenario = next(item for item in scenarios if item.name == scenario_name)
        graph, event = resolved_case(scenario, edge_id, material)
        if aware:
            revised = field_aware_dag_plan(scenario, graph, event)
        else:
            revised = action_map(gamo_plan(scenario, graph, event))
        hard_children = [
            edge.dependent_id
            for edge in graph.active_edges
            if edge.upstream_id == root_id and edge.strength == DependencyType.HARD
        ]
        if len(hard_children) != 1:
            raise AssertionError(f"expected one HARD child for review branch {root_id}")
        expected = Action.RECOMPUTE if material else Action.KEEP
        if revised[root_id] != expected or revised[hard_children[0]] != expected:
            raise AssertionError(f"synthetic review resolution did not propagate for {root_id}")
        final[scenario_name].update(revised)
    return initial, final


def human_review_counts(
    scenarios: tuple[Scenario, ...], final: dict[str, dict[str, Action]]
) -> tuple[int, int, int]:
    """Return projected review requirements, not human actions already performed."""
    relevance_reviews = len(BRANCHES)
    approval_reviews = 0
    distinct_reviewed_assets = 0
    roots = {scenario_name: root for scenario_name, _, root, _ in BRANCHES}
    for scenario in scenarios:
        recomputed = _asset_recomputes(scenario, final[scenario.name])
        approval_reviews += len(set(scenario.oracle.approvals_invalidated_by_event) | recomputed)
        review_holds = {
            node_id
            for node_id, action in final[scenario.name].items()
            if action in (Action.REVIEW, Action.BLOCK)
        }
        resolved_root = {roots[scenario.name]} if scenario.name in roots else set()
        distinct_reviewed_assets += len(
            set(scenario.oracle.approvals_invalidated_by_event)
            | recomputed
            | review_holds
            | resolved_root
        )
    return relevance_reviews, approval_reviews, distinct_reviewed_assets


def measure_planning(
    scenarios: tuple[Scenario, ...], outcomes: tuple[bool, ...], repeats: int
) -> dict[str, tuple[float, float, float, int]]:
    resolved: dict[str, tuple[Any, Any]] = {}
    for (scenario_name, edge_id, _, _), material in zip(BRANCHES, outcomes, strict=True):
        scenario = next(item for item in scenarios if item.name == scenario_name)
        resolved[scenario_name] = resolved_case(scenario, edge_id, material)

    samples: dict[str, list[tuple[float, float, float]]] = {
        "GAMO-CA": [],
        "Field-aware DAG": [],
        "Conventional DAG": [],
        "Full Recompute": [],
    }
    for _ in range(repeats):
        for method in samples:
            initial_start = time.perf_counter_ns()
            for scenario in scenarios:
                if method == "GAMO-CA":
                    gamo_plan(scenario)
                elif method == "Field-aware DAG":
                    field_aware_dag_plan(scenario)
                elif method == "Conventional DAG":
                    dag_incremental(scenario)
                else:
                    full_recompute(scenario)
            initial_end = time.perf_counter_ns()
            replan_elapsed_ms = 0.0
            if method in ("GAMO-CA", "Field-aware DAG"):
                replan_start = time.perf_counter_ns()
                for scenario_name, (graph, event) in resolved.items():
                    scenario = next(item for item in scenarios if item.name == scenario_name)
                    if method == "GAMO-CA":
                        gamo_plan(scenario, graph, event)
                    else:
                        field_aware_dag_plan(scenario, graph, event)
                replan_elapsed_ms = (time.perf_counter_ns() - replan_start) / 1_000_000
            initial_elapsed_ms = (initial_end - initial_start) / 1_000_000
            samples[method].append(
                (
                    initial_elapsed_ms,
                    replan_elapsed_ms,
                    initial_elapsed_ms + replan_elapsed_ms,
                )
            )
    calls = {"GAMO-CA": 9, "Field-aware DAG": 9, "Conventional DAG": 5, "Full Recompute": 5}
    return {
        method: (
            statistics.median(sample[0] for sample in method_samples),
            statistics.median(sample[1] for sample in method_samples),
            statistics.median(sample[2] for sample in method_samples),
            calls[method],
        )
        for method, method_samples in samples.items()
    }


def worksheet_rows(scenarios: tuple[Scenario, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        target = next(node for node in scenario.graph.nodes if node.id == scenario.event.target_id)
        requirements = [node for node in scenario.graph.nodes if isinstance(node, Requirement)]
        if scenario.name in NEW_CONTENT:
            after = NEW_CONTENT[scenario.name]
        elif scenario.name in ("slogan_change", "all_hard_fanout_no_advantage"):
            after = f"{target.content} — revised"
        else:
            after = f"{target.content} [synthetic v2]"
        requirement_text = " | ".join(
            f"{node.id}={node.content} (confirmed)" for node in requirements
        )
        for node in scenario.graph.nodes:
            if not isinstance(node, AssetVersion):
                continue
            inputs = [
                f"{edge.upstream_id} -{edge.strength.value}-> {node.id}"
                + (f" (fields: {','.join(edge.relevant_fields)})" if edge.relevant_fields else "")
                for edge in scenario.graph.active_edges
                if edge.dependent_id == node.id
            ]
            rows.append(
                {
                    "case_code": CASE_CODES[scenario.name],
                    "workflow_change": CHANGE_SUMMARIES[scenario.name],
                    "requirements_before": requirement_text,
                    "changed_target": scenario.event.target_id,
                    "target_before": target.content,
                    "target_after_synthetic_change": after,
                    "changed_fields": ";".join(scenario.event.changed_fields),
                    "asset_to_label": node.id,
                    "asset_role": (
                        "CHANGED_SOURCE" if node.id == scenario.event.target_id else "DERIVED_ASSET"
                    ),
                    "current_asset_description": node.content,
                    "typed_inputs": " | ".join(inputs) if inputs else "No declared dependency",
                    "reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE": "",
                    "reviewer_approval_label_REAPPROVE_UNCHANGED_UNCERTAIN": "",
                    "reviewer_reason": "",
                    "reviewer_confidence_1_to_5": "",
                    "reviewer_notes": "",
                }
            )
    return rows


def build_results(
    seed: int, timing_repeats: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    scenarios = make_scenarios(seed)
    summary_rows: list[dict[str, Any]] = []
    branch_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    for outcomes in itertools.product((False, True), repeat=len(BRANCHES)):
        labels = ["MATERIAL_SYNTHETIC" if value else "NON_MATERIAL_SYNTHETIC" for value in outcomes]
        initial_gamo, final_gamo = final_actions(scenarios, outcomes, aware=False)
        initial_aware, final_aware = final_actions(scenarios, outcomes, aware=True)
        gamo_recomputes = sum(
            len(_asset_recomputes(scenario, final_gamo[scenario.name])) for scenario in scenarios
        )
        aware_recomputes = sum(
            len(_asset_recomputes(scenario, final_aware[scenario.name])) for scenario in scenarios
        )
        gamo_reviews = human_review_counts(scenarios, final_gamo)
        aware_reviews = human_review_counts(scenarios, final_aware)
        if gamo_recomputes != aware_recomputes or gamo_reviews != aware_reviews:
            raise AssertionError(
                "field-aware DAG should match GAMO-CA decisions on these resolved fixtures"
            )
        timings = measure_planning(scenarios, outcomes, timing_repeats)
        material_count = sum(outcomes)
        outcome_id = "".join("M" if item else "N" for item in outcomes)
        common = {
            "outcome_set_id": outcome_id,
            "review_outcomes_are": "SYNTHETIC_ASSUMPTIONS_NOT_HUMAN_RESPONSES",
            "branch_outcomes_S01_to_S04": ";".join(labels),
            "material_branch_count_assumption": material_count,
            "initial_gamo_recomputes_measured_from_plan": sum(
                len(_asset_recomputes(s, initial_gamo[s.name])) for s in scenarios
            ),
        }
        for (scenario_name, _, root_id, case_code), _material, label in zip(
            BRANCHES, outcomes, labels, strict=True
        ):
            scenario = next(item for item in scenarios if item.name == scenario_name)
            hard_child = next(
                edge.dependent_id
                for edge in scenario.graph.active_edges
                if edge.upstream_id == root_id and edge.strength == DependencyType.HARD
            )
            branch_rows.append(
                {
                    "outcome_set_id": outcome_id,
                    "case_code": case_code,
                    "soft_review_root": root_id,
                    "hard_child": hard_child,
                    "synthetic_outcome": label,
                    "root_final_action": final_gamo[scenario_name][root_id].value,
                    "hard_child_final_action": final_gamo[scenario_name][hard_child].value,
                    "final_recomputations_in_this_scenario": len(
                        _asset_recomputes(scenario, final_gamo[scenario_name])
                    ),
                    "note": (
                        "Simulated field relevance was resolved, then the pure planner ran "
                        "on a new snapshot."
                    ),
                }
            )

        for method, final_recompute_count, review_counts in (
            (
                "GAMO-CA",
                gamo_recomputes,
                gamo_reviews,
            ),
            ("Field-aware DAG", aware_recomputes, aware_reviews),
            ("Conventional DAG", 21, (0, 24, 24)),
            ("Full Recompute", 24, (0, 25, 25)),
        ):
            initial_ms, replan_ms, total_ms, calls = timings[method]
            review_resolution, approval_review, unique_review = review_counts
            summary_rows.append(
                {
                    **common,
                    "method": method,
                    "final_recomputation_operations_planned": final_recompute_count,
                    "synthetic_SOFT_resolution_reviews_required": review_resolution,
                    "exact_version_or_renewal_approval_reviews_required": approval_review,
                    "unique_assets_requiring_review": unique_review,
                    "replanning_rounds": 4 if method in ("GAMO-CA", "Field-aware DAG") else 0,
                    "planning_calls": calls,
                    "initial_planning_time_ms_measured_median_workflow": f"{initial_ms:.6f}",
                    "replanning_time_ms_measured_median_workflow": f"{replan_ms:.6f}",
                    "total_planning_overhead_ms_measured_median_workflow": f"{total_ms:.6f}",
                    "timing_repetitions": timing_repeats,
                    "timing_scope": "planner calls only; excludes human review and generation",
                }
            )
            for review_cost in (0.5, 1.0, 4.0):
                for initial_rate in (0.01, 0.1):
                    for replan_rate in (0.01, 0.1):
                        final_cost = float(final_recompute_count)
                        human_cost = (review_resolution + approval_review) * review_cost
                        initial_cost = initial_ms * initial_rate
                        replan_cost = replan_ms * replan_rate
                        cost_rows.append(
                            {
                                "outcome_set_id": outcome_id,
                                "method": method,
                                "final_recomputations_measured_or_planned": final_recompute_count,
                                "projected_human_review_operations_required": review_resolution
                                + approval_review,
                                "initial_planning_ms_measured": f"{initial_ms:.6f}",
                                "replanning_ms_measured": f"{replan_ms:.6f}",
                                "recompute_work_units_per_operation_assumption": 1.0,
                                "review_work_units_per_operation_assumption": review_cost,
                                "initial_plan_work_units_per_ms_assumption": initial_rate,
                                "replan_work_units_per_ms_assumption": replan_rate,
                                "final_recomputation_cost_assumption": f"{final_cost:.4f}",
                                "human_review_cost_assumption": f"{human_cost:.4f}",
                                "initial_planning_cost_assumption": f"{initial_cost:.4f}",
                                "replanning_cost_assumption": f"{replan_cost:.4f}",
                                "total_hypothetical_work_units": (
                                    f"{final_cost + human_cost + initial_cost + replan_cost:.4f}"
                                ),
                                "classification": (
                                    "HYPOTHETICAL_COSTS; no currency or human minutes measured"
                                ),
                            }
                        )
    return summary_rows, branch_rows, cost_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write an empty file: {path}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--timing-repeats", type=int, default=TIMING_REPEATS)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    if args.timing_repeats < 3:
        raise SystemExit("use at least three timing repetitions")
    scenarios = make_scenarios(args.seed)
    worksheet = worksheet_rows(scenarios)
    summaries, branches, costs = build_results(args.seed, args.timing_repeats)
    write_csv(args.output_dir / "review-worksheet.csv", worksheet)
    write_csv(args.output_dir / "synthetic-workflow-results.csv", summaries)
    write_csv(args.output_dir / "branch-resolution.csv", branches)
    write_csv(args.output_dir / "cost-sensitivity.csv", costs)
    manifest = {
        "phase": "R1.3",
        "classification": "SMALL_SYNTHETIC_WORKFLOW_VALIDATION_NOT_HUMAN_REVIEW",
        "seed": args.seed,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "timing_repeats": args.timing_repeats,
        "outcome_combinations": 16,
        "branch_outcomes_are_human_responses": False,
        "worksheet_labels_are_blank": True,
        "original_r1_1_r1_2_artifacts_modified": False,
        "initial_plan_calls_per_workflow": 5,
        "replans_per_gamo_or_field_aware_workflow": 4,
        "synthetic_outcome_semantics": {
            "material": "set the SOFT edge relevant_fields to the changed event fields",
            "non_material": (
                "set the SOFT edge relevant_fields to a distinct, non-overlapping field"
            ),
        },
        "field_aware_dag": (
            "independent traversal baseline using the same edge field metadata and synthetic "
            "review outcomes; assumes valid fixtures and omits GAMO-CA's "
            "validation/provenance features"
        ),
        "timing_scope": (
            "planner calls only; excludes synthetic human review time and asset generation"
        ),
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"R1.3: {len(worksheet)} blank review rows; {len(branches)} branch outcomes; "
        f"{len(summaries)} workflow summaries."
    )
    print("Outcome rows are synthetic assumptions, not human responses.")
    print(f"Output: {args.output_dir}")


if __name__ == "__main__":
    main()
