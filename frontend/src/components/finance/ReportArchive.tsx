import { useEffect, useRef } from "react";

import { api } from "../../lib/api";
import { formatDate, formatMoney } from "../../lib/format";
import type { ReportRecord } from "../../types/api";
import { TelegramButton } from "../shared";

/** PDF-есептер мұрағаты: ашу, жүктеу, Telegram-ға жіберу, жою. */
export function ReportArchive({
  reports,
  highlight,
  onDeleted,
}: {
  reports: ReportRecord[] | null;
  highlight: string | null;
  onDeleted: (id: string) => void;
}) {
  const rowRef = useRef<HTMLLIElement>(null);
  useEffect(() => {
    rowRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlight, reports]);

  if (reports === null) return <p className="text-sm text-ink-mute">Жүктелуде…</p>;
  if (reports.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-paper-line p-6 text-sm text-ink-soft">
        Есептер әзірге жоқ — үзінді талданған соң PDF осында пайда болады.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-paper-line rounded-lg bg-white shadow-card">
      {reports.map((r) => {
        const id = r.file.report_id;
        const marked = id === highlight;
        return (
          <li key={id} ref={marked ? rowRef : undefined} className={`flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 ${marked ? "bg-brand-soft" : ""}`}>
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-fail-soft text-[10px] font-bold text-fail" aria-hidden>
              PDF
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-ink">{r.headline ?? "Қаржылық қорытынды"}</p>
              <p className="text-xs text-ink-mute">
                {formatDate(r.period_start)} — {formatDate(r.period_end)} · {r.rows} операция · нәтиже {formatMoney(r.net, true)}
                {r.issue_key ? ` · ${r.issue_key}` : ""} · жасалған {new Date(r.created_at).toLocaleString("kk-KZ", { dateStyle: "short", timeStyle: "short" })}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <a href={r.file.download_url} target="_blank" rel="noreferrer" className="btn-subtle">
                Ашу
              </a>
              <a href={r.file.download_url} download={r.file.filename} className="btn-subtle">
                Жүктеу
              </a>
              <TelegramButton send={() => api.sendReportToTelegram(id)} />
              <button
                type="button"
                onClick={() => {
                  if (window.confirm("Есепті мұрағаттан жою керек пе? Бұл әрекетті болдырмау мүмкін емес.")) {
                    void api.deleteReport(id).then(() => onDeleted(id));
                  }
                }}
                className="btn text-ink-mute hover:text-fail"
              >
                Жою
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
