"use client"

import { useMemo } from "react"
import { OperatorAccessCard } from "@/components/auth/operator-access-card"

export default function LoginPage() {
  const nextPath = useMemo(() => {
    if (typeof window === "undefined") return "/"
    const n = new URLSearchParams(window.location.search).get("next") || "/"
    return n.startsWith("/") ? n : "/"
  }, [])

  return <OperatorAccessCard nextPath={nextPath} />
}
