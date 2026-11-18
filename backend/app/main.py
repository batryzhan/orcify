"""Точка входа FastAPI.

Запуск: ``uvicorn app.main:app --reload`` из папки ``backend``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_health, routes_legal, routes_tasks
from app.config import Settings, get_settings
from app.core.doc_engine import DocEngine
from app.core.document_store import DocumentStore
from app.core.legal_service import LegalService
from app.core.llm_client import LLMClient, build_http_client
from app.core.logger import configure_logging
from app.core.pipeline import TaskPipeline
from app.core.prompts import PromptLoader
from app.core.router import IntentRouter
from app.core.task_store import TaskStore


def create_app(
    settings: Settings | None = None, llm_transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        http = build_http_client(settings, transport=llm_transport)
        llm = LLMClient(settings, http)
        prompts = PromptLoader(settings.prompts_dir)
        documents = DocumentStore(ttl_s=settings.document_ttl_s)
        legal = LegalService(llm, prompts, DocEngine(settings.templates_dir, settings), documents, settings)
        app.state.llm = llm
        app.state.legal = legal
        app.state.documents = documents
        app.state.pipeline = TaskPipeline(IntentRouter(llm, prompts, settings), legal)
        app.state.task_store = TaskStore(ttl_s=settings.task_ttl_s)
        try:
            yield
        finally:
            await http.aclose()

    app = FastAPI(title="Orcify", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(routes_health.router)
    app.include_router(routes_tasks.router)
    app.include_router(routes_legal.router)
    return app


app = create_app()
