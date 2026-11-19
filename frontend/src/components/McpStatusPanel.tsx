import { useEffect, useState } from "react";

import { api } from "../lib/api";
import type { Domain, McpServerHealth } from "../types/api";

const LABEL: Record<string, string> = {
  local_finance: "Local Finance",
  orcify_jira: "Orcify Jira",
  awesome_posts: "Awesome Posts",
};

/** Реестр MCPServerManager: какие серверы подключены к активному домену и в каком они состоянии. */
export function McpStatusPanel({ activeDomain }: { activeDomain: Domain | null }) {
  const [servers, setServers] = useState<McpServerHealth[] | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .mcpHealth()
      .then((s) => alive && setServers(s))
      .catch(() => alive && setServers([]));
    return () => {
      alive = false;
    };
  }, []);

  if (servers === null || servers.length === 0) return null;

  return (
    <section className="rounded-lg bg-white p-5 shadow-card">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-soft">MCP-серверы</h2>
      <ul className="space-y-2.5">
        {servers.map((s) => {
          const inScope = activeDomain === null || s.domains.includes(activeDomain);
          const state = s.reachable ? "ok" : s.enabled ? "down" : "off";
          return (
            <li key={s.name} className={`flex items-start gap-2.5 text-sm ${inScope ? "" : "opacity-40"}`}>
              <span
                aria-hidden
                className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                  state === "ok" ? "bg-[#22a06b]" : state === "down" ? "bg-fail" : "bg-ink-mute/40"
                }`}
              />
              <div className="min-w-0">
                <p className="font-medium">
                  {LABEL[s.name] ?? s.name}
                  <span className="ml-2 text-xs font-normal text-ink-mute">
                    {s.is_external ? "внешний · через анонимайзер" : "локальный"}
                  </span>
                </p>
                <p className="text-xs text-ink-mute">
                  {s.domains.join(", ")} ·{" "}
                  {state === "ok" ? s.tools.join(", ") : state === "down" ? "недоступен" : "не настроен → деградация"}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
      {activeDomain && <p className="mt-3 text-xs text-ink-mute">Smart Routing: активны только серверы домена {activeDomain}</p>}
    </section>
  );
}
