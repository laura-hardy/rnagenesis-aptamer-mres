# M4 validation protocol

**APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION**

This document must not be consumed by an executable workflow. The Stage 1 protocol package is approved for M4 implementation only. It does not create draw tensors, generate sequences, train a model, select a checkpoint, or open an evidence directory. Formal M4 is COMPLETE / GO for M5 planning only. This document does not authorise M5 execution or D1 training.

Human approval:

- approving person: Laura Hardy
- approval date: 29 September 2026
- approval-recorded timestamp: `2026-09-29T14:57:40+10:00`
- approval source: formal human approval in the M4 review chat
- approval scope: Stage 1 protocol package for M4 implementation only
- explicitly not approved: scientific execution, biological-data runs, B2 generation, validation-artifact creation, model loading, GPU use, B1 generation, D1 training, staging, committing, or pushing
- `consumable_by_executable_workflow: false`
- previous status: `DRAFT_PENDING_HUMAN_APPROVAL`

Machine-readable companions, approved for M4 implementation and not for execution:

- `config/modelling/condition_registry.yaml`
- `config/modelling/validation_metrics_v1.yaml`
- `config/experiments/B1_generic_generation.yaml`
- `config/experiments/B2_empirical_null.yaml`
- `config/experiments/D1_diffusion_pilot.yaml`
- `config/experiments/generator_evaluation.yaml`
- `docs/fine_tuning/run_manifest_schema.md`

Written against MRes `b690f44a025a3790f1af1865856fc480dbec1079`. The implementation plan SHA-256 is `bcd5f5d4a9d6abd45757ed430fe587943abccf7fc3189c8063b87c1199769e2c`. The frozen contract SHA-256 is `396c83c3dbf9afc656ad5c60ec05c94fce3c5a684990c3cc1cebfb2411ccd5ff`.

## 1. What this approval fixes and what it leaves open

The approved Stage 1 design fixes the development metric, the checkpoint-selection rule, and the generated-sample guardrail structure. Requested-length exact-hit rates remain required diagnostic reports. The historical provisional values 0.90 and 0.50 are not execution-success requirements. This approval is for implementation only.

On 1 October 2026 Laura Hardy superseded the discussed Approach A fixed-full-table R=32 design before implementation, plan materialization, biological-data access, authorization, or execution. No Approach A schedule, runner, evidence, output, or GPU run exists. The active M4 design is the restored Stage 1 diagnostic contract. Phase A and Phase B evidence remains accepted and unchanged. The selected cap remains `max_seq_len = requested_biological_length + 1`. Early EOS and length mismatch remain observed generator behaviours. They do not trigger rejection, replacement, resampling, or diagnostic-run failure. The design does not declare an exact-length accepted pool or a final M8 production protocol. At that course change, M4 was not complete.

The same day, the CPU development-pool schedule at `/home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1` and the CPU VALIDATION draw artifacts at `/home/laura/rnagenesis-mres-runs/m4_validation_draw_artifacts_d2b2041520d1` were accepted. The schedule hash is `0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0`. The length-vector hash is `7e6cb523a85116fc38788c336ef50c26e0eccc343712aaea89956a73c485bd3c`. The schedule keeps all 1,000 raw attempts, 112 invocations, NumPy 1.22.0, sampling seed 43000, and invocation seeds `44000 + invocation_index`. It does not reject, replace, resample, pad, trim, drop, or deduplicate. The VALIDATION role has 95 sequences, 4 draws, and seed 1. Clustering and frozen-representation metrics stay deferred. B0, B2, Phase A, and Phase B evidence is unchanged. At that CPU-artifact acceptance, B1 success, checkpoint eligibility, M4 completion, M5, D1 training, REF access, and EVAL access remained unclaimed.

