# M9A exact cross-condition overlap runner

The public core is `run_cross_condition_overlap` in `scripts/modelling/generator_eval_overlap_runner.py`. It accepts in-memory combined-ledger bytes and expected identities. Miniature synthetic ledgers set `enforce_production_counts` false and supply their own row counts. That flag does not relax the frozen contract digest, governing-plan digest, ledger schema, or overlap definitions.

Before a row is accepted, the core verifies:

- contract `config/modelling/generator_eval_overlap_leakage_contract.json`, identity `m9a-overlap-leakage-definitions-v1`, SHA-256 `6aeaa2338776cbe7aceffef63ee4ca7dfd7ed3643aa7d1e400fd54a02d113535`
- governing plan `docs/aptarank_full_mres_thesis_evaluation_plan.md`, SHA-256 `fc6963f01f7d4ab311774865bda15626facdb753ffa0db06b01b338d88162b51`
- the supplied combined-ledger byte digest
- UTF-8 JSONL with one object per row
- production ledger schema `generator-eval-production-ledger-m9-r1`
- parser `m9-biological-parser-v1` and adapter `m9-source-adapter-v2`
- source order B0, then B1, then B2, then D1, and the expected per-condition and combined row counts
- canonical parsed sequences on valid rows, frozen invalid-row sequence and duplicate-field semantics, and within-condition multiplicity and duplicate flags recomputed from the rows
- stable attempt identities unique within each condition

Any mismatch fails the run. Rows are not repaired, reordered, deduplicated, replenished, or rewritten. Overlap counts come from the frozen pure implementation in `scripts/modelling/generator_eval_overlap_leakage.py`.

The sealed entry point `run_sealed_cross_condition_overlap` always enforces the production totals B0 30,080, B1 30,000, B2 30,000, D1 30,000, and combined 120,080. Its combined-ledger locator is `results/fine_tuning/m9_generator_evaluation/m9_all_conditions_derived_attempt_ledger.jsonl`, SHA-256 `d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e`. This implementation does not call that entry point.

A future production directory must not already exist, including an empty directory. The intended directory is `results/fine_tuning/m9_generator_evaluation/m9a_exact_cross_condition_overlap`. It receives only:

- `m9_cross_condition_overlap_summary.json`
- `m9_cross_condition_overlap_manifest.json`

The summary reports the six unordered pairs in both directions, distinct shared counts, coverages, unions, Jaccard values, the global union, exactly-n condition counts, observed membership patterns, and reconciliation totals. B0 is labelled `external_comparator` and is not pooled. The summary states that TRAIN, VALIDATION, REF, and EVAL were not accessed. It emits no sequence, sequence hash, attempt identity, or overlap-member list.

The manifest records the runner commit, frozen contract identity and digest, governing-plan digest, expected and recomputed combined-ledger digest, input and output byte counts, row counts, SHA-256 values, metric grain and denominator rules, deterministic serialization, and access-boundary flags. Its own digest is not embedded. Files are written in a temporary directory and promoted by one rename after validation. A failed validation deletes the temporary directory.

A synthetic run is not production validation and does not complete M9A.
