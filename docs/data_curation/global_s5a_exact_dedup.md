# Global S5A — exact scientific deduplication

S5A collapses frozen S4 **primary** relationships on the exact scientific
key `(sequence_core, canonical_target_name)` and merges provenance. It
does not cluster sequences, merge S4 target dictionary IDs globally,
resolve NCBI/ENA duplicates, balance targets, or assign partitions.

```text
frozen S4 reviewed relationships
    filter s4_route == primary_candidate
        ->
exact scientific identity
    (sequence_core, canonical_target_name)
        ->
corpus_dedup.csv
exact_duplicate_membership.csv
exact_duplicate_groups.csv
        ->
STOP. Clustering is a later S5 milestone.
```

## Input

Authoritative input is

`data/interim/global_s4/global_s4_reviewed_relationships.csv`

restricted to `s4_route == primary_candidate` (1460 relationships;
1429 distinct source `record_id` values). Record-level
`s4_record_outcome` is **not** the filter. Combined S4 extras are
joined by `record_id` for construct/trim/redistribution/ENA family
and modification provenance.

Excluded S4 routes remain excluded. S5A never reconstructs the
primary corpus from record-level outcomes.

## Scientific identity

`scientific_identity_id` is

`S5I_<sha256(sequence_core + "\x1f" + canonical_target_name)>`

using the full SHA-256 hex digest. The ID is independent of row
order and donor selection. Source `record_id` remains donor
provenance and is not unique at relationship grain.

`target_dictionary_id` is not part of the key. Groups with more than
one dictionary ID collapse, keep every contributing ID in
provenance, flag `multiple_target_dictionary_ids`, and retain the
donor ID as the scalar value. The S4 dictionary table is not
rewritten.

Identical sequences against different canonical target names remain
distinct scientific identities.

## Donor hierarchy

1. highest `evidence_score`
2. highest pre-S5 `corroboration_count` (never inferred from duplicate-row count)
3. highest metadata completeness
4. alphabetical `source_db`
5. alphabetical `reviewed_relationship_id`

Metadata completeness is a count of named structured fields that are
present and non-placeholder. It is not row order, column order, text
length, or a count of every populated cell. The frozen field list is:

`canonical_affinity`, `affinity_type`, `doi`, `pubmed_id`,
`accession`, `target_uniprot`, `target_pfam`, `target_family`,
`pdb_id`, `chemistry`, `molecule_type`, `construct_scope`,
`trim_status`, `publication`.

Publication is a presence bit only. Unresolved `unknown` does not
count for family, chemistry, molecule type, or construct scope.

## Provenance

Deduplication merges provenance rather than discarding losing rows.

- `contributing_sources` = sorted unique `source_db`
- `contributing_datasets` = sorted unique datasets
- `corroboration_count` = number of distinct sources, not rows,
  publications, or measurements
- corroboration does not raise evidence level
- `redistribution_status` = most permissive of
  `{permissive, unknown, restricted}`
- `independently_attested_by_permissive_source` is true only when a
  contributing source is actually `permissive`

The membership table is the reversible mapping: every S4 primary
relationship appears exactly once.

If a later source exclusion removes source A from a pair attested by
A and B, the scientific identity remains because B independently
attests it. That behaviour is tested on synthetic fixtures; this
milestone does not run a source-exclusion rebuild.

## Evidence, affinity, chemistry

Donor fields supply scalar canonical evidence, affinity, chemistry,
`sequence_full`, construct/trim, and target metadata. Member
observations remain in `exact_duplicate_membership.csv`.

Affinities are not averaged, minimised, or otherwise combined.
Conflicting nonblank canonical molar values are flagged
`conflicting_affinity_values`. Distinct nonblank chemistries such as
RNA versus 2F-RNA still collapse to one scientific identity and are
flagged `multiple_chemistries`.

## Outputs

Ignored `data/interim/deduplicated/`:

- `corpus_dedup.csv`
- `exact_duplicate_membership.csv`
- `exact_duplicate_groups.csv`
- `target_dictionary_id_conflicts.csv`
- `multi_target_sequence_report.csv`
- `exact_overlap_matrix.csv`
- `s5a_exact_dedup_report.md`

`cluster_id` and `is_cluster_representative` are not assigned.
Tracked reports do not contain biological sequences. The multi-target
report uses `sequence_core_sha256` rather than the raw sequence.

## Not in S5A

- 90% sequence clustering (MMseqs2 / CD-HIT)
- S6 profile / CHECKPOINT-3
- S7 balancing, FT/REF/EVAL, splits
- NCBI/ENA duplicate-resolution workflow
- global S4 target-dictionary ID merge
- retyping or re-resolving frozen S4 targets
