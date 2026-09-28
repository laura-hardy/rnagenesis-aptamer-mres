# M2 published aptamer comparator verification — 28 September 2026

**Status: COMPLETE / GO — 28 September 2026.**

The human gate is GO. On 28 September 2026, Laura Hardy approved B0 as
the external aptamer-adapted comparator and closed formal M2. B0 is the
authors’ released aptamer-adapted comparator, not generic, unadapted or
pretrained-only. Provenance is `DIRECT_HUMAN_CONFIRMED_PROVENANCE`.
M3 is the next formal milestone. No GPU is currently authorised for
later work. Numerical diffusion-training smoke remains formal M5.

The B0 pool audit passed. The published-metric check is a separate,
permitted outcome: formal M2 allows that check only where it is feasible,
and requires the reason when it is not. The classification accepted here
is `INFEASIBLE_WITH_RELEASED_EVIDENCE`. No metric was calculated. That
infeasibility is not a failure of the B0 pool verification.

## Objective and scope

Formal M2, in the implementation plan, is “Published aptamer
implementation/comparator verification.” Its objective is to establish
that the released B0 aptamer condition and its existing 30,080-sequence
pool are correctly identified and usable as the external aptamer-adapted
comparator.

The formal inputs are `checkpoints/Aptamer/diffusion`, the existing B0
30,080 pool, the tracked B0 generation script, and the RNAGenesis aptamer
documentation and results. The formal outputs are a verified pool
manifest, an exact raw count, recorded seeds and settings, regenerated
cleaning statistics where needed, and a limited published aptamer metric
sanity check where that check is feasible.

This documentation step did not train D1, generate sequences, select a
model, or read REF or EVAL. Numerical diffusion-training smoke remains
formal M5, after M2–M4. No GPU was used for this documentation step.
`CUDA_VISIBLE_DEVICES=1` in the 10 June generation script is historical
provenance only. It does not authorise a GPU for this milestone or for
any later session.

The frozen modelling contract
`config/modelling/frozen_data_contract.json`
(`rnagenesis_corrected_669_core_m0`) keeps REF and EVAL unavailable
during generator development. They were not opened.

## Version provenance

| Role | Identity |
| --- | --- |
| Formal M1 closure commit, authoritative MRes repository `/home/laura/rnagenesis-aptamer-mres` | `c360991a374eed87dfdc36bd4a65149215355430`, subject `Close formal M1 released-inference gate` |
| Documentation base for the uncommitted M2 edits, branch `main` | `981d92c14863e021c4832f537f3216aa3e76dc1d`, subject `docs: add thesis evaluation planning docs` |
| RNAGenesis HEAD, branch `mres-d1-diffusion-finetune`, worktree `/home/laura/RNAGenesis` | `112a120282667c382790031fe74942f89f7b84eb`, subject `Add M1 generation output audit` |
| Released RNAGenesis worktree `/home/laura/rnagenesis-mres-worktrees/released-d00899e-m1` | `d00899eef60d664cc7b5880c0bb43f2a9e7a1b01`, subject `Update README.md` |
| Generation-time revision recorded in the 10 June log | abbreviated `d00899e`, which resolves in the RNAGenesis history to `d00899eef60d664cc7b5880c0bb43f2a9e7a1b01` |
| Audit utility | commit `112a120282667c382790031fe74942f89f7b84eb`, path `scripts/audit_generation_output.py`, git blob `3480af2dd758f4824655b3f7c8a5276214a61682` |

`c360991a374eed87dfdc36bd4a65149215355430` remains the formal M1 closure
commit. The uncommitted M2 edits now sit on documentation base
`981d92c14863e021c4832f537f3216aa3e76dc1d`, subject `docs: add thesis
evaluation planning docs`. That commit’s thesis-evaluation planning
documents are concurrent documentation. They are not part of the M2
scientific evidence.

The audit-utility blob at RNAGenesis HEAD
`112a120282667c382790031fe74942f89f7b84eb` matches the worktree blob
recorded before attempt 2. The utility was not patched for this audit.

M1 evidence reused is the closed cleaning rule and the audit utility, not
the M1 sequences. Formal M1 is recorded in
[M1 released-inference validation](m1_released_inference_validation.md).
Its evidence file is
`/home/laura/rnagenesis-mres-runs/m1_inference_e20f556/m1_released_inference_evidence.json`,
SHA-256 `ec518b3f8f78de19227abe5a14e138bcf381c231bc888689a298a16c946ee774`.
That run was a tiny technical regression: seed 42, five DDIM steps, two
sequences. It is not the 30,080-record B0 pool. What M2 reuses is the
boundary-only acceptance rule approved there, and the same audit utility
commit and blob.

