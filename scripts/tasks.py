"""Portable developer commands: python scripts/tasks.py --help."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def export_schemas(check: bool) -> None:
    from gamo_ca.events import GraphChangePayload
    from gamo_ca.models import DOMAIN_TYPES
    from gamo_ca.planner import Plan
    from pydantic import TypeAdapter

    from services.api.app.artifact_schemas import (
        ArtifactCreateRequest,
        ArtifactEligibilityResult,
        DependencyVersion,
        ExecutionAttemptStartRequest,
        ExecutionRunCreateRequest,
        ExecutionTransitionRequest,
        ProvenanceInput,
    )

    destination = ROOT / "docs" / "api" / "schemas"
    destination.mkdir(parents=True, exist_ok=True)
    artifact_models = (
        ArtifactCreateRequest,
        ArtifactEligibilityResult,
        DependencyVersion,
        ExecutionAttemptStartRequest,
        ExecutionRunCreateRequest,
        ExecutionTransitionRequest,
        ProvenanceInput,
    )
    for model in (*DOMAIN_TYPES, Plan, GraphChangePayload, *artifact_models):
        schema = TypeAdapter(model).json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
        path = destination / f"{model.__name__}.json"
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                raise SystemExit(f"Schema drift: {path}; run schemas and review changes")
        else:
            path.write_text(text, encoding="utf-8")
    from gamo_ca.fixtures import change_event, toy_graph
    from gamo_ca.planner import Policy, plan_change

    fixture_path = ROOT / "packages" / "contracts" / "fixtures" / "plan.json"
    fixture = json.loads(
        TypeAdapter(Plan).dump_json(plan_change(toy_graph(), change_event(), Policy()))
    )
    if check:
        if (
            not fixture_path.exists()
            or json.loads(fixture_path.read_text(encoding="utf-8")) != fixture
        ):
            raise SystemExit("Cross-language plan fixture drift; run schemas and review")
    else:
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")


def demo() -> None:
    from gamo_ca.fingerprints import canonical
    from gamo_ca.fixtures import change_event, toy_graph
    from gamo_ca.planner import Policy, plan_change

    graph = toy_graph()
    print(
        json.dumps(
            {
                "status": "SIMULATED",
                "publication": "NOT_IMPLEMENTED",
                "scenarios": [
                    canonical(plan_change(graph, change_event(target, graph), Policy()))
                    for target in ("slogan", "note")
                ],
            },
            indent=2,
        )
    )


def verify_test_gate() -> None:
    # A deliberate broken test must produce pytest's test-failure code (1).
    # Temporary file is outside the checkout and removed automatically.
    with tempfile.TemporaryDirectory(prefix="orcify-ci-gate-") as directory:
        path = Path(directory) / "test_deliberate_failure.py"
        path.write_text("def test_ci_failure_gate():\n    assert False\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 1 or "1 failed" not in result.stdout:
            raise SystemExit(
                f"Broken-test gate failed to reject test: {result.stdout}{result.stderr}"
            )
    print("Verified: deliberately broken test is rejected (exit 1)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "check-python",
            "test",
            "lint",
            "format",
            "schemas",
            "demo",
            "verify-test-gate",
        ),
    )
    parser.add_argument("--check", action="store_true", help="reject generated schema drift")
    args = parser.parse_args()
    if args.command in ("check-python", "lint"):
        run(sys.executable, "-m", "ruff", "check", ".")
        run(sys.executable, "-m", "ruff", "format", "--check", ".")
        run(sys.executable, "-m", "mypy")
    if args.command in ("check-python", "test"):
        run(sys.executable, "-m", "pytest")
    elif args.command == "format":
        run(sys.executable, "-m", "ruff", "check", "--fix", ".")
        run(sys.executable, "-m", "ruff", "format", ".")
    elif args.command == "schemas":
        export_schemas(args.check)
    elif args.command == "demo":
        demo()
    elif args.command == "verify-test-gate":
        verify_test_gate()


if __name__ == "__main__":
    main()
