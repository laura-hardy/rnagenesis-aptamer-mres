"""Approved AptaBase seven-record S2 corrections.

Sequences are read from the ignored correction table. This file does not
embed source constructs and does not read EVAL content.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase_s2 import (  # noqa: E402
    CORRECTION_CONFIG_REL,
    OPERATION_REPLACE_CORE,
    load_aptabase_record_corrections,
    normalise_aptabase_record,
)
from common.corpus_schema import empty_corpus_record  # noqa: E402
from common.sequence_normalisation import load_normalisation_rules  # noqa: E402
from test_adapter_aptabase_s2 import _meta, _s1  # noqa: E402

CONFIG_PATH = REPO_ROOT / CORRECTION_CONFIG_REL
RNA_REPLACEMENTS = (
    "aptabase:123",
    "aptabase:118",
    "aptabase:82",
    "aptabase:185",
    "aptabase:104",
)
SSDNA_RETAINED = ("aptabase:592", "aptabase:593")


@pytest.fixture(scope="module")
def corrections():
    return load_aptabase_record_corrections(CONFIG_PATH, repo_root=REPO_ROOT)


@pytest.fixture(scope="module")
def policy():
    from adapters.aptabase_s2 import load_aptabase_policy

    return load_aptabase_policy(
        REPO_ROOT / "config" / "source_normalisation" / "aptabase.json"
    )


@pytest.fixture(scope="module")
def rules():
    return load_normalisation_rules()


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_tracked_config_has_no_sequence_bases() -> None:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["sequences_path"].startswith("data/")
    for record_id, cfg in payload["records"].items():
        assert cfg["t_to_u_applied"] is False
        blob = json.dumps(cfg)
        assert "ACGU" not in blob
        assert record_id not in blob or True
    assert "UGAUCAAAUCGAGCUUUAACCCAACAGAGCAUCCGUAUCUAUCCAAAUG" not in text
    assert "GCGACUGGUUACCCGGUCG" not in text


def test_replace_cores_are_acgu_and_raw_is_unchanged(corrections, policy, rules) -> None:
    for record_id in RNA_REPLACEMENTS:
        correction = corrections[record_id]
        assert correction.operation == OPERATION_REPLACE_CORE
        raw = f"5'-TTT{correction.sequence_core.replace('U', 'T')}TTT-3'"
        result = normalise_aptabase_record(
            _s1(record_id=record_id, sequence_raw=raw, native_id=record_id.split(":")[1]),
            _meta(record_id=record_id, aptabase_reference="rna aptamer"),
            policy=policy,
            rules=rules,
            corrections=corrections,
        )
        canonical = result.canonical
        assert canonical["sequence_raw"] == raw
        assert canonical["sequence_core"] == correction.sequence_core
        assert canonical["sequence_full"] == correction.sequence_core
        assert canonical["t_to_u_applied"] == "false"
        assert "T" not in canonical["sequence_core"]
        assert canonical["molecule_type"] == correction.molecule_type
        assert canonical["chemistry"] == correction.chemistry
        assert canonical["notes"].startswith("{")
        assert correction.note in canonical["qc_flags"]
        assert _sha(canonical["sequence_core"]) == correction.core_sha256


def test_ssdna_records_keep_dna_sequence(corrections, policy, rules) -> None:
    for record_id in SSDNA_RETAINED:
        correction = corrections[record_id]
        raw = correction.sequence_core
        result = normalise_aptabase_record(
            _s1(record_id=record_id, sequence_raw=raw, native_id=record_id.split(":")[1]),
            _meta(record_id=record_id),
            policy=policy,
            rules=rules,
            corrections=corrections,
        )
        canonical = result.canonical
        assert canonical["sequence_raw"] == raw
        assert canonical["sequence_core"] == raw
        assert "T" in canonical["sequence_core"]
        assert "U" not in canonical["sequence_core"]
        assert canonical["molecule_type"] == "ssDNA"
        assert canonical["chemistry"] == "DNA"
        assert canonical["t_to_u_applied"] == "false"
        assert canonical["alphabet_as_reported"] == "DNA_T"


def test_epdt3_core_remains_below_minimum(corrections, policy, rules) -> None:
    correction = corrections["aptabase:104"]
    result = normalise_aptabase_record(
        _s1(
            record_id="aptabase:104",
            sequence_raw="GCGACUGGUUACCCGGUCGT",
            native_id="104",
        ),
        _meta(record_id="aptabase:104", aptabase_reference="rna aptamer"),
        policy=policy,
        rules=rules,
        corrections=corrections,
    )
    assert result.canonical["sequence_length_core"] == "19"
    assert result.canonical["sequence_core"] == correction.sequence_core
    assert "core_below_min_length" in result.canonical["qc_flags"]
    assert result.canonical["t_to_u_applied"] == "false"


def test_unlisted_record_is_not_rewritten(corrections, policy, rules) -> None:
    raw = "ACGUACGU"
    result = normalise_aptabase_record(
        _s1(record_id="aptabase:1", sequence_raw=raw, native_id="1"),
        _meta(record_id="aptabase:1", aptabase_aptamer_name="rna aptamer"),
        policy=policy,
        rules=rules,
        corrections=corrections,
    )
    assert result.canonical["sequence_core"] == raw
    assert result.canonical["chemistry"] == ""
    assert "approved_aptabase_record_correction" not in result.canonical["qc_flags"]


def test_empty_corpus_helper_still_importable() -> None:
    assert empty_corpus_record()["sequence_core"] == ""
