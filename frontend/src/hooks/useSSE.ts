import { useCallback, useEffect, useRef, useState } from "react";

import { isProgressEvent, TERMINAL_STATUSES, type ProgressEvent } from "../types/api";

export type SSEState = "idle" | "connecting" | "open" | "closed" | "error";

export interface ReceivedEvent {
  data: ProgressEvent;
  /** Хабар алынған сәттегі performance.now() — UI-дағы кезеңдердің тайминдері үшін. */
  at: number;
}

export interface UseSSEResult {
  events: ReceivedEvent[];
  latest: ProgressEvent | null;
  /** Жазылу сәтіндегі performance.now(). */
  startedAt: number | null;
  state: SSEState;
  error: string | null;
  close: () => void;
}

/**
 * Тапсырманың бір реттік SSE-ағынына жазылу (`progress` оқиғасы).
 *
 * Бэкендтегі ағын бір реттік: қайта қосылу 404 қайтарады, сондықтан
 * EventSource-тың кірістірілген авто-реконнектісі өшірілген — терминалдық
 * оқиғаға дейін үзілсе, хук `error` күйіне өтеді.
 *
 * Ашу бір тактіге кейінге қалдырылады: React StrictMode-та эффект
 * екі рет орнатылады, ал кідіріссіз бірінші EventSource тапсырманы «жеп қояр» еді.
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
        setError("Сервермен байланыс үзілді. Тапсырманы қайта іске қосыңыз.");
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
