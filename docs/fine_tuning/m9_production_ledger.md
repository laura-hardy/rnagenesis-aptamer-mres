# M9 production derived ledger

The production entry point is `scripts/modelling/generator_eval_production_ledger.py`. Its controlling inputs are the frozen source manifest and an output directory. It reads only the B0, B1, B2, and D1 artifacts named by that manifest, recomputes each sealed SHA-256 before accepting rows, and applies source adapter `m9-source-adapter-v2` with biological parser `m9-biological-parser-v1`.

Ledger schema `generator-eval-production-ledger-m9-r1` keeps the frozen derived-row fields and adds `ledger_schema`, `is_valid_canonical`, `valid_sequence_multiplicity`, and `is_exact_duplicate_within_condition`. Exact duplicates are counted only among valid canonical sequences within one condition. Every member of a repeated group keeps the same multiplicity and is flagged. Valid singletons are not flagged. Invalid rows keep a false `is_valid_canonical` and null multiplicity and duplicate fields. No row is dropped. Cross-condition overlap is not computed.

Condition order is B0, B1, B2, D1. Within a condition the order is source order. B0 chunks follow the manifest chunk list. The combined ledger is the byte concatenation of the four condition ledgers. JSONL is UTF-8 with an LF after every row. The accounting summary contains counts only. The production manifest records the runner commit, contract and source-manifest digests, expected and recomputed input digests, and the digest of every output except itself. Its own digest is the SHA-256 of those file bytes.

Outputs are written in a temporary directory and promoted only after validation. An existing output file is refused. A failed validation deletes the temporary directory.
