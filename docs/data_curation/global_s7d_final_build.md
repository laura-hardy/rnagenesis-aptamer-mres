# Global S7D — final corpus assembly, diagnostics, reporting, and validation

```text
S7A frozen                               = yes
S7B frozen                               = yes
S7C frozen                               = yes
S7D final build complete                 = this milestone
TRAIN frozen                             = yes (unchanged)
VALIDATION frozen                        = yes (unchanged)
REF frozen                               = yes (unchanged)
EVAL frozen                              = yes (unchanged)
corpus_final built                       = yes
corpus_final.txt built from TRAIN only   = yes
E5 promoted                              = no
non-protein promoted                     = no
model fine-tuning started                = no
REF calibration started                  = no
EVAL evaluation started                  = no
```

```text
frozen S7A post-cap + frozen S7B partitions + frozen S7C TRAIN/VALIDATION
        ->
byte-copy / concatenate / hash / report only
        ->
authoritative ignored outputs under data/processed/
        ->
STOP for Laura/ChatGPT review.
No split revision. No fine-tuning. No AptaRank. No EVAL scoring.
```

S7D is **assembly, diagnostic, reporting and validation**. It does not
choose identities, change the 3% cap, change cluster membership,
reassign FT/REF/EVAL, reassign TRAIN/VALIDATION, promote E5, or promote
non-protein records.

## Authority

1. `docs/data_curation/rna_aptamer_corpus_curation_plan.md` v1.5
2. `docs/data_curation/checkpoint3_supervisor_decisions_2026-09-21.md`
3. Frozen S7A / S7B / S7C contracts and freeze records
4. `config/global_s7d_final_build.json`

Repository baseline for this build:

```text
branch = main
HEAD = origin/main = c1081c14cb3f20869affeddea49f5dd740b0bc51
git ls-files data = empty
```

## Frozen inputs (reverified, not regenerated)

| authority | path | SHA256 |
| --- | --- | --- |
| S7A post-cap | `data/interim/s7a_target_cap/corpus_post_cap.csv` | `6bbf040af6f1c541001a6a6ee4c461539f554737158ff11598aa93e4f137f9cd` |
| S7B partitioned | `data/interim/s7b_partition/corpus_partitioned.csv` | `755e6afaf6a522be390073d3651311f8afc0ca9486322ac3bbfe348cd2a3fb1a` |
| S7B FT | `data/interim/s7b_partition/ft.csv` | `b680ace037be73f650e386a34d97db915e4925a2dcd59e3053b7542b6d6fb4ff` |
| S7B REF | `data/interim/s7b_partition/ref.csv` | `6c8bf5cdec625bdddb9f42b18a15f435826bebabb119dfc268ff737c89b7408d` |
| S7B EVAL | `data/interim/s7b_partition/eval.csv` | `88fe1d8c2c78ed9dc478306c7390cff7016cd49541cfb1019d48ba8c1272c89d` |
| S7C TRAIN | `data/interim/s7c_ft_split/ft_train.csv` | `941fe8783ee8c99a2ce7598dea00ed123e62750026b7f157f28e7bbcc5d14a8f` |
| S7C VALIDATION | `data/interim/s7c_ft_split/ft_validation.csv` | `03be477e12f7b9ca20f8911e2ac88fde2949af2b6131c2d2aa43eef2ae6d9abc` |

REF / EVAL / TRAIN / VALIDATION semantic freeze hashes are those recorded
in `config/checkpoint_reviews/s7b_partition_freeze.json` and
`config/checkpoint_reviews/s7c_ft_split_freeze.json`. Any mismatch is a
hard stop.

## Final primary corpus

`data/processed/corpus_final.csv` is an exact byte copy of frozen
`corpus_partitioned.csv`. TRAIN/VALIDATION is **not** written into
`partition`; that remains a subordinate FT split.

Expected:

```text
identities = 1173
cores      = 1036
clusters   = 794
targets    = 411
FT / REF / EVAL identities = 895 / 114 / 164
max target share = HIV-1 Rev protein 34 / 1173 = 0.0289855072
E5 = 0
non-protein = 0
```

## `corpus_final.txt`

Source = **frozen FT TRAIN only**. Distinct `sequence_core` values in
first-occurrence order in `ft_train.csv`. No re-normalisation and no
near-duplicate filter.

```text
expected lines = 678
duplicate lines = 0
VALIDATION/REF/EVAL contamination = 0
```

The governing plan v1.5 originally described this file as the FT
partition. The S7C freeze made TRAIN the RNAGenesis fitting set; S7D
implements that TRAIN-only rule as a documentation-only clarification,
not a scientific revision.

## Final modelling roles

| role | use | file |
| --- | --- | --- |
| TRAIN | RNAGenesis fitting | `ft_train.csv` + `corpus_final.txt` |
| VALIDATION | training / model-development decisions | `ft_validation.csv` |
| REF | AptaRank / reference calibration (not started) | `ref.csv` |
| EVAL | final held-out evaluation (not started) | `eval.csv` |

`evaluation_references.csv` is **not** the generic EVAL partition. It is
the target-specific NDM-1 / KPC-2 / carbapenemase positive/control
reference lane used for biological grounding and leakage exclusion.

## Parked lanes

Parked records are concatenated from earlier authoritative artefacts.
S7D does not reclassify molecule type, target type, or evidence.

