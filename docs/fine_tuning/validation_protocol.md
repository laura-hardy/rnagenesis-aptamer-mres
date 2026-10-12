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

## 14. M7 validation, candidates and lazy guardrails (inactive package)

**Historical status, 6 October 2026: M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED.** This section describes how the inactive M7 package validates and selects. At that date it authorised no execution, no biological access, no GPU use, and no run directory, no M7 authorisation existed, seeds 43 and 44 had not run, and M7 was not complete. The closure is section 15. See [M7 final replicates implementation](m7_final_replicates_implementation.md).

**Fixed-draw validation.** Each replicate validates the raw denoiser on the unchanged accepted M4 four-draw artifacts (95 sequences, four draws, 380 pairs, equal weight per pair, the seed-1 draws loaded and never regenerated) at update 0 and after every epoch, so at updates 0, 21, 42, 63, 84 and 105. Update 0 is provenance only and is never a candidate. Updates 21 through 105 (epochs 1 through 5) are the five candidates of that seed. VALIDATION is read only through those fixed draws.

**Ranking.** Within each seed the candidates are ordered by fixed-draw VALIDATION MSE ascending. An exact tie goes to the earlier epoch. The order is sealed in the replicate manifest as an ordering; it makes no selection and carries no guardrail evidence.

**Lazy guardrails.** Candidates are evaluated in the sealed order until the first passing checkpoint. Each evaluation uses the accepted 1,000-attempt M6 schedule (`0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0`), the approved M1 cleaner, and the five approved numerical guardrails of section 5, with the accepted M4 comparison semantics. Requested-length matching, early EOS and gross length behaviour are report-only and have no threshold. The evaluated candidates must be a prefix of the sealed ranking: a later-ranked candidate is authorised only by an entry that binds the failed manifests of every earlier-ranked candidate, and nothing is evaluated after the first pass. The first passing candidate of each seed is selected. The production generator (112 invocations, invocation seed `44000 + index`, the approved M1 cleaner, raw weights only) is implemented and wired as the default of the candidate stage; before it generates anything it binds the checkpoint to its sealed replicate manifest and checks that the entry's position and failed predecessors are the prefix of that ranking. Every invalid, empty, duplicate, early-EOS and length-mismatched attempt stays in its denominator, and nothing is resampled, replaced, truncated, padded, dropped or deduplicated. TRAIN is opened only for the exact-copy guardrail, VALIDATION is not requested, and REF and EVAL are refused before any filesystem access. The accepted M6 report-only diagnostics (requested-length exact-hit rate, early-EOS and length-mismatch accounting, nearest-TRAIN normalised edit distance, maximum edit similarity to TRAIN, nucleotide and dinucleotide distribution distance, MFE, MFE per nucleotide, paired fraction, and the length-stratified summaries) are reused unchanged and reported for every candidate; they have no threshold, cannot change the ranking or the five guardrails, and edit similarity is not sequence identity. Before a candidate is consumed, its predecessor replicate manifest is reopened, hash-checked, validated independently and compared with every identity the entry carries.

**No eligible checkpoint.** If no candidate of a seed passes, the outcome is `no_eligible_checkpoint`. The learning rate, thresholds, architecture and seed are not changed automatically. A human decision is required.

**Seed plan and consistency.** The final-selection stage accepts seeds 43 and 44, or seed 43 alone with a separately sealed operational deviation record created before M8 generation. It rejects seed 44 alone, a missing seed without the record, duplicate or unexpected seeds, mismatched B1 initial-state digests, inconsistent validation-artifact identities, an extra, missing or duplicate epoch candidate, selection from update 0, selection from an unevaluated or failed candidate, a non-prefix evaluation, and any REF- or EVAL-derived input. The selection is a prespecified set of seed-specific checkpoints and never depends on downstream EVAL. The final-selection manifest records `human_gate_required: true` and `m7_complete: false`. `validate_final_selection_manifest` re-derives every embedded claim (exact nested key sets, digest shapes, ranking hashes recomputed from the candidate table, seed status from the lazy trace, the guardrail index against the evaluated rows, every checkpoint member hash, and the replicate hashes against the seed records and the deviation record); it proves internal consistency only, so the launcher also rebuilds the manifest from the bound sealed input bytes before and after consumption, and `selected_set_sha256` is a content hash, not an authenticity mechanism.

