import {
  ArrowRight,
  Braces,
  GitBranch,
  Microscope,
  ShieldCheck,
} from "lucide-react";
import { pilotSummary, workflow } from "./data";

export function Overview() {
  const totals = pilotSummary();
  const dag = totals.find((row) => row.method === "Conventional DAG")!;
  const gamo = totals.find((row) => row.method === "GAMO-CA")!;
  const combinations = new Set(workflow.map((row) => row.outcome)).size;
  return (
    <div className="research-page overview-page">
      <div className="page-kicker">
        <span /> A STUDENT RESEARCH PROJECT · ORCIFY 2.0
      </div>
      <section className="research-hero">
        <div className="hero-copy">
          <div className="hero-tag">
            <Microscope size={13} /> Change-aware creative workflows
          </div>
          <h1>
            One requirement changes.
            <br />
            <em>What happens next?</em>
          </h1>
          <p>
            Creative work is connected. A new slogan can affect the copy, a
            storyboard, and a final export. Rebuilding everything wastes work.
            Reusing the wrong version risks a mistake.
          </p>
          <p className="hero-question">
            Orcify explores how a dependency graph can help us decide what to
            keep, review, or recompute.
          </p>
          <div className="hero-actions">
            <a className="button button-primary" href="#explorer">
              Try the interactive demo <ArrowRight size={15} />
            </a>
            <a className="button button-secondary" href="#results">
              Explore the evidence
            </a>
          </div>
          <span className="hero-footnote">
            Deterministic fixtures. No paid AI. No automatic approval.
          </span>
        </div>
        <div
          className="hero-diagram"
          aria-label="Illustration: a changed slogan affects copy and storyboard, while uncertain visuals need review"
        >
          <div className="diagram-grid" />
          <div className="diagram-label">A SMALL ADVERTISING CAMPAIGN</div>
          <svg
            className="diagram-lines"
            viewBox="0 0 480 360"
            aria-hidden="true"
          >
            <path d="M153 114 H220 V100 H274" />
            <path d="M153 114 H205 V242 H274" strokeDasharray="5 5" />
            <path d="M348 147 V185" />
          </svg>
          <div className="diagram-card diagram-source">
            <span>REQUIREMENT · v1 → v2</span>
            <strong>Campaign slogan</strong>
            <p>“Made to move”</p>
            <div className="diagram-change">A new message</div>
          </div>
          <div className="diagram-card diagram-copy">
            <span>HARD DEPENDENCY</span>
            <strong>Campaign copy</strong>
            <div className="mini-action recompute">↻ RECOMPUTE</div>
          </div>
          <div className="diagram-card diagram-story">
            <span>HARD DEPENDENCY</span>
            <strong>Storyboard</strong>
            <div className="mini-action recompute">↻ RECOMPUTE</div>
          </div>
          <div className="diagram-card diagram-review">
            <span>SOFT · IMPACT UNKNOWN</span>
            <strong>Social export</strong>
            <div className="mini-action review">? REVIEW</div>
          </div>
          <div className="diagram-note">
            <ShieldCheck size={13} /> Human approval stays a separate gate.
          </div>
        </div>
      </section>

      <div className="section-heading">
        <div>
          <div className="page-kicker">THE CORE IDEA</div>
          <h2>Follow the change, not a guess.</h2>
        </div>
        <p>
          GAMO-CA uses typed links, input versions, and explicit review holds.
        </p>
      </div>
      <div className="principle-grid">
        <article className="principle-card">
          <div className="principle-icon purple">
            <GitBranch size={21} />
          </div>
          <span className="step-number">01</span>
          <h3>Map the dependencies</h3>
          <p>
            Record which asset uses which input. Distinguish mandatory links
            from conditional influence and background context.
          </p>
        </article>
        <article className="principle-card">
          <div className="principle-icon amber">
            <Braces size={21} />
          </div>
          <span className="step-number">02</span>
          <h3>Plan the affected work</h3>
          <p>
            Recompute clear impacts. Keep results when reuse is justified. Ask
            for review when the information is incomplete.
          </p>
        </article>
        <article className="principle-card">
          <div className="principle-icon teal">
            <ShieldCheck size={21} />
          </div>
          <span className="step-number">03</span>
          <h3>Respect human authority</h3>
          <p>
            Approval belongs to an exact asset version and requirement snapshot.
            A KEEP decision never grants permission to publish.
          </p>
        </article>
      </div>

      <div className="section-heading">
        <div>
          <div className="page-kicker">WHAT WE ACTUALLY OBSERVED</div>
          <h2>A useful result includes the limits.</h2>
        </div>
        <a href="#results" className="text-link">
          See all results <ArrowRight size={14} />
        </a>
      </div>
      <div className="finding-grid">
        <article className="finding-card">
          <span className="finding-index">R1.1 / INITIAL PLANS</span>
          <div className="finding-number">
            {gamo.recomputes}
            <span>vs {dag.recomputes}</span>
          </div>
          <h3>Immediate recomputations</h3>
          <p>
            GAMO-CA vs conventional DAG across five synthetic cases. Eight asset
            operations were deferred behind review, not demonstrated savings.
          </p>
        </article>
        <article className="finding-card">
          <span className="finding-index">R1.3 / COMPLETE PLANNING</span>
          <div className="finding-number">
            {combinations}
            <span>synthetic outcomes</span>
          </div>
          <h3>Field-aware DAG matched</h3>
          <p>
            Using the same field information, a simple DAG matched GAMO-CA’s
            final actions and recomputation counts in every tested outcome.
          </p>
        </article>
        <article className="finding-card finding-pending">
          <span className="finding-index">R1.4 / HUMAN VALIDATION</span>
          <div className="pending-symbol">
            <Microscope size={27} />
          </div>
          <h3>Independent review is pending</h3>
          <p>
            The blinded worksheet and importer are ready. Real reviewer
            responses have not been collected; independent accuracy is unknown.
          </p>
        </article>
      </div>
      <section className="research-boundary">
        <div className="boundary-icon">
          <Microscope size={22} />
        </div>
        <div>
          <h3>A small, reproducible research prototype</h3>
          <p>
            Five authored synthetic workflows, one fixed seed, and no real
            generation or human-time measurements. Planning overhead was higher
            for the current GAMO-CA implementation, with unequal validation work
            across methods. These findings establish neither superiority,
            statistical significance, nor scientific novelty.
          </p>
        </div>
      </section>
    </div>
  );
}
