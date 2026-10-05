# M6 pilot implementation

**M6_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED**

This document describes the checked-in inactive D1 pilot. It does not authorise execution, biological TRAIN or VALIDATION access, model or checkpoint loading, GPU use, REF, EVAL, diagnostic generation, or creation of a run directory. Attempt 1 is recorded below as a consumed failed engineering attempt. `docs/log.md` records the same attempt.

The authoritative configuration is `config/experiments/D1_diffusion_pilot.yaml`. There is no second pilot YAML. The previous M4 status, `APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION`, remains in that file as history and in Git history. It does not authorise M6.

## 1. Inactive gate

The checked-in document has:

- `document_status: M6_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED`;
- `consumable_by_executable_workflow: false`;
- `execution.authorised: false`;
- null output directory, evidence directory, authorisation id, authorisation parent commit, and executing implementation commit;
- an inactive `pilot_execution_authorisation` block that binds no GPU and no paths;
- biological access closed.

The tracked YAML does not contain an `authorization_commit` key. That SHA is the live MRes HEAD observed when an authorisation commit runs. Storing it in the same commit would be self-referential.

The document contains no physical GPU index, UUID, PCI bus, or `CUDA_VISIBLE_DEVICES` value. The production entry point is `scripts/modelling/m6_pilot_runner.py`. It accepts `--help` and no other arguments. A path, data, model, configuration, or output override is rejected. Environment variables cannot inject a backend or a path. The entry reads only the pinned YAML. The inactive document raises `execution_not_authorised` before importing torch, Accelerate, Diffusers, or RNAGenesis, before opening biological data or validation tensors, before probing CUDA, and before creating a directory.

The same Python entry can accept a future document whose status is `M6_AUTHORISED_FOR_SINGLE_USE_EXECUTION`. That path is not enabled by this checked-in file. The parent process performs repository, authorisation, path, and identity checks with the standard library. It observes the accepted model assets and the pinned interpreter before it creates the bound output directory. Creating that directory consumes the authorisation once. The parent then starts the pinned interpreter with its working directory set to the pinned RNAGenesis root, bytecode writing disabled, the three Hugging Face offline controls, and Python, Hugging Face, Torch, and XDG caches under the consumed directory. The production child confirms that its resolved working directory is that root before it imports the training stack. A later import, identity, worker, or training failure leaves `authorization_failure.json` in that directory and does not permit reuse. Synthetic dependency injection is an in-process test seam. It is not a CLI argument or an environment variable.

Synthetic tests call `run_synthetic_control_flow` in-process. That function is not reachable from the CLI.

A zero child exit is not success. The parent accepts the run only when `m6_pilot_manifest.json` is a regular non-symlink file in the bound directory, no failure record exists, the bytes are canonical JSON, and `validate_production_success_manifest` accepts that document for the consumed authorisation. A zero exit with no manifest, malformed or non-canonical JSON, a failure record, or a rejected manifest is a consumed failure, and the invalid manifest is not left as evidence. The child writes `authorization_failure.json` for failures before training as well as during it: runtime isolation, configuration load, repository re-observation, consumed-authorisation validation, authorisation-commit comparison, and training-stack import. The parent keeps that record. It does not replace `identity_mismatch`, `provenance_mismatch`, `authorisation_commit_invalid`, or another precise child code with only `incomplete_evidence_or_manifest`. A generic child record is kept in the same way: the parent does not replace its stage, update, microbatch, or detail. The record includes the authorisation commit, parent commit, and implementation commit only after those values have been validated.

Every exception after authorisation consumption records the latest stage, update, and microbatch. `runtime_identity` is set before the worker obtains the training stack's Torch object. Other stage markers are set before the stage-entry operation. An ordinary exception is registered as `incomplete_evidence_or_manifest`. Its detail is `authorized worker failed; exception_class=<ClassName>`. `<ClassName>` is the Python exception class when that name is an ASCII identifier of at most 128 characters and is not itself sequence text; otherwise the recorded class is `Exception`. The detail does not include the arbitrary exception message, a traceback, biological sequence text, or tensor contents. No traceback file is written into the run directory. A precise `M6PilotError` keeps its code, detail, stage, update, and microbatch. Recording the failure removes a claimed success manifest, so a failure and an accepted success manifest cannot both remain. The failure stays non-resumable, and creating the bound directory still consumes the authorisation once.

The final production CUDA generator state is read with `torch.cuda.get_rng_state` at stage `rng_final_observation`. If that read fails, the worker raises `cuda_rng_final_observation_failed`, writes no success manifest, and does not substitute the initial CUDA state. The CPU stand-in leaves `read_cuda_rng` false and does not take that production read.

