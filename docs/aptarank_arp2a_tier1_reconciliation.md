# ARP-2A — Tier 1 method and statistical-contract reconciliation

| Item | Value |
|---|---|
| Package | ARP-2A |
| Branch | `generator-eval-prep` |
| HEAD at audit | `b530e7e4753604728a25042f34441d4e0359d172` |
| Governing plan | `docs/aptarank_full_mres_thesis_evaluation_plan.md`, version 3.0, 7 October 2026 |
| Status | Reconciliation only. No Tier 1 analysis code is implemented by this package. |
| Data used | Tracked code, configuration, tests, and method documentation. Synthetic ARP-1 fixtures were read. No EVAL, REF, VALIDATION, TRAIN, production pool, checkpoint, or camera-ready result file was opened. |

The governing plan is authoritative. A formula that appears only in provisional historical evidence stays provisional. This document does not choose it.

## Classification labels

| Label | Meaning in this audit |
|---|---|
| `governing_plan_fixed` | Written in the version 3.0 plan. ARP-2 may implement this statement. |
| `authoritative_implementation_verified` | Present in tracked code or configuration on this HEAD, and the worktree bytes match that blob. |
| `provisional_historical_evidence` | Reviewer-supplied method notes, or an earlier tracked narrative. Not adopted. |
| `requires_live_synthetic_ui_verification` | Depends on the deployed AptaRank UI or its download. ARP-1 has `deployment_verified: false`. |
| `requires_prespecified_method_decision` | Needed before M9C, and not fixed by the plan or by tracked code. This audit does not choose a value. |
| `not_implemented_in_local_code` | No tracked function computes it. |
| `deferred_or_not_applicable` | A different analysis. ARP-2 must not import it as a Tier 1 definition. |

## Executive summary

The authoritative AptaRank scoring source is absent from this repository. There is no submodule, no Tier 1 scoring module, and no tracked configuration that states the component equations, the empirical-CDF algebra, the centrality transform, the numeric weights, or the shuffle generator. `git ls-files` names AptaRank only in the governing plan, the ARP-1 draft interface, its tests and synthetic fixtures, and documents that discuss the evaluation boundary.

The deployed AptaRank UI is the scoring authority for the thesis path. Local code prepares uploads and private keys, validates Laura's downloads, joins them by opaque candidate id, and computes the prespecified summaries. It does not recompute normalized MFE, ensemble defect, positional entropy, stem fraction, GC fraction, the composite aptamer-likeness score, or the shuffle draw. Those quantities are `not_implemented_in_local_code`. Numeric recomputation stays blocked until a scoring source is recovered under a later reviewed decision. Recovery is not part of ARP-2A.

What the plan does fix is the scientific contract around that missing scorer: 113 unique corrected REF cores as the calibration set; five named components and their favour directions; a preserved weighted mean whose weights are frozen before EVAL; the analysis pass rule `p ≤ 0.05`; one exact-length uniform A/C/G/U control per EVAL core under master seed 42; a 308-row blinded upload; private-key joins; descriptive AUROC against that uniform floor; cluster resampling with 10,000 replicates, seed 42, and percentile intervals; and the claim boundaries in section 10 of this document.

The reviewer-supplied files listed below describe a composite, an empirical CDF, a shuffle p-value, equal weights, and a Wilcoxon signed-rank test. Those descriptions agree with some sentences in the 25 September 2026 supervisor-review narrative. They are not in the version 3.0 plan as algebra, and they are not in tracked code. They remain `provisional_historical_evidence`. ARP-2 code must not implement them until a prespecified method decision adopts each one, and a synthetic UI preflight binds the export to the adopted rule.

Generator `mfe_per_nt` is `float(mfe) / len(sequence)` on a caller-supplied fold. AptaRank normalized MFE is a different component. The generator also implements `paired_fraction` and `pooled_gc_fraction`, and two different quantile routines. None of those is the Tier 1 component or the Tier 1 median/IQR convention.

## 1. Source provenance

Worktree SHA-256 was computed from the file bytes. The Git blob is `git hash-object` of those bytes. For every tracked row, that blob equals `git rev-parse HEAD:<path>`.

Reviewer-supplied rows were not opened. Their SHA-256 values are the hashes supplied with this package. They have no blob in this repository. The enclosing directory of those files was not clean, so no Git commit is their provenance.

