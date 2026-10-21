# AptaRank + RNAGenesis MRes Thesis Evaluation — Supervisor-Agreed Scope

| Plan detail | Value |
|---|---|
| Project | Towards prediction-guided generative design of RNA aptamers against carbapenemase targets |
| Document version | 3.7 |
| Revision date | 20 October 2026 |
| Status | Active corrective successor from 20 October 2026. Version 3.6 remains an unchanged historical record, SHA-256 `77fcefc24787faa464c3206a1571127e6042cb9db3089a745a2a5d681bf10120`. Version 3.5 remains the governing plan for the completed first Section 6 run, SHA-256 `ebb0e66dd35c7ed20abecacf710ea7a90dd0e2737ba1973af66e8f0753e22c9d`, but that Standard-preset result is superseded for final thesis reporting. Version 3.4 remains the governing plan under which M10 ran, SHA-256 `1f3a73bc294a75c527e11f074c6d3265786c8e7e70d41eacf3ea83d3cf512941`. M9A–M9C and M10 Section 5 remain complete. Section 6 is reopened for a same-input Evaluation-preset rerun before Sections 8–10. |
| Evaluation budget | Approximately five working days once prerequisites are ready; protect subsequent thesis writing |
| Execution model | Completed M10 was server-CPU execution of the frozen Section 5 generator analysis. Laura runs AptaRank manually through its UI under the approval already granted for the prespecified production runs. Version-controlled code prepares uploads and processes downloaded results. |

This plan has five required results: (1) held-out EVAL of all four generation conditions, (2) REF-calibrated AptaRank Tier 1 EVAL under the rigorous Evaluation preset, (3) a one- or two-target illustrative Tier 2 EVAL under that preset, (4) one target-enabled Evaluation-preset AptaRank run on frozen 200-member samples from B0, B1, B2 and D1 with Tier 1 and NDM-1 Tier 2 outputs reported separately, and (5) one Evaluation-preset target-enabled run of the full 30,000-member D1 pool followed by a prespecified filtered supervisor-review pool targeting 50–100 candidates. Section 14 contains deferred future work. A weak or null result fulfils an experiment when its inputs, score and analysis are valid; a technical failure is reported as incomplete, not recast as a null result.

### Rigorous production-preset correction

Every thesis AptaRank production run in Sections 6, 8, 9 and 10 uses the deployed UI's **Evaluation preset**, which is the paper's rigorous mode: **200 sampled structures and 99 candidate dinucleotide-preserving shuffles**, with seed 42. Select the named Evaluation preset and capture its displayed effective settings; do not manually assemble an approximation if the UI differs. `Standard` was the M9C development-validation configuration and the configuration of the first Section 6 run. It was carried forward too broadly and is not the final thesis production preset.

The correction is prospective for Sections 8–10 because no score from those sections has been observed. Section 6 is reopened because its first run used Standard. Reuse its exact 308-row candidate upload, 113-row REF upload, opaque identifiers, private key, paired controls, analysis estimands and exclusion policy. Change only the named preset and its effective sampling/shuffle settings. Preserve the first run and its independent review unchanged as historical evidence; do not pool the two runs or choose between them by outcome. The rigorous rerun becomes the Section 6 thesis result after validation, independent review and explicit result commitment.

The corrected S7D corpus contract and the implemented generator seed roles in the existing plan remain in force. This scope revision changes neither training nor the frozen corpus. It replaces earlier priority labels that made Tier 2, generated-sequence scoring, B0 or NDM-1 contingent.

## 1. Required questions and result boundaries

| Required analysis | Question and permitted interpretation |
|---|---|
| Four-condition generator EVAL | How do B0, B1, B2 and D1 generated distributions compare with untouched EVAL aptamer characteristics? B1 versus D1 is the primary causal comparison. B2 is the secondary data-scale comparator. B0 is the external baseline because of its different 37-nt output regime. |
| AptaRank Tier 1 EVAL | Does frozen REF-calibrated Tier 1 distinguish unique EVAL cores from paired exact-length uniform RNA, and how often does each group pass its own dinucleotide-preserving shuffle check? |
| Illustrative Tier 2 EVAL | For one or two independently configured EVAL targets, what does the frozen target-aware geometric score show? With two valid same-mode targets and eligible cognate relations, report cognate-versus-mismatch ordering. With only one valid target, show descriptive scores/annotations only; there is no cross-target ranking test. |
| Generated-sequence AptaRank | In one target-enabled run of the frozen 200-member sample from each condition, how do Tier 1 aptamer-likeness and NDM-1 Tier 2 outputs compare across B0, B1, B2 and D1? The two tiers remain separate. This is downstream computational prioritisation, not independent biological validation. |
| Full-pool D1 review | Which candidates from one target-enabled run of the complete frozen 30,000-member D1 pool pass the prespecified shuffle and target-compatibility filters and enter the capped supervisor-review pool, and which—if any—does the supervisor take forward? AptaRank does not establish binding or therapeutic activity. |

Use **similarity-aware, cluster-disjoint**, **known cognate target**, **prespecified mismatched target**, **target-aware geometric compatibility** and **computational prioritisation**. Do not claim a family-aware split, binding/affinity/selectivity prediction, experimental non-binders, carbapenemase-specific learning by unconditional D1, or a new Tier 1 + Tier 2 composite score. Canonical A/C/G/U cores do not model modified chemistry. Keep weak, mixed and null findings visible.

## 2. Data roles and firewall

~~~text
TRAIN      -> RNAGenesis fitting and frozen copying/novelty reference
VALIDATION -> generator/model development; separate quarantined camera-ready use
REF        -> M9C only: AptaRank's internal empirical calibration, never a performance test or generator decision set
EVAL       -> opened once at M10 for the Section 5 generator-level assessment; later AptaRank analysis uses that already-opened set and is not a second fresh opening
evaluation_references.csv
           -> separate published-reference/leakage resource; no candidate selection
              or extra thesis experiment in this plan
~~~

REF remains calibration-only data and stays closed through M9B. AptaRank performs its own empirical REF calibration internally from the uploaded corrected REF file. The project does not externally fit a distribution and feed it to the UI. Descriptive REF summaries, calculated only in M9C, are for thesis reporting and audit. They are not calibration of AptaRank. EVAL does not choose checkpoints, sampling, score equations/weights, target mode/site, control-bank rules, thresholds, metrics or shortlist sizes. M9C froze those rules before EVAL was opened. M9C has written the unlock record. The completed M10 Section 5 run opened EVAL once under explicit authorization. After that opening, EVAL metadata may instantiate the prespecified small Tier 2 panel; EVAL scores may not choose it. Camera-ready VALIDATION results cannot tune this thesis evaluation. Opening EVAL happened once, in authorized M10, for the Section 5 generator evaluation. Later AptaRank analysis uses that already-opened held-out set and is not a fresh EVAL opening.

The published NDM-1 reference panel remains a leakage/provenance resource. Its sequence-similarity comparison with generated candidates is deferred to Section 14 and is not part of the NDM-1 AptaRank shortlist.

## 3. Corrected frozen S7D execution contract

The corrected S7D corpus report (closure state **2026-09-25**) and curation plan **v1.6** govern these facts. The primary corpus is RNA/protein-target only, retaining E2-E4; E5, non-protein and ssDNA records remain excluded/parked under the curation plan.

- Final corpus: **1170 identities**, **1031 distinct** `sequence_core` **values**, **790 clusters**, **409 canonical targets**.
- Identity-grain evidence E2/E3/E4/E5: **800 / 247 / 123 / 0**.
- Maximum target share: **34/1170 = 0.0290598291**, for **HIV-1 Rev protein**.
- Top-level partition identities: **FT 858 / REF 131 / EVAL 181**. TRAIN and VALIDATION are the subordinate frozen FT split.

| Role       | Clusters | Identities | Unique cores | Targets | Corrected SHA-256                                                  | Permitted use                                                       |
| ---------- | -------- | ---------- | ------------ | ------- | ------------------------------------------------------------------ | ------------------------------------------------------------------- |
| TRAIN      | 569      | 726        | 669          | 320     | `84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0` | RNAGenesis fitting                                                  |
| VALIDATION | 63       | 132        | 95           | 100     | `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd` | training/model development; quarantined camera-ready exception only |
| REF        | 79       | 131        | 113          | 97      | `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23` | AptaRank calibration; never performance evaluation                  |
| EVAL       | 79       | 181        | 154          | 111     | `ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015` | final held-out assessment only                                      |

### 3.1 Frozen regimes and integrity

