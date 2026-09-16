"""Shared schema, match keys, and row helpers for Milestone-2 target extraction."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Final, Mapping, MutableMapping

RECORD_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "source_db",
    "native_id",
    "existing_target_name_raw",
    "extracted_target_raw",
    "effective_target_raw",
    "target_provenance_source",
    "target_provenance_locator",
    "target_extraction_method",
    "extraction_confidence",
    "relationship_status",
    "n_target_relationships_proposed",
    "record_expansion_proposed",
    "source_target_type_prior",
    "source_target_type_prior_source",
    "source_target_id",
    "source_uniprot_seed",
    "ambiguity_reason",
    "requires_checkpoint2",
    "notes",
)

RELATIONSHIP_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "relationship_index",
    "source_db",
    "raw_target",
    "target_provenance_source",
    "target_provenance_locator",
    "source_target_id",
    "source_uniprot_seed",
    "relationship_confidence",
    "requires_checkpoint2",
    "ambiguity_reason",
)

DICTIONARY_COLUMNS: Final[tuple[str, ...]] = (
    "target_dictionary_id",
    "raw_target",
    "primary_match_key",
    "alias_candidate_key",
    "canonical_target_name_proposal",
    "canonicalisation_method",
    "proposal_confidence",
    "source_keys",
    "n_records",
    "n_relationships",
    "source_uniprot_seed",
    "source_target_type_priors",
    "source_target_ids",
    "record_expansion_involved",
    "ambiguity_flags",
    "requires_checkpoint2",
    "review_status",
)

RELATIONSHIP_STATUS_VOCAB: Final[frozenset[str]] = frozenset(
    {"resolved_single", "resolved_multiple", "ambiguous", "unresolved"}
)
CONFIDENCE_VOCAB: Final[frozenset[str]] = frozenset(
    {"high", "medium", "low", "unresolved"}
)

CANONICAL_FIELDS_MUST_STAY_EMPTY: Final[tuple[str, ...]] = (
    "target_name",
    "target_uniprot",
    "target_type",
    "target_type_source",
    "target_family",
    "target_pfam",
    "pdb_id",
    "binding_evidence_type",
    "binding_evidence_score",
    "affinity_value",
    "affinity_unit",
    "affinity_type",
)

SEQ_LEAK_RE: Final[re.Pattern[str]] = re.compile(r"[ACGTUacgtu]{20,}")
_PUNCT_RE: Final[re.Pattern[str]] = re.compile(r"[\s_\-–—/.,:;+()\[\]{}'\"`]+")


class TargetExtractionError(ValueError):
    """Hard failure during Milestone-2 target extraction."""


def primary_match_key(raw: str) -> str:
    """Unicode-normalise, trim, collapse whitespace, casefold."""
    text = unicodedata.normalize("NFC", raw or "")
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def alias_candidate_key(raw: str) -> str:
    """Punctuation-insensitive key for alias-candidate detection only."""
    return _PUNCT_RE.sub("", primary_match_key(raw))


def bool_token(value: bool) -> str:
    return "true" if value else "false"


def join_unique(values: list[str] | tuple[str, ...], *, sep: str = "|") -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = (value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return sep.join(ordered)


def empty_record_row() -> dict[str, str]:
    return {column: "" for column in RECORD_COLUMNS}


def empty_relationship_row() -> dict[str, str]:
    return {column: "" for column in RELATIONSHIP_COLUMNS}


@dataclass
class TargetRelationship:
    """One source-supported target relationship proposal."""

    record_id: str
    source_db: str
    raw_target: str
    target_provenance_source: str
    target_provenance_locator: str
    source_target_id: str = ""
    source_uniprot_seed: str = ""
    relationship_confidence: str = "high"
    requires_checkpoint2: bool = False
    ambiguity_reason: str = ""
    relationship_index: int = 0

    def as_row(self) -> dict[str, str]:
        if self.relationship_confidence not in CONFIDENCE_VOCAB:
            raise TargetExtractionError(
                f"invalid relationship_confidence {self.relationship_confidence!r}"
            )
        row = empty_relationship_row()
        row.update(
            {
                "record_id": self.record_id,
                "relationship_index": str(self.relationship_index),
                "source_db": self.source_db,
                "raw_target": self.raw_target,
                "target_provenance_source": self.target_provenance_source,
                "target_provenance_locator": self.target_provenance_locator,
                "source_target_id": self.source_target_id,
                "source_uniprot_seed": self.source_uniprot_seed,
                "relationship_confidence": self.relationship_confidence,
                "requires_checkpoint2": bool_token(self.requires_checkpoint2),
                "ambiguity_reason": self.ambiguity_reason,
            }
        )
        return row


@dataclass
class RecordExtraction:
    """One combined-input record's Milestone-2 extraction result."""

    record_id: str
    source_db: str
    native_id: str
    existing_target_name_raw: str
    extracted_target_raw: str = ""
    effective_target_raw: str = ""
    target_provenance_source: str = ""
    target_provenance_locator: str = ""
    target_extraction_method: str = ""
    extraction_confidence: str = "unresolved"
    relationship_status: str = "unresolved"
    record_expansion_proposed: bool = False
    source_target_type_prior: str = ""
    source_target_type_prior_source: str = ""
    source_target_id: str = ""
    source_uniprot_seed: str = ""
    ambiguity_reason: str = ""
    requires_checkpoint2: bool = False
    notes: str = ""
    relationships: list[TargetRelationship] = field(default_factory=list)

    def as_row(self) -> dict[str, str]:
        if self.relationship_status not in RELATIONSHIP_STATUS_VOCAB:
            raise TargetExtractionError(
                f"invalid relationship_status {self.relationship_status!r}"
            )
        if self.extraction_confidence not in CONFIDENCE_VOCAB:
            raise TargetExtractionError(
                f"invalid extraction_confidence {self.extraction_confidence!r}"
            )
        n_rel = len(self.relationships)
        row = empty_record_row()
        row.update(
            {
                "record_id": self.record_id,
                "source_db": self.source_db,
                "native_id": self.native_id,
                "existing_target_name_raw": self.existing_target_name_raw,
                "extracted_target_raw": self.extracted_target_raw,
                "effective_target_raw": self.effective_target_raw,
                "target_provenance_source": self.target_provenance_source,
                "target_provenance_locator": self.target_provenance_locator,
                "target_extraction_method": self.target_extraction_method,
                "extraction_confidence": self.extraction_confidence,
                "relationship_status": self.relationship_status,
                "n_target_relationships_proposed": str(n_rel),
                "record_expansion_proposed": bool_token(self.record_expansion_proposed),
                "source_target_type_prior": self.source_target_type_prior,
                "source_target_type_prior_source": self.source_target_type_prior_source,
                "source_target_id": self.source_target_id,
                "source_uniprot_seed": self.source_uniprot_seed,
                "ambiguity_reason": self.ambiguity_reason,
                "requires_checkpoint2": bool_token(self.requires_checkpoint2),
                "notes": self.notes,
            }
        )
        return row


