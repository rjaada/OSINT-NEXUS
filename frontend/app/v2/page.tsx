import Link from "next/link"

export default function HomePage() {
  return (
    <main className="min-h-screen bg-background text-foreground px-6 py-8 md:px-10">
      <div className="max-w-6xl mx-auto">
        <header className="mb-8">
          <div className="flex items-center justify-end mb-3">
            <Link
              href="/"
              className="text-[10px] tracking-[0.14em] uppercase px-3 py-1.5 rounded"
              style={{ color: "#00ff88", border: "1px solid #00ff8855", background: "#00ff8818" }}
            >
              Switch to V1 Stable
            </Link>
          </div>
          <p className="text-[11px] uppercase tracking-[0.2em] text-osint-blue mb-2">OSINT NEXUS</p>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">Mission Hub</h1>
          <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
            Use dedicated workspaces for live operations, alert assessment, and source verification to reduce dashboard overload during fast-moving incidents.
          </p>
        </header>

        <section className="grid md:grid-cols-3 gap-4">
          <Link
            href="/v2/operations"
            className="rounded-xl p-6 transition-all hover:bg-white/[0.03]"
            style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
          >
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-green mb-2">Live Ops</p>
            <h2 className="text-xl font-semibold mb-2">Operations Dashboard</h2>
            <p className="text-sm text-muted-foreground">
              Real-time map, event stream, timeline, and AI analyst panel for active monitoring.
            </p>
          </Link>

          <Link
            href="/v2/alerts"
            className="rounded-xl p-6 transition-all hover:bg-white/[0.03]"
            style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
          >
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-amber mb-2">Alert Intel</p>
            <h2 className="text-xl font-semibold mb-2">Confidence and ETA</h2>
            <p className="text-sm text-muted-foreground">
              Strike-focused decision board with confidence scoring, provenance, and advisory ETA bands.
            </p>
          </Link>

          <Link
            href="/v2/sources"
            className="rounded-xl p-6 transition-all hover:bg-white/[0.03]"
            style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
          >
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-blue mb-2">Source Desk</p>
            <h2 className="text-xl font-semibold mb-2">Sources and Ops Health</h2>
            <p className="text-sm text-muted-foreground">
              Raw feed verification, source volume, queue health, and watchdog state.
            </p>
          </Link>
        </section>
      </div>
    </main>
  )
}
