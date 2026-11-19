import type { Domain, TaskStatus } from "../types/api";

export const STAGE_LABEL: Record<TaskStatus, string> = {
  classifying_intent: "Доменді анықтау",
  creating_jira_issue: "Orcify Jira-дағы карточка",
  updating_jira: "Карточканы жылжыту",
  routing_smm: "Awesome Posts-қа бағыттау",
  routing_finance: "Finance-қа бағыттау",
  extracting_entities: "Деректемелерді алу",
  rendering_docx: "Үлгі бойынша .docx рендері",
  analyzing_csv: "CSV жергілікті талдауы",
  generating_report: "Аналитикалық қорытынды",
  rendering_pdf: "PDF-есеп",
  writing_copy: "Пост мәтіндері",
  rendering_post: "1080×1350 пост рендері",
  planning_tasks: "Тапсырмалар жоспары",
  completed: "Дайын",
  failed: "Қате",
};

/** Доменнің күтілетін кезеңдері (қайталанатын updating_jira-сыз) — алдын ала сұр түспен көрсетіледі. */
export const STAGE_PLAN: Record<Domain | "unknown", TaskStatus[]> = {
  unknown: ["classifying_intent", "creating_jira_issue", "completed"],
  Legal: ["classifying_intent", "creating_jira_issue", "extracting_entities", "rendering_docx", "completed"],
  Finance: ["classifying_intent", "creating_jira_issue", "routing_finance", "analyzing_csv", "generating_report", "rendering_pdf", "completed"],
  SMM: ["classifying_intent", "creating_jira_issue", "routing_smm", "writing_copy", "rendering_post", "completed"],
  HR: ["classifying_intent", "creating_jira_issue", "planning_tasks", "completed"],
};
