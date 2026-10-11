# M8 raw generation

**Configuration status: `M8_RAW_GENERATION_READY_FOR_REVIEW_NOT_AUTHORISED`.**

**Milestone status, 10 October 2026: raw generation and assembly are complete.** Later four-condition evaluation is required and is not authorised by this closure. The completion and handoff record is section 8. Sections 1 to 7 remain the inactive contract.

The checked-in configuration cannot execute. `authorisation_entries` and `assembly_authorisation_entries` are empty, and every execution flag is false. The former GPU 1 authorisation `m8_d1_seed44_block_b_ac371ba_gpu1_attempt1` is recorded only as a non-executable retirement: unconsumed, not launched, and superseded before dispatch because the exclusive-GPU availability gate was no longer satisfied. Its historical commit `e645925478e0110504f4dd8ce473a1a3be82d677` and the refusal archive are preserved and are not rewritten. The inactive configuration contains no GPU 0 authorisation. No active authority is inferred from an M7 file.

Base identities pinned by the proposal:

- MRes `main` at `d0f9a397b536c64ca1b22662cc9ae36aea0101f6`
- RNAGenesis `mres-d1-diffusion-finetune` at `e3b855bbf4d1af376f43747643fa30afd662828c`
- selected-set SHA-256 `af0c0e555a8b878feadeb17fcbde18d8b780819a42d9e0cc547d2fc0c6895f8f`
- final-selection manifest SHA-256 `49b218e3df74825e1931148e2f65b25aae057c822e2ab32d44c2960b1587c91c`

## 1. What M8 produces

M8 produces and seals raw pools only.

- B1: exactly 30,000 raw attempts from the generic released checkpoint.
- D1: exactly 30,000 raw attempts, 15,000 from selected training seed 43 and 15,000 from selected training seed 44.
- The M4 and M7 1,000-attempt pools are excluded.

Parsing, filtering, clustering, representation analysis, and the four-condition comparison occur later under a common frozen evaluation protocol. M8 does not perform them.

Two D1 training seeds are the approved final set. The absent third seed is a resource and time limitation. The one-seed M8 alternative is historical and is not executable, because both final seeds completed.

Fixed raw-attempt accounting supersedes rejection and resampling language. There is no parsing-based exclusion, validity filtering, replenishment, rejection sampling, replacement, deduplication, truncation, padding, or dropping. No cleaner-derived validity or acceptance classification is performed.

Exact raw bytes remain authoritative in the retained, hashed raw invocation files. `raw_decoded_text` is the deterministic UTF-8-else-Latin-1 decoded representation stored in canonical JSON. Assembly verifies that representation against the retained raw bytes. It is not a second source of authority and it is not a cleaned sequence.

## 2. Sampler

Every invocation uses unchanged RNAGenesis `generation.py`.

- DDIM steps 50, `eta=0`, `top_p=0.95`, `top_k=0`
- sampling enabled, guidance disabled
- raw weights, frozen EncDec
- `max_seq_len = requested_biological_length + 1`
- `--truncate` is forbidden

## 3. Schedule

The length vector is the accepted 669-length file whose SHA-256 is `7e6cb523a85116fc38788c336ef50c26e0eccc343712aaea89956a73c485bd3c`. Quotas use deterministic largest remainder. The numerator is `30000 * empirical_count`. The floor is integer division by 669. The remainder is the modulus 669. Remaining seats go to the largest remainders. An exact tie goes to the smaller biological length.

Every quota splits into blocks A and B. Even quotas split equally. Odd strata are visited in ascending length, and the extra attempt alternates A, B, A, B, starting with A. Each block totals exactly 15,000. Within each length the difference is at most one. Requested nucleotide totals are 830,348 for block A and 830,404 for block B.

For each requested length, one invocation uses `batch_size=16` and `batch_num=floor(block_count/16)`. A nonzero remainder is a separate invocation with `batch_size=remainder` and `batch_num=1`. A zero-batch invocation is not created, and a remainder is not padded. Block A has 163 invocations. Block B has 164.

Block A generation seeds are `800000 + block invocation index`, so `800000` through `800162`. Block B generation seeds are `900000 + block invocation index`, so `900000` through `900163`.

