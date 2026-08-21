import React from "react";
import type { EvidenceSyncState } from "../types/evidence";

const links = [["Overview", "#overview"], ["Trace", "#trace"], ["Experience", "#experience"], ["Compare", "#compare"], ["Evidence", "#evidence"]];

export function Navigation({ sync }: { sync: EvidenceSyncState }) {
  return <header className="nav-shell">
    <a className="wordmark" href="#overview">ENGRAM</a>
    <nav aria-label="Primary navigation">{links.map(([label, href]) => <a key={href} href={href}>{label}</a>)}</nav>
    <div className={`sync-state sync-${sync.toLowerCase()}`}><i />{sync}</div>
  </header>;
}
