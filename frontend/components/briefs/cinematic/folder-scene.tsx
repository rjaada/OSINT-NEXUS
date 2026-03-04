"use client"

import { useState, useEffect } from "react"

interface FolderSceneProps {
  onOpen: () => void
}

export function FolderScene({ onOpen }: FolderSceneProps) {
  const [hovering, setHovering] = useState(false)
  const [lightFlicker, setLightFlicker] = useState(1)
  const [mounted, setMounted] = useState(false)
  const [exiting, setExiting] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  // Subtle light flickering effect
  useEffect(() => {
    const interval = setInterval(() => {
      setLightFlicker(0.85 + Math.random() * 0.15)
    }, 150)
    return () => clearInterval(interval)
  }, [])

  const handleOpen = () => {
    if (exiting) return
    setExiting(true)
    // Brief flash then transition
    setTimeout(() => onOpen(), 500)
  }

  return (
    <div
      className="fixed inset-0 flex cursor-pointer items-center justify-center overflow-hidden"
      style={{
        background: "#0a0a08",
      }}
      onClick={handleOpen}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") handleOpen()
      }}
      aria-label="Open classified folder"
    >
      {/* Desk background */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: "url(/images/desk.jpg)",
          backgroundSize: "cover",
          backgroundPosition: "center",
          opacity: 0.4,
          filter: "brightness(0.3)",
        }}
      />

      {/* Spotlight */}
      <div
        className="pointer-events-none absolute inset-0 transition-opacity duration-300"
        style={{
          background: `radial-gradient(ellipse 500px 400px at 50% 48%, rgba(255,220,150,${
            0.15 * lightFlicker
          }) 0%, rgba(255,200,100,${0.05 * lightFlicker}) 40%, transparent 70%)`,
        }}
      />

      {/* Folder */}
      <div
        className="relative z-10 flex flex-col items-center transition-transform duration-700"
        style={{
          transform: exiting
            ? "scale(1.06) translateY(-8px)"
            : mounted
            ? hovering
              ? "scale(1.04) translateY(-4px)"
              : "scale(1)"
            : "scale(0.9) translateY(30px)",
          opacity: mounted ? 1 : 0,
          transition: "transform 0.7s cubic-bezier(0.22,1,0.36,1), opacity 1.2s ease-out",
        }}
      >
        {/* Folder tab */}
        <div className="relative z-20 ml-[-90px]">
          <div
            className="rounded-t-sm px-6 py-1.5"
            style={{
              background: "linear-gradient(180deg, #c9a96e 0%, #b89050 100%)",
              boxShadow: "0 -2px 8px rgba(0,0,0,0.3)",
            }}
          >
            <span className="font-mono text-[10px] font-bold tracking-[0.15em] text-[#3a2a10]/70">
              EYES ONLY
            </span>
          </div>
        </div>

        {/* Folder body */}
        <div
          className="relative flex h-[340px] w-[460px] flex-col items-center justify-center"
          style={{
            background: "linear-gradient(175deg, #c9a96e 0%, #b08840 30%, #9a7530 100%)",
            borderRadius: "2px",
            boxShadow: hovering
              ? "0 30px 80px rgba(0,0,0,0.7), 0 0 120px rgba(200,160,80,0.08)"
              : "0 20px 60px rgba(0,0,0,0.6)",
            transition: "box-shadow 0.5s ease",
          }}
        >
          {/* Paper peeking out the top */}
          <div
            className="absolute top-[-8px] left-1/2 z-10 h-[12px] w-[85%]"
            style={{
              transform: "translateX(-50%)",
              background: "#e8e0d0",
              boxShadow: "0 -1px 4px rgba(0,0,0,0.2)",
            }}
          />

          {/* Folder texture lines */}
          <div
            className="absolute inset-0 opacity-10"
            style={{
              background:
                "repeating-linear-gradient(0deg, transparent, transparent 20px, rgba(0,0,0,0.03) 20px, rgba(0,0,0,0.03) 21px)",
            }}
          />

          {/* CLASSIFIED stamp */}
          <div
            className="relative"
            style={{
              transform: "rotate(-6deg)",
            }}
          >
            <div
              className="border-[3px] border-[#aa1111] px-8 py-3"
              style={{
                borderRadius: "4px",
              }}
            >
              <span
                className="font-[var(--font-stencil)] text-[36px] tracking-[0.12em] text-[#aa1111]"
                style={{
                  textShadow: "1px 1px 0 rgba(0,0,0,0.1)",
                  filter: "url(#roughen)",
                }}
              >
                CLASSIFIED
              </span>
            </div>
          </div>

          {/* Folder crease */}
          <div
            className="absolute bottom-[38%] left-0 right-0 h-[1px]"
            style={{
              background:
                "linear-gradient(90deg, transparent 5%, rgba(0,0,0,0.15) 30%, rgba(0,0,0,0.15) 70%, transparent 95%)",
            }}
          />
        </div>

        {/* Shadow under folder */}
        <div
          className="absolute bottom-[-20px] h-[30px] w-[400px] blur-xl"
          style={{
            background: "radial-gradient(ellipse at center, rgba(0,0,0,0.5), transparent 70%)",
          }}
        />
      </div>

      {/* SVG filter for roughening the stamp text */}
      <svg className="absolute h-0 w-0">
        <filter id="roughen">
          <feTurbulence type="turbulence" baseFrequency="0.04" numOctaves="4" result="noise" />
          <feDisplacementMap in="SourceGraphic" in2="noise" scale="1.5" />
        </filter>
      </svg>

      {/* Click hint */}
      <div
        className="absolute bottom-16 left-1/2 z-20 -translate-x-1/2 transition-opacity duration-500"
        style={{
          opacity: mounted ? (hovering ? 1 : 0.5) : 0,
        }}
      >
        <p className="animate-pulse font-mono text-[11px] tracking-[0.3em] text-[#c9a96e]/60">
          CLICK TO OPEN
        </p>
      </div>

      {/* Ambient dust particles */}
      <DustParticles />

      {/* Exit flash overlay */}
      <div
        className="pointer-events-none absolute inset-0 z-50"
        style={{
          background: "rgba(255,240,210,0.15)",
          opacity: exiting ? 1 : 0,
          transition: "opacity 0.3s ease-in",
        }}
      />
      <div
        className="pointer-events-none absolute inset-0 z-50"
        style={{
          background: "#0a0a08",
          opacity: exiting ? 1 : 0,
          transition: "opacity 0.4s 0.15s ease-in",
        }}
      />
    </div>
  )
}

function DustParticles() {
  const [particles] = useState(() =>
    Array.from({ length: 20 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: 1 + Math.random() * 2,
      duration: 8 + Math.random() * 15,
      delay: Math.random() * 8,
      opacity: 0.1 + Math.random() * 0.2,
    }))
  )

  return (
    <div className="pointer-events-none absolute inset-0 z-30 overflow-hidden" aria-hidden="true">
      {particles.map((p) => (
        <div
          key={p.id}
          className="absolute rounded-full bg-[#c9a96e]"
          style={{
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: p.size,
            height: p.size,
            opacity: p.opacity,
            animation: `dust-float ${p.duration}s ${p.delay}s ease-in-out infinite`,
          }}
        />
      ))}
    </div>
  )
}