| Scope      | Short unique cores | Long unique cores | E2 identities | E3 identities | E4 identities |
| ---------- | ------------------ | ----------------- | ------------- | ------------- | ------------- |
| Corpus     | 595                | 436               | 800           | 247           | 123           |
| TRAIN      | 386                | 283               | 496           | 153           | 77            |
| VALIDATION | 55                 | 40                | 90            | 28            | 14            |
| REF        | 65                 | 48                | 88            | 30            | 13            |
| EVAL       | 89                 | 65                | 126           | 36            | 19            |

The short/long regime is the frozen S6 two-component GMM assignment/rule. Do not invent a nucleotide cutoff or refit it on evaluation data. Similarity clusters must not be described as complete biological families.

The corrected release records cluster crossings **0**, core crossings **0**, identity duplication **0**, exact evaluation-reference leakage **0**, >=90% evaluation-reference leakage **0**, excluded target aliases in primary **0**, non-protein in primary **0**, and E5 in primary **0**. TRAIN/VALIDATION `^[ACGU]+$` alphabet-gate failures are **0 / 0**. `corpus_final.txt` has **669 lines**, **669 unique lines**, **0 duplicates**, and contains only deduplicated frozen TRAIN cores in first-occurrence order. VALIDATION/REF/EVAL contamination of training text is **0 / 0 / 0**.

These are release-audit facts, not newly executed evaluation results. The broader `evaluation_references.csv` remains **35 rows** and separate from generic held-out EVAL. The published NDM-1 reference comparison is deferred to Section 14.

### 3.2 Corrected output hashes

| File                        | SHA-256                                                            |
| --------------------------- | ------------------------------------------------------------------ |
| `corpus_final.csv`          | `2797e6767f78029574df1b6cdf51bbe7952ea8affce83870441b3d3d93c98849` |
| `ft_train.csv`              | `84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0` |
| `ft_validation.csv`         | `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd` |
| `ref.csv`                   | `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23` |
| `eval.csv`                  | `ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015` |
| `ft_split_assignment.csv`   | `74b2f7db21184cd418580bc299a3cac6af61450848d9e7e45c963a0667f2a27a` |
| `corpus_final.txt`          | `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d` |
| `evaluation_references.csv` | `b6ba6b2cde4a18c04130ecdc457626c5e60b8b90d3ad5b9bae6cb1bfd1f77dad` |
| `corpus_manifest.json`      | `08da8d5e44413ea9ab57c128dbe4ef7986dab7a2bfa794cfef6fb4724577565f` |

These identify corrected source files, not derived uploads or calibration artefacts, which require their own hashes and parent-release lineage. The manifest's retained `build_date = 2026-09-22`, `governing_plan_version = 1.5` and pre-closure `repository_head_baseline` are build metadata, not the current closure date, plan version or closure commit.

### 3.3 Evidence ordering and scientific units

| Level | `binding_evidence_type` | Score |
| ----- | ----------------------- | ----- |
| E1    | `structural`            | 5     |
| E2    | `quantitative_affinity` | 4     |
| E3    | `qualitative_binding`   | 3     |
| E4    | `selection_enrichment`  | 2     |
| E5    | `database_annotation`   | 1     |

The frozen primary corpus retains E2-E4. The formal E2 > E3 > E4 order is provenance/eligibility information and must not become a new result-driven selection axis.

| Analysis               | Observation                                                         | Dependence preserved                                                                                                                                                                                |
| ---------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Final generator EVAL   | Frozen generated-pool distributions compared with the 154 unique EVAL cores, each weighted once | D1 seeds 43 and 44 and matched blocks A and B reported separately; observed ranges only; length strata. The 79 EVAL clusters are a design fact and a limitation. They do not weight M10 formulas, and M10 does not resample them. |
| Tier 1 EVAL            | One unique sequence core                                            | Frozen sequence cluster and its paired control                                                                                                                                                      |
| Illustrative Tier 2 EVAL | One unique core x canonical-target cognate relation                 | Sequence cluster, including multiple targets of one core                                                                                                                                            |
| Generated conditions   | Candidate within a frozen generation pool                           | D1 training-seed membership and actual matched B1/D1 generation-chunk provenance; candidates, length-specific seeds and batches are not training replicates                                         |

## 4. Prerequisites, seed contract and evaluation unlock

The five-day window is realistic only if corrected role files/hashes and the corpus leakage audit are final; M9A has frozen the generator outputs and their provenance; the verified M8 B1/D1 raw pools and allocation exist and B0/B2 provenance is available under the same later protocol; the generator evaluation code and metric specification work on synthetic fixtures; M9B has reviewed the AptaRank paper, public implementation, and implementation notes on documentation and synthetic fixtures; M9C has frozen the manual workflow after the REF-only preflight; and an NDM-1 structure/chain/mode/site can be specified with the supervisor from independent structural evidence. The M9B review of that preparation is complete. Prepare the illustrative Tier 2 target candidates and score-blind eligibility rule without using EVAL scores. Opening REF belonged to completed M9C, and the one opening of EVAL belonged to authorized M10 and is complete.

If any required pool, generator analysis or UI interface is absent, move the evaluation schedule. Do not reclassify one of the five agreed analyses as optional merely to keep a five-day label. If NDM-1 has no defensible configuration, document that technical limitation and confer with the supervisor; do not invent a favourable site or claim the shortlist was completed. The M9B AptaRank review is complete. The later AptaRank workflow remains required and is outside M10. Section 6 is reopened only for the same-input rigorous rerun described in Section 6.4. Laura has explicitly authorized this preset correction and the remaining prespecified manual runs, subject to their frozen-input and preflight gates; final result commitment still requires later explicit approval.

### 4.1 Frozen generation and uncertainty

Retain the implemented M4 design. D1 training seeds are independent model-training replicates when more than one exists. B1 Phase A seeds are paired protocol/length controls; B1 Phase B seed summaries are coupled to length and descriptive; B2 is a single-seed empirical null; B0 retains historical provenance. The limited B1/D1 comparison uses the implemented matched generation-chunk schedule where applicable. Generation chunks and candidate rows are not independent training replicates.

Two D1 training seeds were achieved. The one-seed M8 alternative is historical and is not the executed allocation. M10 reports seed 43, seed 44, matched block A, and matched block B separately, plus observed ranges only. It reports no generator confidence interval, bootstrap, hypothesis test, or EVAL-cluster resampling. The absent third seed remains a resource and time limitation. The verified M8 D1 pool is exactly 30,000 raw attempts, 15,000 from training seed 43 and 15,000 from training seed 44, not 30,000 per checkpoint. Those manifests confirm equal raw production weighting of the two fitted models. An equal mixture of the two seed-specific valid-output distributions may be shown as a labelled descriptive pool. It is not a confidence interval, and it does not replace the separate seed and block results. Raw accounting and global multiplicity remain the actual observed counts. M9A later recorded the parsed and valid counts cited in Section 15. Generated rows within one training seed are nested Monte Carlo samples, not additional model replicates. Keep B0 external rather than pooling its different length regime into the B1–D1 comparison.

### 4.2 M7 guardrails → immutable M8 → M9A → M9B → M9C → explicit M10

The generator sequence is M7 guardrails, then immutable M8 raw generation, then completed M9A, then preparatory M9B, then M9C, then an explicit M10 EVAL unlock. M7 guardrail samples are excluded from production pools. M6 remains the scope and runtime lock below; it does not place guardrail samples into those pools.

