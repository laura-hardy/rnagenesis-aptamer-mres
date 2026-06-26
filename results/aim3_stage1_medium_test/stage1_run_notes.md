# Stage 1 hard filtering run notes

**Timestamp (UTC):** 2026-06-19T07:29:43.197746+00:00
**Condition:** unadapted_medium_test
**Config:** `/Users/laura/Desktop/rnagenesis-aptamer-mres/configs/stage1_hard_filter_default.json`
**Input glob:** `results/phase2_medium_test/*.txt`

## Counts

- Total sequences: 16
- Passed Stage 1: 6
- Failed Stage 1: 10
- Pass rate: 37.5000%

## Options

- Reference corpus: `none`
- Limit: None
- Skip MFE: False

## Input files

- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/phase2_medium_test/seqs_wo_guidance_top_p=0.95_2_16_medium_test_seed42_steps50_batch16.txt`

## Filter counts

- alphabet / applied_pass: 16 (100.0000%)
- alphabet / applied_fail: 0 (0.0000%)
- length / not_applied: 16 (100.0000%)
- exact_dedup / applied_pass: 16 (100.0000%)
- exact_dedup / applied_fail: 0 (0.0000%)
- homopolymer / applied_pass: 6 (37.5000%)
- homopolymer / applied_fail: 10 (62.5000%)
- gc / not_applied: 16 (100.0000%)
- mfe / not_applied: 16 (100.0000%)
- near_dedup / not_applied_reference_missing: 16 (100.0000%)
- stage1_overall / pass: 6 (37.5000%)
- stage1_overall / fail: 10 (62.5000%)
