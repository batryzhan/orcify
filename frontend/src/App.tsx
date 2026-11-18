import { PrivacyBadge } from "./components/PrivacyBadge";
import { WorkspaceView } from "./components/WorkspaceView";

export default function App() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="border-b border-paper-line bg-paper-card/70">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <div className="flex items-baseline gap-3">
            <span className="text-xl font-bold tracking-tight">Orcify</span>
            <span className="hidden text-sm text-ink-mute sm:inline">локальная оркестрация бизнес-процессов</span>
          </div>
          <PrivacyBadge />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        <WorkspaceView />
      </main>
    </div>
  );
}
