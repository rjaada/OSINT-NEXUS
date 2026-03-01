import { NextRequest, NextResponse } from "next/server"

function isPublicPath(pathname: string): boolean {
  if (pathname === "/login") return true
  if (pathname.startsWith("/_next")) return true
  if (pathname.startsWith("/favicon")) return true
  if (pathname.startsWith("/icon")) return true
  if (pathname.startsWith("/apple-icon")) return true
  if (pathname.startsWith("/media")) return true
  return false
}

export function proxy(req: NextRequest) {
  const { pathname, search } = req.nextUrl
  if (isPublicPath(pathname)) return NextResponse.next()

  const session = req.cookies.get("osint_session")?.value
  const signedSession = req.cookies.get("osint_auth")?.value
  const role = req.cookies.get("osint_role")?.value || "viewer"
  if (session === "1" || Boolean(signedSession)) {
    const isV2AdminPath = pathname === "/v2/admin" || pathname.startsWith("/v2/admin/") || pathname === "/v2/ar/admin" || pathname.startsWith("/v2/ar/admin/")
    if (isV2AdminPath && role !== "admin") {
      const deniedUrl = req.nextUrl.clone()
      deniedUrl.pathname = pathname.startsWith("/v2/ar") ? "/v2/ar" : "/v2"
      deniedUrl.search = "?access=admin_denied"
      return NextResponse.redirect(deniedUrl)
    }
    // v2 is analyst/admin only; v1 remains available for any authenticated role.
    if ((pathname === "/v2" || pathname.startsWith("/v2/")) && !["analyst", "admin"].includes(role)) {
      const deniedUrl = req.nextUrl.clone()
      deniedUrl.pathname = "/"
      deniedUrl.search = "?access=v2_denied"
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
