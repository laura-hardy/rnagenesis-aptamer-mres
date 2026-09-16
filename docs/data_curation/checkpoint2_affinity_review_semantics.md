# CHECKPOINT-2 affinity review semantics

Architecture note for Milestones 4E.2–4E.3. Affinity review can now
close truthfully. Later milestones recorded the 31 affinity decisions
and applied CHECKPOINT-2; this file documents the affinity grain.
S5 remains out of scope.

```text
completed target / relationship / evidence review
        ->
4E.2: affinity outcome model + projection helper
        ->
THIS STAGE: controlled affinity-row split/materialisation (19 -> 31)
        ->
4E.4: 31 human affinity decisions recorded
        ->
4F.3: C2EC evidence-consistency recorded (49 flags -> 0)
        ->
Milestone 5: CHECKPOINT-2 applied (global S4 complete; S5 not started)
```

## Gap this stage closes

The shared CHECKPOINT-2 `manual_decision` vocabulary had no first-class
affinity outcomes. `override` requires target name/type and must not be
used here. Grouped rows share one value/unit pair, which cannot store
one scalar for many source numbers. Canonical corpus columns remain
scalar-only (`affinity_value`, `affinity_unit`, `affinity_type`).

## Affinity outcome vocabulary

Affinity-only completed decisions:

| `manual_decision` | Meaning | Canonical scalar |
|---|---|---|
| `confirm_affinity_scalar` | One exact scalar/type/unit is accepted, applied **per source record** | molar `M` if safe |
| `retain_affinity_raw` | Valid affinity information; no scientifically safe exact scalar | blank |
| `exclude_non_affinity` | Source value is not an affinity measurement | blank |
| `park_unresolved` | Source cannot be interpreted confidently | blank |

`retain_affinity_raw` and `exclude_non_affinity` are completed review
outcomes, not unresolved blanks. `park_unresolved` is the existing
scientific-deferral token, reused rather than duplicated.

Do not use target `override` for affinity.

## Reviewed representation

Canonical columns stay scalar-only. Reviewed metadata may live on the
affinity-review row and in the projection sidecar:

- `manual_affinity_type` (`Kd` / `Ki` / `IC50` / `EC50` / `Ka` / `other`)
- `manual_affinity_value` / `manual_affinity_unit` (exact scalar only)
- `manual_affinity_qualifier` (`<` `<=` `>` `>=` `>>` `approximate`)
- `manual_affinity_range_status` (`range` / `list` / `multi_condition`)
- `manual_affinity_transform_rule` (per-record source rule)
- `manual_affinity_non_affinity_reason`

A reviewed record is not required to have a molar scalar. No scalar is
invented to satisfy the canonical schema. Ranges are not collapsed to a
midpoint. Inequalities store a bound, not an exact affinity.

### Transform rules (grouped row → per-record values)

A grouped review row may name a rule. The helper applies it to each
record's own source text:

| rule | Example |
|---|---|
| `mojibake_micro_M` | AptaBase `�M` recovered as `µM`; each number × 1e-6 M |
| `glued_unit` | `50nM` |
| `scientific_notation` | `2 x 10^-5 M` |
| `central_value_uncertainty` | `78.2 nM±2.6 nM` → 78.2 nM |
| `parse_inequality_bound` | `<1.0 pM` → qualifier `<`, bound `1e-12` M, no exact scalar |

Do not store one review-row scalar for a multi-value group.

### Non-affinity invariant

```text
exclude_non_affinity
  => canonical affinity_value blank
  => canonical affinity_unit blank
  => value cannot trigger quantitative-affinity evidence
```

Raw source text is retained. Reasons: `lod`, `assay_caption`,
`mentioned_foreign_kd`, `binding_percentage`, `rate`, `missing_value`,
`no_binding`, `placeholder`.

### Missing units

- Deterministically recoverable: AptaBase mojibake `�M` → `µM` via
  `mojibake_micro_M`. Not inferred from magnitude.
- Unrecoverable (AptamerBase unitless RDF; `Kd: 325`):
  `retain_affinity_raw`, no normalised scalar. Do not infer nM.

## Parser defects (deterministic only)

Fixed in `s4_affinity.py` for future parse/projection. Machine proposal
tables were **not** regenerated:

1. scientific-notation hyphen is not a range (`2 x 10^-5 M`, `2e-5`, `>30E-06`);
2. glued units (`50nM`);
3. central value plus trailing-unit uncertainty (`78.2 nM±2.6 nM`);
4. explicit missing forms (`Kd: NA`).

## Group split

The original machine grouping was
`(source_db, affinity_parse_status, affinity_parse_rule)`. Milestone
4E.3 materialised heterogeneous groups into one review row per
scientific subgroup. Child decision IDs are `{parent}{A|B|…}` from a
documented subgroup order, not row order. Unsplit rows keep the parent
ID. Parent IDs of split groups are not reused as children.

Unsplit when one scientific rule covers the group (including C2A0002:
one µM rule, per-record numbers). Split when one rule cannot govern all
records. Human affinity fields stay blank until later recording.

Live package after 4E.3: 31 affinity review rows; all human fields
blank; unresolved CHECKPOINT-2 decisions = 31.

Milestone 4E.4 recorded all 31 human affinity decisions
(`confirm_affinity_scalar` 4, `retain_affinity_raw` 15,
`exclude_non_affinity` 12, `park_unresolved` 0). Exact scalars use
per-record transform rules, not one review-row number.

Milestone 4F.2 materialised a separate blank 9-row consistency
package (`C2EC0001`–`C2EC0009`). Milestone 4F.3 recorded all nine
as `override_evidence`. See `checkpoint2_evidence_consistency_review.md`.

## Evidence-affinity consistency

The closed evidence-review CSV is not reopened. Supplemental C2EC
rows are a separate grain. Before application, flags use effective
evidence (completed C2EC, else C2E0001–C2E0003, else machine):

```text
exclude_non_affinity AND machine evidence == E2 from that same value
  => evidence_affinity_inconsistency

reviewed exact quantitative affinity
  AND machine evidence weaker than E2
  => evidence_affinity_inconsistency
```

Flags block `ready_for_application` until reconciled. They do not
mutate evidence. Milestone 4F.3 recorded the nine C2EC overrides
and cleared the 49 flags. Milestone 5 later applied CHECKPOINT-2.
S5 has not started.

## Projection helper

`adapters.checkpoint2_affinity.project_affinity_reviews` returns an
effective reviewed affinity projection without touching combined input.
Parked target/relationship records keep canonical affinity blank.
This is not a CHECKPOINT-2 apply CLI.

## Validator

An affinity row is completed when it has one permitted affinity outcome,
even if the normalised scalar is blank. Contradictory combinations are
rejected (non-affinity plus scalar; exact scalar with neither value/unit
nor a scalar transform; range/raw with a fake exact scalar; parked with
incompatible fields).

## S5

Out of scope.
