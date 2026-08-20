from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import threading
from typing import Any, Iterable

from neo4j import GraphDatabase

from memory_modules.memory import Memory, MemoryContextItem, register_memory, require
from memory_modules.trajectory_store import prepare_trajectory_insert


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_ID_HIGH_BIT = 1 << 62
_ID_MASK = (1 << 62) - 1

# HydraDB indexes vertex property values into SlateDB keys. SlateDB currently
# requires each key to fit within u16::MAX bytes. LongMemEval-V2 accessibility
# trees can be much larger, so evidence is persisted as bounded chunk vertices
# rather than as one unbounded property on the state vertex.
_HYDRA_TEXT_CHUNK_BYTES = 8192
_HYDRA_WRITE_BATCH_ROWS = 32
_STATE_CONTENT_FIELDS = ("url", "action", "thoughts", "text")
_TRAJECTORY_CONTENT_FIELDS = ("goal", "outcome", "start_url")
_STORAGE_SCHEMA = "bounded-content-chunks-v2"


def deterministic_vertex_id(kind: str, semantic_id: str) -> int:
    """Return a stable positive int64-range Hydra vertex id."""
    digest = hashlib.sha256(
        f"engram:lmev2:{kind}:{semantic_id}".encode("utf-8")
    ).digest()
    return _ID_HIGH_BIT | (int.from_bytes(digest[:8], "big") & _ID_MASK)


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def _clean(value: object) -> str:
    return value if isinstance(value, str) else ""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _content_digest(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _utf8_chunks(value: str, max_bytes: int = _HYDRA_TEXT_CHUNK_BYTES) -> list[str]:
    """Split text without breaking UTF-8 characters and preserve it exactly."""
    require(max_bytes > 0, "chunk byte budget must be positive")
    if not value:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_bytes = 0

    for char in value:
        char_bytes = len(char.encode("utf-8"))
        require(
            char_bytes <= max_bytes,
            "single UTF-8 character exceeds chunk byte budget",
        )
        if current and current_bytes + char_bytes > max_bytes:
            chunks.append("".join(current))
            current = []
            current_bytes = 0
        current.append(char)
        current_bytes += char_bytes

    if current:
        chunks.append("".join(current))

    require("".join(chunks) == value, "UTF-8 chunk reconstruction mismatch")
    require(
        all(len(chunk.encode("utf-8")) <= max_bytes for chunk in chunks),
        "generated chunk exceeds Hydra byte budget",
    )
    return chunks


def _batched(rows: list[dict[str, object]], size: int = _HYDRA_WRITE_BATCH_ROWS):
    require(size > 0, "write batch size must be positive")
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


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

    Large trajectory/state strings are stored in deterministic bounded chunk
    vertices and reconstructed through Hydra at query time. This preserves the
    benchmark evidence while respecting HydraDB/SlateDB's current key-size
    constraint.
    """

    memory_type = "engram_hydra"

    _driver_lock = threading.Lock()
    _driver_cache: dict[tuple[str, str], Any] = {}
    _ingest_lock = threading.Lock()
    _ingested_fingerprints: set[str] = set()

    def __init__(self, memory_params: dict[str, object]) -> None:
        super().__init__(memory_params)

        self.bolt_uri = str(
            memory_params.get("bolt_uri", "bolt://127.0.0.1:7687")
        ).strip()
        self.database = str(memory_params.get("database", "default")).strip()
        self.token_file_env = str(
            memory_params.get("token_file_env", "ENGRAM_HYDRA_TOKEN_FILE")
        ).strip()
        self.data_root_env = str(
            memory_params.get("data_root_env", "LONGMEMEVAL_V2_DATA_ROOT")
        ).strip()
        self.retrieval_mode = str(
            memory_params.get("retrieval_mode", "graph")
        ).strip()
        self.candidate_top_k = int(memory_params.get("candidate_top_k", 3))
        self.candidate_strategy = str(
            memory_params.get("candidate_strategy", "legacy_tfidf")
        ).strip().lower()
        self.graph_radius = int(memory_params.get("graph_radius", 1))
        self.include_images = bool(memory_params.get("include_images", True))
        self.max_state_chars = int(memory_params.get("max_state_chars", 6000))
        self.chunk_byte_budget = int(
            memory_params.get("chunk_byte_budget", _HYDRA_TEXT_CHUNK_BYTES)
        )
        self.write_batch_rows = int(
            memory_params.get("write_batch_rows", _HYDRA_WRITE_BATCH_ROWS)
        )

        require(self.bolt_uri, "engram_hydra bolt_uri must be non-empty")
        require(self.database, "engram_hydra database must be non-empty")
        require(
            self.token_file_env,
            "engram_hydra token_file_env must be non-empty",
        )
        require(
            self.data_root_env,
            "engram_hydra data_root_env must be non-empty",
        )
        require(
            self.retrieval_mode in {"flat", "graph"},
            "engram_hydra retrieval_mode must be flat or graph",
        )
        require(
            self.candidate_top_k > 0,
            "engram_hydra candidate_top_k must be positive",
        )
        require(
            self.candidate_strategy
            in {"legacy_tfidf", "phrase_trajectory_bm25_v1"},
            (
                "engram_hydra candidate_strategy must be "
                "legacy_tfidf or phrase_trajectory_bm25_v1"
            ),
        )
        require(
            self.graph_radius == 1,
            (
                "engram_hydra currently supports graph_radius=1; "
                "wider radii are intentionally not enabled"
            ),
        )
        require(
            self.max_state_chars > 0,
            "engram_hydra max_state_chars must be positive",
        )
        require(
            0 < self.chunk_byte_budget <= 16384,
            "engram_hydra chunk_byte_budget must be within 1..16384 bytes",
        )
        require(
            self.write_batch_rows > 0,
            "engram_hydra write_batch_rows must be positive",
        )

        token_file = os.environ.get(self.token_file_env) or os.environ.get(
            "GRAPH_AUTH_TOKEN_FILE"
        )
        require(
            isinstance(token_file, str) and token_file.strip(),
            (
                f"Set {self.token_file_env} (or GRAPH_AUTH_TOKEN_FILE) "
                "to the Hydra auth token file"
            ),
        )
        self.token_file = Path(token_file).expanduser().resolve()
        require(
            self.token_file.is_file(),
            f"Missing Hydra auth token file: {self.token_file}",
        )

        data_root = os.environ.get(self.data_root_env)
        require(
            isinstance(data_root, str) and data_root.strip(),
            (
                f"Set {self.data_root_env} to the prepared "
                "LongMemEval-V2 data root"
            ),
        )
        self.data_root = Path(data_root).expanduser().resolve()
        require(
            self.data_root.is_dir(),
            f"Missing LongMemEval-V2 data root: {self.data_root}",
        )

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
                driver = GraphDatabase.driver(
                    self.bolt_uri,
                    auth=("neo4j", token),
                )
                driver.verify_connectivity()
                self._driver_cache[key] = driver
            return driver

    def _run_batched(
        self,
        session: Any,
        query: str,
        rows: list[dict[str, object]],
    ) -> None:
        for batch in _batched(rows, self.write_batch_rows):
            session.run(query, rows=batch).consume()

    def _trajectory_chunk_rows(
        self,
        *,
        trajectory_vertex_id: int,
        trajectory_id: str,
        goal: str,
        outcome: str,
        start_url: str,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        chunk_rows: list[dict[str, object]] = []
        relationship_rows: list[dict[str, object]] = []
        content = {
            "goal": goal,
            "outcome": outcome,
            "start_url": start_url,
        }

        for field in _TRAJECTORY_CONTENT_FIELDS:
            value = content[field]
            for chunk_index, chunk in enumerate(
                _utf8_chunks(value, self.chunk_byte_budget)
            ):
                chunk_vertex = deterministic_vertex_id(
                    "trajectory-chunk",
                    f"{trajectory_id}:{field}:{chunk_index}",
                )
                chunk_rows.append(
                    {
                        "vertex": chunk_vertex,
                        "trajectory_id": trajectory_id,
                        "field": field,
                        "chunk_index": chunk_index,
                        "content": chunk,
                        "content_sha256": _sha256_text(chunk),
                        "content_bytes": len(chunk.encode("utf-8")),
                    }
                )
                relationship_rows.append(
                    {
                        "source_vertex": trajectory_vertex_id,
                        "destination_vertex": chunk_vertex,
                        "relationship_vertex": deterministic_vertex_id(
                            "relationship",
                            (
                                "has_trajectory_chunk:"
                                f"{trajectory_id}:{field}:{chunk_index}"
                            ),
                        ),
                    }
                )
        return chunk_rows, relationship_rows

    def _state_chunk_rows(
        self,
        state: StateRecord,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        chunk_rows: list[dict[str, object]] = []
        relationship_rows: list[dict[str, object]] = []
        content = {
            "url": state.url,
            "action": state.action,
            "thoughts": state.thoughts,
            "text": state.text,
        }

        for field in _STATE_CONTENT_FIELDS:
            value = content[field]
            for chunk_index, chunk in enumerate(
                _utf8_chunks(value, self.chunk_byte_budget)
            ):
                chunk_vertex = deterministic_vertex_id(
                    "state-chunk",
                    (
                        f"{state.trajectory_id}:{state.state_index}:"
                        f"{field}:{chunk_index}"
                    ),
                )
                chunk_rows.append(
                    {
                        "vertex": chunk_vertex,
                        "trajectory_id": state.trajectory_id,
                        "state_index": state.state_index,
                        "field": field,
                        "chunk_index": chunk_index,
                        "content": chunk,
                        "content_sha256": _sha256_text(chunk),
                        "content_bytes": len(chunk.encode("utf-8")),
                    }
                )
                relationship_rows.append(
                    {
                        "source_vertex": state.vertex_id,
                        "destination_vertex": chunk_vertex,
                        "relationship_vertex": deterministic_vertex_id(
                            "relationship",
                            (
                                "has_content_chunk:"
                                f"{state.trajectory_id}:{state.state_index}:"
                                f"{field}:{chunk_index}"
                            ),
                        ),
                    }
                )
        return chunk_rows, relationship_rows

    def insert(self, trajectory: dict[str, object]) -> None:
        prepared = prepare_trajectory_insert(
            trajectory,
            trajectories_root_dir=self.data_root,
        )
        simplified = prepared.simplified
        trajectory_id = str(simplified["id"])
        trajectory_vertex_id = deterministic_vertex_id(
            "trajectory",
            trajectory_id,
        )
        goal = _clean(simplified.get("goal"))
        outcome = _clean(simplified.get("outcome"))
        start_url = _clean(simplified.get("start_url"))
        states_obj = simplified.get("states")
        require(
            isinstance(states_obj, list) and states_obj,
            f"No states for {trajectory_id}",
        )
        require(
            len(states_obj) == len(prepared.screenshot_sources),
            f"Screenshot/state count mismatch for {trajectory_id}",
        )

        state_records: list[StateRecord] = []
        for state, screenshot_src in zip(
            states_obj,
            prepared.screenshot_sources,
        ):
            require(
                isinstance(state, dict),
                f"Invalid state in {trajectory_id}",
            )
            state_index = int(state["state_index"])
            record = StateRecord(
                vertex_id=deterministic_vertex_id(
                    "state",
                    f"{trajectory_id}:{state_index}",
                ),
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

        # Cache only successful physical ingests. Holding the lock through the
        # write keeps two A2/A3 instances from racing the same deterministic
        # corpus into Hydra in one benchmark process.
        with self._ingest_lock:
            if prepared.fingerprint in self._ingested_fingerprints:
                return

            trajectory_rows = [
                {
                    "vertex": trajectory_vertex_id,
                    "trajectory_id": trajectory_id,
                    "fingerprint": prepared.fingerprint,
                    "content_sha256": _content_digest(
                        (goal, outcome, start_url)
                    ),
                    "content_chars": len(goal) + len(outcome) + len(start_url),
                    "storage_schema": _STORAGE_SCHEMA,
                }
            ]
            state_rows = [
                {
                    "vertex": state.vertex_id,
                    "trajectory_vertex_id": state.trajectory_vertex_id,
                    "trajectory_id": state.trajectory_id,
                    "state_index": state.state_index,
                    "step": state.step,
                    "screenshot": state.screenshot,
                    "content_sha256": _content_digest(
                        (
                            state.url,
                            state.action,
                            state.thoughts,
                            state.text,
                        )
                    ),
                    "content_chars": (
                        len(state.url)
                        + len(state.action)
                        + len(state.thoughts)
                        + len(state.text)
                    ),
                    "storage_schema": _STORAGE_SCHEMA,
                }
                for state in state_records
            ]
            has_state_rows = [
                {
                    "source_vertex": trajectory_vertex_id,
                    "destination_vertex": state.vertex_id,
                    "relationship_vertex": deterministic_vertex_id(
                        "relationship",
                        f"has_state:{trajectory_id}:{state.state_index}",
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
                        (
                            f"next_state:{trajectory_id}:"
                            f"{previous.state_index}:{current.state_index}"
                        ),
                    ),
                }
                for previous, current in zip(
                    state_records,
                    state_records[1:],
                )
            ]

            trajectory_chunk_rows, trajectory_chunk_relationship_rows = (
                self._trajectory_chunk_rows(
                    trajectory_vertex_id=trajectory_vertex_id,
                    trajectory_id=trajectory_id,
                    goal=goal,
                    outcome=outcome,
                    start_url=start_url,
                )
            )
            state_chunk_rows: list[dict[str, object]] = []
            state_chunk_relationship_rows: list[dict[str, object]] = []
            for state in state_records:
                chunks, relationships = self._state_chunk_rows(state)
                state_chunk_rows.extend(chunks)
                state_chunk_relationship_rows.extend(relationships)

            driver = self._driver()
            with driver.session(database=self.database) as session:
                self._run_batched(
                    session,
                    (
                        "UNWIND $rows AS row "
                        "MERGE (n {id: row.vertex}) "
                        "SET n:LMEV2Trajectory, "
                        "n.trajectory_id = row.trajectory_id, "
                        "n.fingerprint = row.fingerprint, "
                        "n.content_sha256 = row.content_sha256, "
                        "n.content_chars = row.content_chars, "
                        "n.storage_schema = row.storage_schema"
                    ),
                    trajectory_rows,
                )
                self._run_batched(
                    session,
                    (
                        "UNWIND $rows AS row "
                        "MERGE (n {id: row.vertex}) "
                        "SET n:LMEV2State, "
                        "n.trajectory_vertex_id = row.trajectory_vertex_id, "
                        "n.trajectory_id = row.trajectory_id, "
                        "n.state_index = row.state_index, "
                        "n.step = row.step, "
                        "n.screenshot = row.screenshot, "
                        "n.content_sha256 = row.content_sha256, "
                        "n.content_chars = row.content_chars, "
                        "n.storage_schema = row.storage_schema"
                    ),
                    state_rows,
                )
                self._run_batched(
                    session,
                    (
                        "UNWIND $rows AS row "
                        "MERGE (n {id: row.vertex}) "
                        "SET n:LMEV2TrajectoryChunk, "
                        "n.trajectory_id = row.trajectory_id, "
                        "n.field = row.field, "
                        "n.chunk_index = row.chunk_index, "
                        "n.content = row.content, "
                        "n.content_sha256 = row.content_sha256, "
                        "n.content_bytes = row.content_bytes"
                    ),
                    trajectory_chunk_rows,
                )
                self._run_batched(
                    session,
                    (
                        "UNWIND $rows AS row "
                        "MERGE (n {id: row.vertex}) "
                        "SET n:LMEV2StateChunk, "
                        "n.trajectory_id = row.trajectory_id, "
                        "n.state_index = row.state_index, "
                        "n.field = row.field, "
                        "n.chunk_index = row.chunk_index, "
                        "n.content = row.content, "
                        "n.content_sha256 = row.content_sha256, "
                        "n.content_bytes = row.content_bytes"
                    ),
                    state_chunk_rows,
                )
                self._run_batched(
                    session,
                    (
                        "UNWIND $rows AS row "
                        "MATCH (s:LMEV2Trajectory {id: row.source_vertex}), "
                        "(d:LMEV2State {id: row.destination_vertex}) "
                        "MERGE (s)-[r:HAS_STATE "
                        "{id: row.relationship_vertex}]->(d)"
                    ),
                    has_state_rows,
                )
                if next_state_rows:
                    self._run_batched(
                        session,
                        (
                            "UNWIND $rows AS row "
                            "MATCH (s:LMEV2State {id: row.source_vertex}), "
                            "(d:LMEV2State {id: row.destination_vertex}) "
                            "MERGE (s)-[r:NEXT_STATE "
                            "{id: row.relationship_vertex}]->(d)"
                        ),
                        next_state_rows,
                    )
                if trajectory_chunk_relationship_rows:
                    self._run_batched(
                        session,
                        (
                            "UNWIND $rows AS row "
                            "MATCH "
                            "(s:LMEV2Trajectory {id: row.source_vertex}), "
                            "(d:LMEV2TrajectoryChunk "
                            "{id: row.destination_vertex}) "
                            "MERGE (s)-[r:HAS_TRAJECTORY_CHUNK "
                            "{id: row.relationship_vertex}]->(d)"
                        ),
                        trajectory_chunk_relationship_rows,
                    )
                if state_chunk_relationship_rows:
                    self._run_batched(
                        session,
                        (
                            "UNWIND $rows AS row "
                            "MATCH (s:LMEV2State {id: row.source_vertex}), "
                            "(d:LMEV2StateChunk "
                            "{id: row.destination_vertex}) "
                            "MERGE (s)-[r:HAS_CONTENT_CHUNK "
                            "{id: row.relationship_vertex}]->(d)"
                        ),
                        state_chunk_relationship_rows,
                    )

            self._ingested_fingerprints.add(prepared.fingerprint)

    def _rank_candidates_legacy(
        self,
        query: str,
    ) -> list[StateRecord]:
        """Original Engram Hydra TF-IDF selector.

        Kept intact as a reproducible retrieval baseline.
        """
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
                idf = (
                    math.log(
                        (n_docs + 1) / (document_frequency[term] + 1)
                    )
                    + 1.0
                )
                score += (1.0 + math.log(tf)) * idf * query_tf
            if score > 0:
                scored.append((score, -state.state_index, state))

        if not scored:
            return sorted(
                self._states,
                key=lambda state: (
                    state.trajectory_id,
                    state.state_index,
                ),
            )[: self.candidate_top_k]

        scored.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2].trajectory_id,
            ),
            reverse=True,
        )
        return [
            item[2]
            for item in scored[: self.candidate_top_k]
        ]

    def _rank_candidates_phrase_trajectory(
        self,
        query: str,
    ) -> list[StateRecord]:
        """Phrase-aware trajectory-diverse retrieval.

        This is the production promotion of the frozen LongMemEval-V2
        phrase-diverse diagnostic.

        Ranking inputs are limited to the runtime query and stored memory
        state. Gold answers, question type, evidence labels, and evaluator
        metadata are never consulted.
        """
        from collections import Counter, defaultdict
        import math

        if not self._states:
            return []

        # Match the frozen diagnostic exactly: benchmark answer-format
        # instructions are not retrieval semantics.
        marker = "\n\nMark your final answer"
        retrieval_query = (
            query.split(marker, 1)[0]
            if marker in query
            else query
        )

        query_tokens = _tokens(retrieval_query)
        query_unique = set(query_tokens)

        if not query_unique:
            return []

        def ngrams(
            tokens: list[str],
            n: int,
        ) -> set[tuple[str, ...]]:
            if len(tokens) < n:
                return set()

            return {
                tuple(tokens[i:i + n])
                for i in range(len(tokens) - n + 1)
            }

        states = list(self._states)
        docs = [
            _tokens(state.search_text)
            for state in states
        ]

        n_docs = len(docs)

        if n_docs == 0:
            return []

        avgdl = sum(len(doc) for doc in docs) / n_docs

        term_df: Counter[str] = Counter()

        query_bigrams = ngrams(query_tokens, 2)
        query_trigrams = ngrams(query_tokens, 3)

        matched_bigrams: list[set[tuple[str, ...]]] = []
        matched_trigrams: list[set[tuple[str, ...]]] = []

        for doc in docs:
            term_df.update(set(doc))

            matched_bigrams.append(
                ngrams(doc, 2) & query_bigrams
            )
            matched_trigrams.append(
                ngrams(doc, 3) & query_trigrams
            )

        bigram_df: Counter[tuple[str, ...]] = Counter()
        trigram_df: Counter[tuple[str, ...]] = Counter()

        for bis, tris in zip(
            matched_bigrams,
            matched_trigrams,
        ):
            bigram_df.update(bis)
            trigram_df.update(tris)

        def bm25(
            tokens: list[str],
            k1: float = 1.5,
            b: float = 0.75,
        ) -> float:
            counts = Counter(tokens)
            dl = len(tokens)
            score = 0.0

            for term in query_unique:
                tf = counts.get(term, 0)

                if not tf:
                    continue

                df = term_df[term]

                idf = math.log(
                    1.0
                    + (n_docs - df + 0.5)
                    / (df + 0.5)
                )

                denom = (
                    tf
                    + k1
                    * (
                        1.0
                        - b
                        + b * dl / avgdl
                    )
                )

                score += (
                    idf
                    * tf
                    * (k1 + 1.0)
                    / denom
                )

            return score

        def phrase_idf(
            bis: set[tuple[str, ...]],
            tris: set[tuple[str, ...]],
        ) -> float:
            score = 0.0

            # Frozen diagnostic deliberately used the same untuned IDF
            # rule for bigrams and trigrams.
            for gram in bis:
                score += (
                    math.log(
                        (n_docs + 1)
                        / (bigram_df[gram] + 1)
                    )
                    + 1.0
                )

            for gram in tris:
                score += (
                    math.log(
                        (n_docs + 1)
                        / (trigram_df[gram] + 1)
                    )
                    + 1.0
                )

            return score

        rows: list[
            tuple[
                StateRecord,
                float,
                int,
                int,
                float,
            ]
        ] = []

        for state, doc, bis, tris in zip(
            states,
            docs,
            matched_bigrams,
            matched_trigrams,
        ):
            rows.append(
                (
                    state,
                    phrase_idf(bis, tris),
                    len(tris),
                    len(bis),
                    bm25(doc),
                )
            )

        def phrase_key(
            row: tuple[
                StateRecord,
                float,
                int,
                int,
                float,
            ],
        ) -> tuple[float, int, int, float, int, str]:
            state, phrase_score, tri_count, bi_count, bm25_score = row

            return (
                phrase_score,
                tri_count,
                bi_count,
                bm25_score,
                -state.state_index,
                state.trajectory_id,
            )

        ranked = sorted(
            rows,
            key=phrase_key,
            reverse=True,
        )

        # Exact frozen diversity policy:
        # best state from each trajectory under phrase_key,
        # representatives ranked under phrase_key,
        # then top candidate_top_k trajectories.
        grouped: defaultdict[
            str,
            list[
                tuple[
                    StateRecord,
                    float,
                    int,
                    int,
                    float,
                ]
            ],
        ] = defaultdict(list)

        for row in ranked:
            grouped[row[0].trajectory_id].append(row)

        best = [
            max(
                trajectory_rows,
                key=phrase_key,
            )
            for trajectory_rows in grouped.values()
        ]

        best.sort(
            key=phrase_key,
            reverse=True,
        )

        return [
            row[0]
            for row in best[: self.candidate_top_k]
        ]

    def _rank_candidates(
        self,
        query: str,
    ) -> list[StateRecord]:
        if self.candidate_strategy == "legacy_tfidf":
            return self._rank_candidates_legacy(query)

        if (
            self.candidate_strategy
            == "phrase_trajectory_bm25_v1"
        ):
            return self._rank_candidates_phrase_trajectory(
                query
            )

        raise AssertionError(
            "unreachable candidate strategy: "
            f"{self.candidate_strategy}"
        )

    @staticmethod
    def _state_projection(alias: str) -> str:
        return (
            f"{alias}.id AS vertex_id, "
            f"{alias}.trajectory_vertex_id AS trajectory_vertex_id, "
            f"{alias}.trajectory_id AS trajectory_id, "
            f"{alias}.state_index AS state_index, "
            f"{alias}.step AS step, "
            f"{alias}.screenshot AS screenshot, "
            f"{alias}.content_sha256 AS content_sha256, "
            f"{alias}.storage_schema AS storage_schema"
        )

    @staticmethod
    def _reconstruct_chunks(
        rows: list[Any],
        allowed_fields: tuple[str, ...],
    ) -> tuple[dict[str, str], int]:
        by_field: dict[str, list[tuple[int, str]]] = {
            field: [] for field in allowed_fields
        }
        reads = 0

        for row in rows:
            field = str(row["field"])
            require(
                field in by_field,
                f"Unexpected Hydra content field: {field}",
            )
            chunk_index = int(row["chunk_index"])
            content = str(row["content"])
            expected_hash = str(row["content_sha256"])
            require(
                _sha256_text(content) == expected_hash,
                (
                    "Hydra chunk hash mismatch for "
                    f"{field}[{chunk_index}]"
                ),
            )
            by_field[field].append((chunk_index, content))
            reads += 1

        reconstructed: dict[str, str] = {}
        for field in allowed_fields:
            pieces = sorted(by_field[field], key=lambda item: item[0])
            require(
                [index for index, _ in pieces]
                == list(range(len(pieces))),
                f"Non-contiguous Hydra chunks for field {field}",
            )
            reconstructed[field] = "".join(
                content for _, content in pieces
            )
        return reconstructed, reads

    def _read_state_chunks(
        self,
        session: Any,
        state_vertex_id: int,
    ) -> tuple[dict[str, str], int]:
        rows = list(
            session.run(
                (
                    "MATCH (s:LMEV2State {id: $state})"
                    "-[:HAS_CONTENT_CHUNK]->"
                    "(c:LMEV2StateChunk) "
                    "RETURN c.field AS field, "
                    "c.chunk_index AS chunk_index, "
                    "c.content AS content, "
                    "c.content_sha256 AS content_sha256 "
                    "ORDER BY field, chunk_index"
                ),
                state=state_vertex_id,
            )
        )
        return self._reconstruct_chunks(rows, _STATE_CONTENT_FIELDS)

    def _read_trajectory_chunks(
        self,
        session: Any,
        trajectory_vertex_id: int,
    ) -> tuple[dict[str, str], int]:
        rows = list(
            session.run(
                (
                    "MATCH (t:LMEV2Trajectory {id: $trajectory})"
                    "-[:HAS_TRAJECTORY_CHUNK]->"
                    "(c:LMEV2TrajectoryChunk) "
                    "RETURN c.field AS field, "
                    "c.chunk_index AS chunk_index, "
                    "c.content AS content, "
                    "c.content_sha256 AS content_sha256 "
                    "ORDER BY field, chunk_index"
                ),
                trajectory=trajectory_vertex_id,
            )
        )
        return self._reconstruct_chunks(
            rows,
            _TRAJECTORY_CONTENT_FIELDS,
        )

    def _row_to_record(
        self,
        session: Any,
        row: Any,
        fallback: StateRecord,
    ) -> tuple[StateRecord, int]:
        vertex_id = int(row["vertex_id"])
        trajectory_vertex_id = int(row["trajectory_vertex_id"])

        require(
            str(row["storage_schema"]) == _STORAGE_SCHEMA,
            f"Unexpected Hydra storage schema for state {vertex_id}",
        )

        state_content, state_chunk_reads = self._read_state_chunks(
            session,
            vertex_id,
        )
        trajectory_content, trajectory_chunk_reads = (
            self._read_trajectory_chunks(
                session,
                trajectory_vertex_id,
            )
        )

        expected_state_hash = str(row["content_sha256"])
        require(
            _content_digest(
                (
                    state_content["url"],
                    state_content["action"],
                    state_content["thoughts"],
                    state_content["text"],
                )
            )
            == expected_state_hash,
            f"Hydra reconstructed state hash mismatch for {vertex_id}",
        )

        record = StateRecord(
            vertex_id=vertex_id,
            trajectory_vertex_id=trajectory_vertex_id,
            trajectory_id=str(row["trajectory_id"]),
            goal=trajectory_content["goal"],
            outcome=trajectory_content["outcome"],
            state_index=int(row["state_index"]),
            step=int(row["step"]),
            url=state_content["url"],
            action=state_content["action"],
            thoughts=state_content["thoughts"],
            text=state_content["text"],
            screenshot=str(row["screenshot"]),
        )
        return record, state_chunk_reads + trajectory_chunk_reads

    def _fetch_graph_context(
        self,
        candidate: StateRecord,
    ) -> tuple[list[StateRecord], int, int]:
        driver = self._driver()
        ordered: dict[int, StateRecord] = {}
        graph_neighbors = 0
        chunk_reads = 0

        with driver.session(database=self.database) as session:
            if self.retrieval_mode == "graph":
                prev_row = session.run(
                    (
                        "MATCH (p:LMEV2State)-[:NEXT_STATE]->"
                        "(s:LMEV2State {id: $candidate}) "
                        f"RETURN {self._state_projection('p')} "
                        "ORDER BY state_index DESC LIMIT 1"
                    ),
                    candidate=candidate.vertex_id,
                ).single()
                if prev_row is not None:
                    previous, reads = self._row_to_record(
                        session,
                        prev_row,
                        candidate,
                    )
                    ordered[previous.vertex_id] = previous
                    graph_neighbors += 1
                    chunk_reads += reads

                next_row = session.run(
                    (
                        "MATCH (s:LMEV2State {id: $candidate})"
                        "-[:NEXT_STATE]->(n:LMEV2State) "
                        f"RETURN {self._state_projection('n')} "
                        "ORDER BY state_index LIMIT 1"
                    ),
                    candidate=candidate.vertex_id,
                ).single()
                if next_row is not None:
                    following, reads = self._row_to_record(
                        session,
                        next_row,
                        candidate,
                    )
                    ordered[following.vertex_id] = following
                    graph_neighbors += 1
                    chunk_reads += reads

            current_row = session.run(
                (
                    "MATCH (s:LMEV2State {id: $candidate}) "
                    f"RETURN {self._state_projection('s')}"
                ),
                candidate=candidate.vertex_id,
            ).single(strict=True)
            current, reads = self._row_to_record(
                session,
                current_row,
                candidate,
            )
            ordered[current.vertex_id] = current
            chunk_reads += reads

        rows = sorted(
            ordered.values(),
            key=lambda state: (
                state.trajectory_id,
                state.state_index,
            ),
        )
        return rows, graph_neighbors, chunk_reads

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

    def query(
        self,
        query: str,
        query_image: str | None = None,
    ) -> list[MemoryContextItem]:
        _ = query_image
        candidates = self._rank_candidates(query)
        context: list[MemoryContextItem] = []
        seen_states: set[int] = set()
        graph_neighbor_states = 0
        hydra_state_reads = 0
        hydra_chunk_reads = 0
        fetched_contexts: list[
            tuple[StateRecord, list[StateRecord]]
        ] = []

        for candidate in candidates:
            states, neighbor_count, chunk_reads = (
                self._fetch_graph_context(candidate)
            )
            graph_neighbor_states += neighbor_count
            hydra_state_reads += len(states)
            hydra_chunk_reads += chunk_reads

            current = next(
                (
                    state
                    for state in states
                    if state.vertex_id == candidate.vertex_id
                ),
                None,
            )
            require(
                current is not None,
                (
                    "Hydra graph context omitted selected candidate "
                    f"{candidate.vertex_id}"
                ),
            )

            neighbors = [
                state
                for state in states
                if state.vertex_id != candidate.vertex_id
            ]
            fetched_contexts.append((current, neighbors))

        # The official LongMemEval-V2 harness truncates memory context by
        # prefix. Emit every selected candidate before graph expansion so
        # graph neighbors cannot evict higher-priority retrieval seeds.
        ordered_states: list[StateRecord] = [
            current
            for current, _ in fetched_contexts
        ]

        if self.retrieval_mode == "graph":
            for _, neighbors in fetched_contexts:
                ordered_states.extend(neighbors)

        for state in ordered_states:
            if state.vertex_id in seen_states:
                continue
            seen_states.add(state.vertex_id)
            context.append(
                {
                    "type": "text",
                    "value": self._format_state(state),
                }
            )
            if (
                self.include_images
                and state.screenshot
                and Path(state.screenshot).is_file()
            ):
                context.append(
                    {
                        "type": "image",
                        "value": state.screenshot,
                    }
                )

        self._last_query_debug = {
            "retrieval_mode": self.retrieval_mode,
            "candidate_strategy": self.candidate_strategy,
            "graph_radius": self.graph_radius,
            "context_ordering": "candidate-core-first",
            "candidate_count": len(candidates),
            "candidate_vertex_ids": [
                state.vertex_id for state in candidates
            ],
            "hydra_state_reads": hydra_state_reads,
            "hydra_chunk_reads": hydra_chunk_reads,
            "graph_neighbor_states": graph_neighbor_states,
            "context_items": len(context),
            "storage_schema": _STORAGE_SCHEMA,
            "chunk_byte_budget": self.chunk_byte_budget,
        }
        return context
