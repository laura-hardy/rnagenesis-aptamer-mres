# M9B-4 synthetic manual-run provenance

| Item | Value |
|---|---|
| Status | `DEFINED_SYNTHETIC_ONLY_MANUAL_RUN_UNRESOLVED` |
| Stage | M9B-4, caller-supplied objects or bytes and synthetic fixtures only |
| Contract | `config/modelling/aptarank_manual_run_contract.json`, SHA-256 `f1ed83b155c787c51e3d23198db1e5bc4a72c28e0c2a0adc5675b294c0f93125` |
| Plan | `docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md`, version 3.3, SHA-256 `b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe` |
| Preparation contract | `config/modelling/aptarank_candidate_preparation_contract.json`, SHA-256 `3bcfbdf14cd7e777a0b2746f91d0335ba4876195f5012610157e5aa23e083096` |
| Live deployment | Unresolved until M9C. Deployment identity, the effective preset, and live export behaviour are recorded as unresolved. |

M9B-4 checks two records. A target-configuration record states a choice that was completed independently before this package. A manual-run record states a prepared or completed AptaRank UI run. Inputs are an object or UTF-8 JSON bytes supplied by the caller. A filesystem path is refused. No detail below is a scientific result, a deployment verification, or an AptaRank score.

## Reused pins

Hash syntax and path refusal are the existing parser helpers. Canonical JSON bytes are the corrected M9B-2 serializer. The binding check reads the preparation-manifest pin and the two hash fields already written by that package. It does not sample candidates, assign identifiers, or validate an export.

| Role | Path | SHA-256 |
|---|---|---|
| M9B-2 preparation module | `scripts/modelling/aptarank_candidate_preparation.py` | `a4f5b047f2803e775d9521c226287487412495055446e192681957c3d42879ca` |
| Record parser | `scripts/modelling/generator_eval_parser.py` | `4a59ff8e557ee1948410c7f705a9c3772fe2570d4255b0d2185acee99137eaa2` |

## Target configuration

The record schema is `m9b-target-configuration-v1`. The key set is exact. `selection_status` must be `completed_independently_before_m9b`. The site is either a nonempty residue list or a frozen site rule, not both. A residue token is a positive decimal without a leading zero and an optional single uppercase insertion code. Duplicates fail closed. SHA-256 fields are lowercase hex digests. Notes may be null. Empty required strings, unknown fields, and filesystem paths fail closed.

The checker does not open the structure file or the target-selection record. It does not decide whether the biological choice is good.

## Manual run

The record schema is `m9b-manual-run-v1`. `prepared` carries the identity, operator, five SHA-256 fields, expected candidate count, caller-supplied deployment identifier, caller-supplied requested preset, unresolved effective settings, warnings, and optional rerun lineage. `completed` adds start and completion timestamps, exported, missing, rejected, and failed counts, the raw export digest, and a run-artefact digest or null when that artefact was not captured.

The four completed counts must sum to the expected candidate count. The checker does not add a reason for a missing or failed row. A parent run id requires a nonempty rerun reason. A first run must not have one.

`effective_preset` stays null and `live_export_behavior` stays `unresolved`. The deployment identifier and requested preset are stored as the caller recorded them. They are not looked up and they are not checked against a live AptaRank deployment.

## Binding

`bind_existing_artifacts` accepts only bytes. It checks that the candidate-upload digest and the private-membership-key digest equal the fields in the supplied M9B-2 preparation manifest, that the manifest pins the corrected M9B-2 contract, that the manual-run record contains those same three digests, and that the target-record bytes match `target_configuration_sha256`. Upload bytes and private-key bytes are hashed and are not parsed.

## Boundary

This stage did not open TRAIN, VALIDATION, REF, EVAL, a production sequence ledger, a production upload, a real AptaRank download, the completed target-selection directory, or `results/`. It did not call the AptaRank UI or API, modify or reproduce AptaRank, or select a target. It did not calculate overlap, leakage, a biological summary, or a Tier 1 or Tier 2 score. The no-argument command only checks pins and prints the status.
