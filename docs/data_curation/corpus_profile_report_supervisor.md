# Supervisor briefing: curated RNA aptamer corpus — decisions before final split

## What we need from you

The corpus has been curated and grouped to prevent closely related sequences
from being separated across future datasets. It is ready for consultation, but
it is **not yet balanced or split**. Please advise on the five choices below so
we can freeze the final training, reference, and evaluation datasets (FT/REF/EVAL)
and keep the fine-tuning timeline on track. No exact response deadline is assumed,
but timely responses are needed to avoid delaying that next step.

| Decision | Question for supervisors | Current context |
| --- | --- | --- |
| C3-01 | What maximum share of the final corpus may any one target occupy: 2%, 3%, 5%, 10%, or another value? | NGF is 131/1,278 identities (10.25%); the current configuration's 5% value is only a placeholder, not a decision. |
| C3-02 | Should there be balancing beyond the per-target cap? | The planned split uses target family as a stratification variable, but 1,094/1,278 identities (85.6%) have family unknown; this severely limits meaningful family-based balancing or stratification as written. |
| C3-03 | Keep the present minimum evidence standard, or include lower-confidence E5 records? | The current corpus is E2–E4 only and already has 792 sequence clusters, above the plan's ~500-cluster contingency trigger. |
| C3-04 | Keep the protein-only corpus, or include the separately parked non-protein records? | The present corpus is protein-only; adding non-proteins would change the biological scope and transfer framing. |
| C3-05 | What deterministic rule should select **whole sequence clusters** when enforcing C3-01? | The plan requires cluster-level capping but does not yet specify the denominator, ranking/tie-breaks, or treatment of clusters that touch multiple targets. |

**Standing note:** this report presents evidence and trade-offs; it does not recommend
or silently select any option. Once the five choices are recorded, the remaining work
is to apply the approved cap, assign whole clusters to FT/REF/EVAL, and create the
fine-tuning train/validation split.

## Executive summary

The curated primary RNA/protein corpus contains **1,278 curated aptamer–target identities**,
representing **1,139 distinct sequence cores**, in **792 leakage-safe sequence clusters**,
across **409 canonical protein targets**. Exact duplicate observations have already had their
provenance merged; no balancing, target capping, partitioning, or train/validation split has yet occurred.

The corpus is viable at its current size: 792 clusters is above the plan's `<500`-cluster
trigger for considering broader inclusion criteria. The principal policy issue is target imbalance.
NGF contributes 131 identities (10.25%); all other targets are much smaller.
The corpus also has a major limitation for the planned split: target-family labels are unresolved
(unknown) for **85.60%** of identities. Thus, a split nominally stratified by target
family would be dominated by one unknown stratum, rather than providing broad, biologically informative
family coverage.

Evidence is predominantly strong or directly measured: quantitative affinity (E2) 800 (62.60%),
qualitative binding (E3) 247 (19.33%), and selection/enrichment (E4) 231 (18.08%);
no E5 records are in the primary corpus. Sequence lengths show two substantial regimes
centred near 39 and 77 nucleotides;
this is a modelling/reference-distribution consideration, not a reason to remove records.
Licensing metadata are mostly unresolved (95.77%) with 4.23% restricted;
this is documented provenance, not a legal conclusion or an exclusion rule.

## A short glossary

- **Curated aptamer–target identity (scientific identity):** one curated relationship between one aptamer's standardised binding sequence (sequence core) and one canonical protein target.
  The report's main denominator is 1,278 such relationships. The principal grain is one S5 scientific identity = one exact `(sequence_core, canonical_target_name)` relationship.
- **Sequence core / full sequence:** the core is the standardised sequence used to compare and cluster aptamers. The full sequence retains construct context such as flanking regions where available.
- **Sequence cluster / related-sequence cluster:** a group of similar sequence cores. Clusters are kept intact in later splits so related sequences cannot leak between FT, REF, and EVAL. The final grouping combines 90% sequence-similarity clustering with trusted ENA family links; not every pair within a final cluster must itself be 90% identical.
- **Leakage-safe:** closely related sequences are assigned together, rather than being allowed to appear in both model development and evaluation datasets.
- **Evidence level:** E2 means a reported quantitative affinity measurement (for example Kd, Ka, or IC50) against a named protein; E3 means a named qualitative binding assay without a quantitative constant; E4 means a published selection/enrichment result without an independent binding assay; E5 means a database/deposit target annotation without a traceable assay. The current inclusion threshold is E4 or stronger.
- **Corroboration:** independent source databases supporting the same aptamer–target identity. It preserves provenance but does not upgrade the evidence level.
- **FT / REF / EVAL:** future fine-tuning, reference, and evaluation partitions. They have not yet been assigned.

