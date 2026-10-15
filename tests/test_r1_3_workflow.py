from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gamo_ca.models import AssetVersion  # noqa: E402
from r1_1_pilot import make_scenarios  # noqa: E402
from r1_3_workflow import (  # noqa: E402
    BRANCHES,
    final_actions,
    human_review_counts,
    worksheet_rows,
)


def test_all_sixteen_synthetic_review_outcomes_resolve_and_replan_safely():
    scenarios = make_scenarios()
    combinations = list(itertools.product((False, True), repeat=4))
    assert len(combinations) == 16
    for outcomes in combinations:
        initial_gamo, final_gamo = final_actions(scenarios, outcomes, aware=False)
        initial_dag, final_dag = final_actions(scenarios, outcomes, aware=True)
        for (scenario_name, _, root_id, _), material in zip(BRANCHES, outcomes, strict=True):
            child = next(
                edge.dependent_id
                for edge in next(s for s in scenarios if s.name == scenario_name).graph.active_edges
                if edge.upstream_id == root_id and edge.strength.value == "HARD"
            )
            expected = "RECOMPUTE" if material else "KEEP"
            assert final_gamo[scenario_name][root_id].value == expected
            assert final_gamo[scenario_name][child].value == expected
            assert final_dag[scenario_name] == final_gamo[scenario_name]
        assert sum(
            action.value == "RECOMPUTE"
            for scenario in scenarios
            for node_id, action in final_gamo[scenario.name].items()
            if node_id
            in {node.id for node in scenario.graph.nodes if isinstance(node, AssetVersion)}
        ) == 12 + 2 * sum(outcomes)
        assert (
            sum(
                action.value == "RECOMPUTE"
                for scenario in scenarios
                for node_id, action in initial_gamo[scenario.name].items()
                if node_id
                in {node.id for node in scenario.graph.nodes if isinstance(node, AssetVersion)}
            )
            == 12
        )
        assert (
            sum(
                action.value == "RECOMPUTE"
                for scenario in scenarios
                for node_id, action in initial_dag[scenario.name].items()
                if node_id
                in {node.id for node in scenario.graph.nodes if isinstance(node, AssetVersion)}
            )
            == 12
        )


def test_review_counters_separate_resolution_and_exact_approval_work():
    scenarios = make_scenarios()
    for outcomes in itertools.product((False, True), repeat=4):
        _, final = final_actions(scenarios, outcomes, aware=False)
        relevance_reviews, approval_reviews, unique_assets = human_review_counts(scenarios, final)
        assert relevance_reviews == 4
        assert approval_reviews == 22 + 2 * int(outcomes[2])
        assert unique_assets == 23 + int(outcomes[2])


def test_reviewer_worksheet_has_blank_labels_and_no_algorithm_decisions():
    rows = worksheet_rows(make_scenarios())
    assert len(rows) == 25
    assert {row["case_code"] for row in rows} == {"S01", "S02", "S03", "S04", "S05"}
    assert all(
        row["reviewer_impact_label_RECOMPUTE_REVIEW_KEEP_SOURCE_CHANGE"] == "" for row in rows
    )
    assert all(row["reviewer_approval_label_REAPPROVE_UNCHANGED_UNCERTAIN"] == "" for row in rows)
    assert all(row["reviewer_reason"] == "" for row in rows)
    text = " ".join(str(value) for row in rows for value in row.values()).lower()
    assert "gamo-ca" not in text
    assert "recompute;" not in text
