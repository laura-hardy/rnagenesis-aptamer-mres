# RNAGenesis repo evaluation investigation (Stage 2.3)

**Date:** 2026-06-11  
**Purpose:** Identify the repository-provided aptamer evaluation procedure before running it on project-generated sequences. Investigation only — no custom metrics pipeline, no RNAGenesis source changes, no full 30k run yet.

**Repos inspected:**

| Repo | Path |
|---|---|
| RNAGenesis | `~/RNAGenesis` |
| Project | `~/rnagenesis-aptamer-mres` |

**Generated sequences target (later):** `results/phase4_1_unadapted_rnagenesis_30k/raw/` — 10 chunk files × 3,008 sequences = 30,080 total.

---

## 1. Identified evaluation scripts

| File | Purpose | Aptamer-specific? | Runnable as CLI? | Helper / value function? | Output behaviour |
|---|---|---|---|---|---|
| `~/RNAGenesis/test_wrap_aptamer.py` | Post-hoc secondary-structure evaluation of generated aptamer candidates vs a hard-coded reference aptamer. Computes per-sequence MFE, structure similarity, MFE difference; aggregates threshold pass rates. | **Yes** | **Yes** (`python test_wrap_aptamer.py --candidate_seqs_path …`) | Both: `run_rna_analysis()` for batch eval; `similarity_value_function`, `mfe_value_function`, `combine_value_function` imported by `generation.py` for beam-search guidance during generation | **Returns metrics silently.** `run_rna_analysis` returns `(prop_similarity, prop_mfe)`. Per-sequence fields are in the `results` list inside `batch_analysis` but are not printed because `print_analysis()` is commented out in `run_rna_analysis`. The CLI calls `run_rna_analysis` without printing its return value → **no stdout**. |
| `~/RNAGenesis/test_wrap_sgrna.py` | Same evaluation pattern for **sgRNA** design (different flanking suffix, different reference sequence). | No (sgRNA) | Yes | Same dual role as aptamer file | Same silent-return CLI behaviour |
| `~/RNAGenesis/generation.py` | Generation pipeline; imports aptamer value functions for `--search_general` beam search (`similarity`, `mfe`, `combine` goals). | Used for aptamer generation guidance, **not** post-hoc evaluation of saved outputs | Yes (generation, not evaluation) | Value functions are helpers for in-loop scoring | Prints generation progress; value scores used internally during search, not written as evaluation report |
| `~/RNAGenesis/struct_pred/eval.py` | 3D structure-prediction metrics (distance/contact accuracy). | No | Yes (within struct_pred workflow) | Evaluation module for struct_pred | Prints/returns struct_pred metrics — unrelated to aptamer secondary-structure eval |
| `~/RNAGenesis/README.md` | Documents installation and **generation** commands only. | Aptamer generation mentioned | N/A | N/A | **Does not document** `test_wrap_aptamer.py` or any aptamer evaluation step |

**Conclusion:** The only aptamer-specific, repo-provided post-generation evaluation code is `test_wrap_aptamer.py`.

---

## 2. Evaluation entry point

### Correct entry point

**Script:** `~/RNAGenesis/test_wrap_aptamer.py`  
**Primary function:** `run_rna_analysis(candidate_seqs_path, threshold_A=80.0, threshold_B=2.0, factor=2.0)`  
**Returns:** `(prop_similarity, prop_mfe)` — percentages (0–100) of sequences passing thresholds A and B.

### Supporting functions (importable)

| Function | Role | Returns |
|---|---|---|
| `get_gen_seqs(path)` | Read + preprocess raw generation file | `list[str]` full-length candidate sequences |
| `batch_analysis(candidate_seqs, ref_seq, factor=2.0)` | Fold all candidates + reference | `(ref_structure, ref_mfe, results)` where each result dict has `seq`, `structure`, `mfe`, `similarity`, `mfe_diff` |
| `threshold_analysis(results, threshold_A, threshold_B)` | Aggregate pass rates | `(prop_similarity, prop_mfe)` |
| `print_analysis(...)` | Human-readable report | prints to stdout (available but disabled in `run_rna_analysis`) |
| `similarity_value_function(seqs, factor=5.0)` | Beam-search guidance only | list of similarity scores |
| `mfe_value_function(seqs, factor=5.0)` | Beam-search guidance only | list of negated MFE diffs |
| `combine_value_function(seqs, factor=5.0)` | Beam-search guidance only | list of `similarity + mfe/ref_mfe` |

### CLI arguments

