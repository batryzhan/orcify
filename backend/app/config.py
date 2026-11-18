"""Конфигурация приложения (Pydantic BaseSettings).

Значения читаются из переменных окружения с префиксом ``ORCIFY_``
и из файла ``backend/.env`` (не коммитится в git).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="ORCIFY_",
        extra="ignore",
    )

    # Локальная LLM: Unsloth Studio, OpenAI-совместимый API.
    llm_base_url: HttpUrl = HttpUrl("http://127.0.0.1:8888/v1")
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "unsloth/gemma-4-E4B-it-GGUF"
    # Тайм-аут httpx на каждую сетевую операцию (connect/read/write).
    llm_timeout_s: float = Field(default=120.0, gt=0)
    # Общий дедлайн на вызов structured() со всеми повторными попытками.
    llm_deadline_s: float = Field(default=180.0, gt=0)
    llm_max_tokens: int = Field(default=2048, gt=0)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_attempts: int = Field(default=2, ge=1, le=5)

    # Smart Routing: ниже этого порога результат помечается как неуверенный.
    intent_min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)

    # Сколько секунд задача ждёт подключения к SSE-стриму, прежде чем
    # её текст будет удалён из памяти.
    task_ttl_s: float = Field(default=300.0, gt=0)

    # Сколько секунд готовый .docx хранится в памяти для скачивания.
    document_ttl_s: float = Field(default=3600.0, gt=0)
    # Часовой пояс для «сегодня» (Казахстан — UTC+5).
    tz_offset_hours: int = Field(default=5, ge=-12, le=14)

    # Реквизиты Исполнителя для шаблона договора (заполняются в .env).
    contract_city: str = "Алматы"
    executor_name: str = "____________________"
    executor_bin: str = "____________"
    executor_signatory: str = "____________________"
    executor_basis: str = "Устава"

    # --- MCP-серверы (регистрируются в app/mcp/manager.py) ---
    mcp_timeout_s: float = Field(default=60.0, gt=0)
    # Локальный финансовый MCP (stdio, запускается этим же интерпретатором).
    finance_mcp_enabled: bool = True
    finance_mcp_script: Path = BACKEND_DIR.parent / "mcp_servers" / "local_finance_server" / "server.py"
    # Внешние MCP: пустой URL = сервер не настроен -> graceful degradation.
    higgsfield_mcp_url: str = ""
    higgsfield_mcp_token: SecretStr = SecretStr("")
    higgsfield_tool: str = "generate_video"
    higgsfield_timeout_s: float = Field(default=300.0, gt=0)
    atlassian_mcp_url: str = ""
    atlassian_mcp_token: SecretStr = SecretStr("")
    atlassian_tool: str = "createJiraIssue"
    atlassian_project_key: str = "MKT"
    n8n_mcp_url: str = ""
    n8n_mcp_token: SecretStr = SecretStr("")
    # Очередь отложенной синхронизации: хранит только анонимизированные payload.
    sync_queue_path: Path = BACKEND_DIR / "var" / "sync_queue.jsonl"

    prompts_dir: Path = BACKEND_DIR / "prompts"
    templates_dir: Path = BACKEND_DIR / "templates"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
