# M8 generator-EVAL protocol reconciliation

**Date:** 8 October 2026
**Status:** Synthetic preparation only. This package does not authorize M9A, M9C, or EVAL access.
**Editing base:** tracked `docs/aptarank_full_mres_thesis_evaluation_plan.md` on branch `generator-eval-prep`.
**Starting commit:** `daea0002896c2bf210a6491ab104cb521db467d1`

The tracked plan was edited in place. It was not replaced by the uploaded plan. The uploaded plan and the approved handoff govern the scientific reconciliation. Production facts in any generation note were not copied into the plan and were not verified.

## External protocol inputs

| Input | SHA-256 |
|---|---|
| `/home/laura/eval-protocol-inputs/2026-10-08/plan.md` | `913fc470a2a01af5e60f30fad79716210411f7f8d9d2a3067ec6101906e723eb` |
| `/home/laura/eval-protocol-inputs/2026-10-08/handoff.md` | `63d9e7889b1788a1a8a759d0d1c53938f2901b1a1d167ee24b211cbd90ca972e` |

## Decisions incorporated

- Plan version 3.1, dated 8 October 2026, records the approved M8 generator-EVAL addendum while production facts remain pending authoritative manifest verification.
- Generator sequence: M7 guardrails → immutable M8 raw generation → condition-blind post-M8 parsing/accounting → M9A → M9B → M9C → explicit M10 EVAL unlock.
- M7 guardrail samples are excluded from production pools.
- Raw production artifacts stay immutable. Derived tables are separate, reproducibly linked outputs.
- Filtering, deduplication, truncation, padding, top-up, replacement, and replenishment are prohibited.
- Primary generator grain: all valid parsed attempts, including repetitions. Exact duplicates and multiplicities are outcomes.
- Unique-only generator analysis is a labelled sensitivity only.
- AptaRank continues to use valid unique candidates. That rule is unchanged.
- An equal-size subsample is not the primary B1/B2/D1 generator estimand. An expensive metric may use only a prespecified multiplicity-preserving attempt-level subsample.
- B0 may use a format adapter and then the same biological validity parser as B1/B2/D1. B0 stays outside the B1–D1 controlled comparison.
- `record_id` is the canonical attempt identifier. Each derived row retains `source_artifact_sha256`.
- Parser outcomes use a closed vocabulary: `valid_canonical_sequence`, `empty_output`, `unparseable_output`, `non_sequence_output`, and `parsed_non_acgu`. Valid rows have a null failure reason. Empty, unparseable, and non-sequence outputs have a null sequence. A parsed non-ACGU string stays in the restricted ledger and is biologically invalid. Shareable reports expose failure-reason counts, not sequence strings.
- The existing 30,000 D1 figure is a planned budget, not a verified achieved production count.
- Actual D1 allocation and pooling are confirmed from final manifests before M9A.
- If equal production weighting of fitted D1 models is confirmed, the implemented equal mixture covers GC, nucleotide composition, dinucleotide composition, and nearest-reference distance. Raw accounting and global multiplicity remain actual observed counts. Structure, stratified pooled summaries, nearest-train distance, maximum edit similarity, the valid-only exact-hit diagnostic, and exact TRAIN match rate stay unavailable in the pooled D1 result until an equal-mixture rule is defined. Per-seed results for those metrics remain reportable. Without verified pooling provenance, pooled valid-conditional D1 metrics and pooled B1–D1 directional consistency are unavailable. They do not fall back to concatenated D1 rows.
- Generated-sequence clustering is not required generator output. Representation-space analysis is deferred.
- Section 14 records generated clustering, threshold sensitivities, effective-cluster analyses, and representation analysis as future work.
- The Tier 1 clustered bootstrap is unchanged. It handles AptaRank dependence, not generated-sequence clustering.
- B1–D1 remains primary, B2 remains the non-neural null, and B0 remains external.
- No combined generator-quality score is defined. No metric establishes protein binding.
- Production ViennaRNA settings are not fully pinned. That pin, or an explicit scope decision, is a blocking pre-M9C item. This package does not invent temperature, dangle, salt, or other folding settings.
- The code adds a synthetic source manifest, derived provenance emitted after parsing, a synthetic B0 adapter, attempt-level accounting with a closed parser-outcome vocabulary, a sequence-free multiplicity histogram, and an equal-training-seed mixture that runs only from validated synthetic provenance. It does not add a production-file reader. The first parse does not require a derived-ledger hash. An optional expected derived-ledger hash is only a replay check.

