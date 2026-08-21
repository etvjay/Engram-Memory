#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


SCHEMA_VERSION = "engram-evidence-index-v1"
REPOSITORY = "etvjay/Engram-Memory"

DATASET_MANIFEST = (
    "audit/manifests/"
    "longmemeval-v2-small-full.json"
)

RADIUS_DIR = (
    "evidence/longmemeval-v2/diagnostics/"
    "enterprise-small-a3-radius"
)

PRISM12_DIR = (
    "evidence/longmemeval-v2/prism12/"
    "live-mechanism-replay"
)

PRISM13_DIR = (
    "evidence/longmemeval-v2/prism13/"
    "control-structure"
)

PRISM14_DIR = (
    "evidence/engram/causal/"
    "prism14-live-graph"
)

OUTPUT = Path("evidence/web/index.json")
CHECKSUMS = Path("evidence/web/SHA256SUMS")


def git_text(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        text=True,
    ).strip()


def git_bytes_at(
    commit: str,
    path: str,
) -> bytes:
    return subprocess.check_output(
        [
            "git",
            "show",
            f"{commit}:{path}",
        ]
    )


def git_text_at(
    commit: str,
    path: str,
) -> str:
    return git_bytes_at(
        commit,
        path,
    ).decode("utf-8")


def json_at(
    commit: str,
    path: str,
) -> dict[str, Any]:
    value = json.loads(
        git_text_at(commit, path)
    )

    if not isinstance(value, dict):
        raise RuntimeError(
            f"Expected JSON object: {path}"
        )

    return value


def resolve_commit(value: str) -> str:
    commit = git_text(
        "rev-parse",
        value,
    )

    if not re.fullmatch(
        r"[0-9a-f]{40}",
        commit,
    ):
        raise RuntimeError(
            f"Invalid commit: {commit}"
        )

    return commit


def verify_checksums(
    commit: str,
    directory: str,
) -> None:
    checksum_path = (
        f"{directory}/SHA256SUMS"
    )

    text = git_text_at(
        commit,
        checksum_path,
    )

    verified: set[str] = set()

    for raw in text.splitlines():
        line = raw.strip()

        if not line:
            continue

        parts = line.split(None, 1)

        if len(parts) != 2:
            raise RuntimeError(
                (
                    "Malformed checksum line: "
                    f"{checksum_path}: {line!r}"
                )
            )

        expected, filename = parts

        filename = (
            filename
            .lstrip("*")
            .removeprefix("./")
        )

        content = git_bytes_at(
            commit,
            f"{directory}/{filename}",
        )

        actual = hashlib.sha256(
            content
        ).hexdigest()

        if actual != expected:
            raise RuntimeError(
                (
                    "Checksum mismatch: "
                    f"{directory}/{filename}"
                )
            )

        verified.add(filename)

    required = {
        "result.json",
        "report.txt",
    }

    if not required <= verified:
        raise RuntimeError(
            (
                f"{checksum_path} missing "
                f"coverage for "
                f"{sorted(required - verified)}"
            )
        )


