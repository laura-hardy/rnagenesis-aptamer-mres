# GEP-2A generator metric reconciliation

Audit only. Revision 1 corrects source provenance, the parsed-output requirement, the proposed GEP-2 file list, caller input validation, and the reviewed scientific decisions. It does not change code, M4 arithmetic, thresholds, aliases, or the GEP-1 fixtures. GEP-2 implementation is not started.

| Item | Value |
|---|---|
| Package | GEP-2A revision 1 |
| Governing plan | `docs/aptarank_full_mres_thesis_evaluation_plan.md`, version 3.0, revision date 7 October 2026 |
| Plan SHA-256 | `e6193d0d14245049c218b4da0ef8059fb63b2f31e4885b3457cd44e41b76c50c` |
| Branch | `generator-eval-prep` |
| Starting commit | `b2768e8bd8e584067558d01d2dfcad0ba6b4580c` |
| GEP-1 spec | `config/modelling/generator_eval_metric_spec.json` |
| Spec SHA-256 | `53dd1d1007b3d1c6a5ccc7a66645948d31abeda44cb9abcd360f73d6ac547b9a` |
| Spec schema | `generator-eval-metric-spec-gep1-draft-r1` |
| Spec status | `draft`; `aggregate_generator_quality_score` is false; 30 metric rows |
| Preflight | `scripts/modelling/generator_eval_preflight.py` |
| Preflight SHA-256 | `c70607e7c3168929f11655b9a2d71eaf0d1d709a9bce47b423a3960caa4234a4` |

The default synthetic preflight on `tests/modelling/fixtures/generator_eval_gep1/synthetic_four_condition_two_d1_seeds.json` returned status `passed`, metric count 30, and exactly 16 warnings. Those 16 are the spec `blocking_items`, each prefixed `unresolved:`. Three further warnings exist in `run_preflight` and were not emitted by that default run. They are audited below because the same emitter produces them on other synthetic inputs.

GEP-1 refuses a spec whose `freeze_status` is `frozen` (`metric_spec_frozen_in_gep1`) and refuses any metric row whose `scientific_role` is `closeness` (`closeness_metric_not_implemented`). Nothing in this audit is frozen.

## 1. Branch and source provenance

Metric descriptions in this audit cite the `generator-eval-prep` files at `b2768e8bd8e584067558d01d2dfcad0ba6b4580c`. Those are the files GEP-2 would import. For every cited implementation and configuration path, the worktree bytes, `git show b2768e8:<path>`, and `git show c150894:<path>` (`main` at `c150894b9982d7afebfb2b3390b0797a4da146b5`) were compared. Worktree content SHA-256 equals the HEAD object content for every cited tracked file. No cited metric formula below is taken from a `main`-only copy.

`scripts/modelling/m7_common.py` was checked as both a Git object and worktree bytes.

| Source | Git blob | Content SHA-256 |
|---|---|---|
| Worktree file, and `git hash-object` of those bytes | `8679bc437489421a515da9a932c2d82a9e70d348` | `ab551296da86488b4c13585af968176e5783f0fa4a1a0220621d0b9102a062a8` |
| `generator-eval-prep` HEAD `b2768e8:scripts/modelling/m7_common.py` | `8679bc437489421a515da9a932c2d82a9e70d348` | `ab551296da86488b4c13585af968176e5783f0fa4a1a0220621d0b9102a062a8` |
| `main` `c150894:scripts/modelling/m7_common.py` | `47bcc4a4f56bd74fe134b1ccc6796cc243733c00` | `408b9b8fd8abb9e963ffc9723fc5e0c1fe24da0e9853767d2e43b43a3bbfe9c3` |

The worktree bytes and the HEAD blob are the same object. The `main` blob is a different object. `git diff --stat main -- scripts/modelling/m7_common.py` lists the path: 4 insertions and 75 deletions from `main` to this HEAD. The earlier statement that this path was byte-identical to `main` was wrong.

The copy GEP-2 would import is the `generator-eval-prep` file. `m7_candidate_guardrails.py` on this branch imports it. Its `format_decimal`, at line 195, returns `format(float(value), ".17g")`. Every later citation of `m7_common.format_decimal` means that function. The `main` file also defines `format_decimal` with the same one-line body, at line 196. That file additionally defines child-environment controls absent from this branch: `CUDA_MODULE_LOADING` fixed to `LAZY`, `FIXED_CHILD_ENVIRONMENT_CONTROLS`, `assert_fixed_child_environment_controls`, and `unexpected_environment_detail`. Those names are `main`-only. They are not a metric formula and they are not imported by the generator-eval-prep M7 caller. The review archive stores the `main` file under a separate label as branch-difference evidence. It is not the implementation source.

`docs/aptarank_full_mres_thesis_evaluation_plan.md` on this branch is version 3.0, revision date 7 October 2026. Worktree content SHA-256 equals HEAD: `e6193d0d14245049c218b4da0ef8059fb63b2f31e4885b3457cd44e41b76c50c`. On `main` the same path is version 2.7, dated 29 September 2026, content SHA-256 `3bf2e44667dee3246df46e5413ab74b0a043af8096b5af5df8649ab855110dbb`. `git diff --stat main --` that path is 178 insertions and 447 deletions. This audit follows version 3.0 only. It does not copy `main` into this branch. The version 2.7 file is not archived as an implementation source.

These cited files have the same content SHA-256 in the worktree, at HEAD, and on `main`. Archived source for each is `generator-eval-prep`/`HEAD`. `git diff --stat main` does not list them:

| Path | Content SHA-256 | Archived from |
|---|---|---|
| `scripts/modelling/m4_diagnostic_metrics.py` | `eebb6c8faf0d909bd907cd1e1e09c75908676ffe3e4eb04842f09b943b9d9e56` | `generator-eval-prep`/`HEAD` |
| `scripts/modelling/m6_diagnostic_generation.py` | `83f299bea7ec69406c898ad0e971bebf06056beb58649de0c25a5cc6d7195726` | `generator-eval-prep`/`HEAD` |
| `scripts/modelling/m7_candidate_guardrails.py` | `b368d029ec9d73f81af43ef8f19c4e7255b1228b50138a03a6ca53a554f7f280` | `generator-eval-prep`/`HEAD` |
| `scripts/b1_development_pool_runner.py` | `622684b254f911ca4d00db8af20d0d0c67eeebf46007e3fe84995e1e11db2341` | `generator-eval-prep`/`HEAD` |
| `scripts/null_model.py` | `c5914ba9cfe2240e9f9d2a539d7545d2b35dc44ddae5bfa631bf1c03ca6101f2` | `generator-eval-prep`/`HEAD` |
| `config/modelling/validation_metrics_v1.yaml` | `d30006c6f2b94be89ee2c7721b701e76e6835142a1af9f49997ba0d5baadf4bb` | `generator-eval-prep`/`HEAD` |
| `config/experiments/generator_evaluation.yaml` | `4145b8f4eb5ebf131b4775ee40b452e00e3f6ea03a101c43209006859eb85ce8` | `generator-eval-prep`/`HEAD` |
| `config/experiments/B2_empirical_null.yaml` | `43a691c870f487d81eddb5f2a818c5396b33978a764f1bbae0a8b507bab0f2bf` | `generator-eval-prep`/`HEAD` |
| `scripts/data_preparation/aptabase_cleaning.py` | `258c2787880e341eb12b0b895c860af40f22a302756616dff3516df37be94115` | `generator-eval-prep`/`HEAD` |
| `scripts/data_preparation/adapters/s6_profile.py` | `cc0939579fd6fbbfffb3eefbadf85e4acb158cdfe34925978e26f6003924d6d1` | `generator-eval-prep`/`HEAD` |
| `scripts/data_preparation/adapters/s5_cdhit_clustering.py` | `c17a32fdd389c7b018be5a66e47cf62edcefc0bb718c9fd39b3c81e5f9b64d2f` | `generator-eval-prep`/`HEAD` |
| `scripts/data_preparation/adapters/s5_sequence_clustering.py` | `8fa77b6d7d9b1e209f90112d9493db31b004dc3a83b9db2b0631808492435630` | `generator-eval-prep`/`HEAD` |

These cited files exist at HEAD and are absent from `main`. Archived source for each is `generator-eval-prep`/`HEAD`:

| Path | Content SHA-256 | Archived from |
|---|---|---|
| `config/modelling/generator_eval_metric_spec.json` | `53dd1d1007b3d1c6a5ccc7a66645948d31abeda44cb9abcd360f73d6ac547b9a` | `generator-eval-prep`/`HEAD` |
| `scripts/modelling/generator_eval_preflight.py` | `c70607e7c3168929f11655b9a2d71eaf0d1d709a9bce47b423a3960caa4234a4` | `generator-eval-prep`/`HEAD` |
| `tests/modelling/test_generator_eval_preflight.py` | `fd95e3d69f53e231c01bc55af287551a9bdd1c15f155423c39b48cf6a8a2756d` | `generator-eval-prep`/`HEAD` |

`scripts/modelling/m7_common.py` is archived from `generator-eval-prep`/`HEAD` at content SHA-256 `ab551296da86488b4c13585af968176e5783f0fa4a1a0220621d0b9102a062a8`. The `main` content SHA-256 `408b9b8fd8abb9e963ffc9723fc5e0c1fe24da0e9853767d2e43b43a3bbfe9c3` is stored only as labelled difference evidence.

`config/experiments/generator_evaluation.yaml` records historical hashes that do not match the current `generator-eval-prep` bytes: `minimal_evaluation_implementation.sha256` is `f7abde50ab8020c4d7ee763ed1a88ab1f0f721c98fd46193832fdd912ba28a4e`, while `m4_diagnostic_metrics.py` is `eebb6c8faf0d909bd907cd1e1e09c75908676ffe3e4eb04842f09b943b9d9e56`; `companion_runner_sha256` is `d13133cc80f3e27eaac824399184fbf382a4c78bbcd6575c1adeb9a6ea7ec358`, while `scripts/b1_development_pool_runner.py` is `622684b254f911ca4d00db8af20d0d0c67eeebf46007e3fe84995e1e11db2341`. The GEP-1 spec hashes do match the current M4, M6, and `validation_metrics_v1.yaml` bytes on this branch. Freeze the spec hashes, not the stale block in `generator_evaluation.yaml`.

## 2. Shared rules used by every implemented ledger metric

**Ledger seed rule.** `summarise_attempts`, `evaluate_hard_guardrails`, and `report_only_diagnostics` summarise the ledger they are given. They do not treat candidate rows, generation chunks, B1 length-control seeds, length-sampling seeds, or the single B2 empirical-null seed as independent training replicates. D1 training seeds are the training-replicate unit when more than one exists. These functions do not aggregate across that unit. The same sentence is `seed_or_block_treatment` on every GEP-1 metric row.

**Quantiles.** Where a metric reports quantiles, the index is `int(round(p * (n - 1)))` on values sorted ascending (`m6_diagnostic_generation._quantiles`). The keys are `count`, `minimum`, `p25`, `median`, `p75`, `maximum`, and `mean`. No confidence interval is attached.

**Condition scope on every spec row.** Report B0, B1, B2, and D1 separately. Do not pool B0's historical 37-nt regime into a matched-length B1/D1 contrast. The M4 and M6 functions themselves do not know condition labels. Four-condition separation is the GEP-1 preflight contract, not a second formula.

