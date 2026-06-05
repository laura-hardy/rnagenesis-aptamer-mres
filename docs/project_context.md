# rnagenesis-aptamer-mres — Project Context Document

**Purpose of this document:** Provide enough context for an LLM (e.g. ChatGPT) to give specific guidance on code structure, file placement, scripting conventions, and next development steps for this MRes project.

**Last updated:** 2026-06-05  
**Repository:** `laura-hardy/rnagenesis-aptamer-mres` (GitHub)  
**Local path (Mac):** `~/Desktop/rnagenesis-aptamer-mres`

---

## 1. Project summary

**Title:** Towards prediction-guided generative design of RNA aptamers against carbapenemase targets

**Degree:** MRes Year 2 project

**Core idea:** Use [RNAGenesis](https://github.com/zaixizhang/RNAGenesis) — a diffusion-based RNA generative model — to design RNA aptamers against carbapenemase drug-resistance enzymes (KPC-2, NDM-1, OXA-48). The project combines:

1. Reproducing and running the RNAGenesis aptamer generation pipeline
2. Building evaluation baselines and cleaning/analysis tooling around generated sequences
3. Assembling or fine-tuning on RNA aptamer training data (target-specific data unlikely to exist publicly)
4. Eventually applying prediction-guided generation (classifier guidance) toward carbapenemase-relevant properties

**Important:** This repo is the **MRes project wrapper** — logs, scripts, data, results, and documentation. It is **not** a fork of RNAGenesis itself. RNAGenesis lives in a **separate repository** and is executed from there on GPU servers.

---

## 2. Two-repository architecture

| Repository | GitHub | Local path (server) | Role |
|---|---|---|---|
| **This project** | `laura-hardy/rnagenesis-aptamer-mres` | `~/rnagenesis-aptamer-mres` | Project-specific scripts, data, results, docs, environment exports |
| **RNAGenesis fork** | `laura-hardy/RNAGenesis` (upstream: `zaixizhang/RNAGenesis`) | `~/RNAGenesis` | Upstream model code; run `generation.py` from here |

**Pinned RNAGenesis commit (Phase 1/2 reproduction):** `d00899e` — Update README.md

**Design decision:** RNAGenesis is kept as a separate repo (not a git submodule). This repo records commit hashes, environment notes, run scripts, and small result copies for reproducibility.

**Where to put new code:**

| Task | Put it in… |
|---|---|
| Wrapping RNAGenesis runs, cleaning outputs, null models, dataset prep, evaluation | `rnagenesis-aptamer-mres/scripts/` |
| Modifying RNAGenesis model behaviour | `RNAGenesis/` (document commit + patch in `docs/log.md`) |
| Exploratory analysis | `rnagenesis-aptamer-mres/notebooks/` |
| Generated sequences, structure outputs, plots | `rnagenesis-aptamer-mres/results/` |
| Raw downloads, metadata, corpora | `rnagenesis-aptamer-mres/data/` |
| Session notes, decisions, procedures | `rnagenesis-aptamer-mres/docs/` |

---

## 3. Directory structure

```
rnagenesis-aptamer-mres/
├── README.md                          # One-line project description
├── docs/                              # All project documentation
│   ├── log.md                         # Chronological research/dev log (primary history)
│   ├── project_context.md             # This file
│   ├── dataset_decisions.md           # Dataset search strategy and decisions
│   ├── dataset_search_log.xlsx        # Evidence log for dataset searches
│   ├── environment_notes.md           # RNAGenesis dependency observations
│   ├── checkpoint_download_plan.md    # Zenodo asset plan (Phase 1.5)
│   ├── start_of_day_checklist.md      # A6000 server session startup
│   ├── end_of_day_checklist.md        # Git, logging, cleanup conventions
│   └── a6000_reinstall_procedure.md   # Full server rebuild after format
├── scripts/                           # Project-owned executable scripts
│   ├── run_rnagenesis_aptamer_tiny_test.sh
│   ├── run_rnagenesis_aptamer_small_test.sh
│   ├── run_rnagenesis_aptamer_medium_test.sh
│   └── null_model.py                  # NumPy null baseline generator (WIP)
├── environment/                       # Conda environment exports (not runtime)
│   ├── environment_a6000.yml          # Validated A6000 GPU environment
│   ├── mac_environment.yml            # Mac dev environment
│   └── mac_pip_freeze.txt
├── data/                              # Datasets and metadata (git: small files only)
│   └── raw/
│       └── sra_metadata/              # e.g. PRJNA830749/SraRunInfo.csv
│   # Planned paths (not yet populated):
│   #   data/raw/aptadiff_dataset_A/
│   #   data/structures/                 # PDB files for KPC-2, NDM-1, OXA-48
├── results/                           # Committed small outputs; not full model runs
│   ├── phase2_tiny_test/
│   ├── phase2_small_test/
│   └── phase2_medium_test/
└── notebooks/                         # Jupyter notebooks (mostly empty)
```

**Planned `data/` layout (from dataset_decisions.md):**

```
data/
├── raw/                    # Unprocessed downloads
├── processed/              # Cleaned corpora ready for fine-tuning/eval
├── structures/             # Target protein PDB files + metadata
└── references/             # Known binder sequences from literature
```

**Planned `results/` layout for future work:**

```
results/
├── phase2_<test_name>/              # RNAGenesis generation outputs
│   ├── seqs_*.txt                   # Raw generation output
│   ├── cleaned/                     # Post-processed FASTA/CSV
│   └── alphafold_structures/        # Optional structure prediction artifacts
│       ├── inputs/
│       ├── outputs/
│       ├── logs/
│       └── notes/
├── null_model/                      # Random baseline sequences
└── evaluation/                      # Comparison tables, metrics, figures
```

---

## 4. Compute environments

### 4.1 MacBook (development only)

- **Use for:** Reading code, writing scripts, notebooks, lightweight NumPy/pandas work, git, documentation
- **Do not use for:** Full RNAGenesis GPU generation (requires CUDA)
- **Conda env:** `rnagenesis-mac` (Python 3.10)
- **Export:** `environment/mac_environment.yml`
- **Notes:** NumPy must stay `<2`; `huggingface-hub==0.20.3` required for `diffusers==0.25.0`

### 4.2 A6000 server (primary execution environment as of May 2026)

- **Host:** `warpgolem` (`ssh laura@warpgolem`)
- **GPU:** NVIDIA RTX 6000 Ada Generation, CUDA 12.5 (driver), PyTorch cu121
- **Conda env:** `/home/laura/.conda/envs/rnagenesis-a6000` (Python 3.8.13)
- **Export:** `environment/environment_a6000.yml`
- **Activation:**
  ```bash
  source /opt/anaconda3/etc/profile.d/conda.sh
  conda activate /home/laura/.conda/envs/rnagenesis-a6000
  ```

### 4.3 H200 server (alternate; partially set up)

- **Host:** `aai` (2× NVIDIA H200 NVL)
- **Status:** Environment created; checkpoint download deferred; A6000 became primary
- **Policy:** Datasets under `/Datasets`; code/checkpoints under `~`

### 4.4 Key pinned dependencies (A6000, validated)

| Package | Version |
|---|---|
| Python | 3.8.13 |
| torch / torchvision / torchaudio | 2.1.2 / 0.16.2 / 2.1.2 (+cu121) |
| transformers | 4.36.2 |
| diffusers | 0.25.0 (requires local patch — see §6) |
| huggingface-hub | 0.20.3 |
| numpy | 1.24.4 (<2) |
| biopython, viennarna, einops, timm, torchinfo, tqdm | installed |
| rna-fm, omegaconf, accelerate | installed |

**Package management note:** This project currently uses **conda + pip**, not `uv`. New utility scripts on Mac can use plain Python/NumPy or conda env `rnagenesis-mac`. GPU pipeline scripts are bash wrappers around RNAGenesis.

---

## 5. External model assets (not in git)

Downloaded from Zenodo: https://zenodo.org/records/15203813

| File | Approx. size | Extracted location (under `~/RNAGenesis/`) |
|---|---|---|
| `checkpoints.zip` | ~14 GB | `checkpoints/` |
| `configs.zip` | ~15 GB | `configs/` |
| `progen2-base.zip` | ~1.4 GB | `models/autoencoder/decoder/checkpoints/progen2-base/` |
| `progen2-small.zip` | ~536 MB | `models/autoencoder/decoder/checkpoints/progen2-small/` |

**Key runtime paths for `generation.py`:**

```
--enc_dec_file  configs/rnagenesis/autoencoder
--dm_file       checkpoints/Aptamer/diffusion
--decoder_config config-progen2-small-rna_tokenizer_v2
```

**Known upstream README issues:**

- Typo: `confiigs/` → `configs/`
- Script name: README says `generate.py`; repo uses `generation.py`

---

## 6. Critical compatibility patch

Successful Phase 2 runs required patching `diffusers==0.25.0`:

- **Error:** `ValueError: not enough values to unpack (expected 2, got 1)` in `diffusers/models/normalization.py` (AdaLayerNorm)
- **Fix:** Documented step-by-step in `docs/a6000_reinstall_procedure.md`
- **Must re-apply after environment rebuild**

---

## 7. Project phases and current status

### Aim 1 — Reproduce RNAGenesis aptamer generation

| Phase | Description | Status |
|---|---|---|
| 1.3 | Mac lightweight dev environment | ✅ Complete |
| 1.4 | GPU server environment (A6000) | ✅ Complete |
| 1.5 | Download/extract Zenodo checkpoints | ✅ Complete (may need re-download after server format) |
| 1.6 | Fork/clone RNAGenesis | ✅ Complete |
| 2 | Operational reproduction (unguided generation) | ✅ Tiny/small/medium tests succeeded |
| 2+ | Output cleaning, scaling, guided generation | 🔲 **Next** |

### Dataset / fine-tuning track (parallel)

| Task | Status |
|---|---|
| Target-specific HT-SELEX search (KPC, NDM, OXA-48) | In progress; no obvious public dataset found yet |
| General corpus candidates (AptaDiff A, UTexas, AptaDB) | Identified; not yet downloaded |
| Literature evaluation references (Yu, Chen, Shi, Sabrowski papers) | Identified; sequences not yet extracted |
| Target structures (PDB) | Planned under `data/structures/` |
| Fine-tuning RNAGenesis | Not started |

### Evaluation framework (planned)

| Level | Description | Status |
|---|---|---|
| Null model | Random RNA with corpus-matched length + nucleotide frequencies | Script stub: `scripts/null_model.py` |
| Level 2 shuffled control | Dinucleotide-preserving shuffles for structure-scoring tests | Planned, not implemented |
| RNAGenesis unguided | Baseline generation (Phase 2 complete at small scale) | ✅ |
| Guided generation | Classifier guidance toward target properties | Not started |
| Structural evaluation | AlphaFold3 (external web tool) on sample sequences | Exploratory (2 seqs, tiny test) |

---

## 8. RNAGenesis generation — working commands

All run from `~/RNAGenesis` with conda env active. Reproducible wrappers live in this repo's `scripts/`.

### Tiny test (verified)

```bash
# scripts/run_rnagenesis_aptamer_tiny_test.sh
num_inference_steps=5, batch_size=2, seed=42, max_seq_len=37
Output → ~/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_tiny_test/
Copied to → results/phase2_tiny_test/
```

### Small test (verified)

```bash
num_inference_steps=20, batch_size=8, seed=42
Copied to → results/phase2_small_test/
```

### Medium test (verified)

```bash
num_inference_steps=50, batch_size=16, seed=42
Copied to → results/phase2_medium_test/
```

### Common generation flags (unguided)

```
--do_sample --top_p 0.95 --top_k 0
--eos_token "2" --bos_token "1"
--guidance_scale 1.0  (guidance off in practice)
--device cuda
```

---

## 9. Known output format issue: leading `11` prefix

Generated sequences consistently start with `11`, e.g.:

```
11CGGGUCGUUUGGUUAUUUGUGGUUGGGUGUGGGGGG
```

**Interpretation:** Likely decoder/BOS token artifacts, not biological RNA bases.

**Impact:** All downstream cleaning, FASTA export, AlphaFold submission, and metrics must handle this consistently.

**Planned cleaning script responsibilities (from log, not yet written):**

- Strip or document handling of leading `11`
- Validate RNA alphabet (A, U, C, G)
- Report raw vs cleaned lengths
- Detect duplicates
- Export cleaned CSV and FASTA to `results/<run>/cleaned/`

---

## 10. Existing scripts in this repo

### `scripts/run_rnagenesis_aptamer_*_test.sh`

- Bash wrappers; `cd ~/RNAGenesis`, activate conda, call `python generation.py`
- Server-only (hardcoded A6000 paths)
- Pattern for new runs: copy nearest test script, adjust `--num_inference_steps`, `--batch_size`, `--remark`, `--mid_folder`

### `scripts/null_model.py`

- NumPy-only random sequence generator
- Samples lengths from empirical corpus distribution; nucleotides from corpus A/U/C/G frequencies
- Target: 30,000 sequences for baseline comparison
- **Status:** Function stubs written; corpus stats and output paths not yet filled in
- **Should output to:** `results/null_model/` (recommended)

---

## 11. Scientific targets and data strategy

### Protein targets

- **KPC-2**, **NDM-1**, **OXA-48** carbapenemases
- Structures: download from RCSB PDB → `data/structures/`

### Training data decision tree

1. **If** public HT-SELEX data exists for these targets → use as primary fine-tuning set
2. **Else** (likely) → general RNA aptamer corpus for adaptation; literature binders as evaluation references only

### Candidate training corpora

- AptaDiff Dataset A (13,802 RNA seqs, IGFBP3 SELEX) → `data/raw/aptadiff_dataset_A/`
- UTexas Aptamer Database (Zenodo snapshot)
- AptaDB, Apta-Index (cross-reference / expansion)

### Inclusion criteria (summary)

- RNA, SELEX-derived, known protein target, 20–120 nt, standard alphabet, research-usable licence
- Exclude DNA aptamers from primary RNA corpus unless explicitly justified

Full details: `docs/dataset_decisions.md`

---

## 12. Workflow conventions

### Logging

- **`docs/log.md`** is the authoritative session history
- End each session with: what was done, current status, next step
- See `docs/end_of_day_checklist.md`

### Git

- Commit small results, scripts, docs, environment exports
- Do **not** commit: Zenodo zips, large checkpoints, `.DS_Store`
- `.gitignore` currently only excludes `.DS_Store` (minimal)

### Server sessions

- Start: `docs/start_of_day_checklist.md` (VPN, SSH, `nvidia-smi`, conda activate, verify imports)
- End: stop jobs, check disk, export env if changed, git push, update log

### Reproducibility habits

- Fix random seeds (`--seed 42`)
- Save run commands as scripts in `scripts/`
- Copy representative outputs to `results/<phase>_<name>/`
- Record RNAGenesis commit hash when changing upstream code

---

## 13. Immediate next steps (as of 2026-06-05)

Priority order from project log:

1. **Sequence cleaning script** — handle `11` prefix, validate alphabet, export FASTA/CSV
2. **Complete null model** — fill corpus stats, set output path, generate 30k sequences
3. **Resume A6000** after server upgrade — follow `docs/a6000_reinstall_procedure.md`
4. **Dataset downloads** — AptaDiff A, UTexas; continue SRA/GEO search logging
5. **Extract evaluation references** — known binders from target-specific SELEX papers
6. **Scale generation** — larger baseline runs once cleaning pipeline exists
7. **AlphaFold / structural pipeline** — formalize inputs (trimmed FASTA) and results layout

---

## 14. Open questions (good prompts for LLM guidance)

- Where should cleaning, evaluation, and null-model code live — one module vs separate scripts?
- Preferred output schema for cleaned sequences (CSV columns, FASTA headers)?
- How to structure `data/processed/` for RNAGenesis fine-tuning format?
- When to add `pyproject.toml` / dependency pinning for Mac utility scripts?
- How to version and parameterize run configs (YAML vs shell script flags)?
- Testing strategy for scripts that don't need GPU?
- Naming conventions for result directories as experiments multiply?

---

## 15. How to use this document with ChatGPT

When asking for coding help, provide:

1. This document (or relevant sections)
2. The specific task (e.g. "write `scripts/clean_generated_sequences.py`")
3. Sample input (`results/phase2_medium_test/seqs_*.txt`) and desired output paths
4. Constraints: Mac-runnable vs server-only, conda not uv, match existing bash script patterns

**Good request examples:**

- "Design a `scripts/clean_generated_sequences.py` that reads RNAGenesis output txt files, strips the leading `11`, validates RNA alphabet, and writes FASTA + CSV to `results/<run>/cleaned/`."
- "Propose a `data/processed/` directory structure compatible with RNAGenesis fine-tuning, given AptaDiff Dataset A format."
- "Extend `null_model.py` to read corpus stats from a FASTA file and write 30,000 sequences to `results/null_model/`."
- "Suggest a pytest-free validation approach for the cleaning script using the committed phase2 test outputs."

---

## 16. Key file index

| File | Contents |
|---|---|
| `docs/log.md` | Full chronological project history |
| `docs/dataset_decisions.md` | Dataset strategy and inclusion criteria |
| `docs/a6000_reinstall_procedure.md` | Server rebuild + diffusers patch |
| `docs/start_of_day_checklist.md` | A6000 session startup |
| `docs/end_of_day_checklist.md` | Git, logging, cleanup |
| `environment/environment_a6000.yml` | Validated GPU environment |
| `environment/mac_environment.yml` | Mac dev environment |
| `scripts/run_rnagenesis_aptamer_*_test.sh` | Verified generation wrappers |
| `scripts/null_model.py` | Null baseline generator (WIP) |
| `results/phase2_*_test/` | Committed generation outputs |

---

## 17. Related repositories and URLs

- **This project:** https://github.com/laura-hardy/rnagenesis-aptamer-mres
- **RNAGenesis fork:** https://github.com/laura-hardy/RNAGenesis
- **RNAGenesis upstream:** https://github.com/zaixizhang/RNAGenesis
- **Model weights:** https://zenodo.org/records/15203813
- **Paper context:** RNAGenesis / AptaDiff aptamer generation benchmark pathway
