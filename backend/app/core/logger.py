"""Безопасный логгер (Zero-PII Logging).

В лог попадают только поля из белого списка ``ALLOWED_FIELDS``:
идентификаторы, хэши, домен, тайминги и статусы. Попытка залогировать
любое другое поле (например, ``text`` или ``client_name``) — ошибка
разработчика, поэтому поднимается ``ValueError``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from enum import Enum
from typing import Final

ALLOWED_FIELDS: Final = frozenset(
    {
        "session_id",
        "request_id",
        "task_id",
        "payload_hash",
        "domain",
        "confidence",
        "low_confidence",
        "latency_ms",
        "status",
        "stage",
        "attempt",
        "attempts",
        "error_type",
        "error_code",
        "http_status",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "degraded",
        "server",
        "document_id",
        "size_bytes",
        "outcome",
        "missing_count",
        "invalid_count",
    }
)

# Строковые значения длиннее этого — подозрительны (вероятно, пользовательский текст).
MAX_STRING_VALUE_LEN: Final = 128

LogValue = str | int | float | bool | Enum | None


def payload_hash(data: str | bytes) -> str:
    """SHA-256 хэш артефакта для корреляции в логах без раскрытия содержимого."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def _normalize(name: str, value: LogValue) -> str | int | float | bool | None:
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, str) and len(value) > MAX_STRING_VALUE_LEN:
        raise ValueError(f"Log field '{name}' is too long; raw text must not be logged")
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"Log field '{name}' has unsupported type {type(value).__name__}")
    return value


class SafeLogger:
    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _emit(self, level: int, event: str, fields: dict[str, LogValue]) -> None:
        unknown = set(fields) - ALLOWED_FIELDS
        if unknown:
            raise ValueError(f"Fields not allowed in logs: {sorted(unknown)}")
        record = {"event": event} | {k: _normalize(k, v) for k, v in fields.items()}
        self._logger.log(level, json.dumps(record, ensure_ascii=False))

    def info(self, event: str, **fields: LogValue) -> None:
        self._emit(logging.INFO, event, fields)

    def warning(self, event: str, **fields: LogValue) -> None:
        self._emit(logging.WARNING, event, fields)

    def error(self, event: str, **fields: LogValue) -> None:
        self._emit(logging.ERROR, event, fields)


def get_logger(name: str) -> SafeLogger:
    return SafeLogger(name)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
