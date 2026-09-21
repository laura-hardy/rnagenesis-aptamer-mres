# Global S7C — deterministic FT-only train/validation split and freeze

```text
S7C implementation built                 = yes
S7C v1 raw-JSD preview                   = yes (preserved, not approved)
S7C v2 abs-dev preview                   = yes (preserved, approved 2026-09-21)
authoritative FT train/validation files  = yes
FT train frozen                          = yes
FT validation frozen                     = yes
REF frozen                               = yes (unchanged)
EVAL frozen                              = yes (unchanged)
model fine-tuning started                = no
S7D started                              = no
```

```text
frozen FT (ft.csv)
        ->
blank-partition working copy for feature construction only
        ->
same tested v2 optimiser
        (TRAIN/VALIDATION labels; max-abs-proportion-deviation)
        ->
compare against approved v2 preview (parity only)
        ->
authoritative artefacts under
  data/interim/s7c_ft_split/
        ->
TRAIN frozen, VALIDATION frozen
        ->
STOP. No corpus_final. No fine-tuning. No S7D.
```

This milestone applies and freezes the **approved v2** FT train/validation
split. Human review by Laura/ChatGPT approved v2 on 2026-09-21. v1 remains
preserved and is **not** approved. Approval metadata is audit-only and was
not used as the scientific selection mechanism.

## Why v1 was not approved

The first preview (`data/interim/s7c_ft_split_preview/`, copied
unchanged to `data/interim/s7c_ft_split_preview_jsd_v1/`) was
mechanically valid: leakage gates, quotas, determinism, REF/EVAL
immutability, and whole-cluster integrity all passed.

It was **not** approved scientifically. Raw Jensen–Shannon divergence
was used as the common primary scale across criteria whose category
cardinalities differ radically (390 FT targets vs 7 sources, 3 evidence
levels, 2 length regimes). Attainable target JSD in a 64-cluster
validation set is structurally much larger than source/evidence/length
JSD, so minimax JSD effectively prioritised target matching.

v1 therefore achieved excellent target JSD (`D_target = 0.350017921105`)
at the cost of a distorted validation source distribution:

```text
VALIDATION (v1):
aptabase    = 2 / 90 FT identities
aptadb      = 0 / 54
aptaindex   = 0 / 51
aptamerbase = 38 / 368
ena         = 10 / 94
riboaptamer = 15 / 168
utexas      = 4 / 70
```

That does not satisfy the intended meaning of keeping target, evidence,
length regime, and source **broadly comparable**, as well as practical
whole-cluster constraints permit.

No new biological criterion was added. No manual criterion weights were
introduced. The four supervisor-approved comparability criteria are
unchanged. Only the **measurement scale** was revised.

v1 artefacts were not overwritten.

## Frozen S7B inputs

S7C operates **strictly inside FT**. REF and EVAL are not inputs to the
assignment and were hash-guarded before and after the v2 preview.

```text
data/interim/s7b_partition/ft.csv
SHA256 = b680ace037be73f650e386a34d97db915e4925a2dcd59e3053b7542b6d6fb4ff

identities = 895
distinct sequence_core = 795
clusters = 635
canonical targets = 390
partition = FT for every row
E5 = 0
target_type != protein = 0

E2 = 615
E3 = 187
E4 = 93

frozen S6 length-regime cores:
  short = 448
  long  = 347

source identities:
  aptabase     = 90
  aptadb       = 54
  aptaindex    = 51
  aptamerbase  = 368
  ena          = 94
  riboaptamer  = 168
  utexas       = 70
```

Every FT identity keeps its frozen S5 `cluster_id`. Clusters are not
split. `cluster_id` remains the leakage boundary.

`ft.csv` was not mutated. Top-level `partition` remains `FT`.

## REF / EVAL freeze hashes (before and after)

Automated guards ran before and after the v2 preview. Exact agreement
with the S7B freeze record:

