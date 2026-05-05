# Dataset decisions for RNAGenesis aptamer fine-tuning

**Project:** Towards prediction-guided generative design of RNA aptamers against carbapenemase targets  
**Created:** 2026-05-05  
**Working files:** `docs/dataset_search_log.xlsx`, `docs/dataset_decisions.md`

## 1. Search objective

The objective of this search is to identify whether target-specific RNA aptamer training data exists for KPC, NDM, and OXA-48 carbapenemases, and if not, to assemble a defensible general RNA aptamer corpus for adapting or evaluating RNAGenesis. The search is intentionally structured from most specific to most general: target-specific HT-SELEX datasets first, then curated aptamer databases and general HT-SELEX datasets, followed by structure resources and synthetic-data options.

## 2. Working decision framework

### Case 1: target-specific HT-SELEX dataset found

If public HT-SELEX or deep-sequencing SELEX data is found for KPC-2, NDM-1, OXA-48, or a close carbapenemase relative, that dataset should become the primary fine-tuning dataset, subject to quality, format, and sequence-count checks.

### Case 2: target-specific HT-SELEX dataset absent

If no usable target-specific HT-SELEX dataset is found, the project will use a general RNA aptamer corpus for aptamer-like sequence adaptation, with known carbapenemase-binding aptamers reserved as evaluation references rather than as a fine-tuning set. This is currently the likely pathway, but the Part A search must be completed before this is stated as the final decision.

## 3. Search log status

The detailed evidence log is maintained in `docs/dataset_search_log.xlsx`. Each row records the source, URL, search terms, date accessed, result summary, sequence count where known, format, availability, relevance, status, and next action.

## 4. Target-specific dataset search: preliminary status

Initial web probing did not identify an obvious public target-specific HT-SELEX dataset for KPC, NDM, or OXA-48. However, this is not yet sufficient evidence to conclude absence. The next step is to manually run and log the full NCBI GEO and SRA searches listed in the plan, including zero-result or irrelevant-result searches.

Papers already identified for target-specific aptamers should be treated as evaluation-reference sources unless they contain large supplementary sequence pools:

| Paper/source | Target/status | Current use decision | Next action |
|---|---|---|---|
| Yu et al. 2021 | KPC-2 / KPC-2-expressing bacteria | Candidate positive-reference source | Check full text, methods, supplementary sequence tables, data availability |
| Chen et al. 2020 | NDM-related target to verify | Candidate positive-reference source | Locate full citation and supplement |
| Shi et al. 2025 | Carbapenemase target to verify | Candidate positive-reference source | Locate full citation and supplement |
| Sabrowski et al. 2022 | NDM-1 / His-tag masking context to verify | Use cautiously | Determine whether aptamers bind NDM-1 itself, His-tag, or target construct |

## 5. Candidate general training corpus

### 5.1 AptaDiff Dataset A

AptaDiff Dataset A is the anchor candidate because it is directly related to the RNAGenesis/AptaDiff aptamer benchmark pathway. Published descriptions report 13,802 RNA sequences from six SELEX rounds targeting IGFBP3. Before inclusion, the local files need to be downloaded, counted, and checked for sequence alphabet, round labels, duplicate sequences, and compatibility with the RNAGenesis/AptaDiff format.

Planned local path:

```text
data/raw/aptadiff_dataset_A/
```

Required README fields:

```text
Source:
URL:
Download date:
Target:
Sequence type:
Sequence count:
SELEX rounds:
Original file names:
Processing performed:
Known limitations:
```

### 5.2 UTexas Aptamer Database / Zenodo

The UTexas Aptamer Database is a strong candidate for broad corpus construction because it provides a downloadable literature-curated snapshot. It should be filtered to RNA sequences with known targets, preferably proteins/enzymes, length approximately 20-120 nt, and non-duplicated entries. Target labels should be normalised to support later enzyme/protein subset analysis.

