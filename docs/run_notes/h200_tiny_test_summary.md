## 2026-06-10 — H200 RNAGenesis AdaLayerNorm compatibility patch

During the first H200 tiny aptamer generation run, the model loaded successfully and began the diffusion loop, but failed inside `diffusers.models.normalization.AdaLayerNorm.forward`.

Error:
- `ValueError: not enough values to unpack (expected 2, got 1)`

This matched the previous A6000 compatibility issue.

Applied the same local patch in the H200 conda environment:
- file: `/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/site-packages/diffusers/models/normalization.py`
- backup: `normalization.py.bak_rnagenesis_h200_2026_06_10`
- changed:
  - `scale, shift = torch.chunk(emb, 2)`
- to:
  - `scale, shift = torch.chunk(emb, 2, dim=-1)`

Interpretation:
- H200 CUDA/PyTorch and RNAGenesis checkpoint loading are working.
- Failure was due to a `diffusers` compatibility mismatch, not a model or checkpoint failure.
# H200 RNAGenesis tiny aptamer generation test

Date: 2026-06-10  
Host: aai / H200  
Conda environment: rnagenesis-h200  
RNAGenesis path: ~/RNAGenesis  
Script: scripts/run_rnagenesis_aptamer_tiny_test_h200.sh  

Status: succeeded

Run configuration:
- enc_dec_file: configs/rnagenesis/autoencoder
- dm_file: checkpoints/Aptamer/diffusion
- decoder_config: config-progen2-small-rna_tokenizer_v2
- num_inference_steps: 5
- batch_size: 2
- batch_num: 1
- seed: 42
- eta: 0
- max_seq_len: 37
- top_p: 0.95
- top_k: 0
- device: cuda
- output folder: ~/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_tiny_test

Notes:
- The H200 run initially reproduced the A6000 AdaLayerNorm compatibility error in diffusers.
- Applied local patch to the H200 environment:
  - changed `torch.chunk(emb, 2)` to `torch.chunk(emb, 2, dim=-1)`
  - file: $CONDA_PREFIX/lib/python3.8/site-packages/diffusers/models/normalization.py
- After patching, tiny generation completed successfully.

## Local diffusers patch verification

The H200 environment includes a local compatibility patch to `diffusers.models.normalization.AdaLayerNorm`.

Verified patched lines:

```text
/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/site-packages/diffusers/models/normalization.py:46:         scale, shift = torch.chunk(emb, 2, dim=-1)
/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/site-packages/diffusers/models/normalization.py:180:         scale, shift = torch.chunk(emb, 2, dim=1)

Then check the file:

```bash
tail -40 docs/run_notes/h200_tiny_test_summary.md
tail -40 docs/run_notes/h200_tiny_test_summary.md

## Local diffusers patch verification

The H200 environment includes a local compatibility patch to `diffusers.models.normalization.AdaLayerNorm`.

Verified patched lines:

```text
/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/site-packages/diffusers/models/normalization.py:46:         scale, shift = torch.chunk(emb, 2, dim=-1)
/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/site-packages/diffusers/models/normalization.py:180:         scale, shift = torch.chunk(emb, 2, dim=1)

Then check the file:

```bash
tail -40 docs/run_notes/h200_tiny_test_summary.md
tail -40 docs/run_notes/h200_tiny_test_summary.md

## Local diffusers patch verification

The H200 environment includes a local compatibility patch to `diffusers.models.normalization.AdaLayerNorm`.

Verified patched lines:

```text
/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/site-packages/diffusers/models/normalization.py:46:         scale, shift = torch.chunk(emb, 2, dim=-1)
/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/site-packages/diffusers/models/normalization.py:180:         scale, shift = torch.chunk(emb, 2, dim=1)

Interpretation:

Line 46 is the RNAGenesis compatibility patch applied on H200.
Line 180 was already using an explicit dimension and was not changed for this patch.
This manual site-package patch is not captured by conda env export, so it is documented separately here.
