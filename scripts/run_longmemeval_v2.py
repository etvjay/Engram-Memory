#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import sys


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    lme_root_raw = os.environ.get("LONGMEMEVAL_V2_ROOT")
    if not lme_root_raw:
        raise SystemExit("Set LONGMEMEVAL_V2_ROOT to the pinned LongMemEval-V2 checkout")
    lme_root = Path(lme_root_raw).expanduser().resolve()
    if not (lme_root / "evaluation" / "harness.py").is_file():
        raise SystemExit(f"Invalid LONGMEMEVAL_V2_ROOT: {lme_root}")

    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(lme_root))

    # Importing the adapter registers memory_type=engram_hydra in the official
    # LongMemEval-V2 registry before the harness loads the memory config.
    from engram.longmemeval.hydra_memory import EngramHydraMemory  # noqa: F401
    from evaluation.harness import main as harness_main

    harness_main()


if __name__ == "__main__":
    main()