## 2. Pilot decisions

Initialization is the immutable B1 generic diffusion checkpoint, `configs/rnagenesis/diffusion`, weight SHA-256 `c268021b6cab37423e3bffd495b139bb69698d8d11c7b96477fbfb239b0cff26`. Update 0 validates against that checkpoint and does not copy it. The prohibited initialisation remains `checkpoints/Aptamer/diffusion`.

The complete EncDec stays frozen. The full denoiser is trainable. Precision is FP32 only. EMA is disabled. Validation, and any later diagnostic generation, uses raw denoiser weights.

Physical microbatch is 8 and gradient accumulation is 4. The intended effective batch is 32. The 669 TRAIN records produce 84 microbatches and 21 optimizer updates. The final window contains 29 examples with microbatch sizes `[8, 8, 8, 5]`.

Example-weighted accumulation is the authority in `example_weighted_contributions`. Each microbatch contributes `microbatch_size / window_example_count` as an exact rational. Those contributions sum to 1. The applied float scales use the same rationals, with the last scale replaced by the residual `1 - sum(previous scales)`, so the float64 scales also sum to exactly 1. A full window is four weights of `8/32`. The final window is `8/29`, `8/29`, `8/29`, and `5/29`.

The M5 smoke divided each of four equal microbatch losses by 4. That equal split is not the partial-window rule used here.

Accelerate 0.25.0 divides a non-DeepSpeed loss by `gradient_accumulation_steps` inside `Accelerator.backward`. The authorised worker therefore uses manual accumulation and constructs the Accelerator with `gradient_accumulation_steps=1` and `mixed_precision="no"`. `production_loss_scale` applies the example weight and then divides by 1. It does not also multiply by 4. CPU tests compare one concatenated batch with the weighted microbatches for both the 32-example window and the 29-example window.

AdamW uses learning rate `3e-5`, betas `(0.95, 0.999)`, weight decay `1e-6`, and epsilon `1e-8`. The gradient clip norm is 1.0. A finite norm above 1.0 is clipped and recorded. It is not an abort. The pilot seed is 42. The fixed-draw VALIDATION seed and artifacts remain the accepted M4 artifacts, seed 1. Those tensors are loaded and are not regenerated.

Validation runs at optimizer updates 0, 7, 14, and 21. Weight checkpoints are retained at 7, 14, and 21. Updates 7 and 14 are learning-curve evidence only. They are not selectable from validation loss alone. Update 21 is the final pilot state. It is not selected by validation loss alone, and diagnostic guardrails are not evaluated by this runner.

There is no automatic reduction to `1e-5` and no learning-rate sweep. The training runner does not generate diagnostics. Generation requires a later, separate authorisation.

## 3. Applied learning-rate schedule

`learning_rate_multiplier` is the only schedule authority. It does not call the Diffusers cosine constructor. That constructor uses `current_step / num_warmup_steps`, and a zero-based LambdaLR index makes the first applied multiplier 0. This schedule never applies that position.

Positions 1 through 21 are the applied updates. Position 22 is the scheduler position immediately after update 21. It is exactly 0 and it is not applied.

- Update 1 uses `0.5 × 3e-5`.
- Update 2 uses `1.0 × 3e-5`.
- Update 3 starts the cosine phase at progress 0, so it also uses `1.0 × 3e-5`.
- Updates 4 through 21 use `0.5 * (1 + cos(pi * progress))` with `progress = (position - 3) / 19`.
- Position 22 returns 0 by an explicit branch, before the cosine expression.

Every applied learning rate is written into the optimizer param groups immediately before that optimizer step. None of the 21 applied values is zero. Decimal strings use format `.17g`. Position 22 is the next unapplied schedule position. The worker does not step a PyTorch scheduler and does not record position 22 as `last_epoch`.

| Update | Applied learning rate |
| --- | --- |
| 1 | `1.5e-05` |
| 2 | `3.0000000000000001e-05` |
| 3 | `3.0000000000000001e-05` |
| 4 | `2.9795419551040836e-05` |
| 5 | `2.9187258625509518e-05` |
| 6 | `2.8192106268097336e-05` |
| 7 | `2.6837107640945904e-05` |
| 8 | `2.5159223574386117e-05` |
| 9 | `2.3204222371836409e-05` |
| 10 | `2.1025431369794546e-05` |
| 11 | `1.8682282307111988e-05` |
| 12 | `1.6238690182084989e-05` |
| 13 | `1.3761309817915017e-05` |
| 14 | `1.1317717692888014e-05` |
| 15 | `8.9745686302054618e-06` |
| 16 | `6.7957776281635993e-06` |
| 17 | `4.8407764256138869e-06` |
| 18 | `3.162892359054098e-06` |
| 19 | `1.8078937319026655e-06` |
| 20 | `8.1274137449048048e-07` |
| 21 | `2.0458044895916516e-07` |
| 22 | `0` |

