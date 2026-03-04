"use client"

import { useState, useEffect, useCallback, useRef } from "react"

interface PapersSceneProps {
  onSelectDocument: (docId: string) => void
}

interface DocumentCard {
  id: string
  title: string
  subtitle: string
  classification: string
  classColor: string
  date: string
  rotation: number
  x: number
  y: number
  slideDelay: number
}

const documents: DocumentCard[] = [
  {
    id: "intsum",
    title: "INTELLIGENCE SUMMARY",
    subtitle: "OSINT-NEXUS-2026-0304",
    classification: "CLASSIFIED",
    classColor: "#aa1111",
    date: "04 MAR 2026",
    rotation: -8,
    x: -280,
    y: -80,
    slideDelay: 0.3,
  },
  {
    id: "sitrep",
    title: "SITUATION REPORT",
    subtitle: "OSINT-NEXUS-SITREP-0047",
    classification: "TOP SECRET",
    classColor: "#cc0000",
    date: "03 MAR 2026",
    rotation: 5,
    x: 140,
    y: -100,
    slideDelay: 0.7,
  },
  {
    id: "threat",
    title: "THREAT ASSESSMENT",
    subtitle: "NEXUS-TA-EU-2026-Q1",
    classification: "SECRET",
    classColor: "#aa1111",
    date: "01 MAR 2026",
    rotation: -5,
    x: -160,
    y: 150,
    slideDelay: 1.1,
  },
  {
    id: "sigint",
    title: "SIGINT INTERCEPT LOG",
    subtitle: "NEXUS-SIG-0892-ECHO",
    classification: "TOP SECRET // SCI",
    classColor: "#cc0000",
    date: "02 MAR 2026",
    rotation: 7,
    x: 220,
    y: 120,
    slideDelay: 1.5,
  },
]

