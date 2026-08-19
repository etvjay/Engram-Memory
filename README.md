# Engram Memory

**Benchmark-first execution memory on HydraDB.**

Engram Memory is the fresh Hack Hydra submission repository for Track 03 — Memory + Context Retrieval.

> Benchmark first. Primitive second. Application third.

The project tests whether a memory system can preserve useful experience across long histories and sessions, retrieve the right evidence under changing conditions, respect chronology and updates, abstain when evidence is absent, and expose causal provenance when prior experience changes later behavior.

## Hackathon scope

This repository is intentionally fresh for Hack Hydra and is built against the HydraDB open-source repository.

Primary benchmark suite:

- LongMemEval
- LongMemEval-V2
- BEAM

Engram-specific extensions:

- runtime-death continuity
- recall != influence
- causal memory receipts
- agent/workspace isolation
- temporal repair / change-of-mind provenance

Applications and product demos sit on top of the audited memory substrate; they do not replace benchmark evidence.

## Governing audit

See [`AUDIT.md`](AUDIT.md). Every public claim, benchmark number, ablation, and demo capability must trace to reproducible evidence.

## Repository status

The repository starts with audit and reproducibility scaffolding only. HydraDB OSS integration, benchmark adapters, evidence manifests, and the application surface are built here during the Hack Hydra build window.

## Upstream / prior work

The broader Engram research and prior implementation live separately in `etvjay/Engram`. That repository is treated as pre-existing upstream/reference work, not as this hackathon submission's commit history. Any reused code will be explicitly attributed.

## License

MIT. See [`LICENSE`](LICENSE).
