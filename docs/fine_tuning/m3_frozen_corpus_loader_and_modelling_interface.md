# M3 frozen corpus loader and modelling interface — 29 September 2026

**Status: COMPLETE / GO — 29 September 2026.**

The frozen-input and tokenizer/interface gate is **PASS**. The
chemistry and no-silent-loss human gate is **PASS**. On 29 September
2026, Laura Hardy gave final human approval. The RNAGenesis
implementation commit is `e3b855bbf4d1af376f43747643fa30afd662828c`
on `mres-d1-diffusion-finetune`. This record does not authorise M4, M5,
model loading, GPU work, training, generation, checkpoint selection,
or REF/EVAL.

## 1. Objective, scope, and prohibited actions

Formal M3 proves that the frozen development data can enter the
RNAGenesis modelling interface without transformation or leakage.

The completed gate tokenized every first-occurrence TRAIN and
VALIDATION modelling core on CPU through `encode_rna_characters`.
Chemistry stayed in a report. The production trainer, loaders,
collators, EncDec, denoiser, and tokenizer implementation were not
edited.

This stage did not:

- run a GPU command, even though physical GPU 0 is authorised for
  29 September 2026;
- load a model or checkpoint;
- rerun full-corpus tokenization (attempt 1 is immutable, and the
  harness refuses to overwrite it);
- construct an optimizer, run a forward or backward pass, train, or
  generate;
- open REF or EVAL;
- change frozen data or `config/modelling/frozen_data_contract.json`;
- recreate the obsolete repository-local `data/processed` copies;
- change `train_diffusion_mres.py`, production loaders, collators,
  EncDec, or tokenizer code;
- install dependencies;
- stage, commit, push, or refresh the context mirror.

`CUDA_VISIBLE_DEVICES` was empty for the gate. The summary records
`cuda_visible_devices` as `""` and `gpu_used` as false.

## 2. Repository SHAs and branches

Checked before this documentation edit, and recorded by the passing
gate:

| Repository | Branch | HEAD, upstream, and live `origin` |
| --- | --- | --- |
| `/home/laura/RNAGenesis` | `mres-d1-diffusion-finetune` | `112a120282667c382790031fe74942f89f7b84eb` |
| `/home/laura/rnagenesis-aptamer-mres` | `main` | `f2bdff1ade9e2aec9f37aaa23477ec40f3f21585` |

Both tracked trees and indexes were clean at the gate. The preserved
MRes stash is `stash@{0}` `a6ed3267eac5ef42c11745d9fa345560b47f4a14`,
subject `On main: pre-6bb2aa8 H200 documentation edits`, and it is the
only stash. The backup branch `backup/m1-pre-rebase-f55a6c5` remains
`f55a6c544279aca24b2e212fdb017e7e4c4a4954`.

The RNAGenesis implementation commit is
`e3b855bbf4d1af376f43747643fa30afd662828c` on
`mres-d1-diffusion-finetune`. It records the reviewed gate files below.
This documentation stage did not change their reviewed contents:

- `scripts/m3_frozen_tokenizer_gate.py`
- `tests/test_m3_frozen_tokenizer_gate.py`

## 3. Why the development directory is the M0-authorized location

`/home/laura/rnagenesis-mres-data/development` is the H200 directory
named by the passing M0 development-profile check and the clean M0
preflight. The frozen contract keeps repository-relative names
`data/processed/corpus_final.txt`, `data/processed/ft_train.csv`, and
`data/processed/ft_validation.csv`. The development profile does not
read those relative paths from the repository. It takes the basename
of each contract path and opens it only inside the directory supplied
as `--data-dir`, after refusing REF and EVAL.

M0 required that directory to contain exactly those three regular
files, with the frozen SHA-256 values, and to contain no other names.
The 25 September 2026 closure recorded that isolated directory as
`/home/laura/rnagenesis-mres-data/development`. The same three hashes
passed again before the tokenizer gate. The contract file was not
rewritten to embed that absolute path.

## 4. Obsolete repository-local copies

Before M3, `/home/laura/rnagenesis-aptamer-mres/data/processed`
contained a second, pre-correction copy of the three filenames. Those
files were gitignored. They were not the bytes at HEAD or at corpus
closure `10aac629bb0ef0337107c3d628b23e1897962af9`. Their hashes and
counts were not the frozen contract:

| File | Observed SHA-256 | Size | Observed counts |
| --- | --- | ---: | --- |
| `corpus_final.txt` | `6f8c2091706cc28526ae53a1021395cad1b7943745ddffbaea631edc01df3340` | 38,525 | 678 lines |
| `ft_train.csv` | `941fe8783ee8c99a2ce7598dea00ed123e62750026b7f157f28e7bbcc5d14a8f` | 1,238,344 | 746 identities, 678 cores, 571 clusters |
| `ft_validation.csv` | `03be477e12f7b9ca20f8911e2ac88fde2949af2b6131c2d2aa43eef2ae6d9abc` | 251,148 | 149 identities, 117 cores, 64 clusters |

Those copies failed `^[ACGU]+$` because `sequence_core` still
contained `T` (6 TRAIN cores and 1 VALIDATION identity). They were not
repaired. They were deliberately deleted and must not be recreated or
used. After deletion, `data/processed` exists and is empty. The three
filenames are absent. The development-profile verifier, pointed at the
hash-matching development directory, is the authorized check. Pointing
the local-corpus profile at the old directory is not an alternative
authority.

## 5. Frozen paths, sizes, and SHA-256

Contract `config/modelling/frozen_data_contract.json`, SHA-256
`396c83c3dbf9afc656ad5c60ec05c94fce3c5a684990c3cc1cebfb2411ccd5ff`,
contract id `rnagenesis_corrected_669_core_m0`. Corpus closure
`10aac629bb0ef0337107c3d628b23e1897962af9`.

| Role | Path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| TRAIN text | `/home/laura/rnagenesis-mres-data/development/corpus_final.txt` | 37,700 | `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d` |
| TRAIN CSV | `/home/laura/rnagenesis-mres-data/development/ft_train.csv` | 1,201,524 | `84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0` |
| VALIDATION CSV | `/home/laura/rnagenesis-mres-data/development/ft_validation.csv` | 226,410 | `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd` |

The development directory’s names are exactly those three regular
files. Corpus text is LF-only, ends with a newline, and has 669
physical lines and no blank line. Both CSVs have 86 columns. TRAIN
CSV parsing yields 726 data rows; embedded carriage returns inside
quoted publication fields make a raw `splitlines` count larger than
the record count. VALIDATION CSV parsing yields 132 data rows.
Independently recomputed SHA-256 values match the table. The gate
opened `frozen_data_contract.json`, `corpus_final.txt`, `ft_train.csv`,
and `ft_validation.csv`. It did not open REF or EVAL.

## 6. Identity, core, and cluster counts

| Set | Identity rows | Distinct cores | Clusters (`cluster_id`) |
| --- | ---: | ---: | ---: |
| TRAIN | 726 | 669 | 569 |
| Corpus `corpus_final.txt` | — | 669 records, 669 unique | 569, one cluster per core |
| VALIDATION | 132 | 95 | 63 |

TRAIN has 57 repeated identity rows (`726 - 669`). VALIDATION has 37
(`132 - 95`). No core maps to more than one `cluster_id`. The
contracted cluster column is `cluster_id`. `sequence_cluster_id_mmseqs`
is a different column and is not the contracted count. All-four-role
leakage was not recomputed; REF and EVAL stayed closed, as at M0.

## 7. Alphabet, case, whitespace, order, length, role, and overlap

Every modelling core matches `^[ACGU]+$` on the original string. The
gate applied no trim, no case conversion, and no T-to-U conversion.
`t_to_u_applied` is historical curation metadata: TRAIN `false` 674
and `true` 52; VALIDATION `false` 117 and `true` 15. Those flags do
not authorise another conversion. `alphabet_as_reported` is TRAIN RNA
632, `DNA_T` 52, `chemical_notation` 42; VALIDATION RNA 109, `DNA_T`
15, `chemical_notation` 8. The frozen cores contain no `T`.

`partition` is `FT` on all 726 TRAIN rows and all 132 VALIDATION rows.
`ft_split` is `TRAIN` or `VALIDATION` on the matching file. Scientific
identity ids are unique within each file.

Corpus lines equal the TRAIN `sequence_core` values in first-occurrence
order. VALIDATION modelling order is the same first-occurrence rule.
Frozen indexes start at 0. CSV row numbers treat the header as row 1.