```text
REF file SHA256
  before = 6c8bf5cdec625bdddb9f42b18a15f435826bebabb119dfc268ff737c89b7408d
  after  = 6c8bf5cdec625bdddb9f42b18a15f435826bebabb119dfc268ff737c89b7408d

EVAL file SHA256
  before = 88fe1d8c2c78ed9dc478306c7390cff7016cd49541cfb1019d48ba8c1272c89d
  after  = 88fe1d8c2c78ed9dc478306c7390cff7016cd49541cfb1019d48ba8c1272c89d

REF identity-set hash
  before/after = 54a74c8bb8ef67f36dd4b054d6ed43f201bd38d41d75244d9b69eb1583951abc

REF cluster-set hash
  before/after = 84afc5a5bb030db9cbdddb7246ceaab3457ef8eb02f1192575433d5f77f6cd82

EVAL identity-set hash
  before/after = 47ef50345fae50f14e99547426dbf3a3c34ed0caf49574005fb3f1da94315406

EVAL cluster-set hash
  before/after = c923af78ef7b191b569c5ead859982eb7711460a6537d0a70612a1101ffa8138

REF clusters = 80
EVAL clusters = 79
REF/EVAL cluster overlap = 0
```

Any difference would have hard-failed. No repair was attempted or
needed.

## Authority

1. Governing plan v1.5 §1.1 (FT-only cluster-level 90/10 after the
   top-level FT/REF/EVAL freeze)
2. Frozen S7B partition and freeze record
   `config/checkpoint_reviews/s7b_partition_freeze.json`
3. Frozen S6 `bimodality.json` `gmm_2` (not refit)
4. `config/global_s7c_ft_train_validation.json`

This is an implementation-level operationalisation of the already
approved four comparability criteria. The governing curation plan was
not modified.

## Feature grains

Comparison reference = **the complete frozen FT population**, not the
1,173-identity corpus.

| Criterion | Grain | Notes |
| --- | --- | --- |
| canonical target | identity | each of the 895 FT identities contributes once |
| evidence | identity | E2 / E3 / E4 only; E5 cannot be introduced |
| source | identity-grain `source_db` | `contributing_sources` is not expanded |
| length regime | distinct `sequence_core` | frozen S6 short/long; a multi-target core counts once |
| target family | identity | **secondary diagnostic only; not in the primary objective** |

A cluster is indivisible. Multi-target and multi-source clusters
contribute their full category-count vectors. No majority collapse.

## Frozen S6 length-regime provenance

The two S6 sequence-length regimes are reused from frozen S6
`bimodality.json` `gmm_2`. Assignment uses S6
`gmm_posterior_assignment` (`gmm_k2_maximum_posterior`). Component 0 is
short; exact posterior ties go short.

The two-component GMM is **not** refit on FT. No median split and no new
threshold are used. Sequence length is not a continuous optimisation
criterion.

## Integer cluster quotas

Desired fractions are TRAIN = 0.90, VALIDATION = 0.10 of **FT cluster
count**, with `n_TRAIN + n_VALIDATION = 635`. Quotas are by cluster
count, not identity count.

All integer pairs minimising

```text
(n_TRAIN / 635 - 0.90)^2 + (n_VALIDATION / 635 - 0.10)^2
```

were retained. Tied-optimal candidates:

```text
(n_TRAIN, n_VALIDATION) = (571, 64) and (572, 63)
```

Both were optimised independently under the revised objective. The
scientific objective again selected `(571, 64)`.

Because quotas are cluster-count quotas, identity fractions need not
equal 90/10. v2 VALIDATION contains 16.65% of FT identities despite
10.08% of FT clusters. That is a consequence of the identity-weighted
absolute-deviation objective and whole-cluster constraints, not
leakage.

## Revised primary metric

Raw JSD remains a diagnostic and a later tie-break. It is not the
primary cross-criterion optimisation quantity.

For criterion `c ∈ {target, evidence, length, source}` and subset
`p ∈ {TRAIN, VALIDATION}`, using the complete frozen FT category
support:

```text
A_c(p) = max_k |P_p,c(k) - P_FT,c(k)|
M_c    = max(A_c(TRAIN), A_c(VALIDATION))
```

These are maximum **absolute proportion deviations** (percentage points
= fraction × 100). Relative percentage error is not used. An absent
category contributes its full FT proportion as deviation.

## Weight-free multi-objective hierarchy

The four criteria are treated symmetrically. No manual weights. No hard
source-coverage constraint. `target_family` is not in the primary
objective.

