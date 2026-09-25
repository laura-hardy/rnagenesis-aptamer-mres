# M0 data contract verification — 25 September 2026

**Local data-contract checkpoint: PASS. M0: COMPLETE / GO — 25 September 2026.**
The local checkpoint below is unchanged. The H200 development preflight in
the closure section passed, and the human-gate recommendation is GO. M0
completion does not mean biological fine-tuning has run: the final preflight
took no optimizer step and performed no generation. The next milestone is
M1, released-behaviour and numerical training smoke validation, before the
substantive D1 fitting run.

## Frozen authority

- Corpus closure: `10aac629bb0ef0337107c3d628b23e1897962af9`.
- Repository HEAD during verification: `0e5c7d3` (merge retaining the closure).
- Contract: `config/modelling/frozen_data_contract.json`.
- Pinned S7D metadata: `config/global_s7d_final_build.json` at the closure;
  SHA256 `abd3e1b29f422848aabd309ab0bb985731b9fb3941ddfbd2ec0f43d31a98b475`.
- Existing local corpus manifest: SHA256
  `08da8d5e44413ea9ab57c128dbe4ef7986dab7a2bfa794cfef6fb4724577565f`,
  verified without rerunning its build. The pre-closure S7D baseline
  `5afc24147fdc9b40a3d563cf68430da867ea6aa1` is not the corpus closure.

The prior fine-tuning plan SHA256 was
`561de30294ab23696682284e11f2d40dd9e07779c50574f5a1e603af679a4a28`.
This change names the exact closure, corrects the lingering TRAIN length-regime
summary (382/296 to 386/283), and links the contract and validator. It changes
no corpus file, split, clustering decision or curation configuration.

## Verified local inputs and boundaries

| Artifact | SHA256 | Verification in this M0 step |
| --- | --- | --- |
| TRAIN CSV | `84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0` | Bytes, counts, role labels, alphabet, identity/cluster freeze hashes |
| TRAIN text | `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d` | Bytes; 669 unique lines equal TRAIN cores in frozen first-occurrence order |
| VALIDATION CSV | `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd` | Bytes, counts, role labels, alphabet, identity/cluster freeze hashes |
| REF CSV | `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23` | Hash recorded from closure metadata; file not opened or rehashed |
| EVAL CSV | `ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015` | Hash recorded from closure metadata; file not opened or rehashed |

TRAIN: 726 identities, 669 cores, 569 clusters, 320 targets. VALIDATION:
132 identities, 95 cores, 63 clusters, 100 targets. Every TRAIN/VALIDATION
core is nonempty canonical A/C/G/U. There is zero core, cluster or scientific
identity overlap between TRAIN and VALIDATION. All-four-role leakage checks
remain the evidence established at the corrected S7D closure; this M0 step
does not reopen REF/EVAL to recompute them.

RNAGenesis fitting uses only `corpus_final.txt`, one instance per unique TRAIN
core, not 726 identity rows. VALIDATION is only for model development and
checkpoint selection, never fitting. REF is only for AptaRank calibration after
generator freeze. EVAL remains locked until the M9C complete pipeline freeze
and explicit unlock record. No silent T-to-U conversion, whitespace trimming,
case conversion, new length filter, random resplit or role merging is allowed.

Length summaries measured at distinct-core grain:

| Role | Minimum | Maximum | Median | Mean | Frozen short / long counts |
| --- | ---: | ---: | ---: | ---: | ---: |
| TRAIN | 20 | 123 | 50 | 55.35276532137519 | 386 / 283 |
| VALIDATION | 20 | 94 | 49 | 54.72631578947368 | 55 / 40 |

The short/long counts come from the frozen S7D metadata; no GMM was refit. The
validator emits the full empirical length histograms. Compatibility with the
released tokenizer/model range remains a later check; these lengths do not
by themselves establish model support.

## Repeat the local check

From the repository root:

```bash
python3 scripts/modelling/verify_modelling_contract.py --profile local-corpus
python3 -m unittest discover -s tests/modelling -v
```

Both use only the Python standard library. The verifier checks closure ancestry,
the pinned metadata bytes, the complete contract and only TRAIN/VALIDATION
inputs. It returns nonzero on failure and never repairs inputs. Its output
contains aggregate metadata, not sequence strings. The 12 synthetic tests cover
role/purpose rejection before reads, changed input bytes, symlinks, extra files
in a development input directory, invalid alphabets, wrong role labels,
duplicate/reordered training lines, semantic overlap and duplicate JSON keys.

