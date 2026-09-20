import { NextRequest, NextResponse } from "next/server"
import { chromium } from "playwright"
import type { IntelligenceReportData } from "@/components/briefs/report/types"
import { buildReportPdfFileName } from "@/lib/briefs-pdf-filename"
import { deletePdfPayload, putPdfPayload } from "@/lib/briefs-pdf-store"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

const PDF_TIMEOUT_MS = 90_000

export async function POST(req: NextRequest) {
  if (!req.cookies.get("osint_auth")?.value) {
    return NextResponse.json({ error: "Authentication required" }, { status: 401 })
  }
  const csrf = req.cookies.get("osint_csrf")?.value
  if (!csrf || req.headers.get("x-csrf-token") !== csrf) {
    return NextResponse.json({ error: "CSRF validation failed" }, { status: 403 })
  }
  try {
    const backend = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000"
    const auth = await fetch(`${backend}/api/auth/session`, {
      headers: { cookie: req.headers.get("cookie") || "" },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    })
    if (!auth.ok) return NextResponse.json({ error: "Authentication service unavailable" }, { status: 503 })
    const session = await auth.json()
    if (!session.authenticated) return NextResponse.json({ error: "Authentication required" }, { status: 401 })
    if (!["analyst", "admin"].includes(session.role)) {
      return NextResponse.json({ error: "Analyst or admin role required" }, { status: 403 })
    }
  } catch {
    return NextResponse.json({ error: "Authentication service unavailable" }, { status: 503 })
  }
  let key = ""
  let browser: Awaited<ReturnType<typeof chromium.launch>> | null = null
  try {
    const payload = (await req.json()) as IntelligenceReportData
    if (!payload || typeof payload !== "object" || !payload.title || !payload.docId) {
      return NextResponse.json({ error: "Invalid payload" }, { status: 400 })
    }

    key = await putPdfPayload(payload)
    const origin = process.env.PDF_RENDER_ORIGIN || `http://127.0.0.1:${process.env.PORT || "3000"}`
    const printUrl = `${origin}/v2/briefs/print?pdfKey=${encodeURIComponent(key)}`

    browser = await chromium.launch({
      headless: true,
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    })
    const context = await browser.newContext({
      viewport: { width: 1280, height: 1800 },
    })
    const page = await context.newPage()

    await page.goto(printUrl, { waitUntil: "networkidle", timeout: PDF_TIMEOUT_MS })
    await page.waitForSelector("#pdf-render-root[data-pdf-render='1']", { timeout: PDF_TIMEOUT_MS })
    await page.waitForSelector("#intelligence-report", { timeout: PDF_TIMEOUT_MS })

    const renderCheck = await page.evaluate(() => {
      const root = document.querySelector("#pdf-render-root[data-pdf-render='1']")
      const report = document.querySelector("#intelligence-report")
      const bodyText = (document.body?.innerText || "").slice(0, 1200)
      return {
        href: location.href,
        title: document.title,
        hasRoot: Boolean(root),
        hasReport: Boolean(report),
        hasSystemInit: bodyText.includes("SYSTEM INITIALIZATION"),
        hasSection1: bodyText.includes("SECTION 1"),
        bodyPreview: bodyText.slice(0, 240),
      }
    })
    if (!renderCheck.hasRoot || !renderCheck.hasReport || renderCheck.hasSystemInit || !renderCheck.hasSection1) {
      throw new Error(`Unexpected print DOM state: ${JSON.stringify(renderCheck)}`)
    }
    await page.emulateMedia({ media: "screen" })

    const pdfBuffer = await page.pdf({
      format: "A4",
      printBackground: true,
      margin: { top: "0", right: "0", bottom: "0", left: "0" },
      preferCSSPageSize: true,
      tagged: true,
    })

    await context.close()

    const fileName = buildReportPdfFileName(payload)
    return new NextResponse(pdfBuffer, {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename=\"${fileName}\"`,
        "Cache-Control": "no-store",
      },
    })
  } catch (error) {
    console.error("[PDF][PLAYWRIGHT] render failed", error)
    try {
      return NextResponse.json(
        { error: "Pixel PDF render failed", detail: String((error as Error)?.message || error) },
        { status: 500 },
      )
    } catch {
      // ignore
    }
    return NextResponse.json({ error: "Pixel PDF render failed" }, { status: 500 })
  } finally {
    if (browser) {
      await browser.close().catch(() => {})
    }
    if (key) {
      await deletePdfPayload(key)
    }
  }
}
