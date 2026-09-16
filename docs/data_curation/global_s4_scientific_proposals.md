# Global-S4 Milestone 3 — scientific proposals and CHECKPOINT-2 preparation

Sequence-safe architecture note. This stage proposes target type,
UniProt, family/Pfam, evidence, affinity, leakage, routing preview, and
a blank CHECKPOINT-2 package. It does not apply those proposals to the
2960-row combined input, populate human decisions, or run S5.
CHECKPOINT-2 application is documented separately in
`docs/data_curation/global_s4_checkpoint2_application.md`.

```text
combined pre-S4 input (2960 rows, immutable)
        ->
Milestone 2: raw target extraction + initial dictionary
        ->
THIS STAGE: machine scientific proposals + blank CHECKPOINT-2 package
        ->
Milestone 4: CHECKPOINT-2 human review
        ->
Milestone 5: CHECKPOINT-2 application (reviewed global S4)
        ->
STOP before S5
```

## Grain

* Combined input remains one row per authorised source record (`2960`).
* Scientific tables are proposal layers under ignored `data/interim/global_s4/`.
* Relationship-level proposals follow Milestone-2 relationship grain.
* CHECKPOINT-2 uses grouped decision units, not a 2960-row review.
* Human fields are fail-closed blank. The validator must report
  `ready_for_application = false`.

## RiboAptamer entry gate

`RA_SEQ_FIRST_UNDERSCORE` is valid only where Sequence Name
`{target}_{clone_or_variant}` encodes the ligand in the prefix and that
prefix is corroborated by Aptamer Name, Description, or publication text,
or where Aptamer Name is a clone/construct label and the prefix is a
descriptive ligand string.

Category and Type are not corroboration. Unsupported prefixes are
ambiguous or unresolved, not deterministic targets. Combined input is
unchanged.

## Target type

Closed vocabulary: `protein`, `peptide`, `small_molecule`, `ion`,
`nucleic_acid`, `cell`, `organism`, `other`, `unknown`.

Source category/chemistry/Type/RDF values are priors, not canonical
truth. `enzyme` maps to canonical `protein` with family clue `enzyme`.
Conflicts between identity and prior go to CHECKPOINT-2. Unknown is
allowed to remain unknown; it is not guessed from name morphology.

## UniProt

Protein/peptide only. Hierarchy:

1. U1 source-linked identifier (AptaDB seeds). Conflicting seeds for the
   same dictionary identity are not merged.
2. U2 existing local structured mappings (`data/raw/AptaDB/protein.csv`).
3. U3 official UniProt REST, cached under ignored `data/`, only when
   enabled. Automatic acceptance requires an unambiguous exact name
   match. Network disabled or failed leaves the field unresolved.

Domain/fragment/complex context is preserved. A parent UniProt may be
proposed with `target_region_or_fragment` and CHECKPOINT-2.

## Family / Pfam

Family is assigned only after type is sufficiently resolved. Closed
family vocabulary includes `enzyme`, `receptor`, `cytokine`,
`growth_factor`, `antibody_immunoglobulin`, `transcription_factor`,
`structural_protein`, `viral_protein`, `bacterial_surface_protein`,
`transport_protein`, `other`, `unknown`.

Non-protein targets receive family `other`. Missing Pfam/InterPro is
blank and is never an exclusion.

## Evidence

Ladder E1–E5 (scores 5–1). Highest defensible level wins; supporting
signals remain in provenance. This stage does not exclude or park.

E1 requires a verified aptamer–target complex. An mmCIF URL or
`has_experimentally_determined_structure=true` is not E1. Buffer/conditions
alone are not E3. LOD is not E2. Publication presence alone is not E4.

E4/E5 threshold ambiguities are grouped CHECKPOINT-2 evidence decisions.
Deterministic E2/E3/E4 assignments are not individual human reviews.

## Affinity

Raw source values are retained. Canonical molar values are proposed only
for a single scalar with a supported unit (M, mM, µM/uM, nM, pM).
Ranges, inequalities, approximate verbal values, and malformed units
stay blank. Ka is not converted to Kd. Review is grouped by source parse
pattern, not one row per missing numeric affinity.

No molar scalar is invented to fill canonical columns. Inequalities keep
an operator and bound; ranges are not collapsed to a midpoint. LOD,
assay captions, binding percentages, rates, `N/A`, `TBD`, and “no
binding” are `exclude_non_affinity` and must not populate canonical
affinity or count as E2. Grouped review rows may name a per-record
transform (for example AptaBase mojibake `�M` → µM) instead of one
shared scalar. See
`docs/data_curation/checkpoint2_affinity_review_semantics.md`.

## Leakage

Existing leakage matcher only: exclusion set, target aliases, U/T
comparison, full/core, global Levenshtein, 0.90 threshold. Proposal mode
does not apply exclusions. Ordinary corpus duplication is not leakage.