Overlap between TRAIN and VALIDATION is 0 for `sequence_core`, 0 for
`cluster_id`, and 0 for `scientific_identity_id`.

## 8. Length summaries and histograms

Distinct-core lengths are the `biological_length` column of
`m3_tokenizer_audit.csv`. They match the M0 summaries. The frozen S6
short/long counts below are the recorded assignments in
`config/global_s7d_final_build.json`. This stage did not refit that
length model.

| Role | n | Minimum | Median | Mean | Maximum | Frozen short / long |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| TRAIN | 669 | 20 | 50 | 55.35276532137519 | 123 | 386 / 283 |
| VALIDATION | 95 | 20 | 49 | 54.72631578947368 | 94 | 55 / 40 |

Lengths inside the observed range that are absent below have count 0.

TRAIN histogram, length:count:

```text
20:12, 21:4, 22:5, 23:2, 24:3, 25:5, 26:2, 27:1, 28:4, 29:10,
30:33, 31:4, 32:5, 33:6, 34:11, 35:14, 36:16, 37:11, 38:20, 39:48,
40:54, 41:5, 42:13, 43:6, 44:4, 45:5, 46:3, 47:2, 48:5, 49:12,
50:28, 51:13, 52:1, 53:4, 54:9, 55:6, 56:10, 57:8, 58:1, 59:3,
60:6, 61:2, 62:4, 63:3, 64:4, 65:4, 66:1, 67:5, 68:6, 69:7,
70:9, 71:21, 72:5, 73:5, 74:6, 75:14, 76:4, 77:13, 78:6, 79:10,
80:22, 81:9, 82:6, 83:9, 84:5, 85:2, 86:5, 87:3, 88:2, 89:9,
90:7, 91:4, 92:7, 93:7, 95:4, 96:4, 97:2, 98:2, 99:4,
100:1, 104:2, 106:1, 107:1, 109:1, 112:1, 114:2, 116:1, 117:2, 123:1
```

VALIDATION histogram, length:count:

```text
20:2, 25:2, 29:2, 30:5, 31:1, 32:1, 33:2, 34:2, 35:2, 36:3,
37:3, 38:7, 39:3, 40:8, 42:2, 44:1, 47:1, 49:1, 50:2,
51:4, 54:1, 57:2, 58:2, 65:1, 68:2, 69:1, 70:1, 71:1,
73:1, 74:3, 75:2, 76:2, 77:2, 79:1, 80:4, 81:2, 85:2,
87:1, 89:2, 92:4, 93:2, 94:2
```

## 9. Approved chemistry policy

Retain every frozen core that is canonical A/C/G/U, including cores
whose metadata say 2F-RNA, mixed chemistry, a pipe-joined contributing
label, or nothing. Chemistry is report-only. It is not a tokenizer
input. The model must not be described as learning modified chemistry.
Empty chemistry stays missing. A distinct core whose identity rows do
not share one label stays conflicting, and every observed label is
kept. No model-compatible core is dropped for chemistry.

`2NH2-RNA`, `2OMe-RNA`, `DNA`, and `unknown` do not occur in
`chemistry` or `contributing_chemistries` in these two files.
`molecule_type` is TRAIN RNA 725 and `unknown` 1, and VALIDATION RNA
132. That column was not used as a chemistry label and was not passed
to the tokenizer.

## 10. Chemistry tables

Identity-row counts use one label per row. An empty cell is missing.
`2F-RNA|RNA` is one stored string, not two labels.

TRAIN identity rows (726):

| Label | `chemistry` | `contributing_chemistries` |
| --- | ---: | ---: |
| RNA | 605 | 622 |
| 2F-RNA | 48 | 70 |
| mixed | 5 | 5 |
| `2F-RNA\|RNA` | 0 | 2 |
| missing | 68 | 27 |
| Total | 726 | 726 |

VALIDATION identity rows (132):

| Label | `chemistry` | `contributing_chemistries` |
| --- | ---: | ---: |
| RNA | 114 | 120 |
| 2F-RNA | 6 | 10 |
| `2F-RNA\|RNA` | 0 | 1 |
| missing | 12 | 1 |
| Total | 132 | 132 |

