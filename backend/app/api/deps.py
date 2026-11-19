"""Зависимости FastAPI: сервисы, созданные в lifespan приложения."""

from __future__ import annotations

from fastapi import Request

from app.channels.telegram import TelegramBot
from app.core.document_store import DocumentStore
from app.core.finance_store import BudgetStore, ReportStore
from app.core.jira_store import JiraStore
from app.core.legal_service import LegalService
from app.core.llm_client import LLMClient
from app.core.pipeline import TaskPipeline
from app.core.post_renderer import PostRenderer
from app.core.post_store import PostStore
from app.core.task_store import TaskStore
from app.mcp.manager import MCPServerManager


def get_llm_client(request: Request) -> LLMClient:
    client: LLMClient = request.app.state.llm
    return client


def get_pipeline(request: Request) -> TaskPipeline:
    pipeline: TaskPipeline = request.app.state.pipeline
    return pipeline


def get_task_store(request: Request) -> TaskStore:
    store: TaskStore = request.app.state.task_store
    return store


def get_legal_service(request: Request) -> LegalService:
    legal: LegalService = request.app.state.legal
    return legal


def get_document_store(request: Request) -> DocumentStore:
    documents: DocumentStore = request.app.state.documents
    return documents


def get_mcp_manager(request: Request) -> MCPServerManager:
    manager: MCPServerManager = request.app.state.mcp
    return manager


def get_jira_store(request: Request) -> JiraStore:
    store: JiraStore = request.app.state.jira
    return store


def get_post_store(request: Request) -> PostStore:
    store: PostStore = request.app.state.posts
    return store


def get_post_renderer(request: Request) -> PostRenderer:
    renderer: PostRenderer = request.app.state.post_renderer
    return renderer


def get_telegram_bot(request: Request) -> TelegramBot | None:
    bot: TelegramBot | None = request.app.state.telegram
    return bot


def get_report_store(request: Request) -> ReportStore:
    store: ReportStore = request.app.state.reports
    return store


def get_budget_store(request: Request) -> BudgetStore:
    store: BudgetStore = request.app.state.budgets
    return store