export function PapersScene({ onSelectDocument }: PapersSceneProps) {
  const [phase, setPhase] = useState<"sliding" | "scattered" | "interactive">("sliding")
  const [slidOut, setSlidOut] = useState<Set<number>>(new Set())
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [folderVisible, setFolderVisible] = useState(true)
  const [folderShake, setFolderShake] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Staggered paper sliding out of folder
  useEffect(() => {
    // Small shake before papers start sliding
    const shakeTimer = setTimeout(() => setFolderShake(true), 200)
    const shakeEnd = setTimeout(() => setFolderShake(false), 500)

    const timers: ReturnType<typeof setTimeout>[] = [shakeTimer, shakeEnd]

    documents.forEach((doc, index) => {
      const t = setTimeout(() => {
        setSlidOut((prev) => new Set(prev).add(index))
      }, doc.slideDelay * 1000)
      timers.push(t)
    })

    // After all papers are out, transition to scattered
    const scatterTimer = setTimeout(() => {
      setPhase("scattered")
    }, 2200)
    timers.push(scatterTimer)

    // Folder shrinks away
    const folderTimer = setTimeout(() => {
      setFolderVisible(false)
    }, 2600)
    timers.push(folderTimer)

    // Become interactive
    const interactiveTimer = setTimeout(() => {
      setPhase("interactive")
    }, 3000)
    timers.push(interactiveTimer)

    return () => timers.forEach(clearTimeout)
  }, [])

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 overflow-hidden"
      style={{ background: "#0a0a08" }}
    >
      {/* Desk background */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: "url(/images/desk.jpg)",
          backgroundSize: "cover",
          backgroundPosition: "center",
          opacity: 0.5,
          filter: "brightness(0.35)",
        }}
      />

      {/* Spotlight widens as papers scatter */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            phase === "sliding"
              ? "radial-gradient(ellipse 500px 400px at 50% 55%, rgba(255,220,150,0.18) 0%, rgba(255,200,100,0.06) 50%, transparent 70%)"
              : "radial-gradient(ellipse 900px 700px at 50% 50%, rgba(255,220,150,0.16) 0%, rgba(255,200,100,0.05) 50%, transparent 80%)",
          transition: "background 1.5s ease",
        }}
      />

      {/* Manila folder (stays partially visible, papers emerge from it) */}
      <div
        className="absolute left-1/2 top-1/2 z-10"
        style={{
          transform: folderShake
            ? "translate(-50%, -50%) rotate(-2deg) translateX(3px)"
            : folderVisible
            ? "translate(-50%, -50%) rotate(-2deg)"
            : "translate(-50%, 20%) rotate(-2deg) scale(0.85)",
          opacity: folderVisible ? 1 : 0,
          transition: folderShake
            ? "transform 0.08s ease-in-out"
            : "transform 0.8s cubic-bezier(0.22,1,0.36,1), opacity 0.6s ease-out",
        }}
      >
        {/* Folder tab */}
        <div className="relative z-20 ml-[-80px]">
          <div
            className="rounded-t-sm px-5 py-1"
            style={{
              background: "linear-gradient(180deg, #c9a96e 0%, #b89050 100%)",
              boxShadow: "0 -2px 8px rgba(0,0,0,0.3)",
            }}
          >
            <span className="font-mono text-[9px] font-bold tracking-[0.15em] text-[#3a2a10]/70">
              EYES ONLY
            </span>
          </div>
        </div>

        {/* Folder body */}
        <div
          className="relative h-[300px] w-[420px]"
          style={{
            background: "linear-gradient(175deg, #c9a96e 0%, #b08840 30%, #9a7530 100%)",
            borderRadius: "2px",
            boxShadow: "0 25px 70px rgba(0,0,0,0.6)",
          }}
        >
          {/* Folder texture */}
          <div
            className="absolute inset-0 opacity-10"
            style={{
              background:
                "repeating-linear-gradient(0deg, transparent, transparent 20px, rgba(0,0,0,0.03) 20px, rgba(0,0,0,0.03) 21px)",
            }}
          />

          {/* CLASSIFIED stamp on folder */}
          <div
            className="flex h-full items-center justify-center"
            style={{ transform: "rotate(-6deg)" }}
          >
            <div className="border-[3px] border-[#aa1111]/60 px-7 py-2.5" style={{ borderRadius: "4px" }}>
              <span
                className="font-[var(--font-stencil)] text-[30px] tracking-[0.12em] text-[#aa1111]/60"
                style={{ filter: "url(#roughen)" }}
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
                "linear-gradient(90deg, transparent 5%, rgba(0,0,0,0.12) 30%, rgba(0,0,0,0.12) 70%, transparent 95%)",
            }}
          />

          {/* Top edge slit where papers come out */}
          <div
            className="absolute top-0 left-[8%] right-[8%] h-[3px]"
            style={{
              background: "linear-gradient(90deg, transparent, rgba(0,0,0,0.15) 20%, rgba(0,0,0,0.15) 80%, transparent)",
              boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
            }}
          />
        </div>
      </div>

      {/* Papers that slide out of the folder */}
      <div className="absolute inset-0 flex items-center justify-center">
        {documents.map((doc, index) => (
          <SlidingPaper
            key={doc.id}
            doc={doc}
            index={index}
            hasSlid={slidOut.has(index)}
            isScattered={phase === "scattered" || phase === "interactive"}
            isInteractive={phase === "interactive"}
            isHovered={hoveredId === doc.id}
            onHover={() => phase === "interactive" && setHoveredId(doc.id)}
            onLeave={() => setHoveredId(null)}
            onSelect={() => phase === "interactive" && onSelectDocument(doc.id)}
          />
        ))}
      </div>

      {/* Title appears after scatter */}
      <div
        className="absolute top-10 left-1/2 z-30 -translate-x-1/2 text-center"
        style={{
          opacity: phase === "interactive" ? 1 : 0,
          transform:
            phase === "interactive"
              ? "translateX(-50%) translateY(0)"
              : "translateX(-50%) translateY(-20px)",
          transition: "all 0.8s 0.2s ease-out",
        }}
      >
        <h2 className="font-[var(--font-stencil)] text-xl tracking-[0.2em] text-[#cc0000]/80">
          SELECT DOCUMENT
        </h2>
        <p className="mt-2 font-mono text-[10px] tracking-[0.3em] text-[#c9a96e]/50">
          CHOOSE A FILE TO REVIEW
        </p>
      </div>

      {/* SVG filter for roughening */}
      <svg className="absolute h-0 w-0">
        <filter id="roughen">
          <feTurbulence type="turbulence" baseFrequency="0.04" numOctaves="4" result="noise" />
          <feDisplacementMap in="SourceGraphic" in2="noise" scale="1.5" />
        </filter>
      </svg>

      {/* Dust particles */}
      <DustParticles />
    </div>
  )
}

interface SlidingPaperProps {
  doc: DocumentCard
  index: number
  hasSlid: boolean
  isScattered: boolean
  isInteractive: boolean
  isHovered: boolean
  onHover: () => void
  onLeave: () => void
  onSelect: () => void
}