def exp(
    *,
    id: str,
    title: str,
    kind: str,
    status: str,
    claim_scope: str,
    coverage: str | None = None,
    ablation_stage: str | None = None,
    result_path: str | None = None,
    report_path: str | None = None,
    checksums_path: str | None = None,
    metrics: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    value = {
        "id": id,
        "title": title,
        "kind": kind,
        "status": status,
        "coverage": coverage,
        "ablation_stage": ablation_stage,
        "claim_scope": claim_scope,
        "result_path": result_path,
        "report_path": report_path,
        "checksums_path": checksums_path,
        "metrics": metrics or {},
        "warnings": warnings or [],
    }

    return {
        key: item
        for key, item in value.items()
        if item is not None
    }


def build(
    *,
    commit: str,
    ref: str,
) -> dict[str, Any]:

    for directory in (
        RADIUS_DIR,
        PRISM12_DIR,
        PRISM13_DIR,
        PRISM14_DIR,
    ):
        verify_checksums(
            commit,
            directory,
        )

    manifest = json_at(
        commit,
        DATASET_MANIFEST,
    )

    radius = json_at(
        commit,
        f"{RADIUS_DIR}/result.json",
    )

    prism12 = json_at(
        commit,
        f"{PRISM12_DIR}/result.json",
    )

    prism13 = json_at(
        commit,
        f"{PRISM13_DIR}/result.json",
    )

    prism14 = json_at(
        commit,
        f"{PRISM14_DIR}/result.json",
    )

    if (
        radius["status"]
        != "POSTHOC_A3_GRAPH_RADIUS_DIAGNOSTIC"
    ):
        raise RuntimeError(
            "A3 radius semantic gate failed"
        )

    if (
        prism12["status"]
        != "PRISM12_LIVE_MECHANISM_REPLAY_PASS"
    ):
        raise RuntimeError(
            "PRISM-12 semantic gate failed"
        )

    if (
        prism13["status"]
        != "PRISM13_CONTROL_STRUCTURE_PASS"
    ):
        raise RuntimeError(
            "PRISM-13 semantic gate failed"
        )

    if (
        prism14["status"]
        != "PRISM14_CAUSAL_GRAPH_STRUCTURE_PASS"
    ):
        raise RuntimeError(
            "PRISM-14 semantic gate failed"
        )

    if (
        prism14["integrity"][
            "behavioral_causality_evaluated"
        ]
        is not False
    ):
        raise RuntimeError(
            "PRISM-14 causal scope violation"
        )

    if (
        prism14["integrity"][
            "changed_action_claimed"
        ]
        is not False
    ):
        raise RuntimeError(
            "PRISM-14 CHANGED_ACTION violation"
        )

    d = manifest["dataset"]

    dataset = {
        "benchmark": manifest["benchmark"],
        "tier": manifest["tier"],
        "coverage": manifest["coverage"],
        "multimodal": manifest["multimodal"],
        "questions": d["questions"],
        "trajectories": d["trajectories"],
        "haystack_questions": (
            d["haystack_questions"]
        ),
        "runtime_screenshot_links": (
            d["runtime_screenshot_links"]
        ),
        "validation": d["validation"],
        "benchmark_code_commit": (
            manifest["benchmark_code_commit"]
        ),
        "dataset_revision": (
            manifest["dataset_revision"]
        ),
        "hydradb_commit": (
            manifest["hydradb_commit"]
        ),
    }

    p12_result = (
        f"{PRISM12_DIR}/result.json"
    )
    p12_report = (
        f"{PRISM12_DIR}/report.txt"
    )
    p12_sums = (
        f"{PRISM12_DIR}/SHA256SUMS"
    )

    p13_result = (
        f"{PRISM13_DIR}/result.json"
    )
    p13_report = (
        f"{PRISM13_DIR}/report.txt"
    )
    p13_sums = (
        f"{PRISM13_DIR}/SHA256SUMS"
    )

    p14_result = (
        f"{PRISM14_DIR}/result.json"
    )
    p14_report = (
        f"{PRISM14_DIR}/report.txt"
    )
    p14_sums = (
        f"{PRISM14_DIR}/SHA256SUMS"
    )

    radius_result = (
        f"{RADIUS_DIR}/result.json"
    )
    radius_report = (
        f"{RADIUS_DIR}/report.txt"
    )
    radius_sums = (
        f"{RADIUS_DIR}/SHA256SUMS"
    )

    a0 = prism13["a0"]
    a1 = prism13["a1"]

    live_hits = (
        prism12[
            "mechanism_subset_live_hits"
        ]
    )

    strata = prism12["strata"]

    experiments = [
        exp(
            id="A0",
            title="No memory",
            kind="CONTROL",
            status="TESTED",
            coverage="SUBSET",
            ablation_stage="A0",
            claim_scope=(
                "Official LongMemEval-V2 "
                "no_retrieval control over the "
                "deterministic 12-question "
                "mechanism subset."
            ),
            result_path=p13_result,
            report_path=p13_report,
            checksums_path=p13_sums,
            metrics={
                "n_questions": (
                    prism13["n_questions"]
                ),
                "memory_type": (
                    a0["memory_type"]
                ),
                "empty_contexts": (
                    a0["empty_contexts"]
                ),
            },
            warnings=[
                (
                    "Control-structure proof only; "
                    "reader evaluation NOT_RUN."
                )
            ],
        ),

        exp(
            id="A1",
            title="Flat local memory",
            kind="CONTROL",
            status="TESTED",
            coverage="SUBSET",
            ablation_stage="A1",
            claim_scope=(
                "Genuine non-Hydra flat-memory "
                "control with frozen selector "
                "parity."
            ),
            result_path=p13_result,
            report_path=p13_report,
            checksums_path=p13_sums,
            metrics={
                "n_questions": (
                    prism13["n_questions"]
                ),
                "candidate_strategy": (
                    a1[
                        "candidate_strategy"
                    ]
                ),
                "candidate_top_k": (
                    a1["candidate_top_k"]
                ),
                "selector_matches": (
                    a1["selector_matches"]
                ),
                "local_state_reads": (
                    a1["local_state_reads"]
                ),
                "hydra_driver_attempts": (
                    a1[
                        "hydra_driver_attempts"
                    ]
                ),
                "hydra_state_reads": (
                    a1["hydra_state_reads"]
                ),
                "graph_neighbor_states": (
                    a1[
                        "graph_neighbor_states"
                    ]
                ),
            },
        ),

        exp(
            id="A2",
            title="Hydra state retrieval",
            kind="CONTROL",
            status="TESTED",
            coverage="SUBSET",
            ablation_stage="A2",
            claim_scope=(
                "Live Hydra selected-state "
                "retrieval over the deterministic "
                "PRISM-12 mechanism subset."
            ),
            result_path=p12_result,
            report_path=p12_report,
            checksums_path=p12_sums,
            metrics={
                "n_questions": (
                    prism12["n_questions"]
                ),
                "retrieval_mode": "flat",
                "candidate_top_k": 3,
                "live_evidence_hits": (
                    live_hits["a2"]
                ),
            },
            warnings=[
                (
                    "Diagnostic live evidence "
                    "hits; not benchmark recall."
                )
            ],
        ),

        exp(
            id="A3",
            title="Hydra graph retrieval",
            kind="CONTROL",
            status="TESTED",
            coverage="SUBSET",
            ablation_stage="A3",
            claim_scope=(
                "Same frozen selector as A2 "
                "with live NEXT_STATE radius-1 "
                "graph expansion."
            ),
            result_path=p12_result,
            report_path=p12_report,
            checksums_path=p12_sums,
            metrics={
                "n_questions": (
                    prism12["n_questions"]
                ),
                "retrieval_mode": "graph",
                "candidate_top_k": 3,
                "graph_radius": 1,
                "live_evidence_hits": (
                    live_hits["a3"]
                ),
                "graph1_only_recoveries": (
                    strata["graph1_only"][
                        "a2_miss_a3_live_recovery"
                    ]
                ),
            },
            warnings=[
                (
                    "Mechanism subset only; "
                    "not benchmark recall or "
                    "answer-quality gain."
                )
            ],
        ),

        exp(
            id="A4",
            title="Engram causal memory",
            kind="CAUSAL",
            status="NOT_RUN",
            ablation_stage="A4",
            claim_scope=(
                "Memory-OFF versus memory-ON "
                "behavioral causal experiment "
                "has not run."
            ),
            warnings=[
                (
                    "PRISM-14 proves structural "
                    "provenance only."
                ),
                (
                    "CHANGED_ACTION is not "
                    "claimed."
                ),
            ],
        ),

        exp(
            id="A3-RADIUS-DIAGNOSTIC",
            title="A3 Graph Radius Frontier",
            kind="DIAGNOSTIC",
            status="TESTED",
            coverage="SUBSET",
            claim_scope=(
                "Post-hoc evidence-distance "
                "diagnostic over 104 questions."
            ),
            result_path=radius_result,
            report_path=radius_report,
            checksums_path=radius_sums,
            metrics={
                "n_questions": (
                    radius["n_questions"]
                ),
                "radius_hits": (
                    radius["radius_hits"]
                ),
                "radius_recall": (
                    radius["radius_recall"]
                ),
                "same_trajectory_upper_bound": (
                    radius[
                        "same_trajectory_upper_bound"
                    ]
                ),
                "distance_histogram": (
                    radius[
                        "distance_histogram"
                    ]
                ),
            },
            warnings=[
                (
                    "POST-HOC diagnostic; "
                    "Hydra traversal NOT_RUN."
                ),
                (
                    "NO_CORRECT_TRAJECTORY is "
                    "not a graph distance."
                ),
            ],
        ),

        exp(
            id="PRISM-12",
            title=(
                "Live Hydra radius-1 "
                "mechanism replay"
            ),
            kind="LIVE_MECHANISM",
            status="TESTED",
            coverage="SUBSET",
            claim_scope=(
                prism12["integrity"][
                    "allowed_claim"
                ]
            ),
            result_path=p12_result,
            report_path=p12_report,
            checksums_path=p12_sums,
            metrics={
                "n_questions": (
                    prism12["n_questions"]
                ),
                "strata": strata,
                "mechanism_subset_live_hits": (
                    live_hits
                ),
                "mechanism_matches": (
                    prism12[
                        "mechanism_matches"
                    ]
                ),
            },
            warnings=[
                (
                    "Deterministic diagnostic "
                    "strata; not unbiased "
                    "benchmark recall."
                )
            ],
        ),

        exp(
            id="PRISM-13",
            title="A0/A1 control structure",
            kind="CONTROL",
            status="TESTED",
            coverage="SUBSET",
            claim_scope=(
                prism13["integrity"][
                    "allowed_claim"
                ]
            ),
            result_path=p13_result,
            report_path=p13_report,
            checksums_path=p13_sums,
            metrics={
                "n_questions": (
                    prism13["n_questions"]
                ),
                "a0_empty_contexts": (
                    a0["empty_contexts"]
                ),
                "a1_selector_matches": (
                    a1["selector_matches"]
                ),
                "a1_local_state_reads": (
                    a1["local_state_reads"]
                ),
                "a1_hydra_state_reads": (
                    a1["hydra_state_reads"]
                ),
            },
        ),

        exp(
            id="PRISM-14",
            title="Live causal provenance graph",
            kind="CAUSAL",
            status="TESTED",
            coverage="SMOKE",
            claim_scope=(
                prism14["integrity"][
                    "allowed_claim"
                ]
            ),
            result_path=p14_result,
            report_path=p14_report,
            checksums_path=p14_sums,
            metrics={
                "recall_without_influence_count": (
                    prism14[
                        "recall_without_influence"
                    ]["influence_count"]
                ),
                "influence_state": (
                    prism14[
                        "recall_with_influence"
                    ]["influence_state"]
                ),
                "recall_not_equal_influence": (
                    prism14["proofs"][
                        "recall_not_equal_influence"
                    ]
                ),
                "distinct_runtime_ids": (
                    prism14["proofs"][
                        "distinct_runtime_ids"
                    ]
                ),
                "distinct_writer_processes": (
                    prism14["proofs"][
                        "distinct_writer_processes"
                    ]
                ),
                "live_hydra_writes": (
                    prism14["hydra"][
                        "live_writes_executed"
                    ]
                ),
                "live_hydra_reads": (
                    prism14["hydra"][
                        "live_reads_executed"
                    ]
                ),
            },
            warnings=[
                (
                    "Structural provenance only; "
                    "behavioral causality NOT_RUN."
                ),
                (
                    "Counterfactual memory-OFF/"
                    "memory-ON experiment NOT_RUN."
                ),
            ],
        ),
    ]

    generated_at = git_text(
        "show",
        "-s",
        "--format=%cI",
        commit,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "repository": REPOSITORY,
        "ref": ref,
        "commit": commit,
        "dataset": dataset,
        "experiments": experiments,
        "latest": {
            "radius_diagnostic": (
                "A3-RADIUS-DIAGNOSTIC"
            ),
            "live_mechanism": "PRISM-12",
            "control_structure": "PRISM-13",
            "causal_provenance": "PRISM-14",
            "behavioral_causal_memory": {
                "id": "A4",
                "status": "NOT_RUN",
            },
        },
    }


def validate(
    index: dict[str, Any],
) -> None:

    assert (
        index["schema_version"]
        == SCHEMA_VERSION
    )

    assert (
        index["repository"]
        == REPOSITORY
    )

    assert re.fullmatch(
        r"[0-9a-f]{40}",
        index["commit"],
    )

    dataset = index["dataset"]

    assert (
        dataset["benchmark"]
        == "LongMemEval-V2"
    )

    assert dataset["tier"] == "small"
    assert dataset["coverage"] == "FULL"
    assert dataset["multimodal"] is True
    assert dataset["questions"] == 451
    assert dataset["trajectories"] == 1870
    assert (
        dataset["haystack_questions"]
        == 451
    )
    assert (
        dataset["runtime_screenshot_links"]
        == 1913
    )
    assert dataset["validation"] == "PASS"

    experiments = {
        item["id"]: item
        for item in index["experiments"]
    }

    assert len(experiments) == 9

    for stage in (
        "A0",
        "A1",
        "A2",
        "A3",
    ):
        assert (
            experiments[stage]["status"]
            == "TESTED"
        )

        assert (
            experiments[stage][
                "ablation_stage"
            ]
            == stage
        )

    assert (
        experiments["A4"]["status"]
        == "NOT_RUN"
    )

    assert (
        experiments["A4"][
            "ablation_stage"
        ]
        == "A4"
    )

    assert (
        experiments["PRISM-14"][
            "status"
        ]
        == "TESTED"
    )

    assert (
        experiments["PRISM-14"][
            "metrics"
        ]["recall_not_equal_influence"]
        is True
    )

    assert (
        experiments["PRISM-14"][
            "metrics"
        ]["influence_state"]
        == "CONSIDERED"
    )

    radius = experiments[
        "A3-RADIUS-DIAGNOSTIC"
    ]["metrics"]

    assert radius[
        "radius_hits"
    ]["0"] == 74

    assert radius[
        "radius_hits"
    ]["1"] == 78

    assert radius[
        "radius_hits"
    ]["5"] == 83

    assert (
        radius[
            "same_trajectory_upper_bound"
        ]
        == 87
    )

    assert (
        radius[
            "distance_histogram"
        ]["NO_CORRECT_TRAJECTORY"]
        == 17
    )

    p12 = experiments["PRISM-12"]

    assert (
        p12["metrics"][
            "mechanism_subset_live_hits"
        ]["a2"]
        == 4
    )

    assert (
        p12["metrics"][
            "mechanism_subset_live_hits"
        ]["a3"]
        == 8
    )

    assert (
        p12["metrics"][
            "mechanism_matches"
        ]
        == 12
    )


def render(
    index: dict[str, Any],
) -> str:
    return (
        json.dumps(
            index,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--source-commit",
        default="HEAD",
    )

    parser.add_argument(
        "--ref",
        default=(
            "a3-engram-hydra-memory"
        ),
    )

    parser.add_argument(
        "--check",
        action="store_true",
    )

    args = parser.parse_args()

    commit = resolve_commit(
        args.source_commit
    )

    index = build(
        commit=commit,
        ref=args.ref,
    )

    validate(index)

    content = render(index)

    checksum = (
        hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()
        + "  index.json\n"
    )

    if args.check:
        if not OUTPUT.is_file():
            raise RuntimeError(
                "evidence/web/index.json missing"
            )

        if (
            OUTPUT.read_text(
                encoding="utf-8"
            )
            != content
        ):
            raise RuntimeError(
                "Evidence index stale"
            )

        if not CHECKSUMS.is_file():
            raise RuntimeError(
                "Evidence checksum missing"
            )

        if (
            CHECKSUMS.read_text(
                encoding="utf-8"
            )
            != checksum
        ):
            raise RuntimeError(
                "Evidence checksum stale"
            )

        print(
            "EVIDENCE_INDEX_CHECK=PASS"
        )
        print(
            f"SOURCE_COMMIT={commit}"
        )
        print(
            "A0_A3_STATUS=TESTED"
        )
        print(
            "A4_STATUS=NOT_RUN"
        )

        return 0

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        content,
        encoding="utf-8",
    )

    CHECKSUMS.write_text(
        checksum,
        encoding="utf-8",
    )

    print(
        "EVIDENCE_INDEX_BUILD=PASS"
    )
    print(
        f"SOURCE_COMMIT={commit}"
    )
    print(
        f"EXPERIMENT_COUNT="
        f"{len(index['experiments'])}"
    )
    print(
        "A0_A3_STATUS=TESTED"
    )
    print(
        "A4_STATUS=NOT_RUN"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