On 2 October 2026 the B1 development-pool evidence at `/home/laura/rnagenesis-mres-runs/m4_b1_development_pool_d2b2041520d1_gpu1_attempt1` was accepted for its diagnostic M4 role. The authorisation `m4_b1_development_pool_d2b2041520d1_gpu1_attempt1` is inactive, consumed, successful, and `consumed_complete`. Its physical GPU 1 scope is preserved: UUID `GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, PCI `00000000:61:00.0`, `CUDA_VISIBLE_DEVICES=1`, `CUDA_DEVICE_ORDER=PCI_BUS_ID`, and logical `cuda:0`. Recording that consumption does not claim that access to GPU 1 has been revoked. `authorization_parent_commit` and `executing_implementation_commit` remain `4de4246aa4a97eadaf30caf449e3046378832366`. The runner computed `authorization_commit` `9c0624e9384e19930251355a6b1d61b2d4fdb153` from live HEAD. RNAGenesis remains `mres-d1-diffusion-finetune` at `e3b855bbf4d1af376f43747643fa30afd662828c`. The CPU artifacts materialised at `d2b2041520d176ebd10a1553cf1fec65ad447ac5` are not rewritten.

Independent revalidation, without rewriting the evidence, reconciled 112 invocation files, 1,000 raw records, and 1,000 audited records: 1,000 parsed and valid outputs, zero invalid outputs, 961 exact-length hits, exact-hit rate 0.961, 39 early-EOS length shortfalls, zero length excesses, 1,000 unique outputs, zero duplicates, largest duplicate multiplicity 1, and largest duplicate share 0.001. The pool is a diagnostic generation sample reusable for the later paired D1 workflow. It is not an independent-biological-replicate set or an exact-length accepted production pool. `exact_length_accepted_pool_declared`, `final_production_mapping_declared`, and `final_m8_production_protocol_declared` stay false. B0, B2, Phase A, and Phase B evidence hashes are unchanged. Clustering-dependent and frozen-representation metrics stay deferred beyond M4. The fixed VALIDATION ordering, stored timestep and noise artifacts, checkpoint-selection rule, core sample guardrails, and D1 pilot fields stay in force. Microbatch size, gradient accumulation, numerical precision, and EMA stay deferred to M5.

Formal M4 is **COMPLETE / GO**. The GO authorises progression to M5 planning only. It does not authorise M5 execution or D1 training. REF and EVAL remain closed.

This approval does not:

- declare an exact-length accepted pool or a final M8 production protocol;
- keep clustering-dependent claims or a clustering identity threshold inside M4;
- keep frozen-representation or embedding-aggregation metrics inside M4;
- choose the D1 microbatch, accumulation, numerical precision, or EMA setting;
- authorise B2 sampling, Phase A, Phase B, a second B1 run, M5 execution, or the D1 pilot. The consumed development-pool authorisation is not a new grant.

M5 must pass before the D1 pilot configuration can become executable. Microbatch, accumulation, mixed precision, and EMA stay assigned to M5. Their absence does not, by itself, block final M4 closure. Matters that can remain open after this implementation approval, and that must be resolved before final M4 `COMPLETE / GO`, are listed in section 10.

## 2. Conditions

Four conditions are defined in the condition registry. B1 versus D1 is the primary controlled comparison.

| Manifest label | What it is |
| --- | --- |
| `B0_released_aptamer_rnagenesis` | External released aptamer-adapted comparator. The approved scientific/audit alias `B0_released_aptamer_adapted_RNAGenesis` names this same condition. Not regenerated by default. |
| `B1_generic_released_rnagenesis` | Primary generic model baseline. Released EncDec plus `configs/rnagenesis/diffusion`. |
| `B2_train_matched_empirical_null` | Empirical i.i.d. RNA null. Not random aptamers and not a biological negative. |
| `D1_mres_curated_aptamer_diffusion_adapted` | Unconditional aptamer-domain adaptation from B1. Not target-specific generation. |

B0 must not be treated as the primary causal baseline. Length-sensitive B0 comparisons require normalization, stratification, or a preregistered comparable-length subset.

## 3. Fixed-draw validation

**Status: `ACCEPTED_CPU_ARTIFACT`.** Four fixed VALIDATION draws, seed 1, and deterministic FP32 validation are the accepted CPU artifacts. This protocol document does not create another tensor.

| Item | Proposed value |
| --- | --- |
| Sequence grain | 95 first-occurrence frozen VALIDATION cores |
| Ordering | frozen first-occurrence order |
| VALIDATION CSV SHA-256 | `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd` |
| Ordered-core artifact | future no-sequence artifact; fields are role, zero-based frozen index, SHA-256 of the sequence core, and biological length |
| `validation_sequence_order_sha256` | `eb18fd48e305e86f8000bdc82e9175437d478bd624ea57aef8094497534bda3a`, accepted CPU artifact |
| `validation_order_artifact_sha256` | `df445b617adf5165f3361412bb5c7bc5d2a05b31a98eb6d2f6d17f4b329de248`, accepted CPU artifact |
| Seed | 1 |
| Stochastic draws per sequence | 4 |
| Sequence/draw pairs | 380 |
| Timestep and noise creation | CPU |
| Float32 arithmetic | latent encoding, denoiser forward pass, scheduler arithmetic, noise, and MSE |
| Timestep index dtype | int64 |
| Scheduler | released training `DDIMScheduler`, epsilon prediction, 1000 training timesteps |
| Scheduler config SHA-256 | `6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396` |
| Order | sequence-major, then draw index |
| Persistence | timestep tensor, noise tensor, and a metadata manifest, each independently hashed |
| Reuse | the identical stored timestep and noise tensors at initialization and every checkpoint |
| Regeneration during a training run | prohibited |
| REF or EVAL | prohibited |
| Tensors created in this stage | none |

The 132 VALIDATION identity rows are not the modelling grain. M3 accounted for 37 repeated identity rows on top of the 95 cores.

The fixed-draw protocol requires an ordered-core provenance artifact. That future artifact contains only the role, the zero-based frozen index, the SHA-256 of the sequence core, and the biological length. It must not contain sequence text.

The artifact serialization is approved Stage 1 design and is not created in Stage 2A:

- UTF-8 CSV;
- LF line endings;
- no BOM and no carriage returns;
- exact header `role,zero_based_frozen_index,sequence_core_sha256,biological_length`;
- exactly 95 data rows in frozen first-occurrence order;
- minimal CSV quoting, so a field is quoted only when it contains a comma, a double quote, or a line break;
- a final LF is required;
- `validation_order_artifact_sha256` is the SHA-256 of those exact serialized bytes.

Two ordering hashes are required. Both now name the accepted CPU artifacts, and neither may be replaced by the VALIDATION CSV hash:

1. `validation_sequence_order_sha256` is the SHA-256 of the concatenation of each of the 95 ASCII sequence cores followed by exactly one LF byte, in frozen first-occurrence order.
2. `validation_order_artifact_sha256` is the SHA-256 of the serialized no-sequence order artifact.

The existing VALIDATION CSV hash does not substitute for either ordering hash. The fixed-draw metadata manifest records all three hashes: the VALIDATION CSV hash, the ordered-sequence-bytes hash, and the order-artifact hash.

The proposed draw recipe uses a CPU `torch.Generator` seeded with 1, then, for each core in frozen order and each of the four draws, one integer timestep from `torch.randint(0, 1000)` and one standard-normal noise tensor of shape `[32, 160]`. Stored shapes are timesteps `[95, 4]` int64 and noise `[95, 4, 32, 160]` float32. The global RNG is not used. This matches the walker in tracked RNAGenesis `train_diffusion_mres.py` at `e3b855bbf4d1af376f43747643fa30afd662828c`, except that the tracked default draw count is 1. That code default is not this protocol. This approval does not edit that file and does not create the tensors.

Fixed-draw validation requires the complete frozen `EncDec` in evaluation mode and the denoiser in evaluation mode. Evaluation mode disables dropout. The forward evaluation runs under `torch.no_grad()` and without autocast. Latent encoding, the denoiser forward pass, scheduler arithmetic, noise, and MSE arithmetic are float32. Timesteps are int64. The same stored timestep and noise tensors are used at initialization and at every checkpoint. A comparison must not mix raw and EMA weight variants. The manifest records the evaluated weight variant.

Each pair loss is the mean squared error across all `[32, 160]` latent elements for one sequence/draw pair. The reported metric is the sum of the 380 pair losses divided by exactly 380. An implementation must not average batch means with equal batch weight when batch sizes differ. With four draws on every sequence, the reported metric equals the unweighted mean of the 95 per-sequence means. No weighted composite score is defined.

Draw tensors and metadata are independently hashed. The accepted CPU artifacts were materialised once. A training run must load those bytes and refuse to resample them. This protocol document does not create another tensor.

### Why four draws are proposed

Fixed draws remove checkpoint-to-checkpoint resampling noise. Four timesteps per sequence provide more stable schedule coverage than one while remaining bounded for 95 sequences.

## 4. Checkpoint selection

The primary checkpoint-selection rule is:

> Select the checkpoint with the lowest fixed-draw VALIDATION denoising MSE, provided it passes every approved hard generated-sample guardrail.

Failure of any approved hard threshold makes a checkpoint ineligible even if its validation loss is lowest. Secondary distribution diagnostics interpret checkpoints. They do not select one, and they are not combined into a weighted score.

## 5. Generated-sample guardrails

**Non-length guardrails are `APPROVED_STAGE_1_DESIGN`.** Requested-length exact-hit rates are required diagnostic reports. The historical provisional values 0.90 and 0.50 are not execution-success requirements, and a low exact-hit rate does not invalidate or rerun the B1 diagnostic pool. The 1,000-attempt paired schedule is the restored Stage 1 diagnostic contract. The accepted CPU schedule is immutable. The checked-in B1 configuration authorises one future run of that schedule and does not execute it.

The proposed diagnostic sample is 1,000 raw attempts per evaluated neural checkpoint or condition. Target lengths are sampled with seed 43000. Generation invocations use a separate proposed seed base of 44000. The deterministic execution plan is:

1. sample exactly 1,000 target lengths in attempt-index order from the 669-core empirical length list;
2. retain those original attempt indexes;
3. group attempts by target length in ascending target-length order;
4. within each target length, retain original attempt-index order;
5. divide each group into consecutive chunks of at most 16;
6. invoke generation once per chunk, using its actual chunk size, with `batch_num=1`;
7. assign invocation seeds as `44000 + zero-based invocation index`;
8. never pad, duplicate, or drop an attempt;
9. map every generated record back to its original target-length attempt index;
10. reuse the identical target list, grouping rule, chunk membership, and invocation seeds for paired B1/D1 comparisons where technically applicable.

The manifest must contain the complete invocation table before generation begins. That table is the accepted schedule `0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0`. The length vector is `7e6cb523a85116fc38788c336ef50c26e0eccc343712aaea89956a73c485bd3c`. The checked-in B1 configuration authorises one unconsumed development-pool run on physical GPU 1 (`GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, PCI `00000000:61:00.0`, `CUDA_VISIBLE_DEVICES=1`, `CUDA_DEVICE_ORDER=PCI_BUS_ID`, logical `cuda:0`). `authorization_parent_commit` and `executing_implementation_commit` are both `4de4246aa4a97eadaf30caf449e3046378832366`. The block does not store `authorization_commit`; the runner computes that value from live HEAD. The runner does not hardcode physical GPU 0 or physical GPU 1. A dirty worktree is refused. A future run stays refused unless live HEAD is a clean authorization commit with that single parent. Phase A, Phase B, M5, D1 training, REF, and EVAL stay closed. Length mismatch and early EOS stay retained diagnostic outcomes and do not trigger rejection or resampling.

