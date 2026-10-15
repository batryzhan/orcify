"""Validate two completed R1.3 worksheets and compare labels to saved algorithms.

This command never edits the source worksheets or prior R1.1-R1.3 artifacts. It
refuses incomplete data and does not resolve disagreement. Use actual, independently
completed reviewer files only; test fixtures are not research observations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from r1_1_pilot import make_scenarios  # noqa: E402
from r1_3_workflow import field_aware_dag_plan  # noqa: E402

WORKFLOW_DIR = ROOT / "docs" / "research" / "r1_3-workflow"
PILOT_DIR = ROOT / "docs" / "research" / "r1_1-pilot"
SCENARIO_TO_CASE = {
    "slogan_change": "S01",
    "brand_guideline_change": "S02",
    "asset_version_update": "S03",
    "approval_invalidation": "S04",
    "all_hard_fanout_no_advantage": "S05",
}
IMPACT_LABELS = {"RECOMPUTE", "REVIEW", "KEEP", "SOURCE_CHANGE"}
APPROVAL_LABELS = {"REAPPROVE", "UNCHANGED", "UNCERTAIN"}
REVIEW_COLUMNS = {
    "case_code",
    "asset_to_label",
    "reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE",
    "reviewer_approval_label_REAPPROVE_UNCHANGED_UNCERTAIN",
    "reviewer_reason",
    "reviewer_confidence_1_to_5",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_key(row: dict[str, str]) -> tuple[str, str]:
    return row["case_code"], row["asset_to_label"]


def validate_review(
    path: Path, expected: set[tuple[str, str]]
) -> dict[tuple[str, str], dict[str, str]]:
    rows = read_csv(path)
    if not rows or not REVIEW_COLUMNS.issubset(rows[0]):
        missing = sorted(REVIEW_COLUMNS - set(rows[0] if rows else []))
        raise ValueError(f"{path}: missing rows or required columns: {missing}")
    indexed: dict[tuple[str, str], dict[str, str]] = {}
    for line, row in enumerate(rows, 2):
        key = row_key(row)
        if key in indexed:
            raise ValueError(f"{path}:{line}: duplicate asset row {key}")
        if key not in expected:
            raise ValueError(f"{path}:{line}: unexpected asset row {key}")
        impact = row["reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE"].strip()
        approval = row["reviewer_approval_label_REAPPROVE_UNCHANGED_UNCERTAIN"].strip()
        if impact not in IMPACT_LABELS:
            raise ValueError(f"{path}:{line}: invalid or blank impact label")
        if approval not in APPROVAL_LABELS:
            raise ValueError(f"{path}:{line}: invalid or blank approval label")
        if not row["reviewer_reason"].strip():
            raise ValueError(f"{path}:{line}: reviewer reason is required")
        try:
            confidence = int(row["reviewer_confidence_1_to_5"])
        except ValueError as exc:
            raise ValueError(f"{path}:{line}: confidence must be an integer from 1 to 5") from exc
        if confidence not in range(1, 6):
            raise ValueError(f"{path}:{line}: confidence must be an integer from 1 to 5")
        indexed[key] = row
    missing_keys = expected - set(indexed)
    if missing_keys:
        raise ValueError(
            f"{path}: incomplete worksheet; missing {len(missing_keys)} rows: "
            f"{sorted(missing_keys)}"
        )
    return indexed


def build_algorithm_labels() -> dict[str, dict[tuple[str, str], dict[str, Any]]]:
    decisions = read_csv(PILOT_DIR / "node_decisions.csv")
    output: dict[str, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)
    for row in decisions:
        if row["node_type"] != "AssetVersion":
            continue
        key = (SCENARIO_TO_CASE[row["scenario"]], row["node_id"])
        output[row["method"]][key] = {
            "impact": row["action"],
            "eligible": row["eligible_after_change"].lower() == "true",
        }

    scenarios = make_scenarios(20261014)
    for scenario in scenarios:
        actions = field_aware_dag_plan(scenario)
        case_code = SCENARIO_TO_CASE[scenario.name]
        # This field-aware baseline implements impact decisions only. It does not
        # implement approval state or publication eligibility.
        for node in scenario.graph.nodes:
            if node.id in actions and node.__class__.__name__ == "AssetVersion":
                output["Field-aware DAG"][(case_code, node.id)] = {
                    "impact": actions[node.id].value,
                    "eligible": None,
                }
    return dict(output)


def metrics(
    keys: list[tuple[str, str]],
    review: dict[tuple[str, str], dict[str, str]],
    predictions: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    compared = [
        key
        for key in keys
        if key in predictions
        and review[key]["reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE"].strip()
        != "SOURCE_CHANGE"
    ]
    correct = sum(
        predictions[key]["impact"]
        == review[key]["reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE"].strip()
        for key in compared
    )
    unnecessary = sum(
        predictions[key]["impact"] == "RECOMPUTE"
        and review[key]["reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE"].strip()
        == "KEEP"
        for key in compared
    )
    recompute_when_reviewer_requests_review = sum(
        predictions[key]["impact"] == "RECOMPUTE"
        and review[key]["reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE"].strip()
        == "REVIEW"
        for key in compared
    )
    missed = sum(
        predictions[key]["impact"] != "RECOMPUTE"
        and review[key]["reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE"].strip()
        == "RECOMPUTE"
        for key in compared
    )
    safety_assessed = [
        key for key in keys if key in predictions and predictions[key]["eligible"] is not None
    ]
    safety = sum(
        predictions[key]["eligible"] is True
        and review[key]["reviewer_approval_label_REAPPROVE_UNCHANGED_UNCERTAIN"].strip()
        != "UNCHANGED"
        for key in keys
        if key in predictions
    )
    confusion: Counter[str] = Counter()
    for key in compared:
        expected = review[key]["reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE"].strip()
        confusion[f"{expected}->{predictions[key]['impact']}"] += 1
    return {
        "impact_rows_scored": len(compared),
        "exact_action_correct": correct,
        "exact_action_accuracy": correct / len(compared) if compared else None,
        "unnecessary_recomputations": unnecessary,
        "recomputations_where_reviewer_label_is_review": recompute_when_reviewer_requests_review,
        "missed_required_recomputations": missed,
        "approval_safety_violations": safety,
        "approval_safety_assessed_rows": len(safety_assessed),
        "approval_safety_unassessed_rows": len([key for key in keys if key in predictions])
        - len(safety_assessed),
        "approval_safety_scope": (
            "shared R1.1 correctness-oracle eligibility output is true while reviewer "
            "approval label is REAPPROVE or UNCERTAIN; not a real publication attempt"
        ),
        "confusion_counts": dict(sorted(confusion.items())),
    }


def analyze(
    first: Path,
    second: Path,
    output_dir: Path,
    reviewer_codes: tuple[str, str] = ("reviewer-1", "reviewer-2"),
) -> dict[str, Any]:
    worksheet = read_csv(WORKFLOW_DIR / "review-worksheet.csv")
    expected = {row_key(row) for row in worksheet if row["asset_role"] == "DERIVED_ASSET"}
    reviewer_a = validate_review(first, expected)
    reviewer_b = validate_review(second, expected)
    if first.resolve() == second.resolve():
        raise ValueError("reviewers must provide two distinct worksheet files")
    if not all(reviewer_codes) or reviewer_codes[0] == reviewer_codes[1]:
        raise ValueError("reviewer codes must be present and distinct")
    disagreements = []
    agreements = {}
    for key in sorted(expected):
        a, b = reviewer_a[key], reviewer_b[key]
        impact_a = a["reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE"].strip()
        impact_b = b["reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE"].strip()
        approval_a = a["reviewer_approval_label_REAPPROVE_UNCHANGED_UNCERTAIN"].strip()
        approval_b = b["reviewer_approval_label_REAPPROVE_UNCHANGED_UNCERTAIN"].strip()
        if impact_a != impact_b or approval_a != approval_b:
            disagreements.append(
                {
                    "case_code": key[0],
                    "asset_to_label": key[1],
                    "reviewer_1_impact": impact_a,
                    "reviewer_2_impact": impact_b,
                    "reviewer_1_approval": approval_a,
                    "reviewer_2_approval": approval_b,
                    "status": "UNRESOLVED; no label selected",
                }
            )
        else:
            agreements[key] = a

    algorithms = build_algorithm_labels()
    scored: dict[str, Any] = {}
    for name, predictions in algorithms.items():
        scored[name] = {
            "reviewer_1": metrics(sorted(expected), reviewer_a, predictions),
            "reviewer_2": metrics(sorted(expected), reviewer_b, predictions),
            "agreement_rows_only": metrics(sorted(agreements), agreements, predictions),
        }
    output_dir.mkdir(parents=True, exist_ok=False)
    with (output_dir / "disagreements.csv").open("w", newline="", encoding="utf-8") as stream:
        columns = [
            "case_code",
            "asset_to_label",
            "reviewer_1_impact",
            "reviewer_2_impact",
            "reviewer_1_approval",
            "reviewer_2_approval",
            "status",
        ]
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(disagreements)
    report = {
        "status": "HUMAN_REVIEW_IMPORTED",
        "source_worksheets": [
            {
                "reviewer_code": reviewer_codes[0],
                "path": str(first),
                "sha256": file_hash(first),
            },
            {
                "reviewer_code": reviewer_codes[1],
                "path": str(second),
                "sha256": file_hash(second),
            },
        ],
        "worksheet_rows_expected": len(expected),
        "agreement_rows": len(agreements),
        "unresolved_disagreement_rows": len(disagreements),
        "disagreements_file": "disagreements.csv",
        "algorithm_metrics": scored,
        "limitations": [
            "Agreement-only metrics exclude contested rows; no adjudication is implied.",
            "Conventional DAG is the saved R1.1 baseline; Field-aware DAG is independently "
            "implemented in R1.3.",
            "Field-aware DAG has no approval eligibility; its safety metric is unassessed.",
            "Eligibility checks use reviewer approval labels, not actual publication attempts.",
            "This comparison describes five synthetic workflows; it is not a benchmark or "
            "general safety claim.",
        ],
    }
    (output_dir / "human-validation-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reviewer-1", type=Path, required=True, help="first completed worksheet copy"
    )
    parser.add_argument(
        "--reviewer-2", type=Path, required=True, help="second completed worksheet copy"
    )
    parser.add_argument("--reviewer-1-code", required=True, help="neutral code, not a full name")
    parser.add_argument("--reviewer-2-code", required=True, help="neutral code, not a full name")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="new directory for imported analysis"
    )
    args = parser.parse_args()
    print(
        json.dumps(
            analyze(
                args.reviewer_1,
                args.reviewer_2,
                args.output_dir,
                (args.reviewer_1_code, args.reviewer_2_code),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