B1 block A and D1 seed 43 use identical requested lengths, invocation shapes, seeds, and invocation order. B1 block B and D1 seed 44 use the same pairing. Generation seeds are unique between invocations within a block and are intentionally reused across each paired B1/D1 arm.

These attempts are generated draws, not independent model-training replicates. D1 has only two training replicates, seed 43 and seed 44. The training seed is tied to the technical block. The block length allocations are extremely close and are not identical: 830,348 nt in block A and 830,404 nt in block B. Later evaluation must not treat 30,000 attempts as 30,000 independent model replicates. The absent third training seed is a resource and time limitation.

The master attempt map has exactly 30,000 rows, indexes `0` through `29999`, ordered by requested length ascending, then block A stratum positions, then block B stratum positions.

Canonical schedule hashes:

| Document | SHA-256 |
| --- | --- |
| source length vector | `7e6cb523a85116fc38788c336ef50c26e0eccc343712aaea89956a73c485bd3c` |
| empirical histogram | `dc599c637dafa455447551a78b0234c818262d82a86989cc863e09136abcaee3` |
| quota allocation | `d477d1ffc1d8f3df6f9124b0c613e3beb8891ffa8100b6a5744ac8f9d51aa721` |
| master attempt map | `a99ac979d430c2145f47f696822ec6cc06627142032aaf2f9c5766ffa1cdc14a` |
| block A invocation schedule | `491c47d8df603e6b9277464611ba27da94dc15134b5e8b2290d91962c45cd13e` |
| block B invocation schedule | `7b66e5f79f5ce9bb44a896371715c707b7093883e40b8adf5963abf49e135b8f` |

`scripts/modelling/m8_schedule.py` is pure. It does not import a model, touch a GPU, read a biological sequence, or write a run directory. It does not call `sample_target_lengths`.

## 4. Arms

Each generation arm has its own single-use authorisation and immutable output directory:

- B1 block A
- B1 block B
- D1 seed 43 block A
- D1 seed 44 block B

A future active entry describes exactly one arm. The inactive CLI exposes help, schema inspection, and one `--authorisation-id` entry. While the configuration is inactive, that entry refuses before any environmental, Git, GPU, checkpoint, biological, run-root, or output inspection.

A consumed failure is never resumed or overwritten. A retry requires a new id, a new authorisation, and a new directory.

D1 inspects and hashes all four selected-checkpoint members before generation and after the final raw-output verification. The observations must equal the sealed expected member hashes and must equal each other. Checkpoint members are not copied or rewritten. B1 uses the same immutable-asset check for the accepted generic diffusion and EncDec pins. Every raw invocation file is re-read and hashed, and its bytes must not change before the manifest is completed.

Checkpoint evidence remains retained through at least 1 November 2026. Deletion is not implemented.

## 5. What is refused

M8 refuses:

- an M7 configuration path
- an M7 schema version
- an `m7_` authorisation id
- the live seed-44 M7 authorisation `m7_d1_final_replicate_seed44_2cb1b6a26391_gpu1_attempt1` as M8 authority

REF, EVAL, VALIDATION, and TRAIN sequence data, the evaluation worktree, and unrelated run evidence are prohibited. Sealed M7 manifests are never rewritten. M7 completion is the human closure documentation. The live `D1_final_replicates.yaml` is historical M7 state and is not M8 authority.

## 6. Assembly

Assembly is CPU-only and has its own inactive authorisation. Generation files do not make it runnable.

For B1 and for D1 separately, assembly accepts exactly the two sealed block manifests. Each source path must be the arm manifest `m8_arm_manifest.json` in a normalised direct child of `/home/laura/rnagenesis-mres-runs`. An arbitrary source path does not authorise its own parent. The arm manifest, the raw ledger, and every referenced raw file must be a normalised regular file with link count one. Signatures are compared before and after each read. Byte counts and SHA-256 values are enforced. Missing, duplicate, and extra invocation references are rejected.

Assembly recomputes the pinned schedule and checks every record against it: condition and technical block, the D1 seed-to-block mapping, checkpoint identity, master attempt index, deterministic record id, requested length and `max_seq_len`, invocation index and generation seed, batch number, within-batch position and line index, source raw-file path and hash, and the arm-level authorisation and run ids. It also checks the arm manifest schema, asset before/after equality, repository provenance, and the invocation ledger. All 30,000 records are preserved. Assembly does not parse, clean, filter, classify, or deduplicate them.

