"""Traceable GenBank target extraction for authorised NCBI Nucleotide records."""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Mapping

from adapters.target_extraction_common import (
    RecordExtraction,
    TargetRelationship,
    apply_relationships,
    base_extraction,
    split_comma_entities,
)

BINDS_TO_RE = re.compile(
    r"(?is)aptamer(?:s)?\s+which binds to\s+(?P<target>.+?)\.?\s*$"
)
SPECIFIC_FOR_RE = re.compile(
    r"(?is)aptamer specific for\s+(?P<target>.+?)\.?\s*$"
)
X_BINDING_RE = re.compile(
    r"(?is)(?:synthetic\s+)?(?P<target>.+?)-binding RNA aptamer"
)
TARGETING_RE = re.compile(
    r"(?is)(?:RNA molecule|aptamer)\s+targeting\s+(?P<target>.+?)\.?\s*$"
)
FEATURE_BINDS_RE = re.compile(
    r"(?is)(?:specifically recognizes and binds to|binds to)\s+(?P<target>.+)"
)
AND_SPLIT_RE = re.compile(r"\s+and\s+", re.IGNORECASE)


def _parse_jsonish(raw: str) -> Any:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return None


def _qualifiers(feature: Mapping[str, Any]) -> dict[str, Any]:
    raw = feature.get("qualifiers")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        parsed = _parse_jsonish(raw)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _first_note(qualifiers: Mapping[str, Any]) -> str:
    note = qualifiers.get("note")
    if isinstance(note, list):
        return " ".join(str(item) for item in note if item)
    if note is None:
        return ""
    return str(note)


def _relationship(
    extraction: RecordExtraction,
    raw: str,
    *,
    field_name: str,
    locator: str,
    method: str,
    confidence: str,
    checkpoint2: bool = False,
    ambiguity: str = "",
) -> TargetRelationship:
    return TargetRelationship(
        record_id=extraction.record_id,
        source_db=extraction.source_db,
        raw_target=raw.strip(),
        target_provenance_source=field_name,
        target_provenance_locator=locator,
        relationship_confidence=confidence,
        requires_checkpoint2=checkpoint2,
        ambiguity_reason=ambiguity,
    )


def _multi_or_single(text: str) -> list[str]:
    parts = [item.strip(" .") for item in AND_SPLIT_RE.split(text) if item.strip(" .")]
    if len(parts) <= 1:
        comma_parts = split_comma_entities(text)
        if len(comma_parts) > 1:
            return [item.strip(" .") for item in comma_parts]
        return [text.strip(" .")]
    return parts