Attempt 2 recorded both repositories with clean tracked trees before
cleaning. Attempt 1’s `pre_execution/` records were left unchanged.
Attempt 2 checked that those attempt-1 files remained byte-identical
(`attempt1_byte_identical_to_pre_execution_record true`, 11 files).

## B0 identity

Scientific label: `B0_released_aptamer_adapted_RNAGenesis`.

B0 is the authors’ released aptamer-adapted external comparator. The
generation script points the diffusion checkpoint at
`checkpoints/Aptamer/diffusion`. The implementation plan’s manifest label
for the same condition remains `B0_released_aptamer_rnagenesis`. The two
labels name one condition. The pool audit uses the scientific label above.

B0 is not generic, unadapted, or pretrained-only. Historical filenames and
commit subjects that contain `unadapted` are obsolete labels. They are
quoted in this report only as path and history text. They are not the
condition name.

B0 is not D1. D1 is the future MRes curated-aptamer diffusion adaptation,
initialised from the generic released checkpoint B1. B0 must not be used
as that initialisation.

B0 is not the length-matched causal baseline. The primary adaptation
contrast remains B1 against D1, with B2 as the non-neural null. B0 stays
an external comparator because its sampler setting and cleaned length are
the released aptamer generation regime recorded below, not a
TRAIN-matched length draw.

## Human-confirmed provenance

Classification: `DIRECT_HUMAN_CONFIRMED_PROVENANCE`.

On 28 September 2026, Laura Hardy confirmed that the ten tracked chunks
are the B0 pool she generated earlier in 2026 using the authors’ released
aptamer-fine-tuned RNAGenesis checkpoint, with ChatGPT and Cursor
assistance.

That sentence is the provenance classification. The artefacts below
support it. They do not replace it, and they do not supply a 10 June
checkpoint hash.

Supporting records, listed separately from the confirmation:

| Record | Identity |
| --- | --- |
| Generation script | `scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh`, git blob `dcb81522a67d5e04c55bf0f73fcbd9630dc6d829`, introduced by `f5eef4b094d273355a5b5664c810149d35455731` on 2026-06-10 16:01:09 +1000 |
| Contemporaneous log | `docs/run_notes/h200_baseline_30k_output.log`, SHA-256 `3e351f87db1a4d13c67590b8aada23b43848cd9d882f38519dd3514f6d4fd545` |
| Checksum manifest | `results/phase4_1_unadapted_rnagenesis_30k/checksums/sha256_raw_generated_files.txt`, git blob `65ca7441eb29b5f9bf6c8a3ffad371e86e5ce6b2`, SHA-256 `ad3a75fe157248be50427757357cbc5c060be3ddb664d3be64ef178ac90b85c3` |
| Raw-pool commit | `2623a348947ebcc8f7d4628e5c1712a9938de3b8` on 2026-06-11 12:22:39 +1000 |
| Code revision in the log | `d00899e` / `d00899eef60d664cc7b5880c0bb43f2a9e7a1b01` |
| Pool structure | ten tracked chunks, seeds 4201–4210, 3,008 raw records each |
| Log timing | host `aai`, conda environment `rnagenesis-h200`, working directory `/home/laura/RNAGenesis`, start Wed 10 Jun 2026 16:11:51 AEST, all chunks complete Wed 10 Jun 2026 17:39:40 AEST |
| Log statements on every chunk | `sample strategy top_p=0.95`, `without guidance`, `no tree search`, `EncDec has 157.13 M params.` |

The log contains zero SHA-256 lines. No contemporaneous 10 June
checkpoint hash was retained. This audit did not hash the checkpoint
file. The weight hash recorded in the 25 September model-asset manifest
is a later inspection of the file then on disk. It does not prove that
those bytes were the bytes loaded on 10 June.

## Immutable raw-pool manifest

Repository root: `/home/laura/rnagenesis-aptamer-mres`.

The ten source paths below are repository-relative and are the tracked
files. Each file is 117,312 bytes, which is 3,008 records of 38
characters plus a terminating newline. Each chunk’s raw SHA-256 matched
the tracked checksum manifest before cleaning and matched again after
cleaning.

