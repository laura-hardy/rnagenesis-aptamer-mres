# M0 model asset manifest — 25 September 2026

**Model-asset inventory: recorded. M0: COMPLETE / GO — 25 September 2026.**
The hashes below are the 25 September asset inspection. They were not
re-measured by the clean preflight. That preflight, recorded in
[M0 data contract verification](m0_data_contract_verification.md), passed
after denoiser parameter accounting was corrected. M0 completion does not
mean biological fine-tuning has run, and this manifest does not authorise
the D1 fitting run.

## Purpose

This manifest records the released assets that define the D1 initialisation
boundary and identifies the B0 comparator that must stay outside that
initialisation.

D1 is the released frozen `EncDec`, plus the generic released RNAGenesis
diffusion checkpoint B1 as initialisation, plus a trainable complete
`TransformerDenoiser` only. B0 is the released aptamer-adapted comparator.
B0 must not be used as D1 initialisation.

Canonical condition names follow the implementation plan:
`B1_generic_released_rnagenesis`, `B0_released_aptamer_rnagenesis`, and
`D1_mres_curated_aptamer_diffusion_adapted`.

## RNAGenesis source state

```text
repository: /home/laura/RNAGenesis
commit:     d00899eef60d664cc7b5880c0bb43f2a9e7a1b01
subject:    Update README.md
```

The tracked working tree was restored to clean before the asset inventory.
Paths below are relative to that repository. Exact on-disk byte sizes were
measured during the H200 inspection for the required asset set listed below.
No sizes are recorded for any other files.

## Released loading path

Released `generation.py` loads the autoencoder with
`EncDec.from_pretrained(args.enc_dec_file)`. It loads diffusion with
`Pipeline1D.from_pretrained(args.dm_file)` and then takes
`model = diffusion_pipeline.unet`.

The released RNA configuration used for this classification is:

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

The biomap RNA path does not instantiate `facebook/esm2_t6_8M_UR50D`. That
string remains in the general config. It is not a runtime model dependency
for this released RNA path.

The RNA decoder architecture and tokenizer resolve from:

```text
models/autoencoder/decoder/progen_configs/config-progen2-small-rna_tokenizer_v2.json
models/autoencoder/decoder/progen_configs/tokenizer_rna_v2.json
```

### Pinned biomap encoder dependency

The subsequent read-only compatibility inspection identified the missing
biomap encoder class and tokenizer. The [human-approved reconstruction
decision](biomap_reconstruction_decision.md) records the call convention and
the remaining uncertainty about the historical `get_latent` source.

```text
external repository: Zaixi/RNAGenesis
revision: d8a42130984cbf04f6a5e16a3aa0c0d6578036a8
H200 source directory: /home/laura/rnagenesis-external/Zaixi-RNAGenesis-d8a4213
encoder class: xTrimoPGLMModel
tokenizer class: xTrimoPGLMTokenizer
```

Source/config/tokenizer files are pinned to this revision. The seven hashes
below were reported as matching before and after the compatibility inspection
in *Experimental Boundary Checklist* on 25 September 2026; they were not
remeasured in this documentation update. Paths are relative to the external
source directory, not the RNAGenesis checkout.

| File | SHA256 |
| --- | --- |
| `config.json` | `bf7ef6843232f370f3f7fc37d608f85cb0ff0d75291eed35cef52213e34978f7` |
| `configuration_xtrimopglm.py` | `0319ade99c137c3ba47b9e49396be0b0ae4ac63ab02c54420b323891437a6844` |
| `modeling_xtrimopglm.py` | `cfbf899a55bd34fe3ff4bf8f6e7fc4ad74fdca2edb28f0203cc4bfad40a87602` |
| `tokenization_xtrimopglm.py` | `6a176d9f27d7f3650c1f3eb9728ae7bccbe008c432a80639f093382eb2d1d81e` |
| `tokenizer.model` | `482251d7ac279f7a3f308b2f4356190742b2d065429502baa9015cb53a99365c` |
| `tokenizer_config.json` | `93fe4fc340c4f156ea3e4cb8f0373f6d69e9876a2036f1b99317b8c8403bc34a` |
| `special_tokens_map.json` | `50d488a23997fc928a51db1311bc131b942aba6e21e8f2df1f84124ffa28b760` |

