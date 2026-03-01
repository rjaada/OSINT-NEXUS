import { BottomBar } from "@/components/dashboard/bottom-bar"
import { TopBar } from "@/components/dashboard/top-bar"
import { Dashboard } from "@/components/dashboard/intel-feed-v2"
import { LiveStreams } from "@/components/dashboard/live-streams"
import { CommandNav } from "@/components/dashboard/command-nav"

export default function ArabicOperationsPage() {
  return (
    <div dir="rtl" className="flex flex-col h-screen w-screen overflow-hidden bg-background">
      <TopBar />
      <CommandNav />

      <div className="flex flex-1 min-h-0">
        <main className="flex flex-1 min-w-0 relative">
          <Dashboard />
          <LiveStreams />
        </main>
      </div>

      <BottomBar />
    </div>
  )
}
