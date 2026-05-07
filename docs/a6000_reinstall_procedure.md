# A6000 reinstall procedure — RNAGenesis Aim 1

This note records how to recreate the A6000 RNAGenesis setup after the server upgrade/format.

## 1. Clone repositories

```bash
cd ~

git clone git@github.com:laura-hardy/rnagenesis-aptamer-mres.git ~/rnagenesis-aptamer-mres
git clone git@github.com:laura-hardy/RNAGenesis.git ~/RNAGenesis
RNAGenesis commit used during Phase 1/2 reproduction:

d00899e (HEAD -> main, origin/main, origin/HEAD) Update README.md

Check with:

cd ~/RNAGenesis
git log --oneline -1
2. Create conda environment

Use the existing system Anaconda if available:

source /opt/anaconda3/etc/profile.d/conda.sh
mkdir -p ~/.conda/pkgs ~/.conda/envs
conda config --add pkgs_dirs ~/.conda/pkgs
conda config --add envs_dirs ~/.conda/envs

conda create -p ~/.conda/envs/rnagenesis-a6000 python=3.8.13 -y
conda activate /home/laura/.conda/envs/rnagenesis-a6000
3. Install core dependencies
pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cu121

pip install "numpy<2" biopython transformers==4.36.2 diffusers==0.25.0 huggingface-hub==0.20.3 pytorch-lightning viennarna sentencepiece einops timm torchinfo tqdm
pip install rna-fm
pip install omegaconf==2.3.0
pip install accelerate==0.25.0

Verify:

python - <<'PY'
import torch, numpy, transformers, diffusers, huggingface_hub, RNA, Bio, fm, omegaconf, accelerate
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("gpu:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none")
print("numpy:", numpy.__version__)
print("transformers:", transformers.__version__)
print("diffusers:", diffusers.__version__)
print("huggingface_hub:", huggingface_hub.__version__)
print("imports OK")
PY
4. Apply RNAGenesis compatibility patch to diffusers

The successful Phase 2 runs required a local patch to diffusers==0.25.0.

Original error:

ValueError: not enough values to unpack (expected 2, got 1)

Location:

/home/laura/.conda/envs/rnagenesis-a6000/lib/python3.8/site-packages/diffusers/models/normalization.py

Patch:

NORM_FILE=$(python - <<'PY'
import diffusers.models.normalization as normalization
print(normalization.__file__)
PY
)

cp "$NORM_FILE" "${NORM_FILE}.bak_rnagenesis"

python - <<'PY'
from pathlib import Path
import diffusers.models.normalization as normalization

path = Path(normalization.__file__)
text = path.read_text()

old = "scale, shift = torch.chunk(emb, 2)"
new = "scale, shift = torch.chunk(emb, 2, dim=-1)  # RNAGenesis compatibility patch"

if old not in text and new not in text:
    raise SystemExit(f"Expected line not found in {path}")

if old in text:
    path.write_text(text.replace(old, new))

print(f"Patched or already patched: {path}")
PY

grep -n "scale, shift = torch.chunk" "$NORM_FILE"

Expected patched line:

scale, shift = torch.chunk(emb, 2, dim=-1)  # RNAGenesis compatibility patch
5. Download RNAGenesis Zenodo assets

From ~/RNAGenesis:

cd ~/RNAGenesis

wget -c -O checkpoints.zip "https://zenodo.org/records/15203813/files/checkpoints.zip?download=1"
wget -c -O configs.zip "https://zenodo.org/records/15203813/files/configs.zip?download=1"
wget -c -O progen2-base.zip "https://zenodo.org/records/15203813/files/progen2-base.zip?download=1"
wget -c -O progen2-small.zip "https://zenodo.org/records/15203813/files/progen2-small.zip?download=1"

Previous download sizes and time:

Total download time: approximately 8 hours
checkpoints.zip: 14G
configs.zip: 15G
progen2-base.zip: 1.4G
progen2-small.zip: 536M
6. Extract assets
cd ~/RNAGenesis

mkdir -p checkpoints configs
mkdir -p models/autoencoder/decoder/checkpoints/progen2-base
mkdir -p models/autoencoder/decoder/checkpoints/progen2-small

unzip checkpoints.zip -d checkpoints/
unzip configs.zip -d configs/
unzip progen2-base.zip -d models/autoencoder/decoder/checkpoints/progen2-base/
unzip progen2-small.zip -d models/autoencoder/decoder/checkpoints/progen2-small/

If extraction creates nested folders, flatten them:

chmod -R u+rwX checkpoints configs models/autoencoder/decoder/checkpoints

mv checkpoints/checkpoints/* checkpoints/ 2>/dev/null || true
rmdir checkpoints/checkpoints 2>/dev/null || true

mv configs/configs/* configs/ 2>/dev/null || true
rmdir configs/configs 2>/dev/null || true

mv models/autoencoder/decoder/checkpoints/progen2-base/progen2-base/* \
   models/autoencoder/decoder/checkpoints/progen2-base/ 2>/dev/null || true
rmdir models/autoencoder/decoder/checkpoints/progen2-base/progen2-base 2>/dev/null || true

mv models/autoencoder/decoder/checkpoints/progen2-small/progen2-small/* \
   models/autoencoder/decoder/checkpoints/progen2-small/ 2>/dev/null || true
rmdir models/autoencoder/decoder/checkpoints/progen2-small/progen2-small 2>/dev/null || true

Verify:

ls -la configs/rnagenesis/autoencoder
ls -la checkpoints/Aptamer/diffusion
ls -la models/autoencoder/decoder/checkpoints/progen2-base | head
ls -la models/autoencoder/decoder/checkpoints/progen2-small | head
7. Re-run known working tests

Tiny test:

cd ~/rnagenesis-aptamer-mres
bash scripts/run_rnagenesis_aptamer_tiny_test.sh

Small test:

bash scripts/run_rnagenesis_aptamer_small_test.sh

Medium test:

bash scripts/run_rnagenesis_aptamer_medium_test.sh
Current next work item

Next task after reinstall:

Write a cleaning/summary script for generated RNAGenesis aptamer sequences.

The script should:

read generated sequence .txt files;
remove the leading 11 decoder/BOS-style prefix if justified;
check alphabet validity: A/C/G/U only;
report raw length and cleaned length;
count duplicates;
write cleaned CSV and FASTA files for downstream evaluation.

