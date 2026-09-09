# RNA Aptamer Corpus — Data Curation Plan and Implementation Specification

**Project:** RNAGenesis aptamer MRes (`rnagenesis-aptamer-mres`)
**Owner:** Laura
**Version:** 1.2 — 2026-08-04
**Status:** Ready for implementation. All blocking questions resolved.

**Companion documents (authoritative inputs):**

- `docs/data_curation/raw_data_inventory.csv` — refreshed 2026-08-04, 203 files / 29 directories
- `docs/data_curation/raw_data_inventory_summary.json`
- `docs/data_curation/raw_data_state_assessment.md`
- `docs/data_curation/raw_data_curation_questions.csv` — Q1–Q6 resolutions
- `data/raw/ENA/README_ena_inspection.md`
- `docs/dataset_decisions.md`
- `docs/log.md` — running project log (§17)

The refreshed inventory reconciles against the previous one: 5 files added, 3 removed, 2 modified
(`.DS_Store` only), 196 unchanged, and 203/203 SHA-256 pre/post match confirming `data/raw` was not
mutated. It also carries a `recommended_S0_status` column per file, which the registry (§5.3) should
be built from rather than re-derived.

---

## 0. How to use this document

Written to be handed to an implementing agent (ChatGPT driving Cursor). It is the contract for what
gets built.

| Marker | Meaning | Agent behaviour |
|---|---|---|
| **DECIDED** | Settled. | Implement as written. Do not re-open or offer alternatives. |
| **DECISION REQUIRED** | Genuinely open; a recommendation is given. | Stop and ask. Do not default silently. |
| **CHECKPOINT** | A human-review gate. | Emit the review artefact, stop, wait for the reviewed file. |

Standing rules for the implementing agent are in §15. Read those before writing code.

---

## 1. Purpose of the corpus

Three consumers, and the tension between them drives several decisions below.

1. **Fine-tuning corpus** for RNAGenesis (Aim 2). Hypothesis: a model trained on a diverse,
   multi-target aptamer set learns transferable aptamer "grammar" that generalises to a novel target
   (NDM-1). The corpus must be *diverse across targets*, not deep on a few.
2. **Reference distributions** for Tier 1 intrinsic-quality scoring in the ICDM ranking tool.
3. **Positive controls / test set** — real, validated RNA aptamer–protein pairs with known targets.

### 1.1 Three-way partition — **DECIDED**

If the same records fine-tune the generator, fit the Tier 1 reference distributions, *and* serve as
positive controls, the fine-tuned generator scores well on Tier 1 by construction and the positive
control passes trivially. Neither result means anything.

The build produces a **cluster-level** partition (clusters, not sequences, so near-duplicate SELEX
families cannot straddle a boundary):

| Partition | Fraction of clusters | Used for |
|---|---|---|
| `FT` | ~80% | Fine-tuning (further split 90/10 train/val at cluster level, within `FT`) |
| `REF` | ~10% | Fitting Tier 1 reference distributions **only** |
| `EVAL` | ~10% | Positive controls / held-out real aptamers |

Deterministic (fixed seed), stratified by `target_family`, recorded in `partition`. Assigned at S7,
**after** target normalisation, and distinct from the later RNA-aware splitting plan, which operates
*within* `FT` using the same `cluster_id` hooks.

### 1.2 NDM-1 framing — **RESOLVED, affects the thesis text**

The `selektion_paper` Table 6 D9 clones are confirmed **RNA aptamers selected by RNA SELEX**,
reported in DNA alphabet after sequencing (readme states this explicitly; clones D902, D907, D909,
D913, D914, D918, D920).

The methods framing therefore shifts slightly and, if anything, gets stronger:

> A small number of RNA aptamers have been reported against NDM-1 and serve as evaluation
> references and positive controls. What does not exist is any HT-SELEX or activity-screening
> dataset against NDM-1 of the scale required for target-specific fine-tuning. That absence is
> precisely what motivates the adaptation strategy adopted here — fine-tuning on a broad,
> multi-target aptamer corpus on the hypothesis that transferable aptamer grammar generalises to a
> target with no training data of its own.

This is a better argument than the previous one: rather than "no RNA data exists, so we improvise",
it becomes "references exist for evaluation but not for training, which is the exact regime the
method is designed for." Note that the previous claim in the research-methods document — that no
suitable target-specific RNA data was identified — needs correcting to distinguish *evaluation
references* from *training data*.

These sequences remain **excluded from the corpus** and go to the leakage exclusion set (§2.7).

---

## 2. Corpus design decisions

### 2.0 Record grain — **DECIDED**

**One corpus record is one (sequence, target) pair.** The same aptamer characterised against two
targets is two records with distinct `record_id`s.

This is not pedantry: the AptaDB `interaction.csv` bridge is many-to-many (48 aptamers with >1
target; 228 targets with >1 aptamer), and an aptamer-grain schema would silently discard genuine
polyspecificity data or arbitrarily pick one target. Consequences:

- Exact deduplication keys on **(`sequence_core`, `target_name`)**, not sequence alone (§6, S5).
- Sequences appearing against multiple targets are reported separately — that is either genuine
  polyspecificity (interesting, keep) or a target-annotation conflict (route to review).
- **Clustering** operates on sequences, so a multi-target sequence lands in exactly one cluster and
  the partition stays clean.
- `corpus_final.txt` is deduplicated **on sequence** within the `FT` partition, so a polyspecific
  aptamer is not over-represented in the training text.

### 2.1 AptaDiff downsampling — **DECIDED**

`datasetA_IGFBP3_P6.csv` (13,803 rows) and `datasetB_PTK7_P6.csv` (11,547 rows) hold ~25,000
sequences against **two** targets. Everything else combined is low thousands across hundreds of
targets, far fewer after clustering. Ingested whole, AptaDiff would be ~90% of the corpus and the
model would learn two SELEX libraries' statistics — including their fixed 36 nt length — not
transferable grammar.

**Aggressive downsampling via a per-target cap at balancing time:**

- Config parameter `MAX_TARGET_FRACTION`, default **0.05**.
- The cap applies to **clusters**, not raw records — capping raw records would still let one target
  dominate through near-identical family members. Select cluster representatives first, then cap.
- Selection within an over-represented target: highest `binding_evidence_score` → highest abundance
  (`p6` for count tables) → longest `sequence_core`, seeded RNG breaking ties.
- **Final value set at CHECKPOINT-3** (§6, S6), once the profile report shows real cluster counts.
  Re-running S7 with a different value must be a one-line change.

**Dataset A is also preserved whole, separately**, since RNAGenesis/AptaDiff used it directly:

- `corpus_final.csv` — capped, multi-target. The fine-tuning corpus.
- `corpus_replication_datasetA.csv` — Dataset A alone, same schema, uncapped, for the comparability
  run against published baselines.

Never merge these. Report both.

### 2.2 Sequence columns — original, full construct, and random region — **DECIDED**

Dataset A sequences are 36 nt: random region only. ENA deposits routinely carry the full construct —
T7 promoter, 5′ constant primer-binding site, random region, 3′ constant site. The overlap sample
shows this plainly: sequences beginning with the documented T7 promoter motif lead with the T7 promoter,
not aptamer. Mixing trimmed and untrimmed records teaches the model to emit promoter and primer
motifs as though they were binding motifs, and fits the Tier 1 reference distributions over two
different length/composition regimes.

Three sequence columns, all retained on every record:

| Column | Definition |
|---|---|
| `sequence_raw` | Verbatim from the source. No edits. Audit trail. |
| `sequence_full` | Normalised RNA — uppercase, whitespace and terminal chemical labels stripped, `T`→`U` — **including** any promoter/primer constants present. |
| `sequence_core` | `sequence_full` with T7 promoter and identified constant primer-binding regions removed: random region only, where identifiable. |

For records arriving as random region only (e.g. Dataset A), `sequence_core == sequence_full`. Where
constants are suspected but unresolvable, `sequence_core` is set equal to `sequence_full` and
flagged — never left empty, so downstream code always has a usable value.

Supporting columns: `sequence_length_full`, `sequence_length_core`, `construct_scope`,
`trim_status`, `trim_confidence`, `detected_constant_5p`, `detected_constant_3p`.

**`TRAINING_SEQUENCE_COLUMN` = `sequence_core`** — the random region, matching the original
RNAGenesis paper's use of AptaDiff Dataset A. Both columns are retained, so the alternative is an
ablation switch rather than a re-run.

#### 2.2.1 Constant-region detection — the algorithm

Reliable trimming needs the library design, which most sources do not record. Three tiers, in order,
recording which fired:

1. **Known-motif library.** `config/constant_regions.yaml`, seeded with the T7 promoter
   (`TAATACGACTCACTATAG`, RNA `UAAUACGACUCACUAUAG`, allowing 0–3 leading bases and ≤1 mismatch)
   plus common SELEX primer-binding sites. Grows as review confirms new ones.
   → `trim_confidence = high`.
