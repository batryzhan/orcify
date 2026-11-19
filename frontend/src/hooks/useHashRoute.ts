import { useCallback, useEffect, useState } from "react";

export type View = "board" | "posts" | "finance" | "legal" | "automations";
const VIEWS: readonly View[] = ["board", "posts", "finance", "legal", "automations"];

export interface Route {
  view: View;
  /** «?» кейінгі параметрлер: мысалы, #/posts?post=<id> постты ашады. */
  params: URLSearchParams;
}

function parse(hash: string): Route {
  const [path = "", query = ""] = hash.replace(/^#\/?/, "").split("?");
  const view = (VIEWS as readonly string[]).includes(path) ? (path as View) : "board";
  return { view, params: new URLSearchParams(query) };
}

/** Hash-роутер: #/board, #/posts, #/finance, #/legal, #/automations (+ ?параметрлер). */
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

/** Jira карточкасынан домен терезесіндегі нәтижеге сілтеме. */
export function resultLink(url: string): { view: View; params: Record<string, string>; label: string } | null {
  const post = /\/api\/posts\/([0-9a-f]{32})\.png$/.exec(url)?.[1];
  if (post) return { view: "posts", params: { post }, label: "Awesome Posts-та ашу" };
  const report = /\/api\/finance\/reports\/([0-9a-f]{32})\.pdf$/.exec(url)?.[1];
  if (report) return { view: "finance", params: { report }, label: "Қаржыдан ашу" };
  if (url.startsWith("/api/documents/")) return { view: "legal", params: {}, label: "Келісімшарттардан ашу" };
  return null;
}
