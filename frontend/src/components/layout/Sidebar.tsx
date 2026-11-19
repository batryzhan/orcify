import type { View } from "../../hooks/useHashRoute";
import { BoardIcon, BoltIcon, DocIcon, ChartIcon, ImageIcon, OrcifyMark } from "../icons";

const SECTIONS: { title: string; items: { view: View; label: string; hint: string; Icon: typeof BoardIcon }[] }[] = [
  {
    title: "Жоба",
    items: [{ view: "board", label: "Jira · Тақта", hint: "Нені өзгерту, қосу, алып тастау", Icon: BoardIcon }],
  },
  {
    title: "Агенттер",
    items: [
      { view: "posts", label: "Awesome Posts", hint: "Instagram посттары", Icon: ImageIcon },
      { view: "finance", label: "Қаржы", hint: "Үзінділер, PDF, бюджеттер", Icon: ChartIcon },
      { view: "legal", label: "Келісімшарттар", hint: "Хат-алмасудан келісімшарт", Icon: DocIcon },
    ],
  },
  {
    title: "Интеграциялар",
    items: [{ view: "automations", label: "Автоматтандыру", hint: "Telegram-бот", Icon: BoltIcon }],
  },
];

/** Бүйірлік навигация (тар экрандарда — жоғарғы көлденең жолақ). Нүкте — терезеде агенттер жұмыс істеуде. */
export function Sidebar({ view, onNavigate, running }: { view: View; onNavigate: (v: View) => void; running: Record<View, boolean> }) {
  return (
    <aside className="border-b border-paper-line bg-paper md:sticky md:top-0 md:h-screen md:w-60 md:shrink-0 md:overflow-y-auto md:border-b-0 md:border-r">
      <div className="flex items-center gap-2.5 px-4 py-3 md:py-5">
        <OrcifyMark className="h-8 w-8 shrink-0" />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">Orcify</p>
          <p className="truncate text-xs text-ink-mute">Жергілікті ЖИ-агенттер</p>
        </div>
      </div>
      <nav aria-label="Бөлімдер" className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-4">
        {SECTIONS.map((section) => (
          <div key={section.title} className="contents md:block">
            <p className="hidden px-2 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-ink-mute md:block">{section.title}</p>
            {section.items.map(({ view: v, label, hint, Icon }) => {
              const current = v === view;
              return (
                <button
                  key={v}
                  type="button"
                  data-swarm-target
                  onClick={() => onNavigate(v)}
                  aria-current={current ? "page" : undefined}
                  className={`relative flex w-full shrink-0 items-center gap-3 rounded-[3px] px-2.5 py-2 text-left text-sm md:mb-0.5 ${
                    current ? "bg-brand-soft font-medium text-brand" : "text-ink-soft hover:bg-paper-col hover:text-ink"
                  }`}
                >
                  {current && <span className="absolute inset-y-1.5 left-0 hidden w-[3px] rounded-r bg-brand md:block" aria-hidden />}
                  <Icon className="h-5 w-5 shrink-0" />
                  <span className="min-w-0">
                    <span className="block whitespace-nowrap">{label}</span>
                    <span className="hidden text-xs font-normal text-ink-mute md:block">{hint}</span>
                  </span>
                  {running[v] && <span className="ml-auto h-2 w-2 shrink-0 animate-pulse rounded-full bg-select" title="Агенттер жұмыс істеуде" />}
                </button>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
