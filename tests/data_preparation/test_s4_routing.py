"""Routing precedence for machine preview and CHECKPOINT-2 application."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_routing import routing_preview  # noqa: E402


def test_leakage_precedes_everything() -> None:
    route, reason = routing_preview(
        relationship_status="resolved_single",
        target_type="protein",
        evidence_level="E2",
        evidence_ambiguous=False,
        leakage_proposed=True,
        no_binding=True,
        relationship_parked=True,
        target_parked=True,
    )
    assert route == "leakage_exclusion_proposed"
    assert reason == "leakage_match"


def test_relationship_park_uses_existing_vocab() -> None:
    route, reason = routing_preview(
        relationship_status="resolved_multiple",
        target_type="protein",
        evidence_level="E2",
        evidence_ambiguous=False,
        leakage_proposed=False,
        no_binding=False,
        relationship_parked=True,
    )
    assert route == "hold_target_unresolved"
    assert reason == "relationship_park_unresolved"


def test_target_park_is_not_primary() -> None:
    route, reason = routing_preview(
        relationship_status="resolved_single",
        target_type="protein",
        evidence_level="E2",
        evidence_ambiguous=False,
        leakage_proposed=False,
        no_binding=False,
        target_parked=True,
    )
    assert route == "hold_target_unresolved"
    assert reason == "target_park_unresolved"


def test_no_binding_rejects_usable_protein_metadata() -> None:
    route, reason = routing_preview(
        relationship_status="resolved_single",
        target_type="protein",
        evidence_level="E5",
        evidence_ambiguous=False,
        leakage_proposed=False,
        no_binding=True,
    )
    assert route == "reject_no_binding_evidence"
    assert reason == "no_defensible_binding_evidence"


def test_e5_parks_and_cannot_be_primary() -> None:
    route, reason = routing_preview(
        relationship_status="resolved_single",
        target_type="protein",
        evidence_level="E5",
        evidence_ambiguous=False,
        leakage_proposed=False,
        no_binding=False,
    )
    assert route == "park_evidence_e5"


def test_non_protein_parks() -> None:
    route, reason = routing_preview(
        relationship_status="resolved_single",
        target_type="small_molecule",
        evidence_level="E2",
        evidence_ambiguous=False,
        leakage_proposed=False,
        no_binding=False,
    )
    assert route == "park_non_protein"
    assert "small_molecule" in reason


def test_protein_e4_is_primary() -> None:
    route, reason = routing_preview(
        relationship_status="resolved_single",
        target_type="protein",
        evidence_level="E4",
        evidence_ambiguous=False,
        leakage_proposed=False,
        no_binding=False,
    )
    assert route == "primary_candidate"
    assert reason == "protein_E4"
