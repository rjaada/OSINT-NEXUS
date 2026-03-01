"use client"

import { useEffect, useState } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"

interface OpsDashboard {
  status: string
  uptime_seconds: number
  watchdog_warnings: string[]
  queues: Record<string, number>
  metrics: Record<string, unknown>
  postgres: { configured: boolean; connected: boolean; events_count: number | null; error?: string | null }
  generated_at: string
}

interface OpsAlerts {
  alerts: Array<{ rule: string; severity: "critical" | "warning"; message: string }>
  total: number
  critical: number
  warning: number
}

export default function V2HealthPage() {
  const [data, setData] = useState<OpsDashboard | null>(null)
  const [alerts, setAlerts] = useState<OpsAlerts | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const [r1, r2] = await Promise.all([
          fetch("http://localhost:8000/api/v2/ops/dashboard", { cache: "no-store" }),
          fetch("http://localhost:8000/api/v2/ops/alerts", { cache: "no-store" }),
        ])
        if (r1.ok) setData(await r1.json())
        if (r2.ok) setAlerts(await r2.json())
      } catch (_) {}
    }
    load()
    const i = setInterval(load, 5000)
    return () => clearInterval(i)
  }, [])

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar />
      <CommandNav />
      <main className="px-4 md:px-6 py-5">
        <div className="max-w-7xl mx-auto">
          <header className="mb-5">
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-purple mb-1">Ops Control v2</p>
            <h1 className="text-2xl md:text-3xl font-semibold">Reliability and Health Dashboard</h1>
            <p className="text-xs text-muted-foreground mt-2">Live operational status for ingestion, queues, watchdog, and PostgreSQL connectivity.</p>
          </header>

          <section className="grid md:grid-cols-4 gap-3 mb-4">
            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-green mb-2">System</p>
              <p className={data?.status === "nominal" ? "text-osint-green text-sm" : "text-osint-red text-sm"}>{data?.status || "--"}</p>
              <p className="text-[11px] text-muted-foreground mt-1">Uptime: {data ? Math.floor(data.uptime_seconds / 60) : 0}m</p>
            </article>
            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-blue mb-2">Watchdog</p>
              <p className="text-sm text-[#d0d0df]">{(data?.watchdog_warnings || []).length}</p>
              <p className="text-[11px] text-muted-foreground mt-1">warnings</p>
            </article>
            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-amber mb-2">Postgres</p>
              <p className={(data?.postgres?.connected ? "text-osint-green" : "text-osint-red") + " text-sm"}>{data?.postgres?.connected ? "connected" : "offline"}</p>
              <p className="text-[11px] text-muted-foreground mt-1">events_v2: {data?.postgres?.events_count ?? "--"}</p>
            </article>
            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-purple mb-2">Generated</p>
              <p className="text-[11px] text-[#d0d0df]">{data?.generated_at || "--"}</p>
            </article>
          </section>

          <section className="grid md:grid-cols-3 gap-3 mb-4">
            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-amber mb-2">Rule Alerts</p>
              <p className="text-sm text-[#d0d0df]">{alerts?.total ?? 0}</p>
            </article>
            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-red mb-2">Critical</p>
              <p className="text-sm text-osint-red">{alerts?.critical ?? 0}</p>
            </article>
            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-amber mb-2">Warning</p>
              <p className="text-sm text-osint-amber">{alerts?.warning ?? 0}</p>
            </article>
          </section>

          <section className="grid md:grid-cols-2 gap-3 mb-4">
            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-blue mb-2">Queues</p>
              <div className="grid gap-2">
                {Object.entries(data?.queues || {}).map(([k, v]) => (
                  <div key={k} className="rounded border border-white/10 px-2 py-1 text-[11px] flex justify-between">
                    <span className="text-muted-foreground">{k}</span>
                    <span className="text-[#d0d0df]">{v}</span>
                  </div>
                ))}
              </div>
            </article>
            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-amber mb-2">Watchdog Warnings</p>
              <div className="text-[11px] text-muted-foreground space-y-1">
                {(data?.watchdog_warnings || []).length === 0 ? <p>No warnings.</p> : data?.watchdog_warnings.map((w) => <p key={w}>• {w}</p>)}
                {data?.postgres?.error ? <p className="text-osint-red mt-2">Postgres: {data.postgres.error}</p> : null}
              </div>
            </article>
          </section>

          <section className="rounded-lg border border-white/10 bg-black/30 p-3 mb-4">
            <p className="text-[10px] uppercase tracking-[0.14em] text-osint-red mb-2">Alert Rules Triggered</p>
            <div className="text-[11px] space-y-1">
              {(alerts?.alerts || []).length === 0 ? <p className="text-muted-foreground">No active rule alerts.</p> : (alerts?.alerts || []).map((a, i) => (
                <p key={`${a.rule}-${i}`} className={a.severity === "critical" ? "text-osint-red" : "text-osint-amber"}>
                  • [{a.severity}] {a.rule}: {a.message}
                </p>
              ))}
            </div>
          </section>

          <section className="rounded-lg border border-white/10 bg-black/30 p-3">
            <p className="text-[10px] uppercase tracking-[0.14em] text-osint-green mb-2">Raw Metrics</p>
            <pre className="text-[11px] text-[#bfc3d4] overflow-x-auto">{JSON.stringify(data?.metrics || {}, null, 2)}</pre>
          </section>
        </div>
      </main>
    </div>
  )
}