**Plan roles.** Section 5.1 uses outcome, guardrail, or closeness. The spec also uses `accounting` and `descriptor`. This audit does not promote an accounting count or a descriptor into closeness. "Proposed role: not applicable" means none of those three plan roles.

## 3. Name reconciliation

No alias below is a second metric. This audit does not rename a result key.

### 3.1 `parsed_outputs` versus successfully parsed outputs

| Token | Where it exists | What it counts |
|---|---|---|
| `raw_attempts` | Result key of `m4_diagnostic_metrics.summarise_attempts` | The attempt count. One per schema-valid ledger row. |
| `parsed_outputs` | Result key of `m4_diagnostic_metrics.summarise_attempts` | The legacy M4 predicate. On a schema-valid ledger it equals `raw_attempts`. |
| `successfully_parsed_outputs` | Accounting name in `config/experiments/generator_evaluation.yaml`. No function emits it yet. | The thesis-table accounting quantity. GEP-2 must add it as a new adapter field. |
| `parsed_status` / `parsed_status_true` | Synthetic record field and preflight accounting key | GEP-1 semantics for that thesis quantity: a nonempty extracted sequence before A/C/G/U validity filtering. |

`validate_attempt_record` sets `parsed` to true when `raw_decoded_text` is nonempty, or `cleaned_sequence` is nonempty, or `raw_length == 0`. The ledger schema requires `raw_length == len(raw_decoded_text)`. On every schema-valid row the predicate is therefore true, including an empty unparseable row. `parsed_outputs` equals `raw_attempts` on a schema-valid ledger. It remains that legacy count. GEP-2 must not relabel it.

`successfully_parsed_outputs` is a distinct required accounting quantity for the thesis table. It corresponds to GEP-1 `parsed_status_true`: a nonempty extracted sequence, counted before A/C/G/U validity filtering. An alphabet-invalid nonempty output is parsed and is not valid. An empty or unparseable output is not successfully parsed. `_check_status_consistency` already requires `parsed_status is False` to carry `sequence is None`, `observed_length is None`, `alphabet_valid is False`, and `cleaning_status == "not_applicable"`, and requires `parsed_status is True` to carry a nonempty string. `project_m4_attempt` turns `parsed_status is False` into an empty raw and cleaned string, which the legacy M4 predicate still counts in `parsed_outputs`. `m4_reconciliation` stores both `m4_parsed_outputs` and `contract_parsed_status_true` and does not require them to be equal. The default synthetic preflight shows the difference: overall `attempted=18` and `parsed_status_true=14`, while M4 reconciliation still returned `matched` because equality is checked for attempts, valid outputs, exact hits, and the exact-hit rate only.

**Reviewed implementation requirement.** Keep the M4 result key `parsed_outputs` and do not modify M4 arithmetic. Add `successfully_parsed_outputs` in the GEP-2 adapter as its own accounting field, using the `parsed_status_true` rule above. Do not satisfy the thesis column by renaming `parsed_outputs`.

**Classification.** `parsed_outputs`: `implemented_and_freezable` as the legacy predicate. `successfully_parsed_outputs`: `required_missing` until the new adapter field exists.

### 3.2 `requested_length_exact_hit_rate` versus `exact_hit_rate`

Both names denote one ratio.

- Numerator: valid attempts whose cleaned length equals `requested_target_length`. Invalid and unparseable attempts are non-hits.
- Denominator: `raw_attempts` for that ledger, before filtering. A zero denominator yields `0.0` in `_rate`.
- M4 result key: `exact_hit_rate`, with `exact_hit_rate_denominator` equal to `raw_attempts`.
- Per-length result key: `by_requested_length[].exact_hit_rate`. There is no result key named `per_requested_length_exact_hit_rate`. The spec id `per_requested_length_exact_hit_rate` points at that nested key.
- Config id in `validation_metrics_v1.yaml`: `requested_length_exact_hit_rate`.
- `m6_diagnostic_generation.REPORT_ONLY_ITEMS` lists the config token.
- `m7_candidate_guardrails.report_only_block` emits `requested_length_exact_hit_rate` as `generator-eval-prep` `m7_common.format_decimal` of `exact_length_hits / len(attempts)`, a 17-significant-digit string of the same ratio (`format(float(value), ".17g")` at line 195 of the HEAD file in section 1).

`exact_hit_rate_valid_outputs_diagnostic` is a different denominator (`valid_outputs`), labelled `valid_outputs_only_diagnostic_not_the_approved_metric`, with `replaces_approved_raw_attempt_metric` false. It is not this alias.

`exact_hit_rate_is_an_eligibility_threshold` is false. The yaml historical provisional references 0.90 (overall) and 0.50 (per length, and only as a report once a length has at least 16 raw attempts) are not pass/fail decisions in `m4_diagnostic_metrics.py`.

B0 is a real contract difference, not an alias. The yaml says the eligibility rule does not apply to B0 or B2. The preflight goes further: B0 requested length is `unavailable`, and `exact_length_hits`, `exact_hit_rate`, and the denominator are null, with applicability `not_applicable`. The stated reason is that historical B0 records nominal `max_seq_len` 37 and cleaned length 36 and does not establish a biological requested length. Overall exact-hit accounting uses denominator name `attempted_rows_excluding_b0`. M4 has no B0 exception because it has no condition field.

**Freeze rule.** One public metric id, `exact_hit_rate`. The config token and the M7 string key are presentations of that id. Do not add a second spec row.

**Classification.** `implemented_but_contract_needs_resolution` until the frozen spec states that the alias is not a second metric and states that 0.90 and 0.50 are not decisions. B0 exact-hit applicability is decided below.

**Reviewed decision.** B0 remains a separate external panel. Its requested-length exact-hit rate stays `not_applicable`. Do not assign requested length 37 or 36 in order to compute a rate.

### 3.3 `maximum_identity_to_TRAIN` versus `maximum_edit_similarity_to_train`

| Token | Status |
|---|---|
| `maximum_identity_to_TRAIN` | Name in `validation_metrics_v1.yaml` `report_only_diagnostics.items` and in `generator_evaluation.yaml` `secondary_distribution_diagnostics.items`. No result key. |
| `maximum_edit_similarity_to_train` | Result key of `report_only_diagnostics` |

Formula, in `report_only_diagnostics`: if any valid row exists, `1.0 - min(distances)`; otherwise null. Each distance is the nearest-TRAIN normalised Levenshtein distance. `EDIT_SIMILARITY_DEFINITION` says this is an edit-based similarity, not a sequence identity. `m7_candidate_guardrails.diagnostics_record` sets `edit_similarity_is_sequence_identity` to false.

The nearest distance itself is a separate metric, `nearest_train_normalized_edit_distance`. It is not this alias.

**Freeze rule.** Keep the result key `maximum_edit_similarity_to_train`. Do not define a sequence-identity percentage under the config token, and do not treat the two strings as synonyms.

**Classification.** `implemented_but_contract_needs_resolution`.

**Scientific review.** Accept the edit-similarity key as the only public name, or explicitly retire `maximum_identity_to_TRAIN` without replacement. A true identity metric would be a new quantity. This audit does not define one.

### 3.4 `mfe_per_nucleotide` versus `mfe_per_nt`

| Token | Status |
|---|---|
| `mfe_per_nucleotide` | Config and `REPORT_ONLY_ITEMS` token. No result key in `structure_features`. |
| `mfe_per_nt` | Result key of `structure_features` and of the quantile block in `report_only_diagnostics` |
| `mfe_per_nt_median` | Headline extracted by `m7_candidate_guardrails.diagnostics_record` from `mfe_per_nt.median`. A display of one quantile, not a second formula. |

Formula: `float(mfe) / len(sequence)`. Valid sequences are nonempty, so the division is not zero. Direction in the spec is `not_applicable`. `generator_evaluation.yaml` says more negative MFE is not inherently better.

Section 6.1's AptaRank component "normalized MFE (lower favoured)" is a Tier 1 score component. It is not this generator key. Section 5.1's "normalized MFE" is the generator descriptor. The implemented length normalisation is `mfe_per_nt`.

**Freeze rule.** One generator metric id, `mfe_per_nt`. Do not add `mfe_per_nucleotide` as a second row and do not reuse the AptaRank component as if it were this key.

**Classification.** `implemented_but_contract_needs_resolution` until the public token is fixed to the code key and the AptaRank component is excluded in the frozen sentence.

### 3.5 Nucleotide and dinucleotide total variation

`composition` returns `nucleotide_counts`, `nucleotide_fractions`, `dinucleotide_counts`, and `dinucleotide_fractions`. `report_only_diagnostics` then calls `total_variation` against `composition(list(train_cores))` and emits:

- `nucleotide_total_variation_to_train`
- `dinucleotide_total_variation_to_train`

Formula: if any paired fraction is null, the result is null; otherwise `0.5 * sum(abs(left[key] - right[key]) for key in sorted(left))`. Range is `[0, 1]` when both distributions are complete. The reference role is TRAIN composition, not EVAL. Duplicate valid rows are retained. A sequence shorter than 2 contributes nucleotide counts and no dinucleotide pairs.

These keys are not spec `metric_id`s. The spec rows `nucleotide_distribution` and `dinucleotide_distribution` say total variation is an unresolved membership item, not those metrics.

A third pair of names appears only as labels in `m7_candidate_guardrails.REPORT_ONLY_DIAGNOSTIC_ITEMS`: `nucleotide_distribution_distance` and `dinucleotide_distribution_distance`. The function `m7_candidate_guardrails.report_only_diagnostics` calls the M6 function and does not emit those distance names. The headline uses the `_to_train` keys. Do not add the distance names as metric ids.

**Reviewed decision.** Legacy TRAIN mono- and dinucleotide total variation remains nested descriptive output under `report_only_diagnostics`. It does not become a separate closeness metric and it does not become a quality vote. The existing keys stay `nucleotide_total_variation_to_train` and `dinucleotide_total_variation_to_train`, with TRAIN as their reference. They are not the EVAL closeness metrics in section 7.3.

**Classification.** `implemented_and_freezable` as nested descriptive output. GEP-1 still emits `nucleotide_total_variation_membership_unresolved` and `dinucleotide_total_variation_membership_unresolved` because the draft spec is unchanged. GEP-2 records this membership in the spec and does not add separate metric ids for these TRAIN keys.

### 3.6 Other names that must not become extra metrics

| Name | Relationship |
|---|---|
| `valid_acgu` | Preflight count. On rows projected by `project_m4_attempt` it is compared with M4 `valid_outputs`. The M4 predicate is `^[ACGU]+$`. The preflight also requires `parsed_status`, `alphabet_valid`, `cleaning_status == "cleaned"`, and `observed_length == len(sequence)`. One validity count, not two metrics. |
| `attempted` | Preflight name for the same count as `raw_attempts`. |
| `unique_valid` | Preflight name for `unique_valid_outputs`. |
| `invalid` | Preflight name for `invalid_outputs` (`attempted - valid_acgu`). |

## 4. Capability audit

