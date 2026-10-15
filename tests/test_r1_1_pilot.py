from __future__ import annotations

from gamo_ca.models import Action

from scripts.r1_1_pilot import (
    METHODS,
    PLANNERS,
    PlanResult,
    correctness_oracle,
    make_scenarios,
)


def test_pilot_inputs_are_repeatable_for_a_fixed_seed() -> None:
    first = make_scenarios(20261014)
    second = make_scenarios(20261014)

    assert [scenario.graph.snapshot_hash for scenario in first] == [
        scenario.graph.snapshot_hash for scenario in second
    ]
    assert [scenario.event for scenario in first] == [scenario.event for scenario in second]


def test_every_method_meets_the_predeclared_correctness_oracle() -> None:
    for scenario in make_scenarios():
        for method in METHODS:
            evaluation = correctness_oracle(scenario, PLANNERS[method](scenario))
            assert evaluation.correct, (scenario.name, method, evaluation.failures)
            assert evaluation.approval_leaks == ()


def test_requirement_change_invalidates_all_exact_requirement_approvals() -> None:
    scenario = next(item for item in make_scenarios() if item.name == "approval_invalidation")

    for method in METHODS:
        evaluation = correctness_oracle(scenario, PLANNERS[method](scenario))
        assert evaluation.eligible_asset_ids == ()
        assert evaluation.review_operations == len(scenario.asset_ids)


def test_keep_does_not_preserve_approval_after_requirement_snapshot_changes() -> None:
    scenario = next(item for item in make_scenarios() if item.name == "approval_invalidation")
    output = PLANNERS[METHODS[2]](scenario)
    evaluation = correctness_oracle(scenario, output)

    assert output.actions["moodboard"] == Action.KEEP
    assert "moodboard" not in evaluation.eligible_asset_ids
    assert "moodboard" in scenario.oracle.approvals_invalidated_by_event


def test_asset_version_change_keeps_unrelated_exact_approval_eligible_for_selective_methods() -> (
    None
):
    scenario = next(item for item in make_scenarios() if item.name == "asset_version_update")

    dag = correctness_oracle(scenario, PLANNERS[METHODS[1]](scenario))
    gamo = correctness_oracle(scenario, PLANNERS[METHODS[2]](scenario))

    assert "approved_copy" in dag.eligible_asset_ids
    assert "approved_copy" in gamo.eligible_asset_ids
    assert "source_photo" not in gamo.eligible_asset_ids


def test_soft_unknown_cannot_be_kept_and_hard_dependency_cannot_be_kept() -> None:
    scenario = next(item for item in make_scenarios() if item.name == "brand_guideline_change")
    output = PLANNERS[METHODS[2]](scenario)

    broken_review = dict(output.actions)
    broken_review["layout_review"] = Action.KEEP
    assert not correctness_oracle(scenario, PlanResult(broken_review, output.reasons)).correct

    broken_recompute = dict(output.actions)
    broken_recompute["palette_art"] = Action.KEEP
    assert not correctness_oracle(scenario, PlanResult(broken_recompute, output.reasons)).correct


def test_all_hard_fanout_has_no_selective_recomputation_advantage() -> None:
    scenario = next(
        item for item in make_scenarios() if item.name == "all_hard_fanout_no_advantage"
    )
    counts = {
        method: correctness_oracle(scenario, PLANNERS[method](scenario)).recompute_operations
        for method in METHODS
    }

    assert len(set(counts.values())) == 1
