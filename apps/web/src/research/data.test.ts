import { describe, expect, it } from "vitest";
import {
  demo,
  parseCsv,
  pilot,
  pilotSummary,
  sensitivity,
  workflow,
} from "./data";

describe("saved presentation research data", () => {
  it("reads quoted CSV values without changing their content", () => {
    expect(parseCsv('id,reason\r\na,"A comma, and ""quote"""\r\n')).toEqual([
      { id: "a", reason: 'A comma, and "quote"' },
    ]);
    expect(() => parseCsv('id,value\na,"unfinished')).toThrow();
    expect(() => parseCsv("id,value\na,1,extra")).toThrow();
  });
  it("derives original pilot totals and leaves field-aware DAG absent from R1.1", () => {
    expect(pilot).toHaveLength(15);
    expect(
      pilotSummary().map(({ method, recomputes, reviews }) => ({
        method,
        recomputes,
        reviews,
      })),
    ).toEqual([
      { method: "Full Recompute", recomputes: 24, reviews: 25 },
      { method: "Conventional DAG", recomputes: 21, reviews: 24 },
      { method: "GAMO-CA", recomputes: 12, reviews: 24 },
    ]);
    expect(
      pilotSummary("all_hard_fanout_no_advantage").map((row) => row.recomputes),
    ).toEqual([4, 4, 4]);
  });
  it("preserves all 16 synthetic outcomes and matching field-aware DAG decisions", () => {
    expect(workflow).toHaveLength(64);
    const combinations = [...new Set(workflow.map((row) => row.outcome))];
    expect(combinations).toHaveLength(16);
    for (const combination of combinations) {
      const rows = workflow.filter((row) => row.outcome === combination);
      const gamo = rows.find((row) => row.method === "GAMO-CA")!;
      expect(
        rows.find((row) => row.method === "Field-aware DAG")?.recomputes,
      ).toBe(gamo.recomputes);
      expect(gamo.recomputes).toBe(
        12 + 2 * [...combination].filter((value) => value === "M").length,
      );
      expect(gamo.rounds).toBe(4);
    }
    expect(sensitivity.some((row) => row.planWeight === 1)).toBe(true);
  });
  it("uses a labeled saved planner fixture and actual reasons without granting approval", () => {
    expect(demo.classification).toContain("SIMULATED_OFFLINE");
    const assets = demo.plan.decisions.filter((row) =>
      demo.asset_ids.includes(row.node_id),
    );
    expect(assets.filter((row) => row.action === "RECOMPUTE")).toHaveLength(3);
    expect(assets.filter((row) => row.action === "REVIEW")).toHaveLength(2);
    expect(assets.filter((row) => row.action === "KEEP")).toHaveLength(1);
    expect(assets.every((row) => row.reasons.length)).toBe(true);
  });
});
