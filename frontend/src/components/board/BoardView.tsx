import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { useBoard } from "../../hooks/useBoard";
import type { View } from "../../hooks/useHashRoute";
import type { TaskRunner } from "../../hooks/useTaskRunner";
import { api } from "../../lib/api";
import type { IssuePriority, IssueStatus, IssueType, JiraIssue } from "../../types/api";
import { PRIORITY_LABEL, SearchIcon, TYPE_LABEL } from "../icons";
import { AgentComposer, AgentStage, WindowHeader, type ComposerSample } from "../shared";
import { IssueCard } from "./IssueCard";
import { IssueModal } from "./IssueModal";

const PLANNER_SAMPLES: ComposerSample[] = [
  { label: "Дизайнерді онбордингке қабылдау", text: "Жаңа дизайнерді онбордингке қабылдау жоспарын құр: жұмыс орны мен қолжетімділіктер, командамен танысу, қабылдау бұйрығы, тәлімгер және алғашқы тапсырма." },
  { label: "Сайтты жетілдіру", text: "Олимпиададан бұрын Orcify лендингінде нені өзгерту керек: скриншоттарды жаңарту, құпиялылық туралы бөлім қосу, бейне туралы ескірген блокты алып тастау, мобильді нұсқаны тексеру." },
];

interface Props {
  /** Planner раннері: мақсатты тапсырмаларға тақтаның өзінде бөледі. */
  runner: TaskRunner;
  onNavigate: (view: View, params?: Record<string, string>) => void;
}