Use the external files only to recover the class/config/tokenizer. All encoder
weights must come from the released `configs/rnagenesis/autoencoder/pytorch_model.bin`
`encoder.*` state recorded below; do not download or substitute the external
Hugging Face weights. The inspection found exact key, shape and FP32 dtype
compatibility for all 433 encoder tensors, with no missing or unexpected keys.
This was a metadata/meta-device comparison, not a completed strict runtime
weight load or end-to-end latent test.

Clean modeling-module import remains blocked by `deepspeed` and missing
`quantization.py`; the inspection used in-process stubs without editing the
pinned files. The pinned config has `quantization_bit=0`. Narrow import
integration and manifesting of any local changes remain implementation work
and must preserve `xTrimoPGLMModel.forward` and the approved call convention.

## Required D1 assets

| Asset | Role | Size | SHA256 |
| --- | --- | --- | --- |
| `configs/rnagenesis/autoencoder/config.json` | Frozen EncDec configuration | 530 bytes | `ab309231b75405af3e2ef6fe49e4e74c1b96021ef2a4f61b46e5796b8799378a` |
| `configs/rnagenesis/autoencoder/pytorch_model.bin` | Frozen EncDec weights | 3,476,049,782 bytes | `3c4e34f7626c94416d504c16569b5f3f785fffe77889b9886344477b95e74c68` |
| `models/autoencoder/decoder/progen_configs/config-progen2-small-rna_tokenizer_v2.json` | RNA decoder architecture interpretation | 915 bytes | `42f15517e05ce96d78337fbc1bf20ffc580424fe88cbfcb2c81550b17cc7283e` |
| `models/autoencoder/decoder/progen_configs/tokenizer_rna_v2.json` | RNA tokenizer interpretation | 1,317 bytes | `6d8a20879cec3544cf0f33b0d481fbd5ead6a2bead2dbf1649449172c8336921` |
| `configs/rnagenesis/diffusion/model_index.json` | B1 pipeline index; mandatory D1 initialisation | 217 bytes | `05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e` |
| `configs/rnagenesis/diffusion/scheduler/scheduler_config.json` | B1 scheduler configuration; mandatory D1 initialisation | 492 bytes | `6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396` |
| `configs/rnagenesis/diffusion/unet/config.json` | B1 `TransformerDenoiser` configuration; mandatory D1 initialisation | 531 bytes | `3a9975ff165bbd5ca82923e6ed1c5ed7eb383a23f4f3f55db713c995031f8ee3` |
| `configs/rnagenesis/diffusion/unet/diffusion_pytorch_model.safetensors` | B1 denoiser weights; mandatory D1 initialisation | 7,847,725,416 bytes | `c268021b6cab37423e3bffd495b139bb69698d8d11c7b96477fbfb239b0cff26` |

B1 is the generic released RNAGenesis diffusion checkpoint at
`configs/rnagenesis/diffusion`.

## B0 comparator assets

B0 is the released aptamer-adapted RNAGenesis checkpoint at
`checkpoints/Aptamer/diffusion`. It is recorded so it can be distinguished
from B1. It is not a D1 initialisation asset.

| Asset | Role | Size | SHA256 |
| --- | --- | --- | --- |
| `checkpoints/Aptamer/diffusion/model_index.json` | B0 pipeline index | 217 bytes | `05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e` |
| `checkpoints/Aptamer/diffusion/scheduler/scheduler_config.json` | B0 scheduler configuration | 492 bytes | `6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396` |
| `checkpoints/Aptamer/diffusion/unet/config.json` | B0 denoiser configuration | 549 bytes | `fab9c517efba8269c0edf194b7d0379f317e93da0f849b5ce815e098088b4756` |
| `checkpoints/Aptamer/diffusion/unet/diffusion_pytorch_model.safetensors` | B0 denoiser weights | 7,847,725,416 bytes | `149f012287b1ae83865c25867d7c0bbe0952fa51bcc068e259725092d5dff0ca` |

## B0 generated-pool record — 28 September 2026

This section records the existing B0 sequence pool. It does not replace
the checkpoint inventory above, and it does not authorise D1 training.

