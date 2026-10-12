# M9 parser contract

**Status: `M9_PARSER_IMPLEMENTED_SYNTHETIC_ONLY_NOT_AUTHORISED_FOR_PRODUCTION`.**

This stage freezes parsing and source identity for B0, B1, B2, and D1. It does not compute scientific results. Production execution is unauthorised. Production derived-ledger creation is unauthorised. A synthetic fixture run is not production validation.

The contract files are:

- `config/modelling/generator_eval_parser_contract.json` (`generator-eval-parser-contract-m9-r2`)
- `config/modelling/generator_eval_source_manifest.json`

The source adapter revision is `m9-source-adapter-v2`. The biological parser remains `m9-biological-parser-v1`.

## Contract revision r2

`generator-eval-parser-contract-m9-r2` supersedes the pre-production r1 adapter. r1 incorrectly rejected the literal `/` separators in the required preserved M8 provenance field `source_raw_file_relative_path`. This changes provenance-field acceptance only. It does not change biological parsing, filtering, source identity, or the sealed inputs.

That field is preserved M8 provenance, not a filesystem argument. A dedicated lexical validator accepts the tracked writer form and returns the supplied string unchanged:

`raw/invocation_{invocation_index:04d}/seqs_wo_guidance_top_p=0.95_2_{line_count}_m8_i{invocation_index:04d}_seed{generation_seed}_len{requested_biological_length}.txt`

The invocation index in the folder and the filename is the same `{:04d}` value. `line_count`, `generation_seed`, and `requested_biological_length` are canonical decimal integers. The validator rejects an empty string, control characters, an absolute path, empty, `.`, and `..` components, backslashes, other platform path syntax, and a prefix other than `raw/`. It does not resolve, join, open, stat, or dereference the string, and it does not use the string to choose an input. Actual input access comes only from the frozen source manifest. Other token fields remain on the slash-free validator.

The in-memory implementation is:

- `scripts/modelling/generator_eval_parser.py`
- `scripts/modelling/generator_eval_source_adapters.py`
- `scripts/modelling/generator_eval_derived_ledger.py`

Public functions accept in-memory source bytes. They do not accept filesystem paths or open files. Decoded objects cannot verify the original source bytes, so they are refused and are not a production entry point.

## Pinned cleaner

On valid UTF-8 records, splitting, boundary removal, and validity classification reproduce the pinned RNAGenesis cleaner `scripts/audit_generation_output.py`.

| Pin | Value |
| --- | --- |
| RNAGenesis commit | `e3b855bbf4d1af376f43747643fa30afd662828c` |
| Cleaner introducing commit | `112a120282667c382790031fe74942f89f7b84eb` |
| Cleaner Git blob | `3480af2dd758f4824655b3f7c8a5276214a61682` |
| Cleaner file SHA-256 | `4d0c56a7d931a2c3c5c049cfeabd4937134b3d1125ef7a68b10472527d2fd2a2` |

`split_raw_records` and `strip_boundary_markers` are the local reproduction. On valid UTF-8 records they follow the pinned cleaner: LF splits records, a trailing newline does not add a record, an internal empty record is kept, an empty file has zero records, and a file whose only character is a newline has one empty record. A carriage return is removed only as the partner of a CRLF delimiter.

The leading run of `1` and `2` is removed first. The trailing run is removed only from what remains, so the two removals do not overlap. A marker-only string is entirely the removed prefix, with an empty suffix. Internal characters stay as they are. There is no uppercasing, whitespace stripping, T-to-U conversion, repair, truncation, padding, deduplication, replacement, replenishment, or silent drop.

## UTF-8 extension

On valid UTF-8 records, splitting, boundary removal, and validity classification reproduce the pinned RNAGenesis cleaner.

The M9 source-adapter layer deliberately extends failure accounting by allowing a uniquely identifiable undecodable record to be represented as `unparseable_output`. For B0, byte-level LF boundaries plus explicit chunk metadata establish seed and line identity before record decoding, so one undecodable B0 record can become one `unparseable_output` row.

This is not a change to boundary removal or biological validity. It is not permission to continue after a source-hash failure or loss of attempt identity. It is not a claim of byte-for-byte behavioural identity with the pinned cleaner for whole-file UTF-8 failure. The pinned cleaner fails the whole file when UTF-8 decoding fails.

The sealed source artifacts are expected to pass their source-integrity gates. This branch has not run production parsing.

## Outcomes

The same biological parser runs after source adaptation for every condition.

| Outcome | Parsed sequence | Failure reason |
| --- | --- | --- |
| `valid_canonical_sequence` | retained body matching `^[ACGU]+$` | null |
| `empty_output` | null | `empty_output` |
| `parsed_non_acgu` | retained non-ACGU body | `parsed_non_acgu` |
| `non_sequence_output` | null | `non_sequence_output` |
| `unparseable_output` | null | `unparseable_output` |

