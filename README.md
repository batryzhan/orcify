# Orcify

Локальная оркестрация бизнес-процессов на компактной LLM (**Gemma 4 E4B**) через **Model Context Protocol**.
Чувствительные данные обрабатываются на устройстве; во внешние MCP-серверы уходят только анонимизированные токены.

Архитектурный стандарт и правила разработки — [CLAUDE.md](CLAUDE.md). Научная часть — [docs/](docs/).

## Что умеет

| Сценарий | Что происходит | Где данные |
|---|---|---|
| **А. Legal** | Переписка → Gemma извлекает реквизиты (Structured Output) → Pydantic проверяет ИИН/БИН, суммы, даты → `docxtpl` рендерит договор `.docx` | полностью локально |
| **Б. SMM** | Запрос → Gemma пишет сценарий и раскадровку → `LocalAnonymizer` маскирует PII → Higgsfield MCP (видео) → Atlassian MCP (задача). Если внешний сервис недоступен — storyboard и локальная очередь синхронизации | наружу — только `[PERSON_1]`, `[COMPANY_1]`… |
| **В. Finance** | CSV-выписка → локальный MCP-сервер на `pandas` считает агрегаты → Gemma пишет резюме **только по агрегатам** → отчёт `.md` | полностью локально |
| HR | Домен определяется; пайплайн — следующий этап | — |

Smart Routing: сначала классификация домена, затем в контекст попадают только MCP-инструменты этого домена.

## Требования

- Python 3.11+ (проверено на 3.14), Node.js 20+ (проверено на 24)
- [Unsloth Studio](https://unsloth.ai) с загруженной моделью `unsloth/gemma-4-E4B-it-GGUF` и API-ключом
- Видеокарта с 6 ГБ VRAM достаточно (проверено на RTX 4050 Laptop)

## Запуск

### 1. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env   # впишите ORCIFY_LLM_API_KEY из Unsloth Studio
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

API-документация: http://127.0.0.1:8000/docs

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Откройте http://localhost:5173 — кнопки «Примеры» заполняют форму синтетическими данными для каждого сценария.

### 3. Внешние MCP-серверы (необязательно)

Без настройки Higgsfield, Atlassian и n8n работают в режиме **Graceful Degradation** (storyboard + очередь
`backend/var/sync_queue.jsonl`, только анонимизированные данные). Чтобы подключить реальные серверы, задайте в `backend/.env`:

```
ORCIFY_HIGGSFIELD_MCP_URL=https://…/mcp
ORCIFY_HIGGSFIELD_MCP_TOKEN=…
ORCIFY_ATLASSIAN_MCP_URL=https://…/mcp
ORCIFY_ATLASSIAN_MCP_TOKEN=…
ORCIFY_ATLASSIAN_PROJECT_KEY=MKT
```

Реквизиты Исполнителя для договора: `ORCIFY_EXECUTOR_NAME`, `ORCIFY_EXECUTOR_BIN`, `ORCIFY_EXECUTOR_SIGNATORY`.

## Тесты и замеры

```powershell
cd backend
.venv\Scripts\python -m pytest                          # юнит- и интеграционные тесты (без LLM)
$env:ORCIFY_LIVE_TESTS=1; .venv\Scripts\python -m pytest -m live -s   # против запущенной Gemma
.venv\Scripts\python scripts\benchmark.py                # замеры для docs/metrics.md
```

```powershell
cd frontend
npm test
npm run build
```

> Для замеров держите ноутбук на зарядке и отключите сон: в режиме Modern Standby генерация замедляется в десятки раз.

## Структура

```text
backend/app/core/        router, llm_client, anonymizer, doc_engine, legal/finance/smm-сервисы, pipeline, logger
backend/app/mcp/         MCPServerManager (реестр, домены, анонимизация внешних вызовов, fallback), очередь синхронизации
backend/app/schemas/     Pydantic-контракты (зеркалируются в frontend/src/types/api.ts)
backend/prompts/         все системные промпты (.md)
backend/templates/       шаблон договора service_contract_kz.docx
backend/benchmarks/      синтетический набор для замеров
mcp_servers/local_finance_server/   локальный MCP-сервер анализа CSV (stdio)
frontend/src/            React: useSSE, ProgressStepper, PrivacyBadge, WorkspaceView, экраны доменов
docs/                    metrics.md, experiments.md, privacy_audit.md, results/*.json
```