The public assembly launcher computes SHA-256 over the exact YAML bytes it parsed and passes that digest into assembly. Consumption, failure, and success records store it as `active_configuration_raw_sha256`, separately from the canonical projected `active_configuration_sha256`. The production assembly path refuses a missing raw digest. It does not copy the semantic digest into the raw-digest field.

The combined manifest binds its own authorisation and provenance, the two source paths, byte counts, hashes, and run ids, the combined ledger byte count and hash, timestamps, and the unchanged declarations that parsing, filtering, cleaning, deduplication, replacement, and metric computation were not performed. `repository_identity.mres_commit` is the live authorization commit. `proposal_base_commit` retains `d0f9a397b536c64ca1b22662cc9ae36aea0101f6` and is not recorded as the observed runtime commit.

Assembly rejects a sealed arm whose nested fields contradict the schedule or the pins. That includes sampler settings, sequence-access denials, model-asset kind and checkpoint identity, the exact before/after B1 or D1 asset inventories, `raw_output_hashes` against the invocation ledger in invocation order, both the arm and paired-block schedule hashes, environment and controller/child interpreter observations, library-path and offline and fixed-PATH claims, GPU identity, the sharing-policy evidence described below, numeric free-versus-total and free-versus-threshold relationships, the storage run root and its threshold, timestamps and a nonnegative elapsed duration, and the authorisation and run ids against the direct-child source directory. Existing record-to-schedule and raw-byte checks remain. Each D1 arm must carry `selected_set_evidence` for the approved manifest path, its byte count and SHA-256, the selected-set SHA-256, the block's training seed, checkpoint name, epoch 5, update 105, and member hashes. B1 carries `selected_set_evidence: {applicable: false}`. Assembly checks the D1 block against that selected checkpoint. A source directory, arm manifest, or raw file with a symlinked ancestor is refused, and a raw file must resolve inside its bound arm directory.

Assembly has the same single-use lifecycle as generation: validate inputs, consume a new directory once, write a consumption record before output evidence, never overwrite or resume, and write a safe failure record if failure occurs after consumption. A retry requires a new id, a new authorisation, and a new directory.

## 7. Execution boundary

No M8 execution is authorised. This document does not create a run directory, load a model, open a biological sequence, or launch `generation.py`. Setting `document_status` to an active value and `consumable_by_executable_workflow: true` is not sufficient. Active generation and active assembly have separate exact validators. Each requires the complete shared scientific contract, the execution flags for that role, exactly one entry of that role, an empty list for the other role, and no unknown or missing field. Active assembly authorises no GPU.

A future active entry does not require live MRes HEAD to equal the proposal base `d0f9a397b536c64ca1b22662cc9ae36aea0101f6`. It binds `authorization_parent_commit`, `executing_implementation_commit`, the hashes of `m8_schedule.py`, `m8_generation.py`, and `m8_assemble.py`, and the active configuration identity. At launch, MRes must be clean `main`, live HEAD must be the authorization commit and must have exactly that parent, and `origin/main` must equal live HEAD. Every commit after the executing implementation commit is observed. The range must be linear, must contain no merge commit, and every change in that range must be confined to `config/experiments/M8_raw_generation.yaml`. An intervening commit that changes an executable or policy module is refused even when the latest commit changes only the M8 YAML. Those three implementation files must match the bound hashes in both the implementation commit and the working tree. Launch does not import `m6_pilot_contract.py`; the RNAGenesis clean-tree and reviewed-untracked policy is implemented locally in `m8_generation.py`. RNAGenesis branch, commit, and tracked-tree state stay pinned. Successive one-entry authorization commits can authorise the four arms and the later assemblies without modifying implementation code. The checked-in proposal remains inactive and contains no such commit.

A future generation entry also binds the interpreter `/home/laura/miniconda3/envs/rnagenesis-h200/bin/python`, resolved to `/home/laura/miniconda3/envs/rnagenesis-h200/bin/python3.8`, SHA-256 `058a393acc1b0ee5d0564a6dca1e36f6602b4686b369ad957eca2b359d145059`, and the accepted library versions. The production controller observation inspects the running process: `sys.executable`, its resolved path, the Linux `/proc/self/exe` target where that link exists, the executable SHA-256, and the Python version. Before authorisation consumption, a minimal subprocess probe of the bound child interpreter, with a restricted environment, must return the interpreter path, resolved executable, executable hash, and Python version. That probe does not import the model stack, inspect biological data, query CUDA, or create the run directory. Controller and child observations are recorded separately. A controller or child that reports another executable or hash is refused before the output directory is created. `LD_LIBRARY_PATH` is an explicit nullable binding. This inactive proposal does not choose a value. When a future entry binds one, the live parent value and the child value must match it exactly.

