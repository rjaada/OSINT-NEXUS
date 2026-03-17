/**
 * OSINT NEXUS Landing Page — With Military-Grade Animations
 * Scroll: IntersectionObserver reveals for headings (clip-path), cards (fadeUp), lines (lineGrow)
 * Hero: staggered fade-up on load
 * Stack rows: status dots blink
 */
import { useEffect, useState } from "react";
import type React from "react";
import { useTextScramble } from "@/hooks/useTextScramble";
import RadarVisualization from "@/components/RadarVisualization";
import InteractiveMap from "@/components/InteractiveMap";
import { CoverageSection } from "@/components/CoverageSection";


const HERO_BG = "https://d2xsxph8kpxj0f.cloudfront.net/115364063/3tqFpqY5tZ3ijNZiCgsyyD/hero-bg-Q35BFzfw3Ufio4fWdxyW5x.webp";
const MISSION_BG = "https://d2xsxph8kpxj0f.cloudfront.net/115364063/3tqFpqY5tZ3ijNZiCgsyyD/mission-bg-BZPcV6e3VN2z2Jy2NPX9dM.webp";

/* ─── DATA ─── */
const stackColumns = [
  {
    tag: "[ 01 \u2014 INGEST ]", title: "INGESTION", sub: "LAYER 01",
    rows: [
      { name: "TELEGRAM CHANNELS", status: "LIVE" },
      { name: "RSS FEEDS", status: "LIVE" },
      { name: "ADS-B TRANSPONDER", status: "LIVE" },
      { name: "AIS MARITIME", status: "LIVE" },
      { name: "ACLED DATABASE", status: "SYNC" },
      { name: "RED ALERT API", status: "LIVE" },
    ],
  },
  {
    tag: "[ 02 \u2014 PROCESS ]", title: "PROCESSING", sub: "LAYER 02",
    rows: [
      { name: "POSTGRES DATABASE", status: "ACTIVE" },
      { name: "REDIS CACHE", status: "ACTIVE" },
      { name: "CONFIDENCE SCORING", status: "ACTIVE" },
      { name: "EVENT DEDUPLICATION", status: "ACTIVE" },
      { name: "GEO-TAGGING ENGINE", status: "ACTIVE" },
      { name: "SOURCE WEIGHTING", status: "ACTIVE" },
    ],
  },
  {
    tag: "[ 03 \u2014 INTEL ]", title: "INTELLIGENCE", sub: "LAYER 03",
    rows: [
      { name: "OLLAMA LOCAL LLM", status: "ACTIVE" },
      { name: "NEO4J GRAPH DB", status: "ACTIVE" },
      { name: "EVENT CORRELATION", status: "ACTIVE" },
      { name: "PATTERN DETECTION", status: "ACTIVE" },
      { name: "SITREP GENERATION", status: "ACTIVE" },
      { name: "ANALYST ALERTS", status: "ACTIVE" },
    ],
  },
];

const newsCards = [
  {
    date: "MAR 12, 2026", badge: "PRODUCT UPDATE",
    title: "NEXUS v2.0 RELEASED WITH LOCAL LLM INTEGRATION AND GRAPH INTELLIGENCE",
    body: "Full Ollama integration enables on-device intelligence analysis. Neo4j graph database powers entity relationship mapping across all monitored conflict zones.",
  },
  {
    date: "FEB 28, 2026", badge: "INTELLIGENCE",
    title: "SUDAN CONFLICT ESCALATION DETECTED VIA ACLED PATTERN ANALYSIS",
    body: "Automated pattern detection flagged 340% increase in RSF activity across Darfur region. SITREP generated and distributed to analyst network within 4 minutes.",
  },
  {
    date: "FEB 15, 2026", badge: "OPERATIONS",
    title: "RED SEA MARITIME MONITORING EXPANDED WITH AIS VESSEL TRACKING INTEGRATION",
    body: "Houthi maritime threat corridor now covered by real-time AIS feed integration. Vessel deviation alerts correlated with strike event data from open sources.",
  },
];

