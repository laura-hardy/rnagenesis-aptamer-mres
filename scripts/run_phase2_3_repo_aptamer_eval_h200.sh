#!/usr/bin/env bash
set -euo pipefail

PROJECT_REPO="$HOME/rnagenesis-aptamer-mres"
RNAGENESIS_REPO="$HOME/RNAGenesis"
OUTPUT_DIR="$PROJECT_REPO/results/phase2_3_repo_evaluation"
MEDIUM_TEST_FILE="$PROJECT_REPO/results/phase2_medium_test/seqs_wo_guidance_top_p=0.95_2_16_medium_test_seed42_steps50_batch16.txt"
RAW_DIR="$PROJECT_REPO/results/phase4_1_unadapted_rnagenesis_30k/raw"

source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate rnagenesis-h200

cd "$PROJECT_REPO"

run_eval() {
  local candidate_file="$1"
  local run_label="$2"
  shift 2

  python scripts/run_repo_aptamer_evaluation.py \
    --candidate-file "$candidate_file" \
    --rnagenesis-repo "$RNAGENESIS_REPO" \
    --output-dir "$OUTPUT_DIR" \
    --run-label "$run_label" \
    "$@"
}

echo "=== Stage 2.3 repo aptamer evaluation: medium test (16 sequences) ==="
run_eval "$MEDIUM_TEST_FILE" "medium_test_16" --write-per-sequence

echo
echo "=== Stage 2.3 repo aptamer evaluation: baseline 30k chunk 1 ==="
CHUNK1_FILE="$(find "$RAW_DIR" -maxdepth 1 -type f -name '*chunk1*' | sort | head -n 1)"
if [[ -z "$CHUNK1_FILE" ]]; then
  echo "ERROR: chunk1 file not found under $RAW_DIR" >&2
  exit 1
fi
run_eval "$CHUNK1_FILE" "baseline_30k_chunk1"

if [[ "${RUN_FULL:-0}" == "1" ]]; then
  echo
  echo "=== Stage 2.3 repo aptamer evaluation: full 30,080 merged file ==="
  MERGED_FILE="$OUTPUT_DIR/inputs/merged_30080_raw.txt"
  mkdir -p "$OUTPUT_DIR/inputs"

  : > "$MERGED_FILE"
  for chunk in $(seq 1 10); do
    chunk_file="$(find "$RAW_DIR" -maxdepth 1 -type f -name "*chunk${chunk}_*" | sort | head -n 1)"
    if [[ -z "$chunk_file" ]]; then
      echo "ERROR: chunk${chunk} file not found under $RAW_DIR" >&2
      exit 1
    fi
    cat "$chunk_file" >> "$MERGED_FILE"
  done

  line_count="$(wc -l < "$MERGED_FILE" | tr -d ' ')"
  if [[ "$line_count" != "30080" ]]; then
    echo "ERROR: merged file line count is $line_count, expected 30080" >&2
    exit 1
  fi

  run_eval "$MERGED_FILE" "baseline_30080_full"
else
  echo
  echo "Skipping full 30,080 evaluation (set RUN_FULL=1 to enable)."
fi

echo
echo "Done. Outputs under $OUTPUT_DIR"
