# Raw data state assessment (refreshed)

**Project:** RNAGenesis aptamer MRes
**Assessment date:** 2026-08-04 (refresh)
**Previous inventory baseline:** `docs/data_curation/_prior_raw_data_inventory.csv` (snapshot of the first inventory)
**Scope path:** `data/raw/`

**Outputs:**

| File | Role |
|---|---|
| `docs/data_curation/raw_data_inventory.csv` | Per-file inventory (extended schema) |
| `docs/data_curation/raw_data_workbook_sheets.csv` | Per-sheet XLSX metadata |
| `docs/data_curation/raw_data_inventory_summary.json` | Rollups, overlaps, change summary |
| `docs/data_curation/raw_data_curation_questions.csv` | Machine-readable Q1–Q6 answers |
| `scripts/data_preparation/inventory_raw_data.py` | Read-only inventory script |

**Immutability:** No files under `data/raw` were modified by this refresh. Pre/post SHA-256 fingerprints matched for all 203 raw files.

Evidence classes used below:

- **Documented** — stated in a local README/About/QC note or official source page
- **Observed** — measured from file bytes/schema/counts
- **Inferred** — reasonable interpretation combining the above
- **Unresolved** — insufficient evidence

---

## 1. Purpose and scope

Refresh the raw-data inventory after local dataset updates (new AptaDB interaction export, corrected RiboAptamer sequences, Precision-SELEX README, deletion of `li_et_al`), incorporate README evidence, and answer curation-planning questions for Stage S0 design.

Still out of scope: cleaning, normalisation, exclusion, moves, renames, deduplication of underlying datasets.

---

## 2. Inspection methodology

1. Snapshot prior inventory CSV for change detection.
2. Fingerprint all `data/raw` files (SHA-256) before inspection.
3. Re-run extended `inventory_raw_data.py` (stdlib only; latin-1 fallback for AptaDB CSVs).
4. Read local README/About/QC documentation under `data/raw`.
5. Answer Q1–Q6 with targeted audits (join counts, Category tallies, workbook XML layout, ENA ID field stats).
6. Consult AptaDB About page / publication for schema confirmation (Q3).
7. Re-fingerprint after inspection to confirm read-only behaviour.

Sampling notes: FASTQ/EMBL deep QC remains sample-based where previously flagged; PDF body text was not exhaustively re-parsed beyond local README extracts for selektion/precision.

---

## 3. Changes since the previous inventory

Comparison baseline: first inventory CSV snapshotted to `_prior_raw_data_inventory.csv` (hashes, row counts, column names).

### 3.1 Added files (5)

| Path | Notes |
|---|---|
| `data/raw/AptaDB/interaction.csv` | Official-style interaction bridge export (1350 rows) |
| `data/raw/riboaptamer/all_sequences_509_rows.csv` | Corrected full-sequence RiboAptamer table (509 rows) |
| `data/raw/precision_selex_against_kpc2_paper/README_extracted_data.md` | Detailed schema/biology README |
| `data/raw/precision_selex_against_kpc2_paper/~$extracted_data.xlsx` | Excel lock/temp file (unreadable as workbook) |
| `data/raw/riboaptamer/.DS_Store` | OS metadata |

### 3.2 Removed files (3)

| Path | Notes |
|---|---|
| `data/raw/li_et_al/pone.0086729.s001.xlsx` | Deliberately removed; unresolved provenance (see Q4) |
| `data/raw/riboaptamer/rna_aptamer_seqs.csv` | Truncated predecessor superseded by `all_sequences_509_rows.csv` |
| `data/raw/riboaptamer/rna_aptamer_seqs.xlsx` | Same predecessor pair |

### 3.3 Modified content (2)

Only OS metadata hashes changed:

- `data/raw/.DS_Store`
- `data/raw/ENA/.DS_Store`

No scientific data file content hashes changed relative to the prior inventory.

**Decode note (not a content change):** AptaDB `aptamer.csv` column labels decode differently under latin-1 vs UTF-8 replacement for the `µg/µl` header token; SHA-256 is unchanged. Inventory now records this as `unchanged_bytes_schema_decode_diff` rather than a false modification.

