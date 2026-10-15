import pilotCsv from "../../../../docs/research/r1_1-pilot/results.csv?raw";
import workflowCsv from "../../../../docs/research/r1_3-workflow/synthetic-workflow-results.csv?raw";
import sensitivityCsv from "../../../../docs/research/r1_2-audit/cost-sensitivity.csv?raw";
import pilotUrl from "../../../../docs/research/r1_1-pilot/results.csv?url";
import workflowUrl from "../../../../docs/research/r1_3-workflow/synthetic-workflow-results.csv?url";
import sensitivityUrl from "../../../../docs/research/r1_2-audit/cost-sensitivity.csv?url";
import type { Graph, Plan } from "../api/client";
import fixture from "./demo.json";

/** Small RFC-style CSV reader; handles quoted commas, newlines and escaped quotes. */
export function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = [];
  let row: string[] = [];
  let value = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') {
        value += '"';
        i++;
      } else quoted = !quoted;
    } else if (!quoted && (char === "," || char === "\n")) {
      row.push(value.replace(/\r$/, ""));
      value = "";
      if (char === "\n") {
        rows.push(row);
        row = [];
      }
    } else value += char;
  }
  if (quoted) throw new Error("Unclosed quote in saved research CSV");
  if (value || row.length) rows.push([...row, value.replace(/\r$/, "")]);
  const headers = rows.shift();
  if (!headers?.length) throw new Error("Saved research CSV is empty");
  return rows
    .filter((cells) => cells.some(Boolean))
    .map((cells) => {
      if (cells.length !== headers.length)
        throw new Error("Saved research CSV row has wrong width");
      return Object.fromEntries(
        headers.map((header, index) => [header, cells[index] ?? ""]),
      );
    });
}

function number(row: Record<string, string>, key: string): number {
  const value = row[key];
  if (!value?.trim() || !Number.isFinite(Number(value)))
    throw new Error(`Missing numeric research field: ${key}`);
  return Number(value);
}

export const methodColors: Record<string, string> = {
  "Full Recompute": "#8790a6",
  "Conventional DAG": "#319d98",
  "GAMO-CA": "#7854df",
  "Field-aware DAG": "#c48932",
};
export const methodNames = [
  "Full Recompute",
  "Conventional DAG",
  "GAMO-CA",
  "Field-aware DAG",
];
export const scenarioNames: Record<string, string> = {
  slogan_change: "Slogan change",
  brand_guideline_change: "Brand guideline change",
  asset_version_update: "Asset version update",
  approval_invalidation: "Approval invalidation",
  all_hard_fanout_no_advantage: "All-HARD workflow",
};

export interface PilotRow {
  scenario: string;
  method: string;
  recomputes: number;
  reviews: number;
  planningMs: number;
}
export const pilot: PilotRow[] = parseCsv(pilotCsv).map((row) => ({
  scenario: row.scenario ?? "",
  method:
    row.method === "Conventional DAG Incremental"
      ? "Conventional DAG"
      : (row.method ?? ""),
  recomputes: number(row, "recompute_operations"),
  reviews: number(row, "review_operations"),
  planningMs: number(row, "median_planning_time_ms"),
}));

export interface WorkflowRow {
  outcome: string;
  method: string;
  recomputes: number;
  softReviews: number;
  approvalReviews: number;
  rounds: number;
  initialMs: number;
  replanMs: number;
  totalMs: number;
}
export const workflow: WorkflowRow[] = parseCsv(workflowCsv).map((row) => ({
  outcome: row.outcome_set_id ?? "",
  method: row.method ?? "",
  recomputes: number(row, "final_recomputation_operations_planned"),
  softReviews: number(row, "synthetic_SOFT_resolution_reviews_required"),
  approvalReviews: number(
    row,
    "exact_version_or_renewal_approval_reviews_required",
  ),
  rounds: number(row, "replanning_rounds"),
  initialMs: number(row, "initial_planning_time_ms_measured_median_workflow"),
  replanMs: number(row, "replanning_time_ms_measured_median_workflow"),
  totalMs: number(row, "total_planning_overhead_ms_measured_median_workflow"),
}));
export const sensitivity = parseCsv(sensitivityCsv).map((row) => ({
  q: number(row, "material_review_fraction_assumption"),
  reviewWeight: number(row, "review_work_units_per_operation_assumption"),
  planWeight: number(row, "planning_work_units_per_ms_assumption"),
  method:
    row.method === "Conventional DAG Incremental"
      ? "Conventional DAG"
      : (row.method ?? ""),
  recomputeCost: number(row, "recomputation_cost_assumption"),
  reviewCost: number(row, "review_cost_assumption"),
  planCost: number(row, "planning_cost_using_assumed_rate"),
  total: number(row, "total_hypothetical_work_units"),
}));
export const sources = [
  {
    phase: "R1.1",
    label: "Pilot results",
    url: pilotUrl,
    filename: "r1_1-results.csv",
  },
  {
    phase: "R1.2",
    label: "Cost sensitivity",
    url: sensitivityUrl,
    filename: "r1_2-cost-sensitivity.csv",
  },
  {
    phase: "R1.3",
    label: "Review & replan",
    url: workflowUrl,
    filename: "r1_3-workflow-results.csv",
  },
];

export function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? (sorted[middle] ?? 0)
    : ((sorted[middle - 1] ?? 0) + (sorted[middle] ?? 0)) / 2;
}

export function pilotSummary(scenario = "all"): PilotRow[] {
  return methodNames.slice(0, 3).map((method) => {
    const rows = pilot.filter(
      (row) =>
        row.method === method &&
        (scenario === "all" || row.scenario === scenario),
    );
    return {
      scenario,
      method,
      recomputes: rows.reduce((total, row) => total + row.recomputes, 0),
      reviews: rows.reduce((total, row) => total + row.reviews, 0),
      planningMs: median(rows.map((row) => row.planningMs)),
    };
  });
}

// Generated by the Python domain's Pydantic serializers. export_presentation.py
// --check verifies both this fixture and all preserved research-file hashes.
export const demo = fixture as unknown as {
  classification: string;
  seed: number;
  source: string;
  before: string;
  proposed: string;
  target_id: string;
  asset_ids: string[];
  changed_fields: string[];
  graph: Graph;
  plan: Plan;
};