```
python test_wrap_aptamer.py \
  --candidate_seqs_path PATH \
  [--threshold_A 80.0] \
  [--threshold_B 2.0] \
  [--factor 2.0]
```

### Example command (one project chunk file)

Run from `~/RNAGenesis` with `rnagenesis-h200` active:

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate rnagenesis-h200
cd ~/RNAGenesis

python test_wrap_aptamer.py \
  --candidate_seqs_path ~/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk1_seed4201_steps50_batch16_batchnum188_gpu1.txt \
  --threshold_A 80.0 \
  --threshold_B 2.0 \
  --factor 2.0
```

**Expected CLI behaviour today:** completes with **no printed output**. To see results, import and print the return value (wrapper recommended — see §8).

**Smoke-test result (chunk 1, 3,008 sequences, defaults):** `(0.0, 34.61)` — 0% pass similarity ≥ 80; ~34.6% pass MFE difference ≤ 2 kcal/mol. Elapsed ~8 s on H200 CPU.

Smaller test file already in project repo:

```bash
python test_wrap_aptamer.py \
  --candidate_seqs_path ~/rnagenesis-aptamer-mres/results/phase2_medium_test/seqs_wo_guidance_top_p=0.95_2_16_medium_test_seed42_steps50_batch16.txt
```

---

## 3. Metrics actually computed by the repo

### Per-sequence metrics (`batch_analysis` → `results` list)

| Metric | Code location | What it measures | Exposed how |
|---|---|---|---|
| **Secondary-structure similarity** | `compute_similarity()` in `test_wrap_aptamer.py` | Score 0–100: average of (a) base-pair overlap fraction × 100 and (b) `max(0, 100 - RNA.bp_distance × factor)`. Uses ViennaRNA dot-bracket structures. | Returned in each `results[i]['similarity']`; **not printed** by default CLI |
| **MFE** | `compute_structure()` → `RNA.fold(seq)` | Minimum free energy (kcal/mol) of candidate full sequence (with flanks) | `results[i]['mfe']`; not printed by default |
| **MFE difference from reference** | `batch_analysis`: `abs(mfe - ref_mfe)` | Absolute MFE gap vs reference aptamer fold | `results[i]['mfe_diff']`; not printed by default |
| **Predicted structure** | `compute_structure()` | ViennaRNA MFE dot-bracket | `results[i]['structure']`; not printed by default |

### Aggregate metrics (`threshold_analysis` / `run_rna_analysis`)

| Metric | Code location | What it measures | Exposed how |
|---|---|---|---|
| **Threshold A proportion (similarity)** | `threshold_analysis` | % of sequences with `similarity >= threshold_A` (default 80) | Returned by `run_rna_analysis`; would be printed by `print_analysis` if uncommented |
| **Threshold B proportion (MFE diff)** | `threshold_analysis` | % of sequences with `mfe_diff <= threshold_B` (default 2.0 kcal/mol) | Same as above |

### Beam-search-only metrics (not used in `run_rna_analysis`)

| Metric | Function | Notes |
|---|---|---|
| Per-seq similarity | `similarity_value_function` | Same similarity formula but **`factor=5.0` default** (not 2.0) |
| Negated MFE diff | `mfe_value_function` | Returns `-abs(mfe - ref_mfe)` for maximization during search |
| Combined score | `combine_value_function` | `similarity + mfe / ref_mfe` (uses raw candidate MFE, not diff) |

### Explicitly **not** computed by repo aptamer evaluation

| Metric | Present? |
|---|---|
| GC content | **No** |
| Validity / alphabet checks | **No** |
| Uniqueness / deduplication | **No** |
| Normalised MFE (e.g. MFE/length) | **No** (except incidentally in `combine_value_function` for beam search) |
| Ensemble defect | **No** |
| Sequence identity to reference | **No** |
| Base-pair distance alone (without combining) | Used internally only |

---

## 4. Input format expected

### Raw RNAGenesis output lines

**Yes.** `get_gen_seqs()` reads a plain text file, one sequence per line, matching files written by `generation.py`:

```
seqs_wo_guidance_{sample_strategy}_{eos_token}_{count}{remark}.txt
```

Project examples:

```
seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk1_seed4201_steps50_batch16_batchnum188_gpu1.txt
seqs_wo_guidance_top_p=0.95_2_16_medium_test_seed42_steps50_batch16.txt
```

Typical raw line (38 characters):

```
11CUGGCGGUUUGGUCAUUCUGGGGGCUUGGGGGUCUG
```

### Preprocessing steps (in order, per line)

1. **EOS removal:** if `'2' in line`, replace **all** occurrences of `'2'` with `''` (global, not token-aware).
2. **BOS strip:** `line.strip()[1:]` — removes **only the first character** (intended BOS token `1`).
3. **Flank insertion:** prepend `TCCAGCACTCCACGCATAAC`, append `GTTATGCGTGCTACCGTGAA`.

**Does not** use project cleaning script logic (`strip leading "11"`).

### Observed effect on current project outputs

| Stage | Length / content |
|---|---|
| Raw line | 38 chars; starts with `11`; **no** literal `2` in inspected 30k/raw files |
| After `[1:]` | 37 chars; variable region starts with `1` + 36 RNA letters (decoder token artefact, not A/U/C/G) |
| After flanks | 77 chars total (20 + 37 + 20) |
| Reference full sequence | 76 chars (20 + **36** + 20) |

The repo evaluation therefore folds sequences **one nucleotide longer** than the reference aptamer, with a leading digit `1` in the variable region. ViennaRNA accepts the `1` character and folds it (verified: MFE changes vs sequence without the `1`).

### Alphabet

- **Generated variable region:** RNA letters `A/U/C/G` (uppercase in files).
- **Flanking regions:** DNA-style `T` (ViennaRNA treats `T` ≡ `U`; verified identical structure/MFE for reference).
- **Not expected:** FASTA headers, CSV, or cleaned project outputs unless re-wrapped into raw line format.

### Variable-region length

- Generation uses `--max_seq_len 37` (aptamer README / project scripts).
- Raw file line length 38 = BOS `1` + 37 generated characters (EOS `2` not present in saved lines).
- After repo preprocessing, variable region is **37 characters** including the leading `1` token.

### Multi-file input

**One file at a time.** No batch directory support. For 30,080 sequences: run per chunk, merge files externally, or call `run_rna_analysis` / `batch_analysis` from a wrapper.

---

## 5. Reference aptamer

### Full reference sequence (hard-coded in `test_wrap_aptamer.py`)

```
TCCAGCACTCCACGCATAACGGCGGTGGGTGGGTTGTTGTGGGAGGGGGAGGGGGAGTTATGCGTGCTACCGTGAA
```

| Component | Sequence | Length |
|---|---|---|
| **Prefix (fixed)** | `TCCAGCACTCCACGCATAAC` | 20 |
| **Variable / core region** | `GGCGGTGGGTGGGTTGTTGTGGGAGGGGGAGGGGGAG` | 36 |
| **Suffix (fixed)** | `GTTATGCGTGCTACCGTGAA` | 20 |
| **Full** | (concatenation above) | 76 |

Same sequence is repeated in `run_rna_analysis`, `similarity_value_function`, `mfe_value_function`, and `combine_value_function`.

### Reference structure calculation

```python
structure, mfe = RNA.fold(ref_seq)
```

ViennaRNA MFE folding (same as candidates). No constrained folding, no partition function, no ensemble defect.

**Reference values (verified in `rnagenesis-h200`):**

| Quantity | Value |
|---|---|
| MFE | **−24.20 kcal/mol** |
| Structure | `.((..(.((((.(.(((((((((.........))))))))).).)))))..))(((((.......))).)).....` |

### Default thresholds and factors

| Parameter | `run_rna_analysis` / CLI default | Value-function default (beam search) |
|---|---|---|
| `threshold_A` (similarity ≥) | 80.0 (out of 100) | N/A |
| `threshold_B` (MFE diff ≤) | 2.0 kcal/mol | N/A |
| `factor` (bp_distance scaling) | **2.0** | **5.0** |

---

## 6. Dependencies

### Python imports in `test_wrap_aptamer.py`

| Package | Purpose |
|---|---|
| `RNA` | ViennaRNA Python bindings (`RNA.fold`, `RNA.bp_distance`) |
| `numpy` | Imported but **unused** in current file |
| `argparse` | CLI |

### Status in `rnagenesis-h200`

Verified 2026-06-11:

```bash
conda activate rnagenesis-h200
python -c "import RNA; import numpy; print('RNA', RNA.__version__); print('numpy', numpy.__version__)"
# RNA 2.7.0
# numpy 1.22.0
```

| Dependency | In `environment/environment_h200.yml`? | Install needed? |
|---|---|---|
| ViennaRNA (`viennarna=2.7.0`) | Yes (bioconda) | **No** |
| numpy | Yes | **No** |
| torch / GPU stack | Yes | **Not required for evaluation** |

### Compute requirements

- **GPU:** not required. Evaluation is CPU-only ViennaRNA folding.
- **ViennaRNA / `import RNA`:** **required**.
- **Rough runtime (H200 CPU):** ~0.003 s/sequence → ~8 s per 3,008-seq chunk, ~80 s for all 30,080 (estimate from 200-sequence benchmark).

---

## 7. Risks and quirks

### Critical: CLI produces no output

In `run_rna_analysis`, the call to `print_analysis(...)` is **commented out** (line 124), and `__main__` does not print the return value:

```python
run_rna_analysis(args.candidate_seqs_path, args.threshold_A, args.threshold_B, args.factor)
```

Running the script appears to succeed silently. Reproduction requires a wrapper or interactive Python.

### Preprocessing mismatch with project cleaning script

| Step | Repo `get_gen_seqs` | Project `clean_generated_sequences.py` |
|---|---|---|
| Leading tokens | `[1:]` only → leaves one `1` in variable region | Strips full prefix `11` |
| Flanks | Added by repo eval | Not added (cleaned variable region only) |
| Output length | 77 nt folded | 36 nt variable region |

To reproduce **repo** metrics, feed **raw** `seqs_wo_guidance_*.txt` files directly to `test_wrap_aptamer.py`. Do **not** use project cleaned FASTA/CSV without reversing the format difference.

### Aggressive EOS handling

`line.replace('2', '')` removes **every** `2` in the line, not just an EOS token at the end. Harmless for current outputs (no `2` observed) but dangerous if sequences ever contain `2`.

### Factor inconsistency

Post-hoc evaluation defaults `factor=2.0`; beam-search value functions default `factor=5.0`. Reproduce paper/repo batch eval with **2.0** unless explicitly comparing to guided search scores.

### README gap

`README.md` ends at generation; no evaluation section. Stage 2.3 depends on discovering `test_wrap_aptamer.py` directly.

### Length / artefact asymmetry

Reference variable region = 36 nt; preprocessed candidates = 37 nt with embedded digit `1`. This is repo behaviour, not project data corruption — but it means similarity is computed between structures of different lengths/content.

### No validity filtering

Invalid or duplicate sequences are folded and counted equally. Sequences with non-AUCG characters in the variable region (the leading `1`) are not rejected.

### `numpy` imported but unused

Harmless; no functional impact.

---

## 8. Recommended minimal reproduction plan

### Step 1 — Small test on existing medium-test file

Use `results/phase2_medium_test/seqs_wo_guidance_top_p=0.95_2_16_medium_test_seed42_steps50_batch16.txt` (16 sequences).

Import and print return value (since CLI is silent):

```python
from test_wrap_aptamer import run_rna_analysis
props = run_rna_analysis("…/seqs_wo_guidance_…16….txt")
print(props)
```

Optionally uncomment-equivalent: call `print_analysis` via `batch_analysis` + `threshold_analysis` for reference structure logging.

### Step 2 — Capture exact output

Save to project repo:

```
results/phase2_3_repo_evaluation/
├── logs/
│   └── medium_test_eval.log
└── summaries/
    └── medium_test_thresholds.md
