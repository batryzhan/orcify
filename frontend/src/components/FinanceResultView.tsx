import { useState } from "react";

import { formatBytes, formatDate, formatMoney, formatPercent } from "../lib/format";
import type { FinanceMetrics, FinanceResult, MonthlyFlow, RiskLevel } from "../types/api";

const RISK_STYLE: Record<RiskLevel, { label: string; className: string; icon: string }> = {
  high: { label: "высокий", className: "bg-fail-soft text-fail", icon: "▲" },
  medium: { label: "средний", className: "bg-warn-soft text-warn", icon: "●" },
  low: { label: "низкий", className: "bg-paper text-ink-soft", icon: "○" },
};

const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

function monthLabel(month: string): string {
  const [year, m] = month.split("-");
  return `${MONTHS[Number(m) - 1] ?? m} ${year?.slice(2)}`;
}

export function FinanceResultView({ result }: { result: FinanceResult }) {
  const { metrics, report } = result;
  return (
    <section className="space-y-5">
      <div className="rounded-xl border border-paper-line bg-paper-card p-5">
        <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold">Финансовая сводка</h2>
          <span className="text-xs text-ink-mute">
            {formatDate(metrics.period_start)} — {formatDate(metrics.period_end)} · {metrics.rows} операций · анализ
            локально за {(result.mcp_latency_ms / 1000).toFixed(1)} с
          </span>
        </header>
        <StatTiles metrics={metrics} />
      </div>

      {report ? (
        <div className="space-y-4 rounded-xl border border-paper-line bg-paper-card p-5">
          <p className="text-base font-semibold leading-snug">{report.headline}</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink-soft">
            {report.key_findings.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
          {report.risks.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-soft">Риски</h3>
              {report.risks.map((r) => {
                const style = RISK_STYLE[r.level];
                return (
                  <div key={r.title} className="flex gap-3 text-sm">
                    <span className={`h-fit shrink-0 rounded px-2 py-0.5 text-xs ${style.className}`}>
                      <span aria-hidden>{style.icon}</span> {style.label}
                    </span>
                    <p>
                      <strong className="font-medium">{r.title}.</strong>{" "}
                      <span className="text-ink-soft">{r.detail}</span>
                    </p>
                  </div>
                );
              })}
            </div>
          )}
          <div>
            <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-ink-soft">Рекомендации</h3>
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              {report.recommendations.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ol>
          </div>
          <p className="text-xs text-ink-mute">
            Резюме составлено Gemma только по агрегатам — строки выписки в модель не передавались.
          </p>
        </div>
      ) : (
        <p className="rounded-xl bg-warn-soft p-4 text-sm text-warn">
          Резюме модели недоступно ({result.report_error_code}); метрики ниже посчитаны локально и точны.
        </p>
      )}

      <div className="rounded-xl border border-paper-line bg-paper-card p-5">
        <MonthlyChart monthly={metrics.monthly} />
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="min-w-0 rounded-xl border border-paper-line bg-paper-card p-5">
          <h3 className="mb-3 text-sm font-semibold">Расходы по категориям</h3>
          <CategoryBars metrics={metrics} />
        </div>
        <div className="min-w-0 space-y-4 rounded-xl border border-paper-line bg-paper-card p-5">
          <div>
            <h3 className="mb-2 text-sm font-semibold">Кассовые разрывы</h3>
            {metrics.cash_gaps.length === 0 ? (
              <p className="text-sm text-ink-soft">Остаток не уходил в минус</p>
            ) : (
              <ul className="space-y-1.5 text-sm">
                {metrics.cash_gaps.map((g) => (
                  <li key={g.start} className="flex justify-between gap-3">
                    <span>
                      <span aria-hidden className="text-fail">▲ </span>
                      {formatDate(g.start)} — {formatDate(g.end)} ({g.days} дн.)
                    </span>
                    <span className="font-mono tabular-nums text-fail">{formatMoney(g.min_balance)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold">Аномальные операции</h3>
            {metrics.anomalies.length === 0 ? (
              <p className="text-sm text-ink-soft">Не обнаружены</p>
            ) : (
              <ul className="space-y-1.5 text-sm">
                {metrics.anomalies.map((a) => (
                  <li key={`${a.date}${a.amount}`} className="flex justify-between gap-3">
                    <span className="min-w-0 truncate">
                      {formatDate(a.date)} · {a.counterparty ?? "—"}
                    </span>
                    <span className="font-mono tabular-nums">{formatMoney(a.amount)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {result.document && (
        <a
          href={result.document.download_url}
          download={result.document.filename}
          className="inline-flex items-center gap-2 rounded-lg bg-local px-4 py-2 text-sm font-medium text-white hover:bg-local/90"
        >
          Скачать отчёт (.md, {formatBytes(result.document.size_bytes)})
        </a>
      )}
    </section>
  );
}

function StatTiles({ metrics }: { metrics: FinanceMetrics }) {
  const tiles = [
    { label: "Поступления", value: metrics.total_income },
    { label: "Расходы", value: metrics.total_expense },
    { label: "Чистый поток", value: metrics.net, signed: true },
    { label: "Остаток на конец", value: metrics.closing_balance, signed: true },
  ];
  return (
    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label}>
          <dt className="text-xs text-ink-mute">{t.label}</dt>
          <dd className={`mt-1 text-xl font-semibold tabular-nums ${t.signed && t.value < 0 ? "text-fail" : ""}`}>
            {formatMoney(t.value, true)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Сгруппированные столбцы поступления/расходы по месяцам: одна ось, ховер-тултип, табличный вид. */
function MonthlyChart({ monthly }: { monthly: MonthlyFlow[] }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [asTable, setAsTable] = useState(false);
  const max = Math.max(1, ...monthly.flatMap((m) => [m.income, m.expense]));
  const active = monthly.find((m) => m.month === hovered) ?? null;
  const HEIGHT = 160;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">Денежный поток по месяцам</h3>
        <div className="flex items-center gap-4 text-xs text-ink-soft">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-series-1" /> Поступления
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-series-2" /> Расходы
          </span>
          <button
            type="button"
            onClick={() => setAsTable((v) => !v)}
            className="rounded border border-paper-line px-2 py-0.5 hover:border-ink-mute"
          >
            {asTable ? "График" : "Таблица"}
          </button>
        </div>
      </div>

      {asTable ? (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-ink-mute">
            <tr>
              <th className="py-1 font-normal">Месяц</th>
              <th className="py-1 text-right font-normal">Поступления</th>
              <th className="py-1 text-right font-normal">Расходы</th>
              <th className="py-1 text-right font-normal">Итог</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {monthly.map((m) => (
              <tr key={m.month} className="border-t border-paper-line">
                <td className="py-1.5">{monthLabel(m.month)}</td>
                <td className="py-1.5 text-right">{formatMoney(m.income)}</td>
                <td className="py-1.5 text-right">{formatMoney(m.expense)}</td>
                <td className={`py-1.5 text-right ${m.net < 0 ? "text-fail" : ""}`}>{formatMoney(m.net)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="relative">
          <div className="h-12 text-sm" aria-live="polite">
            {active ? (
              <div className="tabular-nums">
                <span className="font-medium">{monthLabel(active.month)}</span>
                <span className="ml-3 text-ink-soft">поступления {formatMoney(active.income)}</span>
                <span className="ml-3 text-ink-soft">расходы {formatMoney(active.expense)}</span>
                <span className={`ml-3 font-medium ${active.net < 0 ? "text-fail" : ""}`}>
                  итог {formatMoney(active.net)}
                </span>
              </div>
            ) : (
              <span className="text-xs text-ink-mute">Наведите на месяц, чтобы увидеть суммы</span>
            )}
          </div>
          <div className="flex items-end gap-3 border-b border-paper-line" style={{ height: HEIGHT }}>
            {monthly.map((m) => (
              <div
                key={m.month}
                className={`flex h-full flex-1 cursor-default items-end justify-center gap-[2px] rounded-t px-1 ${
                  hovered === m.month ? "bg-paper" : ""
                }`}
                onMouseEnter={() => setHovered(m.month)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(m.month)}
                onBlur={() => setHovered(null)}
                tabIndex={0}
                aria-label={`${monthLabel(m.month)}: поступления ${formatMoney(m.income)}, расходы ${formatMoney(m.expense)}`}
              >
                <div className="w-full max-w-6 rounded-t bg-series-1" style={{ height: `${(m.income / max) * 100}%` }} />
                <div className="w-full max-w-6 rounded-t bg-series-2" style={{ height: `${(m.expense / max) * 100}%` }} />
              </div>
            ))}
          </div>
          <div className="mt-1.5 flex gap-3 text-center text-xs text-ink-mute">
            {monthly.map((m) => (
              <span key={m.month} className="flex-1">
                {monthLabel(m.month)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CategoryBars({ metrics }: { metrics: FinanceMetrics }) {
  if (metrics.expense_by_category.length === 0) {
    return <p className="text-sm text-ink-soft">В выписке нет колонки категорий</p>;
  }
  const max = Math.max(...metrics.expense_by_category.map((c) => c.amount));
  return (
    <ul className="space-y-2.5">
      {metrics.expense_by_category.map((c) => (
        <li key={c.category} title={`${c.category}: ${formatMoney(c.amount)}`}>
          <div className="mb-1 flex justify-between gap-2 text-sm">
            <span className="truncate">{c.category}</span>
            <span className="shrink-0 tabular-nums text-ink-soft">
              {formatMoney(c.amount, true)} · {formatPercent(c.share)}
            </span>
          </div>
          <div className="h-2 rounded-r bg-paper">
            <div className="h-full rounded-r bg-series-1" style={{ width: `${(c.amount / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