| Gate | Required record |
|---|---|
| M6 scope/runtime lock | Five agreed analyses; achieved seeds; four pool availability; generator metric specification; UI time/candidate limits; one/two illustrative target rule; NDM-1 target preparation and supervisor review route. Use an existing M6 record where valid; update the evaluation scope before EVAL access. |
| M9A generator freeze — complete | M9A exclusively owns parsing and validity accounting, within-condition duplicate accounting, cross-condition exact overlap, exact TRAIN leakage, nearest-TRAIN normalized edit distance, and the generator-output freeze with its provenance. It closed at commit `4a8246f0e4062ae13af161b98999f72382bd966c` under the immutable v3.2 plan. Section 15 cites the frozen aggregate conclusions. M9B does not recompute them and does not reopen sequence-bearing inputs. |
| M9B AptaRank full-thesis-evaluation preparation — synthetic-only | Preparatory only. M9B contains no overlap or leakage workflow. Permitted inputs are repository documentation, the reviewed AptaRank paper and public implementation, frozen non-sequence aggregate manifests and summaries, and synthetic fixtures. M9B may prepare and test AptaRank input and output schemas, candidate-ID and condition-membership conventions, deterministic sampling algorithms, blinding and private-key procedures, upload validators, downloaded-export validators, manual-run checklists and provenance records, and synthetic examples of the full thesis evaluation workflow. M9B must not open TRAIN, VALIDATION, REF, or EVAL; open production sequence ledgers; calculate overlap, leakage, or nearest-TRAIN distances; instantiate actual REF distributions; instantiate the actual Tier-2 shuffled-control bank; upload production candidates; execute an AptaRank scoring run; or produce biological evaluation results. Duplicate-ID or duplicate-sequence rejection in a future upload validator is input-integrity validation, not an overlap analysis and not an M9B overlap result. M9B does not unlock EVAL. |
| M9C controlled calibration and end-to-end preflight | M9C begins with separately authorized REF-only work, before EVAL is opened. Open only the authorized corrected REF. Record descriptive REF feature summaries for the thesis and audit. Verify AptaRank's accepted and dropped REF counts. Verify the identity and realized count of the shuffled-control bank that AptaRank constructs internally from the uploaded REF. Run the synthetic and manual UI preflight. Freeze the environment, dependencies, configuration, schemas, metrics, target rules, production sampling rules, runtime fallback, and failure handling. Then write the explicit EVAL-unlock record. AptaRank performs its own empirical REF calibration internally. Independent REF calculations stay descriptive. Do not claim a bank identifier or count before this deployed verification. |
| M10 one-time held-out generator evaluation | Section 5 only: the frozen four-condition B0/B1/B2/D1 generator-level EVAL, on server CPU, after explicit EVAL authorization. This was the one opening of EVAL. It completed successfully on 19 October 2026 and passed review. B1 versus D1 is primary. B2 is the secondary non-neural data-scale comparator. B0 is external and length-aware. Completion is the frozen Section 5 generator outputs, metric specification, design-aware interpretation, provenance, and reviewed derived results. M10 reports three separate headline closeness metrics and forms no aggregate generator-quality score. Diversity is exact-duplicate diversity only. Clustering, representation analysis, generator confidence intervals, bootstrap, hypothesis tests, and EVAL-cluster resampling are outside M10. |
| Later AptaRank thesis evaluation | Required work outside M10: rigorous REF-calibrated Tier 1 EVAL, illustrative Tier 2 EVAL, the combined generated-candidate Tier 1 and NDM-1 Tier 2 comparison, the full-pool D1 review, and the final decision record. M9B and M9C remain completed frozen groundwork. The first Standard Section 6 run is complete and scientifically committed as historical evidence; Section 6 is reopened for the same-input Evaluation-preset rerun. Manual production is authorized for that correction and the prespecified Sections 8–10 runs after their input and preflight gates. This workflow analyses the held-out set already opened at M10. It is not a fresh EVAL opening. |

The unlock record includes timestamps, operator/reviewer, corrected role hashes, the immutable M9A record, M9B preparation artefacts, the M9C REF and deployment record, AptaRank deployment, code/configuration versions, and this v3.3 plan. Independently verifiable bugs before the M9C unlock may be fixed for reasons unrelated to better paper/EVAL performance; repeat the affected preflight. After EVAL unlock, retain technical rerun lineage and report any scientific-method deviation transparently.

### 4.3 Verified M8 raw-source identities

A read-only audit has verified the completed M8 raw generation and assembly record. These identities are the B1 and D1 raw sources for later evaluation. They are not parsed sequences, valid-output counts, or an M9 scientific result. B0 and B2 source artifacts are outside this M8 verification.

| Item | Identity |
| --- | --- |
| B1 combined raw ledger | `/home/laura/rnagenesis-mres-runs/m8_b1_combined_1069b63_cpu_attempt1/m8_combined_raw_attempt_ledger.jsonl`; 30,000 records; 26,427,607 bytes; SHA-256 `37ba0e1b852a6b8492a816a4adc0c6bfee15a554ba28a8ba5dd91d9e32a255d9` |
| B1 assembly manifest | `m8_assembly_manifest.json`; 2,886 bytes; SHA-256 `f217e2e8ce922eef42b5f761159c7d96b7938585b4840922321454076d95d458` |
| D1 combined raw ledger | `/home/laura/rnagenesis-mres-runs/m8_d1_combined_1069b63_cpu_attempt1/m8_combined_raw_attempt_ledger.jsonl`; 30,000 records; 28,971,289 bytes; SHA-256 `cedcc36133f5dfb3678e1560c6d6bab703136fe89e512e939b9f93a9a6361de9` |
| D1 assembly manifest | `m8_assembly_manifest.json`; 2,939 bytes; SHA-256 `5ec79e1485b201d801ca819d9d60a2ee4383abd9cccfbbb011c6e11a9a59bbcb` |
| D1 selected set | SHA-256 `af0c0e555a8b878feadeb17fcbde18d8b780819a42d9e0cc547d2fc0c6895f8f`; final-selection manifest SHA-256 `49b218e3df74825e1931148e2f65b25aae057c822e2ab32d44c2960b1587c91c` |
| D1 seed 43 checkpoint | `D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-43__epoch-5__update-105__git-c150894b9982d7afebfb2b3390b0797a4da146b5`; epoch 5; update 105; weight SHA-256 `c0797888bde9033cc15b056c8c09e70b9f7fba0fb21b1f3840a4f1efb77031ab` |
| D1 seed 44 checkpoint | `D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-44__epoch-5__update-105__git-2cb1b6a26391ed36754ec21685a4501d659d50ef`; epoch 5; update 105; weight SHA-256 `d0fcb5174230b8bbbc6bfe59eabda9b37687c03800012bc1a6981cc215469ed5` |

Allocation. B1 and D1 each contain master indexes 0 through 29999 exactly once and 30,000 unique record ids. B1 block A is paired with D1 training seed 43 and generation seeds 800000–800162: 15,000 attempts and 830,348 nt. B1 block B is paired with D1 training seed 44 and generation seeds 900000–900163: 15,000 attempts and 830,404 nt. B1 records a null training seed. Generation seeds are not training seeds and are not record ids. The two fitted D1 models have equal raw production weight. The training seed is tied to the technical block, so the pooled D1 condition supports condition-level evaluation and does not support clean replicate-level causal inference.

Manifest status, 10 October 2026. Raw generation and CPU assembly are complete. Both assembly manifests record parsing, filtering, deduplication, metric computation, replacement, and replenishment as false, and `later_evaluation_required` as true. The checked-in M8 configuration is inactive. This M8 verification does not authorise EVAL. At that verification, production parsing had not yet been run. Section 15 records the later M9A parsing, overlap, and leakage closure. That later closure completed M9A only. M9B and M9C were completed after it. Both are complete. The generator-evaluation ViennaRNA pin is complete and is distinct from AptaRank's ViennaRNA 2.7.2.

## 5. Four-condition generator-level EVAL

This section is the whole of M10. After M9C and explicit M10 authorization, run this frozen generator evaluation on server CPU, on the B0/B1/B2/D1 pools against the 154 unique EVAL cores. B1 versus D1 remains the primary causal comparison. B2 is the secondary data-scale comparator. **B0 is required in this plan** as the external baseline, with its historical 37-nt output regime. Do not pool B0 into a matched-length B1/D1 causal estimate or imply that the historical B0 run supplies new independent training seeds. EVAL is held out from this project's development; the released B0 model's external training history may not guarantee independence from every EVAL publication, so cite the frozen M9A overlap and leakage record and any unresolved provenance. M10 cites those frozen outputs and does not reopen TRAIN.

Raw production artifacts are immutable. Do not filter, deduplicate, truncate, pad, top up, replace, or replenish them. Derived parsed and accounting tables are separate outputs, reproducibly linked to each source attempt. `record_id` is the canonical attempt identifier. Each derived row retains the source-artifact hash. Do not silently renumber attempts. A low valid or unique count stays visible.

The primary generator-analysis grain is all valid parsed attempts, including repetitions. Exact duplicates and their multiplicities are outcomes. A unique-only generator analysis is a labelled sensitivity with its own denominator; it does not replace the primary result. An expensive metric may use only a prespecified multiplicity-preserving attempt-level subsample, frozen before EVAL, and must report that sampled denominator. This grain is separate from the AptaRank application, which continues to draw valid unique candidates under Section 9.

Post-M8 parsing is condition-blind: the pipeline must not branch on condition in order to improve a condition's result. B0 may use a documented format adapter. After adaptation it enters the same biological validity parser as B1, B2, and D1. The adapter does not put B0 into the B1–D1 controlled comparison. Do not infer a biological requested length for B0 from nominal `max_seq_len` or from cleaned length when the source did not record one.

