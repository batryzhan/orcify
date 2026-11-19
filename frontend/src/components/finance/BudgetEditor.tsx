import { useEffect, useState } from "react";

import { api } from "../../lib/api";
import type { BudgetItem } from "../../types/api";

interface Row {
  id: number;
  category: string;
  limit: string;
}

let nextId = 1;
const toRow = (item: BudgetItem): Row => ({ id: nextId++, category: item.category, limit: String(item.limit) });

/** Санаттар бойынша айлық шығыс лимиттері. Үзіндіні әр талдау кезінде тексеріледі. */
export function BudgetEditor({ suggestions }: { suggestions: string[] }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void api
      .budgets()
      .then((b) => setRows(b.items.map(toRow)))
      .catch(() => setRows([]));
  }, []);

  const parse = (value: string) => Number(value.replace(/\s/g, "").replace(",", "."));
  const valid = rows.every((r) => r.category.trim() && Number.isFinite(parse(r.limit)) && parse(r.limit) > 0);

  const save = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const saved = await api.saveBudgets({ items: rows.map((r) => ({ category: r.category.trim(), limit: parse(r.limit) })) });
      setRows(saved.items.map(toRow));
      setStatus("Сақталды — келесі талдауда ескеріледі");
    } catch {
      setStatus("Сақтау мүмкін болмады");
    } finally {
      setSaving(false);
    }
  };

  const update = (id: number, patch: Partial<Row>) => setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  return (
    <section className="rounded-lg bg-white p-4 shadow-card" data-swarm-target>
      <h2 className="text-sm font-semibold text-ink">Айлық бюджеттер</h2>
      <p className="mb-3 text-xs text-ink-mute">Лимиттер үзіндінің соңғы толық айындағы шығыстармен салыстырылады.</p>
      <datalist id="budget-categories">
        {suggestions.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
      {rows.length === 0 && <p className="mb-2 text-xs text-ink-soft">Лимиттер әзірге жоқ.</p>}
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.id} className="flex items-center gap-2">
            <label className="min-w-0 flex-1">
              <span className="sr-only">Санат</span>
              <input
                list="budget-categories"
                value={r.category}
                onChange={(e) => update(r.id, { category: e.target.value })}
                placeholder="Санат"
                className="w-full rounded-[3px] border-2 border-paper-line px-2 py-1 text-sm outline-none focus:border-brand"
              />
            </label>
            <label className="w-32">
              <span className="sr-only">Лимит, ₸</span>
              <input
                value={r.limit}
                onChange={(e) => update(r.id, { limit: e.target.value })}
                inputMode="decimal"
                placeholder="Лимит, ₸"
                className="w-full rounded-[3px] border-2 border-paper-line px-2 py-1 text-right font-mono text-sm outline-none focus:border-brand"
              />
            </label>
            <button
              type="button"
              onClick={() => setRows((prev) => prev.filter((x) => x.id !== r.id))}
              className="flex h-8 w-8 items-center justify-center rounded text-ink-mute hover:bg-paper-col hover:text-fail"
              aria-label={`${r.category || ""} лимитін жою`}
            >
              ✕
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => setRows((prev) => [...prev, toRow({ category: "", limit: 0 })])} className="btn-subtle">
          + Лимит
        </button>
        <button type="button" onClick={() => void save()} disabled={!valid || saving} className="btn-primary">
          {saving ? "Сақталуда…" : "Сақтау"}
        </button>
        {status && (
          <span role="status" className="text-xs text-ink-soft">
            {status}
          </span>
        )}
      </div>
    </section>
  );
}
