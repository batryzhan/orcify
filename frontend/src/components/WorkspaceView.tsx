import { useRef, useState, type ChangeEvent, type FormEvent } from "react";

import { useSSE } from "../hooks/useSSE";
import { api } from "../lib/api";
import { formatBytes } from "../lib/format";
import type { Domain, TaskAttachment } from "../types/api";
import { FinanceResultView } from "./FinanceResultView";
import { LegalResultView } from "./LegalResultView";
import { McpStatusPanel } from "./McpStatusPanel";
import { ProgressStepper } from "./ProgressStepper";
import { SmmResultView } from "./SmmResultView";

const MAX_CSV_BYTES = 5_000_000;
const DEMO_CSV_URL = "/samples/transactions_demo.csv";

interface Sample {
  label: string;
  text: string;
  csv?: boolean;
  openingBalance?: number;
}

/** Синтетические примеры для демонстрации (реальных персональных данных нет). */
const SAMPLES: Sample[] = [
  {
    label: "Договор из переписки",
    text: `[10:14] Менеджер: Добрый день! Готовы начать работу над сайтом.
[10:16] Клиент: Здравствуйте. Да, давайте оформим договор. Мы ТОО «Альфа Трейд», БИН 900101300017.
[10:19] Клиент: Нужна разработка корпоративного сайта на трёх языках и настройка хостинга.
[10:20] Менеджер: Стоимость, как договаривались, 1 250 000 тенге. Срок — до 15 февраля 2027 года.
[10:21] Клиент: Да, всё верно, присылайте договор.`,
  },
  {
    label: "Договор без БИН",
    text: "Подготовь договор с ИП Сериков на консультационные услуги, 300 000 тенге, срок до 1 марта.",
  },
  {
    label: "Рекламный ролик",
    text: "Сделай рекламный ролик на 15 секунд для Instagram про наш новый сервис доставки ТОО «Альфа Трейд». Покажи кейс клиента Иванов Пётр: заказ доставлен за час. Контакт для заказа +7 701 123-45-67.",
  },
  {
    label: "Анализ выписки (CSV)",
    text: "Проанализируй выписку за последние месяцы: где кассовые разрывы, крупнейшие расходы и что с этим делать.",
    csv: true,
    openingBalance: 500_000,
  },
];

const DOMAIN_LABEL: Record<Domain, string> = {
  Legal: "Юриспруденция",
  SMM: "Маркетинг",
  Finance: "Финансы",
  HR: "Кадры",
};