2. **Group-wise consensus inference.** Group records by (`source_db`, `experiment_group_id` where
   present, else `target_name` + `publication`). For groups of ≥5 records, compute the longest
   common prefix and suffix allowing ≤1 mismatch. If a shared prefix/suffix of ≥12 nt is present in
   ≥80% of members, declare it constant and trim. → `trim_confidence = medium`.
   The ENA file's `experiment_group_id` (679/679 populated, 25 groups) is what makes this work on
   the lane where it matters most — see §5.2.
3. **No detection.** `sequence_core = sequence_full`, `trim_status = no_constants_detected`.
   → `trim_confidence = n/a`.

Guard rails: never trim if it would leave `sequence_core` under 20 nt; never trim more than 40% of a
sequence in one operation without flagging. Tier-2 motifs go to CHECKPOINT-1 for confirmation;
confirmed motifs are appended to `constant_regions.yaml` so later sources benefit.

`construct_scope` records the source record's apparent state: `random_region_only` /
`full_construct` / `partial_construct` / `unknown`.

### 2.3 Length policy — **DECIDED**

**20 ≤ length ≤ 100 nucleotides**, applied to `sequence_core`.

Below ~20 nt there is not enough sequence for a binding-competent fold, and records that short in
these databases are overwhelmingly fragments, motifs, or primer stubs. The 100 nt ceiling is the
practical generation window and matches the reviewed ENA set (max 100).

- Out-of-range → rejection log, reason `length_out_of_range`. Never silently dropped.
- Record `sequence_length_full` too, so the trimming effect is visible.
- Flag, do not drop: records at 20–25 nt and 90–100 nt are counted separately in the report.
- Records where `sequence_length_full` passes but `sequence_length_core` fails go to **review**, not
  straight to rejection — that usually means the trim was too aggressive.
- Note riboaptamer spans 10–179 nt (median 75), so both ends of this filter will bite there.

### 2.4 Alphabet, chemistry, and transcription provenance — **DECIDED**

- Uppercase, strip whitespace, strip terminal labels (`5'-`, `-3'`, `[3'T]`, trailing `p`).
- `T` → `U` for RNA records only.
- Both T and U present after label stripping → reject `mixed_T_and_U`. Do not convert.
- Any IUPAC ambiguity code (`N R Y W S M K H B V D`) → reject `ambiguous_bases`. These are
  degenerate library designs, not aptamers, and this is the main mechanism catching library
  templates (`AGNHNNNWGGWSC`, `AAACNNNNNNNNNNNNNNNNNNNN`).
- Any remaining non-`ACGU` character → reject `invalid_alphabet`.
- Alignment gaps (`-`, `.`) → reject `alignment_gaps`, route to manual repair.

**Transcription provenance — new in v1.2.** Several sources report genuinely-RNA molecules in DNA
alphabet: ENA deposits routinely, and the selektion D9 clones explicitly (§1.2). Applying T→U there
is a *computational transcription*, not a reading of the deposited alphabet, and that distinction
must survive into the corpus. Two columns:

- `alphabet_as_reported` — `RNA_U` / `DNA_T` / `mixed` / `chemical_notation`
- `t_to_u_applied` — boolean

`molecule_type` records the **experimental molecule** (RNA or ssDNA), independent of how the source
printed it. So the selektion clones are `molecule_type = RNA`, `alphabet_as_reported = DNA_T`,
`t_to_u_applied = true`. The precision-SELEX XK sequences are genuinely ssDNA and get
`molecule_type = ssDNA` with no transcription.

**Modified chemistries** are included, tagged, never silently dropped: `chemistry` ∈ `RNA`,
`2F-RNA`, `2NH2-RNA`, `2OMe-RNA`, `DNA`, `mixed`, `unknown`. Caveat for the thesis: these fold and
bind partly *because of* the modification, and RNAGenesis generates unmodified RNA — so `chemistry`
is an ablation lever and an unmodified-only run is a one-line filter.

**Post-SELEX modifications:** where a source records them (UTexas has a column), keep the
**pre-modification** sequence and note the modification.

### 2.5 ssDNA and non-protein targets — **DECIDED: excluded from the corpus, parked, not discarded**

- ssDNA → `parked_ssdna.csv`, same schema, `T` retained.
- Non-protein targets (small molecule, ion, cell, organism, nucleic acid, unknown) →
  `parked_non_protein_targets.csv`, same schema.

Parking rather than dropping matters because a large share of well-characterised *RNA* aptamers
target small molecules — riboaptamer alone contributes ~120 clearly non-protein records
(Fluorophores 42, Pharmaceuticals 32, Nucleosides & Nucleotides 25, RNA 17, Toxin 4, Synthetic 3).
If the protein-only corpus proves too small, relaxing this filter is the fastest recovery, and it is
cheap only if those records were cleaned alongside everything else.

### 2.6 Evidence ladder — **DECIDED**

| Level | `binding_evidence_type` | Definition | `binding_evidence_score` |
|---|---|---|---|
| E1 | `structural` | Experimental structure of the aptamer–target complex (PDB, X-ray/NMR/cryo-EM) | 5 |
| E2 | `quantitative_affinity` | Reported Kd / Ka / IC50 against a named protein target | 4 |
| E3 | `qualitative_binding` | Named binding assay without a quantitative constant (EMSA, ELONA, SPR yes/no, pull-down, filter binding) | 3 |
| E4 | `selection_enrichment` | Published clone from a selection, or late-round HT-SELEX enrichment, no independent binding assay | 2 |
| E5 | `database_annotation` | Database or deposit annotated with a target, no traceable assay | 1 |

Unplaceable → reject `no_binding_evidence`. **Inclusion threshold: E4 (score ≥ 2).** E5 records are
cleaned and retained in `parked_evidence_e5.csv`, so the database lane can be added back as an
ablation. This is also the mechanism by which "remove ENA records if necessary" becomes cheap.

Two sources now supply high-evidence records that were not available in v1.1:

- **riboaptamer** carries `mmCIF Download URL` (structure available → **E1**, and populate `pdb_id`)
  and `Affinity (Kd)` (→ **E2**). This makes it a materially better source than the truncated export
  suggested.
- **AptaDB** via `interaction.csv` carries `Binding Conditions/Buffer` and a PubMed reference per
  interaction → **E3** at minimum, no longer E5-by-default (§7).

### 2.7 Leakage control — **DECIDED**

Build `data/interim/leakage_exclusion_set.csv` at S0 from every sequence associated with:

- **NDM-1** — the `selektion_paper` D9 RNA clones (§1.2) and the published ssDNA NDM-1 aptamers.
- **KPC-2** — `chen_et_al_kpc`, `shi_et_al_paper`, `precision_selex_against_kpc2_paper`
  (20 XK-series ssDNA aptamers, §7).
- **Human serum albumin** (counter-target).
- Any other carbapenemase or beta-lactamase target found during target normalisation.

Applied at merge by (a) exact normalised match on both `sequence_full` and `sequence_core` and
(b) ≥90% identity to any exclusion-set member. Every exclusion logged.

⚠ The exclusion set contains the sequences that define the evaluation. It must never be committed to
the public repository (§18).

### 2.8 Provenance, corroboration, and reversibility — **DECIDED**

Requirement: it must be possible to remove ENA or Aptagen/AptaIndex records later without rebuilding
by hand, and sequences attested by several independent sources should count as more reliable.

**Deduplication merges provenance rather than discarding it:**

| Column | Meaning |
|---|---|
| `source_db` | The winning source (metadata donor) |
| `source_dataset` | The named dataset/version cleaned (§5.3) |
| `contributing_sources` | Pipe-delimited list of every source attesting this (sequence, target) pair |
| `contributing_datasets` | Corresponding dataset names |
| `corroboration_count` | Number of distinct sources attesting; ≥1 |

Three consequences:

1. **Reversibility works correctly.** If a pair appears in both AptamerBase and ENA and dedup keeps
   the ENA copy, a naive "drop all ENA" would wrongly delete something AptamerBase independently
   attests. The correct rule is *drop records whose `contributing_sources` contains only ENA*.
2. **Corroboration is a reliability signal** — reported, available as a dedup tiebreak and in
   ranking, and crossed against `binding_evidence_score` in the report. It does **not** raise the
   evidence level: evidence describes the experiment, corroboration describes the record.
3. **Redistribution.** Each record carries `redistribution_status` (most permissive among its
   contributing sources) and `independently_attested_by_permissive_source`. A sequence in AptaIndex
   *and* independently deposited elsewhere under permissive terms can be cited to the permissive
   source. Report the fraction that is `restricted`/`unknown` **and not** independently attested —
   that number is the real constraint on releasing the corpus with the ICDM paper.
   *(Documentation, not legal advice; check the specific data use agreements with someone who can
   advise before any release.)*

The master file is only ever produced by re-running the merge with a source-exclusion list. Never
hand-edit `corpus_final.csv`.

---

## 3. Output schema (the contract)

Every cleaned per-source file, every parked file, and the master corpus use this schema. Column
order fixed. Missing values are the empty string, never `NA`/`NaN`/`None`/`null`.
One record = one (sequence, target) pair (§2.0).

