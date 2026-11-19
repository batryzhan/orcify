import { useEffect, useState } from "react";

import type { TaskRunner } from "../../hooks/useTaskRunner";
import { api } from "../../lib/api";
import { STAGE_LABEL } from "../../lib/stages";
import type { PostRecord, PostTemplate, TemplateInfo } from "../../types/api";
import { PostResultView } from "../PostResultView";
import { AgentComposer, AgentStage, Skeleton, WindowHeader, type ComposerSample } from "../shared";

const SAMPLES: (ComposerSample & { template: PostTemplate })[] = [
  {
    label: "Знакомство с командой",
    template: "cosmos",
    text: "Сделай пост для Instagram: знакомство с командой Orcify. Мы пятеро инженеров и строим локальный ИИ, который автоматизирует бизнес-процессы без отправки данных в облако. Аккаунт @orcify.",
  },
  {
    label: "Распродажа",
    template: "neon",
    text: "Сделай пост для Instagram: чёрная пятница в сервисе доставки «Альфа Экспресс» — скидка 30% на все тарифы до воскресенья, промокод ALFA30. Аккаунт @alfa.express.",
  },
  {
    label: "Ценности",
    template: "summit",
    text: "Сделай пост-цитату для Instagram о ценностях Orcify: данные клиента не покидают устройство, мы строим ИИ, которому можно доверить коммерческую тайну.",
  },
];

