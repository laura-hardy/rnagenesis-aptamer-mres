# Global S7B — deterministic whole-cluster FT/REF/EVAL assignment and freeze

```text
S7B preview                         = yes (preserved)
S7B preview approved                = 2026-09-21
S7B authoritative assignment applied = this milestone
REF frozen                          = this milestone
EVAL frozen                         = this milestone
S7C not started                     = STOP
FT train/validation not created     = STOP
```

```text
frozen S7A corpus_post_cap.csv
        ->
same build_cluster_features(...)
        ->
same select_preview_assignment(...) / optimise_partition(...)
        ->
compare with approved preview (parity only)
        ->
authoritative partitioned corpus under
  data/interim/s7b_partition/
        ->
REF frozen, EVAL frozen
        ->
STOP. No FT train/val. No corpus_final. No S7C.
```

## Frozen S7A input

```text
data/interim/s7a_target_cap/corpus_post_cap.csv
SHA256 = 6bbf040af6f1c541001a6a6ee4c461539f554737158ff11598aa93e4f137f9cd

identities = 1173
distinct sequence_core = 1036
clusters = 794
canonical targets = 411
partition nonblank = 0
E5 = 0
target_type != protein = 0
```

Every identity has one retained frozen S5 `cluster_id`. Each
`sequence_core` maps to exactly one cluster. S5 clustering is not
re-run. `cluster_id` is the leakage boundary.

S7A was not regenerated. S5/S6 were not mutated.

## Authority

1. `docs/data_curation/checkpoint3_supervisor_decisions_2026-09-21.md` (C3-02)
2. Governing plan v1.5 §1.1
3. Frozen S7A post-cap corpus and frozen S6 GMM artefacts
4. `config/global_s7b_partition.json`
5. Human approval of the reviewed dry-run:
   `config/checkpoint_reviews/s7b_partition_approval.json`
6. Freeze authority after application:
   `config/checkpoint_reviews/s7b_partition_freeze.json`

The approval artefact is an audit / post-derivation parity record only.
Scientific assignment does **not** read partition labels from it and does
not copy `cluster_partition_preview.csv`. The assignment is rederived
from frozen S7A input with the same tested optimiser used for the
preview, then compared.

## Feature grains

| Criterion | Grain | Notes |
| --- | --- | --- |
| canonical target | identity | each of the 1,173 scientific identities contributes once; multi-target cores are not collapsed |
| evidence | identity | E2 / E3 / E4 only; E5 cannot be introduced |
| source | identity-grain `source_db` | `contributing_sources` is not expanded |
| length regime | distinct `sequence_core` | frozen S6 short/long; a multi-target core counts once |
| target family | identity | **secondary diagnostic only; not in the primary objective** |

A cluster is indivisible. Multi-target and multi-source clusters contribute
their full category-count vectors.

## Frozen S6 length-regime provenance

The two S6 sequence-length regimes (component means ≈ 38.9 nt and ≈ 77.4 nt)
are reused from frozen S6 `bimodality.json` `gmm_2`. Assignment uses S6
`gmm_posterior_assignment` (`gmm_k2_maximum_posterior`). Component 0 is
short; exact posterior ties go short.

Post-cap distinct-core labels on the retained 1,036 cores:

```text
short cores = 595
long cores = 441
```

The two-component GMM is **not** refit on the post-cap corpus. No median
split and no new threshold are used.

## Integer cluster quotas

Desired fractions are FT = 0.80, REF = 0.10, EVAL = 0.10 of **cluster
count**, with `n_FT + n_REF + n_EVAL = 794`. Quotas are by cluster count,
not identity count.

Tied-optimal integer candidates for N = 794:

```text
(n_FT, n_REF, n_EVAL) = (635, 79, 80) and (635, 80, 79)
```

The scientific objective selected `(635, 80, 79)`.

