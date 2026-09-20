"use client"

import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react"

interface AuthState {
  role: string
  username: string
  authenticated: boolean
  loading: boolean
}

interface AuthContextValue extends AuthState {
  refresh: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue>({
  role: "viewer",
  username: "user",
  authenticated: false,
  loading: true,
  refresh: async () => {},
  logout: async () => {},
})

const API_BASE = typeof process !== "undefined" ? (process.env.NEXT_PUBLIC_API_URL ?? "") : ""
function apiUrl(path: string) { return API_BASE ? `${API_BASE}${path}` : path }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    role: "viewer",
    username: "user",
    authenticated: false,
    loading: true,
  })

  const fetchSession = useCallback(async () => {
    try {
      const res = await fetch(apiUrl("/api/auth/session"), { credentials: "include", cache: "no-store" })
      if (!res.ok) {
        setState({ role: "viewer", username: "user", authenticated: false, loading: false })
        try { localStorage.removeItem("osint_role"); localStorage.removeItem("osint_user") } catch (_) {}
        return
      }
      const s = await res.json()
      if (!s?.authenticated) {
        setState({ role: "viewer", username: "user", authenticated: false, loading: false })
        try { localStorage.removeItem("osint_role"); localStorage.removeItem("osint_user") } catch (_) {}
        return
      }
      const role = String(s.role || "viewer").toLowerCase()
      const username = String(s.username || "user")
      setState({ role, username, authenticated: true, loading: false })
      try { localStorage.setItem("osint_role", role); localStorage.setItem("osint_user", username) } catch (_) {}
    } catch (_) {
      try { localStorage.removeItem("osint_role"); localStorage.removeItem("osint_user") } catch (_) {}
      setState({ role: "viewer", username: "user", authenticated: false, loading: false })
    }
  }, [])

  useEffect(() => {
    fetchSession()

    // Login events are hints only; authorization state always comes from the server.
    const onLogin = () => {
      void fetchSession()
    }
    window.addEventListener("osint:login", onLogin)
    return () => window.removeEventListener("osint:login", onLogin)
  }, [fetchSession])

  const logout = useCallback(async () => {
    try {
      const { csrfHeaders } = await import("@/lib/security")
      const response = await fetch(apiUrl("/api/auth/logout"), {
        method: "POST", credentials: "include",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
      })
      if (!response.ok) return
    } catch (_) {
      return
    }
    const exp = "Thu, 01 Jan 1970 00:00:00 GMT"
    for (const name of ["osint_session", "osint_role", "osint_user", "osint_csrf", "osint_auth"]) {
      document.cookie = `${name}=; Path=/; Expires=${exp}; SameSite=Lax`
    }
    try { localStorage.removeItem("osint_role"); localStorage.removeItem("osint_user") } catch (_) {}
    setState({ role: "viewer", username: "user", authenticated: false, loading: false })
    window.location.href = "/login"
  }, [])

  return (
    <AuthContext.Provider value={{ ...state, refresh: fetchSession, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
