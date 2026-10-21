# AptaRank + RNAGenesis MRes Thesis Evaluation — Section 10 Prioritisation Amendment

| Plan detail | Value |
|---|---|
| Project | Towards prediction-guided generative design of RNA aptamers against carbapenemase targets |
| Document version | 3.8 |
| Revision date | 21 October 2026 |
| Status | Active prospective amendment for Section 10 prioritisation. Version 3.7 remains an unchanged historical record, SHA-256 `24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9`. Except for the Section 10 review-pool ordering replaced below, every v3.7 input, run setting, validation rule, denominator, scientific boundary and reporting requirement remains in force. |
| Timing | Adopted after the closed Section 8 Tier 2 evaluation and the validated provisional Section 9 NDM-1 result were observed, but before preparation, execution or observation of the full-pool D1 Section 10 run. |

## 1. Reason for the amendment

Section 10 is a prospective candidate-prioritisation exercise for later laboratory review, not an additional test of AptaRank. The ordering should therefore emphasize the evidence that was better supported in this MRes evaluation while retaining conservative target-aware and shuffled-control gates.

The amendment is based on the following evidence available before the full-pool D1 run:

1. The rigorous Section 6 result showed moderate Tier 1 separation between EVAL cores and paired exact-length uniform RNA controls. The candidate-specific shuffled-control difference was weaker and uncertain, but the `pass` token remains a conservative mandatory gate.
2. The closed Section 8 target-aware evaluation provided insufficient evidence that Tier 2 reliably recognizes known cognate aptamers or that the `strong` and `moderate` bands should be ordered as distinct levels of biological promise. GRK2 was `weak`; the two lysozyme cores were `weak` and `moderate`; none was `strong`; and all three failed their candidate-specific shuffle checks.
3. The provisional Section 9 NDM-1 artifact warns: “This cavity is oddly shaped: its robust extent and equivalent-sphere diameter disagree by more than 2×. The geometric comparison assumes a roughly convex pocket.” This directly limits fine-grained interpretation of the target-geometry annotation.
4. The untouched Section 9 PDF reports a negligible-magnitude association between Tier 1 and the target-compatibility percentile (Spearman rho `-0.072`, p `0.0421`, n `800`). The numeric Tier 2 percentiles were not exported and are not reconstructed.

These observations do not establish that Tier 1 predicts laboratory success. They show only that Tier 1 has the stronger empirical discrimination signal within the completed computational evaluation, whereas the distinction between the two favourable Tier 2 bands is insufficiently validated. Accordingly, `strong` and `moderate` are pooled as one favourable-compatibility eligibility class. They are not declared biologically equivalent.

Because aggregate Section 9 outcomes had already been observed, this amendment is explicitly outcome-aware in timing and must not be described as prespecified from the beginning of the evaluation. It is frozen prospectively before any full-pool D1 score or candidate identity is observed. No Section 9 candidate, opaque ID or sequence enters the Section 10 supervisor-review pool.

## 2. Amended Section 10 review-pool rule

Run the complete frozen **30,000-member D1 unique-valid RNA pool** through AptaRank once using the unchanged v3.7 REF, NDM-1 target, Evaluation preset and settings. Preserve all uploads, downloads, exclusions and provenance exactly as required by v3.7. After validation, apply this frozen filter and ordering:

~~~text
eligibility 1     = valid scored D1 candidate
eligibility 2     = shuffle token is pass
eligibility 3     = NDM-1 compatibility token is strong or moderate,
                    pooled as one favourable-compatibility class
ordering 1        = better Tier 1 rank across the pooled favourable class
ordering 2        = ascending stable opaque candidate ID on an exact Tier 1 tie
maximum pool size = 100 candidates
technical rows    = excluded and recorded, never replaced
~~~

The shuffle result is a binary per-candidate gate, not a continuous pass rate used for ordering. Compatibility remains a mandatory coarse eligibility gate and remains visible in the supervisor table, but `strong` does not precede `moderate`. No numerical Tier 1/Tier 2 composite is formed.

Retain every eligible candidate when 100 or fewer qualify. If more than 100 qualify, retain the 100 best Tier 1 ranks across the pooled `strong`/`moderate` class, using ascending opaque ID only for an exact Tier 1 tie. If fewer than 50 qualify, retain and review all qualifying candidates, report the shortfall, and do not admit `weak` or shuffle-`fail` candidates. Do not replenish technical exclusions.

This ordering change can affect pool membership only if more than 100 candidates pass all three eligibility gates. It can affect presentation order when two or more eligible candidates have different compatibility bands. Record the original compatibility token for every retained candidate so the effect remains auditable.

## 3. Unchanged Section 10 decisions

The amendment changes only the ordering of already-eligible `strong` and `moderate` candidates. It does not change:

- the frozen 30,000-member D1 source pool or its SHA-256 `9b6cfb6c6e0d1cb1f7d7c3446843c193ac7934751c0394561655c132e7d5d612`;
- the one-run design, opaque-ID procedure, restricted provenance key or no-replenishment rule;
- the frozen 113-row attempt-3 REF upload;
- NDM-1, PDB `5ZGX`, chain A, pocket/groove recognition, residues 120, 122, 124, 189, 208 and 250, or prepared-target identifier `0fde4d5e4370`;
- the Evaluation preset, seed 42, 99 candidate shuffles, 200 sampled structures, `corpus_weighted_mean` or expected scoring signature `95a49467ef3c6186`;
- the requirement for a valid score, shuffle `pass`, and `strong` or `moderate` compatibility;
- the maximum review-pool size of 100 or the rule that fewer than 50 does not authorize relaxation;
- raw-artifact preservation, hashing, exclusion accounting, exact ID/sequence reconciliation, or supervisor/date/reason recording;
- the requirement to report Tier 1 and Tier 2 separately and preserve all target warnings;
- the prohibition on claims of binding, affinity, specificity, inhibition, target recognition or experimental validation.

## 4. Reporting language

Describe the retained candidates as **computationally prioritised D1 candidates for future experimental validation**. State that target compatibility was used as a coarse favourable-band eligibility screen, while Tier 1 rank supplied the primary ordering because the completed computational evaluation provided stronger evidence for Tier 1 discrimination than for a meaningful `strong`-over-`moderate` distinction.

Report counts at every gate: uploaded, scored, technically excluded, shuffle `pass`, `strong`, `moderate`, pooled favourable compatibility, jointly eligible, retained and capped out. Also report the retained pool's original `strong`/`moderate` composition even though band does not determine order.

## 5. Freeze and authorization boundary

This amendment authorizes documentation and preparation of the revised deterministic review-pool rule. It does not itself commit the provisional Section 9 scientific result, execute AptaRank, prepare or upload the Section 10 candidate file, select any candidate, or close the remaining evaluation. The full-pool D1 production package must pin this document and fail closed if an implementation still places `strong` before `moderate`.

No later result may change the gates, ordering, cap, target, preset or settings without another explicit, dated amendment made before applying the changed rule.