B2 is different. Its required raw set is 30,000 attempts. Guardrail rates for B2 use that full raw set. A 1,000-attempt slice is not a substitute. The existing B0 pool remains 30,080 attempts and is not re-gated as if it had been length-matched.

| Guardrail | Proposed bound | Denominator |
| --- | --- | --- |
| Valid nonempty A/C/G/U fraction | at least 0.99 | raw attempts |
| Empty or unparseable fraction | at most 0.01 | raw attempts |
| Unique fraction | at least 0.95 | valid outputs |
| Exact TRAIN match rate | at most 0.01 | valid outputs |
| Largest duplicate share | at most 0.01 | valid outputs |
| Requested-length exact-hit rate | report the rate; 0.90 is not an execution-success requirement | all raw attempts, before filtering |
| Per requested length | report the rate; 0.50 is not an execution-success requirement | all raw attempts at that requested length |

The exact-hit numerator is the count of valid outputs whose cleaned length equals the requested biological length. Its denominator is every raw attempt, before filtering. Invalid or unparseable accounted attempts are non-hits and remain in that denominator. A separately labelled valid-only diagnostic may be retained, and it must not replace this raw-attempt metric. Validity continues to be reported separately. Raw attempts, valid outputs, and exact hits must always be reported together. A low exact-hit rate does not invalidate or rerun the B1 diagnostic pool.

