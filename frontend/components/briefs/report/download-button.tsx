"use client"

import { useCallback, useState } from "react"
import { Download, Loader2 } from "lucide-react"
import { toast } from "sonner"
import type { IntelligenceReportData } from "./types"
import { buildReportPdfFileName } from "@/lib/briefs-pdf-filename"

function parseAttachmentFilename(contentDisposition: string | null): string | null {
  if (!contentDisposition) return null
  const match = contentDisposition.match(/filename=\"?([^\";]+)\"?/)
  return match?.[1] || null
}

export function DownloadButton({ data }: { data: IntelligenceReportData }) {
  const [loading, setLoading] = useState(false)

  const downloadBlob = useCallback((blob: Blob, fileName: string) => {
    const objectUrl = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = objectUrl
    a.download = fileName
    a.rel = "noopener"
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
  }, [])

  const handleDownload = useCallback(async () => {
    setLoading(true)
    try {
      // Single mode: pixel-perfect server-side Chromium PDF.
      const serverRes = await fetch("/api/v2/briefs/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      })

      if (!serverRes.ok) {
        const body = await serverRes.text().catch(() => "")
        throw new Error(body || `Server PDF failed with status ${serverRes.status}`)
      }

      const blob = await serverRes.blob()
      if (!blob || blob.size <= 0) throw new Error("Server PDF blob is empty")
      const serverName = parseAttachmentFilename(serverRes.headers.get("content-disposition"))
      downloadBlob(blob, serverName || buildReportPdfFileName(data))
      toast.success("Classified report downloaded")
    } catch (err) {
      console.error("PDF generation failed:", err)
      toast.error("PDF download failed. Check browser console for details.")
    } finally {
      setLoading(false)
    }
  }, [data, downloadBlob])

  return (
    <button
      type="button"
      onClick={handleDownload}
      disabled={loading}
      className="group flex items-center gap-2.5 border-2 border-red-official/30 bg-banner-bg px-5 py-3 font-mono text-xs font-bold tracking-wider text-red-official transition-all hover:border-red-official hover:bg-red-official/10 disabled:cursor-wait disabled:opacity-60"
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <Download className="h-4 w-4 transition-transform group-hover:-translate-y-0.5" />
      )}
      {loading ? "GENERATING PDF..." : "DOWNLOAD CLASSIFIED REPORT"}
    </button>
  )
}
