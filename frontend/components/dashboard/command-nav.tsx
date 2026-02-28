"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useMemo, useState } from "react"

export function CommandNav() {
  const pathname = usePathname()
  const inV2 = pathname === "/v2" || pathname.startsWith("/v2/")
  const isArabic = inV2 ? pathname.startsWith("/v2/ar") : pathname.startsWith("/ar")
  const prefix = inV2 ? "/v2" : ""

  const tabs = useMemo(() => {
    if (isArabic) {
      return [
        { href: `${prefix}/ar`, label: "الرئيسية" },
        { href: `${prefix}/ar/operations`, label: "العمليات" },
        { href: `${prefix}/ar/alerts`, label: "الإنذارات" },
        { href: `${prefix}/ar/sources`, label: "المصادر" },
      ]
    }
    return [
      { href: prefix || "/", label: "Hub" },
      { href: `${prefix}/operations`, label: "Operations" },
      { href: `${prefix}/alerts`, label: "Alerts" },
      { href: `${prefix}/sources`, label: "Sources" },
    ]
  }, [isArabic, prefix])

  const [crisisMode, setCrisisMode] = useState(false)

  useEffect(() => {
    try {
      setCrisisMode(localStorage.getItem("osint_crisis_mode") === "1")
    } catch (_) {}
  }, [])

  const toggleMode = () => {
    const next = !crisisMode
    setCrisisMode(next)
    try {
      localStorage.setItem("osint_crisis_mode", next ? "1" : "0")
      window.dispatchEvent(new CustomEvent("osint:mode", { detail: { crisis: next } }))
    } catch (_) {}
  }

  const switchHref = inV2
    ? (pathname.replace(/^\/v2/, "") || "/")
    : `/v2${pathname === "/" ? "" : pathname}`

  return (
    <nav className="flex items-center gap-1 px-3 py-2 border-b border-white/[0.06] flex-wrap">
      {tabs.map((tab) => {
        const active = pathname === tab.href
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className="text-[10px] tracking-[0.18em] uppercase px-3 py-1.5 rounded transition-all"
            style={{
              color: active ? "#e0e0e8" : "#707080",
              background: active ? "rgba(255,255,255,0.07)" : "transparent",
              border: `1px solid ${active ? "rgba(255,255,255,0.14)" : "transparent"}`,
            }}
          >
            {tab.label}
          </Link>
        )
      })}

      <Link
        href={switchHref}
        className="ml-auto text-[9px] tracking-[0.14em] uppercase px-2.5 py-1 rounded"
        style={{
          color: inV2 ? "#00ff88" : "#b24bff",
          border: `1px solid ${inV2 ? "#00ff8855" : "#b24bff55"}`,
          background: inV2 ? "#00ff8818" : "#b24bff18",
        }}
      >
        {inV2 ? "Switch to V1 Stable" : "Switch to V2 Beta"}
      </Link>

      <button
        onClick={toggleMode}
        className="text-[9px] tracking-[0.14em] uppercase px-2.5 py-1 rounded"
        style={{
          color: crisisMode ? "#ff1a3c" : "#00b4d8",
          border: `1px solid ${crisisMode ? "#ff1a3c55" : "#00b4d855"}`,
          background: crisisMode ? "#ff1a3c18" : "#00b4d818",
        }}
      >
        {isArabic ? (crisisMode ? "وضع أزمة" : "وضع عادي") : (crisisMode ? "Crisis Mode" : "Normal Mode")}
      </button>
    </nav>
  )
}
