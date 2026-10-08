# ARP-2B analysis contract

| Item | Value |
|---|---|
| Package | ARP-2B |
| Status | `draft` |
| Schema | `aptarank-tier1-arp2b-draft-r2` |
| Revision | ARP-2B revision 1 |
| Specification | `config/modelling/aptarank_tier1_analysis_spec.json` |
| Module | `scripts/modelling/aptarank_tier1_analysis.py` |
| Scorer | deployed AptaRank UI |
| `deployment_verified` | false |
| `eval_access` | locked |
| Governing plan | `docs/aptarank_full_mres_thesis_evaluation_plan.md`, version 3.0 |
| Governing-plan SHA-256 | `e6193d0d14245049c218b4da0ef8059fb63b2f31e4885b3457cd44e41b76c50c` |
| ARP-2A | `docs/aptarank_arp2a_tier1_reconciliation.md` |
| ARP-2A SHA-256 | `471bb5643650d3f23223ad6625afaeafe515e4beebc4814f262e263d9c18fab4` |
| Analysis-module SHA-256 | `ccc820bca63b9602c5df32e8ddfe117ce6ca61430c597cc6beb5f6db1c1fe99e` |
| Analysis-spec SHA-256 | `47e13c23e42f3dea625fdf67c050de83976bad958ad164ab2fae5e50e19c817b` |
| ARP-1 module | `scripts/modelling/aptarank_io_preflight.py` |
| ARP-1 module SHA-256 | `020ff616caade2983743eb941e7d4ce00d505f9bb349f10b428f98adb505263b` |
| ARP-1 specification | `config/modelling/aptarank_io_spec.json` |
| ARP-1 specification SHA-256 | `d32484b1dd0de0e344aa8cc5f5900fe1c184ab5261392f2dbfb941ba68d6d4a1` |

ARP-2A is unchanged. ARP-1 is unchanged and is imported for mechanical validation. This package does not adopt a provisional camera-ready formula.

The public analysis path calls the fully pinned loader on every call. That loader reads the on-disk specification and refuses a caller-supplied specification object or specification bytes. A private helper may receive a specification only when those bytes decode to that object, those bytes are the on-disk file, and the governing-plan, ARP-2A, ARP-2B module, ARP-1 module, and ARP-1 specification hashes match their files. The no-argument command prints the analysis-spec SHA-256 with the module, governing-plan, ARP-2A, and ARP-1 hashes.

"Normalization" in this package means one accounting disposition per expected candidate. It is not the AptaRank normalized-MFE component. The deployed UI remains the scorer. Local code does not recompute normalized MFE, ensemble defect, positional entropy, stem fraction, GC fraction, empirical REF calibration, the composite aptamer-likeness score, dinucleotide shuffles, or shuffle p-values.

This is not the full Tier 1 statistical analysis. `scientific_result` stays false. `aggregate_tier1_tier2_score` stays false. Binding, affinity, and selectivity are not interpreted. Uniform controls are a synthetic floor.

## Production constants

The specification records these design constants and does not enforce them on synthetic fixtures. Fixture counts are labelled `synthetic`.

| Constant | Value |
|---|---|
| REF calibration cores | 113 |
| EVAL cores | 154 |
| Blinded input rows before technical rejection | 308 |
| EVAL clusters before technical rejection | 79 |

## Private key

A synthetic private key is a JSON object with `fixture_role` `synthetic_private_key`, `count_label` `synthetic`, and `candidates`. Each candidate has exactly these fields:

- `candidate_id`
- `class_label`, exactly `real` or `uniform_control`
- `pair_id`
- `parent_core_id`
- `cluster_id`
- `length`

Identifier and length types are checked before any set, sort, or candidate-id lookup. Identifiers are nonempty strings in the ARP-1 opaque-id form. `length` is a positive JSON integer. Booleans and floats are rejected.

After the type gate:

- candidate ids are unique;
- every candidate belongs to one pair;
- each pair contains exactly two candidates;
- each pair contains exactly one `real` and one `uniform_control`;
- both members share `pair_id`, `parent_core_id`, `cluster_id`, and `length`;
- each `parent_core_id` belongs to exactly one `pair_id`.

The two members of one pair share one parent core. Distinct parent cores may share a cluster. One `parent_core_id` under two or more pair ids fails closed as `duplicate_parent_core_across_pairs`. The error may name the opaque parent-core id and must not include sequence text.

Members are grouped by `pair_id`. A mismatched `pair_id` is a different pair and fails the two-member rule. Joins never use row position.

