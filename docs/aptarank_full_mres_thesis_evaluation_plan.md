# AptaRank + RNAGenesis MRes Thesis Evaluation — Supervisor-Scoped FINAL Plan

**Project:** Towards prediction-guided generative design of RNA aptamers against carbapenemase targets  
**Document version:** 2.7\
**Revision date:** 29 September 2026\
**Status:** FINAL — approved MRes evaluation execution plan incorporating supervisor scope control  
**Evaluation execution budget:** Approximately one week: five working days, separate from the camera-ready day.  
**Broader thesis completion:** Approximately six weeks.  
**Required scope:** Final held-out RNAGenesis generator-level EVAL, final REF-calibrated AptaRank Tier 1 held-out EVAL, and reproducible thesis-ready reporting of those two analyses.  
**Execution model:** Local frozen generator-evaluation code; manual AptaRank UI runs with immutable exports; version-controlled, AI-assisted downstream Python analysis.

> **Governing scope.** Complete and write the minimum defensible thesis core first. Final generator-level EVAL is the highest-priority experiment and the principal evidence for the RNAGenesis fine-tuning/domain-adaptation contribution. AptaRank Tier 1 held-out EVAL is the second required experiment. Tier 2, downstream generated-condition analyses, the NDM-1 application, B0 Tier 1 and the published-reference comparison are contingent. They must not compress interpretation, reproducibility work or thesis writing.

> **Corrected corpus closure — 2026-09-25.** The S7D corrective pass is complete and frozen. Current authority is the corrected `corpus_report.md` plus `rna_aptamer_corpus_curation_plan.md` v1.6. Corrective closure commit: `10aac629bb0ef0337107c3d628b23e1897962af9`. Documentation handoff commit: `05616cf82c3c7c1adbe87f631590f456c44c946a`. Superseded corpus commit `095236dfb13d1d3b13f11bbb34c2e48319c10184` is historical only and must not be used as the modelling/evaluation contract. Corpus closure does not assert that fine-tuning, deployment verification, calibration or evaluation runs are complete.

> **v2.7 seed-contract clarification.** This revision does not alter the M4 implementation or regenerate any pool. It aligns evaluation with the implemented seed roles: D1 training seeds are the independent model-training replicates; B1 Phase A and Phase B seeds are paired protocol/length-control seeds rather than independent replicates; the limited B1/D1 comparison uses a shared, deterministic generation-chunk schedule; B2 is a single-seed null pool; and B0 retains historical provenance only. Seed-aware inference is permitted only where the design supplies genuine training replication or an actual matched B1/D1 chunk comparison.

> **v2.5 supersession.** The v2.5 revision superseded v2.4 where scope differed. It narrowed required evaluation to generator-level held-out EVAL plus core Tier 1; made Tier 2, downstream application, B0 and NDM1-REF contingent; made NDM-1 the only downstream application target; moved the two related carbapenemases to one optional cross-target stress test; and updated NDM1-REF to the verified 10-record panel already present in `evaluation_references.csv`. All corrected S7D facts, hashes, role separation, leakage safeguards, Tier 1 definitions, generator-EVAL logic, reproducibility requirements and scientific claim boundaries remain in force.

## 1. Governing priority and completion hierarchy

### Priority 1 — thesis completion core / MUST COMPLETE

1. **Final generator-level held-out EVAL.** Frozen B1/B2/D1 generation conditions are compared with untouched-at-unlock EVAL. B1 versus D1 is the primary controlled comparison; B2 is the already planned non-neural null.
2. **Core AptaRank Tier 1 held-out EVAL.** Preserve the corrected REF-to-EVAL design: 113 unique REF cores calibrate the fixed method; 154 unique EVAL cores are assessed against 154 paired exact-length uniform controls in one blinded 308-row input before technical rejection.
3. **Reproducibility, interpretation and thesis-ready reporting** for those two analyses. Writing and interpretation time is protected.

### Priority 2 — contingent / extended scope

4. **Limited Tier 2 EVAL**, only after the core is secure. It may be explicitly limited/illustrative and must not become the critical path.
5. **Generated-condition AptaRank Tier 1 for B1/B2/D1**, if it fits easily after the held-out core.
6. **NDM-1 downstream application**, only after the core is secure and after the generated-condition Tier 1 shortlist exists.

### Priority 3 — first things to cut

7. **NDM1-REF published NDM-1 reference-sequence comparison** — defer first when time is constrained.
8. **B0 Tier 1** — defer second.

After those two cuts, reduce or omit further non-core/illustrative work as needed. Tier 2 may be scientifically more informative than NDM1-REF, but it still cannot delay the Priority 1 work. Do not add another null condition, new corpus ablation, extensive sensitivity analysis or other optional experiment unless the core is complete and thesis-writing time is protected.

The curated corpus is itself a methodological/design contribution through rigorous construction, role separation, target balancing, similarity-aware leakage control, provenance and auditability. A formal corpus ablation is not required for the MRes evaluation and is deferred to future work.

A weak, mixed, null or technically limited result is scientifically acceptable. It is preferable to a post-hoc composite score, favourable subset or expanded experiment.

## 2. Data roles, scientific questions and claim boundaries

### 2.1 Role contract

```text
TRAIN      -> RNAGenesis fitting only
VALIDATION -> generator/model development only
REF        -> AptaRank calibration only
EVAL       -> final held-out generator and AptaRank assessment only

evaluation_references.csv
           -> separate target-specific published-reference resource;
              never model fitting, AptaRank calibration or candidate selection
```

TRAIN and VALIDATION must not calibrate AptaRank. REF must not select RNAGenesis checkpoints, hyperparameters, generation settings or cleaning rules. EVAL must not choose scoring equations, weights, thresholds, bandwidths, bank construction, generation samples, shortlist sizes or analyses. EVAL remains sealed until the M9C/M10 unlock.

Authorised curation/reference-verification processes may access published reference sequences to verify provenance, define the approved NDM-1 view and perform leakage auditing. RNAGenesis, AptaRank, candidate-ranking, shortlist-selection and evaluation-analysis workflows remain blind to the 10 NDM-1 reference sequences until the frozen top-50 D1 comparison set has been committed. Reference results cannot feed back into models, settings, rankings, shortlist membership, target configuration or earlier results.

### 2.2 Scientific questions

