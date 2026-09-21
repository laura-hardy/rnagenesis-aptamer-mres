# Global S5B — exact-dedup validation, schema reconciliation, and freeze

S5B validates frozen S5A exact scientific identities against the
original 1460 primary S4 relationships and records the representation
needed for downstream clustering. It does not cluster sequences, run
MMseqs2 or CD-HIT, rewrite S4, or change S5A scientific policy.

```text
frozen S4 primary relationships (1460)
        +
frozen S5A outputs
        ->
invariant validation
schema / row-identity audit
clustering-readiness projection (no clustering)
        ->
S5A/S5B exact-dedup freeze
        ->
STOP. S5C clustering is a later milestone.

```

## Input

Authoritative scientific input remains the S5A freeze:

- `data/interim/deduplicated/corpus_dedup.csv`
- `data/interim/deduplicated/exact_duplicate_membership.csv`
- plus the S5A group, dictionary-conflict, multi-target, and overlap
  sidecars

checked against `global_s4_reviewed_relationships.csv` where
`s4_route == primary_candidate`. S4 files were not regenerated.

## Population

```text
S4 primary relationships     = 1460
membership rows              = 1460
scientific identities        = 1281
duplicate groups             = 157
duplicate excess             = 179
1460 - 179                   = 1281
distinct scientific keys     = 1281
distinct sequence_core       = 1144
```

Every primary relationship occurs once in membership, maps to one
`scientific_identity_id`, retains its `reviewed_relationship_id` and
source `record_id`, and has the expected
`(sequence_core, canonical_target_name)` key.

No excluded route appears in membership (`park_non_protein`,
`park_evidence_e5`, `hold_target_unresolved`,
`reject_no_binding_evidence`, target/relationship parks,
unresolved-no-relationship, leakage). `aptamerbase:1110|2` remains
the primary `Epidermal growth factor receptor` relationship; the
parked A549-cell relationship stays out of S5.

## Scientific key

The mapping between primary scientific keys and
`scientific_identity_id` is a bijection. Each identity has exactly
one canonical target name. 118 `sequence_core` values have more than
one canonical target (326 rows) and remain separate identities.
Exact dedup never collapses them merely because the core is equal.

## Donor

Independent recomputation using the frozen S5A hierarchy matched all
1281 donors. Decision path among the 157 contested identities:

```text
evidence_score                         = 35
metadata_completeness                  = 46
alphabetical source_db                 = 54
alphabetical reviewed_relationship_id  = 22
pre-S5 corroboration_count             =  0
sole member (uncontested)              = 1124
```

Pre-S5 corroboration never separated a winner. Scalar donor fields
match the donor membership row; merged provenance fields match
membership recomputation. Affinities were not averaged.

## Provenance / conflicts

`corroboration_count` equals distinct `source_db` values:

```text
1 = 1143
2 =  131
3 =    6
4 =    1
```

`independently_attested_by_permissive_source` is false on all 1281
identities. Restricted AptaIndex rows remain visible (126). Mixed
restricted/unknown groups remain reversible on synthetic fixtures.

Hard conflict regressions all matched S5A:

```text
target-dictionary ID conflict groups     = 9
differing evidence groups                = 38
conflicting canonical affinity groups    = 3
multiple affinity observations           = 91
multiple chemistry groups                = 3
>1 sequence_full                         = 0
>1 construct_scope                       = 71
>1 trim_status                           = 107
```

Dictionary names: HIV-1 reverse transcriptase 2; NF-kappaB p65 3;
Botulinum neurotoxin type A (BoNT/A) 3; Interleukin-17 A/F
heterodimer 1. S4 dictionary IDs were not globally merged. UTexas
post-SELEX modification notes remain in membership (96). Donor
evidence stays in E2/E3/E4; E5 did not enter S5.

## Row identity

`record_id` on `corpus_dedup.csv` is donor/source provenance and is
**not unique**: 26 donor `record_id` values are repeated across 53
rows. `scientific_identity_id` is 1281/1281 populated, 1281 unique,
regenerates from the scientific key, and has zero collisions.

For all S5 downstream operations, including S5C, the unique row
identifier is `scientific_identity_id`. Do not use donor `record_id`
as the deduplicated identity.

S5B does not rewrite S4 or S5A scientific files. Later final-schema
alignment should use **Option B**: formally extend the final schema
with distinct unique `scientific_identity_id` and keep source donor
`record_id` as provenance. Option A (overwrite `record_id` with the
S5 identity) is not required for mechanical validity and would hide
the source identifier in the primary field.

## Clustering readiness

`corpus_dedup.csv` is suitable as S5C input at scientific-identity
grain, but clustering itself must run at sequence grain:

```text
identities                    = 1281
distinct scientific_identity_id = 1281
distinct sequence_core        = 1144
missing sequence_core         = 0
length min / median / max     = 20 / 50 / 123
outside 20–100 nt             = 13
shared cores                  = 118
extra identities from shares  = 137
```

The 13 length outliers are AptaBase identities already accepted by
S4 (cores 104–123 nt). They are reported, not re-filtered. Alphabet
on `sequence_core`: RNA 1274, DNA_T 4, mixed_T_U 3; none invalid or
missing. Shared-core identity counts: 100 cores with 2 identities,
17 with 3, 1 with 4 — the same 118 multi-target cores.

S5C should create one clustering-input row per distinct
`sequence_core` (1144 rows) containing the core, its SHA-256, length,
and the list of `scientific_identity_id` values that share it. After
clustering, broadcast `cluster_id` back onto every scientific
identity using that core. S5B does not write that input or assign
cluster IDs.

## ENA family provenance

```text
S5 ENA membership rows                         = 237
identities with ENA provenance                 = 235
distinct ENA sequence_core                     = 234
family IDs represented                         = 112
declared multi-member families represented     = 17
families with ≥2 S5 ENA members                = 16
within-family exact-dedup collapses            = 0
family membership reconstructable from sidecar = yes
```

The 16 multi-member families with at least two S5 ENA members are
the relevant later clustering ground truth. One additional family is
declared multi-member in source size but has only one S5 member;
E5-only family members outside S5 are not failures. Cluster recall
is not evaluated.

## Outputs

Tracked:

- `scripts/data_preparation/s5_validate_exact_dedup.py`
- `scripts/data_preparation/adapters/s5_validate_exact_dedup.py`
- `config/global_s5b_exact_dedup_validation.json`
- `tests/data_preparation/test_s5_validate_exact_dedup.py`
- this document

Ignored `data/interim/deduplicated/`:

- `s5b_validation_report.md`
- `s5b_validation_summary.json`

S5A scientific CSVs were not rewritten. Tracked reports contain
aggregate statistics only.

## Not in S5B

- 90% sequence clustering (MMseqs2 / CD-HIT)
- cluster ID assignment
- S6 profile / CHECKPOINT-3
- S7 balancing, FT/REF/EVAL, splits
- final-schema Option A or Option B migration
- live source-exclusion rebuild
