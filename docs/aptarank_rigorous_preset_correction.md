# AptaRank rigorous production-preset correction

Date: 20 October 2026  
Status: `RIGOROUS_PRESET_CORRECTION_FROZEN; SECTION6_RIGOROUS_RESULT_COMMITTED_AND_CLOSED`

## Decision

All thesis AptaRank production runs in Sections 6, 8, 9 and 10 use the deployed UI's named **Evaluation** preset, which is the paper's rigorous mode. Before starting each run, verify that the UI displays seed 42, 99 candidate dinucleotide-preserving shuffles and 200 sampled structures. Stop if the named preset displays different effective settings; do not manually approximate it.

The earlier use of Standard came from the verified M9C development-validation configuration. That verified deployment state did not establish Standard as the intended final thesis preset, and it was carried forward too broadly.

The active corrective plan is `docs/aptarank_full_mres_thesis_evaluation_plan_v3_7.md`, SHA-256 `24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9`. v3.6 and earlier plans remain unchanged historical records.

## Section 6 reopening

The reviewed Standard result remains immutable historical evidence. It is not deleted, relabelled, pooled with the rerun or selected according to outcome. It is superseded for the final thesis result solely because it did not use the required rigorous preset.

The Section 6 rerun changes only the preset. It reuses:

- the exact 308-row candidate upload, SHA-256 `5554f68fd94d1754ff9bcc87fba81be7dc8391af7e45703400796f4a5a336ad2`;
- the exact 113-row attempt-3 REF upload, SHA-256 `5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6`;
- the same opaque identifiers, restricted private key, EVAL/control pairs, clusters, exclusion policy, estimands and analysis module;
- no protein target.

The run package is `data/aptarank_eval/sequence/section6_eval_tier1_evaluation_preset_v4/`. Its `SHA256SUMS` SHA-256 is `678a7096fe6df562f9239a40c503539bd1411fb88885f5a57d181bc82a9e28cb`. The run-sheet SHA-256 is `0dbe9ab773d68537605990d50df1cc50e4f5c8080118b3d6e25d5f683603db0f`. It was prepared and checksum-validated before execution. The subsequent rigorous result passed independent review and was explicitly committed and closed on 20 October 2026. Its closure-record SHA-256 is `ff0cfe59842c4ed63fb8619cf3957b16a29d710246dd19321e7dc1e0af281438`.

## Remaining run packages

The prospectively corrected Section 8 packages are:

- GRK2 pocket case: `data/aptarank_eval/sequence/section8_grk2_tier2_evaluation_preset_v2/`; unchanged candidate upload SHA-256 `e7589866fb3322eb3d9ea90a8276d613720ff9d64e59bfed6f7cb47433b9572f`; package `SHA256SUMS` SHA-256 `f73eab1cc7f3408b8f78caedd959b76455158ef5d2d39a88564797cbabda6682`.
- Lysozyme surface case: `data/aptarank_eval/sequence/section8_lysozyme_tier2_evaluation_preset_v2/`; unchanged candidate upload SHA-256 `ade52448da9a6b8630f082df446745f28c649031df460c7b8eb13c4c9b47ab9d`; package `SHA256SUMS` SHA-256 `78c3e8b8ee4eaae5acec9b165108de99544cf6f3345d5e05fb81ca2146291329`.

The v1 Standard run sheets remain historical preparation artifacts and must not be used for thesis production. Sections 9 and 10 must likewise be prepared with Evaluation/99/200 before their manual runs. The Standard-run scoring signature must not be reused; capture the signature emitted by the first rigorous run.

## Boundary and checks

This correction was made before any Section 8, 9 or 10 score was observed. It does not change candidate membership, controls, targets, binding modes, target sites, metrics, thresholds or downstream selection rules. It does not reopen M10. The known `publication_eligible: false` interface marker remains ignored under the already-recorded thesis-wide decision.

All three corrected package checksum manifests passed. The Section 6 upload is byte-identical to its reviewed predecessor. The focused AptaRank preparation, method, I/O, export-validation and manual-run suite passed 65 tests. No AptaRank production run occurred during this correction.
