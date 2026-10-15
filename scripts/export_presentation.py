"""Export one existing verified fixture; never rerun or overwrite research trials."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

from pydantic import TypeAdapter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from gamo_ca.graph import Graph  # noqa: E402
from gamo_ca.planner import Plan, Policy, plan_change  # noqa: E402
from r1_1_pilot import make_scenarios  # noqa: E402

FIXTURE = ROOT / "apps/web/src/research/demo.json"
LOCK = ROOT / "docs/final-presentation/research-artifact-lock.json"


def research_hashes() -> dict[str, str]:
    paths = sorted((ROOT / "docs/research").glob("r1_[1234]-*/**/*"))
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.is_file()
    }


def fixture_json() -> str:
    scenario = make_scenarios(20261014)[0]
    plan = plan_change(scenario.graph, scenario.event, Policy(version="pilot-policy-v1"))
    with (ROOT / "docs/research/r1_1-pilot/node_decisions.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        saved = {
            row["node_id"]: row["action"]
            for row in csv.DictReader(stream)
            if row["scenario"] == scenario.name and row["method"] == "GAMO-CA"
        }
    if saved != {decision.node_id: decision.action.value for decision in plan.decisions}:
        raise ValueError("current planner differs from saved pilot; inspect before presenting")
    data = {
        "classification": "SIMULATED_OFFLINE_PREVIEW_NOT_EXECUTION",
        "seed": 20261014,
        "scenario": scenario.name,
        "description": scenario.description,
        "asset_ids": scenario.asset_ids,
        "target_id": scenario.event.target_id,
        "before": scenario.graph.node(scenario.event.target_id).content,
        "proposed": scenario.graph.node(scenario.event.target_id).content + " — revised",
        "changed_fields": scenario.event.changed_fields,
        "graph": TypeAdapter(Graph).dump_python(scenario.graph, mode="json"),
        "plan": TypeAdapter(Plan).dump_python(plan, mode="json"),
        "source": "scripts/r1_1_pilot.py / slogan_change; saved R1.1 node_decisions.csv",
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    hashes = research_hashes()
    if LOCK.exists():
        if json.loads(LOCK.read_text(encoding="utf-8")) != hashes:
            raise SystemExit("research artifacts changed; refusing to replace preservation lock")
    elif args.check:
        raise SystemExit("research artifact lock is missing")
    else:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        LOCK.write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    payload = fixture_json()
    if args.check:
        if not FIXTURE.exists() or json.loads(FIXTURE.read_text(encoding="utf-8")) != json.loads(
            payload
        ):
            raise SystemExit("presentation fixture differs; run scripts/export_presentation.py")
    else:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(payload, encoding="utf-8")
    print(f"Verified {len(hashes)} preserved research files; presentation fixture matches planner.")


if __name__ == "__main__":
    main()
