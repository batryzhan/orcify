import {
  ArrowDownToLine,
  ArrowUpRight,
  FlaskConical,
  Info,
} from "lucide-react";
import { useState } from "react";
import {
  methodColors,
  pilotSummary,
  scenarioNames,
  sensitivity,
  sources,
  workflow,
} from "./data";

type Phase = "pilot" | "sensitivity" | "workflow";
const phaseInfo = {
  pilot: {
    code: "R1.1",
    title: "Initial planning pilot",
    note: "Five authored synthetic scenarios · three methods",
  },
  sensitivity: {
    code: "R1.2",
    title: "When would less recomputation pay off?",
    note: "A hypothetical cost model applied to saved pilot data",
  },
  workflow: {
    code: "R1.3",
    title: "Resolve the uncertainty. Replan the work.",
    note: "All 16 synthetic outcomes of four uncertain SOFT branches",
  },
};

function BarChart({
  title,
  subtitle,
  unit,
  rows,
  digits = 0,
}: {
  title: string;
  subtitle: string;
  unit: string;
  rows: Array<{ method: string; value: number }>;
  digits?: number;
}) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <figure className="research-chart">
      <figcaption>
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </figcaption>
      <div className="bar-chart">
        {rows.map((row) => (
          <div className="chart-row" key={row.method}>
            <div className="chart-row-label">
              <span style={{ background: methodColors[row.method] }} />
              {row.method}
            </div>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{
                  width: `${(row.value / max) * 100}%`,
                  background: methodColors[row.method],
                }}
              />
            </div>
            <span className="bar-value">
              {row.value.toFixed(digits)}
              <small>{unit}</small>
            </span>
          </div>
        ))}
      </div>
      <div className="chart-axis">
        <span>0</span>
        <span>
          {max.toFixed(digits)} {unit}
        </span>
      </div>
    </figure>
  );
}

