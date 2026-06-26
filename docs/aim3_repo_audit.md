# Aim 3 Repo Audit

**Date:** 2026-06-19  
**Repo:** `/Users/laura/Desktop/rnagenesis-aptamer-mres`  
**Scope:** Read-only inspection; no code changes. Safe smoke tests only.

---

## Executive summary

- **Aim 3 filtering/ranking pipeline is not yet implemented.** There is no `src/`, `pipeline/`, `configs/`, or dedicated filter/rank module in this repo.
- **Substantial Aim 1 work is complete:** unadapted RNAGenesis generation (tiny/small/medium tests + 30,080-sequence H200 baseline), output cleaning script, and faithful reproduction of RNAGenesis `test_wrap_aptamer.py` evaluation (Stage 2.3 / repo eval — distinct from Aim 3).
- **`scripts/clean_generated_sequences.py`** is the only project-owned code touching pre-filter sequence QC: strips leading `11`, validates A/U/C/G alphabet, records lengths, flags within-condition duplicates, exports CSV/FASTA/summary. Tested on 16-sequence medium test; **not yet run on the 30k baseline pool.**
- **`scripts/null_model.py`** is a NumPy stub (`get_corpus_stats`, `generate_null_sequences`) with no CLI, no corpus inputs filled in, and no generated output.
- **Stage 0 validation set does not exist:** no IGFBP3 positives, no random-RNA pool output, no shuffle/composition-matched controls, no validation scripts or figures.
- **Training/reference aptamer corpus not downloaded:** AptaDiff Dataset A path planned at `data/raw/aptadiff_dataset_A/` but absent. Only NDM-1 SELEX **metadata** (SRA accession list) is present under `data/raw/sra_metadata/PRJNA830749/`.
- **Stage 1–3 features are almost entirely missing** except partial overlap with cleaning (alphabet, length, duplicate flag) and external RNAGenesis repo eval (MFE + structure similarity vs hard-coded reference aptamer, not project pipeline).
- **Generated sequence data is ready for pipeline development:** 30,080 raw unadapted RNAGenesis sequences committed under `results/phase4_1_unadapted_rnagenesis_30k/raw/` plus small test sets (2/8/16 seqs).
- **No automated tests** (`tests/`, pytest, smoke tests) for Aim 3. Mac conda env `rnagenesis-mac` has pandas, numpy, ViennaRNA; missing Levenshtein, forgi, rapidfuzz, ushuffle, mmseqs2 references.
- **Documentation is partially stale:** `docs/project_context.md` (2026-06-05) still lists cleaning script as planned/next; `docs/log.md` records cleaning implemented 2026-06-05 and repo eval completed 2026-06-11.

---

## Current git state

| Item | Value |
|---|---|
| **Branch** | `main` (up to date with `origin/main`) |
| **Working tree** | **Clean** — no uncommitted or untracked tracked changes |
| **Last 5 commits** | `8cc35f6` Update report · `5556666` Add local analysis report for Stage 2.3 repo evaluation · `e219440` Add Stage 2.3 RNAGenesis repo aptamer evaluation · `541f697` Study and document existing repo evaluation procedure · `ef4101b` Add README for Phase 4.1 baseline outputs |
| **Untracked Aim 3 files** | None observed |
| **VC risks** | `.gitignore` excludes most `results/` but force-includes `phase4_1_unadapted_rnagenesis_30k/`; other result dirs (phase2 tests, repo eval) appear historically committed. `__pycache__/` present locally but gitignored. No `pyproject.toml` / lockfile for utility scripts. |

---

## Relevant files found

