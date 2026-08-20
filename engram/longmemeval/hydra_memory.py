from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import threading
from typing import Any

from neo4j import GraphDatabase

from memory_modules.memory import Memory, MemoryContextItem, register_memory, require
from memory_modules.trajectory_store import prepare_trajectory_insert

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_ID_HIGH_BIT = 1 << 62
_ID_MASK = (1 << 62) - 1


def deterministic_vertex_id(kind: str, semantic_id: str) -> int:
    """Return a stable positive int64-range Hydra vertex id."""
    digest = hashlib.sha256(f"engram:lmev2:{kind}:{semantic_id}".encode("utf-8")).digest()
    return _ID_HIGH_BIT | (int.from_bytes(digest[:8], "big") & _ID_MASK)


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def _clean(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


@dataclass(frozen=True)
class StateRecord:
    vertex_id: int
    trajectory_vertex_id: int
    trajectory_id: str
    goal: str
    outcome: str
    state_index: int
    step: int
    url: str
    action: str
    thoughts: str
    text: str
    screenshot: str

    @property
    def search_text(self) -> str:
        return "\n".join(
            part
            for part in (
                self.goal,
                self.outcome,
                self.url,
                self.action,
                self.thoughts,
                self.text,
            )
            if part
        )


@register_memory
class EngramHydraMemory(Memory):
    """LongMemEval-V2 memory backend backed by HydraDB.

    A2 and A3 deliberately share the same local lexical candidate selector.
    `retrieval_mode=flat` returns only the selected Hydra state vertices.
    `retrieval_mode=graph` expands each candidate through typed NEXT_STATE
    relationships, making Hydra graph structure the only material difference.
    """

    memory_type = "engram_hydra"

    _driver_lock = threading.Lock()
    _driver_cache: dict[tuple[str, str], Any] = {}
    _ingest_lock = threading.Lock()
    _ingested_fingerprints: set[str] = set()

    def __init__(self, memory_params: dict[str, object]) -> None:
        super().__init__(memory_params)

        self.bolt_uri = str(memory_params.get("bolt_uri", "bolt://127.0.0.1:7687")).strip()
        self.database = str(memory_params.get("database", "default")).strip()
        self.token_file_env = str(
            memory_params.get("token_file_env", "ENGRAM_HYDRA_TOKEN_FILE")
        ).strip()
        self.data_root_env = str(
            memory_params.get("data_root_env", "LONGMEMEVAL_V2_DATA_ROOT")
        ).strip()
        self.retrieval_mode = str(memory_params.get("retrieval_mode", "graph")).strip()
        self.candidate_top_k = int(memory_params.get("candidate_top_k", 3))
        self.include_images = bool(memory_params.get("include_images", True))
        self.max_state_chars = int(memory_params.get("max_state_chars", 6000))

        require(self.bolt_uri, "engram_hydra bolt_uri must be non-empty")
        require(self.database, "engram_hydra database must be non-empty")
        require(self.token_file_env, "engram_hydra token_file_env must be non-empty")
        require(self.data_root_env, "engram_hydra data_root_env must be non-empty")
        require(
            self.retrieval_mode in {"flat", "graph"},
            "engram_hydra retrieval_mode must be flat or graph",
        )
        require(self.candidate_top_k > 0, "engram_hydra candidate_top_k must be positive")
        require(self.max_state_chars > 0, "engram_hydra max_state_chars must be positive")

        token_file = os.environ.get(self.token_file_env) or os.environ.get("GRAPH_AUTH_TOKEN_FILE")
        require(
            isinstance(token_file, str) and token_file.strip(),
            f"Set {self.token_file_env} (or GRAPH_AUTH_TOKEN_FILE) to the Hydra auth token file",
        )
        self.token_file = Path(token_file).expanduser().resolve()
        require(self.token_file.is_file(), f"Missing Hydra auth token file: {self.token_file}")

        data_root = os.environ.get(self.data_root_env)
        require(
            isinstance(data_root, str) and data_root.strip(),
            f"Set {self.data_root_env} to the prepared LongMemEval-V2 data root",
        )
        self.data_root = Path(data_root).expanduser().resolve()
        require(self.data_root.is_dir(), f"Missing LongMemEval-V2 data root: {self.data_root}")

        self._states: list[StateRecord] = []
        self._state_by_id: dict[int, StateRecord] = {}
        self._last_query_debug: dict[str, object] = {}

    @property
    def last_query_debug(self) -> dict[str, object]:
        return dict(self._last_query_debug)

    def _driver(self):
        token = self.token_file.read_text(encoding="utf-8").strip()
        require(token, f"Hydra token file is empty: {self.token_file}")
        key = (self.bolt_uri, token)
        with self._driver_lock:
            driver = self._driver_cache.get(key)
            if driver is None:
                driver = GraphDatabase.driver(self.bolt_uri, auth=("neo4j", token))
                driver.verify_connectivity()
                self._driver_cache[key] = driver
            return driver

    def insert(self, trajectory: dict[str, object]) -> None:
        prepared = prepare_trajectory_insert(
            trajectory,
            trajectories_root_dir=self.data_root,
        )
        simplified = prepared.simplified
        trajectory_id = str(simplified["id"])
        trajectory_vertex_id = deterministic_vertex_id("trajectory", trajectory_id)
        goal = _clean(simplified.get("goal"))
        outcome = _clean(simplified.get("outcome"))
        start_url = _clean(simplified.get("start_url"))
        states_obj = simplified.get("states")
        require(isinstance(states_obj, list) and states_obj, f"No states for {trajectory_id}")
        require(
            len(states_obj) == len(prepared.screenshot_sources),
            f"Screenshot/state count mismatch for {trajectory_id}",
        )

        state_records: list[StateRecord] = []
        for state, screenshot_src in zip(states_obj, prepared.screenshot_sources):
            require(isinstance(state, dict), f"Invalid state in {trajectory_id}")
            state_index = int(state["state_index"])
            record = StateRecord(
                vertex_id=deterministic_vertex_id("state", f"{trajectory_id}:{state_index}"),
                trajectory_vertex_id=trajectory_vertex_id,
                trajectory_id=trajectory_id,
                goal=goal,
                outcome=outcome,
                state_index=state_index,
                step=int(state["step"]),
                url=_clean(state.get("url")),
                action=_clean(state.get("action")),
                thoughts=_clean(state.get("thoughts")),
                text=_clean(state.get("text")),
                screenshot=str(Path(screenshot_src).resolve()),
            )
            state_records.append(record)
            self._states.append(record)
            self._state_by_id[record.vertex_id] = record

        should_write = False
        with self._ingest_lock:
            if prepared.fingerprint not in self._ingested_fingerprints:
                self._ingested_fingerprints.add(prepared.fingerprint)
                should_write = True

        if not should_write:
            return

        trajectory_rows = [
            {
                "vertex": trajectory_vertex_id,
                "trajectory_id": trajectory_id,
                "goal": goal,
                "outcome": outcome,
                "start_url": start_url,
                "fingerprint": prepared.fingerprint,
            }
        ]
        state_rows = [
            {
                "vertex": state.vertex_id,
                "trajectory_id": state.trajectory_id,
                "state_index": state.state_index,
                "step": state.step,
                "url": state.url,
                "action": state.action,
                "thoughts": state.thoughts,
                "text": state.text,
                "screenshot": state.screenshot,
            }
            for state in state_records
        ]
        has_state_rows = [
            {
                "source_vertex": trajectory_vertex_id,
                "destination_vertex": state.vertex_id,
                "relationship_vertex": deterministic_vertex_id(
                    "relationship", f"has_state:{trajectory_id}:{state.state_index}"
                ),
            }
            for state in state_records
        ]
        next_state_rows = [
            {
                "source_vertex": previous.vertex_id,
                "destination_vertex": current.vertex_id,
                "relationship_vertex": deterministic_vertex_id(
                    "relationship",
                    f"next_state:{trajectory_id}:{previous.state_index}:{current.state_index}",
                ),
            }
            for previous, current in zip(state_records, state_records[1:])
        ]

        driver = self._driver()
        with driver.session(database=self.database) as session:
            session.run(
                "UNWIND $rows AS row "
                "MERGE (n {id: row.vertex}) "
                "SET n:LMEV2Trajectory, "
                "n.trajectory_id = row.trajectory_id, "
                "n.goal = row.goal, "
                "n.outcome = row.outcome, "
                "n.start_url = row.start_url, "
                "n.fingerprint = row.fingerprint",
                rows=trajectory_rows,
            ).consume()
            session.run(
                "UNWIND $rows AS row "
                "MERGE (n {id: row.vertex}) "
                "SET n:LMEV2State, "
                "n.trajectory_id = row.trajectory_id, "
                "n.state_index = row.state_index, "
                "n.step = row.step, "
                "n.url = row.url, "
                "n.action = row.action, "
                "n.thoughts = row.thoughts, "
                "n.text = row.text, "
                "n.screenshot = row.screenshot",
                rows=state_rows,
            ).consume()
            session.run(
                "UNWIND $rows AS row "
                "MATCH (s:LMEV2Trajectory {id: row.source_vertex}), "
                "(d:LMEV2State {id: row.destination_vertex}) "
                "MERGE (s)-[r:HAS_STATE {id: row.relationship_vertex}]->(d)",
                rows=has_state_rows,
            ).consume()
            if next_state_rows:
                session.run(
                    "UNWIND $rows AS row "
                    "MATCH (s:LMEV2State {id: row.source_vertex}), "
                    "(d:LMEV2State {id: row.destination_vertex}) "
                    "MERGE (s)-[r:NEXT_STATE {id: row.relationship_vertex}]->(d)",
                    rows=next_state_rows,
                ).consume()

    def _rank_candidates(self, query: str) -> list[StateRecord]:
        query_terms = _tokens(query)
        if not self._states or not query_terms:
            return []

        docs = [_tokens(state.search_text) for state in self._states]
        document_frequency: Counter[str] = Counter()
        for doc in docs:
            document_frequency.update(set(doc))

        n_docs = len(docs)
        query_counter = Counter(query_terms)
        scored: list[tuple[float, int, StateRecord]] = []
        for state, doc in zip(self._states, docs):
            counts = Counter(doc)
            score = 0.0
            for term, query_tf in query_counter.items():
                tf = counts.get(term, 0)
                if not tf:
                    continue
                idf = math.log((n_docs + 1) / (document_frequency[term] + 1)) + 1.0
                score += (1.0 + math.log(tf)) * idf * query_tf
            if score > 0:
                scored.append((score, -state.state_index, state))

        if not scored:
            # Deterministic fallback: use the earliest states from the admissible haystack.
            return sorted(
                self._states,
                key=lambda state: (state.trajectory_id, state.state_index),
            )[: self.candidate_top_k]

        scored.sort(key=lambda item: (item[0], item[1], item[2].trajectory_id), reverse=True)
        return [item[2] for item in scored[: self.candidate_top_k]]

    @staticmethod
    def _row_to_record(row: Any, fallback: StateRecord) -> StateRecord:
        return StateRecord(
            vertex_id=int(row["vertex_id"]),
            trajectory_vertex_id=fallback.trajectory_vertex_id,
            trajectory_id=str(row["trajectory_id"]),
            goal=fallback.goal,
            outcome=fallback.outcome,
            state_index=int(row["state_index"]),
            step=int(row["step"]),
            url=str(row["url"]),
            action=str(row["action"]),
            thoughts=str(row["thoughts"]),
            text=str(row["text"]),
            screenshot=str(row["screenshot"]),
        )

    def _fetch_graph_context(self, candidate: StateRecord) -> tuple[list[StateRecord], int]:
        driver = self._driver()
        ordered: dict[int, StateRecord] = {candidate.vertex_id: candidate}
        graph_neighbors = 0

        projection = (
            "p.id AS vertex_id, p.trajectory_id AS trajectory_id, "
            "p.state_index AS state_index, p.step AS step, p.url AS url, "
            "p.action AS action, p.thoughts AS thoughts, p.text AS text, "
            "p.screenshot AS screenshot"
        )
        next_projection = projection.replace("p.", "n.")

        with driver.session(database=self.database) as session:
            if self.retrieval_mode == "graph":
                prev_row = session.run(
                    "MATCH (p:LMEV2State)-[:NEXT_STATE]->"
                    "(s:LMEV2State {id: $candidate}) "
                    f"RETURN {projection} ORDER BY state_index DESC LIMIT 1",
                    candidate=candidate.vertex_id,
                ).single()
                if prev_row is not None:
                    previous = self._row_to_record(prev_row, candidate)
                    ordered[previous.vertex_id] = previous
                    graph_neighbors += 1

                next_row = session.run(
                    "MATCH (s:LMEV2State {id: $candidate})-[:NEXT_STATE]->"
                    "(n:LMEV2State) "
                    f"RETURN {next_projection} ORDER BY state_index LIMIT 1",
                    candidate=candidate.vertex_id,
                ).single()
                if next_row is not None:
                    following = self._row_to_record(next_row, candidate)
                    ordered[following.vertex_id] = following
                    graph_neighbors += 1

            # Even flat mode must read the selected state from Hydra rather than
            # returning the local lexical index as memory.
            current_row = session.run(
                "MATCH (s:LMEV2State {id: $candidate}) "
                "RETURN s.id AS vertex_id, s.trajectory_id AS trajectory_id, "
                "s.state_index AS state_index, s.step AS step, s.url AS url, "
                "s.action AS action, s.thoughts AS thoughts, s.text AS text, "
                "s.screenshot AS screenshot",
                candidate=candidate.vertex_id,
            ).single(strict=True)
            current = self._row_to_record(current_row, candidate)
            ordered[current.vertex_id] = current

        rows = sorted(
            ordered.values(),
            key=lambda state: (state.trajectory_id, state.state_index),
        )
        return rows, graph_neighbors

    def _format_state(self, state: StateRecord) -> str:
        text = state.text
        if len(text) > self.max_state_chars:
            text = text[: self.max_state_chars] + "\n[truncated]"
        parts = [
            f"Trajectory: {state.trajectory_id}",
            f"Goal: {state.goal}" if state.goal else "",
            f"Outcome: {state.outcome}" if state.outcome else "",
            f"State index: {state.state_index}",
            f"Step: {state.step}",
            f"URL: {state.url}",
            f"Action: {state.action}" if state.action else "",
            f"Thoughts: {state.thoughts}" if state.thoughts else "",
            "Observed state:",
            text,
        ]
        return "\n".join(part for part in parts if part)

    def query(self, query: str, query_image: str | None = None) -> list[MemoryContextItem]:
        _ = query_image  # A3 candidate selection is text-only; returned memory remains multimodal.
        candidates = self._rank_candidates(query)
        context: list[MemoryContextItem] = []
        seen_states: set[int] = set()
        graph_neighbor_states = 0
        hydra_state_reads = 0

        for candidate in candidates:
            states, neighbor_count = self._fetch_graph_context(candidate)
            graph_neighbor_states += neighbor_count
            hydra_state_reads += len(states)
            for state in states:
                if state.vertex_id in seen_states:
                    continue
                seen_states.add(state.vertex_id)
                context.append({"type": "text", "value": self._format_state(state)})
                if self.include_images and state.screenshot and Path(state.screenshot).is_file():
                    context.append({"type": "image", "value": state.screenshot})

        self._last_query_debug = {
            "retrieval_mode": self.retrieval_mode,
            "candidate_count": len(candidates),
            "candidate_vertex_ids": [state.vertex_id for state in candidates],
            "hydra_state_reads": hydra_state_reads,
            "graph_neighbor_states": graph_neighbor_states,
            "context_items": len(context),
        }
        return context