### 3.4 Changed row counts / schemas (material)

| Asset | Change |
|---|---|
| RiboAptamer | Truncated 509-row CSV/XLSX removed → full `all_sequences_509_rows.csv` (509 rows; richer columns including Affinity, PubMed, mmCIF) |
| AptaDB | New `interaction.csv` (1350 × Apta_index/TargetID/…) |
| Precision-SELEX | New README documenting true multi-row header (inventory still sees row-1 layout headers unless README-aware parsing is used) |
| `li_et_al` | Source directory gone |

### 3.5 Newly documented meanings

- Precision-SELEX workbook columns, DNA nature, XK-10 validation, count semantics (**documented** in README).
- Selektion D9 clones as RNA SELEX reported in DNA alphabet (**documented** in `selektion_paper/readme.rtf`).
- AptaDB interaction bridge enabling aptamer↔protein joins (**documented** on AptaDB About + **observed** locally).

### 3.6 Processing-state changes

- RiboAptamer corrected export is now the authoritative local file; truncated pair deleted.
- ENA review_v2 selected file remains the in-`data/raw` curated selected set; a **processed** finalize output also exists outside raw (see Q1).
- `li_et_al` no longer an active source.

### 3.7 Questions resolved vs remaining

| Resolved / improved by this refresh | Still unresolved |
|---|---|
| AptaDB join key (via `interaction.csv`) | Whether processed ENA supplement should become Stage S0 input after restoring `experiment_group_id` |
| RiboAptamer truncated sequences | RiboAptamer Category→protein ontology mapping |
| Precision-SELEX schema | Exact primer boundaries for “truncated” constructs |
| Selektion RNA vs DNA interpretation | Full dissertation methods page citations beyond README |
| `li_et_al` absence | Original Li et al. supplement identity if ever re-added |
| | rbms Zenodo / InstructNA FASTQs still not local |
| | Empty `near_duplicate_family_id` singleton policy |

---

## 4. Raw-data directory overview

**Current totals:** 29 directories, **203 files**, ~118 MB.

`li_et_al/` is gone. New/changed highlights:

```text
data/raw/AptaDB/
  aptamer.csv
  protein.csv
  interaction.csv          # NEW bridge table
  AptaDB_ About.pdf

data/raw/riboaptamer/
  all_sequences_509_rows.csv   # NEW corrected sequences
  readme.rtf
  # rna_aptamer_seqs.csv/.xlsx REMOVED (truncated)

data/raw/precision_selex_against_kpc2_paper/
  extracted_data.xlsx
  README_extracted_data.md     # NEW
  paper.pdf
  ~$extracted_data.xlsx        # temp lock file

# data/raw/li_et_al/           # REMOVED
```

ENA layout unchanged in structure: EMBL download + inspection/candidates/review/review_v2 derived products.

---

## 5. Dataset-by-dataset inventory (updated)

### ENA

- **Authoritative original download:** `ena_embl_20260720-0853.txt` (5841 records) — **observed**.
- **Authoritative selected output inside raw:** `review_v2/ena_selected_after_manual_review.csv` (679 rows) — **observed**; contains `experiment_group_id` and `near_duplicate_family_id` (Q1).
- **Derived:** inspection/, candidates/, review/, review_v2/ templates/provenance/rejected.
- **Outside raw (note):** `data/processed/ena/ena_aptamer_supplement_clean.csv` (676) finalised from selected; loses dedicated `experiment_group_id` column (has `supporting_experiment_group_ids` instead).
- **S0 recommendation:** EMBL = authoritative raw input; review_v2 selected = curated ENA lane input; other ENA CSVs = derived_output_not_raw_input.

### AptaDB

- **Files:** aptamer (1293), protein (194), **interaction (1350)**, About PDF.
- **Join:** `interaction.Apta_index` ↔ `aptamer.Apta_index`; protein rows via `interaction.TargetID` ↔ `protein.Uni-port ID` when `Target chemistry=Protein` (Q3) — **high confidence**.
- **S0:** include all three CSVs as authoritative inputs.

