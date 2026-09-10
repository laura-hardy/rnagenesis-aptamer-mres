# ENA review v2 (group-first clerical review)

Corrective **stage 4** after inspection → candidate processing → review
consolidation. Repairs target normalisation and binding-evidence scope, then
enforces a **group-first** manual-review workflow.

Does **not** overwrite `data/raw/ena/review/`.

## Workflow

```text
repair targets and evidence
        ↓
generate compact experiment-group review
        ↓
user marks experiment groups 0/1
        ↓
apply group decisions
        ↓
generate sequence-level review only for retained groups
        ↓
user marks sequence–target pairs 0/1
```

## Commands

```bash
python scripts/data_preparation/refine_ena_manual_review.py build-review \
  --review-dir data/raw/ena/review \
  --candidate-dir data/raw/ena/candidates \
  --output-dir data/raw/ena/review_v2 \
  --overwrite
```

```bash
python scripts/data_preparation/refine_ena_manual_review.py apply-group-review \
  --group-review-file data/raw/ena/review_v2/ena_group_review_template.csv \
  --output-dir data/raw/ena/review_v2
```

```bash
python scripts/data_preparation/refine_ena_manual_review.py apply-sequence-review \
  --sequence-review-file data/raw/ena/review_v2/ena_sequence_review_template.csv \
  --output-dir data/raw/ena/review_v2 \
  --overwrite
```

No internet access is required. Rules live in `ena_review_v2_rules.py`
(editable `TARGET_ALIASES` near the top).

## Outputs

```text
data/raw/ena/review_v2/
├── ena_group_review_template.csv       # Compact group clerical sheet
├── ena_group_review_provenance.csv     # Full group provenance
├── ena_target_repairs.csv
├── ena_target_aliases.csv
├── ena_evidence_repairs.csv
├── ena_group_review_qc_report.md
├── ena_sequence_conflicts.csv          # Genuine / unresolved only
├── ena_groups_retained_after_review.csv
├── ena_groups_rejected_after_review.csv
├── ena_sequence_review_template.csv    # After apply-group-review
├── ena_sequence_review_provenance.csv
├── ena_selected_after_manual_review.csv
├── ena_rejected_after_manual_review.csv
├── ena_unreviewed_after_manual_review.csv
├── ena_selected_sequence_provenance.csv
├── ena_apply_sequence_review_qc_report.md
├── ena_apply_sequence_review_log.txt
└── ena_review_v2_log.txt
```

`manual_group_include` / `manual_include`: blank = unreviewed, `1` = retain,
`0` = reject. Manual fields are left blank by `build-review`.

## Scientific unit

```text
unique RNA aptamer sequence – named protein target pair
```

with provenance and evidence scoped as:

* individual_sequence_quantitative / qualitative
* experiment_family_level
* patent_claim_level
* selection_context_only
* none

Patent titles are **not** treated as individual-sequence measurements.

## Tests

```bash
pytest tests/data_preparation/test_refine_ena_manual_review.py -q
```
