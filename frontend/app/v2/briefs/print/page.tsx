import { IntelligenceReport } from "@/components/briefs/report/intelligence-report"
import { getPdfPayload } from "@/lib/briefs-pdf-store"

export const dynamic = "force-dynamic"

interface PrintPageProps {
  searchParams: Promise<{ pdfKey?: string }>
}

export default async function BriefsPrintPage({ searchParams }: PrintPageProps) {
  const params = await searchParams
  const key = (params?.pdfKey || "").trim()
  const data = key ? await getPdfPayload(key) : null

  if (!data) {
    return (
      <main className="min-h-screen bg-[#1a1a1e] px-6 py-10 text-[#d7d7df]">
        <div className="mx-auto max-w-[900px] border border-[#cc0000]/40 bg-[#120d0d] px-4 py-3 font-mono text-xs tracking-wide">
          PDF render session expired. Generate again from the briefs page.
        </div>
      </main>
    )
  }

  return (
    <main
      className="min-h-screen bg-[#1a1a1e] px-4 py-8"
      style={{
        background: "linear-gradient(180deg, #1a1a1e 0%, #121214 100%)",
      }}
    >
      <div id="pdf-render-root" data-pdf-render="1" data-doc-id={data.docId}>
        <IntelligenceReport data={data} />
      </div>
    </main>
  )
}
