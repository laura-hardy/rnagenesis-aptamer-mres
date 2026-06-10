# H200 baseline 30k — Phase 4.1 run plan

Date: 2026-06-10  
Host: aai / H200  
Conda environment: `rnagenesis-h200`  
RNAGenesis path: `~/RNAGenesis`  
Project repo path: `~/rnagenesis-aptamer-mres`  
Script: `scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh`

## Goal

Generate approximately 30,000 unadapted RNAGenesis aptamer sequences on the H200 server for Phase 4.1 baseline characterisation. Outputs remain under the RNAGenesis repo and are not copied into this project repo.

## H200 environment

- Conda installation: `~/miniconda3`
- Conda environment: `rnagenesis-h200`
- Python: 3.8.13
- PyTorch: 2.1.2+cu121 (pip CUDA wheels)
- RNAGenesis working directory: `~/RNAGenesis`

## GPU isolation

Booked physical GPU: **GPU1**

The script sets:

```bash
export CUDA_VISIBLE_DEVICES=1
```

This restricts the job to physical GPU1 without killing or interfering with other users' processes. PyTorch will see one visible device (`cuda:0`), mapped to physical GPU1.

Do not use `sudo`. Do not assume exclusive server access beyond this environment variable.

## Prerequisite tests passed

The following H200 generation smoke tests completed successfully before this baseline run:

| Test   | Script                                      | Status   |
|--------|---------------------------------------------|----------|
| Tiny   | `scripts/run_rnagenesis_aptamer_tiny_test_h200.sh` | Passed   |
| Small  | H200 small test (steps 20, batch 8)       | Passed   |
| Medium | H200 medium test (steps 50, batch 16)     | Passed   |

See `docs/run_notes/h200_tiny_test_summary.md` for tiny-test details and the AdaLayerNorm compatibility patch.

## Generation configuration

Run from `~/RNAGenesis` via `python generation.py`:

| Parameter | Value |
|-----------|-------|
| `enc_dec_file` | `configs/rnagenesis/autoencoder` |
| `dm_file` | `checkpoints/Aptamer/diffusion` |
| `decoder_config` | `config-progen2-small-rna_tokenizer_v2` |
| `num_inference_steps` | 50 |
| `batch_size` | 16 |
| `batch_num` | 188 |
| `eta` | 0 |
| `target_class` | 0 |
| `guidance_classifier_model_config` | `dummy_unused.yaml` |
| `guidance_scale` | 1.0 |
| `classifier_loss_type` | `l2` |
| `recurrence_step` | 1 |
| `guidance_start_step` | 0 |
| `guidance_stop_step` | 50 |
| `search_goal` | `similarity` |
| `active_size` | 1 |
| `branch_size` | 1 |
| `max_seq_len` | 37 |
| `do_sample` | enabled |
| `top_p` | 0.95 |
| `top_k` | 0 |
| `eos_token` | `2` |
| `bos_token` | `1` |
| `device` | `cuda` |
| `superfolder` | `generation_sequences` |
| `mid_folder` | `RNAGenesis_Aptamer_h200_baseline_30k` |

## Chunking rationale

The full run is split into **10 chunks** so that:

- Progress is checkpointed if a chunk fails or the session drops.
- Each chunk uses a distinct seed for reproducibility.
- The job is easier to monitor and resume inside tmux.
- Partial recovery is supported via `START_CHUNK` and `END_CHUNK` environment variables (default: 1–10).

| Chunk | Seed | Sequences per chunk |
|-------|------|---------------------|
| 1 | 4201 | 3,008 |
| 2 | 4202 | 3,008 |
| 3 | 4203 | 3,008 |
| 4 | 4204 | 3,008 |
| 5 | 4205 | 3,008 |
| 6 | 4206 | 3,008 |
| 7 | 4207 | 3,008 |
| 8 | 4208 | 3,008 |
| 9 | 4209 | 3,008 |
| 10 | 4210 | 3,008 |

Per chunk: `batch_size × batch_num = 16 × 188 = 3,008` sequences.  
Remark pattern: `_h200_baseline_30k_chunk{N}_seed{SEED}_steps50_batch16_batchnum188_gpu1`

## Expected sequence count

Raw total across all chunks:

```text
16 × 188 × 10 = 30,080 sequences
```

## Output folder

All generated sequence files remain under:

```text
~/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_baseline_30k/
```

Do **not** move or copy raw generated `.txt` files into `~/rnagenesis-aptamer-mres`. Cleaning and analysis happen in a separate pipeline step.

## How to run

On the H200 server, inside tmux:

```bash
cd ~/rnagenesis-aptamer-mres
bash scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh 2>&1 | tee docs/run_notes/h200_baseline_30k_output.log
```

To resume a partial run (e.g. chunks 7–10 after chunks 1–6 completed):

```bash
START_CHUNK=7 END_CHUNK=10 bash scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh 2>&1 | tee -a docs/run_notes/h200_baseline_30k_output.log
```

If no variables are supplied, the script runs chunks 1–10 as before.

## Post-run checks

After all chunks complete, the script automatically:

1. Lists `.txt` files under the output folder.
2. Runs `wc -l` on generated `.txt` files.

Manual checks:

```bash
ls -lh ~/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_baseline_30k/
wc -l ~/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_baseline_30k/*.txt
```

Confirm:

- 10 chunk output files (or equivalent per RNAGenesis naming).
- Total line count is approximately 30,080.
- No unexpected empty or truncated files.

## Do not commit generated sequences

Generated sequence files under `~/RNAGenesis/generation_sequences/` must **not** be committed to either repository. Only scripts, run notes, and logs in this project repo are version-controlled.

## Required diffusers patch

The H200 `rnagenesis-h200` environment requires a local AdaLayerNorm compatibility patch in `diffusers` before generation will succeed. This is documented in `docs/run_notes/h200_tiny_test_summary.md`:

- File: `$CONDA_PREFIX/lib/python3.8/site-packages/diffusers/models/normalization.py`
- Change: `torch.chunk(emb, 2)` → `torch.chunk(emb, 2, dim=-1)` (line 46)

This manual site-package patch is not captured by `conda env export` and must remain documented separately for reproducibility.