/** Окно «Awesome Posts»: постановка задачи копирайтеру, превью, которое собирает рой, и галерея. */
export function PostsWindow({ runner, openPostId, onClosePost }: { runner: TaskRunner; openPostId: string | null; onClosePost: () => void }) {
  const [text, setText] = useState("");
  const [template, setTemplate] = useState<PostTemplate | null>(null);
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [posts, setPosts] = useState<PostRecord[] | null>(null);
  const result = runner.result?.smm ?? null;

  const loadPosts = () => void api.posts().then(setPosts).catch(() => setPosts([]));
  useEffect(() => {
    void api.postTemplates().then(setTemplates).catch(() => setTemplates([]));
    loadPosts();
  }, []);
  useEffect(() => {
    if (runner.latest?.status === "completed") loadPosts();
  }, [runner.latest?.status]);

  const open = openPostId ? (posts?.find((p) => p.post.post_id === openPostId) ?? null) : null;

  return (
    <div className="px-4 pb-28 pt-5 sm:px-8" data-swarm-scope="posts">
      <WindowHeader title="Awesome Posts">
        Gemma пишет только тексты, а рендерер кладёт их на фон шаблона — получается готовый пост 1080×1350. Всё локально;
        в Telegram пост уходит только по кнопке.
      </WindowHeader>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-5">
          <AgentComposer
            id="post-text"
            label="Задача копирайтеру"
            hint="о чём пост, для кого, аккаунт бренда"
            placeholder="Например: пост про открытие новой кофейни, акция −20% в первую неделю, аккаунт @coffee.almaty"
            text={text}
            onText={setText}
            samples={SAMPLES}
            onSample={(s) => {
              setText(s.text);
              setTemplate(SAMPLES.find((x) => x.label === s.label)?.template ?? null);
            }}
            runner={runner}
            submitLabel="Сделать пост"
            onSubmit={() => void runner.submit({ text: text.trim(), domain: "SMM", ...(template ? { post_template: template } : {}) })}
          >
            <fieldset>
              <legend className="mb-2 text-xs font-semibold text-ink-soft">Шаблон</legend>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup">
                <TemplateTile selected={template === null} onSelect={() => setTemplate(null)} title="Авто" note="выберет модель" />
                {templates.map((t) => (
                  <TemplateTile key={t.id} selected={template === t.id} onSelect={() => setTemplate(t.id)} title={t.title} note={t.use_case} image={t.preview_url} />
                ))}
              </div>
            </fieldset>
          </AgentComposer>

          {result && runner.latest?.status === "completed" && (
            <section className="rounded-lg bg-white p-5 shadow-card animate-fade-up">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-soft">Готово</h2>
              <PostResultView post={result.post} content={result.content} hideImage />
            </section>
          )}
        </div>

        <div className="lg:sticky lg:top-4 lg:self-start">
          <div
            data-swarm-focus="posts"
            className="relative aspect-[4/5] overflow-hidden rounded-lg bg-[#1d2125] shadow-raised"
            aria-live="polite"
          >
            {runner.running ? (
              <div className="flex h-full flex-col items-center justify-center gap-4 p-8">
                <Skeleton className="h-10 w-3/4 bg-white/10" />
                <Skeleton className="h-10 w-2/3 bg-white/10" />
                <Skeleton className="h-4 w-1/2 bg-white/10" />
                <p className="mt-4 text-center text-sm text-white/70">{STAGE_LABEL[runner.latest?.status ?? "classifying_intent"]}…</p>
              </div>
            ) : result ? (
              <img src={result.post.image_url} alt={`${result.content.headline} ${result.content.headline_accent}`} className="h-full w-full animate-fade-up object-cover" />
            ) : (
              <div className="flex h-full flex-col items-center justify-center p-8 text-center text-sm text-white/60">
                Здесь появится пост. Опишите задачу и нажмите «Сделать пост» — агенты соберут его прямо здесь.
              </div>
            )}
          </div>
        </div>
      </div>

      <h2 className="mb-3 mt-10 text-sm font-semibold uppercase tracking-wide text-ink-soft">
        Готовые посты {posts && posts.length > 0 ? <span className="font-normal">· {posts.length}</span> : null}
      </h2>
      {posts === null ? (
        <p className="text-sm text-ink-mute">Загрузка…</p>
      ) : posts.length === 0 ? (
        <p className="rounded-md border border-dashed border-paper-line p-6 text-sm text-ink-soft">Пока пусто — первый пост появится здесь.</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {posts.map((record) => (
            <a
              key={record.post.post_id}
              href={`#/posts?post=${record.post.post_id}`}
              data-swarm-target
              className="group overflow-hidden rounded-lg bg-white text-left shadow-card hover:shadow-raised"
            >
              <img src={record.post.image_url} alt="" loading="lazy" className="block aspect-[4/5] w-full object-cover" />
              <span className="block truncate px-3 pt-2 text-sm font-medium text-ink">
                {record.content.headline} {record.content.headline_accent}
              </span>
              <span className="block px-3 pb-2.5 text-xs text-ink-mute">
                {record.post.template} · {new Date(record.post.created_at).toLocaleDateString("ru-RU")}
                {record.issue_key ? ` · ${record.issue_key}` : ""}
              </span>
            </a>
          ))}
        </div>
      )}

      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#091e42]/50 p-3 sm:p-8" onMouseDown={(e) => e.target === e.currentTarget && onClosePost()}>
          <div role="dialog" aria-modal="true" aria-label="Пост" className="w-full max-w-4xl animate-fade-up rounded-lg bg-white p-5 shadow-raised">
            <div className="mb-4 flex items-center justify-between gap-3">
              <p className="text-lg font-semibold">
                {open.content.headline} {open.content.headline_accent}
              </p>
              <button type="button" onClick={onClosePost} className="btn-subtle">
                Закрыть
              </button>
            </div>
            <PostResultView post={open.post} content={open.content} />
          </div>
        </div>
      )}

      <AgentStage runner={runner} focusSelector={runner.running ? '[data-swarm-focus="posts"]' : null} scopeSelector='[data-swarm-scope="posts"]' />
    </div>
  );
}

function TemplateTile({ selected, onSelect, title, note, image }: { selected: boolean; onSelect: () => void; title: string; note: string; image?: string }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={`overflow-hidden rounded-md border-2 text-left transition-colors ${selected ? "border-brand" : "border-paper-line hover:border-ink-mute"}`}
    >
      {image ? (
        <img src={image} alt="" loading="lazy" className="block aspect-[4/5] w-full object-cover" />
      ) : (
        <span className="flex aspect-[4/5] w-full items-center justify-center bg-paper-col text-2xl font-semibold text-ink-mute">A</span>
      )}
      <span className="block px-2 pt-1.5 text-xs font-semibold text-ink">{title}</span>
      <span className="block truncate px-2 pb-1.5 text-[11px] text-ink-mute" title={note}>
        {note}
      </span>
    </button>
  );
}
