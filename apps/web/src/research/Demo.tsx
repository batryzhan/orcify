import {
  ArrowRight,
  CircleHelp,
  Database,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { useMemo, useState } from "react";
import { App as LiveExplorer, NodeInspector } from "../app/App";
import { Button } from "../components/ui";
import { GraphCanvas } from "../graph/GraphCanvas";
import { demo } from "./data";

const labels: Record<string, string> = {
  req_slogan: "Campaign slogan",
  req_palette: "Brand palette",
  copy: "Campaign copy",
  captions: "Social captions",
  storyboard: "Storyboard",
  social_visual: "Social visual",
  social_export: "Social export",
  logo: "Logo",
  "evidence-slogan_change": "Confirmed brief evidence",
};

export function Demo() {
  const [mode, setMode] = useState<"offline" | "live">("offline");
  const [preview, setPreview] = useState(false);
  const [selected, setSelected] = useState(demo.target_id);
  const [canvasKey, setCanvasKey] = useState(0);
  const node = demo.graph.nodes.find((item) => item.id === selected)!;
  const actions = useMemo(
    () =>
      Object.fromEntries(
        demo.plan.decisions
          .filter((decision) => demo.asset_ids.includes(decision.node_id))
          .map((decision) => [decision.node_id, decision.action]),
      ),
    [],
  );
  const decisions = demo.plan.decisions.filter((decision) =>
    demo.asset_ids.includes(decision.node_id),
  );
  const selectedDecision = demo.plan.decisions.find(
    (decision) => decision.node_id === selected,
  );
  const reset = () => {
    setPreview(false);
    setSelected(demo.target_id);
    setCanvasKey((key) => key + 1);
  };

  return (
    <div className="research-page demo-page">
      <div className="section-heading page-title-row">
        <div>
          <div className="page-kicker">INTERACTIVE DEMONSTRATION</div>
          <h1>Graph & impact explorer</h1>
          <p>Trace one change through a small creative workflow.</p>
        </div>
        <div className="mode-switch" aria-label="Explorer data source">
          <button
            aria-pressed={mode === "offline"}
            onClick={() => setMode("offline")}
          >
            Presentation demo
          </button>
          <button
            aria-pressed={mode === "live"}
            onClick={() => setMode("live")}
          >
            <Database size={13} /> Live API
          </button>
        </div>
      </div>
      {mode === "live" ? (
        <div className="live-explorer-host">
          <div className="mode-notice">
            <Database size={16} />
            <span>
              <strong>Live API mode.</strong> Requires the local API and
              PostgreSQL plus a server-provisioned token. API failures stay
              visible; this view never falls back to simulated data.
            </span>
          </div>
          <LiveExplorer />
        </div>
      ) : (
        <>
          <div className="mode-notice">
            <CircleHelp size={16} />
            <span>
              <strong>SIMULATED · OFFLINE PREVIEW.</strong> Existing R1.1 graph
              and saved Python planner output. No backend writes, asset
              generation, or human approvals occur.
            </span>
            <span className="source-chip">Seed {demo.seed}</span>
          </div>
          <section className="change-panel">
            <div className="change-copy">
              <span className="page-kicker">
                FICTIONAL CAMPAIGN / SLOGAN CHANGE
              </span>
              <h2>A new message for the campaign.</h2>
              <p>
                Preview the effect of changing the confirmed slogan’s text
                field.
              </p>
            </div>
            <div className="change-values">
              <div>
                <span>Current requirement · v1</span>
                <strong>{demo.before}</strong>
              </div>
              <ArrowRight size={18} />
              <div
                className={preview ? "proposed-value active" : "proposed-value"}
              >
                <span>Proposed requirement · v2</span>
                <strong>{demo.proposed}</strong>
              </div>
            </div>
            <div className="change-buttons">
              <Button
                onClick={() => {
                  setPreview(true);
                  setSelected("copy");
                }}
                disabled={preview}
              >
                {preview ? "Impact preview shown" : "Preview slogan change"}
                <ArrowRight size={14} />
              </Button>
              <Button variant="secondary" onClick={reset}>
                <RotateCcw size={14} /> Reset demo
              </Button>
              {preview && (
                <div
                  className="preview-totals"
                  aria-live="polite"
                  aria-label="Derived asset decisions"
                >
                  {(["RECOMPUTE", "REVIEW", "KEEP"] as const).map((action) => (
                    <span
                      key={action}
                      className={`action-label ${action.toLowerCase()}`}
                    >
                      <strong>
                        {
                          decisions.filter(
                            (decision) => decision.action === action,
                          ).length
                        }
                      </strong>{" "}
                      {action}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </section>
          <div className="demo-workspace">
            <section className="demo-canvas-panel">
              <div className="demo-canvas-heading">
                <div>
                  <span className="purple-dot" />
                  <strong>Campaign dependency graph</strong>
                </div>
                <span>
                  {demo.graph.nodes.length} nodes · {demo.graph.edges.length}{" "}
                  typed links
                </span>
              </div>
              <GraphCanvas
                key={canvasKey}
                graph={demo.graph}
                selectedId={selected}
                onSelect={(item) => setSelected(item.id)}
                labels={labels}
                caption="Saved synthetic snapshot · read only"
                {...(preview ? { actions, changedId: demo.target_id } : {})}
              />
              <div className="graph-instructions">
                Scroll to zoom · drag the canvas to pan · select a node to
                inspect · use the fit-view control to recenter
              </div>
            </section>
            <aside className="demo-inspector">
              <div className="demo-inspector-heading">
                <span className="page-kicker">NODE INSPECTOR</span>
                <h3>{labels[selected] ?? selected}</h3>
              </div>
              {preview && selectedDecision && (
                <div
                  className={`selected-impact impact-note-${selectedDecision.action.toLowerCase()}`}
                >
                  <span
                    className={`action-label ${selectedDecision.action.toLowerCase()}`}
                  >
                    {selected === demo.target_id
                      ? "PROPOSED CHANGE"
                      : selectedDecision.action}
                  </span>
                  <p>
                    {selected === demo.target_id
                      ? "Proposed source update: v1 → v2. The saved snapshot remains unchanged; this is a planning preview."
                      : selectedDecision.reasons.join(" · ")}
                  </p>
                </div>
              )}
              <NodeInspector node={node} graph={demo.graph} />
            </aside>
          </div>
          <div className="decision-guide" aria-live="polite">
            <div className="section-heading">
              <div>
                <div className="page-kicker">
                  {preview ? "SAVED PLANNER DECISIONS" : "READING THE PLAN"}
                </div>
                <h2>
                  {preview
                    ? "Six assets. Three kinds of action."
                    : "Each action answers a different question."}
                </h2>
              </div>
              <span className="source-chip">
                {preview
                  ? "Derived assets only"
                  : "Select Preview slogan change to begin"}
              </span>
            </div>
            <div className="decision-card-grid">
              {(["RECOMPUTE", "REVIEW", "KEEP"] as const).map((action) => (
                <article
                  className={`decision-explainer decision-explainer-${action.toLowerCase()}`}
                  key={action}
                >
                  <div>
                    <span className={`action-label ${action.toLowerCase()}`}>
                      {action}
                    </span>
                    <strong>
                      {preview
                        ? decisions.filter((item) => item.action === action)
                            .length
                        : "—"}
                    </strong>
                  </div>
                  <p>
                    {action === "RECOMPUTE"
                      ? "A changed mandatory input makes a new version necessary."
                      : action === "REVIEW"
                        ? "Impact is uncertain. Pause this branch and its mandatory descendants."
                        : "The changed text is disjoint from this asset’s palette-related SOFT link."}
                  </p>
                  {preview && (
                    <ul>
                      {decisions
                        .filter((item) => item.action === action)
                        .map((item) => (
                          <li key={item.node_id}>
                            <button onClick={() => setSelected(item.node_id)}>
                              {labels[item.node_id] ?? item.node_id}{" "}
                              <ArrowRight size={12} />
                            </button>
                          </li>
                        ))}
                    </ul>
                  )}
                </article>
              ))}
            </div>
          </div>
          <section className="demo-footnote">
            <ShieldCheck size={18} />
            <p>
              <strong>KEEP is not approval.</strong> This preview has unresolved
              SOFT branches. New asset versions and changed requirement
              snapshots need exact-version human approval before any publication
              workflow could proceed. No publication action is available here.
            </p>
            <a className="text-link" href="#results">
              Compare the methods <ArrowRight size={14} />
            </a>
          </section>
          <details className="source-details">
            <summary>Dependency semantics & reproducibility</summary>
            <p>
              <strong>HARD:</strong> mandatory input; propagate invalidation.{" "}
              <strong>SOFT:</strong> inspect relevant fields or hold for review.{" "}
              <strong>INFORMATIONAL:</strong> context only; does not itself
              invalidate. The selected R1.1 fixture contains HARD and SOFT links
              only.
            </p>
            <p>
              Labels are friendly display names for the original node IDs;
              dependencies and decisions are unchanged. The source graph remains
              at v1 while the preview describes a proposed v2. Actual planner
              reasons appear in the inspector.
            </p>
            <code>{demo.source}</code>
            <p>
              Plan hash: <code>{demo.plan.plan_hash}</code>
            </p>
            <p>
              Re-export and check with{" "}
              <code>
                .venv/Scripts/python scripts/export_presentation.py --check
              </code>
              .
            </p>
          </details>
        </>
      )}
    </div>
  );
}
