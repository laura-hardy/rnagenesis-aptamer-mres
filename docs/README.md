# Documentation guide

Start with the [thesis guide](THESIS_GUIDE.md) to map the submitted work to code
and results. This directory also preserves execution records and earlier plans.
They document how the experiments were conducted; descriptions of proposed runs
or historical authorisation do not request a new run.

| Area | Useful entry points |
| --- | --- |
| Corpus construction | [Source preparation](data_curation/source_preparation_methodology.md), [final corpus build](data_curation/global_s7d_final_build.md), [TRAIN/VALIDATION split](data_curation/global_s7c_ft_train_validation.md) |
| Fine-tuning | [Frozen method](fine_tuning/section6_method_freeze.md), [final replicates](fine_tuning/m7_final_replicates_implementation.md), [generation](fine_tuning/m8_raw_generation.md) |
| Generator evaluation | [M10 results](fine_tuning/m10_generator_evaluation_results.md), [supervisor report](evaluation/generator_evaluation_report_supervisor.md) |
| AptaRank evaluation | [Thesis mapping](THESIS_GUIDE.md), [result index](../results/aptarank/evaluation/README.md), [historical evaluation pack](evaluation/README.md) |
| Target preparation | [NDM-1 guide](../target/README.md) |
| Environment | [Environment records and selected CPU checks](../environment/README.md) |
| Data and models | [Availability and exclusions](../DATA_AVAILABILITY.md) |

The final thesis selection is the [filtered 50-candidate set](../results/aptarank/evaluation/thesis_filtered_shortlist/README.md).
It supersedes the unfiltered v3.10 list for that purpose. Frozen plans, supervisor
materials and compatibility copies still describe earlier dispositions and are
retained unchanged because manifests and code refer to their exact paths or hashes.
