# Section 6 method freeze

| Item | Value |
|---|---|
| Status | `SECTION6_METHOD_FROZEN_SYNTHETIC_ONLY_PRODUCTION_UNAUTHORIZED` |
| Stage | Synthetic fixtures only. Manual AptaRank production remains unauthorized. |
| Plan | `docs/aptarank_full_mres_thesis_evaluation_plan_v3_5.md`, version 3.5, section 6, SHA-256 `ebb0e66dd35c7ed20abecacf710ea7a90dd0e2737ba1973af66e8f0753e22c9d` |
| Contract | `config/modelling/aptarank_section6_method_contract.json`, SHA-256 `50652795985ddec6d93925715c7a6a50462a215ed830c54ccd7faf9a7c84e555` |
| Scorer | The deployed AptaRank UI. This package does not recompute the five components, the composite, the shuffles, or shuffle p-values. |

No detail below is a scientific result. The package does not open TRAIN, VALIDATION, REF, or EVAL sequence data, does not recover the attempt-3 reference file, does not create a production secret or upload, does not write under `results/`, and does not inspect the protected M10 evidence.

## Historical draft left in place

ARP-2B remains the historical synthetic draft. Its specification SHA-256 is `5065112af2de0668f3ed240242dacbdd73ccadfccc15d288769353bafadda03e` and its module SHA-256 is `127d20a1e14d8f72dca1913a596be0a812cba1be25c310d5ca7c1c86c32a7f6c`. Section 6 does not edit that draft and does not treat its blocked register as production-ready. The conventions below close the former U22–U26 and U29–U38 decisions in this new contract only.

## Reused validators

ARP-1 still parses candidate uploads and target-free exports. Its current behavior is applicable and unchanged.

| Role | Path | SHA-256 |
|---|---|---|
| ARP-1 specification | `config/modelling/aptarank_io_spec.json` | `46ba6c8be873dad4c086e9f6b889b51702ba31212fa502d00f26e267a22da732` |
| ARP-1 module | `scripts/modelling/aptarank_io_preflight.py` | `eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01` |

Candidate columns remain `id,sequence`. The target-free profile still accepts only compatibility `not evaluated` and shuffle `pass` or `fail`. M9B-3 is not reused for this gate because its public token set also accepts `strong`, `moderate`, `weak`, and U+2014.

The uniform-stream length prefix is the same four-byte big-endian UTF-8 layout as M9B-2. Section 6 does not import the M9B-2 preparer, because that preparer blinds a different domain.

## M9C deployment facts

These facts are cited from the 13 October 2026 deployment record. This package does not re-operate AptaRank.

Resolved and used by the Section 6 run sheet:

- Deployment identity: AptaRank 0.1.0, schema 1.0.0, git `49a85609e352`.
- Dependencies: ViennaRNA 2.7.2, forgi 2.2.3, fpocket 4.0.
- Attempt 3 reference upload SHA-256 `5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6`, with 113 accepted and 0 dropped.
- Standard preset: seed 42, 20 candidate shuffles, 100 ensemble samples.
- The recorded composite method name is `corpus_weighted_mean`. The scoring signature `6dec9dc463a8fde1` is not a control-bank hash. The composite is not recomputed here.

Recorded as provenance only, and unused by Section 6 Tier 1: the REF-derived compatibility bank has realized count 5,085 and is distinct from those 20 shuffles. The Tier 2 band thresholds are moderate at least 0.75 and strong at least 0.95. Section 6 Tier 1 is target-free and does not apply that bank or those bands.

Still unresolved, and not filled in by this package:

- The ushuffle version remains unknown.
- No explicit bank identifier or content hash was exposed.
- The quick-preset discrepancy, paper 30 versus fast-mode 0, remains unresolved. Section 6 does not use the quick preset.
- Local recomputation of the calibration, components, composite, shuffles, and p-values remains refused.
- The recorded development run used a protein target. The target-free token `not evaluated` is the Section 6 expectation, not an observed target-free export. A different token fails closed and requires reviewed rerun lineage.

## Uniform controls

One exact-length i.i.d. A/C/G/U control is drawn for each parent. The master seed is 42. The stream is SHA-256 over a length-delimited preimage: domain `aptarank-section6-uniform-v1`, seed `42`, the parent `sequence_core_sha256`, the attempt index, and the block counter. Integers are canonical decimal text. Digest bytes below 252 map with `byte % 4` in order A, C, G, U. Bytes 252–255 are discarded, so the four nucleotides stay equiprobable. Attempts run from 0 through 9999. The caller-supplied known-core inventory must contain every input parent source digest before any control is drawn. A missing parent digest fails closed. The first draw whose digest is outside that inventory and outside controls already accepted is kept. Attempt 10000 fails closed and returns no sequence.

Parents are processed in ascending core-digest order, so input order does not change the accepted controls. Later production is expected to build the inventory from the corrected unique cores in TRAIN, VALIDATION, REF, and EVAL. This package does not build that inventory and does not emit sequences or overlap results. A uniform control remains a synthetic floor.

## Blinding and the private key

The caller supplies one 32-byte secret. No production secret is embedded in code, configuration, manifests, tests, or Git. The candidate id is HMAC-SHA-256 under domain `aptarank-section6-id-v1`, truncated to 16 bytes, and written as `cand_` plus 32 lowercase hex characters. A truncated collision fails closed. Upload order is a domain-separated ordering HMAC under that same secret and domain `aptarank-section6-order-v1`. The implementation does not accept a second ordering key. An ordering collision fails closed.

