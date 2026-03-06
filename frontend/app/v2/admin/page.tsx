"use client"

import { useEffect, useMemo, useState } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"
import { csrfHeaders } from "@/lib/security"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""
function apiUrl(path: string): string {
  if (API_BASE) return `${API_BASE}${path}`
  return path
}

type Role = "viewer" | "analyst" | "admin"

interface AdminUser {
  username: string
  role: Role
  created_at: string
  updated_at: string
}

function b64urlToBytes(input: string): Uint8Array {
  const base64 = input.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (input.length % 4 || 4)) % 4)
  const binary = atob(base64)
  const out = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i)
  return out
}

function bytesToB64url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let binary = ""
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
}

export default function AdminUsersPage() {
  const [role, setRole] = useState<Role>("viewer")
  const [actor, setActor] = useState("")
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState("")
  const [busyUser, setBusyUser] = useState("")
  const [passkeyEnabled, setPasskeyEnabled] = useState(false)
  const [passkeyCount, setPasskeyCount] = useState(0)

  useEffect(() => {
    const roleCookie = document.cookie.split("; ").find((x) => x.startsWith("osint_role="))
    const currentRole = (roleCookie ? decodeURIComponent(roleCookie.split("=")[1]) : "viewer").toLowerCase() as Role
    setRole(currentRole)
  }, [])

  const loadUsers = async () => {
    setLoading(true)
    setMsg("")
    try {
      const res = await fetch(apiUrl("/api/admin/users"), { credentials: "include", cache: "no-store" })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setMsg(data?.detail || "Failed to load users")
        return
      }
      setUsers(Array.isArray(data?.items) ? data.items : [])
      setActor(String(data?.actor || ""))
    } catch (_) {
      setMsg("Network error while loading users")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (role !== "admin") return
    void loadUsers()
  }, [role])

  const loadPasskeyStatus = async () => {
    try {
      const res = await fetch(apiUrl("/api/auth/passkey/status"), { credentials: "include", cache: "no-store" })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) return
      setPasskeyEnabled(Boolean(data?.enabled))
      setPasskeyCount(Number(data?.count || 0))
    } catch {
      // best effort
    }
  }

  useEffect(() => {
    if (role !== "admin") return
    void loadPasskeyStatus()
  }, [role])

  useEffect(() => {
    if (role !== "admin") return
    const loadSession = async () => {
      try {
        const res = await fetch(apiUrl("/api/auth/session"), { credentials: "include", cache: "no-store" })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) return
        if (data?.authenticated && data?.username) {
          setActor(String(data.username))
        }
      } catch {
        // best effort
      }
    }
    void loadSession()
  }, [role])

  const enrollPasskey = async () => {
    if (!window.PublicKeyCredential || !navigator.credentials) {
      setMsg("Passkey not supported in this browser")
      return
    }
    setMsg("")
    try {
      const optsRes = await fetch(apiUrl("/api/auth/passkey/register/options"), {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "include",
      })
      const optsJson = await optsRes.json().catch(() => ({}))
      if (!optsRes.ok) {
        setMsg(optsJson?.detail || "Failed to start passkey enrollment")
        return
      }
      const options = optsJson?.options || {}
      const publicKey: PublicKeyCredentialCreationOptions = {
        ...options,
        challenge: b64urlToBytes(String(options.challenge || "")),
        user: {
          ...(options.user || {}),
          id: b64urlToBytes(String(options?.user?.id || "")),
        },
        excludeCredentials: Array.isArray(options.excludeCredentials)
          ? options.excludeCredentials.map((c: Record<string, unknown>) => ({
              ...c,
              id: b64urlToBytes(String(c.id || "")),
            }))
          : [],
      }
      const cred = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential | null
      if (!cred) {
        setMsg("Passkey enrollment cancelled")
        return
      }
      const res = cred.response as AuthenticatorAttestationResponse
      const credential = {
        id: cred.id,
        rawId: bytesToB64url(cred.rawId),
        type: cred.type,
        response: {
          clientDataJSON: bytesToB64url(res.clientDataJSON),
          attestationObject: bytesToB64url(res.attestationObject),
        },
      }
      const verify = await fetch(apiUrl("/api/auth/passkey/register/verify"), {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        credentials: "include",
        body: JSON.stringify({ credential, label: "admin" }),
      })
      const verifyJson = await verify.json().catch(() => ({}))
      if (!verify.ok) {
        setMsg(verifyJson?.detail || "Passkey enrollment failed")
        return
      }
      setMsg("Passkey enrolled successfully")
      void loadPasskeyStatus()
    } catch {
      setMsg("Passkey enrollment failed")
    }
  }

  const adminsCount = useMemo(() => users.filter((u) => u.role === "admin").length, [users])
  const actorNorm = actor.trim().toLowerCase()

  const setUserRole = async (username: string, nextRole: Role) => {
    setBusyUser(username)
    setMsg("")
    try {
      const res = await fetch(apiUrl(`/api/admin/users/${encodeURIComponent(username)}/role`), {
        method: "PATCH",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        credentials: "include",
        body: JSON.stringify({ role: nextRole }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setMsg(data?.detail || "Role update failed")
        return
      }
      setUsers((prev) => prev.map((u) => (u.username === username ? { ...u, role: nextRole, updated_at: String(data?.updated_at || u.updated_at) } : u)))
      setMsg(`Updated ${username} to ${nextRole}`)
    } catch (_) {
      setMsg("Network error while updating role")
    } finally {
      setBusyUser("")
    }
  }

  const deleteUser = async (username: string) => {
    const ok = window.confirm(`Delete user "${username}"? This action cannot be undone.`)
    if (!ok) return
    setBusyUser(username)
    setMsg("")
    try {
      const res = await fetch(apiUrl(`/api/admin/users/${encodeURIComponent(username)}`), {
        method: "DELETE",
        headers: csrfHeaders(),
        credentials: "include",
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setMsg(data?.detail || "Delete failed")
        return
      }
      setUsers((prev) => prev.filter((u) => u.username !== username))
      setMsg(`Deleted ${username}`)
    } catch (_) {
      setMsg("Network error while deleting user")
    } finally {
      setBusyUser("")
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar />
      <CommandNav />
      <main className="px-4 md:px-6 py-5">
        <div className="max-w-6xl mx-auto">
          <header className="mb-4">
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-purple mb-1">Admin</p>
            <h1 className="text-2xl md:text-3xl font-semibold">User Role Management</h1>
            <p className="text-xs text-muted-foreground mt-2">Manage access levels for viewer, analyst, and admin users.</p>
          </header>

          {role !== "admin" ? (
            <section className="rounded-lg border border-osint-red/40 bg-osint-red/10 p-4 text-sm text-osint-red">
              Admin access required.
            </section>
          ) : (
            <section className="rounded-lg border border-white/10 bg-black/30 p-3">
              <div className="flex items-center gap-2 mb-3 text-[11px]">
                <span className="text-muted-foreground">Signed in as:</span>
                <span className="text-osint-green">{actor || "unknown"}</span>
                <span className="ml-2 text-muted-foreground">Admins:</span>
                <span className="text-osint-blue">{adminsCount}</span>
                <span className="ml-2 text-muted-foreground">Passkeys:</span>
                <span className={passkeyEnabled ? "text-osint-green" : "text-osint-amber"}>{passkeyCount}</span>
                <button
                  className="text-[10px] px-2 py-1 rounded border border-osint-green/40 text-osint-green"
                  onClick={() => void enrollPasskey()}
                >
                  Enroll Passkey
                </button>
                <button
                  className="ml-auto text-[10px] px-2 py-1 rounded border border-osint-blue/40 text-osint-blue"
                  onClick={() => void loadUsers()}
                  disabled={loading}
                >
                  {loading ? "Refreshing..." : "Refresh"}
                </button>
              </div>

              {msg ? <p className="text-xs text-osint-amber mb-2">{msg}</p> : null}

              <div className="grid gap-2">
                {users.map((u) => (
                  <article key={u.username} className="rounded border border-white/10 p-2 grid md:grid-cols-5 gap-2 items-center">
                    <div>
                      <p className="text-[12px] text-[#e0e0ef]">{u.username}</p>
                      <p className="text-[10px] text-muted-foreground">updated: {u.updated_at}</p>
                    </div>
                    <p className="text-[11px] text-muted-foreground">created: {u.created_at}</p>
                    <p className="text-[11px] text-muted-foreground">current: <span className="text-osint-green">{u.role}</span></p>
                    <div className="md:col-span-2 flex gap-1 flex-wrap">
                      {(["viewer", "analyst", "admin"] as Role[]).map((r) => (
                        <button
                          key={r}
                          disabled={busyUser === u.username || u.role === r}
                          onClick={() => void setUserRole(u.username, r)}
                          className="text-[10px] px-2 py-1 rounded border disabled:opacity-50"
                          style={{
                            borderColor: u.role === r ? "rgba(0,255,136,0.45)" : "rgba(255,255,255,0.2)",
                            color: u.role === r ? "#00ff88" : "#cfd2df",
                            background: u.role === r ? "rgba(0,255,136,0.08)" : "transparent",
                          }}
                        >
                          {busyUser === u.username ? "..." : r}
                        </button>
                      ))}
                      <button
                        disabled={busyUser === u.username || u.username.toLowerCase() === actorNorm}
                        onClick={() => void deleteUser(u.username)}
                        className="text-[10px] px-2 py-1 rounded border disabled:opacity-50 border-osint-red/40 text-osint-red bg-osint-red/10"
                        title={u.username.toLowerCase() === actorNorm ? "You cannot delete your own account" : "Delete user"}
                      >
                        {busyUser === u.username ? "..." : "delete"}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  )
}
