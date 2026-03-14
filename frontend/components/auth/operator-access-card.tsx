"use client"

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { OsintShield } from "@/components/auth/osint-shield"

type Role = "viewer" | "analyst" | "admin"
type Mode = "login" | "register"
type Phase = "boot" | "ready" | "scanning" | "verified" | "backflip" | "transition" | "failed"
type CheckState = "pending" | "ok" | "fail"

interface CardMeta {
  username: string
  role: Role
  operator_id: string
  theater: string
  issued_at: string
  expires_at: string | null
  expires_in_sec: number
  token_preview: string
  signature_preview: string
  hash_lines: string[]
  grid_bits: number[]
  chain_status: "verified" | "expired" | "invalid"
  fingerprint_id: string
  audit_stamp: string
  security_grade: string
  generated_at: string
}

interface OperatorAccessCardProps {
  nextPath?: string
  displayOnly?: boolean
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

function apiUrl(path: string): string {
  if (API_BASE) return `${API_BASE}${path}`
  return path
}

const ROLE_STYLE: Record<
  Role,
  { text: string; border: string; bg: string; strip: string; label: string; glow: string; backTint: string }
> = {
  viewer: {
    text: "#00ff88",
    border: "rgba(0,255,136,0.45)",
    bg: "rgba(0,255,136,0.10)",
    strip: "linear-gradient(180deg,#00ff88 0%,#33ffc0 45%,#00b4d8 100%)",
    label: "VIEWER",
    glow: "0 0 12px rgba(0,255,136,0.2)",
    backTint: "linear-gradient(135deg,rgba(0,255,136,0.08),rgba(0,180,216,0.04))",
  },
  analyst: {
    text: "#00b4d8",
    border: "rgba(0,180,216,0.45)",
    bg: "rgba(0,180,216,0.10)",
    strip: "linear-gradient(180deg,#00b4d8 0%,#5dd7ff 45%,#00ff88 100%)",
    label: "ANALYST",
    glow: "0 0 12px rgba(0,180,216,0.22)",
    backTint: "linear-gradient(135deg,rgba(0,180,216,0.10),rgba(0,255,136,0.03))",
  },
  admin: {
    text: "#ffbe58",
    border: "rgba(255,190,88,0.55)",
    bg: "rgba(255,190,88,0.14)",
    strip: "linear-gradient(180deg,#ffbe58 0%,#ffa630 45%,#ff1a3c 100%)",
    label: "ADMIN",
    glow: "0 0 14px rgba(255,190,88,0.30)",
    backTint: "linear-gradient(135deg,rgba(255,190,88,0.16),rgba(255,26,60,0.05))",
  },
}

function placeholderBits() {
  return Array.from({ length: 100 }, (_, i) => ((i * 13 + 7) % 5 === 0 ? 1 : 0))
}

function placeholderHashLines() {
  return Array.from({ length: 7 }, (_, i) => `${i}f9d0cc9a6e7f2aa34b92c5e2ad91b0f52a9d2e5acfb1f3e77${i}d4ae02${i}dd`)
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

export function OperatorAccessCard({ nextPath = "/", displayOnly = false }: OperatorAccessCardProps) {
  const [mode, setMode] = useState<Mode>("login")
  const [phase, setPhase] = useState<Phase>(displayOnly ? "ready" : "boot")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [mfaCode, setMfaCode] = useState("")
  const [breakGlassCode, setBreakGlassCode] = useState("")
  const [role, setRole] = useState<Role>("viewer")
  const [resolvedRole, setResolvedRole] = useState<Role>("viewer")
  const [error, setError] = useState("")
  const [note, setNote] = useState("")
  const [scanProgress, setScanProgress] = useState(0)
  const [soundOn, setSoundOn] = useState(true)
  const [cardMeta, setCardMeta] = useState<CardMeta | null>(null)
  const [checks, setChecks] = useState<Record<string, CheckState>>({
    session: displayOnly ? "ok" : "pending",
    backend: displayOnly ? "ok" : "pending",
    ops: displayOnly ? "ok" : "pending",
    models: displayOnly ? "ok" : "pending",
  })
  const [rotateX, setRotateX] = useState(0)
  const [rotateY, setRotateY] = useState(0)
  const [isDragging, setIsDragging] = useState(false)

  const dragState = useRef({ x: 0, y: 0, rx: 0, ry: 0 })
  const audioCtxRef = useRef<AudioContext | null>(null)

  const displayRole: Role = displayOnly ? resolvedRole : mode === "register" ? role : resolvedRole
  const style = ROLE_STYLE[displayRole]
  const operatorText = (username || cardMeta?.username || "AUTHENTICATING...").toUpperCase()
  const allChecksDone = useMemo(() => Object.values(checks).every((s) => s !== "pending"), [checks])
  const displayRedirect = useMemo(() => {
    if (typeof window === "undefined") return "/v2/card"
    const p = window.location.pathname || "/v2/card"
    return p.startsWith("/") ? p : "/v2/card"
  }, [])

  const playBeep = useCallback(
    (freq: number, durationMs: number) => {
      if (!soundOn) return
      try {
        if (!audioCtxRef.current) audioCtxRef.current = new AudioContext()
        const ctx = audioCtxRef.current
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = "square"
        osc.frequency.value = freq
        gain.gain.value = 0.02
        osc.connect(gain)
        gain.connect(ctx.destination)
        osc.start()
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + durationMs / 1000)
        osc.stop(ctx.currentTime + durationMs / 1000)
      } catch {
        // ignore audio issues
      }
    },
    [soundOn]
  )

  const fetchCardMeta = useCallback(async () => {
    try {
      const res = await fetch(apiUrl("/api/auth/card"), { credentials: "include", cache: "no-store" })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data?.card) {
        const c = data.card as CardMeta
        setCardMeta(c)
        setResolvedRole((c.role || "viewer") as Role)
        if (!displayOnly && !username) setUsername(c.username || "")
      }
    } catch {
      // best effort
    }
  }, [displayOnly, username])

