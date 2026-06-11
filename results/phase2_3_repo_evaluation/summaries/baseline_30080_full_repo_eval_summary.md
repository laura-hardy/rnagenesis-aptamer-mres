# RNAGenesis repo aptamer evaluation — baseline_30080_full

**Timestamp (UTC):** 2026-06-11T07:38:37.302606+00:00
**Host:** aai

## Input

- Candidate file: `/home/laura/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/inputs/merged_30080_raw.txt`
- Raw lines: 30080
- Candidates after repo preprocessing: 30080
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
- prop_mfe (<= 2.0 kcal/mol): **35.511968%**

## Per-sequence summary stats

### Similarity
- mean: 6.197090
- min: 0.000000
- max: 69.090909

### MFE
- mean: -21.968365
- min: -39.299999
- max: -12.280000

### MFE difference
- mean: 3.260825
- min: 0.000000
- max: 15.099998

## Outputs

- JSON: `/home/laura/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/summaries/baseline_30080_full_repo_eval_summary.json`
- Markdown: `/home/laura/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/summaries/baseline_30080_full_repo_eval_summary.md`
- Log: `/home/laura/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/logs/baseline_30080_full_repo_eval.log`