The generator analysis uses full-pool attempt accounting. The later AptaRank 200-per-condition sample is a separate derived input. Preserve condition/checkpoint, actual training seed, length-sampling seed, length-condition seed, generation chunk, cleaning/version and metric-specific denominators. Do not choose favourable seeds or generate replacement pools after seeing EVAL.

### 5.1 Frozen M10 scientific contract

M10 reports three separate headline closeness metrics: nearest-EVAL longer-length-normalized edit distance, nucleotide total variation to EVAL, and dinucleotide total variation to EVAL. M10 forms no aggregate generator-quality score. Diversity is exact-duplicate diversity only. Clustering and representation analysis are outside M10. M10 reports no generator confidence interval, bootstrap, hypothesis test, or EVAL-cluster resampling. Report D1 seeds 43 and 44 and matched blocks A and B separately, plus observed ranges only. The 154 unique EVAL cores are weighted once each. The 79 EVAL clusters are reported as a design fact and a limitation, and they do not weight formulas.

The thesis-facing parsed count is `successfully_parsed_outputs`: nonempty extracted sequences before A/C/G/U filtering. Legacy `parsed_outputs` remains only as an explicitly labelled internal/schema-valid-record audit field. It is not renamed, and it is not the thesis-facing parsed count.

M10 cites the frozen M9A TRAIN-overlap and nearest-TRAIN outputs and does not reopen TRAIN:

| Frozen M9A output | SHA-256 |
|---|---|
| `results/fine_tuning/m9_generator_evaluation/m9a_train_leakage/m9_exact_train_leakage_summary.json` | `f7d10f7f41777a091cc2b2bf3dfeec555d5e8d84b3b89850328be7cdcf15e0d3` |
| `results/fine_tuning/m9_generator_evaluation/m9a_train_leakage/m9_nearest_train_distance_summary.json` | `c68fa997207a657a7049e53dd074e8d593333f84152008d631cae0d6565c1d66` |
| `results/fine_tuning/m9_generator_evaluation/m9a_train_leakage/m9_train_leakage_manifest.json` | `e2b97da3b1f39859c1d4fc3a652dd4abb6e4da5836e2a5e9c067ce1b87491d88` |

Those files emit no sequence strings. Their recorded digests match the files cited here.

Fold each distinct valid generated sequence once. Generated condition, seed, and block quantiles use valid attempt rows with duplicate-attempt weighting. Fold each of the 154 unique EVAL cores once. Report MFE per nucleotide and paired fraction descriptively, including length strata and per-D1-seed results. M10 creates no structure-distance metric. The generator-evaluation fold is the existing `RNA.fold(sequence)` call, and the code sets no model detail. The frozen generator record is `viennarna_production_settings` in `config/modelling/generator_eval_metric_spec.json`, confirmed by `generator_viennarna_pin` in `results/fine_tuning/m9_generator_evaluation/m9c_closure/m9c_closure_manifest.json`. Both record ViennaRNA 2.7.0, build `py38pl5321hd78456e_0`. That version is distinct from AptaRank's ViennaRNA 2.7.2. The pin is complete.

| Result | Minimum output |
|---|---|
| Output accounting | Attempted counts, thesis-facing `successfully_parsed_outputs`, valid A/C/G/U, unique valid, duplicates/invalid, and metric-specific denominators for all four conditions. Legacy `parsed_outputs` is reported only as the labelled internal/schema-valid-record audit field. |
| TRAIN relationship | The frozen M9A exact TRAIN-overlap summary and nearest-TRAIN normalized edit distance cited above. M10 does not reopen TRAIN. |
| Sequence/structure distributions | Length, nucleotide/GC composition, and frozen mono-/dinucleotide summaries. Each distinct valid generated sequence is folded once. Condition, seed, and block quantiles use valid attempt rows with duplicate-attempt weighting. The 154 unique EVAL cores are folded once each. MFE per nucleotide and paired fraction include length strata and per-D1-seed results. No structure-distance metric is created. |
| Diversity | Exact-duplicate excess, multiplicity, and a sequence-free multiplicity histogram on valid attempts. Unique-only counts are a labelled sensitivity. Clustering and representation analysis are outside M10. |
| EVAL relationship | The three headline closeness metrics, reported separately, with their directions and longer-length or composition handling. The 154 unique EVAL cores are weighted once each. The 79 clusters are a design fact and a limitation and do not weight formulas. |
| Design-aware interpretation | D1 seed 43, D1 seed 44, matched block A, and matched block B, each reported separately, plus observed ranges only. B2's single-seed limitation stays visible. B0 stays on a separate length-aware panel. |

`config/modelling/generator_eval_metric_spec.json` is frozen and production-ready. The historical v3.4 pre-execution record was that M10 execution remained unauthorized and EVAL access remained unauthorized. The frozen specification carries one row per implemented metric: exact name, data/reference, denominator/filter, calculation, units/range, length/seed treatment, improvement direction or “not applicable”, role, and code/configuration revision. Validity, TRAIN novelty, and exact-duplicate multiplicity are outcomes or guardrails. They are not extra votes for closeness. The three closeness metrics declare the production reference role `authorized_eval_unique_cores`: the 154 frozen unique EVAL cores, each weighted once, available only after authorization and hash verification. Synthetic fixtures may exercise the formulas without changing that declaration. Clustering, representation analysis, and confidence intervals, bootstrap, hypothesis tests, and EVAL-cluster resampling are resolved as outside M10. TRAIN loading is resolved through the frozen M9A summaries. Structure execution and matched-block wiring are resolved as implemented and synthetically verified. At that historical pre-execution freeze they awaited authorization only. A candidate frozen specification must be frozen at the top level, on every metric row, and on the contract, with no blocking item left unresolved. The broad code inventory is captured. Metric-calculation revisions stay validated through the specification. Before EVAL access, the frozen S6 parameter-record SHA-256 is `8e2e20cfe1fa68ba53beec8df9aa9a64a9a2144dc9006fbbf5f8eb064f01df0f`. The frozen S7 configuration hashes are S7B `c62553344748fc8c322869d68a46f69e653dee5641bf5f208dcb776e597c9550`, S7C `e07f5af0de56beff4cefe75854493eaa3f696b9bc20c554ce2261033165f0873`, and S7D `abd3e1b29f422848aabd309ab0bb985731b9fb3941ddfbd2ec0f43d31a98b475`. Absent `bimodality.json` remains a provenance limitation, and the parameter-record hash is not an artefact hash. The ledger adapter, single-read EVAL adapter, matched schedule, structure wrapper and distinct-sequence cache, and production writer are implemented and synthetically verified. At the historical v3.4 pre-execution freeze they had not yet run biologically, and awaiting authorization was not then an active implementation blocker. That pre-EVAL metric-specification freeze did not itself authorize M10 and did not open EVAL. Section 5.2 records the later completed execution.

Use only this design-aware procedure. Stratify by length where needed. Do not turn generated rows, B1 length seeds, B2's single seed, or generation chunks into independent training replicates. The verified M8 raw counts are 30,000 B1 attempts and 30,000 D1 attempts. Section 15 records the completed M9A accounting of 120,080 valid canonical attempt rows, the exact cross-condition overlap, the exact TRAIN leakage, and the nearest-TRAIN normalized edit distance. Those results stay in the frozen M9A outputs. Report discordant metrics as mixed. These results assess generated-distribution movement toward held-out aptamer characteristics; they do not show binding, affinity, selectivity or NDM-1-specific generation.

### 5.2 Completed execution and result handoff

M10 Section 5 completed successfully on 19 October 2026 and passed review. This subsection records that execution and hands the reviewed result to the remaining thesis evaluation. It does not revise the Section 5.1 methods or the frozen scientific contract.

The production directory is `results/fine_tuning/m10_generator_evaluation/m10_section5_production_v1/`. The sequence-free report SHA-256 is `20e8daf7b2decb92299a9c0274273fd764db94c63c46e603c204cc7b0f09547f`. The run manifest SHA-256 is `5d828d918ff8d79e66d65181584175c87d125f69f59b76b2e3a48e78395803d0`. EVAL was read once. The accepted EVAL counts from that read are 181 scientific identities, 154 unique cores, and 79 clusters, of which 89 cores are short and 65 are long. The frozen metric specification SHA-256 is `2b0679b999235cc838298563448b01ef73f5fdd5132c5ddd3d9944f301f5c824`. The runner `scripts/modelling/generator_eval_m10.py` SHA-256 is `02735f84f264b3b0cfe7f9b5d2ab704846bb5840f9235707197e2999f9152c77`. The governing plan for the run remains v3.4, SHA-256 `1f3a73bc294a75c527e11f074c6d3265786c8e7e70d41eacf3ea83d3cf512941`.