```text
R1 = max(M_target, M_evidence, M_length, M_source)
R2 = lexicographic minimum of the four M values sorted descending
R3 = M_target + M_evidence + M_length + M_source
```

If still tied, JSD:

```text
descending (D_target, D_evidence, D_length, D_source),
then D_target + D_evidence + D_length + D_source
```

Final scientific tie-break: stable assignment signature
`cluster_id:label` joined in sorted `cluster_id` order.

```text
comparison tuple =
  (R1, descending M vector, R3,
   descending D vector, sum of D, assignment_signature)

reference distribution = complete frozen FT
arbitrary manually chosen criterion weights = none
new hard source constraint = no
target_family in primary objective = no
```

S7B remains frozen on the original JSD minimax profile. Shared
optimiser code accepts an explicit `objective_profile`; the default is
unchanged S7B `jsd_minimax`.

## Deterministic heuristic

S7C reuses the S7B optimiser rather than duplicating it. Optional
`partition_labels` / `placement_labels` default to the frozen S7B
FT/REF/EVAL behaviour. S7C passes TRAIN/VALIDATION and
`objective_profile = max_abs_proportion_deviation`.

1. `build_cluster_features` on a blank-partition working copy of FT
2. `derive_integer_quota_pairs`
3. `select_preview_assignment` → `optimise_partition`
   (greedy feasible placement, then deterministic pairwise swaps)

Cluster processing order (same as S7B):

1. identity count descending
2. distinct canonical target count descending
3. distinct cores descending
4. stable `cluster_id` ascending

Greedy placement scores each feasible TRAIN/VALIDATION assignment
against frozen FT using the revised primary objective. Stable labels are
the final exact tie-break (`TRAIN` < `VALIDATION` alphabetically).

Local improvement is quota-preserving pairwise cluster swaps between
TRAIN and VALIDATION. A swap is accepted only on a strict comparison-
tuple improvement. Search stops after a full pass with no improvement.

No validation labels, no model performance, and no invented
minimum-target-count or minimum-source-count rule influence assignment.
If all sources appear in validation, that is a result rather than a
constraint.

## Rare targets

Many of the 390 FT targets are singletons. It is not required — and
generally impossible under whole-cluster constraints — that every
target appear in validation. The revised objective intentionally does
not strongly penalise absence of very rare singleton targets, because
each contributes only a small FT proportion. That is scientifically
appropriate for an FT validation set used for model development. There
is no target-coverage hard constraint. Singleton absence from
validation is a coverage limitation, not leakage.

## Preview outputs

Ignored v1 tree (preserved, not approved):

- `data/interim/s7c_ft_split_preview/`
- `data/interim/s7c_ft_split_preview_jsd_v1/` (byte-identical copy)

Ignored v2 tree (approved preview, preserved unchanged):

- `data/interim/s7c_ft_split_preview_v2/cluster_ft_split_preview.csv`
- `data/interim/s7c_ft_split_preview_v2/train_identity_summary.csv`
- `data/interim/s7c_ft_split_preview_v2/validation_identity_summary.csv`
- `data/interim/s7c_ft_split_preview_v2/train_core_summary.csv`
- `data/interim/s7c_ft_split_preview_v2/validation_core_summary.csv`
- `data/interim/s7c_ft_split_preview_v2/target_distribution.csv`
- `data/interim/s7c_ft_split_preview_v2/evidence_distribution.csv`
- `data/interim/s7c_ft_split_preview_v2/length_regime_distribution.csv`
- `data/interim/s7c_ft_split_preview_v2/source_distribution.csv`
- `data/interim/s7c_ft_split_preview_v2/target_family_diagnostic.csv`
- `data/interim/s7c_ft_split_preview_v2/divergence_metrics.csv`
- `data/interim/s7c_ft_split_preview_v2/absolute_deviation_metrics.csv`
- `data/interim/s7c_ft_split_preview_v2/s7c_ft_split_preview_report.md`
- `data/interim/s7c_ft_split_preview_v2/s7c_ft_split_preview_manifest.json`

The sidecar field is `proposed_ft_split` ∈ {TRAIN, VALIDATION}.
Top-level `partition` is not rewritten.