| Path | Git blob | SHA-256 | Worktree matches HEAD | Symbol, key, or lines | Authority | ARP-2 use |
|---|---|---|---|---|---|---|
| `docs/aptarank_full_mres_thesis_evaluation_plan.md` | `96673c761da6b7ecc7f9b958f025449ecd6727c6` | `e6193d0d14245049c218b4da0ef8059fb63b2f31e4885b3457cd44e41b76c50c` | yes | Version 3.0; §§1, 3, 6, 7, 13 | `governing_plan_fixed` | Implement only the statements classified fixed below. |
| `config/modelling/aptarank_io_spec.json` | `017a043b8e8dc104d9554a8e49af2d592347300f` | `d32484b1dd0de0e344aa8cc5f5900fe1c184ab5261392f2dbfb941ba68d6d4a1` | yes | `aptarank-io-arp1-draft-r3`; `deployment_verified` false; shortlist columns; `shuffle_threshold` null | `authoritative_implementation_verified` for the draft validator | Import the draft mechanical checks. Do not treat the draft as a frozen UI schema. |
| `docs/aptarank_arp1_interface_reconciliation.md` | `042d704112d3ba61cb3d83b39d5f4da25c0c9cc9` | `2b1c932af92aa2494804e0f4a5b2c6c2a584ccceefbb06de18f5878454f3d4fb` | yes | Draft revision 3; shuffle literals uninterpreted | `authoritative_implementation_verified` as the ARP-1 note | Same boundary as the spec. |
| `scripts/modelling/aptarank_io_preflight.py` | `9d1593786a9c09eb52af0682b6b91303c6454976` | `020ff616caade2983743eb941e7d4ce00d505f9bb349f10b428f98adb505263b` | yes | `SHORTLIST_COLUMNS`; `classify_likeness`; `_check_shortlist_rows`; `sequence_matches_by_id` | `authoritative_implementation_verified` | Import for synthetic export validation. Validate UI output only after a later schema revision. |
| `tests/modelling/test_aptarank_io_preflight.py` | `e30179dfac84d44a456cc497da55870376dcc34e` | `bea77ce03decc404b023cb46ade7e7c64aee49348c94675fb7d912b05f052dd0` | yes | Fail-closed schema, id, sequence, and non-finite score tests | `authoritative_implementation_verified` | Keep as the ARP-1 regression suite. ARP-2B adds a separate suite. |
| `tests/modelling/fixtures/aptarank_arp1/valid_target_free_rigorous_shortlist.csv` | `daddc66db16b2913fd82d28cde92bed829db9865` | `d5926fa4f4ab38c72df75d71bd481420922dea8d1b1182e78e722c94366b4cf1` | yes | Synthetic rows: likeness `0.125` and `-3.5`; shuffle `pass`/`fail` | `authoritative_implementation_verified` for what the draft accepts | Use only as a synthetic validator fixture. |
| `scripts/modelling/m6_diagnostic_generation.py` | `6ad3982047de468e662f8f357e2a7394a2b18264` | `83f299bea7ec69406c898ad0e971bebf06056beb58649de0c25a5cc6d7195726` | yes | `_quantiles` lines 1044–1057; `structure_features` lines 1060–1065 | `deferred_or_not_applicable` to AptaRank scoring | Do not import as normalized MFE, stem fraction, or the Tier 1 quantile rule. |
| `scripts/modelling/generator_eval_analysis.py` | `3e264811127cda4e9ecd3111e180d43efbc76aca` | `0c8ebe27273734bc30931932d84271639bdf8aefb4cf85417881084e74f126bb` | yes | `pooled_gc_fraction` lines 179–192; `aptarank_normalized_mfe: False` in `_blank_structure`, `_structure_quantiles`, `_structure_block` | `authoritative_implementation_verified` as a generator boundary | Do not import `pooled_gc_fraction` as the AptaRank GC component. |
| `scripts/modelling/generator_eval_preflight.py` | `1fc7de706398aba18c2cba92cd749e56310c6352` | `7787ed8687a7595b3fbe14949ef03c6aa80a83e87d4800ae62903a01368b05d8` | yes | `RESOLVED_REQUIRED_PHRASES["alias_mfe_per_nucleotide"]` | `authoritative_implementation_verified` as a generator boundary | Keep the generator id `mfe_per_nt` separate. |
| `config/modelling/generator_eval_metric_spec.json` | `101f5d68c74c054490501f7a40ae43cd9fa09af3` | `8c14b2c51eca6bda2e4d69bd0b823a054bedeb764bba87933ecb8848ff89abd0` | yes | Metric rows `mfe`, `mfe_per_nt`, `paired_fraction`, `pooled_gc_fraction`; resolution `alias_mfe_per_nucleotide` | `authoritative_implementation_verified` for generator metrics | Do not add an AptaRank component to this spec. |
| `docs/generator_eval_gep2a_metric_reconciliation.md` | `86aef9ae1a3b115b6db0190f398c22c9f62c5197` | `94395c865f4a8b9d4b70db5af5240d5da018d1af46cdff02474e09c1c2f41088` | yes | §3.4; cluster-resampling note that GEP does not copy the Tier 1 bootstrap | `authoritative_implementation_verified` as the generator reconciliation | Leave the Tier 1 bootstrap unimplemented there. |
| `docs/planned_evaluation_report.md` | `6a6e132d2907addcbe6e469da40a8d6e7917b72e` | `fd760a2816283ba36a3911133d3d8be9059121dbef8cecff0076c5ab4066db4d` | yes | 25 September 2026 review request; §3.4 describes plan v2.3 | `provisional_historical_evidence` | Do not promote its equal-weight or 99-shuffle sentences. |
| `docs/data_curation/rna_aptamer_corpus_curation_plan.md` | `ef3afd29fea161388da73d3ac97233a56c9af41d` | `bbe93710582540b4aa80248a3e4c549ce358139b07db5fe4215495d416385802` | yes | v1.6; REF fits Tier 1 reference distributions only; lines 59–75, 199, 997 | Corpus role is fixed by the governing plan. The phrase "length-conditioned" does not choose pooled versus stratified calibration. | Do not open role files from this plan. |
| `scripts/data_preparation/adapters/s6_profile.py` | `db2c30fa37e30b6ca48b9f0c1e463d34e017c2af` | `cc0939579fd6fbbfffb3eefbadf85e4acb158cdfe34925978e26f6003924d6d1` | yes | `percentile_bundle` lines 310–334, NumPy `method="linear"` | `deferred_or_not_applicable` | Do not import as the Tier 1 median, IQR, or bootstrap percentile. |
| `scripts/analyse_repo_aptamer_eval_results.py` | `13edfc6a6017729633f814d6af7b9f6e6f08b209` | `ab0f4511e2479dc3af0d63f00520b46c0d845129f4902b4497a5eb61f72aa6fc` | yes | Lines 458–459 and 481–482: repository evaluation does not compute normalised MFE or ensemble defect | `not_implemented_in_local_code` | Do not treat that script as an AptaRank scorer. |
| `config/method_freeze.json` | absent | `76467e97bcf4d17c017f894bd6f8e1e314ece8eefbeaed95fc768bf32cbd41b5` | not in this worktree; hash not recomputed | Reviewer-supplied historical freeze | `provisional_historical_evidence` | Do not import. |
| `analyse_tier1_biological_run.py` | absent | `31bc9c1b94651f61a6c75a3f964dcdf81c8dad642f16fafa593d15d88230c1e9` | not in this worktree; hash not recomputed | Reviewer-supplied historical analysis | `provisional_historical_evidence` | Do not import. |
| `tests/test_tier1_biological_run.py` | absent | `e899683340336c46a3dfbe0181a5239c329da7eb7051c5f325a0a71c1355221d` | not in this worktree; hash not recomputed | Reviewer-supplied historical test | `provisional_historical_evidence` | Do not import. |
| `tests/test_tier1_biological_freeze.py` | absent | `cb5982aa3c01251d26a8b9a40af09eb258e61773010b6eeae679a4946661a6c9` | not in this worktree; hash not recomputed | Reviewer-supplied historical test | `provisional_historical_evidence` | Do not import. |

The spec pins the governing-plan SHA-256 as `e6193d0d14245049c218b4da0ef8059fb63b2f31e4885b3457cd44e41b76c50c`. The worktree plan matches that pin.

### Comparison of the provisional method notes with tracked sources

