/** Browser requests use the same-origin proxy unless explicitly configured. */
export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/+$/, "")

export function websocketBase(): string {
  const explicit = process.env.NEXT_PUBLIC_WS_URL
  if (explicit) return explicit.replace(/\/+$/, "")
  if (typeof window === "undefined") return ""
  const url = new URL(API_BASE || window.location.origin, window.location.origin)
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
  return url.href.replace(/\/+$/, "")
}