Distinct-core categories are mutually exclusive and follow
first-occurrence order. A core with one observed label is unanimous.
A core with two or more observed labels is conflicting and is not also
counted under a unanimous label.

TRAIN distinct cores (669):

| Category | `chemistry` | `contributing_chemistries` |
| --- | ---: | ---: |
| unanimous RNA | 551 | 567 |
| unanimous 2F-RNA | 42 | 55 |
| unanimous mixed | 5 | 5 |
| unanimous `2F-RNA\|RNA` | 0 | 1 |
| unanimous missing | 46 | 21 |
| conflicting | 25 | 20 |
| Total | 669 | 669 |

VALIDATION distinct cores (95):

| Category | `chemistry` | `contributing_chemistries` |
| --- | ---: | ---: |
| unanimous RNA | 78 | 84 |
| unanimous 2F-RNA | 5 | 6 |
| unanimous missing | 1 | 0 |
| conflicting | 11 | 5 |
| Total | 95 | 95 |

Each conflicting record stores `frozen_index`, `sequence_core_sha256`,
the identity-row count, `observed_labels`, and per-label counts.
Missing is JSON `null`. The chemistry report is
`m3_chemistry_report.json`. `chemistry_was_tokenizer_input` is false.
The only tokenizer input field is `sequence_core`.

## 11. Mutually exclusive categories and the earlier union-style tables

The 28 September reconnaissance collapsed the labels of one core into
one composite key. Those keys also summed to 669 and 95, but a
multi-label core disappeared into a joined bucket. For TRAIN
`chemistry` the composite buckets were RNA only 551, empty only 46,
2F-RNA only 42, mixed only 5, and 25 conflicts split as empty+RNA 19,
2F-RNA+RNA 5, and empty+2F-RNA 1. For contributing chemistry the
composite union was RNA 571, 2F-RNA 56, empty 21, `2F-RNA|RNA` 16, and
mixed 5. Sixteen of those cores carried more than one contributing
label. VALIDATION contributing chemistry was reported as RNA 85,
2F-RNA 6, and `2F-RNA|RNA` 4.

The approved report does not use that composite axis. One core is
exactly one of unanimous missing, unanimous one present label, or
conflicting. The stored string `2F-RNA|RNA` is one label when every
identity row of that core has that same string. It is not, by itself,
a conflict. Disagreement across identity rows is the conflict. The
conflict row keeps every observed label, and the core is counted once.

An overlapping membership reading of the same cores, counting a
conflicting core under every observed label, produces column totals
694, 689, 106, and 100 for TRAIN `chemistry`, TRAIN
`contributing_chemistries`, VALIDATION `chemistry`, and VALIDATION
`contributing_chemistries`. Those totals exceed 669 and 95 by exactly
the conflicting-core counts 25, 20, 11, and 5. Every conflict here has
two labels. Those overlapping columns are not the modelling counts and
must not be added as if they partitioned the cores.

## 12. Loader and automatic-split trace

The biological entry point at RNAGenesis `112a120` is
`train_diffusion_mres.py`. This gate did not call it, so it did not
construct a DataLoader, shuffle, optimizer, EncDec, or denoiser.

The module states that it does not reuse the upstream 90/10 split,
T-to-U rewriting, or RNA-FM loader. `parse_args` (lines 878–899) takes
explicit `--train_data` (`corpus_final.txt`) and `--validation_data`
(`ft_validation.csv`). There is no `test_size`, `train_test_split`, or
90/10 flag on this entry point. `--fixture` disables frozen SHA-256
equality and is marked not for biological data. M3 did not pass it.

`run_training` (lines 918–926) reads TRAIN with `read_train_sequences`
and VALIDATION with `read_validation_cores`, then checks the frozen
669 and 95 counts when the hash guard is on. `read_train_sequences`
(lines 263–279) pins the file hash, splits on newline delimiters only,
rejects a non-canonical line, and refuses a repeated TRAIN line instead
of dropping it. `ft_train.csv` is not the fitting stream.
`read_validation_cores` (lines 282–319) keeps the first occurrence of
each `sequence_core` in file order. The function comment states that
this is the same rule that built `corpus_final.txt` and that it is not
a new split. Later identity rows are skipped only after the core has
already been retained. A missing core, a wrong `ft_split`, or a
non-canonical core raises.