| Capability | Supported by existing generator code? | Evidence | Classification |
|---|---|---|---|
| GC fraction | No generator metric yet. The reviewed formula is the pooled fraction in section 7.1. Nucleotide fractions can display G and C separately. | Warning `gc_fraction_not_implemented`. `composition` has no GC key. | `required_missing` |
| Sequence clustering | No. Threshold is null and claims are not permitted. | `generator_evaluation.yaml` `sequence_clustering_identity_threshold.value: null`; `DEFERRED_BEYOND_M4` in M4; `clustering_or_embedding_metrics: false` in `report_only_diagnostics`. | `explicitly_deferred_by_plan` |
| Structure clustering | No generator or corpus structure-cluster metric was found in `scripts/modelling` or `config/experiments`. | Section 5.1 asks for structure clusters only where implemented. | `explicitly_deferred_by_plan` |
| Singleton, largest-cluster, and effective-diversity summaries | No. Named only as deferred quantities: `generated_cluster_concentration`, `cluster_count`, `singleton_fraction`, `largest_cluster_share`, `shannon_diversity`, `effective_cluster_count`. | Same yaml block. `largest_duplicate_share` is exact-string multiplicity, not a cluster share. | `explicitly_deferred_by_plan` |
| Validated representation metric | No. | `representation_metrics.implemented_in_m4: false`; `frozen_representation_metrics` is in `DEFERRED_BEYOND_M4`. | `explicitly_deferred_by_plan` |
| Generator-to-EVAL distance or closeness | No implemented row. Section 7.3 predeclares three metrics for synthetic references first. They become EVAL closeness only after unlock supplies unique EVAL cores. The spec contains no `closeness` row, and the preflight rejects that role. | Warning `eval_closeness_not_implemented`. | `required_missing` |
| Normalised MFE and paired fraction | Yes, behind a caller-supplied fold. GEP-1 does not call a fold. | `structure_features` keys `mfe_per_nt` and `paired_fraction`. | `mfe_per_nt`: `implemented_but_contract_needs_resolution`. `paired_fraction`: `implemented_and_freezable`. |
| Cluster-aware reference resampling | No generator procedure resamples EVAL clusters. | Section 3.3 includes EVAL clusters only where a frozen procedure resamples the reference. Section 6.2's 10,000 replicates and seed 42 belong to Tier 1, not to section 5.1. | `optional_not_implemented` |
| D1 per-training-seed summaries and observed ranges | Seed identity, count, and the one-seed limitation are implemented. Per-seed metric values and an observed range are not. The required uncertainty is those values and that range. | `d1_training_seed_summary`. With two seeds the statement says GEP-1 does not compute a confidence interval. Section 7.4. | `implemented_but_contract_needs_resolution` |
| Matched B1/D1 invocation analysis | The match predicate is implemented on synthetic rows. Production schedule documents are not loaded. Metrics are not computed inside matched blocks. A matched block is a descriptive controlled block, not a training replicate and not a significance-test unit. | `matched_schedule_structure`, `assert_pairing`, `build_schedule`. `production_schedule_wired` is false. | `implemented_but_contract_needs_resolution` for the predicate. Applying frozen metrics inside matched blocks is `required_missing`. |
| Production length-schedule provenance | The 1,000-attempt diagnostic builder exists. Its serialised formula strings are not the strings GEP-1 requires. No loader connects a production schedule to the preflight. | See section 6. | `implemented_but_contract_needs_resolution` |
| Unambiguous B2 empirical-null seed mapping | The evaluation record requires `empirical_null_seed` and rejects a generic `seed` field. The B2 raw record and authorisation block use `seed`. No mapper connects them. | `RAW_RECORD_KEYS` and `DEFAULT_SEED` in `scripts/null_model.py`. | `implemented_but_contract_needs_resolution` |

Corpus builders that are not generator metrics, and must not be copied in as if they were:

- `scripts/data_preparation/aptabase_cleaning.py` `calculate_gc_content` returns `100.0 * (G+C) / length` (a percent) for a cleaning alphabet. SHA-256 `258c2787880e341eb12b0b895c860af40f22a302756616dff3516df37be94115`.
- `scripts/data_preparation/adapters/s6_profile.py` `sequence_composition` appends per-sequence `(G+C)/length` using `GC_BASES = {G, C}`, then summarises those fractions. SHA-256 `cc0939579fd6fbbfffb3eefbadf85e4acb158cdfe34925978e26f6003924d6d1`.
- Corpus sequence clustering in `scripts/data_preparation/adapters/s5_cdhit_clustering.py` and `s5_sequence_clustering.py` uses identity 0.90 for corpus construction. `generator_evaluation.yaml` sets the generator threshold to null and says it was not invented in that draft. Copying 0.90 onto generated pools is a new decision.

## 5. Catalogue

Fields shared by every M4 or M6 row are in section 2. "Suitable for freezing without modification" means the formula and result key can stay as they are. It does not mean the draft package is already frozen.

Source hashes for this catalogue are the `generator-eval-prep`/`HEAD` content SHA-256 values from section 1. `m7_common.py` is `ab551296da86488b4c13585af968176e5783f0fa4a1a0220621d0b9102a062a8` on this branch. The `main` content SHA-256 `408b9b8fd8abb9e963ffc9723fc5e0c1fe24da0e9853767d2e43b43a3bbfe9c3` is not a catalogue source.

### 5.1 Spec rows

#### `raw_attempts`

- Classification: `implemented_and_freezable`
- Quantity: number of attempt-ledger rows
- Implementation: `m4_diagnostic_metrics.summarise_attempts` / `_consume`; config key `hard_guardrails.sample` does not define this count
- Result key: `raw_attempts`
- Formula: add 1 for every schema-valid row
- Reference role: none
- Denominator and filtering: not a ratio; no row removed
- Units and range: nonnegative integer count
- Direction: not applicable
- Length handling: not normalised; the same count is repeated inside `by_requested_length`
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `accounting`)
- Freeze without modification: yes

#### `parsed_outputs`

- Classification: `implemented_and_freezable` as the legacy M4 predicate
- Quantity: rows meeting the M4 parsed predicate. On a schema-valid ledger this equals `raw_attempts`. It is not the thesis successful-parse count.
- Implementation: `m4_diagnostic_metrics.validate_attempt_record`
- Result key: `parsed_outputs`
- Formula, reference, denominator, units, direction, length, and seed: section 3.1
- Proposed role: not applicable (spec role `accounting`)
- Freeze without modification: yes for the key and the predicate. Do not modify M4 arithmetic. Do not relabel this key as `successfully_parsed_outputs`.
- Warning: `parsed_outputs_predicate_versus_successful_parse` (emitted by the default preflight). The warning records the distinction. Closing it means adding the adapter field below, not editing M4.

#### `successfully_parsed_outputs`

- Classification: `required_missing`
- Quantity: thesis-table count of nonempty extracted sequences before A/C/G/U validity filtering
- Implementation: none yet. GEP-1 exposes the same rule as `parsed_status_true` in `generator_eval_preflight._accounting`. GEP-2 adds a new adapter accounting field. It does not change `summarise_attempts`.
- Result key: `successfully_parsed_outputs`. This is not a rename of `parsed_outputs`.
- Formula: count rows whose extracted sequence is nonempty. An alphabet-invalid nonempty output is included. An empty or unparseable output is excluded. Validity filtering remains the separate `valid_outputs` count.
- Reference role: none
- Denominator and filtering: not a ratio. The count is taken before A/C/G/U validity filtering.
- Units and range: nonnegative integer, at most `raw_attempts`
- Direction: not applicable
- Length handling: not a length metric
- Seed handling: ledger seed rule
- Proposed role: not applicable (accounting)
- Freeze without modification: no, until the adapter field exists and the spec carries its own row
- The default synthetic preflight's `parsed_status_true=14` against `attempted=18` is the behaviour this field must reproduce on that fixture.

#### `valid_outputs`

- Classification: `implemented_and_freezable`
- Quantity: attempts whose cleaned body matches `^[ACGU]+$`
- Implementation: `m4_diagnostic_metrics.recomputed_validity`, counted in `summarise_attempts`
- Result key: `valid_outputs`. Preflight key `valid_acgu` is the same count on a projected synthetic row, not a second metric (section 3.6).
- Formula: regex full match on a nonempty canonical body. A stored validity flag that disagrees raises `DiagnosticMetricError`.
- Reference role: none
- Denominator and filtering: not a ratio. Empty, unparseable, and other invalid rows stay in `raw_attempts`.
- Units and range: nonnegative integer
- Direction: not applicable
- Length handling: no length cutoff
- Seed handling: ledger seed rule
- Proposed role: not applicable for the count. The plan's validity outcome is the separate guardrail fraction.
- Freeze without modification: yes

#### `invalid_outputs`

- Classification: `implemented_and_freezable`
- Quantity: attempts that fail `recomputed_validity`
- Implementation: `m4_diagnostic_metrics.summarise_attempts`
- Result key: `invalid_outputs`
- Formula: `raw_attempts - valid_outputs`
- Reference role: none
- Denominator and filtering: not a ratio; invalid rows stay in the ledger
- Units and range: nonnegative integer
- Direction: not applicable
- Length handling: not normalised
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `accounting`)
- Freeze without modification: yes

#### `empty_or_unparseable_outputs`

- Classification: `implemented_and_freezable`
- Quantity: invalid attempts with an empty cleaned body or empty raw text
- Implementation: `m4_diagnostic_metrics.validate_attempt_record`
- Result key: `empty_or_unparseable_outputs`
- Formula: `(not valid) and (cleaned == "" or raw == "")`. A nonempty alphabet failure is invalid and is not in this count.
- Reference role: none
- Denominator and filtering: not a ratio
- Units and range: nonnegative integer
- Direction: not applicable
- Length handling: empty bodies have length 0
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `accounting`)
- Freeze without modification: yes

#### `exact_length_hits`

- Classification: `implemented_and_freezable`
- Quantity: valid attempts whose cleaned length equals the requested biological length
- Implementation: `m4_diagnostic_metrics.summarise_attempts`
- Result key: `exact_length_hits`
- Formula: count of `valid and len(cleaned) == requested_target_length`, before filtering
- Reference role: none
- Denominator and filtering: not the rate. Non-hits remain in the ledger.
- Units and range: nonnegative integer
- Direction: not applicable
- Length handling: equality of cleaned length and requested length. No nucleotide cutoff.
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `accounting`)
- Freeze without modification: yes, including for B1 and D1. B0 applicability is the exact-hit rate contract in section 3.2, not a change to this count's formula.

#### `exact_hit_rate`

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: requested-length exact-hit rate
- Implementation: `m4_diagnostic_metrics.summarise_attempts`; alias tokens in `validation_metrics_v1.yaml`, `m6_diagnostic_generation.REPORT_ONLY_ITEMS`, and `m7_candidate_guardrails.report_only_block`
- Result key: `exact_hit_rate`
- Formula and the unresolved alias: section 3.2
- Reference role: none
- Denominator and filtering: `raw_attempts`, before filtering
- Units and range: fraction in `[0, 1]`
- Direction: not applicable. It is not an execution-success requirement and not an eligibility threshold.
- Length handling: cleaned length versus requested length. B0 is `not_applicable` in the preflight.
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: the ratio can stay. The public alias, the historical 0.90 reference, and the B0 applicability sentence cannot be left implicit.
- Warnings: `alias_requested_length_exact_hit_rate`, `per_length_exact_hit_floor_not_a_decision`

#### `exact_hit_rate_valid_outputs_diagnostic`

- Classification: `implemented_and_freezable`
- Quantity: valid-only exact-hit diagnostic
- Implementation: `m4_diagnostic_metrics.summarise_attempts`
- Result key: `exact_hit_rate_valid_outputs_diagnostic` with nested `rate`, `denominator`, and `replaces_approved_raw_attempt_metric`
- Formula: `exact_length_hits / valid_outputs`. The rate is `0.0` when `valid_outputs` is 0. `replaces_approved_raw_attempt_metric` is false.
- Reference role: none
- Denominator and filtering: `valid_outputs` only
- Units and range: fraction in `[0, 1]`
- Direction: not applicable
- Length handling: same hit definition as `exact_hit_rate`
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: yes, provided it remains labelled as not the approved rate

