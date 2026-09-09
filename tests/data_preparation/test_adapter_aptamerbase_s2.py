"""Tests for AptamerBase S2 (synthetic sequences and synthetic RDF only).

Every literal nucleotide string in this file is shorter than 20 nt, except
programmatically generated homopolymers used to exercise length QC.
Does not read real AptamerBase aptamer sequences or real RDF source records
except in the optional local-only production skipif gate, which asserts
counts without embedding sequences in this file.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptamerbase import (  # noqa: E402
    SIDECAR_COLUMNS,
    TYPE_APTAMER,
    TYPE_PREDICTED_STRUCTURE,
    TYPE_SECONDARY_STRUCTURE,
)
from adapters.aptamerbase_rdf import (  # noqa: E402
    AptamerBaseRdfError,
    AptamerBaseRdfSubjectFacts,
    load_aptamerbase_rdf_index,
    parse_ntriples_line,
    require_subject_facts,
)
from adapters.aptamerbase_s2 import (  # noqa: E402
    GROUP_INFERENCE_DISABLED,
    AptamerBaseS2Error,
    classify_modification,
    load_aptamerbase_policy,
    normalise_aptamerbase_record,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S2_FORBIDDEN_FIELDS,
    empty_corpus_record,
)
from common.sequence_normalisation import load_normalisation_rules  # noqa: E402
from s2_normalise import (  # noqa: E402
    S2NormaliseError,
    run_aptamerbase_s2,
    run_s2_normalisation,
)

POLICY_PATH = REPO_ROOT / "config" / "source_normalisation" / "aptamerbase.json"
RULES_PATH = REPO_ROOT / "config" / "sequence_normalisation_rules.json"
PRODUCTION_S1 = (
    REPO_ROOT / "data" / "interim" / "extracted" / "aptamerbase_extracted.csv"
)
PRODUCTION_SIDECAR = (
    REPO_ROOT / "data" / "interim" / "extracted" / "aptamerbase_source_metadata.csv"
)
PRODUCTION_RAW_CSV = (
    REPO_ROOT / "data" / "raw" / "aptamerbase" / "aptamerbase_aptamers.csv"
)
PRODUCTION_RDF = (
    REPO_ROOT / "data" / "raw" / "aptamerbase" / "aptamerbase.freebase.extract.nt.gz"
)

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
FB_TYPE = "http://rdf.freebase.com/ns/type.object.type"
URI_RNA = "http://rdf.freebase.com/ns/base.aptamer.rna"
URI_DNA = "http://rdf.freebase.com/ns/base.aptamer.dna"
URI_MOD = "http://rdf.freebase.com/ns/base.aptamer.modified_nucleic_acid"
URI_SUBJECT = "http://rdf.freebase.com/ns/m.synthetic01"
URI_SUBJECT_B = "http://rdf.freebase.com/ns/m.synthetic02"
URI_EXTRA = "http://rdf.freebase.com/ns/m.synthetic99"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _facts(
    *,
    subject: str = URI_SUBJECT,
    rna: bool = False,
    dna: bool = False,
    modified: bool = False,
    aptamer: bool = True,
    secondary: bool = False,
    predicted: bool = False,
    modification_literal: bool = False,
) -> AptamerBaseRdfSubjectFacts:
    types: set[str] = set()
    if aptamer:
        types.add(TYPE_APTAMER)
    if rna:
        types.add(URI_RNA)
    if dna:
        types.add(URI_DNA)
    if modified:
        types.add(URI_MOD)
    if secondary:
        types.add(TYPE_SECONDARY_STRUCTURE)
    if predicted:
        types.add(TYPE_PREDICTED_STRUCTURE)
    frozen = frozenset(types)
    return AptamerBaseRdfSubjectFacts(
        subject_uri=subject,
        rdf_type_objects=frozen,
        freebase_type_objects=frozen,
        union_types=frozen,
        has_rna=rna,
        has_dna=dna,
        has_aptamer=aptamer,
        has_nucleic_acid=False,
        has_linear_polymer=False,
        has_modified_nucleic_acid=modified,
        has_minimal_aptamer=False,
        has_secondary_structure=secondary,
        has_predicted_secondary_structure=predicted,
        has_modification_details_literal=modification_literal,
    )


def _meta(*, native_id: str = "0001", **overrides: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row["record_id"] = f"aptamerbase:{native_id}"
    row["native_id"] = native_id
    row["aptamerbase_csv_data_row"] = str(int(native_id))
    row["aptamerbase_type"] = TYPE_APTAMER
    row["aptamerbase_id"] = URI_SUBJECT
    row["aptamerbase_sequence"] = "ACGUAC"
    row.update(overrides)
    return row


def _s1(*, native_id: str = "0001", **overrides: str) -> dict[str, str]:
    record = empty_corpus_record()
    record.update(
        {
            "record_id": f"aptamerbase:{native_id}",
            "sequence_raw": "ACGUAC",
            "source_db": "aptamerbase",
            "source_dataset": "aptamerbase_export_2026-06-24",
            "contributing_sources": "aptamerbase",
            "contributing_datasets": "aptamerbase_export_2026-06-24",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "target_name_raw": "",
            "notes": "{}",
        }
    )
    record.update(overrides)
    return record


def _write_nt_gz(path: Path, triples: list[tuple[str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for subject, predicate, obj in triples:
            if obj.startswith("http://") or obj.startswith("https://"):
                handle.write(f"<{subject}>\t<{predicate}>\t<{obj}> .\n")
            else:
                escaped = obj.replace("\\", "\\\\").replace('"', '\\"')
                handle.write(f'<{subject}>\t<{predicate}>\t"{escaped}"@en .\n')


def _typed_subject(subject: str, *type_uris: str) -> list[tuple[str, str, str]]:
    triples: list[tuple[str, str, str]] = []
    for uri in type_uris:
        triples.append((subject, RDF_TYPE, uri))
        triples.append((subject, FB_TYPE, uri))
    return triples


def _write_inputs(
    input_dir: Path,
    canonical_rows: list[dict[str, str]],
    sidecar_rows: list[dict[str, str]],
) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    with (input_dir / "aptamerbase_extracted.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(CORPUS_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for row in canonical_rows:
            writer.writerow({col: row.get(col, "") for col in CORPUS_COLUMNS})
    with (input_dir / "aptamerbase_source_metadata.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(SIDECAR_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for row in sidecar_rows:
            writer.writerow({col: row.get(col, "") for col in SIDECAR_COLUMNS})


def _runner_tree(
    tmp_path: Path,
    canonical_rows: list[dict[str, str]],
    sidecar_rows: list[dict[str, str]],
    rdf_triples: list[tuple[str, str, str]],
) -> tuple[Path, Path, Path]:
    repo_root = tmp_path / "repo"
    input_dir = repo_root / "data" / "interim" / "extracted"
    output_dir = repo_root / "data" / "interim" / "normalised"
    _write_inputs(input_dir, canonical_rows, sidecar_rows)
    _write_nt_gz(
        repo_root / "data" / "raw" / "aptamerbase" / "aptamerbase.freebase.extract.nt.gz",
        rdf_triples,
    )
    return repo_root, input_dir, output_dir


@pytest.fixture(scope="module")
def policy():
    return load_aptamerbase_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def rules():
    return load_normalisation_rules()


def _literal_of_class(policy, chem_class: str) -> str:
    for literal, mapped in policy.chemistry_literals.items():
        if mapped == chem_class:
            return literal
    raise AssertionError(f"no policy literal for class {chem_class}")


def test_policy_disables_grouping_and_trims(policy) -> None:
    assert policy.source_key == "aptamerbase"
    assert policy.group_inference_key == GROUP_INFERENCE_DISABLED
    assert policy.apply_approved_trims is False
    assert policy.do_not_infer_molecule_from_alphabet is True
    assert policy.approved_trims == ()


def test_grouping_mode_other_than_disabled_hard_fails(tmp_path: Path) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["group_inference_key"] = "label_prefix"
    path = tmp_path / "bad_policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AptamerBaseS2Error, match="disabled"):
        load_aptamerbase_policy(path)


# --- RDF join / type ---


def test_01_explicit_rna_source_type_molecule_rna(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(),
        _meta(),
        _facts(rna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.qc["molecule_evidence_source"] == "rdf_type"


def test_02_explicit_dna_source_type_molecule_ssdna(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(aptamerbase_sequence="ACGTAC"),
        _facts(dna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "ssDNA"


def test_03_rna_dna_conflict_unknown_and_flag(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(),
        _meta(),
        _facts(rna=True, dna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "unknown"
    assert "source_molecule_type_conflict" in result.canonical["qc_flags"]


def test_04_unresolved_aptamer_unknown(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(),
        _meta(),
        _facts(rna=False, dna=False),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "unknown"
    assert "molecule_type_unknown" in result.canonical["qc_flags"]
    assert "chemistry_requires_review" not in result.canonical["qc_flags"]


def test_05_structure_topic_overrides_incidental_rna(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(aptamerbase_type=TYPE_PREDICTED_STRUCTURE),
        _facts(rna=True, predicted=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "unknown"
    assert result.canonical["chemistry"] == "unknown"
    assert "non_aptamer_structure_topic" in result.canonical["qc_flags"]
    assert "chemistry_requires_review" not in result.canonical["qc_flags"]
    assert result.qc["source_object_type"] == "predicted_secondary_structure"


def test_06_missing_rdf_subject_fails_closed(policy, tmp_path: Path) -> None:
    rdf_path = tmp_path / "only_other.nt.gz"
    _write_nt_gz(rdf_path, _typed_subject(URI_EXTRA, TYPE_APTAMER, URI_RNA))
    index = load_aptamerbase_rdf_index(
        rdf_path,
        rdf_type_predicate=policy.rdf_type_predicate,
        freebase_type_predicate=policy.freebase_type_predicate,
        modification_details_predicate=policy.modification_details_predicate,
        type_uris=policy.rdf_type_uris,
    )
    with pytest.raises(AptamerBaseRdfError, match="absent"):
        require_subject_facts(index, URI_SUBJECT)


def test_07_repeated_source_id_gets_identical_metadata(policy, rules) -> None:
    facts = _facts(rna=True)
    first = normalise_aptamerbase_record(
        _s1(native_id="0001"),
        _meta(native_id="0001"),
        facts,
        policy=policy,
        rules=rules,
    )
    second = normalise_aptamerbase_record(
        _s1(native_id="0002", sequence_raw="ACGUAC"),
        _meta(native_id="0002", aptamerbase_sequence="ACGUAC"),
        facts,
        policy=policy,
        rules=rules,
    )
    assert first.rdf_molecule_type == second.rdf_molecule_type == "RNA"
    assert first.canonical["molecule_type"] == second.canonical["molecule_type"]
    assert first.qc["rdf_has_rna"] == second.qc["rdf_has_rna"] == "true"


def test_08_rdf_cannot_generate_additional_canonical_records(tmp_path: Path) -> None:
    canonical = [_s1(native_id="0001"), _s1(native_id="0002")]
    sidecar = [
        _meta(native_id="0001"),
        _meta(native_id="0002", aptamerbase_id=URI_SUBJECT_B),
    ]
    triples = (
        _typed_subject(URI_SUBJECT, TYPE_APTAMER, URI_RNA)
        + _typed_subject(URI_SUBJECT_B, TYPE_APTAMER, URI_DNA)
        + _typed_subject(URI_EXTRA, TYPE_APTAMER, URI_RNA)
    )
    repo_root, input_dir, output_dir = _runner_tree(
        tmp_path, canonical, sidecar, triples
    )
    result = run_aptamerbase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    assert result.stats.s1_rows == 2
    assert result.stats.s2_rows == 2
    assert result.stats.unique_record_ids == 2
    rows = list(csv.DictReader(result.output_normalised.open(encoding="utf-8")))
    assert [row["record_id"] for row in rows] == [
        "aptamerbase:0001",
        "aptamerbase:0002",
    ]


# --- Alphabet / transcription ---


def test_09_rna_plus_t_alphabet_transcribes(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(aptamerbase_sequence="ACGTAC"),
        _facts(rna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["alphabet_as_reported"] == "DNA_T"
    assert result.canonical["t_to_u_applied"] == "true"
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert result.canonical["sequence_raw"] == "ACGTAC"


def test_10_dna_plus_t_alphabet_no_transcription(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(aptamerbase_sequence="ACGTAC"),
        _facts(dna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "ssDNA"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGTAC"


def test_11_dna_plus_u_alphabet_conflict_no_transcription(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(aptamerbase_sequence="ACGUAC"),
        _facts(dna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "ssDNA"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert "source_molecule_alphabet_conflict" in result.canonical["qc_flags"]


def test_12_unresolved_plus_u_remains_unknown(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(),
        _facts(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "unknown"
    assert result.canonical["t_to_u_applied"] == "false"


def test_13_unresolved_plus_t_remains_unknown(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(aptamerbase_sequence="ACGTAC"),
        _facts(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "unknown"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGTAC"


def test_14_acg_only_plus_rdf_rna_resolves_rna_alphabet(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGACG"),
        _meta(aptamerbase_sequence="ACGACG"),
        _facts(rna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["alphabet_as_reported"] == "RNA"


def test_15_acg_only_plus_rdf_dna_resolves_dna_alphabet(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGACG"),
        _meta(aptamerbase_sequence="ACGACG"),
        _facts(dna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "ssDNA"
    assert result.canonical["alphabet_as_reported"] == "DNA_T"


def test_16_mixed_t_u_retains_explicit_molecule_and_qc(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGTU"),
        _meta(aptamerbase_sequence="ACGTU"),
        _facts(rna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGTU"
    assert "mixed_t_u" in result.canonical["qc_flags"]


def test_17_ambiguous_invalid_retain_explicit_molecule(policy, rules) -> None:
    ambiguous = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGNAC"),
        _meta(aptamerbase_sequence="ACGNAC"),
        _facts(rna=True),
        policy=policy,
        rules=rules,
    )
    assert ambiguous.canonical["molecule_type"] == "RNA"
    assert "ambiguous_base" in ambiguous.canonical["qc_flags"]
    invalid = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGXac"),
        _meta(aptamerbase_sequence="ACGXac"),
        _facts(dna=True),
        policy=policy,
        rules=rules,
    )
    assert invalid.canonical["molecule_type"] == "ssDNA"
    assert "invalid_character" in invalid.canonical["qc_flags"]
    assert invalid.canonical["t_to_u_applied"] == "false"


# --- Chemistry ---


def test_18_unmodified_rdf_rna_chemistry_rna(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(),
        _meta(),
        _facts(rna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["chemistry"] == "RNA"


def test_19_unmodified_rdf_dna_chemistry_dna(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(aptamerbase_sequence="ACGTAC"),
        _facts(dna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["chemistry"] == "DNA"


def test_20_allowlisted_twof_only_rna_maps_2f(policy, rules) -> None:
    literal = _literal_of_class(policy, "twof_rna")
    result = normalise_aptamerbase_record(
        _s1(),
        _meta(aptamerbase_has_modification_details=literal),
        _facts(rna=True, modified=True, modification_literal=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "2F-RNA"


def test_21_terminal_conjugate_does_not_change_backbone(policy, rules) -> None:
    literal = _literal_of_class(policy, "terminal_conjugate")
    rna = normalise_aptamerbase_record(
        _s1(),
        _meta(aptamerbase_has_modification_details=literal),
        _facts(rna=True),
        policy=policy,
        rules=rules,
    )
    dna = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(
            aptamerbase_sequence="ACGTAC",
            aptamerbase_has_modification_details=literal,
        ),
        _facts(dna=True),
        policy=policy,
        rules=rules,
    )
    assert rna.canonical["chemistry"] == "RNA"
    assert dna.canonical["chemistry"] == "DNA"
    assert "terminal_conjugate_present" in rna.canonical["qc_flags"]


def test_22_twof_plus_terminal_conjugate_remains_2f(policy, rules) -> None:
    twof = _literal_of_class(policy, "twof_rna")
    conjugate = _literal_of_class(policy, "terminal_conjugate")
    composed = f"{twof}; {conjugate}"
    result = normalise_aptamerbase_record(
        _s1(),
        _meta(aptamerbase_has_modification_details=composed),
        _facts(rna=True, modified=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["chemistry"] == "2F-RNA"
    assert "terminal_conjugate_present" in result.canonical["qc_flags"]


def test_23_spiegelmer_keeps_rna_molecule_unknown_chemistry(policy, rules) -> None:
    literal = _literal_of_class(policy, "spiegelmer_l_rna")
    result = normalise_aptamerbase_record(
        _s1(),
        _meta(aptamerbase_has_modification_details=literal),
        _facts(rna=True, modified=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "unknown"
    assert "spiegelmer_l_rna_review" in result.canonical["qc_flags"]
    assert "chemistry_requires_review" in result.canonical["qc_flags"]


def test_24_ome_mixed_unusual_chemistry_review(policy, rules) -> None:
    literal = _literal_of_class(policy, "ome_or_mixed_sugar")
    result = normalise_aptamerbase_record(
        _s1(),
        _meta(aptamerbase_has_modification_details=literal),
        _facts(rna=True, modified=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["chemistry"] == "unknown"
    assert "chemistry_requires_review" in result.canonical["qc_flags"]


def test_25_dna_plus_twof_like_modification_review(policy, rules) -> None:
    literal = _literal_of_class(policy, "twof_rna")
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(
            aptamerbase_sequence="ACGTAC",
            aptamerbase_has_modification_details=literal,
        ),
        _facts(dna=True, modified=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "ssDNA"
    assert result.canonical["chemistry"] == "unknown"
    assert "dna_twof_like_modification_review" in result.canonical["qc_flags"]


def test_26_modification_text_type_inconsistency_flagged(policy, rules) -> None:
    missing_text = normalise_aptamerbase_record(
        _s1(),
        _meta(),
        _facts(rna=True, modified=True),
        policy=policy,
        rules=rules,
    )
    assert "rdf_modified_type_without_modification_text" in missing_text.canonical[
        "qc_flags"
    ]
    extra_text = normalise_aptamerbase_record(
        _s1(),
        _meta(aptamerbase_has_modification_details=_literal_of_class(policy, "twof_rna")),
        _facts(rna=True, modified=False),
        policy=policy,
        rules=rules,
    )
    assert "modification_text_without_rdf_modified_type" in extra_text.canonical[
        "qc_flags"
    ]


# --- Object / constant ---


def test_27_structure_topic_retained(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(aptamerbase_type=TYPE_SECONDARY_STRUCTURE),
        _facts(secondary=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["record_id"] == "aptamerbase:0001"
    assert result.canonical["molecule_type"] == "unknown"
    assert "non_aptamer_structure_topic" in result.canonical["qc_flags"]


def test_28_no_group_wise_constant_inference_occurs(tmp_path: Path) -> None:
    canonical = [_s1(native_id="0001"), _s1(native_id="0002")]
    sidecar = [_meta(native_id="0001"), _meta(native_id="0002")]
    triples = _typed_subject(URI_SUBJECT, TYPE_APTAMER, URI_RNA)
    repo_root, input_dir, output_dir = _runner_tree(
        tmp_path, canonical, sidecar, triples
    )
    result = run_aptamerbase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    assert result.stats.groups_considered == 0
    proposals = list(csv.DictReader(result.output_proposals.open(encoding="utf-8")))
    assert all(row["proposal_source"] != "group_consensus" for row in proposals)
    import adapters.aptamerbase_s2 as mod

    assert not hasattr(mod, "infer_group_constant_regions")


def test_29_known_motif_detection_never_auto_trims(policy, rules) -> None:
    motif = "TAATACGACTCACTATA"
    result = normalise_aptamerbase_record(
        _s1(sequence_raw=motif),
        _meta(aptamerbase_sequence=motif),
        _facts(rna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["detected_constant_5p"]
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.canonical["t_to_u_applied"] == "true"
    assert "trim_requires_review" in result.canonical["qc_flags"]


def test_30_sequence_core_equals_sequence_full_no_approved_trim(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(aptamerbase_sequence="ACGTAC"),
        _facts(rna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.canonical["trim_confidence"] == "n/a"


# --- Stage boundary ---


def test_31_target_evidence_pdb_affinity_remain_empty(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(),
        _meta(),
        _facts(rna=True),
        policy=policy,
        rules=rules,
    )
    for field in S2_FORBIDDEN_FIELDS:
        assert result.canonical[field] == ""
    assert result.canonical["target_name_raw"] == ""


def test_32_no_records_dropped(tmp_path: Path) -> None:
    canonical = [
        _s1(native_id="0001", sequence_raw=""),
        _s1(native_id="0002", sequence_raw="n/a"),
        _s1(native_id="0003"),
    ]
    sidecar = [
        _meta(native_id="0001", aptamerbase_sequence=""),
        _meta(native_id="0002", aptamerbase_sequence="n/a"),
        _meta(native_id="0003"),
    ]
    triples = _typed_subject(URI_SUBJECT, TYPE_APTAMER, URI_RNA)
    repo_root, input_dir, output_dir = _runner_tree(
        tmp_path, canonical, sidecar, triples
    )
    result = run_aptamerbase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=3,
    )
    assert result.stats.s2_rows == 3
    assert result.stats.records_dropped == 0
    assert result.stats.records_parked == 0
    assert result.stats.missing_sequence_rows == 2


def test_33_no_deduplication(tmp_path: Path) -> None:
    canonical = [
        _s1(native_id="0001"),
        _s1(native_id="0002"),
        _s1(native_id="0003"),
    ]
    sidecar = [
        _meta(native_id="0001"),
        _meta(native_id="0002"),
        _meta(native_id="0003"),
    ]
    triples = _typed_subject(URI_SUBJECT, TYPE_APTAMER, URI_RNA)
    repo_root, input_dir, output_dir = _runner_tree(
        tmp_path, canonical, sidecar, triples
    )
    result = run_aptamerbase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=3,
    )
    rows = list(csv.DictReader(result.output_normalised.open(encoding="utf-8")))
    assert len(rows) == 3
    assert [row["record_id"] for row in rows] == [
        "aptamerbase:0001",
        "aptamerbase:0002",
        "aptamerbase:0003",
    ]
    assert result.stats.unique_freebase_ids == 1


def test_34_deterministic_rerun(tmp_path: Path) -> None:
    canonical = [_s1(native_id="0001"), _s1(native_id="0002", sequence_raw="ACGTAC")]
    sidecar = [
        _meta(native_id="0001"),
        _meta(native_id="0002", aptamerbase_sequence="ACGTAC"),
    ]
    triples = _typed_subject(URI_SUBJECT, TYPE_APTAMER, URI_RNA)
    repo_root, input_dir, output_dir = _runner_tree(
        tmp_path, canonical, sidecar, triples
    )
    result = run_aptamerbase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
        check_deterministic_rerun=True,
    )
    assert result.deterministic_rerun_ok is True
    assert result.inputs_unchanged is True


def test_dispatcher_recognises_aptamerbase(tmp_path: Path) -> None:
    canonical = [_s1()]
    sidecar = [_meta()]
    triples = _typed_subject(URI_SUBJECT, TYPE_APTAMER, URI_RNA)
    repo_root, input_dir, output_dir = _runner_tree(
        tmp_path, canonical, sidecar, triples
    )
    result = run_s2_normalisation(
        repo_root=repo_root,
        source_key="aptamerbase",
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        source_policy=POLICY_PATH,
        expected_rows=1,
    )
    assert result.source_key == "aptamerbase"
    assert result.stats.s2_rows == 1


def test_textual_null_n_a_becomes_missing_without_changing_raw(policy, rules) -> None:
    result = normalise_aptamerbase_record(
        _s1(sequence_raw="n/a"),
        _meta(aptamerbase_sequence="n/a"),
        _facts(rna=True),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == "n/a"
    assert result.canonical["sequence_full"] == ""
    assert result.canonical["alphabet_as_reported"] == "missing"
    assert result.canonical["molecule_type"] == "RNA"


def test_twof_synonym_classes_in_closed_allowlist(policy) -> None:
    classes = set(policy.chemistry_literals.values())
    assert "twof_rna" in classes
    twof_literals = [
        literal
        for literal, mapped in policy.chemistry_literals.items()
        if mapped == "twof_rna"
    ]
    assert len(twof_literals) >= 8
    for literal in twof_literals:
        chem_class, _extras = classify_modification(literal, policy)
        assert chem_class == "twof_rna"


def test_parse_ntriples_literal_and_uri() -> None:
    uri_line = (
        f"<{URI_SUBJECT}>\t<{RDF_TYPE}>\t<{URI_RNA}> .\n"
    )
    parsed = parse_ntriples_line(uri_line)
    assert parsed == (URI_SUBJECT, RDF_TYPE, "uri", URI_RNA)
    lit_line = (
        f'<{URI_SUBJECT}>\t<{FB_TYPE}>\t"demo token"@en .\n'
    )
    parsed_lit = parse_ntriples_line(lit_line)
    assert parsed_lit is not None
    assert parsed_lit[2] == "literal"
    assert parsed_lit[3] == "demo token"


def test_s1_and_raw_untouched_by_synthetic_runner(tmp_path: Path) -> None:
    canonical = [_s1()]
    sidecar = [_meta()]
    triples = _typed_subject(URI_SUBJECT, TYPE_APTAMER, URI_RNA)
    repo_root, input_dir, output_dir = _runner_tree(
        tmp_path, canonical, sidecar, triples
    )
    c_path = input_dir / "aptamerbase_extracted.csv"
    s_path = input_dir / "aptamerbase_source_metadata.csv"
    before_c = _sha256(c_path)
    before_s = _sha256(s_path)
    run_aptamerbase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=1,
    )
    assert _sha256(c_path) == before_c
    assert _sha256(s_path) == before_s


@pytest.mark.skipif(
    not PRODUCTION_S1.is_file() or not PRODUCTION_RDF.is_file(),
    reason="production AptamerBase S1/RDF not present",
)
def test_production_counts_without_embedding_sequences() -> None:
    result = run_aptamerbase_s2(
        repo_root=REPO_ROOT,
        input_dir=PRODUCTION_S1.parent,
        output_dir=REPO_ROOT / "data" / "interim" / "normalised",
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2128,
    )
    assert result.stats.s1_rows == 2128
    assert result.stats.s2_rows == 2128
    assert result.stats.unique_record_ids == 2128
    assert result.stats.unique_freebase_ids == 1868
    assert result.stats.records_dropped == 0
    assert result.stats.applied_trims == 0
    assert result.stats.core_differs_from_full == 0
    assert result.inputs_unchanged is True