v2 preview hashes (frozen at approval):

```text
cluster_ft_split_preview.csv SHA256 =
  2f11a2b129f025965a428d0f6344e98fd9f615d519c68ba49a49c7d0386951ee
s7c_ft_split_preview_manifest.json SHA256 =
  5bb05e2d73651221e8a553b453c807114427da950968b7bafe6b769900e20838
```

## Approval

Tracked audit record:

`config/checkpoint_reviews/s7c_ft_split_approval.json`

```text
decision_date = 2026-09-21

v1:
  review_status = not_approved
  reason = raw-JSD cross-criterion minimax caused target-support
           cardinality to dominate and yielded inadequate source
           comparability

v2:
  review_status = approved_for_application_and_freeze
  objective = maximum absolute category-proportion deviation
              primary hierarchy, JSD diagnostic/tie-break

frozen_ft_sha256 =
  b680ace037be73f650e386a34d97db915e4925a2dcd59e3053b7542b6d6fb4ff
approved quotas TRAIN/VALIDATION = 571 / 64
approved identities 746 / 149
approved cores 678 / 117
```

This artefact contains no nucleotide sequences and no cluster-ID
selection list. Scientific application rederived the assignment from
frozen `ft.csv` with the tested optimiser, then compared.

## Authoritative application

Mode is `apply`. Output directory is `data/interim/s7c_ft_split/`.
Preview directories were not overwritten.

Command:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/data_preparation/s7_ft_train_validation.py \
  --config config/global_s7c_ft_train_validation.json
```

Authoritative files:

- `data/interim/s7c_ft_split/ft_split_assignment.csv`
- `data/interim/s7c_ft_split/ft_train.csv`
- `data/interim/s7c_ft_split/ft_validation.csv`
- plus sequence-free summaries, distributions, report, and manifest

Every train/validation identity retains top-level `partition = FT`.
The S7C designation is the additional field `ft_split` ∈ {TRAIN, VALIDATION}.

## Preview / application parity

```text
clusters compared                    = 635
cluster assignment mismatches        = 0
aggregate/statistical mismatches     = 0
objective mismatches                 = 0
semantic mismatches total            = 0
approval used for assignment         = no
```

The v2 assignment was reproduced exactly.

## Authoritative split sizes

| subset | clusters | cluster % | identities | identity % | cores | core % |
| --- | --- | --- | --- | --- | --- | --- |
| TRAIN | 571 | 89.92 | 746 | 83.35 | 678 | 85.28 |
| VALIDATION | 64 | 10.08 | 149 | 16.65 | 117 | 14.72 |
| FT total | 635 | 100 | 895 | 100 | 795 | 100 |

TRAIN represents 333 FT targets. VALIDATION represents 102.
Targets shared = 45; train-only = 288; validation-only = 57.
Singleton-target identities TRAIN/VALIDATION = 181 / 39.

The larger validation identity/core fraction is an accepted consequence
of whole-cluster quota splitting and four-way distribution comparability.
Validation-only targets are permitted. No target-coverage hard constraint
was added.

## TRAIN / VALIDATION freeze

Tracked freeze record:

`config/checkpoint_reviews/s7c_ft_split_freeze.json`

```text
freeze date = 2026-09-21
FT train frozen = true
FT validation frozen = true

TRAIN:
  clusters = 571
  identities = 746
  cores = 678
  targets represented = 333
  ft_train.csv SHA256 =
    941fe8783ee8c99a2ce7598dea00ed123e62750026b7f157f28e7bbcc5d14a8f
  identity-set hash =
    75e5cb8471d2fb3ee30529617aaf80ff584d5bf79e9976dc338434057a6aac6a
  cluster-set hash =
    18c6df63ac4935557bad9c5fcc12610dd280b207652208faf04f0ba39d9c3349

VALIDATION:
  clusters = 64
  identities = 149
  cores = 117
  targets represented = 102
  ft_validation.csv SHA256 =
    03be477e12f7b9ca20f8911e2ac88fde2949af2b6131c2d2aa43eef2ae6d9abc
  identity-set hash =
    19121149b9e0e02dd9cda5eb5619c64df86940331603139b702d436e6bde67ac
  cluster-set hash =
    088d6b4db826be5c970b410e74cfa2d52fc402fa4818c692f8be30e42f79c4f9

