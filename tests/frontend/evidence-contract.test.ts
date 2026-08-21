import { describe, expect, it } from "vitest";
import { parseEvidenceIndex } from "../../apps/web/src/lib/evidence-schema.js";
import { findAblationExperiment } from "../../apps/web/src/lib/ablation.js";

const baseIndex = {
  schema_version: "engram-evidence-index-v1",
  repository: "etvjay/Engram-Memory",
  ref: "main",
  commit: "abcdef1234567890",
  experiments: [
    { id: "PRISM-13-A0", title: "No-memory control", kind: "CONTROL", status: "TESTED", coverage: "SUBSET", ablation_stage: "A0", claim_scope: "official no_retrieval control", metrics: { empty_contexts: 12 } },
    { id: "PRISM-13-A1", title: "Flat-memory control", kind: "CONTROL", status: "TESTED", coverage: "SUBSET", ablation_stage: "A1", claim_scope: "non-Hydra flat memory control" },
    { id: "A4", title: "Behavioral causal proof", kind: "CAUSAL", status: "NOT_RUN", coverage: "SUBSET", ablation_stage: "A4", claim_scope: "memory-off versus memory-on behavioral causal experiment" },
    { id: "PRISM-14", title: "Structural causal provenance", kind: "CAUSAL", status: "TESTED", coverage: "SUBSET", claim_scope: "structural causal provenance only; not behavioral causal proof" }
  ]
};

describe("evidence index contract", () => {
  it("rejects a missing schema version", () => expect(() => parseEvidenceIndex({ experiments: [] })).toThrow(/schema_version/));
  it("preserves index provenance instead of deriving it", () => { const parsed = parseEvidenceIndex(baseIndex); expect(parsed.ref).toBe("main"); expect(parsed.commit).toBe("abcdef1234567890"); });
  it("normalizes unknown statuses without strengthening the claim", () => { const parsed = parseEvidenceIndex({ ...baseIndex, experiments: [{ id: "X", title: "Future experiment", kind: "FUTURE", status: "MAGIC" }] }); expect(parsed.experiments?.[0]?.status).toBe("UNKNOWN"); });
  it("preserves ablation_stage from the canonical index", () => { const parsed = parseEvidenceIndex(baseIndex); expect(parsed.experiments?.find((item) => item.id === "PRISM-13-A0")?.ablation_stage).toBe("A0"); expect(parsed.experiments?.find((item) => item.id === "A4")?.ablation_stage).toBe("A4"); });
  it("resolves ablations only from explicit ablation_stage metadata", () => { const parsed = parseEvidenceIndex(baseIndex); expect(findAblationExperiment(parsed, "A0")?.id).toBe("PRISM-13-A0"); expect(findAblationExperiment(parsed, "A1")?.id).toBe("PRISM-13-A1"); expect(findAblationExperiment(parsed, "A4")?.id).toBe("A4"); });
  it("keeps PRISM-14 structurally separate from A4 behavioral causal proof", () => { const parsed = parseEvidenceIndex(baseIndex); const prism14 = parsed.experiments?.find((item) => item.id === "PRISM-14"); expect(prism14?.status).toBe("TESTED"); expect(prism14?.ablation_stage).toBeUndefined(); expect(findAblationExperiment(parsed, "A4")?.status).toBe("NOT_RUN"); });
});
