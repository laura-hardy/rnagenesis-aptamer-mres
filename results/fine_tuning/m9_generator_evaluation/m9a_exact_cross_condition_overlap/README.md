# M9A exact cross-condition overlap

This directory records exact cross-condition overlap on the sealed combined derived ledger. The frozen contract is `m9a-overlap-leakage-definitions-v1` at `config/modelling/generator_eval_overlap_leakage_contract.json`. The runner commit is `a62f3afb53d67ac1619536c26e7848109b0a0ee8`.

The input is `m9_all_conditions_derived_attempt_ledger.jsonl`, 120,080 production rows: B0 30,080 and B1, B2, and D1 30,000 each. Every row in that ledger is a valid canonical sequence. Invalid attempts stay in attempt accounting and do not enter these denominators. This closeout does not complete M9A. TRAIN exact leakage and nearest-TRAIN-distance work remain outstanding.

## Frozen definitions and metric grains

Row overlap uses the valid-canonical-row grain. For source condition A and target condition B, the numerator is the number of valid canonical rows in A whose parsed sequence occurs at least once among valid canonical sequences in B. The denominator is the number of valid canonical rows in A. Each unordered pair is reported in both directions. A repeated sequence contributes once per source row and only membership when its condition is the target. Duplicate rows are not removed or downweighted. A zero required denominator yields a null rate and does not become zero.

Distinct-sequence sensitivity uses the distinct-valid-sequence grain. The shared count is `|S_A intersect S_B|`. Directional distinct coverage uses the source condition's distinct valid-sequence count as the denominator. Jaccard uses `|S_A union S_B|`. The global distinct count is `|S_B0 union S_B1 union S_B2 union S_D1|`. Membership-pattern counts must sum to that union. The summary emits no sequence strings, sequence hashes, attempt identifiers, or overlap member lists.

B0 is an external comparator. Pairs that include B0 are calculated with the same definitions. B0 is not pooled into a B1/B2/D1 aggregate and is not included in the causal B1/B2/D1 comparison.

## Pairwise results

| Pair | A→B rows | B→A rows | Shared | A distinct coverage | B distinct coverage | Union | Jaccard |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0–B1 | 0/30,080 | 0/30,000 | 0 | 0/30,080 | 0/29,983 | 60,063 | 0/60,063 |
| B0–B2 | 0/30,080 | 0/30,000 | 0 | 0/30,080 | 0/30,000 | 60,080 | 0/60,080 |
| B0–D1 | 0/30,080 | 0/30,000 | 0 | 0/30,080 | 0/30,000 | 60,080 | 0/60,080 |
| B1–B2 | 0/30,000 | 0/30,000 | 0 | 0/29,983 | 0/30,000 | 59,983 | 0/59,983 |
| B1–D1 | 1/30,000 | 1/30,000 | 1 | 1/29,983 | 1/30,000 | 59,982 | 1/59,982 |
| B2–D1 | 0/30,000 | 0/30,000 | 0 | 0/30,000 | 0/30,000 | 60,000 | 0/60,000 |

Only B1–D1 had nonzero exact overlap. B1→D1 row overlap is 1/30,000. D1→B1 row overlap is 1/30,000. B1 distinct coverage is 1/29,983. D1 distinct coverage is 1/30,000. The B1–D1 union is 59,982 and the Jaccard overlap is 1/59,982.

The global distinct valid-sequence count is 120,062. Of those, 120,061 sequences occur in exactly one condition and one sequence occurs in exactly two. Counts for exactly three and exactly four conditions are zero. The single shared sequence is the B1–D1 member. Membership-pattern counts sum to 120,062.

## Review and access boundary

An independent local review verified the downloaded hashes and independently recomputed all overlap results without importing the production implementation.

TRAIN, VALIDATION, REF, EVAL, models, checkpoints, structure tools, and AptaRank were not accessed. The combined JSONL ledger remains a regenerable server-side artifact and is not committed. The frozen overlap contract and the governing evaluation plan were not modified.

## Hashes

| Artifact | SHA-256 |
| --- | --- |
| `m9_cross_condition_overlap_summary.json` | `03e2b8f6d1dd21181c2d5521a552ec4aac6f78ad4fbd0dc5260ca105e849c32e` |
| `m9_cross_condition_overlap_manifest.json` | `555159f1f0ca2cf2311ed4c797c2f22538e0a230e725f79eff90e8dcc94259c9` |
| Combined ledger `m9_all_conditions_derived_attempt_ledger.jsonl` | `d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e` |
| Contract `config/modelling/generator_eval_overlap_leakage_contract.json` | `6aeaa2338776cbe7aceffef63ee4ca7dfd7ed3643aa7d1e400fd54a02d113535` |
| Governing plan `docs/aptarank_full_mres_thesis_evaluation_plan.md` | `fc6963f01f7d4ab311774865bda15626facdb753ffa0db06b01b338d88162b51` |

The manifest digest is the digest of the manifest file bytes. It is not embedded in the manifest.

## Limitation

Exact cross-condition separation does not establish TRAIN novelty, structural novelty, biological quality, or superiority.