| # | Column | Type | Req | Allowed values / format |
|---:|---|---|:---:|---|
| 1 | `record_id` | str | ✔ | `{source_db}:{native_id}`, unique across the corpus |
| 2 | `sequence_raw` | str | ✔ | Verbatim from source |
| 3 | `sequence_full` | str | ✔ | `[ACGU]+` (RNA lanes) / `[ACGT]+` (`parked_ssdna`); constants retained |
| 4 | `sequence_core` | str | ✔ | Same alphabet; constants removed where identified |
| 5 | `sequence_length_full` | int | ✔ | Computed, never copied from source |
| 6 | `sequence_length_core` | int | ✔ | Computed |
| 7 | `construct_scope` | str | ✔ | `random_region_only` / `full_construct` / `partial_construct` / `unknown` |
| 8 | `trim_status` | str | ✔ | `no_constants_detected` / `t7_removed` / `primers_removed` / `t7_and_primers_removed` / `constants_suspected_unresolved` |
| 9 | `trim_confidence` | str | ✔ | `high` / `medium` / `n/a` |
| 10 | `detected_constant_5p` | str | | Motif trimmed from the 5′ end |
| 11 | `detected_constant_3p` | str | | Motif trimmed from the 3′ end |
| 12 | `molecule_type` | str | ✔ | `RNA` / `ssDNA` — the **experimental** molecule |
| 13 | `alphabet_as_reported` | str | ✔ | `RNA_U` / `DNA_T` / `mixed` / `chemical_notation` |
| 14 | `t_to_u_applied` | bool | ✔ | True where transcription was computational |
| 15 | `chemistry` | str | ✔ | `RNA` / `2F-RNA` / `2NH2-RNA` / `2OMe-RNA` / `DNA` / `mixed` / `unknown` |
| 16 | `target_name_raw` | str | ✔ | Verbatim from source |
| 17 | `target_name` | str | ✔ | Normalised canonical name (§8) |
| 18 | `target_uniprot` | str | | UniProt accession; empty if unresolved |
| 19 | `target_type` | str | ✔ | `protein` / `peptide` / `small_molecule` / `ion` / `nucleic_acid` / `cell` / `organism` / `other` / `unknown` |
| 20 | `target_type_source` | str | ✔ | `source_column` / `category_prior` / `dictionary` / `manual` — how `target_type` was decided |
| 21 | `target_family` | str | | Functional class (§8.3) |
| 22 | `target_pfam` | str | | Pfam/InterPro identifier where resolvable |
| 23 | `pdb_id` | str | | 4-character code, or pipe-delimited list |
| 24 | `binding_evidence_type` | str | ✔ | One of the five ladder labels (§2.6) |
| 25 | `binding_evidence_score` | int | ✔ | 1–5 |
| 26 | `affinity_value` | float | | Numeric Kd/Ka/IC50 |
| 27 | `affinity_unit` | str | | Normalised to `M` where parseable |
| 28 | `affinity_type` | str | | `Kd` / `Ka` / `IC50` / `EC50` / `other` |
| 29 | `source_db` | str | ✔ | Registry key (§4) |
| 30 | `source_dataset` | str | ✔ | Named dataset/version, e.g. `riboaptamer_full_2026-08` |
| 31 | `contributing_sources` | str | ✔ | Pipe-delimited; equals `source_db` before dedup |
| 32 | `contributing_datasets` | str | ✔ | Pipe-delimited |
| 33 | `corroboration_count` | int | ✔ | ≥1 |
| 34 | `redistribution_status` | str | ✔ | `permissive` / `restricted` / `unknown` |
| 35 | `independently_attested_by_permissive_source` | bool | ✔ | |
| 36 | `native_id` | str | ✔ | Source-native identifier |
| 37 | `publication` | str | | Free-text citation |
| 38 | `doi` | str | | |
| 39 | `pubmed_id` | str | | |
| 40 | `accession` | str | | ENA/GenBank/SRA accession |
| 41 | `experiment_group_id` | str | | Carried where the source provides it; drives §2.2.1 tier 2 |
| 42 | `near_duplicate_family_id` | str | | Carried where provided; validates clustering |
| 43 | `cluster_id` | str | | Assigned at S5 |
| 44 | `is_cluster_representative` | bool | | Assigned at S5 |
| 45 | `partition` | str | | `FT` / `REF` / `EVAL`; assigned at S7 |
| 46 | `qc_flags` | str | | Pipe-delimited non-fatal flags |
| 47 | `notes` | str | | Free text, including manual review notes |

**Rejection log schema** (`rejected_{source}.csv`): `record_id`, `source_db`, `source_dataset`,
`native_id`, `sequence_raw`, `target_name_raw`, `stage`, `rejection_reason`, `rejection_detail`.

**Rejection reason vocabulary (closed set):**
`missing_sequence`, `missing_target`, `length_out_of_range`, `ambiguous_bases`, `invalid_alphabet`,
`mixed_T_and_U`, `alignment_gaps`, `truncated_sequence`, `primer_like`, `library_template`,
`ssdna_parked`, `non_protein_target_parked`, `non_nucleic_acid_molecule`, `non_aptamer_source_object`,
`no_binding_evidence`,
`evidence_below_threshold`, `leakage_excluded`, `duplicate`, `target_cap_subsample`,
`manual_reject`.

`non_nucleic_acid_molecule`: source-declared non-nucleic-acid aptamer/molecule record, e.g. peptide aptamer.

`non_aptamer_source_object`: source record belongs to an explicitly typed metadata/structure object rather than an aptamer biological record (technical/source-reconciliation rejection, not a human decision).

---

## 4. Source registry

### 4.1 Tier 1 — ingested in v1

| Key | Dataset / input | Rows | Notes |
|---|---|---:|---|
| `aptadiff_a` | `Aptadiff_datasetA/datasetA_IGFBP3_P6.csv` | 13,803 | Capped; also builds the replication file |
| `aptadiff_b` | `Aptadiff_otherdata/datasetB_PTK7_P6.csv` | 11,547 | Capped |
| `ena` | `ENA/review_v2/ena_selected_after_manual_review.csv` | 679 | Retains both ID columns — see §5.2 |
| `riboaptamer` | `riboaptamer/all_sequences_509_rows.csv` | 509 | Corrected full-sequence export — see §5.1 |
| `aptadb` | `AptaDB/interaction.csv` (spine) + `aptamer.csv` + `protein.csv` | 1,350 / 1,293 / 194 | Interaction-grain — see §5.4 |
| `aptaindex` | `AptaIndex/aptamers-export-2026-07-22.csv` | 1,050 | Chemical-notation parser required (§7) |
| `utexas` | `UTexas_aptamer_dataset/UTexas Aptamer Database dataset_Sept2023.xlsx` | 1,894 | Richest metadata; 399 missing sequences |
| `aptabase` | `aptabase/aptabase_cleaned.csv` | 610 | Use `sequence_raw` as input |
| `aptamerbase` | `aptamerbase/aptamerbase_aptamers.csv` | 2,128 | RNA-like (U); 179 missing, 184 duplicate |
| `ncbi_nuc` | `NCBI_nucleotide/*.gb` | 18 | Parse LOCUS/ACCESSION/FEATURES; expect ENA overlap |

### 4.2 Tier 1-eval — cleaned to schema, routed to the exclusion set and evaluation lane, never to `FT`

| Key | Input | Rows | Role |
|---|---|---:|---|
| `selektion_ndm1` | `selektion_paper/table6_d9_ndm1_sequences.csv` | 7 | **NDM-1 RNA** references (§1.2). `molecule_type = RNA`, `alphabet_as_reported = DNA_T` |
| `chen_kpc` | `chen_et_al_kpc/chen2020_kpc2_ecoli_xk10_aptamer_sequences.csv` | 8 | KPC-2. Use `core_aptamer_sequence_5to3`; exclude negative controls |
| `shi_kpc` | `shi_et_al_paper/shi2025_kpc2kp_mdrab_aptamer_sequences.csv` | 2 | KPC-2. **Shi KPC-2 KP ≡ Chen XK10** — merge to one record, dual citation |
| `precision_selex_kpc2` | `precision_selex_against_kpc2_paper/extracted_data.xlsx` | 20 records | KPC-2 ssDNA (§7). Schema resolved — column B primary |

### 4.3 Tier 2 — deferred, revisit only if the corpus is too small

| Path | Reason deferred |
|---|---|
| `Aptadiff_otherdata/datasetC.fastq`, `datasetD.fastq` (81k / 121k reads) | No target annotation, unknown adapter state, ~0 added target diversity, high preprocessing cost |
| `sra_metadata_ndm1_aptamers/PRJNA830749/*` | Metadata only, reads absent |
| AptaDB `molecule.csv` / `cell.csv` / `other.csv` | Not downloaded. Needed only if non-protein AptaDB targets are wanted — see §5.4 |

`li_et_al` has been **removed from `data/raw` and is out of scope**: the workbook's provenance could
not be established. If it ever resurfaces, it re-enters only with a documented DOI/supplement
identity.

