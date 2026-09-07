"""Rules for ENA review v2: target repair, evidence scope, group-first workflow.

Stage 4 corrective layer on top of ``ena_review_rules``. Pure, deterministic,
offline helpers. Does not replace prior stages or overwrite review/ outputs.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

from ena_candidate_rules import (
    PROTEIN_COMPATIBLE_TARGET_TYPES,
    T7_PROMOTER_DNA,
    T7_PROMOTER_RNA,
    classify_target_type,
)
from ena_review_rules import (
    GENERIC_TARGET_PHRASES,
    IUPAC_AMBIGUITY,
    PATENT_CLAIM_RE,
    QUANTITATIVE_BINDING_RE,
    INDIVIDUAL_ASSAY_RE,
    PROTEIN_COMPATIBLE_REPAIRED,
    RNA_IDENTITY_PLAUSIBLE,
    is_generic_target_phrase,
    is_probable_compound_code,
    join_unique,
    parse_structured_target,
    validate_manual_include,
)

# ---------------------------------------------------------------------------
# Editable alias dictionary (orthographic / formatting only)
# ---------------------------------------------------------------------------

# Maps a comparison key → preferred display form.
# Keys are produced by ``_orthographic_key`` (alphanumeric uppercase).
# Only safe formatting variants — not biological synonyms.
TARGET_ALIASES: dict[str, str] = {
    # FGF family
    "FGF2": "FGF2",
    "FGF1": "FGF1",
    "FGF21": "FGF21",
    # Interleukins
    "IL17": "IL-17",
    "IL17A": "IL-17A",
    "IL21": "IL-21",
    "IL6": "IL-6",
    "IL8": "IL-8",
    "IL10": "IL-10",
    "IL1": "IL-1",
    "IL1B": "IL-1B",
    "IL1BETA": "IL-1β",
    "IL2": "IL-2",
    "IL4": "IL-4",
    "IL12": "IL-12",
    "IL13": "IL-13",
    "IL15": "IL-15",
    "IL18": "IL-18",
    "IL22": "IL-22",
    "IL23": "IL-23",
    # TNF / related
    "TNFALPHA": "TNF-α",
    "TNFA": "TNF-α",
    "TNFΑ": "TNF-α",
    "TNF": "TNF",
    "TNFR": "TNFR",
    # Common hyphenated protein codes
    "HMGB1": "HMGB1",
    "ADAMTS5": "ADAMTS5",
    "ERBB2": "ErbB2",
    "HER2": "HER2",
    "EGFR": "EGFR",
    "VEGF": "VEGF",
    "VEGFA": "VEGF-A",
    "PDGF": "PDGF",
    "CTHRC1": "CTHRC1",
    "ALPPL2": "ALPPL2",
    "NS5B": "NS5B",
    "PCV2": "PCV2",
    "TSA56": "TSA56",
    # Orthographic / strain-label variants of Orientia surface protein TSA56
    "TST56": "TSA56",
    "TSG56": "TSA56",
}

# Alias orthographic keys that are protein-compatible (not compounds).
KNOWN_PROTEIN_ALIAS_KEYS = frozenset(TARGET_ALIASES.keys())

# Extra orthographic normalisations applied before keying
_GREEK_MAP = str.maketrans(
    {
        "α": "ALPHA",
        "β": "BETA",
        "γ": "GAMMA",
        "δ": "DELTA",
        "ε": "EPSILON",
        "Α": "A",
        "Β": "B",
        "Γ": "G",
    }
)

CONFLICT_TYPES = (
    "no_conflict",
    "orthographic_alias_only",
    "same_target_different_region",
    "genuine_different_target",
    "target_unresolved",
)

EVIDENCE_SCOPES_V2 = (
    "individual_sequence_quantitative",
    "individual_sequence_qualitative",
    "experiment_family_level",
    "patent_claim_level",
    "selection_context_only",
    "none",
)

BINDING_EVIDENCE_TYPES = (
    "target_specific_aptamer_claim",
    "explicit_binding_claim",
    "functional_or_inhibitory_claim",
    "individual_sequence_binding",
    "individual_sequence_affinity",
    "selection_against_target",
    "none",
)

# Map legacy / stage-3 type tokens onto the v2 vocabulary.
_LEGACY_BINDING_TYPE_MAP = {
    "explicit_binds_or_recognizes_statement": "explicit_binding_claim",
    "inhibition_or_functional_effect": "functional_or_inhibitory_claim",
    "explicit_affinity": "individual_sequence_affinity",
    "publication_title_only": "target_specific_aptamer_claim",
    "selection_against_target": "selection_against_target",
    "experiment_family": "explicit_binding_claim",
    "experiment_or_family": "explicit_binding_claim",
    "experiment_family_level": "explicit_binding_claim",
}

GROUP_ACTIONS = (
    "retain_for_group_review",
    "retain_but_sequence_roles_need_review",
    "reject_non_protein_target",
    "reject_unknown_target",
    "reject_platform_or_vector_construct",
    "reject_natural_or_riboswitch",
    "insufficient_information",
)

KNOWN_SMALL_MOLECULES = frozenset(
    {
        "histamine",
        "sphingosylphosphorylcholine",
        "theophylline",
        "dopamine",
        "serotonin",
        "cocaine",
        "atp",
        "gtp",
        "camp",
        "8-oxodg",
        "8-oxo-dg",
        "8-oxodg lesion",
    }
)

GENERIC_EXTRA = frozenset(
    {
        "genome editing enzyme",
        "genome-editing enzyme",
        "detecting target protein by using the same",
        "protein of interest",
        "use thereof",
        "preparing same",
        "treatment of retinal disorders",
        "same",
        "target protein",
    }
)

ACTION_PHRASE_RE = re.compile(
    r"(?is)^\s*(?:purification|isolation|detection|capture|immobilisation|"
    r"immobilization|enrichment)\s+of\s+(?:the\s+)?(?P<name>.+?)\s*$"
)

VIRAL_PROCESS_RE = re.compile(
    r"(?i)\b(?:replication\s+of\b|replicon\b|viral\s+replication|"
    r"infection\s+of\b|life[\s\-]?cycle)\b"
)

EXPLICIT_PROTEIN_WORDING_RE = re.compile(
    r"(?is)^\s*(?:(?:human|mouse|murine|rat|bovine)\s+)?"
    r"(?:(?:surface|capsid|non[\s\-]?structural|membrane|secreted)\s+)?"
    r"protein\s+(?P<name>[A-Za-z0-9][A-Za-z0-9\-_]*)\s*$"
    r"|^\s*(?P<name2>[A-Za-z0-9][A-Za-z0-9\-_]*)\s+protein\s*$"
    r"|^\s*(?:human|mouse|murine)\s+(?P<name3>.+?)\s+protein\s*$"
    r"|^\s*(?P<name4>.+?)[\s\-]+targeted\s*$"
)

APTAMER_BINDING_TARGET_RE = re.compile(
    r"(?is)\b(?:RNA\s+)?aptamer(?:s)?\s+"
    r"(?:that\s+)?"
    r"(?:(?:selectively|specifically|capable\s+of)\s+)?"
    r"(?:binds?(?:\s+to)?|binding(?:\s+to)?|against|for|to)\s+"
    r"(?:the\s+)?"
    r"(?P<target>.+?)"
    r"(?:\s+protein)?(?:\s+and\s+use(?:\s+thereof)?)?\s*$"
)

ANTI_TARGET_TITLE_RE = re.compile(
    r"(?is)\b(?:anti[\s\-]?|aptamer(?:s)?\s+(?:against|to|for|binding)\s+|"
    r"specific\s+aptamer\s+for\s+)"
    r"(?P<target>[A-Za-z0-9][A-Za-z0-9αβγδε\-\s/()]{0,60}?)"
    r"(?:\s+(?:aptamer|and\s+use|having|with)\b|\s*$)"
)

EXPLICIT_BINDS_TITLE_RE = re.compile(
    r"(?i)\b(?:selectively\s+binds?|specifically\s+binds?|capable\s+of\s+binding|"
    r"binds?\s+(?:specifically\s+)?to|binding\s+to)\b"
)

INHIBITION_TITLE_RE = re.compile(
    r"(?i)\b(?:inhibits?|inhibiting|inhibition\s+of|suppresses?|blocks?)\b"
)

TARGET_SPECIFIC_CLAIM_RE = re.compile(
    r"(?i)\b(?:anti[\s\-]?[A-Za-z0-9]|aptamer(?:s)?\s+(?:against|to|for)\b|"
    r"specific\s+aptamer\s+for\b|aptamer\s+binding\b|"
    r"RNA\s+aptamer\s+binding\b)\b"
)

CAPSID_OF_RE = re.compile(
    r"(?is)^\s*capsid\s+protein\s+of\s+(?P<name>[A-Za-z0-9][A-Za-z0-9\-_]*)\s*$"
)
CAPSID_PREFIX_RE = re.compile(
    r"(?is)^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9\-_]*)\s+capsid\s+protein\s*$"
)

PROMOTER_DNA = T7_PROMOTER_DNA
PROMOTER_RNA = T7_PROMOTER_RNA


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TargetRepairV2:
    target_raw: str = ""
    target_name: str = ""
    target_display_name: str = ""
    target_comparison_key: str = ""
    target_region: str = ""
    target_context: str = ""
    target_type: str = "unknown"
    target_repair_reason: str = "unchanged"
    target_confidence: str = "low"
    prior_type: str = ""
    type_changed: bool = False
    alias_applied: bool = False
    was_generic: bool = False
    unresolved: bool = False
    notes: str = ""

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceRepairV2:
    binding_evidence_strength: str = "none"
    binding_evidence_type: str = "none"
    evidence_scope: str = "none"
    binding_evidence_text: str = ""
    prior_scope: str = ""
    prior_strength: str = ""
    repair_reason: str = ""
    upgraded_from_none: bool = False
    downgraded_from_individual: bool = False

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PromoterTrimProposal:
    possible_post_promoter_sequence: str = ""
    post_promoter_sequence_length: int = 0
    promoter_trim_status: str = ""  # proposed_for_review | unresolved | ""

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Comparison keys / aliases
# ---------------------------------------------------------------------------


def _orthographic_key(name: str) -> str:
    """Strip punctuation/spacing/case; expand Greek letters."""
    if not name:
        return ""
    text = name.strip().translate(_GREEK_MAP)
    # Expand remaining alpha/β words already handled; normalise unicode dashes
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = text.upper()
    # TNF-α already mapped via translate if greek; handle ALPHA word form
    text = re.sub(r"[^A-Z0-9]+", "", text)
    return text


def normalize_target_comparison_key(name: str) -> str:
    """Alias-aware comparison key so FGF2 ≡ FGF-2 ≡ fgf 2."""
    ortho = _orthographic_key(name)
    if not ortho:
        return ""
    if ortho in TARGET_ALIASES:
        return _orthographic_key(TARGET_ALIASES[ortho])
    # IL17 / IL-17 style: already collapsed by orthographic key
    # Prefer alias display canonical key when present
    for alias_key, display in TARGET_ALIASES.items():
        if ortho == alias_key or ortho == _orthographic_key(display):
            return _orthographic_key(display)
    return ortho


def preferred_display_name(name: str, fallback: str = "") -> str:
    ortho = _orthographic_key(name)
    if ortho in TARGET_ALIASES:
        return TARGET_ALIASES[ortho]
    cleaned = re.sub(r"\s+", " ", (name or fallback or "").strip())
    return cleaned


def targets_compare_equivalent(a: str, b: str) -> bool:
    ka, kb = normalize_target_comparison_key(a), normalize_target_comparison_key(b)
    if not ka or not kb:
        return False
    return ka == kb


# ---------------------------------------------------------------------------
# Target repair
# ---------------------------------------------------------------------------


def _strip_junk(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip(" .,;:\"'")
    text = re.sub(
        r"(?i)\s+(?:inhibiting|and\s+use(?:\s+thereof)?|use\s+thereof|"
        r"having\s+improved.*|complete\s+sequence|partial\s+sequence|"
        r"generated\s+by.*|from\s+SELEX.*|with\s+high\s+affinity.*)$",
        "",
        text,
    ).strip(" .,;:\"'")
    return text


def _is_generic(text: str) -> bool:
    cleaned = _strip_junk(text).lower()
    if cleaned in GENERIC_TARGET_PHRASES or cleaned in GENERIC_EXTRA:
        return True
    return is_generic_target_phrase(text)


def _is_viral_process(text: str) -> bool:
    cleaned = _strip_junk(text)
    if not cleaned:
        return False
    if VIRAL_PROCESS_RE.search(cleaned):
        # Specific viral protein named elsewhere → not purely a process
        if re.search(
            r"(?i)\b(?:NS\d+[A-Z]?|capsid\s+protein|envelope\s+protein|"
            r"protease|polymerase|helicase)\b",
            cleaned,
        ):
            return False
        return True
    return False


def _extract_from_aptamer_phrase(text: str) -> str | None:
    m = APTAMER_BINDING_TARGET_RE.search(_strip_junk(text))
    if not m:
        # Try anti-/against titles
        m2 = ANTI_TARGET_TITLE_RE.search(_strip_junk(text))
        if m2:
            return _strip_junk(m2.group("target"))
        return None
    return _strip_junk(m.group("target"))


def repair_target_v2(
    target_raw: str,
    target_type: str = "",
    context_text: str = "",
) -> TargetRepairV2:
    """Repair target fields for review v2."""
    raw = str(target_raw or "").strip()
    prior_type = str(target_type or "").strip() or "unknown"
    result = TargetRepairV2(
        target_raw=raw,
        prior_type=prior_type,
        target_type=prior_type,
        target_confidence="moderate",
    )

    if not raw:
        result.target_name = ""
        result.target_display_name = ""
        result.target_comparison_key = "UNKNOWN"
        result.target_type = "unknown"
        result.target_repair_reason = "empty_target"
        result.target_confidence = "low"
        result.unresolved = True
        return result

    if _is_generic(raw):
        result.was_generic = True
        result.target_name = ""
        result.target_display_name = "unknown"
        result.target_comparison_key = "UNKNOWN"
        result.target_type = "unknown"
        result.target_repair_reason = "generic_phrase"
        result.target_confidence = "low"
        result.unresolved = True
        result.type_changed = prior_type != "unknown"
        return result

    if _is_viral_process(raw):
        cleaned = _strip_junk(raw)
        result.target_name = cleaned
        result.target_display_name = cleaned
        result.target_comparison_key = normalize_target_comparison_key(cleaned) or "VIRAL_PROCESS"
        result.target_type = "viral_process_or_system"
        result.target_repair_reason = "viral_process_not_protein"
        result.target_confidence = "moderate"
        result.type_changed = prior_type != result.target_type
        result.unresolved = False
        return result

    # Action phrases: purification of human IgG → human IgG
    m_action = ACTION_PHRASE_RE.match(_strip_junk(raw))
    if m_action:
        name = _strip_junk(m_action.group("name"))
        ttype, note = classify_target_type(name, context_text)
        if re.search(r"(?i)\b(?:Ig[GAMDE]|antibody|mAb|Fab)\b", name):
            ttype = "antibody"
            note = "action_phrase_antibody"
        result.target_name = name
        result.target_display_name = preferred_display_name(name)
        result.target_comparison_key = normalize_target_comparison_key(name)
        result.target_type = ttype
        result.target_repair_reason = "action_phrase_stripped"
        result.target_confidence = "moderate"
        result.type_changed = ttype != prior_type
        result.notes = note
        result.alias_applied = _orthographic_key(name) in TARGET_ALIASES
        return result

    # Capsid protein of PCV2 / PCV2 capsid protein
    m_cap = CAPSID_OF_RE.match(_strip_junk(raw)) or CAPSID_PREFIX_RE.match(_strip_junk(raw))
    if m_cap:
        virus = m_cap.group("name").strip()
        name = f"{virus} capsid protein"
        result.target_name = name
        result.target_display_name = name
        result.target_region = "capsid protein"
        result.target_comparison_key = normalize_target_comparison_key(name)
        result.target_type = "protein"
        result.target_repair_reason = "capsid_protein_parsed"
        result.target_confidence = "high"
        result.type_changed = prior_type != "protein"
        return result

    # Structured region/domain forms (reuse stage-3 parser)
    structured = parse_structured_target(raw)
    if structured:
        name = structured["target_name"]
        region = structured["target_region"]
        organism = structured.get("target_organism_or_context", "")
        blob = f"{name} {region} {organism} {context_text}"
        ttype, note = classify_target_type(name, blob)
        if structured["pattern"] in {"capsid", "surface_protein", "nonstructural_protein"}:
            ttype = "protein"
            note = f"{note}|forced_protein_from_{structured['pattern']}"
        if structured["pattern"] in {"region_of_protein", "x_of_y_protein"} and ttype == "unknown":
            ttype = "protein"
            note = f"{note}|region_of_named_protein"
        # Never call a viral structural protein an enzyme from context alone
        if structured["pattern"] == "capsid" and ttype == "enzyme":
            ttype = "protein"
            note = f"{note}|capsid_not_enzyme"
        result.target_name = name
        result.target_display_name = preferred_display_name(name)
        result.target_region = region
        result.target_context = organism
        result.target_comparison_key = normalize_target_comparison_key(name)
        result.target_type = ttype
        result.target_repair_reason = f"structured_{structured['pattern']}"
        result.target_confidence = "high"
        result.type_changed = ttype != prior_type
        result.notes = note
        result.alias_applied = _orthographic_key(name) in TARGET_ALIASES
        result.unresolved = ttype in {"unknown", "unknown_or_probable_small_molecule"}
        return result

    # Explicit protein wording: protein tyrosinase / surface protein TSA56 /
    # human cyclin T1 protein / phospholamban-targeted
    m_prot = EXPLICIT_PROTEIN_WORDING_RE.match(_strip_junk(raw))
    if m_prot:
        name = next(
            g for g in (m_prot.group("name"), m_prot.group("name2"), m_prot.group("name3"), m_prot.group("name4"))
            if g
        )
        name = _strip_junk(name)
        result.target_name = name
        result.target_display_name = preferred_display_name(name)
        result.target_comparison_key = normalize_target_comparison_key(name)
        result.target_type = "protein"
        result.target_repair_reason = "explicit_protein_wording"
        result.target_confidence = "high"
        result.type_changed = prior_type != "protein"
        return result

    # Aptamer binding phrases in the target field itself
    extracted = _extract_from_aptamer_phrase(raw)
    if extracted and extracted.lower() != raw.lower():
        # May still contain region language
        nested = parse_structured_target(extracted)
        if nested:
            name = nested["target_name"]
            region = nested["target_region"]
        else:
            name = extracted
            region = ""
            # strip trailing "protein"
            name = re.sub(r"(?i)\s+protein$", "", name).strip()
        ttype, note = classify_target_type(name, context_text)
        if ttype == "unknown":
            ttype = "protein"
            note = "aptamer_binding_phrase_protein"
        result.target_name = name
        result.target_display_name = preferred_display_name(name)
        result.target_region = region
        result.target_comparison_key = normalize_target_comparison_key(name)
        result.target_type = ttype
        result.target_repair_reason = "extracted_from_aptamer_phrase"
        result.target_confidence = "moderate"
        result.type_changed = ttype != prior_type
        result.notes = note
        return result

    cleaned = _strip_junk(raw)
    ortho = _orthographic_key(cleaned)
    context_suggests_protein = bool(
        re.search(
            r"(?i)\b(?:surface\s+protein|capsid\s+protein|protein\b|antibody|"
            r"aptamer(?:s)?\s+(?:against|to|for|binding)|anti[\s\-])",
            context_text or "",
        )
    )

    # Configured protein aliases take precedence over compound-code heuristics
    if ortho in KNOWN_PROTEIN_ALIAS_KEYS:
        display = preferred_display_name(cleaned)
        result.target_name = cleaned
        result.target_display_name = display
        result.target_comparison_key = normalize_target_comparison_key(cleaned)
        result.target_type = "protein"
        result.target_repair_reason = "known_protein_alias"
        result.target_confidence = "moderate"
        result.type_changed = prior_type != "protein"
        result.alias_applied = True
        result.notes = "alias_forced_protein"
        return result

    # Known small molecules / compounds (skip when prior/context say protein)
    if cleaned.lower() in KNOWN_SMALL_MOLECULES:
        result.target_name = cleaned
        result.target_display_name = cleaned
        result.target_comparison_key = normalize_target_comparison_key(cleaned) or "COMPOUND"
        result.target_type = "small_molecule"
        result.target_repair_reason = "known_small_molecule"
        result.target_confidence = "moderate"
        result.type_changed = prior_type != result.target_type
        result.unresolved = False
        return result

    if is_probable_compound_code(cleaned):
        if prior_type in PROTEIN_COMPATIBLE_REPAIRED or context_suggests_protein:
            result.target_name = cleaned
            result.target_display_name = preferred_display_name(cleaned)
            result.target_comparison_key = normalize_target_comparison_key(cleaned)
            result.target_type = "protein" if prior_type in {"unknown", ""} else prior_type
            if result.target_type not in PROTEIN_COMPATIBLE_REPAIRED:
                result.target_type = "protein"
            result.target_repair_reason = "compound_like_but_protein_context"
            result.target_confidence = "moderate"
            result.type_changed = prior_type != result.target_type
            result.notes = "prior_or_context_overrides_compound_heuristic"
            return result
        result.target_name = cleaned
        result.target_display_name = cleaned
        result.target_comparison_key = normalize_target_comparison_key(cleaned) or "COMPOUND"
        result.target_type = "unknown_or_probable_small_molecule"
        result.target_repair_reason = "compound_code_not_protein"
        result.target_confidence = "moderate"
        result.type_changed = prior_type != result.target_type
        result.unresolved = True
        return result

    ttype, note = classify_target_type(cleaned, context_text)
    # Guard: process language still present
    if _is_viral_process(cleaned):
        ttype = "viral_process_or_system"
        note = "viral_process_guard"
    # Guard: enzyme only from genuine enzyme name, not replication context
    if ttype == "enzyme" and re.search(r"(?i)replication|replicon", cleaned):
        ttype = "viral_process_or_system"
        note = "replication_not_enzyme"
    # Preserve protein-compatible prior when lexicon is inconclusive
    if ttype == "unknown" and prior_type in PROTEIN_COMPATIBLE_REPAIRED:
        ttype = prior_type
        note = f"{note}|preserved_prior_protein_type"
    if ttype == "unknown" and context_suggests_protein and re.fullmatch(
        r"[A-Za-z][A-Za-z0-9\-]{1,20}", cleaned
    ):
        ttype = "protein"
        note = f"{note}|short_name_with_protein_context"

    display = preferred_display_name(cleaned)
    key = normalize_target_comparison_key(cleaned)
    alias = ortho in TARGET_ALIASES or display != cleaned

    result.target_name = cleaned
    result.target_display_name = display
    result.target_comparison_key = key or "UNKNOWN"
    result.target_type = ttype
    result.target_repair_reason = "alias_normalized" if alias and ttype == prior_type else (
        "reclassified" if ttype != prior_type else "unchanged"
    )
    result.target_confidence = "moderate" if ttype not in {"unknown", ""} else "low"
    result.type_changed = ttype != prior_type
    result.alias_applied = bool(alias)
    result.notes = note
    result.unresolved = ttype in {"unknown", "unknown_or_probable_small_molecule", ""}
    return result


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------


def classify_conflict_type(
    keys_and_regions: Sequence[tuple[str, str, str]],
) -> str:
    """Classify conflict among (comparison_key, region, display_or_name) tuples.

    Unresolved keys (UNKNOWN / empty / COMPOUND) yield ``target_unresolved``
    when mixed with concrete keys, or when all unresolved with multiple labels.

    Viral-process keys (including the ``VIRAL_PROCESS`` fallback) are concrete:
    they must participate in conflict detection against proteins and other
    named targets.
    """
    items = [(k, r, n) for k, r, n in keys_and_regions if k or n]
    if len(items) <= 1:
        return "no_conflict"

    unresolved_keys = {"UNKNOWN", "COMPOUND"}
    concrete = [(k, r, n) for k, r, n in items if k and k not in unresolved_keys]
    unresolved = [(k, r, n) for k, r, n in items if not k or k in unresolved_keys]

    if unresolved and concrete:
        return "target_unresolved"
    if unresolved and not concrete:
        labels = {n.lower() for _, _, n in unresolved if n}
        if len(labels) > 1:
            return "target_unresolved"
        return "no_conflict"

    keys = {k for k, _, _ in concrete}
    if len(keys) == 1:
        regions = {re.sub(r"\s+", " ", (r or "").strip().lower()) for _, r, _ in concrete}
        regions.discard("")
        if len(regions) > 1:
            return "same_target_different_region"
        return "orthographic_alias_only" if len({n for _, _, n in concrete}) > 1 else "no_conflict"

    # Multiple distinct comparison keys
    # Check whether they are only orthographic (shouldn't happen if keys correct)
    if len(keys) > 1:
        return "genuine_different_target"
    return "no_conflict"


def conflict_is_biological(conflict_type: str) -> bool:
    return conflict_type in {
        "genuine_different_target",
        "target_unresolved",
        "same_target_different_region",
    }


# ---------------------------------------------------------------------------
# Evidence repair
# ---------------------------------------------------------------------------


def _patentish(text: str) -> bool:
    return bool(PATENT_CLAIM_RE.search(text or "")) or bool(
        re.search(r"(?i)\b(?:WO|US|EP|KR|JP|CN)\s*\d", text or "")
    )


def _feature_note_individual(text: str) -> bool:
    """Heuristic: accession-specific feature note / assay language."""
    if not text:
        return False
    if INDIVIDUAL_ASSAY_RE.search(text):
        return True
    if re.search(
        r"(?i)\b(?:this\s+(?:aptamer|sequence|oligonucleotide)|"
        r"the\s+deposited\s+sequence|"
        r"clone\s+\w+\s+binds|"
        r"Kd\s*[=:])",
        text,
    ):
        return True
    return False


def normalize_binding_evidence_type(
    raw_types: str = "",
    *,
    evidence_scope: str = "",
) -> str:
    """Return a value from ``BINDING_EVIDENCE_TYPES`` only."""
    text = str(raw_types or "").strip()
    if text in BINDING_EVIDENCE_TYPES:
        return text
    # Prefer the first pipe-/comma-separated token that maps cleanly
    tokens = re.split(r"[|,;]+", text) if text else []
    for tok in tokens:
        cleaned = tok.strip()
        if not cleaned or cleaned in {"none", "none_found"}:
            continue
        if cleaned in BINDING_EVIDENCE_TYPES:
            return cleaned
        mapped = _LEGACY_BINDING_TYPE_MAP.get(cleaned)
        if mapped:
            return mapped
        # Soft match on substrings of legacy labels
        low = cleaned.lower()
        if "affinity" in low or "kd" in low:
            return "individual_sequence_affinity"
        if "inhibit" in low or "functional" in low:
            return "functional_or_inhibitory_claim"
        if "bind" in low or "recogn" in low:
            return "explicit_binding_claim"
        if "selection" in low or "selex" in low:
            return "selection_against_target"
        if "aptamer" in low or "title" in low:
            return "target_specific_aptamer_claim"

    scope = evidence_scope if evidence_scope != "experiment_or_family_level" else "experiment_family_level"
    if scope.startswith("individual_sequence_quantitative"):
        return "individual_sequence_affinity"
    if scope.startswith("individual_sequence_qualitative"):
        return "individual_sequence_binding"
    if scope == "patent_claim_level":
        return "target_specific_aptamer_claim"
    if scope == "selection_context_only":
        return "selection_against_target"
    if scope == "experiment_family_level":
        return "explicit_binding_claim"
    return "none"


def repair_binding_evidence_v2(
    *,
    description: str = "",
    reference_titles: str = "",
    binding_evidence_status: str = "",
    binding_evidence_types: str = "",
    binding_evidence_strength: str = "",
    binding_evidence_text: str = "",
    selection_evidence: str = "",
    feature_notes: str = "",
    prior_scope: str = "",
    accession_count: int = 1,
) -> EvidenceRepairV2:
    """Reclassify evidence scope/type/strength for review v2."""
    titles = " || ".join(filter(None, [description, reference_titles]))
    blob = " || ".join(
        filter(
            None,
            [
                description,
                reference_titles,
                binding_evidence_text,
                binding_evidence_status,
                binding_evidence_types,
                selection_evidence,
                feature_notes,
            ],
        )
    )
    prior_strength = str(binding_evidence_strength or "").strip() or "none"
    prior = str(prior_scope or "").strip() or "none"
    # Map stage-3 scope name
    if prior == "experiment_or_family_level":
        prior = "experiment_family_level"

    result = EvidenceRepairV2(
        prior_scope=prior,
        prior_strength=prior_strength,
        binding_evidence_text=(binding_evidence_text or titles)[:500],
    )

    has_individual = _feature_note_individual(feature_notes) or (
        _feature_note_individual(binding_evidence_text)
        and not _patentish(titles)
    )
    quantitative = bool(QUANTITATIVE_BINDING_RE.search(blob))

    # Individual sequence evidence only with accession-specific support
    if has_individual and quantitative:
        result.binding_evidence_type = "individual_sequence_affinity"
        result.evidence_scope = "individual_sequence_quantitative"
        result.binding_evidence_strength = "strong"
        result.repair_reason = "accession_specific_affinity"
        return result
    if has_individual and re.search(r"(?i)\bbinds?|recognis|recogniz", feature_notes or binding_evidence_text or ""):
        result.binding_evidence_type = "individual_sequence_binding"
        result.evidence_scope = "individual_sequence_qualitative"
        result.binding_evidence_strength = "moderate"
        result.repair_reason = "accession_specific_binding"
        return result

    patentish = _patentish(titles) or _patentish(blob)
    explicit_binds = bool(EXPLICIT_BINDS_TITLE_RE.search(titles))
    inhibition = bool(INHIBITION_TITLE_RE.search(titles))
    target_claim = bool(TARGET_SPECIFIC_CLAIM_RE.search(titles)) or bool(
        ANTI_TARGET_TITLE_RE.search(titles)
    )

    if patentish and explicit_binds:
        result.binding_evidence_type = "explicit_binding_claim"
        result.evidence_scope = "patent_claim_level"
        result.binding_evidence_strength = "moderate"
        result.repair_reason = "patent_explicit_binding_title"
        result.upgraded_from_none = prior in {"none", "selection_context_only", ""}
        result.downgraded_from_individual = prior.startswith("individual")
        return result

    if patentish and inhibition and target_claim:
        result.binding_evidence_type = "functional_or_inhibitory_claim"
        result.evidence_scope = "patent_claim_level"
        result.binding_evidence_strength = "moderate"
        result.repair_reason = "patent_functional_claim"
        result.upgraded_from_none = prior in {"none", "selection_context_only", ""}
        result.downgraded_from_individual = prior.startswith("individual")
        return result

    if patentish and target_claim:
        result.binding_evidence_type = "target_specific_aptamer_claim"
        result.evidence_scope = "patent_claim_level"
        result.binding_evidence_strength = "weak"
        result.repair_reason = "patent_anti_target_claim"
        result.upgraded_from_none = prior in {"none", "selection_context_only", ""}
        result.downgraded_from_individual = prior.startswith("individual")
        return result

    # Non-patent family / experiment language
    if explicit_binds and not has_individual:
        result.binding_evidence_type = "explicit_binding_claim"
        result.evidence_scope = "experiment_family_level"
        result.binding_evidence_strength = "moderate"
        result.repair_reason = "family_binding_language"
        result.downgraded_from_individual = prior.startswith("individual")
        return result

    if selection_evidence and selection_evidence not in {"none", "none_found", ""}:
        result.binding_evidence_type = "selection_against_target"
        result.evidence_scope = "selection_context_only"
        result.binding_evidence_strength = "weak"
        result.repair_reason = "selection_context"
        return result

    if re.search(r"(?i)\bSELEX\b", blob):
        result.binding_evidence_type = "selection_against_target"
        result.evidence_scope = "selection_context_only"
        result.binding_evidence_strength = "weak"
        result.repair_reason = "selex_language"
        return result

    # Downgrade prior individual scopes that rested only on shared titles
    if prior.startswith("individual") and patentish and not has_individual:
        result.binding_evidence_type = (
            "explicit_binding_claim" if explicit_binds else "target_specific_aptamer_claim"
        )
        result.evidence_scope = "patent_claim_level"
        result.binding_evidence_strength = "moderate" if explicit_binds else "weak"
        result.repair_reason = "downgraded_patent_title_not_individual"
        result.downgraded_from_individual = True
        return result

    if prior_strength not in {"", "none"} and prior not in {"", "none"}:
        # Preserve non-none prior with mapped scope name and a valid type token
        scope = prior if prior in EVIDENCE_SCOPES_V2 else "experiment_family_level"
        result.binding_evidence_type = normalize_binding_evidence_type(
            binding_evidence_types,
            evidence_scope=scope,
        )
        result.evidence_scope = scope
        result.binding_evidence_strength = prior_strength
        result.repair_reason = "preserved_prior"
        return result

    result.binding_evidence_type = "none"
    result.evidence_scope = "none"
    result.binding_evidence_strength = "none"
    result.repair_reason = "no_evidence"
    return result


# Higher rank = stronger evidence. EVIDENCE_SCOPES_V2 is ordered strongest→weakest.
_SCOPE_RANK = {
    s: len(EVIDENCE_SCOPES_V2) - 1 - i for i, s in enumerate(EVIDENCE_SCOPES_V2)
}
_SCOPE_RANK["experiment_or_family_level"] = _SCOPE_RANK["experiment_family_level"]


def strongest_evidence_scope_v2(scopes: Iterable[str]) -> str:
    best = "none"
    best_rank = -1
    for s in scopes:
        # treat experiment_or_family_level as experiment_family_level
        if s == "experiment_or_family_level":
            s = "experiment_family_level"
        r = _SCOPE_RANK.get(s, -1)
        if r > best_rank:
            best = s
            best_rank = r
    return best


# ---------------------------------------------------------------------------
# Group recommendations
# ---------------------------------------------------------------------------


def recommend_group_action(
    *,
    target_type: str,
    target_display_name: str,
    rna_identity_statuses: Sequence[str],
    concrete_sequence_count: int,
    library_template_count: int,
    promoter_or_template_count: int,
    member_count: int,
    binding_evidence_type: str,
    evidence_scope: str,
    descriptions: str = "",
    group_concerns: Sequence[str] = (),
) -> str:
    concerns = set(group_concerns)
    blob = descriptions or ""

    if re.search(r"(?i)\briboswitch\b|natural\s+aptamer|genomic\s+SELEX", blob):
        return "reject_natural_or_riboswitch"
    if "platform_or_vector" in concerns or re.search(
        r"(?i)\bexpression\s+vector|plasmid\s+backbone|cloning\s+vector\b", blob
    ):
        return "reject_platform_or_vector_construct"

    rna_ok = any(s in RNA_IDENTITY_PLAUSIBLE for s in rna_identity_statuses if s)
    protein_ok = target_type in PROTEIN_COMPATIBLE_REPAIRED | PROTEIN_COMPATIBLE_TARGET_TYPES
    named = bool(target_display_name) and target_display_name.lower() not in {
        "", "unknown", "same"
    }
    has_claim = evidence_scope not in {"none", ""} or binding_evidence_type not in {
        "none", ""
    }
    # Title claim for named target counts
    if not has_claim and named and re.search(r"(?i)\baptamers?\b", blob):
        has_claim = True

    if target_type in {
        "small_molecule",
        "unknown_or_probable_small_molecule",
        "ion",
        "nucleic_acid",
        "viral_process_or_system",
        "cell_or_tissue",
        "virus_or_virion",
        "peptide",
    }:
        return "reject_non_protein_target"
    if target_type in {"unknown", ""} or not named:
        return "reject_unknown_target"

    if not rna_ok and not re.search(r"(?i)\bRNA\s+aptamer\b", blob):
        return "insufficient_information"

    if concrete_sequence_count <= 0 and library_template_count >= member_count:
        return "reject_platform_or_vector_construct"

    if protein_ok and named and has_claim and concrete_sequence_count > 0:
        if (
            promoter_or_template_count > 0
            or library_template_count > 0
            or "sequence_roles_uncertain" in concerns
        ):
            return "retain_but_sequence_roles_need_review"
        return "retain_for_group_review"

    if protein_ok and named and has_claim:
        return "retain_but_sequence_roles_need_review"

    return "insufficient_information"


def is_retention_recommendation(action: str) -> bool:
    return action in {
        "retain_for_group_review",
        "retain_but_sequence_roles_need_review",
    }


# ---------------------------------------------------------------------------
# Promoter trim proposals (advisory only)
# ---------------------------------------------------------------------------


def propose_promoter_trim(sequence_rna: str) -> PromoterTrimProposal:
    seq = str(sequence_rna or "").strip().upper().replace(" ", "")
    if not seq:
        return PromoterTrimProposal()
    dna = seq.replace("U", "T")
    if seq.startswith(PROMOTER_RNA) or dna.startswith(PROMOTER_DNA):
        rest = seq[len(PROMOTER_RNA) :]
        return PromoterTrimProposal(
            possible_post_promoter_sequence=rest,
            post_promoter_sequence_length=len(rest),
            promoter_trim_status="proposed_for_review",
        )
    # Internal / multiple / ambiguous placement
    if PROMOTER_RNA in seq or PROMOTER_DNA in dna:
        return PromoterTrimProposal(
            possible_post_promoter_sequence="",
            post_promoter_sequence_length=0,
            promoter_trim_status="unresolved",
        )
    return PromoterTrimProposal()


# ---------------------------------------------------------------------------
# Manual field validation
# ---------------------------------------------------------------------------


def validate_manual_group_include(value: Any) -> str | None:
    """Accept blank / 0 / 1 only (same contract as sequence manual_include)."""
    return validate_manual_include(value)


def is_protein_compatible_v2(ttype: str) -> bool:
    return ttype in PROTEIN_COMPATIBLE_REPAIRED | PROTEIN_COMPATIBLE_TARGET_TYPES
