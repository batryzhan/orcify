import { memo } from "react";

import { useTypewriter } from "../../hooks/useTypewriter";
import { labelClass } from "../../lib/labels";
import type { JiraIssue } from "../../types/api";
import { Avatar, IssueTypeIcon, PriorityIcon } from "../icons";

interface Props {
  issue: JiraIssue;
  /** Карточку сейчас «строят» агенты: подсветка и печать заголовка. */
  active: boolean;
  onOpen: (key: string) => void;
  register: (key: string, el: HTMLElement | null) => void;
  onDragStart: (key: string) => void;
  onDragEnd: () => void;
}

const RESULT_LABEL: Record<"post" | "document" | "report", string> = {
  post: "пост",
  report: "PDF-отчёт",
  document: "договор",
};

/** Карточка задачи: только текст (результаты агентов живут в своих окнах). */
export const IssueCard = memo(function IssueCard({ issue, active, onOpen, register, onDragStart, onDragEnd }: Props) {
  const { shown, typing } = useTypewriter(issue.summary, active);
  const result = issue.attachments[0];

  return (
    <article
      ref={(el) => register(issue.key, el)}
      data-issue-key={issue.key}
      data-swarm-target
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", issue.key);
        e.dataTransfer.effectAllowed = "move";
        onDragStart(issue.key);
      }}
      onDragEnd={onDragEnd}
      className={`group relative cursor-grab rounded-md bg-paper-card p-3 shadow-card transition-colors hover:bg-[#f7f8f9] active:cursor-grabbing ${
        active ? "ring-2 ring-select/70" : ""
      }`}
      onClick={() => onOpen(issue.key)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(issue.key);
        }
      }}
      tabIndex={0}
      aria-label={`${issue.key}: ${issue.summary}`}
    >
      <p className="text-sm leading-snug text-ink">
        {shown}
        {typing && <span className="ml-px inline-block h-4 w-[2px] translate-y-0.5 animate-caret bg-select" />}
      </p>
      {issue.labels.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {issue.labels.map((label) => (
            <span key={label} className={`lozenge ${labelClass(label)}`}>
              {label}
            </span>
          ))}
        </div>
      )}
      <div className="mt-2 flex items-center gap-1.5">
        <IssueTypeIcon type={issue.type} />
        <PriorityIcon priority={issue.priority} />
        {issue.story_points !== null && (
          <span className="rounded-full bg-paper-col px-1.5 text-[11px] font-semibold tabular-nums text-ink-soft" title="Story points">
            {issue.story_points}
          </span>
        )}
        {issue.parent_key && <span className="truncate text-[11px] text-ink-mute">↳ {issue.parent_key}</span>}
        {result && (
          <span className="flex items-center gap-0.5 truncate text-[11px] text-ink-mute" title="Результат агента — в окне домена">
            <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
              <path d="M10.5 4.5L5.8 9.2a1.4 1.4 0 002 2l5-5a2.8 2.8 0 00-4-4L3.6 7.4a4.2 4.2 0 006 6l4-4" strokeLinecap="round" />
            </svg>
            {RESULT_LABEL[result.kind]}
          </span>
        )}
        <span className="ml-auto text-xs font-medium text-ink-soft">{issue.key}</span>
        <Avatar name={issue.assignee} size={22} />
      </div>
    </article>
  );
});
