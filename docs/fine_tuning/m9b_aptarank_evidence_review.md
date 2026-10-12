# M9B-1 public AptaRank evidence review

| Item | Value |
|---|---|
| Status | `FROZEN_PUBLIC_EVIDENCE_SYNTHETIC_ONLY_DEPLOYMENT_UNVERIFIED` |
| Stage | M9B-1, synthetic-only |
| Contract | `config/modelling/aptarank_evidence_contract.json`, SHA-256 `0494ea740b1a2402032bfa695c23a422b142cda6a2bc043d1da87dbb9ddb092b` |
| Plan | `docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md`, version 3.3, SHA-256 `b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe` |
| Retrieval | 2026-10-12T07:24:37Z |
| Deployment | Unverified. The inspected public commit is not the live deployment. |

M9B-1 freezes a read-only review of the paper, the public implementation, and the supplied camera-ready interface files. It does not open TRAIN, VALIDATION, REF, or EVAL, and it does not construct a reference distribution or a Tier 2 control bank. The v3.3 plan was not edited. No detail below is a scientific result.

## Evidence inventory

Hashes were checked before the files were read.

| File | Bytes | SHA-256 | Role |
|---|---:|---|---|
| `aptarank_paper.pdf` | 1254624 | `aaf40af707acc236639dccb8ecbf1f3fb522143f0a447e71f490168896af433d` | Paper |
| `example_shortlist.csv` | 280 | `447ce90b4fdf8fab7bbd5a4fcda1824fc91d3b7b697c6cfc7fbe466e16400852` | Supplied CSV |
| `example_results_screenshot.png` | 492122 | `ffbc22abfd874af242623536ce516f35a8eda17bbc4b52048c39cae63e5c1e63` | Supplied screenshot |

The CSV and screenshot are interface evidence. They do not choose an MRes target, threshold, validation result, or outcome. The screenshot's target label is not adopted.

## Public repository

Repository: `https://github.com/alishahsvnd/AptaRank`.

| Commit | Available | Subject |
|---|---|---|
| `bd934ca54a6649eb8cf241f56a95d5903c873d91` | Inspected HEAD | Remove implementation spec details from README |
| `49a85609e3529adace60d3267ee88550159bba29` | Yes | update |

The previous independent review named `bd934ca` as the current public commit and reported that implementation code was unchanged from `49a8560`. This inspection confirms both points. The diff from `49a8560` to `bd934ca` deletes `IMPLEMENTATION_SPEC.md`, `Project Proposal.md`, and `REFINEMENTS_SPEC.md`, and edits `README.md`. No non-markdown path differs.

Public package version in source is `0.1.0`. That version is not a live-deployment identity. Deployment identity is M9C work.

The clone used for inspection was a temporary directory outside this repository.

## Evidence matrix

Levels are `paper`, `code`, `interface`, `inferred`, and `deployment`. A deployment mark means the live UI still has to confirm the point.

