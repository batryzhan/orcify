"""MCPServerManager, Сценарий В (Finance) и Сценарий Б (SMM) с in-process MCP-серверами."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel

from app.config import BACKEND_DIR, Settings
from app.core.anonymizer import AnonymizationSession
from app.main import create_app
from app.mcp.manager import MCPServerManager, PiiLeakError
from app.mcp.sync_queue import SyncQueue
from app.schemas.finance import FinanceMetrics
from app.schemas.intent import DomainEnum
from app.schemas.mcp import McpServerSpec, McpTransport
from tests.conftest import Handler, intent_json, schema_router
from tests.test_api import parse_sse

SAMPLE_CSV = (BACKEND_DIR.parent / "frontend" / "public" / "samples" / "transactions_demo.csv").read_text(encoding="utf-8")
FINANCE_DIR = BACKEND_DIR.parent / "mcp_servers" / "local_finance_server"


def load_finance_server() -> ModuleType:
    sys.path.insert(0, str(FINANCE_DIR))
    spec = importlib.util.spec_from_file_location("orcify_finance_server", FINANCE_DIR / "server.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FINANCE = load_finance_server()


class EchoArgs(BaseModel):
    prompt: str


def external_spec(name: str, domain: DomainEnum = DomainEnum.SMM) -> McpServerSpec:
    return McpServerSpec(
        name=name, domains=frozenset({domain}), is_external=True, transport=McpTransport.HTTP, url="http://fake"
    )


class Captured:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []


def fake_higgsfield(captured: Captured, fail: bool = False) -> MCPServer:
    server = MCPServer(name="fake-higgsfield")

    @server.tool(name="generate_video")
    def generate_video(prompt: str, duration: int, aspect_ratio: str) -> dict[str, str]:
        captured.calls.append({"prompt": prompt, "duration": duration, "aspect_ratio": aspect_ratio})
        if fail:
            raise RuntimeError("service down")
        return {"url": "https://cdn.example/video.mp4"}

    return server


def fake_atlassian(captured: Captured) -> MCPServer:
    server = MCPServer(name="fake-atlassian")

    @server.tool(name="createJiraIssue")
    def create_issue(project_key: str, summary: str, description: str, issue_type: str, labels: list[str]) -> dict[str, str]:
        captured.calls.append({"summary": summary, "description": description})
        return {"key": f"{project_key}-42"}

    return server


def build_manager(tmp_path: Path, *, higgsfield: MCPServer | None, atlassian: MCPServer | None) -> MCPServerManager:
    queue = SyncQueue(tmp_path / "queue.jsonl")
    manager = MCPServerManager()
    manager.register(
        McpServerSpec(
            name="local_finance", domains=frozenset({DomainEnum.FINANCE}), is_external=False, transport=McpTransport.STDIO
        ),
        in_process=FINANCE.mcp,
    )
    hf_spec = external_spec("higgsfield")
    manager.register(hf_spec if higgsfield else hf_spec.model_copy(update={"enabled": False}), in_process=higgsfield)
    at_spec = external_spec("atlassian")
    manager.register(
        at_spec if atlassian else at_spec.model_copy(update={"enabled": False}),
        queue.fallback_handler,
        in_process=atlassian,
    )
    return manager


# --- MCPServerManager ----------------------------------------------------------


def test_servers_are_scoped_by_domain(tmp_path: Path) -> None:
    manager = build_manager(tmp_path, higgsfield=None, atlassian=None)
    assert [s.name for s in manager.servers_for(DomainEnum.FINANCE)] == ["local_finance"]
    assert {s.name for s in manager.servers_for(DomainEnum.SMM)} == {"higgsfield", "atlassian"}
    assert manager.servers_for(DomainEnum.LEGAL) == []


async def test_list_tools_scoped_vs_full(tmp_path: Path) -> None:
    manager = build_manager(tmp_path, higgsfield=fake_higgsfield(Captured()), atlassian=fake_atlassian(Captured()))
    finance_tools = await manager.list_tools(DomainEnum.FINANCE)
    all_tools = await manager.list_tools()
    assert [t.name for t in finance_tools] == ["analyze_transactions"]
    assert {t.name for t in all_tools} == {"analyze_transactions", "generate_video", "createJiraIssue"}


async def test_external_call_requires_anonymizer(tmp_path: Path) -> None:
    manager = build_manager(tmp_path, higgsfield=fake_higgsfield(Captured()), atlassian=None)
    with pytest.raises(PiiLeakError):
        await manager.call_tool("higgsfield", "generate_video", EchoArgs(prompt="x"))


async def test_external_call_is_anonymized_and_result_deanonymized(tmp_path: Path) -> None:
    server = MCPServer(name="echo")

    @server.tool(name="echo")
    def echo(prompt: str) -> str:
        return f"получено: {prompt}"

    manager = MCPServerManager()
    manager.register(external_spec("echo"), in_process=server)
    session = AnonymizationSession()
    result = await manager.call_tool("echo", "echo", EchoArgs(prompt="ТОО «Альфа», ИИН 900101300017"), anonymizer=session)

    assert result.ok and result.anonymized
    assert result.text == "получено: ТОО «Альфа», ИИН 900101300017"  # де-анонимизировано локально


async def test_unavailable_server_degrades_to_queue(tmp_path: Path) -> None:
    manager = build_manager(tmp_path, higgsfield=None, atlassian=None)
    session = AnonymizationSession()
    result = await manager.call_tool("atlassian", "createJiraIssue", EchoArgs(prompt="Клиент ИИН 900101300017"), anonymizer=session)

    assert result.degraded and not result.ok and result.error_code == "not_configured"
    queued = SyncQueue(tmp_path / "queue.jsonl").pending()
    assert len(queued) == 1
    assert queued[0].arguments == {"prompt": "Клиент ИИН [IIN_1]"}  # в очередь — только токены
    assert "900101300017" not in (tmp_path / "queue.jsonl").read_text(encoding="utf-8")


# --- Сценарий В: Finance -----------------------------------------------------------


def test_finance_contract_matches_mcp_server() -> None:
    server_metrics = FINANCE.analyze_csv(SAMPLE_CSV, 500_000)
    backend_metrics = FinanceMetrics.model_validate(server_metrics.model_dump(mode="json"))
    assert set(FinanceMetrics.model_fields) == set(type(server_metrics).model_fields)
    assert backend_metrics.cash_gaps and backend_metrics.cash_gaps[0].min_balance < 0
    assert backend_metrics.anomalies[0].amount == -4_800_000


@pytest.mark.parametrize(
    ("csv_text", "code"),
    [("a;b\n1;2", "date_column_not_found"), ("Дата;Описание\n01.01.2026;x", "amount_column_not_found")],
)
def test_finance_input_errors(csv_text: str, code: str) -> None:
    with pytest.raises(FINANCE.FinanceInputError, match=code):
        FINANCE.analyze_csv(csv_text)


def test_finance_income_expense_columns() -> None:
    csv_text = "date,credit,debit,counterparty\n2026-01-05,1000,,A\n2026-01-06,,300,B\n2026-02-01,500,,A\n"
    metrics = FINANCE.analyze_csv(csv_text)
    assert (metrics.total_income, metrics.total_expense, metrics.net) == (1500.0, 300.0, 1200.0)
    assert [m.month for m in metrics.monthly] == ["2026-01", "2026-02"]


REPORT = json.dumps(
    {
        "headline": "Поток положительный, но был кассовый разрыв",
        "key_findings": ["Выручка выше расходов", "Зарплата — крупнейшая статья"],
        "risks": [{"title": "Кассовый разрыв", "level": "high", "detail": "Июль"}],
        "recommendations": ["Создать резерв"],
    },
    ensure_ascii=False,
)


def make_client(settings: Settings, handler: Handler, manager: MCPServerManager) -> TestClient:
    return TestClient(create_app(settings, llm_transport=httpx.MockTransport(handler), mcp_manager=manager))


def test_finance_scenario_end_to_end(settings: Settings, tmp_path: Path) -> None:
    seen_by_llm: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen_by_llm.append(json.dumps(body["messages"], ensure_ascii=False))
        return schema_router({"IntentClassificationResult": intent_json("Finance"), "FinanceReportSchema": REPORT})(request)

    manager = build_manager(tmp_path, higgsfield=None, atlassian=None)
    with make_client(settings, handler, manager) as client:
        task = client.post(
            "/api/tasks",
            json={
                "text": "Проанализируй выписку",
                "attachment": {"filename": "bank.csv", "content": SAMPLE_CSV},
                "opening_balance": 500000,
            },
        ).json()
        events = parse_sse(client.get(task["events_url"]).text)

        assert [e["status"] for e in events] == [
            "classifying_intent", "routing_finance", "analyzing_csv", "generating_report", "completed",
        ]
        assert all(e.get("domain") == "Finance" for e in events[1:])
        finance = events[-1]["result"]["finance"]  # type: ignore[index]
        assert finance["report"]["risks"][0]["level"] == "high"
        assert finance["metrics"]["cash_gaps"]
        report_md = client.get(finance["document"]["download_url"]).text
        assert "Кассовые разрывы" in report_md

    # В LLM не попадает ни одна сырая строка выписки (только имя файла и агрегаты).
    llm_input = "\n".join(seen_by_llm)
    assert "Оплата по счёту" not in llm_input  # назначение платежа из строк
    assert "bank.csv" in llm_input


def test_finance_without_attachment_asks_for_csv(settings: Settings, tmp_path: Path) -> None:
    manager = build_manager(tmp_path, higgsfield=None, atlassian=None)
    handler = schema_router({"IntentClassificationResult": intent_json("Finance")})
    with make_client(settings, handler, manager) as client:
        task = client.post("/api/tasks", json={"text": "Посчитай расходы"}).json()
        final = parse_sse(client.get(task["events_url"]).text)[-1]
    assert final["status"] == "completed" and "CSV" in str(final["message"])


def test_finance_bad_csv_fails_gracefully(settings: Settings, tmp_path: Path) -> None:
    manager = build_manager(tmp_path, higgsfield=None, atlassian=None)
    handler = schema_router({"IntentClassificationResult": intent_json("Finance")})
    with make_client(settings, handler, manager) as client:
        task = client.post(
            "/api/tasks", json={"text": "Анализ", "attachment": {"filename": "x.csv", "content": "a;b\n1;2"}}
        ).json()
        final = parse_sse(client.get(task["events_url"]).text)[-1]
    assert final["status"] == "failed"
    assert final["error"]["code"] == "tool_error:date_column_not_found"  # type: ignore[index]


# --- Сценарий Б: SMM ----------------------------------------------------------------

SMM_REQUEST = (
    "Сделай ролик для ТОО «Альфа Трейд» про наш новый сервис доставки. "
    "Упомяни кейс клиента Иванов Пётр, контакт для связи +7 701 123-45-67."
)

SCRIPT = json.dumps(
    {
        "title": "Доставка от ТОО «Альфа Трейд»",
        "goal": "Рассказать о сервисе доставки",
        "target_audience": "Малый бизнес Алматы",
        "aspect_ratio": "9:16",
        "duration_s": 15,
        "scenes": [
            {"scene_no": 1, "duration_s": 7, "visual": "Курьер у офиса", "voiceover": "Иванов Пётр получил заказ за час",
             "on_screen_text": "Доставка за час"},
            {"scene_no": 2, "duration_s": 8, "visual": "Логотип", "voiceover": "Звоните +7 701 123-45-67",
             "on_screen_text": "ТОО «Альфа Трейд»"},
        ],
        "video_prompt": "Courier hands a parcel to Иванов Пётр near ТОО «Альфа Трейд» office, golden hour, handheld",
        "hashtags": ["доставка"],
    },
    ensure_ascii=False,
)

PII = json.dumps({"entities": [{"text": "Иванов Пётр", "category": "PERSON"}]}, ensure_ascii=False)
SENSITIVE = ["Альфа Трейд", "Иванов Пётр", "+7 701 123-45-67"]


def smm_handler() -> Handler:
    return schema_router(
        {"IntentClassificationResult": intent_json("SMM"), "VideoScriptSchema": SCRIPT, "PiiDetectionResult": PII}
    )


def test_smm_scenario_sends_only_tokens_to_external_mcp(settings: Settings, tmp_path: Path) -> None:
    hf, jira = Captured(), Captured()
    manager = build_manager(tmp_path, higgsfield=fake_higgsfield(hf), atlassian=fake_atlassian(jira))
    with make_client(settings, smm_handler(), manager) as client:
        task = client.post("/api/tasks", json={"text": SMM_REQUEST}).json()
        events = parse_sse(client.get(task["events_url"]).text)

    assert [e["status"] for e in events] == [
        "classifying_intent", "routing_smm", "analyzing", "anonymizing_pii",
        "generating_video", "creating_jira_issue", "completed",
    ]
    smm = events[-1]["result"]["smm"]  # type: ignore[index]
    assert smm["video"] == {"status": "generated", "url": "https://cdn.example/video.mp4", "latency_ms": smm["video"]["latency_ms"]}
    assert smm["tracker"]["status"] == "created" and smm["tracker"]["issue_key"] == "MKT-42"
    assert smm["anonymization"]["leaked_count"] == 0
    assert "[PERSON_1]" in smm["external_prompt"] and "[COMPANY_1]" in smm["external_prompt"]

    # PII Leakage Rate = 0: ни одно чувствительное значение не дошло до внешних серверов.
    outbound = json.dumps(hf.calls + jira.calls, ensure_ascii=False)
    assert hf.calls and jira.calls
    for value in SENSITIVE:
        assert value not in outbound
    # Локальный сценарий в UI — с реальными данными.
    assert "Иванов Пётр" in json.dumps(smm["script"], ensure_ascii=False)


def test_smm_degrades_to_storyboard_and_queue(settings: Settings, tmp_path: Path) -> None:
    hf = Captured()
    manager = build_manager(tmp_path, higgsfield=fake_higgsfield(hf, fail=True), atlassian=None)
    with make_client(settings, smm_handler(), manager) as client:
        task = client.post("/api/tasks", json={"text": SMM_REQUEST}).json()
        events = parse_sse(client.get(task["events_url"]).text)
        smm = events[-1]["result"]["smm"]  # type: ignore[index]
        storyboard = client.get(smm["storyboard"]["download_url"]).text

    assert events[-1]["status"] == "completed"  # не 500 и не failed
    assert smm["video"]["status"] == "storyboard"
    assert smm["tracker"]["status"] == "queued" and smm["tracker"]["queued_id"]
    assert "| 1 | 7 с | Курьер у офиса |" in storyboard
    queue_text = (tmp_path / "queue.jsonl").read_text(encoding="utf-8")
    for value in SENSITIVE:
        assert value not in queue_text
