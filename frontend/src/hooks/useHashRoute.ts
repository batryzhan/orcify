import { useCallback, useEffect, useState } from "react";

export type View = "board" | "posts" | "finance" | "legal" | "automations";
const VIEWS: readonly View[] = ["board", "posts", "finance", "legal", "automations"];

export interface Route {
  view: View;
  /** Параметры после «?»: например #/posts?post=<id> открывает пост. */
  params: URLSearchParams;
}

function parse(hash: string): Route {
  const [path = "", query = ""] = hash.replace(/^#\/?/, "").split("?");
  const view = (VIEWS as readonly string[]).includes(path) ? (path as View) : "board";
  return { view, params: new URLSearchParams(query) };
}

/** Роутер на hash: #/board, #/posts, #/finance, #/legal, #/automations (+ ?параметры). */
export function useHashRoute(): [Route, (view: View, params?: Record<string, string>) => void] {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const navigate = useCallback((next: View, params?: Record<string, string>) => {
    const query = params ? `?${new URLSearchParams(params).toString()}` : "";
    window.location.hash = `/${next}${query}`;
  }, []);
  return [route, navigate];
}

/** Ссылка из карточки Jira на результат в окне домена. */
export function resultLink(url: string): { view: View; params: Record<string, string>; label: string } | null {
  const post = /\/api\/posts\/([0-9a-f]{32})\.png$/.exec(url)?.[1];
  if (post) return { view: "posts", params: { post }, label: "Открыть в Awesome Posts" };
  const report = /\/api\/finance\/reports\/([0-9a-f]{32})\.pdf$/.exec(url)?.[1];
  if (report) return { view: "finance", params: { report }, label: "Открыть в Финансах" };
  if (url.startsWith("/api/documents/")) return { view: "legal", params: {}, label: "Открыть в Договорах" };
  return null;
}