| Topic | Paper | Code | Interface | Inferred | Deployment |
|---|---|---|---|---|---|
| Candidate columns | CSV or text; sequence required | CSV `sequence`, optional `id`; also FASTA and lines | Not in the sample upload |  | Live upload UI |
| Sequence normalisation | T accepted; length 20–100; alphabet A/C/G/U | Strip whitespace, uppercase, T→U, then A/C/G/U and configured bounds | Sample sequences are uppercase A/C/G/U | In-range lengths 24 and 90 do not prove the bound | Live bounds if config differs. ARP-1's canonical uppercase rule is an MRes input policy, not this live check |
| Duplicates | Deduplicated | Collapse duplicate sequences; keep the first; skip blank CSV sequence cells; invalid non-empty rows are rejections | Unique ids and sequences in the sample |  | Live rejection accounting |
| Reference fields | Study-specific library with target provenance | Enforced required column is `sequence`; the other four are optional; dashboard wants at least one provenance column | Not in the sample | ARP-1 keeps five columns for provenance | Accepted and dropped REF counts |
| Shortlist columns | Ranked annotated list | `rank`, `candidate`, `aptamer-likeness`, `compatibility`, `shuffle`, `len`, `sequence` | Same header and order |  | Future download |
| Exported rank | Ranked list | Deterministic consecutive 1-based ordinal after descending Tier 1 score and ascending candidate ID | Larger aptamer-likeness first | Not the statistical minimum rank retained for the CDF | Live export |
| Opaque ids | Stable ids if absent | Supplied ids kept only when every accepted row has a nonempty unique id | `synthetic-long` and `synthetic-short` preserved | Consistent with the all-ids-present branch only | Live id policy |
| Tier 1 components | Five named features and directions | Same five, with the UI labels seen on the screenshot | Labels visible; numbers are not outcomes |  | Live component table |
| Empirical calibration | Mid-rank CDF; one-sided flip; two-sided peak at the median; one pooled distribution per criterion from the accepted uploaded reference | `F(x) = (#{r < x} + 0.5 #{r == x}) / m`; lower uses `1-F`; two-sided uses `1-2\|F-0.5\|`, already in `[0, 1]` for a valid CDF | Not in the CSV | No MRes short/long calibration is chosen or implemented | Live match to this inspected grain, plus accepted and dropped counts |
| Weights and composite | Equal weights 1; weighted mean | Same default; missing weight is an error; batch-rank aggregation remains a config alternative | CSV shows the composite only |  | Effective weights and method |
| Shuffle | Dinucleotide shuffles; four-term structural mean; `p=(1+c)/(M+1)`; pass at `p ≤ 0.05` | ushuffle `k=2`; same p-value; default alpha 0.05 | Em dash in the CSV, not pass/fail | Em dash matches a missing boolean, not a computed pass | Effective M and seed |
| Tier 2 direction | Percentile of geometric mismatch; lower mismatch agrees better | Higher control percentile is better agreement | Raw score absent from CSV and not readable as a number in the screenshot |  | Live raw-score export |
| Control bank | Equal dinucleotide shuffles from every unique reference sequence | `per_source = max(1, ceil(bank_size / n_sources))`; total is `per_source * n_sources`; id from corpus id plus signature | Not shown |  | Bank id, hash, and realized count |
| Bands | Weak below 75th; moderate 75th–95th; strong above 95th | `P ≥ 0.95` strong, else `P ≥ 0.75` moderate, else weak | Sample label `weak` |  | Equality at 0.95 |
| Target configuration | Optional PDB or UniProt, chain, mode, optional site; top 1000 annotated | Pocket and surface implemented; groove refused; annotation cap default 1000; Tier 2 does not reorder | Screenshot shows a target panel |  | MRes target entry |
| CSV omissions | UI shows breakdown, shuffle status, and target panel | Those fields are outside `ranked_table` | Confirmed absent; UI shows three-decimal likeness `0.680` against CSV `0.679646017699115` | UI metric format, not a second score | Future export |
| Manual provenance | Run rigour and dashboard provenance | Provenance panel shows counts, composite method, scoring signature, tool versions, and git commit | Settings are not in the CSV |  | The M9C capture itself |

ARP-1's target-free profile still accepts only compatibility `not evaluated` and shuffle `pass` or `fail`. The sample's `weak` and U+2014 em dash are a different, target-present export. They are not added to that profile.

## Conditional algorithms

These are public definitions. No production value is instantiated. Accepted REF count, dropped REF count, bank id, bank hash, and realized bank count stay null.

- Sequence normalisation: strip whitespace, uppercase, rewrite T as U.
- Opaque ids: keep supplied ids only when all accepted ids are nonempty and unique; otherwise generate `c`-prefixed ids.
- Empirical CDF: `(#{r < x} + 0.5 #{r == x}) / m`.
- Lower-favoured score: `1 - F` for normalised MFE, ensemble defect, and mean positional entropy.
- Two-sided score: `1 - 2|F - 0.5|` for stem fraction and GC fraction. A valid empirical CDF already places that value in `[0, 1]`. The public clip is defensive and does not change the result.
- Default composite: weighted mean with each default weight 1. The denominator is the sum of positive weights.
- Shuffle: `p = (1 + #{control ≥ real}) / (M + 1)`, pass when `p ≤ alpha`. Public default alpha is 0.05. Structural terms exclude GC fraction and length.
- Bank allocation: equal count per unique source sequence, using the ceiling formula above. Public config default bank size is 5000. That default is not a realized count.
- Tier 2 percentile: `(#{Δ_control > Δ} + 0.5 #{Δ_control = Δ}) / B`, higher meaning better agreement.
- Bands: code uses `≥ 0.95` and `≥ 0.75`. The paper's strict greater-than at the 95th is not reconciled.

Source anchors include `src/aptarank/ingest.py` (`normalise_sequence`, `ingest`), `src/aptarank/tier1/scoring.py` (`empirical_cdf`, `two_sided_score`, `weighted_mean`), `src/aptarank/tier1/shuffles.py` (`evaluate`), `src/aptarank/tier1/corpus.py` (`REQUIRED_COLUMNS`, `load_corpus_table`), `src/aptarank/tier2/calibration.py` (`assign_band`, `build_or_load`, `percentile`), `src/aptarank/tier1/service.py` (rank sort; fast mode zeros ensemble samples), `dashboard/views.py` (`ranked_table`), and `dashboard/jobs.py` (`preset_settings`).

