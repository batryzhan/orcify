import { describe, expect, it } from "vitest";
import type { Graph } from "../api/client";
import { nodeKind, toFlowGraph } from "./model";

const at = "2026-10-14T10:00:00Z";
const graph = {
  tenant_id: "tenant-a",
  project_id: "project-a",
  as_of: at,
  nodes: [
    {
      id: "evidence",
      tenant_id: "tenant-a",
      project_id: "project-a",
      created_at: at,
      schema_version: 1,
      version: 1,
      content: "Confirmed source",
      valid_from: at,
      valid_to: null,
      inputs: [],
      evidence_ids: [],
      provider: "human",
      model_version: "none",
      prompt_version: "none",
      policy_version: "v1",
      estimated_cost_usd: null,
      estimated_latency_s: null,
      source_id: "brief",
      extracted_span: "Source span",
      confirmed_by: "reviewer",
    },
    {
      id: "requirement",
      tenant_id: "tenant-a",
      project_id: "project-a",
      created_at: at,
      schema_version: 1,
      version: 3,
      content: "Campaign uses cobalt blue",
      valid_from: at,
      valid_to: null,
      inputs: [],
      evidence_ids: ["evidence"],
      provider: "human",
      model_version: "none",
      prompt_version: "none",
      policy_version: "v1",
      estimated_cost_usd: null,
      estimated_latency_s: null,
      source_id: "evidence",
      status: "CONFIRMED",
      confirmed_by: "reviewer",
    },
  ],
  edges: [
    {
      id: "edge-1",
      tenant_id: "tenant-a",
      project_id: "project-a",
      created_at: at,
      schema_version: 1,
      upstream_id: "requirement",
      dependent_id: "evidence",
      strength: "HARD",
      valid_from: at,
      valid_to: null,
      relevant_fields: ["content"],
    },
  ],
} as unknown as Graph;

describe("authoritative graph mapping", () => {
  it("renders typed nodes and active dependency edges with versions", () => {
    const flow = toFlowGraph(graph);
    expect(flow.nodes).toHaveLength(2);
    expect(flow.edges).toHaveLength(1);
    expect(
      flow.nodes.find((node) => node.id === "requirement")?.data.kind,
    ).toBe("Requirement");
    expect(
      flow.nodes.find((node) => node.id === "requirement")?.data.title,
    ).toBe("Campaign uses cobalt blue");
    expect(flow.edges[0]).toMatchObject({
      source: "requirement",
      target: "evidence",
      label: "HARD",
    });
    expect(nodeKind(graph.nodes[0]!)).toBe("Evidence");
  });

  it("excludes historically closed edges from the current graph view", () => {
    const historical = {
      ...graph,
      edges: graph.edges.map((edge) => ({ ...edge, valid_to: at })),
    } as Graph;
    expect(toFlowGraph(historical).edges).toEqual([]);
  });
});