| Chunk | Seed | Repository-relative source path | Raw SHA-256 |
| --- | ---: | --- | --- |
| 1 | 4201 | `results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk1_seed4201_steps50_batch16_batchnum188_gpu1.txt` | `12df7c26eed40f68241455f43b20aed190de81c27d47f06d2117aaef0866f1f6` |
| 2 | 4202 | `results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk2_seed4202_steps50_batch16_batchnum188_gpu1.txt` | `1f8b9b082dc4cf01570d5aedb9d2fd1a71fb746c6ee63cde4fbef9c10a943cd6` |
| 3 | 4203 | `results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk3_seed4203_steps50_batch16_batchnum188_gpu1.txt` | `49c6ff2ce0979ef406e7c63aeabf0fc6226ca2f5498b7b08f6c2fbf2b31e1ff3` |
| 4 | 4204 | `results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk4_seed4204_steps50_batch16_batchnum188_gpu1.txt` | `cdd853c1a7d5a27e4c5ee7c242a7f0808b212aa7464d3d3bb41c11b78742d236` |
| 5 | 4205 | `results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk5_seed4205_steps50_batch16_batchnum188_gpu1.txt` | `f1bd2686fa5fb494bf9a270424fbdfbeb6b158669da09b4fc86694d6c5bd40f8` |
| 6 | 4206 | `results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk6_seed4206_steps50_batch16_batchnum188_gpu1.txt` | `275b744eeb2dd1cdc7b6042de65b5ea08cd159c1e90896d53f6300b1331d3904` |
| 7 | 4207 | `results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk7_seed4207_steps50_batch16_batchnum188_gpu1.txt` | `db64a6e3c52980cbd62590f6b190774b55f079dfb8b552b27b3043141e4771ca` |
| 8 | 4208 | `results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk8_seed4208_steps50_batch16_batchnum188_gpu1.txt` | `63c21618be699ad1323570bbf2041db31fac6aa2d2b8c03691da767dfdd36b27` |
| 9 | 4209 | `results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk9_seed4209_steps50_batch16_batchnum188_gpu1.txt` | `1ec36b36e11fc966a870327b3cc02653c037382ffd9ce44cea7952cce6e0be0f` |
| 10 | 4210 | `results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk10_seed4210_steps50_batch16_batchnum188_gpu1.txt` | `b4e5f2e8ae9187d711dc614fd523e89f83dbc84b792b28c8f951cf343a38f511` |

Numeric raw concatenation SHA-256, chunks 1–10 in that order:

```text
ed612277105c6b8747fc7365cc6b67fa8a94e8e5e8e64ee535ecadcb37ff4aaa
```

The pre-execution hash gate recorded `numeric_order_concat_match true`.

Numeric order is required because the historical filenames are unpadded.
A lexical glob of `chunk*.txt` orders the basenames as `chunk1`,
`chunk10`, `chunk2`, `chunk3`, `chunk4`, `chunk5`, `chunk6`, `chunk7`,
`chunk8`, `chunk9`. After the shared prefix `chunk1`, the character `0`
in `chunk10` sorts before `chunk2`. Seed 4210 would therefore sit between
seed 4201 and seed 4202. The recorded concatenation hash is the numeric
chunk order, which is also seed order 4201–4210. A lexical concatenation
is a different byte string and is not this hash.

The directory name `phase4_1_unadapted_rnagenesis_30k` is a preserved
historical source name. It is an obsolete label. The scientific condition
is `B0_released_aptamer_adapted_RNAGenesis`.

## Generation settings

Recovered from
`scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh`
and corroborated by the short lines in
`docs/run_notes/h200_baseline_30k_output.log`.
The script calls `python generation.py`. Seeds are `4200 + chunk` for
chunks 1–10. The remark is
`_h200_baseline_30k_chunk${CHUNK}_seed${SEED}_steps50_batch16_batchnum188_gpu1`.

### Settings that defined the sampler

