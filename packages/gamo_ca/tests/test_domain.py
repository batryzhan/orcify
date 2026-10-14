from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest
from gamo_ca.fingerprints import fingerprint, input_fingerprint, requirement_fingerprint, stable_id
from gamo_ca.fixtures import toy_graph
from gamo_ca.models import DOMAIN_TYPES, AssetVersion, InputRef
from pydantic import TypeAdapter


def test_all_entity_contracts_have_schema_and_round_trip() -> None:
    from gamo_ca.fixtures import entity_examples

    examples = entity_examples()
    assert {type(example) for example in examples} == set(DOMAIN_TYPES)
    for example in examples:
        adapter = TypeAdapter(type(example))
        assert adapter.json_schema()["type"] == "object"
        assert adapter.validate_json(adapter.dump_json(example)) == example


def test_snapshots_are_deeply_immutable() -> None:
    node = toy_graph().nodes[0]
    with pytest.raises(FrozenInstanceError):
        node.content = "mutated"  # type: ignore[misc]  # deliberate mutation attack
    assert isinstance(node.inputs, tuple)
    with pytest.raises(TypeError):
        replace(node, inputs=[])  # type: ignore[arg-type]  # deliberate mutable collection


def test_hashes_are_canonical_and_sensitive_to_versions_and_configuration() -> None:
    graph = toy_graph()
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    refs = (InputRef("r", 1, fingerprint("one")), InputRef("s", 1, fingerprint("two")))
    assert input_fingerprint(
        refs, "mock", "v1", "p1", "policy1", tenant_id="tenant", project_id="project"
    ) == input_fingerprint(
        tuple(reversed(refs)),
        "mock",
        "v1",
        "p1",
        "policy1",
        tenant_id="tenant",
        project_id="project",
    )
    assert input_fingerprint(
        refs, "mock", "v1", "p1", "policy1", tenant_id="tenant", project_id="project"
    ) != input_fingerprint(
        refs, "mock", "v2", "p1", "policy1", tenant_id="tenant", project_id="project"
    )
    requirements = graph.requirements
    assert requirement_fingerprint(requirements) == requirement_fingerprint(
        tuple(reversed(requirements))
    )
    assert requirement_fingerprint(requirements) != requirement_fingerprint(
        (replace(requirements[0], version=2),)
    )
    with pytest.raises(ValueError):
        fingerprint(float("nan"))


def test_invalid_metadata_and_provenance_fail_closed() -> None:
    node = toy_graph().nodes[0]
    with pytest.raises(ValueError, match="timezone"):
        replace(node, created_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="validity"):
        replace(node, valid_to=node.valid_from - timedelta(seconds=1))
    with pytest.raises(ValueError, match="version"):
        replace(node, version=0)
    asset = next(n for n in toy_graph().nodes if isinstance(n, AssetVersion))
    with pytest.raises(ValueError, match="provenance"):
        replace(asset, evidence_ids=())
    assert datetime(2026, 1, 1, tzinfo=UTC).tzinfo is UTC


def test_identifiers_and_input_signatures_are_namespaced() -> None:
    assert stable_id("t", "p", "asset", "copy-v1") == stable_id("t", "p", "asset", "copy-v1")
    assert stable_id("t", "p", "asset", "copy-v1") != stable_id("other", "p", "asset", "copy-v1")
    assert stable_id("t", "p", "asset", "copy-v1") != stable_id("t", "p", "asset", "copy-v2")
    assert input_fingerprint(
        (), "mock", "v1", "p1", "policy1", tenant_id="t", project_id="p"
    ) != input_fingerprint((), "mock", "v1", "p1", "policy1", tenant_id="other", project_id="p")
