"use client"

import { useEffect, useState } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"
import { useAuth } from "@/lib/auth-context"
import { API_BASE } from "@/lib/api"
import { csrfHeaders } from "@/lib/security"

type Evidence = { id: string; event_id: string; text: string; timestamp: string; source: string; publisher: string | null; url: string | null }
type Finding = { text: string; kind?: string; evidence_ids: string[] }
type Saved = { id: string; question: string; created_at: string }
type Report = { id: string; question: string; status: string; generated_at: string; window_start: string; window_end: string; findings: Finding[]; contradictions: Finding[]; unknowns: string[]; next_questions: string[]; evidence: Evidence[]; retrieval: { scope: string; candidate_count: number; candidate_limit: number } }

async function api(path: string, init?: RequestInit) {
  const response = await fetch(`${API_BASE}/api/v2/investigations${path}`, { ...init, credentials: "include" })
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(typeof data?.detail === "string" ? data.detail : `Request failed (${response.status}). Please retry.`)
  return data
}

export default function InvestigationsPage() {
  const { role, loading } = useAuth()
  const allowed = role === "admin" || role === "analyst"
  const [question, setQuestion] = useState("")
  const [days, setDays] = useState(7)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [history, setHistory] = useState<Saved[]>([])
  const [report, setReport] = useState<Report | null>(null)
  useEffect(() => {
    if (allowed) api("").then(setHistory).catch(e => setError(e.message))
  }, [allowed])

  async function run() {
    if (busy) return
    setBusy(true); setError("")
    try {
      const result = await api("", { method: "POST", headers: { "Content-Type": "application/json", ...csrfHeaders() }, body: JSON.stringify({ question: question.trim(), days }) })
      setReport(result)
      setHistory(current => [{ id: result.id, question: result.question, created_at: result.generated_at }, ...current].slice(0, 50))
    } catch (e) { setError(e instanceof Error ? e.message : "Investigation failed") }
    finally { setBusy(false) }
  }
  async function open(id: string) {
    setBusy(true); setError("")
    try { setReport(await api(`/${id}`)) }
    catch (e) { setError(e instanceof Error ? e.message : "Could not open investigation") }
    finally { setBusy(false) }
  }
  function exportReport() {
    if (!report) return
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }))
    const link = document.createElement("a"); link.href = url; link.download = `investigation-${report.id}.json`; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  const cite = (finding: Finding) => <div className="mt-3 flex gap-2 flex-wrap">{finding.evidence_ids.map(id => <a key={id} href={`#evidence-${id}`} className="text-cyan-300 underline underline-offset-4">[{id}]</a>)}</div>

  return <div className="min-h-screen bg-[#080b12] text-slate-200"><TopBar /><CommandNav />
    <main className="mx-auto max-w-7xl p-5 md:p-8">
      <p className="text-xs uppercase tracking-[0.24em] text-cyan-400">Evidence workspace</p>
      <h1 className="mt-2 text-3xl font-semibold">Investigate a question</h1>
      <p className="mt-3 max-w-3xl text-sm text-slate-400">Trace what sources reported, inspect conflicting accounts, and identify what is still unknown. Each saved investigation preserves the evidence used at the time.</p>
      {loading ? <p className="mt-8">Checking access…</p> : !allowed ? <p className="mt-8">An analyst or admin account is required.</p> : <>
        <form className="my-7 rounded-xl border border-slate-700 bg-slate-900/60 p-5" onSubmit={e => { e.preventDefault(); void run() }}>
          <label htmlFor="question" className="block mb-2 text-sm">Research question — include a place, actor, or specific event</label>
          <textarea id="question" required minLength={8} maxLength={600} value={question} onChange={e => setQuestion(e.target.value)} placeholder="What changed around Beirut, and what do the sources actually support?" className="w-full rounded-lg bg-slate-950 border border-slate-600 p-3 min-h-24" />
          <div className="mt-3 flex flex-wrap items-center gap-4"><label className="text-sm">Look back <select value={days} onChange={e => setDays(Number(e.target.value))} className="ml-2 rounded bg-slate-800 p-2">{[1, 3, 7, 14, 30].map(d => <option key={d} value={d}>{d} day{d > 1 ? "s" : ""}</option>)}</select></label>
            <button disabled={busy || question.trim().length < 8} className="rounded-lg bg-cyan-300 px-5 py-2 font-medium text-slate-950 disabled:opacity-40">{busy ? "Working…" : "Investigate"}</button>
            <span className="text-xs text-slate-400">Groq primary · local Ollama fallback · may take a few minutes</span></div>
        </form>
        {error && <p role="alert" className="mb-5 rounded border border-red-400/40 p-4 text-red-300">{error}</p>}
        <div className="grid gap-7 lg:grid-cols-[230px_1fr]">
          <aside><h2 className="font-semibold mb-3">Your saved investigations</h2>{!history.length && <p className="text-sm text-slate-500">Your first investigation will appear here.</p>}
            <div className="space-y-2">{history.map(item => <button key={item.id} disabled={busy} onClick={() => void open(item.id)} className={`block w-full rounded border p-3 text-left text-sm disabled:opacity-40 ${report?.id === item.id ? "border-cyan-500 bg-cyan-950/30" : "border-slate-800"}`}><span className="block">{item.question}</span><span className="mt-2 block text-xs text-slate-500">{new Date(item.created_at).toLocaleString()}</span></button>)}</div>
          </aside>
          <section aria-live="polite" aria-busy={busy}>{report ? <>
            <div className="flex justify-between gap-4"><h2 className="text-xl font-semibold">{report.question}</h2><button onClick={exportReport} className="shrink-0 text-sm text-cyan-300">Export JSON</button></div>
            <p className="mt-2 text-xs text-slate-400">{new Date(report.window_start).toLocaleString()} → {new Date(report.window_end).toLocaleString()}</p>
            <p className="mt-3 text-sm text-slate-400">{report.retrieval.scope} Selected {report.evidence.length} evidence records from {report.retrieval.candidate_count} candidates (cap {report.retrieval.candidate_limit}).</p>
            {report.status !== "assessed" && <p className="my-4 rounded border border-amber-500/40 p-4 text-amber-200">{report.status === "no_evidence" ? "No matching stored evidence. Try another location, actor, or time window." : "The model did not produce a usable cited assessment. Retrieved evidence is preserved below."}</p>}
            <h3 className="mt-7 mb-3 font-semibold">Assessment</h3>
            <div className="space-y-3">{report.findings.map((f, i) => <article key={i} className="rounded-lg border border-slate-700 p-4"><span className="text-xs uppercase tracking-wider text-cyan-300">{f.kind === "reported" ? "Source-reported · not independently verified" : "Model inference · requires review"}</span><p className="mt-2 text-sm leading-relaxed">{f.text}</p>{cite(f)}</article>)}</div>
            <h3 className="mt-7 mb-3 font-semibold">Potential contradictions</h3>
            {report.contradictions.length ? report.contradictions.map((f, i) => <article key={i} className="mb-3 rounded-lg border border-amber-500/30 p-4 text-sm"><p>{f.text}</p>{cite(f)}</article>) : <p className="text-sm text-slate-400">No cited contradiction was returned. This does not establish agreement.</p>}
            <h3 className="mt-7 mb-3 font-semibold">Unknowns & limits</h3><ul className="list-disc pl-5 space-y-2 text-sm text-slate-400">{report.unknowns.map((s, i) => <li key={i}>{s}</li>)}</ul>
            {!!report.next_questions.length && <><h3 className="mt-7 mb-3 font-semibold">Questions to pursue</h3><div className="flex flex-col items-start gap-3">{report.next_questions.map((q, i) => <button key={i} disabled={busy} onClick={() => { setQuestion(q.slice(0, 600)); document.getElementById("question")?.focus() }} className="text-left text-sm text-cyan-300 underline">{q}</button>)}</div></>}
            <h3 className="mt-8 mb-3 font-semibold">Evidence timeline</h3><p className="mb-4 text-xs text-slate-400">Stored source excerpts, not verified facts. Shared publishers may repeat the same upstream claim.</p>
            <div className="space-y-3">{[...report.evidence].sort((a, b) => a.timestamp.localeCompare(b.timestamp)).map(e => <article key={e.id} id={`evidence-${e.id}`} className="scroll-mt-6 rounded-lg border border-slate-700 p-4 target:border-cyan-400"><div className="flex flex-wrap gap-3 text-xs text-slate-400"><strong className="text-cyan-300">[{e.id}]</strong><span>{e.source}</span><time>{e.timestamp ? new Date(e.timestamp).toLocaleString() : "Time unknown"}</time></div><p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">{e.text}</p><p className="mt-3 text-xs text-slate-500">Record {e.event_id} · Publisher: {e.publisher || "unknown"}</p>{e.url && <a href={e.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-sm text-cyan-300 underline">Open original source ↗</a>}</article>)}</div>
          </> : <div className="rounded-xl border border-dashed border-slate-700 p-10 text-slate-400">Start with a specific question. The assessment, citations, and evidence timeline will appear here.</div>}</section>
        </div>
      </>}
    </main>
  </div>
}