The M3 gate repeated that grain independently. Corpus lines equalled
the 669 TRAIN first-occurrence cores, including order. The summary
records `automatic_or_random_split` as false.

## 13. VALIDATION grain and the 37-row duplicate audit

VALIDATION modelling grain is 95 first-occurrence cores from 132
identity rows. `95 + 37 = 132`. The same identity arithmetic holds for
TRAIN: `669 + 57 = 726`. Neither sum drops a row.

`m3_validation_duplicate_audit.csv` has 37 data rows, all with status
`REPEATED_IDENTITY_ACCOUNTED`. Columns are `csv_row_number`,
`first_occurrence_frozen_index`, `sequence_core_sha256`, and `status`.
CSV row numbers run from 27 through 133 and are not every integer in
that span. The 37 rows point at 27 of the 95 first-occurrence indexes.
No sequence text is in the file. The 57 TRAIN repeats are summary
counts only; they do not have a second duplicate CSV. That is an
accepted limitation in section 20, not an omitted modelling core.

## 14. Tokenizer implementation and vocabulary hashes

| Item | Value |
| --- | --- |
| Function | `models.autoencoder.encoder.biomap.rna_tokens.encode_rna_characters` |
| Interface | `encode_rna_characters` |
| Hugging Face `__call__` used | false |
| Implementation SHA-256 (`rna_tokens.py`) | `d43427bc695f21abd5ce529e4e91e349c1d18a5f951bb7978411d98d757a9b10` |
| Wrapper SHA-256 (`tokenization_xtrimopglm.py`) | `6a176d9f27d7f3650c1f3eb9728ae7bccbe008c432a80639f093382eb2d1d81e` |
| Vocabulary file | `models/autoencoder/encoder/biomap/tokenizer.model` |
| Vocabulary SHA-256 | `482251d7ac279f7a3f308b2f4356190742b2d065429502baa9015cb53a99365c` |

`encode_rna_characters` checks a nonempty canonical string and then
calls `tokenizer.convert_tokens_to_ids`. It does not strip, change
case, rewrite T to U, or accept an ambiguity code. The gate does not
construct EncDec or the denoiser. `load_tokenizer` reads the vocabulary
file as a tokenizer, not as a model checkpoint.

## 15. Nucleotide token mapping

| Character | Token id |
| --- | ---: |
| U | 1 |
| G | 2 |
| C | 3 |
| A | 4 |

Pad id is 0, the base-vocabulary index of `<pad>`. Allowed ids on a
modelling core are `{1, 2, 3, 4}` only.

## 16. Configured maximum length versus observed maxima

The pinned tokenizer’s configured maximum length is 2048. The observed
maximum biological length is 123 overall, 123 on the 669 TRAIN cores,
and 94 on the 95 VALIDATION cores. Every observed core is inside the
configured maximum. The gate does not truncate. A core longer than
2048 would still be tokenized in full and would still have to round-trip;
none occurred. Padding and collation are outside this tokenizer-only
gate.

## 17. Round trips and excluded ids

All 764 audit rows have status `PASS`. On every row, token length
equals biological length. Token ids are only 1, 2, 3, and 4. Mapping
ids back to characters is byte-identical to the original core. Pad,
special, and unknown ids are absent (`special_or_pad_or_unknown_ids_present`
is false).

Vocabulary size recorded from `len(all_tokens)` is 24. Excluded ids
are `0` and `5` through `27`. Ids `24`–`27` are Hugging Face
added-token ids beyond the 24-line `tokenizer.model` file. The audit
still accepts only ids 1–4. The audit columns are `role`,
`frozen_index`, `sequence_core_sha256`, `biological_length`,
`token_length`, and `status`.

## 18. Tests

The pinned interpreter is
`/home/laura/miniconda3/envs/rnagenesis-h200/bin/python` (Python 3.8).
`python -m pytest` failed because that environment has no `pytest`
module. That missing optional runner is not a scientific failure. The
same interpreter then ran the module with `unittest`.

Fifteen tests passed:

- accepted A/C/G/U mapping and byte-identical round trip;
- the general tokenizer call interface is not the production path;
- rejection of `T`, lowercase, whitespace, an empty string, and an
  ambiguity symbol, without delegating that input;
