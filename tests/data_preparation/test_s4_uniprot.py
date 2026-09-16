"""Synthetic tests for UniProt proposal resolution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_uniprot import (  # noqa: E402
    build_local_uniprot_index,
    cache_path,
    resolve_uniprot,
    write_cache,
)


def test_aptadb_source_seed_is_u1() -> None:
    result = resolve_uniprot(
        raw_target="Prothrombin",
        source_uniprot_seed="P00734",
        target_type="protein",
    )
    assert result["uniprot_proposed"] == "P00734"
    assert result["uniprot_resolution_tier"] == "U1_source_linked"


def test_conflicting_uniprot_ids_never_auto_merged() -> None:
    result = resolve_uniprot(
        raw_target="Prothrombin",
        source_uniprot_seed="P00734|P00735",
        target_type="protein",
    )
    assert result["uniprot_proposed"] == ""
    assert "P00734" in result["uniprot_candidates"]
    assert "P00735" in result["uniprot_candidates"]
    assert result["uniprot_requires_review"] == "true"


def test_unique_local_mapping() -> None:
    index = build_local_uniprot_index(
        [
            {
                "Uni-port ID": "P01308",
                "Protein names": "Insulin",
                "Entry name": "INS_HUMAN",
                "Gene names": "INS",
                "Organism": "Homo sapiens",
            }
        ]
    )
    result = resolve_uniprot(
        raw_target="Insulin",
        source_uniprot_seed="",
        target_type="protein",
        local_index=index,
    )
    assert result["uniprot_proposed"] == "P01308"
    assert result["uniprot_resolution_tier"] == "U2_local_structured"


def test_multiple_candidate_refusal() -> None:
    index = build_local_uniprot_index(
        [
            {
                "Uni-port ID": "P00734",
                "Protein names": "Prothrombin",
                "Entry name": "THRB_HUMAN",
                "Gene names": "F2",
                "Organism": "Homo sapiens",
            },
            {
                "Uni-port ID": "P00735",
                "Protein names": "Prothrombin",
                "Entry name": "THRB_BOVIN",
                "Gene names": "F2",
                "Organism": "Bos taurus",
            },
        ]
    )
    result = resolve_uniprot(
        raw_target="Prothrombin",
        source_uniprot_seed="",
        target_type="protein",
        local_index=index,
    )
    assert result["uniprot_proposed"] == ""
    assert result["uniprot_requires_review"] == "true"
    assert "P00734" in result["uniprot_candidates"]


def test_network_cache_is_deterministic(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    query_name = "SyntheticCacheProtein"
    payload = {
        "query": f'protein_name:"{query_name}"',
        "results": [
            {
                "primaryAccession": "P99999",
                "proteinDescription": {
                    "recommendedName": {"fullName": {"value": query_name}}
                },
            }
        ],
        "error": "",
    }
    write_cache(cache_dir, f'protein_name:"{query_name}"', payload)
    first = resolve_uniprot(
        raw_target=query_name,
        source_uniprot_seed="",
        target_type="protein",
        cache_dir=cache_dir,
        api_base="https://rest.uniprot.org/uniprotkb/search",
        api_version="uniprotkb-v2",
        allow_network=False,
    )
    second = resolve_uniprot(
        raw_target=query_name,
        source_uniprot_seed="",
        target_type="protein",
        cache_dir=cache_dir,
        api_base="https://rest.uniprot.org/uniprotkb/search",
        api_version="uniprotkb-v2",
        allow_network=False,
    )
    assert first == second
    assert first["uniprot_proposed"] == "P99999"
    assert cache_path(cache_dir, f'protein_name:"{query_name}"').is_file()


def test_non_protein_skips_uniprot() -> None:
    result = resolve_uniprot(
        raw_target="theophylline",
        source_uniprot_seed="P00734",
        target_type="small_molecule",
    )
    assert result["uniprot_proposed"] == ""
    assert result["uniprot_resolution_tier"] == ""
