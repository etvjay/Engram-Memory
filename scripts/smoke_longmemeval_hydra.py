#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


def load_trajectory(path: Path, trajectory_id: str | None) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            if trajectory_id is None or item.get("id") == trajectory_id:
                return item
    raise RuntimeError(f"Trajectory not found: {trajectory_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Real LongMemEval-V2 -> Engram -> Hydra smoke")
    parser.add_argument("--trajectory-id", default=None)
    parser.add_argument("--query", default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    lme_root = Path(os.environ["LONGMEMEVAL_V2_ROOT"]).expanduser().resolve()
    data_root = Path(os.environ["LONGMEMEVAL_V2_DATA_ROOT"]).expanduser().resolve()
    trajectories_path = data_root / "trajectories.jsonl"

    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(lme_root))

    from engram.longmemeval.hydra_memory import EngramHydraMemory

    trajectory = load_trajectory(trajectories_path, args.trajectory_id)
    trajectory_id = str(trajectory["id"])
    raw_goal = trajectory.get("goal")
    if isinstance(raw_goal, str) and raw_goal.strip():
        fallback_query = raw_goal
    else:
        metadata = trajectory.get("metadata")
        original_goal = metadata.get("original_goal") if isinstance(metadata, dict) else None
        if isinstance(original_goal, list):
            fallback_query = " ".join(x for x in original_goal if isinstance(x, str))
        elif isinstance(original_goal, str):
            fallback_query = original_goal
        else:
            fallback_query = trajectory_id
    query = args.query or fallback_query

    memory = EngramHydraMemory(
        {
            "bolt_uri": "bolt://127.0.0.1:7687",
            "database": "default",
            "token_file_env": "ENGRAM_HYDRA_TOKEN_FILE",
            "data_root_env": "LONGMEMEVAL_V2_DATA_ROOT",
            "retrieval_mode": "graph",
            "candidate_top_k": 1,
            "include_images": True,
            "max_state_chars": 4000,
        }
    )

    print(f"TRAJECTORY_ID={trajectory_id}")
    print(f"QUERY={query}")
    memory.insert(trajectory)
    print("INGEST=PASS")

    context = memory.query(query)
    debug = memory.last_query_debug
    print("QUERY=PASS")
    print(json.dumps(debug, indent=2, sort_keys=True))

    assert context, "Engram returned no memory context"
    assert int(debug.get("hydra_state_reads", 0)) > 0, debug
    states = trajectory.get("states") or trajectory.get("content")
    if isinstance(states, list) and len(states) > 1:
        assert int(debug.get("graph_neighbor_states", 0)) > 0, debug
    assert any(item.get("type") == "text" for item in context), context
    image_items = [item for item in context if item.get("type") == "image"]
    for item in image_items:
        assert Path(str(item["value"])).is_file(), item

    print(f"CONTEXT_ITEMS={len(context)}")
    print(f"IMAGE_ITEMS={len(image_items)}")
    print("ENGRAM_HYDRA_MEMORY_SMOKE=PASS")


if __name__ == "__main__":
    main()
