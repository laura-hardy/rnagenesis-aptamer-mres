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
