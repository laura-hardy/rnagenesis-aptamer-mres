# AptaRank + RNAGenesis MRes Thesis Evaluation — Final Future-Shortlisting Amendment

## 1. Status, timing and authority

| Item | Decision |
|---|---|
| Status | Active final-disposition amendment adopted after completion of Sections 6–10 and consultation with the biology supervisor. |
| Base evidence | The closed Section 10 run and its original 100-candidate gated review pool remain unchanged historical results under v3.8/v3.9. |
| Scope | Version 3.10 replaces the pending candidate-specific supervisor review and experimental-progression decision. It does not alter any AptaRank run, score, rank, exclusion, raw export or earlier evaluation conclusion. |
| Timing | Outcome-aware: adopted after the Section 10 results, the two alternative 100-candidate review options, the NDM-1 cavity warning and the broader generator evaluation were available. It must not be described as prespecified. |
| Authorization | Explicit project-owner instruction following supervisor consultation, 30 October 2026. |

The scientific reason for the amendment is that the available evidence does not support progressing any MRes sequence to experimental validation. The selected NDM-1 pocket carries a substantial geometry warning, the known-cognate Tier 2 panel was weak to mixed, and D1 did not establish a decisive advantage over the B2 TRAIN-matched non-neural null model across the sequence and structural evaluation. These limitations do not invalidate the completed computational work, but they narrow what its final output can claim.

## 2. Final thesis outcome

No candidate generated or prioritised in the MRes thesis is advanced to experimental validation.

The final sequence-bearing output is instead described as **50 candidates progressing towards shortlisting for experimental validation**. These candidates are retained for possible future consideration only after a better computational prioritisation and evaluation approach has been developed. They are not a validated binder set, an experimental shortlist, or a recommendation to begin laboratory work.

## 3. Tier-1-led future-shortlisting rule

Apply the following rule to the already validated Section 10 scored export. Do not run AptaRank again.

1. Start from candidates with a valid exported Tier 1 score and a complete provenance join.
2. Order candidates by the existing AptaRank Tier 1 rank. The deployed export already resolves an exact Tier 1 tie by ascending stable opaque candidate ID.
3. Define the sensitivity-review pool as Tier 1 ranks 1–100, corresponding to the previously prepared Tier-1-only review option.
4. Retain Tier 1 ranks 1–50 as the final future-shortlisting set.
5. Preserve the candidate-specific shuffle token and exact Tier 2 target-control percentile, mismatch and band as coarse annotations only. They are not eligibility gates, ordering variables or evidence of NDM-1 binding.
6. Do not create a numerical Tier 1/Tier 2 composite, replace an excluded sequence, replenish the set, or use manual preference to reorder it.

This is a deliberate loosening of the original Section 10 gate-based review rule after observing the evaluation evidence. The historical 137 jointly eligible and 100 retained gated candidates remain part of the closed Section 10 result; they are not silently redefined by this amendment.

## 4. Required retained fields

For every one of the 50 candidates, retain:

- future-shortlisting order and AptaRank Tier 1 rank;
- opaque AptaRank candidate ID and D1 source candidate ID;
- RNA sequence, length and sequence SHA-256;
- exact Tier 1 score;
- candidate-specific shuffle token;
- exact Tier 2 target-control percentile, geometric mismatch and compatibility band;
- D1 training seed and technical block;
- source record identity, checkpoint identity, generation seed, invocation index, master-attempt index and requested biological length;
- frozen source-artifact identifier and digest; and
- the NDM-1 cavity-geometry warning and the claim boundary governing future use.

The output must reconcile every sequence and identifier to the frozen Section 10 export and restricted provenance keys. Input and output files must be hashed. Failed, duplicated or incomplete joins must stop the procedure rather than be replaced.

## 5. Reporting language

Use the following description:

> The MRes evaluation retained the 50 highest Tier 1 ranked D1 candidates as sequences progressing towards shortlisting for experimental validation in future work. Tier 2 compatibility and shuffled-control results were retained as coarse annotations but did not determine inclusion or order. No sequence was progressed to experimental validation within the thesis.

Do not describe the set as:

- experimentally selected, validated or ready for validation;
- predicted NDM-1 binders, inhibitors or functional aptamers;
- a target-specific computational shortlist supported by validated Tier 2 performance; or
- evidence that D1 learned target-specific or higher-order aptamer organisation.

The appropriate thesis claim is that AptaRank Tier 1 supplied a transparent, reproducible ordering of the generated D1 pool. The resulting 50 sequences are a reproducible future-work hand-off, not a biological success claim.

## 6. Historical records and reproducibility

The following remain unchanged:

- all Sections 6–10 raw uploads, exports, hashes, settings and closure records;
- the 30,000 uploaded, 29,583 scored and 417 technically excluded Section 10 accounting;
- the original gate-based Section 10 result of 137 jointly eligible and 100 retained for review;
- the Evaluation preset, seed 42, 99 shuffles, 200 sampled structures and NDM-1 target configuration;
- the NDM-1 cavity warning; and
- the conclusion that AptaRank outputs are computational prioritisation evidence rather than binding or experimental evidence.

The v3.10 output is stored as a separate result family under `results/aptarank/evaluation/future_shortlisting_sequences/`. It must cite the immutable Section 10 closure and input hashes so that the later reporting amendment cannot be mistaken for a rerun or alteration of the closed analysis.
