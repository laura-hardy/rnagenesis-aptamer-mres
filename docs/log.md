# Project Log

## 2026-04-24 — Initial setup

- Created GitHub repository.
- Cloned repository locally.
- Created initial project folder structure.
- Added project log file.

## 2026-04-24 — RNAGenesis environment inspection

### Context
Inspecting environment requirements before attempting installation.

### Findings
- Python version pinned to 3.8.13.
- PyTorch pinned to:
  - torch==2.1.2
  - torchvision==0.16.2
  - torchaudio==2.1.2
- CUDA version is not explicitly specified in environment.yml or README.
  - This means GPU compatibility must be handled manually on H200.

### Dependency observations
- Environment uses strict version pinning (including older system libraries like openssl 1.1.1).
- Potential compatibility issues expected on macOS (Apple Silicon).

- Cursor analysis identified additional dependencies used in code but not declared:
  - einops
  - timm
  - torchinfo
  - tqdm
  - tensorflow (for some modules)
  - nupack, catboost, ruptures (likely optional components)

### Interpretation / decisions
- Will use H200 server for full environment + model execution.
- Will use MacBook for:
  - code reading
  - lightweight testing
  - documentation

- Will NOT attempt to perfectly reproduce full environment on Mac.
- On H200:
  - Start with environment.yml or README instructions
  - Expect to install missing dependencies incrementally based on errors

### Open questions
- Which dependencies are actually required for the aptamer pipeline vs optional modules?
- What CUDA version is compatible with H200 + PyTorch 2.1.2?

## 2026-04-24 — End of session

- Set up project repository
- Configured SSH access
- Inspected RNAGenesis environment requirements
- Created environment notes

Next:
- Set up Mac lightweight environment (Phase 1.3)


## 2026-04-25 — Lightweight Mac environment setup (1.3)

Created local Mac environment `rnagenesis-mac` for code reading, notebooks, import testing, and utility scripts.

Decision:
- Did not attempt full reproduction environment on MacBook because RNAGenesis execution is expected to require NVIDIA/CUDA.
- H200 will be used for full model execution.

Environment:
- Python 3.10
- Installed core scientific packages, ViennaRNA, PyTorch, transformers, diffusers, and likely missing code dependencies such as einops, timm, torchinfo, and tqdm.
- Used Python 3.10 locally as a pragmatic Apple Silicon development environment. This is not intended to be the strict reproduction environment. The H200 environment will use Python 3.8.13 to match RNAGenesis.

Validation:
- Tested PyTorch import.
- Tested ViennaRNA import.
- Tested core transformer/diffusion imports.
- Mac environment initially produced compatibility errors due to NumPy 2.x, missing ViennaRNA Python bindings, and incompatible huggingface-hub version with diffusers 0.25.0. Fixed by downgrading NumPy below 2, installing ViennaRNA via pip, and pinning huggingface-hub to 0.20.3.

### Current status
- PyTorch working (MPS available: True)
- Core ML imports working (transformers, diffusers, Bio)
- ViennaRNA import now working

## 2026-04-25 — H200 access attempt (Phase 1.4)

Attempted to SSH into the H200 server via university VPN.

Status:
- VPN connected successfully.
- Server reachable over SSH.
- Username appears correct.
- Login failing due to password/authentication issue.

Action:
- Contacted support / relevant contact for assistance.
- Pausing H200 environment setup until access is resolved.
- Booked H200 access for 4 May to resume setup and coding.

## 2026-04-25 — Forked RNAGenesis repository (Phase 1.6)

Forked the upstream RNAGenesis repository to my GitHub account for stable annotation and modification.

Repository:
- Upstream: zaixizhang/RNAGenesis
- Fork: laura-hardy/RNAGenesis

Local clone:
- ~/Desktop/RNAGenesis

Current commit:
- [paste commit hash here]

Decision:
- Keeping RNAGenesis as a separate repository for now rather than adding it as a submodule.
- The MRes project repository will record commit hashes and environment notes for reproducibility.

Current RNAGenesis commit:
- d00899e — Update README.md

## 2026-04-28 — Checkpoint and data preparation (Phase 1.5)

Reviewed RNAGenesis repository instructions for checkpoint and data download.

Findings:
- Aptamer pipeline depends on external model weights from Zenodo.
- Required files:
  - checkpoints.zip
  - configs.zip
  - progen2-base.zip
  - progen2-small.zip
- These must be downloaded directly to H200.

Issues identified:
- README contains typo ("confiigs/" instead of "configs/")
- README references generate.py, but repository uses generation.py
- Required configuration files are not present in repository and come from configs.zip

Decision:
- Will perform all downloads on H200 once access is available.
- Will verify directory structure after extraction before attempting execution.

## 2026-04-28 — Hugging Face model inspection

Inspected RNAGenesis model on Hugging Face.

Observation:
- Hugging Face model provides encoder-only functionality (sequence embeddings).
- Contains standard transformer files (pytorch_model.bin, tokenizer, config).

Conclusion:
- This is NOT the full generation pipeline used for aptamer design.
- Aptamer generation requires Zenodo checkpoints (diffusion + autoencoder + decoder).

Decision:
- Will not download Hugging Face model at this stage.
- Focus remains on Zenodo checkpoints for reproduction.

## 2026-04-28 — H200 server usage constraints

Reviewed server usage policies.

Key constraints:
- Must register usage before running code (H200ServerBooking.xlsx)
- Datasets must be stored under /Datasets
- Code, environments, and checkpoints must be stored in home directory (~)
- Users are responsible for managing storage and deleting unused files
- Excessive storage usage may result in reduced priority or access restrictions

Adjustments to plan:
- Zenodo model weights will be stored under ~/RNAGenesis/
- Only true datasets (if used) will be stored under /Datasets
- Will monitor storage usage regularly and delete unnecessary files
- Will ensure all runs are registered before execution


## 2026-04-30 — H200 access and system inspection

Successfully logged into H200 server.

System:
- Hostname: aai
- OS: Ubuntu 24.04.4 LTS
- GPUs: 2 x NVIDIA H200 NVL
- NVIDIA driver: 580.95.05
- CUDA version reported by nvidia-smi: 13.0

Initial observations:
- `python` command not available; need to use `python3` or create environment.
- `conda` not available on PATH.
- GPUs were already heavily in use at login, so no GPU workloads were started.

Next:
- Identify available Python/environment tools.
- Decide whether to install Miniconda/Mambaforge under home directory.

## 2026-04-30 — H200 environment setup (initial)

System inspection:
- Python 3.12.3 available as system Python
- No conda/mamba installed
- GPU available but fully in use at login
- Large shared filesystem available (~60TB free)

Decision:
- Will install Miniconda in home directory (~) for isolated environment
- Will not use system Python due to incompatibility with RNAGenesis dependencies
- Will create Python 3.8.13 environment to match repository

Status:
- Miniconda installation in progress / completed
- Environment creation planned next

## 2026-04-30 — H200 environment setup (pre-GPU phase)

Completed:
- SSH access to H200 server
- Installed Miniconda in home directory
- Created rnagenesis-h200 environment (Python 3.8.13)
- Installed core scientific stack and ViennaRNA
- Verified imports

Prepared:
- Cloned RNAGenesis repository on server
- Created directory structure for checkpoints/configs

Deferred:
- PyTorch + CUDA installation
- Model checkpoint downloads
- Pipeline execution

Reason:
- GPUs currently in use
- Will proceed after booking server time

## 2026-04-30 — H200 setup complete

Completed:
- SSH access configured and verified
- GitHub SSH key added for server
- RNAGenesis repo cloned to H200
- Project repo cloned to H200
- Conda environment created (Python 3.8.13)
- Core dependencies installed and verified

Status:
- Environment ready for model installation and checkpoint download

Next:
- Book server usage
- Install PyTorch with CUDA
- Download Zenodo checkpoints
- Begin pipeline execution


## 2026-05-05 — A6000 environment setup and checkpoint download started

Continued Aim 1 Phase 1.4–1.5 by setting up the RNAGenesis execution environment on the A6000 server and beginning the checkpoint/config download process.

### Completed

#### Server access and system inspection
- SSH access to the A6000 server was confirmed.
- Server identified as:
  - Hostname: `warpgolem`
- GPU confirmed available with `nvidia-smi`:
  - NVIDIA RTX 6000 Ada Generation
  - NVIDIA driver: 555.58.02
  - CUDA version reported by `nvidia-smi`: 12.5
- GPU was available for use, with only minor display-related memory usage at login.

#### Conda environment setup
- Used the existing system Anaconda installation:
  - `/opt/anaconda3`
- Created a user-owned conda environment:
  - `/home/laura/.conda/envs/rnagenesis-a6000`
- Environment Python version:
  - Python 3.8.13
- Encountered a permissions issue with the system conda package cache under `/opt/anaconda3/pkgs`.
- Resolved this by configuring conda to use user-owned environment and package directories under:
  - `/home/laura/.conda`

#### PyTorch and CUDA validation
- Installed CUDA-compatible PyTorch:
  - torch 2.1.2+cu121
  - torchvision 0.16.2
  - torchaudio 2.1.2
- Verified PyTorch GPU access:
  - `torch.cuda.is_available()` returned `True`
  - PyTorch CUDA runtime: 12.1
  - PyTorch detected GPU: NVIDIA RTX 6000 Ada Generation

#### Core dependency installation
- Installed and verified core RNAGenesis dependencies:
  - NumPy 1.24.4
  - transformers 4.36.2
  - diffusers 0.25.0
  - huggingface_hub 0.20.3
  - BioPython
  - ViennaRNA
  - einops
  - timm
  - torchinfo
  - tqdm
- Resolved a dependency mismatch:
  - `diffusers==0.25.0` required an older `huggingface_hub` because it imports `cached_download`.
  - Pinned `huggingface_hub==0.20.3`.
  - Pinned `transformers==4.36.2` to remain compatible with `huggingface_hub==0.20.3`.

#### Environment documentation
- Exported the validated A6000 environment to:
  - `environment/environment_a6000.yml`
- Configured Git identity on the server:
  - name: Laura Hardy
  - email: laura.hardy625@gmail.com
- Set up GitHub SSH access from `warpgolem`.

#### Repository setup
- Cloned the project repository:
  - `~/rnagenesis-aptamer-mres`
- Cloned the RNAGenesis fork:
  - `~/RNAGenesis`
- Confirmed RNAGenesis repository commit:
  - `d00899e (HEAD -> main, origin/main, origin/HEAD) Update README.md`

### Checkpoint/config download

- Began Phase 1.5 Zenodo downloads directly on the A6000 server.
- `checkpoints.zip` completed downloading.
- The remaining downloads were moved into a `tmux` session so they can continue after SSH disconnect:
  - tmux session: `rnagenesis-downloads`
- Remaining expected files:
  - `configs.zip`
  - `progen2-base.zip`
  - `progen2-small.zip`

### Notes

- The checkpoint files are large and are not tracked in Git.
- Because the A6000 server is scheduled for formatting after May 8, important code, logs, environment files, and small results must be committed and pushed to GitHub.
- Large Zenodo checkpoint files may need to be redownloaded after the server upgrade unless copied elsewhere.
- The A6000 environment is now ready for RNAGenesis checkpoint verification and, once downloads/extraction are complete, Phase 2 operational reproduction.

### Next

- Reconnect to `warpgolem`.
- Reattach to the download session:
  - `tmux attach -t rnagenesis-downloads`
- Check whether downloads completed.
- Verify file sizes with:
  - `ls -lh ~/RNAGenesis/checkpoints.zip ~/RNAGenesis/configs.zip ~/RNAGenesis/progen2-base.zip ~/RNAGenesis/progen2-small.zip`
- Unzip and verify expected RNAGenesis paths.
- If checkpoint/config structure is correct, proceed to Phase 2: operational reproduction of the aptamer pipeline.

## 2026-05-06 — RNAGenesis checkpoint/config download verified

Completed Aim 1 Phase 1.5 checkpoint/config setup on the A6000 server.

Downloads:
- Downloaded Zenodo RNAGenesis assets directly to `~/RNAGenesis`.
- Total download time was approximately 8 hours.
- Downloaded files:
  - `checkpoints.zip`: 14G
  - `configs.zip`: 15G
  - `progen2-base.zip`: 1.4G
  - `progen2-small.zip`: 536M

Extraction:
- Extracted checkpoint, config, and ProGen decoder files.
- Initial extraction produced nested directories:
  - `checkpoints/checkpoints/...`
  - `configs/configs/...`
  - `progen2-base/progen2-base/...`
  - `progen2-small/progen2-small/...`
- Resolved by flattening extracted directories to match the expected RNAGenesis paths.
- Some extracted directories were read-only (`dr-xr-xr-x`), so permissions were fixed with `chmod -R u+rwX` before moving files.

Verified expected paths:
- `~/RNAGenesis/checkpoints/Aptamer/diffusion`
- `~/RNAGenesis/configs/rnagenesis/autoencoder`
- `~/RNAGenesis/models/autoencoder/decoder/checkpoints/progen2-base`
- `~/RNAGenesis/models/autoencoder/decoder/checkpoints/progen2-small`

Environment re-check:
- Active environment: `/home/laura/.conda/envs/rnagenesis-a6000`
- Python: 3.8.13
- PyTorch: 2.1.2+cu121
- CUDA available to PyTorch: True
- GPU detected by PyTorch: NVIDIA RTX 6000 Ada Generation

Status:
- Phase 1.5 complete.
- Ready to proceed to Phase 2: operational reproduction of the RNAGenesis aptamer pipeline.

Next:
- Inspect RNAGenesis README/example commands.
- Locate the aptamer generation/evaluation entry point.
- Run the first unmodified aptamer pipeline command.
- Log any errors and fixes.


## 2026-05-06 — Phase 2 tiny aptamer generation succeeded

Started Aim 1 Phase 2 operational reproduction of the RNAGenesis aptamer pipeline.

Findings:
- The README aptamer command refers to `generate.py`, but the repository contains `generation.py`.
- `generation.py --help` initially failed due to missing dependencies:
  - `rna-fm`
  - `omegaconf`
- Installed missing dependencies incrementally until `generation.py --help` worked.
- `generation.py` requires additional arguments not shown in the README, including:
  - `--decoder_config`
  - `--num_inference_steps`
  - `--seed`
  - `--eta`
  - `--bos_token`
  - guidance/search placeholder arguments
  - `--remark`
  - `--device`

Decoder/config decision:
- Used decoder config:
  - `config-progen2-small-rna_tokenizer_v2`
- This corresponds to the ProGen2-small RNA decoder config available under:
  - `models/autoencoder/decoder/progen_configs/`

Compatibility issue:
- Initial tiny run loaded the EncDec and diffusion model but failed inside `diffusers.models.normalization.AdaLayerNorm.forward`.
- Error:
  - `ValueError: not enough values to unpack (expected 2, got 1)`
- Cause:
  - `diffusers==0.25.0` used `torch.chunk(emb, 2)` without specifying a dimension, so PyTorch split along `dim=0`.
  - RNAGenesis passed timestep tensors into this AdaLayerNorm path, requiring scale/shift to be split along the feature dimension instead.
- Applied local environment compatibility patch:
  - file: `/home/laura/.conda/envs/rnagenesis-a6000/lib/python3.8/site-packages/diffusers/models/normalization.py`
  - original backed up as: `normalization.py.bak_rnagenesis_2026_05_06`
  - changed:
    - `scale, shift = torch.chunk(emb, 2)`
  - to:
    - `scale, shift = torch.chunk(emb, 2, dim=-1)`

Tiny generation test:
- Ran unguided aptamer generation using:
  - `generation.py`
  - `configs/rnagenesis/autoencoder`
  - `checkpoints/Aptamer/diffusion`
  - `config-progen2-small-rna_tokenizer_v2`
  - `num_inference_steps=5`
  - `batch_size=2`
  - `batch_num=1`
  - `seed=42`
  - `max_seq_len=37`
  - `top_p=0.95`
- Output file:
  - `generation_sequences/RNAGenesis_Aptamer_tiny_test/seqs_wo_guidance_top_p=0.95_2_2_tiny_test_seed42_steps5_batch2_after_adaln_patch.txt`
- Generated sequences:
  - `11CGGGUCGUUUGGUUAUUUGUGGUUGGGUGUGGGGGG`
  - `11GACGUUGGGUGGAUGGGGGGGUAGUUUGGUUUUUUU`

Status:
- First tiny Phase 2 aptamer generation run succeeded.
- RNAGenesis can now generate aptamer-like sequences on the A6000 server.
- Next step is to run a slightly larger small-scale test and then inspect/evaluate output format before attempting larger baseline reproduction.


## 2026-05-06 — Phase 2 small aptamer generation sanity test succeeded

Ran a slightly larger unguided RNAGenesis aptamer generation sanity test after the successful tiny test.

Run settings:
- Entry point: `generation.py`
- Encoder-decoder checkpoint: `configs/rnagenesis/autoencoder`
- Aptamer diffusion checkpoint: `checkpoints/Aptamer/diffusion`
- Decoder config: `config-progen2-small-rna_tokenizer_v2`
- num_inference_steps: 20
- batch_size: 8
- batch_num: 1
- seed: 42
- max_seq_len: 37
- top_p: 0.95
- top_k: 0
- eos_token: `2`
- bos_token: `1`
- guidance: off
- tree/search: off

Output:
- RNAGenesis output directory:
  - `~/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_small_test`
- Output file:
  - `seqs_wo_guidance_top_p=0.95_2_8_small_test_seed42_steps20_batch8.txt`
- Sequence count:
  - 8 sequences, matching expected `batch_size × batch_num`.

Generated sequences:
- `11CGGGUCGUUUGGUUAAUUGUGGUUGGGUGUGGGGGG`
- `11GACGUUGGGUGGAUGGGGGGGUAGUUUGGUUUUUUU`
- `11GUUGGAGGUUUGGUUGGUGUUUUCUUGGUGGGGUGU`
- `11GGUUGGGGAGGCUCUAGGUAUGGUCGGGGGGGGGGG`
- `11GACGUGUGGGGUUCCUUGGUCGGCCGGGCGGUGGUU`
- `11UUCCACGGUUUUUGUUUUGUCUGUGUGUUUGCAAUG`
- `11CGGGGGGGGGUAAUGAGGCGGGUACGUGUGUUAAUU`
- `11UGGGGUGUUAAGGUUGGGUGGAUUGGGGGGUCGGUA`

Notes:
- The run completed successfully after the local `diffusers` AdaLayerNorm compatibility patch.
- The leading `11` prefix appears consistently and likely reflects decoder/BOS-related tokens rather than biological RNA sequence. Downstream structural/evaluation work should consider trimming this prefix and documenting the decision.
- This small test confirms the pipeline remains stable beyond the minimal 5-step tiny test.

Status:
- Phase 2 operational reproduction is progressing.
- RNAGenesis can generate small batches of aptamer-like sequences on A6000.

Next:
- Save the run command as a reproducible script.
- Copy small-test outputs into the project repo.
- Decide the next scaling step, e.g. `batch_size=16`, `batch_num=1`, `num_inference_steps=50`, or begin output-format cleaning/evaluation before scaling further.


## 2026-05-06 — Phase 2 medium aptamer generation test succeeded

Ran a medium-sized unguided RNAGenesis aptamer generation test after the successful tiny and small sanity tests.

Run settings:
- Entry point: `generation.py`
- Encoder-decoder checkpoint: `configs/rnagenesis/autoencoder`
- Aptamer diffusion checkpoint: `checkpoints/Aptamer/diffusion`
- Decoder config: `config-progen2-small-rna_tokenizer_v2`
- num_inference_steps: 50
- batch_size: 16
- batch_num: 1
- seed: 42
- max_seq_len: 37
- top_p: 0.95
- top_k: 0
- eos_token: `2`
- bos_token: `1`
- guidance: off
- tree/search: off

Output:
- RNAGenesis output directory:
  - `~/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_medium_test`
- Output file:
  - `seqs_wo_guidance_top_p=0.95_2_16_medium_test_seed42_steps50_batch16.txt`
- Sequence count:
  - 16 sequences, matching expected `batch_size × batch_num`.

Generated sequences:
- `11CGGGUCGUUUGGUUAAUUUUGGUUGGGUGUGGGGGG`
- `11GACGUUGGGUGGAUGGGGGGGUAGUUUGGUUUUUUU`
- `11GUUGGAGGUUUGGUUGGUGUUUUCUUGGUGGGGUGU`
- `11GGUUGGGGAGGCUCUAGGUAUGGUCGGGGGGGGGGG`
- `11GACGUGUGGGGUUCCUUGGUCGGCCGGGCGGUGGUU`
- `11UUCCACGGUUUUUGUUUUGUCUGUGUGUUUCCAAUG`
- `11CGGGGGGGGGUAAUGAGGCGGGUACGUGUGUUAAUU`
- `11UGGGGUGUUAAGGUUGGGUGGAUUGGGGGGUCGGUA`
- `11GGGUCGGGGGGGGGGGUGGAGUGGUUGCGGGUGUGG`
- `11UGGGGGGGUGGGAUGUGGGUAGGUAGGAGUGGGUGU`
- `11GGUUGGGUACGUUGGUGGGGUUUGGUGUUCUUUUGG`
- `11CGCGGGUGGUGGUUUUUGUCUGGUCCUGGGUCAUGU`
- `11GGGGGCGUGGAAAAUUGGGUUGGGCUGGGCGGGGGU`
- `11GGUGGUUGGCGGUUUGGAUGUGGGUGGUGUUGGUGG`
- `11UUCGUGAGAUCGGGUUGGAUUGGUUCGGAUGAGUGC`
- `11GAGUGGGAGUGGGAUGAAGGAGGUUGGUUGGGUUUG`

Notes:
- The medium run completed successfully after the local `diffusers` AdaLayerNorm compatibility patch.
- Sequence count matched the expected output count.
- The leading `11` prefix persists across generated sequences and should be handled consistently in downstream cleaning/evaluation.
- Several early sequences are very similar to those produced in the smaller tests, consistent with using the same seed and overlapping generation settings.

Status:
- Phase 2 operational reproduction has now progressed from tiny to small to medium successful generation runs.
- The pipeline appears stable for at least `batch_size=16`, `batch_num=1`, and `num_inference_steps=50`.

Next:
- Copy output into the project repo.
- Save the medium-test command as a reproducible script.
- Begin output cleaning/format validation before scaling to larger baseline generation.
- Decide whether to trim leading decoder tokens before structural or sequence-level evaluation.


## 2026-05-07 — A6000 backup before server upgrade

Prepared for scheduled A6000 server upgrade/format.

Backed up to GitHub:
- Project logs in `docs/log.md`
- A6000 environment export in `environment/environment_a6000.yml`
- Start-of-day checklist
- A6000 reinstall procedure
- RNAGenesis tiny/small/medium generation scripts
- Phase 2 tiny/small/medium generated sequence outputs
- AlphaFold structure folders/notes for Phase 2 tiny test where applicable

Important server-only files:
- Large RNAGenesis checkpoint/config zip files and extracted model assets were not committed to GitHub.
- These files are public Zenodo artifacts and may need to be redownloaded after the server upgrade:
  - `checkpoints.zip` (~14G)
  - `configs.zip` (~15G)
  - `progen2-base.zip` (~1.4G)
  - `progen2-small.zip` (~536M)

Documented reinstall procedure:
- Added `docs/a6000_reinstall_procedure.md`.
- Includes:
  - cloning project and RNAGenesis repos
  - recreating the conda environment
  - installing dependencies
  - applying the local `diffusers` AdaLayerNorm compatibility patch
  - redownloading/extracting Zenodo assets
  - verifying checkpoint paths
  - rerunning known working Phase 2 tests

Status before cleanup:
- Phase 1.4 complete: A6000 environment setup
- Phase 1.5 complete: checkpoint/config download and verification
- Phase 1.6 complete: RNAGenesis fork/clone
- Phase 2 started successfully:
  - tiny test succeeded
  - small test succeeded
  - medium test succeeded

Next work item after server upgrade:
- Recreate environment if needed.
- Restore/check repositories from GitHub.
- Redownload checkpoints if needed.
- Resume Phase 2 by writing a cleaning/summary script for generated sequences.
- Cleaning script should remove/handle leading `11` decoder tokens, check RNA alphabet validity, calculate raw/cleaned lengths, detect duplicates, and export cleaned CSV/FASTA files.

## 2026-06-05 — Added null model generation script

Added a small NumPy-based null model script for generating random RNA sequences as a baseline for generator-level evaluation.

Purpose:
- Establish a lower-bound comparison for RNAGenesis-generated aptamer candidates.
- Test whether generated sequences show stronger structural or compositional signal than compositionally matched random RNA.
- Provide a baseline distinct from the Level 2 shuffled-sequence control.

Design decisions:
- Generate 30,000 sequences to match other generation conditions.
- Sample nucleotide identities independently from global corpus-derived A/U/C/G frequencies.
- Sample sequence lengths from the empirical corpus length distribution.
- Use no structural, thermodynamic, positional, or GC-content constraints.
- Use NumPy only; no GPU required.
- Fix and log the random seed for reproducibility.

Rationale:
- Corpus-derived nucleotide frequencies avoid an unrealistically weak uniform-random baseline.
- Empirical length sampling avoids MFE artefacts caused by mismatched length distributions.
- GC content is not directly constrained, so the null model does not partially reproduce the guided GC reward used later in the pipeline.
- The Level 2 shuffled control remains separate: it tests structure-scoring behaviour under dinucleotide-preserving shuffles, whereas this null model is a generation-condition baseline.

Parameters to fill in before generation:
- Corpus nucleotide frequencies: A = ; U = ; C = ; G =
- Corpus length range: min = ; max = ; mean = ; median =
- Length sampling method: empirical histogram with 1-nt bins
- Random seed:
- NumPy version:
- Generation script path:
- Output file path:

## 2026-06-05 - Implemented initial RNAGenesis output cleaning script.

The script reads raw RNAGenesis sequence text files, strips the leading "11" decoder artefact, validates the cleaned RNA alphabet, records raw and cleaned lengths, flags duplicate cleaned sequences, and writes auditable CSV, FASTA, and summary outputs.

Tested on results/phase2_medium_test using condition label unadapted_rnagenesis. The script processed 16 sequences. All 16 had the leading "11" prefix stripped, all 16 were valid RNA after cleaning, no empty sequences or invalid alphabet rows were detected, and no duplicate cleaned sequences were found. Outputs were written to results/phase2_medium_test/cleaned/.

This completes the first cleaning step needed before Stage 1 hard filtering. Biological filtering has deliberately not yet been implemented in this script; it will be handled separately in the Stage 1 filtering module.


## 2026-05-26 H200 CUDA PyTorch verification

Date: 2026-05-26  
Host: aai / H200 server  
Conda environment: rnagenesis-h200  
Python: 3.8.13  
PyTorch: 2.1.2+cu121  
Torch CUDA runtime: 12.1  
CUDA available: True  
GPU count: 2  
GPU detected: NVIDIA H200 NVL  

Verification:
- Successfully imported torch
- `torch.cuda.is_available()` returned True
- CUDA tensor multiplication test passed

Decision:
- PyTorch installed via pip CUDA wheels rather than conda because conda solver failed under the Python 3.8/OpenBLAS environment.
- Proceeding to Zenodo checkpoint/config download.

## 2026-05-26 RNAGenesis asset installation and first import issue

Date: 2026-05-26  
Host: aai / H200  
RNAGenesis path: `~/RNAGenesis`  
Environment: `rnagenesis-h200`

Asset installation status:
- `checkpoints/`: 15G
- `configs/`: 20G
- `models/autoencoder/decoder/checkpoints/progen2-base`: 1.5G
- `models/autoencoder/decoder/checkpoints/progen2-small`: 578M
- `checkpoints/Aptamer/diffusion`: 7.4G

Key files observed:
- `configs/rnagenesis/autoencoder/pytorch_model.bin`
- `checkpoints/Aptamer/diffusion/unet/diffusion_pytorch_model.safetensors`
- `models/autoencoder/decoder/checkpoints/progen2-base/pytorch_model.bin`
- `models/autoencoder/decoder/checkpoints/progen2-small/pytorch_model.bin`

Attempted:
- `python generation.py --help`

Result:
- Failed at import stage with `ModuleNotFoundError: No module named 'fm'`
- Error occurs via `models/autoencoder/encdec.py`, which imports `fm.modules`

Interpretation:
- Checkpoint/config installation appears successful.
- The next blocker is a missing Python dependency or missing local module, likely related to the encoder stack.

## 2026-06-10 — H200 diffusers patch recorded

Recorded the local H200 `diffusers` compatibility patch in `docs/run_notes/h200_tiny_test_summary.md`.

Verified patched line:
- `/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/site-packages/diffusers/models/normalization.py:46`
- `scale, shift = torch.chunk(emb, 2, dim=-1)`

Note:
- This manual site-package patch is not captured by `conda env export`, so it must remain documented separately for reproducibility.

## 2026-06-10 — Added accelerate to H200 environment

Installed `accelerate==0.25.0` into the `rnagenesis-h200` environment to support the Hugging Face `transformers`/`diffusers` stack used by RNAGenesis generation.

Updated:
- `environment/environment_h200.yml`

## 2026-06-10 — Started H200 unadapted RNAGenesis 30k baseline generation

Started Phase 4.1 unadapted RNAGenesis baseline generation on the H200 server.

Run context:
- Host: aai / H200
- RNAGenesis repo: `~/RNAGenesis`
- Project repo: `~/rnagenesis-aptamer-mres`
- Conda environment: `rnagenesis-h200`
- Script: `scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh`
- tmux session: `rnagenesis_baseline_30k_gpu1`
- GPU isolation: `CUDA_VISIBLE_DEVICES=1`
- Physical GPU used: GPU1

Pre-run status:
- H200 tiny, small and medium operational reproduction tests completed successfully.
- GPU1 was confirmed clear before launch.
- Git working tree was clean before launching the long run.
- Script passed `bash -n`.

Generation configuration:
- Output folder: `~/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_baseline_30k`
- 10 chunks
- Seeds: 4201–4210
- `num_inference_steps=50`
- `batch_size=16`
- `batch_num=188`
- Expected raw total: 30,080 sequences

Launch command:
```bash
tmux new -s rnagenesis_baseline_30k_gpu1
cd ~/rnagenesis-aptamer-mres
bash scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh \
  2>&1 | tee docs/run_notes/h200_baseline_30k_output.log
Initial monitoring:

nvidia-smi showed a Python process on GPU1.
GPU1 utilisation rose to approximately 94%.
GPU0 remained occupied by other users' jobs and was not affected.

Status:

Long baseline generation run is currently active inside tmux.

## 2026-06-10 — Completed H200 unadapted RNAGenesis 30k baseline generation

Completed Phase 4.1 unadapted RNAGenesis baseline generation on the H200 server.

Run context:
- Host: aai / H200
- RNAGenesis repo: `~/RNAGenesis`
- Project repo: `~/rnagenesis-aptamer-mres`
- Conda environment: `rnagenesis-h200`
- Script: `scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh`
- tmux session: `rnagenesis_baseline_30k_gpu1`
- GPU isolation: `CUDA_VISIBLE_DEVICES=1`
- Physical GPU used: GPU1

Output:
- Folder: `~/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_baseline_30k`
- Chunks completed: 10/10
- Sequences per chunk: 3,008
- Total raw sequences: 30,080

Runtime:
- Start: Wed 10 Jun 2026 16:11:51 AEST
- End: Wed 10 Jun 2026 17:39:40 AEST
- Elapsed: 1 hour, 27 minutes, 49 seconds
- Total elapsed seconds: 5,269
- Approximate throughput: 5.71 raw sequences per second

Chunk timing:
- Each chunk took approximately 8 minutes 45–49 seconds.
- Runtime was consistent across all 10 chunks.

Status:
- Run completed successfully.
- Raw generated sequence files remain outside Git under `~/RNAGenesis/generation_sequences/`.
- Next step: merge/clean generated outputs, deduplicate, and prepare exactly 30,000 sequences for baseline characterisation.

## 2026-06-10 — Completed Phase 2.4 H200 repeatability check

Completed Phase 2.4 of the RNAGenesis reproduction workflow: fixed random seeds and confirmed repeatability on the H200 server.

Run context:
- Host: aai / H200
- RNAGenesis repo: `~/RNAGenesis`
- Project repo: `~/rnagenesis-aptamer-mres`
- Conda environment: `rnagenesis-h200`
- Script: `scripts/run_rnagenesis_phase2_4_repeatability_h200.sh`
- Analysis script: `scripts/analyze_phase2_4_repeatability.py`
- GPU isolation: `CUDA_VISIBLE_DEVICES=1`

Test design:
- Ran the same small aptamer generation workload twice with seed 42.
- Ran the same workload once with seed 43.
- Workload:
  - `num_inference_steps=20`
  - `batch_size=8`
  - `batch_num=1`
  - `max_seq_len=37`
  - `top_p=0.95`
  - `top_k=0`

Outputs:
- RNAGenesis raw outputs remain under `~/RNAGenesis/generation_sequences/`.
- Small copied outputs for reproducibility checking are stored under:
  - `results/phase2_4_repeatability/`
- Markdown report:
  - `docs/run_notes/h200_phase2_4_repeatability_report.md`

Result:
- Same-seed outputs were compared byte-for-byte and by SHA256 hash.
- Different-seed output was compared against the seed 42 run.
- See the Phase 2.4 report for exact hashes, line counts and interpretation.

Status:
- Phase 2.4 repeatability check completed successfully.
- Next step: proceed to cleaning, merging, deduplicating and characterising the 30,080-sequence unadapted RNAGenesis baseline pool.

## 2026-06-10 — Saved Phase 4.1 raw baseline outputs into project repo

Saved the successful H200 unadapted RNAGenesis baseline generation outputs into the MRes project repository structure.

Source:
- `~/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_baseline_30k`

Project copy:
- `results/phase4_1_unadapted_rnagenesis_30k/raw/`

Raw output:
- 10 chunk files
- 3,008 sequences per chunk
- 30,080 raw generated sequences total
- Total size approximately 1.2 MB

Version-control decision:
- Because the generated sequence files are small text files and represent a core Phase 4.1 research artifact, they will be committed to Git.
- Large model checkpoints and Zenodo assets remain excluded from Git.

Next step:
- Verify checksums after syncing to the Mac.
- Proceed to cleaning, merging, deduplicating and preparing exactly 30,000 sequences for baseline characterisation.

## 2026-06-10 — Removed duplicate RNAGenesis baseline output folder from aai

After copying and committing the Phase 4.1 unadapted RNAGenesis baseline outputs into the MRes project repo, removed the duplicate generated-output folder from the RNAGenesis repo on the shared H200 server.

Deleted duplicate source folder:
- `~/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_baseline_30k`

Retained project copy:
- `~/rnagenesis-aptamer-mres/results/phase4_1_unadapted_rnagenesis_30k/raw/`

Verification:
- Project copy retained 30,080 raw generated sequences across 10 chunk files.

Rationale:
- Avoid retaining duplicate generated results indefinitely in the RNAGenesis working directory on a shared server.

## 2026-06-11 — Reproduced RNAGenesis repository aptamer evaluation on full baseline pool

Completed Stage 2.3 by reproducing the RNAGenesis repository-provided aptamer evaluation procedure on generated outputs.

The repository evaluation procedure is implemented in:
- `~/RNAGenesis/test_wrap_aptamer.py`

The project wrapper is:
- `scripts/run_repo_aptamer_evaluation.py`

The H200 runner is:
- `scripts/run_phase2_3_repo_aptamer_eval_h200.sh`

Evaluation scope:
- Medium test output: 16 generated sequences
- Baseline chunk 1: 3,008 generated sequences
- Full unadapted baseline pool: 30,080 generated sequences

Repository metrics reproduced:
- Secondary-structure similarity threshold pass rate
- MFE-difference threshold pass rate

Default parameters:
- Similarity threshold: `threshold_a = 80.0`
- MFE-difference threshold: `threshold_b = 2.0` kcal/mol
- Base-pair distance factor: `factor = 2.0`

Important repository behaviour:
- The original RNAGenesis CLI runs silently because `run_rna_analysis()` returns metrics but does not print them.
- The project wrapper imports the repository functions directly and verifies that its exposed values match `run_rna_analysis()`.
- Raw `seqs_wo_guidance_*.txt` outputs were used directly to preserve repository-faithful preprocessing.
- The full baseline evaluation used a merged raw input file with 30,080 lines:
  - `results/phase2_3_repo_evaluation/inputs/merged_30080_raw.txt`

Full baseline result:
- Run label: `baseline_30080_full`
- Timestamp (UTC): `2026-06-11T07:38:37.302606+00:00`
- Host: `aai`
- RNAGenesis commit: `d00899e`
- Raw lines: 30,080
- Candidates after repo preprocessing: 30,080

Reference aptamer:
- Sequence: `TCCAGCACTCCACGCATAACGGCGGTGGGTGGGTTGTTGTGGGAGGGGGAGGGGGAGTTATGCGTGCTACCGTGAA`
- Reference MFE: -24.200001 kcal/mol
- Reference structure: `.((..(.((((.(.(((((((((.........))))))))).).)))))..))(((((.......))).)).....`

Aggregate metrics for the full 30,080-sequence baseline:
- Proportion passing secondary-structure similarity threshold (`similarity >= 80.0`): **0.000000%**
- Proportion passing MFE-difference threshold (`mfe_diff <= 2.0 kcal/mol`): **35.511968%**

Per-sequence summary statistics:
- Similarity:
  - mean: 6.197090
  - min: 0.000000
  - max: 69.090909
- MFE:
  - mean: -21.968365 kcal/mol
  - min: -39.299999 kcal/mol
  - max: -12.280000 kcal/mol
- MFE difference from reference:
  - mean: 3.260825 kcal/mol
  - min: 0.000000 kcal/mol
  - max: 15.099998 kcal/mol

Earlier smoke-test results:
- `medium_test_16`:
  - n = 16
  - prop_similarity = 0.0%
  - prop_mfe = 25.0%
- `baseline_30k_chunk1`:
  - n = 3,008
  - prop_similarity = 0.0%
  - prop_mfe = 34.61%

Outputs:
- Full summary markdown:
  - `results/phase2_3_repo_evaluation/summaries/baseline_30080_full_repo_eval_summary.md`
- Full summary JSON:
  - `results/phase2_3_repo_evaluation/summaries/baseline_30080_full_repo_eval_summary.json`
- Full evaluation log:
  - `results/phase2_3_repo_evaluation/logs/baseline_30080_full_repo_eval.log`
- Medium-test per-sequence output:
  - `results/phase2_3_repo_evaluation/per_sequence/medium_test_16_repo_eval_per_sequence.csv`
- Run log:
  - `docs/run_notes/h200_phase2_3_repo_eval_full_30080.log`

Interpretation:
- The full unadapted RNAGenesis baseline produced no candidates meeting the repository's high secondary-structure similarity threshold of 80.0.
- Approximately one third of candidates met the repository's MFE-difference threshold of 2.0 kcal/mol relative to the hard-coded reference aptamer.
- This reproduces the repository's own aptamer evaluation procedure but does not replace the later project-specific baseline characterisation pipeline.

Status:
- Stage 2.3 repository evaluation reproduction completed.
- Full custom baseline characterisation metrics remain deferred to a later project stage.
- Raw lines: 30,080
- Candidates after repo preprocessing: 30,080

Reference aptamer:
- Sequence: `TCCAGCACTCCACGCATAACGGCGGTGGGTGGGTTGTTGTGGGAGGGGGAGGGGGAGTTATGCGTGCTACCGTGAA`
- Reference MFE: -24.200001 kcal/mol
- Reference structure: `.((..(.((((.(.(((((((((.........))))))))).).)))))..))(((((.......))).)).....`

Aggregate metrics for the full 30,080-sequence baseline:
- Proportion passing secondary-structure similarity threshold (`similarity >= 80.0`): **0.000000%**
- Proportion passing MFE-difference threshold (`mfe_diff <= 2.0 kcal/mol`): **35.511968%**

Per-sequence summary statistics:
- Similarity:
  - mean: 6.197090
  - min: 0.000000
  - max: 69.090909
- MFE:
  - mean: -21.968365 kcal/mol
  - min: -39.299999 kcal/mol
  - max: -12.280000 kcal/mol
- MFE difference from reference:
  - mean: 3.260825 kcal/mol
  - min: 0.000000 kcal/mol
  - max: 15.099998 kcal/mol

Earlier smoke-test results:
- `medium_test_16`:
  - n = 16
  - prop_similarity = 0.0%
  - prop_mfe = 25.0%
- `baseline_30k_chunk1`:
  - n = 3,008
  - prop_similarity = 0.0%
  - prop_mfe = 34.61%

Outputs:
- Full summary markdown:
  - `results/phase2_3_repo_evaluation/summaries/baseline_30080_full_repo_eval_summary.md`
- Full summary JSON:
  - `results/phase2_3_repo_evaluation/summaries/baseline_30080_full_repo_eval_summary.json`
- Full evaluation log:
  - `results/phase2_3_repo_evaluation/logs/baseline_30080_full_repo_eval.log`
- Medium-test per-sequence output:
  - `results/phase2_3_repo_evaluation/per_sequence/medium_test_16_repo_eval_per_sequence.csv`
- Run log:
  - `docs/run_notes/h200_phase2_3_repo_eval_full_30080.log`

Interpretation:
- The full unadapted RNAGenesis baseline produced no candidates meeting the repository's high secondary-structure similarity threshold of 80.0.
- Approximately one third of candidates met the repository's MFE-difference threshold of 2.0 kcal/mol relative to the hard-coded reference aptamer.
- This reproduces the repository's own aptamer evaluation procedure but does not replace the later project-specific baseline characterisation pipeline.

Status:
- Stage 2.3 repository evaluation reproduction completed.
- Full custom baseline characterisation metrics remain deferred to a later project stage.

## 2026-06-19 — Aim 3 Stage 1 hard filtering

Implemented the first Aim 3 filtering stage: binary hard filtering for intrinsic RNA sequence quality.

Created:
- `src/aim3_pipeline/` package (`config.py`, `io.py`, `stage1_hard_filter.py`)
- Config-driven CLI: `scripts/run_stage1_hard_filter.py`
- Default config: `configs/stage1_hard_filter_default.json`
- Tests: `tests/test_stage1_hard_filter.py` (13 passed)
- Run notes: `docs/run_notes/stage1_hard_filtering.md`

Stage 1 functionality:
- Canonical RNAGenesis preprocessing (leading `11` strip, uppercase, metadata)
- RNA alphabet validation (A/U/C/G)
- Exact within-condition deduplication (keep first occurrence)
- Homopolymer run filter (default fail if max run ≥ 5)
- GC fraction computation
- ViennaRNA MFE, dot-bracket structure, and normalised MFE computation
- Placeholder / reference-dependent near-deduplication (not applied without corpus)
- Per-filter status columns, `stage1_pass`, and `stage1_failure_reasons`

Runs:
- Medium smoke test (`results/phase2_medium_test/`): 16 processed, 6 passed, 10 failed — all failures due to homopolymer runs ≥ 5.
- Unadapted 30k baseline (`results/phase4_1_unadapted_rnagenesis_30k/raw/`): 30,080 processed, 13,136 passed, 16,944 failed — pass rate 43.7%. All failures were homopolymer runs ≥ 5; alphabet validity and exact deduplication removed no sequences.

Reference-free filters not yet applied as exclusion criteria (computed or scaffolded only until AptaDiff / training corpus thresholds are available): length bounds, GC bounds, MFE threshold, near-deduplication.

Outputs written to `results/aim3_stage1_medium_test/` and `results/aim3_stage1_unadapted_30k/`; these are regenerable and should remain uncommitted.

Status:
- Stage 1 hard filtering implemented and QA-checked.
- Next: download reference aptamer corpus (AptaDiff Dataset A) for Stage 0 validation and empirical Stage 1 threshold calibration.

## 2026-06-22 - 2026-06-26

## Poster preliminary results preparation

Prepared and committed the poster-stage preliminary results workflow on the `poster-stage1-preliminary-results` branch, then pushed the branch to GitHub and returned to `main`. The work established an Aptadiff Dataset A-calibrated reference workflow for comparing unadapted RNAGenesis outputs against a composition- and length-matched null model. I estimated Dataset A nucleotide, GC, length, and MFE reference distributions; generated 30,000 null model RNA sequences using the empirical mononucleotide and length distributions; created Stage 1 poster configs with Dataset A-derived GC and lenient MFE thresholds; and ran Stage 1 filtering on both the null model and unadapted RNAGenesis pools. The final preliminary Stage 1 pass rates were similar between conditions, with homopolymer filtering as the dominant rejection driver and the very lenient MFE threshold adding no further exclusions. I also generated the poster-ready preliminary result figures: an illustrative RNAfold/ViennaRNA secondary structure from a passed RNAGenesis sequence, a Level 1 pass-rate comparison, and a GC content distribution plot with Dataset A 5th–95th percentile bounds. These results are intended as preliminary poster evidence only: Dataset A is a proxy reference subset, and passing Stage 1 filters does not imply NDM-1 binding or aptamer function.

## 2026-05-05 - 2026-08-04 — Raw aptamer dataset search and curation-input inventory

### Context and objective

Completed the principal search for raw aptamer data to support construction of the project corpus. The main search was completed on 28 July 2026 and the raw-data inventory was refreshed on 4 August 2026. The search began with the original aim of finding target-specific RNA HT-SELEX or activity-screening data for carbapenemases at a scale suitable for fine-tuning. No such dataset was identified for KPC-2, NDM-1 or OXA-48. However, seven RNA aptamers reported against NDM-1 were recovered from the selektion source and retained as evaluation references. The resulting strategy is to assemble a curated multi-source corpus of published RNA aptamers with experimentally supported protein targets, rather than treating a large late-round SELEX pool against one unrelated target as equivalent to a general aptamer corpus.

This is a data-discovery and raw-input milestone, not completion of the cleaned corpus. No cross-source master corpus has yet been created. The next pipeline stage, S0, will freeze an explicit source registry and construct the leakage-exclusion set. Source-specific extraction, normalisation and eligibility filtering occur subsequently at S1, S2 and S3. Cross-source target normalisation, deduplication, clustering, balancing and partitioning do not occur until later stages.

### Intended downstream uses

| Use | Role of the corpus | Data-separation requirement |
|---|---|---|
| RNAGenesis fine-tuning | Shift the RNA foundation model towards the distribution of experimentally reported, protein-binding RNA aptamers so that it generates aptamer-like RNA sequences for subsequent NDM-1 candidate generation. | Use only the `FT` partition for model adaptation. A later RNA-aware split will divide `FT` into train and validation subsets at cluster level. |
| AptaRank reference distributions | Define empirical distributions for sequence and predicted secondary-structure features used to score generated candidates relative to validated RNA aptamers. | Fit all calibration distributions from the independent `REF` partition only, not from `FT`. |
| AptaRank evaluation | Test whether the tool ranks held-out validated aptamers above suitable controls and model-generated candidates without leakage from calibration. | Use the cluster-held-out `EVAL` partition only. No sequence cluster may span `FT`, `REF` and `EVAL`. |
| Target-specific biological grounding | Retain known NDM-1, KPC-2 and related carbapenemase aptamers as positive references and methodological examples. | Route all carbapenemase and human-serum-albumin sequences to the leakage-exclusion/evaluation lane. The NDM-1 D9 records are RNA aptamers reported in DNA alphabet; genuine ssDNA references remain ssDNA. |

### Corpus design decision

The target training distribution is **diverse published RNA aptamers that bind proteins**, not all sequences observed in a single HT-SELEX experiment. This decision follows from the project objective: the model should learn transferable RNA aptamer sequence and structural regularities rather than reproduce the enriched sequence distribution of one experiment and one target.

The corpus should therefore:

- contain RNA aptamer sequences with a resolved protein or protein-domain target;
- prioritise experimentally selected and reported binders over unselected library members or bulk late-round reads;
- span many protein targets and protein families, including enzymes and non-enzyme proteins;
- avoid domination by a single target, publication, database, experimental family or highly similar sequence family;
- preserve selection, assay, source and publication provenance wherever available;
- distinguish exact duplicates from near-duplicate variants rather than treating every database row as independent;
- retain enough source and family identifiers to support leakage-aware cluster-level `FT`/`REF`/`EVAL` partitioning and the later train/validation split within `FT`; and
- keep true DNA aptamers separate rather than converting them to RNA solely to increase corpus size.

One corpus record is one `(sequence, target)` pair. A sequence reported against two targets therefore remains two records, while clustering is performed on sequence so that all occurrences remain in one partition. A sequence written with `T` may be converted to `U` only when the source establishes that it represents an RNA aptamer or an RNA sequencing representation, and the transformation must be recorded in `alphabet_as_reported` and `t_to_u_applied`. A genuine ssDNA aptamer is not made an RNA aptamer by alphabet substitution and remains outside the primary RNA corpus.

### Search strategy

The search was organised into target-specific, general-corpus, related-work and supplementary workstreams. Search actions, zero-result searches, access dates, URLs/accessions, candidate decisions and follow-up actions were recorded in `dataset_search_log.xlsx`.

| Workstream | Principal sources searched | Representative search concepts | Purpose and outcome |
|---|---|---|---|
| Carbapenemase-specific repositories | NCBI GEO, NCBI SRA, NCBI Nucleotide/GenBank and ENA | `KPC`, `KPC-2`, `NDM`, `NDM-1`, `New Delhi metallo-beta-lactamase`, `OXA-48`, `carbapenemase`, `beta-lactamase` combined with `aptamer`, `SELEX`, `HT-SELEX` and `SELEX-seq` | Searched first for target-specific RNA sequencing data. No suitable RNA HT-SELEX corpus was identified. The main NDM-1 sequencing hit, BioProject `PRJNA830749`, contains ssDNA selection pools and was retained as target-specific reference material rather than direct RNA fine-tuning data. |
| Patents and target-specific papers | Google Patents, Espacenet, PubMed/full text and supplementary files | Carbapenemase target names plus `RNA aptamer`, `DNA aptamer`, `nucleic acid aptamer`, `oligonucleotide aptamer` and `SELEX` | Recovered small numbers of reported KPC-2/NDM-1 aptamers and selection tables. These are valuable for evaluation and biological context but are too small and often DNA-based for the main training corpus. |
| Curated aptamer databases | AptaDB, Apta-Index, UTexas Aptamer Database, AptamerBase, AptaBase, RiboaptDB/RiboCentre and SELEX-DB | RNA aptamers, protein/enzyme targets, target name, molecule type and sequence availability | Identified the main source collections for the multi-source corpus. Most require molecule-type filtering, target resolution, sequence cleaning and substantial cross-source deduplication. |
| Datasets used in aptamer ML papers | AptaDiff, RaptGen, RaptRanker, AptaBLE, AptaGPT, InstructNA and RBM-based aptamer modelling | Paper/repository names plus `data`, `GitHub`, `HT-SELEX` and accession searches | Confirmed that several related papers reuse the same target-specific HT-SELEX datasets. AptaDiff datasets were acquired for comparison or fallback use, but they are not the preferred general RNA aptamer corpus. Some reported data, including the approximately 4,000 AptaGPT round-20 sequences, were not publicly available. |
| Broader archive searches | ENA text search, NCBI GEO/SRA simplified searches and NCBI Nucleotide `RNA aptamer` searches | Initially complex Boolean searches, followed by simpler source-native queries | Complex archive queries frequently returned no useful results or were poorly matched to archive search interfaces. Searches were simplified and candidate records were then screened manually. |
| Synthetic-data feasibility | Literature searches for `in silico SELEX`, computational SELEX simulation and synthetic aptamer datasets | Synthetic augmentation and simulated selection | Full in silico SELEX was not adopted because it would require a defensible RNA-protein binding or enrichment model and would exceed the MRes scope. Synthetic data will not substitute for experimentally supported aptamers in the reference corpus. |

This was a structured project dataset search rather than a formal systematic review. Major named databases, sequence archives, related-work repositories, patents and known carbapenemase papers were covered. Broad paper-by-paper Google Scholar mining beyond the already identified literature was limited, and this limitation should be stated in the thesis.

### Eligibility criteria for the primary RNA protein-aptamer corpus

| Criterion | Required rule at S0 | Rationale |
|---|---|---|
| Molecule type | Record must represent RNA. Accept `U` sequences and `T`-encoded records only where RNA identity is supported by source metadata or publication context. | RNAGenesis is RNA-native, and DNA and RNA aptamer sequence/structure distributions are not interchangeable. |
| Target type | Target must be a protein, enzyme or resolved protein domain/region. | The model is being adapted for protein-binding aptamer generation against NDM-1. |
| Sequence availability | A concrete aptamer sequence must be recoverable after removal of explicit notation, modifications and non-sequence formatting. | Sequence-only names, paper indexes and target records cannot train or calibrate the model. |
| Aptamer status | Sequence must be presented as a selected, enriched or experimentally tested aptamer/candidate, with provenance sufficient to distinguish it from a random library template. | Prevents unselected degenerate pools, primers and natural RNAs from entering the validated-aptamer distribution. |
| Evidence/provenance | Retain source database, source record ID, publication/patent reference and available binding/selection evidence. Direct affinity measurements are preferred but not mandatory if selection provenance is credible. | Supports auditability, evidence stratification and later sensitivity analyses. |
| Sequence role | Exclude full degenerate libraries, primer-only records, promoter-containing templates unless the aptamer region can be resolved, and ambiguous constructs that cannot be interpreted confidently. | Ensures the model sees aptamer sequences rather than experimental scaffolds or unresolved constructs. |
| Target resolution | Normalise synonyms but retain the original target string and target region. Exclude unresolved cell/tissue targets unless a specific protein target is documented. | Enables target-family balancing and avoids treating whole-cell selections with unknown molecular targets as protein-binding examples. |
| Duplication | Retain one canonical sequence-target pair with merged provenance; preserve evidence that several sources or accessions reported it. | Prevents repeated database copies from overweighting famous aptamers. |
| Near-duplicate families | Cluster related variants and retain family/group identifiers. Variants may remain as separate sequences where experimentally distinct, but must be grouped for weighting and splitting. | Avoids family-level leakage and overrepresentation of mutational series or patent clone families. |
| Length and alphabet | Require a valid canonical RNA `sequence_core` of 20–100 nt after justified normalisation. Records at 20–25 nt and 90–100 nt are flagged; records pushed below 20 nt by trimming are reviewed before rejection. | The fixed range matches the intended generation window while retaining an audit path for boundary cases and potentially over-aggressive trimming. |
| Availability and reuse | Source must permit project use; redistribution restrictions must be recorded. | Apta-Index access is subject to a data-use agreement and may constrain release of the combined corpus. |

### Records retained outside the primary training corpus

| Record class | Planned handling |
|---|---|
| Experimentally reported ssDNA aptamers against NDM-1, KPC-2 or related targets | Keep as a separate target-specific positive-reference/evaluation set. Do not include in RNA training or RNA reference distributions by default. |
| AptaDiff datasets A and B | Include in the Tier-1 build but cap each target at cluster level during balancing so that IGFBP3 and PTK7 do not dominate. Preserve Dataset A separately and uncapped for the replication/comparability run. |
| AptaDiff datasets C and D | Defer from v1 because they lack target annotation and add preprocessing cost without target diversity; revisit only if the diverse corpus is too small. |
| Small-molecule, ion, metabolite, cell, tissue and organism aptamers | Exclude from the primary protein corpus unless a resolved protein target is explicitly documented; retain source records for possible future corpora. |
| Natural riboswitches, genomic motifs, regulatory RNAs and non-aptamer binding motifs | Exclude because the selection objective is experimentally selected protein-binding aptamers. |
| Non-standard oligonucleotide-like polymers such as HFNAPs | Exclude from the canonical RNA corpus because their chemical side chains and alphabet are not represented by standard RNA sequence. |
| Synthetic/generated sequences | Keep separate from validated aptamers and never use them to define the empirical validated-aptamer reference distribution. |
| Records without a sequence or with unresolved sequence notation | Hold for manual review or exclude with a documented reason. |
| Inaccessible or sequence-free discovery indexes | Use only for literature discovery and cross-checking, not as direct corpus inputs. |

### Raw data assembled and current planned role

The raw inventory contains overlapping records; the row counts below are source-file counts and must not be added to estimate the final corpus size.

| Source | Principal raw artefact(s) | Observed raw size | Planned role and main curation issues |
|---|---|---:|---|
| AptaDB | `aptamer.csv`, `interaction.csv`, `protein.csv` | 1,293 aptamer rows; 1,350 interaction rows; 194 protein rows | High-priority source. Join aptamer, interaction and protein information; filter molecule and target chemistry; resolve conflicting targets; deduplicate repeated sequence-target pairs. |
| Apta-Index | `aptamers-export-2026-07-22.csv` plus data-use agreement | 1,050 rows | High-priority mixed aptamer source with target, affinity and conditions. Filter to RNA/protein rows, clean sequence notation and respect redistribution restrictions. The inventory found missing sequences/targets, duplicated sequences and extensive formatting/modification notation. |
| UTexas Aptamer Database | `UTexas Aptamer Database dataset_Sept2023.xlsx` | 1,894 tabular rows | High-priority, well-annotated mixed source. Reconcile the workbook row count with earlier database-level counts; filter RNA/protein records and resolve 399 rows without observed sequences. |
| AptamerBase | `aptamerbase_aptamers.csv` | 2,128 rows | Broad mixed source. Requires target information to be recovered or joined from source context, removal of missing sequences and consolidation of duplicated sequences. |
| AptaBase | `aptabase_cleaned.csv` | 610 rows | Registered Tier-1 input. Use its `sequence_raw` field as the adapter input and run the shared normaliser again so the corpus alphabet policy is applied uniformly. `aptabase_raw.csv` and cached HTML are forbidden as parallel inputs because they would duplicate the same scrape. |
| RiboaptDB/RiboCentre | `all_sequences_509_rows.csv` plus README | 509 rows | Valuable RNA-focused source. Use `Category`, `Type` and description fields to separate protein aptamers from small-molecule and other categories before inclusion. |
| ENA | `ena_embl_20260720-0853.txt`; reviewed selected lane in `review_v2/` | 5,841 source records; 679 selected unique sequence-target pairs | Supplementary archive-derived source. The original EMBL download is retained as raw provenance. The manually reviewed selected file is the authoritative ENA lane for later cleaning and cross-source integration. |
| NCBI Nucleotide/GenBank | 18 `.gb` records | 18 records | Small supplementary set. Review each record for RNA identity, sequence role, target resolution and overlap with curated databases/ENA. |
| KPC-2 Precision-SELEX paper | `extracted_data.xlsx` plus schema README and paper | 20 aptamer records in a 43-row workbook layout | ssDNA evaluation source. Parse the N40 sequence from column B and the construct from column D using the documented multi-row layout; retain the incomplete column-I heading as a note rather than guessing. |
| Other carbapenemase papers | Chen et al. table, NDM-1 selection table and Shi et al. table | 8, 7 and 2 rows respectively | Small target-specific collections. Review true molecular target, sequence type, controls, primers/modifications and overlap. Keep DNA/cell-binding records outside the primary RNA training lane. |
| AptaDiff datasets | Dataset A/B CSV files; Dataset C/D FASTQ files retained locally | 13,803; 11,547; 80,864; 121,185 rows/reads | Dataset A and B are Tier-1 inputs, computationally transcribed to RNA with provenance recorded, then aggressively capped by target at cluster level. Dataset A is also exported uncapped for replication. Dataset C/D are deferred from v1 because target annotation and adapter state are unresolved. |
| NDM-1 SRA metadata | `PRJNA830749` run metadata | 8 public runs | Target-specific ssDNA SELEX metadata. Retain for reference and possible later preprocessing, but not direct RNA corpus inclusion. |

Sources investigated but not selected as direct raw inputs included Maptamer (principally an index without sequences), SELEX-DB (old/inaccessible sequence interface), HTP-SELEX transcription-factor DNA data, private BasePair Bio data, non-public AptaGPT data and sources whose chemistry or target class did not match the corpus objective.

### ENA search and manual-review outcome

ENA was treated separately because the search result was a heterogeneous EMBL text download rather than a curated aptamer table. The search produced 5,841 accession records. Automated parsing and conservative triage were used to expose sequence, target, publication and evidence fields while preserving the deposited record and accession-level provenance.

The review workflow grouped accessions into sequence-target units, experiment groups and near-duplicate families before manual decisions. This reduced repeated clerical review of patent clone families and allowed group-level exclusion of unsuitable experimental sources. Natural motifs, riboswitches, non-protein aptamers, degenerate libraries, unresolved constructs and records without sufficient aptamer evidence were separated from plausible RNA aptamer-protein records.

The final reviewed ENA lane is:

- `data/raw/ENA/review_v2/ena_selected_after_manual_review.csv`
- 679 unique sequence-target pairs;
- 37 columns, including both `experiment_group_id` and `near_duplicate_family_id`;
- 230 rejected rows in `ena_rejected_after_manual_review.csv`;
- 0 unreviewed rows in `ena_unreviewed_after_manual_review.csv`; and
- 924 accession-level provenance rows in `ena_selected_sequence_provenance.csv`.

The two grouping fields must be retained beyond S0. `experiment_group_id` supports group-wise decisions, source-aware weighting and leakage-safe splitting. `near_duplicate_family_id` supports family-aware clustering, balancing and validation of the later sequence-similarity pipeline. Approximately 46% of selected rows have no near-duplicate family identifier. The curation specification resolves these as singletons: S1 will materialise deterministic `ena_singleton_{n}` identifiers and record family size 1, while retaining the original missingness in provenance. The separate 679-versus-676 ENA export difference remains a required CHECKPOINT-1 reconciliation.

The older empty file `data/raw/ENA/review/ena_selected_after_manual_review.csv` is superseded and must not be ingested. Although the final reviewed file is technically a derived manual-review output rather than an untouched raw download, it is the authoritative selected ENA input lane for the next corpus stage; the original EMBL file remains the raw source of record.

### Raw inventory and reproducibility controls

Generated `raw_data_inventory.csv` to capture the state of the complete `data/raw/` tree before S0 processing. The inventory records relative path, source, file role, size, modification time, SHA-256 hash, readability, row and column counts, observed schema, candidate sequence/target/label/provenance columns, inferred sequence and target types, issue flags, associated documentation, recommended S0 status and changes since the previous inventory.

Inventory summary:

| Recommended S0 status | File count | Interpretation |
|---|---:|---|
| `include_as_authoritative_input` | 37 | Source tables, exports, archive records or reads from which S0 processing should begin. |
| `include_with_documented_caveat` | 16 | Papers, READMEs and agreements required to interpret or license the data, but not sequence rows themselves. |
| `hold_for_manual_review` | 78 | Cached HTML, metadata, documentation or unresolved inputs requiring a source-specific decision. |
| `derived_output_not_raw_input` | 56 | Inspection, QC, review or cleaned outputs that must not be mistaken for independent raw sources. Some, such as the final reviewed ENA lane, are explicitly designated authoritative inputs to the next stage while retaining their derived provenance. |
| `not_relevant_to_protein_aptamer_corpus` | 15 | Operating-system files, fixtures or sources outside the protein RNA aptamer objective. |
| `superseded` | 1 | Older empty ENA selected-output file replaced by the `review_v2` result. |
| **Total** | **203** | Files distributed across 21 top-level source directories. |

This inventory is intended to prevent three common errors: treating a derived cleaning output as an independent source, silently using an obsolete or backup file, and losing the exact raw bytes needed to reproduce later curation decisions. The read-only inventory script passed 11 unit tests, and pre/post SHA-256 fingerprints matched for all 203 files. Before version control, trackable inventory artefacts are sanitised so that they contain schemas, counts, paths and hashes but no aptamer sequence values; sequence-level overlap samples are written only beneath ignored `data/`. Hashes will be checked again at S0, and all generated outputs will be written outside `data/raw/`.

### Curation questions resolved during inventory refresh

| Question | Resolution carried into the curation specification |
|---|---|
| Q1 — ENA input and grouping fields | Use `data/raw/ENA/review_v2/ena_selected_after_manual_review.csv` (679 rows). It retains `experiment_group_id` and `near_duplicate_family_id`; materialise deterministic singleton family IDs at S1 and reconcile the three-row difference from the 676-row processed export at CHECKPOINT-1. |
| Q2 — corrected RiboAptamer input | Use `data/raw/riboaptamer/all_sequences_509_rows.csv` (509 rows). Treat `Category` as a prior only; resolve target name and type per record and surface disagreements at CHECKPOINT-2. |
| Q3 — AptaDB aptamer-to-protein join | Read `interaction.csv` as the interaction-grain spine, join `Apta_index` to `aptamer.csv`, and join protein `TargetID` to `protein.csv` UniProt IDs. |
| Q4 — `li_et_al` | Excluded because the workbook's provenance could not be established; do not reconstruct or reintroduce it without a documented DOI/supplement identity. |
| Q5 — Precision-SELEX layout | Parse 20 even-row records beginning at row 4; use column B as the N40 core and column D as the construct. Keep the incomplete column-I heading documented rather than inferred in code. |
| Q6 — selektion D9 molecule type | Treat D902, D907, D909, D913, D914, D918 and D920 as RNA aptamers selected by RNA SELEX but reported in DNA alphabet; retain the reported string and record computational T-to-U transcription. |

### Harmonised record contract for per-source outputs

The full curation specification defines a fixed 47-column schema used by cleaned per-source files, parked files and the master corpus. The summary below records the main field groups; implementation must use the complete schema rather than treating this table as sufficient:

| Field group | Required information |
|---|---|
| Sequence | Original sequence string, cleaned canonical RNA sequence, molecule type, sequence length and normalisation actions. |
| Target | Original target text, normalised protein name, protein family where available, target region/domain and target-type decision. |
| Evidence | Selection method/round or final-candidate status, binding evidence/affinity where reported, evidence scope and any control status. |
| Provenance | Source database, source file, source record/accession, publication/patent identifier and exact source location where available. |
| Grouping | Source experiment/publication group, exact-duplicate group and near-duplicate/family identifier. |
| Eligibility | Primary-corpus inclusion decision, exclusion/separate-lane reason and unresolved-review flag. |
| Reuse | Data-use or redistribution restriction where applicable. |

### Planned curation workflow

1. **S0 — registry and leakage exclusion:** author `data/interim/registry/source_registry.csv`, verify every registered file hash and row count, warn on inventory divergence, and build `leakage_exclusion_set.csv`. The registry is authoritative; `recommended_S0_status` is a starting classification rather than an automatically inferred input list.
2. **S1 — extraction:** use one source adapter per registered source and preserve every input row. Extraction performs column mapping and format parsing only.
3. **S2 — normalisation and constant-region trimming:** apply one shared sequence normaliser, preserve `sequence_raw`, build `sequence_full` and `sequence_core`, record transcription provenance, and detect known or group-consensus constant regions without dropping records.
4. **S3 — per-source filtering and CHECKPOINT-1:** apply the closed-vocabulary rejection rules, route ssDNA/non-protein/E5 records to parked lanes, emit source review files, reconcile ENA 679 versus 676, and stop for manual review.
5. **S4 — target normalisation and CHECKPOINT-2:** construct and review the raw-target-to-canonical-target dictionary, seeded from AptaDB protein/UniProt metadata; then apply leakage and the evidence threshold.
6. **S5 — exact deduplication and 90% sequence clustering:** deduplicate `(sequence_core, target_name)` pairs while merging provenance, cluster by sequence, validate against ENA near-duplicate families, and report cross-source overlap.
7. **S6 — profile report and CHECKPOINT-3:** produce the supervisor-facing pre-balancing corpus profile and obtain decisions on the target cap and any relaxation of the E4/protein-only rules.
8. **S7 — balance, partition and finalise:** apply the target cap at cluster level, assign cluster-level `FT`/`REF`/`EVAL` partitions, and write the final, parked, evaluation, rejection, report and manifest outputs.

Every stage reads only the previous stage's outputs, writes a QC report, appends a project-log entry, and leaves `data/raw/` unchanged.

### Key findings and decisions

- No public target-specific RNA HT-SELEX or activity-screening corpus at fine-tuning scale was found for NDM-1/KPC-2/OXA-48. Seven NDM-1 RNA aptamers were identified as evaluation references, not training-scale data.
- The useful public data landscape consists mainly of several moderate curated databases, small paper-derived collections and archive records requiring substantial interpretation.
- Dataset construction is therefore a substantive methodological component of the project rather than a simple download step.
- A smaller, carefully curated and diverse RNA protein-aptamer corpus is more aligned with the model objective than a much larger single-target late-round pool.
- DNA aptamers remain scientifically useful for target-specific evaluation and discussion but will not be used to define the primary RNA training or AptaRank reference distribution merely by replacing `T` with `U`.
- Cross-source duplication is expected to be substantial because the major databases draw from overlapping literature. Raw row counts are not estimates of unique sequences.
- The final corpus must be balanced by target and near-duplicate family, not only deduplicated exactly.
- Sequence-similarity, experiment-family and source grouping must be established before train/validation/test splitting.
- AptaRank calibration must use only the independent `REF` partition, while held-out real aptamers remain in `EVAL`; the fine-tuning data remain in `FT`.
- Apta-Index licensing/data-use terms must be carried forward and may limit publication or redistribution of the combined sequence-level corpus.

### Outputs

- Rough search and decision record: `docs/dataset_search_log.xlsx`
- Raw-tree inventory and S0 recommendations: `docs/data_curation/raw_data_inventory.csv`
- Sanitised aggregate inventory summary: `docs/data_curation/raw_data_inventory_summary.json`
- Raw-state assessment: `docs/data_curation/raw_data_state_assessment.md`
- Q1–Q6 resolutions: `docs/data_curation/raw_data_curation_questions.csv`
- Curation implementation specification: `docs/data_curation/rna_aptamer_corpus_curation_plan.md`
- Read-only inventory implementation: `scripts/data_preparation/inventory_raw_data.py`
- Inventory tests: `tests/data_preparation/test_inventory_raw_data.py`
- Existing source documentation and QC reports under each `data/raw/<source>/` directory
- Final reviewed ENA input lane: `data/raw/ENA/review_v2/ena_selected_after_manual_review.csv`
- ENA selected-record provenance: `data/raw/ENA/review_v2/ena_selected_sequence_provenance.csv`

### Status and next step

The search for major raw sources is sufficiently complete to proceed to the checkpointed curation pipeline. Before this documentation milestone, the inventory artefacts were sanitised to remove sequence-level examples. The inventory, assessment, Q1–Q6 resolutions, curation specification and this log entry are now ready to be committed together. The first curation task is S0 registry and leakage-exclusion construction; the first source adapter will be selected with Laura immediately before S1 implementation. The master corpus, cross-source duplicate resolution, target/family balancing and cluster-level `FT`/`REF`/`EVAL` partitions remain to be created.

## 2026-08-04 — S0a registry framework and AptaBase registration

### Stage

S0a — source-registry framework and first-source registration. Full S0 remains incomplete until the leakage-exclusion set is built. S1 must not begin.

### What was done

A deterministic S0a registry builder was added. It reads a tracked specification (`config/source_registry.csv`), validates each registered input against on-disk SHA-256 and CSV data-row counts (UTF-8-SIG, quoted embedded newlines handled), compares paths with `docs/data_curation/raw_data_inventory.csv`, and writes an operational copy to `data/interim/registry/source_registry.csv`. AptaBase is the first and currently only registered source. The cleaned scrape validated successfully (hash and 610 rows). Inventory divergence was emitted as warnings rather than failures. A pre/post hash of all 203 inventory-listed raw files confirmed the raw tree was unchanged. Unit tests cover success, mismatch, forbidden-path and inventory-warning cases; existing offline AptaBase tests were re-run for regression.

### Decisions made

- `data/raw/aptabase/aptabase_cleaned.csv` is the binding Tier 1 registered input (`source_dataset=aptabase_cleaned_scrape_2026-07-20`).
- `aptabase_raw.csv`, cached HTML under `html/`, fixtures, and duplicate search-page HTML files are forbidden pipeline inputs (retained as scrape provenance only).
- Later S1 must map from `sequence_raw` only; prior derived fields such as `sequence_clean` / inferred molecule type remain noncanonical diagnostics.
- The user-supplied note that AptaBase is referenced by Maptamer is stored as database-level source confidence only and must not raise any record’s experimental evidence level.
- `redistribution_status` remains `unknown` pending explicit reuse terms.
- Cross-source and intra-corpus deduplication remains deferred until S5.
- Inventory `recommended_S0_status` for the cleaned file (`derived_output_not_raw_input`) is intentionally overridden by the curation plan; the inventory’s preference for `aptabase_raw.csv` does not make that companion eligible for ingest.

### Inputs used

- Tracked registry specification: `config/source_registry.csv`
- AptaBase cleaned CSV: `data/raw/aptabase/aptabase_cleaned.csv` (SHA-256 `649ca9c2db37743917fc611eb2154ebaf7a3aa1a8a729f05c0f9c61fc376430e`)
- Tracked inventory: `docs/data_curation/raw_data_inventory.csv`
- AptaBase local documentation: `data/raw/aptabase/README_aptabase_curation.txt`, `aptabase_qc_report.md`
- Corpus curation specification: `docs/data_curation/rna_aptamer_corpus_curation_plan.md`

### Outputs produced

- `config/source_registry.csv` — tracked, reviewable registry specification (no sequence values)
- `scripts/data_preparation/s0_build_registry.py` — S0a validator/writer
- `tests/data_preparation/test_s0_build_registry.py` — synthetic non-biological fixtures
- `data/interim/registry/source_registry.csv` — operational registry; ignored by Git via `/data/`; contains the same registry metadata as the tracked specification and no sequence values

### Numbers

- Registered sources: 1 (`aptabase`)
- AptaBase expected rows: 610; actual rows: 610
- AptaBase SHA-256 (actual = registry): `649ca9c2db37743917fc611eb2154ebaf7a3aa1a8a729f05c0f9c61fc376430e`
- Inventory warnings on the real run: 2 (cleaned derived-output override; raw companion recommended-but-forbidden)
- Tests: `test_inventory_raw_data.py` + `test_s0_build_registry.py` → 34 passed; offline AptaBase cleaning/parser tests → 25 passed
- Raw-tree immutability: 203/203 inventory-listed raw-file hashes unchanged after S0a

### Open questions carried forward

- S0 leakage-exclusion set still required before S0 is complete
- Shared sequence normalisation and constant-region detection still required (S2)
- DNA-like AptaBase records remain unclassified pending molecule-type policy
- Redistribution terms for AptaBase remain unknown
- No AptaBase S1 adapter has been written; S1 must not start until S0 is finished

## 2026-08-05 — S0b evaluation-reference and leakage-exclusion build

### Stage

S0b — carbapenemase evaluation-reference manifest, target-exclusion aliases, and sequence leakage-exclusion set. S0a registry validation was re-run against the expanded specification. Shared general sequence normalisation, AptaBase S1 adapters, source filtering, target normalisation, corpus merging and partitioning were not started.

### What was done

Intentional evaluation-reference raw additions under `data/raw/evaluation_references/` were audited (README, additions-and-overrides CSV, supporting PDFs, and `source_documents/` supplements). The read-only inventory was reconciled against the committed 203-row baseline with an explicit transient-file exclusion rule (``.DS_Store``, ``.Rhistory``, Excel ``~$`` locks, ``Thumbs.db``, ``desktop.ini``). Tier `eval` registry rows were added for every machine-readable file parsed by S0b. `config/leakage_target_aliases.csv` was created for target-level exclusion. Leakage-specific comparison helpers were added in `scripts/data_preparation/common/leakage_matching.py`. The S0b builder reconciles D9, Precision-SELEX, Chen, Shi (with authoritative override), Sabrowski additions/controls, both patent sequences, and the PRJNA830749 dataset-level record into ignored interim outputs. A tracked resolution note records the final zero-pending status without sequences.

### Decisions made

- Sequence comparison uses global Levenshtein identity `1 - edit_distance / max(len_a, len_b)` with threshold 0.90 for later merge matching (T/U-aware comparison representation).
- Comparison representation collapses U→T so DNA/RNA T↔U equivalents have identity 1.0; empty strings are never compared; no local substring matching; no automatic promoter/primer trimming.
- D9 clones are experimental RNA printed with DNA alphabet (`alphabet_as_reported=DNA_T`); RNA form is derived computationally (`t_to_u_applied=true`). Genuine ssDNA retains T (`t_to_u_applied=false`).
- Full and core forms are both retained where documented (Precision column D full / column B core; D9 full equals core; patents may flag `core_unresolved`).
- Positive binders, pool non-binders, HIS-tag controls and masking probes from the selected evaluation pool all enter the leakage set; evaluation labels remain distinct.
- XK10 is one sequence family with merged Yu/Precision, Chen, and Shi provenance (application/replication, not independent corroborating selection).
- APNV carries combined NDM-1|VIM-2 target provenance. H14-01 is a HIS-tag control; H14-01-FR is a masking control.
- PRJNA830749 is dataset-level only and never expands to per-SRA-run sequence rows.
- Supporting Table S1 / Supplementary Table S2 resolve Shi XK10 and Sabrowski H14.2_43; pending sequence extractions = 0.
- Generic `albumin` alone is not an exclusion alias; HSA uses explicit human-serum-albumin forms only.
- Transient filesystem artefacts are excluded from the authoritative inventory and substantive hash-comparison denominator; they are reported separately and never deleted or modified.

### Inputs used

- D9 Table 6 CSV; Precision-SELEX `extracted_data.xlsx` (registry physical layout 43 rows; adapter asserts 20 logical XK records); Chen XK10 CSV; Shi CSV; `carbapenemase_reference_additions_and_overrides.csv`
- Supporting documentation PDFs under `data/raw/evaluation_references/` and `source_documents/` (not registered as sequence-table inputs)
- Tracked target aliases: `config/leakage_target_aliases.csv`

### Outputs produced

- Tracked: expanded `config/source_registry.csv`; `config/leakage_target_aliases.csv`; `scripts/data_preparation/common/leakage_matching.py`; `scripts/data_preparation/s0_build_leakage_exclusion.py`; registry XLSX validation and transient-aware inventory updates; tests; regenerated sanitised inventory artefacts; `docs/data_curation/carbapenemase_evaluation_reference_resolution.md`; this log entry
- Ignored under `/data/`: `data/interim/leakage_exclusion_set.csv`; `data/interim/evaluation/evaluation_reference_manifest.csv`; `data/interim/evaluation/reference_dataset_manifest.csv`; `data/interim/evaluation/pending_reference_extractions.csv`; `data/interim/evaluation/leakage_build_report.md`; operational registry refresh

### Numbers

- All 193 previously inventoried substantive raw-source files remained byte-identical. Changes involving `.DS_Store` files and the disappearance of an Excel lock file were classified as transient filesystem activity and excluded from the authoritative source-integrity denominator (11 transient paths ignored on disk; 10 transient paths present in the prior inventory).
- New substantive raw files: 10
- Modified previous substantive source files: 0
- Removed previous substantive source files: 0
- Registered sources after S0a refresh: 6 (AptaBase + 5 eval inputs); all validated by hash and row count
- Inventory warnings on registry rebuild: 2 (unchanged AptaBase overrides); no new registry warnings
- S0b aggregates: sources validated 5; records read 36; resolved evaluation records 35; unique sequence exclusions 32; distinct full/core forms 20; DNA 25; RNA 7; positive-class labels 26; negative/control labels 6; merged duplicate-provenance groups 3; dataset-level references 1; pending sequence extractions 0
- Target-alias rows: 29
- No contiguous nucleotide strings of length ≥20 in tracked S0b artefacts
- Nothing under `data/` is tracked; leakage outputs remain gitignored

### Status and next step

S0 is complete: the source registry and carbapenemase leakage-exclusion controls are operational and all required evaluation-reference sequences have been resolved. S1 must still not begin until the first source adapter is selected with Laura. Shared S2 normalisation, corpus merge (≥90% identity using the shared leakage matcher), target balancing and FT/REF/EVAL partitioning remain ahead.

## 2026-08-05 — Shared sequence-normalisation and constant-region foundation

### Stage

Implementation infrastructure for S2. This milestone does not constitute execution of S1, S2 or S3 on any source. No source adapter was written.

### What was done

- Shared display cleaning (whitespace, 5′/3′ labels, separators, case)
- Conservative alphabet and molecule handling with explicit QC flags
- Explicit T→U provenance (`t_to_u_applied`) only for independently established RNA
- Full/core sequence preservation (`sequence_raw` immutable; `sequence_full` retained after trim)
- Approved trim application with exact prefix/suffix match and hard failure on mismatch
- Known motif detection (including minimal T7) without automatic trimming
- Group-level constant-region proposal logic (proposal only; application requires approval)
- Deterministic unit tests using synthetic non-biological fixtures only

### Decisions

- Source adapters preserve `sequence_raw`; shared normalisation is authoritative from S2 onward
- Genuine DNA is never relabelled RNA; T-only values remain ambiguous without experimental molecule evidence
- Motif detection does not automatically authorise trimming
- Inferred constants require explicit approval before application; non-matching records stay untrimmed and flagged
- Training core length policy is 20–100 nt (evaluated after core determination; no silent truncation)
- Invalid or ambiguous records are flagged rather than silently repaired
- Constant-region inference is a technical aid, not biological proof of nonfunctionality

### Inputs

Only the tracked configuration file and synthetic test fixtures were used. No raw source table was processed.

### Outputs

```text
config/sequence_normalisation_rules.json
docs/data_curation/sequence_normalisation_contract.md
scripts/data_preparation/common/sequence_normalisation.py
scripts/data_preparation/common/constant_region_inference.py
tests/data_preparation/test_sequence_normalisation.py
tests/data_preparation/test_constant_region_inference.py
```

### Results

- New + leakage suite: 63 passed (`test_sequence_normalisation.py` 38; `test_constant_region_inference.py` 18; `test_leakage_matching.py` 7)
- Full curation foundation suite: 121 passed (inventory, S0 registry, leakage matching, S0b leakage exclusion, sequence normalisation, constant-region inference)
- Offline AptaBase regression: 25 passed (`test_aptabase_cleaning.py`, `test_aptabase_parser.py`)
- Tracked-file sequence safety scan: no contiguous A/C/G/T/U strings of length ≥20 in the new artefacts or this log section

### Open work

- AptaBase S1 adapter not yet implemented
- No real records have passed through S2
- Source-specific constant-region evidence remains to be supplied by adapters
- CHECKPOINT-1 has not been reached

## 2026-08-05 — AptaBase S1 verbatim extraction

### Stage

AptaBase has passed through S1 extraction only. No S2 normalisation, trimming, filtering, parking, deduplication, molecule inference, T→U conversion, affinity interpretation, or CHECKPOINT-1 artefact was produced.

### What was done

- Generic S1 runner (`scripts/data_preparation/s1_extract.py`) resolving inputs from the tracked source registry
- Central 47-column canonical corpus schema (`scripts/data_preparation/common/corpus_schema.py`)
- AptaBase source adapter (`scripts/data_preparation/adapters/aptabase.py`) with exact 33-column input validation
- Registry-gated SHA-256 and row-count validation before adapter execution (reusing S0 helpers; no duplicated hash/row-count logic)
- Canonical output plus a complete source-metadata sidecar under ignored `data/interim/extracted/`
- Atomic, deterministic CSV/Markdown writes with aggregate-only reporting

### Decisions

- All 610 AptaBase records are retained at S1
- `sequence_raw` is copied verbatim (no whitespace strip, case change, label removal, T→U, or use of `sequence_clean`)
- `sequence_clean` and previous molecule inference remain diagnostic source metadata only
- `target_specific` is preferred for `target_name_raw`, with `target_general` used only as a fallback when specific is empty or a textual null
- No target type or protein classification is performed
- No affinity or evidence interpretation is performed
- Source-specific fields are preserved exactly in an ignored sidecar
- No deduplication occurs before S5

### Inputs

- `config/source_registry.csv` (`source_key=aptabase`)
- `data/raw/aptabase/aptabase_cleaned.csv`
- Registered dataset: `aptabase_cleaned_scrape_2026-07-20`
- Registered SHA-256: `649ca9c2db37743917fc611eb2154ebaf7a3aa1a8a729f05c0f9c61fc376430e`

### Outputs

Ignored under `/data/`:

- `data/interim/extracted/aptabase_extracted.csv`
- `data/interim/extracted/aptabase_source_metadata.csv`
- `data/interim/extracted/aptabase_s1_report.md`

Tracked scripts and tests:

- `scripts/data_preparation/common/corpus_schema.py`
- `scripts/data_preparation/adapters/__init__.py`
- `scripts/data_preparation/adapters/aptabase.py`
- `scripts/data_preparation/s1_extract.py`
- `tests/data_preparation/test_corpus_schema.py`
- `tests/data_preparation/test_s1_extract.py`
- `tests/data_preparation/test_adapter_aptabase.py`
- this log entry

No shared registry-module refactor was required: S1 reuses `validate_registered_file`, `load_registry_spec`, `sha256_file`, and related helpers from `s0_build_registry.py`.

### Numbers

- Input rows: 610
- Canonical output rows: 610
- Sidecar rows: 610
- Nonempty `sequence_raw`: 556
- Missing `sequence_raw`: 54
- Target mapping: specific 576; general fallback 11; no usable raw target 23
- Publication fields: nonempty publication 598; DOI 60; PMID 1
- Source diagnostics (sidecar only): parse-warning rows 304; duplicate-group annotations 4
- Exact-copy `sequence_raw` validation: pass
- Source-input pre/post hash: pass (unchanged binding hash)
- Deterministic rerun: all three output files byte-identical across two runs
- New S1 tests: 58 passed
- Complete curation foundation suite: 179 passed
- Legacy AptaBase regression: 25 passed (`test_aptabase_cleaning.py` + `test_aptabase_parser.py`) after installing undocumented `ftfy` into the active environment (`ftfy==6.3.1`; no tracked dependency manifest changed)
- S0 registry validation: 6 registered, 6 validated, 2 AptaBase inventory-override warnings, no new warnings
- Raw-file integrity: all 203 previously inventoried substantive raw files remained byte-identical; registered AptaBase CSV retained binding hash; nothing under `data/` is tracked; S1 outputs are gitignored

### Open work

- No real AptaBase record has yet passed through S2
- Molecule types remain unresolved
- No T→U conversion has occurred
- No sequence has been trimmed
- No record has been filtered or parked
- No CHECKPOINT-1 artefact exists yet

## 2026-08-05 — AptaBase S2 sequence normalisation and QC

### Stage

All 610 AptaBase records passed through S2 normalisation only. No S3 inclusion, parking or rejection rules were applied. CHECKPOINT-1 was not created.

### What was done

- Shared sequence normaliser applied to S1 `sequence_raw` (never to legacy `sequence_clean`)
- AptaBase-specific preprocessing for corrupted terminal 5′/3′ display labels (`U+FFFD` / `?`) before shared display cleaning
- Source-specific conservative molecule-evidence policy (aptamer name → reference → alphabet)
- Display-only cleaning with auditable transformations
- Full/core preservation without approved trimming (`full_equals_core_untrimmed`)
- T→U conversion only for independently classified RNA
- Reported-length and GC diagnostics in an ignored QC sidecar
- Semantic comparison against legacy molecule labels (diagnostics only; literal vocabulary differences are not disagreements)
- Row-level review-candidate generation from operational QC flags
- Constant-region inference boundary demonstrated: no pooling under missing `experiment_group_id`

### Decisions

- Target fields are not evidence of aptamer molecule type
- Prior AptaBase molecule inference and `sequence_clean` are diagnostic only
- T-only sequences without explicit RNA/DNA text evidence remain `unknown`
- No motif authorises automatic trimming
- No AptaBase records are grouped for constant-region inference
- No records are filtered at S2
- Compatible/unresolved legacy molecule comparisons are sidecar diagnostics only and are not alone sufficient for the review-candidate file
- Corrupted AptaBase terminal-label cleanup is source-specific and tightly anchored; chemical-modification notation is retained

### Reconciliation

An initial audit found that many surprising invalid/length tallies came from corrupted AptaBase terminal prime notation (`5`/`3` plus `U+FFFD` or `?`) being conservatively retained, and that `legacy_molecule_type_disagreement` compared incompatible label vocabularies literally. Bounded AptaBase-specific terminal-label cleanup was added before the shared normaliser; no generic biological characters are dropped. Legacy molecule comparisons now use semantic categories rather than literal label strings. Canonical molecule classifications remain conservative and independent of the legacy cleaner.

### Inputs

- `data/interim/extracted/aptabase_extracted.csv`
- `data/interim/extracted/aptabase_source_metadata.csv`
- `config/sequence_normalisation_rules.json`
- `config/source_normalisation/aptabase.json`

### Outputs

Ignored under `/data/`:

- `data/interim/normalised/aptabase_normalised.csv`
- `data/interim/normalised/aptabase_s2_qc.csv`
- `data/interim/normalised/aptabase_s2_review_candidates.csv`
- `data/interim/normalised/aptabase_constant_region_proposals.csv`
- `data/interim/normalised/aptabase_s2_report.md`
- `data/interim/normalised/audit/` (reconciliation artefacts)

Tracked code, tests and configuration:

- `config/source_normalisation/aptabase.json`
- `scripts/data_preparation/common/corpus_schema.py`
- `scripts/data_preparation/adapters/aptabase_s2.py`
- `scripts/data_preparation/s2_normalise.py`
- `tests/data_preparation/test_corpus_schema.py`
- `tests/data_preparation/test_adapter_aptabase_s2.py`
- `tests/data_preparation/test_s2_normalise.py`
- this log entry

### Numbers

- S1/S2 rows: 610 / 610 (unique `record_id` 610; order and provenance preserved)
- Missing / nonempty sequences: 54 / 556
- Display transformations: AptaBase corrupted 5p 64; AptaBase corrupted 3p 89; five-prime label 442; three-prime label 420; display separators 51; whitespace 15; uppercase 3; textual null 54; t_to_u 1
- Alphabet: DNA_T 283; RNA 200; invalid 68; missing 54; mixed_T_U 3; ambiguous 2
- Molecule type: unknown 364; RNA 201; ssDNA 45
- Molecule evidence: sequence_alphabet 404; none 112; reference 90; aptamer_name 4
- T→U conversions: 1
- Invalid / ambiguous / mixed T/U: 68 / 2 / 3
- Known motif detections (configured five_prime): 1
- Trim-review rows: 4
- Core below / above 20–100: 8 / 34
- Reported-length mismatch: 71; reported GC mismatch: 13; GC unparseable: 1
- Legacy sequence_clean disagreement: 12; length 11; alphabet 291; GC 11
- Legacy molecule comparison: literal vocabulary mismatch 610; semantic agreement 245; substantive disagreement 1; compatible difference 120; unresolved 244; unrecognised 0; empty legacy 0
- Review candidates: 408
- Constant-region proposals: 0 (`records_with_experiment_group_id=0`; reason `no_experiment_group_id`)
- Shared S2-related tests: 173 passed
- Full curation suite: 288 passed
- Legacy AptaBase regression: 25 passed
- Deterministic rerun: all five S2 outputs byte-identical across two runs
- Integrity: registered AptaBase raw hash unchanged (`649ca9c2…430e`); S1 canonical and sidecar hashes unchanged; nothing written under `data/raw/`; nothing under `data/` tracked

### Comparison with earlier preprocessing

- Missing-sequence count agrees (54)
- Invalid rows fell from 156 to 68 after bounded corrupted-terminal cleanup; residual invalids are dominated by chemical-modification and malformed letters, not terminal-label leftovers
- Alphabet DNA_T/RNA tallies moved toward the legacy DNA/RNA band without forcing letter-stripping
- Molecule-type distribution remains more unknown than legacy because T-only without explicit evidence stays unknown
- Promoter detections rose only to 1: most residual T7 hits still sit after non-label prefixes, so the shared five_prime position rule correctly withholds them
- Length mismatches fell (150 → 71); GC mismatches rose (5 → 13) because more rows become GC-eligible after cleanup
- Semantic molecule disagreements are 1 (legacy `mixed_or_uncertain` versus new RNA), not the defective literal 610

### Open work

- S3 inclusion/parking/rejection rules have not been applied
- Molecule-type unknowns require policy-based handling at S3
- Trim-review candidates remain untrimmed
- Target types and evidence remain unresolved
- CHECKPOINT-1 has not been created
- Unrelated unstaged S1 forbidden-companion case-insensitive edits remain outside this S2 milestone

## 2026-08-05 — AptaBase S3 eligibility classification and CHECKPOINT-1

### Stage

S3 provisional eligibility decisions have been generated for AptaBase. The pipeline has stopped at CHECKPOINT-1 pending manual review. No record is authorised to proceed to S4.

### What was done

- Added a generic eligibility and decision framework (`EligibilityDecision`, reason codes, review priorities, checkpoint status)
- Implemented sequence-level evaluation-leakage matching against the S0b exclusion set (U→T comparison form; identity ≥ 0.90)
- Implemented raw-target leakage matching against tracked aliases (exact, normalised, bounded family patterns)
- Implemented the AptaBase S3 decision policy with deterministic precedence
- Classified all 610 records into proposed accept / park / reject
- Emitted sequence-free CHECKPOINT-1 review artefacts and an aggregate summary
- Reconciliation audit validated all 610 proposed decisions and their precedence assignments; zero sequence leakage and zero target leakage remain valid; all 173 proposed accepts satisfy the technical S4-entry conditions
- Confirmed the S2/S3 short-core count difference is definitional rather than a bug (S3 `core_below_minimum` uses nonempty-sequence policy length; S2 QC flag tally is broader)
- Usability revision: mechanical missing-sequence rejects are excluded from the manual-review queue (`manual_review_required=false`, priority `none`) even when secondary reasons such as unresolved molecule type or missing target remain for provenance
- Added a deterministic ignored local-detail scientific review table that may contain source and canonical sequences and must never be staged or tracked

### Decisions encoded

- Technically valid RNA may be proposed for acceptance
- ssDNA and unknown molecule types are parked
- Invalid, ambiguous, mixed-T/U and unresolved trimming/construct cases are parked
- Missing sequences, explicit source-invalid records, cores below 20 nt and evaluation leakage matches are rejected
- Cores above 100 nt are parked rather than rejected (possible fixed regions / full constructs)
- Missing targets are parked for later source review during S4 preparation
- Missing-sequence rejects remain proposed_reject but are not queued for manual scientific review
- All decisions remain provisional until manual CHECKPOINT-1 approval

### Inputs

- `data/interim/normalised/aptabase_normalised.csv`
- `data/interim/normalised/aptabase_s2_qc.csv`
- `data/interim/extracted/aptabase_source_metadata.csv`
- `data/interim/leakage_exclusion_set.csv`
- `config/leakage_target_aliases.csv`
- `config/source_eligibility/aptabase.json`

### Outputs

Ignored under `/data/`:

- `data/interim/checkpoints/aptabase_cp1/aptabase_s3_canonical.csv`
- `data/interim/checkpoints/aptabase_cp1/aptabase_s3_decisions.csv`
- `data/interim/checkpoints/aptabase_cp1/aptabase_checkpoint1_review.csv`
- `data/interim/checkpoints/aptabase_cp1/aptabase_checkpoint1_local_detail.csv`
- `data/interim/checkpoints/aptabase_cp1/aptabase_checkpoint1_summary.md`
- `data/interim/checkpoints/aptabase_cp1/aptabase_checkpoint1_reason_counts.csv`
- `data/interim/checkpoints/aptabase_cp1/aptabase_leakage_matches.csv`

Tracked code, tests and configuration:

- `config/source_eligibility/aptabase.json`
- `scripts/data_preparation/common/corpus_schema.py` (`validate_s3_record`)
- `scripts/data_preparation/common/eligibility.py`
- `scripts/data_preparation/adapters/aptabase_s3.py`
- `scripts/data_preparation/s3_classify.py`
- `tests/data_preparation/test_corpus_schema.py`
- `tests/data_preparation/test_eligibility.py`
- `tests/data_preparation/test_adapter_aptabase_s3.py`
- `tests/data_preparation/test_s3_classify.py`
- this log entry

### Numbers

- S2/S3 rows: 610 / 610 (unique `record_id` 610; S2 order preserved; canonical byte-identical to S2)
- Proposed decisions: accept 173; park 343; reject 94 (unchanged by usability revision)
- Primary reasons: molecule_type_unresolved 227; technically_eligible_rna 173; missing_sequence 54; ssdna_not_eligible_for_rna_training 41; core_below_minimum 39; invalid_sequence_requires_review 36; core_above_maximum_requires_review 34; mixed_t_u_requires_review 3; trim_or_construct_requires_review 1; ambiguous_sequence_requires_review 1; source_record_invalid 1 (unchanged)
- Review priorities after usability revision: medium 315; none 179; high 73; low 43
- `manual_review_required`: true 431; false 179
- Mechanical missing-sequence rejects excluded from manual review: 54 (all priority `none`, `manual_review_required=false`)
- Sequence leakage / target leakage / both: 0 / 0 / 0
- Condition tallies (any reason): missing_sequence 54; source_invalid 1; core_below_minimum 40; invalid 68; ambiguous 2; mixed_T/U 3; trim/construct 4; core_above_maximum 37; ssDNA 45; unknown molecule 364; missing_target 23; technically_eligible_rna 173
- Records with multiple eligibility reasons: 156
- Accepted-record invariants: all RNA; no invalid/ambiguous/mixed/trim-review flags; all cores 20–100 nt; no leakage; no ssDNA/unknown
- Local-detail rows: 610 (same review ordering as sequence-free checkpoint review; sequence-bearing; ignored under `data/`)
- New S3-focused tests: 89 passed (`test_eligibility` + `test_adapter_aptabase_s3` + `test_s3_classify` + S3 validators in `test_corpus_schema`)
- Full curation suite: 376 passed
- Legacy AptaBase regression: 25 passed
- Deterministic rerun: all seven CHECKPOINT-1 outputs byte-identical across two runs (including local-detail)
- Integrity: registered AptaBase raw hash unchanged (`649ca9c2…430e`); S1 and S2 inputs unchanged during S3; S3 canonical hash equals S2 normalised hash; nothing written under `data/raw/`; nothing under `data/` tracked; checkpoint outputs gitignored; local-detail must never be tracked

### Pipeline stop

- CHECKPOINT-1 remains pending manual review and is unapproved
- No record has proceeded to S4
- No target normalisation, UniProt mapping, evidence scoring, affinity interpretation, deduplication, clustering, balancing or partitioning has occurred

## 2026-08-05 — AptaBase CHECKPOINT-1 manual-review package

### Stage

The AptaBase CHECKPOINT-1 manual-review package has been generated. Proposed decisions are unchanged. CHECKPOINT-1 remains unapproved. No S4 work has begun.

### What was done

- Added a tracked manual-review protocol describing permitted reviewer actions and completion rules
- Implemented a deterministic review-package generator that selects only `manual_review_required=true` rows
- Assigned exactly one review batch to each active row
- Emitted an ignored sequence-bearing working CSV, a sequence-free safe index, and an aggregate summary
- Left all `review_action`, `reviewer_note` and `reviewer_initials` fields empty

### Review queue

- Active review rows: 431
- No-review records: 179
- Batch counts: `01_reject_review` 40; `02_accept_with_diagnostics` 48; `03_park_unresolved_molecule` 227; `04_park_ssdna` 41; `05_park_invalid_sequence` 36; `06_park_overlength` 34; `07_park_mixed_t_u` 3; `08_park_trim_construct` 1; `09_park_ambiguous` 1
- Missing-sequence rejects remain outside the active queue
- Sequence-bearing working CSV remains ignored under `data/`
- Sequence-free index is available for safe summary and discussion
- No review action has been recorded

### Outputs

Ignored under `/data/`:

- `data/interim/checkpoints/aptabase_cp1/manual_review/aptabase_checkpoint1_manual_review.csv`
- `data/interim/checkpoints/aptabase_cp1/manual_review/aptabase_checkpoint1_manual_review_index.csv`
- `data/interim/checkpoints/aptabase_cp1/manual_review/aptabase_checkpoint1_manual_review_summary.md`

Tracked code, tests and documentation:

- `docs/data_curation/aptabase_checkpoint1_review_protocol.md`
- `scripts/data_preparation/checkpoint1_prepare_review.py`
- `tests/data_preparation/test_checkpoint1_prepare_review.py`
- this log entry

### Verification

- Review-package tests: 28 passed (suite); combined S3 + review prep: 97 passed
- Full curation suite: 404 passed
- Legacy AptaBase regression: 25 passed
- Deterministic rerun: all three manual-review outputs byte-identical across two runs
- Integrity: raw, S1, S2 and S3 checkpoint inputs unchanged; nothing under `data/` tracked

### Pipeline stop

- CHECKPOINT-1 remains unapproved and pending manual review
- No record has proceeded to S4

## 2026-08-12 — AptaBase CHECKPOINT-1 review applied and closed

### Stage

AptaBase CHECKPOINT-1 human review has been applied and closed. Only resolved
accepts are authorised for S4. S4 target normalisation has not been run.

### Review conventions

- Active rows reviewed: 431 (all with explicit valid `review_action`)
- No-review rows resolved automatically: 179
- Single-reviewer convention (`review_model=single_reviewer`)
- Reviewer initials optional and intentionally omitted on all 431 rows
- Reviewer notes optional (`reviewer_notes_required=false`); notes present 207;
  notes absent 224
- Human `review_action` is the authoritative judgement; blank notes do not
  invalidate overrides

### Validation

- Completed review compared to a pristine reconstructed baseline
- Only permitted review fields differed (plus spreadsheet-semantic boolean /
  numeric coercions)
- Sequences, proposed decisions, reasons, targets and review order unchanged
- Review-file SHA-256:
  `1591663fd525860a59df1110129b6998f9d70e5906d2e42c47278449e8cc84f4`
- Raw / S1 / S2 / S3 integrity: pass
- Deterministic rerun: pass

### Action distribution

- `confirm_current`: 122
- `override_to_accept`: 23
- `override_to_park`: 0
- `override_to_reject`: 286
- `needs_source_review`: 0
- `not_required`: 179

### Final resolutions

- Proposed: accept 173; park 343; reject 94
- Resolved: accept 162; park 68; reject 380
- `approved_for_s4` / S4-authorised: 162
- `parked_after_checkpoint1`: 68
- `rejected_after_checkpoint1`: 380
- `needs_source_review`: 0
- Override transitions: park → accept 23; park → reject 252; accept → reject 34

### Outputs

Tracked:

- `config/checkpoint_reviews/aptabase_checkpoint1_resolutions.csv`
- `config/checkpoint_reviews/aptabase_checkpoint1_metadata.json`

Ignored under `data/`:

- `data/interim/checkpoints/aptabase_cp1/resolved/aptabase_checkpoint1_resolution.csv`
- `data/interim/checkpoints/aptabase_cp1/resolved/aptabase_s4_authorised_ids.csv`
- `data/interim/checkpoints/aptabase_cp1/resolved/aptabase_checkpoint1_parked_ids.csv`
- `data/interim/checkpoints/aptabase_cp1/resolved/aptabase_checkpoint1_rejected_ids.csv`
- `data/interim/checkpoints/aptabase_cp1/resolved/aptabase_checkpoint1_resolution_summary.md`

### Pipeline stop

- CHECKPOINT-1 is closed
- Exactly the 162 resolved accepts are authorised for S4
- S4 target normalisation has not begun

## 2026-08-12 — AptaBase prepared for future global S4

### Stage

The curation-plan architecture was rechecked. Target normalisation is a
corpus-wide stage after per-source cleaning, not a definitive per-source S4.
CHECKPOINT-1 remains the authoritative AptaBase endpoint. Exactly 162 records
are authorised for future global S4. No final AptaBase S4, CHECKPOINT-2 or S5
work exists.

### Provisional S4 discarded

An exploratory AptaBase-only S4 implementation was useful for inspecting source
target-metadata fields, but its target decisions were not authoritative. The
uncommitted provisional implementation and any local experimental commits were
discarded before this handoff commit. No AptaBase CHECKPOINT-2 exists.

### Meaning of authorised_for_s4

For AptaBase, `authorised_for_s4=true` means technically eligible after
sequence/molecule CHECKPOINT-1 and eligible to enter future corpus-wide target
normalisation. It does not mean protein target confirmed, target canonicalised,
UniProt resolved, evidence threshold passed, leakage check passed globally, or
CHECKPOINT-2 approved.

### Source target-metadata observations retained

Among the 162 authorised records:

- `aptabase_target_specific` present: 162; missing: 0
- `aptabase_target_general` is categorical
- Observed categories: Protein 113; Small Organic 37; Peptide 6; Cells 5;
  Antibody 1
- No source UniProt / PDB / Pfam / family columns

These category counts are source observations only. They are not final target
type, eligibility, UniProt, family or CHECKPOINT-2 decisions.

### What was done

- Added `config/global_s4_sources/aptabase.json`
- Documented the handoff in `docs/data_curation/aptabase_global_s4_handoff.md`
- Added reusable `prepare_global_s4_source.py`
- Materialised the exact 162-record S3 subset for future global merge
- Ran focused and full curation tests; ran handoff twice for determinism

### Verification

- Focused handoff + CHECKPOINT-1 + S3 tests: 128 passed
- Full curation suite (excluding legacy cleaner/ENA import-order suite): 483
  passed
- Legacy AptaBase regression: 25 passed
- Deterministic handoff rerun: byte-identical
- Integrity: raw, S1, S2, S3 and CHECKPOINT-1 artefacts unchanged
- `git ls-files data` empty; handoff outputs ignored under `/data/`

### Outputs

Tracked:

- `config/global_s4_sources/aptabase.json`
- `docs/data_curation/aptabase_global_s4_handoff.md`
- `scripts/data_preparation/prepare_global_s4_source.py`
- `tests/data_preparation/test_prepare_global_s4_source.py`
- this log entry

Ignored under `data/`:

- `data/interim/global_s4_ready/aptabase_global_s4_input.csv`
- `data/interim/global_s4_ready/aptabase_global_s4_handoff_summary.md`

### Pipeline stop

- AptaBase S1/S2/S3 complete; CHECKPOINT-1 closed
- Global-S4 handoff ready: 162 records
- Final AptaBase S4 not run
- AptaBase CHECKPOINT-2 does not exist
- AptaBase S5 not run
- Future global S4 will merge AptaBase with other cleaned sources before
  canonical target resolution

## 2026-08-12 — UTexas registration and S1 verbatim extraction

### Stage

UTexas source registration (S0 registry update) and S1 extraction only. No S2
normalisation, molecule classification, target normalisation, evidence scoring,
filtering, parking, deduplication or CHECKPOINT-1 work was started for UTexas.

### Source

Authoritative workbook:

`data/raw/UTexas_aptamer_dataset/UTexas Aptamer Database dataset_Sept2023.xlsx`

- Sheet: `Dataset`
- Registered `source_key`: `utexas`
- Registered `source_dataset`: `utexas_sept2023_2026-08`
- Registered SHA-256:
  `b5a66beb58d30c5c3d2f36a29ea2cc3678e7d4a6b1bb1a97efc1e166a49fd15c`
- Registered / validated physical row count: **1894**
  (`sheetData` rows minus header; project physical-workbook-row convention)
- Of those 1,894 physical source records: **1,495** nonempty and **399** blank
  trailing rows that are physically represented in the workbook XML
- `redistribution_status`: `unknown`
- Snapshot date in registry: `2026-08-04` (inventory-refresh campaign date)

The workbook was added to tracked `config/source_registry.csv` and the
operational registry was rebuilt with the existing S0a builder
(`scripts/data_preparation/s0_build_registry.py`). Validation result:
7 registered sources, 7 validated, unchanged AptaBase inventory-override
warnings only. Nothing under `data/raw/` was written.

### Identifier decision

UTexas `Serial Number` is unsuitable as the corpus `native_id`:

| Metric | Count |
|---|---|
| Populated Serial Number values | 1,495 |
| Unique Serial Number values | 1,444 |
| Duplicate Serial Number keys | 45 |
| Rows participating in duplicated keys | 96 |
| Physical source rows without a Serial Number | 399 |

Because every one of the 1,894 registered physical rows must retain an identity,
and because duplicate serials must not be collapsed, S1 adopts the **actual Excel
worksheet row number** from each `sheetData` row `@r` attribute:

- `native_id = row_{NNNN}` (4-digit zero padding)
- `record_id = utexas:row_{NNNN}`

This identity is auditable against the SHA-pinned workbook snapshot. Completely
absent worksheet row numbers (the registered workbook skips rows 1497–1504 in
`sheetData`) are not fabricated. Original `Serial Number` values are preserved
verbatim in the source-metadata sidecar and are never used as the corpus key.
`{serial}:{occurrence}` was not used.

### Extraction methodology

Implemented under the existing S1 architecture:

- Adapter: `scripts/data_preparation/adapters/utexas.py`
- Runner dispatch: `scripts/data_preparation/s1_extract.py --source utexas`
- Reader: stdlib ZIP/OOXML (same physical-row philosophy as S0 XLSX counting),
  so trailing blank `sheetData` rows are retained rather than dropped by a
  dataframe reader

Canonical mapping at S1 (format/provenance only):

- `Aptamer Sequence` → `sequence_raw` (verbatim; no cleaning)
- `Target ` (source header includes the trailing space) → `target_name_raw`
  (verbatim)
- `Citation` → `publication`
- `Journal DOI` → `doi` (verbatim source string)
- `Link to PubMed Entry` → `pubmed_id` only when a numeric PMID can be extracted
  deterministically from the source string (PubMed URL or bare digits);
  otherwise left empty, with the raw link retained in the sidecar
- `Name of Aptamer` → optional JSON `notes` when nonempty
- Provenance fields: `source_db=utexas`, contributing sources/datasets,
  `corroboration_count=1`, `independently_attested_by_permissive_source=false`,
  registry `redistribution_status`

All 28 original UTexas columns plus the worksheet row number are written to the
source-metadata sidecar. No sequence normalisation, T→U conversion, molecule or
chemistry classification, length filtering, constant-region trimming, target
normalisation, affinity/evidence interpretation, DNA parking, missing-sequence
rejection, or Serial Number deduplication occurred. Later-stage canonical fields
remain empty.

Ignored outputs:

- `data/interim/extracted/utexas_extracted.csv` (47-column canonical schema;
  1,894 rows)
- `data/interim/extracted/utexas_source_metadata.csv` (1,894 rows)
- `data/interim/extracted/utexas_s1_report.md`

### Verification

- Targeted UTexas S1 tests (`test_adapter_utexas.py`): **14 passed**
  (synthetic fixtures only; no real aptamer sequences committed)
- Core S0/S1 regression files (UTexas + AptaBase S1 + registry + corpus schema):
  **125 passed**
- Broader data-preparation suite excluding known hang-prone legacy AptaBase
  cleaner/parser and ENA legacy tests: **497 passed**
- Real extraction counts:

  | Check | Value |
  |---|---|
  | Registered SHA = actual SHA | pass |
  | Expected / extracted / sidecar rows | 1894 / 1894 / 1894 |
  | Unique `record_id` / `native_id` | 1894 / 1894 |
  | Nonempty / empty `sequence_raw` | 1495 / 399 |
  | Nonempty / empty `target_name_raw` | 1495 / 399 |
  | Populated / unique / duplicate-key / blank Serial Number | 1495 / 1444 / 45 keys (96 rows) / 399 |
  | S2/S3 scientific fields populated | 0 |

- Determinism: two runs with identical flags produced byte-identical
  `utexas_extracted.csv` and `utexas_source_metadata.csv`; the S1 report is also
  byte-identical when the deterministic-rerun flag state matches
- Raw-data immutability: workbook SHA-256 unchanged before and after
  (`b5a66beb…fd15c`); no files under `data/raw/UTexas_aptamer_dataset/` were
  written or modified

### Pipeline stop

```text
UTexas S1 complete.
UTexas S2 has not started.
No UTexas records are yet authorised for global S4.
```

Next step (separate planning milestone): UTexas S2 decisions, especially molecule /
chemistry mapping for FANA and unusual modified chemistries, and whether the
shared display cleaner should recognise `[3'T]` / `[5'T]` terminal notation.
Do not begin that work from this S1 milestone.

## 2026-08-12 — UTexas S2 sequence normalisation

### Stage

UTexas S2 sequence normalisation and constant-region detection/proposal only.
No S3 filtering, parking, rejection, target normalisation, affinity/evidence
scoring, or CHECKPOINT-1 work was started.

### Input

Registered UTexas S1 outputs:

- `data/interim/extracted/utexas_extracted.csv` (1,894 rows)
- `data/interim/extracted/utexas_source_metadata.csv` (1,894 rows)
- `source_key = utexas`
- `source_dataset = utexas_sept2023_2026-08`
- Raw workbook SHA-256 unchanged:
  `b5a66beb58d30c5c3d2f36a29ea2cc3678e7d4a6b1bb1a97efc1e166a49fd15c`

S1 reconciliation before S2: 1,894 rows; 1,894 unique `record_id` /
`native_id`; 1,495 nonempty / 399 empty `sequence_raw`.

### Shared normalisation

One shared normaliser
(`scripts/data_preparation/common/sequence_normalisation.py`) was used for all
display cleaning, alphabet classification, molecule-aware T→U, known-motif
detection, and length QC. UTexas-specific handling was limited to structured
source-metadata mapping in `config/source_normalisation/utexas.json` and the
thin adapter `scripts/data_preparation/adapters/utexas_s2.py`.

### Display-label improvement

Shared terminal-label handling was extended to cover bracketed UTexas notation
required by the curation plan (`[3'T]`, `[3′T]`, `[5'T]` and Unicode prime
variants), plus trailing phosphorylation display `p`. Stripping is end-anchored
only; internal bracketed text is retained and flagged. Focused shared unit
tests were added; AptaBase normalisation regressions still pass. AptaBase’s
source-specific corrupted `5?`/`3?` cleaner was not inherited by UTexas.

Real-data display transformations (aggregate):

| Transformation | Count |
|---|---|
| `remove_five_prime_label` | 1462 |
| `remove_three_prime_label` | 1447 |
| `remove_bracketed_three_prime_label` | 9 |
| `remove_bracketed_five_prime_label` | 0 |
| `uppercase` | 26 |
| `strip_whitespace` | 9 |
| `remove_whitespace` | 6 |
| `remove_display_separators` | 2 |
| `textual_null` | 399 |

### Molecule policy

Experimental `Type of Nucleic Acid` was primary evidence (config map, not
scattered conditionals):

- RNA forms (ssRNA and modified RNA classes) → `molecule_type = RNA`
- `ssDNA` → `ssDNA`; `dsDNA` / BNA-LNA-DNA / 5-uracil-modified-DNA → `DNA`
- `FANA XNA` and blank → `unknown` (not guessed from T/U alphabet)
- T-only alphabet never established molecule type

| molecule_type | Count |
|---|---|
| RNA | 583 |
| ssDNA | 896 |
| DNA | 13 |
| unknown | 402 |
| **total** | **1894** |

### Chemistry

Canonical `chemistry` was populated at S2 per the curation plan closed
vocabulary. This also corrected the prior AptaBase-era stage-guard divergence
in which `chemistry` was blocked until after S3 (`S2_FORBIDDEN_FIELDS` /
`S3_FORBIDDEN_FIELDS`). Historical AptaBase interim outputs were **not**
re-curated; AptaBase S2 still leaves `chemistry` empty because that source has
no chemistry map.

Unsupported specialised UTexas chemistries map to canonical `unknown` while
retaining the exact source value in `utexas_type_of_nucleic_acid`, with QC flag
`chemistry_not_in_canonical_vocab` (15 rows). `FANA XNA` additionally carries
`molecule_type_requires_review` (3 rows).

| chemistry | Count |
|---|---|
| RNA | 438 |
| DNA | 897 |
| 2F-RNA | 108 |
| 2NH2-RNA | 23 |
| 2OMe-RNA | 6 |
| mixed | 5 |
| unknown | 417 |
| **total** | **1894** |

### Alphabet / T→U

After display cleaning: DNA_T 878, RNA 552, invalid 57, ambiguous 8,
missing 399. T→U applied = **0** (no established-RNA record reported a pure
T alphabet after cleaning; RNA sources already used U). Mixed T/U unresolved
after cleaning = 0. Post-SELEX modification text was retained in the sidecar
only and did not alter `sequence_full` / `sequence_core`.

### Constant regions

UTexas `Pool Type` was parsed only with a deterministic single-`N##`
construct pattern for detection/proposal. Group consensus used pool-type hash
groups only (never empty `target_name`). Known motifs from the shared library
were flagged. **No newly inferred UTexas trim was applied**
(`apply_approved_trims = false`; no approved UTexas trim rules exist).

| Metric | Value |
|---|---|
| Constant-region proposals | 1653 |
| — pool_type | 816 |
| — group_consensus | 816 |
| — known_motif | 21 |
| Applied trims | 0 |
| `sequence_core != sequence_full` | 0 |
| `trim_status = constants_suspected_unresolved` | 1287 |
| `trim_status = no_constants_detected` | 208 |
| `trim_status = not_applicable` (missing) | 399 |

Proposals remain pending Laura review before any can be used as trims.

### Length / QC (diagnostic only; no S3 filtering)

| Core/full length bucket | Count |
|---|---|
| missing | 399 |
| <20 | 15 |
| 20–100 | 1287 |
| 101–200 | 191 |
| >200 | 2 |

Notable QC: missing_sequence 399; invalid_character 57; ambiguous_base 8;
molecule_type_unknown 402; chemistry_not_in_canonical_vocab 15;
core_below_min_length 13; core_above_max_length 178; review candidates 1730.

### Outputs (gitignored under `data/`)

- `data/interim/normalised/utexas_normalised.csv`
- `data/interim/normalised/utexas_s2_qc.csv`
- `data/interim/normalised/utexas_s2_review_candidates.csv`
- `data/interim/normalised/utexas_constant_region_proposals.csv`
- `data/interim/normalised/utexas_s2_report.md`

### Verification

- Targeted shared normaliser + UTexas S2 + AptaBase S2 + corpus schema +
  constant-region + S2 orchestration tests: **216 passed** (pre-real-data)
- Broader data-preparation suite excluding hang-prone legacy AptaBase
  cleaner/parser and ENA legacy tests: **537 passed**
- Exclusions (same class as S1 log): `test_aptabase_cleaning.py`,
  `test_aptabase_parser.py`, `test_process_ena_aptamer_candidates.py`,
  `test_inspect_ena_aptamer_records.py`, `test_refine_ena_manual_review.py`,
  `test_consolidate_ena_candidate_review.py`,
  `test_finalize_ena_aptamer_supplement.py`
- Determinism: `--check-deterministic-rerun` byte-identical for normalised,
  QC, review-candidate and proposal CSVs
- S1 provenance: `record_id`, `native_id`, `sequence_raw`, `target_name_raw`
  preserved for all 1,894 rows
- Raw workbook SHA unchanged before and after S2

### Pipeline stop

```text
UTexas S2 complete.
No records have been filtered, parked or rejected.
UTexas S3 and CHECKPOINT-1 have not started.
Any unresolved constant-region proposals remain pending review before they can be used as trims.
```

## 2026-08-13 — UTexas S2 constant-region inference refinement

### Stage

Corrective refinement of the UTexas S2 **constant-region proposal** layer only.
No sequence trims were approved or applied. S3 and CHECKPOINT-1 were not
started. Molecule-type / T→U logic was not reopened as a scientific question
(T→U = 0 remains valid).

### Problem

The initial UTexas S2 pass (commit `0c45d18`) correctly normalised sequences
with `applied trims = 0` and `sequence_core == sequence_full` for all 1,894
rows. Review of the proposal artefact found that Tier-2 group consensus had
been configured with `group_inference_by_pool_type = true`, so consensus was
grouped by Pool Type rather than the curation plan’s fallback
`(source_db, target_name, publication)`.

That made `pool_type` and `group_consensus` proposal counts artificially equal
(816 / 816) and admitted 717 zero-length diagnostic rows
(`insufficient_group_size` / `insufficient_support`) into the scientific
proposal table. No sequence damage occurred because no trim was applied.

### Corrections

1. **Tier-2 grouping** now uses configurable
   `group_inference_key = target_name_raw_plus_publication` (UTexas has no
   `experiment_group_id`; canonical `target_name` awaits global S4). Missing
   target/publication values are not pooled into a catch-all group.
2. **Pool Type** remains an independent source-documented evidence channel
   with empirical exact-match fractions against `sequence_full` ends;
   parse success is no longer reported as `support = 1.0`.
3. **Failed inference** is recorded only in aggregate diagnostics; the
   proposal CSV contains genuine motifs only (`motif_length > 0`).
4. Shared inference defaults aligned to the plan: `minimum_support = 0.8`,
   `minimum_region_length = 12`. Qualifying Tier-2 proposals use
   `confidence = medium` / `proposed_for_checkpoint1` (never “high” merely
   because support = 1.0).
5. A **rule-level review package** was produced for Laura/ChatGPT (candidate
   rules, membership sidecar, blank decision template, sequence-safe summary).

### Counts (old → corrected)

| Metric | Old (superseded) | Corrected |
|---|---|---|
| Proposal rows | 1653 | 927 genuine |
| pool_type | 816 | 816 |
| group_consensus | 816 (incl. failures) | 90 qualifying |
| known_motif | 21 | 21 |
| Zero-length pseudo-proposals | 717 | 0 |
| `(target_name_raw, publication)` groups | n/a (was Pool Type) | 591 |
| Groups ≥5 | n/a | 74 eligible (57 size 5–9; 15 size 10–24; 2 size 25–49) |
| Qualifying 5′ / 3′ consensus groups | n/a | 47 / 43 |
| Unique candidate trim rules | n/a | 569 |
| pool+consensus exact motif agreements | n/a | 47 |
| Conflicted rules | n/a | 57 |
| Applied trims | 0 | 0 |

Pool Type empirical exact-match bands: perfect 530; partial 98; poor/zero 188.

### Sequence invariants

```text
rows in = 1894
rows out = 1894
sequence_raw changed = no
sequence_full unchanged relative to prior S2 core construction
sequence_core == sequence_full for all rows
applied trims = 0
T→U = 0
molecule_type counts unchanged (RNA 583 / ssDNA 896 / DNA 13 / unknown 402)
raw workbook SHA unchanged =
b5a66beb58d30c5c3d2f36a29ea2cc3678e7d4a6b1bb1a97efc1e166a49fd15c
```

### Outputs (gitignored under `data/interim/normalised/`)

- `utexas_normalised.csv` / `utexas_s2_qc.csv` / `utexas_s2_review_candidates.csv`
- `utexas_constant_region_proposals.csv` (genuine proposals only)
- `utexas_constant_region_rule_candidates.csv`
- `utexas_constant_region_rule_membership.csv`
- `utexas_constant_region_review_decisions.csv` (blank decisions)
- `utexas_constant_region_review_summary.md`
- `utexas_s2_report.md`

### Verification

- Shared constant-region + UTexas S2 + sequence-normalisation + AptaBase S2
  + broader data-preparation suite (legacy hang-prone exclusions as before):
  **550 passed**
- Deterministic rerun: byte-identical for normalised, proposals, rule
  candidates, membership, decisions template and review summary
- AptaBase scientific interim outputs were not rewritten

### Pipeline stop

```text
UTexas S2 constant-region proposal semantics corrected.
No trim has been approved.
No trim has been applied.
sequence_core remains unchanged.
S3 has not started.
CHECKPOINT-1 has not started.
Laura/ChatGPT must review rule-level candidates before any UTexas trim approval.
```

## 2026-08-13 — UTexas S2 approved constant-region trimming

### Stage

Human-reviewed rule-level trim policy was recorded and applied. S3 and
record-level CHECKPOINT-1 were not started. Target normalisation, evidence
scoring, deduplication, clustering and global S4 were not performed.

### Review decisions

569 candidate constant-region rules were reviewed as a package:

| Decision | Count | Policy |
|---|---|---|
| `approve` | 47 | 46 `pool_type_plus_consensus_agree` (no conflict, support ≥0.80, motif ≥12, no rule-level guard-rail violation) plus 1 `consensus_only` rule (5 records, support 1.0, motif 22 nt) |
| `needs_source_review` | 522 | 464 `pool_type_only` + 56 `conflicting_evidence` + 1 `known_motif_only` + 1 otherwise-supported rule with a >40% hypothetical trim |
| `reject` | 0 | Unresolved rules are not scientifically disproven |

The conservative approval policy requires independent Pool Type documentation
and qualifying target+publication consensus (or, for the single consensus-only
rule, plan-threshold consensus with perfect exact match). Pool Type alone,
conflicts, known-motif-only detections, and the >40% rule remain for later
source/CHECKPOINT review.

Review model: `single_reviewer` (initials blank). Decision date: 2026-08-13.

### Application safeguards

- Exact terminal match only (T/U-collapsed comparison). No fuzzy matching.
- Same-side competing approved motifs: do not trim; flag for review.
- Combined per-record 5′+3′ simulation: if resulting core <20 nt or combined
  trim fraction >40%, apply neither side.
- Unresolved rules are never applied.
- `trim_confidence = medium` for all applied Tier-2 rules.

### Applied-trim results

```text
approved rules = 47 (all matched ≥1 record)
unresolved rules = 522
records safely trimmed = 299
5′ only = 199
3′ only = 92
both ends = 8
same-side ambiguities = 0
combined <20 prevented = 0
combined >40% prevented = 230
total bases removed = 5978
resolved_by_approved_trim = 27
still_trim_requires_review = 1278
```

Core-length buckets after trimming:

| Bucket | Full (unchanged) | Core after trim |
|---|---|---|
| missing | 399 | 399 |
| <20 | 15 | 15 |
| 20–100 | 1287 | 1318 |
| 101–200 | 191 | 160 |
| >200 | 2 | 2 |

31 records moved from `sequence_full` >100 into `sequence_core` 20–100.
No record that was 20–100 nt full became out of range after trimming.

### Invariants

```text
rows in/out = 1894
sequence_raw changed = no
sequence_full changed = no
molecule_type unchanged (RNA 583 / ssDNA 896 / DNA 13 / unknown 402)
T→U = 0
raw workbook SHA unchanged =
b5a66beb58d30c5c3d2f36a29ea2cc3678e7d4a6b1bb1a97efc1e166a49fd15c
AptaBase normalised SHA unchanged
```

### Tracked provenance

- `config/checkpoint_reviews/utexas_constant_region_review_metadata.json`
- `config/checkpoint_reviews/utexas_constant_region_resolutions.csv`
- `config/source_normalisation/utexas_approved_trim_rules.json` (47 source-scoped motifs)

### Verification

- Broader data-preparation suite (same legacy exclusions as before): **563 passed**
- Deterministic rerun: byte-identical for normalised, QC, review candidates,
  proposals, trim audit, ambiguity sidecar and S2 report

### Pipeline stop

```text
UTexas S2 sequence normalisation and approved constant-region trimming complete.
S3 has not started.
CHECKPOINT-1 record eligibility review has not started.
Unresolved constant/construct cases remain flagged for S3 CHECKPOINT-1.
```

## 2026-08-13 — UTexas S3 technical eligibility and CHECKPOINT-1 package

### Stage

UTexas **S3 technical sequence/molecule eligibility** and generation of the
record-level **CHECKPOINT-1** review package. Human review decisions were not
applied. CHECKPOINT-1 was not closed. Global S4 was not started. Target
normalisation, evidence scoring, leakage exclusion, deduplication, clustering,
balancing and partitioning were not performed.

### S3 policy

Tracked policy: `config/source_eligibility/utexas.json`. Shared seed
`42` is recorded in that policy and in `config/curation_config.yaml`.
AptaBase S3/CHECKPOINT-1 behaviour was not rewritten.

S3 assigns exactly one provisional primary state per record
(`proposed_accept` / `proposed_park` / `proposed_reject`) plus secondary
reason codes. No record disappears.

Deterministic precedence:

1. missing sequence
2. explicit non-RNA experimental molecule (`ssDNA` / `DNA`)
3. unresolved molecule type
4. mixed T/U, ambiguous bases, alignment gaps, invalid alphabet
5. `sequence_length_core` outside 20–100 nt
6. unresolved trim/construct
7. otherwise technically acceptable RNA

### Source-specific scientific rules

- Missing `sequence_core` (399 blank physical workbook rows) →
  `proposed_reject` / `missing_sequence`, excluded from the active review
  queue, retained in the rejection log.
- Explicit `ssDNA`/`DNA` → mechanical `proposed_park` /
  `non_rna_molecule` (`manual_review_required=false`). T is retained. No
  active ssDNA confirmation batch.
- Non-missing `molecule_type=unknown` (the three `FANA XNA` records) →
  `proposed_park` / `molecule_type_unresolved` with active review batch
  `03_park_unresolved_molecule`. FANA is not inferred as RNA or DNA from
  alphabet.
- Mixed T/U, IUPAC ambiguity and remaining invalid alphabet → reject
  (`mixed_T_and_U`, `ambiguous_bases`, `invalid_alphabet`). Alignment-gap
  invalidity would reject as `alignment_gaps` with repair-review batch
  `05_repair_alignment_gaps`; none were present.
- Length is evaluated on `sequence_length_core` only (20–100 nt). Out of
  range → `length_out_of_range`. If unresolved trim evidence remains, the
  provisional reject stays but enters `04_park_trim_construct` so
  CHECKPOINT-1 can override. Full-passed / core-failed cases would also
  require review; the S2 assertion of zero such cases remains true.
- Otherwise acceptable records at 20–25 nt or 90–100 nt stay
  `proposed_accept` but enter `02_accept_with_diagnostics`.
- All 299 medium-confidence applied trims keep their S2 trim. Otherwise
  acceptable medium-trim RNA records are `proposed_accept` with review
  reason `medium_confidence_trim`. If a stronger rule parks or rejects,
  the medium-trim diagnostic is retained as secondary.
- Unresolved trim/construct after alphabet/length checks →
  `proposed_park` / `trim_construct_unresolved` / batch
  `04_park_trim_construct`, including the 230 S2-blocked >40% combined
  trims. Unresolved full constructs are not sent to S4 merely because the
  current core is 20–100 nt.
- Modified RNA chemistries (`2F-RNA`, `2NH2-RNA`, `2OMe-RNA`, `mixed`,
  unknown specialised chemistry) are not rejected for chemistry alone.
- `construct_scope` is preserved from S2 (`full_construct` 8 /
  `partial_construct` 291 / `unknown` 1595).

### Target/evidence deferral

UTexas target type was not inferred in S3 because the source provides
free-text `target_name_raw` only. Target normalisation,
protein/non-protein classification, UniProt mapping, Kd/Affinity parsing,
evidence eligibility and leakage exclusion are deferred to global S4.
CHECKPOINT-1 authorisation, when it later happens, will mean only
technical eligibility to enter that future global stage.

### S3 reconciliation

```text
S3 input rows = 1894
proposed_accept = 109
proposed_park = 1264
proposed_reject = 521
1894 = 109 + 1264 + 521

manual_review_required = 468
mechanical/no-review = 1426
record_id unique = 1894
S2 canonical fields mutated = no
```

Proposed rejects by primary reason:

```text
missing_sequence = 399
ambiguous_bases = 8
invalid_alphabet = 23
alignment_gaps = 0
length_out_of_range = 91
mixed_T_and_U = 0
```

The 34 DNA/ssDNA rows with invalid characters are parked as
`non_rna_molecule` (invalid alphabet retained as a secondary diagnostic)
because explicit experimental molecule type outranks alphabet under the
UTexas precedence. Invalid-alphabet primary rejects are therefore the 23
RNA cases.

Proposed parks by primary reason:

```text
non_rna_molecule (DNA/ssDNA) = 909
molecule_type_unresolved = 3
trim_construct_unresolved = 352
```

Proposed accepts: `109` technically eligible RNA records.

### Review queue

```text
active review rows = 468
01_reject_review = 0
02_accept_with_diagnostics = 45
03_park_unresolved_molecule = 3
04_park_trim_construct = 420
05_repair_alignment_gaps = 0
```

`01_reject_review` is empty because judgement-dependent rejects in this
source are the 68 overlength records that still have unresolved trim
evidence; those were routed to `04_park_trim_construct` as specified.
Mechanical missing-sequence, invalid-alphabet, ambiguous-base and
plain length rejects stay out of the active queue.

Trim mapping after precedence:

```text
299 applied medium-confidence trims → 97 in the active queue
  (7 otherwise-acceptable RNA accepts in batch 02; 88 RNA trim/construct
  parks in batch 04; 2 RNA length-out-of-range rows in batch 04).
  The remaining 202 medium trims stay out of the active queue:
  198 mechanically parked ssDNA, 3 RNA ambiguous-base rejects, and
  1 mechanical RNA length reject. The medium-trim diagnostic is
  retained; they are not queued as ssDNA confirmations.
1278 still trim_requires_review before S3 → 352 primary trim/construct
  parks; 68 additional length-out-of-range rows keep that diagnostic and
  enter batch 04; DNA/ssDNA cases keep it as secondary only.
230 >40% blocked trims → 29 RNA rows in the active trim/construct queue;
  201 are mechanical ssDNA parks with the diagnostic retained.
```

Length/boundary/audit:

```text
full-passed / core-failed = 0
lower-boundary (20–25 nt) condition = 12
upper-boundary (90–100 nt) condition = 127
boundary-length rows in active review = 65
random clean-accept sample = 30 (pool 94, seed 42, shortfall 0)
```

Reviewer fields (`review_action`, `reviewer_note`, `reviewer_initials`)
are blank. Review model: `single_reviewer`; initials and notes are not
required.

### Verification

- Targeted UTexas S3 + CHECKPOINT-1 + AptaBase S3/CHECKPOINT-1 +
  eligibility tests: **127 passed**
- Broader data-preparation suite (same hang-prone legacy AptaBase
  cleaner/parser and ENA exclusions as before): **593 passed**
- Deterministic rerun: byte-identical S3 canonical, decisions, review,
  local-detail, reason counts, rejection log, park sidecar, and the
  CHECKPOINT-1 queue/index/summary
- S2 canonical SHA unchanged
  (`588498eaeeacb1f7d7349ef1f0f30ef46ba2e64d873416439ed62df614e50c7e`)
- Raw workbook SHA unchanged =
  `b5a66beb58d30c5c3d2f36a29ea2cc3678e7d4a6b1bb1a97efc1e166a49fd15c`
- AptaBase scientific interim outputs were not rewritten

### Outputs (gitignored under `data/interim/checkpoints/utexas_cp1/`)

- `utexas_s3_canonical.csv` / `utexas_s3_decisions.csv` /
  `utexas_s3_parks.csv`
- `rejected_utexas.csv` (sequence-bearing rejection log)
- `utexas_checkpoint1_review.csv` (sequence-free, all 1894 rows)
- `utexas_checkpoint1_local_detail.csv` (sequence-bearing, all rows)
- `utexas_checkpoint1_reason_counts.csv` /
  `utexas_checkpoint1_summary.md`
- `manual_review/utexas_checkpoint1_manual_review.csv` (active queue)
- `manual_review/utexas_checkpoint1_manual_review_index.csv`
- `manual_review/utexas_checkpoint1_manual_review_summary.md`

### Pipeline stop

```text
CHECKPOINT-1 package generated.
No human decisions applied.
No record authorised for S4 yet.
target type inferred = no
evidence scored = no
S4 started = no
records authorised_for_s4 = 0
```

Laura/ChatGPT should inspect the sequence-safe summary and index, then
decide how to review and close CHECKPOINT-1. Do not populate review
decisions in this milestone.

## 2026-08-13 — UTexas RNA alphabet exception review (CHECKPOINT-1)

### Stage

Human scientific exception review **preparation** for the 31
source-reported UTexas RNA records currently rejected at S3 for
`ambiguous_bases` or `invalid_alphabet`. CHECKPOINT-1 was not closed.
Human checkpoint decisions were not applied. Canonical S2/S3 sequences
were not edited. Global S4 was not started.

### Scientific context

Laura inspected the active CHECKPOINT-1 queue and judged UTexas a
high-confidence curated aptamer source whose source-reported RNA records
generally require minimal additional sequence adjudication. Unresolved
trim flags will not automatically exclude otherwise acceptable RNA
records. Target normalisation, protein filtering and balancing remain
deferred to global S4.

The remaining alphabet concern sat **outside** the 468-row active review
queue: 8 `ambiguous_bases` and 23 `invalid_alphabet` RNA rejects (31
total). Non-ACGU characters in this source can represent chemical
modifications or publication notation rather than degenerate libraries
or corruption. This package distinguishes those cases without changing
canonical cleaning behaviour.

### Cohort

```text
total exception rows = 31
ambiguous_bases = 8
invalid_alphabet = 23
molecule_type = RNA for every selected row
DNA / ssDNA / FANA / missing-sequence / ordinary length rejects excluded
```

### Proposed classifications (not applied)

```text
recoverable_modification_notation = 17
true_iupac_degenerate_sequence = 9
modified_rna_underlying_sequence_unresolved = 0
malformed_or_unrecoverable = 1
needs_manual_source_review = 4

high-confidence recoverable underlying RNA sequences = 17
proposed reject cases = 10
proposed park cases = 0
needs source-paper review = 4
```

Recoverable cases are leftover display labels the shared stripper did
not recognise (curly quotes, reversed `3'`), explicit 2′-fluoro /
2′-O-methyl tokens with a named underlying base, `Gcon` conserved-G
annotation, and an inverted terminal cap whose base is written in the
token. IUPAC/degenerate records were not converted to an arbitrary
base. Concatenated multi-construct fields were routed to source-paper
review. One mixed-script corrupted field is proposed malformed.

Ten of the 17 alphabet-recoverable strings remain outside 20–100 nt;
length policy is not decided by this exception review. Reviewer action
cells were left blank.

### Integrity

```text
canonical sequences changed = no
CHECKPOINT-1 actions applied = no
CHECKPOINT-1 closed = no
S4 started = no
records authorised_for_s4 = 0
raw workbook SHA unchanged =
b5a66beb58d30c5c3d2f36a29ea2cc3678e7d4a6b1bb1a97efc1e166a49fd15c
S2 canonical SHA unchanged =
588498eaeeacb1f7d7349ef1f0f30ef46ba2e64d873416439ed62df614e50c7e
S3 canonical SHA unchanged (byte-identical to S2 canonical)
```

### Verification

- New alphabet-exception tests: **17 passed** (synthetic notation only;
  no real UTexas sequences)
- UTexas S2 + S3 + CHECKPOINT-1 + shared sequence-normalisation +
  eligibility tests: **206 passed**
- Broader data-preparation suite (same hang-prone legacy AptaBase
  cleaner/parser and ENA exclusions as before): **610 passed**
- Deterministic rerun: byte-identical exception CSV and summary
- Shared normaliser was not modified

### Outputs (gitignored under `data/interim/checkpoints/utexas_cp1/exceptions/`)

- `utexas_alphabet_exception_review.csv` (sequence-bearing; 31 rows)
- `utexas_alphabet_exception_summary.md` (sequence-safe)

Tracked: diagnostic classifier, synthetic tests, this log entry.

### Pipeline stop

```text
Alphabet-exception review package generated.
No canonical sequence was changed.
No CHECKPOINT-1 decision was applied.
CHECKPOINT-1 remains open.
Global S4 has not started.
```

Laura/ChatGPT should review the 31-row exception file and then make the
final CHECKPOINT-1 closure decisions. Do not apply exception resolutions
in this milestone.

## 2026-08-13 — Close UTexas CHECKPOINT-1 and prepare global-S4 handoff

### Stage

Final per-source UTexas S1–S3 milestone. Human-reviewed alphabet-exception
decisions were recorded; 17 approved recoveries were applied through the
reproducible S2 pathway; S2/S3 were rerun; CHECKPOINT-1 was closed under
Laura's source-specific eligibility judgement; UTexas was prepared as one
input to future **global S4**. Global S4 itself was not executed.

### 1. Alphabet-exception review (31 RNA records)

Laura/ChatGPT reviewed the 31 source-reported RNA records previously
rejected for `ambiguous_bases` or `invalid_alphabet`. Package counts were
unchanged before decisions were recorded:

```text
exception rows = 31
recoverable_modification_notation = 17
true_iupac_degenerate_sequence = 9
malformed_or_unrecoverable = 1
needs_manual_source_review = 4
molecule_type = RNA for every selected row
```

All 17 proposed recoveries had `recovery_confidence = high` and a nonempty
underlying A/C/G/U string (7 recovered lengths in 20–100; 10 outside).

Recorded CHECKPOINT-1 judgements:

```text
accept_recovered_sequence = 17
confirm_reject = 10
override_to_park = 4
needs_source_review = 0
blank = 0
```

- 17 recoverable modification/display-notation records were approved at
  the alphabet-normalisation level only. They remained subject to approved
  constant-region processing, core length 20–100, and other S3 rules.
- 9 genuine IUPAC/degenerate sequences were confirmed reject. No arbitrary
  nucleotide substitution was applied.
- 1 malformed/corrupted sequence field was confirmed reject.
- 4 complex/concatenated constructs (hammerhead-ribozyme, aptamer dimers,
  aptamer/shRNA composites) were parked. No aptamer component was extracted.

Sequence-bearing decisions remain under ignored `data/`. Tracked
sequence-safe artefacts:

- `config/checkpoint_reviews/utexas_alphabet_exception_resolutions.csv`
- `config/checkpoint_reviews/utexas_alphabet_exception_metadata.json`

### 2. Reviewed sequence recoveries in S2

Only the 17 approved record IDs received deterministic recoveries via
`adapters/utexas_alphabet_exceptions.py`. `sequence_raw` was unchanged for
all 1,894 rows. Recovered A/C/G/U strings fed `sequence_full`, after which
the existing 47 approved constant-region rules were applied unchanged.

```text
rows in = 1894
rows out = 1894
reviewed alphabet recoveries applied = 17
sequence_raw / record_id / native_id / target_name_raw unchanged = 1894

recovered records with core length 20–100 = 7
recovered records with core length <20 = 2
recovered records with core length >100 = 8
recovered records with approved constant trim applied = 0
recovered records still trim_requires_review = 17
```

The 47 approved trim-rule IDs were loaded from the tracked constant-region
review and were not re-derived. Live diagnostic candidate-package agreement
tallies may differ after recovery; that does not reopen the 47-rule review.

### 3. S3 rerun and source-specific eligibility policy

UTexas S3 was regenerated from the updated S2 output. Unresolved trim is
not exclusionary for this source: source-reported RNA with a valid
nondegenerate alphabet and core length 20–100 is technically eligible even
when `trim_requires_review`, `constants_suspected_unresolved`, or
`trim_combined_exceeds_40pct` remain as QC/provenance. This is a
source-specific judgement, not a change to other corpus sources. AptaBase
policy is unchanged (`unresolved_trim_blocks_eligibility` defaults to
blocking).

Old vs new proposed decisions:

```text
                 old     new
proposed_accept   109     468
proposed_park    1264     912
proposed_reject   521     514
trim_construct_unresolved primary parks  352  →  0
```

The previous 352 unresolved-trim parks became proposed technical accepts
where alphabet and core length already passed. Length and alphabet rules
still applied: 10 recovered records became `length_out_of_range` rejects
(8 >100, 2 <20). DNA/ssDNA (909), FANA (3), missing sequence (399),
true IUPAC and malformed alphabet rejects were unchanged at S3; the four
complex constructs remained available for the human park overlay.

### 4. CHECKPOINT-1 decisions and closure

Active review (194 rows: 191 accept-with-diagnostics including random
audit and boundary/medium-trim cases, plus 3 FANA parks) was confirmed
current. Mechanical DNA parks and missing-sequence rejects were not added
to human review. Alphabet overlays then parked the four complex constructs
and preserved the 10 IUPAC/malformed rejects.

```text
final accept = 468
final park = 916
final reject = 510
accept + park + reject = 1894

overrides to accept = 0
overrides to park = 4
overrides to reject = 0

alphabet recoveries applied = 17
true IUPAC final rejects = 9
malformed final rejects = 1
complex construct final parks = 4
FANA parks = 3
DNA / ssDNA parks = 909
missing-sequence rejects = 399
length_out_of_range rejects = 101
```

Park reasons: 909 `non_rna_molecule` + 3 `molecule_type_unresolved` + 4
`complex_construct_unresolved` = 916.

Reject reasons: 399 `missing_sequence` + 101 `length_out_of_range` + 9
IUPAC + 1 malformed = 510.

QC retained on accepted records (provenance, not gates):

```text
trim_requires_review = 359
constants_suspected_unresolved = 359
trim_combined_exceeds_40pct = 29
medium trim confidence = 95
```

CHECKPOINT-1 closed = yes.
`authorised_for_s4 = 468`, meaning technically eligible after UTexas
sequence/molecule/checkpoint review only.

### 5. Global-S4 handoff (not global S4)

`config/global_s4_sources/utexas.json` selects the 468 authorised
canonical rows and joins sequence-safe UTexas source-metadata fields
(`utexas_kd_nm`, `utexas_affinity`, `utexas_type_of_nucleic_acid`,
`utexas_post_selex_modifications`) for later global target/evidence work.
Those fields were not scored.

```text
global-S4 handoff prepared = yes
global S4 executed = no
target normalisation performed = no
protein filtering performed = no
evidence scoring performed = no
leakage applied = no
global dedup performed = no
balancing performed = no
partitioning performed = no
```

Ignored artefacts: `data/interim/global_s4_ready/utexas_global_s4_input.csv`
and `utexas_global_s4_handoff_summary.md`. Tracked note:
`docs/data_curation/utexas_global_s4_handoff.md`.

### Verification

- Targeted UTexas S2/S3/CHECKPOINT-1/alphabet/approved-trim + AptaBase
  checkpoint/handoff tests included in the broader suite
- Broader data-preparation suite (same hang-prone legacy AptaBase
  cleaner/parser and ENA exclusions as before): **618 passed**
- Deterministic rerun: byte-identical final S2 normalised, S3 decisions,
  CHECKPOINT-1 resolution artefacts, UTexas global-S4 input and handoff
  summary
- Raw workbook SHA unchanged =
  `b5a66beb58d30c5c3d2f36a29ea2cc3678e7d4a6b1bb1a97efc1e166a49fd15c`
- AptaBase scientific interim outputs were not rewritten
- The 47 approved UTexas trim-rule decisions were not altered

### Pipeline state

```text
UTexas S1 complete
UTexas S2 complete
UTexas S3 complete
CHECKPOINT-1 closed
468 records authorised for future global S4
global S4 executed = no
```

Laura/ChatGPT should review the UTexas CHECKPOINT-1 closure summary and
the global-S4 handoff summary before beginning corpus-wide global S4.
Do not merge UTexas with AptaBase yet.

## 2026-08-26 — AptaDB S0 registration (three-file logical source)

### Stage

S0a registry extension and AptaDB registration only. AptaDB S1 had not yet
been run when this entry was drafted; the S1 extraction follows as a
separate log item after the extract completed. No S2, S3, target
normalisation, evidence scoring, leakage application, parking or
deduplication was started for AptaDB.

### What was done

The tracked registry previously required a unique `source_key` and a unique
`source_dataset` per row, which could not represent AptaDB's three
authoritative exports as one logical source. Uniqueness was changed so that:

- many rows may share one `source_key` when they also share one
  `source_dataset`;
- a `source_dataset` still belongs to exactly one `source_key`;
- registered paths remain unique.

Existing one-file sources are unchanged. CSV row counting now tries
`utf-8-sig` and, on `UnicodeDecodeError`, retries `latin-1` without rewriting
the file. That fallback is required because AptaDB `interaction.csv` and
`aptamer.csv` are not valid UTF-8.

Three registry rows were added, all `source_key=aptadb` and
`source_dataset=aptadb_official_export_2026-08`:

| Path | SHA-256 | Rows |
|---|---|---:|
| `data/raw/AptaDB/interaction.csv` | `6dbd97f20fa6f98d359d697713c43032d5a6a3c1a400d80ef28a150d676dff86` | 1,350 |
| `data/raw/AptaDB/aptamer.csv` | `9d3ab029d1de4408d2406051a68bc0e6da347ee1be1838aee9c938ca3f3fb464` | 1,293 |
| `data/raw/AptaDB/protein.csv` | `4de0d8b105b3318c9704ff64819089f5e17b5c735f0730724052f3e808325f79` | 194 |

`redistribution_status` remains `unknown`. Snapshot date is `2026-08-04`
(inventory-refresh campaign; the interaction export was added then).
`molecule.csv`, `cell.csv` and `other.csv` are forbidden registry inputs and
were not read or downloaded.

S0a was rebuilt successfully: 10 registered rows validated (8 unique
source keys). The only inventory warnings were the two pre-existing AptaBase
overrides. Nothing under `data/raw/` was written.

### Decisions made

- AptaDB is one logical dataset with three registered files, not a single
  interaction path with companion hashes hidden in `notes`.
- S1 remains interaction-grain: `interaction.csv` is the spine.
- Encoding: utf-8-sig, then latin-1. The aptamer molarity header's
  non-UTF-8 micro-symbol token is not repaired.
- Non-protein AptaDB lookup tables stay out of the registry.

### Outputs produced

- Tracked: `config/source_registry.csv`; `scripts/data_preparation/s0_build_registry.py`; S0 tests
- Ignored: rebuilt `data/interim/registry/source_registry.csv`

### Numbers

- Registered rows: 10 (previously 7); unique source keys: 8
- AptaDB files validated: 3
- Inventory warnings: 2 (AptaBase only)
- AptaDB raw SHA-256 values matched the registry and the preflight audit

### Open questions carried forward

- AptaDB S1 extraction (next)
- AptaDB S2 molecule/chemistry classification and constant-region proposals
- AptaDB S3 technical eligibility, ssDNA parking, and source-level
  `missing_target` rejection logging for the 37 unlinked aptamers
- Global S4 target canonicalisation, UniProt beyond the supplied protein
  table, evidence scoring, and leakage

## 2026-08-26 — AptaDB S1 verbatim extraction

### Stage

AptaDB S1 extraction only. No S2 normalisation, molecule classification,
constant-region inference, target canonicalisation, evidence scoring,
filtering, parking, leakage, or CHECKPOINT-1 work was started for AptaDB.

### Source

Logical source `aptadb` (`source_dataset=aptadb_official_export_2026-08`),
registered as three SHA-pinned files:

- `data/raw/AptaDB/interaction.csv` — 1,350 rows; SHA-256
  `6dbd97f20fa6f98d359d697713c43032d5a6a3c1a400d80ef28a150d676dff86`
- `data/raw/AptaDB/aptamer.csv` — 1,293 rows; SHA-256
  `9d3ab029d1de4408d2406051a68bc0e6da347ee1be1838aee9c938ca3f3fb464`
- `data/raw/AptaDB/protein.csv` — 194 rows; SHA-256
  `4de0d8b105b3318c9704ff64819089f5e17b5c735f0730724052f3e808325f79`

`interaction.csv` and `aptamer.csv` are read with utf-8-sig then latin-1.
`protein.csv` is valid UTF-8. Raw files were not transcoded. The aptamer
molarity header's non-UTF-8 micro-symbol token was left unrepaired.

### Identifier decision

`interaction.csv.Index` is unique across 1–1,350 and is the interaction
spine. S1 therefore uses:

- `native_id` = `Index` verbatim
- `record_id` = `aptadb:{Index}`

Duplicate `(Apta_index, TargetID)` pairs are retained as separate
interaction records. Aptamer-table rows without an interaction are not
given fabricated interaction identities.

### Extraction methodology

Adapter: `scripts/data_preparation/adapters/aptadb.py`, dispatched by
`scripts/data_preparation/s1_extract.py --source aptadb`. The dispatcher
resolves the three registered paths by basename rather than hardcoding
absolute locations.

For each interaction row the adapter joins `Apta_index` to `aptamer.csv`,
hard-fails if the aptamer is absent, compares interaction `Sequence` with
aptamer `Sequence` byte-for-byte, and copies `aptamer.csv.Sequence` into
`sequence_raw`. Protein interactions join `TargetID` to `protein.csv`
`Uni-port ID` and copy `Protein names` into `target_name_raw`. Molecule,
Cell and Other interactions leave `target_name_raw` empty; their TargetIDs
are sidecar-only. `Reference(pubmed ID)` is copied verbatim to `pubmed_id`.
`publication` is left empty because the source does not supply publication
text. No sequence normalisation, T→U conversion, trimming, chemistry
classification, or evidence assignment occurs at S1.

The unnamed trailing interaction field is preserved in the sidecar. One
row (Index 370) has a nonempty trailing token; it is retained verbatim and
is not interpreted.

### Unlinked-aptamer reconciliation

Thirty-seven aptamer-table rows have no interaction. They are omitted from
`aptadb_extracted.csv` and written to
`data/interim/extracted/aptadb_unlinked_aptamers.csv` (DNA 34, RNA 3) with
`planned_s3_reason=missing_target`. Later S3 must emit source-level
`missing_target` rejection-log rows; that step is not implemented here.

### Outputs produced

- Ignored under `/data/`: `aptadb_extracted.csv` (1,350 rows),
  `aptadb_source_metadata.csv` (1,350 rows),
  `aptadb_unlinked_aptamers.csv` (37 rows), `aptadb_s1_report.md`
- Tracked: adapter, S1 dispatcher, tests, this log entry

### Numbers

- Canonical rows: 1,350; unique native IDs: 1,350; unique record IDs: 1,350
- Aptamer joins: 1,350/1,350; sequence disagreements: 0/1,350
- Protein interactions: 639; protein joins: 639/639; protein-table
  coverage: 194/194
- Non-protein interactions: 711 (`Molecule` 393, `Cell` 189, `Other` 129)
- Nonempty `target_name_raw`: 639; empty `target_name_raw`: 711
- Nonempty `pubmed_id`: 1,350; nonempty `publication`: 0
- Unlinked aptamers: 37
- Deterministic rerun: byte-identical canonical, sidecar and unlinked CSVs
- AptaDB raw SHA-256 values unchanged before and after S0/S1
- No file under `data/` is tracked by Git

### Deferred

- S2: molecule/chemistry classification, constant-region proposals;
  grouping helper should later use `target_name_raw + publication`,
  falling back to `target_name_raw + pubmed_id` when publication is empty
- S3: technical eligibility, ssDNA parking, and `missing_target` logging
  for the 37 unlinked aptamers
- S4: UniProt/PDB/target canonicalisation beyond the supplied protein
  table, evidence scoring, leakage, clustering, partitions

### Pipeline status

```text
AptaDB S0 complete
AptaDB S1 complete
AptaDB S2 has not started
No AptaDB records are yet authorised for global S4
```

## 2026-08-26 — AptaDB S2 normalisation and constant-region proposals

### Stage

AptaDB S2 sequence normalisation, QC and constant-region proposal generation
only. No S3 filtering, parking, rejection, target canonicalisation, evidence
scoring, leakage, clustering, balancing, partitioning, or CHECKPOINT-1
approval of AptaDB motifs was started.

A narrow shared corrective pass was applied before approving this milestone:
alignment-gap handling, canonical `trim_confidence`, and A/C/G-only alphabet
provenance. S3 was not started.

### Input

Registered AptaDB S1 outputs:

- `data/interim/extracted/aptadb_extracted.csv` (1,350 interaction records)
- `data/interim/extracted/aptadb_source_metadata.csv` (1,350 rows)
- `source_key = aptadb`
- `source_dataset = aptadb_official_export_2026-08`

Raw SHA-256 values unchanged:

- `interaction.csv` `6dbd97f20fa6f98d359d697713c43032d5a6a3c1a400d80ef28a150d676dff86`
- `aptamer.csv` `9d3ab029d1de4408d2406051a68bc0e6da347ee1be1838aee9c938ca3f3fb464`
- `protein.csv` `4de0d8b105b3318c9704ff64819089f5e17b5c735f0730724052f3e808325f79`

### Purpose

Normalise every interaction-grain record with the shared S2 machinery while
preserving every row. S2 does not reject, park or deduplicate.

### Reconciliation

1,350 in / 1,350 out; 1,350 unique `record_id`; row disappearance = 0.
`sequence_raw` unchanged. S1 provenance unchanged. S4 target/evidence fields
remain blank.

### Molecule mapping

Source `aptamer.csv.Aptamer Chemistry` is authoritative. Molecule type is not
inferred from alphabet. Unexpected or blank chemistry is a hard adapter
failure.

- `RNA` → `molecule_type=RNA`, `chemistry=RNA` (289)
- `DNA` → `molecule_type=ssDNA`, `chemistry=DNA` (1,061)

AptaDB `DNA` is treated as DNA aptamers (`ssDNA`), not double-stranded DNA.

### Alphabet and T→U

Shared alphabet vocabulary is `RNA` / `DNA_T` / `mixed_T_U` / `invalid`
(not a separate `RNA_U` token). That `RNA` versus plan `RNA_U` discrepancy
is a later global schema-alignment item, not migrated in this pass.

| alphabet_as_reported | Count |
|---|---:|
| RNA | 288 |
| DNA_T | 1,060 |
| mixed_T_U | 1 |
| invalid | 1 |

Of the 289 source-RNA records, 288 are U-alphabet and one is mixed T/U.
No source-RNA record was a clean T-only DNA-alphabet report, so
`t_to_u_applied=true` is 0. The mixed T/U RNA row was not silently
transcribed (`mixed_t_u` policy = review). ssDNA retains T.

A/C/G-only sequences cannot be distinguished by alphabet alone. The shared
classifier now uses authoritative source `molecule_type` as the tiebreak:
source-confirmed ssDNA → `DNA_T`; source-confirmed RNA → `RNA`. Sequence
characters are not changed. One source-confirmed ssDNA A/C/G-only row is
therefore `DNA_T` rather than the previous misleading `RNA` label.

### QC (aggregate)

Display transformations: `uppercase` 3. Internal `-` / `.` are no longer
stripped as display separators.

| Flag / diagnostic | Count |
|---|---:|
| alignment gaps | 2 |
| mixed T/U | 1 |
| invalid character | 1 |
| core below min length (<20) | 25 |
| core above max length (>100) | 21 |
| known promoter detected | 1 |
| trim_requires_review | 2 |
| rows with any QC flag | 50 |

After terminal-label stripping, remaining `-` and `.` in the sequence body
are retained, flagged `alignment_gaps`, and left for later S3
(`alignment_gaps` / `05_repair_alignment_gaps`). They are not silently
repaired. Genuine `5'-` / `-3'` / `[3'T]` terminal notation continues to be
stripped. The remaining `invalid_character` row is a non-gap unexpected
character, not an alignment gap. Both gap rows remain in S2.

Review-candidate rows are 50 (was 49) because the internal-hyphen row is now
flagged instead of being silently cleaned.

### Length

Computed from the shared normalised representation, not AptaDB source
`Length`. No trim was applied, so full and core distributions are identical:

- min / median / max: 12 / 50 / 133
- `<20`: 25; `20–25`: 72; `26–89`: 1,156; `90–100`: 76; `>100`: 21

Out-of-range lengths were retained for S3.

### Construct / trim

`construct_scope=unknown` for all 1,350 (no reliable source construct-scope
field; absence of a detected primer is not evidence of random-region-only).
`trim_status`: `no_constants_detected` 1,349; `constants_suspected_unresolved` 1
(configured T7 motif detection). `trim_confidence = n/a` for all 1,350
(canonical vocabulary; no approved trim applied; unapplied medium-confidence
proposals are not written as `medium`). `sequence_core == sequence_full` for
all 1,350. Records actually trimmed: 0. Previously approved high-confidence
trims applied: 0.

### Constant-region inference

Shared grouping helper now resolves publication identity as nonempty
`publication`, else nonempty `pubmed_id`, and still requires a usable
`target_name_raw`. Canonical `publication` was not rewritten. AptaDB protein
rows therefore group as `target_name_raw + pubmed_id`. The 711 Molecule/Cell/
Other rows with empty `target_name_raw` were not grouped by PMID alone
(diagnostics: 711 skipped missing grouping evidence).

Gapped sequences are excluded from positional consensus. Proposal counts did
not change.

| Inference statistic | Count |
|---|---:|
| Candidate groups considered | 255 |
| Groups meeting minimum size (≥5) | 28 |
| 5′ group-consensus proposals | 8 |
| 3′ group-consensus proposals | 7 |
| Records associated with medium-confidence proposals | 66 |
| Known-motif proposal rows | 1 |
| Genuine proposal rows total | 16 |

Newly inferred medium-confidence motifs were written as proposals
(`applied=false`) and did **not** mutate `sequence_core`.
`config/constant_regions.yaml` was not modified.

### Integrity

- S1 canonical SHA-256 before/after: `bee7aebf3fda9164918bf25945fb210eed7f576566881aad35f7d9b17ba1ca0b`
- Source-metadata SHA-256 before/after: `12e817369c620625c6d9758d88de71b82ca387d7376ca21d4614c4c7343d5465`
- Raw SHA-256 unchanged (values above)
- Deterministic rerun: pass
- No file under `data/` is tracked

### Deferred

- S3: technical eligibility, ssDNA parking, length/invalid/mixed-T/U/
  alignment-gap rejection logging, and `missing_target` logging for the 37
  unlinked aptamers. Existing UTexas S3 infers `alignment_gaps` from
  `invalid_character` plus remaining `-`/`.`; later S3 should also honour
  the explicit S2 `alignment_gaps` flag.
- CHECKPOINT-1: human review of AptaDB medium-confidence constant-region
  proposals before any trim is applied
- S4: UniProt/PDB/target canonicalisation, evidence scoring, leakage
- Global schema: migrate shared `alphabet_as_reported` token `RNA` → plan
  `RNA_U` across sources

### Pipeline status

```text
AptaDB S0 complete
AptaDB S1 complete
AptaDB S2 complete
AptaDB S3 has not started
No AptaDB records are yet authorised for global S4
```

## 2026-08-26 — AptaDB S3 technical eligibility and CHECKPOINT-1 package

### Stage

AptaDB **S3 technical sequence eligibility**, ssDNA parking, source-explicit
non-protein-target parking, rejection logging, and generation of the
record-level **CHECKPOINT-1** review package. Human review decisions were
not applied. CHECKPOINT-1 was not closed. Constant-region proposals were
not applied. Global S4 was not started.

### S3 policy

Tracked policy: `config/source_eligibility/aptadb.json`. Shared seed
`42` and random-accept audit size `30` are recorded in that policy.
AptaBase and UTexas S3/CHECKPOINT-1 behaviour was not rewritten.

S3 assigns exactly one primary interaction-stream route per canonical
row. No interaction row disappears. The 1,350-row interaction spine is
the denominator; the 37 unlinked aptamers are reconciled separately.

Deterministic precedence:

1. technical rejection
2. ssDNA park
3. RNA non-protein-target park
4. RNA-protein technically eligible

A malformed ssDNA record is therefore rejected, not parked. A
technically valid ssDNA record is parked as ssDNA regardless of Target
chemistry. Only technically valid RNA proceeds to target-chemistry
routing. Canonical S3 CSV remains byte-identical to S2; routing lives in
the decision sidecar.

### Source-specific scientific rules

- Length is evaluated on `sequence_length_core` (20–100 nt). Out of
  range → `length_out_of_range`. Because no S2 trim was applied,
  `sequence_core == sequence_full` for all 1,350 rows, so `<20` and
  `>100` reject directly. A future full-in-range / core-out-of-range
  applied-trim case would enter review rather than automatic rejection.
- Explicit S2 `alignment_gaps` is honoured even without
  `invalid_character`. Those rows reject as `alignment_gaps` and enter
  CHECKPOINT-1. Gaps are not silently removed.
- Mixed T/U is not computationally repaired (`mixed_T_and_U`). The
  remaining non-gap unexpected character rejects as `invalid_alphabet`.
  Both enter CHECKPOINT-1 as judgement-dependent technical cases.
- Surviving `molecule_type=ssDNA` is parked (`ssdna_parked`). T is
  retained. DNA is not rejected merely for being DNA.
- Technically valid RNA uses the AptaDB sidecar `Target chemistry`
  value. `Protein` continues as S3-eligible. `Molecule` / `Cell` /
  `Other` park as `non_protein_target_parked`. Empty `target_name_raw`
  is not the parking criterion. Canonical `target_type` /
  `target_type_source` are not populated.
- Unlinked aptamer.csv rows (no interaction) receive source-level
  `missing_target` rejection-log entries with identity
  `aptadb:unlinked:{Apta_index}` and stage `S3_source_reconciliation`.
  They are not fake interaction Index IDs and are not parked.

### Target/evidence/leakage deferral

AptaDB S3 does not classify Binding Conditions/Buffer + PMID as E3.
Evidence mapping and thresholding (`no_binding_evidence`,
`evidence_below_threshold`) remain deferred to global S4. This is an
architecture decision, not an accidental omission of the plan wording.

Target canonicalisation, Molecule/Cell/Other name resolution, UniProt
lookup, target-family assignment, NDM-1/KPC/OXA/HSA leakage exclusion,
PDB canonical-field population, cross-source deduplication, clustering,
balancing and FT/REF/EVAL partitioning also remain deferred.

### Interaction reconciliation

```text
rows in = 1350
technical rejects = 50
parked ssDNA = 1035
parked non-protein RNA = 115
RNA-protein technically eligible = 150
1350 = 50 + 1035 + 115 + 150
```

Technical rejects by primary reason:

```text
missing_sequence = 0
length_out_of_range = 46
mixed_T_and_U = 1
alignment_gaps = 2
invalid_alphabet = 1
ambiguous_bases = 0
primer_like = 0
library_template = 0
truncated_sequence = 0
```

Parking:

```text
source ssDNA before technical rejection = 1061
technically rejected ssDNA = 26
actually parked ssDNA = 1035

RNA non-protein before technical rejection = 125
technically rejected RNA non-protein = 10
actually parked RNA non-protein = 115
```

Eligible corpus lane:

```text
RNA Protein before technical rejection = 164
technically rejected RNA Protein = 14
final technically eligible RNA Protein = 150
```

### Source-level unlinked-aptamer reconciliation

```text
unlinked aptamers = 37
missing_target rejection entries = 37
chemistry split: DNA 34 / RNA 3
```

These 37 are additional to the 1,350-row interaction stream. Rejection
log total = 87 (50 interaction-spine technical rejects + 37
`missing_target`).

### CHECKPOINT-1

Unique review records: `238`. Human columns (`manual_decision`,
`manual_sequence_corrected`, `manual_target_corrected`, `manual_notes`)
are blank. Permitted decisions: `keep` / `drop` / `edit`. Machine
`proposed_decision` is not a human decision.

```text
judgement-dependent technical = 4
  (alignment_gaps 2, mixed_T_and_U 1, invalid_alphabet 1)
constant-proposal records in review = 67
  (group-consensus 66 + known-motif 1; proposals remain applied=false)
length-boundary records in review = 148
  (20–25 nt = 72; 90–100 nt = 76)
random kept audit = 30 (pool 150, seed 42, shortfall 0)
```

Batch assignment is one primary batch per record (reasons are combined
when a record qualifies for several categories):

```text
01_judgement_dependent_technical = 4
02_constant_region_proposal = 66
03_length_boundary = 141
04_random_kept_audit = 27
238 = 4 + 66 + 141 + 27
```

The known-motif proposal row is also judgement-dependent, so it occupies
batch 01 while remaining in the 67 constant-proposal count. Three of the
30 random-audit rows already had a higher-priority batch, leaving 27
exclusive batch-04 rows. `<20` and `>100` length rejects are not queued
as boundary records.

Canonical `trim_confidence` remains `n/a` for all 1,350 rows. No trim
was applied. `config/sequence_normalisation_rules.json` and
`config/constant_regions.yaml` were not modified.

### Verification

- AptaDB S3 / CHECKPOINT-1 plus AptaBase/UTexas S3, eligibility and
  checkpoint regression tests: **156 passed**
- Additional AptaDB S1/S2, constant-region and checkpoint-apply tests:
  **126 passed**
- Deterministic rerun: byte-identical S3 canonical, decisions, review,
  local-detail, reason counts, rejection log, park sidecars
- S2 canonical SHA-256 unchanged =
  `b4075b602a9e569e3e91a66f1437a8939d56432138b8e9fcd2063920b0028aa5`
- Raw SHA-256 unchanged:
  `interaction.csv` `6dbd97f20fa6f98d359d697713c43032d5a6a3c1a400d80ef28a150d676dff86`
  `aptamer.csv` `9d3ab029d1de4408d2406051a68bc0e6da347ee1be1838aee9c938ca3f3fb464`
  `protein.csv` `4de0d8b105b3318c9704ff64819089f5e17b5c735f0730724052f3e808325f79`
- No file under `data/` is tracked

### Outputs (gitignored under `data/interim/checkpoints/aptadb_cp1/`)

- `aptadb_s3_canonical.csv` / `aptadb_s3_decisions.csv`
- `rejected_aptadb.csv` (interaction technical rejects plus 37 unlinked)
- `aptadb_s3_parked_ssdna.csv` / `aptadb_s3_parked_non_protein.csv`
- `aptadb_checkpoint1_review.csv` (sequence-free, all 1,350 rows)
- `aptadb_checkpoint1_local_detail.csv` (sequence-bearing, all rows)
- `aptadb_checkpoint1_reason_counts.csv` /
  `aptadb_checkpoint1_summary.md`
- `manual_review/aptadb_checkpoint1_manual_review.csv` (active queue;
  this is the file Laura must review)
- `manual_review/aptadb_checkpoint1_manual_review_index.csv`
- `manual_review/aptadb_checkpoint1_manual_review_summary.md`

Tracked code, tests and configuration:

- `config/source_eligibility/aptadb.json`
- `scripts/data_preparation/common/eligibility.py`
- `scripts/data_preparation/adapters/aptadb_s3.py`
- `scripts/data_preparation/s3_classify.py`
- `scripts/data_preparation/checkpoint1_prepare_review.py`
- `tests/data_preparation/test_eligibility.py`
- `tests/data_preparation/test_adapter_aptadb_s3.py`
- `tests/data_preparation/test_aptadb_s3_classify.py`
- `tests/data_preparation/test_aptadb_checkpoint1_prepare_review.py`
- this log entry

### Pipeline stop

```text
CHECKPOINT-1 package generated.
No human decisions applied.
No AptaDB record is authorised for S4 yet.
The pipeline is stopped awaiting Laura CHECKPOINT-1 review.
```

## 2026-08-26 — AptaDB CHECKPOINT-1 structured review schema

### Stage

AptaDB CHECKPOINT-1 remains **unapplied**. This pass extends the review
artefacts and future application logic so human review can record sequence
corrections, molecule/chemistry overrides, group-wise constant-region
decisions, numeric trim-boundary corrections, per-record exceptions, and
bulk audit confirmation without pasting hand-trimmed cores.

No `manual_decision` was entered. No trim was applied. Canonical S2/S3
outputs were not rewritten. S4 was not started. CHECKPOINT-1 is not complete.

### Why the schema was extended

The previous record-level fields (`manual_decision`,
`manual_sequence_corrected`, `manual_target_corrected`, `manual_notes`)
could not express:

- an experimental molecule correction that must re-run shared
  molecule-aware normalisation while preserving `sequence_raw`;
- approval, numeric override, rejection or deferral of a proposed
  constant-region trim;
- a per-record exception to an otherwise valid group trim.

### Review artefacts

Human fields remain blank. Machine recommendations are stored separately
(`review_recommendation`, `review_rationale`, `requires_specific_human_decision`,
and `recommended_*` counterparts) and are not human decisions.

A group-level CSV now carries one row per constant-region proposal group.
Otherwise-clean `length_boundary` and/or `random_kept_audit` rows are marked
bulk-eligible with recommendation `keep_current_route`; confirming them still
requires an explicit later `confirm=true` step.

The validator fails closed: 238 unresolved manual decisions, 9 unresolved
constant groups, 2 unresolved exceptions, 168 unconfirmed audit-only rows,
`ready_for_application=0`.

### Future apply semantics (not executed)

Preserved `sequence_raw`; optional reviewed sequence correction; molecule
override through the shared normaliser; numeric trim of reviewed
`sequence_full`; re-evaluation under AptaDB S3 technical rules. `defer`
does not become `keep`. Group decisions propagate unless a record-level
trim action overrides them. Guard rails: core ≥20 nt, trim not longer than
the sequence, combined fraction ≤40%.

### Verification

- Structured review/apply tests plus AptaDB/AptaBase/UTexas S3 and
  checkpoint regressions: **216 passed**
- Deterministic review-package regeneration: pass
- Raw SHA-256 unchanged
- S2/S3 canonical SHA-256 unchanged
  (`b4075b602a9e569e3e91a66f1437a8939d56432138b8e9fcd2063920b0028aa5`)

### Pipeline stop

```text
CHECKPOINT-1 structured review package generated.
No human decisions applied.
No trims applied.
No AptaDB record is authorised for S4 yet.
The pipeline is stopped awaiting Laura CHECKPOINT-1 review.
```

## 2026-08-26 — AptaDB CHECKPOINT-1 human review entered (unapplied)

Human CHECKPOINT-1 decisions were completed for AptaDB: 238 record
decisions and 9 group decisions were reviewed. The fail-closed validator
passed (`ready_for_application=238`; unresolved manual decisions,
constant groups, record exceptions, unconfirmed audit-only rows,
contradictory fields, invalid trim lengths and edits without a
specification all 0). No decisions have yet been applied to canonical
outputs. S4 remains blocked pending reviewed application. CHECKPOINT-1
is not closed.

## 2026-08-26 — AptaDB CHECKPOINT-1 application dry-run (unapplied)

Human CHECKPOINT-1 decisions were validated (`ready_for_application=238`).
An application dry-run using the real apply transformation failed closed:
60 human-approved constant-region trims exceeded the combined ≤40%
threshold (HIV/Gag-Pol, AP65 ordinary members, OX40, pancreatic
polypeptide, CBF1, CD25, NPY). That stop was correct given the
implementation at the time: >40% was coded as a hard apply-time gate.
No complete post-review 1,350-row routing preview was authorised.
Technical/exception simulations for `aptadb:230`, `aptadb:491`,
`aptadb:305`, `aptadb:1170` and `aptadb:459` succeeded in isolation,
including G5α3N.4 core 57 nt and AP65_A1 23/0. Canonical S2/S3 outputs
were not changed. CHECKPOINT-1 remained unapplied. S4 remained blocked.
Real application was **NO-GO** pending a specification-aligned
reinterpretation of the 40% rail.

## 2026-08-27 — AptaDB CHECKPOINT-1 large-trim semantics + second dry-run (unapplied)

Specification review clarified that "never trim more than 40% of a
sequence in one operation without flagging" is a review/trigger guard
rail, not an absolute prohibition. The apply path was corrected:

- unreviewed / automatic / machine-only combined trims >40% still fail
  closed and require explicit CHECKPOINT-1 human review;
- an explicit human group or record `manual_trim_action` of `approve` or
  `override` may apply a biologically large trim;
- recommendations, bulk `keep`, blank/defer/reject, and inferred
  approvals are not authorisation;
- empty core, core <20 nt, over-length, negative, and non-integer trims
  remain hard failures;
- every human-approved >40% trim records derived
  `large_trim_human_approved` provenance (percentage, source, action,
  5′/3′ nt, core length, CHECKPOINT-1 authorisation) in notes and
  `qc_flags`.

Reviewed trim lengths were not reduced to satisfy 40%. Human review
files were not edited.

The fail-closed validator still passed (`238` total; `0` unresolved
record/group/exception/audit/blocker rows; `ready_for_application=238`).
The second full AptaDB application dry-run succeeded: all 1,350
interactions received a post-review route; remaining guard-rail
failures = `0`; human-approved >40% cohort = `60`; in-memory and
on-disk reruns were byte-identical. Canonical S2/S3, raw AptaDB files,
source-metadata sidecar, recommendation JSON, and all three human
review files were unchanged. No resolved/S4 outputs were written.
CHECKPOINT-1 remains unapplied. S4 remains blocked. The checkpoint is
not closed.

Post-review routing (including 1 human drop inside technical rejects):
`47` technical rejects + `1037` parked ssDNA + `115` parked RNA
non-protein + `151` RNA-protein technically eligible = `1350`.
Unlinked aptamers remain `37` `missing_target`. `authorised_for_s4=0`.

Real CHECKPOINT-1 application is technically **GO** from this dry-run.
It was not executed in this pass.

## 2026-08-27 — AptaDB CHECKPOINT-1 applied and closed

Human CHECKPOINT-1 review was applied to AptaDB and the checkpoint is
**closed**. The real application used the same `apply_reviewed_record`
transformation as the validated dry-run. Applied canonical, routing,
rejection, parked, eligible, change-report, group-summary, and large-trim
artefacts were byte-identical to that dry-run preview. Guard-rail
failures remained 0. S4 was not started.

This checkpoint exists because AptaDB source annotation, construct
constants, and molecule labels are not reliable enough to feed S4
automatically. The 238-row review queue is the scientific authorisation
for sequence repair, molecule correction, and terminal trimming. The 40%
combined-trim rule is a review trigger, not an absolute prohibition:
sixty constant-region trims exceeded 40% and were applied only because
CHECKPOINT-1 explicitly approved or overrode them, with
`large_trim_human_approved` provenance retained. Empty core, core <20 nt,
over-length, negative, non-integer, contradictory, and non-contiguous
trims remain hard failures.

Record decisions: 173 keep / 64 edit / 1 drop (`aptadb:305`, mixed T/U,
unrepairable from source evidence). Group decisions: 5 approve / 3
override / 1 reject (albumin deletion-series left untrimmed because the
shared prefix is part of the shortened construct). Bulk audit
confirmations: 168. Source-sequence corrections: 3. Molecule correction:
1 (G5α3N.4 / `aptadb:1170`, AptaDB ssDNA annotation to experimental RNA;
reviewed trim 18/0; core 57 nt; high-confidence T7 motif retained;
route technically eligible). AP65_A1 (`aptadb:459`) used the record-level
23/0 override rather than the group 3′ trim. Alignment-gap and terminal-
period repairs (`aptadb:230`, `aptadb:491`) restored ssDNA parking
without mutating `sequence_raw`.

Post-review interaction routing: 47 technical/human rejects + 1037
parked ssDNA + 115 parked RNA non-protein + 151 RNA-protein technically
eligible = 1350. Unlinked aptamers remain 37 source-level
`missing_target` rows outside that denominator. Only the 151 technically
eligible RNA-protein records are marked authorised for a future global
S4 handoff. That handoff has not been prepared.

Original S2, pre-review S3, raw AptaDB files, source-metadata sidecar,
review CSVs, and the recommendation JSON were not overwritten.
In-memory and on-disk deterministic reruns matched the authoritative
applied payload.

### Verification

- AptaDB structured review / dry-run / apply, checkpoint prepare/apply,
  AptaDB S3, shared eligibility, sequence normalisation, and
  AptaBase/UTexas S3 and checkpoint regressions: **287 passed**
- Dry-run vs applied byte identity: pass
- Frozen human-review, recommendation, S2/S3, and raw hashes: unchanged
- S4 was not started

## 2026-08-31 — RiboAptamer registration and S1 extraction

**Stage:** Aim 2 / data curation / S0 registration + S1 extraction only.
RiboAptamer S2 was not started.

### What was done

The corrected 509-row Ribocentre/RiboAptamer export was registered as the
authoritative Tier-1 source and frozen by SHA-256 and expected row count.
A source-specific S1 adapter then extracted every registered row into the
canonical corpus schema, with a complete source-metadata sidecar. All 509
source records and all 13 raw source columns were retained. Deterministic
row-based source IDs were used because `Sequence Name` is complete but
not unique. Sequence normalisation, target extraction, target
classification, affinity/evidence mapping, eligibility filtering,
parking, leakage checks, and deduplication were deliberately deferred to
their specified later stages.

### Decisions made

- `native_id` uses the zero-padded 1-based source CSV data-row number
  (`001`…`509`) because `Sequence Name` has three duplicated identifiers
  affecting six rows. `record_id` is `riboaptamer:{native_id}`.
  `Sequence Name` is preserved verbatim in the sidecar only.
- Exact duplicate source rows are intentionally retained as separate S1
  records. Deduplication belongs later (S5), not at extraction.
- Source `Category` is recorded only as structured provenance in
  `notes` (`category_prior`). Source `Type` (`Proteins`, `Small
  molecules`, `Cells`, `Nucleic acids`) is a source target-class field
  retained in the sidecar. Neither is used as experimental molecule type
  or as a canonical target.
- The source has no canonical target column, so `target_name_raw` is
  empty through S1. Target identity will be extracted and resolved
  globally at S4 from the retained descriptive metadata (`Aptamer Name`,
  `Description`, `Sequence Name`, `Category`, `Type`).
- RiboAptamer `redistribution_status` remains `unknown` because no
  reliable local licence information was identified.
- Numeric PubMed IDs are parsed from `PubMed Link` only where the URL
  matches an unambiguous PubMed-ID pattern (505/509). The remaining four
  links are non-PubMed publisher/dissertation URLs and were left unparsed.
  `Article name` is a clone/variant label, not a publication citation.
  DOI values are not invented from arbitrary external URLs.

### Inputs used

- `source_dataset = riboaptamer_full_2026-08`
- `data/raw/riboaptamer/all_sequences_509_rows.csv`
- SHA-256:
  `721d8c5ea81476c1f371ef8bfa814743f364eaf004c0a6eda2aabd6dc5d9a9fd`
- 509 rows; 13-column UTF-8 CSV (no BOM)
- Snapshot date: `2026-08-04`; tier `1`;
  `redistribution_status = unknown`

### Outputs produced

Ignored under `/data/`:

- `data/interim/registry/source_registry.csv` (operational S0 registry;
  11 validated registered files, exactly one `riboaptamer` entry)
- `data/interim/extracted/riboaptamer_extracted.csv` (509 rows)
- `data/interim/extracted/riboaptamer_source_metadata.csv` (509 rows)
- `data/interim/extracted/riboaptamer_s1_report.md`

Tracked scripts, tests and this log entry. Nothing under `data/` is
tracked.

### Numbers

- 509 rows input
- 509 extracted; 509 unique `record_id`; 509 unique `native_id`
- first native ID `001`; last native ID `509`
- 0 S1 rejections, parking, or filtering
- 13 raw metadata columns preserved in the sidecar; one-to-one join to
  canonical rows
- `sequence_raw` is byte/text-equivalent to source `Sequence`; source
  order preserved
- nonempty PubMed IDs parsed at S1: 505; publication/DOI: 0
- unique `Sequence Name` values: 506; duplicate keys: 3; rows in those
  groups: 6 (native IDs `011`/`012`, `026`/`060`, `031`/`043`)
- source raw hash unchanged before and after S0/S1:
  `721d8c5ea81476c1f371ef8bfa814743f364eaf004c0a6eda2aabd6dc5d9a9fd`
- S0: 11 registered, 11 validated; existing AptaBase inventory-override
  warnings only; no superseded truncated RiboAptamer file registered
- Deterministic S1 rerun: byte-identical canonical and sidecar CSVs

### Open questions carried forward

- S2 will initially use known-motif detection only; no group-wise
  consensus grouping has been authorised for RiboAptamer.
- Target extraction and type reconciliation remain a global S4 /
  CHECKPOINT-2 task, including Category-versus-resolved-type
  disagreements.

### Pipeline status

```text
RiboAptamer S0 complete
RiboAptamer S1 complete
RiboAptamer S2 has not started
No RiboAptamer records are yet authorised for global S4
```

## 2026-08-31 — RiboAptamer S2 sequence normalisation

**Stage:** Aim 2 / data curation / S2 sequence normalisation only.
RiboAptamer S3, CHECKPOINT-1, target extraction, and global S4 were not
started.

### What was done

The 509 extracted RiboAptamer records were passed through the shared
sequence-normalisation implementation. The source was treated as
experimental RNA independently of the source `Type` target-class field.
Alphabet provenance was preserved, and computational T→U transcription
was applied only where a T-alphabet sequence was reported under that
RNA contract. Normalised full and core sequences and lengths were
computed under the current approved-trim architecture: known motifs
were detected but not applied, so `sequence_core` equals
`sequence_full` for every row. Group-wise constant-region inference
was deliberately disabled. Technically problematic records (ambiguous
bases, invalid characters, alignment gaps, and the remaining internal
ellipsis) were retained with QC flags for S3/CHECKPOINT-1 rather than
silently dropped or repaired.

### Decisions made

- Source `Type` (`Proteins` 344, `Small molecules` 122, `Cells` 26,
  `Nucleic acids` 17) remains target-class metadata in the sidecar
  only. It is not `molecule_type`, `chemistry`, canonical
  `target_type`, or an S2/S3 parking rule.
- `molecule_type = RNA` and `chemistry = RNA` come from the source
  contract, not from alphabet and not from `Type`.
- Known-motif detection only for this initial RiboAptamer lane. The
  configured T7 motif library was scanned; detections are proposals
  (`applied=false`) and do not mutate `sequence_core`.
- No group-wise `(Aptamer Name, PubMed)` inference. No
  `experiment_group_id` or `target_name_raw` was manufactured to
  exploit an existing grouping mode.
- Malformed, ambiguous, gapped, and truncated records are carried
  forward with QC. Display-only terminal labels continue to be
  stripped by the shared cleaner; remaining body hyphens, periods,
  slashes, primes, and parenthetical notation are not repaired.
- `(ms)`-style notation is not interpreted as modified-RNA chemistry.
- Target, evidence, affinity, and PDB work remain deferred to global
  S4 / CHECKPOINT-2.

### Inputs used

- `source_dataset = riboaptamer_full_2026-08`
- S1 extracted path: `data/interim/extracted/riboaptamer_extracted.csv`
- S1 sidecar: `data/interim/extracted/riboaptamer_source_metadata.csv`
- Registered raw file: `data/raw/riboaptamer/all_sequences_509_rows.csv`
- SHA-256:
  `721d8c5ea81476c1f371ef8bfa814743f364eaf004c0a6eda2aabd6dc5d9a9fd`
- Shared rules: `config/sequence_normalisation_rules.json`
- Source policy: `config/source_normalisation/riboaptamer.json`

### Outputs produced

Ignored under `data/`:

- `data/interim/normalised/riboaptamer_normalised.csv`
- `data/interim/normalised/riboaptamer_s2_qc.csv`
- `data/interim/normalised/riboaptamer_s2_review_candidates.csv`
- `data/interim/normalised/detected_constants_riboaptamer.csv`
- `data/interim/normalised/riboaptamer_s2_report.md`

Tracked adapter, policy, tests, dispatcher changes, and this log
entry. Nothing under `data/` is tracked.

### Numbers

509 in / 509 out; 0 dropped; 0 parked; 509 unique `record_id`; source
order preserved; sidecar join one-to-one; `sequence_raw` unchanged.

Normalised full length (not source `Length`): min / median / max =
10 / 75 / 179. Buckets are descriptive only: `<20` 9; `20–25` 8;
`26–89` 349; `90–100` 46; `>100` 97. Core lengths are identical
because no trim was applied.

Alphabet (shared vocabulary `RNA` / `DNA_T` / `mixed_T_U` /
`ambiguous` / `invalid`, not a separate `RNA_U` token): `RNA` 498;
`DNA_T` 1; `ambiguous` 4; `invalid` 6; mixed T/U 0.
`t_to_u_applied=true` on 1 RNA record. That T-alphabet row remains
`molecule_type=RNA`; it is not classified as ssDNA.

QC flags (post-display-clean, not raw-character diagnostics):
invalid character 6; ambiguous base 4; alignment gaps 1; truncated
sequence / internal ellipsis 1; mixed T/U 0; core below min 9; core
above max 95; known promoter detected 1; rows with any QC flag 114.
Display cleaning: uppercase 4; whitespace removed 1; terminal 3′
label stripped 1; T→U 1.

The preflight found two raw records containing `-`. After shared
display cleaning, one hyphen belonged to a genuine terminal 3′ label
and was stripped (length 37→33, no remaining QC). The other remains
on the internal-ellipsis record, which also contains digits, so S2
classifies it as `invalid` plus `alignment_gaps` plus
`truncated_sequence`. That is a raw-versus-display-clean distinction,
not a dropped record. Two of the six invalid rows are longer than
100 nt but do not carry `core_above_max_length` because the shared
normaliser returns early on invalid alphabets; the length bucket
still counts them (`>100` 97 versus flag 95).

Constant regions: approved motif scanned = `t7_promoter_minimal`;
known-motif detections = 1 (5′); records actually trimmed = 0;
group-wise inference disabled.

Truncation regressions (display-normalised; do not drop records):

- A: `<1%` ending in `.` / `...` / `…` — PASS (0/509)
- B: median full length > 20 nt — PASS (median 75)
- C: ≤1 containing `...` or `…` anywhere — PASS (1/509)

Raw SHA-256 unchanged before and after S2. Deterministic rerun:
pass.

### Open questions carried forward

- CHECKPOINT-1 will adjudicate judgement-dependent sequence/trim
  issues during S3, including the internal-ellipsis record (which is
  also invalid/gapped), the six invalid-alphabet rows, the four
  clean ambiguous-IUPAC rows, and the unapplied T7 detection.
  S3 should honour `truncated_sequence` as a review reason even when
  `invalid_character` or `alignment_gaps` co-occur, and should not
  treat source `Type` as a parking rule.
- Group-wise constant-region inference remains disabled unless later
  evidence justifies a source-specific grouping mode.
- Target extraction and Category/Type reconciliation remain S4 /
  CHECKPOINT-2.
- Length filtering (9 below 20 nt; ~97 above 100 nt) is deferred to
  S3. The 20–25 and 90–100 bands should be reported, not silently
  dropped.

### Pipeline status

```text
RiboAptamer S0 complete
RiboAptamer S1 complete
RiboAptamer S2 complete
RiboAptamer S3 has not started
No RiboAptamer records are yet authorised for global S4
```

## 2026-08-31 — RiboAptamer S3 technical filtering and CHECKPOINT-1

**Stage:** Aim 2 / data curation / S3 technical eligibility and
CHECKPOINT-1 package preparation only. Human review decisions were not
applied. CHECKPOINT-1 is not closed. Constant-region proposals were not
applied. Target extraction and global S4 were not started.

### What was done

The 509 S2-normalised RiboAptamer records were classified with the
shared eligibility implementation under a source policy that defers
target classification, evidence scoring, and leakage exclusion. Length
eligibility used the actual computed `sequence_core` length (20–100 nt),
not S2 length QC flags. Every record received a closed-vocabulary
decision and, where excluded, a rejection-log entry. Structured
CHECKPOINT-1 review artefacts were generated and validated. The apply
stage was confirmed fail-closed on the blank review. No human decisions
were filled or applied.

### Decisions / implementation rules

- Source `Type` (`Proteins`, `Small molecules`, `Cells`, `Nucleic acids`)
  was not used for protein / non-protein parking. It remains sidecar
  review-context metadata for later S4 / CHECKPOINT-2.
- Empty `target_name_raw` does not reject. Canonical target type is not
  populated. Evidence / E4 and leakage matching were not applied.
- S3 eligibility was calculated from `len(sequence_core)`, not solely
  from S2 `core_above_max_length` / `core_below_min_length` flags. That
  is required because the S2 normaliser can return early on invalid
  alphabets before emitting a length QC flag.
- Judgement-dependent truncation / alignment / primer / library
  conditions take CHECKPOINT-1 review precedence when they overlap
  generic automatic reasons such as `invalid_alphabet`. A single
  canonical `rejection_reason` is emitted; overlaps are retained in
  `secondary_reasons`, `qc_flags`, and `checkpoint_review_reasons`.
- The known T7 `t7_promoter_minimal` motif remains an unapplied trim
  proposal. Detection confidence is the approved motif library.
  `sequence_core` is unchanged. Group-wise constant-region inference
  remains disabled; no medium-confidence consensus trims appeared.
- ssDNA parking remains zero under the experimental-RNA source
  contract. An unexpected DNA molecule type would hard-fail rather than
  be silently parked.
- Judgement-dependent records are provisional technical rejects and
  also enter CHECKPOINT-1. They are counted once in the reject route
  and once in the unique review-record count. They are not a separate
  disappearing bucket. Automatic-only rejects do not enter the active
  review queue.

### Inputs used

- `source_dataset = riboaptamer_full_2026-08`
- S2 canonical: `data/interim/normalised/riboaptamer_normalised.csv`
- S2 QC: `data/interim/normalised/riboaptamer_s2_qc.csv`
- S2 proposals: `data/interim/normalised/detected_constants_riboaptamer.csv`
- S1 sidecar: `data/interim/extracted/riboaptamer_source_metadata.csv`
- Registered raw file: `data/raw/riboaptamer/all_sequences_509_rows.csv`
- SHA-256:
  `721d8c5ea81476c1f371ef8bfa814743f364eaf004c0a6eda2aabd6dc5d9a9fd`
- Eligibility policy: `config/source_eligibility/riboaptamer.json`
- Review recommendations:
  `config/checkpoint_reviews/riboaptamer_checkpoint1_recommendations.json`

### Outputs produced

Ignored under `data/interim/checkpoints/riboaptamer_cp1/`:

- `riboaptamer_s3_canonical.csv` (byte-identical to S2)
- `riboaptamer_s3_decisions.csv`
- `riboaptamer_checkpoint1_review.csv`
- `riboaptamer_checkpoint1_local_detail.csv`
- `riboaptamer_checkpoint1_reason_counts.csv`
- `rejected_riboaptamer.csv`
- `riboaptamer_s3_parked_ssdna.csv` (header only)
- `riboaptamer_checkpoint1_summary.md`

Ignored under
`data/interim/checkpoints/riboaptamer_cp1/manual_review/`:

- `riboaptamer_checkpoint1_manual_review.csv`
- `riboaptamer_checkpoint1_manual_review_index.csv`
- `riboaptamer_checkpoint1_manual_review_summary.md`
- `riboaptamer_checkpoint1_constant_group_review.csv` (0 data rows)
- `riboaptamer_checkpoint1_bulk_audit_confirmation.csv`
- `README.md`
- `riboaptamer_checkpoint1_validation.md`

Tracked adapter, policy, schema note, tests, dispatcher changes, and
this log entry. Nothing under `data/` is tracked.

### Numbers

```text
rows in = 509
technical rejects = 112
parked ssDNA = 0
parked non-protein = 0
technically eligible RNA = 397
pending human review (unique records) = 85
509 = 112 rejected + 0 parked + 397 eligible
```

Primary rejection reasons (112 unique records; one reason each):

- `length_out_of_range`: 102
- `invalid_alphabet`: 5
- `ambiguous_bases`: 4
- `truncated_sequence`: 1
- `missing_sequence`: 0
- `mixed_T_and_U`: 0
- `primer_like`: 0
- `library_template`: 0
- `alignment_gaps` as primary: 0 (the one gapped record is SelB,
  primary `truncated_sequence`)

Condition tallies (a record may contribute to more than one):

- actual core `<20`: 9
- actual core `>100`: 97
- length-out-of-range condition: 106 (9 + 97)
- invalid-alphabet condition: 6
- ambiguous-bases condition: 4
- alignment-gaps condition: 1
- truncated-sequence condition: 1
- mixed T/U: 0
- missing sequence: 0

Overlaps (not additive):

- invalid alphabet AND length out of range: 2
  (`riboaptamer:251` length 120; `riboaptamer:252` length 124).
  These two lack S2 `core_above_max_length` because the normaliser
  returned early on invalid alphabet; S3 still length-checked them.
  Primary reason remains `invalid_alphabet`.
- truncated AND invalid alphabet: 1 (`riboaptamer:169`, SelB)
- truncated AND alignment gaps: 1 (same SelB record)
- ambiguous bases AND length out of range: 2
  (`riboaptamer:185` length 112; `riboaptamer:214` length 133)
- length-boundary records with another technical failure: 0
- trim-pushed length out of range: 0
- known-motif detections inside 20–100 nt: 1
- records with more than one reason: 59

The four length-condition records whose primary reason is not
`length_out_of_range` are the two invalid+long and two
ambiguous+long rows above (106 − 102 = 4).

CHECKPOINT-1 unique review records = 85, with no row duplication:

- judgement-dependent technical: 1 (`riboaptamer:169`, Sequence Name
  `Elongation factor SelB_clone 488`; primary `truncated_sequence`;
  secondary `alignment_gaps|invalid_alphabet`; core length 38)
- constant-region / known-motif proposal: 1 (`riboaptamer:382`,
  IL-17A / Apt21-2; unapplied 5′ `t7_promoter_minimal` length 17;
  core length 96, so also in the 90–100 review band; batch is
  `02_constant_region_proposal` by precedence)
- length-boundary retained: 54 condition rows (8 at 20–25 nt; 46 at
  90–100 nt). One of those 54 is the T7 record, so batch
  `03_length_boundary` contains 53 unique remaining boundary rows.
- random kept audit: 30 (seed 42; pool 343; shortfall 0)
- trim-induced length failures presented: 0
- group-consensus proposals: 0
- unique review = 1 + 1 + 53 + 30 = 85

Active review queue proposed decisions: 84 `proposed_accept` + 1
`proposed_reject` (SelB). Blank `manual_*` fields. Apply refused
with 85 unresolved decisions, 83 unconfirmed audit-only rows, 0
ready for application, 168 blocking issues.

Raw SHA-256 unchanged before and after S3. S3 canonical output is
byte-identical to S2. Deterministic rerun: pass. No trim applied.

### Open questions carried forward

CHECKPOINT-1 now requires Laura's manual review before the
RiboAptamer lane may progress. Decisions have not been made.

Scientific judgement that particularly needs review:

- SelB clone 488 (`riboaptamer:169`): internal ellipsis, alignment
  gap, and invalid-character context on a 38 nt core. Truncation /
  alignment review takes precedence over automatic
  `invalid_alphabet`.
- The unapplied T7 proposal on `riboaptamer:382` (96 nt core, also
  in the 90–100 eyeball band). Approve, override, reject, or defer;
  do not treat detection as an automatic trim or `primer_like`
  reject.
- The five automatic invalid-alphabet rejects that did not enter
  the active queue (native IDs 118, 251, 252, 307, 367), and the
  four automatic ambiguous-base rejects (185, 214, 259, 345).
- Length-boundary eyeballing of the remaining 53 retained 20–25 /
  90–100 records, plus the 30 random kept audit rows.

Group-wise constant-region inference remains disabled. Target
extraction, source `Type` protein / non-protein routing, evidence
scoring, and leakage exclusion remain S4 / CHECKPOINT-2.

### Pipeline status

```text
RiboAptamer S0 complete
RiboAptamer S1 complete
RiboAptamer S2 complete
RiboAptamer S3 provisional technical classification complete
RiboAptamer CHECKPOINT-1 prepared; awaiting Laura's review
No RiboAptamer records are yet authorised for global S4
```

## 2026-09-02 — RiboAptamer CHECKPOINT-1 review applied

**Stage:** Aim 2 / data curation / RiboAptamer CHECKPOINT-1 closure and
global-S4 handoff preparation only. Target extraction was not performed.
Global S4 was not run. Evidence scoring, protein/non-protein routing,
leakage exclusion, deduplication, clustering, balancing and partitioning
were not performed.

### What was done

Laura reviewed all 85 RiboAptamer CHECKPOINT-1 records. Human decisions
were validated fail-closed and applied through the existing apply path.
The truncated SelB source record was rejected because its missing
sequence could not be reconstructed from source evidence. The known 5′
T7 promoter on the IL-17A aptamer was approved for removal and the
resulting core was revalidated inside the 20–100 nt window. All other
reviewed sequences were retained. Human review also identified strong
and weaker patterns of unresolved terminal construct sequence on a
subset of records; these were retained without speculative trimming and
explicitly flagged. RiboAptamer is now closed through S3 and prepared
as one input to later corpus-wide S4 target normalisation.

Laura's as-saved Excel/MacRoman review CSV was preserved, then exported
to the canonical UTF-8 review path without changing decision semantics.
Informal `manual_trim_action=trim` on the T7 row was mapped to schema
`approve` of the existing known-motif proposal. Trim lengths were not
invented.

### Decisions and reasoning

- Truncated/gapped SelB record (`riboaptamer:169`) dropped rather than
  repaired. No corrected sequence was invented. Rejection reason remains
  `truncated_sequence`, with the human drop recorded in the rejection
  detail and notes.
- Known high-confidence 17-nt 5′ T7 promoter trim on `riboaptamer:382`
  approved. `sequence_raw` and `sequence_full` unchanged; `sequence_core`
  became 79 nt; `trim_status=t7_removed`; `trim_confidence=high`.
- No group-wise automatic constant inference was retroactively added.
- Strong terminal similarities observed during human review were flagged
  `constants_suspected_unresolved` from `manual_notes` prefixes, not
  converted into guessed trims. `trim_confidence` remains `n/a`.
- Weaker possible similarities were preserved as a separate warning
  class (`possible_constants_unresolved`) with
  `trim_status=no_constants_detected`.
- Preserving rather than guessing construct boundaries maintains
  auditability and reversibility.
- Clone-label chemistry such as `t44-OMe` (`riboaptamer:157`) was not
  inferred during this checkpoint. `chemistry=RNA` is unchanged.
- Target extraction, target-type routing, evidence and leakage remain
  deferred to S4.

### Inputs

- `source_dataset = riboaptamer_full_2026-08`
- Completed review (canonical UTF-8 path):
  `data/interim/checkpoints/riboaptamer_cp1/manual_review/riboaptamer_checkpoint1_manual_review.csv`
- Human as-saved copy:
  `data/interim/checkpoints/riboaptamer_cp1/manual_review/human_source/riboaptamer_checkpoint1_manual_review.as_saved.csv`
- Registered raw file: `data/raw/riboaptamer/all_sequences_509_rows.csv`
- SHA-256:
  `721d8c5ea81476c1f371ef8bfa814743f364eaf004c0a6eda2aabd6dc5d9a9fd`

### Outputs

Tracked:

- `config/checkpoint_reviews/riboaptamer_checkpoint1_resolutions.csv`
- `config/checkpoint_reviews/riboaptamer_checkpoint1_metadata.json`
- `config/global_s4_sources/riboaptamer.json`
- `docs/data_curation/riboaptamer_checkpoint1_review_schema.md`

Ignored under `data/`:

- `data/interim/checkpoints/riboaptamer_cp1/resolved/riboaptamer_checkpoint1_applied_canonical.csv`
- `data/interim/checkpoints/riboaptamer_cp1/resolved/riboaptamer_checkpoint1_applied_rejection.csv`
- `data/interim/checkpoints/riboaptamer_cp1/resolved/riboaptamer_checkpoint1_s4_authorised_ids.csv`
- `data/interim/checkpoints/riboaptamer_cp1/resolved/riboaptamer_checkpoint1_decision_audit.csv`
- `data/interim/checkpoints/riboaptamer_cp1/resolved/riboaptamer_checkpoint1_resolution_summary.md`
- `data/interim/global_s4_ready/riboaptamer_global_s4_input.csv`
- `data/interim/global_s4_ready/riboaptamer_global_s4_handoff_summary.md`

### Numbers

- Source records: 509
- Reviewed: 85 / 85 decisions consumed
- Human keep / edit / drop: 83 / 1 / 1
- Approved known T7 trims: 1
- Rejected/deferred known proposals: 0
- Group-consensus proposals: 0
- Strong unresolved-constant flags: 35
- Weak possible-constant flags: 3
- Speculative numeric trims outside approved proposals: 0
- Final retained (technically eligible / authorised for later S4): 397
- Final rejected: 112
- Parked ssDNA / non-protein: 0 / 0
- Unresolved review decisions: 0
- Blocking issues: 0
- Raw SHA-256 unchanged

### Open questions carried forward

- Target extraction/normalisation occurs later in global S4 /
  CHECKPOINT-2.
- Source Category/Type versus resolved target type must be reconciled
  then. Type is a target-class prior, not canonical truth.
- Modified-chemistry metadata such as clone labels containing `OMe` may
  require later source-level confirmation.
- Unresolved construct flags remain available for sensitivity analyses
  or future library-design research. They are human CHECKPOINT-1
  observations, not S2 consensus trims.

### Pipeline status

```text
RiboAptamer S0 complete
RiboAptamer S1 complete
RiboAptamer S2 complete
RiboAptamer S3 complete
RiboAptamer CHECKPOINT-1 closed
RiboAptamer prepared for later global S4 (not run)
```

## 2026-09-02 — AptaIndex registration and S1 extraction

**Stage:** Aim 2 / data curation / AptaIndex S0-S1.
AptaIndex S2, S3, CHECKPOINT-1, and global S4 were not started.

### What was done

The 22 July 2026 AptaIndex snapshot was registered as a restricted
Tier-1 source and frozen by SHA-256 and expected row count. A
source-specific S1 adapter then extracted every registered row into
the canonical corpus schema, with a complete source-metadata sidecar.
All 1050 source records and all 14 raw source columns were retained.
Deterministic row-based source IDs were used because `Title` is not
unique. Chemical-notation parsing, target/evidence/affinity
interpretation, eligibility filtering, parking, leakage checks, and
deduplication were deliberately deferred to their specified later
stages.

### Decisions made

- `native_id` uses the zero-padded 1-based source CSV data-row number
  (`0001`…`1050`) because `Title` is duplicated (21 duplicate keys
  affecting 48 rows). `record_id` is `aptaindex:{native_id}`.
  `Title` is preserved verbatim in the sidecar only.
- AptaIndex sequences are not parsed at S1. Chemical notation, token
  grammar, T→U conversion, alphabet classification, and molecule/chemistry
  inference are deferred to S2.
- Source `Type`, `Target Type`, and affinity columns remain sidecar-only
  metadata. They do not populate canonical `molecule_type`, `chemistry`,
  `target_type`, or affinity/evidence fields.
- `Target` is copied verbatim into `target_name_raw`, including blanks.
  Target normalisation and type classification remain a later global-S4
  task.
- `Reference` is copied verbatim into `publication`, matching the
  AptaBase `reference` / UTexas `Citation` S1 precedent. AptaIndex has
  no dedicated DOI/PMID columns, so `doi` and `pubmed_id` are left
  empty rather than adding a source-specific citation parser.
- `redistribution_status = restricted` under the Aptagen/AptaIndex
  Data Use Agreement. The DUA PDF is documentation only and is not
  registered as a corpus input.
- Written canonical and sidecar CSVs use `QUOTE_ALL` so embedded CR
  characters inside quoted source fields remain one logical row.

### Inputs used

- `source_dataset = aptaindex_export_2026-07-22`
- `data/raw/AptaIndex/aptamers-export-2026-07-22.csv`
- SHA-256:
  `912b8e554fa2bb2ed3a9e9bdf1cfbe4f757d8c7a00c401629e5bcb5e5c2877a8`
- 1050 logical rows; 14-column UTF-8 CSV with BOM
- Snapshot date: `2026-07-22`; tier `1`;
  `redistribution_status = restricted`

### Outputs produced

Ignored under `/data/`:

- `data/interim/registry/source_registry.csv` (operational S0 registry;
  12 validated registered files, exactly one `aptaindex` entry)
- `data/interim/extracted/aptaindex_extracted.csv` (1050 rows)
- `data/interim/extracted/aptaindex_source_metadata.csv` (1050 rows)
- `data/interim/extracted/aptaindex_s1_report.md`

Tracked scripts, tests and this log entry. Nothing under `data/` is
tracked.

### Numbers

- 1050 rows input
- 1050 extracted; 1050 unique `record_id`; 1050 unique `native_id`
- first native ID `0001`; last native ID `1050`
- 0 S1 rejections, parking, or filtering
- 14 raw metadata columns preserved in the sidecar; one-to-one join
  to canonical rows
- `sequence_raw` is text-equivalent to source `Sequence`; source order
  preserved
- known blank Sequence rows retained: 31
- known blank Target rows retained: 28
- nonempty publication (verbatim Reference): 1013; DOI/PMID: 0
- unique `Title` values: 1023; duplicate keys: 21; rows in those
  groups: 48
- source Type retained as sidecar diagnostics only: DNA 673, RNA 200,
  2′-F-RNA 71, Peptide 57, Chimeric 11, L-RNA 10, L-DNA 4, blank 24
- source raw hash unchanged before and after S0/S1:
  `912b8e554fa2bb2ed3a9e9bdf1cfbe4f757d8c7a00c401629e5bcb5e5c2877a8`
- S0: 12 registered, 12 validated; existing AptaBase inventory-override
  warnings only; DUA PDF not registered
- Deterministic S1 rerun: byte-identical canonical and sidecar CSVs

### Open questions carried forward

- S2 full-consumption chemical parser.
- L-RNA / L-DNA / Chimeric chemistry handling.
- Token/type disagreements and unparseable chemical notation.
- CHECKPOINT-1 later, including blank sequences/targets and conflicting
  targets for the same sequence.

### Pipeline status

```text
AptaIndex S0 complete
AptaIndex S1 complete
AptaIndex S2 has not started
No AptaIndex records are yet authorised for global S4
```

## 2026-09-02 — AptaIndex S2 chemical-notation parsing and normalisation

**Stage:** Aim 2 / data curation / AptaIndex S2.
AptaIndex S3, CHECKPOINT-1, and global S4 were not started.

### What was done

AptaIndex Sequence values are chemical notation, not nucleotide letters.
A source-specific full-consumption parser tokenises the entire string
before shared nucleotide normalisation. Raw notation remains in
`sequence_raw`. Unknown or incomplete syntax fails closed: no partial
nucleotide sequence is emitted. Source-declared peptide rows are
recognised as outside the nucleotide parser and are retained, not
excluded. `alphabet_as_reported = chemical_notation` records the
alphabet representation as supplied (governing-plan DECIDED value, not
a new scientific decision). Deterministic Type/token-supported
molecule/chemistry mappings were applied only where justified.
Unusual, modified, and mismatch cases remain flagged for
S3/CHECKPOINT-1. No target, evidence, affinity, leakage, parking, or
eligibility decisions were made.

### Parser

- Module: `scripts/data_preparation/adapters/aptaindex_sequence_parser.py`
- Adapter: `scripts/data_preparation/adapters/aptaindex_s2.py`
- Policy: `config/source_normalisation/aptaindex.json`
- Supported tokens: optional `L` + prefix `d`/`r`/`m`/`f`/`n` + base
  `A`/`C`/`G`/`T`/`U`/`I`; internucleotide linkages `p`/`s`; optional
  trailing terminal phosphate; 5′/3′ markers with ASCII `'`, Unicode
  right single quote, or prime, including quote-before-digit order;
  token-separating whitespace.
- Fail-closed: `/` prefix, thiol decoration, `Dsp`, `Xlk`, IUPAC `N`,
  brace labels, unprefixed stretches, omitted chemistry prefixes,
  3′→5′ terminal order, and other unconsumed material.
- Peptide `Type` is parser-not-applicable, not a parser bug.

### Schema

`chemical_notation` was added to the allowed `alphabet_as_reported`
vocabulary. Existing source values (`RNA`, `DNA_T`, `mixed_T_U`,
`ambiguous`, `invalid`, `missing`) are unchanged. Empty remains
allowed for source-declared peptide rows.

### Numbers (aggregate only)

- S1 rows 1050 → S2 rows 1050; records lost 0; unique IDs 1050
- Sequence missing 31; peptide 57; nonempty nucleic-acid 962
- Successful complete nucleic-acid parses 923
- Unsupported/unparseable nucleic-acid rows 39
- Preflight experimental split was 927 / 35. Production is four
  successes lower because 3′→5′ terminal order is treated as reverse
  orientation (fail closed; 3 rows) and because one further row that a
  slightly more permissive experimental grammar accepted is left for
  review. Lower coverage is accepted; the production parser is more
  conservative, not more permissive.
- Straightforward DNA (`Type` DNA, `d`-only, no L): 635; `ssDNA` / `DNA`;
  T retained
- Straightforward RNA (`Type` RNA, `r`-only, no L): 172; `RNA` / `RNA`
- Straightforward 2F-RNA (`Type` 2′-F-RNA, `f+r`): 65; `RNA` / `2F-RNA`
- L-RNA 9 parsed (+1 missing); L-DNA 4 parsed; Chimeric 10 parsed
  (+1 unsupported); not auto-resolved
- Type/token disagreements flagged: 28
- `alphabet_as_reported`: chemical_notation 962; missing 31; empty
  (peptide) 57
- `t_to_u_applied=true`: 1; mixed T+U retained: 5
- Length (parsed nucleic-acid): min/median/max 11 / 60 / 201;
  <20: 27; 20–25: 29; 90–100: 68; >100: 43. Not rejected at S2.
- Known-motif proposals 3 (unapplied); no group-wise inference;
  `sequence_core == sequence_full` for all rows; trim-to-short 0
- ssDNA rows remain in the canonical table (635); peptides remain (57)
- Deterministic rerun: byte-identical normalised, QC, review, proposals
- Raw SHA-256 unchanged:
  `912b8e554fa2bb2ed3a9e9bdf1cfbe4f757d8c7a00c401629e5bcb5e5c2877a8`

### Pipeline status

```text
AptaIndex S0 complete
AptaIndex S1 complete
AptaIndex S2 complete
AptaIndex S3 has not started
CHECKPOINT-1 has not been generated
No AptaIndex records are yet authorised for global S4
```

## 2026-09-02 — AptaIndex S3 technical classification and CHECKPOINT-1 preparation

**Stage:** Aim 2 / data curation / AptaIndex S3 + CHECKPOINT-1 preparation.
Human review decisions were not applied. CHECKPOINT-1 is not closed.
AptaIndex is not authorised for global S4. Global S4 was not run.

### What was done

The 1,050 S2-normalised AptaIndex records were classified with the
shared eligibility implementation under a source-specific policy.
Deterministic technical outcomes were applied where already justified.
ssDNA was parked, not rejected and not T→U converted. Source-declared
peptide aptamer/molecule records were excluded with an explicit
`non_nucleic_acid_molecule` reason rather than being forced through RNA
normalisation or parked as non-protein targets. Unsupported chemical
notation, Type/token disagreements, L-RNA, L-DNA, Chimeric constructs,
and mixed T/U after chemical parsing were routed to structured
CHECKPOINT-1 rather than flattened or silently labelled
`invalid_alphabet`. Length 20–100 nt was applied to successfully parsed
nucleotide `sequence_core`. Target canonicalisation, Target Type
protein/non-protein routing, evidence scoring, affinity normalisation,
leakage exclusion, and deduplication were not started. Structured
CHECKPOINT-1 review was prepared and validated as unresolved. The apply
stage was not run.

### Peptide-molecule vocabulary

The closed rejection vocabulary had no existing reason that meant
“source record is not a nucleic-acid aptamer”. The smallest coherent
extension is `non_nucleic_acid_molecule` (`proposed_reject`). This is
not `non_protein_target_parked`, `ssdna_parked`, or `invalid_alphabet`.
Peptide *targets* (`Target Type = Peptide` on a nucleic-acid molecule)
do not trigger it. Completed-source policies are unchanged.

### Technical routing

- Missing sequence (31): automatic `missing_sequence` reject; not queued
  for CHECKPOINT-1.
- Straightforward ssDNA: parked (`ssdna_parked`); T retained.
- Straightforward RNA and 2′-F-RNA: technically eligible at S3 if they
  pass shared alphabet/length rules.
- Peptide molecules (57): `non_nucleic_acid_molecule` reject.
- Length `<20` or `>100` on parsed nucleotide cores: `length_out_of_range`
  (70; 27 below 20 nt and 43 above 100 nt). No trim-pushed exception
  occurred (S2 applied 0 trims).
- Unsupported chemical notation (39): parked for chemistry review;
  parser failed closed; no partial nucleotide repair.
- L-RNA (9 parsed; 1 missing sequence), L-DNA (4), Chimeric (11), and
  Type/token disagreement (28): CHECKPOINT-1 judgement, not auto-mapped
  to ordinary RNA/ssDNA eligibility.
- Mixed T/U (5): shared `mixed_T_and_U` is collected after chemical
  parsing. All five are mixed-chemistry constructs, so chemistry-review
  parking takes precedence over automatic-only mixed-T/U rejection.
  They enter CHECKPOINT-1. No silent T↔U conversion.
- Blank raw Target (28): deferred; S3 `missing_target` rejects = 0.
  Current classified-row architecture (AptaDB interaction stream /
  UTexas / RiboAptamer) does not auto-reject blank `target_name_raw`
  at S3.
- Multi-target copies are not S3 conflicts. Grain is one
  `(sequence, target)` pair. Nonempty raw Sequence strings with >1
  Target: 24 (preflight ~25). Nonempty `sequence_core` values with >1
  Target after S2 parsing: 36. Neither count was treated as an error.

### Numbers (aggregate only)

`1050` = `199` technically eligible RNA/2F-RNA + `603` parked ssDNA +
`90` parked chemistry-review + `158` rejected.

Rejections by primary reason: `length_out_of_range` 70;
`non_nucleic_acid_molecule` 57; `missing_sequence` 31.

CHECKPOINT-1 active queue: 213 unique records (one row each).
Batches: judgement-dependent technical 90; constant-region proposal 3;
length-boundary 90; random kept audit 30 (seed 42, size 30).
Judgement-required 93; audit-only 120. Length-boundary reason flag 97
(7 overlap a higher-priority batch). Mixed T/U review 5. Automatic
rejects not requiring review: 158. Parked ssDNA: 603. Peptide
molecules: 57.

Source Type disposition: DNA 673 (603 parked ssDNA / 34 chemistry
review / 36 reject); RNA 200 (141 eligible / 26 chemistry review /
33 reject); 2′-F-RNA 71 (58 eligible / 6 chemistry review / 7 reject);
Peptide 57 (all `non_nucleic_acid_molecule`); Chimeric 11 (all
chemistry review); L-RNA 10 (9 chemistry review / 1 missing sequence);
L-DNA 4 (all chemistry review); blank 24 (all missing sequence).

Known-motif proposals 3, unapplied; group-wise inference remained
disabled; `sequence_core` unchanged.

### CHECKPOINT-1

Local review package (gitignored under `data/`):

- `data/interim/checkpoints/aptaindex_cp1/manual_review/aptaindex_checkpoint1_manual_review.csv`

Machine recommendations are populated. `manual_*` fields are blank.
The validator reports the package structurally readable and not closed
(213 unresolved decisions; not ready for application). Apply was not
run.

### Integrity / determinism

- Raw SHA-256 unchanged:
  `912b8e554fa2bb2ed3a9e9bdf1cfbe4f757d8c7a00c401629e5bcb5e5c2877a8`
- S1 extracted hash unchanged:
  `b74f6cc852ab342a6a28eafdbe97ee51cf325d5419c67ac6456d560753530552`
- S2 normalised / S3 canonical hash unchanged:
  `08004a065f02ce0d618c449f61198a94306e57e9af833a69fd0bc1097d56bbaa`
- S2 QC hash unchanged:
  `7d67d9ad31e1ceb0b103a0c8e7b31a482b246b029612becbd8a52e19f0cdbfe4`
- `data/raw/` unchanged
- Independent S3 + CHECKPOINT-1 reruns: byte-identical artefacts
- AptaIndex CSVs that may contain source CR characters use `QUOTE_ALL`

### Pipeline stop

```text
CHECKPOINT-1 package generated.
No human decisions applied.
No AptaIndex record is authorised for S4 yet.
The pipeline is stopped awaiting Laura CHECKPOINT-1 review.
```

## 2026-09-03 — AptaIndex S3 specification alignment (pre-review)

**Stage:** Aim 2 / data curation / AptaIndex specification repair only.
Human CHECKPOINT-1 decisions were not applied. Global S4 was not run.
AptaIndex is not authorised for S4.

### Closed rejection vocabulary

`non_nucleic_acid_molecule` was added to the governing closed
rejection-reason vocabulary in
`docs/data_curation/rna_aptamer_corpus_curation_plan.md`. Meaning:
source-declared non-nucleic-acid aptamer/molecule record, e.g. peptide
aptamer. This does not change the DECIDED exclusion of peptide
aptamers; it supplies the previously missing auditable reason.
Implemented AptaIndex S3 already used this reason (57 `Type = Peptide`
automatic rejects). Peptide *targets* on nucleotide aptamers remain
unaffected. The untracked duplicate plan was not edited.

### Multi-target counts (25 vs 24 vs 36)

Three diagnostics count the same 1,050 records under different equality
keys. None is record loss and none is an S2 parsing error.

- Preflight **25**: nonempty source Sequence after whitespace stripping
  and uppercasing; >1 distinct nonempty Target after stripping and
  lowercasing.
- S3 report **24**: exact nonempty raw `sequence_raw` / Sequence
  strings; >1 Target as stored (empty Target counts as a distinct
  value).
- Post-S2 **36**: nonempty parsed `sequence_core`; >1 raw Target as
  stored.

24 vs 25 is a key-definition difference, not a dropped row: two
exact-raw groups are multi-target only because of a blank Target or a
case/whitespace-only Target difference (excluded by the preflight
nonempty-lower rule), and three further groups become multi-target only
after whitespace is stripped from Sequence. 24 − 2 + 3 = 25.

24 vs 36 is parse collapse, not loss: 23 of the 24 exact-raw groups
remain multi-target on `sequence_core`; one unsupported-notation pair
has an empty core (parser failed closed; both records retained).
Thirteen additional cores become multi-target because two distinct
chemical-notation strings tokenise to the same nucleotide core with
different targets. 23 + 13 = 36. Empty cores = 127 (31 missing + 57
peptide + 39 unsupported). Raw = S2 = S3 = 1,050 unique records.

### Random-kept audit population

CHECKPOINT-1 batch 04 was already sampled from technically eligible
RNA/modified-RNA records pending later S4 (`proposed_accept`,
`technically_eligible_rna`, `primary_route=technically_eligible`,
`molecule_type=RNA`, not already queued). Pool 154, sample 30 (seed 42):
21 straightforward RNA + 9 straightforward 2′-F-RNA. It does not
include parked ssDNA, chemistry-review parks, peptide rejects, or other
automatic rejects. No resampling was performed.

### Pipeline stop

```text
CHECKPOINT-1 package generated.
No human decisions applied.
No AptaIndex record is authorised for S4 yet.
The pipeline is stopped awaiting Laura CHECKPOINT-1 review.
```

## 2026-09-03 — AptaIndex parser syntax refinement (pre-review)

**Stage:** Aim 2 / data curation / AptaIndex parser refinement, then
S2 → S3 → CHECKPOINT-1 regeneration.
Human CHECKPOINT-1 decisions were not applied. CHECKPOINT-1 is not
closed. AptaIndex is not authorised for global S4. Global S4 was not
run.

### What was done

The read-only CHECKPOINT-1 decision-support audit found that a subset
of AptaIndex parser failures were source-wide deterministic syntax
issues rather than record-specific scientific ambiguities. The
source-specific chemical parser was extended only for narrowly defined,
full-consumption syntax: uniform-family omitted-prefix inheritance,
allowlisted 5′ phosphate decorations (`{5'/Phosphate}` and `P-`),
allowlisted 5′ thiol-hexyl cap `SH-(CH2)6-`, and display hyphens that
separate already-valid nucleotide tokens. Reverse orientation, trailing
`i`, Nap-dU / `dN`, BNA, Hachimoji, gemcitabine, spacers, IUPAC
residues, generic brace stripping, generic unprefixed strings, and
case-folding of token bases were not added. No `manual_*` field was
populated. No real AptaIndex sequence was edited by hand.

S2, S3, and CHECKPOINT-1 were regenerated from the unchanged S1 input
before any human review. The previous review package contained no
human decisions and was safely superseded.

### Parser coverage

- S1/S2 rows 1050; missing 31; peptide 57; nonempty nucleic-acid 962
- Successful complete nucleic-acid parses 936 (previously 923)
- Unsupported/unparseable nucleic-acid rows 26 (previously 39)
- Newly parsed records 13, all by the explicit new syntax classes
- Inherited-prefix rows 10; terminal-phosphate decorations 2;
  thiol-hexyl cap 1; display-separator rows 1

### S3 reconciliation

`1050` = `207` technically eligible RNA/2F-RNA + `603` parked ssDNA +
`80` parked chemistry-review + `160` rejected.

Rejections by primary reason: `length_out_of_range` 71;
`non_nucleic_acid_molecule` 57; `missing_sequence` 31;
`mixed_T_and_U` 1.

### CHECKPOINT-1

Local review package (gitignored under `data/`):

- `data/interim/checkpoints/aptaindex_cp1/manual_review/aptaindex_checkpoint1_manual_review.csv`

Active queue 206 (previously 213). Batches: judgement-dependent
technical 81; constant-region proposal 3; length-boundary 92;
random kept audit 30. Judgement-required 84; audit-only 122.
Machine recommendations are populated. `manual_*` decision fields are
blank. Apply was not run.

Known-motif proposals remain 0187, 0276, and 0605, unapplied.

### Integrity / determinism

- Raw SHA-256 unchanged:
  `912b8e554fa2bb2ed3a9e9bdf1cfbe4f757d8c7a00c401629e5bcb5e5c2877a8`
- S1 extracted hash unchanged:
  `b74f6cc852ab342a6a28eafdbe97ee51cf325d5419c67ac6456d560753530552`
- S2/S3 canonical hash:
  `4a41c90c102d5dc5b9d9e469c6b636014d27c428868d1b3230b8fb2b1c4412da`
- `data/raw/` unchanged
- Independent S2, S3, and CHECKPOINT-1 reruns: byte-identical artefacts

### Pipeline stop

```text
CHECKPOINT-1 package regenerated.
No human decisions applied.
No AptaIndex record is authorised for S4 yet.
The pipeline is stopped awaiting Laura CHECKPOINT-1 review.
```

## 2026-09-07 — AptaIndex CHECKPOINT-1 apply adapter and dry-run (unapplied)

Human CHECKPOINT-1 review is complete: 206/206 resolved decisions
(42 edit / 22 drop / 142 keep; judgement 84; audit-only 122
`keep_current_route`). The fail-closed validator reports
`ready_for_application=206` and zero blockers.

An AptaIndex-specific CHECKPOINT-1 apply/dry-run adapter was added to
the shared dispatcher. AptaIndex `sequence_raw` remains chemical
notation and is never passed to generic nucleotide normalisation. Keep
preserves the pre-review S3 route. Drop uses shared `manual_reject`.
Edit reclassifies from the resolved human molecule/chemistry/sequence
state, including trim `reject` (no additional machine trim). Actual
apply is refused without `--dry-run`.

A production dry-run was run twice against the locked review
(`f8012c241972159d70e46b2727921da3c7694bb9abde267dc05eade781824a77`)
and was byte-identical. Sequence-free local report:

`data/interim/checkpoints/aptaindex_cp1/dry_run/aptaindex_checkpoint1_dry_run_report.md`

SHA-256:
`2ba6f16549f950e896a2c724b5b29f8e620488a9f38079d621a2c5fec50f7469`

Projected post-review 1050-row reconciliation:

`221` technically eligible + `611` parked ssDNA + `33` chemistry-review
+ `185` technical rejects (`22` manual + `4` after edit + `159`
remaining automatic) = `1050`.

All 142 keeps preserved route. All 22 drops became `manual_reject`.
Edits (42): 16 eligible, 9 ssDNA park, 13 chemistry-review, 4 technical
reject. 0187 remained 51 nt 2F-RNA with no second trim. 0605 became
58 nt RNA with no second trim. 0754 is a faithful 19-nt 2F-RNA and
routes as `length_out_of_range` under the current 20–100 rule. 0412,
0518, and 0519 received DNA identity; they did not park as ssDNA
because the corrected strings are not technically valid plain
nucleotides (and exceed 100 nt). `t_to_u_applied` records only whether
this apply step's nucleotide normaliser converted T→U. S4 fields were
not populated. Sequence corrections remain restricted/local.

Actual CHECKPOINT apply was **not** performed. No tracked resolutions
or closure metadata were written. CHECKPOINT-1 is not closed.
AptaIndex is not authorised for global S4. Global S4 was not run.
Raw / S1 / S2 / S3 hashes were unchanged.

### Pipeline stop

```text
CHECKPOINT-1 human review is complete.
AptaIndex apply/dry-run adapter implemented.
Dry-run complete. Actual apply was not run.
CHECKPOINT-1 is not closed.
S4 remains blocked.
```

## 2026-09-07 — AptaIndex CHECKPOINT-1 review applied

**Stage:** Aim 2 / data curation / AptaIndex S1–S3 + CHECKPOINT-1 closed.
Target normalisation was not performed. Target-type routing was not
performed. Evidence scoring was not performed. Affinity normalisation
was not performed. Leakage exclusion was not performed. Global S4 was
not run.

### What was done

AptaIndex was previously registered and extracted verbatim at S1.
Chemical notation was parsed deterministically at S2. Parser refinements
were completed before human review. S3 assigned technical eligibility
and local parking. Laura completed structured CHECKPOINT-1 review of
all 206 queued records, including literature-supported resolution of
chemistry/sequence ambiguities and audit-only confirmation of the
remaining keep-current-route rows.

The locked review package was re-validated fail-closed
(`unresolved_manual_decisions=0`, `audit_only_unconfirmed=0`,
`blocking_issues=0`, `ready_for_application=206`). A final production
dry-run was GO. Actual CHECKPOINT-1 apply was then run once through the
shared dispatcher, using the same `apply_reviewed_record` transformation
already exercised by the dry-run. Applied outputs were byte-identical to
the locked dry-run preview (0 semantic mismatches). Pre-review S2/S3
snapshots were not overwritten. Tracked sequence-free resolutions and
checkpoint metadata were written. A future global-S4 handoff config was
added following the RiboAptamer/AptaBase/UTexas closure convention.
Global S4 itself was not run.

`0754` is a faithful 19-nt RNA / 2F-RNA aptamer. The governing corpus
length range remains 20–100 nt, so it stays `length_out_of_range`. No
special length exception was introduced.

### Methods

- source registered and S1 extracted verbatim
- chemical notation parsed deterministically at S2
- parser refinements completed before human review
- S3 technical eligibility/routing
- structured CHECKPOINT-1 review
- literature-supported resolution of chemistry/sequence ambiguities
- audit-only confirmation
- apply dry-run
- actual apply
- dry-run/apply parity

### Decisions and reasoning

- Keep (142): pre-review technical route preserved.
- Drop (22): excluded through the established `manual_reject` route.
- Edit (42): reclassified from the resolved nucleotide/molecule/chemistry
  state under current S3 policy. Ordinary RNA edits are technically
  eligible. 2F-RNA edits are technically eligible unless length fails.
  2NH2-RNA, 2OMe-RNA, and mixed remain chemistry-review. ssDNA parks.
- Trim reject on 0187 and 0605: no additional machine 17-nt trim.
  Final lengths remain 51 nt (2F-RNA, eligible) and 58 nt (RNA,
  eligible).
- Corrected orientation DNA (0412, 0518, 0519) and plain/inverted-dT
  DNA (0492, 0753, 0960) park as ssDNA. No reverse-complement and no
  T→U were applied to those DNA corrections.
- Human molecule/chemistry overrides supersede stale S2 mapping/source
  classes. AptaIndex `sequence_raw` remains chemical notation and is
  never passed to generic nucleotide normalisation.

### Inputs

- Completed review:
  `data/interim/checkpoints/aptaindex_cp1/manual_review/aptaindex_checkpoint1_manual_review.csv`
- Review SHA-256:
  `843946d525a1bb269e9d5c399db30faa6a5b626beef8470eb6469e1529fc02fd`
- Bulk-confirmation SHA-256:
  `df65efea68aa787c51a19e90af29f07d19a63f6d8c6e16c6e85c154302a87457`
- Raw SHA-256:
  `912b8e554fa2bb2ed3a9e9bdf1cfbe4f757d8c7a00c401629e5bcb5e5c2877a8`
- S1 SHA-256:
  `b74f6cc852ab342a6a28eafdbe97ee51cf325d5419c67ac6456d560753530552`
- Pre-review S2/S3 canonical SHA-256:
  `4a41c90c102d5dc5b9d9e469c6b636014d27c428868d1b3230b8fb2b1c4412da`

### Outputs

Tracked:

- `config/checkpoint_reviews/aptaindex_checkpoint1_resolutions.csv`
- `config/checkpoint_reviews/aptaindex_checkpoint1_metadata.json`
- `config/global_s4_sources/aptaindex.json`

Ignored under `data/`:

- `data/interim/checkpoints/aptaindex_cp1/resolved/aptaindex_checkpoint1_applied_canonical.csv`
- `data/interim/checkpoints/aptaindex_cp1/resolved/aptaindex_checkpoint1_applied_routing.csv`
- `data/interim/checkpoints/aptaindex_cp1/resolved/aptaindex_checkpoint1_applied_eligible.csv`
- `data/interim/checkpoints/aptaindex_cp1/resolved/aptaindex_checkpoint1_applied_parked_ssdna.csv`
- `data/interim/checkpoints/aptaindex_cp1/resolved/aptaindex_checkpoint1_applied_parked_chemistry.csv`
- `data/interim/checkpoints/aptaindex_cp1/resolved/aptaindex_checkpoint1_applied_rejection.csv`
- `data/interim/checkpoints/aptaindex_cp1/resolved/aptaindex_checkpoint1_s4_authorised_ids.csv`
- `data/interim/checkpoints/aptaindex_cp1/resolved/aptaindex_checkpoint1_resolution_summary.md`

### Numbers

Source funnel after apply:

- Total: 1050
- Technically eligible (authorised for later global S4): 221
- Parked ssDNA: 614
- Chemistry-review/local park: 33
- Technical reject: 182

`221 + 614 + 33 + 182 = 1050`

Human decisions: 42 edit / 22 drop / 142 keep. Reviewed-206 post-state:
91 eligible, 59 parked ssDNA, 33 chemistry-review, 23 technical reject
(includes 22 manual rejects). Edit routes: 16 eligible, 12 ssDNA, 13
chemistry-review, 1 technical reject (`0754` length). Unresolved
decisions: 0. Blocking issues: 0. Dry-run/apply mismatches: 0.
Deterministic verification: pass. S4-forbidden fields remain empty.

`authorised_for_s4=true` on a record means RNA/2F-RNA technical
eligibility after AptaIndex CHECKPOINT-1. Source-level closure means
this source may proceed to later global-S4 preparation under those
routing rules. It does not authorise parked ssDNA, chemistry-review
parks, or rejects, and it does not mean target canonicalisation,
evidence, affinity, or leakage work has been done.

### Boundary

- Target normalisation deferred
- Target-type routing deferred
- Evidence scoring deferred
- Affinity normalisation deferred
- Leakage deferred
- The 25/38 multi-target phenomena remain untouched
- Global S4 not run

### Pipeline status

```text
AptaIndex S0 complete
AptaIndex S1 complete
AptaIndex S2 complete
AptaIndex S3 complete
AptaIndex CHECKPOINT-1 closed
AptaIndex global-S4 handoff config recorded; sequence-bearing input not yet materialised
```

## 2026-09-07 — ENA S0 registration and S1 extraction

**Stage:** Aim 2 / data curation / ENA S0 registration + S1 extraction only.
ENA S2 was not started. CHECKPOINT-1 was not opened. Global S4 was not run.

### What was done

The curated 679-row ENA review_v2 selected file was registered as the
authoritative Tier-1 source and frozen by SHA-256 and expected row
count. A source-specific S1 adapter then extracted every registered
row into the canonical corpus schema, with a complete one-to-one
source-metadata sidecar. All 679 source records and all 37 original
source columns were retained. Sequence normalisation, T→U conversion,
molecule/chemistry classification, trimming, target canonicalisation,
evidence scoring, leakage, deduplication, clustering, balancing, and
CHECKPOINT-1 were deliberately not performed.

### Why this file is authoritative

Inventory `recommended_S0_status` for this path is
`derived_output_not_raw_input`. That classification is correct as a
raw-tree label: the file is a reviewed selected lane, not the original
EMBL download. The governing curation plan already authorises a
registry-over-inventory override, so S0 emitted the existing generic
inventory warning and did not fail. The original EMBL download,
inspection/, candidates/, review/, other review_v2 CSVs, the processed
676-row export, and copied ENA data under `upload to chat gpt/` were
not registered and were not ingested.

### Decisions made

- `native_id` is source `review_unit_id` (populated and unique 679/679).
  `record_id` is `ena:{review_unit_id}`. Supporting `review_unit_ids`
  remain sidecar provenance. Three consolidated rows were not split.
- Reviewed source `sequence` is copied verbatim into `sequence_raw`.
  `sequence_original` is sidecar provenance only. No uppercase, no
  whitespace strip, no T→U, and no alphabet inspection were applied.
- Sequence and target correction fields remain sidecar provenance
  (8 sequence corrections; 1 target correction).
- Canonical `publication`, `doi`, `pubmed_id`, evidence, and affinity
  fields remain empty. Source evidence/title/reference fields stay in
  the sidecar for later global S4.
- Canonical `experiment_group_id` remains empty because the live S1
  schema forbids it. The primary source field is preserved in the
  sidecar for later S2 group inference. Supporting
  `experiment_group_ids` are stored separately and are not treated as
  the primary key (25 primary groups vs 28 expanded supporting IDs).
- Blank source `near_duplicate_family_id` means singleton, not unknown.
  312 blank rows received deterministic sidecar IDs
  `ena_singleton_{review_unit_id}` with family size 1. 367 nonblank
  source family values were left unchanged, including one
  pipe-delimited consolidated family value. Canonical
  `near_duplicate_family_id` remains empty at S1.
- The 679-versus-676 processed-export difference remains deferred to
  ENA CHECKPOINT-1.

### Inputs used

- `source_dataset = ena_selected_v2_2026-08`
- `data/raw/ENA/review_v2/ena_selected_after_manual_review.csv`
- SHA-256:
  `d1069b96c2bcf5eba02d7d7907b3bcc33e041bf80aac6345e7295715e45c5a35`
- 679 logical rows; 37-column UTF-8 CSV with BOM
- Snapshot date: `2026-08-04`; tier `1`;
  `redistribution_status = unknown`

### Outputs produced

Ignored under `/data/`:

- `data/interim/registry/source_registry.csv` (operational S0 registry;
  13 validated registered files, exactly one `ena` entry)
- `data/interim/extracted/ena_extracted.csv` (679 rows)
- `data/interim/extracted/ena_source_metadata.csv` (679 rows)
- `data/interim/extracted/ena_s1_report.md`

Tracked scripts, tests and this log entry. Nothing under `data/` is
tracked.

### Numbers

- 679 rows input
- 679 extracted; 679 unique `record_id`; 679 unique `native_id`
- 0 S1 rejections, parking, filtering, or deduplication
- 37 raw metadata columns preserved in the sidecar, plus three derived
  family-provenance fields; one-to-one join to canonical rows
- `sequence_raw` is text-equivalent to source `sequence`; source order
  preserved
- `target_name_raw` is text-equivalent to source `target`
- populated primary experiment groups: 679; distinct primary groups: 25
- original blank family IDs: 312; materialised unique singleton IDs: 312
- original nonblank family IDs unchanged: 367
- source sequence_corrected_applied=1: 8; target_corrected_applied=1: 1
- consolidated source rows retained unsplit: 3
- canonical publication/DOI/PMID: 0
- source raw hash unchanged before and after S0/S1:
  `d1069b96c2bcf5eba02d7d7907b3bcc33e041bf80aac6345e7295715e45c5a35`
- S0: 13 registered, 13 validated; warnings=3 (two AptaBase inventory
  overrides plus the expected ENA generic `derived_output_not_raw_input`
  warning). No shared registry machinery was added.
- Deterministic S1 rerun: byte-identical canonical, sidecar, and report

### Open questions carried forward

- ENA S2 shared sequence normalisation, including T→U for the five
  current T-alphabet reviewed sequences.
- S2 consumption of sidecar primary `experiment_group_id` for
  group-wise constant-region inference.
- 679-versus-676 CHECKPOINT-1 reconciliation.

### Pipeline status

```text
ENA S0 complete
ENA S1 complete
ENA S2 has not started
No ENA CHECKPOINT-1 decision has been made
No ENA records are yet authorised for global S4
```

## 2026-09-07 — ENA S2 sequence normalisation and constant-region proposals

**Stage:** Aim 2 / data curation / ENA S2 sequence normalisation, QC, and
constant-region proposals only. S1 was not reopened. S3 was not started.
CHECKPOINT-1 was not generated. No human trim decisions were made. No
inferred ENA constant-region trims were applied. Global S4 was not run.

### What was done

ENA S1 canonical `sequence_raw` was passed through the shared sequence
normaliser under a fixed RNA source contract. Alphabet classification,
molecule-aware T→U, known-motif detection, and group-wise constant-region
inference used the live shared machinery. ENA-specific code is a thin
adapter plus dispatcher registration. Legacy ENA normalisation/finalisation
scripts were not imported or executed.

### Source-contract decision

The authoritative 679-row ENA lane represents RNA aptamers. Therefore at
S2, `molecule_type=RNA` and `chemistry=RNA` for all 679 records. Molecule
type is not inferred from T/U alphabet. T alphabet does not mean ssDNA.
T→U on a T-encoded reviewed sequence is computational transcription of an
RNA record.

### Numbers

- 679 S1 rows in; 679 S2 canonical rows out; 679 unique `record_id`
- same row order; zero drops; zero parks; zero deduplication
- `sequence_raw` unchanged 679/679; `target_name_raw` unchanged 679/679
- `molecule_type=RNA`: 679; `chemistry=RNA`: 679
- alphabet: `RNA` 674, `DNA_T` 5; mixed T/U 0; ambiguous 0; invalid 0
- T→U applied: 5 (exactly the DNA_T rows); those `sequence_full` values
  contain U rather than T
- live shared vocabulary used (`RNA` / `DNA_T`, not `RNA_U`)
- the shared normaliser also flags those 5 rows `t_in_reported_rna` as
  transcription provenance; T→U still succeeded
- display transformations: `t_to_u` on 5 rows only
- `sequence_core == sequence_full` for 679/679; applied trims = 0
- length (from S2 sequences, not source `sequence_length`):
  missing 0; `<20` 4; `20-25` 22; `26-89` 643; `90-100` 10; `>100` 0
  (min/median/max 17 / 64 / 100). Source length mismatches: 0
- sidecar sequence_corrected_applied=1 preserved: 8
- primary `experiment_group_id` groups: 25 (679/679 populated)
- supporting `experiment_group_ids` expanded (diagnostic only): 28
- inference used the 25 primary groups, not the 28-ID expansion
- groups meeting live minimum size 5: 14; skipped for size: 11
- records in eligible groups: 654
- group-consensus proposals: 5 (3 five-prime, 2 three-prime);
  medium confidence; applied=false; 92 associated records
- shared known-motif detections: 0
- source promoter/template concern rows: 8 (all also T7-flagged)
- overlap source concern and shared known motif: 0
- source concern without shared motif: 8
- family provenance unchanged: 312 original-blank/materialised
  singletons; 367 nonblank source family rows
- review-candidate rows: 104
  (group-consensus 92; source promoter/template 8; T-encoded RNA
  transcription flag 5; core below min length 4; some overlap)
- exact post-S2 `sequence_full` values with count>1: 3 values / 6
  records (diagnostic only — no deduplication performed)
- no target canonicalisation, UniProt, evidence scoring, affinity,
  leakage, clustering, or partitioning
- 679-versus-676 reconciliation not performed

### Outputs produced

Ignored under `/data/`:

- `data/interim/normalised/ena_normalised.csv`
- `data/interim/normalised/ena_s2_qc.csv`
- `data/interim/normalised/ena_s2_review_candidates.csv`
- `data/interim/normalised/ena_constant_region_proposals.csv`
- `data/interim/normalised/ena_constant_region_membership.csv`
- `data/interim/normalised/ena_s2_report.md`

Tracked: ENA S2 policy, thin adapter, S2 dispatcher registration,
synthetic tests, and this log entry. `config/constant_regions.yaml`
was not modified. Nothing under `data/` is tracked.

### Integrity

- Raw SHA-256 unchanged:
  `d1069b96c2bcf5eba02d7d7907b3bcc33e041bf80aac6345e7295715e45c5a35`
- S1 canonical hash unchanged:
  `3d823f4007cde419e2c5cb4a71230c8febaefbeb237cf54e5888740c02578fac`
- S1 sidecar hash unchanged:
  `977cf57be81152e2c5307db68928ccdfc9f66aa2c0a20f8999eab4c9ba78acad`
- Deterministic rerun: byte-identical normalised, QC, review,
  proposal, and membership CSVs
- `git ls-files data` remains empty
- newly tracked artefacts contain no real ENA aptamer sequences

### Open questions carried forward

- ENA S3 eligibility plus structured CHECKPOINT-1 preparation,
  including the 679-versus-676 reconciliation (3 exact
  `sequence_full` pair collapses after T→U are diagnostic only at S2).
- Human review of 5 unapplied group-consensus proposals and 8
  source promoter/template flags that the shared T7 detector did
  not match one-for-one.

### Pipeline status

```text
ENA S0 complete
ENA S1 complete
ENA S2 complete
ENA S3 has not started
No ENA CHECKPOINT-1 decision has been made
No ENA records are yet authorised for global S4
```

## 2026-09-07 — ENA S3 technical eligibility and CHECKPOINT-1 preparation

**Stage:** Aim 2 / data curation / ENA S3 provisional technical eligibility
and structured CHECKPOINT-1 preparation only. S2 was not scientifically
regenerated. No human CHECKPOINT-1 decision was populated. No constant-region
trim was applied. CHECKPOINT-1 was not applied or closed. Global S4 was not
prepared or run. ENA was not deduplicated.

### 679-row reconciliation

- S3 input = 679; S3 route total = 679; unique `record_id` = 679
- `679` = `575` proposed_accept + `100` proposed_park + `4` proposed_reject
- S3 canonical scientific fields unchanged from S2 (byte-identical SHA-256
  `4e88f44a07cfee89014eae17d68b90f70acc23d6a6792f29c8ee8f622e2aa8ca`)
- applied trims remain 0; `sequence_core == sequence_full` for 679/679
- molecule_type RNA = 679; chemistry RNA = 679; T→U provenance unchanged (5)

### Proposed routes

- proposed_accept / `technically_eligible_rna`: 575
- proposed_park / `trim_construct_unresolved`: 100
  - 92 unresolved medium-confidence group-consensus records
  - 8 source promoter/template concerns with no group-consensus coverage
- proposed_reject / `length_out_of_range`: 4 (all `<20` nt; none `>100`)
- ssDNA parks: 0; chemistry parks: 0; non-RNA parks: 0

### Secondary / review reasons

- `constant_region_proposal`: 92
- `medium_confidence_trim`: 92
- `lower_length_boundary`: 22
- `upper_length_boundary`: 10
- `random_accept_audit`: 30

### Four below-minimum records

Machine route: `proposed_reject` / `length_out_of_range`. Included in
CHECKPOINT-1 batch `01_judgement_dependent_technical` with recommendation
`confirm_current_length_reject`. No source-specific `<20` exception was
introduced.

### Five group-consensus rules / 92 affected records

One structured rule row per inferred proposal (5), not 92 independent trim
decisions. Hypothetical trim was simulated only; nothing was applied.
Machine recommendation for all five: `needs_source_review`.

- 5′ / group 23 / support 1 / motif length 23 / affected 23 /
  hypothetical `<20` 0 / hypothetical `>40%` 21 / conflict 0 /
  source-promoter overlap 0
- 3′ / group 23 / support 0.913043 / motif length 20 / affected 23 /
  hypothetical `<20` 0 / hypothetical `>40%` 21 / conflict 0 /
  source-promoter overlap 0
- 5′ / group 15 / support 1 / motif length 23 / affected 15 /
  hypothetical `<20` 0 / hypothetical `>40%` 12 / conflict 0 /
  source-promoter overlap 0
- 3′ / group 15 / support 0.8 / motif length 20 / affected 15 /
  hypothetical `<20` 0 / hypothetical `>40%` 12 / conflict 0 /
  source-promoter overlap 0
- 5′ / group 54 / support 0.851852 / motif length 12 / affected 54 /
  hypothetical `<20` 0 / hypothetical `>40%` 0 / conflict 0 /
  source-promoter overlap 0

`>40%` combined trim is a group-level human-review trigger, not an automatic
rejection. Record-level exceptions: 13, all `non_terminal_match` (members
that do not carry an exact terminal motif). Human fields blank.

S2 proposal/membership group IDs are namespaced
(`ena:experiment_group:experiment_<hash>`) while QC uses the unprefixed
source key. S3 joins both forms plus membership `record_id`; S2 was not
reopened.

### Eight source promoter/template concerns

Shared known-motif detector remains 0 matches. None of the 8 overlap a
group-consensus rule, so each is a record-level CHECKPOINT item in batch
`01` under `proposed_park` / `trim_construct_unresolved`. Recommendation:
needs human construct review; no automatic trim. No trim action populated.

### Five T-transcribed RNA audit records

All five remain experimental RNA after S2 T→U. They are not DNA/ssDNA/chemistry
parks. All five also carry a source promoter/template flag, so the higher-precedence
construct park applies; they still appear in CHECKPOINT-1. Three participate
in the legacy 679→676 collapse.

### Legacy 679→676 reconciliation

Mechanical reproduction (not a hardcoded preflight): 3 collapse groups,
6 source records, all still present in the 679-row S3 set. The old 676-row
finaliser collapsed three pairs after T→U, target alias, and exact
`(sequence, target)` consolidation. It did not reject three bad records.
Machine recommendation: `retain_both_through_checkpoint_and_defer_exact_dedup`.
Human fields blank. No pair was collapsed.

Post-S2 exact `sequence_full` diagnostic: 3 duplicated values / 6 records;
label `diagnostic only — no deduplication performed`. Equality is not an
S3 route.

### Length-boundary and random-kept audits

- 20–25 nt: 22 proposed_accept (eyeball only)
- 90–100 nt: 10 proposed_accept (eyeball only)
- random kept audit: 30 selected from pool 540, seed 42, shortfall 0

### Review queues

- record-level active queue: 77 (12 judgement, 3 transcription/reconciliation,
  32 length-boundary, 30 random kept)
- group-only parks are not duplicated as individual trim decisions (602
  records have no record-level review row)
- constant-group review rows: 5
- reconciliation review rows: 3
- human decision fields blank; `ready_for_application = 0`
- validator fail-closed (exit 2): unresolved decisions > 0; apply would fail

### Deferred

No S4 fields populated. No target/evidence/leakage work. No exact
deduplication. Near-duplicate families unused for routing.

### Integrity

- raw SHA-256 unchanged:
  `d1069b96c2bcf5eba02d7d7907b3bcc33e041bf80aac6345e7295715e45c5a35`
- S1 canonical SHA-256 unchanged:
  `3d823f4007cde419e2c5cb4a71230c8febaefbeb237cf54e5888740c02578fac`
- S1 sidecar SHA-256 unchanged:
  `977cf57be81152e2c5307db68928ccdfc9f66aa2c0a20f8999eab4c9ba78acad`
- S2 canonical and proposal artefacts unchanged
- S3 + CHECKPOINT preparation rerun byte-identical
- `git ls-files data` remains empty
- newly tracked artefacts contain no real ENA aptamer sequences

### Pipeline status

```text
ENA S0 complete
ENA S1 complete
ENA S2 complete
ENA S3 technical eligibility complete
ENA CHECKPOINT-1 prepared, blank, unapplied, fail-closed
Global S4 has not been run
```

## 2026-09-07 — ENA S3 technical eligibility and CHECKPOINT-1 preparation

**Stage:** Aim 2 / data curation / ENA S3 technical sequence/molecule/construct
eligibility and structured CHECKPOINT-1 **preparation only**. S2 was not
reopened. Human CHECKPOINT-1 decisions were not populated. No constant-region
trim was applied. CHECKPOINT-1 was not applied or closed. Exact deduplication
was not performed. Global S4 was not started.

### What was done

All 679 accepted S2 records received exactly one provisional S3 route.
Canonical scientific fields remain byte-identical to S2. Routing, rejection
logging, construct parking, and CHECKPOINT artefacts live in sidecars under
ignored `data/interim/checkpoints/ena_cp1/`.

ENA uses the shared eligibility framework with
`unresolved_trim_blocks_eligibility=true`. Precedence: missing sequence →
mixed T/U → ambiguous bases → alignment gaps → invalid alphabet →
length out of range → unresolved construct/trim → technically eligible RNA.
ssDNA / non-RNA / chemistry parking paths were not used. Source target type,
evidence, leakage, clustering, balancing, and partitioning were not run.

S2 QC `experiment_group_id` values (`experiment_<hash>`) and S2 proposal
group ids (`ena:experiment_group:experiment_<hash>`) were joined in S3
without rewriting S2. Membership record_ids were used as a second attachment
path.

### S3 row reconciliation

```text
S3 input = 679
S3 route total = 679
unique record_id = 679
679 = 575 proposed_accept + 100 proposed_park + 4 proposed_reject
```

Primary reasons:

```text
technically_eligible_rna = 575
trim_construct_unresolved = 100
length_out_of_range = 4
```

Secondary reasons:

```text
constant_region_proposal = 92
medium_confidence_trim = 92
lower_length_boundary = 22
upper_length_boundary = 10
random_accept_audit = 30
```

Canonical invariants: `sequence_raw` / `sequence_full` / `sequence_core`
unchanged; applied trims = 0; `sequence_core == sequence_full` = 679;
molecule_type RNA = 679; chemistry RNA = 679; T→U provenance unchanged (5).
S4 fields remain empty. No ssDNA park. No chemistry park. No non-RNA park.

### Four below-minimum records

Four records with core length <20 nt were `proposed_reject` /
`length_out_of_range` under the already-decided 20–100 nt corpus rule.
They are in CHECKPOINT-1 batch 01 with recommendation
`confirm_current_length_reject`. No source-specific <20 exception was
introduced. No >100 records exist.

### Five T-transcribed RNA records

All five remain experimental RNA. They were not reclassified as DNA and were
not parked for `t_in_reported_rna`. All five also carry a source
promoter/template concern, so the higher-precedence unresolved-construct
park applies. They appear in CHECKPOINT-1 batch 01 with the construct-review
recommendation; transcription is a secondary audit reason, not an exclusion
reason.

### Constant-region group review

Five unapplied medium-confidence group-consensus proposals (3 five-prime,
2 three-prime) affect 92 unique S3 records (130 membership rows because two
groups have both ends). Those 92 are `proposed_park` /
`trim_construct_unresolved` and are reviewed as **five rule rows**, not 92
independent trim decisions.

Sequence-free rule summary:

```text
rule A  five_prime   group=23  support=1        motif_len=23  affected=23
        hypo<20=0  hypo>40%=21  conflict=0  promoter_overlap=0
        hard_invalid=0  rec=needs_source_review

rule B  three_prime  group=23  support=0.913043 motif_len=20  affected=23
        hypo<20=0  hypo>40%=21  conflict=0  promoter_overlap=0
        hard_invalid=2  rec=needs_source_review

rule C  five_prime   group=15  support=1        motif_len=23  affected=15
        hypo<20=0  hypo>40%=12  conflict=0  promoter_overlap=0
        hard_invalid=0  rec=needs_source_review

rule D  three_prime  group=15  support=0.8      motif_len=20  affected=15
        hypo<20=0  hypo>40%=12  conflict=0  promoter_overlap=0
        hard_invalid=3  rec=needs_source_review

rule E  five_prime   group=54  support=0.851852 motif_len=12  affected=54
        hypo<20=0  hypo>40%=0   conflict=0  promoter_overlap=0
        hard_invalid=8  rec=needs_source_review
```

Hypothetical >40% combined trim is a human-review trigger on the rule row,
not an automatic rejection and not a per-record exception when it is the
majority group pattern. No trim was applied. Motif strings remain only in
ignored `data/` membership/local-detail files.

Record-level constant-region exceptions: 13, all `non_terminal_match`
(2 + 3 + 8 on the three-prime / large five-prime rules). Human fields blank.

### Eight source promoter/template concerns

S2 retained 8 source promoter/template/T7 concern rows. Shared known-motif
detections remain 0. None overlap a group-consensus proposal, so all 8 are
record-level CHECKPOINT items in batch 01 (`proposed_park` /
`trim_construct_unresolved`). Machine recommendation:
`needs human construct review; no automatic trim`. No trim action was
populated. Five of the eight are the T-transcribed RNA records above.

### Length-boundary and random-kept audits

```text
20–25 nt = 22  (proposed_accept; eyeball only)
90–100 nt = 10 (proposed_accept; eyeball only)
random kept = 30 of pool 540, seed 42, shortfall 0
```

Random pool = otherwise-clean proposed accepts not already in a higher
review batch, not group-covered, and not source-promoter.

### Exact duplicate diagnostic and 679-versus-676

Post-S2 exact `sequence_full` collisions: 3 duplicated values / 6 records.
Label: `diagnostic only — no deduplication performed`. Sequence equality
did not become an S3 route. All six records remain.

Mechanical legacy-finaliser reproduction found 3 collapse groups (pairs).
The old 676-row file collapsed three pairs after T→U, target alias, and
exact `(sequence,target)` consolidation; it did not reject three bad
records. Unified S2 `sequence_full` is identical within each pair. One pair
has differing raw target strings. All three pairs have prior manual
sequence/target correction provenance and a source promoter/template flag
on at least one member. Machine recommendation:
`retain_both_through_checkpoint_and_defer_exact_dedup`. Human fields blank.
No pair was collapsed. Denominator remains 679.

Of the six members: 3 are parked (source-promoter overlap, including the
three T-encoded members) and 3 are proposed accepts in batch 02.

### Record-level review queue

```text
active record-level rows = 77
no record-level review = 602  (includes 92 group-only parks)
01_judgement_dependent_technical = 12  (4 length reject + 8 promoter)
02_transcription_or_reconciliation_audit = 3  (clean collapse-pair members)
03_length_boundary = 32
04_random_kept_audit = 30
constant-group review rows = 5
reconciliation review rows = 3
record-level constant exceptions = 13
```

A record appears once in the primary per-record queue. Group-rule and
reconciliation tables are separate CHECKPOINT components.

### Human decisions and fail-closed validation

All human decision fields are blank. Machine recommendations are populated
and do not count as decisions. Validator:

```text
unresolved_manual_decisions = 77
unresolved_constant_rules = 5
unresolved_exceptions = 13
unresolved_reconciliation_groups = 3
ready_for_application = 0
CHECKPOINT-1 is not closed
apply would fail closed
```

This is SUCCESS for preparation. Decisions were not filled to force a pass.
Apply was not run.

### Tests, determinism, integrity

Synthetic-only ENA S3/CHECKPOINT tests plus completed-source S3/CHECKPOINT
regressions passed. Production S3 `--check-deterministic-rerun` and
CHECKPOINT prepare were each run twice with byte-identical outputs.

- Raw SHA-256 unchanged:
  `d1069b96c2bcf5eba02d7d7907b3bcc33e041bf80aac6345e7295715e45c5a35`
- S1 canonical unchanged:
  `3d823f4007cde419e2c5cb4a71230c8febaefbeb237cf54e5888740c02578fac`
- S1 sidecar unchanged:
  `977cf57be81152e2c5307db68928ccdfc9f66aa2c0a20f8999eab4c9ba78acad`
- S2 canonical unchanged:
  `4e88f44a07cfee89014eae17d68b90f70acc23d6a6792f29c8ee8f622e2aa8ca`
- S2 QC / proposal / membership artefacts unchanged
- S3 canonical SHA-256 equals S2
- `git ls-files data` remains empty
- newly tracked Milestone 3 artefacts contain no real ENA aptamer sequences
  or inferred motifs

### Unexpected notes

- S2 QC grouping keys and proposal `experiment_group_id` values used
  different namespaces; S3 joins them. S2 was not rewritten.
- All 5 T-encoded records are among the 8 source promoter/template
  concerns, so they park rather than `proposed_accept`.
- Two groups have both 5′ and 3′ proposals; hypothetical combined trim
  exceeds 40% for the matching majority. Flagged on the rule, not auto-rejected.

### Pipeline status

```text
ENA S0 complete
ENA S1 complete
ENA S2 complete
ENA S3 technical eligibility complete
ENA CHECKPOINT-1 package prepared; human fields blank; unapplied
No ENA record is authorised for S4
Global S4 has not been run
```

## 2026-09-07 — ENA CHECKPOINT-1 application dry-run — unapplied

Human CHECKPOINT-1 review is complete and fail-closed validated:
77/77 record decisions, 5 group rules, 13 exceptions, 3
reconciliation groups, and 62/62 audit-only bulk confirmation.
Zero unresolved decisions or blockers. Frozen completed-review
hashes matched. Pristine reconstruction (written only under ignored
`dry_run/pristine_reconstruction/`) differed from the completed
package only in allowed human fields.

An ENA-specific CHECKPOINT-1 apply/dry-run adapter was added to the
shared dispatcher. `manual_decision=keep` retains the record, applies
reviewed trim/no-trim resolution, then recomputes technical
eligibility; it does not force `technically_eligible`. Real apply
without `--dry-run` is refused. No `resolved/` outputs, tracked
resolutions, or closure metadata were written.

Reviewed Korean cassette policy (ALPPL2 and CTHRC1): one 23-nt 5′
removal and one 19-nt 3′ removal from `sequence_full`. Combined >40%
trim is human-approved. Five Korean 3′ exceptions received exactly
one 19-nt 3′ trim (no double application). NGF 12-nt group trim was
rejected: 54 records remain untrimmed. Eight promoter/template
concerns were resolved as keep-untrimmed (reject trim, not reject
record). Four `<20 nt` records remain confirmed `length_out_of_range`
technical rejects. Three legacy-collapse pairs were consumed as
`retain_both`; no deduplication.

Production dry-run was run twice against the frozen review and was
byte-identical. Sequence-free local report:

`data/interim/checkpoints/ena_cp1/dry_run/ena_checkpoint1_dry_run_report.md`

SHA-256:
`cb39c4c1e9b69c4c62b14a56ab37cc72c342098088811b0136afd79b3a6cff36`

Projected post-review 679-row reconciliation (derived, not targeted):

`675` technically eligible + `0` parked + `4` technical rejects
(`length_out_of_range`) = `679`.

Trim preview: 38 records trimmed (0 five-only, 0 three-only, 38
both-end); 38 `large_trim_human_approved`; 0 exact-terminal /
overlap / core `<20` / unreviewed >40% failures. Korean cassette
cores min/median/max = 38 / 39.0 / 40. Transitions: 575 accept→accept,
100 park→accept, 4 reject→reject. All 679 source identities remain.
S4/forbidden fields remain empty. CHECKPOINT-1 remains
`pending_checkpoint_1_review`.

Actual CHECKPOINT apply was **not** performed. CHECKPOINT-1 is not
closed. ENA is not authorised for global S4. Global S4 was not run.
Raw / S1 / S2 / S3 / completed-review hashes were unchanged.
`git ls-files data` remains empty.

### Pipeline stop

```text
CHECKPOINT-1 human review is complete.
ENA apply/dry-run adapter implemented.
Dry-run complete. Actual apply was not run.
CHECKPOINT-1 is not closed.
S4 remains blocked.
```

## 2026-09-07 — ENA CHECKPOINT-1 applied and closed

Frozen human CHECKPOINT-1 review was applied through the same
`apply_ena_reviewed_record` / `simulate_ena_checkpoint1_application`
path used by the accepted dry-run. Authoritative outputs were written
under ignored `data/interim/checkpoints/ena_cp1/resolved/`. Sequence-free
tracked closure records were written to
`config/checkpoint_reviews/ena_checkpoint1_resolutions.csv` and
`config/checkpoint_reviews/ena_checkpoint1_metadata.json`.

Dry-run/apply parity: all nine scientific CSV payloads are
byte-identical to the accepted dry-run freeze (zero semantic
mismatches). Deterministic verification rerun matched the
authoritative applied files. Pre-review raw / S1 / S2 / S3 and frozen
human-review hashes were unchanged.

Derived 679-row reconciliation: `675` technically eligible + `0`
parked + `4` technical rejects = `679`. `authorised_for_s4=true` for
the 675 technically eligible records only. That flag means allowed to
enter a future global-S4 source handoff; it does not mean target
canonicalised, protein confirmed, evidence threshold passed, leakage
cleared, deduplicated, clustered, balanced, or partitioned.

Korean cassette: 38 records received one 23-nt 5′ trim and one 19-nt
3′ trim. Resulting cores min/median/max = 38 / 39 / 40
(distribution 38×5, 39×29, 40×4). All 38 combined >40% trims remain
`large_trim_human_approved`. Guard-rail failures = 0. Five Korean
exception records received 23+19 exactly once.

NGF 12-nt group trim remains rejected: 54 records retained untrimmed
and technically eligible. Eight promoter/template records remain
untrimmed and eligible; historical source concern survives on S2 QC
and applied routing; the reviewed construct blocker is resolved.
Four `<20 nt` records remain `technical_reject` /
`length_out_of_range` with `authorised_for_s4=false`. Three
679→676 legacy-collapse groups (`retain_both`) keep all six member
records. No deduplication.

S4 target/evidence/leakage/cluster/partition fields remain empty.
`config/global_s4_sources/ena.json` was not created. Global S4 was
not run. CHECKPOINT-1 is closed.

### Pipeline status

```text
ENA S0 complete
ENA S1 complete
ENA S2 complete
ENA S3 technical eligibility complete
ENA CHECKPOINT-1 applied and closed
675 records technically authorised for a future global-S4 handoff
ENA global-S4 handoff has not been prepared
Global S4 has not been run
```

## 2026-09-07 — ENA prepared for future global S4

ENA S1–S3 are complete and CHECKPOINT-1 is closed. The 675
CHECKPOINT-authorised records were materialised as a reviewed applied
subset for a future corpus-wide global S4 input. Global S4 was not
run.

`authorised_for_s4=true` / inclusion in this handoff means only
technically eligible after ENA sequence/molecule/construct review and
prepared as an input to the future corpus-wide global S4 stage. It
does not mean protein target confirmed, target canonicalised, UniProt
resolved, evidence threshold passed, leakage cleared, final corpus
included, deduplicated, clustered, balanced, or partitioned.

Handoff denominator: 675 authorised, 0 parked, 4
`length_out_of_range` rejects excluded. The 675-row reviewed applied
canonical subset was joined to ENA source sidecar target, evidence,
experiment-group, and near-duplicate-family provenance. Canonical S4
target/evidence/leakage/cluster/partition fields remain empty. Three
exact sequence duplicate pairs remain as six source records
(diagnostic only — no deduplication performed). Target
canonicalisation, evidence scoring, leakage exclusion, deduplication,
and clustering were not performed.

Authorised-lane provenance (derived): 310 materialised singletons;
365 source-nonblank family rows; 25 distinct primary experiment
groups. Korean cassette trimmed records = 38 (both-end; core
min/median/max 38/39/40; `large_trim_human_approved` = 38). Five
T-transcribed records remain authorised with DNA_T/T→U provenance.
NGF no-trim (54) and promoter no-trim (8) records remain full/core
equal.

Tracked: `config/global_s4_sources/ena.json`, a minimal reusable
extension of `prepare_global_s4_source.py` for colliding sidecar
extras, and tests. Ignored: `ena_global_s4_input.csv` (675 rows) and
the sequence-free handoff summary. Deterministic rerun was
byte-identical. Raw / S1 / S2 / S3 / CHECKPOINT-1 / applied /
human-review hashes were unchanged. `git ls-files data` remains
empty.

### Pipeline status

```text
ENA S0 complete
ENA S1 complete
ENA S2 complete
ENA S3 technical eligibility complete
ENA CHECKPOINT-1 applied and closed
ENA future global-S4 handoff prepared (675 records)
Global S4 has not been run
```

## 2026-09-08 — AptamerBase registration and S1 verbatim extraction

**Stage:** Aim 2 / data curation / AptamerBase S0-S1.
AptamerBase S2, S3, CHECKPOINT-1, and global S4 were not started.

### What was done

The authoritative AptamerBase CSV was registered as a Tier-1 source
and frozen by SHA-256 and expected row count. A source-specific S1
adapter then extracted every physical source row into the canonical
corpus schema, with a complete source-metadata sidecar. All 2128
physical rows and all 14 raw source columns were retained.
Deterministic physical-row native IDs were used because source
Freebase `id` is not unique. Molecule classification, T→U conversion,
target extraction from `label`, evidence scoring, structure/PDB
mapping, eligibility filtering, parking, leakage checks, and
deduplication were deliberately deferred.

### Decisions made

- AptamerBase is a flattened Freebase/RDF-style export. One physical
  CSV row is not necessarily one biological aptamer.
- All 2128 physical rows are preserved through S1. Duplicate complete
  rows, repeated Freebase IDs, repeated sequences, parent/minimal-aptamer
  expansions, structure-topic rows, blank sequences, and textual `n/a`
  sequences are retained. No biological deduplication occurred. This is
  not an S1 defect.
- `native_id` uses the zero-padded 1-based source CSV data-row number
  (`0001`…`2128`). `record_id` is `aptamerbase:{native_id}`. The source
  Freebase `id` is preserved verbatim in the sidecar only.
- Source object types are retained in the sidecar (aptamer topics and
  secondary/predicted-structure topics). Source `type` is not treated
  as eligibility.
- Source `label` is a composite Freebase export label, not a documented
  raw-target column. It is sidecar-only; `target_name_raw` is left empty.
- Minimal-aptamer relationship fields (`has_minimal_aptamer`,
  `is_minimal_aptamer_of`) are retained verbatim in the sidecar and are
  not mapped into canonical clustering fields.
- Structure/evidence metadata is retained but uninterpreted. Boolean
  and URI-valued source fields do not populate canonical PDB or
  evidence fields.
- Molecule type and chemistry are deferred to S2. No T→U conversion,
  sequence normalisation, or constant trimming was performed.
- `paper.pdf` is documentation only and is not a registered corpus input.
- `source_dataset = aptamerbase_export_2026-06-24` follows the inventory
  last-modified date rather than inventing an August extraction date.

### Inputs used

- `source_dataset = aptamerbase_export_2026-06-24`
- `data/raw/aptamerbase/aptamerbase_aptamers.csv`
- SHA-256:
  `40b329551b225a29ee2c656cf6b59b98ff686a981968b856685cdc7c222a784c`
- 2128 logical rows; 14-column UTF-8 CSV, no BOM
- Snapshot date: `2026-06-24`; tier `1`;
  `redistribution_status = unknown`

### Outputs produced

Ignored under `/data/`:

- `data/interim/registry/source_registry.csv` (operational S0 registry;
  14 validated registered files, exactly one `aptamerbase` entry)
- `data/interim/extracted/aptamerbase_extracted.csv` (2128 rows)
- `data/interim/extracted/aptamerbase_source_metadata.csv` (2128 rows)
- `data/interim/extracted/aptamerbase_s1_report.md`

Tracked scripts, tests and this log entry. Nothing under `data/` is
tracked.

### Numbers

- 2128 rows input
- 2128 extracted; 2128 unique `record_id`; 2128 unique `native_id`
- first native ID `0001`; last native ID `2128`
- 0 S1 rejections, parking, or filtering
- 14 raw metadata columns preserved in the sidecar; one-to-one join
  to canonical rows
- `sequence_raw` is text-equivalent to source `sequence`; source order
  preserved
- empty sequence rows retained: 179
- exact textual `n/a` sequence rows retained: 4
- other nonempty sequence rows: 1945
- `target_name_raw` populated: 0; publication / DOI / PMID: 0
- unique Freebase IDs: 1868; duplicated ID groups: 66; rows in those
  groups: 326
- exact duplicate complete-row groups: 2; rows in those groups: 6;
  excess: 4
- source type retained as sidecar diagnostics only: aptamer 2056,
  nucleic-acid secondary structure 69, predicted secondary structure 3
- nonempty `has_minimal_aptamer`: 273; nonempty
  `is_minimal_aptamer_of`: 266
- source raw hash unchanged before and after S0/S1:
  `40b329551b225a29ee2c656cf6b59b98ff686a981968b856685cdc7c222a784c`
- S0: 13 registered files before, 14 after; 14 validated; existing
  AptaBase and ENA inventory-override warnings only; AptamerBase
  inventory SHA and row count agree; `paper.pdf` not registered
- Deterministic S1 rerun: byte-identical canonical and sidecar CSVs

### Open questions carried forward

- S2 molecule-type and chemistry investigation, including mixed
  alphabets, textual `n/a`, blank sequences, and structure-topic rows.
- Later target extraction from sidecar `label` (not at S1).
- Later interpretation of minimal-aptamer relationships, structure
  metadata, and evidence flags.
- CHECKPOINT-1 later. Global S4 later.

### Pipeline status

```text
AptamerBase S0 complete
AptamerBase S1 complete
AptamerBase S2 has not started
No AptamerBase record is authorised for global S4
```

## 2026-09-08 — AptamerBase source contract enriched with Freebase RDF metadata

**Stage:** Aim 2 / data curation / AptamerBase supporting-source registration.
This is not S2. AptamerBase S1 was not rerun. Global S4 was not started.

### Why this was needed

The frozen 14-column AptamerBase CSV is the sole 2128-row S1 spine, but it
does not carry experimental RNA/DNA molecule typing. Alphabet inspection
cannot supply that identity. The original authors' Freebase RDF extract
does contain source-native type predicates and is therefore registered as
supporting provenance for a later S2 join.

### What was done

- Validated the local gzip RDF already present under `data/raw/` (read-only;
  not downloaded or rewritten).
- Registered it as a second file of the same logical `source_dataset`
  `aptamerbase_export_2026-06-24`, following the AptaDB multi-file pattern.
- Extended generic S0 validation to stream `.nt.gz` files, hash the
  compressed bytes, and count decompressed N-Triples physical statements
  without writing an uncompressed copy.
- Extended generic inventory inspection for `.nt.gz` as supporting RDF
  metadata, not as additional aptamer records.
- S1 now distinguishes files by basename: CSV remains the row spine;
  RDF is supporting-only. S1 outputs were not regenerated.

### Inputs used

- CSV spine: `data/raw/aptamerbase/aptamerbase_aptamers.csv`
  SHA-256 `40b329551b225a29ee2c656cf6b59b98ff686a981968b856685cdc7c222a784c`
  (2128 rows; unchanged)
- Supporting RDF: `data/raw/aptamerbase/aptamerbase.freebase.extract.nt.gz`
  SHA-256 `3ab9340ee1fcb6a0910532a6e8d4cf5cc62579c3b21d85355c48d473e372006c`
  (270507 decompressed N-Triples statements)
- Upstream: `micheldumontier/aptamerbase@e7a3eb43d24504fd5a7b6c3e470ab242bc471b3a`

### Decisions made

- CSV remains the sole 2128-row generating spine.
- RDF is supporting-only, joined later by Freebase ID; it does not create
  additional corpus records.
- Experimental molecule typing exists in the RDF and is reserved for S2.
- S1 remains frozen (2128 canonical rows; 2128 sidecar rows).
- Experiments/interactions remain deferred to global S4.

### Numbers

- Registered files: 14 before this milestone, 15 after
- AptamerBase registry rows: 2 files, 1 `source_dataset`
- S0 validated 15/15; existing AptaBase and ENA inventory-override warnings
  only; no AptamerBase inventory discrepancy after refresh
- Inventory substantive files: 203 previous → 206 current
  - intentional new file: supporting RDF
  - previously uninventoried local PDFs under `rbms_paper/` (2)
  - unchanged: 203; modified: 0; removed: 0
  - transient artefacts ignored on disk: 11
- S1 canonical and sidecar hashes unchanged

### Pipeline status

```text
AptamerBase CSV S0 registration complete.
AptamerBase supporting RDF registration complete.
AptamerBase S1 remains complete and frozen.
AptamerBase S2 has not started.
No AptamerBase record is authorised for global S4.
```

## 2026-09-08 — AptamerBase S2 RDF-supported sequence normalisation

**Stage:** Aim 2 / data curation / AptamerBase S2.
AptamerBase S3, CHECKPOINT-1, and global S4 were not started.

### What was done

Supporting RDF type statements were joined to the frozen S1 sidecar by
Freebase ID and used as the source-native RNA/DNA identity. Shared
display-level sequence normalisation, a closed chemistry allowlist, and
known-motif detection (proposals only) were applied to every physical
S1 row. No record was dropped, parked, or collapsed.

### Decisions made

- Experimental molecule type is RDF RNA/DNA typing, not the printed
  alphabet. Sequence alphabet does not establish or erase molecule type.
- Source-confirmed RNA printed in T is computationally transcribed to U
  with `t_to_u_applied` provenance. RDF DNA printed in U remains ssDNA
  with a contradiction flag and is not auto-repaired.
- Unresolved source IDs remain `molecule_type=unknown` rather than
  alphabet-inferred.
- Secondary-structure and predicted-secondary-structure objects are
  retained but not treated as aptamers (`molecule_type=unknown`,
  `chemistry=unknown`), even if RDF also carries an incidental RNA type.
- Chemistry is conservative. Only unmodified RNA/DNA backbones,
  terminal/conjugate-only metadata, and a closed 2′-fluoro-pyrimidine
  RNA class are assigned automatically. Spiegelmer/L-RNA keeps RDF RNA
  identity but chemistry `unknown` with a review flag. Unusual
  modifications are retained for review.
- Group-wise constant-region inference is disabled. Known-motif
  detections are S2 proposals only; no trim was applied
  (`sequence_core == sequence_full`).
- Target, interaction, publication, evidence, affinity, PDB, leakage,
  filtering, dedup, clustering, CHECKPOINT-1, and global S4 remain
  deferred. Every S1 row is retained.

### Inputs used

- Frozen S1 canonical:
  `data/interim/extracted/aptamerbase_extracted.csv`
  SHA-256 `0bb0282033ba0561b2c8d8de1358ae6e5a4e8fa47bfb640c56dc87b177552896`
- Frozen S1 sidecar:
  `data/interim/extracted/aptamerbase_source_metadata.csv`
  SHA-256 `47a49f7495648bb11105a77eee9cbcfeabeb7b7b05f357dc433d3edb779f41b7`
- CSV spine SHA-256
  `40b329551b225a29ee2c656cf6b59b98ff686a981968b856685cdc7c222a784c`
- Supporting RDF SHA-256
  `3ab9340ee1fcb6a0910532a6e8d4cf5cc62579c3b21d85355c48d473e372006c`
  (270507 N-Triples statements; 1868/1868 S1 Freebase IDs joined)

### Outputs produced

Ignored under `/data/`:

- `data/interim/normalised/aptamerbase_normalised.csv` (2128 rows)
- `data/interim/normalised/aptamerbase_s2_qc.csv`
- `data/interim/normalised/aptamerbase_s2_review_candidates.csv`
- `data/interim/normalised/detected_constants_aptamerbase.csv`
- `data/interim/normalised/aptamerbase_s2_report.md`

Tracked policy, S2 adapter, RDF helper, dispatcher registration, tests,
and this log entry. Nothing under `data/` is tracked.

### Numbers

- Physical rows in/out: 2128 / 2128; unique `record_id`: 2128
- Object grain: aptamer 2056; secondary-structure 69;
  predicted-secondary-structure 3
- Molecule type rows: RNA 980; ssDNA 896; unknown 252
- Molecule type unique IDs: RNA 917; ssDNA 836; unknown 115
- Missing after shared textual-null processing: 183
- T→U applied: 122 (121 RNA × clean DNA_T; 1 RNA × ambiguous with T)
- RDF DNA × U alphabet conflict: 15 rows / 15 IDs
- Chemistry: RNA 855; DNA 892; 2F-RNA 105; unknown 276
- Known-motif detections / proposals: 7; applied trims: 0
- Deferred S4 fields empty on all rows

### Pipeline status

```text
AptamerBase S0 complete.
AptamerBase S1 complete and frozen.
AptamerBase S2 complete.
AptamerBase S3 has not started.
CHECKPOINT-1 has not been generated.
No AptamerBase record is authorised for global S4.
```

## 2026-09-08 — AptamerBase S3 technical eligibility and CHECKPOINT-1 preparation

**Stage:** Aim 2 / data curation / AptamerBase S3 + CHECKPOINT-1 prepare.
Human CHECKPOINT-1 decisions were not populated. Apply was not run.
Global S4 was not prepared or started.

### What was done

Every physical S2 row received exactly one provisional primary route.
RDF-flattened secondary-structure and predicted-secondary-structure
objects were rejected as `non_aptamer_source_object`. Missing aptamer
sequences were mechanically rejected. Technically surviving ssDNA was
parked. RDF DNA × U alphabet contradictions remained ssDNA parks but
entered CHECKPOINT-1. Aptamer-topic unresolved molecule rows were
parked for review. Clean RNA and 2′-F-RNA were technically eligible.
Unsupported RNA chemistry was parked for chemistry review. Mixed /
ambiguous / invalid / gapped source notation was provisionally rejected
but placed in active review. Known-motif proposals were not applied.
A structured CHECKPOINT-1 package was written with blank human fields
and fail-closed validation (`ready_for_application = 0`).

### Decisions made

- Structure-topic source objects are not biological aptamer records.
  They do not require human review to establish that fact.
- Missing sequence is a mechanical reject, not a park.
- Judgement-dependent sequence syntax remains a proposed technical
  reject, but AptamerBase notation may be recoverable so those rows
  enter CHECKPOINT-1. Sequences are not auto-repaired. RDF molecule
  type is not erased.
- Length uses actual `len(sequence_core)`, 20–100 nt, with no
  source-specific exception.
- Length-boundary eyeballing (20–25 and 90–100) applies only to
  proposed technical accepts, not ordinary ssDNA parks.
- Ordinary clean ssDNA is parked and not reviewed. DNA×U conflicts
  stay ssDNA (`t_to_u_applied=false`) with `needs_source_review`.
- No U-only or T-only fallback for unknown molecule type.
- Chemistry does not replace molecule identity. Eligible RNA chemistry
  is RNA or 2F-RNA. Spiegelmer/L-RNA is not ordinary RNA chemistry.
- Known motifs remain unapplied. Group-wise constant inference stays
  disabled. Unresolved construct blocks eligibility.
- Target, interactions, evidence, affinity, PDB, leakage, dedup,
  clustering, and global S4 remain deferred. `target_name_raw` stays
  empty by design.

### Inputs used

- S2 canonical SHA-256
  `69bcfb97592255bc0d70727991bd68d7bf5dc18f1c47db532b182461ba6d81f8`
- Frozen S1 canonical SHA-256
  `0bb0282033ba0561b2c8d8de1358ae6e5a4e8fa47bfb640c56dc87b177552896`
- Frozen S1 sidecar SHA-256
  `47a49f7495648bb11105a77eee9cbcfeabeb7b7b05f357dc433d3edb779f41b7`
- CSV spine SHA-256
  `40b329551b225a29ee2c656cf6b59b98ff686a981968b856685cdc7c222a784c`
- Supporting RDF SHA-256
  `3ab9340ee1fcb6a0910532a6e8d4cf5cc62579c3b21d85355c48d473e372006c`

Raw, S1, and S2 hashes were unchanged. S3 canonical is byte-identical
to S2. Applied trims remain 0.

### Outputs produced

Ignored under `/data/`:

- `data/interim/checkpoints/aptamerbase_cp1/aptamerbase_s3_canonical.csv`
- `data/interim/checkpoints/aptamerbase_cp1/aptamerbase_s3_decisions.csv`
- `data/interim/checkpoints/aptamerbase_cp1/rejected_aptamerbase.csv`
- parked ssDNA / molecule / chemistry / construct sidecars
- CHECKPOINT-1 review, local-detail, reason-counts, and summary
- `data/interim/checkpoints/aptamerbase_cp1/manual_review/`

Tracked eligibility policy, checkpoint recommendation/metadata JSON,
S3 and CHECKPOINT adapters, dispatcher wiring, tests, plan vocabulary,
and this log entry. Nothing under `data/` is tracked.

### Numbers

- Physical rows: 2128 / 2128; unique `record_id`: 2128
- Object grain unchanged: aptamer 2056; secondary-structure 69;
  predicted-secondary-structure 3
- Primary routes: technical/source reject 407; parked ssDNA 817;
  parked molecule unknown 70; parked chemistry review 16;
  parked unresolved construct 6; technically eligible 812
- Eligible chemistry split: RNA 712; 2F-RNA 100
- Non-aptamer source objects: 72 (primary)
- Missing-sequence condition: 183 (71 structure / 112 aptamer-topic)
- RDF DNA × U conflicts in CHECKPOINT-1: 15; still ssDNA
- Known-motif proposals: 7; applied trims: 0
- Active CHECKPOINT-1 records: 291; human decisions: 0;
  `ready_for_application = 0`
- Random-kept audit: 30 from pool 720; shortfall 0

### Pipeline status

```text
AptamerBase S0 complete.
AptamerBase S1 complete and frozen.
AptamerBase S2 complete.
AptamerBase S3 technical classification complete.
AptamerBase CHECKPOINT-1 prepared with human decisions blank.
No AptamerBase record is authorised for global S4.
Global S4 has not been run.
```

## 2026-09-08 — AptamerBase CHECKPOINT-1 decision-support audit (Milestone 4A)

**Stage:** Aim 2 / data curation / AptamerBase CHECKPOINT-1 decision-support
audit and audit-only bulk-confirmation preparation.
Human CHECKPOINT-1 decisions were not entered. CHECKPOINT-1 is not
closed. Apply was not run. AptamerBase is not authorised for global S4.
Global S4 was not run. S2/S3 scientific routes were not altered.

### What was done

The AptaDB/AptaIndex bulk-audit architecture was reused for AptamerBase:
122 length-boundary / random-kept rows are `bulk_audit_eligible=true` with
machine recommendation `keep_current_route`. A blank bulk-confirmation
artefact was emitted. Confirm remains empty. The validator is fail-closed.

A decision-support audit was added under ignored
`data/interim/checkpoints/aptamerbase_cp1/manual_review/audit/`. Freebase-ID
grouping is review support only: physical rows and `record_id` values are
unchanged. PMID-like label prefixes are audit-only bibliographic hints.
Canonical `pubmed_id` / `target_name_raw` were not populated.

### Integrity

- Raw CSV SHA-256
  `40b329551b225a29ee2c656cf6b59b98ff686a981968b856685cdc7c222a784c`
- Supporting RDF SHA-256
  `3ab9340ee1fcb6a0910532a6e8d4cf5cc62579c3b21d85355c48d473e372006c`
- Frozen S1 canonical SHA-256
  `0bb0282033ba0561b2c8d8de1358ae6e5a4e8fa47bfb640c56dc87b177552896`
- Frozen S1 sidecar SHA-256
  `47a49f7495648bb11105a77eee9cbcfeabeb7b7b05f357dc433d3edb779f41b7`
- S2 canonical SHA-256
  `69bcfb97592255bc0d70727991bd68d7bf5dc18f1c47db532b182461ba6d81f8`
- S2 QC SHA-256
  `58e895c8e63fac7c14e8b094da9f6276083902d091020dd4e5abf1da2b67b1fd`
- S3 canonical SHA-256 (byte-identical to S2)
  `69bcfb97592255bc0d70727991bd68d7bf5dc18f1c47db532b182461ba6d81f8`
- S3 decisions SHA-256
  `f76127b32e930981e40a1ee15bbd08083fc798c9d0215f33b89c0c8ef026e866`
- CHECKPOINT-1 review SHA-256
  `1423f852cbe1b9eb194acef929f581ce7dddc6a9a4ed564404b26b43dba7dc61`
- CHECKPOINT-1 local-detail SHA-256
  `e16dba912e37453baad35ea6d3cad4ba32cb5104be45d5e0a3de1eb4fb4b0ecb`

Human decision fields remain blank. `ready_for_application = 0`.

### Workload

- Active CHECKPOINT-1 records: 291
- Judgement-required physical rows: 169 → 151 unique Freebase source-ID
  review units
- Audit-only: 122 (92 length-boundary + 30 frozen random-kept, seed 42)
- Safe scientifically identical multi-record Freebase groups: 19
  (0 unsafe). Thirteen of those groups are among the 169 judgement rows.

### Fail-closed validation

```text
unresolved_judgement_required=169
audit_only_rows=122
audit_only_unconfirmed=122
bulk_audit_confirmed=false
ready_for_application=0
checkpoint_closed=false
```

### Pipeline status

```text
AptamerBase CHECKPOINT-1 decision-support audit complete.
Human decisions remain blank.
CHECKPOINT-1 remains open and unapplied.
No AptamerBase record is authorised for global S4.
Global S4 has not been run.
```

## 2026-09-09 — AptamerBase CHECKPOINT-1 human review entered and dry-run

Laura approved the 169 judgement-required CHECKPOINT-1 decisions
(119 edit / 50 drop / 0 keep). The 122 audit-only rows (92
length-boundary + 30 frozen random-kept) were bulk-confirmed
(`confirm=true`); individual audit `manual_decision` fields remain
blank. Fail-closed validation: `ready_for_application=291`, zero
blockers.

Notation: 50 unrecoverable/malformed/Spiegelmer rows were dropped;
11 source-supported sequence repairs were edited (2 biotin display
tokens retained as ssDNA; 9 publication-supported T→U RNA
corrections, of which five 4'-thioRNA cases remain chemistry-parked).
Fifteen RDF DNA × U conflicts were overridden to RNA (14 eligible;
1152 chemistry-parked as 4'-thioRNA). Seventy molecule-unknown rows
were resolved from publication groups (39 ssDNA/DNA parked; 31 RNA,
including one cationic-uridine chemistry park). Sixteen primary
chemistry parks were edited (2 pentynyl-dU → ssDNA park; 7 × 2F-RNA;
2 × 2NH2-RNA; 5 × mixed). Seven known-motif T7 5′-17 nt trims were
approved (0922 length reject → eligible; six construct parks →
eligible). No 2OMe-RNA records were present in this reviewed set.

AptamerBase S3/apply now treats reviewed `2NH2-RNA`, `2OMe-RNA`, and
`mixed` as technically eligible for this source only. Reviewed
`unknown` chemistry is not inferred back to RNA.

A production dry-run was run twice against the completed review
(`55000f2ea3cf51e5236c4ba9e44bc2e73d87050cc9c0d1c0e7afe5d995098ae1`)
and was byte-identical. Sequence-free local report:

`data/interim/checkpoints/aptamerbase_cp1/dry_run/aptamerbase_checkpoint1_dry_run_report.md`

SHA-256:
`f589fd95317b33266e5b63e465c59e3b11aaa727bd0a5f707474b3c9695bc3af`

Projected post-review 2128-row reconciliation:

`881` technically eligible + `845` parked ssDNA + `0` molecule-unresolved
+ `7` chemistry-review + `0` construct + `395` technical rejects
= `2128`.

Chemistry parks remain 0410 / 0473 / 0474 / 1152 / 1160 / 1161 / 1162.
S4 fields were not populated. Raw / S1 / S2 / S3 hashes were unchanged.

Actual CHECKPOINT apply was **not** performed. No tracked resolutions
or closure metadata were written. CHECKPOINT-1 remains open and
unapplied. No AptamerBase record is authorised for global S4. Global
S4 was not run.

### Pipeline stop

```text
AptamerBase CHECKPOINT-1 human review is complete.
AptamerBase CHECKPOINT-1 dry-run is complete.
Actual CHECKPOINT-1 apply has NOT been run.
CHECKPOINT-1 remains open and unapplied.
No AptamerBase record is yet authorised for global S4.
Global S4 has not been run.
```

## 2026-09-09 — AptamerBase CHECKPOINT-1 applied and closed

Laura authorised actual CHECKPOINT-1 application after accepting the
completed review and production dry-run. The shared AptamerBase apply
adapter consumed the frozen completed review through the same
transformation used by the accepted dry-run. CHECKPOINT-1 is closed.
Global S4 was not started. No global-S4 handoff was prepared.

`authorised_for_s4=true` means technical eligibility only: the source
object is an aptamer, sequence/molecule/chemistry/construct review is
complete, and the record may enter a future corpus-wide global S4. It
does not mean target identified, target canonicalised, protein target
confirmed, UniProt resolved, evidence scored, affinity resolved, PDB
resolved, leakage cleared, final corpus included, deduplicated,
clustered, balanced, or partitioned.

### Numbers

- Source rows retained through checkpoint: 2128
- 169 judgement decisions applied (119 edit / 50 drop / 0 keep)
- 122 audit-only records bulk-confirmed with `keep_current_route`
- 50 manual drops
- 11 reviewed sequence corrections; 106 molecule/chemistry overrides
- Molecule resolution removed all unresolved-molecule primary parks
- ssDNA parked (845)
- Supported modified RNA chemistries retained (2F-RNA, 2NH2-RNA, mixed)
- Seven chemistry-unknown modified RNA cases remain parked
- Seven T7 5′-17 nt known-motif trims applied once
- Final technically eligible: 881
- `authorised_for_s4`: 881

Reconciliation: 395 technical/source reject + 845 parked ssDNA + 0
molecule park + 7 chemistry park + 0 construct park + 881 technically
eligible = 2128.

Dry-run/apply parity: 10/10 corresponding CSV payloads byte-identical;
semantic mismatches = 0. Deterministic verification rerun passed.
Tracked resolutions/metadata contain no biological sequences.

### Pipeline stop

```text
AptamerBase S0 complete.
AptamerBase S1 complete and frozen.
AptamerBase S2 complete.
AptamerBase S3 complete.
AptamerBase CHECKPOINT-1 applied and closed.
881 AptamerBase records are technically authorised for future global S4.
AptamerBase global-S4 handoff has NOT been prepared.
Global S4 has not been run.
```

## 2026-09-09 — AptamerBase prepared for future global S4

AptamerBase S1–S3 are complete and CHECKPOINT-1 is closed. The 881
CHECKPOINT-authorised records were materialised from the authoritative
applied checkpoint state as one future corpus-wide global S4 input.
Global S4 was not run. Target normalisation, evidence scoring, leakage
exclusion, and deduplication were not performed.

`authorised_for_s4=true` / inclusion in this handoff means only
technically eligible after AptamerBase sequence/molecule/chemistry/construct
review. It does not mean target identified, target canonicalised, protein
target confirmed, UniProt resolved, evidence scored, affinity resolved,
PDB resolved, leakage cleared, final corpus included, deduplicated,
clustered, balanced, or partitioned.

Handoff denominator: 881 authorised physical records, 881 unique
`record_id`, 881 handoff rows. Unique Freebase IDs = 827; 32 duplicated
Freebase-ID groups covering 86 rows (diagnostic only — physical rows were
not collapsed). Exact sequence-duplicate diagnostic: 40 duplicate
`sequence_full` values across 109 records; same for `sequence_core`.
Minimal-aptamer relations retained as source metadata: 84 nonempty
`has_minimal_aptamer` and 84 nonempty `is_minimal_aptamer_of`.

Canonical `target_name_raw` remains empty. `aptamerbase_label` is sidecar
source metadata only and was not copied into `target_name_raw`. The
Freebase ID (`aptamerbase_id`) is nonempty on every authorised row and is
preserved as the future source-metadata join key
(`record_id` → S1 sidecar Freebase ID → interaction/experiment graph).
Original interaction/experiment companion tables are not registered;
they remain a prerequisite for actual global S4 target/evidence
enrichment.

Derived authorised-lane technical state: molecule_type RNA = 881;
chemistry RNA = 758, 2F-RNA = 112, 2NH2-RNA = 6, mixed = 5; ssDNA = 0;
molecule unknown = 0; chemistry unknown = 0; source_object_type aptamer
= 881; reviewed T7 trims = 7 (0922 core 89; 1738–1741 core 81; 1935 core
65; 1955 core 58). No additional trims were applied. T-transcribed
records = 119.

SOURCE METADATA ONLY — NOT CANONICAL TARGET/EVIDENCE DECISIONS:
nonempty labels = 881; has_experimentally_determined_structure=true =
125; RDF RNA flag true = 837; RDF DNA flag true = 14; RDF
modified_nucleic_acid flag true = 127. Structure booleans were not
mapped to E1/PDB.

Tracked: `config/global_s4_sources/aptamerbase.json`,
`docs/data_curation/aptamerbase_global_s4_handoff.md`, a reusable
extension of `prepare_global_s4_source.py` for additional source-metadata
joins / required Freebase IDs / derived summary counts, and tests.
Ignored: `aptamerbase_global_s4_input.csv` (881 rows) and the
sequence-free handoff summary. Deterministic rerun was byte-identical.
Raw / RDF / S1 / sidecar / S2 / pre-review S3 / completed review /
CHECKPOINT closure / applied hashes were unchanged. `git ls-files data`
remains empty.

### Pipeline status

```text
AptamerBase S0 complete.
AptamerBase S1 complete and frozen.
AptamerBase S2 complete.
AptamerBase S3 complete.
AptamerBase CHECKPOINT-1 applied and closed.
AptamerBase future global-S4 handoff prepared for 881 records.
AptamerBase target/evidence enrichment has NOT been run.
Global S4 has not been run.
```

## 2026-09-10 — AptaDiff Dataset A/B S0 registration and S1 verbatim extraction

**Stage:** Aim 2 / data curation / AptaDiff A/B S0 registration + S1
verbatim extraction only. AptaDiff S2 was not started.

### What was done

AptaDiff Dataset A and Dataset B were registered as two distinct Tier-1
sources and extracted independently. There is no combined `aptadiff`
source identity or output. Every physical P6 CSV row was retained.
Sequence normalisation, molecule/chemistry decisions, T→U conversion,
constant-region inference, target canonicalisation, evidence/affinity
mapping, eligibility, parking, capping, downsampling, clustering,
deduplication, CHECKPOINT-1, and global S4 were not performed.

### Decisions made

- Two source keys: `aptadiff_a` and `aptadiff_b`. They are not merged.
- `native_id` is the zero-padded 1-based CSV data-row ordinal (five
  digits). `record_id` is `aptadiff_a:{native_id}` or
  `aptadiff_b:{native_id}`. Sequence is not used as a native ID.
- Source `seq` is copied verbatim into `sequence_raw`. No uppercase,
  whitespace stripping, T→U, N repair, alphabet exclusion, trimming,
  or row collapse.
- There is no per-row target column. `target_name_raw` remains empty.
  Documented IGFBP3 (A) and PTK7 (B) identity is sidecar-only
  (`aptadiff_documented_target`, `aptadiff_target_provenance`).
- Source `p6` is preserved exactly in each sidecar and is not mapped
  to affinity, evidence, a binding score, or a sampling/capping weight.
  Its later use for abundance-aware capping and Dataset A replication
  remains available; S1 does not interpret it as round-6 read count.
- S1 is molecule-neutral. Primary-source review outside Cursor
  indicates ssDNA HT-SELEX libraries with a DNA_T alphabet and
  random-region-only 36-nt constructs; that evidence will govern the
  forthcoming S2 decision. It was not applied at S1.
- `datasetA_IGFBP3_x_z.csv` is a derived latent-coordinate file and is
  forbidden as a parallel input. Dataset A remains 13803 rows; it is
  not reduced to the 13802-row x_z derivative. Dataset A is retained
  whole for a later uncapped replication role.
- Dataset C and Dataset D are not companion corpus inputs.
- `redistribution_status = unknown` because no explicit sequence-data
  redistribution licence has been established.
- No capping or downsampling during S1–S3.

### Inputs used

- `source_key = aptadiff_a`
- `source_dataset = aptadiff_a_igfbp3_p6_2026-06-22`
- `data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv`
- SHA-256:
  `ec970c478aaba1aa089ecbaf7f5bc8aa7a11f6eacd0f7b3d3c418de6a27e8c77`
- 13803 rows; schema `seq,p6`
- Snapshot date: `2026-06-22`; tier `1`;
  `redistribution_status = unknown`

- `source_key = aptadiff_b`
- `source_dataset = aptadiff_b_ptk7_p6_2026-06-22`
- `data/raw/Aptadiff_otherdata/datasetB_PTK7_P6.csv`
- SHA-256:
  `546de810e34035731502caf6476c73cc06feab8156ec8178efaade2d21bf4d72`
- 11547 rows; schema `seq,p6`
- Snapshot date: `2026-06-22`; tier `1`;
  `redistribution_status = unknown`

### Outputs produced

Ignored under `/data/`:

- `data/interim/registry/source_registry.csv` (operational S0 registry;
  17 validated registered files; exactly one `aptadiff_a` and one
  `aptadiff_b` entry)
- `data/interim/extracted/aptadiff_a_extracted.csv` (13803 rows)
- `data/interim/extracted/aptadiff_a_source_metadata.csv` (13803 rows)
- `data/interim/extracted/aptadiff_a_s1_report.md`
- `data/interim/extracted/aptadiff_b_extracted.csv` (11547 rows)
- `data/interim/extracted/aptadiff_b_source_metadata.csv` (11547 rows)
- `data/interim/extracted/aptadiff_b_s1_report.md`

Tracked scripts, tests and this log entry. Nothing under `data/` is
tracked. The governing curation plan was not updated.

### Numbers

Dataset A:

- 13803 rows in / 13803 canonical / 13803 sidecar
- 13803 unique `record_id`; 13803 unique `native_id`
- first native ID `00001`; last native ID `13803`
- all length 36; 13802 A/C/G/T-only; 1 N-containing row retained
- no missing rows; no duplicate sequences
- p6 sidecar exact copy; diagnostic min/median/max 5 / 9 / 194981
- `target_name_raw` populated: 0

Dataset B:

- 11547 rows in / 11547 canonical / 11547 sidecar
- 11547 unique `record_id`; 11547 unique `native_id`
- first native ID `00001`; last native ID `11547`
- all length 36; 11532 A/C/G/T-only; 15 N-containing rows retained
- no missing rows; no duplicate sequences
- p6 sidecar exact copy; diagnostic min/median/max 2 / 4 / 36136
- `target_name_raw` populated: 0

A vs B exact sequence overlap: 0. No combined output. 0 S1
rejections, parking, filtering, capping, or deduplication.

S0: 15 registered files before, 17 after; 17 validated; existing
AptaBase and ENA inventory-override warnings only. x_z, C, and D are
not registered.

Source raw hashes unchanged before and after S0/S1. Deterministic S1
rerun: byte-identical canonical, sidecar, and report files.

### Open questions carried forward

- S2 molecule/chemistry/alphabet decision (ssDNA / DNA_T; no T→U;
  random_region_only) is authorised only as a forthcoming S2 task.
- Later abundance-aware target capping using preserved `p6`.
- Dataset A uncapped replication export later.
- CHECKPOINT-1 later. Global S4 later.

### Pipeline status

```text
AptaDiff Dataset A S0 complete
AptaDiff Dataset A S1 complete
AptaDiff Dataset A S2 has not started
AptaDiff Dataset B S0 complete
AptaDiff Dataset B S1 complete
AptaDiff Dataset B S2 has not started
No AptaDiff A/B record is authorised for global S4
```

## 2026-09-10 — AptaDiff Dataset A/B S2 sequence normalisation

**Stage:** Aim 2 / data curation / AptaDiff A/B S2 sequence normalisation only.
AptaDiff S3 was not started. Records were not parked.

### What was done

Accepted S1 canonical tables for `aptadiff_a` and `aptadiff_b` were
normalised independently through the shared sequence-normalisation
machinery and two separate source-normalisation contracts. There is
still no combined `aptadiff` source identity. Every S1 row was
retained. S3 eligibility, ssDNA parking, N-row rejection, CHECKPOINT-1,
global-S4 handoffs, capping, downsampling, clustering, balancing,
partitioning, and Dataset-A replication export were not performed.

The governing plan was corrected so future implementation does not treat
A/B as RNA.

### Decisions made

- Laura's explicit source-level decision, from primary AptaDiff paper
  review: both A and B are genuine ssDNA HT-SELEX libraries, not RNA
  molecules printed using T. Canonical chemistry is DNA.
- Molecule identity is not inferred from sequence alphabet.
- Canonical S2 retains DNA. `t_to_u_applied = false` for every row.
  No ordinary AptaDiff sequence is computationally transcribed to RNA.
- The registered P6 `seq` values are 36-nt random regions. Experimental
  fixed primer constructs were already excluded.
  `construct_scope = random_region_only`; `sequence_core == sequence_full`.
- Constant-region inference is disabled by source contract. No known-motif
  trim, T7-promoter trim, group-wise consensus trim, or selected-sequence
  end scanning. Shared SELEX motifs are not treated as residual primers.
  The constant-region proposal artefact is header-only.
- N-containing rows (A: 1; B: 15) survive S2, remain ssDNA, are classified
  `alphabet_as_reported = ambiguous`, carry `ambiguous_base`, and are
  review candidates. N is not repaired, dropped, or used to exclude the
  row. Later S3 technical rejection is not applied here.
- `p6` is preserved uninterpreted in the S1 sidecar and copied into S2 QC
  only. It does not populate affinity or evidence fields and is not used
  for filtering or sampling.
- Canonical `target_name_raw` remains empty. Documented IGFBP3 (A) and
  PTK7 (B) identity remains sidecar provenance. Target canonicalisation
  remains global S4.
- Binding evidence, evidence score, affinity, leakage, and target
  eligibility are not evaluated at S2. HT-SELEX provenance is not an
  instruction to assign E4 here.
- Dataset A remains 13,803 rows (not reduced to the 13,802-row `x_z`
  derivative) and remains available, uncapped, for later AptaDiff /
  RNAGenesis replication/comparability. Any future RNA-alphabet Dataset-A
  representation would be a derived replication-specific transformation
  with explicit provenance, not a change to experimental molecule identity.
  That derived representation was not built.
- The previous plan instruction to computationally transcribe A/B to RNA
  for the canonical corpus is superseded. Ordinary technically valid rows
  will later park as ssDNA and are excluded from the primary RNA corpus by
  default. They do not participate in ordinary primary-RNA target capping
  unless the DNA-parking policy is later changed.

### Inputs used

S1 canonical outputs (unchanged hashes):

- `data/interim/extracted/aptadiff_a_extracted.csv`
  SHA-256: `22bd7357311ce5d9d0a000c20f75fc439942b16c37105a71509fb8329ee7b083`
- `data/interim/extracted/aptadiff_a_source_metadata.csv`
  SHA-256: `ec0453c50205854dc1648c833a2f96a40b691ee39b8c49433d0024480c9314ea`
- `data/interim/extracted/aptadiff_b_extracted.csv`
  SHA-256: `321ef00b4e7a78834f431b4335bf21e89752c8e596523480676f2d5ac2e50921`
- `data/interim/extracted/aptadiff_b_source_metadata.csv`
  SHA-256: `3f7183e5999d2f729b1fd1d225287b3515414cec2d7b91e44de46cf84a5ec4a0`

Registered raw files (hash-verification only; unchanged):

- `data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv`
  SHA-256: `ec970c478aaba1aa089ecbaf7f5bc8aa7a11f6eacd0f7b3d3c418de6a27e8c77`
- `data/raw/Aptadiff_otherdata/datasetB_PTK7_P6.csv`
  SHA-256: `546de810e34035731502caf6476c73cc06feab8156ec8178efaade2d21bf4d72`

Source policies:

- `config/source_normalisation/aptadiff_a.json`
- `config/source_normalisation/aptadiff_b.json`
- Shared rules: `config/sequence_normalisation_rules.json`

### Outputs produced

Ignored under `/data/`:

- `data/interim/normalised/aptadiff_a_normalised.csv` (13803 rows)
- `data/interim/normalised/aptadiff_a_s2_qc.csv`
- `data/interim/normalised/aptadiff_a_s2_review_candidates.csv` (1 row)
- `data/interim/normalised/detected_constants_aptadiff_a.csv` (header only)
- `data/interim/normalised/aptadiff_a_s2_report.md`
- `data/interim/normalised/aptadiff_b_normalised.csv` (11547 rows)
- `data/interim/normalised/aptadiff_b_s2_qc.csv`
- `data/interim/normalised/aptadiff_b_s2_review_candidates.csv` (15 rows)
- `data/interim/normalised/detected_constants_aptadiff_b.csv` (header only)
- `data/interim/normalised/aptadiff_b_s2_report.md`

Tracked: source-normalisation configs, AptaDiff S2 adapter, S2 dispatcher,
synthetic tests, governing-plan correction, and this log entry. Nothing
under `data/` is tracked.

### Numbers

Dataset A:

- 13803 S1 rows in / 13803 S2 rows out; 0 dropped; 0 parked
- `molecule_type=ssDNA` 13803; `chemistry=DNA` 13803
- `alphabet_as_reported=DNA_T` 13802; `ambiguous` 1
- T→U applied: 0; applied trims: 0; core differs from full: 0
- length 36 for every row; `random_region_only` 13803
- review candidates: 1 (the N-containing row)

Dataset B:

- 11547 S1 rows in / 11547 S2 rows out; 0 dropped; 0 parked
- `molecule_type=ssDNA` 11547; `chemistry=DNA` 11547
- `alphabet_as_reported=DNA_T` 11532; `ambiguous` 15
- T→U applied: 0; applied trims: 0; core differs from full: 0
- length 36 for every row; `random_region_only` 11547
- review candidates: 15 (N-containing rows)

S1 canonical, sidecar, and S1 report hashes were unchanged after S2.
Registered raw hashes were unchanged. Deterministic S2 rerun:
byte-identical normalised, QC, review, and proposal files. `git ls-files
data` remains empty.

### Open questions carried forward

- S3 technical eligibility, including routing of ordinary valid ssDNA
  rows to the parked-ssDNA lane and separate handling of the 16
  N-containing rows, is authorised only as a forthcoming S3 task.
- Dataset A uncapped replication export later, including any optional
  derived RNA-alphabet representation.
- CHECKPOINT-1 later. Global S4 later.

### Pipeline status

```text
AptaDiff Dataset A S0 complete
AptaDiff Dataset A S1 complete
AptaDiff Dataset A S2 complete
AptaDiff Dataset A S3 has not started
AptaDiff Dataset B S0 complete
AptaDiff Dataset B S1 complete
AptaDiff Dataset B S2 complete
AptaDiff Dataset B S3 has not started
No AptaDiff A/B record has been parked
No AptaDiff A/B record is authorised for global S4
```

## 2026-09-10 — AptaDiff Dataset A/B S3 technical classification and CHECKPOINT-1 preparation

**Stage:** Aim 2 / data curation / AptaDiff A/B S3 technical classification +
CHECKPOINT-1 package preparation only. Human review was not entered.
CHECKPOINT-1 was not applied or closed. Global-S4 handoffs were not prepared.
Dataset-A replication output was not built.

### What was done

Accepted S2 tables for `aptadiff_a` and `aptadiff_b` were classified
independently through source-specific eligibility policies and a shared
AptaDiff S3 adapter. There is still no combined `aptadiff` source identity.
Every S2 row was retained and assigned exactly one primary route. Technical
sequence failure was applied before otherwise-valid ssDNA parking. Unresolved
CHECKPOINT-1 packages were generated for Laura; human decision fields were left
blank.

### Decisions made

- Both sources remain experimentally `molecule_type = ssDNA`, `chemistry =
  DNA`. Canonical DNA was retained. No T→U.
- Ordinary clean A/C/G/T 36-nt `random_region_only` records park as
  `ssdna_parked`. They are not RNA accepts, not global-S4-authorised, and not
  CHECKPOINT scientific anomalies. They do not require manual confirmation.
- N-containing rows remain experimentally ssDNA, but the unresolved IUPAC N
  is a technical sequence failure (`proposed_reject`, `ambiguous_bases`) rather
  than an ordinary DNA park. N was not repaired, inferred, deleted, or
  transcribed. These 16 rows are the only active CHECKPOINT-1 scientific
  exceptions.
- Machine recommendation for those exceptions is `confirm_current_reject`
  (no source-supported deterministic repair). Human `manual_*` fields remain
  blank. CHECKPOINT-1 remains unresolved.
- Empty `target_name_raw` is not a missing-target rejection. Documented IGFBP3
  (A) and PTK7 (B) identity remains sidecar provenance.
- `p6` is preserved uninterpreted and is not a technical gate.
- Constant-region inference remains disabled. Applied trims = 0. Length 36
  is inside the technical window (`length_out_of_range = 0`).
- Zero technically eligible RNA records. The random-kept audit pool is empty
  (sampled 0 / requested 30 / shortfall 30). No fabricated RNA audit.
- `authorised_for_s4` remains 0 for both sources. No global-S4 handoff was
  prepared.
- Dataset-A replication (`corpus_replication_datasetA.csv`) was not built.
  Whether a later replication file should preserve all 13,803 P6 rows or
  the 13,802-row x_z consumed set is deferred. Canonical S3 may reject the one
  N-containing Dataset-A row; the source row remains in raw/S1/S2.

### Inputs used

S2 canonical hashes (unchanged):

- `data/interim/normalised/aptadiff_a_normalised.csv`
  SHA-256: `c88e6f12dea4d60377a1c5a7a95861fcc666e47be27920a234f828b70df6ca55`
- `data/interim/normalised/aptadiff_b_normalised.csv`
  SHA-256: `c40bc662f4c79fcc24c161c5a82e74c2d58f96fbb6ca74fbb84b105bf8bc98f6`

S1 hashes (unchanged):

- `data/interim/extracted/aptadiff_a_extracted.csv`
  SHA-256: `22bd7357311ce5d9d0a000c20f75fc439942b16c37105a71509fb8329ee7b083`
- `data/interim/extracted/aptadiff_a_source_metadata.csv`
  SHA-256: `ec0453c50205854dc1648c833a2f96a40b691ee39b8c49433d0024480c9314ea`
- `data/interim/extracted/aptadiff_b_extracted.csv`
  SHA-256: `321ef00b4e7a78834f431b4335bf21e89752c8e596523480676f2d5ac2e50921`
- `data/interim/extracted/aptadiff_b_source_metadata.csv`
  SHA-256: `3f7183e5999d2f729b1fd1d225287b3515414cec2d7b91e44de46cf84a5ec4a0`

Registered raw hashes (unchanged):

- `data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv`
  SHA-256: `ec970c478aaba1aa089ecbaf7f5bc8aa7a11f6eacd0f7b3d3c418de6a27e8c77`
- `data/raw/Aptadiff_otherdata/datasetB_PTK7_P6.csv`
  SHA-256: `546de810e34035731502caf6476c73cc06feab8156ec8178efaade2d21bf4d72`

Policies:

- `config/source_eligibility/aptadiff_a.json`
- `config/source_eligibility/aptadiff_b.json`

### Outputs produced

Ignored under `/data/`:

- `data/interim/checkpoints/aptadiff_a_cp1/` (S3 decisions, parked ssDNA,
  rejection log, all-record sequence-free review index, local-detail, summary)
- `data/interim/checkpoints/aptadiff_a_cp1/manual_review/` (1-row active queue;
  human fields blank)
- `data/interim/checkpoints/aptadiff_b_cp1/` (separate B artefacts)
- `data/interim/checkpoints/aptadiff_b_cp1/manual_review/` (15-row active queue;
  human fields blank)

Tracked: eligibility policies, recommendation configs, AptaDiff S3 adapter,
CHECKPOINT-1 prepare helper, S3/CHECKPOINT dispatch, synthetic tests, and this
log entry. Nothing under `data/` is tracked.

### Numbers

Dataset A:

- S3 input = 13803
- parked ssDNA = 13802 (`ssdna_parked`)
- technical reject = 1 (`ambiguous_bases`)
- technically eligible RNA = 0
- 13803 = 13802 + 1 + 0
- active CHECKPOINT review = 1
- `authorised_for_s4` = 0

Dataset B:

- S3 input = 11547
- parked ssDNA = 11532 (`ssdna_parked`)
- technical reject = 15 (`ambiguous_bases`)
- technically eligible RNA = 0
- 11547 = 11532 + 15 + 0
- active CHECKPOINT review = 15
- `authorised_for_s4` = 0

Combined diagnostic only (outputs remain separate): 25350 rows; 25334 parked
ssDNA; 16 ambiguous-N technical rejects; 0 RNA eligible.

T→U applied: 0. Applied trims: 0. Constant-region proposals: 0.
`length_out_of_range` = 0. Human decision fields blank. CHECKPOINT-1 not closed.

### Open questions carried forward

- Laura CHECKPOINT-1 review of the 16 N-containing technical exceptions.
- After closure: whether the live architecture wants no global-S4 handoff
  because authorised count = 0, or an explicit empty/zero-record closure
  handoff for provenance.
- Dataset-A replication row-count decision (13,803 P6 vs 13,802 x_z).
- Later abundance-aware target capping using preserved `p6`.

### Pipeline status

```text
AptaDiff Dataset A S0 complete
AptaDiff Dataset A S1 complete
AptaDiff Dataset A S2 complete
AptaDiff Dataset A S3 complete
AptaDiff Dataset A CHECKPOINT-1 package generated; human review pending
AptaDiff Dataset B S0 complete
AptaDiff Dataset B S1 complete
AptaDiff Dataset B S2 complete
AptaDiff Dataset B S3 complete
AptaDiff Dataset B CHECKPOINT-1 package generated; human review pending
CHECKPOINT-1 not applied
CHECKPOINT-1 not closed
No AptaDiff A/B record is authorised for global S4
Dataset-A replication not built
```

## 2026-09-10 — AptaDiff Dataset A/B CHECKPOINT-1 closed

**Stage:** Aim 2 / data curation / AptaDiff A/B CHECKPOINT-1 human
decision recording, fail-closed validation, dry-run, actual apply, and
closure. Global S4 was not prepared or run. Dataset-A replication was
not built. No T→U was introduced. The replication denominator remains a
later decision.

### What was done

Laura approved the complete CHECKPOINT-1 decision set in advance: all
16 unresolved-IUPAC-N review records (1 in Dataset A, 15 in Dataset B)
were confirmed as current technical rejects. There was no
source-supported deterministic nucleotide repair. No nucleotide
replacement was invented. Ordinary ssDNA parks were not reviewed as
scientific exceptions and were left on their existing park route.

Human decisions were recorded in the existing AptaDiff CHECKPOINT-1
review files using the live `keep` / `drop` / `edit` vocabulary.
Confirming the current reject is encoded as `manual_decision=keep` so
the technical reason remains `ambiguous_bases`. Correction fields were
left empty. No-review parked rows were not marked as reviewed exceptions
and were not authorised for S4.

Fail-closed validation passed for both sources. The empty RNA-eligible
audit pool was not treated as an unresolved human decision and no audit
rows were fabricated. A production dry-run used the same
`apply_aptadiff_checkpoint1_package` transformation as actual apply and
was GO for both sources, including a byte-identical deterministic
rerun. Actual apply then matched the locked dry-run preview
(`semantic_mismatches=0`; compared artefacts were byte-identical).
Sequence-safe tracked closure artefacts were written separately for
`aptadiff_a` and `aptadiff_b`.

These two Tier-1 sources are now completely curated at CHECKPOINT-1.
They contribute no records to primary global S4. Ordinary records
remain parked DNA. AptaDiff A/B do not contribute to the RNA corpus at
this stage.

### Decisions made

- All 16 reviewed records: confirm current rejection (`keep`).
- Technical rejection reason remains `ambiguous_bases`.
- 0 approved repairs; 0 sequence edits; 0 molecule overrides;
  0 chemistry overrides; 0 trim decisions; 0 target corrections;
  0 source-review deferrals.
- Ordinary ssDNA parks: A 13802 and B 11532 remain parked; not converted
  to rejects; not marked reviewed exceptions; not authorised for S4.
- `authorised_for_s4 = 0` is a valid final count.
- No ordinary global-S4 handoff was prepared. No empty/synthetic
  global-S4 input was created.
- `corpus_replication_datasetA.csv` was not built. Whether a later
  replication file should use 13803 P6 rows or the 13802-row x_z
  consumed set remains deferred.

### Inputs used

Human review queues after recording:

- `data/interim/checkpoints/aptadiff_a_cp1/manual_review/aptadiff_a_checkpoint1_manual_review.csv`
  (1 row; `keep`; SHA-256
  `5a60217e6df22bd70746865cf50ec15fc151bd249dd7ffa0928ffba593e94b23`)
- `data/interim/checkpoints/aptadiff_b_cp1/manual_review/aptadiff_b_checkpoint1_manual_review.csv`
  (15 rows; `keep`; SHA-256
  `9ac8a27bbdc2dafde1b7bf3c6aa89f73b6b80a3748edc011a33552a2122019dc`)

Frozen raw / S1 / S2 / pre-review S3 hashes were unchanged (see Integrity).

### Numbers

Fail-closed validation:

- aptadiff_a: active review records = 1; resolved human decisions = 1;
  unresolved = 0; blocking issues = 0
- aptadiff_b: active review records = 15; resolved human decisions = 15;
  unresolved = 0; blocking issues = 0

Dry-run and actual apply routing (unchanged from provisional S3):

Dataset A:

- total = 13803
- parked ssDNA = 13802
- rejected = 1 (`ambiguous_bases`)
- authorised_for_s4 = 0
- 13803 = 13802 + 1

Dataset B:

- total = 11547
- parked ssDNA = 11532
- rejected = 15 (`ambiguous_bases`)
- authorised_for_s4 = 0
- 11547 = 11532 + 15

Combined diagnostic only (outputs remain source-separate): 25350
records; 25334 parked ssDNA; 16 rejected ambiguous-N; 0 authorised for
S4.

Sequence corrections = 0. Molecule/chemistry overrides = 0. Trim
changes = 0. Target corrections = 0. T→U applied = 0. N was not
replaced. Reviewed rows remain experimentally `molecule_type=ssDNA`,
`chemistry=DNA`, with unresolved N in sequence provenance.

### Outputs produced

Ignored under `/data/`:

- `data/interim/checkpoints/aptadiff_a_cp1/dry_run/`
- `data/interim/checkpoints/aptadiff_a_cp1/resolved/`
- `data/interim/checkpoints/aptadiff_b_cp1/dry_run/`
- `data/interim/checkpoints/aptadiff_b_cp1/resolved/`

Tracked sequence-safe closure artefacts (no aptamer sequences):

- `config/checkpoint_reviews/aptadiff_a_checkpoint1_resolutions.csv`
  SHA-256: `700fec79d4ff22beef9c1ce3ea567993946f6986c03d1e94ef00745db8d9dfbf`
- `config/checkpoint_reviews/aptadiff_a_checkpoint1_metadata.json`
- `config/checkpoint_reviews/aptadiff_b_checkpoint1_resolutions.csv`
  SHA-256: `b2224e30306ef78c738f6ff4435b3ff2e1ed023afca8a874f921e4e4e98c2687`
- `config/checkpoint_reviews/aptadiff_b_checkpoint1_metadata.json`

Closure metadata: `checkpoint1_closed = true` for both;
`authorised_for_s4 = 0` / `0`; `global_s4_run = false`;
`dataset_a_replication_built = false`. Dry-run/apply preview comparison
passed with 0 semantic mismatches and byte-identical canonical,
routing, rejection, parked-ssDNA, eligible, change-report, and
decision-audit artefacts.

Nothing under `data/` is tracked. No AptaDiff global-S4 input was
written under `data/interim/global_s4_ready/`.

### Integrity

Registered raw hashes unchanged:

- `data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv`
  SHA-256: `ec970c478aaba1aa089ecbaf7f5bc8aa7a11f6eacd0f7b3d3c418de6a27e8c77`
- `data/raw/Aptadiff_otherdata/datasetB_PTK7_P6.csv`
  SHA-256: `546de810e34035731502caf6476c73cc06feab8156ec8178efaade2d21bf4d72`

S1 canonical/sidecar hashes unchanged:

- `data/interim/extracted/aptadiff_a_extracted.csv`
  SHA-256: `22bd7357311ce5d9d0a000c20f75fc439942b16c37105a71509fb8329ee7b083`
- `data/interim/extracted/aptadiff_a_source_metadata.csv`
  SHA-256: `ec0453c50205854dc1648c833a2f96a40b691ee39b8c49433d0024480c9314ea`
- `data/interim/extracted/aptadiff_b_extracted.csv`
  SHA-256: `321ef00b4e7a78834f431b4335bf21e89752c8e596523480676f2d5ac2e50921`
- `data/interim/extracted/aptadiff_b_source_metadata.csv`
  SHA-256: `3f7183e5999d2f729b1fd1d225287b3515414cec2d7b91e44de46cf84a5ec4a0`

S2 canonical hashes unchanged:

- `data/interim/normalised/aptadiff_a_normalised.csv`
  SHA-256: `c88e6f12dea4d60377a1c5a7a95861fcc666e47be27920a234f828b70df6ca55`
- `data/interim/normalised/aptadiff_b_normalised.csv`
  SHA-256: `c40bc662f4c79fcc24c161c5a82e74c2d58f96fbb6ca74fbb84b105bf8bc98f6`

Pre-review S3 inputs unchanged:

- `aptadiff_a_s3_canonical.csv` SHA-256:
  `c88e6f12dea4d60377a1c5a7a95861fcc666e47be27920a234f828b70df6ca55`
- `aptadiff_a_s3_decisions.csv` SHA-256:
  `d17c68aa2b97d9b4836a1dcf77de6c5cf596145aa4064f8f46ca76a9bda45af1`
- `aptadiff_b_s3_canonical.csv` SHA-256:
  `c40bc662f4c79fcc24c161c5a82e74c2d58f96fbb6ca74fbb84b105bf8bc98f6`
- `aptadiff_b_s3_decisions.csv` SHA-256:
  `921b4eb4d7799e7ffcf12da5154665c111e0b9ccca5ddde71af0ce23aaae5433`

Human review files changed only in permitted review fields
(`manual_decision`, `manual_notes`). `git ls-files data` remains empty.
Deterministic dry-run and apply reruns were byte-identical.

### Tests

Synthetic non-biological fixtures only. Targeted suite:

`tests/data_preparation/test_aptadiff_checkpoint1_apply.py`,
`test_aptadiff_checkpoint1_prepare_review.py`, AptaDiff S1/S2/S3 adapter
tests, and completed-source CHECKPOINT regressions
(`test_aptamerbase_checkpoint1_apply.py`,
`test_checkpoint1_apply_review.py`,
`test_checkpoint1_prepare_review.py`): **203 passed**.

Covered: completed 1-row A-style and multi-row B-style validation;
confirm-current-reject preserves `ambiguous_bases`; no sequence
correction; reviewed ambiguous ssDNA remains rejected; no-review
ssDNA remains parked; no reviewed record becomes S4-authorised; final
authorised count may be zero; empty RNA audit pool does not manufacture
review rows; unresolved decisions fail closed; dry-run does not write
resolved outputs; actual apply uses the same transformation; dry-run
and apply routing parity; tracked artefacts are sequence-free and
source-separate.

### Open questions carried forward

- Dataset-A replication row-count decision (13,803 P6 vs 13,802 x_z)
  and any later optional derived RNA-alphabet representation.
- Later abundance-aware target capping using preserved `p6`.
- Global S4 remains a later, separate corpus-wide step. AptaDiff A/B
  currently contribute 0 authorised primary-RNA records to that step.

### Pipeline status

```text
AptaDiff Dataset A S0 complete
AptaDiff Dataset A S1 complete
AptaDiff Dataset A S2 complete
AptaDiff Dataset A S3 complete
aptadiff_a CHECKPOINT-1 closed
AptaDiff Dataset B S0 complete
AptaDiff Dataset B S1 complete
AptaDiff Dataset B S2 complete
AptaDiff Dataset B S3 complete
aptadiff_b CHECKPOINT-1 closed
authorised_for_s4 = 0 / 0
global S4 not prepared
global S4 not run
Dataset-A replication not built
All ordinary AptaDiff A/B records remain parked DNA
```

## 2026-09-10 — Source-preparation methodology brought under version control

Repository provenance only. No scientific pipeline was rerun. Completed
ENA, AptaBase, and AptaDiff source decisions were not changed.

The previously untracked AptaBase scrape/parser/cleaner and ENA
inspection/candidate/review-v2 scripts, READMEs, synthetic tests, and
synthetic EMBL fixture are now tracked. They document the pre-S1
preparation of the frozen registered AptaBase cleaned scrape and the ENA
679-row selected lane. They are not part of the live S1–S3 execution path.
See `docs/data_curation/source_preparation_methodology.md`.

## 2026-09-12 — NCBI Nucleotide S0 registration and S1 GenBank extraction

**Stage:** Aim 2 / data curation / NCBI Nucleotide (`ncbi_nuc`) S0
registration + S1 verbatim GenBank extraction only. S2 was not
started. CHECKPOINT-1 was not opened. Global S4 was not run.

### What was done

All 18 authoritative NCBI Nucleotide `.gb` files under
`data/raw/NCBI_nucleotide` were registered as one logical Tier-1 source
and frozen by SHA-256 plus expected GenBank record count. S0 gained
generic GenBank record-count support: `n_rows_expected` for `.gb`
inputs is the number of physical GenBank records parsed from that file
(here `1` per file), not LOCUS length, text lines, FEATURES, or any
later cleaned-sequence count. One `ncbi_nuc` S1 adapter then consumed
every registered row of the shared `source_dataset` in registry order
and emitted one canonical record per parsed GenBank record. Filenames
were treated as opaque. Sequence normalisation, T→U, molecule or
chemistry assignment, trimming, target extraction, eligibility
classification, evidence scoring, leakage, NCBI↔ENA deduplication,
within-NCBI deduplication, clustering, balancing, partition, and
CHECKPOINT-1 were deliberately not performed.

### Decisions made

- Logical source: `source_key = ncbi_nuc`;
  `source_dataset = ncbi_nuc_genbank_2026-07-27`.
- `snapshot_date = 2026-07-27` is a local source-snapshot/download-date
  proxy supported by the tight 2026-07-27 file-mtime cluster. It is
  not an NCBI database release date.
- `tier = 1`; `redistribution_status = unknown` because no local
  licence/reuse documentation establishes something stronger.
- `native_id` is GenBank ACCESSION. `record_id` is
  `ncbi_nuc:{ACCESSION}`. LOCUS, VERSION, and local filename remain
  sidecar provenance. ACCESSION is populated and unique 18/18.
  Canonical `accession` remains empty under the live S1 stage guard.
- `sequence_raw` is the deposited ORIGIN residue string after removing
  only flatfile display syntax (line numbers, grouping spaces, line
  breaks). Deposited lowercase case is preserved. No T→U, no IUPAC/N
  removal, no trimming.
- Canonical `target_name_raw` is empty for all 18 records. Target-like
  strings in DEFINITION, COMMENT, and reference titles are sidecar
  context only.
- Canonical `pubmed_id` is populated only where a record has exactly
  one unambiguous structured PUBMED value: U34759 → 9222504 and
  AF083271 → 9751715. Canonical `publication` and `doi` remain empty.
  Complete FEATURES, COMMENT, and REFERENCE sets are in the sidecar.
- No record was rejected or parked. One physical GenBank record remains
  one S1 row.

### Inputs used

- 18 registered `.gb` files under `data/raw/NCBI_nucleotide`
- 18 GenBank records; `n_rows_expected = 1` per file
- Snapshot date: `2026-07-27`; tier `1`;
  `redistribution_status = unknown`

### Outputs produced

Ignored under `data/`:

- `data/interim/registry/source_registry.csv` (operational S0
  registry; 35 validated registered files, 18 `ncbi_nuc` rows)
- `data/interim/extracted/ncbi_nuc_extracted.csv` (18 rows)
- `data/interim/extracted/ncbi_nuc_source_metadata.csv` (18 rows)
- `data/interim/extracted/ncbi_nuc_s1_report.md`

Tracked scripts, tests, registry rows, and this log entry. Nothing
under `data/` is tracked.

### Numbers

- 18 files / 18 GenBank records in; 18 extracted; 18 unique
  `record_id`; 18 unique `native_id`
- 0 S1 rejections, parking, filtering, or deduplication
- `sequence_raw` nonempty 18/18; ORIGIN length agrees with LOCUS
  length 18/18; deposited lowercase preserved; 0 U introduced
- `target_name_raw` empty 18/18; canonical accession empty 18/18
- canonical publication/DOI: 0; structured unique PMID: 2
  (U34759, AF083271)
- S0: 35 registered, 35 validated; warnings=3 (two AptaBase inventory
  overrides plus the existing ENA `derived_output_not_raw_input`
  warning). No new NCBI inventory warning.
- Deterministic S1 rerun: byte-identical canonical and sidecar
- 18 NCBI raw SHA-256 values unchanged; `git ls-files data` empty

### Tests

Synthetic non-biological fixtures only.

Focused:

`tests/data_preparation/test_s0_build_registry.py`
`tests/data_preparation/test_adapter_ncbi_nuc.py`: **61 passed**.

S0/S1 regression for completed sources (S0, S1 runner, ncbi_nuc,
ENA, AptaBase, AptamerBase, AptaDB, RiboAptamer, UTexas, AptaIndex,
AptaDiff, corpus schema): **345 passed**.

Hang-prone legacy AptaBase/ENA preparation suites were not run.

### Open questions carried forward

- NCBI Nucleotide S2 scientific normalisation and construct
  investigation, including molecule/chemistry conflicts, construct
  vs aptamer-core identity, unresolved N, short records, and
  non-protein target context.
- NCBI↔ENA accession and T/U-equivalent sequence deduplication is
  deferred to later S2/S3/CHECKPOINT/S4 work.

### Pipeline status

```text
NCBI Nucleotide S0 complete
NCBI Nucleotide S1 complete
NCBI Nucleotide S2 has not started
No NCBI Nucleotide CHECKPOINT-1 decision has been made
No NCBI Nucleotide records are yet authorised for global S4
```

## 2026-09-12 — NCBI Nucleotide S2 sequence/molecule/construct normalisation

**Stage:** Aim 2 / data curation / NCBI Nucleotide (`ncbi_nuc`) S2
sequence/molecule/construct normalisation only. S3 was not started.
CHECKPOINT-1 was not opened. Global S4 was not run.

### What was done

The 18 accepted S1 NCBI Nucleotide records were normalised with the
shared sequence-normalisation and known-motif machinery plus one
source-specific accession policy. Molecule identity was assigned only
from the approved GenBank preflight decisions, not from T/U alphabet,
patent titles, or ENA overlap. Construct scope was assigned only where
the S1 sidecar COMMENT unambiguously identified a primer, reverse
primer, poly-A fragment, or DNA transcription template. Group-wise
constant-region inference was disabled. No trim was applied.
`sequence_raw` was preserved. Canonical target, evidence, affinity,
leakage, NCBI↔ENA deduplication, and eligibility were not performed.

### Decisions made

- 18 in / 18 out; 0 dropped; 0 parked.
- RNA + chemistry RNA, T→U applied: U34759, U37124, U37123,
  AF083271, BD161067. Alphabet provenance remains `DNA_T`.
- DNA + chemistry DNA, no T→U: QT662269. Generic `DNA` is supported
  by the live schema; ssDNA was not assigned.
- Remaining 12 ACCESSION values: molecule_type unknown, chemistry
  unknown, no T→U. Alphabet alone did not manufacture molecule type.
- Ambiguous `N` in HV200497 was retained and flagged. No gaps or other
  invalid ORIGIN symbols were present; none were repaired.
- Construct: FW366678 and FZ422269 `partial_construct` (primer);
  DJ028182 `partial_construct` (poly-A fragment); DD421991
  `full_construct` (DNA transcription template; no core extracted);
  HV507922 and HW065069 construct unknown (cDNA/template, boundaries
  unresolved). Remaining records construct unknown.
- QT662269 flagged as a possible non-aptamer method/object for later
  review; not rejected.
- Group-wise constant inference disabled. Shared known-motif
  detection ran; 0 proposals because the configured T7 motif is
  5′-anchored and was not terminal. No motif was added. Applied trims
  = 0; `sequence_core == sequence_full` for 18/18.
- Target/evidence/leakage/dedup deferred.

### Inputs used

- S1 `ncbi_nuc_extracted.csv` (18) and `ncbi_nuc_source_metadata.csv` (18)
- 18 registered `.gb` files under `data/raw/NCBI_nucleotide`
- `config/source_normalisation/ncbi_nuc.json`
- `config/sequence_normalisation_rules.json`

### Outputs produced

Ignored under `data/`:

- `data/interim/normalised/ncbi_nuc_normalised.csv`
- `data/interim/normalised/ncbi_nuc_s2_qc.csv`
- `data/interim/normalised/ncbi_nuc_s2_review_candidates.csv`
- `data/interim/normalised/detected_constants_ncbi_nuc.csv`
- `data/interim/normalised/ncbi_nuc_s2_report.md`

Tracked policy, adapter, dispatcher, tests, and this log entry.
Nothing under `data/` is tracked.

### Numbers

- 18 in; 18 out; 18 unique `record_id`; 18 unique `native_id`
- molecule: RNA 5, DNA 1, unknown 12
- chemistry: RNA 5, DNA 1, unknown 12
- alphabet: DNA_T 16, RNA 1 (A/C/G-only poly-A), ambiguous 1
- T→U 5; ambiguous 1; gaps 0; invalid 0; mixed T/U 0
- construct_scope: partial_construct 3; full_construct 1; unknown 14
- length full/core: `<20` 5; `20-25` 2; `26-89` 9; `90-100` 1; `>100` 1
- review candidates 18; known-motif proposals 0; applied trims 0
- Deterministic S2 rerun: byte-identical
- 18 NCBI raw SHA-256 values unchanged; S1 canonical/sidecar unchanged;
  `git ls-files data` empty

### Tests

Synthetic non-biological fixtures only.

Focused:

`tests/data_preparation/test_adapter_ncbi_nuc_s2.py`: **24 passed**.

Shared S2 regressions for completed sources (sequence normalisation,
generic S2 runner, NCBI, ENA, AptaBase, AptamerBase, AptaDB,
RiboAptamer, UTexas, AptaIndex, AptaDiff): **396 passed**.

Hang-prone legacy AptaBase/ENA preparation suites were not run.

### Open questions carried forward

- NCBI Nucleotide S3 technical eligibility and CHECKPOINT-1
  preparation, including unresolved molecule identity, primer /
  cDNA / template / poly-A construct state, possible non-aptamer
  source object, ambiguous N, and length diagnostics.
- NCBI↔ENA accession and T/U-equivalent sequence deduplication remains
  deferred.

### Pipeline status

```text
NCBI Nucleotide S0 complete
NCBI Nucleotide S1 complete
NCBI Nucleotide S2 complete
NCBI Nucleotide S3 has not started
No NCBI Nucleotide CHECKPOINT-1 decision has been made
No NCBI Nucleotide records are yet authorised for global S4
```

## 2026-09-12 — NCBI Nucleotide S3 technical eligibility and CHECKPOINT-1 preparation

**Stage:** Aim 2 / data curation / NCBI Nucleotide (`ncbi_nuc`) S3
technical/source-object eligibility and CHECKPOINT-1 package
preparation only. Human decisions were not entered, applied, or
closed. Global S4 was not prepared.

### What was done

The 18 accepted S2 NCBI Nucleotide records were classified with the
shared eligibility/CHECKPOINT infrastructure plus a source-specific
policy. Molecule routing used S2 `molecule_type`, never
`alphabet_as_reported`. Primer and non-aptamer source objects were
proposed rejects with active review. Unresolved-molecule records
were parked with molecule review before ordinary length/alphabet
disposition. No trim was applied. Target extraction, evidence,
affinity, leakage, NCBI↔ENA deduplication, clustering, and global
S4 were not performed. Human `manual_*` fields remain blank.

### Decisions made

- 18 in / 18 out; 0 dropped; 0 disappearing rows.
- Technically eligible RNA (5): U34759, U37124, U37123, AF083271,
  BD161067. Unknown construct alone did not block them. U34759
  (99 nt) is an upper-boundary retained audit.
- Judgement-dependent proposed rejects (4): FW366678 and FZ422269
  `primer_like`; DJ028182 and QT662269 `non_aptamer_source_object`.
  DJ028182 remains `molecule_type=unknown` despite
  `alphabet_as_reported=RNA`. QT662269 remains DNA/chemistry DNA and
  was not parked as a validated DNA aptamer.
- Unresolved molecule/construct parks (9): HW308409, DI203649,
  DI198507, DI183534, HV507922, DD421991, DI115369, HW065069,
  HV200497. Primary reason `molecule_type_unresolved`. cDNA and
  transcription-template records were not auto-rejected, transcribed,
  or trimmed.
- Secondary technical conditions preserved: `<20` (5), `20–25`
  (2), `90–100` (1), `>100` (1); HV200497 `ambiguous_bases` retained
  unrepaired. Length did not erase molecule/source-object review.
- Applied trims = 0; known-motif proposals 0; group inference
  disabled; `sequence_core == sequence_full` 18/18.
- Target/evidence/leakage/NCBI↔ENA dedup deferred. `target_name_raw`
  empty 18/18. `authorised_for_s4 = 0`.
- CHECKPOINT-1: all 18 rows have a genuine judgement or audit reason.
  Human fields blank. Fail-closed validator:
  `ready_for_application = 0`, `checkpoint_closed = false`.

### Inputs used

- S2 `ncbi_nuc_normalised.csv` (18) and `ncbi_nuc_s2_qc.csv` (18)
- S1 `ncbi_nuc_extracted.csv` / `ncbi_nuc_source_metadata.csv`
- 18 registered `.gb` files under `data/raw/NCBI_nucleotide`
- `config/source_eligibility/ncbi_nuc.json`
- `config/checkpoint_reviews/ncbi_nuc_checkpoint1_recommendations.json`
- Shared AptaDB structured-review schema (`keep`/`drop`/`edit`,
  molecule/chemistry overrides `RNA`/`DNA`)

### Outputs produced

Ignored under `data/interim/checkpoints/ncbi_nuc_cp1/`:

- `ncbi_nuc_s3_canonical.csv`
- `ncbi_nuc_s3_decisions.csv`
- `ncbi_nuc_checkpoint1_review.csv`
- `ncbi_nuc_checkpoint1_local_detail.csv`
- `ncbi_nuc_checkpoint1_reason_counts.csv`
- `rejected_ncbi_nuc.csv`
- `ncbi_nuc_s3_parked.csv`
- `ncbi_nuc_checkpoint1_summary.md`
- `manual_review/` queue, index, empty group review, blank bulk
  confirmation, README, validation snapshot, summary

Tracked policy, adapter, dispatcher, tests, and this log entry.
Nothing under `data/` is tracked.

### Numbers

- `18 = 5 eligible + 9 parked + 4 proposed reject`
- Primary reasons: technically_eligible_rna 5; molecule_type_unresolved 9;
  primer_like 2; non_aptamer_source_object 2
- Review batches: 01 judgement-dependent 4; 02 unresolved molecule 9;
  03 construct/motif 0; 04 length-boundary 1; 05 random-kept 4
- Random-audit pool 5 / sample 5 / shortfall 25 (requested 30; no
  fabricated rows)
- Length-boundary review reasons 3 (U34759 plus two unresolved
  20–25 parks); judgement-required 13; audit-only 5
- Rejection log 4; park sidecar 9
- Deterministic S3 rerun: byte-identical
- Fail-closed: unresolved_manual_decisions 18;
  unresolved_judgement_required 13; ready_for_application 0
- 18 NCBI raw SHA-256 values unchanged; S1 canonical/sidecar unchanged;
  S2 canonical/QC unchanged; `git ls-files data` empty

### Tests

Synthetic non-biological fixtures only.

Focused NCBI S3/CHECKPOINT:

`tests/data_preparation/test_adapter_ncbi_nuc_s3.py`,
`test_ncbi_nuc_s3_classify.py`,
`test_ncbi_nuc_checkpoint1_prepare_review.py`: **25 passed**.

Related completed-source S3/CHECKPOINT regressions (AptaDB, UTexas,
AptaDiff, RiboAptamer, AptaIndex adapters and CHECKPOINT prepare/
structured review): **137 passed**.

Hang-prone legacy AptaBase/ENA preparation suites were not run.

### Open questions carried forward

- NCBI Nucleotide CHECKPOINT-1 human scientific review (molecule
  identity, primer/source-object rejects, cDNA/template/poly-A
  construct questions, ambiguous N, length-boundary/random audits).
- NCBI↔ENA accession and T/U-equivalent sequence deduplication remains
  deferred to later global work.

### Pipeline status

```text
NCBI Nucleotide S0 complete
NCBI Nucleotide S1 complete
NCBI Nucleotide S2 complete
NCBI Nucleotide S3 complete (provisional; CHECKPOINT-1 not closed)
NCBI Nucleotide CHECKPOINT-1 package generated
No NCBI Nucleotide CHECKPOINT-1 decision has been made
No NCBI Nucleotide records are yet authorised for global S4
```

## 2026-09-12 — NCBI Nucleotide CHECKPOINT-1 human review entered (unapplied)

**Stage:** Aim 2 / data curation / NCBI Nucleotide (`ncbi_nuc`)
CHECKPOINT-1 human scientific review entry and fail-closed validation
only. Decisions were not applied. CHECKPOINT-1 remains open. Global S4
was not prepared.

### What was done

Live AptaDB-compatible CHECKPOINT semantics treat
`manual_decision=keep` as confirm/preserve the current proposed route.
It does not force technical acceptance. `drop` would convert a
proposed reject into a human-reviewed exclusion. Machine
`recommended_manual_decision=drop` on primer/non-aptamer rows was
left as guidance and was not copied into `manual_*` fields.

Human review confirmed the current S3 routes for all 18 records.
Judgement-required rows received `manual_decision=keep`. The five
technically eligible RNA records are audit-only and were confirmed
together with `confirm=true` in
`ncbi_nuc_checkpoint1_bulk_audit_confirmation.csv`. No sequence,
molecule, chemistry, target, or trim edits were entered.

The fail-closed validator passed. CHECKPOINT-1 was not applied, not
closed, and not authorised for global S4.

### Decisions made

- 18/18 review decisions resolved; 0 remaining unresolved.
- 13 judgement-required rows: `keep` (preserve current route).
- 5 audit-only rows: bulk `confirm=true`; individual `manual_decision`
  left blank (U34759 length-boundary plus four random-kept RNA).
- 5 technically eligible RNA confirmed/audited: U34759, U37124,
  U37123, AF083271, BD161067.
- 9 unresolved-molecule parks confirmed: HW308409, DI203649,
  DI198507, DI183534, HV507922, DD421991, DI115369, HW065069,
  HV200497.
- 4 source-object rejects confirmed: FW366678 and FZ422269
  `primer_like`; DJ028182 and QT662269 `non_aptamer_source_object`.
- Intended routing unchanged: `5 eligible + 9 park + 4 reject = 18`.
- Edits: sequence corrections 0; molecule overrides 0; chemistry
  overrides 0; target corrections 0; trim approvals 0; trim
  overrides 0.
- No rows were added to compensate for the random-audit shortfall
  of 25.

### Inputs used

- Live CHECKPOINT-1 review package under
  `data/interim/checkpoints/ncbi_nuc_cp1/manual_review/`
- Pre-review S3 review/local-detail artefacts
- `config/checkpoint_reviews/ncbi_nuc_checkpoint1_recommendations.json`
  (guidance only)

### Outputs produced

Human fields written only in ignored `data/` review files plus the
existing open-checkpoint metadata counters:

- `ncbi_nuc_checkpoint1_manual_review.csv` (13 `keep`; 5 audit-only blank)
- `ncbi_nuc_checkpoint1_manual_review_index.csv`
- `ncbi_nuc_checkpoint1_bulk_audit_confirmation.csv` (`confirm=true`)
- `ncbi_nuc_checkpoint1_validation.md` (fail-closed snapshot)
- `config/checkpoint_reviews/ncbi_nuc_checkpoint1_metadata.json`
  (`human_decisions_recorded=18`, `ready_for_application=18`,
  `checkpoint_closed=false`)

No `resolved/` outputs. No tracked final resolutions. No global-S4
handoff. Nothing under `data/` is tracked.

### Numbers

Fail-closed validation:

```text
total_review_records=18
unresolved_manual_decisions=0
unresolved_judgement_required=0
unresolved_constant_groups=0
unresolved_exceptions=0
audit_only_rows=5
audit_only_unconfirmed=0
bulk_audit_confirmed=true
ready_for_application=18
blocking_issues=0
checkpoint_closed=false
s4_started=false
```

Pristine reconstruction differed only in permitted human fields
(`manual_decision`, `manual_notes`, bulk `confirm`). Scientific
machine fields, review order, proposed routes, and source metadata
were unchanged.

### Integrity

- 18 NCBI raw SHA-256 values match the registry
- S1 canonical
  `329f518e94e0813080545fe61d823ad44607ec8a193e14498fc62a91d647e9dc`
- S1 sidecar
  `f1d003f64e7a9619d94b7025838e229b4ec7655fa93f9bda2bf34e2ba0021fe1`
- S2 canonical
  `965cd5a88426c40f54b43afb9fbe7fdb9688c16ff53fad3ef8858ee9ef86824c`
- S2 QC
  `6639c15db9752370f3bd65702d8740776d50e0082aa9724181fdea7aa6729342`
- Pre-review S3 canonical equals S2
- S3 decisions
  `1fc014981832b83be04eab7d5a3cf957f2b66174dd11f1126d440b25b32b9c8d`
- ENA S1/S2 hashes unchanged
- `git ls-files data` empty
- No sequence values entered into tracked config/docs

### Open questions carried forward

- NCBI Nucleotide CHECKPOINT-1 application dry-run of these reviewed
  decisions.
- NCBI↔ENA accession and T/U-equivalent sequence deduplication remains
  deferred to later global work.

### Pipeline status

```text
NCBI Nucleotide S0 complete
NCBI Nucleotide S1 complete
NCBI Nucleotide S2 complete
NCBI Nucleotide S3 complete (provisional; CHECKPOINT-1 not closed)
NCBI Nucleotide CHECKPOINT-1 human review complete
NCBI Nucleotide CHECKPOINT-1 not applied
NCBI Nucleotide CHECKPOINT-1 not closed
No NCBI Nucleotide records are yet authorised for global S4
Global S4 has not been run
```

## 2026-09-12 — NCBI Nucleotide CHECKPOINT-1 application dry-run — unapplied

**Stage:** Aim 2 / data curation / NCBI Nucleotide (`ncbi_nuc`)
CHECKPOINT-1 application **dry-run only**. Decisions were not applied.
CHECKPOINT-1 remains open. Global S4 was not prepared.

### What was done

Human review is fully resolved (`ready_for_application=18`,
`blocking_issues=0`). `manual_decision=keep` preserved the current
proposed route; it did not force technical acceptance. The five
audit-only RNA accepts were bulk-confirmed. Zero sequence, molecule,
chemistry, target, or trim edits were requested or invented.

An NCBI-specific CHECKPOINT-1 apply/dry-run adapter was added to the
shared dispatcher. Dry-run and future actual apply share
`apply_reviewed_record` / `simulate_ncbi_nuc_checkpoint1_application`.
Actual apply without an explicit later authorisation remains refused.
No `resolved/` outputs, tracked resolutions, closure metadata, or
`config/global_s4_sources/ncbi_nuc.json` were written. ENA was not
consulted.

Projected post-review 18-row reconciliation (derived, not targeted):

`5` technically eligible + `9` parked (`molecule_type_unresolved`) +
`4` technical rejects = `18`.

Projected `authorised_for_s4 = 5`. Current authoritative
`authorised_for_s4 = 0`. This is **projected after apply**, not final
authorisation.

Production dry-run was run twice against the frozen review and was
byte-identical for all scientific CSVs. Sequence-free local report:

`data/interim/checkpoints/ncbi_nuc_cp1/dry_run/ncbi_nuc_checkpoint1_dry_run_report.md`

SHA-256:
`077a4c8459071db1292b996ec78655081115ceb86f52e36c47c35df01ea90442`

Actual CHECKPOINT apply was **not** performed. CHECKPOINT-1 is not
closed. NCBI Nucleotide is not authorised for global S4. Global S4
was not run. Raw / S1 / S2 / pre-review S3 / completed-review / ENA
hashes were unchanged. `git ls-files data` remains empty.

### Pipeline stop

```text
CHECKPOINT-1 human review is complete.
NCBI Nucleotide apply/dry-run adapter implemented.
Dry-run complete. Actual apply was not run.
CHECKPOINT-1 is not closed.
S4 remains blocked.
```

## 2026-09-12 — NCBI Nucleotide CHECKPOINT-1 applied and closed

**Stage:** Aim 2 / data curation / NCBI Nucleotide (`ncbi_nuc`)
CHECKPOINT-1 **applied and closed**. Global-S4 handoff was not prepared.
Global S4 was not run. NCBI was not deduplicated against ENA.

### What was done

Human review remained fully resolved (`ready_for_application=18`,
`blocking_issues=0`). Actual apply consumed the accepted S3 state, the
completed human review, and the bulk audit confirmation through the same
`apply_reviewed_record` transformation used by the accepted dry-run.
No sequence, molecule, chemistry, target, or trim edits were applied.
`sequence_core == sequence_full` for 18/18. T→U provenance from S2 is
unchanged. The five source-supported RNA records retain their S2
transcription state.

Final source reconciliation:

`5` technically eligible + `9` parked (`molecule_type_unresolved`) +
`4` technical rejects = `18`.

`authorised_for_s4 = 5`. This means only technical
sequence/molecule/source-object eligibility after NCBI CHECKPOINT-1 and
permission to enter future corpus-wide global S4 preparation. It does
**not** mean protein target confirmed, target canonicalised, `target_name`
resolved, UniProt resolved, target family assigned, evidence threshold
passed, affinity resolved, leakage cleared, deduplicated against ENA,
final corpus included, clustered, balanced, or partitioned.

Authorised ACCESSION values: `U34759`, `U37124`, `U37123`, `AF083271`,
`BD161067`. These are not final corpus inclusions.

Parked ACCESSION values remain unresolved-molecule parks, including
cDNA/template/transcription-template and ambiguous-N diagnostics, with no
computational transcription or T7/core trim.

Rejected ACCESSION values: `FW366678` and `FZ422269` (`primer_like`);
`DJ028182` and `QT662269` (`non_aptamer_source_object`). A-only shared
alphabet classification did not convert `DJ028182` into RNA. `QT662269`
remains experimental DNA / chemistry DNA.

Dry-run/apply byte parity: semantic mismatches = 0, byte mismatches = 0
for all seven scientific CSV payloads. Authoritative rerun was
byte-identical. No `config/global_s4_sources/ncbi_nuc.json` was written.

Genuine pytest (Conda `rnagenesis-mac`): pre-apply NCBI suite
`20 passed / 0 skipped`; after apply-path tests
`22 passed / 0 skipped`. Focused completed-source CHECKPOINT subset
(AptaDiff apply/prepare + NCBI S3 classify): `20 passed / 0 skipped`.

### Integrity

- 18 NCBI raw SHA-256 values match the registry
- S1/S2/pre-review S3/completed-review/ENA hashes unchanged
- `git ls-files data` empty
- Tracked resolutions and metadata are sequence-safe

### Pipeline status

```text
NCBI Nucleotide S0 complete
NCBI Nucleotide S1 complete
NCBI Nucleotide S2 complete
NCBI Nucleotide S3 complete
NCBI Nucleotide CHECKPOINT-1 applied and closed
authorised_for_s4 = 5
global_s4_handoff_prepared = false
global_s4_run = false
```

## 2026-09-14 — NCBI Nucleotide prepared for future global S4

NCBI Nucleotide S1–S3 are complete and CHECKPOINT-1 is already closed.
The five CHECKPOINT-authorised records were materialised from the
authoritative applied checkpoint state as one future corpus-wide
global S4 input. Global S4 was not run. Target canonicalisation,
evidence scoring, leakage exclusion, and NCBI↔ENA deduplication
were not performed.

`authorised_for_s4=true` / inclusion in this handoff means only
technically eligible after NCBI sequence/molecule/source-object
review. It does not mean protein target confirmed, target
canonicalised, UniProt resolved, evidence scored, affinity resolved,
leakage cleared, deduplicated against ENA, final corpus included,
clustered, balanced, or partitioned.

Handoff denominator: 18 source rows → 5 authorised after
CHECKPOINT-1 → 5 handoff rows. Unique `record_id` = 5; unique
`native_id` = 5. Parked (9) and rejected (4) records are excluded.
Authorised ACCESSION values: `U34759`, `U37124`, `U37123`,
`AF083271`, `BD161067`.

The applied five-record canonical subset was joined one-to-one by
`record_id` to the frozen S1 GenBank source-metadata sidecar (5/5;
ACCESSION and VERSION nonempty 5/5). Sidecar fields carried for later
target/evidence interpretation include registered path/basename/file
SHA-256, LOCUS identity/length/molecule/topology/division, ACCESSION,
VERSION, DEFINITION, COMMENT, keywords, source organism/`mol_type`,
FEATURES JSON, and REFERENCES JSON. ORIGIN residues were not copied.
Canonical `accession` remains empty; `ncbi_nuc_accession` is source
provenance only.

Canonical scientific state is unchanged from applied CHECKPOINT-1:
molecule_type RNA = 5; chemistry RNA = 5; T→U retained from S2 = 5;
no trim applied (`no_constants_detected` = 5);
`sequence_core == sequence_full` for 5/5. Canonical `target_name_raw`
remains empty. DEFINITION, COMMENT, FEATURES, and REFERENCE titles were
not parsed into target fields. Evidence scores, affinity, PDB, and
E1–E5 assignments were not produced.

No currently known NCBI↔ENA accession overlaps are present among the
five authorised handoff records. The three known preflight overlaps
(`HW308409`, `DI203649`, `DI183534`) remain parked and are outside the
handoff. NO NCBI↔ENA DEDUPLICATION PERFORMED. Corpus-wide
deduplication remains a later global stage.

`redistribution_status` remains `unknown` for all five records.
Tracked CHECKPOINT scientific counts were not mutated. Handoff
status is recorded in `config/global_s4_sources/ncbi_nuc.json`
(`handoff_status = ready_for_global_s4`, `global_s4_run = false`).

Tracked: `config/global_s4_sources/ncbi_nuc.json`, a reusable
sequence-bearing extra (`ncbi_nuc_origin_residues`) on
`prepare_global_s4_source.py`, and tests. Ignored:
`ncbi_nuc_global_s4_input.csv` (5 rows) and the sequence-free handoff
summary. Deterministic rerun was byte-identical. Raw / S1 / sidecar /
S2 / pre-review S3 / completed review / CHECKPOINT closure / applied /
ENA / other completed-source hashes were unchanged. `git ls-files data`
remains empty.

Genuine pytest (Conda `rnagenesis-mac`):
`tests/data_preparation/test_prepare_global_s4_source.py`
`75 passed / 0 skipped` (15 NCBI-specific + 60 existing
completed-source/generic handoff regressions).

### Pipeline status

```text
NCBI S0 complete
NCBI S1 complete
NCBI S2 complete
NCBI S3 complete
NCBI CHECKPOINT-1 closed
NCBI global-S4 handoff prepared for 5 records
Global S4 NOT run
```

## 2026-09-14 — AptaDB and AptaIndex global-S4 handoffs materialised

AptaDB and AptaIndex CHECKPOINT-1 were already closed. The two missing
positive-authorised source-local global-S4 handoffs were materialised
from the authoritative applied checkpoint state. Global S4 was not
run. Combined 2960-row input construction, target canonicalisation,
UniProt/type/family/Pfam assignment, evidence scoring, affinity
normalisation, leakage, CHECKPOINT-2, cross-source deduplication,
NCBI↔ENA merge, clustering, balancing, and partitioning were not
performed.

`authorised_for_s4=true` / inclusion in these handoffs means only
technical eligibility after each source's sequence/molecule
CHECKPOINT-1. It does not mean protein target confirmed, target
canonicalised, UniProt resolved into canonical fields, evidence scored,
leakage cleared, final corpus included, clustered, balanced, or
partitioned.

### AptaDB

Handoff denominator: 1350 interaction records → 151 authorised
RNA-protein records → 151 handoff rows. Unique `record_id` = 151.
Parked ssDNA (1037), parked RNA non-protein (115), interaction-stream
rejects (47), and 37 unlinked `missing_target` aptamers are excluded.
`redistribution_status` remains `unknown` 151/151.

The applied 151-row subset was joined one-to-one by `record_id` to the
frozen S1 interaction/protein sidecar. Source UniProt
(`aptadb_uniprot_id`) is nonempty 151/151 (81 unique accessions) and
was not copied into canonical `target_uniprot`. Source protein names,
Target chemistry, PubMed ID, Binding Conditions/Buffer, assay text,
and PDB cross-reference are SOURCE extras only. Canonical `pdb_id`,
evidence, and affinity remain empty. Binding Conditions/Buffer was not
interpreted as E3. Physical interaction grain is preserved (148 unique
Apta_index values among 151 rows; no collapse). Canonical
`target_name_raw` retains the applied CHECKPOINT-1 protein-names
value.

AptaDB's closed resolution manifest records `authorised_for_s4` and
`checkpoint1_resolution_status` without a separate `resolved_decision`
column. The shared handoff utility accepts that closed schema when
status is already `approved_for_s4`.

### AptaIndex

The existing tracked config `config/global_s4_sources/aptaindex.json`
was validated against the live handoff contract and left unchanged.
Handoff denominator: 1050 source records → 221 authorised RNA/2F-RNA
records → 221 handoff rows. Unique `record_id` = 221. Parked ssDNA
(614), chemistry-review parks (33), and rejects (182) are excluded.
`redistribution_status=restricted` 221/221. Canonical `target_name_raw`
is populated 221/221 from the applied state.

Source Target / Target Type / Affinity / Reference extras survive
one-to-one from the frozen S1 sidecar. Canonical target/evidence/affinity
fields remain empty. Bare CR characters in AptaIndex source extras
are written with `QUOTE_ALL` so the 221-row file round-trips as 221
records.

### Aggregate (individual handoffs, not concatenated)

Positive-authorised sources = 8. Individual-handoff rows = 2960.
Unique `record_id` = 2960. Cross-source collisions = 0. AptaDiff A/B
remain `ready_zero_authorised` with no sequence-bearing handoff.

Tracked: `config/global_s4_sources/aptadb.json`,
`docs/data_curation/aptadb_global_s4_handoff.md`, shared handoff
utility/tests, and this log. AptaIndex config was not rewritten.
Ignored: `aptadb_global_s4_input.csv` (151 rows) and
`aptaindex_global_s4_input.csv` (221 rows) plus sequence-free summaries.
Deterministic reruns were byte-identical. `git ls-files data` remains
empty.

### Pipeline status

```text
AptaDB CHECKPOINT-1 closed
AptaDB global-S4 handoff prepared for 151 records
AptaIndex CHECKPOINT-1 closed
AptaIndex global-S4 handoff prepared for 221 records
Eight positive-authorised handoffs = 2960 rows
AptaDiff A/B ready_zero_authorised
Global S4 NOT run
```

## 2026-09-14 — Deterministic combined global-S4 input

The eight positive-count source-local handoffs were concatenated into one
row-preserving pre-S4 input. This is not a merge. Records were not joined,
collapsed, or provenance-merged. Global S4 was not run.

Contributing sources and counts:

```text
aptabase       162
utexas         468
aptadb         151
riboaptamer    397
aptaindex      221
ena            675
aptamerbase    881
ncbi_nuc         5
TOTAL         2960
```

Unique `record_id` = 2960. Duplicate / cross-source collisions = 0.
AptaDiff A/B remain `ready_zero_authorised` with no fabricated rows.

Canonical `CORPUS_COLUMNS` occupy the first 47 columns and were copied
exactly. 129 source-specific extras were unioned in configured source
order; extras are empty on rows from other sources. No extra-name
collision remained after the existing ENA aliases. Canonical S4/S5
fields remain empty. `contributing_sources` / `corroboration_count`
remain source-local. AptaIndex `redistribution_status=restricted`
remains 221/221. No licensing filter was applied.

Target extraction, target-dictionary construction, evidence assignment,
affinity canonicalisation, leakage, CHECKPOINT-2, non-protein routing,
cross-source deduplication, NCBI↔ENA merge, clustering, balancing, and
partitioning were not performed.

Tracked: `config/global_s4_combined_input.json`,
`scripts/data_preparation/combine_global_s4_input.py`,
`tests/data_preparation/test_combine_global_s4_input.py`,
`docs/data_curation/global_s4_combined_input.md`, and this log.
Ignored: `data/interim/global_s4/combined_global_s4_input.csv` (2960
rows), the sequence-safe summary, and the sequence-safe manifest.
Deterministic rerun was byte-identical. Source-handoff hashes were
unchanged. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
AptaDiff A/B ready_zero_authorised
Combined pre-S4 input prepared
Global S4 NOT run
```

## 2026-09-14 — Milestone 2 raw target extraction and initial dictionary proposal

Source-supported raw target relationships were extracted from the immutable
2960-row combined pre-S4 input. Proposals were written beside that file, not
into it. Canonical target identity, target type, UniProt, family/Pfam,
evidence, affinity, leakage, CHECKPOINT-2 decisions, and S5 were not applied.

Structured sources (`aptabase` 162, `utexas` 468, `aptadb` 151, `aptaindex`
221, `ena` 675) preserved existing `target_name_raw` exactly (1677/1677).
AptaBase `target_general`, AptaDB chemistry, AptaIndex Target Type, ENA
source target type, and RiboAptamer Type remain priors only.

RiboAptamer (397) used Sequence Name `{target}_{clone}` as the primary
explicit encoding, with narrow Aptamer Name fallbacks. Category/Type were
not substituted for target names. Result: 370 resolved_single, 19
ambiguous, 8 unresolved, 0 resolved_multiple.

AptamerBase (881) used the local RDF path `is_participant_in` →
`has_participant` → English `rdfs:label` on `aptamer_target` nodes.
`aptamerbase_label` was not treated as a target. Affinity/evidence triples
were provenance only. Result: 777 resolved_single, 46 resolved_multiple
(expansion proposed, not applied), 10 ambiguous, 48 unresolved.

NCBI (5): U34759 / U37124 / U37123 / AF083271 resolved_single from
DEFINITION or FEATURE binding phrases; BD161067 ambiguous dual targeting
of IRES and NS3 protease.

Record extraction rows = 2960 with exact `record_id` set match.
Relationship proposals = 3008. Machine dictionary proposals = 818
(`review_status=machine_proposed`). AptaDB source-UniProt seeds were not
copied into canonical `target_uniprot`.

Tracked: `config/global_s4_target_extraction.json`,
`scripts/data_preparation/extract_global_s4_targets.py`, source extraction
adapters, synthetic tests, `docs/data_curation/global_s4_target_extraction.md`,
and this log. Ignored: record/relationship/dictionary CSVs plus sequence-safe
summary and manifest. Deterministic rerun was byte-identical. Combined-input
and eight source-handoff hashes were unchanged. `git ls-files data` remains
empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 raw target extraction + initial dictionary proposal complete
CHECKPOINT-2 NOT started
Global S4 NOT run
```

## 2026-09-14 — Milestone 3 scientific proposals and CHECKPOINT-2 preparation

Machine proposals for target type, UniProt, family/Pfam, evidence,
affinity, leakage, and routing were written beside the immutable 2960-row
combined input. Human CHECKPOINT-2 fields were left blank. Proposals were
not applied. S5 was not run.

### RiboAptamer entry-gate audit

`RA_SEQ_FIRST_UNDERSCORE` was audited against Aptamer Name, Description, and
publication text. Category and Type were not used as corroboration.
Outside biological knowledge was not used to rescue labels.

Convention: Sequence Name `{target}_{clone_or_variant}` encodes the ligand
in the prefix. Aptamer Name is usually `{target} aptamer` or a clone
label. The 364 single-prefix cohort classified as:

- corroborated_target_label: 331
- sequence_name_is_explicit_target_label: 3
- conflicting_source_metadata: 29 → ambiguous (`RA_SEQ_FIRST_UNDERSCORE_CONFLICT`)
- insufficient_support: 1 → unresolved
- clone_or_construct_label_not_target: 0

Unsupported prefixes are no longer deterministic targets. Combined
input remained 2960 rows. Regenerated Milestone-2 counts:

```text
resolved_single   2796
resolved_multiple =   46
ambiguous         =   61
unresolved        =   57
relationships     = 3038
dictionary        =  831
```

RiboAptamer: 338 resolved_single / 50 ambiguous / 9 unresolved.

### Target type

Closed vocabulary only. Source priors are evidence, not canonical truth.
`enzyme` → canonical `protein` plus family clue `enzyme`. Conflicts and
unmapped priors go to CHECKPOINT-2. Unknown is allowed to remain unknown
(UTexas has no structured type).

Dictionary proposals: protein 471, peptide 13, small_molecule 127,
nucleic_acid 12, cell 24, other 4, unknown 180.

### UniProt

U1 AptaDB source seeds: 81. U2 local AptaDB protein table: 8. U3
external lookup was not used (`allow_uniprot_network=false`); unresolved
proteins remain unresolved rather than fuzzy-matched. AptaDB
Prothrombin (`P00734` / `P00735`) and Hemagglutinin (`P03436` / `P03451`)
were not merged. Region/fragment context is preserved; parent UniProt
plus `target_region_or_fragment` requires CHECKPOINT-2.

### Family / Pfam

Family only after type is resolved. Non-protein → `other`. Assigned:
enzyme 17, antibody_immunoglobulin 1, other 168, unknown 645. Pfam 0/831.
Missing Pfam is not an exclusion and is not a CHECKPOINT-2 reason by itself.

### Evidence and affinity

Ladder E1–E5. E1 requires a verified aptamer–target complex; mmCIF URL and
`has_experimentally_determined_structure=true` are not E1. Buffer is not
E3. LOD is not E2. Counts: E1=0, E2=1917, E3=267, E4=404, E5=507.
E4/E5 threshold ambiguities: AptaDB PMID-without-assay (62), ENA
target-specific claim (438), NCBI publication-only (1).

Affinity: 959 scalar values normalised to molar. Ranges, inequalities,
approximate verbal values, missing units, and malformed text were not
converted to invented scalars. Ka was not converted to Kd.

### Leakage and routing

Existing leakage matcher in proposal mode only. Exact / ≥90% / target-alias
matches: 0. No exclusions applied.

Routing preview only: primary_candidate 1394, park_non_protein 476,
park_evidence_e5 17, hold_target_unresolved 573, hold_evidence_ambiguous 500,
leakage 0, no-binding 0.

### CHECKPOINT-2 package

Grouped blank review: 204 target, 107 relationship, 3 evidence, 19
affinity, 0 leakage (333 decisions; 1636 affected records). Validator:
`ready_for_application=false`. CHECKPOINT-2 is prepared, not complete.

Tracked: scientific proposal config/scripts/adapters, CHECKPOINT-2
prepare/validate, synthetic tests, `docs/data_curation/global_s4_scientific_proposals.md`,
and this log. Ignored: proposal CSVs, routing preview, CHECKPOINT-2 CSVs,
summary, and manifest under `data/interim/global_s4/`. Deterministic
rerun was byte-identical. Combined-input hash unchanged.
`git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 human review NOT started
Global S4 NOT run
```

## 2026-09-14 — Milestone 4A.1 CHECKPOINT-2 target-dictionary Batch-1 recording

Human decisions were recorded into the ignored CHECKPOINT-2 target
dictionary review CSV only. Proposals were not applied. Combined input
was not modified. Relationship, evidence, affinity, and leakage review
files were not populated. S5 was not run.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- pre-edit target-review SHA-256:
  `5a402d93903ce9bfe757d454dc29c6d4a0a169c658a576d38b238260f050a4cb`
- pristine copy:
  `data/interim/global_s4/checkpoint2/pristine/checkpoint2_target_dictionary_review.csv`
  (same hash)
- post-edit target-review SHA-256:
  `93ced101f4bed9fa1d3e33a00d36f96c8bc4c341df5bf399aebe3ed722ace7fe`
- only human-review fields changed on 15 authorised rows

### Adopted policies (not bulk-applied)

Recorded under ignored
`data/interim/global_s4/checkpoint2/human_review/batch1_adopted_policies.md`:

1. Equivalent type-prior vocabulary (`Protein`/`Proteins`;
   `Small molecule`/`Small molecules`/`Small Organic`) only where all
   mapped priors agree.
2. Free amino acids are `small_molecule`, not `peptide`.
3. `Enzyme` supports protein + family `enzyme` only when the resolved
   target is an enzyme/protein.
4. Region/fragment/cleaved-form wording is retained; source UniProt may
   be parent-protein metadata; do not silently rename to the whole
   protein.
5. Strict orthographic aliases (case/whitespace/punctuation/hyphen)
   may share a canonical target; abbreviations, gene symbols, and
   distinct components remain individual review.

### Recorded target-dictionary decisions (15)

- `approve_proposal` (13): `C2T0001` Codeine; `C2T0002` bFGF;
  `C2T0003` ALPPL2; `C2T0006` ATP; `C2T0007` L-arginine; `C2T0009` uPA
  cleaved-form / P00749 with policy note; `C2T0010` Pepocin;
  `C2T0011` Human Activated Protein C; `C2T0017` Adenine;
  `C2T0018` L-selectin; `C2T0019` Lysozyme; `C2T0024` Bovine thrombin;
  `C2T0026` Dopamine.
- `override` (2): `C2T0004` hnRNP L → protein / family other;
  `C2T0022` B. subtilis RNase P RNA P5.1 stem-loop → nucleic_acid /
  family other.

Live IDs: `C2T0006` is ATP and `C2T0007` is L-arginine. Both were
authorised as `approve_proposal`.

### Deferred Batch-1 rows (still blank)

`C2T0005`, `C2T0008`, `C2T0012`, `C2T0013`, `C2T0014`, `C2T0015`,
`C2T0016`, `C2T0020`, `C2T0021`, `C2T0023`. These depend on relationship
review.

Remaining 189 target-dictionary rows are blank.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
318 (was 333). Errors: none. Fail-closed blank-package flag is now false
because 15 human fields are populated, as expected.

Tracked: this log and a one-line CHECKPOINT-2 status note in
`docs/data_curation/global_s4_scientific_proposals.md`. Ignored: the
edited target-review CSV, pristine copy, policy note, and recording
manifest. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-14 — Milestone 4B.1 CHECKPOINT-2 relationship Batch-1 recording

Human decisions were recorded into the ignored CHECKPOINT-2
relationship review CSV only. Proposals were not applied. Combined
input was not modified. Target-dictionary, evidence, affinity, and
leakage review files were not populated. S5 was not run.

Decisions were supplied by Laura/ChatGPT on 2026-09-14.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- pre-edit relationship-review SHA-256:
  `5c4d8fbd9c2a924d17c2038b28337767e3485dba4e0cbd9e2e95e6c8a2f88297`
- pristine copy:
  `data/interim/global_s4/checkpoint2/pristine/checkpoint2_relationship_review.csv`
  (same hash)
- post-edit relationship-review SHA-256:
  `be587b255156e14d994e9d25217cd421617794cdffa96457fc6c5cacb6a10dc1`
- target-review SHA-256 unchanged:
  `93ced101f4bed9fa1d3e33a00d36f96c8bc4c341df5bf399aebe3ed722ace7fe`
- only `manual_decision` and `manual_notes` changed on 34 authorised rows
- `manual_relationship_action` left blank

### Recorded relationship decisions (34)

- `confirm_multi_target_expansion` (17): NF-kappaB p50/p65
  (`C2R0001`–`C2R0007`); seven-aminoglycoside panel (`C2R0015`–`C2R0018`);
  Pyr-tobramycin/Tobramycin (`C2R0022`, `C2R0023`); Neu5Ac/Neu5Gc
  (`C2R0027`–`C2R0030`).
- `reject_proposed_relationship` (16): PAI-1/PAI1 (`C2R0044`–`C2R0052`);
  Mitochondria/Mitochondrion (`C2R0071`–`C2R0074`);
  Theophyline/Theophylline (`C2R0058`–`C2R0060`).
- `park_unresolved` (1): NCBI BD161067 (`C2R0057`).

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/batch1_relationship_recording_manifest.json`.

Unlocked target-dictionary rows remain blank for a later milestone.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
284 (was 318). Errors: none.

Tracked: this log and a one-line CHECKPOINT-2 status note in
`docs/data_curation/global_s4_scientific_proposals.md`. Ignored: the
edited relationship-review CSV, pristine copy, and recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-14 — Milestone 4B.2 relationship-unlocked target-dictionary recording

Human decisions were recorded into the ignored CHECKPOINT-2 target
dictionary review CSV only. Proposals were not applied. Combined
input was not modified. Relationship, evidence, affinity, and
leakage review files were not populated. Dictionary rows were not
collapsed. S5 was not run.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- pre-edit target-review SHA-256:
  `93ced101f4bed9fa1d3e33a00d36f96c8bc4c341df5bf399aebe3ed722ace7fe`
- pristine copy unchanged:
  `data/interim/global_s4/checkpoint2/pristine/checkpoint2_target_dictionary_review.csv`
  (`5a402d93903ce9bfe757d454dc29c6d4a0a169c658a576d38b238260f050a4cb`)
- post-edit target-review SHA-256:
  `77a8d355121da3cd264c5ffc704443953fd73d9d24acec5d0d5566f9f91b412f`
- relationship-review SHA-256 unchanged:
  `be587b255156e14d994e9d25217cd421617794cdffa96457fc6c5cacb6a10dc1`
- only human-review fields changed on 18 authorised rows, all `override`

### Recorded target-dictionary decisions (18 override)

- PAI-1 aliases (`C2T0005`, `C2T0016`) → protein / family other /
  Plasminogen activator inhibitor-1.
- NF-kappaB p65 / p50 (`C2T0008`, `C2T0020`) remain distinct
  transcription-factor proteins.
- Seven aminoglycosides (`C2T0014`, `C2T0015`, `C2T0021`, `C2T0035`,
  `C2T0037`, `C2T0042`, `C2T0051`) remain distinct small molecules.
- Pyr tobramycin (`C2T0117`) remains distinct from Tobramycin.
- Neu5Ac / Neu5Gc (`C2T0013`, `C2T0049`) remain distinct sialic acids.
- Mitochondria / Mitochondrion (`C2T0012`, `C2T0048`) → organelle
  type `other`, canonical name Mitochondrion.
- Theophylline / Theophyline (`C2T0023`, `C2T0078`) →
  Theophylline / small_molecule.

IRES (`C2T0174`) and NS3 protease (`C2T0182`) remain blank. Each has
`n_records=1` from `ncbi_nuc` only; BD161067 was parked.

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/batch1_relationship_unlocked_target_recording_manifest.json`.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
266 (was 284). Errors: none. Fail-closed blank-package flag remains
false.

Tracked: this log and a one-line CHECKPOINT-2 status note in
`docs/data_curation/global_s4_scientific_proposals.md`. Ignored: the
edited target-review CSV, pristine copy, and recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-14 — Milestone 4B.4 CHECKPOINT-2 relationship Batch-2 recording

Human decisions were recorded into the ignored CHECKPOINT-2
relationship review CSV only. Proposals were not applied. Combined
input was not modified. Target-dictionary, evidence, affinity, and
leakage review files were not populated. Batch 3 and S5 were not
started.

Decisions were supplied by Laura/ChatGPT on 2026-09-14.

### Reject-semantics safeguard

No `checkpoint2_apply` script exists. Live collapse of
`reject_proposed_relationship` with blank `manual_target_name` /
`manual_relationship_action` keeps `relationship_index=1`. Ten
authorised rows were withheld because that would retain the wrong
relationship: `C2R0107` (Spinach, not DMHBI); `C2R0065`–`C2R0066`
(`3'`, not complete `3',5'-cAMP`); `C2R0067`–`C2R0070` (generic
NS5B, not NS5BΔC55); `C2R0012`–`C2R0014` (L Tyrosine-agarose, not
free Tyrosine). The Tyrosine/agarose corpus-grain policy is documented
in the recording note but was not entered.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- pre-edit relationship-review SHA-256:
  `be587b255156e14d994e9d25217cd421617794cdffa96457fc6c5cacb6a10dc1`
- pristine copy:
  `data/interim/global_s4/checkpoint2/pristine/checkpoint2_relationship_review.csv`
  (`5c4d8fbd9c2a924d17c2038b28337767e3485dba4e0cbd9e2e95e6c8a2f88297`)
- post-edit relationship-review SHA-256:
  `c8b3da755abbf541debfd399f6176b0b82787ee07aaa5a715e35d58177ccfa39`
- target-review SHA-256 unchanged:
  `77a8d355121da3cd264c5ffc704443953fd73d9d24acec5d0d5566f9f91b412f`
- evidence/affinity/leakage hashes unchanged
- only `manual_decision` and `manual_notes` changed on 30 recorded rows
- previous 34 relationship decisions unchanged
- `manual_relationship_action` left blank

### Recorded relationship decisions (30 of 40 authorised)

- `confirm_multi_target_expansion` (11): EF-Tu GDP/GTP
  (`C2R0008`–`C2R0011`); Prothrombin/Thrombin (`C2R0024`, `C2R0025`);
  KRAS v12/WT (`C2R0040`, `C2R0041`); BACE1 CT phospho states
  (`C2R0037`–`C2R0039`).
- `reject_proposed_relationship` (19): IgG (`C2R0085`–`C2R0087`);
  GlnRS (`C2R0061`); AML1 Runt domain (`C2R0090`, `C2R0091`);
  fluorogen ligands except Spinach/DMHBI (`C2R0089`, `C2R0092`–
  `C2R0094`, `C2R0096`, `C2R0099`, `C2R0102`–`C2R0104`);
  organism/context (`C2R0062`, `C2R0075`–`C2R0077`).

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/batch2_relationship_recording_manifest.json`.

Unlocked target-dictionary rows remain blank.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
236 (was 266). Errors: none. Target 33/171; relationship 64/43;
evidence 3; affinity 19; leakage 0.

Tracked: this log and a one-line CHECKPOINT-2 status note in
`docs/data_curation/global_s4_scientific_proposals.md`. Ignored: the
edited relationship-review CSV, pristine copy, and recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107; 10 Batch-2 IDs withheld)
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-14 — Milestone 4B.4A withheld Batch-2 relationship overrides

Human decisions were recorded into the ignored CHECKPOINT-2
relationship review CSV only. Proposals were not applied. Combined
input was not modified. Target-dictionary, evidence, affinity, and
leakage review files were not populated. Batch 3 and S5 were not
started.

### Override-semantics gate

No `checkpoint2_apply` CLI exists. A narrow helper
`apply_relationship_override` now replaces a record's machine
relationship set with one human-specified target via
`apply_relationships` on a single replacement relationship. It does
not retain the original `relationship_index=1` candidate. Synthetic
tests lock that contract. The full CHECKPOINT-2 apply stage was not
created.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- pre-edit relationship-review SHA-256:
  `c8b3da755abbf541debfd399f6176b0b82787ee07aaa5a715e35d58177ccfa39`
- post-edit relationship-review SHA-256:
  `b60dac9e99a6245f3e3682334c67980b528200232c95659ac6356a0096be9d79`
- target-review SHA-256 unchanged:
  `77a8d355121da3cd264c5ffc704443953fd73d9d24acec5d0d5566f9f91b412f`
- evidence/affinity/leakage hashes unchanged
- only `manual_decision`, `manual_target_name`, `manual_target_type`,
  and `manual_notes` changed on the 10 withheld rows
- previous 64 relationship decisions unchanged
- 33 resolved target-dictionary decisions unchanged
- `manual_relationship_action`, UniProt, family, and Pfam left blank

### Recorded relationship overrides (10)

- `C2R0107`: DMHBI / small_molecule (not Spinach)
- `C2R0065`, `C2R0066`: 3',5'-cyclic adenosine monophosphate (cAMP)
- `C2R0067`–`C2R0070`: hepatitis C virus (HCV) NS5BΔC55 protein
- `C2R0012`–`C2R0014`: Tyrosine (agarose remains evidence provenance)

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/batch2_withheld_relationship_override_recording_manifest.json`.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
226 (was 236). Errors: none. Target 33/171; relationship 74/33;
evidence 3; affinity 19; leakage 0.

Tracked: relationship-override helper, synthetic tests, this log, and
a one-line CHECKPOINT-2 status note in
`docs/data_curation/global_s4_scientific_proposals.md`. Ignored: the
edited relationship-review CSV, pristine copy, and recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-14 — Milestone 4B.6 CHECKPOINT-2 relationship Batch-3 recording

Human decisions were recorded into the ignored CHECKPOINT-2
relationship review CSV only. Proposals were not applied. Combined
input was not modified. Target-dictionary, evidence, affinity, and
leakage review files were not populated. S5 was not started.

This closes the CHECKPOINT-2 relationship-review component
(107/107). Eight `park_unresolved` rows are completed human review
outcomes, not missing decisions. Unlocked target-dictionary rows
remain blank.

Decisions were supplied by Laura/ChatGPT on 2026-09-14.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- pre-edit relationship-review SHA-256:
  `b60dac9e99a6245f3e3682334c67980b528200232c95659ac6356a0096be9d79`
- pristine copy unchanged:
  `data/interim/global_s4/checkpoint2/pristine/checkpoint2_relationship_review.csv`
  (`5c4d8fbd9c2a924d17c2038b28337767e3485dba4e0cbd9e2e95e6c8a2f88297`)
- post-edit relationship-review SHA-256:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- target-review SHA-256 unchanged:
  `77a8d355121da3cd264c5ffc704443953fd73d9d24acec5d0d5566f9f91b412f`
- evidence/affinity/leakage hashes unchanged
- machine proposal hashes unchanged
- only `manual_decision` and `manual_notes` changed on 32 rows;
  `C2R0034` also received `manual_target_name` and `manual_target_type`
- previous 74 relationship decisions unchanged
- 33 resolved target-dictionary decisions unchanged
- `manual_relationship_action`, UniProt, family, and Pfam left blank

### Recorded relationship decisions (33 of 33 remaining)

- `confirm_multi_target_expansion` (15): trypanosome stage/strain
  panel (`C2R0019`, `C2R0020`); human/mouse CCL1 (`C2R0021`);
  A549/EGFR (`C2R0026`); zinc-finger p1-8/TFIIIA (`C2R0031`–
  `C2R0033`); PrP ARR/VRQ (`C2R0035`); CPEB3/CPEB4 domains
  (`C2R0036`); GluA2 open/closed (`C2R0042`, `C2R0043`); HIV
  LTR-325/LTR-408 (`C2R0053`); human/mouse IL-17A (`C2R0054`);
  IL-17 A/A, A/F, F/F (`C2R0055`, `C2R0056`).
- `reject_proposed_relationship` (9): Guanine (`C2R0063`);
  Malachite green (`C2R0064`); engineered FKBP (`C2R0078`,
  `C2R0079`); calsenilin (`C2R0083`, `C2R0084`); DFHBI not Fab
  (`C2R0088`); Chili DMHBO+ (`C2R0098`); FAD (`C2R0101`).
- `override` (1): `C2R0034` RVV-X / protein (not VEGF165).
- `park_unresolved` (8): polκ versus polβ (`C2R0080`–`C2R0082`);
  AMPA/kainate (`C2R0095`); OTB-SO3/Fab (`C2R0097`); Beetroot
  ThT/DFHO/DFAME (`C2R0100`); TMR versus pAF (`C2R0105`,
  `C2R0106`).

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/batch3_relationship_recording_manifest.json`.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
193 (was 226). Errors: none. Target 33/171; relationship 107/0;
evidence 3; affinity 19; leakage 0.

Tracked: this log and a one-line CHECKPOINT-2 status note in
`docs/data_curation/global_s4_scientific_proposals.md`. Ignored: the
edited relationship-review CSV, pristine copy, and recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-14 — Milestone 4C.2 CHECKPOINT-2 active target-dictionary Batch-2 recording

Human decisions were recorded into the ignored CHECKPOINT-2 target
dictionary review CSV only. Proposals were not applied. Combined
input was not modified. Relationship, evidence, affinity, and
leakage review files were not populated. Inactive/superseded and
parked-relationship-only target rows were not reviewed. No cAMP
dictionary row was created. S5 was not run.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- pre-edit target-review SHA-256:
  `77a8d355121da3cd264c5ffc704443953fd73d9d24acec5d0d5566f9f91b412f`
- pristine copy unchanged:
  `data/interim/global_s4/checkpoint2/pristine/checkpoint2_target_dictionary_review.csv`
  (`5a402d93903ce9bfe757d454dc29c6d4a0a169c658a576d38b238260f050a4cb`)
- post-edit target-review SHA-256:
  `66f9cff59c667b6c96dddad92bb75cd359e6edc9d748175d145b6efbd42a257a`
- relationship-review SHA-256 unchanged:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence/affinity/leakage hashes unchanged
- machine proposal hashes unchanged
- only human-review fields changed on 40 authorised active rows
- previous 33 target-dictionary decisions unchanged

### Recorded target-dictionary decisions (40)

- `approve_proposal` (31): TFKBP*3R-2G; DFHBI-1T; sheep PrP VRQ/ARR;
  GlnRS; L-Citrulline; prothrombin; p1-8; DFHBI; Guanine; RF1;
  calsenilin; DFHO; Xanthine; ACE; CsrA; CPEB3/CPEB4 domains; DMHBI;
  DMHBO+; FAD; HBC; Malachite green; NBSI; YO3; RVV-X; BACE1 CT
  phospho states; EFTuGDP/GTP; Tyrosine.
- `override` (9 family only): HIV-1 Tat `viral_protein`; HEWL
  `enzyme`; HCV NS5BΔC55 `enzyme`; SARS-CoV N `viral_protein`;
  polκ `enzyme`; TFIIIA `transcription_factor`; Thrombin `enzyme`;
  Human IgG `antibody_immunoglobulin`; Pol II `enzyme`.

PrP ARR/VRQ, prothrombin/thrombin, p1-8/TFIIIA, CPEB3/CPEB4, BACE1
phospho states, and EF-Tu GDP/GTP remain separate identities. polκ,
DFHO, Xanthine, and DMHBI were not globally removed.

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/batch2_target_recording_manifest.json`.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
153 (was 193). Errors: none. Target 73/131; relationship 107/0;
evidence 3; affinity 19; leakage 0.

Tracked: this log and a one-line CHECKPOINT-2 status note in
`docs/data_curation/global_s4_scientific_proposals.md`. Ignored: the
edited target-review CSV, pristine copy, and recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-14 — Milestone 4C.3 target-dictionary review/application semantics

Architecture/semantics only. No additional target identities were
reviewed. The 131 blank target-review rows were not populated.
Evidence, affinity, and CHECKPOINT-2 application were not started.
S5 was not run.

Current target actions could not represent relationship-conditioned
inactivity. Using `park_unresolved` for superseded or parked-only
candidates would treat them as unresolved science. The smallest
correction is one explicit target action,
`exclude_no_active_relationship`, valid only when the reviewed
relationship projection shows zero effective resolved relationships
for that dictionary identity. Machine-derived provenance
distinguishes `superseded_by_relationship_review` from
`parked_relationship_only`. Both are excluded from the resolved
effective dictionary; parked-only provenance remains linked to the
parked relationship records.

Relationship overrides reuse a dictionary identity only on exact
name match. Non-matching names, including
`3',5'-cyclic adenosine monophosphate (cAMP)`, create a deterministic
human-derived identity (`TDH…`) that still requires a target-level
review row. Nearby `cAMP` / `Cyclic adenosine monophosphate` rows are
not reused. Machine proposal tables and live review CSVs were not
mutated.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- target-review SHA-256 unchanged:
  `66f9cff59c667b6c96dddad92bb75cd359e6edc9d748175d145b6efbd42a257a`
- relationship-review SHA-256 unchanged:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence/affinity/leakage hashes unchanged
- machine proposal tables unchanged
- `git ls-files data` remains empty

### Dry-run against accepted live state

- superseded candidates passing the inactivity invariant: 26/26
- parked-only candidates passing: 10/10
- inactive action rejected for active-elsewhere `C2T0025` polκ,
  `C2T0094` DFHO, `C2T0132` Xanthine, `C2T0150` DMHBI
- projected cAMP identity `TDHc92005d63414` with blank proposed
  review row `C2THc92005d63414`; not written

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
153. Errors: none. Target 73/131; relationship 107/0; evidence 3;
affinity 19; leakage 0. The new action is not recorded on any live
row. When later recorded, inactive rows will count as resolved
decisions without entering the effective dictionary.

Tracked: vocabulary, relationship projection, dictionary transform
helper, validator invariant, synthetic tests, scientific docs, this
log. Ignored review CSVs were not edited.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added;
  36 non-active target rows still blank; cAMP review row not added
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-14 — Milestone 4C.4 relationship-inactive target-dictionary recording

Human decisions were recorded into the ignored CHECKPOINT-2 target
dictionary review CSV only. Proposals were not applied. Combined
input was not modified. Relationship, evidence, affinity, and
leakage review files were not populated. The 95 remaining active
blank target rows were not reviewed. No cAMP dictionary or review
row was created. S5 was not run.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- pre-edit target-review SHA-256:
  `66f9cff59c667b6c96dddad92bb75cd359e6edc9d748175d145b6efbd42a257a`
- post-edit target-review SHA-256:
  `2dfc68237ae0a7ac8eb41fa04dd17d89c4195823b350ff9cc00f7a35850df4e1`
- relationship-review SHA-256 unchanged:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence SHA-256 unchanged:
  `dc42db78661d2b68723eb9380093435f6285ad2833556339a366496b67517dc0`
- affinity SHA-256 unchanged:
  `ec7da21e3d7fbe2ba17715b477bf3e6c000a92b04ea8ea303a8020f3e5e732c8`
- leakage SHA-256 unchanged:
  `9adb73232c363ed440dc776c3c8669784e7232ec8e67f7b55bcf4c0627bfacf7`
- machine proposal hashes unchanged
- only `manual_decision` changed on the 36 authorised inactive rows
- previous 73 target-dictionary decisions unchanged

### Recorded target-dictionary decisions (36)

All 36: `exclude_no_active_relationship`. Override fields blank.

- `superseded_by_relationship_review` (26): IgG; GlnRs; AML1
  (RUNX1); Ca2+ binding protein; Engineered FKBP protein_s23; TMR;
  FMN; Riboflavin; VEGF165; Spinach; Broccoli; Clivias; Corn;
  Mango-III; Okra; Pepper; Squash; T. thermophilus; E. coli;
  S. cerevisiae; `3'`; `5'-cyclic adenosine monophosphate (cAMP)`;
  generic NS5B parent; L Tyrosine-agarose; long DMHBI source label;
  Fab.
- `parked_relationship_only` (10): polβ; pAF; TMR; AMPA; kainate
  receptors; DFAME; ThT; IRES; NS3 protease of hepatitis C virus;
  OTB-SO3.

Active-elsewhere controls polκ, DFHO, Xanthine, and DMHBI still
reject the inactive action. Projected cAMP identity
`TDHc92005d63414` remains unwritten.

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/inactive_target_recording_manifest.json`.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
117 (was 153). Errors: none. Target 109/95; relationship 107/0;
evidence 3; affinity 19; leakage 0.

Tracked: this log and a one-line CHECKPOINT-2 status note in
`docs/data_curation/global_s4_scientific_proposals.md`. Ignored: the
edited target-review CSV, package README, and recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added
CHECKPOINT-2 relationship-inactive target-dictionary decisions recorded (109/204; 36 inactive)
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-14 — Milestone 4C.5 human-derived cAMP target identity

The reviewed relationship overrides `C2R0065` and `C2R0066` were
projected into one deterministic human-derived target-dictionary
identity and reviewed at target grain. Combined input was not
modified. Relationship, evidence, affinity, and leakage review files
were not populated. The 95 remaining active blank target rows were
not reviewed. The 36 inactive decisions were not modified. No
CHECKPOINT-2 apply was performed. S5 was not run.

Exact dictionary mapping found no existing machine/reviewed identity
for `3',5'-cyclic adenosine monophosphate (cAMP)`. Nearby `cAMP` and
`Cyclic adenosine monophosphate` identities were not reused. Old
parse fragments `C2T0083` and `C2T0085` remain
`exclude_no_active_relationship`.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- pre-edit target-review SHA-256:
  `2dfc68237ae0a7ac8eb41fa04dd17d89c4195823b350ff9cc00f7a35850df4e1`
- post-edit target-review SHA-256:
  `ee11da4205381e5e757e3e1d121fc5606523b5bc4d94357c870a374daa466a48`
- relationship-review SHA-256 unchanged:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence SHA-256 unchanged:
  `dc42db78661d2b68723eb9380093435f6285ad2833556339a366496b67517dc0`
- affinity SHA-256 unchanged:
  `ec7da21e3d7fbe2ba17715b477bf3e6c000a92b04ea8ea303a8020f3e5e732c8`
- leakage SHA-256 unchanged:
  `9adb73232c363ed440dc776c3c8669784e7232ec8e67f7b55bcf4c0627bfacf7`
- machine proposal hashes unchanged
- previous 109 target-dictionary decisions unchanged
- one new row only: `C2THc92005d63414` / `TDHc92005d63414`

### Recorded target-dictionary decision (1)

`C2THc92005d63414`: `approve_proposal` for
`3',5'-cyclic adenosine monophosphate (cAMP)` (`small_molecule`,
family `other`). Override fields blank. Provenance
`checkpoint2_relationship_override:C2R0065|C2R0066`.

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/human_derived_camp_target_recording_manifest.json`.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
117. Errors: none. Target 110/95/205; relationship 107/0; evidence 3;
affinity 19; leakage 0.

Tracked: human-derived materialisation helper, synthetic
idempotency test, this log, and a one-line CHECKPOINT-2 status note
in `docs/data_curation/global_s4_scientific_proposals.md`. Ignored:
the edited target-review CSV, package README, and recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added
CHECKPOINT-2 relationship-inactive target-dictionary decisions recorded (109/204; 36 inactive)
CHECKPOINT-2 human-derived cAMP target identity materialised and approved (110/205)
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-14 — Milestone 4C.7 CHECKPOINT-2 active target-dictionary Batch-3 recording

Human decisions were recorded into the ignored CHECKPOINT-2 target
dictionary review CSV only. Proposals were not applied. Combined
input was not modified. Relationship, evidence, affinity, and
leakage review files were not populated. The previous 110
target-dictionary decisions, including the 36 inactive exclusions
and the approved human-derived cAMP row, were not modified. S5 was
not run. Batch 4 was not started.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- pre-edit target-review SHA-256:
  `ee11da4205381e5e757e3e1d121fc5606523b5bc4d94357c870a374daa466a48`
- post-edit target-review SHA-256:
  `b34ea79952d26c2f1d0d29a243cf97bc11ab3273eb754f687d04238468c8869d`
- relationship-review SHA-256 unchanged:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence SHA-256 unchanged:
  `dc42db78661d2b68723eb9380093435f6285ad2833556339a366496b67517dc0`
- affinity SHA-256 unchanged:
  `ec7da21e3d7fbe2ba17715b477bf3e6c000a92b04ea8ea303a8020f3e5e732c8`
- leakage SHA-256 unchanged:
  `9adb73232c363ed440dc776c3c8669784e7232ec8e67f7b55bcf4c0627bfacf7`
- machine proposal hashes unchanged
- only human-review fields changed on the 40 authorised active rows
- previous 110 target-dictionary decisions unchanged
- 36 `exclude_no_active_relationship` rows unchanged

### Recorded target-dictionary decisions (40)

- `override` (32): AML1 Runt domain; closed/open GluA2Qflip; IL-2RA;
  IL-6RA; H2N2/H3N2 hemagglutinin seed splits; bovine/human
  prothrombin; human/mouse CCL1; human/mouse IL-17A; IL-17 A/A, A/F
  (two IDs), F/F dimers; mutant/WT KRAS; Human Thrombin; Nogo-66
  Receptor; Apramycin; Kanamycin A; N-terminal histone H3 peptide;
  *E. coli* O157:H7; HIV-1 Rev peptide; Neuropeptide Y; Lys-Arg-
  azobenzene-Arg; A549 cells; EGFR; HIV-1 reverse transcriptase
  spelling pair.
- `approve_proposal` (7): HIV-1 LTR-325/LTR-408; four *T. brucei*
  stage/strain cell identities; Thyroxine.
- `park_unresolved` (1): CypB pancreatic cell line (`C2T0092`).

Apramycin `C2T0038` is exactly `Apramycin` (`small_molecule`), not
an aminoglycoside group. It may share that canonical name with
`C2T0037` / `TD0059` while remaining `TD0060`. Machine UniProt
accessions P03451, P03436, P00735, P00734, P01589, and P08887 were
retained; `manual_uniprot` was left blank.

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/batch3_target_recording_manifest.json`.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
77 (was 117). Errors: none. Target 150/55/205; relationship 107/0;
evidence 3; affinity 19; leakage 0.

Tracked: this log and a one-line CHECKPOINT-2 status note in
`docs/data_curation/global_s4_scientific_proposals.md`. Ignored: the
edited target-review CSV, package README, and recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added
CHECKPOINT-2 relationship-inactive target-dictionary decisions recorded (109/204; 36 inactive)
CHECKPOINT-2 human-derived cAMP target identity materialised and approved (110/205)
CHECKPOINT-2 Batch-3 active target-dictionary decisions recorded (150/205; 1 scientific park)
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-14 — Milestone 4C.9 final active target-dictionary recording

Human decisions were recorded into the ignored CHECKPOINT-2 target
dictionary review CSV only. Proposals were not applied. Combined
input was not modified. Relationship, evidence, affinity, and
leakage review files were not populated. The previous 150
target-dictionary decisions, including the 36 inactive exclusions,
the approved human-derived cAMP row, and the CypB park, were not
modified. S5 was not run. Evidence and affinity review were not
started.

This closes the CHECKPOINT-2 target-dictionary review component
(205/205).

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- pre-edit target-review SHA-256:
  `b34ea79952d26c2f1d0d29a243cf97bc11ab3273eb754f687d04238468c8869d`
- post-edit target-review SHA-256:
  `ce7c64137b0d0764c137d85b606a500db29139c78c2db753ad4efd250a7ed765`
- relationship-review SHA-256 unchanged:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence SHA-256 unchanged:
  `dc42db78661d2b68723eb9380093435f6285ad2833556339a366496b67517dc0`
- affinity SHA-256 unchanged:
  `ec7da21e3d7fbe2ba17715b477bf3e6c000a92b04ea8ea303a8020f3e5e732c8`
- leakage SHA-256 unchanged:
  `9adb73232c363ed440dc776c3c8669784e7232ec8e67f7b55bcf4c0627bfacf7`
- machine proposal hashes unchanged
- only human-review fields changed on the 55 authorised active rows
- previous 150 target-dictionary decisions unchanged
- 36 `exclude_no_active_relationship` rows unchanged
- CypB `C2T0092` remains `park_unresolved`

### Recorded target-dictionary decisions (55)

- `approve_proposal` (15): FMN; Cyanocobalamin; Tetracycline;
  4,4′-Methylenedianiline; moenomycin A; DFHBI chemical name;
  Cyanine dye cy3; Factor VII; Sulforhodamine B; BHDP; African
  Trypanosomes (`cell`); Brain capillary endothelia and parenchyma
  (`other`); Factor IX; FADH; S-Adenosyl-L-homocysteine.
- `override` (36): Angiopoietin-2 pair; PSMA trio; TO1-biotin pair;
  ATP; NF-kappaB p50; ALPPL2; M3 HIV-1 RT pair; whole VEEV and
  influenza A/Panama virions (`organism`); MS2 coat protein; mAb198;
  Rabbit IgG; aniline-substituted sulforhodamine analogue; BoNT/A
  pair; HEF; NF-kappaB p65; hemoglobin beta; CD23; MMP-9; CRP;
  complement C5; HIV-1 gp160; integrin alpha-IIb / alpha-V; IL-8;
  Ebola sGP; Pro-neuropeptide Y; Progonadoliberin-1; LAMTOR5; RACK1.
- `park_unresolved` (4): HCV H77 genome polyprotein; HIV-1 HXB2
  Gag-Pol; MoMLV Gag-Pol; FIV Pol polyprotein.

Canonical-name convergence does not collapse dictionary IDs.
Machine UniProt accessions were retained with `manual_uniprot`
blank. No accession was invented for `C2T0059`.

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/final_target_recording_manifest.json`.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
22 (was 77). Errors: none. Target 205/0/205; relationship 107/0;
evidence 3; affinity 19; leakage 0.

Effective-dictionary dry-run (not applied): 164 resolved entries,
36 inactive exclusions, 5 target scientific parks.

Tracked: this log and a one-line CHECKPOINT-2 status note in
`docs/data_curation/global_s4_scientific_proposals.md`. Ignored: the
edited target-review CSV, package README, and recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added
CHECKPOINT-2 relationship-inactive target-dictionary decisions recorded (109/204; 36 inactive)
CHECKPOINT-2 human-derived cAMP target identity materialised and approved (110/205)
CHECKPOINT-2 Batch-3 active target-dictionary decisions recorded (150/205; 1 scientific park)
CHECKPOINT-2 final active target-dictionary decisions recorded (205/205; 5 scientific parks)
CHECKPOINT-2 target-dictionary review CLOSED
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-15 — Milestone 4D.2 CHECKPOINT-2 evidence recording

Human evidence decisions were recorded into the ignored CHECKPOINT-2
evidence review CSV only. Proposals were not applied. Combined input
was not modified. Target, relationship, affinity, and leakage review
files were not populated. Machine evidence/affinity proposal tables
were not bulk-updated. S5 was not run. Affinity review was not
started.

This closes the CHECKPOINT-2 evidence-review component (3/3).

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- target-review SHA-256 unchanged:
  `ce7c64137b0d0764c137d85b606a500db29139c78c2db753ad4efd250a7ed765`
- relationship-review SHA-256 unchanged:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- pre-edit evidence SHA-256:
  `dc42db78661d2b68723eb9380093435f6285ad2833556339a366496b67517dc0`
- post-edit evidence SHA-256:
  `2116183dc4db64f1939149d68e9416f36db8e9b747b4b1d7fbffca1c3c840718`
- affinity SHA-256 unchanged:
  `ec7da21e3d7fbe2ba17715b477bf3e6c000a92b04ea8ea303a8020f3e5e732c8`
- leakage SHA-256 unchanged:
  `9adb73232c363ed440dc776c3c8669784e7232ec8e67f7b55bcf4c0627bfacf7`
- machine proposal hashes unchanged
- only human-review fields changed on the three evidence rows

### Recorded evidence decisions (3)

- `C2E0001` AptaDB `override_evidence` E4 → E5 (score 1): PMID
  without Assay, binding assay, or selection provenance.
- `C2E0002` ENA `confirm_evidence` E5 (score 1): patent-level
  target-specific aptamer claims; not upgraded to E4.
- `C2E0003` NCBI `confirm_evidence` E5 (score 1): BD161067
  patent/DEFINITION association only. Relationship park `C2R0057`
  remains authoritative.

No review-row split. Nearby non-reviewed ENA E4 assignments were
not reopened.

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/evidence_recording_manifest.json`.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
19 (was 22). Errors: none. Target 205/0; relationship 107/0;
evidence 3/0; affinity 0/19; leakage 0.

Evidence-projection dry-run (not applied): E1=0, E2=1917, E3=267,
E4=342, E5=569. Only AptaDB moved 62 rows E4→E5.

Routing dry-run (not applied): AptaDB 59 `park_evidence_e5` plus 3
already target-parked; ENA 438 `park_evidence_e5`; NCBI relationship
park unchanged.

Tracked: this log and a one-line CHECKPOINT-2 status note in
`docs/data_curation/global_s4_scientific_proposals.md`. Ignored: the
edited evidence-review CSV, package README, and recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added
CHECKPOINT-2 relationship-inactive target-dictionary decisions recorded (109/204; 36 inactive)
CHECKPOINT-2 human-derived cAMP target identity materialised and approved (110/205)
CHECKPOINT-2 Batch-3 active target-dictionary decisions recorded (150/205; 1 scientific park)
CHECKPOINT-2 final active target-dictionary decisions recorded (205/205; 5 scientific parks)
CHECKPOINT-2 target-dictionary review CLOSED
CHECKPOINT-2 evidence decisions recorded (3/3; all E5)
CHECKPOINT-2 evidence review CLOSED
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-15 — Milestone 4D.2 CHECKPOINT-2 evidence recording

Human evidence decisions were recorded into the ignored CHECKPOINT-2
evidence review CSV only. Proposals were not applied. Combined input
was not modified. Target, relationship, affinity, and leakage review
files were not populated. Machine evidence/affinity proposal tables
were not bulk-updated. S5 was not run. Affinity review was not
started.

This closes the CHECKPOINT-2 evidence-review component (3/3).

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- target-review SHA-256 unchanged:
  `ce7c64137b0d0764c137d85b606a500db29139c78c2db753ad4efd250a7ed765`
- relationship-review SHA-256 unchanged:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- pre-edit evidence SHA-256:
  `dc42db78661d2b68723eb9380093435f6285ad2833556339a366496b67517dc0`
- post-edit evidence SHA-256:
  `2116183dc4db64f1939149d68e9416f36db8e9b747b4b1d7fbffca1c3c840718`
- affinity SHA-256 unchanged:
  `ec7da21e3d7fbe2ba17715b477bf3e6c000a92b04ea8ea303a8020f3e5e732c8`
- leakage SHA-256 unchanged:
  `9adb73232c363ed440dc776c3c8669784e7232ec8e67f7b55bcf4c0627bfacf7`
- machine proposal hashes unchanged
- only human-review fields changed on the three evidence rows

### Recorded evidence decisions (3)

- `C2E0001` AptaDB `override_evidence` E4 → E5 (score 1): PMID
  without Assay, binding assay, or selection provenance.
- `C2E0002` ENA `confirm_evidence` E5 (score 1): patent-level
  target-specific aptamer claims; not upgraded to E4.
- `C2E0003` NCBI `confirm_evidence` E5 (score 1): BD161067
  patent/DEFINITION association only. Relationship park `C2R0057`
  remains authoritative.

No review-row split. Nearby non-reviewed ENA E4 assignments were
not reopened.

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/evidence_recording_manifest.json`.

### Validator

`ready_for_application=false`. Unresolved CHECKPOINT-2 decisions:
19 (was 22). Errors: none. Target 205/0; relationship 107/0;
evidence 3/0; affinity 0/19; leakage 0.

Evidence-projection dry-run (not applied): E1=0, E2=1917, E3=267,
E4=342, E5=569. Only AptaDB moved 62 rows E4→E5.

Routing dry-run (not applied): AptaDB 59 `park_evidence_e5` plus 3
already target-parked; ENA 438 `park_evidence_e5`; NCBI relationship
park unchanged.

Tracked: this log and a one-line CHECKPOINT-2 status note in
`docs/data_curation/global_s4_scientific_proposals.md`. Ignored: the
edited evidence-review CSV, package README, and recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added
CHECKPOINT-2 relationship-inactive target-dictionary decisions recorded (109/204; 36 inactive)
CHECKPOINT-2 human-derived cAMP target identity materialised and approved (110/205)
CHECKPOINT-2 Batch-3 active target-dictionary decisions recorded (150/205; 1 scientific park)
CHECKPOINT-2 final active target-dictionary decisions recorded (205/205; 5 scientific parks)
CHECKPOINT-2 target-dictionary review CLOSED
CHECKPOINT-2 evidence decisions recorded (3/3; all E5)
CHECKPOINT-2 evidence review CLOSED
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```



## 2026-09-15 — Milestone 4E.2 affinity review semantics

Affinity review gained first-class outcomes, per-record transforms,
qualifier/raw/non-affinity representation, a projection helper, and
an evidence-affinity consistency check. The 19 live affinity decisions
were not recorded. Combined input, target/relationship/evidence review,
and machine proposal tables were not modified. CHECKPOINT-2 was not
applied. S5 was not run.

The previous shared vocabulary could not express retain-raw-without
scalar, non-affinity, qualifier/range, or per-record scalars under one
grouped row. Target `override` is not used for affinity.

### Integrity (unchanged)

- combined SHA-256:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- target-review SHA-256:
  `ce7c64137b0d0764c137d85b606a500db29139c78c2db753ad4efd250a7ed765`
- relationship-review SHA-256:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence-review SHA-256:
  `2116183dc4db64f1939149d68e9416f36db8e9b747b4b1d7fbffca1c3c840718`
- affinity-review SHA-256:
  `ec7da21e3d7fbe2ba17715b477bf3e6c000a92b04ea8ea303a8020f3e5e732c8`

Affinity remains 0 resolved / 19 blank; all affinity human fields
blank.

### Semantics (not recorded)

Affinity-only completed outcomes: `confirm_affinity_scalar`,
`retain_affinity_raw`, `exclude_non_affinity`, plus existing
`park_unresolved`. Canonical scalar columns stay blank unless a
per-record exact molar value is safe. No invented midpoint/nM.

Deterministic parser repairs (not re-proposed): scientific-notation
hyphen, glued units, uncertainty after unit, `Kd: NA`.

Live dry-run split: 19 rows → 31 proposed subgroups. Unsplit 13
rows. Split: C2A0004, C2A0009, C2A0013, C2A0014, C2A0016, C2A0018.
Projected record classes: exact scalar 11; retain-raw 741;
non-affinity 114; park 0. Evidence-affinity inconsistency flags: 49
records. These block application until reconciled and do not mutate
evidence.

Validator: `ready_for_application=false`. Unresolved 19. Errors: none.

Tracked: affinity helper/validator/parser tests, this log, and
`docs/data_curation/checkpoint2_affinity_review_semantics.md`.
Ignored live review CSVs were not edited. `git ls-files data`
remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added
CHECKPOINT-2 relationship-inactive target-dictionary decisions recorded (109/204; 36 inactive)
CHECKPOINT-2 human-derived cAMP target identity materialised and approved (110/205)
CHECKPOINT-2 Batch-3 active target-dictionary decisions recorded (150/205; 1 scientific park)
CHECKPOINT-2 final active target-dictionary decisions recorded (205/205; 5 scientific parks)
CHECKPOINT-2 target-dictionary review CLOSED
CHECKPOINT-2 evidence decisions recorded (3/3; all E5)
CHECKPOINT-2 evidence review CLOSED
CHECKPOINT-2 affinity semantics added; 19 affinity rows still blank
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-16 — Milestone 4E.3 controlled affinity review split

The 19-row affinity review was materialised into 31 scientifically
coherent rows. Human affinity fields remain blank. Combined input,
target/relationship/evidence review, and machine proposal tables were
not modified. CHECKPOINT-2 was not applied. S5 was not run.

The 19→31 increase is corrected review grain, not regression: six
heterogeneous groups cannot share one human rule.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- target-review SHA-256 unchanged:
  `ce7c64137b0d0764c137d85b606a500db29139c78c2db753ad4efd250a7ed765`
- relationship-review SHA-256 unchanged:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence-review SHA-256 unchanged:
  `2116183dc4db64f1939149d68e9416f36db8e9b747b4b1d7fbffca1c3c840718`
- pre-split affinity SHA-256:
  `ec7da21e3d7fbe2ba17715b477bf3e6c000a92b04ea8ea303a8020f3e5e732c8`
- pristine copy:
  `data/interim/global_s4/checkpoint2/pristine/checkpoint2_affinity_review_pre_split.csv`
  (same hash)
- post-split affinity SHA-256:
  `518f8f262b0133cc5938c0b3ce0166ba200102abd9b59790e6e9122fb39cec25`
- leakage and machine proposal hashes unchanged

### Split map

Unsplit (13): C2A0001, C2A0002, C2A0003, C2A0005, C2A0006, C2A0007,
C2A0008, C2A0010, C2A0011, C2A0012, C2A0015, C2A0017, C2A0019.

Split parents are not reused as children:

- C2A0004 → C2A0004A assay caption (60) / C2A0004B mentioned foreign Kd (25)
- C2A0009 → C2A0009A list (2) / C2A0009B true range (2)
- C2A0013 → C2A0013A inequality (4) / C2A0013B multiple (1) / C2A0013C uncertainty (9)
- C2A0014 → C2A0014A approximate (5) / C2A0014B binding % (2) / C2A0014C range (1)
- C2A0016 → C2A0016A central±unc (2) / C2A0016B glued nM (3) / C2A0016C NA (2) / C2A0016D multiple (35) / C2A0016E rate (2)
- C2A0018 → C2A0018A multiple (6) / C2A0018B `2e-5 M` (2) / C2A0018C true range (10)

Seven C2A0004 records on parked targets remain in A/B. `riboaptamer:481`
remains in C2A0016D; relationship park is authoritative.

### Projected outcome classes (machine metadata only)

Review rows: exact-scalar 4; retain-raw 15; non-affinity 12; park 0.
Records: exact-scalar 11; retain-raw 741; non-affinity 114; park 0.
No `manual_decision` was written.

Evidence-affinity inconsistency flags remain 49 unique records and
block application: 40 machine-E2 / projected non-affinity; 9 machine-E4
but projected exact scalar. Evidence review was not reopened.

### Validator

`ready_for_application=false`. Unresolved 31 (was 19). Errors: none.
Target 205/0; relationship 107/0; evidence 3/0; affinity 0/31.

Tracked: affinity split/materialisation helper and tests, this log,
semantics note, scientific-proposals status line. Ignored: 31-row
affinity CSV, pristine 19-row copy, package README, materialisation
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added
CHECKPOINT-2 relationship-inactive target-dictionary decisions recorded (109/204; 36 inactive)
CHECKPOINT-2 human-derived cAMP target identity materialised and approved (110/205)
CHECKPOINT-2 Batch-3 active target-dictionary decisions recorded (150/205; 1 scientific park)
CHECKPOINT-2 final active target-dictionary decisions recorded (205/205; 5 scientific parks)
CHECKPOINT-2 target-dictionary review CLOSED
CHECKPOINT-2 evidence decisions recorded (3/3; all E5)
CHECKPOINT-2 evidence review CLOSED
CHECKPOINT-2 affinity review split 19 -> 31; all affinity human fields blank
CHECKPOINT-2 not applied; not ready for application
Global S4 NOT run
```

## 2026-09-16 — Milestone 4E.4 affinity decisions recorded

Recorded exactly 31 authorised affinity-review decisions into the
ignored 31-row package. Target, relationship, and evidence review were
not modified. Machine proposal tables and combined input were not
modified. CHECKPOINT-2 was not applied. S5 was not run.

### Integrity

- combined SHA-256 unchanged:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- target-review SHA-256 unchanged:
  `ce7c64137b0d0764c137d85b606a500db29139c78c2db753ad4efd250a7ed765`
- relationship-review SHA-256 unchanged:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence-review SHA-256 unchanged:
  `2116183dc4db64f1939149d68e9416f36db8e9b747b4b1d7fbffca1c3c840718`
- pre-recording affinity SHA-256:
  `518f8f262b0133cc5938c0b3ce0166ba200102abd9b59790e6e9122fb39cec25`
- pristine copy:
  `data/interim/global_s4/checkpoint2/pristine/checkpoint2_affinity_review_pre_recording.csv`
  (same hash)
- post-recording affinity SHA-256:
  `08dc960c0c8626f89a4bfdc36c17b029ebbb48d830d12a040c19c6c45a4597f4`

Changed affinity columns are human fields only:
`manual_decision`, `manual_affinity_type`,
`manual_affinity_transform_rule`, `manual_affinity_qualifier`,
`manual_affinity_range_status`, `manual_affinity_non_affinity_reason`,
`manual_notes`.

### Decision counts

```text
confirm_affinity_scalar =  4
retain_affinity_raw     = 15
exclude_non_affinity    = 12
park_unresolved         =  0
--------------------------------
total                   = 31
```

Record grain: exact scalar 11; retain-raw 741; non-affinity 114;
affinity parks 0. No group-level numeric scalar was stored.

Evidence-affinity inconsistency flags remain 49 unique records and
continue to block application: 40 machine-E2 / reviewed non-affinity
(C2A0004A 9, C2A0004B 25, C2A0010 3, C2A0014B 2, C2A0019 1);
9 machine-E4 / reviewed exact quantitative affinity
(C2A0002 4, C2A0016A 2, C2A0016B 3). C2A0018B is exact + machine E2
and is consistent.

### Validator

`ready_for_application=false`. Unresolved 0. Errors: none.
Target 205/0; relationship 107/0; evidence 3/0; affinity 31/0.
Application blocked by the 49 evidence-affinity inconsistencies.

Tracked: affinity recording helper and tests, this log, semantics
note, scientific-proposals status line. Ignored: recorded 31-row
affinity CSV, pristine blank 31-row copy, package README, recording
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added
CHECKPOINT-2 relationship-inactive target-dictionary decisions recorded (109/204; 36 inactive)
CHECKPOINT-2 human-derived cAMP target identity materialised and approved (110/205)
CHECKPOINT-2 Batch-3 active target-dictionary decisions recorded (150/205; 1 scientific park)
CHECKPOINT-2 final active target-dictionary decisions recorded (205/205; 5 scientific parks)
CHECKPOINT-2 target-dictionary review CLOSED
CHECKPOINT-2 evidence decisions recorded (3/3; all E5)
CHECKPOINT-2 evidence review CLOSED
CHECKPOINT-2 affinity review split 19 -> 31; all affinity human fields blank
CHECKPOINT-2 affinity decisions recorded (31/31; 0 parks)
CHECKPOINT-2 not applied; not ready for application (49 evidence-affinity flags)
Global S4 NOT run
```

## 2026-09-16 — Milestone 4F.1 evidence–affinity consistency review support

Read-only reconciliation of the 49 evidence-affinity inconsistency
records. No review CSV, proposal table, or combined input was modified.
Supplemental evidence rows were not materialised. CHECKPOINT-2 was not
applied. S5 was not run.

### Integrity (unchanged except affinity already recorded in 4E.4)

- combined SHA-256:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- target-review SHA-256:
  `ce7c64137b0d0764c137d85b606a500db29139c78c2db753ad4efd250a7ed765`
- relationship-review SHA-256:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence-review SHA-256:
  `2116183dc4db64f1939149d68e9416f36db8e9b747b4b1d7fbffca1c3c840718`
- affinity-review SHA-256:
  `08dc960c0c8626f89a4bfdc36c17b029ebbb48d830d12a040c19c6c45a4597f4`

Target 205/205; relationship 107/107; evidence 3/3; affinity 31/31.
Unresolved human decisions: 0. Unique evidence-affinity flags: 49.
`ready_for_application=false`. Closed E5 rows C2E0001–C2E0003 do not
overlap these 49 records.

### Recommended corrected evidence (not recorded)

False-positive machine E2 (40): 30 remain E3 after removing the invalid
quantitative signal; 10 fall to E5 (6 AptaDB non-binding remainder,
3 AptamerBase no-binding without SELEX, 1 UTexas TBD/patent-only).
False-negative machine E4 (9): all recommended E2 (4 AptaBase recovered
µM Kd; 5 RiboAptamer recovered exact Kd). Projected 49-only distribution:
9 E2, 30 E3, 0 E4, 10 E5.

Design (not materialised): nine supplemental consistency-review rows
`C2EC0001`–`C2EC0009` in a new package file, leaving the closed 3-row
evidence CSV untouched. Projection precedence: supplemental correction,
then C2E0001–C2E0003, then machine evidence.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added
CHECKPOINT-2 relationship-inactive target-dictionary decisions recorded (109/204; 36 inactive)
CHECKPOINT-2 human-derived cAMP target identity materialised and approved (110/205)
CHECKPOINT-2 Batch-3 active target-dictionary decisions recorded (150/205; 1 scientific park)
CHECKPOINT-2 final active target-dictionary decisions recorded (205/205; 5 scientific parks)
CHECKPOINT-2 target-dictionary review CLOSED
CHECKPOINT-2 evidence decisions recorded (3/3; all E5)
CHECKPOINT-2 evidence review CLOSED
CHECKPOINT-2 affinity review split 19 -> 31; all affinity human fields blank
CHECKPOINT-2 affinity decisions recorded (31/31; 0 parks)
CHECKPOINT-2 evidence-affinity consistency analysed (49 flags; not recorded)
CHECKPOINT-2 not applied; not ready for application (49 evidence-affinity flags)
Global S4 NOT run
```

## 2026-09-16 — Milestone 4F.2 blank supplemental evidence-consistency review

Materialised a blank 9-row supplemental evidence-consistency package
`C2EC0001`–`C2EC0009` in a new ignored file. Human C2EC fields were
not recorded. The frozen 3-row evidence review was not modified.
Affinity review, target/relationship review, combined input, and
machine proposal tables were unchanged. CHECKPOINT-2 was not
applied. S5 was not run.

### Integrity (unchanged)

- combined SHA-256:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- target-review SHA-256:
  `ce7c64137b0d0764c137d85b606a500db29139c78c2db753ad4efd250a7ed765`
- relationship-review SHA-256:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence-review SHA-256:
  `2116183dc4db64f1939149d68e9416f36db8e9b747b4b1d7fbffca1c3c840718`
- affinity-review SHA-256:
  `08dc960c0c8626f89a4bfdc36c17b029ebbb48d830d12a040c19c6c45a4597f4`

Target 205/205; relationship 107/107; evidence 3/3; affinity 31/31.
Supplemental evidence consistency: resolved 0 / blank 9.
Unresolved human decisions: 9. Unique evidence-affinity flags: 49.
`ready_for_application=false`. Closed E5 rows C2E0001–C2E0003 do not
overlap these 49 records.

### Ordering

Independent of CSV row order: AptaBase C2A0002, AptaDB C2A0004A,
AptaDB C2A0004B E3 then E5, AptamerBase C2A0010, RiboAptamer C2A0014B,
C2A0016A, C2A0016B, UTexas C2A0019.

Supplemental SHA-256:
`0b16b918c6963068ee8334e5d72dc64f82cb0663c1bd091d61afe18a94fdb3d9`

Tracked: evidence-consistency adapter/CLI/tests, validator/flag
precedence, this log, scientific-proposals status, semantics note.
Ignored: 9-row supplemental CSV, package README update, materialisation
manifest/note. `git ls-files data` remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added
CHECKPOINT-2 relationship-inactive target-dictionary decisions recorded (109/204; 36 inactive)
CHECKPOINT-2 human-derived cAMP target identity materialised and approved (110/205)
CHECKPOINT-2 Batch-3 active target-dictionary decisions recorded (150/205; 1 scientific park)
CHECKPOINT-2 final active target-dictionary decisions recorded (205/205; 5 scientific parks)
CHECKPOINT-2 target-dictionary review CLOSED
CHECKPOINT-2 evidence decisions recorded (3/3; all E5)
CHECKPOINT-2 evidence review CLOSED
CHECKPOINT-2 affinity review split 19 -> 31; all affinity human fields blank
CHECKPOINT-2 affinity decisions recorded (31/31; 0 parks)
CHECKPOINT-2 evidence-affinity consistency analysed (49 flags; not recorded)
CHECKPOINT-2 blank supplemental evidence-consistency review materialised (0/9)
CHECKPOINT-2 not applied; not ready for application (49 evidence-affinity flags)
Global S4 NOT run
```

## 2026-09-16 — Milestone 4F.3 recorded supplemental evidence-consistency decisions

Recorded all nine authorised C2EC decisions as `override_evidence`
into the ignored supplemental review CSV. Human fields on the
original 3-row evidence review, affinity review, target review, and
relationship review were not modified. Combined input and machine
proposal tables were unchanged. CHECKPOINT-2 was not applied.
S5 was not run.

The blank 9-row package was copied to
`pristine/checkpoint2_evidence_consistency_review_pre_recording.csv`
before recording.

### Integrity

- combined SHA-256:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- target-review SHA-256:
  `ce7c64137b0d0764c137d85b606a500db29139c78c2db753ad4efd250a7ed765`
- relationship-review SHA-256:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence-review SHA-256:
  `2116183dc4db64f1939149d68e9416f36db8e9b747b4b1d7fbffca1c3c840718`
- affinity-review SHA-256:
  `08dc960c0c8626f89a4bfdc36c17b029ebbb48d830d12a040c19c6c45a4597f4`
- leakage-review SHA-256:
  `9adb73232c363ed440dc776c3c8669784e7232ec8e67f7b55bcf4c0627bfacf7`
- machine proposal hashes unchanged
- only human fields changed on the nine supplemental rows

Pre-recording / pristine supplemental SHA-256:
`0b16b918c6963068ee8334e5d72dc64f82cb0663c1bd091d61afe18a94fdb3d9`

Post-recording supplemental SHA-256:
`5775cf8682f2423f61fd6c412a4406bb62f3e23164a56e92280ccfed91edd3db`

Target 205/205; relationship 107/107; evidence 3/3; affinity 31/31;
evidence consistency 9/9. Unresolved human decisions: 0.
Evidence-affinity flags: 49 → 0. Errors: none.
`ready_for_application=true`. CHECKPOINT-2 was not applied.

### Recorded decisions (9)

```text
C2EC0001 |  4 | E2 | 4
C2EC0002 |  9 | E3 | 3
C2EC0003 | 19 | E3 | 3
C2EC0004 |  6 | E5 | 1
C2EC0005 |  3 | E5 | 1
C2EC0006 |  2 | E3 | 3
C2EC0007 |  2 | E2 | 4
C2EC0008 |  3 | E2 | 4
C2EC0009 |  1 | E5 | 1
```

Record outcomes: 9 E2, 30 E3, 0 E4, 10 E5.
Transitions: E4→E2 = 9; E2→E3 = 30; E2→E5 = 10.
C2EC0005 does not encode no-binding as zero Kd.

### Routing dry-run (not applied)

9 E2 and 30 E3 records pass the evidence threshold. 10 E5 records
fail unless already parked. New evidence parks from otherwise
protein-primary context: `aptadb:132`–`136`, `aptadb:1068`.
Independent parks remain authoritative (AptaBase peptides,
`aptadb:383`–`386` target-parked, AptamerBase target-held,
RiboAptamer cell, UTexas target-unresolved).

Recording manifest:
`data/interim/global_s4/checkpoint2/human_review/evidence_consistency_recording_manifest.json`.

Tracked: evidence-consistency recording CLI/helpers/tests, this
log, scientific-proposals status, architecture/semantics notes.
Ignored: recorded 9-row supplemental CSV, pristine copy, package
README update, recording manifest/note. `git ls-files data`
remains empty.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 Batch-1 target-dictionary decisions recorded (15/204)
CHECKPOINT-2 Batch-1 relationship decisions recorded (34/107)
CHECKPOINT-2 relationship-unlocked target-dictionary decisions recorded (33/204)
CHECKPOINT-2 Batch-2 relationship decisions recorded (64/107)
CHECKPOINT-2 Batch-2 withheld relationship overrides recorded (74/107)
CHECKPOINT-2 Batch-3 relationship decisions recorded (107/107; 8 parked)
CHECKPOINT-2 Batch-2 active target-dictionary decisions recorded (73/204)
CHECKPOINT-2 inactive-target and override-identity semantics added
CHECKPOINT-2 relationship-inactive target-dictionary decisions recorded (109/204; 36 inactive)
CHECKPOINT-2 human-derived cAMP target identity materialised and approved (110/205)
CHECKPOINT-2 Batch-3 active target-dictionary decisions recorded (150/205; 1 scientific park)
CHECKPOINT-2 final active target-dictionary decisions recorded (205/205; 5 scientific parks)
CHECKPOINT-2 target-dictionary review CLOSED
CHECKPOINT-2 evidence decisions recorded (3/3; all E5)
CHECKPOINT-2 evidence review CLOSED
CHECKPOINT-2 affinity review split 19 -> 31; all affinity human fields blank
CHECKPOINT-2 affinity decisions recorded (31/31; 0 parks)
CHECKPOINT-2 evidence-affinity consistency analysed (49 flags; not recorded)
CHECKPOINT-2 blank supplemental evidence-consistency review materialised (0/9)
CHECKPOINT-2 supplemental evidence-consistency decisions recorded (9/9)
CHECKPOINT-2 not applied; ready for application (0 evidence-affinity flags)
Global S4 NOT run
```

## 2026-09-16 — Milestone 5 CHECKPOINT-2 applied; global S4 complete

Applied the completed CHECKPOINT-2 package to the 2960-row combined
input and wrote the reviewed global-S4 relationship corpus. Combined
input and all review CSVs were not modified. S5 was not started: no
dedup, clustering, balancing, FT/REF/EVAL, or splits.

### Integrity (unchanged)

- branch `main` HEAD / origin/main:
  `08e37ce6cacdb93e3c0de2dbc4a15389cb720b19`
- combined SHA-256:
  `24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0`
- target-review SHA-256:
  `ce7c64137b0d0764c137d85b606a500db29139c78c2db753ad4efd250a7ed765`
- relationship-review SHA-256:
  `a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9`
- evidence-review SHA-256:
  `2116183dc4db64f1939149d68e9416f36db8e9b747b4b1d7fbffca1c3c840718`
- affinity-review SHA-256:
  `08dc960c0c8626f89a4bfdc36c17b029ebbb48d830d12a040c19c6c45a4597f4`
- evidence-consistency SHA-256:
  `5775cf8682f2423f61fd6c412a4406bb62f3e23164a56e92280ccfed91edd3db`
- leakage-review SHA-256:
  `9adb73232c363ed440dc776c3c8669784e7232ec8e67f7b55bcf4c0627bfacf7`
- `git ls-files data` remains empty

Validator before application: target 205/205; relationship 107/107;
evidence 3/3; affinity 31/31; evidence consistency 9/9. Unresolved 0.
Evidence-affinity flags 0. Errors none. `ready_for_application=true`.

### Application

Existing projection helpers were composed; science was not
reimplemented. Output grain is one reviewed `(sequence,target)`
relationship. Combined extras remain on the immutable combined file
and are joined by `record_id`.

Relationship projection: 2960 source records → 2963 effective
relationship rows including 12 target-park rows, plus 19
relationship-parked rows from 9 records, 44 reject-survivors, 11
overrides, 43 confirmed expansions (112 expanded rows). Target-park
and relationship-park rows are excluded from the active corpus file.

Target dictionary: 205 decisions; 36 inactive exclusions; 5 scientific
parks; **164 reviewed resolved identities** including
`TDHc92005d63414` once (`3',5'-cyclic adenosine monophosphate (cAMP)`,
`small_molecule`, `other`). 627 unreviewed deterministic identities
are carried forward so every active relationship has metadata. Equal
canonical names were not merged. Documented extra versus 164-only: the
active dictionary has 791 entries (164 reviewed + 627 unreviewed).

Evidence record grain after precedence
(supplemental → original C2E → machine):

```text
E1 =    0
E2 = 1762
E3 =  296
E4 =  324
E5 =  578
--------------
     2960
```

Supplemental 49-record corrections: 9 E2, 30 E3, 10 E5. Original C2E
membership 501 records, all E5. Evidence-affinity flags after
application: 0.

Affinity record grain: exact scalar 11; retain-raw 741; non-affinity
114; affinity park 0. Canonical molar also kept for 920 unreviewed
already-normalised machine scalars. Representative reviewed scalars:
AptaBase µM Kd `1.9e-06` / `1.8e-05` / `2.5e-06`; glued nM `5e-08` /
`2e-08` / `5.27e-08`; `2 x 10^-5 M` → `2e-05`; central±unc
`7.82e-08` / `1.012e-07`. LOD / binding % / no-binding / rates /
captions / TBD / N/A did not enter canonical affinity.

Leakage recomputed on reviewed relationships: 0 exclusions.

### Routing

Source-record grain (2960):

```text
primary_candidate            = 1428
park_non_protein             =  541
park_evidence_e5             =  521
hold_target_unresolved       =  389
unresolved_no_relationship   =   57
target_parked                =   12
relationship_parked          =    9
reject_no_binding_evidence   =    3
leakage_excluded             =    0
--------------------------------
                             2960
```

Reviewed relationship grain (2951 active rows):

```text
primary_candidate            = 1460
park_non_protein             =  578
park_evidence_e5             =  521
hold_target_unresolved       =  389
reject_no_binding_evidence   =    3
leakage_exclusion_proposed   =    0
```

Holds are unknown target type. Five target parks (CypB pancreatic cell
line; HCV H77 genome polyprotein; HIV-1 HXB2 Gag-Pol; MoMLV Gag-Pol;
FIV Pol) cover 12 records. Nine relationship parks remain
authoritative, including `ncbi_nuc:BD161067`. Three AptamerBase no-
binding records were rejected, not primary.

### Validation

Every original record has a map outcome. No active relationship
references an inactive or scientifically parked target. E5 is never
primary. Application rerun hashes identical. Input/review hashes
unchanged.

S5 diagnostic only (not resolved): 461 duplicate `sequence_core`
values (1199 rows); 259 exact `(sequence_core, canonical_target_name)`
duplicate groups (570 rows); 386 cross-source duplicate cores; 0
NCBI/ENA overlapping cores.

### Outputs (ignored `data/`)

- `global_s4_reviewed_relationships.csv`
  `dc0afb900231b2a4ef821f906bf6f5dab3c9329a49e5e9090c2aba2c818bb502`
- `global_s4_reviewed_target_dictionary.csv`
  `e7234d9a9308dd899cbb3f801ff20ba05b2960071ede98812c6109db0f21b5ec`
- `global_s4_record_relationship_map.csv`
  `632df4888f50d60cf376e8dee506c4cbde2044914f5158d9af26215de55b999b`
- `global_s4_parked_excluded_audit.csv`
  `98ae60ac81c585b44deb229d93e8601271d71512bffbf62cb8113ff0d7e23bc7`
- `global_s4_routing_summary.csv`
  `46bc0c91a121f1737f3816ec4b16fef4630b388310c9599171cf054b17e74635`

Tracked: apply adapter/CLI/config/tests, routing kwargs, this log,
`docs/data_curation/global_s4_checkpoint2_application.md`. Not
committed in this milestone.

### Pipeline status

```text
Eight positive-authorised handoffs concatenated = 2960 rows
Milestone 2 regenerated after RiboAptamer entry-gate audit
Milestone 3 scientific proposals + blank CHECKPOINT-2 package complete
CHECKPOINT-2 target-dictionary review CLOSED (205/205; 5 scientific parks)
CHECKPOINT-2 relationship review CLOSED (107/107; 9 parked)
CHECKPOINT-2 evidence review CLOSED (3/3; all E5)
CHECKPOINT-2 affinity review CLOSED (31/31; 0 parks)
CHECKPOINT-2 supplemental evidence-consistency CLOSED (9/9)
CHECKPOINT-2 applied; ready_for_application was true
Global S4 COMPLETE at reviewed relationship grain
S5 NOT started
```

## 2026-09-16 — Global S4 version-control closure

Global S4 is scientifically complete and CHECKPOINT-2 is applied.
This entry records version-control closure of the tracked
implementation. Scientific review decisions were not changed. S5
was not started: no dedup, NCBI/ENA resolution, clustering,
balancing, FT/REF/EVAL, or splits.

Reviewed grain remains one `(sequence, target)` relationship.
Combined input is 2960 source records. Leakage exclusions = 0.
Unresolved human decisions = 0. Evidence-affinity flags = 0.

Reviewed relationship routing:

```text
primary_candidate          = 1460
park_non_protein           =  578
park_evidence_e5           =  521
hold_target_unresolved     =  389
reject_no_binding_evidence =    3
leakage                    =    0
```

Source-record routing:

```text
primary_candidate          = 1428
park_non_protein           =  541
park_evidence_e5           =  521
hold_target_unresolved     =  389
unresolved_no_relationship =   57
target_parked              =   12
relationship_parked        =    9
reject_no_binding_evidence =    3
leakage_excluded           =    0
```

S5 diagnostics remain unresolved (461 duplicate sequence_core
groups / 1199 rows; 259 exact pair groups / 570 rows; 386
cross-source cores; 0 NCBI/ENA overlapping cores).

Input/review hashes unchanged. Application rerun hashes identical.
`git ls-files data` empty. Ignored `data/` outputs were not staged.

### Pipeline status

```text
CHECKPOINT-2 applied = yes
Global S4 COMPLETE at reviewed relationship grain
S5 NOT started
```

## 2026-09-17 — Global S5A exact scientific deduplication

Implemented exact `(sequence_core, canonical_target_name)`
deduplication with provenance merge. Clustering, MMseqs2/CD-HIT,
balancing, partitions, global dictionary-ID merge, and NCBI/ENA
duplicate resolution were not started. S4 outputs were not rewritten.

Starting state: `main` HEAD / origin/main
`bdc1df1b170eaac37a909a701e07c62377acfffd`
(`Complete global S4 and CHECKPOINT-2 review`). Working tree was
clean. `git ls-files data` empty. Frozen S4 hashes matched.

### Input

`global_s4_reviewed_relationships.csv` where
`s4_route == primary_candidate` only. Record-level
`s4_record_outcome` was not used. `aptamerbase:1110` retains its
EGFR primary relationship (`aptamerbase:1110|2`).

```text
relationships                         = 1460
distinct source record_id             = 1429
distinct sequence_core                = 1144
ncbi_nuc                              = 0
ena                                   = 237

aptamerbase = 526
riboaptamer = 279
ena         = 237
aptaindex   = 126
aptabase    = 112
utexas      = 104
aptadb      = 76

E2 = 931
E3 = 258
E4 = 271
E1 = 0
E5 = 0
```

29 source `record_id` values contribute >1 primary relationship
(60 rows; max 3). Combined extras were joined by `record_id` for
construct/trim/redistribution/ENA family/modification provenance.

### Exact dedup

Scientific identity ID:
`S5I_<sha256(sequence_core + "\x1f" + canonical_target_name)>`
full SHA-256 hex. Independent of row order and donor selection.

```text
scientific identities                 = 1281
exact duplicate groups                = 157
rows in those groups                  = 336
excess duplicate observations         = 179
membership rows                       = 1460
groups with >1 target_dictionary_id   = 9
```

Duplicate-group source combinations match the accepted preflight
(138 cross-source, 19 within-source; AptaBase–AptaIndex 65,
RiboAptamer–UTexas 57). Membership contains every input primary
relationship exactly once.

### Donor hierarchy

1. highest `evidence_score`
2. highest pre-S5 `corroboration_count` (not duplicate-row count)
3. highest metadata completeness
4. alphabetical `source_db`
5. alphabetical `reviewed_relationship_id`

Completeness fields: canonical affinity, affinity type, DOI, PMID,
accession (relationship or ENA extras), UniProt, Pfam, resolved
family, PDB, resolved chemistry, resolved molecule type, resolved
construct scope, trim status, publication as a presence bit.
Unresolved `unknown` does not count. Text length is ignored.

Donor source distribution (1281 identities):

```text
aptamerbase = 491
ena         = 235
riboaptamer = 217
utexas      = 104
aptabase    = 102
aptadb      = 70
aptaindex   = 62
```

### Provenance

`corroboration_count` = distinct `source_db` values, not rows.

```text
1 = 1143
2 =  131
3 =    6
4 =    1
```

`independently_attested_by_permissive_source` is false on all 1281
identities (no permissive contributing sources). Redistribution is
the most permissive of `{permissive, unknown, restricted}`:
unknown 1334 / restricted 126 on membership rows. Reversibility of
restricted+other-source pairs was tested on synthetic fixtures only.

### Dictionary-ID conflicts

Nine exact groups collapse on the name key while spanning two S4
IDs. Both IDs remain in membership. Scalar ID is the donor's. S4
dictionary table was not modified (hash unchanged). Groups:

HIV-1 reverse transcriptase `TD0365|TD0366` (2);
NF-kappaB p65 `TD0532|TD0771` (3);
Botulinum neurotoxin type A (BoNT/A) `TD0087|TD0088` (3);
Interleukin-17 A/F heterodimer `TD0413|TD0418` (1).

### Evidence / affinity / chemistry

Duplicate groups: differing evidence levels 38; multiple nonempty
canonical affinity observations 91 (88 same-value pairs plus 3
conflicting scalars); conflicting canonical molar values 3;
multiple chemistries 3 (RNA vs 2F-RNA); >1 `sequence_full` 0;
>1 construct_scope 71; >1 trim_status 107. Donor supplies scalars.
Member observations remain in the membership table. Affinities were
not averaged.

The 91 multiple-affinity count is canonical-value occupancy, not
the preflight complementary blank-vs-value count (32). Conflicting
nonblank canonical molars remain 3.

### Multi-target sequences

118 `sequence_core` values have >1 canonical name (326 rows);
122 have >1 name or dictionary ID (334 rows). They remain distinct
scientific identities. Sequence-only collapse was not performed.

### Outputs (ignored `data/interim/deduplicated/`)

```text
corpus_dedup.csv
  9dae7d8f59f36590945fa71baf473a8bfbbad95e9794355b5acab91ccc3cd2c2
exact_duplicate_membership.csv
  802c9d8dfed036639307e8456dbb330541dec2c519b5f06600c7cb82d113c618
exact_duplicate_groups.csv
  2eb63537abb5121bc79dc2a41cb26bbbc935008eb1015103d5a1e9f89ab3d903
target_dictionary_id_conflicts.csv
  5b44c9a59b86be1350d43eaf0ca8812d7130399832ba7c46f7ecceea7fb8be8f
multi_target_sequence_report.csv
  f1634ccc81ae857425aaf93bd939dbea756486112a9aa45fe02e200913d2dc80
exact_overlap_matrix.csv
  7b89d674c6a94eb7b36d920a185ec4a726793a1ca86cdc1ff47706416cc9211c
s5a_exact_dedup_report.md
  685f7a98c77e79af7cb9985b74f7759475e782bf9f32e40115f822214ecb0136
```

Tracked: `scripts/data_preparation/s5_deduplicate.py`,
`scripts/data_preparation/adapters/s5_exact_dedup.py`,
`config/global_s5a_exact_dedup.json`,
`tests/data_preparation/test_s5_exact_dedup.py`,
`docs/data_curation/global_s5a_exact_dedup.md`,
narrow S4-boundary notes, this log. Not committed.

S4 hashes unchanged. Combined input hash unchanged.
`git ls-files data` empty. Two S5A runs byte-identical.
Synthetic pytest: 21 passed. No clustering.

### Pipeline status

```text
CHECKPOINT-2 applied = yes
Global S4 COMPLETE at reviewed relationship grain
S5A exact scientific dedup COMPLETE
S5B/S5C clustering NOT started
S6 NOT started
S7 NOT started
```

## 2026-09-17 — Global S5B exact-dedup validation and scientific freeze

Validated frozen S5A exact scientific identities against the original
1460 primary S4 relationships. Schema/row-identity was reconciled for
downstream S5. Clustering, MMseqs2/CD-HIT, S4 rewrite, S5A scientific
rewrite, and final-schema migration were not started.

Starting state: `main` HEAD / origin/main
`bdc1df1b170eaac37a909a701e07c62377acfffd`. Working tree contained
the accepted uncommitted S5A workstream only. `git ls-files data`
empty. Frozen S4 hashes matched. Existing S5A output hashes matched;
rerunning S5A from frozen S4 was byte-identical.

### Population

```text
primary relationships     = 1460
membership rows           = 1460
scientific identities     = 1281
duplicate groups          = 157
duplicate excess          = 179
1460 - 179                = 1281
distinct scientific keys  = 1281
distinct sequence_core    = 1144
```

1:1 membership coverage. No excluded S4 routes in membership.
`aptamerbase:1110|2` remains the primary Epidermal growth factor
receptor relationship. 118 multi-target cores (326 rows) stay
separate identities.

### Donor

Independent recomputation matched all 1281 donors.

```text
evidence_score                         = 35
metadata_completeness                  = 46
alphabetical source_db                 = 54
alphabetical reviewed_relationship_id  = 22
pre-S5 corroboration_count             =  0
sole member                            = 1124
```

### Provenance / conflicts

Corroboration 1=1143, 2=131, 3=6, 4=1. Permissive-attestation flag
false on all 1281 identities. Restricted AptaIndex membership rows
126. Dictionary-ID conflicts 9; differing evidence 38; conflicting
canonical affinity 3; multiple affinity observations 91; multiple
chemistries 3; >1 sequence_full 0; >1 construct_scope 71; >1
trim_status 107. Donor sequence_full mismatches 0; missing cores 0.

### Row identity

Donor `record_id` is not unique (26 duplicated values / 53 rows).
`scientific_identity_id` is 1281/1281 unique, regenerates from the
key, zero collisions. S5C must use `scientific_identity_id`. Later
final-schema recommendation: Option B (keep source `record_id` as
provenance; do not overwrite it). Not implemented in S5B.

### Clustering readiness

1144 sequence-level clustering-input rows recommended (one per
distinct `sequence_core`), then broadcast cluster assignment back to
the 1281 identities. Length min/median/max 20/50/123. 13 AptaBase
rows already accepted by S4 sit above 100 nt (104–123); reported,
not re-filtered. Alphabet: RNA 1274, DNA_T 4, mixed_T_U 3. No
cluster IDs assigned.

### ENA

237 ENA membership rows; 235 identities; 234 distinct cores; 112
family IDs; 16 multi-member families with ≥2 S5 members (the later
ground truth); 0 within-family exact collapses; sidecar
reconstructable. Cluster recall not evaluated.

### Tests / safety

Synthetic pytest: 17 S5B + 21 S5A + 11 CHECKPOINT-2 apply = 49
passed. Tracked S5 implementation/docs/config/tests: no contiguous
A/C/G/T/U strings of length ≥20. Historical `docs/log.md` Phase-2
generation examples were not deleted.

### S5A/S5B freeze (S5C input)

```text
corpus_dedup.csv
  9dae7d8f59f36590945fa71baf473a8bfbbad95e9794355b5acab91ccc3cd2c2
exact_duplicate_membership.csv
  802c9d8dfed036639307e8456dbb330541dec2c519b5f06600c7cb82d113c618
exact_duplicate_groups.csv
  2eb63537abb5121bc79dc2a41cb26bbbc935008eb1015103d5a1e9f89ab3d903
target_dictionary_id_conflicts.csv
  5b44c9a59b86be1350d43eaf0ca8812d7130399832ba7c46f7ecceea7fb8be8f
multi_target_sequence_report.csv
  f1634ccc81ae857425aaf93bd939dbea756486112a9aa45fe02e200913d2dc80
exact_overlap_matrix.csv
  7b89d674c6a94eb7b36d920a185ec4a726793a1ca86cdc1ff47706416cc9211c
s5a_exact_dedup_report.md
  685f7a98c77e79af7cb9985b74f7759475e782bf9f32e40115f822214ecb0136
```

S4 hashes unchanged. Combined input hash unchanged.
`git ls-files data` empty. S5A scientific outputs not rewritten.
Not committed.

### Pipeline status

```text
CHECKPOINT-2 applied = yes
Global S4 COMPLETE at reviewed relationship grain
S5A exact scientific dedup COMPLETE
S5B exact-dedup validation COMPLETE and frozen
S5C clustering NOT started
S6 NOT started
S7 NOT started
```

## 2026-09-17 — Global S5C 90% sequence-identity clustering

Clustered the frozen S5A exact-deduplicated primary corpus on
`sequence_core` at 90% identity with MMseqs2. CD-HIT, ENA-family
adjudication, S4/S5A rewrite, balancing, and FT/REF/EVAL were not
started.

Starting state: `main` HEAD / origin/main
`bdc1df1b170eaac37a909a701e07c62377acfffd`. Working tree contained
the accepted uncommitted S5A/S5B workstream only. `git ls-files data`
empty. Frozen S4 hashes matched. Frozen S5A hashes matched.

### Tool environment

MMseqs2 was absent, then installed with Homebrew
`brew install mmseqs2`.

```text
path    = /opt/homebrew/bin/mmseqs
version = 18-8cc5c
CD-HIT  = not installed; fallback not run
```

Synthetic RNA/U preflight: A/C/G/U FASTA accepted as nucleotide;
identical and near-identical U sequences clustered; U treated as a
valid nucleotide and internally equivalent to T. Authoritative
`sequence_core` was not transcoded U→T. Preflight GO.

### Sequence-level input

```text
scientific identities              = 1281
distinct sequence_core             = 1144
unique S5SEQ IDs                   = 1144
shared cores                       = 118
identities on shared cores         = 255
S4/S5A membership rows on those cores = 326
extra identities from shared cores = 137
missing sequence_core              = 0
length min / median / max          = 20 / 50 / 123 (identity)
cores >100 nt                      = 13 (reported, not filtered)
alphabet identities RNA/DNA_T/mixed_T_U = 1274 / 4 / 3
```

The S5A/S5B 326 figure is membership rows on the 118 shared cores,
not 326 scientific identities. All 255 identities and all 326
relationships were retained. FASTA ordered by
`sequence_core_sha256`, then `sequence_id`. No target labels in
MMseqs headers.

### MMseqs execution

```text
mmseqs easy-cluster \
  sequence_clustering_input.fasta \
  s5c_mmseqs_work/run1/clusters \
  s5c_mmseqs_work/run1/tmp \
  --min-seq-id 0.9 -c 0.8 --cov-mode 1 -s 7.5 --threads 1
```

`--threads 1` is a determinism control only. The four governing
scientific parameters were not changed.

### Cluster results

```text
clusters              = 813
singletons            = 651
multi-sequence        = 162
singleton fraction    = 0.801
largest size          = 36
1144 → 813; reduction = 331
```

Sizes: 1=651, 2=106, 3=35, 4=6, 5=5, 6=5, 7=1, 9=1, 11=1, 34=1,
36=1. Two 30+ sequence clusters are single-target. Scientific
identities retained 1281/1281. Missing cluster IDs 0. Exactly 813
scientific representatives. Shared cores have one cluster ID each.

Independent global-Levenshtein diagnostic (not the MMseqs
definition): 198 non-representative members in non-singleton
clusters fall below 0.90. MMseqs clusters were not rejected.

### ENA family diagnostics for S5D

16 multi-member S5 families: 8 contained in one cluster, 8 split.
Largest split: `ndfam_e51f65c5e5` (46 cores, 7 clusters). Largest
contained: `ndfam_fa8cf96e7e` (31 cores, 1 cluster). Not adjudicated.
CD-HIT not run.

### Tests / safety

Synthetic pytest: 24 S5C passed. Tracked S5C implementation/docs/
config/tests: no contiguous A/C/G/T/U strings of length ≥20. Two
MMseqs runs: identical membership, stable cluster IDs, and
representatives.

### Integrity

S4 hashes unchanged. Combined input hash unchanged. Seven S5A freeze
hashes unchanged. `git ls-files data` empty. `corpus_dedup.csv` not
overwritten. Not committed.

### Pipeline status

```text
CHECKPOINT-2 applied = yes
Global S4 COMPLETE at reviewed relationship grain
S5A exact scientific dedup COMPLETE
S5B exact-dedup validation COMPLETE and frozen
S5C 90% sequence-identity clustering COMPLETE
S5D ENA-family adjudication COMPLETE
S5 final clustering NOT accepted
S6 NOT started
S7 NOT started
```

---

## Global S5D — ENA cluster validation + CD-HIT fallback

Date: 2026-09-17.

### GO / NO-GO

S5D **execution succeeded**. A **final clustering method is not
accepted**.

```text
decision = NO-GO — GROUND-TRUTH / 90%-RULE CONTRADICTION
```

CD-HIT was run as the authorised fallback. It is not promoted.
No `*_final` artefacts.

### Integrity

Branch `main`. HEAD = origin/main =
`bdc1df1b170eaac37a909a701e07c62377acfffd`. Recalculated S4 hashes,
combined S4 input hash, seven S5A freeze hashes, and S5C candidate
hashes were unchanged. `corpus_dedup.csv` unchanged. 1281 scientific
identities retained. `git ls-files data` empty.

### ENA methodology

Tracked ENA review code builds `ndfam_*` IDs as connected components
**within** experiment group + target. Edges are reverse complement,
equal-length Hamming ≤ max(2, ceil(0.05×L)), substring/truncation at
≥50% length ratio, or edit/max-length ≤ 0.08. That is not a 90%
global-identity family. Blank source IDs were materialised as
`ena_singleton_{review_unit_id}` with size 1. Families were not
regenerated.

### MMseqs characterisation

16 families, 8 contained (0.50), 59/141 cores contained, 82 split.
Largest split still `ndfam_e51f65c5e5` (46 cores, 7 clusters). Six
families are disconnected at 0.90 global Levenshtein (three reverse
complements, truncation/substring series). 96 materialised
singletons: 83 isolated from other ENA cores, 10 with another
singleton, 2 with a real family, 1 only with non-ENA. 8 clusters
combine distinct ENA families.

### CD-HIT

Installed via Homebrew `brewsci/bio/cd-hit` 4.8.1 at
`/opt/homebrew/bin/cd-hit-est`. Native U preflight passed; no U→T
comparison FASTA. Command:

```text
cd-hit-est -c 0.9 -n 8 -T 1 -d 0
```

Identity documented as identical bases / shorter-sequence length.
Default +/- strand search was left as installed.

```text
1144 cores → 791 clusters (612 singleton, 179 multi, largest 44)
1281 identities retained; missing cluster_id = 0
ENA containment 11/16 (0.6875); cores 60/141 contained
still split: 5 families, including 46 → 44+1+1
```

Two identical runs matched.

### Adjudication

The plan's 90% clustering rule and ENA-family acceptance criterion
conflict. CD-HIT improved recall but cannot make truncation and
reverse-complement families into 90% global-identity clusters
without retuning, which is forbidden. STOP for human review of the
clustering policy.

### Tests

83 passed (21 S5D, 24 S5C, 21 S5A, 17 S5B). Not committed.

---

## Global S5E — leakage-safe final clustering + S5 closure

Date: 2026-09-17.

### GO / NO-GO

**GO.** S5 can close. Final `cluster_id` is the connected component of
frozen MMseqs 90% clusters union trusted real multi-member ENA family
must-links. CD-HIT is not selected.

```text
decision = GO — S5 CLOSED
MMseqs clusters 813 → final clusters 796
16/16 retained multi-member ENA families contained
```

### Integrity

Branch `main`. HEAD = origin/main =
`bdc1df1b170eaac37a909a701e07c62377acfffd`. Recalculated S4 hashes,
combined S4 input hash, seven S5A freeze hashes, and S5C candidate
hashes were unchanged. `corpus_dedup.csv` and frozen S5C files were
not overwritten. `git ls-files data` empty.

### Policy resolution

ENA families are positive must-links, not complete global 90%
ground truth. Materialised singleton IDs are not cannot-links.
Different family IDs may share a cluster. This supersedes the S5D
validation interpretation without changing MMseqs parameters.

### Union construction

```text
MMseqs base                         = 813
real multi-member family IDs      = 17
must-link families (≥2 S5 cores) = 16
families that created a union edge = 8
MMseqs clusters in unioned finals  = 23
finals affected by must-links      = 6
reduction from family constraints   = 17
final clusters                      = 796
```

### Final statistics

```text
singletons 637 / multi-sequence 159 / largest 89
identities 1281 / cores 1144 / representatives 796
16/16 family containment; 0 splits
descriptive: 6 clusters with multiple ENA family IDs;
3 combining distinct real families (not a failure)
```

### Freeze hashes

```text
clusters_final.tsv
  9b1b3c671cd1cd603e56ab23f0b2a9adac4ad85d47b019679ccb602605f971d9
corpus_clustered_final.csv
  615677d51aa81337a3660b8c67e9db9fae2a5c8abc7128e7668617a342689d30
cluster_summary_final.csv
  7d06793fbf56be2e4e52c21d83faccef822feb2234118e4ef4b36dc307b6d078
cluster_union_provenance.csv
  83023ba556d0a3e486ef7205001d9ae46f9ba9ef2e56210fa4f7a7e892c5f2dc
overlap_report.md
  41e52f80ec632e6dbc7a912f244d4df302b78b79d1cbab8e7141432a89d8e33b
s5_final_clustering_manifest.json
  aa5bab02a78481f32b4bab82c157d3f8aa975ebf4a77350fec9d9dd88623c5b0
```

Two live runs were byte-identical. 102 synthetic tests passed
(19 S5E, 21 S5D, 24 S5C, 21 S5A, 17 S5B). Plan v1.4. Not committed.

### Pipeline status

```text
CHECKPOINT-2 applied = yes
Global S4 COMPLETE at reviewed relationship grain
S5A exact scientific dedup COMPLETE
S5B exact-dedup validation COMPLETE and frozen
S5C 90% sequence-identity clustering COMPLETE (MMseqs candidate frozen)
S5D ENA-family audit + CD-HIT fallback COMPLETE (diagnostic; not selected)
S5E leakage-safe final clustering COMPLETE
S5 COMPLETE
S6 NOT started
S7 NOT started
```

## 2026-09-17 — Global S6 pre-balancing corpus profile + CHECKPOINT-3 preparation

S6 profiled the frozen final S5 clustered corpus and stopped for
supervisor review. It did not balance, apply a target cap, assign
FT/REF/EVAL, populate `partition`, drop rows, rewrite S4/S5, or start
S7.

Starting state: `main` HEAD / origin/main
`bdc1df1b170eaac37a909a701e07c62377acfffd`. Recalculated S4 hashes,
combined S4 input hash, S5A freeze hashes, and six final S5 freeze
hashes matched. `git ls-files data` empty.

### Grain

```text
scientific identities = 1281
distinct sequence_core = 1144
final clusters         = 796
canonical targets      = 411
```

Records in this profile are the 1281 exact scientific identities, not
1460 pre-dedup relationships, 1429 source records, 1144 cores, or 796
clusters.

### Headline

```text
donor sources: aptamerbase 491, ena 235, riboaptamer 217,
  utexas 104, aptabase 102, aptadb 70, aptaindex 62
evidence: E2 803 (62.69%), E3 247 (19.28%), E4 231 (18.03%), E5 0
largest target: NGF 131 identities (10.23%)
enzyme identities: 78 (6.09%); unknown family 1097 (85.64%)
singleton clusters: 637 / 796 (80.0%)
UniProt: 53/411 targets; 105/1281 identities
<500-cluster trigger: not met
```

Exact duplicates were already provenance-merged. Final cluster IDs
combine frozen 90% MMseqs grouping with trusted ENA family must-links.
No balancing or partitioning has occurred.

### Candidate cap (diagnostic only)

v1.4 requires a cluster-level cap but does not specify denominator,
floor/ceiling, which whole clusters are retained, multi-target
treatment, ordering, or collateral removal. S6 did not invent an S7
algorithm. C3-05 records that gap.

Nominal threshold = floor(fraction × 1281). Idealised record-wise size
is not executable S7 output.

```text
0.02: threshold 25; 5 targets above; excess 123; idealised 1158
0.03: threshold 38; 1 target (NGF); excess 93; idealised 1188
0.05: threshold 64; 1 target (NGF); excess 67; idealised 1214
0.10: threshold 128; 1 target (NGF); excess 3; idealised 1278
```

NGF occupies 14 exclusive clusters, including an 89-core family-union
cluster. Exclusive clusters can absorb the identity excess at every
candidate fraction, but choosing which clusters to drop remains C3-05.

### Sequence / clusters

Distinct-core length median 49 nt, mean 55.0, max 123. Thirteen
>100-nt identities/cores are retained. Distinct-core GMM/BIC prefers
two components (means ~39 and ~77 nt; ΔBIC 437). This is a mixture
comparison, not proof of bimodality, and is not caused by parked
AptaDiff 36-mers. Distinct-core GC mean 0.531.

```text
clusters 796; multi-sequence 159; multi-target 143
ENA provenance 98; ENA must-link union 6
largest cluster 89 cores, NGF, mmseqs_plus_ena_family_must_link
```

118 cores / 255 identities are multi-target by identical core. 143
clusters have >1 target (104 include a shared identical core; 39 are
near-sequence co-membership only). Neutral wording retained.

### CHECKPOINT-3

Five decision rows, all human fields blank: C3-01 cap fraction;
C3-02 further balancing; C3-03 E4 vs E5; C3-04 protein-only;
C3-05 S7 cluster-selection semantics.

Two live S6 runs from frozen S5 inputs produced byte-identical
markdown, tables, CHECKPOINT-3 files, and plot-data CSVs. Synthetic
pytest: 23 passed. Sequence-safety scan of tracked S6 files: 0 leaks.
Not committed.

### Pipeline status

```text
CHECKPOINT-2 applied = yes
Global S4 COMPLETE at reviewed relationship grain
S5 COMPLETE
S6 profile COMPLETE
CHECKPOINT-3 prepared, not decided or applied
S7 NOT started
```

## 2026-09-21 — CHECKPOINT-3 supervisor consultation complete

Recorded supervisor decisions in
`docs/data_curation/checkpoint3_supervisor_decisions_2026-09-21.md`.
Final decisions: cap each target at 3% of the post-cap identity denominator;
no additional target-family balancing (known family labels secondary only);
retain E2–E4 and keep E5 excluded; retain the protein-only corpus; and apply
Amin's deterministic whole-cluster removal rule (target-pure first,
least-collateral mixed clusters only if needed, stable `cluster_id` tie-break,
recompute after every removal).

Additional constraints: freeze REF/EVAL before fine-tuning or hyperparameter
decisions; split train/validation only within FT; preserve the two observed
sequence-length regimes for splitting and null/reference distributions; do
not publish sequence data publicly (only aggregate statistics, provenance,
and reconstruction procedures); and complete a pre-publication GitHub leakage
audit. Ian requested an E5 population/inclusion-impact diagnostic; E5 remains
excluded. No scientific data or S4/S5/S6 output changed. S7/final capping and
splitting have not yet run. Not committed.

## 2026-09-21 — S7A 3% target-cap preparation and dry-run

**Stage:** Aim 2 / data curation / S7A target-cap preview
**What was done:** Incorporated closed CHECKPOINT-3 decisions into the
governing curation plan (v1.5 — 2026-09-21) and active configuration.
Implemented Amin's deterministic whole-cluster 3% cap as a pure selection
function and ran it in preview mode against the frozen final S5 corpus.
No authoritative post-cap corpus was written.

**Decisions encoded:** C3-01 active cap 3% of the current/post-removal
identity denominator (previous 5% placeholder retired); C3-02
multi-objective FT/REF/EVAL comparability with `target_family` secondary
only; C3-03 retain E2–E4, keep E5 parked; C3-04 protein-only primary
corpus; C3-05 never split clusters, target-pure first, least-collateral
mixed fallback, stable `cluster_id` tie-break, recompute after every
removal, fail closed if two targets are simultaneously overrepresented.
REF/EVAL freeze, FT-only cluster-level train/validation split, two
sequence-length regimes, and pre-publication leakage audit recorded in
the plan. Not applied beyond this preview.

**Inputs used:** frozen `corpus_clustered_final.csv`
SHA-256 `615677d51aa81337a3660b8c67e9db9fae2a5c8abc7128e7668617a342689d30`.
Counts independently verified: 1281 identities, 1144 cores, 796 clusters,
411 canonical protein targets, partition blank, E5 = 0.

**Outputs produced (preview only, gitignored):**
`data/interim/s7a_target_cap_preview/` sequence-free trace, removed-cluster
table, post-cap target distribution, mixed-collateral sidecar, markdown
report, and manifest.

**Numbers:** Synthetic pytest 17 S7A + 19 S5E + 33 S6 = 69 passed.
Dry-run: 2 target-pure NGF clusters proposed removed (89 then 19
identities); 0 mixed clusters; 0 collateral identities. 1281 → 1173
identities; 1144 → 1036 cores; 796 → 794 clusters; 411 → 411 targets.
Final independent max share 34/1173 = 0.0289855072 (HIV-1 Rev protein),
cap gate PASS. No non-initial-dominant target exceeded 3% after
denominator reduction. Remaining NGF 23/1173 = 0.0196078431.

**Open questions carried forward:** human review of this dry-run before
scientific cap application. No partitioning. Not committed. Not pushed.

## 2026-09-21 — S7A 3% target-cap preview approved and applied

**Stage:** Aim 2 / data curation / S7A target-cap application
**What was done:** Recorded human approval of the reviewed S7A dry-run
and applied the same tested `select_target_cap` function to the frozen
final S5 corpus. Wrote the authoritative post-cap/pre-partition corpus
under ignored `data/interim/s7a_target_cap/`. Did not begin S7B.

```text
S7A preview approved            = yes
S7A authoritative cap applied   = yes
S7A validation complete         = yes
S7B not started                 = yes
FT/REF/EVAL not assigned        = yes
```

**Approval:** `config/checkpoint_reviews/s7a_target_cap_approval.json`
(`review_status = approved_for_application`, decision_date 2026-09-21,
max_target_fraction 0.03). Approval metadata was used only as a
post-derivation parity check and was not used to select clusters.

**Reviewed preview hashes (frozen, not overwritten):**
- `s7a_target_cap_removal_trace.csv` `da3cd922e53c1388f25d2e1e9fcd714cdc22119fdecc11057e7a2205e1df1048`
- `s7a_removed_clusters.csv` `46defa4e1b460a4b9fec91106f2cf2c432146348a23888399c3fae6c0072c40b`
- `s7a_post_cap_target_distribution.csv` `f2be67a8c117335157577464362dc5eb1e89c28feeb9689f2b342453532ac2c7`
- `s7a_mixed_cluster_collateral.csv` `91eb65f42d4469e48ba3b1c3d915c14a4d34145645169c918cd0eed3e6aacc5e`
- `s7a_target_cap_preview_report.md` `e08ccab6f0cf3d9f22c9f9e516d780a4cab0c6820720cdc6b10f14db8e896f14`
- `s7a_target_cap_preview_manifest.json` `f230d70db5cff5b445e730a0ee6664600584a1d5dde1e12ca8c174d044dce65a`

**Inputs used:** frozen `corpus_clustered_final.csv`
SHA-256 `615677d51aa81337a3660b8c67e9db9fae2a5c8abc7128e7668617a342689d30`.
All frozen final-S5 hashes matched. Independently verified: 1281
identities, 1144 cores, 796 clusters, 411 canonical protein targets,
partition blank, E5 = 0, non-protein = 0.

**Application result:** 1281 → 1173 identities; 1144 → 1036 cores;
796 → 794 clusters; 411 → 411 targets. Two NGF target-pure clusters
removed (89 then 19 identities); 108 identities removed; 108 cores
removed; 0 mixed clusters; 0 collateral identities; 0 targets lost.
Post-cap NGF 23/1173 = 0.0196078431. Final maximum target = HIV-1 Rev
protein 34/1173 = 0.0289855072. All 411 targets independently
`exceeds_cap = false`. All-target 3% hard gate PASS.
preview/application semantic mismatches = 0.

**Authoritative output hashes:**
- `corpus_post_cap.csv` `6bbf040af6f1c541001a6a6ee4c461539f554737158ff11598aa93e4f137f9cd`
- `s7a_target_cap_removal_trace.csv` `da3cd922e53c1388f25d2e1e9fcd714cdc22119fdecc11057e7a2205e1df1048`
- `s7a_removed_clusters.csv` `46defa4e1b460a4b9fec91106f2cf2c432146348a23888399c3fae6c0072c40b`
- `s7a_post_cap_target_distribution.csv` `f2be67a8c117335157577464362dc5eb1e89c28feeb9689f2b342453532ac2c7`
- `s7a_target_cap_report.md` `12a1b1207826995a31c5229f39d6c5654783bd7bf24d8593d55ff1e04df3d08b`
- `s7a_target_cap_manifest.json` `c6f7d5846761bbc3e66eaea275c4eaa6ad835062ecdaf6d483d0e0277eb5d01c`

**Determinism:** two temporary application writes produced byte-identical
scientific payloads. In-process reversed-row re-selection matched.
Deterministic rerun PASS.

**Numbers:** Synthetic pytest 22 S7A + 19 S5E + 33 S6 = 74 passed.
The extra 5 S7A tests cover the application path (approval is audit-only,
preview directory is not overwritten, retained fields/partition are
preserved). No relevant failure.

**Boundary:** S7B not started. FT/REF/EVAL not assigned. REF/EVAL not
frozen. FT train/validation not created. S4/S5/S6 not mutated. No
commit. No push.

## 2026-09-21 — S7B whole-cluster FT/REF/EVAL assignment preview (dry-run)

**Stage:** Aim 2 / data curation / S7B partition preview
**What was done:** Implemented a deterministic whole-cluster assignment
of the frozen S7A post-cap corpus into FT/REF/EVAL under closed
CHECKPOINT-3 C3-02. Feature grains: identity-level target, evidence and
`source_db`; distinct-core frozen S6 short/long GMM. Integer quotas
minimise squared fraction error vs 80/10/10 cluster count and keep tied
REF/EVAL triples as candidates. Weight-free objective: JSD log2;
O1 = max worst-partition D; O2 = lexicographic descending D vector;
O3 = sum D; assignment-signature tie-break. Heuristic: harder-clusters-
first greedy placement then pairwise first-improvement swaps until a
no-improve pass. Wrote sequence-free preview artefacts under ignored
`data/interim/s7b_partition_preview/`. Did not write corpus_final, freeze
REF/EVAL, populate `partition` on the S7A input, or create FT train/val.

```text
S7B deterministic assignment implementation = yes
S7B dry-run completed                       = yes
authoritative partitioned corpus written    = no
REF frozen                                  = no
EVAL frozen                                 = no
REF/EVAL hashes created                     = no
FT train/validation split                   = no
commit performed                            = no
push performed                              = no
```

**Frozen input:** `corpus_post_cap.csv` SHA-256
`6bbf040af6f1c541001a6a6ee4c461539f554737158ff11598aa93e4f137f9cd`.
Independently verified: 1173 identities, 1036 cores, 794 clusters, 411
canonical protein targets, partition blank, E5 = 0, non-protein = 0.
Every identity has one frozen S5 `cluster_id`; each core maps to one
cluster.

**Length regimes:** reused frozen S6 `bimodality.json` `gmm_2` with
`gmm_k2_maximum_posterior` (means ≈ 38.89 / 77.36 nt). Not refit.
Post-cap distinct cores: short = 595, long = 441.

**Quotas:** tied-optimal (635, 79, 80) and (635, 80, 79). Scientific
objective selected FT=635, REF=80, EVAL=79.

**Preview sizes:** FT 635 clusters / 895 identities / 795 cores;
REF 80 / 114 / 103; EVAL 79 / 164 / 138.

**Objective:** O1 = 0.269453695698 (D_target); D_source = 0.019546237985;
D_length = 0.001660102797; D_evidence = 0.000086296904; O3 =
0.290746333384. Local search converged after 4222 accepted swaps / 76
passes (greedy O1 0.46395). Random diagnostic (21 seeds) O1
min/mean/max = 0.4185 / 0.4694 / 0.5017; not used as the assignment.

**Integrity:** clusters assigned exactly once; identities assigned
exactly once; cores cross partitions = 0; cluster crossings = 0;
E5 = 0; non-protein = 0; S7A input unmutated; tracked S7B sequence
leaks = 0.

**Tests:** pytest 32 S7B + 22 S7A + 19 S5E + 33 S6 = 106 passed.

**Open questions carried forward:** human review of this dry-run before
authoritative assignment and REF/EVAL freeze. No corpus_final. Not
committed. Not pushed.

## 2026-09-21 — S7B preview approved; authoritative FT/REF/EVAL applied; REF/EVAL frozen

**Stage:** Aim 2 / data curation / S7B partition application and freeze
**What was done:** Recorded human approval of the reviewed S7B dry-run
and rederived the assignment from frozen S7A `corpus_post_cap.csv` with
the same tested `build_cluster_features` / `select_preview_assignment`
implementation. Wrote the authoritative partitioned corpus under ignored
`data/interim/s7b_partition/`. Formally froze REF and EVAL. Did not begin
S7C or create an FT train/validation split.

```text
S7B preview                         = yes (preserved)
S7B preview approved                = yes
S7B authoritative assignment applied = yes
REF frozen                          = yes
EVAL frozen                         = yes
S7C not started                     = yes
FT train/validation not created     = yes
```

**Approval:** `config/checkpoint_reviews/s7b_partition_approval.json`
(`review_status = approved_for_application_and_freeze`, decision_date
2026-09-21). Approval metadata was used only as a post-derivation parity
check and was not used to assign clusters.

**Reviewed preview hashes (frozen, not overwritten):**
- `cluster_partition_preview.csv` `5e74ec91469fd33309d0bd1034866a6d752316b10e89a2dafecaab7c5f4402b1`
- `partition_identity_summary.csv` `03a2bba35855ca126f28b05c63641b527aedb48844d55abc880a65e4b75fa0bf`
- `partition_core_summary.csv` `34ec67488c3242f6887d55d642d0d80a61d8bc5fb89c7c0958f9b2b8f3c68ce3`
- `partition_target_distribution.csv` `94e14ee0350c42030283bc7f6a16371fbd24601863d41d8cb10d285a197b1120`
- `partition_evidence_distribution.csv` `067e0cecfc89040d7aeab82aa5cccbba636026c73039f22a65235c0b33d5d67b`
- `partition_length_regime_distribution.csv` `83a80b04f39b3a0146aabd4dd5f7c354b8197f52df27d764444b043b912f472b`
- `partition_source_distribution.csv` `2c4468abd1e38fa3782bc75ae0b6dd7e44e28da7d94a14bbcd5f123ffb43a7ee`
- `partition_target_family_diagnostic.csv` `a314cf3fa530c591e979449faf67ea146276a449b46b126e172638174beca366`
- `partition_divergence_metrics.csv` `efff4974e1acd055dd433e1672a1ee68be32f06b698fca7ab2d486e311fa687a`
- `s7b_partition_preview_report.md` `cabe07de51628ea9329e48b802fe555268bddb77319828cfac3937b8e8363ec6`
- `s7b_partition_preview_manifest.json` `e07e7674f53b46733c8bfe3eca8213ac81a9fd0153ac6dc0ff283c5665dc6a17`

**Inputs used:** frozen `corpus_post_cap.csv` SHA-256
`6bbf040af6f1c541001a6a6ee4c461539f554737158ff11598aa93e4f137f9cd`.
All frozen S7A artefact hashes matched. Independently verified: 1173
identities, 1036 cores, 794 clusters, 411 canonical protein targets,
partition blank, E5 = 0, non-protein = 0.

**Application result:** FT 635 clusters / 895 identities / 795 cores /
390 targets; REF 80 / 114 / 103 / 88; EVAL 79 / 164 / 138 / 111.
794 / 794 cluster assignments identical to the reviewed preview.
preview/application semantic mismatches = 0. Objective unchanged:
O1 = D_target = 0.2694536956975229; D_source = 0.01954623798492084;
D_length = 0.001660102797405985; D_evidence = 8.629690438492248e-05;
O3 = 0.29074633338423467.

Quotas are by cluster count, not identity count. EVAL therefore contains
13.98% of identities despite 9.95% of clusters. REF contains zero
globally singleton-target identities but still represents 88 canonical
targets across 114 identities. This follows the approved
identity-weighted target objective and whole-cluster constraints, not
leakage. No additional singleton-target balancing constraint was
introduced. Target JSD dominates because the 411-target long tail is
harder to reproduce than evidence or two-regime length. Source, evidence
and length diagnostics were reviewed and accepted before freeze. This is
the approved deterministic operationalisation, not a claim of unique
global optimality.

**Authoritative output hashes:**
- `corpus_partitioned.csv` `755e6afaf6a522be390073d3651311f8afc0ca9486322ac3bbfe348cd2a3fb1a`
- `cluster_partition_assignment.csv` `6278d42a067e741b0f057169a862112351f8f183da49103952074f6f65376072`
- `ft.csv` `b680ace037be73f650e386a34d97db915e4925a2dcd59e3053b7542b6d6fb4ff`
- `ref.csv` `6c8bf5cdec625bdddb9f42b18a15f435826bebabb119dfc268ff737c89b7408d`
- `eval.csv` `88fe1d8c2c78ed9dc478306c7390cff7016cd49541cfb1019d48ba8c1272c89d`
- `partition_divergence_metrics.csv` `efff4974e1acd055dd433e1672a1ee68be32f06b698fca7ab2d486e311fa687a`

**REF freeze:** identity-set
`54a74c8bb8ef67f36dd4b054d6ed43f201bd38d41d75244d9b69eb1583951abc`;
cluster-set
`84afc5a5bb030db9cbdddb7246ceaab3457ef8eb02f1192575433d5f77f6cd82`.
**EVAL freeze:** identity-set
`47ef50345fae50f14e99547426dbf3a3c34ed0caf49574005fb3f1da94315406`;
cluster-set
`c923af78ef7b191b569c5ead859982eb7711460a6537d0a70612a1101ffa8138`.
Freeze record:
`config/checkpoint_reviews/s7b_partition_freeze.json`. Freeze date
2026-09-21. Future movement of REF/EVAL is prohibited without a
documented split revision.

**Integrity:** identities assigned exactly once; clusters assigned
exactly once; cores cross partitions = 0; cluster crossings = 0;
partition blank = 0; invalid labels = 0; E5 = 0; non-protein = 0;
S7A/S5/S6 unmutated.

**Determinism:** two temporary application writes produced byte-identical
scientific payloads. In-process reversed-row re-optimisation matched.
Deterministic rerun PASS.

**Tests:** pytest 37 S7B + 22 S7A + 19 S5E + 33 S6 = 111 passed.
The extra 5 S7B tests cover the application/freeze path (approval is
audit-only, preview directory is not overwritten, retained fields other
than `partition` are preserved). No relevant failure.

**Boundary:** S7C not started. FT train/validation not created. Model
fine-tuning not started. REF calibration not started. EVAL model
evaluation not started. No commit. No push.

## 2026-09-21 — S7C FT train/validation preview dry-run

**Stage:** Aim 2 / data curation / S7C FT-only train/validation preview
**What was done:** Designed, implemented, tested, and dry-ran a
deterministic approximately 90/10 whole-cluster split of frozen FT into
TRAIN/VALIDATION. Reused the S7B feature-vector, JSD, greedy, and
local-search implementation with TRAIN/VALIDATION labels. Did not write
authoritative `ft_train.csv` / `ft_validation.csv`. Did not start
fine-tuning. Did not use validation results for any model decision.

```text
S7C implementation built                 = yes
S7C dry-run/preview                      = yes
authoritative FT train/validation files  = no
FT train frozen                          = no
FT validation frozen                     = no
```

**Inputs used:** frozen `ft.csv` SHA-256
`b680ace037be73f650e386a34d97db915e4925a2dcd59e3053b7542b6d6fb4ff`.
Independently verified: 895 identities, 795 cores, 635 clusters, 390
canonical protein targets, all `partition=FT`, E2/E3/E4 = 615/187/93,
E5 = 0, short/long cores = 448/347.

**REF/EVAL guards (automated, before and after):** file SHA-256 and
identity/cluster-set hashes identical to the S7B freeze. REF 80
clusters, EVAL 79 clusters, overlap 0. REF/EVAL files byte-identical
after the preview.

**Tied-optimal cluster quotas:** (571, 64) and (572, 63). Scientific
objective selected 571 TRAIN / 64 VALIDATION.

**Preview sizes:** TRAIN 571 clusters / 826 identities / 727 cores /
390 targets; VALIDATION 64 / 69 / 68 / 59. Cluster fractions 89.92% /
10.08%. Identity fractions 92.29% / 7.71% because quotas are by cluster
count.

**Objective (JSD log2 vs complete frozen FT):** O1 = D_target =
0.350017921105; D_source = 0.085263227565; D_length = 0.000073625782;
D_evidence = 0.000061441657; O3 = 0.435416216109. Local search
converged after 585 accepted swaps / 32 passes (greedy O1 0.50081).
`target_family` not in the primary objective. No manual criterion
weights.

**Target coverage:** TRAIN has all 390 FT targets. VALIDATION has 59,
all shared with TRAIN; 331 targets train-only; 0 validation-only.
Singleton-target identities 220 TRAIN / 0 VALIDATION. Validation is not
required to contain every target.

**Random diagnostic (21 seeds, 571/64 quotas):** O1 min/mean/max =
0.4887 / 0.5194 / 0.5489. Optimised O1 0.3500. Some random splits beat
optimised D_length and D_source while remaining worse under minimax.
Not used as the assignment.

**Integrity:** FT clusters assigned exactly once; identities assigned
exactly once; cores cross train/validation = 0; cluster crossings = 0;
REF/EVAL leakage = 0; E5 = 0; non-protein = 0; `ft.csv` unmutated;
top-level `partition` still FT; tracked S7C sequence leaks = 0;
`git ls-files data` empty.

**Tests:** pytest 39 S7C + 38 S7B + 22 S7A + 19 S5E + 33 S6 = 151
passed. The extra S7B test is a synthetic assignment fingerprint
proving the shared-optimiser refactor did not change S7B semantics.

**Open questions carried forward:** human review of this dry-run before
authoritative FT train/validation freeze. No fine-tuning. Not
committed. Not pushed.

## 2026-09-21 — S7C v2 FT train/validation preview (revised objective)

**Stage:** Aim 2 / data curation / S7C FT-only train/validation preview
**What was done:** Did not freeze or apply the first S7C preview. Preserved
the v1 raw-JSD artefacts under `data/interim/s7c_ft_split_preview/` and a
byte-identical copy at `data/interim/s7c_ft_split_preview_jsd_v1/`.
Revised the S7C primary metric from raw JSD minimax to maximum absolute
category-proportion deviation on complete frozen FT support, so target,
evidence, length regime, and source are measured on a common
percentage-point scale. Regenerated a v2 dry-run under
`data/interim/s7c_ft_split_preview_v2/`. Did not write authoritative
`ft_train.csv` / `ft_validation.csv`. Did not start fine-tuning. Did not
commit or push.

```text
S7C v1 preview preserved                 = yes
S7C v1 approved                          = no
S7C v2 preview generated                 = yes
S7C v2 approved                          = no
authoritative FT train/validation files  = no
```

**Why v1 was not approved:** mechanically valid, but raw JSD across
criteria of radically different support size (390 targets vs 7/3/2)
effectively prioritised target matching and yielded poor validation
source coverage (AptaDB 0/54, AptaIndex 0/51, AptamerBase 38/368).

**Inputs used:** frozen `ft.csv` SHA-256
`b680ace037be73f650e386a34d97db915e4925a2dcd59e3053b7542b6d6fb4ff`.
Independently verified: 895 identities, 795 cores, 635 clusters, 390
canonical protein targets, all `partition=FT`.

**REF/EVAL guards (automated, before and after):** file SHA-256 and
identity/cluster-set hashes identical to the S7B freeze. REF 80
clusters, EVAL 79 clusters, overlap 0. REF/EVAL files byte-identical
after the preview.

**Tied-optimal cluster quotas:** (571, 64) and (572, 63). Revised
objective selected 571 TRAIN / 64 VALIDATION.

**v2 preview sizes:** TRAIN 571 clusters / 746 identities / 678 cores /
333 targets; VALIDATION 64 / 149 / 117 / 102. Cluster fractions 89.92%
/ 10.08%. Identity fractions 83.35% / 16.65% because quotas are by
cluster count.

**Revised objective (max abs proportion deviation vs complete FT):**
R1 = M_target = 0.016782272881 (1.68 pp); M_evidence = 0.003471935810
(0.35 pp); M_length = 0.000580551524 (0.06 pp); M_source =
0.003291965056 (0.33 pp); R3 = 0.024126725271. JSD is diagnostic /
tie-break only. `target_family` not in the primary objective. No
manual criterion weights. No hard source-coverage constraint. Local
search converged after 526 accepted swaps / 33 passes (greedy R1
0.12762). Frozen S7B JSD semantics unchanged (synthetic assignment
fingerprint reproduced).

**Source:** all 7 sources present in validation. Worst validation
deviation 0.33 pp (aptaindex). VALIDATION count = 0 sources: none.

**Target coverage:** TRAIN 333 / VALIDATION 102 / shared 45 /
validation-only 57 / train-only 288. Singleton-target identities 181
TRAIN / 39 VALIDATION. Maximum target-share deviation 1.68 pp
(HIV-1 aspartyl protease (PR) in VALIDATION). No target-coverage hard
constraint.

**v1 vs v2 trade-off:** same 571/64 quotas. v2 improves R1 0.140 →
0.017 and M_source 0.140 → 0.003, with all sources represented;
validation identities rise 69 → 149; target JSD worsens 0.350 → 0.431
because JSD is no longer the first scale. v2 is not declared superior
solely because it is newer; it is the intended scientific correction
pending review.

**Random diagnostic (21 seeds, 571/64 quotas):** R1 min/mean/max =
0.0459 / 0.0886 / 0.1808. Optimised R1 0.0168, better than every
random split on R1 and on each reported M_c minimum. Not used as the
assignment.

**Integrity:** FT clusters assigned exactly once; identities assigned
exactly once; cores cross train/validation = 0; cluster crossings = 0;
REF/EVAL leakage = 0; E5 = 0; non-protein = 0; `ft.csv` unmutated;
top-level `partition` still FT; tracked S7C sequence leaks = 0;
`git ls-files data` empty.

**Tests:** pytest 49 S7C + 38 S7B + 22 S7A + 19 S5E + 33 S6 = 161
passed. S7B synthetic assignment fingerprint unchanged after the
shared objective-profile refactor.

**Open questions carried forward:** human review of the v2 dry-run
before authoritative FT train/validation freeze. No fine-tuning. Not
committed. Not pushed.

## 2026-09-21 — S7C v2 authoritative application and TRAIN/VALIDATION freeze

**Stage:** Aim 2 / data curation / S7C FT train/validation application
and freeze
**What was done:** Recorded explicit approval of the v2
maximum-absolute-proportion-deviation preview and non-approval of v1.
Preserved both preview trees unchanged. Rederived the v2 assignment
from frozen `ft.csv` with the same tested optimiser, required exact
preview/application parity, wrote authoritative `ft_train.csv` /
`ft_validation.csv` / `ft_split_assignment.csv` under ignored
`data/interim/s7c_ft_split/`, and froze TRAIN and VALIDATION with file
and semantic hashes. Did not begin S7D. Did not start model
fine-tuning. Did not construct `corpus_final`. Did not commit or push.

```text
S7C v1 preview preserved / not approved  = yes
S7C v2 preview approved                  = yes
authoritative assignment reproduced      = yes (635/635, mismatches 0)
FT TRAIN frozen                          = yes
FT VALIDATION frozen                     = yes
REF/EVAL hash guards                     = passed
```

**Approval:** `config/checkpoint_reviews/s7c_ft_split_approval.json`.
Audit-only. Not used for cluster selection.

**Freeze:** `config/checkpoint_reviews/s7c_ft_split_freeze.json`,
date 2026-09-21.

**TRAIN:** 571 clusters / 746 identities / 678 cores / 333 targets.
`ft_train.csv` SHA-256
`941fe8783ee8c99a2ce7598dea00ed123e62750026b7f157f28e7bbcc5d14a8f`.
Identity-set
`75e5cb8471d2fb3ee30529617aaf80ff584d5bf79e9976dc338434057a6aac6a`.
Cluster-set
`18c6df63ac4935557bad9c5fcc12610dd280b207652208faf04f0ba39d9c3349`.

**VALIDATION:** 64 / 149 / 117 / 102.
`ft_validation.csv` SHA-256
`03be477e12f7b9ca20f8911e2ac88fde2949af2b6131c2d2aa43eef2ae6d9abc`.
Identity-set
`19121149b9e0e02dd9cda5eb5619c64df86940331603139b702d436e6bde67ac`.
Cluster-set
`088d6b4db826be5c970b410e74cfa2d52fc402fa4818c692f8be30e42f79c4f9`.

**Objective (exact v2 parity):** R1 = M_target = 0.016782272880656892;
M_evidence = 0.0034719358104308012; M_length = 0.0005805515239477588;
M_source = 0.0032919650556784558; R3 = 0.024126725270713908.

**Integrity:** TRAIN∩VALIDATION identities/clusters/cores = 0; no
REF/EVAL leakage; every FT identity/cluster/core appears exactly once;
E5 = 0; non-protein = 0; top-level `partition` remains FT; `ft.csv`
unmutated; REF/EVAL six freeze hashes unchanged; tracked sequence leaks
= 0; `git ls-files data` empty. Deterministic rerun of scientific
payloads was byte-identical.

**Tests:** specified S7C/S7B/S7A/S5E/S6 command: 166 passed
(was 161 at the accepted v2 preview baseline). Increase is the five
new application/freeze tests.

**Boundary:** No model training. No REF calibration. No EVAL
evaluation. No S7D. Not committed. Not pushed.

## 2026-09-22 — S7D final corpus build and validation

**Stage:** Aim 2 / data curation / S7D final assembly, diagnostics,
reporting and validation

**What was done:** Verified every frozen S7A/S7B/S7C authority against
the recorded SHA256 and semantic freeze hashes. Assembled ignored
`data/processed/` deliverables by byte-copying frozen partition files
and concatenating authoritative parked/rejected/evaluation-reference
lanes. Wrote `corpus_final.txt` from frozen FT TRAIN `sequence_core`
values only, deduplicated by first occurrence. Completed the CHECKPOINT-3
E5 inclusion-impact diagnostic without promoting E5. Independently
re-ran integrity, leakage, split, target-cap and sequence-safety gates.
Did not alter any frozen split. Did not start model fine-tuning. Did not
calculate AptaRank reference distributions. Did not evaluate models on
EVAL. Did not commit or push.

```text
S7D final build complete
all frozen splits unchanged
model work has not started
final sequence-bearing data remain under ignored data/
```

**Contract:** `config/global_s7d_final_build.json`.
**Adapter / CLI:** `scripts/data_preparation/adapters/s7_final_build.py`,
`scripts/data_preparation/s7_finalise.py`.
**Documentation:** `docs/data_curation/global_s7d_final_build.md`.

**Boundary:** TRAIN/VALIDATION/REF/EVAL remain the frozen S7C/S7B
authorities. E5 promoted = no. Non-protein promoted = no. Repository
HEAD baseline `c1081c14cb3f20869affeddea49f5dd740b0bc51`. `git ls-files
data` empty. Pre-publication history leakage audit remains required.

**Tests:**
`PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/data_preparation/test_s7_final_build.py tests/data_preparation/test_s7_ft_train_validation.py tests/data_preparation/test_s7_partition.py tests/data_preparation/test_s7_target_cap.py tests/data_preparation/test_s5_final_clustering.py tests/data_preparation/test_s6_profile.py`
= 178 passed / 0 failed / 0 skipped (166 prior S7C/S7B/S7A/S5E/S6 + 12 new S7D).

Not committed. Not pushed.

## 2026-09-22 — S7D parked-completeness audit patch

**Stage:** Aim 2 / data curation / S7D documentation and audit completeness

**What was done:** Bounded documentation/audit pass after scientific S7D
acceptance. Independently reverified frozen scientific hashes. Inventoried
every earlier parked route from frozen CHECKPOINT-1 applied artefacts and
global-S4 routing/audit metadata. Wrote sequence-safe
`data/processed/parked_inventory.csv` so residual chemistry, molecule,
construct, and S4 hold/unresolved parks remain attributable without being
coerced into ssDNA / non-protein / E5. Clarified that 235 E5D diagnostic
cluster units are a counterfactual approximation, not exact future S5
clusters. Confirmed Dataset A is replication-only. Did not change
`corpus_final.csv`, `corpus_final.txt`, TRAIN, VALIDATION, REF, EVAL,
S7A results, or any S7B/S7C split. Did not commit or push.

```text
S7D scientific corpus changed by this audit patch = no
unaccounted parked lanes = 0
E5 promoted = no
frozen corpus changed = no
model work started = no
commit performed = no
push performed = no
```

**Tests:**
`PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/data_preparation/test_s7_final_build.py tests/data_preparation/test_s7_ft_train_validation.py tests/data_preparation/test_s7_partition.py tests/data_preparation/test_s7_target_cap.py tests/data_preparation/test_s5_final_clustering.py tests/data_preparation/test_s6_profile.py`
= 179 passed / 0 failed / 0 skipped (166 prior S7C/S7B/S7A/S5E/S6 + 13 S7D).

Not committed. Not pushed.

## 2026-09-23 — RNAGenesis fine-tuning strategy and implementation-plan freeze

**Stage:** Aim 2 / modelling preparation / RNAGenesis fine-tuning design

**What was done:** Completed read-only H200 inspection of the released
RNAGenesis assets and current upstream fine-tuning code. Confirmed that the
generic released diffusion checkpoint at `configs/rnagenesis/diffusion`
differs from the released aptamer-adapted checkpoint at
`checkpoints/Aptamer/diffusion`. Reviewed the upstream diffusion-only
fine-tuning workflow and selected a single MRes strategy: freeze the complete
released `EncDec` stack and fine-tune only the latent diffusion denoiser from
the generic released checkpoint on the frozen 678-core TRAIN corpus.

Replaced the earlier Q-Former/decoder-primary draft with the approved tracked
implementation plan at `docs/fine-tuning-implementation-plan.md`. Locked the
condition terminology B1 = generic released RNAGenesis, B0 = released
aptamer-adapted RNAGenesis, B2 = TRAIN-matched empirical RNA null, and
D1 = MRes curated-aptamer diffusion-adapted RNAGenesis. Recorded that the
existing 30,080-sequence B0 pool is retained and that `scripts/null_model.py`
will be reused/hardened to regenerate 30,000 B2 sequences.

Verified the Mac and H200 MRes repositories are synchronized at
`5afc24147fdc9b40a3d563cf68430da867ea6aa1`, and reverified the frozen H200
TRAIN/VALIDATION hashes. GPU0 remains the default H200 device; GPU1 may be used
only when explicitly authorised for that session/run.

**Boundary:** No RNAGenesis optimisation or GPU training started. REF remains
reserved for AptaRank calibration and EVAL remains untouched. Next stage is
M0 reproducibility/data-contract/code-integration implementation.

## 2026-09-25 — Corrective corpus revision for the RNA modelling alphabet gate

**Why reopened:** The frozen corpus in `095236dfb13d1d3b13f11bbb34c2e48319c10184` failed the RNAGenesis M0 alphabet gate. Seven Aptabase records still carried literal `T` or the wrong molecule class in the modelling core.

**Dispositions, from primary evidence, without silent T-to-U:**

- `aptabase:592` and `aptabase:593`: genuine ssDNA heparanase aptamers; parked out of the RNA corpus.
- `aptabase:104`: corrected RNA core is 19 nt, below the 20 nt minimum; rejected.
- `aptabase:185`: TRAIN, 24 nt RNA core `ACCCUGAUGGUAGACGCCGGGGUG`.
- `aptabase:118`: TRAIN, 49 nt 2F-RNA core `UUGUAAUUCAAAACAAAGGUUUCCUGGACUCCCCGCAGGUCUUGUGAAU`.
- `aptabase:123`: TRAIN, 49 nt 2F-RNA core `UGAUCAAAUCGAGCUUUAACCCAACAGAGCAUCCGUAUCUAUCCAAAUG`.
- `aptabase:82`: VALIDATION, 47 nt RNA core `GACAGCGUGCCUAGAAGUCCAAGCUUAAAUAACCACGCUCGACAAGC`.

**Implementation boundary:** Rerun stages, in order: Aptabase CHECKPOINT-1 overlay; global S4/CHECKPOINT-2; S5A exact dedup; S5B validation; S5C MMseqs clustering; S5D CD-HIT diagnostic; S5E final clustering; S6 profile; S7A target cap; S7B partition; S7C FT split; S7D final build. S7B local search kept the same objective and gained a category-count hot path so the rerun could finish; the partition rule did not change. No RNAGenesis training, generation, or evaluation was run. EVAL was not used to choose splits.

**Final primary corpus:** 1170 identities, 1031 cores, 790 clusters. TRAIN 726 / 569 / 669. VALIDATION 132 / 63 / 95. REF 131 / 79 / 113. EVAL 181 / 79 / 154. `corpus_final.txt` has 669 unique TRAIN cores. Cross-role cluster leakage 0. Cross-role core leakage 0. TRAIN/VALIDATION cores match `^[ACGU]+$`.

**Final hashes:**

- `ft_train.csv` `84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0`
- `corpus_final.txt` `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d`
- `ft_validation.csv` `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd`
- `ref.csv` `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23`
- `eval.csv` `ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015`
- `corpus_final.csv` `2797e6767f78029574df1b6cdf51bbe7952ea8affce83870441b3d3d93c98849`
- `corpus_manifest.json` `08da8d5e44413ea9ab57c128dbe4ef7986dab7a2bfa794cfef6fb4724577565f`

**Closure:** `10aac629bb0ef0337107c3d628b23e1897962af9`, subject `Complete corrective corpus revision for RNA modelling alphabet gate`. This commit supersedes frozen corpus commit `095236dfb13d1d3b13f11bbb34c2e48319c10184`. RNAGenesis M0 resumes from this corrected corpus and must not rerun S7D. Use only the hashes in this entry. The S7D `repository_head_baseline` pin remains the pre-closure HEAD `5afc24147fdc9b40a3d563cf68430da867ea6aa1`. Sequence-bearing files stay under ignored `data/`.

## 2026-09-25 — M0 technical preflight closure

**Stage:** Aim 2 / modelling / M0 reproducibility and frozen-contract verification

**Status:** COMPLETE / GO. The human gate accepts that the imported trainer and development data contract match the fine-tuning plan. M0 completion does not mean biological fine-tuning has run. No optimizer step and no generation occurred. Next is M1, released-behaviour and numerical training smoke validation, before the substantive D1 fitting run.

**Versions:** MRes source before this documentation closure `4d8730f4eb82f7066c2d8d107b97240897687021`. RNAGenesis branch `mres-d1-diffusion-finetune`: `29619df` restore biomap latent encoding, `81418f9` document biomap attribution, `789ecc2` add the MRes D1 diffusion trainer, `e20f556` correct denoiser parameter accounting. Clean preflight git `e20f5567526a6d76a173eba87e363e8edf130cd6`. Output `/home/laura/rnagenesis-mres-runs/m0_preflight_e20f556_clean`. `working_tree_dirty = false` after rerun with `PYTHONDONTWRITEBYTECODE=1`.

**Contract:** development verifier passed before the preflight. `input_directory_isolation = PASS`. `restricted_role_files_opened = []`. Contract SHA256 `396c83c3dbf9afc656ad5c60ec05c94fce3c5a684990c3cc1cebfb2411ccd5ff`. TRAIN 669 examples, `/home/laura/rnagenesis-mres-data/development/corpus_final.txt`, SHA256 `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d`. VALIDATION 95 unique cores, `/home/laura/rnagenesis-mres-data/development/ft_validation.csv`, SHA256 `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd`. No REF/EVAL access. `preflight = true`. `fixture = false`.

**Model:** B1 `configs/rnagenesis/diffusion`. EncDec `configs/rnagenesis/autoencoder`, frozen. Denoiser and trainable parameter count 1,911,589,344. Registered buffer elements 50,331,648. Serialized state elements 1,961,920,992. EMA false. The first preflight correctly failed on the old assertion that the parameter count equalled the serialized-element total, before optimizer construction. The 50,331,648-element difference is 24 registered `transformer_blocks.0`–`23.pos_embed.pe` buffers, corrected in `e20f556`. The clean rerun passed.

**Schedule observed, not run:** microbatch 8, accumulation 4, effective batch 32, 84 dataloader batches/epoch, 21 optimizer updates/epoch, 5 epochs, 105 updates maximum, warmup 10, AdamW, learning rate 3e-5, betas 0.95/0.999, epsilon 1e-8, weight decay 1e-6, cosine schedule, gradient clip 1.0, mixed precision no. TRAIN/DataLoader/diffusion seed 42. Fixed VALIDATION seed 1, one draw per sequence. Validation sequence SHA256 `b23647f40bb8fccee463009a5562411eceabe8070b953dfe0dcd59e10d8dc088`. Timestep SHA256 `aa20a66ed2c91351b667baf726f011d3522a9bb2e569046db5041e0242bfe080`. Noise SHA256 `248a65d462be827afe313523b3dd8481394ae0d627633c56bbe965037d84b410`.

**Documentation:** `docs/fine_tuning/m0_data_contract_verification.md`, `docs/fine-tuning-implementation-plan.md`, `docs/fine_tuning/model_asset_manifest.md`, `docs/fine_tuning/environment_manifest.md`, `docs/fine_tuning/biomap_reconstruction_decision.md`. Documentation only. Not committed. Not pushed.

## 2026-09-28 — Formal M1 released-inference execution

**Stage:** Aim 2 / modelling / M1 released inference

**Status:** COMPLETE / GO — 28 September 2026. The formal M1 human gate is GO. The released-inference milestone is closed. M2 is the next formal milestone. Numerical diffusion-training smoke remains formal M5 and remains pending after M2–M4.

**Design:** Six runs. Current lineage twice for B0 and twice for B1 at RNAGenesis `e20f5567526a6d76a173eba87e363e8edf130cd6`, worktree `/home/laura/RNAGenesis`. Released lineage once for B0 and once for B1 at `d00899eef60d664cc7b5880c0bb43f2a9e7a1b01`, worktree `/home/laura/rnagenesis-mres-worktrees/released-d00899e-m1`. Settings were a technical smoke: seed 42, eta 0.0, five DDIM steps, two sequences, `max_seq_len` 37. Guidance and search arguments were present and inert.

**Identity:** Current B0 run 1 and run 2 match. Current B1 run 1 and run 2 match. Released and current B0 raw outputs are byte-identical (`407ed27564fdc200f190ff78eddae04466dd4ba3e7d4a0c30c5af64e8a91f25d`). Released and current B1 raw outputs are byte-identical (`b5bf57a8977476e05119d380aeefa7a407daec002ecefad9ea747c1dd3ef835d`). B0 and B1 denoiser weights differ. The two-sequence B0 versus B1 output difference is not biological evidence.

**Cleaning:** Boundary-only rule. All 12 rows had raw prefix `11`, an empty suffix, raw length 38 and cleaned length 36. All 12 were accepted as A/C/G/U. Zero rows were rejected. Raw hashes were unchanged by cleaning.

**Audit utility:** `112a120282667c382790031fe74942f89f7b84eb`, subject `Add M1 generation output audit`. Pre-commit rerun: audit utility tests 16/16; lightweight trainer tests 39/39. Those tallies are not fields of the evidence JSON.

**Evidence:** `/home/laura/rnagenesis-mres-runs/m1_inference_e20f556/m1_released_inference_evidence.json`, SHA-256 `ec518b3f8f78de19227abe5a14e138bcf381c231bc888689a298a16c946ee774`. Authoritative MRes commit `6bb2aa8564d3493c598122545c0baa640b29bfe4`.

**Boundary:** No TRAIN, VALIDATION, REF or EVAL sequence was accessed. No backward pass, optimizer step, fine-tuning or model selection occurred. No biological-data, optimizer or fine-tuning boundary was crossed. No numerical training smoke was performed. The human gate chose the existing formal ordering. The broader “released-behaviour and numerical training smoke validation” wording does not reassign M5 work into M1. M2–M4 remain required before M5.

**Documentation:** `docs/fine_tuning/m1_released_inference_validation.md` and a current-status paragraph in the formal M1 section of `docs/fine-tuning-implementation-plan.md`. Documentation only. Not committed. Not pushed.

## 2026-09-28 — Formal M2 evidence assembly

**Stage:** Aim 2 / modelling / M2 published aptamer comparator verification

**Status:** COMPLETE / GO — 28 September 2026. The human gate approved B0 as the external aptamer-adapted comparator. Formal M2 is closed. M3 is the next formal milestone.

**Identity:** Scientific label `B0_released_aptamer_adapted_RNAGenesis`. Provenance `DIRECT_HUMAN_CONFIRMED_PROVENANCE`. Laura Hardy confirmed on 28 September 2026 that the ten tracked chunks are the B0 pool she generated earlier in 2026 from the authors’ released aptamer-fine-tuned RNAGenesis checkpoint. Historical `unadapted` path names are preserved obsolete labels. B0 is the authors’ released aptamer-adapted comparator, not generic, unadapted or pretrained-only. It is not D1 and it is not the length-matched causal baseline.

**Pool:** Raw 30,080; accepted 30,080; rejected 0; unique accepted 30,080; duplicate accepted 0. Raw length 38 throughout; cleaned length 36 throughout. Nominal `max_seq_len=37`. Numeric raw concatenation SHA-256 `ed612277105c6b8747fc7365cc6b67fa8a94e8e5e8e64ee535ecadcb37ff4aaa`. Pooled cleaned SHA-256 `51ccf2b997f1e6386438be303e5affaf908f102bd098bab243a2a9ba1d94d6e1`. Guidance and tree search were not enabled. Raw artifacts remained unchanged. Recovered settings and seeds are recorded in the M2 report. The missing contemporaneous 10 June checkpoint hash remains an explicit limitation. No biological-quality claim follows from syntactic acceptance or uniqueness.

**Execution:** Attempt 1 `SAFE_STOP_OUTPUT_DIRECTORY_ALREADY_EXISTED`; no cleaning. Attempt 2 PASS. Pooled evidence JSON SHA-256 `83ad84ee3c1cf49e8cbcd88cd31cd5580dbf16fb2994e7bba715c8b356f70f1d`. Raw hashes unchanged. Audit utility tests 16/16 under CPU-only Python 3.13.13. That test does not reproduce the Python 3.8 generation environment.

**Published metric:** `INFEASIBLE_WITH_RELEASED_EVIDENCE`. Version 1 (64,000/13,802) stays separate from versions 2 and 3 (25,600/13,802). No metric was calculated. This infeasibility is the documented “where feasible” outcome and is not a B0 pool-verification failure.

**Boundary:** No D1 training, generation, model selection, REF/EVAL access or unauthorised GPU use occurred. No GPU is currently authorised for later work. Numerical diffusion-training smoke remains formal M5.

**Documentation:** `docs/fine-tuning-implementation-plan.md`, `docs/fine_tuning/model_asset_manifest.md`, `docs/fine_tuning/m2_published_aptamer_comparator_verification.md` and `docs/log.md` are being committed and pushed in the closure commit.

## 2026-09-29 — M3 frozen corpus loader and modelling-interface evidence

**Stage:** Aim 2 / modelling / M3 frozen corpus loader and modelling-interface gates

**Status:** EVIDENCE COMPLETE / PENDING FINAL HUMAN GO — 29 September 2026. The tokenizer gate is PASS and the chemistry/no-silent-loss human gate is PASS. Formal M3 is not closed. Closure still requires exact-diff review, explicit-path staging, commit, push, live-remote confirmation, context-mirror refresh, and final human GO.

**Frozen inputs:** The M0-authorized H200 location is `/home/laura/rnagenesis-mres-data/development`. Repository-local `data/processed` held obsolete pre-correction copies with the wrong hashes and counts (`corpus_final.txt` `6f8c2091706cc28526ae53a1021395cad1b7943745ddffbaea631edc01df3340`, 678 lines; `ft_train.csv` `941fe8783ee8c99a2ce7598dea00ed123e62750026b7f157f28e7bbcc5d14a8f`, 746/678/571; `ft_validation.csv` `03be477e12f7b9ca20f8911e2ac88fde2949af2b6131c2d2aa43eef2ae6d9abc`, 149/117/64). Those copies were deliberately deleted and were not recreated. The authorized files match the frozen contract: corpus `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d` (37,700 bytes, 669 cores), TRAIN CSV `84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0` (726 identities, 669 cores, 569 clusters), VALIDATION CSV `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd` (132 identities, 95 cores, 63 clusters).

**Tokenizer audit:** All 669 TRAIN and 95 VALIDATION first-occurrence cores passed `encode_rna_characters` with `U=1`, `G=2`, `C=3`, `A=4`, byte-identical round trips, and no pad, special, or unknown ids. Configured maximum length 2048; observed maxima 123 and 94. All 37 repeated VALIDATION identity rows were audited. Chemistry stayed report-only, including missing and conflicting labels. No model-compatible sequence was dropped. No normalization, truncation, replacement, filtering, or automatic split was applied.

**Tests:** `pytest` is not installed in the pinned `rnagenesis-h200` interpreter. That missing optional runner is not a scientific failure. `python -m unittest -q tests.test_m3_frozen_tokenizer_gate` passed 15 tests.

**Artifacts:** `/home/laura/rnagenesis-mres-runs/m3_tokenizer_112a120_f2bdff1_attempt1`. `m3_tokenizer_audit.csv` `063a068187e5b34c598b1ef4a294f924f3167538aec824786d6e9fac01d4eb9f`; `m3_validation_duplicate_audit.csv` `bfc966dbaff60523ebb44a75fa610f83f08724b0277ba4ed6c9b2a9956d39697`; `m3_chemistry_report.json` `8192b0717a7d5791d06c842ea5ba07011a7502dd6c51a5da004e5ae84fedeb50`; `m3_summary.json` `8862ecb066fac12ae80529737a2398322227f8789af07c2de2d375279896638c`, status `PASS`.

**Boundary:** No GPU command, model or checkpoint load, full-corpus tokenization rerun, optimizer, training, generation, REF, or EVAL. Physical GPU 0 is authorised for 29 September 2026 and was not used. RNAGenesis remained `mres-d1-diffusion-finetune` at `112a120282667c382790031fe74942f89f7b84eb`. MRes remained `main` at `f2bdff1ade9e2aec9f37aaa23477ec40f3f21585`. The untracked gate and tests were not altered by this documentation edit. Nothing was staged, committed, or pushed. The context mirror was not refreshed.

**Documentation:** `docs/fine_tuning/m3_frozen_corpus_loader_and_modelling_interface.md`, plus the formal M3 status and the Section 22 milestone order in `docs/fine-tuning-implementation-plan.md`. Documentation only. Not committed. Not pushed.

## 2026-09-29 — Formal M3 closure

**Stage:** Aim 2 / modelling / M3 frozen corpus loader and modelling-interface gates

**Status:** COMPLETE / GO — 29 September 2026. Laura Hardy gave final human approval on 29 September 2026. Formal M3 is closed. M4 is the next formal milestone and has not begun.

**Implementation:** RNAGenesis branch `mres-d1-diffusion-finetune`, commit `e3b855bbf4d1af376f43747643fa30afd662828c`, subject `Add M3 frozen corpus tokenizer gate`.

**Evidence:** `/home/laura/rnagenesis-mres-runs/m3_tokenizer_112a120_f2bdff1_attempt1` remains the preserved evidence location.

**Boundary:** This closure does not start training, GPU work, or M4.

## 2026-10-01 — E1 structural-evidence wording aligned to the corrected corpus

**Stage:** Aim 2 / data curation / documentation only

**What was done:** The governing curation plan now states that E1 remains an experimentally verified aptamer–target complex structure, and that mmCIF URLs and AptamerBase structure flags are retained structural signals. In the corrected v1.6 corpus those signals were not assigned E1, because the applied CHECKPOINT-2 rule did not verify an aptamer–target complex for the curated relationship. The corrected final corpus contains no E1 rows. No data files, frozen corpus, or curation stages were changed.

## 2026-10-01 — Accept M4 CPU artifacts and close the B1 development-pool gate

**Stage:** Aim 2 / modelling / M4 B1 diagnostic pool

**Status:** CPU schedule and VALIDATION draw artifacts accepted. Execution remains closed. No active or consumable development-pool authorisation is stored. The self-referential authorization-commit field is not used.

**Accepted schedule:** `/home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1`. Schedule SHA-256 `0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0`. Length vector SHA-256 `7e6cb523a85116fc38788c336ef50c26e0eccc343712aaea89956a73c485bd3c`. 1,000 raw attempts, 112 invocations, NumPy 1.22.0, sampling seed 43000, invocation seeds `44000 + invocation_index`, maximum chunk 16, cap `target_length + 1`. No rejection, replacement, resampling, padding, trimming, dropping, or deduplication.

**Accepted VALIDATION draws:** `/home/laura/rnagenesis-mres-runs/m4_validation_draw_artifacts_d2b2041520d1`. Role VALIDATION, 95 sequences, 4 draws, seed 1. Manifest SHA-256 `b4e8d6d7cf7298d201062986419797e7fc322f2e88066764d4332a432a0d0d49`.

**Non-executable GPU proposal:** `m4_b1_development_pool_d2b2041520d1_gpu1_attempt1` records the intended physical GPU 1 binding, UUID `GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, PCI `00000000:61:00.0`, `CUDA_VISIBLE_DEVICES=1`, `CUDA_DEVICE_ORDER=PCI_BUS_ID`, logical `cuda:0`. It does not satisfy the executable authorisation schema. `authorization_parent_commit` and `executing_implementation_commit` stay unset until a later authorization-only commit. That later commit must not modify the runner. The runner will compute `authorization_commit` from live HEAD. RNAGenesis remains `mres-d1-diffusion-finetune` at `e3b855bbf4d1af376f43747643fa30afd662828c`. The CPU artifacts were materialised at `d2b2041520d176ebd10a1553cf1fec65ad447ac5`. Evidence directory not created.

**Boundary:** B0, B2, Phase A, and Phase B evidence unchanged. Clustering and frozen-representation metrics remain deferred. B1 success, checkpoint eligibility, M4 completion, M5, D1 training, REF, and EVAL remain unclaimed. Nothing was staged, committed, pushed, authorised, or executed.

## 2026-10-01 — Prepare the M4 B1 development-pool authorization

**Stage:** Aim 2 / modelling / M4 B1 diagnostic pool

**Status:** One unconsumed development-pool authorisation is prepared in the working tree. It is not staged, committed, pushed, or executed. The evidence directory is not created.

**Authorisation:** `development_pool_scientific_execution_authorisation`, id `m4_b1_development_pool_d2b2041520d1_gpu1_attempt1`, status `active_unconsumed`, consumed false. `authorization_parent_commit` and `executing_implementation_commit` are both `4de4246aa4a97eadaf30caf449e3046378832366`. The block does not store `authorization_commit`. The future authorization commit must have that commit as its single parent and must not modify `scripts/b1_development_pool_runner.py`. The runner computes `authorization_commit` from live HEAD.

**Binding:** Physical GPU 1, UUID `GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, PCI `00000000:61:00.0`, `CUDA_VISIBLE_DEVICES=1`, `CUDA_DEVICE_ORDER=PCI_BUS_ID`, logical `cuda:0`. RNAGenesis remains `mres-d1-diffusion-finetune` at `e3b855bbf4d1af376f43747643fa30afd662828c`. Schedule SHA-256 `0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0`. Length-vector SHA-256 `7e6cb523a85116fc38788c336ef50c26e0eccc343712aaea89956a73c485bd3c`. Output and evidence directory `/home/laura/rnagenesis-mres-runs/m4_b1_development_pool_d2b2041520d1_gpu1_attempt1`.

**Boundary:** Shared and development-pool execution gates are open for this one run. Phase A, Phase B, M5, D1 training, REF, and EVAL stay closed. Clustering and frozen-representation metrics stay deferred. Length mismatch and early EOS stay retained diagnostic outcomes. B1 success, checkpoint eligibility, and M4 completion stay unclaimed. Nothing was staged, committed, pushed, or executed.

## 2026-10-02 — Accept the B1 development pool and close M4

**Stage:** Aim 2 / modelling / M4 B1 diagnostic pool

**Status:** COMPLETE / GO — 2 October 2026. The GO authorises M5 planning only. It does not authorise M5 execution or D1 training.

**Preflight:** Branch `main`. Local HEAD, local `origin/main`, and live `origin/main` were `9c0624e9384e19930251355a6b1d61b2d4fdb153`. The tracked, staged, and untracked state was clean. The evidence directory existed. No B1 development-pool runner process was active. The idle tmux session `m4-b1-phase-b-gpu1` was a finished Phase B shell, not a runner. The single-run authorisation was active and unconsumed before this acceptance edit.

**Evidence:** `/home/laura/rnagenesis-mres-runs/m4_b1_development_pool_d2b2041520d1_gpu1_attempt1`, revalidated and not rewritten. Manifest `6a3e3be9d589443e82f2f8b0321c445e96f0f989b4984ec8c25ce10db48927c8`. Manifest hash report `15acfa7b7ee0fbaba27e03a3719f72c1b8fbc881d7e23ec7d0350df2fe5be99e`. Metrics `5c927839c94d78d575d787392da137c28f1310ef637b57bbb8b500e7dbf9b3ea`. Raw ledger `086d26458fc2363017c812dc65cb0440185ad6b4f8cfe4fc3377dfa74c5f292a`. Audited ledger `3aad5a0cd59405aca52a9800c47c1fe8f70e474d68b8a602e5fb1b8f5e14e150`. Invocation outputs `331308120e3ce7d672381178a06b1924dabd371cc5cfdaa8f9787e924725d572`. Schedule `0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0`. Schedule hash report `7ad13cf5155c55c5cb6ba24f91159c45cc3c3ffa51cd407a92a267e2e51407df`.

**Reconciliation:** 112 invocation files, 1,000 raw records, and 1,000 audited records. 1,000 parsed and valid outputs. Zero invalid outputs. 961 exact-length hits. Exact-hit rate 0.961. 39 early-EOS length shortfalls. Zero length excesses. 1,000 unique outputs and zero duplicates. Largest duplicate multiplicity 1 and share 0.001. The pool is a diagnostic generation sample reusable for the later paired D1 workflow. It is not an independent-biological-replicate set or an exact-length accepted production pool.

**Authorisation:** `m4_b1_development_pool_d2b2041520d1_gpu1_attempt1` is inactive, consumed, successful, and `consumed_complete`. Physical GPU 1, UUID `GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, and PCI `00000000:61:00.0` are preserved. This records consumption of the scientific authorisation. It does not claim that access to GPU 1 has been revoked.

**Boundary:** `exact_length_accepted_pool_declared`, `final_production_mapping_declared`, and `final_m8_production_protocol_declared` stay false. M5 execution and D1 training stay unauthorised. The accepted CPU schedule, VALIDATION artifacts, and B0, B2, Phase A, and Phase B evidence were revalidated and not rewritten. Clustering-dependent and frozen-representation metrics stay deferred beyond M4. VALIDATION ordering, timestep and noise artifacts, the checkpoint-selection rule, core sample guardrails, and D1 pilot fields stay in force. Microbatch size, gradient accumulation, numerical precision, and EMA stay deferred to M5. Nothing was staged, committed, pushed, or executed. M5 was not begun. D1 training was not begun.

## 2026-10-03 — Accept the M5 synthetic smoke and close M5

**Stage:** Aim 2 / modelling / M5 diffusion-training software smoke

**Status:** COMPLETE / GO — 3 October 2026. The GO authorises M6 planning only. It does not authorise M6 execution, biological TRAIN or VALIDATION access, D1 training, GPU use, REF, EVAL, or a new run.

**Human approval:** Laura Hardy, 3 October 2026. Approval-recorded timestamp `2026-10-03T00:23+10:00`, minute precision as supplied. Source: explicit authorisation in the M5 review chat, “approve to stage commit and push”. Scope: the exact reviewed documentation-only M5 evidence-acceptance and closure package. Explicitly not authorised: M6 execution, biological TRAIN or VALIDATION access, D1 training, GPU use, REF, EVAL, or a new run.

**Preflight:** MRes branch `main`. HEAD, local `origin/main`, and live `origin/main` were `9d818e11c18e33e95b48dda8b5b2a72870ca30b0`. The MRes worktree was clean. RNAGenesis branch `mres-d1-diffusion-finetune`, HEAD `e3b855bbf4d1af376f43747643fa30afd662828c`, was not fetched. No tracked RNAGenesis file was modified and nothing was staged. RNAGenesis was not modified. Attempt 3 manifest SHA-256 `e82ad082d7b66adce128cf6757e36be20bf3a0289d8aa2a9b5b10754b4f53532` matched `m5_smoke_manifest.sha256`. With CUDA hidden, bytecode disabled, offline settings, and an isolated cache, the untouched manifest was replayed through `build_final_manifest` and `canonical_json` at that commit. Reconstruction was byte-identical and the manifest SHA was unchanged. Checkpoint weights and `resume_sidecar.pt` were not read or hashed. Their closed manifest identities were used.

**Evidence:** `/home/laura/rnagenesis-mres-runs/m5_synthetic_smoke_e8550e7_gpu1_attempt3` is the sole accepted M5 smoke evidence. The run exited 0, emitted `m5_smoke_manifest.json` (64,245 bytes), and emitted no failure record. Execution implementation commit `e8550e7da095cfc6f17dd001425734e4bea6a3cb`. Single-use authorisation commit `d947d4eaef7cc1e7d85cdabbf83f7e02d4bfda72`. The manifest records execution contract SHA-256 `4fcfb5607c064d97f40163529ad43c568f98b74e95e41188ece9c565ebde3738` and harness SHA-256 `52ee776d3adcddc58d474fddb507df705bae3926b9f893e4a5e2a77c3ee8d656`. The replay contract at `9d818e11c18e33e95b48dda8b5b2a72870ca30b0` is SHA-256 `cbb9ff275149315c6a7cb227fafe5c2a0cd3d9b0a5375b296861945f0666ce3a`. The prior evidence-review archive SHA-256 is `5b101f6f963c77119e50ac2a84196ee4c5a05c45f76773aad1eadaf4cd359203`. Closed identities, not re-hashed: resume sidecar `bb22ab79dc04f56d10d8593a1c3cf317900173c59f4f58297ea329be217c0380`; `model_index.json` `05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e`; `scheduler/scheduler_config.json` `6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396`; `unet/config.json` `42c864c81e35ef1a0c7964a3642492fba95c9e24a153407f9fd98855b20d9d70`; `unet/diffusion_pytorch_model.safetensors` `cc5be013fca86125292855e61af8be28a64c1f97f95499958363b4eda89b989e`. The stored field `m5_milestone_complete` remains intentionally false in the immutable accepted manifest because the manifest records the automated correctness phase, while formal milestone completion occurred later through human review.

**Preserved failures:** `/home/laura/rnagenesis-mres-runs/m5_synthetic_smoke_1266a9b_gpu1_attempt1` and `/home/laura/rnagenesis-mres-runs/m5_synthetic_smoke_a634673_gpu1_attempt2` remain preserved failed engineering attempts. They are not accepted M5 evidence. Each exited 1, has a failure record, and has no final manifest. They were not rewritten.

**Measurements:** Physical GPU 1, UUID `GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, PCI `00000000:61:00.0`, NVIDIA H200 NVL. Physical microbatch 8. Gradient accumulation 4. Observed effective batch 32. FP32 correctness path. Finite loss and gradients. Gradient norm 5.4995274281909055. Denoiser update max absolute delta 3.0040740966796875e-05. The encoder, Q-Former, query tokens, latent projection, and decoder remained frozen after backward, update, and generation. Checkpoint fresh reload, AdamW state, scheduler, global step, RNG restoration, and the subsequent resumed update passed. Tiny overfit losses: 0.6921789050102234, 0.6151523590087891, 0.5786029696464539, 0.5625630617141724, 0.5575369596481323. Generation reloaded the immutable one-update checkpoint after the training objects were released. Training peak allocated 42,046,809,088 bytes. Training peak reserved 42,563,796,992 bytes. Overall peak allocated 72,871,646,208 bytes. Overall peak reserved 73,614,229,504 bytes. Total wall time 193.7824976965785 seconds. TRAIN, VALIDATION, REF, and EVAL were not accessed. Physical microbatch 8, gradient accumulation 4, and FP32 are M5-supported observations. EMA was disabled and smoke generation used raw weights. Those observations form a conservative M6 proposal only and are not automatically accepted M6 production decisions.

**BF16 observation:** FP32 paired loss 0.8125295639038086. BF16 paired loss 0.8128108978271484. Absolute difference 0.00028133392333984375. Relative difference 0.0003462445378457017. Finite. No acceptance tolerance was applied. It does not select production precision.

**Unresolved for M6 and D1 planning:** production numerical precision; production gradient accumulation and batch policy; EMA policy and raw-versus-EMA generation policy; final D1 seed count; biological training authorisation.

**Decoding caveat:** Both smoke generation strings contain a leading `1` followed by 32 A/C/G/U characters. Treat this as a decoder and control-token format observation, not a biologically valid sequence claim. Explicit output normalisation and nucleotide-alphabet validation are required before production generation or biological interpretation.

**Boundary:** `config/experiments/D1_diffusion_smoke.yaml` stays inactive. No GPU identity, output directory, evidence directory, or active authorisation was reintroduced. During the read-only evidence replay and review, no evidence, code, configuration, authorisation, model, biological-data file, or run artifact was modified. After human approval, the reviewed documentation-only M5 closure was staged, committed, and pushed as `49723b177c5e43879b4103050ff05d138b748dab`. This cleanup is documentation-only and remains unstaged and uncommitted during preparation. That closure records the existing attempt-3 run and leaves its evidence unchanged. M6 execution was not begun. D1 training was not begun. Biological TRAIN, VALIDATION, REF, and EVAL were not accessed.

## 2026-10-05 — Record M6 attempt 1 as a consumed failure

**Stage:** Aim 2 / modelling / M6 D1 diffusion pilot

**Status:** Attempt 1 is a consumed failed engineering attempt. The checked-in pilot configuration is restored to the inactive, non-consumable implementation state. This record does not authorise another run, GPU use, biological TRAIN or VALIDATION access, model loading, REF, EVAL, or diagnostic generation.

**Preflight:** MRes branch `main`. Local HEAD `ef31b8cef054dbbc5835ca03fbfb403a8ca49e45`. Its parent `4a2fd6f7e5784ad5c116949c5ee59814dc959f7c`. Local `origin/main` and live `origin/main` were `4a2fd6f7e5784ad5c116949c5ee59814dc959f7c`. RNAGenesis branch `mres-d1-diffusion-finetune`, commit `e3b855bbf4d1af376f43747643fa30afd662828c`.

**Evidence:** `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_4a2fd6f7e578_gpu1_attempt1` is immutable. `authorization_failure.json` SHA-256 `857b5be2ebe3742c853cefb39acea097d8c8712cfcc344a0ba0c12af89136126`. `authorization_consumption.json` SHA-256 `e6bcc942f39394f57b08afa1224bbb30d0cf58fb2fd5fd953677656027d83d2f`. `m6_pilot_manifest.json` is absent. No checkpoints are present. Completion is `consumed_failed`. `scientific_run_completed` is false. `retained_checkpoints_exist` is false. The failure record's stage, update, and microbatch are null. The original failure stage and the underlying exception are unrecoverable. Whether biological inputs or model weights were opened is unknown. The evidence directory was not altered.

**Defect:** `_record_consumed_failure` copied progress only onto an `M6PilotError`. `failure_payload` wrote an ordinary exception with null stage, update, and microbatch. `_raise_consumed_failure` then reopened that record, so its fallback stage could not repair it.

**Remediation:** After authorisation consumption, every exception records the latest stage, update, and microbatch. An ordinary exception remains `incomplete_evidence_or_manifest` and records its Python exception class in `authorized worker failed; exception_class=<ClassName>`. The exception message, traceback, sequence text, and tensor contents are omitted, and no traceback file is written. A precise `M6PilotError` keeps its code, detail, and context. A child failure record stays authoritative. A failure removes a claimed success manifest. `runtime_identity` is set before the training stack's Torch object is obtained. Authorisation reuse remains impossible and the failure remains non-resumable. `config/experiments/D1_diffusion_pilot.yaml` is restored from the inactive document at `4a2fd6f7e5784ad5c116949c5ee59814dc959f7c`. The working-tree authorisation binds no GPU, output directory, biological path, or executable authorisation.

**Boundary:** Nothing in this remediation was staged, committed, or pushed. The M6 runner was not executed. No new run directory was created. No GPU was used. Biological data and model weights were not opened for this remediation. GPU0 authorisation was not prepared.

## 2026-10-05 — Record M6 attempt 2 and correct pinned path types

**Stage:** Aim 2 / modelling / M6 D1 diffusion pilot

**Status:** Attempt 2 is a consumed failed engineering attempt. The checked-in pilot configuration is restored to the inactive, non-consumable document at `97cbb77d10472dd9ec75f61d1af9a6a69453b699`. This record does not authorise attempt 3, GPU use, biological TRAIN or VALIDATION access, model loading, REF, EVAL, or diagnostic generation.

**Preflight:** MRes branch `main`. Local HEAD `f5e94b583cd94aabe53f72ff9cca1b922b106485`. Its parent `97cbb77d10472dd9ec75f61d1af9a6a69453b699`. Local `origin/main` and live `origin/main` were `97cbb77d10472dd9ec75f61d1af9a6a69453b699`. The MRes tracked tree and index were clean. RNAGenesis branch `mres-d1-diffusion-finetune`, commit `e3b855bbf4d1af376f43747643fa30afd662828c`.

**Evidence:** `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_97cbb77d1047_gpu0_attempt2` is immutable. `authorization_failure.json` is 723 bytes, SHA-256 `f0b3cf0b7e871b0db46d4c4633cfc15dfae5afdd0c4c1d8751d74802cd6d716d`. `authorization_consumption.json` is 560 bytes, SHA-256 `dd24bfb8a4db78c0060f826d75c6286cf2e1bfa4896e0dce103ab49eb3416b1b`. `m6_pilot_manifest.json` is absent. No checkpoints are present. Completion is `consumed_failed`. The failure code is `incomplete_evidence_or_manifest`. The recorded exception class is `AttributeError`. The recorded stage is `biological_inputs`. Update and microbatch are null. `scientific_run_completed` is false. `pilot_completed` is false. `retained_checkpoints_exist` is false. `authorization_commit` is `f5e94b583cd94aabe53f72ff9cca1b922b106485`. `authorization_parent_commit` and `executing_implementation_commit` are `97cbb77d10472dd9ec75f61d1af9a6a69453b699`. Runtime identity and asset identity completed. The required model assets were read for identity hashing. Model objects were not loaded. TRAIN was opened, hashed, decoded, and counted before the adapter failed. VALIDATION and the validation artifacts were not reached. No optimizer update, checkpoint, success manifest, or scientific result exists. Existing GPU 0 processes were authorized and were not implicated in this failure. Attempt 1 may share the same cause, but its record cannot establish that. The evidence directory was not altered.

**Defect:** `PinnedTrainingStack.read_train_sequences` passed the authorised string path into pinned RNAGenesis `read_train_sequences(path: Path, ...)`. That function calls `path.is_absolute()` in `assert_allowed_input_path`. A string has no `is_absolute`, so the worker raised `AttributeError` at `biological_inputs`. The same string reaches `read_validation_cores` (`is_absolute()`), `load_b1_denoiser` (`resolve()`), and `save_diffusers_checkpoint` (`mkdir()`), which would raise `AttributeError` as well. `load_frozen_encdec` and `load_scheduler` pass `str(path)` into `from_pretrained`, so a string does not raise there and a `Path` is safe. Reload calls `TransformerDenoiser.from_pretrained`, which accepts `str` or `os.PathLike`. `load_verified_artifacts` already converts with `Path(directory)`.

**Remediation:** The adapter now passes `pathlib.Path` into `read_train_sequences`, `read_validation_cores`, `load_frozen_encdec`, `load_b1_denoiser`, `load_scheduler`, `save_diffusers_checkpoint`, and `TransformerDenoiser.from_pretrained`. The artifact loader's existing `Path(directory)` conversion is unchanged. RNAGenesis is not modified. CPU/mock tests use a fake trainer that rejects strings, records the received objects, and covers every audited path-bearing adapter method, including an integrated mocked pilot through checkpoint save. `config/experiments/D1_diffusion_pilot.yaml` is restored from the inactive document at `97cbb77d10472dd9ec75f61d1af9a6a69453b699`. The working-tree authorisation binds no GPU, output directory, biological path, or executable authorisation.

**Boundary:** Nothing in this remediation was staged, committed, or pushed. The M6 pilot was not executed. No new run directory was created. Attempt 1 and attempt 2 were not modified. No GPU was used. Biological data and model weights were not opened. The bytecode-disabled CPU/mock suite was run with CUDA hidden. Attempt 3 was not prepared.

## 2026-10-05 — Record M6 attempt 3 and correct the production worker directory

**Stage:** Aim 2 / modelling / M6 D1 diffusion pilot

**Status:** Attempt 3 is a consumed failed engineering attempt. The checked-in pilot configuration is restored to the inactive, non-consumable document at `712ba18568548adc73013818630c4e4101417a9a`. This record does not authorise attempt 4, GPU use, biological TRAIN or VALIDATION access, model loading, REF, EVAL, or diagnostic generation.

**Preflight:** MRes branch `main`. Local HEAD `4dd7f2c600322bf8134f57c491d10d08d86c3640`. Its parent `712ba18568548adc73013818630c4e4101417a9a`. Local `origin/main` and live `origin/main` were `712ba18568548adc73013818630c4e4101417a9a`. RNAGenesis branch `mres-d1-diffusion-finetune`, commit `e3b855bbf4d1af376f43747643fa30afd662828c`.

**Evidence:** `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_712ba1856854_gpu0_attempt3` is immutable. `authorization_failure.json` is 719 bytes, SHA-256 `8d2ed2687989eac3c165e0e158c2115435845bce3abf75e903fd8934371fe50d`. `authorization_consumption.json` is 560 bytes, SHA-256 `287f2b59f4efe2c3d170f2695e7dc250e14dc07f19a4f8068667c866f27d7c60`. `m6_pilot_manifest.json` is absent. No checkpoints are present. Completion is `consumed_failed`. The failure code is `incomplete_evidence_or_manifest`. The recorded exception class is `FileNotFoundError`. The recorded stage is `model_load`. Update and microbatch are null. `scientific_run_completed` is false. `pilot_completed` is false. `retained_checkpoints_exist` is false. `authorization_commit` is `4dd7f2c600322bf8134f57c491d10d08d86c3640`. `authorization_parent_commit` and `executing_implementation_commit` are `712ba18568548adc73013818630c4e4101417a9a`. Runtime, asset, TRAIN, VALIDATION, and validation-artifact stages completed. TRAIN and VALIDATION were opened and validated. Validation artifacts were opened and loaded. EncDec model loading began and failed on a runtime-relative file lookup. No optimizer update, checkpoint, success manifest, or scientific result exists. GPU 0 memory and its authorized concurrent processes were not implicated. The evidence directory was not altered.

**Defect:** `_default_spawn` started the production child with the MRes repository as `cwd`. RNAGenesis `util.py` defines `ProGenPath` as the relative string `models/autoencoder/decoder/progen_configs`. `load_frozen_encdec` constructs EncDec, whose constructor opens the decoder configuration and tokenizer beneath `ProGenPath`. Those relative files resolved beneath MRes. The pinned biomap RNA constructor reaches `config-progen2-small-rna_tokenizer_v2.json` and `tokenizer_rna_v2.json`, the hashed `decoder_config` and `tokenizer` assets. The biomap encoder config and xTrimo vocabulary resolve from `__file__`. `DATA_CACHE_DIR` is unused. Relative `XDG_CACHE_HOME` assignment is limited to `generation.py` and `models/guidance/classifier.py`, which the worker does not import. M5 used RNAGenesis as the worker working directory.

**Remediation:** The production child is launched with `cwd=/home/laura/RNAGenesis`. The production worker confirms that its resolved working directory is that pinned root before importing or invoking the training stack. An injected test `stack_loader` remains available. Runner, configuration, Git, output, checkpoint, evidence, cache, biological, and artifact paths stay absolute. Hugging Face, Torch, Python, and XDG caches stay under the consumed directory. RNAGenesis is not modified. `config/experiments/D1_diffusion_pilot.yaml` is restored from the inactive document at `712ba18568548adc73013818630c4e4101417a9a`. The working-tree authorisation binds no GPU, output directory, biological path, or executable authorisation. Permitted files, roles, data, GPUs, generation, resume, REF, and EVAL are unchanged.

**Boundary:** Nothing in this remediation was staged, committed, or pushed. The M6 pilot was not executed. No new run directory was created. Attempts 1, 2, and 3 were not modified. No GPU was used. Biological corpora, EncDec weights, and B1 weights were not opened. The bytecode-disabled CPU/mock suite was run with CUDA hidden. Attempt 4 was not prepared.

## 2026-10-05 — Record M6 attempt 4 and normalize the logical CUDA device

**Stage:** Aim 2 / modelling / M6 D1 diffusion pilot

**Status:** Attempt 4 is a consumed failed engineering attempt. The checked-in pilot configuration is restored to the inactive, non-consumable document at `7387bb2e5f7510508f3b87b4ac228ef341b1b39b`. This record does not authorise attempt 5, GPU use, biological TRAIN or VALIDATION access, model loading, REF, EVAL, or diagnostic generation.

**Preflight:** MRes branch `main`. Local HEAD `2262ba5840f92451a273ab766af3573fffa8382e`. Its parent `7387bb2e5f7510508f3b87b4ac228ef341b1b39b`. Local `origin/main` and live `origin/main` were `7387bb2e5f7510508f3b87b4ac228ef341b1b39b`. RNAGenesis branch `mres-d1-diffusion-finetune`, commit `e3b855bbf4d1af376f43747643fa30afd662828c`.

**Evidence:** `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_7387bb2e5f75_gpu0_attempt4` is immutable. `authorization_failure.json` is 660 bytes, SHA-256 `10896972516ca7e9781e0b3d1af2a214529b65692212ee3d3a8de4009209ab79`. `authorization_consumption.json` is 560 bytes, SHA-256 `4d2e962f104cbcc55bba79fbb0726ef36f918d4ca887d3d32f7e832a6971b04e`. `m6_pilot_manifest.json` is absent. No checkpoints are present. Completion is `consumed_failed`. The failure code is `identity_mismatch`. The failure detail is `logical device is not cuda:0`. The recorded stage is `model_load`. Update and microbatch are null. `scientific_run_completed` is false. `pilot_completed` is false. `retained_checkpoints_exist` is false. `authorization_commit` is `2262ba5840f92451a273ab766af3573fffa8382e`. `authorization_parent_commit` and `executing_implementation_commit` are `7387bb2e5f7510508f3b87b4ac228ef341b1b39b`. Model loading and `Accelerator.prepare` were reached. The logical-device check immediately after `prepare` failed before EncDec placement. No optimizer update, checkpoint, success manifest, or scientific result exists. The evidence directory was not altered.

**Defect:** Installed Accelerate 0.25 `PartialState.default_device` returns `torch.device("cuda")` when CUDA is available. `PartialState.device` is assigned from that value, and `Accelerator.device` returns `self.state.device`. `str(torch.device("cuda"))` is `cuda`, its type is `cuda`, and its index is `None`. `str(torch.device("cuda", 0))` is `cuda:0`. `assert_prepared_runtime` compared `str(accelerator.device)` directly with `cuda:0`, so the unindexed Accelerate device raised `identity_mismatch` at `model_load`.

**Remediation:** The prepared-runtime check still requires exactly one Accelerate process and exactly one visible CUDA device. It normalizes `accelerator.device` with the supplied torch module. The device type must be `cuda`. An explicit index must be 0. An index of `None` is resolved with `torch.cuda.current_device()` and must be 0. The normalized `torch.device("cuda", 0)` is the device passed to placement and to the training and validation workflow. Malformed devices, CPU devices, explicit `cuda:1`, an unindexed CUDA device whose current index is not 0, and failures while resolving the current device remain `identity_mismatch`. Physical GPU UUID, PCI, `CUDA_VISIBLE_DEVICES`, device count, process count, precision, and accumulation checks are unchanged. The authorization and manifest logical device stays `cuda:0`. Accelerate and RNAGenesis are not modified. `config/experiments/D1_diffusion_pilot.yaml` is restored from the inactive document at `7387bb2e5f7510508f3b87b4ac228ef341b1b39b`. The working-tree authorisation binds no GPU, output directory, biological path, or executable authorisation.

**Boundary:** Nothing in this remediation was staged, committed, or pushed. The M6 pilot was not executed. No new run directory was created. Attempts 1, 2, 3, and 4 were not modified. No GPU was used. Biological corpora, EncDec weights, and B1 weights were not opened. The bytecode-disabled CPU/mock suite was run with CUDA hidden. Attempt 5 was not prepared.

## 2026-10-06 — Record M6 attempt 5 and correct checkpoint configuration evidence

**Stage:** Aim 2 / modelling / M6 D1 diffusion pilot

**Status:** Attempt 5 is a consumed failed engineering attempt. The checked-in pilot configuration is restored to the inactive, non-consumable document at `8b6dc1f1be7005f05290405740939962a7c988b5`. This record does not authorise attempt 6, GPU use, biological TRAIN or VALIDATION access, REF, EVAL, resume from the attempt-5 checkpoint, or diagnostic generation.

**Preflight:** MRes branch `main`. Local HEAD `afe29597147dc3740d5695bb17439b6266263031`, the unpushed and consumed attempt-5 authorization commit. Its single parent, and local and live `origin/main`, is `8b6dc1f1be7005f05290405740939962a7c988b5`. RNAGenesis branch `mres-d1-diffusion-finetune`, commit `e3b855bbf4d1af376f43747643fa30afd662828c`, with the accepted untracked state unchanged.

**Evidence:** `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_8b6dc1f1be70_gpu1_attempt5` is immutable. Physical GPU 1, UUID `GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, PCI `00000000:61:00.0`, `CUDA_VISIBLE_DEVICES=1`, logical `cuda:0`. `authorization_failure.json` is 708 bytes, SHA-256 `d4a14b1231ce08fac2bebd6bbf80022fa6469e2da6ef886e3ecf2faee68d55dc`. `authorization_consumption.json` is 560 bytes, SHA-256 `c5e2f310c3260a6953107af68b9a07b17953dd9757e86f9d2fba83db8cc69d5a`. Both were re-hashed and matched. `m6_pilot_manifest.json` is absent. The failure is `incomplete_evidence_or_manifest`, exception class `TypeError`, stage `checkpoint`, update 7, microbatch null, no retained checkpoint. Updates 1 through 7 completed. The physical update-7 checkpoint directory is present, unverified, non-retained, non-resumable, and unsuitable for interpretation or later training. This remediation did not modify or hash the attempt-5 checkpoint. A separate earlier read-only CPU diagnostic opened it solely to reload the denoiser and made no writes.

**Defect:** Diffusers 0.25.0 stores the `pathlib.Path` given to `from_pretrained` in `config["_name_or_path"]`. `_config_mapping` returned it unchanged, and `assert_configuration_compatible` hashed the raw mapping with `canonical_json`, which raised `TypeError: Object of type PosixPath is not JSON serializable`. The contract already ignored top-level `_name_or_path` for compatibility but hashed the raw mapping first. A read-only CPU diagnostic showed the fresh reload itself succeeds. The same `TypeError` was reproduced here with real Diffusers 0.25.0. The `_use_default_values` hypothesis was disproved and no fix was made for it. The state comparison also ran before the configuration check.

**Remediation:** A top-level `_name_or_path` implementing `os.PathLike` is converted with `os.fspath` and must be `str`. No other key is converted, nested `_name_or_path` stays covered, there is no `default=str`, and the ignore list is unchanged. The proof order is structure, inventory, configuration, then state, with a spy test. Checkpoint progress is split into seven substages with controlled `checkpoint_save_reload_incompatibility` failures that record the class name only. The exact checkpoint tree is checked with `lstat` before hashing and after reload. `state_entry_digest` streams bytes in bounded chunks with digests proven identical to the earlier implementation. Tensor subclasses are hashed by bytes. `write_atomic_json` handles short writes and cleans up its temporary file.

**Benchmark:** The earlier `bytes(untyped_storage())` extraction ran at 0.43 to 0.46 MiB/s. The streaming digest ran at about 1,300 to 1,555 MiB/s. Digests were identical across 25 dtype and layout combinations. No GPU was used, so device transfer was not measured. The earlier rate is of the order of the observed 8 hours 47 minutes between the last checkpoint-member write time and the failure record, but it does not fully reconcile with the pre-checkpoint timeline, so it is recorded as consistent and not as a proven cause.

**Deferred:** The verification-to-consumption window for TRAIN, VALIDATION, and validation artifacts; `st_nlink` on checkpoint leaves; a directory `fsync` after the atomic replace.

**Boundary:** Nothing in this remediation was staged, committed, or pushed. The M6 pilot was not executed. No attempt-6 configuration, timestamp, or output directory was created. No GPU was used. REF and EVAL were not accessed. Attempts 1 through 5 were not modified. The bytecode-disabled CPU/mock suite was run with CUDA hidden. Attempt 6 was not prepared.

---

## 2026-10-06 — Record M6 attempt 6 as the accepted training pilot and prepare update-21 diagnostic generation

**Stage:** Aim 2 / modelling / M6 D1 diffusion pilot

**Status:** Attempt 6 is the accepted successful training pilot. At that stage, **M6 was not complete** and update-21 diagnostic generation was then pending and needed a separate authorisation (both resolved by the closure entry below). This record did not authorise diagnostic generation, M7, REF, EVAL, GPU use, TRAIN or VALIDATION access, or any new run.

**Preflight:** MRes branch `main`. Local HEAD `15f49a17081f573970495891e9283a17fc5c3dc2`, the unpushed and consumed attempt-6 authorization commit. Its single parent, and local and live `origin/main`, is `6fd611589d7a3365b793c2ca64cf13c29ef5bfc1`. The index was empty and the working tree clean. RNAGenesis stayed read-only on `mres-d1-diffusion-finetune` at `e3b855bbf4d1af376f43747643fa30afd662828c` and was not fetched.

**Evidence:** `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_6fd611589d7a_gpu1_attempt6`. `m6_pilot_manifest.json` is 159,013 bytes, SHA-256 `4b24d5bf5bc392a8f6ee4b8af91adb3582e3a17cac459559632494ec64f8ae52`, canonical JSON, `pilot_completed`, `consumed_successfully`. `authorization_consumption.json` is 560 bytes, SHA-256 `ec822747cca4916331fd7a79dd504a54c425bc7699457ca6d85e9b0c446f0874`. No `authorization_failure.json`. Both small files were re-hashed and matched. The checkpoint weights were not opened or hashed. Their identities are the closed manifest's: update 7 `7f1cdbd854c1d26c5b8bfe68469bc7e59f5d7293c4a105d724c1c63c83a32f10`, update 14 `0a2fa065f962adaf54e63b797974367915a6552382a8db76c3fbd0c6a0078901`, update 21 `47b2dc9b392ea766eee7e947f0f92f5a039c42ac714326104e719352d20b5924`. The evidence was not rewritten, moved, or deleted.

**Result:** Fixed-draw VALIDATION MSE was `0.1404131591699728` at update 0, `0.10955412184224482` at update 7 (−21.977%), `0.10202736076728462` at update 14 (−27.338%), and `0.10076265001606723` at update 21 (−28.238%). All 21 updates changed the denoiser. All losses and gradients were finite. Only update 6 was clipped (pre-clip norm `1.0183641910552979`, applied 1.0). Peak allocated memory was 42,045,783,552 bytes and peak reserved 42,633,003,008 bytes. The EncDec was unchanged. Updates 7, 14, and 21 each passed fresh reload, configuration compatibility, and exact comparison of 366 state entries. No stop condition fired and no warning was recorded. REF and EVAL were not opened. The figures above were cross-checked against the closed manifest.

**Decision boundary:** The `3e-5` pilot passed and no reduction to `1e-5` is proposed. FP32, microbatch 8, accumulation 4, effective batch 32, EMA disabled, and raw weights remain the conservative supported configuration. The complete M7 configuration is not frozen. Updates 7 and 14 stay learning-curve evidence only. Update 21 is the sole D1 pilot checkpoint for the pending comparison, which reuses the accepted B1 pool.

**Configuration:** `config/experiments/D1_diffusion_pilot.yaml` is restored to the inactive blob `4c0ef9b700f0c4566e1fdaa71dc68c25370712f0` (SHA-256 `1d31b4bca55c2c22c477220449781bb7b494bd6f26a3f575b547012566e3fe9f`) from `6fd611589d7a3365b793c2ca64cf13c29ef5bfc1`.

**Prepared, inactive:** `config/experiments/D1_update21_diagnostic_generation.yaml`, `scripts/modelling/m6_diagnostic_generation.py`, and `tests/modelling/test_m6_diagnostic_generation.py`. The design reuses the accepted B1 development-pool runner, the M4 metrics module, the M6 contract, and the approved M1 cleaner, each pinned by hash. It generates exactly 1,000 raw attempts from the raw update-21 checkpoint on the accepted schedule (`0f527d44…1702f0`, length vector `7e6cb523…bd3c`). It compares against the accepted B1 pool without regenerating it, keeps raw and normalised text together, and keeps every invalid, empty, duplicate, early-EOS, and length-mismatched attempt in its denominator. The five hard guardrails keep their approved thresholds. Requested-length exact-hit rates are reported, not enforced. Nearest-TRAIN edit distance, maximum TRAIN identity, nucleotide and dinucleotide distributions, MFE, MFE per nucleotide, paired fraction, and length-stratified results are report-only. TRAIN is opened for exact-copy and nearest-TRAIN diagnostics only. VALIDATION is not requested. REF and EVAL are refused before open. The document binds no GPU, output directory, timestamp, or authorisation, and the entry point accepts only `--help`. Details are in [M6 pilot implementation](fine_tuning/m6_pilot_implementation.md) section 11.

**Finding for review:** The accepted B1 pool has 39 of 1,000 early-EOS attempts with a trailing `2`. They are valid under the approved M1 cleaner. The stricter exact-`11`, no-suffix helper in the M6 contract would reject them, and the accepted B1 pool would then fail the 0.99 valid-fraction guardrail itself. The diagnostic uses the M1 cleaner and reports the stricter helper only as a sensitivity count. This is an open decision for the reviewer.

**Tests:** CPU/mock only, CUDA hidden, bytecode disabled, offline controls, caches outside both repositories, pinned Python 3.8.13. `tests/modelling`: 232 tests passed, of which 69 are the new file. `tests/test_b1_development_pool_runner.py` 30, `tests/test_b1_generic_runner.py` 62, `tests/test_b1_phase_b_runner.py` 35, and `tests/test_null_model.py` 54 passed, each in its own process. `tests/data_preparation` and `tests/test_stage1_hard_filter.py` cannot run here because no interpreter has pytest, which is unchanged.

**Boundary:** Nothing was executed on a GPU. No diagnostic generation, output directory, or checkpoint load occurred. TRAIN, VALIDATION, REF, and EVAL were not opened. B1 was not regenerated. M7 was not started. RNAGenesis and every accepted evidence directory were not modified. Nothing was staged, committed, or pushed.

---

## 2026-10-06 — Revise the inactive update-21 diagnostic package after archive review

**Stage:** Aim 2 / modelling / M6 D1 diffusion pilot

**Status:** The inactive package was revised in place. At that stage, M6 was not complete. No diagnostic authorisation, output directory, GPU execution, TRAIN access, checkpoint access, M7, REF, or EVAL occurred, and nothing was staged, committed, or pushed.

**Decided policy:** The approved M1 cleaner is the primary normalisation authority. The exact-`11`, no-suffix helper is sensitivity only. VALIDATION stays unopened, and REF and EVAL stay structurally denied. The frozen EncDec assets are rehashed. `maximum_identity_to_train` was renamed `maximum_edit_similarity_to_train`, defined as one minus the minimum Levenshtein distance divided by the longer sequence length, and never called sequence identity. The frozen approved files `config/modelling/validation_metrics_v1.yaml` and `config/experiments/generator_evaluation.yaml`, the plan, and two earlier reports still use the older wording and were not touched.

**Changes:** The output directory and consumption record are now created before TRAIN is opened or the checkpoint is read, hashed, or loaded. Catchable `KeyboardInterrupt` and `SystemExit` after consumption become a message-safe failure record before propagating. `authorization_failure.json` now records the schema, status, code, controlled detail, identities, output directory, consumption state, GPU binding, stage, invocation index, checkpoint state, and the non-resumable and not-complete flags. Success-manifest validation is exhaustive with exact nested key sets and cross-field checks. The written manifest is reopened, must be canonical, is validated independently, and every emitted file is verified against the manifest, or the manifest is withdrawn. Active-authorisation validation now requires the basename to equal `authorisation_id`, the offset timestamp format, and symlink-free run-root and output ancestry. The launch script must fetch `origin/main` and compare the live remote before the authorisation commit and immediately before launch.

**Tests:** CPU/mock only, CUDA hidden, bytecode disabled, offline controls, caches outside both repositories. `tests/modelling` 255 passed, including 92 in the diagnostic file. The B1 development-pool (30), generic (62), phase B (35), and null-model (54) suites passed, each in its own process.

---

## 2026-10-06 — Final evidence hardening of the inactive update-21 diagnostic package

**Status:** Revision 3 of the inactive package. At that stage, M6 was not complete. No authorisation, real output directory, TRAIN or checkpoint access, GPU use, M7, REF, or EVAL occurred. Nothing was staged, committed, or pushed. All rev2 policy and execution behaviour is preserved.

**Changes:** Success-manifest provenance is bound to the active authorisation, the measured provenance, and the pinned generation-input and EncDec/patch inventories. Written-evidence reverification reruns the pinned M4 metrics and five guardrails from the audited ledger and the pinned TRAIN cores, including `exact_train_match_rate`, and requires equality with the metrics file, the guardrail file, the manifest, and both sides of the comparison (B1 against the recomputed accepted reference). The report and hash report receive the regular, non-symlink, exact-size check. Output ancestry must be real directories. Adversarial regression tests cover each case.

---

## 2026-10-06 — Accept the update-21 diagnostic and close M6

**Stage:** Aim 2 / modelling / M6 D1 diffusion pilot

**Status:** M6 is COMPLETE / GO for M7 planning only. On 6 October 2026 the human gate approved: "Approve M6 closure and update-21 checkpoint selection for M7 planning only." The raw update-21 checkpoint is selected. This record does not authorise M7 execution, additional training or generation, GPU use, biological-data access, VALIDATION, REF, or EVAL, and the complete M7 configuration is not frozen.

**Preflight:** MRes branch `main`. Local HEAD was `0682185758eb62d9401706b1e37e02468c4c9fbb`, the single-use authorization commit, not yet pushed at that time, with the single parent `6953687e2e9e36bb1670a7b2b9faaa18849c3711` and changing only the diagnostic YAML. Local and live `origin/main` were `6953687e2e9e36bb1670a7b2b9faaa18849c3711`. The index and worktree were clean. RNAGenesis stayed on `mres-d1-diffusion-finetune` at `e3b855bbf4d1af376f43747643fa30afd662828c`, unmodified and not fetched.

**Evidence:** The update-21 diagnostic generation was executed once under the single-use authorisation `m6_d1_update21_diagnostic_6953687e2e9_gpu0_attempt1` on physical GPU 0 (UUID `GPU-b3c42ea9-ec47-c854-e469-cd78e443c76b`, PCI `00000000:41:00.0`, `CUDA_VISIBLE_DEVICES=0`, logical `cuda:0`). The authorization commit is `0682185758eb62d9401706b1e37e02468c4c9fbb`. Its sole parent and the executing implementation commit are `6953687e2e9e36bb1670a7b2b9faaa18849c3711`. Immediately before authorization and throughout execution and closure review, local and live `origin/main` remained `6953687e2e9e36bb1670a7b2b9faaa18849c3711`; the authorization commit had not yet been pushed. The evidence directory is `/home/laura/rnagenesis-mres-runs/m6_d1_update21_diagnostic_6953687e2e9_gpu0_attempt1`. `m6_diagnostic_manifest.json` is 86,206 bytes, SHA-256 `95074f0d76ab11cf43146e672bc75399da56dd9b2ffeef8fa14a39c7f8acd959`, canonical JSON, authorisation state `consumed_successfully`. No `authorization_failure.json` exists. The compact review summary is `/home/laura/m6-review-archives/m6_update21_diagnostic_attempt1_compact_summary.txt` (7,906 bytes, SHA-256 `7795371f2815370d1387dd4245b66a436d734dfba9c4d427bf4af0ede9c230bc`). All 112 scheduled invocations completed, giving 1,000 raw attempts, 1,000 parsed and valid outputs, 0 invalid or empty outputs, 1,000 unique valid outputs, and 0 duplicates. The exact-length hits were 971 (rate `0.971`, report-only), and 29 early-EOS observations and length mismatches were retained in their denominators. The checkpoint weights were identical before and after generation. Raw update-21 weights were used, EMA was not used, and no other checkpoint update and no B1 diffusion weights were loaded. All five preregistered hard guardrails passed:

**Guardrails:** all five passed: valid fraction `1.0`, empty fraction `0.0`, unique fraction `1.0`, exact TRAIN match rate `0.0`, largest duplicate share `0.001`.

**Interpretation:** descriptive only. D1 against B1: exact-hit rate `0.971` against `0.961`, early EOS 29 against 39, maximum edit similarity to TRAIN `0.6571428571428571` against `0.6666666666666667`, mean nearest-TRAIN normalized edit distance `0.4447902555859842` against `0.44196911254273263`, nucleotide total variation `0.0378592381533492` against `0.05944973828983485`, dinucleotide total variation `0.08128290946173325` against `0.08459451208560434`, mean MFE `-10.997260006524623` against `-10.294600009977817`, mean MFE per nucleotide `-0.17954261954423192` against `-0.16933682358738514`, mean paired fraction `0.44445466775022013` against `0.4447719803195546`. This is not a paired significance test. No statistical significance, biological-quality improvement, clustering, embedding, or downstream performance is claimed.

**Closure review:** read-only. Every top-level evidence file and all 112 raw invocation files were re-hashed. The hash report, every manifest ledger binding, metrics, guardrails, report comparison, report hash, identities and accounting were verified, and the pinned M4 metrics were recomputed from the audited ledger. TRAIN, the checkpoint, model assets, and B1 evidence were not reopened. The run directory and all earlier evidence were not modified.

**Configuration:** `config/experiments/D1_update21_diagnostic_generation.yaml` is restored to the exact inactive blob `d33a0284b7edf81b922364eb4838b9f52a551d57` (SHA-256 `a7b1055d6dc3fc07419313a7226321e1648ebd23477b290c5b0cc9000e3da2db`), non-consumable and unauthorised. Production code and tests were not changed.

**Boundary:** Nothing was staged, committed, or pushed. No M7 authorisation or output directory, no tmux session, no GPU use, and no scientific workflow ran.

---

## 2026-10-06 — Inactive M7 final-replicate implementation package

**Stage:** Aim 2 / modelling / M7 final D1 replicate training

**Status:** `M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED`. This is authorised implementation work, not M7 execution authorisation. No biological data (TRAIN, VALIDATION, REF, or EVAL) and no model or checkpoint weights were accessed. No GPU was used and `nvidia-smi` was not run. No run or evidence directory was created. No M7 authorisation or execution binding exists. Seeds 43 and 44 have not run. M7 is not complete. Nothing was staged, committed, pushed, or fetched.

**Preflight:** MRes `main` at `a58528d61c775cb5208ddb7efb3988dc3bd3fe88`, tracked tree and index clean, local HEAD and `origin/main` equal, M6 pilot YAML blob `4c0ef9b700f0c4566e1fdaa71dc68c25370712f0` and diagnostic YAML blob `d33a0284b7edf81b922364eb4838b9f52a551d57`. RNAGenesis `mres-d1-diffusion-finetune` at `e3b855bbf4d1af376f43747643fa30afd662828c`, tracked tree and index clean, accepted untracked assets unchanged. RNAGenesis was not fetched or modified. The accepted M6 evidence directories were not opened.

**Decisions implemented:** training seeds 43 and 44 (pilot seed 42 excluded, validation-draw seed 1 separate); one completed seed only through a sealed operational deviation; every seed initialised independently from the generic B1 checkpoint with M6 updates 7, 14 and 21 forbidden as initialisation or resume inputs (paths, names and weight hashes); five epochs of 84 microbatches and 21 updates (105 per seed), microbatch 8, accumulation 4, effective batch 32, final window `[8, 8, 8, 5]` at every epoch boundary; FP32, AdamW at `3e-5`, EMA off, raw weights; the M6 explicit applied-update LR convention generalised to ten warm-up updates and cosine decay over 105 updates (trace hash `37013ac0a50290dbb476f4cdec806f058b8fb3347d967ac2d6e59b6e07aeae50`, no zero applied rate); validation at update 0 (provenance only) and after every epoch; one proved checkpoint per epoch; ranking by fixed-draw VALIDATION MSE then earlier epoch; lazy candidate guardrails with `no_eligible_checkpoint` and no automatic change; resume unsupported with a new-directory, new-authorisation retry; checkpoint retention through at least 1 November 2026 with no deletion; the frozen M8 boundary of 30,000 raw D1 attempts; and the operational cutoff (18:00 AEDT 7 October stretch, 17:00 AEDT 8 October hard, `current time + 1.25 x seed-43 time + 2 hours`), recorded and not automated.

**New files:** `config/experiments/D1_final_replicates.yaml`, `D1_candidate_guardrails.yaml`, `D1_final_selection.yaml` (inactive, non-consumable); `scripts/modelling/m7_common.py`, `m7_replicate_contract.py`, `m7_replicate_runner.py`, `m7_candidate_guardrails.py`, `m7_selection.py`; `tests/modelling/test_m7_common.py`, `test_m7_replicate_contract.py`, `test_m7_replicate_runner.py`, `test_m7_candidate_guardrails.py`, `test_m7_selection.py` and the fixture module `m7_support.py`; `docs/fine_tuning/m7_final_replicates_implementation.md`. The M7 sections of the plan, the validation protocol and the manifest schema, and this log were updated. No M5 or M6 source, test or configuration was changed.

**Design:** the entry points accept only `--help` and `--schema`. The authorisation schema supports one authorisation-only commit with up to two independently consumable entries (one per seed), each binding the seed, implementation commit, physical and logical GPU identity, exact output directory, configuration and artifact hashes, and the full epoch and checkpoint universe. A launcher accepts only an authorisation id (not wired to the command line). The worker runs one seed per process, with a strict allow-listed child environment, isolated home, temporary and cache directories, runtime GPU identity checks, a free-space budget, REF, EVAL and sibling-evidence denial before any open, streaming digests, symlink-safe, single-link, same-device checkpoint inventories, atomic writes with parent-directory `fsync`, and a message-safe failure record for every `BaseException` after consumption with a secondary-failure report. Three separate manifests (replicate, candidate-guardrail, final-selection) keep seed evidence, candidate evidence and the selection apart. The final-selection manifest records `human_gate_required: true` and `m7_complete: false`.

**Tests:** CPU and mock only, CUDA hidden, offline controls, bytecode disabled, caches outside both repositories. 165 focused M7 tests pass (44, 31, 38, 25 and 27 by file). `tests/modelling` passes with 433 tests (268 existing plus 165 new). The B1 development-pool (30), generic (62), phase B (35) and null-model (54) suites passed, each in its own process. `tests/data_preparation` and `tests/test_stage1_hard_filter.py` cannot run here (no pytest) and were not run.

**Residual limitations and deferred findings:** the hash-to-open TOCTOU window is documented, not solved. The candidate-generation callable (the 112-invocation loop) is injected and not implemented. The real GPU identity read cannot be exercised without a GPU. `LD_LIBRARY_PATH` is not inherited by the child. The five-checkpoint reload digest cost has not been measured. See the implementation document, section 10.

**Boundary:** no tmux session, no GPU use, no scientific workflow, and no biological or weight access occurred. A code-only review archive was prepared outside both repositories.

---

## 2026-10-06 — M7 production candidate-generation callable and `LD_LIBRARY_PATH` binding (package still inactive)

**Stage:** Aim 2 / modelling / M7 final D1 replicate training

**Status:** `M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED`, unchanged. This is a bounded correction to the inactive package, not an authorisation. No biological data (TRAIN, VALIDATION, REF, or EVAL), model weight, checkpoint, or run or evidence directory was opened, created, or read; no GPU was used and `nvidia-smi` was not run; no M7 authorisation, GPU, output directory or timestamp is bound; seeds 43 and 44 have not run; M7 is not complete. Nothing was staged, committed, pushed, or fetched. The only filesystem observation outside the repositories was a directory listing of the run root, to confirm that no M7 directory exists.

**Production callable.** `production_generate_and_measure` is now the default of `run_candidate`, wired through `launch_authorised_candidate` and the entry point's `--authorisation-id` (which refuses while the configuration is inactive). It runs the accepted 1,000-attempt schedule in 112 invocations (seed `44000 + index`) through the pinned generator with only `--dm_file` substituted, the approved M1 cleaner, the five numerical guardrails, report-only length behaviour, raw weights only, and retained raw and normalised ledgers bound by hash. It binds the checkpoint to its sealed replicate manifest and checks the ranking prefix before generating; it refuses update 0, epochs outside 1 through 5, unexpected seeds, unlisted or mismatching checkpoints, M6 and sibling paths, REF and EVAL before any filesystem access, and consumed or already evaluated candidates. A failed invocation is recorded with its exact index and sub-stage. M5 and M6 files were not modified; the accepted M6 diagnostic module is reused by its tracked path.

**`LD_LIBRARY_PATH`.** Not inherited. An entry binds `null` or one exact value; the launcher requires the live value to match before consumption, only that value enters the child, the worker re-checks it, and the manifests record its SHA-256. The inactive configurations bind none. This preserves the known-working M6 runtime without restoring wholesale environment inheritance. The value to bind must be observed at authorisation time; it was not read here. Two defects found by the new tests were fixed (a second worker isolation check, and the manifest digest comparison).

**Changed files:** `scripts/modelling/m7_candidate_guardrails.py`, `m7_common.py`, `m7_replicate_contract.py`, `m7_replicate_runner.py`; the three inactive YAMLs (`D1_candidate_guardrails.yaml`, `D1_final_replicates.yaml` for schema keys only; `D1_final_selection.yaml` unchanged); `tests/modelling/m7_support.py`, `test_m7_common.py`, `test_m7_replicate_contract.py`, `test_m7_replicate_runner.py`, `test_m7_candidate_guardrails.py`, new `test_m7_candidate_generation.py`; the implementation document, the manifest schema, the validation protocol, and this log.

**Tests:** CPU and mock only, CUDA hidden, offline controls, bytecode disabled, caches outside both repositories. 235 focused M7 tests pass (54, 35, 44, 26, 49 and 27 by file). `tests/modelling` passes with 503 tests. The B1 development-pool (30), generic (62), phase B (35) and null-model (54) suites passed, each in its own process. The M6 YAML blobs are unchanged (`4c0ef9b700f0c4566e1fdaa71dc68c25370712f0`, `d33a0284b7edf81b922364eb4838b9f52a551d57`) and RNAGenesis tracked state is clean at `e3b855bbf4d1af376f43747643fa30afd662828c`.

**Deferred findings:** the hash-to-open TOCTOU window; the generator has never run for real; the GPU identity read; the `LD_LIBRARY_PATH` value is not yet chosen; checkpoint-digest and EncDec-hash cost; the replicate runner's `--authorisation-id` is not wired to its launcher; the candidate launcher does not re-read predecessor manifests. See the implementation document, section 10.

---

## 2026-10-06 — M7 final bounded corrections: wired launcher, predecessor evidence, diagnostics, inspection, interpreter (package still inactive)

**Stage:** Aim 2 / modelling / M7 final D1 replicate training

**Status:** `M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED`, unchanged. All three configurations remain inactive and non-consumable, with `authorisation_entries: []` and no GPU, UUID, PCI bus, output directory, timestamp, `LD_LIBRARY_PATH`, interpreter or predecessor value bound. No biological data, model weight, checkpoint, accepted evidence, GPU or live interpreter was touched or executed; no M7 run or evidence directory exists; seeds 43 and 44 have not run; M7 is not complete. Nothing was staged, committed, pushed, or fetched. No M5 or M6 file changed.

**Replicate launcher wired.** `--authorisation-id <id>` now dispatches to `launch_authorised_entry`. With the inactive configuration it parses the id, reads the tracked configuration and refuses with `execution_not_authorised` before any directory, environment, git, GPU, interpreter, asset or weight is touched. For a future active entry it validates the schema, locates exactly one entry, verifies seed, implementation and authorisation commits, branch, clean tree and index, `origin/main` binding, the permitted changed-file set, GPU, `cuda:0`, UUID, PCI, output path and ancestry, then consumes only that entry and starts one worker from values sealed in it. Unknown, duplicate, inactive, consumed and mismatched entries fail closed; the two seeds are independently consumable; a retry needs a distinct entry and directory.

**Candidate predecessor evidence.** A candidate entry now binds the replicate manifest path, byte count and SHA-256, the seed, epoch, update, the checkpoint relative name and weight hash. Before consumption the launcher reopens that manifest through a symlink-safe inspection, requires canonical JSON, the exact schema, the independent validator and a successful terminal state, and checks the seed, B1 initialisation, validation-artifact identities and checkpoint identity against the entry. Update 0, M6 evidence, sibling replicates and unlisted checkpoints are refused; TRAIN, assets and weights open only after consumption.

**Report-only diagnostics.** The accepted M6 diagnostics (nearest-TRAIN normalised edit distance, maximum edit similarity, nucleotide and dinucleotide distances, MFE, MFE per nucleotide, paired fraction, length strata) are reused unchanged, written to a hashed file, and summarised in the manifest. They are not thresholds, do not touch ranking or the guardrails, and edit similarity is not described as sequence identity.

**Inspection and interpreter.** Required files are inspected with an `lstat` ancestry walk, regular non-symlink leaf, size, recorded signature, `O_NOFOLLOW` hash and recheck; single-link is enforced for checkpoints and the sealed manifest. The pinned RNAGenesis H200 interpreter path, resolved path, SHA-256 and size are bound in each entry, observed before consumption (mocked in tests), rechecked by the worker and producer, and recorded in the manifests.

**Tests:** CPU and mock only, CUDA hidden, offline controls, bytecode disabled, caches outside both repositories. 301 focused M7 tests pass (54, 35, 44, 26, 49, 66, 27 by file). `tests/modelling` passes with 569 tests. The B1 development-pool (30), generic (62), phase B (35) and null-model (54) suites passed, each in its own process. The M6 YAML blobs are unchanged (`4c0ef9b700f0c4566e1fdaa71dc68c25370712f0`, `d33a0284b7edf81b922364eb4838b9f52a551d57`) and RNAGenesis tracked state is clean at `e3b855bbf4d1af376f43747643fa30afd662828c`. Four defects found by the new tests were fixed (see the implementation document, section 9).

**Deferred:** the hash-to-open TOCTOU window; nothing has run for real (generator, launchers, GPU probe, live observations); strict ancestry may refuse a path M6 accepted; the interpreter identity must be observed at authorisation time and so must the `LD_LIBRARY_PATH` value; failed predecessor candidate manifests are verified only at selection; the M6 asset observer used by the replicate launcher is unhardened M6 code. See the implementation document, section 10.

---

## 2026-10-06 — M7 revision 4: final-selection launcher, validator re-derivation, fixed PATH (package still inactive)

**Stage:** Aim 2 / modelling / M7 final D1 replicate training

**Status:** `M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED`, unchanged. This is a bounded revision of the inactive package (revision 3 was reviewed from archive SHA-256 `618972a81d4d7d744c2266db7b89b869755143fe884f40eaa68bba3de2161daf`), not an authorisation. All three M7 configurations remain inactive and non-consumable, with `authorisation_entries: []` and no GPU, UUID, PCI bus, output directory, timestamp, interpreter identity, predecessor identity or biological binding. No biological data (TRAIN, VALIDATION, REF or EVAL), model or checkpoint weights, accepted run evidence or GPU was used; `nvidia-smi` was located by path inspection only and never executed; no run or evidence directory exists; nothing was staged, committed, pushed or fetched; RNAGenesis and every M5 and M6 file are unchanged (the two inactive M6 YAML blobs `4c0ef9b7…` and `d33a0284…` are unchanged). The revision 1 to 3 review archives are kept unchanged. **M7 is not complete.**

**Final selection made operational.** Revision 3's `m7_selection.py` accepted only `--help` and `--schema`, so M7 could not have been completed without an untracked script. It now has `launch_authorised_selection`, reachable only through `--authorisation-id <id>` (no manifest path, seed, epoch, checkpoint, output or scientific argument exists). `D1_final_selection.yaml` stays inactive and gained an empty `authorisation_entries` and an exact `authorisation_schema`; its versions were bumped to `m7-final-selection-config-2` and `m7-final-selection-manifest-2` (the replicate and candidate versions are unchanged). While inactive the launcher refuses with `execution_not_authorised` before the environment, git, the run root, any manifest, RNAGenesis or an output path is inspected. A later authorisation-only commit that changes only that file (and only four activation paths; the GPU and biological-path flags stay false) may bind one single-use entry: the id, the parent and executing commit, the implementation hashes, the exact new output directory, one or two replicate manifests (seed, path, bytes, SHA-256), every evaluated guardrail manifest (seed, epoch, path, bytes, SHA-256), and either no deviation for seeds 43 and 44 or the already sealed deviation for seed 43 alone. The launcher never decides to omit seed 44 and never reads a clock. Before consumption it validates the schema and all path text, the repository binding, the manifests (symlink-, hard-link- and change-safe, canonical, exact schema) and a dry-run build; it then consumes exactly the bound directory, rebuilds, validates and atomically writes the manifest, records any later `BaseException` in the message-safe failure record and re-raises interrupts. It imports no training stack.

**Validator gaps closed.** `validate_final_selection_manifest` now enforces exact key sets for every nested record, SHA-256 shapes, integer types, type-strict comparison of fixed blocks, exact and ordered replicate and guardrail indexes (the latter equal to the evaluated rows), recomputed ranking hashes over the rebuilt replicate-style ranking record, seed status derived from the lazy trace, all four checkpoint member hashes bound between the candidate table and the selected set (candidate rows gained `members_sha256`), and replicate hashes bound to the seed records and the deviation. `selected_set_sha256` is documented as a content hash, not an authenticity mechanism, and `rebuild_matches` compares a manifest with the bytes rebuilt from the sealed inputs. The new tests found that a float or bool (`epoch: 5.0`, a closure flag `0`) passed every dictionary comparison; comparisons are now type-strict.

**Ambient `PATH` removed.** The child `PATH` is the constant `<pinned environment>/bin:/usr/bin:/bin`; `git` and `nvidia-smi` run only by `/usr/bin/git` and `/usr/bin/nvidia-smi` after an `lstat` validation (root-owned, not writable by group or others, regular, not a symlink), with `shell=False` and a fresh environment; the child interpreter must be the absolute pinned Python; each launcher pins its own process `PATH` after its inactive gate. M7 code uses M7 replacements for the by-name `git` and `nvidia-smi` calls of the accepted B1 and M6 helpers (which are unchanged), and a test shows the replacements return what the accepted ones return on the same output.

**Wording corrected.** Earlier text said the live interpreter was not used. The pinned interpreter ran every test suite; what is mocked is the M7 interpreter-identity observation and the authorised launch. Statements that the final-selection stage has no launcher, and that every selection claim was already re-derived, were corrected in the implementation document and the schema, protocol and plan summaries. Historical entries above are unchanged.

**Tests:** CPU and mock only, CUDA hidden, offline controls, bytecode disabled, caches outside both repositories, each suite in its own process. 418 focused M7 tests pass (54 shared primitives, 35 replicate contract, 44 replicate runner, 26 candidate guardrails, 49 candidate generation, 66 launch and inspection, 50 final selection, 61 final-selection launcher, 33 fixed path); revision 3 had 301. `tests/modelling` passes with 686 tests (revision 3 had 569; the 117 additional tests are all M7). The B1 development-pool (30), generic (62), phase B (35) and null-model (54) suites passed. `tests/data_preparation` (76 errors) and `tests/test_stage1_hard_filter.py` (1 error) cannot run because no interpreter has pytest; the errors are identical at HEAD and the suites were not run. Five existing environment assertions were updated because `PATH` is now a constant.

**Residual limitations (accepted, not blockers):** the hash-to-open window; the generator, launchers and tool paths have never run for real; the selection binds the running interpreter by resolved path only; a self-consistent rewrite of a final manifest is detectable only by `rebuild_matches` against the sealed inputs; the fixed `PATH` and tool paths are specific to this host. Details are in section 10 of the implementation document.

**Review-time wording corrections before staging.** Three clarifications were made while preparing the commit; they change no execution behavior, scientific decision or authorisation state. (1) The replicate-launcher section heading comment in `m7_replicate_runner.py` now reads "authorised launcher and entry point" instead of the stale "launcher (not wired to the entry point)". (2) The comment above `FIXED_CHILD_PATH` in `m7_common.py` and the matching sentence in the implementation document no longer say that every user-controlled directory is absent: the child `PATH` never inherits the parent `PATH` text, the deliberately pinned environment's `bin` directory (the only user-space component) comes first, `/usr/bin` and `/bin` follow, and `/usr/local/bin` and every ambient directory from the invoking shell are absent; the value is unchanged. (3) The implementation document no longer implies that the launcher calls `rebuild_matches`: `launch_authorised_selection` invokes the deterministic builder as a dry run before consumption and again after consumption, validates the result and writes it atomically, and `rebuild_matches` provides the corresponding byte-for-byte comparison for later audit. All historical entries are preserved.

---

## 2026-10-07 — M7 seed-43 attempt 1 failed at runtime identity; fixed `CUDA_MODULE_LOADING` control (configuration returned to inactive)

**Stage:** Aim 2 / modelling / M7 final D1 replicate training

**Status:** `M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED`. This is an implementation-contract correction after a consumed failed attempt. It is not an authorisation for attempt 2. The checked-in replicate configuration is again inactive and non-consumable: `authorisation_entries: []`, every execution flag false, and no GPU, interpreter, output directory, timestamp or attempt-2 binding. Scientific hyperparameters, the seed policy, the M8 total of 30,000 raw D1 attempts, and retention through at least 1 November 2026 are unchanged. Nothing was staged, committed, pushed, or fetched. No attempt-2 authorisation, command, or run directory was created. **M7 is not complete.**

**Attempt 1.** Authorisation `m7_d1_final_replicate_seed43_e682cb6064a5_gpu1_attempt1` was consumed and failed. The evidence directory `/home/laura/rnagenesis-mres-runs/m7_d1_final_replicate_seed43_e682cb6064a5_gpu1_attempt1` is retained and was not modified. `authorization_consumption.json` SHA-256 is `d99177aee5c719082bfcc79d1a9d3c1f639c63ea44b7470cf4d877b0b982eb15`. `authorization_failure.json` SHA-256 is `2612bcbcc8aa3f9273ad51ce00ad3d8524f16b08298d1e31637ce4c39f29c722`. The code is `environment_rejected`, the stage is `runtime_identity`, and the recorded detail is `the worker environment holds 1 names outside the allow-list`. The state is consumed, failed, and non-resumable. Epoch, update, microbatch and the partial checkpoint are null. There is no success manifest and no training update. The authorisation commit is `efa118dee886fa29e66626170dba9467b10e72c3`. Its parent and the executing implementation commit are `e682cb6064a578868cc258e58465a0c036afe0d4`. The post-failure observation supplied with the attempt is that GPU 1 remained at 15 MiB used and 0% utilization. This correction did not query the GPU.

**Cause.** The import-only diagnostic passed. `run_authorised_replicate` then calls `clock.stamp()`, and `SynchronizedClock.stamp()` calls `torch.cuda.synchronize()`. Pinned PyTorch `2.1.2+cu121` assigns `CUDA_MODULE_LOADING=LAZY` during CUDA lazy initialisation when the variable is absent. The following worker environment check rejected that name. This happened before biological inputs, training updates, or checkpoints. The installed source was read only; CUDA was not initialised to reconfirm it.

**Correction.** The child environment now sets `CUDA_MODULE_LOADING` itself to exactly `LAZY` through `FIXED_CHILD_ENVIRONMENT_CONTROLS`. An ambient parent value is not copied and cannot replace it. The worker requires that exact value. A missing, empty, differently cased, non-text, or other value fails closed. The name enters the worker allow-list only after that check. A genuinely stray name is still rejected. The unexpected-environment diagnostic reports a bounded, sorted list of names and never their values. The null `LD_LIBRARY_PATH` behaviour, fixed `PATH`, CUDA device mapping, offline controls, isolated cache paths, and the repository, GPU, interpreter, asset, data-access and single-use gates are unchanged.

**Attempt 2.** It needs a new implementation commit, a new authorisation id, a new output directory, and a separate approval. This entry does not create them. Attempt 1 cannot be resumed.

**Tests.** CPU and mock only, CUDA hidden, offline controls, bytecode disabled, caches outside both repositories. 432 focused M7 tests pass (64, 35, 47, 26, 49, 67, 50, 61, 33 by file). The 16 modelling test modules together pass with 700 tests. The B1 development-pool (30), generic (62), phase B (35) and null-model (54) suites passed, each in its own process. No real GPU test was run.

---

## 2026-10-07 — M7 candidate-guardrail provenance split (inactive; not an authorisation)

**Stage:** Aim 2 / modelling / M7 candidate guardrails

**Status:** `M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED` for `config/experiments/D1_candidate_guardrails.yaml`. This commit corrects the repository-binding contract. It does not authorise a candidate, bind a GPU, name an output directory, or launch generation. The live seed-44 replicate authorisation is unchanged. **M7 is not complete.**

**Why the commits are distinct.** `c150894b9982d7afebfb2b3390b0797a4da146b5` is the sealed training implementation of the completed seed-43 replicate and of its checkpoint directory names. A later guardrail authorisation has to be a single child of the guardrail implementation it executes, on clean `main`, with `origin/main` equal to that parent or to the authorisation commit. After replicate authorisations advanced `main`, those two commits are no longer the same. Requiring them to be identical made forward-only execution impossible. A side branch, a second worktree, a rewritten history, a locally moved `origin/main`, a force-push, and an unpushed authorisation commit were rejected: the launcher refuses every one of them.

**Correction.** `authorization_parent_commit` remains equal to `executing_implementation_commit`, and that commit is the guardrail implementation. The new entry field `checkpoint_training_implementation_commit` is the sealed training commit. It must match the completed replicate manifest, the checkpoint path, and the checkpoint member hashes, and `git merge-base --is-ancestor` must show it is an ancestor of the guardrail execution commit. A later, unrelated, missing, malformed, or substituted commit is refused. Checkpoint members, including the weight file, are still streamed before and after generation. Thresholds, schedule, ranking, learning rate, selection policy and the M8 allocation are unchanged. The revision-2 proposal that stored the training commit as `executing_implementation_commit` is superseded and must not be committed as written. Both completed replicate directories are unchanged. Final selection was updated in the same schema migration. It binds each guardrail to its replicate by `checkpoint_training_implementation_commit` and the replicate's training `executing_implementation_commit`. It does not treat the guardrail execution commit as checkpoint provenance. A later unequal execution commit is accepted when the training commit and the other evidence relationships match. The final-selection manifest stores neither commit in a new field: checkpoint names keep the sealed training commit, and the execution commit stays on the hashed guardrail manifest.

## 2026-10-07 — M7 cross-seed comparability after sequential authorisations (inactive; not an authorisation)

**Stage:** Aim 2 / modelling / M7 final selection

**Status:** `M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED` for both `config/experiments/D1_candidate_guardrails.yaml` and `config/experiments/D1_final_selection.yaml`. This note records a proposal-only correction. It does not authorise a candidate, bind a GPU, name an output directory, or launch generation. The live seed-44 replicate authorisation is unchanged. **M7 is not complete.**

**Why the training commits differ.** Sequential single-use authorisations give the two replicates different training commit ids. Seed 43 is sealed to `c150894b9982d7afebfb2b3390b0797a4da146b5`. Seed 44 is sealed to `2cb1b6a26391ed36754ec21685a4501d659d50ef`, the authorisation commit of seed 43. The only Git change between those commits is the authorisation-bearing replicate YAML. The sealed training implementation-file hashes are identical. Each manifest's raw `implementation_config_sha256` differs because that hash covers the parent YAML, including its authorisation state.

**Correction.** Checkpoint provenance is checked within each seed. A guardrail must carry that seed's own training commit. It must not carry the other seed's. Cross-seed selection does not require the training commit ids, the authorisation commits, or the raw authorisation-bearing configuration hashes to be equal. Comparability is the sealed implementation content and protocol: implementation-file hashes, B1 identity, architecture, the learning-rate schedule and fixed training protocol, TRAIN and VALIDATION identities, validation artifacts, and non-seed hyperparameters. An ancestor relationship is not used as a substitute for those content identities. An authorisation-only Git difference is not a scientific training difference. No shared training commit is synthesized. Checkpoint names keep each replicate's own training commit.

---

## 2026-10-08 — Accept the M7 selected set and close M7

**Stage:** Aim 2 / modelling / M7 final D1 replicates

**Status:** M7 is COMPLETE / GO for M8 planning only. On 8 October 2026 the human gate accepts the two-seed selected set. This record does not authorise M8 generation, further training, GPU use, biological-data access, VALIDATION, REF, or EVAL.

**Preflight:** MRes branch `main`. HEAD and `origin/main` were `0761f866c97e8f9372b0f224fb413dcc0995c6e9`, the single-use final-selection authorisation, with the single parent `b5de24327ed5d3c601597d1f1c886e2c253916dd`. The index and worktree were clean. The closure review did not query a GPU, did not open a weight file or a biological dataset, and did not modify a run directory.

**Evidence:** Final selection ran once under `m7_d1_final_selection_b5de24327ed5_attempt1`. The directory contains `authorization_consumption.json` (503 bytes, SHA-256 `29df8fdc56a0198b53b32ee6918b3f158a283c0f4d05a893ce70bd9ea2f00c5d`, `consumed_output_created`, `reuse_permitted: false`) and `m7_final_selection_manifest.json` (13,124 bytes, SHA-256 `49b218e3df74825e1931148e2f65b25aae057c822e2ab32d44c2960b1587c91c`). No failure record exists. The outcome is `selected_set_complete` for seeds 43 and 44. The selected-set SHA-256 is `af0c0e555a8b878feadeb17fcbde18d8b780819a42d9e0cc547d2fc0c6895f8f`. Rebuilding from the four sealed manifests reproduced the manifest bytes and the allocation of 15,000 sequences for each seed. The selected checkpoints are seed 43 epoch 5 update 105 `D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-43__epoch-5__update-105__git-c150894b9982d7afebfb2b3390b0797a4da146b5` and seed 44 epoch 5 update 105 `D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-44__epoch-5__update-105__git-2cb1b6a26391ed36754ec21685a4501d659d50ef`.

**Attempts:** Seed 43 attempt 1 remains the consumed `runtime_identity` failure at `/home/laura/rnagenesis-mres-runs/m7_d1_final_replicate_seed43_e682cb6064a5_gpu1_attempt1` and is not accepted training evidence. Seed 43 attempt 2 is the accepted replicate, manifest SHA-256 `f59bb4a236e3d1ac532dd83d524d8e7ceb51cbf2b9010741206169577d1acecc`. Seed 44 attempt 1 is the accepted replicate, manifest SHA-256 `900182689f3e133d395b45dd58a987e91b767e005fc00e744e1eacedeffa3fa6`.

**Limitation and retention:** The accepted set is seeds 43 and 44 only. Seed 42 stays excluded, no third seed was trained, and no one-seed deviation was used. All five epoch checkpoints of each executed seed are retained through at least 1 November 2026. Deletion is not implemented.

**Configuration:** `D1_candidate_guardrails.yaml` is restored to inactive blob `e04fb083073f780959b24f335f81c61961607625`. `D1_final_selection.yaml` is restored to inactive blob `544b79bbf4e98f8770c8a788e3990473a1f010fa`. `D1_final_replicates.yaml` is unchanged at blob `3d8238da0158c9157fbbcb14645822a3cb6e340d`, the seed-44 authorisation. The validators have no consumed document status, and the tests require that live replicate file. The sealed manifests keep `m7_complete: false`. They are not the milestone-status authority. This closure is not a new executable authorisation.

**Boundary:** Nothing in this review was staged, committed, or pushed. No M8 authorisation or output directory was created, no sequence was generated, and no scientific workflow was launched.

---

## 2026-10-08 — M8 raw-generation proposal ready for review (inactive; not applied)

**Stage:** Aim 2 / modelling / M8 raw B1 and D1 generation

**Status:** `M8_RAW_GENERATION_READY_FOR_REVIEW_NOT_AUTHORISED`. This log text belongs to the inactive proposal. It is not an authorisation, and this task does not apply it as a live commit. The checked-in configuration `config/experiments/M8_raw_generation.yaml` is non-consumable, every execution flag is false, and both authorisation lists are empty. No GPU, interpreter, `LD_LIBRARY_PATH`, timestamp, or output directory is bound.

**What M8 seals.** Raw pools only. B1 is 30,000 raw attempts. D1 is 30,000 raw attempts, 15,000 from training seed 43 and 15,000 from training seed 44. The M4 and M7 1,000-attempt pools are excluded. Parsing, filtering, clustering, representation analysis, and the four-condition comparison are later work under a common frozen evaluation protocol. The cleaner is not invoked. Exact raw bytes in the retained invocation files are authoritative. `raw_decoded_text` is the deterministic UTF-8-else-Latin-1 representation stored in canonical JSON and checked against those bytes.

**Seeds and accounting.** Two D1 training seeds are the approved final set. The absent third seed is a resource and time limitation. The one-seed M8 alternative is historical and is not executable, because both final seeds completed. Fixed raw-attempt accounting supersedes rejection and resampling. There is no replenishment.

**M7 boundary.** M7 completion is the human closure recorded above. Sealed M7 manifest bytes remain unchanged. The live seed-44 replicate YAML is historical M7 state and is not M8 authority. M8 refuses an M7 configuration path, an M7 schema version, an `m7_` authorisation id, and that live seed-44 id.

**Boundary:** No M8 execution is authorised. This proposal was prepared in an isolated tree. It was not staged, committed, pushed, or copied onto the live checkout.

## 2026-10-08 — M8 inactive proposal revision (not applied)

**Stage:** Aim 2 / modelling / M8 raw B1 and D1 generation

**Status:** `M8_RAW_GENERATION_READY_FOR_REVIEW_NOT_AUTHORISED`. This revision stays inactive. It does not authorise an arm, bind a GPU, choose an `LD_LIBRARY_PATH`, choose free-memory or free-space thresholds, or create a run directory.

**Scientific design.** The 30,000/30,000 attempt totals, the 15,000/15,000 D1 seed split, the paired blocks, the six schedule hashes, `max_seq_len = requested biological length + 1`, and the no-filter accounting are unchanged. Attempts are generated draws. Generation seeds are unique within a block and reused across paired B1/D1 arms. They are not 30,000 independent training replicates. The absent third training seed remains a resource and time limitation.

**Implementation corrections.** Active generation and active assembly now have separate exact validators. A future authorization commit binds its parent, the executing implementation commit, the three implementation-file hashes, and the active configuration identity. Live HEAD is that authorization commit, not the proposal base. The interpreter path, resolved `python3.8`, and interpreter SHA-256 are bound for a future generation entry. GPU identity, compute-process absence, and storage thresholds are preflight predicates and do not move or terminate a process. Evidence writes use the complete-write, fsync, and interruption-cleanup pattern. Assembly rechecks canonical arm paths, single-link files, and every schedule field, and it has the same consume-once failure lifecycle.

**Planning assumption.** Approximately 6.4–10.4 GPU-hours for all four arms, with a practical 12–16 hour reservation including verification and overhead. Actual runtime is recorded later from the manifests. Checkpoint weights are not copied. Expected evidence storage is modest, and a launch still requires a fresh free-space check.

## 2026-10-08 — M8 inactive proposal revision, second pass (not applied)

**Stage:** Aim 2 / modelling / M8 raw B1 and D1 generation

**Status:** `M8_RAW_GENERATION_READY_FOR_REVIEW_NOT_AUTHORISED`. This second revision stays inactive. It does not authorise an arm, assemble a pool, query a GPU, or create a run directory.

**Provenance.** The public assembly launcher hashes the exact YAML bytes it parsed. Consumption, failure, and success records store that digest as `active_configuration_raw_sha256`, separately from `active_configuration_sha256`. A missing raw digest is refused. `repository_identity.mres_commit` is the live authorization commit. `proposal_base_commit` keeps `d0f9a397b536c64ca1b22662cc9ae36aea0101f6`.

**Runtime identity and history.** The controller observation inspects the running process, including `/proc/self/exe` where available. A restricted child probe returns the bound interpreter path, resolved executable, hash, and Python version before consumption, without importing the model stack or querying CUDA. Every commit after the executing implementation commit must be linear and confined to `config/experiments/M8_raw_generation.yaml`. Launch does not import `m6_pilot_contract.py`.

**Paths and evidence.** Production preflight refuses a symlinked run root, checkpoint directory, arm directory, or raw directory that escapes its arm. Assembly validates the nested arm manifest, including sampler, sequence access, asset inventory, both schedule hashes, interpreter and GPU and storage claims, timestamps, and D1 `selected_set_evidence`. B1 uses an explicit not-applicable selected-set record. Isolated `HOME`, `TMPDIR`, cache, and pycache directories are created inside the consumed output before the first generation subprocess. `TMPDIR` must exist.

**Boundary:** This revision was prepared in an isolated tree. It was not staged, committed, pushed, or copied onto either live checkout.

## 2026-10-09 — M8 shared-GPU implementation and GPU1 revocation proposal (inactive; not applied)

**Stage:** Aim 2 / modelling / M8 raw B1 and D1 generation

**Status:** `M8_RAW_GENERATION_READY_FOR_REVIEW_NOT_AUTHORISED`. This proposal is inactive. It does not authorise generation, assembly, physical GPU 0, or a run directory. It was prepared in an isolated clone and was not committed, pushed, launched, or copied onto either live checkout.

**Retired authorisation.** `m8_d1_seed44_block_b_ac371ba_gpu1_attempt1`, commit `e645925478e0110504f4dd8ce473a1a3be82d677`, is recorded as unconsumed, not launched, and superseded before dispatch. The exclusive-GPU availability gate refused it because physical GPU 1 had other compute processes. Dispatch did not occur, no controller started, no output directory was created, no consumption record exists, and no sequence was generated. That was a resource-gate refusal, not a model or scientific failure. The historical commit and the refusal archive are preserved. The authorisation is not executable. No GPU 0 authorisation entry is present.

**Sharing policy.** An active generation entry must name `gpu_sharing_policy` as `exclusive` or `shared_allowed`. Absence is rejected for a new entry and does not enable sharing. `exclusive` still requires zero pre-existing compute applications on the selected GPU. `shared_allowed` permits a positive count only when that entry says so. GPU identity, processes, memory, and storage are observed once during pre-consumption validation, before output creation and model generation, and that observation is not repeated after asset verification. The launch does not terminate or signal another process. Historical `m8-arm-manifest-1` B1 and seed-43 manifests remain valid without rewriting. New manifests use `m8-arm-manifest-2` and record that single observation: the policy, the pre-existing count, the compute-app snapshot and its SHA-256, the observation time, and the selected GPU memory readings. Pre-existing processes are not generated-model processes.

**Method.** Shared execution is an operational and resource-management deviation. It does not change the D1 seed-44 checkpoint, epoch 5, update 105, weight SHA-256 `d0fcb5174230b8bbbc6bfe59eabda9b37687c03800012bc1a6981cc215469ed5`, the 15,000 raw attempts, the block-B schedule, the 164 invocations, or generation seeds 900000–900163. It may change wall-clock runtime and it raises interruption and resource-contention risk. It does not by itself justify a biological or model-quality conclusion. The recommended later GPU 0 free-memory threshold is 30 GiB, exactly 32212254720 bytes, stored on that future authorisation rather than hard-coded. It is a point-in-time safety gate on the single pre-consumption observation, not a reservation or a guarantee against later growth.

**Boundary:** No CUDA initialisation, no `nvidia-smi` launch probe, no output directory, and no generation were performed for this proposal.

## 2026-10-09 — M8 shared-GPU selected-GPU PID correction (inactive; not applied)

**Stage:** Aim 2 / modelling / M8 raw B1 and D1 generation

**Status:** `M8_RAW_GENERATION_READY_FOR_REVIEW_NOT_AUTHORISED`. This revision stays inactive. It does not authorise generation, assembly, physical GPU 0, or a run directory. It was prepared in an isolated clone and was not committed, pushed, launched, or copied onto either live checkout. The previous proposal archive remains immutable.

**Process rows.** `selected_preexisting_compute_count` counts every selected-GPU compute-app row whose PID is a positive decimal integer. A selected-GPU row whose PID is empty, non-decimal, zero, negative, `[N/A]`, or `[Not Found]` is rejected as malformed or indeterminate evidence. An indeterminate row for another GPU does not increment the selected-GPU count and does not by itself prevent use of the selected GPU. Production launch validation and assembly validation apply that rule through `assert_compute_app_evidence`. No path kills, signals, pauses, moves, or otherwise inspects or alters another process.

**Single probe.** The GPU and storage probe still occurs once during pre-consumption validation, before output creation and model generation. It is not repeated after asset verification. Checkpoint and asset verification may occur between that observation and output-directory consumption. Concurrent workloads may grow after the observation. The 30 GiB figure remains an authorisation-level recommendation and a point-in-time safety gate. The manifest records that single observation. This revision does not add a second probe.

**Boundary:** No CUDA initialisation, no `nvidia-smi`, no output directory, no authorisation consumption, and no generation were performed for this revision.

## 2026-10-10 — M8 completion and evaluation handoff (inactive proposal; not applied)

**Stage:** Aim 2 / modelling / M8 raw B1 and D1 generation

**Status:** Raw generation and CPU assembly are complete. This proposal returns `config/experiments/M8_raw_generation.yaml` to `M8_RAW_GENERATION_READY_FOR_REVIEW_NOT_AUTHORISED`. The document is non-consumable, both authorisation lists are empty, and every execution flag is false. The retired GPU 1 seed-44 block-B record stays unconsumed and non-executable. This proposal does not authorise evaluation, filtering, or a new run. It was prepared in an isolated clone and was not applied, staged, committed, or pushed on either live checkout.

**Arms.** Each arm has 15,000 raw attempts. B1 block A, manifest `bb788e862d6a7c41e8b942d53e8121d2d19722574d4956b4c2c2644f392931b9`, ledger `5e9c00664fce3a423e8c89aad43f32fcf1d1db59b8639561eff436e6fdba7d82`, elapsed 8348.671256661415 seconds, authorization commit `c08be8839d9681d4f68b9242abcf9a7ff40c4d24`, exclusive GPU 1, generation seeds 800000–800162. B1 block B, manifest `d51be51bbf10a90ca7ff809403f38007167a7cdd72704473a0dd39a2bb8510e7`, ledger `11003ba60bf191ee841ae55a7dd81f0d78d731c96855f28f564b53da4b353e61`, elapsed 8369.749910581857 seconds, authorization commit `f13e0849e19632181315bf5585ae585e16bbb127`, exclusive GPU 1, generation seeds 900000–900163. D1 training seed 43 block A, manifest `a0fde7024662ee13837e6f99b163711263b60d55fa6c60b8012db53f93873e52`, ledger `d0d16afe63f767179c8e7af261095af709ce6298cfe64673600cf04965d87473`, elapsed 8451.951393645257 seconds, weight `c0797888bde9033cc15b056c8c09e70b9f7fba0fb21b1f3840a4f1efb77031ab`, authorization commit `acc7e244926fcb9336d35d29d0d767cf1afc5743`, exclusive GPU 1, generation seeds 800000–800162, epoch 5 update 105. D1 training seed 44 block B, manifest `f38aebd53e08c9012af5c4faa8a51a07ca39538dd1ccfcd26d003719b6ea5ca3`, ledger `d007b8d8a2cfed49104be90100059a9f2fdf8ffee86933d5d68b26ba7245920b`, elapsed 8381.193621516228 seconds, weight `d0fcb5174230b8bbbc6bfe59eabda9b37687c03800012bc1a6981cc215469ed5`, authorization commit `50a41b84c7340aca5841672ea7507ceb4c1b7b94`, shared GPU 0 with two pre-existing compute processes, generation seeds 900000–900163, epoch 5 update 105.

**Combined outputs.** B1 ledger `/home/laura/rnagenesis-mres-runs/m8_b1_combined_1069b63_cpu_attempt1/m8_combined_raw_attempt_ledger.jsonl`, 30,000 records, 26,427,607 bytes, SHA-256 `37ba0e1b852a6b8492a816a4adc0c6bfee15a554ba28a8ba5dd91d9e32a255d9`, authorization commit `b79e70c0d895ba34f7655732412a1c3e039b4067`. D1 ledger `/home/laura/rnagenesis-mres-runs/m8_d1_combined_1069b63_cpu_attempt1/m8_combined_raw_attempt_ledger.jsonl`, 30,000 records, 28,971,289 bytes, SHA-256 `cedcc36133f5dfb3678e1560c6d6bab703136fe89e512e939b9f93a9a6361de9`, authorization commit `c9a8cfc8cb2d720fdab8743bed088e8f900c3198`. Each combined ledger contains master indexes 0 through 29999 exactly once and 30,000 unique record ids. Training seed, generation seed, and record id stay distinct. Selected-set SHA-256 `af0c0e555a8b878feadeb17fcbde18d8b780819a42d9e0cc547d2fc0c6895f8f`. Final-selection manifest SHA-256 `49b218e3df74825e1931148e2f65b25aae057c822e2ab32d44c2960b1587c91c`.

**Runtime.** Summed GPU execution time, the four `elapsed_seconds` values, is 33551.566182404757 seconds. Wall-clock scheduling time from `2026-10-08T13:55:44+00:00` to `2026-10-09T13:32:21+00:00` is 84997 seconds. The arms were sequential. The difference is idle time between arms. CPU assembly is not included in either figure.

**Contract and limits.** No filtering, parsing, classification, deduplication, replacement, or replenishment was performed. Evidence is retained through at least 1 November 2026. Sealed manifests were not rewritten. Only two fine-tuning seeds were used, because of time and GPU constraints. Evaluation completeness was prioritized over a third training replicate. The training seed is coupled to the D1 technical block and generation-seed range, so pooled D1 supports condition-level evaluation and does not support clean replicate-level causal inference. Raw attempts are not yet established to be valid nucleotide sequences. No duplicate removal, training-set-match analysis, leakage analysis, biological-quality assessment, structure analysis, clustering, representation-space analysis, or functional evaluation was performed. M7 guardrail samples were not included. Seed 43 attempt 1 remains the consumed `runtime_identity` environment failure, not a model failure. Guardrails establish generation and runtime sanity only. Shared GPU use on the seed-44 arm may affect runtime and resource contention; its generated bytes and provenance remain sealed.

**Handoff.** Later evaluation must apply the same declared parsing and filtering policy symmetrically across B0, B1, B2, and D1, and must not tune parameters after inspecting REF or EVAL outcomes. The evaluation worktree stays out of scope. The full record is section 8 of `docs/fine_tuning/m8_raw_generation.md`.

**Boundary:** This review did not stage, commit, or push on the live checkout. It did not launch, consume, generate, assemble, filter, or evaluate. It did not modify the run root or the evaluation worktree.

## 2026-10-12 — Stage 4 M9 production parsing evidence

**Stage:** Aim 2 / modelling / M9 production derived ledgers

**Status:** COMPLETE for the parser freeze, the production derived-ledger run, and closeout hardening. M9A exact cross-condition overlap and leakage preparation remains a separate gate and has not started.

**Commits:**

- `c8202f9dd33b7f8bbbad8967ac88e0e00c04737b` — Implement frozen synthetic-only M9 parser contract
- `d40584d4a666dc2ca7a778a4b1ef1bbda449b484` — Correct M8 relative-path provenance validation
- `378f574b1620a9ff999082262868bffbe647d063` — Implement M9 production derived-ledger runner
- `f703a8c721384e821337eba9a59093918f8decfe` — Harden M9 production ledger closeout

**Location:** `results/fine_tuning/m9_generator_evaluation/`. Parser `m9-biological-parser-v1`. Adapter `m9-source-adapter-v2`. Frozen parser-contract SHA-256 `a8cda86af2cd6aff52ed7929c1a8cdfe134394f9087c768a731e8597339fe872`. Frozen source-manifest SHA-256 `89be54f49b020027d58686ececfc1d743c16e58c0ed12d0b6bae269d36c4aa6c`. Production runner commit `378f574b1620a9ff999082262868bffbe647d063`.

**Accounting:** 120,080 attempts: B0 30,080, B1 30,000, B2 30,000, D1 30,000. D1 is 15,000 from training seed 43 and 15,000 from training seed 44. Every attempt is `valid_canonical_sequence`. That result is syntactic validity only, not biological validity. Empty, unparseable, non-sequence, and parsed non-ACGU outcomes are zero.

**Duplicates:** Exact duplicates were counted only within a condition. B1 has 29,983 distinct valid sequences, 29,969 singleton rows, 31 duplicate-member rows, 14 repeated groups, and maximum multiplicity 4. B0, B2, and D1 have no within-condition repeats. `overall.distinct_valid_sequences = 120063` is the sum of the per-condition distinct counts, not global distinctness. Cross-condition overlap was not computed.

**Outputs:** Summary `m9_parsing_accounting_summary.json`, 4,014 bytes, SHA-256 `b06aaf5cf9d2938cf555c496990ba6d04ed4d385fc5c7a6d7071eb504df148d4`. Manifest `m9_production_manifest.json`, 7,876 bytes, SHA-256 `9aa5f60f939a8b25d031967ed3466a26d9d8e2d0610c76ec0b5db4cb43c2cc80`. The five JSONL ledgers remain ignored and are retained as regenerable server-side artifacts. Their recorded digests are in the manifest and in the directory README. The summary and manifest contain no sequence strings.

**Boundary:** REF, EVAL, TRAIN, VALIDATION, models, checkpoints, and AptaRank were not accessed. No sealed source or JSONL ledger was rewritten. Biological evaluation was not performed.

**Next gate:** M9A exact cross-condition overlap and leakage preparation remains separate. It must not access REF or EVAL.

## 2026-10-12 — M9A exact cross-condition overlap evidence

**Stage:** Aim 2 / modelling / M9A exact cross-condition overlap

**Status:** COMPLETE for exact cross-condition overlap on the sealed combined derived ledger. M9A is not complete. TRAIN exact leakage and nearest-TRAIN-distance work remain outstanding.

**Runner:** `a62f3afb53d67ac1619536c26e7848109b0a0ee8`. Contract `m9a-overlap-leakage-definitions-v1`, SHA-256 `6aeaa2338776cbe7aceffef63ee4ca7dfd7ed3643aa7d1e400fd54a02d113535`. Governing plan SHA-256 `fc6963f01f7d4ab311774865bda15626facdb753ffa0db06b01b338d88162b51`.

**Location:** `results/fine_tuning/m9_generator_evaluation/m9a_exact_cross_condition_overlap/`. Input combined ledger `m9_all_conditions_derived_attempt_ledger.jsonl`, 120,080 rows (B0 30,080; B1, B2, and D1 30,000 each), SHA-256 `d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e`. The ledger stays ignored. Summary SHA-256 `03e2b8f6d1dd21181c2d5521a552ec4aac6f78ad4fbd0dc5260ca105e849c32e`. Manifest SHA-256 `555159f1f0ca2cf2311ed4c797c2f22538e0a230e725f79eff90e8dcc94259c9`.

**Result:** Only B1–D1 had nonzero exact overlap. B1→D1 row overlap is 1/30,000 and D1→B1 row overlap is 1/30,000. B1 distinct coverage is 1/29,983 and D1 distinct coverage is 1/30,000. The B1–D1 union is 59,982 and the Jaccard overlap is 1/59,982. The other five pairs are zero at both grains. Global distinct valid sequences are 120,062: 120,061 in exactly one condition and one in exactly two. B0 is an external comparator and is not pooled into the causal B1/B2/D1 comparison.

**Review:** An independent local review verified the downloaded hashes and independently recomputed all overlap results without importing the production implementation.

**Boundary:** TRAIN, VALIDATION, REF, EVAL, models, checkpoints, structure tools, and AptaRank were not accessed. The frozen contract and governing plan were not modified. No JSONL file is committed.

**Limitation:** Exact cross-condition separation does not establish TRAIN novelty, structural novelty, biological quality, or superiority.

**Next gate:** TRAIN exact leakage and nearest-TRAIN-distance remain outstanding.

## 2026-10-12 — M9A TRAIN leakage evidence and M9A closure

**Stage:** Aim 2 / modelling / M9A overlap and leakage

**Status:** M9A is complete. M9B and M9C remain incomplete.

**Prior exact overlap:** `results/fine_tuning/m9_generator_evaluation/m9a_exact_cross_condition_overlap/`. Summary SHA-256 `03e2b8f6d1dd21181c2d5521a552ec4aac6f78ad4fbd0dc5260ca105e849c32e`. Manifest SHA-256 `555159f1f0ca2cf2311ed4c797c2f22538e0a230e725f79eff90e8dcc94259c9`. Only B1–D1 had nonzero exact overlap: 1/30,000 rows in each direction, B1 distinct coverage 1/29,983, D1 distinct coverage 1/30,000, and Jaccard 1/59,982. The other five pairs were zero at both grains. B0 stayed an external comparator.

**TRAIN leakage:** `results/fine_tuning/m9_generator_evaluation/m9a_train_leakage/`. Sealed production execution succeeded once with no retry. Runner commit `532bbba34f3918b6f5fc3b4d09d48de0d92be54e`. Runner-contract digest `ef68b1575df4d770af2bdd622eeb84f647a18db9d4cbd115e0b8a60de5dce528`. M9A contract digest `6aeaa2338776cbe7aceffef63ee4ca7dfd7ed3643aa7d1e400fd54a02d113535`. Governing-plan digest `fc6963f01f7d4ab311774865bda15626facdb753ffa0db06b01b338d88162b51`.

**Identities:** Combined ledger `m9_all_conditions_derived_attempt_ledger.jsonl`, SHA-256 `d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e`, 120,080 rows. TRAIN CSV `ft_train.csv`, SHA-256 `84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0`, 726 identity rows and 669 distinct cores. TRAIN text `corpus_final.txt`, SHA-256 `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d`, 669 lines, equal to the CSV first-occurrence cores. These identities are taken from the leakage manifest. This closure did not reopen the ledger or the TRAIN sources.

**Result:** Exact TRAIN leakage is zero for B0, B1, B2, and D1 at row and distinct-sequence grain. D1 seeds 43 and 44 each have zero exact leakage, 0/15,000 at both grains. Nearest-TRAIN distance is global Levenshtein distance divided by the longer length. Maximum edit similarity is not sequence identity. B0 remains an external comparator. No threshold, bootstrap, confidence interval, or hypothesis test was introduced.

**Hashes:**

- `m9_exact_train_leakage_summary.json` — `f7d10f7f41777a091cc2b2bf3dfeec555d5e8d84b3b89850328be7cdcf15e0d3`
- `m9_nearest_train_distance_summary.json` — `c68fa997207a657a7049e53dd074e8d593333f84152008d631cae0d6565c1d66`
- `m9_train_leakage_manifest.json` — `e2b97da3b1f39859c1d4fc3a652dd4abb6e4da5836e2a5e9c067ce1b87491d88`

**Boundary:** VALIDATION, REF, and EVAL were not accessed. Models, checkpoints, structure tools, and AptaRank were not accessed. No sequence-bearing JSONL file is committed. The generated JSON fields `m9a_complete=false` stay immutable and do not self-certify the milestone.

**Review:** Independent local review passed. Review archive SHA-256 `9af7253146647301fbbf5d0e765b4a104d1e5e263f1d27e451a069976720bc72`.

**Completion:** M9A became complete only when the exact-overlap evidence, this TRAIN-leakage evidence, independent review, documentation, and this closure commit were all present.

**Next task:** A separate plan revision making M9B synthetic/preparatory-only and leaving overlap and leakage exclusively in M9A.

## 2026-10-12 — M9B preparatory boundary

**Stage:** Aim 2 / modelling / M9B AptaRank full-thesis-evaluation preparation

**Status:** M9B preparation has started. M9B is preparatory-only and contains no overlap or leakage analysis. M9A remains complete. M9C and M10 have not started.

**Plans:** The unversioned file `docs/aptarank_full_mres_thesis_evaluation_plan.md` is retained as the immutable v3.2 governing artifact for completed M9A. Its SHA-256 remains `fc6963f01f7d4ab311774865bda15626facdb753ffa0db06b01b338d88162b51`. `docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md` is the active plan for M9B onward. No scientific result motivated the split.

**Boundary:** This entry did not open TRAIN, VALIDATION, REF, EVAL, a production sequence ledger, a model, a checkpoint, a structure tool, or AptaRank. It did not create a result under `results/`. Frozen M9A contracts, runners, tests, manifests, and evidence were not rewritten.

## 2026-10-12 — M9B-1 public AptaRank evidence freeze

**Stage:** Aim 2 / modelling / M9B-1 synthetic-only AptaRank evidence review

**Status:** `FROZEN_PUBLIC_EVIDENCE_SYNTHETIC_ONLY_DEPLOYMENT_UNVERIFIED`. This review freezes the paper, the public implementation, and the supplied interface files. It does not verify the live deployment. M9A remains complete. M9C and M10 have not started. No scientific result is claimed.

**Plan:** `docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md` stays the active plan, SHA-256 `b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe`. It was not edited. The conflicts found do not require a plan change.

**Evidence:** Paper `aptarank_paper.pdf`, 1,254,624 bytes, SHA-256 `aaf40af707acc236639dccb8ecbf1f3fb522143f0a447e71f490168896af433d`. CSV `example_shortlist.csv`, 280 bytes, SHA-256 `447ce90b4fdf8fab7bbd5a4fcda1824fc91d3b7b697c6cfc7fbe466e16400852`. Screenshot `example_results_screenshot.png`, 492,122 bytes, SHA-256 `ffbc22abfd874af242623536ce516f35a8eda17bbc4b52048c39cae63e5c1e63`. The CSV and screenshot are interface evidence only.

**Public code:** Retrieved 2026-10-12T07:24:37Z from `https://github.com/alishahsvnd/AptaRank`. Inspected commit `bd934ca54a6649eb8cf241f56a95d5903c873d91`. Comparison commit `49a85609e3529adace60d3267ee88550159bba29` is present. Implementation code is unchanged between them; the diff is documentation only. Neither commit is claimed as the live deployment.

**Corrections:** ARP-1 now states that it rejects lowercase and T while the public parser normalises them, and that supplied-id preservation is conditional in the public parser. The validator behavior is unchanged. ARP-2B notes now cite the recorded public algorithms and leave every U item unresolved. Local recomputation stays off.

**Unresolved for M9C:** Live deployment identity, effective preset, accepted and dropped REF counts, bank id, hash, and realized count, runtime, live export behavior, the strong-band equality conflict, and the deployed folding-tool versions.

**Boundary:** TRAIN, VALIDATION, REF, EVAL, production sequence ledgers, models, checkpoints, and `results/` were not opened. No production upload or AptaRank scoring run was performed. No REF distribution or Tier 2 control bank was built. No overlap, leakage, or nearest-TRAIN workflow was run.

## 2026-10-12 — M9B-1 AptaRank evidence clarification

**Stage:** Aim 2 / modelling / M9B-1 synthetic-only AptaRank evidence review

**Status:** `FROZEN_PUBLIC_EVIDENCE_SYNTHETIC_ONLY_DEPLOYMENT_UNVERIFIED`. This clarification reclassifies terminology in the frozen evidence. It does not verify the live deployment. No scientific result is claimed.

**Plan:** `docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md` stays the active plan, SHA-256 `b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe`. It was not edited.

**Contract:** `config/modelling/aptarank_evidence_contract.json`, SHA-256 `0494ea740b1a2402032bfa695c23a422b142cda6a2bc043d1da87dbb9ddb092b`.

**Reclassifications:** Canonical uppercase A/C/G/U, with no reliance on silent normalisation, is a deliberate stricter MRes input policy. The five reference columns are a deliberate stricter provenance policy retained for auditability. Both are compatible with the inspected public loader, which still normalises case and T and technically requires only `sequence`. The inspected public implementation constructs one pooled empirical REF distribution per criterion from the REF sequences it accepts. The project does not choose or implement a competing short/long calibration. Local recomputation stays disabled, and live agreement with that implementation remains for M9C. The public two-sided clip is defensive: a valid empirical CDF already keeps `1 - 2 * abs(F - 0.5)` in `[0, 1]`, so `two_sided_clip` is not an unresolved conflict and does not require M9C resolution. The exported rank is the deterministic consecutive 1-based ordinal position after sorting by descending Tier 1 score and ascending candidate ID for ties. It is not a dense rank and it is not the statistical minimum rank retained for the empirical CDF. U2–U21 stay unresolved for deployment application. Their recorded public definitions stay established, and local scorer reimplementation stays disabled.

**Unresolved for M9C:** Live deployment identity and dependency versions, effective preset and runtime, the quick-preset 30-versus-0 discrepancy, accepted and dropped REF counts, bank id, hash, and realized count, live export behavior, and the strong-band equality difference. Whether the live deployment applies the inspected pooled calibration also remains for M9C.

**Boundary:** TRAIN, VALIDATION, REF, EVAL, production sequence ledgers, models, checkpoints, and `results/` were not opened. No production upload or AptaRank scoring run was performed. No REF distribution or Tier 2 control bank was built. No production value was instantiated.

