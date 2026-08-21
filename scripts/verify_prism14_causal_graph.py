#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


EXECUTION_A = "prism14:execution-a:v1"
OUTCOME_A = "prism14:outcome-a:v1"
MEMORY_A = "prism14:memory-a:v1"

EXECUTION_B0 = "prism14:execution-b0:v1"
RECALL_B0 = "prism14:recall-b0:v1"
DECISION_B0 = "prism14:decision-b0:v1"

EXECUTION_B1 = "prism14:execution-b1:v1"
RECALL_B1 = "prism14:recall-b1:v1"
DECISION_B1 = "prism14:decision-b1:v1"
INFLUENCE_B1 = "prism14:influence-b1:v1"
ACTION_B1 = "prism14:action-b1:v1"
OUTCOME_B1 = "prism14:outcome-b1:v1"

TASK_ID = "prism14:route-selection:v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mode",
        required=True,
        choices=[
            "seed-a",
            "recall-no-influence",
            "recall-with-influence",
            "verify",
        ],
    )

    parser.add_argument(
        "--output-dir",
        default=None,
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]

    sys.path.insert(0, str(repo_root))

    from engram.causal.hydra_causal import (
        EngramHydraCausalStore,
        InfluenceState,
        deterministic_causal_id,
        normalize_influence_state,
    )

    pid = os.getpid()

    store = EngramHydraCausalStore()

    try:
        if args.mode == "seed-a":
            store.record_execution(
                execution_id=EXECUTION_A,
                runtime_id="runtime-a-prism14",
                task_id=TASK_ID,
                writer_pid=pid,
            )

            store.record_outcome(
                outcome_id=OUTCOME_A,
                execution_id=EXECUTION_A,
                status="FAILURE",
                reason="thin-liquidity",
            )

            store.record_memory(
                memory_id=MEMORY_A,
                source_execution_id=EXECUTION_A,
                source_outcome_id=OUTCOME_A,
                interpretation=(
                    "Route C failed under "
                    "thin liquidity"
                ),
                evidence_state="OBSERVED",
            )

            row = store.read_one(
                (
                    "MATCH "
                    "(e:EngramExecution "
                    "{id: $execution})"
                    "-[:PRODUCED]->"
                    "(o:EngramOutcome "
                    "{id: $outcome})"
                    "-[:DISTILLED_TO]->"
                    "(m:EngramMemory "
                    "{id: $memory}) "
                    "RETURN "
                    "e.runtime_id AS runtime_id, "
                    "e.writer_pid AS writer_pid, "
                    "o.status AS status, "
                    "o.reason AS reason, "
                    "m.interpretation "
                    "AS interpretation, "
                    "m.evidence_state "
                    "AS evidence_state"
                ),
                execution=deterministic_causal_id(
                    "execution",
                    EXECUTION_A,
                ),
                outcome=deterministic_causal_id(
                    "outcome",
                    OUTCOME_A,
                ),
                memory=deterministic_causal_id(
                    "memory",
                    MEMORY_A,
                ),
            )

            require(
                row is not None,
                (
                    "Execution A -> Outcome A -> "
                    "Memory A traversal failed"
                ),
            )

            print("PRISM14_SEED_A=PASS")
            print(
                "EXECUTION_A_RUNTIME="
                f"{row['runtime_id']}"
            )
            print(
                "EXECUTION_A_WRITER_PID="
                f"{row['writer_pid']}"
            )
            print(
                "OUTCOME_A_STATUS="
                f"{row['status']}"
            )
            print(
                "OUTCOME_A_REASON="
                f"{row['reason']}"
            )
            print(
                "MEMORY_A_EVIDENCE_STATE="
                f"{row['evidence_state']}"
            )
            return

        if args.mode == "recall-no-influence":
            store.record_execution(
                execution_id=EXECUTION_B0,
                runtime_id="runtime-b0-prism14",
                task_id=TASK_ID,
                writer_pid=pid,
            )

            store.record_recall(
                recall_id=RECALL_B0,
                execution_id=EXECUTION_B0,
                memory_id=MEMORY_A,
                query_text=(
                    "What prior route experience "
                    "is relevant?"
                ),
                writer_pid=pid,
            )

            store.record_decision(
                decision_id=DECISION_B0,
                execution_id=EXECUTION_B0,
                choice="inspect-market-state",
                reasoning_receipt=(
                    "Decision recorded without an "
                    "influence assertion."
                ),
                writer_pid=pid,
            )

            base_negative = store.read_one(
                (
                    "MATCH "
                    "(e:EngramExecution "
                    "{id: $execution})"
                    "-[:PERFORMED_RECALL]->"
                    "(r:EngramRecall "
                    "{id: $recall})"
                    "-[:RECALLED_MEMORY]->"
                    "(m:EngramMemory "
                    "{id: $memory}) "
                    "RETURN "
                    "e.runtime_id AS runtime_id, "
                    "e.writer_pid AS writer_pid, "
                    "r.recall_id AS recall_id, "
                    "m.memory_id AS memory_id"
                ),
                execution=deterministic_causal_id(
                    "execution",
                    EXECUTION_B0,
                ),
                recall=deterministic_causal_id(
                    "recall",
                    RECALL_B0,
                ),
                memory=deterministic_causal_id(
                    "memory",
                    MEMORY_A,
                ),
            )

            require(
                base_negative is not None,
                "B0 recall-to-memory traversal failed",
            )

            influence_probe = store.read_one(
                (
                    "MATCH "
                    "(r:EngramRecall "
                    "{id: $recall})"
                    "-[:RECORDED_INFLUENCE]->"
                    "(i:EngramInfluence) "
                    "RETURN "
                    "i.influence_id AS influence_id "
                    "LIMIT 1"
                ),
                recall=deterministic_causal_id(
                    "recall",
                    RECALL_B0,
                ),
            )

            require(
                influence_probe is None,
                (
                    "Recall-without-influence "
                    "negative control failed"
                ),
            )

            row = dict(base_negative)
            row["influence_count"] = 0

            require(
                row is not None,
                "B0 recall traversal failed",
            )

            require(
                int(row["influence_count"]) == 0,
                (
                    "Recall-without-influence "
                    "negative control failed"
                ),
            )

            print(
                "PRISM14_RECALL_WITHOUT_INFLUENCE="
                "PASS"
            )
            print(
                "EXECUTION_B0_RUNTIME="
                f"{row['runtime_id']}"
            )
            print(
                "EXECUTION_B0_WRITER_PID="
                f"{row['writer_pid']}"
            )
            print("B0_INFLUENCE_COUNT=0")
            return

        if args.mode == "recall-with-influence":
            store.record_execution(
                execution_id=EXECUTION_B1,
                runtime_id="runtime-b1-prism14",
                task_id=TASK_ID,
                writer_pid=pid,
            )

            store.record_recall(
                recall_id=RECALL_B1,
                execution_id=EXECUTION_B1,
                memory_id=MEMORY_A,
                query_text=(
                    "What prior route experience "
                    "is relevant?"
                ),
                writer_pid=pid,
            )

            store.record_decision(
                decision_id=DECISION_B1,
                execution_id=EXECUTION_B1,
                choice="run-liquidity-preflight",
                reasoning_receipt=(
                    "Prior failure was explicitly "
                    "considered before the decision."
                ),
                writer_pid=pid,
            )

            store.record_influence(
                influence_id=INFLUENCE_B1,
                recall_id=RECALL_B1,
                decision_id=DECISION_B1,
                state=InfluenceState.CONSIDERED,
                reason=(
                    "The recalled thin-liquidity "
                    "failure was reviewed before "
                    "choosing the next action."
                ),
                writer_pid=pid,
            )

            store.record_action(
                action_id=ACTION_B1,
                execution_id=EXECUTION_B1,
                decision_id=DECISION_B1,
                action="preflight-liquidity-check",
                writer_pid=pid,
            )

            store.record_outcome(
                outcome_id=OUTCOME_B1,
                execution_id=EXECUTION_B1,
                status="OBSERVED",
                reason="preflight-completed",
                action_id=ACTION_B1,
            )

            row = store.read_one(
                (
                    "MATCH "
                    "(r:EngramRecall "
                    "{id: $recall})"
                    "-[:RECORDED_INFLUENCE]->"
                    "(i:EngramInfluence "
                    "{id: $influence})"
                    "-[:APPLIED_TO]->"
                    "(d:EngramDecision "
                    "{id: $decision})"
                    "-[:SELECTED_ACTION]->"
                    "(a:EngramAction "
                    "{id: $action})"
                    "-[:PRODUCED_OUTCOME]->"
                    "(o:EngramOutcome "
                    "{id: $outcome}) "
                    "RETURN "
                    "i.state AS state, "
                    "d.choice AS choice, "
                    "a.action AS action, "
                    "o.status AS outcome_status"
                ),
                recall=deterministic_causal_id(
                    "recall",
                    RECALL_B1,
                ),
                influence=deterministic_causal_id(
                    "influence",
                    INFLUENCE_B1,
                ),
                decision=deterministic_causal_id(
                    "decision",
                    DECISION_B1,
                ),
                action=deterministic_causal_id(
                    "action",
                    ACTION_B1,
                ),
                outcome=deterministic_causal_id(
                    "outcome",
                    OUTCOME_B1,
                ),
            )

            require(
                row is not None,
                (
                    "Recall -> Influence -> Decision "
                    "-> Action -> Outcome traversal "
                    "failed"
                ),
            )

            require(
                row["state"]
                == InfluenceState.CONSIDERED.value,
                "Influence state mismatch",
            )

            print(
                "PRISM14_RECALL_WITH_INFLUENCE="
                "PASS"
            )
            print(
                "INFLUENCE_STATE="
                f"{row['state']}"
            )
            print(
                "ACTION_B1="
                f"{row['action']}"
            )
            return

        require(
            args.output_dir is not None,
            "--output-dir is required for verify",
        )

        output_dir = Path(
            args.output_dir
        ).expanduser().resolve()

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        path_a = store.read_one(
            (
                "MATCH "
                "(e:EngramExecution "
                "{id: $execution})"
                "-[:PRODUCED]->"
                "(o:EngramOutcome "
                "{id: $outcome})"
                "-[:DISTILLED_TO]->"
                "(m:EngramMemory "
                "{id: $memory}) "
                "RETURN "
                "e.runtime_id AS runtime_id, "
                "e.writer_pid AS writer_pid, "
                "o.status AS outcome_status, "
                "o.reason AS outcome_reason, "
                "m.memory_id AS memory_id, "
                "m.interpretation "
                "AS interpretation, "
                "m.evidence_state "
                "AS evidence_state"
            ),
            execution=deterministic_causal_id(
                "execution",
                EXECUTION_A,
            ),
            outcome=deterministic_causal_id(
                "outcome",
                OUTCOME_A,
            ),
            memory=deterministic_causal_id(
                "memory",
                MEMORY_A,
            ),
        )

        base_negative = store.read_one(
            (
                "MATCH "
                "(e:EngramExecution "
                "{id: $execution})"
                "-[:PERFORMED_RECALL]->"
                "(r:EngramRecall "
                "{id: $recall})"
                "-[:RECALLED_MEMORY]->"
                "(m:EngramMemory "
                "{id: $memory}) "
                "RETURN "
                "e.runtime_id AS runtime_id, "
                "e.writer_pid AS writer_pid, "
                "r.recall_id AS recall_id, "
                "m.memory_id AS memory_id"
            ),
            execution=deterministic_causal_id(
                "execution",
                EXECUTION_B0,
            ),
            recall=deterministic_causal_id(
                "recall",
                RECALL_B0,
            ),
            memory=deterministic_causal_id(
                "memory",
                MEMORY_A,
            ),
        )

        require(
            base_negative is not None,
            "B0 recall-to-memory traversal failed",
        )

        influence_probe = store.read_one(
            (
                "MATCH "
                "(r:EngramRecall "
                "{id: $recall})"
                "-[:RECORDED_INFLUENCE]->"
                "(i:EngramInfluence) "
                "RETURN "
                "i.influence_id AS influence_id "
                "LIMIT 1"
            ),
            recall=deterministic_causal_id(
                "recall",
                RECALL_B0,
            ),
        )

        require(
            influence_probe is None,
            (
                "Recall-without-influence "
                "negative control failed"
            ),
        )

        negative = dict(base_negative)
        negative["influence_count"] = 0

        positive = store.read_one(
            (
                "MATCH "
                "(e:EngramExecution "
                "{id: $execution})"
                "-[:PERFORMED_RECALL]->"
                "(r:EngramRecall "
                "{id: $recall})"
                "-[:RECALLED_MEMORY]->"
                "(m:EngramMemory "
                "{id: $memory}), "
                "(e)-[:MADE_DECISION]->"
                "(d:EngramDecision "
                "{id: $decision}), "
                "(r)-[:RECORDED_INFLUENCE]->"
                "(i:EngramInfluence "
                "{id: $influence})"
                "-[:APPLIED_TO]->(d), "
                "(d)-[:SELECTED_ACTION]->"
                "(a:EngramAction "
                "{id: $action})"
                "-[:PRODUCED_OUTCOME]->"
                "(o:EngramOutcome "
                "{id: $outcome}) "
                "RETURN "
                "e.runtime_id AS runtime_id, "
                "e.writer_pid AS writer_pid, "
                "r.recall_id AS recall_id, "
                "m.memory_id AS memory_id, "
                "i.influence_id AS influence_id, "
                "i.state AS influence_state, "
                "d.choice AS decision_choice, "
                "a.action AS action, "
                "o.status AS outcome_status"
            ),
            execution=deterministic_causal_id(
                "execution",
                EXECUTION_B1,
            ),
            recall=deterministic_causal_id(
                "recall",
                RECALL_B1,
            ),
            memory=deterministic_causal_id(
                "memory",
                MEMORY_A,
            ),
            decision=deterministic_causal_id(
                "decision",
                DECISION_B1,
            ),
            influence=deterministic_causal_id(
                "influence",
                INFLUENCE_B1,
            ),
            action=deterministic_causal_id(
                "action",
                ACTION_B1,
            ),
            outcome=deterministic_causal_id(
                "outcome",
                OUTCOME_B1,
            ),
        )

        require(
            path_a is not None,
            "Origin path missing",
        )

        require(
            negative is not None,
            "Negative recall path missing",
        )

        require(
            positive is not None,
            "Positive influence path missing",
        )

        require(
            int(negative["influence_count"]) == 0,
            (
                "Negative recall unexpectedly "
                "has influence"
            ),
        )

        require(
            positive["influence_state"]
            == InfluenceState.CONSIDERED.value,
            "Positive influence state mismatch",
        )

        runtime_a = str(path_a["runtime_id"])
        runtime_b0 = str(negative["runtime_id"])
        runtime_b1 = str(positive["runtime_id"])

        pid_a = int(path_a["writer_pid"])
        pid_b0 = int(negative["writer_pid"])
        pid_b1 = int(positive["writer_pid"])

        require(
            len(
                {
                    runtime_a,
                    runtime_b0,
                    runtime_b1,
                }
            )
            == 3,
            "Runtime identifiers are not distinct",
        )

        require(
            len(
                {
                    pid_a,
                    pid_b0,
                    pid_b1,
                }
            )
            == 3,
            (
                "Expected separate writer processes "
                "for A, B0, and B1"
            ),
        )

        try:
            normalize_influence_state(
                "INVALID_STATE"
            )
        except RuntimeError:
            invalid_state_rejected = True
        else:
            invalid_state_rejected = False

        require(
            invalid_state_rejected,
            (
                "Invalid influence state was not "
                "rejected"
            ),
        )

        result = {
            "status": (
                "PRISM14_CAUSAL_GRAPH_STRUCTURE_PASS"
            ),
            "schema_version": (
                "engram-causal-provenance-v1"
            ),
            "hydra": {
                "bolt_uri": (
                    "bolt://127.0.0.1:7687"
                ),
                "database": "default",
                "live_writes_executed": True,
                "live_reads_executed": True,
            },
            "origin_experience": {
                "execution_id": EXECUTION_A,
                "runtime_id": runtime_a,
                "writer_pid": pid_a,
                "outcome_id": OUTCOME_A,
                "outcome_status": (
                    path_a["outcome_status"]
                ),
                "outcome_reason": (
                    path_a["outcome_reason"]
                ),
                "memory_id": MEMORY_A,
                "interpretation": (
                    path_a["interpretation"]
                ),
                "evidence_state": (
                    path_a["evidence_state"]
                ),
            },
            "recall_without_influence": {
                "execution_id": EXECUTION_B0,
                "runtime_id": runtime_b0,
                "writer_pid": pid_b0,
                "recall_id": RECALL_B0,
                "memory_id": MEMORY_A,
                "influence_count": int(
                    negative["influence_count"]
                ),
            },
            "recall_with_influence": {
                "execution_id": EXECUTION_B1,
                "runtime_id": runtime_b1,
                "writer_pid": pid_b1,
                "recall_id": RECALL_B1,
                "memory_id": MEMORY_A,
                "influence_id": INFLUENCE_B1,
                "influence_state": (
                    positive["influence_state"]
                ),
                "decision_id": DECISION_B1,
                "decision_choice": (
                    positive["decision_choice"]
                ),
                "action_id": ACTION_B1,
                "action": positive["action"],
                "outcome_id": OUTCOME_B1,
                "outcome_status": (
                    positive["outcome_status"]
                ),
            },
            "proofs": {
                "execution_to_outcome_to_memory": True,
                "memory_recalled_later": True,
                "recall_without_influence_valid": True,
                "recall_with_explicit_influence_valid": True,
                "recall_not_equal_influence": True,
                "influence_enum_enforced": True,
                "decision_provenance_recorded": True,
                "action_provenance_recorded": True,
                "later_outcome_recorded": True,
                "distinct_runtime_ids": True,
                "distinct_writer_processes": True,
            },
            "integrity": {
                "structural_provenance_only": True,
                "behavioral_causality_evaluated": False,
                "changed_action_claimed": False,
                "counterfactual_experiment_run": False,
                "allowed_claim": (
                    "Engram records live Hydra "
                    "causal-provenance structure in "
                    "which recall is distinct from "
                    "explicit influence, and an "
                    "influence receipt can connect a "
                    "recalled experience to a later "
                    "decision, action, and outcome."
                ),
            },
        }

        output_path = (
            output_dir / "result.json"
        )

        output_path.write_text(
            json.dumps(
                result,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        print(
            "PRISM14_ORIGIN_EXPERIENCE_PATH=PASS"
        )
        print(
            "PRISM14_RECALL_WITHOUT_INFLUENCE=PASS"
        )
        print(
            "PRISM14_RECALL_WITH_INFLUENCE=PASS"
        )
        print("RECALL_NOT_EQUAL_INFLUENCE=PASS")
        print("INFLUENCE_ENUM=PASS")
        print(
            "INFLUENCE_STATE="
            f"{positive['influence_state']}"
        )
        print("DISTINCT_RUNTIME_IDS=PASS")
        print("DISTINCT_WRITER_PROCESSES=PASS")
        print("LIVE_HYDRA_WRITES=PASS")
        print("LIVE_HYDRA_READS=PASS")
        print(
            "BEHAVIORAL_CAUSALITY_EVALUATED=FALSE"
        )
        print(
            "CHANGED_ACTION_CLAIMED=FALSE"
        )
        print(f"RESULT_JSON={output_path}")
        print(
            "PRISM14_CAUSAL_GRAPH_STRUCTURE=PASS"
        )

    finally:
        store.close()


if __name__ == "__main__":
    main()