### 4.4 Tier 3 — out of scope for v1

`instructNA_paper/*.sh` (payload absent) · `rbms_paper/README.md` (Zenodo pointer) ·
`NCBI_GEO_papers/*.pdf`, `NCBI_SRA_papers/*.pdf`, `NCBI_PRJNA1221092/*.pdf` (documentary evidence) ·
`aptabase/html/**` and `fixtures/**` (scrape cache) · all `.DS_Store` ·
`Aptadiff_datasetA/datasetA_IGFBP3_x_z.csv` (latent coordinates, not sequences).

### 4.5 Forbidden inputs — **DECIDED, ingesting these would double-count or corrupt**

- Every file under `data/raw/ENA/` **except** `review_v2/ena_selected_after_manual_review.csv`. The
  `inspection/`, `candidates/`, `review/`, and remaining `review_v2/` trees are derived products of
  the same 5,841-record EMBL download; ingesting more than one double-counts the same sequences.
  The refreshed inventory marks 56 files `derived_output_not_raw_input` — that classification is
  binding.
- `ENA/review/ena_selected_after_manual_review.csv` — empty (0 rows) despite the name.
- `ENA/review_v2/ena_sequence_review_template_backup.csv` — byte-identical to the template.
- `aptabase/aptabase_raw.csv` — superseded by `aptabase_cleaned.csv` (same 610 rows).
- `aptabase/Aptamer Search Page {1,2,37,61}.html` and `aptabase/fixtures/*` — byte-duplicates of
  `aptabase/html/*`.
- **`precision_selex_against_kpc2_paper/~$extracted_data.xlsx`** — an Excel lock/temp file, not
  data. It appears in the refreshed inventory as newly added. Never read it; it should be deleted
  from `data/raw` and excluded via `.gitignore`.

---

## 5. Source-specific input notes

### 5.1 riboaptamer — resolved, promoted to Tier 1

`data/raw/riboaptamer/all_sequences_509_rows.csv`, 509 rows, replacing the deleted truncated
exports. Sequences are full length (1/509 retains an ellipsis, versus 508/509 before);
lengths 10–179, median 75.

Schema: `Sequence Name | Aptamer Name | Category | Type | Article name | Sequence | Length |
GC Content | Discovery Year | Affinity (Kd) | Description | PubMed Link | mmCIF Download URL`.

Three things to handle:

1. **There is no target column.** The target must be parsed from `Aptamer Name` and `Description`
   (e.g. a theophylline aptamer names its ligand in the aptamer name). This is a text-extraction
   job feeding into the S4 target dictionary, and unresolvable records reject as `missing_target`.
   Do not treat `Category` as the target.
2. **`Category` is an organism/ligand class prior, not a molecule type.** Values: Mammalian 198,
   Viral 96, Fluorophores 42, Pharmaceuticals 32, Nucleosides & Nucleotides 25, Bacteria 22,
   Other 22, Cell 20, RNA 17, Amino Acids & Peptides 11, Biologics & Signaling Molecules 9,
   Prion 7, Toxin 4, Synthetic 3, Parasite 1.
   **DECIDED:** use `Category` as a *prior* recorded in `notes`, resolve `target_type` per record in
   S4 from the extracted target name, and cross-check the two — disagreements go to CHECKPOINT-2.
   Set `target_type_source = category_prior` only where nothing better resolves. Category alone is
   not reliable enough to decide: "Mammalian" and "Viral" usually denote proteins from those
   organisms but can denote whole cells or virions; "Toxin" spans protein toxins (ricin) and small
   molecules (aflatoxin); "Amino Acids & Peptides" spans free amino acids (small molecules) and
   peptides. A rule table that silently collapses these would misroute records between the corpus
   and the parked file, which is exactly the decision that most needs to be right.
3. **Evidence signals are good here.** `mmCIF Download URL` present → **E1**, and populate `pdb_id`.
   `Affinity (Kd)` present → **E2**. This makes riboaptamer one of the few high-evidence lanes.

Regression assertion at S2: <1% of riboaptamer sequences end in `.`/`…`, median length >20 nt.
Fires if the truncated file is ever re-registered.

### 5.2 ENA — resolved, with one call flagged

**Registered input: `data/raw/ENA/review_v2/ena_selected_after_manual_review.csv` (679 rows).**

There are two candidates and they differ in a way that matters:

| File | Rows | `experiment_group_id` | `near_duplicate_family_id` |
|---|---:|---|---|
| `data/raw/ENA/review_v2/ena_selected_after_manual_review.csv` | 679 | ✔ present, 679/679, 25 groups | 367/679 populated (54%) |
| `data/processed/ena/ena_aptamer_supplement_clean.csv` | 676 | ✘ replaced by `supporting_experiment_group_ids` | ✔ present |

**I have registered the 679-row raw file.** Reasoning: `experiment_group_id` at pair grain is what
drives group-wise constant-region inference (§2.2.1 tier 2), and the ENA lane is where full
constructs are concentrated — losing it would degrade the most important trimming lane to tier 3.
The processed file's `supporting_experiment_group_ids` is a pipe-delimited multi-value field, which
is not a usable grouping key without an unambiguous primary. Our S2/S3 stages redo normalisation and
filtering anyway, so nothing is lost by starting from the less-processed file.

**Flagged, because it is your call rather than mine:** the processed export drops 3 rows (679 → 676).
Those three exclusions encode a judgement made by `finalize_ena_aptamer_supplement.py`, and starting
from the raw file discards it. **Required at CHECKPOINT-1:** reconcile the delta — list the 3 rows,
state why the finalize script dropped them, and either confirm the same exclusion in our rejection
log or overturn it. If you would rather use the processed export as the input, restore a single
unambiguous `experiment_group_id` column to it first and re-register.

**Singleton policy — DECIDED.** `near_duplicate_family_id` is empty for 312/679 rows (46%), which
coincides with missing `near_duplicate_family_size` and means "no multi-member family". Materialise
these as explicit singleton IDs (`ena_singleton_{n}`) at S1, so that downstream code never has to
distinguish empty-means-singleton from empty-means-unknown. Record `near_duplicate_family_size = 1`.

Other ENA handling:

- **Sequence:** `sequence` (reviewed, RNA-normalised). Carry `sequence_original` into `sequence_raw`
  and into `notes` where `sequence_corrected_applied` is true. Deposited ENA RNA is routinely
  T-alphabet → set `alphabet_as_reported = DNA_T` and `t_to_u_applied` accordingly.
- **Target:** `target`, with `target_original` in `notes` where `manual_target_corrected` is set.
  Records with `unresolved_target` or `genuine_target_conflict` → CHECKPOINT-1, no auto-include.
- **Evidence:** map `binding_evidence_type` / `binding_evidence_strength` / `evidence_scope` onto the
  E1–E5 ladder. Expect most at **E4 or E5**; under the E4 threshold a substantial share parks in
  `parked_evidence_e5.csv`. Intended, and it is what makes ENA removable.
- **UTF-8 BOM** present — strip.
- `consolidated_from_n_units > 1` on three rows and `experiment_group_ids` with `|` separators on
  126 rows: carry both, do not split into multiple records.
- ENA sequences also appear in `NCBI_nucleotide/*.gb`. Dedup by `accession` first, then by
  (sequence, target).

### 5.3 Registry over inventory — **DECIDED**

Inputs move (three files removed, five added since the previous inventory), so the registry is
authored, not inferred.

`data/interim/registry/source_registry.csv` columns:
`source_key`, `source_dataset` (name + version, e.g. `ena_selected_v2_2026-08`), `path`, `sha256`,
`n_rows_expected`, `snapshot_date`, `tier`, `redistribution_status`, `notes`.

Rules:

1. Every output record carries `source_dataset`, so the dataset being worked on is identifiable per
   record without consulting a log.
2. At S0, compute each registered file's sha256 and row count and compare against the registry.
   **Mismatch is a hard failure.**
3. Also compare against `raw_data_inventory.csv`, using its `recommended_S0_status` column as the
   starting classification. **Mismatch with the inventory is a warning, not a failure**, and must
   name the file and both hashes.
4. `corpus_manifest.json` embeds the whole registry, so any build traces to exact inputs.
5. When a source is updated mid-project, bump `source_dataset` rather than overwriting. The version
   string is what makes two builds comparable.

### 5.4 AptaDB — resolved, interaction-grain

The join is confirmed with high confidence: **`interaction.csv` is the bridge.**
`aptamer.csv.Apta_index` = `interaction.csv.Apta_index`; for protein targets,
`interaction.csv.TargetID` = `protein.csv.Uni-port ID`. All 194 protein UniProt IDs appear as
`TargetID`; all 639 `Target chemistry = Protein` interactions match `protein.csv`.

**The adapter reads `interaction.csv` as the spine and emits one record per interaction row**
(§2.0), joining aptamer metadata and protein metadata onto it:

- 1,350 interactions; many-to-many (48 aptamers with >1 target, 228 targets with >1 aptamer).
- 1,256/1,293 aptamers have interaction rows; **the 37 without → reject `missing_target`.**
- `Target chemistry` gives `target_type` directly (`target_type_source = source_column`) —
  Protein vs Molecule/Cell/Other.
- **`molecule.csv`, `cell.csv`, and `other.csv` are not downloaded**, so non-protein AptaDB targets
  have a `TargetID` but no resolvable name. They still park correctly with a recorded chemistry and
  an unresolved name — record `qc_flags = target_name_unresolved_missing_lookup_table`. Only fetch
  those tables if the non-protein lane is ever promoted.
- `Aptamer Chemistry` from `aptamer.csv` gives `molecule_type` (DNA 1,029 / RNA 264).
- `Reference(pubmed ID)` → `pubmed_id`; `Binding Conditions/Buffer` present → **E3**.
- Watch the flags: 48 conflicting targets for the same sequence, 95 duplicate sequences — expected
  at interaction grain, and handled by (sequence, target) dedup rather than treated as errors.
- **DECIDED:** take the sequence from `aptamer.csv` (the canonical aptamer record), not from
  `interaction.csv`'s own `Sequence` column. Assert the two agree, and log mismatches — an
  unexplained mismatch means the join is wrong.

---

## 6. Pipeline stages

Each stage is one script under `scripts/data_preparation/`, reads only the previous stage's outputs,
writes a log and a QC report, and appends an entry to `docs/log.md` (§17). `data/raw/` is read-only.

```
data/raw/  ──S0──▶  interim/registry/     ──S1──▶  interim/extracted/
                                                        │
                                                       S2  (normalise + trim)
                                                        ▼
                                              interim/normalised/
                                                        │
                                                       S3  ◀── CHECKPOINT-1 (per-source review)
                                                        ▼
                                               interim/filtered/
                                                        │
                                                       S4  ◀── CHECKPOINT-2 (target dictionary)
                                                        ▼
                                                interim/merged/
                                                        │
                                                       S5  (dedup + cluster)
                                                        ▼
                                             interim/deduplicated/
                                                        │
                                                       S6  ◀── CHECKPOINT-3 (SUPERVISOR REVIEW)
                                                        ▼        corpus_profile_report.md
                                                       S7  (balance + partition)
                                                        ▼
                             processed/corpus_final.csv + corpus_report.md
                                        + parked_*.csv + corpus_final.txt
```

**Ordering:** target normalisation (S4) precedes deduplication, clustering, balancing, and any
partitioning or splitting. Nothing that groups or divides the corpus runs before targets are
canonical, because every such operation keys on target or family.

### S0 — Registry and leakage exclusion set

**Out:** `registry/source_registry.csv`, `leakage_exclusion_set.csv`.

Freeze the registry per §5.3; hard-fail on registry hash mismatch, warn on inventory divergence.
Build the leakage exclusion set (§2.7). Write the first pipeline entry in `docs/log.md`.

### S1 — Extraction (one adapter per source)

**Out:** `extracted/{source}_extracted.csv`.

Column mapping and format parsing only — no cleaning, no filtering. Every input row appears in the
output even if empty; for interaction-grain sources the assertion is
`rows_out == rows_in(interaction)`. Materialise ENA singleton family IDs here (§5.2). Per-source
notes in §7.

### S2 — Normalisation and constant-region trimming

**Out:** `normalised/{source}_normalised.csv`, `{source}_qc.md`,
`normalised/detected_constants_{source}.csv`.

In order: strip BOM/whitespace → strip terminal chemical labels → uppercase → classify
`molecule_type`, `alphabet_as_reported`, `chemistry` → build `sequence_full` (`T`→`U` for RNA,
setting `t_to_u_applied`) → detect and trim constants to build `sequence_core` (§2.2.1) → compute
both lengths → emit non-fatal `qc_flags`. Nothing dropped here. Source-specific assertions (e.g. the
riboaptamer truncation regression, §5.1; the AptaDB sequence-agreement check, §5.4) run here.

### S3 — Per-source filtering + **CHECKPOINT-1**

**Out:** `filtered/{source}_clean.csv`, `rejected_{source}.csv`, `{source}_review.csv`.

Apply drop rules: missing sequence, alphabet, ambiguity, mixed T/U, gaps, length, primer-like /
library template, truncated. Route ssDNA and non-protein targets to their parked files. Every drop
gets a rejection-log row with a closed-vocabulary reason.

**CHECKPOINT-1** emits `{source}_review.csv` containing:

- records dropped for a *judgement-dependent* reason (`primer_like`, `library_template`,
  `truncated_sequence`, `alignment_gaps`, `no_binding_evidence`),
- records where trimming pushed length below 20 nt, and all `trim_confidence = medium` trims,
- records at the length boundaries (20–25 nt, 90–100 nt),
- **the ENA 679 vs 676 reconciliation (§5.2)**,
- a seeded random sample of 30 *kept* records for eyeballing,

with `manual_decision` (`keep`/`drop`/`edit`), `manual_sequence_corrected`,
`manual_target_corrected`, `manual_notes`. The pipeline stops per source; an apply-script folds
decisions back in and records them in `notes`. Confirmed constant-region motifs are appended to
`config/constant_regions.yaml`.

### S4 — Target normalisation + **CHECKPOINT-2**

**Out:** `merged/target_dictionary.csv`, `merged/target_review.csv`, `merged/all_sources_merged.csv`.

See §8. Also applied here: leakage exclusion (§2.7) and the evidence threshold (§2.6).
**CHECKPOINT-2** sends the target dictionary to Laura — every distinct raw target string with its
proposed canonical name, UniProt accession, type, and family, plus riboaptamer Category-versus-
resolved-type disagreements (§5.1).

### S5 — Deduplication and clustering

**Out:** `deduplicated/corpus_dedup.csv`, `clusters.tsv`, `overlap_report.md`.

1. **Exact dedup** on **(`sequence_core`, `target_name`)** (§2.0). Merge provenance per §2.8.
   Winner: highest `binding_evidence_score` → highest `corroboration_count` → most complete
   metadata → alphabetical `source_db` for determinism.
   Separately report (a) sequences appearing against **multiple targets** — polyspecificity or
   conflict, either way it goes in the report — and (b) records sharing a `sequence_core` but
   differing in `sequence_full`, which is corroboration across construct scopes, not a conflict.
2. **Cluster** on sequences at 90% identity:
   `mmseqs easy-cluster --min-seq-id 0.9 -c 0.8 --cov-mode 1 -s 7.5`.
   ⚠ Sequences are short (median ~50–75 nt) and MMseqs2's k-mer prefilter loses sensitivity below
   ~50 nt, hence the raised sensitivity. Validate against ENA's `near_duplicate_family_id` — the 56
   real families are free ground truth, and the materialised singletons should stay singletons. If
   recall is poor, fall back to `cd-hit-est -c 0.9 -n 8`.
3. Assign `cluster_id`; mark one `is_cluster_representative` per cluster.
4. Report cross-source overlap as an n×n matrix, sequences unique to each source, and the
   `corroboration_count` distribution.

### S6 — Profile report + **CHECKPOINT-3 (supervisor review)**

**Out:** `interim/deduplicated/corpus_profile_report.md` + figures.

The report Laura takes to Beheshti and Paulsen. It runs on the deduplicated, clustered,
target-normalised corpus **before any balancing or partitioning**, so supervisors see the real
distribution and their input shapes the balancing decision rather than rationalising it. Contents in
§9.1. Produces no corpus file — it exists to stop and ask.

Decisions taken here: final `MAX_TARGET_FRACTION`, whether further balancing beyond the cap is
wanted now, and whether the E4 threshold or protein-only policy should be relaxed given actual size.

### S7 — Balancing, partition, and final outputs

**Out:** `data/processed/`.

1. Apply the per-target cap at cluster level (§2.1), seeded.
2. Assign `FT`/`REF`/`EVAL` at cluster level, stratified by `target_family` (§1.1).
3. Write:

| File | Contents |
|---|---|
| `corpus_final.csv` | Full schema, all retained records |
| `corpus_final.txt` | `sequence_core` only, one per line, `FT` partition, **deduplicated on sequence** |
| `corpus_replication_datasetA.csv` | Dataset A alone, uncapped, same schema |
| `parked_ssdna.csv` | Cleaned ssDNA |
| `parked_non_protein_targets.csv` | Cleaned non-protein-target records |
| `parked_evidence_e5.csv` | Cleaned E5 records |
| `evaluation_references.csv` | NDM-1 / KPC-2 references from Tier 1-eval |
| `rejected_all.csv` | Concatenated rejection logs |
| `corpus_report.md` | §9.2 final build report |
| `corpus_manifest.json` | Registry, parameters, seeds, versions, timestamp |

---

## 7. Per-source adapter notes

