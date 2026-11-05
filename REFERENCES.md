# Citation and selected references

Preferred thesis citation:

Hardy, Laura (2026). *Towards Prediction-Guided Generative Design of RNA
Aptamers*. Master of Research thesis, School of Computing, Macquarie University.

Use [CITATION.cff](CITATION.cff) for citation software and
[references.bib](references.bib) for BibTeX. Identify the repository commit when
citing computational artifacts. No thesis DOI, software release DOI or ORCID is
asserted here; add verified identifiers when issued.

The list below is a selected dependency and methods bibliography, drawn from the
supplied thesis and bibliography. It is not the full thesis bibliography.

## Research software and framework

The AptaRank paper is listed in the thesis as accepted to the IEEE ICDM 2026
demonstration track. Proceedings details and a paper DOI were not supplied; the
link below identifies its implementation, not a published proceedings record.
The MRes RNAGenesis training implementation is available on the
[pinned training branch](https://github.com/laura-hardy/RNAGenesis/tree/e3b855bbf4d1af376f43747643fa30afd662828c).
The original B1 generic and B0 aptamer-adapted checkpoints are distributed in the
[RNAGenesis Zenodo release (DOI 10.5281/zenodo.15203813)](https://zenodo.org/records/15203813).
Their archive paths and the separate MRes D1 checkpoint identities are documented
in [model availability](DATA_AVAILABILITY.md).

- Hardy, Laura et al. (2026). [AptaRank: Interpretable Ranking and Target-Aware Annotation of Foundation-Model-Generated RNA Aptamers](https://github.com/alishahsvnd/AptaRank).

- Zhang, Zaixi et al. (2024). [RNAGenesis: A Generalist Foundation Model for Functional RNA Therapeutics](https://doi.org/10.1101/2024.12.30.630826).

- Wang, Zhen et al. (2024). [AptaDiff: de novo design and optimization of aptamers based on diffusion models](https://doi.org/10.1093/bib/bbae517). Briefings in Bioinformatics.

- Lorenz, Ronny et al. (2011). [ViennaRNA Package 2.0](https://doi.org/10.1186/1748-7188-6-26). Algorithms for Molecular Biology : AMB.

- Le Guilloux, Vincent et al. (2009). [Fpocket: An open source platform for ligand pocket detection](https://doi.org/10.1186/1471-2105-10-168). BMC Bioinformatics.

- Steinegger, Martin and Söding, Johannes (2017). [MMseqs2 enables sensitive protein sequence searching for the analysis of massive data sets](https://doi.org/10.1038/nbt.3988). Nature Biotechnology.

- Huang, Ying et al. (2010). [CD-HIT Suite: a web server for clustering and comparing biological sequences](https://doi.org/10.1093/bioinformatics/btq003). Bioinformatics.

- Zhang, Hongmin et al. (2018). [Active-Site Conformational Fluctuations Promote the Enzymatic Activity of NDM-1](https://doi.org/10.1128/AAC.01579-18). Antimicrobial Agents and Chemotherapy.

- King, Dustin and Strynadka, Natalie (2011). [Crystal structure of New Delhi metallo‐beta‐lactamase reveals molecular basis for antibiotic resistance](https://doi.org/10.1002/pro.697). Protein Science.

- Berman, Helen M. et al. (2000). [The Protein Data Bank](https://doi.org/10.1093/nar/28.1.235). Nucleic Acids Research.

- Chen, Long et al. (2024). [AptaDB: a comprehensive database integrating aptamer–target interactions](https://doi.org/10.1261/rna.079784.123). RNA.

- Vinay Bachu et al. (2021). [Aptabase: An aptamer database](https://www.iitg.ac.in/proj/aptabase/).

## Source attribution and licences

The [source preparation methodology](docs/data_curation/source_preparation_methodology.md)
and [source configurations](config/global_s4_sources/) provide the broader dataset
inventory, including AptaIndex, AptaBase, AptaDB, AptamerBase, RiboAptamer,
literature and sequence-archive sources. Citation does not grant redistribution
permission. See [data availability](DATA_AVAILABILITY.md), [licence scope](LICENSE_SCOPE.md)
and [third-party notices](THIRD_PARTY_NOTICES.md).