| Path | Purpose | Status | Notes |
|---|---|---|---|
| `scripts/clean_generated_sequences.py` | Pre-filter cleaning: strip `11`, alphabet check, lengths, duplicate flag, CSV/FASTA export | **Partial / pre-Stage-1** | Functions: `validate_rna_alphabet`, `strip_leading_artifact`, `build_records`, `clean_generated_sequences`. Tested on medium test (16 seqs). Explicitly not biological filtering. |
| `scripts/null_model.py` | Random RNA baseline generator | **Stub** | `get_corpus_stats`, `generate_null_sequences`; no main/CLI, corpus params empty in log |
| `scripts/run_repo_aptamer_evaluation.py` | Wrapper for RNAGenesis `test_wrap_aptamer.py` | **Complete (Aim 1)** | MFE, structure similarity vs fixed ref aptamer; not Aim 3 pipeline |
| `scripts/analyse_repo_aptamer_eval_results.py` | Plots/tables/report for repo eval summaries | **Complete (Aim 1)** | Writes to `results/phase2_3_repo_evaluation/analysis/` |
| `scripts/analyze_phase2_4_repeatability.py` | Repeatability analysis for generation | **Complete (Aim 1)** | Unrelated to filtering |
| `scripts/run_rnagenesis_aptamer_*_test.sh` | GPU generation wrappers | **Complete (Aim 1)** | Server-only bash |
| `scripts/run_phase2_3_repo_aptamer_eval_h200.sh` | H200 runner for repo eval | **Complete (Aim 1)** | |
| `~/RNAGenesis/test_wrap_aptamer.py` | Upstream aptamer eval (external repo) | **Complete (upstream)** | `RNA.fold`, similarity, MFE diff; no GC/homopolymer/dedup/novelty |
| `docs/log.md` | Chronological project history | **Current through 2026-06-11** | Records cleaning + repo eval; defers custom pipeline |
| `docs/project_context.md` | LLM context doc | **Partially stale** | Still says cleaning "not yet written" |
| `docs/dataset_decisions.md` | Dataset strategy | **Planning doc** | AptaDiff, NDM refs planned, not downloaded |
| `docs/run_notes/rnagenesis_repo_evaluation_investigation.md` | Repo eval investigation | **Complete** | Documents what upstream eval does/doesn't compute |
| `results/phase4_1_unadapted_rnagenesis_30k/raw/*.txt` | 30k unadapted generation pool | **Raw input ready** | 10 × 3,008 = 30,080 lines |
| `results/phase2_medium_test/cleaned/` | Example cleaned output | **Sample processed** | 16 sequences |
| `results/phase2_3_repo_evaluation/` | Repo eval outputs | **Aim 1 results** | Summaries, plots, per-sequence CSV (medium test only) |

**Not found:** `src/`, `pipeline/`, `configs/`, `tests/`, `notebooks/` (empty), Aim 3 stage modules, YAML/JSON filter configs.

**Naming conventions in use:**
- Results: `results/phase{N}_{description}/`
- Raw generation: `seqs_wo_guidance_top_p=0.95_2_{count}_{remark}.txt`
- Cleaned: `cleaned/cleaned_sequences.csv`, `cleaned_sequences.fasta`, `cleaning_summary.txt`
- Condition labels: e.g. `unadapted_rnagenesis`
- Sequence IDs: `{condition}_{source_stem}_{index:05d}`

---

## Stage 0 validation status

| Item | Status |
|---|---|
| IGFBP3 late-round positives | ❌ **Missing** — planned from AptaDiff Dataset A, not downloaded |
| Random RNA negative controls | ❌ **Missing** — `null_model.py` stub only, no output |
| Shuffled / composition-matched controls | ❌ **Missing** — documented as planned in `project_context.md` |
| Validation scripts/notebooks | ❌ **Not found** |
| Validation output figures/tables | ❌ **Not found** |
| Enough to run validation pass? | ❌ **No** — lacks positives, negatives, controls, and pipeline |
| Intended commands | None for Stage 0. Closest existing: `scripts/clean_generated_sequences.py`, `scripts/run_repo_aptamer_evaluation.py` (repo eval, not validation) |

---

## Stage 1 hard filtering status

| Feature | Status | Location |
|---|---|---|
| Valid RNA alphabet (A/U/C/G) | ✅ Implemented, tested (medium test) | `clean_generated_sequences.py`: `validate_rna_alphabet` |
| Length calculation | ✅ Implemented, tested | `raw_length`, `cleaned_length` columns |
| Empirical length bounds from training corpus | ❌ Not found | — |
| Exact deduplication within condition | ⚠️ Partial — flags only, does not remove | `is_duplicate_within_condition` in `build_records` |
| Near-dedup vs training (Levenshtein) | ❌ Not found | — |
| Homopolymer run removal (5+) | ❌ Not found | — |
| GC content calculation | ❌ Not found | — |
| Empirical GC band (5th–95th pct) | ❌ Not found | — |
| ViennaRNA/RNAfold MFE | ⚠️ Upstream only — not in project filter pipeline | `RNAGenesis/test_wrap_aptamer.py`: `compute_structure` → `RNA.fold` |
| Normalised MFE by length | ❌ Not found | — |
| Lenient MFE threshold from training distribution | ❌ Not found | Repo eval uses fixed ref-aptamer diff threshold |
| Per-filter logging (removed/retained counts) | ⚠️ Partial — cleaning summary only | `write_cleaning_summary` |
| Threshold/config system | ❌ Not found | Hardcoded in repo eval wrapper args only |
| Output table with removal reasons / pass-fail | ⚠️ Partial — `cleaning_status` only | No multi-filter pass/fail flags |

