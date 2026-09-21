"""Synthetic tests for S5B exact-dedup validation.

Every literal nucleotide string in this file is shorter than 20 nt.
Tests do not read live biological S4 CSVs.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s5_exact_dedup import (  # noqa: E402
    exact_deduplicate,
    identities_remaining_after_excluding_sources,
    scientific_identity_id,
)
from adapters.s5_validate_exact_dedup import (  # noqa: E402
    S5ValidateError,
    classify_donor_decision,
    clustering_sequence_projection,
    forbid_donor_record_id_as_s5_unique_identity,
    require_unique_s5_row_identity,
    s5_row_identity,
    validate_exact_dedup,
)


SEQ_A = "ACGUACGUAA"
SEQ_B = "UGCAUGCAUU"
assert len(SEQ_A) < 20 and len(SEQ_B) < 20


def _row(
    *,
    rel_id: str,
    record_id: str,
    source_db: str,
    sequence_core: str,
    canonical_target_name: str,
    s4_route: str = "primary_candidate",
    **fields: str,
) -> dict[str, str]:
    row = {
        "reviewed_relationship_id": rel_id,
        "record_id": record_id,
        "source_db": source_db,
        "native_id": record_id.split(":", 1)[-1],
        "source_dataset": f"{source_db}_dataset",
        "sequence_core": sequence_core,
        "sequence_full": sequence_core,
        "canonical_target_name": canonical_target_name,
        "target_dictionary_id": fields.get("target_dictionary_id", "TD0001"),
        "s4_route": s4_route,
        "s4_route_reason": "protein_E2",
        "evidence_level": "E4",
        "evidence_score": "2",
        "evidence_type": "selection_enrichment",
        "molecule_type": "RNA",
        "chemistry": "RNA",
        "redistribution_status": "unknown",
        "pre_s5_corroboration_count": "1",
        "construct_scope": "unknown",
        "trim_status": "no_constants_detected",
    }
    row.update(fields)
    return row


def _validate(rows: list[dict[str, str]], result=None, **kwargs):
    produced = result or exact_deduplicate(rows)
    return validate_exact_dedup(
        relationship_rows=rows,
        corpus_rows=produced.corpus_dedup,
        membership_rows=produced.membership,
        group_rows=produced.duplicate_groups,
        dictionary_conflict_rows=produced.dictionary_id_conflicts,
        **kwargs,
    )


def test_complete_one_to_one_membership_coverage() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="aptaindex",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        ),
        _row(
            rel_id="c:1|1",
            record_id="c:1",
            source_db="ena",
            sequence_core=SEQ_B,
            canonical_target_name="VEGF",
        ),
    ]
    result = _validate(rows)
    assert result.ok
    assert result.diagnostics["n_input_relationships"] == 3
    assert result.diagnostics["n_membership_rows"] == 3
    assert result.diagnostics["n_scientific_identities"] == 2
    assert result.diagnostics["n_duplicate_excess"] == 1


def test_no_membership_from_excluded_routes() -> None:
    rows = [
        _row(
            rel_id="syn:1110|1",
            record_id="syn:1110",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="A549 cells",
            s4_route="park_non_protein",
        ),
        _row(
            rel_id="syn:1110|2",
            record_id="syn:1110",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            s4_route="primary_candidate",
            evidence_level="E2",
            evidence_score="4",
        ),
        _row(
            rel_id="syn:parked|1",
            record_id="syn:parked",
            source_db="ena",
            sequence_core=SEQ_B,
            canonical_target_name="EGFR",
            s4_route="park_evidence_e5",
        ),
        _row(
            rel_id="syn:hold|1",
            record_id="syn:hold",
            source_db="utexas",
            sequence_core=SEQ_B,
            canonical_target_name="unknown target",
            s4_route="hold_target_unresolved",
        ),
        _row(
            rel_id="syn:reject|1",
            record_id="syn:reject",
            source_db="aptamerbase",
            sequence_core=SEQ_B,
            canonical_target_name="EGFR",
            s4_route="reject_no_binding_evidence",
        ),
    ]
    produced = exact_deduplicate(rows)
    result = _validate(rows, produced, regression_relationship_id="syn:1110|2")
    assert result.ok
    member_ids = {row["reviewed_relationship_id"] for row in produced.membership}
    assert member_ids == {"syn:1110|2"}
    assert all(row["s4_route"] == "primary_candidate" for row in produced.membership)

    leaked = list(produced.membership)
    leaked.append(
        dict(
            produced.membership[0],
            reviewed_relationship_id="syn:parked|1",
            s4_route="park_evidence_e5",
        )
    )
    failed = validate_exact_dedup(
        relationship_rows=rows,
        corpus_rows=produced.corpus_dedup,
        membership_rows=leaked,
        group_rows=produced.duplicate_groups,
        dictionary_conflict_rows=produced.dictionary_id_conflicts,
        regression_relationship_id="syn:1110|2",
    )
    assert not failed.ok
    assert any("excluded" in item or "park_evidence_e5" in item for item in failed.errors)


def test_bidirectional_master_member_integrity() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="utexas",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            evidence_level="E2",
            evidence_score="4",
        ),
    ]
    produced = exact_deduplicate(rows)
    result = _validate(rows, produced)
    assert result.ok
    orphaned = [dict(row) for row in produced.corpus_dedup]
    orphaned.append(dict(produced.corpus_dedup[0], scientific_identity_id="S5I_" + "0" * 64))
    failed = validate_exact_dedup(
        relationship_rows=rows,
        corpus_rows=orphaned,
        membership_rows=produced.membership,
        group_rows=produced.duplicate_groups,
        dictionary_conflict_rows=produced.dictionary_id_conflicts,
    )
    assert not failed.ok


def test_unique_scientific_identity_and_key_consistency() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="ena",
            sequence_core=SEQ_B,
            canonical_target_name="VEGF",
        ),
    ]
    produced = exact_deduplicate(rows)
    result = _validate(rows, produced)
    assert result.ok
    ids = require_unique_s5_row_identity(produced.corpus_dedup)
    assert len(ids) == 2
    for row in produced.corpus_dedup:
        assert row["scientific_identity_id"] == scientific_identity_id(
            row["sequence_core"], row["canonical_target_name"]
        )


def test_multi_target_sequences_remain_separate() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="IL-17 A/A homodimer",
            target_dictionary_id="TD0412",
        ),
        _row(
            rel_id="a:1|2",
            record_id="a:1",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="IL-17 A/F heterodimer",
            target_dictionary_id="TD0413",
        ),
    ]
    produced = exact_deduplicate(rows)
    result = _validate(rows, produced)
    assert result.ok
    assert result.diagnostics["n_scientific_identities"] == 2
    assert result.diagnostics["n_multi_target_sequence_cores"] == 1


def test_donor_recomputation_and_decision_paths() -> None:
    evidence_rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="zzz_source",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            evidence_level="E2",
            evidence_score="4",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            evidence_level="E4",
            evidence_score="2",
            doi="10.1/aaa",
        ),
    ]
    assert classify_donor_decision(evidence_rows) == "evidence_score"
    completeness_rows = [
        _row(
            rel_id="c:1|1",
            record_id="c:1",
            source_db="utexas",
            sequence_core=SEQ_A,
            canonical_target_name="VEGF",
            evidence_level="E2",
            evidence_score="4",
            doi="10.1/aaa",
        ),
        _row(
            rel_id="d:1|1",
            record_id="d:1",
            source_db="utexas",
            sequence_core=SEQ_A,
            canonical_target_name="VEGF",
            evidence_level="E2",
            evidence_score="4",
        ),
    ]
    assert classify_donor_decision(completeness_rows) == "metadata_completeness"
    source_rows = [
        _row(
            rel_id="z:1|1",
            record_id="z:1",
            source_db="utexas",
            sequence_core=SEQ_B,
            canonical_target_name="EGFR",
            evidence_level="E2",
            evidence_score="4",
        ),
        _row(
            rel_id="e:1|1",
            record_id="e:1",
            source_db="aptabase",
            sequence_core=SEQ_B,
            canonical_target_name="EGFR",
            evidence_level="E2",
            evidence_score="4",
        ),
    ]
    assert classify_donor_decision(source_rows) == "alphabetical_source_db"
    tie_rows = [
        _row(
            rel_id="f:2|1",
            record_id="f:2",
            source_db="aptabase",
            sequence_core=SEQ_B,
            canonical_target_name="VEGF",
            evidence_level="E2",
            evidence_score="4",
        ),
        _row(
            rel_id="f:1|1",
            record_id="f:1",
            source_db="aptabase",
            sequence_core=SEQ_B,
            canonical_target_name="VEGF",
            evidence_level="E2",
            evidence_score="4",
        ),
    ]
    assert classify_donor_decision(tie_rows) == "alphabetical_reviewed_relationship_id"
    produced = exact_deduplicate(
        evidence_rows + completeness_rows + source_rows + tie_rows
    )
    result = _validate(
        evidence_rows + completeness_rows + source_rows + tie_rows, produced
    )
    assert result.ok
    assert result.diagnostics["n_donor_mismatches"] == 0
    assert result.diagnostics["n_identities_evidence_determined_winner"] == 1
    assert result.diagnostics["n_identities_completeness_determined_winner"] == 1
    assert result.diagnostics["n_identities_source_alphabetical_determined_winner"] == 1
    assert result.diagnostics["n_identities_relationship_id_tiebreak_determined_winner"] == 1


def test_corroboration_recomputation_ignores_within_source_duplicates() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        ),
        _row(
            rel_id="a:2|1",
            record_id="a:2",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="utexas",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            evidence_level="E2",
            evidence_score="4",
        ),
    ]
    result = _validate(rows)
    assert result.ok
    assert result.diagnostics["corroboration_count_distribution"] == {"2": 1}


def test_dictionary_id_conflict_validation() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="HIV-1 reverse transcriptase",
            target_dictionary_id="TD0365",
            evidence_level="E2",
            evidence_score="4",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="riboaptamer",
            sequence_core=SEQ_A,
            canonical_target_name="HIV-1 reverse transcriptase",
            target_dictionary_id="TD0366",
            evidence_level="E4",
            evidence_score="2",
        ),
    ]
    produced = exact_deduplicate(rows)
    result = _validate(rows, produced)
    assert result.ok
    assert result.diagnostics["n_target_dictionary_id_conflict_groups"] == 1
    assert produced.corpus_dedup[0]["target_dictionary_id"] == "TD0365"
    assert "TD0366" in produced.corpus_dedup[0]["contributing_target_dictionary_ids"]


def test_affinity_conflict_validation_does_not_flag_same_value_replicas() -> None:
    conflict_rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="CD4",
            evidence_level="E2",
            evidence_score="4",
            canonical_affinity_value="5e-09",
            affinity_type="Kd",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="aptaindex",
            sequence_core=SEQ_A,
            canonical_target_name="CD4",
            evidence_level="E2",
            evidence_score="4",
            canonical_affinity_value="5e-10",
            affinity_type="Kd",
        ),
    ]
    replica_rows = [
        _row(
            rel_id="c:1|1",
            record_id="c:1",
            source_db="aptabase",
            sequence_core=SEQ_B,
            canonical_target_name="VEGF",
            evidence_level="E2",
            evidence_score="4",
            canonical_affinity_value="1e-09",
            affinity_type="Kd",
        ),
        _row(
            rel_id="d:1|1",
            record_id="d:1",
            source_db="aptaindex",
            sequence_core=SEQ_B,
            canonical_target_name="VEGF",
            evidence_level="E2",
            evidence_score="4",
            canonical_affinity_value="1e-09",
            affinity_type="Kd",
        ),
    ]
    produced = exact_deduplicate(conflict_rows + replica_rows)
    result = _validate(conflict_rows + replica_rows, produced)
    assert result.ok
    assert result.diagnostics["n_groups_conflicting_affinity_values"] == 1
    assert result.diagnostics["n_groups_multiple_affinity_measurements"] == 2


def test_chemistry_conflict_validation() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="Factor Xa",
            chemistry="RNA",
            evidence_level="E2",
            evidence_score="4",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="aptaindex",
            sequence_core=SEQ_A,
            canonical_target_name="Factor Xa",
            chemistry="2F-RNA",
            evidence_level="E3",
            evidence_score="3",
        ),
    ]
    produced = exact_deduplicate(rows)
    result = _validate(rows, produced)
    assert result.ok
    assert result.diagnostics["n_scientific_identities"] == 1
    assert result.diagnostics["n_groups_multiple_chemistries"] == 1
    assert produced.corpus_dedup[0]["chemistry"] == "RNA"


def test_construct_trim_conflict_validation() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            construct_scope="full_equals_core_untrimmed",
            trim_status="not_trimmed",
            evidence_level="E2",
            evidence_score="4",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="ena",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            construct_scope="core_after_constant_trim",
            trim_status="trimmed_both",
        ),
    ]
    produced = exact_deduplicate(rows)
    result = _validate(rows, produced)
    assert result.ok
    assert result.diagnostics["n_scientific_identities"] == 1
    assert result.diagnostics["n_groups_multiple_construct_scopes"] == 1
    assert result.diagnostics["n_groups_multiple_trim_statuses"] == 1
    assert result.diagnostics["n_groups_multiple_sequence_full"] == 0
    assert result.diagnostics["n_donor_sequence_full_inconsistent"] == 0
    assert result.diagnostics["n_identities_with_differing_member_sequence_core"] == 0


def test_row_order_independence() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="aptaindex",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        ),
        _row(
            rel_id="c:1|1",
            record_id="c:1",
            source_db="ena",
            sequence_core=SEQ_B,
            canonical_target_name="VEGF",
        ),
    ]
    forward = exact_deduplicate(rows)
    shuffled = list(rows)
    random.Random(1).shuffle(shuffled)
    backward = exact_deduplicate(shuffled)
    first = _validate(rows, forward)
    second = validate_exact_dedup(
        relationship_rows=list(reversed(rows)),
        corpus_rows=list(reversed(backward.corpus_dedup)),
        membership_rows=list(reversed(backward.membership)),
        group_rows=list(reversed(backward.duplicate_groups)),
        dictionary_conflict_rows=list(reversed(backward.dictionary_id_conflicts)),
    )
    assert first.ok and second.ok
    assert first.diagnostics["n_scientific_identities"] == second.diagnostics[
        "n_scientific_identities"
    ]
    assert (
        first.diagnostics["donor_decision_distribution"]
        == second.diagnostics["donor_decision_distribution"]
    )


def test_duplicate_source_record_id_is_allowed_in_deduplicated_corpus_provenance() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        ),
        _row(
            rel_id="a:1|2",
            record_id="a:1",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="VEGF",
        ),
    ]
    produced = exact_deduplicate(rows)
    result = _validate(rows, produced)
    assert result.ok
    record_ids = [row["record_id"] for row in produced.corpus_dedup]
    assert len(record_ids) != len(set(record_ids))
    assert result.diagnostics["row_identity"]["record_id_is_unique"] is False
    assert result.diagnostics["row_identity"]["n_duplicated_donor_record_id_values"] == 1
    ids = [row["scientific_identity_id"] for row in produced.corpus_dedup]
    assert len(ids) == len(set(ids)) == 2


def test_scientific_identity_id_is_required_unique() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="ena",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        )
    ]
    produced = exact_deduplicate(rows)
    require_unique_s5_row_identity(produced.corpus_dedup)
    duplicated = produced.corpus_dedup + produced.corpus_dedup
    with pytest.raises(S5ValidateError, match="not unique"):
        require_unique_s5_row_identity(duplicated)
    blanked = [dict(produced.corpus_dedup[0], scientific_identity_id="")]
    with pytest.raises(S5ValidateError, match="required"):
        s5_row_identity(blanked[0])


def test_downstream_must_not_treat_donor_record_id_as_s5_unique_identity() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        ),
        _row(
            rel_id="a:1|2",
            record_id="a:1",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="VEGF",
        ),
    ]
    produced = exact_deduplicate(rows)
    require_unique_s5_row_identity(produced.corpus_dedup)
    assert s5_row_identity(produced.corpus_dedup[0]) == produced.corpus_dedup[0][
        "scientific_identity_id"
    ]
    with pytest.raises(S5ValidateError, match="scientific_identity_id"):
        forbid_donor_record_id_as_s5_unique_identity(produced.corpus_dedup)


def test_clustering_ready_sequence_projection_one_row_per_core_without_clustering() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        ),
        _row(
            rel_id="a:1|2",
            record_id="a:1",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="VEGF",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="ena",
            sequence_core=SEQ_B,
            canonical_target_name="EGFR",
        ),
    ]
    produced = exact_deduplicate(rows)
    projection = clustering_sequence_projection(produced.corpus_dedup)
    assert len(projection) == 2
    by_core = {row["sequence_core"]: row for row in projection}
    assert by_core[SEQ_A]["n_scientific_identities"] == "2"
    assert by_core[SEQ_B]["n_scientific_identities"] == "1"
    assert all("cluster_id" not in row for row in projection)
    assert all(row.get("cluster_id", "") == "" for row in produced.corpus_dedup)
    result = _validate(rows, produced)
    assert result.ok
    assert result.diagnostics["clustering_readiness"]["n_clustering_input_rows"] == 2


def test_source_exclusion_reversibility_is_retained() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptaindex",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            redistribution_status="restricted",
            evidence_level="E2",
            evidence_score="4",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            redistribution_status="unknown",
            evidence_level="E3",
            evidence_score="3",
        ),
    ]
    produced = exact_deduplicate(rows)
    result = _validate(rows, produced)
    assert result.ok
    assert result.diagnostics["n_restricted_aptaindex_membership_rows"] == 1
    identity = produced.corpus_dedup[0]["scientific_identity_id"]
    remaining = identities_remaining_after_excluding_sources(
        produced.membership, {"aptaindex"}
    )
    assert identity in remaining
    assert remaining[identity]["contributing_sources"] == "aptabase"