/** Orcify Jira: тек тапсырмалар — нені өзгерту, қосу немесе алып тастау. Агент нәтижелері — өз терезелерінде. */
export function BoardView({ runner, onNavigate }: Props) {
  const { board, error, apply, update, remove, reload } = useBoard(!runner.running);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [plannerOpen, setPlannerOpen] = useState(false);
  const [plannerText, setPlannerText] = useState("");
  const [creating, setCreating] = useState(false);
  const [dragKey, setDragKey] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<IssueStatus | null>(null);

  // Planner SSE карточка суреттері келген сайын тақтаға қолданылады.
  const applied = useRef(0);
  useEffect(() => {
    applied.current = 0;
  }, [runner.taskId]);
  useEffect(() => {
    for (const event of runner.events.slice(applied.current)) {
      if (event.data.issue) apply(event.data.issue);
    }
    applied.current = runner.events.length;
  }, [runner.events, apply]);

  // FLIP: карточкалар бағандар арасында тегіс жылжиды, жаңалары «пайда болады».
  const cardEls = useRef(new Map<string, HTMLElement>());
  const boardEl = useRef<HTMLDivElement>(null);
  const rects = useRef(new Map<string, { x: number; y: number }>());
  const register = useCallback((key: string, el: HTMLElement | null) => {
    if (el) cardEls.current.set(key, el);
    else cardEls.current.delete(key);
  }, []);
  useLayoutEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const origin = boardEl.current?.getBoundingClientRect();
    const ox = (origin?.left ?? 0) - (boardEl.current?.scrollLeft ?? 0);
    const oy = origin?.top ?? 0;
    const next = new Map<string, { x: number; y: number }>();
    cardEls.current.forEach((el, key) => {
      const r = el.getBoundingClientRect();
      const rect = { x: r.left - ox, y: r.top - oy };
      next.set(key, rect);
      const prev = rects.current.get(key);
      if (reduce || rects.current.size === 0) return;
      if (prev) {
        const dx = prev.x - rect.x;
        const dy = prev.y - rect.y;
        if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
          el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }], { duration: 480, easing: "cubic-bezier(.2,.8,.2,1)" });
        }
      } else {
        el.animate([{ opacity: 0, transform: "scale(.94) translateY(-6px)" }, { opacity: 1, transform: "none" }], {
          duration: 360,
          easing: "cubic-bezier(.2,.8,.2,1)",
        });
      }
    });
    rects.current = next;
  }, [board]);

  const issues = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (board?.issues ?? []).filter((i) => q === "" || i.summary.toLowerCase().includes(q) || i.key.toLowerCase().includes(q) || i.labels.some((l) => l.toLowerCase().includes(q)));
  }, [board, query]);

  const byStatus = useMemo(() => {
    const groups = new Map<IssueStatus, JiraIssue[]>();
    for (const issue of issues) groups.set(issue.status, [...(groups.get(issue.status) ?? []), issue]);
    return groups;
  }, [issues]);

  const focusKey = runner.focusIssue?.key ?? null;
  const openIssue = openKey ? (board?.issues.find((i) => i.key === openKey) ?? null) : null;
  const doneCount = board?.issues.filter((i) => i.status === "done").length ?? 0;

  const drop = (status: IssueStatus) => {
    const key = dragKey;
    setDragKey(null);
    setDropTarget(null);
    const issue = board?.issues.find((i) => i.key === key);
    if (key && issue && issue.status !== status) void update(key, { status });
  };

  const clear = async (scope: "done" | "all") => {
    const total = scope === "all" ? (board?.issues.length ?? 0) : doneCount;
    if (total === 0) return;
    const what = scope === "all" ? `барлық тапсырмаларды (${total})` : `орындалған тапсырмаларды (${total})`;
    if (!window.confirm(`${what} жою керек пе? Бұл әрекетті болдырмау мүмкін емес.`)) return;
    await api.clearBoard(scope);
    await reload();
  };

  return (
    <div className="px-4 pb-28 pt-5 sm:px-8">
      <WindowHeader
        title={`${board?.project_key ?? "ORC"} тақтасы`}
        actions={
          <>
            <button type="button" className="btn-primary" onClick={() => setCreating(true)}>
              + Тапсырма жасау
            </button>
            <button type="button" className="btn-subtle" aria-expanded={plannerOpen} onClick={() => setPlannerOpen((v) => !v)}>
              Planner
            </button>
            <ClearMenu doneCount={doneCount} total={board?.issues.length ?? 0} onClear={(s) => void clear(s)} />
          </>
        }
      >
        Нені өзгерту, қосу немесе алып тастау керектігінің тізімі. Карточкаларды бағандар арасында сүйреңіз; агенттер осында
        қысқа карточкалар қосады, ал олардың нәтижелері өз терезелерінде ашылады.
      </WindowHeader>

      {plannerOpen && (
        <div className="mb-5">
          <AgentComposer
            id="planner-text"
            label="Planner"
            hint="мақсатты сипаттаңыз — агент оны тақтадағы тапсырмаларға бөледі"
            placeholder="Мысалы: жобаны қорғауға демо дайындау — интерфейс пен бэкендте нені аяқтау керек"
            text={plannerText}
            onText={setPlannerText}
            samples={PLANNER_SAMPLES}
            rows={3}
            runner={runner}
            submitLabel="Тапсырмаларға бөлу"
            onSubmit={() => void runner.submit({ text: plannerText.trim(), domain: "HR" })}
          />
        </div>
      )}

      <label className="relative inline-block">
        <span className="sr-only">Тақтадан іздеу</span>
        <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-mute" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Тақтадан іздеу"
          className="w-56 rounded-[3px] border-2 border-paper-line bg-white py-1 pl-8 pr-2 text-sm outline-none focus:border-brand"
        />
      </label>

      {error && !board && (
        <p role="alert" className="mt-6 rounded-md bg-fail-soft p-4 text-sm text-fail">
          Бэкенд қолжетімсіз — тақта жүктелмеді. backend папкасында uvicorn іске қосыңыз.
        </p>
      )}

      <div ref={boardEl} data-swarm-board className="mt-4 grid grid-flow-col auto-cols-[minmax(250px,1fr)] gap-3 overflow-x-auto pb-2">
        {(board?.columns ?? []).map((column) => {
          const cards = byStatus.get(column.status) ?? [];
          const target = dropTarget === column.status && dragKey !== null;
          return (
            <section
              key={column.status}
              aria-label={column.title}
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                setDropTarget(column.status);
              }}
              onDragLeave={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDropTarget(null);
              }}
              onDrop={(e) => {
                e.preventDefault();
                drop(column.status);
              }}
              className={`flex min-h-[360px] flex-col rounded-md p-2 transition-colors ${target ? "bg-brand-soft ring-2 ring-brand/40" : "bg-paper-col"}`}
            >
              <h2 data-swarm-target className="px-1.5 pb-2 pt-1 text-xs font-semibold uppercase tracking-wide text-ink-soft">
                {column.title} <span className="ml-1 font-normal tabular-nums">{cards.length}</span>
              </h2>
              <div className="flex flex-col gap-2">
                {cards.map((issue) => (
                  <IssueCard
                    key={issue.key}
                    issue={issue}
                    active={runner.running && issue.key === focusKey}
                    onOpen={setOpenKey}
                    register={register}
                    onDragStart={setDragKey}
                    onDragEnd={() => {
                      setDragKey(null);
                      setDropTarget(null);
                    }}
                  />
                ))}
              </div>
              {board && board.issues.length === 0 && column.status === "todo" && (
                <p className="px-1.5 py-3 text-sm text-ink-mute">Тақта бос. Тапсырма жасаңыз немесе Planner-ден сұраңыз.</p>
              )}
              <QuickAdd onCreate={(summary) => api.createIssue({ summary, status: column.status }).then(apply)} />
            </section>
          );
        })}
      </div>

      <AgentStage
        runner={runner}
        focusSelector={focusKey ? `[data-issue-key="${focusKey}"]` : null}
        pulse={runner.focusIssue?.status ?? null}
        scopeSelector="[data-swarm-board]"
      />

      {creating && (
        <CreateIssueDialog
          onClose={() => setCreating(false)}
          onCreate={async (body) => {
            apply(await api.createIssue(body));
            setCreating(false);
          }}
        />
      )}

      {openIssue && board && (
        <IssueModal
          issue={openIssue}
          columns={board.columns}
          onClose={() => setOpenKey(null)}
          onOpen={setOpenKey}
          onUpdate={update}
          onDelete={remove}
          onNavigate={(view, params) => {
            setOpenKey(null);
            onNavigate(view, params);
          }}
        />
      )}
    </div>
  );
}

