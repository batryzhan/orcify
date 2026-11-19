// Orcify агенттері: аттар бэкенд қоятын assignee-мен сәйкес келеді (app/core/pipeline.py).
import type { Domain } from "../types/api";

export interface AgentInfo {
  name: string;
  role: string;
  color: string;
}

export const AGENTS: Record<string, AgentInfo> = {
  Router: { name: "Router", role: "Smart Routing", color: "#1d7afc" },
  Lawyer: { name: "Lawyer", role: "Келісімшарттар", color: "#8f7ee7" },
  Analyst: { name: "Analyst", role: "Қаржы", color: "#22a06b" },
  Copywriter: { name: "Copywriter", role: "Пост мәтіндері", color: "#f38a3f" },
  Designer: { name: "Designer", role: "Пост үлгілері", color: "#e774bb" },
  Planner: { name: "Planner", role: "Тапсырма жоспарлары", color: "#2898bd" },
  Courier: { name: "Courier", role: "Telegram", color: "#5e4db2" },
  Guard: { name: "Guard", role: "Құпиялылық", color: "#626f86" },
};

/** Доменнің жетекші агенттері: олардың курсорларында жазулар бар. */
export const DOMAIN_LEADS: Record<Domain, string[]> = {
  Legal: ["Router", "Lawyer"],
  Finance: ["Router", "Analyst"],
  SMM: ["Router", "Copywriter", "Designer"],
  HR: ["Router", "Planner"],
};

/** Жүйенің атаусыз «жұмысшы» курсорлары (түстері дизайн редакторларындағы курсорлар сияқты). */
export const SWARM_COLORS = ["#f87168", "#fca700", "#e2b203", "#4bce97", "#6cc3e0", "#579dff", "#9f8fef", "#e774bb"];

const FALLBACK = ["#1d7afc", "#22a06b", "#f38a3f", "#8f7ee7", "#e774bb", "#2898bd"];

export function agentColor(name: string | null): string {
  if (!name) return "#8590a2";
  const known = AGENTS[name];
  if (known) return known.color;
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return FALLBACK[hash % FALLBACK.length] ?? "#8590a2";
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return (parts.length > 1 ? `${parts[0]?.[0] ?? ""}${parts[1]?.[0] ?? ""}` : name.slice(0, 2)).toUpperCase();
}
