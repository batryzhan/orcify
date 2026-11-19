from __future__ import annotations

import io
import json

import httpx
from docx import Document
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import VALID_IIN, Handler, chat_response, entities_json, intent_json, schema_router

Event = dict[str, object]


def parse_sse(body: str) -> list[Event]:
    events = []
    for block in body.strip().split("\n\n"):
        data_lines = [line.removeprefix("data: ") for line in block.splitlines() if line.startswith("data: ")]
        events.append(json.loads("".join(data_lines)))
    return events


def make_test_client(settings: Settings, handler: Handler) -> TestClient:
    return TestClient(create_app(settings, llm_transport=httpx.MockTransport(handler)))


def run_task(client: TestClient, text: str) -> list[Event]:
    created = client.post("/api/tasks", json={"text": text})
    assert created.status_code == 201
    stream = client.get(created.json()["events_url"])
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    return parse_sse(stream.text)


def docx_text(content: bytes) -> str:
    doc = Document(io.BytesIO(content))
    parts = [p.text for p in doc.paragraphs]
    parts += [cell.text for table in doc.tables for row in table.rows for cell in row.cells]
    return "\n".join(parts)


def test_legal_scenario_renders_contract(settings: Settings) -> None:
    handler = schema_router(
        {"IntentClassificationResult": intent_json("Legal", 0.95), "ContractEntitiesSchema": entities_json()}
    )
    with make_test_client(settings, handler) as client:
        events = run_task(client, "ТОО Тест-пен 500 000 теңгеге жыл соңына дейін келісімшарт жаса")

        assert [(e["status"], e["progress"]) for e in events] == [
            ("classifying_intent", 5),
            ("creating_jira_issue", 10),
            ("updating_jira", 20),
            ("extracting_entities", 50),
            ("rendering_docx", 80),
            ("updating_jira", 95),
            ("completed", 100),
        ]
        legal = events[-1]["result"]["legal"]  # type: ignore[index]
        # Orcify Jira-дағы карточка Орындалуға -> Жұмыста -> Дайын жолынан өтті және келісімшартқа сілтемені сақтайды.
        key = events[-1]["result"]["issue_key"]  # type: ignore[index]
        assert [e["issue"]["status"] for e in events if "issue" in e] == ["todo", "in_progress", "done"]
        issue = next(i for i in client.get("/api/jira/board").json()["issues"] if i["key"] == key)
        assert issue["status"] == "done" and issue["assignee"] == "Lawyer"
        assert issue["attachments"][0]["url"] == legal["document"]["download_url"]
        assert "ТОО" not in issue["summary"]  # карточкаға клиент атауы көшірілмейді
        assert legal["outcome"] == "rendered"
        document = legal["document"]

        download = client.get(document["download_url"])
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert document["filename"] in download.headers["content-disposition"]
        assert len(download.content) == document["size_bytes"]

        text = docx_text(download.content)
        assert "ТОО «Тест & Ко»" in text  # & дұрыс экрандалған және қалпына келтірілген
        assert VALID_IIN in text
        assert "500 000,00 теңге" in text
        assert "«31» желтоқсан 2026 ж." in text
        assert "Корпоративтік сайтты әзірлеу" in text
        assert "{{" not in text and "}}" not in text


def test_legal_scenario_needs_input_when_fields_missing_or_invalid(settings: Settings) -> None:
    handler = schema_router(
        {
            "IntentClassificationResult": intent_json("Legal"),
            "ContractEntitiesSchema": entities_json(bin_iin="900101300018", deadline_date=None),
        }
    )
    with make_test_client(settings, handler) as client:
        events = run_task(client, "келісімшарт")

    assert [e["status"] for e in events] == [
        "classifying_intent", "creating_jira_issue", "updating_jira", "extracting_entities", "updating_jira", "completed",
    ]
    assert events[-2]["issue"]["status"] == "review"  # type: ignore[index]
    assert "NEEDS INPUT" in events[-2]["issue"]["labels"]  # type: ignore[index]
    legal = events[-1]["result"]["legal"]  # type: ignore[index]
    assert legal["outcome"] == "needs_input"
    assert legal["missing_fields"] == ["deadline_date"]
    assert legal["invalid_fields"] == ["bin_iin"]
    assert "document" not in legal


def test_render_contract_endpoint_without_llm(settings: Settings) -> None:
    def no_llm(_req: httpx.Request) -> httpx.Response:
        raise AssertionError("LLM must not be called")

    contract = json.loads(entities_json())
    with make_test_client(settings, no_llm) as client:
        created = client.post("/api/legal/contracts", json=contract)
        assert created.status_code == 201
        assert client.get(created.json()["download_url"]).status_code == 200

        bad = client.post("/api/legal/contracts", json=contract | {"bin_iin": "900101300018"})
        assert bad.status_code == 422
        assert "900101300018" not in json.dumps([e["msg"] for e in bad.json()["detail"]])


def test_stream_is_single_use(settings: Settings) -> None:
    with make_test_client(settings, lambda _req: chat_response(intent_json("HR"))) as client:
        url = client.post("/api/tasks", json={"text": "x"}).json()["events_url"]
        assert client.get(url).status_code == 200
        assert client.get(url).status_code == 404  # тапсырма мәтіні жадтан өшірілген


def test_low_confidence_flag(settings: Settings) -> None:
    with make_test_client(settings, lambda _req: chat_response(intent_json("Finance", 0.3))) as client:
        final = run_task(client, "бірдеңе")[-1]
    assert final["result"]["low_confidence"] is True  # type: ignore[index]


def test_task_degrades_when_llm_down(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with make_test_client(settings, handler) as client:
        final = run_task(client, "келісімшарт")[-1]  # күйі 200, қате оқиғамен келеді
    assert final["status"] == "failed"
    assert final["error"]["code"] == "connection_error"  # type: ignore[index]
    assert "issue" not in final  # жіктеуге дейін карточка жасалмайды


def test_extraction_failure_is_reported(settings: Settings) -> None:
    handler = schema_router({"IntentClassificationResult": intent_json("Legal"), "ContractEntitiesSchema": "oops"})
    with make_test_client(settings, handler) as client:
        events = run_task(client, "келісімшарт")
    assert events[-1]["status"] == "failed"
    assert events[-1]["error"]["code"] == "schema_mismatch"  # type: ignore[index]
    assert "ERROR" in events[-1]["issue"]["labels"]  # type: ignore[index]


def test_create_task_validates_input(settings: Settings) -> None:
    with make_test_client(settings, lambda _req: chat_response(intent_json())) as client:
        assert client.post("/api/tasks", json={"text": ""}).status_code == 422
        assert client.post("/api/tasks", json={"text": "x", "extra": 1}).status_code == 422


def test_unknown_ids_return_404(settings: Settings) -> None:
    zero = "00000000-0000-0000-0000-000000000000"
    with make_test_client(settings, lambda _req: chat_response(intent_json())) as client:
        assert client.get(f"/api/tasks/{zero}/events").status_code == 404
        assert client.get(f"/api/documents/{zero}").status_code == 404


def test_health_degraded_when_llm_unauthorized(settings: Settings) -> None:
    with make_test_client(settings, lambda _req: httpx.Response(401)) as client:
        body = client.get("/api/health").json()
    assert body["status"] == "degraded"
    assert body["llm"]["error_code"] == "unauthorized"
