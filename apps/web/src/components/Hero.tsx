import React from "react";

const runA = ["state", "state", "thin liquidity", "failure"];
const runB = ["similar state", "recall", "decision", "altered action"];

function RunTrack({ items, run }: { items: string[]; run: "A" | "B" }) {
  return <div className={`hero-run hero-run-${run.toLowerCase()}`}>
    <div className="hero-run-label"><span>RUNTIME {run}</span><i>{run === "A" ? "source execution" : "later execution"}</i></div>
    <div className="hero-run-track">{items.map((item, index) => <React.Fragment key={`${run}-${item}-${index}`}>
      <div className={`hero-state hero-state-${item.replaceAll(" ", "-")}`}><small>{String(index + 1).padStart(2, "0")}</small><span>{item}</span></div>
      {index < items.length - 1 && <div className="hero-edge" aria-hidden="true"><i /></div>}
    </React.Fragment>)}</div>
  </div>;
}

export function Hero() {
  return <section className="hero" id="overview">
    <div className="hero-copy">
      <p className="eyebrow">Persistent execution memory for autonomous agents · HydraDB</p>
      <h1>Memory for what agents do.</h1>
      <p className="hero-lede">Past executions should not disappear when an agent runtime does. Engram preserves what happened, reconstructs relevant prior experience in later runtimes, and records whether recall actually influenced what happened next.</p>
      <div className="hero-actions"><a href="#trace">Follow the trace</a><a className="secondary" href="#evidence">Inspect evidence</a></div>
      <div className="hero-invariant"><span>critical invariant</span><strong>RECALL ≠ INFLUENCE</strong><p>Seeing prior experience again is not proof that it changed behavior.</p></div>
    </div>
    <div className="trajectory-hero" aria-label="Illustrative execution-memory trajectory across two runtimes">
      <div className="trajectory-kicker"><span>ILLUSTRATIVE MECHANISM</span><strong>Execution survives runtime death.</strong></div>
      <RunTrack items={runA} run="A" />
      <div className="hero-memory-bridge">
        <div className="memory-origin"><span>EXPERIENCE</span><strong>prior outcome becomes durable operational memory</strong></div>
        <div className="memory-spine" aria-hidden="true"><i /><i /></div>
        <div className="runtime-cut"><span>RUNTIME ENDS</span><b /></div>
        <div className="memory-return"><span>relevant prior experience</span><strong>reconstructed</strong></div>
      </div>
      <RunTrack items={runB} run="B" />
      <div className="influence-gate"><span>INFLUENCE GATE</span><strong>Did recalled experience materially affect this decision?</strong><i aria-hidden="true" /></div>
    </div>
  </section>;
}