The upload header is exactly `id,sequence`. Class, pair, cluster, and target fields stay out of the upload. The restricted private key carries the Section 6 package, schema, and `restricted` marker. Each row keeps the candidate id, class, pair, parent-core identifier, cluster, length, and the SHA-256 of that row's sequence. Class is `eval_core` or `paired_uniform_shuffle`. Candidate ids match `cand_` plus 32 lowercase hex characters. Source digests are lowercase SHA-256. Candidate ids and source digests are unique. Each pair contains exactly one `eval_core` and one `paired_uniform_shuffle`, and those two rows share `parent_core_id`, `cluster_id`, and `length`. The key does not keep the sequence or the secret. The candidate id is the join key.

## Production gates

The count gate is exercised only on synthetic fixtures. It requires 154 real memberships, 154 controls, 154 complete pairs, 308 globally unique upload sequences, and 79 pre-rejection clusters. Passing that gate does not instantiate a production upload and does not authorize AptaRank.

The target-free run sheet is frozen to the attempt-3 reference digest, publication attempt 3, the Standard preset, seed 42, 20 candidate shuffles, 100 ensemble samples, no protein target, and compatibility token `not evaluated`. Any schema or token discrepancy fails closed and requires reviewed rerun lineage.

Every summary records the SHA-256 and byte count of the exact candidate-upload bytes and the exact downloaded-export bytes being analyzed. Those two records remain present when the optional raw-artifact list is empty. Optional run artifacts stay separate: an available artifact is hashed, and an unavailable role is recorded and is not replaced.

No deployed AptaRank component-artifact schema has been observed or frozen. A JSON document is not verified because it declares the scorer `deployed AptaRank UI` and the role `aptarank_five_component_export`. That synthetic document is unverified. Duplicate candidate ids, candidate ids that do not reconcile with the analyzed export and private key, incomplete rows, and merely self-declared rows do not receive `populated_from_verified_artifact`. The production five-component table remains unavailable. The names normalized MFE, ensemble defect, positional entropy, stem fraction, and GC fraction are the v3.5 Tier 1 checklist names. They are not an observed artifact schema. This package does not invent a production schema and does not recompute component values.

If the deployed UI later exposes components, the acceptance gate is, in order: capture and hash the untouched artifact, review and freeze its real schema, enforce unique candidate ids and reconciliation against the analyzed export and private key, then compute a compact class-level descriptive table from the exported component values. Summarizing exported values is allowed. Recomputing component values is not.

## Statistics

Higher aptamer-likeness is favourable. An exported score is accepted only when it is a finite decimal on the closed interval [0, 1], including both endpoints. A value below 0 or above 1 fails closed. Export rank is read from the rank values, not from physical CSV order. A complete export uses ranks exactly 1 through N. When technical failures leave retained gaps, increasing rank must correspond to non-increasing score, and equal scores must have ascending candidate ids.

Quantiles are Hyndman–Fan type 7. Each class reports its mean, median, Q1, Q3, and IQR. The primary paired effect is the median of the eval-core minus paired-uniform-shuffle differences. The mean paired difference is descriptive. AUROC uses the members of complete pairs, treats the `eval_core` membership as the positive class, and gives a tied comparison credit 0.5. A result below 0.5 is preserved.

Shuffle-pass rates use rows with an exported `pass` or `fail`. The paired pass-rate difference uses pairs in which both members have a valid value, `eval_core` minus `paired_uniform_shuffle`. The secondary test is a two-sided Wilcoxon signed-rank test. Zeros are discarded. Tied absolute differences take average ranks. The p-value is the normal approximation without a continuity correction. Its variance is `n(n+1)(2n+1)/24 - sum(t^3-t)/48`, which equals the sum of the squared average ranks divided by 4. The reported statistic is the sum of the ranks on strictly positive differences. When every difference is zero, the statistic is 0, the p-value is 1, and the disposition is `all_zero_differences`.

The cluster bootstrap draws 10,000 replicates from seed 42 on domain `aptarank-section6-bootstrap-v1`. It resamples the observed unique cluster ids with replacement, draws as many clusters as were observed, and includes every eligible complete pair in a selected cluster once for each time that cluster is drawn. The 95% interval uses type-7 quantiles at 0.025 and 0.975. An undefined replicate is counted and excluded. It is never imputed. A paired, AUROC, or bootstrap result requires at least two complete pairs from at least two clusters. An interval also requires at least 9,500 defined replicates. Otherwise the missing value is null and the reason is technical incompleteness. Input, evaluable, complete-pair, cluster, shuffle, failure, and undefined-replicate denominators are retained.

## Modules

| Path | SHA-256 |
|---|---|
| `scripts/modelling/aptarank_section6_uniform.py` | `02b158fc372ca2c50d80f44fe7afce1c85a5f3ae035afb42e181863bece02ee2` |
| `scripts/modelling/aptarank_section6_blinding.py` | `be644bfa62d37cc93a5a4b0714fcbd351e71e7fd5775b6bd254030e757b524ff` |
| `scripts/modelling/aptarank_section6_analysis.py` | `f4051c232d1a5be0c12fc959006957c439973e67baf32e4e3fdd31544f0ae3bf` |
| `tests/modelling/test_aptarank_section6_method.py` | `cabf6e33e4e6dbe4a6963359319fc7569c2aa52f8a31fb554b103d6011e06216` |

The no-argument command checks the pins and prints the status. Any argument is refused. There is no production runner.