| Provisional observation | Tracked position | Classification left in force |
|---|---|---|
| Composite `sum(w_i * s_i) / sum(w_i)` | The plan says "established weighted mean" and does not write this quotient. No local function implements it. The 25 September narrative says "equally weighted mean". | `provisional_historical_evidence` and `not_implemented_in_local_code` |
| Five weights equal to 1 | The plan says weights are frozen. It does not record the numbers. | `provisional_historical_evidence` and `requires_prespecified_method_decision` |
| Lower favoured: normalized MFE, ensemble defect, positional entropy | Plan §6.1 names those three directions. | `governing_plan_fixed` for the direction. The equations remain absent. |
| Two-sided centrality for stem fraction and GC fraction | Plan §6.1. Stem fraction's parenthesis includes "around the REF median". GC fraction's parenthesis is "two-sided centrality" and does not restate the reference point. | Stem reference point is `governing_plan_fixed`. GC reference point stays `provisional_historical_evidence`. |
| Empirical CDF `(# REF values < x + 0.5 × # REF values equal to x) / m` | Not in the plan and not in code. The plan says to keep the established CDF and tie handling. | `provisional_historical_evidence`. The algebra is `requires_prespecified_method_decision`. |
| Shuffle p-value `(1 + # shuffle structural subscores ≥ candidate) / (M + 1)` | Not in the plan and not in code. | `provisional_historical_evidence` |
| Pass at `p ≤ 0.05` | Plan §6.2 writes this rule. | `governing_plan_fixed` as the analysis rule. Binding an export token to it is still a UI question. |
| Shuffle uses normalized MFE, ensemble defect, positional entropy, and stem fraction | The plan says "shuffle criterion" without the component list. GC is absent from the provisional list. | `provisional_historical_evidence` |
| Two-sided Wilcoxon signed-rank, `zero_method=wilcox`, approximate inference, average ranks for tied absolute differences, no continuity correction | The plan requires one secondary paired test with predeclared tie and zero handling. It does not name the test. No local function implements Wilcoxon. | `provisional_historical_evidence` and `requires_prespecified_method_decision` |
| Higher aptamer-likeness is favourable and scores lie in `[0, 1]` | ARP-1 accepts any finite decimal and applies no direction and no range. The bundled synthetic shortlist contains `-3.5`. | `provisional_historical_evidence` for the historical checker. Live range and direction are `requires_live_synthetic_ui_verification`. |

No historical VALIDATION performance value and no camera-ready outcome was used to accept or reject any row above.

## 2. Responsibility boundary

| Operation | Owner | What is already fixed | ARP-2 relationship |
|---|---|---|---|
| Five component calculations, REF empirical calibration inside the scorer, composite aptamer-likeness, shuffle draws, and the label or p-value the deployment emits | Deployed AptaRank UI | Plan §7: Laura operates the UI. No local stage calls an API, starts a job, or changes deployment settings. | Validate downloaded output. Do not reimplement the scorer. |
| Candidate-upload and REF-upload files, column contract, opaque ids on the upload | Upload preparation | ARP-1 draft columns `id`, `sequence` for candidates and the five reference columns. Plan: upload the blinded candidates with the frozen REF, without a protein target. | Prepare files later. ARP-1 may validate synthetic files now. |
| Opaque-id randomization and the private key | Private-key construction | Plan §6.1 names the key contents and forbids recovery of labels by row position. The randomization seed and id format are open. | Blocked until those two decisions exist. |
| Header, id set, sequence round-trip, length, finite score token, profile tokens, failure reason, hashes | Export validation | ARP-1 draft, `deployment_verified` false. A header difference fails closed. | Import ARP-1 for the draft. A live file that differs needs a reviewed schema revision before analysis. |
| Median, IQR, mean, paired difference, AUROC, shuffle-pass counts, the secondary paired test, cluster intervals | Local statistical analysis | Plan §6.2 names the estimands. Several algebraic conventions are open. | Implement only the fixed estimands, and only after the open conventions in the register are prespecified. |
| Build the calibration from 113 unique corrected REF cores and record the effective preset | M9B | Plan §4.2 and §6.1. Calibration is not a REF performance result. | Do not fit a local substitute CDF in ARP-2B. |
| Freeze questions, metrics, the control algorithm, tie and failure handling, and code hashes before EVAL access | M9C | Plan §4.2. EVAL does not choose equations, weights, thresholds, or metrics. | ARP-2A does not freeze the open register. |
| Run the blinded EVAL Tier 1 upload and the local summaries on real cores | Post-unlock EVAL execution | Plan M10. One frozen analysis after unlock. | Out of scope for ARP-2A and for any pre-unlock test. |

Local reproducibility of the UI's numeric score requires the missing scoring source or a component-level export that this repository does not define. Until one of those exists, local code can check the download contract and can compute summaries from the exported composite and shuffle field. It cannot audit the component arithmetic.

## 3. Five Tier 1 components

The plan's five names and favour directions are `governing_plan_fixed`. Every equation, unit, software setting, and missing-value rule inside the scorer is `not_implemented_in_local_code`.

Generator quantities in the right-hand column are verified local implementations of different metrics.

| Component | Plan name and favour direction | Input, equation, normalization, units, range | Missing or failure handling | Length handling | Unresolved |
|---|---|---|---|---|---|
| Normalized MFE | `normalized MFE`, lower favoured. Source: plan §6.1. | No AptaRank symbol, equation, or unit is in the repository. | Absent with the scorer. An unscored candidate is a technical failure in the export contract, and the missing composite is not stored as zero. | The plan does not define an internal length normalization for this component. | Equation, temperature, folding package, and whether the divisor is length. |
| Ensemble defect | `ensemble defect`, lower favoured. | No local symbol or equation. `scripts/analyse_repo_aptamer_eval_results.py` states that the repository evaluation procedure does not compute ensemble defect. | Same export rule for a missing composite. Component-level failure policy is absent. | Unresolved. | Definition, including whether it is the ViennaRNA ensemble defect and over which ensemble. |
| Positional entropy | `positional entropy`, lower favoured. | No local symbol or equation. | Same. | Unresolved. | The 25 September narrative says "mean positional entropy". The plan does not say "mean". That qualifier is provisional. |
| Stem fraction | `stem fraction`, two-sided centrality around the REF median. | No local symbol or equation. | Same. | Unresolved. The S6 short/long regime is not a component formula, and the plan forbids inventing a nucleotide cutoff. | Algebra of "stem", and the centrality transform in §4. |
| GC fraction | `GC fraction`, two-sided centrality. | No AptaRank per-sequence function. | Same. | Exact-length controls match the parent. That does not define this component. | The reference point is not restated in the plan parenthesis. Provisional notes place it at the REF median. Equation is open. Per-candidate scope follows from its role as a score component. |

### Generator metrics that stay separate