Position 22 is not an applied update.

## 4. Resume and checkpoints

Resume is not part of this pilot. `resume_supported` is false. Optimizer moments and a resumable training sidecar are not saved. An interrupted attempt is failed and cannot continue. Restart requires a new output directory and a new single-use authorisation.

At updates 7, 14, and 21 the future worker must create a new checkpoint directory and refuse if it already exists, save the raw denoiser in the Diffusers layout, and hash every saved member by streaming. The 7.85 GB weight file is not read into one bytes object. A fresh object is constructed and compared with the training denoiser entry by entry, including persistent buffers, without copying both complete state dictionaries to CPU. Each entry keeps its dtype and shape, must satisfy `torch.equal`, and contributes a digest. The ordered inventory has its own digest. The compatibility digest drops only top-level `_name_or_path`. A nested `_name_or_path` remains covered. The reloaded object is distinct from the training object. Weight reload is not training resume. Checkpoint save and reload time, when recorded, is a separate timing field and is excluded from training-update time and validation time.

Omitting optimizer-moment files is what reduces the expected retained storage from roughly 69 GB to about 24–26 GB. The arithmetic is in section 8. Update 0 adds no copy of the 7,847,725,416-byte B1 weight file.

## 5. Failure and review

Automatic technical failures are non-finite training loss, any non-finite trainable gradient, a non-finite pre-clip gradient norm, a non-finite fixed-draw VALIDATION pair loss or aggregate, a modified or trainable EncDec, no observed denoiser change after an applied nonzero learning rate, wrong repository or data or checkpoint identity, an unexpected biological path or role, REF or EVAL access, checkpoint overwrite, checkpoint save or reload incompatibility, incomplete evidence or manifest, authorisation reuse, and unexpected output normalisation in a later diagnostic phase. An ordinary Python exception after consumption is also `incomplete_evidence_or_manifest`.

### Attempt 1

On 5 October 2026 the single-use authorisation `m6_d1_diffusion_pilot_4a2fd6f7e578_gpu1_attempt1` was consumed. The evidence directory is `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_4a2fd6f7e578_gpu1_attempt1`. It is immutable failed engineering evidence. `authorization_failure.json` SHA-256 is `857b5be2ebe3742c853cefb39acea097d8c8712cfcc344a0ba0c12af89136126`. `authorization_consumption.json` SHA-256 is `e6bcc942f39394f57b08afa1224bbb30d0cf58fb2fd5fd953677656027d83d2f`. `m6_pilot_manifest.json` is absent. No checkpoints are present. Completion is `consumed_failed`. `scientific_run_completed` is false and `retained_checkpoints_exist` is false. The failure record's stage, update, and microbatch are null. The original failure stage and the underlying exception are unrecoverable from that record. Whether biological inputs or model weights were opened is unknown. The directory was not altered by this remediation. Attempt 1 is not a successful pilot and does not authorise another run.

### Attempt 2

On 5 October 2026 the single-use authorisation `m6_d1_diffusion_pilot_97cbb77d1047_gpu0_attempt2` was consumed. The evidence directory is `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_97cbb77d1047_gpu0_attempt2`. It is immutable failed engineering evidence. `authorization_failure.json` is 723 bytes and its SHA-256 is `f0b3cf0b7e871b0db46d4c4633cfc15dfae5afdd0c4c1d8751d74802cd6d716d`. `authorization_consumption.json` is 560 bytes and its SHA-256 is `dd24bfb8a4db78c0060f826d75c6286cf2e1bfa4896e0dce103ab49eb3416b1b`. `m6_pilot_manifest.json` is absent. No checkpoints are present. Completion is `consumed_failed`. `scientific_run_completed` is false, `pilot_completed` is false, and `retained_checkpoints_exist` is false. The failure code is `incomplete_evidence_or_manifest`. The recorded exception class is `AttributeError`. The recorded stage is `biological_inputs`. Update and microbatch are null. The failure detail is `authorized worker failed; exception_class=AttributeError`. `authorization_commit` is `f5e94b583cd94aabe53f72ff9cca1b922b106485`. `authorization_parent_commit` and `executing_implementation_commit` are `97cbb77d10472dd9ec75f61d1af9a6a69453b699`.

Runtime identity and asset identity completed. The required model assets were read for identity hashing. Model objects were not loaded. TRAIN was opened, hashed, decoded, and counted before the adapter failed. VALIDATION and the validation artifacts were not reached. No optimizer update, checkpoint, success manifest, or scientific result exists. Existing GPU 0 processes were authorized and were not implicated in this failure. Attempt 1 may share the same cause, but its record cannot establish that. The directory was not altered by this remediation. Attempt 2 is not a successful pilot and does not authorise another run.