ft_split_assignment.csv SHA256 =
  22f3ef6236e8f59303670497772707e71625f2f444785fda4e7f9f9daa28eb04
```

Evidence TRAIN E2/E3/E4 = 513/156/77; VALIDATION = 102/31/16.
Length TRAIN short/long = 382/296; VALIDATION = 66/51.
Source identities TRAIN/VALIDATION: aptabase 75/15, aptadb 45/9,
aptaindex 43/8, aptamerbase 307/61, ena 78/16, riboaptamer 140/28,
utexas 58/12. All seven sources emerged from the approved assignment.

## Model-development boundary

After this freeze:

- model training uses **FT TRAIN only**
- checkpoint selection / early stopping / hyperparameter comparison may
  use **FT VALIDATION only**
- REF remains reserved for AptaRank / reference-distribution calibration
- EVAL remains reserved for final held-out evaluation
- EVAL may later evaluate fine-tuned RNAGenesis, but must not influence
  training, checkpoint, or hyperparameter choices
- no cluster may move among TRAIN/VALIDATION/REF/EVAL based on modelling
  results

Any later legitimate correction requires a documented split revision,
new hashes, and explicit human approval.

## v2 preview split sizes

| subset | clusters | cluster % | identities | identity % | cores | core % |
| --- | --- | --- | --- | --- | --- | --- |
| TRAIN | 571 | 89.92 | 746 | 83.35 | 678 | 85.28 |
| VALIDATION | 64 | 10.08 | 149 | 16.65 | 117 | 14.72 |
| FT total | 635 | 100 | 895 | 100 | 795 | 100 |

TRAIN represents 333 FT targets. VALIDATION represents 102.

## v2 primary absolute-deviation metrics

Fractions and percentage points versus complete frozen FT.

```text
A_target(TRAIN)      = 0.003351955307  (0.335195530726 pp)
A_target(VALIDATION) = 0.016782272881  (1.678227288066 pp)
M_target             = 0.016782272881  (1.678227288066 pp)

A_evidence(TRAIN)      = 0.000693456348  (0.069345634820 pp)
A_evidence(VALIDATION) = 0.003471935810  (0.347193581043 pp)
M_evidence             = 0.003471935810  (0.347193581043 pp)

A_length(TRAIN)      = 0.000100183670  (0.010018367006 pp)
A_length(VALIDATION) = 0.000580551524  (0.058055152395 pp)
M_length             = 0.000580551524  (0.058055152395 pp)

A_source(TRAIN)      = 0.000657510447  (0.065751044678 pp)
A_source(VALIDATION) = 0.003291965056  (0.329196505568 pp)
M_source             = 0.003291965056  (0.329196505568 pp)

