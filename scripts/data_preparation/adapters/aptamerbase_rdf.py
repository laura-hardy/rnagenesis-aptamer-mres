"""Stream AptamerBase supporting RDF for S2 typing only.

The gzip N-Triples extract is supporting metadata. It must not create corpus
rows. Only type and modification-detail predicates required by S2 are
collected. Target, interaction, affinity, publication and evidence graph
structure are ignored.
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable, Mapping

_NT_RE: Final[re.Pattern[str]] = re.compile(
    r"^<([^>]*)>\s+<([^>]*)>\s+(.*)\s+\.\s*$"
)
_LITERAL_RE: Final[re.Pattern[str]] = re.compile(
    r'^"(?:\\.|[^"\\])*"'
)


class AptamerBaseRdfError(ValueError):
    """Hard failure while reading AptamerBase supporting RDF."""


@dataclass(frozen=True)
class AptamerBaseRdfSubjectFacts:
    """Per-subject type facts used by AptamerBase S2."""

    subject_uri: str
    rdf_type_objects: frozenset[str]
    freebase_type_objects: frozenset[str]
    union_types: frozenset[str]
    has_rna: bool
    has_dna: bool
    has_aptamer: bool
    has_nucleic_acid: bool
    has_linear_polymer: bool
    has_modified_nucleic_acid: bool
    has_minimal_aptamer: bool
    has_secondary_structure: bool
    has_predicted_secondary_structure: bool
    has_modification_details_literal: bool


@dataclass(frozen=True)
class AptamerBaseRdfIndex:
    """Subject-keyed RDF typing index plus statement coverage."""

    subjects: dict[str, AptamerBaseRdfSubjectFacts]
    statement_count: int


def _unescape_literal(body: str) -> str:
    return (
        body.replace(r"\\", "\\")
        .replace(r"\"", '"')
        .replace(r"\n", "\n")
        .replace(r"\t", "\t")
        .replace(r"\r", "\r")
    )


def parse_ntriples_line(line: str) -> tuple[str, str, str, str] | None:
    """Parse one N-Triples statement into subject, predicate, kind, object.

    ``kind`` is ``uri`` or ``literal``. Returns None for comments/blank lines.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    match = _NT_RE.match(stripped)
    if match is None:
        raise AptamerBaseRdfError("unparseable N-Triples statement in supporting RDF")
    subject, predicate, raw_object = match.group(1), match.group(2), match.group(3)
    if raw_object.startswith("<") and raw_object.endswith(">"):
        return subject, predicate, "uri", raw_object[1:-1]
    if raw_object.startswith('"'):
        lit = _LITERAL_RE.match(raw_object)
        if lit is None:
            raise AptamerBaseRdfError("unparseable N-Triples literal in supporting RDF")
        body = lit.group(0)[1:-1]
        return subject, predicate, "literal", _unescape_literal(body)
    raise AptamerBaseRdfError("unsupported N-Triples object form in supporting RDF")


def _relevant_type_set(
    objects: Iterable[str],
    type_uris: Mapping[str, str],
) -> frozenset[str]:
    wanted = frozenset(type_uris.values())
    return frozenset(obj for obj in objects if obj in wanted)


def _facts_for_subject(
    subject_uri: str,
    *,
    rdf_types: set[str],
    freebase_types: set[str],
    has_modification_literal: bool,
    type_uris: Mapping[str, str],
) -> AptamerBaseRdfSubjectFacts:
    rdf_relevant = _relevant_type_set(rdf_types, type_uris)
    freebase_relevant = _relevant_type_set(freebase_types, type_uris)
    if rdf_relevant and freebase_relevant and rdf_relevant != freebase_relevant:
        # Both predicates were audited as agreeing; disagreement fails closed.
        raise AptamerBaseRdfError(
            "RDF rdf:type and Freebase type.object.type disagree for a "
            "supporting subject"
        )
    union_types = frozenset(rdf_relevant | freebase_relevant)
    return AptamerBaseRdfSubjectFacts(
        subject_uri=subject_uri,
        rdf_type_objects=rdf_relevant,
        freebase_type_objects=freebase_relevant,
        union_types=union_types,
        has_rna=type_uris["rna"] in union_types,
        has_dna=type_uris["dna"] in union_types,
        has_aptamer=type_uris["aptamer"] in union_types,
        has_nucleic_acid=type_uris["nucleic_acid"] in union_types,
        has_linear_polymer=type_uris["linear_polymer"] in union_types,
        has_modified_nucleic_acid=type_uris["modified_nucleic_acid"] in union_types,
        has_minimal_aptamer=type_uris["minimal_aptamer"] in union_types,
        has_secondary_structure=(
            type_uris["nucleic_acid_secondary_structure"] in union_types
        ),
        has_predicted_secondary_structure=(
            type_uris["predicted_secondary_structure"] in union_types
        ),
        has_modification_details_literal=has_modification_literal,
    )


def load_aptamerbase_rdf_index(
    path: str | Path,
    *,
    rdf_type_predicate: str,
    freebase_type_predicate: str,
    modification_details_predicate: str,
    type_uris: Mapping[str, str],
    expected_statements: int | None = None,
) -> AptamerBaseRdfIndex:
    """Stream gzip N-Triples and collect S2 type facts per subject URI."""
    rdf_path = Path(path)
    rdf_types: dict[str, set[str]] = {}
    freebase_types: dict[str, set[str]] = {}
    modification_literal: dict[str, bool] = {}
    statement_count = 0

    try:
        with gzip.open(rdf_path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                statement_count += 1
                if (
                    rdf_type_predicate not in line
                    and freebase_type_predicate not in line
                    and modification_details_predicate not in line
                ):
                    continue
                parsed = parse_ntriples_line(line)
                if parsed is None:
                    continue
                subject, predicate, kind, obj = parsed
                if predicate == rdf_type_predicate and kind == "uri":
                    rdf_types.setdefault(subject, set()).add(obj)
                elif predicate == freebase_type_predicate and kind == "uri":
                    freebase_types.setdefault(subject, set()).add(obj)
                elif predicate == modification_details_predicate and kind == "literal":
                    if obj.strip():
                        modification_literal[subject] = True
    except gzip.BadGzipFile as exc:
        raise AptamerBaseRdfError("supporting RDF gzip is corrupt") from exc
    except OSError as exc:
        raise AptamerBaseRdfError(
            f"cannot read supporting RDF: {exc.strerror}"
        ) from exc

    if expected_statements is not None and statement_count != expected_statements:
        raise AptamerBaseRdfError(
            "supporting RDF statement count does not match the registered "
            f"expectation ({expected_statements} vs {statement_count})"
        )

    subjects: dict[str, AptamerBaseRdfSubjectFacts] = {}
    all_subjects = set(rdf_types) | set(freebase_types) | set(modification_literal)
    for subject in all_subjects:
        subjects[subject] = _facts_for_subject(
            subject,
            rdf_types=rdf_types.get(subject, set()),
            freebase_types=freebase_types.get(subject, set()),
            has_modification_literal=modification_literal.get(subject, False),
            type_uris=type_uris,
        )
    return AptamerBaseRdfIndex(subjects=subjects, statement_count=statement_count)


def require_subject_facts(
    index: AptamerBaseRdfIndex,
    subject_uri: str,
) -> AptamerBaseRdfSubjectFacts:
    """Fail closed when an S1 Freebase ID is absent from the RDF index."""
    facts = index.subjects.get(subject_uri)
    if facts is None:
        raise AptamerBaseRdfError(
            "S1 Freebase ID is absent from the supporting RDF subject index"
        )
    return facts
