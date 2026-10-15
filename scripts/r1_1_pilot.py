"""Small deterministic comparison of recomputation plans for R1.1.

This is a teaching pilot, not a benchmark framework. The two baseline planners are
implemented here independently of gamo_ca.planner; GAMO-CA calls the existing pure
planner. No API, database, model provider, or network service is used.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import random
import statistics
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from gamo_ca.fingerprints import fingerprint, requirement_fingerprint  # noqa: E402
from gamo_ca.graph import Graph  # noqa: E402
from gamo_ca.models import (  # noqa: E402
    Action,
    AssetVersion,
    ChangeEvent,
    DependencyEdge,
    DependencyType,
    Evidence,
    InputRef,
    Requirement,
    RequirementStatus,
)
from gamo_ca.planner import Policy, plan_change  # noqa: E402

SEED = 20261014
TIMING_REPEATS = 101
TIME = datetime(2026, 10, 14, tzinfo=UTC)
TENANT_ID = "pilot-tenant"
PROJECT_PREFIX = "pilot"
METHODS = ("Full Recompute", "Conventional DAG Incremental", "GAMO-CA")
COLORS = {
    "Full Recompute": "#64748b",
    "Conventional DAG Incremental": "#f59e0b",
    "GAMO-CA": "#0f766e",
}


@dataclass(frozen=True)
class EdgeSpec:
    upstream: str
    downstream: str
    strength: DependencyType
    relevant_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class Oracle:
    """Hand-authored expected safety obligations, fixed before planners run."""

    must_recompute: frozenset[str]
    must_review: frozenset[str]
    initially_approved: frozenset[str]
    approvals_invalidated_by_event: frozenset[str]


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    graph: Graph
    event: ChangeEvent
    oracle: Oracle
    asset_ids: tuple[str, ...]


@dataclass(frozen=True)
class PlanResult:
    actions: dict[str, Action]
    reasons: dict[str, str]


@dataclass(frozen=True)
class Evaluation:
    recompute_operations: int
    review_operations: int
    correct: bool
    failures: tuple[str, ...]
    approval_leaks: tuple[str, ...]
    eligible_asset_ids: tuple[str, ...]
    action_by_node: dict[str, Action]
    reason_by_node: dict[str, str]


class ScenarioManifest(TypedDict):
    name: str
    description: str
    snapshot_hash: str
    event_id: str
    changed_target: str
    changed_fields: list[str]
    nodes: int
    edges: int
    oracle_must_recompute: list[str]
    oracle_must_review: list[str]
    oracle_invalidated_approvals: list[str]


class PilotManifest(TypedDict):
    pilot: str
    classification: str
    seed: int
    python_version: str
    platform: str
    timing_repetitions: int
    methods: list[str]
    oracle_definition: dict[str, str]
    scenarios: list[ScenarioManifest]


def make_scenarios(seed: int = SEED) -> tuple[Scenario, ...]:
    """Build five fixed workloads; the seed selects harmless synthetic copy text."""

    rng = random.Random(seed)
    slogan = rng.choice(("Make room for wonder", "Small steps, bright ideas", "Made to move"))
    future_slogan = f"{slogan} — revised"
    slogan_change = _scenario(
        name="slogan_change",
        description=("A confirmed slogan changes; copy paths are HARD and visual paths are SOFT."),
        requirements={"req_slogan": slogan, "req_palette": "teal and cream"},
        target="req_slogan",
        new_content=future_slogan,
        changed_fields=("text",),
        assets=("copy", "captions", "storyboard", "social_visual", "social_export", "logo"),
        edges=(
            EdgeSpec("req_slogan", "copy", DependencyType.HARD),
            EdgeSpec("copy", "captions", DependencyType.HARD),
            EdgeSpec("copy", "storyboard", DependencyType.HARD),
            EdgeSpec("req_slogan", "social_visual", DependencyType.SOFT, ("palette",)),
            EdgeSpec("req_slogan", "social_export", DependencyType.SOFT),
            EdgeSpec("social_export", "logo", DependencyType.HARD),
        ),
        must_recompute=frozenset({"copy", "captions", "storyboard"}),
        must_review=frozenset({"social_export", "logo"}),
    )
    brand_change = _scenario(
        name="brand_guideline_change",
        description=(
            "A brand palette changes; relevant links recompute and unknown links need review."
        ),
        requirements={"req_palette": "teal and cream", "req_slogan": slogan},
        target="req_palette",
        new_content="cobalt and ivory",
        changed_fields=("color",),
        assets=("copy", "palette_art", "photo_grade", "layout_review", "final_export"),
        edges=(
            EdgeSpec("req_slogan", "copy", DependencyType.HARD),
            EdgeSpec("req_palette", "palette_art", DependencyType.SOFT, ("color",)),
            EdgeSpec("req_palette", "photo_grade", DependencyType.SOFT, ("color",)),
            EdgeSpec("req_palette", "layout_review", DependencyType.SOFT),
            EdgeSpec("layout_review", "final_export", DependencyType.HARD),
        ),
        must_recompute=frozenset({"palette_art", "photo_grade"}),
        must_review=frozenset({"layout_review", "final_export"}),
    )
    asset_update = _scenario(
        name="asset_version_update",
        description="A source photo is replaced; dependent crops are HARD and captions uncertain.",
        requirements={"req_campaign": "Spring community launch"},
        target="source_photo",
        new_content="Synthetic replacement photo v2",
        changed_fields=("image",),
        assets=(
            "source_photo",
            "ad_crop",
            "web_crop",
            "caption",
            "caption_export",
            "approved_copy",
        ),
        edges=(
            EdgeSpec("req_campaign", "source_photo", DependencyType.HARD),
            EdgeSpec("source_photo", "ad_crop", DependencyType.HARD),
            EdgeSpec("source_photo", "web_crop", DependencyType.HARD),
            EdgeSpec("source_photo", "caption", DependencyType.SOFT),
            EdgeSpec("caption", "caption_export", DependencyType.HARD),
            EdgeSpec("req_campaign", "approved_copy", DependencyType.HARD),
        ),
        must_recompute=frozenset({"ad_crop", "web_crop"}),
        must_review=frozenset({"caption", "caption_export"}),
    )
    approval_change = _scenario(
        name="approval_invalidation",
        description=("A legal requirement changes; approvals bound to the old snapshot expire."),
        requirements={"req_legal": "Include the local disclaimer", "req_mood": "Warm tone"},
        target="req_legal",
        new_content="Include the updated local disclaimer",
        changed_fields=("disclaimer",),
        assets=("compliance_copy", "legal_montage", "legal_export", "moodboard"),
        edges=(
            EdgeSpec("req_legal", "compliance_copy", DependencyType.HARD),
            EdgeSpec("req_legal", "legal_montage", DependencyType.SOFT),
            EdgeSpec("legal_montage", "legal_export", DependencyType.HARD),
            EdgeSpec("req_mood", "moodboard", DependencyType.HARD),
        ),
        must_recompute=frozenset({"compliance_copy"}),
        must_review=frozenset({"legal_montage", "legal_export"}),
    )
    no_advantage = _scenario(
        name="all_hard_fanout_no_advantage",
        description="Every output is on a HARD path; selective planning has no work to avoid.",
        requirements={"req_slogan": slogan},
        target="req_slogan",
        new_content=future_slogan,
        changed_fields=("text",),
        assets=("copy", "captions", "storyboard", "banner"),
        edges=(
            EdgeSpec("req_slogan", "copy", DependencyType.HARD),
            EdgeSpec("copy", "captions", DependencyType.HARD),
            EdgeSpec("copy", "storyboard", DependencyType.HARD),
            EdgeSpec("req_slogan", "banner", DependencyType.HARD),
        ),
        must_recompute=frozenset({"copy", "captions", "storyboard", "banner"}),
        must_review=frozenset(),
    )
    return (slogan_change, brand_change, asset_update, approval_change, no_advantage)


def _scenario(
    *,
    name: str,
    description: str,
    requirements: dict[str, str],
    target: str,
    new_content: str,
    changed_fields: tuple[str, ...],
    assets: tuple[str, ...],
    edges: tuple[EdgeSpec, ...],
    must_recompute: frozenset[str],
    must_review: frozenset[str],
) -> Scenario:
    project_id = f"{PROJECT_PREFIX}-{name}"
    evidence = Evidence(
        id=f"evidence-{name}",
        tenant_id=TENANT_ID,
        project_id=project_id,
        created_at=TIME,
        version=1,
        content=f"Synthetic confirmed source for {name}",
        valid_from=TIME,
        source_id=f"source-{name}",
        extracted_span="Synthetic human-confirmed instruction",
        confirmed_by="synthetic-reviewer",
    )
    requirement_nodes = {
        node_id: Requirement(
            id=node_id,
            tenant_id=TENANT_ID,
            project_id=project_id,
            created_at=TIME,
            version=1,
            content=content,
            valid_from=TIME,
            source_id=evidence.id,
            evidence_ids=(evidence.id,),
            status=RequirementStatus.CONFIRMED,
            confirmed_by="synthetic-reviewer",
        )
        for node_id, content in requirements.items()
    }
    asset_content = {asset_id: f"Synthetic draft: {asset_id}" for asset_id in assets}
    input_ids: dict[str, list[str]] = {asset_id: [] for asset_id in assets}
    for edge in edges:
        if edge.downstream in input_ids:
            input_ids[edge.downstream].append(edge.upstream)

    by_id: dict[str, Requirement | AssetVersion] = dict(requirement_nodes)
    for asset_id in _asset_order(assets, edges):
        inputs = tuple(_reference(by_id[source_id]) for source_id in input_ids[asset_id])
        node = AssetVersion(
            id=asset_id,
            tenant_id=TENANT_ID,
            project_id=project_id,
            created_at=TIME,
            version=1,
            content=asset_content[asset_id],
            valid_from=TIME,
            inputs=inputs,
            evidence_ids=(evidence.id,),
            provider="deterministic-mock",
            model_version="fixture-v1",
            prompt_version="pilot-v1",
            policy_version="policy-v1",
            asset_id=f"asset-{asset_id}",
            requirement_fingerprint=requirement_fingerprint(tuple(requirement_nodes.values())),
        )
        by_id[asset_id] = node

    graph_edges = tuple(
        DependencyEdge(
            id=f"edge-{spec.upstream}-{spec.downstream}",
            tenant_id=TENANT_ID,
            project_id=project_id,
            created_at=TIME,
            upstream_id=spec.upstream,
            dependent_id=spec.downstream,
            strength=spec.strength,
            valid_from=TIME,
            relevant_fields=spec.relevant_fields,
        )
        for spec in edges
    )
    graph = Graph(
        tenant_id=TENANT_ID,
        project_id=project_id,
        as_of=TIME,
        nodes=tuple([evidence, *requirement_nodes.values(), *(by_id[item] for item in assets)]),
        edges=graph_edges,
    )
    target_node = by_id[target]
    event = ChangeEvent(
        id=f"event-{name}",
        tenant_id=TENANT_ID,
        project_id=project_id,
        created_at=TIME,
        target_id=target,
        source_id=evidence.id,
        actor_id="synthetic-reviewer",
        change_type="SYNTHETIC_CONTENT_CHANGE",
        old_version=target_node.version,
        new_version=target_node.version + 1,
        old_hash=target_node.content_hash,
        new_hash=fingerprint(new_content),
        changed_fields=changed_fields,
        occurred_at=graph.as_of,
        expected_snapshot_hash=graph.snapshot_hash,
    )
    invalidated = frozenset(assets) if target in requirement_nodes else frozenset({target})
    return Scenario(
        name=name,
        description=description,
        graph=graph,
        event=event,
        oracle=Oracle(
            must_recompute=must_recompute,
            must_review=must_review,
            initially_approved=frozenset(assets),
            approvals_invalidated_by_event=invalidated,
        ),
        asset_ids=assets,
    )


def _asset_order(assets: tuple[str, ...], edges: tuple[EdgeSpec, ...]) -> tuple[str, ...]:
    """Order asset specs by their declared input assets; fail on a fixture cycle."""
    pending = set(assets)
    ordered: list[str] = []
    while pending:
        ready = sorted(
            asset_id
            for asset_id in pending
            if all(
                edge.upstream not in pending
                for edge in edges
                if edge.downstream == asset_id and edge.upstream in assets
            )
        )
        if not ready:
            raise ValueError("pilot fixture contains an asset dependency cycle")
        ordered.extend(ready)
        pending.difference_update(ready)
    return tuple(ordered)


def _reference(node: Requirement | AssetVersion) -> InputRef:
    return InputRef(node.id, node.version, node.content_hash)


def full_recompute(scenario: Scenario) -> PlanResult:
    """Baseline A: regenerate every derived creative node except the edited source."""
    source = scenario.event.target_id
    actions = {
        node.id: (
            Action.RECOMPUTE
            if isinstance(node, AssetVersion) and node.id != source
            else Action.KEEP
        )
        for node in scenario.graph.nodes
    }
    return PlanResult(actions, {key: "full replay baseline" for key in actions})


def dag_incremental(scenario: Scenario) -> PlanResult:
    """Baseline B: invalidate all downstream declared HARD and SOFT dependencies."""
    outgoing: dict[str, list[str]] = {node.id: [] for node in scenario.graph.nodes}
    for edge in scenario.graph.active_edges:
        if edge.strength != DependencyType.INFORMATIONAL:
            outgoing[edge.upstream_id].append(edge.dependent_id)
    affected: set[str] = set()
    stack = list(outgoing[scenario.event.target_id])
    while stack:
        node_id = stack.pop()
        if node_id in affected:
            continue
        affected.add(node_id)
        stack.extend(outgoing[node_id])
    actions = {
        node.id: Action.RECOMPUTE if node.id in affected else Action.KEEP
        for node in scenario.graph.nodes
    }
    return PlanResult(actions, {key: "DAG descendant invalidation" for key in actions})


def gamo_ca(scenario: Scenario) -> PlanResult:
    """Treatment: adapt the already-implemented pure GAMO-CA planner output."""
    plan = plan_change(scenario.graph, scenario.event, Policy(version="pilot-policy-v1"))
    return PlanResult(
        {decision.node_id: decision.action for decision in plan.decisions},
        {decision.node_id: "; ".join(decision.reasons) for decision in plan.decisions},
    )


PLANNERS: dict[str, Callable[[Scenario], PlanResult]] = {
    METHODS[0]: full_recompute,
    METHODS[1]: dag_incremental,
    METHODS[2]: gamo_ca,
}


def correctness_oracle(scenario: Scenario, result: PlanResult) -> Evaluation:
    """Check actions and exact-version eligibility against hand-authored obligations."""
    failures: list[str] = []
    for node_id in sorted(scenario.oracle.must_recompute):
        if result.actions.get(node_id) != Action.RECOMPUTE:
            failures.append(f"required HARD recomputation missing: {node_id}")
    for node_id in sorted(scenario.oracle.must_review):
        if result.actions.get(node_id) not in (Action.REVIEW, Action.RECOMPUTE, Action.BLOCK):
            failures.append(f"uncertain SOFT impact kept without review: {node_id}")

    recomputed_assets = {
        node_id for node_id in scenario.asset_ids if result.actions[node_id] == Action.RECOMPUTE
    }
    invalidated_approvals = set(scenario.oracle.approvals_invalidated_by_event)
    invalidated_approvals.update(recomputed_assets)
    review_holds = {
        node_id
        for node_id, action in result.actions.items()
        if action in (Action.REVIEW, Action.BLOCK)
    }
    review_operations = invalidated_approvals | review_holds
    eligible: list[str] = []
    for asset_id in scenario.oracle.initially_approved:
        if asset_id in invalidated_approvals or asset_id in review_holds:
            continue
        # Exact asset version and requirement fingerprint remain unchanged here.
        if result.actions[asset_id] == Action.KEEP:
            eligible.append(asset_id)

    approval_leaks = tuple(sorted(set(eligible) & invalidated_approvals))
    if approval_leaks:
        failures.append(f"stale exact-version approval accepted: {', '.join(approval_leaks)}")
    return Evaluation(
        recompute_operations=len(recomputed_assets),
        review_operations=len(review_operations),
        correct=not failures,
        failures=tuple(failures),
        approval_leaks=approval_leaks,
        eligible_asset_ids=tuple(sorted(eligible)),
        action_by_node=result.actions,
        reason_by_node=result.reasons,
    )


def _median_planning_ms(
    planner: Callable[[Scenario], PlanResult], scenario: Scenario, repeats: int
) -> float:
    samples: list[float] = []
    expected: PlanResult | None = None
    for _ in range(repeats):
        start = time.perf_counter_ns()
        result = planner(scenario)
        elapsed = time.perf_counter_ns() - start
        if expected is not None and result != expected:
            raise AssertionError("planner output changed for deterministic input")
        expected = result
        samples.append(elapsed / 1_000_000)
    return statistics.median(samples)


def run_pilot(
    seed: int = SEED, timing_repeats: int = TIMING_REPEATS
) -> tuple[list[dict[str, object]], list[dict[str, object]], PilotManifest]:
    if timing_repeats < 3:
        raise ValueError("use at least three timing repetitions")
    scenarios = make_scenarios(seed)
    results: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    manifest_scenarios: list[ScenarioManifest] = []
    for scenario in scenarios:
        manifest_scenarios.append(
            {
                "name": scenario.name,
                "description": scenario.description,
                "snapshot_hash": scenario.graph.snapshot_hash,
                "event_id": scenario.event.id,
                "changed_target": scenario.event.target_id,
                "changed_fields": list(scenario.event.changed_fields),
                "nodes": len(scenario.graph.nodes),
                "edges": len(scenario.graph.active_edges),
                "oracle_must_recompute": sorted(scenario.oracle.must_recompute),
                "oracle_must_review": sorted(scenario.oracle.must_review),
                "oracle_invalidated_approvals": sorted(
                    scenario.oracle.approvals_invalidated_by_event
                ),
            }
        )
        for method in METHODS:
            planner = PLANNERS[method]
            output = planner(scenario)
            evaluation = correctness_oracle(scenario, output)
            elapsed_ms = _median_planning_ms(planner, scenario, timing_repeats)
            results.append(
                {
                    "scenario": scenario.name,
                    "method": method,
                    "seed": seed,
                    "graph_nodes": len(scenario.graph.nodes),
                    "graph_edges": len(scenario.graph.active_edges),
                    "recompute_operations": evaluation.recompute_operations,
                    "review_operations": evaluation.review_operations,
                    "correctness": "PASS" if evaluation.correct else "FAIL",
                    "correctness_failures": " | ".join(evaluation.failures),
                    "approval_leaks": len(evaluation.approval_leaks),
                    "eligible_asset_ids": ";".join(evaluation.eligible_asset_ids),
                    "median_planning_time_ms": f"{elapsed_ms:.6f}",
                    "timing_repetitions": timing_repeats,
                    "timing_scope": "planner only; no generation or human time",
                }
            )
            for node in scenario.graph.nodes:
                decisions.append(
                    {
                        "scenario": scenario.name,
                        "method": method,
                        "node_id": node.id,
                        "node_type": type(node).__name__,
                        "action": evaluation.action_by_node[node.id].value,
                        "reason": evaluation.reason_by_node[node.id],
                        "required_by_oracle": (
                            "RECOMPUTE"
                            if node.id in scenario.oracle.must_recompute
                            else "REVIEW"
                            if node.id in scenario.oracle.must_review
                            else "NONE"
                        ),
                        "eligible_after_change": node.id in evaluation.eligible_asset_ids,
                    }
                )
    manifest: PilotManifest = {
        "pilot": "R1.1",
        "classification": "SMALL_SYNTHETIC_ENGINEERING_PILOT",
        "seed": seed,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "timing_repetitions": timing_repeats,
        "methods": list(METHODS),
        "oracle_definition": {
            "hard_required": "the listed node must be RECOMPUTE",
            "soft_uncertain": "the listed node must be REVIEW, RECOMPUTE, or BLOCK",
            "approval": (
                "eligible only for unchanged asset version and requirement fingerprint; "
                "no new approval is assumed"
            ),
            "counts": (
                "AssetVersion nodes count as recomputation operations; reviews count "
                "unique reviewed nodes plus invalidated approved assets"
            ),
        },
        "scenarios": manifest_scenarios,
    }
    return results, decisions, manifest


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError("cannot write empty CSV")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def render_bar_chart(
    title: str,
    ylabel: str,
    scenario_names: list[str],
    values: dict[str, dict[str, float]],
    *,
    width: int = 1050,
    height: int = 480,
) -> str:
    """Draw a grouped SVG bar chart using only the Python standard library."""
    left, top, right, bottom = 76, 64, 30, 105
    plot_width, plot_height = width - left - right, height - top - bottom
    largest = max(1e-9, max((v for row in values.values() for v in row.values()), default=1)) * 1.12
    svg = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": str(width),
            "height": str(height),
            "viewBox": f"0 0 {width} {height}",
        },
    )

    def add(tag: str, text: str | None = None, **attrs: object) -> None:
        element = ET.SubElement(
            svg, tag, {key.replace("_", "-"): str(value) for key, value in attrs.items()}
        )
        element.text = text

    add("rect", width="100%", height="100%", fill="white")
    add(
        "text",
        title,
        x=width / 2,
        y=30,
        font_family="Arial,sans-serif",
        font_size=20,
        font_weight=700,
        fill="#0f172a",
        text_anchor="middle",
    )
    for tick in range(5):
        value = largest * tick / 4
        y = top + plot_height * (1 - tick / 4)
        add("line", x1=left, y1=f"{y:.1f}", x2=width - right, y2=f"{y:.1f}", stroke="#e2e8f0")
        add(
            "text",
            f"{value:.2f}",
            x=left - 10,
            y=f"{y + 4:.1f}",
            font_size=10,
            text_anchor="end",
            fill="#475569",
        )
    middle = top + plot_height / 2
    add(
        "text",
        ylabel,
        x=18,
        y=f"{middle:.1f}",
        transform=f"rotate(-90 18 {middle:.1f})",
        font_size=12,
        text_anchor="middle",
    )

    group_width = plot_width / max(len(scenario_names), 1)
    bar_width = min(42, group_width / (len(METHODS) + 1))
    for index, scenario in enumerate(scenario_names):
        center = left + group_width * (index + 0.5)
        add(
            "text",
            scenario.replace("_", " "),
            x=f"{center:.1f}",
            y=top + plot_height + 22,
            font_size=10,
            text_anchor="middle",
        )
        for method_index, method in enumerate(METHODS):
            value = values[scenario][method]
            bar_height = plot_height * value / largest
            x = center + (method_index - 1) * (bar_width + 5) - bar_width / 2
            y = top + plot_height - bar_height
            add(
                "rect",
                x=f"{x:.1f}",
                y=f"{y:.1f}",
                width=f"{bar_width:.1f}",
                height=f"{bar_height:.1f}",
                rx=3,
                fill=COLORS[method],
            )
            add(
                "text",
                f"{value:g}",
                x=f"{x + bar_width / 2:.1f}",
                y=f"{max(y - 4, top + 12):.1f}",
                font_size=10,
                text_anchor="middle",
            )

    legend_y, legend_x = height - 31, (width - 620) / 2
    for index, method in enumerate(METHODS):
        x = legend_x + index * 210
        add("rect", x=f"{x:.1f}", y=legend_y - 12, width=13, height=13, rx=2, fill=COLORS[method])
        add("text", method, x=f"{x + 19:.1f}", y=legend_y, font_size=11)
    return ET.tostring(svg, encoding="unicode")


def save_outputs(output_dir: Path, seed: int, timing_repeats: int) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results, decisions, manifest = run_pilot(seed, timing_repeats)
    write_csv(output_dir / "results.csv", results)
    write_csv(output_dir / "node_decisions.csv", decisions)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    by_metric: dict[str, dict[str, dict[str, float]]] = {}
    for metric in ("recompute_operations", "review_operations", "median_planning_time_ms"):
        by_metric[metric] = {}
        for scenario in manifest["scenarios"]:
            name = scenario["name"]
            by_metric[metric][name] = {}
            for method in METHODS:
                value = next(
                    row[metric]
                    for row in results
                    if row["scenario"] == name and row["method"] == method
                )
                by_metric[metric][name][method] = float(str(value))
    for metric, title, ylabel, filename in (
        (
            "recompute_operations",
            "Recomputation operations by scenario",
            "Asset regeneration operations",
            "recomputation.svg",
        ),
        (
            "review_operations",
            "Review operations by scenario",
            "Distinct reviewer operations",
            "reviews.svg",
        ),
        (
            "median_planning_time_ms",
            "Planning time by scenario",
            "Median planning time (ms)",
            "planning-time.svg",
        ),
    ):
        (output_dir / filename).write_text(
            render_bar_chart(
                title,
                ylabel,
                [item["name"] for item in manifest["scenarios"]],
                by_metric[metric],
            ),
            encoding="utf-8",
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--timing-repeats", type=int, default=TIMING_REPEATS)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs" / "research" / "r1_1-pilot",
    )
    args = parser.parse_args()
    results = save_outputs(args.output_dir, args.seed, args.timing_repeats)
    failures = [row for row in results if row["correctness"] != "PASS"]
    print(f"R1.1 pilot: {len(results)} scenario-method runs; seed={args.seed}")
    print(f"Correctness: {len(results) - len(failures)}/{len(results)} PASS")
    print(f"Results: {args.output_dir / 'results.csv'}")
    print("Charts:")
    for filename in ("recomputation.svg", "reviews.svg", "planning-time.svg"):
        print(f"  {args.output_dir / filename}")
    if failures:
        for row in failures:
            print(f"FAIL {row['scenario']} / {row['method']}: {row['correctness_failures']}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