Role: external aptamer-adapted comparator pool. Scientific label:
`B0_released_aptamer_adapted_RNAGenesis`. Provenance classification:
`DIRECT_HUMAN_CONFIRMED_PROVENANCE`. On 28 September 2026, Laura Hardy
confirmed that the ten tracked chunks are the pool she generated earlier
in 2026 from the authors’ released aptamer-fine-tuned checkpoint. The
authoritative account is
[M2 published aptamer comparator verification](m2_published_aptamer_comparator_verification.md).

The pool is not D1 initialisation, not the generic or pretrained-only
checkpoint, and not the length-matched causal baseline. Historical paths
under `results/phase4_1_unadapted_rnagenesis_30k/` keep an obsolete name.
That name is not the condition label.

| Quantity | Value |
| --- | --- |
| Raw records | 30,080 |
| Accepted records | 30,080 |
| Rejected records | 0 |
| Unique accepted | 30,080 |
| Duplicate accepted | 0 |
| Cleaned length | 36 on every record |
| Nominal `max_seq_len` | 37 |
| Numeric raw concatenation SHA-256 | `ed612277105c6b8747fc7365cc6b67fa8a94e8e5e8e64ee535ecadcb37ff4aaa` |
| Pooled cleaned SHA-256 | `51ccf2b997f1e6386438be303e5affaf908f102bd098bab243a2a9ba1d94d6e1` |
| Pooled evidence JSON SHA-256 | `83ad84ee3c1cf49e8cbcd88cd31cd5580dbf16fb2994e7bba715c8b356f70f1d` |

Limitations, recorded and not treated as resolved: no contemporaneous
10 June checkpoint hash was retained, so the B0 weight hash in the table
above does not prove the historical checkpoint bytes. The limited
published aptamer metric is `INFEASIBLE_WITH_RELEASED_EVIDENCE`; no
metric was calculated. Syntactic A/C/G/U acceptance is not biological
quality. The human gate is GO. On 28 September 2026, Laura Hardy approved
B0 as the external aptamer-adapted comparator. Formal M2 is
COMPLETE / GO — 28 September 2026. M3 is the next formal milestone. No
GPU is currently authorised for later work. Numerical diffusion-training
smoke remains formal M5.

## B1 versus B0

`model_index.json` and `scheduler/scheduler_config.json` have identical
SHA256 values in B1 and B0. The denoiser configuration and weight files do
not:

| File | B1 SHA256 | B0 SHA256 | Identical |
| --- | --- | --- | --- |
| `model_index.json` | `05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e` | `05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e` | yes |
| `scheduler/scheduler_config.json` | `6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396` | `6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396` | yes |
| `unet/config.json` | `3a9975ff165bbd5ca82923e6ed1c5ed7eb383a23f4f3f55db713c995031f8ee3` | `fab9c517efba8269c0edf194b7d0379f317e93da0f849b5ce815e098088b4756` | no |
| `unet/diffusion_pytorch_model.safetensors` | `c268021b6cab37423e3bffd495b139bb69698d8d11c7b96477fbfb239b0cff26` | `149f012287b1ae83865c25867d7c0bbe0952fa51bcc068e259725092d5dff0ca` | no |

Safetensors metadata inspection:

| Checkpoint | Tensor count | Serialized FP32 elements | Dtype element counts |
| --- | ---: | ---: | --- |
| B1 | 366 | 1,961,920,992 | F32: 1,961,920,992 |
| B0 | 366 | 1,961,920,992 | F32: 1,961,920,992 |

Comparison of the two safetensors files:

```text
same tensor names = true
same tensor shapes = true
same serialized element count = true
```

Both `unet/config.json` files were opened. Every architecture field inspected
was the same:

```text
_class_name = TransformerDenoiser
activation_fn = geglu
attention_bias = false
attention_head_dim = 128
cross_attention_dim = null
double_self_attention = false
dropout = 0.1
in_channels = 160
norm_elementwise_affine = true
norm_type = ada_norm
num_attention_heads = 16
num_embeds_ada_norm = 2000
num_layers = 24
num_positional_embeddings = 1024
positional_embeddings = sinusoidal
```

The observed config difference is provenance/path metadata, not an
architectural difference:

```text
B1 generic:  _name_or_path = "../../checkpoint-27500"
B0 aptamer:  _name_or_path = "../../../../configs/rnagenesis/diffusion"
```