## Corpus at a glance

| Measure | Result | Plain-language meaning |
| --- | --- | --- |
| Curated aptamer–target identities | 1,278 | Curated sequence–target relationships available before balancing. |
| Distinct sequence cores | 1,139 | Some cores bind more than one retained target. |
| Leakage-safe clusters | 792 | The independent units available for future partitioning. |
| Canonical protein targets | 409 | Nominal target breadth before accounting for imbalance. |
| Singleton clusters | 634/792 (80.1%) | Most clusters contain a single distinct core. |
| Largest target | NGF: 131 (10.25%) | A target cap is needed if this concentration is undesirable. |
| Quantitative-affinity evidence | 800/1,278 (62.60%) | Most identities have a reported quantitative measurement. |
| Target family unknown | 1,094/1,278 (85.60%) | Family-stratified splitting is currently weak. |
| UniProt-resolved targets | 53/409 (12.96%) | Target annotation remains incomplete. |

## What the target distribution means

The target counts are moderately concentrated rather than evenly spread:

- **Gini = 0.552594.** On a scale where 0 would mean every target has the same number of identities and 1 would mean extreme concentration, this indicates substantial imbalance.
- **Shannon entropy = 5.233210 nats; normalised Shannon = 0.870212.** These summarise diversity while giving less weight to rare targets than a simple target count.
- **Effective number of targets = 187.39.** Put plainly, the observed distribution carries about as much target diversity as **187 equally represented targets**, rather than 409 equally represented targets.

NGF is the largest target at present; it is 10.25% of identities. The next-largest targets are HIV-1 Rev protein (34; 2.66%), PAP (29; 2.27%), E.Coli rho factor (27; 2.11%), Envelope glycoprotein GP120 (27; 2.11%). There are 212 targets represented by only one identity and 240 represented by only one cluster.

### Target-family limitation for the planned split

The planned FT/REF/EVAL process stratifies by target family. However, 349 of 409 targets
and 1,094 of 1,278 identities have target family unknown. Known labels therefore
cannot provide the intended biological coverage for most of the corpus without either accepting a dominant
unknown stratum, enriching annotations in a bounded follow-up, or approving another explicit stratification
approach. This is central to C3-02, not a minor metadata caveat.

| Target family | Identities | Share |
| --- | --- | --- |
| unknown | 1,094 | 85.60% |
| enzyme | 78 | 6.10% |
| other | 27 | 2.11% |
| transcription factor | 23 | 1.80% |
| viral protein | 15 | 1.17% |
| receptor | 13 | 1.02% |
| antibody immunoglobulin | 11 | 0.86% |
| cytokine | 11 | 0.86% |
| growth factor | 4 | 0.31% |
| transport protein | 2 | 0.16% |

## C3-01: target-cap options

These simulations are decision support only. They use the present identity denominator and show an
idealised, record-wise result; the approved implementation must retain or remove **whole clusters**,
so the final size will depend on C3-05.

| Maximum target share | Nominal threshold | Targets above threshold | Raw excess identities | Idealised retained size | Interpretation |
| --- | --- | --- | --- | --- | --- |
| 2% | 25 | 5 | 123 | 1,155 | Broadest listed intervention. |
| 3% | 38 | 1 | 93 | 1,185 | Primarily reduces NGF. |
| 5% | 63 | 1 | 68 | 1,210 | Current configuration default; not preselected. |
| 10% | 127 | 1 | 4 | 1,274 | Minimal listed intervention. |

At each option, the overrepresented targets have enough identities in clusters that contain only that
target to absorb the raw excess in principle. Removing every cluster that touches an overrepresented
target would be much more conservative; those values illustrate a comparison range rather than a unique
S7 output. Neither comparison is the final predicted corpus size.

## Decisions requested at CHECKPOINT-3

Human choice is blank. S6 does not recommend a final approved option.