| Local symbol | Verified definition | Why it stays separate |
|---|---|---|
| `m6_diagnostic_generation.structure_features` key `mfe_per_nt` | `float(mfe) / len(sequence)` from a caller-supplied fold. Spec direction `not_applicable`. | Plan §6.1 normalized MFE is the AptaRank component. GEP-2A and the generator spec already say `mfe_per_nt` is the generator metric. |
| `structure_features` key `mfe` | Fold-returned float, not divided by length. | A raw fold energy is not the AptaRank component. |
| `structure_features` key `paired_fraction` | `(count("(") + count(")")) / len(sequence)`. | This is a parenthesis count. It is not stem fraction, and it has no REF-median centrality. |
| `generator_eval_analysis.pooled_gc_fraction` | `(count_G + count_C) / total canonical bases` on a pool of valid rows, duplicates retained, direction `not_applicable`. | This is a pool descriptor. It is not the per-candidate AptaRank GC component and it has no two-sided transform. |
| `m6_diagnostic_generation._quantiles` | Index `int(round(p * (n - 1)))` on ascending values. Keys `count`, `minimum`, `p25`, `median`, `p75`, `maximum`, `mean`. | Generator summary convention. It is not adopted here as the Tier 1 IQR or the bootstrap percentile. |
| `s6_profile.percentile_bundle` | NumPy percentile, `method="linear"`. An empty input returns zeros. | Corpus-profile convention. Empty-input zeros would also violate the Tier 1 rule that missing results are not zeros. |

`generator_eval_analysis` sets `aptarank_normalized_mfe` to false on every structure block it builds. GEP-1 does not call ViennaRNA. Those facts confirm a boundary. They do not describe the AptaRank fold.

## 4. REF calibration and the composite

REF has 113 unique corrected cores, 65 short and 48 long, in plan §3 and §6.1. That count is the calibration unit. A REF score, a REF shuffle-pass rate, or any other REF outcome is not a performance result. The curation plan v1.6 assigns REF to fitting Tier 1 reference distributions only. The same plan's phrase "length-conditioned Tier 1 reference distributions" records a design concern about mixed length regimes. It does not choose whether the CDF is pooled across 113 cores or fit separately inside the frozen short and long regimes. That choice remains `requires_prespecified_method_decision` (`U1`).

| Item | Statement | Classification |
|---|---|---|
| REF unit | 113 unique corrected REF cores. | `governing_plan_fixed` |
| Short and long counts | 65 short and 48 long, under the frozen S6 assignment. No nucleotide cutoff is invented. | `governing_plan_fixed` as corpus facts. They do not by themselves stratify the CDF. |
| Pooled or length-stratified calibration | Not written as a choice. | `requires_prespecified_method_decision` (`U1`) |
| Empirical CDF | Plan: keep the established CDF and tie handling. Algebra absent. Provisional mid-rank formula: `(# REF values < x + 0.5 × # REF values equal to x) / m`. | Formula is `provisional_historical_evidence`. Adoption is `requires_prespecified_method_decision` (`U2`). |
| Lower-is-better transform | Directions are fixed. The map from a raw value into the CDF argument is not written. A decreasing transform, an upper-tail CDF, and a reflected percentile are different maps. | `requires_prespecified_method_decision` (`U3`) |
| Two-sided centrality | Stem fraction is centred on the REF median. The algebra, including the distance and the subsequent CDF, is not written. GC fraction is two-sided; its centre is the provisional REF median and is not restated by the plan. | Stem centre: `governing_plan_fixed`. Algebra and GC centre: `U4`, `U5`. |
| Values beyond the REF range | Not written. The provisional CDF maps a value below every REF point to 0 and a value above every REF point to 1, with no separate winsorization step. That behaviour is not adopted. | `provisional_historical_evidence` (`U6`) |
| Component weights | Frozen before EVAL. Numeric weights are not in the plan or the code. Provisional notes record five weights equal to 1. The 25 September narrative says equally weighted. | Values: `provisional_historical_evidence` and `U7`. The prohibition on EVAL-tuned weights is `governing_plan_fixed`. |
| Weighted-mean denominator | Provisional notes describe `sum(w_i * s_i) / sum(w_i)`. | `provisional_historical_evidence` and `U7` |
| Missing component | Not written. A missing export cell is not zero. Whether a missing component drops out of the denominator is a scorer policy this repository does not contain. | `requires_prespecified_method_decision` (`U8`), and `not_implemented_in_local_code` |
| Score range | Provisional historical checking expected `[0, 1]`. ARP-1's type is `finite_decimal`. The synthetic passing fixture includes `-3.5`. | Live range: `requires_live_synthetic_ui_verification` (`U9`) |
| Rounding versus full precision | Not written. ARP-1 preserves the decimal token long enough to test finiteness and does not round it. | Display precision is a UI question (`U9`). Analysis precision stays unresolved with it. |
| Who computes the score | The UI computes it. Local code verifies the exported token and then analyses it. | `governing_plan_fixed` for the thesis path. Local recomputation is blocked because the source is absent. |

The provisional composite is a weighted mean of already transformed component scores. This audit does not identify those transformed scores with the raw structural measurements.

## 5. Shuffle criterion

| Item | Statement | Classification |
|---|---|---|
| Analysis pass rule | `p ≤ 0.05`. | `governing_plan_fixed` |
| Export tokens | ARP-1 profile `target_free_rigorous_style` accepts `pass` and `fail` only. `shuffle_meaning` is `unresolved`. `shuffle_threshold` is null. | `authoritative_implementation_verified` for the draft. The tokens are not yet the p-value rule. |
| Binding `pass` to `p ≤ 0.05` | The plan tells the analyst to use the p-value rule. The draft interface refuses to assign that threshold to the token. | `requires_live_synthetic_ui_verification` (`U19`) |
| Structural components inside the shuffle | Provisional list: normalized MFE, ensemble defect, positional entropy, stem fraction. GC is not in that list. The plan does not list the set. | `provisional_historical_evidence` (`U12`) |
| Structural-subscore equation | Absent. | `not_implemented_in_local_code` and `U13` |
| Preset | Plan §7: historically 200 sampled structures and 99 shuffles, to be verified. The 25 September narrative also says 99 shuffles. ARP-1 `preset_value` is null. | `provisional_historical_evidence` and `requires_live_synthetic_ui_verification` (`U14`) |
| Seed for the shuffle stream | Plan §6.1 says keep the established seed. The number is not in the plan or the code. Master seed 42 belongs to the uniform-control generator, not automatically to the shuffle stream. | `requires_prespecified_method_decision` (`U15`) and UI verification of the effective preset |
| Dinucleotide-preserving algorithm | Named by the plan as the stronger null. The algorithm, including the exact preservation statistic and the implementation, is absent. | Name: `governing_plan_fixed`. Algorithm: `U16` |
| Comparison direction | Provisional p-value counts shuffle subscores that are greater than or equal to the candidate subscore. The plan does not say whether the favourable structural subscore is low or high. | `provisional_historical_evidence` (`U17`) |
| Inclusive or exclusive count | The provisional count is inclusive (`>=`). | `provisional_historical_evidence` (`U17`) |
| Plus-one correction | Provisional formula `(1 + count) / (M + 1)`. | `provisional_historical_evidence` (`U18`) |
| Failed shuffles | Not written. A failed candidate export is a technical failure, not a shuffle fail. | `U20` |
| What the export contains | The provisional shortlist carried labels. ARP-1 therefore has a label slot and no p-value column. A full export might differ. | `requires_live_synthetic_ui_verification` (`U21`) |

