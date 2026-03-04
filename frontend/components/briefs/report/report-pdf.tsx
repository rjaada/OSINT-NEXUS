"use client"

import {
  Document,
  Font,
  Page,
  StyleSheet,
  Text,
  View,
  pdf,
} from "@react-pdf/renderer"
import type { IntelligenceReportData } from "./types"

let fontsRegistered = false

function fontUrl(path: string): string {
  if (typeof window !== "undefined" && window.location?.origin) {
    return `${window.location.origin}${path}`
  }
  return path
}

function ensurePdfFonts() {
  if (fontsRegistered) return
  Font.register({
    family: "IBMPlexSerif",
    fonts: [
      {
        src: fontUrl("/fonts/IBMPlexSerif-Regular.ttf"),
        fontWeight: 400,
      },
      {
        src: fontUrl("/fonts/IBMPlexSerif-Bold.ttf"),
        fontWeight: 700,
      },
    ],
  })
  Font.register({
    family: "IBMPlexMono",
    fonts: [
      {
        src: fontUrl("/fonts/IBMPlexMono-Regular.ttf"),
        fontWeight: 400,
      },
      {
        src: fontUrl("/fonts/IBMPlexMono-Bold.ttf"),
        fontWeight: 700,
      },
    ],
  })
  Font.register({
    family: "BlackOpsOne",
    src: fontUrl("/fonts/BlackOpsOne-Regular.ttf"),
  })
  fontsRegistered = true
}

