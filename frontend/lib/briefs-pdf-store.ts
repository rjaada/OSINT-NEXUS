import { promises as fs } from "fs"
import path from "path"
import type { IntelligenceReportData } from "@/components/briefs/report/types"

const TTL_MS = 2 * 60 * 1000
const STORE_DIR = "/tmp/osint_briefs_pdf"

function filePathFor(key: string): string {
  return path.join(STORE_DIR, `${key}.json`)
}

async function ensureDir() {
  await fs.mkdir(STORE_DIR, { recursive: true })
}

async function pruneStore() {
  await ensureDir()
  const now = Date.now()
  const files = await fs.readdir(STORE_DIR)
  for (const file of files) {
    if (!file.endsWith(".json")) continue
    const fpath = path.join(STORE_DIR, file)
    try {
      const raw = await fs.readFile(fpath, "utf-8")
      const parsed = JSON.parse(raw) as { expiresAt?: number }
      if (!parsed.expiresAt || parsed.expiresAt <= now) {
        await fs.rm(fpath, { force: true })
      }
    } catch {
      await fs.rm(fpath, { force: true })
    }
  }
}

export async function putPdfPayload(data: IntelligenceReportData): Promise<string> {
  await pruneStore()
  const key = crypto.randomUUID()
  const payload = {
    data,
    expiresAt: Date.now() + TTL_MS,
  }
  await fs.writeFile(filePathFor(key), JSON.stringify(payload), "utf-8")
  return key
}

export async function getPdfPayload(key: string): Promise<IntelligenceReportData | null> {
  await pruneStore()
  try {
    const raw = await fs.readFile(filePathFor(key), "utf-8")
    const parsed = JSON.parse(raw) as { data?: IntelligenceReportData; expiresAt?: number }
    if (!parsed.expiresAt || parsed.expiresAt <= Date.now() || !parsed.data) {
      return null
    }
    return parsed.data
  } catch {
    return null
  }
}

export async function deletePdfPayload(key: string): Promise<void> {
  try {
    await fs.rm(filePathFor(key), { force: true })
  } catch {
    // ignore cleanup errors
  }
}