| Setting | Recorded value |
| --- | --- |
| `enc_dec_file` | `configs/rnagenesis/autoencoder` |
| `dm_file` | `checkpoints/Aptamer/diffusion` |
| `decoder_config` | `config-progen2-small-rna_tokenizer_v2` |
| `num_inference_steps` | 50 |
| `batch_size` | 16 |
| `batch_num` | 188 |
| seeds | 4201, 4202, 4203, 4204, 4205, 4206, 4207, 4208, 4209, 4210 |
| `eta` | 0 |
| `max_seq_len` | 37 |
| `do_sample` | passed (`store_true`) |
| `top_p` | 0.95 |
| `top_k` | 0 |
| `eos_token` | `2` |
| `bos_token` | `1` |
| `device` recorded in the script | `cuda` |
| `superfolder` | `generation_sequences` |
| `mid_folder` | `RNAGenesis_Aptamer_h200_baseline_30k` |
| sequences per chunk | 3,008 (`16 × 188`) |
| chunk count | 10 |

`do_sample` with `top_p=0.95` is the active sampling strategy. The log
prints `sample strategy top_p=0.95` for every chunk. `top_k=0` does not
select top-k sampling on that path, because the released `generation.py`
prints a top-k strategy only when `top_p` is not below 1.

### Enabling flags that were not passed

`generation.py` turns guidance and search on only with `store_true`
flags. The 10 June script did not pass any of these:

```text
--guidance
--search_general
--tree_search
--update_seq
--truncate
--extend_input
--multiple_eos_tokens
--save_latent_space
```

The attempt-2 evidence records `guidance_flag_passed = false` and
`search_general_flag_passed = false`. Every chunk log says
`without guidance` and `no tree search`. Guidance and tree search were
not enabled.

### Required parser arguments that did not enable those modes

`generation.py` marks the following arguments `required=True` even when
the enabling flags above are absent. The script supplied them. They are
not evidence that guidance or tree search ran.

| Argument | Supplied value | Role in this invocation |
| --- | --- | --- |
| `--target_class` | `0` | Forwarded into `diffusion_pipeline` together with `guidance=False` |
| `--recurrence_step` | `1` | Forwarded with `guidance=False` |
| `--guidance_start_step` | `0` | Forwarded with `guidance=False` |
| `--guidance_stop_step` | `50` | Forwarded with `guidance=False` |
| `--guidance_classifier_model_config` | `dummy_unused.yaml` | Classifier load is gated by `--guidance`, which was not passed |
| `--guidance_scale` | `1.0` | Printed only in the `with guidance` branch, which was not taken |
| `--classifier_loss_type` | `l2` | Not an argument of the unconditional `diffusion_pipeline` call |
| `--search_goal` | `similarity` | Used only when `--search_general` is set |
| `--active_size` | `1` | Used only when `--search_general` is set |
| `--branch_size` | `1` | Used only when `--search_general` is set |

`CUDA_VISIBLE_DEVICES=1` is recorded in the script and in the log. It is
historical device provenance for the 10 June run. It grants no current
GPU authorisation. No GPU is currently authorised for later work. Before
any future GPU command, the human must identify the authorised physical
device; `CUDA_VISIBLE_DEVICES` must then map that physical device to
logical `cuda:0`.

## Cleaning protocol

The cleaning rule is the boundary-only rule approved in formal M1 and
implemented by `scripts/audit_generation_output.py` at blob
`3480af2dd758f4824655b3f7c8a5276214a61682`.

Newline delimiters separate records and are not sequence characters. A
trailing newline does not add a record. Each record then loses its
leading run of the characters `1` and `2`, and any trailing run of `1`
and `2` that remains after that. Characters in the middle stay as they
are. The cleaned body is accepted only when it is nonempty and every
character is A, C, G, or U. There is no uppercasing, no T-to-U
conversion, no truncation, no filtering, and no deduplication. Rejected
rows are not written. Accepted duplicates, if any, stay in the cleaned
output. This audit had no rejected rows and no accepted duplicates.

Attempt 2’s pre-execution contract inspection recorded
`implementation_matches_m1_contract true` and `patched false`.

Two other procedures exist in the project history. Neither was
substituted for this rule.

`test_wrap_aptamer.get_gen_seqs` is a different evaluation’s
preprocessor. If the character `2` occurs anywhere, it deletes every `2`.
It then drops only the first remaining character, and it concatenates
fixed flanking strings. On a raw record whose boundary prefix is `11`,
dropping one character leaves a `1` inside the string that is then
folded. The M1 rule removes the whole leading run and adds no flanks.
`get_gen_seqs` was not run. The published-source audit classifies the
script that calls it as a different evaluation with unpublished
repository defaults.

