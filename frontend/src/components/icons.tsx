import type { IssuePriority, IssueType } from "../types/api";
import { agentColor, initials } from "../lib/agents";

type IconProps = { className?: string };

const TYPE_STYLE: Record<IssueType, { bg: string; label: string }> = {
  task: { bg: "#4688ec", label: "Тапсырма" },
  story: { bg: "#63ba3c", label: "Оқиға" },
  bug: { bg: "#e5493a", label: "Қате" },
  epic: { bg: "#904ee2", label: "Эпик" },
};

export function IssueTypeIcon({ type, className = "h-4 w-4" }: { type: IssueType } & IconProps) {
  const { bg, label } = TYPE_STYLE[type];
  return (
    <svg viewBox="0 0 16 16" className={className} role="img" aria-label={label}>
      <rect width="16" height="16" rx="3" fill={bg} />
      {type === "task" && <path d="M4.5 8.2l2.3 2.3 4.7-5" stroke="#fff" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />}
      {type === "story" && <path d="M5 3.5h6v9l-3-2.2-3 2.2z" fill="#fff" />}
      {type === "bug" && <circle cx="8" cy="8" r="3.2" fill="#fff" />}
      {type === "epic" && <path d="M9.2 2.8L4.8 9h3l-1 4.2L11.2 7h-3z" fill="#fff" />}
    </svg>
  );
}

export const TYPE_LABEL: Record<IssueType, string> = {
  task: "Тапсырма",
  story: "Оқиға",
  bug: "Қате",
  epic: "Эпик",
};

export const PRIORITY_LABEL: Record<IssuePriority, string> = {
  highest: "Ең жоғары",
  high: "Жоғары",
  medium: "Орташа",
  low: "Төмен",
};

export function PriorityIcon({ priority, className = "h-4 w-4" }: { priority: IssuePriority } & IconProps) {
  const label = PRIORITY_LABEL[priority];
  return (
    <svg viewBox="0 0 16 16" className={className} role="img" aria-label={`Басымдық: ${label}`}>
      {priority === "highest" && (
        <g stroke="#e5493a" strokeWidth="1.9" fill="none" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3.5 8.5L8 4l4.5 4.5" />
          <path d="M3.5 12.5L8 8l4.5 4.5" />
        </g>
      )}
      {priority === "high" && (
        <path d="M3.5 10.5L8 6l4.5 4.5" stroke="#f15b50" strokeWidth="1.9" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      )}
      {priority === "medium" && (
        <g stroke="#e2a03f" strokeWidth="1.9" strokeLinecap="round">
          <path d="M3.5 6.5h9" />
          <path d="M3.5 10h9" />
        </g>
      )}
      {priority === "low" && (
        <path d="M3.5 5.5L8 10l4.5-4.5" stroke="#2e7ff3" strokeWidth="1.9" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  );
}

export function Avatar({ name, size = 24 }: { name: string | null; size?: number }) {
  if (!name) {
    return (
      <span
        className="inline-flex shrink-0 items-center justify-center rounded-full bg-paper-line text-ink-mute"
        style={{ width: size, height: size }}
        title="Тағайындалмаған"
      >
        <svg viewBox="0 0 16 16" className="h-3/5 w-3/5" aria-hidden>
          <circle cx="8" cy="5.5" r="3" fill="currentColor" />
          <path d="M2.5 14c.8-3 3-4.5 5.5-4.5s4.7 1.5 5.5 4.5" fill="currentColor" />
        </svg>
      </span>
    );
  }
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white ring-2 ring-white"
      style={{ width: size, height: size, background: agentColor(name), fontSize: size * 0.4 }}
      title={name}
    >
      {initials(name)}
    </span>
  );
}

export function BoardIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg viewBox="0 0 20 20" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <rect x="2.5" y="3" width="15" height="14" rx="2" />
      <path d="M7.5 3v14M12.5 3v14" />
    </svg>
  );
}

export function ImageIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg viewBox="0 0 20 20" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <rect x="2.5" y="3" width="15" height="14" rx="2" />
      <circle cx="7.5" cy="8" r="1.6" />
      <path d="M3 15l4.5-4.5 3 3 2.5-2.5 4 4" strokeLinejoin="round" />
    </svg>
  );
}

export function BoltIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg viewBox="0 0 20 20" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d="M11 2.5L4.5 11h5l-1 6.5L15.5 9h-5z" strokeLinejoin="round" />
    </svg>
  );
}

export function ChartIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg viewBox="0 0 20 20" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d="M3 16.5h14" strokeLinecap="round" />
      <path d="M5.5 13.5V9M10 13.5V5M14.5 13.5v-6" strokeLinecap="round" />
    </svg>
  );
}

export function DocIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg viewBox="0 0 20 20" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d="M5 2.5h6.5L15 6v11.5H5z" strokeLinejoin="round" />
      <path d="M11.5 2.5V6H15M7.5 10h5M7.5 13h5" strokeLinecap="round" />
    </svg>
  );
}

export function SendIcon({ className = "h-4 w-4" }: IconProps) {
  return (
    <svg viewBox="0 0 20 20" className={className} fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
      <path d="M17.5 2.5L9 11M17.5 2.5l-5 15-3.5-6.5-6.5-3.5z" strokeLinejoin="round" />
    </svg>
  );
}

export function CloseIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg viewBox="0 0 20 20" className={className} stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
    </svg>
  );
}

export function SearchIcon({ className = "h-4 w-4" }: IconProps) {
  return (
    <svg viewBox="0 0 20 20" className={className} fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <circle cx="9" cy="9" r="5.5" />
      <path d="M13.2 13.2L17 17" strokeLinecap="round" />
    </svg>
  );
}

export function OrcifyMark({ className = "h-8 w-8" }: IconProps) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <defs>
        <linearGradient id="orcify-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1d7afc" />
          <stop offset="1" stopColor="#8f7ee7" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="7" fill="url(#orcify-g)" />
      <circle cx="16" cy="16" r="7.5" fill="none" stroke="#fff" strokeWidth="2.6" />
      <path d="M16 8.5v3M16 20.5v3M8.5 16h3M20.5 16h3" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

/** Агент курсоры: «қағаз ұшақ», қозғалыс бағытына бұрылады. */
export function AgentCursorShape({ color }: { color: string }) {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden style={{ display: "block", overflow: "visible" }}>
      <path
        d="M2 2 L19 9.2 L11 11 L8.8 19 Z"
        fill={color}
        stroke="#fff"
        strokeWidth="1.6"
        strokeLinejoin="round"
        style={{ filter: "drop-shadow(0 1px 1.5px rgba(9,30,66,.35))" }}
      />
    </svg>
  );
}
