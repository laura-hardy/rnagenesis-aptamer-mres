# Phase 4.1 — Unadapted RNAGenesis 30k baseline generation

This folder contains the raw unadapted RNAGenesis aptamer-generation outputs used for Phase 4.1 baseline characterisation.

The purpose of this run was to generate a large baseline pool of RNA aptamer-like sequences from the unadapted RNAGenesis model, before any project-specific adaptation, fine-tuning, filtering, ranking, or target conditioning. These sequences provide the starting point for subsequent cleaning, deduplication, baseline characterisation, and comparison against null/random RNA controls.

## Output summary

The run produced:

- 10 chunk files
- 3,008 raw sequences per chunk
- 30,080 raw generated sequences total

The raw output files are stored in:

```text
results/phase4_1_unadapted_rnagenesis_30k/raw/
```

Each chunk file corresponds to one RNAGenesis generation call with a distinct random seed.

## Hardware and execution environment

The generation was run on the shared H200 server.



```
Host: aai / H200 server
GPU used: physical GPU1
GPU type: NVIDIA H200 NVL
GPU isolation: CUDA_VISIBLE_DEVICES=1
Conda environment: rnagenesis-h200
Python: 3.8.13
PyTorch: 2.1.2+cu121
Torch CUDA runtime: 12.1
```

The run was launched inside `tmux` to protect against SSH disconnection:



```
tmux session: rnagenesis_baseline_30k_gpu1
```

The long generation run was executed using:



```
scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh
```

## RNAGenesis source and checkpoint state

The generation was run from the RNAGenesis repository on the H200 server:


```
~/RNAGenesis
```

The RNAGenesis commit used for the project setup was pinned as:



```
d00899e
```

The run used the Zenodo RNAGenesis assets downloaded and installed into the RNAGenesis repository on the H200 server.

Key model/configuration paths:



```
configs/rnagenesis/autoencoder
checkpoints/Aptamer/diffusion
models/autoencoder/decoder/checkpoints/progen2-small
```

The main generation entry point was:



```
generation.py
```

Note: the upstream README referred to `generate.py`, but this repository version contains and uses `generation.py`.

## Local environment compatibility patch

The H200 `rnagenesis-h200` environment required the same local `diffusers` AdaLayerNorm compatibility patch previously identified on the A6000.

Patched file:



```
$CONDA_PREFIX/lib/python3.8/site-packages/diffusers/models/normalization.py
```

Patch applied:


```
scale, shift = torch.chunk(emb, 2)
```

was changed to:


```
scale, shift = torch.chunk(emb, 2, dim=-1)
```

This patch was required because the unpatched `diffusers` code split `emb` along the default dimension, causing the RNAGenesis diffusion model to fail during inference with:



```
ValueError: not enough values to unpack (expected 2, got 1)
```

This manual site-package patch is not captured by `conda env export`, so it is documented separately in the project run notes.

## Generation configuration

The 30k baseline run used unadapted RNAGenesis generation with the following configuration:



```
enc_dec_file: configs/rnagenesis/autoencoder
dm_file: checkpoints/Aptamer/diffusion
decoder_config: config-progen2-small-rna_tokenizer_v2
num_inference_steps: 50
batch_size: 16
batch_num: 188
eta: 0
target_class: 0
guidance_classifier_model_config: dummy_unused.yaml
guidance_scale: 1.0
classifier_loss_type: l2
recurrence_step: 1
guidance_start_step: 0
guidance_stop_step: 50
search_goal: similarity
active_size: 1
branch_size: 1
max_seq_len: 37
do_sample: enabled
top_p: 0.95
top_k: 0
eos_token: 2
bos_token: 1
device: cuda
superfolder: generation_sequences
mid_folder: RNAGenesis_Aptamer_h200_baseline_30k
```

Guidance and tree search were not enabled. The run therefore represents unguided/unadapted RNAGenesis sampling under the selected aptamer checkpoint and decoder configuration.

## Chunking design

The run was split into 10 chunks rather than run as a single monolithic command. This was done to improve robustness on a shared server and to make partial recovery easier if a chunk failed.

Each chunk used:



```
batch_size = 16
batch_num = 188
sequences per chunk = 16 × 188 = 3,008
```

The full run used:



```
10 chunks × 3,008 sequences = 30,080 raw sequences
```

Seeds were assigned by chunk:


| Chunk | Seed | Expected sequences |
| ----- | ---- | ------------------ |
| 1     | 4201 | 3,008              |
| 2     | 4202 | 3,008              |
| 3     | 4203 | 3,008              |
| 4     | 4204 | 3,008              |
| 5     | 4205 | 3,008              |
| 6     | 4206 | 3,008              |
| 7     | 4207 | 3,008              |
| 8     | 4208 | 3,008              |
| 9     | 4209 | 3,008              |
| 10    | 4210 | 3,008              |


## Command used

The run was launched from the project repository using the H200 baseline generation script:



