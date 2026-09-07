"""Conservative evidence extraction and classification rules for ENA aptamer candidates.

This module is deliberately non-destructive: derived conclusions are accompanied by
evidence text, source field, strength, and notes. Final corpus inclusion is out of
scope.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

T7_PROMOTER_DNA = "TAATACGACTCACTATA"
T7_PROMOTER_RNA = "UAAUACGACUCACUAUA"

CANDIDATE_TIERS = (
    "Tier_A_high_confidence",
    "Tier_B_plausible_needs_review",
    "Tier_C_sequence_role_uncertain",
    "Tier_D_non_core_or_exclude",
    "Tier_E_insufficient_information",
)

PROTEIN_COMPATIBLE_TARGET_TYPES = frozenset(
    {"protein", "protein_complex", "enzyme", "antibody"}
)
NON_CORE_TARGET_TYPES = frozenset(
    {"small_molecule", "ion", "nucleic_acid", "natural_ligand", "cell_or_tissue", "virus_or_virion"}
)

AFFINITY_RE = re.compile(
    r"(?P<label>\b(?:Kd|KD|Ka|KA|IC50|EC50|Ki|KI)\b)"
    r"\s*(?:=|:|of|≈|~)?\s*"
    r"(?P<value>\d+(?:\.\d+)?(?:\s*[x×]\s*10\s*[-−]?\s*\d+)?|\d+(?:\.\d+)?(?:e[-+]?\d+)?)"
    r"\s*(?P<unit>fM|pM|nM|uM|µM|μM|mM|M)\b",
    re.IGNORECASE,
)

BINDS_RE = re.compile(
    r"\b(?:binds?(?:\s+specifically)?(?:\s+to)?|specifically\s+(?:binds?|recognis(?:es?|es?)|recognizes?)|"
    r"recognis(?:es?|es?)|recognition\s+of|specific\s+for|targeting|directed\s+against|"
    r"selected\s+against)\b",
    re.IGNORECASE,
)

SELECTION_RE = re.compile(
    r"\b(?:SELEX|systematic\s+evolution\s+of\s+ligands|"
    r"in[\s-]?vitro\s+(?:select(?:ed|ion)|evolv(?:ed|ution))|"
    r"selected\s+(?:RNA|DNA|ligand)|combinatorial\s+library|"
    r"random\s+library|binding\s+selection|genomic\s+SELEX|cell[\s-]?SELEX|"
    r"capture[\s-]?SELEX)\b",
    re.IGNORECASE,
)

RNA_APTAMER_RE = re.compile(r"\bRNA\s+aptamer\b", re.IGNORECASE)
DNA_APTAMER_RE = re.compile(r"\bDNA\s+aptamer\b", re.IGNORECASE)
APTAMER_RE = re.compile(r"\baptamers?\b", re.IGNORECASE)

RIBOSWITCH_RE = re.compile(
    r"\b(?:riboswitch|aptamer\s+domain|metabolite[\s-]sensing|cis[\s-]regulatory|"
    r"leader\s+RNA)\b",
    re.IGNORECASE,
)
NATURAL_GENOMIC_RE = re.compile(
    r"\b(?:TPA:inferential|Third\s+Party\s+Data|genomic\s+(?:locus|SELEX)|"
    r"natural\s+aptamer|antisense\s+.*aptamer|conserved\s+motif|"
    r"chromosome|genomic\s+RNA\s+aptamer\s+gene)\b|"
    r"\bTPA:\s*",
    re.IGNORECASE,
)
ENGINEERED_SWITCH_RE = re.compile(
    r"\b(?:aptazyme|ribozyme|molecular\s+switch|biosensor|allosteric|"
    r"expression\s+construct|chimeric|fusion\s+construct)\b",
    re.IGNORECASE,
)
TEMPLATE_PROMOTER_RE = re.compile(
    r"\b(?:DNA\s+template|transcription\s+template|T7\s+promoter|SP6\s+promoter|"
    r"promoter[\s-]?containing|template\s+for\s+(?:T7|RNA))\b",
    re.IGNORECASE,
)
PRIMER_FLANK_RE = re.compile(
    r"\b(?:primer[\s-]?(?:binding|flank|region)|flanking\s+sequence|"
    r"constant\s+region|random\s+region|variable\s+region)\b",
    re.IGNORECASE,
)

# Target-type lexicons (conservative; free-text still inspected).
SMALL_MOLECULE_TERMS = [
    "theophylline", "atp", "amp", "gtp", "gmp", "camp", "sam", "sah",
    "streptomycin", "kanamycin", "tobramycin", "neomycin", "tetracycline",
    "dopamine", "serotonin", "cocaine", "ethanol", "malachite green",
    "fluorophore", "dye", "8-oxodg", "8-oxo-dg", "adenosine", "guanosine",
    "cysteine", "glycine", "lysine", "histidine", "tryptophan", "arginine",
    "glucose", "sucrose", "caffeine", "nicotine", "ochratoxin", "aflatoxin",
    "toxin", "metabolite", "small molecule", "aminoglycoside",
]
ION_TERMS = ["magnesium", "mg2+", "calcium", "ca2+", "zinc", "zn2+", "potassium", "k+", "sodium", "na+"]
NUCLEIC_ACID_TARGET_TERMS = [
    "mrna", "microrna", "mirna", "dsdna", "ssdna", "double-stranded dna",
    "single-stranded dna", "rna duplex", "dna duplex", "nucleic acid target",
    "hairpin", "rnase p rna", "stem-loop",
]
CELL_TISSUE_TERMS = [
    "cancer cell", "tumor cell", "tumour cell", "cell line", "cells",
    "tissue", "exosome", "microvesicle", "vesicle", "plasma membrane",
]
VIRUS_TERMS = [
    "virus", "virion", "viral particle", "hiv-1", "hiv", "hcv", "hbv",
    "herpes", "hsv-1", "hsv", "influenza", "rhabdovirus", "coronavirus",
    "sars", "norovirus",
]
ANTIBODY_TERMS = ["antibody", "igg", "iga", "igm", "fab fragment", "scfv", "mab"]
ENZYME_TERMS = [
    "enzyme", "kinase", "protease", "phosphatase", "polymerase", "nuclease",
    "transferase", "synthase", "reductase", "oxidase", "dehydrogenase",
    "thrombin", "chymase", "elastase", "lysozyme", "rnase", "dnase",
    "termination factor", "rf1", "reverse transcriptase",
]
PROTEIN_COMPLEX_TERMS = [
    "protein complex", "ribosome", "nucleosome", "spliceosome", "proteasome",
    "transcription factor complex",
]
PEPTIDE_TERMS = ["peptide", "oligopeptide", "polypeptide epitope"]

# Common protein-like name patterns in free text.
PROTEIN_NAME_HINT_RE = re.compile(
    r"\b(?:"
    r"VEGF(?:-?[AB])?|NGF|TNF(?:-?α|-?alpha)?|IL-?\d+[A-Za-z]?|"
    r"HMGB1|PDGF|FGF\d*|EGFR|HER2|EpCAM|PTK7|PSMA|CD\d+|"
    r"thrombin|lysozyme|streptavidin|protein\s+A|protein\s+G|"
    r"prion\s+protein|PrP(?:C|Sc)?|complement\s+(?:C\d+|factor\s+[A-Z])|"
    r"factor\s+[A-Z]|interferon|cytokine|albumin|hemoglobin|"
    r"nucleolin|nucleophosmin|tenascin|mucin|MUC1|ADAMTS\d*|"
    r"chymase|RF1|IL-21|"
    r"[A-Z][a-z]{2,}(?:ase)\b|"
    r"[A-Z]{3,}[0-9]+"
    r")\b"
)

TARGET_EXTRACT_PATTERNS = [
    re.compile(
        r"(?i)(?:binds?(?:\s+specifically)?(?:\s+to)?|recognis(?:es?|es?)|"
        r"specific(?:ally)?\s+(?:for|against|to)|selected\s+against|"
        r"targeting|against|for|inhibiting)\s+"
        r"(?P<target>[A-Za-z0-9][A-Za-z0-9αβγδε\s\-'/(),.+]{1,80}?)"
        r"(?=\s+(?:in|with|and|after)\b|\s*[,;.]|\s*$|\s*/note|\s+generated|\s+from)"
    ),
    re.compile(
        r"(?i)\baptamer(?:s)?\s+(?:for|against|to|binding\s+to)\s+"
        r"(?P<target>[A-Za-z0-9][A-Za-z0-9αβγδε\s\-'/(),.+]{1,80}?)"
        r"(?=\s+(?:and|use)\b|\s*[,;.]|\s*$)"
    ),
    re.compile(
        r"(?i)(?P<target>[A-Za-z0-9][A-Za-z0-9αβγδε\s\-'/()]{1,60}?)"
        r"[\s\-]+(?:binding|specific)\s+RNA\s+aptamer"
    ),
]

_HINT_STOPWORDS = frozenset(
    {
        "rna", "dna", "tpa", "selex", "aptamer", "aptamers", "complete", "partial",
        "sequence", "synthetic", "construct", "gene", "human", "mouse",
        "wo", "us", "ep", "jp", "kr", "cn", "pct", "in", "to", "of", "and", "the",
        "for", "use", "thereof",
    }
)


# ---------------------------------------------------------------------------
# Evidence container
# ---------------------------------------------------------------------------


@dataclass
class EvidenceItem:
    accession: str
    evidence_category: str
    evidence_type: str
    source_field: str
    source_text: str
    normalized_value: str = ""
    evidence_strength: str = "weak"
    supports_candidate: bool = False
    raises_concern: bool = False
    notes: str = ""

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClassificationResult:
    fields: dict[str, Any] = field(default_factory=dict)
    evidence: list[EvidenceItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sequence helpers
# ---------------------------------------------------------------------------


def reverse_complement(seq: str) -> str:
    table = str.maketrans("ACGTURYSWKMBDHVN", "TGCAAYRSWMKVHDBN")
    return seq.upper().translate(table)[::-1]


def rna_normalize_sequence(seq: str) -> str:
    """T→U only; leave ambiguous characters unchanged."""
    out = []
    for ch in seq.upper():
        if ch == "T":
            out.append("U")
        else:
            out.append(ch)
    return "".join(out)


def stable_group_id(prefix: str, key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "t"}


def _pipe_split(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    parts = re.split(r"\s*\|\|\s*|\s*\|\s*", text)
    return [p.strip().strip('"').strip("'") for p in parts if p.strip() and p.strip() not in {";", '""'}]


def _first_nonempty(*values: Any) -> str:
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _combined_text(record: dict[str, Any], fields: Iterable[str]) -> str:
    chunks = []
    for f in fields:
        val = record.get(f, "")
        if val is None:
            continue
        s = str(val).strip()
        if s:
            chunks.append(s)
    return " || ".join(chunks)


def _contains_any(text: str, terms: Iterable[str]) -> str | None:
    """Match lexicon terms with word boundaries for short tokens."""
    lower = text.lower()
    for term in terms:
        t = term.lower()
        if len(t) <= 3:
            if re.search(rf"\b{re.escape(t)}\b", lower):
                return term
        elif t in lower:
            return term
    return None


# ---------------------------------------------------------------------------
# Affinity / binding helpers
# ---------------------------------------------------------------------------


def parse_affinity(text: str) -> dict[str, str]:
    """Extract a quantitative affinity phrase; ignore unrelated numerics."""
    if not text:
        return {"affinity_raw": "", "affinity_value": "", "affinity_unit": "", "label": ""}
    m = AFFINITY_RE.search(text)
    if not m:
        return {"affinity_raw": "", "affinity_value": "", "affinity_unit": "", "label": ""}
    return {
        "affinity_raw": m.group(0),
        "affinity_value": re.sub(r"\s+", "", m.group("value")),
        "affinity_unit": m.group("unit"),
        "label": m.group("label"),
    }


# ---------------------------------------------------------------------------
# Target classification
# ---------------------------------------------------------------------------


def _clean_target_phrase(raw: str) -> str:
    text = re.sub(r"\s+", " ", raw).strip(" .,;:\"'")
    text = re.sub(
        r"(?i)\b(?:complete sequence|partial sequence|use thereof|and use thereof|"
        r"generated by.*|from SELEX.*|in DNA.*|with high affinity.*)$",
        "",
        text,
    ).strip(" .,;:\"'")
    if len(text) > 120:
        text = text[:120].rstrip()
    return text


def extract_target_candidates(record: dict[str, Any]) -> list[dict[str, str]]:
    """Return candidate target phrases with source field, ordered by preference."""
    field_order = [
        ("feature_notes", "feature_note"),
        ("products", "product"),
        ("description", "description"),
        ("reference_titles", "reference_title"),
        ("matched_terms", "matched_terms"),
    ]
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for field_name, source_label in field_order:
        text = str(record.get(field_name, "") or "")
        if not text.strip():
            continue
        for pat in TARGET_EXTRACT_PATTERNS:
            for m in pat.finditer(text):
                phrase = _clean_target_phrase(m.group("target"))
                if len(phrase) < 2 or phrase.lower() in {"rna", "dna", "aptamer", "the"}:
                    continue
                key = phrase.lower()
                if key in seen:
                    continue
                seen.add(key)
                found.append(
                    {
                        "target_raw": phrase,
                        "target_source": source_label,
                        "target_evidence_text": m.group(0)[:300],
                    }
                )
        # Fallback: protein-name hint in preferred fields
        if field_name in {"feature_notes", "products", "description", "reference_titles"}:
            for hint in PROTEIN_NAME_HINT_RE.finditer(text):
                phrase = _clean_target_phrase(hint.group(0))
                key = phrase.lower()
                if key in _HINT_STOPWORDS or len(phrase) < 2:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                found.append(
                    {
                        "target_raw": phrase,
                        "target_source": source_label,
                        "target_evidence_text": hint.group(0),
                    }
                )
                break
    return found


def classify_target_type(target_raw: str, context_text: str = "") -> tuple[str, str]:
    """Return (target_type, rationale_note)."""
    blob = f"{target_raw} {context_text}".strip()
    if not target_raw and not context_text:
        return "unknown", "no_target_text"

    # Stability / nuclease-resistance wording is not an enzyme target.
    if re.search(r"(?i)protection\s+against\s+nucleases|nuclease[\s-]resistant", blob):
        if re.search(r"(?i)^protection\s+against\s+nucleases$", target_raw.strip()):
            return "unknown", "nuclease_resistance_not_a_target"
        if "nuclease" in target_raw.lower() and "against" in target_raw.lower():
            return "unknown", "nuclease_resistance_not_a_target"

    # Peptide-recognised aptamers are peptide-directed unless a protein is named.
    if re.search(r"(?i)peptide[\s-]recognised|peptide[\s-]recognized|peptide[\s-]binding", blob):
        if not PROTEIN_NAME_HINT_RE.search(target_raw or "") and not re.search(
            r"(?i)\bprotein\b", target_raw or ""
        ):
            return "peptide", "peptide_recognized_language"

    if _contains_any(blob, ION_TERMS):
        return "ion", "matched_ion_term"
    if _contains_any(blob, SMALL_MOLECULE_TERMS):
        return "small_molecule", "matched_small_molecule_term"
    if _contains_any(blob, NUCLEIC_ACID_TARGET_TERMS):
        return "nucleic_acid", "matched_nucleic_acid_target_term"
    if _contains_any(blob, ANTIBODY_TERMS):
        return "antibody", "matched_antibody_term"
    if _contains_any(blob, ENZYME_TERMS):
        return "enzyme", "matched_enzyme_term"
    if _contains_any(blob, PROTEIN_COMPLEX_TERMS):
        return "protein_complex", "matched_protein_complex_term"
    if _contains_any(blob, PEPTIDE_TERMS) and not PROTEIN_NAME_HINT_RE.search(target_raw):
        return "peptide", "matched_peptide_term"
    # Virus / cell: only if no more specific protein named in target_raw itself
    virus_hit = _contains_any(blob, VIRUS_TERMS)
    cell_hit = _contains_any(blob, CELL_TISSUE_TERMS)
    protein_in_target = PROTEIN_NAME_HINT_RE.search(target_raw) if target_raw else None
    if virus_hit and not protein_in_target:
        return "virus_or_virion", "matched_virus_term_without_named_protein"
    if cell_hit and not protein_in_target:
        return "cell_or_tissue", "matched_cell_tissue_term_without_named_protein"
    if protein_in_target or re.search(r"(?i)\bprotein\b", target_raw or ""):
        return "protein", "protein_name_or_protein_keyword"
    if target_raw:
        return "unknown", "ambiguous_target_phrase"
    return "unknown", "no_clear_target"


def assess_target(record: dict[str, Any]) -> ClassificationResult:
    evidence: list[EvidenceItem] = []
    accession = str(record.get("accession", ""))
    candidates = extract_target_candidates(record)
    context = _combined_text(
        record,
        ["description", "feature_notes", "products", "reference_titles"],
    )

    if not candidates:
        # Still classify from context alone (e.g. riboswitch metabolite)
        ttype, note = classify_target_type("", context)
        fields = {
            "target_raw": "",
            "target_normalized": "",
            "target_type": ttype if ttype != "unknown" else "unknown",
            "target_source": "",
            "target_confidence": "none",
            "target_evidence_text": "",
        }
        if ttype != "unknown":
            evidence.append(
                EvidenceItem(
                    accession=accession,
                    evidence_category="target",
                    evidence_type="context_inferred_target_type",
                    source_field="combined_annotation",
                    source_text=context[:300],
                    normalized_value=ttype,
                    evidence_strength="weak",
                    supports_candidate=ttype in PROTEIN_COMPATIBLE_TARGET_TYPES,
                    raises_concern=ttype in NON_CORE_TARGET_TYPES,
                    notes=note,
                )
            )
        return ClassificationResult(fields=fields, evidence=evidence)

    best = candidates[0]
    ttype, note = classify_target_type(best["target_raw"], context)
    source = best["target_source"]
    if source == "feature_note":
        confidence = "high"
        strength = "strong"
    elif source == "product":
        confidence = "high"
        strength = "strong"
    elif source == "description":
        confidence = "moderate"
        strength = "moderate"
    elif source == "reference_title":
        confidence = "low"
        strength = "weak"
    else:
        confidence = "low"
        strength = "weak"

    # Downgrade if only title and ambiguous
    if source == "reference_title" and ttype == "unknown":
        confidence = "low"

    fields = {
        "target_raw": best["target_raw"],
        "target_normalized": best["target_raw"],
        "target_type": ttype,
        "target_source": source,
        "target_confidence": confidence,
        "target_evidence_text": best["target_evidence_text"],
    }
    evidence.append(
        EvidenceItem(
            accession=accession,
            evidence_category="target",
            evidence_type="extracted_target_phrase",
            source_field=source,
            source_text=best["target_evidence_text"],
            normalized_value=f"{best['target_raw']}|{ttype}",
            evidence_strength=strength,
            supports_candidate=ttype in PROTEIN_COMPATIBLE_TARGET_TYPES,
            raises_concern=ttype in NON_CORE_TARGET_TYPES or ttype in {"peptide", "unknown"},
            notes=note,
        )
    )
    return ClassificationResult(fields=fields, evidence=evidence)


# ---------------------------------------------------------------------------
# Binding evidence
# ---------------------------------------------------------------------------


def assess_binding(record: dict[str, Any], target_fields: dict[str, Any]) -> ClassificationResult:
    accession = str(record.get("accession", ""))
    evidence: list[EvidenceItem] = []
    texts = {
        "feature_notes": str(record.get("feature_notes", "") or ""),
        "description": str(record.get("description", "") or ""),
        "products": str(record.get("products", "") or ""),
        "reference_titles": str(record.get("reference_titles", "") or ""),
    }
    combined = " || ".join(t for t in texts.values() if t)

    types: list[str] = []
    strength = "none"
    status = "none_found"
    affinity = parse_affinity(combined)
    assay = ""

    if affinity["affinity_raw"]:
        types.append("explicit_affinity")
        strength = "strong"
        status = "explicit_affinity"
        evidence.append(
            EvidenceItem(
                accession=accession,
                evidence_category="binding",
                evidence_type="explicit_affinity",
                source_field="combined_annotation",
                source_text=affinity["affinity_raw"],
                normalized_value=f"{affinity['affinity_value']} {affinity['affinity_unit']}".strip(),
                evidence_strength="strong",
                supports_candidate=True,
                notes="quantitative affinity phrase",
            )
        )

    binds_fields = []
    for fname, text in texts.items():
        if BINDS_RE.search(text):
            binds_fields.append(fname)
            snippet = text[:300]
            evidence.append(
                EvidenceItem(
                    accession=accession,
                    evidence_category="binding",
                    evidence_type="explicit_binds_or_recognizes_statement",
                    source_field=fname,
                    source_text=snippet,
                    normalized_value="binds_or_recognizes",
                    evidence_strength="strong" if fname == "feature_notes" else "moderate",
                    supports_candidate=True,
                    notes="",
                )
            )
    if binds_fields:
        types.append("explicit_binds_or_recognizes_statement")
        if strength not in {"strong"}:
            strength = "strong" if "feature_notes" in binds_fields else "moderate"
        if status == "none_found":
            status = "explicit_binds_or_recognizes_statement"

    selection_fields = []
    for fname, text in texts.items():
        if SELECTION_RE.search(text):
            selection_fields.append(fname)
    # Also honor inventory flags even if phrase regex missed typo variants
    if _truthy(record.get("mentions_selex")) or _truthy(record.get("mentions_in_vitro_selection")):
        if "inventory_flags" not in selection_fields:
            selection_fields.append("inventory_flags")
    if selection_fields:
        types.append("selection_against_target")
        if strength == "none":
            strength = "moderate"
        if status == "none_found":
            status = "selection_against_target"
        evidence.append(
            EvidenceItem(
                accession=accession,
                evidence_category="binding",
                evidence_type="selection_against_target",
                source_field="|".join(sorted(set(selection_fields))),
                source_text=combined[:300],
                normalized_value="selection_language",
                evidence_strength="moderate",
                supports_candidate=True,
                notes="selection language present; not alone proof of binding characterisation",
            )
        )

    if re.search(r"(?i)\b(?:inhibit(?:s|ing|ion)?|neutralis(?:es?|es?)|blocks?)\b", combined):
        types.append("inhibition_or_functional_effect")
        if strength in {"none", "weak"}:
            strength = "moderate"
        if status == "none_found":
            status = "inhibition_or_functional_effect"
        evidence.append(
            EvidenceItem(
                accession=accession,
                evidence_category="binding",
                evidence_type="inhibition_or_functional_effect",
                source_field="combined_annotation",
                source_text=combined[:300],
                normalized_value="functional_effect",
                evidence_strength="moderate",
                supports_candidate=True,
                notes="",
            )
        )

    if re.search(r"(?i)\b(?:crystal\s+structure|NMR\s+structure|structure\s+of\s+.*aptamer)\b", combined):
        types.append("structure_with_target")
        if strength in {"none", "weak"}:
            strength = "moderate"
        if status == "none_found":
            status = "structure_with_target"

    # Title-only protein co-occurrence → weak
    title = texts["reference_titles"]
    target_raw = str(target_fields.get("target_raw", "") or "")
    if (
        target_raw
        and target_fields.get("target_source") == "reference_title"
        and "explicit_binds_or_recognizes_statement" not in types
        and "explicit_affinity" not in types
    ):
        types.append("publication_title_only")
        if strength == "none":
            strength = "weak"
        if status == "none_found":
            status = "publication_title_only"
        evidence.append(
            EvidenceItem(
                accession=accession,
                evidence_category="binding",
                evidence_type="publication_title_only",
                source_field="reference_title",
                source_text=title[:300],
                normalized_value=target_raw,
                evidence_strength="weak",
                supports_candidate=True,
                raises_concern=True,
                notes="target inferred primarily from publication title",
            )
        )

    if not types:
        types = ["none_found"]

    # Assay/method hints
    assay_m = re.search(
        r"(?i)\b(SPR|ELISA|ITC|filter[\s-]?binding|EMSA|pull[\s-]?down|"
        r"fluorescence\s+anisotropy|BLI|MST)\b",
        combined,
    )
    if assay_m:
        assay = assay_m.group(1)

    fields = {
        "binding_evidence_status": status,
        "binding_evidence_types": "|".join(dict.fromkeys(types)),
        "binding_evidence_text": combined[:500],
        "binding_evidence_strength": strength,
        "affinity_raw": affinity["affinity_raw"],
        "affinity_value": affinity["affinity_value"],
        "affinity_unit": affinity["affinity_unit"],
        "assay_or_method": assay,
    }
    return ClassificationResult(fields=fields, evidence=evidence)


# ---------------------------------------------------------------------------
# Selection evidence (separate from binding strength)
# ---------------------------------------------------------------------------


def assess_selection(record: dict[str, Any]) -> ClassificationResult:
    accession = str(record.get("accession", ""))
    evidence: list[EvidenceItem] = []
    texts = {
        "feature_notes": str(record.get("feature_notes", "") or ""),
        "description": str(record.get("description", "") or ""),
        "keywords": str(record.get("keywords", "") or ""),
        "reference_titles": str(record.get("reference_titles", "") or ""),
        "matched_selection_terms": str(record.get("matched_selection_terms", "") or ""),
    }
    hits = []
    for fname, text in texts.items():
        if SELECTION_RE.search(text) or (fname == "matched_selection_terms" and text.strip()):
            hits.append(fname)
            evidence.append(
                EvidenceItem(
                    accession=accession,
                    evidence_category="selection",
                    evidence_type="selection_phrase",
                    source_field=fname,
                    source_text=text[:300],
                    normalized_value="selection",
                    evidence_strength="strong" if fname in {"feature_notes", "keywords"} else "moderate",
                    supports_candidate=True,
                    notes="",
                )
            )
    if _truthy(record.get("mentions_selex")) or _truthy(record.get("mentions_in_vitro_selection")):
        if "inventory_flags" not in hits:
            hits.append("inventory_flags")
        flag_bits = []
        if _truthy(record.get("mentions_selex")):
            flag_bits.append("mentions_selex")
        if _truthy(record.get("mentions_in_vitro_selection")):
            flag_bits.append("mentions_in_vitro_selection")
        evidence.append(
            EvidenceItem(
                accession=accession,
                evidence_category="selection",
                evidence_type="selection_phrase",
                source_field="inventory_flags",
                source_text="|".join(flag_bits),
                normalized_value="selection",
                evidence_strength="moderate",
                supports_candidate=True,
                notes="selection inferred from inspection inventory flags",
            )
        )

    if hits:
        strength = "strong" if any(h in {"feature_notes", "keywords"} for h in hits) else "moderate"
        summary = "selection_language:" + "|".join(sorted(set(hits)))
    else:
        strength = "none"
        summary = "no_explicit_selection_language"

    return ClassificationResult(
        fields={
            "selection_evidence": summary,
            "selection_evidence_strength": strength,
        },
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# RNA identity
# ---------------------------------------------------------------------------


def assess_rna_identity(record: dict[str, Any]) -> ClassificationResult:
    accession = str(record.get("accession", ""))
    evidence: list[EvidenceItem] = []
    mol = str(record.get("molecule_type", "") or "")
    desc = str(record.get("description", "") or "")
    notes = str(record.get("feature_notes", "") or "")
    titles = str(record.get("reference_titles", "") or "")
    alphabet = str(record.get("sequence_alphabet", "") or "")
    seq = str(record.get("sequence_deposited", "") or "")
    has_t7 = _truthy(record.get("contains_t7_promoter_like_motif"))
    dna_template_signal = _truthy(record.get("signal_dna_template_or_promoter"))

    mol_l = mol.lower()
    blob = f"{desc} || {notes} || {titles}"

    status = "uncertain_nucleic_acid_type"
    confidence = "low"
    reason_parts: list[str] = []

    if DNA_APTAMER_RE.search(blob) and not RNA_APTAMER_RE.search(blob):
        status = "dna_aptamer"
        confidence = "high"
        reason_parts.append("explicit_dna_aptamer_language")
    elif (has_t7 or dna_template_signal or TEMPLATE_PROMOTER_RE.search(blob)) and (
        "dna" in mol_l or has_t7
    ):
        status = "possible_dna_template_for_rna"
        confidence = "moderate"
        reason_parts.append("promoter_or_template_signal")
    elif RNA_APTAMER_RE.search(blob) or re.search(
        r"(?i)\bRNA\s+molecules?\b.*aptamer|aptamer.*\bRNA\b", blob
    ):
        if "dna" in mol_l and "rna" not in mol_l:
            status = (
                "rna_described_but_dna_alphabet"
                if alphabet == "DNA_alphabet"
                else "possible_dna_template_for_rna"
            )
            confidence = "moderate"
            reason_parts.append("rna_aptamer_described_with_dna_molecule_type")
        elif "rna" in mol_l:
            status = "explicit_rna_aptamer"
            confidence = "high"
            reason_parts.append("explicit_rna_aptamer_plus_rna_molecule_type")
        else:
            status = "explicit_rna_aptamer"
            confidence = "moderate"
            reason_parts.append("explicit_rna_aptamer_language")
    elif "rna" in mol_l and APTAMER_RE.search(blob):
        status = "rna_molecule_type"
        confidence = "moderate"
        reason_parts.append("rna_molecule_type_with_aptamer_mention")
    elif "dna" in mol_l and APTAMER_RE.search(blob):
        # DNA molecule + aptamer without RNA wording
        if re.search(r"(?i)\bRNA\b", blob):
            status = "possible_dna_template_for_rna"
            confidence = "low"
            reason_parts.append("dna_record_mentions_rna")
        else:
            status = "dna_aptamer"
            confidence = "moderate"
            reason_parts.append("dna_molecule_type_aptamer_without_rna_language")
    elif APTAMER_RE.search(blob):
        status = "uncertain_nucleic_acid_type"
        confidence = "low"
        reason_parts.append("aptamer_mention_only")
    else:
        status = "not_rna_aptamer"
        confidence = "moderate"
        reason_parts.append("no_clear_rna_aptamer_signal")

    # Alphabet alone must not override biological classification
    evidence.append(
        EvidenceItem(
            accession=accession,
            evidence_category="rna_identity",
            evidence_type=status,
            source_field="molecule_type|description|feature_notes",
            source_text=f"molecule_type={mol}; alphabet={alphabet}; desc={desc[:160]}",
            normalized_value=status,
            evidence_strength=confidence if confidence != "low" else "weak",
            supports_candidate=status
            in {
                "explicit_rna_aptamer",
                "rna_molecule_type",
                "rna_described_but_dna_alphabet",
                "possible_dna_template_for_rna",
            },
            raises_concern=status in {"dna_aptamer", "uncertain_nucleic_acid_type", "not_rna_aptamer"},
            notes=";".join(reason_parts),
        )
    )

    normalize = status in {
        "explicit_rna_aptamer",
        "rna_molecule_type",
        "rna_described_but_dna_alphabet",
    }
    rna_seq = rna_normalize_sequence(seq) if normalize and seq else ""
    fields = {
        "rna_identity_status": status,
        "rna_identity_confidence": confidence,
        "rna_identity_evidence": ";".join(reason_parts) or status,
        "sequence_rna_normalized": rna_seq,
        "rna_normalization_applied": bool(rna_seq),
        "rna_normalization_reason": (
            "confident_rna_identity_T_to_U"
            if rna_seq
            else "not_applied_insufficient_rna_confidence_or_empty_sequence"
        ),
    }
    return ClassificationResult(fields=fields, evidence=evidence)


# ---------------------------------------------------------------------------
# Sequence role
# ---------------------------------------------------------------------------


def extract_feature_sequence(
    sequence_deposited: str,
    start: Any,
    end: Any,
    is_complement: bool,
) -> dict[str, Any]:
    """Extract a subsequence using 1-based inclusive coordinates."""
    result = {
        "feature_sequence_deposited": "",
        "feature_sequence_rna_normalized": "",
        "feature_start": "",
        "feature_end": "",
        "feature_strand": "",
        "feature_sequence_extraction_method": "",
    }
    if not sequence_deposited:
        return result
    try:
        s = int(start)
        e = int(end)
    except (TypeError, ValueError):
        return result
    if s < 1 or e < s or e > len(sequence_deposited):
        return result
    sub = sequence_deposited[s - 1 : e]
    method = "direct_span"
    strand = "+"
    if isinstance(is_complement, bool):
        apply_complement = is_complement
    else:
        apply_complement = str(is_complement).strip().lower() in {
            "true",
            "1",
            "-",
            "yes",
            "t",
        }
    if apply_complement:
        sub = reverse_complement(sub)
        method = "reverse_complement_of_span"
        strand = "-"
    result.update(
        {
            "feature_sequence_deposited": sub,
            "feature_sequence_rna_normalized": rna_normalize_sequence(sub),
            "feature_start": s,
            "feature_end": e,
            "feature_strand": strand,
            "feature_sequence_extraction_method": method,
        }
    )
    return result


def assess_sequence_role(
    record: dict[str, Any],
    rna_fields: dict[str, Any],
    feature_info: dict[str, Any] | None = None,
) -> ClassificationResult:
    accession = str(record.get("accession", ""))
    evidence: list[EvidenceItem] = []
    desc = str(record.get("description", "") or "")
    notes = str(record.get("feature_notes", "") or "")
    titles = str(record.get("reference_titles", "") or "")
    blob = f"{desc} || {notes} || {titles}"
    mol = str(record.get("molecule_type", "") or "").lower()
    length = int(float(record.get("reported_length") or record.get("record_length") or 0) or 0)
    has_t7 = _truthy(record.get("contains_t7_promoter_like_motif"))
    dna_template = _truthy(record.get("signal_dna_template_or_promoter"))
    natural = _truthy(record.get("signal_natural_or_genomic"))
    riboswitch = _truthy(record.get("signal_riboswitch_related")) or bool(RIBOSWITCH_RE.search(blob))
    engineered = _truthy(record.get("signal_engineered_construct")) or bool(
        ENGINEERED_SWITCH_RE.search(blob)
    )
    complement = _truthy(record.get("signal_reverse_complement_feature")) or _truthy(
        record.get("has_complement_feature")
    )

    role = "unknown_sequence_role"
    confidence = "low"
    reasons: list[str] = []

    feat = feature_info or {}
    feat_len = feat.get("feature_length")
    try:
        feat_len_i = int(feat_len) if feat_len not in (None, "") else None
    except (TypeError, ValueError):
        feat_len_i = None

    if riboswitch:
        role = "riboswitch_domain"
        confidence = "high"
        reasons.append("riboswitch_language_or_signal")
    elif natural and not _truthy(record.get("mentions_selex")):
        role = "natural_genomic_motif"
        confidence = "moderate"
        reasons.append("natural_or_genomic_signal")
    elif engineered and ENGINEERED_SWITCH_RE.search(blob):
        role = "aptazyme_or_switch_construct"
        confidence = "high"
        reasons.append("engineered_switch_language")
    elif has_t7 or (dna_template and TEMPLATE_PROMOTER_RE.search(blob)):
        if "dna" in mol or has_t7:
            role = "promoter_plus_rna_template" if has_t7 else "dna_template_for_rna_aptamer"
            confidence = "high" if has_t7 else "moderate"
            reasons.append("t7_or_template_evidence")
    elif complement and feat.get("is_complement"):
        role = "reverse_complement_feature"
        confidence = "moderate"
        reasons.append("complement_feature_location")
    elif feat_len_i is not None and length > 0 and feat_len_i < length * 0.85 and feat_len_i >= 15:
        core_or_minimal_aptamer = bool(
            re.search(r"(?i)\b(?:core|minimal)\s+aptamer\b", blob)
        )
        if PRIMER_FLANK_RE.search(blob) or core_or_minimal_aptamer:
            role = (
                "selected_rna_aptamer_core"
                if core_or_minimal_aptamer
                else "aptamer_embedded_in_construct"
            )
            confidence = "moderate"
            reasons.append("subregion_feature_shorter_than_record")
        else:
            role = "aptamer_embedded_in_construct"
            confidence = "low"
            reasons.append("partial_feature_span")
    elif PRIMER_FLANK_RE.search(blob):
        role = "primer_flanked_library_sequence"
        confidence = "moderate"
        reasons.append("primer_or_flank_language")
    elif (
        rna_fields.get("rna_identity_status")
        in {"explicit_rna_aptamer", "rna_molecule_type", "rna_described_but_dna_alphabet"}
        and 15 <= length <= 200
        and not has_t7
    ):
        if re.search(r"(?i)\bcomplete\s+sequence\b", blob) or feat.get("feature_is_full_record"):
            role = "selected_full_length_rna_aptamer"
            confidence = "moderate"
            reasons.append("full_length_like_rna_aptamer")
        elif re.search(r"(?i)\b(?:core|minimal)\s+aptamer\b", blob):
            role = "selected_rna_aptamer_core"
            confidence = "moderate"
            reasons.append("core_or_minimal_language")
        else:
            role = "selected_full_length_rna_aptamer"
            confidence = "low"
            reasons.append("plausible_length_rna_aptamer")
    elif "flank" in blob.lower() or "primer" in blob.lower():
        role = "rna_aptamer_with_flanks"
        confidence = "low"
        reasons.append("flank_language")

    evidence.append(
        EvidenceItem(
            accession=accession,
            evidence_category="sequence_role",
            evidence_type=role,
            source_field="description|feature_notes|signals",
            source_text=blob[:300],
            normalized_value=role,
            evidence_strength=confidence if confidence != "low" else "weak",
            supports_candidate=role
            in {
                "selected_full_length_rna_aptamer",
                "selected_rna_aptamer_core",
                "rna_aptamer_with_flanks",
            },
            raises_concern=role
            in {
                "dna_template_for_rna_aptamer",
                "promoter_plus_rna_template",
                "natural_genomic_motif",
                "riboswitch_domain",
                "aptazyme_or_switch_construct",
                "unknown_sequence_role",
            },
            notes=";".join(reasons),
        )
    )

    fields = {
        "sequence_role": role,
        "sequence_role_confidence": confidence,
        "sequence_role_evidence": ";".join(reasons) or role,
    }
    return ClassificationResult(fields=fields, evidence=evidence)


# ---------------------------------------------------------------------------
# Tier assignment
# ---------------------------------------------------------------------------


def assign_candidate_tier(
    record: dict[str, Any],
    rna: dict[str, Any],
    target: dict[str, Any],
    binding: dict[str, Any],
    selection: dict[str, Any],
    role: dict[str, Any],
) -> ClassificationResult:
    accession = str(record.get("accession", ""))
    evidence: list[EvidenceItem] = []

    rna_status = rna.get("rna_identity_status", "")
    target_type = target.get("target_type", "unknown")
    binding_strength = binding.get("binding_evidence_strength", "none")
    selection_strength = selection.get("selection_evidence_strength", "none")
    seq_role = role.get("sequence_role", "unknown_sequence_role")
    synthetic = _truthy(record.get("mentions_synthetic_construct")) or str(
        record.get("organism", "")
    ).lower() in {"synthetic construct", "artificial sequences"}

    reasons: list[str] = []

    # Tier D: non-core / exclude
    if seq_role == "riboswitch_domain" or _truthy(record.get("signal_riboswitch_related")):
        tier = "Tier_D_non_core_or_exclude"
        reasons.append("riboswitch")
    elif seq_role == "natural_genomic_motif" or (
        _truthy(record.get("signal_natural_or_genomic"))
        and not synthetic
        and selection_strength == "none"
    ):
        tier = "Tier_D_non_core_or_exclude"
        reasons.append("natural_or_genomic_motif")
    elif seq_role == "aptazyme_or_switch_construct":
        tier = "Tier_D_non_core_or_exclude"
        reasons.append("engineered_switch")
    elif rna_status == "dna_aptamer":
        tier = "Tier_D_non_core_or_exclude"
        reasons.append("dna_aptamer")
    elif target_type in {"small_molecule", "ion", "nucleic_acid", "natural_ligand", "peptide"}:
        tier = "Tier_D_non_core_or_exclude"
        reasons.append(f"non_protein_target:{target_type}")
    elif target_type in {"cell_or_tissue", "virus_or_virion"}:
        tier = "Tier_D_non_core_or_exclude"
        reasons.append("cell_or_virus_without_named_protein")
    elif rna_status == "not_rna_aptamer" and not APTAMER_RE.search(
        str(record.get("description", "")) + str(record.get("feature_notes", ""))
    ):
        tier = "Tier_D_non_core_or_exclude"
        reasons.append("invalid_or_unrelated")
    # Tier C: sequence role uncertain
    elif seq_role in {
        "dna_template_for_rna_aptamer",
        "promoter_plus_rna_template",
        "primer_flanked_library_sequence",
        "aptamer_embedded_in_construct",
        "reverse_complement_feature",
        "rna_aptamer_with_flanks",
    } or rna_status == "possible_dna_template_for_rna":
        tier = "Tier_C_sequence_role_uncertain"
        reasons.append(f"sequence_role:{seq_role}")
    else:
        protein_ok = target_type in PROTEIN_COMPATIBLE_TARGET_TYPES
        rna_ok = rna_status in {
            "explicit_rna_aptamer",
            "rna_molecule_type",
            "rna_described_but_dna_alphabet",
        }
        binding_ok = binding_strength in {"strong", "moderate"}
        selection_ok = selection_strength in {"strong", "moderate"}
        role_ok = seq_role in {
            "selected_full_length_rna_aptamer",
            "selected_rna_aptamer_core",
        }
        length = int(float(record.get("reported_length") or record.get("record_length") or 0) or 0)
        length_ok = 15 <= length <= 250
        no_strong_natural = not (
            _truthy(record.get("signal_natural_or_genomic")) and not synthetic
        )

        # Tier A: defensible combination — not every signal, but several strong ones.
        # Synthetic alone is NEVER enough.
        strong_combo = (
            rna_ok
            and protein_ok
            and (binding_ok or selection_ok)
            and (role_ok or length_ok)
            and no_strong_natural
            and (
                binding_strength == "strong"
                or (selection_ok and binding_ok and target.get("target_confidence") in {"high", "moderate"})
                or (
                    selection_strength == "strong"
                    and target.get("target_confidence") == "high"
                    and rna_status == "explicit_rna_aptamer"
                    and binding_ok
                )
            )
            and not (
                synthetic
                and selection_strength == "none"
                and binding_strength != "strong"
            )
        )

        if strong_combo and target.get("target_source") in {"feature_note", "product", "description"}:
            # Tier A requires feature/product-level characterisation OR strong binding,
            # not patent-title/description + inventory SELEX flag alone.
            selection_from_annotation = "feature_notes" in str(
                selection.get("selection_evidence", "")
            ) or "keywords" in str(selection.get("selection_evidence", ""))
            if binding_strength == "strong" and target.get("target_source") in {
                "feature_note",
                "product",
            }:
                tier = "Tier_A_high_confidence"
                reasons.append("strong_binding_with_annotated_protein_target")
            elif (
                selection_from_annotation
                and binding_ok
                and target.get("target_source") in {"feature_note", "product"}
                and target.get("target_confidence") == "high"
            ):
                tier = "Tier_A_high_confidence"
                reasons.append("strong_combined_rna_protein_binding_evidence")
            else:
                tier = "Tier_B_plausible_needs_review"
                reasons.append("plausible_but_not_feature_characterised_enough_for_tier_a")
        elif rna_ok and protein_ok and (binding_ok or selection_ok or target.get("target_raw")):
            tier = "Tier_B_plausible_needs_review"
            reasons.append("plausible_rna_protein_candidate_needs_review")
            if target.get("target_source") == "reference_title":
                reasons.append("target_from_title_only")
            if not (record.get("doi_values") or record.get("pubmed_values")):
                reasons.append("missing_publication_ids")
        elif APTAMER_RE.search(str(record.get("description", "")) + str(record.get("feature_notes", ""))):
            if protein_ok and target.get("target_raw"):
                # Aptamer wording + protein target, but RNA identity not yet confident enough
                # for the main Tier B gate (rna_ok). Keep as reviewable, not insufficient.
                tier = "Tier_B_plausible_needs_review"
                reasons.append("aptamer_and_protein_target_with_uncertain_rna_identity")
                if target.get("target_source") == "reference_title":
                    reasons.append("target_from_title_only")
            else:
                tier = "Tier_E_insufficient_information"
                reasons.append("aptamer_sequence_present_but_target_or_binding_unresolved")
        else:
            tier = "Tier_E_insufficient_information"
            reasons.append("insufficient_information")

        # Guard: synthetic alone must not create Tier A
        if tier == "Tier_A_high_confidence" and synthetic and selection_strength == "none" and binding_strength != "strong":
            tier = "Tier_B_plausible_needs_review"
            reasons.append("downgraded_synthetic_without_selection_or_strong_binding")

    # Corpus relevance
    if tier == "Tier_A_high_confidence":
        corpus = "potential_rna_protein_pair"
    elif tier == "Tier_B_plausible_needs_review" and target_type in PROTEIN_COMPATIBLE_TARGET_TYPES:
        corpus = "possible_rna_protein_pair"
    elif tier == "Tier_C_sequence_role_uncertain":
        corpus = "sequence_role_unresolved"
    elif tier == "Tier_D_non_core_or_exclude":
        corpus = "not_core_target_type" if target_type in NON_CORE_TARGET_TYPES | {"peptide"} else "insufficient_evidence"
        if "riboswitch" in reasons or "natural" in "".join(reasons) or "dna_aptamer" in reasons:
            corpus = "not_core_target_type"
    else:
        corpus = "insufficient_evidence"

    manual = tier in {
        "Tier_A_high_confidence",
        "Tier_B_plausible_needs_review",
        "Tier_C_sequence_role_uncertain",
    } or binding_strength == "strong"

    if tier == "Tier_A_high_confidence":
        priority = 1
    elif tier == "Tier_B_plausible_needs_review" and target_type in PROTEIN_COMPATIBLE_TARGET_TYPES:
        priority = 2
    elif tier == "Tier_C_sequence_role_uncertain":
        priority = 3
    elif binding_strength == "strong":
        priority = 2
    else:
        priority = 5

    fields = {
        "candidate_tier": tier,
        "candidate_rationale": ";".join(reasons),
        "corpus_relevance_status": corpus,
        "manual_review_required": manual,
        "review_priority": priority,
    }
    evidence.append(
        EvidenceItem(
            accession=accession,
            evidence_category="tier",
            evidence_type=tier,
            source_field="derived",
            source_text=";".join(reasons),
            normalized_value=tier,
            evidence_strength="provisional",
            supports_candidate=tier in {"Tier_A_high_confidence", "Tier_B_plausible_needs_review"},
            raises_concern=tier in {"Tier_D_non_core_or_exclude", "Tier_E_insufficient_information"},
            notes="provisional_tier_not_final_inclusion",
        )
    )
    return ClassificationResult(fields=fields, evidence=evidence)


def exclusion_category_for(tier_fields: dict[str, Any], target: dict[str, Any], role: dict[str, Any], rna: dict[str, Any]) -> str:
    rationale = str(tier_fields.get("candidate_rationale", ""))
    if "riboswitch" in rationale:
        return "riboswitch"
    if "natural_or_genomic" in rationale:
        return "natural_or_genomic_motif"
    if "engineered_switch" in rationale:
        return "engineered_switch"
    if "dna_aptamer" in rationale or rna.get("rna_identity_status") == "dna_aptamer":
        return "dna_aptamer"
    if "cell_or_virus" in rationale:
        return "cell_or_virus_without_named_protein"
    if "non_protein_target" in rationale:
        return "non_protein_target"
    if "invalid" in rationale:
        return "invalid_or_unrelated"
    if tier_fields.get("candidate_tier") == "Tier_E_insufficient_information":
        if not target.get("target_raw"):
            return "insufficient_target_information"
        return "insufficient_binding_evidence"
    return "non_protein_target"


def recommended_review_action(
    tier: str,
    role: str,
    target_source: str,
    binding_strength: str,
    has_conflict: bool,
) -> str:
    if has_conflict:
        return "resolve duplicate family"
    if tier == "Tier_D_non_core_or_exclude" and role in {"natural_genomic_motif", "riboswitch_domain"}:
        return "exclude natural motif"
    if role in {"promoter_plus_rna_template", "dna_template_for_rna_aptamer", "primer_flanked_library_sequence"}:
        return "inspect promoter/flanks"
    if role in {"aptamer_embedded_in_construct", "reverse_complement_feature"}:
        return "inspect feature coordinates"
    if target_source == "reference_title":
        return "confirm protein target"
    if binding_strength in {"none", "weak"}:
        return "confirm binding evidence"
    if role in {"unknown_sequence_role", "rna_aptamer_with_flanks"}:
        return "confirm mature RNA sequence"
    return "verify paper"