/* ─── COMPONENT ─── */
export default function Home() {

  /* ── Repeating hero scramble: triggers every 5s after initial appearance ── */
  const [heroScrambleTick, setHeroScrambleTick] = useState(false);
  const scrambledHeroText = useTextScramble("OSINT NEXUS", heroScrambleTick, 52);

  useEffect(() => {
    // First trigger after intro is done (~5.5s from page load)
    const firstTrigger = setTimeout(() => setHeroScrambleTick(true), 5500);
    // Then repeat every 5s after that
    const interval = setInterval(() => {
      setHeroScrambleTick((prev: boolean) => !prev); // toggle triggers the hook every cycle
    }, 5000); // repeat every 5s after first trigger

    // Simpler: restart every 5 seconds from t=5.5s
    return () => {
      clearTimeout(firstTrigger);
      clearInterval(interval);
    };
  }, []);

  /* ── Scroll reveal ── */
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-revealed");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
    );
    document
      .querySelectorAll(".reveal-heading, .reveal-card, .reveal-line")
      .forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  const delay = (ms: number): React.CSSProperties => ({ "--delay": `${ms}ms` } as React.CSSProperties);

  return (
    <div className="min-h-screen w-full" style={{ scrollBehavior: "smooth" }}>

      {/* ═══ HERO SECTION — Centered intro style ═══ */}
      <section className="relative w-full min-h-screen bg-black flex flex-col hero-scanlines">
        {/* Slim top nav */}
        <nav className="relative z-10 flex items-center justify-between px-8 md:px-16 py-8 w-full" style={{ animation: "fadeUp 400ms 4600ms cubic-bezier(0.16,1,0.3,1) both" }}>
          <div className="flex items-center gap-3 opacity-0" style={{ animation: "fadeUp 400ms 4600ms cubic-bezier(0.16,1,0.3,1) forwards" }}>
            <img src="/logo.svg" alt="logo" style={{ width: "26px", height: "auto", display: "block" }} />
            <span className="font-mono text-[10px] tracking-[0.2em] text-white/35">[ OSINT NEXUS ]</span>
          </div>
          <div className="flex items-center gap-8 opacity-0" style={{ animation: "fadeUp 400ms 4700ms cubic-bezier(0.16,1,0.3,1) forwards" }}>
            <a href="#system" className="text-[10px] tracking-[0.35em] text-white/35 uppercase hidden md:block hover:text-white/60 transition-colors">INTELLIGENCE</a>
            <a href="#coverage" className="text-[10px] tracking-[0.35em] text-white/35 uppercase hidden md:block hover:text-white/60 transition-colors">COVERAGE</a>
            <a href="#architecture" className="text-[10px] tracking-[0.35em] text-white/35 uppercase hidden md:block hover:text-white/60 transition-colors">ARCHITECTURE</a>
            <a href="#news" className="text-[10px] tracking-[0.35em] text-white/35 uppercase hidden md:block hover:text-white/60 transition-colors">NEWS</a>
          </div>
        </nav>

        {/* Centered content — mirrors intro animation layout */}
        <div className="flex-1 flex flex-col items-center justify-center text-center gap-7">
          {/* Logo */}
          <div className="opacity-0" style={{ animation: "fadeUp 600ms 4650ms cubic-bezier(0.16,1,0.3,1) forwards" }}>
            <img src="/logo.svg" alt="OSINT NEXUS" style={{ width: "80px", height: "auto", display: "block", margin: "0 auto" }} />
          </div>

          {/* Name + subtitle */}
          <div className="flex flex-col items-center gap-3 opacity-0" style={{ animation: "fadeUp 700ms 4800ms cubic-bezier(0.16,1,0.3,1) forwards" }}>
            <h1
              className="text-white font-extrabold uppercase tracking-[-0.02em] leading-none"
              style={{ fontSize: "clamp(32px, 5vw, 56px)" }}
            >
              {scrambledHeroText || "OSINT NEXUS"}
            </h1>
            <span className="font-mono text-[9px] tracking-[0.32em] text-white/30 uppercase">
              [ Global Intelligence Platform ]
            </span>
          </div>

          {/* Status row */}
          <div className="flex items-center gap-6 opacity-0" style={{ animation: "fadeUp 500ms 5000ms cubic-bezier(0.16,1,0.3,1) forwards" }}>
            <span className="font-mono text-[9px] tracking-[0.15em] text-white/25 flex items-center gap-2">
              <span className="w-[5px] h-[5px] rounded-full bg-white inline-block status-blink" />
              SYSTEM ONLINE
            </span>
            <span className="text-white/10 text-[10px]">|</span>
            <span className="font-mono text-[9px] tracking-[0.15em] text-white/25">4 ACTIVE ZONES</span>
            <span className="text-white/10 text-[10px]">|</span>
            <span className="font-mono text-[9px] tracking-[0.15em] text-white/25">v2.0</span>
          </div>

          {/* Action Buttons */}
          <div className="opacity-0 mt-8 flex items-center gap-3" style={{ animation: "fadeUp 500ms 5100ms cubic-bezier(0.16,1,0.3,1) forwards", pointerEvents: "auto" }}>
            {/* Primary — white pill */}
            <a
              href="http://localhost:3000"
              className="group flex items-center font-mono text-[10px] tracking-[0.18em] text-black bg-white rounded-full pl-6 pr-1.5 h-11 hover:bg-white/90 active:scale-[0.97] transition-all duration-300"
              style={{ transitionTimingFunction: "cubic-bezier(0.32,0.72,0,1)", boxShadow: "0 0 30px rgba(255,255,255,0.12)" }}
            >
              ENTER PLATFORM
              <span className="ml-3 w-7 h-7 rounded-full bg-black/10 flex items-center justify-center group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform duration-300">
                <svg width="9" height="9" viewBox="0 0 8 8" fill="none">
                  <path d="M1.5 6.5L6.5 1.5M6.5 1.5H2.5M6.5 1.5V5.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                </svg>
              </span>
            </a>
            {/* Secondary — ghost pill */}
            <a
              href="#coverage"
              onClick={(e) => { e.preventDefault(); document.getElementById("coverage")?.scrollIntoView({ behavior: "smooth" }); }}
              className="group flex items-center font-mono text-[10px] tracking-[0.18em] text-white/70 rounded-full ring-1 ring-white/20 bg-white/3 pl-6 pr-1.5 h-11 hover:bg-white/8 hover:ring-white/35 active:scale-[0.97] transition-all duration-300"
              style={{ transitionTimingFunction: "cubic-bezier(0.32,0.72,0,1)" }}
            >
              EXPLORE
              <span className="ml-3 w-7 h-7 rounded-full bg-white/5 flex items-center justify-center group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform duration-300">
                <svg width="9" height="9" viewBox="0 0 8 8" fill="none">
                  <path d="M4 1.5V6.5M4 6.5L1.5 4M4 6.5L6.5 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                </svg>
              </span>
            </a>
          </div>

          {/* Scroll hint */}
          <div className="opacity-0" style={{ animation: "fadeUp 400ms 5300ms cubic-bezier(0.16,1,0.3,1) forwards", marginTop: "24px" }}>
            <span className="font-mono text-[9px] tracking-[0.3em] text-white/15 uppercase">SCROLL TO EXPLORE</span>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="relative z-10 flex items-center justify-between px-8 md:px-16 py-8 border-t border-white/[0.07] opacity-0" style={{ animation: "fadeUp 400ms 5400ms cubic-bezier(0.16,1,0.3,1) forwards" }}>
          <span className="text-[10px] tracking-[0.35em] text-white/20 uppercase">CONFLICT MONITORING</span>
          <span className="font-mono text-[10px] tracking-[0.2em] text-white/15">[ 2026 ]</span>
        </div>
      </section>

      {/* ═══ MISSION STATEMENT ═══ */}
      <section
        className="relative w-full bg-black py-16 md:py-24 px-8 md:px-16"
        style={{ backgroundImage: `url(${MISSION_BG})`, backgroundSize: "cover", backgroundPosition: "center" }}
      >
        <div className="absolute inset-0 bg-black/70" />
        <div className="relative z-10">
          <div className="flex items-center justify-between mb-16">
            <span className="text-[10px] tracking-[0.35em] text-white/35 uppercase reveal-card" style={delay(0)}>MISSION</span>
            <span className="font-mono text-[10px] tracking-[0.2em] text-white/25 reveal-card" style={delay(100)}>[ STATEMENT ]</span>
          </div>
          <div className="max-w-[800px]">
            <p className="text-white/80 text-[14px] md:text-[16px] leading-[2] tracking-[0.02em] reveal-card" style={delay(200)}>
              WE BUILD AUTONOMOUS INTELLIGENCE SYSTEMS THAT MONITOR, ANALYZE AND REPORT ON ACTIVE CONFLICT ZONES WORLDWIDE. OUR PLATFORM FUSES OPEN-SOURCE DATA FROM TELEGRAM, SATELLITE IMAGERY, FLIGHT TRACKING AND MARITIME FEEDS INTO ACTIONABLE INTELLIGENCE — PROCESSED LOCALLY, WITH ZERO CLOUD DEPENDENCY.
            </p>
          </div>
          <div className="mt-16 flex items-center gap-8 reveal-card" style={delay(350)}>
            <span className="text-[10px] tracking-[0.05em] text-white/30 leading-[1.8]">4 ACTIVE ZONES</span>
            <span className="text-white/10">|</span>
            <span className="text-[10px] tracking-[0.05em] text-white/30 leading-[1.8]">6 DATA SOURCES</span>
            <span className="text-white/10">|</span>
            <span className="text-[10px] tracking-[0.05em] text-white/30 leading-[1.8]">60s REFRESH CYCLE</span>
          </div>
        </div>
      </section>

      {/* ═══ GLOBAL COVERAGE MAP ═══ */}
      <section className="w-full bg-black flex flex-col items-center py-12 px-8 md:px-16 border-t border-white/[0.05]" id="global-map">
        <div className="flex w-full items-center justify-between mb-8">
          <span className="text-[10px] tracking-[0.35em] text-white/35 uppercase reveal-card" style={delay(0)}>GLOBAL</span>
          <span className="font-mono text-[10px] tracking-[0.2em] text-white/25 reveal-card" style={delay(100)}>[ LIVE MAP ]</span>
        </div>
        
        <div className="w-full reveal-card" style={delay(200)}>
          <InteractiveMap />
        </div>
      </section>

      {/* ═══ WHERE THE WAR IS — backend-driven ═══ */}
      <CoverageSection />

      {/* ═══ LATTICE / SYSTEM CAPABILITIES ═══ */}
      <section className="w-full bg-[#F5F4EF] text-black border-t border-black/10" id="system">
        {/* Top bar */}
        <div className="flex items-center justify-between" style={{ padding: "32px 40px 0 40px" }}>
          <span className="font-mono text-[10px] tracking-[0.15em] text-black/45 reveal-card" style={delay(0)}>[ LATTICE FOR MISSION AUTONOMY ]</span>
          <div style={{ display: "grid", gridTemplateColumns: "3px 3px", gap: "4px", ...delay(100) }} className="reveal-card">
            <div style={{ width: "3px", height: "3px", background: "rgba(0,0,0,0.4)" }} />
            <div style={{ width: "3px", height: "3px", background: "rgba(0,0,0,0.4)" }} />
            <div style={{ width: "3px", height: "3px", background: "rgba(0,0,0,0.4)" }} />
            <div style={{ width: "3px", height: "3px", background: "rgba(0,0,0,0.4)" }} />
          </div>
        </div>

        {/* Heading */}
        <div style={{ padding: "24px 40px 40px 40px" }}>
          <h2 className="text-black font-extrabold uppercase leading-[0.88] tracking-[-0.025em] reveal-heading" style={{ fontSize: "clamp(52px, 8vw, 108px)", maxWidth: "700px" }}>
            ADVANTAGES FOR<br />UNRIVALED<br />DETERRENCE
          </h2>
        </div>

        {/* Thin border */}
        <div className="reveal-line" style={{ width: "100%", height: "1px", background: "rgba(0,0,0,0.12)" }} />

        {/* Radar — 3-column grid (Made radar column wider) */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 3fr 1fr", borderLeft: "1px solid rgba(0,0,0,0.12)" }} className="radar-grid">
          <div style={{ borderRight: "1px solid rgba(0,0,0,0.12)", minHeight: "500px", background: "#F5F4EF" }} className="hidden lg:block" />
          <div style={{ borderRight: "1px solid rgba(0,0,0,0.12)", padding: "40px", display: "flex", alignItems: "center", justifyContent: "center", background: "#F5F4EF" }}>
            <RadarVisualization />
          </div>
          <div style={{ background: "#F5F4EF" }} className="hidden lg:block" />
        </div>

        {/* Bottom border */}
        <div className="reveal-line" style={{ width: "100%", height: "1px", background: "rgba(0,0,0,0.12)" }} />

        {/* Feature cards */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", borderLeft: "1px solid rgba(0,0,0,0.12)" }} className="feature-cards-grid">
          <div style={{ borderRight: "1px solid rgba(0,0,0,0.08)", padding: "48px 40px" }} className="reveal-card">
            <div style={{ display: "grid", gridTemplateColumns: "5px 5px", gap: "4px", width: "fit-content", marginBottom: "28px" }}>
              <div style={{ width: "5px", height: "5px", background: "#000" }} /><div style={{ width: "5px", height: "5px", background: "#000" }} />
              <div style={{ width: "5px", height: "5px", background: "#000" }} /><div style={{ width: "5px", height: "5px", background: "#000" }} />
            </div>
            <h3 style={{ fontSize: "22px", fontWeight: 800, color: "#000", letterSpacing: "-0.01em", marginBottom: "20px" }}>DISTRIBUTED C2</h3>
            <p className="font-mono" style={{ fontSize: "11px", lineHeight: "1.9", color: "rgba(0,0,0,0.55)", letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: "14px" }}>
              AUTOMATICALLY BREAKS DOWN OPERATOR INTENT INTO DISCRETE TASKS THAT ARE DISTRIBUTED ACROSS UNMANNED SYSTEMS TO BEST ACCOMPLISH MISSIONS UNDER HUMAN SUPERVISION.
            </p>
            <p className="font-mono" style={{ fontSize: "11px", lineHeight: "1.9", color: "rgba(0,0,0,0.55)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              USE A COMBINATION OF OPEN-SOURCE DATA AND ANALYTICS TO DEVELOP AUTONOMOUS MONITORING BEHAVIORS AND DETECTION TACTICS.
            </p>
          </div>
          <div style={{ padding: "48px 40px" }} className="reveal-card">
            <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#000", marginBottom: "28px" }} />
            <h3 style={{ fontSize: "22px", fontWeight: 800, color: "#000", letterSpacing: "-0.01em", marginBottom: "20px" }}>REAL-TIME FUSION</h3>
            <p className="font-mono" style={{ fontSize: "11px", lineHeight: "1.9", color: "rgba(0,0,0,0.55)", letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: "14px" }}>
              INGESTS LIVE DATA FROM TELEGRAM CHANNELS, ADS-B TRANSPONDERS, AIS MARITIME FEEDS AND RSS SOURCES SIMULTANEOUSLY. ALL SOURCES CROSS-REFERENCED EVERY 60 SECONDS.
            </p>
            <p className="font-mono" style={{ fontSize: "11px", lineHeight: "1.9", color: "rgba(0,0,0,0.55)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              CONFIDENCE SCORES COMPUTED PER EVENT USING ICD 203 ANALYTIC STANDARDS. SOURCE RELIABILITY WEIGHTED BY TIER CLASSIFICATION AND HISTORICAL ACCURACY.
            </p>
          </div>
        </div>
      </section>

      {/* ═══ THE STACK / ARCHITECTURE ═══ */}
      <section className="w-full bg-black text-white" id="architecture">
        <div className="flex items-center justify-between px-8 md:px-16 pt-20">
          <span className="text-[10px] tracking-[0.35em] text-white/35 uppercase reveal-card" style={delay(0)}>SYSTEM</span>
          <span className="font-mono text-[10px] tracking-[0.2em] text-white/25 reveal-card" style={delay(100)}>[ ARCHITECTURE ]</span>
        </div>
        <div className="px-8 md:px-16 pt-8 pb-16">
          <h2 className="text-white font-extrabold uppercase leading-[0.9] tracking-[-0.02em] reveal-heading" style={{ fontSize: "clamp(72px, 11vw, 160px)" }}>
            THE<br />STACK
          </h2>
        </div>
        <div className="w-full h-px bg-white/10 reveal-line" />
        <div className="grid grid-cols-1 md:grid-cols-3 border-l border-white/[0.08]">
          {stackColumns.map((col, ci) => (
            <div key={col.tag} className="border-r border-white/[0.08] px-10 py-12 reveal-card" style={delay(ci * 120)}>
              <span className="font-mono text-[10px] text-white/30">{col.tag}</span>
              <div className="h-8" />
              <h3 className="text-[18px] font-bold text-white">{col.title}</h3>
              <span className="text-[10px] tracking-[0.3em] text-white/35">{col.sub}</span>
              <div className="w-full h-px bg-white/[0.08] mt-7 mb-3 reveal-line" />
              {col.rows.map((row, ri) => (
                <div key={row.name} className="flex items-center justify-between py-3 border-b border-white/[0.06] reveal-card" style={delay(ri * 55 + ci * 120)}>
                  <span className="text-[11px] tracking-[0.15em] text-white/60">{row.name}</span>
                  <div className="flex items-center gap-[6px]">
                    <span className="w-[6px] h-[6px] rounded-full bg-white inline-block status-blink" style={{ animationDelay: `${ri * 300}ms` }} />
                    <span className="font-mono text-[9px] text-white/40">{row.status}</span>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between px-8 md:px-16 py-12 md:py-16">
          <div className="text-[11px] text-white/35 tracking-[0.05em] leading-[1.8] reveal-card" style={delay(0)}>
            ALL PROCESSING RUNS LOCALLY.<br />
            ZERO CLOUD DEPENDENCY. ZERO DATA EXFILTRATION.
          </div>
          <span className="font-mono text-[10px] text-white/20 mt-4 md:mt-0 reveal-card" style={delay(100)}>v2.0 &middot; AUTONOMOUS</span>
        </div>
      </section>

      {/* ═══ NEWS ═══ */}
      <section className="w-full bg-black text-white" id="news">
        <div className="flex items-center justify-between px-8 md:px-16 pt-16">
          <span className="text-[10px] tracking-[0.35em] text-white/35 uppercase reveal-card" style={delay(0)}>NEWS</span>
          <span className="font-mono text-[10px] tracking-[0.2em] text-white/25 reveal-card" style={delay(100)}>[ LIVE ]</span>
        </div>
        <div className="px-8 md:px-16 pt-8 pb-12">
          <h2 className="text-white font-extrabold uppercase leading-[1.1] tracking-[-0.02em] reveal-heading" style={{ fontSize: "clamp(28px, 3.5vw, 48px)", maxWidth: "700px" }}>
            CREATING INTELLIGENCE<br />THAT HELPS CONTAIN CONFLICT
          </h2>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", borderLeft: "1px solid rgba(255,255,255,0.08)", borderTop: "1px solid rgba(255,255,255,0.08)" }} className="news-grid pb-12 mx-8 md:mx-16">
          {newsCards.map((card, i) => (
            <div key={card.date} className="reveal-card" style={{ borderRight: "1px solid rgba(255,255,255,0.08)", padding: "32px", ...delay(i * 120) }}>
              <span className="font-mono text-[10px] tracking-[0.1em] text-white/30">{card.date}</span>
              <div className="mt-6">
                <span className="text-[9px] tracking-[0.2em] text-white/50 inline-block" style={{ border: "1px solid rgba(255,255,255,0.15)", padding: "3px 8px" }}>
                  {card.badge}
                </span>
              </div>
              <h3 className="mt-6 text-white font-bold leading-[1.35] tracking-[-0.01em]" style={{ fontSize: "clamp(14px, 1.5vw, 18px)" }}>
                {card.title}
              </h3>
              <p className="mt-4 text-[12px] leading-[1.85] text-white/55 tracking-[0.03em]">{card.body}</p>
              <span className="mt-6 inline-block text-[10px] tracking-[0.2em] text-white/35 hover:text-white/60 transition-colors cursor-pointer">READ MORE &rarr;</span>
            </div>
          ))}
        </div>
      </section>

      {/* ═══ FOOTER ═══ */}
      <footer className="w-full bg-black border-t border-white/[0.08] px-8 md:px-16 py-12">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/logo.svg" alt="logo" style={{ width: "22px", height: "auto", display: "block" }} />
            <span className="font-mono text-[10px] tracking-[0.2em] text-white/30">[ OSINT NEXUS ]</span>
          </div>
          <div className="flex flex-col md:flex-row items-start md:items-center gap-4 md:gap-8 mt-4 md:mt-0">
            <span className="text-[10px] tracking-[0.05em] text-white/25">OPEN-SOURCE INTELLIGENCE PLATFORM</span>
            <span className="font-mono text-[10px] text-white/15">&copy; 2026</span>
          </div>
        </div>
      </footer>

      {/* Responsive overrides */}
      <style>{`
        @media (max-width: 1200px) {
          .coverage-grid { grid-template-columns: repeat(2, 1fr) !important; }
          .radar-grid { grid-template-columns: 1fr !important; }
          .feature-cards-grid { grid-template-columns: 1fr !important; }
        }
        @media (max-width: 768px) {
          section[id="coverage"] { padding: 48px 24px 64px 24px !important; }
          .coverage-grid { grid-template-columns: 1fr !important; }
          .news-grid { grid-template-columns: 1fr !important; }
          .feature-cards-grid { grid-template-columns: 1fr !important; }
          .coverage-col { padding: 24px 20px 32px 20px !important; }
        }
        .coverage-col:hover { background: rgba(0,0,0,0.03); cursor: default; }
      `}</style>
    </div>
  );
}
