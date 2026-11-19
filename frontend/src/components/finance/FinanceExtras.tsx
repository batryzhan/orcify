import { formatMoney } from "../../lib/format";
import type { BudgetCheck, FinanceMetrics } from "../../types/api";

const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

export function monthLabel(month: string): string {
  const [year, m] = month.split("-");
  return `${MONTHS[Number(m) - 1] ?? m} ${year}`;
}

/** Прогноз остатка на 3 месяца: столбики остатка (сейчас + прогноз) и таблица. */
export function ForecastCard({ metrics }: { metrics: FinanceMetrics }) {
  if (metrics.forecast.length === 0) return null;
  const points = [
    { label: "сейчас", balance: metrics.closing_balance, actual: true },
    ...metrics.forecast.map((p) => ({ label: monthLabel(p.month), balance: p.balance, actual: false })),
  ];
  const peak = Math.max(...points.map((p) => Math.abs(p.balance)), 1);
  const negative = metrics.forecast.find((p) => p.balance < 0);
  const first = metrics.forecast[0];

  return (
    <section className="rounded-lg bg-white p-5 shadow-card">
      <header className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-base font-semibold">Прогноз остатка на 3 месяца</h3>
        <span className="text-xs text-ink-mute">по среднему последних {metrics.forecast_basis_months} полных мес.</span>
      </header>
      {negative ? (
        <p className="mb-3 rounded-md bg-fail-soft px-3 py-2 text-sm text-fail">
          При текущем темпе остаток уйдёт в минус в {monthLabel(negative.month)} ({formatMoney(negative.balance)}).
        </p>
      ) : (
        <p className="mb-3 text-sm text-ink-soft">
          Каждый месяц в среднем +{formatMoney(first?.net ?? 0)}: поступления {formatMoney(first?.income ?? 0)}, расходы{" "}
          {formatMoney(first?.expense ?? 0)}.
        </p>
      )}
      <div className="flex h-36 items-end gap-3" role="img" aria-label="Остаток сейчас и прогноз по месяцам">
        {points.map((p) => (
          <div key={p.label} className="flex min-w-0 flex-1 flex-col items-center gap-1">
            <span className={`font-mono text-[11px] tabular-nums ${p.balance < 0 ? "text-fail" : "text-ink-soft"}`}>
              {formatMoney(p.balance, true)}
            </span>
            <div
              className={`w-full max-w-14 rounded-t ${p.balance < 0 ? "bg-fail" : p.actual ? "bg-series-1" : "bg-series-1/45"}`}
              style={{ height: `${Math.max(4, (Math.abs(p.balance) / peak) * 100)}px` }}
            />
            <span className="text-xs text-ink-mute">{p.label}</span>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-ink-mute">Прогноз — ориентир по среднему, а не обещание: сезонность и разовые платежи не учтены.</p>
    </section>
  );
}

/** Сравнение последнего полного месяца с предыдущим: итоги и изменения по категориям. */
export function MonthOverMonthCard({ metrics }: { metrics: FinanceMetrics }) {
  const mom = metrics.month_over_month;
  if (!mom) return null;
  const totals: [string, number, number][] = [
    ["Поступления", mom.income_previous, mom.income_current],
    ["Расходы", mom.expense_previous, mom.expense_current],
  ];
  return (
    <section className="rounded-lg bg-white p-5 shadow-card">
      <h3 className="mb-3 text-base font-semibold">
        {monthLabel(mom.current_month)} к {monthLabel(mom.previous_month)}
      </h3>
      <div className="mb-4 grid grid-cols-2 gap-3">
        {totals.map(([label, before, after]) => (
          <div key={label} className="rounded-md bg-paper p-3">
            <p className="text-xs text-ink-mute">{label}</p>
            <p className="font-semibold tabular-nums">{formatMoney(after)}</p>
            <Delta value={after - before} base={before} invert={label === "Расходы"} />
          </div>
        ))}
      </div>
      {mom.categories.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-ink-mute">
              <th className="pb-1.5 font-semibold">Категория расходов</th>
              <th className="pb-1.5 text-right font-semibold">Было</th>
              <th className="pb-1.5 text-right font-semibold">Стало</th>
              <th className="pb-1.5 text-right font-semibold">Изменение</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-paper-line">
            {mom.categories.map((c) => (
              <tr key={c.category}>
                <td className="py-1.5">{c.category}</td>
                <td className="py-1.5 text-right font-mono text-xs tabular-nums text-ink-soft">{formatMoney(c.previous)}</td>
                <td className="py-1.5 text-right font-mono text-xs tabular-nums">{formatMoney(c.current)}</td>
                <td className="py-1.5 text-right">
                  <Delta value={c.change} base={c.previous} invert />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

/** Изменение со знаком и стрелкой (не только цветом). invert: рост — плохо (расходы). */
function Delta({ value, base, invert = false }: { value: number; base: number; invert?: boolean }) {
  if (Math.abs(value) < 0.5) return <span className="text-xs text-ink-mute">без изменений</span>;
  const up = value > 0;
  const bad = invert ? up : !up;
  const pct = base > 0 ? ` (${up ? "+" : "−"}${Math.abs((value / base) * 100).toFixed(0)}%)` : "";
  return (
    <span className={`whitespace-nowrap text-xs font-medium tabular-nums ${bad ? "text-fail" : "text-local"}`}>
      {up ? "▲ +" : "▼ −"}
      {formatMoney(Math.abs(value))}
      {pct}
    </span>
  );
}

/** Бюджеты: лимит, потрачено за последний полный месяц, остаток или перерасход. */
export function BudgetsCard({ checks, month }: { checks: BudgetCheck[]; month: string | null }) {
  if (checks.length === 0) return null;
  return (
    <section className="rounded-lg bg-white p-5 shadow-card">
      <h3 className="mb-3 text-base font-semibold">Бюджеты{month ? ` · ${monthLabel(month)}` : ""}</h3>
      <ul className="space-y-3">
        {checks.map((b) => (
          <li key={b.category}>
            <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2 text-sm">
              <span className="font-medium">{b.category}</span>
              <span className={`text-xs tabular-nums ${b.over ? "font-semibold text-fail" : "text-ink-soft"}`}>
                {formatMoney(b.spent)} из {formatMoney(b.limit)} ·{" "}
                {b.over ? `перерасход ${formatMoney(-b.remaining)}` : `осталось ${formatMoney(b.remaining)}`}
              </span>
            </div>
            <div
              className="h-2 overflow-hidden rounded-full bg-paper-col"
              role="progressbar"
              aria-label={`${b.category}: использовано ${(b.ratio * 100).toFixed(0)}%`}
              aria-valuenow={Math.round(b.ratio * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className={`h-full rounded-full ${b.over ? "bg-fail" : b.ratio > 0.85 ? "bg-warn" : "bg-local"}`}
                style={{ width: `${Math.min(100, b.ratio * 100)}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
