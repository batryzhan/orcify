import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { readPlan } from "./plan.js";

const fixture: unknown = JSON.parse(
  readFileSync("packages/contracts/fixtures/plan.json", "utf8"),
);

test("reads the Python-generated synthetic plan and preserves review holds", () => {
  const plan = readPlan(fixture);
  assert.deepEqual(plan.execution_order, ["copy", "storyboard"]);
  assert.equal(
    plan.decisions.find((d) => d.node_id === "visual")?.action,
    "REVIEW",
  );
  assert.equal(plan.estimate_status, "SIMULATED");
  assert.ok(Object.isFrozen(plan.decisions));
});

test("rejects unrecognized actions and execution of review-only nodes", () => {
  const plan = readPlan(fixture);
  assert.throws(() => readPlan({ ...plan, execution_order: ["visual"] }));
  assert.throws(() =>
    readPlan({
      ...plan,
      decisions: [{ node_id: "x", action: "PUBLISH", reasons: ["unsafe"] }],
    }),
  );
});

test("retains unknown cost as null; refuses missing explanations or measured labels", () => {
  const plan = readPlan(fixture);
  assert.equal(
    readPlan({ ...plan, expected_cost_usd: null }).expected_cost_usd,
    null,
  );
  assert.throws(() => readPlan({ ...plan, estimate_status: "MEASURED" }));
  assert.throws(() =>
    readPlan({
      ...plan,
      decisions: [{ node_id: "x", action: "KEEP", reasons: [] }],
    }),
  );
});
