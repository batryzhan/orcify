"""Сценарий Б (SMM): сценарий (локально) -> LocalAnonymizer -> Higgsfield MCP
(или storyboard при деградации) -> Atlassian MCP (или очередь синхронизации).

Во внешние MCP уходят только анонимизированные данные; это обеспечивает
MCPServerManager (``is_external=True``). Сценарий с реальными именами
остаётся локально и показывается пользователю в UI.
"""

from __future__ import annotations

import re
from typing import Final

from app.config import Settings
from app.core.anonymizer import AnonymizationSession, LocalAnonymizer
from app.core.document_store import DocumentStore
from app.core.llm_client import ChatMessage, LLMClient
from app.core.logger import get_logger, payload_hash
from app.core.prompts import PromptLoader
from app.mcp.manager import MCPServerManager
from app.schemas.legal import DocumentInfo
from app.schemas.privacy import AnonymizationReport
from app.schemas.smm import (
    HiggsfieldVideoArgs,
    JiraIssueArgs,
    TrackerOutcome,
    TrackerStatus,
    VideoOutcome,
    VideoScriptSchema,
    VideoStatus,
)

SCRIPT_PROMPT: Final = "smm_orchestrator"
MD_MEDIA_TYPE: Final = "text/markdown; charset=utf-8"
_URL_RE = re.compile(r"https?://\S+")
_ISSUE_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")

log = get_logger(__name__)


def render_storyboard(script: VideoScriptSchema, video: VideoOutcome | None = None) -> str:
    lines = [
        f"# {script.title}",
        "",
        f"**Цель:** {script.goal}  ",
        f"**Аудитория:** {script.target_audience}  ",
        f"**Формат:** {script.aspect_ratio}, {script.duration_s} с",
        "",
    ]
    if video and video.url:
        lines += [f"**Видео:** {video.url}", ""]
    elif video:
        lines += ["> Видео не сгенерировано (внешний сервис недоступен) — раскадровка для ручного продакшена.", ""]
    lines += ["| # | Длит. | Кадр | Закадровый текст | Текст на экране |", "|---|---|---|---|---|"]
    lines += [
        f"| {s.scene_no} | {s.duration_s} с | {s.visual} | {s.voiceover} | {s.on_screen_text} |" for s in script.scenes
    ]
    lines += ["", "## Промпт для видеомодели", "", script.video_prompt, ""]
    if script.hashtags:
        lines += [" ".join(h if h.startswith("#") else f"#{h}" for h in script.hashtags), ""]
    return "\n".join(lines)


class SmmService:
    def __init__(
        self,
        llm: LLMClient,
        prompts: PromptLoader,
        anonymizer: LocalAnonymizer,
        mcp: MCPServerManager,
        documents: DocumentStore,
        settings: Settings,
    ) -> None:
        self._llm = llm
        self._prompts = prompts
        self._anonymizer = anonymizer
        self._mcp = mcp
        self._documents = documents
        self._settings = settings

    async def write_script(self, text: str) -> VideoScriptSchema:
        messages = [
            ChatMessage(role="system", content=self._prompts.load(SCRIPT_PROMPT)),
            ChatMessage(role="user", content=text),
        ]
        return (await self._llm.structured(messages, VideoScriptSchema, stage="analyzing")).data

    async def anonymize(self, text: str, script: VideoScriptSchema) -> tuple[AnonymizationSession, str, AnonymizationReport]:
        session = await self._anonymizer.build_session([text])
        external_prompt = session.anonymize(script.video_prompt)
        # Предварительный прогон по всему сценарию: регистрирует PII, попавшие в сцены.
        masked = session.anonymize_json(script.model_dump(mode="json"))
        report = session.report(leaked_count=session.leaked_json(masked) + session.leaked(external_prompt))
        return session, external_prompt, report

    async def generate_video(self, script: VideoScriptSchema, session: AnonymizationSession) -> VideoOutcome:
        result = await self._mcp.call_tool(
            "higgsfield",
            self._settings.higgsfield_tool,
            HiggsfieldVideoArgs(prompt=script.video_prompt, duration=script.duration_s, aspect_ratio=script.aspect_ratio),
            anonymizer=session,
        )
        if result.ok:
            url = None
            if result.structured:
                candidate = result.structured.get("url") or result.structured.get("video_url")
                url = candidate if isinstance(candidate, str) else None
            if url is None and result.text:
                match = _URL_RE.search(result.text)
                url = match.group(0) if match else None
            if url:
                return VideoOutcome(status=VideoStatus.GENERATED, url=url, latency_ms=result.latency_ms)
            return VideoOutcome(status=VideoStatus.STORYBOARD, error_code="no_video_url", latency_ms=result.latency_ms)
        return VideoOutcome(status=VideoStatus.STORYBOARD, error_code=result.error_code, latency_ms=result.latency_ms)

    def store_storyboard(self, script: VideoScriptSchema, video: VideoOutcome) -> DocumentInfo:
        content = render_storyboard(script, video).encode("utf-8")
        filename = "storyboard.md"
        doc_id = self._documents.put(filename=filename, media_type=MD_MEDIA_TYPE, content=content)
        return DocumentInfo(
            document_id=doc_id,
            filename=filename,
            download_url=f"/api/documents/{doc_id}",
            sha256=payload_hash(content),
            size_bytes=len(content),
        )

    async def create_issue(
        self, script: VideoScriptSchema, video: VideoOutcome, session: AnonymizationSession
    ) -> TrackerOutcome:
        args = JiraIssueArgs(
            project_key=self._settings.atlassian_project_key,
            summary=f"Видеоролик: {script.title}",
            description=render_storyboard(script, video),
            labels=["orcify", "video", video.status.value],
        )
        result = await self._mcp.call_tool("atlassian", self._settings.atlassian_tool, args, anonymizer=session)
        if result.ok:
            key = None
            if result.structured:
                candidate = result.structured.get("key") or result.structured.get("issue_key")
                key = candidate if isinstance(candidate, str) else None
            if key is None and result.text:
                match = _ISSUE_RE.search(result.text)
                key = match.group(0) if match else None
            return TrackerOutcome(status=TrackerStatus.CREATED, issue_key=key)
        queued = result.structured.get("queued_id") if result.structured else None
        return TrackerOutcome(
            status=TrackerStatus.QUEUED,
            queued_id=queued if isinstance(queued, str) else None,
            error_code=result.error_code,
        )