- **Final generator EVAL:** after all generator decisions are frozen, did D1 move the generated distribution toward held-out experimentally supported aptamer characteristics relative to B1 while preserving validity, novelty and diversity? B2 supplies non-neural context.
- **Tier 1 EVAL:** under frozen REF calibration, do held-out EVAL cores score differently from paired exact-length uniform RNA controls, and how often do they exceed their candidate-specific dinucleotide-shuffle null?
- **Contingent Tier 2:** in a small score-blind same-mode panel, does the direction-known geometric score tend to rank known cognate targets above prespecified mismatched targets?
- **Contingent downstream analysis:** does D1 change computational prioritisation relative to B1, with B2 as supporting context, under the frozen AptaRank system?
- **Contingent NDM-1 application:** what computational ranking is obtained for equal top-L B1/B2/D1 candidate sets under one frozen NDM-1 target configuration?
- **Optional NDM1-REF:** does the frozen top-50 Tier-1-ranked D1 set share obvious nucleotide-level similarity with the approved 10-record published NDM-1 panel?

Use **similarity-aware, cluster-disjoint**, **known cognate target**, **prespecified mismatched target**, **target-aware geometric compatibility** and **computational prioritisation**. Do not claim a family-aware split, binding/affinity/selectivity prediction or validation, experimental non-binders, or that D1 learned carbapenemase-specific binding. Preserve Tier 1 ranking with Tier 2 annotation; create no Tier 1 + Tier 2 composite score.

Canonical A/C/G/U sequence cores do not represent modified chemistry such as 2F or 2OMe. Chemistry is a limitation/descriptive attribute, not an unmodelled source of claimed predictive capability.

## 3. Corrected frozen S7D execution contract

The corrected S7D corpus report (closure state **2026-09-25**) and curation plan **v1.6** govern these facts. The primary corpus is RNA/protein-target only, retaining E2-E4; E5, non-protein and ssDNA records remain excluded/parked under the curation plan.

- Final corpus: **1170 identities**, **1031 distinct `sequence_core` values**, **790 clusters**, **409 canonical targets**.
- Identity-grain evidence E2/E3/E4/E5: **800 / 247 / 123 / 0**.
- Maximum target share: **34/1170 = 0.0290598291**, for **HIV-1 Rev protein**.
- Top-level partition identities: **FT 858 / REF 131 / EVAL 181**. TRAIN and VALIDATION are the subordinate frozen FT split.

| Role | Clusters | Identities | Unique cores | Targets | Corrected SHA-256 | Permitted use |
|---|---:|---:|---:|---:|---|---|
| TRAIN | 569 | 726 | 669 | 320 | `84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0` | RNAGenesis fitting |
| VALIDATION | 63 | 132 | 95 | 100 | `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd` | training/model development; quarantined camera-ready exception only |
| REF | 79 | 131 | 113 | 97 | `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23` | AptaRank calibration; never performance evaluation |
| EVAL | 79 | 181 | 154 | 111 | `ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015` | final held-out assessment only |

### 3.1 Frozen regimes and integrity

| Scope | Short unique cores | Long unique cores | E2 identities | E3 identities | E4 identities |
|---|---:|---:|---:|---:|---:|
| Corpus | 595 | 436 | 800 | 247 | 123 |
| TRAIN | 386 | 283 | 496 | 153 | 77 |
| VALIDATION | 55 | 40 | 90 | 28 | 14 |
| REF | 65 | 48 | 88 | 30 | 13 |
| EVAL | 89 | 65 | 126 | 36 | 19 |

The short/long regime is the frozen S6 two-component GMM assignment/rule. Do not invent a nucleotide cutoff or refit it on evaluation data. Similarity clusters must not be described as complete biological families.

The corrected release records cluster crossings **0**, core crossings **0**, identity duplication **0**, exact evaluation-reference leakage **0**, >=90% evaluation-reference leakage **0**, excluded target aliases in primary **0**, non-protein in primary **0**, and E5 in primary **0**. TRAIN/VALIDATION `^[ACGU]+$` alphabet-gate failures are **0 / 0**. `corpus_final.txt` has **669 lines**, **669 unique lines**, **0 duplicates**, and contains only deduplicated frozen TRAIN cores in first-occurrence order. VALIDATION/REF/EVAL contamination of training text is **0 / 0 / 0**.

These are release-audit facts, not newly executed evaluation results. The broader `evaluation_references.csv` remains **35 rows** and separate from generic held-out EVAL. Its approved NDM-1 subset is governed by Section 10.

### 3.2 Corrected output hashes

| File | SHA-256 |
|---|---|
| `corpus_final.csv` | `2797e6767f78029574df1b6cdf51bbe7952ea8affce83870441b3d3d93c98849` |
| `ft_train.csv` | `84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0` |
| `ft_validation.csv` | `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd` |
| `ref.csv` | `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23` |
| `eval.csv` | `ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015` |
| `ft_split_assignment.csv` | `74b2f7db21184cd418580bc299a3cac6af61450848d9e7e45c963a0667f2a27a` |
| `corpus_final.txt` | `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d` |
| `evaluation_references.csv` | `b6ba6b2cde4a18c04130ecdc457626c5e60b8b90d3ad5b9bae6cb1bfd1f77dad` |
| `corpus_manifest.json` | `08da8d5e44413ea9ab57c128dbe4ef7986dab7a2bfa794cfef6fb4724577565f` |

These identify corrected source files, not derived uploads or calibration artefacts, which require their own hashes and parent-release lineage. The manifest's retained `build_date = 2026-09-22`, `governing_plan_version = 1.5` and pre-closure `repository_head_baseline` are build metadata, not the current closure date, plan version or closure commit.

### 3.3 Evidence ordering and scientific units

| Level | `binding_evidence_type` | Score |
|---|---|---:|
| E1 | `structural` | 5 |
| E2 | `quantitative_affinity` | 4 |
| E3 | `qualitative_binding` | 3 |
| E4 | `selection_enrichment` | 2 |
| E5 | `database_annotation` | 1 |

The frozen primary corpus retains E2-E4. The formal E2 > E3 > E4 order is provenance/eligibility information and must not become a new result-driven selection axis.

| Analysis | Observation | Dependence preserved |
|---|---|---|
| Final generator EVAL | Frozen generated-pool distributions compared with unique EVAL cores | Independent D1 training-seed blocks where available; actual matched B1/D1 generation-chunk blocks where applicable; length strata; EVAL clusters where the frozen procedure resamples the reference |
| Tier 1 EVAL | One unique sequence core | Frozen sequence cluster and its paired control |
| Contingent Tier 2 EVAL | One unique core x canonical-target cognate relation | Sequence cluster, including multiple targets of one core |
| Generated conditions | Candidate within a frozen generation pool | D1 training-seed membership and actual matched B1/D1 generation-chunk provenance; candidates, length-specific seeds and batches are not training replicates |
| NDM1-REF | Frozen D1 candidate x approved reference | Descriptive repeated pairs only; no hypothesis test |

