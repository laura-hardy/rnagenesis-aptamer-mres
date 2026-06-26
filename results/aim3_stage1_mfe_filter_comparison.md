# Stage 1 MFE filter comparison

Comparison of poster Stage 1 runs **without** vs **with** the lenient normalised-MFE hard filter.

## MFE cutoff

| Setting | Value |
|---------|-------|
| Source distribution | `data/processed/corpus_distributions/aptadiff_datasetA_p6_with_mfe.json` |
| Quantile used | **q95** (default; q99 is more lenient) |
| `max_normalised_mfe` | **0.0** |
| Reference raw MFE at q95 | **0.0** kcal/mol |
| Reference normalised MFE mean | **−0.093177** |
| Reference normalised MFE q90 | **−0.008333** |
| Reference normalised MFE q95 | **0.0** |
| Reference normalised MFE q99 | **0.0** |

Filter logic: pass if `normalised_mfe <= max_normalised_mfe`; fail if `normalised_mfe > max_normalised_mfe`.

Because ViennaRNA MFE values are ≤ 0, a cutoff of 0.0 removes only sequences with **positive** normalised MFE (essentially no predicted folding). At q95, ≥5% of Aptadiff A reference sequences already have MFE = 0, so this is the most lenient upper-tail threshold available from the reference distribution.

**Interpretation:** This is a lenient “does this fold at all?” hard filter relative to the Aptadiff A reference corpus. It does **not** select for optimal folders.

## Pass rates

| Condition | Config | Total | Passed | Pass rate |
|-----------|--------|------:|-------:|----------:|
| Null model | no MFE (`stage1_hard_filter_aptadiffA_poster.json`) | 30,000 | 12,602 | **42.0%** |
| Null model | with MFE (`stage1_hard_filter_aptadiffA_poster_with_mfe.json`) | 30,000 | 12,602 | **42.0%** |
| Unadapted RNAGenesis | no MFE | 30,080 | 12,337 | **41.0%** |
| Unadapted RNAGenesis | with MFE | 30,080 | 12,337 | **41.0%** |

**Incremental MFE effect:** 0 additional rejections for both conditions (pass counts unchanged).

## Per-filter rejection counts (with-MFE runs)

| Condition | Homopolymer fail | GC fail | MFE fail | Overall pass |
|-----------|-----------------:|--------:|---------:|-------------:|
| Null model | 16,682 | 2,802 | **0** | 12,602 |
| Unadapted RNAGenesis | 16,944 | 3,093 | **0** | 12,337 |

Homopolymer remains the dominant rejection driver (~56% of inputs fail homopolymer before other filters compound).

## Output paths

| Run | Summary JSON |
|-----|--------------|
| Null, no MFE | `results/aim3_stage1_null_30k/stage1_summary.json` |
| Null, with MFE | `results/aim3_stage1_null_30k_with_mfe_filter/stage1_summary.json` |
| Unadapted, no MFE | `results/aim3_stage1_unadapted_30k_poster_config/stage1_summary.json` |
| Unadapted, with MFE | `results/aim3_stage1_unadapted_30k_poster_config_with_mfe_filter/stage1_summary.json` |

## Notes

- Near-deduplication remains disabled in both configs.
- MFE was computed in all runs (`skip_mfe: false`); the no-MFE config simply did not apply MFE as a hard filter (`mfe` status: `not_applied`).
- If a stricter MFE cutoff is desired later, consider q90 (−0.008333 normalised) or a fixed offset below zero; q95/q99 both collapse to 0.0 for this reference corpus.
