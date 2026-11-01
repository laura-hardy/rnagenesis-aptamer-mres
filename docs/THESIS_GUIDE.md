# Thesis companion guide

Companion to Laura Hardy's *Towards Prediction-Guided Generative Design of RNA
Aptamers*, Master of Research, Macquarie University, November 2026. Section and
printed-page references below follow the supplied examiner-copy PDF. The thesis
and full personal bibliography are not redistributed in this repository.

## Evidence map

| Thesis section | Repository evidence | Implementation |
| --- | --- | --- |
| §§3.2, 4.1: survey of 45 models | Background and motivation are in the thesis; this repository focuses on the computational case study | No survey rerun is claimed |
| §3.3.1: baseline reproduction | [Released-model validation](fine_tuning/m1_released_inference_validation.md), [B0 comparator identity](fine_tuning/m2_published_aptamer_comparator_verification.md) | [Baseline launcher](../scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh) |
| §3.3.2: NDM-1 target preparation | [Target guide](../target/README.md), PDB 5ZGX chain A and fpocket 4 artifacts | [Target preparation](../target/prepare_ndm1_target.py) |
| §§3.3.3, 4.2: corpus curation | [Source preparation](data_curation/source_preparation_methodology.md), [final build](data_curation/global_s7d_final_build.md), [split](data_curation/global_s7c_ft_train_validation.md) | [Curation scripts](../scripts/data_preparation/), [source configuration](../config/global_s4_sources/) |
| §§3.3.4, 4.3: adaptation | [Frozen method](fine_tuning/section6_method_freeze.md), [replicate outcomes](fine_tuning/m7_final_replicates_implementation.md) | [MRes replicate runner](../scripts/modelling/m7_replicate_runner.py), [experiment configuration](../config/experiments/D1_final_replicates.yaml), [pinned training implementation](https://github.com/laura-hardy/RNAGenesis/blob/e3b855bbf4d1af376f43747643fa30afd662828c/train_diffusion_mres.py) |
| §4.4: B0/B1/B2/D1 generator evaluation | [M10 results](fine_tuning/m10_generator_evaluation_results.md), [aggregate outputs](../results/fine_tuning/m10_generator_evaluation/m10_section5_production_v1/) | [M10 analysis](../scripts/modelling/generator_eval_m10.py), [null model](../scripts/null_model.py) |
| §§3.4, 4.5: AptaRank framework and evaluation | [Tier 1 EVAL result](../results/aptarank/evaluation/section6_tier1_eval_evaluation_preset_v2/), [Section 8 target panel](../results/aptarank/evaluation/section8_two_target_panel_evaluation_preset_v1/), [Section 9 condition comparison](../results/aptarank/evaluation/section9_generated_conditions_ndm1_evaluation_preset_v1/) | [Evaluation scripts](../scripts/modelling/), [separate AptaRank application](https://github.com/alishahsvnd/AptaRank) |
| §4.6 and Table A.13, pp. 110–111: NDM-1 application | [Closed full-pool analysis](../results/aptarank/evaluation/section10_d1_full_pool_ndm1_evaluation_preset_v1/), [final filtered 50](../results/aptarank/evaluation/thesis_filtered_shortlist/README.md) | [Original Section 10 analysis](../scripts/modelling/aptarank_section10_analyze_and_build_review_pool.py); final selection uses frozen outputs |

## Corpus and comparison identities

The final corpus has 1,170 identities, 1,031 unique core sequences, 790 clusters
and 409 targets. Identity counts by role are TRAIN 726, VALIDATION 132, REF 131
and EVAL 181. Roles are separated by sequence cluster; the full sequence corpus
is withheld because redistribution terms differ by source. See
[data availability](../DATA_AVAILABILITY.md).

B0 is the released aptamer-adapted comparator. Historical directories containing
`unadapted` predate this checkpoint-identity reconciliation and retain their names.
B1 is the released generic model; D1 adapts that generic model using the MRes
corpus; B2 draws independent bases using TRAIN-derived length and nucleotide
frequencies. B0 is descriptive, whereas B1/B2/D1 use the matched protocol.

The two D1 training replicates are seeds 43 and 44, each selected at epoch 5,
update 105. A technical generation block is not an independent training replicate.
Thirty thousand attempts are assessed for each matched condition, with D1 split
15,000 per replicate. D1 has 30,000 distinct sequences; B1 has 29,983 distinct
sequences from 30,000 attempts. These numbers have different denominators from
the 29,583 D1 candidates successfully scored in the later AptaRank full-pool run.

## Which 50-candidate list is final?

The repository owner's confirmed choice for the public companion is the thesis's
filtered selection, not the later unfiltered v3.10 hand-off. The final directory
is [thesis_filtered_shortlist](../results/aptarank/evaluation/thesis_filtered_shortlist/README.md).
It contains the first 50 of 137 candidates passing shuffle and moderate/strong
compatibility gates, ordered by frozen Tier 1 rank within the exact Tier 2 top
1,000. Every Table A.13 row was checked, including sequence, ID, length, rank,
seed/block and rounded Tier 1 score. The first three sequences also match
Figure 4.13.

The earlier [v3.10 set](../results/aptarank/evaluation/future_shortlisting_sequences/README.md)
and hash-bound [supervisor pack](evaluation/README.md) remain historical records.
Their references to a final Tier-1-only list are superseded for the submitted
thesis selection. The [decision record](../results/aptarank/evaluation/thesis_filtered_shortlist/selection_decision.json)
records this reconciliation without rewriting earlier results or rerunning AptaRank.

## Interpretation and reproducibility limits

D1's distributional improvement over B1 does not outperform the empirical B2
null. Tier 1's paired median gain is 0.108 (bootstrap 95% interval 0.064–0.164),
with AUROC 0.638 over 153 pairs. Tier 2 results are weak to mixed. The NDM-1 pocket
also carries a geometric warning: robust extent and equivalent-sphere diameter
differ by more than 2×, while the comparison assumes a roughly convex cavity.
None of these analyses establishes binding, affinity, specificity or inhibition.

[Environment guidance](../environment/README.md) separates selected CPU checks
from a full GPU rerun. Original inputs, adapted checkpoints and external tools
have separate availability and licensing conditions. Existing source paths,
scientific outputs and checksum-bound records are preserved; the new final-list
artifacts are an additional, explicitly documented selection of frozen evidence.
