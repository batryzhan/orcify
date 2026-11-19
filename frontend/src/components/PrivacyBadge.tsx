import { useEffect, useState } from "react";

import { api } from "../lib/api";
import type { HealthResponse } from "../types/api";

const ERROR_TEXT: Record<string, string> = {
  unauthorized: "API-кілт қате",
  connection_error: "Unsloth Studio іске қосылмаған",
  model_not_found: "модель жүктелмеген",
};

/** Жергілікті өңдеу индикаторы: қандай модель жұмыс істейді және деректер бұлтқа кетпейді. */
export function PrivacyBadge() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [backendDown, setBackendDown] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .health()
        .then((h) => {
          if (!alive) return;
          setHealth(h);
          setBackendDown(false);
        })
        .catch(() => alive && setBackendDown(true));
    void load();
    const id = window.setInterval(load, 15_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  const ok = health?.status === "ok";
  const model = health?.llm.model?.replace(/^unsloth\//, "").replace(/-GGUF$/, "") ?? "Gemma 4";
  const problem = backendDown
    ? "бэкенд жауап бермейді"
    : health && !ok
      ? (ERROR_TEXT[health.llm.error_code ?? ""] ?? "модель қолжетімсіз")
      : null;

  return (
    <div
      className={`flex items-center gap-2.5 rounded-full border px-3.5 py-1.5 text-xs ${
        problem ? "border-warn/30 bg-warn-soft text-warn" : "border-local/25 bg-local-soft text-local"
      }`}
      title="Сұраныстарды жергілікті модель өңдейді. Трекер, пост рендері және CSV талдауы да құрылғыда жұмыс істейді."
    >
      <span className={`h-2 w-2 rounded-full ${problem ? "bg-warn" : "bg-local"} ${ok ? "animate-pulse" : ""}`} />
      {problem ? (
        <span>Жергілікті модель: {problem}</span>
      ) : (
        <span>
          <strong className="font-semibold">Жергілікті</strong> · {model}
          {health?.llm.context_length ? ` · ctx ${health.llm.context_length}` : ""} · деректер құрылғыдан шықпайды
        </span>
      )}
    </div>
  );
}
