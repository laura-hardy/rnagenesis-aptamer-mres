# Global-S4 Milestone 2 — raw target extraction

Sequence-safe architecture note for the first corpus-wide target
milestone. This stage proposes source-supported raw target relationships
and an initial machine dictionary. It does not apply final canonical
target identity, target type, UniProt, family/Pfam, evidence, affinity,
leakage, CHECKPOINT-2 decisions, or S5.

```text
combined pre-S4 input (2960 rows, immutable)
        ->
THIS STAGE: raw target extraction + initial dictionary proposal
        ->
future Milestone 3 / CHECKPOINT-2
```

## Grain

* Combined input remains one row per authorised source record (`2960`).
* Record extraction is 1:1 with combined `record_id`.
* One eventual corpus record is still one `(sequence, target)` pair, but
  this milestone does **not** expand the combined input.
* If source provenance supports more than one distinct target, the
  extra relationships go to `target_relationship_proposals.csv`.

## Vocabularies

`relationship_status` means only that the **source relationship** is
mechanically identifiable. It does not mean canonical target review is done.

| status | meaning |
|---|---|
| `resolved_single` | one source-supported target relationship |
| `resolved_multiple` | two or more distinct source-supported relationships; expansion is proposed, not applied |
| `ambiguous` | source text/graph is compatible with more than one scientific reading |
| `unresolved` | no source-supported target relationship was extracted |

`extraction_confidence`:

| value | meaning |
|---|---|
| `high` | existing structured `target_name_raw`, or an explicit RDF `aptamer_target` / explicit GenBank binding phrase |
| `medium` | deterministic free-text or secondary RDF counterpart without `aptamer_target` type |
| `low` | weak but still source-supported candidate |
| `unresolved` | no target extracted |

## Source pathways

Structured sources (`aptabase`, `utexas`, `aptadb`, `aptaindex`, `ena`)
preserve existing `target_name_raw` exactly. Source category/chemistry
values are priors only.

RiboAptamer uses Sequence Name `{target}_{clone}` when the prefix is
corroborated by Aptamer Name, Description, or publication text, or when
Aptamer Name is a clone/construct label and the prefix is a descriptive
ligand string. Unsupported or clone-like prefixes are unresolved.
Conflicting Aptamer Name vs Sequence Name identities are ambiguous.
Category and Type are never substituted for a target name.

AptamerBase uses the local RDF path:

```text
aptamer Freebase ID
  -base.aptamer.interactor.is_participant_in-> interaction
  -base.aptamer.interaction.has_participant-> counterpart
```

The aptamer's own label is never the target. Other aptamer participants
and experiment/affinity/structure nodes are skipped. English
`rdfs:label` on `base.aptamer.aptamer_target` nodes is the raw target.
`aptamer_target.has_type` is a source type prior only.

NCBI uses DEFINITION / FEATURE notes only when they explicitly state
that the aptamer binds / is specific for / is an X-binding aptamer.
Organism, title-only mentions, and dual “targeting A and B” statements
are not auto-resolved.

## Dictionary

Grouping is by primary match key (Unicode NFC, trim, collapse
whitespace, casefold), **except** AptaDB rows with conflicting
source-UniProt seeds remain separate entries.

An alias-candidate key (punctuation-insensitive) is emitted for later
review. It does not auto-merge entries.

Machine `canonical_target_name_proposal` is the most frequent exact raw
string in the group. It is not written into canonical `target_name`.

CHECKPOINT-2 does not fuzzy-merge dictionary identities. A relationship
override reuses a dictionary ID only on an exact name match; otherwise
it creates a new human-derived identity. Machine candidates that lose
all resolved relationships are inactive dictionary rows, not merged
aliases. S5 deduplication is out of scope here.