## Routing preview

Not applied. Precedence: leakage → unresolved/ambiguous target → no-binding
reject → E4/E5 evidence hold → non-protein park → E5 park → protein
primary candidate (E1–E4).

## CHECKPOINT-2

Linked tables:

* target dictionary review (flagged dictionary units, records descending)
* relationship / multi-target review
* evidence review (E4/E5 threshold patterns only)
* affinity review (recoverable parse patterns; affinity-specific
  outcomes in `checkpoint2_affinity_review_semantics.md`)
* evidence-consistency review (supplemental `C2EC*` rows; does not
  reopen `C2E0001`–`C2E0003`; see
  `checkpoint2_evidence_consistency_review.md`)
* leakage review (borderline matches only)

Evidence-affinity inconsistencies block CHECKPOINT-2 application until
reconciled. They do not silently mutate the closed evidence review.

Permitted `manual_decision` values are documented in the package README.

Relationship review precedes effective target-dictionary application.
A machine dictionary candidate with no surviving reviewed resolved
relationship is **inactive**, not an unresolved biological target.
`exclude_no_active_relationship` records that state. It is valid only
when zero effective resolved relationships still reference that
dictionary identity. Machine-derived provenance distinguishes
`superseded_by_relationship_review` from `parked_relationship_only`.
Both are excluded from the resolved effective dictionary; parked-only
rows keep parked-relationship provenance for audit. This is not
scientific rejection, leakage exclusion, or a global target blacklist.

Relationship `override` reuses an existing dictionary identity only on
an exact name match. Otherwise it creates a deterministic
human-derived dictionary identity (`TDH…`) from the manual name and
type, with relationship-override provenance. No fuzzy merge is
performed. The new identity still requires a target-level decision
before it enters the resolved dictionary. S5 deduplication remains
out of scope.

Milestone 4A.1 recorded 15 target-dictionary Batch-1 human decisions
without applying them. Milestone 4B.1 recorded 34 authorised
relationship Batch-1 human decisions without applying them. Milestone
4B.2 recorded 18 relationship-unlocked target-dictionary overrides
(33/204 target decisions resolved). Milestone 4B.4 recorded 30
authorised relationship Batch-2 human decisions (10 withheld because
reject semantics would retain the wrong relationship). Milestone
4B.4A recorded those 10 withheld rows as relationship-level
`override` (74/107 relationship decisions resolved). Milestone
4B.6 recorded the remaining 33 relationship decisions (107/107
relationship decisions resolved; 8 parked). Milestone 4C.2 recorded
40 active target-dictionary Batch-2 human decisions (31
`approve_proposal`, 9 family `override`; 73/204 target decisions
resolved). Milestone 4C.3 added inactive-target and override-identity
semantics without populating the 36 non-active target rows or the
cAMP review row. Milestone 4C.4 recorded those 36 rows as
`exclude_no_active_relationship` (109/204 target decisions resolved).
Milestone 4C.5 materialised and approved the human-derived cAMP
identity `TDHc92005d63414` (110/205 target decisions resolved).
Milestone 4C.7 recorded 40 active target-dictionary Batch-3 human
decisions (32 `override`, 7 `approve_proposal`, 1 target-level
`park_unresolved`; 150/205 target decisions resolved). Milestone 4C.9
recorded the remaining 55 active target-dictionary decisions (15
`approve_proposal`, 36 `override`, 4 target-level
`park_unresolved`; 205/205 target decisions resolved). Target review
is complete. Milestone 4D.2 recorded the 3 evidence decisions
(3/3; all E5). Milestone 4E.2 added affinity-specific review outcomes
and a projection helper. Milestone 4E.3 materialised the 19-row
affinity package into 31 scientifically coherent review rows. Milestone
4E.4 recorded all 31 affinity decisions (4 exact-scalar transforms,
15 retain-raw, 12 non-affinity, 0 parks). Human affinity review is
complete. Milestone 4F.2 materialised a blank 9-row supplemental
evidence-consistency package (`C2EC0001`–`C2EC0009`). Milestone 4F.3
recorded all nine C2EC decisions as `override_evidence` (3 E2, 3 E3,
3 E5; record outcomes 9 E2 / 30 E3 / 10 E5). Evidence-affinity flags
49 → 0. The frozen 3-row evidence review was not modified.
`ready_for_application = true`. Milestone 5 applied CHECKPOINT-2 and
wrote the reviewed global-S4 relationship corpus. S5 has not started.
See `docs/data_curation/global_s4_checkpoint2_application.md`.

## Scientific boundary

No proposals written into combined input. No final
`all_sources_merged.csv`. No S5 dedup, clustering, balancing, or
partition.