Requested-length exact-hit rates are reported for the diagnostic sample. They are not B1 diagnostic-run success requirements. They do not apply to B2, whose length is the sampled length. They are not applied retroactively to the existing B0 pool as a checkpoint-eligibility rule.

Valid output means a nonempty cleaned body matching `^[ACGU]+$` under the M1-approved cleaner. Raw attempts that fail that test stay in the raw denominator. Duplicate valid outputs stay in the valid denominator. Nothing is dropped silently before a rate is calculated.

B2 attempt 2 is completed accepted evidence at `/home/laura/rnagenesis-mres-runs/m4_b2_empirical_null_6f82878_attempt2`. The accepted raw SHA-256 is `bbe35f448db0d7fc02ad0156865798382b0b41e9ad047b4e52eddf7cff740c83` and the accepted manifest SHA-256 is `31c07fb966c462263307569b383b112ecfb39725adb9b1b2fd2f93a95d3d8baa`. That evidence must not be rerun. Its raw output is canonical JSON Lines: UTF-8; one JSON object per attempt; key order exactly the declared field order; compact separators `,` and `:`; `ensure_ascii=false`; no spaces outside string values; an LF after every record, including the final record; no BOM; and no carriage returns. The raw-output SHA-256 is the hash of those exact file bytes. Probabilities were computed in float64, in order A, C, U, G. An implementation must reject an empty TRAIN stream, a non-A/C/G/U character, a count other than 669, a duplicate input sequence, a non-finite or negative probability, and any probability vector whose ordered A/C/U/G values fail `abs(sum(probabilities) - 1.0) <= 1e-12`. Relative tolerance is zero. This stage does not recompute nucleotide probabilities from biological TRAIN text and does not authorise another B2 sample.

