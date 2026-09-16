"""UniProt proposal resolution: source seed, local maps, optional cached lookup."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Mapping

from adapters.s4_scientific_common import (
    ScientificProposalError,
    alias_candidate_key,
    join_unique,
    primary_match_key,
)

UNIPROT_ACC_RE = re.compile(r"^[OPQ][0-9][A-Z0-9]{3}[0-9]$|^[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9]$")


def is_uniprot_accession(value: str) -> bool:
    return bool(UNIPROT_ACC_RE.fullmatch((value or "").strip()))


def load_aptadb_protein_table(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [{key: row.get(key, "") or "" for key in (reader.fieldnames or [])} for row in reader]


def build_local_uniprot_index(rows: list[Mapping[str, str]]) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        accession = (row.get("Uni-port ID") or "").strip()
        if not accession:
            continue
        names = [row.get("Protein names") or "", row.get("Entry name") or "", row.get("Gene names") or ""]
        keys: set[str] = set()
        for name in names:
            for part in re.split(r"[;|/]", name):
                part = part.strip()
                if not part:
                    continue
                keys.add(primary_match_key(part))
                keys.add(alias_candidate_key(part))
                for paren in re.findall(r"\(([^)]+)\)", part):
                    if 2 <= len(paren.strip()) <= 80:
                        keys.add(primary_match_key(paren))
                        keys.add(alias_candidate_key(part))
        organism = (row.get("Organism") or "").strip()
        payload = {
            "accession": accession,
            "protein_names": row.get("Protein names") or "",
            "gene_names": row.get("Gene names") or "",
            "organism": organism,
            "entry_name": row.get("Entry name") or "",
            "pdb": row.get("Cross-reference (PDB)") or "",
            "function": row.get("Function") or "",
            "catalytic_activity": row.get("Catalytic activity") or "",
        }
        for key in keys:
            if not key or len(key) < 3:
                continue
            if payload not in index[key]:
                index[key].append(payload)
    return index


def _unique_accessions(hits: list[Mapping[str, str]]) -> list[str]:
    return list(dict.fromkeys(item["accession"] for item in hits if item.get("accession")))


def cache_path(cache_dir: Path, query: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", query)[:120]
    digest = __import__("hashlib").sha256(query.encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"{digest}_{safe}.json"


def read_cache(cache_dir: Path, query: str) -> dict | None:
    path = cache_path(cache_dir, query)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_cache(cache_dir: Path, query: str, payload: Mapping) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path(cache_dir, query)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def uniprot_search(
    query_name: str,
    *,
    cache_dir: Path,
    api_base: str,
    api_version: str,
    organism: str = "",
    allow_network: bool = False,
) -> dict:
    """Deterministic UniProt search with on-disk cache. Never ranks-to-accept."""
    parts = [f'protein_name:"{query_name}"']
    if organism:
        parts.append(f"organism_name:{organism}")
    query = " AND ".join(parts)
    cached = read_cache(cache_dir, query)
    if cached is not None:
        return cached
    payload = {
        "query": query,
        "query_name": query_name,
        "organism": organism,
        "api_base": api_base,
        "api_version": api_version,
        "results": [],
        "error": "",
        "from_network": False,
    }
    if not allow_network:
        payload["error"] = "network_disabled"
        return payload
    params = urllib.parse.urlencode(
        {
            "query": query,
            "fields": "accession,protein_name,organism_name,gene_primary,reviewed,xref_pfam,xref_interpro,cc_function,keyword",
            "format": "json",
            "size": "10",
        }
    )
    url = f"{api_base}?{params}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "rnagenesis-aptamer-mres-s4-proposals/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        payload["from_network"] = True
        payload["http_status"] = int(getattr(response, "status", 200) or 200)
        payload["results"] = body.get("results") or []
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        payload["error"] = f"uniprot_lookup_failed:{type(exc).__name__}"
    write_cache(cache_dir, query, payload)
    return payload


def _exact_name_hits(results: list[Mapping], query_name: str) -> list[str]:
    wanted = primary_match_key(query_name)
    accessions: list[str] = []
    for item in results:
        accession = (item.get("primaryAccession") or "").strip()
        if not accession:
            continue
        names: list[str] = []
        protein = item.get("proteinDescription") or {}
        rec = protein.get("recommendedName") or {}
        full = rec.get("fullName") or {}
        if isinstance(full, dict):
            names.append(full.get("value") or "")
        for alt in protein.get("alternativeNames") or []:
            alt_full = alt.get("fullName") or {}
            if isinstance(alt_full, dict):
                names.append(alt_full.get("value") or "")
        if any(primary_match_key(name) == wanted for name in names if name):
            accessions.append(accession)
    return list(dict.fromkeys(accessions))


def resolve_uniprot(
    *,
    raw_target: str,
    source_uniprot_seed: str,
    target_type: str,
    organism_context: str = "",
    local_index: Mapping[str, list[dict[str, str]]] | None = None,
    cache_dir: Path | None = None,
    api_base: str = "",
    api_version: str = "",
    allow_network: bool = False,
) -> dict[str, str]:
    """Resolve a UniProt proposal. Protein-only. Never merge conflicting seeds."""
    blank = {
        "uniprot_proposed": "",
        "uniprot_candidates": "",
        "uniprot_resolution_tier": "",
        "uniprot_query": "",
        "uniprot_organism_context": organism_context,
        "uniprot_ambiguity_reason": "",
        "pfam_from_uniprot": "",
        "interpro_from_uniprot": "",
        "family_clue_from_uniprot": "",
        "uniprot_requires_review": "false",
    }
    if target_type not in {"protein", "peptide"}:
        return blank
    seed = (source_uniprot_seed or "").strip()
    if seed:
        seeds = [item.strip() for item in seed.split("|") if item.strip()]
        if len(seeds) == 1 and is_uniprot_accession(seeds[0]):
            blank.update(
                {
                    "uniprot_proposed": seeds[0],
                    "uniprot_candidates": seeds[0],
                    "uniprot_resolution_tier": "U1_source_linked",
                    "uniprot_query": raw_target,
                }
            )
            return blank
        blank.update(
            {
                "uniprot_candidates": join_unique(seeds),
                "uniprot_resolution_tier": "U1_source_linked",
                "uniprot_query": raw_target,
                "uniprot_ambiguity_reason": "source_uniprot_seed_conflict",
                "uniprot_requires_review": "true",
            }
        )
        return blank

    keys = [primary_match_key(raw_target), alias_candidate_key(raw_target)]
    hits: list[dict[str, str]] = []
    if local_index:
        for key in keys:
            hits.extend(local_index.get(key, []))
    unique = _unique_accessions(hits)
    if len(unique) == 1:
        blank.update(
            {
                "uniprot_proposed": unique[0],
                "uniprot_candidates": unique[0],
                "uniprot_resolution_tier": "U2_local_structured",
                "uniprot_query": raw_target,
                "uniprot_organism_context": hits[0].get("organism", organism_context)
                if hits
                else organism_context,
            }
        )
        return blank
    if len(unique) > 1:
        organisms = join_unique([item.get("organism", "") for item in hits])
        blank.update(
            {
                "uniprot_candidates": join_unique(unique),
                "uniprot_resolution_tier": "U2_local_structured",
                "uniprot_query": raw_target,
                "uniprot_organism_context": organisms,
                "uniprot_ambiguity_reason": "multiple_local_uniprot_candidates",
                "uniprot_requires_review": "true",
            }
        )
        return blank

    if cache_dir is None or not api_base:
        blank["uniprot_resolution_tier"] = "unresolved"
        return blank

    lookup = uniprot_search(
        raw_target,
        cache_dir=cache_dir,
        api_base=api_base,
        api_version=api_version,
        organism=organism_context,
        allow_network=allow_network,
    )
    blank["uniprot_query"] = lookup.get("query", raw_target)
    blank["uniprot_resolution_tier"] = "U3_external_lookup"
    if lookup.get("error") and not lookup.get("results"):
        if lookup["error"] == "network_disabled":
            blank["uniprot_resolution_tier"] = "unresolved"
            return blank
        blank["uniprot_ambiguity_reason"] = lookup["error"]
        blank["uniprot_resolution_tier"] = "unresolved"
        return blank
    exact = _exact_name_hits(lookup.get("results") or [], raw_target)
    if len(exact) == 1:
        blank.update(
            {
                "uniprot_proposed": exact[0],
                "uniprot_candidates": exact[0],
            }
        )
        return blank
    if len(exact) > 1:
        blank.update(
            {
                "uniprot_candidates": join_unique(exact),
                "uniprot_ambiguity_reason": "multiple_external_uniprot_candidates",
                "uniprot_requires_review": "true",
            }
        )
        return blank
    blank["uniprot_ambiguity_reason"] = "no_unambiguous_uniprot_match"
    blank["uniprot_resolution_tier"] = "unresolved"
    return blank
