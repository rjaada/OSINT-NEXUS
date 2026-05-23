"use client"

import { useEffect, useState, useCallback } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

type Status = "OPEN" | "CONFIRMED" | "REFUTED" | "SUSPENDED"

interface Hypothesis {
  id: string
  title: string
  statement: string
  status: Status
  confidence: number
  evidence_ids: string[]
  analyst_notes: string
  analyst: string
  created_at: string
  updated_at: string
  tags: string[]
}

interface RecentEvent {
  id: string
  type: string
  desc: string
  source: string
  timestamp: string
  confidence_score?: number
}

const STATUS_CONFIG: Record<Status, { label: string; color: string; border: string; bg: string }> = {
  OPEN:      { label: "OPEN",      color: "#60a5fa", border: "#60a5fa40", bg: "#60a5fa10" },
  CONFIRMED: { label: "CONFIRMED", color: "#22c55e", border: "#22c55e40", bg: "#22c55e10" },
  REFUTED:   { label: "REFUTED",   color: "#ef4444", border: "#ef444440", bg: "#ef444410" },
  SUSPENDED: { label: "SUSPENDED", color: "#94a3b8", border: "#94a3b840", bg: "#94a3b810" },
}

function confidenceColor(c: number): string {
  if (c >= 75) return "#22c55e"
  if (c >= 50) return "#ffa630"
  if (c >= 25) return "#f59e0b"
  return "#ef4444"
}

function icd203Label(c: number): string {
  if (c >= 90) return "ALMOST CERTAIN"
  if (c >= 75) return "HIGHLY LIKELY"
  if (c >= 55) return "LIKELY"
  if (c >= 40) return "ROUGHLY EVEN"
  if (c >= 25) return "UNLIKELY"
  return "HIGHLY UNLIKELY"
}

function fmtDate(iso: string): string {
  try { return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }) }
  catch { return iso }
}

