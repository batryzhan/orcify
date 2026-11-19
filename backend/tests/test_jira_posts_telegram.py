"""Orcify Jira (хранилище и API), рендер Awesome Posts и Telegram-бот с мок-API."""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr

from app.channels.telegram import TelegramBot
from app.config import Settings
from app.core.jira_store import JiraStore
from app.core.post_renderer import HEIGHT, WIDTH, PostRenderer
from app.main import create_app
from app.schemas.jira import IssueCreate, IssueStatus, IssueUpdate
from app.schemas.smm import PostCopySchema, PostTemplate
from app.schemas.telegram import TgChat, TgDocument, TgMessage
from tests.conftest import chat_response, intent_json, schema_router
from tests.test_mcp_and_scenarios import SMM_REQUEST, smm_handler

TOKEN = "123456:TEST-SECRET-TOKEN"


# --- Orcify Jira -------------------------------------------------------------------


def test_store_starts_empty_persists_and_clears(tmp_path: Path) -> None:
    path = tmp_path / "board.json"
    store = JiraStore(path)
    board = store.board()
    assert board.project_key == "ORC" and [c.status for c in board.columns] == list(IssueStatus)
    assert board.issues == []  # никакого демо-хлама: доска начинается пустой

    a = store.create(IssueCreate(summary="Первая"))
    b = store.create(IssueCreate(summary="Вторая"))
    assert (a.key, b.key) == ("ORC-1", "ORC-2") and store.board().issues[0].key == "ORC-2"
    store.update(a.key, IssueUpdate(status=IssueStatus.DONE))
    reopened = JiraStore(path)  # повторное открытие читает файл
    assert reopened.get("ORC-2").summary == "Вторая"

    assert reopened.clear({IssueStatus.DONE}) == 1
    assert [i.key for i in reopened.board().issues] == ["ORC-2"]
    assert reopened.clear() == 1 and reopened.board().issues == []
    assert reopened.create(IssueCreate(summary="x")).key == "ORC-1"  # пустая доска — нумерация заново


def test_moving_card_puts_it_on_top_of_column(tmp_path: Path) -> None:
    store = JiraStore(None)
    a = store.create(IssueCreate(summary="A"))
    b = store.create(IssueCreate(summary="B"))
    store.update(a.key, IssueUpdate(status=IssueStatus.DONE))
    assert [i.key for i in store.board().issues] == [a.key, b.key]
    same = store.update(b.key, IssueUpdate(priority="high"))  # type: ignore[arg-type]
    assert same.status is IssueStatus.TODO and same.updated_at >= same.created_at


def test_jira_api_crud(settings: Settings) -> None:
    with TestClient(create_app(settings, llm_transport=httpx.MockTransport(lambda r: chat_response("{}")))) as client:
        assert client.get("/api/jira/board").json()["issues"] == []
        created = client.post("/api/jira/issues", json={"summary": "Сверстать лендинг", "labels": ["FRONTEND"]})
        assert created.status_code == 201
        key = created.json()["key"]
        moved = client.patch(f"/api/jira/issues/{key}", json={"status": "in_progress", "assignee": "Designer"})
        assert moved.json()["status"] == "in_progress" and moved.json()["assignee"] == "Designer"
        assert client.patch("/api/jira/issues/ORC-999", json={"status": "done"}).status_code == 404
        assert client.post("/api/jira/issues", json={"summary": ""}).status_code == 422
        assert client.delete(f"/api/jira/issues/{key}").status_code == 204
        assert client.get("/api/jira/board").json()["issues"] == []
        client.post("/api/jira/issues", json={"summary": "A", "status": "done"})
        client.post("/api/jira/issues", json={"summary": "B"})
        assert client.post("/api/jira/clear", json={"scope": "done"}).json() == {"removed": 1}
        assert client.post("/api/jira/clear", json={"scope": "all"}).json() == {"removed": 1}
        assert client.post("/api/jira/clear", json={"scope": "everything"}).status_code == 422


# --- Awesome Posts: рендер ------------------------------------------------------------


def copy(template: PostTemplate, **overrides: object) -> PostCopySchema:
    data: dict[str, object] = {
        "template": template, "kicker": "−30%", "headline": "Чёрная", "headline_accent": "Пятница",
        "subtitle": "Скидка на все тарифы до воскресенья", "cta": "Заказать", "handle": "orcify",
        "caption": "", "hashtags": [],
    }
    data.update(overrides)
    return PostCopySchema.model_validate(data)


@pytest.mark.parametrize("template", list(PostTemplate))
def test_every_template_renders_deterministically(settings: Settings, template: PostTemplate) -> None:
    renderer = PostRenderer(settings.assets_dir)
    first = renderer.render(template, copy(template))
    assert first == renderer.render(template, copy(template))  # Deterministic Core: тот же вход -> тот же PNG
    assert Image.open(io.BytesIO(first)).size == (WIDTH, HEIGHT)


def test_long_texts_are_fitted_not_crashing(settings: Settings) -> None:
    long = copy(
        PostTemplate.SUMMIT,
        headline="Очень длинный заголовок, который не влезает",
        headline_accent="и ещё бесконечно длинная акцентная строка",
        subtitle="Подзаголовок " * 12,
        kicker=None,
        cta=None,
    )
    for template in PostTemplate:
        assert Image.open(io.BytesIO(PostRenderer(settings.assets_dir).render(template, long))).size == (WIDTH, HEIGHT)


# --- Telegram-бот ----------------------------------------------------------------------