`_name_or_path` records a path string stored in each config. It does not
change the inspected architecture. The 531-byte and 549-byte file sizes
match that metadata difference. Both denoiser weight files are
7,847,725,416 bytes and still have different SHA256 values, so equal length
does not make the weights interchangeable. B1 and B0 have identical tensor
names and shapes, and both contain exactly 1,961,920,992 FP32 elements.
That safetensors total is the serialized state. It is not the runtime
`nn.Parameter` count: it includes registered sinusoidal position buffers.
The runtime split is in the next section.

## Exact denoiser parameter count

Safetensors inspection on 25 September 2026 counted 1,961,920,992 FP32
elements and labelled them parameters. The clean M0 preflight corrected
that label.

Runtime counts at RNAGenesis `e20f556`, before any optimizer step:

```text
denoiser parameter count = 1,911,589,344
trainable parameter count = 1,911,589,344
registered buffer elements = 50,331,648
serialized state elements = 1,961,920,992
```

`1,911,589,344 + 50,331,648 = 1,961,920,992`. The 50,331,648 buffer
elements are 24 registered `transformer_blocks.0`–`23.pos_embed.pe`
buffers. Every safetensors element inspected earlier is F32. The count
was not inferred from the 7.4 GB checkpoint size.

The first preflight correctly failed on the old assertion that the loaded
denoiser parameter count equals 1,961,920,992. That failure happened before
optimizer construction. RNAGenesis `e20f556` (`Correct denoiser parameter
accounting`) separated parameters from those buffers. The clean corrected
preflight then passed, with `EncDec` frozen and the trainable count equal
to the denoiser parameter count. `EMA = false`.

This manifest still does not claim that an optimizer was built or stepped,
or that loaded weight hashes were recomputed during the preflight.

## What is and is not a runtime dependency

Established for the released RNA generation path, and required for D1:

- frozen EncDec configuration and `pytorch_model.bin`;
- the two RNA decoder/tokenizer JSON files named above;
- the B1 diffusion directory as the denoiser initialisation.

For the approved D1 sequence-to-latent reconstruction, also restore the pinned
biomap source/config/tokenizer dependency above. This encoder tokenizer is
distinct from the RNA decoder tokenizer; both retain their recorded roles.

Present in the checkout, and not established as a required D1 runtime asset
at M0:

```text
models/autoencoder/decoder/checkpoints/progen2-small/pytorch_model.bin
```

No runtime use of that standalone checkpoint was found in the released
generation path. Its SHA256 was not measured here.

`facebook/esm2_t6_8M_UR50D` remains a string in the general config. The
biomap RNA path does not instantiate it, so it is not a runtime model
dependency for this released RNA path.

## Verification after the asset inspection

The clean M0 preflight closed the parameter-count check: the loaded denoiser
parameter count is 1,911,589,344, not the 1,961,920,992 serialized-element
total, and `EncDec frozen = true`.

Still not established by the recorded preflight facts, and still required
before a biological optimisation step by the plan's frozen-model assertions:

1. optimiser membership is exactly the complete `TransformerDenoiser`;
2. loaded weight hashes equal the B1 hashes in this manifest;
3. the B0 weight file is not the loaded initialisation.

Section 10.2 also requires those freeze assertions again after the first
optimisation update. That update has not happened. These open checks do not
keep M0 incomplete; they belong to M1 smoke validation and the later fitting
gates.

The metadata compatibility probe did not execute strict loading of every
released `encoder.*` tensor, the approved sequence-to-Q-Former path, latent
shape `[B, 32, 160]`, or deterministic repeated encoding. The clean preflight
record does not add those measurements. Historical-source uncertainty about
the missing `get_latent` remains as recorded in the reconstruction decision.
The architecture fields opened in the two `unet/config.json` files stay in
the B1 versus B0 section above.

## M0 status

M0 is COMPLETE / GO. The development-profile preflight, REF/EVAL access
record, RNAGenesis integration commits and human gate are in
[M0 data contract verification](m0_data_contract_verification.md). This
manifest remains the asset inventory. M0 completion does not authorise
biological fine-tuning.

GPU1 was explicitly authorised for the asset-inspection session on
25 September 2026 and was not used for that inspection. That authorisation
is session-specific. GPU0 remains the project default.
