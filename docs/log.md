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

