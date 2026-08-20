from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path

from memory_modules.memory import (
    Memory,
    MemoryContextItem,
    register_memory,
    require,
)
from memory_modules.trajectory_store import prepare_trajectory_insert

from .hydra_memory import (
    EngramHydraMemory,
    StateRecord,
    _clean,
    deterministic_vertex_id,
)


_LOCAL_STORAGE_SCHEMA = "local-flat-state-records-v1"


@register_memory
class EngramFlatLocalMemory(EngramHydraMemory):
    """Genuine non-Hydra flat-memory control for LongMemEval-V2.

    A1 deliberately reuses the frozen EngramHydraMemory lexical selector
    implementation without invoking the Hydra constructor, driver, state
    reconstruction, or graph traversal.

    This preserves selector semantics while changing the storage/retrieval
    substrate:

      A1: local prepared state records, no graph
      A2: Hydra state reconstruction, no graph expansion
      A3: Hydra state reconstruction + radius-1 NEXT_STATE expansion

    Gold answers, evidence labels, question types, and evaluator metadata
    are never runtime selection inputs.
    """

    memory_type = "engram_flat_local"

    def __init__(self, memory_params: dict[str, object]) -> None:
        # Do not invoke EngramHydraMemory.__init__ because that constructor
        # validates Hydra credentials and prepares a Hydra driver path.
        Memory.__init__(self, memory_params)

        self.data_root_env = str(
            memory_params.get(
                "data_root_env",
                "LONGMEMEVAL_V2_DATA_ROOT",
            )
        ).strip()

        self.candidate_top_k = int(
            memory_params.get("candidate_top_k", 3)
        )

        self.candidate_strategy = str(
            memory_params.get(
                "candidate_strategy",
                "phrase_trajectory_bm25_v1",
            )
        ).strip().lower()

        self.include_images = bool(
            memory_params.get("include_images", True)
        )

        self.max_state_chars = int(
            memory_params.get("max_state_chars", 6000)
        )

        # These values are intentionally explicit for control introspection.
        self.retrieval_mode = "flat"
        self.graph_radius = 0

        require(
            self.data_root_env,
            "engram_flat_local data_root_env must be non-empty",
        )

        require(
            self.candidate_top_k > 0,
            "engram_flat_local candidate_top_k must be positive",
        )

        require(
            self.candidate_strategy == "phrase_trajectory_bm25_v1",
            (
                "engram_flat_local is frozen to "
                "candidate_strategy=phrase_trajectory_bm25_v1"
            ),
        )

        require(
            self.max_state_chars > 0,
            "engram_flat_local max_state_chars must be positive",
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

        states_obj = simplified.get("states")

        require(
            isinstance(states_obj, list) and states_obj,
            f"No states for {trajectory_id}",
        )

        require(
            len(states_obj) == len(prepared.screenshot_sources),
            f"Screenshot/state count mismatch for {trajectory_id}",
        )

        for state, screenshot_src in zip(
            states_obj,
            prepared.screenshot_sources,
        ):
            require(
                isinstance(state, dict),
                f"Invalid state in {trajectory_id}",
            )

            state_index = int(state["state_index"])

            vertex_id = deterministic_vertex_id(
                "state",
                f"{trajectory_id}:{state_index}",
            )

            # Avoid accidental duplicate local insertion while keeping
            # semantic IDs identical to A2/A3.
            if vertex_id in self._state_by_id:
                continue

            record = StateRecord(
                vertex_id=vertex_id,
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

            self._states.append(record)
            self._state_by_id[record.vertex_id] = record

    def query(
        self,
        query: str,
        query_image: str | None = None,
    ) -> list[MemoryContextItem]:
        _ = query_image

        candidates = self._rank_candidates(query)

        context: list[MemoryContextItem] = []

        for state in candidates:
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
            "memory_type": self.memory_type,
            "backend": "local_flat",
            "retrieval_mode": "flat",
            "candidate_strategy": self.candidate_strategy,
            "candidate_top_k": self.candidate_top_k,
            "graph_radius": 0,
            "context_ordering": "candidate-core-only",
            "candidate_count": len(candidates),
            "candidate_vertex_ids": [
                state.vertex_id for state in candidates
            ],
            "candidate_state_refs": [
                {
                    "trajectory_id": state.trajectory_id,
                    "state_index": state.state_index,
                }
                for state in candidates
            ],
            "local_state_reads": len(candidates),
            "hydra_driver_attempted": False,
            "hydra_state_reads": 0,
            "hydra_chunk_reads": 0,
            "graph_neighbor_states": 0,
            "context_items": len(context),
            "storage_schema": _LOCAL_STORAGE_SCHEMA,
        }

        return context

    def _save_backend(self, output_dir: Path) -> None:
        state_file = output_dir / "states.jsonl"

        with state_file.open("w", encoding="utf-8") as handle:
            for state in self._states:
                handle.write(
                    json.dumps(
                        asdict(state),
                        sort_keys=True,
                        ensure_ascii=True,
                    )
                    + "\n"
                )

    def _load_backend(self, input_dir: Path) -> None:
        state_file = input_dir / "states.jsonl"

        require(
            state_file.is_file(),
            f"Missing A1 state file: {state_file}",
        )

        self._states = []
        self._state_by_id = {}

        with state_file.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()

                if not line:
                    continue

                raw = json.loads(line)

                require(
                    isinstance(raw, dict),
                    (
                        "Invalid A1 state record at "
                        f"{state_file}:{line_number}"
                    ),
                )

                record = StateRecord(**raw)

                require(
                    record.vertex_id not in self._state_by_id,
                    (
                        "Duplicate A1 state vertex "
                        f"{record.vertex_id}"
                    ),
                )

                self._states.append(record)
                self._state_by_id[record.vertex_id] = record
