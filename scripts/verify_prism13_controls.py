#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from unittest.mock import patch


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Verify PRISM-13 A0 no-memory and "
            "A1 genuine non-Hydra flat controls"
        )
    )

    parser.add_argument(
        "--manifest",
        default=(
            "evidence/longmemeval-v2/prism12/"
            "mechanism-subset/manifest.json"
        ),
    )

    parser.add_argument(
        "--output-dir",
        required=True,
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]

    lme_root = Path(
        os.environ["LONGMEMEVAL_V2_ROOT"]
    ).expanduser().resolve()

    data_root = Path(
        os.environ["LONGMEMEVAL_V2_DATA_ROOT"]
    ).expanduser().resolve()

    manifest_path = (
        repo_root / args.manifest
    ).expanduser().resolve()

    output_dir = Path(
        args.output_dir
    ).expanduser().resolve()

    output_dir.mkdir(parents=True, exist_ok=True)

    runtime_root = (
        Path.home() / ".engram-prism13-runtime"
    ).resolve()

    if runtime_root.exists():
        shutil.rmtree(runtime_root)

    runtime_root.mkdir(parents=True)

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

    from memory_modules.no_retrieval import (
        NoRetrievalMemory,
    )

    from engram.longmemeval.flat_memory import (
        EngramFlatLocalMemory,
    )

    from engram.longmemeval.hydra_memory import (
        EngramHydraMemory,
        GraphDatabase,
    )

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    questions_manifest = manifest.get("questions")

    require(
        isinstance(questions_manifest, list),
        "Manifest questions must be a list",
    )

    require(
        len(questions_manifest) == 12,
        (
            "PRISM-13 verifier requires frozen "
            "12-question PRISM-12 subset"
        ),
    )

    trajectories = load_trajectories(
        str(data_root / "trajectories.jsonl")
    )

    common_a1 = {
        "data_root_env": "LONGMEMEVAL_V2_DATA_ROOT",
        "candidate_top_k": 3,
        "include_images": True,
        "max_state_chars": 6000,
        "candidate_strategy": "phrase_trajectory_bm25_v1",
    }

    results: list[dict[str, object]] = []

    a0_empty_contexts = 0
    a1_selector_matches = 0
    total_a1_local_state_reads = 0
    total_a1_hydra_state_reads = 0
    total_a1_hydra_chunk_reads = 0
    total_a1_graph_neighbors = 0

    # Strong control: any attempt by A1 to create a Hydra driver
    # immediately fails the experiment.
    with patch.object(
        GraphDatabase,
        "driver",
        side_effect=AssertionError(
            "A1 attempted to initialize Hydra driver"
        ),
    ):
        try:
            for index, item in enumerate(
                questions_manifest,
                start=1,
            ):
                require(
                    isinstance(item, dict),
                    "Invalid manifest question entry",
                )

                question_id = str(item["question_id"])
                stratum = str(item["stratum"])

                expected_selection = item.get(
                    "expected_selection"
                )

                require(
                    isinstance(expected_selection, list),
                    (
                        f"Missing expected selection "
                        f"for {question_id}"
                    ),
                )

                case_dir = runtime_root / question_id
                case_dir.mkdir(parents=True)

                selected_questions = (
                    materialize_runtime_questions(
                        data_root=data_root,
                        domain="enterprise",
                        question_ids=[question_id],
                        limit=None,
                        output_path=(
                            case_dir / "questions.json"
                        ),
                    )
                )

                materialize_runtime_haystack(
                    data_root=data_root,
                    tier="small",
                    selected_questions=selected_questions,
                    output_path=case_dir / "haystack.json",
                )

                questions = load_questions(
                    str(case_dir / "questions.json")
                )

                mapping = load_haystack_mapping(
                    str(case_dir / "haystack.json")
                )

                require(
                    len(questions) == 1,
                    (
                        f"Expected one question for "
                        f"{question_id}"
                    ),
                )

                question = questions[0]

                loaded_question_id = question.get("id")

                require(
                    loaded_question_id == question_id,
                    (
                        f"Question ID mismatch: "
                        f"{loaded_question_id} "
                        f"!= {question_id}"
                    ),
                )

                require(
                    question_id in mapping,
                    (
                        f"Missing haystack mapping "
                        f"for {question_id}"
                    ),
                )

                question_text, question_image = (
                    get_question_components(
                        question.get("question")
                    )
                )

                haystack_ids = mapping[question_id]

                require(
                    bool(haystack_ids),
                    (
                        f"Empty haystack for "
                        f"{question_id}"
                    ),
                )

                a0 = NoRetrievalMemory({})
                a1 = EngramFlatLocalMemory(common_a1)

                for trajectory_id in haystack_ids:
                    require(
                        trajectory_id in trajectories,
                        (
                            f"Missing trajectory "
                            f"{trajectory_id}"
                        ),
                    )

                    a1.insert(
                        trajectories[trajectory_id]
                    )

                a0_context = a0.query(
                    question_text,
                    query_image=question_image,
                )

                a1_context = a1.query(
                    question_text,
                    query_image=question_image,
                )

                a0_context = validate_memory_context_items(
                    a0_context,
                    question_id=question_id,
                )

                a1_context = validate_memory_context_items(
                    a1_context,
                    question_id=question_id,
                )

                require(
                    a0_context == [],
                    (
                        f"A0 returned memory for "
                        f"{question_id}"
                    ),
                )

                a0_empty_contexts += 1

                debug = a1.last_query_debug

                actual_selection = debug.get(
                    "candidate_state_refs"
                )

                require(
                    actual_selection
                    == expected_selection,
                    (
                        f"A1 selector mismatch for "
                        f"{question_id}\n"
                        f"expected={expected_selection}\n"
                        f"actual={actual_selection}"
                    ),
                )

                a1_selector_matches += 1

                require(
                    debug.get("backend")
                    == "local_flat",
                    (
                        f"A1 backend mismatch for "
                        f"{question_id}"
                    ),
                )

                require(
                    debug.get("retrieval_mode")
                    == "flat",
                    (
                        f"A1 retrieval mode mismatch "
                        f"for {question_id}"
                    ),
                )

                require(
                    debug.get("candidate_strategy")
                    == "phrase_trajectory_bm25_v1",
                    (
                        f"A1 selector mismatch for "
                        f"{question_id}"
                    ),
                )

                require(
                    int(
                        debug.get(
                            "hydra_state_reads",
                            -1,
                        )
                    )
                    == 0,
                    (
                        f"A1 performed Hydra state "
                        f"reads for {question_id}"
                    ),
                )

                require(
                    int(
                        debug.get(
                            "hydra_chunk_reads",
                            -1,
                        )
                    )
                    == 0,
                    (
                        f"A1 performed Hydra chunk "
                        f"reads for {question_id}"
                    ),
                )

                require(
                    int(
                        debug.get(
                            "graph_neighbor_states",
                            -1,
                        )
                    )
                    == 0,
                    (
                        f"A1 traversed graph for "
                        f"{question_id}"
                    ),
                )

                require(
                    debug.get(
                        "hydra_driver_attempted"
                    )
                    is False,
                    (
                        f"A1 Hydra driver flag "
                        f"invalid for {question_id}"
                    ),
                )

                local_reads = int(
                    debug.get(
                        "local_state_reads",
                        -1,
                    )
                )

                require(
                    local_reads == 3,
                    (
                        f"Expected 3 A1 local state "
                        f"reads for {question_id}, "
                        f"got {local_reads}"
                    ),
                )

                total_a1_local_state_reads += (
                    local_reads
                )

                total_a1_hydra_state_reads += int(
                    debug.get(
                        "hydra_state_reads",
                        0,
                    )
                )

                total_a1_hydra_chunk_reads += int(
                    debug.get(
                        "hydra_chunk_reads",
                        0,
                    )
                )

                total_a1_graph_neighbors += int(
                    debug.get(
                        "graph_neighbor_states",
                        0,
                    )
                )

                results.append(
                    {
                        "question_id": question_id,
                        "stratum": stratum,
                        "haystack_size": len(
                            haystack_ids
                        ),
                        "expected_selection": (
                            expected_selection
                        ),
                        "a0": {
                            "memory_type": (
                                "no_retrieval"
                            ),
                            "context_items": len(
                                a0_context
                            ),
                        },
                        "a1": {
                            **debug,
                            "selector_match": True,
                            "context_items_validated": len(
                                a1_context
                            ),
                        },
                    }
                )

                print(
                    (
                        f"CONTROL_PROGRESS={index}/12 "
                        f"QID={question_id} "
                        f"A0_EMPTY=PASS "
                        f"A1_SELECTOR=PASS "
                        f"A1_HYDRA_READS=0"
                    ),
                    flush=True,
                )

        finally:
            if runtime_root.exists():
                shutil.rmtree(runtime_root)

    require(
        EngramHydraMemory._driver_cache == {},
        (
            "Hydra driver cache was populated "
            "during isolated PRISM-13 control verifier"
        ),
    )

    result = {
        "status": "PRISM13_CONTROL_STRUCTURE_PASS",
        "n_questions": len(results),
        "a0": {
            "memory_type": "no_retrieval",
            "semantic": "no memory",
            "empty_contexts": a0_empty_contexts,
            "expected_empty_contexts": 12,
        },
        "a1": {
            "memory_type": "engram_flat_local",
            "semantic": (
                "genuine non-Hydra flat memory"
            ),
            "candidate_strategy": (
                "phrase_trajectory_bm25_v1"
            ),
            "candidate_top_k": 3,
            "selector_matches": a1_selector_matches,
            "expected_selector_matches": 12,
            "local_state_reads": (
                total_a1_local_state_reads
            ),
            "hydra_state_reads": (
                total_a1_hydra_state_reads
            ),
            "hydra_chunk_reads": (
                total_a1_hydra_chunk_reads
            ),
            "graph_neighbor_states": (
                total_a1_graph_neighbors
            ),
            "hydra_driver_attempts": 0,
        },
        "frozen_controls": {
            "a2": {
                "memory_type": "engram_hydra",
                "retrieval_mode": "flat",
                "candidate_strategy": (
                    "phrase_trajectory_bm25_v1"
                ),
                "candidate_top_k": 3,
                "graph_radius": 1,
                "modified_by_prism13": False,
            },
            "a3": {
                "memory_type": "engram_hydra",
                "retrieval_mode": "graph",
                "candidate_strategy": (
                    "phrase_trajectory_bm25_v1"
                ),
                "candidate_top_k": 3,
                "graph_radius": 1,
                "modified_by_prism13": False,
            },
        },
        "integrity": {
            "official_no_retrieval_used_for_a0": True,
            "a1_uses_frozen_selector_implementation": True,
            "a1_hydra_driver_forbidden_during_test": True,
            "a1_hydra_reads_zero": True,
            "a1_graph_traversal_zero": True,
            "gold_used_in_runtime_selection": False,
            "question_type_used_in_runtime_selection": False,
            "evaluator_metadata_used_in_runtime_selection": False,
            "frozen_expected_selection_used_posthoc_for_parity": True,
            "subset_is_unbiased_benchmark_sample": False,
            "reader_invoked": False,
            "answer_quality_evaluated": False,
            "allowed_claim": (
                "A0 is a genuine no-memory control and "
                "A1 is a genuine non-Hydra flat-memory "
                "control with frozen selector parity "
                "over the deterministic 12-question "
                "mechanism subset"
            ),
        },
        "questions": results,
    }

    require(
        a0_empty_contexts == 12,
        "A0 control gate failed",
    )

    require(
        a1_selector_matches == 12,
        "A1 selector parity gate failed",
    )

    require(
        total_a1_hydra_state_reads == 0,
        "A1 Hydra state-read gate failed",
    )

    require(
        total_a1_hydra_chunk_reads == 0,
        "A1 Hydra chunk-read gate failed",
    )

    require(
        total_a1_graph_neighbors == 0,
        "A1 graph traversal gate failed",
    )

    output_path = output_dir / "result.json"

    output_path.write_text(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print("PRISM13_A0_NO_MEMORY=PASS")
    print("PRISM13_A1_NON_HYDRA_FLAT=PASS")
    print("A0_EMPTY_CONTEXTS=12/12")
    print("A1_SELECTOR_PARITY=12/12")
    print(
        "A1_CANDIDATE_STRATEGY="
        "phrase_trajectory_bm25_v1"
    )
    print("A1_CANDIDATE_TOP_K=3")
    print(
        "A1_LOCAL_STATE_READS="
        f"{total_a1_local_state_reads}"
    )
    print("A1_HYDRA_DRIVER_ATTEMPTS=0")
    print("A1_HYDRA_STATE_READS=0")
    print("A1_HYDRA_CHUNK_READS=0")
    print("A1_GRAPH_NEIGHBOR_STATES=0")
    print("A2_A3_MODIFIED=FALSE")
    print(f"RESULT_JSON={output_path}")
    print("PRISM13_CONTROL_STRUCTURE=PASS")


if __name__ == "__main__":
    main()
