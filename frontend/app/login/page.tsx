"use client"

import { FormEvent, useMemo, useState } from "react"
import { useRouter } from "next/navigation"

const CREDENTIALS = {
  viewer: {
    username: (process.env.NEXT_PUBLIC_OSINT_VIEWER_USER || "viewer").toLowerCase(),
    password: process.env.NEXT_PUBLIC_OSINT_VIEWER_PASSWORD || "viewer123",
  },
  analyst: {
    username: (process.env.NEXT_PUBLIC_OSINT_ANALYST_USER || "analyst").toLowerCase(),
    password: process.env.NEXT_PUBLIC_OSINT_ANALYST_PASSWORD || "analyst123",
  },
  admin: {
    username: (process.env.NEXT_PUBLIC_OSINT_ADMIN_USER || "admin").toLowerCase(),
    password: process.env.NEXT_PUBLIC_OSINT_ADMIN_PASSWORD || process.env.NEXT_PUBLIC_OSINT_PASSWORD || "osint123",
  },
}

export default function LoginPage() {
  const router = useRouter()
  const nextPath = useMemo(() => {
    if (typeof window === "undefined") return "/"
    const n = new URLSearchParams(window.location.search).get("next") || "/"
    return n.startsWith("/") ? n : "/"
  }, [])

  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [role, setRole] = useState<"viewer" | "analyst" | "admin">("analyst")

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const selected = CREDENTIALS[role]
    const validUser = username.trim().toLowerCase() === selected.username
    const validPass = password === selected.password
    if (!validUser || !validPass) {
      setError("Invalid credentials")
      return
    }

    const expires = new Date(Date.now() + 1000 * 60 * 60 * 8).toUTCString()
    document.cookie = `osint_session=1; Path=/; Expires=${expires}; SameSite=Lax`
    document.cookie = `osint_role=${role}; Path=/; Expires=${expires}; SameSite=Lax`
    document.cookie = `osint_user=${selected.username}; Path=/; Expires=${expires}; SameSite=Lax`
    router.replace(nextPath)
  }

  return (
    <main className="min-h-screen bg-background text-foreground px-6 py-8 md:px-10 grid place-items-center">
      <section className="w-full max-w-md rounded-xl border border-white/10 bg-black/40 p-6">
        <p className="text-[11px] uppercase tracking-[0.22em] text-osint-blue mb-2">OSINT NEXUS</p>
        <h1 className="text-3xl font-semibold mb-2">Login</h1>
        <p className="text-sm text-muted-foreground mb-5">Authenticate to access the operations dashboards.</p>

        <form onSubmit={onSubmit} className="space-y-3">
          <label className="block">
            <span className="text-xs text-muted-foreground">Role</span>
            <select
              className="mt-1 w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-osint-blue/60"
              value={role}
              onChange={(e) => setRole(e.target.value as "viewer" | "analyst" | "admin")}
            >
              <option value="viewer">Viewer</option>
              <option value="analyst">Analyst</option>
              <option value="admin">Admin</option>
            </select>
          </label>

          <label className="block">
            <span className="text-xs text-muted-foreground">Username</span>
            <input
              className="mt-1 w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-osint-blue/60"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={CREDENTIALS[role].username}
            />
          </label>

          <label className="block">
            <span className="text-xs text-muted-foreground">Password</span>
            <input
              type="password"
              className="mt-1 w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-osint-blue/60"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
            />
          </label>

          {error ? <p className="text-xs text-osint-red">{error}</p> : null}

          <button
            type="submit"
            className="w-full rounded border border-osint-green/40 bg-osint-green/15 py-2 text-sm font-medium text-osint-green hover:bg-osint-green/25 transition-colors"
          >
            Access Console
          </button>
        </form>

        <div className="mt-4 text-[11px] text-muted-foreground space-y-1">
          <p>Default credentials:</p>
          <p><span className="text-[#d0d0df]">viewer</span> / {CREDENTIALS.viewer.password}</p>
          <p><span className="text-[#d0d0df]">analyst</span> / {CREDENTIALS.analyst.password}</p>
          <p><span className="text-[#d0d0df]">admin</span> / {CREDENTIALS.admin.password}</p>
        </div>
      </section>
    </main>
  )
}
