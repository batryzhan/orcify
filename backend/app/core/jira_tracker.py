"""Пайплайнның MCPServerManager арқылы Orcify Jira-мен жұмысы (``orcify_jira`` сервері).

Трекер — қосымша арна: MCP-сервер қолжетімсіз болса, пайплайн
карточкасыз жұмысын жалғастырады (Graceful Degradation), құламайды.
"""

from __future__ import annotations

from typing import Final

from pydantic import ValidationError

from app.core.logger import get_logger
from app.mcp.manager import MCPServerManager
from app.schemas.jira import CreateIssueToolArgs, IssueCreate, IssueUpdate, JiraIssue, UpdateIssueToolArgs

JIRA_SERVER: Final = "orcify_jira"
log = get_logger(__name__)


class JiraTracker:
    def __init__(self, mcp: MCPServerManager) -> None:
        self._mcp = mcp

    async def create(self, issue: IssueCreate) -> JiraIssue | None:
        result = await self._mcp.call_tool(JIRA_SERVER, "create_issue", CreateIssueToolArgs(issue=issue))
        return self._parse(result.structured if result.ok else None, "create_issue")

    async def update(self, key: str | None, changes: IssueUpdate) -> JiraIssue | None:
        if key is None:
            return None
        result = await self._mcp.call_tool(JIRA_SERVER, "update_issue", UpdateIssueToolArgs(key=key, changes=changes))
        return self._parse(result.structured if result.ok else None, "update_issue")

    @staticmethod
    def _parse(structured: object, stage: str) -> JiraIssue | None:
        if structured is None:
            return None
        try:
            return JiraIssue.model_validate(structured)
        except ValidationError:
            log.warning("jira_contract_mismatch", server=JIRA_SERVER, stage=stage, error_code="contract_mismatch")
            return None