ARP-2 may count `pass` and `fail` only after `U19` and `U21` are closed by a synthetic UI record. It must not recompute shuffles.

## 6. Exact-length uniform controls

This is the future algorithm's contract. It does not generate controls, and it does not read EVAL lengths.

| Step | Contract | Classification |
|---|---|---|
| Parents | After unlock, one control for each of the 154 unique EVAL cores. | `governing_plan_fixed`. Execution is post-unlock. |
| Length | The control length equals the parent core length. | `governing_plan_fixed` |
| Alphabet and probabilities | Uniform A/C/G/U, so each letter has probability 1/4 on each draw. | `governing_plan_fixed` |
| Master seed | 42. | `governing_plan_fixed` |
| RNG and letter order | The plan requires a deterministic generator and deterministic resampling. It does not name the generator, the bit width, or the index order of A, C, G, and U. | `requires_prespecified_method_decision` (`U22`). This audit does not choose `random.Random`, NumPy, or any other generator. |
| One control per parent | Yes. | `governing_plan_fixed` |
| Duplicates | Resample when a draw matches another generated control. | `governing_plan_fixed` as "duplicate" resampling |
| Known-core collisions | Resample on a known-core match. | The duty to resample is `governing_plan_fixed`. Which roles are "known" is `U23`. |
| Digest inventory | Collision checks need a sequence-free inventory: one digest per known core, plus length and role, with no sequence column. The digest function is not specified. | `U23` |
| Other controls | A later draw that copies an earlier control is a duplicate and is resampled. | `governing_plan_fixed` |
| Resampling order | Deterministic. The successor rule, including whether the next draw continues one stream or uses an attempt index, is not written. | `U24` |
| Attempt cap | Not written. On exhaustion the run fails closed. The cap itself is not chosen here. | `U24` |
| Scientific role | Synthetic floor. See the proof below. | `governing_plan_fixed` |

### Sequence-free inventory

The inventory required before a control can be accepted is a table of digests, not a table of sequences. Each row needs the digest of one canonical A/C/G/U core, the core length, and the corpus role. The generator compares a digest of the proposed control with that table and with the digests of controls already accepted.

This audit does not build that table. Building the EVAL portion requires the EVAL cores. Building the TRAIN, VALIDATION, or REF portions would open those role files. Both are outside this package.

`U23` still has to name the digest function and the role membership. A defensible membership is every corrected primary core whose identity would make the control a copy of a real aptamer core. That sentence is the open decision, not an adopted rule.

### Impossible before EVAL unlock

The following cannot be done before the formal unlock, because each one needs protected EVAL content:

- the 154 parent lengths;
- digests of the 154 EVAL cores;
- the 308-row candidate upload;
- cluster identifiers for those cores;
- any check that a control collided with an EVAL core.

The written contract above can be frozen at M9C. The draws cannot be made.

### Synthetic floor

A uniform control is an i.i.d. exact-length string from the uniform distribution on `{A, C, G, U}`. It is not a sequence that was tested in a binding assay and found not to bind. Plan §§1 and 6.1 assign it the interpretation "synthetic floor". Candidate-specific dinucleotide-preserving shuffles are the stronger composition-preserving null. A Tier 1 comparison with the uniform control does not show that the control is an experimental non-binder, and it does not show that a real core binds its protein.

## 7. Blinding and joins

| Item | Contract | Classification |
|---|---|---|
| Upload size before technical rejection | 308 rows: 154 real cores and 154 controls. | `governing_plan_fixed` |
| Opaque id syntax accepted by ARP-1 | A nonempty string with no whitespace (`ID_TEXT`). The upload id is copied into the export `candidate` column. | `authoritative_implementation_verified` as validator syntax |
| Opaque id format for the thesis upload | Not frozen. ARP-1's syntax is the draft acceptor, not the randomization format. | `requires_prespecified_method_decision` (`U25`) |
| Randomization | The plan says to randomize opaque ids. | Duty: `governing_plan_fixed`. Seed and algorithm: `U26`. The seed is not chosen here and is not taken from any result. |
| Private-key fields named by the plan | Real versus control, pair, parent core, cluster, and length. | `governing_plan_fixed` |
| Private-key join field | The opaque candidate id. The plan's join rule requires it on the key. | `governing_plan_fixed` as a consequence of the join |
| Pair identity | The real core and its one exact-length control share one pair id. | `governing_plan_fixed` |
| Parent core and cluster | Taken from the corrected EVAL release after unlock, and stored in the private key. | `governing_plan_fixed` for the contents. Execution is post-unlock. |
| Exact length | Control length equals parent length. Exported `len` equals the uploaded sequence length and the exported sequence length. | Parent match: `governing_plan_fixed`. Export match: `authoritative_implementation_verified` in ARP-1. |
| Join | By candidate id. `JOIN_USES_ROW_POSITION` is false. | `governing_plan_fixed` and `authoritative_implementation_verified` |
| Duplicates, missing rows, extra rows | ARP-1 rejects them. | `authoritative_implementation_verified` |
| Technical failure | One explicit failure record with a nonempty reason. The row is not dropped and is not stored as zero. | `governing_plan_fixed` and `authoritative_implementation_verified` |
| Sequence-bearing artefacts | Candidate upload, reference upload, and any export that retains `sequence`. The private key is restricted because it restores parent-core identity. The ARP-1 shortlist schema includes `sequence`, so that download is sequence-bearing. | `governing_plan_fixed` for the upload and the key's sensitivity. Export sequence column: draft schema. |
| Sequence-free artefacts | Expected opaque-id lists, file hashes, row-count manifests, aggregate summaries, and the digest inventory. ARP-1 failure records are `candidate_id` and `reason` only. | `authoritative_implementation_verified` for the ARP-1 failure shape. Aggregate tables are the intended analysis output. |

The blinded upload carries `id` and `sequence` only. It does not carry the real/control label, the pair id, the cluster id, or a target.

## 8. Tier 1 export validation

ARP-1 defines one download schema, `shortlist_export`. No tracked file defines a separate full-ranking export. Reconciling the two schemas is `requires_live_synthetic_ui_verification` (`U27`). ARP-1 is unchanged by this audit.

Draft shortlist columns, in order:

`rank`, `candidate`, `aptamer-likeness`, `compatibility`, `shuffle`, `len`, `sequence`.