**Final-selection launcher (revision 4).** `m7_selection.py --authorisation-id <id>` is the only way to run the selection. While the checked-in configuration is inactive it refuses with `execution_not_authorised` before inspecting the environment, git, the run root, any manifest, RNAGenesis or an output path. After a later authorisation-only commit that changes only `config/experiments/D1_final_selection.yaml` it reads exactly the bound replicate and guardrail manifests (path, byte count and SHA-256 bound, symlink- and hard-link-safe, canonical JSON, exact schema), never a checkpoint's contents, biological data, REF or EVAL, consumes exactly the bound new output directory, and writes the selection atomically. A retry needs a new id and a new directory. Seed 44 is never omitted by the launcher: a one-seed entry must carry the already sealed human-approved operational deviation record.

**Fixed `PATH`.** Child processes receive the constant `PATH` `<pinned environment>/bin:/usr/bin:/bin`, never parent text; `git` and `nvidia-smi` are started only by their absolute, `lstat`-validated paths `/usr/bin/git` and `/usr/bin/nvidia-smi` in a fresh environment; the child interpreter is the absolute pinned Python.

**Not decided here.** Nothing in this section changes REF or EVAL handling: both stay unopened, and no REF- or EVAL-derived value may enter an M7 manifest.

## 15. M7 closure and the selected set

On 8 October 2026 the human gate accepts the selected set in `/home/laura/rnagenesis-mres-runs/m7_d1_final_selection_b5de24327ed5_attempt1`. `m7_final_selection_manifest.json` is 13,124 bytes, SHA-256 `49b218e3df74825e1931148e2f65b25aae057c822e2ab32d44c2960b1587c91c`, `selection_outcome: selected_set_complete`. The selected-set SHA-256 is `af0c0e555a8b878feadeb17fcbde18d8b780819a42d9e0cc547d2fc0c6895f8f`. Completed seeds are 43 and 44. Each selected checkpoint is epoch 5, update 105. The M8 allocation is 15,000 raw attempts for seed 43 and 15,000 for seed 44. The manifest closure stays `human_gate_required: true`, `m7_complete: false`, and `m8_generation_performed: false`, and it is not rewritten. Those flags are the run-time gate. This section is the milestone-status authority for acceptance, together with section 14 of [M7 final replicates implementation](m7_final_replicates_implementation.md).

Seed 43 attempt 1 remains a consumed failure at `runtime_identity` and is not accepted training evidence. Seed 43 attempt 2 and seed 44 attempt 1 are the accepted replicates. The result is the two-seed set only. Seed 42 stays excluded, no third seed was trained, and no operational deviation was required. All five epoch checkpoints of each executed seed are retained through at least 1 November 2026. No deletion is implemented.

`D1_candidate_guardrails.yaml` and `D1_final_selection.yaml` return to their inactive documents. `D1_final_replicates.yaml` remains the seed-44 authorisation because the tests require that live file and the configuration classifier has no consumed status. Closing M7 does not create an executable authorisation. M8 generation, GPU use, TRAIN, VALIDATION, REF, and EVAL remain unauthorised.

## 16. M8 raw pools and the later common evaluation

**Configuration status: `M8_RAW_GENERATION_READY_FOR_REVIEW_NOT_AUTHORISED`.** This section records the approved refinement and the inactive shared-GPU contract. Completion and the evaluation handoff are section 17. The checked-in configuration authorises no further generation, assembly, GPU use, or run directory. The implementation is [M8 raw generation](m8_raw_generation.md). The checked-in GPU 1 seed-44 block-B authorisation remains the unconsumed retirement, superseded before dispatch. That refusal was a GPU-availability gate, not a model or scientific failure. The consumed shared-GPU seed-44 authorisation is recorded in section 17 and is absent from the inactive configuration.

M8 produces and seals raw B1 and D1 pools. B1 is 30,000 raw attempts. D1 is 30,000 raw attempts, split 15,000 from training seed 43 and 15,000 from training seed 44. The M4 and M7 1,000-attempt pools stay outside those totals. Parsing, filtering, clustering, representation analysis, and the four-condition comparison occur later under a common frozen evaluation protocol. M8 does not invoke the cleaner and does not classify a raw string as valid, invalid, accepted, rejected, biological, or filtered.

Two D1 training seeds are the approved final set. The absent third seed is a resource and time limitation. The one-seed M8 alternative is historical and is not executable, because both final seeds completed. Rejection and resampling language from earlier planning is superseded by fixed raw-attempt accounting with no replenishment.

