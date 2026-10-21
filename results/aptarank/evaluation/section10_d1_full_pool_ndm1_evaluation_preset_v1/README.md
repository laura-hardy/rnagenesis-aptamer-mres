# Section 10 full-pool D1 NDM-1 run

Status: `SECTION10_COMPUTATIONAL_VALIDATION_ANALYSIS_AND_SUPERVISOR_REVIEW_POOL_SCIENTIFICALLY_COMMITTED_AND_CLOSED`

The `raw/` directory contains unchanged artifacts downloaded from the single authorized Section 10 AptaRank run on 21 October 2026. The run used the independently reviewed 30,000-row D1 upload, frozen 113-row reference, NDM-1 target and Evaluation preset.

The raw files must not be edited. Full restricted-provenance validation, analysis and construction of the deterministic 100-candidate supervisor-review pool are complete. Sequence-free outputs are under `derived/analysis_v1/`. The ignored, owner-only sequence-bearing files are under `restricted/supervisor_review_v1/`. The later joint biologist-supervisor assessment may retain at most 50 candidates under plan v3.9.

The exact Tier 1/Tier 2 CSV is a scorer-exported artifact. It contains the first 1,000 candidates in Tier 1 rank order and reconciles exactly to ranks 1 through 1,000 in the full scored export. Its `control_percentile` values are raw AptaRank outputs and were not reconstructed locally.

The frozen gates yield 137 jointly eligible candidates. Tier 1 ordering retains 100 and caps out 37. The retained pool contains 33 `strong` and 67 `moderate` annotations; compatibility does not determine their order. Independent review found no material defect or blocker, and Laura explicitly committed and closed the computational result on 21 October 2026. The reviewed analysis files remain unchanged; the independent-review and closure records are stored separately under `review/` and `closure/`.

Manual supervisor review has not started. Under plan v3.9, that separate joint assessment may remove candidates and retain at most 50 for future experimental consideration, but it cannot add a candidate outside the closed computational pool.