| Check | What ARP-1 verifies | What remains pending |
|---|---|---|
| Column names and order | Exact match to the draft. A renamed, reordered, missing, or extra column fails closed. One leading UTF-8 BOM is stripped only for decoding. | Whether the live full ranking uses these columns. |
| Score type | Finite decimal. Non-finite tokens are rejected. No range and no direction are applied. | Live range and direction (`U9`, `U29`). Historical `[0, 1]` and higher-is-better stay provisional. |
| Rank type | Positive integer. Duplicate ranks are rejected (`duplicate_rank`). | Consecutive ranks `1..N` are not checked. Rank ties and monotonic score order are not checked (`U28`). |
| Candidate id | Nonempty, unique among exported rows, joined to the upload, and equal to the expected set once failures are included. | Live preservation under the real UI. |
| Sequence and length | Character-for-character sequence match and integer length match, by id. | Silent UI conversions must be checked in the synthetic preflight. |
| Compatibility | Token `not evaluated` under `target_free_rigorous_style` only. The literal is not interpreted. | Live target-free behaviour. |
| Shuffle | Tokens `pass` and `fail` for that profile only. Threshold null. | `U19`, `U21`. |
| Technical failure | Explicit reason. Missing is not zero. | The live failure-file shape, if it differs from the draft. |
| UI provenance | The spec lists run id, operator, timestamps, deployment version, schema version, code revision, preset, effective settings, hashes, and row counts. The bundled synthetic provenance leaves deployment fields null and `deployment_verified` false. | A new synthetic UI preflight must fill them. This package does not. |
| Shortlist versus full export | Not defined. The 308-row analysis needs every evaluable row. A shortlist that omits rows would not be that analysis. | `U27` |

The synthetic fixture's second likeness value is `-3.5`. That shows the draft validator's acceptance set. It is not a biological score and it is not evidence that the UI emits negative scores.

Plan §9's later top-L rule, tie-broken by ascending opaque candidate id, is a generated-candidate selection rule. It is not a definition of how the UI assigns `rank`, and ARP-2A does not implement top-L.

## 9. Required Tier 1 analysis

Denominators required by plan §6.2:

| Denominator | Definition used here | Classification |
|---|---|---|
| Input | The 308-row blinded upload before technical rejection, accounted after the download as expected ids. | `governing_plan_fixed` |
| Evaluable | Exported rows that pass the frozen export contract for the statistic being computed. | The reporting duty is fixed. The per-statistic predicate is in the table below. |
| Excluded | Expected ids with an explicit technical failure, plus incomplete pairs where the statistic requires a complete pair. Exclusions are reported. They are not imputed as zero. | `governing_plan_fixed` |
| Cluster count before rejection | 79 corrected EVAL clusters, reported before technical rejection. | `governing_plan_fixed` |

| Estimand | Definition | Classification |
|---|---|---|
| Group median, IQR, and mean of the exported Tier 1 score | Separate real and uniform-control summaries on the evaluable rows of that group. | Summaries: `governing_plan_fixed`. Quantile convention: `U30`. |
| IQR | Upper quartile minus lower quartile, once `U30` names those quartiles. | `U30` |
| Paired difference | Real minus control on the exported score, for complete pairs. | The contrast direction is `governing_plan_fixed`. Which functional of the paired differences is the reported effect (mean, median, or both) is `U31`. |
| Confidence intervals on paired effects | Plan §6.2 asks for 95% intervals on paired effects. | The duty is fixed. The functional is `U31`. |
| AUROC | Descriptive discrimination of unique EVAL cores from their paired uniform controls. The positive class is the real EVAL core and the negative class is its uniform control, because the plan's question is whether Tier 1 distinguishes those cores from that null. The exported score is used as exported. A result below 0.5 stays visible. | Class labels and the descriptive role: `governing_plan_fixed`. Tie handling: `U32`. Live score direction: `U29`. |
| AUROC scope | This AUROC is against the uniform synthetic floor on this paired upload. It is not universal aptamer classification. | `governing_plan_fixed` |
| Shuffle-pass `n/N` and rate | By group, under the frozen `p ≤ 0.05` rule once the export is bound to that rule. | Rule: `governing_plan_fixed`. Token binding: `U19`. Denominator (all scored group rows, or complete pairs only): `U33`. |
| Paired shuffle-pass difference | Plan §6.2 includes the shuffle-pass rate difference among the interval targets. | The difference is required. Its pairing and denominator are `U33`. |
| Secondary paired test | One test, with tie and zero handling declared before EVAL. | Existence: `governing_plan_fixed`. Name, alternative, zero method, tie method, exact or approximate inference, and continuity correction: `U34`. The historical Wilcoxon specification is not adopted. |
| Incomplete pairs | Paired effects and AUROC use complete pairs. A pair is incomplete when either member is missing, duplicated, or a technical failure. | `governing_plan_fixed` |
| Undefined results | A statistic that lacks the pairs or the classes it needs is undefined and is reported as undefined. It is not filled with zero, with 0.5, or with a skipped replicate that is later treated as a number. | Principle: `governing_plan_fixed`. Numeric minimums that depend on `U34` stay inside `U34` and `U38`. |
| Five-component table | A compact descriptive table is enough. The plan does not require component-wise confidence intervals. | `governing_plan_fixed` as a reporting limit. Component columns exist only if the export or a recovered scorer provides them. The current shortlist schema has the composite only. |

Generator `_quantiles` and corpus `percentile_bundle` are both implemented and they disagree with each other. Neither is selected as `U30`.

## 10. Cluster-aware bootstrap

The plan's procedure is an uncertainty method for the Tier 1 estimands. GEP-2A recorded that the generator package does not implement it and must not copy it. This audit also does not implement it and does not run it on EVAL.

Fixed inputs:

- Resampling unit: the EVAL sequence cluster. Plan §3.3 preserves the cluster and its paired control. Plan §6.2 resamples clusters with their paired controls.
- Cores that share a cluster stay in that cluster's resampled block. Their controls stay with them.
- 10,000 replicates.
- Seed 42.
- Percentile intervals.
- Nominal level 95%.
- The reported cluster total before technical rejection is 79.
- Complete pairs enter the paired estimands and AUROC.

The following lines are intentionally unresolved. Writing a pseudocode loop would choose them.

