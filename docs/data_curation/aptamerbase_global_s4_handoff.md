# AptamerBase global-S4 handoff

Sequence-free handoff note for the future corpus-wide S4 stage.

## Authoritative pipeline status

```text
AptamerBase S0 complete
AptamerBase S1 complete and frozen
AptamerBase S2 complete
AptamerBase S3 complete
CHECKPOINT-1 applied and closed
881 records authorised for future global S4
```

For AptamerBase, `authorised_for_s4=true` means:

> Technically eligible after AptamerBase sequence/molecule/chemistry/construct
> CHECKPOINT-1 and prepared as an input to the future corpus-wide global S4
> stage.

It does **not** mean:

```text
target identified
target canonicalised
protein target confirmed
UniProt resolved
evidence threshold passed
affinity resolved
PDB resolved
leakage cleared
final corpus included
deduplicated
clustered
balanced
partitioned
CHECKPOINT-2 approved
```

## Handoff source

This handoff is a pure selection/join from the authoritative CHECKPOINT-1
applied state:

* applied canonical:
  `data/interim/checkpoints/aptamerbase_cp1/resolved/aptamerbase_checkpoint1_applied_canonical.csv`
* authorised IDs:
  `data/interim/checkpoints/aptamerbase_cp1/resolved/aptamerbase_checkpoint1_s4_authorised_ids.csv`
* tracked config:
  `config/global_s4_sources/aptamerbase.json`

It is not taken from S1 extracted, S2 normalised, pre-review S3, or dry-run
output.

## Physical source grain

AptamerBase remains a flattened RDF/Freebase source. The 881 authorised
physical source records remain 881 handoff rows.

Do not collapse this handoff by:

```text
Freebase ID
sequence
label
minimal-aptamer parent relationship
exact duplicate row
```

`record_id` is the physical-row reconciliation key. Deduplication remains S5.

## Canonical target/evidence boundary

Canonical `target_name_raw` is deliberately empty. AptamerBase `label` is
retained only as sidecar source metadata (`aptamerbase_label`) and must not
be copied into `target_name_raw`.

All global-S4-and-later canonical fields remain empty:

```text
target_name_raw
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

## Freebase ID as future S4 join key

AptamerBase future target/evidence enrichment must join through:

```text
record_id
  -> S1 sidecar AptamerBase Freebase ID (aptamerbase_id)
  -> AptamerBase interaction/experiment graph/tables
```

The Freebase ID is **not**:

```text
record_id
native_id
target ID
dedup key
```

It is source provenance / a future source-metadata join key. Every authorised
handoff row must have a nonempty Freebase ID.

## Future global-S4 prerequisite

Before AptamerBase target/evidence normalisation begins, hash-pin the
original-authors interaction and experiment companion tables (or equivalent
RDF graph representation) and join them by Freebase ID/interaction
relationships.

Those companion tables are **not** registered in this handoff. This
preparation is still pre-global-S4.

Do not interpret:

```text
has_experimentally_determined_structure = E1
structure boolean = PDB
PMID-like labels = publication identifiers
source label = protein/non-protein class
```

SOURCE METADATA ONLY — NOT CANONICAL TARGET/EVIDENCE DECISIONS.

## Future global S4 behaviour

All 881 CHECKPOINT-1-authorised AptamerBase records must enter global S4 as
physical source rows.

Global S4 will consider AptamerBase alongside AptaBase, UTexas, AptaDB,
RiboAptamer, ENA, AptaIndex, AptaDiff and the other included sources.

```text
No AptamerBase CHECKPOINT-2 currently exists.
target_name remains unresolved
target_type remains unresolved
protein/non-protein filtering not performed
Kd/Affinity evidence not scored
leakage not applied
global deduplication not performed
balancing not performed
partitioning not performed
global S4 executed = no
```

Handoff artefacts (ignored under `data/`):

* `data/interim/global_s4_ready/aptamerbase_global_s4_input.csv`
* `data/interim/global_s4_ready/aptamerbase_global_s4_handoff_summary.md`

Tracked config:

* `config/global_s4_sources/aptamerbase.json`
