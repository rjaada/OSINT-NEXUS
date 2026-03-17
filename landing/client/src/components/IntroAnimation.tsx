/**
 * Intro Animation
 * Phase 1: Real logo.svg centered, scales in
 * Phase 2: "OSINT NEXUS" scrambles in (slower, military terminal feel)
 * Phase 3: Short hold → overlay fades out → page reveals
 * — No bottom status bar, no slide left, always centered —
 */
import { useEffect, useState } from "react";
import { useTextScramble } from "@/hooks/useTextScramble";

type Phase = "idle" | "logoIn" | "scramble" | "hold" | "fadeout" | "done";

export default function IntroAnimation() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [scrambleStart, setScrambleStart] = useState(false);

  // speed=58ms → ~2.4s total scramble for "OSINT NEXUS"
  const scrambledText = useTextScramble("OSINT NEXUS", scrambleStart, 58);

  useEffect(() => {
    const t0 = setTimeout(() => setPhase("logoIn"),   80);
    const t1 = setTimeout(() => {
      setPhase("scramble");
      setScrambleStart(true);
    }, 900);
    const t2 = setTimeout(() => setPhase("hold"),     3500);
    const t3 = setTimeout(() => setPhase("fadeout"),  3800);
    const t4 = setTimeout(() => setPhase("done"),     4600);

    return () => [t0, t1, t2, t3, t4].forEach(clearTimeout);
  }, []);

  if (phase === "done") return null;

  const logoVisible   = phase !== "idle";
  const textVisible   = phase === "scramble" || phase === "hold" || phase === "fadeout";
  const overlayFading = phase === "fadeout";

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "#000000",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "28px",
        opacity: overlayFading ? 0 : 1,
        transition: overlayFading ? "opacity 700ms ease-in" : "none",
        pointerEvents: "all",
      }}
    >
      {/* Scanline texture */}
      <div style={{
        position: "absolute", inset: 0, zIndex: 0,
        backgroundImage: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.018) 2px, rgba(255,255,255,0.018) 4px)",
        pointerEvents: "none",
      }} />

      {/* Logo — centered, scales in */}
      <div
        style={{
          position: "relative", zIndex: 1,
          opacity: logoVisible ? 1 : 0,
          transform: logoVisible ? "scale(1)" : "scale(0.75)",
          transition: "opacity 700ms cubic-bezier(0.16,1,0.3,1), transform 700ms cubic-bezier(0.16,1,0.3,1)",
        }}
      >
        <img
          src="/logo.svg"
          alt="OSINT NEXUS"
          style={{ width: "88px", height: "auto", display: "block" }}
        />
      </div>

      {/* Text block — scramble below logo */}
      <div
        style={{
          position: "relative", zIndex: 1, textAlign: "center",
          opacity: textVisible ? 1 : 0,
          transform: textVisible ? "translateY(0)" : "translateY(10px)",
          transition: "opacity 300ms ease, transform 300ms ease",
        }}
      >
        {/* Big scramble heading */}
        <span style={{
          fontFamily: "'Inter', sans-serif",
          fontWeight: 800,
          fontSize: "clamp(28px, 4.5vw, 48px)",
          letterSpacing: "-0.02em",
          color: "#F5F4EF",
          textTransform: "uppercase",
          display: "block",
          lineHeight: 1,
        }}>
          {scrambledText}
        </span>

        {/* Sub label */}
        <span style={{
          fontFamily: "'Geist Mono', monospace",
          fontSize: "9px",
          letterSpacing: "0.32em",
          color: "rgba(245,244,239,0.28)",
          display: "block",
          marginTop: "14px",
          textTransform: "uppercase",
        }}>
          [ Global Intelligence Platform ]
        </span>
      </div>
    </div>
  );
}