The 30,000 attempts in each pool are generated draws. Generation seeds are unique within a technical block and are intentionally reused across the paired B1 and D1 arms. They are not 30,000 independent model-training replicates. D1 has two training replicates, and the training seed is tied to the technical block. Those blocks allocate 830,348 nt and 830,404 nt, which is extremely close and not identical. Later evaluation must not analyse the pools as if every attempt were an independent training replicate. Exact raw bytes in the retained invocation files stay authoritative. `raw_decoded_text` is only the deterministic UTF-8-else-Latin-1 representation checked against those bytes.

M7 completion is the 8 October 2026 human closure. Sealed M7 manifest bytes remain unchanged, including `m7_complete: false` and `m8_generation_performed: false`. The live `D1_final_replicates.yaml` seed-44 authorisation is historical M7 state and is not M8 authority. The completed D1 arms recorded that approved selected set as `selected_set_evidence` without rewriting the sealed M7 manifest. On each sealed M8 manifest, `repository_identity.mres_commit` is that run's authorization commit, and `proposal_base_commit` keeps `d0f9a397b536c64ca1b22662cc9ae36aea0101f6`. No further M8 execution is authorised. This closure does not rewrite those manifests.

Shared GPU use, if a later authorisation names `shared_allowed`, is an operational and resource-management deviation. It does not change sampling, the D1 seed-44 epoch-5 update-105 checkpoint, the 15,000 raw attempts, the block-B schedule, the 164 invocations, or generation seeds 900000–900163. It may change wall-clock runtime and it raises interruption and resource-contention risk. It does not by itself justify a biological or model-quality conclusion. The recommended future free-memory threshold on physical GPU 0 is 30 GiB, exactly 32212254720 bytes. That value would be stored on the authorisation and read from the single GPU and storage observation taken during pre-consumption validation, before output creation and model generation. The observation is not repeated after asset verification. Checkpoint and asset verification may occur between that observation and output-directory consumption. Concurrent workloads may grow afterwards. The threshold is a point-in-time safety gate, not a reservation or a guarantee. The manifest records that single observation. A selected-GPU compute-app row counts only when its PID is a positive decimal integer. An empty, non-decimal, zero, negative, `[N/A]`, or `[Not Found]` PID on the selected GPU is refused by the shared evidence validator used for launch and assembly. An indeterminate row for another GPU does not increment the selected-GPU count. Historical exclusive B1 and seed-43 manifests remain valid without rewriting. The one consumed `shared_allowed` execution is the D1 seed-44 block-B arm in section 17.

## 17. M8 completion and the four-condition handoff

On 10 October 2026 the M8 raw pools are complete and the checked-in configuration is returned to the inactive status `M8_RAW_GENERATION_READY_FOR_REVIEW_NOT_AUTHORISED`. Both authorisation lists are empty. Every execution flag is false. This section does not rewrite a sealed manifest. The detailed identities are section 8 of [M8 raw generation](m8_raw_generation.md).

B1 combined ledger: `/home/laura/rnagenesis-mres-runs/m8_b1_combined_1069b63_cpu_attempt1/m8_combined_raw_attempt_ledger.jsonl`, 30,000 records, 26,427,607 bytes, SHA-256 `37ba0e1b852a6b8492a816a4adc0c6bfee15a554ba28a8ba5dd91d9e32a255d9`. Authorization commit `b79e70c0d895ba34f7655732412a1c3e039b4067`. Assembly manifest SHA-256 `f217e2e8ce922eef42b5f761159c7d96b7938585b4840922321454076d95d458`. Consumption record SHA-256 `5cf932bc39d9ed5a02d18056c85bde85c0a016d5f24c9bb7a4fa751d74827e92`.

D1 combined ledger: `/home/laura/rnagenesis-mres-runs/m8_d1_combined_1069b63_cpu_attempt1/m8_combined_raw_attempt_ledger.jsonl`, 30,000 records, 28,971,289 bytes, SHA-256 `cedcc36133f5dfb3678e1560c6d6bab703136fe89e512e939b9f93a9a6361de9`. Authorization commit `c9a8cfc8cb2d720fdab8743bed088e8f900c3198`. Assembly manifest SHA-256 `5ec79e1485b201d801ca819d9d60a2ee4383abd9cccfbbb011c6e11a9a59bbcb`. Consumption record SHA-256 `59f1b09349e1965eff813cb24a9c969d77a1770c2febec60fc674123c302401a`. The 30,000 D1 rows are 15,000 from training seed 43, technical block A, generation seeds 800000–800162, and 15,000 from training seed 44, technical block B, generation seeds 900000–900163.

