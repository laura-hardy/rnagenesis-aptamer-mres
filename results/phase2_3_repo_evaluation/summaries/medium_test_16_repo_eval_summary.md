# RNAGenesis repo aptamer evaluation — medium_test_16

**Timestamp (UTC):** 2026-06-11T07:35:41.829113+00:00
**Host:** aai

## Input

- Candidate file: `/home/laura/rnagenesis-aptamer-mres/results/phase2_medium_test/seqs_wo_guidance_top_p=0.95_2_16_medium_test_seed42_steps50_batch16.txt`
- Raw lines: 16
- Candidates after repo preprocessing: 16
- RNAGenesis repo: `/home/laura/RNAGenesis`
- RNAGenesis commit: `d00899e`

## Parameters

- threshold_a: 80.0
- threshold_b: 2.0
- factor: 2.0

## Reference

- Sequence: `TCCAGCACTCCACGCATAACGGCGGTGGGTGGGTTGTTGTGGGAGGGGGAGGGGGAGTTATGCGTGCTACCGTGAA`
- MFE: -24.200001 kcal/mol
- Structure: `.((..(.((((.(.(((((((((.........))))))))).).)))))..))(((((.......))).)).....`

## Aggregate metrics

- prop_similarity (>= 80.0): **0.000000%**
- prop_mfe (<= 2.0 kcal/mol): **25.000000%**

## Per-sequence summary stats

### Similarity
- mean: 7.318182
- min: 4.000000
- max: 17.545455

### MFE
- mean: -20.887500
- min: -26.400000
- max: -16.500000

### MFE difference
- mean: 3.587501
- min: 0.700001
- max: 7.700001

## Outputs

- JSON: `/home/laura/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/summaries/medium_test_16_repo_eval_summary.json`
- Markdown: `/home/laura/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/summaries/medium_test_16_repo_eval_summary.md`
- Log: `/home/laura/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/logs/medium_test_16_repo_eval.log`
- Per-sequence CSV: `/home/laura/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/per_sequence/medium_test_16_repo_eval_per_sequence.csv`
