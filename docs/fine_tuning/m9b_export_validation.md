# M9B-3 synthetic downloaded-export validation

| Item | Value |
|---|---|
| Status | `DEFINED_SYNTHETIC_ONLY_EXPORT_BEHAVIOR_UNRESOLVED` |
| Stage | M9B-3, caller-supplied bytes and synthetic fixtures only |
| Contract | `config/modelling/aptarank_export_validation_contract.json`, SHA-256 `91c318459789bb95eeca169cc398941b71b2f73856a416ea308142ebffd43a1f` |
| Plan | `docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md`, version 3.3, SHA-256 `b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe` |
| Evidence contract | `config/modelling/aptarank_evidence_contract.json`, SHA-256 `0494ea740b1a2402032bfa695c23a422b142cda6a2bc043d1da87dbb9ddb092b` |
| Preparation contract | `config/modelling/aptarank_candidate_preparation_contract.json`, SHA-256 `3bcfbdf14cd7e777a0b2746f91d0335ba4876195f5012610157e5aa23e083096` |
| Live export | Unresolved until M9C. `live_export_behavior` stays unresolved. |

M9B-3 checks a downloaded shortlist against the upload and the private membership key. Inputs are bytes supplied by the caller. A filesystem path is refused. No detail below is a scientific result, a deployment verification, or an AptaRank score.

## Reused pins

The export contract fails closed unless these files match the recorded digests. CSV parsing, opaque-id shape, the finite-decimal check, and id-keyed sequence comparison are the existing ARP-1 helpers. Private-key fields and JSONL splitting are the corrected M9B-2 contract and the existing record splitter. Public column order and export tokens are the M9B-1 facts.

| Role | Path | SHA-256 |
|---|---|---|
| M9B-1 evidence module | `scripts/modelling/aptarank_evidence_contract.py` | `08e780e03108c0008174a4559840ce59a56d567b99376d3ad0272eb29a69bbcb` |
| M9B-2 preparation module | `scripts/modelling/aptarank_candidate_preparation.py` | `a4f5b047f2803e775d9521c226287487412495055446e192681957c3d42879ca` |
| ARP-1 module | `scripts/modelling/aptarank_io_preflight.py` | `eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01` |
| Record splitter | `scripts/modelling/generator_eval_parser.py` | `4a59ff8e557ee1948410c7f705a9c3772fe2570d4255b0d2185acee99137eaa2` |

The public shortlist header is `rank`, `candidate`, `aptamer-likeness`, `compatibility`, `shuffle`, `len`, `sequence`. A different name, order, or membership fails closed. Compatibility tokens are `strong`, `moderate`, `weak`, and the two-word literal `not evaluated`. Shuffle tokens are `pass`, `fail`, and U+2014. That public set is wider than ARP-1's target-free profile. No profile is inferred from the file.

## Join

Rows join on the opaque candidate id. The export column is `candidate`, the upload column is `id`, and the private-key field is `candidate_id`. Row position is not a key. Sequence text is not a key. An id that is well formed but absent from the upload is unknown, including when its sequence text belongs to another uploaded id.

The exported sequence must be character-for-character the sequence stored for that same id. A sequence that belongs to a different uploaded id is substitution. Any other difference is a mismatch. Case and T are not rewritten.

Every private-key membership for that id is kept, including two conditions that selected one uploaded sequence. Memberships are emitted in condition order B0, B1, B2, D1. Source occurrences stay in the supplied order. The private key still does not carry a sequence. Declared multiplicity must equal the number of source occurrences. Comparison roles stay the recorded condition roles.

## Fields that are checked and not recomputed

- Rank is a positive integer without a leading zero. Across the exported rows it is the consecutive 1-based ordinal of descending exported aptamer-likeness, with ties broken by ascending candidate id. It is not the statistical minimum rank used inside the empirical CDF. The number in the likeness cell is parsed only to order those rows. It is not a new Tier 1 score.
- Aptamer-likeness must be a finite decimal token. The original token is copied into the joined row. Non-finite tokens are rejected. No threshold is applied.
- Compatibility and shuffle must be exact public tokens. They are not interpreted.
- `len` must be a nonnegative integer and must equal the character length of the exported sequence. After the sequences match, that length is also the uploaded length and every private-key length for the id.

Component scores, shuffle p-values, raw Tier 2 disagreement, and control percentiles are absent from this schema. They are not reconstructed.

## Missing and rejected rows

The caller supplies `require_complete` or `allow_partial`. There is no default. Deployed downloads may omit rows, and M9B-1 leaves that behavior unresolved until M9C.

| Policy | Absence from the export |
|---|---|
| `require_complete` | Fails closed as `missing` when the id also has no caller-supplied rejection. |
| `allow_partial` | Records the id as `missing` and still returns the other rows. |

A missing row has no rank, likeness, compatibility, or shuffle. Those cells are null. They are not stored as zero, and no rejection reason is written.

A row is `rejected` only when the caller supplies a JSONL rejection record with that id and a nonempty reason. The reason is copied. A blank reason fails closed and is not replaced. An id cannot be both exported and rejected. An unknown rejection id fails closed.

## Outputs

The validator returns bytes. It does not write a production directory. The no-argument command only checks pins and prints the status.

| Output | Contents |
|---|---|
| `joined_candidates.jsonl` | One restricted row per uploaded id. Sequence, length, memberships, and, when exported, the original rank, likeness token, compatibility, and shuffle. Order is exported rank, then missing ids, then rejected ids. |
| `validation_manifest.json` | Sequence-free counts, the caller policy, input and joined hashes, and the pins. No candidate id, source id, sequence, exported score, rejection text, or overlap metric. The manifest does not contain its own hash. |

Joined bytes are analysis-ready and restricted because they contain sequences. The manifest is the sequence-free record.

## Boundary

This stage did not open TRAIN, VALIDATION, REF, EVAL, a production sequence ledger, a production upload, or a real AptaRank download. It did not call the AptaRank UI or API, modify or reproduce AptaRank, or write under `results/`. It did not calculate overlap, leakage, nearest-TRAIN distance, a biological summary, or a Tier 1 or Tier 2 score. No production export was instantiated.
