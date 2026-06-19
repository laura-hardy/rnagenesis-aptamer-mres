# Stage 1 hard filtering

Stage 1 implements binary hard filtering for intrinsic RNA sequence quality on
RNAGenesis-style raw `.txt` outputs.

## Run

From the repository root, using the Mac conda environment:

```bash
/Users/laura/anaconda3/envs/rnagenesis-mac/bin/python scripts/run_stage1_hard_filter.py \
  --input-glob "results/phase2_medium_test/*.txt" \
  --condition unadapted_medium_test \
  --output-dir results/aim3_stage1_medium_test \
  --config configs/stage1_hard_filter_default.json
```

Large reference-free baseline:

```bash
/Users/laura/anaconda3/envs/rnagenesis-mac/bin/python scripts/run_stage1_hard_filter.py \
  --input-glob "results/phase4_1_unadapted_rnagenesis_30k/raw/*.txt" \
  --condition unadapted_rnagenesis_30k \
  --output-dir results/aim3_stage1_unadapted_30k \
  --config configs/stage1_hard_filter_default.json
```

## Default config behaviour

With `configs/stage1_hard_filter_default.json`:

- Strips leading `11` when present
- Enforces RNA alphabet (A/U/C/G)
- Enforces exact within-condition deduplication (keeps first occurrence)
- Fails homopolymer runs of length >= 5
- Computes GC and MFE metrics but does **not** filter on length, GC, or MFE
  until bounds/thresholds are supplied in config
- Skips near-deduplication unless `--reference-corpus` is provided

## Outputs

For each run, the output directory contains:

- `stage1_all_sequences.csv`
- `stage1_passed_sequences.csv`
- `stage1_failed_sequences.csv`
- `stage1_summary.json`
- `stage1_filter_counts.csv`
- `stage1_run_notes.md`
- `stage1_passed_sequences.fasta` (when passes exist)

## Tests

```bash
/Users/laura/anaconda3/envs/rnagenesis-mac/bin/python -m pytest tests/test_stage1_hard_filter.py -q
```

## Notes

- Stage 1 is not ranking and does not claim binding evidence.
- Reference-corpus-calibrated length/GC/MFE thresholds require AptaDiff or another
  training corpus; until then those filters remain `not_applied`.
- Near-deduplication requires `rapidfuzz` or `python-Levenshtein` when a reference
  corpus is supplied.

> On the unadapted 30k baseline using the default Stage 1 config, the pass rate was 43.7% (13,136/30,080). All failures were caused by homopolymer runs ≥5; alphabet validity, exact deduplication, and reference-dependent filters removed no sequences. Long G-rich runs dominated the failures, suggesting this is a characteristic of the unadapted RNAGenesis output rather than a preprocessing artefact. The homopolymer threshold should be revisited once the reference aptamer corpus is available, but the current default is retained as a conservative intrinsic-quality filter.
