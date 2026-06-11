# Aim 1 — RNAGenesis repository reproduction: aptamer generation and evaluation

## Purpose

We reimplemented the RNAGenesis aptamer generation procedure without guidance, generated 30,000 sequences, then reproduced the RNAGenesis repository-provided aptamer evaluation procedure on the generated aptamer outputs, rather than applying a new project-specific metric suite. The goal was faithful reproduction of upstream `test_wrap_aptamer.py` behaviour on medium-test, single-chunk, and full baseline pools.

## Inputs

- **medium_test_16** — medium-test RNAGenesis output with 16 sequences.
- **baseline_30k_chunk1** — one 30k baseline chunk with 3,008 sequences
(`seqs_wo_guidance_*.txt` from the unadapted baseline run).
- **baseline_30080_full** — full merged unadapted baseline pool with 30,080 sequences
(`inputs/merged_30080_raw.txt`).
- Raw `seqs_wo_guidance_*.txt` files were used to preserve repository-faithful
preprocessing (including raw token handling quirks).

## Repository evaluation procedure

- **Evaluation script:** RNAGenesis `test_wrap_aptamer.py` (`batch_analysis`,
`threshold_analysis`, `run_rna_analysis`).
- **Project wrapper:** `scripts/run_repo_aptamer_evaluation.py`.
- The original repository CLI calls `run_rna_analysis()` but does not print returned
metrics; the project wrapper exposes those metrics and verifies consistency with
`run_rna_analysis()`.
- **Reference aptamer sequence:** `TCCAGCACTCCACGCATAACGGCGGTGGGTGGGTTGTTGTGGGAGGGGGAGGGGGAGTTATGCGTGCTACCGTGAA`
- **Reference MFE:** -24.200001 kcal/mol
- **Reference structure:** `.((..(.((((.(.(((((((((.........))))))))).).)))))..))(((((.......))).)).....`

## Metrics reproduced

The repository evaluation computes only:

- secondary-structure similarity to the hard-coded reference aptamer;
- per-sequence minimum free energy (MFE);
- MFE difference from the reference aptamer;
- percentage passing the structure-similarity threshold (`prop_similarity`);
- percentage passing the MFE-difference threshold (`prop_mfe`).

Where per-sequence CSVs were saved, mean/min/max summary statistics are also reported.
Project-specific metrics (GC content, uniqueness, validity, normalised MFE, ensemble
defect, diversity) are **not** part of this repository procedure and are deferred to a
later stage.

## Results

### Threshold pass rates by run


| Run                 | n     | prop_similarity | prop_mfe   |
| ------------------- | ----- | --------------- | ---------- |
| medium_test_16      | 16    | 0.000000%       | 25.000000% |
| baseline_30k_chunk1 | 3008  | 0.000000%       | 34.607713% |
| baseline_30080_full | 30080 | 0.000000%       | 35.511968% |


### Full baseline (baseline_30080_full) summary statistics


| Metric                    | mean       | min        | max        |
| ------------------------- | ---------- | ---------- | ---------- |
| Similarity                | 6.197090   | 0.000000   | 69.090909  |
| MFE (kcal/mol)            | -21.968365 | -39.299999 | -12.280000 |
| MFE difference (kcal/mol) | 3.260825   | 0.000000   | 15.099998  |


## Interpretation

- The unadapted baseline produced **no** candidates meeting the repository's high
structure-similarity threshold of 80 (`prop_similarity = 0%` across all runs).
- About **one third** of candidates met the MFE-difference threshold of 2 kcal/mol
(`prop_mfe` ≈ 25–37% depending on subset).
- This is plausible for an unadapted/unguided baseline because generation was not
target-conditioned or explicitly optimised for the hard-coded reference aptamer fold.
- These results reproduce repository-style evaluation but do not yet answer all
project-specific baseline-characterisation questions.

## Limitations

- Repository evaluation does **not** compute validity, uniqueness, GC content,
normalised MFE, ensemble defect, or diversity.
- Repository preprocessing has quirks (including raw token handling); this report
intentionally preserves those quirks for faithful reproduction.
- Full project-specific baseline evaluation is deferred to a later stage.

## Sequence length

The unadapted RNAGenesis baseline was generated using the repository aptamer-generation setting --max_seq_len 37, so the raw generated outputs have a fixed sequence length. This should be treated as a generation-configuration artefact rather than an emergent property of the model or a biologically inferred aptamer length distribution. Later project-specific evaluation will separately clean model tokens and characterise the resulting variable-region lengths.

Something I wil consider is whether to make the generation conditions fairer across models; if the length should be sampled instead from the fine-tuning data set length distribution, or whether it is better practice to faithfully re-implement the repository.

## Per-sequence data availability

Full per-sequence CSV was saved only for `medium_test_16` unless additional per-sequence files are present under `per_sequence/`.

## Generated figures

- `plots/threshold_pass_rates.png` — Threshold pass rates across runs
- `plots/full_baseline_metric_ranges.png` — Full baseline mean/min/max for similarity, MFE, and MFE difference
- `plots/raw_sequence_length_distribution.png` — Histogram of raw baseline line lengths
- `plots/medium_test_16_similarity_histogram.png` — Per-sequence similarity histogram (medium_test_16)
- `plots/medium_test_16_mfe_histogram.png` — Per-sequence mfe histogram (medium_test_16)
- `plots/medium_test_16_mfe_diff_histogram.png` — Per-sequence mfe_diff histogram (medium_test_16)

## Next steps

- Curate fine-tuning data set.
- Generate null model (random RNA sampled based on empirical properties of fine-tuning data set).
- Compare null model and unadapted RNAGenesis using initial stages of project filtering and ranking pipeline. 

