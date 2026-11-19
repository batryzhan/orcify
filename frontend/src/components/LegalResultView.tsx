import { useState, type FormEvent } from "react";

import { api, ApiError } from "../lib/api";
import { formatAmount, formatBytes, formatDate } from "../lib/format";
import { isValidKzId } from "../lib/kzId";
import type { ContractData, ContractEntities, ContractField, Currency, DocumentInfo, LegalResult } from "../types/api";

const FIELD_LABELS: Record<ContractField, string> = {
  client_name: "Клиент (тапсырыс беруші)",
  bin_iin: "ЖСН / БСН",
  contract_amount: "Сома",
  currency: "Валюта",
  deadline_date: "Орындау мерзімі",
  scope_of_work: "Келісімшарт нысаны",
};

const FIELDS: ContractField[] = [
  "client_name",
  "bin_iin",
  "contract_amount",
  "currency",
  "deadline_date",
  "scope_of_work",
];

const CURRENCIES: Currency[] = ["KZT", "USD", "EUR", "RUB"];

function displayValue(field: ContractField, e: ContractEntities): string {
  switch (field) {
    case "contract_amount":
      return formatAmount(e.contract_amount, e.currency);
    case "deadline_date":
      return formatDate(e.deadline_date);
    default:
      return e[field] ?? "—";
  }
}

interface Rendered {
  document: DocumentInfo;
  entities: ContractEntities;
}

export function LegalResultView({ result }: { result: LegalResult }) {
  const [rendered, setRendered] = useState<Rendered | null>(
    result.document ? { document: result.document, entities: result.entities } : null,
  );

  return (
    <section className="space-y-5 rounded-xl border border-paper-line bg-paper-card p-5">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">Өтеулі қызмет көрсету келісімшарты</h2>
        <span className="text-xs text-ink-mute">
          Мәтін — тіркелген docxtpl үлгісі, модель тек деректемелерді алды
        </span>
      </header>

      {rendered ? (
        <>
          <EntitiesTable entities={rendered.entities} />
          <DownloadCard document={rendered.document} />
        </>
      ) : (
        <CorrectionForm result={result} onRendered={setRendered} />
      )}
    </section>
  );
}

function EntitiesTable({ entities }: { entities: ContractEntities }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-[max-content_1fr]">
      {FIELDS.filter((f) => f !== "currency").map((field) => (
        <div key={field} className="contents">
          <dt className="text-sm text-ink-mute">{FIELD_LABELS[field]}</dt>
          <dd className={`text-sm ${field === "bin_iin" ? "font-mono" : ""}`}>{displayValue(field, entities)}</dd>
        </div>
      ))}
    </dl>
  );
}

function DownloadCard({ document }: { document: DocumentInfo }) {
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg border border-local/25 bg-local-soft p-4">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink">{document.filename}</p>
        <p className="mt-0.5 font-mono text-xs text-ink-soft" title={document.sha256}>
          {formatBytes(document.size_bytes)} · SHA-256 {document.sha256.slice(0, 16)}…
        </p>
      </div>
      <a
        href={document.download_url}
        download={document.filename}
        className="rounded-lg bg-local px-4 py-2 text-sm font-medium text-white hover:bg-local/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-local"
      >
        .docx жүктеу
      </a>
    </div>
  );
}

type Draft = Record<ContractField, string>;

function toDraft(e: ContractEntities): Draft {
  return {
    client_name: e.client_name ?? "",
    bin_iin: e.bin_iin ?? "",
    contract_amount: e.contract_amount ?? "",
    currency: e.currency ?? "KZT",
    deadline_date: e.deadline_date ?? "",
    scope_of_work: e.scope_of_work ?? "",
  };
}

function CorrectionForm({ result, onRendered }: { result: LegalResult; onRendered: (r: Rendered) => void }) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(result.entities));
  const [serverErrors, setServerErrors] = useState<Partial<Record<ContractField, string>>>({});
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const flagged = new Set<ContractField>([...result.missing_fields, ...result.invalid_fields]);

  const localError = (field: ContractField): string | null => {
    const value = draft[field].trim();
    if (value === "") return "Міндетті өріс";
    if (field === "bin_iin" && !isValidKzId(value)) return "Бақылау разряды дұрыс 12 цифр";
    if (field === "contract_amount" && !(Number(value.replace(",", ".")) > 0)) return "Оң сан";
    return null;
  };
  const hasErrors = FIELDS.some((f) => localError(f) !== null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (hasErrors) return;
    setSubmitting(true);
    setFailure(null);
    setServerErrors({});
    const body: ContractData = {
      client_name: draft.client_name.trim(),
      bin_iin: draft.bin_iin.trim(),
      contract_amount: draft.contract_amount.trim().replace(",", "."),
      currency: draft.currency as Currency,
      deadline_date: draft.deadline_date,
      scope_of_work: draft.scope_of_work.trim(),
    };
    try {
      const document = await api.renderContract(body);
      onRendered({ document, entities: body });
    } catch (err) {
      if (err instanceof ApiError && err.validation) {
        const next: Partial<Record<ContractField, string>> = {};
        for (const item of err.validation.detail) {
          const field = item.loc[1];
          if (typeof field === "string" && field in FIELD_LABELS) next[field as ContractField] = item.msg;
        }
        setServerErrors(next);
      } else {
        setFailure("Құжатты жасау мүмкін болмады. Бэкенд іске қосылғанын тексеріңіз.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <p className="rounded-lg bg-warn-soft px-4 py-3 text-sm text-warn">
        Модель 6 деректемеден {flagged.size}-ін таппады немесе қате тапты. Өрістерді тексеріңіз — келісімшарт
        модельге қайта жүгінбей жасалады.
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        {FIELDS.map((field) => {
          const error = serverErrors[field] ?? localError(field);
          const id = `contract-${field}`;
          const common = {
            id,
            value: draft[field],
            "aria-invalid": error !== null,
            "aria-describedby": error ? `${id}-error` : undefined,
            onChange: (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [field]: e.target.value })),
            className: `w-full rounded-lg border bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-local/40 ${
              error ? "border-fail/60" : flagged.has(field) ? "border-warn/60" : "border-paper-line"
            } ${field === "bin_iin" ? "font-mono" : ""}`,
          };
          return (
            <div key={field} className={field === "scope_of_work" || field === "client_name" ? "sm:col-span-2" : ""}>
              <label htmlFor={id} className="mb-1 flex items-center gap-2 text-sm text-ink-soft">
                {FIELD_LABELS[field]}
                {flagged.has(field) && (
                  <span className="rounded bg-warn-soft px-1.5 text-[11px] text-warn">
                    {result.missing_fields.includes(field) ? "табылмады" : "қате"}
                  </span>
                )}
              </label>
              {field === "currency" ? (
                <select {...common}>
                  {CURRENCIES.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              ) : field === "scope_of_work" ? (
                <textarea {...common} rows={3} />
              ) : (
                <input
                  {...common}
                  type={field === "deadline_date" ? "date" : "text"}
                  inputMode={field === "bin_iin" || field === "contract_amount" ? "decimal" : undefined}
                />
              )}
              {error && (
                <p id={`${id}-error`} className="mt-1 text-xs text-fail">
                  {error}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {failure && <p className="text-sm text-fail">{failure}</p>}

      <button
        type="submit"
        disabled={hasErrors || submitting}
        className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white enabled:hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {submitting ? "Жасалуда…" : "Келісімшартты жасау"}
      </button>
    </form>
  );
}
