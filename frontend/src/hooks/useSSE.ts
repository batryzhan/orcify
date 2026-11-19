import { useCallback, useEffect, useRef, useState } from "react";

import { isProgressEvent, TERMINAL_STATUSES, type ProgressEvent } from "../types/api";

export type SSEState = "idle" | "connecting" | "open" | "closed" | "error";

export interface ReceivedEvent {
  data: ProgressEvent;
  /** performance.now() в момент получения — для таймингов этапов в UI. */
  at: number;
}

export interface UseSSEResult {
  events: ReceivedEvent[];
  latest: ProgressEvent | null;
  /** performance.now() момента подписки. */
  startedAt: number | null;
  state: SSEState;
  error: string | null;
  close: () => void;
}

/**
 * Подписка на одноразовый SSE-стрим задачи (событие `progress`).
 *
 * Стрим на бэкенде одноразовый: повторное подключение вернёт 404, поэтому
 * встроенный авто-реконнект EventSource отключается — при обрыве до
 * терминального события хук переходит в `error`.
 *
 * Открытие откладывается на тик: в React StrictMode эффект монтируется
 * дважды, и без задержки первый EventSource «съел» бы задачу.
 */
export function useSSE(url: string | null, eventName = "progress"): UseSSEResult {
  const [events, setEvents] = useState<ReceivedEvent[]>([]);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [state, setState] = useState<SSEState>("idle");
  const [error, setError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  const close = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
  }, []);

  useEffect(() => {
    setEvents([]);
    setError(null);
    if (url === null) {
      setState("idle");
      setStartedAt(null);
      return;
    }
    setState("connecting");
    setStartedAt(performance.now());

    let finished = false;
    let source: EventSource | null = null;

    const onProgress = (message: MessageEvent<string>) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(message.data);
      } catch {
        return;
      }
      if (!isProgressEvent(parsed)) return;
      const event = parsed;
      const at = performance.now();
      setEvents((prev) => [...prev, { data: event, at }]);
      if (TERMINAL_STATUSES.has(event.status)) {
        finished = true;
        source?.close();
        setState("closed");
      }
    };

    const timer = window.setTimeout(() => {
      source = new EventSource(url);
      sourceRef.current = source;
      source.onopen = () => setState("open");
      source.addEventListener(eventName, onProgress as EventListener);
      source.onerror = () => {
        if (finished) return;
        finished = true;
        source?.close();
        setState("error");
        setError("Соединение с сервером прервано. Запустите задачу заново.");
      };
    }, 0);

    return () => {
      finished = true;
      window.clearTimeout(timer);
      source?.close();
      sourceRef.current = null;
    };
  }, [url, eventName]);

  return { events, latest: events.at(-1)?.data ?? null, startedAt, state, error, close };
}
