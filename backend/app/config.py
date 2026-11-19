"""Қолданба конфигурациясы (Pydantic BaseSettings).

Мәндер ``ORCIFY_`` префиксті орта айнымалыларынан және
``backend/.env`` файлынан оқылады (git-ке коммиттелмейді).
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

    # Жергілікті LLM: Unsloth Studio, OpenAI-үйлесімді API.
    llm_base_url: HttpUrl = HttpUrl("http://127.0.0.1:8888/v1")
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "unsloth/gemma-4-E4B-it-GGUF"
    # Әр желілік операцияға httpx тайм-ауты (connect/read/write).
    llm_timeout_s: float = Field(default=120.0, gt=0)
    # Барлық қайталау әрекеттерімен ``structured()`` шақыруының жалпы дедлайны.
    llm_deadline_s: float = Field(default=180.0, gt=0)
    llm_max_tokens: int = Field(default=2048, gt=0)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_attempts: int = Field(default=2, ge=1, le=5)

    # Smart Routing: осы шектен төмен нәтиже сенімсіз деп белгіленеді.
    intent_min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)

    # Тапсырма жадынан мәтіні жойылғанға дейін SSE-ағынға қосылуды
    # қанша секунд күтеді.
    task_ttl_s: float = Field(default=300.0, gt=0)

    # Дайын .docx жүктеу үшін жадта қанша секунд сақталады.
    document_ttl_s: float = Field(default=3600.0, gt=0)
    # «Бүгін» үшін уақыт белдеуі (Қазақстан — UTC+5).
    tz_offset_hours: int = Field(default=5, ge=-12, le=14)

    # Келісімшарт үлгісіне арналған Орындаушы деректемелері (.env ішінде толтырылады).
    contract_city: str = "Алматы"
    executor_name: str = "____________________"
    executor_bin: str = "____________"
    executor_signatory: str = "____________________"
    executor_basis: str = "Жарғы"

    # --- MCP-серверлер (app/mcp/manager.py ішінде тіркеледі) ---
    mcp_timeout_s: float = Field(default=60.0, gt=0)
    # Жергілікті қаржылық MCP (stdio, дәл осы интерпретатормен іске қосылады).
    finance_mcp_enabled: bool = True
    finance_mcp_script: Path = BACKEND_DIR.parent / "mcp_servers" / "local_finance_server" / "server.py"

    # --- Orcify Jira: өз жергілікті трекері (in-process MCP "orcify_jira") ---
    jira_board_path: Path | None = BACKEND_DIR / "var" / "jira_board.json"
    jira_project_key: str = Field(default="ORC", pattern=r"^[A-Z][A-Z0-9]{1,9}$")

    # --- Awesome Posts: Instagram-посттарының жергілікті рендері (in-process MCP "awesome_posts") ---
    assets_dir: Path = BACKEND_DIR / "assets"
    posts_dir: Path = BACKEND_DIR / "var" / "posts"
    default_post_handle: str = "@orcify"

    # --- «Қаржы» терезесі: бюджеттер және PDF-есептер мұрағаты (жергілікті) ---
    finance_reports_dir: Path = BACKEND_DIR / "var" / "finance_reports"
    finance_budgets_path: Path | None = BACKEND_DIR / "var" / "finance_budgets.json"

    # --- Telegram-бот (n8n орнына автоматтандыру арнасы) ---
    # Токен TELEGRAM_BOT_API_KEY-ден оқылады (backend/.env ішінде солай аталған).
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
