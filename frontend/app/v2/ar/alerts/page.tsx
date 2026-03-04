"use client"

import { useEffect, useState } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"
import { VideoModal } from "@/components/system/video-modal"

type Confidence = "LOW" | "MEDIUM" | "HIGH"

interface MediaCred {
  claim_alignment?: string
  credibility_note?: string
  transcript_text?: string
  transcript_language?: string
  transcript_error?: string
  deepfake_score?: string
  deepfake_label?: string
  deepfake_error?: string
}

interface AlertAssessment {
  id: string
  incident_id?: string
  type: "STRIKE" | "CRITICAL" | "CLASH"
  desc: string
  timestamp: string
  lat: number
  lng: number
  source: string
  confidence: Confidence
  confidence_score: number
  confidence_reason?: string
  eta_band: string
  age_minutes: number
  corroborating_sources: string[]
  observed_facts?: string[]
  model_inference?: string[]
  insufficient_evidence?: boolean
  video_url?: string
  video_assessment?: string
  video_confidence?: string
  media?: MediaCred
  review?: { status?: string; analyst?: string; note?: string }
}

const CONF_STYLE: Record<Confidence, { text: string; bg: string; border: string }> = {
  LOW: { text: "#ffa630", bg: "#ffa63020", border: "#ffa63040" },
  MEDIUM: { text: "#00b4d8", bg: "#00b4d820", border: "#00b4d840" },
  HIGH: { text: "#00ff88", bg: "#00ff8820", border: "#00ff8840" },
}

function isPlayableVideoUrl(url?: string | null): boolean {
  if (!url) return false
  if (url.startsWith("/media/telegram/")) return true
  return /\.(mp4|webm|mov|m4v)(\?|$)/i.test(url)
}

