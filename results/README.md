# Results guide

| Evidence | Location |
| --- | --- |
| Final thesis 50-candidate NDM-1 selection, §4.6 and Table A.13 | [Filtered selection and provenance](aptarank/evaluation/thesis_filtered_shortlist/README.md) |
| B0/B1/B2/D1 generator evaluation, §4.4 | [M10 aggregate outputs](fine_tuning/m10_generator_evaluation/m10_section5_production_v1/), [results narrative](../docs/fine_tuning/m10_generator_evaluation_results.md) |
| Overlap, leakage and reference-preparation evidence | [M9 outputs](fine_tuning/m9_generator_evaluation/) |
| AptaRank Tier 1 EVAL, §4.5 | [Corrected Evaluation-preset result](aptarank/evaluation/section6_tier1_eval_evaluation_preset_v2/) |
| Illustrative Tier 2 target cases, §4.5 | [Section 8 panel](aptarank/evaluation/section8_two_target_panel_evaluation_preset_v1/) |
| Generated-condition AptaRank comparison | [Section 9](aptarank/evaluation/section9_generated_conditions_ndm1_evaluation_preset_v1/) |
| Full 30,000-member D1 NDM-1 run | [Section 10](aptarank/evaluation/section10_d1_full_pool_ndm1_evaluation_preset_v1/) |
| Historical Tier-1-only 50-candidate hand-off | [v3.10 output](aptarank/evaluation/future_shortlisting_sequences/README.md), superseded for final thesis selection |
| Historical released-aptamer comparator (B0) | [Raw outputs and summaries](phase4_1_unadapted_rnagenesis_30k/), [identity reconciliation](../docs/fine_tuning/m2_published_aptamer_comparator_verification.md) |

Directories labelled `phase2`, `aim3_stage1` and `unadapted` retain historical
names and outputs. They are not interchangeable with the final matched generator
evaluation. In particular, the old `unadapted` label refers to the released
aptamer-adapted B0 checkpoint in the reconciled thesis terminology.

Some result families contain public aggregates and manifests while their raw
inputs remain ignored. A manifest path does not imply that the referenced input
is distributed. See [data availability](../DATA_AVAILABILITY.md) and the
[thesis guide](../docs/THESIS_GUIDE.md).
