#!/usr/bin/env bash
set -euo pipefail

source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate rnagenesis-h200

CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-1}"
export CUDA_VISIBLE_DEVICES

PROJECT_REPO="$HOME/rnagenesis-aptamer-mres"
RNAGENESIS_REPO="$HOME/RNAGenesis"
RESULTS_DIR="${PROJECT_REPO}/results/phase2_4_repeatability"
REPORT_PATH="${PROJECT_REPO}/docs/run_notes/h200_phase2_4_repeatability_report.md"

cd "$RNAGENESIS_REPO"

RNAGENESIS_COMMIT="$(git log --oneline -1)"
RUN_DATE="$(date)"
RUN_HOST="$(hostname)"
CONDA_ENV="${CONDA_DEFAULT_ENV:-unset}"

echo "============================================================"
echo "RNAGenesis H200 Phase 2.4 — seed repeatability test"
echo "============================================================"
echo "date:                 ${RUN_DATE}"
echo "hostname:             ${RUN_HOST}"
echo "working directory:    $(pwd)"
echo "conda environment:    ${CONDA_ENV}"
echo "CUDA_VISIBLE_DEVICES: ${CUDA_VISIBLE_DEVICES}"
echo "RNAGenesis commit:    ${RNAGENESIS_COMMIT}"
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

run_generation() {
  local seed="$1"
  local mid_folder="$2"
  local remark="$3"
  local label="$4"

  echo ""
  echo "============================================================"
  echo "Starting generation: ${label}"
  echo "seed:       ${seed}"
  echo "mid_folder: ${mid_folder}"
  echo "remark:     ${remark}"
  echo "started at: $(date)"
  echo "============================================================"

  python generation.py \
    --enc_dec_file "configs/rnagenesis/autoencoder" \
    --dm_file "checkpoints/Aptamer/diffusion" \
    --decoder_config "config-progen2-small-rna_tokenizer_v2" \
    --num_inference_steps 20 \
    --batch_size 8 \
    --batch_num 1 \
    --seed "${seed}" \
    --eta 0 \
    --target_class 0 \
    --guidance_classifier_model_config "dummy_unused.yaml" \
    --guidance_scale 1.0 \
    --classifier_loss_type "l2" \
    --recurrence_step 1 \
    --guidance_start_step 0 \
    --guidance_stop_step 20 \
    --search_goal "similarity" \
    --active_size 1 \
    --branch_size 1 \
    --max_seq_len 37 \
    --do_sample \
    --top_p 0.95 \
    --top_k 0 \
    --eos_token "2" \
    --bos_token "1" \
    --remark "${remark}" \
    --device "cuda" \
    --superfolder "generation_sequences" \
    --mid_folder "${mid_folder}"

  echo "------------------------------------------------------------"
  echo "Completed generation: ${label} at $(date)"
  echo "------------------------------------------------------------"
}

MID_FOLDER_A="RNAGenesis_Aptamer_h200_phase2_4_seed42_runA"
MID_FOLDER_B="RNAGenesis_Aptamer_h200_phase2_4_seed42_runB"
MID_FOLDER_C="RNAGenesis_Aptamer_h200_phase2_4_seed43"

REMARK_A="_h200_phase2_4_seed42_runA_steps20_batch8"
REMARK_B="_h200_phase2_4_seed42_runB_steps20_batch8"
REMARK_C="_h200_phase2_4_seed43_steps20_batch8"

run_generation 42 "${MID_FOLDER_A}" "${REMARK_A}" "seed42 replicate A"
run_generation 42 "${MID_FOLDER_B}" "${REMARK_B}" "seed42 replicate B"
run_generation 43 "${MID_FOLDER_C}" "${REMARK_C}" "seed43 different-seed comparison"

echo ""
echo "============================================================"
echo "All generation jobs complete at $(date)"
echo "Running Python analysis..."
echo "============================================================"

python "$PROJECT_REPO/scripts/analyze_phase2_4_repeatability.py" \
  --rnagenesis-repo "$RNAGENESIS_REPO" \
  --project-repo "$PROJECT_REPO" \
  --output-folder-a "RNAGenesis_Aptamer_h200_phase2_4_seed42_runA" \
  --output-folder-b "RNAGenesis_Aptamer_h200_phase2_4_seed42_runB" \
  --output-folder-c "RNAGenesis_Aptamer_h200_phase2_4_seed43" \
  --label-a "seed42_runA" \
  --label-b "seed42_runB" \
  --label-c "seed43" \
  --results-dir "$RESULTS_DIR" \
  --report-path "$REPORT_PATH" \
  --run-date "$RUN_DATE" \
  --host "$RUN_HOST" \
  --conda-env "$CONDA_ENV" \
  --cuda-visible-devices "$CUDA_VISIBLE_DEVICES" \
  --rnagenesis-commit "$RNAGENESIS_COMMIT"

echo ""
echo "============================================================"
echo "Phase 2.4 repeatability workflow complete at $(date)"
echo "Report written to: ${REPORT_PATH}"
echo "Copied outputs in: ${RESULTS_DIR}"
echo "============================================================"