Generation performs one GPU and storage probe during pre-consumption validation, before output creation and model generation. Checkpoint and asset verification may occur after that observation and before the output directory is consumed. The probe is not repeated after asset verification. The arm manifest records that single observation: the physical GPU index, UUID, PCI bus identity, logical mapping to `cuda:0`, total, used, and free GPU memory, the entry's minimum free-memory threshold, the observation timestamp, the compute-app snapshot and its SHA-256, and free filesystem bytes at the canonical run root against the entry's minimum free-space threshold. A saved snapshot is not launch authority. This contract does not add a second probe. Exact UUID, PCI identity, and physical index must match. The child stays bound with `CUDA_VISIBLE_DEVICES` set to that physical index and `CUDA_DEVICE_ORDER=PCI_BUS_ID`.

`gpu_sharing_policy` is required on every active generation entry. The only values are `exclusive` and `shared_allowed`. A missing key fails the entry schema. An unknown value is rejected. Neither absence nor an unknown value enables sharing.

`exclusive` is the default contract for a new entry that names it, and it is the only reading of a historical `m8-arm-manifest-1` arm. It requires zero pre-existing compute applications on the selected physical GPU. The count is the number of ordinary `nvidia-smi` compute-app rows whose GPU UUID is the authorised GPU and whose PID is a positive decimal integer, with no sign and no leading zero. A selected-GPU row whose PID is empty, non-decimal, zero, negative, `[N/A]`, or `[Not Found]` is malformed or indeterminate GPU evidence and is refused. An indeterminate row that belongs only to another GPU does not increment the selected-GPU count and does not by itself prevent use of the selected GPU. Processes on another GPU are not disturbed. The launch does not kill, signal, pause, move, or otherwise inspect or alter another process. Historical B1 and D1 seed-43 manifests stay valid without rewriting: they have no sharing-policy field, they record `compute_processes: 0`, and assembly accepts that exact historical block as exclusive. A historical manifest with a positive count, or a historical block that has been relabelled with new sharing fields, is refused.

`shared_allowed` permits a positive pre-existing count only when the active entry names that policy. Identity, the free-memory threshold, the storage threshold, and every repository, interpreter, configuration, asset, checkpoint, and selected-set check still apply. The arm manifest records the policy, whether pre-existing compute applications were observed, the observed count, the full compute-app snapshot and its SHA-256, the observation timestamp, and the selected GPU's index, UUID, PCI identity, total memory, used memory, free memory, and required free-memory threshold. Those pre-existing processes are not generated-model processes. Production launch validation and assembly validation apply the same selected-GPU PID rule through the shared evidence validator. The launch does not terminate, signal, pause, move, inspect, or alter any other process. Malformed, missing, inconsistent, falsely labelled, or indeterminate selected-GPU process evidence is refused in both the launch gate and assembly. Shared mode still rejects the wrong GPU, insufficient free memory, and insufficient storage.

The free-memory threshold is an authorisation-level value. It is not a global hard-coded constant and it is not a memory reservation. GPU identity, processes, memory, and storage are observed once during pre-consumption validation, before output creation and model generation. That observation is not repeated after asset verification. Checkpoint and asset verification may occur between the observation and output-directory consumption. Concurrent workloads may grow after the observation. The threshold is a point-in-time safety gate, not a reservation or a guarantee that memory will remain free. The manifest records that single observation. For a later shared-GPU authorisation on physical GPU 0, the recommended threshold is 30 GiB, exactly 32212254720 bytes. Completed M8 generation used approximately 11.7 GiB, so 30 GiB is more than 2.5 times that observation and remains practical on a shared server. The inactive configuration contains no GPU 0 authorisation. The consumed shared-GPU seed-44 arm is recorded in section 8. The 30 GiB figure does not change the scientific sampling contract.

