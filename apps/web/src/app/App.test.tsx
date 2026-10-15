import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createApi,
  type Approval,
  type Artifact,
  type Plan,
} from "../api/client";
import type { Graph } from "../api/client";
import { GraphCanvas } from "../graph/GraphCanvas";
import { App, ArtifactRow, PlanResults } from "./App";

vi.mock("@xyflow/react", () => ({
  Background: () => null,
  Controls: () => null,
  Handle: () => null,
  MiniMap: () => null,
  Position: { Left: "left", Right: "right" },
  ReactFlow: ({
    nodes,
    edges,
    onNodeClick,
  }: {
    nodes: Array<{ id: string; data: { title: string } }>;
    edges: Array<{ id: string }>;
    onNodeClick: (event: unknown, node: (typeof nodes)[number]) => void;
  }) => (
    <div aria-label="mock graph">
      <span>{nodes.length} graph nodes</span>
      <span>{edges.length} graph edges</span>
      {nodes.map((node) => (
        <button key={node.id} onClick={(event) => onNodeClick(event, node)}>
          {node.data.title}
        </button>
      ))}
    </div>
  ),
}));

function renderWithQuery(element: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{element}</QueryClientProvider>,
  );
}

describe("authenticated explorer boundaries", () => {
  it("surfaces invalid and revoked credentials as an authorization error", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "invalid credential" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    renderWithQuery(<App />);
    fireEvent.change(screen.getByLabelText("Development access token"), {
      target: { value: "test-bearer-value-which-is-long-enough" },
    });
    fireEvent.click(screen.getByRole("button", { name: /continue securely/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "invalid, expired, or revoked",
    );
    const [input] = fetchMock.mock.calls[0] ?? [];
    expect(String(input)).not.toContain("test-bearer-value");
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    fetchMock.mockRestore();
  });

  it("attaches bearer only to the in-memory API request and reports authorization failures", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input) => {
        expect(
          input instanceof Request ? input.headers.get("Authorization") : null,
        ).toBe("Bearer secret-in-memory-only");
        return new Response(JSON.stringify({ detail: "membership revoked" }), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        });
      });
    await expect(
      createApi("secret-in-memory-only").tenants(),
    ).rejects.toMatchObject({
      status: 403,
      message: "membership revoked",
    } satisfies Partial<ApiError>);
    fetchMock.mockRestore();
  });

  it("shows planner actions and the exact returned explanation", () => {
    const plan = {
      event_id: "event-1",
      tenant_id: "tenant-a",
      project_id: "project-a",
      snapshot_hash: "a".repeat(64),
      policy_version: "v1",
      decisions: [
        {
          node_id: "copy",
          action: "RECOMPUTE",
          reasons: ["HARD dependency changed"],
          input_fingerprint: "b".repeat(64),
          evidence_ids: [],
        },
        {
          node_id: "note",
          action: "KEEP",
          reasons: ["No relevant dependency changed"],
          input_fingerprint: "c".repeat(64),
          evidence_ids: [],
        },
      ],
      traces: [],
      execution_order: ["copy"],
      non_publishable_ids: [],
      expected_cost_usd: null,
      expected_latency_s: null,
      estimate_status: "SIMULATED",
      plan_hash: "d".repeat(64),
    } as unknown as Plan;
    render(<PlanResults plan={plan} />);
    expect(screen.getByText("HARD dependency changed")).toBeInTheDocument();
    expect(
      screen.getByText("No relevant dependency changed"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "KEEP is a reuse decision only; it does not grant approval or publication eligibility.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Deterministic preview")).toBeInTheDocument();
  });

  it("renders the authoritative node and typed edge count on the graph canvas", () => {
    const graph = {
      tenant_id: "tenant-a",
      project_id: "project-a",
      as_of: "2026-10-14T10:00:00Z",
      nodes: [
        {
          id: "brief",
          tenant_id: "tenant-a",
          project_id: "project-a",
          created_at: "2026-10-14T10:00:00Z",
          schema_version: 1,
          version: 1,
          content: "Launch brief",
          valid_from: "2026-10-14T10:00:00Z",
          valid_to: null,
          inputs: [],
          evidence_ids: [],
          provider: "human",
          model_version: "none",
          prompt_version: "none",
          policy_version: "v1",
          estimated_cost_usd: null,
          estimated_latency_s: null,
          filename: "brief.md",
        },
      ],
      edges: [],
    } as unknown as Graph;
    render(<GraphCanvas graph={graph} selectedId="brief" onSelect={vi.fn()} />);
    expect(screen.getByText("1 graph nodes")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "brief.md" }),
    ).toBeInTheDocument();
  });

  it("shows approval binding and authoritative blocked eligibility for one exact artifact version", () => {
    const artifact = {
      artifact_version_id: "artifact-copy-1",
      artifact_id: "copy",
      version: 1,
      node_id: "copy-node",
      node_version: 4,
      graph_revision: 9,
      graph_snapshot_hash: "1".repeat(64),
      dependencies: [],
      content: "draft copy",
      content_hash: "2".repeat(64),
      planner_decision: {},
    } as unknown as Artifact;
    const approval = {
      id: "approval-copy-4",
      tenant_id: "tenant-a",
      project_id: "project-a",
      created_at: "2026-10-14T10:10:00Z",
      asset_version_id: "copy-node",
      asset_version: 4,
      requirement_fingerprint: "3".repeat(64),
      actor_id: "reviewer-1",
      decision: "APPROVED",
      policy_version: "policy-v2",
      idempotency_key: "approval-key",
      expected_revision: 9,
      reason: null,
      supersedes_id: null,
    } as unknown as Approval;
    render(
      <ArtifactRow
        artifact={artifact}
        approval={approval}
        approvalLoading={false}
        approvalError={false}
        eligibility={{
          artifact_version_id: artifact.artifact_version_id,
          eligible: false,
          reasons: ["requirement snapshot changed"],
        }}
        eligibilityError={false}
        loading={false}
      />,
    );
    expect(screen.getByText("Exact v4 · reviewer-1")).toBeInTheDocument();
    expect(
      screen.getByText(`req ${"3".repeat(10)} · policy-v2`),
    ).toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    expect(
      screen.getByText("requirement snapshot changed"),
    ).toBeInTheDocument();
  });
});