### C3-02 to C3-05: decision record

**C3-02 — further balancing.** Decide among: no additional balancing; target-family balancing; or another documented scheme. The v1 plan defers family balancing beyond the target cap. No family-balancing simulation has been run, and the unresolved family share is the key constraint.

**C3-03 — evidence threshold.** Decide among: retain the E4 minimum; admit parked E5; or another documented threshold. Admitting E5 has not been simulated. The current corpus has E2 800, E3 247, E4 231, E5 0, and 792 clusters.

**C3-04 — biological scope.** Decide among: retain the protein-only primary corpus; admit parked non-protein records; or another documented scope. Non-protein inclusion has not been simulated and would change the target-type mix.

**C3-05 — cap-selection semantics.** Specify a deterministic cluster-level rule, including: whether the cap is calculated against the post-cap final denominator; floor/ceiling convention; how whole clusters are ranked and ties resolved; how multi-target clusters are handled; and whether collateral identities may be removed when a cluster is selected for an overrepresented target. Without this, S7 cannot produce a unique capped corpus size.

## Evidence, sequence, and provenance considerations

### Evidence standard (C3-03)

| Evidence | Identities | Share | Meaning |
| --- | --- | --- | --- |
| Quantitative affinity (E2) | 800 | 62.60% | Quantitative affinity reported. |
| Qualitative binding (E3) | 247 | 19.33% | Named qualitative binding assay. |
| Selection / enrichment (E4) | 231 | 18.08% | Selection/enrichment evidence, no independent assay. |
| Database/deposit-only (E5) | 0 | 0.00% | Currently parked; not in this primary corpus. |

The current corpus retains E2–E4 only. Since there are 792 clusters, the contingency threshold
for relaxing inclusion (`<500` clusters) is **not met**. Admitting E5 would change the evidence mix and
corpus composition; it has not been simulated or applied.

### Sequence profile

Core lengths range from 20.0 to 123.0 nt (median 50.000; mean 55.894;
5th–95th percentile 29.000–92.000 nt). 13 retained, upstream-reviewed
identities exceed 100 nt. Distinct core lengths show material two-regime structure: the two-component model has
means of 38.96 and 77.29 nt,
weights 0.583 and 0.417,
and improves BIC by 434.427 over a one-component model. In plain terms, the corpus
contains sizeable short- and longer-sequence populations; later modelling and reference distributions should
reflect this rather than assume one typical length.

The two length regimes are also associated with data source rather than being
uniformly represented across databases. This suggests the apparent bimodality
may partly reflect source/protocol differences — such as construct design or
trimming conventions — as well as biological aptamer length. This matters when
defining empirical length priors or null/reference distributions: a single pooled
length distribution may inadvertently encode source-specific curation practices.

Observed association (not a proven protocol cause): each distinct core is assigned
to the shorter (~39.0 nt) or longer (~77.3 nt) two-component GMM
regime by maximum posterior probability. Length distributions differ strongly by
source; this is consistent with source-associated experimental designs, construct
definitions, or trimming conventions, but does not prove that those practices
caused the modes.

Observed source association: AptamerBase and ENA assigned predominantly to the shorter regime; Aptabase assigned predominantly to the longer regime; AptaDB, AptaIndex, Riboaptamer, and UT Austin more mixed.

- Aptabase: median 75.5 nt; 72 distinct cores; 23.61% shorter-regime / 76.39% longer-regime.
- AptaDB: median 51.0 nt; 46 distinct cores; 60.87% shorter-regime / 39.13% longer-regime.
- AptaIndex: median 77.0 nt; 42 distinct cores; 30.95% shorter-regime / 69.05% longer-regime.
- AptamerBase: median 40.0 nt; 448 distinct cores; 75.45% shorter-regime / 24.55% longer-regime.
- ENA: median 40.0 nt; 233 distinct cores; 74.68% shorter-regime / 25.32% longer-regime.
- Riboaptamer: median 71.0 nt; 205 distinct cores; 34.15% shorter-regime / 65.85% longer-regime.
- UT Austin: median 65.0 nt; 93 distinct cores; 34.41% shorter-regime / 65.59% longer-regime.

A later modelling-stage decision can determine whether reference/null
distributions need source or length-regime stratification. This is a modelling
caveat, not a new CHECKPOINT-3 decision.

