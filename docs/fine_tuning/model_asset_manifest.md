# M0 model asset manifest — 25 September 2026

**Model-asset inventory: recorded. Full M0: incomplete.** No training,
generation, optimiser construction, biological-data access or GPU computation
was performed. These hashes describe the released RNAGenesis checkout after
its tracked working tree was restored to clean. They do not authorise a
training run.

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

| Checkpoint | Tensor count | Exact parameter count | Dtype parameter counts |
| --- | ---: | ---: | --- |
| B1 | 366 | 1,961,920,992 | F32: 1,961,920,992 |
| B0 | 366 | 1,961,920,992 | F32: 1,961,920,992 |

Comparison of the two safetensors files:

```text
same tensor names = true
same tensor shapes = true
same parameter count = true
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
names and shapes, and both contain exactly 1,961,920,992 FP32 parameters.

## Exact denoiser parameter count

The exact full `TransformerDenoiser` parameter count is:

```text
1,961,920,992
```

This is the intended D1 trainable-model parameter count because the approved
strategy trains the complete denoiser. Every recorded parameter is F32.
This count comes from safetensors metadata. It was not inferred from
checkpoint file size.

Optimiser membership and `requires_grad` were not measured. Those runtime
properties must still be independently verified during trainer integration
and M5. This manifest does not claim that the optimiser contains only
denoiser parameters, or that `EncDec` parameters have
`requires_grad=False`.

## What is and is not a runtime dependency

Established for the released RNA generation path, and required for D1:

- frozen EncDec configuration and `pytorch_model.bin`;
- the two RNA decoder/tokenizer JSON files named above;
- the B1 diffusion directory as the denoiser initialisation.

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

## Unresolved verification

Trainer integration and M5 must still verify, before any optimiser is built
on biological data:

1. the loaded denoiser parameter count equals 1,961,920,992;
2. optimiser membership is exactly the complete `TransformerDenoiser`;
3. `requires_grad` is false for every `EncDec` parameter, including encoder,
   Q-Former, query-token, latent-projection and decoder parameters;
4. the loaded weight hashes equal the B1 hashes in this manifest;
5. the B0 weight file is not the loaded initialisation.

The architecture fields opened in the two `unet/config.json` files are
recorded in the B1 versus B0 section above. Optimiser membership and
`requires_grad` remain unverified.

## Remaining M0 work

This manifest does not complete M0. The local data-contract checkpoint is a
separate record. H200 development-profile validation, proof that REF and
EVAL are absent from the training workspace, RNAGenesis code-integration
review, and the M0 human gate remain outside this document.

GPU1 was explicitly authorised for this session on 25 September 2026 and was
not used. That authorisation is session-specific. GPU0 remains the project
default.
