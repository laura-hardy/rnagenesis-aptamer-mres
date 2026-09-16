# Combined global-S4 input contract

Sequence-safe architecture note for the corpus-wide pre-S4 concatenation.

This stage is **input preparation for global S4**, not global S4 itself.
It concatenates the eight authorised source-local handoffs into one
deterministic file. It does not extract targets, build a target dictionary,
assign evidence, apply leakage, or begin CHECKPOINT-2 / S5.

```text
source-local CHECKPOINT-1
        ->
source-local global-S4 handoff
        ->
THIS STAGE: combined pre-S4 input
        ->
future global S4
```

## Tracked contract

`config/global_s4_combined_input.json` is the single combination contract.
It names the eight contributing sources in explicit order, points at each
source handoff config, records expected counts, and states the aggregate
`2960`. Source discovery must not use filesystem glob order.

Configured contributing order:

```text
aptabase
utexas
aptadb
riboaptamer
aptaindex
ena
aptamerbase
ncbi_nuc
```

AptaDiff A/B are listed as `ready_zero_authorised`. They contribute no
rows and must not receive fabricated blank records.

## Combination rule

Row-preserving concatenation / union:

* every authorised handoff row appears exactly once;
* within each source, handoff row order is preserved;
* combined order is configured source order, then that within-source order;
* records are not joined, collapsed, or provenance-merged;
* identical sequences and identical sequence-target pairs remain separate.

The source-local handoffs are the only inputs. Combination must not
rebuild rows from S2, S3, authorised-ID lists, the registry, or source
metadata sidecars.

## Schema

Canonical columns occupy the live `CORPUS_COLUMNS` order first.
Source-specific extras follow, grouped by the same configured source
order, preserving each handoff's extra-column order. An extra used by
only one source is kept and is empty on other sources' rows.

A duplicate extra name, or an extra that collides with a canonical
column, fails closed. Combination must not rename scientifically
ambiguous fields.

Canonical scientific values are copied exactly. Source extras must not
populate:

```text
target_name
target_uniprot
target_type
target_type_source
target_family
target_pfam
pdb_id
binding_evidence_type
binding_evidence_score
affinity_value
affinity_unit
affinity_type
cluster_id
is_cluster_representative
partition
```

`contributing_sources` and `corroboration_count` remain the source-local
handoff values. Cross-source merged provenance belongs after later
deduplication.

## Outputs

Ignored under `data/`:

* `data/interim/global_s4/combined_global_s4_input.csv`
* `data/interim/global_s4/combined_global_s4_input_summary.md`
* `data/interim/global_s4/combined_global_s4_input_manifest.json`

These sit beside, not inside, `data/interim/global_s4_ready/`, which
holds source-local handoffs only.

The CSV may contain sequences. The summary and manifest must not.

## Orchestration

`scripts/data_preparation/combine_global_s4_input.py` is a separate
combiner. It must not be folded into `prepare_global_s4_source.py`, which
remains the source-local handoff builder.
