# RNAGenesis Checkpoint Download Plan (Phase 1.5)

## Required assets (Zenodo)
- checkpoints.zip
- configs.zip
- progen2-base.zip
- progen2-small.zip

Source:
https://zenodo.org/records/15203813

## Expected directory structure

checkpoints/
configs/
models/autoencoder/decoder/checkpoints/progen2-base/
models/autoencoder/decoder/checkpoints/progen2-small/

## Known issues
- README typo: "confiigs/" should be "configs/"
- README refers to generate.py, but repo uses generation.py

## Key runtime paths
- --enc_dec_file → configs/rnagenesis/autoencoder
- --dm_file → checkpoints/Aptamer/diffusion

## Strategy
- Download directly on H200 (avoid transferring large files)
- Verify extracted paths before running anything
- Log all commands, file names, and structure

## Open questions
- Exact contents of configs.zip
- Correct decoder_config argument
- Minimal working generation command

## Server storage policy alignment

- Datasets → /Datasets (if used)
- Model checkpoints and configs → ~/RNAGenesis/
- Code and environments → home directory (~)

~/RNAGenesis/              # code
~/rnagenesis-aptamer-mres/ # your project repo
~/envs/                    # conda envs (optional)
~/checkpoints/             # model weights (optional)

Decision:
- Zenodo model weights treated as model artifacts, not datasets.
- Will not store large files in /Datasets unless explicitly required.