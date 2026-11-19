import type { ReceivedEvent, SSEState } from "../hooks/useSSE";
import { STAGE_LABEL as LABELS, STAGE_PLAN as PLAN } from "../lib/stages";
import type { Domain, TaskStatus } from "../types/api";

interface Props {
  events: ReceivedEvent[];
  startedAt: number | null;
  state: SSEState;
  domain: Domain | null;
}

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} с`;
}

export function ProgressStepper({ events, startedAt, state, domain }: Props) {
  const reached = new Map<TaskStatus, number>();
  events.forEach((e, i) => {
    // Карточканы көшірулер (updating_jira) қайталанады — кезеңдер тізімінде көрсетпейміз.
    if (e.data.status !== "updating_jira" && !reached.has(e.data.status)) reached.set(e.data.status, i);
  });

  const latest = events.at(-1)?.data ?? null;
  const failed = latest?.status === "failed";
  const finished = latest?.status === "completed" || failed;
  // Аяқталған соң өтілмеген кезеңдер жасырылады (мысалы, needs_input кезіндегі рендер).
  const plan = PLAN[domain ?? "unknown"].filter((s) => (finished ? reached.has(s) : true));
  const steps: TaskStatus[] = [...plan, ...[...reached.keys()].filter((s) => !plan.includes(s))];
  const order = (s: TaskStatus) => reached.get(s) ?? Number.MAX_SAFE_INTEGER;
  steps.sort((a, b) => order(a) - order(b) || plan.indexOf(a) - plan.indexOf(b));

  const progress = latest?.progress ?? 0;
  const running = state === "connecting" || state === "open";
  const total = events.length > 0 && startedAt !== null ? (events.at(-1)?.at ?? startedAt) - startedAt : null;

  return (
    <section aria-label="Орындалу барысы">
      <div className="mb-4 flex items-baseline justify-between gap-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-soft">Орындалу барысы</h2>
        <span className="font-mono text-sm tabular-nums text-ink-soft">
          {progress}%{total !== null && !running ? ` · ${seconds(total)}` : ""}
        </span>
      </div>

      <div
        className="mb-5 h-1.5 overflow-hidden rounded-full bg-paper-line"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
      >
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${failed ? "bg-fail" : "bg-brand"}`}
          style={{ width: `${progress}%` }}
        />
      </div>

      <ol className="space-y-2.5">
        {steps.map((status) => {
          const index = reached.get(status);
          const done = index !== undefined;
          const isCurrent = done && index === events.length - 1 && running;
          // Кезеңнің ұзақтығы = оның оқиғасынан ағынның келесі оқиғасына дейін.
          const thisAt = index !== undefined ? events[index]?.at : undefined;
          const nextAt = index !== undefined ? events[index + 1]?.at : undefined;
          const duration = thisAt !== undefined && nextAt !== undefined ? nextAt - thisAt : null;
          const isTerminal = status === "completed" || status === "failed";

          return (
            <li key={status} className="flex items-center gap-3 text-sm">
              <span
                aria-hidden
                className={[
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px]",
                  status === "failed"
                    ? "border-fail bg-fail text-white"
                    : done && !isCurrent
                      ? "border-brand bg-brand text-white"
                      : isCurrent
                        ? "border-brand text-brand"
                        : "border-paper-line text-ink-mute",
                ].join(" ")}
              >
                {status === "failed" ? "!" : done && !isCurrent ? "✓" : isCurrent ? <Spinner /> : ""}
              </span>
              <span className={done ? "text-ink" : "text-ink-mute"}>{LABELS[status]}</span>
              {duration !== null && !isTerminal && (
                <span className="ml-auto font-mono text-xs tabular-nums text-ink-mute">{seconds(duration)}</span>
              )}
            </li>
          );
        })}
      </ol>

      {latest?.message && !failed && <p className="mt-4 text-sm text-ink-soft">{latest.message}</p>}
    </section>
  );
}

function Spinner() {
  return <span className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-brand border-t-transparent" />;
}