### RiboAptamer

- **Authoritative:** `all_sequences_509_rows.csv` (509) — full sequences (**observed**).
- **Docs:** readme.rtf (Ribocentre-aptamer) — brief.
- **Category:** 15 clean labels; protein vs small-molecule split not 1:1 with Category (Q2).
- **S0:** include_as_authoritative_input with Category caveat.

### Precision-SELEX (KPC-2)

- **Extract:** `extracted_data.xlsx` + **README_extracted_data.md**.
- **Biology (documented):** ssDNA Precision-SELEX; target KPC-2; 20 XK aptamers; primary sequence column B (N40).
- **S0:** include_with_documented_caveat / manually extracted DNA eval source.

### Selektion (NDM-1 D9)

- **Extract:** `table6_d9_ndm1_sequences.csv` (7 clones) + `data.xlsx` + detailed readme.rtf.
- **Molecule type (documented):** RNA SELEX; sequences printed as DNA alphabet; optional T→U for RNA representation (Q6).
- **S0:** include as eval-reference RNA (alphabet caveat).

### Other sources (brief)

Unchanged in substance from prior assessment: AptaDiff A/B/C/D, UTexas, AptaIndex, AptaBase, AptamerBase, NCBI folders, chen/shi extracts, SRA metadata, instructNA script-only, rbms README-only.

---

## 6. Questions informing the data curation plan

Full machine-readable answers: `docs/data_curation/raw_data_curation_questions.csv`.

### Q1 — New / final ENA file

**Status:** partially_resolved

**In-raw final selected file:**

| Field | Value |
|---|---|
| Path | `data/raw/ENA/review_v2/ena_selected_after_manual_review.csv` |
| Rows | 679 |
| Columns | 37 |
| `experiment_group_id` | Present; 679/679 non-null (0% missing); 25 unique; duplicates **expected** (shared SELEX/experiment groups; max 131 rows/group) |
| `near_duplicate_family_id` | Present; 367/679 non-null (**45.95% missing**); 56 unique; duplicates expected within families; empties align with blank `near_duplicate_family_size` → **inferred** singletons / no multi-member family |
| Multi-ID provenance | `experiment_group_ids` has 126 multi-value (`\|`) rows; 3 rows have `consolidated_from_n_units` ∈ {2,11} retaining multiple `review_unit_ids` / accessions |

**Authoritative?** Yes for the **raw curated selected lane**.

**Processed companion:** `data/processed/ena/ena_aptamer_supplement_clean.csv` (676 rows) retains `near_duplicate_family_id` but **not** `experiment_group_id` (only `supporting_experiment_group_ids`). For Stage S0 ID requirements, prefer the review_v2 selected file or amend the finalize export.

### Q2 — Corrected RiboAptamer file

**Status:** resolved

| Field | Value |
|---|---|
| Path | `data/raw/riboaptamer/all_sequences_509_rows.csv` |
| Rows | 509 |
| Columns | Sequence Name, Aptamer Name, Category, Type, Article name, Sequence, Length, GC Content, Discovery Year, Affinity (Kd), Description, PubMed Link, mmCIF Download URL |
| Evidence corrected | Replaces deleted truncated CSV/XLSX; only 1/509 sequences contain `...`; length distribution spans tens–100+ nt |
| Superseded | `rna_aptamer_seqs.csv`, `rna_aptamer_seqs.xlsx` (removed) |

**Category counts (no missing):** Mammalian 198; Viral 96; Fluorophores 42; Pharmaceuticals 32; Nucleosides & Nucleotides 25; Bacteria 22; Other 22; Cell 20; RNA 17; Amino Acids & Peptides 11; Biologics & Signaling Molecules 9; Prion 7; Toxin 4; Synthetic 3; Parasite 1.

No spelling/case/whitespace duplicate labels among the 15 values. Protein-oriented vs small-molecule-oriented groupings are **inferred** only (see questions CSV); do not collapse yet.

