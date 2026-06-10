#!/usr/bin/env bash
set -euo pipefail

cd ~/RNAGenesis

source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate rnagenesis-h200

export CUDA_VISIBLE_DEVICES=1

OUTPUT_DIR="$HOME/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_baseline_30k"

echo "============================================================"
echo "RNAGenesis H200 baseline 30k — Phase 4.1"
echo "============================================================"
echo "date:              $(date)"
echo "hostname:          $(hostname)"
echo "working directory: $(pwd)"
echo "conda environment: ${CONDA_DEFAULT_ENV:-unset}"
echo "CUDA_VISIBLE_DEVICES: ${CUDA_VISIBLE_DEVICES}"
echo "RNAGenesis commit:  $(git log --oneline -1)"
echo "output directory:   ${OUTPUT_DIR}"
echo "------------------------------------------------------------"
python - <<'PY'
import torch

print(f"torch version:      {torch.__version__}")
print(f"cuda available:     {torch.cuda.is_available()}")
print(f"visible gpu count:  {torch.cuda.device_count()}")
if torch.cuda.is_available() and torch.cuda.device_count() > 0:
    print(f"visible gpu name:   {torch.cuda.get_device_name(0)}")
PY
echo "============================================================"

mkdir -p "${OUTPUT_DIR}"

# Optional resume controls:
#   START_CHUNK=7 END_CHUNK=10 ./run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh
START_CHUNK="${START_CHUNK:-1}"
END_CHUNK="${END_CHUNK:-10}"

echo "Chunk range: ${START_CHUNK} to ${END_CHUNK}"

for CHUNK in $(seq "${START_CHUNK}" "${END_CHUNK}"); do
  SEED=$((4200 + CHUNK))
  REMARK="_h200_baseline_30k_chunk${CHUNK}_seed${SEED}_steps50_batch16_batchnum188_gpu1"

  echo ""
  echo "============================================================"
  echo "Starting chunk ${CHUNK}/10"
  echo "seed:   ${SEED}"
  echo "remark: ${REMARK}"
  echo "started at: $(date)"
  echo "============================================================"

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
    --remark "${REMARK}" \
    --device "cuda" \
    --superfolder "generation_sequences" \
    --mid_folder "RNAGenesis_Aptamer_h200_baseline_30k"

  echo "------------------------------------------------------------"
  echo "Completed chunk ${CHUNK}/10 at $(date)"
  echo "------------------------------------------------------------"
done

echo ""
echo "============================================================"
echo "All chunks complete at $(date)"
echo "============================================================"
echo "Generated .txt files under ${OUTPUT_DIR}:"
if compgen -G "${OUTPUT_DIR}/*.txt" > /dev/null; then
  ls -lh "${OUTPUT_DIR}"/*.txt
  echo ""
  echo "Line counts:"
  wc -l "${OUTPUT_DIR}"/*.txt
else
  echo "No .txt files found."
fi
echo "============================================================"
