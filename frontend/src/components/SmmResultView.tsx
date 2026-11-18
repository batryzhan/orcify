import type { PiiCategory, SmmResult } from "../types/api";

const CATEGORY_LABEL: Record<PiiCategory, string> = {
  PERSON: "люди",
  COMPANY: "компании",
  ADDRESS: "адреса",
  IIN: "ИИН",
  BIN: "БИН",
  PHONE: "телефоны",
  EMAIL: "email",
  IBAN: "счета",
  CARD: "карты",
};

/** Подсвечивает токены-плейсхолдеры [PERSON_1] в тексте, ушедшем во внешний сервис. */
function Highlighted({ text }: { text: string }) {
  const parts = text.split(/(\[[A-Z]+_\d+\])/g);
  return (
    <>
      {parts.map((part, i) =>
        /^\[[A-Z]+_\d+\]$/.test(part) ? (
          <mark key={i} className="rounded bg-local-soft px-1 font-mono text-[0.85em] text-local">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

export function SmmResultView({ result }: { result: SmmResult }) {
  const { script, video, tracker, anonymization } = result;
  const categories = Object.entries(anonymization.by_category) as [PiiCategory, number][];

  return (
    <section className="space-y-5">
      <div className="rounded-xl border border-paper-line bg-paper-card p-5">
        <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold">{script.title}</h2>
          <span className="font-mono text-xs text-ink-mute">
            {script.aspect_ratio} · {script.duration_s} с · {script.scenes.length} сцен
          </span>
        </header>
        <p className="text-sm text-ink-soft">
          <span className="text-ink">Цель:</span> {script.goal}
        </p>
        <p className="mt-1 text-sm text-ink-soft">
          <span className="text-ink">Аудитория:</span> {script.target_audience}
        </p>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="text-left text-xs text-ink-mute">
              <tr>
                <th className="w-8 py-1 font-normal">#</th>
                <th className="w-12 py-1 font-normal">Сек</th>
                <th className="py-1 font-normal">Кадр</th>
                <th className="py-1 font-normal">Закадровый текст</th>
                <th className="py-1 font-normal">На экране</th>
              </tr>
            </thead>
            <tbody>
              {script.scenes.map((s) => (
                <tr key={s.scene_no} className="border-t border-paper-line align-top">
                  <td className="py-2 font-mono text-ink-mute">{s.scene_no}</td>
                  <td className="py-2 font-mono tabular-nums text-ink-mute">{s.duration_s}</td>
                  <td className="py-2 pr-3">{s.visual}</td>
                  <td className="py-2 pr-3 text-ink-soft">{s.voiceover}</td>
                  <td className="py-2 font-medium">{s.on_screen_text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {script.hashtags.length > 0 && (
          <p className="mt-3 text-xs text-ink-mute">
            {script.hashtags.map((h) => (h.startsWith("#") ? h : `#${h}`)).join(" ")}
          </p>
        )}
      </div>

      <div className="rounded-xl border border-local/25 bg-paper-card p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">Что ушло во внешние сервисы</h3>
          <span
            className={`rounded px-2 py-0.5 text-xs ${
              anonymization.leaked_count === 0 ? "bg-local-soft text-local" : "bg-fail-soft text-fail"
            }`}
          >
            {anonymization.leaked_count === 0 ? "✓ утечек PII: 0" : `! утечек: ${anonymization.leaked_count}`}
          </span>
        </div>
        <p className="rounded-lg bg-paper p-3 font-mono text-[13px] leading-relaxed">
          <Highlighted text={result.external_prompt} />
        </p>
        <p className="mt-3 text-xs text-ink-soft">
          Замаскировано сущностей: {anonymization.entities_total}
          {categories.length > 0 && ` (${categories.map(([c, n]) => `${CATEGORY_LABEL[c]}: ${n}`).join(", ")})`}
          {anonymization.llm_detection_used ? " · поиск: регулярные выражения + локальная Gemma" : " · поиск: регулярные выражения"}
          . Таблица соответствия хранилась только в памяти и удалена после запроса.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="min-w-0 rounded-xl border border-paper-line bg-paper-card p-5">
          <h3 className="mb-2 text-sm font-semibold">Видео · Higgsfield MCP</h3>
          {video.status === "generated" && video.url ? (
            <a href={video.url} target="_blank" rel="noreferrer" className="text-sm text-local underline">
              Открыть сгенерированное видео
            </a>
          ) : (
            <div className="space-y-2 text-sm">
              <p className="rounded-md bg-warn-soft px-3 py-2 text-warn">
                Сервис недоступен — сформирована раскадровка для ручного продакшена
              </p>
              <p className="font-mono text-xs text-ink-mute">{video.error_code}</p>
            </div>
          )}
          <a
            href={result.storyboard.download_url}
            download={result.storyboard.filename}
            className="mt-3 inline-block rounded-lg border border-paper-line px-3 py-1.5 text-sm hover:border-ink-mute"
          >
            Скачать раскадровку (.md)
          </a>
        </div>
        <div className="min-w-0 rounded-xl border border-paper-line bg-paper-card p-5">
          <h3 className="mb-2 text-sm font-semibold">Задача · Atlassian MCP</h3>
          {tracker.status === "created" ? (
            <p className="text-sm">
              Создана задача <span className="font-mono font-medium">{tracker.issue_key ?? "—"}</span>
            </p>
          ) : (
            <div className="space-y-2 text-sm">
              <p className="rounded-md bg-warn-soft px-3 py-2 text-warn">
                Jira недоступна — задача сохранена в локальную очередь синхронизации
              </p>
              <p className="font-mono text-xs text-ink-mute">
                {tracker.error_code} · id {tracker.queued_id?.slice(0, 8)}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
