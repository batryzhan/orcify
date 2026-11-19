"""In-process MCP-сервер ``orcify_jira``: инструменты нашего собственного трекера.

Агенты пайплайна создают и двигают задачи только через этот сервер
(MCPServerManager -> in-process Client), так же как раньше это делал бы
внешний Atlassian MCP — но данные никогда не покидают устройство.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app.core.jira_store import IssueNotFoundError, JiraStore
from app.schemas.jira import IssueCreate, IssueStatus, IssueUpdate, JiraBoard, JiraIssue


def build_jira_server(store: JiraStore) -> MCPServer:
    server = MCPServer(
        name="orcify-jira",
        instructions="Локальный трекер задач Orcify (доска ORC): создание, перенос и поиск задач.",
    )

    @server.tool(name="create_issue", description="Создать задачу на доске Orcify Jira")
    def create_issue(issue: IssueCreate) -> JiraIssue:
        return store.create(issue)

    @server.tool(
        name="update_issue",
        description="Изменить задачу: статус (колонку), исполнителя, приоритет, метки, вложения",
    )
    def update_issue(key: str, changes: IssueUpdate) -> JiraIssue:
        try:
            return store.update(key, changes)
        except IssueNotFoundError:
            raise ToolError("jira_input_error:issue_not_found") from None

    @server.tool(name="list_issues", description="Получить доску: колонки и задачи (опционально по статусу)")
    def list_issues(status: IssueStatus | None = None) -> JiraBoard:
        board = store.board()
        if status is not None:
            board.issues = [i for i in board.issues if i.status == status]
        return board

    return server
