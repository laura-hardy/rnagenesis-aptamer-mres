"""AptamerBase RDF interaction-graph target extraction.

Uses the registered local N-Triples extract only. Aptamer labels are never
treated as targets. Affinity/evidence triples are retained as provenance
identifiers and are not scored.
"""

from __future__ import annotations

import gzip
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from adapters.aptamerbase_rdf import parse_ntriples_line
from adapters.target_extraction_common import (
    RecordExtraction,
    TargetExtractionError,
    TargetRelationship,
    alias_candidate_key,
    apply_relationships,
    base_extraction,
    join_unique,
    primary_match_key,
)

HAS_PARTICIPANT = "http://rdf.freebase.com/ns/base.aptamer.interaction.has_participant"
IS_PARTICIPANT_IN = (
    "http://rdf.freebase.com/ns/base.aptamer.interactor.is_participant_in"
)
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
FB_TYPE = "http://rdf.freebase.com/ns/type.object.type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
OBJECT_NAME = "http://rdf.freebase.com/ns/type.object.name"
HAS_TYPE = "http://rdf.freebase.com/ns/base.aptamer.aptamer_target.has_type"
HAS_KD = "http://rdf.freebase.com/ns/base.aptamer.interaction.has_dissociation_constant"
CONFIRMED_BY = "http://rdf.freebase.com/ns/base.aptamer.interaction.is_confirmed_by"

TYPE_APTAMER = "http://rdf.freebase.com/ns/base.aptamer.aptamer"
TYPE_APTAMER_TARGET = "http://rdf.freebase.com/ns/base.aptamer.aptamer_target"
TYPE_MOLECULAR_TARGET = "http://rdf.freebase.com/ns/base.aptamer.molecular_target"
TYPE_PROTEIN = "http://rdf.freebase.com/ns/biology.protein"
TYPE_PAIRWISE = "http://rdf.freebase.com/ns/base.aptamer.pairwise_interaction"
TYPE_COLLECTIVE = "http://rdf.freebase.com/ns/base.aptamer.collective_interaction"
TYPE_INTERACTION = "http://rdf.freebase.com/ns/base.aptamer.interaction"

SKIP_TYPES = frozenset(
    {
        TYPE_INTERACTION,
        TYPE_PAIRWISE,
        TYPE_COLLECTIVE,
        "http://rdf.freebase.com/ns/base.aptamer.experiment",
        "http://rdf.freebase.com/ns/base.aptamer.affinity_experiment",
        "http://rdf.freebase.com/ns/base.aptamer.selex_experiment",
        "http://rdf.freebase.com/ns/base.aptamer.experimental_outcome",
        "http://rdf.freebase.com/ns/base.aptamer.dissociation_constant",
        "http://rdf.freebase.com/ns/base.aptamer.experimental_conditions",
        "http://rdf.freebase.com/ns/base.aptamer.affinity_conditions",
        "http://rdf.freebase.com/ns/base.aptamer.nucleic_acid_secondary_structure",
        "http://rdf.freebase.com/ns/base.aptamer.predicted_secondary_structure",
        "http://rdf.freebase.com/ns/base.aptamer.interaction_experiment",
        "http://rdf.freebase.com/ns/base.aptamer.aptamer_experiment",
    }
)

KEEP_PREDICATES = frozenset(
    {
        HAS_PARTICIPANT,
        IS_PARTICIPANT_IN,
        RDF_TYPE,
        FB_TYPE,
        RDFS_LABEL,
        OBJECT_NAME,
        HAS_TYPE,
        HAS_KD,
        CONFIRMED_BY,
    }
)

_LITERAL_LANG_RE = re.compile(
    r'^"((?:\\.|[^"\\])*)"(?:@([A-Za-z][A-Za-z0-9-]*))?(?:\^\^<[^>]*>)?$'
)


def _unescape_literal(body: str) -> str:
    return (
        body.replace(r"\\", "\\")
        .replace(r"\"", '"')
        .replace(r"\n", "\n")
        .replace(r"\t", "\t")
        .replace(r"\r", "\r")
    )


def _parse_literal_lang(raw_object: str) -> tuple[str, str] | None:
    match = _LITERAL_LANG_RE.match(raw_object.strip())
    if match is None:
        return None
    return _unescape_literal(match.group(1)), (match.group(2) or "").lower()


