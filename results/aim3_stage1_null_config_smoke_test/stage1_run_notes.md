# Stage 1 hard filtering run notes

**Timestamp (UTC):** 2026-06-26T06:21:39.433969+00:00
**Condition:** null_model_smoke_config_check
**Config:** `/Users/laura/Desktop/rnagenesis-aptamer-mres/configs/stage1_hard_filter_aptadiffA_poster.json`
**Input glob:** `results/null_model_30k/null_sequences.txt`

## Counts

- Total sequences: 100
- Passed Stage 1: 39
- Failed Stage 1: 61
- Pass rate: 39.0000%

## Options

- Reference corpus: `none`
- Limit: 100
- Skip MFE: True

## Input files

- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/null_model_30k/null_sequences.txt`

## Filter counts

- alphabet / applied_pass: 100 (100.0000%)
- alphabet / applied_fail: 0 (0.0000%)
- length / applied_pass: 100 (100.0000%)
- exact_dedup / applied_pass: 100 (100.0000%)
- exact_dedup / applied_fail: 0 (0.0000%)
- homopolymer / applied_pass: 41 (41.0000%)
- homopolymer / applied_fail: 59 (59.0000%)
- gc / applied_fail: 6 (6.0000%)
- gc / applied_pass: 94 (94.0000%)
- mfe / skipped: 100 (100.0000%)
- near_dedup / not_applied_reference_missing: 100 (100.0000%)
- stage1_overall / pass: 39 (39.0000%)
- stage1_overall / fail: 61 (61.0000%)