## Deliberate MRes input and provenance policies

These are not unresolved scientific or deployment conflicts. The public AptaRank behavior stays recorded as inspected. Neither policy claims live-deployment verification.

1. All prepared MRes uploads must already contain canonical uppercase A, C, G, and U. ARP-1 rejects lowercase and T. Silent normalization is not relied upon. The public normaliser still strips whitespace, uppercases, and rewrites T as U. The policy is compatible with that inspected loader.
2. ARP-1 retains the five reference columns `id`, `sequence`, `target_name`, `target_pdb_id`, and `source_reference` for provenance and auditability. The public loader technically requires only `sequence`. The policy is compatible with that inspected loader.

## Non-material implementation detail

The empirical CDF returns values in `[0, 1]`, so `1 - 2 * abs(F - 0.5)` is already in `[0, 1]`. The public implementation's clip is defensive and does not change the result for a valid empirical CDF. `two_sided_clip` is not an unresolved conflict and does not require M9C resolution.

## Calibration grain and exported rank

The inspected public implementation constructs one pooled empirical REF distribution per criterion from the REF sequences it accepts. The MRes project does not choose or implement a competing short/long calibration. Local recomputation of AptaRank calibration remains disabled. Whether the live deployment matches that inspected implementation remains for M9C.

The exported rank is the deterministic consecutive 1-based ordinal position after sorting by descending Tier 1 score and ascending candidate ID for ties. That ordinal is not the statistical minimum rank retained for the empirical CDF.

## Conflicts left unresolved

1. Paper prose puts a strong band strictly above the 95th percentile. Public code uses `P ≥ 0.95`.
2. The paper says a quick run samples 30 structures. In this commit, fast mode forces candidate ensemble samples to 0, while the preset still writes 30 into config and the Tier 2 bank builder reads that config value.

The v3.3 plan already treats unverified scorer details as limitations and already assigns bank identity and REF counts to M9C. The remaining conflicts do not require a plan edit.

## Specification corrections

ARP-1 wording records canonical uppercase A/C/G/U, and rejection of silent normalisation, as a deliberate stricter MRes input policy. It also records the five reference columns as a deliberate provenance policy. Supplied-id preservation stays conditional in the public parser. Duplicate-sequence collapse stays a public behavior. ARP-1 still rejects duplicate ids, and ARP-2B still rejects a repeated canonical sequence in the candidate upload. The ARP-1 validator was not loosened. Target-free tokens, preset, raw Tier 2 equation, and control-bank identity stay unresolved.

U1 records the inspected pooled calibration. It does not leave a project short/long grain choice open. U2–U21 keep status `unresolved` and a null value: the public implementation definition is established where recorded, live deployment application remains unverified, and local scorer reimplementation remains disabled. Those notes do not relabel the recorded public algorithms as scientifically unknown. Local recomputation stays off. `deployment_verified` stays false. `provisional_camera_ready_formula_adopted` stays false.

## Still for M9C

- Live deployment version, schema version, code revision, and dependency versions.
- Effective preset and runtime, including shuffle count and ensemble-sample count.
- The quick-preset discrepancy between the paper's 30 sampled structures and this commit's fast-mode count of 0.
- Accepted and dropped REF counts. Descriptive REF summaries remain descriptive.
- Bank id, hash, and realized count from the deployed REF upload.
- Whether the live shortlist matches this public table, including raw-score absence and the em dash.
- Which side of the strong-band equality the deployment uses.
- Whether the live deployment applies the inspected pooled calibration. No separate short/long grain choice is open.
- ViennaRNA and forgi versions on that deployment. The paper's 2.7.2 and 2.2.3 citations belong to the paper's runs.

The canonical-uppercase policy, the five-column provenance policy, and the defensive two-sided clip are not M9C resolution items. No REF distribution, control bank, or production count is instantiated here.

## Prohibited in M9B

Opening TRAIN, VALIDATION, REF, EVAL, a production sequence ledger, a model, or a checkpoint; uploading or scoring production candidates; instantiating REF distributions or the Tier 2 bank; claiming those production identities; and running overlap, leakage, or nearest-TRAIN analysis. Paper evaluation numbers and the sample target are excluded from the MRes protocol.
