# M1 released-inference validation — 28 September 2026

**Status: COMPLETE / GO — 28 September 2026.**

The human gate is GO. It accepts this formal released-inference result
and closes formal M1 on 28 September 2026. The rationale is the recorded
tiny technical regression: released and current raw outputs are
byte-identical for B0 and for B1, cleaning accepted A/C/G/U sequences
only, and no fine-tuning or model selection occurred. The same decision
keeps numerical diffusion-training smoke as formal M5, after M2–M4.
This closure does not authorise fine-tuning, model selection, or a
biological reading of the generated sequences. It is not
production-generation validation and it is not evidence of training
correctness.

Evidence file, read and hashed before this document was written:

```text
/home/laura/rnagenesis-mres-runs/m1_inference_e20f556/m1_released_inference_evidence.json
SHA-256 ec518b3f8f78de19227abe5a14e138bcf381c231bc888689a298a16c946ee774
```

Every hash, count, path and commit below is taken from that file unless a
section says otherwise. The unit-test tallies are the exception, and that
exception is stated where they appear.

## Objective and formal authority

Formal M1, in the implementation plan, is “Reproduce released inference
behavior.” Its objective is to ensure code integration does not alter
known-working inference. The inputs are the released `EncDec`, the B0
checkpoint, the B1 generic checkpoint and the existing cleaning code. The
human gate is “Accept inference regression.”

The evidence `scope.purpose` is `formal M1 released-inference regression`.
Its extent is: “Tiny technical regression only, not production generation
or biological evaluation.”

