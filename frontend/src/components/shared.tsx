import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import type { TaskRunner } from "../hooks/useTaskRunner";
import { ApiError } from "../lib/api";
import type { SendPostResponse } from "../types/api";
import { SendIcon } from "./icons";
import { AgentSwarm } from "./swarm/AgentSwarm";
import { SwarmPill } from "./swarm/SwarmPill";

/** Заголовок окна: хлебные крошки, название, пояснение и действия справа. */
export function WindowHeader({ title, children, actions }: { title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-5">
      <nav className="text-sm text-ink-soft" aria-label="Навигация">
        Проекты <span className="text-ink-mute">/</span> Orcify
      </nav>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-ink">{title}</h1>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children && <p className="mt-1 max-w-3xl text-sm text-ink-soft">{children}</p>}
    </header>
  );
}

/**
 * Рой агентов + нижняя плашка для одного окна. Рой появляется на каждую новую
 * задачу этого окна и строит элемент `focusSelector` (превью поста, отчёт, карточку).
 */
export function AgentStage({
  runner,
  focusSelector,
  scopeSelector,
  pulse,
  onOpenResult,
  hidePill = false,
}: {
  runner: TaskRunner;
  focusSelector: string | null;
  scopeSelector: string;
  pulse?: string | null;
  onOpenResult?: () => void;
  hidePill?: boolean;
}) {
  const [swarmTask, setSwarmTask] = useState<string | null>(null);
  useEffect(() => {
    if (runner.taskId && runner.running) setSwarmTask(runner.taskId);
  }, [runner.taskId, runner.running]);

  return (
    <>
      {swarmTask && swarmTask === runner.taskId && (
        <AgentSwarm
          key={swarmTask}
          status={runner.latest?.status ?? null}
          domain={runner.domain}
          focusSelector={focusSelector}
          pulse={pulse === undefined ? (runner.latest?.status ?? null) : pulse}
          scopeSelector={scopeSelector}
          onFinished={() => setSwarmTask(null)}
        />
      )}
      {!hidePill && <SwarmPill runner={runner} onOpenResult={onOpenResult} />}
    </>
  );
}

export interface ComposerSample {
  label: string;
  text: string;
}

/** Поле постановки задачи агентам окна (Ctrl+Enter — запуск). */
export function AgentComposer({
  id,
  label,
  hint,
  placeholder,
  text,
  onText,
  samples,
  onSample,
  runner,
  onSubmit,
  submitLabel,
  rows = 4,
  disabled = false,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  placeholder: string;
  text: string;
  onText: (value: string) => void;
  samples?: ComposerSample[];
  onSample?: (sample: ComposerSample) => void;
  runner: TaskRunner;
  onSubmit: () => void;
  submitLabel: string;
  rows?: number;
  disabled?: boolean;
  children?: ReactNode;
}) {
  const busy = runner.running || runner.submitting;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim() || busy || disabled) return;
    onSubmit();
  };
  return (
    <form onSubmit={submit} className="rounded-lg border border-paper-line bg-paper-card p-4 shadow-card" data-swarm-target>
      <label htmlFor={id} className="mb-2 flex flex-wrap items-baseline gap-x-2 text-sm font-semibold text-ink">
        {label}
        {hint && <span className="text-xs font-normal text-ink-mute">{hint}</span>}
      </label>
      <textarea
        id={id}
        value={text}
        onChange={(e) => onText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(e);
        }}
        rows={rows}
        placeholder={placeholder}
        className="w-full resize-y rounded-[3px] border-2 border-paper-line bg-paper px-3 py-2 text-[15px] leading-relaxed outline-none placeholder:text-ink-mute focus:border-brand focus:bg-white"
      />
      {children && <div className="mt-3">{children}</div>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {samples && samples.length > 0 && (
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
            <span className="mr-1 text-xs text-ink-mute">Примеры:</span>
            {samples.map((s) => (
              <button
                key={s.label}
                type="button"
                onClick={() => (onSample ? onSample(s) : onText(s.text))}
                className="rounded-full border border-paper-line px-2.5 py-0.5 text-xs text-ink-soft hover:border-brand hover:text-brand"
              >
                {s.label}
              </button>
            ))}
          </div>
        )}
        <button type="submit" disabled={!text.trim() || busy || disabled} className="btn-primary ml-auto" data-swarm-origin>
          {busy ? "Агенты работают…" : submitLabel}
          <kbd className="hidden font-sans text-[11px] text-white/60 sm:inline">Ctrl+Enter</kbd>
        </button>
      </div>
      {runner.submitError && <p className="mt-3 text-sm text-fail">{runner.submitError}</p>}
      {runner.latest?.status === "failed" && runner.latest.error && (
        <p role="alert" className="mt-3 rounded-md bg-fail-soft px-3 py-2 text-sm text-fail">
          {runner.latest.error.message} <span className="font-mono text-xs opacity-70">({runner.latest.error.code})</span>
        </p>
      )}
      {runner.error && <p className="mt-3 text-sm text-fail">{runner.error}</p>}
    </form>
  );
}

/** Кнопка «В Telegram» с понятным итогом (сколько чатов, бот не настроен и т.п.). */
export function TelegramButton({ send, label = "В Telegram" }: { send: () => Promise<SendPostResponse>; label?: string }) {
  const [state, setState] = useState<{ busy: boolean; note: string | null }>({ busy: false, note: null });
  const click = async () => {
    setState({ busy: true, note: null });
    try {
      const res = await send();
      setState({
        busy: false,
        note:
          res.sent > 0
            ? `Отправлено в Telegram: ${res.sent} ${res.sent === 1 ? "чат" : "чата"}`
            : "Боту ещё никто не писал — откройте @orcify_bot и нажмите /start",
      });
    } catch (error) {
      setState({
        busy: false,
        note: error instanceof ApiError && error.status === 409 ? "Telegram-бот не настроен (TELEGRAM_BOT_API_KEY)" : "Не удалось отправить",
      });
    }
  };
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <button type="button" onClick={() => void click()} disabled={state.busy} className="btn-subtle">
        <SendIcon /> {state.busy ? "Отправка…" : label}
      </button>
      {state.note && (
        <span role="status" className="text-xs text-ink-soft">
          {state.note}
        </span>
      )}
    </span>
  );
}

/** Скелет-плейсхолдер, пока агенты собирают результат. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <span className={`block animate-pulse rounded bg-paper-col ${className}`} aria-hidden />;
}