Because quotas are cluster-count quotas, EVAL contains 13.98% of
identities despite 9.95% of clusters. REF contains 9.72% of identities
at 10.08% of clusters. This is a consequence of the approved
identity-weighted target-distribution objective and whole-cluster
constraints, not leakage.

## Divergence and weight-free objective

This assignment is the **approved deterministic operationalisation** of
CHECKPOINT-3 C3-02. It is not claimed to be a mathematically unique or
globally optimal solution of the combinatorial partition.

Jensen–Shannon divergence is used with **log base 2** (bits, bounded by 1)
throughout. Each partition distribution is compared to the **full post-cap
global** distribution on the complete category support.

```text
J_c(p)  = JSD_2( partition_p  ||  global )   c ∈ {target, evidence, length, source}
D_c     = max_p J_c(p)
O1      = max(D_target, D_evidence, D_length, D_source)
O2      = lexicographic minimum of (D_target, D_evidence, D_length, D_source)
          sorted descending
O3      = D_target + D_evidence + D_length + D_source
```

Final scientific tie-break: stable assignment signature
`cluster_id:label` joined in sorted `cluster_id` order.

```text
comparison tuple =
  (O1, descending D vector, O3, assignment_signature)

arbitrary manually chosen criterion weights = none
target_family in primary objective = no
```

Target JSD dominates the minimax objective because the 411-target long
tail is much harder to reproduce than evidence or two-regime length
distributions. Source, evidence and length diagnostics were reviewed and
accepted before freeze.

## Deterministic heuristic

The same functions used for the reviewed preview are used for
authoritative application:

1. `build_cluster_features`
2. `derive_integer_quotas`
3. `select_preview_assignment` → `optimise_partition`
   (greedy feasible placement, then deterministic pairwise swaps)

No second apply-only splitter exists. Cluster IDs are not hard-coded
into the optimiser.

## Rare targets

Many of the 411 targets are singletons. It is not required — and generally
impossible under whole-cluster constraints — that every target appear in
FT, REF and EVAL. Singleton absence from a partition is a coverage
limitation, not leakage.

REF contains zero globally singleton-target identities, but still
represents 88 canonical targets across 114 identities. No additional
singleton-target balancing constraint was introduced.

## Preview versus application

The reviewed preview remains frozen under:

- `data/interim/s7b_partition_preview/`

Application writes a distinct authoritative tree under ignored `data/`:

- `data/interim/s7b_partition/corpus_partitioned.csv`
- `data/interim/s7b_partition/cluster_partition_assignment.csv`
- `data/interim/s7b_partition/ft.csv`
- `data/interim/s7b_partition/ref.csv`
- `data/interim/s7b_partition/eval.csv`
- `data/interim/s7b_partition/partition_identity_summary.csv`
- `data/interim/s7b_partition/partition_core_summary.csv`
- `data/interim/s7b_partition/partition_target_distribution.csv`
- `data/interim/s7b_partition/partition_evidence_distribution.csv`
- `data/interim/s7b_partition/partition_length_regime_distribution.csv`
- `data/interim/s7b_partition/partition_source_distribution.csv`
- `data/interim/s7b_partition/partition_target_family_diagnostic.csv`
- `data/interim/s7b_partition/partition_divergence_metrics.csv`
- `data/interim/s7b_partition/s7b_partition_report.md`
- `data/interim/s7b_partition/s7b_partition_manifest.json`

`corpus_partitioned.csv` contains every frozen S7A identity in source
row order. The only intended scientific field change is `partition`
populated with exactly one of `FT` / `REF` / `EVAL`. Clusters are not
renumbered. Representative status, targets, evidence, sequences and
source/provenance are unchanged.

`ft.csv` / `ref.csv` / `eval.csv` are exact row subsets of
`corpus_partitioned.csv` with the same column order.

The reviewed preview is not overwritten. `corpus_final.csv` /
`corpus_final.txt` are not written.

## Command

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/data_preparation/s7_partition.py \
  --config config/global_s7b_partition.json