Report, and do not threshold-optimize:

- nearest-TRAIN normalized edit distance;
- maximum edit similarity to TRAIN (one minus the minimum Levenshtein distance divided by the longer sequence length; not a sequence identity);
- nucleotide and dinucleotide distributions;
- MFE and MFE per nucleotide;
- paired fraction;
- full length-stratified results.

Clustering-dependent claims, selection of a clustering identity threshold, frozen-representation or embedding metrics, and representation aggregation rules are formally deferred beyond M4. They are not M4 closure blockers. No substitute optional metrics are added in their place.

## 6. Roles

| Role | Use |
| --- | --- |
| TRAIN | Fitting, and copying or novelty reference. Not checkpoint selection. |
| VALIDATION | Development decisions and the fixed-draw selection metric. |
| REF | Later AptaRank calibration only, after the generator is frozen. |
| EVAL | Final held-out assessment only, after an M9C unlock record. |

Development generator comparisons do not use REF.

## 7. B1 length characterization

Phase A and Phase B are specified in `config/experiments/B1_generic_generation.yaml`. Both evidence packages are accepted and are not re-executable. The active development-pool design is the restored 1,000-raw-attempt diagnostic contract.

Phase A keeps the eleven target lengths in ascending order. For one target biological length, the three candidate `max_seq_len` values — the target, the target plus 1, and the target plus 2 — use the same seed, `41000 + zero-based target index`. There are 11 seeds, 41000 through 41010. There are not 33 different seeds. Each candidate still has 16 attempts, and each candidate invocation is initialised with that shared target seed, so the total remains 528. Each attempt records `pairing_group` equal to the target length and `attempt_within_candidate` from 0 through 15. Sharing the seed reduces stochastic confounding when comparing decoder caps. It does not imply that output strings must remain aligned after early termination or stochastic divergence.

