# H200 Phase 2.4 — fix random seeds and confirm repeatability

## Stage

Phase 2.4 — fix random seeds and confirm repeatability

## Purpose

Test whether RNAGenesis aptamer generation is repeatable under a fixed seed on the H200 server, and whether changing the seed changes the generated outputs.

## Run metadata

- Date: Thu 11 Jun 2026 12:04:41 AEST
- Host: aai
- Conda environment: rnagenesis-h200
- CUDA_VISIBLE_DEVICES: 0
- RNAGenesis commit: d00899e Update README.md

## Generation settings

- num_inference_steps: 20
- batch_size: 8
- batch_num: 1
- seeds tested: 42 (replicate A), 42 (replicate B), 43 (different-seed comparison)
- max_seq_len: 37
- top_p: 0.95
- top_k: 0
- enc_dec_file: configs/rnagenesis/autoencoder
- dm_file: checkpoints/Aptamer/diffusion
- decoder_config: config-progen2-small-rna_tokenizer_v2
- guidance: off
- tree/search: off

## RNAGenesis source output files

- `/home/laura/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_phase2_4_seed42_runA/seqs_wo_guidance_top_p=0.95_2_8_h200_phase2_4_seed42_runA_steps20_batch8.txt`
- `/home/laura/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_phase2_4_seed42_runB/seqs_wo_guidance_top_p=0.95_2_8_h200_phase2_4_seed42_runB_steps20_batch8.txt`
- `/home/laura/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_phase2_4_seed43/seqs_wo_guidance_top_p=0.95_2_8_h200_phase2_4_seed43_steps20_batch8.txt`

## Project copied output files

- `/home/laura/rnagenesis-aptamer-mres/results/phase2_4_repeatability/seed42_runA.txt`
- `/home/laura/rnagenesis-aptamer-mres/results/phase2_4_repeatability/seed42_runB.txt`
- `/home/laura/rnagenesis-aptamer-mres/results/phase2_4_repeatability/seed43.txt`

## Line counts

| File | Lines |
| --- | ---: |
| seed42_runA.txt | 8 |
| seed42_runB.txt | 8 |
| seed43.txt | 8 |

## SHA256 hashes

| File | SHA256 |
| --- | --- |
| seed42_runA.txt | `3f00afdcfc6c0b47b0851de40fc2f511cb28f4c4705a7bc5df60e7c0f17ad6c2` |
| seed42_runB.txt | `3f00afdcfc6c0b47b0851de40fc2f511cb28f4c4705a7bc5df60e7c0f17ad6c2` |
| seed43.txt | `9e3d7594dc628363610cf3cfdc369955d4d4e9877c9f6c7a01f2a2ccc5ff23ab` |

## Same-seed comparison result

Comparison: seed42_runA.txt vs seed42_runB.txt

Result: **identical**

## Different-seed comparison result

Comparison: seed42_runA.txt vs seed43.txt

Result: **different**

## Interpretation

- Same-seed repeatability: Fixed-seed generation appears exactly repeatable for this small H200 workload.
- Different-seed behaviour: Changing the seed changes sampled outputs as expected.

## Next step

Proceed to cleaning, merging, deduplicating, and characterising the 30,080-sequence unadapted RNAGenesis baseline pool.
