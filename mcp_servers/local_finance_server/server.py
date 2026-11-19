"""Жергілікті қаржылық талдау MCP-сервері (stdio).

Іске қосу: ``python mcp_servers/local_finance_server/server.py``
(әдетте бэкенд MCPServerManager арқылы автоматты түрде іске қосады).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from analysis import FinanceInputError, FinanceMetrics, analyze_csv  # noqa: E402

mcp = MCPServer(
    name="orcify-local-finance",
    instructions="CSV-үзінділердің жергілікті детерминистік талдауы. Тек агрегаттарды қайтарады.",
)


@mcp.tool(
    name="analyze_transactions",
    description=(
        "Банк үзіндісінің CSV-і бойынша агрегаттарды есептейді: түсім, санаттар бойынша шығыстар, "
        "айлар бойынша ақша ағыны, ақша ағынының үзілістері, топ контрагенттер, аномалиялар. "
        "Шикі жолдар сыртқа қайтарылмайды."
    ),
)
def analyze_transactions(csv_text: str, opening_balance: float = 0.0) -> FinanceMetrics:
    try:
        return analyze_csv(csv_text, opening_balance)
    except FinanceInputError as exc:
        # Кіріс деректеріндегі күтілетін қате: тек машиналық код, трассировкасыз және деректерсіз.
        raise ToolError(f"finance_input_error:{exc}") from None


if __name__ == "__main__":
    mcp.run("stdio")
