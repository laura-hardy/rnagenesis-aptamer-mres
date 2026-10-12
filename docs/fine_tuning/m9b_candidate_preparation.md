# M9B-2 synthetic candidate preparation

| Item | Value |
|---|---|
| Status | `DEFINED_SYNTHETIC_ONLY_PRODUCTION_INPUTS_UNOPENED` |
| Stage | M9B-2, synthetic fixtures only |
| Contract | `config/modelling/aptarank_candidate_preparation_contract.json`, SHA-256 `99c0ff690f716e6b4560a22d04d9a968e7f039288454cc3669c89a1beb65f3b9` |
| Plan | `docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md`, version 3.3, SHA-256 `b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe` |
| Evidence contract | `config/modelling/aptarank_evidence_contract.json`, SHA-256 `0494ea740b1a2402032bfa695c23a422b142cda6a2bc043d1da87dbb9ddb092b` |
| Production sample | Not chosen. The caller must later supply 200, 150, or 100. |

M9B-2 prepares candidate-upload bytes from in-memory membership records or caller-supplied JSONL bytes. It does not open TRAIN, VALIDATION, REF, EVAL, or a production sequence ledger. It does not choose the production membership count, embed a production blinding key, or call AptaRank. No detail below is a scientific result.

## Reused pins

The preparation contract fails closed unless these files match the recorded digests. Parsing and candidate-upload checks are the existing validators, not a second CSV implementation.

| Role | Path | SHA-256 |
|---|---|---|
| ARP-1 specification | `config/modelling/aptarank_io_spec.json` | `46ba6c8be873dad4c086e9f6b889b51702ba31212fa502d00f26e267a22da732` |
| ARP-1 module | `scripts/modelling/aptarank_io_preflight.py` | `eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01` |
| M9B-1 evidence module | `scripts/modelling/aptarank_evidence_contract.py` | `08e780e03108c0008174a4559840ce59a56d567b99376d3ad0272eb29a69bbcb` |

Candidate upload columns stay `id,sequence`. Sequence text must already be canonical uppercase A, C, G, and U. Silent case or T-to-U normalisation is not applied. Technical eligibility is the pinned evidence bound of length 20 through 100 inclusive.

## Input contract

One input row is one within-condition distinct eligible sequence membership. The record keys are `condition`, `source_identity`, `sequence`, `length`, and `provenance`.

- Condition is exactly one of B0, B1, B2, and D1.
- Length must equal the sequence length and sit inside 20–100.
- Source identity is unique across the supplied records.
- A repeated `(condition, sequence)` membership fails closed. It is not silently dropped.

Provenance follows the recorded condition roles:

- B0 keeps `b0_seed` as a chunk seed. It has no training-seed field and no empirical-null seed.
- B1 keeps the M8 provenance fields and a null `d1_training_seed`.
- B2 keeps `empirical_null_seed`. That seed is not a training seed, and the training-seed field is absent.
- D1 training seed is exactly 43 with technical block A, or 44 with technical block B.

JSONL bytes are split with the existing record splitter. A filesystem path is refused. There is no sealed production entry point.

## Sampling

Sampling is score-blind and platform-independent. The priority is SHA-256 over a length-delimited UTF-8 concatenation of:

1. domain separator `m9b2-candidate-sample-v1`
2. fixed sampling seed `m9b2-fixed-sampling-seed-v1`
3. condition
4. stable source identity
5. canonical sequence

Each component is a 4-byte big-endian length followed by its UTF-8 bytes. The lowest digest is taken first. Ties break by ascending UTF-8 source identity, then ascending UTF-8 sequence. The construction does not use Python's hash randomisation, filesystem order, input order, or a library PRNG.

The caller supplies one membership count: 200, 150, or 100. The same count is required for every condition. Any other count is rejected. If a condition has fewer eligible memberships than requested, preparation fails with an exact shortage report and does not replenish from later scores.

D1 is balanced by the recorded training seeds. The selected counts are 100 and 100 at 200, 75 and 75 at 150, and 50 and 50 at 100. A short seed fails closed. The other seed does not fill the gap. Equal-seed weighting is not applied.

B0 remains the external baseline, B1 and D1 the primary causal comparison, and B2 the secondary data-scale comparator. Those labels are stored on the private membership rows. They are not written into candidate ids.

## Upload grouping

After the four conditions are sampled independently, a sequence selected in more than one condition is written once in the candidate upload. Every selected condition membership remains in the private key. Later denominators stay at membership grain. The upload stays at globally distinct sequence grain.

This grouping is upload integrity for the one-row-per-sequence candidate file. The manifest records the requested count, the selected count, the upload-row count, and the two D1 seed counts. It does not record a pair table, a shared-sequence count, or any other cross-condition metric.

## Opaque ids

The caller supplies a 32-byte blinding key. The id is HMAC-SHA-256 over the length-delimited domain separator `m9b2-candidate-id-v1` and the canonical sequence. The key is not part of the preimage. The digest is truncated to 16 bytes and written as `cand_` plus 32 lowercase hex characters. That form matches the ARP-1 nonempty opaque-id rule.

A truncated collision fails closed. The id is not lengthened and the row is not renamed. The same selected sequence receives one id in every condition. Changing the key changes ids and leaves the sampled memberships unchanged. Tests use labelled test-only keys. No production key is stored in the contract, module, tests, or this note.

## Outputs

Preparation returns bytes only. It does not write a production directory.

| Output | Grain | Contents |
|---|---|---|
| `candidate_upload.csv` | Distinct selected sequence | Header exactly `id,sequence`. The canonical sequence is unchanged. |
| `private_membership_key.jsonl` | Selected condition membership | Candidate id, condition, comparison role, source identity, length, and the applicable provenance. No invented field and no sequence string. |
| `preparation_manifest.json` | One preparation | Contract, specification, and module hashes; requested and selected membership counts; upload-row count; D1 seed counts; upload and private-key hashes; synthetic status. |

The manifest does not contain its own hash, sequence strings, source identifiers, candidate identifiers, or the HMAC key. Its hash is computed from the returned bytes.

`publish_directory` is a generic writer. The destination must not already exist. A file, an existing directory, or a symlink is refused, as is a destination under a directory named `results`. Bytes are written to a temporary sibling, read back, and checked against the expected hashes. One rename promotes the directory. A failed attempt deletes the temporary sibling. M9B-2 does not add a production locator or a production runner. The no-argument command only checks pins and prints the status.

## Boundary

This stage did not open TRAIN, VALIDATION, REF, EVAL, or a production sequence ledger. It did not inspect generated production sequences, calculate overlap, leakage, or nearest-TRAIN results, reproduce Tier 1 or Tier 2 scoring, or run AptaRank. No production sample, blinding key, upload, or private key was instantiated. Nothing was written under `results/`.
