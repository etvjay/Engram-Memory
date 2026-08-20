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

_TRAJECTORY_RE = re.compile(r"^Trajectory: (.+)$", re.MULTILINE)
_STATE_INDEX_RE = re.compile(r"^State index: (\d+)$", re.MULTILINE)


def context_state_refs(context: list[dict[str, str]]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for item in context:
        if item.get("type") != "text":
            continue
        value = str(item.get("value", ""))
        trajectory_match = _TRAJECTORY_RE.search(value)
        state_match = _STATE_INDEX_RE.search(value)
        if trajectory_match and state_match:
            refs.append(
                {
                    "trajectory_id": trajectory_match.group(1),
                    "state_index": int(state_match.group(1)),
                }
            )
    return refs


def image_count(context: list[dict[str, str]]) -> int:
    return sum(1 for item in context if item.get("type") == "image")


def run_query(
    memory: Any,
    *,
    question_text: str,
    question_image: str | None,
) -> tuple[list[dict[str, str]], dict[str, object], float]:
    started = time.perf_counter()
    context = memory.query(question_text, query_image=question_image)
    elapsed = time.perf_counter() - started
    return context, memory.last_query_debug, elapsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Official LongMemEval-V2 question/haystack A2 vs A3 retrieval ablation"
        )
    )
    parser.add_argument("--domain", choices=["web", "enterprise"], default="enterprise")
    parser.add_argument("--tier", choices=["small", "medium"], default="small")
    parser.add_argument("--question-id", default=None)
    parser.add_argument("--candidate-top-k", type=int, default=3)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    lme_root = Path(os.environ["LONGMEMEVAL_V2_ROOT"]).expanduser().resolve()
    data_root = Path(os.environ["LONGMEMEVAL_V2_DATA_ROOT"]).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    runtime_dir = output_dir / "runtime_inputs"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(lme_root))

    from data.public_data import (
        materialize_runtime_haystack,
        materialize_runtime_questions,
    )
    from evaluation.harness import (
        get_question_components,
        load_haystack_mapping,
        load_questions,
        load_trajectories,
        validate_memory_context_items,
    )
    from engram.longmemeval.hydra_memory import EngramHydraMemory

    requested_ids = [args.question_id] if args.question_id else None
    selected_questions = materialize_runtime_questions(
        data_root=data_root,
        domain=args.domain,
        question_ids=requested_ids,
        limit=None if requested_ids else 1,
        output_path=runtime_dir / "questions.json",
    )
    materialize_runtime_haystack(
        data_root=data_root,
        tier=args.tier,
        selected_questions=selected_questions,
        output_path=runtime_dir / "haystack.json",
    )

    questions = load_questions(str(runtime_dir / "questions.json"))
    haystack_mapping = load_haystack_mapping(str(runtime_dir / "haystack.json"))
    trajectories = load_trajectories(str(data_root / "trajectories.jsonl"))

    if len(questions) != 1:
        raise RuntimeError(f"Expected exactly one materialized question, got {len(questions)}")

    question = questions[0]
    question_id = question.get("id")
    if not isinstance(question_id, str) or not question_id:
        raise RuntimeError("Selected question has invalid id")
    if question_id not in haystack_mapping:
        raise RuntimeError(f"Missing haystack for selected question {question_id}")

    question_text, question_image = get_question_components(question.get("question"))
    haystack_ids = haystack_mapping[question_id]
    if not haystack_ids:
        raise RuntimeError(f"Empty haystack for selected question {question_id}")

    common = {
        "bolt_uri": "bolt://127.0.0.1:7687",
        "database": "default",
        "token_file_env": "ENGRAM_HYDRA_TOKEN_FILE",
        "data_root_env": "LONGMEMEVAL_V2_DATA_ROOT",
        "candidate_top_k": args.candidate_top_k,
        "include_images": True,
        "max_state_chars": 6000,
    }

    flat = EngramHydraMemory({**common, "retrieval_mode": "flat"})
    graph = EngramHydraMemory({**common, "retrieval_mode": "graph"})

    ingest_started = time.perf_counter()
    for index, trajectory_id in enumerate(haystack_ids, start=1):
        if trajectory_id not in trajectories:
            raise RuntimeError(f"Missing trajectory {trajectory_id} for question {question_id}")
        trajectory = trajectories[trajectory_id]
        flat.insert(trajectory)
        graph.insert(trajectory)
        if index == 1 or index % 10 == 0 or index == len(haystack_ids):
            print(f"INGEST_PROGRESS={index}/{len(haystack_ids)}", flush=True)
    ingest_seconds = time.perf_counter() - ingest_started
    print("HAYSTACK_INGEST=PASS", flush=True)

    flat_context, flat_debug, flat_seconds = run_query(
        flat,
        question_text=question_text,
        question_image=question_image,
    )
    graph_context, graph_debug, graph_seconds = run_query(
        graph,
        question_text=question_text,
        question_image=question_image,
    )

    flat_context = validate_memory_context_items(flat_context, question_id=question_id)
    graph_context = validate_memory_context_items(graph_context, question_id=question_id)

    flat_candidates = list(flat_debug.get("candidate_vertex_ids", []))
    graph_candidates = list(graph_debug.get("candidate_vertex_ids", []))
    if flat_candidates != graph_candidates:
        raise AssertionError((flat_debug, graph_debug))
    if not flat_candidates:
        raise AssertionError("Official question produced no lexical candidates")

    if flat_debug.get("retrieval_mode") != "flat":
        raise AssertionError(flat_debug)
    if graph_debug.get("retrieval_mode") != "graph":
        raise AssertionError(graph_debug)
    if int(flat_debug.get("graph_neighbor_states", -1)) != 0:
        raise AssertionError(flat_debug)
    if int(flat_debug.get("hydra_state_reads", 0)) <= 0:
        raise AssertionError(flat_debug)
    if int(graph_debug.get("hydra_state_reads", 0)) <= 0:
        raise AssertionError(graph_debug)

    flat_refs = context_state_refs(flat_context)
    graph_refs = context_state_refs(graph_context)
    flat_ref_keys = {(str(x["trajectory_id"]), int(x["state_index"])) for x in flat_refs}
    graph_ref_keys = {(str(x["trajectory_id"]), int(x["state_index"])) for x in graph_refs}
    additional_refs = sorted(graph_ref_keys - flat_ref_keys)

    graph_neighbors = int(graph_debug.get("graph_neighbor_states", 0))
    graph_delta_present = bool(additional_refs) and graph_neighbors > 0

    result = {
        "benchmark": {
            "name": "LongMemEval-V2",
            "domain": args.domain,
            "tier": args.tier,
            "question_id": question_id,
            "question_text": question_text,
            "question_image": question_image,
            "haystack_size": len(haystack_ids),
            "question_selection": (
                "exact --question-id" if args.question_id else f"first {args.domain} question in questions.jsonl"
            ),
        },
        "integrity": {
            "gold_answer_used_by_memory": False,
            "question_type_used_by_memory": False,
            "evaluator_metadata_used_by_memory": False,
            "haystack_scope_exact": True,
        },
        "controlled_variables": {
            "same_question": True,
            "same_question_image": True,
            "same_haystack": True,
            "same_candidate_selector": True,
            "candidate_selector": "local lexical overlap",
            "candidate_top_k": args.candidate_top_k,
            "candidate_vertex_ids_equal": True,
            "candidate_vertex_ids": flat_candidates,
            "same_hydra_database": "default",
        },
        "ingestion": {
            "haystack_trajectories": len(haystack_ids),
            "seconds": ingest_seconds,
        },
        "a2_flat": {
            **flat_debug,
            "state_refs": flat_refs,
            "image_items": image_count(flat_context),
            "query_seconds": flat_seconds,
        },
        "a3_graph": {
            **graph_debug,
            "state_refs": graph_refs,
            "image_items": image_count(graph_context),
            "query_seconds": graph_seconds,
        },
        "delta": {
            "graph_delta_present": graph_delta_present,
            "additional_state_refs": [
                {"trajectory_id": trajectory_id, "state_index": state_index}
                for trajectory_id, state_index in additional_refs
            ],
            "additional_hydra_state_reads": int(graph_debug.get("hydra_state_reads", 0))
            - int(flat_debug.get("hydra_state_reads", 0)),
            "additional_graph_neighbor_states": graph_neighbors,
            "additional_context_items": len(graph_context) - len(flat_context),
            "additional_image_items": image_count(graph_context) - image_count(flat_context),
        },
        "claims": {
            "official_question_path_exercised": True,
            "official_haystack_scope_exercised": True,
            "graph_capability_delta_present": graph_delta_present,
            "answer_quality_evaluated": False,
        },
    }

    output_path = output_dir / "result.json"
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"QUESTION_ID={question_id}")
    print(f"DOMAIN={args.domain}")
    print(f"TIER={args.tier}")
    print(f"HAYSTACK_SIZE={len(haystack_ids)}")
    print(f"CANDIDATE_VERTEX_IDS_EQUAL={flat_candidates == graph_candidates}")
    print(f"A2_HYDRA_STATE_READS={flat_debug.get('hydra_state_reads')}")
    print(f"A3_HYDRA_STATE_READS={graph_debug.get('hydra_state_reads')}")
    print(f"A3_GRAPH_NEIGHBOR_STATES={graph_neighbors}")
    print(f"GRAPH_DELTA_PRESENT={graph_delta_present}")
    print(f"RESULT_JSON={output_path}")
    print("OFFICIAL_QUESTION_A2_A3_RETRIEVAL=PASS")


if __name__ == "__main__":
    main()
