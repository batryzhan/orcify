/** Minimal, defensive plan view shared by the future React client. */
export const actions = ["KEEP", "RECOMPUTE", "REVIEW", "BLOCK"];
function record(value) {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new Error("Expected plan object");
    }
    return value;
}
function text(value) {
    if (typeof value !== "string" || !value.trim()) {
        throw new Error("Expected nonempty string");
    }
    return value;
}
function texts(value) {
    if (!Array.isArray(value))
        throw new Error("Expected string array");
    return Object.freeze(value.map(text));
}
function estimate(value) {
    if (value === null)
        return null;
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
        throw new Error("Invalid simulated estimate");
    }
    return value;
}
export function readPlan(value) {
    const plan = record(value);
    if (plan.estimate_status !== "SIMULATED") {
        throw new Error("Unsupported estimate status");
    }
    if (!Array.isArray(plan.decisions))
        throw new Error("Missing decisions");
    const decisions = Object.freeze(plan.decisions.map((item) => {
        const decision = record(item);
        const action = text(decision.action);
        if (!actions.some((candidate) => candidate === action)) {
            throw new Error("Unknown plan action");
        }
        const reasons = texts(decision.reasons);
        if (!reasons.length)
            throw new Error("Decision requires explanation");
        return Object.freeze({
            node_id: text(decision.node_id),
            action: action,
            reasons,
        });
    }));
    const byId = new Map(decisions.map((d) => [d.node_id, d]));
    if (byId.size !== decisions.length)
        throw new Error("Duplicate node decisions");
    const execution = texts(plan.execution_order);
    if (new Set(execution).size !== execution.length ||
        execution.some((id) => byId.get(id)?.action !== "RECOMPUTE")) {
        throw new Error("Unsafe execution order");
    }
    const hash = text(plan.plan_hash);
    if (!/^[a-f0-9]{64}$/.test(hash))
        throw new Error("Invalid plan hash");
    return Object.freeze({
        event_id: text(plan.event_id),
        plan_hash: hash,
        decisions,
        execution_order: execution,
        non_publishable_ids: texts(plan.non_publishable_ids),
        estimate_status: "SIMULATED",
        expected_cost_usd: estimate(plan.expected_cost_usd),
        expected_latency_s: estimate(plan.expected_latency_s),
    });
}