| Source | Sequence | Target | Evidence | Specific handling |
|---|---|---|---|---|
| `aptadiff_a` / `_b` | `seq` | Constant: IGFBP3 / PTK7 (filename + readme, not a column) | E4; `p6` is round-6 count | `construct_scope = random_region_only` (fixed 36 nt), so `sequence_core == sequence_full`. Resolve target to UniProt manually. Rank by `p6` for cap subsampling |
| `ena` | `sequence` | `target` | Evidence fields → ladder | §5.2 |
| `riboaptamer` | `Sequence` | **Parsed from `Aptamer Name` + `Description`** | `mmCIF Download URL` → E1 + `pdb_id`; `Affinity (Kd)` → E2; else E4 | §5.1. `Category` is a prior in `notes`, never the target. Truncation regression assertion at S2 |
| `aptadb` | `aptamer.csv.Sequence` via `interaction.csv` spine | `interaction.TargetID` → `protein.Uni-port ID` | `Binding Conditions/Buffer` → E3 | §5.4. One record per interaction row. 37 aptamers without interactions → `missing_target`. Non-protein TargetIDs unresolvable (lookup tables absent) |
| `aptaindex` | `Sequence` | `Target`, `Target Type` | `Affinity Type`+`Affinity` → E2; else E3 | **Chemical-notation parser required**: `5'-dApdTpdA…`. Parse `dN`/`rN`/`mN`/`fN` tokens; set `chemistry` from the prefix mix and `alphabet_as_reported = chemical_notation`. `Type` gives molecule type (DNA 673, RNA 200, 2′-F-RNA 71, Peptide 57 → drop peptides). 31 missing sequences, 28 missing targets, 25 conflicting targets → CHECKPOINT-1. `redistribution_status = restricted` (Data Use Agreement) |
| `utexas` | `Aptamer Sequence` | `Target ` (trailing space) | `Kd (nM)` → E2; `Affinity` text → E3 | `Type of Nucleic Acid` → molecule/chemistry (ssRNA, ssDNA, 2′-fluoro-RNA, 2′-amino-RNA). Keep `Post-selex modifications` in `notes`, use the **pre**-modification sequence. Rich citation columns → `publication`/`doi`/`pubmed_id`. The 1,495 punctuation flags are mostly `5'…[3'T]` labels; the label stripper handles them |
| `aptabase` | `sequence_raw` (not `sequence_clean`) | `target_specific`, fall back `target_general` | `affinity_measurement_type` → E2/E3 | Reuse parsed `affinity_molar`, `doi`, `pmid`. Re-run the shared normaliser on `sequence_raw` so the alphabet policy applies once, uniformly |
| `aptamerbase` | `sequence` | `label` | Boolean flags → E4/E5 | `has_experimentally_determined_structure` → **E1**, populate `pdb_id`. `is_minimal_aptamer_of` links variants — carry into `notes`, useful for clustering validation. Already uses U |
| `ncbi_nuc` | GenBank ORIGIN | FEATURES qualifiers | Usually E5 | Parse LOCUS/ACCESSION/DEFINITION/FEATURES. Filenames are opaque (`sequence (1).gb`) — `native_id` from ACCESSION, never the filename. Dedup against `ena` by accession |
| `selektion_ndm1` | `sequence_cleaned` | Constant: NDM-1 | E4 | Eval lane. `molecule_type = RNA`, `alphabet_as_reported = DNA_T`, `t_to_u_applied = true` (§1.2). Alignment gaps → manual repair at CHECKPOINT-1 |
| `chen_kpc` | `core_aptamer_sequence_5to3` | `target_name` | Kd in README → E2 | Eval lane. Exclude `is_negative_control` rows |
| `shi_kpc` | `sequence_5to3_fam_removed` | `target_label` | Qualitative → E3 | Eval lane. **KPC-2 KP ≡ Chen XK10** — one merged record, both citations |
| `precision_selex_kpc2` | **Column B** (N40, 40 nt ssDNA) | Constant: KPC-2 | Round counts → E4 | Eval lane. **Non-trivial layout:** one sheet, multi-row header on rows 2–3, data on **even rows from row 4**, merged cells, 20 records XK-1…XK-20. Column D = construct DNA → `sequence_full`; column B → `sequence_core`. `Repeat times` on row 1 is a merged layout label spanning columns F–J, not a field. `molecule_type = ssDNA`, no T→U. Column I heading incomplete (library 1 inferred) — note it, do not guess in code. **Do not read `~$extracted_data.xlsx`** |

---

## 8. Target normalisation

The gate on everything that groups or divides the corpus, so it gets its own stage, running before
dedup, clustering, balancing, and partitioning.

### 8.1 The problem, concretely

Raw target strings in the ENA lane alone include `fgf2` and `fgf-2` (one protein, two strings);
`same` and `detecting target protein by using the same` (patent-abstract artefacts); `targeted
genome modification` (a method); `tansferase` (typo); `extracellular domain of pap` (a domain).
riboaptamer has no target column at all and needs extraction from free text. AptaDB non-protein
TargetIDs have no local lookup table. Across sources you also get organism names, cell lines, and
trade names used where a protein is meant.

Unnormalised, "balance across target families" is not executable, and the per-target cap silently
fails because one target appears under five names.

### 8.2 Procedure

1. Collect every distinct `target_name_raw` across all sources with its record count.
2. Deterministic rules: lowercase, strip punctuation/hyphens for matching, move
   `recombinant`/`human`/`protein`/`domain of` qualifiers into a `target_region` note.
3. Resolve to **UniProt accession** where possible — the join key everything downstream depends on.
   UniProt ID-mapping/search on the normalised string; accept only unambiguous single hits
   automatically, everything else to CHECKPOINT-2.
   **Seed the dictionary from AptaDB `protein.csv`**, which supplies 194 UniProt IDs with names,
   organisms, and `Cross-reference (PDB)` — free, high-quality, and it also populates `pdb_id`.
4. Assign `target_type` from the closed vocabulary, recording `target_type_source`. Methods, assays,
   and patent-abstract fragments → `unknown` → rejected as `missing_target`.
5. Emit `target_dictionary.csv`: `target_name_raw` → `target_name`, `target_uniprot`, `target_type`,
   `target_type_source`, `target_family`, `target_pfam`, `n_records`, `resolution_method`
   (`auto`/`manual`/`unresolved`), `confidence`.

**CHECKPOINT-2:** the dictionary goes to Laura sorted by `n_records` descending, so high-impact
entries get attention first and the long tail of singletons costs little. Include a dedicated
section for riboaptamer Category-versus-resolved-type disagreements.

### 8.3 Target family — **DECIDED: assign both schemes**

- **`target_family`** — functional class from a closed vocabulary: `enzyme`, `receptor`, `cytokine`,
  `growth_factor`, `antibody_immunoglobulin`, `transcription_factor`, `structural_protein`,
  `viral_protein`, `bacterial_surface_protein`, `transport_protein`, `other`, `unknown`. Manually
  assignable, guaranteed coverage, legible in a thesis figure. **Used for stratification and
  balancing.**
- **`target_pfam`** — Pfam/InterPro family via UniProt cross-reference. Better granularity for the
  "does aptamer grammar transfer across protein families" argument, but coverage depends on UniProt
  resolution. **Reported as a secondary diversity statistic**, not used for stratification.

NDM-1 is an enzyme, so an enzyme-heavy corpus is arguably a feature rather than a defect — the
report should state the enzyme share explicitly so that argument can be made or refuted.

---

## 9. Reports

### 9.1 `corpus_profile_report.md` — supervisor-facing (CHECKPOINT-3)

Produced at S6, before balancing, written for someone who has not seen the pipeline. Lead with a
one-page summary: final counts, number of targets, number of clusters, and the three or four
decisions Laura wants input on.

**Targets — the main event**
- Records and clusters per `target_name`, sorted descending; full table plus a top-30 figure.
- Records and clusters per `target_family`; per `target_pfam` where resolved.
- Gini coefficient and Shannon entropy of the target distribution, as-is.
- Targets with only one record, and only one cluster.
- The same recomputed under candidate `MAX_TARGET_FRACTION` values (0.02, 0.03, 0.05, 0.10) with the
  resulting corpus size for each — this turns an abstract balancing question into a concrete
  size-versus-diversity tradeoff.
- UniProt resolution rate; count of unresolved targets.
- Sequences appearing against multiple targets (§2.0) — polyspecificity or conflict.

**Sequences**
- Length distribution for `sequence_core` and `sequence_full`, overall and by source, by
  `construct_scope`, by target.
  ⚠ Explicitly test for and report **bimodality** — Dataset A contributes only 36-mers while ENA
  spans 17–100 nt and riboaptamer 10–179 nt. A bimodal length prior would be learned by the model
  and would corrupt the length-conditioned Tier 1 reference distributions.
- Nucleotide composition and GC content, overall and by source. Also the null-model input for the
  existing generation pipeline.
- Cluster size distribution; singleton fraction; largest clusters with source and target.

