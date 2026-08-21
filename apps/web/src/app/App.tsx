import React, { useEffect, useMemo, useState } from "react";
import { Navigation } from "../components/Navigation";
import { Hero } from "../components/Hero";
import { ExecutionTrace, ExperienceInspector, AblationCompare } from "../components/ProductSurfaces";
import { EvidenceOverview } from "../components/EvidenceOverview";
import { evidenceClient } from "../lib/evidence-client";
import type { EvidenceIndex, EvidenceSyncState } from "../types/evidence";

export function App() {
  const [evidence, setEvidence] = useState<EvidenceIndex | null>(null);
  const [sync, setSync] = useState<EvidenceSyncState>("LOADING");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    evidenceClient.loadIndex().then((index) => {
      if (!active) return;
      setEvidence(index);
      setSync("SYNCED");
    }).catch((cause) => {
      if (!active) return;
      setSync("UNAVAILABLE");
      setError(cause instanceof Error ? cause.message : "Evidence source unavailable");
    });
    return () => { active = false; };
  }, []);

  const source = useMemo(() => ({
    commit: evidence?.commit ? evidence.commit.slice(0, 7) : "UNAVAILABLE",
    ref: evidence?.ref ?? "UNAVAILABLE",
    repository: evidence?.repository ?? "UNAVAILABLE",
  }), [evidence]);

  return <main>
    <Navigation sync={sync} />
    <Hero />
    <section className="sequence-band" aria-label="Engram memory sequence">
      {["Execution", "Outcome", "Experience", "Recall", "Influence"].map((step, index) => <React.Fragment key={step}>
        <div><span>{String(index + 1).padStart(2, "0")}</span><strong>{step}</strong></div>
        {index < 4 && <i aria-hidden="true">→</i>}
      </React.Fragment>)}
    </section>
    <ExecutionTrace />
    <ExperienceInspector />
    <AblationCompare index={evidence} />
    <EvidenceOverview index={evidence} sync={sync} error={error} />
    <footer className="site-footer" id="source">
      <div><span>BUILD / SOURCE / COMMIT</span><strong>Engram unified submission surface</strong></div>
      <div><span>Evidence source</span><strong>{source.repository}</strong></div>
      <div><span>Ref</span><strong>{source.ref}</strong></div>
      <div><span>Evidence commit</span><strong>{source.commit}</strong></div>
    </footer>
  </main>;
}