```

Record: `threshold_A`, `threshold_B`, `factor`, `prop_similarity`, `prop_mfe`, reference MFE/structure, sequence count, timestamp, RNAGenesis commit.

### Step 3 — Wrapper (proposed, **not implemented** — awaiting approval)

**Design:** `scripts/run_repo_aptamer_evaluation.py` in project repo.

- Add `~/RNAGenesis` to `sys.path` or run with `cd ~/RNAGenesis`.
- Import `run_rna_analysis`, `batch_analysis`, `get_gen_seqs`, `threshold_analysis`, `print_analysis`.
- CLI: `--input`, `--threshold-a`, `--threshold-b`, `--factor`, `--output-dir`.
- Write:
  - `threshold_summary.json` / `.md` with aggregate proportions
  - optional `per_sequence_metrics.csv` from `batch_analysis` results
  - stdout log mirroring `print_analysis` output
- Do **not** alter preprocessing; call repo functions unchanged.

### Step 4 — Scale to 30,080 sequences

Options (equivalent if preprocessing is identical):

1. Run wrapper once per chunk (10 runs) → aggregate proportions manually or in wrapper.
2. Merge raw chunks into one file (30,080 lines) → single run.

Merging is safe (one sequence per line; no headers):

```bash
cat results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_*.txt \
  > results/phase2_3_repo_evaluation/inputs/merged_30080_raw.txt
