# RNAGenesis aptamer MRes companion

Code, configurations, provenance records and computational results accompanying
**Laura Hardy, _Towards Prediction-Guided Generative Design of RNA Aptamers_,
Master of Research, School of Computing, Macquarie University, November 2026.**

This project investigates adaptation of the RNAGenesis RNA foundation model to
curated aptamer data and uses AptaRank to prioritise generated candidates for
NDM-1. Its results concern sequence distributions and computational ranking.
The candidates have not been experimentally validated for binding or inhibition.

## Start here

| Reader task | Entry point |
| --- | --- |
| Locate evidence for a thesis section | [Thesis guide](docs/THESIS_GUIDE.md) |
| Inspect the final 50 candidates in Table A.13 | [Thesis filtered selection](results/aptarank/evaluation/thesis_filtered_shortlist/README.md) |
| Find closed generator and AptaRank results | [Results index](results/README.md) |
| Understand what is available to reproduce | [Data and model availability](DATA_AVAILABILITY.md) |
| Run checks without private data or a GPU | [Environment records and CPU checks](environment/README.md) |
| Cite the work or its dependencies | [References](REFERENCES.md), [BibTeX](references.bib), [citation metadata](CITATION.cff) |

## What the thesis evaluated

The curated corpus contains 1,170 aptamer identities, 1,031 unique core sequences
and 790 clusters across 409 targets. Cluster-separated TRAIN, VALIDATION, REF and
EVAL roles support adaptation and evaluation. The corpus incorporates sources
with different redistribution terms; it is not bundled as a downloadable dataset.
See [availability](DATA_AVAILABILITY.md) before attempting a complete rerun.

D1 adaptation freezes the encoder–decoder and trains the latent transformer
denoiser. Two replicates, seeds 43 and 44, each supply an epoch-5, update-105
checkpoint. Generation and evaluation distinguish four conditions:

| Label | Condition | Comparison role |
| --- | --- | --- |
| B0 | Released RNAGenesis aptamer-adapted checkpoint | External descriptive comparator; historical output contains 30,080 attempts, all 36 nt |
| B1 | Released generic RNAGenesis checkpoint | Matched baseline: 30,000 attempts |
| B2 | TRAIN-matched empirical independent-base null | Statistical baseline: 30,000 attempts |
| D1 | MRes aptamer-adapted diffusion model | Two replicates, 15,000 attempts each |

D1 is closer to EVAL than B1 on all three prespecified distribution metrics, but
B2 is closer on all three. This supports a distributional shift rather than a
claim that D1 has demonstrated higher-order aptamer properties. Tier 1 evaluation
shows modest discrimination; Tier 2 evidence is weak to mixed. See the
[thesis guide](docs/THESIS_GUIDE.md) for the corresponding reports and limitations.

## Final thesis candidate selection

The [final filtered selection](results/aptarank/evaluation/thesis_filtered_shortlist/README.md)
implements thesis §4.6 and Table A.13: within the exact Tier 2 top 1,000, require
shuffle pass and moderate or strong compatibility, then retain the first 50 of
137 eligible candidates in frozen Tier 1 rank order. All 50 sequences and their
identifiers, ranks, lengths, training seeds, blocks and rounded scores have been
checked against the supplied thesis. No scores were recomputed.

The earlier [v3.10 hand-off](results/aptarank/evaluation/future_shortlisting_sequences/README.md)
retains unfiltered Tier 1 ranks 1–50. It is preserved as a historical artifact and
is superseded for the final thesis selection. Some frozen supervisor reports and
plans still describe that earlier disposition. Their paths and bytes remain
unchanged for provenance; use the new filtered directory for the final list.
Both sets are computational candidates for future work, not validated binders.

## Repository map and reproduction

- `scripts/`: curation, generation orchestration, filtering and evaluation code.
- `config/`: source rules, experiment settings and recorded decisions.
- `docs/`: methods and execution records, indexed in the [documentation guide](docs/README.md).
- `results/`: committed outputs and aggregate analyses; see the [results index](results/README.md).
- `target/`: NDM-1 structure and pocket preparation, with its own [reproduction guide](target/README.md).
- `environment/`: historical machine exports and bounded CPU checks.

The adapted model training implementation lives in the separate public
[RNAGenesis training branch](https://github.com/laura-hardy/RNAGenesis/tree/e3b855bbf4d1af376f43747643fa30afd662828c).
The AptaRank application lives in [its own repository](https://github.com/alishahsvnd/AptaRank).
This repository provides the MRes orchestration and evidence around those tools.
A full training or generation rerun requires external model assets, suitable GPU
resources and the original corpus. The environment exports are historical
records; a fresh end-to-end installation has not been verified.

Existing thesis paths and hash-bound compatibility copies are retained.
Historical run configurations contain consumed execution settings and local paths;
consult their recorded contracts rather than treating them as fresh run commands.

## Citation and licence

Please cite the thesis using [CITATION.cff](CITATION.cff) or the
`hardy_mres_2026` entry in [references.bib](references.bib), and identify the
repository commit used. The [reference guide](REFERENCES.md) credits the source
model, ranking framework, datasets and supporting tools. A public thesis DOI or
repository release DOI can be added when issued.

Project-owned software and associated technical documentation use the
[MIT licence](LICENSE). See [licence scope](LICENSE_SCOPE.md) and
[third-party notices](THIRD_PARTY_NOTICES.md) for material governed by other terms.
