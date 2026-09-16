# Global S4 after CHECKPOINT-2 application

Sequence-safe architecture note. CHECKPOINT-2 human review has been
applied to the 2960-row combined global-S4 input. This is the
authoritative reviewed S4 corpus at **relationship grain**. S5 has
not started.

```text
combined_global_s4_input (2960 source records, immutable)
        ->
reviewed relationship projection
        ->
reviewed target dictionary projection
        ->
reviewed evidence projection
        ->
reviewed affinity projection
        ->
leakage projection
        ->
final S4 routing
        ->
reviewed global S4 output
        ->
STOP. S5 is a later milestone.
```

## Grain

One reviewed output row is one reviewed `(sequence, target)`
relationship, not necessarily one original source record.

Confirmed multi-target records expand. Rejected and overridden
relationships collapse to the surviving target. Relationship-parked
source records and target-scientific-park relationships produce no
active corpus relationship row; they remain in the record map and
park/exclusion audit.

Combined input is not overwritten. Source-local extra columns stay on
the combined file and are reachable through `record_id`.

## Target dictionary

Reviewed decisions (205):

* `approve_proposal` / `override` enter the resolved reviewed set
* `park_unresolved` is a scientific park (five identities)
* `exclude_no_active_relationship` is inactive, not a scientific
  rejection (36 identities)

Expected reviewed-resolved count is **164**, including the
human-derived cAMP identity `TDHc92005d63414` exactly once:

`3',5'-cyclic adenosine monophosphate (cAMP)` / `small_molecule` /
`other`.

Unreviewed machine dictionary identities that were never flagged for
CHECKPOINT-2 remain as deterministic carry-forward. They are required
so every active relationship has canonical metadata. Dictionary IDs
are not merged merely because canonical names are equal (Apramycin,
PSMA, ATP, NF-kappaB spelling variants, and similar). ID merging is
S5.

## Evidence

Effective evidence precedence:

1. supplemental evidence-consistency correction (`C2EC*`)
2. original C2E review (`C2E0001`–`C2E0003`)
3. machine evidence

Application requires zero evidence-affinity inconsistencies.

## Affinity

Reviewed outcomes use the existing projection helper.

* `confirm_affinity_scalar` may populate canonical molar fields only
  for a per-record safe scalar
* `retain_affinity_raw` keeps raw/qualifier/range provenance; canonical
  scalar stays blank
* `exclude_non_affinity` keeps the non-affinity reason; canonical
  affinity stays blank

LOD, binding percentage, `no binding`, rate constants, assay captions,
TBD, and N/A never become canonical affinity values. Unreviewed
machine rows that already parsed as a single normalised scalar keep
that machine molar value.

## Leakage

The established S4 matcher is re-run on reviewed relationships
(comparison U→T, full/core, global Levenshtein, 0.90 threshold, alias
exact/normalised/family-token logic, no local-substring matching).
This is evaluation-reference leakage, not ordinary cross-source
deduplication.

## Routing

Existing vocabulary only. Precedence: leakage → relationship park →
unresolved relationship → target scientific park → no-binding reject →
non-protein park → E5 park → protein primary (E1–E4). Unknown target
type on an otherwise resolved relationship is `hold_target_unresolved`.

`reject_no_binding_evidence` remains valid even if later target
metadata looks usable. The three AptamerBase `no binding` records must
not become primary candidates.

Non-protein effective types park; their reviewed S4 provenance is
kept.

## S4 / S5 boundary

S4 application does **not**:

* exact-deduplicate `(sequence_core, target_name)`
* merge provenance across sources
* resolve NCBI/ENA duplicates
* cluster sequences (MMseqs/CD-HIT or otherwise)
* balance or cap targets
* assign FT / REF / EVAL
* split train/validation/test

Duplicate `(sequence_core, canonical_target_name)` observations may be
counted only, labelled `S5 diagnostic only`.

## Outputs

All under ignored `data/interim/global_s4/`:

* `global_s4_reviewed_relationships.csv`
* `global_s4_reviewed_target_dictionary.csv`
* `global_s4_record_relationship_map.csv`
* `global_s4_parked_excluded_audit.csv`
* `global_s4_routing_summary.csv`
* `checkpoint2_application_summary.json`
* `checkpoint2_application_manifest.json`

Handoff to S5 is those reviewed relationship rows plus the dictionary,
record map, and audit. Combined input remains the extras/provenance
sidecar.
