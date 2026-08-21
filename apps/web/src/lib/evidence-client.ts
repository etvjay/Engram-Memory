import { parseEvidenceIndex } from "./evidence-schema";
import type { EvidenceIndex, ExperimentEvidence } from "../types/evidence";

const env = (import.meta as ImportMeta & { env: Record<string, string | undefined> }).env;
const owner = env.VITE_ENGRAM_EVIDENCE_OWNER ?? "etvjay";
const repo = env.VITE_ENGRAM_EVIDENCE_REPO ?? "Engram-Memory";
const ref = env.VITE_ENGRAM_EVIDENCE_REF ?? "main";
const indexPath = env.VITE_ENGRAM_EVIDENCE_INDEX ?? "evidence/web/index.json";
const rawBase = env.VITE_ENGRAM_EVIDENCE_RAW_BASE ?? `https://raw.githubusercontent.com/${owner}/${repo}/${ref}`;

async function getJson(url: string): Promise<unknown> {
  const response = await fetch(url, { headers: { accept: "application/json" }, cache: "no-store" });
  if (!response.ok) throw new Error(`Evidence source returned ${response.status}`);
  return response.json();
}

export class EvidenceClient {
  async loadIndex(): Promise<EvidenceIndex> {
    let lastError: unknown;
    for (const url of [`${rawBase}/${indexPath}`]) {
      try { return parseEvidenceIndex(await getJson(url)); } catch (error) { lastError = error; }
    }
    throw lastError instanceof Error ? lastError : new Error("Evidence source unavailable");
  }
  getDataset(index: EvidenceIndex) { return index.dataset; }
  getExperiments(index: EvidenceIndex) { return index.experiments ?? []; }
  getExperiment(index: EvidenceIndex, id: string) { return this.getExperiments(index).find((item) => item.id === id); }
  getLatestByKind(index: EvidenceIndex, kind: string): ExperimentEvidence | undefined { return [...this.getExperiments(index)].reverse().find((item) => item.kind === kind); }
}

export const evidenceClient = new EvidenceClient();
