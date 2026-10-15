import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PresentationApp } from "./PresentationApp";

vi.mock("../graph/GraphCanvas", () => ({
  GraphCanvas: ({
    actions,
    onSelect,
    graph,
  }: {
    actions?: Record<string, string>;
    graph: { nodes: { id: string }[] };
    onSelect: (node: { id: string }) => void;
  }) => (
    <div aria-label="graph preview">
      <span>{actions ? "Saved impact shown" : "Baseline snapshot shown"}</span>
      <button
        onClick={() =>
          onSelect(graph.nodes.find((node) => node.id === "social_export")!)
        }
      >
        Inspect social export
      </button>
    </div>
  ),
}));

function renderPresentation() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PresentationApp />
    </QueryClientProvider>,
  );
}
function navigate(hash: string) {
  window.location.hash = hash;
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}
beforeEach(() => {
  window.location.hash = "";
  window.scrollTo = vi.fn();
});
afterEach(cleanup);

describe("final research showcase", () => {
  it("opens without credentials or a backend request and preserves honest limitations", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderPresentation();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "One requirement changes",
    );
    expect(
      screen.getByText("Independent review is pending"),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    fetchMock.mockRestore();
  });
  it("shows the saved decisions, actual reasons, and resets deterministically", async () => {
    navigate("explorer");
    renderPresentation();
    expect(
      screen.getByText("SIMULATED · OFFLINE PREVIEW."),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /preview slogan change/i }),
    );
    expect(screen.getByText("Saved impact shown")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Inspect social export" }),
    );
    expect(screen.getByText(/SOFT impact unknown/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /reset demo/i }));
    expect(screen.getByText("Baseline snapshot shown")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /preview slogan change/i }),
    ).not.toBeDisabled();
    navigate("results");
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        "Experiments & results",
      ),
    );
  });
  it("switches to saved workflow outcomes and exposes sensitivity assumptions", () => {
    navigate("results");
    renderPresentation();
    fireEvent.click(screen.getByRole("button", { name: /review & replan/i }));
    expect(screen.getByText("NNNN")).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /S01 · Social export/i });
    fireEvent.click(toggle);
    expect(screen.getByText("MNNN")).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByText("Field-aware DAG matches GAMO-CA for this outcome."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /cost sensitivity/i }));
    expect(screen.getByText("HYPOTHETICAL WORK UNITS.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Planning units / millisecond"), {
      target: { value: "1" },
    });
    expect(
      screen.getByText(
        "Conventional DAG has a lower or equal hypothetical total here.",
      ),
    ).toBeInTheDocument();
  });
  it("requires explicitly selecting live mode before showing development login", () => {
    navigate("explorer");
    renderPresentation();
    expect(
      screen.queryByLabelText("Development access token"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /live api/i }));
    expect(
      screen.getByLabelText("Development access token"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /presentation demo/i }));
    expect(
      screen.queryByLabelText("Development access token"),
    ).not.toBeInTheDocument();
  });
});