**Confidence and provenance**
- Evidence-level distribution (E1–E5), overall and by source.
- `corroboration_count` distribution; evidence level crossed with corroboration.
- Cross-source overlap matrix; sequences unique to each source.
- `chemistry`, `construct_scope`, `trim_confidence`, and `t_to_u_applied` breakdowns.
- Licensing: fraction from `restricted`/`unknown` sources, and the fraction of those **not**
  independently attested by a permissive source (§2.8).

**Open questions for supervisors** — a short explicit list, not buried in prose.

### 9.2 `corpus_report.md` — final build report (S7)

Everything in §9.1 recomputed post-balancing, plus:

- Source-by-source funnel: rows in → extracted → normalised → kept / rejected (by reason) → parked →
  deduplicated → capped → final. Must reconcile exactly at every stage.
- Partition sizes and the per-family stratification check.
- Every CHECKPOINT decision Laura made, with counts.
- Parameter values, seeds, input hashes and `source_dataset` names, tool versions.
- Before/after comparison of the target distribution, showing what the cap did.

---

## 10. Expected corpus size — sanity projection

An estimate, not a prediction. Revised upward from v1.1 because riboaptamer now contributes real
sequences and AptaDB's interaction join unlocks structured protein targets.

| Lane | Rows in | Rough survivors after RNA + protein-target + evidence + length | Notes |
|---|---:|---:|---|
| AptaDiff A + B | 25,350 | capped to ≤5% of total each | 2 targets |
| AptamerBase | 2,128 | ~400–900 | 179 missing, 184 dup, RNA-like |
| riboaptamer | 509 | ~200–350 | **Revised up.** ~364 records in protein-leaning categories; RNA throughout; some E1/E2 |
| UTexas | 1,894 | ~250–500 | RNA subset of a mixed DB, 399 missing |
| AptaDB | 1,350 interactions | ~150–300 | **Revised up.** 639 protein interactions × RNA fraction (264/1,293 aptamers) |
| AptaIndex | 1,050 | ~150–270 | RNA 200 + 2′-F 71 |
| ENA | 679 | ~150–400 | many may fall to E5 |
| AptaBase | 610 | ~100–300 | mixed |
| NCBI nucleotide | 18 | ~10 | mostly ENA overlap |
| **Diverse (non-AptaDiff) total, pre-dedup** | | **~1,400–3,000** | |
| **After 90% clustering** | | **~500–1,700 clusters** | SELEX families collapse hard |

So roughly **one to three thousand sequences across a few hundred targets**, AptaDiff capped to a
modest share. Small, but not unreasonable for parameter-efficient fine-tuning of the generative
components on a frozen encoder — which is exactly why the plan freezes the encoder.

**Trigger points.** If the diverse lane yields fewer than ~500 clusters, relax in this order:
(1) admit E5 records, (2) admit non-protein targets, (3) raise the length ceiling, (4) fetch the
AptaDB molecule/cell/other lookup tables to make non-protein AptaDB targets nameable. The parked
files exist so steps 1 and 2 are one-line filter changes rather than a re-run.

---

## 11. Validation and acceptance tests

Implement as assertions in the pipeline, not manual checks.

**Integrity**
- [ ] No file under `data/raw/` modified — sha256 of every file matches pre-run (203/203).
- [ ] Every registered input's sha256 and row count match `source_registry.csv` (hard fail).
- [ ] Divergence from `raw_data_inventory.csv` reported as a warning naming both hashes.
- [ ] `corpus_manifest.json` embeds the full registry, every parameter, and every seed.
- [ ] Re-running from the same inputs produces a byte-identical `corpus_final.csv`.
- [ ] No forbidden input (§4.5) was opened — including `~$extracted_data.xlsx`.

**Reconciliation**
- [ ] For every source and stage: `rows_in == rows_kept + rows_rejected + rows_parked`.
- [ ] Every rejected record has a closed-vocabulary reason.
- [ ] No record disappears anywhere without a log entry.
- [ ] The ENA 679 vs 676 delta is explicitly reconciled and documented.

**Schema**
- [ ] All required columns present and non-empty in `corpus_final.csv`.
- [ ] `record_id` unique; every record has a non-empty `source_dataset`.
- [ ] `sequence_length_full == len(sequence_full)`; `sequence_length_core == len(sequence_core)`.
- [ ] Every `sequence_core` in RNA lanes matches `^[ACGU]{20,100}$`.
- [ ] `sequence_core` is a substring of `sequence_full` for every record.
- [ ] `parked_ssdna.csv` sequences match `^[ACGT]+$`.
- [ ] `t_to_u_applied` is false wherever `alphabet_as_reported == RNA_U`.
- [ ] `binding_evidence_score` ∈ {2,3,4,5} in `corpus_final.csv` (E5 is parked).
- [ ] Every `pdb_id` is a plausible 4-character code.

**Leakage — hard gate**
- [ ] Zero exact matches between `corpus_final.csv` (`sequence_full` or `sequence_core`) and
      `leakage_exclusion_set.csv`.
- [ ] Zero ≥90%-identity matches against the exclusion set.
- [ ] No `target_name` matches NDM-1, KPC-2, OXA-48, or human serum albumin, including dictionary
      synonyms.
- [ ] No cluster spans two partitions.

**Corpus properties**
- [ ] No single `target_name` exceeds `MAX_TARGET_FRACTION` of records.
- [ ] Every record has exactly one `cluster_id`; every cluster exactly one representative.
- [ ] `contributing_sources` of every deduplicated record contains its `source_db`, and
      `corroboration_count == len(contributing_sources)`.
- [ ] ENA `near_duplicate_family_id` families do not split across clusters (clustering sanity check).
- [ ] Length distribution tested for bimodality; if bimodal, the report says so prominently.
- [ ] `corpus_final.txt` has no duplicate lines, and its line count equals the number of distinct
      `sequence_core` values in the `FT` partition.
- [ ] riboaptamer regression: <1% of its sequences end in `.`/`…`; median length >20 nt.

---

## 12. Directory layout

```
config/
├── curation_config.yaml          # thresholds, seeds, MAX_TARGET_FRACTION, TRAINING_SEQUENCE_COLUMN
└── constant_regions.yaml         # known promoters/primers, grows via CHECKPOINT-1

docs/
├── log.md                        # running project log (§17)
└── data_curation/                # inventory, assessment, questions, this plan

data/                             # ENTIRELY GITIGNORED (§18)
├── raw/                                   # READ-ONLY. Never written to.
├── interim/
│   ├── registry/source_registry.csv
│   ├── leakage_exclusion_set.csv
│   ├── extracted/{source}_extracted.csv
│   ├── normalised/{source}_normalised.csv + {source}_qc.md + detected_constants_{source}.csv
│   ├── filtered/{source}_clean.csv + rejected_{source}.csv + {source}_review.csv
│   ├── reviewed/{source}_review_completed.csv        # returned by Laura
│   ├── merged/target_dictionary.csv + target_review.csv + all_sources_merged.csv
│   └── deduplicated/corpus_dedup.csv + clusters.tsv + overlap_report.md
│                    + corpus_profile_report.md + figures/
└── processed/
    ├── corpus_final.csv / corpus_final.txt
    ├── corpus_replication_datasetA.csv
    ├── parked_ssdna.csv / parked_non_protein_targets.csv / parked_evidence_e5.csv
    ├── evaluation_references.csv
    ├── rejected_all.csv
    ├── corpus_report.md
    └── corpus_manifest.json

scripts/data_preparation/
├── s0_build_registry.py
├── s1_extract.py + adapters/{source}.py
├── s2_normalise.py
├── s3_filter.py + s3_apply_review.py
├── s4_normalise_targets.py + s4_apply_target_review.py
├── s5_deduplicate.py
├── s6_profile_report.py
├── s7_finalise.py
├── common/sequence_normalisation.py     # ONE implementation, shared by all sources
├── common/constant_region_detection.py
├── common/evidence_ladder.py
└── tests/
```

---

## 13. Sequencing of work

1. S0 registry + leakage set — cheap, and the hash gate catches input drift immediately.
2. `common/sequence_normalisation.py` and `common/constant_region_detection.py` with unit tests —
   **write these before any adapter.** Every source-specific bug fixed inside an adapter instead of
   here becomes a permanent inconsistency in the corpus.
3. Adapters in order of value per hour: `ena` → `riboaptamer` → `aptamerbase` → `aptadb` (join is
   now known, and it brings structured UniProt targets that seed the target dictionary) → `utexas`
   → `aptabase` → `aptaindex` (hardest, needs the notation parser) → `ncbi_nuc` → `aptadiff_a/b`
   (trivial schema) → eval lane.
4. Run S1–S3 for the first two adapters and do CHECKPOINT-1 on those **before writing the rest** —
   the review will change the filter and trim rules, and it is cheaper to learn that on two sources
   than on ten.
5. Start target normalisation (S4) early and in parallel; it has the longest human turnaround and
   everything downstream waits on it. Seed it from AptaDB `protein.csv` immediately.
6. S5, S6 (supervisor checkpoint), S7.

---

## 14. Deliberately deferred

Not in v1; these belong to the later RNA-aware splitting and balancing plan:

