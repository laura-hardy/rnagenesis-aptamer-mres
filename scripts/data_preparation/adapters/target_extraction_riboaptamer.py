"""Deterministic RiboAptamer free-text target extraction."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Mapping

from adapters.target_extraction_common import (
    RecordExtraction,
    TargetRelationship,
    alias_candidate_key,
    apply_relationships,
    base_extraction,
    primary_match_key,
    split_comma_entities,
)

NAME_APTAMER_RE = re.compile(
    r"^(?P<entity>.+?)\s+apt(?:amer|ermer)(?:\s*\((?P<paren>[^)]*)\))?\s*$",
    re.IGNORECASE,
)
LEADING_PAREN_RE = re.compile(
    r"^(?P<head>.+?)\s*\((?P<inner>[^)]+)\)(?P<rest>.*)$"
)
EXPLICIT_DESC_RE = re.compile(
    r"(?i)\b(?:RNA\s+|DNA\s+)?aptamers?\s+"
    r"(?:for|against|that binds?(?:\s+to)?)\s+"
    r"(?P<target>[^.;:]{2,80})"
)
AND_JOIN_RE = re.compile(r"\s+and\s+", re.IGNORECASE)
PAREN_RE = re.compile(r"\(([^)]+)\)")
STOP_TOKENS = frozenset(
    {
        "the",
        "of",
        "and",
        "to",
        "for",
        "a",
        "an",
        "in",
        "with",
        "protein",
        "proteins",
        "aptamer",
        "aptermer",
        "rna",
        "dna",
        "type",
        "region",
        "domain",
        "cell",
        "cells",
        "human",
        "expressed",
        "on",
        "from",
    }
)
GENERIC_PREFIX_RE = re.compile(
    r"^(?:clone|variant|construct|library|seq|aptamer|aptermer|rna|dna|"
    r"selex|pool|round|unknown|na|n/?a|none)\s*\d*$",
    re.IGNORECASE,
)
CLONE_LIKE_ENTITY_RE = re.compile(
    r"^(?:"
    r"[A-Za-zαβγδ]{0,4}[-_]?\d+[A-Za-z0-9.\-]*|"
    r"(?:rafl|bg)\d+[A-Za-z0-9]*|"
    r"tmg(?:\s+rna)?|"
    r"ii-mini3-4|"
    r"l-sup-a-\d+"
    r")$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SeqFirstUnderscoreAudit:
    """Sequence-safe classification of one RA_SEQ_FIRST_UNDERSCORE extraction."""

    classification: str
    corroboration_sources: tuple[str, ...]
    prefix_is_clone_like: bool
    aptamer_entity_is_clone_like: bool
    notes: str


def _name_entity(aptamer_name: str) -> str:
    match = NAME_APTAMER_RE.match((aptamer_name or "").strip())
    if match is None:
        return ""
    return match.group("entity").strip()


def _paren_parts(text: str) -> list[str]:
    return [match.group(1).strip() for match in PAREN_RE.finditer(text or "")]


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9αβγδκ]+", primary_match_key(text))
        if token not in STOP_TOKENS and len(token) >= 2
    }


def _token_overlap(a: str, b: str) -> float:
    left = _tokens(a)
    right = _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _labels_agree(left: str, right: str, *, _depth: int = 0) -> bool:
    """True when source strings name the same entity without outside knowledge."""
    left = (left or "").strip()
    right = (right or "").strip()
    if not left or not right or _depth > 2:
        return False
    if primary_match_key(left) == primary_match_key(right):
        return True
    if alias_candidate_key(left) == alias_candidate_key(right):
        return True
    left_key = primary_match_key(left)
    right_key = primary_match_key(right)
    if len(left_key) >= 3 and (left_key in right_key or right_key in left_key):
        return True
    left_alias = alias_candidate_key(left)
    right_alias = alias_candidate_key(right)
    if len(left_alias) >= 3 and (
        left_alias in right_alias or right_alias in left_alias
    ):
        return True
    if _depth == 0:
        for part in _paren_parts(left):
            if _labels_agree(part, right, _depth=1):
                return True
        for part in _paren_parts(right):
            if _labels_agree(part, left, _depth=1):
                return True
    return _token_overlap(left, right) >= 0.6


def _contains_label(haystack: str, needle: str) -> bool:
    if not haystack or not needle:
        return False
    hay = primary_match_key(haystack)
    need = primary_match_key(needle)
    if len(need) >= 3 and need in hay:
        return True
    for part in _paren_parts(needle):
        part_key = primary_match_key(part)
        if len(part_key) >= 3 and part_key in hay:
            return True
        part_alias = alias_candidate_key(part)
        if len(part_alias) >= 3 and part_alias in alias_candidate_key(haystack):
            return True
    return False


def _prefix_is_clone_like(prefix: str) -> bool:
    text = (prefix or "").strip()
    if not text:
        return True
    if GENERIC_PREFIX_RE.match(text):
        return True
    if re.match(r"^clone\b", text, re.IGNORECASE) or re.match(
        r"^clone[A-Za-z0-9_-]*$", text, re.IGNORECASE
    ):
        return True
    if re.fullmatch(r"\d+", text):
        return True
    return False


def _entity_is_clone_like(entity: str) -> bool:
    text = (entity or "").strip()
    if not text:
        return False
    if CLONE_LIKE_ENTITY_RE.match(text):
        return True
    if GENERIC_PREFIX_RE.match(text):
        return True
    return False


def _and_joined_entities(prefix: str) -> list[str]:
    """Split short 'X and Y' ligand lists; leave sentence-like phrases intact."""
    text = (prefix or "").strip()
    if not AND_JOIN_RE.search(text):
        return [text] if text else []
    parts = [item.strip() for item in AND_JOIN_RE.split(text) if item.strip()]
    if len(parts) != 2:
        return [text]
    if any(len(item) > 40 or len(item.split()) > 4 for item in parts):
        return [text]
    return parts


def classify_seq_first_underscore(
    *,
    prefix: str,
    aptamer_name: str,
    description: str,
    article_name: str,
) -> SeqFirstUnderscoreAudit:
    """Classify a Sequence Name `{prefix}_{clone}` extraction against source text.

    Category is never used. Type is not used. Outside biological knowledge is
    not used. Sequence Name may remain a target only where Aptamer Name,
    Description, or publication text corroborates it, or where Aptamer Name
    is a clone/construct label and the prefix is a descriptive ligand string
    under the documented `{target}_{clone}` convention.
    """
    entity = _name_entity(aptamer_name)
    entity_prefix = entity.split("_", 1)[0].strip() if entity else ""
    prefix_clone = _prefix_is_clone_like(prefix)
    apt_clone = _entity_is_clone_like(entity)
    sources: list[str] = []
    notes: list[str] = []

    apt_direct = (aptamer_name or "").strip()
    if _labels_agree(entity, prefix) or _labels_agree(entity_prefix, prefix):
        sources.append("aptamer_name")
    elif apt_direct and not entity and _labels_agree(apt_direct, prefix):
        sources.append("aptamer_name")
    elif entity and any(_labels_agree(entity, part) for part in _paren_parts(prefix)):
        sources.append("aptamer_name")
    elif entity and any(_labels_agree(part, prefix) for part in _paren_parts(aptamer_name)):
        sources.append("aptamer_name")
    if _contains_label(description, prefix):
        sources.append("description")
    if article_name and not _entity_is_clone_like(article_name):
        if _contains_label(article_name, prefix):
            sources.append("article_name")

    unique_sources = tuple(dict.fromkeys(sources))
    conflicting = bool(
        entity
        and not apt_clone
        and not prefix_clone
        and not _labels_agree(entity, prefix)
        and not _labels_agree(entity_prefix, prefix)
        and not any(_labels_agree(entity, part) for part in _paren_parts(prefix))
        and not any(_labels_agree(part, prefix) for part in _paren_parts(aptamer_name))
    )

    if prefix_clone:
        classification = "clone_or_construct_label_not_target"
        notes.append("sequence_name_prefix_is_clone_or_generic")
    elif conflicting:
        classification = "conflicting_source_metadata"
        notes.append("aptamer_name_entity_disagrees_with_sequence_name_prefix")
    elif unique_sources:
        classification = "corroborated_target_label"
    elif apt_clone and not prefix_clone:
        classification = "sequence_name_is_explicit_target_label"
        notes.append("aptamer_name_is_clone_or_construct_label")
        notes.append("sequence_name_prefix_encodes_target_under_documented_convention")
    elif entity and _labels_agree(entity, (aptamer_name or "").rsplit(" aptamer", 1)[0]):
        classification = "insufficient_support"
    else:
        classification = "insufficient_support"
        notes.append("no_source_text_corroboration_of_sequence_name_prefix")

    return SeqFirstUnderscoreAudit(
        classification=classification,
        corroboration_sources=unique_sources,
        prefix_is_clone_like=prefix_clone,
        aptamer_entity_is_clone_like=apt_clone,
        notes=";".join(notes),
    )


def inspect_riboaptamer_patterns(
    rows: list[Mapping[str, str]],
) -> dict[str, object]:
    """Sequence-safe aggregate inspection of RiboAptamer name/description fields."""
    names = [row.get("riboaptamer_aptamer_name", "") for row in rows]
    seqs = [row.get("riboaptamer_sequence_name", "") for row in rows]
    descs = [row.get("riboaptamer_description", "") for row in rows]
    name_counts = Counter(names)
    n_underscore = Counter(seq.count("_") for seq in seqs)
    return {
        "n_records": len(rows),
        "unique_aptamer_names": len(set(names)),
        "unique_sequence_names": len(set(seqs)),
        "unique_descriptions": len(set(descs)),
        "names_containing_aptamer": sum(
            1 for name in names if re.search(r"(?i)aptamer", name)
        ),
        "names_containing_aptermer": sum(
            1 for name in names if re.search(r"(?i)aptermer", name)
        ),
        "sequence_name_underscore_counts": {
            str(key): int(value) for key, value in sorted(n_underscore.items())
        },
        "top_aptamer_names": [
            {"name": name, "n": int(count)}
            for name, count in name_counts.most_common(20)
        ],
        "category_counts": dict(
            Counter(row.get("riboaptamer_category", "") for row in rows)
        ),
        "type_counts": dict(
            Counter(row.get("riboaptamer_type", "") for row in rows)
        ),
        "description_explicit_aptamer_for_hits": sum(
            1 for desc in descs if EXPLICIT_DESC_RE.search(desc or "")
        ),
        "seq_first_underscore_audit": audit_seq_first_underscore_cohort(rows),
    }


def audit_seq_first_underscore_cohort(
    rows: list[Mapping[str, str]],
) -> dict[str, object]:
    """Sequence-safe audit of records whose Sequence Name has a first-underscore prefix."""
    counts: Counter[str] = Counter()
    corroboration: Counter[str] = Counter()
    n_cohort = 0
    for row in rows:
        seq_name = (row.get("riboaptamer_sequence_name") or "").strip()
        if "_" not in seq_name:
            continue
        prefix, _suffix = seq_name.split("_", 1)
        prefix = prefix.strip()
        entities = [item for item in split_comma_entities(prefix) if item]
        and_entities = _and_joined_entities(prefix) if len(entities) <= 1 else entities
        if len(and_entities) > 1:
            continue
        if not prefix:
            continue
        n_cohort += 1
        audit = classify_seq_first_underscore(
            prefix=prefix,
            aptamer_name=row.get("riboaptamer_aptamer_name", ""),
            description=row.get("riboaptamer_description", ""),
            article_name=row.get("riboaptamer_article_name", ""),
        )
        counts[audit.classification] += 1
        if audit.corroboration_sources:
            for source in audit.corroboration_sources:
                corroboration[source] += 1
        else:
            corroboration["none"] += 1
    return {
        "n_single_prefix_cohort": n_cohort,
        "classification_counts": dict(counts),
        "corroboration_source_counts": dict(corroboration),
        "convention": (
            "Sequence Name uses {target}_{clone_or_variant} where the prefix "
            "is the ligand/target and the suffix is a clone/construct/variant "
            "label. Aptamer Name is typically '{target} aptamer' or a clone "
            "label. Category and Type are not used as corroboration."
        ),
    }


def _relationship(
    extraction: RecordExtraction,
    raw: str,
    *,
    field_name: str,
    rule_id: str,
    confidence: str,
    checkpoint2: bool = False,
    ambiguity: str = "",
) -> TargetRelationship:
    return TargetRelationship(
        record_id=extraction.record_id,
        source_db=extraction.source_db,
        raw_target=raw.strip(),
        target_provenance_source=field_name,
        target_provenance_locator=f"riboaptamer:{field_name}|rule={rule_id}",
        relationship_confidence=confidence,
        requires_checkpoint2=checkpoint2,
        ambiguity_reason=ambiguity,
    )


def extract_riboaptamer_record(row: Mapping[str, str]) -> RecordExtraction:
    """Extract a RiboAptamer target from source-native name/description fields."""
    extraction = base_extraction(row)
    extraction.source_target_type_prior = (row.get("riboaptamer_type") or "").strip()
    extraction.source_target_type_prior_source = (
        "riboaptamer_type" if extraction.source_target_type_prior else ""
    )
    category = (row.get("riboaptamer_category") or "").strip()
    notes = []
    if category:
        notes.append(f"riboaptamer_category={category}")
    notes.append("riboaptamer_type_is_prior_only=true")
    notes.append("riboaptamer_category_is_prior_only=true")

    seq_name = (row.get("riboaptamer_sequence_name") or "").strip()
    apt_name = (row.get("riboaptamer_aptamer_name") or "").strip()
    description = (row.get("riboaptamer_description") or "").strip()
    article_name = (row.get("riboaptamer_article_name") or "").strip()
    name_entity = _name_entity(apt_name)

    if "_" in seq_name:
        prefix, _suffix = seq_name.split("_", 1)
        prefix = prefix.strip()
        entities = [item for item in split_comma_entities(prefix) if item]
        if len(entities) <= 1:
            entities = [item for item in _and_joined_entities(prefix) if item]
        if len(entities) > 1:
            rels = [
                _relationship(
                    extraction,
                    item,
                    field_name="riboaptamer_sequence_name",
                    rule_id="RA_SEQ_FIRST_UNDERSCORE_MULTI",
                    confidence="medium",
                    checkpoint2=True,
                    ambiguity="sequence_name_prefix_lists_multiple_entities",
                )
                for item in entities
            ]
            return apply_relationships(
                extraction,
                rels,
                status="ambiguous",
                method="RA_SEQ_FIRST_UNDERSCORE_MULTI",
                confidence="medium",
                checkpoint2=True,
                ambiguity_reason="sequence_name_prefix_lists_multiple_entities",
                notes=";".join(notes),
            )
        if prefix:
            audit = classify_seq_first_underscore(
                prefix=prefix,
                aptamer_name=apt_name,
                description=description,
                article_name=article_name,
            )
            notes.append(f"ra_seq_first_underscore_audit={audit.classification}")
            if audit.corroboration_sources:
                notes.append(
                    "corroborated_by=" + "|".join(audit.corroboration_sources)
                )
            if audit.notes:
                notes.append(audit.notes)
            if audit.classification in {
                "corroborated_target_label",
                "sequence_name_is_explicit_target_label",
            }:
                confidence = "medium"
                if "aptamer_name" in audit.corroboration_sources:
                    confidence = "high"
                rel = _relationship(
                    extraction,
                    prefix,
                    field_name="riboaptamer_sequence_name",
                    rule_id="RA_SEQ_FIRST_UNDERSCORE",
                    confidence=confidence,
                )
                return apply_relationships(
                    extraction,
                    [rel],
                    status="resolved_single",
                    method="RA_SEQ_FIRST_UNDERSCORE",
                    confidence=confidence,
                    notes=";".join(notes),
                )
            if audit.classification == "conflicting_source_metadata":
                rels = [
                    _relationship(
                        extraction,
                        prefix,
                        field_name="riboaptamer_sequence_name",
                        rule_id="RA_SEQ_FIRST_UNDERSCORE_CONFLICT",
                        confidence="low",
                        checkpoint2=True,
                        ambiguity="aptamer_name_and_sequence_name_entities_differ",
                    )
                ]
                if name_entity and not _labels_agree(name_entity, prefix):
                    rels.append(
                        _relationship(
                            extraction,
                            name_entity,
                            field_name="riboaptamer_aptamer_name",
                            rule_id="RA_SEQ_FIRST_UNDERSCORE_CONFLICT",
                            confidence="low",
                            checkpoint2=True,
                            ambiguity="aptamer_name_and_sequence_name_entities_differ",
                        )
                    )
                return apply_relationships(
                    extraction,
                    rels,
                    status="ambiguous",
                    method="RA_SEQ_FIRST_UNDERSCORE_CONFLICT",
                    confidence="low",
                    checkpoint2=True,
                    ambiguity_reason="aptamer_name_and_sequence_name_entities_differ",
                    notes=";".join(notes),
                )
            return apply_relationships(
                extraction,
                [],
                status="unresolved",
                method="RA_SEQ_FIRST_UNDERSCORE_UNSUPPORTED",
                confidence="unresolved",
                notes=";".join(notes),
            )

    paren = LEADING_PAREN_RE.match(seq_name)
    if paren is not None:
        head = paren.group("head").strip()
        inner = paren.group("inner").strip()
        seq_raw = f"{head} ({inner})"
        name_key = primary_match_key(name_entity)
        head_key = primary_match_key(head)
        inner_key = primary_match_key(inner)
        if name_key and (name_key == head_key or name_key == inner_key):
            rel = _relationship(
                extraction,
                seq_raw,
                field_name="riboaptamer_sequence_name",
                rule_id="RA_SEQ_LEADING_PAREN",
                confidence="medium",
            )
            return apply_relationships(
                extraction,
                [rel],
                status="resolved_single",
                method="RA_SEQ_LEADING_PAREN",
                confidence="medium",
                notes=";".join(notes),
            )
        if name_entity and name_key not in {head_key, inner_key}:
            rels = [
                _relationship(
                    extraction,
                    name_entity,
                    field_name="riboaptamer_aptamer_name",
                    rule_id="RA_NAME_VS_SEQ_CONFLICT",
                    confidence="low",
                    checkpoint2=True,
                    ambiguity="aptamer_name_and_sequence_name_entities_differ",
                ),
                _relationship(
                    extraction,
                    seq_raw,
                    field_name="riboaptamer_sequence_name",
                    rule_id="RA_NAME_VS_SEQ_CONFLICT",
                    confidence="low",
                    checkpoint2=True,
                    ambiguity="aptamer_name_and_sequence_name_entities_differ",
                ),
            ]
            return apply_relationships(
                extraction,
                rels,
                status="ambiguous",
                method="RA_NAME_VS_SEQ_CONFLICT",
                confidence="low",
                checkpoint2=True,
                ambiguity_reason="aptamer_name_and_sequence_name_entities_differ",
                notes=";".join(notes),
            )

    if apt_name and seq_name and primary_match_key(apt_name) == primary_match_key(seq_name):
        notes.append("aptamer_name_equals_sequence_name_not_used_as_target")
        return apply_relationships(
            extraction,
            [],
            status="unresolved",
            method="RA_UNRESOLVED_IDENTITY_NAME",
            confidence="unresolved",
            notes=";".join(notes),
        )

    if name_entity and seq_name.lower().startswith(name_entity.lower()):
        rel = _relationship(
            extraction,
            name_entity,
            field_name="riboaptamer_aptamer_name",
            rule_id="RA_NAME_ENTITY_CORROBORATED_BY_SEQ",
            confidence="medium",
        )
        return apply_relationships(
            extraction,
            [rel],
            status="resolved_single",
            method="RA_NAME_ENTITY_CORROBORATED_BY_SEQ",
            confidence="medium",
            notes=";".join(notes),
        )

    if apt_name and not NAME_APTAMER_RE.match(apt_name) and seq_name.lower().startswith(
        apt_name.split("(")[0].strip().lower()
    ):
        rel = _relationship(
            extraction,
            apt_name,
            field_name="riboaptamer_aptamer_name",
            rule_id="RA_NAME_DIRECT_LIGAND",
            confidence="medium",
        )
        return apply_relationships(
            extraction,
            [rel],
            status="resolved_single",
            method="RA_NAME_DIRECT_LIGAND",
            confidence="medium",
            notes=";".join(notes),
        )

    desc_match = EXPLICIT_DESC_RE.search(description)
    if desc_match is not None:
        target = desc_match.group("target").strip()
        if target and len(target) <= 80:
            rel = _relationship(
                extraction,
                target,
                field_name="riboaptamer_description",
                rule_id="RA_DESC_EXPLICIT_APTAMER_FOR",
                confidence="low",
                checkpoint2=True,
                ambiguity="description_explicit_phrase_needs_review",
            )
            return apply_relationships(
                extraction,
                [rel],
                status="resolved_single",
                method="RA_DESC_EXPLICIT_APTAMER_FOR",
                confidence="low",
                checkpoint2=True,
                ambiguity_reason="description_explicit_phrase_needs_review",
                notes=";".join(notes),
            )

    notes.append("no_mechanically_explicit_target_phrase")
    return apply_relationships(
        extraction,
        [],
        status="unresolved",
        method="RA_UNRESOLVED",
        confidence="unresolved",
        notes=";".join(notes),
    )