export default function ArabicAlertsPage() {
  const [alerts, setAlerts] = useState<AlertAssessment[]>([])
  const [loading, setLoading] = useState(true)
  const [lastSync, setLastSync] = useState("")
  const [activeVideo, setActiveVideo] = useState<{ eventId: string; videoUrl: string; title: string } | null>(null)

  const load = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/v2/alerts?limit=60")
      if (!res.ok) return
      setAlerts(await res.json())
      setLastSync(new Date().toISOString().slice(11, 19) + "Z")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div dir="rtl" className="min-h-screen bg-background text-foreground">
      <TopBar />
      <CommandNav />

      <main className="px-4 md:px-6 py-5">
        <div className="max-w-7xl mx-auto">
          <header className="mb-5 flex items-end justify-between gap-3 flex-wrap">
            <div>
              <p className="text-[10px] tracking-[0.18em] uppercase text-osint-amber mb-1">تنبيهات v2</p>
              <h1 className="text-2xl md:text-3xl font-semibold">لوحة الثقة والتحقق والتقدير الزمني</h1>
              <p className="text-xs text-muted-foreground mt-2">
                إرشادي فقط. لا تعتمد على تقدير الوقت كتحذير رسمي؛ اتبع قنوات الدفاع المدني الرسمية.
              </p>
            </div>
            <div className="text-[11px] text-muted-foreground">
              {loading ? "جاري التحديث..." : `آخر مزامنة: ${lastSync || "--:--:--Z"}`}
            </div>
          </header>

          <section className="grid gap-3">
            {alerts.map((a) => {
              const c = CONF_STYLE[a.confidence]
              const videoHref = a.video_url ? (a.video_url.startsWith("/media/") ? `http://localhost:8000${a.video_url}` : a.video_url) : null
              const canInlineVideo = isPlayableVideoUrl(a.video_url)
              return (
                <article
                  key={a.id}
                  className="rounded-xl p-4"
                  style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
                >
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <span className="text-[9px] px-2 py-0.5 rounded border border-white/10 tracking-[0.14em] uppercase">{a.type}</span>
                    <span className="text-[9px] px-2 py-0.5 rounded border border-white/10 tracking-[0.14em] uppercase text-muted-foreground">{a.source}</span>
                    <span className="text-[9px] px-2 py-0.5 rounded tracking-[0.14em] uppercase" style={{ color: c.text, background: c.bg, border: `1px solid ${c.border}` }}>
                      الثقة {a.confidence} ({a.confidence_score})
                    </span>
                    <span className="text-[9px] px-2 py-0.5 rounded tracking-[0.14em] uppercase border border-osint-red/30 text-osint-red">ETA {a.eta_band}</span>
                    {a.insufficient_evidence ? (
                      <span className="text-[9px] px-2 py-0.5 rounded tracking-[0.14em] uppercase border border-osint-amber/40 text-osint-amber">أدلة محدودة</span>
                    ) : null}
                    <span className="ml-auto text-[10px] text-muted-foreground">منذ {a.age_minutes} دقيقة</span>
                  </div>

                  <p className="text-sm text-[#c9c9db] leading-relaxed mb-2">{a.desc.replace(/^\[.+?\]\s*/, "")}</p>
                  <p className="text-[11px] text-osint-blue mb-3">سبب مستوى الثقة: {a.confidence_reason || "بيانات غير كافية"}</p>

                  <div className="grid md:grid-cols-3 gap-3 text-[11px] mb-3">
                    <div className="rounded-md border border-white/10 p-2 bg-black/20">
                      <p className="text-[10px] uppercase tracking-[0.12em] text-osint-green mb-1">حقائق مرصودة</p>
                      {(a.observed_facts && a.observed_facts.length > 0)
                        ? <ul className="text-[#b7d7c1] list-disc pr-4 space-y-1">{a.observed_facts.slice(0, 3).map((x, i) => <li key={i}>{x}</li>)}</ul>
                        : <p className="text-muted-foreground">لا توجد حقائق مباشرة.</p>}
                    </div>
                    <div className="rounded-md border border-white/10 p-2 bg-black/20">
                      <p className="text-[10px] uppercase tracking-[0.12em] text-osint-amber mb-1">استدلال النموذج</p>
                      {(a.model_inference && a.model_inference.length > 0)
                        ? <ul className="text-[#d7c6a8] list-disc pr-4 space-y-1">{a.model_inference.slice(0, 3).map((x, i) => <li key={i}>{x}</li>)}</ul>
                        : <p className="text-muted-foreground">لا يوجد استدلال مرفق.</p>}
                    </div>
                    <div className="rounded-md border border-white/10 p-2 bg-black/20">
                      <p className="text-[10px] uppercase tracking-[0.12em] text-osint-purple mb-1">مصداقية الوسائط</p>
                      <p className="text-[#c7b9dd] line-clamp-3">{a.media?.credibility_note || "بانتظار تحليل الوسائط"}</p>
                      {a.media?.deepfake_label || a.media?.deepfake_score ? (
                        <p className="text-[10px] text-osint-amber mt-2">
                          Deepfake: {a.media?.deepfake_label || "unknown"} {a.media?.deepfake_score ? `(${a.media.deepfake_score})` : ""}
                        </p>
                      ) : null}
                      {a.media?.deepfake_error ? (
                        <p className="text-[10px] text-osint-red mt-1">خطأ فحص Deepfake: {a.media.deepfake_error}</p>
                      ) : null}
                      {a.media?.transcript_text ? (
                        <p className="text-[10px] text-[#a6d2c9] mt-2 line-clamp-3">
                          تفريغ صوتي{a.media?.transcript_language ? ` (${a.media.transcript_language})` : ""}: {a.media.transcript_text}
                        </p>
                      ) : null}
                      {a.media?.transcript_error ? (
                        <p className="text-[10px] text-osint-red mt-1">خطأ التفريغ الصوتي: {a.media.transcript_error}</p>
                      ) : null}
                    </div>
                  </div>

                  <div className="flex items-center gap-4 text-[11px] text-muted-foreground flex-wrap">
                    <span>{Number(a.lat).toFixed(3)}N {Number(a.lng).toFixed(3)}E</span>
                    <span>{a.timestamp}</span>
                    <span>تحقق متقاطع: {a.corroborating_sources.length > 0 ? a.corroborating_sources.join(", ") : "مصدر واحد"}</span>
                    {a.video_assessment ? <span>الفيديو: {a.video_assessment} ({a.video_confidence || "LOW"})</span> : null}
                    {videoHref && canInlineVideo ? (
                      <button
                        onClick={() => setActiveVideo({ eventId: a.id, videoUrl: a.video_url || "", title: a.desc.replace(/^\[.+?\]\s*/, "") })}
                        className="text-osint-green underline underline-offset-2"
                      >
                        أحدث فيديو
                      </button>
                    ) : null}
                  </div>
                </article>
              )
            })}
          </section>
        </div>
      </main>

      <VideoModal
        open={Boolean(activeVideo)}
        eventId={activeVideo?.eventId}
        videoUrl={activeVideo?.videoUrl}
        title={activeVideo?.title}
        onClose={() => setActiveVideo(null)}
        onConsumed={() => load()}
      />
    </div>
  )
}