```

Verify line count = 30,080 before evaluating.

### Step 5 — Save final outputs

```
results/phase2_3_repo_evaluation/
├── inputs/
│   └── merged_30080_raw.txt          # optional
├── logs/
│   ├── chunk01_eval.log
│   └── full_30080_eval.log
└── summaries/
    ├── per_chunk_thresholds.csv
    └── full_cohort_thresholds.md
```

---

## 9. Concrete next commands

### Check imports / dependencies

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate rnagenesis-h200

python -c "import RNA; import numpy; print('ViennaRNA OK')"
python ~/RNAGenesis/test_wrap_aptamer.py --help
```

### Run repo script directly on one chunk (silent — confirm with exit code only)

```bash
cd ~/RNAGenesis

python test_wrap_aptamer.py \
  --candidate_seqs_path ~/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk1_seed4201_steps50_batch16_batchnum188_gpu1.txt \
  --threshold_A 80.0 \
  --threshold_B 2.0 \
  --factor 2.0

echo "exit code: $?"
# Expect: no stdout
```

### Print results interactively (recommended until wrapper exists)

```bash
cd ~/RNAGenesis

python - <<'PY'
from test_wrap_aptamer import run_rna_analysis, batch_analysis, get_gen_seqs, threshold_analysis

path = "/home/laura/rnagenesis-aptamer-mres/results/phase2_medium_test/seqs_wo_guidance_top_p=0.95_2_16_medium_test_seed42_steps50_batch16.txt"
A, B, factor = 80.0, 2.0, 2.0

ref_seq = "TCCAGCACTCCACGCATAACGGCGGTGGGTGGGTTGTTGTGGGAGGGGGAGGGGGAGTTATGCGTGCTACCGTGAA"
seqs = get_gen_seqs(path)
ref_structure, ref_mfe, results = batch_analysis(seqs, ref_seq, factor)
prop_sim, prop_mfe = threshold_analysis(results, A, B)

print(f"n={len(results)}")
print(f"ref_mfe={ref_mfe:.2f}")
print(f"ref_structure={ref_structure}")
print(f"prop_similarity>={A}: {prop_sim:.2f}%")
print(f"prop_mfe_diff<={B}: {prop_mfe:.2f}%")
PY
```

