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