This execution covers that formal released-inference section. It does not
cover formal M5. The scope decision is recorded in
[Resolved scope decision](#resolved-scope-decision). The formal milestone
definitions and ordering govern. Milestone order and experimental design
are unchanged.

## Version provenance

| Role | Commit | Subject |
| --- | --- | --- |
| Authoritative MRes repository `/home/laura/rnagenesis-aptamer-mres` | `6bb2aa8564d3493c598122545c0baa640b29bfe4` | Close M0 fine-tuning preflight gate |
| Current RNAGenesis HEAD during evidence assembly, branch `mres-d1-diffusion-finetune` | `112a120282667c382790031fe74942f89f7b84eb` | Add M1 generation output audit |
| Current-lineage generation code | `e20f5567526a6d76a173eba87e363e8edf130cd6` | Correct denoiser parameter accounting |
| Released RNAGenesis baseline, worktree `/home/laura/rnagenesis-mres-worktrees/released-d00899e-m1` | `d00899eef60d664cc7b5880c0bb43f2a9e7a1b01` | Update README.md |
| Audit utility | `112a120282667c382790031fe74942f89f7b84eb` | Add M1 generation output audit |

`112a120282667c382790031fe74942f89f7b84eb` is both the current RNAGenesis
HEAD named by the evidence and the audit-utility commit. Generation on the
current lineage used `e20f5567526a6d76a173eba87e363e8edf130cd6`. The only
commits between those two RNAGenesis revisions are the audit-utility commit
itself. Its diff adds `scripts/audit_generation_output.py` and
`tests/test_audit_generation_output.py` and no other path. That diff check
is a read of the named commits; it is not a field inside the evidence JSON.

Current-lineage runs used worktree `/home/laura/RNAGenesis`. Released-lineage
runs used `/home/laura/rnagenesis-mres-worktrees/released-d00899e-m1`.

## Environment and authorised GPU provenance

```text
python = 3.8.13 (default, Oct 21 2022, 23:50:54)  [GCC 11.2.0]
python executable = /home/laura/miniconda3/envs/rnagenesis-h200/bin/python
CUDA_VISIBLE_DEVICES = 1
HF_HUB_OFFLINE = 1
TRANSFORMERS_OFFLINE = 1
PYTHONDONTWRITEBYTECODE = 1 for every run except b0_current_run1, where the variable was absent
```

| Package | Version |
| --- | --- |
| torch | 2.1.2+cu121 |
| transformers | 4.36.2 |
| diffusers | 0.25.0 |
| accelerate | 0.25.0 |
| huggingface-hub | 0.20.3 |
| numpy | 1.22.0 |
| omegaconf | 2.3.0 |
| safetensors | 0.5.3 |
| tqdm | 4.68.2 |

Recorded GPU for every run:

```text
name = NVIDIA H200 NVL
physical index = 1
logical device = cuda:0
UUID = GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f
```

`CUDA_VISIBLE_DEVICES=1` made that physical GPU appear as `cuda:0`. This is
the device provenance stored in the evidence. It does not change the plan’s
standing GPU0 default for later sessions.

## Data and training boundary

The evidence states both of the following, and the corresponding flags are
true or false as written:

```text
sequence_access = No TRAIN, VALIDATION, REF or EVAL sequence was accessed.
training_statement = No backward pass, optimizer step, fine-tuning or model selection occurred.
no_backward_pass = true
no_optimizer_step = true
no_fine_tuning = true
model_selection_occurred = false
```

TRAIN, VALIDATION, REF and EVAL sequences were not accessed. No backward
pass, optimizer step, fine-tuning or model selection occurred.

## B0 and B1 checkpoint identity

| Asset | Path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| B0 denoiser weights | `/home/laura/RNAGenesis/checkpoints/Aptamer/diffusion/unet/diffusion_pytorch_model.safetensors` | 7847725416 | `149f012287b1ae83865c25867d7c0bbe0952fa51bcc068e259725092d5dff0ca` |
| B0 denoiser config | `/home/laura/RNAGenesis/checkpoints/Aptamer/diffusion/unet/config.json` | 549 | `fab9c517efba8269c0edf194b7d0379f317e93da0f849b5ce815e098088b4756` |
| B0 model index | `/home/laura/RNAGenesis/checkpoints/Aptamer/diffusion/model_index.json` | 217 | `05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e` |
| B0 scheduler | `/home/laura/RNAGenesis/checkpoints/Aptamer/diffusion/scheduler/scheduler_config.json` | 492 | `6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396` |
| B1 denoiser weights | `/home/laura/RNAGenesis/configs/rnagenesis/diffusion/unet/diffusion_pytorch_model.safetensors` | 7847725416 | `c268021b6cab37423e3bffd495b139bb69698d8d11c7b96477fbfb239b0cff26` |
| B1 denoiser config | `/home/laura/RNAGenesis/configs/rnagenesis/diffusion/unet/config.json` | 531 | `3a9975ff165bbd5ca82923e6ed1c5ed7eb383a23f4f3f55db713c995031f8ee3` |
| B1 model index | `/home/laura/RNAGenesis/configs/rnagenesis/diffusion/model_index.json` | 217 | `05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e` |
| B1 scheduler | `/home/laura/RNAGenesis/configs/rnagenesis/diffusion/scheduler/scheduler_config.json` | 492 | `6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396` |

Checkpoint directories:

```text
B0 = /home/laura/RNAGenesis/checkpoints/Aptamer/diffusion
B1 = /home/laura/RNAGenesis/configs/rnagenesis/diffusion
```

Identity conclusion: B0 and B1 are distinct diffusion checkpoints.
`b0_b1_weights_distinct` is PASS. The denoiser weights differ, and the
denoiser configs differ. `model_index.json` is byte-identical across the
two directories, and `scheduler_config.json` is byte-identical across the
two directories. The same byte length of the two weight files does not make
them the same checkpoint.

Additional assets in the evidence provenance. Every run passed the same
`--enc_dec_file` directory and the same `--decoder_config` name:

| Asset | Path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Parent EncDec weights | `/home/laura/RNAGenesis/configs/rnagenesis/autoencoder/pytorch_model.bin` | 3476049782 | `3c4e34f7626c94416d504c16569b5f3f785fffe77889b9886344477b95e74c68` |
| Parent EncDec config | `/home/laura/RNAGenesis/configs/rnagenesis/autoencoder/config.json` | 530 | `ab309231b75405af3e2ef6fe49e4e74c1b96021ef2a4f61b46e5796b8799378a` |
| Biomap config | `/home/laura/RNAGenesis/models/autoencoder/encoder/biomap/config.json` | 1369 | `bf7ef6843232f370f3f7fc37d608f85cb0ff0d75291eed35cef52213e34978f7` |
| Decoder config | `/home/laura/RNAGenesis/models/autoencoder/decoder/progen_configs/config-progen2-small-rna_tokenizer_v2.json` | 915 | `42f15517e05ce96d78337fbc1bf20ffc580424fe88cbfcb2c81550b17cc7283e` |
| Decoder tokenizer | `/home/laura/RNAGenesis/models/autoencoder/decoder/progen_configs/tokenizer_rna_v2.json` | 1317 | `6d8a20879cec3544cf0f33b0d481fbd5ead6a2bead2dbf1649449172c8336921` |

`b0_b1_tiny_outputs_distinct` is PASS. The B0 raw SHA-256 and the B1 raw
SHA-256 differ. That difference is two sequences per condition from a
five-step smoke. B0/B1 output differences from two sequences are not
biological evidence.

## Tiny-regression settings

These settings are a technical smoke. The evidence extent says this was a
tiny technical regression, not production generation and not biological
evaluation. Five DDIM steps and two sequences per condition cannot support
a distributional or biological claim. `max_seq_len` 37 is the generation
argument; it is not the observed raw or cleaned length reported below.

Common arguments on every run:

```text
enc_dec_file = /home/laura/RNAGenesis/configs/rnagenesis/autoencoder
decoder_config = config-progen2-small-rna_tokenizer_v2
num_inference_steps = 5
batch_size = 2
batch_num = 1
seed = 42
eta = 0.0
max_seq_len = 37
do_sample = present
top_p = 0.95
top_k = 0
bos_token = 1
eos_token = 2
device = cuda:0
target_class = 0
guidance_scale = 1.0
classifier_loss_type = l2
recurrence_step = 1
guidance_start_step = 0
guidance_stop_step = 5
search_goal = similarity
active_size = 1
branch_size = 8
guidance_classifier_model_config = /home/laura/RNAGenesis/configs/rnagenesis/classifier/mlp_160_32.yaml
superfolder = /home/laura/rnagenesis-mres-runs/m1_inference_e20f556
```

The guidance and search arguments above were present and inert. These
enabling flags were absent:

```text
--extend_input
--guidance
--multiple_eos_tokens
--save_latent_space
--search_general
--tree_search
--truncate
--update_seq
```

Per-run differences were only `--dm_file`, `--mid_folder` and `--remark`.
B0 used `/home/laura/RNAGenesis/checkpoints/Aptamer/diffusion`. B1 used
`/home/laura/RNAGenesis/configs/rnagenesis/diffusion`.

## Six-run design

| Run | Lineage | Condition | Code commit | Worktree | `PYTHONDONTWRITEBYTECODE` |
| --- | --- | --- | --- | --- | --- |
| `b0_current_run1` | current | B0 | `e20f5567526a6d76a173eba87e363e8edf130cd6` | `/home/laura/RNAGenesis` | absent |
| `b0_current_run2` | current | B0 | `e20f5567526a6d76a173eba87e363e8edf130cd6` | `/home/laura/RNAGenesis` | `1` |
| `b0_release_d00899e_run1` | released | B0 | `d00899eef60d664cc7b5880c0bb43f2a9e7a1b01` | `/home/laura/rnagenesis-mres-worktrees/released-d00899e-m1` | `1` |
| `b1_current_run1` | current | B1 | `e20f5567526a6d76a173eba87e363e8edf130cd6` | `/home/laura/RNAGenesis` | `1` |
| `b1_current_run2` | current | B1 | `e20f5567526a6d76a173eba87e363e8edf130cd6` | `/home/laura/RNAGenesis` | `1` |
| `b1_release_d00899e_run1` | released | B1 | `d00899eef60d664cc7b5880c0bb43f2a9e7a1b01` | `/home/laura/rnagenesis-mres-worktrees/released-d00899e-m1` | `1` |

Each run wrote two sequences. Each run’s audit counts were `input_count` 2,
`accepted_count` 2, `modified_accepted_count` 2, `unchanged_accepted_count`
0 and `rejected_count` 0.

## B0 and B1 repeatability

| Comparison | Result | Shared raw SHA-256 |
| --- | --- | --- |
| `b0_current_run1_versus_run2` | PASS | `407ed27564fdc200f190ff78eddae04466dd4ba3e7d4a0c30c5af64e8a91f25d` |
| `b1_current_run1_versus_run2` | PASS | `b5bf57a8977476e05119d380aeefa7a407daec002ecefad9ea747c1dd3ef835d` |

Within B0, the current repeat also matches the released run on raw, cleaned
and row-manifest bytes. Within B1, the same is true. Those cross-lineage
identities are the next section. Repeatability here is the current-lineage
pair for each checkpoint.

## Current versus released

| Comparison | Result | Shared raw SHA-256 |
| --- | --- | --- |
| `current_versus_released_b0` | PASS | `407ed27564fdc200f190ff78eddae04466dd4ba3e7d4a0c30c5af64e8a91f25d` |
| `current_versus_released_b1` | PASS | `b5bf57a8977476e05119d380aeefa7a407daec002ecefad9ea747c1dd3ef835d` |

Released and current B0 raw outputs are byte-identical. Released and current
B1 raw outputs are byte-identical. Cleaned files and row manifests are
likewise byte-identical within each condition, including the released run.
B0 and B1 remain distinct from each other. That two-sequence difference is
not biological evidence.

## Raw, cleaned and row-manifest hashes

B0, all three runs. Raw files are 78 bytes. Cleaned files are 74 bytes.
Row manifests are 337 bytes.

| Artifact | SHA-256 |
| --- | --- |
| Raw | `407ed27564fdc200f190ff78eddae04466dd4ba3e7d4a0c30c5af64e8a91f25d` |
| Cleaned | `2ad84c80d87042e6f70f9f8e18f2c8fca16822808ef2253a71aecedd95aa8ee2` |
| Row manifest | `7f809cafb00e1282119c96943b7d9447addd7b9208638620600d0178f8f082ca` |

B1, all three runs. The same byte lengths apply.

| Artifact | SHA-256 |
| --- | --- |
| Raw | `b5bf57a8977476e05119d380aeefa7a407daec002ecefad9ea747c1dd3ef835d` |
| Cleaned | `2ac348fad712b36dd264bdaa950c0698cb31889f3a42646327945fd84cbb600b` |
| Row manifest | `97694aae3c6623163348f83784a9fe900cf8a1ccaaf160a8096808424a920c1d` |

`raw_hashes_unchanged_by_cleaning` is PASS for all six runs. Cleaning wrote
new files. It did not rewrite the raw generation files.

Audit-summary JSON hashes differ across runs because each summary embeds
its own absolute paths. They are not a failed identity check:

| Run | Audit-summary SHA-256 |
| --- | --- |
| `b0_current_run1` | `ac7410eabb3bb8a20e52e90f22ccd421f40216faa96ac1fbcf42b830a80255f4` |
| `b0_current_run2` | `43517944675111f5926cc73946892e7864c939e28398b0430ff0e886a8c642eb` |
| `b0_release_d00899e_run1` | `77363c980477aa8d96d8774b10a32c7254acb509660e337b40c87871822f9f9f` |
| `b1_current_run1` | `dfd90195d53bb79958e7a7a5b2cc0b7607e8c187233bc50f7345ad5171b5b80e` |
| `b1_current_run2` | `1a1142e5b4d1c833f5e3fbbf81ebf245200df71cf3649a97cf8e41819e61ac2f` |
| `b1_release_d00899e_run1` | `c86001ece12aba07d35e4de5ce83eb1d8b808c4b911ab8f4d74e4947fc3fd429` |

## Observed boundary markers and the approved cleaning rule

The approved cleaning rule is boundary-only. It is the rule implemented by
the audit utility at `112a120282667c382790031fe74942f89f7b84eb`. Newline
delimiters separate records and are not sequence characters. A trailing
newline does not add a record. Each record then loses its leading run of
`1` and `2`, and any trailing run of `1` and `2` that remains after that.
Characters in the middle stay as they are. The cleaned body is accepted
only when it is nonempty and every character is A, C, G or U. There is no
uppercasing, no T-to-U conversion, no truncation and no other rewrite.

Observed on all 12 manifest rows, checked against the evidence comparisons
and against the six manifest files:

```text
removed prefix = 11
removed suffix = empty
raw length = 38
cleaned length = 36
reason = boundary_markers_removed
status = accepted
alphabet after cleaning = A/C/G/U only
```

`removed_prefixes_exactly_11` is PASS for 12 rows.
`removed_suffixes_empty` is PASS for 12 rows.
`cleaned_sequences_length_36_and_acgu_only` is PASS for 12 rows.
`rows_accepted` is PASS: 12 accepted, 12 expected.
`rows_rejected` is PASS: 0 rejected.

Generation set `bos_token` 1 and `eos_token` 2. The observed handling is the
leading `11` prefix and the absent suffix marker. No trailing `1` or `2`
marker was present to remove.

## Released-code construction difference

Released-code logs warned:

```text
Some weights of the model checkpoint at /home/laura/RNAGenesis/configs/rnagenesis/autoencoder were not used when initializing EncDec
```

The evidence finding records `encoder_weights_unused = true`,
`unused_weight_count = 433` and `unused_weight_prefix = encoder.`. The
unused checkpoint path is
`/home/laura/RNAGenesis/configs/rnagenesis/autoencoder`. The warning is in:

```text
/home/laura/rnagenesis-mres-runs/m1_inference_e20f556/b0_release_d00899e_run1.console.log
/home/laura/rnagenesis-mres-runs/m1_inference_e20f556/b1_release_d00899e_run1.console.log
```

Parameter lines recorded by the evidence:

```text
released = EncDec has 157.13 M params.
current  = EncDec has 865.80 M params.
```

`unconditional_outputs_byte_identical` is true. The 157.13 M versus 865.80 M
construction difference, and the unused released encoder weights, did not
change the unconditional raw outputs. Released and current bytes match for
B0, and they match for B1.

## Tracked-bytecode operational incident

`b0_current_run1` omitted `PYTHONDONTWRITEBYTECODE`. That run rewrote three
tracked CPython 3.8 bytecode files. The evidence classifies this as an
operational note. `scientific_failure` is false. Later runs set
`PYTHONDONTWRITEBYTECODE=1`.

Exact restoration recorded by the evidence: each rewritten tracked
cpython-38 bytecode file matches its HEAD git blob. The cleanup command was
not recovered from a retained log
(`cleanup_command_recovered_from_a_retained_log = false`). The restoration
evidence is the blob identity below, not a reconstructed shell command.

| Path | Bytes | Git blob SHA-1 | SHA-256 | mtime |
| --- | ---: | --- | --- | --- |
| `/home/laura/RNAGenesis/models/autoencoder/encoder/esm/model/__pycache__/esm1.cpython-38.pyc` | 5268 | `a21a5d1f9b253b48a926c7d056f7daa25b557ba7` | `020ffe136eec1253a1641eecbbf1ca4dfd45b04d135a727e7e20ed5524d833b3` | 2026-09-28T10:13:59.393253498+10:00 |
| `/home/laura/RNAGenesis/models/autoencoder/encoder/esm/model/__pycache__/esm2.cpython-38.pyc` | 4237 | `0ee618c7e0bbad961efa8cb0172cdbdb50f74797` | `66255c859d8992bf539ba96ebd25e5b2048020ff1e38b65149429ea8afa7abb5` | 2026-09-28T10:13:59.393253498+10:00 |
| `/home/laura/RNAGenesis/models/autoencoder/encoder/esm/model/__pycache__/msa_transformer.cpython-38.pyc` | 5557 | `d2be904a754b1028d2e5f5ebdf753a492237aca4` | `bbe22dea2ba881a19ed29419c3dcadd1c42dd1a501646515aa8aeddc4bd6b7a4` | 2026-09-28T10:13:59.393253498+10:00 |

## Unit tests named with the audit-utility commit

The evidence JSON does not store unit-test tallies. The audit-utility commit
it names, `112a120282667c382790031fe74942f89f7b84eb`, was created only after
a bytecode-disabled rerun of the two test modules below. That rerun is not
a field of the inference evidence file.

| Module | Result | Condition |
| --- | --- | --- |
| `tests.test_audit_generation_output` | 16/16 | `PYTHONDONTWRITEBYTECODE=1` |
| `tests.test_train_diffusion_mres` | 39/39 | `PYTHONDONTWRITEBYTECODE=1`, CUDA hidden |

The 39 trainer tests are the lightweight trainer module. They are not the
biomap model-loading tests, which were not part of that rerun.

## Limitations recorded in the evidence

```text
author_supplied_golden_sequence_output_available = false
biological_quality_or_distributional_conclusion_supported = false
numerical_training_smoke_inside_this_result = false
diffusion_steps = 5
sequences_per_condition = 2
```

Statements stored with those flags:

- No author-supplied golden sequence output was available.
- Only two sequences per condition.
- Only five diffusion steps.
- The prior untracked B0 artifact matched the B0 raw SHA-256 but was not treated as authoritative.
- No biological-quality or distributional conclusion is supported.
- Numerical training smoke was not performed. It remains formal M5, outside this released-inference result.

The prior untracked artifact is not authoritative:

```text
path = /home/laura/RNAGenesis/generation_sequences/RNAGenesis_Aptamer_h200_tiny_test/seqs_wo_guidance_top_p=0.95_2_2_h200_tiny_test_seed42_steps5_batch2.txt
bytes = 78
sha256 = 407ed27564fdc200f190ff78eddae04466dd4ba3e7d4a0c30c5af64e8a91f25d
matched_b0_raw = true
authoritative = false
```

B0/B1 output differences from two sequences are not biological evidence.

## Checklist against formal M1

| Formal M1 output or constraint | Evidence |
| --- | --- |
| Tiny deterministic B0 generation regression | `b0_current_run1_versus_run2` PASS; all three B0 raw SHA-256 values identical |
| Tiny deterministic B1 generation | `b1_current_run1_versus_run2` PASS; all three B1 raw SHA-256 values identical |
| BOS/EOS handling verified | `bos_token` 1 and `eos_token` 2 in every argv; `removed_prefixes_exactly_11` PASS, 12 rows; `removed_suffixes_empty` PASS, 12 rows; raw length 38; cleaned length 36 |
| Cleaned A/C/G/U outputs | `cleaned_sequences_length_36_and_acgu_only` PASS, 12 rows; `rows_accepted` 12; `rows_rejected` 0 |
| Generation output provenance | Per-run raw, cleaned and manifest paths and SHA-256 values; code commits; argv; worktrees |
| B1 versus B0 weight and checkpoint identity | `b0_b1_weights_distinct` PASS; denoiser weights and configs differ; model index and scheduler are byte-identical |
| Current code does not alter released inference | `current_versus_released_b0` PASS; `current_versus_released_b1` PASS |
| No fine-tuning | `no_fine_tuning`, `no_backward_pass` and `no_optimizer_step` are true |
| No model-selection use of EVAL or REF | `model_selection_occurred` is false; no TRAIN, VALIDATION, REF or EVAL sequence was accessed |
| Human gate: accept inference regression | GO, 28 September 2026. Formal released-inference validation is COMPLETE / GO |

## Resolved scope decision

On 28 September 2026 the human gate chose the existing formal ordering.
Formal M1 released-inference validation is COMPLETE / GO. The formal
milestone definitions and ordering govern. No experimental milestone
order changes.

- The formal M1 section covers released inference: “Reproduce released inference behavior.”
- The formal M5 section covers numerical diffusion-training smoke: “Diffusion-training software smoke tests.”
- Formal M2, M3 and M4 remain required before M5.
- Broader wording elsewhere calls work after M0 “released-behaviour and numerical training smoke validation.” That phrase is in the M0 closure record and in the implementation plan’s M0 close and immediate-next-action text. That wording does not reassign M5 work into M1.
- No numerical training smoke was performed here. `numerical_training_smoke_inside_this_result` is false. Numerical diffusion-training smoke remains formal M5.
- No milestone definition, order or experimental design is changed by this decision.

The two-sequence B0 versus B1 difference stays outside any biological
claim. The evidence does not support a biological-quality or
distributional conclusion.
