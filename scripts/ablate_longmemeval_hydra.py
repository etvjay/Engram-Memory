#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

_STATE_INDEX_RE = re.compile(r"^State index: (\d+)$", re.MULTILINE)


def load_trajectory(path: Path, trajectory_id: str) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("id") == trajectory_id:
                return item
    raise RuntimeError(f"Trajectory not found: {trajectory_id}")


def visible_goal(trajectory: dict[str, object]) -> str:
    raw_goal = trajectory.get("goal")
    if isinstance(raw_goal, str) and raw_goal.strip():
        return raw_goal
    metadata = trajectory.get("metadata")
    original_goal = metadata.get("original_goal") if isinstance(metadata, dict) else None
    if isinstance(original_goal, list):
        text = " ".join(x for x in original_goal if isinstance(x, str)).strip()
        if text:
            return text
    if isinstance(original_goal, str) and original_goal.strip():
        return original_goal
    return str(trajectory["id"])


def text_state_indices(context: list[dict[str, str]]) -> list[int]:
    values: list[int] = []
    for item in context:
        if item.get("type") != "text":
            continue
        match = _STATE_INDEX_RE.search(str(item.get("value", "")))
        if match:
            values.append(int(match.group(1)))
    return values


def image_count(context: list[dict[str, str]]) -> int:
    return sum(1 for item in context if item.get("type") == "image")


def run_query(memory: Any, query: str) -> tuple[list[dict[str, str]], dict[str, object], float]:
    started = time.perf_counter()
    context = memory.query(query)
    elapsed = time.perf_counter() - started
    return context, memory.last_query_debug, elapsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Controlled A2 vs A3 LongMemEval-V2 Hydra graph ablation"
    )
    parser.add_argument("--trajectory-id", default="00332982")
    parser.add_argument("--query", default=None)
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    lme_root = Path(os.environ["LONGMEMEVAL_V2_ROOT"]).expanduser().resolve()
    data_root = Path(os.environ["LONGMEMEVAL_V2_DATA_ROOT"]).expanduser().resolve()
    trajectories_path = data_root / "trajectories.jsonl"

    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(lme_root))

    from engram.longmemeval.hydra_memory import EngramHydraMemory

    trajectory = load_trajectory(trajectories_path, args.trajectory_id)
    query = args.query or visible_goal(trajectory)

    common = {
        "bolt_uri": "bolt://127.0.0.1:7687",
        "database": "default",
        "token_file_env": "ENGRAM_HYDRA_TOKEN_FILE",
        "data_root_env": "LONGMEMEVAL_V2_DATA_ROOT",
        "candidate_top_k": 1,
        "include_images": True,
        "max_state_chars": 4000,
    }

    flat = EngramHydraMemory({**common, "retrieval_mode": "flat"})
    graph = EngramHydraMemory({**common, "retrieval_mode": "graph"})

    flat.insert(trajectory)
    graph.insert(trajectory)
    print("SHARED_INGEST=PASS")

    flat_context, flat_debug, flat_seconds = run_query(flat, query)
    graph_context, graph_debug, graph_seconds = run_query(graph, query)

    flat_candidates = list(flat_debug.get("candidate_vertex_ids", []))
    graph_candidates = list(graph_debug.get("candidate_vertex_ids", []))
    assert flat_candidates == graph_candidates, (flat_debug, graph_debug)
    assert flat_candidates, "Ablation produced no lexical candidate"

    assert flat_debug.get("retrieval_mode") == "flat", flat_debug
    assert graph_debug.get("retrieval_mode") == "graph", graph_debug
    assert int(flat_debug.get("graph_neighbor_states", -1)) == 0, flat_debug
    assert int(graph_debug.get("graph_neighbor_states", 0)) > 0, graph_debug

    flat_reads = int(flat_debug.get("hydra_state_reads", 0))
    graph_reads = int(graph_debug.get("hydra_state_reads", 0))
    assert flat_reads > 0, flat_debug
    assert graph_reads > flat_reads, (flat_debug, graph_debug)

    flat_indices = text_state_indices(flat_context)
    graph_indices = text_state_indices(graph_context)
    assert flat_indices, flat_context
    assert set(flat_indices).issubset(set(graph_indices)), (flat_indices, graph_indices)
    assert set(graph_indices) - set(flat_indices), (flat_indices, graph_indices)

    result = {
        "trajectory_id": args.trajectory_id,
        "query": query,
        "controlled_variables": {
            "candidate_selector": "local lexical overlap",
            "candidate_top_k": 1,
            "candidate_vertex_ids_equal": True,
            "candidate_vertex_ids": flat_candidates,
            "same_trajectory": True,
            "same_query": True,
            "same_hydra_database": "default",
        },
        "a2_flat": {
            **flat_debug,
            "state_indices": flat_indices,
            "image_items": image_count(flat_context),
            "query_seconds": flat_seconds,
        },
        "a3_graph": {
            **graph_debug,
            "state_indices": graph_indices,
            "image_items": image_count(graph_context),
            "query_seconds": graph_seconds,
        },
        "delta": {
            "additional_hydra_state_reads": graph_reads - flat_reads,
            "additional_graph_neighbor_states": int(graph_debug["graph_neighbor_states"]),
            "additional_state_indices": sorted(set(graph_indices) - set(flat_indices)),
            "additional_context_items": len(graph_context) - len(flat_context),
            "additional_image_items": image_count(graph_context) - image_count(flat_context),
            "capability_loss_without_graph": "surrounding execution-state context is absent in A2 flat mode",
        },
    }

    if args.output_json:
        output = Path(args.output_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"TRAJECTORY_ID={args.trajectory_id}")
    print(f"CANDIDATE_VERTEX_IDS_EQUAL={flat_candidates == graph_candidates}")
    print("A2_FLAT=" + json.dumps(result["a2_flat"], sort_keys=True))
    print("A3_GRAPH=" + json.dumps(result["a3_graph"], sort_keys=True))
    print("DELTA=" + json.dumps(result["delta"], sort_keys=True))
    print("A2_A3_CONTROLLED_ABLATION=PASS")


if __name__ == "__main__":
    main()
