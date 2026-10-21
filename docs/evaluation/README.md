# Evaluation documentation

This directory is the canonical home for evaluation plans, method reconciliations,
closed result narratives and sequence-free supervisor materials. Historical paths at
the top of `docs/` are retained as byte-identical compatibility copies because frozen
scripts, contracts and manifests cite those exact locations and reject symlinks.

## Current AptaRank status

- Sections 6–10 of the computational evaluation are complete, independently reviewed
  and closed.
- The deterministic 100-candidate D1 pool is ready for joint review with the biology
  supervisor.
- The only remaining evaluation task is that manual review and its dated decision
  record, retaining at most 50 candidates and introducing none from outside the
  closed pool.
- No further AptaRank run is planned at this pause point.

See [the concise status tracker](aptarank_evaluation_status.md) for the hand-off state.

## Supervisor materials

- [AptaRank supervisor briefing](aptarank_evaluation_report_supervisor.md)
- [AptaRank detailed tables and figures](aptarank_evaluation_supervisor_tables.md)
- [AptaRank figure assets](assets/figures/)
- [Generator-evaluation supervisor briefing](generator_evaluation_report_supervisor.md)
- [Generator-evaluation tables](generator_evaluation_supervisor_tables.md)

`SHA256SUMS` binds the AptaRank supervisor pack and status tracker; it is not a
checksum catalogue for every historical document in this directory.

No sequence-bearing candidate material is stored here. Raw AptaRank exports remain
inside ignored `raw/` result directories. The restricted Section 10 candidate list
remains inside the ignored, owner-only `restricted/` directory.
