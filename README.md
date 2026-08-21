# Engram

**Persistent execution memory for autonomous agents, powered by HydraDB.**

Hack Hydra 2026 · Track 3 — Memory + Context Retrieval

> **Memory for what agents do.**

Engram preserves what an agent did, what happened as a result, and the operational memory derived from that experience across runtime death. A later runtime can retrieve relevant prior experience from HydraDB, expand surrounding execution context through graph relationships, and record explicit provenance when recall influences a later decision or action.

The central invariant is simple:

> **RECALL ≠ INFLUENCE**

Retrieving prior experience does not, by itself, prove that the experience changed behavior.

## Judge quick path

Everything required to inspect the submission lives in this repository.

- **Product source:** [`apps/web/`](apps/web/)
- **Canonical evidence:** [`evidence/web/index.json`](evidence/web/index.json)
- **Audit ledger:** [`AUDIT.md`](AUDIT.md)
- **Hydra memory adapter:** [`engram/longmemeval/hydra_memory.py`](engram/longmemeval/hydra_memory.py)
- **Causal provenance:** [`engram/causal/hydra_causal.py`](engram/causal/hydra_causal.py)
- **LongMemEval-V2 configs:** [`configs/longmemeval-v2/`](configs/longmemeval-v2/)
- **Reproduction scripts:** [`scripts/`](scripts/)
- **Attribution:** [`ATTRIBUTION.md`](ATTRIBUTION.md)

GitHub Pages deployment target: `https://etvjay.github.io/Engram-Memory/`

## What Engram is testing

Most agent memory systems optimize for retrieving text. Engram asks a stricter question:

> Can an agent's past execution survive runtime death, become relevant again under later conditions, and leave inspectable evidence of whether that experience influenced what happened next?

Canonical lifecycle:

```text
Execution
    ↓
Outcome
    ↓
Operational Memory
    ↓
runtime ends
    ↓
Later Execution
    ↓
Recall
    ↓
Influence
    ↓
Decision
    ↓
Action
    ↓
New Outcome
```

Recall can exist without influence. Influence requires explicit recall and decision context. Engram records structured provenance; it does not expose or depend on hidden chain-of-thought.

## Why HydraDB

HydraDB is not used as a passive document store. Engram persists execution state as graph-native memory.

For the controlled A2/A3 mechanism test, candidate selection is held fixed:

```text
A2 — Hydra flat
question → frozen selector → selected Hydra state → context

A3 — Hydra graph
question → same frozen selector → selected Hydra state
                                  ↓
                         NEXT_STATE radius 1
                                  ↓
                           expanded context
```

A2 reads the selected state from HydraDB without graph expansion. A3 uses the same selector and candidate budget, then traverses typed `NEXT_STATE` relationships. In the deterministic live mechanism cohort, four cases missed by A2 flat retrieval were recovered through live Hydra radius-1 traversal.

That isolates graph traversal as the material mechanism difference.

## Evidence matrix

| Stage | Memory condition | Hydra | Graph | Status |
|---|---|---:|---:|---|
| A0 | No memory | No | No | **TESTED** |
| A1 | Local flat memory | No | No | **TESTED** |
| A2 | Hydra selected-state retrieval | Yes | No | **TESTED** |
| A3 | Hydra + `NEXT_STATE` radius-1 expansion | Yes | Yes | **TESTED** |
| A4 | Behavioral causal memory | — | — | **NOT_RUN** |

| Proof | Establishes | Status |
|---|---|---|
| PRISM-12 | Live Hydra radius-1 mechanism | **TESTED** |
| PRISM-13 | Genuine A0/A1 controls | **TESTED** |
| PRISM-14 | Structural causal provenance; `RECALL ≠ INFLUENCE` | **TESTED** |
| PRISM-15 | Memory-OFF vs memory-ON behavioral causality | **NOT_RUN** |

PRISM-14 does **not** establish a behavioral counterfactual. `CHANGED_ACTION` remains unclaimed until the controlled PRISM-15 experiment passes.

## LongMemEval-V2

The prepared small tier contains:

- **451 questions**
- **1,870 trajectories**
- **1,913 runtime screenshot links**
- multimodal trajectories
- validation: **PASS**

The Hydra adapter implements the official LongMemEval-V2 `Memory` interface without modifying the benchmark repository. Trajectories and states are persisted in HydraDB and consecutive states are connected through typed `NEXT_STATE` relationships.