The reviewed result is that D1 is closer than B1 on all three frozen sequence metrics overall and in both blocks. The nearest-edit change is small. The composition changes are larger. B2 is numerically closer than D1. The structural result is mixed. There is no exact TRAIN copying and no D1 exact-duplicate collapse. Full tables are in `docs/m10_generator_evaluation_results.md`.

Full-thesis completion item 2 is complete. The first Section 6 run used the already-opened held-out EVAL set and did not constitute a fresh opening; its rigorous rerun analyses the same already-opened set and is likewise not a new held-out opening. Section 6 rigorous rerun preparation is the next active scientific stage.

## 6. REF-calibrated AptaRank Tier 1 EVAL

### 6.1 Reference upload and blinded inputs

AptaRank performs its own empirical REF calibration internally from the uploaded corrected REF file. The project does not externally fit a distribution and feed it to the UI. In M9C, local code may calculate REF component distributions for thesis reporting, interpretation, and audit. Those calculations must be labelled descriptive and must not be represented as calibration of AptaRank. M9B does not open REF and does not calculate those distributions.

The reference file uses **113 corrected unique REF cores** (65 short, 48 long). The established Tier 1 description remains the review checklist: normalized MFE (lower favoured), ensemble defect (lower), positional entropy (lower), stem fraction (two-sided centrality around the REF median) and GC fraction (two-sided centrality), together with the established weighted mean, frozen weights/directions, empirical CDF/tie handling, shuffle criterion, preset and seed. M9B checked that description against the paper, GitHub implementation, implementation notes, and public interface evidence, using synthetic fixtures only. A detail those sources do not establish is a limitation. It is not filled by reimplementing the scorer. That M9B review is complete. AptaRank's internal calibration is not a REF performance evaluation. Ensemble defect in this checklist is an AptaRank Tier 1 component. It is outside M10, and M10 does not add an ensemble or structure-distance metric.

After unlock, take all **154 unique EVAL cores** and make one exact-length uniform A/C/G/U control per core using recorded master seed 42 and deterministic resampling for duplicate/known-core matches. Randomize opaque IDs into a **308-row blinded candidate upload before technical rejection**; keep real/control, pair, core, cluster and length in a private key. Laura uploads this with the frozen REF through the AptaRank UI, without a protein target. The analysis code consumes the downloaded results, never labels recovered by row position.

Uniform RNA is a synthetic floor, not an experimental non-binder. Candidate-specific dinucleotide-preserving shuffles provide the stronger composition-preserving null.

### 6.2 Required analysis

Report exact input/evaluable/excluded counts and the 79 corrected EVAL clusters before rejection; full real/control Tier 1 distributions; median/IQR and mean; paired real-minus-control difference; descriptive AUROC against this uniform null; real/control shuffle-pass n/N and rates under the frozen p ≤ 0.05 rule; and one secondary paired test with predeclared tie/zero handling.

Resample EVAL sequence clusters with their paired controls for 95% CIs on paired effects, AUROC and shuffle-pass rate/difference. The existing default is 10,000 replicates, seed 42, percentile intervals. Use complete pairs for paired effects/AUROC; report exclusions. A compact five-component descriptive table is enough. Do not hide low shuffle-pass sensitivity or weak separation, and do not interpret AUROC as universal aptamer classification. This resampling is AptaRank Tier 1 analysis. It is outside M10. M10 does not resample EVAL clusters and does not report a generator confidence interval.

### 6.3 Historical first execution: Standard preset

The first Section 6 run closed on 20 October 2026 after independent review found no material defect under its then-frozen Standard-preset method. The exact 308-row blinded upload produced 306 scored rows and two recorded length exclusions. The exclusions were the two members of one 121-nt pair, leaving 153 complete pairs across all 79 pre-rejection clusters. No candidate was replaced.

EVAL cores had mean aptamer-likeness 0.513 and median 0.512; paired uniform controls had mean 0.429 and median 0.409. The median paired EVAL-minus-control difference was 0.108 with cluster-bootstrap 95% CI 0.064 to 0.164. Descriptive AUROC was 0.638 with 95% CI 0.555 to 0.717. The frozen Wilcoxon signed-rank test gave W+ = 7,959 and two-sided p = 0.000164702. Shuffle passes were 9/153 EVAL cores and 7/153 controls; the paired pass-rate difference was 1.3 percentage points with 95% CI -4.1 to 6.6. All five cluster-bootstrap targets used 10,000 defined replicates with no imputation.

That Standard-preset result showed moderate Tier 1 separation from exact-length uniform RNA, alongside low and statistically indistinguishable shuffle-pass rates under the stronger candidate-specific null. It is not evidence of binding, target recognition or universal aptamer classification. The five-component table was unavailable because the UI exposed no verified component artifact; no component was recomputed. Raw and derived artifacts remain immutable under `results/aptarank/evaluation/section6_tier1_eval_v1/`. The reviewed analysis-summary SHA-256 is `b3dec6026badbdfb38cce10cd5d7ad04838d6a0f20069a1b7dab0878b6bf8422`. Under v3.7 this result is historical and superseded for the final thesis analysis solely because it used Standard rather than the required rigorous Evaluation preset. It must not be deleted, silently relabelled as rigorous or pooled with the rerun.

### 6.4 Required rigorous rerun

Run the exact same candidate upload (SHA-256 `5554f68fd94d1754ff9bcc87fba81be7dc8391af7e45703400796f4a5a336ad2`) with the exact same attempt-3 REF upload (SHA-256 `5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6`), no protein target, seed 42 and the named Evaluation preset. The expected effective settings are 200 sampled structures and 99 candidate shuffles; record what the UI actually displays and stop before scoring if the named preset differs. Reuse the existing private key and pair/cluster membership without regenerating candidates, controls, identifiers or ordering.

The rerun receives a new run id and result directory. Preserve the first run unchanged and record explicit rerun lineage: `method_correction_standard_to_evaluation_preset_before_remaining_thesis_scoring`. Apply the existing frozen Section 6 validation, joining, exclusion accounting, paired statistics, Wilcoxon rule and 10,000-replicate cluster bootstrap to the new export. Do not replace technical exclusions. Treat the rigorous run as the final Section 6 result regardless of whether it is more favourable, less favourable or null. Independent review and explicit result commitment are required before Section 6 closes again.

## 7. AptaRank manual execution and analysis-code boundary

Laura operates AptaRank manually through its UI. The expected workflow is: upload the frozen reference file; upload the sequence file; separately select or upload the independently chosen target configuration when Tier 2 is used; run the frozen UI configuration; and download the sequence file containing rankings and annotations. Local code prepares uploads, opaque-ID private keys, a target-configuration record, an expected-cell manifest, and a per-run checklist. It then imports Laura's downloads, validates IDs/settings/row counts, joins the private keys, computes the prespecified summaries and exports review tables. The M9B review of the paper, GitHub implementation, implementation notes, and interface is complete. This workflow remains required and is outside M10. No code stage assumes API access, starts UI jobs, changes deployment settings, or replaces AptaRank as the scorer.

The target JSON is a reproducible configuration record: canonical target, structure/PDB file and hash, chain/domain, binding mode, independent site/residue evidence or frozen pocket rule, numbering and preparation choices. Use it as an upload only if the deployed UI actually supports that format; otherwise Laura enters the frozen settings manually and captures the UI/run artefact. Select mode and site from literature/structural evidence with the supervisor, not from an attractive AptaRank score.

Before the first corrected production run, verify that the deployed named **Evaluation** preset displays 200 sampled structures and 99 candidate shuffles with seed 42. Check accepted columns, opaque-ID preservation, silent sequence conversions, score directions, target controls, download schema and runtime. If the named preset differs, stop and record the discrepancy rather than manually approximating it. Runtime is not grounds for switching to Standard or changing panels after scores are observed.

For each run, retain run ID, operator, timestamps, deployment/preset and effective settings, candidate/reference/target hashes, expected/exported/failed rows, raw CSV/run-artefact/log hashes, warnings and rerun lineage. Never overwrite a raw export. Mark every expected row or score cell as scored or technical failure; missing results are not zeros.

## 8. Illustrative Tier 2 EVAL: one or two targets

This is a deliberately bounded demonstration similar to the camera-ready workflow. It does not require a global census of EVAL target structures or a four-target/K=3 panel.