## 4. M6 scope lock, prerequisites and unlock sequence

### 4.1 M6 — real-data pilot / final evaluation scope lock

M6 occurs before the final evaluation week and before EVAL is opened. Assess:

- whether the generator-evaluation suite is implemented, tested and runtime-feasible;
- real-data pilot runtime and available GPU time;
- achieved D1 training-seed count;
- readiness of B1/B2/D1 generation pools;
- whether generation effort and pool sizes are reasonably symmetric;
- Tier 1 UI/runtime feasibility;
- whether a small Tier 2 experiment is realistic;
- whether the NDM-1 application, B0 and NDM1-REF fit without compressing thesis writing; and
- whether the **2 October modelling/evaluation target remains realistic** given the real-data pilot, generator-suite readiness/runtime, available GPU/time, and Tier 1/Tier 2 runtime evidence. If it is not realistic, reduce scope immediately under this hierarchy rather than compressing the subsequent thesis-writing period.

Freeze `m6_evaluation_scope_lock` with included and deferred workstreams, rationale, expected runtimes, chosen D1 seed count, primary generation-analysis sample sizes, generation-pool sizes, any Tier 2 scope, B0 status, NDM1-REF status, and an explicit `target_date_feasible = yes/no` decision for the 2 October target with rationale.

Allowed outcomes are:

- **Minimum thesis scope:** final generator EVAL + Tier 1 EVAL + reproducible thesis-ready write-up.
- **Extended scope:** minimum scope plus limited Tier 2 and/or NDM-1 application and generated-condition Tier 1.
- **Contextual extras:** B0 and NDM1-REF only when higher-priority work is secure.

The M6 decision is based on feasibility, never observed EVAL or condition performance. The final EVAL partition remains sealed until M9C/M10.

### 4.2 Seed and generation-symmetry contract

Three D1 training seeds are preferred, not mandatory. Freeze the achieved/feasible count at M6 and M9A before result inspection. Do not sacrifice thesis completion or writing quality solely to obtain three seeds. With one or two independent D1 training seeds, report that uncertainty is limited and, with one seed, does not include training-run variability.

The frozen M4 implementation distinguishes the following seed roles and is not changed by this evaluation plan:

- **B1 Phase A protocol seeds:** `41000`-`41010` (11 seeds). Each seed is reused across the three candidate length caps for one target length. This is a paired protocol comparison. Because seed and target length are coupled, the 11 seeds are not 11 independent generation replicates.
- **B1 Phase B length-condition seeds:** `42000`-`42088` (89 seeds), one for each distinct TRAIN length. These preserve deterministic empirical-length generation. Seed is confounded with length and must not be used as an independent replicate or as a basis for between-seed uncertainty.
- **Limited 1,000-sequence B1/D1 comparison:** `43000` samples the 1,000 target lengths and does not directly generate RNA. Generation uses one seed per batch/chunk, starting at `44000`, with batches of at most 16. D1 reuses the exact B1 target-length allocation and generation-seed schedule. The final number of chunk seeds and the complete seed-to-condition/length/attempt mapping are frozen after deterministic batching and before condition results are inspected. Shared chunk IDs may support paired B1-D1 summaries, but chunks are not biological or training replicates.
- **B2 null generation:** one NumPy sequence-generation seed, `42`. B2 therefore supplies no between-generation-seed variability; its single-seed limitation is reported descriptively.
- **B0 existing pool:** historical seeds `4201`-`4210`. B0 is not regenerated and its seeds provide provenance only.

Before the limited-pool batch schedule is constructed, M4 therefore has 101 fixed new sequence-generation seeds: 11 Phase A seeds, 89 Phase B seeds and one B2 seed. The length-sampling seed `43000` is separate. Neither the count of 101 nor the later number of `44000+` chunk seeds is a count of independent model or biological replicates. Training, length-sampling, length-condition, generation-chunk and downstream analysis seeds remain separate manifest fields even where numerical values happen to coincide.

Keep B1/B2/D1 generation effort reasonably symmetric. The primary D1 generation budget is 30,000 raw attempts in total across the retained D1 training-seed checkpoints, allocated as evenly as practicable; it is not 30,000 attempts per checkpoint. A design such as 90,000 D1 outputs versus 30,000 for B1 and B2 requires a strong methodological reason approved before results. Where pool sizes differ, use a fixed equal-size primary analysis sample across B1/B2/D1 and report full-pool attempted/parsed/valid/unique accounting separately. Preserve all seed-role provenance and never choose favourable training seeds, generation seeds or chunks. Add no further null condition.

### 4.3 Required readiness before the five-day clock

- Corrected source files and hashes in Section 3 are available and verified.
- M6 is signed and identifies every contingent workstream retained or deferred.
- M9A has frozen checkpoints, feasible D1 seed count, generation settings, cleaning, pool manifests and generator-evaluation code.
- B1/B2/D1 pools contain attempted/parsed/valid/unique accounting and separate training-seed, length-sampling, length-condition and generation-chunk provenance as applicable. Any B0 pool is separate and optional.
- The generator suite, `generator_eval_metric_spec`, loaders, synthetic fixtures and design-aware summaries are implemented and tested without EVAL access.
- Tier 1 deployment/preset, REF workflow, export schema, runtime and recovery are verified on non-EVAL inputs.
- If retained at M6, the small Tier 2 panel rule and direction-known raw-score definition are frozen; no new control-bank engineering is a prerequisite.
- If retained at M6, one NDM-1 target configuration is frozen from independent structural sources before condition results.

If these are not true, delay the evaluation week or reduce contingent scope. Do not spend the core week implementing a new generator suite, generating large pools, building a representation model, searching extensively for target configurations or constructing a new Tier 2 control bank.

### 4.4 Freeze and unlock milestones

| Milestone | Timing | Required decision record |
|---|---|---|
| **M6 — real-data pilot / final evaluation scope lock** | Before evaluation week | Feasible seed count, symmetric pool/sample policy, expected runtimes, retained/deferred workstreams and writing protection |
| **M9A — generator freeze** | Before Day 1 | Checkpoints, pools/manifests, seed policy, cleaning, frozen generator metrics/code/configuration |
| **M9B — AptaRank calibration** | Day 1 | Corrected REF Tier 1 artefact; brief Tier 2 scoring-basis audit only if Tier 2 remains in scope |
| **M9C — end-to-end freeze** | End Day 1 | Final M6-consistent scope; equations/directions/weights; `generator_eval_metric_spec`; Tier 1 controls/blinding; any contingent panels, runtime caps and shortlist rules; hashes |
| **M10 — final assessment** | Days 2-5 | Explicit EVAL unlock; execute frozen generator and Tier 1 analyses without retuning; run contingent stages only after core security checks |