```
cd ~/rnagenesis-aptamer-mres

bash scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh \
  2>&1 | tee docs/run_notes/h200_baseline_30k_output.log
```

Internally, each chunk called `generation.py` from `~/RNAGenesis`. The per-chunk command template was:



```
python generation.py \
  --enc_dec_file "configs/rnagenesis/autoencoder" \
  --dm_file "checkpoints/Aptamer/diffusion" \
  --decoder_config "config-progen2-small-rna_tokenizer_v2" \
  --num_inference_steps 50 \
  --batch_size 16 \
  --batch_num 188 \
  --seed "${SEED}" \
  --eta 0 \
  --target_class 0 \
  --guidance_classifier_model_config "dummy_unused.yaml" \
  --guidance_scale 1.0 \
  --classifier_loss_type "l2" \
  --recurrence_step 1 \
  --guidance_start_step 0 \
  --guidance_stop_step 50 \
  --search_goal "similarity" \
  --active_size 1 \
  --branch_size 1 \
  --max_seq_len 37 \
  --do_sample \
  --top_p 0.95 \
  --top_k 0 \
  --eos_token "2" \
  --bos_token "1" \
  --remark "_h200_baseline_30k_chunk${CHUNK}_seed${SEED}_steps50_batch16_batchnum188_gpu1" \
  --device "cuda" \
  --superfolder "generation_sequences" \
  --mid_folder "RNAGenesis_Aptamer_h200_baseline_30k"
```

## Runtime

The run completed successfully.


```
Start:   Wed 10 Jun 2026 16:11:51 AEST
End:     Wed 10 Jun 2026 17:39:40 AEST
Elapsed: 1 hour, 27 minutes, 49 seconds
```

Total elapsed seconds:


```
5,269 seconds
```

Approximate throughput:



```
30,080 raw sequences / 5,269 seconds ≈ 5.71 raw sequences per second
```

Each chunk took approximately 8 minutes 45–49 seconds.

## Verification

The raw output count was verified with:


```
cd ~/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_baseline_30k
wc -l *.txt
```

The verified line counts were:



```
3008 seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk1_seed4201_steps50_batch16_batchnum188_gpu1.txt
3008 seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk2_seed4202_steps50_batch16_batchnum188_gpu1.txt
3008 seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk3_seed4203_steps50_batch16_batchnum188_gpu1.txt
3008 seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk4_seed4204_steps50_batch16_batchnum188_gpu1.txt
3008 seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk5_seed4205_steps50_batch16_batchnum188_gpu1.txt
3008 seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk6_seed4206_steps50_batch16_batchnum188_gpu1.txt
3008 seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk7_seed4207_steps50_batch16_batchnum188_gpu1.txt
3008 seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk8_seed4208_steps50_batch16_batchnum188_gpu1.txt
3008 seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk9_seed4209_steps50_batch16_batchnum188_gpu1.txt
3008 seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk10_seed4210_steps50_batch16_batchnum188_gpu1.txt
30080 total
```

Checksums for the raw generated files are stored in:



```
checksums/sha256_raw_generated_files.txt
```

## Output files

The raw generated sequence files are stored in:



```
raw/
```

The files are:



```
seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk1_seed4201_steps50_batch16_batchnum188_gpu1.txt
seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk2_seed4202_steps50_batch16_batchnum188_gpu1.txt
seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk3_seed4203_steps50_batch16_batchnum188_gpu1.txt
seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk4_seed4204_steps50_batch16_batchnum188_gpu1.txt
seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk5_seed4205_steps50_batch16_batchnum188_gpu1.txt
seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk6_seed4206_steps50_batch16_batchnum188_gpu1.txt
seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk7_seed4207_steps50_batch16_batchnum188_gpu1.txt
seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk8_seed4208_steps50_batch16_batchnum188_gpu1.txt
seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk9_seed4209_steps50_batch16_batchnum188_gpu1.txt
seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk10_seed4210_steps50_batch16_batchnum188_gpu1.txt
```

## Notes on raw sequence format

These are raw RNAGenesis outputs. They have not yet been cleaned, deduplicated, filtered, ranked, structurally evaluated, or target-conditioned.

Some sequences include the expected raw generation prefix/special-token pattern, for example leading `11`. Cleaning and standardisation are performed in later pipeline stages.

## Version-control decision

The raw generated sequence files are approximately 1.2 MB total. Because they are small text files and represent a core Phase 4.1 research artifact, they are committed to this project repository.

Large RNAGenesis assets remain excluded from Git, including:


```
checkpoints/
configs/
Zenodo archives
model weight files
```

## Next steps

The next analysis steps are:

1.  Merge the 10 raw chunk files. 
2.  Clean model-specific raw tokens/prefixes if required. 
3.  Deduplicate generated sequences. 
4.  Prepare exactly 30,000 sequences for baseline characterisation. 
5.  Compute sequence-level and structure-level baseline metrics. 
6.  Compare against appropriate null/random RNA controls.

