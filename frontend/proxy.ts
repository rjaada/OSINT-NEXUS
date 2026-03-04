import { NextRequest, NextResponse } from "next/server"

function isPublicPath(pathname: string): boolean {
  if (pathname === "/login") return true
  if (pathname.startsWith("/_next")) return true
  if (pathname.startsWith("/favicon")) return true
  if (pathname.startsWith("/icon")) return true
  if (pathname.startsWith("/apple-icon")) return true
  if (pathname.startsWith("/fonts")) return true
  if (pathname.startsWith("/v2/briefs/print")) return true
  if (pathname.startsWith("/media")) return true
  return false
}

async function resolveAuthFromBackend(req: NextRequest): Promise<{ authenticated: boolean; role: string } | null> {
  const cookieHeader = req.headers.get("cookie") || ""
  if (!cookieHeader) return null
  const baseUrls = [
    process.env.BACKEND_INTERNAL_URL || "",
    "http://backend:8000",
    "http://localhost:8000",
  ].filter(Boolean)
  for (const baseUrl of baseUrls) {
    try {
      const res = await fetch(`${baseUrl}/api/auth/session`, {
        method: "GET",
        headers: { cookie: cookieHeader },
        cache: "no-store",
      })
      if (!res.ok) continue
      const data = await res.json().catch(() => null)
      if (!data || typeof data !== "object") continue
      return {
        authenticated: Boolean((data as { authenticated?: unknown }).authenticated),
        role: String((data as { role?: unknown }).role || "viewer").toLowerCase(),
      }
    } catch {
      continue
    }
  }
  return null
}

export async function proxy(req: NextRequest) {
  const { pathname, search } = req.nextUrl
  if (isPublicPath(pathname)) return NextResponse.next()

  const session = req.cookies.get("osint_session")?.value
  const signedSession = req.cookies.get("osint_auth")?.value
  const cookieRole = (req.cookies.get("osint_role")?.value || "viewer").toLowerCase()

  const backendAuth = signedSession ? await resolveAuthFromBackend(req) : null
  const authenticated = Boolean((session === "1" || Boolean(signedSession)) && (backendAuth ? backendAuth.authenticated : true))
  const role = backendAuth?.role || cookieRole

  if (authenticated) {
    const isV2AdminPath = pathname === "/v2/admin" || pathname.startsWith("/v2/admin/") || pathname === "/v2/ar/admin" || pathname.startsWith("/v2/ar/admin/")
    if (isV2AdminPath && role !== "admin") {
      const deniedUrl = req.nextUrl.clone()
      deniedUrl.pathname = pathname.startsWith("/v2/ar") ? "/v2/ar" : "/v2"
      deniedUrl.search = "?access=admin_denied"
      return NextResponse.redirect(deniedUrl)
    }
    return NextResponse.next()
  }

  const loginUrl = req.nextUrl.clone()
  loginUrl.pathname = "/login"
  loginUrl.search = `?next=${encodeURIComponent(pathname + search)}`
  return NextResponse.redirect(loginUrl)
}

export const config = {
  matcher: ["/((?!api).*)"],
}
