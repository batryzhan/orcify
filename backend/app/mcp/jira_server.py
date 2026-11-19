"""In-process MCP-сервері ``orcify_jira``: өз трекеріміздің құралдары.

Пайплайн агенттері тапсырмаларды тек осы сервер арқылы жасайды және жылжытады
(MCPServerManager -> in-process Client), бұрын мұны сыртқы
Atlassian MCP істейтін еді — бірақ деректер құрылғыдан ешқашан шықпайды.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app.core.jira_store import IssueNotFoundError, JiraStore
from app.schemas.jira import IssueCreate, IssueStatus, IssueUpdate, JiraBoard, JiraIssue


def build_jira_server(store: JiraStore) -> MCPServer:
    server = MCPServer(
        name="orcify-jira",
        instructions="Orcify жергілікті тапсырмалар трекері (ORC тақтасы): тапсырмаларды жасау, жылжыту және іздеу.",
    )

    @server.tool(name="create_issue", description="Orcify Jira тақтасында тапсырма жасау")
    def create_issue(issue: IssueCreate) -> JiraIssue:
        return store.create(issue)

    @server.tool(
        name="update_issue",
        description="Тапсырманы өзгерту: мәртебе (баған), орындаушы, басымдық, белгілер, тіркемелер",
    )
    def update_issue(key: str, changes: IssueUpdate) -> JiraIssue:
        try:
            return store.update(key, changes)
        except IssueNotFoundError:
            raise ToolError("jira_input_error:issue_not_found") from None

    @server.tool(name="list_issues", description="Тақтаны алу: бағандар және тапсырмалар (қалауынша мәртебе бойынша)")
    def list_issues(status: IssueStatus | None = None) -> JiraBoard:
        board = store.board()
        if status is not None:
            board.issues = [i for i in board.issues if i.status == status]
        return board

    return server