R1 = 0.016782272881  (1.678227288066 pp)
descending M vector = [0.016782272881, 0.003471935810, 0.003291965056, 0.000580551524]
R3 = 0.024126725271  (2.412672527071 pp)
```

R1 is `M_target`. The responsible target is HIV-1 aspartyl protease
(PR) in VALIDATION.

Greedy R1 before local search = 0.127624576681. Local search converged
after 526 accepted swaps / 33 passes.

## v2 source distribution

Identity-grain `source_db`. No source is absent from validation. That
is a result of the symmetric metric, not a hard constraint.

| source | full FT count/share | TRAIN count/share | VALIDATION count/share | validation abs share deviation |
| --- | --- | --- | --- | --- |
| aptabase | 90 (0.10056) | 75 (0.10054) | 15 (0.10067) | 0.00011 |
| aptadb | 54 (0.06034) | 45 (0.06032) | 9 (0.06040) | 0.00007 |
| aptaindex | 51 (0.05698) | 43 (0.05764) | 8 (0.05369) | 0.00329 |
| aptamerbase | 368 (0.41117) | 307 (0.41153) | 61 (0.40940) | 0.00178 |
| ena | 94 (0.10503) | 78 (0.10456) | 16 (0.10738) | 0.00235 |
| riboaptamer | 168 (0.18771) | 140 (0.18767) | 28 (0.18792) | 0.00021 |
| utexas | 70 (0.07821) | 58 (0.07775) | 12 (0.08054) | 0.00232 |

```text
VALIDATION count = 0 sources = 0
M_source = 0.003291965056 (0.33 pp)
responsible category = aptaindex in VALIDATION
```

## v2 evidence and length

Evidence (identity grain):

```text
E2: FT 615 (0.68715); TRAIN 513 (0.68767); VALIDATION 102 (0.68456)
E3: FT 187 (0.20894); TRAIN 156 (0.20912); VALIDATION  31 (0.20805)
E4: FT  93 (0.10391); TRAIN  77 (0.10322); VALIDATION  16 (0.10738)
M_evidence = 0.003471935810 (0.35 pp); category = E4
```

Length regime (distinct-core grain):

```text
short: FT 448 (0.56352); TRAIN 382 (0.56342); VALIDATION 66 (0.56410)
long:  FT 347 (0.43648); TRAIN 296 (0.43658); VALIDATION 51 (0.43590)
M_length = 0.000580551524 (0.06 pp)
```

Evidence and length were already good in v1; v2 improved both
absolute-deviation maxima and did not create a substantial
deterioration.

## v2 target diagnostics

```text
targets represented TRAIN      = 333
targets represented VALIDATION = 102
targets only in TRAIN          = 288
targets only in VALIDATION     = 57
targets shared                 = 45
targets absent from VALIDATION = 288

singleton-target identities TRAIN/VALIDATION = 181 / 39
singleton-target clusters   TRAIN/VALIDATION = 181 / 39

M_target = 0.016782272881 (1.68 pp)
responsible target = HIV-1 aspartyl protease (PR) in VALIDATION
```

Top 15 FT targets (identity grain):

| target | full FT | TRAIN | VALIDATION |
| --- | --- | --- | --- |
| HIV-1 Rev protein | 25 | 23 | 2 |
| E.Coli rho factor | 21 | 20 | 1 |
| Envelope glycoprotein GP120 | 21 | 19 | 2 |
| ALPPL2 | 20 | 17 | 3 |
| NGF | 18 | 16 | 2 |
| PAP | 17 | 13 | 4 |
| Tumor necrosis factor alpha (hTNFα) | 15 | 13 | 2 |
| Basic fibroblast growth factor (bFGF) | 13 | 12 | 1 |
| CTHRC1 | 13 | 11 | 2 |
| HIV-1 Rev binding protein | 12 | 11 | 1 |
| Vascular Endothelial Growth Factor (VEGF) | 12 | 11 | 1 |
| angiopoietin 2 | 12 | 11 | 1 |
| heterogeneous nuclear ribonucleoprotein L | 12 | 11 | 1 |
| Glutamate receptor, AMPA type, Glur2 subunit | 11 | 10 | 1 |
| Keratinocyte growth factor | 11 | 10 | 1 |

## v2 JSD diagnostics (tie-break / reporting only)

```text
J_target(TRAIN)      = 0.052039505541
J_target(VALIDATION) = 0.431467103096
D_target             = 0.431467103096

J_evidence(TRAIN)      = 0.000000934360
J_evidence(VALIDATION) = 0.000023014526
D_evidence             = 0.000023014526

J_length(TRAIN)      = 0.000000007359
J_length(VALIDATION) = 0.000000247149
D_length             = 0.000000247149

J_source(TRAIN)      = 0.000002297874
J_source(VALIDATION) = 0.000058480761
D_source             = 0.000058480761

