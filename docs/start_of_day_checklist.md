````markdown
# A6000 Day-Start Checklist — RNAGenesis Aim 1

Use this checklist at the start of each server work session.

---

## 1. Connect to VPN

Before SSH, make sure the university VPN is connected if required.

---

## 2. SSH into the A6000 server

From a local Mac terminal:

```bash
ssh laura@warpgolem
````

Confirm you are on the server:

```bash
hostname
pwd
whoami
```

Expected:

```text
warpgolem
/home/laura
laura
```

---

## 3. Check GPU status

Run:

```bash
nvidia-smi
```

Check:

* GPU is visible.
* GPU is not heavily occupied by another user/process.
* Available memory is sufficient before running RNAGenesis.

Expected GPU:

```text
NVIDIA RTX 6000 Ada Generation
```

---

## 4. Activate the RNAGenesis conda environment

If the environment is not already active:

```bash
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate /home/laura/.conda/envs/rnagenesis-a6000
```

Confirm the prompt shows:

```text
(rnagenesis-a6000)
```

---

## 5. Verify Python, PyTorch and CUDA

Run:

```bash
which python
python --version

python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))
PY
```

Expected:

```text
/home/laura/.conda/envs/rnagenesis-a6000/bin/python
Python 3.8.13
torch: 2.1.2+cu121
cuda available: True
gpu: NVIDIA RTX 6000 Ada Generation
```

---

## 6. Update the project repo from GitHub

Go to the project repo:

```bash
cd ~/rnagenesis-aptamer-mres
git status
```

If the working tree is clean:

```bash
git pull
```

If `git status` shows local changes, do **not** pull yet. First inspect:

```bash
git status
git diff
```

Then decide whether to commit, stash, or discard the local changes.

---

## 7. Check the RNAGenesis repo

Go to the RNAGenesis repo:

```bash
cd ~/RNAGenesis
git status
git log --oneline -1
```

Expected current commit:

```text
d00899e ... Update README.md
```

If you have intentionally modified RNAGenesis code, make sure those changes are committed and pushed to your fork before the server upgrade.

---

## 8. Confirm checkpoint/config paths

Run:

```bash
cd ~/RNAGenesis

ls -la configs/rnagenesis/autoencoder
ls -la checkpoints/Aptamer/diffusion
ls -la models/autoencoder/decoder/checkpoints/progen2-base | head
ls -la models/autoencoder/decoder/checkpoints/progen2-small | head
```

Expected paths:

```text
configs/rnagenesis/autoencoder
checkpoints/Aptamer/diffusion
models/autoencoder/decoder/checkpoints/progen2-base
models/autoencoder/decoder/checkpoints/progen2-small
```

---

## 9. Check storage

Because the server is shared and scheduled for upgrade/formatting, check disk usage regularly:

```bash
df -h .
du -sh ~/RNAGenesis
du -sh ~/rnagenesis-aptamer-mres
du -sh ~/.conda
```

---

## 10. If using tmux

List existing tmux sessions:

```bash
tmux ls
```

Attach to a session:

```bash
tmux attach -t rnagenesis-downloads
```

Detach without stopping the process:

```text
Ctrl-b then d
```

Start a new tmux session if running a long job:

```bash
tmux new -s rnagenesis-run
```

---

## 11. Before starting work

Make a short plan in the log or notes:

```bash
cd ~/rnagenesis-aptamer-mres
date
git status
```

Then continue with the next step.



```
```
