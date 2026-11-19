import { useCallback, useMemo, useState } from "react";

import { api } from "../lib/api";
import type { Domain, JiraIssue, TaskCreateRequest, TaskResult } from "../types/api";
import { useSSE, type UseSSEResult } from "./useSSE";

export interface TaskRunner extends UseSSEResult {
  taskId: string | null;
  submitting: boolean;
  submitError: string | null;
  running: boolean;
  result: TaskResult | null;
  domain: Domain | null;
  /** Последний снимок главной карточки задачи на доске Orcify Jira. */
  focusIssue: JiraIssue | null;
  submit: (body: TaskCreateRequest) => Promise<boolean>;
}

/** Запуск задачи агентам и подписка на её SSE-стрим (живёт на уровне App, переживает смену вкладок). */
export function useTaskRunner(): TaskRunner {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [eventsUrl, setEventsUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const sse = useSSE(eventsUrl);

  const submit = useCallback(async (body: TaskCreateRequest) => {
    setSubmitting(true);
    setSubmitError(null);
    setEventsUrl(null);
    try {
      const task = await api.createTask(body);
      setTaskId(task.task_id);
      setEventsUrl(task.events_url);
      return true;
    } catch {
      setSubmitError("Бэкенд недоступен. Запустите uvicorn в папке backend.");
      return false;
    } finally {
      setSubmitting(false);
    }
  }, []);

  const derived = useMemo(() => {
    const result = sse.events.find((e) => e.data.result)?.data.result ?? null;
    const domain = [...sse.events].reverse().find((e) => e.data.domain)?.data.domain ?? null;
    const firstIssue = sse.events.find((e) => e.data.issue)?.data.issue ?? null;
    const focusIssue = firstIssue
      ? ([...sse.events].reverse().find((e) => e.data.issue?.key === firstIssue.key)?.data.issue ?? firstIssue)
      : null;
    return { result, domain, focusIssue };
  }, [sse.events]);

  return {
    ...sse,
    ...derived,
    taskId,
    submitting,
    submitError,
    running: sse.state === "connecting" || sse.state === "open",
    submit,
  };
}
