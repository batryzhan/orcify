import { useEffect, useState } from "react";

import type { TaskRunner } from "../../hooks/useTaskRunner";
import { AGENTS, DOMAIN_LEADS } from "../../lib/agents";
import { STAGE_LABEL, STAGE_PLAN } from "../../lib/stages";
import { Avatar } from "../icons";
import { SWARM_SIZE } from "./AgentSwarm";

/** Нижняя плашка роя: «16 агентов · этап 3 / 6», прогресс, текущее действие, время. */
export function SwarmPill({ runner, onOpenResult }: { runner: TaskRunner; onOpenResult?: () => void }) {
  const { latest, events, startedAt, running, domain } = runner;
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => setNow(performance.now()), 100);
    return () => window.clearInterval(id);
  }, [running]);

  // После завершения плашка сама исчезает через 6 с, чтобы не закрывать результат.
  const [hiddenFor, setHiddenFor] = useState<number | null>(null);
  const terminal = latest?.status === "completed" || latest?.status === "failed";
  useEffect(() => {
    if (!terminal) return;
    const id = window.setTimeout(() => setHiddenFor(events.length), 6000);
    return () => window.clearTimeout(id);
  }, [terminal, events.length]);

  if (!latest && !running) return null;
  if (terminal && hiddenFor === events.length) return null;
  const plan = STAGE_PLAN[domain ?? "unknown"];
  const reached = new Set(events.map((e) => e.data.status));
  const step = Math.max(1, plan.filter((s) => reached.has(s)).length);
  const failed = latest?.status === "failed";
  const completed = latest?.status === "completed";
  const end = events.at(-1)?.at ?? now;
  const elapsed = startedAt !== null ? ((running ? now : end) - startedAt) / 1000 : 0;
  const leads = domain ? DOMAIN_LEADS[domain] : ["Router"];
  const message = failed ? latest?.error?.message : (latest?.message ?? "Агенты подключаются…");

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-[70] flex justify-center px-4">
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-auto flex max-w-[min(760px,100%)] items-center gap-3 rounded-full bg-[#1d2125]/95 py-2 pl-2.5 pr-2 text-sm text-white shadow-raised backdrop-blur"
      >
        <span className="flex -space-x-1.5">
          {leads.map((name) => (
            <Avatar key={name} name={AGENTS[name]?.name ?? name} size={22} />
          ))}
        </span>
        <span className="whitespace-nowrap font-semibold tabular-nums">
          {SWARM_SIZE} агентов
        </span>
        <span className="hidden whitespace-nowrap tabular-nums text-white/60 sm:inline">
          {Math.min(step, plan.length)} / {plan.length} этапов
        </span>
        <span className="hidden h-1 w-20 overflow-hidden rounded-full bg-white/15 sm:block" aria-hidden>
          <span
            className={`block h-full rounded-full transition-[width] duration-500 ${failed ? "bg-[#f87168]" : completed ? "bg-[#4bce97]" : "bg-[#579dff]"}`}
            style={{ width: `${latest?.progress ?? 3}%` }}
          />
        </span>
        <span className={`min-w-0 truncate ${failed ? "text-[#fd9891]" : "text-white/80"}`} title={message ?? ""}>
          {completed ? "Готово" : (message ?? STAGE_LABEL[latest?.status ?? "classifying_intent"])}
        </span>
        <span className="whitespace-nowrap font-mono text-xs tabular-nums text-white/50">{elapsed.toFixed(1)} с</span>
        {completed && onOpenResult && (
          <button type="button" onClick={onOpenResult} className="whitespace-nowrap rounded-full bg-white px-3 py-1 text-xs font-semibold text-[#1d2125] hover:bg-white/90">
            Открыть результат
          </button>
        )}
      </div>
    </div>
  );
}
