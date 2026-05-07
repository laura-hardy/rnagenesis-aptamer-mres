#!/usr/bin/env bash
set -euo pipefail

cd ~/RNAGenesis

source /opt/anaconda3/etc/profile.d/conda.sh
conda activate /home/laura/.conda/envs/rnagenesis-a6000

python generation.py \
  --enc_dec_file "configs/rnagenesis/autoencoder" \
  --dm_file "checkpoints/Aptamer/diffusion" \
  --decoder_config "config-progen2-small-rna_tokenizer_v2" \
  --num_inference_steps 50 \
  --batch_size 16 \
  --batch_num 1 \
  --seed 42 \
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
  --remark "_medium_test_seed42_steps50_batch16" \
  --device "cuda" \
  --superfolder "generation_sequences" \
  --mid_folder "RNAGenesis_Aptamer_medium_test"
