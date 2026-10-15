"""Audit saved R1.1 pilot outputs without changing or rerunning them.

The generated R1.2 files are an accounting and sensitivity analysis, not new
benchmark observations. Cost weights and review-resolution fractions are explicit
assumptions; R1.1 planning times and operation counts remain the observed inputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "docs" / "research" / "r1_1-pilot"
OUTPUT_DIR = ROOT / "docs" / "research" / "r1_2-audit"
METHODS = ("Full Recompute", "Conventional DAG Incremental", "GAMO-CA")
SCENARIO_REASONS = {
    "slogan_change": (
        "Three HARD text-path outputs recompute. A field-disjoint SOFT palette edge is kept. "
        "An unknown SOFT export and its HARD child wait for review."
    ),
    "brand_guideline_change": (
        "Two color-relevant SOFT edges recompute. An unknown layout edge and its HARD export "
        "wait for review."
    ),
    "asset_version_update": (
        "Two HARD crops recompute. The uncertain caption edge and its HARD export wait for "
        "review; unrelated approved copy is kept."
    ),
    "approval_invalidation": (
        "The HARD compliance copy recomputes. The uncertain legal montage and its HARD export "
        "wait. The global requirement fingerprint also invalidates the unrelated moodboard "
        "approval."
    ),
    "all_hard_fanout_no_advantage": (
        "All four outputs are on HARD paths, so every method recomputes all four."
    ),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_inputs(results: list[dict[str, str]], decisions: list[dict[str, str]]) -> None:
    if len(results) != 15 or len(decisions) != 114:
        raise ValueError("unexpected R1.1 artifact row counts; refusing to audit changed inputs")
    if any(row["correctness"] != "PASS" for row in results):
        raise ValueError("R1.1 has a failed case; inspect it before sensitivity analysis")
    if {row["method"] for row in results} != set(METHODS):
        raise ValueError("R1.1 method labels differ from the expected three methods")
    if len({row["seed"] for row in results}) != 1:
        raise ValueError("R1.1 results contain multiple seeds")


def scenario_accounting(
    result_rows: list[dict[str, str]], decision_rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    by_result = {(row["scenario"], row["method"]): row for row in result_rows}
    by_decision: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in decision_rows:
        by_decision[(row["scenario"], row["method"])].append(row)

    scenarios = list(dict.fromkeys(row["scenario"] for row in result_rows))
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        gamo_decisions = by_decision[(scenario, "GAMO-CA")]
        review_assets = [
            row["node_id"]
            for row in gamo_decisions
            if row["node_type"] == "AssetVersion" and row["action"] == "REVIEW"
        ]
        held_hard_descendants = [
            row["node_id"]
            for row in gamo_decisions
            if row["node_type"] == "AssetVersion"
            and row["action"] == "REVIEW"
            and "HARD input pending human review" in row["reason"]
        ]
        soft_review_roots = [
            row["node_id"]
            for row in gamo_decisions
            if row["node_type"] == "AssetVersion"
            and row["action"] == "REVIEW"
            and "SOFT impact unknown" in row["reason"]
        ]
        obligations = [row for row in gamo_decisions if row["required_by_oracle"] == "RECOMPUTE"]
        incorrect_hard_reviews = [
            row["node_id"] for row in obligations if row["action"] != "RECOMPUTE"
        ]
        dag_count = int(
            by_result[(scenario, "Conventional DAG Incremental")]["recompute_operations"]
        )
        gamo_count = int(by_result[(scenario, "GAMO-CA")]["recompute_operations"])
        rows.append(
            {
                "scenario": scenario,
                "dag_immediate_recomputes": dag_count,
                "gamo_immediate_recomputes": gamo_count,
                "immediate_recomputes_avoided": dag_count - gamo_count,
                "oracle_required_hard_recomputes": len(obligations),
                "oracle_required_hard_not_recomputed": ";".join(incorrect_hard_reviews),
                "soft_review_roots": ";".join(soft_review_roots),
                "hard_descendants_held_for_review": ";".join(held_hard_descendants),
                "review_asset_nodes_with_conditional_recompute": ";".join(review_assets),
                "conditional_recompute_upper_bound": len(review_assets),
                "gamo_if_every_reviewed_asset_is_recomputed": gamo_count + len(review_assets),
                "review_operations_dag": int(
                    by_result[(scenario, "Conventional DAG Incremental")]["review_operations"]
                ),
                "review_operations_gamo": int(
                    by_result[(scenario, "GAMO-CA")]["review_operations"]
                ),
                "scenario_interpretation": SCENARIO_REASONS[scenario],
            }
        )
    return rows


def make_sensitivity(
    result_rows: list[dict[str, str]], conditional_nodes: int = 8
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_method: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in result_rows:
        by_method[row["method"]].append(row)
    planning_ms = {
        method: sum(float(row["median_planning_time_ms"]) for row in rows)
        for method, rows in by_method.items()
    }
    recomputes = {
        method: sum(int(row["recompute_operations"]) for row in rows)
        for method, rows in by_method.items()
    }
    reviews = {
        method: sum(int(row["review_operations"]) for row in rows)
        for method, rows in by_method.items()
    }

    fractions = (0.0, 0.25, 0.5, 0.75, 1.0)
    planning_weights = (0.0, 0.01, 0.1, 1.0)
    review_weights = (0.25, 1.0, 4.0)
    rows: list[dict[str, Any]] = []
    thresholds: list[dict[str, Any]] = []
    plan_delta = planning_ms["GAMO-CA"] - planning_ms["Conventional DAG Incremental"]
    for q in fractions:
        gamo_expected = recomputes["GAMO-CA"] + q * conditional_nodes
        compute_saved = recomputes["Conventional DAG Incremental"] - gamo_expected
        break_even = compute_saved / plan_delta if plan_delta > 0 else None
        thresholds.append(
            {
                "review_branches_resolved_as_material_fraction_assumption": q,
                "gamo_expected_recomputes_assumption": gamo_expected,
                "dag_recomputes_observed": recomputes["Conventional DAG Incremental"],
                "gamo_minus_dag_planning_ms_measured": f"{plan_delta:.6f}",
                "break_even_planning_work_units_per_ms_per_recompute_work_unit": (
                    f"{break_even:.6f}" if break_even is not None else "undefined"
                ),
                "interpretation": (
                    "GAMO total cost is lower below this assumed planning-cost ratio; "
                    "DAG is lower above it, under this q assumption."
                ),
            }
        )
        for review_weight in review_weights:
            for plan_weight in planning_weights:
                totals: dict[str, float] = {}
                for method in METHODS:
                    method_recomputes = gamo_expected if method == "GAMO-CA" else recomputes[method]
                    compute_cost = method_recomputes  # Assumption: one unit per recomputation.
                    review_cost = reviews[method] * review_weight
                    planning_cost = planning_ms[method] * plan_weight
                    total = compute_cost + review_cost + planning_cost
                    totals[method] = total
                    rows.append(
                        {
                            "material_review_fraction_assumption": q,
                            "recompute_work_units_per_operation_assumption": 1.0,
                            "review_work_units_per_operation_assumption": review_weight,
                            "planning_work_units_per_ms_assumption": plan_weight,
                            "method": method,
                            "recomputes_observed_or_expected": f"{method_recomputes:.2f}",
                            "review_operations_observed": reviews[method],
                            "planning_ms_measured_sum_of_five_case_medians": (
                                f"{planning_ms[method]:.6f}"
                            ),
                            "recomputation_cost_assumption": f"{compute_cost:.4f}",
                            "review_cost_assumption": f"{review_cost:.4f}",
                            "planning_cost_using_assumed_rate": f"{planning_cost:.4f}",
                            "total_hypothetical_work_units": f"{total:.4f}",
                            "gamo_vs_dag_preference_under_assumptions": (
                                "GAMO-CA"
                                if totals.get("GAMO-CA", float("inf"))
                                < totals.get("Conventional DAG Incremental", float("inf"))
                                else "DAG Incremental"
                            ),
                        }
                    )
                # The preference field is resolved below after all three totals are known.
                for item in rows[-len(METHODS) :]:
                    item["gamo_vs_dag_preference_under_assumptions"] = (
                        "GAMO-CA"
                        if totals["GAMO-CA"] < totals["Conventional DAG Incremental"]
                        else "DAG Incremental"
                    )
    return rows, thresholds


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def render_break_even(thresholds: list[dict[str, Any]]) -> str:
    """Render the assumed break-even planning rate with a standard-library SVG."""
    width, height = 760, 440
    left, right, top, bottom = 78, 28, 46, 72
    plot_w, plot_h = width - left - right, height - top - bottom
    y_values = [
        float(row["break_even_planning_work_units_per_ms_per_recompute_work_unit"])
        for row in thresholds
    ]
    y_max = max(y_values) * 1.15
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
        element = ET.SubElement(svg, tag, {k.replace("_", "-"): str(v) for k, v in attrs.items()})
        element.text = text

    add("rect", width="100%", height="100%", fill="white")
    add(
        "text",
        "When does planner overhead outweigh avoided recomputation?",
        x=width / 2,
        y=26,
        font_family="Arial,sans-serif",
        font_size=16,
        font_weight=700,
        text_anchor="middle",
        fill="#0f172a",
    )
    for tick in range(5):
        fraction = tick / 4
        y = top + plot_h * (1 - fraction)
        value = y_max * fraction
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
    coords: list[tuple[float, float]] = []
    for row in thresholds:
        q = float(row["review_branches_resolved_as_material_fraction_assumption"])
        value = float(row["break_even_planning_work_units_per_ms_per_recompute_work_unit"])
        x = left + plot_w * q
        y = top + plot_h * (1 - value / y_max)
        coords.append((x, y))
        add("circle", cx=f"{x:.1f}", cy=f"{y:.1f}", r=5, fill="#0f766e")
        add(
            "text",
            f"{value:.3f}",
            x=f"{x:.1f}",
            y=f"{y - 11:.1f}",
            font_size=10,
            text_anchor="middle",
            fill="#0f766e",
        )
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    add("polyline", points=points, fill="none", stroke="#0f766e", stroke_width=3)
    add("line", x1=left, y1=top + plot_h, x2=width - right, y2=top + plot_h, stroke="#64748b")
    add("line", x1=left, y1=top, x2=left, y2=top + plot_h, stroke="#64748b")
    add(
        "text",
        "Fraction of four uncertain branches confirmed as material (assumption)",
        x=left + plot_w / 2,
        y=height - 22,
        font_size=11,
        text_anchor="middle",
        fill="#334155",
    )
    add(
        "text",
        "Break-even assumed planner cost / recompute cost",
        x=18,
        y=top + plot_h / 2,
        transform=f"rotate(-90 18 {top + plot_h / 2})",
        font_size=11,
        text_anchor="middle",
        fill="#334155",
    )
    return ET.tostring(svg, encoding="unicode")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    result_path = args.source_dir / "results.csv"
    decision_path = args.source_dir / "node_decisions.csv"
    result_rows, decision_rows = read_csv(result_path), read_csv(decision_path)
    validate_inputs(result_rows, decision_rows)
    accounting = scenario_accounting(result_rows, decision_rows)
    sensitivity, thresholds = make_sensitivity(result_rows)
    write_csv(args.output_dir / "scenario-accounting.csv", accounting)
    write_csv(args.output_dir / "cost-sensitivity.csv", sensitivity)
    write_csv(args.output_dir / "break-even.csv", thresholds)
    (args.output_dir / "break-even.svg").write_text(render_break_even(thresholds), encoding="utf-8")
    manifest = {
        "audit": "R1.2",
        "classification": "AUDIT_OF_EXISTING_R1_1_OUTPUTS; NOT_A_NEW_BENCHMARK_RUN",
        "source_results_sha256": sha256(result_path),
        "source_decisions_sha256": sha256(decision_path),
        "source_result_rows": len(result_rows),
        "source_decision_rows": len(decision_rows),
        "source_seed": result_rows[0]["seed"],
        "inputs_are_read_only": True,
        "assumptions": {
            "recomputation_work_units_per_operation": 1,
            "review_work_units_per_operation": [0.25, 1, 4],
            "planning_work_units_per_ms": [0, 0.01, 0.1, 1],
            "fraction_of_four_uncertain_branches_resolved_as_material": [0, 0.25, 0.5, 0.75, 1],
            "conditional_asset_recomputes_if_all_four_branches_are_material": 8,
        },
        "timing_note": (
            "Planning values sum the five saved scenario medians. This is descriptive, "
            "not an independent repeated workload sample."
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"R1.2 audit accepted {len(result_rows)} saved R1.1 rows; no R1.1 file was written.")
    totals = {
        method: sum(
            int(row["recompute_operations"]) for row in result_rows if row["method"] == method
        )
        for method in METHODS
    }
    conditional = sum(row["conditional_recompute_upper_bound"] for row in accounting)
    print(f"Immediate recomputations: GAMO-CA={totals['GAMO-CA']}; DAG={totals[METHODS[1]]}.")
    print(f"Review-gated conditional AssetVersions: {conditional}.")
    print(f"Outputs: {args.output_dir}")


if __name__ == "__main__":
    main()