Shared execution is an operational and resource-management deviation. It does not change sampling, checkpoint selection, the 15,000-attempt block-B schedule, generation seeds 900000–900163, or evaluation criteria. It may change wall-clock runtime and it raises interruption and resource-contention risk. It does not by itself justify a biological or model-quality conclusion.

Active-document validation does not touch the filesystem. Before GPU probing or authorisation consumption, production preflight requires `/home/laura/rnagenesis-mres-runs` to be the exact resolved run root, a real directory, and not a symlink. The proposed output must be a non-existing direct child, and its resolved parent must not fall inside MRes, RNAGenesis, or the evaluation worktree. The sealed selection manifest, D1 checkpoint directories and members, and B1 asset ancestry must have no symlinked ancestor. Generation and assembly output directories must be normalised direct children of exactly `/home/laura/rnagenesis-mres-runs`. An authorised D1 preflight reopens the sealed final-selection manifest by its approved path, byte count, and SHA-256, checks the selected-set identity, and requires the requested seed, checkpoint, epoch 5, update 105, and member hashes to be one of the two human-approved selections. It does not rewrite that manifest. The successful result is stored on the D1 arm as `selected_set_evidence`. B1 stores the explicit not-applicable record. The D1 checkpoint directory must contain exactly the four expected regular single-link members. Those members are streamed before and after generation and are not copied. After consumption and before the first generation subprocess, every bound isolated home, `TMPDIR`, cache, and pycache directory is created inside the consumed output and must not be a symlink. `TMPDIR` must exist so Python cannot fall back to a shared system directory.

Evidence writes loop until every byte is written, fsync the file, rename atomically, fsync the directory, and remove the temporary file on every exception, including interruption. A generation failure record stores the failing invocation index and the number of completed invocations. It does not store sequence text, stderr, credentials, or an uncontrolled third-party exception.

The runtime estimate was a planning assumption: approximately 6.4–10.4 GPU-hours for all four arms, with a practical 12–16 hour reservation including verification and overhead. The measured generation times are in section 8. Checkpoint weights were not copied. Expected M8 evidence storage is modest. The free-space reading used at launch is the filesystem half of that same single observation.

## 8. Completion and evaluation handoff

**Date: 10 October 2026.** This section records completed M8 generation and CPU assembly. It restores no authorisation. The checked-in configuration stays `M8_RAW_GENERATION_READY_FOR_REVIEW_NOT_AUTHORISED`, with empty `authorisation_entries` and `assembly_authorisation_entries`, `consumable_by_executable_workflow: false`, and every execution flag false. `closure.execution_authorised` and `closure.m8_execution_authorised` are false. `closure.filtering_performed`, `closure.cleaner_invoked`, and `closure.replacement_or_replenishment_performed` stay false. `closure.later_evaluation_required` stays true. The retired GPU 1 record and the immutable scientific pins are unchanged. Sealed run manifests, ledgers, consumption records, and checkpoint weights are not rewritten.

Proposal-base identity remains MRes `main` at `d0f9a397b536c64ca1b22662cc9ae36aea0101f6` and RNAGenesis `mres-d1-diffusion-finetune` at `e3b855bbf4d1af376f43747643fa30afd662828c`. Each sealed manifest stores its own authorization commit in `repository_identity.mres_commit` and keeps `proposal_base_commit` as `d0f9a397b536c64ca1b22662cc9ae36aea0101f6`.

### 8.1 Arms

Each arm attempted 15,000 raw draws. Each arm manifest records `filtering_performed: false`, `cleaner_invoked: false`, `replacement_or_replenishment_performed: false`, and `later_evaluation_required: true`. Parsing, classification, and deduplication flags are assembly-manifest fields, not arm-manifest fields. Evidence is retained through at least 1 November 2026. Deletion is not implemented.