`PinnedTrainingStack.read_train_sequences` passed the authorised string path into pinned RNAGenesis `read_train_sequences(path: Path, ...)`. That function calls `path.is_absolute()` in `assert_allowed_input_path`, and a string has no such method, so the call raised `AttributeError`. The same audit covers every path-bearing adapter method. `read_validation_cores` reaches the same `is_absolute()` check. `load_b1_denoiser` calls `path.resolve()`. `save_diffusers_checkpoint` calls `directory.mkdir()`. A string would raise `AttributeError` at each of those three as well. `load_frozen_encdec` and `load_scheduler` pass `str(path)` into `from_pretrained`, so a string does not raise there and a `Path` is safe. Reload calls `TransformerDenoiser.from_pretrained`, which accepts `str` or `os.PathLike` and converts with `str()` before opening a file. `load_verified_artifacts` already begins with `Path(directory)` and is unchanged. The adapter now builds a `pathlib.Path` before each RNAGenesis path call. RNAGenesis is not modified.

### Attempt 3

On 5 October 2026 the single-use authorisation `m6_d1_diffusion_pilot_712ba1856854_gpu0_attempt3` was consumed. The evidence directory is `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_712ba1856854_gpu0_attempt3`. It is immutable failed engineering evidence. `authorization_failure.json` is 719 bytes and its SHA-256 is `8d2ed2687989eac3c165e0e158c2115435845bce3abf75e903fd8934371fe50d`. `authorization_consumption.json` is 560 bytes and its SHA-256 is `287f2b59f4efe2c3d170f2695e7dc250e14dc07f19a4f8068667c866f27d7c60`. `m6_pilot_manifest.json` is absent. No checkpoints are present. Completion is `consumed_failed`. `scientific_run_completed` is false, `pilot_completed` is false, and `retained_checkpoints_exist` is false. The failure code is `incomplete_evidence_or_manifest`. The recorded exception class is `FileNotFoundError`. The recorded stage is `model_load`. Update and microbatch are null. The failure detail is `authorized worker failed; exception_class=FileNotFoundError`. `authorization_commit` is `4dd7f2c600322bf8134f57c491d10d08d86c3640`. `authorization_parent_commit` and `executing_implementation_commit` are `712ba18568548adc73013818630c4e4101417a9a`.

Runtime identity and asset identity completed. TRAIN and VALIDATION were opened and validated. Validation artifacts were opened and loaded. EncDec model loading began and failed on a runtime-relative file lookup. No optimizer update, checkpoint, success manifest, or scientific result exists. GPU 0 memory and its authorized concurrent processes were not implicated. The directory was not altered by this remediation. Attempt 3 is not a successful pilot and does not authorise another run.

`_default_spawn` started the production child with the MRes repository as its working directory. RNAGenesis `util.py` defines `ProGenPath` as the relative string `models/autoencoder/decoder/progen_configs`. `load_frozen_encdec` constructs EncDec, and that constructor opens the decoder configuration and tokenizer beneath `ProGenPath`. Those relative files resolved beneath MRes. The released biomap RNA config selects `models/autoencoder/decoder/progen_configs/config-progen2-small-rna_tokenizer_v2.json` and `models/autoencoder/decoder/progen_configs/tokenizer_rna_v2.json`. Those are the hashed required assets `decoder_config` (`42f15517e05ce96d78337fbc1bf20ffc580424fe88cbfcb2c81550b17cc7283e`, 915 bytes) and `tokenizer` (`6d8a20879cec3544cf0f33b0d481fbd5ead6a2bead2dbf1649449172c8336921`, 1317 bytes). The other `ProGenPath` opens, protein `tokenizer.json`, `config-progen2-small-rna.json`, and `DataCollatorEncDec`, are not on this constructor path. The biomap encoder config and the xTrimo vocabulary resolve from `__file__`. `DATA_CACHE_DIR` is unused. The relative `XDG_CACHE_HOME = ".cache"` assignment is in `generation.py` and `models/guidance/classifier.py`, which the worker does not import. `pipeline_ddim` imports `ProGenPath` and does not open it. M5 launched its worker with RNAGenesis as the working directory.

