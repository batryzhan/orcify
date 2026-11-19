import { AutomationsView } from "./components/AutomationsView";
import { BoardView } from "./components/board/BoardView";
import { Sidebar } from "./components/layout/Sidebar";
import { PrivacyBadge } from "./components/PrivacyBadge";
import { FinanceWindow } from "./components/windows/FinanceWindow";
import { LegalWindow } from "./components/windows/LegalWindow";
import { PostsWindow } from "./components/windows/PostsWindow";
import { useHashRoute } from "./hooks/useHashRoute";
import { useTaskRunner } from "./hooks/useTaskRunner";

export default function App() {
  const [route, navigate] = useHashRoute();
  // Әр терезенің өз раннері бар: терезелер арасында ауысқанда тапсырмалар жалғаса береді.
  const planner = useTaskRunner();
  const posts = useTaskRunner();
  const finance = useTaskRunner();
  const legal = useTaskRunner();
  const running = { board: planner.running, posts: posts.running, finance: finance.running, legal: legal.running, automations: false };

  return (
    <div className="min-h-screen bg-white text-ink md:flex">
      <Sidebar view={route.view} onNavigate={(v) => navigate(v)} running={running} />
      <div className="min-w-0 flex-1">
        <header className="flex items-center justify-end gap-3 border-b border-paper-line px-4 py-2.5 sm:px-8">
          <PrivacyBadge />
        </header>
        <main>
          {route.view === "board" && <BoardView runner={planner} onNavigate={navigate} />}
          {route.view === "posts" && (
            <PostsWindow runner={posts} openPostId={route.params.get("post")} onClosePost={() => navigate("posts")} />
          )}
          {route.view === "finance" && <FinanceWindow runner={finance} highlightReport={route.params.get("report")} />}
          {route.view === "legal" && <LegalWindow runner={legal} />}
          {route.view === "automations" && <AutomationsView />}
        </main>
      </div>
    </div>
  );
}
