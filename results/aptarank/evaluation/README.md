# AptaRank evaluation results

This directory is the local root for outputs from the remaining MRes AptaRank evaluation.

Create a new versioned subdirectory for each approved run or analysis stage. Preserve raw uploads, UI downloads, logs and run artifacts unchanged. Write derived tables and reports separately and bind every artifact to its SHA-256, run settings, expected/exported/failed row accounting and rerun lineage.

Result families under active remaining-evaluation plan v3.9 are:

- the preserved historical Standard-preset Section 6 REF-calibrated Tier 1 EVAL and its separate, same-input Evaluation-preset successor, now independently reviewed, explicitly committed and closed as the final Section 6 thesis result;
- Section 8 illustrative Tier 2 EVAL, now technically validated, independently reviewed, explicitly committed and closed as a weak-to-mixed descriptive result;
- one Section 9 target-enabled run of the frozen 200-per-condition B0/B1/B2/D1 sample, with Tier 1 and NDM-1 Tier 2 reported separately; and
- one Section 10 target-enabled run of the full 30,000-member D1 pool, followed by a filtered computational supervisor-review pool of at most 100 shuffle-pass candidates with strong or moderate target compatibility pooled as one favourable eligibility class and ordered primarily by Tier 1 rank; joint assessment with the biologist supervisor then retains at most 50 candidates in the final decision record.

Version 3.8 is a transparent prospective computational-prioritisation amendment made after the closed Section 8 evaluation and validated provisional Section 9 evidence, but before any Section 10 preparation or result. Version 3.9 retains that computational rule and adds the post-supervisor maximum of 50; it was frozen after preparation review but before the Section 10 run. Version 3.7 remains unchanged at SHA-256 `24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9`. The v3.8 SHA-256 is `8cf982180663ad8591583bd5e37613be4ce8234cfc8a2b82822a36b756d661dc`; v3.9 is `88be515dcb04dd3db9f4ec7392b70ce90de085a601d15ac00facc43f509ad274`.

The Section 10 result family is at `section10_d1_full_pool_ndm1_evaluation_preset_v1/`. Full restricted-provenance validation passes for 30,000 uploaded = 29,583 scored + 417 excluded, with no missing or replenished rows. The exact Tier 1/Tier 2 export covers ranks 1 through 1,000. The frozen shuffle and pooled favourable-compatibility gates yield 137 eligible candidates; Tier 1 ordering retains 100 for supervisor review and caps out 37. The sequence-bearing review files remain local under an ignored `restricted/` directory. The computational result and deterministic pool have passed independent review and are explicitly committed and closed. Joint biologist-supervisor assessment remains pending and may retain at most 50 candidates.

Later-discovered untouched exact Tier 2 exports are archived and analysed for the two closed Section 8 target cases and the 800-row Section 9 run. The versioned Section 8 supplemental addendum preserves its historical closure and has been independently reviewed, explicitly approved and closed. Section 9 exact-score analysis v2 supersedes analysis v1 and has been independently reviewed, explicitly committed and closed. The quantitative values sharpen but do not materially reverse the earlier interpretations.

Do not use this directory to reopen or extend M10. AptaRank scores are computational prioritisation evidence, not binding, affinity, specificity, inhibition or experimental validation.

All thesis production runs in Sections 6, 8, 9 and 10 use the deployed named **Evaluation** preset. Before starting, verify that the UI displays seed 42, 99 candidate shuffles and 200 sampled structures. Stop if the named preset differs; do not manually approximate it. Preserve Standard-run evidence unchanged and do not pool it with corrected runs.

## Recorded interface-marker decision

Decision recorded 20 October 2026: the deployed AptaRank interface has an existing, known bug that can mark result artifacts `publication_eligible: false` and describe them as development runs because its internal reference-library provenance record is absent. This marker does not interact with execution of the frozen two-tier ranking framework. It is therefore disregarded for the remaining thesis evaluation and does not require diagnosis, remediation or rerunning by itself.

This decision applies only to that interface marker and its accompanying development-run warning. It does not waive validation of the actual reference and candidate hashes, software and scoring identities, frozen settings, raw exports, exclusions, missing rows, or rerun lineage. Do not repeat the marker as a limitation in individual run records or thesis results.
