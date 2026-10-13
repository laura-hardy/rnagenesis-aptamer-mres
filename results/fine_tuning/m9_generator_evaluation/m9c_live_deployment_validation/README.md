# M9C live deployment validation

This record is a development run only. `scientific_result` is false. Status is `M9C_LIVE_VALIDATION_RECORDED_REVIEW_PENDING`. M9C is not complete, and EVAL remains locked.

The run used only AptaRank's downloaded example candidates. Their scores, compatibility distribution, top candidate, correlation, and biological narrative are not scientific MRes results and are not copied here. EVAL and production candidates remained unopened. REF preparation and AptaRank were not rerun.

The summary is `m9c_live_deployment_validation_summary.json`. The manifest digest below was recomputed from the file bytes and is not embedded in the summary.

## Job

Job `job_20261013T032514_0a356a`. The authorized evidence directory is `/home/laura/rnagenesis-mres-runs/m9c_aptarank_development_validation_20261013/`. Those files stay outside Git.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `demo_candidates.csv` | 9876 | `6db3dae7b68afb4c171301a9a53b53e24df04940cdb82a375c6d23bbffba1b02` |
| `run_20261013T032639Z_6db3dae7_shortlist.csv` | 16881 | `e51141a97bc0df0150b7d2801031c7227681177e07358f69bb7b401f5d8f4b71` |
| `AptaRankrun_13oct218pm.pdf` | 780130 | `7d798dbb67c6c9e11862209b8215b1591f83da1a9fc3c147a596170ae5e175f5` |

The candidate input digest is the first digest. Accounting is 199 submitted, 199 returned, and 0 omitted.

## Reference upload

The attempt-3 upload SHA-256 is `5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6`. The UI accepted 113 reference aptamers and dropped 0.

`publication_eligible` was false because no AptaRank provenance sidecar accompanied the REF upload. Laura decided that this implementation flag does not block M9C, because REF provenance is independently frozen in the project. No sidecar was added.

## Deployment facts

The composite method is `corpus_weighted_mean`. The scoring signature is `6dec9dc463a8fde1`. That signature is not a control-bank hash.

AptaRank is 0.1.0, schema 1.0.0, git `49a85609e352`. ViennaRNA is 2.7.2, forgi is 2.2.3, and fpocket is 4.0. The ushuffle version is unknown.

The analysis preset is standard, with 20 shuffled controls and seed 42. The reported ranking runtime is 6 seconds. That figure is not total wall-clock runtime.

The target is 5ZGX chain A, pocket/groove recognition. The prepared-target identifier is `0fde4d5e4370`. Fifteen cavities were detected, and cavity 1 was selected. The characteristic width is 23.0 Å and the volume is 744 Å³. Electrostatics were skipped.

The compatibility control bank realized count is 5,085. The moderate threshold is at least 0.75 and the strong threshold is at least 0.95. The UI did not expose a control-bank hash or an explicit bank ID.

The chosen cavity is unusually shaped. Its robust extent and equivalent-sphere diameter differ by more than twofold, which limits interpretation of the convex-pocket geometric comparison.

## Export check

The candidate header is `id,sequence`. The shortlist header is `rank,candidate,aptamer-likeness,compatibility,shuffle,len,sequence`. Both files have 199 rows. Ranks are 1 through 199. Every example candidate appears once, and the ID-and-sequence join is exact. Lengths are 20–70 nt and match the length field. Aptamer-likeness values are finite and within [0, 1]. Rows follow descending likeness, then ascending candidate ID for an exact tie. Compatibility and shuffle values are within the supported public export tokens. No sequence, candidate ID, or individual score is stored in this directory.

## Boundary

The frozen pre-run v3 preparation contract, preparation module, tests, governing plan, and historical M9B artifacts are unchanged. Attempt 2 is unchanged. The attempt-3 preparation manifest is unchanged. This record does not complete M9 and does not unlock EVAL.
