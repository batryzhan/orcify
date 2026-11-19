import { formatMoney } from "../../lib/format";
import type { BudgetCheck, FinanceMetrics } from "../../types/api";

const MONTHS = ["қаң", "ақп", "нау", "сәу", "мам", "мау", "шіл", "там", "қыр", "қаз", "қар", "жел"];

export function monthLabel(month: string): string {
  const [year, m] = month.split("-");
  return `${MONTHS[Number(m) - 1] ?? m} ${year}`;
}

/** 3 айлық қалдық болжамы: қалдық бағандары (қазір + болжам) және кесте. */
export function ForecastCard({ metrics }: { metrics: FinanceMetrics }) {
  if (metrics.forecast.length === 0) return null;
  const points = [
    { label: "қазір", balance: metrics.closing_balance, actual: true },
    ...metrics.forecast.map((p) => ({ label: monthLabel(p.month), balance: p.balance, actual: false })),
  ];
  const peak = Math.max(...points.map((p) => Math.abs(p.balance)), 1);
  const negative = metrics.forecast.find((p) => p.balance < 0);
  const first = metrics.forecast[0];

  return (
    <section className="rounded-lg bg-white p-5 shadow-card">
      <header className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-base font-semibold">3 айлық қалдық болжамы</h3>
        <span className="text-xs text-ink-mute">соңғы {metrics.forecast_basis_months} толық айдың орташасы бойынша</span>
      </header>
      {negative ? (
        <p className="mb-3 rounded-md bg-fail-soft px-3 py-2 text-sm text-fail">
          Қазіргі қарқында қалдық {monthLabel(negative.month)} айында минусқа кетеді ({formatMoney(negative.balance)}).
        </p>
      ) : (
        <p className="mb-3 text-sm text-ink-soft">
          Әр ай орта есеппен +{formatMoney(first?.net ?? 0)}: түсімдер {formatMoney(first?.income ?? 0)}, шығыстар{" "}
          {formatMoney(first?.expense ?? 0)}.
        </p>
      )}
      <div className="flex h-36 items-end gap-3" role="img" aria-label="Қазіргі қалдық және айлар бойынша болжам">
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
      <p className="mt-3 text-xs text-ink-mute">Болжам — орташа бойынша бағдар, уәде емес: маусымдылық пен бір реттік төлемдер ескерілмеген.</p>
    </section>
  );
}

/** Соңғы толық айды алдыңғымен салыстыру: қорытындылар және санаттар бойынша өзгерістер. */
export function MonthOverMonthCard({ metrics }: { metrics: FinanceMetrics }) {
  const mom = metrics.month_over_month;
  if (!mom) return null;
  const totals: [string, number, number][] = [
    ["Түсімдер", mom.income_previous, mom.income_current],
    ["Шығыстар", mom.expense_previous, mom.expense_current],
  ];
  return (
    <section className="rounded-lg bg-white p-5 shadow-card">
      <h3 className="mb-3 text-base font-semibold">
        {monthLabel(mom.current_month)} · алдыңғы ай: {monthLabel(mom.previous_month)}
      </h3>
      <div className="mb-4 grid grid-cols-2 gap-3">
        {totals.map(([label, before, after]) => (
          <div key={label} className="rounded-md bg-paper p-3">
            <p className="text-xs text-ink-mute">{label}</p>
            <p className="font-semibold tabular-nums">{formatMoney(after)}</p>
            <Delta value={after - before} base={before} invert={label === "Шығыстар"} />
          </div>
        ))}
      </div>
      {mom.categories.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-ink-mute">
              <th className="pb-1.5 font-semibold">Шығыс санаты</th>
              <th className="pb-1.5 text-right font-semibold">Бұрын</th>
              <th className="pb-1.5 text-right font-semibold">Қазір</th>
              <th className="pb-1.5 text-right font-semibold">Өзгеріс</th>
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

/** Таңбасы мен көрсеткісі бар өзгеріс (тек түспен емес). invert: өсу — жаман (шығыстар). */
function Delta({ value, base, invert = false }: { value: number; base: number; invert?: boolean }) {
  if (Math.abs(value) < 0.5) return <span className="text-xs text-ink-mute">өзгеріссіз</span>;
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

/** Бюджеттер: лимит, соңғы толық айда жұмсалғаны, қалдық немесе асып кету. */
export function BudgetsCard({ checks, month }: { checks: BudgetCheck[]; month: string | null }) {
  if (checks.length === 0) return null;
  return (
    <section className="rounded-lg bg-white p-5 shadow-card">
      <h3 className="mb-3 text-base font-semibold">Бюджеттер{month ? ` · ${monthLabel(month)}` : ""}</h3>
      <ul className="space-y-3">
        {checks.map((b) => (
          <li key={b.category}>
            <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2 text-sm">
              <span className="font-medium">{b.category}</span>
              <span className={`text-xs tabular-nums ${b.over ? "font-semibold text-fail" : "text-ink-soft"}`}>
                {formatMoney(b.spent)} / {formatMoney(b.limit)} ·{" "}
                {b.over ? `асып кету ${formatMoney(-b.remaining)}` : `қалды ${formatMoney(b.remaining)}`}
              </span>
            </div>
            <div
              className="h-2 overflow-hidden rounded-full bg-paper-col"
              role="progressbar"
              aria-label={`${b.category}: пайдаланылған ${(b.ratio * 100).toFixed(0)}%`}
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
