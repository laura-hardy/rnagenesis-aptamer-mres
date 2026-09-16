# CHECKPOINT-2 supplemental evidence-consistency review

Architecture note for Milestone 4F.3. This stage recorded the nine
authorised C2EC human decisions as `override_evidence`. The frozen
3-row E4/E5 evidence review is not modified. Milestone 5 later applied
CHECKPOINT-2; S5 remains out of scope.

```text
completed target / relationship / evidence / affinity review
        ->
4F.1: read-only 49-flag reconciliation (9 scientific groups)
        ->
4F.2: blank C2EC0001–C2EC0009 package
        ->
THIS STAGE: record the nine human evidence-consistency decisions
        ->
Milestone 5: CHECKPOINT-2 applied (global S4 complete; S5 not started)
```

Milestone 5 applied CHECKPOINT-2. This supplemental file was not
modified. Effective evidence still uses the precedence below.

## Why a separate file

`checkpoint2_evidence_review.csv` is a frozen E4/E5-threshold grain
(`C2E0001`–`C2E0003`) with an accepted integrity hash. The 49 flagged
records are a different grain: cross-reconciliation between completed
evidence and completed affinity review. They are written to:

`data/interim/global_s4/checkpoint2/checkpoint2_evidence_consistency_review.csv`

## Decision-ID ordering

IDs are assigned independently of CSV row order:

1. Source/review groups from Milestone 4F.1:
   AptaBase `C2A0002`, AptaDB `C2A0004A`, AptaDB `C2A0004B`,
   AptamerBase `C2A0010`, RiboAptamer `C2A0014B`, RiboAptamer `C2A0016A`,
   RiboAptamer `C2A0016B`, UTexas `C2A0019`.
2. Within `C2A0004B`, the E3 remainder subgroup (`C2EC0003`) is assigned
   before the E5 annotation-only subgroup (`C2EC0004`).
3. Record membership is the frozen 4F.1 inventory.

## Recorded corrections

All nine rows are `override_evidence`. No E4 supplemental decision.

```text
C2EC0001 E2   4 AptaBase recovered quantitative Kd
C2EC0002 E3   9 AptaDB assay-caption false E2, qualitative binding remains
C2EC0003 E3  19 AptaDB foreign/non-row Kd removed, qualitative binding remains
C2EC0004 E5   6 AptaDB foreign/non-row Kd removed, annotation only
C2EC0005 E5   3 AptamerBase no-binding (not zero Kd)
C2EC0006 E3   2 RiboAptamer binding percentage
C2EC0007 E2   2 RiboAptamer recovered GRK2 Kd
C2EC0008 E2   3 RiboAptamer recovered glued-unit Kd
C2EC0009 E5   1 UTexas TBD placeholder
```

Record outcomes: 9 E2, 30 E3, 0 E4, 10 E5.

## Effective evidence precedence

Projection only; machine proposal tables are not rewritten:

1. completed supplemental `C2EC*` correction, if present;
2. else completed original `C2E0001`–`C2E0003` evidence review;
3. else machine `evidence_level_proposed`.

Only the 49 member records change effective evidence.

## Validator

After recording, supplemental C2EC rows are complete. Evidence-affinity
flags must be zero. `ready_for_application` became true. Milestone 5
applied CHECKPOINT-2 using this precedence.
