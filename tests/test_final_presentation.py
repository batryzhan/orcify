"""Presentation fixture and original research-artifact preservation checks."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_presentation import FIXTURE, LOCK, fixture_json, research_hashes  # noqa: E402


def test_prior_research_artifacts_match_presentation_preservation_lock() -> None:
    assert research_hashes() == json.loads(LOCK.read_text(encoding="utf-8"))


def test_offline_fixture_matches_pure_planner_and_original_r1_1_decisions() -> None:
    # fixture_json verifies every action against the saved R1.1 CSV before export.
    saved = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert saved == json.loads(fixture_json())
    assert saved["classification"] == "SIMULATED_OFFLINE_PREVIEW_NOT_EXECUTION"
    assert saved["seed"] == 20261014
