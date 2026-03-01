"use client"

import { useEffect, useState } from "react"

export function FirstOpenOverlay() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    setVisible(true)
    const t = setTimeout(() => {
      setVisible(false)
    }, 2200)
    return () => clearTimeout(t)
  }, [])

  if (!visible) return null

  return (
    <div className="fixed inset-0 z-[200] bg-[#030406] text-[#d6d6e0] pointer-events-none">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_15%,rgba(0,180,216,0.25),transparent_45%),radial-gradient(circle_at_80%_75%,rgba(255,26,60,0.2),transparent_40%)]" />
      <div className="absolute inset-0 opacity-40 boot-grid" />

      <div className="absolute inset-0 flex items-center justify-center">
        <div className="w-[min(520px,90vw)] rounded-xl border border-white/15 bg-black/45 px-6 py-5 backdrop-blur-md">
          <p className="text-[11px] tracking-[0.26em] uppercase text-[#00b4d8] mb-2">OSINT NEXUS</p>
          <h2 className="text-3xl font-semibold tracking-tight text-white mb-3">Initializing Mission Console</h2>
          <p className="text-sm text-[#aab0c2] mb-5">Syncing sources, geospatial overlays, and analyst channels.</p>

          <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
            <div className="h-full boot-progress" />
          </div>

          <div className="mt-3 flex items-center justify-between text-[11px] text-[#8f96ab]">
            <span>Secure uplink</span>
            <span>v2 beta ready</span>
          </div>
        </div>
      </div>

      <style jsx>{`
        .boot-grid {
          background-image:
            linear-gradient(rgba(0, 255, 136, 0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 255, 136, 0.05) 1px, transparent 1px);
          background-size: 34px 34px;
          animation: drift 2.4s linear infinite;
        }

        .boot-progress {
          width: 0;
          background: linear-gradient(90deg, #00b4d8 0%, #00ff88 55%, #ff1a3c 100%);
          animation: load 2.1s ease-out forwards;
        }

        @keyframes load {
          0% { width: 0%; }
          100% { width: 100%; }
        }

        @keyframes drift {
          0% { transform: translateY(0px); }
          100% { transform: translateY(34px); }
        }
      `}</style>
    </div>
  )
}
