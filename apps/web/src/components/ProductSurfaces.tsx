import React from "react";
import type { AblationStage, EvidenceIndex } from "../types/evidence";
import { findAblationExperiment } from "../lib/ablation";

function SectionHead({ index, eyebrow, title, copy }: { index: string; eyebrow: string; title: string; copy: string }) {
  return <div className="section-head"><span className="section-index">{index}</span><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2><p className="section-copy">{copy}</p></div></div>;
}

export function ExecutionTrace() {
  return <section className="product-section" id="trace">
    <SectionHead index="01" eyebrow="Execution trace" title="What happened, and what survived it." copy="Engram treats execution topology as the primary artifact: state transitions, outcomes, memory origin, later recovery, and any recorded influence." />
    <div className="trace-stage"><div className="trace-meta"><span>ILLUSTRATIVE TOPOLOGY</span><strong>Mechanism view</strong><p>Geometry explains the interface. Numerical evidence is never synthesized here.</p></div><div className="graph-canvas"><div className="seed-label">retrieval seed</div><div className="node seed"><small>STATE</small><b>41</b></div><div className="edge"><span>NEXT_STATE</span></div><div className="node evidence-node"><small>STATE</small><b>42</b><em>evidence found</em></div><div className="origin-line"><i /><span>experience originates here</span></div></div></div>
  </section>;
}

export function ExperienceInspector() {
  const fields = [["Memory ID", "UNAVAILABLE"], ["Source execution", "UNAVAILABLE"], ["Source trajectory", "UNAVAILABLE"], ["Source state(s)", "UNAVAILABLE"], ["Observed event", "UNAVAILABLE"], ["Outcome", "UNAVAILABLE"], ["Evidence", "UNAVAILABLE"], ["Interpretation", "UNAVAILABLE"], ["Recovered by", "UNAVAILABLE"], ["Used by execution", "UNAVAILABLE"], ["Influence status", "UNAVAILABLE"]];
  return <section className="product-section" id="experience">
    <SectionHead index="02" eyebrow="Experience" title="A memory is more than a sentence." copy="The inspector keeps provenance and influence separate. Recall means an experience re-entered context; it does not, by itself, prove that behavior changed." />
    <div className="experience-shell"><div className="experience-summary"><span className="status amber-outline">UNAVAILABLE</span><h3>Experience data appears when supplied by an execution evidence source.</h3><p>No recall or influence state is asserted without evidence.</p><div className="invariant"><span>CRITICAL INVARIANT</span><strong>RECALL ≠ INFLUENCE</strong></div></div><div className="inspector-grid">{fields.map(([label, value]) => <div key={label}><span>{label}</span><strong className="dim">{value}</strong></div>)}</div></div>
  </section>;
}

export function AblationCompare({ index }: { index: EvidenceIndex | null }) {
  const stages: ReadonlyArray<readonly [AblationStage, string]> = [["A0", "NO MEMORY"], ["A1", "FLAT MEMORY"], ["A2", "HYDRA STATE"], ["A3", "HYDRA GRAPH"], ["A4", "ENGRAM CAUSAL MEMORY"]];
  const resolved = stages.map(([id, name]) => { const experiment = findAblationExperiment(index, id); return { id, name, status: experiment?.status ?? "UNAVAILABLE", experiment }; });
  const causal = resolved.find((stage) => stage.id === "A4");
  const structural = (index?.experiments ?? []).find((experiment) => experiment.id === "PRISM-14");
  return <section className="product-section" id="compare">
    <SectionHead index="03" eyebrow="Compare" title="Mechanism before behavioral causality." copy="A0 through A4 form the control-to-causal progression. Structural causal provenance is separate from the stronger memory-off versus memory-on behavioral causal experiment." />
    <div className="ablation-row">{resolved.map((stage, stageIndex) => <React.Fragment key={stage.id}><article><span>{stage.id}</span><strong>{stage.name}</strong><em className={stage.status === "TESTED" ? "tested" : ""}>{stage.status}</em></article>{stageIndex < resolved.length - 1 && <i>→</i>}</React.Fragment>)}</div>
    <div className="causal-notice"><span>STRUCTURAL PROVENANCE</span><strong>{structural?.status ?? "UNAVAILABLE"}</strong><p>{structural?.claim_scope ?? "Structural causal provenance unavailable."}</p></div>
    <div className="causal-notice"><span>BEHAVIORAL CAUSAL PROOF</span><strong>{causal?.status ?? "UNAVAILABLE"}</strong><p>{causal?.experiment?.claim_scope ?? "A4 remains unavailable until published by the canonical evidence index."}</p></div>
  </section>;
}
