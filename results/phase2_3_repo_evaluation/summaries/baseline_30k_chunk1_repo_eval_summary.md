# RNAGenesis repo aptamer evaluation — baseline_30k_chunk1

**Timestamp (UTC):** 2026-06-11T07:35:57.892313+00:00
**Host:** aai

## Input

- Candidate file: `/home/laura/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk10_seed4210_steps50_batch16_batchnum188_gpu1.txt`
- Raw lines: 3008
- Candidates after repo preprocessing: 3008
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
- prop_mfe (<= 2.0 kcal/mol): **37.234043%**

## Per-sequence summary stats

### Similarity
- mean: 6.188769
- min: 0.000000
- max: 64.818182

### MFE
- mean: -22.023816
- min: -34.500000
- max: -12.600000

### MFE difference
- mean: 3.211157
- min: 0.000000
- max: 11.600000

## Outputs

- JSON: `/home/laura/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/summaries/baseline_30k_chunk1_repo_eval_summary.json`
- Markdown: `/home/laura/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/summaries/baseline_30k_chunk1_repo_eval_summary.md`
- Log: `/home/laura/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/logs/baseline_30k_chunk1_repo_eval.log`