```

Mode is `apply`. Preview artefacts and the approval record are read for
parity only.

## Authoritative sizes

| partition | clusters | identities | cores | targets represented |
| --- | --- | --- | --- | --- |
| FT | 635 | 895 | 795 | 390 |
| REF | 80 | 114 | 103 | 88 |
| EVAL | 79 | 164 | 138 | 111 |

Primary divergences (JSD, log2 bits; full stored preview precision):

```text
D_target   = 0.2694536956975229
D_evidence = 8.629690438492248e-05
D_length   = 0.001660102797405985
D_source   = 0.01954623798492084
O1 = 0.2694536956975229
O3 = 0.29074633338423467
```

## REF / EVAL independence rule

After this freeze:

- no cluster may be moved between FT/REF/EVAL to improve model results
- no REF or EVAL identity may be added or removed because of fine-tuning performance
- no hyperparameter or model-selection result may alter REF/EVAL
- any later legitimate scientific correction requires a documented **split revision**, new hashes, and explicit human approval
- S7C operates only inside FT

Do not perform a revision now. The tracked freeze record is the
authority for future checks that REF/EVAL have not changed.

## Tests

Synthetic tests in `tests/data_preparation/test_s7_partition.py` cover
cluster integrity, grains, quota derivation including tied REF/EVAL,
JSD support, the objective hierarchy, greedy capacity, local-search
rules, row-order independence, sequence-free preview metadata, intact
S5E/S6/S7A interfaces, and the application/freeze path (approval is
audit-only, preview directory is not overwritten, retained fields other
than `partition` are preserved, REF/EVAL freeze metadata is written).

## Scientific boundary

```text
S7B deterministic assignment implementation = yes
S7B dry-run/preview                         = yes
S7B preview approved                        = yes
authoritative partitioned corpus            = yes
REF frozen                                  = yes
EVAL frozen                                 = yes
FT assigned                                 = yes
FT train/validation split                   = no
S7C started                                 = no
model fine-tuning started                   = no
REF calibration started                     = no
EVAL model evaluation started               = no
```

The next milestone is S7C (FT train/validation only) and requires a
separate planning/review gate.

## Authoritative hashes (2026-09-21 freeze)

Reviewed preview (preserved, not overwritten):

```text
cluster_partition_preview.csv
  5e74ec91469fd33309d0bd1034866a6d752316b10e89a2dafecaab7c5f4402b1
s7b_partition_preview_manifest.json
  e07e7674f53b46733c8bfe3eca8213ac81a9fd0153ac6dc0ff283c5665dc6a17
```

Authoritative scientific payloads:

```text
corpus_partitioned.csv
  755e6afaf6a522be390073d3651311f8afc0ca9486322ac3bbfe348cd2a3fb1a
cluster_partition_assignment.csv
  6278d42a067e741b0f057169a862112351f8f183da49103952074f6f65376072
ft.csv
  b680ace037be73f650e386a34d97db915e4925a2dcd59e3053b7542b6d6fb4ff
ref.csv
  6c8bf5cdec625bdddb9f42b18a15f435826bebabb119dfc268ff737c89b7408d
eval.csv
  88fe1d8c2c78ed9dc478306c7390cff7016cd49541cfb1019d48ba8c1272c89d
```

REF semantic fingerprints:

```text
identity-set 54a74c8bb8ef67f36dd4b054d6ed43f201bd38d41d75244d9b69eb1583951abc
cluster-set  84afc5a5bb030db9cbdddb7246ceaab3457ef8eb02f1192575433d5f77f6cd82
```

EVAL semantic fingerprints:

```text
identity-set 47ef50345fae50f14e99547426dbf3a3c34ed0caf49574005fb3f1da94315406
cluster-set  c923af78ef7b191b569c5ead859982eb7711460a6537d0a70612a1101ffa8138
```

Distribution CSVs are byte-identical to the reviewed preview. Preview /
application semantic mismatches = 0.
