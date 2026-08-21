import React from "react";
import type { ExperimentEvidence } from "../types/evidence";

function record(value: unknown): Record<string, unknown> | null { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null; }
function numberEntries(value: unknown) { const r = record(value); return r ? Object.entries(r).filter((entry): entry is [string, number] => typeof entry[1] === "number") : []; }
function EvidenceUnavailable({ title }: { title: string }) { return <article className="research-module unavailable-module"><span>UNAVAILABLE</span><h3>{title}</h3><p>Waiting for the canonical evidence index to provide this module’s source metrics.</p></article>; }

export function RadiusFrontier({ experiment }: { experiment?: ExperimentEvidence }) {
  const hits = numberEntries(experiment?.metrics?.radius_hits);
  const upper = typeof experiment?.metrics?.same_trajectory_upper_bound === "number" ? experiment.metrics.same_trajectory_upper_bound : undefined;
  const cohort = typeof experiment?.metrics?.n_questions === "number" ? experiment.metrics.n_questions : undefined;
  if (!experiment || !hits.length) return <EvidenceUnavailable title="A3 Graph Radius Frontier" />;
  const max = Math.max(...hits.map(([, n]) => n), upper ?? 0, 1);
  return <article className="research-module"><div className="module-head"><div><span>POST-HOC DIAGNOSTIC</span><h3>A3 Graph Radius Frontier</h3><p>Recoverable evidence as graph traversal expands around trajectory-aware retrieval seeds.</p></div><em>{cohort ? `${cohort} QUESTION COHORT` : "COHORT UNAVAILABLE"}</em></div><div className="radius-chart">{hits.map(([radius, count]) => <div className="radius-column" key={radius}><div className="radius-bar"><i style={{height:`${Math.max(4,(count/max)*100)}%`}}><b>{count}</b></i></div><span>R{radius}</span></div>)}</div>{upper !== undefined && <div className="upper-bound"><span>trajectory upper bound</span><strong>{upper}</strong></div>}</article>;
}

export function DistanceHistogram({ experiment }: { experiment?: ExperimentEvidence }) {
  const raw = record(experiment?.metrics?.distance_histogram);
  if (!experiment || !raw) return <EvidenceUnavailable title="Evidence distance distribution" />;
  const noTrajectory = typeof raw.NO_CORRECT_TRAJECTORY === "number" ? raw.NO_CORRECT_TRAJECTORY : undefined;
  const distances = Object.entries(raw).filter((entry): entry is [string, number] => entry[0] !== "NO_CORRECT_TRAJECTORY" && typeof entry[1] === "number").sort((a,b)=>Number(a[0])-Number(b[0]));
  const max = Math.max(...distances.map(([,n])=>n),1);
  return <article className="research-module"><div className="module-head"><div><span>DIAGNOSTIC DISTRIBUTION</span><h3>Evidence distance</h3><p>Minimum selected-seed distance to evidence. Missing correct trajectories remain semantically separate.</p></div></div><div className="distance-list">{distances.map(([distance,count])=><div key={distance}><span>distance {distance}</span><i><b style={{width:`${Math.max(2,(count/max)*100)}%`}} /></i><strong>{count}</strong></div>)}</div>{noTrajectory !== undefined && <div className="no-trajectory"><span>NO_CORRECT_TRAJECTORY</span><strong>{noTrajectory}</strong></div>}</article>;
}

export function LiveMechanismReplay({ experiment }: { experiment?: ExperimentEvidence }) {
  if (!experiment) return <EvidenceUnavailable title="PRISM-12 Live Hydra proof" />;
  const m = experiment.metrics ?? {}; const strata = record(m.strata); const exact = record(strata?.exact_seed); const graph = record(strata?.graph1_only); const negative = record(strata?.unrecovered_r1); const hits = record(m.mechanism_subset_live_hits);
  const rows: [string, unknown, string][] = [["exact seed", exact?.a2_and_a3_live_recovered, exact?.n ? `/ ${exact.n} preserved` : ""], ["graph1 only", graph?.a2_miss_a3_live_recovery, graph?.n ? `/ ${graph.n} A2 miss → A3 recovery` : ""], ["negative controls", negative?.a2_and_a3_live_miss, negative?.n ? `/ ${negative.n} remained unrecovered` : ""], ["mechanism parity", m.mechanism_matches, typeof m.n_questions === "number" ? `/ ${m.n_questions}` : ""], ["A2 evidence hits", hits?.a2, typeof m.n_questions === "number" ? `/ ${m.n_questions}` : ""], ["A3 evidence hits", hits?.a3, typeof m.n_questions === "number" ? `/ ${m.n_questions}` : ""]];
  return <article className="research-module live-module"><div className="module-head"><div><span>LIVE HYDRA · NEXT_STATE · RADIUS 1</span><h3>{experiment.title}</h3><p>{experiment.claim_scope ?? "Claim scope unavailable."}</p></div><em>{experiment.status}</em></div><div className="live-grid">{rows.map(([label,val,suffix])=><div key={label}><span>{label}</span><strong>{typeof val === "number" ? val : "UNAVAILABLE"} <small>{suffix}</small></strong></div>)}</div><div className="claim-warning">DETERMINISTIC DIAGNOSTIC SUBSET · NOT UNBIASED BENCHMARK RECALL</div></article>;
}
