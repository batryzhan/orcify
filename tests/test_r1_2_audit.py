from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_r1_1 import (  # noqa: E402
    METHODS,
    make_sensitivity,
    read_csv,
    render_break_even,
    scenario_accounting,
    validate_inputs,
)


def _saved_r1_1():
    source = ROOT / "docs" / "research" / "r1_1-pilot"
    results = read_csv(source / "results.csv")
    decisions = read_csv(source / "node_decisions.csv")
    validate_inputs(results, decisions)
    return results, decisions


def test_r1_1_hard_recompute_obligations_are_not_reviewed_by_gamo():
    results, decisions = _saved_r1_1()
    audited = scenario_accounting(results, decisions)
    assert all(row["oracle_required_hard_not_recomputed"] == "" for row in audited)
    assert all(row["oracle_required_hard_recomputes"] > 0 for row in audited)


def test_immediate_counts_separate_from_review_gated_future_work():
    results, decisions = _saved_r1_1()
    audited = scenario_accounting(results, decisions)
    assert sum(row["gamo_immediate_recomputes"] for row in audited) == 12
    assert sum(row["dag_immediate_recomputes"] for row in audited) == 21
    assert sum(row["conditional_recompute_upper_bound"] for row in audited) == 8
    assert sum(row["gamo_if_every_reviewed_asset_is_recomputed"] for row in audited) == 20
    assert sum(row["hard_descendants_held_for_review"] != "" for row in audited) == 4


def test_sensitivity_marks_q_and_cost_weights_as_hypothetical_inputs():
    results, _ = _saved_r1_1()
    rows, thresholds = make_sensitivity(results)
    assert len(rows) == 5 * 3 * 4 * len(METHODS)
    assert [
        row["review_branches_resolved_as_material_fraction_assumption"] for row in thresholds
    ] == [
        0.0,
        0.25,
        0.5,
        0.75,
        1.0,
    ]
    assert thresholds[0]["gamo_expected_recomputes_assumption"] == 12.0
    assert thresholds[-1]["gamo_expected_recomputes_assumption"] == 20.0
    assert float(
        thresholds[0]["break_even_planning_work_units_per_ms_per_recompute_work_unit"]
    ) > float(thresholds[-1]["break_even_planning_work_units_per_ms_per_recompute_work_unit"])
    assert {row["gamo_vs_dag_preference_under_assumptions"] for row in rows} == {
        "GAMO-CA",
        "DAG Incremental",
    }


def test_break_even_chart_is_well_formed_svg():
    results, _ = _saved_r1_1()
    _, thresholds = make_sensitivity(results)
    root = ET.fromstring(render_break_even(thresholds))
    assert root.tag.endswith("svg")
    assert len(root.findall("{http://www.w3.org/2000/svg}circle")) == 5


def test_all_methods_have_saved_rows_for_each_shared_scenario():
    results, _ = _saved_r1_1()
    grouped: dict[str, set[str]] = {}
    for row in results:
        grouped.setdefault(row["scenario"], set()).add(row["method"])
    assert len(grouped) == 5
    assert all(methods == set(METHODS) for methods in grouped.values())
