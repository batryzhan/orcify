"""Importer checks use disposable synthetic rows, never research observations."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from import_r1_4_reviews import WORKFLOW_DIR, analyze, validate_review  # noqa: E402


def write_review(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def valid_row(case: str = "S01", asset: str = "copy") -> dict[str, str]:
    return {
        "case_code": case,
        "asset_to_label": asset,
        "reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE": "RECOMPUTE",
        "reviewer_approval_label_REAPPROVE_UNCHANGED_UNCERTAIN": "REAPPROVE",
        "reviewer_reason": "Synthetic importer test fixture only",
        "reviewer_confidence_1_to_5": "3",
    }


def test_validates_complete_review_and_returns_rows(tmp_path: Path) -> None:
    path = tmp_path / "review.csv"
    row = valid_row()
    write_review(path, [row])

    result = validate_review(path, {("S01", "copy")})

    assert result[("S01", "copy")]["reviewer_reason"].startswith("Synthetic")


@pytest.mark.parametrize(
    ("row", "expected", "message"),
    [
        (valid_row(), {("S01", "copy"), ("S01", "other")}, "incomplete worksheet"),
        ({**valid_row(), "reviewer_confidence_1_to_5": "8"}, {("S01", "copy")}, "confidence"),
        (
            {**valid_row(), "reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE": ""},
            {("S01", "copy")},
            "invalid or blank impact",
        ),
    ],
)
def test_rejects_incomplete_or_invalid_review(
    tmp_path: Path, row: dict[str, str], expected: set[tuple[str, str]], message: str
) -> None:
    path = tmp_path / "review.csv"
    write_review(path, [row])

    with pytest.raises(ValueError, match=message):
        validate_review(path, expected)


def test_rejects_duplicate_asset_labels(tmp_path: Path) -> None:
    path = tmp_path / "review.csv"
    row = valid_row()
    write_review(path, [row, row])

    with pytest.raises(ValueError, match="duplicate asset row"):
        validate_review(path, {("S01", "copy")})


def test_analysis_reports_disagreement_without_resolving_it(tmp_path: Path) -> None:
    template = list(csv.DictReader((WORKFLOW_DIR / "review-worksheet.csv").open(encoding="utf-8")))
    derived = [row for row in template if row["asset_role"] == "DERIVED_ASSET"]
    reviewer_rows: list[list[dict[str, str]]] = [[], []]
    for row in derived:
        for index in range(2):
            response = {
                "case_code": row["case_code"],
                "asset_to_label": row["asset_to_label"],
                "reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE": "KEEP",
                "reviewer_approval_label_REAPPROVE_UNCHANGED_UNCERTAIN": "UNCERTAIN",
                "reviewer_reason": "Temporary synthetic importer fixture",
                "reviewer_confidence_1_to_5": "3",
            }
            reviewer_rows[index].append(response)
    reviewer_rows[1][0]["reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE"] = "REVIEW"

    paths = [tmp_path / "r1.csv", tmp_path / "r2.csv"]
    for path, rows in zip(paths, reviewer_rows, strict=True):
        write_review(path, rows)
    report = analyze(paths[0], paths[1], tmp_path / "analysis")

    assert report["agreement_rows"] == 23
    assert report["unresolved_disagreement_rows"] == 1
    assert (
        report["algorithm_metrics"]["Field-aware DAG"]["reviewer_1"][
            "approval_safety_unassessed_rows"
        ]
        == 24
    )
    assert report["algorithm_metrics"]["GAMO-CA"]["reviewer_1"]["approval_safety_violations"] > 0
    disagreement = list(csv.DictReader((tmp_path / "analysis" / "disagreements.csv").open()))
    assert disagreement[0]["status"] == "UNRESOLVED; no label selected"