The Aim 3 Stage 1 cleaner
(`src/aim3_pipeline/stage1_hard_filter.py`,
`scripts/run_stage1_hard_filter.py`) is a quality filter. Its default
configuration strips a leading `11`, uppercases, enforces an RNA
alphabet, drops exact duplicates after the first copy, and fails
homopolymer runs of length 5 or greater. It can also compute GC content
and ViennaRNA minimum free energy. The M2 audit does none of those
rewrites or exclusions. Stage 1 was not run, and its historical outputs
were not used as the cleaned pool.

## Exact accounting

Definitions used by the audit utility:

```text
raw = newline-delimited records; a trailing newline does not add a record
accepted = cleaned body nonempty and restricted to A, C, G, and U
rejected = raw records that were not accepted
unique accepted = number of distinct accepted cleaned strings
duplicate accepted = accepted count minus unique accepted count
```

| Quantity | Value |
| --- | ---: |
| Raw | 30,080 |
| Accepted | 30,080 |
| Rejected | 0 |
| Unique accepted | 30,080 |
| Duplicate accepted | 0 |
| Raw length | 38 on every record |
| Cleaned length | 36 on every record |

Rejection reasons: none.

Removed prefix: `11` on all 30,080 records. Removed suffix: empty on all
30,080 records. Acceptance reason: `boundary_markers_removed` on all
30,080 records.

Raw alphabet counts: `1` 60,160; A 91,836; C 89,148; G 578,835; U 323,061.

Cleaned alphabet counts: A 91,836; C 89,148; G 578,835; U 323,061.

The 60,160 copies of `1` are the two leading boundary characters on each
of 30,080 records (`2 × 30,080`). Those characters are absent from the
cleaned alphabet. The A, C, G, and U counts are unchanged, which is what
boundary-only removal requires when nothing else is rewritten.

Pooled cleaned SHA-256, accepted records concatenated in numeric chunk
order:

```text
51ccf2b997f1e6386438be303e5affaf908f102bd098bab243a2a9ba1d94d6e1
```

Per-chunk cleaned SHA-256 values, same numeric order:

| Chunk | Seed | Accepted | Cleaned SHA-256 |
| --- | ---: | ---: | --- |
| 1 | 4201 | 3,008 | `3c6458240e0080caf2d75dc821c21ebcc5598c99b9b028643f88f0564b123a1c` |
| 2 | 4202 | 3,008 | `1154fe5a8da7efdce9cf363148a4530c7784628bd95bd6134e53766be980d34c` |
| 3 | 4203 | 3,008 | `37eeecb12d073af169c8a73356b7f3eb88bcc06b825d96bcd6dff57febf6a3f1` |
| 4 | 4204 | 3,008 | `80770db3604a5fdf86c6a2bf384162705c323720899ce8b0cbd79129d7b6056e` |
| 5 | 4205 | 3,008 | `5bc4cdea457f9b7d8f6345486f8002199111e84d247e88f5a63de874376b619e` |
| 6 | 4206 | 3,008 | `ddbb6c99f3684d415e85691736c7aef841a0fdddfd3104fd2fb9c4d000ff21de` |
| 7 | 4207 | 3,008 | `70945237cc5d519a0077e3b9a71877c89169a0c57722ca45e3961d2d0822d4ac` |
| 8 | 4208 | 3,008 | `2e50747c6d9610aa793db30555cfd313b18cc7532dc89a5e7f7cfb6ac065e1f5` |
| 9 | 4209 | 3,008 | `855dad1eb7747085ebfcba524cd3c6cf5e8a9e7033784f280d1104d5ab58be37` |
| 10 | 4210 | 3,008 | `4d9fc81e3ca676de003e5263da454e87ea349bba072abfda2a454657c5ad9c3d` |

Filtering occurred: false. Deduplication occurred: false. Every raw
record has a manifest row. Every accepted row was written, in order, to
that chunk’s cleaned file.

Syntactic validity and exact uniqueness are not evidence of biological
quality. Acceptance here means the cleaned body is a nonempty A/C/G/U
string after boundary-marker removal. It does not mean the sequence is
aptamer-like, structured, novel, or suitable as a therapeutic candidate.
Uniqueness means the 30,080 cleaned strings are pairwise distinct. It
does not mean they are biologically independent.

