"""Synthetic tests for affinity parsing and unit conversion."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_affinity import parse_affinity_from_text, parse_affinity_value  # noqa: E402


def test_unit_conversions() -> None:
    cases = [
        ("1", "pM", 1e-12),
        ("1", "nM", 1e-9),
        ("1", "uM", 1e-6),
        ("1", "µM", 1e-6),
        ("1", "mM", 1e-3),
        ("1", "M", 1.0),
    ]
    for value, unit, expected in cases:
        parsed = parse_affinity_value(value, unit=unit, affinity_type="Kd")
        assert parsed["affinity_parse_status"] == "normalised"
        assert abs(float(parsed["affinity_value_molar_proposed"]) - expected) < 1e-18


def test_type_retention() -> None:
    assert parse_affinity_value("2", unit="nM", affinity_type="Kd")["affinity_type_proposed"] == "Kd"
    assert parse_affinity_value("2", unit="nM", affinity_type="Ka")["affinity_type_proposed"] == "Ka"
    assert parse_affinity_value("2", unit="nM", affinity_type="IC50")["affinity_type_proposed"] == "IC50"
    assert parse_affinity_value("2", unit="nM", affinity_type="EC50")["affinity_type_proposed"] == "EC50"
    kd_text = parse_affinity_from_text("Kd: 5 nM")
    assert kd_text["affinity_type_proposed"] == "Kd"
    assert kd_text["affinity_parse_status"] == "normalised"


def test_range_not_converted_to_scalar() -> None:
    parsed = parse_affinity_value("22.25-24.74", unit="nM", affinity_type="Kd")
    assert parsed["affinity_value_molar_proposed"] == ""
    assert parsed["affinity_parse_status"] == "range_or_multiple"


def test_inequality_not_converted_to_scalar() -> None:
    parsed = parse_affinity_value("<1.0", unit="pM", affinity_type="Kd")
    assert parsed["affinity_value_molar_proposed"] == ""
    assert parsed["affinity_parse_status"] == "inequality"


def test_malformed_safely_unresolved() -> None:
    parsed = parse_affinity_value("notanumber", unit="nM", affinity_type="Kd")
    assert parsed["affinity_parse_status"] == "malformed"
    assert parsed["affinity_value_molar_proposed"] == ""
    assert parsed["affinity_requires_review"] == "true"


def test_scientific_notation_hyphen_is_not_a_range() -> None:
    parsed = parse_affinity_from_text("Kd: 2 x 10^-5 M")
    assert parsed["affinity_parse_status"] == "normalised"
    assert abs(float(parsed["affinity_value_molar_proposed"]) - 2e-5) < 1e-18
    e_notation = parse_affinity_value("2e-5", unit="M", affinity_type="Kd")
    assert e_notation["affinity_parse_status"] == "normalised"
    assert abs(float(e_notation["affinity_value_molar_proposed"]) - 2e-5) < 1e-18
    inequality = parse_affinity_value(">30E-06", unit="M", affinity_type="Kd")
    assert inequality["affinity_parse_status"] == "inequality"
    assert inequality["affinity_value_molar_proposed"] == ""


def test_glued_nanomolar_unit() -> None:
    parsed = parse_affinity_from_text("Kd: 50nM")
    assert parsed["affinity_parse_status"] == "normalised"
    assert abs(float(parsed["affinity_value_molar_proposed"]) - 5e-8) < 1e-18


def test_uncertainty_after_unit_uses_central_value() -> None:
    parsed = parse_affinity_from_text("Kd: 78.2 nM±2.6 nM")
    assert parsed["affinity_parse_status"] == "normalised"
    assert abs(float(parsed["affinity_value_molar_proposed"]) - 7.82e-8) < 1e-18


def test_explicit_missing_kd_na() -> None:
    parsed = parse_affinity_from_text("Kd: NA")
    assert parsed["affinity_parse_status"] == "absent"
    assert parsed["affinity_value_molar_proposed"] == ""
    assert parsed["affinity_requires_review"] == "false"