The unlock record contains timestamps, operator/reviewer, role hashes, M6/M9A/M9B references, deployment and calibration identifiers, code revision, runtime decision and frozen protocol.

## 5. Priority 1A — final generator-level held-out EVAL

### 5.1 Purpose and inputs

This is the highest-priority experiment and cannot be replaced by AptaRank. After M9C and explicit unlock, apply existing frozen generator-evaluation code to unique EVAL cores and frozen B1/B2/D1 pools. B1 versus D1 is primary; B2 is the non-neural null. Use TRAIN only for predeclared copying/novelty diagnostics; REF is not generator-evaluation data.

B0 is external/descriptive and only appears if already available and its length regime permits a meaningful length-aware comparison. B0 is not required for completion and is not pooled with the controlled B1/D1 analysis.

The generator analysis uses its predeclared equal-size primary samples, not the AptaRank N=200 sample or a Tier 1-selected shortlist. Preserve pool/sample policy, metric-specific denominators, length allocation, cleaning, checkpoint hashes and the distinct training, length-sampling, length-condition and generation-chunk seed roles. Do not regenerate pools, choose seeds or alter representations after unlock.

### 5.2 Frozen outputs

| Output | Required content |
|---|---|
| Output accounting | Attempted / parsed / valid A/C/G/U / unique valid outputs; duplicate/invalid counts and metric-specific denominators; no early discarding of failed attempts |
| TRAIN overlap and novelty | Exact TRAIN overlap and already implemented nearest-TRAIN similarity/novelty diagnostics, such as normalized edit distance and maximum identity |
| Sequence distributions | Length, nucleotide fractions, GC and any other already implemented core descriptors such as mono-/dinucleotide frequencies |
| Structure/thermodynamics | Normalized MFE, paired fraction and other predeclared frozen descriptors using pinned settings; more negative MFE is not inherently better or evidence of binding |
| Diversity/mode collapse | Existing cluster, singleton, largest-cluster, Shannon/effective-cluster and structural-diversity summaries only where already implemented |
| Seed/design-level reporting | Per-D1-training-seed values where more than one training run exists; matched B1-D1 generation-chunk effects where applicable; length-stratified summaries; B2 as single-seed context; explicit limits on uncertainty |

Include one frozen-representation distance to EVAL only if already implemented, stable and frozen by M6/M9C. Otherwise record its pre-unlock deferral; it is non-blocking. Build no new representation model or metric during evaluation week.

### 5.3 `generator_eval_metric_spec`

Before unlock, export and hash one row per implemented metric with:

- exact metric/output name;
- data, denominator, filters, reference and seed/length handling;
- exact statistic/distance, units/range, aggregation and parameters;
- predeclared closeness/improvement direction or `not applicable`;
- role: `closeness`, `guardrail` or `outcome`; and
- code/configuration revision and pinned settings.

Length, composition, normalized MFE, paired fraction and any representation metric are closeness measures only where the frozen implementation defines an EVAL distance. TRAIN overlap/novelty, validity and diversity are guardrails/outcomes, not extra votes for closeness.

Report each metric separately. Do not create an aggregate generator-quality score. If directional closeness results disagree, report the result as mixed. Report validity, novelty and diversity separately, including trade-offs and negative findings.

### 5.4 Statistical framing

Use the frozen design-aware procedure, preserving independent D1 training-seed blocks and the actual matched B1/D1 `44000+` generation-chunk design where applicable. Condition on or stratify by target length for length-sensitive metrics. Do not use B1 Phase A seeds, B1 Phase B length-condition seeds, B2's single seed, batch count or individual generated sequences as independent training or biological replicates. Phase A cap comparisons remain paired within target length; Phase B seed summaries remain descriptive because seed and length are coupled; B2 has no between-generation-seed uncertainty. Matched chunk summaries estimate within-schedule B1-D1 differences but do not measure training-run variability.

Do not treat tens of thousands of generated sequences as independent biological replicates or rely on tiny raw-N p-values. Report training-seed values/ranges where available, matched-chunk summaries where applicable and all interval limitations. With one D1 training seed, state explicitly that training-run variability is not represented; with two, report the observed range and limited precision rather than implying a well-estimated training-seed distribution. No new hierarchical model is required.

The permitted conclusion is about generated-distribution movement toward held-out aptamer-domain characteristics. It is not evidence of binding, affinity, selectivity, biological function or carbapenemase-specific generation.

## 6. Priority 1B — REF-calibrated AptaRank Tier 1 held-out EVAL

### 6.1 Final REF calibration

Build the empirical calibration from **113 unique corrected REF cores** (**65 short / 48 long**) after M9A and before EVAL access. Record technical rejections and actual denominators. Retain the five established components and directions:

1. normalized MFE: lower favoured;
2. ensemble defect: lower favoured;
3. mean positional entropy: lower favoured;
4. stem fraction: two-sided centrality around the REF median; and
5. GC fraction: two-sided centrality around the REF median.

Retain the established weighted mean, with equal default weights unless an already approved vector governs, plus frozen empirical-CDF/tie definitions and candidate-specific dinucleotide-shuffle criterion. Record equations, weights, directions, mid-rank handling, deployed preset, seed and calibration artefact hash. Calibration is not REF performance testing.

### 6.2 Blinded EVAL input

After M9C/unlock, take all **154 unique EVAL cores** and generate one exact-length uniform control for each:

```text
alphabet         = A, C, G, U
probabilities    = 0.25 each
length           = exact paired EVAL-core length
master seed      = 42; record implementation and per-core derivation
duplicate/match  = deterministically resample duplicate controls or known-core matches
```

Combine the 154 real cores and 154 controls into a randomized, opaque-ID **308-row file before technical rejection**. Keep group, pair, core, cluster and length in a private key. Use one frozen REF/preset/seed. Capacity-driven chunks use identical settings and a pre-result allocation. Account for every row and never count missing output as a shuffle failure or zero score.

Uniform RNA is a synthetic floor/sanity comparator, not an experimental non-binder. The candidate-specific dinucleotide-preserving shuffle test provides the stronger composition-preserving null.

### 6.3 Required Tier 1 results

