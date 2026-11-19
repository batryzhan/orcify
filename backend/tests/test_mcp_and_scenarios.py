"""MCPServerManager, Сценарии В (Finance), Б (Awesome Posts) и HR с in-process MCP-серверами."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver import MCPServer
from PIL import Image
from pydantic import BaseModel

from app.config import BACKEND_DIR, Settings
from app.core.anonymizer import AnonymizationSession
from app.core.jira_store import JiraStore
from app.core.post_renderer import PostRenderer
from app.core.post_store import PostStore
from app.main import create_app
from app.mcp.manager import MCPServerManager, PiiLeakError, build_default_manager
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


def local_factory(settings: Settings, jira: JiraStore, renderer: PostRenderer, posts: PostStore) -> MCPServerManager:
    """Реестр по умолчанию, но финансовый сервер подключён in-process (без подпроцесса)."""
    return build_default_manager(settings, jira, renderer, posts, finance_server=FINANCE.mcp)


def make_client(settings: Settings, handler: Handler) -> TestClient:
    return TestClient(create_app(settings, llm_transport=httpx.MockTransport(handler), mcp_factory=local_factory))


def registry(settings: Settings, tmp_path: Path) -> MCPServerManager:
    return local_factory(settings, JiraStore(None), PostRenderer(settings.assets_dir), PostStore(tmp_path))


# --- MCPServerManager ----------------------------------------------------------


def test_servers_are_scoped_by_domain(settings: Settings, tmp_path: Path) -> None:
    manager = registry(settings, tmp_path)
    assert [s.name for s in manager.servers_for(DomainEnum.FINANCE)] == ["local_finance", "orcify_jira"]
    assert [s.name for s in manager.servers_for(DomainEnum.SMM)] == ["orcify_jira", "awesome_posts"]
    assert [s.name for s in manager.servers_for(DomainEnum.LEGAL)] == ["orcify_jira"]
    assert not any(s.is_external for s in manager.specs)  # все серверы Orcify локальные


async def test_list_tools_scoped_vs_full(settings: Settings, tmp_path: Path) -> None:
    manager = registry(settings, tmp_path)
    smm_tools = {t.name for t in await manager.list_tools(DomainEnum.SMM)}
    all_tools = {t.name for t in await manager.list_tools()}
    assert smm_tools == {"create_issue", "update_issue", "list_issues", "render_post"}
    assert all_tools == smm_tools | {"analyze_transactions"}


def echo_server(seen: list[str]) -> MCPServer:
    server = MCPServer(name="echo")

    @server.tool(name="echo")
    def echo(prompt: str) -> str:
        seen.append(prompt)
        return f"получено: {prompt}"

    return server


async def test_external_call_requires_anonymizer() -> None:
    manager = MCPServerManager()
    manager.register(external_spec("echo"), in_process=echo_server([]))
    with pytest.raises(PiiLeakError):
        await manager.call_tool("echo", "echo", EchoArgs(prompt="x"))


async def test_external_call_is_anonymized_and_result_deanonymized() -> None:
    seen: list[str] = []
    manager = MCPServerManager()
    manager.register(external_spec("echo"), in_process=echo_server(seen))
    session = AnonymizationSession()
    result = await manager.call_tool("echo", "echo", EchoArgs(prompt="ТОО «Альфа», ИИН 900101300017"), anonymizer=session)

    assert seen and "900101300017" not in seen[0] and "[IIN_1]" in seen[0]  # наружу ушёл только токен
    assert result.ok and result.anonymized
    assert result.text == "получено: ТОО «Альфа», ИИН 900101300017"  # де-анонимизировано локально


async def test_disabled_server_degrades() -> None:
    manager = MCPServerManager()
    manager.register(external_spec("echo").model_copy(update={"enabled": False}))
    result = await manager.call_tool("echo", "echo", EchoArgs(prompt="x"), anonymizer=AnonymizationSession())
    assert result.degraded and not result.ok and result.error_code == "not_configured"


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


def test_finance_scenario_end_to_end(settings: Settings) -> None:
    seen_by_llm: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen_by_llm.append(json.dumps(body["messages"], ensure_ascii=False))
        return schema_router({"IntentClassificationResult": intent_json("Finance"), "FinanceReportSchema": REPORT})(request)

    with make_client(settings, handler) as client:
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
            "classifying_intent", "creating_jira_issue", "routing_finance", "updating_jira",
            "analyzing_csv", "generating_report", "rendering_pdf", "updating_jira", "completed",
        ]
        assert all(e.get("domain") == "Finance" for e in events[1:])
        assert events[1]["issue"]["summary"] == "Анализ выписки bank.csv"  # type: ignore[index]
        assert events[-2]["issue"]["status"] == "done"  # type: ignore[index]
        finance = events[-1]["result"]["finance"]  # type: ignore[index]
        assert finance["report"]["risks"][0]["level"] == "high"
        assert finance["metrics"]["cash_gaps"]
        pdf = client.get(finance["report_file"]["download_url"])
        assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF") and len(pdf.content) == finance["report_file"]["size_bytes"]
        assert finance["metrics"]["forecast"] and finance["metrics"]["month_over_month"]
        assert events[-2]["issue"]["attachments"][0]["kind"] == "report"  # type: ignore[index]
        archive = client.get("/api/finance/reports").json()
        assert archive[0]["file"]["report_id"] == finance["report_file"]["report_id"]
        assert archive[0]["issue_key"] == events[-1]["result"]["issue_key"]  # type: ignore[index]

    # В LLM не попадает ни одна сырая строка выписки (только имя файла и агрегаты).
    llm_input = "\n".join(seen_by_llm)
    assert "Оплата по счёту" not in llm_input  # назначение платежа из строк
    assert "bank.csv" in llm_input


def test_finance_without_attachment_asks_for_csv(settings: Settings) -> None:
    handler = schema_router({"IntentClassificationResult": intent_json("Finance")})
    with make_client(settings, handler) as client:
        task = client.post("/api/tasks", json={"text": "Посчитай расходы"}).json()
        events = parse_sse(client.get(task["events_url"]).text)
    assert events[-1]["status"] == "completed" and "CSV" in str(events[-1]["message"])
    assert "NEEDS INPUT" in events[-2]["issue"]["labels"]  # type: ignore[index]


def test_finance_bad_csv_fails_gracefully(settings: Settings) -> None:
    handler = schema_router({"IntentClassificationResult": intent_json("Finance")})
    with make_client(settings, handler) as client:
        task = client.post(
            "/api/tasks", json={"text": "Анализ", "attachment": {"filename": "x.csv", "content": "a;b\n1;2"}}
        ).json()
        final = parse_sse(client.get(task["events_url"]).text)[-1]
    assert final["status"] == "failed"
    assert final["error"]["code"] == "tool_error:date_column_not_found"  # type: ignore[index]


# --- Сценарий Б: Awesome Posts --------------------------------------------------------

SMM_REQUEST = "Сделай пост для Instagram: знакомство с командой Orcify, мы строим локальный ИИ для бизнеса."


def post_copy(**overrides: object) -> str:
    data: dict[str, object] = {
        "template": "cosmos",
        "kicker": None,
        "headline": "Знакомьтесь",
        "headline_accent": "Команда Orcify",
        "subtitle": "Пятеро инженеров, которые учат локальный ИИ работать на бизнес",
        "cta": None,
        "handle": "orcify",
        "caption": "Привет! Мы — команда Orcify.",
        "hashtags": ["#orcify", "localai"],
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def smm_handler(copy_json: str | None = None) -> Handler:
    return schema_router({"IntentClassificationResult": intent_json("SMM"), "PostCopySchema": copy_json or post_copy()})


def test_smm_scenario_renders_post_and_moves_card(settings: Settings) -> None:
    with make_client(settings, smm_handler()) as client:
        task = client.post("/api/tasks", json={"text": SMM_REQUEST}).json()
        events = parse_sse(client.get(task["events_url"]).text)

        assert [e["status"] for e in events] == [
            "classifying_intent", "creating_jira_issue", "routing_smm", "updating_jira", "writing_copy",
            "updating_jira", "rendering_post", "updating_jira", "completed",
        ]
        assert [e["issue"]["status"] for e in events if "issue" in e] == ["todo", "in_progress", "in_progress", "done"]
        result = events[-1]["result"]  # type: ignore[index]
        post = result["smm"]["post"]
        assert post["template"] == "cosmos" and (post["width"], post["height"]) == (1080, 1350)

        png = client.get(post["image_url"])
        assert png.status_code == 200 and png.headers["content-type"] == "image/png"
        assert Image.open(io.BytesIO(png.content)).size == (1080, 1350)

        board = client.get("/api/jira/board").json()
        issue = next(i for i in board["issues"] if i["key"] == result["issue_key"])
        assert issue["status"] == "done" and issue["summary"] == "Instagram-пост: Знакомьтесь Команда Orcify"
        assert issue["attachments"] == [{"kind": "post", "title": "Пост · cosmos", "url": post["image_url"]}]

        gallery = client.get("/api/posts").json()
        assert gallery[0]["post"]["post_id"] == post["post_id"] and gallery[0]["issue_key"] == result["issue_key"]


def test_smm_user_template_overrides_model(settings: Settings) -> None:
    with make_client(settings, smm_handler(post_copy(template="summit"))) as client:
        task = client.post("/api/tasks", json={"text": SMM_REQUEST, "post_template": "neon"}).json()
        result = parse_sse(client.get(task["events_url"]).text)[-1]["result"]
    assert result["smm"]["post"]["template"] == "neon" and result["smm"]["template_forced"] is True  # type: ignore[index]


def test_smm_render_failure_is_reported(settings: Settings, tmp_path: Path) -> None:
    broken = settings.model_copy(update={"assets_dir": tmp_path / "no_assets"})
    with make_client(broken, smm_handler()) as client:
        task = client.post("/api/tasks", json={"text": SMM_REQUEST}).json()
        final = parse_sse(client.get(task["events_url"]).text)[-1]
    assert final["status"] == "failed"
    assert final["error"]["code"] == "tool_error:background_missing"  # type: ignore[index]
    assert "ERROR" in final["issue"]["labels"]  # type: ignore[index]


def test_post_templates_and_safe_ids(settings: Settings) -> None:
    with make_client(settings, smm_handler()) as client:
        templates = client.get("/api/posts/templates").json()
        assert [t["id"] for t in templates] == ["cosmos", "neon", "summit"]
        background = client.get(templates[0]["background_url"])
        assert background.status_code == 200 and background.headers["content-type"] == "image/jpeg"
        preview = client.get(templates[1]["preview_url"])
        assert preview.status_code == 200 and Image.open(io.BytesIO(preview.content)).size == (1080, 1350)
        assert client.get("/api/posts/nothex.png").status_code == 404
        # Без настроенного бота отправка в Telegram — 404/409, а не 500.
        assert client.post(f"/api/posts/{'0' * 32}/telegram").status_code == 404


# --- HR: планировщик задач Orcify Jira -------------------------------------------------

PLAN = json.dumps(
    {
        "epic": "Онбординг дизайнера",
        "issues": [
            {"summary": "Подготовить рабочее место", "description": "Ноутбук и доступы", "type": "task",
             "priority": "high", "story_points": 2, "assignee_role": "IT"},
            {"summary": "Провести знакомство с командой", "description": "Встреча в первый день", "type": "story",
             "priority": "medium", "story_points": 1, "assignee_role": "Руководитель"},
            {"summary": "Оформить приказ о приёме", "description": "Подписать документы", "type": "task",
             "priority": "highest", "story_points": 3, "assignee_role": "HR"},
        ],
    },
    ensure_ascii=False,
)


def test_hr_plan_creates_issues_on_board(settings: Settings) -> None:
    handler = schema_router({"IntentClassificationResult": intent_json("HR"), "JiraPlanSchema": PLAN})
    with make_client(settings, handler) as client:
        task = client.post("/api/tasks", json={"text": "Составь план онбординга нового дизайнера"}).json()
        events = parse_sse(client.get(task["events_url"]).text)
        board = client.get("/api/jira/board").json()

    result = events[-1]["result"]  # type: ignore[index]
    epic_key = result["issue_key"]
    assert result["hr"]["plan"]["epic"] == "Онбординг дизайнера" and len(result["hr"]["issue_keys"]) == 3
    children = [i for i in board["issues"] if i.get("parent_key") == epic_key]
    assert {c["summary"] for c in children} == {
        "Подготовить рабочее место", "Провести знакомство с командой", "Оформить приказ о приёме",
    }
    assert all(c["status"] == "todo" and c["domain"] == "HR" and c["labels"] == ["PLAN"] for c in children)
    epic = next(i for i in board["issues"] if i["key"] == epic_key)
    assert epic["type"] == "epic" and epic["summary"] == "Онбординг дизайнера"


def test_pipeline_works_without_jira(settings: Settings) -> None:
    """Graceful Degradation: недоступный трекер не ломает сценарий, просто нет карточки."""

    def no_jira(settings: Settings, jira: JiraStore, renderer: PostRenderer, posts: PostStore) -> MCPServerManager:
        manager = local_factory(settings, jira, renderer, posts)
        reg = manager._servers["orcify_jira"]  # noqa: SLF001
        reg.spec = reg.spec.model_copy(update={"enabled": False})
        return manager

    app = create_app(settings, llm_transport=httpx.MockTransport(smm_handler()), mcp_factory=no_jira)
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"text": SMM_REQUEST}).json()
        events = parse_sse(client.get(task["events_url"]).text)
    assert events[-1]["status"] == "completed"
    assert "issue_key" not in events[-1]["result"]  # type: ignore[operator]
    assert not any("issue" in e for e in events)


# --- Окна интерфейса задают домен: Этап 1 не вызывается ----------------------------


def test_window_preset_domain_skips_classifier(settings: Settings) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content)["response_format"]["json_schema"]["name"])
        return smm_handler()(request)

    with make_client(settings, handler) as client:
        task = client.post("/api/tasks", json={"text": SMM_REQUEST, "domain": "SMM"}).json()
        events = parse_sse(client.get(task["events_url"]).text)
    assert calls == ["PostCopySchema"]  # классификатор не вызывался
    assert events[0]["message"] == "Домен задан окном: SMM"
    assert events[-1]["result"]["intent"]["confidence"] == 1.0  # type: ignore[index]


# --- Окно «Финансы»: бюджеты, прогноз, сравнение месяцев ---------------------------


def test_finance_forecast_and_month_over_month() -> None:
    metrics = FINANCE.analyze_csv(SAMPLE_CSV, 500_000)
    assert [p.month for p in metrics.forecast] == ["2026-11", "2026-12", "2027-01"]
    assert metrics.forecast_basis_months == 3  # октябрь неполный (выписка до 29.10) — не в базе
    mom = metrics.month_over_month
    assert mom is not None and (mom.previous_month, mom.current_month) == ("2026-08", "2026-09")
    assert metrics.budget_month == "2026-09" and metrics.last_month_by_category[0].category == "Зарплата"


def test_budgets_are_checked_and_reach_the_report(settings: Settings) -> None:
    handler = schema_router({"IntentClassificationResult": intent_json("Finance"), "FinanceReportSchema": REPORT})
    with make_client(settings, handler) as client:
        saved = client.put(
            "/api/finance/budgets",
            json={"items": [{"category": "Реклама", "limit": 300000}, {"category": "Аренда", "limit": 500000}]},
        )
        assert saved.status_code == 200 and len(client.get("/api/finance/budgets").json()["items"]) == 2
        assert client.put("/api/finance/budgets", json={"items": [{"category": "x", "limit": -1}]}).status_code == 422
        task = client.post(
            "/api/tasks",
            json={"text": "Анализ", "domain": "Finance", "attachment": {"filename": "bank.csv", "content": SAMPLE_CSV}},
        ).json()
        finance = parse_sse(client.get(task["events_url"]).text)[-1]["result"]["finance"]  # type: ignore[index]
        report_id = finance["report_file"]["report_id"]
        assert client.post(f"/api/finance/reports/{report_id}/telegram").status_code == 409  # бот не настроен
        assert client.delete(f"/api/finance/reports/{report_id}").status_code == 204
        assert client.get(f"/api/finance/reports/{report_id}.pdf").status_code == 404
    checks = {c["category"]: c for c in finance["budget_checks"]}
    assert checks["Реклама"]["over"] is True and checks["Реклама"]["spent"] > 300000
    assert checks["Аренда"]["over"] is False and checks["Аренда"]["remaining"] == 50000