B0, as cleaned for this milestone, is a 36-nt pool. The sampler argument
was nominal `max_seq_len=37`. Every raw record is 38 characters because
it carries the leading boundary prefix `11` in front of 36 letters, and
it has no trailing boundary suffix. The cleaned length is 36 throughout.
This pool is not a 37-nt biological pool. Earlier plan wording that calls
the released setting a “37-nt maximum/output regime” names that nominal
`max_seq_len`. The length of the cleaned comparator sequences is 36 nt.

## Execution evidence

### Attempt 1

Directory: `/home/laura/rnagenesis-mres-runs/m2_b0_pool_audit_c360991`.

Classification: `SAFE_STOP_OUTPUT_DIRECTORY_ALREADY_EXISTED`.

The directory already existed and already held `pre_execution/` records
from 2026-09-28T13:52:58+10:00, including `heads.txt`. No cleaning was
performed. The stop was not a scientific cleaning failure. The directory
was not modified, deleted, renamed, merged, or reused. Those
`pre_execution/` files were read for this report and were not edited.

Attempt-1 heads, preserved:

```text
MRES_HEAD=c360991a374eed87dfdc36bd4a65149215355430
RNAGENESIS_HEAD=112a120282667c382790031fe74942f89f7b84eb
AUDIT_UTILITY_BLOB=3480af2dd758f4824655b3f7c8a5276214a61682
```

### Attempt 2

Classification: `PASS`.

Output directory:
`/home/laura/rnagenesis-mres-runs/m2_b0_pool_audit_c360991_attempt2`.

| Evidence | Path | SHA-256 |
| --- | --- | --- |
| Pooled evidence JSON | `.../pooled/pooled_evidence_summary.json` | `83ad84ee3c1cf49e8cbcd88cd31cd5580dbf16fb2994e7bba715c8b356f70f1d` |
| Pooled evidence Markdown | `.../pooled/pooled_evidence_summary.md` | `cb7f9681d615a63fbe319b29a9feae563e3bdb6c0d07fd05d6715aa78852fb1b` |
| Accepted numeric-order text | `.../pooled/accepted_numeric_order.txt` | `51ccf2b997f1e6386438be303e5affaf908f102bd098bab243a2a9ba1d94d6e1` |

The accepted-text hash equals the pooled cleaned hash. Chunk outputs
live under `chunks/chunk_01_seed4201` through `chunks/chunk_10_seed4210`,
each with `cleaned.txt`, `manifest.csv`, `summary.json`, and
`command.log`. Post-execution records are in `post_execution/`, including
`classification.txt`, `raw_rehash.txt`, `audit_utility_tests.log`, and
`attempt1_unchanged.txt`.

All ten raw hashes remained unchanged. `raw_rehash.txt` records `MATCH`
for every chunk and `all_byte_identical true`.

Audit tests: `python3 -m unittest tests.test_audit_generation_output`,
16 tests, 16 passed, exit code 0. The recorded interpreter is
Python 3.13.13, packaged by Anaconda, with `CUDA_VISIBLE_DEVICES` empty
and `PYTHONDONTWRITEBYTECODE=1`. That run is CPU-only. It verifies the
audit utility used for this cleaning account. It does not reproduce the
Python 3.8 generation environment. The 10 June log names conda environment
`rnagenesis-h200`, and the M0 environment manifest records that
environment as Python 3.8.13.

## Published-source audit

Source audit:
`/home/laura/rnagenesis-mres-runs/m2_published_metric_source_audit_c360991/REPORT.md`,
SHA-256 `4043a5ac98397071f1773212a4729cb832642364480111301c75c51d09402667`.

Inspection window: 2026-09-28T05:18:19Z through 2026-09-28T05:27:15Z.
DOI inspected: `10.1101/2024.12.30.630826`. The audit retrieved the
papers and metadata. It did not generate sequences, load weights, open
biological sequence datasets, or calculate a metric. This documentation
step did not reopen the PDFs or recompute those hashes. The values below
are the audit’s recorded rendition hashes for the files served on
28 September 2026. PDF `ModDate` values are that retrieval day. Version
identity is the versioned URL plus the in-PDF posting line.

| Version | Posted | Pages | PDF SHA-256 |
| --- | --- | ---: | --- |
| 1 | December 31, 2024 | 17 | `e72492733da0c5724aacfc2e97760e249c8b08fa9a4ddf9a530b998bbebb920e` |
| 2 | June 22, 2025 | 51 | `83f2f0b4eacdf817feea89a1bcd1dcf6c95ac78f4018199462fbbe7559295336` |
| 3 | July 1, 2025 | 51 | `fe64fad529876d848334120c3fa35f67f0b01917b2b5a07849ff2d38eef02046` |

