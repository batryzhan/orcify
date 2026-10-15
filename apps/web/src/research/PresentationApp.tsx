import {
  ArrowDownToLine,
  BookOpen,
  ChevronRight,
  Command,
  FlaskConical,
  GitBranch,
  GraduationCap,
  LayoutDashboard,
} from "lucide-react";
import { Component, useEffect, useState, type ReactNode } from "react";
import overviewUrl from "../../../../docs/final-presentation/overview.md?url";
import { Demo } from "./Demo";
import { Overview } from "./Overview";
import { Results } from "./Results";
import "./presentation.css";

const pages = {
  overview: { title: "Research overview", icon: LayoutDashboard, number: "01" },
  explorer: { title: "Graph & impact", icon: GitBranch, number: "02" },
  results: { title: "Experiments & results", icon: FlaskConical, number: "03" },
};
type Page = keyof typeof pages;
function currentPage(): Page {
  const hash = window.location.hash.slice(1);
  return hash === "explorer" || hash === "results" ? hash : "overview";
}

class PresentationBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed)
      return (
        <div className="presentation-error" role="alert">
          <h1>The presentation could not load.</h1>
          <p>
            Reload the page. If it continues, run the build and fixture
            verification commands in the startup guide; no substitute results
            are shown.
          </p>
          <button
            className="button button-primary"
            onClick={() => window.location.reload()}
          >
            Reload presentation
          </button>
        </div>
      );
    return this.props.children;
  }
}

export function PresentationApp() {
  const [page, setPage] = useState<Page>(currentPage);
  useEffect(() => {
    const navigate = () => setPage(currentPage());
    window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, []);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [page]);
  return (
    <div className="research-shell">
      <a
        className="skip-to-content"
        href="#research-content"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("research-content")?.focus();
        }}
      >
        Skip to content
      </a>
      <aside className="showcase-sidebar">
        <a
          className="showcase-brand"
          href="#overview"
          aria-label="Orcify research overview"
        >
          <div className="brand-mark">
            <Command size={23} />
          </div>
          <div>
            <strong>
              orcify<span>.</span>
            </strong>
            <small>RESEARCH EDITION 2.0</small>
          </div>
        </a>
        <div className="sidebar-project">
          <span className="project-symbol">
            <GitBranch size={17} />
          </span>
          <div>
            <strong>Change-aware workflows</strong>
            <span>Student research prototype</span>
          </div>
        </div>
        <div className="showcase-nav-label">THE RESEARCH</div>
        <nav aria-label="Research navigation">
          {(Object.entries(pages) as [Page, (typeof pages)[Page]][]).map(
            ([key, item]) => (
              <a
                key={key}
                href={`#${key}`}
                className={
                  page === key
                    ? "showcase-nav-link active"
                    : "showcase-nav-link"
                }
                aria-current={page === key ? "page" : undefined}
              >
                <item.icon size={17} />
                <span>{item.title}</span>
                <ChevronRight size={13} />
              </a>
            ),
          )}
        </nav>
        <div className="sidebar-research-note">
          <span className="small-purple-line" />
          <strong>Research, made explainable.</strong>
          <p>
            A small experiment in managing creative work when requirements
            change.
          </p>
        </div>
        <div className="showcase-sidebar-bottom">
          <a
            className="presentation-download"
            href={overviewUrl}
            download="orcify-project-overview.md"
          >
            <BookOpen size={16} />
            <span>Project overview</span>
            <ArrowDownToLine size={13} />
          </a>
          <div className="school-project">
            <GraduationCap size={17} />
            <div>
              <strong>High-school scientific project</strong>
              <span>Kazakhstan · RKNP preparation</span>
            </div>
          </div>
        </div>
      </aside>
      <div className="showcase-content">
        <header className="showcase-header">
          <div>
            <span>Orcify research</span>
            <ChevronRight size={13} />
            <strong>{pages[page].title}</strong>
          </div>
          <span className="prototype-badge">
            <span /> Research prototype
          </span>
        </header>
        <main id="research-content" tabIndex={-1}>
          <PresentationBoundary>
            {page === "overview" ? (
              <Overview />
            ) : page === "explorer" ? (
              <Demo />
            ) : (
              <Results />
            )}
          </PresentationBoundary>
        </main>
        <footer className="showcase-footer">
          <span>
            Orcify 2.0 <i /> Understand the change. Respect the evidence.
          </span>
          <span>Synthetic workflows · independent validation pending</span>
        </footer>
      </div>
    </div>
  );
}