- actual cores, **79 corrected EVAL clusters** before rejection, controls, complete pairs, exclusions and failures;
- full Tier 1 score distributions, group median/IQR and mean;
- paired real-minus-control effects, with median primary and mean descriptive;
- descriptive AUROC against this synthetic null, not general aptamer-classification performance;
- real/control shuffle-pass n/N and proportions under the frozen p <= 0.05 rule, plus the paired difference;
- cluster-bootstrap 95% CIs for paired effects, AUROC and pass-rate summaries/difference;
- one secondary paired non-parametric test: Wilcoxon signed-rank with frozen tie/zero handling, or the predeclared sign-test fallback when signed-rank is not estimable/appropriate; and
- one compact five-component table/plot without five new headline tests.

Resample the frozen EVAL clusters with replacement, retaining all member cores and paired controls. The default is 10,000 replicates, seed 42 and percentile 95% intervals. Report the number of clusters represented after exclusions. Use complete pairs for paired effects and AUROC, with excluded-pair counts. Always report weak separation or low shuffle-pass rates if observed. Do not add more nulls or extensive subgroup analyses.

## 7. Runtime, preflight and core reproducibility

On synthetic RNA and non-EVAL targets, confirm candidate/reference columns, silent transformations, invalid/duplicate handling, opaque-ID recovery, deployed preset, reference artefact, export schema, score directions, runtime, capacity, download/recovery and immutable run IDs. The prior rigorous preset was 200 sampled structures and 99 dinucleotide-preserving shuffles; verify the deployed values rather than assuming them.

Freeze `runtime_decision.json` with preparation, measured computation, downloads/checks and repair margin for the generator and Tier 1 core. Reserve approximately 25% overhead unless profiling supports another documented margin. Overnight jobs are allowed only after stable completion and export recovery are demonstrated.

Minimum core archive:

```text
evaluation/
  00_contract/                 # M6, M9A-M9C, unlock, runtime decisions
  01_inputs_restricted/        # uploads and private opaque-ID keys
  02_calibration/              # corrected REF Tier 1 artefact
  04_ui_exports_raw/<run_id>/  # immutable exports, artefacts and logs
  05_normalized_private/       # canonical tables
  06_analysis_code/            # version-controlled code, fixtures, environment
  07_results_shareable/        # safe aggregates, figures, result manifest
  08_thesis/                   # thesis-ready findings and private shortlists
```

Hash every derived input/output and record parent release, code/configuration revision and environment. Keep sequence-bearing restricted data local and out of public repositories. Use AI assistance only against synthetic fixtures or non-sensitive schemas; apply reviewed code locally to restricted inputs.

## 8. Priority 2 — contingent limited Tier 2 EVAL

Run Tier 2 only after final generator EVAL and Tier 1 outputs, checks and thesis-ready interpretations are secure, and only if M6 retained it. The panel is deliberately small, bounded and illustrative. No four-target/K=3 minimum applies; a smaller honest panel is acceptable. Do not perform a global structural-eligibility census.

### 8.1 Brief scoring-basis audit

Spend only a brief, M6-bounded period confirming the deployed raw geometric-score equation, direction and same-mode comparability, plus any recoverable server-side control-bank identifier/provenance. The default defensible analysis is the **direction-known raw same-mode geometric score**.

Use percentile/band analysis only if control-bank provenance, direction, identity and independence are verified quickly and cleanly. If provenance is unclear, proceed with raw score and omit percentiles, bands, >95 thresholds and joint-region claims. A new REF-derived Tier 2 bank is future/optional work and may be used only if it is already or trivially available after the core; do not engineer it during the evaluation week. Freeze `tier2_scoring_basis_manifest.json`; never switch basis after scores.

### 8.2 Score-blind bounded panel

Before scoring, freeze a small panel that fits the M6 runtime budget. Selection uses EVAL metadata and independent structural/source evidence only, never Tier 1 or Tier 2 scores. Each included cognate relation requires E2/E3/E4 support, an unambiguous canonical protein target, a reproducible experimental structure/chain/domain, an independently justified mode/site, and at least one permissible same-mode mismatched target.

Use a stable metadata order and review only as many targets as fit the frozen time box. Keep at most one configuration per canonical target. Do not search across structures, sites, modes or bandwidths for the best score. Record selected, screened-ineligible, unresolved, runtime-capped, not-screened and technical-failure statuses. Unscreened targets are not scientific exclusions and the bounded screen does not estimate global structural eligibility.

Known additional cognates and cross-binding conflicts must be removed from mismatch lists. Mismatches are prespecified comparison targets, not experimental non-binders. Pool neither surface and pocket raw scores nor other incomparable modes.

### 8.3 Compact metrics and interpretation

For cognate relation i and K_i valid prespecified mismatches, orient score s so larger means more compatible:

```text
concordance_i = (# cognate > mismatch + 0.5 x # exact ties) / K_i
rank_i        = average rank of cognate among selected scores
delta_i       = cognate score - median mismatch score
```

Report per-relation concordance, rank, K_i and delta; aggregate median/mean concordance, unique top-1 n/N, tied-first count and median delta; target concentration; explicit failures and denominators; and cluster-aware intervals only where meaningful. With too few clusters, label intervals unstable or not estimable.

Cross-tier Spearman is optional and exists only if Tier 2 ran. It is a redundancy analysis, not binding evidence. The joint region `Tier 1 shuffle pass AND Tier 2 percentile > 95` may be reported only with trustworthy percentiles. Otherwise omit it; do not invent a raw-score threshold. If Tier 2 is omitted, omit the cross-tier result rather than treating it as a missing core experiment.

## 9. Priority 2/3 — contingent RNAGenesis-to-AptaRank analysis

### 9.1 Conditions and fixed sampling

| ID | Condition | Role |
|---|---|---|
| B1 | Generic released RNAGenesis | Primary neural baseline |
| B2 | TRAIN-matched empirical i.i.d. RNA | Already planned non-neural null |
| D1 | Curated-aptamer diffusion-adapted RNAGenesis | Adapted condition |
| B0 | Released aptamer-adapted RNAGenesis | Optional external comparator; different 37-nt maximum/output regime |

B1 versus D1 is primary; B2 is supporting. Add no null. If generated-condition Tier 1 was retained at M6 and core work is secure, use a blinded combined B1/B2/D1 upload. Default N is 200 valid unique candidates per condition; score-blind runtime fallbacks are 150, then 100. Keep equal N across B1/B2/D1, balance D1 across available training seeds as practicable, preserve all generation-chunk and length provenance, and use deterministic sampling without replacement from frozen pools. Balance refers to independent D1 training-seed membership, not to Phase A/Phase B seed IDs; retain matched B1/D1 chunk representation where practicable without overriding equal condition N or score-blind sampling.

