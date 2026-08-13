# UTexas global-S4 handoff

Sequence-free handoff note for the future corpus-wide S4 stage.

## Authoritative pipeline status

```text
UTexas S1 complete
UTexas S2 complete
UTexas S3 complete
CHECKPOINT-1 closed
468 records authorised for future global S4
```

For UTexas, `authorised_for_s4=true` means:

> Technically eligible after UTexas sequence/molecule CHECKPOINT-1 and
> eligible to enter the future corpus-wide target-normalisation stage.

It does **not** mean:

```text
protein target confirmed
target canonicalised
UniProt resolved
evidence threshold passed
leakage check passed globally
globally deduplicated
balanced
CHECKPOINT-2 approved
```

## CHECKPOINT-1 outcome (sequence-safe)

```text
final accept = 468
final park = 916
final reject = 510
authorised_for_s4 = 468

alphabet recoveries applied = 17
true IUPAC final rejects = 9
malformed final rejects = 1
complex construct final parks = 4
FANA / unresolved-molecule parks = 3
DNA / ssDNA parks = 909
missing-sequence rejects = 399
length_out_of_range rejects = 101
```

Unresolved trim/construct QC remains provenance on accepted records and is
not an eligibility gate under the UTexas source-specific CHECKPOINT-1
policy.

## Future global S4 behaviour

All 468 CHECKPOINT-1-authorised UTexas records must enter global S4.

Global S4 will consider UTexas alongside AptaBase, AptaDB, RiboAptamer,
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
No UTexas CHECKPOINT-2 currently exists.
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

* `data/interim/global_s4_ready/utexas_global_s4_input.csv`
* `data/interim/global_s4_ready/utexas_global_s4_handoff_summary.md`

Tracked config:

* `config/global_s4_sources/utexas.json`
