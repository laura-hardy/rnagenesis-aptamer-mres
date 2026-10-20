# Section 6 Tier 1 EVAL v1 run archive

## Status

This directory preserves the completed Section 6 Tier 1 EVAL run. The three files under `raw/` are unchanged browser exports. Frozen validation and analysis passed, independent review found no material defect, and the user explicitly approved scientific result commitment and closure on 20 October 2026.

The project-level evaluation README records the decision about the known AptaRank interface marker. That marker does not affect this run's status or require a rerun.

## Run accounting

- UI analysis name: `section6_eval_tier1_v1`
- Run/export identifier: `run_20261020T063814Z_5554f68f`
- UI timestamp: 20 October 2026, 17:29 AEDT
- Reported ranking runtime: 6 seconds
- Uploaded candidates: 308 before rejection
- Scored/exported candidates: 306
- Excluded candidates: 2
- Exclusion reason: both sequences were length 121, above the deployed maximum of 100
- Target: none
- Binding mode: none
- Shuffled controls: 20
- Seed: 42
- Candidate-upload SHA-256 prefix shown by AptaRank: `5554f68fd94d1754...`
- Reference upload: `m9c_reference_upload_attempt3.csv`
- Reference-upload SHA-256 prefix shown by AptaRank: `5f5c90572263818b...`
- Reference accounting: 113 accepted, 0 dropped
- Composite method: `corpus_weighted_mean`
- Scoring signature: `6dec9dc463a8fde1`
- AptaRank: 0.1.0, schema 1.0.0, Git `49a85609e352`
- ViennaRNA: 2.7.2
- forgi: 2.2.3
- fpocket: 4.0
- ushuffle: unknown

The 306-row shortlist has unique opaque candidate IDs, complete ranks 1 through 306, and finite aptamer-likeness values in the closed interval [0, 1]. The two excluded IDs are distinct from the shortlist; together the files account for all 308 uploaded candidates.

## Raw artifact inventory

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `raw/run_20261020T063814Z_5554f68f_shortlist.csv` | 42,480 | `3fddbf7b13746c08595e2f3cf68be70dc8c1a76a9b7dc05045af131462a7b015` |
| `raw/aptarank_tier1_eval_v1.pdf` | 487,234 | `6bca5c8c317112902a8f1637bcd8647e37ede46aed8edd3d3ac0b420f97ced9a` |
| `raw/excluded_sequences.csv` | 289 | `91ff501e648389b2c8234c0bd2460ea8a8c2d63ccf56a37c8079abc2b82d3d3e` |

Any subsequent validation or analysis output belongs under a separate `derived/` directory and must not overwrite these files.

## Closed analysis

Production validation and prespecified aggregate analysis passed on 20 October 2026. Outputs are under `derived/analysis_v1/`. The reviewed files remain unchanged. The separate closure record is under `closure/`.

- Input candidates: 308
- Evaluable scores: 306, comprising 153 EVAL cores and 153 paired controls
- Technical exclusions: 2, removing one whole matched pair without replacement
- Complete pairs: 153
- Clusters represented among complete pairs: 79 of 79
- Bootstrap: 10,000 replicates for every target, with zero undefined or imputed replicates
- Median paired score difference, EVAL minus control: 0.108; cluster-bootstrap 95% CI 0.064 to 0.164
- Descriptive AUROC against the paired uniform null: 0.638; cluster-bootstrap 95% CI 0.555 to 0.717
- Shuffle pass: 9/153 EVAL cores and 7/153 controls; paired difference 1.3 percentage points, 95% CI -4.1 to 6.6
- Production five-component table: unavailable because no verified component-level export was provided; no component was recomputed

Derived artifact hashes:

| Artifact | SHA-256 |
|---|---|
| `derived/analysis_v1/analysis_summary.json` | `b3dec6026badbdfb38cce10cd5d7ad04838d6a0f20069a1b7dab0878b6bf8422` |
| `derived/analysis_v1/analysis_manifest.json` | `1908f34a9dfa2987920bd9c077810783875b915db8c5cce677764a7c9e078161` |
| `derived/analysis_v1/section6_tier1_results.md` | `b96c5b323f6ad0a8a31ff8d5feefe3720e55217237966ba77aa608272c7a84fc` |

The production adapter is `scripts/modelling/aptarank_section6_production_analysis.py`, SHA-256 `db0127ec0c245e187a482dc2c00330dccc1b0d9e8e28f8bfdca1d87f80317286`. It does not modify the frozen method modules, expose candidate-level memberships, copy the private key, or recompute AptaRank scores.

Section 6 is scientifically committed and closed. This does not mean that the work has been Git-committed or pushed.