### Q3 — AptaDB aptamer↔protein join

**Status:** resolved (confidence **high**)

1. **Join method:** `interaction.csv` bridges `aptamer.Apta_index` to targets; protein targets use `TargetID = protein.Uni-port ID` when `Target chemistry = Protein`.
2. **Evidence:** AptaDB About download table (Interaction/Aptamer/Protein); publication (Aptamer ID + Target ID / UniProt); local overlap audit.
3. **Audit:** 1350 interactions; 1256/1293 aptamers linked; 37 aptamers unmatched; 639 protein interactions all match 194 UniProt IDs; all proteins appear ≥1 time; many-to-many.
4. **Examples:** Apta_1/Apta_2 → A6MI22 (HIV-1 Tat, RNA aptamers); Apta_3 → E0Z2R8 (influenza HA, DNA).
5. **Contradictions:** none for protein chemistry; Molecule/Cell/Other TargetIDs correctly absent from `protein.csv`; molecule/cell/other CSVs not downloaded locally.
6. **Curation implication:** structured protein targets **can** be attached now; free-text E5 fallback not required for protein-linked AptaDB rows. Non-protein targets need additional exports.

### Q4 — Deleted `li_et_al`

**Status:** not_applicable

Confirmed absent under `data/raw`; not in current inventory; no residual extracts found. Recorded as deliberately removed for unresolved provenance. Do not reconstruct.

### Q5 — Precision-SELEX workbook

**Status:** resolved

| Item | Finding |
|---|---|
| Sheets | `Sheet1` only |
| Layout | Multi-row header (rows 1–3); blank spacer rows; many merged cells; 20 data records |
| Sequence columns | **B** `Sequences of N40 from 5' to 3'` (primary 40-nt); **D** construct/truncated library sequence |
| Alphabet | DNA / ssDNA (A/C/G/T) — **documented** + **observed** |
| `Repeat times` | Row-1 merged label over count columns F–I — **not** a per-aptamer measurement column |
| Counts | F–I = round4/round8 × library1/library2 observation counts |

Schema interpretation (proposed future fields):

| Col | Header (row 2) | Sample | Inferred meaning | Confidence | Proposed field |
|---|---|---|---|---|---|
| A | Aptamer-ID | XK-1 | Clone/candidate ID | high | aptamer_id |
| B | Sequences of N40… | ACCCCA… (40 nt) | Selected region DNA | high | sequence_n40_dna_5to3 |
| C | ΔG | -2.4 | ΔG for N40 | high | delta_g_n40_kcal_mol |
| D | Truncated sequences… | GGCAGG… | Construct DNA | high | sequence_construct_dna_5to3 |
| E | ΔG | -5.51 | ΔG for construct | high | delta_g_construct_kcal_mol |
| F | The fourth round (library 2) | 0 | Round4 lib2 count | high | count_round4_library2 |
| G | The fourth round (library 1) | 0 | Round4 lib1 count | high | count_round4_library1 |
| H | The eighth round (library 2) | 2 | Round8 lib2 count | high | count_round8_library2 |
| I | The eighth round (library ) | 0 | Round8 lib1 count (heading incomplete) | medium | count_round8_library1 |
| J | Target | KPC-2 | Target | high | target_reported |

### Q6 — Selektion D9 RNA or DNA?

**Status:** resolved (confidence **high** for experimental RNA)

1. Table path: `data/raw/selektion_paper/table6_d9_ndm1_sequences.csv` (+ `data.xlsx`).
2. Clones: D902, D907, D909, D913, D914, D918, D920.
3. Printed alphabet: DNA letters with T (**observed**).
4. Experimental molecule: RNA SELEX / RNA aptamers (**documented** in readme.rtf).
5. Canonical curation interpretation: **DNA-encoded representation of RNA aptamers**.
6. Future normalisation: optional T→U into a derived RNA field; retain reported DNA-alphabet string.
7. Supporting docs: local README (“RNA SELEX”; “reports them with T rather than U”; convert T→U only if RNA alphabet required).

---