Report full Tier 1 distributions, N/exclusions, median/IQR, shuffle-pass n/N, B1-D1 effects, B2 context and design-appropriate training-seed/matched-chunk summaries and limitations. This is complementary computational prioritisation evidence, not independent biological confirmation or a substitute for held-out generator EVAL.

B0 Tier 1 runs only after generator EVAL and Tier 1 EVAL are secure and time remains. Run and report it separately because of the different length regime. B0 Tier 2 is not required. If deferred, state that it was omitted for scope/time and that B1 versus D1 is the primary controlled comparison.

### 9.2 Contingent NDM-1 application

Run only if retained at M6 and higher-priority work is secure. Use the frozen equal top-L Tier-1-ranked candidate sets from B1/B2/D1:

```text
default L        = 30 per condition
runtime fallback = 20, then 10, frozen before condition results
tie break        = ascending stable opaque candidate ID
shuffle filter   = none; shuffle pass remains an annotation
```

Where possible, combine B1/B2/D1 into one blinded NDM-1 target-batched job. Deduplicate identical sequences only while retaining every condition membership in the private key. B1 versus D1 is primary; B2 is supporting. Use one independently frozen NDM-1 structure/chain/mode/site and the same score basis as any Tier 2 evaluation. If the configuration is invalid or unavailable, report that limitation and do not substitute another target or launch a new configuration search.

Report selected/scored/failed N, score distributions, D1 training-seed representation, B1-D1 effects and B2 context. Use percentile bands or joint regions only when Section 8.1 permits them; otherwise report raw same-mode scores. Failures remain in the denominators and are not replaced by lower-ranked candidates. Label any D1 output **computationally prioritised candidates for future experimental validation**, not predicted binders.

### 9.3 Optional related-carbapenemase cross-target stress test

Only after all core, contingent NDM-1 work and writing are secure, and only when valid frozen target configurations already exist, the **same frozen NDM-1 candidate set** may be scored against KPC-2 and OXA-48. Do not reselect candidates or undertake new configuration searches. Treat KPC-2 and OXA-48 as related mismatched targets, not negative targets or non-binders. Report whether NDM-1 tends to receive the higher same-mode geometric score and interpret the result only as a geometric related-target stress test, never binding selectivity.

## 10. Priority 3 — optional NDM1-REF published-reference comparison

### 10.1 Purpose, priority and approved 10-record view

**NDM1-REF — independent published NDM-1 reference comparison** is descriptive, is the first item to defer, and is never a thesis-completion blocker. If run, compare the frozen top-50 Tier-1-ranked D1 candidates with a versioned 10-row selection manifest/view of records already present in `evaluation_references.csv`. Do not add duplicate scientific rows. A physical derived file, if convenient, must be a deterministic export of those records and retain source row identity, stable source ID, molecule type, source role and provenance. The view may add an `analysis_role` while preserving any differently worded source-role field.

Use exactly this panel:

| Analysis role | Molecule | Reference(s) | Length(s) | Interpretation |
|---|---|---|---|---|
| Primary positive | ssDNA | CN102 SEQ ID NO:1, APNV, NDM1-H14.2_43 | 88, 35, 80 nt | Experimentally supported NDM-1 binders |
| Primary positive | RNA | D909 | 48 nt | Strongest D9 binding signal; limited inhibition evidence |
| Secondary positive | RNA | D918, D920 | 49, 50 nt | Positive binding, weaker than D909 |
| Weak-binding context | RNA | D907, D913, D914 | 34, 50, 50 nt | Weak signals; contextual comparators, not true non-binders |
| Negative comparator | RNA | D902 | 50 nt | No detectable binding in the reported assay |

The 10-row selection manifest uses these stable source IDs and adds no scientific records:

| Stable source ID | Display reference | Molecule | Analysis role |
|---|---|---|---|
| `cn102965377b_seq1` | CN102 SEQ ID NO:1 | ssDNA | Primary positive |
| `cn108949766b_apnv` | APNV | ssDNA | Primary positive; cross-binding |
| `sabrowski2022_ndm1_h14_2_43` | NDM1-H14.2_43 | ssDNA | Primary positive |
| `von_laer_2013_d909` | D909 | RNA | Primary positive |
| `von_laer_2013_d918` | D918 | RNA | Secondary positive |
| `von_laer_2013_d920` | D920 | RNA | Secondary positive |
| `von_laer_2013_d907` | D907 | RNA | Weak-binding context |
| `von_laer_2013_d913` | D913 | RNA | Weak-binding context |
| `von_laer_2013_d914` | D914 | RNA | Weak-binding context |
| `von_laer_2013_d902` | D902 | RNA | Negative comparator |

Evidence statements to preserve:

- CN102 SEQ ID NO:1 retains the exact verified published 88-nt listing despite the documented generic-library discrepancy.
- APNV is an NDM-1/VIM-2 cross-binding positive; always state cross-reactivity and never call it NDM-1-selective.
- NDM1-H14.2_43 is a positive NDM-1 binder with published specificity-control context.
- D909 is the primary RNA positive; D918/D920 are secondary positives.
- D907/D913/D914 are weak-binding context and must never be relabelled as non-binders.
- D902 is the single negative comparator.
- No quantitative dissociation constant is reported for the RNA panel. None showed detectable binding below 1 µM NDM-1 in the reported assay. D909 inhibition required a large RNA excess; do not call it high-affinity or a clinically validated inhibitor.

The positive-reference-only pool is **6 sequences**: the 3 ssDNA records plus D909, D918 and D920. The complete panel is **10 sequences**: 6 positives, 3 weak-binding references and 1 negative comparator. Excluded controls are Con1, ConSc, NDM1-H14-01 and NDM1-H14-01-FR. Do not add other NDM-1 rows from the broader resource.

### 10.2 Freeze and access firewall

From the frozen D1 generated-condition Tier 1 sample, select the top 50 valid unique candidates by Tier 1 rank, breaking ties by ascending stable candidate ID. If fewer than 50 exist, use all and report N. Do not use Tier 2, shuffle pass, reference similarity, target score or annotation availability to choose, replace or reorder candidates. No extra AptaRank run is required.

Freeze/hash membership and ordering before the evaluation-analysis workflow accesses the 10 reference sequences. Record the shortlist-freeze and reference-opening timestamps, approved-view hash, source `evaluation_references.csv` hash, code/configuration revision and all output hashes. Authorised curation may access the references earlier only for provenance, view construction and leakage audit; that access does not authorise modelling, ranking or evaluation use.

### 10.3 Local comparison method and scale

