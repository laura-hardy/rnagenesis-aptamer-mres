# AptaRank evaluation: final thesis entry point

The final public thesis selection is the [filtered 50-candidate set](thesis_filtered_shortlist/README.md),
matching §4.6 and Table A.13. The repository owner confirmed this choice when
preparing the thesis companion. It supersedes the Tier-1-only v3.10 hand-off for
final-selection purposes. The historical plan and result artifacts remain
unchanged; no scores were recomputed. See the [thesis guide](../../../docs/THESIS_GUIDE.md).

The remainder of this index records the earlier v3.10 hand-off context. Its use
of “final” refers to that historical disposition.

---

# Historical evaluation and v3.10 hand-off

This directory is the local root for outputs from the remaining MRes AptaRank evaluation.

Create a new versioned subdirectory for each approved run or analysis stage. Preserve raw uploads, UI downloads, logs and run artifacts unchanged. Write derived tables and reports separately and bind every artifact to its SHA-256, run settings, expected/exported/failed row accounting and rerun lineage.

Result families under the completed evaluation and final-disposition plan v3.10 are:

- the preserved historical Standard-preset Section 6 REF-calibrated Tier 1 EVAL and its separate, same-input Evaluation-preset successor, now independently reviewed, explicitly committed and closed as the final Section 6 thesis result;
- Section 8 illustrative Tier 2 EVAL, now technically validated, independently reviewed, explicitly committed and closed as a weak-to-mixed descriptive result;
- one Section 9 target-enabled run of the frozen 200-per-condition B0/B1/B2/D1 sample, with Tier 1 and NDM-1 Tier 2 reported separately; and
- one Section 10 target-enabled run of the full 30,000-member D1 pool, which historically produced a filtered 100-candidate review pool under v3.8/v3.9; and
- a separate v3.10 future-work hand-off containing Tier 1 ranks 1–50, with shuffle and Tier 2 retained as coarse annotations rather than gates.

Version 3.8 is a transparent prospective computational-prioritisation amendment made after the closed Section 8 evaluation and validated provisional Section 9 evidence, but before any Section 10 preparation or result. Version 3.9 retained that computational rule and added the pending post-supervisor maximum of 50. Version 3.10 is a later, explicitly outcome-aware final-disposition amendment made after Section 10 and supervisor consultation. It leaves the closed evaluation unchanged, advances no sequence to experimental validation, and retains Tier 1 ranks 1–50 as candidates progressing towards future shortlisting. Version 3.7 remains unchanged at SHA-256 `24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9`. The v3.8 SHA-256 is `8cf982180663ad8591583bd5e37613be4ce8234cfc8a2b82822a36b756d661dc`; v3.9 is `88be515dcb04dd3db9f4ec7392b70ce90de085a601d15ac00facc43f509ad274`; v3.10 is `08b019ce00ea87485dee1c1d436eca3d1b9780d3506ad8c88716cf089f53c020`.

The Section 10 result family is at `section10_d1_full_pool_ndm1_evaluation_preset_v1/`. Full restricted-provenance validation passes for 30,000 uploaded = 29,583 scored + 417 excluded, with no missing or replenished rows. The exact Tier 1/Tier 2 export covers ranks 1 through 1,000. The historical shuffle and pooled favourable-compatibility gates yielded 137 eligible candidates; Tier 1 ordering retained 100 for review and capped out 37. That computational result remains closed and unchanged.

The final sequence-bearing hand-off is at `future_shortlisting_sequences/`. It contains the 50 highest Tier 1 ranked D1 candidates with sequences, identifiers, exact AptaRank outputs and D1 provenance. Shuffle and Tier 2 are annotations only. No candidate is progressed to experimental validation within the thesis.

Later-discovered untouched exact Tier 2 exports are archived and analysed for the two closed Section 8 target cases and the 800-row Section 9 run. The versioned Section 8 supplemental addendum preserves its historical closure and has been independently reviewed, explicitly approved and closed. Section 9 exact-score analysis v2 supersedes analysis v1 and has been independently reviewed, explicitly committed and closed. The quantitative values sharpen but do not materially reverse the earlier interpretations.

Do not use this directory to reopen or extend M10. AptaRank scores are computational prioritisation evidence, not binding, affinity, specificity, inhibition or experimental validation.

All thesis production runs in Sections 6, 8, 9 and 10 use the deployed named **Evaluation** preset. Before starting, verify that the UI displays seed 42, 99 candidate shuffles and 200 sampled structures. Stop if the named preset differs; do not manually approximate it. Preserve Standard-run evidence unchanged and do not pool it with corrected runs.

## Recorded interface-marker decision

Decision recorded 20 October 2026: the deployed AptaRank interface has an existing, known bug that can mark result artifacts `publication_eligible: false` and describe them as development runs because its internal reference-library provenance record is absent. This marker does not interact with execution of the frozen two-tier ranking framework. It is therefore disregarded for the remaining thesis evaluation and does not require diagnosis, remediation or rerunning by itself.

This decision applies only to that interface marker and its accompanying development-run warning. It does not waive validation of the actual reference and candidate hashes, software and scoring identities, frozen settings, raw exports, exclusions, missing rows, or rerun lineage. Do not repeat the marker as a limitation in individual run records or thesis results.