export default function HypothesesPage() {
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([])
  const [recentEvents, setRecentEvents] = useState<RecentEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)

  // New hypothesis form
  const [newTitle, setNewTitle] = useState("")
  const [newStatement, setNewStatement] = useState("")
  const [newConfidence, setNewConfidence] = useState(50)

  // Edit state for selected hypothesis
  const [editNotes, setEditNotes] = useState("")
  const [editConfidence, setEditConfidence] = useState(50)
  const [attachSearch, setAttachSearch] = useState("")

  const load = useCallback(async () => {
    const [hypRes, evtRes] = await Promise.all([
      fetch(`${API_BASE}/api/v2/hypotheses`, { credentials: "include" }),
      fetch(`${API_BASE}/api/v2/events?limit=100`, { credentials: "include" }),
    ])
    if (hypRes.ok) setHypotheses(await hypRes.json())
    if (evtRes.ok) setRecentEvents(await evtRes.json())
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  const selectedHyp = hypotheses.find(h => h.id === selected) ?? null

  useEffect(() => {
    if (selectedHyp) {
      setEditNotes(selectedHyp.analyst_notes)
      setEditConfidence(selectedHyp.confidence)
    }
  }, [selected, selectedHyp?.id])

  const patch = useCallback(async (id: string, updates: Partial<Hypothesis>) => {
    setSaving(true)
    await fetch(`${API_BASE}/api/v2/hypotheses/${id}`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    })
    await load()
    setSaving(false)
  }, [load])

  const createHyp = useCallback(async () => {
    if (!newTitle.trim()) return
    setSaving(true)
    await fetch(`${API_BASE}/api/v2/hypotheses`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: newTitle, statement: newStatement, confidence: newConfidence }),
    })
    setNewTitle(""); setNewStatement(""); setNewConfidence(50)
    setCreating(false)
    await load()
    setSaving(false)
  }, [newTitle, newStatement, newConfidence, load])

  const deleteHyp = useCallback(async (id: string) => {
    await fetch(`${API_BASE}/api/v2/hypotheses/${id}`, { method: "DELETE", credentials: "include" })
    setSelected(null)
    await load()
  }, [load])

  const attachEvent = useCallback(async (hyp: Hypothesis, evtId: string) => {
    const current = hyp.evidence_ids ?? []
    if (current.includes(evtId)) return
    await patch(hyp.id, { evidence_ids: [...current, evtId] })
  }, [patch])

  const detachEvent = useCallback(async (hyp: Hypothesis, evtId: string) => {
    await patch(hyp.id, { evidence_ids: (hyp.evidence_ids ?? []).filter(id => id !== evtId) })
  }, [patch])

  const saveNotes = useCallback(async () => {
    if (!selectedHyp) return
    await patch(selectedHyp.id, { analyst_notes: editNotes, confidence: editConfidence })
  }, [selectedHyp, editNotes, editConfidence, patch])

  const filteredEvents = recentEvents.filter(e =>
    attachSearch.length < 2 ||
    e.desc.toLowerCase().includes(attachSearch.toLowerCase()) ||
    e.source.toLowerCase().includes(attachSearch.toLowerCase())
  ).slice(0, 20)

  const statusGroups: Record<Status, Hypothesis[]> = { OPEN: [], CONFIRMED: [], REFUTED: [], SUSPENDED: [] }
  for (const h of hypotheses) {
    statusGroups[h.status as Status]?.push(h)
  }

  if (loading) return (
    <div className="flex flex-col h-screen bg-[#05080e]">
      <TopBar /><CommandNav />
      <div className="flex-1 flex items-center justify-center text-white/30 font-mono text-xs tracking-widest">
        LOADING HYPOTHESIS BOARD...
      </div>
    </div>
  )

  return (
    <div className="flex flex-col h-screen bg-[#05080e] text-white font-mono overflow-hidden">
      <TopBar />
      <CommandNav />

      {/* Sub-header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-[9px] tracking-[0.2em] text-white/30 uppercase">Hypothesis Board</span>
          <span className="text-[9px] text-white/20">·</span>
          <span className="text-[9px] text-white/40">{hypotheses.length} hypotheses · {hypotheses.filter(h => h.status === "OPEN").length} open</span>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="px-3 py-1 rounded border border-blue-400/40 bg-blue-400/10 text-blue-400 text-[9px] tracking-widest uppercase hover:bg-blue-400/20 transition-colors"
        >
          + New Hypothesis
        </button>
      </div>

      {/* Body */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Board — columns by status */}
        <div className="flex-1 flex gap-3 p-4 overflow-x-auto overflow-y-hidden">
          {(["OPEN", "CONFIRMED", "REFUTED", "SUSPENDED"] as Status[]).map(status => {
            const cfg = STATUS_CONFIG[status]
            const cards = statusGroups[status]
            return (
              <div key={status} className="flex flex-col min-w-[220px] w-56 shrink-0">
                {/* Column header */}
                <div
                  className="flex items-center gap-2 px-2 py-1.5 rounded border mb-2 text-[9px] tracking-widest uppercase font-bold"
                  style={{ color: cfg.color, borderColor: cfg.border, background: cfg.bg }}
                >
                  <span>{cfg.label}</span>
                  <span className="ml-auto text-[8px] opacity-60">{cards.length}</span>
                </div>

                {/* Cards */}
                <div className="flex flex-col gap-2 overflow-y-auto flex-1">
                  {cards.map(hyp => (
                    <div
                      key={hyp.id}
                      onClick={() => setSelected(selected === hyp.id ? null : hyp.id)}
                      className="rounded border p-2.5 cursor-pointer transition-all"
                      style={{
                        borderColor: selected === hyp.id ? cfg.color : "rgba(255,255,255,0.08)",
                        background: selected === hyp.id ? cfg.bg : "rgba(255,255,255,0.02)",
                      }}
                    >
                      <div className="text-[10px] font-bold text-white/85 leading-snug mb-1">{hyp.title}</div>
                      {hyp.statement && (
                        <div className="text-[8px] text-white/35 line-clamp-2 mb-2 leading-relaxed">{hyp.statement}</div>
                      )}
                      {/* Confidence bar */}
                      <div className="flex items-center gap-1.5 mb-1">
                        <div className="flex-1 h-0.5 bg-white/10 rounded-full overflow-hidden">
                          <div className="h-full rounded-full transition-all" style={{ width: `${hyp.confidence}%`, background: confidenceColor(hyp.confidence) }} />
                        </div>
                        <span className="text-[8px]" style={{ color: confidenceColor(hyp.confidence) }}>{hyp.confidence}%</span>
                      </div>
                      <div className="text-[7px] text-white/20">{icd203Label(hyp.confidence)}</div>
                      <div className="flex items-center gap-2 mt-1.5">
                        {(hyp.evidence_ids?.length ?? 0) > 0 && (
                          <span className="text-[7px] text-white/30">{hyp.evidence_ids.length} evidence</span>
                        )}
                        <span className="text-[7px] text-white/15 ml-auto">{fmtDate(hyp.updated_at)}</span>
                      </div>
                    </div>
                  ))}
                  {cards.length === 0 && (
                    <div className="text-[8px] text-white/10 text-center py-4">empty</div>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Detail panel */}
        {selectedHyp && (
          <div className="w-80 border-l border-white/10 flex flex-col overflow-hidden shrink-0">
            <div className="px-4 pt-4 pb-3 border-b border-white/10">
              <div className="text-[8px] tracking-widest text-white/25 uppercase mb-1">Hypothesis</div>
              <div className="text-[11px] font-bold text-white/90 leading-snug mb-1">{selectedHyp.title}</div>
              {selectedHyp.statement && (
                <div className="text-[9px] text-white/40 leading-relaxed mb-2">{selectedHyp.statement}</div>
              )}

              {/* Status buttons */}
              <div className="flex gap-1 flex-wrap mb-3">
                {(["OPEN","CONFIRMED","REFUTED","SUSPENDED"] as Status[]).map(s => {
                  const c = STATUS_CONFIG[s]
                  return (
                    <button
                      key={s}
                      onClick={() => patch(selectedHyp.id, { status: s })}
                      className="px-1.5 py-0.5 rounded border text-[7px] tracking-wide font-bold transition-all"
                      style={{
                        color: selectedHyp.status === s ? c.color : "rgba(255,255,255,0.25)",
                        borderColor: selectedHyp.status === s ? c.border : "rgba(255,255,255,0.08)",
                        background: selectedHyp.status === s ? c.bg : "transparent",
                      }}
                    >
                      {s}
                    </button>
                  )
                })}
              </div>

              {/* Confidence slider */}
              <div className="mb-2">
                <div className="flex items-center justify-between text-[8px] mb-1">
                  <span className="text-white/30 uppercase tracking-wider">Confidence</span>
                  <span style={{ color: confidenceColor(editConfidence) }}>{editConfidence}% — {icd203Label(editConfidence)}</span>
                </div>
                <input
                  type="range" min={0} max={100} step={5}
                  value={editConfidence}
                  onChange={e => setEditConfidence(Number(e.target.value))}
                  className="w-full h-1 rounded-full appearance-none cursor-pointer"
                  style={{ accentColor: confidenceColor(editConfidence) }}
                />
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-4">
              {/* Analyst notes */}
              <div>
                <div className="text-[8px] tracking-widest text-white/25 uppercase mb-1.5">Analyst Notes</div>
                <textarea
                  value={editNotes}
                  onChange={e => setEditNotes(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded p-2 text-[9px] text-white/70 leading-relaxed resize-none focus:outline-none focus:border-white/20"
                  rows={4}
                  placeholder="Assessment, reasoning, contradictions..."
                />
                <button
                  onClick={saveNotes}
                  disabled={saving}
                  className="mt-1 px-2 py-0.5 rounded border border-blue-400/30 text-blue-400 text-[8px] hover:bg-blue-400/10 transition-colors disabled:opacity-40"
                >
                  {saving ? "SAVING..." : "SAVE"}
                </button>
              </div>

              {/* Evidence attached */}
              <div>
                <div className="text-[8px] tracking-widest text-white/25 uppercase mb-1.5">
                  Evidence ({selectedHyp.evidence_ids?.length ?? 0})
                </div>
                {(selectedHyp.evidence_ids ?? []).map(eid => {
                  const evt = recentEvents.find(e => e.id === eid)
                  return (
                    <div key={eid} className="flex items-start gap-2 mb-1.5 p-1.5 rounded bg-white/3 border border-white/5">
                      <div className="flex-1 min-w-0">
                        <div className="text-[8px] text-white/55 truncate">{evt?.desc ?? eid}</div>
                        {evt && <div className="text-[7px] text-white/25">{evt.source} · {fmtDate(evt.timestamp)}</div>}
                      </div>
                      <button
                        onClick={() => detachEvent(selectedHyp, eid)}
                        className="text-[8px] text-white/20 hover:text-red-400 transition-colors shrink-0"
                      >
                        ×
                      </button>
                    </div>
                  )
                })}

                {/* Attach event search */}
                <div className="mt-2">
                  <input
                    type="text"
                    value={attachSearch}
                    onChange={e => setAttachSearch(e.target.value)}
                    placeholder="Search events to attach..."
                    className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-[8px] text-white/60 focus:outline-none focus:border-white/20 placeholder:text-white/20"
                  />
                  {attachSearch.length >= 2 && (
                    <div className="mt-1 max-h-36 overflow-y-auto border border-white/10 rounded">
                      {filteredEvents.filter(e => !(selectedHyp.evidence_ids ?? []).includes(e.id)).map(evt => (
                        <div
                          key={evt.id}
                          onClick={() => { attachEvent(selectedHyp, evt.id); setAttachSearch("") }}
                          className="px-2 py-1.5 cursor-pointer hover:bg-white/5 border-b border-white/5 last:border-0"
                        >
                          <div className="text-[8px] text-white/60 truncate">{evt.desc}</div>
                          <div className="text-[7px] text-white/25">{evt.source} · {evt.type}</div>
                        </div>
                      ))}
                      {filteredEvents.length === 0 && (
                        <div className="px-2 py-2 text-[8px] text-white/20">No matching events</div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* ICD 203 export */}
              <div>
                <div className="text-[8px] tracking-widest text-white/25 uppercase mb-1.5">ICD 203 Assessment</div>
                <div className="bg-white/3 border border-white/8 rounded p-2 text-[8px] text-white/40 leading-relaxed">
                  <div className="text-white/60 font-bold mb-1">{selectedHyp.title.toUpperCase()}</div>
                  <div className="mb-1">Confidence: <span style={{ color: confidenceColor(selectedHyp.confidence) }}>{icd203Label(selectedHyp.confidence)} ({selectedHyp.confidence}%)</span></div>
                  <div className="mb-1">Status: {selectedHyp.status}</div>
                  {selectedHyp.analyst_notes && <div className="mb-1 text-white/30">{selectedHyp.analyst_notes.slice(0, 200)}{selectedHyp.analyst_notes.length > 200 ? "..." : ""}</div>}
                  <div className="text-white/20">Evidence items: {selectedHyp.evidence_ids?.length ?? 0} · Analyst: {selectedHyp.analyst}</div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-4 pb-4 pt-2 border-t border-white/10 flex gap-2">
              <button
                onClick={() => setSelected(null)}
                className="flex-1 py-1.5 text-[9px] tracking-widest uppercase text-white/25 border border-white/10 rounded hover:text-white/50 transition-colors"
              >
                Close
              </button>
              <button
                onClick={() => { if (confirm("Delete this hypothesis?")) deleteHyp(selectedHyp.id) }}
                className="py-1.5 px-3 text-[9px] tracking-widest uppercase text-red-400/50 border border-red-400/20 rounded hover:text-red-400 hover:border-red-400/40 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Create modal */}
      {creating && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-[#0a0d14] border border-white/15 rounded w-[480px] p-6 font-mono">
            <div className="text-[9px] tracking-widest text-white/30 uppercase mb-4">New Hypothesis</div>
            <div className="mb-3">
              <label className="text-[8px] text-white/30 uppercase tracking-wider block mb-1">Title *</label>
              <input
                type="text"
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
                className="w-full bg-white/5 border border-white/15 rounded px-3 py-2 text-[10px] text-white focus:outline-none focus:border-blue-400/50"
                placeholder="e.g. Hamas is pre-positioning north of Jabaliya"
                autoFocus
              />
            </div>
            <div className="mb-3">
              <label className="text-[8px] text-white/30 uppercase tracking-wider block mb-1">Statement</label>
              <textarea
                value={newStatement}
                onChange={e => setNewStatement(e.target.value)}
                className="w-full bg-white/5 border border-white/15 rounded px-3 py-2 text-[9px] text-white/70 focus:outline-none focus:border-blue-400/50 resize-none"
                rows={3}
                placeholder="Specific claim, supported by what evidence, against what alternative..."
              />
            </div>
            <div className="mb-5">
              <div className="flex items-center justify-between text-[8px] mb-1">
                <label className="text-white/30 uppercase tracking-wider">Initial Confidence</label>
                <span style={{ color: confidenceColor(newConfidence) }}>{newConfidence}% — {icd203Label(newConfidence)}</span>
              </div>
              <input
                type="range" min={0} max={100} step={5}
                value={newConfidence}
                onChange={e => setNewConfidence(Number(e.target.value))}
                className="w-full cursor-pointer"
                style={{ accentColor: confidenceColor(newConfidence) }}
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={createHyp}
                disabled={!newTitle.trim() || saving}
                className="flex-1 py-2 rounded border border-blue-400/40 bg-blue-400/10 text-blue-400 text-[9px] tracking-widest uppercase hover:bg-blue-400/20 disabled:opacity-40 transition-colors"
              >
                {saving ? "CREATING..." : "CREATE"}
              </button>
              <button
                onClick={() => setCreating(false)}
                className="py-2 px-4 rounded border border-white/10 text-white/30 text-[9px] tracking-widest uppercase hover:text-white/50 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
