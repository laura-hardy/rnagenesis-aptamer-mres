# Stage 1 hard filtering run notes

**Timestamp (UTC):** 2026-06-26T06:46:07.326586+00:00
**Condition:** null_model_30k_mfe_filter
**Config:** `/Users/laura/Desktop/rnagenesis-aptamer-mres/configs/stage1_hard_filter_aptadiffA_poster_with_mfe.json`
**Input glob:** `results/null_model_30k/null_sequences.txt`

## Counts

- Total sequences: 30000
- Passed Stage 1: 12602
- Failed Stage 1: 17398
- Pass rate: 42.0067%

## Options

- Reference corpus: `none`
- Limit: None
- Skip MFE: False

## Input files

- `/Users/laura/Desktop/rnagenesis-aptamer-mres/results/null_model_30k/null_sequences.txt`

## Filter counts

- alphabet / applied_pass: 30000 (100.0000%)
- alphabet / applied_fail: 0 (0.0000%)
- length / applied_pass: 30000 (100.0000%)
- exact_dedup / applied_pass: 30000 (100.0000%)
- exact_dedup / applied_fail: 0 (0.0000%)
- homopolymer / applied_pass: 13318 (44.3933%)
- homopolymer / applied_fail: 16682 (55.6067%)
- gc / applied_fail: 2802 (9.3400%)
- gc / applied_pass: 27198 (90.6600%)
- mfe / applied_pass: 30000 (100.0000%)
- near_dedup / not_applied_reference_missing: 30000 (100.0000%)
- stage1_overall / pass: 12602 (42.0067%)
- stage1_overall / fail: 17398 (57.9933%)
