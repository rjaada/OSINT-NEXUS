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
  const role = req.cookies.get("osint_role")?.value || "viewer"
  if (session === "1") {
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