#### `eos_marker_observations`

- Classification: `implemented_and_freezable`
- Quantity: attempts with `eos_marker_observed` true
- Implementation: `m4_diagnostic_metrics.summarise_attempts`
- Result key: `eos_marker_observations`
- Formula: count of the boolean flag. A non-boolean flag rejects the ledger.
- Reference role: none
- Denominator and filtering: not a ratio
- Units and range: nonnegative integer
- Direction: not applicable
- Length handling: the flag is not a length
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: yes

#### `early_eos_observations`

- Classification: `implemented_and_freezable`
- Quantity: valid attempts with an EOS marker and cleaned length strictly below the requested length
- Implementation: `m4_diagnostic_metrics.validate_attempt_record`
- Result key: `early_eos_observations`
- Formula: count of `early_eos`, which must equal `valid and eos_marker_observed and len(cleaned) < requested`. An early EOS is not an exact hit.
- Reference role: none
- Denominator and filtering: not a ratio. A disagreeing flag rejects the ledger.
- Units and range: nonnegative integer
- Direction: not applicable
- Length handling: strict shortfall plus validity plus EOS
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: yes

#### `cleaned_length_distribution`

- Classification: `implemented_and_freezable`
- Quantity: cleaned-length multiset over every attempt, including invalid rows
- Implementation: `m4_diagnostic_metrics.summarise_attempts`
- Result key: `cleaned_length_distribution` as `{value, count}` pairs sorted by length
- Formula: count of attempts at each cleaned length
- Reference role: none
- Denominator and filtering: not a ratio; no attempt removed
- Units and range: nonnegative counts over nonnegative integer lengths
- Direction: not applicable
- Length handling: this is the length distribution. It does not define a short/long cutoff. The plan's short/long regime remains the frozen S6 two-component GMM. This metric does not refit it.
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: yes

#### `length_shortfall_distribution`

- Classification: `implemented_and_freezable`
- Quantity: distribution of `requested - cleaned` where cleaned is shorter than requested
- Implementation: `m4_diagnostic_metrics.summarise_attempts`
- Result key: `length_shortfall_distribution`
- Formula: counts of positive shortfalls
- Reference role: none
- Denominator and filtering: attempts that are not short are omitted here and remain in `raw_attempts`
- Units and range: nonnegative counts over positive integer nucleotide shortfalls
- Direction: not applicable
- Length handling: exact hits and excesses are not shortfalls
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: yes

#### `length_excess_distribution`

- Classification: `implemented_and_freezable`
- Quantity: distribution of `cleaned - requested` where cleaned is longer than requested
- Implementation: `m4_diagnostic_metrics.summarise_attempts`
- Result key: `length_excess_distribution`
- Formula: counts of positive excesses
- Reference role: none
- Denominator and filtering: attempts that are not long are omitted here and remain in `raw_attempts`
- Units and range: nonnegative counts over positive integer nucleotide excesses
- Direction: not applicable
- Length handling: excess is cleaned length minus requested length
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: yes

#### `unique_valid_outputs`

- Classification: `implemented_and_freezable`
- Quantity: number of distinct valid cleaned sequences
- Implementation: `m4_diagnostic_metrics.summarise_attempts` / `_duplicate_summary`
- Result key: `unique_valid_outputs`
- Formula: number of distinct strings among valid cleaned bodies. Exact string equality. No clustering.
- Reference role: none
- Denominator and filtering: not a ratio. Invalid sequences are excluded. `unique_fraction` uses `valid_outputs` as its denominator.
- Units and range: nonnegative integer
- Direction: not applicable
- Length handling: no length bin
- Seed handling: ledger seed rule
- Proposed role: outcome
- Freeze without modification: yes. The spec already says this is not a closeness vote and not an aggregate score.

#### `duplicates`

- Classification: `implemented_and_freezable`
- Quantity: extra copies of valid sequences
- Implementation: `m4_diagnostic_metrics.summarise_attempts`
- Result key: `duplicates`
- Formula: `valid_outputs - unique_valid_outputs`
- Reference role: none
- Denominator and filtering: not a ratio. Invalid sequences are excluded.
- Units and range: nonnegative integer
- Direction: not applicable
- Length handling: not normalised
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `accounting`)
- Freeze without modification: yes

#### `largest_duplicate_multiplicity`

- Classification: `implemented_and_freezable`
- Quantity: largest number of times one valid cleaned sequence occurs
- Implementation: `m4_diagnostic_metrics.summarise_attempts`
- Result key: `largest_duplicate_multiplicity`
- Formula: maximum exact-string count, or 0 when there are no valid outputs
- Reference role: none
- Denominator and filtering: not a ratio
- Units and range: nonnegative integer
- Direction: not applicable
- Length handling: not normalised
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `accounting`)
- Freeze without modification: yes

#### `largest_duplicate_share`

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: share of the most frequent valid sequence
- Implementation: `m4_diagnostic_metrics.evaluate_hard_guardrails` and the same value from `summarise_attempts`
- Result key: `largest_duplicate_share`
- Formula: count of the most frequent valid output divided by `valid_outputs`
- Reference role: none
- Denominator and filtering: `valid_outputs`. Invalid attempts are in neither part.
- Units and range: null when `valid_outputs` is 0; otherwise `(0, 1]`
- Direction: lower. Approved comparison maximum 0.01.
- Length handling: not length-stratified
- Seed handling: ledger seed rule
- Proposed role: guardrail
- Freeze without modification: the ratio and the existing 0.01 comparison can stay.
- Reviewed reporting rule: a guardrail failure on a frozen final pool remains visible. It does not authorize replacement of that pool and it does not authorize exclusion of the pool after EVAL. Section 7.7 applies the same sentence to the other four hard-guardrail comparisons. GEP-1 does not apply the M4 checkpoint-ineligibility decision, and GEP-2 must not add a post-EVAL replacement or exclusion.
- This is exact-string concentration, not `largest_cluster_share`.

#### `valid_nonempty_acgu_fraction`

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: fraction of raw attempts that are valid canonical RNA
- Implementation: `m4_diagnostic_metrics.evaluate_hard_guardrails`
- Result key: `values.valid_nonempty_acgu_fraction` and the matching `decisions` entry
- Formula: `valid_outputs / raw_attempts`
- Reference role: none
- Denominator and filtering: `raw_attempts`. Invalid attempts remain.
- Units and range: fraction in `[0, 1]`
- Direction: higher. Approved comparison minimum 0.99.
- Length handling: not length-stratified
- Seed handling: ledger seed rule
- Proposed role: guardrail
- Missing-denominator behaviour: `_rate` returns `0.0` when `raw_attempts` is 0, and the decision is `passed: false`, status `undefined_empty_valid_denominator`
- Freeze without modification: the ratio and 0.99 comparison can stay. The reviewed reporting rule is the same sentence as `largest_duplicate_share`: a failure on a frozen final pool remains visible and does not authorize replacement or exclusion after EVAL. The spec already says a failed guardrail makes a checkpoint ineligible in the M4 rule and that GEP-1 does not apply that decision. GEP-2 must not apply it as a post-EVAL exclusion.

#### `empty_or_unparseable_fraction`

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: fraction of raw attempts that are empty or unparseable
- Implementation: `m4_diagnostic_metrics.evaluate_hard_guardrails`
- Result key: `values.empty_or_unparseable_fraction`
- Formula: `empty_or_unparseable_outputs / raw_attempts`. Nonempty alphabet failures are not in the numerator.
- Reference role: none
- Denominator and filtering: `raw_attempts`
- Units and range: fraction in `[0, 1]`
- Direction: lower. Approved comparison maximum 0.01.
- Length handling: not length-stratified
- Seed handling: ledger seed rule
- Proposed role: guardrail
- Freeze without modification: the ratio and 0.01 comparison can stay. The reviewed reporting rule is section 7.7: a failure on a frozen final pool remains visible and does not authorize replacement or exclusion after EVAL.

#### `unique_fraction`

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: fraction of valid outputs that are the first occurrence of their cleaned string
- Implementation: `m4_diagnostic_metrics.evaluate_hard_guardrails`
- Result key: `values.unique_fraction`
- Formula: `unique_valid_outputs / valid_outputs`
- Reference role: none
- Denominator and filtering: `valid_outputs`
- Units and range: `[0, 1]` when the denominator is positive
- Direction: higher. Approved comparison minimum 0.95.
- Length handling: not length-stratified
- Seed handling: ledger seed rule
- Proposed role: guardrail. The count `unique_valid_outputs` remains the outcome. This fraction is not a second diversity metric and not a cluster diversity.
- Freeze without modification: the ratio and 0.95 comparison can stay. The reviewed reporting rule is section 7.7: a failure on a frozen final pool remains visible and does not authorize replacement or exclusion after EVAL.

#### `exact_train_match_rate`

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: exact copy rate against caller-supplied TRAIN cores
- Implementation: `m4_diagnostic_metrics.evaluate_hard_guardrails`
- Result key: `values.exact_train_match_rate`; match count key `exact_train_matches`
- Formula: number of valid attempts whose cleaned string is a member of the supplied TRAIN set, divided by `valid_outputs`. Exact string equality. Cores that fail `^[ACGU]+$` raise `train_reference_invalid`.
- Reference role: TRAIN cores as an exact copying reference. REF and EVAL are not inputs.
- Denominator and filtering: `valid_outputs`
- Units and range: `[0, 1]` when the denominator is positive
- Direction: lower. Approved comparison maximum 0.01.
- Length handling: full-string equality. No partial match and no length normalisation.
- Seed handling: ledger seed rule
- Proposed role: guardrail. Section 5.1 also calls TRAIN overlap a relationship to report. It is not closeness to EVAL.
- Freeze without modification: the ratio and 0.01 comparison can stay. GEP-1 does not load TRAIN (`train_reference_loaded` is false). The reviewed reporting rule is section 7.7: a failure on a frozen final pool remains visible and does not authorize replacement or exclusion after EVAL. Loading TRAIN at execution time is a later wiring step, not a new formula. The GEP-2 caller must fail closed on an empty or noncanonical TRAIN reference before this calculation, as section 7.8 requires. This audit does not load TRAIN.
- Warning: `train_reference_not_loaded_in_gep1` records that boundary. The warning does not mean the formula is missing.

#### `per_requested_length_exact_hit_rate`

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: exact-hit rate inside one requested length
- Implementation: `m4_diagnostic_metrics.summarise_attempts`
- Result key: `by_requested_length[].exact_hit_rate` together with `requested_target_length`
- Formula: the `exact_hit_rate` rule restricted to rows with that `requested_target_length`
- Reference role: none
- Denominator and filtering: `raw_attempts` at that requested length. Invalid accounted attempts at that length remain and are non-hits.
- Units and range: fraction in `[0, 1]` for each requested length present
- Direction: not applicable. The historical provisional reference 0.50 is not a decision. Lengths with fewer than 16 raw attempts are reported; that minimum is yaml text, not a drop rule in M4.
- Length handling: stratified by requested biological length. No short/long boundary is defined here.
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: the stratified rate can stay. The frozen spec must say 0.50 is not a pass/fail rule.
- Warning: `per_length_exact_hit_floor_not_a_decision`

#### `nearest_train_normalized_edit_distance`