| Step | Status | Register |
|---|---|---|
| Draw clusters with replacement | Not stated. "Resample" does not record the with-replacement rule. | `U35` |
| Keep the multiplicity of a cluster drawn more than once | Not stated. | `U35` |
| Weight of the statistic when one cluster contains more than one core | The observation grain is the unique core. The dependence grain is the cluster. Equal weight per core inside the resampled multiset, and equal weight per cluster, are different estimands. | `U35` |
| Generator that consumes seed 42 | Not stated. This seed is the bootstrap seed in §6.2. It is also the uniform-control master seed. The two streams still need separate prespecified generators so one draw does not advance the other. | `U22` and `U35` |
| Percentile endpoint convention | "Percentile intervals" does not choose an order-statistic rule or a NumPy method. | `U36` |
| Replicates in which AUROC, a rate, or the paired functional is undefined | Not stated. Dropping them, failing the run, and imputing a value are different methods. Imputation as zero is already forbidden. | `U37` |
| Interval targets | Paired effects, AUROC, group shuffle-pass rates, and the shuffle-pass difference. | Targets: `governing_plan_fixed`. Their formulas wait on `U31`, `U32`, and `U33`. |
| Interval for the secondary test | Not requested as a separate interval. | Do not add one unless a later decision says so. |

Point estimates are computed on the original complete pairs. Each bootstrap replicate recomputes the same prespecified functional on the resampled clusters. The interval is the prespecified percentile interval of the defined replicate values. That paragraph is the plan's shape. It becomes code only after `U35`, `U36`, and `U37` are filled in.

## 11. Scientific boundaries

These limits stay in force for any later ARP-2 code and for the thesis text:

- Uniform RNA is a synthetic floor.
- Candidate-specific dinucleotide-preserving shuffles are the stronger composition-preserving null.
- Tier 1 is target-free. The EVAL Tier 1 upload has no protein target.
- Tier 1 does not establish binding, affinity, selectivity, therapeutic activity, or universal aptamer classification.
- Mixed, weak, and null findings remain visible. A low shuffle-pass rate and a weak separation are reported as found.
- A technical failure is incomplete. It is not recoded as a null biological result and it is not stored as zero.
- There is no combined Tier 1 and Tier 2 score.
- Canonical A/C/G/U cores do not represent modified chemistry.
- REF calibration is not a performance evaluation.
- EVAL does not choose the formula, the weights, the threshold, the preset, the target, or the interpretation.

## 12. Unresolved-decision register

Items in this register are blocked. ARP-2A does not close them.

| ID | Decision still required | Why it is blocked | Label |
|---|---|---|---|
| `U1` | Pooled CDF on 113 cores, or a CDF inside each frozen length regime | Counts are fixed. The grain is not. | `requires_prespecified_method_decision` |
| `U2` | Empirical-CDF formula and mid-rank tie rule | Provisional mid-rank formula is not in the plan or the code. | `provisional_historical_evidence` |
| `U3` | Transform that implements "lower favoured" | Direction is fixed. The map is not. | `requires_prespecified_method_decision` |
| `U4` | Two-sided centrality algebra | Centre for stem fraction is the REF median. The distance and CDF are not written. | `requires_prespecified_method_decision` |
| `U5` | GC centrality reference point | Plan parenthesis does not restate the REF median. | `provisional_historical_evidence` |
| `U6` | Values outside the REF sample | Provisional CDF endpoints are not adopted. | `provisional_historical_evidence` |
| `U7` | Numeric weights and the weighted-mean denominator | Provisional weights are 1 and the provisional mean divides by `sum(w_i)`. | `provisional_historical_evidence` |
| `U8` | Missing-component policy inside the composite | No scorer source. | `not_implemented_in_local_code` |
| `U9` | Exported score range, direction, and rounding | Historical `[0, 1]` and higher-is-better are provisional. ARP-1 accepts `-3.5`. | `requires_live_synthetic_ui_verification` |
| `U10` | Whether positional entropy is a mean | Only the older narrative says "mean". | `provisional_historical_evidence` |
| `U11` | Component equations and folding settings | Scoring source absent. | `not_implemented_in_local_code` |
| `U12` | Structural components in the shuffle subscore | Provisional four-component list. | `provisional_historical_evidence` |
| `U13` | Structural-subscore equation | Absent. | `not_implemented_in_local_code` |
| `U14` | Effective preset, including structure-sample count and shuffle count `M` | Historical 200 / 99 must be verified. | `requires_live_synthetic_ui_verification` |
| `U15` | Shuffle seed and stream | "Established seed" is not recorded. | `requires_prespecified_method_decision` |
| `U16` | Dinucleotide-preserving algorithm | Named, not specified. | `requires_prespecified_method_decision` |
| `U17` | Shuffle comparison direction and inclusive count | Provisional `>=` rule. | `provisional_historical_evidence` |
| `U18` | Plus-one p-value correction | Provisional `(1 + count) / (M + 1)`. | `provisional_historical_evidence` |
| `U19` | Equivalence of export `pass` and `p ≤ 0.05` | ARP-1 leaves the token uninterpreted. | `requires_live_synthetic_ui_verification` |
| `U20` | Failed-shuffle handling inside the UI | Separate from an export technical failure. | `requires_live_synthetic_ui_verification` |
| `U21` | Export carries p-values, labels, or both | Draft schema has a label column only. | `requires_live_synthetic_ui_verification` |
| `U22` | Uniform-control RNG and nucleotide index order | Seed 42 and probability 1/4 are fixed. The generator is not. | `requires_prespecified_method_decision` |
| `U23` | Known-core role membership and digest function | Resampling is required. The inventory specification is not. | `requires_prespecified_method_decision` |
| `U24` | Resampling successor rule, attempt cap, and fail-closed stop | Determinism is required. The cap is not chosen. | `requires_prespecified_method_decision` |
| `U25` | Opaque candidate-id format | Validator syntax is not the format. | `requires_prespecified_method_decision` |
| `U26` | Opaque-id randomization seed and algorithm | Not frozen. Not chosen from results. | `requires_prespecified_method_decision` |
| `U27` | Full-ranking export schema versus the ARP-1 shortlist | No full-ranking schema is tracked. | `requires_live_synthetic_ui_verification` |
| `U28` | Consecutive ranks, rank ties, and monotonic score order | ARP-1 rejects duplicate ranks and does not check the rest. | `requires_live_synthetic_ui_verification` |
| `U29` | Live favourable direction of aptamer-likeness | Needed before AUROC is interpreted. The positive class is already the real core. | `requires_live_synthetic_ui_verification` |
| `U30` | Median and IQR quantile convention | Two different local conventions exist and neither is selected. | `requires_prespecified_method_decision` |
| `U31` | Which paired functional receives the confidence interval | Mean and median are both requested as summaries. | `requires_prespecified_method_decision` |
| `U32` | AUROC tie handling | Absent. | `requires_prespecified_method_decision` |
| `U33` | Shuffle-rate denominator and the paired pass difference | Group `n/N` and the paired difference can use different row sets. | `requires_prespecified_method_decision` |
| `U34` | Secondary paired test: name, alternative, zeros, ties, exact or approximate method, continuity correction | Historical Wilcoxon details stay provisional. | `requires_prespecified_method_decision` |
| `U35` | Bootstrap replacement, multiplicity, and core-versus-cluster weighting | Unit, pair blocking, replicate count, and seed are fixed. | `requires_prespecified_method_decision` |
| `U36` | Percentile-interval endpoint convention | "Percentile" is fixed. The order-statistic rule is not. | `requires_prespecified_method_decision` |
| `U37` | Undefined bootstrap replicates | Must not be imputed as zero. The remaining policy is open. | `requires_prespecified_method_decision` |
| `U38` | Minimum evaluable counts for a defined result | The undefined-result principle is fixed. Thresholds that depend on the test are not. | `requires_prespecified_method_decision` |