Phase B used 16 raw attempts for every one of the 89 distinct TRAIN lengths. The batch size was 16 and the total was `89 × 16 = 1,424`. Each ascending length had one invocation seed, `42000 + zero-based length index`. That evidence is accepted. Its exact-hit rates remain diagnostic observations. They do not become execution-success requirements for the restored 1,000-attempt pool. Validity is still reported separately.

Phase A and Phase B evidence is accepted. The 1 October 2026 course change restored the 1,000-raw-attempt diagnostic contract and marked the rejection/resampling direction superseded before implementation. Sequences must not be silently truncated to force a length. Early EOS and length mismatch remain diagnostic outcomes.

The M1 boundary observation is a five-step, two-sequence smoke: `max_seq_len` 37, leading `11`, empty suffix, raw length 38, cleaned length 36. It is a boundary reference. It is not a 50-step length law.

Review triggers before Phase B are observations that require human interpretation, because Phase A exists to measure them:

- the leading boundary run differs from the M1-observed `11`;
- any trailing `1`/`2` run is present;
- boundary-run frequencies vary materially with target length or candidate cap;
- early termination materially changes the cleaned-length distribution.

A trailing EOS boundary is not, by itself, a correctness failure. It may still make a proposed length-matching method scientifically unacceptable.

Hard implementation failures are separate:

- the cleaner changes an interior character;
- the cleaner removes a character outside a leading or trailing run of `1`/`2`;
- accepted cleaned output is empty or contains a non-A/C/G/U character;
- raw output cannot be associated unambiguously with its attempt metadata;
- an output or evidence path would be overwritten.

## 8. D1 pilot boundary

The one-epoch/21-update pilot design is `APPROVED_STAGE_1_DESIGN_BLOCKED_BY_M5_AND_LATER_HUMAN_AUTHORIZATION`. Initialization is the B1 generic diffusion checkpoint. The complete EncDec stays frozen. The full denoiser is trainable. TRAIN is the only fitting input. VALIDATION is the only development evaluation input. The proposed learning rate is `3e-5`, the proposed training seed is 42, and the proposed maximum is one epoch or 21 optimizer updates. That training seed is a PyTorch generator. It is not the B2 NumPy stream, which also proposes seed 42, and it is not the validation-draw seed 1. Warmup is derived from the actual approved update count. If that count is 21, the plan formula gives 2. The five-epoch warmup of 10 is not the pilot warmup.

Validation is proposed at optimizer updates 0, 7, 14, and 21. Update 0 references the immutable released B1 checkpoint and its recorded hash, `c268021b6cab37423e3bffd495b139bb69698d8d11c7b96477fbfb239b0cff26`. It does not require copying or saving another 7.4 GB initialization checkpoint.

Retention of the update-7 and update-14 states is `APPROVED_AS_LEARNING_CURVE_EVIDENCE_ONLY_NOT_SELECTABLE_WITHOUT_GUARDRAIL_EVIDENCE`. Those states are learning-curve evidence. They are not eligible for checkpoint selection based on validation loss alone. They cannot become selectable unless the approved generated-sample guardrails are also evaluated for those exact weights. The currently proposed diagnostic-generation authorization covers only initialization/B1 and the final pilot state. It does not cover updates 7 or 14.

The final pilot state remains a technical and scientific pilot result. It is not the final D1 model.

There is no automatic learning-rate change. A reduction to `1e-5` requires human review of the `3e-5` evidence. Diagnostic generation occurs only at the prespecified checkpoints above and only after its own authorization.

Microbatch, accumulation, mixed precision, and EMA were deferred to M5. Their absence does not, by itself, block final M4 closure. M5 must pass before this pilot becomes executable. The accepted 3 October 2026 M5 smoke does not settle them. Production numerical precision, production gradient accumulation and batch policy, EMA policy and raw-versus-EMA generation policy, the final D1 seed count, and biological training authorisation remain unresolved for M6 and D1 planning.

## 9. Still not executable

