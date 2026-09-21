# Global S5E — leakage-safe final cluster construction + S5 closure

S5E changes only the **S5 clustering interpretation**. It does not
reopen S4 or S5A, does not change MMseqs parameters, does not tune
clustering against ENA, does not select CD-HIT, and does not begin
S6/S7.

```text
frozen S5A identities (1281) + cores (1144)
frozen S5C MMseqs clusters (813)
trusted real multi-member ENA family must-links (16)
        ->
union-find connected components
        ->
final cluster_id + one technical representative
        ->
S5 CLOSE
```

## GO / NO-GO

**GO.** The revised final S5 clustering was constructed and S5 can close.

```text
decision = GO — S5 CLOSED
base     = frozen MMseqs 90% clusters
constraints = positive ENA family must-links only
```

## Integrity

HEAD and `origin/main` remain `bdc1df1b170eaac37a909a701e07c62377acfffd`
on `main`. Recalculated S4, S5A, and S5C candidate hashes matched the
freeze. `git ls-files data` is empty. Frozen S5C files were not mutated.
CD-HIT diagnostic outputs were not deleted.

## Scientific-policy resolution

ENA `near_duplicate_family_id` is positive must-link provenance, not
complete global 90%-identity ground truth. See
`s5_clustering_methodology.md`. Materialised `ena_singleton_*` IDs
create no union edges and no cannot-links.

## Final union construction

```text
MMseqs starting clusters                         = 813
real/multi-member family IDs represented           = 17
families with ≥2 retained S5 ENA cores           = 16
families that created a union edge                =  8
already-contained families (no new edge)        =  8
MMseqs clusters in unioned final clusters         = 23
final clusters affected by ENA must-links       =  6
reduction attributable to family constraints    = 17
final clusters                                   = 796
```

796 ≤ 813. S5E created no clusters. Every frozen MMseqs cluster is a
subset of exactly one final cluster.

Eight families already occupied one MMseqs cluster; they remain
contained. Eight families spanned 2–7 MMseqs clusters and were unioned.
Transitive overlap among NGF families produced 6 unioned finals rather
than 8 independent merges (18 independent reductions would be expected;
17 were observed).

## ENA positive validation

```text
16 / 16 retained multi-member ENA families contained
```

Required. Failure would be NO-GO. Observed split count = 0.

Descriptive, **not** fail conditions:

```text
singleton-source family IDs (1 S5 membership row)     = 96
isolated from every other ENA core                   = 83
clustered with another materialised singleton          = 10
clustered with a real multi-member ENA family         =  2
clustered only with non-ENA sequences                   =  1
clusters containing multiple ENA family IDs         =  6
clusters combining distinct real ENA families          =  3
clusters mixing real families and singletons           =  2
```

The 96 figure includes the declared multi-member family
`ndfam_1f332f7a5e|ndfam_68975c601e`, which has only one surviving S5
core and therefore created no must-link. Ninety-five IDs are
`ena_singleton_*`.

## Final clustering statistics

```text
final clusters              = 796
singleton clusters          = 637
multi-sequence clusters     = 159
singleton fraction          = 0.800
largest cluster size        = 89
scientific identities       = 1281
unique sequence cores       = 1144
clusters with >1 target     = 143
clusters with >1 source     = 187
clusters with ENA provenance = 98
clusters with a shared core  = 104
```

Cluster-size distribution (sequence cores):
1=637, 2=107, 3=35, 4=5, 5=4, 6=4, 7=1, 9=1, 19=1, 89=1.

Identities per cluster:
1=577, 2=133, 3=48, 4=18, 5=8, 6=2, 7=3, 8=4, 9=1, 19=1, 89=1.

The 89-sequence cluster is a single-target NGF family union
(`mmseqs_plus_ena_family_must_link`). The 19-sequence cluster is also a
family-union component. Neither is a scientific-identity merge.

## Representative validation

Exactly 796 scientific representatives and 796 sequence-level
representatives. Policy: among frozen MMseqs representatives in the
final cluster, take the representative of the largest MMseqs component;
tie-break on lexicographically smallest `sequence_core_sha256`; then
lexicographically smallest `scientific_identity_id`. Technical only.

Un-unioned finals keep the frozen MMseqs `cluster_id`.

## Population preservation

```text
scientific identities before = 1281
scientific identities after  = 1281
unique sequence cores        = 1144
shared cores                 = 118
identities on shared cores   = 255
membership rows on those cores = 326
missing cluster_id           = 0
```

No scientific identity was removed or merged. Canonical targets are
unchanged. All identities sharing a core share final `cluster_id`.

## Final outputs and hashes

Ignored under `data/interim/deduplicated/`:

| File | SHA-256 |
|---|---|
| `clusters_final.tsv` | `9b1b3c671cd1cd603e56ab23f0b2a9adac4ad85d47b019679ccb602605f971d9` |
| `corpus_clustered_final.csv` | `615677d51aa81337a3660b8c67e9db9fae2a5c8abc7128e7668617a342689d30` |
| `cluster_summary_final.csv` | `7d06793fbf56be2e4e52c21d83faccef822feb2234118e4ef4b36dc307b6d078` |
| `cluster_union_provenance.csv` | `83023ba556d0a3e486ef7205001d9ae46f9ba9ef2e56210fa4f7a7e892c5f2dc` |
| `overlap_report.md` | `41e52f80ec632e6dbc7a912f244d4df302b78b79d1cbab8e7141432a89d8e33b` |
| `s5_final_clustering_manifest.json` | `aa5bab02a78481f32b4bab82c157d3f8aa975ebf4a77350fec9d9dd88623c5b0` |

`clusters_final.tsv` has 1144 rows. `corpus_clustered_final.csv` has
1281 scientific identities. Sidecar `s5e_ena_must_link_containment.csv`
and `s5e_ena_must_link_cohort.csv` are diagnostic only.

Manifest records:

```text
base_sequence_clustering_method = mmseqs
base_sequence_clustering_parameters =
  --min-seq-id 0.9 -c 0.8 --cov-mode 1 -s 7.5
family_constraint_source = ena.near_duplicate_family_id
family_constraint_semantics = positive_must_link_only
materialised_singletons_as_cannot_link = false
cd_hit_fallback_tested = true
cd_hit_selected = false
```

## Plan / documentation

Governing plan bumped to **v1.4 — 2026-09-17**. S5 clustering text and
the ENA acceptance test were revised. S1–S4 scientific decisions were
not changed. Methodology: `s5_clustering_methodology.md`.

## Tests and determinism

```text
S5E synthetic tests = 19 passed
S5D regression      = 21 passed
S5C regression      = 24 passed
S5A regression      = 21 passed
S5B regression      = 17 passed
total               = 102 passed
```

Two live S5E runs from frozen inputs produced byte-identical
`clusters_final.tsv`, `corpus_clustered_final.csv`,
`cluster_summary_final.csv`, `cluster_union_provenance.csv`,
`overlap_report.md`, and `s5_final_clustering_manifest.json`.

## S5 closure / boundary

- S5 complete
- exact dedup complete
- leakage-safe clustering complete
- no balancing
- no S6 executed
- no target cap
- no FT/REF/EVAL
- no train/validation split
- no S4 changes
- no commit/push
- no tracked data

S6 is next and has not started. S6 will profile the final
target-normalised, exact-deduplicated, leakage-safe clustered corpus.
No target cap has been selected.
