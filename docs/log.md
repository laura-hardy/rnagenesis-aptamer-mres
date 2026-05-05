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

## 2026-05-05 — A6000 environment setup

Set up RNAGenesis execution environment on A6000 server.

System:
- Hostname: warpgolem
- GPU: NVIDIA RTX 6000 Ada Generation
- NVIDIA driver: 555.58.02
- CUDA version reported by nvidia-smi: 12.5
- PyTorch CUDA runtime: 12.1

Environment:
- Conda environment: /home/laura/.conda/envs/rnagenesis-a6000
- Python: 3.8.13
- NumPy: 1.24.4
- PyTorch: 2.1.2+cu121
- torchvision: 0.16.2
- torchaudio: 2.1.2
- transformers: 4.36.2
- diffusers: 0.25.0
- huggingface_hub: 0.20.3
- ViennaRNA import: OK
- BioPython import: OK
- CUDA available to PyTorch: True
- GPU detected by PyTorch: NVIDIA RTX 6000 Ada Generation

Notes:
- Used existing system Anaconda at /opt/anaconda3.
- System conda package cache caused permission errors, so environment and package cache were configured under /home/laura/.conda.
- Pinned huggingface_hub to 0.20.3 because diffusers 0.25.0 requires cached_download.
- Pinned transformers to 4.36.2 to remain compatible with huggingface_hub 0.20.3.

Status:
- Phase 1.4 complete on A6000.
- Ready to proceed to Phase 1.5: download and verify RNAGenesis checkpoints/configs.


## 2026-05-05 — A6000 setup and checkpoint download started

Continued Aim 1 Phase 1.4–1.5 on the A6000 server.

Completed:
- SSH access to A6000 server confirmed.
- Server identified as `warpgolem`.
- GPU confirmed available:
  - NVIDIA RTX 6000 Ada Generation
  - NVIDIA driver: 555.58.02
  - CUDA version reported by `nvidia-smi`: 12.5
- Created conda environment:
  - `/home/laura/.conda/envs/rnagenesis-a6000`
  - Python 3.8.13
- Installed CUDA-compatible PyTorch:
  - torch 2.1.2+cu121
  - torchvision 0.16.2
  - torchaudio 2.1.2
- Verified PyTorch GPU access:
  - `torch.cuda.is_available()` returned True
  - PyTorch detected NVIDIA RTX 6000 Ada Generation
- Installed and verified core dependencies:
  - numpy 1.24.4
  - transformers 4.36.2
  - diffusers 0.25.0
  - huggingface_hub 0.20.3
  - BioPython
  - ViennaRNA
  - einops
  - timm
  - torchinfo
  - tqdm
- Resolved dependency mismatch:
  - `diffusers==0.25.0` required older `huggingface_hub` because it imports `cached_download`.
  - Pinned `huggingface_hub==0.20.3`.
  - Pinned `transformers==4.36.2` to remain compatible.
- Exported A6000 environment to:
  - `environment/environment_a6000.yml`
- Configured Git identity on server:
  - name: Laura Hardy
  - email: laura.hardy625@gmail.com
- Set up GitHub SSH access from `warpgolem`.
- Cloned project repository:
  - `~/rnagenesis-aptamer-mres`
- Cloned RNAGenesis fork:
  - `~/RNAGenesis`
- Confirmed RNAGenesis commit:
  - `d00899e (HEAD -> main, origin/main, origin/HEAD) Update README.md`

Checkpoint/config download:
- Began Phase 1.5 Zenodo downloads directly on A6000.
- `checkpoints.zip` completed downloading.
- Remaining downloads were moved into a `tmux` session so they can continue after SSH disconnect:
  - tmux session: `rnagenesis-downloads`
  - remaining expected files:
    - `configs.zip`
    - `progen2-base.zip`
    - `progen2-small.zip`

Notes:
- The checkpoint files are large and are not tracked in Git.
- Because the A6000 server is scheduled for formatting after May 8, important code, logs, environment files, and small results must be committed and pushed to GitHub.
- Large Zenodo checkpoint files may need to be redownloaded after the server upgrade unless copied elsewhere.

Next:
- Reconnect to `warpgolem`.
- Reattach to tmux with:
  - `tmux attach -t rnagenesis-downloads`
- Check whether downloads completed.
- Verify file sizes with:
  - `ls -lh ~/RNAGenesis/checkpoints.zip ~/RNAGenesis/configs.zip ~/RNAGenesis/progen2-base.zip ~/RNAGenesis/progen2-small.zip`
- Unzip and verify expected RNAGenesis paths.
- If checkpoint/config structure is correct, proceed to Phase 2: operational reproduction of the aptamer pipeline.