---

## Stage 2 structural scoring status

| Feature | Status | Location |
|---|---|---|
| ViennaRNA `fold_compound` usage | ❌ Not found | Repo uses `RNA.fold` only |
| MFE structure / dot-bracket output | ✅ Upstream repo eval only | `test_wrap_aptamer.py`; per-seq CSV in repo eval |
| Partition function / ensemble features | ❌ Not found | |
| Ensemble defect | ❌ Not found | |
| Positional entropy / base-pair probability | ❌ Not found | |
| Normalised MFE vs training distribution | ❌ Not found | |
| GC proximity score | ❌ Not found | |
| Structural element parsing (forgi) | ❌ Not found | |
| Loop/stem/hairpin/internal loop features | ❌ Not found | |
| Rank aggregation | ❌ Not found | |
| Caching of ViennaRNA results | ❌ Not found | |
| Shuffled-sequence structural control | ❌ Planned only | `docs/project_context.md` |

---

## Stage 3 novelty/diversity status

| Feature | Status |
|---|---|
| Novelty score vs training corpus | ❌ Not found |
| NDM-1 ssDNA reference aptamer handling | ❌ Not found (papers logged in `dataset_decisions.md` only) |
| T-to-U conversion for comparison | ❌ Not found |
| Structural similarity to NDM-1 references | ❌ Not found |
| Loop accessibility score | ❌ Not found |
| Clustering (MMseqs2 / CD-HIT-EST) | ❌ Not found |
| Top 1–2 per cluster selection | ❌ Not found |
| Stage 3 composite score | ❌ Not found |

---

## Data inventory

| Path | Count / size | Format | State | Local test size |
|---|---|---|---|---|
| `results/phase2_tiny_test/*.txt` | 2 seqs | One seq/line, leading `11` | Raw generation | ✅ Tiny |
| `results/phase2_small_test/*.txt` | 8 seqs | Same | Raw | ✅ Tiny |
| `results/phase2_medium_test/*.txt` | 16 seqs | Same | Raw | ✅ Small |
| `results/phase2_medium_test/cleaned/cleaned_sequences.csv` | 16 rows | CSV: sequence_id, raw/cleaned seq, lengths, flags | Processed | ✅ Small |
| `results/phase4_1_unadapted_rnagenesis_30k/raw/*.txt` | 10 files × 3,008 = **30,080** | Raw RNAGenesis output (~1.2 MB total) | Raw, uncleaned | ⚠️ Large but text-light |
| `results/phase2_3_repo_evaluation/inputs/merged_30080_raw.txt` | 30,080 lines | Merged raw for repo eval | Processed merge | Large |
| `results/phase2_4_repeatability/*.txt` | 3 small files | Raw generation | Raw | ✅ Tiny |
| `results/null_model/` | — | — | ❌ Does not exist | — |
| `data/raw/aptadiff_dataset_A/` | — | — | ❌ Not present | — |
| `data/raw/sra_metadata/PRJNA830749/SraRunInfo.csv` | 8 SRA runs | CSV metadata for NDM-1 SELEX | Raw metadata only | ✅ Small |
| NDM-1 reference aptamer sequences | — | — | ❌ Not extracted | — |
| Fine-tuned / guided RNAGenesis output | — | — | ❌ Not generated | — |

**Raw line format example:** `11CGGGUCGUUUGGUUAUUUGUGGUUGGGUGUGGGGGG` (38 chars raw → 36 cleaned).

---

## Dependencies / environment

**Package management:** Conda exports in `environment/` (`mac_environment.yml`, `environment_a6000.yml`, `environment_h200.yml`). No `pyproject.toml`, `requirements.txt`, or `setup.py` in repo. Project docs note conda+pip, not `uv`.

**Mac env `rnagenesis-mac` (Python 3.10.18) — import checks run 2026-06-19:**

