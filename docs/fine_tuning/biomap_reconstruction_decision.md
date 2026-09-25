# M0 biomap/xTrimoPGLM reconstruction decision — 25 September 2026

**Status: human-approved reconstruction boundary. Full M0: incomplete.**
Laura approved the published/released encoder call convention in
[Experimental Boundary Checklist](chatgpt-conversation://6ab4891a-ab80-83ec-809e-f9e59c792c00)
after review of the read-only compatibility report. This record documents
that approval; it does not claim that dependency integration, strict runtime
weight loading or end-to-end latent verification has been completed.

## Approved decision and unchanged scientific design

Restore the biomap encoder with `xTrimoPGLMModel` and `xTrimoPGLMTokenizer`
from `Zaixi/RNAGenesis`, pinned to revision
`d8a42130984cbf04f6a5e16a3aa0c0d6578036a8`. The source/config/tokenizer
hashes are recorded in the [model asset manifest](model_asset_manifest.md#pinned-biomap-encoder-dependency).
Load encoder weights from the released RNAGenesis `EncDec` checkpoint's
`encoder.*` tensors, not from external Hugging Face weights.

Use `encoder(input_ids)` with **no explicit `position_ids` and no encoder
`attention_mask`**. This follows the pinned published `AutoModel` embedding
example and the released RNAGenesis `struct_pred` convention.

The D1 design remains unchanged: freeze the complete released `EncDec`,
including encoder, Q-Former, query-token embeddings, latent projection and
ProGen decoder; train only the complete `TransformerDenoiser`, initialised
from B1 at `configs/rnagenesis/diffusion`. B0 at
`checkpoints/Aptamer/diffusion` remains a comparator, not D1 initialisation.
TRAIN/VALIDATION roles, REF/EVAL restrictions, the fixed-stochastic-draw
VALIDATION denoising-loss selection rule and all milestone gates remain in
force under the [implementation plan](../fine-tuning-implementation-plan.md).

## Approved sequence-to-latent path

| Stage | Contract |
| --- | --- |
| Sequence | Canonical A/C/G/U, with the frozen alphabet/role checks; no silent rewriting or new split |
| Tokenisation | `tokenizer.convert_tokens_to_ids(sequence)`, character-wise; `pad=0`, `U=1`, `G=2`, `C=3`, `A=4`; no BOS/CLS/EOS additions |
| Collation | Pad with ID 0; `input_ids` is `[B, L]`; the frozen collator mask is `[B, L]`, true where `input_ids != 0` |
| Encoder | Pinned `xTrimoPGLMModel`, using released `EncDec` encoder weights; call `encoder(input_ids)` only |
| Encoder output | `outputs.last_hidden_state` is sequence-first `[L, B, 1280]` |
| Orientation | `transpose(0, 1)` gives batch-first `[B, L, 1280]` |
| Q-Former | `encoder_hidden_states` receives `[B, L, 1280]`; `encoder_attention_mask` receives the frozen collator `[B, L]` mask |
| Diffusion latent | `qt_out.last_hidden_state`, retaining all 32 queries: `[B, 32, 160]`, before `transform` |
| Decoding | The released `EncDec.generate` path applies `transform` afterward, before ProGen decoding |

The ordinary `tokenizer(sequence)` API is not interchangeable with the
published character-wise conversion: the compatibility report found
whitespace tokenisation and invalid scalar special-token ID properties under
the inspected environment. In particular, padding ID 0 comes from the base
vocabulary/collator, not from `convert_tokens_to_ids("<pad>")`.

Frozen latent extraction uses eval mode and `torch.no_grad()` together with
explicit `requires_grad=False` for the complete `EncDec`. Runtime freeze
assertions remain required by the plan; `no_grad()` alone is not proof that
the whole representation/decoder stack is frozen.

## Evidence and its limits

The following findings come from the compatibility report attached to the
approval conversation, not from new model execution in this documentation
task. The RNAGenesis inspection baseline was
`d00899eef60d664cc7b5880c0bb43f2a9e7a1b01`.

- **Encoder identity:** all 433 released `encoder.*` tensors matched the
  pinned `xTrimoPGLMModel` state dict exactly in key, shape and FP32 dtype,
  after removing the outer `encoder.` prefix. No missing/unexpected keys or
  shape/dtype mismatches were found. This identifies the base model class,
  not the `xTrimoPGLMForMaskedLM` wrapper.
- **Tokenisation:** the pinned `tokenizer.model` and tokenizer implementation
  establish the nucleotide IDs. The pinned `README.md`/`example_usage.py` and
  released `struct_pred/data/dataset.py:178-179` and
  `struct_pred/predict.py:153-154` use character-wise conversion.
- **Call and orientation:** released `struct_pred/model/network.py:328-331`
  calls `self.encoder(input_ids)` and permutes the sequence-first hidden
  state to batch-first. Pinned `modeling_xtrimopglm.py:172-184,899-944`
  supplies the matching orientation evidence. The probe measured only the
  embedding/convolution shapes on meta tensors; the 32-layer transformer
  and complete `get_latent` path were not executed.
- **Q-Former/latent:** released `models/autoencoder/modeling_qt.py:564-567`
  requires batch-first cross-attention states and mask. Its query embeddings
  and output contract retain `[B, 32, 160]`; the released generation/decoder
  path places `transform` after the diffusion latent.
- **Position IDs:** the pinned base model leaves `position_ids` optional and
  does not construct them when omitted. Its rotary operation runs only when
  positions are supplied. The checkpoint's `rotary_emb.inv_freq` buffers are
  class-defined buffers, not evidence that the missing training method
  supplied positions. Their presence does not override the approved
  published call convention.
- **Encoder masking:** the inspected base-model path calls `get_masks`
  without overriding its default causal behaviour when a padded mask is
  supplied, despite the non-causal config. The published call avoids this
  path; the padding mask is applied only at Q-Former cross-attention.

The initial report withheld implementation pending a position-ID decision.
The subsequent human approval resolves that implementation choice in favour
of the published/released call; it does not turn it into recovered historical
source or runtime evidence.

## Residual uncertainty and remaining implementation checks

**The missing historical `EncDec.get_latent` source has not been published
or recovered in the inspected release/history.** We cannot establish whether
the original training method explicitly supplied position IDs or otherwise
used the exact approved call. Tensor compatibility and released usage support
this reconstruction, but do not prove numerical equivalence to the missing
historical training path. This limitation must remain in implementation and
methods reporting even after synthetic runtime checks pass. Any change to
the approved call requires a new documented human-reviewed decision.

The encoder identity, nucleotide mapping and output orientation are resolved
by the recorded evidence. Dependency restoration and runtime verification
remain outstanding. Clean import currently fails on `deepspeed` and missing
`quantization.py`; the metadata probe used in-process stubs. The pinned
config has `quantization_bit=0`. Resolve these import issues narrowly during
implementation, record any local integration changes, and preserve
`xTrimoPGLMModel.forward` and the approved scientific path.

The first implementation verification is synthetic-only: strictly load all
released encoder tensors; verify character-wise IDs, padding, transpose and
Q-Former mask routing; confirm `[B, 32, 160]` pre-`transform` latents and
deterministic repeated eval-mode encoding; and verify that the complete
`EncDec` is frozen. Do not import `train_diffusion.py` or access biological
TRAIN/VALIDATION for that dependency-restoration check. Full M0 and the later
training gates remain incomplete; this record authorises no training run.

## M0 plan arithmetic housekeeping

For 669 unique TRAIN cores and effective batch 32 on one GPU, retaining the
final partial batch and stepping a final incomplete accumulation window gives
`ceil(669 / 32) = 21` optimizer updates per epoch and `5 * 21 = 105` over the
five-epoch maximum. This corrects the previous approximately 22/110 estimate;
it does not change the data, batch target, epoch limit or optimisation design.
The actual loader/accumulation count and derived warmup integer must be
recorded before execution using Sections 11.4-11.5 of the implementation plan.

This change records documentation only. No data, curation outputs, AptaRank
drafts, RNAGenesis code, training configs or model assets are changed.
