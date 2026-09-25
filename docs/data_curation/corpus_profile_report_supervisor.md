# Supervisor briefing: corrected RNA aptamer corpus closure

**Status: corrective S7D complete — 2026-09-25.** Target capping, FT/REF/EVAL
partitioning, and the subordinate TRAIN/VALIDATION split are complete and frozen.
The CHECKPOINT-3 choices are recorded and applied; this is the final corpus handoff.

- Corrective closure: `10aac629bb0ef0337107c3d628b23e1897962af9` — `Complete corrective corpus revision for RNA modelling alphabet gate`.
- Documentation handoff: `05616cf82c3c7c1adbe87f631590f456c44c946a` — `Clarify corrected corpus documentation handoff`.
- Superseded corpus: `095236dfb13d1d3b13f11bbb34c2e48319c10184`. Its counts and hashes are historical and must not be used for modelling.
- Authoritative records: [2026-09-25 corrective log entry](../log.md#2026-09-25--corrective-corpus-revision-for-the-rna-modelling-alphabet-gate), [S7D final build](global_s7d_final_build.md), [curation plan v1.6](rna_aptamer_corpus_curation_plan.md), and [processed corpus report](../../data/processed/corpus_report.md).

## Executive summary

The corrected primary RNA/protein corpus contains **1170 curated aptamer–target
identities / 790 leakage-safe sequence clusters / 1031 unique sequence cores**,
covering **409 canonical protein targets**. The RNAGenesis fitting file,
`data/processed/corpus_final.txt`, contains **669 unique TRAIN cores** only.

TRAIN and VALIDATION cores pass `^[ACGU]+$` with **0 failures**. The closure records
**0 cross-role cluster leakage** and **0 cross-role core leakage**. The maximum
target share is HIV-1 Rev protein at 34/1170 (2.906%), within the approved 3% cap.
The primary corpus remains protein-only and E2–E4; E5 remains excluded.

RNAGenesis M0 resumes from this corrected corpus. **Do not rerun S7D or any curation
stage for this handoff.** This report update changes documentation only.

## Frozen modelling roles

Counts are explicitly ordered as identities / clusters / unique cores.

| Role | Identities | Clusters | Unique cores | Permitted use |
| --- | ---: | ---: | ---: | --- |
| TRAIN | 726 | 569 | 669 | RNAGenesis fitting. |
| VALIDATION | 132 | 63 | 95 | Checkpoint selection and model-development decisions. |
| REF | 131 | 79 | 113 | AptaRank calibration only. |
| EVAL | 181 | 79 | 154 | Final held-out assessment only. |
| **Final corpus** | **1170** | **790** | **1031** | All frozen roles combined. |

Top-level `partition` remains FT/REF/EVAL, with 858/131/181 identities. TRAIN and
VALIDATION are the subordinate FT split. `corpus_final.txt` equals deduplicated
TRAIN `sequence_core` values in first-occurrence order, with 669 lines, 669 unique
lines, and no VALIDATION/REF/EVAL contamination.

Use only TRAIN for RNAGenesis fitting. REF and EVAL must not inform RNAGenesis
training, checkpoint selection, learning-rate choice, generation hyperparameters,
or other model-development decisions. The separate `evaluation_references.csv`
contains target-specific biological references and controls; it is not the generic
EVAL partition.

## Recorded decisions and completed implementation

The [2026-09-21 CHECKPOINT-3 decision record](checkpoint3_supervisor_decisions_2026-09-21.md)
preserves the original advice and approval context. Its milestone-time implementation
status is historical; the corrected closure completes the approved work.

| Decision | Recorded policy | Corrected closure result |
| --- | --- | --- |
| C3-01 | Maximum target share 3%, calculated against the post-cap identity denominator. | Applied; every target passes. |
| C3-02 | No additional target-family balancing; compare target representation, evidence, length regime, and source; use family labels as a secondary diagnostic. | Frozen FT/REF/EVAL and TRAIN/VALIDATION splits are complete. |
| C3-03 | Retain E2–E4; exclude E5 and quantify its possible inclusion separately. | E2 800, E3 247, E4 123, E5 0; informational E5 diagnostic complete. |
| C3-04 | Retain protein-only primary scope. | Non-protein records remain parked. |
| C3-05 | Remove whole clusters deterministically: target-pure first, ranked by descending target count; use mixed clusters only if needed with least collateral removal; break ties by stable cluster ID and recompute the denominator after each removal. | Two NGF target-pure clusters removed; 108 identities; no mixed-cluster or collateral removals. |

The corrected S7A input contained **1278 pre-cap identities / 792 clusters / 1139
unique cores**. Removing the 89- and 19-identity NGF clusters produced **1170 /
790 / 1031**. NGF fell from 131/1278 (10.25%, pre-cap) to 23/1170 (1.966%, final).
See the [corrected S7A aggregate report and removal trace](../../data/interim/s7a_target_cap/s7a_target_cap_report.md).
These pre-cap figures are stage context, not alternative final counts.

## Corrective workstream and validation

The earlier corpus failed the M0 alphabet gate. The seven-record disposition was:

- `aptabase:592` and `aptabase:593`: genuine ssDNA; parked out of the primary RNA corpus.
- `aptabase:104`: corrected RNA core of 19 nt; rejected below the 20 nt minimum.
- `aptabase:185`, `aptabase:118`, and `aptabase:123`: RNA cores corrected and retained in TRAIN.
- `aptabase:82`: RNA core corrected and retained in VALIDATION.

No silent T-to-U conversion was used. The corrective workstream reran the Aptabase
CHECKPOINT-1 overlay, global S4/CHECKPOINT-2, S5A–S5E, S6, and S7A–S7D. S7D then
assembled and validated the corrected frozen splits. This documentation update
does not repeat those stages.

The closure records passing RNA alphabet, TRAIN-only text equality, 3% target cap,
cross-role disjointness, and evaluation-reference leakage gates. At corpus closure,
model fine-tuning, REF calibration, and EVAL evaluation had not started; that is a
closure snapshot, not a live status claim about subsequent modelling work.

## Current aggregate profile

### Evidence, targets, and provenance

| Evidence | Identities | Share of final identities |
| --- | ---: | ---: |
| Quantitative affinity (E2) | 800 | 68.38% |
| Qualitative binding (E3) | 247 | 21.11% |
| Selection / enrichment (E4) | 123 | 10.51% |
| Database/deposit-only (E5) | 0 | 0.00% |

Target family is unknown for 986/1170 identities (84.27%). It remains a secondary
diagnostic rather than a balancing objective. The largest retained targets include
HIV-1 Rev protein (34), PAP (29), E.Coli rho factor (27), and Envelope glycoprotein
GP120 (27). Target capping reduces concentration without making targets equally represented.

| Primary metadata source | Final identities |
| --- | ---: |
| Aptabase | 99 |
| AptaDB | 70 |
| AptaIndex | 62 |
| AptamerBase | 491 |
| ENA | 127 |
| Riboaptamer | 217 |
| UT Austin | 104 |

These source counts identify the canonical metadata donor after exact deduplication;
contributing-source provenance is retained separately. Multiple sources support
138/1170 identities (11.79%); corroboration does not upgrade evidence level.
Redistribution status is unknown for 1116 identities (95.38%) and restricted for
54 (4.62%). No identity has independent permissive attestation. This describes
provenance, not a legal conclusion. Sequence-bearing outputs remain local under
ignored `data/`; these reports contain aggregate information without nucleotide strings.

Chemistry metadata are RNA 998, unknown 95, 2F-RNA 69, mixed 6, and 2OMe-RNA 2.
These metadata categories do not override the passing TRAIN/VALIDATION alphabet gate.

### Sequence-length regimes

The corrected S6 two-component length model was frozen before the final splits;
S7D did not refit it. Its component means are approximately 38.96 and 77.29 nt.
The final 1031 unique cores comprise 595 short-regime and 436 long-regime cores.
The pre-cap GMM mixture weights are not final-corpus proportions.

| Role | Short-regime cores | Long-regime cores |
| --- | ---: | ---: |
| TRAIN | 386 | 283 |
| VALIDATION | 55 | 40 |
| REF | 65 | 48 |
| EVAL | 89 | 65 |

The upstream profile found length regimes associated with source, without proving
a protocol cause. This remains a caveat for length priors and reference distributions.
Any RNAGenesis development choice must respect the frozen role restrictions above.

### E5 and other excluded lanes

The E5 counterfactual reports 521 relationship rows / 521 source records, 520 exact
identities / distinct cores, and 47 targets. It found 30 exact-core attachments and
3 additional >=90% diagnostic attachments, with 235 additional E5D diagnostic
cluster units. These are not the exact S5 clusters that would result from E5 admission:
the diagnostic did not rerun MMseqs clustering and lacked usable E5 ENA family must-links.
E5 remains excluded. Admission would require a new scientific revision and downstream splits.
Non-protein and ssDNA lanes remain outside the primary corpus. Dataset A is a separate
replication/comparability artefact and contributes no cores to `corpus_final.txt`.

## Current final hashes (SHA-256)

All paths below are relative to `data/processed/`. These are the hashes in the latest
corrective handoff, verified against the files on disk for this report update.

| File | SHA-256 |
| --- | --- |
| `corpus_final.csv` | `2797e6767f78029574df1b6cdf51bbe7952ea8affce83870441b3d3d93c98849` |
| `ft_train.csv` | `84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0` |
| `ft_validation.csv` | `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd` |
| `ref.csv` | `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23` |
| `eval.csv` | `ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015` |
| `corpus_final.txt` | `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d` |
| `corpus_manifest.json` | `08da8d5e44413ea9ab57c128dbe4ef7986dab7a2bfa794cfef6fb4724577565f` |

The manifest remains byte-for-byte unchanged. Its retained `build_date = 2026-09-22`,
`governing_plan_version = 1.5`, and pre-closure `repository_head_baseline` are build
metadata; the closure date, current plan, and commit authority are given at the top
of this report. Use the final-file hashes above for the modelling handoff.

## A short glossary

- **Curated aptamer–target identity (scientific identity):** one curated relationship between one aptamer's standardised binding sequence (sequence core) and one canonical protein target.
  The report's main denominator is 1,170 such relationships. The principal grain is one S5 scientific identity = one exact `(sequence_core, canonical_target_name)` relationship.
- **Sequence core / full sequence:** the core is the standardised sequence used to compare and cluster aptamers. The full sequence retains construct context such as flanking regions where available.
- **Sequence cluster / related-sequence cluster:** a group of similar sequence cores. Clusters are kept intact in the frozen splits so related sequences cannot leak between FT, REF, and EVAL. The final grouping combines 90% sequence-similarity clustering with trusted ENA family links; not every pair within a final cluster must itself be 90% identical.
- **Leakage-safe:** closely related sequences are assigned together, rather than being allowed to appear in both model development and evaluation datasets.
- **Evidence level:** E2 means a reported quantitative affinity measurement (for example Kd, Ka, or IC50) against a named protein; E3 means a named qualitative binding assay without a quantitative constant; E4 means a published selection/enrichment result without an independent binding assay; E5 means a database/deposit target annotation without a traceable assay. The current inclusion threshold is E4 or stronger.
- **Corroboration:** independent source databases supporting the same aptamer–target identity. It preserves provenance but does not upgrade the evidence level.
- **FT / REF / EVAL:** frozen fine-tuning, reference, and evaluation partitions. FT is further split into TRAIN and VALIDATION; only TRAIN is used for fitting.

## Historical / superseded context — not the final modelling contract

### Superseded 2026-09-22 corpus

The superseded build had 1173 identities / 794 clusters / 1036 unique cores,
411 targets, FT/REF/EVAL identity counts 895/114/164, and 678 unique TRAIN cores.
Its TRAIN counts were 746 identities / 571 clusters / 678 cores; VALIDATION was
149 / 64 / 117. These values and that build's hashes are superseded by the corrected
closure. Historical final-file hashes are not repeated here; they remain in Git history.

### Corrected S6/pre-cap profile retained for stage provenance

The former live briefing described S6 rather than the completed S7D corpus. Its
1278 identities / 792 clusters / 1139 cores are the corrected **pre-cap** population,
not the final modelling population. The summary below preserves that stage context.

| Pre-cap measure | Historical stage value |
| --- | --- |
| NGF | 131/1278 identities (10.25%); 14 clusters. |
| Target family unknown | 1094/1278 identities (85.60%). |
| Evidence E2 / E3 / E4 / E5 | 800 / 247 / 231 / 0. |
| Primary ENA identities | 235, before 108 NGF cap removals. |
| Redistribution status | Unknown 1224 (95.77%); restricted 54 (4.23%). |
| Target-count diversity | Gini 0.552594; Shannon 5.233210 nats; normalised Shannon 0.870212; effective targets 187.39. |
| Core-length profile, identity grain | Median 50 nt; mean 55.894 nt; 5th–95th percentile 29–92 nt. |
| Full-length profile, identity grain | Median 51 nt; mean 57.685 nt; 5th–95th percentile 29–93 nt. |
| Core/full lengths equal | 1207/1278 identities (94.4%). |
| Distinct-core GC profile | Mean 0.531117; median 0.530120; 5th–95th percentile 0.400000–0.650000. |
| Pre-cap clusters | 634 singleton-core and 158 multi-sequence clusters; largest NGF clusters contained 89 and 19 cores. |
| Multi-target/source context | 144 multi-target clusters; 188 multi-source clusters; 119 multi-target cores. |

These pre-cap diversity, length, GC, and cluster statistics have not been relabelled
as final-corpus measurements. The previous statement that a small amount of T was
retained is superseded; the corrected TRAIN/VALIDATION RNA alphabet gate passes.

### Historical target-cap alternatives

The pre-cap consultation compared 2%, 3%, 5%, and 10% caps. Its idealised
record-wise retained sizes were 1155, 1185, 1210, and 1274 respectively. Those were
decision-support simulations, not final S7 results. The former 5% placeholder and
open decision requests are superseded by the recorded 3% whole-cluster policy.
The applied corrected result is 1170 identities.

### Historical S6 figure pack — pre-cap only

The existing figures below were generated for the S6/pre-cap profile and were not
regenerated in this documentation update. Their denominators and captions are
historical; do not circulate them as figures for the final 1170-identity corpus.

| Existing figure | Historical scope |
| --- | --- |
| `fig01_top30_targets.png` | Pre-cap target/cluster representation, including the NGF concentration before removal. |
| `fig02_target_family.png` | Pre-cap family annotation coverage. |
| `fig03_sequence_core_length.png` | Pre-cap distinct-core length and source association. |
| `fig04_sequence_full_length.png` | Pre-cap core versus full-construct length. |
| `fig05_gc_distribution.png` | Pre-cap distinct-core GC distribution. |
| `fig06_cluster_size.png` | Pre-cap clusters, including the two subsequently removed NGF clusters. |
| `fig07_evidence_level.png` | Pre-cap E2–E4 counts and percentages. |
| `fig08_source_contribution.png` | Pre-cap primary metadata-source distribution. |
| `fig09_candidate_target_cap.png` | Unapplied alternatives; neither simulation curve is the final result. |
| `fig10_corroboration.png` | Pre-cap independent-source support. |

### Upstream S4/S5 freeze hashes — stage provenance only

The following existing hashes identify upstream artefacts, not final S7D outputs.
They are retained to preserve the S6 briefing's reproducibility context. They must
not substitute for the current final-file hashes above, even where an upstream
hash remains valid after the corrective rebuild.

#### Upstream S4 freeze

- `reviewed_relationships`: `252987d71839623566ea1fa5ddf0c0c591d23fe39fad858f84d212d7abf5d458`
- `reviewed_dictionary`: `afcd8f02e13feee26bb54cf1caad76508780828d4cee3816ab5c9c1cf0b178d8`
- `record_map`: `701acc7134f010401a49c137e80ff4bc50f31a9645b71cda4ae686426a032d7f`
- `parked_audit`: `d46730de8de9e4f111866f2543269b6d72c56e45bc89e65f92de36481c6aabd2`
- `routing_summary`: `add4655eaf498e3b369f66b12866c6a32e837e28b4d49bc44a1c5245ab939ff6`
- `combined_input`: `6609f1839cbe8ce335f04a9be4fa865b6127514d307c757c77ff71871c558fd0`

#### Upstream S5A freeze

- `corpus_dedup_csv`: `f92a4858afe354db036b974cf90456de409131a24d257b30c400a00d4a351d86`
- `membership_csv`: `c6a34cb0158dc9492f45683bd18fc8f0355c659ffcc1ec6f2d542bcf6a7b582c`
- `groups_csv`: `2eb63537abb5121bc79dc2a41cb26bbbc935008eb1015103d5a1e9f89ab3d903`
- `dictionary_conflicts_csv`: `5b44c9a59b86be1350d43eaf0ca8812d7130399832ba7c46f7ecceea7fb8be8f`
- `multi_target_csv`: `7c81edf29df24ee06a8218a6ebb8c00dd15a21bb3efbaccf4cd108ca6498963b`
- `overlap_matrix_csv`: `8de8bbb1d1c569e3be5117591033ad1963a649ccabe6e576a9c8b0d0c1e2f348`
- `report_md`: `77d43b1299389cd90f0de076431d8a1adfc9f2ff38ef244d45e82a5d0ab22062`

#### Upstream final S5 freeze (before S7A)

- `clusters_final_tsv`: `29aaf4089be3b736a2a81d3aa92af6663cda21ccbf7c1f35a113b9ee1126d677`
- `corpus_clustered_final_csv`: `c6ee6288423d863e55bbfa1b73ccee66f2999e27f3bae04d3b95d200c35e56d6`
- `cluster_summary_final_csv`: `79fa62b0041b6f38bb6b8c87847035078b5bf5186eae8cd2415cf48722b97907`
- `cluster_union_provenance_csv`: `00d558f3525a14125d30d208005c2cb1e91bb82d1a298b8f27ffdebf9b698140`
- `overlap_report_md`: `c00003a7d15eae1aed950373e6b66da16eeb6b96eb0687d413b70d0742e959cc`
- `manifest_json`: `5a81d328dd10d712088b458782a1b89db94e3d75c70c703b7d578c2d06db6ede`

## Report-update boundary

Only this report and `data/processed/corpus_report.md` are updated. No curation
stage, model training, generation, or evaluation is run; no corpus payload, split,
manifest, figure, or scientific decision is changed. REF/EVAL sequence content is
not inspected for this update. Verification uses the recorded aggregate closure
results, file hashes, and lightweight TRAIN/VALIDATION and training-text checks.