### 5.3 AptaDB

AptaDB should be used as a cross-reference and possible corpus expansion source. The key task is to export or manually extract RNA entries that are not already present in the UTexas dataset, prioritising protein/enzyme targets and any beta-lactamase/carbapenemase-related records.

### 5.4 Apta-Index and older databases

Apta-Index and older resources should be searched mainly for coverage and defensibility. If bulk export is not available, only target-relevant or high-value RNA protein aptamers should be manually logged.

### 5.5 RaptGen and RaptRanker datasets

RaptGen and RaptRanker should be checked for usable HT-SELEX sequence files or supplementary datasets. Even if the datasets are not directly reusable, both papers are relevant methodologically because they use HT-SELEX data for aptamer generation/ranking.

## 6. Inclusion criteria

A dataset or sequence collection should be included in the training corpus only if it satisfies most of the following:

- RNA sequence or clearly convertible RNA sequence representation.
- Derived from SELEX, HT-SELEX, or a literature-curated aptamer entry.
- Known target, preferably protein or enzyme.
- Usable sequence format: FASTA, CSV, FASTQ, TSV, or plain text.
- Sufficient sequence quality: standard nucleotide alphabet after cleaning, length approximately 20-120 nt unless justified.
- Not duplicated from another corpus source.
- Licence or access conditions compatible with research use.

DNA aptamers should not be included in the primary RNA fine-tuning corpus unless a specific cross-modal augmentation experiment is later justified. They may still be logged as background evidence or excluded records.

## 7. Evaluation reference sequences

Known binders from target-specific SELEX papers should be extracted into the `Evaluation Sequences` sheet of the workbook. These should be used as positive references for qualitative comparison, target-specific benchmarking, and sanity-checking of candidate-ranking outputs. They are not expected to provide enough data for fine-tuning.

Required fields for each sequence:

```text
Paper/source
Target claimed
Aptamer name
Sequence
Sequence type
Length
Binding metric
Selection method
Rounds
Supplement source
Use in project
Status
Notes
```

## 8. Target structures

KPC-2, NDM-1, and OXA-48 structures should be downloaded from RCSB PDB and logged in the `Target Structures` sheet. For each target, prioritise high-resolution experimental structures, preferably better than 2.0 Å where available. Apo structures are preferred for docking-like evaluation, but inhibitor-bound structures may be useful for identifying binding-pocket geometry.

Planned local path:

```text
data/structures/
```

Required metadata:

```text
Target
PDB ID
Resolution
Method
Organism
Ligand state
Chain to use
Publication
File path
Known issues
```

## 9. Synthetic-data decision: provisional note

Full in silico SELEX simulation is currently considered outside MRes scope because it would require a defensible RNA-protein binding score, simulated selection rounds, and substantial validation. A simpler fallback is structure-based RNA augmentation using ViennaRNA to generate sequences with aptamer-like structural properties, such as controlled length, GC content, stem-loop content, and MFE range. This should only be used if the real RNA aptamer corpus is too small, and synthetic sequences should be labelled as low-confidence or pre-warming data rather than treated as equivalent to experimental SELEX sequences.

## 10. Immediate next actions

1. Complete target-specific NCBI GEO searches and log results, including zero-result searches.
2. Complete target-specific NCBI SRA searches and log BioProject/publication links for any hits.
3. Download and validate AptaDiff Dataset A.
4. Download the UTexas Aptamer Database Zenodo snapshot and begin filtering RNA entries.
5. Review the four target-specific SELEX papers and extract final aptamer sequences.
6. Search RCSB PDB for KPC-2, NDM-1, and OXA-48 structures.
7. Update this document with evidence after each search session.

## 11. Final decision placeholder

**Final case:** Pending.  
**Final training corpus:** Pending.  
**Evaluation references:** Pending extraction.  
**Structures selected:** Pending.  
**Synthetic data decision:** Pending final corpus-size assessment.
