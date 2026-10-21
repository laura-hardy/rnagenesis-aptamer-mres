# AptaRank + RNAGenesis MRes Thesis Evaluation — Section 10 Post-Review Retention Amendment

## 1. Status and scope

| Item | Frozen decision |
|---|---|
| Status | Active prospective amendment for the final post-supervisor-review retention decision in Section 10. |
| Base plan | Version 3.8 remains unchanged and in force for the computational supervisor-review pool, SHA-256 `8cf982180663ad8591583bd5e37613be4ce8234cfc8a2b82822a36b756d661dc`. Version 3.9 adds the post-review decision stage described here. |
| Scope | This document keeps the v3.8 computational supervisor-review pool unchanged and adds an explicit joint manual assessment followed by a final cap of 50 candidates. Every v3.8 eligibility rule, ordering rule, 100-candidate computational-pool cap, input, target, run setting, validation requirement, denominator, limitation and reporting boundary remains in force. |
| Timing | Adopted after the Section 10 30,000-row D1 upload package passed local preflight and independent preparation review, but before the upload was run and before any Section 10 score, compatibility token, shuffle token, exclusion or candidate outcome was observed. |

The candidate upload, opaque identifiers, reference upload, target, AptaRank run configuration and deterministic computational-pool rule are unchanged. Re-preparing or reblinding the reviewed upload is neither required nor permitted solely because of this post-review retention amendment.

## 2. Frozen NDM-1 shortlisting rule

Apply the following rule only after the untouched Section 10 exports and exclusions have passed validation against the reviewed upload and restricted provenance:

1. The candidate must have a valid exported AptaRank score.
2. The candidate-specific shuffle token must be `pass`.
3. NDM-1 compatibility must be `strong` or `moderate`. These tokens are pooled as one favourable eligibility class; `strong` does not precede `moderate`.
4. Rank all eligible candidates by better Tier 1 rank.
5. Use ascending stable opaque candidate ID only to break an exact Tier 1 tie.
6. Retain at most 100 candidates in the deterministic computational pool for joint manual assessment with the biologist supervisor, as frozen in v3.8.
7. Never relax an eligibility gate, admit a `weak` or shuffle-`fail` candidate, replace a technical exclusion, or replenish the computational pool to reach 100.

If 100 or fewer candidates qualify, include all qualifying candidates in the supervisor-review pool. If more than 100 qualify, include the first 100 under the frozen Tier-1-primary ordering. A smaller computational pool, including an empty pool, is a valid outcome.

The original compatibility token must remain visible in the review table. Do not create a numerical Tier 1/Tier 2 composite score. The shuffle result remains a binary gate rather than a continuous ranking variable.

## 3. Joint manual assessment

The computational pool of at most 100 candidates is reviewed jointly with the biologist supervisor. This is a final manual assessment step, not a further AptaRank score or a claim of experimental validation.

For every reviewed candidate, preserve the opaque ID, source provenance, sequence, length, Tier 1 score and rank, shuffle token, compatibility token, technical warnings, and the final manual decision with supervisor, date and concise reason. Record candidates that are not advanced as well as those selected for experimental consideration.

After that joint assessment, retain at most 50 candidates for experimental consideration. Manual assessment may reduce the set below 50, including to zero, but must not introduce a candidate that failed the frozen computational gates or fell outside the deterministic supervisor-review pool. The final 50-candidate maximum is not a second automated ranking cutoff. Any laboratory-feasibility consideration must be stated explicitly and must not be retroactively described as part of AptaRank.

## 4. Unchanged production and scientific boundaries

The following remain unchanged from v3.8:

- the complete frozen 30,000-member D1 source pool and reviewed candidate upload;
- the frozen 113-row attempt-3 REF;
- NDM-1, PDB `5ZGX`, chain A, pocket/groove recognition, residues 120, 122, 124, 189, 208 and 250, and prepared-target identifier `0fde4d5e4370`;
- the Evaluation preset, seed 42, 99 candidate shuffles, 200 sampled structures, `corpus_weighted_mean`, and expected scoring signature `95a49467ef3c6186`;
- one manual production run, raw-artifact preservation, hashing, exclusion accounting and exact opaque-ID reconciliation;
- separate Tier 1 and Tier 2 reporting and the NDM-1 cavity-geometry warning;
- no replacement, replenishment, threshold relaxation or post-outcome alteration of the target or run settings.

AptaRank outputs are computational prioritisation evidence. They are not evidence of binding, affinity, specificity, inhibition, target recognition or experimental function. The Section 6 and Section 8 limitations, the provisional Section 9 target characterisation, and the NDM-1 cavity warning remain material to interpretation.

## 5. Reporting

Report the counts uploaded, scored, technically excluded, exported, otherwise missing, shuffle `pass`, `strong`, `moderate`, pooled favourable compatibility, jointly eligible, capped out of the at-most-100 computational pool, manually reviewed, finally retained after supervisor review, and not retained after supervisor review.

Describe the first table as a **supervisor-review pool of computationally prioritised D1 candidates** and the second decision record as the **post-review set retained for future experimental consideration**. Do not describe either as a validated binder set or as evidence that AptaRank predicts laboratory success.

The Section 10 reviewed production package was prepared under v3.8 before this amendment. Its candidate upload, AptaRank run sheet and embedded at-most-100 computational review-pool rule remain valid. Version 3.9 adds the joint manual assessment and the final post-review maximum of 50; it does not replace the deterministic v3.8 pool.
