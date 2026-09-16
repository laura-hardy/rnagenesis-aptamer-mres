# AptaDB global-S4 handoff

Sequence-free handoff note for the future corpus-wide S4 stage.

## Authoritative pipeline status

```text
AptaDB S0 complete
AptaDB S1 complete
AptaDB S2 complete
AptaDB S3 complete
CHECKPOINT-1 applied and closed
151 interaction records authorised for future global S4
```

For AptaDB, `authorised_for_s4=true` means:

> Technically eligible RNA-protein interaction records after AptaDB
> sequence/molecule/target-chemistry CHECKPOINT-1 and prepared as an
> input to the future corpus-wide global S4 stage.

It does **not** mean:

```text
target canonicalised
UniProt copied into canonical target_uniprot
evidence threshold passed
E3 inferred from Binding Conditions/Buffer
affinity resolved
PDB resolved into canonical pdb_id
leakage cleared
unlinked aptamers included
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
  `data/interim/checkpoints/aptadb_cp1/resolved/aptadb_checkpoint1_applied_canonical.csv`
* authorised IDs:
  `data/interim/checkpoints/aptadb_cp1/resolved/aptadb_checkpoint1_s4_authorised_ids.csv`
* tracked config:
  `config/global_s4_sources/aptadb.json`

It is not taken from S1 extracted, S2 normalised, pre-review S3, old
eligible lists, or dry-run output.

## Interaction denominator

The CHECKPOINT-1 interaction stream remains 1350 records:

```text
technically eligible RNA-protein = 151
parked ssDNA = 1037
parked RNA non-protein = 115
interaction-stream rejects = 47
```

Only the 151 authorised RNA-protein interaction records belong in this
handoff. Unique `record_id` = 151.

The 37 unlinked aptamers remain separate source-level `missing_target`
records outside the 1350 interaction denominator and are not selected.

## Physical source grain

AptaDB remains an interaction-grain source. The 151 authorised interaction
records remain 151 handoff rows.

Do not collapse this handoff by:

```text
Apta_index
source UniProt
TargetID
sequence
```

`record_id` is the physical-row reconciliation key. Deduplication remains a
later global stage.

## Source provenance retained, not canonicalised

Structured AptaDB protein/interaction metadata is joined one-to-one from
the frozen S1 sidecar and retained as SOURCE extras, including:

```text
interaction Index
Apta_index
source protein names / entry name / gene names
source UniProt (aptadb_uniprot_id)
source Target chemistry
source PubMed ID
source Binding Conditions/Buffer
source assay / function / applications
source PDB cross-reference
protein and aptamer join status
```

These extras are **not** copied into canonical S4 fields.

Canonical `target_name_raw` retains its already-approved applied
CHECKPOINT-1 protein-names value. It is not recanonicalised here.

All global-S4-and-later canonical fields remain empty:

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

Do not interpret Binding Conditions/Buffer as E3. Do not convert the
source PDB cross-reference into canonical `pdb_id`.

`redistribution_status` remains the registry/checkpoint value `unknown`.

SOURCE METADATA ONLY — NOT CANONICAL TARGET/EVIDENCE DECISIONS.

## Future global S4 behaviour

All 151 CHECKPOINT-1-authorised AptaDB interaction records must enter global
S4 as physical source rows.

Global S4 will consider AptaDB alongside AptaBase, UTexas, RiboAptamer,
AptamerBase, ENA, AptaIndex, AptaDiff and the other included sources.

```text
No AptaDB CHECKPOINT-2 currently exists.
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

* `data/interim/global_s4_ready/aptadb_global_s4_input.csv`
* `data/interim/global_s4_ready/aptadb_global_s4_handoff_summary.md`

Tracked config:

* `config/global_s4_sources/aptadb.json`