The production child is now launched with `cwd` `/home/laura/RNAGenesis`. Before importing or invoking the training stack, the production worker requires its resolved working directory to be that pinned root. An injected `stack_loader` remains a test seam. The runner, configuration, Git, output, checkpoint, evidence, cache, biological, and artifact paths stay absolute. Hugging Face, Torch, Python, and XDG caches stay under the consumed directory. The correction does not change permitted files, roles, data, GPUs, generation, resume, REF, or EVAL. RNAGenesis is not modified. `config/experiments/D1_diffusion_pilot.yaml` is restored from the inactive document at `712ba18568548adc73013818630c4e4101417a9a`. The working-tree authorisation binds no GPU, output directory, biological path, or executable authorisation.

### Attempt 4

On 5 October 2026 the single-use authorisation `m6_d1_diffusion_pilot_7387bb2e5f75_gpu0_attempt4` was consumed. The evidence directory is `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_7387bb2e5f75_gpu0_attempt4`. It is immutable failed engineering evidence. `authorization_failure.json` is 660 bytes and its SHA-256 is `10896972516ca7e9781e0b3d1af2a214529b65692212ee3d3a8de4009209ab79`. `authorization_consumption.json` is 560 bytes and its SHA-256 is `4d2e962f104cbcc55bba79fbb0726ef36f918d4ca887d3d32f7e832a6971b04e`. `m6_pilot_manifest.json` is absent. No checkpoints are present. Completion is `consumed_failed`. `scientific_run_completed` is false, `pilot_completed` is false, and `retained_checkpoints_exist` is false. The failure code is `identity_mismatch`. The failure detail is `logical device is not cuda:0`. The recorded stage is `model_load`. Update and microbatch are null. `authorization_commit` is `2262ba5840f92451a273ab766af3573fffa8382e`. `authorization_parent_commit` and `executing_implementation_commit` are `7387bb2e5f7510508f3b87b4ac228ef341b1b39b`.

Model loading and `Accelerator.prepare` were reached. The failure is raised by the logical-device check immediately after `prepare`, before EncDec placement and before the optimizer-update loop. No optimizer update, checkpoint, success manifest, or scientific result exists. The directory was not altered by this remediation. Attempt 4 is not a successful pilot and does not authorise another run.

Installed Accelerate 0.25 `PartialState.default_device` returns `torch.device("cuda")` when CUDA is available, and `PartialState.device` is assigned from that value. `Accelerator.device` returns `self.state.device`. `str(torch.device("cuda"))` is `cuda`, its type is `cuda`, and its index is `None`. `str(torch.device("cuda", 0))` is `cuda:0`. The runner compared `str(accelerator.device)` directly with `cuda:0`, so the unindexed Accelerate device failed closed at `model_load`.

`assert_prepared_runtime` still requires exactly one Accelerate process and exactly one visible CUDA device. It then normalizes `accelerator.device` with the supplied torch module. The device type must be `cuda`. An explicit index must be 0. An index of `None` is resolved with `torch.cuda.current_device()` and must be 0. The normalized object is `torch.device("cuda", 0)`, and that object is what the worker passes to placement and to the training and validation workflow. A malformed device, a CPU device, explicit `cuda:1`, an unindexed CUDA device whose current index is not 0, and a failure while resolving the current device are `identity_mismatch`. Physical GPU UUID, PCI, `CUDA_VISIBLE_DEVICES`, device count, process count, FP32, and accumulation checks are unchanged. The authorization and manifest logical device remains the string `cuda:0`. Accelerate and RNAGenesis are not modified. `config/experiments/D1_diffusion_pilot.yaml` is restored from the inactive document at `7387bb2e5f7510508f3b87b4ac228ef341b1b39b`. The working-tree authorisation binds no GPU, output directory, biological path, or executable authorisation.

There is no numeric catastrophic-validation cutoff. Every finite update-7, update-14, and update-21 aggregate is recorded relative to update 0. Finite worsening is a human-review signal. It does not stop the 21-update run and it does not change the learning rate.

The approved generated-sample guardrails remain valid nonempty A/C/G/U fraction at least 0.99, empty or unparseable fraction at most 0.01, unique fraction at least 0.95, exact TRAIN match rate at most 0.01, and largest duplicate share at most 0.01. They apply only after separately authorised diagnostic generation. A failure makes the checkpoint ineligible for M7. It does not trigger an automatic rerun or an automatic learning-rate fallback. Nearest-TRAIN similarity stays report-only.

## 6. Output normalisation

Future M6 diagnostics, when separately authorised, use the B1 `generation.py` invocation contract: numeric `bos_token=1`, numeric `eos_token=2`, and the accepted paired schedule `0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0`. This stage does not generate and does not open generated output.

`normalize_generated_output` is a pure helper. It always retains the raw string. It requires an exact leading prefix `11`, removes exactly that prefix, and accepts the body only when it is nonempty and matches `^[ACGU]+$`. It does not uppercase, trim biological characters, convert T to U, truncate, pad, resample, or remove a suffix. Any other leading marker, any trailing `1` or `2`, and any other unexpected character fail closed. The record stores the raw string, the removed prefix, the normalised string, both lengths, and the failure reason.

