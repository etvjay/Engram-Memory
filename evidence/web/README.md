# Engram canonical web evidence

`evidence/web/index.json` is the machine-readable bridge from the
Engram-Memory research repository to Engram product surfaces.

## Provenance

The top-level `commit` identifies the committed research-evidence snapshot
summarized by this index.

It is intentionally different from the later commit that publishes
`index.json`; embedding a commit's own final SHA would be circular.

`generated_at` comes from the source commit timestamp, making regeneration
from the same evidence snapshot deterministic.

## Evidence boundary

At the PRISM-14 snapshot:

- A0 — TESTED
- A1 — TESTED
- A2 — TESTED
- A3 — TESTED
- A4 behavioral causal memory — NOT_RUN
- PRISM-14 structural causal provenance — TESTED

PRISM-14 establishes `RECALL != INFLUENCE` and records explicit influence
provenance connecting recalled experience to later decision, action, and
outcome.

It does not establish a behavioral counterfactual.

`CHANGED_ACTION` remains unclaimed until PRISM-15 passes a controlled
memory-OFF versus memory-ON experiment.

## Build

    python3 scripts/build_evidence_index.py \
      --source-commit <research-commit> \
      --ref <research-ref>

Validate:

    python3 scripts/build_evidence_index.py \
      --check \
      --source-commit <research-commit> \
      --ref <research-ref>

The producer verifies committed SHA256 evidence bundles before publishing
their normalized summaries.