- Classification: `implemented_and_freezable`
- Quantity: nearest-TRAIN normalised Levenshtein distance, as quantiles over valid rows
- Implementation: `m6_diagnostic_generation.nearest_train`, `edit_distance`, `report_only_diagnostics`
- Result key: `nearest_train_normalized_edit_distance`
- Formula: for each distinct valid sequence, the minimum over TRAIN cores of Levenshtein distance divided by the length of the longer sequence. Myers' bit-parallel method implements the distance. The distance is computed once per distinct sequence and then repeated for every valid row of that sequence. Quantiles use the shared quantile rule. `thresholds_defined` is false.
- Reference role: TRAIN cores as a nearest-edit reference
- Denominator and filtering: the longer of the valid sequence and that TRAIN core. Quantiles are over valid rows. Invalid rows are excluded.
- Units and range: null when there are no valid rows; otherwise quantiles of values in `[0, 1]`
- Direction: higher, and `novelty_direction_only` is true. The spec statement says this direction is not an extra vote for generator quality.
- Length handling: normalised by the longer length. The length-stratified report is `full_length_stratified_results`.
- Seed handling: ledger seed rule
- Proposed role: outcome
- Freeze without modification: yes. GEP-1 does not execute it because it does not load TRAIN. That is the warning `train_reference_not_loaded_in_gep1`, not a formula change.

#### `maximum_edit_similarity_to_train`

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: one minus the smallest nearest-TRAIN normalised edit distance
- Implementation: `m6_diagnostic_generation.report_only_diagnostics`
- Result key: `maximum_edit_similarity_to_train`
- Formula and the rejected identity alias: section 3.3
- Reference role: TRAIN cores as a nearest-edit reference
- Denominator and filtering: valid rows only
- Units and range: null when there are no valid rows; otherwise a float in `[0, 1]`
- Direction: lower, novelty only
- Length handling: inherits the longer-sequence normalisation. Not an identity percentage.
- Seed handling: ledger seed rule
- Proposed role: outcome
- Freeze without modification: the formula and the code key can stay. The config token `maximum_identity_to_TRAIN` cannot be frozen as a synonym.
- Warning: `alias_maximum_identity_to_train`

#### `nucleotide_distribution`

- Classification: `implemented_and_freezable` for the four fractions. The nested TRAIN total variation is the section 3.5 decision.
- Quantity: base composition of valid rows
- Implementation: `m6_diagnostic_generation.composition`
- Result keys: `composition.nucleotide_counts` and `composition.nucleotide_fractions` for A, C, G, and U. There is no key named `nucleotide_distribution`.
- Formula: each valid row contributes every base. A fraction is null when the base total is 0. The four fractions sum to 1 when the total is positive.
- Reference role: none for the fractions. `nucleotide_total_variation_to_train` stays nested descriptive output and is not this metric.
- Denominator and filtering: total bases across valid rows. Invalid rows are excluded. Duplicate valid rows are retained. The pooled GC fraction in section 7.1 uses this same valid-row population.
- Units and range: counts, and fractions in `[0, 1]` or null
- Direction: not applicable
- Length handling: each base contributes equally. Not length-stratified in this block.
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: yes for the four fractions and for leaving TRAIN total variation nested.
- Pooled GC is a separate descriptor defined in section 7.1. It is not one of these four keys.
- Warning: `nucleotide_total_variation_membership_unresolved` still fires from the unchanged draft spec.

#### `dinucleotide_distribution`

- Classification: `implemented_and_freezable` for the 16 fractions. The nested TRAIN total variation is the section 3.5 decision.
- Quantity: overlapping dinucleotide composition of valid rows
- Implementation: `m6_diagnostic_generation.composition`
- Result keys: `composition.dinucleotide_counts` and `composition.dinucleotide_fractions` for the 16 A/C/G/U pairs
- Formula: overlapping pairs `sequence[i:i+2]`. A sequence shorter than 2 adds no pairs. A fraction is null when the pair total is 0.
- Reference role: none for the fractions. `dinucleotide_total_variation_to_train` stays nested descriptive output and is not this metric.
- Denominator and filtering: total overlapping dinucleotides across valid rows of length at least 2
- Units and range: counts, and fractions in `[0, 1]` or null
- Direction: not applicable
- Length handling: no short/long cutoff
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: yes for the 16 fractions and for leaving TRAIN total variation nested.
- Warning: `dinucleotide_total_variation_membership_unresolved` still fires from the unchanged draft spec.

#### `mfe`

- Classification: `implemented_and_freezable`
- Quantity: fold-returned minimum free energy, as quantiles over valid rows
- Implementation: `m6_diagnostic_generation.structure_features`
- Result key: `mfe`
- Formula: `float(mfe)` from the caller-supplied fold. The code does not rescale. A structure whose length differs from the sequence raises `fold_invalid`. Quantiles use the shared rule. The value is computed once per distinct valid sequence and repeated on each valid row.
- Reference role: none
- Denominator and filtering: not a ratio. Invalid rows are excluded.
- Units and range: unconstrained float. The spec notes the ViennaRNA convention kcal/mol and says this code does not convert the value. `generator_evaluation.yaml` records ViennaRNA 2.7.0 as `recorded_h200_version_not_a_new_pin`.
- Direction: not applicable. More negative is not a selection score.
- Length handling: not divided by length
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: yes. GEP-1 does not call a fold. Warning `structure_metrics_not_executed_in_gep1` is that execution boundary.

