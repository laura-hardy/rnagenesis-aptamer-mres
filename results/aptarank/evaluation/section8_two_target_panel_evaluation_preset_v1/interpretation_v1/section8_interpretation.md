# Section 8 illustrative Tier 2 EVAL: provisional scientific interpretation

Status: `PROVISIONAL_SECTION8_INTERPRETATION_AWAITING_INDEPENDENT_REVIEW_AND_EXPLICIT_RESULT_COMMITMENT`

## Scientific question

Section 8 asks whether the deployed AptaRank Tier 2 pathway gives directionally sensible, technically interpretable compatibility annotations for a deliberately small set of known cognate aptamer-target cases representing two binding modes. It is an illustrative stress test, not a validation study of binding or target discrimination.

The two cases must be interpreted separately because pocket and surface modes use different target geometries and target-specific shuffled-control distributions. No numerical cross-target comparison, mismatch test, concordance statistic, top-1 accuracy, confidence interval or cross-tier correlation is justified.

## GRK2/3UZS pocket-mode case

The single GRK2 cognate core was scored successfully with no technical exclusion. It received an aptamer-likeness score of 0.3415929203539823, failed its candidate-specific shuffled-control check and received a `weak` compatibility band.

For this case, the deployed workflow did not identify the known cognate core as having moderate or strong pocket compatibility. The UI attributed the weak annotation to a poor geometric match between an approximately 21 A predicted accessible loop and the selected 15.1 A cavity. This is a negative computational result for this configured case, not evidence that the experimentally studied aptamer does not bind GRK2. The calculation uses a sequence-predicted RNA fold and a computationally isolated protein chain retained in its bound-state conformation; it does not reproduce the crystallographic complex or conformational adaptation during binding.

## Hen egg-white lysozyme/4M4O surface-mode case

Both lysozyme cognate cores were scored successfully with no technical exclusion. The 59-nt core ranked first by aptamer-likeness at 0.672566371681416 but received `weak` compatibility and failed its shuffled-control check. The 45-nt core ranked second by aptamer-likeness at 0.5893805309734514, received `moderate` compatibility and also failed its shuffled-control check. Neither core received a `strong` band.

This is a mixed computational result: one known cognate core reached the moderate control-relative region, while the other remained weak. The higher Tier 1-ranked core had the weaker Tier 2 category, illustrating that aptamer-likeness and target compatibility are distinct outputs rather than a single quality axis. With only two cores from one cluster, this ordering difference cannot support a correlation or general claim about tier independence.

The configured surface patch was independently defined from crystallographic contacts, but the UI reported that those residues overlapped no fpocket cavity and used the highest-fpocket-score fallback. That warning is expected in surface mode, where the contact patch rather than a discrete cavity is the primary evidence, but the fallback must not be described as binding-site-selected. The isolated-chain, bound-state-conformation limitation also applies.

## Overall Section 8 conclusion

The result is weak to mixed rather than confirmatory. AptaRank did not consistently assign moderate or strong compatibility to these known cognate examples, and the candidate-specific shuffle check did not pass in either target run. Section 8 therefore provides no evidence that the deployed scores validate binding, affinity, specificity, inhibition, target recognition or experimental function. It also provides no target-discrimination evidence because no permissible cross-mode mismatches were scored.

The result nevertheless identifies reproducible computational behaviour and useful limitations. Tier 2 reports target-specific geometric compatibility separately from Tier 1 aptamer-likeness, preserves target-specific warnings, and can produce a different ordering from Tier 1. Its sensitivity to known cognate examples in this tiny panel is limited, so a favourable downstream band must be treated as a prioritisation signal only.

## Compatibility-bank and downstream-use decision

The deployed percentile bands are operationally interpretable for conservative within-target prioritisation under the frozen downstream workflow, subject to major validation limitations:

- the UI identifies the bank as 5,085 fixed dinucleotide-shuffled controls derived from the uploaded REF and scored against the same target geometry;
- REF is disjoint from EVAL under the frozen corpus split;
- higher percentiles are the favourable direction, with `moderate` at or above 0.75 and `strong` at or above 0.95;
- the UI states that the bands are relative to the target-specific control bank rather than to the candidates in the current batch, so the thresholds do not shift with batch composition;
- both rigorous Section 8 runs expose the same bank count, deployment and scoring signature;
- no bank identifier or content hash is exposed, and none is invented;
- no untouched artifact exposes a numeric Tier 2 score, so no raw score is reconstructed.

Accordingly, Sections 9 and 10 may retain the prespecified `strong` and `moderate` tokens for the single frozen NDM-1 configuration. They must be described as control-relative computational compatibility bands, not probabilities of binding or experimentally validated thresholds. Tier 1 and Tier 2 must remain separate; a favourable compatibility band cannot rescue a shuffle failure or weak Tier 1 evidence. No cross-target numerical comparison is permitted, and the review-pool criteria must not be relaxed if few or no D1 candidates qualify.

This downstream-use decision remains provisional pending independent review and explicit scientific result commitment.

## Thesis-ready concise statement

In two descriptive cognate cases, AptaRank Tier 2 produced weak GRK2 pocket compatibility and mixed lysozyme surface compatibility, with one moderate and one weak annotation; none was strong. All candidates failed their candidate-specific shuffled-control checks. The results show that Tier 2 can provide a target-specific annotation distinct from Tier 1, but do not demonstrate reliable recognition of known binders or target discrimination. The REF-derived compatibility bands are retained only as conservative within-target prioritisation categories for the frozen NDM-1 workflow, with binding and functional claims explicitly excluded.
