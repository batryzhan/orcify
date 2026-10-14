"""Canonical domain hashing, including scope and producer configuration."""

import hashlib
import json
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import cast

from gamo_ca.models import InputRef, Requirement, require_id


def canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("hashing requires timezone")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple | list):
        return [canonical(item) for item in value]
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        if not all(isinstance(key, str) for key in mapping):
            raise ValueError("hash keys must be strings")
        return {str(key): canonical(item) for key, item in mapping.items()}
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"unsupported hash type: {type(value).__name__}")


def fingerprint(value: object) -> str:
    payload = json.dumps(
        canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_id(tenant_id: str, project_id: str, entity_type: str, logical_key: str) -> str:
    """Namespaced deterministic ID; immutable versions use distinct logical keys."""
    for value in (tenant_id, project_id, entity_type, logical_key):
        require_id(value)
    return fingerprint((tenant_id, project_id, entity_type, logical_key))


def input_fingerprint(
    inputs: tuple[InputRef, ...],
    provider: str,
    model: str,
    prompt: str,
    policy: str,
    *,
    tenant_id: str,
    project_id: str,
) -> str:
    require_id(tenant_id)
    require_id(project_id)
    if len({ref.source_id for ref in inputs}) != len(inputs):
        raise ValueError("duplicate inputs")
    ordered_inputs = sorted(inputs, key=lambda ref: ref.source_id)
    return fingerprint(
        {
            "inputs": ordered_inputs,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "provider": provider,
            "model": model,
            "prompt": prompt,
            "policy": policy,
        }
    )


def requirement_fingerprint(requirements: tuple[Requirement, ...]) -> str:
    if len({r.id for r in requirements}) != len(requirements):
        raise ValueError("duplicate requirements")
    return fingerprint(tuple(sorted(requirements, key=lambda r: (r.tenant_id, r.project_id, r.id))))
