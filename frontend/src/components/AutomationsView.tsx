import { useEffect, useState } from "react";

import { api } from "../lib/api";
import type { TelegramStatus } from "../types/api";
import { McpStatusPanel } from "./McpStatusPanel";

interface FlowNode {
  title: string;
  detail: string;
  tone: string;
  glyph: string;
}

const FLOW: FlowNode[] = [
  { title: "Telegram Trigger", detail: "@orcify_bot-қа хабарлама немесе CSV", tone: "#2aabee", glyph: "✈" },
  { title: "Smart Router", detail: "Gemma 4 · тапсырма домені", tone: "#1d7afc", glyph: "◆" },
  { title: "Домен агенті", detail: "Posts · Finance · Legal · HR", tone: "#e774bb", glyph: "✦" },
  { title: "Orcify Jira", detail: "ORC тақтасындағы карточка", tone: "#22a06b", glyph: "▦" },
  { title: "Чатқа жауап", detail: "пост, есеп, келісімшарт, жоспар", tone: "#f38a3f", glyph: "↩" },
];

const COMMANDS: [string, string][] = [
  ["Кез келген мәтін", "агенттерге тапсырма: «Instagram үшін пост жаса…», «Онбординг жоспарын құр…», келісімшарт үшін хат-алмасу"],
  ["CSV-құжат", "үзіндінің жергілікті қаржылық талдауы (файлға жазба — тапсырманы нақтылау)"],
  ["/board", "Orcify Jira тақтасының бағандар бойынша қорытындысы"],
  ["/start, /help", "анықтама"],
];

/** Автоматтандыру: n8n стиліндегі воркфлоу ретінде Telegram-бот, бірақ сыртқы оркестраторсыз. */
export function AutomationsView() {
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .telegramStatus()
        .then((s) => {
          if (!alive) return;
          setStatus(s);
          setDown(false);
        })
        .catch(() => alive && setDown(true));
    void load();
    const id = window.setInterval(load, 5000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  const live = status?.polling ?? false;
  const username = status?.bot_username ?? "orcify_bot";

  return (
    <div className="px-4 pb-16 pt-5 sm:px-8">
      <nav className="text-sm text-ink-soft">
        Жобалар <span className="text-ink-mute">/</span> Orcify
      </nav>
      <h1 className="mt-1 text-2xl font-semibold text-ink">Автоматтандыру</h1>
      <p className="mt-1 max-w-2xl text-sm text-ink-soft">
        Telegram-бот тақтадағы сол агенттерді іске қосады: чаттағы тапсырма Orcify Jira карточкасына айналады, ал нәтиже
        чатқа қайтарылады. n8n воркфлоуы сияқты, тек оркестратор — жергілікті Gemma.
      </p>

      <section className="mt-6 rounded-lg bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-center gap-3">
          <span className={`h-2.5 w-2.5 rounded-full ${live ? "animate-pulse bg-[#22a06b]" : status?.configured ? "bg-warn" : "bg-ink-mute/40"}`} />
          <p className="font-semibold text-ink">
            {down
              ? "Бэкенд қолжетімсіз"
              : !status
                ? "Жүктелуде…"
                : !status.configured
                  ? "Бот бапталмаған"
                  : live
                    ? `@${username} хабарламаларды тыңдайды`
                    : "Бот бапталған, бірақ іске қосылмаған"}
          </p>
          <a href={`https://t.me/${username}`} target="_blank" rel="noreferrer" className="btn-primary ml-auto">
            @{username} ашу
          </a>
        </div>
        {status && !status.configured && (
          <p className="mt-3 text-sm text-ink-soft">
            @BotFather-ден токенді <code className="rounded bg-paper-col px-1 font-mono text-xs">backend/.env</code> ішіне{" "}
            <code className="rounded bg-paper-col px-1 font-mono text-xs">TELEGRAM_BOT_API_KEY=…</code> ретінде қосыңыз да, бэкендті қайта іске қосыңыз.
          </p>
        )}
        {status?.last_error && <p className="mt-3 text-xs text-warn">Bot API-дың соңғы қатесі: {status.last_error}</p>}
        {status && (
          <dl className="mt-5 grid grid-cols-3 gap-4 border-t border-paper-line pt-4">
            {[
              ["Чаттар", status.linked_chats],
              ["Хабарламалар", status.handled_messages],
              ["Орындалған тапсырмалар", status.completed_runs],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs text-ink-mute">{label}</dt>
                <dd className="text-2xl font-semibold tabular-nums text-ink">{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <section className="mt-6 overflow-x-auto rounded-lg bg-[#1d2125] p-6 shadow-card" aria-label="Воркфлоу">
        <div className="flex min-w-[720px] items-center">
          {FLOW.map((node, i) => (
            <div key={node.title} className="flex flex-1 items-center">
              <div className="flex w-32 shrink-0 flex-col items-center text-center">
                <div
                  className="flex h-16 w-16 items-center justify-center rounded-2xl border-2 bg-[#22272b] text-2xl text-white"
                  style={{ borderColor: node.tone, boxShadow: live ? `0 0 18px ${node.tone}55` : undefined }}
                >
                  <span style={{ color: node.tone }}>{node.glyph}</span>
                </div>
                <p className="mt-2 text-sm font-semibold text-white">{node.title}</p>
                <p className="text-xs text-white/55">{node.detail}</p>
              </div>
              {i < FLOW.length - 1 && (
                <svg className="mx-1 h-4 w-0 min-w-[24px] flex-1" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden>
                  <line
                    x1="0"
                    y1="5"
                    x2="100"
                    y2="5"
                    stroke="#8c9bab"
                    strokeWidth="2"
                    strokeDasharray="6 4"
                    className={live ? "animate-dash" : ""}
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
              )}
            </div>
          ))}
        </div>
      </section>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="rounded-lg bg-white p-5 shadow-card">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-soft">Бот нені түсінеді</h2>
          <dl className="space-y-3 text-sm">
            {COMMANDS.map(([cmd, text]) => (
              <div key={cmd} className="grid grid-cols-[120px_minmax(0,1fr)] gap-3">
                <dt className="font-mono text-xs font-semibold text-ink">{cmd}</dt>
                <dd className="text-ink-soft">{text}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 rounded-md bg-paper p-3 text-xs text-ink-soft">
            Құпиялылық: Telegram — бұлттық сервис. Бот тек тапсырма келген чатқа жауап береді және өздігінен ештеңе жарияламайды.
            Модель, трекер және пост рендері жергілікті жұмыс істейді; бот токені логқа жазылмайды.
          </p>
        </section>
        <McpStatusPanel activeDomain={null} />
      </div>
    </div>
  );
}