M5's single leading `1` came from direct `EncDec.generate` defaults. That observation does not broaden this rule. The helper does not call `scripts/clean_generated_sequences.py`.

## 7. Authorisation and the real worker

A later authorisation-only commit may change `document_status`, `consumable_by_executable_workflow`, the execution grant, and `pilot_execution_authorisation`. It may not change the pilot decisions, the pinned hashes, or the Python files. Live HEAD must have exactly one parent, and that parent must be the executing implementation commit stored in the document. The runner, contract, and tests must match the SHA-256 values recorded for that parent. MRes must be clean, including untracked files. RNAGenesis tracked state and index must be clean. Its accepted untracked asset trees remain in place.

The active block binds one physical GPU index, UUID, and PCI bus, logical `cuda:0`, the exact `CUDA_VISIBLE_DEVICES` value, and one new output directory that is a direct child of `/home/laura/rnagenesis-mres-runs`. It also binds the TRAIN, VALIDATION, validation-artifact, and B1 identities. Permitted roles are TRAIN, VALIDATION, the stored validation artifacts, B1 initialisation, and the frozen EncDec. REF and EVAL are not permitted. The session pattern is the M5 single-use timestamp and scope. M5 did not define a wall-clock expiry, so `wall_clock_expiry` stays null. Consumption happens when the bound directory is created. There is no resume.

RNAGenesis acceptance reuses the M5 reviewed untracked-directory fingerprint and the M5 rejection of unexpected untracked source and configuration files. Untracked content under `models/` is not accepted as a class. Before any biological file is opened, the worker observes every required model and environment asset as a regular non-symlink file and checks the accepted byte size and streamed SHA-256. That set is the M5 `REQUIRED_MODEL_FILES` inventory plus the patched Diffusers normalization file: B1 pipeline index, scheduler, UNet config, and UNet weights; EncDec config and weights; biomap config; decoder config; tokenizer; and `normalization.py`. The executable must be `/home/laura/miniconda3/envs/rnagenesis-h200/bin/python`. The observed versions must be Python `3.8.13`, torch `2.1.2+cu121` from the live module attribute, diffusers `0.25.0`, accelerate `0.25.0`, and transformers `4.36.2`. Package metadata that drops the torch `+cu121` suffix does not satisfy the check. A mismatch fails closed before biological access. The production manifest stores those measured hashes, sizes, paths, the executable, and the module versions. Expected pins remain in expected fields.

The production parent launches that worker with `cwd` set to `/home/laura/RNAGenesis`. The production worker resolves its working directory and requires it to be that pinned root before the training-stack import. It does not change directory to compensate. Runner, configuration, Git, biological, artifact, checkpoint, and evidence paths remain absolute. Cache environment variables remain under the consumed directory.

The authorised worker composes the tracked RNAGenesis functions at `e3b855b`: the TRAIN and VALIDATION readers, `load_tokenizer`, `collate_sequences`, `SequenceIndexDataset`, `load_frozen_encdec`, `load_b1_denoiser`, `load_scheduler`, `build_adamw`, `extract_latents`, `sample_train_diffusion`, `denoising_mse`, and `save_diffusers_checkpoint`. Fresh reload uses `TransformerDenoiser.from_pretrained` on the saved directory. It does not call `load_b1_denoiser` for that reload, because that helper refuses every path except immutable B1. Fixed validation draws come from `load_verified_artifacts`, loaded from the absolute tracked path `scripts/modelling/build_validation_artifacts.py`. The worker does not call the artifact builder or `build_fixed_validation_draws`. `PinnedTrainingStack` passes a `pathlib.Path` into `read_train_sequences`, `read_validation_cores`, `load_frozen_encdec`, `load_b1_denoiser`, `load_scheduler`, and `save_diffusers_checkpoint`, and into `TransformerDenoiser.from_pretrained` on reload. `load_verified_artifacts` keeps its own `Path(directory)` conversion.

After `Accelerator.prepare`, the worker requires exactly one process, exactly one visible CUDA device, logical device `cuda:0`, `gradient_accumulation_steps == 1`, and `mixed_precision == "no"`. Accelerate 0.25 represents that single visible CUDA device as `torch.device("cuda")`, whose index is `None`. The worker accepts that object when `torch.cuda.current_device()` is 0, and it accepts an explicit index only when the index is 0. The device passed into the training and validation workflow is the normalized `torch.device("cuda", 0)`. The stored authorization and manifest value remains the string `cuda:0`. Every floating denoiser parameter and every floating persistent buffer must be float32. The prepared denoiser is placed in training mode before the optimizer-update loop. Fixed-draw validation receives that same prepared object, runs it in evaluation mode inside `torch.no_grad()` and without autocast, and then restores the previous training or evaluation state. Latent, noise, prediction, target, and MSE stay float32. Timesteps stay int64.

