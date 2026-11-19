import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../lib/api";
import type { IssueUpdate, JiraBoard, JiraIssue } from "../types/api";

const POLL_MS = 4000;

export interface BoardState {
  board: JiraBoard | null;
  error: boolean;
  apply: (issue: JiraIssue) => void;
  update: (key: string, changes: IssueUpdate) => Promise<void>;
  remove: (key: string) => Promise<void>;
  reload: () => Promise<void>;
}

/** Карточка суретін бэкендтегідей қолданады: басқа бағанға көшіру — бағанның жоғарғы жағына. */
function upsert(issues: JiraIssue[], issue: JiraIssue): JiraIssue[] {
  const index = issues.findIndex((i) => i.key === issue.key);
  if (index === -1) return [issue, ...issues];
  const current = issues[index];
  if (current && current.status !== issue.status) {
    return [issue, ...issues.filter((i) => i.key !== issue.key)];
  }
  const next = [...issues];
  next[index] = issue;
  return next;
}

/**
 * Orcify Jira тақтасы. Агенттер жұмыс істегенде карточкалар SSE-ден жаңарады (apply);
 * тыныштықта тақта сұратылады, Telegram-боттан келген тапсырмаларды көрсету үшін.
 */
export function useBoard(polling: boolean): BoardState {
  const [board, setBoard] = useState<JiraBoard | null>(null);
  const [error, setError] = useState(false);

  const signature = useRef<string | null>(null); // null: тақта әлі жүктелмеген (бос тақта "" береді)
  const reload = useCallback(async () => {
    try {
      const next = await api.board();
      // Әр 4 с сайын сұрау: тақтаны тек бір нәрсе өзгерсе қайта салады.
      const sig = next.issues.map((i) => `${i.key}:${i.updated_at}`).join("|");
      if (sig !== signature.current) {
        signature.current = sig;
        setBoard(next);
      }
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!polling) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void reload();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [polling, reload]);

  const apply = useCallback((issue: JiraIssue) => {
    setBoard((prev) => (prev ? { ...prev, issues: upsert(prev.issues, issue) } : prev));
  }, []);

  const update = useCallback(
    async (key: string, changes: IssueUpdate) => {
      apply(await api.updateIssue(key, changes));
    },
    [apply],
  );

  const remove = useCallback(async (key: string) => {
    await api.deleteIssue(key);
    setBoard((prev) => (prev ? { ...prev, issues: prev.issues.filter((i) => i.key !== key) } : prev));
  }, []);

  return { board, error, apply, update, remove, reload };
}