Distinct-core GC fraction has mean 0.531117 (median 0.530120;
5th–95th percentile 0.400000–0.650000). The stored alphabet is predominantly RNA,
with a small amount of T retained as reported; this report does not reclassify chemistry.

### Clustering and multi-target relationships

There are 158 multi-sequence clusters, 144 clusters that include more than one canonical target,
and 188 clusters with more than one contributing source. Of 119 cores associated with multiple canonical targets,
105 create a cluster with an identical shared core and 39 are multi-target only through near-sequence membership.
These are retained relationships, not automatically claims of biological polyspecificity.

The largest cluster contains 89 cores/89 identities for NGF;
the next contains 19, for NGF.
6 clusters were created or expanded by trusted ENA family must-links. This confirms why cap implementation must operate at cluster level and be explicit about multi-target clusters.

### Sources, annotation, and redistribution

The primary-source distribution after exact deduplication is: Aptabase 99, AptaDB 70, AptaIndex 62, AptamerBase 491, ENA 235, Riboaptamer 217, UT Austin 104.
When the same sequence–target relationship appears in several databases, one source supplies the canonical
scalar metadata while all contributing-source provenance is retained. A total of
138/1,278 identities are supported by more than one source.

Redistribution metadata are unknown for 1,224 identities (95.77%) and restricted for 54 (4.23%);
none are labelled permissive, and no restricted/unknown identity has independent permissive attestation. This is descriptive provenance only and is not a legal conclusion or a decision to exclude records.

## Figure pack for the consultation

Please circulate the figure pack with this briefing. Captions are written so the figures can be read
without the technical appendix. The pack contains aggregate labels and counts, not sequences.

### Figure 1 — Target representation and independent sequence diversity

`fig01_top30_targets.png`

Bars show the number of curated aptamer–target identities and dots show the number of leakage-safe sequence clusters. A large gap means that many records belong to closely related sequence families rather than providing independent sequence diversity. NGF is the clearest example: 131 identities reduce to only 14 clusters. This is why the target-cap decision should operate on whole clusters rather than treating all records as independent.

### Figure 2 — Target-family annotation coverage

`fig02_target_family.png`

Target family is unresolved for 85.6% of the corpus. Because the planned FT/REF/EVAL split was intended to stratify by target family, this missing annotation substantially limits how informative family-based stratification can be without a further annotation step or an alternative split strategy.

### Figure 3 — Binding-sequence length and source-specific shapes

`fig03_sequence_core_length.png`

The top panel is the overall length distribution of distinct binding-sequence cores and shows two regimes, near 39.0 and 77.3 nt. The lower panels use the same bins and x-range for each donor source, plotted as within-source densities so shapes can be compared despite different source sizes. Observed source association: AptamerBase and ENA assigned predominantly to the shorter regime; Aptabase assigned predominantly to the longer regime; AptaDB, AptaIndex, Riboaptamer, and UT Austin more mixed. This is a modelling caveat for empirical length priors and null/reference distributions, not a reason to remove either mode.

### Figure 4 — Binding-sequence versus reported-construct length

`fig04_sequence_full_length.png`

Binding-sequence (core) and reported/full-construct lengths are shown on the same bins so construct context can be compared directly. Median core length is 50.0 nt; median full length is 51.0 nt; 94.4% of identities have the same core and full length (median difference 0.0 nt). Downstream modelling and reference distributions use the core sequence so flanking construct sequence does not inflate length. In this corpus the two length measures are nearly identical for most identities.

### Figure 5 — GC content of distinct binding-sequence cores

`fig05_gc_distribution.png`

GC content is shown for distinct binding-sequence cores so a sequence associated with several targets is counted once. These empirical composition statistics will later inform the matched/null reference used when assessing generated sequences.

### Figure 6 — Related-sequence cluster sizes

`fig06_cluster_size.png`

Most leakage-safe groups contain only one distinct sequence, but a small number contain large related families. The two largest groups contain 89 and 19 sequences and both target NGF. Because final balancing and dataset splitting operate on whole clusters, these large families cannot be divided across datasets and therefore constrain the exact effect of a target cap.

### Figure 7 — Experimental evidence in the retained corpus

`fig07_evidence_level.png`

