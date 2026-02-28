"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

const TABS = [
  { href: "/", label: "Hub" },
  { href: "/operations", label: "Operations" },
  { href: "/alerts", label: "Alerts" },
]

export function CommandNav() {
  const pathname = usePathname()

  return (
    <nav className="flex items-center gap-1 px-3 py-2 border-b border-white/[0.06]">
      {TABS.map((tab) => {
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
    </nav>
  )
}
