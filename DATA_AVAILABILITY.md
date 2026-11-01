# Data and model availability

This is a thesis companion containing software, provenance and selected research
outputs. It is not a redistribution of the complete source databases or frozen
sequence corpus. Availability is separate from the [software licence](LICENSE_SCOPE.md).

## Corpus sources and derivatives

| Material | Repository disposition |
| --- | --- |
| AptaIndex sequence records, bulk exports and sequence-bearing derivatives | Not distributed. The combined frozen corpus includes 54 AptaIndex identities, so the complete TRAIN/VALIDATION/REF/EVAL sequence files are withheld. |
| AptaIndex record-level derivatives without sequences | Retained where useful for decisions and provenance, including IDs, review outcomes and metadata. |
| AptaBase examples and permitted source material | Retained. AptaBase is a publicly available, more permissive source; source attribution and terms still apply. |
| Other literature/database sources and published reference sequences | Retained only as already tracked examples, references or derivatives; source terms are not replaced by MIT. Consult the source rules and registry. |
| Aggregate corpus profiles, counts, decisions and manifests | Retained for auditability. A hash or local path identifies an input without distributing its contents. |
| Foundation-model-generated sequences and aggregate evaluation results | Retained, including the final thesis filtered 50 and the historical v3.10 hand-off. These are computational outputs, not demonstrated binders. |

The source inventory and handling are documented in
[source preparation](docs/data_curation/source_preparation_methodology.md),
[source configurations](config/global_s4_sources/) and
[curation decisions](docs/dataset_decisions.md). The [final corpus build](docs/data_curation/global_s7d_final_build.md)
and [training split](docs/data_curation/global_s7c_ft_train_validation.md) record
identities, counts and hashes. Rebuilding the full corpus requires the original
inputs and appropriate source access; it cannot be reproduced from public
aggregates alone.

## Results and thesis material

The [results index](results/README.md) separates final analyses from historical
smoke tests and baselines. Many raw AptaRank exports, source snapshots and large
run artifacts remain ignored. Their absence is documented in the corresponding
manifests. The [final filtered selection](results/aptarank/evaluation/thesis_filtered_shortlist/README.md)
provides 50 generated sequences and a sequence-free inventory of all 137 eligible
candidates; its provenance identifies the frozen source exports.

The thesis PDF and complete personal bibliography are not bundled. The root
[reference list](REFERENCES.md) and [BibTeX subset](references.bib) contain selected
scholarly metadata, without local attachment paths, abstracts or personal notes.

## Model code and checkpoints

- Original RNAGenesis implementation: [upstream repository](https://github.com/zaixizhang/RNAGenesis).
- Original released model assets: [upstream Zenodo record 15203813](https://zenodo.org/records/15203813).
- Adaptation training implementation: [MRes training branch pinned at e3b855b](https://github.com/laura-hardy/RNAGenesis/tree/e3b855bbf4d1af376f43747643fa30afd662828c), including `train_diffusion_mres.py`.
- Adapted D1 weights: stored separately on Zenodo, as reported by the repository owner. The adapted-record DOI/link has not yet been verified in this companion. The upstream Zenodo record above identifies the original release and must not be substituted for the adapted-model record.

This Git repository does not distribute model weights. The selected D1 checkpoints
are both epoch 5, update 105; their recorded weight-file SHA-256 identities are:

| Training seed | SHA-256 |
| --- | --- |
| 43 | `c0797888bde9033cc15b056c8c09e70b9f7fba0fb21b1f3840a4f1efb77031ab` |
| 44 | `d0fcb5174230b8bbbc6bfe59eabda9b37687c03800012bc1a6981cc215469ed5` |

See [selected-replicate evidence](docs/fine_tuning/m7_final_replicates_implementation.md),
[model asset manifest](docs/fine_tuning/model_asset_manifest.md) and
[environment manifest](docs/fine_tuning/environment_manifest.md). A full rerun
requires external assets, the frozen corpus and suitable GPU resources. Model
weights and source data retain their own licensing conditions.