## 13. Facts ARP-2 code may safely implement

ARP-2B may encode the following without waiting for the register. Each item is either written in the version 3.0 plan or verified in tracked code on this HEAD.

1. The UI remains the scorer. Local code does not recompute the five components, the composite, or the shuffles.
2. Local code prepares uploads and a private key, validates downloads, joins by candidate id, and computes summaries from exported fields.
3. The REF calibration set is the 113 unique corrected REF cores. REF output is not a performance result.
4. The five component names and the favour directions in §3, including stem fraction centred on the REF median.
5. Generator `mfe_per_nt`, `paired_fraction`, and `pooled_gc_fraction` are excluded from the AptaRank component identities.
6. The analysis pass threshold is `p ≤ 0.05`, used only after `U19` binds the export. The threshold itself is not retuned on EVAL.
7. One uniform A/C/G/U control per parent, exact parent length, master seed 42, letter probability 1/4, duplicate resampling, and fail-closed behaviour once `U22`–`U24` exist. The control is a synthetic floor.
8. The pre-rejection upload has 308 rows. The private key holds real/control, pair, parent core, cluster, length, and the opaque id.
9. Joins use candidate id. Duplicate, missing, and extra ids fail closed. A missing score is a technical failure and is not zero.
10. Reports state input, evaluable, and excluded counts, and state the 79 EVAL clusters before technical rejection.
11. Reports give real and control median, IQR, and mean once `U30` is prespecified; the paired real-minus-control contrast; descriptive AUROC with the real core as the positive class; and shuffle-pass `n/N` once `U19` and `U33` are closed.
12. Paired effects and AUROC use complete pairs.
13. Uncertainty uses cluster resampling, paired controls kept with the cluster, 10,000 replicates, seed 42, and percentile intervals, once `U35`–`U37` are prespecified.
14. ARP-1 draft mechanical checks may be imported for synthetic files. `deployment_verified` stays false until a new synthetic UI preflight.
15. The claim boundaries in §11, including the absence of a combined Tier 1 and Tier 2 score.

Implementing item 7, item 11, or item 13 still waits on the register ids named inside that item. The surrounding contract is what may be coded now as guards and interfaces.

## 14. Items that stay blocked

ARP-2B must not implement, silently default, or test against biological data for any of the following.

- `U1`–`U11`: calibration grain, CDF, transforms, weights, missing components, score range, and component equations. The scoring source is absent. Do not invent a ViennaRNA call.
- `U12`–`U21`: shuffle subscore, preset, seed, algorithm, p-value formula, and the meaning of the export label. Do not treat `pass` as `p ≤ 0.05` yet. Do not adopt the provisional plus-one formula yet.
- `U22`–`U26`: uniform RNG, digest inventory, attempt cap, opaque-id format, and opaque-id seed. Do not generate EVAL controls. Do not read EVAL lengths.
- `U27`–`U29`: full-export schema, rank conventions, and live score direction. Do not change ARP-1 to accept a different header.
- `U30`–`U38`: quantile convention, paired functional, AUROC ties, shuffle denominator, the secondary test, and the bootstrap details that the plan left unspecified. Do not import `_quantiles` or `percentile_bundle` to fill these gaps. Do not adopt the historical Wilcoxon call.
- Any use of VALIDATION camera-ready outcomes, REF performance, or EVAL scores to choose a formula, weight, threshold, preset, target, or interpretation.
- Local recomputation of aptamer-likeness as a check on the UI, until a reviewed source for that recomputation exists.

## 15. Proposed ARP-2B file and test plan

No ARP-2B file is added by this package. The later package should add code only for the safe list, with the register represented as explicit unresolved guards rather than as hidden defaults.

| Proposed path | Role |
|---|---|
| `scripts/modelling/aptarank_tier1_analysis.py` | Join exported synthetic rows to a synthetic private key, apply the fixed exclusion rules, and compute the estimands whose register ids have been closed. Refuse a request to recompute components. |
| `scripts/modelling/aptarank_tier1_controls.py` | Deterministic uniform controls on caller-supplied synthetic lengths, after `U22`–`U24` are written into a reviewed config. No default RNG. |
| `config/modelling/aptarank_tier1_method.json` | The closed register only. Absent keys stay blocked. This audit does not create the file. |
| `tests/modelling/test_aptarank_tier1_analysis.py` | Synthetic numeric fixtures and synthetic A/C/G/U strings. |
| `tests/modelling/fixtures/aptarank_arp2/` | Synthetic uploads, shuffled row order, duplicate and missing ids, incomplete pairs, and numeric scores. No biological cores. |

Tests the later package should include:

- Join by id after the export rows are permuted. A join by row position fails the test.
- A missing export is a technical failure. It is not a zero score and it does not enter the median.
- An incomplete pair is excluded from the paired difference and from AUROC, and the exclusion count is reported.
- AUROC on a hand-built synthetic score vector uses the real label as the positive class and does not flip the scores when the value is below 0.5.
- Shuffle tokens are not counted as passes until a fixture declares that the UI binding `U19` is present. Without that declaration the shuffle summary is undefined.
- Cluster resampling on synthetic cluster ids keeps a real row and its control in the same cluster block, uses 10,000 replicates only when the percentile rule is configured, and is reproducible under seed 42.
- An undefined replicate is not replaced with zero.
- Uniform-control tests use synthetic parent lengths such as 4 and 6. They never read an EVAL file. Collision checks use synthetic digests supplied by the test.
- The loader refuses paths and role names for EVAL, REF, VALIDATION, TRAIN, production pools, and checkpoints.
- Importing `mfe_per_nt` or `pooled_gc_fraction` as an AptaRank component fails the test.
- No test constructs a combined Tier 1 and Tier 2 score.

ARP-2B still does not run the biological EVAL upload, does not fit the REF CDF locally, and does not verify the live UI. Those remain M9B, the synthetic UI preflight, M9C, and post-unlock execution.