## Reconciliation

Export CSV parsing, finite-score checks, sequence and length checks, and id reconciliation reuse ARP-1. ARP-2B does not duplicate those checks and does not weaken them. The expected id set is the private-key candidate set.

Every expected candidate has exactly one of:

- one validated exported score row; or
- one explicit technical-failure record with a nonempty reason.

The same id in both, in neither, duplicated, missing, or unexpected fails closed. Malformed identifier types fail closed. A silent sequence or length change fails closed. A non-finite score fails closed. Pair and key inconsistencies fail closed.

After ARP-1 has parsed the candidate upload and accepted its uppercase A/C/G/U alphabet, ARP-2B compares those exact canonical sequence strings. The same sequence under more than one candidate id fails closed as `duplicate_candidate_sequence`. Real/real, control/control, and real/control duplicates are all rejected. The error may name the opaque candidate ids and must not include the sequence. This check runs before the accounting report is built. It inspects only the supplied candidate upload. It does not compare an external known-core inventory, and it does not close `U23`.

A successful exported score of `0` is a numeric value. It stays in the evaluable group. A technical failure stays a missing technical outcome and is never stored as zero. Finite score tokens are preserved unchanged.

A nonempty collection of finite scores has a defined arithmetic mean. Each token is converted with `Decimal` and then `fractions.Fraction`. The sum is rational addition, so it does not depend on the active `Decimal` context and a repeating expansion does not make the mean undefined. The machine-readable mean carries:

- `exact_numerator` and `exact_denominator`, the reduced integer fraction;
- the original score tokens;
- `value`, a terminating decimal string, when that expansion is exact;
- `decimal_approximation` only for a repeating value, labelled with its precision and rounding.

`undefined` is true only for an empty collection, which keeps denominator zero and a null value. A defined rational mean is not labelled undefined. Terminating results such as `1.25` and `8.00` remain the same values.

## Report

A passing synthetic report states:

- input candidate count and input pair count;
- cluster count before technical rejection, taken from the private key;
- counts by `real` and `uniform_control`;
- exported evaluable count by group;
- technical-failure count by group;
- complete-pair count and incomplete-pair count;
- an explicit reason for each incomplete pair;
- the eligible paired-difference count;
- `real_minus_control` recorded for each internally constructed delta;
- the arithmetic mean of exported scores by group, as an exact rational with its denominator;
- null, denominator zero, and an undefined reason only where a group has no evaluable score;
- `join_uses_row_position: false`;
- `missing_results_are_zero: false`;
- `uniform_controls_are_synthetic_floor: true`;
- `deployment_verified: false`;
- `eval_access: locked`.

The paired difference is computed internally as real score minus control score. The report keeps the eligible count and the direction. It does not select or report a mean or median paired effect.

A surviving member of an incomplete pair remains in its group count and group mean. That pair does not contribute a paired difference.

The aggregate report contains no sequence strings and no candidate-level biological table. Synthetic diagnostics may name invented fixture ids and preserved score tokens.

An empty synthetic key, upload, export, and failure list returns genuine zero counts. Empty-group means are null with an undefined reason. Blocked statistics are not filled with zero.

## Blocked outputs

| Output | Blocking ids |
|---|---|
| Median and IQR | `U30` |
| Aggregate paired-effect functional and confidence interval | `U31` |
| AUROC | `U29`, `U32` |
| Shuffle-pass rates or interpretation | `U19`, `U21`, `U33` |
| Secondary paired test | `U34` |
| Bootstrap intervals | `U35`, `U36`, `U37`, `U38` |
| Component table not supplied by a verified deployment | `U1` through `U11` |
| Local recomputation of scorer internals | `U1` through `U21` |
| Uniform-control generation | `U22`, `U23`, `U24` |
| Opaque production ids | `U25`, `U26` |
| Full-ranking schema | `U27`, `U28`, `U29` |

Unresolved ids `U1` through `U38` stay unresolved. A request to recompute a component, the composite, or a shuffle fails closed.

## Data firewall

The no-argument command runs the bundled synthetic demonstration and rejects every argument, including paths, protected role names, and an EVAL unlock. The demonstration uses only synthetic fixtures and loads no EVAL, REF, VALIDATION, TRAIN, production pool, or checkpoint.

Synthetic fixtures live under `tests/modelling/fixtures/aptarank_arp2/`. Invented ids and synthetic A/C/G/U sequences only. Existing ARP-1 synthetic fixtures remain available to ARP-1 and are not modified.
