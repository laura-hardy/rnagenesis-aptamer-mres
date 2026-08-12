# AptaBase global-S4 handoff

Sequence-free handoff note for the future corpus-wide S4 stage.

## Authoritative pipeline status

```text
AptaBase S1 complete
AptaBase S2 complete
AptaBase S3 complete
CHECKPOINT-1 closed
162 records authorised for future global S4
```

For AptaBase, `authorised_for_s4=true` means:

> Technically eligible after sequence/molecule CHECKPOINT-1 and eligible to
> enter the future corpus-wide target-normalisation stage.

It does **not** mean:

```text
protein target confirmed
target canonicalised
UniProt resolved
evidence threshold passed
leakage check passed globally
CHECKPOINT-2 approved
```

## Why the provisional S4 was not retained

The curation plan specifies target normalisation as a **corpus-wide stage after
per-source cleaning**:

```text
per-source S1 → S2 → S3/CHECKPOINT-1
                    ↓
              merge clean sources
                    ↓
                GLOBAL S4
        target dictionary + CHECKPOINT-2
                    ↓
                GLOBAL S5
```

A provisional AptaBase-only S4 was useful for inspecting the target-metadata
schema and source category labels. Its target decisions were exploratory only,
are **not authoritative**, and were deliberately discarded before commit.

No AptaBase CHECKPOINT-2 currently exists.

## Useful observations retained

`aptabase_target_general` is categorical (broad source labels, not free-form
general target names). Among the 162 CHECKPOINT-1-authorised records the
observed category counts are:

```text
Protein = 113
Small Organic = 37
Peptide = 6
Cells = 5
Antibody = 1
```

These counts are **source observations**, not final target classifications.
They must not be treated as:

```text
Protein -> accept
Antibody -> accept
Small Organic -> reject
Cells -> reject
Peptide -> park
```

Final target-type and eligibility decisions belong to global S4.

Among the same 162 authorised records:

```text
aptabase_target_specific present = 162
specific target missing = 0
```

There are no AptaBase source columns providing:

```text
UniProt
PDB
Pfam
target family
```

These observations may be used as **source evidence** during global S4.

## Future global S4 behaviour

All 162 CHECKPOINT-1-authorised AptaBase records must enter global S4.

Global S4 will consider AptaBase alongside UTexas, AptaDB, RiboAptamer,
AptamerBase, ENA, AptaIndex, AptaDiff and the other included sources.

Global S4 will then:

* collect raw target strings across all sources;
* create one shared target dictionary;
* reconcile synonyms across databases;
* seed protein identities using AptaDB protein metadata;
* resolve UniProt where appropriate;
* assign canonical target names;
* assign target type;
* assign target family;
* apply evidence eligibility;
* apply corpus-wide target leakage rules;
* emit the real CHECKPOINT-2.

```text
No AptaBase CHECKPOINT-2 currently exists.
```

Handoff artefacts (ignored under `data/`):

* `data/interim/global_s4_ready/aptabase_global_s4_input.csv`
* `data/interim/global_s4_ready/aptabase_global_s4_handoff_summary.md`

Tracked config:

* `config/global_s4_sources/aptabase.json`