| Arm | Directory | Manifest SHA-256 | Raw ledger SHA-256 | Elapsed seconds |
| --- | --- | --- | --- | --- |
| B1 block A | `/home/laura/rnagenesis-mres-runs/m8_b1_block_a_ac371ba_gpu1_attempt1` | `bb788e862d6a7c41e8b942d53e8121d2d19722574d4956b4c2c2644f392931b9` | `5e9c00664fce3a423e8c89aad43f32fcf1d1db59b8639561eff436e6fdba7d82` | 8348.671256661415 |
| B1 block B | `/home/laura/rnagenesis-mres-runs/m8_b1_block_b_ac371ba_gpu1_attempt1` | `d51be51bbf10a90ca7ff809403f38007167a7cdd72704473a0dd39a2bb8510e7` | `11003ba60bf191ee841ae55a7dd81f0d78d731c96855f28f564b53da4b353e61` | 8369.749910581857 |
| D1 training seed 43, block A | `/home/laura/rnagenesis-mres-runs/m8_d1_seed43_block_a_ac371ba_gpu1_attempt1` | `a0fde7024662ee13837e6f99b163711263b60d55fa6c60b8012db53f93873e52` | `d0d16afe63f767179c8e7af261095af709ce6298cfe64673600cf04965d87473` | 8451.951393645257 |
| D1 training seed 44, block B | `/home/laura/rnagenesis-mres-runs/m8_d1_seed44_block_b_1069b63_gpu0_shared_attempt1` | `f38aebd53e08c9012af5c4faa8a51a07ca39538dd1ccfcd26d003719b6ea5ca3` | `d007b8d8a2cfed49104be90100059a9f2fdf8ffee86933d5d68b26ba7245920b` | 8381.193621516228 |

