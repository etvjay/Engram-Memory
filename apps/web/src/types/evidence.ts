export type EvidenceStatus = "IMPLEMENTED" | "TESTED" | "DEPLOYED" | "SIMULATED" | "PROPOSED" | "UNKNOWN" | "NOT_RUN";
export type EvidenceCoverage = "FULL" | "SUBSET" | "SMOKE";
export type ExperimentKind = "BENCHMARK" | "DIAGNOSTIC" | "LIVE_MECHANISM" | "CONTROL" | "CAUSAL" | string;
export type AblationStage = "A0" | "A1" | "A2" | "A3" | "A4";
export type DatasetEvidence = { benchmark?: string; tier?: string; coverage?: EvidenceCoverage; multimodal?: boolean; questions?: number; trajectories?: number; haystack_questions?: number; runtime_screenshot_links?: number; validation?: string; benchmark_code_commit?: string; dataset_revision?: string; hydradb_commit?: string; };
export type ExperimentEvidence = { id: string; title: string; kind: ExperimentKind; status: EvidenceStatus; coverage?: EvidenceCoverage; ablation_stage?: AblationStage; claim_scope?: string; result_path?: string; report_path?: string; checksums_path?: string; metrics?: Record<string, unknown>; warnings?: string[]; };
export type EvidenceIndex = { schema_version: string; generated_at?: string; repository?: string; ref?: string; commit?: string; dataset?: DatasetEvidence; experiments?: ExperimentEvidence[]; latest?: Record<string, unknown>; };
export type EvidenceSyncState = "SYNCED" | "STALE" | "UNAVAILABLE" | "LOADING";