EncDec evidence covers parameters and persistent buffers. The M5 rotary runtime caches `_cos_cached`, `_sin_cached`, and `_seq_len_cached` are excluded from the persistent-buffer digest. Parameter and persistent-buffer digests are recorded at initialization and after updates 7, 14, and 21, and those four digests of each kind must be equal. A denoiser buffer digest is not EncDec evidence. Live identities must show that every EncDec parameter has `requires_grad == false`, that EncDec stays in evaluation mode, that no EncDec parameter or buffer is in the optimizer, and that the optimizer contains exactly the trainable denoiser parameters.

CUDA synchronization brackets each timed GPU region. The manifest records one synchronized wall time for each of the 21 training updates and one synchronized validation time at updates 0, 7, 14, and 21. Aggregate training-update time is the sum of the 21 update durations. Aggregate validation time is the sum of the four validation durations.

Before a reader opens an input, the path is resolved, symlink components and non-regular files are rejected, and the streamed SHA-256, byte size, and count are returned with the loaded object. Those returned records are the manifest observations. Each physical validation-artifact file, including `validation_draw_manifest_sha256.json`, is hashed the same way. The logical sequence-order hash is read from the loaded artifact manifest. The hash-report file is pinned to `bc6c7587e4a22892d84d1e901939bf988304957da778d49afb00cdea552ea075`. Each optimizer update records one denoiser element that had a finite nonzero gradient and a changed value. Retained checkpoints are exclusive children of the bound output directory. Their names follow the checked-in pattern `D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-42__update-<count>__git-<sha>`, and `<sha>` is the executing implementation commit. Configuration comparison ignores only top-level `_name_or_path`.

Python, torch CPU, and torch CUDA global streams are seeded and digested. The TRAIN permutation and the diffusion timestep/noise draws use two dedicated CPU generators, both seeded with 42, which is the tracked RNAGenesis convention. Their manifest fields are separate. Validation noise is not drawn again. The pilot code does not call NumPy. The pinned artifact loader does use `numpy.frombuffer` to reconstruct stored tensors, and the manifest records that fact. An interruption after the output directory exists is a consumed failure. Restart needs a new authorisation and a new directory.

## 8. Manifest

Schema version `m6-pilot-manifest-1`. Canonical JSON sorts keys, uses compact separators, and ends with one LF. Validation is by exact key set. A missing key and an unexpected key are both rejected. The training manifest must not contain sequence text.

Top-level keys, in canonical order:

```text
applied_learning_rate_trace
authorisation
b1_identity
completion_state
config_version
data_roles
denoiser_update_evidence
deviations
diagnostic_generation_status
environment
experiment_id
failure_state
frozen_state
gpu
manifest_schema_version
memory
microbatch_accounting
optimizer
post_update_21_scheduler_position
production_identities
ref_eval_access
repository
restart_policy
resume_supported
rng
run_id
schema_version
stop_conditions
timing
train_update_observations
validation_artifacts
validation_observations
validation_review
warnings
weight_checkpoints
```

`diagnostic_generation_status` on this package is `not_performed_requires_separate_authorisation`. `resume_supported` is false. Peak allocated bytes and peak reserved bytes are separate fields. A success manifest is written only after the full control flow succeeds. A failure record does not accompany a success manifest.

