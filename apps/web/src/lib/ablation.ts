import type { AblationStage, EvidenceIndex, ExperimentEvidence } from "../types/evidence.js";

export function findAblationExperiment(index: EvidenceIndex | null, stage: AblationStage): ExperimentEvidence | undefined {
  return (index?.experiments ?? []).find((experiment) => experiment.ablation_stage === stage);
}