See [`docs/ENGRAM_HYDRA_MEMORY.md`](docs/ENGRAM_HYDRA_MEMORY.md).

### Local reader

A local multimodal reader path was exercised with:

- Ollama **0.32.14**
- Qwen2.5-VL 3B (`qwen25vl`, reported 3.8B parameters)
- Q4_K_M quantization
- `num_ctx = 16384`
- `temperature = 0`
- `top_k = 1`

This is a **local reader experiment**, not a claim of canonical official LongMemEval reader performance.

## Causal provenance

PRISM-14 exercises a live Hydra provenance graph across separate runtimes:

```text
Execution ─PRODUCED→ Outcome ─DISTILLED_TO→ Memory
    │
    └─PERFORMED_RECALL→ Recall ─RECALLED_MEMORY→ Memory
                         │
                         └─RECORDED_INFLUENCE→ Influence ─APPLIED_TO→ Decision
                                                            │
                                                            └─SELECTED_ACTION→ Action
```

The negative control records recall with **zero** influence edges. The positive structural case records an explicit influence receipt with state `CONSIDERED` connected to a later decision, action, and outcome.

That proves structural provenance. It does not yet prove that memory caused a different action.

## Product surface

The submission UI is part of this repository under [`apps/web/`](apps/web/). It consumes the canonical machine-readable evidence index from this same repository and renders:

- Overview
- Trace
- Experience
- Compare
- Evidence

The frontend never upgrades a claim beyond the evidence source. A4 remains `NOT_RUN` while PRISM-14 can separately remain `TESTED` as structural provenance.

### Run locally

Requirements: Node.js 22+ and npm.

```bash
npm install
npm run check
npm run dev:web
```

Build the static product:

```bash
npm run build:web
```

## Hydra memory smoke

Set the benchmark and Hydra paths:

```bash
export LONGMEMEVAL_V2_ROOT="$HOME/work/LongMemEval-V2"
export LONGMEMEVAL_V2_DATA_ROOT="$LONGMEMEVAL_V2_ROOT/data/longmemeval-v2-full"
export ENGRAM_HYDRA_TOKEN_FILE="$HOME/work/hydradb/.hydradb/auth-token"
```

Install the Python dependency:

```bash
python -m pip install -r requirements-hydra-memory.txt
```

Run the smoke:

```bash
python scripts/smoke_longmemeval_hydra.py
```

Expected mechanism-level success includes:

```text
INGEST=PASS
QUERY=PASS
ENGRAM_HYDRA_MEMORY_SMOKE=PASS
```

## Reproduce the controls and provenance

A0/A1 control structure:

```bash
python scripts/verify_prism13_controls.py
```

Live causal-provenance structure:

```bash
python scripts/verify_prism14_causal_graph.py
```

Canonical evidence index validation:

```bash
python scripts/build_evidence_index.py --check \
  --source-commit <evidence-source-commit> \
  --ref main

cd evidence/web
sha256sum -c SHA256SUMS
```

The index is generated from committed evidence and preserves the distinction between the source evidence commit and the later publication commit.

## Repository map

```text
apps/web/                  evidence-driven submission UI
engram/longmemeval/        HydraDB LongMemEval-V2 memory adapter
engram/causal/             causal-provenance graph implementation
configs/                    frozen experiment configurations
scripts/                    smoke, ablation, control, provenance, index tooling
evidence/                   immutable experiment outputs + checksums
audit/                      manifests and reproducibility metadata
docs/                       implementation notes
AUDIT.md                    human-readable claim ledger
ATTRIBUTION.md              upstream and reused-work attribution
```

## Claim discipline

Engram deliberately separates:

- ingestion from retrieval;
- retrieval from graph expansion;
- graph expansion from context packing;
- reader behavior from memory behavior;
- recall from influence;
- structural provenance from behavioral causality;
- diagnostics from benchmark results.

Preserved failures remain in the evidence tree rather than being erased from the research record.

## Tech stack

Python · HydraDB · Bolt / Neo4j Python driver · LongMemEval-V2 · Ollama · Qwen2.5-VL 3B · React · TypeScript · Vite · Vitest · Node.js · GitHub Actions · GitHub Pages · AWS EC2

## License

MIT. See [`LICENSE`](LICENSE).
