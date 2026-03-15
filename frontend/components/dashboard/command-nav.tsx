"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useMemo, useState } from "react"

export function CommandNav() {
  const pathname = usePathname()
  const inV2 = pathname === "/v2" || pathname.startsWith("/v2/")
  const isArabic = inV2 ? pathname.startsWith("/v2/ar") : pathname.startsWith("/ar")
  const prefix = inV2 ? "/v2" : ""
  const [role, setRole] = useState("viewer")

  useEffect(() => {
    const roleCookie = document.cookie.split("; ").find((x) => x.startsWith("osint_role="))
    setRole(roleCookie ? decodeURIComponent(roleCookie.split("=")[1]).toLowerCase() : "viewer")
  }, [])

  const tabs = useMemo(() => {
    if (isArabic) {
      return [
        { href: `${prefix}/ar`, label: "الرئيسية" },
        { href: `${prefix}/ar/operations`, label: "العمليات" },
        { href: `${prefix}/ar/alerts`, label: "الإنذارات" },
        { href: `${prefix}/ar/sources`, label: "المصادر" },
        ...(inV2 && (role === "analyst" || role === "admin") ? [{ href: `${prefix}/briefs`, label: "الإيجاز" }] : []),
        ...(inV2 && (role === "analyst" || role === "admin") ? [{ href: `${prefix}/graph`, label: "الرسم البياني" }] : []),
        ...(inV2 ? [{ href: `${prefix}/ar/card`, label: "بطاقة" }] : []),
        ...(inV2 ? [{ href: `${prefix}/ar/health`, label: "الصحة" }] : []),
        ...(inV2 && role === "admin" ? [{ href: `${prefix}/ar/admin`, label: "المشرف" }] : []),
      ]
    }
    return [
      { href: prefix || "/", label: "Hub" },
      { href: `${prefix}/operations`, label: "Operations" },
      { href: `${prefix}/alerts`, label: "Alerts" },
      { href: `${prefix}/sources`, label: "Sources" },
      ...(inV2 && (role === "analyst" || role === "admin") ? [{ href: `${prefix}/briefs`, label: "Intel Briefs" }] : []),
      ...(inV2 && (role === "analyst" || role === "admin") ? [{ href: `${prefix}/sitrep`, label: "SITREP" }] : []),
      ...(inV2 && (role === "analyst" || role === "admin") ? [{ href: `${prefix}/graph`, label: "Intel Graph" }] : []),
      ...(inV2 ? [{ href: `${prefix}/card`, label: "My Card" }] : []),
      ...(inV2 ? [{ href: `${prefix}/health`, label: "Health" }] : []),
      ...(inV2 && role === "admin" ? [{ href: `${prefix}/admin`, label: "Admin" }] : []),
    ]
  }, [inV2, isArabic, prefix, role])

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

      <button
        onClick={toggleMode}
        className="ml-auto text-[9px] tracking-[0.14em] uppercase px-2.5 py-1 rounded"
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