O1 (JSD diagnostic) = 0.431467103096
O3 (JSD diagnostic) = 0.431548845531
```

Target JSD is larger than in v1 because JSD is no longer the first
optimisation scale.

## v1 versus v2

v1 absolute-deviation metrics were calculated retrospectively from the
preserved v1 assignment. v2 is not automatically superior solely because
it is newer; the comparison below is the scientific trade-off.

| metric | v1 raw-JSD preview | v2 revised preview |
| --- | --- | --- |
| cluster quotas | 571 / 64 | 571 / 64 |
| TRAIN identities | 826 | 746 |
| VALIDATION identities | 69 | 149 |
| targets represented in validation | 59 | 102 |
| validation sources represented | 5 | 7 |
| sources absent from validation | aptadb, aptaindex | none |
| M_target | 0.022281596632 | 0.016782272881 |
| M_evidence | 0.008501335924 | 0.003471935810 |
| M_length | 0.010007399186 | 0.000580551524 |
| M_source | 0.139551453324 | 0.003291965056 |
| R1 | 0.139551453324 | 0.016782272881 |
| D_target | 0.350017921105 | 0.431467103096 |
| D_evidence | 0.000061441657 | 0.000023014526 |
| D_length | 0.000073625782 | 0.000000247149 |
| D_source | 0.085263227565 | 0.000058480761 |

v1 matched the 390-target distribution more closely in JSD terms by
placing mostly small clusters in validation, which collapsed source
coverage (AptaDB and AptaIndex absent; AptamerBase 55% of validation
vs 41% of FT). v2 uses a common percentage-point scale, keeps all
seven sources within 0.33 pp of FT, and still holds evidence and length
within 0.35 pp. The cost is worse target JSD and a larger, more
identity-heavy validation set. That is the intended scientific
correction. Laura/ChatGPT approved v2 for application and freeze.

## Secondary target-family diagnostic — not optimisation objective

Known-family identities = 140 (share 0.15642). Unknown = 755 (share
0.84358).

```text
J_family(TRAIN)      = 0.001551656538
J_family(VALIDATION) = 0.033813423900
D_family (diagnostic)= 0.033813423900
```

Clusters were not moved to improve this metric.

## Random whole-cluster baseline (diagnostic only)

Fixed-seed random whole-cluster assignments using the selected 571/64
quotas, 21 seeds. Not eligible as the scientific assignment.

```text
random R1 min/mean/max = 0.04587 / 0.08864 / 0.18082
optimised R1           = 0.01678

random M_target   min = 0.03036 ; optimised = 0.01678
random M_evidence min = 0.00888 ; optimised = 0.00347
random M_length   min = 0.00227 ; optimised = 0.00058
random M_source   min = 0.02760 ; optimised = 0.00329

random O1 (JSD) min/mean/max = 0.48865 / 0.51942 / 0.54889
optimised O1 (JSD diagnostic)= 0.43147
```

The revised solution is better than every random split on R1 and on
each individual `M_c` minimum reported above. Random splits are not
used as the assignment.

## Tests

Synthetic tests in `tests/data_preparation/test_s7_ft_train_validation.py`
cover FT-only admission, REF/EVAL rejection, whole-cluster integrity,
90/10 quota derivation including ties, grains, complete-support
absolute deviation (including absent categories), R1 / sorted-M / R3
hierarchy, JSD used only after that hierarchy, stable assignment
signature, no manual weights, target-family exclusion, greedy capacity,
local-search rules, row-order independence, REF/EVAL file and
semantic-set guards, unmutated `ft.csv`, unaltered top-level
`partition`, E5/non-protein exclusion, sequence-free preview metadata,
the frozen S7B synthetic assignment fingerprint after the shared
objective-profile refactor, and the application/freeze path (approval
is audit-only, preview directories are not overwritten, retained
scientific fields other than `ft_split` are preserved).

S7B tests continue to reproduce the frozen S7B JSD comparison tuple and
synthetic assignment fingerprint under the default profile.

The specified S7C/S7B/S7A/S5E/S6 command after application/freeze:
166 passed. The accepted v2 preview baseline was 161; the increase is
the five new application/freeze tests.

## Scientific boundary

```text
S7C v1 preview preserved                    = yes
S7C v1 approved                             = no
S7C v2 preview generated                    = yes
S7C v2 approved                             = yes (2026-09-21)
authoritative FT train/validation files     = yes
FT train frozen                             = yes
FT validation frozen                        = yes
REF frozen                                  = yes
EVAL frozen                                 = yes
REF changed                                 = no
EVAL changed                                = no
model fine-tuning started                   = no
REF calibration started                     = no
EVAL evaluation started                     = no
S7D started                                 = no
commit performed                            = no
push performed                              = no
```

STOP. Do not begin S7D. Do not generate `corpus_final`. Do not start
model fine-tuning.
