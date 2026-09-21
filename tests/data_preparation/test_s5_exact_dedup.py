"""Synthetic tests for S5A exact scientific deduplication.

Every literal nucleotide string in this file is shorter than 20 nt.
Tests do not read live biological S4 CSVs.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s5_exact_dedup import (  # noqa: E402
    METADATA_COMPLETENESS_FIELDS,
    exact_deduplicate,
    identities_remaining_after_excluding_sources,
    metadata_completeness_score,
    scientific_identity_id,
    select_donor,
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


def test_completeness_field_list_is_explicit_and_stable() -> None:
    assert METADATA_COMPLETENESS_FIELDS == (
        "canonical_affinity",
        "affinity_type",
        "doi",
        "pubmed_id",
        "accession",
        "target_uniprot",
        "target_pfam",
        "target_family",
        "pdb_id",
        "chemistry",
        "molecule_type",
        "construct_scope",
        "trim_status",
        "publication",
    )


def test_only_primary_candidate_enters_and_mixed_route_record_keeps_primary() -> None:
    rows = [
        _row(
            rel_id="syn:1110|1",
            record_id="syn:1110",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="A549 cells",
            s4_route="park_non_protein",
            target_dictionary_id="TD9001",
        ),
        _row(
            rel_id="syn:1110|2",
            record_id="syn:1110",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            s4_route="primary_candidate",
            target_dictionary_id="TD0207",
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
    result = exact_deduplicate(rows)
    assert result.diagnostics["n_input_relationships"] == 1
    assert result.membership[0]["reviewed_relationship_id"] == "syn:1110|2"
    assert result.corpus_dedup[0]["canonical_target_name"] == "EGFR"
    assert all(row["s4_route"] == "primary_candidate" for row in result.input_rows)


def test_record_level_outcome_is_not_used_as_filter() -> None:
    rows = [
        _row(
            rel_id="syn:1110|2",
            record_id="syn:1110",
            source_db="aptamerbase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            s4_record_outcome="park_non_protein",
        )
    ]
    result = exact_deduplicate(rows)
    assert result.diagnostics["n_input_relationships"] == 1


def test_same_sequence_same_target_collapses() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            evidence_level="E3",
            evidence_score="3",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="aptaindex",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            evidence_level="E2",
            evidence_score="4",
        ),
    ]
    result = exact_deduplicate(rows)
    assert len(result.corpus_dedup) == 1
    assert len(result.membership) == 2
    assert len(result.duplicate_groups) == 1


def test_same_sequence_different_target_does_not_collapse() -> None:
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
    result = exact_deduplicate(rows)
    assert len(result.corpus_dedup) == 2
    names = {row["canonical_target_name"] for row in result.corpus_dedup}
    assert names == {"IL-17 A/A homodimer", "IL-17 A/F heterodimer"}
    assert result.diagnostics["n_multi_target_sequence_cores"] == 1


def test_same_target_different_sequence_does_not_collapse() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="ena",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        ),
        _row(
            rel_id="a:2|1",
            record_id="a:2",
            source_db="ena",
            sequence_core=SEQ_B,
            canonical_target_name="EGFR",
        ),
    ]
    result = exact_deduplicate(rows)
    assert len(result.corpus_dedup) == 2


def test_two_dictionary_ids_collapse_without_global_merge() -> None:
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
    result = exact_deduplicate(rows)
    assert len(result.corpus_dedup) == 1
    master = result.corpus_dedup[0]
    assert master["target_dictionary_id"] == "TD0365"
    assert master["contributing_target_dictionary_ids"] == "TD0365|TD0366"
    assert "multiple_target_dictionary_ids" in master["conflict_flags"]
    member_ids = {row["target_dictionary_id"] for row in result.membership}
    assert member_ids == {"TD0365", "TD0366"}
    assert len(result.dictionary_id_conflicts) == 1


def test_higher_evidence_wins_donor() -> None:
    low = _row(
        rel_id="a:1|1",
        record_id="a:1",
        source_db="aptabase",
        sequence_core=SEQ_A,
        canonical_target_name="EGFR",
        evidence_level="E4",
        evidence_score="2",
        doi="10.1/aaa",
        pubmed_id="1",
        accession="X1",
        target_uniprot="P00533",
    )
    high = _row(
        rel_id="b:1|1",
        record_id="b:1",
        source_db="zzz_source",
        sequence_core=SEQ_A,
        canonical_target_name="EGFR",
        evidence_level="E2",
        evidence_score="4",
    )
    result = exact_deduplicate([low, high])
    assert result.corpus_dedup[0]["source_db"] == "zzz_source"
    assert result.corpus_dedup[0]["evidence_level"] == "E2"


def test_completeness_tiebreak_ignores_text_length() -> None:
    short_pub = _row(
        rel_id="a:1|1",
        record_id="a:1",
        source_db="utexas",
        sequence_core=SEQ_A,
        canonical_target_name="EGFR",
        evidence_level="E2",
        evidence_score="4",
        doi="10.1/aaa",
        publication="A",
    )
    long_pub = _row(
        rel_id="b:1|1",
        record_id="b:1",
        source_db="utexas",
        sequence_core=SEQ_A,
        canonical_target_name="EGFR",
        evidence_level="E2",
        evidence_score="4",
        publication="A" * 80,
    )
    assert metadata_completeness_score(short_pub) > metadata_completeness_score(long_pub)
    result = exact_deduplicate([long_pub, short_pub])
    assert result.corpus_dedup[0]["donor_reviewed_relationship_id"] == "a:1|1"
    assert result.corpus_dedup[0]["doi"] == "10.1/aaa"


def test_alphabetical_source_tiebreak() -> None:
    rows = [
        _row(
            rel_id="z:1|1",
            record_id="z:1",
            source_db="utexas",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            evidence_level="E2",
            evidence_score="4",
        ),
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            evidence_level="E2",
            evidence_score="4",
        ),
    ]
    result = exact_deduplicate(rows)
    assert result.corpus_dedup[0]["source_db"] == "aptabase"


def test_final_tie_is_row_order_independent() -> None:
    first = _row(
        rel_id="a:2|1",
        record_id="a:2",
        source_db="aptabase",
        sequence_core=SEQ_A,
        canonical_target_name="EGFR",
        evidence_level="E2",
        evidence_score="4",
    )
    second = _row(
        rel_id="a:1|1",
        record_id="a:1",
        source_db="aptabase",
        sequence_core=SEQ_A,
        canonical_target_name="EGFR",
        evidence_level="E2",
        evidence_score="4",
    )
    forward = exact_deduplicate([first, second])
    backward = exact_deduplicate([second, first])
    assert (
        forward.corpus_dedup[0]["donor_reviewed_relationship_id"]
        == backward.corpus_dedup[0]["donor_reviewed_relationship_id"]
        == "a:1|1"
    )
    assert select_donor([first, second])["reviewed_relationship_id"] == "a:1|1"
    assert select_donor([second, first])["reviewed_relationship_id"] == "a:1|1"


def test_pre_s5_corroboration_is_not_duplicate_row_count() -> None:
    rows = [
        _row(
            rel_id="u:1|1",
            record_id="u:1",
            source_db="utexas",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            evidence_level="E2",
            evidence_score="4",
            pre_s5_corroboration_count="1",
        ),
        _row(
            rel_id="u:2|1",
            record_id="u:2",
            source_db="utexas",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            evidence_level="E2",
            evidence_score="4",
            pre_s5_corroboration_count="1",
        ),
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            evidence_level="E2",
            evidence_score="4",
            pre_s5_corroboration_count="1",
        ),
    ]
    result = exact_deduplicate(rows)
    assert result.corpus_dedup[0]["corroboration_count"] == "2"
    # Two UTexas rows must not become a corroboration tiebreak over AptaBase.
    assert result.corpus_dedup[0]["source_db"] == "aptabase"


def test_membership_contains_every_input_relationship_once() -> None:
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
    result = exact_deduplicate(rows)
    member_ids = [row["reviewed_relationship_id"] for row in result.membership]
    assert sorted(member_ids) == ["a:1|1", "b:1|1", "c:1|1"]
    assert len(member_ids) == len(set(member_ids))


def test_corroboration_counts_distinct_sources_not_rows() -> None:
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
    result = exact_deduplicate(rows)
    master = result.corpus_dedup[0]
    assert master["corroboration_count"] == "2"
    assert master["contributing_sources"] == "aptamerbase|utexas"
    datasets = master["contributing_datasets"].split("|")
    assert datasets == sorted(datasets)


def test_affinity_measurements_are_retained_not_averaged() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="CD4",
            evidence_level="E2",
            evidence_score="4",
            canonical_affinity_value="5e-09",
            affinity_value_molar="5e-09",
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
            affinity_value_molar="5e-10",
            affinity_type="Kd",
        ),
    ]
    result = exact_deduplicate(rows)
    master = result.corpus_dedup[0]
    assert master["canonical_affinity_value"] in {"5e-09", "5e-10"}
    assert master["canonical_affinity_value"] != "2.75e-09"
    member_vals = {row["canonical_affinity_value"] for row in result.membership}
    assert member_vals == {"5e-09", "5e-10"}
    assert "conflicting_affinity_values" in master["conflict_flags"]
    assert "multiple_affinity_measurements" in master["conflict_flags"]


def test_chemistry_conflict_still_one_identity() -> None:
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
    result = exact_deduplicate(rows)
    assert len(result.corpus_dedup) == 1
    master = result.corpus_dedup[0]
    assert master["chemistry"] == "RNA"
    assert master["contributing_chemistries"] == "2F-RNA|RNA"
    assert "multiple_chemistries" in master["conflict_flags"]
    chemistries = {row["chemistry"] for row in result.membership}
    assert chemistries == {"RNA", "2F-RNA"}


def test_scientific_identity_id_stable_under_shuffle_and_unique() -> None:
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
        _row(
            rel_id="c:1|2",
            record_id="c:1",
            source_db="ena",
            sequence_core=SEQ_B,
            canonical_target_name="EGFR",
        ),
    ]
    forward = exact_deduplicate(rows)
    shuffled = list(rows)
    random.Random(0).shuffle(shuffled)
    backward = exact_deduplicate(shuffled)
    assert [row["scientific_identity_id"] for row in forward.corpus_dedup] == [
        row["scientific_identity_id"] for row in backward.corpus_dedup
    ]
    ids = [row["scientific_identity_id"] for row in forward.corpus_dedup]
    assert len(ids) == len(set(ids)) == 3
    expected = {
        scientific_identity_id(SEQ_A, "EGFR"),
        scientific_identity_id(SEQ_B, "VEGF"),
        scientific_identity_id(SEQ_B, "EGFR"),
    }
    assert set(ids) == expected
    for identity in ids:
        assert identity.startswith("S5I_")
        assert len(identity) == 4 + 64


def test_reversibility_keeps_independent_source() -> None:
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
    result = exact_deduplicate(rows)
    identity = result.corpus_dedup[0]["scientific_identity_id"]
    remaining = identities_remaining_after_excluding_sources(
        result.membership, {"aptaindex"}
    )
    assert identity in remaining
    merged = remaining[identity]
    assert merged["contributing_sources"] == "aptabase"
    assert merged["corroboration_count"] == "1"
    assert merged["redistribution_status"] == "unknown"
    dropped = identities_remaining_after_excluding_sources(
        result.membership, {"aptaindex", "aptabase"}
    )
    assert identity not in dropped


def test_permissive_flag_stays_false_without_permissive_source() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptaindex",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            redistribution_status="restricted",
        ),
        _row(
            rel_id="b:1|1",
            record_id="b:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
            redistribution_status="unknown",
        ),
    ]
    result = exact_deduplicate(rows)
    assert result.corpus_dedup[0]["independently_attested_by_permissive_source"] == "false"
    assert result.corpus_dedup[0]["redistribution_status"] == "unknown"


def test_combined_extras_fill_blank_construct_and_dataset_fields() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="aptabase",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        )
    ]
    rows[0]["source_dataset"] = ""
    rows[0]["construct_scope"] = ""
    rows[0]["trim_status"] = ""
    extras = {
        "a:1": {
            "source_dataset": "aptabase_cleaned_scrape_2026-07-20",
            "construct_scope": "full_equals_core_untrimmed",
            "trim_status": "not_trimmed",
            "redistribution_status": "unknown",
            "corroboration_count": "1",
            "accessions": "",
        }
    }
    result = exact_deduplicate(rows, combined_by_record_id=extras)
    assert result.membership[0]["source_dataset"] == "aptabase_cleaned_scrape_2026-07-20"
    assert result.membership[0]["construct_scope"] == "full_equals_core_untrimmed"
    assert result.membership[0]["trim_status"] == "not_trimmed"


def test_cluster_fields_remain_empty() -> None:
    rows = [
        _row(
            rel_id="a:1|1",
            record_id="a:1",
            source_db="ena",
            sequence_core=SEQ_A,
            canonical_target_name="EGFR",
        )
    ]
    result = exact_deduplicate(rows)
    assert result.corpus_dedup[0]["cluster_id"] == ""
    assert result.corpus_dedup[0]["is_cluster_representative"] == ""
    assert result.corpus_dedup[0]["partition"] == ""