/** Бағанның төменгі жағындағы «+ Тапсырма жасау»: Enter — жасау, Esc — болдырмау. */
function QuickAdd({ onCreate }: { onCreate: (summary: string) => Promise<unknown> }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    setText(""); // бірден тазалаймыз: осы тапсырма жасалып жатқанда келесісін жазуға болады
    await onCreate(value);
  };
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="mt-2 rounded-[3px] px-2 py-1.5 text-left text-sm text-ink-soft hover:bg-ink/[0.06]">
        + Тапсырма жасау
      </button>
    );
  }
  return (
    <form onSubmit={(e) => void submit(e)} className="mt-2">
      <label>
        <span className="sr-only">Жаңа тапсырма атауы</span>
        <textarea
          autoFocus
          rows={2}
          value={text}
          maxLength={200}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) void submit(e);
            if (e.key === "Escape") setOpen(false);
          }}
          onBlur={() => !text.trim() && setOpen(false)}
          placeholder="Не істеу керек?"
          className="w-full resize-none rounded-md border-2 border-brand bg-white px-2.5 py-2 text-sm shadow-card outline-none"
        />
      </label>
      <p className="mt-1 text-[11px] text-ink-mute">Enter — жасау, Esc — болдырмау</p>
    </form>
  );
}

/** Жаңа тапсырманың толық формасы. */
function CreateIssueDialog({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (body: { summary: string; description: string; type: IssueType; priority: IssuePriority; labels: string[] }) => Promise<void>;
}) {
  const [summary, setSummary] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState<IssueType>("task");
  const [priority, setPriority] = useState<IssuePriority>("medium");
  const [labels, setLabels] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!summary.trim()) return;
    setBusy(true);
    try {
      await onCreate({
        summary: summary.trim(),
        description: description.trim(),
        type,
        priority,
        labels: labels.split(",").map((l) => l.trim().toUpperCase()).filter(Boolean).slice(0, 6),
      });
    } finally {
      setBusy(false);
    }
  };

  const input = "w-full rounded-[3px] border-2 border-paper-line px-3 py-2 text-sm outline-none focus:border-brand";
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#091e42]/50 p-3 sm:p-12" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form onSubmit={(e) => void submit(e)} role="dialog" aria-modal="true" aria-labelledby="create-title" className="w-full max-w-lg animate-fade-up space-y-4 rounded-lg bg-white p-5 shadow-raised">
        <h2 id="create-title" className="text-lg font-semibold">
          Жаңа тапсырма
        </h2>
        <label className="block text-sm font-semibold">
          Не істеу керек <span className="text-fail">*</span>
          <input autoFocus required maxLength={200} value={summary} onChange={(e) => setSummary(e.target.value)} className={`${input} mt-1 font-normal`} />
        </label>
        <label className="block text-sm font-semibold">
          Сипаттама
          <textarea rows={4} maxLength={4000} value={description} onChange={(e) => setDescription(e.target.value)} className={`${input} mt-1 font-normal`} />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm font-semibold">
            Түрі
            <select value={type} onChange={(e) => setType(e.target.value as IssueType)} className={`${input} mt-1 font-normal`}>
              {(Object.keys(TYPE_LABEL) as IssueType[]).map((t) => (
                <option key={t} value={t}>
                  {TYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-semibold">
            Басымдық
            <select value={priority} onChange={(e) => setPriority(e.target.value as IssuePriority)} className={`${input} mt-1 font-normal`}>
              {(Object.keys(PRIORITY_LABEL) as IssuePriority[]).map((p) => (
                <option key={p} value={p}>
                  {PRIORITY_LABEL[p]}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="block text-sm font-semibold">
          Белгілер <span className="font-normal text-ink-mute">үтір арқылы</span>
          <input value={labels} onChange={(e) => setLabels(e.target.value)} placeholder="FRONTEND, BUG" className={`${input} mt-1 font-normal`} />
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-subtle">
            Болдырмау
          </button>
          <button type="submit" disabled={!summary.trim() || busy} className="btn-primary">
            Жасау
          </button>
        </div>
      </form>
    </div>
  );
}

/** «Тақтаны тазалау»: орындалған немесе барлық тапсырмаларды жою (растаумен). */
function ClearMenu({ doneCount, total, onClear }: { doneCount: number; total: number; onClear: (scope: "done" | "all") => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button type="button" className="btn-subtle" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)} disabled={total === 0}>
        Тақтаны тазалау
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-30 mt-1 w-60 animate-fade-up rounded-md bg-white py-1 shadow-raised">
          <button
            type="button"
            role="menuitem"
            disabled={doneCount === 0}
            onClick={() => {
              setOpen(false);
              onClear("done");
            }}
            className="block w-full px-3 py-2 text-left text-sm enabled:hover:bg-paper-col disabled:opacity-40"
          >
            Орындалғандарды жою ({doneCount})
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onClear("all");
            }}
            className="block w-full px-3 py-2 text-left text-sm text-fail hover:bg-fail-soft"
          >
            Барлық тапсырманы жою ({total})
          </button>
        </div>
      )}
    </div>
  );
}
