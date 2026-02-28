import { LeftSidebar } from "@/components/dashboard/left-sidebar"
import { BottomBar } from "@/components/dashboard/bottom-bar"
import { TopBar } from "@/components/dashboard/top-bar"
import { Dashboard } from "@/components/dashboard/intel-feed"
import { LiveStreams } from "@/components/dashboard/live-streams"
import { AiAnalyst } from "@/components/dashboard/ai-analyst"

export default function DashboardPage() {
  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-background">
      <TopBar />

      <div className="flex flex-1 min-h-0">
        <LeftSidebar />

        <main className="flex flex-1 min-w-0 relative">
          <Dashboard />

          {/* Floating live stream panel */}
          <LiveStreams />
        </main>
      </div>

      <BottomBar />
    </div>
  )
}
