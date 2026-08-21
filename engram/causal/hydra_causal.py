from __future__ import annotations

from enum import Enum
import hashlib
import os
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase


_ID_HIGH_BIT = 1 << 62
_ID_MASK = (1 << 62) - 1

SCHEMA_VERSION = "engram-causal-provenance-v1"


class InfluenceState(str, Enum):
    CONSIDERED = "CONSIDERED"
    SUPPORTED_ACTION = "SUPPORTED_ACTION"
    CONSTRAINED_ACTION = "CONSTRAINED_ACTION"
    CHANGED_ACTION = "CHANGED_ACTION"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def deterministic_causal_id(
    kind: str,
    semantic_id: str,
) -> int:
    digest = hashlib.sha256(
        (
            f"engram:causal:v1:"
            f"{kind}:{semantic_id}"
        ).encode("utf-8")
    ).digest()

    return _ID_HIGH_BIT | (
        int.from_bytes(digest[:8], "big")
        & _ID_MASK
    )


def relationship_id(
    relationship: str,
    source: str,
    destination: str,
) -> int:
    return deterministic_causal_id(
        "relationship",
        (
            f"{relationship}:"
            f"{source}:{destination}"
        ),
    )


def normalize_influence_state(
    value: InfluenceState | str,
) -> InfluenceState:
    if isinstance(value, InfluenceState):
        return value

    try:
        return InfluenceState(str(value))
    except ValueError as exc:
        allowed = ", ".join(
            state.value for state in InfluenceState
        )
        raise RuntimeError(
            (
                f"Invalid influence state {value!r}; "
                f"allowed: {allowed}"
            )
        ) from exc