62.6% of the retained corpus has quantitative affinity evidence (E2). Qualitative binding (E3) and selection/enrichment (E4) make up the remainder. E5 database/deposit-only records are parked and are not included in this primary corpus.

### Figure 8 — Primary source after exact deduplication

`fig08_source_contribution.png`

When the same sequence–target relationship appears in several databases, one source supplies the canonical scalar metadata while all contributing-source provenance is retained. These bars therefore show the primary metadata donor after deduplication, not the raw number of records originally downloaded from each database.

### Figure 9 — How the target-cap choice affects retained corpus size

`fig09_candidate_target_cap.png`

The blue line is an idealised calculation in which individual identities could be removed exactly to the target threshold; the red line shows the much more conservative result of removing every cluster that touches an overrepresented target. The real S7 implementation must retain whole leakage-safe clusters, so the final corpus size depends on the cluster-selection rule requested in C3-05. Neither line is the final predicted corpus size. From 3% to 10%, NGF is the only target above threshold, which is why the remove-all-touching-clusters comparison remains flat: it removes the same 14 NGF clusters under each of those candidate caps. At 2%, 5 targets exceed the nominal threshold.

### Figure 10 — Independent source support per aptamer–target identity

`fig10_corroboration.png`

Most identities are reported in only one contributing database; 138 are independently represented in more than one source. Multiple-source corroboration preserves provenance but does not automatically upgrade the experimental evidence level.

## Next steps after decisions

1. Record the five CHECKPOINT-3 choices, including a reproducible whole-cluster rule for C3-05.
2. Apply the approved cap and any approved inclusion/balancing policy without splitting clusters.
3. Verify the post-cap distribution against the approved final denominator.
4. Assign whole clusters to FT, REF, and EVAL using the approved stratification policy; document the known target-family limitation or any approved alternative.
5. Produce the final split corpus and then create the FT train/validation split.

---

# Technical appendix

This appendix preserves audit and reproducibility context. It is not required for the supervisory decisions above.

## A. Scope and data grain

The final corpus was produced by canonical target normalisation, exact scientific deduplication, and leakage-safe clustering.
The main grain is one exact `(sequence_core, canonical_target_name)` relationship: 1,278 curated aptamer–target identities,
1,139 distinct cores, and 792 final clusters. These are distinct from the 1,460 pre-dedup relationship/provenance
observations and 1,429 source records. `scientific_identity_id` is unique at the S5 identity grain; source `record_id` is provenance and is not unique at that grain.

The final cluster construction is frozen 90% corpus-wide MMseqs grouping unioned with trusted ENA positive family must-links.
It must not be read as a statement that every pair in a final cluster is at least 90% identical.
There are 792 scientific representatives, with none missing and none duplicated.
`partition` is blank for all 1,278 identities.

## B. Additional target and cluster diagnostics

Secondary target diagnostics: cluster-occupancy Gini 0.476051; cluster-majority Gini 0.509152;
cluster-majority Shannon 5.112247 nats. Enzyme identities are 78/1,278 (6.10%).
No target has non-empty Pfam or InterPro annotation used for balancing.

Final cluster core-count distribution: 1=634, 2=106, 3=35, 4=5, 5=4, 6=4, 7=1, 9=1, 19=1, 89=1.

Clusters with ENA provenance: 98; clusters created/expanded by ENA union: 6.

## C. Detailed sequence and metadata profile

Full-sequence lengths: n=1278; min 20.0; p05 29.000; p25 40.000; median 51.000; mean 57.685; p75 79.000; p95 93.000; max 123.0.
Core lengths: n=1278; min 20.0; p05 29.000; p25 39.000; median 50.000; mean 55.894; p75 76.000; p95 92.000; max 123.0.
Identity-grain core vs full: 1207/1278 identities have identical lengths (94.4%); median full−core difference 0.0 nt.
The full-sequence two-component diagnostic likewise reports `evidence_of_material_bimodality` (ΔBIC 508.018).

Distinct-core composition: A 0.236405, U 0.232906, C 0.253727, G 0.276962, T 0.000000, other 0.000000.
Identity-weighted GC mean 0.531574; median 0.530685.

GMM source-regime assignment method: Each distinct sequence core is assigned to the two-component length GMM component with the higher posterior probability. Component 0 is the shorter-mean regime. Exact posterior ties are assigned to the shorter regime.