B1 block A. Authorisation `m8_b1_block_a_ac371ba_gpu1_attempt1`. Authorization commit `c08be8839d9681d4f68b9242abcf9a7ff40c4d24`. Parent and executing implementation commit `ac371ba274cbce21484ced78985f21902244e6cd`. Schema `m8-arm-manifest-1`. Condition `B1_generic_released_rnagenesis`. Training seed null. Technical block A. Generation seeds `800000` through `800162` (163 invocations). Master indexes are the block-A positions in the master map, 15,000 distinct values from 0 to 29976. Physical GPU 1, UUID `GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, PCI `00000000:61:00.0`, `compute_processes: 0`, exclusive historical GPU block. Started `2026-10-08T13:55:44+00:00`. Finished `2026-10-08T16:14:52+00:00`. Ledger `m8_raw_attempt_ledger.jsonl`, 13,213,570 bytes.

B1 block B. Authorisation `m8_b1_block_b_ac371ba_gpu1_attempt1`. Authorization commit `f13e0849e19632181315bf5585ae585e16bbb127`. Parent `c08be8839d9681d4f68b9242abcf9a7ff40c4d24`. Executing implementation commit `ac371ba274cbce21484ced78985f21902244e6cd`. Schema `m8-arm-manifest-1`. Condition `B1_generic_released_rnagenesis`. Training seed null. Technical block B. Generation seeds `900000` through `900163` (164 invocations). Master indexes are the block-B positions, 15,000 distinct values from 269 to 29999. Same exclusive physical GPU 1, `compute_processes: 0`. Started `2026-10-09T00:35:55+00:00`. Finished `2026-10-09T02:55:25+00:00`. Ledger 13,214,037 bytes.

D1 training seed 43, block A. Authorisation `m8_d1_seed43_block_a_ac371ba_gpu1_attempt1`. Authorization commit `acc7e244926fcb9336d35d29d0d767cf1afc5743`. Parent `f13e0849e19632181315bf5585ae585e16bbb127`. Executing implementation commit `ac371ba274cbce21484ced78985f21902244e6cd`. Schema `m8-arm-manifest-1`. Condition `D1_mres_curated_aptamer_diffusion_adapted`. Training seed 43, which is not the generation seed and is not the record id. Technical block A. Generation seeds `800000` through `800162`, the same generation-seed range as B1 block A. Checkpoint `D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-43__epoch-5__update-105__git-c150894b9982d7afebfb2b3390b0797a4da146b5`, epoch 5, update 105, weight SHA-256 `c0797888bde9033cc15b056c8c09e70b9f7fba0fb21b1f3840a4f1efb77031ab`. Exclusive physical GPU 1, `compute_processes: 0`. Started `2026-10-09T03:28:22+00:00`. Finished `2026-10-09T05:49:14+00:00`. Ledger 14,377,091 bytes.

D1 training seed 44, block B. Authorisation `m8_d1_seed44_block_b_1069b63_gpu0_shared_attempt1`. Authorization commit `50a41b84c7340aca5841672ea7507ceb4c1b7b94`. Parent and executing implementation commit `1069b6311f327bee6f0831fae5b42b47181b450d`. Schema `m8-arm-manifest-2`. Condition `D1_mres_curated_aptamer_diffusion_adapted`. Training seed 44. Technical block B. Generation seeds `900000` through `900163`, the same generation-seed range as B1 block B. Checkpoint `D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-44__epoch-5__update-105__git-2cb1b6a26391ed36754ec21685a4501d659d50ef`, epoch 5, update 105, weight SHA-256 `d0fcb5174230b8bbbc6bfe59eabda9b37687c03800012bc1a6981cc215469ed5`. Started `2026-10-09T11:12:39+00:00`. Finished `2026-10-09T13:32:21+00:00`. Ledger 14,594,198 bytes.

Shared-GPU scope is this seed-44 block-B arm only. `gpu_sharing_policy` is `shared_allowed`. Physical GPU 0, UUID `GPU-b3c42ea9-ec47-c854-e469-cd78e443c76b`, PCI `00000000:41:00.0`. The single pre-consumption observation at `2026-10-09T11:12:26+00:00` recorded `preexisting_compute_applications_observed: true` and `preexisting_compute_process_count: 2`. Those two processes were pre-existing compute applications, not generated-model processes. The other three arms stayed on the exclusive historical GPU-1 contract with `compute_processes: 0`. Shared use can affect runtime and resource contention. The exact generated bytes and provenance of the seed-44 arm remain the sealed ledger and manifest named above. This closure does not rewrite them.

Both selected checkpoints are the human-approved epoch-5 update-105 pair. Selected-set SHA-256 `af0c0e555a8b878feadeb17fcbde18d8b780819a42d9e0cc547d2fc0c6895f8f`. Final-selection manifest SHA-256 `49b218e3df74825e1931148e2f65b25aae057c822e2ab32d44c2960b1587c91c`. The sealed M7 final-selection manifest still has `m8_generation_performed: false`. That run-time flag is not the milestone-status authority and is not rewritten.

### 8.2 Allocation, seeds, and record ids

The master attempt map has indexes 0 through 29999. Block A and block B partition those indexes. They are not the ranges 0–14999 and 15000–29999. Each combined ledger is ordered by master index and contains each index exactly once.

Generation seeds are invocation seeds. Block A uses `800000 + invocation index`. Block B uses `900000 + invocation index`. The same generation seed is reused across the paired B1 and D1 arm. A generation seed is not a training seed. B1 records `d1_training_seed: null`. D1 block A records training seed 43 on every one of its 15,000 rows. D1 block B records training seed 44 on every one of its 15,000 rows. The record id is `m8:{condition_id}:master:{master_index_as_five_digits}`. It encodes the condition and the master index. It does not encode the training seed or the generation seed. Each arm has 15,000 unique record ids. Each combined ledger has 30,000 unique record ids.

### 8.3 Combined outputs

B1 combined directory `/home/laura/rnagenesis-mres-runs/m8_b1_combined_1069b63_cpu_attempt1`. Authorisation `m8_b1_combined_1069b63_cpu_attempt1`. Authorization commit `b79e70c0d895ba34f7655732412a1c3e039b4067`. Parent and executing implementation commit `c9a8cfc8cb2d720fdab8743bed088e8f900c3198`. Ledger `m8_combined_raw_attempt_ledger.jsonl`, 30,000 records, 26,427,607 bytes, SHA-256 `37ba0e1b852a6b8492a816a4adc0c6bfee15a554ba28a8ba5dd91d9e32a255d9`. Assembly manifest `m8_assembly_manifest.json`, 2,886 bytes, SHA-256 `f217e2e8ce922eef42b5f761159c7d96b7938585b4840922321454076d95d458`. Consumption record `authorization_consumption.json`, 1,016 bytes, SHA-256 `5cf932bc39d9ed5a02d18056c85bde85c0a016d5f24c9bb7a4fa751d74827e92`. Parsing, filtering, deduplication, metric computation, replacement, and replenishment are false. `later_evaluation_required` is true.

D1 combined directory `/home/laura/rnagenesis-mres-runs/m8_d1_combined_1069b63_cpu_attempt1`. Authorisation `m8_d1_combined_1069b63_cpu_attempt1`. Authorization commit `c9a8cfc8cb2d720fdab8743bed088e8f900c3198`. Parent and executing implementation commit `02b273955a5db4b5439c4fc12038aac911371e9c`. Ledger `m8_combined_raw_attempt_ledger.jsonl`, 30,000 records, 28,971,289 bytes, SHA-256 `cedcc36133f5dfb3678e1560c6d6bab703136fe89e512e939b9f93a9a6361de9`. Assembly manifest `m8_assembly_manifest.json`, 2,939 bytes, SHA-256 `5ec79e1485b201d801ca819d9d60a2ee4383abd9cccfbbb011c6e11a9a59bbcb`. Consumption record `authorization_consumption.json`, 1,016 bytes, SHA-256 `59f1b09349e1965eff813cb24a9c969d77a1770c2febec60fc674123c302401a`. Parsing, filtering, deduplication, metric computation, replacement, and replenishment are false. `later_evaluation_required` is true. The D1 ledger contains 15,000 rows with training seed 43 and 15,000 rows with training seed 44.

### 8.4 Generation runtime

Summed GPU execution time is the sum of the four manifest `elapsed_seconds` values:

8348.671256661415 + 8369.749910581857 + 8451.951393645257 + 8381.193621516228 = 33551.566182404757 seconds.

That is 9 hours, 19 minutes, and 11.566182404757 seconds, or 9.3198794951124325 hours. It counts the four generation executions and excludes CPU assembly. It lies inside the 6.4–10.4 GPU-hour planning band.

Wall-clock scheduling time is the span from the first recorded arm start `2026-10-08T13:55:44+00:00` to the last recorded arm finish `2026-10-09T13:32:21+00:00`, which is 84,997 seconds: 23 hours, 36 minutes, and 37 seconds. Those timestamps are whole seconds. The four arms do not overlap. The idle gaps between a recorded finish and the next recorded start are 30,063 seconds, 1,977 seconds, and 19,405 seconds. Those gaps are scheduling time. They are not GPU execution. The practical 12–16 hour reservation was a planning figure. The measured wall-clock span is longer because of those gaps.

### 8.5 What this closure does not establish

Only two fine-tuning seeds were used, because of time and GPU constraints. Evaluation completeness was prioritized over a third training replicate. The training seed is coupled to the D1 technical block and to the generation-seed range: seed 43 is block A and generation seeds 800000–800162; seed 44 is block B and generation seeds 900000–900163. The pooled D1 condition supports condition-level evaluation. It does not support clean replicate-level causal inference.

Raw attempts are not yet established to be valid nucleotide sequences. M8 performed no duplicate removal, exact training-set-match analysis, leakage analysis, biological-quality assessment, structure analysis, clustering, representation-space analysis, or functional evaluation.

M7 guardrail samples were not included in M8. The M4 and M7 1,000-attempt pools stay outside the 30,000-attempt totals. Seed 43 attempt 1, authorisation `m7_d1_final_replicate_seed43_e682cb6064a5_gpu1_attempt1`, remains the consumed M7 failure at stage `runtime_identity` with code `environment_rejected`. That failure was an environment and runtime-identity failure. It was not a model failure, it is not accepted training evidence, and its outputs are not part of M8.

Guardrails establish generation and runtime sanity only. They do not establish downstream biological quality.

### 8.6 Handoff to the separate four-condition evaluation

The evaluation inputs from M8 are the two combined ledgers:

- B1: `/home/laura/rnagenesis-mres-runs/m8_b1_combined_1069b63_cpu_attempt1/m8_combined_raw_attempt_ledger.jsonl`, 30,000 records, SHA-256 `37ba0e1b852a6b8492a816a4adc0c6bfee15a554ba28a8ba5dd91d9e32a255d9`
- D1: `/home/laura/rnagenesis-mres-runs/m8_d1_combined_1069b63_cpu_attempt1/m8_combined_raw_attempt_ledger.jsonl`, 30,000 records, SHA-256 `cedcc36133f5dfb3678e1560c6d6bab703136fe89e512e939b9f93a9a6361de9`

Later evaluation must apply the same declared parsing and filtering policy symmetrically across B0, B1, B2, and D1. Evaluation must not tune parameters after inspecting REF or EVAL outcomes. The evaluation worktree `/home/laura/rnagenesis-mres-worktrees/generator-eval-prep` remains out of scope. This closure does not enter it, modify it, or authorise evaluation.
