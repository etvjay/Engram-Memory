# EngramHydraMemory — A2/A3 LongMemEval-V2 backend

Status: implementation branch `a3-engram-hydra-memory`.

## Contract

`EngramHydraMemory` implements the official LongMemEval-V2 `Memory` interface without modifying the benchmark repository.

- `insert(trajectory)` normalizes a real LongMemEval-V2 trajectory with the benchmark's own `prepare_trajectory_insert` helper.
- Trajectories and states are written into HydraDB with deterministic int64-range vertex ids.
- Consecutive states are connected with typed `NEXT_STATE` relationships.
- `query(question, query_image=None)` uses only the public query text for lexical candidate selection.
- The selected state is then read back from HydraDB.
- `retrieval_mode=graph` additionally traverses typed `NEXT_STATE` relationships to recover surrounding execution context.
- Returned memory contains text context plus existing screenshot paths.

No question id, question type, gold answer, evidence label, evaluator metadata, or benchmark-private metadata is used by the backend.

## A2 / A3 separation

Both modes use the same candidate selector.

- **A2 / flat**: selected state is read from HydraDB; graph neighbors are not traversed.
- **A3 / graph**: selected state is read from HydraDB and expanded through `NEXT_STATE` predecessors/successors.

This keeps candidate selection fixed so graph context is the material ablation.

## Required environment

```bash
export LONGMEMEVAL_V2_ROOT="$HOME/work/LongMemEval-V2"
export LONGMEMEVAL_V2_DATA_ROOT="$LONGMEMEVAL_V2_ROOT/data/longmemeval-v2-full"
export ENGRAM_HYDRA_TOKEN_FILE="$HOME/work/hydradb/.hydradb/auth-token"
```

The live Hydra runtime used by the audited EC2 path resolves Bolt database `default` to namespace `engram`, graph id `engram-memory`, cell `cell-0`.

## Smoke

```bash
source .venv-hydra/bin/activate
python -m pip install -r requirements-hydra-memory.txt
python scripts/smoke_longmemeval_hydra.py
```

Success requires:

```text
INGEST=PASS
QUERY=PASS
graph_neighbor_states > 0   # for trajectories with >1 state
ENGRAM_HYDRA_MEMORY_SMOKE=PASS
```

## Official harness wrapper

The wrapper registers `memory_type=engram_hydra` before invoking the pinned official harness:

```bash
python scripts/run_longmemeval_v2.py \
  --domain web \
  --questions-path "$LONGMEMEVAL_V2_DATA_ROOT/questions.jsonl" \
  --haystack-path "$LONGMEMEVAL_V2_DATA_ROOT/haystacks/lme_v2_small.json" \
  --trajectories-path "$LONGMEMEVAL_V2_DATA_ROOT/trajectories.jsonl" \
  --memory-config-path configs/longmemeval-v2/engram_hydra_graph.json \
  --output-dir evidence/longmemeval-v2/a3-web \
  --model '<reader-model>'
```

Run web and enterprise according to the benchmark's official evaluation procedure. Report only results produced by the pinned benchmark harness.