Run locally: **50 D1 RNA candidates x 10 references = 500 pairwise comparisons**, or N x 10 when N < 50.

Preserve original molecule identity and sequences. D902/D907/D909/D913/D914/D918/D920 remain RNA even if U/T is normalized for comparison. Reuse the previously approved repository sequence-comparison identity implementation and the same matching normalization: U-to-T for matching only and no reverse-complement matching. Freeze its code revision, alignment method, numerator/denominator, gap/length handling, score range and configuration. Do not substitute an assumed identity definition. If the implementation cannot be recovered quickly, defer this optional stage.

No formal hypothesis test is required. Identity >=0.90 is a descriptive threshold inherited from the leakage audit, not a biological cutoff. Do not trim constructs or infer binding cores to raise similarity.

### 10.4 Compact outputs

- N x 10 pairwise identity table and matrix;
- per candidate: best match across all 10, best match to the 7 RNA references, best match to the 3 ssDNA references, and nearest reference ID/analysis role/molecule, retaining ties;
- per reference: maximum candidate identity, median/IQR candidate identity and top five D1 candidate matches;
- overall best-reference identity distribution and RNA-reference/ssDNA-reference stratified distributions;
- exact-match and >=0.90 identity counts overall and by molecule type, at pair and distinct-candidate grain;
- candidate/reference lengths for top pairs; and
- GC summaries or a heatmap only if trivial.

RNA-to-RNA similarity remains descriptive and does not establish binding, affinity, fold equivalence or “rediscovery.” ssDNA comparisons require the additional cross-chemistry caveat. Low sequence similarity does not argue against NDM-1 binding. This small heterogeneous panel is context, not a model-performance benchmark. If deferred, state simply that NDM1-REF was omitted under the predeclared scope-control rule.

## 11. Five-day critical path

| Timing | Protected work | Decision/output |
|---|---|---|
| **Before week — M6** | Real-data pilot; verify generator implementation/runtime; freeze feasible seed count and symmetric pool/sample strategy; estimate Tier 1 runtime; retain or defer Tier 2, generated-condition Tier 1, NDM-1 application, B0 and NDM1-REF | Signed `m6_evaluation_scope_lock`; EVAL remains sealed |
| **Day 1** | Final contracts and synthetic preflight; validate/freeze generator suite and metric specification; corrected REF Tier 1 calibration; final scope/scoring freeze | M9B/M9C records, calibration artefact, tested loaders and clean unlock-ready contract. Do not spend half a day engineering a Tier 2 bank |
| **Day 2** | Explicit EVAL unlock; launch frozen generator-vs-EVAL analysis; run blinded core EVAL Tier 1 | Immutable inputs/exports, generator run accounting and Tier 1 output accounting |
| **Day 3** | Complete generator and Tier 1 analyses; produce thesis-ready tables, figures, limitations and interpretation | Priority 1 completion check. If not secure, defer Tier 2 and all later work; if secure and M6 retained it, run the small raw-score Tier 2 panel |
| **Day 4** | If core is secure: generated-condition B1/B2/D1 Tier 1 and/or NDM-1 preparation under the M6 decision; B0 only if time remains | Contingent results and frozen equal top-L sets; otherwise protected writing/reproducibility time |
| **Day 5** | If higher-priority work and writing are secure: NDM-1 application; optional NDM1-REF after everything above; related-target stress test only after all other work or after the core week | Final archive and thesis-ready text; explicit deferrals where applicable |

Protect writing time throughout, especially Days 3 and 5. The next contingent stage starts only after core outputs reconcile cleanly and their interpretation is drafted, not merely after a job finishes. Unexpected slowness triggers the declared cut order, never score-guided thinning or reconfiguration.

## 12. The only thesis-evaluation completion blockers

1. **Frozen role/hash/model/evaluation contract and clean EVAL unlock**, including M6, M9A-M9C and immutable source/derived hashes.
2. **Final generator-level B1/B2/D1-versus-EVAL evaluation**, with output accounting, validity, TRAIN overlap/novelty, sequence/structure distributions, diversity, predeclared metric directions, design-aware interpretation and honest reduced-training-seed limitations.
3. **Final REF-calibrated Tier 1 EVAL**, using 154 unique EVAL cores, 154 exact-length controls, the 308-row blinded input, full distributions, paired effects, descriptive AUROC, shuffle-pass rates, cluster-aware CIs and one secondary paired test.
4. **Reproducible code/manifests/outputs plus thesis-ready analysis and interpretation** of those core results.

Everything else is contingent: limited illustrative Tier 2, generated-condition Tier 1, NDM-1 target application, B0 Tier 1, NDM1-REF and the optional related-target stress test.

The supervisor cut-first order is:

1. NDM1-REF;
2. B0 Tier 1; and
3. further non-core/illustrative work as required.

Technical failure or unavailable evidence is reported as a limitation or uncompleted contingent stage, not relabelled a null result. Neither a favourable p-value nor a candidate in a favourable score band is required for thesis completion.

## 13. Analysis quality, run ledger and provenance

### 13.1 Canonical checks

Retain condition/pool/checkpoint identity, attempted/parsed/valid/unique accounting, separate training/length-sampling/length-condition/generation-chunk seed fields, metric denominators, EVAL/reference hashes and frozen code/configuration for generator results. Check every result against its `generator_eval_metric_spec` row.

Minimum Tier 1 fields are opaque ID/run, local pair/group/core/cluster/length, accepted/rejected and reason, five raw/component scores, Tier 1 score, shuffle count/exceedance/p-value/pass, preset/seed, reference artefact hash and deployment.

For any contingent Tier 2 run, retain opaque ID/run, core/cluster/cognate relation, target/configuration/mode, raw score, optional percentile/band, score-basis status, bank evidence, target/reference hashes, accepted/failed status and reason.

Before unblinding, synthetic fixtures must verify shuffled-row joins, duplicates, missing/failed rows, paired controls, multi-core clusters, effect/AUROC direction, zero/all shuffle-pass cases, seeded cluster resampling, D1-training-seed-balanced sampling, matched B1/D1 chunk handling, runtime-cap determinism and conditional absence of percentiles. For Tier 2 only if run, also verify variable-K concordance/rank/ties and mode separation. Validate schemas/ranges/keys automatically, spot-check at least five representative rows against UI artefacts, and execute the final analysis cleanly from immutable inputs.

For NDM1-REF if run, verify the exact 10 source IDs, analysis roles, molecule types, lengths, N x 10 accounting, shortlist order/hash, original-sequence preservation and exclusion of the four named controls.