An executable workflow must refuse this approved-for-implementation package. In particular it must refuse to:

- treat `APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION` or `consumable_by_executable_workflow: false` as an approved run config;
- open REF or EVAL;
- regenerate B0 by default;
- overwrite or append to an existing evidence directory;
- rerun the completed accepted B2 evidence;
- rerun Phase A or Phase B;
- rerun the accepted 1,000-attempt development pool, or treat its consumed authorisation as a new grant;
- resample, replace, or rewrite the accepted fixed validation-draw tensors or the ordered-core artifact;
- start the D1 pilot.

## 10. M4 closure

The closure conditions are satisfied. Formal M4 is COMPLETE / GO for M5 planning only:

- accepted implementation;
- the materialised and accepted 1,000-attempt schedule;
- the accepted fixed validation artifacts;
- completed and accepted B1 diagnostic evidence;
- frozen code and configuration hashes;
- the final human closure decision.

The GO does not authorise M5 execution or D1 training. Formally deferred beyond M4, and therefore not M4 closure blockers:

- clustering-dependent claims;
- selection of a clustering identity threshold;
- frozen-representation and embedding metrics;
- representation aggregation rules.

Microbatch, gradient accumulation, numerical precision, and EMA stay explicitly deferred to M5. M4 is not blocked merely because those M5-dependent hardware results do not yet exist. The D1 pilot fields that are already fixed, including the learning rate, training seed, one-epoch or 21-update budget, fixed-draw validation points, and frozen EncDec, remain fixed. This implementation does not begin M5 or D1 training. The same deferrals are recorded in `config/experiments/generator_evaluation.yaml`.

On 3 October 2026 formal M5 became COMPLETE / GO for M6 planning only. The account is the M5 current status in `docs/fine-tuning-implementation-plan.md` and the same-day entry in `docs/log.md`. The GO does not authorise M6 execution, biological TRAIN or VALIDATION access, D1 training, GPU use, REF, EVAL, or a new run. Physical microbatch 8, gradient accumulation 4, and FP32 are M5-supported observations. EMA was disabled and smoke generation used raw weights. Those observations were a conservative M6 proposal at M5 acceptance. The M4 GO above still authorises M5 planning only; it is not the M5 acceptance.

## 11. M6 implementation review

On 3 October 2026 the inactive M6 package is `M6_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED`. This is not `M6_IMPLEMENTED_NOT_AUTHORISED`, and it does not authorise execution. The checked-in pilot YAML stays non-consumable and binds no GPU or output directory. The Python implementation contains the authorised worker, accumulation rule, tensor-safe checkpoint comparison, and production-manifest validator described in [M6 pilot implementation](m6_pilot_implementation.md). A later authorisation-only commit would be required before that path can run. Sections 8 through 10 above remain the M4 and M5 history. This addendum does not change them and does not authorise biological TRAIN or VALIDATION access, D1 training, GPU use, REF, EVAL, or a new run. The final D1 seed count remains unresolved for M7.

On 5 October 2026 the same inactive status was corrected in place. Fixed-draw validation uses the prepared denoiser in evaluation mode, inside `torch.no_grad()` and without autocast, and then restores the training state. EncDec evidence is the parameter digest and the persistent-buffer digest at initialization and after updates 7, 14, and 21, with the documented rotary runtime caches excluded. Validation time is the sum of the synchronized durations at updates 0, 7, 14, and 21. The production manifest cross-checks that evidence: update 0 has a null relative record, updates 7, 14, and 21 match the review-item schema and the recorded aggregate MSE, worsening flags equal `later > initial`, and `validation_review.observations` match those relative records. The status remains `M6_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED`.

## 12. M6 attempt 6 and the update-21 diagnostic comparison (executed; see section 13)

On 6 October 2026 the M6 attempt-6 training pilot (`/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_6fd611589d7a_gpu1_attempt6`) was accepted as the successful training attempt. Its fixed-draw VALIDATION MSE fell from `0.1404131591699728` at update 0 to `0.10955412184224482` at update 7, `0.10202736076728462` at update 14, and `0.10076265001606723` at update 21. The `3e-5` pilot passed, and no reduction to `1e-5` is proposed. At that stage, **M6 was not complete.** The generated-sample guardrails in section 5 had not been evaluated for any D1 weights, and M6 stayed open until they were generated and reviewed (section 13).