### 8.1 Freeze a usable score and panel

AptaRank constructs its Tier 2 shuffled-control bank from the uploaded REF. That bank is part of the deployed Tier 2 implementation. It is not an unrelated legacy global bank, and it is not deferred future work. M9C verified a 5,085-member bank during the Standard development-validation run. Do not assume without capture that every score-producing detail is identical under the Evaluation preset. During the first rigorous target-enabled Section 8 run, capture the untouched run artifact and record the realized bank count, construction/provenance fields, score direction and any exposed identifier or content hash. If the deployment still exposes no identifier or hash, do not invent either one. Local code must not instantiate or replace the bank.

Prefer the deployed percentile only when the verified bank's provenance, direction, within-mode comparability and independence from EVAL are adequately established. Otherwise, if the raw score has a known equation/direction and is comparable for the intended comparison, freeze raw same-mode scoring. In that branch make no percentile, band or >95 joint-region claim. If neither score is interpretable, report the reproducibility gap and mark the quantitative demonstration technically incomplete. Do not replace AptaRank's internal REF-derived bank with a separately engineered bank during the evaluation week.

After EVAL unlock, use metadata and independent structural sources only to identify **one or two** readily configurable targets with eligible EVAL cognate relations. Require an experimental protein structure, unambiguous chain/domain, independently justified binding mode and surface residues or frozen pocket rule where relevant. Fix structure, site, mode, preparation and target settings before scores; record eligible, configuration-failed, not-screened and run-failed cases. Apply a stable metadata/target/core-ID order if more candidates are available than the time cap. Do not pick a target because its Tier 1 or Tier 2 score is favourable.

With **two** valid same-mode targets, score eligible cognate aptamers against their own target and the other prespecified target if it is a permissible mismatch. Exclude aliases, known additional cognates and documented cross-binding conflicts. One mismatch per cognate relation gives K=1; report the relation-level score difference, win/tie/loss count and top-1 count with exact denominators. This is a small illustrative ranking, not broad Tier 2 validation.

With **one** valid target, score its eligible aptamers and show the frozen annotation/score distribution with N, technical failures and source/configuration limitations. **Do not compute cognate-versus-mismatch concordance, top-1 or a claim of target discrimination from one target.** If both targets are configured but no permissible mismatches remain, use this one-target/descriptive interpretation.

Laura performs the target-specific UI runs and downloads the exports. Code prepares the candidate file and target settings, validates returned IDs/cells, joins cognate labels locally and produces the small result table. Report target concentration and cluster/core counts even for a tiny panel; do not manufacture a precise CI from one or two independent clusters. A cross-tier correlation is not required for this illustration.

The frozen two-case panel uses separate descriptive runs: GRK2/3UZS chain A in pocket mode (one unique core, one cluster) and hen egg-white lysozyme/4M4O chain A in surface mode (two unique cores, one cluster). Because the modes differ, do not compute cross-target mismatch, concordance or top-1 statistics. Both runs use the Evaluation preset, 200 sampled structures, 99 candidate shuffles and seed 42.

## 9. Combined Tier 1 and NDM-1 Tier 2 comparison across generation conditions

### 9.1 Frozen 800-membership sample

Prepare exactly **200 condition memberships from each of B0, B1, B2 and D1** by deterministic, score-blind sampling from the existing frozen pools. That is 800 condition memberships in total. Keep B1/B2/D1 equal size and balance D1 across training seeds 43 and 44 as far as the frozen provenance permits. Preserve condition, checkpoint, training/generation/length/chunk seeds where applicable, original pool ID, sequence length and cleaning provenance. B0 remains an external baseline with a different length regime, not a fourth controlled replicate.

If an identical sequence is selected under more than one condition, upload it once under one stable opaque ID while retaining every condition membership in the private key and denominators. The blinded upload can therefore contain fewer than 800 distinct rows. This is provenance-preserving construction, not a new overlap experiment. The measured UI performance supports the full 200-per-condition design; the former 150/100 runtime fallback is removed prospectively. Technical exclusions are recorded and are not replaced.

### 9.2 One target-enabled run

Run the complete deduplicated 800-membership sample once in AptaRank with the frozen REF and the prespecified NDM-1 target configuration:

- target: NDM-1;
- PDB: 5ZGX;
- chain: A;
- mode: pocket/groove recognition;
- residues: 120, 122, 124, 189, 208 and 250;
- prepared-target identifier: `0fde4d5e4370`;
- Evaluation preset (rigorous mode), seed 42, 200 sampled structures and 99 candidate shuffles.

Prepare a target settings record, expected-cell manifest, blinded candidate upload and private membership key before the run. Laura enters the frozen settings and executes the target-enabled UI run, then downloads every available raw export and artefact. Code validates IDs, rows, sequences, settings, hashes and failures. It does not replenish rejected candidates.

The same run supplies Tier 1 aptamer-likeness/shuffle outputs and NDM-1 Tier 2 outputs for the same frozen candidates. Report the tiers separately. Do not form a combined score, joint threshold or rule in which a favourable target score rescues weak Tier 1 evidence.

Use percentile bands only if Section 8 establishes an interpretable and consistent deployed bank. Otherwise report the direction-known raw same-mode NDM-1 score and omit percentile, band and joint-region claims.

### 9.3 End-to-end comparison and dependence

Report B1 versus D1 as the primary downstream comparison, B2 as the secondary non-neural data-scale comparator, and B0 as the external baseline. For each condition report selected/scored/failed membership counts, Tier 1 distribution and shuffle-pass n/N, Tier 2 distribution under the Section 8 score branch, and the relationship between the two separate outputs. Retain D1 seed 43 and seed 44 summaries and the relevant matched B1/D1 provenance where available.

Candidate rows, chunks and generation seeds are not independent training replicates. Two D1 training seeds do not support a precise training-population interval. The analysis describes the frozen samples and does not prove that an entirely new training run would behave similarly. Interpret the end-to-end comparison in light of Section 6's moderate uniform-null separation and low shuffle-pass sensitivity and Section 8's observed Tier 2 limitations. No Section 9 candidate enters a supervisor shortlist from this 800-membership comparison.

## 10. Full-pool D1 NDM-1 run and supervisor review

Run the complete frozen **30,000-member D1 unique-valid RNA pool** through AptaRank once with the same frozen REF, target, preset and settings used in Section 9. The source pool SHA-256 is `9b6cfb6c6e0d1cb1f7d7c3446843c193ac7934751c0394561655c132e7d5d612`. Prepare a fresh opaque-ID upload and restricted private provenance key under the frozen blinding procedure; the existing source IDs are provenance IDs and must not be uploaded as AptaRank opaque IDs. No score-informed subsampling, replenishment or second target run is permitted.

Preserve and validate the exact upload, every returned row, exclusions, raw exports, target record and run artefacts. Build the supervisor-review pool only if Section 8 establishes that the deployed compatibility bands are interpretable for this use. The UI token `strong` is the high-compatibility category intended here. Apply this frozen filter and ordering:

~~~text
eligibility 1     = valid scored D1 candidate
eligibility 2     = shuffle token is pass
eligibility 3     = NDM-1 compatibility token is strong or moderate
ordering 1        = strong before moderate
ordering 2        = better Tier 1 rank within compatibility band
ordering 3        = ascending stable opaque candidate ID on an exact Tier 1 tie
maximum pool size = 100 candidates
technical rows    = excluded and recorded, never replaced
~~~

Retain every eligible candidate when 100 or fewer qualify. If more than 100 qualify, retain the first 100 under the frozen band-then-Tier-1 ordering. The desired manual-review workload is 50–100 candidates, but 50 is not a minimum scientific denominator: if fewer than 50 qualify, retain and review all qualifying candidates, report the shortfall, and do not admit weak-compatibility or shuffle-fail candidates to fill the pool. Do not replenish technical exclusions. This is a filter followed by a lexicographic ordering, not a numerical Tier 1/Tier 2 composite.

If Section 8 establishes no interpretable compatibility-band basis, the filtered NDM-1 review pool is technically unavailable. Do not invent a raw-score cutoff, substitute Tier 1 alone or weaken the filter after observing D1 results. Record counts at every gate: uploaded, scored, technically excluded, shuffle-pass, strong, moderate, jointly eligible, retained and capped-out.

Generate a restricted supervisor-review table for the retained candidates containing opaque ID, sequence and length, checkpoint/training seed, existing novelty provenance, Tier 1 score/rank/shuffle status, NDM-1 Tier 2 score and justified percentile/band, warnings, failures and source hashes. Label it **computationally prioritised D1 candidates for future experimental validation**.

