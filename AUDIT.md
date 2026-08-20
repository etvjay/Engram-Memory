# AUDIT.md — Engram Memory × HydraDB Benchmark Contract

Status: **GOVERNING AUDIT DOCUMENT** for the Hack Hydra submission.

> **Benchmark first. Primitive second. Application third.**
>
> Any product, demo, vertical, agent workflow, or use case is built on top of the audited memory substrate. It does not replace substrate evaluation.

## 0. Authority order

1. Official Hack Hydra rules and Track 03 problem statement
2. Current `hydra-db/hydradb` OSS repository and executable behavior
3. LongMemEval-V2 official repository and evaluation harness
4. LongMemEval official repository and evaluation harness
5. BEAM official repository and evaluation harness
6. Engram-specific causal-memory experiments
7. Applications, demos, UI, product narratives, and use cases

No product claim overrides a failed benchmark or conformance result.

## 1. Hack Hydra eligibility gate

Primary track: **03 | Memory + Context Retrieval**.

HydraDB must do real work in the project. The audited path uses the HydraDB OSS implementation directly, locally or self-hosted, and records the exact HydraDB commit/image used.

This repository is the fresh submission repository. Pre-existing Engram work lives separately in `etvjay/Engram` and is treated as upstream/reference work. Any reused code must be explicitly attributed.

## 2. Core memory contract

The project is evaluated as a memory system before it is evaluated as a product.

The audited primitive must demonstrate:

1. persistence across sessions/runtimes;
2. retrieval from long histories;
3. chronological and temporal correctness;
4. knowledge updates without silent history deletion;
5. contradiction/premise awareness;
6. abstention when evidence is absent;
7. multi-session reasoning;
8. environment/workflow memory;
9. isolation/scoping correctness;
10. measurable latency and retrieval quality;
11. causal provenance when prior experience is claimed to influence a later action.

## 3. Baseline A — LongMemEval

Source: `xiaowu0162/LongMemEval`

Required abilities:

- Information Extraction
- Multi-Session Reasoning
- Knowledge Updates
- Temporal Reasoning
- Abstention

Required retrieval metrics when applicable:

Session level:

- `recall_all@5`
- `ndcg_any@5`
- `recall_all@10`
- `ndcg_any@10`

Turn level:

- `recall_all@5`
- `ndcg_any@5`
- `recall_all@10`
- `ndcg_any@10`
- `recall_all@50`
- `ndcg_any@50`

Abstention is evaluated at the QA layer; retrieval-only evaluation must not manufacture an abstention score.

## 4. Baseline B — LongMemEval-V2

Source: `xiaowu0162/LongMemEval-V2`

This is the primary agent-experience baseline.

Required abilities:

- Static state recall
- Dynamic state tracking
- Workflow knowledge
- Environment gotchas
- Premise awareness

Where feasible, compare against the official baseline classes:

- `no_retrieval`
- `rag_query_to_slice`
- `rag_query_to_slice_notes`
- `agentrunbook_r`
- `codex`
- `agentrunbook_c`

Preserve these scored outputs:

- `overall_full_set`
- `gotchas_accuracy`
- `static_accuracy`
- `dynamic_accuracy`
- `procedure_accuracy`
- `memory_query_avg_seconds`

Benchmark leakage is forbidden: the memory query path must not access gold answers, question types, evidence labels, or evaluator metadata.

## 5. Baseline C — BEAM

Source: `mohammadtavakoli78/BEAM`

Required scales are labeled exactly as run:

- 128K
- 500K
- 1M
- 10M

Coverage must be labeled:

- `FULL`
- `SUBSET`
- `SMOKE`

Required probing categories:

1. Abstention
2. Contradiction Resolution
3. Event Ordering
4. Information Extraction
5. Instruction Following
6. Knowledge Update
7. Multi-Session Reasoning
8. Preference Following
9. Summarization
10. Temporal Reasoning

## 6. HydraDB OSS conformance

For every audited run, record:

```text
HydraDB repository     hydra-db/hydradb
HydraDB commit SHA     <exact SHA>
Build/image            <source build or exact image/digest>
Graph namespace        <value>
Graph id               <value>
Cell configuration     <value>
Storage backend        <local/S3-compatible/etc>
Bolt endpoint          <if used>
HTTP endpoint          <if used>
```

Minimum OSS proof:

1. HydraDB node starts from the open-source project/image.
2. Readiness passes.
3. A graph mutation round-trips.
4. Restart preserves durable state when durability is claimed.
5. Benchmark memory is written into HydraDB.
6. Benchmark evidence is retrieved through HydraDB.
7. At least one evaluated path uses graph relationships/traversal materially.
8. Removing graph structure causes a measurable degradation or capability loss before any graph-native advantage is claimed.

## 7. Engram causal-memory extension

Canonical chain:

```text
Execution A
  -> Outcome A
  -> Operational Memory
  -> originating runtime ends
  -> Recall B
  -> Decision B
  -> explicit Influence
  -> Action B
  -> Outcome B
```

Required distinction:

`RECALL != INFLUENCE`

Influence states:

- `CONSIDERED`
- `SUPPORTED_ACTION`
- `CONSTRAINED_ACTION`
- `CHANGED_ACTION`

Temporal repair must preserve old experience while allowing later evidence to change current applicability.

## 8. Mandatory ablations

- **A0 — No memory**
- **A1 — Flat retrieval**
- **A2 — Hydra retrieval without graph advantage**
- **A3 — Hydra graph memory**
- **A4 — Engram + Hydra causal memory**

Claims about graph benefit or Engram benefit require the relevant adjacent ablation.

## 9. Audit dimensions

Correctness:
- answer accuracy
- retrieval recall/ranking
- abstention
- knowledge-update correctness
- temporal ordering
- contradiction/premise handling
- cross-session reasoning

Systems:
- ingestion time
- memory-query latency p50/p95 where available
- end-to-end answer latency
- index/storage size
- restart/recovery behavior
- peak memory/CPU when measured

Integrity:
- no cross-agent contamination
- no benchmark leakage
- deterministic identifiers where required
- provenance reconstructability
- historical state preservation

Hydra-native value:
- graph model documented
- graph traversals/relationships used live
- capability or quality lost when Hydra graph behavior is removed
- exact HydraDB OSS commit reproducible by judges

## 10. Evidence states

```text
IMPLEMENTED   code exists
TESTED        deterministic/local test passed
DEPLOYED      running in target environment
SIMULATED     surrounding workload/environment is simulated
PROPOSED      designed but not implemented
UNKNOWN       not established
NOT_RUN       benchmark/ablation intentionally not executed, with reason
```

Benchmark subsets additionally record:

```text
coverage = FULL | SUBSET | SMOKE
n_examples = <integer>
dataset_filter = <exact selection rule>
```

## 11. Required run manifest

Every run directory must contain a machine-readable manifest with at least:

```json
{
  "run_id": "...",
  "started_at": "...",
  "git": {
    "submission_commit": "...",
    "engram_upstream_commit": "...",
    "hydradb_commit": "..."
  },
  "benchmark": {
    "name": "LongMemEval|LongMemEval-V2|BEAM|Engram-Causal",
    "source_commit": "...",
    "split": "...",
    "coverage": "FULL|SUBSET|SMOKE",
    "n_examples": 0
  },
  "models": {},
  "retrieval": {},
  "hydradb": {},
  "hardware": {},
  "metrics": {},
  "artifacts": [],
  "notes": []
}
```

No README benchmark number may exist without a traceable manifest and raw output.

## 12. Artifact layout

```text
audit/
  manifests/
  baseline-status.json
  claim-ledger.json

evidence/
  hydradb/
    oss-smoke/
    conformance/
  longmemeval/
    runs/
    reports/
  longmemeval-v2/
    runs/
    reports/
  beam/
    runs/
    reports/
  engram/
    causal/
    temporal-repair/
    isolation/
    ablations/
```

Raw artifacts are retained.

## 13. Claim ledger

Before any claim enters the README, demo script, submission form, landing page, or pitch, add it to `audit/claim-ledger.json`.

Approval requires matching splits/configuration, raw evidence, no benchmark leakage, reproducible commands, and wording no stronger than the evidence.

## 14. Application/use-case rule

```text
BEAM / LongMemEval / LongMemEval-V2
              ↓
      audited memory substrate
              ↓
        Engram semantics
              ↓
       HydraDB graph layer
              ↓
   application / product / demo
```

Applications demonstrate why the primitive matters. They do not redefine whether it works.

## 15. Current audit state

