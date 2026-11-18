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
        events = run_task(client, "Сделай договор с ТОО Тест на 500 000 тенге до конца года")

        assert [(e["status"], e["progress"]) for e in events] == [
            ("classifying_intent", 5),
            ("extracting_entities", 50),
            ("rendering_docx", 85),
            ("completed", 100),
        ]
        legal = events[-1]["result"]["legal"]  # type: ignore[index]
        assert legal["outcome"] == "rendered"
        document = legal["document"]

        download = client.get(document["download_url"])
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert document["filename"] in download.headers["content-disposition"]
        assert len(download.content) == document["size_bytes"]

        text = docx_text(download.content)
        assert "ТОО «Тест & Ко»" in text  # & корректно экранирован и восстановлен
        assert VALID_IIN in text
        assert "500 000,00 тенге" in text
        assert "«31» декабря 2026 г." in text
        assert "Разработка корпоративного сайта" in text
        assert "{{" not in text and "}}" not in text


def test_legal_scenario_needs_input_when_fields_missing_or_invalid(settings: Settings) -> None:
    handler = schema_router(
        {
            "IntentClassificationResult": intent_json("Legal"),
            "ContractEntitiesSchema": entities_json(bin_iin="900101300018", deadline_date=None),
        }
    )
    with make_test_client(settings, handler) as client:
        events = run_task(client, "договор")

    assert [e["status"] for e in events] == ["classifying_intent", "extracting_entities", "completed"]
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


def test_non_legal_domain_stops_after_routing(settings: Settings) -> None:
    with make_test_client(settings, lambda _req: chat_response(intent_json("HR", 0.92))) as client:
        events = run_task(client, "Приказ о приёме на работу")

    assert [e["status"] for e in events] == ["classifying_intent", "completed"]
    result = events[-1]["result"]
    assert result == {  # type: ignore[comparison-overlap]
        "intent": {"domain": "HR", "confidence": 0.92, "reasoning": "Запрос на договор."},
        "low_confidence": False,
    }


def test_stream_is_single_use(settings: Settings) -> None:
    with make_test_client(settings, lambda _req: chat_response(intent_json("HR"))) as client:
        url = client.post("/api/tasks", json={"text": "x"}).json()["events_url"]
        assert client.get(url).status_code == 200
        assert client.get(url).status_code == 404  # текст задачи уже удалён из памяти


def test_low_confidence_flag(settings: Settings) -> None:
    with make_test_client(settings, lambda _req: chat_response(intent_json("SMM", 0.3))) as client:
        final = run_task(client, "что-нибудь")[-1]
    assert final["result"]["low_confidence"] is True  # type: ignore[index]


def test_task_degrades_when_llm_down(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with make_test_client(settings, handler) as client:
        final = run_task(client, "договор")[-1]  # статус 200, ошибка приходит событием
    assert final["status"] == "failed"
    assert final["error"]["code"] == "connection_error"  # type: ignore[index]


def test_extraction_failure_is_reported(settings: Settings) -> None:
    handler = schema_router({"IntentClassificationResult": intent_json("Legal"), "ContractEntitiesSchema": "oops"})
    with make_test_client(settings, handler) as client:
        events = run_task(client, "договор")
    assert events[-1]["status"] == "failed"
    assert events[-1]["error"]["code"] == "schema_mismatch"  # type: ignore[index]


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
