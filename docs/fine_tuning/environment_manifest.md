# M0 environment manifest — 25 September 2026

**Environment inventory: recorded on host `aai`. M0: COMPLETE / GO —
25 September 2026.** No GPU computation, training, generation, optimiser
construction or biological-data access occurred during this inspection.
The clean preflight that closed M0 is recorded in
[M0 data contract verification](m0_data_contract_verification.md). It did
not re-measure this environment or the diffusers patch. This record does
not authorise biological fine-tuning.

## Host and Conda environment

```text
host = aai
authoritative conda environment = /home/laura/miniconda3/envs/rnagenesis-h200
Python = 3.8.13
```

The Mac is not this environment. Package versions below were observed in the
named Conda environment.

## Package versions

| Package | Version |
| --- | --- |
| torch | 2.1.2+cu121 |
| torch CUDA runtime | 12.1 |
| transformers | 4.36.2 |
| diffusers | 0.25.0 |
| accelerate | 0.25.0 |
| huggingface_hub | 0.20.3 |
| numpy | 1.22.0 |
| scipy | 1.10.1 |
| pandas | 1.3.1 |
| Biopython | 1.83 |
| ViennaRNA | 2.7.0 |

## GPU, driver and CUDA

Hardware observed on `aai`:

| Device | Model | Memory |
| --- | --- | --- |
| GPU0 | NVIDIA H200 NVL | 143771 MiB |
| GPU1 | NVIDIA H200 NVL | 143771 MiB |

```text
NVIDIA driver = 580.95.05
torch CUDA runtime = 12.1
```

The torch CUDA runtime is the runtime bundled with `torch==2.1.2+cu121`.
A separate host CUDA toolkit version was not recorded. Free memory,
utilization and a full `nvidia-smi` snapshot were not archived, because no
GPU computation was performed.

GPU0 remains the project default in the implementation plan. On 25 September
2026, GPU1 was explicitly authorised for this session. That authorisation is
session-specific. It is not a permanent configuration change, and it does
not change the GPU0 default for later sessions.

## Conda history

```text
file:   /home/laura/miniconda3/envs/rnagenesis-h200/conda-meta/history
SHA256: 1a94d259addd1e002dd5b6e6910e5a80cef22ddc8ee729147dba528b24d75114
```

## Required local diffusers compatibility patch

Installed file:

```text
/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/site-packages/diffusers/models/normalization.py
```

Current file SHA256:

```text
09bc632069f1d6e1dc1b1cb7f5b9ca096c83e3010835f11b8dc6c58b45aa13a5
```

Required code, observed inside `AdaLayerNorm.forward` before
`x = self.norm(x) * (1 + scale) + shift`:

```python
scale, shift = torch.chunk(emb, 2, dim=-1)
```

The installed `diffusers-0.25.0` dist-info `RECORD` contains the original
hash of this file:

```text
sha256=ns8zDMdCYlJMZynNH9F0rDn-yvJ36O52V5FF3nqLZuI
```

That RECORD token is the URL-safe base64 form of SHA256
`9ecf330cc74262524c6729cd1fd174ac39fecaf277e8ee76579145de7a8b66e2`.

Current file, in the same RECORD form:

```text
sha256=CbxjIGnx1uHcGxy39bnKCWyD4wEINfEbjcbFi0WqE6U
```

That token matches the current hex digest above.
`matches installed RECORD hash = false`.

This independently confirms that `normalization.py` differs from the
original installed diffusers package. A normal package or version export
would not capture the local patch.

## Reproducibility consequence

An environment rebuild must verify or reproduce this patch before RNAGenesis
use. Matching `diffusers==0.25.0` is not sufficient. The rebuilt
`normalization.py` must contain the required line in `AdaLayerNorm.forward`
and should be checked against the current file SHA256 recorded here. The
Conda history hash records the environment history file; it does not by
itself reproduce the site-packages edit.

## M0 status

M0 is COMPLETE / GO. Development-profile validation, REF/EVAL isolation,
RNAGenesis code-integration review and the human gate are recorded in
[M0 data contract verification](m0_data_contract_verification.md). Model-asset
hashes remain a separate record. This inspection's patch hash is still the
diffusers verification for M0; the passing preflight did not re-hash
`normalization.py`.

Optimiser membership was not measured here, and the preflight took no
optimizer step. That check remains a later frozen-model assertion. It does
not leave M0 incomplete.

No GPU computation was needed or performed for the M0 data, environment or
asset inspections. M0 completion does not mean biological fine-tuning has
run. The next milestone is M1.
