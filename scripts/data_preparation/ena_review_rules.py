"""Rules for ENA candidate consolidation and clerical review.

Builds on ``ena_candidate_rules`` without replacing prior stages. Pure,
deterministic helpers for target repair, sequence-quality classification,
exact/near-duplicate grouping, binding-evidence scope, and review eligibility.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

from ena_candidate_rules import (
    PROTEIN_COMPATIBLE_TARGET_TYPES,
    T7_PROMOTER_DNA,
    T7_PROMOTER_RNA,
    classify_target_type,
    rna_normalize_sequence,
    reverse_complement,
    stable_group_id,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONCRETE_BASES = frozenset("ACGU")
IUPAC_AMBIGUITY = frozenset("NRYSWKMBDHV")
IUPAC_ALL = CONCRETE_BASES | IUPAC_AMBIGUITY | frozenset("T")

SEQUENCE_QUALITY_STATUSES = (
    "concrete_candidate_sequence",
    "limited_ambiguity",
    "degenerate_library_template",
    "possible_consensus_pattern",
    "too_short_requires_review",
    "long_construct_requires_review",
    "promoter_or_template_requires_review",
    "missing_or_invalid",
)

LENGTH_STATUSES = (
    "under_15_high_concern",
    "15_to_19_short_review",
    "20_to_120_typical_range",
    "121_to_200_long_but_possible",
    "201_to_500_likely_construct",
    "over_500_construct_or_non_aptamer",
    "missing_length",
)

EVIDENCE_SCOPES = (
    "individual_sequence_quantitative",
    "individual_sequence_qualitative",
    "experiment_or_family_level",
    "patent_claim_level",
    "selection_context_only",
    "none",
)

PROTEIN_COMPATIBLE_REPAIRED = PROTEIN_COMPATIBLE_TARGET_TYPES | frozenset(
    {"protein", "enzyme", "protein_complex", "antibody"}
)

RNA_IDENTITY_PLAUSIBLE = frozenset(
    {
        "explicit_rna_aptamer",
        "rna_molecule_type",
        "rna_described_but_dna_alphabet",
        "possible_dna_template_for_rna",
    }
)

GENERIC_TARGET_PHRASES = frozenset(
    {
        "target protein",
        "detecting target protein by using the same",
        "detecting a target protein using a dna aptamer",
        "preparing same",
        "use thereof",
        "and use thereof",
        "same",
        "protein of interest",
        "treatment of retinal disorders",
        "targeted genome modification",
        "the same",
        "thereof",
        "application thereof",
        "and application thereof",
        "detecting target protein",
        "a target protein",
        "target",
        "protein",
        "the protein",
        "said protein",
        "said target",
        "the target",
        "interest",
    }
)

LIBRARY_PHRASE_RE = re.compile(
    r"(?i)\b(?:random\s+(?:library|region|sequence|pool)|"
    r"variable\s+(?:region|sequence|domain)|"
    r"degenerate\s+(?:pool|library|sequence)|"
    r"N(?:\d+|\{?\d+\}?)\b|"
    r"combinatorial\s+library|"
    r"randomized\s+(?:region|library))\b"
)

COMPOUND_CODE_RE = re.compile(
    r"(?i)^(?:"
    r"[A-Z]{2,6}\d{2,6}"
    r"(?:\s+or\s+an?\s+analogue(?:s)?\s+thereof)?"
    r"|"
    r".*\bor\s+an?\s+analogue(?:s)?\s+thereof\b.*"
    r")$"
)

# Region / domain / subunit of [protein]
REGION_OF_PROTEIN_RE = re.compile(
    r"(?is)^\s*(?:the\s+)?"
    r"(?P<region>"
    r"(?:extracellular|intracellular|cytoplasmic|transmembrane|"
    r"N[\s\-]?terminal|C[\s\-]?terminal|amino[\s\-]?terminal|"
    r"carboxy(?:l)?[\s\-]?terminal|catalytic|binding|"
    r"beta[\s\-]?catenin\s+interaction|"
    r"[A-Za-z0-9\-]+\s+)?"
    r"(?:domain|region|subunit|fragment|motif|epitope|loop|domain\s+of)"
    r")"
    r"\s+of\s+(?:the\s+)?"
    r"(?P<name>.+?)"
    r"(?:\s+protein)?\s*$"
)

# "X region of Y protein" / "X domain of Y"
X_OF_Y_PROTEIN_RE = re.compile(
    r"(?is)^\s*(?:the\s+)?"
    r"(?P<region>[A-Za-z0-9][A-Za-z0-9\-\s]{0,40}?\s+(?:region|domain|subunit|fragment))"
    r"\s+of\s+(?:the\s+)?"
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9αβγδε\-\s/()]{0,60}?)"
    r"(?:\s+protein)?\s*$"
)

SURFACE_PROTEIN_RE = re.compile(
    r"(?is)^\s*(?P<region>surface\s+protein)\s+"
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9\-_]*)"
    r"(?:\s+of\s+(?P<organism>.+))?$"
)

CAPSID_RE = re.compile(
    r"(?is)^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9\-_]*)\s+"
    r"(?P<region>capsid(?:\s+protein)?)\b"
    r"(?P<rest>.*)$"
)

NONSTRUCTURAL_RE = re.compile(
    r"(?is)^\s*(?P<region>non[\s\-]?structural\s+protein)\s+"
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9\-_]*)"
    r"(?:\s+of\s+(?P<organism>.+))?$"
)

TRUNCATION_HINT_RE = re.compile(
    r"(?i)\b(?:core|motif|truncat(?:ed|ion)|minimal|fragment|shortened|"
    r"stem[\s\-]?loop|seed)\b"
)

PATENT_CLAIM_RE = re.compile(
    r"(?i)\b(?:patent|WO\s*\d|US\s*\d|EP\s*\d|invention|claims?\b|"
    r"use\s+thereof|and\s+use\s+thereof)\b"
)

QUANTITATIVE_BINDING_RE = re.compile(
    r"(?i)\b(?:Kd|KD|Ka|KA|IC50|EC50|Ki|KI)\b"
)

INDIVIDUAL_ASSAY_RE = re.compile(
    r"(?i)\b(?:SPR|BLI|ELISA|filter[\s\-]?binding|EMSA|"
    r"pull[\s\-]?down|ITC|MST|affinity\s+chromatography|"
    r"measured\s+(?:Kd|affinity)|dissociation\s+constant)\b"
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TargetRepairResult:
    target_raw: str = ""
    target_proposed: str = ""
    target_type_proposed: str = "unknown"
    target_region_proposed: str = ""
    target_organism_or_context: str = ""
    target_key: str = ""
    repair_action: str = "unchanged"
    evidence_phrase: str = ""
    candidate_names: list[str] = field(default_factory=list)
    notes: str = ""
    was_generic: bool = False
    type_changed: bool = False
    region_extracted: bool = False
    unresolved: bool = False

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d["candidate_names"] = "|".join(self.candidate_names)
        return d


@dataclass
class SequenceQualityResult:
    sequence_rna: str = ""
    sequence_length: int = 0
    is_concrete: bool = False
    contains_ambiguous_bases: bool = False
    ambiguous_base_count: int = 0
    ambiguous_base_fraction: float = 0.0
    longest_ambiguous_run: int = 0
    ambiguity_symbols_present: str = ""
    contains_t7_promoter: bool = False
    sequence_quality_status: str = "missing_or_invalid"
    length_status: str = "missing_length"
    library_phrase_hit: bool = False

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Target helpers
# ---------------------------------------------------------------------------


def normalize_target_key(name: str) -> str:
    """Canonical key so FGF2 and FGF-2 consolidate."""
    if not name:
        return ""
    text = name.upper().strip()
    text = text.replace("Α", "A").replace("Β", "B").replace("Γ", "G")
    text = re.sub(r"[^A-Z0-9]+", "", text)
    return text


def _strip_trailing_junk(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" .,;:\"'")
    text = re.sub(
        r"(?i)\s+(?:inhibiting|and\s+use(?:\s+thereof)?|use\s+thereof|"
        r"complete\s+sequence|partial\s+sequence|generated\s+by.*|"
        r"from\s+SELEX.*|with\s+high\s+affinity.*)$",
        "",
        text,
    ).strip(" .,;:\"'")
    return text


def is_generic_target_phrase(text: str) -> bool:
    cleaned = _strip_trailing_junk(text).lower().strip()
    cleaned = re.sub(r"^(?:the\s+)+", "", cleaned).strip()
    if not cleaned:
        return True
    if cleaned in GENERIC_TARGET_PHRASES:
        return True
    # soft match: phrase is only generic words
    if re.fullmatch(
        r"(?i)(?:the\s+)?(?:detecting\s+)?(?:a\s+)?target(?:\s+protein)?"
        r"(?:\s+by\s+using\s+the\s+same)?|"
        r"(?:preparing\s+)?same|"
        r"(?:and\s+)?(?:use|application)\s+thereof|"
        r"treatment\s+of\s+retinal\s+disorders|"
        r"targeted\s+genome\s+modification",
        cleaned,
    ):
        return True
    return False


def is_probable_compound_code(text: str) -> bool:
    cleaned = _strip_trailing_junk(text)
    if not cleaned:
        return False
    if re.search(r"(?i)\banalogue(?:s)?\s+thereof\b", cleaned):
        return True
    # Alphanumeric compound-like codes without protein keywords
    if re.fullmatch(r"[A-Za-z]{1,6}\d{2,8}(?:[A-Za-z]{0,3})?", cleaned):
        if not re.search(r"(?i)\b(?:protein|enzyme|kinase|ase|antibody|IgG)\b", cleaned):
            return True
    if COMPOUND_CODE_RE.fullmatch(cleaned):
        if not re.search(r"(?i)\b(?:protein|enzyme|kinase|antibody)\b", cleaned):
            return True
    return False


def _clean_protein_name(name: str) -> str:
    name = _strip_trailing_junk(name)
    name = re.sub(r"(?i)^(the\s+)+", "", name).strip()
    name = re.sub(r"(?i)\s+protein$", "", name).strip()
    # Fix glued tokens like "ofTCF-1"
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .,;:\"'")
    return name


def parse_structured_target(raw: str) -> dict[str, str] | None:
    """Extract name / region / organism from common free-text forms."""
    text = _strip_trailing_junk(raw)
    if not text:
        return None

    m = SURFACE_PROTEIN_RE.match(text)
    if m:
        return {
            "target_name": m.group("name").strip(),
            "target_region": m.group("region").strip(),
            "target_organism_or_context": (m.group("organism") or "").strip(),
            "evidence_phrase": m.group(0)[:300],
            "pattern": "surface_protein",
        }

    m = NONSTRUCTURAL_RE.match(text)
    if m:
        return {
            "target_name": m.group("name").strip(),
            "target_region": m.group("region").strip(),
            "target_organism_or_context": (m.group("organism") or "").strip(),
            "evidence_phrase": m.group(0)[:300],
            "pattern": "nonstructural_protein",
        }

    m = CAPSID_RE.match(text)
    if m:
        virus = m.group("name").strip()
        region = m.group("region").strip()
        return {
            "target_name": f"{virus} capsid protein",
            "target_region": region if "protein" in region.lower() else f"{region} protein",
            "target_organism_or_context": "",
            "evidence_phrase": m.group(0)[:300],
            "pattern": "capsid",
        }

    m = REGION_OF_PROTEIN_RE.match(text)
    if m:
        region = re.sub(r"\s+", " ", m.group("region")).strip()
        # Avoid matching "domain of" alone as region when pattern swallowed "of"
        region = re.sub(r"(?i)\s+of$", "", region).strip()
        name = _clean_protein_name(m.group("name"))
        if name and len(name) >= 1:
            return {
                "target_name": name,
                "target_region": region,
                "target_organism_or_context": "",
                "evidence_phrase": m.group(0)[:300],
                "pattern": "region_of_protein",
            }

    m = X_OF_Y_PROTEIN_RE.match(text)
    if m:
        region = re.sub(r"\s+", " ", m.group("region")).strip()
        name = _clean_protein_name(m.group("name"))
        if name and len(name) >= 1:
            return {
                "target_name": name,
                "target_region": region,
                "target_organism_or_context": "",
                "evidence_phrase": m.group(0)[:300],
                "pattern": "x_of_y_protein",
            }

    return None


def repair_target(
    target_raw: str,
    target_type: str = "",
    target_normalized: str = "",
    context_text: str = "",
) -> TargetRepairResult:
    """Improve target parsing before exact-sequence deduplication."""
    raw = str(target_raw or "").strip()
    prior_type = str(target_type or "").strip() or "unknown"
    prior_norm = str(target_normalized or "").strip() or raw
    result = TargetRepairResult(
        target_raw=raw,
        target_proposed=prior_norm,
        target_type_proposed=prior_type,
        evidence_phrase=raw[:300],
    )

    if not raw:
        result.repair_action = "empty_target"
        result.target_proposed = ""
        result.target_type_proposed = "unknown"
        result.target_key = "UNKNOWN"
        result.unresolved = True
        return result

    if is_generic_target_phrase(raw):
        result.was_generic = True
        result.target_proposed = "unknown"
        result.target_type_proposed = "unknown"
        result.target_key = "UNKNOWN"
        result.repair_action = "generic_to_unknown"
        result.unresolved = True
        result.type_changed = prior_type != "unknown"
        result.notes = "generic_target_phrase"
        return result

    if is_probable_compound_code(raw):
        result.target_proposed = _strip_trailing_junk(raw)
        result.target_type_proposed = "unknown_or_probable_small_molecule"
        result.target_key = normalize_target_key(result.target_proposed) or "UNKNOWN_COMPOUND"
        result.repair_action = "compound_code_not_protein"
        result.type_changed = prior_type != result.target_type_proposed
        result.notes = "probable_compound_or_analogue_language"
        return result

    structured = parse_structured_target(raw)
    if structured:
        name = structured["target_name"]
        region = structured["target_region"]
        organism = structured.get("target_organism_or_context", "")
        result.target_proposed = name
        result.target_region_proposed = region
        result.target_organism_or_context = organism
        result.evidence_phrase = structured["evidence_phrase"]
        result.region_extracted = bool(region)
        result.candidate_names = [name]
        # Classify type from repaired name + context
        blob = f"{name} {region} {organism} {context_text}"
        ttype, note = classify_target_type(name, blob)
        # Capsid / surface protein forms are protein-compatible
        if structured["pattern"] in {"capsid", "surface_protein", "nonstructural_protein"}:
            if ttype not in PROTEIN_COMPATIBLE_REPAIRED:
                ttype = "protein"
                note = f"{note}|forced_protein_from_{structured['pattern']}"
        if structured["pattern"] in {"region_of_protein", "x_of_y_protein"} and ttype == "unknown":
            ttype = "protein"
            note = f"{note}|region_of_named_protein"
        result.target_type_proposed = ttype
        result.target_key = normalize_target_key(name)
        result.repair_action = f"structured_{structured['pattern']}"
        result.type_changed = ttype != prior_type
        result.notes = note
        result.unresolved = ttype in {"unknown", "unknown_or_probable_small_molecule"}
        return result

    # Unstructured: keep cleaned name, reclassify type cautiously
    cleaned = _strip_trailing_junk(raw)
    result.target_proposed = cleaned or raw
    ttype, note = classify_target_type(cleaned, context_text)
    # Do not upgrade unknown to protein solely because prior stage said protein
    # when phrase looks non-protein; but keep enzyme/antibody if lexicon hits.
    if is_probable_compound_code(cleaned):
        ttype = "unknown_or_probable_small_molecule"
        note = "probable_compound_code"
    result.target_type_proposed = ttype
    result.target_key = normalize_target_key(result.target_proposed) or "UNKNOWN"
    result.repair_action = "reclassified" if ttype != prior_type else "unchanged"
    result.type_changed = ttype != prior_type
    result.notes = note
    result.unresolved = ttype in {"unknown", "unknown_or_probable_small_molecule", ""} or not cleaned
    return result


def targets_are_equivalent(a: str, b: str) -> bool:
    ka, kb = normalize_target_key(a), normalize_target_key(b)
    if not ka or not kb:
        return False
    return ka == kb


# ---------------------------------------------------------------------------
# Sequence quality
# ---------------------------------------------------------------------------


def recoverable_rna_sequence(
    sequence_rna_normalized: str = "",
    sequence_deposited: str = "",
) -> str:
    """Prefer existing RNA-normalised form; else T→U on deposited if usable."""
    rna = str(sequence_rna_normalized or "").strip().upper().replace(" ", "")
    if rna:
        return rna
    dep = str(sequence_deposited or "").strip().upper().replace(" ", "")
    if not dep:
        return ""
    # Recover only if alphabet is DNA/RNA/IUPAC (no other junk)
    if all(ch in IUPAC_ALL for ch in dep):
        return rna_normalize_sequence(dep)
    return ""


def longest_run_of(seq: str, chars: Iterable[str]) -> int:
    charset = set(c.upper() for c in chars)
    best = cur = 0
    for ch in seq.upper():
        if ch in charset:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def classify_length(length: int) -> str:
    if length <= 0:
        return "missing_length"
    if length < 15:
        return "under_15_high_concern"
    if length < 20:
        return "15_to_19_short_review"
    if length <= 120:
        return "20_to_120_typical_range"
    if length <= 200:
        return "121_to_200_long_but_possible"
    if length <= 500:
        return "201_to_500_likely_construct"
    return "over_500_construct_or_non_aptamer"


def assess_sequence_quality(
    sequence_rna: str,
    description: str = "",
    sequence_role: str = "",
    contains_t7_flag: Any = False,
) -> SequenceQualityResult:
    seq = str(sequence_rna or "").strip().upper().replace(" ", "")
    result = SequenceQualityResult(sequence_rna=seq, sequence_length=len(seq))
    if not seq:
        result.sequence_quality_status = "missing_or_invalid"
        result.length_status = "missing_length"
        return result

    amb_chars = sorted({ch for ch in seq if ch in IUPAC_AMBIGUITY})
    amb_count = sum(1 for ch in seq if ch in IUPAC_AMBIGUITY)
    invalid = [ch for ch in seq if ch not in CONCRETE_BASES and ch not in IUPAC_AMBIGUITY]
    result.ambiguous_base_count = amb_count
    result.ambiguous_base_fraction = amb_count / len(seq) if seq else 0.0
    result.longest_ambiguous_run = longest_run_of(seq, IUPAC_AMBIGUITY)
    result.ambiguity_symbols_present = "".join(amb_chars)
    result.contains_ambiguous_bases = amb_count > 0
    result.is_concrete = amb_count == 0 and not invalid
    result.length_status = classify_length(len(seq))

    t7 = bool(contains_t7_flag) if not isinstance(contains_t7_flag, str) else contains_t7_flag.strip().lower() in {
        "1", "true", "yes", "t"
    }
    if T7_PROMOTER_RNA in seq or T7_PROMOTER_DNA in seq.replace("U", "T"):
        t7 = True
    result.contains_t7_promoter = t7

    blob = f"{description} {sequence_role}"
    result.library_phrase_hit = bool(LIBRARY_PHRASE_RE.search(blob))

    if invalid:
        result.sequence_quality_status = "missing_or_invalid"
        return result

    is_library = (
        amb_count >= 5
        or result.ambiguous_base_fraction >= 0.10
        or longest_run_of(seq, "N") >= 4
        or result.library_phrase_hit
    )
    if is_library:
        result.sequence_quality_status = "degenerate_library_template"
        return result

    if amb_count > 0 and amb_count <= 2 and result.ambiguous_base_fraction < 0.10:
        # limited ambiguity — still reviewable
        base_status = "limited_ambiguity"
    elif amb_count > 2:
        base_status = "possible_consensus_pattern"
    else:
        base_status = "concrete_candidate_sequence"

    if t7 or re.search(r"(?i)promoter|transcription\s+template|dna\s+template", blob):
        if base_status == "concrete_candidate_sequence":
            result.sequence_quality_status = "promoter_or_template_requires_review"
            return result

    if result.length_status == "over_500_construct_or_non_aptamer":
        result.sequence_quality_status = "long_construct_requires_review"
        return result
    if result.length_status == "201_to_500_likely_construct":
        result.sequence_quality_status = "long_construct_requires_review"
        return result
    if result.length_status in {"under_15_high_concern", "15_to_19_short_review"}:
        # Short but concrete/limited — flag via length; quality stays concrete/limited
        if base_status in {"concrete_candidate_sequence", "limited_ambiguity"}:
            result.sequence_quality_status = (
                "too_short_requires_review"
                if result.length_status == "under_15_high_concern"
                else base_status
            )
            return result

    result.sequence_quality_status = base_status
    return result


# ---------------------------------------------------------------------------
# Binding evidence scope
# ---------------------------------------------------------------------------


def classify_evidence_scope(
    binding_evidence_status: str = "",
    binding_evidence_types: str = "",
    binding_evidence_strength: str = "",
    binding_evidence_text: str = "",
    selection_evidence: str = "",
    description: str = "",
    reference_titles: str = "",
    accession_count: int = 1,
) -> str:
    """Distinguish individual vs family/patent-level binding claims."""
    status = str(binding_evidence_status or "")
    types = str(binding_evidence_types or "")
    strength = str(binding_evidence_strength or "")
    text = " || ".join(
        [
            str(binding_evidence_text or ""),
            str(selection_evidence or ""),
            str(description or ""),
            str(reference_titles or ""),
            status,
            types,
        ]
    )

    if strength in {"", "none"} and status in {"", "none_found", "none"}:
        if selection_evidence and selection_evidence not in {"none", "none_found", ""}:
            return "selection_context_only"
        return "none"

    if QUANTITATIVE_BINDING_RE.search(text) or "explicit_affinity" in types or status == "explicit_affinity":
        # Quantitative claims in patents often apply to the family, not each clone
        if PATENT_CLAIM_RE.search(text) and accession_count > 1 and not INDIVIDUAL_ASSAY_RE.search(text):
            return "patent_claim_level"
        if INDIVIDUAL_ASSAY_RE.search(text) or accession_count == 1:
            return "individual_sequence_quantitative"
        return "experiment_or_family_level"

    if status in {
        "explicit_binds_or_recognizes_statement",
        "inhibition_or_functional_effect",
    } or any(
        t in types
        for t in (
            "explicit_binds_or_recognizes_statement",
            "inhibition_or_functional_effect",
        )
    ):
        if PATENT_CLAIM_RE.search(text) or accession_count > 3:
            # Family-level patent wording
            if accession_count > 1:
                return "patent_claim_level"
        if accession_count == 1 and INDIVIDUAL_ASSAY_RE.search(text):
            return "individual_sequence_qualitative"
        if accession_count == 1:
            return "individual_sequence_qualitative"
        return "experiment_or_family_level"

    if status == "selection_against_target" or "selection" in types.lower():
        return "selection_context_only"

    if status == "publication_title_only" or "publication_title_only" in types:
        return "patent_claim_level" if PATENT_CLAIM_RE.search(text) else "experiment_or_family_level"

    if strength not in {"", "none"}:
        return "experiment_or_family_level"
    return "none"


_SCOPE_RANK = {
    "individual_sequence_quantitative": 5,
    "individual_sequence_qualitative": 4,
    "experiment_or_family_level": 3,
    "patent_claim_level": 2,
    "selection_context_only": 1,
    "none": 0,
}


def strongest_evidence_scope(scopes: Iterable[str]) -> str:
    best = "none"
    best_rank = -1
    for s in scopes:
        r = _SCOPE_RANK.get(s, -1)
        if r > best_rank:
            best = s
            best_rank = r
    return best


def strongest_binding_summary(rows: Sequence[dict[str, Any]]) -> tuple[str, str]:
    """Return (summary_text, level) without upgrading family → individual."""
    scopes = []
    summaries = []
    for r in rows:
        scope = r.get("evidence_scope") or classify_evidence_scope(
            binding_evidence_status=str(r.get("binding_evidence_status", "")),
            binding_evidence_types=str(r.get("binding_evidence_types", "")),
            binding_evidence_strength=str(r.get("binding_evidence_strength", "")),
            binding_evidence_text=str(r.get("binding_evidence_text", "")),
            selection_evidence=str(r.get("selection_evidence", "")),
            description=str(r.get("description", "")),
            reference_titles=str(r.get("reference_titles", "")),
            accession_count=1,
        )
        scopes.append(scope)
        strength = str(r.get("binding_evidence_strength", "") or "none")
        types = str(r.get("binding_evidence_types", "") or "")
        text = str(r.get("binding_evidence_text", "") or "")[:200]
        summaries.append(f"{strength}:{types}:{text}".strip(":"))
    best_scope = strongest_evidence_scope(scopes)
    # Prefer summary from a row that achieved best_scope
    chosen = ""
    for r, scope, summary in zip(rows, scopes, summaries):
        if scope == best_scope and summary:
            chosen = summary
            break
    if not chosen and summaries:
        chosen = summaries[0]
    return chosen, best_scope


# ---------------------------------------------------------------------------
# Near-duplicate relationships
# ---------------------------------------------------------------------------


def hamming_distance(a: str, b: str) -> int | None:
    if len(a) != len(b):
        return None
    return sum(x != y for x, y in zip(a, b))


def levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Ensure a is shorter for memory
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(a) + 1))
    for j, cb in enumerate(b, start=1):
        cur = [j]
        for i, ca in enumerate(a, start=1):
            ins = cur[i - 1] + 1
            delete = prev[i] + 1
            sub = prev[i - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def equal_length_near_duplicate_threshold(length: int) -> int:
    return max(2, math.ceil(0.05 * length))


def classify_sequence_relationship(a: str, b: str) -> str:
    """Conservative relationship label between two concrete RNA sequences."""
    if not a or not b:
        return "unrelated"
    if a == b:
        return "exact duplicate"
    # Reverse complement (RNA alphabet)
    rc = reverse_complement(a.replace("U", "T")).replace("T", "U")
    if rc == b:
        return "reverse-complement relationship"

    if len(a) == len(b):
        d = hamming_distance(a, b)
        assert d is not None
        thr = equal_length_near_duplicate_threshold(len(a))
        if d <= thr:
            if d == 1:
                return "single substitution"
            return "small Hamming-distance variant"
        return "unrelated"

    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 15 and shorter in longer and (len(shorter) / len(longer)) >= 0.5:
        if longer.startswith(shorter) or longer.endswith(shorter):
            return "prefix/suffix truncation"
        return "internal substring/core relationship"
    # Extension with flanking bases: edit distance dominated by length gap
    edit = levenshtein_distance(a, b)
    max_len = max(len(a), len(b))
    if max_len and (edit / max_len) <= 0.08:
        if shorter in longer:
            return "extension with flanking bases"
        return "small edit-distance variant"
    return "unrelated"


def are_near_duplicates(a: str, b: str) -> bool:
    rel = classify_sequence_relationship(a, b)
    return rel != "unrelated"


def assign_near_duplicate_families(
    units: list[dict[str, Any]],
    seq_key: str = "rna_sequence",
    group_key: str = "experiment_group_id",
    target_key: str = "target_key",
    id_key: str = "review_unit_id",
) -> tuple[dict[str, str], dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Assign near-duplicate family IDs within (experiment_group, target).

    Returns:
        unit_id → family_id
        family_id → summary dict
        unit_id → list of relationship strings to other family members
    """
    from collections import defaultdict

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for u in units:
        g = str(u.get(group_key, "") or "")
        t = str(u.get(target_key, "") or "")
        seq = str(u.get(seq_key, "") or "")
        # Only concrete sequences participate in near-dup clustering
        if not seq or any(ch not in CONCRETE_BASES for ch in seq):
            continue
        buckets[(g, t)].append(u)

    unit_to_family: dict[str, str] = {}
    unit_relationships: dict[str, list[str]] = defaultdict(list)
    family_summaries: dict[str, dict[str, Any]] = {}

    for (g, t), members in buckets.items():
        n = len(members)
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

        edge_labels: dict[tuple[int, int], str] = {}
        for i in range(n):
            for j in range(i + 1, n):
                sa = members[i][seq_key]
                sb = members[j][seq_key]
                rel = classify_sequence_relationship(sa, sb)
                if rel != "unrelated":
                    union(i, j)
                    edge_labels[(i, j)] = rel

        components: dict[int, list[int]] = defaultdict(list)
        for i in range(n):
            components[find(i)].append(i)

        for root, idxs in components.items():
            if len(idxs) < 2:
                # Singletons get no family id (or optional self family — spec says
                # near_duplicate_family_id for related sets; leave blank for singles)
                continue
            seqs = [members[i][seq_key] for i in idxs]
            ids = [str(members[i][id_key]) for i in idxs]
            fam_key = f"{g}|{t}|{'|'.join(sorted(ids))}"
            fam_id = stable_group_id("ndfam", fam_key)

            rels_present = set()
            id_by_idx = {i: str(members[i][id_key]) for i in idxs}
            for i in idxs:
                for j in idxs:
                    if i >= j:
                        continue
                    rel = edge_labels.get((i, j)) or edge_labels.get((j, i))
                    if rel is None:
                        rel = classify_sequence_relationship(
                            members[i][seq_key], members[j][seq_key]
                        )
                    if rel != "unrelated":
                        rels_present.add(rel)
                        unit_relationships[id_by_idx[i]].append(f"{id_by_idx[j]}:{rel}")
                        unit_relationships[id_by_idx[j]].append(f"{id_by_idx[i]}:{rel}")

            for i in idxs:
                unit_to_family[str(members[i][id_key])] = fam_id

            # Exact-duplicate subgroups within family (should be rare after exact collapse)
            exact_groups = defaultdict(list)
            for i in idxs:
                exact_groups[members[i][seq_key]].append(str(members[i][id_key]))
            exact_sub = [ids_ for ids_ in exact_groups.values() if len(ids_) > 1]

            trunc_series = any(
                r
                in {
                    "prefix/suffix truncation",
                    "internal substring/core relationship",
                    "extension with flanking bases",
                }
                for r in rels_present
            )
            point_series = any(
                r in {"single substitution", "small Hamming-distance variant"}
                for r in rels_present
            )

            lengths = sorted({len(s) for s in seqs})
            # Representative: median length, then lexicographically first
            med_len = lengths[len(lengths) // 2]
            candidates = sorted([s for s in seqs if len(s) == med_len]) or sorted(seqs)
            rep = candidates[0]

            concerns = []
            if any(r == "reverse-complement relationship" for r in rels_present):
                concerns.append("contains_reverse_complements")
            if trunc_series:
                concerns.append("possible_truncation_series")
            if point_series:
                concerns.append("possible_point_mutation_series")

            family_summaries[fam_id] = {
                "family_id": fam_id,
                "experiment_group_id": g,
                "target_proposed": t,  # caller may overwrite with display name
                "member_count": len(idxs),
                "review_unit_ids": "|".join(sorted(ids)),
                "sequence_lengths": "|".join(str(x) for x in lengths),
                "representative_sequence": rep,
                "relationship_summary": "|".join(sorted(rels_present)),
                "exact_duplicate_subgroups": str(len(exact_sub)),
                "possible_truncation_series": "1" if trunc_series else "0",
                "possible_point_mutation_series": "1" if point_series else "0",
                "family_concerns": ";".join(concerns),
            }

    return unit_to_family, family_summaries, dict(unit_relationships)


def short_sequence_family_context(
    short_seq: str,
    family_seqs: Sequence[str],
    description: str = "",
) -> dict[str, str]:
    """Annotate whether a short sequence relates to longer family members."""
    longer = [s for s in family_seqs if s and len(s) > len(short_seq)]
    is_sub = any(short_seq in s for s in longer)
    return {
        "longer_related_variants_exist": "1" if longer else "0",
        "is_substring_of_longer_member": "1" if is_sub else "0",
        "truncation_or_motif_language": "1" if TRUNCATION_HINT_RE.search(description or "") else "0",
    }


# ---------------------------------------------------------------------------
# Review eligibility
# ---------------------------------------------------------------------------


def is_protein_compatible_type(ttype: str) -> bool:
    return ttype in PROTEIN_COMPATIBLE_REPAIRED


def review_eligibility(
    *,
    rna_identity_status: str,
    target_type_proposed: str,
    sequence_quality_status: str,
    length_status: str,
    evidence_scope: str,
    binding_evidence_summary: str = "",
    selection_evidence_summary: str = "",
    descriptions: str = "",
) -> tuple[bool, str]:
    """Return (eligible_for_main_template, exclusion_bucket)."""
    if rna_identity_status and rna_identity_status not in RNA_IDENTITY_PLAUSIBLE:
        if rna_identity_status == "dna_aptamer":
            return False, "dna_aptamer"
        return False, "rna_identity_not_plausible"

    if not is_protein_compatible_type(target_type_proposed):
        if target_type_proposed in {"small_molecule", "unknown_or_probable_small_molecule"}:
            return False, "small_molecule_targets"
        if target_type_proposed in {"cell_or_tissue", "virus_or_virion"}:
            return False, "cell_or_virus_without_named_protein"
        if target_type_proposed in {"unknown", ""}:
            return False, "generic_target_only_records"
        return False, f"non_protein_target:{target_type_proposed}"

    if sequence_quality_status == "degenerate_library_template":
        return False, "degenerate_library_templates"
    if sequence_quality_status == "missing_or_invalid":
        return False, "missing_sequences"
    if sequence_quality_status == "long_construct_requires_review":
        return False, "very_long_constructs"
    if length_status == "over_500_construct_or_non_aptamer":
        return False, "very_long_constructs"

    if sequence_quality_status not in {
        "concrete_candidate_sequence",
        "limited_ambiguity",
        "too_short_requires_review",
        "promoter_or_template_requires_review",
        "possible_consensus_pattern",
    }:
        return False, f"sequence_quality:{sequence_quality_status}"

    has_claim = evidence_scope not in {"none", ""}
    summary = str(binding_evidence_summary or "").strip()
    if summary and not summary.startswith("none") and summary not in {":", "none:"}:
        has_claim = True
    sel = str(selection_evidence_summary or "").strip()
    if sel and sel not in {"none", "none_found", ""}:
        has_claim = True
    # Aptamer + named protein in patent/description counts as a family-level claim
    if not has_claim and re.search(r"(?i)\baptamers?\b", descriptions or ""):
        has_claim = True
    if not has_claim:
        return False, "no_binding_or_selection_claim"

    return True, ""


def validate_manual_include(value: Any) -> str | None:
    """Return normalised value ('', '0', '1') or None if invalid."""
    if value is None:
        return ""
    s = str(value).strip()
    if s == "":
        return ""
    if s in {"0", "1"}:
        return s
    return None


def join_unique(values: Iterable[Any], sep: str = " | ") -> str:
    seen: list[str] = []
    for v in values:
        s = str(v or "").strip()
        if not s:
            continue
        if s not in seen:
            seen.append(s)
    return sep.join(seen)