- Structure-aware or fold-similarity deduplication beyond sequence identity.
- Target-family *balancing* beyond the per-target cap — S6 gives supervisors the evidence to specify
  this properly.
- Sequence-similarity-aware train/val/test splitting within `FT` — `cluster_id` and `partition` are
  the hooks it will use.
- Structure prediction, folding energy, or Tier 1 feature extraction. The corpus is the input to
  those, not the place to compute them.
- Fetching missing external payloads (Zenodo, InstructNA FASTQ, SRA reads, AptaDB molecule/cell/other
  tables).

---

## 15. Standing rules for the implementing agent

1. **`data/raw/` is read-only.** No writes, moves, renames, deletions. Verify by sha256 after runs.
2. **Never silently drop a record.** Every exclusion gets a rejection-log row with a closed-vocabulary
   reason (§3). A record vanishing without a log entry is a bug.
3. **One normalisation implementation.** All sources call the same functions in `common/`.
   Source-specific handling lives in adapters and is limited to column mapping and format parsing.
4. **Determinism.** Every random operation uses a seed from the config. Two runs on the same inputs
   produce byte-identical outputs.
5. **Stop at CHECKPOINTs.** Emit the artefact and stop. Do not guess Laura's judgement calls.
6. **Stop at DECISION REQUIRED.** Ask; do not default silently.
7. **Do not re-open DECIDED items.**
8. **Never read a forbidden input** (§4.5). If a needed field seems missing from an allowed input,
   ask — do not reach into the derived ENA trees.
9. **Read paths from the registry, never hardcoded.**
10. **Config over constants.** Thresholds, fractions, seeds live in `config/curation_config.yaml`.
11. **Every stage writes a QC report and appends to `docs/log.md`** (§17). A stage producing data but
    no report and no log entry is incomplete.
12. **Never commit data** (§18). Code, docs, and configs go to GitHub; sequences do not.

---

## 16. Remaining open items

All Stage-S0 blockers are resolved. What is left:

| Item | Status |
|---|---|
| `MAX_TARGET_FRACTION` final value | **Deferred by design** to CHECKPOINT-3, once the profile report shows real cluster counts and the size-versus-diversity tradeoff at 0.02 / 0.03 / 0.05 / 0.10. Default 0.05 until then |
| ENA 679 vs 676 reconciliation | **Required at CHECKPOINT-1** (§5.2). Not a blocker for starting |
| riboaptamer Category → target-type mapping | **Resolved as an approach** (§5.1): Category is a prior, per-record resolution happens at S4, disagreements surface at CHECKPOINT-2 |
| AptaDB molecule/cell/other lookup tables | Not local. Only needed if the non-protein lane is promoted. Records park correctly without them |
| Precision-SELEX column I heading | Incomplete in the source ("library 1" inferred). Note in `notes`; do not guess in code |
| `rbms_paper` / `instructNA_paper` payloads | Still absent; Tier 3, out of scope |

---

## 17. Project log — `docs/log.md`

**Requirement.** A single running log describing the project's methods as they develop, updated
continuously rather than reconstructed at the end. It is the raw material for the thesis methods
section and for supervisor updates, so it should be written in prose a reader outside the project
can follow — not as a commit log.

### 17.1 Structure

```markdown
# Project log — RNAGenesis aptamer MRes

## <YYYY-MM-DD> — <short title>
**Stage:** <e.g. Aim 2 / data curation / S2 normalisation>
**What was done:** <prose, 1–3 paragraphs>
**Decisions made:** <bullets, each with the reasoning, not just the outcome>
**Inputs used:** <source_dataset names and hashes, or a pointer to the manifest>
**Outputs produced:** <paths>
**Numbers:** <counts that a reader would want: rows in/out, rejections by reason>
**Open questions carried forward:** <bullets>
```

### 17.2 Entry 1 — to write now

The first entry covers the raw-data inventory and the search that produced it. Suggested content,
to be written up rather than pasted:

- **Data search completed 28 July 2026.** Describe what was searched and why: a systematic search
  for target-specific RNA HT-SELEX or activity-screening data against KPC-2, NDM-1, and OXA-48,
  which established that no such dataset exists at fine-tuning scale, and a broader search for
  multi-target RNA aptamer resources to support the adaptation strategy actually adopted. Name the
  resources identified: AptaDiff datasets, ENA, AptaDB, AptaIndex/Aptagen, the UTexas Aptamer
  Database, AptaBase, AptamerBase, Ribocentre-aptamer, NCBI Nucleotide/GEO/SRA, and the individual
  papers (Chen, Shi, the selektion dissertation, Yu et al. precision-SELEX).
- **Raw-data inventory, 4 August 2026.** 203 files across 29 directories and 21 top-level sources,
  ~118 MB, produced read-only by `scripts/data_preparation/inventory_raw_data.py`, with 203/203
  SHA-256 pre/post match confirming nothing under `data/raw` was modified. Six unit tests pass.
- **Reconciliation against the previous inventory:** 5 added, 3 removed, 2 modified (`.DS_Store`
  only), 196 unchanged. The substantive changes were: AptaDB `interaction.csv` added (resolving the
  aptamer–protein join), riboaptamer re-downloaded with full sequences replacing a truncated export,
  and `li_et_al` removed for unresolved provenance.
- **Principal findings:** a large fraction of the `ENA/` tree is derived review output rather than
  source data, so only one ENA file is a legitimate input; several sources carry mixed DNA/RNA and
  modified chemistries; target annotation is heterogeneous and in one source absent entirely; and
  the AptaDiff datasets, while by far the largest, cover only two targets.
- **Questions raised and resolved:** the six Q1–Q6 items in `raw_data_curation_questions.csv`, with
  their resolutions — most usefully that the selektion D9 clones are RNA aptamers against NDM-1,
  which sharpens the methods framing (§1.2).
- **Decision taken:** proceed to a specified, checkpointed curation pipeline rather than ad-hoc
  per-source cleaning, on the grounds that the corpus feeds three consumers with conflicting
  requirements and needs an auditable provenance trail.

### 17.3 Ongoing rule

Every pipeline stage appends an entry when it completes (§15 rule 11). Every CHECKPOINT appends an
entry recording what was reviewed, what was decided, and why — the reasoning is the part that will
be hard to reconstruct in November and is exactly what the methods section needs.

---

## 18. Version control and data handling

**DECIDED — code and documentation to GitHub; data stays local.**

`.gitignore` must contain at minimum:

```gitignore
# Data is local-only — never committed
data/

# OS and editor noise
.DS_Store
~$*
*.tmp

# Environments and caches
.venv/
__pycache__/
*.pyc
```

**Tracked:** `scripts/`, `config/`, `docs/`, `tests/`, environment specification, README.
**Not tracked:** everything under `data/`.

Three cautions:

1. **The reports are not automatically safe to commit.** `corpus_report.md` and
   `corpus_profile_report.md` are aggregate statistics and are fine, but any report that embeds
   example sequences is not. Write report generators to emit counts and distributions, and put
   sequence-level examples in a separate file under `data/`.
2. **`leakage_exclusion_set.csv` must never be committed** — it contains the sequences that define
   the evaluation, and it lives under `data/`, which is covered.
3. **Licence constraints follow the data, not the repo.** AptaIndex ships a Data Use Agreement and
   the AptaBase scrape has terms implications (§2.8). Keeping `data/` out of the public repo handles
   the immediate risk, but the redistribution question returns if the corpus is released alongside
   the ICDM paper — the `redistribution_status` reporting exists to answer it when it does.

The inventory CSV and this plan contain schemas, column names, counts, and file paths but no
sequences, so both are safe to track under `docs/`.

---

## 19. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-04 | Initial specification from the curation notes, raw-data state assessment, and inventory of 201 files across 21 sources. |
| 1.1 | 2026-08-04 | Confirmed AptaDiff downsampling; three sequence columns plus constant-region detection; three-way partition and evidence ladder confirmed; supervisor profile report added as its own stage and checkpoint before balancing; target normalisation made to precede all grouping and splitting; corroboration-as-reliability and redistribution status added; riboaptamer promoted after the truncation fix; source registry made authoritative over the inventory. |
| 1.2 | 2026-08-04 | Q1–Q6 resolved against the refreshed 203-file inventory. Record grain defined as (sequence, target) and dedup keyed accordingly. ENA input registered as the 679-row review_v2 file with a required 679-vs-676 reconciliation and an explicit singleton policy. riboaptamer resolved to `all_sequences_509_rows.csv` with Category treated as a prior rather than a rule. AptaDB resolved to interaction-grain via `interaction.csv`, upgrading it from E5-by-default and seeding the target dictionary with 194 UniProt entries. Precision-SELEX layout resolved (column B primary, even rows from row 4). Selektion D9 confirmed RNA, with the resulting thesis reframing recorded. `li_et_al` removed. Added `alphabet_as_reported` / `t_to_u_applied` transcription provenance and `target_type_source`. `TRAINING_SEQUENCE_COLUMN` fixed to `sequence_core`. Added §17 project log and §18 version-control and data-handling policy. |
