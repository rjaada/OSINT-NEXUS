"use client"

import { useEffect, useMemo, useState } from "react"
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

interface SourceOps {
  per_source: Record<string, {
    lag_seconds: number | null
    throughput_per_min: number
    events_window: number
    degraded: boolean
    last_success: string | null
  }>
}

interface SourceResponse {
  items: SourceItem[]
  counts_by_source: Record<string, number>
  reliability_profile: Record<string, number>
  ops: SourceOps
  degraded_sources: string[]
}

interface EvalScorecard {
  reviewed_total: number
  confirmed: number
  false_positive_rate_pct: number
  geo_accuracy_proxy_pct: number
}

interface SystemInfo {
  storage_backend: string
  ollama_model_primary: string
  ollama_model_fallback: string
  queue: { media_jobs_pending: number; media_jobs_tracked: number }
}

export default function ArabicSourcesPage() {
  const [data, setData] = useState<SourceResponse | null>(null)
  const [scorecard, setScorecard] = useState<EvalScorecard | null>(null)
  const [system, setSystem] = useState<SystemInfo | null>(null)

  const sourceVolumes = useMemo(() => {
    const counts = data?.counts_by_source ?? {}
    return Object.entries(counts).sort((a, b) => Number(b[1]) - Number(a[1]))
  }, [data])

  useEffect(() => {
    const load = async () => {
      try {
        const [r1, r2, r3] = await Promise.all([
          fetch("http://localhost:8000/api/v2/sources?limit=220"),
          fetch("http://localhost:8000/api/v2/evaluation/scorecard"),
          fetch("http://localhost:8000/api/v2/system"),
        ])
        if (r1.ok) setData(await r1.json())
        if (r2.ok) setScorecard(await r2.json())
        if (r3.ok) setSystem(await r3.json())
      } catch (_) {}
    }
    load()
    const i = setInterval(load, 10000)
    return () => clearInterval(i)
  }, [])

  return (
    <div dir="rtl" className="min-h-screen bg-background text-foreground">
      <TopBar />
      <CommandNav />

      <main className="px-4 md:px-6 py-5">
        <div className="max-w-7xl mx-auto">
          <header className="mb-5">
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-blue mb-1">مكتب المصادر v2</p>
            <h1 className="text-2xl md:text-3xl font-semibold">المصادر والموثوقية وصحة خطوط المعالجة</h1>
            <p className="text-xs text-muted-foreground mt-2">
              الحقائق = بيانات مرصودة من المصدر. الاستدلال = تفسير النموذج وقد يكون خاطئاً.
            </p>
          </header>

          <section className="grid md:grid-cols-4 gap-3 mb-4">
            <article className="rounded-lg p-3 border border-white/10 bg-black/30 md:col-span-2">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-green mb-2">أحجام المصادر</p>
              <div className="flex flex-wrap gap-2 text-[11px]">
                {sourceVolumes.slice(0, 14).map(([k, v]) => (
                  <span key={k} className="px-2 py-1 rounded border border-white/10 text-[#c5c5d5]">
                    {k}: {v}
                  </span>
                ))}
              </div>
            </article>

            <article className="rounded-lg p-3 border border-white/10 bg-black/30">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-amber mb-2">مصادر متدهورة</p>
              <div className="text-[11px] text-muted-foreground space-y-1">
                {(data?.degraded_sources ?? []).length === 0
                  ? <p>لا توجد.</p>
                  : (data?.degraded_sources ?? []).map((x) => <p key={x}>• {x}</p>)}
              </div>
            </article>

            <article className="rounded-lg p-3 border border-white/10 bg-black/30">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-purple mb-2">النموذج والطابور</p>
              <div className="text-[11px] text-muted-foreground space-y-1">
                <p>التخزين: {system?.storage_backend ?? "--"}</p>
                <p>النموذج الأساسي: {system?.ollama_model_primary ?? "--"}</p>
                <p>النموذج الاحتياطي: {system?.ollama_model_fallback ?? "--"}</p>
                <p>طابور الوسائط: {system?.queue.media_jobs_pending ?? 0}</p>
              </div>
            </article>
          </section>

          <section className="grid md:grid-cols-2 gap-3 mb-4">
            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-amber mb-2">أوزان الموثوقية</p>
              <div className="grid sm:grid-cols-2 gap-2 text-[11px]">
                {Object.entries(data?.reliability_profile ?? {}).sort((a, b) => b[1] - a[1]).map(([name, weight]) => (
                  <div key={name} className="rounded border border-white/10 px-2 py-1 flex justify-between">
                    <span className="text-[#d0d0df]">{name}</span>
                    <span className="text-osint-blue">{weight}</span>
                  </div>
                ))}
              </div>
            </article>

            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-green mb-2">بطاقة جودة أسبوعية</p>
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="rounded border border-white/10 p-2"><p className="text-muted-foreground">مراجَع</p><p className="text-[#d0d0df]">{scorecard?.reviewed_total ?? 0}</p></div>
                <div className="rounded border border-white/10 p-2"><p className="text-muted-foreground">مؤكد</p><p className="text-[#d0d0df]">{scorecard?.confirmed ?? 0}</p></div>
                <div className="rounded border border-white/10 p-2"><p className="text-muted-foreground">إيجابي كاذب</p><p className="text-[#d0d0df]">{scorecard?.false_positive_rate_pct ?? 0}%</p></div>
                <div className="rounded border border-white/10 p-2"><p className="text-muted-foreground">دقة جغرافية تقريبية</p><p className="text-[#d0d0df]">{scorecard?.geo_accuracy_proxy_pct ?? 0}%</p></div>
              </div>
            </article>
          </section>

          <section className="rounded-lg border border-white/10 bg-black/30 p-3 mb-4">
            <p className="text-[10px] uppercase tracking-[0.14em] text-osint-blue mb-3">تشغيل كل مصدر</p>
            <div className="grid gap-2">
              {Object.entries(data?.ops?.per_source ?? {}).sort((a, b) => (b[1].events_window - a[1].events_window)).map(([name, op]) => (
                <article key={name} className="rounded-md border border-white/10 p-2 text-[11px] grid md:grid-cols-5 gap-2">
                  <p className="text-[#d0d0df]">{name}</p>
                  <p className="text-muted-foreground">التأخر: {op.lag_seconds ?? "--"}ث</p>
                  <p className="text-muted-foreground">المعدل: {op.throughput_per_min}/د</p>
                  <p className="text-muted-foreground">النافذة: {op.events_window}</p>
                  <p className={op.degraded ? "text-osint-red" : "text-osint-green"}>{op.degraded ? "متدهور" : "جيد"}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="rounded-lg border border-white/10 bg-black/30 p-3">
            <p className="text-[10px] uppercase tracking-[0.14em] text-osint-blue mb-3">التدفق الخام (الأحدث)</p>
            <div className="grid gap-2">
              {(data?.items ?? []).slice(0, 80).map((item) => (
                <article key={item.id} className="rounded-md border border-white/10 p-2 text-[12px]">
                  <div className="flex flex-wrap gap-2 mb-1 text-[10px]">
                    <span className="px-1.5 py-0.5 border border-white/10 rounded">{item.type}</span>
                    <span className="px-1.5 py-0.5 border border-white/10 rounded text-muted-foreground">{item.source}</span>
                    <span className="ml-auto text-muted-foreground">{item.timestamp}</span>
                  </div>
                  <p className="text-[#d0d0df]">{item.desc.replace(/^\[.+?\]\s*/, "")}</p>
                  <div className="grid md:grid-cols-2 gap-2 mt-1 text-[10px]">
                    <p className="text-muted-foreground">{Number(item.lat).toFixed(3)}N {Number(item.lng).toFixed(3)}E</p>
                    <p className="text-muted-foreground text-left">{item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer" className="underline text-osint-blue">المصدر</a> : ""}</p>
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