Update 21 was the sole D1 pilot checkpoint for the then-pending diagnostic comparison. Updates 7 and 14 stay learning-curve evidence and receive no generation, as section 8 already records. The comparison reuses the accepted B1 development pool in place of a new B1 run: the accepted schedule (`0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0`, length vector `7e6cb523a85116fc38788c336ef50c26e0eccc343712aaea89956a73c485bd3c`), the accepted B1 ledgers, and the accepted B1 metrics. B1 is read only and is not regenerated.

The guardrails, denominators, and report-only diagnostics are exactly those of section 5. Requested-length exact-hit rates are reported, overall and per length, and the historical 0.90 and 0.50 values are not enforced. TRAIN may be opened only for exact-copy and nearest-TRAIN diagnostics. VALIDATION is not requested by this comparison. REF and EVAL are not reachable.

Normalisation uses the approved M1 cleaner of section 5, the same code that produced the accepted B1 pool. In that pool 39 of 1,000 attempts have a trailing `2` (early EOS) and are valid under the cleaner. The stricter exact-`11`, no-suffix helper in the M6 contract would reject them, and the accepted B1 pool would then fail the 0.99 valid-fraction guardrail itself. The diagnostic therefore reports that helper only as a sensitivity count. This policy is decided; see [M6 pilot implementation](m6_pilot_implementation.md) section 6.

The inactive implementation was described in [M6 pilot implementation](m6_pilot_implementation.md) section 11. That description did not itself authorise generation, a GPU, TRAIN access, M7, REF, or EVAL.

## 13. M6 closure and checkpoint selection

The update-21 diagnostic generation was executed once under the single-use authorisation `m6_d1_update21_diagnostic_6953687e2e9_gpu0_attempt1` on physical GPU 0 (UUID `GPU-b3c42ea9-ec47-c854-e469-cd78e443c76b`, PCI `00000000:41:00.0`, `CUDA_VISIBLE_DEVICES=0`, logical `cuda:0`). The authorization commit is `0682185758eb62d9401706b1e37e02468c4c9fbb`. Its sole parent and the executing implementation commit are `6953687e2e9e36bb1670a7b2b9faaa18849c3711`. Immediately before authorization and throughout execution and closure review, local and live `origin/main` remained `6953687e2e9e36bb1670a7b2b9faaa18849c3711`; the authorization commit had not yet been pushed. The evidence directory is `/home/laura/rnagenesis-mres-runs/m6_d1_update21_diagnostic_6953687e2e9_gpu0_attempt1`. `m6_diagnostic_manifest.json` is 86,206 bytes, SHA-256 `95074f0d76ab11cf43146e672bc75399da56dd9b2ffeef8fa14a39c7f8acd959`, canonical JSON, authorisation state `consumed_successfully`. No `authorization_failure.json` exists. The compact review summary is `/home/laura/m6-review-archives/m6_update21_diagnostic_attempt1_compact_summary.txt` (7,906 bytes, SHA-256 `7795371f2815370d1387dd4245b66a436d734dfba9c4d427bf4af0ede9c230bc`).

All five approved hard guardrails passed (valid fraction `1.0`, empty fraction `0.0`, unique fraction `1.0`, exact TRAIN match rate `0.0`, largest duplicate share `0.001`). Requested-length exact-hit rates stay report-only (D1 `0.971`, B1 `0.961`). The section 4 selection rule is therefore satisfied for the raw update-21 checkpoint, whose fixed-draw VALIDATION MSE `0.10076265001606723` is the lowest recorded. The comparison with B1 is descriptive and report-only. It is not a paired significance test and supports no claim of significance, biological quality, clustering, embedding, or downstream performance. On 6 October 2026 the human gate approved M6 closure and the selection of the raw update-21 checkpoint for M7 planning only. M7 execution, further training or generation, GPU use, biological-data access, VALIDATION, REF, and EVAL remain unauthorised.
