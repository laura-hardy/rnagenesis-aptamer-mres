# Global S7A — 3% whole-cluster target-cap application

S7A implements the CHECKPOINT-3 C3-01 / C3-05 target cap.

```text
S7A preview approved              = 2026-09-21
S7A authoritative cap applied     = this milestone
S7A validation complete           = this milestone
S7B not started                   = STOP
FT/REF/EVAL not assigned          = STOP
```

```text
frozen final S5 corpus
  corpus_clustered_final.csv
        ->
same deterministic whole-cluster selection (pure function)
        ->
authoritative post-cap/pre-partition corpus under
  data/interim/s7a_target_cap/corpus_post_cap.csv
        ->
STOP. No corpus_final. No partition. No FT/REF/EVAL. No S7B.
```

## Authority

1. `docs/data_curation/checkpoint3_supervisor_decisions_2026-09-21.md`
2. Frozen accepted S5/S6 scientific state
3. Governing plan v1.5 and `config/curation_config.yaml`
4. `config/global_s7a_target_cap.json`
5. Human approval of the reviewed dry-run:
   `config/checkpoint_reviews/s7a_target_cap_approval.json`

The approval artefact is an audit / post-derivation parity record only.
Cluster selection does **not** read it.

## Active configuration

```text
MAX_TARGET_FRACTION = 0.03
training_sequence_column = sequence_core
cap unit = final cluster
cap denominator = current / post-removal identity count
```

A target is overrepresented only if `count(t) / N > 0.03`. Equality to
exactly 0.03 passes. `N` is the currently retained scientific-identity
count and is recomputed after every cluster removal.

## Selection semantics

The same pure function (`select_target_cap`) is used for the approved
preview and for this scientific application.

1. Never split a cluster. Removing a cluster removes every retained
   scientific identity in that `cluster_id`.
2. For the single overrepresented target `t`, consider **target-pure**
   clusters first. Rank by trigger-target identity count descending,
   then stable `cluster_id` ascending.
3. Use mixed-target clusters only if no remaining target-pure cluster
   exists for `t`. Rank by least collateral identities, then stable
   `cluster_id`.
4. Remove one cluster. Recompute every target share against the new
   denominator. Repeat until no target exceeds 3%.
5. If more than one target is simultaneously overrepresented at a
   decision step, fail closed. CHECKPOINT-3 does not authorise an
   ordering rule among them.

S7A does not promote E5, does not promote non-protein records, and
does not populate `partition`. Cluster IDs are not renumbered.

## Preview versus application

The reviewed preview remains frozen under:

- `data/interim/s7a_target_cap_preview/`

Application writes a distinct authoritative tree:

- `data/interim/s7a_target_cap/corpus_post_cap.csv`
- `data/interim/s7a_target_cap/s7a_target_cap_removal_trace.csv`
- `data/interim/s7a_target_cap/s7a_removed_clusters.csv`
- `data/interim/s7a_target_cap/s7a_post_cap_target_distribution.csv`
- `data/interim/s7a_target_cap/s7a_target_cap_report.md`
- `data/interim/s7a_target_cap/s7a_target_cap_manifest.json`

`corpus_post_cap.csv` is the authoritative scientific output of S7A.
It is not `corpus_final.csv` and not a training file. It remains
pre-partition under ignored `data/`.

The reviewed preview is not overwritten.

## Command

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/data_preparation/s7_target_cap.py \
  --config config/global_s7a_target_cap.json
```

Mode is `apply`. Preview artefacts are read for parity only.
