"""Зависимости FastAPI: сервисы, созданные в lifespan приложения."""

from __future__ import annotations

from fastapi import Request

from app.core.document_store import DocumentStore
from app.core.legal_service import LegalService
from app.core.llm_client import LLMClient
from app.core.pipeline import TaskPipeline
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
