# Section 9 generated-condition NDM-1 run

This directory preserves the single prespecified AptaRank Evaluation-preset run of the frozen 800-membership B0/B1/B2/D1 sample against the prepared NDM-1 target.

- `raw/` contains unchanged browser downloads. The supplied run scored all 800 uploaded candidates, so no exclusion register was returned or inferred.
- `records/raw_artifact_manifest.json` records the exact bytes and the run-level facts displayed by AptaRank.
- `records/pdf_visual_review.json` records a human visual review of all three PDF pages, including the target-geometry warning.
- `derived/analysis_v1/` contains sequence-free validation and provisional scientific analysis. It must not contain opaque candidate identifiers, RNA sequences or restricted provenance.
- `supplemental_exact_tier2_v1/raw/` contains the unchanged later-discovered exact Tier 1/Tier 2 scorer export.
- `derived/analysis_v2_exact_tier2/` revalidates analysis v1, joins the exact export by opaque candidate ID and adds quantitative target-control percentiles. It supersedes v1 and is the independently reviewed, explicitly committed Section 9 thesis result.
- `review_v2_exact_tier2/` and `closure/` record independent review and explicit scientific result commitment without altering the reviewed analysis.
