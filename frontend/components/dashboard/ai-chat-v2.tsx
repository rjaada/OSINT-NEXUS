"use client"

import { useState } from "react"
import { MessageSquare, SendHorizontal } from "lucide-react"

interface ChatReply {
  reply: string
  next_actions: string[]
  risk_note: string
  model: string
  generated_at: string
}

interface ChatTurn {
  role: "user" | "assistant"
  text: string
  meta?: string
}

export function AiChatV2() {
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [turns, setTurns] = useState<ChatTurn[]>([
    { role: "assistant", text: "v2 copilot online. Ask for short operational guidance.", meta: "qwen2.5:7b" },
  ])

  const send = async () => {
    const trimmed = input.trim()
    if (!trimmed || loading) return
    setInput("")
    setTurns((prev) => [...prev, { role: "user", text: trimmed }])
    setLoading(true)
    try {
      const res = await fetch("http://localhost:8000/api/v2/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed }),
      })
      if (!res.ok) throw new Error("chat request failed")
      const data: ChatReply = await res.json()
      const next = data.next_actions && data.next_actions.length > 0 ? `Next: ${data.next_actions.slice(0, 2).join(" | ")}` : ""
      const risk = data.risk_note ? `Risk: ${data.risk_note}` : ""
      const details = [next, risk].filter(Boolean).join("  ")
      setTurns((prev) => [
        ...prev,
        { role: "assistant", text: data.reply || "No response.", meta: `${data.model}${details ? ` • ${details}` : ""}` },
      ])
    } catch (_) {
      setTurns((prev) => [...prev, { role: "assistant", text: "Chat endpoint unavailable.", meta: "error" }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-xl border border-white/[0.08] bg-black/25 overflow-hidden">
      <div className="px-3 py-2 border-b border-white/[0.06] flex items-center gap-2">
        <MessageSquare className="h-3.5 w-3.5 text-osint-blue" />
        <span className="text-[10px] font-bold tracking-[0.18em] uppercase text-[#d8d8e6]">v2 AI Chat</span>
      </div>

      <div className="max-h-48 overflow-auto p-2 space-y-1.5">
        {turns.slice(-8).map((t, i) => (
          <div key={i} className={`rounded p-2 text-[10px] border ${t.role === "user" ? "border-osint-blue/30 bg-osint-blue/10 text-[#b7d7ef]" : "border-white/10 bg-black/30 text-[#c8c8d8]"}`}>
            <p className="leading-relaxed">{t.text}</p>
            {t.meta ? <p className="mt-1 text-[9px] text-muted-foreground">{t.meta}</p> : null}
          </div>
        ))}
      </div>

      <div className="p-2 border-t border-white/[0.06] flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void send()
          }}
          placeholder="Ask v2 copilot..."
          className="flex-1 h-8 rounded border border-white/10 bg-black/30 px-2 text-[11px] outline-none focus:border-osint-blue/50"
        />
        <button
          onClick={() => void send()}
          disabled={loading || !input.trim()}
          className="h-8 px-2 rounded border border-osint-blue/40 text-osint-blue disabled:opacity-50"
        >
          <SendHorizontal className={`h-3.5 w-3.5 ${loading ? "animate-pulse" : ""}`} />
        </button>
      </div>
    </div>
  )
}