### 13.2 UI run ledger

```text
run ID, stage/purpose, operator, start/end timestamps,
deployment/version/code revision, candidate filename/hash/count,
REF artefact hash, scoring-basis manifest hash where applicable,
target configuration/prepared-structure hash where applicable,
preset/effective structures/shuffles/random seed,
expected/exported/failed rows, raw export/run artefact hashes,
warnings, rerun parent/reason
```

Never overwrite exports. A rerun receives a new ID and retains the failed/original lineage. Reconcile every input and every planned score cell.

### 13.3 Statistics and provenance

Use effect sizes and 95% intervals before p-values. Do not treat generated sequences, target-score cells, length-condition seeds or generation chunks as independent model-training or biological replicates. Freeze analysis seeds and explicit denominators; report undefined or unstable intervals honestly. Use D1 training seeds for training-run variation, matched B1/D1 chunks only for paired within-schedule summaries, and EVAL clusters where the frozen reference-resampling procedure requires them.

Every final number maps to normalized-input hashes, source run/raw hashes or local-analysis hashes, inclusion filter, statistic/CI method, code/environment revision and output hash. Preserve role, checkpoint, pool/sample, calibration, target, scoring-basis, shortlist and NDM1-REF view/freeze/access/result manifests as applicable.

Three D1 training seeds are preferred but not mandatory. Training-seed count is frozen before results; reduced-training-seed limitations are explicit. The M4 generation schedule remains fixed and its seed counts are not presented as replicate counts. Primary B1/B2/D1 samples are equal-size where possible, D1's 30,000-attempt budget is aggregate across its retained training checkpoints, and asymmetric full pools are separately accounted for with pre-result justification.

## 14. Thesis write-up

### 14.1 Guaranteed Results subsections

1. **Final generator-level held-out evaluation.** Report B1-D1 comparisons with EVAL, B2 context, output accounting, TRAIN overlap/novelty, sequence and structure distributions, diversity, design-appropriate training-seed/matched-chunk results and uncertainty limitations. Report closeness metrics individually, mixed results as mixed, and validity/novelty/diversity as separate guardrails/outcomes. Include B0 only as optional external length-aware context if executed.
2. **AptaRank Tier 1 held-out evaluation.** Report the corrected REF calibration, blinded EVAL/control flow, full distributions, paired effect, descriptive AUROC, shuffle-pass rates, cluster-aware CIs, secondary paired test and compact component summary.

### 14.2 Conditional subsections only when executed

- limited illustrative Tier 2 EVAL and any contingent cross-tier redundancy result;
- downstream generated-condition B1/B2/D1 AptaRank Tier 1;
- NDM-1 application and computationally prioritised D1 candidates;
- B0 Tier 1 as a separate external comparator; and
- NDM1-REF published-reference context.

Do not create placeholders that imply omitted contingent work is a missing core result. State predeclared deferrals briefly. Do not create a Tier 1 + Tier 2 composite or aggregate generator-quality score.

### 14.3 Required interpretation and limitations

The curated corpus is a methodological/design contribution through rigorous construction, role separation, target balancing, similarity-aware leakage control, provenance and auditability. Formal corpus ablation is future work and is not required for this MRes evaluation.

If Tier 2 is weak or null, state that the limited panel does not establish consistent cognate-target ranking. If supportive, limit the claim to direction-known geometric ranking in the selected cases. If Tier 1 separation or shuffle-pass rates are low, report that directly. Generator claims extend only to predeclared held-out distributional metrics; downstream AptaRank changes are computational prioritisation outcomes. None establishes biological binding, affinity, selectivity or clinical function.

Limitations must cover, as applicable: few training seeds, generation-pool asymmetry, B0's different length regime, synthetic controls, incomplete target-family metadata, structural/site uncertainty, small/configurability-selected Tier 2 panels, control-bank provenance, missing technical outputs, canonical-sequence chemistry representation, and absence of wet-lab validation.

For NDM1-REF, state that the 10 references are small and heterogeneous; RNA similarity is descriptive; ssDNA adds cross-chemistry and construct-length caveats; APNV cross-reacts; D902 is the single negative comparator; and D907/D913/D914 are weak-binding context, not negatives.

## 15. Source basis and finality

This v2.7 FINAL revision uses the supervisor-scoped v2.6 plan as its authoritative base. Current corpus authority remains corrected S7D `corpus_report.md` (closure state 2026-09-25) plus `rna_aptamer_corpus_curation_plan.md` v1.6, with closure `10aac629bb0ef0337107c3d628b23e1897962af9` and documentation handoff `05616cf82c3c7c1adbe87f631590f456c44c946a`. Historical values in earlier plans are not execution authority.

The 10 NDM-1 reference records are selected from the frozen **35-row** `evaluation_references.csv` identified by SHA-256 `b6ba6b2cde4a18c04130ecdc457626c5e60b8b90d3ad5b9bae6cb1bfd1f77dad`. The approved view replaces the obsolete separate three-ssDNA scientific dataset concept; it does not duplicate or alter the source rows. Dedicated provenance about the three ssDNA records, including the accepted CN102 88-nt listing and APNV cross-reactivity, remains applicable. The RNA panel adds D902, D907, D909, D913, D914, D918 and D920 under the analysis roles and evidence cautions in Section 10.

The established five-component Tier 1 score, candidate-specific dinucleotide shuffle check, REF-to-EVAL separation, similarity-cluster dependence, immutable exports, leakage firewall and Tier 1 ranking with optional Tier 2 annotation are preserved. The companion FINAL v2.4 camera-ready workflow continues to govern its separate one-day publication analysis.

**v2.6 finality note.** This revision makes only two approved clarifications to v2.5: it orders generated-condition Tier 1 before the dependent NDM-1 downstream application in Priority 2, and it records an explicit M6 feasibility decision for the 2 October modelling/evaluation target so scope is reduced before EVAL access rather than by compressing thesis writing.

**v2.7 finality note.** This revision leaves the M4 implementation unchanged and aligns evaluation with its fixed seed behaviour. It separates D1 training seeds from protocol, length-sampling, length-condition, generation-chunk, B2 and historical B0 seeds; confines seed-aware inference to genuine training replication and actual matched B1/D1 chunks; records that the fixed M4 seed counts are not replicate counts; and makes the symmetric 30,000-attempt D1 budget aggregate across retained training checkpoints.

This document is the FINAL governing MRes evaluation execution plan. It defines what must be completed, what may be added, and what is cut first. Neither corpus closure nor this documentation revision asserts that fine-tuning, deployment verification, calibration or evaluation runs have been completed.
