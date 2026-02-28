"use client"

import { useEffect, useState } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"

interface SourceItem {
  id: string
  type: string
  desc: string
  source: string
  timestamp: string
  lat: number
  lng: number
  url?: string
}

interface SourceResponse {
  items: SourceItem[]
  counts_by_source: Record<string, number>
  generated_at: string
}

interface OpsHealth {
  status: string
  warnings: string[]
  queues: Record<string, number>
  metrics: Record<string, unknown>
}

export default function SourcesPage() {
  const [data, setData] = useState<SourceResponse | null>(null)
  const [ops, setOps] = useState<OpsHealth | null>(null)
  const sourceOrder = ["Roaa War Studies (TG)", "AJ Mubasher (TG)", "Al Jazeera", "BBC News", "Reuters", "CBS News", "The Guardian", "Times of Israel", "Red Alert", "FR24-MIL"]
  const sourceCounts = data?.counts_by_source ?? {}
  const sourceVolumes = [
    ...sourceOrder.map((name) => [name, sourceCounts[name] ?? 0] as const),
    ...Object.entries(sourceCounts).filter(([name]) => !sourceOrder.includes(name)).sort((a, b) => Number(b[1]) - Number(a[1])),
  ]

  useEffect(() => {
    const load = async () => {
      try {
        const [r1, r2] = await Promise.all([
          fetch("http://localhost:8000/api/sources/recent?limit=180"),
          fetch("http://localhost:8000/api/ops/health"),
        ])
        if (r1.ok) setData(await r1.json())
        if (r2.ok) setOps(await r2.json())
      } catch (_) {}
    }
    load()
    const i = setInterval(load, 10000)
    return () => clearInterval(i)
  }, [])

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar />
      <CommandNav />

      <main className="px-4 md:px-6 py-5">
        <div className="max-w-7xl mx-auto">
          <header className="mb-5">
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-blue mb-1">Source Desk</p>
            <h1 className="text-2xl md:text-3xl font-semibold">Sources and Reliability Monitor</h1>
            <p className="text-xs text-muted-foreground mt-2">
              Observed feed records and operational health. Treat model-derived fields as inference, not confirmed fact.
            </p>
          </header>

          <section className="grid md:grid-cols-3 gap-3 mb-4">
            <article className="rounded-lg p-3 border border-white/10 bg-black/30 md:col-span-2">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-green mb-2">Source Volumes</p>
              <div className="flex flex-wrap gap-2 text-[11px]">
                {sourceVolumes.slice(0, 14).map(([k, v]) => (
                  <span key={k} className="px-2 py-1 rounded border border-white/10 text-[#c5c5d5]">
                    {k}: {v}
                  </span>
                ))}
              </div>
            </article>

            <article className="rounded-lg p-3 border border-white/10 bg-black/30">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-amber mb-2">Watchdog</p>
              <p className="text-[11px] text-[#c5c5d5]">Status: {ops?.status ?? "--"}</p>
              <div className="text-[11px] text-muted-foreground mt-2">
                {(ops?.warnings ?? []).length === 0 ? "No warnings" : (ops?.warnings ?? []).join(" · ")}
              </div>
            </article>
          </section>

          <section className="rounded-lg border border-white/10 bg-black/30 p-3">
            <p className="text-[10px] uppercase tracking-[0.14em] text-osint-blue mb-3">Raw Feed (Latest)</p>
            <div className="grid gap-2">
              {(data?.items ?? []).slice(0, 80).map((item) => (
                <article key={item.id} className="rounded-md border border-white/10 p-2 text-[12px]">
                  <div className="flex flex-wrap gap-2 mb-1 text-[10px]">
                    <span className="px-1.5 py-0.5 border border-white/10 rounded">{item.type}</span>
                    <span className="px-1.5 py-0.5 border border-white/10 rounded text-muted-foreground">{item.source}</span>
                    <span className="ml-auto text-muted-foreground">{item.timestamp}</span>
                  </div>
                  <p className="text-[#d0d0df]">{item.desc.replace(/^\[.+?\]\s*/, "")}</p>
                  <div className="mt-1 text-[10px] text-muted-foreground">
                    {Number(item.lat).toFixed(3)}N {Number(item.lng).toFixed(3)}E
                    {item.url ? (
                      <a href={item.url} target="_blank" rel="noopener noreferrer" className="ml-3 underline text-osint-blue">
                        source ↗
                      </a>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}
