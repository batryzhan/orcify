import { useState } from "react";

import { api } from "../lib/api";
import { formatBytes } from "../lib/format";
import type { PostCopy, RenderedPost } from "../types/api";
import { TelegramButton } from "./shared";

const TEMPLATE_TITLE: Record<RenderedPost["template"], string> = {
  cosmos: "Cosmos",
  neon: "Neon",
  summit: "Summit",
};

/** Готовый Instagram-пост: картинка 1080×1350, подпись, хэштеги, скачивание и отправка в Telegram. */
export function PostResultView({ post, content, hideImage = false }: { post: RenderedPost; content: PostCopy; hideImage?: boolean }) {
  const [copied, setCopied] = useState(false);
  const tags = content.hashtags.map((h) => (h.startsWith("#") ? h : `#${h}`)).join(" ");
  const caption = [content.caption, tags].filter(Boolean).join("\n\n");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(caption);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className={hideImage ? "space-y-4" : "grid grid-cols-1 gap-5 md:grid-cols-[minmax(0,320px)_minmax(0,1fr)]"}>
      {!hideImage && (
        <a href={post.image_url} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-lg shadow-raised">
          <img src={post.image_url} alt={`${content.headline} ${content.headline_accent}`} className="block aspect-[4/5] w-full object-cover" />
        </a>
      )}
      <div className="min-w-0 space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-mute">Подпись к посту</p>
          <p className="mt-1.5 whitespace-pre-wrap text-sm leading-relaxed text-ink">{content.caption}</p>
          {tags && <p className="mt-2 text-sm text-brand">{tags}</p>}
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          <dt className="text-ink-mute">Шаблон</dt>
          <dd>{TEMPLATE_TITLE[post.template]}</dd>
          <dt className="text-ink-mute">Аккаунт</dt>
          <dd>{content.handle || "@orcify"}</dd>
          <dt className="text-ink-mute">Размер</dt>
          <dd className="tabular-nums">
            {post.width}×{post.height} · {formatBytes(post.size_bytes)}
          </dd>
          <dt className="text-ink-mute">Рендер</dt>
          <dd className="tabular-nums">{(post.render_ms / 1000).toFixed(2)} с, локально</dd>
        </dl>
        <div className="flex flex-wrap items-center gap-2">
          <a href={post.image_url} download className="btn-primary">
            Скачать PNG
          </a>
          <button type="button" onClick={() => void copy()} className="btn-subtle">
            {copied ? "Скопировано" : "Копировать подпись"}
          </button>
          <TelegramButton send={() => api.sendPostToTelegram(post.post_id)} />
        </div>
      </div>
    </section>
  );
}
