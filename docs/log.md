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