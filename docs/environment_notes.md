# RNAGenesis Environment Notes

## Core environment (from repository)
- Python: 3.8.13
- PyTorch:
  - torch==2.1.2
  - torchvision==0.16.2
  - torchaudio==2.1.2

## Key observations
- CUDA version is not explicitly specified.
- Environment relies on pip-installed PyTorch → CUDA compatibility depends on install method.
- Some system libraries (e.g. openssl=1.1.1) are outdated and may cause issues on modern systems.

## Likely required dependencies (core pipeline)
- torch / transformers / diffusers
- pytorch-lightning
- viennarna (for RNA folding metrics)
- biopython
- sentencepiece

## Potential missing dependencies (from code inspection)
- einops
- timm
- torchinfo
- tqdm

## Optional / pathway-specific dependencies
- tensorflow (framepool module)
- nupack (structure prediction scripts)
- catboost / ruptures (analysis scripts)

## Installation strategy

### H200 (primary execution environment)
- Use repository environment as baseline
- Explicitly install CUDA-compatible PyTorch
- Add missing dependencies only when required
- Record full environment after successful setup

### MacBook (development environment)
- Lightweight environment only
- No attempt to fully reproduce GPU setup
- Used for:
  - code reading
  - debugging logic
  - small tests

## Open questions
- Which dependencies are strictly required for aptamer pipeline?
- Best CUDA version for H200 + PyTorch 2.1.2