export function WorkspaceView() {
  const [text, setText] = useState("");
  const [attachment, setAttachment] = useState<TaskAttachment | null>(null);
  const [openingBalance, setOpeningBalance] = useState("0");
  const [eventsUrl, setEventsUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const { events, latest, startedAt, state, error } = useSSE(eventsUrl);

  const result = events.find((e) => e.data.result)?.data.result ?? null;
  const domain = [...events].reverse().find((e) => e.data.domain)?.data.domain ?? null;
  const running = state === "connecting" || state === "open";

  const attachCsv = (filename: string, content: string) => {
    setAttachment({ filename, media_type: "text/csv", content });
  };

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > MAX_CSV_BYTES) {
      setSubmitError("Файл больше 5 МБ");
      return;
    }
    // Файл читается в браузере и уходит только на локальный бэкенд.
    attachCsv(file.name, await file.text());
  };

  const applySample = async (sample: Sample) => {
    setText(sample.text);
    setSubmitError(null);
    if (sample.csv) {
      const response = await fetch(DEMO_CSV_URL);
      attachCsv("transactions_demo.csv", await response.text());
      setOpeningBalance(String(sample.openingBalance ?? 0));
    } else {
      setAttachment(null);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim() || running) return;
    setSubmitting(true);
    setSubmitError(null);
    setEventsUrl(null);
    try {
      const balance = Number(openingBalance.replace(/\s/g, "").replace(",", "."));
      const task = await api.createTask({
        text: text.trim(),
        ...(attachment ? { attachment, opening_balance: Number.isFinite(balance) ? balance : 0 } : {}),
      });
      setEventsUrl(task.events_url);
    } catch {
      setSubmitError("Бэкенд недоступен. Запустите uvicorn в папке backend.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0 space-y-6">
        <form onSubmit={submit} className="rounded-xl border border-paper-line bg-paper-card p-5">
          <label htmlFor="task-text" className="mb-2 block text-sm font-semibold text-ink">
            Задача
          </label>
          <textarea
            id="task-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void submit(e);
            }}
            rows={6}
            placeholder="Вставьте переписку с клиентом, опишите ролик или задачу по выписке…"
            className="w-full resize-y rounded-lg border border-paper-line bg-paper px-3.5 py-3 text-[15px] leading-relaxed outline-none placeholder:text-ink-mute focus:border-local/50 focus:ring-2 focus:ring-local/20"
          />

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <input ref={fileInput} type="file" accept=".csv,text/csv" className="hidden" onChange={onFile} />
            {attachment ? (
              <div className="flex flex-wrap items-center gap-3 rounded-lg border border-paper-line bg-paper px-3 py-1.5 text-sm">
                <span className="font-mono text-xs">
                  {attachment.filename} · {formatBytes(attachment.content.length)}
                </span>
                <label className="flex items-center gap-1.5 text-xs text-ink-soft">
                  Остаток на начало, ₸
                  <input
                    value={openingBalance}
                    onChange={(e) => setOpeningBalance(e.target.value)}
                    inputMode="decimal"
                    className="w-28 rounded border border-paper-line bg-white px-2 py-0.5 text-right font-mono text-xs outline-none focus:ring-2 focus:ring-local/30"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => setAttachment(null)}
                  className="text-xs text-ink-mute hover:text-fail"
                  aria-label="Убрать файл"
                >
                  ✕
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                className="rounded-lg border border-dashed border-paper-line px-3 py-1.5 text-sm text-ink-soft hover:border-ink-mute hover:text-ink"
              >
                + CSV-выписка
              </button>
            )}
            <button
              type="submit"
              disabled={!text.trim() || running || submitting}
              className="ml-auto rounded-lg bg-ink px-5 py-2 text-sm font-medium text-white enabled:hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {running || submitting ? "Выполняется…" : "Запустить"}
              <kbd className="ml-2 hidden font-sans text-[11px] text-white/50 sm:inline">Ctrl+Enter</kbd>
            </button>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-paper-line pt-3">
            <span className="mr-1 text-xs text-ink-mute">Примеры:</span>
            {SAMPLES.map((s) => (
              <button
                key={s.label}
                type="button"
                onClick={() => void applySample(s)}
                className="rounded-full border border-paper-line px-3 py-1 text-xs text-ink-soft hover:border-ink-mute hover:text-ink"
              >
                {s.label}
              </button>
            ))}
          </div>
          {submitError && <p className="mt-3 text-sm text-fail">{submitError}</p>}
        </form>

        {latest?.status === "failed" && latest.error && (
          <div role="alert" className="rounded-xl border border-fail/30 bg-fail-soft p-4 text-sm text-fail">
            <p className="font-medium">{latest.error.message}</p>
            <p className="mt-1 font-mono text-xs opacity-80">{latest.error.code}</p>
          </div>
        )}
        {error && (
          <div role="alert" className="rounded-xl border border-fail/30 bg-fail-soft p-4 text-sm text-fail">
            {error}
          </div>
        )}

        {result?.legal && <LegalResultView key={eventsUrl} result={result.legal} />}
        {result?.finance && <FinanceResultView result={result.finance} />}
        {result?.smm && <SmmResultView result={result.smm} />}
        {result && !result.legal && !result.finance && !result.smm && latest?.status === "completed" && (
          <div className="rounded-xl border border-paper-line bg-paper-card p-5 text-sm text-ink-soft">
            {latest.message}
          </div>
        )}
      </div>

      <aside className="space-y-6">
        {eventsUrl && <ProgressStepper events={events} startedAt={startedAt} state={state} domain={domain} />}
        {result && (
          <section className="rounded-xl border border-paper-line bg-paper-card p-5">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-soft">Smart Routing</h2>
            <p className="text-2xl font-semibold">{DOMAIN_LABEL[result.intent.domain]}</p>
            <p className="mt-1 font-mono text-xs text-ink-mute">
              {result.intent.domain} · уверенность {(result.intent.confidence * 100).toFixed(0)}%
            </p>
            {result.low_confidence && (
              <p className="mt-3 rounded-md bg-warn-soft px-3 py-2 text-xs text-warn">
                Низкая уверенность — проверьте результат
              </p>
            )}
            <p className="mt-3 text-sm text-ink-soft">{result.intent.reasoning}</p>
          </section>
        )}
        <McpStatusPanel activeDomain={domain} />
      </aside>
    </div>
  );
}