## Production facts that remain unverified

No authoritative manifest was opened. The following were not established:

- achieved raw attempt counts for B0, B1, B2, or D1;
- whether M7 samples are absent from the production pools that will actually be analysed;
- D1 training-seed labels, per-seed allocation, and whether equal production weighting was used;
- B1 block count and block allocation;
- checkpoint identities and checkpoint hashes;
- source-artifact identifiers, byte sizes, and SHA-256 values;
- the production B0 file schema;
- production parser or adapter versions;
- pinned ViennaRNA settings.

Candidate expectations in the uploaded note, including any seed labels or round attempt counts, stay outside the plan until those manifests are checked.

## Manifest fields still required

Before parsing, an authoritative source manifest must be able to supply the fields known without a derived ledger:

- source artifact identifier;
- source artifact SHA-256;
- source byte size;
- raw attempt count for each of B0, B1, B2, and D1, when that count is already known;
- explicit confirmation that M7 guardrail samples are excluded from each production pool;
- D1 training-seed identifiers;
- D1 raw-attempt allocation for each fitted training seed;
- the D1 pooling policy, including whether fitted models have equal production weight;
- B1 generation-block structure and block allocation;
- checkpoint identifier and checkpoint SHA-256 for each neural source;
- whether a biological requested length was recorded for each source;
- a production B0 format description sufficient to pin an adapter, if the historical file is not already in the canonical attempt schema;
- production parser/adapter version;
- generation settings required to interpret the attempts;
- an explicit replenishment prohibition.

The source manifest must not require the caller to know the derived-ledger SHA-256 before the first parse. After the condition-blind parser runs, derived provenance records the source identity and hash, the parser/adapter version, the derived row count, the derived-ledger SHA-256, and the no-replenishment statement. A later replay may supply that derived-ledger hash as an optional expected value. A mismatch fails closed.

## D1 aggregation currently implemented

| Aggregation basis | Metrics |
|---|---|
| Actual attempt accounting | Raw attempts, parsed outputs, successfully parsed outputs, valid and invalid outputs, empty or unparseable outputs, exact-length hits and exact-hit rate, per-requested-length exact-hit rate, validity and empty fractions, failure-reason counts, and the actual combined attempt-level validity rate |
| Global condition-level duplicate/multiplicity outcome | Unique valid outputs, duplicates, duplicate excess, largest duplicate multiplicity and share, multiplicity histogram, and unique fraction |
| Equal-training-seed valid-conditional mixture | Pooled GC, nucleotide and dinucleotide total variation to the reference, nearest-reference distance, equal-seed mean validity, nucleotide and dinucleotide total variation to the synthetic TRAIN collection, and pooled B1–D1 directional consistency |
| Per-seed only | Per-seed population summaries, matched B1–D1 block comparisons, and the observed range across training seeds |
| Unavailable pending a defined aggregation | MFE, MFE per nucleotide, paired fraction, exact TRAIN match rate, the valid-only exact-hit diagnostic, nearest-train distance, maximum edit similarity, and pooled full-length stratified results |

Nearest-reference distances use the frozen `inclusive_cumulative_weight_exact_v2` rule. Each observation weight is the exact rational `1 / (n_seeds × valid rows for that seed)`. Quantiles are the first observation whose exact inclusive cumulative weight is at least `1/4`, `1/2`, or `3/4`. The comparison does not use a floating-point tolerance. Nucleotide, GC, and dinucleotide comparisons mix seed-specific frequency distributions with equal seed weight before the comparison. A participating seed with no valid observations makes that conditional metric null. The seed is not dropped and the remaining seeds are not reweighted.

`record_id` remains the only attempt identifier. A second synonymous attempt-ID field is not part of the contract.

## Inspection boundary

No REF, EVAL, VALIDATION, or TRAIN sequence or data file was inspected. No production M8 or historical B0/B2 generation artifact, M7 generation sample, checkpoint, or model result was inspected. The timestamped plan backup was not opened. Synthetic fixtures and the two protocol inputs above were used.

Passing the synthetic checks in this package does not authorize M9A, M9C, or EVAL access.