| Dependency | Present? |
|---|---|
| pandas | ✅ 2.3.3 |
| numpy | ✅ 1.26.4 |
| ViennaRNA (`RNA`) | ✅ |
| biopython | ✅ (in conda env) |
| matplotlib / seaborn | ✅ |
| scikit-learn / scipy | ✅ |
| python-Levenshtein | ❌ ModuleNotFoundError |
| rapidfuzz | ❌ ModuleNotFoundError |
| forgi | ❌ ModuleNotFoundError |
| ushuffle | ❌ Not referenced in env files |
| mmseqs2 / cd-hit-est | ❌ Not referenced |

**Likely installation gaps before Aim 3 coding:** Levenshtein or rapidfuzz (near-dedup), forgi (structure parsing), shuffle tool (Stage 0/2 controls), optional MMseqs2/CD-HIT (Stage 3 clustering).

**Note:** Default `python3` on PATH (`/Users/laura/anaconda3/bin/python3`) appeared to hang on script invocations in sandbox; use explicit `/Users/laura/anaconda3/envs/rnagenesis-mac/bin/python`.

---

## Tests / runnable commands

| Command | Outcome |
|---|---|
| `git status` | ✅ Clean on `main` |
| `rnagenesis-mac/bin/python scripts/clean_generated_sequences.py --help` | ✅ Success |
| `rnagenesis-mac/bin/python scripts/run_repo_aptamer_evaluation.py --candidate-file results/phase2_medium_test/... --rnagenesis-repo ~/Desktop/RNAGenesis --output-dir /tmp/...` | ✅ Success (n=16, prop_mfe=25%) |
| `import pandas, numpy, RNA` | ✅ Success |
| `import Levenshtein, forgi, rapidfuzz` | ❌ ModuleNotFoundError |
| `uv run ...` | ❌ `uv` not installed |
| `pytest` | ❌ No test suite found |
| Cleaning on medium test (prior session per `docs/log.md`) | ✅ 16/16 valid |

---

## Documentation notes

**What docs say is done:**
- RNAGenesis unguided generation reproduced (Phases 2, 4.1 baseline 30k)
- Cleaning script implemented and tested on medium test
- Null model script added (stub)
- Stage 2.3 repo aptamer evaluation reproduced on 16, 3,008, and 30,080 sequences
- Full custom baseline characterisation / filtering pipeline **explicitly deferred**

**Doc/code agreement:**
- Repo eval docs match implemented wrappers and results ✅
- `project_context.md` §13 "Immediate next steps" still lists cleaning as #1 — **stale** (cleaning exists)
- Phase 4.1 README "Next steps" (merge, clean, dedup, 30k prep) — **accurate, not yet done**

**Planned next steps in logs:**
1. Merge/clean/deduplicate 30k baseline
2. Complete null model with corpus stats
3. Download AptaDiff Dataset A
4. Build project-specific filtering/ranking (Aim 3)

---

## Blockers / risks

1. **No Aim 3 code structure** — everything remains ad hoc scripts; no config schema or pipeline stages.
2. **Missing training/validation data** — AptaDiff/IGFBP3 not downloaded; blocks Stage 0 and empirical Stage 1 thresholds.
3. **30k pool uncleaned** — baseline committed raw but not merged/cleaned/deduplicated to target 30,000.
4. **Null model incomplete** — no random-RNA negative pool for Stage 0.
5. **Missing Python deps** for planned features (Levenshtein, forgi, shuffle, clustering tools).
6. **Two preprocessing paths** — project cleaning strips `11`; RNAGenesis repo eval uses different token handling (`replace '2'`, `[1:]` BOS strip, flanks). Aim 3 must define one canonical sequence representation.
7. **Stale `project_context.md`** may mislead future development planning.
8. **RNAGenesis repo eval ≠ Aim 3** — reference aptamer is RNAGenesis hard-coded IGFBP3-related sequence, not NDM-1 targets.

---

## Recommended next step

**Download and validate AptaDiff Dataset A, then build a small Stage 0 validation fixture (IGFBP3 late-round positives + corpus-derived random negatives + composition-matched shuffles).**

**Why:** Stage 0 is the immediate MRes focus and is entirely absent. Stage 1 empirical length/GC/MFE thresholds also require the training corpus. Cleaning and 30k generation are ahead of filtering code but cannot be *validated* without labelled positives and controls. This is the smallest step that unblocks both Stage 0 and Stage 1 threshold design without GPU work.

**Immediate follow-on (after fixture):** Standardise the sequence table schema (extend `cleaned_sequences.csv` columns) and run `clean_generated_sequences.py` on the 30k baseline with a documented canonical preprocessing path distinct from repo-eval flanking.