Source arms, each 15,000 raw attempts, with manifest SHA-256, raw-ledger SHA-256, and `elapsed_seconds`:

- B1 block A, `bb788e862d6a7c41e8b942d53e8121d2d19722574d4956b4c2c2644f392931b9`, `5e9c00664fce3a423e8c89aad43f32fcf1d1db59b8639561eff436e6fdba7d82`, 8348.671256661415. Exclusive physical GPU 1. Authorization commit `c08be8839d9681d4f68b9242abcf9a7ff40c4d24`.
- B1 block B, `d51be51bbf10a90ca7ff809403f38007167a7cdd72704473a0dd39a2bb8510e7`, `11003ba60bf191ee841ae55a7dd81f0d78d731c96855f28f564b53da4b353e61`, 8369.749910581857. Exclusive physical GPU 1. Authorization commit `f13e0849e19632181315bf5585ae585e16bbb127`.
- D1 seed 43 block A, `a0fde7024662ee13837e6f99b163711263b60d55fa6c60b8012db53f93873e52`, `d0d16afe63f767179c8e7af261095af709ce6298cfe64673600cf04965d87473`, 8451.951393645257. Weight SHA-256 `c0797888bde9033cc15b056c8c09e70b9f7fba0fb21b1f3840a4f1efb77031ab`. Exclusive physical GPU 1. Authorization commit `acc7e244926fcb9336d35d29d0d767cf1afc5743`.
- D1 seed 44 block B, `f38aebd53e08c9012af5c4faa8a51a07ca39538dd1ccfcd26d003719b6ea5ca3`, `d007b8d8a2cfed49104be90100059a9f2fdf8ffee86933d5d68b26ba7245920b`, 8381.193621516228. Weight SHA-256 `d0fcb5174230b8bbbc6bfe59eabda9b37687c03800012bc1a6981cc215469ed5`. Shared physical GPU 0, `shared_allowed`, two pre-existing compute processes. Authorization commit `50a41b84c7340aca5841672ea7507ceb4c1b7b94`.

Summed GPU execution time is 33551.566182404757 seconds. Wall-clock scheduling time from `2026-10-08T13:55:44+00:00` to `2026-10-09T13:32:21+00:00` is 84997 seconds. The arms were sequential. The difference is idle time between arms.

Both selected checkpoints are epoch 5, update 105. Selected-set SHA-256 `af0c0e555a8b878feadeb17fcbde18d8b780819a42d9e0cc547d2fc0c6895f8f`. Final-selection manifest SHA-256 `49b218e3df74825e1931148e2f65b25aae057c822e2ab32d44c2960b1587c91c`. Master indexes 0 through 29999 occur exactly once in each combined ledger. Record ids are unique within each combined ledger and are separate from training seeds and generation seeds. The no-filtering and no-replenishment contract stands. Assembly also records parsing, deduplication, and metric computation as false. Evidence is retained through at least 1 November 2026.

The seed-43 M7 attempt 1 failure remains an environment and runtime-identity failure, not a model failure. M7 guardrail samples were not included in M8. Only two fine-tuning seeds were used, because of time and GPU constraints, with evaluation completeness prioritized over a third training replicate. Because the training seed is coupled to the technical block and the generation-seed range, pooled D1 supports condition-level evaluation and does not support clean replicate-level causal inference. Raw attempts are not yet established to be valid nucleotide sequences. No duplicate removal, exact training-set-match analysis, leakage analysis, biological-quality assessment, structure analysis, clustering, representation-space analysis, or functional evaluation was performed in M8. Guardrails establish generation and runtime sanity only. Shared GPU use may affect runtime and resource contention on the seed-44 arm; the exact generated bytes and provenance remain sealed.

Later evaluation must apply the same declared parsing and filtering policy symmetrically across B0, B1, B2, and D1. Evaluation must not tune parameters after inspecting REF or EVAL outcomes. The evaluation worktree remains out of scope and is not entered or modified by this closure. This section does not authorise that evaluation.
