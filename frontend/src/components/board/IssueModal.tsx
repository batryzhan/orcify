import { useEffect, useRef, useState, type ReactNode } from "react";

import { resultLink, type View } from "../../hooks/useHashRoute";
import { labelClass } from "../../lib/labels";
import type { BoardColumn, IssuePriority, IssueStatus, IssueType, IssueUpdate, JiraIssue } from "../../types/api";
import { CloseIcon, IssueTypeIcon, PRIORITY_LABEL, TYPE_LABEL } from "../icons";

interface Props {
  issue: JiraIssue;
  columns: BoardColumn[];
  onClose: () => void;
  onOpen: (key: string) => void;
  onUpdate: (key: string, changes: IssueUpdate) => Promise<void>;
  onDelete: (key: string) => Promise<void>;
  onNavigate: (view: View, params: Record<string, string>) => void;
}

const STATUS_STYLE: Record<IssueStatus, string> = {
  todo: "bg-paper-col text-ink-soft",
  in_progress: "bg-brand-soft text-brand",
  review: "bg-[#f8e6a0] text-[#7f5f01]",
  done: "bg-[#dcfff1] text-[#216e4e]",
};

const field = "w-full rounded-[3px] border-2 border-transparent bg-transparent px-2 py-1 text-sm outline-none hover:bg-paper-col focus:border-brand focus:bg-white";