Laura and her supervisor review this frozen pool using experimental constraints, but they do not change AptaRank scores, target settings or pool membership. Record reviewer/date, selected IDs, reasons and exclusions, including a decision that no candidate should advance. Extract exactly the recorded selections into a private final shortlist and a thesis-ready aggregate table. No binding, affinity, selectivity or inhibition claim follows from inclusion in either the filtered review pool or the final supervisor selection.

## 11. Five-day critical path

This timetable is conditional on the Section 4 prerequisites and availability of the supervisor for the D1 review. M10 remains the server-CPU Section 5 generator evaluation and the one opening of EVAL. Later AptaRank work uses that already-opened set and does not open EVAL again. Section 6 is reopened for its same-input rigorous rerun; Section 8 follows after that rerun is captured and validated.

| Timing | Required work and output |
|---|---|
| Before Day 1 | M9A is already complete under the immutable v3.2 plan. M9B reviews the AptaRank paper, public implementation, and notes, and tests schemas, sampling, blinding, validators, checklists, and synthetic workflow examples. Proposed illustrative target(s); literature-based NDM-1 configuration; supervisor review slot. M9B does not open TRAIN, VALIDATION, REF, EVAL, or a production sequence ledger, and it does not score. |
| Day 1 | M9C, before any EVAL unlock: open only the authorized corrected REF; write descriptive REF feature summaries; verify accepted and dropped REF counts; verify the identity and realized count of AptaRank's internally constructed REF-derived Tier-2 shuffled-control bank; run the synthetic and manual UI preflight; freeze environment, dependencies, configuration, sampling, runtime fallback, and failure handling; write the explicit EVAL-unlock record. |
| Day 2 | Complete. M10 only: opened EVAL once and ran the frozen four-condition generator EVAL on server CPU, including the Section 5 outputs, metric specification, design-aware interpretation, provenance, and reviewed derived results. |
| Day 3 | Preserve the independently reviewed Standard Section 6 run as historical evidence; rerun the exact same blinded EVAL/control upload target-free under the Evaluation preset; validate and independently review it. Then run the already-frozen two-case Section 8 panel under the same rigorous preset. |
| Day 4 | Prepare the deterministic 200-per-condition sample and run one target-enabled Section 9 job on the deduplicated 800 memberships; validate and compute separate Tier 1 and NDM-1 Tier 2 comparisons. |
| Day 5 and review window | Prepare and run the full 30,000-member D1 target-enabled job once; validate all rows; apply the frozen shuffle-pass and strong/moderate compatibility filter; cap the Tier-1-ordered review pool at 100; then complete the supervisor review and reproducible archive. Move the schedule rather than reduce the full-pool commitment after scores are seen. |

Long UI jobs can run unattended only if recovery/export reliability has been tested. Write methods and results while jobs run. Do not use a favourable preliminary score to reconfigure an in-progress panel.

## 12. Completion criteria

M10 is complete. Section 6 is reopened for its rigorous rerun. No single generator-quality score is formed. The list below defines completion of the full thesis evaluation.

The thesis evaluation is complete when all of the following exist with exact denominators and traceable artefacts:

1. Corrected role/hash contract, M9A–M9C records and a clean one-time EVAL unlock.
2. **Complete.** Four-condition B0/B1/B2/D1 generator EVAL, with B1–D1 as the primary causal comparison, B2 as the secondary data-scale comparator, and B0 as the external baseline; frozen metrics, seed limitations and honest null/mixed results.
3. REF-calibrated Tier 1 EVAL on 154 unique EVAL cores and their paired exact-length controls under the Evaluation preset, including distributions, effects/AUROC, shuffle passes and cluster-aware uncertainty. The completed Standard run is historical and does not satisfy this corrected completion item.
4. One- or two-target **illustrative** Tier 2 EVAL, labelled descriptive for one target and cognate-versus-mismatch only when two same-mode targets yield permissible comparisons.
5. Separate Tier 1 and NDM-1 Tier 2 outputs from one target-enabled run of the frozen 200-member sample from **all four** conditions, with B1–D1 primary, B2 secondary and B0 external.
6. One target-enabled run of the complete frozen 30,000-member D1 pool, exact gate/failure accounting and a deterministic supervisor-review pool containing at most 100 shuffle-pass candidates with strong or moderate target compatibility, ordered by compatibility band and then Tier 1 rank.
7. A supervisor-reviewed D1 decision record followed by extracted selected records or an explicit decision that none should advance.
8. Immutable raw UI downloads, prepared upload files/target settings, normalized data, version-controlled analysis, manifests/hashes and thesis-ready methods/results/limitations.

There is no favourable-score completion criterion. An unavailable target, uninterpretable score or missing UI export is an explicit uncompleted technical item, not a negative biological finding.

## 13. Analysis checks, provenance and thesis write-up

Before unblinding, synthetic fixtures should cover opaque-ID joins after row shuffling, duplicates, invalid/missing rows, paired controls and clustered EVAL resampling, effect/AUROC directions, variable-K/tied Tier 2 ranking, single-target descriptive mode, score-blind four-condition sampling, B0 separation, D1 seed roles, the combined-run schema, the shuffle-pass plus strong/moderate filter, band-priority/Tier-1 ordering, the 100-candidate cap and fewer-than-50 accounting. Review code/output using synthetic or non-sensitive fixtures; apply it locally to restricted sequences.

Normalized generator tables retain `record_id`, the source-artifact hash, every condition/pool/checkpoint identity, the attempted/parsed/valid/unique denominator, seed role, EVAL or REF parent hash, run ID, target configuration, technical exclusion and score-basis branch. Validate schemas/ranges/unique keys, spot-check representative rows against Laura's UI artefacts, and regenerate final tables cleanly from immutable raw inputs. Every reported number maps to source hashes, the filter/statistic, code revision/environment and output hash.

Write five Results subsections matching Section 1's five required analyses. The generated-condition subsection presents Tier 1 and NDM-1 Tier 2 outputs separately for the same 800 memberships. The full-pool D1 subsection reports the complete filter flow and distinguishes the frozen filtered review pool from the supervisor's final choices. The discussion covers few D1 seeds, asymmetric pools, B0 length differences, synthetic controls, incomplete target-family metadata, the Section 6 and Section 8 limitations, bank/score limitations, modified chemistry not represented and absent wet-lab validation. Report low Tier 1 pass rates, weak target ranking, a review pool below the desired 50 candidates and unselected NDM-1 candidates as found. No aggregate generator-quality score or new Tier 1/Tier 2 composite is introduced.

## 14. Deferred future work — outside this evaluation

AptaRank's Tier 2 shuffled-control bank is constructed from the uploaded REF and is verified in M9C. It is not legacy, and it is not an item of future work. The following items are recorded for later work. None is required to finish the five analyses above:

- **Published NDM-1 sequence-reference comparison (NDM1-REF).** The approved 10-record view from the separate 35-row evaluation_references.csv (SHA-256 b6ba6b2cde4a18c04130ecdc457626c5e60b8b90d3ad5b9bae6cb1bfd1f77dad) remains available: three ssDNA references (CN102 SEQ ID NO:1, APNV, NDM1-H14.2_43) and seven RNA records (D902, D907, D909, D913, D914, D918, D920). A future comparison must freeze D1 candidates before accessing reference sequences for ranking, preserve molecule/role distinctions, APNV cross-reactivity and RNA/ssDNA caveats, and treat sequence identity as descriptive rather than binding evidence.
- **Broader Tier 2 validation.** More targets, modes and mismatches; full structural eligibility screening; homology-sensitive/alternate-site sensitivity; leave-one-target-out analysis; matched uniform-control Tier 2 runs and a formal joint-region analysis. The current one- or two-target result is illustrative. These extensions do not replace the REF-derived shuffled-control bank that AptaRank constructs and that M9C verifies.
- **Related carbapenemase stress test.** Score the same frozen NDM-1 candidates against independently justified KPC-2/OXA-48 structures if later feasible; mismatches are not experimental non-binders and this cannot prove selectivity.
- **Expanded generated-condition analysis.** Larger four-condition samples, full-pool B0/B1/B2 target scoring, extra training seeds, a harmonized B0 rerun and extensive seed/length/subgroup sensitivity. The full D1 target-enabled run in Section 10 is part of the thesis evaluation and is not deferred future work.
- **Formal corpus ablation and experimental follow-up.** The current curated corpus is already a methodological contribution; ablation, binding measurements and independent functional testing need separate time and evidence.
- **Generated-sequence clustering.** Near-duplicate clustering of generated outputs, identity-threshold choice, threshold sensitivity, cluster-size summaries, Shannon diversity, and effective-cluster analyses belong to a later sequence-prioritisation pipeline. Do not import a corpus clustering threshold into generated outputs. Exact duplicate and multiplicity reporting remains in the core evaluation.
- **Representation-space analysis.** A later study would need a frozen encoder and hashes, a justified query-token-to-sequence aggregation, normalization, a distance or kernel, a subsampling policy, and seed-aware reporting. Representation similarity does not establish binding, specificity, activity, or affinity.