def extract_ncbi_nuc_record(row: Mapping[str, str]) -> RecordExtraction:
    """Extract NCBI targets only from explicit GenBank binding phrasing."""
    extraction = base_extraction(row)
    accession = (row.get("ncbi_nuc_accession") or "").strip()
    definition = (row.get("ncbi_nuc_definition") or "").strip()
    definition_one_line = re.sub(r"\s+", " ", definition)
    notes = [
        f"ncbi_nuc_accession={accession}",
        "organism_is_not_target=true",
        "title_alone_is_not_target=true",
    ]

    candidates: list[tuple[str, str, str, str]] = []
    binds = BINDS_TO_RE.search(definition_one_line)
    if binds:
        candidates.append(
            (
                binds.group("target").strip(" ."),
                "ncbi_nuc_definition",
                f"ncbi_nuc:{accession}|DEFINITION|BINDS_TO",
                "NCBI_DEF_BINDS_TO",
            )
        )
    specific = SPECIFIC_FOR_RE.search(definition_one_line)
    if specific:
        candidates.append(
            (
                specific.group("target").strip(" ."),
                "ncbi_nuc_definition",
                f"ncbi_nuc:{accession}|DEFINITION|SPECIFIC_FOR",
                "NCBI_DEF_SPECIFIC_FOR",
            )
        )
    binding = X_BINDING_RE.search(definition_one_line)
    if binding:
        candidates.append(
            (
                binding.group("target").strip(" ."),
                "ncbi_nuc_definition",
                f"ncbi_nuc:{accession}|DEFINITION|X_BINDING",
                "NCBI_DEF_X_BINDING",
            )
        )
    targeting = TARGETING_RE.search(definition_one_line)
    targeting_text = targeting.group("target").strip(" .") if targeting else ""

    features = _parse_jsonish(row.get("ncbi_nuc_features_json") or "")
    feature_targets: list[tuple[str, str, str, str]] = []
    if isinstance(features, list):
        for index, feature in enumerate(features):
            if not isinstance(feature, dict):
                continue
            feat_type = str(feature.get("type") or "")
            note = _first_note(_qualifiers(feature))
            note_one = re.sub(r"\s+", " ", note)
            match = FEATURE_BINDS_RE.search(note_one)
            if match is None:
                continue
            feature_targets.append(
                (
                    match.group("target").strip(" ."),
                    "ncbi_nuc_features_json",
                    (
                        f"ncbi_nuc:{accession}|FEATURES[{index}]"
                        f"|type={feat_type}|note"
                    ),
                    "NCBI_FEATURE_BINDS",
                )
            )

    if targeting_text:
        entities = _multi_or_single(targeting_text)
        if len(entities) > 1:
            rels = [
                _relationship(
                    extraction,
                    entity,
                    field_name="ncbi_nuc_definition",
                    locator=f"ncbi_nuc:{accession}|DEFINITION|TARGETING",
                    method="NCBI_DEF_TARGETING_MULTI",
                    confidence="medium",
                    checkpoint2=True,
                    ambiguity="definition_names_multiple_target_entities",
                )
                for entity in entities
            ]
            return apply_relationships(
                extraction,
                rels,
                status="ambiguous",
                method="NCBI_DEF_TARGETING_MULTI",
                confidence="medium",
                checkpoint2=True,
                ambiguity_reason="definition_names_multiple_target_entities",
                notes=";".join(notes),
            )
        candidates.append(
            (
                targeting_text,
                "ncbi_nuc_definition",
                f"ncbi_nuc:{accession}|DEFINITION|TARGETING",
                "NCBI_DEF_TARGETING",
            )
        )

    all_hits = candidates + feature_targets
    unique_raw: list[str] = []
    seen: set[str] = set()
    chosen: list[tuple[str, str, str, str]] = []
    for raw, field_name, locator, method in all_hits:
        key = raw.casefold()
        if not raw or key in seen:
            continue
        seen.add(key)
        unique_raw.append(raw)
        chosen.append((raw, field_name, locator, method))

    if len(chosen) > 1:
        longest = max(chosen, key=lambda item: len(item[0]))
        if all(
            item[0].casefold() in longest[0].casefold()
            or longest[0].casefold() in item[0].casefold()
            for item in chosen
        ):
            chosen = [longest]
            unique_raw = [longest[0]]

    if not chosen:
        notes.append("no_explicit_genbank_binding_phrase")
        return apply_relationships(
            extraction,
            [],
            status="unresolved",
            method="NCBI_UNRESOLVED",
            confidence="unresolved",
            notes=";".join(notes),
        )

    if len(unique_raw) > 1:
        rels = [
            _relationship(
                extraction,
                raw,
                field_name=field_name,
                locator=locator,
                method=method,
                confidence="medium",
                checkpoint2=True,
                ambiguity="multiple_explicit_genbank_target_statements",
            )
            for raw, field_name, locator, method in chosen
        ]
        return apply_relationships(
            extraction,
            rels,
            status="ambiguous",
            method="NCBI_MULTI_STATEMENT",
            confidence="medium",
            checkpoint2=True,
            ambiguity_reason="multiple_explicit_genbank_target_statements",
            notes=";".join(notes),
        )

    raw, field_name, locator, method = chosen[0]
    rel = _relationship(
        extraction,
        raw,
        field_name=field_name,
        locator=locator,
        method=method,
        confidence="high",
    )
    return apply_relationships(
        extraction,
        [rel],
        status="resolved_single",
        method=method,
        confidence="high",
        notes=";".join(notes),
    )
