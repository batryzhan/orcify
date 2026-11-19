import type { Currency } from "../types/api";

const CURRENCY_LABEL: Record<Currency, string> = { KZT: "₸", USD: "$", EUR: "€", RUB: "₽" };

export function formatAmount(amount: string | null, currency: Currency | null): string {
  if (amount === null) return "—";
  const n = Number(amount);
  const text = Number.isFinite(n)
    ? n.toLocaleString("ru-RU", { minimumFractionDigits: 0, maximumFractionDigits: 2 })
    : amount;
  return currency ? `${text} ${CURRENCY_LABEL[currency]}` : text;
}

export function formatDate(iso: string | null): string {
  if (iso === null) return "—";
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
}

export function formatMoney(value: number, compact = false): string {
  if (compact && Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} млн ₸`;
  }
  return `${Math.round(value).toLocaleString("ru-RU")} ₸`;
}

export function formatPercent(share: number): string {
  return `${(share * 100).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`;
}

export function formatBytes(size: number): string {
  return size < 1024 ? `${size} Б` : `${(size / 1024).toFixed(1)} КБ`;
}
