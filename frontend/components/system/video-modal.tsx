"use client"

import { useEffect, useState } from "react"
import { csrfHeaders } from "@/lib/security"

interface VideoModalProps {
  open: boolean
  videoUrl?: string | null
  eventId?: string | null
  title?: string
  onClose: () => void
  onConsumed?: () => void
}

export function VideoModal({ open, videoUrl, eventId, title, onClose, onConsumed }: VideoModalProps) {
  const [consumed, setConsumed] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) {
      setConsumed(false)
      setBusy(false)
    }
  }, [open])

  const normalized = videoUrl
    ? (videoUrl.startsWith("/media/") ? `http://localhost:8000${videoUrl}` : videoUrl)
    : null

  const consumeNow = async () => {
    if (consumed || !videoUrl) return
    setBusy(true)
    try {
      const res = await fetch("http://localhost:8000/api/media/consume", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        credentials: "include",
        body: JSON.stringify({ event_id: eventId || "", video_url: videoUrl }),
      })
      if (res.ok) {
        setConsumed(true)
        onConsumed?.()
      }
    } catch (_) {
      // ignore
    } finally {
      setBusy(false)
    }
  }

  const handleClose = async () => {
    onClose()
  }

  if (!open || !normalized) return null

  return (
    <div className="fixed inset-0 z-[220]">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={handleClose} />

      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div className="w-[min(980px,96vw)] rounded-xl border border-white/15 bg-[#06080d] shadow-2xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
            <p className="text-sm text-[#d8d8e4] truncate">{title || "Latest Video"}</p>
            <button
              onClick={handleClose}
              className="px-2 py-1 text-xs rounded border border-osint-red/40 text-osint-red hover:bg-osint-red/10"
            >
              X
            </button>
          </div>

          <div className="bg-black">
            <video
              src={normalized}
              controls
              autoPlay
              className="w-full max-h-[74vh]"
            />
          </div>

          <div className="px-4 py-2 text-[11px] text-muted-foreground flex items-center justify-between gap-3">
            <span>
              {busy ? "Finalizing..." : consumed ? "Video consumed and removed from storage." : "Video kept for rewatch until you delete it."}
            </span>
            {!consumed ? (
              <button
                onClick={consumeNow}
                className="px-2 py-1 text-[10px] rounded border border-osint-red/40 text-osint-red hover:bg-osint-red/10"
                disabled={busy}
              >
                Delete Video Now
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
