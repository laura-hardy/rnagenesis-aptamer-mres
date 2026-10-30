# Future shortlisting sequences

Status: `FUTURE_SHORTLISTING_SET_SCIENTIFICALLY_COMMITTED`

This result contains the 50 highest Tier 1 ranked D1 candidates from the already validated Section 10 AptaRank export. It implements evaluation-plan v3.10 after biology-supervisor consultation. No AptaRank run or score recomputation occurred.

## Final disposition

No sequence is advanced to experimental validation within the MRes thesis. These 50 sequences are retained as **candidates progressing towards shortlisting for experimental validation** in future work, after a better computational prioritisation and evaluation approach has been developed.

## Selection

- Source: the previously prepared Tier-1-only top-100 sensitivity option.
- Retained: AptaRank Tier 1 ranks 1–50, without replacement or manual reordering.
- Primary and only selection metric: Tier 1 rank.
- Shuffle token: coarse annotation only (48 pass; 2 fail).
- Tier 2 band: coarse annotation only (3 strong; 6 moderate; 41 weak).
- Candidates carrying both shuffle-pass and moderate/strong annotations: 8/50. This count did not affect retention.

The original closed Section 10 result remains unchanged: its earlier gates produced 137 jointly eligible candidates and a 100-candidate review pool. Version 3.10 is a later, outcome-aware final-disposition amendment and is recorded separately rather than rewriting that historical result.

## Files

- `future_shortlisting_candidates.jsonl`: sequence, AptaRank scores/ranks/annotations, identifiers and complete D1 provenance for each candidate.
- `future_shortlisting_sequences.fasta`: sequence hand-off with rank and principal identifiers in the headers.
- `dashboard_candidate_numbers.txt`: AptaRank dashboard candidate numbers/ranks 1–50.
- `future_shortlisting_manifest.json`: input hashes, denominators, annotation counts and validation checks.
- `future_shortlisting_decision_record.json`: supervisor-informed final methodology and claim boundary.

## Interpretation boundary

Tier 2 and shuffle outputs are retained for traceability but are not validated binding evidence and did not determine selection. The selected NDM-1 cavity carries the following warning:

> This cavity is oddly shaped: its robust extent and equivalent-sphere diameter disagree by more than 2×. The geometric comparison assumes a roughly convex pocket.

The output is not a validated binder set, an experimental shortlist or evidence of NDM-1 affinity, specificity, inhibition or function.