def numbered_relationships(
    relationships: list[TargetRelationship],
) -> list[TargetRelationship]:
    ordered = list(relationships)
    for index, rel in enumerate(ordered, start=1):
        rel.relationship_index = index
    return ordered


def apply_relationships(
    extraction: RecordExtraction,
    relationships: list[TargetRelationship],
    *,
    status: str,
    method: str,
    confidence: str,
    expansion: bool = False,
    checkpoint2: bool = False,
    ambiguity_reason: str = "",
    notes: str = "",
    effective_override: str | None = None,
) -> RecordExtraction:
    numbered = numbered_relationships(relationships)
    extraction.relationships = numbered
    extraction.relationship_status = status
    extraction.target_extraction_method = method
    extraction.extraction_confidence = confidence
    extraction.record_expansion_proposed = expansion
    extraction.requires_checkpoint2 = checkpoint2 or any(
        rel.requires_checkpoint2 for rel in numbered
    )
    extraction.ambiguity_reason = ambiguity_reason
    if notes:
        extraction.notes = notes
    if numbered:
        first = numbered[0]
        extraction.extracted_target_raw = first.raw_target
        extraction.effective_target_raw = (
            effective_override if effective_override is not None else first.raw_target
        )
        extraction.target_provenance_source = first.target_provenance_source
        extraction.target_provenance_locator = first.target_provenance_locator
        if not extraction.source_target_id:
            extraction.source_target_id = first.source_target_id
        if not extraction.source_uniprot_seed:
            extraction.source_uniprot_seed = first.source_uniprot_seed
        if status == "resolved_multiple":
            extraction.effective_target_raw = join_unique(
                [rel.raw_target for rel in numbered]
            )
            extraction.extracted_target_raw = extraction.effective_target_raw
        elif status == "ambiguous":
            extraction.effective_target_raw = ""
            extraction.extracted_target_raw = join_unique(
                [rel.raw_target for rel in numbered]
            )
    else:
        extraction.extracted_target_raw = ""
        extraction.effective_target_raw = ""
        extraction.extraction_confidence = "unresolved"
    return extraction


def base_extraction(row: Mapping[str, str]) -> RecordExtraction:
    return RecordExtraction(
        record_id=row.get("record_id", ""),
        source_db=row.get("source_db", ""),
        native_id=row.get("native_id", ""),
        existing_target_name_raw=row.get("target_name_raw", ""),
    )


def assert_no_sequence_leak(text: str, *, label: str) -> None:
    if SEQ_LEAK_RE.search(text or ""):
        raise TargetExtractionError(
            f"{label} must not contain biological sequence strings"
        )


def split_comma_entities(text: str) -> list[str]:
    """Split comma-separated entities, ignoring commas inside parentheses."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
            buf.append(char)
        elif char == ")":
            depth = max(0, depth - 1)
            buf.append(char)
        elif char == "," and depth == 0:
            item = "".join(buf).strip()
            if item:
                parts.append(item)
            buf = []
        else:
            buf.append(char)
    item = "".join(buf).strip()
    if item:
        parts.append(item)
    return parts


def fill_missing(row: MutableMapping[str, str], columns: tuple[str, ...]) -> dict[str, str]:
    return {column: row.get(column, "") for column in columns}