function PilotResults() {
  const [scenario, setScenario] = useState("all");
  const rows = pilotSummary(scenario);
  return (
    <>
      <div className="experiment-filter">
        <div>
          <label htmlFor="pilot-scenario">Workflow scenario</label>
          <select
            id="pilot-scenario"
            value={scenario}
            onChange={(event) => setScenario(event.target.value)}
          >
            <option value="all">All five scenarios — combined counts</option>
            {Object.entries(scenarioNames).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <span className="data-label">SYNTHETIC FIXTURES · RECORDED PLANS</span>
      </div>
      <div className="result-chart-grid">
        <BarChart
          title="Immediate recomputation"
          subtitle="Operations scheduled before uncertain reviews are resolved"
          unit="ops"
          rows={rows.map((row) => ({
            method: row.method,
            value: row.recomputes,
          }))}
        />
        <BarChart
          title="Review-operation proxy"
          subtitle="Distinct assets requiring review or approval work, not human minutes"
          unit="ops"
          rows={rows.map((row) => ({ method: row.method, value: row.reviews }))}
        />
      </div>
      <div className="result-interpretation">
        <Info size={18} />
        <div>
          <strong>
            {scenario === "all_hard_fanout_no_advantage"
              ? "The all-HARD case gives no recomputation advantage."
              : "Fewer immediate recomputations do not mean the work is gone."}
          </strong>
          <p>
            {scenario === "all_hard_fanout_no_advantage"
              ? "All three methods schedule four recomputations here. The additional GAMO-CA planning work has no recomputation benefit in this workload."
              : "Across all five cases, eight asset operations wait behind four uncertain SOFT branches. Material outcomes add them back on replanning. Only one field-disjoint asset is kept instead of recomputed by the conventional DAG."}
          </p>
        </div>
      </div>
      <BarChart
        title="Planning overhead in the current implementation"
        subtitle={
          scenario === "all"
            ? "Median of the five per-case timing medians; plan calls only"
            : "Saved median of 101 repeated planner calls for this case"
        }
        unit="ms"
        digits={4}
        rows={rows.map((row) => ({
          method: row.method,
          value: row.planningMs,
        }))}
      />
      <p className="chart-caveat">
        GAMO-CA’s observed planning time is higher. It validates graphs, hashes
        state, and builds explanations; the baseline functions do much less
        work. This comparison does not isolate algorithmic runtime and excludes
        generation, human work, and I/O. Field-aware DAG was not evaluated in
        R1.1. Aggregate timing medians here are calculated from the CSV; the
        historical R1.1 prose reports different median values.
      </p>
      <details className="source-details">
        <summary>Read the numeric values</summary>
        <div className="research-table-wrap">
          <table className="research-table">
            <thead>
              <tr>
                <th>Method</th>
                <th>Recompute ops</th>
                <th>Review proxy</th>
                <th>Planner median (ms)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.method}>
                  <th>{row.method}</th>
                  <td>{row.recomputes}</td>
                  <td>{row.reviews}</td>
                  <td>{row.planningMs.toFixed(6)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}

function SensitivityResults() {
  const [q, setQ] = useState(0.5);
  const [human, setHuman] = useState(1);
  const [planning, setPlanning] = useState(0.1);
  const rows = sensitivity.filter(
    (row) =>
      row.q === q && row.reviewWeight === human && row.planWeight === planning,
  );
  const gamo = rows.find((row) => row.method === "GAMO-CA")!;
  const dag = rows.find((row) => row.method === "Conventional DAG")!;
  return (
    <>
      <div className="assumption-banner">
        <FlaskConical size={18} />
        <span>
          <strong>HYPOTHETICAL WORK UNITS.</strong> Cost weights and
          material-review fraction are assumptions. They are not measured costs,
          currency, human time, or probabilities.
        </span>
      </div>
      <div className="sensitivity-controls">
        <label>
          <span>Material SOFT-branch fraction, q</span>
          <select
            value={q}
            onChange={(event) => setQ(Number(event.target.value))}
          >
            {[0, 0.25, 0.5, 0.75, 1].map((value) => (
              <option key={value} value={value}>
                {value * 100}% assumed material
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Review units / operation</span>
          <select
            value={human}
            onChange={(event) => setHuman(Number(event.target.value))}
          >
            {[0.25, 1, 4].map((value) => (
              <option key={value} value={value}>
                {value} assumed units
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Planning units / millisecond</span>
          <select
            value={planning}
            onChange={(event) => setPlanning(Number(event.target.value))}
          >
            {[0, 0.01, 0.1, 1].map((value) => (
              <option key={value} value={value}>
                {value} assumed units
              </option>
            ))}
          </select>
        </label>
      </div>
      <BarChart
        title="Total cost under the selected assumptions"
        subtitle="Directly selected rows from the preserved R1.2 sensitivity CSV"
        unit="units"
        digits={2}
        rows={rows.map((row) => ({ method: row.method, value: row.total }))}
      />
      <div className="result-interpretation">
        <Info size={18} />
        <div>
          <strong>
            {gamo.total < dag.total
              ? "GAMO-CA has a lower hypothetical total than conventional DAG here."
              : "Conventional DAG has a lower or equal hypothetical total here."}
          </strong>
          <p>
            Raising the assumed price of planning can reverse the preference.
            R1.2 models GAMO-CA recomputation as 12 + 8q and compares it with
            the eager conventional DAG. It does not include the later
            field-aware DAG comparison and cannot establish real savings.
          </p>
        </div>
      </div>
      <div className="research-table-wrap">
        <table className="research-table">
          <caption>Separate model components — hypothetical units</caption>
          <thead>
            <tr>
              <th>Method</th>
              <th>Recomputation</th>
              <th>Review</th>
              <th>Planning</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.method}>
                <th>{row.method}</th>
                <td>{row.recomputeCost.toFixed(3)}</td>
                <td>{row.reviewCost.toFixed(3)}</td>
                <td>{row.planCost.toFixed(3)}</td>
                <td>
                  <strong>{row.total.toFixed(3)}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="formula-card">
        <code>C = c_recompute × R + c_review × H + c_plan × T</code>
        <p>
          R = recomputations, H = review operations, T = saved planner
          milliseconds. R1.3 keeps initial planning and replanning separate. No
          model estimates the unknown amount of real human effort.
        </p>
      </div>
    </>
  );
}

const branchLabels = [
  "S01 · Social export",
  "S02 · Layout review",
  "S03 · Caption",
  "S04 · Legal montage",
];
function WorkflowResults() {
  const [outcome, setOutcome] = useState("NNNN");
  const rows = workflow.filter((row) => row.outcome === outcome);
  const toggle = (index: number) =>
    setOutcome((old) =>
      [...old]
        .map((char, i) => (i === index ? (char === "M" ? "N" : "M") : char))
        .join(""),
    );
  return (
    <>
      <div className="assumption-banner">
        <FlaskConical size={18} />
        <span>
          <strong>SYNTHETIC REVIEW OUTCOMES.</strong> Four binary branches
          produce 2⁴ = 16 combinations. These toggles select already saved test
          outcomes; they do not represent real reviewer responses.
        </span>
      </div>
      <div className="branch-controls">
        {branchLabels.map((label, index) => (
          <button
            key={label}
            className={
              outcome[index] === "M"
                ? "branch-toggle material"
                : "branch-toggle"
            }
            aria-pressed={outcome[index] === "M"}
            onClick={() => toggle(index)}
          >
            <span>{label}</span>
            <strong>
              <i />
              {outcome[index] === "M" ? "Material" : "Non-material"}
            </strong>
            <small>
              {outcome[index] === "M" ? "Recompute the pair" : "Keep the pair"}
            </small>
          </button>
        ))}
      </div>
      <div className="outcome-caption">
        Selected saved outcome: <code>{outcome}</code>
        <span>
          M = material · N = non-material · each material branch adds its root
          and HARD child
        </span>
      </div>
      <BarChart
        title="Final planned recomputations"
        subtitle="Complete workflow after synthetic review resolution and replanning"
        unit="ops"
        rows={rows.map((row) => ({
          method: row.method,
          value: row.recomputes,
        }))}
      />
      <div className="result-interpretation">
        <Info size={18} />
        <div>
          <strong>Field-aware DAG matches GAMO-CA for this outcome.</strong>
          <p>
            It also matched the final actions and counts in all 16 saved
            combinations. Across them, GAMO-CA schedules 12–20 final
            recomputations, not a fixed 12. These cases do not demonstrate
            superiority over a DAG using the same field information.
          </p>
        </div>
      </div>
      <div className="research-table-wrap">
        <table className="research-table">
          <caption>
            Review and replanning work — counts of required operations, not
            performed human actions
          </caption>
          <thead>
            <tr>
              <th>Method</th>
              <th>Recompute ops</th>
              <th>SOFT reviews</th>
              <th>Approval reviews</th>
              <th>Replan rounds</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.method}>
                <th>
                  <span
                    className="table-method-dot"
                    style={{ background: methodColors[row.method] }}
                  />
                  {row.method}
                </th>
                <td>{row.recomputes}</td>
                <td>{row.softReviews}</td>
                <td>{row.approvalReviews}</td>
                <td>{row.rounds}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="research-table-wrap">
        <table className="research-table">
          <caption>
            Saved plan-only timing medians for this outcome (milliseconds)
          </caption>
          <thead>
            <tr>
              <th>Method</th>
              <th>Initial planning</th>
              <th>Replanning</th>
              <th>Total overhead</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.method}>
                <th>{row.method}</th>
                <td>{row.initialMs.toFixed(4)}</td>
                <td>{row.replanMs.toFixed(4)}</td>
                <td>{row.totalMs.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="chart-caveat">
        The saved medians come from 21 workflow repetitions per outcome. Total
        medians need not equal the sum of the two component medians. GAMO-CA’s
        additional validation and explanation work makes the timing comparison
        asymmetric. No human-review or generation time was measured. A reviewer
        who remains uncertain is not modeled by these binary outcomes.
      </p>
    </>
  );
}

export function Results() {
  const [phase, setPhase] = useState<Phase>("pilot");
  const current = phaseInfo[phase];
  return (
    <div className="research-page results-page">
      <div className="section-heading page-title-row">
        <div>
          <div className="page-kicker">EVIDENCE, WITH CONTEXT</div>
          <h1>Experiments & results</h1>
          <p>
            Actual saved data. Small synthetic workloads. Conclusions kept in
            scope.
          </p>
        </div>
        <span className="research-status">
          <span /> Descriptive pilot · no significance claim
        </span>
      </div>
      <div className="result-tabs" aria-label="Experiment phase">
        {(["pilot", "sensitivity", "workflow"] as const).map((value) => (
          <button
            aria-pressed={phase === value}
            className={phase === value ? "active" : ""}
            onClick={() => setPhase(value)}
            key={value}
          >
            <span>{phaseInfo[value].code}</span>
            {value === "pilot"
              ? "Initial pilot"
              : value === "sensitivity"
                ? "Cost sensitivity"
                : "Review & replan"}
          </button>
        ))}
      </div>
      <section className="experiment-panel">
        <div className="experiment-panel-heading">
          <div>
            <span className="page-kicker">
              {current.code} / SAVED RESEARCH ARTIFACT
            </span>
            <h2>{current.title}</h2>
            <p>{current.note}</p>
          </div>
          <FlaskConical size={23} />
        </div>
        {phase === "pilot" ? (
          <PilotResults />
        ) : phase === "sensitivity" ? (
          <SensitivityResults />
        ) : (
          <WorkflowResults />
        )}
      </section>
      <section className="conclusions-panel">
        <div>
          <span className="page-kicker">THE CURRENT CONCLUSION</span>
          <h2>
            Useful engineering.
            <br />
            An open scientific question.
          </h2>
        </div>
        <div>
          <p>
            Typed dependencies and review holds make changes traceable. A
            simpler field-aware DAG can make the same impact decisions on these
            fixtures. Versioned approval and provenance are engineering
            safeguards; their benefit over a DAG with equivalent safeguards has
            not been isolated.
          </p>
          <p>
            <strong>Independent human validation is not complete.</strong> No
            real-world cost savings, AI generation measurements, statistically
            significant effect, or research novelty has been established.
          </p>
          <a className="text-link" href="#explorer">
            Walk through the mechanism <ArrowUpRight size={14} />
          </a>
        </div>
      </section>
      <section className="research-sources">
        <div>
          <h3>Inspect the source data</h3>
          <p>
            Original CSV files included with this build. No experiment is rerun
            by opening this page.
          </p>
        </div>
        <div className="source-downloads">
          {sources.map((source) => (
            <a key={source.phase} href={source.url} download={source.filename}>
              <span>{source.phase}</span>
              {source.label}
              <ArrowDownToLine size={15} />
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}
