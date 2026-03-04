"use client"

import { useState, useCallback } from "react"
import { FolderScene } from "./folder-scene"
import { PapersScene } from "./papers-scene"
import { DocumentZoom } from "./document-zoom"
import { IntelligenceReport } from "@/components/briefs/report/intelligence-report"
import { DownloadButton } from "@/components/briefs/report/download-button"
import type { IntelligenceReportData } from "@/components/briefs/report/types"

type Scene = "folder" | "papers" | "zoom" | "report"

interface CinematicSequenceProps {
  data: IntelligenceReportData
  loading: boolean
  error: string
  offlineFallback: boolean
}

export function CinematicSequence({ data, loading, error, offlineFallback }: CinematicSequenceProps) {
  const [scene, setScene] = useState<Scene>("folder")

  const handleFolderClick = useCallback(() => {
    setScene("papers")
  }, [])

  const handleSelectDocument = useCallback(() => {
    setScene("zoom")
  }, [])

  const handleZoomComplete = useCallback(() => {
    setScene("report")
  }, [])

  const handleGoBack = useCallback(() => {
    setScene("papers")
  }, [])

  if (scene === "folder") {
    return <FolderScene onOpen={handleFolderClick} />
  }

  if (scene === "papers") {
    return <PapersScene onSelectDocument={handleSelectDocument} />
  }

  if (scene === "zoom") {
    return <DocumentZoom onComplete={handleZoomComplete} />
  }

  // Report scene
  return (
    <main
      className="min-h-screen px-4 py-10"
      style={{
        background: "linear-gradient(180deg, #1a1a1e 0%, #121214 100%)",
        animation: "fade-in 0.8s ease-out",
      }}
    >
      {/* Top controls */}
      <div className="mx-auto mb-6 flex max-w-[900px] items-center justify-between">
        <div className="flex items-center gap-6">
          <button
            onClick={handleGoBack}
            className="group flex items-center gap-2 font-mono text-[11px] tracking-wider text-[#c9a96e]/60 transition-colors hover:text-[#c9a96e]"
            aria-label="Return to document selection"
          >
            <svg
              className="h-4 w-4 transition-transform group-hover:-translate-x-1"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            BACK TO FILES
          </button>
          <div>
            <h1 className="font-[var(--font-stencil)] text-lg tracking-wider text-[#cc0000]">
              OSINT NEXUS
            </h1>
            <p className="font-mono text-[11px] tracking-wide text-[#666]">
              {"AI-GENERATED INTELLIGENCE BRIEF // DOCUMENT VIEWER"}
            </p>
          </div>
        </div>
        <DownloadButton data={data} />
      </div>

      {loading ? (
        <div className="mx-auto mb-4 max-w-[900px] border border-[#cc0000]/40 bg-[#120d0d] px-4 py-3 font-mono text-xs tracking-wide text-[#d9b3b3]">
          Generating intelligence brief via AI analyst...
        </div>
      ) : null}
      {!loading && error ? (
        <div className="mx-auto mb-4 max-w-[900px] border border-[#cc0000]/40 bg-[#120d0d] px-4 py-3 font-mono text-xs tracking-wide text-[#d9b3b3]">
          {offlineFallback ? "AI analyst offline. Displaying last cached brief." : error}
        </div>
      ) : null}

      {/* Report document */}
      <IntelligenceReport data={data} />

      {/* Bottom spacer */}
      <div className="h-10" />
    </main>
  )
}
