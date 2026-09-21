# Global S5C — 90% sequence-identity clustering

S5C clusters the frozen exact-deduplicated primary corpus on
`sequence_core` at 90% identity using MMseqs2. It does not run
CD-HIT, adjudicate ENA-family recall, rewrite S4 or S5A, balance
targets, or assign FT/REF/EVAL.

```text
frozen S5A corpus_dedup.csv (1281 scientific identities)
        ->
1144 distinct sequence_core rows
        ->
mmseqs easy-cluster --min-seq-id 0.9 -c 0.8 --cov-mode 1 -s 7.5
        ->
stable S5C cluster IDs + one scientific representative per cluster
        ->
broadcast onto all 1281 identities as corpus_clustered.csv
        ->
STOP. S5D ENA-family adjudication is a later milestone.
```

## Input

Authoritative scientific input remains the S5A freeze, especially
`data/interim/deduplicated/corpus_dedup.csv`. S5C reads it and
writes derived outputs. It does not overwrite
`corpus_dedup.csv`.

Clustering is corpus-wide and sequence-only. Target labels are not
exposed to MMseqs.

## Sequence-level population

```text
scientific identities     = 1281
distinct sequence_core    = 1144
shared sequence cores     = 118
identities on shared cores = 255
S4/S5A membership rows on those cores = 326
extra identities from shared cores = 137
missing sequence_core     = 0
```

The S5A/S5B figure 326 is membership/relationship rows on the 118
shared cores, not 326 scientific identities. S5C retains all 255
identities on those cores and all 326 membership relationships.

Length and alphabet are reported, not used as filters:

```text
identity length min / median / max = 20 / 50 / 123
core length min / median / max     = 20 / 49 / 123
identities / cores >100 nt         = 13 / 13
identity alphabet: RNA 1274, DNA_T 4, mixed_T_U 3
core alphabet:     RNA 1137, DNA_T 4, mixed_T_U 3
```

The 13 length outliers remain the AptaBase identities already
accepted by S4.

## Identifiers

`sequence_id` is `S5SEQ_<sha256(sequence_core)>`. It is a
sequence-level key, not a scientific `(sequence, target)` identity.

FASTA order is:

1. `sequence_core_sha256` ascending
2. `sequence_id` ascending

`cluster_id` is `S5C_` plus SHA-256 of the sorted member
`sequence_core_sha256` values joined by U+001F. MMseqs numeric
labels are not persisted.

Scientific `is_cluster_representative` is technical only: take the
MMseqs representative `sequence_core`, then the lexicographically
smallest `scientific_identity_id` among identities carrying that
core. Donor `record_id` is never used. Exactly one scientific
representative is marked per cluster.

## Tool environment

MMseqs2 18-8cc5c was installed with Homebrew
(`brew install mmseqs2`) at `/opt/homebrew/bin/mmseqs`. CD-HIT was
not installed and was not run.

Synthetic RNA/U preflight accepted A/C/G/U FASTA in nucleotide
mode, clustered identical and near-identical U sequences, and did
not require a U→T derived corpus. This version treats U as
internally equivalent to T. Authoritative `sequence_core` values
were still clustered as frozen.

## Cluster results

```text
clusters                         = 813
singleton clusters               = 651
multi-sequence clusters          = 162
singleton fraction               = 0.801
largest cluster size             = 36
1144 sequences → 813 clusters
reduction from near-sequence clustering = 331
```

No scientific identity was removed. `is_cluster_representative` is
an annotation, not an inclusion filter.

Two identical pipeline runs produced the same MMseqs membership,
stable cluster IDs, and representative selection.

## ENA diagnostics for S5D

Of the 16 multi-member S5 ENA families, 8 are contained in one
cluster and 8 are split. S5C does not decide whether that recall is
adequate and does not run the CD-HIT fallback.

## Outputs

Tracked:

- `scripts/data_preparation/s5_cluster_sequences.py`
- `scripts/data_preparation/adapters/s5_sequence_clustering.py`
- `config/global_s5c_sequence_clustering.json`
- `tests/data_preparation/test_s5_sequence_clustering.py`
- this document

Ignored `data/interim/deduplicated/`:

- `sequence_clustering_input.csv`
- `sequence_clustering_input.fasta`
- `clusters.tsv`
- `corpus_clustered.csv`
- `cluster_summary.csv`
- `s5c_clustering_manifest.json`
- `s5c_sequence_clustering_report.md`

plus sequence-safe sidecars for identity mapping, identity audit,
and ENA family diagnostics. Tracked reports contain aggregate
statistics only.

## Not in S5C

- CD-HIT fallback
- S5D ENA-family performance adjudication
- S6 profile / CHECKPOINT-3
- S7 balancing, FT/REF/EVAL, splits
- U→T derived clustering corpus
- rewrite of S4 or the S5A freeze
