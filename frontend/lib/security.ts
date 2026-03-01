export function readCookie(name: string): string {
  if (typeof document === "undefined") return ""
  const row = document.cookie.split("; ").find((x) => x.startsWith(`${name}=`))
  return row ? decodeURIComponent(row.split("=")[1]) : ""
}

export function csrfHeaders(base: Record<string, string> = {}): Record<string, string> {
  const csrf = readCookie("osint_csrf")
  return csrf ? { ...base, "x-csrf-token": csrf } : base
}