```text
Hack Hydra Track 03 alignment       DEFINED
Benchmark authority order           DEFINED
LongMemEval baseline                DEFINED / NOT_RUN
LongMemEval-V2 substrate            FULL MULTIMODAL VALIDATED / LOCAL-READER SCORE SMOKE
LongMemEval-V2 A3 smoke             TESTED / SMOKE / n_examples=1
LongMemEval-V2 official question    TESTED / SMOKE / n_examples=1
Official Small haystack isolation   TESTED / SMOKE / 100 trajectories
Bounded Hydra evidence storage      TESTED / SMOKE
Hydra evidence reconstruction       TESTED / SMOKE
BEAM baseline                       DEFINED / NOT_RUN
HydraDB OSS runtime                 TESTED
HydraDB restart durability          TESTED
HydraDB Bolt retrieval              TESTED
HydraDB benchmark graph integration TESTED / OFFICIAL-QUESTION SMOKE
A2 vs A3 graph ablation             TESTED / OFFICIAL-QUESTION SMOKE / n_examples=1
Graph capability advantage          TESTED / OFFICIAL-QUESTION SMOKE
A3 context-budget truncation        TESTED / SMOKE / 27277 -> 11265 tokens
A3 candidate-core ordering repair   TESTED / SMOKE / all 3 cores preserved
A3 repaired local-reader score      TESTED / SMOKE / score=0
Seed retrieval relevance failure    TESTED / SMOKE / gold state 1d56a4d6:11 missed
Seed ranker exact reproduction      TESTED / SMOKE / target rank=128
Answer-footer retrieval pollution   TESTED / SMOKE / target rank 128 -> 45
State-local-only retrieval           TESTED / SMOKE / target rank=151
Seed scorer replacement              REQUIRED / NOT_IMPLEMENTED
Current seed top3 state recall       TESTED / enterprise-small literal cohort / 59/104 = 56.73%
Phrase seed top3 state recall        TESTED / same cohort / 66/104 = 63.46%
Phrase top3 trajectory recall        TESTED / same cohort / 87/104 = 83.65%
Trajectory/fusion graph diagnostic   TESTED / enterprise-small literal cohort / n=104
Current diverse trajectory recall    TESTED / 77/104 = 74.04%
Current diverse exact seed recall    TESTED / 67/104 = 64.42%
Current diverse graph1 recoverable   TESTED / 71/104 = 68.27%
Phrase diverse trajectory recall     TESTED / 87/104 = 83.65%
Phrase diverse exact seed recall     TESTED / 74/104 = 71.15%
Phrase diverse graph1 recoverable    TESTED / 78/104 = 75.00%
RRF diverse graph1 recoverable       TESTED / 76/104 = 73.08%
A3 graph-radius frontier              TESTED / enterprise-small literal cohort / n=104
Phrase diverse exact seed             74/104 = 71.15%
Phrase diverse radius-1 recoverable   78/104 = 75.00%
Phrase diverse radius-2 recoverable   78/104 = 75.00%
Phrase diverse radius-3 recoverable   81/104 = 77.88%
Phrase diverse radius-5 recoverable   83/104 = 79.81%
Phrase diverse trajectory upper bound 87/104 = 83.65%
A3 production graph radius            DECIDED / radius=1
A3 production seed policy             DECIDED / phrase-aware trajectory-diverse
A3 production retriever               IMPLEMENTED / TESTED / phrase-diverse + radius=1
A3 selector frozen reproduction        PASS / exact selections 104/104 / mismatches=0
A2/A3 selector control                 PASS / identical top-3 seeds
A2 live Hydra exact-state path         PASS / reads=3 / graph-neighbors=0
A3 live Hydra radius-1 path            PASS / reads=9 / graph-neighbors=6
A3 live candidate vertex parity        PASS / A2=A3 / n=3
A3 context ordering                    PASS / candidate-core-first
Hydra multi-question graph replay    REQUIRED / NOT_RUN
Benchmark answer quality            TESTED / SMOKE / n_examples=1 / A2=0 A3=0
Benchmark quality advantage         NOT OBSERVED / SMOKE / n_examples=1
Engram causal proof on Hydra        PROPOSED
Temporal repair                     PROPOSED
Submission repo eligibility         PASS — fresh repository
Application layer                   OUT OF SCOPE UNTIL BASELINE PATH RUNS
```

PRISM-12 live Hydra replay                  PASS / TESTED / 12-question deterministic mechanism subset
PRISM-12 exact-seed preservation             PASS / 4 of 4
PRISM-12 radius-1-only live graph gains       PASS / 4 of 4 / A2 miss -> A3 live recovery
PRISM-12 radius-1 negative controls           PASS / 4 of 4 remained unrecovered
PRISM-12 mechanism expectation parity         PASS / 12 of 12
PRISM-12 diagnostic live evidence hits        A2=4/12 / A3=8/12 / STRATIFIED SUBSET, NOT BENCHMARK RECALL
PRISM-12 graph execution                      LIVE HYDRA / NEXT_STATE / radius=1
PRISM-13 A0 no-memory control                PASS / TESTED / official LongMemEval-V2 no_retrieval
PRISM-13 A0 empty memory contexts             PASS / 12 of 12
PRISM-13 A1 non-Hydra flat memory             PASS / TESTED / local prepared-state backend
PRISM-13 A1 frozen selector parity             PASS / 12 of 12 / phrase_trajectory_bm25_v1 / top_k=3
PRISM-13 A1 local state reads                  PASS / 36 total / 3 per question
PRISM-13 A1 Hydra driver attempts              PASS / 0
PRISM-13 A1 Hydra state reads                  PASS / 0
PRISM-13 A1 Hydra chunk reads                  PASS / 0
PRISM-13 A1 graph traversal                    PASS / 0 neighbors
PRISM-13 A2/A3 frozen semantics                PASS / UNCHANGED
PRISM-13 coverage                              SUBSET / deterministic 12-question mechanism cohort
PRISM-13 reader evaluation                     NOT_RUN / control-structure proof only