A nonempty canonical body is valid. An empty body after boundary removal is `empty_output`. A decoded non-string payload is `non_sequence_output`. `unparseable_output` is permitted only when a unique source attempt is already established and the attempt payload itself cannot be decoded or interpreted. Boundary-marker text is not classified before the leading and trailing runs are removed.

Successfully parsed outputs are the valid canonical rows plus the parsed non-ACGU rows.

## Source integrity

Every bytes-based adapter computes SHA-256 from the exact supplied source bytes and compares that digest with the caller-supplied expected hash before trusted parsing. A mismatch fails closed. A malformed expected hash fails closed. Derived rows carry the recomputed digest. An arbitrary caller-supplied hash is not copied onto a derived row.

## Source-container failure and biological outcome

Source-container integrity and biological-output classification are different layers.

A source hash mismatch, a JSONL structural failure, a missing required identity field, a duplicate source identity, or corruption that prevents reliable attempt identity is a source-level hard failure. The adapter does not invent a B1 or D1 `record_id` when it cannot be recovered. It does not invent a B2 attempt index when it cannot be recovered. Malformed JSON that prevents recovery of the required record identity fails the source rather than emitting a fabricated derived row.

For schema-valid B1, D1, and B2 records, a null or otherwise uninterpretable payload field may become an accounted outcome only when the record identity and all required provenance remain valid.

## Source adapters

B0 takes newline-delimited bytes plus synthetic chunk metadata. The stable id is `b0:seed:{seed}:line:{one_based_line_number}`. Seed, line number, chunk id, and the recomputed source-artifact SHA-256 are preserved. Biological requested length is unavailable. Nominal `max_seq_len=37` is stored as the nominal sampler setting and is not converted into a requested biological length. Production order is later seeds 4201–4210. This stage does not require those seeds. B0 remains an external comparator.

B1 and D1 take in-memory JSONL bytes matching the M8 raw-attempt schema. `raw_decoded_text` is parsed with the common parser only after the source hash matches and the record identity and required provenance are valid. The existing `record_id` is preserved. It is not invented. Master attempt index, generation seed, invocation index, requested biological length, maximum sequence length, technical block, checkpoint identity, source hashes, and `source_raw_file_relative_path` are preserved. The relative path is accepted only in the tracked M8 writer form described above and is copied exactly. `d1_training_seed` is null for B1 and an integer for D1. Equal-seed weighting is not applied. D1 seed counts are observed source allocation only.

B2 takes in-memory JSONL bytes matching the B2 field set. `sequence` is parsed with the common parser and validity is recomputed. `valid_acgu` is retained as a source claim and is not the validity authority. The stable id is `b2:attempt:{attempt_index_as_five_digits}`, formed only from a recovered attempt index. `attempt_index`, sampled length, sequence hash, and seed are preserved. The B2 `seed` is the empirical-null seed, not a training seed. Seed 42 is the verified production value in the source manifest. It is not a general parser rule.

## Source manifest

`generator_eval_source_manifest.json` is schema `generator-eval-source-manifest-m9-r1`. Its status is `FROZEN_SOURCE_IDENTITY_CONTRACT_NOT_EVIDENCE_OF_PRODUCTION_PARSING`.

Logical artifact ids and SHA-256 values identify the sources. A filesystem path is not part of that identity. The manifest records the verified B0, B1, B2, D1, M7 selected-set, and seed-43/seed-44 weight hashes already published in the M8, M7, M2, and B2 documents. It does not reopen those files.

M7 diagnostic and guardrail samples, and the M4 and M7 1,000-attempt pools, are excluded by declared lineage and directory identity. They are not excluded by comparing sequences. Replacement, replenishment, filtering, deduplication, dropping, and source rewriting are prohibited. REF and EVAL are not inputs.

## Derived ledger

Construction keeps one row per source attempt, in source order, with no silent renumbering. Canonical bytes are JSONL in the frozen field order, with compact separators and a final LF after every row, including the last. The derived-ledger SHA-256 is the SHA-256 of those bytes. The first construction does not require a derived hash. Replay with an expected hash fails closed on mismatch.

The sequence-free accounting projection reports raw attempts, valid canonical sequences, empty outputs, unparseable outputs, non-sequence outputs, parsed non-ACGU outputs, successfully parsed outputs, unique valid sequences, duplicate excess, failure-reason counts, and observed D1 counts by training seed. It does not contain sequence strings. It does not compute TRAIN novelty, EVAL closeness, structure, clustering, AptaRank, or statistical inference.

## Firewall

The implementation refuses filesystem path arguments, the role names `TRAIN`, `VALIDATION`, `REF`, and `EVAL`, the basenames `corpus_final.txt`, `ft_train.csv`, `ft_validation.csv`, `ref.csv`, and `eval.csv`, production run-root paths, an EVAL unlock, and any request to replenish, filter, deduplicate, or drop rows.