### Create merged candidate file (optional, for single-pass eval)

```bash
mkdir -p ~/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/inputs

cat ~/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_*.txt \
  > ~/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/inputs/merged_30080_raw.txt

wc -l ~/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/inputs/merged_30080_raw.txt
# Expect: 30080
```

### Run evaluation on merged file and save log (when approved)

```bash
mkdir -p ~/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/{logs,summaries}

cd ~/RNAGenesis

python - <<'PY' | tee ~/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/logs/full_30080_eval.log
from test_wrap_aptamer import run_rna_analysis
path = "/home/laura/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation/inputs/merged_30080_raw.txt"
prop_sim, prop_mfe = run_rna_analysis(path, threshold_A=80.0, threshold_B=2.0, factor=2.0)
print(f"threshold_A=80  prop_similarity={prop_sim:.4f}%")
print(f"threshold_B=2   prop_mfe={prop_mfe:.4f}%")
PY
```

### Per-chunk loop (alternative to merging)

```bash
OUT=~/rnagenesis-aptamer-mres/results/phase2_3_repo_evaluation
mkdir -p "$OUT/logs" "$OUT/summaries"

cd ~/RNAGenesis
for f in ~/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_*.txt; do
  base=$(basename "$f" .txt)
  python -c "
from test_wrap_aptamer import run_rna_analysis
p=r'$f'
s,m=run_rna_analysis(p)
print(f'{p}\tprop_sim={s:.4f}\tprop_mfe={m:.4f}')
" | tee -a "$OUT/logs/per_chunk_eval.log"
done
```

---

## Summary

| Question | Answer |
|---|---|
| Repo aptamer eval entry point? | `~/RNAGenesis/test_wrap_aptamer.py` → `run_rna_analysis()` |
| Documented in README? | **No** |
| Metrics | Per-seq: similarity, MFE, MFE diff. Aggregate: % passing thresholds A=80, B=2 |
| Input | Raw `seqs_wo_guidance_*.txt`, one file at a time; repo handles BOS/EOS/flanks |
| GPU needed? | **No** |
| ViennaRNA needed? | **Yes** (already in `rnagenesis-h200`) |
| Main blocker for reproduction? | CLI returns metrics but **prints nothing** — wrapper or inline Python required |
| Use project cleaned sequences? | **No** — use raw generation files for faithful repo reproduction |

**Next action awaiting approval:** implement proposed wrapper in `scripts/run_repo_aptamer_evaluation.py`, then run Steps 1–2 on medium test before any full 30k evaluation.