function SlidingPaper({
  doc,
  hasSlid,
  isScattered,
  isInteractive,
  isHovered,
  onHover,
  onLeave,
  onSelect,
}: SlidingPaperProps) {
  const handleClick = useCallback(() => {
    if (isInteractive) onSelect()
  }, [isInteractive, onSelect])

  // Three states:
  // 1. Not yet slid: hidden inside folder (center, slightly below center)
  // 2. hasSlid but not scattered: popped up above folder, slight random offset
  // 3. scattered: moved to final position

  const getTransform = () => {
    if (!hasSlid) {
      // Hidden inside the folder
      return "translate(0px, 20px) rotate(0deg) scale(0.7)"
    }
    if (!isScattered) {
      // Just emerged from folder - hovering above center with slight offset
      const riseY = -120 + doc.y * 0.2
      const driftX = doc.x * 0.15
      const rot = doc.rotation * 0.3
      return `translate(${driftX}px, ${riseY}px) rotate(${rot}deg) scale(0.85)`
    }
    // Final scattered position
    const hoverOffset = isHovered ? "translateY(-12px) scale(1.08)" : ""
    return `translate(${doc.x}px, ${doc.y}px) rotate(${doc.rotation}deg) scale(1) ${hoverOffset}`
  }

  const getTransition = () => {
    if (!hasSlid) return "none"
    if (!isScattered) {
      // Rising out of folder - fast upward motion
      return "transform 0.5s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease"
    }
    if (isHovered) {
      return "transform 0.25s cubic-bezier(0.22,1,0.36,1), box-shadow 0.25s ease"
    }
    // Drifting to final position - slower, natural feeling
    return "transform 0.9s cubic-bezier(0.22, 1, 0.36, 1)"
  }

  return (
    <div
      className="absolute z-10"
      style={{
        transform: getTransform(),
        transition: getTransition(),
        opacity: hasSlid ? 1 : 0,
        zIndex: isHovered ? 25 : 10,
        cursor: isInteractive ? "pointer" : "default",
        pointerEvents: isInteractive ? "auto" : "none",
      }}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      onClick={handleClick}
      role={isInteractive ? "button" : undefined}
      tabIndex={isInteractive ? 0 : -1}
      onKeyDown={(e) => {
        if ((e.key === "Enter" || e.key === " ") && isInteractive) handleClick()
      }}
      aria-label={isInteractive ? `Open ${doc.title}` : undefined}
    >
      {/* Paper shadow (appears when scattered) */}
      <div
        className="absolute -bottom-3 left-2 right-2 h-8 rounded-[50%] blur-lg"
        style={{
          background: "rgba(0,0,0,0.4)",
          opacity: isScattered ? (isHovered ? 0.6 : 0.35) : 0,
          transition: "opacity 0.4s ease",
        }}
      />

      {/* Paper card */}
      <div
        className="relative flex h-[260px] w-[190px] flex-col overflow-hidden"
        style={{
          background: "linear-gradient(180deg, #f5f0e8 0%, #ebe4d5 100%)",
          boxShadow: isHovered
            ? "0 25px 50px rgba(0,0,0,0.5), 0 0 40px rgba(200,160,80,0.12)"
            : hasSlid
            ? "0 8px 25px rgba(0,0,0,0.35)"
            : "none",
          transition: "box-shadow 0.3s ease",
        }}
      >
        {/* Top classification bar */}
        <div className="w-full bg-[#1a1a1a] py-1.5">
          <p
            className="text-center font-mono text-[7px] font-bold tracking-[0.15em]"
            style={{ color: doc.classColor }}
          >
            {doc.classification}
          </p>
        </div>

        {/* Content */}
        <div className="flex flex-1 flex-col items-center justify-center px-4">
          {/* Stamp */}
          <div
            className="mb-3 border-2 px-3 py-1.5"
            style={{
              borderColor: doc.classColor,
              transform: "rotate(-3deg)",
            }}
          >
            <span
              className="font-[var(--font-stencil)] text-[11px] tracking-[0.1em]"
              style={{ color: doc.classColor }}
            >
              {doc.classification}
            </span>
          </div>

          {/* Title */}
          <h3 className="text-center font-[var(--font-stencil)] text-[10px] leading-tight tracking-wider text-[#1a1a1a]">
            {doc.title}
          </h3>
          <p className="mt-1.5 font-mono text-[7px] tracking-wide text-[#1a1a1a]/50">
            {doc.subtitle}
          </p>
          <p className="mt-1 font-mono text-[7px] tracking-wide text-[#1a1a1a]/40">
            {doc.date}
          </p>

          {/* Fake redacted text lines */}
          <div className="mt-4 w-full space-y-1.5">
            {[100, 85, 92, 70, 88].map((width, i) => (
              <div
                key={i}
                className="h-[2px]"
                style={{
                  width: `${width}%`,
                  background: i === 2 ? "#1a1a1a" : "rgba(26,26,26,0.1)",
                }}
              />
            ))}
          </div>
        </div>

        {/* Bottom classification bar */}
        <div className="w-full bg-[#1a1a1a] py-1.5">
          <p
            className="text-center font-mono text-[7px] font-bold tracking-[0.15em]"
            style={{ color: doc.classColor }}
          >
            {doc.classification}
          </p>
        </div>

        {/* Hover warm light overlay */}
        {isHovered && (
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(circle at 50% 30%, rgba(255,220,150,0.1), transparent 70%)",
            }}
          />
        )}
      </div>
    </div>
  )
}

function DustParticles() {
  const [particles] = useState(() =>
    Array.from({ length: 18 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: 1 + Math.random() * 2,
      duration: 8 + Math.random() * 15,
      delay: Math.random() * 8,
      opacity: 0.08 + Math.random() * 0.15,
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
