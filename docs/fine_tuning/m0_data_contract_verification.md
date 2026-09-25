# M0 data contract verification — 25 September 2026

**Local data-contract checkpoint: PASS. Full M0: incomplete.** No curation,
optimisation, generation, model evaluation, remote connection or GPU use was
performed. The two AptaRank planning documents remain outside this change.

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

## Remaining M0 work

1. Review this contract together with the eventual trainer integration. The
   current validator is not wired into an upstream trainer; future entry points
   must verify the contract and their actual input files before creating an
   optimizer. They must use TRAIN text for fitting and unique VALIDATION cores
   for development evaluation, bypassing the upstream automatic split.
2. Prepare a dedicated H200 data directory containing only `ft_train.csv`,
   `corpus_final.txt`, and `ft_validation.csv`, using direct secure transfer.
   Transfer neither the combined corpus nor REF/EVAL/interim curation data.
   Keep sequence files outside Git. With the closure present in the H200
   repository, run the same validator there with `--profile development` and
   `--data-dir` pointing to that dedicated directory. This profile checks the
   entire directory entry allowlist before opening any inputs.
3. Separately document that REF/EVAL are absent or inaccessible throughout the
   actual H200 training workspace and loader search paths. A successful
   directory check is not proof of isolation across an entire host.
4. Complete the model asset and environment manifests, exact denoiser parameter
   count, diffusers compatibility-patch verification and trainer integration
   review required by the plan's M0 human gate.

No optimiser run on biological data is authorised by a local contract PASS.
No VALIDATION text view or derived corpus was created in this step. GPU1 is
authorised for this session on 25 September 2026 but was not used; that is a
session-level permission, not a permanent change to the data contract or GPU0
default. GPU execution remains unnecessary for this checkpoint.