The Mac's `data/processed` is the curation store and contains held-out files.
The `local-corpus` profile is appropriate here and makes no claim that this is
an isolated training workspace. Do not transfer this directory wholesale.

No optimiser run on biological data was authorised by the local contract PASS.
No VALIDATION text view or derived corpus was created in that local step. GPU1
was authorised for the 25 September 2026 session and was not used for the local
checkpoint; that is a session-level permission, not a permanent change to the
data contract or GPU0 default.

## M0 closure — 25 September 2026

**Status: COMPLETE / GO.** The human gate confirms that the imported trainer
and this data contract match the implementation plan. M0 completion records
that boundary. It does not mean biological fine-tuning has run.

MRes source commit before this documentation closure:
`4d8730f4eb82f7066c2d8d107b97240897687021`.

RNAGenesis branch `mres-d1-diffusion-finetune`:

| Commit | Subject |
| --- | --- |
| `29619df` | Restore biomap latent encoding path |
| `81418f9` | Document biomap upstream attribution |
| `789ecc2` | Add MRes D1 diffusion trainer |
| `e20f556` | Correct denoiser parameter accounting |

Final clean real-data preflight, RNAGenesis
`e20f5567526a6d76a173eba87e363e8edf130cd6`. Output directory
`/home/laura/rnagenesis-mres-runs/m0_preflight_e20f556_clean`, outside the
protected development input directory. `preflight = true`. `fixture = false`.
`working_tree_dirty = false` after the rerun with
`PYTHONDONTWRITEBYTECODE=1`.

The development contract verifier passed before that preflight:

```text
input_directory_isolation = PASS
restricted_role_files_opened = []
contract SHA256 = 396c83c3dbf9afc656ad5c60ec05c94fce3c5a684990c3cc1cebfb2411ccd5ff
```

Development inputs opened by the preflight:

| Role | Path | SHA256 | Count |
| --- | --- | --- | --- |
| TRAIN | `/home/laura/rnagenesis-mres-data/development/corpus_final.txt` | `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d` | 669 examples |
| VALIDATION | `/home/laura/rnagenesis-mres-data/development/ft_validation.csv` | `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd` | 95 unique sequence cores |

These hashes match the local TRAIN text and VALIDATION CSV hashes above.
No REF or EVAL file was accessed.

Model boundary:

```text
B1 = configs/rnagenesis/diffusion
EncDec = configs/rnagenesis/autoencoder
EncDec frozen = true
denoiser parameter count = 1,911,589,344
trainable parameter count = 1,911,589,344
registered buffer elements = 50,331,648
serialized state elements = 1,961,920,992
EMA = false
```

The first preflight correctly failed on the old parameter-accounting
assertion, before optimizer construction. That assertion treated the
1,961,920,992 serialized state elements as the denoiser parameter count.
Forensic inspection established that the 50,331,648-element difference
comprises 24 registered `transformer_blocks.0`–`23.pos_embed.pe` buffers.
RNAGenesis `e20f556` corrected the accounting. The clean corrected preflight
then passed. `1,911,589,344 + 50,331,648 = 1,961,920,992`.

Training configuration observed, with no optimizer step:

```text
microbatch = 8
gradient accumulation = 4
effective batch = 32
dataloader batches/epoch = 84
optimizer updates/epoch = 21
epochs maximum = 5
total optimizer updates maximum = 105
warmup updates = 10
learning rate = 3e-5
optimizer = AdamW
beta1 = 0.95
beta2 = 0.999
epsilon = 1e-8
weight decay = 1e-6
scheduler = cosine
gradient clip = 1.0
mixed_precision = no
```

Seeds and fixed VALIDATION draws:

```text
TRAIN/DataLoader/diffusion seed = 42
fixed VALIDATION seed = 1
validation draws per sequence = 1
validation sequence SHA256 = b23647f40bb8fccee463009a5562411eceabe8070b953dfe0dcd59e10d8dc088
validation timestep SHA256 = aa20a66ed2c91351b667baf726f011d3522a9bb2e569046db5041e0242bfe080
validation noise SHA256 = 248a65d462be827afe313523b3dd8481394ae0d627633c56bbe965037d84b410
```

Boundary of the passing preflight: no optimizer step, no generation, no
REF/EVAL access, and output outside the protected development input directory.

The model-asset manifest, environment manifest and biomap reconstruction
decision remain the M0 inventories. The diffusers patch verification stays
the record in the environment manifest; this preflight did not re-measure
that file. Residual uncertainty about the missing historical `get_latent`
is unchanged.

**Next milestone:** M1, released-behaviour and numerical training smoke
validation, before the substantive D1 fitting run.