- `parked_ssdna.csv` — CHECKPOINT-1 applied parked-ssDNA files, plus
  UTexas S3 parks restricted to recorded `molecule_type == ssDNA`.
  Aptabase ssDNA-like S3 parks were rejected at CHECKPOINT-1 and are
  not a parked-ssDNA source. ENA/NCBI parks are construct/unresolved,
  not ssDNA.
- `parked_non_protein_targets.csv` — frozen global-S4 `park_non_protein`
  plus AptaDB S3 parked non-protein.
- `parked_evidence_e5.csv` — frozen global-S4 `park_evidence_e5`.

These three files are the principal reusable park classes defined by
the governing corpus plan. Additional source-specific unresolved parks
exist (chemistry review, molecule unresolved, construct unresolved,
S4 hold / relationship-park / target-park). They are deliberately not
coerced into ssDNA, non-protein, or E5. They remain preserved in frozen
source/checkpoint artefacts. Sequence-safe `parked_inventory.csv`
indexes every parked lane, including residual source-level parks, and
labels grain so source-record, relationship, and scientific-identity
counts are not summed as if they were equivalent.

E5 remains excluded from every primary and modelling file.

## Dataset A replication file

`corpus_replication_datasetA.csv` is a separate
replication/comparability artefact. It is not part of the primary RNA
TRAIN/VALIDATION/REF/EVAL corpus, does not contribute to
`corpus_final.txt`, and its source lane remained outside S4/S5 primary
scientific identities. Its authoritative source is parked AptaDiff A,
written in the CHECKPOINT-1 applied canonical schema. Dataset A never
entered S4/S5, so this file cannot use the primary
`scientific_identity_id` schema without reopening earlier decisions.

## E5 inclusion-impact diagnostic

CHECKPOINT-3 C3-03 requires an informational diagnostic only.

Outputs live under ignored
`data/processed/diagnostics/e5_inclusion/`.

The diagnostic reports relationship/record/identity/core/target
counts, exact overlap with the frozen pre-cap and post-cap corpora,
and a **diagnostic-only** cluster-grain approximation:

- exact `sequence_core` attachment onto frozen S5 clusters
- remaining E5 cores attached at the approved 90% global-edit identity
  threshold
- leftover E5 cores grouped among themselves at the same threshold
  with separate `E5D_` IDs

This is not a MMseqs recluster and does not rewrite frozen `S5C_`
cluster IDs. ENA family must-link IDs are used where the combined
global-S4 input already records them.

```text
This is a counterfactual diagnostic only. E5 remains excluded and
no frozen split changes.

235 E5D diagnostic cluster units is a counterfactual diagnostic
quantity produced by the documented E5 diagnostic procedure. It is
not the exact number of S5 clusters that would result from admitting
E5. The diagnostic did not rerun the frozen MMseqs S5 clustering
pipeline and could not apply ENA family must-links because usable E5
family metadata were unavailable. Actual E5 admission would require a
new scientific corpus revision, re-running applicable
deduplication/clustering, target capping, and all downstream splits.

E5 promoted = no
frozen corpus changed = no
```

## Rejection log

`rejected_all.csv` concatenates:

- source-level CHECKPOINT-1 technical rejects
- global-S4 exclusion routes (`reject_no_binding_evidence`,
  `hold_target_unresolved`, `unresolved_no_relationship`)
- S7A target-cap removals with reason `target_cap_subsample`

Parked records are not classified as rejected. S5 merged-duplicate
provenance is not treated as a lost scientific observation.

## Gates re-run at S7D

- frozen-input SHA256 and semantic freeze hashes
- identity / core / cluster / target schema
- 3% target cap from `corpus_final.csv`
- exact and >=90% evaluation-reference leakage
- excluded target-alias gate
- TRAIN/VALIDATION/REF/EVAL cluster, core, and identity disjointness
- TRAIN-only training-text set equality
- E5 = 0 and non-protein = 0 in the primary corpus
- `git ls-files data` empty
- new S7D tracked sequence leaks = 0 versus `origin/main`

The plan retains the requirement for a full pre-publication
repository/history leakage audit before making the repository public.
S7D does not rewrite Git history.

## Determinism

The CLI runs the scientific payloads twice into independent temporary
directories under `data/processed/` before writing the live tree.
Byte identity is required for:

```text
corpus_final.csv
corpus_final.txt
ft_train.csv
ft_validation.csv
ref.csv
eval.csv
ft_split_assignment.csv
parked_ssdna.csv
parked_non_protein_targets.csv
parked_evidence_e5.csv
parked_inventory.csv
evaluation_references.csv
rejected_all.csv
corpus_replication_datasetA.csv
```

Report/manifest timestamps, if any, are compared separately from
scientific payloads. The written report is sequence-safe aggregate
content only.

## Command

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/data_preparation/s7_finalise.py \
  --config config/global_s7d_final_build.json
```

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest \
  tests/data_preparation/test_s7_final_build.py \
  tests/data_preparation/test_s7_ft_train_validation.py \
  tests/data_preparation/test_s7_partition.py \
  tests/data_preparation/test_s7_target_cap.py \
  tests/data_preparation/test_s5_final_clustering.py \
  tests/data_preparation/test_s6_profile.py
```

## Boundary

S7D does not start model fine-tuning, does not calculate AptaRank
reference distributions, does not evaluate models on EVAL, and does
not commit or push. Sequence-bearing outputs remain under ignored
`data/`.