const styles = StyleSheet.create({
  page: {
    backgroundColor: "#f5f0e8",
    color: "#1a1a1a",
    fontFamily: "IBMPlexSerif",
    paddingTop: 16,
    paddingBottom: 14,
    paddingHorizontal: 20,
    fontSize: 10,
    lineHeight: 1.45,
    position: "relative",
  },
  watermarkWrap: {
    position: "absolute",
    top: 260,
    left: 110,
    transform: "rotate(-32deg)",
    opacity: 0.08,
  },
  watermark: {
    fontFamily: "BlackOpsOne",
    fontSize: 110,
    color: "#8b0000",
    letterSpacing: 6,
  },
  banner: {
    backgroundColor: "#000000",
    color: "#cc0000",
    textAlign: "center",
    fontFamily: "IBMPlexMono",
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 2,
    paddingVertical: 6,
    marginBottom: 1,
  },
  topRule: {
    height: 1.6,
    backgroundColor: "#8b0000",
    marginBottom: 14,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 12,
  },
  brand: {
    fontFamily: "BlackOpsOne",
    fontSize: 29,
    letterSpacing: 2.5,
    color: "#1a1a1a",
  },
  leftCol: {
    width: "38%",
  },
  headerRight: {
    alignItems: "flex-end",
    width: "60%",
  },
  title: {
    fontFamily: "BlackOpsOne",
    color: "#8b0000",
    fontSize: 24,
    lineHeight: 1.02,
    textAlign: "right",
    marginBottom: 2,
  },
  mono: {
    fontFamily: "IBMPlexMono",
    fontSize: 8.8,
    lineHeight: 1.25,
    letterSpacing: 0.4,
  },
  metadataBar: {
    backgroundColor: "#2a2a2a",
    color: "#d4cfc5",
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 8,
    paddingVertical: 8,
    marginBottom: 14,
  },
  metadataCell: {
    width: "19%",
  },
  metadataText: {
    fontFamily: "IBMPlexMono",
    fontSize: 8.5,
  },
  section: {
    marginBottom: 9,
  },
  sectionTitleWrap: {
    flexDirection: "row",
    alignItems: "stretch",
    marginBottom: 6,
  },
  sectionBar: {
    width: 3,
    backgroundColor: "#8b0000",
  },
  sectionTitle: {
    backgroundColor: "#efebe2",
    paddingHorizontal: 8,
    paddingVertical: 5,
    fontFamily: "BlackOpsOne",
    letterSpacing: 1,
    fontSize: 14,
  },
  body: {
    paddingLeft: 10,
    fontSize: 10,
  },
  bodyParagraph: {
    marginBottom: 6,
  },
  listItem: {
    marginBottom: 5,
    paddingLeft: 10,
  },
  listBullet: {
    width: 7,
    height: 7,
    borderRadius: 4,
    marginTop: 4,
    marginRight: 6,
  },
  listItemRow: {
    flexDirection: "row",
    alignItems: "flex-start",
  },
  listItemText: {
    fontFamily: "IBMPlexMono",
    fontSize: 11,
    lineHeight: 1.35,
  },
  sourceTagsRow: {
    flexDirection: "row",
    marginLeft: 22,
    marginTop: 2,
    marginBottom: 2,
  },
  sourceTag: {
    fontFamily: "IBMPlexMono",
    fontSize: 8,
    color: "#58606a",
    backgroundColor: "#e4e0d8",
    paddingHorizontal: 4,
    paddingVertical: 2,
    marginRight: 4,
  },
  threatBox: {
    borderWidth: 1,
    borderColor: "#2a2a2a",
    backgroundColor: "#f0ece3",
    padding: 10,
    marginLeft: 10,
  },
  threatLabels: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  threatLabelLow: {
    fontFamily: "IBMPlexMono",
    color: "#2d7a2d",
    fontSize: 9,
    fontWeight: 700,
  },
  threatLabelHigh: {
    fontFamily: "IBMPlexMono",
    color: "#cc0000",
    fontSize: 9,
    fontWeight: 700,
  },
  threatBarRow: {
    flexDirection: "row",
    height: 14,
    position: "relative",
  },
  threatSeg1: { backgroundColor: "#2d7a2d", width: "16.6%" },
  threatSeg2: { backgroundColor: "#6aab2d", width: "16.6%" },
  threatSeg3: { backgroundColor: "#c9a800", width: "16.6%" },
  threatSeg4: { backgroundColor: "#e85d00", width: "16.6%" },
  threatSeg5: { backgroundColor: "#cc0000", width: "16.6%" },
  threatSeg6: { backgroundColor: "#8b0000", width: "17%" },
  threatMarkerWrap: {
    position: "absolute",
    top: 0,
    alignItems: "center",
  },
  threatMarkerLine: {
    width: 1.2,
    height: 14,
    backgroundColor: "#101010",
  },
  threatPointer: {
    marginTop: 1,
    fontFamily: "IBMPlexMono",
    fontSize: 10,
  },
  threatScale: {
    marginTop: 11,
    flexDirection: "row",
    justifyContent: "space-between",
  },
  threatScaleText: {
    fontFamily: "IBMPlexMono",
    fontSize: 7.4,
    color: "#7a746b",
  },
  threatScaleTextActive: {
    fontFamily: "IBMPlexMono",
    fontSize: 7.4,
    color: "#111111",
    fontWeight: 700,
  },
  footerMeta: {
    marginTop: 8,
    borderTopWidth: 1,
    borderTopColor: "#c9c0b0",
    paddingTop: 6,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  tiny: {
    fontFamily: "IBMPlexMono",
    fontSize: 8,
    color: "#5a5550",
  },
  bottomBanner: {
    marginTop: 8,
    backgroundColor: "#000000",
    color: "#cc0000",
    textAlign: "center",
    fontFamily: "IBMPlexMono",
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 2,
    paddingVertical: 6,
  },
})

const threatColorByPriority: Record<string, string> = {
  CRITICAL: "#cc0000",
  HIGH: "#e85d00",
  MEDIUM: "#c9a800",
  LOW: "#2d7a2d",
}

function threatMarkerLeft(score: number): string {
  const clamped = Math.max(0, Math.min(100, score))
  return `${clamped}%`
}

function ReportPdfDocument({ data }: { data: IntelligenceReportData }) {
  const priority = data.keyDevelopments.slice(0, 5)
  const notes = data.analystNotes.slice(0, 3)
  const scale = ["MINIMAL", "LOW", "GUARDED", "ELEVATED", "HIGH", "CRITICAL"]
  return (
    <Document>
      <Page size="A4" style={styles.page}>
        <View style={styles.watermarkWrap}>
          <Text style={styles.watermark}>CLASSIFIED</Text>
        </View>
        <Text style={styles.banner}>//UNCLASSIFIED//FOR OFFICIAL USE ONLY//</Text>
        <View style={styles.topRule} />

        <View style={styles.headerRow}>
          <View style={styles.leftCol}>
            <Text style={styles.brand}>OSINT NEXUS</Text>
          </View>
          <View style={styles.headerRight}>
            <Text style={styles.title}>{data.title}</Text>
            <Text style={styles.mono}>{data.docId}</Text>
            <Text style={styles.mono}>CLASSIFICATION: {data.classification}</Text>
            <Text style={styles.mono}>DISTRIBUTION: {data.distribution}</Text>
          </View>
        </View>

        <View style={styles.metadataBar}>
          <View style={styles.metadataCell}><Text style={styles.metadataText}>GENERATED: {data.metadata.generatedAt}</Text></View>
          <View style={styles.metadataCell}><Text style={styles.metadataText}>ANALYST: {data.metadata.analyst}</Text></View>
          <View style={styles.metadataCell}><Text style={styles.metadataText}>SOURCES: {data.metadata.sourcesActive} ACTIVE</Text></View>
          <View style={styles.metadataCell}><Text style={styles.metadataText}>CONFIDENCE: {data.metadata.confidence}</Text></View>
          <View style={styles.metadataCell}><Text style={styles.metadataText}>REPORT: {data.metadata.reportId}</Text></View>
        </View>

        <View style={styles.section}>
          <View style={styles.sectionTitleWrap}>
            <View style={styles.sectionBar} />
            <Text style={styles.sectionTitle}>SECTION 1 — EXECUTIVE SUMMARY</Text>
          </View>
          <View style={styles.body}>
            {data.executiveSummary.slice(0, 3).map((p, idx) => (
              <Text key={`summary-${idx}`} style={styles.bodyParagraph}>{p}</Text>
            ))}
          </View>
        </View>

        <View style={styles.section}>
          <View style={styles.sectionTitleWrap}>
            <View style={styles.sectionBar} />
            <Text style={styles.sectionTitle}>SECTION 2 — KEY DEVELOPMENTS</Text>
          </View>
          <View style={styles.body}>
            {priority.map((item, idx) => (
              <View key={`dev-${idx}`} style={styles.listItem}>
                <View style={styles.listItemRow}>
                  <View style={[styles.listBullet, { backgroundColor: threatColorByPriority[item.priority] || "#666" }]} />
                  <Text style={styles.listItemText}>{idx + 1}. [{item.priority}] {item.text}</Text>
                </View>
                {item.sources?.length ? (
                  <View style={styles.sourceTagsRow}>
                    {item.sources.slice(0, 3).map((src, sIdx) => (
                      <Text key={`src-${idx}-${sIdx}`} style={styles.sourceTag}>[{src}]</Text>
                    ))}
                  </View>
                ) : null}
              </View>
            ))}
          </View>
        </View>

        <View style={styles.section}>
          <View style={styles.sectionTitleWrap}>
            <View style={styles.sectionBar} />
            <Text style={styles.sectionTitle}>SECTION 3 — THREAT ASSESSMENT</Text>
          </View>
          <View style={styles.threatBox}>
            <View style={styles.threatLabels}>
              <Text style={styles.threatLabelLow}>MINIMAL</Text>
              <Text style={styles.threatLabelHigh}>CRITICAL</Text>
            </View>
            <View style={styles.threatBarRow}>
              <View style={styles.threatSeg1} />
              <View style={styles.threatSeg2} />
              <View style={styles.threatSeg3} />
              <View style={styles.threatSeg4} />
              <View style={styles.threatSeg5} />
              <View style={styles.threatSeg6} />
              <View style={[styles.threatMarkerWrap, { left: threatMarkerLeft(data.threat.score) }]}>
                <View style={styles.threatMarkerLine} />
                <Text style={styles.threatPointer}>▼</Text>
                <Text style={styles.threatLabelHigh}>{data.threat.level}</Text>
              </View>
            </View>
            <View style={styles.threatScale}>
              {scale.map((s) => (
                <Text key={s} style={s === data.threat.level ? styles.threatScaleTextActive : styles.threatScaleText}>{s}</Text>
              ))}
            </View>
          </View>
        </View>

        <View style={styles.section}>
          <View style={styles.sectionTitleWrap}>
            <View style={styles.sectionBar} />
            <Text style={styles.sectionTitle}>SECTION 4 — GEOGRAPHIC FOCUS</Text>
          </View>
          <View style={styles.body}>
            <Text style={styles.bodyParagraph}>
              Primary theater: Middle East AOI. Continue monitoring high-density clusters in recent
              event stream and correlate with source corroboration.
            </Text>
          </View>
        </View>

        <View style={styles.section}>
          <View style={styles.sectionTitleWrap}>
            <View style={styles.sectionBar} />
            <Text style={styles.sectionTitle}>SECTION 5 — ANALYST NOTES</Text>
          </View>
          <View style={styles.body}>
            {notes.map((n, idx) => (
              <Text key={`note-${idx}`} style={styles.bodyParagraph}>{n}</Text>
            ))}
          </View>
        </View>

        <View style={styles.footerMeta}>
          <Text style={styles.tiny}>PREPARED BY: OSINT NEXUS AI ANALYST</Text>
          <Text style={styles.tiny}>PAGE 1 OF 1</Text>
          <Text style={styles.tiny}>DOC CONTROL: {data.docId}</Text>
        </View>
        <Text style={styles.bottomBanner}>//UNCLASSIFIED//FOR OFFICIAL USE ONLY//</Text>
      </Page>
    </Document>
  )
}

export async function generateReportPdfBlob(data: IntelligenceReportData): Promise<Blob> {
  ensurePdfFonts()
  return pdf(<ReportPdfDocument data={data} />).toBlob()
}
