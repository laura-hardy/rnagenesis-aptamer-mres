"""Prepare the blank CHECKPOINT-2 human-review package."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from adapters.s4_scientific_common import (
    AFFINITY_DECISION_VOCAB,
    AFFINITY_EXTRA_HUMAN_FIELDS,
    HUMAN_FIELDS,
    MANUAL_DECISION_VOCAB,
    assert_human_fields_blank,
    assert_no_sequence_leak,
    blank_affinity_human_fields,
    blank_human_fields,
    fill_row,
    join_unique,
    write_text_atomic,
)
from common.corpus_schema import write_corpus_csv_atomic

TARGET_REVIEW_COLUMNS = (
    "decision_id",
    "target_dictionary_id",
    "raw_target",
    "source_keys",
    "n_records",
    "canonical_target_name_proposal",
    "uniprot_proposed",
    "uniprot_candidates",
    "target_type_proposed",
    "target_family_proposed",
    "target_pfam_proposed",
    "target_interpro_proposed",
    "proposal_confidence",
    "resolution_provenance",
    "scientific_ambiguity_reason",
    "machine_recommendation",
    *HUMAN_FIELDS,
)

RELATIONSHIP_REVIEW_COLUMNS = (
    "decision_id",
    "record_id",
    "source_db",
    "relationship_status",
    "n_relationships",
    "raw_targets",
    "target_dictionary_ids",
    "ambiguity_reason",
    "machine_recommendation",
    *HUMAN_FIELDS,
)

EVIDENCE_REVIEW_COLUMNS = (
    "decision_id",
    "source_db",
    "evidence_rule",
    "evidence_level_proposed",
    "alternative_evidence_level",
    "e4_e5_threshold_ambiguous",
    "n_records",
    "record_ids_preview",
    "evidence_provenance",
    "threshold_consequence",
    "machine_recommendation",
    *HUMAN_FIELDS,
)

AFFINITY_REVIEW_COLUMNS = (
    "decision_id",
    "parent_decision_id",
    "source_db",
    "affinity_parse_status",
    "affinity_parse_rule",
    "affinity_subgroup",
    "affinity_type_proposed",
    "n_records",
    "record_ids",
    "record_ids_preview",
    "affinity_raw_examples",
    "scientific_ambiguity_reason",
    "review_consequence",
    "machine_recommendation",
    "machine_affinity_transform_rule",
    "park_provenance_record_ids",
    *HUMAN_FIELDS,
    *AFFINITY_EXTRA_HUMAN_FIELDS,
)

LEAKAGE_REVIEW_COLUMNS = (
    "decision_id",
    "record_id",
    "source_db",
    "sequence_match_kind",
    "identity",
    "target_alias_match",
    "matched_canonical_target",
    "notes",
    "machine_recommendation",
    *HUMAN_FIELDS,
)

ACTION_VOCABULARY_TEXT = (
    "Permitted manual_decision values: "
    + ", ".join(sorted(MANUAL_DECISION_VOCAB))
    + ". Affinity-only outcomes: "
    + ", ".join(sorted(AFFINITY_DECISION_VOCAB))
    + ". Human fields must remain blank until Milestone 4."
)


def _preview_ids(record_ids: Sequence[str], *, limit: int = 8) -> str:
    ordered = list(dict.fromkeys(record_ids))
    if len(ordered) <= limit:
        return "|".join(ordered)
    return "|".join(ordered[:limit]) + f"|+{len(ordered) - limit}"


def prepare_checkpoint2_package(
    *,
    repo_root: Path,
    output_dir: Path,
    dictionary_rows: Sequence[Mapping[str, str]],
    relationship_rows: Sequence[Mapping[str, str]],
    extraction_rows: Sequence[Mapping[str, str]],
    evidence_rows: Sequence[Mapping[str, str]],
    leakage_rows: Sequence[Mapping[str, str]],
    routing_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    human = blank_human_fields()

    target_rows: list[dict[str, str]] = []
    dict_review = [
        row for row in dictionary_rows if row.get("requires_checkpoint2") == "true"
    ]
    dict_review.sort(key=lambda row: (-int(row.get("n_records") or 0), row.get("target_dictionary_id", "")))
    affected_records: set[str] = set()
    for index, row in enumerate(dict_review, start=1):
        item = fill_row(
            TARGET_REVIEW_COLUMNS,
            {
                "decision_id": f"C2T{index:04d}",
                "target_dictionary_id": row.get("target_dictionary_id", ""),
                "raw_target": row.get("raw_target", ""),
                "source_keys": row.get("source_keys", ""),
                "n_records": row.get("n_records", ""),
                "canonical_target_name_proposal": row.get("canonical_target_name_proposal", ""),
                "uniprot_proposed": row.get("uniprot_proposed", ""),
                "uniprot_candidates": row.get("uniprot_candidates", ""),
                "target_type_proposed": row.get("target_type_proposed", ""),
                "target_family_proposed": row.get("target_family_proposed", ""),
                "target_pfam_proposed": row.get("target_pfam_proposed", ""),
                "target_interpro_proposed": row.get("target_interpro_proposed", ""),
                "proposal_confidence": row.get("proposal_confidence", ""),
                "resolution_provenance": row.get("resolution_provenance", ""),
                "scientific_ambiguity_reason": row.get("scientific_ambiguity_reason", ""),
                "machine_recommendation": row.get("machine_recommendation", "review_required"),
                **human,
            },
        )
        assert_human_fields_blank(item, label="target review")
        target_rows.append(item)

    review_dictionary_ids = {
        row.get("target_dictionary_id", "") for row in dict_review if row.get("target_dictionary_id")
    }

    extraction_by_id = {row["record_id"]: row for row in extraction_rows}
    rel_groups: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in relationship_rows:
        rels_status = row.get("relationship_status", "")
        if rels_status in {"ambiguous", "resolved_multiple"} or row.get("record_expansion_proposed") == "true":
            rel_groups[row["record_id"]].append(row)
    relationship_review: list[dict[str, str]] = []
    for index, record_id in enumerate(sorted(rel_groups), start=1):
        group = rel_groups[record_id]
        extraction = extraction_by_id.get(record_id, {})
        rec = fill_row(
            RELATIONSHIP_REVIEW_COLUMNS,
            {
                "decision_id": f"C2R{index:04d}",
                "record_id": record_id,
                "source_db": group[0].get("source_db", ""),
                "relationship_status": extraction.get("relationship_status", group[0].get("relationship_status", "")),
                "n_relationships": str(len(group)),
                "raw_targets": join_unique([item.get("raw_target", "") for item in group]),
                "target_dictionary_ids": join_unique(
                    [item.get("target_dictionary_id", "") for item in group]
                ),
                "ambiguity_reason": extraction.get("ambiguity_reason", ""),
                "machine_recommendation": (
                    "confirm_multi_target_expansion"
                    if extraction.get("record_expansion_proposed") == "true"
                    else "review_relationship"
                ),
                **human,
            },
        )
        assert_human_fields_blank(rec, label="relationship review")
        relationship_review.append(rec)
        affected_records.add(record_id)

    evidence_groups: dict[tuple[str, str, str, str], list[Mapping[str, str]]] = defaultdict(list)
    seen_evidence_records: set[str] = set()
    for row in evidence_rows:
        # Only E4/E5 threshold (or equivalent evidence-level) ambiguities.
        # Deterministic E2/E3/E4 and affinity-parse issues are not evidence decisions.
        if row.get("e4_e5_threshold_ambiguous") != "true":
            continue
        key = (
            row.get("source_db", ""),
            row.get("evidence_rule", ""),
            row.get("evidence_level_proposed", ""),
            row.get("alternative_evidence_level", ""),
        )
        evidence_groups[key].append(row)
    evidence_review: list[dict[str, str]] = []
    for index, (key, group) in enumerate(sorted(evidence_groups.items()), start=1):
        record_ids = list(dict.fromkeys(item.get("record_id", "") for item in group))
        consequence = "inclusion_threshold_unchanged"
        if key[3] and {key[2], key[3]} >= {"E4", "E5"} or (
            key[2] in {"E4", "E5"} and key[3] in {"E4", "E5"}
        ):
            consequence = "changes_e4_inclusion_threshold"
        rec = fill_row(
            EVIDENCE_REVIEW_COLUMNS,
            {
                "decision_id": f"C2E{index:04d}",
                "source_db": key[0],
                "evidence_rule": key[1],
                "evidence_level_proposed": key[2],
                "alternative_evidence_level": key[3],
                "e4_e5_threshold_ambiguous": group[0].get("e4_e5_threshold_ambiguous", "false"),
                "n_records": str(len(record_ids)),
                "record_ids_preview": _preview_ids(record_ids),
                "evidence_provenance": group[0].get("evidence_provenance", ""),
                "threshold_consequence": consequence,
                "machine_recommendation": "confirm_evidence",
                **human,
            },
        )
        assert_human_fields_blank(rec, label="evidence review")
        evidence_review.append(rec)
        affected_records.update(record_ids)
        seen_evidence_records.update(record_ids)

    affinity_groups: dict[tuple[str, str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in evidence_rows:
        if row.get("affinity_requires_review") != "true":
            continue
        if row.get("affinity_parse_status") in {"absent", ""}:
            continue
        key = (
            row.get("source_db", ""),
            row.get("affinity_parse_status", ""),
            row.get("affinity_parse_rule", ""),
        )
        affinity_groups[key].append(row)
    affinity_review: list[dict[str, str]] = []
    for index, (key, group) in enumerate(sorted(affinity_groups.items()), start=1):
        record_ids = list(dict.fromkeys(item.get("record_id", "") for item in group))
        rec = fill_row(
            AFFINITY_REVIEW_COLUMNS,
            {
                "decision_id": f"C2A{index:04d}",
                "parent_decision_id": f"C2A{index:04d}",
                "source_db": key[0],
                "affinity_parse_status": key[1],
                "affinity_parse_rule": key[2],
                "affinity_type_proposed": group[0].get("affinity_type_proposed", ""),
                "n_records": str(len(record_ids)),
                "record_ids": join_unique(record_ids),
                "record_ids_preview": _preview_ids(record_ids),
                "machine_recommendation": "review_affinity_parse",
                **blank_affinity_human_fields(),
            },
        )
        assert_human_fields_blank(rec, label="affinity review")
        affinity_review.append(rec)
        affected_records.update(record_ids)

    leakage_review: list[dict[str, str]] = []
    leak_index = 1
    for row in leakage_rows:
        if row.get("requires_review") != "true":
            continue
        rec = fill_row(
            LEAKAGE_REVIEW_COLUMNS,
            {
                "decision_id": f"C2L{leak_index:04d}",
                "record_id": row.get("record_id", ""),
                "source_db": row.get("source_db", ""),
                "sequence_match_kind": row.get("sequence_match_kind", ""),
                "identity": row.get("identity", ""),
                "target_alias_match": row.get("target_alias_match", ""),
                "matched_canonical_target": row.get("matched_canonical_target", ""),
                "notes": row.get("notes", ""),
                "machine_recommendation": "review_leakage_match",
                **human,
            },
        )
        assert_human_fields_blank(rec, label="leakage review")
        leakage_review.append(rec)
        affected_records.add(row.get("record_id", ""))
        leak_index += 1

    write_corpus_csv_atomic(output_dir / "checkpoint2_target_dictionary_review.csv", target_rows, columns=TARGET_REVIEW_COLUMNS)
    write_corpus_csv_atomic(
        output_dir / "checkpoint2_relationship_review.csv",
        relationship_review,
        columns=RELATIONSHIP_REVIEW_COLUMNS,
    )
    write_corpus_csv_atomic(output_dir / "checkpoint2_evidence_review.csv", evidence_review, columns=EVIDENCE_REVIEW_COLUMNS)
    write_corpus_csv_atomic(output_dir / "checkpoint2_affinity_review.csv", affinity_review, columns=AFFINITY_REVIEW_COLUMNS)
    write_corpus_csv_atomic(output_dir / "checkpoint2_leakage_review.csv", leakage_review, columns=LEAKAGE_REVIEW_COLUMNS)

    for row in relationship_rows:
        if row.get("requires_checkpoint2") == "true" or row.get("target_dictionary_id") in review_dictionary_ids:
            affected_records.add(row.get("record_id", ""))
    for row in routing_rows:
        if row.get("requires_checkpoint2") == "true":
            affected_records.add(row.get("record_id", ""))

    readme = "\n".join(
        [
            "# CHECKPOINT-2 review package",
            "",
            "Blank fail-closed human review for Milestone 3. Do not treat this as",
            "CHECKPOINT-2 completion. Human fields must stay empty until Milestone 4.",
            "",
            ACTION_VOCABULARY_TEXT,
            "",
            "Decision grains:",
            f"- target dictionary: {len(target_rows)}",
            f"- relationship / multi-target: {len(relationship_review)}",
            f"- evidence: {len(evidence_review)}",
            f"- affinity: {len(affinity_review)}",
            f"- leakage: {len(leakage_review)}",
            f"- affected records (union): {len(affected_records)}",
            "",
        ]
    )
    assert_no_sequence_leak(readme, label="checkpoint2 readme")
    write_text_atomic(output_dir / "README.md", readme)

    counts = {
        "target": len(target_rows),
        "relationship": len(relationship_review),
        "evidence": len(evidence_review),
        "affinity": len(affinity_review),
        "leakage": len(leakage_review),
        "affected_records": len(affected_records),
        "total_decisions": (
            len(target_rows)
            + len(relationship_review)
            + len(evidence_review)
            + len(affinity_review)
            + len(leakage_review)
        ),
    }
    return {
        "decision_counts": counts,
        "files": [
            "checkpoint2_target_dictionary_review.csv",
            "checkpoint2_relationship_review.csv",
            "checkpoint2_evidence_review.csv",
            "checkpoint2_affinity_review.csv",
            "checkpoint2_leakage_review.csv",
            "README.md",
        ],
        "human_fields": list(HUMAN_FIELDS),
        "manual_decision_vocabulary": sorted(MANUAL_DECISION_VOCAB),
    }
