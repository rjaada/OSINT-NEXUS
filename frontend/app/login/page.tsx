"use client"

import { FormEvent, useMemo, useState } from "react"

type Role = "viewer" | "analyst" | "admin"

export default function LoginPage() {
  const nextPath = useMemo(() => {
    if (typeof window === "undefined") return "/"
    const n = new URLSearchParams(window.location.search).get("next") || "/"
    return n.startsWith("/") ? n : "/"
  }, [])

  const [mode, setMode] = useState<"login" | "register">("login")
  const [role, setRole] = useState<Role>("viewer")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [note, setNote] = useState("")

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError("")
    setNote("")
    if (!username.trim() || !password) {
      setError("Username and password are required")
      return
    }
    if (mode === "register" && password !== confirm) {
      setError("Password confirmation does not match")
      return
    }
    setBusy(true)
    try {
      if (mode === "register") {
        const reg = await fetch("http://localhost:8000/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ username: username.trim(), password, role }),
        })
        const regJson = await reg.json().catch(() => ({}))
        if (!reg.ok) {
          setError(regJson?.detail || "Registration failed")
          return
        }
        setNote("Account created. Logging you in...")
      }

      const login = await fetch("http://localhost:8000/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username: username.trim(), password }),
      })
      const loginJson = await login.json().catch(() => ({}))
      if (!login.ok) {
        setError(loginJson?.detail || "Invalid credentials")
        return
      }

      const expires = new Date(Date.now() + 1000 * 60 * 60 * 8).toUTCString()
      let resolvedRole = String(loginJson?.role || role).toLowerCase()
      let resolvedUser = String(loginJson?.username || username).toLowerCase()
      try {
        const sessionRes = await fetch("http://localhost:8000/api/auth/session", {
          credentials: "include",
          cache: "no-store",
        })
        const sessionJson = await sessionRes.json().catch(() => ({}))
        if (sessionRes.ok && sessionJson?.authenticated) {
          resolvedRole = String(sessionJson?.role || resolvedRole).toLowerCase()
          resolvedUser = String(sessionJson?.username || resolvedUser).toLowerCase()
        }
      } catch {}
      document.cookie = `osint_session=1; Path=/; Expires=${expires}; SameSite=Lax`
      document.cookie = `osint_role=${resolvedRole}; Path=/; Expires=${expires}; SameSite=Lax`
      document.cookie = `osint_user=${resolvedUser}; Path=/; Expires=${expires}; SameSite=Lax`

      // Avoid role-gate redirect loop when "next" points to /v2 and user is viewer.
      const targetPath = nextPath.startsWith("/v2") && !["analyst", "admin"].includes(resolvedRole) ? "/" : nextPath
      window.location.href = targetPath
    } catch {
      setError("Network error while authenticating")
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="min-h-screen bg-background text-foreground px-6 py-8 md:px-10 grid place-items-center">
      <section className="w-full max-w-md rounded-xl border border-white/10 bg-black/40 p-6">
        <p className="text-[11px] uppercase tracking-[0.22em] text-osint-blue mb-2">OSINT NEXUS</p>
        <h1 className="text-3xl font-semibold mb-2">{mode === "login" ? "Login" : "Create Account"}</h1>
        <p className="text-sm text-muted-foreground mb-5">
          {mode === "login"
            ? "Authenticate to access the operations dashboards."
            : "Create an encrypted account record (salted PBKDF2 hash)."}
        </p>

        <form onSubmit={onSubmit} className="space-y-3">
          {mode === "register" && (
            <label className="block">
              <span className="text-xs text-muted-foreground">Role</span>
              <select
                className="mt-1 w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-osint-blue/60"
                value={role}
                onChange={(e) => setRole(e.target.value as Role)}
              >
                <option value="viewer">Viewer</option>
                <option value="analyst">Analyst</option>
                <option value="admin">Admin</option>
              </select>
              <p className="mt-1 text-[10px] text-muted-foreground">Viewer, Analyst, and Admin can all access V2. Admin is only required for the Admin page.</p>
            </label>
          )}

          <label className="block">
            <span className="text-xs text-muted-foreground">Username</span>
            <input
              className="mt-1 w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-osint-blue/60"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="username"
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

          {mode === "register" && (
            <label className="block">
              <span className="text-xs text-muted-foreground">Confirm Password</span>
              <input
                type="password"
                className="mt-1 w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-osint-blue/60"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Confirm password"
              />
            </label>
          )}

          {error ? <p className="text-xs text-osint-red">{error}</p> : null}
          {note ? <p className="text-xs text-osint-green">{note}</p> : null}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded border border-osint-green/40 bg-osint-green/15 py-2 text-sm font-medium text-osint-green hover:bg-osint-green/25 transition-colors disabled:opacity-60"
          >
            {busy ? "Please wait..." : mode === "login" ? "Access Console" : "Create and Login"}
          </button>
        </form>

        <div className="mt-4 text-[11px] text-muted-foreground">
          {mode === "login" ? (
            <button className="underline underline-offset-2" onClick={() => setMode("register")}>
              Need an account? Create one
            </button>
          ) : (
            <button className="underline underline-offset-2" onClick={() => setMode("login")}>
              Already have an account? Login
            </button>
          )}
        </div>
      </section>
    </main>
  )
}
