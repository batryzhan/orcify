import type { Domain, TaskStatus } from "../types/api";

export const STAGE_LABEL: Record<TaskStatus, string> = {
  classifying_intent: "Определение домена",
  creating_jira_issue: "Карточка в Orcify Jira",
  updating_jira: "Перенос карточки",
  routing_smm: "Маршрутизация в Awesome Posts",
  routing_finance: "Маршрутизация в Finance",
  extracting_entities: "Извлечение реквизитов",
  rendering_docx: "Рендер .docx по шаблону",
  analyzing_csv: "Локальный анализ CSV",
  generating_report: "Аналитическое резюме",
  rendering_pdf: "PDF-отчёт",
  writing_copy: "Тексты поста",
  rendering_post: "Рендер поста 1080×1350",
  planning_tasks: "План задач",
  completed: "Готово",
  failed: "Ошибка",
};

/** Ожидаемые этапы домена (без повторяющихся updating_jira) — показываются заранее серыми. */
export const STAGE_PLAN: Record<Domain | "unknown", TaskStatus[]> = {
  unknown: ["classifying_intent", "creating_jira_issue", "completed"],
  Legal: ["classifying_intent", "creating_jira_issue", "extracting_entities", "rendering_docx", "completed"],
  Finance: ["classifying_intent", "creating_jira_issue", "routing_finance", "analyzing_csv", "generating_report", "rendering_pdf", "completed"],
  SMM: ["classifying_intent", "creating_jira_issue", "routing_smm", "writing_copy", "rendering_post", "completed"],
  HR: ["classifying_intent", "creating_jira_issue", "planning_tasks", "completed"],
};
