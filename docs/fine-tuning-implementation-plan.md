# RNAGenesis RNA Aptamer Latent-Diffusion Fine-Tuning Implementation Plan

**Project:** Towards prediction-guided generative design of RNA aptamers against carbapenemase targets  
**Status:** Approved modelling strategy; implementation plan to be completed before any GPU training  
**Plan revision date:** 25 September 2026  
**Frozen corpus commit:** `10aac629bb0ef0337107c3d628b23e1897962af9` — `Complete corrective corpus revision for RNA modelling alphabet gate`. This corrected closure supersedes `095236dfb13d1d3b13f11bbb34c2e48319c10184` — `Complete S7D final corpus build and validation`.\
**Primary compute:** One NVIDIA H200 NVL GPU on host `aai`; GPU0 is the default. GPU1 may be used only when explicitly authorised for that session/run.  
**Primary MRes strategy:** freeze the complete released RNAGenesis sequence autoencoder and fine-tune the released generic latent-diffusion denoiser on the frozen TRAIN aptamer corpus  
**Deferred to PhD:** parameter-efficient diffusion adaptation, partial diffusion unfreezing, Q-Former/decoder adaptation, joint latent-space realignment, target-conditioned generation, target-aware guidance, extensive hyperparameter optimisation and wet-lab feedback loops

---

## 1. Purpose

This document defines the auditable implementation and experimental protocol for adapting RNAGenesis to the frozen MRes RNA aptamer corpus.

The MRes adaptation experiment will use the following architecture:

```text
RNA sequence
    |
    v
released RNAGenesis sequence autoencoder
    encoder + Q-Former + latent projection
    [FROZEN]
    |
    v
latent representation z
    |
    v
RNAGenesis TransformerDenoiser
    [TRAINABLE]
    |
    v
aptamer-domain latent distribution
    |
    v
released latent projection + ProGen2-small decoder
    [FROZEN]
    |
    v
generated RNA sequence
```

The implementation must:

1. use only the frozen TRAIN role for RNAGenesis fitting;
2. use only frozen VALIDATION for checkpoint and model-development decisions;
3. keep REF reserved exclusively for AptaRank calibration;
4. keep EVAL inaccessible during model development and unlock it only after the generator and ranking pipeline are frozen;
5. preserve the complete released RNAGenesis `EncDec` representation/decoding interface;
6. fine-tune only the latent diffusion denoiser;
7. begin from the generic released RNAGenesis diffusion checkpoint rather than the already aptamer-adapted checkpoint;
8. prevent silent repartitioning, sequence rewriting, chemistry rewriting or data leakage;
9. compare the adapted generator with clearly defined and correctly named baseline conditions;
10. record exact data, code, environment, checkpoint, generation and result provenance for every thesis result;
11. remain realistic for the MRes timeline and avoid an unnecessary adaptation-strategy sweep.

No GPU training run may begin until the implementation, validation metrics, baseline definitions, training configuration and contamination gates described here have been reviewed.

---

## 2. MRes scientific question and claim boundaries

### 2.1 Primary scientific question

The primary MRes modelling question is:

> **Can small-data adaptation of the RNAGenesis latent diffusion model using a leakage-controlled corpus of experimentally supported protein-binding RNA aptamers shift the model's unconditional generative distribution toward held-out aptamer-like sequence and structural characteristics while retaining validity, diversity and novelty?**

The experiment tests adaptation of a **general RNA latent prior toward an aptamer-domain prior**.

Conceptually, the MRes intervention is:

\[
p_{\text{generic}}(z) \longrightarrow p_{\text{curated aptamer}}(z)
\]

while holding the learned sequence-to-latent and latent-to-sequence mappings fixed.

### 2.2 What the model is learning

The frozen TRAIN corpus is heterogeneous across many protein targets. It does not contain a training-scale set of KPC, NDM or OXA-48 RNA aptamers.

The MRes model may therefore learn statistical characteristics associated with experimentally supported RNA aptamers across many protein targets, including potentially:

- sequence composition;
- recurring sequence motifs;
- length-related characteristics;
- latent structural/functional regularities already represented by the frozen RNAGenesis autoencoder;
- secondary-structure tendencies;
- diversity characteristics of the curated aptamer domain.

The training data do **not** provide a mechanism for learning:

\[
p(\text{RNA sequence}\mid\text{KPC-2})
\]

or another protein-specific conditional distribution.

### 2.3 Target-specific design is out of scope for this MRes fine-tuning stage

The following are explicitly deferred:

- direct target-conditioned generation;
- protein-conditioned diffusion;
- KPC/NDM/OXA-specific fine-tuning;
- classifier or reward guidance toward a carbapenemase;
- learned aptamer-protein interaction conditioning;
- wet-lab-guided reinforcement or active learning.

Target prioritisation in the MRes will instead arise later through AptaRank and the downstream ranking pipeline. Any such prioritisation must be described as computational prioritisation, not evidence that the generative model learned target binding.

### 2.4 Permitted conclusion

The strongest permitted generator-level conclusion is of the form:

> Diffusion adaptation using the curated TRAIN corpus changed the distribution of RNAGenesis-generated sequences toward characteristics observed in held-out experimentally supported RNA aptamers while retaining specified levels of validity, novelty and diversity.

The MRes fine-tuning experiment cannot demonstrate:

- binding to KPC-2, NDM-1, OXA-48 or another specific protein;
- improved binding affinity;
- biological activity;
- target selectivity;
- causal discovery of aptamer binding mechanisms.

---

## 3. Frozen corpus modelling contract

The curation pipeline S1-S7D is complete. The corpus is immutable unless a separately documented corpus revision is initiated.

### 3.1 TRAIN

```text
identities = 726
distinct sequence cores = 669
clusters = 569
targets represented = 320

ft_train.csv SHA256 =
84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0

corpus_final.txt =
669 unique TRAIN sequence_core values only

corpus_final.txt SHA256 =
d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d
```

**Role:** RNAGenesis fitting only.

The authoritative RNAGenesis training sequence file is `corpus_final.txt`.

### 3.2 VALIDATION

```text
identities = 132
cores = 95
clusters = 63
targets represented = 100

ft_validation.csv SHA256 =
cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd
```

**Role:** model-development decisions only, including:

- validation diffusion objective;
- checkpoint selection;
- early-stop decisions if needed;
- bounded hyperparameter/configuration selection;
- development-time generator diagnostics.

VALIDATION must never be merged into TRAIN during model development.

### 3.3 REF

```text
identities = 131
cores = 113
clusters = 79
targets represented = 97

ref.csv SHA256 =
531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23
```

**Role:** fitting/calibrating empirical AptaRank reference distributions only.

REF must not be used to:

- fit RNAGenesis;
- select RNAGenesis checkpoints;
- choose RNAGenesis hyperparameters;
- compare development-time generator configurations.

### 3.4 EVAL

```text
identities = 181
cores = 154
clusters = 79
targets represented = 111

eval.csv SHA256 =
ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015
```

**Role:** final held-out assessment only, after generator and downstream pipeline decisions are frozen.

EVAL must not influence:

- training;
- checkpoint selection;
- learning rate or epoch decisions;
- generation hyperparameters;
- AptaRank calibration;
- metric choice;
- model/pipeline configuration selection.

### 3.5 Frozen role invariant

```text
TRAIN      -> RNAGenesis fitting only
VALIDATION -> RNAGenesis development decisions only
REF        -> AptaRank calibration only
EVAL       -> final held-out assessment only
```

There is zero frozen cluster/core leakage across the four roles.

---

## 4. Required terminology for conditions and thesis reporting

Condition names must be stable across code, manifests, figures, tables, weekly reports and the thesis.

### 4.1 B1 — Generic released RNAGenesis baseline

**Canonical short name:** `B1 — generic released RNAGenesis`  
**Manifest label:** `B1_generic_released_rnagenesis`

Definition:

- released frozen RNAGenesis `EncDec`;
- released diffusion checkpoint at `configs/rnagenesis/diffusion`;
- no MRes aptamer-corpus fine-tuning.

Preferred thesis wording:

> **generic released RNAGenesis baseline**

or:

> **generic released RNAGenesis diffusion checkpoint (B1)**

Do not silently rename B1 to `unadapted aptamer RNAGenesis`.

If the authors' release provenance is explicitly verified as ncRNA-pretrained, the methods may additionally state that provenance, but the condition name remains **generic released RNAGenesis** so that it does not depend on an inference about undocumented training history.

B1 is the principal model baseline for estimating the effect of the MRes aptamer-domain adaptation.

### 4.2 B0 — Released aptamer-adapted RNAGenesis baseline

**Canonical short name:** `B0 — released aptamer-adapted RNAGenesis`  
**Manifest label:** `B0_released_aptamer_rnagenesis`

Definition:

- same released frozen `EncDec`;
- released application-specific diffusion checkpoint at `checkpoints/Aptamer/diffusion`;
- already adapted by the RNAGenesis authors using their separate aptamer dataset/workflow;
- not trained on the frozen MRes corpus.

Preferred thesis wording:

> **released aptamer-adapted RNAGenesis baseline**

or:

> **published/released RNAGenesis aptamer checkpoint (B0)**

**Prohibited wording:**

- `unadapted RNAGenesis`;
- `pretrained-only RNAGenesis`;
- `generic RNAGenesis`;
- wording that implies B0 has not already undergone aptamer-specific adaptation.

