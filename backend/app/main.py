"""Точка входа FastAPI.

Запуск: ``uvicorn app.main:app --reload`` из папки ``backend``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_finance,
    routes_health,
    routes_jira,
    routes_legal,
    routes_posts,
    routes_tasks,
    routes_telegram,
)
from app.channels.telegram import TelegramBot
from app.config import Settings, get_settings
from app.core.doc_engine import DocEngine
from app.core.document_store import DocumentStore
from app.core.finance_pdf import FinancePdfRenderer
from app.core.finance_service import FinanceService
from app.core.finance_store import BudgetStore, ReportStore
from app.core.hr_service import HrService
from app.core.jira_store import JiraStore
from app.core.jira_tracker import JiraTracker
from app.core.legal_service import LegalService
from app.core.llm_client import LLMClient, build_http_client
from app.core.logger import configure_logging
from app.core.pipeline import TaskPipeline
from app.core.post_renderer import PostRenderer
from app.core.post_store import PostStore
from app.core.prompts import PromptLoader
from app.core.router import IntentRouter
from app.core.smm_service import SmmService
from app.core.task_store import TaskStore
from app.mcp.manager import MCPServerManager, build_default_manager

# (settings, jira, renderer, posts) -> реестр MCP; тесты подменяют серверы in-process.
McpFactory = Callable[[Settings, JiraStore, PostRenderer, PostStore], MCPServerManager]


def create_app(
    settings: Settings | None = None,
    llm_transport: httpx.AsyncBaseTransport | None = None,
    mcp_factory: McpFactory | None = None,
    telegram_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        http = build_http_client(settings, transport=llm_transport)
        llm = LLMClient(settings, http)
        prompts = PromptLoader(settings.prompts_dir)
        documents = DocumentStore(ttl_s=settings.document_ttl_s)
        jira = JiraStore(settings.jira_board_path, project_key=settings.jira_project_key)
        renderer = PostRenderer(settings.assets_dir, settings.default_post_handle)
        posts = PostStore(settings.posts_dir)
        mcp = (mcp_factory or build_default_manager)(settings, jira, renderer, posts)
        reports = ReportStore(settings.finance_reports_dir)
        budgets = BudgetStore(settings.finance_budgets_path)
        finance = FinanceService(
            llm, prompts, mcp, FinancePdfRenderer(settings.assets_dir / "fonts"), reports, budgets
        )
        legal = LegalService(llm, prompts, DocEngine(settings.templates_dir, settings), documents, settings)
        pipeline = TaskPipeline(
            IntentRouter(llm, prompts, settings),
            legal,
            finance,
            SmmService(llm, prompts, mcp),
            HrService(llm, prompts),
            JiraTracker(mcp),
            posts,
        )
        app.state.llm = llm
        app.state.mcp = mcp
        app.state.legal = legal
        app.state.documents = documents
        app.state.jira = jira
        app.state.posts = posts
        app.state.post_renderer = renderer
        app.state.reports = reports
        app.state.budgets = budgets
        app.state.pipeline = pipeline
        app.state.task_store = TaskStore(ttl_s=settings.task_ttl_s)

        tg_http = httpx.AsyncClient(transport=telegram_transport, timeout=httpx.Timeout(40.0, connect=10.0))
        bot = TelegramBot(settings, tg_http, pipeline, posts, documents, jira, reports)
        app.state.telegram = bot
        polling: asyncio.Task[None] | None = None
        if bot.configured and settings.telegram_polling:
            polling = asyncio.create_task(bot.run_polling())
        try:
            yield
        finally:
            if polling is not None:
                polling.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await polling
            await tg_http.aclose()
            await http.aclose()

    app = FastAPI(title="Orcify", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(routes_health.router)
    app.include_router(routes_tasks.router)
    app.include_router(routes_legal.router)
    app.include_router(routes_jira.router)
    app.include_router(routes_posts.router)
    app.include_router(routes_telegram.router)
    app.include_router(routes_finance.router)
    return app


app = create_app()