## 7. Source-level assessment with Stage S0 recommendations

| source | authoritative file(s) | obsolete/superseded | state | approx records | sequence type | target type | binding | provenance | ID quality | S0 issues | recommended_S0_status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ENA | `ena_embl_*.txt`; selected: `review_v2/ena_selected_after_manual_review.csv` | v1 empty selected; most inspection/candidates | original + heavy derived | 5841 / 679 selected | RNA (often T deposited; selected U) | protein-oriented curated | evidence fields | high | high in selected | derived leakage in raw; ndfam empties; processed loses experiment_group_id | EMBL: include_as_authoritative_input; selected: derived_output_not_raw_input **but Stage S0 curated input**; others: derived_output_not_raw_input |
| AptaDB | aptamer/protein/**interaction** | — | official exports | 1293 / 194 / 1350 | mixed DNA/RNA | protein via join; also mol/cell/other | buffer/pubmed in interaction | high | high (Apta_index, UniProt) | missing molecule/cell CSVs | include_as_authoritative_input |
| RiboAptamer | `all_sequences_509_rows.csv` | truncated csv/xlsx removed | corrected export | 509 | RNA-like (U common) | Category (mixed ontology) | Affinity column | medium | medium | Category protein mapping | include_as_authoritative_input |
| Aptadiff_datasetA | `datasetA_IGFBP3_P6.csv` | x_z embeddings optional | original | 13803 | DNA/T | implied IGFBP3 | p6 counts | medium | low | no target column | include_as_authoritative_input |
| Aptadiff_otherdata | B csv; C/D fastq | — | original-ish | 11547 + ~202k reads | DNA/T | B: PTK7 by name | p6 / none | medium | low | FASTQ adapters/target | include_with_documented_caveat |
| UTexas | Sept2023 xlsx | — | snapshot | 1894 | mixed | protein/other | Kd/affinity | high | medium | missing seqs; labels | include_as_authoritative_input |
| AptaIndex | export csv | — | export | 1050 | mixed+mods | yes | affinity | medium | medium | chemical notation | include_with_documented_caveat |
| aptabase | html + raw csv | cleaned is derivative | scrape | 610 | mixed | yes | affinity | high | medium | cleaned in raw | raw: include; cleaned: derived |
| aptamerbase | aptamers csv | — | export | 2128 | RNA-like | via labels | flags | medium | medium | missing seqs | include_as_authoritative_input |
| NCBI_nucleotide | *.gb | — | downloads | 18 | per-record | features | unclear | medium-low | accession in file | opaque names | include_with_documented_caveat |
| NCBI PDF folders | pdfs | — | documentary | — | — | — | — | documentary | — | no tables | not_relevant_to_protein_aptamer_corpus |
| chen / shi | curated csv | — | manual | 8 / 2 | DNA | bacterium/protein context | Kd (chen) | high | high | tiny; Chen≡Shi XK10 | include_with_documented_caveat (eval) |
| selektion_paper | table6 csv | — | manual extract | 7 | RNA via DNA alphabet | NDM-1 | weak binding notes | high | clone_id | small-n | include_with_documented_caveat (eval) |
| precision_selex… | extracted xlsx | — | manual extract | 20 aptamers | ssDNA | KPC-2 protein | counts≠Kd | high w/ README | XK-IDs | layout header | include_with_documented_caveat |
| instructNA / rbms | script / README | — | pointers | — | — | — | — | external | — | data absent | hold_for_manual_review |
| sra_metadata_ndm1… | SraRunInfo | — | metadata | 8 runs | — | — | — | medium | SRR | no reads | hold_for_manual_review |
| li_et_al | — | deleted | removed | — | — | — | — | unresolved | — | gone | exclude_due_to_provenance |

---

## 8. Schema and metadata observations (refresh)

- Extended inventory columns now capture documentation links, S0 status, hashes, supersession, and README snippets.
- Workbook sheet CSV lists UTexas (`Dataset`, 1894×28), Precision-SELEX (`Sheet1`, layout headers), selektion `data.xlsx`.
- Precision-SELEX inventory row_count remains layout-oriented (43 XML rows including spacers); README states 20 aptamer records after blank removal — **documented vs observed discrepancy** to handle in cleaning, not by rewriting the xlsx now.

---

## 9. Sequence / target / duplication notes

Prior findings stand, with updates:

- RiboAptamer truncation **resolved** by replacement file.
- AptaDB protein targets **joinable**.
- Exact duplicate groups unchanged (AptaBase HTML triples; ENA template backup).
- Chen XK10 ↔ Shi / Precision-SELEX XK-10 related DNA aptamer family remains an eval-lane overlap to document later.

---

## 10. Provenance and reproducibility risks

- Excel lock file `~$extracted_data.xlsx` should be ignored (not scientific data).
- Processed ENA finalize outputs live under `data/processed/` — keep raw vs processed boundaries clear for Stage S0.
- AptaDB still missing Molecule/Cell/Other downloads if those target classes are required.
- External Zenodo/InstructNA payloads still absent.

---

## 11. Ambiguities requiring manual review

1. Stage S0 input choice for ENA: review_v2 selected vs processed clean (ID field gap).
2. Materialise singleton `near_duplicate_family_id` values or allow nulls?
3. RiboAptamer Category ontology for protein filter.
4. Download AptaDB molecule/cell/other tables?
5. Ignore vs delete Excel lock files from inventory scope going forward.
6. rbms / InstructNA fetch timing.

---

## 12. Recommended starting point for curation (updated categories)

### Authoritative original / corrected source files

- ENA EMBL download
- AptaDiff A/B (+ Fastqs with caveat)
- AptaDB aptamer + protein + **interaction**
- AptaIndex export; UTexas xlsx; AptamerBase csv; AptaBase html + raw csv
- **RiboAptamer `all_sequences_509_rows.csv`**
- NCBI GenBank set; SRA metadata

### Manually assembled extracts (eval / targeted)

- chen, shi, selektion table6, precision_selex extracted_data (+ README)

### Derived / review products (not raw ingest)

- ENA inspection/candidates/review/review_v2 (except: selected used as curated ENA lane input)
- aptabase_cleaned.csv

### Superseded / removed

- RiboAptamer truncated csv/xlsx (deleted)
- ENA v1 empty selected
- **li_et_al** (deleted; exclude_due_to_provenance)

### Hold

- rbms README-only; instructNA script-only

---

## Validation

| Check | Result |
|---|---|
| Current files in inventory | 203/203 |
| Deleted `li_et_al` absent from inventory | yes |
| Directories | 29 |
| Unreadable | 1 (`~$extracted_data.xlsx` lock file) |
| Documentation files read/associated | AptaDB About PDF; ENA README/QC md; Aptadiff rtf; aptabase qc; chen/shi READMEs; precision README; rbms README; riboaptamer rtf; selektion rtf; instructNA rtf; UTexas rtfd noted via inventory |
| Raw files changed by inspection | **0** |
| Sample-based checks | FASTQ/EMBL as flagged in inventory |

### Files created or modified outside `data/raw`

- `scripts/data_preparation/inventory_raw_data.py` (extended)
- `docs/data_curation/raw_data_inventory.csv`
- `docs/data_curation/raw_data_inventory_summary.json`
- `docs/data_curation/raw_data_workbook_sheets.csv`
- `docs/data_curation/raw_data_state_assessment.md` (this file)
- `docs/data_curation/raw_data_curation_questions.csv`
- `docs/data_curation/_prior_raw_data_inventory.csv` (baseline snapshot)
- `tests/data_preparation/test_inventory_raw_data.py`

---

## Terminal summary of principal findings

See the agent completion summary: 203 files; +5 / ~2 OS-meta modifications / −3 vs prior; ENA selected 679 with both Stage S0 ID fields; RiboAptamer corrected path + Category tallies; AptaDB join via interaction.csv (high confidence); `li_et_al` absent; Precision-SELEX sequence column B; D9 clones = RNA reported as DNA alphabet.