`validate_success_manifest` accepts only `synthetic_control_flow_completed`. `validate_production_success_manifest` accepts only `pilot_completed` with `production_identities: true`. It checks every top-level section and every exact nested key: schema and experiment identity; observed B1 and EncDec asset identity; runtime executable, module versions including torch `2.1.2+cu121`, patch identity, offline controls, and cache isolation; microbatch and final-window accounting; AdamW hyperparameters, FP32, EMA and raw-weight policy, clipping, and the learning-rate trace; denoiser-update evidence; validation-artifact identity, including the hash-report file and the logical sequence-order hash, and tensor shapes; validation timing and pair counts; the no-auto-stop and no-auto-retune review policy; restart and no-resume policy; checkpoint inventory and reload proof; frozen EncDec parameter and persistent-buffer digests; closed REF and EVAL; repository, GPU, authorisation, and consumption identity; and every stop condition. Observed file hashes use `streamed_sha256`. Observed runtime versions use `module_attribute`. A synthetic manifest, or a manifest that labels an expected constant as an observation, does not pass. A failure after consumption writes `authorization_failure.json`. That record names the authorisation and implementation commits when they have been validated, the latest stage, the update or microbatch when the failure has reached one, the failure code, the fired stop condition, the non-resumable state, and whether retained checkpoints already exist. An ordinary exception records `incomplete_evidence_or_manifest` and the controlled detail `authorized worker failed; exception_class=<ClassName>`. It does not record the exception message or a traceback file. A precise `M6PilotError` keeps its own code, detail, and context. An existing child failure record remains the parent's record. A claimed success manifest is removed when the failure is recorded. The record does not claim pilot completion and it does not contain sequence text. `STOP_CONDITION_CODES` is the authoritative registry of stops reachable on the active launch and worker path, including authorisation, provenance, schedule, microbatch, validation-schedule, and prohibited automatic learning-rate changes. A success manifest records every registered condition with `fired: false`. A failure record's `fired_stop_condition` must be one of those codes. `cli_argument_rejected` and `environment_injection_rejected` are the only exclusions: they are raised by the inactive CLI and the pre-consumption entry gate, before a bound directory exists. The production validator also rejects contradictory nested evidence. Update 0 has `relative_to_update_0: null`. Updates 7, 14, and 21 use the review-item schema. `initial`, `later`, and `delta` are finite decimal strings consistent with the recorded aggregate MSE. `finite_worsening` and `human_review_signal` equal `later > initial`. Automatic stop, automatic learning-rate change, and the numeric cutoff keep their approved values. `validation_review.observations` match the corresponding relative records. Checkpoint configuration and state digests are SHA-256. Raw and normalized equality flags match those digests, `configuration_compatible` matches normalized equality, and the ordered entry-digest aggregate and parameter-name digest are recomputed from `entry_digests`.

## 9. Estimates

These figures are planning arithmetic. This implementation did not run a GPU step and did not write a checkpoint.

The accepted B1 weight file is 7,847,725,416 bytes. Three retained raw denoiser checkpoints are `3 × 7,847,725,416 = 23,543,176,248` bytes, or 23.543 GB in decimal units. Update 0 is a reference, not a fourth copy.

The M0 parameter count is 1,911,589,344. AdamW moments, if they were saved, would be two FP32 tensors per parameter: `2 × 1,911,589,344 × 4 = 15,292,714,752` bytes per checkpoint. Three moment files would be 45,878,144,256 bytes. Weights plus moments would be 69,421,320,504 bytes, about 69.42 GB. That is the roughly 69 GB figure this pilot avoids. Moments are estimated for parameters only. The 50,331,648 registered buffers are in the weight file, whose 41,448-byte safetensors header accounts for `7,847,725,416 - 1,961,920,992 × 4`.

The retained planning range is about 24–26 GB: 23.543 GB of weights plus Diffusers JSON members, hash sidecars, the manifest, and logs. It assumes no optimizer sidecar and no generated-sequence corpus.

The closest FP32 microbatch-8 memory observation remains the accepted M5 smoke: training peak allocated 42,046,809,088 bytes and training peak reserved 42,563,796,992 bytes. M6 uses the same microbatch and precision, so that pair is the planning memory band. M5 did not encode the 669 biological lengths or run the 380-pair validation, so the band is not a new measurement.

M5 wall time was 193.7824976965785 seconds and included asset load, four backward microsteps, checkpoint I/O, resume, and a tiny generation. It is not a per-step biological measurement. A future exclusive H200 allowance of 1–3 hours is a wide planning band for 84 denoiser backward microbatches, four validation passes of 380 pair forwards each, and three writes of the 7.85 GB weight file. It is not a benchmark.

## 10. What remains closed

This status is `M6_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED`. It is not `M6_IMPLEMENTED_NOT_AUTHORISED`. The checked-in YAML is the inactive, non-consumable document from `7387bb2e5f7510508f3b87b4ac228ef341b1b39b`. Attempt 1 consumed the earlier GPU 1 single-use authorisation and remains a failed engineering attempt. Attempt 2 consumed the earlier GPU 0 single-use authorisation and remains a failed engineering attempt. Attempt 3 consumed the GPU 0 single-use authorisation at `4dd7f2c600322bf8134f57c491d10d08d86c3640` and remains a failed engineering attempt. Attempt 4 consumed the GPU 0 single-use authorisation at `2262ba5840f92451a273ab766af3573fffa8382e` and remains a failed engineering attempt. This package does not authorise attempt 5, biological access, GPU use, REF, EVAL, or diagnostic generation. Reusable code does not hard-code physical GPU 0 or physical GPU 1. The active schema accepts the index named by a future authorisation and checks the live probe against that binding.