class EngramHydraCausalStore:
    """Hydra-backed causal provenance store.

    This primitive deliberately separates:

      recall:
        a prior memory was retrieved/considered

    influence:
        an explicit provenance record connects
        that recall to a later decision.

    Therefore:

        RECALL != INFLUENCE

    PRISM-14 proves the structure and traversal.
    It does not itself prove behavioral causality.
    """

    def __init__(
        self,
        *,
        bolt_uri: str = "bolt://127.0.0.1:7687",
        database: str = "default",
        token_file_env: str = "ENGRAM_HYDRA_TOKEN_FILE",
    ) -> None:
        self.bolt_uri = bolt_uri.strip()
        self.database = database.strip()
        self.token_file_env = token_file_env.strip()

        require(
            bool(self.bolt_uri),
            "bolt_uri must be non-empty",
        )

        require(
            bool(self.database),
            "database must be non-empty",
        )

        token_file_raw = (
            os.environ.get(self.token_file_env)
            or os.environ.get(
                "GRAPH_AUTH_TOKEN_FILE"
            )
        )

        require(
            isinstance(token_file_raw, str)
            and token_file_raw.strip(),
            (
                f"Set {self.token_file_env} "
                "or GRAPH_AUTH_TOKEN_FILE"
            ),
        )

        self.token_file = Path(
            token_file_raw
        ).expanduser().resolve()

        require(
            self.token_file.is_file(),
            (
                "Missing Hydra auth token file: "
                f"{self.token_file}"
            ),
        )

        token = self.token_file.read_text(
            encoding="utf-8"
        ).strip()

        require(
            bool(token),
            (
                "Hydra auth token file is empty: "
                f"{self.token_file}"
            ),
        )

        self.driver = GraphDatabase.driver(
            self.bolt_uri,
            auth=("neo4j", token),
        )

        self.driver.verify_connectivity()

    def close(self) -> None:
        self.driver.close()

    def _run(
        self,
        query: str,
        **params: object,
    ) -> None:
        with self.driver.session(
            database=self.database
        ) as session:
            session.run(
                query,
                **params,
            ).consume()

    def _upsert_node(
        self,
        *,
        label: str,
        vertex: int,
        properties: dict[str, object],
    ) -> None:
        """Hydra-compatible one-row vertex upsert over Bolt.

        HydraDB's executable Bolt batch form supports:

            UNWIND $rows AS row
            MERGE (n {id: row.vertex})
            SET ...

        Regular scalar MERGE followed by SET is deliberately not used.
        """

        allowed_labels = {
            "EngramExecution",
            "EngramOutcome",
            "EngramMemory",
            "EngramRecall",
            "EngramDecision",
            "EngramInfluence",
            "EngramAction",
        }

        require(
            label in allowed_labels,
            f"Unsupported causal node label: {label}",
        )

        require(
            isinstance(vertex, int) and vertex >= 0,
            "Causal vertex id must be a non-negative integer",
        )

        require(
            bool(properties),
            "Causal node properties must be non-empty",
        )

        for key in properties:
            require(
                key.replace("_", "").isalnum()
                and not key[0].isdigit(),
                f"Invalid causal property name: {key}",
            )

        row = {
            "vertex": vertex,
            **properties,
        }

        assignments = [
            f"n:{label}",
            *[
                f"n.{key} = row.{key}"
                for key in properties
            ],
        ]

        query = (
            "UNWIND $rows AS row "
            "MERGE (n {id: row.vertex}) "
            "SET "
            + ", ".join(assignments)
        )

        self._run(
            query,
            rows=[row],
        )

    def _upsert_relationship(
        self,
        *,
        source_label: str,
        source_vertex: int,
        relationship_type: str,
        relationship_vertex: int,
        destination_label: str,
        destination_vertex: int,
    ) -> None:
        """Hydra-compatible one-row relationship upsert."""

        allowed_labels = {
            "EngramExecution",
            "EngramOutcome",
            "EngramMemory",
            "EngramRecall",
            "EngramDecision",
            "EngramInfluence",
            "EngramAction",
        }

        allowed_relationships = {
            "PRODUCED",
            "DISTILLED_TO",
            "PERFORMED_RECALL",
            "RECALLED_MEMORY",
            "MADE_DECISION",
            "RECORDED_INFLUENCE",
            "APPLIED_TO",
            "SELECTED_ACTION",
            "EXECUTED_ACTION",
            "PRODUCED_OUTCOME",
        }

        require(
            source_label in allowed_labels,
            f"Unsupported source label: {source_label}",
        )

        require(
            destination_label in allowed_labels,
            (
                "Unsupported destination label: "
                f"{destination_label}"
            ),
        )

        require(
            relationship_type in allowed_relationships,
            (
                "Unsupported relationship type: "
                f"{relationship_type}"
            ),
        )

        for name, value in (
            ("source_vertex", source_vertex),
            (
                "relationship_vertex",
                relationship_vertex,
            ),
            (
                "destination_vertex",
                destination_vertex,
            ),
        ):
            require(
                isinstance(value, int)
                and value >= 0,
                (
                    f"{name} must be a "
                    "non-negative integer"
                ),
            )

        row = {
            "source_vertex": source_vertex,
            "relationship_vertex": (
                relationship_vertex
            ),
            "destination_vertex": (
                destination_vertex
            ),
            "schema_version": SCHEMA_VERSION,
        }

        query = (
            "UNWIND $rows AS row "
            f"MATCH "
            f"(s:{source_label} "
            "{id: row.source_vertex}), "
            f"(d:{destination_label} "
            "{id: row.destination_vertex}) "
            f"MERGE "
            f"(s)-[r:{relationship_type} "
            "{id: row.relationship_vertex}]->(d) "
            "SET "
            "r.schema_version = row.schema_version"
        )

        self._run(
            query,
            rows=[row],
        )


    def read_one(
        self,
        query: str,
        **params: object,
    ) -> Any:
        with self.driver.session(
            database=self.database
        ) as session:
            return session.run(
                query,
                **params,
            ).single()

    def record_execution(
        self,
        *,
        execution_id: str,
        runtime_id: str,
        task_id: str,
        writer_pid: int,
    ) -> int:
        vertex = deterministic_causal_id(
            "execution",
            execution_id,
        )

        self._upsert_node(
            label="EngramExecution",
            vertex=vertex,
            properties={
                "schema_version": SCHEMA_VERSION,
                "execution_id": execution_id,
                "runtime_id": runtime_id,
                "task_id": task_id,
                "writer_pid": int(writer_pid),
            },
        )

        return vertex

    def record_outcome(
        self,
        *,
        outcome_id: str,
        execution_id: str,
        status: str,
        reason: str,
        action_id: str | None = None,
    ) -> int:
        outcome_vertex = deterministic_causal_id(
            "outcome",
            outcome_id,
        )

        execution_vertex = deterministic_causal_id(
            "execution",
            execution_id,
        )

        self._upsert_node(
            label="EngramOutcome",
            vertex=outcome_vertex,
            properties={
                "schema_version": SCHEMA_VERSION,
                "outcome_id": outcome_id,
                "status": status,
                "reason": reason,
            },
        )

        self._upsert_relationship(
            source_label="EngramExecution",
            source_vertex=execution_vertex,
            relationship_type="PRODUCED",
            relationship_vertex=relationship_id(
                "PRODUCED",
                execution_id,
                outcome_id,
            ),
            destination_label="EngramOutcome",
            destination_vertex=outcome_vertex,
        )

        if action_id is not None:
            action_vertex = (
                deterministic_causal_id(
                    "action",
                    action_id,
                )
            )

            self._upsert_relationship(
                source_label="EngramAction",
                source_vertex=action_vertex,
                relationship_type="PRODUCED_OUTCOME",
                relationship_vertex=relationship_id(
                    "PRODUCED_OUTCOME",
                    action_id,
                    outcome_id,
                ),
                destination_label="EngramOutcome",
                destination_vertex=outcome_vertex,
            )

        return outcome_vertex

    def record_memory(
        self,
        *,
        memory_id: str,
        source_execution_id: str,
        source_outcome_id: str,
        interpretation: str,
        evidence_state: str,
    ) -> int:
        memory_vertex = deterministic_causal_id(
            "memory",
            memory_id,
        )

        outcome_vertex = deterministic_causal_id(
            "outcome",
            source_outcome_id,
        )

        self._upsert_node(
            label="EngramMemory",
            vertex=memory_vertex,
            properties={
                "schema_version": SCHEMA_VERSION,
                "memory_id": memory_id,
                "source_execution_id": source_execution_id,
                "source_outcome_id": source_outcome_id,
                "interpretation": interpretation,
                "evidence_state": evidence_state,
            },
        )

        self._upsert_relationship(
            source_label="EngramOutcome",
            source_vertex=outcome_vertex,
            relationship_type="DISTILLED_TO",
            relationship_vertex=relationship_id(
                "DISTILLED_TO",
                source_outcome_id,
                memory_id,
            ),
            destination_label="EngramMemory",
            destination_vertex=memory_vertex,
        )

        return memory_vertex

    def record_recall(
        self,
        *,
        recall_id: str,
        execution_id: str,
        memory_id: str,
        query_text: str,
        writer_pid: int,
    ) -> int:
        recall_vertex = deterministic_causal_id(
            "recall",
            recall_id,
        )

        execution_vertex = deterministic_causal_id(
            "execution",
            execution_id,
        )

        memory_vertex = deterministic_causal_id(
            "memory",
            memory_id,
        )

        self._upsert_node(
            label="EngramRecall",
            vertex=recall_vertex,
            properties={
                "schema_version": SCHEMA_VERSION,
                "recall_id": recall_id,
                "execution_id": execution_id,
                "memory_id": memory_id,
                "query_text": query_text,
                "writer_pid": int(writer_pid),
            },
        )

        self._upsert_relationship(
            source_label="EngramExecution",
            source_vertex=execution_vertex,
            relationship_type="PERFORMED_RECALL",
            relationship_vertex=relationship_id(
                "PERFORMED_RECALL",
                execution_id,
                recall_id,
            ),
            destination_label="EngramRecall",
            destination_vertex=recall_vertex,
        )

        self._upsert_relationship(
            source_label="EngramRecall",
            source_vertex=recall_vertex,
            relationship_type="RECALLED_MEMORY",
            relationship_vertex=relationship_id(
                "RECALLED_MEMORY",
                recall_id,
                memory_id,
            ),
            destination_label="EngramMemory",
            destination_vertex=memory_vertex,
        )

        return recall_vertex

    def record_decision(
        self,
        *,
        decision_id: str,
        execution_id: str,
        choice: str,
        reasoning_receipt: str,
        writer_pid: int,
    ) -> int:
        decision_vertex = deterministic_causal_id(
            "decision",
            decision_id,
        )

        execution_vertex = deterministic_causal_id(
            "execution",
            execution_id,
        )

        self._upsert_node(
            label="EngramDecision",
            vertex=decision_vertex,
            properties={
                "schema_version": SCHEMA_VERSION,
                "decision_id": decision_id,
                "execution_id": execution_id,
                "choice": choice,
                "reasoning_receipt": reasoning_receipt,
                "writer_pid": int(writer_pid),
            },
        )

        self._upsert_relationship(
            source_label="EngramExecution",
            source_vertex=execution_vertex,
            relationship_type="MADE_DECISION",
            relationship_vertex=relationship_id(
                "MADE_DECISION",
                execution_id,
                decision_id,
            ),
            destination_label="EngramDecision",
            destination_vertex=decision_vertex,
        )

        return decision_vertex

    def record_influence(
        self,
        *,
        influence_id: str,
        recall_id: str,
        decision_id: str,
        state: InfluenceState | str,
        reason: str,
        writer_pid: int,
    ) -> int:
        normalized = normalize_influence_state(
            state
        )

        influence_vertex = deterministic_causal_id(
            "influence",
            influence_id,
        )

        recall_vertex = deterministic_causal_id(
            "recall",
            recall_id,
        )

        decision_vertex = deterministic_causal_id(
            "decision",
            decision_id,
        )

        self._upsert_node(
            label="EngramInfluence",
            vertex=influence_vertex,
            properties={
                "schema_version": SCHEMA_VERSION,
                "influence_id": influence_id,
                "state": normalized.value,
                "reason": reason,
                "writer_pid": int(writer_pid),
            },
        )

        self._upsert_relationship(
            source_label="EngramRecall",
            source_vertex=recall_vertex,
            relationship_type="RECORDED_INFLUENCE",
            relationship_vertex=relationship_id(
                "RECORDED_INFLUENCE",
                recall_id,
                influence_id,
            ),
            destination_label="EngramInfluence",
            destination_vertex=influence_vertex,
        )

        self._upsert_relationship(
            source_label="EngramInfluence",
            source_vertex=influence_vertex,
            relationship_type="APPLIED_TO",
            relationship_vertex=relationship_id(
                "APPLIED_TO",
                influence_id,
                decision_id,
            ),
            destination_label="EngramDecision",
            destination_vertex=decision_vertex,
        )

        return influence_vertex

    def record_action(
        self,
        *,
        action_id: str,
        execution_id: str,
        decision_id: str,
        action: str,
        writer_pid: int,
    ) -> int:
        action_vertex = deterministic_causal_id(
            "action",
            action_id,
        )

        execution_vertex = deterministic_causal_id(
            "execution",
            execution_id,
        )

        decision_vertex = deterministic_causal_id(
            "decision",
            decision_id,
        )

        self._upsert_node(
            label="EngramAction",
            vertex=action_vertex,
            properties={
                "schema_version": SCHEMA_VERSION,
                "action_id": action_id,
                "execution_id": execution_id,
                "action": action,
                "writer_pid": int(writer_pid),
            },
        )

        self._upsert_relationship(
            source_label="EngramDecision",
            source_vertex=decision_vertex,
            relationship_type="SELECTED_ACTION",
            relationship_vertex=relationship_id(
                "SELECTED_ACTION",
                decision_id,
                action_id,
            ),
            destination_label="EngramAction",
            destination_vertex=action_vertex,
        )

        self._upsert_relationship(
            source_label="EngramExecution",
            source_vertex=execution_vertex,
            relationship_type="EXECUTED_ACTION",
            relationship_vertex=relationship_id(
                "EXECUTED_ACTION",
                execution_id,
                action_id,
            ),
            destination_label="EngramAction",
            destination_vertex=action_vertex,
        )

        return action_vertex