function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** Карточка задачи: всё редактируется на месте (заголовок, описание, статус, тип, приоритет, метки…). */
export function IssueModal({ issue, columns, onClose, onOpen, onUpdate, onDelete, onNavigate }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [summary, setSummary] = useState(issue.summary);
  const [description, setDescription] = useState(issue.description);
  const [labelDraft, setLabelDraft] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSummary(issue.summary);
    setDescription(issue.description);
  }, [issue.key, issue.summary, issue.description]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const save = async (changes: IssueUpdate) => {
    setSaving(true);
    try {
      await onUpdate(issue.key, changes);
    } finally {
      setSaving(false);
    }
  };

  const addLabel = () => {
    const label = labelDraft.trim().toUpperCase().slice(0, 32);
    if (!label || issue.labels.includes(label) || issue.labels.length >= 6) return;
    setLabelDraft("");
    void save({ labels: [...issue.labels, label] });
  };

  const links = issue.attachments.map((a) => ({ a, link: resultLink(a.url) }));

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#091e42]/50 p-3 sm:p-8" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="issue-title" className="w-full max-w-4xl animate-fade-up rounded-lg bg-white shadow-raised">
        <header className="flex items-center gap-2 border-b border-paper-line px-5 py-3 text-sm">
          <IssueTypeIcon type={issue.type} />
          {issue.parent_key && (
            <>
              <button type="button" className="text-ink-soft hover:text-brand hover:underline" onClick={() => onOpen(issue.parent_key ?? "")}>
                {issue.parent_key}
              </button>
              <span className="text-ink-mute">/</span>
            </>
          )}
          <span className="font-medium text-ink-soft">{issue.key}</span>
          {saving && <span className="text-xs text-ink-mute">сохранение…</span>}
          <button ref={closeRef} type="button" onClick={onClose} className="ml-auto rounded p-1 text-ink-soft hover:bg-paper-col" aria-label="Закрыть">
            <CloseIcon />
          </button>
        </header>

        <div className="grid grid-cols-1 gap-6 p-5 md:grid-cols-[minmax(0,1fr)_260px]">
          <div className="min-w-0 space-y-5">
            <label className="block">
              <span className="sr-only">Название задачи</span>
              <input
                id="issue-title"
                value={summary}
                maxLength={200}
                onChange={(e) => setSummary(e.target.value)}
                onBlur={() => summary.trim() && summary !== issue.summary && void save({ summary: summary.trim() })}
                onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                className={`${field} -ml-2 text-2xl font-semibold leading-tight text-ink`}
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-semibold text-ink">Описание</span>
              <textarea
                value={description}
                maxLength={4000}
                rows={6}
                placeholder="Что нужно изменить, добавить или убрать…"
                onChange={(e) => setDescription(e.target.value)}
                onBlur={() => description !== issue.description && void save({ description })}
                className="w-full resize-y rounded-[3px] border-2 border-paper-line px-3 py-2 text-sm leading-relaxed outline-none placeholder:text-ink-mute focus:border-brand"
              />
            </label>

            {links.some((l) => l.link) && (
              <section>
                <h3 className="mb-2 text-sm font-semibold text-ink">Результат агента</h3>
                <div className="flex flex-wrap gap-2">
                  {links.map(({ a, link }) =>
                    link ? (
                      <button key={a.url} type="button" onClick={() => onNavigate(link.view, link.params)} className="btn-subtle">
                        {link.label} →
                      </button>
                    ) : null,
                  )}
                </div>
              </section>
            )}
          </div>

          <aside className="space-y-4">
            <label className="block">
              <span className="sr-only">Статус</span>
              <select
                value={issue.status}
                onChange={(e) => void save({ status: e.target.value as IssueStatus })}
                className={`w-full cursor-pointer rounded-[3px] border-0 px-3 py-2 text-sm font-semibold uppercase outline-none ${STATUS_STYLE[issue.status]}`}
              >
                {columns.map((c) => (
                  <option key={c.status} value={c.status}>
                    {c.title}
                  </option>
                ))}
              </select>
            </label>

            <dl className="space-y-2 rounded-md border border-paper-line p-3 text-sm">
              <Row label="Исполнитель">
                <input
                  defaultValue={issue.assignee ?? ""}
                  key={`a-${issue.key}-${issue.assignee ?? ""}`}
                  maxLength={40}
                  placeholder="Не назначен"
                  aria-label="Исполнитель"
                  onBlur={(e) => e.target.value.trim() && e.target.value.trim() !== issue.assignee && void save({ assignee: e.target.value.trim() })}
                  className={field}
                />
              </Row>
              <Row label="Тип">
                <select value={issue.type} aria-label="Тип" onChange={(e) => void save({ type: e.target.value as IssueType })} className={field}>
                  {(Object.keys(TYPE_LABEL) as IssueType[]).map((t) => (
                    <option key={t} value={t}>
                      {TYPE_LABEL[t]}
                    </option>
                  ))}
                </select>
              </Row>
              <Row label="Приоритет">
                <select value={issue.priority} aria-label="Приоритет" onChange={(e) => void save({ priority: e.target.value as IssuePriority })} className={field}>
                  {(Object.keys(PRIORITY_LABEL) as IssuePriority[]).map((p) => (
                    <option key={p} value={p}>
                      {PRIORITY_LABEL[p]}
                    </option>
                  ))}
                </select>
              </Row>
              <Row label="Story points">
                <select
                  value={issue.story_points ?? ""}
                  aria-label="Story points"
                  onChange={(e) => e.target.value && void save({ story_points: Number(e.target.value) })}
                  className={field}
                >
                  <option value="">—</option>
                  {[1, 2, 3, 5, 8, 13].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </Row>
              <Row label="Метки">
                <div className="flex flex-wrap items-center gap-1 px-2 py-1">
                  {issue.labels.map((l) => (
                    <button
                      key={l}
                      type="button"
                      onClick={() => void save({ labels: issue.labels.filter((x) => x !== l) })}
                      className={`lozenge ${labelClass(l)} hover:opacity-70`}
                      aria-label={`Убрать метку ${l}`}
                      title="Убрать метку"
                    >
                      {l} ✕
                    </button>
                  ))}
                  {issue.labels.length < 6 && (
                    <input
                      value={labelDraft}
                      onChange={(e) => setLabelDraft(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && addLabel()}
                      onBlur={addLabel}
                      placeholder="+ метка"
                      aria-label="Новая метка"
                      className="w-20 rounded bg-transparent px-1 text-xs outline-none focus:bg-paper-col"
                    />
                  )}
                </div>
              </Row>
            </dl>

            <div className="space-y-1 text-xs text-ink-mute">
              <p>Создано {dateTime(issue.created_at)}</p>
              <p>Обновлено {dateTime(issue.updated_at)}</p>
            </div>
            <button
              type="button"
              className="text-xs text-ink-mute hover:text-fail"
              onClick={() => {
                if (window.confirm(`Удалить ${issue.key}? Это действие нельзя отменить.`)) void onDelete(issue.key).then(onClose);
              }}
            >
              Удалить задачу
            </button>
          </aside>
        </div>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[88px_minmax(0,1fr)] items-center gap-1">
      <dt className="text-xs font-semibold text-ink-mute">{label}</dt>
      <dd className="min-w-0 text-ink">{children}</dd>
    </div>
  );
}