Do not use future-work results to relabel the one-time thesis EVAL as fresh or to retrofit this plan's score definitions.

## 15. Source basis and document status

This revision starts from the user's locally edited v2.7 plan and preserves the corrected S7D counts/hashes, formal evidence definitions, M4 seed roles, B1/D1 primary comparison, Tier 1 methods, manual AptaRank UI and claim boundaries. The corrected corpus authority is corpus_report.md (closure state 25 September 2026) and rna_aptamer_corpus_curation_plan.md v1.6, with corrective closure commit 10aac629bb0ef0337107c3d628b23e1897962af9 and documentation handoff 05616cf82c3c7c1adbe87f631590f456c44c946a. The separate camera-ready workflow still governs its one-day publication analysis.

Version 3.7 is the active corrective protocol from 20 October 2026. Version 3.6 remains unchanged as the historical plan that first carried Standard into the remaining workflow. Version 3.5 remains the governing plan for the completed first Section 6 run, whose artifacts and independent review remain valid for that Standard-preset execution. Version 3.4 remains the governing plan under which M10 ran. Version 3.2 remains the immutable governing artifact for completed M9A, and version 3.3 remains the M9C-frozen artifact. Version 3.7 does not rewrite or delete an earlier plan or result.

### Revision note — 12 October 2026

M9A closed at commit `4a8246f0e4062ae13af161b98999f72382bd966c`. Version 3.3 narrowed M9B to preparatory-only work and left production overlap and leakage solely in M9A. Actual REF access and AptaRank's internal calibration moved to M9C. No scientific result motivated the change.

### Revision note — 19 October 2026

Version 3.5 succeeds governing v3.4 as the active plan for the remaining full-thesis evaluation. M10 Section 5 had already completed successfully and passed review. This succession records that handoff. It does not change the frozen Section 5 scientific contract or the frozen Sections 6–10 methods.

### Revision note — 20 October 2026

Version 3.6 succeeds v3.5 after Section 6 completed and passed independent review. It commits the reviewed Section 6 result without changing its method or artifacts. Before generated-condition AptaRank scores were observed, it prospectively replaced the separate generated Tier 1 and top-L Tier 2 runs with one target-enabled run of the same frozen 200-per-condition sample. It also moved supervisor review away from that comparative sample and added one target-enabled run of the complete frozen 30,000-member D1 pool followed by a deterministic, capped review pool requiring shuffle pass and strong or moderate compatibility. Tier 1 and Tier 2 outputs remain separate; no combined score is introduced.

### Corrective revision note — 20 October 2026

Version 3.7 corrects the production preset before any Section 8, Section 9 or Section 10 scores were observed. The public/deployed preset terminology distinguishes Quick, Standard and Evaluation; Evaluation is the paper's rigorous configuration of 200 sampled structures and 99 candidate shuffles. Standard was verified during M9C development validation and was then carried into the first Section 6 run and the initial remaining-run sheets. Laura explicitly determined that all thesis production runs must use rigorous mode. The first Section 6 result remains immutable and independently reviewed but is superseded for final thesis reporting. Section 6 is reopened for a same-input Evaluation-preset rerun. Candidate memberships, controls, targets, metrics, thresholds and downstream selection rules are unchanged. This correction is procedural and was made before any remaining target-aware outcome was observed.

### Status recorded on 12 October 2026

M9A is complete. It exclusively owns parsing and validity accounting, within-condition duplicate accounting, cross-condition exact overlap, exact TRAIN leakage, nearest-TRAIN normalized edit distance, and the generator-output freeze. The parser runner commit is `378f574b1620a9ff999082262868bffbe647d063`. The hardening commit is `f703a8c721384e821337eba9a59093918f8decfe`. The parsing evidence commit is `1c74fb9b3c92247b524dbe40a744f59525d18bd2`. The combined derived ledger SHA-256 is `d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e`, with 120,080 valid canonical attempt rows. Within-condition duplicates occurred only in B1. Exact cross-condition overlap and exact TRAIN leakage, including nearest-TRAIN normalized edit distance, are closed in the M9A result directories. Those aggregate conclusions are upstream evidence. This plan does not recompute them and does not reopen sequence-bearing inputs.

On 12 October 2026, M9B had started as preparatory-only work and was not yet frozen. That sentence is historical. M9B later closed at commit `f7aba126170fce7c6da8cf7653ee282402b2f0e4`, and M9C later closed with EVAL unlocked and unopened. The 12 October statement that EVAL stayed locked is superseded by the M9C closure.

### Historical status — 17 October 2026

This block records the status on that date. It is historical.

M9A, M9B, and M9C are complete. M9C unlocked EVAL. EVAL remains unopened, and M10 execution remains unauthorized. `eval_opened` is false. `m10_started` is false. `m10_execution_authorized` is false. Version 3.4 is the active plan. Version 3.3 stays the M9C-frozen artifact at the hash above.

M10 is only Section 5, the four-condition generator-level EVAL, on server CPU after explicit EVAL authorization. B1 versus D1 remains primary. B2 remains the secondary non-neural data-scale comparator. B0 remains external and length-aware. Sections 6–10 and the NDM-1 decision record remain required thesis-evaluation work and are outside M10. M9B and M9C remain completed groundwork for that later AptaRank workflow. EVAL is opened once, at authorized M10 execution. Later AptaRank analysis uses that already-opened held-out set. It is not a second fresh opening.

The M10 scientific contract in Section 5.1 is frozen by this revision. The three headline closeness metrics stay separate. There is no aggregate generator-quality score. Diversity is exact-duplicate diversity only. Clustering, representation analysis, generator confidence intervals, bootstrap, hypothesis tests, and EVAL-cluster resampling are outside M10. D1 seeds 43 and 44 and matched blocks A and B are reported separately, with observed ranges only. The 154 unique EVAL cores are weighted once each. The 79 clusters are a design fact and a limitation and do not weight formulas. TRAIN-overlap and nearest-TRAIN results are the frozen M9A outputs cited in Section 5.1. The thesis-facing parsed count is `successfully_parsed_outputs`. The generator-evaluation ViennaRNA version is 2.7.0, verified from the frozen generator record, and it is distinct from AptaRank's ViennaRNA 2.7.2. The executable metric specification is frozen and production-ready. M10 execution and EVAL access remain unauthorized. The ledger adapter, single-read EVAL adapter, matched schedule, structure wrapper and distinct-sequence cache, and production writer are implemented and synthetically verified. They have not run biologically, and awaiting authorization is not an active implementation blocker. This note records no new scientific result, does not authorize M10, and does not open EVAL.

### Historical status — 19 October 2026, before Section 5 execution

This block records the pre-execution status on that date. It is historical. Its statements that execution remained unauthorized describe that pre-execution record.

The executable metric specification `config/modelling/generator_eval_metric_spec.json` is frozen and production-ready. M10 execution remains unauthorized. EVAL access remains unauthorized. `eval_opened` is false. `m10_started` is false. `m10_execution_authorized` is false. Version 3.4 remains the active plan. Version 3.3 stays the unchanged M9C-frozen artifact. This note records no EVAL outcome and does not authorize production.

### Current status — 20 October 2026

Version 3.7 is the active plan for the remaining full-thesis evaluation. Version 3.6 and the first Section 6 closure remain unchanged historical records. Version 3.4 remains the governing plan under which M10 ran and is not rewritten. Version 3.3 stays the unchanged M9C-frozen artifact.

M10 Section 5 completed successfully and passed review. EVAL was opened once. Full-thesis completion item 2, the generator EVAL, is complete. The production directory, report and manifest hashes, accepted EVAL counts, and the frozen metric-specification and runner hashes are recorded in Section 5.2. Full tables are in `docs/m10_generator_evaluation_results.md`.

Section 6 is reopened only for the same-input Evaluation-preset rerun. Its Standard result remains preserved but is not the final thesis result. Sections 8–10 then use the same Evaluation preset. Laura performs all AptaRank UI runs manually. This note does not recalculate Section 5 or either Section 6 result.
