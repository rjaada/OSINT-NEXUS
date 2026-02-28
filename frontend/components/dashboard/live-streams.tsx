"use client"

import { useState } from "react"
import { Tv, X, Maximize2, Minimize2 } from "lucide-react"

const STREAMS = [
  {
    id: "cnn",
    name: "CNN Intl",
    channelId: "UCupvZG-5ko_eiXAupbDfxWw", // CNN International coverage
    color: "#cc0000",
    flag: "🌎",
  },
  {
    id: "dw",
    name: "DW News",
    channelId: "UCknLrEdhRCp1aegoMqRaCZg",
    color: "#d0003c",
    flag: "🇩🇪",
  },
  {
    id: "france24",
    name: "France 24",
    channelId: "UCQfwfsi5VrQ8yKZ-UWmAEFg",
    color: "#0055a5",
    flag: "🇫🇷",
  },
  {
    id: "trt",
    name: "TRT World",
    channelId: "UC7fWeaHhqgM4Ry-RMpM2YYw",
    color: "#e84e4e",
    flag: "🌐",
  },
]

// YouTube channel live stream embed — always points to whatever the channel is broadcasting now
const streamUrl = (channelId: string) =>
  `https://www.youtube.com/embed/live_stream?channel=${channelId}&autoplay=1&mute=1&controls=1&rel=0&modestbranding=1`

export function LiveStreams() {
  const [open, setOpen]       = useState(false)
  const [active, setActive]   = useState(STREAMS[0])
  const [expanded, setExpanded] = useState(false)

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed z-50 flex items-center gap-2 px-3 py-2 rounded-lg text-[10px] font-bold tracking-widest uppercase transition-all hover:scale-105"
        style={{
          right: "348px",
          bottom: "52px",
          background: "rgba(5,5,10,0.95)",
          border: "1px solid rgba(200,168,75,0.4)",
          color: "#c8a84b",
          backdropFilter: "blur(12px)",
          boxShadow: "0 0 16px rgba(200,168,75,0.15)",
        }}
      >
        <Tv className="h-3.5 w-3.5" />
        <span>Live Streams</span>
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full rounded-full bg-osint-red opacity-75 animate-blink" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-osint-red" />
        </span>
      </button>
    )
  }

  return (
    <div
      className="fixed z-50 shadow-2xl flex flex-col overflow-hidden"
      style={{
        right: expanded ? "340px" : "348px",
        bottom: "48px",
        width:  expanded ? "640px" : "380px",
        height: expanded ? "380px" : "220px",
        background: "rgba(5,5,10,0.97)",
        border: "1px solid rgba(255,255,255,0.1)",
        borderRadius: "12px",
        backdropFilter: "blur(20px)",
        transition: "all 0.25s ease",
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-white/[0.06]">
        <Tv className="h-3.5 w-3.5 text-osint-amber" />
        <span className="text-[10px] font-bold tracking-[0.2em] text-[#e0e0e8] uppercase">Live Streams</span>
        <span className="relative flex h-1.5 w-1.5 ml-1">
          <span className="absolute inline-flex h-full w-full rounded-full bg-osint-red opacity-75 animate-blink" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-osint-red" />
        </span>

        {/* Stream selector */}
        <div className="flex items-center gap-1 ml-2 flex-1">
          {STREAMS.map((s) => (
            <button
              key={s.id}
              onClick={() => setActive(s)}
              title={s.name}
              className="text-[9px] px-1.5 py-0.5 rounded transition-all"
              style={{
                background: active.id === s.id ? `${s.color}20` : "transparent",
                border: `1px solid ${active.id === s.id ? s.color + "60" : "transparent"}`,
                color: active.id === s.id ? s.color : "#505060",
              }}
            >
              {s.flag} {s.name.split(" ")[0]}
            </button>
          ))}
        </div>

        <button onClick={() => setExpanded(!expanded)} className="text-muted-foreground hover:text-white transition-colors ml-auto">
          {expanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
        </button>
        <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-osint-red transition-colors">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Video */}
      <div className="flex-1 relative bg-black">
        <iframe
          key={active.id}
          src={streamUrl(active.channelId)}
          allow="autoplay; encrypted-media"
          allowFullScreen
          className="absolute inset-0 w-full h-full"
          style={{ border: "none" }}
        />
      </div>
    </div>
  )
}
