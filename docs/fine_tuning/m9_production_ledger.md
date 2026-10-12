# M9 production derived ledger

The production entry point is `scripts/modelling/generator_eval_production_ledger.py`. Its controlling inputs are the frozen source manifest and an output directory.

The parser contract `config/modelling/generator_eval_parser_contract.json` and the source manifest `config/modelling/generator_eval_source_manifest.json` are immutable pre-production freeze artifacts. Their SHA-256 digests are `a8cda86af2cd6aff52ed7929c1a8cdfe134394f9087c768a731e8597339fe872` and `89be54f49b020027d58686ececfc1d743c16e58c0ed12d0b6bae269d36c4aa6c`. The sealed production entry point verifies both exact file-byte digests before it opens any sealed source. A mismatch fails closed. Synthetic `run_ledger` calls may use a synthetic manifest; the source-manifest pin applies to the sealed entry point.

The status fields in those frozen files describe the state when they were frozen. They record that production parsing had not yet been run. Production was subsequently authorised and executed using runner commit `378f574b1620a9ff999082262868bffbe647d063`. The production manifest is the evidence of that execution. The frozen contract files are not rewritten to say so.

After the pins match, the entry point reads only the B0, B1, B2, and D1 artifacts named by that manifest, recomputes each sealed SHA-256 before accepting rows, and applies source adapter `m9-source-adapter-v2` with biological parser `m9-biological-parser-v1`.

Ledger schema `generator-eval-production-ledger-m9-r1` keeps the frozen derived-row fields and adds `ledger_schema`, `is_valid_canonical`, `valid_sequence_multiplicity`, and `is_exact_duplicate_within_condition`. Exact duplicates are counted only among valid canonical sequences within one condition. Every member of a repeated group keeps the same multiplicity and is flagged. Valid singletons are not flagged. Invalid rows keep a false `is_valid_canonical` and null multiplicity and duplicate fields. No row is dropped. Cross-condition overlap was not computed.

`overall.distinct_valid_sequences` is the sum of the per-condition distinct valid-sequence counts. It is not global distinctness. The summary records that fact in `overall.distinct_valid_sequences_are_within_condition_sums`.

Condition order is B0, B1, B2, D1. Within a condition the order is source order. B0 chunks follow the manifest chunk list. The combined ledger is the byte concatenation of the four condition ledgers. JSONL is UTF-8 with an LF after every row. The accounting summary contains counts only. The production manifest records the runner commit, contract and source-manifest digests, expected and recomputed input digests, and the digest of every output except itself. Its own digest is the SHA-256 of those file bytes.

The final output directory itself must not already exist. An existing empty directory is refused, as is a nonempty one. Outputs are written in a temporary directory and, after validation, promoted by one directory rename. A failed validation deletes the temporary directory.