The existing 30,080-sequence H200 pool generated from B0 is an existing baseline asset and must be retained with its original provenance.

### 4.3 B2 — TRAIN-matched empirical i.i.d. RNA null

**Canonical short name:** `B2 — TRAIN-matched empirical RNA null`  
**Manifest label:** `B2_train_matched_empirical_null`

Definition:

- no neural model;
- sequence lengths sampled from the frozen TRAIN empirical length distribution of the corrected 669 unique TRAIN cores;
- nucleotide identities sampled independently from frozen TRAIN nucleotide frequencies of those same 669 cores;
- no learned structure, motif, positional dependency or binding information.

Preferred thesis wording:

> **TRAIN-matched empirical i.i.d. RNA null (B2)**

or:

> **empirical TRAIN-matched random-RNA baseline (B2)**

**Prohibited wording:**

- `random aptamers`;
- `negative aptamers`;
- `non-binding RNA`;
- language implying B2 sequences have experimentally established biological status.

The existing implementation is `scripts/null_model.py`. It already computes corpus nucleotide frequencies and empirical lengths and generates i.i.d. sequences with NumPy. It should be reused and hardened with frozen-input loading, output writing, manifest generation and hash/provenance checks before regenerating the required 30,000-sequence pool. Do not replace its statistical design unless inspection demonstrates a correctness problem.

### 4.4 D1 — MRes curated-aptamer diffusion-adapted RNAGenesis

**Canonical short name:** `D1 — MRes curated-aptamer diffusion-adapted RNAGenesis`  
**Manifest label:** `D1_mres_curated_aptamer_diffusion_adapted`

Definition:

- released frozen `EncDec`;
- diffusion model initialized from B1 (`configs/rnagenesis/diffusion`);
- full latent diffusion denoiser fine-tuned on the 669 frozen TRAIN sequence cores;
- VALIDATION used for development decisions;
- no protein-target conditioning.

Preferred thesis wording:

> **MRes curated-aptamer diffusion-adapted RNAGenesis (D1)**

or, when the full description has already been established:

> **MRes-adapted RNAGenesis (D1)**

The methods must state at first use:

> RNAGenesis was adapted by fine-tuning its latent diffusion denoiser while keeping the released sequence autoencoder — encoder, Q-Former, latent projection and ProGen decoder — frozen.

### 4.5 Required wording about target conditioning

Use wording such as:

> The MRes fine-tuning corpus contains experimentally supported RNA aptamers against many protein targets. The resulting D1 generator is therefore an unconditional aptamer-domain model; it is not conditioned on protein identity and should not be described as a KPC-, NDM- or OXA-specific generator.

Use wording such as:

> Target-specific prioritisation is performed downstream by AptaRank and related ranking components and is distinct from the unconditional RNAGenesis adaptation experiment.

### 4.6 Required wording about chemistry

Use wording such as:

> RNAGenesis receives canonical nucleotide identity only. Where an experimentally tested aptamer used modified RNA chemistry but its curated `sequence_core` is representable as A/C/G/U, the base sequence may be used for model adaptation; the model does not receive or learn the chemical modification state directly.

Do not claim that D1 models 2F, 2OMe or other noncanonical chemistry unless a future model explicitly represents those modifications.

### 4.7 Required wording about "aptamer-like"

`aptamer-like` may refer only to measured similarity to distributions of curated aptamer sequences/structures.

It must not be used as shorthand for:

- proven binding;
- functional activity;
- target specificity;
- experimental validation.

---

## 5. Approved MRes adaptation strategy

### 5.1 D1 architecture

The only RNAGenesis fine-tuning strategy to be implemented as the main MRes adaptation is:

| Component | MRes state |
|---|---|
| RNA encoder | Frozen |
| Q-Former layers | Frozen |
| Query-token embeddings | Frozen |
| Latent projection | Frozen |
| ProGen2-small decoder | Frozen |
| TransformerDenoiser | **Trainable** |

The denoiser is initialized from the generic released checkpoint distributed at:

```text
configs/rnagenesis/diffusion
```

not from:

```text
checkpoints/Aptamer/diffusion
```

unless a later documented failure shows that the generic checkpoint cannot be used as intended.

### 5.2 Why this is the selected strategy

#### Small-data suitability

TRAIN contains only 669 distinct sequence cores. The selected approach preserves the high-capacity pretrained sequence representation and decoder instead of attempting to relearn them from 669 sequences.

The experiment therefore performs transfer learning on an existing latent generative prior rather than training a new latent representation or decoder.

#### Architectural consistency

The diffusion denoiser is trained to model the distribution of latents generated by the released frozen autoencoder. Holding that autoencoder fixed preserves the coordinate system in which the released diffusion model already operates.

#### Released-code support

Upstream RNAGenesis commit `6bc641acfb16aa2dfcbfd33b50fe5085150777a9` adds an official latent-diffusion fine-tuning workflow (`FINETUNE.md`, `train_diffusion.py`, `data/dataset_builder.py`, `data/fasta2txt.py`, `configs/diffusion/config_n.json`).

The released trainer:

- loads the same `EncDec` used by `generation.py`;
- calculates sequence latents under `torch.no_grad()`;
- loads an existing denoiser using `--pretrained_ckpts`;
- adds diffusion noise;
- predicts the diffusion target;
- optimises denoising MSE;
- writes checkpoints directly compatible with `generation.py`.

#### Methodological contribution remains substantive

The MRes will not simply run the upstream script unchanged. The project-specific implementation must add or modify:

- immutable TRAIN/VALIDATION loading;
- removal of upstream automatic random 90/10 splitting;
- strict role/hash guards;
- fixed stochastic validation draws;
- held-out diffusion loss;
- checkpoint selection;
- small-data optimisation settings;
- memorisation/mode-collapse diagnostics;
- empirical length-matched generation;
- chemistry eligibility checks;
- complete experiment manifests;
- final EVAL lock/unlock logic.

### 5.3 Strategies explicitly deferred to PhD

Do not implement these as MRes competitors unless the approved D1 strategy proves technically impossible:

- LoRA/other PEFT on the diffusion transformer;
- partial diffusion-layer unfreezing;
- Q-Former adaptation;
- decoder adaptation;
- Q-Former + decoder adaptation;
- joint autoencoder + diffusion training;
- diffusion training from scratch;
- target-conditioned diffusion;
- inference-time protein-target guidance.

Their absence from the MRes is intentional scope control, not a missing baseline.

---

## 6. Observed RNAGenesis implementation state

The following facts were established by read-only inspection on H200 before adopting this plan.

### 6.1 Local released RNAGenesis checkout

```text
repository: /home/laura/RNAGenesis
local commit: d00899eef60d664cc7b5880c0bb43f2a9e7a1b01
```

At this commit:

- `generation.py` is present;
- `models/autoencoder/encdec.py` is present;
- `FINETUNE.md` is absent;
- `train_diffusion.py` is absent.

### 6.2 Current upstream fine-tuning additions

Read-only upstream inspection found:

```text
upstream inspection commit:
6bc641acfb16aa2dfcbfd33b50fe5085150777a9

intermediate fine-tuning commit:
790a1b4 Add latent diffusion fine-tuning tutorial
```

Files added after the local release include:

```text
FINETUNE.md
configs/diffusion/config_n.json
data/dataset_builder.py
data/fasta2txt.py
train_diffusion.py
```

These files should be incorporated into a dedicated RNAGenesis implementation branch only after review.

### 6.3 Released generic and aptamer diffusion assets are distinct

Generic released checkpoint candidate:

```text
configs/rnagenesis/diffusion
```

Released aptamer checkpoint:

```text
checkpoints/Aptamer/diffusion
```

Both contain approximately 7.4 GB denoiser weights, and byte comparison established that the weights differ.

### 6.4 Autoencoder configuration

Observed released configuration:

```text
data_type = rna
rna_encoder_type = biomap
num_query_tokens = 32
hidden_size = 160
num_attn_heads = 20
decoder_config = config-progen2-small-rna_tokenizer_v2
rna_tokenizer_config = tokenizer_rna_v2
rm_encoder = false
rm_qt = false
```

**M0 reconstruction decision approved — 25 September 2026:** restore the biomap encoder using `xTrimoPGLMModel` and the character-wise tokenizer from `Zaixi/RNAGenesis` revision `d8a42130984cbf04f6a5e16a3aa0c0d6578036a8`, with encoder weights from the released RNAGenesis `EncDec` checkpoint. The approved call is `encoder(input_ids)` with no explicit `position_ids` and no encoder `attention_mask`; transpose its `[L, B, 1280]` output to `[B, L, 1280]`, then pass the frozen collator mask only to the Q-Former. Diffusion receives the Q-Former's pre-`transform` latent `[B, 32, 160]`.

