# Final thesis filtered selection

Status: `FINAL_THESIS_FILTERED_SELECTION`.

This is the 50-candidate computational selection reported in thesis §4.6,
Table A.13 (printed pp. 110–111) and Figure 4.13. The repository owner confirmed
that this filtered selection is the final result for the public thesis companion.
The [decision record](selection_decision.json) documents that choice.

## Selection from frozen results

1. Start with the closed 30,000-member D1 NDM-1 run: 29,583 scored and 417 technical exclusions.
2. Use the exact Tier 2 export covering Tier 1 ranks 1–1,000.
3. Require `shuffle == pass` and compatibility `moderate` or `strong`.
4. Sort the 137 jointly eligible candidates by ascending frozen Tier 1 rank, then ascending opaque candidate ID.
5. Retain the first 50, without manual reordering or replenishment.

Among the top 1,000, 558 pass shuffle and 236 have moderate/strong compatibility;
137 pass both. The original filtered review pool retained the first 100 of those
137. The thesis selection is its first 50, spanning Tier 1 ranks 2–248: 34 moderate
and 16 strong, with 33 candidates from training seed 43 and 17 from seed 44.
Sequences range from 32 to 96 nt.

All 50 IDs, sequences, ranks, lengths, seeds, technical blocks and rounded Tier 1
scores match Table A.13. The first three sequences also match Figure 4.13. The
selected sequences are unique canonical RNA. This extraction used existing frozen
exports and review-pool provenance; AptaRank and score computation were not rerun.

## Files and verification

| File | Contents |
| --- | --- |
| [thesis_filtered_candidates.jsonl](thesis_filtered_candidates.jsonl) | 50 generated sequences, exact scores, source IDs, training/generation provenance, selection order and sequence SHA-256 |
| [thesis_filtered_sequences.fasta](thesis_filtered_sequences.fasta) | The same 50 sequences in selection order |
| [eligible_candidates.jsonl](eligible_candidates.jsonl) | Sequence-free inventory of all 137 eligible candidates, with exact scores and original ranks |
| [selection_decision.json](selection_decision.json) | Final-selection rule and the disposition of the earlier hand-off |
| [selection_manifest.json](selection_manifest.json) | Source hashes, denominators, thesis identity and validation checks |
| [SHA256SUMS](SHA256SUMS) | Checksums of this directory's files other than the checksum file itself |

The public 137-row inventory allows the final ordering and 50-row cutoff to be
checked. The raw full-pool and exact Tier 2 exports and the original 100-row review
pool remain unbundled; their paths and SHA-256 identities are recorded in the
manifest. Full source rederivation requires those files.

On macOS, check the directory checksums with `shasum -a 256 -c SHA256SUMS`.

## Historical output and interpretation

The earlier [v3.10 directory](../future_shortlisting_sequences/README.md) retains
Tier 1 ranks 1–50 without shuffle or compatibility gates. It remains unchanged
as a historical hand-off and is superseded for final thesis selection. Frozen
supervisor reports and plans may still describe that earlier disposition.

No sequence is advanced to experimental validation within this thesis. Shuffle
and compatibility values are computational outputs, not evidence of NDM-1
binding, affinity, specificity or inhibition. The original pocket warning remains:

> This cavity is oddly shaped: its robust extent and equivalent-sphere diameter disagree by more than 2×. The geometric comparison assumes a roughly convex pocket.