- hash mismatch;
- corpus/TRAIN order mismatch;
- a duplicate TRAIN corpus line;
- TRAIN/VALIDATION core overlap;
- cluster overlap;
- a wrong role label;
- retention of conflicting and missing chemistry;
- a pipe-separated chemistry string stays one label;
- an existing output directory is refused;
- restricted filenames are not opened;
- the gate does not import or construct EncDec or a denoiser;
- failure diagnostics omit sequence text.

The synthetic tests call the gate with `production=False`, so they do
not themselves exercise the pinned 669/95 counters or the repository
checks. The completed production summary records those checks as
passed.

## 19. Evidence artifacts

Directory, unchanged by this documentation stage:

`/home/laura/rnagenesis-mres-runs/m3_tokenizer_112a120_f2bdff1_attempt1`

| Artifact | SHA-256 |
| --- | --- |
| `m3_tokenizer_audit.csv` | `063a068187e5b34c598b1ef4a294f924f3167538aec824786d6e9fac01d4eb9f` |
| `m3_validation_duplicate_audit.csv` | `bfc966dbaff60523ebb44a75fa610f83f08724b0277ba4ed6c9b2a9956d39697` |
| `m3_chemistry_report.json` | `8192b0717a7d5791d06c842ea5ba07011a7502dd6c51a5da004e5ae84fedeb50` |
| `m3_summary.json` | `8862ecb066fac12ae80529737a2398322227f8789af07c2de2d375279896638c` |

`m3_summary.json` status is `PASS`. It embeds the three sibling hashes.
`summary_sha256_embedded` is false: the summary file does not contain
its own final hash. The separate code-review patch in that directory,
`m3_untracked_code_review.patch`, SHA-256
`1f722eaa852c74fe0cde0fa2a17ca39ff87ad4bdc731b0d6da49e92059beb835`,
1,281 lines, is not one of the four evidence artifacts and was not
modified here.

## 20. Reviewed acceptable limitations

The 29 September 2026 line-by-line review found no blocker and no
required correction. Acceptable limitations:

- `vocabulary_size` is 24, while `excluded_token_ids` also lists
  Hugging Face added-token ids 24–27, so the listed ids span 0–27.
  The audit still accepts only ids 1–4.
- `prohibited_actions`, the alphabet booleans, and
  `huggingface_call_interface_used` are constants written into the
  summary. The binding evidence is the call graph and
  `cuda_visible_devices: ""`.
- `opened_files` lists the four `read_regular_file` basenames and omits
  the tokenizer files, which are hashed in the tokenizer record.
- Assigning `tokenizer.__call__` on an instance does not intercept a
  real `tokenizer()` call, because Python resolves that through the
  class. The production path is `convert_tokens_to_ids`.
- Tests use `production=False`, so they do not exercise the pinned
  669/95 counters or the repository checks. The production summary
  records those checks as passed.
- A core longer than 2048 would be fully tokenized and reported. The
  observed maxima are 123 and 94.
- The 57 TRAIN repeats are summary counts, not a second duplicate CSV.

## 21. No model-compatible sequence was dropped

All 669 TRAIN cores and all 95 VALIDATION cores produced one passing
audit row. Token length equals biological length on every row. The 37
VALIDATION repeats and the 57 TRAIN repeats are accounted for on top of
those cores, not instead of them. Chemistry, including missing and
conflicting labels, did not remove a core. The gate fails closed on a
non-canonical core, a hash mismatch, an order mismatch, overlap, a role
mismatch, an unexpected token id, or a round-trip mismatch. No such
failure occurred on the frozen inputs.

## 22. Gate results

- Frozen-input and tokenizer/interface gate: **PASS**.
- Chemistry and no-silent-loss human gate: **PASS**.

## 23. Still unauthorized

M4, M5, model loading, GPU work, training, generation, checkpoint
selection, and REF/EVAL remain unauthorized. Physical GPU 0 may be
authorised for 29 September 2026, and that authorisation stays unused
for M3. Numerical diffusion-training smoke remains formal M5, after
formal M3 closure and M4.

## 24. Status

**COMPLETE / GO — 29 September 2026.**

On 29 September 2026, Laura Hardy gave final human approval. The
RNAGenesis implementation commit is
`e3b855bbf4d1af376f43747643fa30afd662828c` on
`mres-d1-diffusion-finetune`. M4 is the next formal milestone and has
not begun.
