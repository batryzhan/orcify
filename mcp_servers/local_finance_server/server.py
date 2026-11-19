"""Локальный MCP-сервер финансового анализа (stdio).

Запуск: ``python mcp_servers/local_finance_server/server.py``
(обычно запускается автоматически бэкендом через MCPServerManager).
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
    instructions="Локальный детерминированный анализ CSV-выписок. Возвращает только агрегаты.",
)


@mcp.tool(
    name="analyze_transactions",
    description=(
        "Считает агрегаты по CSV банковской выписки: выручка, расходы по категориям, "
        "помесячный денежный поток, кассовые разрывы, топ контрагентов, аномалии. "
        "Сырые строки наружу не возвращаются."
    ),
)
def analyze_transactions(csv_text: str, opening_balance: float = 0.0) -> FinanceMetrics:
    try:
        return analyze_csv(csv_text, opening_balance)
    except FinanceInputError as exc:
        # Ожидаемая ошибка входных данных: только машинный код, без трассировки и данных.
        raise ToolError(f"finance_input_error:{exc}") from None


if __name__ == "__main__":
    mcp.run("stdio")