chemistry: (blank)=95, 2F-RNA=69, 2OMe-RNA=2, RNA=1106, mixed=6

Canonical affinity is present for 372/1,278 (29.11%). Measurements are not averaged across observations.

## D. Source and evidence detail

| Primary source | Identities | Contributing identities | Unique identities | Unique cores |
| --- | --- | --- | --- | --- |
| Aptabase | 99 | 107 | 36 | 25 |
| AptaDB | 70 | 76 | 70 | 25 |
| AptaIndex | 62 | 126 | 54 | 25 |
| AptamerBase | 491 | 500 | 485 | 435 |
| ENA | 235 | 235 | 235 | 232 |
| NCBI Nuc | 0 | 0 | 0 | 0 |
| Riboaptamer | 217 | 276 | 215 | 191 |
| UT Austin | 104 | 104 | 45 | 32 |

Unspecified S7 cluster-selection items:

- denominator definition
- floor or ceiling rule
- which whole clusters are retained or removed
- treatment of clusters containing multiple targets
- ordering and tie breaking
- whether removing a cluster for one dominant target may remove identities belonging to other targets

## E. Reproducibility freeze hashes

### S4 freeze

- `reviewed_relationships`: `252987d71839623566ea1fa5ddf0c0c591d23fe39fad858f84d212d7abf5d458`
- `reviewed_dictionary`: `afcd8f02e13feee26bb54cf1caad76508780828d4cee3816ab5c9c1cf0b178d8`
- `record_map`: `701acc7134f010401a49c137e80ff4bc50f31a9645b71cda4ae686426a032d7f`
- `parked_audit`: `d46730de8de9e4f111866f2543269b6d72c56e45bc89e65f92de36481c6aabd2`
- `routing_summary`: `add4655eaf498e3b369f66b12866c6a32e837e28b4d49bc44a1c5245ab939ff6`
- `combined_input`: `6609f1839cbe8ce335f04a9be4fa865b6127514d307c757c77ff71871c558fd0`

### S5A freeze

- `corpus_dedup_csv`: `f92a4858afe354db036b974cf90456de409131a24d257b30c400a00d4a351d86`
- `membership_csv`: `c6a34cb0158dc9492f45683bd18fc8f0355c659ffcc1ec6f2d542bcf6a7b582c`
- `groups_csv`: `2eb63537abb5121bc79dc2a41cb26bbbc935008eb1015103d5a1e9f89ab3d903`
- `dictionary_conflicts_csv`: `5b44c9a59b86be1350d43eaf0ca8812d7130399832ba7c46f7ecceea7fb8be8f`
- `multi_target_csv`: `7c81edf29df24ee06a8218a6ebb8c00dd15a21bb3efbaccf4cd108ca6498963b`
- `overlap_matrix_csv`: `8de8bbb1d1c569e3be5117591033ad1963a649ccabe6e576a9c8b0d0c1e2f348`
- `report_md`: `77d43b1299389cd90f0de076431d8a1adfc9f2ff38ef244d45e82a5d0ab22062`

### Final S5 freeze

- `clusters_final_tsv`: `29aaf4089be3b736a2a81d3aa92af6663cda21ccbf7c1f35a113b9ee1126d677`
- `corpus_clustered_final_csv`: `c6ee6288423d863e55bbfa1b73ccee66f2999e27f3bae04d3b95d200c35e56d6`
- `cluster_summary_final_csv`: `79fa62b0041b6f38bb6b8c87847035078b5bf5186eae8cd2415cf48722b97907`
- `cluster_union_provenance_csv`: `00d558f3525a14125d30d208005c2cb1e91bb82d1a298b8f27ffdebf9b698140`
- `overlap_report_md`: `c00003a7d15eae1aed950373e6b66da16eeb6b96eb0687d413b70d0742e959cc`
- `manifest_json`: `5a81d328dd10d712088b458782a1b89db94e3d75c70c703b7d578c2d06db6ede`

## F. Boundary of this report

- S6 profile complete after this report is generated
- CHECKPOINT-3 prepared, not decided or applied
- no balancing
- no target cap applied
- no rows removed
- no S7
- no FT/REF/EVAL
- no train/validation split
- no S4/S5 science changed
