# RNAGenesis repo aptamer evaluation — baseline_30k_chunk1

**Timestamp (UTC):** 2026-06-11T08:01:03.204984+00:00
**Host:** Gerald.local

## Input

- Candidate file: `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk1_seed4201_steps50_batch16_batchnum188_gpu1.txt`
- Raw lines: 3008
- Candidates after repo preprocessing: 3008
- RNAGenesis repo: `/Users/laura/Desktop/RNAGenesis`
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
- prop_mfe (<= 2.0 kcal/mol): **34.607713%**

## Per-sequence summary stats

### Similarity
- mean: 6.096682
- min: 0.000000
- max: 60.545455

### MFE
- mean: -21.908677
- min: -38.099998
- max: -13.200000

### MFE difference
- mean: 3.279887
- min: 0.000000
- max: 13.899998

## Outputs

- JSON: `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/summaries/baseline_30k_chunk1_repo_eval_summary.json`
- Markdown: `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/summaries/baseline_30k_chunk1_repo_eval_summary.md`
- Log: `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/logs/baseline_30k_chunk1_repo_eval.log`