class FakeTelegram:
    """Мок Bot API: запоминает вызовы и отвечает как Telegram."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert TOKEN in request.url.path  # токен уходит только в путь запроса к Telegram
        method = request.url.path.rsplit("/", 1)[-1]
        self.calls.append((method, request.content))
        message = {"message_id": len(self.calls), "chat": {"id": 42, "type": "private"}}
        results: dict[str, object] = {
            "getMe": {"id": 1, "is_bot": True, "first_name": "Orcify", "username": "orcify_bot"},
            "getFile": {"file_id": "f1", "file_path": "documents/bank.csv", "file_size": 120},
        }
        if request.url.path.startswith("/file/"):
            return httpx.Response(200, content="date,amount\n2026-01-05,1000\n2026-01-06,-300\n".encode())
        return httpx.Response(200, json={"ok": True, "result": results.get(method, message)})

    def methods(self) -> list[str]:
        return [m for m, _ in self.calls]


def bot_app(settings: Settings, fake: FakeTelegram, llm: httpx.MockTransport) -> tuple[TestClient, Settings]:
    configured = settings.model_copy(update={"telegram_bot_token": SecretStr(TOKEN), "telegram_polling": False})
    app = create_app(configured, llm_transport=llm, telegram_transport=httpx.MockTransport(fake.handler))
    return TestClient(app), configured


def message(text: str | None = None, document: TgDocument | None = None) -> TgMessage:
    return TgMessage(message_id=7, chat=TgChat(id=42, type="private"), text=text, document=document)


def test_bot_runs_pipeline_and_replies_with_post(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    fake = FakeTelegram()
    client, configured = bot_app(settings, fake, httpx.MockTransport(smm_handler()))
    with client:
        bot: TelegramBot = client.app.state.telegram  # type: ignore[attr-defined]
        client.portal.call(bot.handle_message, message("/start"))  # type: ignore[union-attr]
        client.portal.call(bot.handle_message, message(SMM_REQUEST))  # type: ignore[union-attr]
        board = client.get("/api/jira/board").json()
        status = client.get("/api/telegram/status").json()
        post_id = client.get("/api/posts").json()[0]["post"]["post_id"]
        sent = client.post(f"/api/posts/{post_id}/telegram").json()

    methods = fake.methods()
    assert methods[0] == "sendMessage" and b"Orcify" in fake.calls[0][1]  # справка на /start
    assert "editMessageText" in methods  # ход работы обновляется в одном сообщении
    photo = next(body for m, body in fake.calls if m == "sendPhoto")
    assert b"image/png" in photo and "#orcify".encode() in photo
    assert "Orcify Jira".encode() in photo  # подпись ссылается на карточку
    assert board["issues"][0]["status"] == "done" and board["issues"][0]["summary"].startswith("Instagram-пост")
    assert status == {**status, "configured": True, "linked_chats": 1, "handled_messages": 2, "completed_runs": 1}
    assert sent == {"sent": 1, "linked_chats": 1}
    assert json.loads(configured.telegram_chats_path.read_text())  == [42]  # type: ignore[union-attr]
    assert TOKEN not in caplog.text and "TEST-SECRET" not in caplog.text  # Zero-secret logging


def test_bot_board_command_and_csv_rejection(settings: Settings) -> None:
    fake = FakeTelegram()
    client, _ = bot_app(settings, fake, httpx.MockTransport(lambda r: chat_response(intent_json("Finance"))))
    with client:
        bot: TelegramBot = client.app.state.telegram  # type: ignore[attr-defined]
        client.portal.call(bot.handle_message, message("/board"))  # type: ignore[union-attr]
        client.portal.call(  # type: ignore[union-attr]
            bot.handle_message, message(document=TgDocument(file_id="f1", file_name="photo.jpg"))
        )
    texts = [body.decode() for m, body in fake.calls if m == "sendMessage"]
    assert "Orcify Jira" in json.loads(texts[0])["text"]
    assert "CSV" in json.loads(texts[1])["text"]


def test_status_without_token(settings: Settings) -> None:
    with TestClient(create_app(settings, llm_transport=httpx.MockTransport(lambda r: chat_response("{}")))) as client:
        assert client.get("/api/telegram/status").json()["configured"] is False


def test_bot_sends_finance_pdf(settings: Settings) -> None:
    from tests.test_mcp_and_scenarios import REPORT, SAMPLE_CSV, local_factory

    fake = FakeTelegram()
    llm = httpx.MockTransport(
        schema_router({"IntentClassificationResult": intent_json("Finance"), "FinanceReportSchema": REPORT})
    )
    configured = settings.model_copy(update={"telegram_bot_token": SecretStr(TOKEN), "telegram_polling": False})
    app = create_app(configured, llm_transport=llm, telegram_transport=httpx.MockTransport(fake.handler),
                     mcp_factory=local_factory)
    with TestClient(app) as client:
        bot: TelegramBot = client.app.state.telegram  # type: ignore[attr-defined]
        client.portal.call(bot.handle_message, message("/start"))  # type: ignore[union-attr]
        task = client.post(
            "/api/tasks",
            json={"text": "Анализ", "domain": "Finance", "attachment": {"filename": "bank.csv", "content": SAMPLE_CSV}},
        ).json()
        client.get(task["events_url"])
        report_id = client.get("/api/finance/reports").json()[0]["file"]["report_id"]
        sent = client.post(f"/api/finance/reports/{report_id}/telegram").json()
    document = next(body for m, body in fake.calls if m == "sendDocument")
    assert b"application/pdf" in document and b"%PDF" in document
    assert sent == {"sent": 1, "linked_chats": 1}
