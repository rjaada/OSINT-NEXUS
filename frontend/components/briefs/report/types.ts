export type ThreatLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
export type ReportType = "INTSUM" | "SITREP" | "FLASH" | "OSINT-BRIEF"

export interface BriefMetadata {
  generatedAt: string
  analyst: string
  sourcesActive: number
  confidence: "LOW" | "MEDIUM" | "HIGH"
  reportId: string
}

export interface DevelopmentItem {
  priority: ThreatLevel
  text: string
  sources: string[]
}

export interface ThreatData {
  level: ThreatLevel
  score: number
}

export interface IntelligenceReportData {
  reportType: ReportType
  title: string
  docId: string
  classification: string
  distribution: string
  metadata: BriefMetadata
  executiveSummary: string[]
  keyDevelopments: DevelopmentItem[]
  threat: ThreatData
  analystNotes: string[]
}
