"""Конфигурация приложения (Pydantic BaseSettings).

Значения читаются из переменных окружения с префиксом ``ORCIFY_``
и из файла ``backend/.env`` (не коммитится в git).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="ORCIFY_",
        extra="ignore",
        populate_by_name=True,
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

    # --- Orcify Jira: собственный локальный трекер (in-process MCP "orcify_jira") ---
    jira_board_path: Path | None = BACKEND_DIR / "var" / "jira_board.json"
    jira_project_key: str = Field(default="ORC", pattern=r"^[A-Z][A-Z0-9]{1,9}$")

    # --- Awesome Posts: локальный рендер Instagram-постов (in-process MCP "awesome_posts") ---
    assets_dir: Path = BACKEND_DIR / "assets"
    posts_dir: Path = BACKEND_DIR / "var" / "posts"
    default_post_handle: str = "@orcify"

    # --- Окно «Финансы»: бюджеты и архив PDF-отчётов (локально) ---
    finance_reports_dir: Path = BACKEND_DIR / "var" / "finance_reports"
    finance_budgets_path: Path | None = BACKEND_DIR / "var" / "finance_budgets.json"

    # --- Telegram-бот (канал автоматизации вместо n8n) ---
    # Токен читается из TELEGRAM_BOT_API_KEY (так он назван в backend/.env).
    telegram_bot_token: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("TELEGRAM_BOT_API_KEY", "ORCIFY_TELEGRAM_BOT_TOKEN", "telegram_bot_token"),
    )
    telegram_polling: bool = True
    telegram_api_base: str = "https://api.telegram.org"
    telegram_chats_path: Path | None = BACKEND_DIR / "var" / "telegram_chats.json"
    telegram_max_file_bytes: int = Field(default=5_000_000, gt=0)

    prompts_dir: Path = BACKEND_DIR / "prompts"
    templates_dir: Path = BACKEND_DIR / "templates"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
