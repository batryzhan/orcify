"""MCPServerManager: единая точка всех вызовов MCP.

* реестр серверов с доменами (Smart Routing подгружает только инструменты домена);
* ``is_external=True`` -> аргументы обязательно проходят через LocalAnonymizer,
  ответ де-анонимизируется локально; при обнаружении утечки вызов блокируется;
* любая ошибка/тайм-аут/«не настроен» -> ``fallback_handler`` и ``degraded=True``
  вместо HTTP 500.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, JsonValue, SecretStr

from app.config import Settings
from app.core.anonymizer import AnonymizationSession
from app.core.logger import get_logger
from app.mcp.sync_queue import SyncQueue
from app.schemas.intent import DomainEnum
from app.schemas.mcp import (
    McpCallRequest,
    McpCallResult,
    McpServerHealth,
    McpServerSpec,
    McpToolInfo,
    McpTransport,
)

log = get_logger(__name__)

FallbackHandler = Callable[[McpCallRequest, str], Awaitable[McpCallResult]]

_ERROR_CODE_RE = re.compile(r"finance_input_error:([a-z_]{1,48})")


class PiiLeakError(RuntimeError):
    """Анонимизированные аргументы всё ещё содержат PII — вызов внешнего MCP запрещён."""


@dataclass
class _Registration:
    spec: McpServerSpec
    fallback: FallbackHandler
    token: SecretStr | None
    in_process: MCPServer | None


async def degraded_only(request: McpCallRequest, error_code: str) -> McpCallResult:
    """Fallback по умолчанию: только флаг деградации, артефакт строит пайплайн."""
    return McpCallResult(server=request.server, tool=request.tool, ok=False, degraded=True, error_code=error_code)


class MCPServerManager:
    def __init__(self) -> None:
        self._servers: dict[str, _Registration] = {}

    # --- реестр -------------------------------------------------------------

    def register(
        self,
        spec: McpServerSpec,
        fallback_handler: FallbackHandler = degraded_only,
        *,
        token: SecretStr | None = None,
        in_process: MCPServer | None = None,
    ) -> None:
        if spec.name in self._servers:
            raise ValueError(f"MCP server already registered: {spec.name}")
        self._servers[spec.name] = _Registration(spec, fallback_handler, token, in_process)

    def spec(self, name: str) -> McpServerSpec:
        return self._servers[name].spec

    def servers_for(self, domain: DomainEnum) -> list[McpServerSpec]:
        return [r.spec for r in self._servers.values() if domain in r.spec.domains]

    @property
    def specs(self) -> list[McpServerSpec]:
        return [r.spec for r in self._servers.values()]

    # --- подключение --------------------------------------------------------

    def _client(self, reg: _Registration) -> Client:
        spec = reg.spec
        if reg.in_process is not None:
            return Client(server=reg.in_process)
        if spec.transport is McpTransport.STDIO:
            if not spec.command:
                raise ValueError("stdio server without command")
            return Client(server=StdioServerParameters(command=spec.command, args=list(spec.args)))
        if not spec.url:
            raise ValueError("http server without url")
        headers = {}
        if reg.token is not None and reg.token.get_secret_value():
            headers["Authorization"] = f"Bearer {reg.token.get_secret_value()}"
        transport = streamable_http_client(spec.url, http_client=httpx2.AsyncClient(headers=headers, timeout=spec.timeout_s))
        return Client(server=transport)  # type: ignore[arg-type]

    async def list_tools(self, domain: DomainEnum | None = None) -> list[McpToolInfo]:
        """Инструменты домена (Scoped Execution) или все (Full Context, для экспериментов)."""
        tools: list[McpToolInfo] = []
        for reg in self._servers.values():
            if not reg.spec.enabled or (domain is not None and domain not in reg.spec.domains):
                continue
            try:
                async with asyncio.timeout(reg.spec.timeout_s):
                    async with self._client(reg) as client:
                        listed = await client.list_tools()
            except Exception as exc:  # noqa: BLE001 — недоступный сервер не должен ронять листинг
                log.warning("mcp_list_tools_failed", server=reg.spec.name, error_type=type(exc).__name__)
                continue
            tools += [
                McpToolInfo(server=reg.spec.name, name=t.name, description=t.description or "", input_schema=t.input_schema)
                for t in listed.tools
            ]
        return tools

    async def health(self) -> list[McpServerHealth]:
        result: list[McpServerHealth] = []
        for reg in self._servers.values():
            spec = reg.spec
            item = McpServerHealth(
                name=spec.name,
                domains=sorted(spec.domains),
                is_external=spec.is_external,
                enabled=spec.enabled,
                reachable=False,
            )
            if not spec.enabled:
                item.error_code = "not_configured"
            else:
                try:
                    async with asyncio.timeout(min(spec.timeout_s, 15.0)):
                        async with self._client(reg) as client:
                            item.tools = [t.name for t in (await client.list_tools()).tools]
                    item.reachable = True
                except Exception as exc:  # noqa: BLE001
                    item.error_code = type(exc).__name__
            result.append(item)
        return result

    # --- вызов --------------------------------------------------------------

    async def call_tool(
        self,
        server: str,
        tool: str,
        arguments: BaseModel,
        *,
        anonymizer: AnonymizationSession | None = None,
    ) -> McpCallResult:
        reg = self._servers[server]
        spec = reg.spec
        args: dict[str, JsonValue] = arguments.model_dump(mode="json")
        anonymized = False

        if spec.is_external:
            if anonymizer is None:
                raise PiiLeakError(f"external MCP '{server}' requires an anonymization session")
            masked = anonymizer.anonymize_json(args)
            if not isinstance(masked, dict):
                raise PiiLeakError("anonymized arguments must stay an object")
            leaked = anonymizer.leaked_json(masked)
            if leaked:
                log.error("mcp_pii_leak_blocked", server=server, stage=tool)
                raise PiiLeakError("PII remained after anonymization")
            args, anonymized = masked, True

        request = McpCallRequest(server=server, tool=tool, arguments=args)
        if not spec.enabled:
            return await self._fallback(reg, request, "not_configured", 0)

        started = time.monotonic()
        try:
            async with asyncio.timeout(spec.timeout_s):
                async with self._client(reg) as client:
                    result = await client.call_tool(tool, args)
        except TimeoutError:
            return await self._fallback(reg, request, "timeout", _ms(started))
        except Exception as exc:  # noqa: BLE001 — Graceful Degradation по CLAUDE.md §3.4
            return await self._fallback(reg, request, f"unavailable:{type(exc).__name__}", _ms(started))

        text = "\n".join(getattr(block, "text", "") for block in result.content if getattr(block, "type", "") == "text")
        if result.is_error:
            # Машинный код ошибки берём только у локальных серверов (их сообщения — наши коды).
            match = _ERROR_CODE_RE.search(text) if not spec.is_external else None
            code = f"tool_error:{match.group(1)}" if match else "tool_error"
            return await self._fallback(reg, request, code, _ms(started))

        structured: Any = result.structured_content
        if anonymized and anonymizer is not None:
            text = anonymizer.deanonymize(text)
            structured = anonymizer.deanonymize_json(structured) if structured is not None else None

        latency = _ms(started)
        log.info("mcp_call_ok", server=server, stage=tool, latency_ms=latency, degraded=False)
        return McpCallResult(
            server=server,
            tool=tool,
            ok=True,
            text=text or None,
            structured=structured if isinstance(structured, dict) else None,
            latency_ms=latency,
            anonymized=anonymized,
        )

    async def _fallback(self, reg: _Registration, request: McpCallRequest, code: str, latency: int) -> McpCallResult:
        log.warning("mcp_call_degraded", server=request.server, stage=request.tool, error_code=code[:64], degraded=True)
        result = await reg.fallback(request, code)
        return result.model_copy(update={"degraded": True, "latency_ms": latency, "anonymized": reg.spec.is_external})


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


# --- реестр по умолчанию (CLAUDE.md §5.4) ------------------------------------


def build_default_manager(settings: Settings, sync_queue: SyncQueue) -> MCPServerManager:
    manager = MCPServerManager()

    manager.register(
        McpServerSpec(
            name="local_finance",
            domains=frozenset({DomainEnum.FINANCE}),
            is_external=False,
            transport=McpTransport.STDIO,
            command=sys.executable,
            args=(str(settings.finance_mcp_script),),
            timeout_s=settings.mcp_timeout_s,
            enabled=settings.finance_mcp_enabled and settings.finance_mcp_script.is_file(),
            description="Локальный анализ CSV/Excel-выписок (pandas)",
        ),
        degraded_only,
    )
    manager.register(
        McpServerSpec(
            name="higgsfield",
            domains=frozenset({DomainEnum.SMM}),
            is_external=True,
            transport=McpTransport.HTTP,
            url=settings.higgsfield_mcp_url or None,
            timeout_s=settings.higgsfield_timeout_s,
            enabled=bool(settings.higgsfield_mcp_url),
            description="Генерация видео по сценарию",
        ),
        degraded_only,  # storyboard строит SMM-пайплайн из уже готового сценария
        token=settings.higgsfield_mcp_token,
    )
    manager.register(
        McpServerSpec(
            name="atlassian",
            domains=frozenset({DomainEnum.SMM, DomainEnum.HR}),
            is_external=True,
            transport=McpTransport.HTTP,
            url=settings.atlassian_mcp_url or None,
            timeout_s=settings.mcp_timeout_s,
            enabled=bool(settings.atlassian_mcp_url),
            description="Задачи Jira / страницы Confluence",
        ),
        sync_queue.fallback_handler,
        token=settings.atlassian_mcp_token,
    )
    manager.register(
        McpServerSpec(
            name="n8n",
            domains=frozenset({DomainEnum.SMM}),
            is_external=True,
            transport=McpTransport.HTTP,
            url=settings.n8n_mcp_url or None,
            timeout_s=settings.mcp_timeout_s,
            enabled=bool(settings.n8n_mcp_url),
            description="Запуск автоматизированных воркфлоу",
        ),
        sync_queue.fallback_handler,
        token=settings.n8n_mcp_token,
    )
    return manager
