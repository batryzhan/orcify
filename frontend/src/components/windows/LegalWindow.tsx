import { useState } from "react";

import type { TaskRunner } from "../../hooks/useTaskRunner";
import { STAGE_LABEL } from "../../lib/stages";
import { LegalResultView } from "../LegalResultView";
import { AgentComposer, AgentStage, Skeleton, WindowHeader, type ComposerSample } from "../shared";

const SAMPLES: ComposerSample[] = [
  {
    label: "Хат-алмасудан келісімшарт",
    text: [
      "[10:14] Менеджер: Қайырлы күн! Сайт бойынша жұмысты бастауға дайынбыз.",
      "[10:16] Клиент: Сәлеметсіз бе. Иә, келісімшартты рәсімдейік. Біз ТОО «Альфа Трейд», БСН 900101300017.",
      "[10:19] Клиент: Корпоративтік сайтты үш тілде әзірлеу және хостингті баптау қажет.",
      "[10:20] Менеджер: Құны, келіскендей, 1 250 000 теңге. Мерзімі — 2027 жылғы 15 ақпанға дейін.",
      "[10:21] Клиент: Иә, бәрі дұрыс, келісімшартты жіберіңіздер.",
    ].join("\n"),
  },
  { label: "БСН-сіз", text: "ЖК Сериковпен кеңес беру қызметтеріне келісімшарт дайында, 300 000 теңге, мерзімі 1 наурызға дейін." },
];

/** «Келісімшарттар» терезесі: хат-алмасу -> деректемелер (Structured Output) -> тексеру -> үлгі бойынша .docx. */
export function LegalWindow({ runner }: { runner: TaskRunner }) {
  const [text, setText] = useState("");
  const legal = runner.result?.legal ?? null;

  return (
    <div className="px-4 pb-28 pt-5 sm:px-8" data-swarm-scope="legal">
      <WindowHeader title="Келісімшарттар">
        Модель тек деректемелерді алады; келісімшарт мәтіні заңды үлгіден (.docx) алынады, ал ЖСН/БСН, сомалар және мерзімдер
        рендер алдында тексеріледі.
      </WindowHeader>
      <AgentComposer
        id="legal-text"
        label="Хат-алмасу немесе өтініш"
        hint="клиентпен чатты немесе шарт жобасын қойыңыз"
        placeholder="WhatsApp/Telegram-дағы хат-алмасуды деректемелермен және мәміле шарттарымен көшіріп қойыңыз…"
        text={text}
        onText={setText}
        samples={SAMPLES}
        rows={6}
        runner={runner}
        submitLabel="Келісімшарт дайындау"
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