#### `mfe_per_nt`

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: fold-returned MFE divided by sequence length
- Implementation: `m6_diagnostic_generation.structure_features`
- Result key: `mfe_per_nt`
- Formula and alias: section 3.4
- Reference role: none
- Denominator and filtering: sequence length in nucleotides. Quantiles over valid rows.
- Units and range: unconstrained float per nucleotide
- Direction: not applicable
- Length handling: divides by the valid sequence length. It does not define the S6 short/long regime.
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`). It is not an EVAL closeness metric.
- Freeze without modification: the division and the code key can stay. The public token and the separation from AptaRank normalised MFE cannot stay implicit.
- Warning: `alias_mfe_per_nucleotide`

#### `paired_fraction`

- Classification: `implemented_and_freezable`
- Quantity: fraction of positions marked paired in the fold dot-bracket
- Implementation: `m6_diagnostic_generation.structure_features`
- Result key: `paired_fraction`
- Formula: `(count of "(" plus count of ")") / sequence length`. Unpaired positions are not in the numerator. The structure length must equal the sequence length.
- Reference role: none
- Denominator and filtering: sequence length. Quantiles over valid rows.
- Units and range: null when there are no valid rows; otherwise quantiles of values in `[0, 1]` for a consistent dot-bracket
- Direction: not applicable
- Length handling: normalised by sequence length. No short/long cutoff.
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: yes. The same fold-execution warning as `mfe` applies.

#### `full_length_stratified_results`

- Classification: `implemented_and_freezable`
- Quantity: the report-only block repeated at each requested length
- Implementation: `m6_diagnostic_generation.report_only_diagnostics`
- Result key: `by_requested_length`
- Formula: for each `requested_target_length`, the unstratified report-only block on that length's valid rows, plus `raw_attempts`, `exact_length_hits`, and `exact_hit_rate` on every attempt at that length
- Reference role: none for the grouping. Stratum blocks use the same TRAIN and fold inputs as the unstratified block.
- Denominator and filtering: the unstratified denominators, restricted to that requested length
- Units and range: one stratum per requested length present
- Direction: not applicable. This grouping is not an aggregate score and does not define a new length boundary.
- Length handling: grouped by `requested_target_length` only
- Seed handling: ledger seed rule
- Proposed role: not applicable (spec role `descriptor`)
- Freeze without modification: yes. An empty stratum list is the empty-ledger result. A stratum with no valid rows keeps null structure and distance summaries and a defined attempt count.

### 5.2 Plan section 5.1 requirements that are not one spec row

#### Four-condition accounting and the separate B0 panel

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: attempted, successfully parsed, valid, unique, duplicate, and invalid accounting for B0, B1, B2, and D1, with B0 outside the matched-length contrast. The successfully parsed column is `successfully_parsed_outputs`, not the legacy `parsed_outputs` key.
- Implementation: `generator_eval_preflight._accounting`, `_b0_provenance`, `assess_claim`. SHA-256 of the preflight file is in the header.
- Result keys: `accounting_by_condition`, `b0_external_comparator`, `b0_included_in_matched_b1_d1_controlled_comparison` (always false), `b0_exact_hit_applicability`, `b0_requested_length_status`
- Formula: section 3.1, section 3.2, and section 3.6. `assess_claim` rejects a controlled comparison that includes B0 or B2.
- Reference role: none
- Denominator and filtering: condition-specific. B0 exact-hit denominator is null.
- Units and range: counts, plus the exact-hit fraction where applicable
- Direction: not applicable
- Length handling: B0 length regime `historical_37nt`; nominal `max_seq_len` constant 37; requested length unavailable
- Seed handling: B0 historical generation seeds, historical batches, and candidate rows are not training replicates. The preflight rejects B0 rows that carry a training, invocation, length-control, or empirical-null seed.
- Proposed role: not applicable for the accounting. B0 remains a separate external panel.
- Freeze without modification: the separation rules can stay. Reviewed decision: B0 exact-hit applicability stays `not_applicable`. Production pools are not loaded (`production_pools_loaded` is false).

#### GC fraction

- Classification: `required_missing`
- Quantity: pooled GC fraction of valid rows, named in section 5.1 beside nucleotide composition
- Implementation: none in the generator suite. Section 7.1 is the formula GEP-2 must add. `composition` still has no GC key.
- Result key: to be added by GEP-2. It is not a relabel of `nucleotide_fractions`.
- Formula: `(count_G + count_C) / total canonical bases` over the same valid-row population used by `nucleotide_fractions`. Duplicate valid rows are retained.
- Reference role: none
- Denominator and filtering: total canonical bases in that valid-row population. Invalid rows are excluded.
- Units and range: fraction in `[0, 1]`
- Direction: `not_applicable`
- Length handling: each canonical base contributes equally. A requested length stratum uses the same population restricted to that stratum. The short/long assignment, when requested, is the frozen S6 assignment and is not a new nucleotide cutoff.
- Seed handling: ledger seed rule
- Proposed role: descriptor
- Freeze without modification: the formula is decided. The code is not written.
- Warning: `gc_fraction_not_implemented`
- Decision: section 7.1

#### Sequence clustering, singleton, largest cluster, effective diversity

- Classification: `explicitly_deferred_by_plan`
- Quantity: section 5.1 diversity summaries "where implemented"
- Implementation: explicitly not implemented. Config status `DEFERRED_BEYOND_M4`, `clustering_dependent_claims_permitted: false`, `value: null`.
- Result key: none
- Formula: none
- Reference role: none
- Denominator and filtering: not defined
- Units and range: not defined
- Direction: not applicable
- Length handling: not defined
- Seed handling: not defined
- Proposed role: outcome or guardrail only if a later review un-defers them. They are not closeness votes. Section 5.1 says diversity is not an extra closeness vote.
- Freeze without modification: yes, as deferred. Do not invent a threshold in GEP-2.
- Warning: `clustering_diversity_deferred`
- Options: section 7.2

#### Structure clustering

- Classification: `explicitly_deferred_by_plan`
- Quantity: structure clusters, required by section 5.1 only where implemented
- Implementation: none found
- Result key: none
- Formula: none
- Reference role: none
- Remainder: same as sequence clustering. No structure-cluster threshold exists to freeze.
- Proposed role: not applicable until an implementation exists
- Freeze without modification: yes, as absent
- Options: section 7.2

#### Representation metric

- Classification: `explicitly_deferred_by_plan`
- Quantity: one frozen representation metric only if already implemented and validated before unlock
- Implementation: none. `representation_metrics_implemented: false`.
- Result key: none
- Formula: none
- Reference role: would have been a validated embedding. None is validated in this repository's generator contract.
- Proposed role: closeness only if one had already existed. It does not.
- Freeze without modification: yes, as not used
- Warning: `representation_metrics_deferred`
- Option: do not add one in GEP-2. Section 5.1 does not allow a new representation model during evaluation.

#### EVAL distance or closeness

- Classification: `required_missing`
- Quantity: three separate closeness metrics, defined in section 7.3
- Implementation: none. No row has reference role EVAL. GEP-2 may implement them against synthetic references only. They become EVAL closeness metrics only after the formal unlock supplies unique EVAL cores.
- Result keys: one each for nearest-reference normalized edit distance, nucleotide total variation to the reference, and dinucleotide total variation to the reference. They are not combined.
- Formula: section 7.3. Legacy TRAIN total variation stays the nested descriptive output in section 3.5 and is not one of these rows.
- Reference role: a synthetic reference until unlock; unique EVAL cores after the formal unlock. The caller rejects an unexpected reference role before calculation.
- Denominator and filtering: section 7.3. Invalid generated rows stay out of the generated side, as in the existing TRAIN edit and composition functions.
- Units and range: each distance is in `[0, 1]` when defined
- Direction: lower means closer for all three. Discordant results are reported as `mixed`. No aggregate score is formed.
- Length handling: support the frozen S6 short/long assignment. Do not invent a nucleotide cutoff. A stratified result requested without length-stratum labels fails closed before calculation.
- Seed handling: per D1 training seed values and the observed range. Matched B1/D1 blocks are descriptive controlled blocks, not training replicates and not significance-test units. B2 remains one seed.
- Proposed role: closeness
- Freeze without modification: the three metrics are decided. The code is not written, and EVAL is not loaded.
- Warning: `eval_closeness_not_implemented`
- Decision: section 7.3

#### D1 per-training-seed values and observed range

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: section 5.1 "D1 training-seed values/range"
- Implementation: `generator_eval_preflight.d1_training_seed_summary`
- Result keys: `d1_training_seeds`, `d1_training_seed_count`, `one_d1_training_seed_limitation`, `uncertainty_excludes_training_run_variability`, `statement`
- Formula: the set of `training_seed` on D1 rows. One seed sets the limitation statement "Uncertainty excludes training-run variability." Two or more seeds produce a statement that no confidence interval is computed. There is no per-seed map of metric values and no min/max across seeds. The reviewed uncertainty is those per-seed values and the observed range. It is not a confidence interval.
- Reference role: none
- Denominator and filtering: every D1 row must carry a training seed or the summary fails with `d1_training_seed_provenance_missing`
- Units and range: seed identifiers and a boolean limitation. Not a numeric metric range.
- Direction: not applicable
- Length handling: not applied
- Seed handling: `training_seed` is the only training-replicate unit. `NOT_TRAINING_REPLICATE_UNITS` lists record id, chunk id, generation seed, invocation seed, invocation index, batch position, attempt index, length-sampling seed, length-condition seed, empirical-null seed, and B0 historical fields.
- Proposed role: not applicable. This is the design-aware frame for outcome, guardrail, and closeness values.
- Freeze without modification: the limitation statement can stay. The missing per-seed metric values cannot be described as implemented.
- Decision: section 7.4. Generator uncertainty is the per-D1-training-seed values and the observed range.

#### Matched B1/D1 invocation analysis

- Classification: `implemented_but_contract_needs_resolution` for the match predicate. `required_missing` for metric values inside matched blocks.
- Quantity: section 5.1 "actual matched B1/D1 chunk results where applicable"
- Implementation of the predicate: `m6_diagnostic_generation.assert_pairing` compares `invocation_index`, `batch_position`, `requested_target_length`, `max_seq_len`, and `invocation_seed` by `original_attempt_index`. `generator_eval_preflight.matched_schedule_structure` compares those fields plus length-schedule provenance. Equality of `generation_chunk_id` is not sufficient. One-sided invocation indexes stay descriptive. `comparison_table` is a side-by-side ledger report with role `side_by_side_report_not_a_paired_significance_test`. It is not a within-block metric table.
- Result keys: `matched_invocation_indexes`, `incompatible_invocation_indexes`, `b1_only_invocation_indexes`, `d1_only_invocation_indexes`, `generation_chunk_label_is_sufficient_evidence` (false), `schedule_blocks_are_training_replicates` (false)
- Formula: a block is compatible only when invocation seed, provenance token, and position tokens agree. Position token is `(original_attempt_index, batch_position, requested_target_length, max_seq_len)`.
- Reference role: none
- Denominator and filtering: B0 and B2 are excluded from the controlled comparison
- Units and range: indexes and boolean flags
- Direction: not applicable
- Length handling: requested length and `max_seq_len` must match across B1 and D1 inside a block
- Seed handling: a matched block is a descriptive controlled block. It is not a training replicate and it is not a significance-test unit. D1 rows in one block may still carry a training seed; the block does not create extra replicates.
- Proposed role: not applicable. It is the frame for other metrics.
- Freeze without modification: the synthetic predicate can stay. It is not wired to a production schedule. Metric summaries inside a compatible block are not implemented.
- Warning: `production_matched_chunk_schedule_not_wired`
- The default synthetic preflight matched invocation index 1, left index 2 as B1-only, and left index 3 as D1-only. Those indexes are fixture labels, not a production schedule.

#### Production length-schedule provenance

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: the length-sampling and invocation-seed provenance that a matched B1/D1 comparison must share
- Implementation: `b1_development_pool_runner.build_schedule` builds the 1,000-attempt diagnostic schedule. Constants: `SAMPLING_SEED = 43000`, `GENERATION_SEED_BASE = 44000`, `MAX_CHUNK = 16`, `BATCH_NUM = 1`, `MAX_SEQ_LEN_OFFSET = 1`, `ATTEMPT_COUNT = 1000`. Invocation seed is `44000 + invocation_index`. The returned document's `seed_formula` string is `44000 + invocation_index`. Its `max_seq_len_formula` string is `sampled_target_length + 1`. The sampling key is `sampling_seed`.
- GEP-1 synthetic object `length_schedule_provenance` requires different strings: `seed_formula` exactly `generation_seed_base + invocation_index`, and `max_seq_len_formula` exactly `requested_target_length + 1`, plus keys `target_length_sampling_seed`, `length_vector_sha256`, `generation_seed_base`, `max_chunk_size`, and `batch_num`. `m6_diagnostic_generation.expected_static_sections` uses yet another token, `max_seq_len_rule: requested_length_plus_1`.
- Result key: none that loads a production schedule. `production_schedule_wired` is false. The conditional warning `chunk_id_namespace_unspecified` fires when the caller does not set `chunk_id_namespace` to `synthetic_stand_in_for_m4_m6_invocation_index`. The default fixture sets that namespace, so the default preflight did not emit the warning.
- Reference role: none
- Denominator and filtering: not a metric
- Direction: not applicable
- Length handling: `max_seq_len = requested_target_length + 1` in the preflight check, and `length + 1` in `build_schedule`
- Seed handling: invocation seed is not a training seed
- Proposed role: not applicable
- Freeze without modification: no. The arithmetic agrees (`44000 + invocation_index`, chunk size 16, batch number 1, max length offset 1). The serialised key names and formula strings do not. GEP-2 needs an explicit mapper. It must not treat the 1,000-attempt diagnostic schedule as the 30,000-attempt final-pool budget in section 4.1 unless a frozen production schedule says so. This audit did not open a schedule file or a pool.
- The plan's 30,000 raw attempts in total across retained D1 checkpoints is a budget sentence. `build_schedule` emits 1,000 attempts. No second schedule builder was found under `scripts/` by searching `def build_schedule`.

#### Unambiguous B2 empirical-null seed

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: the single B2 sampler seed, which is not a training replicate
- Implementation of the evaluation contract: `generator_eval_preflight._check_seed_roles` and `_one_record`. A record key named `seed` raises `ambiguous_seed_field`. B2 must carry only `empirical_null_seed`. More than one distinct B2 value raises `b2_multiple_seeds`. `assess_claim` rejects B2 as a training-replicate summary.
- Implementation of the producer: `scripts/null_model.py` `RAW_RECORD_KEYS` includes `seed`, not `empirical_null_seed`. `DEFAULT_SEED = 42`. `DEFAULT_ATTEMPT_COUNT = 30000`. The authorisation block also uses the key `seed`. `config/experiments/B2_empirical_null.yaml` `raw_record_fields` lists `seed`.
- Result keys: `b2_empirical_null_seeds`, `b2_rows_are_training_replicates` (false)
- Formula: identity of one integer. No metric is computed from it.
- Reference role: none. B2 sampling uses TRAIN-matched nucleotide probabilities in the null model. That use is not an EVAL reference and is not recomputed by this audit.
- Direction: not applicable
- Length handling: B2 length regime is `empirical_null_length_draw`. The preflight does not apply the B1/D1 schedule fields to B2.
- Seed handling: one empirical-null seed. Rows are not training replicates.
- Proposed role: not applicable
- Freeze without modification: the evaluation-record name `empirical_null_seed` can stay. The mapper from the producer field `seed` is not implemented.
- Warning: `b2_generic_seed_field_disambiguated`
- Option: section 7.5. This audit did not open `b2_empirical_null_raw.jsonl` or a manifest, so it does not assert that an accepted run's stored seed equals 42. `DEFAULT_SEED` is the source constant for an authorised production call.

#### Hashed metric-spec row before unlock

- Classification: `implemented_but_contract_needs_resolution`
- Quantity: section 5.1's requirement to hash one spec row per implemented metric, with name, data/reference, denominator, calculation, units, length and seed treatment, direction or "not applicable", role, and code/configuration revision
- Implementation: the draft spec and `validate_metric_spec`
- Result key: the spec document itself. `metric_spec_validation_status` on the default preflight was `valid_draft_with_unresolved_items`.
- Formula: structural validation, not a scientific formula
- Freeze without modification: no. The field schema matches the plan's list, with extra spec roles `accounting` and `descriptor`. Blocking items are unresolved, `freeze_status` is `draft`, and GEP-1 rejects a frozen spec.

#### No aggregate generator-quality score

- Classification: `implemented_and_freezable`
- Quantity: absence of a composite score
- Implementation: spec field `aggregate_generator_quality_score: false`. `validate_metric_spec` rejects true with `aggregate_score_forbidden`.
- Result key: `aggregate_generator_quality_score`
- Direction: not applicable
- Proposed role: not applicable
- Freeze without modification: yes

#### Replicate boundaries

- Classification: `implemented_and_freezable`
- Quantity: section 5.1's prohibition on treating 30,000 rows, B1 length seeds, the B2 seed, or generation chunks as training replicates
- Implementation: `assess_claim`, `NOT_TRAINING_REPLICATE_UNITS`, and the false flags on schedule blocks
- Result key: the claim errors `d1_unit_is_not_a_training_replicate`, `b1_length_condition_seed_is_not_a_training_replicate`, `b2_rows_are_not_training_replicates`, `b0_unit_is_not_a_training_replicate`
- Direction: not applicable
- Proposed role: not applicable
- Freeze without modification: yes

#### Discordant metrics reported as mixed

- Classification: `required_missing`
- Quantity: section 5.1 "Report discordant metrics as mixed."
- Implementation: no result key and no function assign `mixed`
- Formula: section 7.6. Discordant results among the three section 7.3 closeness metrics are reported as `mixed`. The three values stay separate. They are never combined into one score.
- Reference role: the three closeness metrics. None are implemented yet.
- Direction: not applicable. The label names disagreement. It is not itself a direction.
- Proposed role: not applicable. It is a reporting label, not a metric.
- Freeze without modification: the reporting rule is decided. The label is not implemented.
- Decision: section 7.6

#### Claim boundary against binding, affinity, selectivity, and NDM-1-specific generation

- Classification: `implemented_and_freezable`
- Quantity: the last sentence of section 5.1
- Implementation: written constraint. The spec warning `eval_closeness_not_implemented` repeats that a distributional similarity would not demonstrate binding, affinity, selectivity, inhibition, or NDM-1-specific learning. No generator function emits a binding score.
- Direction: not applicable
- Proposed role: not applicable
- Freeze without modification: yes, as a prohibition

#### Cluster-aware reference resampling

- Classification: `optional_not_implemented`
- Quantity: section 3.3's dependence note, "EVAL clusters where the frozen procedure resamples the reference"
- Implementation: no generator resampling function. `build_schedule` sets `resampling: false` for attempt retention, which is a different use of the word.
- Formula: none for the generator
- Reference role: would be EVAL clusters. Section 6.2 specifies 10,000 replicates, seed 42, and percentile intervals for Tier 1 paired effects, AUROC, and shuffle-pass rates. That sentence is not in section 5.1.
- Direction: not applicable
- Proposed role: not applicable. It would be an uncertainty procedure for a closeness or outcome metric, not itself a closeness metric.
- Freeze without modification: yes, as unused, unless review separately authorises a procedure. This audit does not copy the Tier 1 bootstrap.

#### Confidence intervals

- Classification: `optional_not_implemented`
- Quantity: a generator confidence interval, hypothesis test, or bootstrap
- Implementation: none. `_quantiles` has no interval.
- Formula: none
- Direction: not applicable
- Proposed role: not applicable
- Freeze without modification: yes, as unused. Generator uncertainty is the per-D1-training-seed values and the observed range in section 7.4. A confidence interval is not that uncertainty.
- Warning: `confidence_intervals_not_specified_in_gep1` (emitted by the default preflight)
- GEP-2 must not add a confidence interval in order to fill the range.

### 5.3 Warnings from `run_preflight`

The default synthetic preflight emitted warnings 1–16. Warnings 17–19 are implemented and were not emitted on that fixture.

| # | Warning id or text | Emitted by default preflight | Classification | Same issue as |
|---|---|---|---|---|
| 1 | `parsed_outputs_predicate_versus_successful_parse` | yes | `required_missing` for `successfully_parsed_outputs`; legacy `parsed_outputs` is `implemented_and_freezable` | section 3.1. GEP-2 adds the adapter field and does not relabel `parsed_outputs`. |
| 2 | `alias_requested_length_exact_hit_rate` | yes | `implemented_but_contract_needs_resolution` | `exact_hit_rate` |
| 3 | `alias_maximum_identity_to_train` | yes | `implemented_but_contract_needs_resolution` | `maximum_edit_similarity_to_train` |
| 4 | `alias_mfe_per_nucleotide` | yes | `implemented_but_contract_needs_resolution` | `mfe_per_nt` |
| 5 | `per_length_exact_hit_floor_not_a_decision` | yes | `implemented_but_contract_needs_resolution` | `exact_hit_rate` and `per_requested_length_exact_hit_rate` |
| 6 | `gc_fraction_not_implemented` | yes | `required_missing` | GC fraction |
| 7 | `clustering_diversity_deferred` | yes | `explicitly_deferred_by_plan` | sequence clustering and cluster summaries |
| 8 | `representation_metrics_deferred` | yes | `explicitly_deferred_by_plan` | representation metric |
| 9 | `eval_closeness_not_implemented` | yes | `required_missing` | EVAL closeness |
| 10 | `nucleotide_total_variation_membership_unresolved` | yes | `implemented_and_freezable` as nested descriptive output. The draft spec still emits the warning. | section 3.5 |
| 11 | `dinucleotide_total_variation_membership_unresolved` | yes | `implemented_and_freezable` as nested descriptive output. The draft spec still emits the warning. | section 3.5 |
| 12 | `confidence_intervals_not_specified_in_gep1` | yes | `optional_not_implemented` | confidence intervals |
| 13 | `train_reference_not_loaded_in_gep1` | yes | `implemented_and_freezable` | execution boundary for `exact_train_match_rate` and the two TRAIN edit metrics. The formulas stay. GEP-1 must continue not to load TRAIN. |
| 14 | `structure_metrics_not_executed_in_gep1` | yes | `implemented_and_freezable` | execution boundary for `mfe`, `mfe_per_nt`, and `paired_fraction`. The `mfe_per_nt` alias remains separately unresolved. |
| 15 | `production_matched_chunk_schedule_not_wired` | yes | `implemented_but_contract_needs_resolution` | production length-schedule provenance |
| 16 | `b2_generic_seed_field_disambiguated` | yes | `implemented_but_contract_needs_resolution` | B2 seed mapping |
| 17 | `chunk_id_namespace_unspecified` | no; only when `chunk_id_namespace` is omitted | `implemented_and_freezable` | synthetic stand-in warning. It does not load a production schedule. |
| 18 | `no_synthetic_records` | no; only on an empty record list | `implemented_and_freezable` | empty-input visibility. Not a scientific metric. |
| 19 | `no_valid_acgu_outputs` | no; only when rows exist and `valid_acgu` is 0 | `implemented_and_freezable` | empty-valid visibility. Not a scientific metric. |

Warning 13 is classified `implemented_and_freezable` because the scientific contract is already the existing functions plus a prohibition on loading TRAIN inside the synthetic package. Closing the warning is later execution, not a formula edit. Warning 14 is the same kind of boundary for the fold. Neither warning authorises opening TRAIN, calling ViennaRNA, or reading a pool in GEP-2A.

## 6. Schedule-string mismatch in one place

The arithmetic to preserve, if review accepts the existing diagnostic builder as the matched-schedule rule:

| Quantity | `build_schedule` | GEP-1 required provenance string or key |
|---|---|---|
| Length-sampling seed | `sampling_seed` = 43000 | key `target_length_sampling_seed` |
| Generation seed | `44000 + invocation_index` | key `generation_seed_base`, and `seed_formula` text `generation_seed_base + invocation_index` |
| Serialised seed formula | text `44000 + invocation_index` | text `generation_seed_base + invocation_index` |
| Max length | `length + 1` | check `max_seq_len == requested_target_length + 1` |
| Serialised max-length formula | text `sampled_target_length + 1` | text `requested_target_length + 1` |
| M6 design token | `requested_length_plus_1` | not accepted as the GEP-1 formula string |
| Chunk size | 16 | `max_chunk_size` 16 |
| Batch number | 1 | `batch_num` 1 |
| Attempt count | 1000 | not a GEP-1 constant. The plan's D1 budget sentence is 30,000 raw attempts in total. |

A mapper may rename keys and accept these equivalent formula strings. It may not silently treat 1,000 diagnostic attempts as the final 30,000-attempt pools.

## 7. Reviewed decisions for the future GEP-2 package

Revision 1 records the decisions below. No threshold was taken from biological observations. GEP-2 has not implemented them. This correction does not authorize loading TRAIN or EVAL.

### 7.1 GC fraction

Pooled GC fraction is `(count_G + count_C) / total canonical bases` over the same valid-row population used by `nucleotide_fractions`. Duplicate valid rows are retained. The range is `[0, 1]`. The role is descriptor. The direction is `not_applicable`.

GEP-2 adds this as its own descriptor. It calls the generator-eval-prep `composition` population. It does not call `calculate_gc_content` and it does not call `s6_profile.sequence_composition`. No GC acceptance window is added.

### 7.2 Clustering and effective diversity

Section 5.1 includes these summaries only where they already exist. They do not exist for generated sequences, and the generator config forbids inventing a threshold. GEP-2 does not call the corpus cluster builders.

The identity 0.90 and coverage 0.80 in `s5_sequence_clustering.py` remain corpus-construction parameters. `generator_evaluation.yaml` sets the generator clustering value to null. Structure clustering has no generator implementation. `shannon_diversity` and `effective_cluster_count` have names and no generator formula. GEP-2 does not introduce `exp(entropy)` or a cluster-share threshold.

`largest_duplicate_share` remains the implemented exact-string guardrail. It is an exact-string share.

### 7.3 EVAL closeness

Future synthetic-only implementations cover three metrics:

- nearest-reference normalized edit distance, using the existing longer-length normalisation in `nearest_train`;
- nucleotide total variation to the reference, using the existing `total_variation` formula `0.5 * sum(abs(left - right))` on nucleotide fractions;
- dinucleotide total variation to the reference, using that same formula on dinucleotide fractions.

Each metric is reported separately. They are never combined. Lower means closer for all three. Length handling supports the frozen S6 short/long assignment and does not invent a nucleotide cutoff.

These three become EVAL closeness metrics only after the formal unlock supplies unique EVAL cores. Until that unlock, GEP-2 exercises them on synthetic references only. Legacy TRAIN mono- and dinucleotide total variation remains the nested descriptive output in section 3.5 and does not become one of these closeness rows or a quality vote. TRAIN nearest-edit metrics remain the existing TRAIN outcome keys. A representation metric is not added. This audit does not load EVAL.

### 7.4 Per-seed range

Generator uncertainty is the per-D1-training-seed values and the observed range. It is not a confidence interval.

The implemented seed-count summary stays. GEP-2 groups each reported ledger metric, the pooled GC fraction, and the three section 7.3 closeness metrics by `training_seed`. With one D1 training seed, it keeps the limitation sentence "Uncertainty excludes training-run variability." and reports that seed's values. With two or more D1 training seeds, it reports each seed's values and the observed minimum and maximum across those seeds. Rows, chunks, invocation indexes, and length seeds are not extra seeds.

### 7.5 B2 seed mapper

The mapper is a rename at the evaluation-record boundary, not a new seed and not a metric.

- Read the integer authorisation and raw-record field `seed`.
- Store it as `empirical_null_seed`.
- Reject an evaluation record that still has a generic `seed` key.
- Require exactly one distinct value.
- Do not copy it into `training_seed`.

No new seed number is chosen here. Confirming that an accepted manifest's `seed` equals `DEFAULT_SEED` is an execution-time check on that manifest. This audit did not perform it and did not open `b2_empirical_null_raw.jsonl`.

### 7.6 Mixed closeness label

Discordant closeness results are reported as `mixed`. The three section 7.3 metrics are the closeness results that can disagree. The label is `mixed` when those reported directions of closeness disagree, and it names the separate results when they agree. The field is not a score and has no threshold. Guardrail outcomes and TRAIN novelty directions do not enter the label. The three closeness values remain separate in either case.

### 7.7 Guardrail visibility on a frozen final pool

For `valid_nonempty_acgu_fraction`, `empty_or_unparseable_fraction`, `unique_fraction`, `exact_train_match_rate`, and `largest_duplicate_share`, the formulas and the existing comparisons stay: minimum 0.99, maximum 0.01, minimum 0.95, maximum 0.01, and maximum 0.01.

A guardrail failure on a frozen final pool remains visible. It does not authorize replacement of that pool and it does not authorize exclusion after EVAL. GEP-1 does not apply the M4 checkpoint-ineligibility decision. GEP-2 must not add a post-EVAL replacement or exclusion.

### 7.8 Input validation before metric calculation

The future GEP-2 caller fails closed before metric calculation when any of the following is true:

- TRAIN is empty or contains a noncanonical core;
- a synthetic reference is empty or malformed;
- a reference role is unexpected;
- length-stratum labels are missing when a stratified result is requested.

`evaluate_hard_guardrails` already raises `train_reference_invalid` for a noncanonical core, and it does so after `summarise_attempts` has run. An empty TRAIN collection passes that type check. The GEP-2 caller therefore performs the four checks above before it calls `summarise_attempts`, `evaluate_hard_guardrails`, `report_only_diagnostics`, or a closeness calculation. A missing S6 short/long label is a failure. The caller does not invent a nucleotide cutoff to fill it.

This requirement does not authorize loading TRAIN or EVAL in GEP-2A or in this audit. Synthetic fixtures in section 11 are the inputs that exercise the closed failures.

## 8. Blockers before GEP-2 implementation

GEP-2 can call the existing M4 and M6 functions on this branch. It must not edit their formulas to resolve names, and it must import `generator-eval-prep` `m7_common.py` at content SHA-256 `ab551296da86488b4c13585af968176e5783f0fa4a1a0220621d0b9102a062a8`. The `main` copy is not a substitute. The scientific sentences in section 7 are recorded. They are not yet code. These items still block implementation:

1. `successfully_parsed_outputs` is not implemented. GEP-2 must add it as a new adapter accounting field. It must leave `parsed_outputs` as the legacy predicate that equals `raw_attempts` on a schema-valid ledger.
2. The frozen spec must still state that `exact_hit_rate` is the only exact-hit metric id and that 0.90 and 0.50 are not decisions. B0 exact-hit applicability is decided: `not_applicable`, and B0 remains a separate external panel.
3. The frozen spec must retire `maximum_identity_to_TRAIN` as a synonym and keep `maximum_edit_similarity_to_train`.
4. The frozen spec must keep `mfe_per_nt` as the only generator id and exclude AptaRank normalised MFE.
5. Pooled GC fraction, the three section 7.3 closeness metrics, the per-seed value table, the observed range, and the `mixed` label are specified and not implemented. A confidence interval must not be added as the uncertainty.
6. The caller must implement the section 7.8 fail-closed checks before any metric calculation.
7. The schedule mapper in section 6 is required before any production B1/D1 ledger is summarised as a matched schedule. The 1,000-attempt builder is not automatically the 30,000-attempt budget. Matched invocation blocks are descriptive controlled blocks, not training replicates and not significance-test units.
8. The B2 field mapper in section 7.5 is required before a production B2 record enters the evaluation contract. A generic `seed` field is rejected.
9. New synthetic fixtures under `tests/modelling/fixtures/generator_eval_gep2/` are required for the cases in section 11. The GEP-1 fixtures stay unchanged.
10. Clustering, structure clustering, effective diversity, and a representation metric stay deferred. GEP-2 must not invent their thresholds.
11. `generator_evaluation.yaml` implementation hashes are stale. They are not the freeze hashes.
12. The spec is draft. GEP-1 will reject it if GEP-2 marks it frozen before the section 7 sentences and the alias sentences are in the spec. The three closeness metrics stay synthetic-only until the formal unlock supplies unique EVAL cores.
13. Version 3.0 of the plan differs from `main`, and `m7_common.py` differs from `main`. GEP-2 must not resolve these items by copying the version 2.7 plan or the `main` copy of `m7_common.py`.

## 9. Blockers before M9A

Plan section 4.2 requires M9A to freeze generator evaluation code together with checkpoint hashes, selected seeds, generation settings, cleaning, and pools/manifests. This audit did not inspect those pools or checkpoints. From the metric contract alone, M9A is blocked by:

1. The generator metric spec is still a draft. The section 7 decisions are recorded in this audit and are not yet in frozen code. M9A's "frozen generator evaluation code" cannot be this draft.
2. `successfully_parsed_outputs`, pooled GC fraction, the three closeness metrics, per-seed values, the observed range, the `mixed` label, and the section 7.8 fail-closed checks are not implemented.
3. Production length-schedule provenance is not wired, and the serialised formula strings disagree. A pool manifest cannot yet be checked by the GEP-1 predicate. Matched blocks remain descriptive controlled blocks.
4. The B2 producer field `seed` is not mapped to `empirical_null_seed`.
5. The three closeness metrics become EVAL metrics only after the formal unlock supplies unique EVAL cores. Freezing code that still has no synthetic implementation would not answer the section 1 generator question.
6. D1 uncertainty is per-training-seed values and the observed range. Freezing a seed count without that table would not meet section 5.1's "values/range".
7. Stale hashes in `generator_evaluation.yaml` must not be copied into an M9A hash record. The `main` SHA-256 of `m7_common.py` must not be copied in its place. The freeze hash is the `generator-eval-prep` content SHA-256 `ab551296da86488b4c13585af968176e5783f0fa4a1a0220621d0b9102a062a8` until a later reviewed edit changes that file.

M9A's checkpoint, pool, and cleaning artefacts are outside this package. Their absence from this audit is not evidence that they exist or that they fail.

## 10. Blockers before M9C

Plan section 4.2 requires M9C to freeze analysis questions, metrics, and code/configuration hashes. Additional blockers at that gate:

1. Every section 7 decision and every remaining section 8 spec sentence must already be in the hashed spec. M9C is the hash gate. It is not the place to choose a closeness metric after seeing results.
2. The `mixed` label is specified for the three section 7.3 closeness metrics and is not implemented. The three values are reported separately and are never combined.
3. Generator uncertainty is the per-D1-training-seed values and the observed range. M9C must not invent a confidence interval, and must not reuse section 6.2's 10,000-replicate Tier 1 bootstrap as the generator procedure. This audit does not recommend that reuse.
4. Cluster-aware resampling of EVAL for the generator is not specified. Section 3.3 applies it only where a frozen procedure already resamples. None does.
5. Guardrail failures on a frozen final pool remain visible and do not authorize replacement or exclusion after EVAL. That section 7.7 sentence has to be in the frozen spec.
6. B0 remains a separate external panel. Exact-hit applicability for B0 is `not_applicable`. The frozen spec must not invent requested length 37 or 36.
7. The caller fail-closed checks in section 7.8 have to be in the frozen code before a stratified or reference-backed result can be hashed as the M9C procedure.
8. The governing plan hashed by the spec must remain version 3.0 at SHA-256 `e6193d0d14245049c218b4da0ef8059fb63b2f31e4885b3457cd44e41b76c50c` unless a later reviewed plan revision replaces it. The version 2.7 file on `main` is not that revision.

## 11. Proposed minimal GEP-2 implementation file list

GEP-2 is not started here. A minimal implementation that does not retune M4 or M6 formulas:

| File | Role |
|---|---|
| `config/modelling/generator_eval_metric_spec.json` | Edit when GEP-2 implements the section 7 sentences. Add `successfully_parsed_outputs` as its own accounting row. Record pooled GC, the three closeness metrics, per-seed values and range, the `mixed` label, B0 `not_applicable`, and the guardrail visibility rule. Keep legacy TRAIN total variation nested. Do not retitle `parsed_outputs` and do not add a synonym as a new `metric_id`. |
| `scripts/modelling/generator_eval_analysis.py` | New caller. It calls `summarise_attempts`, `evaluate_hard_guardrails`, `report_only_diagnostics`, `assert_pairing`, and `d1_training_seed_summary` from the `generator-eval-prep` modules, including `m7_common.py` at the section 1 HEAD hash. It adds `successfully_parsed_outputs`, pooled GC, the synthetic closeness metrics, per-seed values and the observed range, and the `mixed` label. It runs the section 7.8 checks before those calculations. It does not rewrite M4 or M6 arithmetic. |
| `scripts/modelling/generator_eval_preflight.py` | Extend only the synthetic contract checks that the accepted sentences require, such as alias rejection, B2 field rejection, and the new accounting field. Do not weaken the EVAL gate. |
| `tests/modelling/test_generator_eval_gep2.py` | New tests for the adapter, the fail-closed checks, and the fixtures below. |
| `tests/modelling/fixtures/generator_eval_gep2/` | New synthetic fixtures. Required. Do not put them in the GEP-1 directory. |
| `tests/modelling/fixtures/generator_eval_gep1/` | Leave unchanged. Do not add biological fixtures. |

New synthetic fixtures are required for:

- successful parse versus validity;
- pooled GC fraction;
- synthetic EVAL stand-in metrics;
- empty and malformed TRAIN/reference inputs;
- one and two D1 training seeds;
- per-seed values and ranges;
- compatible and incompatible matched B1/D1 blocks;
- B1-only and D1-only blocks;
- B2 generic-seed mapping and rejection;
- B0 exact-hit `not_applicable`;
- discordant closeness results reported as `mixed`.

Do not modify `m4_diagnostic_metrics.py`, `m6_diagnostic_generation.py`, `validation_metrics_v1.yaml`, or the GEP-1 fixtures in order to implement these fields. A schedule-key mapper can live in the new analysis module. Corpus clustering, AptaBase GC percent, and `s6_profile.py` are not on this list. The `main` copy of `m7_common.py` is not on this list.

## 12. Checks

Revision 1 re-ran only the commands below. `uv` was not on `PATH`. The GEP-1 tests import only the Python standard library, so they were run with `python3`. No broad test discovery was run.

- `python3 -m unittest tests.modelling.test_generator_eval_preflight -v`: 25 tests, result OK.
- `python3 scripts/modelling/generator_eval_preflight.py`: status `passed`, 16 warnings, 0 errors, metric count 30. `git_head` was `b2768e8bd8e584067558d01d2dfcad0ba6b4580c`. The text report contains no sequence strings.
- `git diff --check`: exit 0. The audit document is untracked, so this command does not see it.
- `git diff --check --no-index /dev/null docs/generator_eval_gep2a_metric_reconciliation.md`: no whitespace warnings were printed. Exit 1 is the ordinary difference status of an untracked file against `/dev/null`.

The command output is in the review archive as `test_results.txt`.

## 13. Data-access confirmation

No EVAL, REF, VALIDATION, or TRAIN data were loaded. No production generated pool, checkpoint, schedule JSON, or biological sequence row was opened, listed, hashed, or counted. Dynamic checks used the existing GEP-1 synthetic fixtures only. The untracked file `docs/aptarank_full_mres_thesis_evaluation_plan.md.backup.20261006T233303Z` was not opened. Provenance hashes used `git show` and `git hash-object` on the cited source and configuration paths. Version 2.7 of the plan was identified from the header of `git show` of `main` and was not copied into this branch. The `main` copy of `m7_common.py` was compared as source code and is archived only as labelled difference evidence.

The archive that accompanies this document is `/home/laura/generator_eval_gep2a_r1_audit_b2768e8.tar.gz`. It contains this note, the version 3.0 plan, the GEP-1 spec, preflight, and focused test, the `generator-eval-prep`/`HEAD` copies of the cited source and configuration files, the separately labelled `main` copy of `m7_common.py`, and the command records. It does not contain datasets, generated pools, checkpoints, or biological sequence records.