This is a human-approved reconstruction following the published `AutoModel`/released `struct_pred` convention. The missing historical `get_latent` source has not been recovered, so equivalence to its original training-time call cannot be established. See the [approved decision and residual uncertainty](fine_tuning/biomap_reconstruction_decision.md) and [pinned dependency manifest](fine_tuning/model_asset_manifest.md#pinned-biomap-encoder-dependency). The clean M0 preflight loaded `EncDec` from `configs/rnagenesis/autoencoder` with `EncDec` frozen and the denoiser as the trainable parameter set. That check does not establish equivalence to the missing historical `get_latent`. The complete `EncDec` stays frozen and only the denoiser is trainable.

### 6.5 Diffusion architecture

Observed generic denoiser configuration includes:

```text
class = TransformerDenoiser
in_channels = 160
num_layers = 24
num_attention_heads = 16
attention_head_dim = 128
dropout = 0.1
activation_fn = geglu
norm_type = ada_norm
num_embeds_ada_norm = 2000
prediction_type = epsilon
num_train_timesteps = 1000
```

The exact trainable parameter count must be measured programmatically and logged before the first optimisation run; do not infer the count only from checkpoint size.

**Measured at the clean M0 preflight on 25 September 2026, RNAGenesis `e20f556`, before any optimizer step:** denoiser parameter count = 1,911,589,344; trainable parameter count = 1,911,589,344; registered buffer elements = 50,331,648; serialized state elements = 1,961,920,992. Safetensors metadata reports 1,961,920,992 FP32 elements because that file total includes the 24 registered `transformer_blocks.0`–`23.pos_embed.pe` buffers. The runtime `nn.Parameter` count is 1,911,589,344. See the [model asset manifest](fine_tuning/model_asset_manifest.md).

### 6.6 H200 environment

Observed environment:

```text
host = aai
conda env = /home/laura/miniconda3/envs/rnagenesis-h200
Python = 3.8.13
torch = 2.1.2+cu121
transformers = 4.36.2
diffusers = 0.25.0
accelerate = 0.25.0
huggingface_hub = 0.20.3
numpy = 1.22.0
scipy = 1.10.1
pandas = 1.3.1
Biopython = 1.83
ViennaRNA = 2.7.0
```

### 6.7 Required local diffusers patch

The H200 environment contains a required compatibility modification:

```python
scale, shift = torch.chunk(emb, 2, dim=-1)
```

in:

```text
/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/site-packages/diffusers/models/normalization.py
```

This patch is not captured by a normal Conda export. Its exact file hash and patch diff must be included in the experiment environment manifest.

---

## 7. TRAIN input representation

### 7.1 Authoritative sequence input

Use:

```text
data/processed/corpus_final.txt
```

containing exactly 669 unique frozen TRAIN `sequence_core` values.

Do not construct the training stream from the 726 scientific-identity rows.

### 7.2 Why one row per unique sequence core

RNAGenesis D1 receives no target label. Repeating one sequence because it is associated with multiple target identities or multiple provenance records would silently reweight that sequence without supplying the model with the reason for the multiplicity.

Therefore:

```text
training grain = one distinct TRAIN sequence_core
```

### 7.3 `sequence_core`, not full construct

Use `sequence_core`, not `sequence_full`.

The core is the frozen modelling unit after removal of identified experimental constants. Training on full constructs could teach promoter, primer or scaffold artifacts rather than the selected aptamer region.

### 7.4 Chemistry policy

Primary policy:

> Retain every frozen TRAIN `sequence_core` that is directly representable by the released RNAGenesis RNA tokenizer as canonical A/C/G/U sequence.

Do not discard an otherwise model-compatible sequence solely because the experimentally tested molecule used 2F-RNA, 2OMe-RNA or another modification if the curated base sequence itself is standard A/C/G/U.

Rationale:

- the corpus is small;
- the objective is to preserve as much experimentally supported sequence evidence as possible;
- RNAGenesis models nucleotide identity, not the chemical modification state;
- chemistry metadata remains available for interpretation and later analyses.

The model must not be described as learning modified chemistry.

### 7.5 No silent alphabet conversion

Unlike the upstream convenience loader, the MRes loader must **not silently convert `T` to `U`** in the frozen TRAIN/VALIDATION files.

The frozen RNA modelling files should already satisfy the modelling contract.

Required assertion:

```regex
^[ACGU]+$
```

for every TRAIN and VALIDATION sequence.

If this assertion fails, stop and investigate. Do not silently rewrite the frozen corpus.

### 7.6 Length policy

Do not impose a new arbitrary fixed training length if every frozen sequence is within the released model's supported range.

Before training, record:

- minimum TRAIN length;
- maximum TRAIN length;
- median/mean;
- full empirical histogram;
- corresponding VALIDATION summary;
- frozen S6 short/long regime membership.

The corrected frozen S6 length regime contains **386 short and 283 long TRAIN cores** (669 total), and **55 short and 40 long VALIDATION cores** (95 total), as recorded in `config/global_s7d_final_build.json` under `expected_length_regime_cores`. Use these recorded assignments without refitting the length model.

---

## 8. Baseline definitions and existing assets

### 8.1 Separate implementation verification from scientific baselines

Implementation-verification tests establish that the code works. They are not scientific comparison conditions.

Scientific baseline conditions are B0, B1 and B2.

### 8.2 B0 existing asset

The project already contains a tracked H200 generation script:

```text
scripts/run_rnagenesis_aptamer_baseline_30k_h200_gpu1.sh
```

It generated:

```text
10 chunks
batch_size = 16
batch_num = 188
3008 attempts per chunk
30,080 raw attempts total
DDIM steps = 50
eta = 0
top_p = 0.95
top_k = 0
max_seq_len = 37
checkpoint = checkpoints/Aptamer/diffusion
```

This pool is retained as the existing **B0 released aptamer-adapted RNAGenesis** baseline.

Do not regenerate B0 merely because the new MRes experiment is beginning.

### 8.3 B0 comparability boundary

The existing B0 pool uses the released aptamer generation setting with a 37-nt maximum/output regime. It is therefore an **external comparator**, not the primary length-matched causal baseline.

Primary statements about the effect of MRes adaptation should rely on the controlled comparison:

```text
B1 generic released RNAGenesis
vs
D1 MRes diffusion-adapted RNAGenesis
```

with B2 as the non-neural empirical null.

Length-sensitive comparisons involving B0 must use one or more of:

- normalized metrics such as MFE/nt;
- explicit length stratification;
- a preregistered comparable-length subset;
- a separately justified harmonized B0 rerun only if later shown scientifically necessary.

A new B0 generation run is not part of the default plan.

### 8.4 B2 existing code

The existing project implementation `scripts/null_model.py` should be reviewed, hardened for the frozen modelling contract and reused rather than rewritten from scratch.

Before regeneration it must be verified to:

1. read only frozen TRAIN statistics;
2. sample lengths from the empirical TRAIN length distribution;
3. calculate nucleotide frequencies from TRAIN only;
4. sample nucleotides independently;
5. use a fixed recorded seed or prespecified seed set;
6. produce raw output accounting before any deduplication/filtering;
7. write a manifest containing the exact TRAIN hashes and derived distribution parameters.

The required B2 pool is 30,000 raw sequences.

### 8.5 B1 generic baseline generation

B1 must be generated from:

```text
EncDec = configs/rnagenesis/autoencoder
Diffusion = configs/rnagenesis/diffusion
```

The desired B1 design is empirical TRAIN-length matching.

Because `generation.py` exposes `max_seq_len` rather than an explicit requested biological length, M1/M4 must first determine the relationship among:

- requested `max_seq_len`;
- BOS/EOS artifacts;
- cleaned sequence length;
- early EOS termination.

If cleaned outputs reliably reach the requested length, B1 can be generated by allocating attempts across TRAIN lengths according to the empirical histogram and running the corresponding `max_seq_len` values.

If early EOS materially changes the output distribution, implement a documented rejection/resampling or alternative matching method before the main B1 pool is generated.

Do not silently truncate generated sequences merely to force length matching.

### 8.6 D1 generation

D1 must use the same generation protocol as B1 wherever technically applicable:

- same frozen `EncDec`;
- same length-allocation method;
- same generation seeds or paired seed schedule where possible;
- same DDIM step count;
- same `eta`;
- same top-p/top-k settings;
- same cleaning code;
- same raw-attempt accounting.

The main causal model comparison is therefore B1 versus D1.

---

## 9. Validation strategy

### 9.1 Upstream random splitting is prohibited

The upstream fine-tuning helper automatically creates a 90/10 random split. That behaviour must not be used.

The project already has leakage-safe frozen TRAIN and VALIDATION roles.

The MRes implementation must accept explicit inputs, conceptually:

```text
--train_data      frozen TRAIN text
--validation_data frozen VALIDATION text
```

No additional train/test or train/validation split may be generated.

### 9.2 Primary development metric

The primary checkpoint-selection metric is:

> **fixed-stochastic-draw VALIDATION diffusion denoising loss**

For each frozen VALIDATION sequence:

1. obtain its latent using the frozen `EncDec`;
2. use a preregistered set of diffusion timesteps and Gaussian noise tensors;
3. create the noisy latent with the same scheduler used in training;
4. predict the diffusion target with the denoiser;
5. compute the same MSE objective as training;
6. aggregate over the complete VALIDATION set.

### 9.3 Why validation noise/timesteps must be fixed

If a new noise draw is sampled for every checkpoint evaluation, differences in validation loss contain avoidable Monte Carlo noise.

Before training, generate a validation-evaluation specification containing:

- validation sequence ordering/hash;
- validation evaluation seed;
- number of stochastic draws per sequence;
- timestep tensor hash;
- Gaussian-noise tensor hash or deterministic generation recipe.

The same fixed stochastic problem must be used for every checkpoint/configuration comparison.

### 9.4 Development-time generated-sample metrics

At prespecified checkpoints, generate a modest fixed-seed diagnostic sample and calculate:

#### Hard guardrails

- valid A/C/G/U fraction;
- empty/unparseable fraction;
- unique fraction;
- exact TRAIN match rate;
- duplicate concentration/largest duplicate share;
- gross output-length collapse.

#### Memorisation/novelty

- exact overlap with TRAIN;
- nearest-TRAIN normalized edit distance;
- maximum sequence identity to TRAIN;
- distribution of nearest-TRAIN similarity;
- generated sequence-cluster concentration.

#### Aptamer-domain distribution diagnostics

- length distribution;
- A/U/C/G composition;
- GC distribution;
- mono-/dinucleotide distribution distance;
- ViennaRNA MFE;
- normalized MFE (MFE/nt);
- base-pair/paired fraction;
- structural diversity;
- frozen-encoder embedding distribution distance such as MMD to VALIDATION.

### 9.5 Secondary metrics do not replace the primary selection criterion

Do not build a post-hoc weighted score over many biological-looking metrics.

Default checkpoint selection rule:

> Choose the checkpoint with the lowest prespecified fixed-draw VALIDATION denoising loss, provided that it passes the preregistered validity, uniqueness and memorisation guardrails.

Secondary generated-distribution metrics are used to interpret checkpoints and to detect pathological solutions, not to tune an arbitrary composite objective.

### 9.6 REF is prohibited in development evaluation

Do not use REF for generator-distribution comparison.

All development-time generator comparisons use VALIDATION.

REF remains untouched until AptaRank calibration.

---

## 10. Training objective and implementation design

### 10.1 Training objective

For each TRAIN sequence:

1. tokenize canonical A/C/G/U character-wise using the pinned biomap encoder tokenizer, with no BOS/CLS/EOS additions, as recorded in Section 6.4;
2. encode to the pre-`transform` Q-Former latent `[B, 32, 160]` with the frozen `EncDec` in eval mode under `torch.no_grad()`, using the approved reconstruction in Section 6.4;
3. sample timestep `t`;
4. sample Gaussian noise `epsilon`;
5. create noisy latent using the released DDIM scheduler;
6. predict the configured diffusion target;
7. for the released epsilon-prediction checkpoint, minimize:

\[
\mathcal{L}_{\mathrm{diff}}=
\mathbb{E}_{z,t,\epsilon}
\left[
\lVert \epsilon-\epsilon_\theta(z_t,t)\rVert_2^2
\right]
\]

Only denoiser parameters receive gradients.

### 10.2 Frozen-model assertions

Before training and after the first optimisation update, assert:

- all `EncDec` parameters have `requires_grad=False`;
- the optimizer contains only denoiser parameters;
- encoder parameters have no gradients;
- Q-Former parameters have no gradients;
- projection parameters have no gradients;
- decoder parameters have no gradients;
- selected frozen tensors remain bit-identical;
- the denoiser contains changed tensors after an optimisation step.

Any failure is a hard stop.

### 10.3 Exact trainable-parameter report

Before the first run produce:

```text
component
parameter count
trainable parameter count
frozen parameter count
dtype
```

Do not report the denoiser parameter count by estimating from its 7.4 GB checkpoint.

---

## 11. Initial small-data optimisation regime

The upstream example configuration is not copied blindly because it was designed for much larger corpora.

For 669 TRAIN sequences, an effective batch of 256 would yield only approximately three optimizer updates per epoch, and a fixed 50-step warmup would span many effective epochs.

### 11.1 Optimizer

Use upstream-supported AdamW.

Starting operational parameters, unless the imported upstream script establishes a different required value:

```text
optimizer = AdamW
beta1 = 0.95
beta2 = 0.999
weight_decay = 1e-6
epsilon = 1e-8
gradient_clip_norm = 1.0
```

These values originate from the upstream fine-tuning implementation defaults and must be recorded in the run config.

### 11.2 Learning rate

Initial project starting value:

```text
3e-5
```

Rationale:

- lower than the upstream `1e-4` example;
- conservative continued-training step for a very small corpus;
- aims to reduce catastrophic movement away from the generic pretrained prior.

A single bounded adjustment to `1e-5` is permitted if the M5 pilot demonstrates immediate overfitting/divergence at `3e-5`.

Do not run a broad learning-rate sweep.

Any adjustment must be made using VALIDATION only and recorded before the full replicate stage.

### 11.3 Effective batch

Target initial effective batch:

```text
32```

The physical microbatch is determined by the GPU-memory pilot.

Example permitted configurations:

```text
microbatch 8  x accumulation 4 = effective batch 32
microbatch 16 x accumulation 2 = effective batch 32
microbatch 32 x accumulation 1 = effective batch 32
```

Single GPU only.

### 11.4 Epoch/step policy

Maximum development run:

```text
5 epochs
```

For 669 unique TRAIN cores at effective batch 32, the corrected plan arithmetic is `ceil(669 / 32) = 21` optimizer updates per epoch and `5 * 21 = 105` updates over five epochs. This assumes the final partial batch is retained (`drop_last=False`) and any final incomplete accumulation window is stepped at the epoch boundary. On one GPU, each permitted microbatch/accumulation combination in Section 11.3 gives 21 updates under these assumptions.

This M0 housekeeping correction replaces the previous approximately 22/110 estimate; it does not change the 669-core corpus, effective batch target, five-epoch maximum or optimisation strategy. Verify and record the actual loader/accumulation update count before execution, and derive warmup from that count using Section 11.5.

**Recorded by the clean M0 preflight on 25 September 2026, before any optimizer step:** microbatch 8, gradient accumulation 4, effective batch 32, dataloader batches/epoch 84, optimizer updates/epoch 21, epochs maximum 5, total optimizer updates maximum 105, warmup updates 10. Those loader and accumulation counts match this arithmetic. Warmup 10 is the stored integer from `max(1, round(0.10 * 105))`.

Save every epoch.

Report both epochs and optimizer-update counts.

### 11.5 Warmup

Do not use a fixed 50-step warmup.

Use a short warmup defined relative to the actual total optimizer-update count, initially:

```text
warmup = max(1, round(0.10 * planned_optimizer_updates))
```

The exact integer is stored in the run config before execution.

### 11.6 Scheduler

Use the upstream-supported cosine scheduler as the initial project configuration unless code inspection shows that the released generic checkpoint's documented continued-training recipe requires another scheduler.

### 11.7 Mixed precision

Smoke test first in full precision or the most conservative supported mode.

For the full H200 run, BF16 is preferred if:

- forward/backward smoke tests are finite;
- validation loss matches FP32 within expected numerical variation;
- checkpoint reload and generation succeed.

Do not use FP16 merely because it is available.

### 11.8 EMA

The upstream trainer supports EMA, and the released models were trained with EMA.

Use EMA if:

- the starting checkpoint contains compatible EMA state; or
- the upstream fine-tuning path initializes EMA consistently when it is absent.

Record separately whether generation uses raw or EMA weights.

Do not compare EMA versus non-EMA as a separate MRes strategy.

### 11.9 Random seeds

Stages:

- one fixed seed for implementation/smoke work;
- one pilot seed for configuration confirmation;
- **three independent full-training seeds** for the final D1 configuration if runtime permits.

Three full seeds are the target, not an optional afterthought. If server availability makes this impossible, the deviation must be documented explicitly as a limitation.

---

## 12. Hardware and shared-server constraints

### 12.1 Local MacBook

Use the M4 Max / 64 GB Mac for:

- code editing;
- Git/version control;
- data/hash verification;
- frozen data-view construction;
- unit tests not requiring CUDA;
- B2 generation;
- ViennaRNA evaluation;
- metric aggregation;
- plots/tables;
- documentation.

The Mac is not the authoritative RNAGenesis training environment.

### 12.2 H200

Use H200 for:

- released-model inference verification;
- diffusion training smoke tests;
- D1 pilot;
- D1 full training;
- large B1/D1 generation runs.

### 12.3 GPU selection policy

GPU0 is the default device for this project.

GPU1 is also authorised **only when its use is explicitly stated for that session/run**. Permission to use GPU1 in one session does not change the default for later sessions.

Every GPU command must explicitly isolate the selected device, for example:

```bash
# Default
CUDA_VISIBLE_DEVICES=0 ...

# Only when GPU1 has been explicitly authorised for the current session/run
CUDA_VISIBLE_DEVICES=1 ...
```

The selected physical GPU must be recorded in the run manifest and log.

### 12.4 Shared-server safety

Before every GPU run:

1. run `nvidia-smi`;
2. record the output in the run log;
3. identify the GPU authorised for that session, defaulting to GPU0;
4. verify that sufficient memory is actually free on the selected GPU;
5. do not infer availability from low GPU utilization alone;
6. do not kill or reconfigure another user's process;
7. postpone the run if memory is insufficient.

All project outputs, caches, code, environments and checkpoints must remain under directories owned by `laura`, except where university policy explicitly requires datasets to use another approved storage location.

---

## 13. Repository responsibilities and code-integration policy

### 13.1 `laura-hardy/RNAGenesis`

Use a dedicated implementation branch for RNAGenesis-specific changes.

The branch should:

- start from the known working release state;
- incorporate the upstream diffusion trainer at a pinned commit;
- preserve known-working `generation.py` behavior;
- add project-specific TRAIN/VALIDATION support;
- add validation evaluation;
- add role guards where appropriate;
- make the diffusers compatibility patch reproducible or at minimum automatically verifiable;
- retain a small, reviewable diff from upstream.

Do not update the working tree by blindly merging all upstream changes without review.

### 13.2 `laura-hardy/rnagenesis-aptamer-mres`

Store:

```text
docs/fine-tuning-implementation-plan.md

docs/fine_tuning/
    h200_readiness_report.md
    strategy_decision_record.md
    model_asset_manifest.md
    validation_protocol.md
    run_manifest_schema.md
    risk_register.md

config/modelling/
    frozen_data_contract.json
    validation_metrics_v1.yaml
    condition_registry.yaml

config/experiments/
    B1_generic_generation.yaml
    B2_empirical_null.yaml
    D1_diffusion_smoke.yaml
    D1_diffusion_pilot.yaml
    D1_diffusion_primary.yaml
    generator_evaluation.yaml

scripts/modelling/
    verify_modelling_contract.py
    build_validation_view.py
    verify_model_assets.py
    verify_frozen_parameters.py

scripts/evaluation/
    ../null_model.py  # existing B2 implementation; retain or wrap rather than duplicate
    evaluate_generator_conditions.py
    cluster_generated_sequences.py

results/
    modelling/<run_id>/...
```

Large model checkpoints remain outside Git.

### 13.3 Corpus transfer policy

Do not commit the frozen sequence-level corpus merely to transport it to H200 unless a later explicit data-governance decision authorises that approach.

Preferred transfer:

- direct secure transfer from Mac to `/home/laura/...`;
- hash verification after transfer;
- TRAIN and VALIDATION only during development;
- REF and especially EVAL remain physically absent from the training environment until needed.

---

## 14. Reproducibility and run manifests

Every scientific result must map to one immutable experiment manifest.

### 14.1 Required run fields

Record at minimum:

```text
experiment_id
condition_id
run_id
start/end timestamps
hostname
GPU model
CUDA_VISIBLE_DEVICES
nvidia-smi snapshot
MRes repository SHA
RNAGenesis repository SHA
upstream training-code SHA
working-tree dirty status
patch/diff hash if dirty
frozen corpus commit
TRAIN CSV SHA256
TRAIN text SHA256
VALIDATION SHA256
REF SHA256 recorded in contract but unavailable to training
EVAL SHA256 recorded in contract but unavailable to training
actual input file hashes
chemistry policy
sequence count
length summary
EncDec checkpoint asset hashes
generic diffusion input checkpoint hashes
aptamer diffusion B0 checkpoint hashes where relevant
tokenizer/config hashes
Python/package versions
diffusers patch verification/hash
trainable parameter names/counts
frozen parameter names/counts
optimizer parameters
scheduler
warmup
microbatch
gradient accumulation
effective batch
seed
optimizer update count
checkpoint cadence
validation protocol version
selected checkpoint rule
selected checkpoint
checkpoint SHA256
generation settings
post-processing/cleaning version
raw generation-output hashes
cleaned generation-output hashes
metric-code SHA
warnings/retries/deviations
```

### 14.2 Checkpoint naming

Use deterministic informative names, e.g.:

```text
D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-42__epoch-03__git-<sha>
```

Do not use ambiguous names such as:

```text
final
final2
best
good_run
new_model
```

### 14.3 Generated-sequence provenance

Every generated sample set must preserve:

- condition ID;
- checkpoint hash;
- generation seed;
- requested length/max length;
- DDIM steps;
- eta;
- top-p/top-k;
- raw attempt index;
- raw output string;
- cleaned sequence;
- cleaning flags;
- raw and cleaned file hashes.

---

## 15. Hard contamination and integrity guards

### 15.1 Frozen data contract

The machine-readable contract is `config/modelling/frozen_data_contract.json`. Its read-only validator is `scripts/modelling/verify_modelling_contract.py`; local results and repeatable checks are documented in `docs/fine_tuning/m0_data_contract_verification.md`. The minimum role/hash fields are:

```json
{
  "corpus_commit": "10aac629bb0ef0337107c3d628b23e1897962af9",
  "corpus_commit_supersedes": "095236dfb13d1d3b13f11bbb34c2e48319c10184",
  "corpus_commit_subject": "Complete corrective corpus revision for RNA modelling alphabet gate",
  "roles": {
    "TRAIN": {
      "sha256": "84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0",
      "allowed": ["fit"]
    },
    "TRAIN_TEXT": {
      "sha256": "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d",
      "allowed": ["fit"]
    },
    "VALIDATION": {
      "sha256": "cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd",
      "allowed": ["development_evaluate", "checkpoint_select"]
    },
    "REF": {
      "sha256": "531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23",
      "allowed": ["aptarank_calibrate"]
    },
    "EVAL": {
      "sha256": "ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015",
      "allowed": ["final_evaluate_after_unlock"]
    }
  }
}
```

### 15.2 Fail-closed behavior

Before training:

```text
verify hashes
    -> verify role permissions
    -> verify sequence counts
    -> verify alphabet
    -> verify no duplicate TRAIN lines
    -> verify semantic split invariants
    -> verify model assets
    -> verify config
    -> only then build optimizer
```

The training command must raise an error if given:

- REF;
- EVAL;
- a file with an unexpected hash;
- a role not authorised for `fit`;
- a silently modified TRAIN/VALIDATION export.

### 15.3 Physical EVAL lock

Prefer not to place `eval.csv` in the H200 training workspace at all until M10.

This provides a second defence in addition to software guards.

---

## 16. Experimental milestones

The modelling work is divided into gated milestones. Each milestone has an objective, inputs, outputs/tests, a human review gate and explicit prohibited actions.

### M0 — Reproducibility and frozen-contract verification

**Objective**  
Establish the exact data/software/model boundary before implementation.

**Inputs**

- frozen corpus commit and hashes;
- updated MRes repository;
- released RNAGenesis checkout;
- upstream fine-tuning commit;
- H200 environment;
- generic and aptamer diffusion assets.

**Outputs/tests**

- `frozen_data_contract.json`;
- model asset manifest;
- environment manifest;
- exact denoiser parameter count;
- verified diffusers patch;
- TRAIN/VALIDATION hashes on H200;
- proof REF/EVAL are absent or inaccessible during training;
- [approved biomap reconstruction decision](fine_tuning/biomap_reconstruction_decision.md), including the external dependency pin, call convention and residual historical uncertainty;
- corrected 21/105 plan arithmetic, with actual loader/accumulation and warmup counts verified before execution;
- RNAGenesis code-integration diff reviewed.

**Human gate**  
Confirm that the imported trainer and data contract match this plan.

**Must not happen yet**

- no optimiser run on biological data;
- no EVAL access;
- no corpus modification.

**Current status: COMPLETE / GO — 25 September 2026.**

The human gate is GO: the imported trainer and development data contract match this plan, as recorded in [M0 data contract verification](fine_tuning/m0_data_contract_verification.md). The clean real-data preflight passed on RNAGenesis `e20f556` (`mres-d1-diffusion-finetune`) after `e20f556` corrected denoiser parameter accounting. Evidence in that record covers the frozen contract, H200 TRAIN/VALIDATION hashes, development-directory isolation with no REF/EVAL access, the exact denoiser parameter count, the verified 21/105 loader and warmup counts, and review of the RNAGenesis integration commits through `e20f556`.

M0 completion does not mean biological fine-tuning has run. The final preflight constructed no optimizer step and performed no generation. The missing historical `get_latent` source remains unrecovered. The next milestone is M1: released-behaviour and numerical training smoke validation, before the substantive D1 fitting run.

---

### M1 — Reproduce released inference behavior

**Objective**  
Ensure code integration does not alter known-working inference.

**Inputs**

- released `EncDec`;
- B0 checkpoint;
- B1 generic checkpoint;
- existing cleaning code.

**Outputs/tests**

- tiny deterministic B0 generation regression;
- tiny deterministic B1 generation;
- BOS/EOS handling verified;
- cleaned A/C/G/U outputs;
- generation output provenance;
- B1 versus B0 weight/checkpoint identity confirmation.

**Human gate**  
Accept inference regression.

**Must not happen yet**

- no fine-tuning;
- no model-selection use of EVAL/REF.

**Current status: COMPLETE / GO — 28 September 2026.**

The human gate is GO and chose the existing formal ordering. The accepted evidence is `/home/laura/rnagenesis-mres-runs/m1_inference_e20f556/m1_released_inference_evidence.json`, SHA-256 `ec518b3f8f78de19227abe5a14e138bcf381c231bc888689a298a16c946ee774`, recorded in [M1 released-inference validation](fine_tuning/m1_released_inference_validation.md). Released and current B0 raw outputs are byte-identical, and released and current B1 raw outputs are byte-identical. Cleaning accepted A/C/G/U sequences only. No fine-tuning ran, and no TRAIN, VALIDATION, REF or EVAL sequence was accessed. Numerical diffusion-training smoke was not performed and remains formal M5, after M2–M4. The broader “released-behaviour and numerical training smoke validation” wording does not reassign that M5 work into M1.

---

### M2 — Published aptamer implementation/comparator verification

**Objective**  
Establish that the released B0 aptamer condition and its existing 30,080-sequence pool are correctly identified and usable.

**Inputs**

- `checkpoints/Aptamer/diffusion`;
- existing B0 30,080 pool;
- tracked B0 generation script;
- RNAGenesis aptamer documentation/results.

**Outputs/tests**

- B0 pool manifest reconstructed/verified;
- exact raw count confirmed;
- generation seeds/settings recorded;
- cleaning statistics regenerated if needed;
- a limited published aptamer metric sanity check reproduced where feasible.

**Human gate**  
Approve B0 as external aptamer-adapted comparator.

**Must not happen yet**

- no D1 training;
- no reinterpretation of B0 as generic/unadapted.

**Current status: COMPLETE / GO — 28 September 2026.**

The human gate is GO. On 28 September 2026, Laura Hardy approved B0 as the external aptamer-adapted comparator. B0 is the authors’ released aptamer-adapted comparator, scientific label `B0_released_aptamer_adapted_RNAGenesis`, not generic, unadapted or pretrained-only. Provenance is `DIRECT_HUMAN_CONFIRMED_PROVENANCE`. The final account is [M2 published aptamer comparator verification](fine_tuning/m2_published_aptamer_comparator_verification.md). Pool accounting is raw 30,080, accepted 30,080, rejected 0, unique accepted 30,080, duplicate accepted 0, and cleaned length 36 throughout. Raw artifacts remained unchanged. Recovered settings and seeds are recorded in that report. The published metric is `INFEASIBLE_WITH_RELEASED_EVIDENCE`; no metric was calculated. The missing contemporaneous 10 June checkpoint hash remains an explicit limitation. No biological-quality claim follows from syntactic acceptance or uniqueness. No D1 training, generation, model selection, REF/EVAL access or unauthorised GPU use occurred. No GPU is currently authorised for later work. Numerical diffusion-training smoke remains formal M5. M3 is the next formal milestone.

---

### M3 — Frozen corpus loader and modelling-interface gates

**Objective**  
Prove that the frozen data can enter RNAGenesis without transformation or leakage.

**Inputs**

- `corpus_final.txt`;
- `ft_train.csv`;
- `ft_validation.csv`.

**Outputs/tests**

- exactly 669 TRAIN lines;
- exactly 669 unique TRAIN cores;
- exactly 95 unique VALIDATION cores;
- A/C/G/U-only assertion;
- length summaries;
- chemistry distribution report from metadata;
- tokenization success for every sequence;
- no TRAIN/VALIDATION core overlap;
- frozen cluster role assertions where metadata is available;
- upstream automatic split disabled.

**Human gate**  
Confirm chemistry policy and that no model-incompatible sequences are lost silently.

**Must not happen yet**

- no optimizer;
- no REF/EVAL loading.

**Current status: COMPLETE / GO — 29 September 2026.**

The human gate is GO. On 29 September 2026, Laura Hardy gave final human approval. The frozen-input and tokenizer/interface gate is PASS, and the chemistry and no-silent-loss human gate is PASS. The account is [M3 frozen corpus loader and modelling interface](fine_tuning/m3_frozen_corpus_loader_and_modelling_interface.md). The RNAGenesis implementation commit is `e3b855bbf4d1af376f43747643fa30afd662828c` on `mres-d1-diffusion-finetune`. Evidence is `/home/laura/rnagenesis-mres-runs/m3_tokenizer_112a120_f2bdff1_attempt1`: `m3_tokenizer_audit.csv` SHA-256 `063a068187e5b34c598b1ef4a294f924f3167538aec824786d6e9fac01d4eb9f`; `m3_validation_duplicate_audit.csv` SHA-256 `bfc966dbaff60523ebb44a75fa610f83f08724b0277ba4ed6c9b2a9956d39697`; `m3_chemistry_report.json` SHA-256 `8192b0717a7d5791d06c842ea5ba07011a7502dd6c51a5da004e5ae84fedeb50`; `m3_summary.json` SHA-256 `8862ecb066fac12ae80529737a2398322227f8789af07c2de2d375279896638c`. All 669 TRAIN and 95 VALIDATION modelling cores passed, and all 37 repeated VALIDATION identity rows were audited. Chemistry remained report-only. No model-compatible sequence was dropped. M4 is the next formal milestone and has not begun. M5, model loading, GPU work, training, generation, checkpoint selection, and REF/EVAL remain unauthorized.

---

### M4 — Baselines and validation protocol freeze

**Objective**  
Predeclare B1/B2 generation and all development metrics before D1 training.

**Inputs**

- B1 generic checkpoint;
- B0 existing pool;
- frozen TRAIN/VALIDATION;
- existing B2 code.

**Outputs/tests**

- verify and harden `scripts/null_model.py` as the B2 generator;
- regenerate 30,000 B2 sequences;
- determine `max_seq_len` -> cleaned-length behavior for B1;
- finalize B1 empirical-length matching algorithm;
- generate a limited B1 development pool;
- freeze validation timestep/noise draws;
- freeze checkpoint-selection rule;
- freeze generated-sample guardrails;
- freeze evaluation code/config version.

**Human gate**  
Approve baseline definitions, metric definitions and D1 pilot config.

**Must not happen yet**

- no D1 biological fine-tuning before this gate passes.

**Current status: COMPLETE / GO — 2 October 2026.**

The human gate is GO for M5 planning only. Laura Hardy accepted the B1 development-pool evidence at `/home/laura/rnagenesis-mres-runs/m4_b1_development_pool_d2b2041520d1_gpu1_attempt1` for its diagnostic M4 role. The authorisation `m4_b1_development_pool_d2b2041520d1_gpu1_attempt1` is inactive, consumed, successful, and `consumed_complete`. Physical GPU 1 scope is preserved and this record does not claim that access to GPU 1 has been revoked. Independent revalidation found 112 invocation files, 1,000 raw records, 1,000 audited records, 1,000 valid outputs, zero invalid outputs, 961 exact-length hits, exact-hit rate 0.961, 39 early-EOS length shortfalls, zero length excesses, 1,000 unique outputs, zero duplicates, largest duplicate multiplicity 1, and largest duplicate share 0.001. The pool is a diagnostic generation sample reusable for the later paired D1 workflow. It is not an independent-biological-replicate set or an exact-length accepted production pool. `exact_length_accepted_pool_declared`, `final_production_mapping_declared`, and `final_m8_production_protocol_declared` stay false. M5 execution and D1 training stay unauthorised. Clustering-dependent and frozen-representation metrics stay deferred beyond M4. Microbatch, gradient accumulation, numerical precision, and EMA stay deferred to M5. The accepted CPU schedule, VALIDATION artifacts, and B0, B2, Phase A, and Phase B evidence were revalidated and not rewritten.

---

### M5 — Diffusion-training software smoke tests

**Objective**  
Demonstrate technical correctness of the adapted trainer.

**Inputs**

- synthetic A/C/G/U fixtures;
- optionally a tiny TRAIN-only subset after synthetic success.

**Tests**

1. dataset loading;
2. tokenisation/collation;
3. frozen latent encoding;
4. one diffusion forward pass;
5. one backward/update step;
6. frozen EncDec assertions;
7. denoiser parameter-change assertion;
8. finite loss/gradient check;
9. save/reload checkpoint;
10. resume training;
11. tiny overfit/software-behaviour test;
12. generation from saved test checkpoint.

**Outputs**

- smoke-test report;
- parameter table;
- peak GPU-memory measurement;
- feasible physical microbatch;
- checkpoint compatibility proof.

**Human gate**  
Approve transition to real-data pilot.

**Must not happen yet**

- no full TRAIN run;
- no EVAL/REF.

**Current status: COMPLETE / GO — 3 October 2026.**

The human gate is GO for M6 planning only. On 3 October 2026, Laura Hardy approved the exact reviewed documentation-only M5 evidence-acceptance and closure package by explicit authorisation in the M5 review chat, “approve to stage commit and push”, recorded at `2026-10-03T00:23+10:00`. That approval does not authorise M6 execution, biological TRAIN or VALIDATION access, D1 training, GPU use, REF, EVAL, or a new run. Attempt 3 at `/home/laura/rnagenesis-mres-runs/m5_synthetic_smoke_e8550e7_gpu1_attempt3` is the sole accepted M5 smoke evidence. Attempts 1 and 2 remain preserved failed engineering attempts and are not accepted evidence. The run exited 0, emitted `m5_smoke_manifest.json`, and emitted no failure record. Manifest SHA-256 `e82ad082d7b66adce128cf6757e36be20bf3a0289d8aa2a9b5b10754b4f53532`. After the order-independent validator correction at `9d818e11c18e33e95b48dda8b5b2a72870ca30b0`, replay with that committed contract reconstructed the canonical manifest byte for byte and left the manifest SHA unchanged. RNAGenesis was not modified and remains `mres-d1-diffusion-finetune` at `e3b855bbf4d1af376f43747643fa30afd662828c`. Execution used implementation commit `e8550e7da095cfc6f17dd001425734e4bea6a3cb` and single-use authorisation commit `d947d4eaef7cc1e7d85cdabbf83f7e02d4bfda72`. The checked-in smoke configuration stays inactive. The stored field `m5_milestone_complete` remains intentionally false in the immutable accepted manifest because the manifest records the automated correctness phase, while formal milestone completion occurred later through human review. This acceptance does not rewrite the manifest.

Physical GPU 1 was `GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, PCI `00000000:61:00.0`, NVIDIA H200 NVL. The correctness path used physical microbatch 8, gradient accumulation 4, observed effective batch 32, and FP32. Physical microbatch 8, gradient accumulation 4, and FP32 are M5-supported observations. EMA was disabled and smoke generation used raw weights. Those observations were a conservative M6 proposal at M5 acceptance. The inactive M6 package now records them as bounded pilot decisions and does not authorise a run. Loss and gradients were finite. The gradient norm was 5.4995274281909055. The denoiser update max absolute delta was 3.0040740966796875e-05. The encoder, Q-Former, query tokens, latent projection, and decoder remained frozen after backward, update, and generation. Checkpoint fresh reload, AdamW state, scheduler, global step, RNG restoration, and the subsequent resumed update passed. The tiny overfit losses were 0.6921789050102234, 0.6151523590087891, 0.5786029696464539, 0.5625630617141724, and 0.5575369596481323. Generation reloaded the immutable one-update checkpoint after the training objects were released. Training peak allocated was 42,046,809,088 bytes and training peak reserved was 42,563,796,992 bytes. Overall peak allocated was 72,871,646,208 bytes and overall peak reserved was 73,614,229,504 bytes. Total wall time was 193.7824976965785 seconds. TRAIN, VALIDATION, REF, and EVAL were not accessed.

BF16 is an observation only. The FP32 paired loss was 0.8125295639038086. The BF16 paired loss was 0.8128108978271484. The absolute difference was 0.00028133392333984375. The relative difference was 0.0003462445378457017. The comparison was finite. No acceptance tolerance was applied. It does not select production precision.

The inactive M6 pilot package now records FP32, physical microbatch 8, gradient accumulation 4, disabled EMA, and raw denoiser weights as bounded pilot decisions. It does not authorise execution. The final D1 seed count and biological training authorisation remain unresolved. Both smoke generation strings contain a leading `1` followed by 32 A/C/G/U characters. That is a decoder and control-token format observation, not a biologically valid sequence claim. Production generation or biological interpretation requires explicit output normalisation and nucleotide-alphabet validation. The M6 rule is the exact leading prefix `11` documented in [M6 pilot implementation](fine_tuning/m6_pilot_implementation.md). M5's single leading `1` does not broaden it.

---

### M6 — Small real-data D1 pilot

**Objective**  
Test the planned small-data regime on TRAIN without committing to the full experiment.

**Starting configuration**

```text
starting diffusion = B1 generic checkpoint
trainable = full denoiser only
LR = 3e-5
effective batch = 32
scheduler = cosine
warmup = ~10% planned optimizer updates
max epochs = bounded pilot
seed = prespecified pilot seed
```

**Measure**

- TRAIN denoising loss;
- fixed-draw VALIDATION loss;
- gradient norm;
- learning rate;
- peak memory;
- step time;
- generated validity/uniqueness;
- exact TRAIN copying;
- nearest-TRAIN similarity;
- gross diversity/length behavior.

**Stop/adjust conditions**

A bounded reduction to LR `1e-5` is permitted if `3e-5` shows immediate destructive adaptation, such as:

- validation loss worsens catastrophically from initialization;
- output validity collapses;
- memorisation becomes extreme within very few updates;
- training becomes numerically unstable.

Do not introduce new adaptation strategies at this stage.

**Human gate**  
Freeze the final D1 training configuration.

**Must not happen yet**

- no EVAL;
- no REF;
- no broad hyperparameter sweep.

**Implementation status: M6_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED — 3 October 2026.**

The checked-in pilot configuration is `config/experiments/D1_diffusion_pilot.yaml`. It is not consumable, `execution.authorised` is false, and it binds no GPU, output directory, or authorisation. The Python implementation contains the authorised worker behind that inactive gate, so a later authorisation-only commit can activate it without changing Python. The detailed contract, the 21-value applied learning-rate trace, the resume decision, and the storage arithmetic are in [M6 pilot implementation](fine_tuning/m6_pilot_implementation.md). This status does not authorise execution.

On 5 October 2026 the same status was revised in place. The authorised path observes model, patch, and runtime identity before biological access, isolates the worker with the M5 repository fingerprint and cache controls, validates the prepared denoiser under the fixed-draw rules, records EncDec parameter and persistent-buffer digests, and sums synchronized per-update and per-validation times. The production manifest validator checks every nested section. A later correction in the same inactive package makes the final CUDA RNG read fail closed, makes the parent reopen and validate a claimed success manifest, preserves the child's precise failure code and stage, treats `STOP_CONDITION_CODES` as the exhaustive active-path registry, and cross-checks nested validation and checkpoint evidence. The status remains `M6_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED`.

For this 21-update pilot the recorded decisions are: immutable B1 initialisation; complete EncDec frozen; full denoiser trainable; FP32; microbatch 8; accumulation 4; effective batch 32; 84 microbatches and 21 optimizer updates; final window `[8, 8, 8, 5]`; example-weighted accumulation; AdamW at `3e-5` with betas `(0.95, 0.999)`, weight decay `1e-6`, and epsilon `1e-8`; clip norm 1.0 as a clip rather than an abort; EMA disabled; raw weights for validation; seed 42; the accepted M4 validation artifacts; validation at updates 0, 7, 14, and 21; retained weights at 7, 14, and 21; no copy of B1 at update 0; no automatic reduction to `1e-5`; no learning-rate sweep; no diagnostic generation in the training runner; and `resume_supported: false`. The earlier paragraph that permits a bounded reduction to `1e-5` after destructive adaptation is not an automatic rule for this pilot. Finite validation worsening is recorded for human review. The run is not stopped by a numeric deterioration cutoff.

The M4 approval recorded in the pilot YAML remains historical. It does not make this implementation executable.

---

### M7 — Final D1 replicate training

**Objective**  
Run the approved single MRes adaptation strategy reproducibly.

**Inputs**

- complete TRAIN only;
- frozen D1 config from M6.

**Plan**

- target three prespecified independent seeds;
- maximum five epochs per run unless M6 justifies a lower fixed limit;
- save every epoch;
- evaluate fixed-draw VALIDATION after every epoch;
- calculate diagnostic generated-sample metrics at prespecified checkpoints;
- retain full logs/manifests/checkpoint hashes.

**Checkpoint selection**

Within each seed, select by lowest fixed-draw VALIDATION diffusion loss subject to hard guardrails.

The final model condition is the prespecified replicate ensemble/set of selected seed-specific checkpoints; do not cherry-pick one seed based on downstream EVAL.

**Human gate**  
Review seed consistency and freeze D1 training.

**Must not happen yet**

- no EVAL;
- no REF;
- no post-hoc architecture changes.

---

### M8 — Final development generation and VALIDATION comparison

**Objective**  
Generate the full B1 and D1 pools and complete development-time generator analysis.

**Conditions**

- B1 generic released RNAGenesis;
- B2 TRAIN-matched empirical RNA null;
- D1 MRes curated-aptamer diffusion-adapted RNAGenesis;
- B0 existing released aptamer-adapted RNAGenesis as external comparator.

**Primary generation target**

```text
30,000 raw attempts per new condition
```

B0 retains its existing 30,080 attempts.

**Primary controlled comparison**

```text
B1 vs D1
```

with B2 as the non-neural null.

B0 is a separately interpreted external aptamer-adapted comparator because its existing pool uses the 37-nt released aptamer sampling regime.

**Reference use**

- TRAIN: copying/novelty only;
- VALIDATION: held-out development distribution comparison;
- REF: prohibited;
- EVAL: prohibited.

**Human gate**  
Freeze generator checkpoint(s), generation settings and generator-level analysis.

**Must not happen yet**

- no AptaRank tuning from TRAIN;
- no REF use for RNAGenesis decisions;
- no EVAL.

---

### M9A — RNAGenesis generator freeze

**Objective**  
Create an immutable generator decision record before AptaRank calibration.

**Freeze**

- D1 checkpoint hashes;
- replicate/seed policy;
- generation parameters;
- cleaning code;
- evaluation code;
- condition definitions;
- no further RNAGenesis training.

---

### M9B — AptaRank REF calibration

**Objective**  
Fit/calibrate the empirical AptaRank reference distributions independently of RNAGenesis development.

**Input**

```text
REF only
```

**Rule**

AptaRank calibration may not alter the frozen RNAGenesis generator.

No TRAIN-based AptaRank calibration is permitted.

No EVAL is permitted.

---

### M9C — Final end-to-end pipeline freeze

Freeze:

- RNAGenesis D1;
- generation settings;
- AptaRank calibration;
- ranking/filtering configuration;
- final evaluation metrics;
- all condition names;
- statistical analysis plan.

Write an explicit EVAL-unlock record.

---

### M10 — Final EVAL assessment

**Objective**  
Perform the final held-out assessment once.

**Input**

```text
EVAL
```

Use EVAL to assess the already frozen:

- D1 generator;
- B1/B0/B2 comparisons where appropriate;
- AptaRank;
- final ranking pipeline.

After seeing EVAL:

- do not retrain RNAGenesis;
- do not recalibrate AptaRank;
- do not change thresholds to improve EVAL;
- do not return to VALIDATION and then re-open EVAL as if it were untouched.

If final results are weaker than expected, report them.

---

## 17. Generator evaluation metrics

### 17.1 Output accounting

For every condition report separately:

- raw attempted sequences;
- successfully parsed outputs;
- valid A/C/G/U outputs;
- unique valid outputs;
- duplicate outputs;
- invalid outputs;
- final metric-specific denominator.

Never silently discard invalid or duplicate generations before calculating their rates.

### 17.2 Sequence metrics

- output length;
- A/U/C/G fractions;
- GC fraction;
- mono-/dinucleotide frequencies;
- exact TRAIN overlap;
- normalized edit distance to nearest TRAIN sequence;
- maximum identity to nearest TRAIN sequence;
- sequence clustering at the frozen/project-specified identity threshold;
- cluster count;
- singleton fraction;
- largest-cluster share;
- Shannon diversity;
- effective cluster count.

### 17.3 Structure/thermodynamic metrics

Use pinned ViennaRNA.

Include:

- MFE;
- MFE/nt;
- paired fraction;
- selected length-aware secondary-structure descriptors;
- structural diversity;
- optional ensemble/conformational metrics only where their interpretation is scientifically valid.

A more negative MFE is not inherently better.

Interpret structural metrics as distributional/plausibility properties, not direct evidence of protein binding.

### 17.4 Representation-space metrics

Using a frozen representation model only:

- embedding MMD between generated conditions and VALIDATION/EVAL as permitted by stage;
- optional nearest-neighbour/coverage diagnostics.

Do not train a representation model on EVAL.

### 17.5 Statistical reporting

Prefer:

- full distributions;
- effect sizes;
- seed-level summaries;
- confidence intervals respecting generation/training seed structure;
- length stratification where relevant.

Avoid relying on tiny p-values produced only by having tens of thousands of generated sequences.

---

## 18. Development versus final evaluation

### 18.1 Development evaluation

Uses:

```text
TRAIN      -> fit / copying diagnostics
VALIDATION -> checkpoint + development model decisions
```

Questions include:

- did denoising loss improve on held-out aptamer latents?;
- did generation remain valid/diverse?;
- did D1 move toward held-out aptamer distributions relative to B1?;
- is there evidence of memorisation or mode collapse?;
- is the result stable across training/generation seeds?

### 18.2 REF

REF is not generator evaluation data.

REF enters only after RNAGenesis freeze, for AptaRank empirical calibration.

### 18.3 Final evaluation

Uses:

```text
EVAL only after M9C freeze
```

This yields the final held-out estimate of the generator/ranking pipeline selected without EVAL access.

---

## 19. Risk register

| Risk | Severity | Detection | Mitigation |
|---|---:|---|---|
| Generic checkpoint provenance insufficiently documented | Medium | asset/release review | use conservative condition name `generic released RNAGenesis`; record uncertainty |
| Full denoiser overfits 669 sequences | High | VALIDATION loss; TRAIN copying; diversity collapse | low LR; few updates; save all epochs; fixed guardrails |
| Upstream random split leaks/repartitions frozen roles | Blocker | code review/tests | bypass/remove automatic split; explicit TRAIN/VALIDATION loader |
| EncDec accidentally becomes trainable | Blocker | parameter/gradient/tensor assertions | fail closed |
| REF used for RNAGenesis decisions | Blocker | role guards/manifests | software rejection; keep REF off training workspace where possible |
| EVAL contamination | Blocker | role guards + physical absence | no EVAL transfer until M10 |
| B0 mislabelled as unadapted | High | condition registry/review | fixed terminology in Section 4 |
| B0 37-nt pool compared naively with length-matched conditions | High | metric review | treat B0 as external comparator; normalize/stratify length-sensitive metrics |
| B1 length matching fails due early EOS | Medium | M4 length experiment | documented matching/resampling design before 30k generation |
| Existing B2 implementation differs from frozen protocol | Medium | code audit | correct/reuse before regeneration; record diff |
| Modified chemistry overinterpreted | Medium | methods review | model base sequence only; preserve chemistry metadata; explicit wording |
| AdaLayerNorm patch omitted after environment rebuild | High | startup verification | automated patch/hash check |
| Default/authorised GPU occupied by other users | High | `nvidia-smi` before run | postpone or, only if explicitly authorised for that session, use GPU1; never kill other users' processes |
| Single training seed understates uncertainty | Medium | run registry | target three final D1 seeds |
| Extensive hyperparameter tuning consumes MRes scope | High | milestone gate | one approved strategy; bounded LR repair only |
| Generation sample size produces misleading significance | Medium | stats review | effect sizes/seed-aware uncertainty; not raw-N p-values |

---

## 20. Essential MRes experiments, optional work and PhD extensions

### 20.1 Essential MRes work

- B1 generic released RNAGenesis baseline;
- B2 TRAIN-matched empirical RNA null regeneration;
- D1 diffusion-only adaptation from B1;
- existing B0 external aptamer-adapted comparator;
- frozen VALIDATION checkpoint selection;
- multiple D1 training seeds where feasible;
- memorisation/diversity analysis;
- final generator freeze;
- REF-only AptaRank calibration;
- EVAL-only final assessment.

### 20.2 Useful only if time remains and already supported by the core analysis

- limited legacy reproduction of RNAGenesis aptamer metrics;
- dinucleotide-preserving shuffled structural-control baseline;
- additional representation-space visualisation;
- richer uncertainty/bootstrap analysis.

These must not delay the essential experiment.

### 20.3 Explicit PhD extensions

- LoRA/PEFT diffusion adaptation;
- layer-selective diffusion adaptation;
- formal comparison of full versus parameter-efficient fine-tuning;
- Q-Former adaptation;
- decoder adaptation;
- joint latent-space realignment;
- target-conditioned RNA generation;
- protein-structure or protein-embedding conditioning;
- KPC/NDM/OXA-specific adaptation;
- active-learning loops with wet-lab feedback;
- reinforcement/inference-time optimisation for target interaction;
- explicit representation of modified RNA chemistry.

---

## 21. Completion criteria

The MRes RNAGenesis modelling implementation is complete when:

1. the frozen role/hash contract is implemented and tested;
2. TRAIN/VALIDATION are verified without repartitioning;
3. REF and EVAL are excluded from model development;
4. the upstream diffusion trainer has been reviewed and project-specific modifications are version controlled;
5. the released `EncDec` is demonstrably frozen;
6. only the D1 denoiser is trainable;
7. the B1 generic checkpoint is recorded and hashed;
8. the B0 existing 30,080 pool is fully manifested and correctly labelled;
9. B2 has been regenerated to 30,000 raw sequences using verified TRAIN-derived statistics;
10. B1 and D1 primary pools use the approved TRAIN-length matching method;
11. the D1 pilot passes technical and scientific guardrails;
12. the approved final D1 configuration has been run using the prespecified final seeds or a documented deviation;
13. selected D1 checkpoints are chosen using VALIDATION only;14. B1/B2/D1 development comparisons use VALIDATION rather than REF;
15. RNAGenesis is frozen before REF is used for AptaRank;
16. AptaRank is calibrated from REF only;
17. EVAL is unlocked only after the complete pipeline freeze;
18. every thesis result is reproducible from committed code/configuration plus recorded input/model hashes;
19. terminology in Section 4 is used consistently in methods, results and discussion;
20. claims remain limited to unconditional aptamer-domain adaptation and downstream computational prioritisation rather than target-specific binding.

---

## 22. Immediate next actions

M0 is COMPLETE / GO — 25 September 2026. M1 is COMPLETE / GO — 28 September 2026. M2 is COMPLETE / GO — 28 September 2026. M3 is COMPLETE / GO — 29 September 2026, as recorded in [M3 frozen corpus loader and modelling interface](fine_tuning/m3_frozen_corpus_loader_and_modelling_interface.md). The RNAGenesis implementation commit is `e3b855bbf4d1af376f43747643fa30afd662828c`. M4 is COMPLETE / GO — 2 October 2026, for M5 planning only. M5 is COMPLETE / GO — 3 October 2026, for M6 planning only. The M6 pilot package is ready for review and is not authorised. Biological fine-tuning is not authorised. M6 execution is not authorised. This does not authorise biological TRAIN or VALIDATION access, D1 training, GPU use, REF, EVAL, or a new run.

Proceed in this order:

1. Review the inactive M6 package. Do not execute M6, do not access biological TRAIN or VALIDATION, and do not begin D1 training;
2. a biological D1 pilot only after a later, separate execution authorisation;
3. M7 and later only after those gates pass.

---

## 23. Strategy decision record

**Decision:** GO with D1 full latent-diffusion denoiser fine-tuning from the generic released RNAGenesis checkpoint, with the complete released sequence autoencoder frozen.

**Reasons:**

1. **small-data inductive bias:** preserves the pretrained sequence representation/decoder instead of relearning them from 669 sequences;
2. **architectural consistency:** adapts the probability distribution over an unchanged latent space;
3. **released-code support:** directly matches the upstream RNAGenesis fine-tuning design;
4. **experimental clarity:** B1 and D1 share architecture/checkpoint family and differ primarily by MRes TRAIN adaptation;
5. **MRes scope:** avoids turning adaptation architecture search into the project;
6. **methodological contribution:** focuses the research contribution on leakage-safe small-data adaptation, validation, reproducibility and rigorous generator evaluation rather than on an unsupported bespoke training pathway.

**Alternatives considered and deferred:**

- LoRA/PEFT diffusion — promising small-data PhD extension but introduces adapter-placement/rank choices unsupported by current released RNAGenesis workflow;
- partial diffusion unfreezing — arbitrary layer-selection boundary without evidence;
- Q-Former/decoder fine-tuning — higher direct memorisation risk and moves the latent coordinate system while leaving the generative prior mismatched;
- joint autoencoder/diffusion training — data-hungry and substantially beyond MRes scope;
- diffusion from scratch — discards the strongest available pretrained prior and is inappropriate for 669 sequences.

This decision remains in force unless a documented implementation failure demonstrates that D1 cannot be executed with the released assets/code. Any such failure requires a new human-reviewed strategy decision rather than an implicit fallback.