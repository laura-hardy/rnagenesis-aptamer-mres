# M9C-2 descriptive REF summary preparation

| Item | Value |
|---|---|
| Status | `PREPARATION_FROZEN_SYNTHETIC_ONLY_PRODUCTION_REF_NOT_RUN` |
| Stage | M9C-2. M9C is not complete. |
| Schema | `m9c-descriptive-ref-summary-v1` |
| Contract | `config/modelling/aptarank_descriptive_ref_summary_contract.json`, SHA-256 `3a662b960ab3e4a70b7515acdd532d45e93e31e80ff3025922d04f7df9d0fab4` |
| Module | `scripts/modelling/aptarank_descriptive_ref_summary.py` |
| Plan | `docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md`, version 3.3. This note does not modify that plan. |

This preparation freezes a sequence-free descriptive summary of the five raw REF components. It does not open production REF, calculate the production summary, calibrate AptaRank, or unlock EVAL. No number below is a scientific result.

## Components

The components are the reviewed AptaRank raw features, not calibrated scores.

| Component | Definition |
|---|---|
| Normalized MFE | ViennaRNA MFE divided by length, after `RNA.md()` with `uniq_ML = 1`, MFE, `exp_params_rescale`, and `pf()` |
| Ensemble defect | `fc.ensemble_defect(mfe_struct)` after `pf()` |
| Positional entropy | Mean of `fc.positional_entropy()[1:n+1]` |
| Stem fraction | Paired positions in the MFE dot-bracket, divided by length. The reviewed forgi numerator is `sum(2 * stem_length)`. This preparation does not import forgi. |
| GC fraction | `(count("G") + count("C")) / length` |

The fold sets no temperature, dangle, or salt value. Those details remain the defaults of whichever ViennaRNA interpreter runs a later production summary.

## Population and aggregate

Retention calls the attempt-3 function `_retain_rows`: existing order, first identity for each distinct `sequence_core`, and no later replacement. The required accounting is 131 source rows, 113 cores, and 18 duplicate-core collapses.

Short and long labels use the frozen S6 two-component GMM, method `gmm_k2_maximum_posterior`, without refitting. Component 0 is short. A posterior tie goes short. The summary must contain 65 short cores and 48 long cores.

The aggregate has strata `all`, `short`, and `long`. Each component records the successful count, the error or missing count, the mean, the population standard deviation with divisor `n`, the minimum, the first quartile, the median, the third quartile, and the maximum. Quartiles use NumPy's linear percentile, named `numpy_percentile_linear`. A non-finite component or a count mismatch is rejected. A successful table records an error count of 0. The table is labelled descriptive. It is not an empirical CDF, a calibrated score, a composite, a weight, a shuffle pass, or a candidate ranking.

## Tier 2 bank decision

The 20 Tier 1 candidate shuffles and the 5,085-member REF-derived Tier 2 compatibility bank are different quantities. The 20 shuffles are the Standard preset's per-candidate dinucleotide controls. The bank is the compatibility control set built from the accepted REF upload.

The verified bank identity is the construction record: accepted REF upload digest `5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6`, 113 sources, AptaRank 0.1.0, schema 1.0.0, git `49a85609e352`, ViennaRNA 2.7.2, forgi 2.2.3, fpocket 4.0, equal 45-per-source dinucleotide-preserving allocation, seed 42, 100 ensemble samples, and realized count 5,085.

The deployment exposed no explicit bank ID or content hash. The ushuffle version is unknown. No bank ID or content hash is claimed. This construction identity is accepted as sufficient provenance for the planned deployed percentile analysis, with those limitations reported. v3.3 is unchanged.

## Generator ViennaRNA settings

The generator metric specification still has the unresolved item `viennarna_production_settings_not_pinned` for `mfe`, `mfe_per_nt`, and `paired_fraction`. Those metrics remain synthetic-injection-only. They are not the AptaRank normalized-MFE component. This preparation does not modify that specification and does not invent generator folding settings.

Resolving the pin here would broaden the change. The H200 interpreter used to import ViennaRNA for the synthetic fold check is 2.7.0. The live AptaRank deployment recorded ViennaRNA 2.7.2. Those versions are not interchangeable as a silent pin.

The smallest defensible resolution, not applied in this change, is a scope decision: leave the three generator structure metrics synthetic-injection-only through this M9C AptaRank preparation, and keep their production ViennaRNA settings unpinned. The alternative is an explicit pin that names one ViennaRNA version and states whether the generator model is AptaRank's `uniq_ML = 1` constructor or another model. That choice is still required before those generator metrics leave synthetic injection. It is not made here.

## Boundary

The no-argument command checks the contract pins and accepts no path. Production REF, EVAL, production candidates, TRAIN, VALIDATION, models, and checkpoints stay closed. AptaRank is not run. Nothing is written under `results/`. M9C is not complete, and there is no EVAL-unlock record.
