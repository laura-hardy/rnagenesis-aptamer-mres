# M9A TRAIN leakage and nearest-distance preparation

The public core is `run_train_leakage` in `scripts/modelling/generator_eval_train_leakage_runner.py`. It accepts in-memory combined-ledger bytes, TRAIN CSV bytes, TRAIN text bytes, and explicit expected identities. Miniature synthetic inputs set `enforce_production_identities` false and supply their own digests and counts. That flag does not relax the pinned contract digests, the ledger schema, or the frozen overlap and leakage formulas.

The runner-specific contract is `config/modelling/generator_eval_train_leakage_runner_contract.json`, identity `m9a-train-leakage-runner-v1`. Its SHA-256 is `ef68b1575df4d770af2bdd622eeb84f647a18db9d4cbd115e0b8a60de5dce528`. It records the sealed source-opening order. It does not alter `m9a-overlap-leakage-definitions-v1`.

Before a supplied byte string is parsed, the core requires bytes rather than a decoded object, checks every expected digest is lowercase SHA-256, recomputes each supplied digest, and verifies:

- M9A contract `config/modelling/generator_eval_overlap_leakage_contract.json`, SHA-256 `6aeaa2338776cbe7aceffef63ee4ca7dfd7ed3643aa7d1e400fd54a02d113535`
- governing plan `docs/aptarank_full_mres_thesis_evaluation_plan.md`, SHA-256 `fc6963f01f7d4ab311774865bda15626facdb753ffa0db06b01b338d88162b51`
- frozen data contract `config/modelling/frozen_data_contract.json`, identity `rnagenesis_corrected_669_core_m0`, SHA-256 `396c83c3dbf9afc656ad5c60ec05c94fce3c5a684990c3cc1cebfb2411ccd5ff`
- this runner contract

`corpus_final.txt` is the comparison population because it is the authoritative fitting input. `ft_train.csv` is the identity-grain provenance source: 726 identity rows and 669 distinct `sequence_core` values in production. The runner parses quoted CSV fields, requires the scientific columns, and refuses a repeated scientific identity id. A repeated core across different identity rows is kept. The comparison list is the first-occurrence order of those cores. TRAIN text must be LF-only, trailing-LF terminated, nonempty, canonical, unique, and equal to that order. Cores are not trimmed, uppercased, converted from T to U, or otherwise rewritten. Synthetic mode may supply miniature counts. Production enforcement requires the sealed ledger digest `d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e`, TRAIN CSV digest `84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0`, TRAIN text digest `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d`, ledger totals B0 30,080, B1 30,000, B2 30,000, D1 30,000, and combined 120,080, plus the 726 and 669 TRAIN counts. Synthetic mode cannot claim those production identities and cannot claim production validation.

Exact leakage and nearest distance reuse `scripts/modelling/generator_eval_overlap_leakage.py` without changing its formulas. Membership is full parsed-string equality at row grain and distinct-sequence grain. Invalid attempts stay out of valid denominators. A zero denominator is null except where the frozen D1 seed rule fails closed. B0 stays an external comparator. D1 reports seeds 43 and 44, the unweighted mean of the seed rates, the observed range, and a separately labelled actual-attempt pooled rate. The historical 0.01 guardrail is not a decision threshold.

Nearest distance is global Levenshtein distance divided by the longer length. The runner calculates one scalar per globally distinct generated sequence and the frozen summary projects it to rows, conditions, and seeds. That cache does not replace `nearest_train_distance_summaries`. Row quantiles keep `int(round(p * (n - 1)))`. Equal-mixture D1 quantiles keep `inclusive_cumulative_weight_exact_v2`. Edit similarity is not sequence identity.

A future production directory must not already exist, including an empty directory. The intended directory is `results/fine_tuning/m9_generator_evaluation/m9a_train_leakage`. It receives only:

- `m9_exact_train_leakage_summary.json`
- `m9_nearest_train_distance_summary.json`
- `m9_train_leakage_manifest.json`

Those documents emit no sequence, sequence hash, attempt identifier, nearest-neighbour identity, TRAIN identity-row id, or target label. Files are written in a temporary sibling directory, reread, and promoted by one rename. A failed validation deletes the temporary directory. This implementation does not create that results directory.

The sealed entry point `run_sealed_train_leakage` remains unexecuted. Its combined-ledger locator is `results/fine_tuning/m9_generator_evaluation/m9_all_conditions_derived_attempt_ledger.jsonl`. Its development locators are `/home/laura/rnagenesis-mres-data/development/ft_train.csv` and `/home/laura/rnagenesis-mres-data/development/corpus_final.txt`. Before any sealed source is opened, it validates the invocation and the production identity bundle, validates the root and output paths, refuses an existing output destination (including an empty directory or a symlink), verifies the pinned M9A contract, governing plan, frozen data contract, and runner contract, and verifies that the runner commit is available. It then opens the combined ledger and verifies its production digest before opening either TRAIN file, opens the TRAIN CSV and verifies its production digest before opening TRAIN text, opens TRAIN text and verifies its production digest, and only then enters parsing and metric computation. The in-memory core repeats the digest, schema, count, provenance, and output-destination checks. No source is parsed before its digest matches. It opens TRAIN only. It does not open VALIDATION, REF, or EVAL. It enforces the production identities above. No test and no command in this implementation calls it. Running this module as a program exits without opening those files.

A synthetic run is not production validation and does not complete M9A.
