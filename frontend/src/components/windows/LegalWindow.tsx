import { useState } from "react";

import type { TaskRunner } from "../../hooks/useTaskRunner";
import { STAGE_LABEL } from "../../lib/stages";
import { LegalResultView } from "../LegalResultView";
import { AgentComposer, AgentStage, Skeleton, WindowHeader, type ComposerSample } from "../shared";

const SAMPLES: ComposerSample[] = [
  {
    label: "Договор из переписки",
    text: [
      "[10:14] Менеджер: Добрый день! Готовы начать работу над сайтом.",
      "[10:16] Клиент: Здравствуйте. Да, давайте оформим договор. Мы ТОО «Альфа Трейд», БИН 900101300017.",
      "[10:19] Клиент: Нужна разработка корпоративного сайта на трёх языках и настройка хостинга.",
      "[10:20] Менеджер: Стоимость, как договаривались, 1 250 000 тенге. Срок — до 15 февраля 2027 года.",
      "[10:21] Клиент: Да, всё верно, присылайте договор.",
    ].join("\n"),
  },
  { label: "Без БИН", text: "Подготовь договор с ИП Сериков на консультационные услуги, 300 000 тенге, срок до 1 марта." },
];

/** Окно «Договоры»: переписка -> реквизиты (Structured Output) -> проверка -> .docx по шаблону. */
export function LegalWindow({ runner }: { runner: TaskRunner }) {
  const [text, setText] = useState("");
  const legal = runner.result?.legal ?? null;

  return (
    <div className="px-4 pb-28 pt-5 sm:px-8" data-swarm-scope="legal">
      <WindowHeader title="Договоры">
        Модель только извлекает реквизиты; текст договора берётся из юридического шаблона (.docx), а ИИН/БИН, суммы и сроки
        проверяются перед рендером.
      </WindowHeader>
      <AgentComposer
        id="legal-text"
        label="Переписка или заявка"
        hint="вставьте чат с клиентом или черновик условий"
        placeholder="Скопируйте переписку из WhatsApp/Telegram с реквизитами и условиями сделки…"
        text={text}
        onText={setText}
        samples={SAMPLES}
        rows={6}
        runner={runner}
        submitLabel="Подготовить договор"
        onSubmit={() => void runner.submit({ text: text.trim(), domain: "Legal" })}
      />
      <section data-swarm-focus="legal" className="mt-6 min-h-[160px]" aria-live="polite">
        {runner.running ? (
          <div className="space-y-3 rounded-lg bg-white p-5 shadow-card">
            <p className="text-sm text-ink-soft">{STAGE_LABEL[runner.latest?.status ?? "classifying_intent"]}…</p>
            <Skeleton className="h-6 w-1/2" />
            <Skeleton className="h-24" />
          </div>
        ) : legal && runner.latest?.status === "completed" ? (
          <div className="animate-fade-up">
            <LegalResultView key={runner.taskId ?? "legal"} result={legal} />
          </div>
        ) : null}
      </section>
      <AgentStage runner={runner} focusSelector={runner.running ? '[data-swarm-focus="legal"]' : null} scopeSelector='[data-swarm-scope="legal"]' />
    </div>
  );
}