Version 1 title: “RNAGenesis: Foundation Model for Enhanced RNA Sequence
Generation and Structural Insights.” Versions 2 and 3 title: “RNAGenesis:
A Generalist Foundation Model for Functional RNA Therapeutics.” All three
are preprints under CC-BY-NC-ND 4.0. No version 4 was present. No version
has a separate downloadable supplement.

These are two experiments, and they stay separate.

Version 1 generated 64,000 sequences and evaluated 13,802 drawn at random
from each generated set, described as the same count as HT-SELEX dataset
A. Its aptamer figures are Figures 5 and 6. Named metrics include minimum
4-mer distance, minimum sequence Levenshtein distance, minimum
secondary-structure Levenshtein distance, G/C content, minimum free
energy, t-SNE, Fréchet Inception Distance, DNA base ratio, and MEME
E-value. The text gives no numeric result, formula, seed, eta, DDIM step
count, or aptamer length.

Versions 2 and 3 generated 25,600 RNAGenesis sequences and 25,600 RNA-FM
sequences, with batch size 128 resampled 200 times (`128 × 200 = 25,600`).
Figure 3f compares those generated sequences with 13,802 HT-SELEX dataset
A sequences. The four named distributional metrics are sequence edit
(Levenshtein) distance, GC content, minimum free energy, and
secondary-structure edit distance. The paper describes the direction of
the difference and the box-plot geometry. It does not print the plotted
medians. The string “64,000” does not occur in versions 2 or 3. The
version 1 metric set is not silently reused as the version 2/3 metric
set.

The released README mixes those versions. At author revision
`d00899eef60d664cc7b5880c0bb43f2a9e7a1b01`, and identically at MRes
RNAGenesis `112a120282667c382790031fe74942f89f7b84eb`, the README badge
links to version 2, while the citation block uses the version 1 title and
the version 1 author list. The README aptamer example uses `batch_size`
128 and `batch_num` 200, which matches the version 2/3 count and does not
match version 1. That example calls `python generate.py`. No `generate.py`
exists at either revision. The printed command also omits seed, eta, and
the DDIM step count, all of which `generation.py` requires. The README
therefore does not pin one protocol, and it is not a complete invocation
of either published comparison.

No exact released implementation maps to either published comparison.
`generation.py` is a sampler. It does not compute the paper metrics.
Tracked code at the inspected revisions has no Levenshtein, GC-content,
FID, or MEME evaluation script for the aptamer figures.
`test_wrap_aptamer.py` folds sequences and scores them against one
hard-coded reference. That is a different quantity from a distribution
against 13,802 SELEX sequences, and it is a different quantity from a
structure-string edit distance.

Classification of `test_wrap_aptamer.py`: a different evaluation, with
unpublished repository defaults. It was not run for M2. Its CLI defaults,
`threshold_A=80.0`, `threshold_B=2.0`, and `factor=2.0`, are not stated
as aptamer acceptance rules in any paper version. The value-function path
uses `factor=5.0` instead. Neither default is the published aptamer
metric.

Published-metric classification:

```text
INFEASIBLE_WITH_RELEASED_EVIDENCE
```

The source audit’s own metric-stage decision is NO-GO. Nothing in the
released evidence is a recoverable blocked check. No tolerance was
invented, and no PASS/FAIL band is proposed.

Routes that would not supply the missing protocol or the missing numeric
target:

- Opening the SELEX file would supply sequences. It would not supply the
  unpublished formula, the sampler settings the paper omits, or the
  plotted numbers. The AptaDiff README does not restate the RNAGenesis
  split. The file was not downloaded.
- Digitising Figures 5, 6, or 3f would estimate pixels. It would not
  recover author source data, a formula, or a software version. Pixel
  measurement was not done.
- Library defaults in `pipeline_ddim.py`, including eta 0 with 50 steps
  on one path and eta 1 on a search path, are caller defaults. The paper
  does not select one, and the README aptamer block does not either.
  They were not adopted as the published protocol.
- Repository thresholds in `test_wrap_aptamer.py` are unpublished
  defaults for a different single-reference screen. They are not a
  numeric target for Figure 3f or for Figures 5 and 6.