  useEffect(() => {
    try {
      const saved = localStorage.getItem("osint_login_sound")
      if (saved === "0") setSoundOn(false)
    } catch {}
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem("osint_login_sound", soundOn ? "1" : "0")
    } catch {}
  }, [soundOn])

  useEffect(() => {
    let cancelled = false
    async function initDisplay() {
      try {
        const sessionRes = await fetch(apiUrl("/api/auth/session"), { credentials: "include", cache: "no-store" })
        const session = await sessionRes.json().catch(() => ({}))
        if (!sessionRes.ok || !session?.authenticated) {
          if (!cancelled) window.location.href = `/login?next=${encodeURIComponent(displayRedirect)}`
          return
        }
        if (cancelled) return
        setUsername(String(session?.username || "operator"))
        setResolvedRole(String(session?.role || "viewer").toLowerCase() as Role)
        void fetchCardMeta()
      } catch {
        if (!cancelled) window.location.href = `/login?next=${encodeURIComponent(displayRedirect)}`
      }
    }
    if (displayOnly) {
      void initDisplay()
      return () => {
        cancelled = true
      }
    }
    return () => {
      cancelled = true
    }
  }, [displayOnly, displayRedirect, fetchCardMeta])

  useEffect(() => {
    if (displayOnly) return
    let cancelled = false
    async function runChecks() {
      const mark = (k: string, v: CheckState) => !cancelled && setChecks((prev) => ({ ...prev, [k]: v }))
      try {
        const sessionRes = await fetch(apiUrl("/api/auth/session"), { credentials: "include", cache: "no-store" })
        const session = await sessionRes.json().catch(() => ({}))
        if (sessionRes.ok && session?.authenticated) {
          const expires = new Date(Date.now() + 1000 * 60 * 60 * 8).toUTCString()
          const sessionRole = String(session?.role || "viewer").toLowerCase() as Role
          const sessionUser = String(session?.username || "user").toLowerCase()
          document.cookie = `osint_session=1; Path=/; Expires=${expires}; SameSite=Lax`
          document.cookie = `osint_role=${sessionRole}; Path=/; Expires=${expires}; SameSite=Lax`
          document.cookie = `osint_user=${sessionUser}; Path=/; Expires=${expires}; SameSite=Lax`
          window.location.href = nextPath || "/"
          return
        }
        mark("session", "ok")
      } catch {
        mark("session", "fail")
      }
      try {
        mark("backend", (await fetch(apiUrl("/api/health"), { cache: "no-store" })).ok ? "ok" : "fail")
      } catch {
        mark("backend", "fail")
      }
      try {
        mark("ops", (await fetch(apiUrl("/api/ops/health"), { cache: "no-store" })).ok ? "ok" : "fail")
      } catch {
        mark("ops", "fail")
      }
      try {
        mark("models", (await fetch(apiUrl("/api/v2/ai/policy"), { cache: "no-store" })).ok ? "ok" : "fail")
      } catch {
        mark("models", "fail")
      }
    }
    void runChecks()
    return () => {
      cancelled = true
    }
  }, [displayOnly, nextPath])

  useEffect(() => {
    if (displayOnly) return
    if (!allChecksDone || phase !== "boot") return
    const t = setTimeout(() => setPhase("ready"), 380)
    return () => clearTimeout(t)
  }, [allChecksDone, displayOnly, phase])

  useEffect(() => {
    if (phase !== "ready" || isDragging) return
    let raf = 0
    let t = 0
    const tick = () => {
      t += 0.015
      setRotateY(Math.sin(t) * 14)
      setRotateX(Math.cos(t * 1.2) * 3)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [phase, isDragging])

  useEffect(() => {
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Escape" && !displayOnly && (phase === "boot" || phase === "ready")) {
        setPhase("ready")
        setError("")
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [displayOnly, phase])

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (phase !== "ready" && phase !== "failed") return
    setIsDragging(true)
    dragState.current = { x: e.clientX, y: e.clientY, rx: rotateX, ry: rotateY }
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return
    const dx = e.clientX - dragState.current.x
    const dy = e.clientY - dragState.current.y
    setRotateY(dragState.current.ry + dx * 0.42)
    setRotateX(dragState.current.rx - dy * 0.25)
  }

  const snapToNearestFace = useCallback(() => {
    const current = rotateY
    const normalized = ((current % 360) + 360) % 360
    const targetNorm = normalized < 90 || normalized >= 270 ? 0 : 180
    const delta = ((targetNorm - normalized + 540) % 360) - 180
    setRotateY(current + delta)
    setRotateX(0)
  }, [rotateY])

  const handlePointerUp = () => {
    setIsDragging(false)
    snapToNearestFace()
  }

  const completeLogin = async (loginJson: Record<string, unknown>) => {
    const sessionRes = await fetch(apiUrl("/api/auth/session"), { credentials: "include", cache: "no-store" })
    const sessionJson = await sessionRes.json().catch(() => ({}))
    const expires = new Date(Date.now() + 1000 * 60 * 60 * 8).toUTCString()
    const finalRole = String(sessionJson?.role || loginJson?.role || role || "viewer").toLowerCase() as Role
    const finalUser = String(sessionJson?.username || loginJson?.username || username).toLowerCase()
    setResolvedRole(finalRole)
    document.cookie = `osint_session=1; Path=/; Expires=${expires}; SameSite=Lax`
    document.cookie = `osint_role=${finalRole}; Path=/; Expires=${expires}; SameSite=Lax`
    document.cookie = `osint_user=${finalUser}; Path=/; Expires=${expires}; SameSite=Lax`
    try { localStorage.setItem("osint_role", finalRole) } catch (_) {}
    try { localStorage.setItem("osint_user", finalUser) } catch (_) {}
    window.dispatchEvent(new CustomEvent("osint:login", { detail: { role: finalRole, username: finalUser } }))
    await fetchCardMeta()

    setScanProgress(100)
    setPhase("verified")
    playBeep(950, 90)
    setTimeout(() => {
      setPhase("backflip")
      setRotateY(-180)
      setTimeout(() => {
        setRotateY(-360)
        setTimeout(() => {
          setPhase("transition")
          setTimeout(() => {
            window.location.href = nextPath || "/"
          }, 760)
        }, 520)
      }, 700)
    }, 420)
  }

  const handlePasskeyLogin = async () => {
    setError("")
    setNote("")
    if (!username.trim()) {
      setError("Username is required for passkey login")
      return
    }
    if (!window.PublicKeyCredential || !navigator.credentials) {
      setError("Passkey not supported in this browser")
      return
    }
    setPhase("scanning")
    setRotateX(0)
    setRotateY(0)
    setScanProgress(0)
    playBeep(700, 80)
    const timer = window.setInterval(() => setScanProgress((v) => Math.min(100, v + 4)), 40)
    try {
      const optsRes = await fetch(apiUrl("/api/auth/passkey/login/options"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username: username.trim() }),
      })
      const optsJson = await optsRes.json().catch(() => ({}))
      if (!optsRes.ok) throw new Error(String(optsJson?.detail || "Passkey challenge failed"))
      const options = optsJson?.options || {}
      const publicKey: PublicKeyCredentialRequestOptions = {
        ...options,
        challenge: b64urlToBytes(String(options.challenge || "")),
        allowCredentials: Array.isArray(options.allowCredentials)
          ? options.allowCredentials.map((c: Record<string, unknown>) => ({
              ...c,
              id: b64urlToBytes(String(c.id || "")),
            }))
          : [],
      }
      let cred: PublicKeyCredential | null = null
      try {
        cred = (await navigator.credentials.get({
          publicKey,
          mediation: "required",
        } as CredentialRequestOptions)) as PublicKeyCredential | null
      } catch {
        cred = (await navigator.credentials.get({ publicKey })) as PublicKeyCredential | null
      }
      if (!cred) throw new Error("Passkey assertion canceled")
      const res = cred.response as AuthenticatorAssertionResponse
      const credential = {
        id: cred.id,
        rawId: bytesToB64url(cred.rawId),
        type: cred.type,
        response: {
          clientDataJSON: bytesToB64url(res.clientDataJSON),
          authenticatorData: bytesToB64url(res.authenticatorData),
          signature: bytesToB64url(res.signature),
          userHandle: res.userHandle ? bytesToB64url(res.userHandle) : null,
        },
      }
      const verify = await fetch(apiUrl("/api/auth/passkey/login/verify"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username: username.trim(), credential }),
      })
      const verifyJson = await verify.json().catch(() => ({}))
      if (!verify.ok) throw new Error(String(verifyJson?.detail || "Passkey verification failed"))
      window.clearInterval(timer)
      await completeLogin(verifyJson as Record<string, unknown>)
    } catch (err) {
      window.clearInterval(timer)
      setScanProgress(0)
      setError(err instanceof Error ? err.message : "Passkey authentication failed")
      setPhase("failed")
      setRotateX(0)
      setRotateY(0)
      playBeep(250, 140)
    }
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError("")
    setNote("")
    if (!username.trim() || !password) {
      setError("Username and password are required")
      setPhase("failed")
      playBeep(280, 120)
      return
    }
    if (mode === "register" && password !== confirm) {
      setError("Password confirmation does not match")
      setPhase("failed")
      playBeep(280, 120)
      return
    }

    setPhase("scanning")
    setRotateX(0)
    setRotateY(0)
    setScanProgress(0)
    playBeep(700, 80)
    const timer = window.setInterval(() => setScanProgress((v) => Math.min(100, v + 4)), 40)

    try {
      if (mode === "register") {
        const reg = await fetch(apiUrl("/api/auth/register"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ username: username.trim(), password, role }),
        })
        const regJson = await reg.json().catch(() => ({}))
        if (!reg.ok) throw new Error(String(regJson?.detail || "Registration failed"))
        setNote("Account created. Verifying identity...")
      }

      const login = await fetch(apiUrl("/api/auth/login"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          username: username.trim(),
          password,
          mfa_code: mfaCode.trim() || undefined,
          break_glass_code: breakGlassCode.trim() || undefined,
        }),
      })
      const loginJson = await login.json().catch(() => ({}))
      if (!login.ok) throw new Error(String(loginJson?.detail || "Invalid credentials"))

      window.clearInterval(timer)
      await completeLogin(loginJson as Record<string, unknown>)
    } catch (err) {
      window.clearInterval(timer)
      setScanProgress(0)
      setError(err instanceof Error ? err.message : "Authentication failed")
      setPhase("failed")
      setRotateX(0)
      setRotateY(0)
      playBeep(250, 140)
    }
  }

  const bits = cardMeta?.grid_bits?.length === 100 ? cardMeta.grid_bits : placeholderBits()
  const hashes = cardMeta?.hash_lines?.length ? cardMeta.hash_lines : placeholderHashLines()
  const cardStatus = (cardMeta?.chain_status === "verified") || phase === "verified" || phase === "backflip" || phase === "transition"
  const chainStatusLabel = cardMeta?.chain_status?.toUpperCase() || (cardStatus ? "VERIFIED" : "VALIDATING...")
  const chainStatusClass =
    chainStatusLabel === "VERIFIED" ? "text-osint-green" : chainStatusLabel === "EXPIRED" ? "text-osint-amber" : "text-osint-red"
  const normalizedY = ((rotateY % 360) + 360) % 360
  const backVisible = normalizedY > 90 && normalizedY < 270

  return (
    <main className="relative min-h-screen bg-background text-foreground overflow-hidden">
      <div className="absolute inset-0 opacity-[0.03] grid-overlay" />
      <div className="absolute inset-0 scanline-overlay pointer-events-none" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(0,180,216,0.05),transparent_65%)] pointer-events-none" />

      <section className="relative z-10 min-h-screen flex flex-col items-center justify-center px-4 py-8">
        <div className="w-full max-w-[390px]">
          {!displayOnly && (
            <div className="rounded-xl border border-white/10 bg-black/30 p-2 mb-3">
              <p className="text-[9px] tracking-[0.2em] uppercase text-muted-foreground mb-2">System Readiness</p>
              <div className="grid grid-cols-2 gap-2 text-[10px]">
                {Object.entries(checks).map(([key, state]) => (
                  <div key={key} className="flex items-center gap-2 text-muted-foreground">
                    <span
                      className="inline-block w-2 h-2 rounded-full"
                      style={{ background: state === "ok" ? "#00ff88" : state === "fail" ? "#ff1a3c" : "rgba(255,255,255,0.3)" }}
                    />
                    <span className="uppercase tracking-[0.14em]">{key}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="relative mx-auto" style={{ width: 360, height: 500, perspective: "1400px" }} onPointerMove={handlePointerMove}>
            <div
              role="presentation"
              onPointerDown={handlePointerDown}
              onPointerUp={handlePointerUp}
              className="absolute inset-0 rounded-2xl select-none"
              style={{
                transformStyle: "preserve-3d",
                transform: `rotateX(${rotateX}deg) rotateY(${rotateY}deg)`,
                transition: isDragging ? "none" : "transform 260ms ease, opacity 400ms ease",
                opacity: phase === "transition" ? 0 : 1,
              }}
            >
              <div
                className="absolute inset-0 rounded-2xl border border-[#1e1e36]/60 bg-gradient-to-br from-[#12121e] via-[#0c0d17] to-[#070710] overflow-hidden"
                style={{
                  boxShadow: `0 0 1px ${style.border}, 0 18px 65px rgba(0,0,0,0.6), ${style.glow}`,
                  transformStyle: "preserve-3d",
                }}
              >
                <div className="absolute inset-0 opacity-[0.04] grid-overlay" />
                <div className="absolute right-0 top-4 bottom-4 w-[6px] rounded-l-sm overflow-hidden">
                  <div className="absolute inset-0 login-holo-shift bg-[length:100%_200%]" style={{ background: style.strip }} />
                  <div className="absolute inset-0 login-holo-sweep opacity-60 bg-[linear-gradient(180deg,transparent_0%,rgba(255,255,255,0.4)_50%,transparent_100%)] bg-[length:100%_42px]" />
                </div>

                {phase === "scanning" && (
                  <div
                    className="absolute left-0 right-0 h-[2px] z-20"
                    style={{ top: `${scanProgress}%`, background: style.text, boxShadow: `0 0 8px ${style.text}` }}
                  />
                )}

                <div
                  className="absolute inset-0 p-5 flex flex-col"
                  style={{
                    visibility: backVisible ? "hidden" : "visible",
                    opacity: backVisible ? 0 : 1,
                    zIndex: backVisible ? 1 : 3,
                  }}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2.5">
                      <OsintShield size={34} />
                      <div>
                        <div className="text-osint-blue font-mono text-[10px] tracking-[0.25em]">OSINT NEXUS</div>
                        <div className="text-[8px] text-muted-foreground font-mono tracking-[0.2em] mt-0.5">SECURE ACCESS</div>
                      </div>
                    </div>
                    <div className="px-2 py-0.5 border border-osint-red/40 bg-osint-red/10 rounded-sm">
                      <span className="text-osint-red font-mono text-[7px] tracking-[0.18em]">NEXUS // COMPARTMENTED</span>
                    </div>
                  </div>

                  <div className="mt-4 h-px bg-gradient-to-r from-transparent via-osint-blue/20 to-transparent" />
                  <div className="mt-5 flex-1">
                    <div className="text-[8px] text-muted-foreground font-mono tracking-[0.3em] mb-1">OPERATOR</div>
                    <div className="text-foreground font-mono text-2xl tracking-[0.16em] leading-tight">{operatorText}</div>
                    <div className="mt-2 text-[10px] text-muted-foreground font-mono tracking-[0.2em]">
                      OP-ID: {cardMeta?.operator_id || "NX-2049-77A"}
                    </div>
                  </div>
                  <div className="mt-3">
                    <div className="text-[7px] text-muted-foreground font-mono tracking-[0.3em] mb-1.5">CLEARANCE LEVEL</div>
                    <div className="inline-flex items-center px-3 py-1 rounded-sm border" style={{ borderColor: style.border, background: style.bg }}>
                      <span className="font-mono text-[11px] tracking-[0.25em]" style={{ color: style.text }}>
                        {style.label}
                      </span>
                    </div>
                  </div>
                  <div className="mt-4 h-px bg-gradient-to-r from-transparent via-osint-blue/20 to-transparent" />
                  <div className="mt-3 flex items-center justify-between">
                    <div>
                      <div className="text-[7px] text-muted-foreground font-mono tracking-[0.2em]">SESSION</div>
                      <div className="text-[10px] text-foreground font-mono tracking-[0.15em]">
                        {cardMeta?.expires_in_sec ? `${Math.max(1, Math.floor(cardMeta.expires_in_sec / 3600))}:00H` : "08:00H"}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-[7px] text-muted-foreground font-mono tracking-[0.2em]">STATUS</div>
                      <div className={`text-[10px] font-mono tracking-[0.15em] ${cardStatus ? "text-osint-green" : "text-muted-foreground"}`}>
                        {cardStatus ? "IDENTITY VERIFIED" : "PENDING"}
                      </div>
                    </div>
                  </div>
                </div>

                <div
                  className="absolute inset-0 p-5 flex flex-col"
                  style={{
                    background: style.backTint,
                    transform: "rotateY(180deg)",
                    visibility: backVisible ? "visible" : "hidden",
                    opacity: backVisible ? 1 : 0,
                    zIndex: backVisible ? 3 : 1,
                  }}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-[8px] text-muted-foreground font-mono tracking-[0.3em]">ENCRYPTED TOKEN BLOCK</div>
                      <div className="mt-1 text-[7px] text-osint-blue/70 font-mono tracking-[0.2em]">HMAC-SHA256 / SESSION DERIVED</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[7px] text-muted-foreground font-mono tracking-[0.2em]">THEATER</div>
                      <div className="text-[10px] text-foreground font-mono tracking-[0.15em]">{cardMeta?.theater || "SECTOR-CENTCOM"}</div>
                    </div>
                  </div>
                  <div className="mt-4 mx-auto w-24 h-24 rounded border border-osint-blue/30 bg-black/35 grid grid-cols-10 gap-[2px] p-[6px] shadow-[inset_0_0_24px_rgba(0,180,216,0.08)]">
                    {bits.map((b, i) => (
                      <div key={i} className={b ? "bg-osint-blue/50 rounded-[1px]" : "bg-transparent"} />
                    ))}
                  </div>
                  <div className="mt-4 p-2 rounded bg-[#0a0a14]/78 border border-[#1e1e36]/40">
                    <div className="text-[7px] text-osint-blue/70 font-mono tracking-[0.2em] mb-1">SHA-256 CHAIN VERIFICATION</div>
                    <div className="space-y-[1px]">
                      {hashes.map((line, i) => (
                        <div key={`${i}-${line.slice(0, 8)}`} className="text-[6px] font-mono text-osint-green/60 truncate">
                          {line}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-[8px] font-mono">
                    <div className="rounded border border-white/10 bg-black/25 p-2">
                      <p className="text-muted-foreground tracking-[0.18em]">TOKEN PREVIEW</p>
                      <p className="text-osint-blue truncate">{cardMeta?.token_preview || "pending"}</p>
                    </div>
                    <div className="rounded border border-white/10 bg-black/25 p-2">
                      <p className="text-muted-foreground tracking-[0.18em]">FINGERPRINT</p>
                      <p className="text-osint-green truncate">{cardMeta?.fingerprint_id || "FP-PENDING"}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center justify-between border-t border-white/10 pt-2">
                    <div>
                      <div className="text-[7px] text-muted-foreground font-mono tracking-[0.2em]">CHAIN STATUS</div>
                      <div className={`text-[10px] font-mono tracking-[0.15em] ${chainStatusClass}`}>
                        {chainStatusLabel}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-[7px] text-muted-foreground font-mono tracking-[0.2em]">SECURITY GRADE</div>
                      <div className="text-[10px] text-foreground font-mono tracking-[0.15em]">{cardMeta?.security_grade || "S3"}</div>
                    </div>
                  </div>
                  <div className="mt-2 text-[8px] text-muted-foreground font-mono tracking-[0.2em] text-center space-y-1">
                    <p>REF: {cardMeta?.operator_id || "NX-2049-77A"} | SIG {cardMeta?.signature_preview || "pending"}</p>
                    <p className="text-osint-amber/80">AUDIT: {cardMeta?.audit_stamp || "PENDING"}</p>
                  </div>
                  <div className="mt-auto text-center border-t border-osint-red/20 pt-2">
                    <span className="text-[6px] text-osint-red/50 font-mono tracking-[0.2em]">
                      UNAUTHORIZED DUPLICATION PROHIBITED // TAMPER EVIDENT
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {displayOnly ? (
            <div className="mt-4 rounded-lg border border-white/10 bg-black/30 p-3 text-[11px] font-mono text-muted-foreground">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="px-2 py-1 rounded border border-osint-blue/40 text-osint-blue"
                  onClick={() => {
                    setRotateX(0)
                    setRotateY(0)
                    void fetchCardMeta()
                  }}
                >
                  Reset / Refresh
                </button>
                <button
                  type="button"
                  className="ml-auto px-2 py-1 rounded border border-white/20"
                  onClick={() => setSoundOn((v) => !v)}
                >
                  SOUND {soundOn ? "ON" : "OFF"}
                </button>
              </div>
              <p className="mt-2 text-[10px] text-muted-foreground/70">Drag card to inspect all angles. Role styling is live from your current authenticated role.</p>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="mt-4 space-y-3">
              <div className="flex gap-2 text-[10px]">
                <button
                  type="button"
                  onClick={() => setMode("login")}
                  className="px-2 py-1 rounded border"
                  style={{ borderColor: mode === "login" ? "rgba(0,180,216,0.5)" : "rgba(255,255,255,0.15)", color: mode === "login" ? "#00b4d8" : "#9fa3b7" }}
                >
                  LOGIN
                </button>
                <button
                  type="button"
                  onClick={() => setMode("register")}
                  className="px-2 py-1 rounded border"
                  style={{ borderColor: mode === "register" ? "rgba(0,180,216,0.5)" : "rgba(255,255,255,0.15)", color: mode === "register" ? "#00b4d8" : "#9fa3b7" }}
                >
                  REGISTER
                </button>
                <button
                  type="button"
                  onClick={() => setSoundOn((v) => !v)}
                  className="ml-auto px-2 py-1 rounded border border-white/15 text-[10px] text-muted-foreground"
                >
                  SOUND {soundOn ? "ON" : "OFF"}
                </button>
              </div>

              {mode === "register" && (
                <label className="block">
                  <span className="text-[9px] text-muted-foreground font-mono tracking-[0.2em]">CLEARANCE</span>
                  <select
                    className="mt-1 w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-osint-blue/60"
                    value={role}
                    onChange={(e) => setRole(e.target.value as Role)}
                    disabled={phase === "scanning" || phase === "transition"}
                  >
                    <option value="viewer">Viewer</option>
                    <option value="analyst">Analyst</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
              )}

              <label className="block">
                <span className="text-[9px] text-muted-foreground font-mono tracking-[0.25em] uppercase">Operator ID</span>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter callsign..."
                  className="mt-1 w-full bg-[#0a0a14] border border-[#1e1e36] rounded px-3 py-2 text-foreground font-mono text-sm tracking-wider placeholder:text-muted-foreground/35 focus:outline-none focus:border-osint-blue/50 focus:ring-1 focus:ring-osint-blue/20 transition-colors"
                  autoComplete="username"
                  disabled={phase === "scanning" || phase === "transition"}
                />
              </label>

              <label className="block">
                <span className="text-[9px] text-muted-foreground font-mono tracking-[0.25em] uppercase">Access Key</span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter passphrase..."
                  className="mt-1 w-full bg-[#0a0a14] border border-[#1e1e36] rounded px-3 py-2 text-foreground font-mono text-sm tracking-wider placeholder:text-muted-foreground/35 focus:outline-none focus:border-osint-blue/50 focus:ring-1 focus:ring-osint-blue/20 transition-colors"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  disabled={phase === "scanning" || phase === "transition"}
                />
              </label>

              {mode === "login" && (
                <label className="block">
                  <span className="text-[9px] text-muted-foreground font-mono tracking-[0.25em] uppercase">MFA Code (If Required)</span>
                  <input
                    type="text"
                    value={mfaCode}
                    onChange={(e) => setMfaCode(e.target.value)}
                    placeholder="123456"
                    className="mt-1 w-full bg-[#0a0a14] border border-[#1e1e36] rounded px-3 py-2 text-foreground font-mono text-sm tracking-wider placeholder:text-muted-foreground/35 focus:outline-none focus:border-osint-blue/50 focus:ring-1 focus:ring-osint-blue/20 transition-colors"
                    autoComplete="one-time-code"
                    disabled={phase === "scanning" || phase === "transition"}
                  />
                </label>
              )}

              {mode === "login" && (
                <label className="block">
                  <span className="text-[9px] text-muted-foreground font-mono tracking-[0.25em] uppercase">Break-Glass (Admin Emergency)</span>
                  <input
                    type="password"
                    value={breakGlassCode}
                    onChange={(e) => setBreakGlassCode(e.target.value)}
                    placeholder="Optional emergency code"
                    className="mt-1 w-full bg-[#0a0a14] border border-[#1e1e36] rounded px-3 py-2 text-foreground font-mono text-sm tracking-wider placeholder:text-muted-foreground/35 focus:outline-none focus:border-osint-amber/50 focus:ring-1 focus:ring-osint-amber/20 transition-colors"
                    autoComplete="off"
                    disabled={phase === "scanning" || phase === "transition"}
                  />
                </label>
              )}

              {mode === "register" && (
                <label className="block">
                  <span className="text-[9px] text-muted-foreground font-mono tracking-[0.25em] uppercase">Confirm Key</span>
                  <input
                    type="password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    placeholder="Confirm passphrase..."
                    className="mt-1 w-full bg-[#0a0a14] border border-[#1e1e36] rounded px-3 py-2 text-foreground font-mono text-sm tracking-wider placeholder:text-muted-foreground/35 focus:outline-none focus:border-osint-blue/50 focus:ring-1 focus:ring-osint-blue/20 transition-colors"
                    autoComplete="new-password"
                    disabled={phase === "scanning" || phase === "transition"}
                  />
                </label>
              )}

              {error ? <p className="text-[11px] text-osint-red">{error}</p> : null}
              {note ? <p className="text-[11px] text-osint-green">{note}</p> : null}

              <button
                type="submit"
                disabled={phase === "scanning" || phase === "transition"}
                className="w-full py-2.5 rounded font-mono text-xs tracking-[0.2em] uppercase transition-all border disabled:opacity-60 disabled:cursor-not-allowed bg-osint-blue/10 border-osint-blue/35 text-osint-blue hover:bg-osint-blue/20 hover:border-osint-blue/55"
              >
                {phase === "scanning" ? "AUTHENTICATING..." : phase === "verified" || phase === "backflip" ? "IDENTITY VERIFIED" : mode === "login" ? "ACCESS CONSOLE" : "CREATE AND ACCESS"}
              </button>

              {mode === "login" && (
                <button
                  type="button"
                  disabled={phase === "scanning" || phase === "transition"}
                  onClick={() => void handlePasskeyLogin()}
                  className="w-full py-2 rounded font-mono text-[11px] tracking-[0.2em] uppercase transition-all border disabled:opacity-60 disabled:cursor-not-allowed bg-osint-green/10 border-osint-green/35 text-osint-green hover:bg-osint-green/20 hover:border-osint-green/55"
                >
                  ADMIN PASSKEY SIGN-IN
                </button>
              )}

              <div className="text-center text-[8px] text-muted-foreground/50 font-mono tracking-[0.2em]">
                ESC TO SKIP READINESS // DRAG CARD TO INSPECT 360
              </div>
            </form>
          )}
        </div>
      </section>
    </main>
  )
}
