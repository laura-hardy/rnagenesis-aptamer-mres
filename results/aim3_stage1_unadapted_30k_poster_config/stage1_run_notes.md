# Stage 1 hard filtering run notes

**Timestamp (UTC):** 2026-06-26T06:30:46.215252+00:00
**Condition:** unadapted_rnagenesis_30k
**Config:** `/Users/laura/Desktop/rnagenesis-aptamer-mres/configs/stage1_hard_filter_aptadiffA_poster.json`
**Input glob:** `results/phase4_1_unadapted_rnagenesis_30k/raw/*.txt`

## Counts

- Total sequences: 30080
- Passed Stage 1: 12337
- Failed Stage 1: 17743
- Pass rate: 41.0140%

## Options

- Reference corpus: `none`
- Limit: None
- Skip MFE: False

## Input files

- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk10_seed4210_steps50_batch16_batchnum188_gpu1.txt`
- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk1_seed4201_steps50_batch16_batchnum188_gpu1.txt`
- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk2_seed4202_steps50_batch16_batchnum188_gpu1.txt`
- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk3_seed4203_steps50_batch16_batchnum188_gpu1.txt`
- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk4_seed4204_steps50_batch16_batchnum188_gpu1.txt`
- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk5_seed4205_steps50_batch16_batchnum188_gpu1.txt`
- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk6_seed4206_steps50_batch16_batchnum188_gpu1.txt`
- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk7_seed4207_steps50_batch16_batchnum188_gpu1.txt`
- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk8_seed4208_steps50_batch16_batchnum188_gpu1.txt`
- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk9_seed4209_steps50_batch16_batchnum188_gpu1.txt`

## Filter counts

- alphabet / applied_pass: 30080 (100.0000%)
- alphabet / applied_fail: 0 (0.0000%)
- length / applied_pass: 30080 (100.0000%)
- exact_dedup / applied_pass: 30080 (100.0000%)
- exact_dedup / applied_fail: 0 (0.0000%)
- homopolymer / applied_pass: 13136 (43.6702%)
- homopolymer / applied_fail: 16944 (56.3298%)
- gc / applied_fail: 3093 (10.2826%)
- gc / applied_pass: 26987 (89.7174%)
- mfe / not_applied: 30080 (100.0000%)
- near_dedup / not_applied_reference_missing: 30080 (100.0000%)
- stage1_overall / pass: 12337 (41.0140%)
- stage1_overall / fail: 17743 (58.9860%)
