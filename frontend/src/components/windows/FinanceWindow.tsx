import { useEffect, useRef, useState, type ChangeEvent } from "react";

import type { TaskRunner } from "../../hooks/useTaskRunner";
import { api } from "../../lib/api";
import { formatBytes } from "../../lib/format";
import { STAGE_LABEL } from "../../lib/stages";
import type { ReportRecord, TaskAttachment } from "../../types/api";
import { BudgetEditor } from "../finance/BudgetEditor";
import { BudgetsCard, ForecastCard, MonthOverMonthCard } from "../finance/FinanceExtras";
import { ReportArchive } from "../finance/ReportArchive";
import { FinanceResultView } from "../FinanceResultView";
import { AgentComposer, AgentStage, Skeleton, TelegramButton, WindowHeader } from "../shared";

const MAX_CSV_BYTES = 5_000_000;
const DEMO_CSV_URL = "/samples/transactions_demo.csv";
const DEFAULT_TASK = "Үзіндіні талда: ақша ағынының үзілістері, ең ірі шығыстар, болжам және мұнымен не істеу керек.";

/** «Қаржы» терезесі: CSV-үзінді -> жергілікті талдау -> PDF-есеп, бюджеттер, болжам, мұрағат, Telegram. */
export function FinanceWindow({ runner, highlightReport }: { runner: TaskRunner; highlightReport: string | null }) {
  const [text, setText] = useState(DEFAULT_TASK);
  const [attachment, setAttachment] = useState<TaskAttachment | null>(null);
  const [openingBalance, setOpeningBalance] = useState("0");
  const [fileError, setFileError] = useState<string | null>(null);
  const [reports, setReports] = useState<ReportRecord[] | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const finance = runner.result?.finance ?? null;
  const done = runner.latest?.status === "completed";

  const loadReports = () => void api.reports().then(setReports).catch(() => setReports([]));
  useEffect(loadReports, []);
  useEffect(() => {
    if (done) loadReports();
  }, [done]);

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > MAX_CSV_BYTES) {
      setFileError("Файл 5 МБ-тан үлкен");
      return;
    }
    setFileError(null);
    // Файл браузерде оқылады және тек жергілікті бэкендке жіберіледі.
    setAttachment({ filename: file.name, media_type: "text/csv", content: await file.text() });
  };

  const useDemo = async () => {
    const response = await fetch(DEMO_CSV_URL);
    setAttachment({ filename: "transactions_demo.csv", media_type: "text/csv", content: await response.text() });
    setOpeningBalance("500000");
    setFileError(null);
  };

  const submit = () => {
    if (!attachment) return;
    const balance = Number(openingBalance.replace(/\s/g, "").replace(",", "."));
    void runner.submit({
      text: text.trim(),
      domain: "Finance",
      attachment,
      opening_balance: Number.isFinite(balance) ? balance : 0,
    });
  };

  const categories = finance?.metrics.expense_by_category.map((c) => c.category) ?? [];

  return (
    <div className="px-4 pb-28 pt-5 sm:px-8" data-swarm-scope="finance">
      <WindowHeader title="Қаржы">
        Үзінді жергілікті есептеледі (pandas): модельге тек агрегаттар жіберіледі. Есеп — мұрағаттағы PDF; оны Telegram-ға
        бір батырмамен жіберуге болады.
      </WindowHeader>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <AgentComposer
          id="finance-text"
          label="Талдаушыға тапсырма"
          hint="үзінді бойынша нені білгіңіз келеді"
          placeholder={DEFAULT_TASK}
          text={text}
          onText={setText}
          rows={2}
          runner={runner}
          submitLabel="Талдау"
          disabled={!attachment}
          onSubmit={submit}
        >
          <input ref={fileInput} type="file" accept=".csv,text/csv" className="hidden" onChange={onFile} />
          {attachment ? (
            <div className="flex flex-wrap items-center gap-3 rounded-[3px] bg-paper-col px-3 py-2 text-sm">
              <span className="font-mono text-xs">
                {attachment.filename} · {formatBytes(attachment.content.length)}
              </span>
              <label className="flex items-center gap-1.5 text-xs text-ink-soft">
                Кезең басындағы қалдық, ₸
                <input
                  value={openingBalance}
                  onChange={(e) => setOpeningBalance(e.target.value)}
                  inputMode="decimal"
                  className="w-28 rounded-[3px] border border-paper-line bg-white px-2 py-0.5 text-right font-mono text-xs outline-none focus:border-brand"
                />
              </label>
              <button type="button" onClick={() => setAttachment(null)} className="ml-auto text-xs text-ink-mute hover:text-fail">
                Файлды алып тастау
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2 rounded-[3px] border-2 border-dashed border-paper-line px-3 py-3 text-sm">
              <button type="button" onClick={() => fileInput.current?.click()} className="btn-subtle">
                CSV-үзіндіні таңдау
              </button>
              <button type="button" onClick={() => void useDemo()} className="btn text-brand hover:underline">
                немесе демо-үзінді
              </button>
              <span className="text-xs text-ink-mute">5 МБ-қа дейін, файл құрылғыдан шықпайды</span>
            </div>
          )}
          {fileError && <p className="mt-2 text-sm text-fail">{fileError}</p>}
        </AgentComposer>
        <BudgetEditor suggestions={categories} />
      </div>

      <section data-swarm-focus="finance" className="mt-6 min-h-[200px]" aria-live="polite">
        {runner.running ? (
          <div className="space-y-4 rounded-lg bg-white p-5 shadow-card">
            <p className="text-sm text-ink-soft">{STAGE_LABEL[runner.latest?.status ?? "classifying_intent"]}…</p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
            <Skeleton className="h-40" />
          </div>
        ) : finance && done ? (
          <div className="space-y-5 animate-fade-up">
            {finance.report_file && (
              <div className="flex flex-wrap items-center gap-2 rounded-lg bg-white p-4 shadow-card">
                <span className="flex h-9 w-9 items-center justify-center rounded bg-fail-soft text-[10px] font-bold text-fail" aria-hidden>
                  PDF
                </span>
                <span className="mr-auto text-sm">
                  <span className="font-medium">{finance.report_file.filename}</span>
                  <span className="ml-2 text-xs text-ink-mute">{formatBytes(finance.report_file.size_bytes)}</span>
                </span>
                <a href={finance.report_file.download_url} target="_blank" rel="noreferrer" className="btn-primary">
                  PDF ашу
                </a>
                <a href={finance.report_file.download_url} download={finance.report_file.filename} className="btn-subtle">
                  Жүктеу
                </a>
                <TelegramButton send={() => api.sendReportToTelegram(finance.report_file?.report_id ?? "")} />
              </div>
            )}
            <FinanceResultView result={finance} />
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
              <ForecastCard metrics={finance.metrics} />
              <MonthOverMonthCard metrics={finance.metrics} />
            </div>
            <BudgetsCard checks={finance.budget_checks} month={finance.metrics.budget_month} />
          </div>
        ) : (
          <p className="rounded-lg border border-dashed border-paper-line p-6 text-sm text-ink-soft">
            Үзіндіні жүктеп, «Талдау» батырмасын басыңыз — агенттер есепті осында жинайды: қорытындылар, болжам, айларды салыстыру,
            бюджеттер және PDF.
          </p>
        )}
      </section>

      <h2 className="mb-3 mt-10 text-sm font-semibold uppercase tracking-wide text-ink-soft">
        Есептер мұрағаты {reports && reports.length > 0 ? <span className="font-normal">· {reports.length}</span> : null}
      </h2>
      <ReportArchive
        reports={reports}
        highlight={highlightReport}
        onDeleted={(id) => setReports((prev) => prev?.filter((r) => r.file.report_id !== id) ?? null)}
      />

      <AgentStage runner={runner} focusSelector={runner.running ? '[data-swarm-focus="finance"]' : null} scopeSelector='[data-swarm-scope="finance"]' />
    </div>
  );
}
