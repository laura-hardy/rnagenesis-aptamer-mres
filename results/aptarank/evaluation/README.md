# AptaRank evaluation results

This directory is the local root for outputs from the remaining MRes AptaRank evaluation.

Create a new versioned subdirectory for each approved run or analysis stage. Preserve raw uploads, UI downloads, logs and run artifacts unchanged. Write derived tables and reports separately and bind every artifact to its SHA-256, run settings, expected/exported/failed row accounting and rerun lineage.

Result families under evaluation plan v3.6 are:

- completed Section 6 REF-calibrated Tier 1 EVAL;
- Section 8 illustrative Tier 2 EVAL;
- one Section 9 target-enabled run of the frozen 200-per-condition B0/B1/B2/D1 sample, with Tier 1 and NDM-1 Tier 2 reported separately; and
- one Section 10 target-enabled run of the full 30,000-member D1 pool, followed by a filtered supervisor-review pool of at most 100 shuffle-pass candidates with strong or moderate target compatibility, ordered by compatibility band and Tier 1 rank, and a final decision record.

Do not use this directory to reopen or extend M10. AptaRank scores are computational prioritisation evidence, not binding, affinity, specificity, inhibition or experimental validation.

## Recorded interface-marker decision

Decision recorded 20 October 2026: the deployed AptaRank interface has an existing, known bug that can mark result artifacts `publication_eligible: false` and describe them as development runs because its internal reference-library provenance record is absent. This marker does not interact with execution of the frozen two-tier ranking framework. It is therefore disregarded for the remaining thesis evaluation and does not require diagnosis, remediation or rerunning by itself.

This decision applies only to that interface marker and its accompanying development-run warning. It does not waive validation of the actual reference and candidate hashes, software and scoring identities, frozen settings, raw exports, exclusions, missing rows, or rerun lineage. Do not repeat the marker as a limitation in individual run records or thesis results.