def _pick_english(values: list[tuple[str, str]]) -> str:
    for text, lang in values:
        if lang == "en" and text.strip():
            return text
    for text, lang in values:
        if lang == "" and text.strip():
            return text
    return ""


@dataclass
class AptamerBaseTargetGraph:
    """In-memory interaction subgraph used for Milestone-2 target extraction."""

    statement_count: int
    types: dict[str, set[str]] = field(default_factory=dict)
    labels: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    names: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    is_participant_in: dict[str, set[str]] = field(default_factory=dict)
    has_participant: dict[str, set[str]] = field(default_factory=dict)
    has_type: dict[str, set[str]] = field(default_factory=dict)
    has_kd: dict[str, set[str]] = field(default_factory=dict)
    confirmed_by: dict[str, set[str]] = field(default_factory=dict)

    def english_label(self, uri: str) -> str:
        return _pick_english(self.labels.get(uri, [])) or _pick_english(
            self.names.get(uri, [])
        )

    def node_types(self, uri: str) -> set[str]:
        return self.types.get(uri, set())


def load_aptamerbase_target_graph(path: str | Path) -> AptamerBaseTargetGraph:
    """Stream gzip N-Triples and keep interaction/target provenance triples."""
    rdf_path = Path(path)
    graph = AptamerBaseTargetGraph(statement_count=0)
    try:
        with gzip.open(rdf_path, "rt", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                graph.statement_count += 1
                if not any(pred in stripped for pred in KEEP_PREDICATES):
                    continue
                parsed = parse_ntriples_line(line)
                if parsed is None:
                    continue
                subject, predicate, kind, obj = parsed
                if predicate not in KEEP_PREDICATES:
                    continue
                if predicate in {RDF_TYPE, FB_TYPE} and kind == "uri":
                    graph.types.setdefault(subject, set()).add(obj)
                elif predicate == HAS_PARTICIPANT and kind == "uri":
                    graph.has_participant.setdefault(subject, set()).add(obj)
                elif predicate == IS_PARTICIPANT_IN and kind == "uri":
                    graph.is_participant_in.setdefault(subject, set()).add(obj)
                elif predicate == HAS_TYPE and kind == "uri":
                    graph.has_type.setdefault(subject, set()).add(obj)
                elif predicate == HAS_KD and kind == "uri":
                    graph.has_kd.setdefault(subject, set()).add(obj)
                elif predicate == CONFIRMED_BY and kind == "uri":
                    graph.confirmed_by.setdefault(subject, set()).add(obj)
                elif predicate in {RDFS_LABEL, OBJECT_NAME} and kind == "literal":
                    raw_object = stripped.rsplit(" ", 2)[0]
                    # parse_ntriples_line already unescaped obj; recover lang
                    # from the original object field.
                    match = re.search(r'(<[^>]*>)\s+(<[^>]*>)\s+(.*)\s+\.\s*$', stripped)
                    if match is None:
                        continue
                    lit = _parse_literal_lang(match.group(3))
                    if lit is None:
                        text, lang = obj, ""
                    else:
                        text, lang = lit
                    bucket = graph.labels if predicate == RDFS_LABEL else graph.names
                    bucket.setdefault(subject, []).append((text, lang))
    except gzip.BadGzipFile as exc:
        raise TargetExtractionError("AptamerBase RDF gzip is corrupt") from exc
    except OSError as exc:
        raise TargetExtractionError(
            f"cannot read AptamerBase RDF: {exc.strerror}"
        ) from exc
    return graph


def _is_skipped_node(types: set[str]) -> bool:
    return bool(types & SKIP_TYPES)


def _is_other_aptamer(types: set[str]) -> bool:
    return TYPE_APTAMER in types and TYPE_APTAMER_TARGET not in types


@dataclass
class Counterpart:
    interaction_uri: str
    node_uri: str
    label: str
    kind: str
    pairwise: bool
    collective: bool


def _counterparts_for_aptamer(
    graph: AptamerBaseTargetGraph,
    aptamer_uri: str,
) -> list[Counterpart]:
    found: list[Counterpart] = []
    for interaction in sorted(graph.is_participant_in.get(aptamer_uri, set())):
        inter_types = graph.node_types(interaction)
        pairwise = TYPE_PAIRWISE in inter_types
        collective = TYPE_COLLECTIVE in inter_types
        for participant in sorted(graph.has_participant.get(interaction, set())):
            if participant == aptamer_uri:
                continue
            types = graph.node_types(participant)
            if _is_skipped_node(types) or _is_other_aptamer(types):
                continue
            label = graph.english_label(participant)
            if TYPE_APTAMER_TARGET in types:
                kind = "aptamer_target"
            elif TYPE_PROTEIN in types:
                kind = "biology_protein"
            elif label:
                kind = "other_labeled_counterpart"
            else:
                continue
            found.append(
                Counterpart(
                    interaction_uri=interaction,
                    node_uri=participant,
                    label=label,
                    kind=kind,
                    pairwise=pairwise,
                    collective=collective,
                )
            )
    return found


def _group_by_alias(items: Iterable[Counterpart]) -> dict[str, list[Counterpart]]:
    grouped: dict[str, list[Counterpart]] = defaultdict(list)
    for item in items:
        key = alias_candidate_key(item.label) or primary_match_key(item.label)
        if not key:
            continue
        grouped[key].append(item)
    return dict(grouped)


def _preferred_label(items: list[Counterpart]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[item.label] += 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]


def _type_prior(graph: AptamerBaseTargetGraph, node_uri: str) -> str:
    labels = []
    for type_uri in sorted(graph.has_type.get(node_uri, set())):
        label = graph.english_label(type_uri)
        if label:
            labels.append(label)
    return join_unique(labels)


def extract_aptamerbase_record(
    row: Mapping[str, str],
    *,
    graph: AptamerBaseTargetGraph,
) -> RecordExtraction:
    """Extract AptamerBase targets from the local RDF interaction graph."""
    extraction = base_extraction(row)
    aptamer_uri = (row.get("aptamerbase_id") or "").strip()
    aptamer_label = (row.get("aptamerbase_label") or "").strip()
    notes = [
        "aptamerbase_label_is_not_target=true",
        "evidence_not_assigned=true",
        "affinity_not_canonicalised=true",
    ]
    if aptamer_label:
        notes.append("aptamerbase_label_preserved_as_source_metadata_only")
    if not aptamer_uri:
        return apply_relationships(
            extraction,
            [],
            status="unresolved",
            method="AB_UNRESOLVED_MISSING_FREEBASE_ID",
            confidence="unresolved",
            checkpoint2=True,
            ambiguity_reason="missing_aptamerbase_id",
            notes=";".join(notes),
        )

    counterparts = _counterparts_for_aptamer(graph, aptamer_uri)
    interactions = graph.is_participant_in.get(aptamer_uri, set())
    if not interactions:
        return apply_relationships(
            extraction,
            [],
            status="unresolved",
            method="AB_UNRESOLVED_NO_INTERACTION",
            confidence="unresolved",
            notes=";".join(notes + ["rdf_no_is_participant_in"]),
        )

    primary = [item for item in counterparts if item.kind == "aptamer_target" and item.label]
    secondary = [
        item for item in counterparts if item.kind == "biology_protein" and item.label
    ]
    other = [
        item
        for item in counterparts
        if item.kind == "other_labeled_counterpart" and item.label
    ]
    chosen = primary or secondary or other
    method_kind = (
        "aptamer_target"
        if primary
        else "biology_protein"
        if secondary
        else "other_labeled_counterpart"
        if other
        else ""
    )
    if not chosen:
        return apply_relationships(
            extraction,
            [],
            status="unresolved",
            method="AB_UNRESOLVED_NO_TARGET_COUNTERPART",
            confidence="unresolved",
            notes=";".join(notes + ["rdf_interaction_without_target_counterpart"]),
        )

    groups = _group_by_alias(chosen)
    confidence = "high" if method_kind == "aptamer_target" else "medium"
    method_prefix = {
        "aptamer_target": "AB_RDF_APTAMER_TARGET",
        "biology_protein": "AB_RDF_PROTEIN_COUNTERPART",
        "other_labeled_counterpart": "AB_RDF_OTHER_COUNTERPART",
    }[method_kind]
    if method_kind != "aptamer_target":
        notes.append(f"target_type_not_aptamer_target={method_kind}")

    type_priors = [_type_prior(graph, item.node_uri) for item in chosen]
    extraction.source_target_type_prior = join_unique(type_priors)
    if extraction.source_target_type_prior:
        extraction.source_target_type_prior_source = (
            "rdf:base.aptamer.aptamer_target.has_type"
        )

    def _rel_from_group(items: list[Counterpart], *, checkpoint2: bool, reason: str) -> TargetRelationship:
        representative = next(item for item in items if item.label == _preferred_label(items))
        kd_ids = sorted(graph.has_kd.get(representative.interaction_uri, set()))
        locator_parts = [
            f"aptamer={aptamer_uri}",
            f"interaction={representative.interaction_uri}",
            f"target={representative.node_uri}",
            "predicates=is_participant_in>has_participant",
            "label=rdfs:label@en",
        ]
        if kd_ids:
            locator_parts.append("has_dissociation_constant=" + ",".join(kd_ids[:3]))
            notes.append("kd_node_ids_provenance_only")
        if representative.label == aptamer_label:
            raise TargetExtractionError(
                "AptamerBase extraction selected the aptamer label as a target"
            )
        return TargetRelationship(
            record_id=extraction.record_id,
            source_db=extraction.source_db,
            raw_target=representative.label,
            target_provenance_source="aptamerbase_rdf",
            target_provenance_locator="rdf:" + "|".join(locator_parts),
            source_target_id=representative.node_uri,
            relationship_confidence=confidence,
            requires_checkpoint2=checkpoint2,
            ambiguity_reason=reason,
        )

    if len(groups) == 1:
        only_key = next(iter(groups))
        rel = _rel_from_group(groups[only_key], checkpoint2=False, reason="")
        extraction.source_target_id = rel.source_target_id
        return apply_relationships(
            extraction,
            [rel],
            status="resolved_single",
            method=method_prefix,
            confidence=confidence,
            notes=";".join(dict.fromkeys(notes)),
        )

    # Multiple distinct alias groups.
    same_interaction = False
    per_interaction_labels: dict[str, set[str]] = defaultdict(set)
    for items in groups.values():
        label = _preferred_label(items)
        for item in items:
            per_interaction_labels[item.interaction_uri].add(alias_candidate_key(label))
    if any(len(labels) > 1 for labels in per_interaction_labels.values()):
        same_interaction = True

    rels = [
        _rel_from_group(
            items,
            checkpoint2=True,
            reason=(
                "multiple_targets_in_same_interaction"
                if same_interaction
                else "multiple_distinct_rdf_target_relationships"
            ),
        )
        for _, items in sorted(groups.items(), key=lambda pair: pair[0])
    ]
    extraction.source_target_id = join_unique([rel.source_target_id for rel in rels])
    if same_interaction:
        return apply_relationships(
            extraction,
            rels,
            status="ambiguous",
            method=f"{method_prefix}_SAME_INTERACTION_MULTI",
            confidence="medium",
            checkpoint2=True,
            ambiguity_reason="multiple_targets_in_same_interaction",
            notes=";".join(dict.fromkeys(notes)),
        )
    return apply_relationships(
        extraction,
        rels,
        status="resolved_multiple",
        method=f"{method_prefix}_MULTI_INTERACTION",
        confidence=confidence,
        expansion=True,
        checkpoint2=True,
        ambiguity_reason="multiple_distinct_rdf_target_relationships",
        notes=";".join(dict.fromkeys(notes)),
    )


def aptamerbase_graph_coverage(
    rows: list[Mapping[str, str]],
    graph: AptamerBaseTargetGraph,
) -> dict[str, int]:
    """Sequence-safe RDF coverage counts for authorised AptamerBase rows."""
    n_id = 0
    n_join = 0
    n_inter = 0
    n_target = 0
    for row in rows:
        uri = (row.get("aptamerbase_id") or "").strip()
        if not uri:
            continue
        n_id += 1
        if uri in graph.types or uri in graph.is_participant_in:
            n_join += 1
        if graph.is_participant_in.get(uri):
            n_inter += 1
            if any(
                item.kind == "aptamer_target" and item.label
                for item in _counterparts_for_aptamer(graph, uri)
            ):
                n_target += 1
    return {
        "authorised_rows": len(rows),
        "nonempty_aptamerbase_id": n_id,
        "rdf_subject_joined": n_join,
        "has_interaction": n_inter,
        "has_aptamer_target_counterpart": n_target,
        "rdf_statements_scanned": graph.statement_count,
    }
