"""Воспроизводимые замеры для docs/metrics.md и docs/experiments.md.

Запуск из папки backend (нужен запущенный Unsloth Studio):
    .venv\\Scripts\\python scripts\\benchmark.py [--only routing,tools,pii,legal] [--repeat 1]

Все данные — синтетические (benchmarks/dataset.json). Результаты пишутся в
docs/results/benchmark_<время>.json. Вызовы идут последовательно, чтобы
задержки не искажались конкуренцией за GPU.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, create_model

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BACKEND_DIR, Settings  # noqa: E402
from app.core.anonymizer import LocalAnonymizer  # noqa: E402
from app.core.doc_engine import DocEngine  # noqa: E402
from app.core.document_store import DocumentStore  # noqa: E402
from app.core.legal_service import LegalService  # noqa: E402
from app.core.llm_client import ChatMessage, LLMClient, LLMError, LLMCallStats, build_http_client  # noqa: E402
from app.core.prompts import PromptLoader  # noqa: E402
from app.core.router import IntentRouter  # noqa: E402

DATASET = BACKEND_DIR / "benchmarks" / "dataset.json"
RESULTS_DIR = BACKEND_DIR.parent / "docs" / "results"


class CallRecord(BaseModel):
    ok: bool
    correct: bool
    latency_ms: int
    server_predicted_ms: int | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    first_attempt_valid: bool = False
    error_code: str | None = None
    expected: str | None = None
    got: str | None = None


def stats_record(stats: LLMCallStats, **kw: object) -> CallRecord:
    return CallRecord(
        ok=True,
        latency_ms=stats.latency_ms,
        server_predicted_ms=stats.server_predicted_ms,
        prompt_tokens=stats.prompt_tokens,
        completion_tokens=stats.completion_tokens,
        first_attempt_valid=stats.attempts == 1,
        **kw,  # type: ignore[arg-type]
    )


def summarize(records: list[CallRecord]) -> dict[str, float | int]:
    lat = sorted(r.latency_ms for r in records if r.ok)
    ok = [r for r in records if r.ok]

    def pct(p: float) -> int:
        return lat[min(len(lat) - 1, round(p * (len(lat) - 1)))] if lat else 0

    return {
        "n": len(records),
        "accuracy": round(sum(r.correct for r in records) / len(records), 4) if records else 0.0,
        "json_valid_first_attempt": round(sum(r.first_attempt_valid for r in records) / len(records), 4) if records else 0.0,
        "failed_calls": len(records) - len(ok),
        "latency_ms_mean": round(statistics.mean(lat)) if lat else 0,
        "latency_ms_p50": pct(0.5),
        "latency_ms_p95": pct(0.95),
        "prompt_tokens_mean": round(statistics.mean(r.prompt_tokens for r in ok)) if ok else 0,
        "completion_tokens_mean": round(statistics.mean(r.completion_tokens for r in ok)) if ok else 0,
    }


async def bench_routing(router: IntentRouter, data: list[dict[str, str]]) -> list[CallRecord]:
    records = []
    for item in data:
        try:
            r = await router.classify(item["text"])
            got = r.data.domain.value
            records.append(stats_record(r.stats, correct=got == item["domain"], expected=item["domain"], got=got))
        except LLMError as exc:
            records.append(CallRecord(ok=False, correct=False, latency_ms=0, error_code=exc.code, expected=item["domain"]))
        print(f"  routing {len(records)}/{len(data)} -> {records[-1].got} ({records[-1].latency_ms} ms)", flush=True)
    return records


def tool_choice_model(names: list[str]) -> type[BaseModel]:
    literal = Literal.__getitem__(tuple(names))  # type: ignore[attr-defined]
    return create_model("ToolChoice", __config__=ConfigDict(extra="forbid"), tool=(literal, ...))


async def bench_tools(
    llm: LLMClient, prompts: PromptLoader, catalog: list[dict[str, str]], data: list[dict[str, str]], scoped: bool
) -> list[CallRecord]:
    records = []
    for item in data:
        tools = [t for t in catalog if not scoped or t["domain"] == item["domain"]]
        listing = "\n".join(f"- {t['name']}: {t['description']}" for t in tools)
        schema = tool_choice_model([t["name"] for t in tools])
        messages = [
            ChatMessage(role="system", content=prompts.load("tool_selector", tools=listing)),
            ChatMessage(role="user", content=item["text"]),
        ]
        try:
            r = await llm.structured(messages, schema, stage="tool_selection")
            got = str(getattr(r.data, "tool"))
            records.append(stats_record(r.stats, correct=got == item["tool"], expected=item["tool"], got=got))
        except LLMError as exc:
            records.append(CallRecord(ok=False, correct=False, latency_ms=0, error_code=exc.code, expected=item["tool"]))
        mode = "scoped" if scoped else "full"
        print(f"  tools[{mode}] {len(records)}/{len(data)} -> {records[-1].got} ({records[-1].latency_ms} ms)", flush=True)
    return records


async def bench_pii(anonymizer: LocalAnonymizer, data: list[dict[str, object]], use_llm: bool) -> dict[str, object]:
    total = leaked = 0
    per_item = []
    started = time.monotonic()
    for item in data:
        text = str(item["text"])
        values = [str(v) for v in item["values"]]  # type: ignore[attr-defined]
        session = await anonymizer.build_session([text], use_llm=use_llm)
        out = session.anonymize(text)
        missed = [v for v in values if v.lower() in out.lower()]
        total += len(values)
        leaked += len(missed)
        # Данные синтетические, поэтому пропущенные значения можно сохранить для разбора ошибок.
        per_item.append({"values": len(values), "leaked": len(missed), "missed": missed})
        session.clear()
    return {
        "mode": "regex+llm" if use_llm else "regex_only",
        "pii_values_total": total,
        "pii_values_leaked": leaked,
        "pii_leakage_rate": round(leaked / total, 4) if total else 0.0,
        "elapsed_s": round(time.monotonic() - started, 1),
        "per_item": per_item,
    }


async def bench_legal(legal: LegalService, data: list[dict[str, object]]) -> dict[str, object]:
    fields = ["bin_iin", "contract_amount", "currency", "deadline_date"]
    correct = {f: 0 for f in fields}
    records = []
    for item in data:
        gold: dict[str, str | None] = item["gold"]  # type: ignore[assignment]
        try:
            r = await legal.extract(str(item["text"]))
        except LLMError as exc:
            records.append(CallRecord(ok=False, correct=False, latency_ms=0, error_code=exc.code))
            continue
        e = r.data
        got = {
            "bin_iin": e.bin_iin,
            "contract_amount": str(e.contract_amount.normalize()) if e.contract_amount is not None else None,
            "currency": e.currency.value if e.currency else None,
            "deadline_date": e.deadline_date.isoformat() if e.deadline_date else None,
        }
        gold_norm = {k: (str(Decimal(v).normalize()) if k == "contract_amount" and v else v) for k, v in gold.items()}
        hits = {f: got[f] == gold_norm[f] for f in fields}
        for f, hit in hits.items():
            correct[f] += hit
        records.append(stats_record(r.stats, correct=all(hits.values())))
        print(f"  legal {len(records)}/{len(data)} -> {sum(hits.values())}/4 fields ({r.stats.latency_ms} ms)", flush=True)
    n = len(data)
    return {
        "summary": summarize(records),
        "field_accuracy": {f: round(c / n, 4) for f, c in correct.items()},
        "documents_fully_correct": round(sum(r.correct for r in records) / n, 4),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="routing,tools,pii,legal")
    args = parser.parse_args()
    parts = set(args.only.split(","))

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    settings = Settings()
    results: dict[str, object] = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "model": settings.llm_model,
        "endpoint": "Unsloth Studio (llama.cpp), local",
    }

    async with build_http_client(settings) as http:
        llm = LLMClient(settings, http)
        prompts = PromptLoader(settings.prompts_dir)
        health = await llm.health()
        results["llm_health"] = health.model_dump()

        if "routing" in parts:
            print("Smart Routing (Этап 1)…", flush=True)
            recs = await bench_routing(IntentRouter(llm, prompts, settings), data["routing"])
            results["routing"] = {"summary": summarize(recs), "records": [r.model_dump() for r in recs]}

        if "tools" in parts:
            print("Smart Routing vs Full Context (выбор инструмента)…", flush=True)
            scoped = await bench_tools(llm, prompts, data["tool_catalog"], data["tool_selection"], scoped=True)
            full = await bench_tools(llm, prompts, data["tool_catalog"], data["tool_selection"], scoped=False)
            results["tool_selection"] = {
                "catalog_size": len(data["tool_catalog"]),
                "scoped": {"summary": summarize(scoped), "records": [r.model_dump() for r in scoped]},
                "full_context": {"summary": summarize(full), "records": [r.model_dump() for r in full]},
            }

        if "pii" in parts:
            print("PII Leakage…", flush=True)
            anonymizer = LocalAnonymizer(llm, prompts)
            results["pii"] = {
                "regex_only": await bench_pii(anonymizer, data["pii"], use_llm=False),
                "regex_llm": await bench_pii(anonymizer, data["pii"], use_llm=True),
            }

        if "legal" in parts:
            print("Legal extraction…", flush=True)
            legal = LegalService(llm, prompts, DocEngine(settings.templates_dir, settings), DocumentStore(60), settings)
            results["legal"] = await bench_legal(legal, data["legal"])

    results["finished_at"] = datetime.now().isoformat(timespec="seconds")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"benchmark_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nsaved {out}")
    for key in ("routing", "legal"):
        if key in results:
            print(key, json.dumps(results[key]["summary"], ensure_ascii=False))  # type: ignore[index]
    if "tool_selection" in results:
        ts = results["tool_selection"]
        print("tools scoped", json.dumps(ts["scoped"]["summary"]))  # type: ignore[index]
        print("tools full  ", json.dumps(ts["full_context"]["summary"]))  # type: ignore[index]
    if "pii" in results:
        for mode, r in results["pii"].items():  # type: ignore[union-attr]
            print("pii", mode, r["pii_values_leaked"], "/", r["pii_values_total"], "rate", r["pii_leakage_rate"])


if __name__ == "__main__":
    asyncio.run(main())
