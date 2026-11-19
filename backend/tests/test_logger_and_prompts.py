from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from app.config import BACKEND_DIR
from app.core.logger import get_logger, payload_hash
from app.core.prompts import PromptLoader, PromptNotFoundError
from app.schemas.intent import DomainEnum


def test_logger_rejects_non_whitelisted_fields() -> None:
    log = get_logger("test")
    with pytest.raises(ValueError, match="not allowed"):
        log.info("bad", text="Иванов Иван, ЖСН 900101300017")


def test_logger_rejects_long_strings() -> None:
    with pytest.raises(ValueError, match="too long"):
        get_logger("test").info("bad", status="x" * 500)


def test_logger_emits_json(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="test"):
        get_logger("test").info("ok", domain=DomainEnum.LEGAL, latency_ms=42, payload_hash=payload_hash("abc"))
    record = json.loads(caplog.records[-1].getMessage())
    assert record == {"event": "ok", "domain": "Legal", "latency_ms": 42, "payload_hash": payload_hash("abc")}


def test_payload_hash_is_sha256() -> None:
    assert payload_hash("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_prompt_loader_reads_real_prompts() -> None:
    loader = PromptLoader(BACKEND_DIR / "prompts")
    assert "Legal" in loader.load("intent_classifier")
    extractor = loader.load("legal_extractor", today="2026-11-18")
    assert "2026-11-18" in extractor and "$today" not in extractor


def test_prompt_loader_missing_variable_fails() -> None:
    with pytest.raises(KeyError):
        PromptLoader(BACKEND_DIR / "prompts").load("legal_extractor", other="x")


@pytest.mark.parametrize("name", ["../config", "Intent", "a/b"])
def test_prompt_loader_rejects_bad_names(name: str) -> None:
    with pytest.raises(ValueError):
        PromptLoader(BACKEND_DIR / "prompts").load(name)


def test_prompt_loader_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PromptNotFoundError):
        PromptLoader(tmp_path).load("nope")