No metric was calculated. No GC content, minimum free energy, edit
distance, similarity, FID, motif, or structure metric was computed from
the B0 pool in this milestone.

## Formal checklist and limitations

| Formal M2 requirement | Evidence |
| --- | --- |
| Objective: identify the released B0 condition and the existing 30,080 pool | Scientific label, human-confirmed provenance, ten-chunk manifest, raw count 30,080 |
| Input: `checkpoints/Aptamer/diffusion` | Path recorded in the generation script and in the model-asset manifest. No 10 June byte hash. See limitations |
| Input: existing B0 30,080 pool | Ten tracked files, checksum manifest, numeric concatenation hash |
| Input: tracked B0 generation script | `scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh`, blob `dcb81522a67d5e04c55bf0f73fcbd9630dc6d829` |
| Input: RNAGenesis aptamer documentation and results | Published-source audit of bioRxiv versions 1–3 and released revision `d00899ee` |
| Output: pool manifest reconstructed and verified | Attempt-2 pooled evidence; pre-execution hash gate PASS |
| Output: exact raw count | 30,080 raw, 3,008 per chunk |
| Output: seeds and settings recorded | Seeds 4201–4210 and the setting tables above |
| Output: cleaning statistics regenerated where needed | Attempt 2 regenerated the boundary-only account. Attempt 1 cleaned nothing |
| Output: limited published metric sanity check where feasible | Infeasible with released evidence. Documented. No metric calculated |
| Human gate: approve B0 as the external aptamer-adapted comparator | GO — 28 September 2026. Laura Hardy approved B0 as the external aptamer-adapted comparator |
| Must not: D1 training | Not performed |
| Must not: reinterpret B0 as generic or unadapted | Scientific label is the aptamer-adapted comparator. Historical `unadapted` strings are preserved as obsolete names |

### Known from records

The script, log, checksum manifest, file sizes, and raw hashes establish
the sampler settings, the ten seeds, the 10 June code-revision
abbreviation, the absence of the guidance and search flags, the chunk
timing, and the byte identity of the tracked raw files. The attempt-2
audit establishes the boundary-only counts, alphabets, lengths, and
cleaned hash. The published-source audit establishes the three preprint
versions and the absence of a matching released metric implementation.

### Human-confirmed, and not inferred from hashes alone

Laura Hardy’s 28 September 2026 confirmation identifies these ten files
as the pool she generated earlier in 2026 from the authors’ released
aptamer-fine-tuned checkpoint, with ChatGPT and Cursor assistance. That
confirmation is the provenance class
`DIRECT_HUMAN_CONFIRMED_PROVENANCE`.

### Irrecoverable from released evidence

No contemporaneous 10 June checkpoint hash exists in the log or in the
retained manifest. Today’s on-disk checkpoint identity does not fill that
gap. The published aptamer comparisons lack a single version pin, textual
metric formulas, aptamer sampler settings in the paper, figure source
data, and an evaluation script that implements either comparison. Those
gaps are limitations. They are not silently resolved facts.

## Conclusion

Formal M2 is COMPLETE / GO — 28 September 2026. The human gate approved
B0 as the external aptamer-adapted comparator. B0 is the authors’
released aptamer-adapted comparator, not generic, unadapted or
pretrained-only. The scientific label is
`B0_released_aptamer_adapted_RNAGenesis`. Provenance is
`DIRECT_HUMAN_CONFIRMED_PROVENANCE`.

Pool accounting is raw 30,080, accepted 30,080, rejected 0, unique
accepted 30,080, duplicate accepted 0, and cleaned length 36 throughout.
Raw artifacts remained unchanged. Recovered settings and seeds are
recorded above. Guidance and tree search were not enabled.

The limited published-metric check is
`INFEASIBLE_WITH_RELEASED_EVIDENCE`. That result is the documented
“where feasible” outcome formal M2 requires when the check cannot be
performed. No metric was calculated. It does not withdraw the pool
identification. The missing contemporaneous 10 June checkpoint hash
remains an explicit limitation. No biological-quality claim follows from
syntactic acceptance or uniqueness.

No D1 training, generation, model selection, REF/EVAL access or
unauthorised GPU use occurred. No GPU is currently authorised for later
work. Numerical diffusion-training smoke remains formal M5. M3 is the
next formal milestone.
