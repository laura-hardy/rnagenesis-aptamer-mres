"""S6 report, figure, and CHECKPOINT-3 rendering.

Supervisor-facing text is plain English first, with technical audit
material in the appendix. Figures are deterministic and sequence-free.
"""

from __future__ import annotations

import math
import os
import tempfile
import textwrap
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from adapters.s4_scientific_common import write_json_atomic, write_text_atomic
from adapters.s6_profile import (
    CHECKPOINT3_DECISION_COLUMNS,
    CORE_FULL_COMPARISON_COLUMNS,
    HUMAN_CHECKPOINT_FIELDS,
    S6Assembly,
    S6ProfileError,
    S7_UNSPECIFIED_ITEMS,
    SOURCE_REGIME_COLUMNS,
    TOP_N_TARGETS,
    assert_no_sequence_leak,
    assert_not_frozen_s5_path,
    fmt_float,
    fmt_pct,
    scientific_payload,
)
from common.corpus_schema import write_corpus_csv_atomic

FIGURE_FILENAMES: tuple[str, ...] = (
    "fig01_top30_targets.png",
    "fig02_target_family.png",
    "fig03_sequence_core_length.png",
    "fig04_sequence_full_length.png",
    "fig05_gc_distribution.png",
    "fig06_cluster_size.png",
    "fig07_evidence_level.png",
    "fig08_source_contribution.png",
    "fig09_candidate_target_cap.png",
    "fig10_corroboration.png",
)

PREFERRED_SOURCE_FACET_ORDER: tuple[str, ...] = (
    "aptamerbase",
    "ena",
    "riboaptamer",
    "utexas",
    "aptabase",
    "aptadb",
    "aptaindex",
)

SOURCE_DISPLAY_NAMES: dict[str, str] = {
    "aptabase": "Aptabase",
    "aptadb": "AptaDB",
    "aptaindex": "AptaIndex",
    "aptamerbase": "AptamerBase",
    "ena": "ENA",
    "ncbi_nuc": "NCBI Nuc",
    "riboaptamer": "Riboaptamer",
    "utexas": "UT Austin",
}

FAMILY_DISPLAY_NAMES: dict[str, str] = {
    "transcription_factor": "transcription factor",
    "viral_protein": "viral protein",
    "antibody/immunoglobulin": "antibody / immunoglobulin",
    "growth_factor": "growth factor",
    "transport_protein": "transport protein",
}

EVIDENCE_DISPLAY: dict[str, str] = {
    "E2": "Quantitative affinity\n(E2)",
    "E3": "Qualitative binding\n(E3)",
    "E4": "Selection / enrichment\n(E4)",
}

PRIMARY_EVIDENCE_LEVELS: tuple[str, ...] = ("E2", "E3", "E4")
E5_PARKED_NOTE = (
    "E5 database/deposit-only records are parked and are not included in this primary corpus."
)
LENGTH_BIN_WIDTH = 2
FIG01_N_ANNOTATE = 3
REGIME_PREDOMINANT_PCT = 70.0


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if hasattr(value, "item") and callable(value.item):
        try:
            return _jsonable(value.item())
        except Exception:
            pass
    return value


def _md_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "/").replace("\n", " ").strip()


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(_md_cell(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(item) for item in row) + " |")
    return lines


def _comma(value: int | str) -> str:
    return f"{int(value):,}"


def _pct(n: int, d: int, digits: int = 2) -> str:
    if d == 0:
        return "n/a"
    return f"{fmt_pct(n, d, digits)}%"


def source_display_name(value: str) -> str:
    return SOURCE_DISPLAY_NAMES.get(value, value.replace("_", " "))


def display_target_name(value: str) -> str:
    return value.replace("_", " ")


def family_display_name(value: str) -> str:
    if value in FAMILY_DISPLAY_NAMES:
        return FAMILY_DISPLAY_NAMES[value]
    return value.replace("_", " ")


def _join_and(names: Sequence[str]) -> str:
    items = [str(name) for name in names]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _target_row(assembly: S6Assembly, name: str) -> dict[str, str] | None:
    return next(
        (row for row in assembly.target_rows if row["canonical_target_name"] == name),
        None,
    )


def _family_row(assembly: S6Assembly, name: str) -> dict[str, str] | None:
    return next((row for row in assembly.family_rows if row["target_family"] == name), None)


def _source_regime_rows(assembly: S6Assembly, *, include_all: bool = False) -> list[dict[str, str]]:
    rows = list(assembly.source_regime_rows)
    if include_all:
        return rows
    return [row for row in rows if row["source_db"] != "all"]


def donor_facet_sources(assembly: S6Assembly) -> list[str]:
    present = [src for src, values in assembly.core_lengths_by_source.items() if values]
    ordered = [src for src in PREFERRED_SOURCE_FACET_ORDER if src in present]
    extras = sorted(src for src in present if src not in PREFERRED_SOURCE_FACET_ORDER)
    return ordered + extras


def length_histogram_bins(values: Sequence[int], *, width: int = LENGTH_BIN_WIDTH) -> list[int]:
    if not values:
        return [0, width]
    max_v = max(int(v) for v in values)
    end = max_v + width
    if end % width:
        end += width - (end % width)
    return list(range(0, end + width, width))


def cluster_targets_for_core_size(assembly: S6Assembly, size: int) -> list[str]:
    names: list[str] = []
    for row in assembly.cluster_rows:
        if int(row["n_distinct_sequence_core"]) != size:
            continue
        names.extend(
            part for part in str(row.get("canonical_targets", "")).split("|") if part
        )
    return sorted(set(names))


def _regime_pattern_sentence(assembly: S6Assembly) -> str:
    rows = _source_regime_rows(assembly)
    shorter: list[str] = []
    longer: list[str] = []
    mixed: list[str] = []
    for row in rows:
        pct_short = float(row["pct_shorter_regime"] or 0.0)
        pct_long = float(row["pct_longer_regime"] or 0.0)
        name = source_display_name(row["source_db"])
        if pct_short >= REGIME_PREDOMINANT_PCT:
            shorter.append(name)
        elif pct_long >= REGIME_PREDOMINANT_PCT:
            longer.append(name)
        else:
            mixed.append(name)
    parts: list[str] = []
    if shorter:
        parts.append(
            f"{_join_and(shorter)} assigned predominantly to the shorter regime"
        )
    if longer:
        parts.append(
            f"{_join_and(longer)} assigned predominantly to the longer regime"
        )
    if mixed:
        parts.append(f"{_join_and(mixed)} more mixed")
    if not parts:
        return "Length-regime membership varies by donor source."
    return "Observed source association: " + "; ".join(parts) + "."


def source_regime_bullet_lines(assembly: S6Assembly) -> list[str]:
    lines: list[str] = []
    for row in _source_regime_rows(assembly):
        lines.append(
            f"- {source_display_name(row['source_db'])}: median {row['median_length_nt']} nt; "
            f"{row['n_distinct_cores']} distinct cores; "
            f"{row['pct_shorter_regime']}% shorter-regime / "
            f"{row['pct_longer_regime']}% longer-regime."
        )
    return lines


def fig01_spec(assembly: S6Assembly) -> dict[str, Any]:
    top = assembly.target_rows[:TOP_N_TARGETS]
    names = [display_target_name(row["canonical_target_name"]) for row in reversed(top)]
    identities = [int(row["n_scientific_identities"]) for row in reversed(top)]
    clusters = [int(row["n_clusters"]) for row in reversed(top)]
    annotations: list[dict[str, Any]] = []
    n_annotate = min(FIG01_N_ANNOTATE, len(top))
    for rank, row in enumerate(top[:n_annotate]):
        n_id = int(row["n_scientific_identities"])
        n_cl = int(row["n_clusters"])
        text = (
            f"{n_id} identities / {n_cl} clusters"
            if rank == 0
            else f"{n_id} / {n_cl}"
        )
        annotations.append(
            {
                "y_index": len(top) - 1 - rank,
                "x": max(n_id, n_cl),
                "text": text,
                "target": row["canonical_target_name"],
                "n_identities": n_id,
                "n_clusters": n_cl,
            }
        )
    return {
        "filename": "fig01_top30_targets.png",
        "title": "Target representation and independent sequence diversity",
        "xlabel": "Count",
        "bar_label": "curated aptamer–target identities",
        "dot_label": "independent sequence clusters",
        "names": names,
        "identities": identities,
        "clusters": clusters,
        "annotations": annotations,
    }


def fig02_spec(assembly: S6Assembly) -> dict[str, Any]:
    return {
        "filename": "fig02_target_family.png",
        "title": "Target-family annotation coverage",
        "ylabel": "Curated aptamer–target identities",
        "labels": [family_display_name(row["target_family"]) for row in assembly.family_rows],
        "counts": [int(row["n_scientific_identities"]) for row in assembly.family_rows],
        "raw_families": [row["target_family"] for row in assembly.family_rows],
    }


def fig03_spec(assembly: S6Assembly) -> dict[str, Any]:
    sources = donor_facet_sources(assembly)
    all_lengths = list(assembly.core_lengths)
    for values in assembly.core_lengths_by_source.values():
        all_lengths.extend(values)
    bins = length_histogram_bins(all_lengths or assembly.core_lengths)
    return {
        "filename": "fig03_sequence_core_length.png",
        "title": "Binding-sequence length and source-specific shapes",
        "overall_xlabel": "Length (nt)",
        "overall_ylabel": "Distinct sequence cores",
        "facet_ylabel": "Within-source density",
        "bins": bins,
        "x_range": (bins[0], bins[-1]),
        "overall_lengths": list(assembly.core_lengths),
        "sources": sources,
        "source_labels": [source_display_name(src) for src in sources],
        "source_lengths": {
            src: list(assembly.core_lengths_by_source.get(src, [])) for src in sources
        },
        "source_n": {
            src: len(assembly.core_lengths_by_source.get(src, [])) for src in sources
        },
        "n_facet_slots": int(math.ceil(max(len(sources), 1) / 4.0) * 4),
    }


def fig04_spec(assembly: S6Assembly) -> dict[str, Any]:
    core = list(assembly.identity_core_lengths)
    full = list(assembly.full_lengths)
    bins = length_histogram_bins([*core, *full])
    cmp_ = assembly.core_full_comparison
    return {
        "filename": "fig04_sequence_full_length.png",
        "title": "Binding-sequence versus reported-construct length",
        "xlabel": "Length (nt)",
        "ylabel": "Curated aptamer–target identities",
        "core_label": "binding sequence (core)",
        "full_label": "reported/full construct",
        "bins": bins,
        "x_range": (bins[0], bins[-1]),
        "core_lengths": core,
        "full_lengths": full,
        "n_identities": int(cmp_.get("n_identities", len(core))),
        "n_same_length": int(cmp_.get("n_same_length", 0)),
        "pct_same_length": float(cmp_.get("pct_same_length", 0.0)),
        "median_core_nt": float(cmp_.get("median_core_nt", 0.0)),
        "median_full_nt": float(cmp_.get("median_full_nt", 0.0)),
        "median_full_minus_core_nt": float(cmp_.get("median_full_minus_core_nt", 0.0)),
    }


def fig05_spec(assembly: S6Assembly) -> dict[str, Any]:
    return {
        "filename": "fig05_gc_distribution.png",
        "title": "GC content of distinct binding-sequence cores",
        "xlabel": "GC content (fraction of G + C)",
        "ylabel": "Distinct sequence cores",
        "values": list(assembly.gc_values),
    }


def fig06_spec(assembly: S6Assembly) -> dict[str, Any]:
    dist = assembly.cluster_stats["core_size_distribution"]
    sizes = [int(size) for size in dist.keys()]
    counts = [int(dist[size]) for size in dist.keys()]
    annotations: list[dict[str, Any]] = []
    for size in sizes:
        if size not in {19, 89}:
            continue
        targets = cluster_targets_for_core_size(assembly, size)
        if targets:
            annotations.append(
                {
                    "size": size,
                    "x_index": sizes.index(size),
                    "count": int(dist[size]),
                    "targets": targets,
                    "label": f"size {size}: {_join_and(targets)}",
                }
            )
    return {
        "filename": "fig06_cluster_size.png",
        "title": "Related-sequence cluster sizes",
        "xlabel": "Distinct sequences per related-sequence cluster",
        "ylabel": "Number of clusters",
        "yscale": "log",
        "categories": sizes,
        "counts": counts,
        "n_clusters": int(sum(counts)),
        "annotations": annotations,
        "singleton_fraction": float(assembly.cluster_stats["singleton_fraction"]),
    }


def fig07_spec(assembly: S6Assembly) -> dict[str, Any]:
    by_level = {row["evidence_level"]: int(row["n_scientific_identities"]) for row in assembly.evidence_rows}
    labels: list[str] = []
    counts: list[int] = []
    levels: list[str] = []
    for level in PRIMARY_EVIDENCE_LEVELS:
        if level not in by_level:
            continue
        levels.append(level)
        labels.append(EVIDENCE_DISPLAY.get(level, level))
        counts.append(int(by_level[level]))
    n_e1 = int(by_level.get("E1", 0))
    n_e5 = int(by_level.get("E5", assembly.evidence.get("n_e5", 0)))
    return {
        "filename": "fig07_evidence_level.png",
        "title": "Experimental evidence in the retained corpus",
        "ylabel": "Curated aptamer–target identities",
        "levels": levels,
        "labels": labels,
        "counts": counts,
        "n_e1": n_e1,
        "n_e5": n_e5,
        "include_e1_bar": n_e1 > 0,
        "include_e5_bar": False,
        "e5_note": E5_PARKED_NOTE,
        "n_e2": int(assembly.evidence.get("n_e2", by_level.get("E2", 0))),
        "n_e3": int(assembly.evidence.get("n_e3", by_level.get("E3", 0))),
        "n_e4": int(assembly.evidence.get("n_e4", by_level.get("E4", 0))),
    }


def fig08_spec(assembly: S6Assembly) -> dict[str, Any]:
    donor_rows = [row for row in assembly.source_rows if int(row["n_identities_donor"]) > 0]
    return {
        "filename": "fig08_source_contribution.png",
        "title": "Primary source after exact deduplication",
        "ylabel": "Curated aptamer–target identities",
        "xlabel": "Primary metadata donor",
        "labels": [source_display_name(row["source_db"]) for row in donor_rows],
        "raw_sources": [row["source_db"] for row in donor_rows],
        "counts": [int(row["n_identities_donor"]) for row in donor_rows],
    }


def fig09_spec(assembly: S6Assembly) -> dict[str, Any]:
    n_id = int(assembly.headline["n_scientific_identities"])
    fractions = [float(row["max_target_fraction"]) for row in assembly.cap_rows]
    tick_labels = [f"{int(round(frac * 100))}%" for frac in fractions]
    ideal = [int(row["idealised_recordwise_capped_corpus_size"]) for row in assembly.cap_rows]
    conservative = [
        int(row["cluster_union_upper_bound_remaining_identities"]) for row in assembly.cap_rows
    ]
    targets_above = [int(row["n_targets_above_threshold"]) for row in assembly.cap_rows]
    touching = [
        int(row["n_clusters_touching_overrepresented_targets"]) for row in assembly.cap_rows
    ]
    ngf = _target_row(assembly, "NGF")
    ngf_clusters = int(ngf["n_clusters"]) if ngf else 0
    names_by_fraction: dict[str, list[str]] = {}
    for row in assembly.cap_target_rows:
        names_by_fraction.setdefault(row["max_target_fraction"], []).append(
            row["canonical_target_name"]
        )
    return {
        "filename": "fig09_candidate_target_cap.png",
        "title": "How the target-cap choice affects retained corpus size",
        "xlabel": "Candidate maximum share for any one target",
        "ylabel": "Curated aptamer–target identities",
        "fractions": fractions,
        "tick_labels": tick_labels,
        "ideal": ideal,
        "conservative": conservative,
        "current_corpus": n_id,
        "current_label": f"current corpus = {_comma(n_id)} identities",
        "ideal_label": "idealised record-wise comparison",
        "conservative_label": "remove-all-touching-clusters comparison",
        "band_label": "illustrated comparison range (not every possible S7 rule)",
        "targets_above": targets_above,
        "clusters_touching": touching,
        "ngf_clusters": ngf_clusters,
        "names_by_fraction": names_by_fraction,
        "only_ngf_from_3pct": bool(
            all(
                names_by_fraction.get(row["max_target_fraction"], []) == ["NGF"]
                for row in assembly.cap_rows
                if float(row["max_target_fraction"]) >= 0.03 - 1e-12
            )
            and ngf_clusters > 0
            and all(
                int(row["n_clusters_touching_overrepresented_targets"]) == ngf_clusters
                for row in assembly.cap_rows
                if float(row["max_target_fraction"]) >= 0.03 - 1e-12
            )
        ),
    }


def fig10_spec(assembly: S6Assembly) -> dict[str, Any]:
    items = list(assembly.source_stats["corroboration_count_distribution"].items())
    return {
        "filename": "fig10_corroboration.png",
        "title": "Independent source support per aptamer–target identity",
        "xlabel": "Number of source databases",
        "ylabel": "Curated aptamer–target identities",
        "labels": [str(key) for key, _ in items],
        "counts": [int(value) for _, value in items],
    }


def build_figure_captions(assembly: S6Assembly) -> list[dict[str, str]]:
    h = assembly.headline
    n_id = int(h["n_scientific_identities"])
    ngf = _target_row(assembly, "NGF")
    unknown = _family_row(assembly, "unknown")
    unknown_n = int(unknown["n_scientific_identities"]) if unknown else 0
    unknown_pct = _pct(unknown_n, n_id, 1)
    bimo = assembly.bimodality
    means = [float(v) for v in bimo.get("component_means", [])]
    mean_short = fmt_float(means[0], 1) if len(means) > 1 else ""
    mean_long = fmt_float(means[1], 1) if len(means) > 1 else ""
    spec04 = fig04_spec(assembly)
    spec06 = fig06_spec(assembly)
    spec07 = fig07_spec(assembly)
    spec09 = fig09_spec(assembly)
    e2_pct = _pct(spec07["n_e2"], n_id, 1)
    n_corr_gt1 = int(assembly.source_stats.get("n_identities_corroborated_gt1", 0))
    ngf_id = int(ngf["n_scientific_identities"]) if ngf else 0
    ngf_cl = int(ngf["n_clusters"]) if ngf else 0
    fig01 = (
        "Bars show the number of curated aptamer–target identities and dots show "
        "the number of leakage-safe sequence clusters. A large gap means that many "
        "records belong to closely related sequence families rather than providing "
        "independent sequence diversity."
    )
    if ngf:
        fig01 += (
            f" NGF is the clearest example: {ngf_id} identities reduce to only "
            f"{ngf_cl} clusters. This is why the target-cap decision should operate "
            "on whole clusters rather than treating all records as independent."
        )
    else:
        fig01 += (
            " This is why the target-cap decision should operate on whole clusters "
            "rather than treating all records as independent."
        )
    fig03 = (
        f"The top panel is the overall length distribution of distinct binding-sequence "
        f"cores and shows two regimes, near {mean_short} and {mean_long} nt. The lower "
        "panels use the same bins and x-range for each donor source, plotted as "
        "within-source densities so shapes can be compared despite different source "
        f"sizes. {_regime_pattern_sentence(assembly)} This is a modelling caveat for "
        "empirical length priors and null/reference distributions, not a reason to "
        "remove either mode."
    )
    same_pct = f"{100.0 * spec04['pct_same_length']:.1f}%"
    fig04 = (
        "Binding-sequence (core) and reported/full-construct lengths are shown on the "
        "same bins so construct context can be compared directly. Median core length is "
        f"{fmt_float(spec04['median_core_nt'], 1)} nt; median full length is "
        f"{fmt_float(spec04['median_full_nt'], 1)} nt; {same_pct} of identities have "
        "the same core and full length "
        f"(median difference {fmt_float(spec04['median_full_minus_core_nt'], 1)} nt). "
        "Downstream modelling and reference distributions use the core sequence so "
        "flanking construct sequence does not inflate length."
    )
    if spec04["pct_same_length"] >= 0.90:
        fig04 += " In this corpus the two length measures are nearly identical for most identities."
    fig06 = (
        "Most leakage-safe groups contain only one distinct sequence, but a small number "
        "contain large related families."
    )
    has_89 = 89 in spec06["categories"]
    has_19 = 19 in spec06["categories"]
    targets_89 = cluster_targets_for_core_size(assembly, 89) if has_89 else []
    targets_19 = cluster_targets_for_core_size(assembly, 19) if has_19 else []
    if has_89 and has_19 and targets_89 == ["NGF"] and targets_19 == ["NGF"]:
        fig06 += (
            " The two largest groups contain 89 and 19 sequences and both target NGF. "
            "Because final balancing and dataset splitting operate on whole clusters, "
            "these large families cannot be divided across datasets and therefore "
            "constrain the exact effect of a target cap."
        )
    else:
        fig06 += (
            f" Because final balancing and dataset splitting operate on whole clusters, "
            f"large families cannot be divided across datasets and therefore constrain "
            f"the exact effect of a target cap. Singleton clusters are "
            f"{100.0 * spec06['singleton_fraction']:.0f}% of {spec06['n_clusters']} clusters."
        )
    n_above_2 = 0
    if spec09["fractions"]:
        n_above_2 = int(spec09["targets_above"][0]) if spec09["targets_above"] else 0
    fig09 = (
        "The blue line is an idealised calculation in which individual identities could "
        "be removed exactly to the target threshold; the red line shows the much more "
        "conservative result of removing every cluster that touches an overrepresented "
        "target. The real S7 implementation must retain whole leakage-safe clusters, so "
        "the final corpus size depends on the cluster-selection rule requested in C3-05. "
        "Neither line is the final predicted corpus size."
    )
    if spec09["only_ngf_from_3pct"] and spec09["ngf_clusters"]:
        fig09 += (
            f" From 3% to 10%, NGF is the only target above threshold, which is why the "
            f"remove-all-touching-clusters comparison remains flat: it removes the same "
            f"{spec09['ngf_clusters']} NGF clusters under each of those candidate caps. "
            f"At 2%, {n_above_2} targets exceed the nominal threshold."
        )
    captions = [
        {
            "id": "1",
            "filename": "fig01_top30_targets.png",
            "title": "Target representation and independent sequence diversity",
            "caption": fig01,
        },
        {
            "id": "2",
            "filename": "fig02_target_family.png",
            "title": "Target-family annotation coverage",
            "caption": (
                f"Target family is unresolved for {unknown_pct} of the corpus. Because "
                "the planned FT/REF/EVAL split was intended to stratify by target family, "
                "this missing annotation substantially limits how informative family-based "
                "stratification can be without a further annotation step or an alternative "
                "split strategy."
            ),
        },
        {
            "id": "3",
            "filename": "fig03_sequence_core_length.png",
            "title": "Binding-sequence length and source-specific shapes",
            "caption": fig03,
        },
        {
            "id": "4",
            "filename": "fig04_sequence_full_length.png",
            "title": "Binding-sequence versus reported-construct length",
            "caption": fig04,
        },
        {
            "id": "5",
            "filename": "fig05_gc_distribution.png",
            "title": "GC content of distinct binding-sequence cores",
            "caption": (
                "GC content is shown for distinct binding-sequence cores so a sequence "
                "associated with several targets is counted once. These empirical "
                "composition statistics will later inform the matched/null reference used "
                "when assessing generated sequences."
            ),
        },
        {
            "id": "6",
            "filename": "fig06_cluster_size.png",
            "title": "Related-sequence cluster sizes",
            "caption": fig06,
        },
        {
            "id": "7",
            "filename": "fig07_evidence_level.png",
            "title": "Experimental evidence in the retained corpus",
            "caption": (
                f"{e2_pct} of the retained corpus has quantitative affinity evidence (E2). "
                "Qualitative binding (E3) and selection/enrichment (E4) make up the remainder. "
                f"{E5_PARKED_NOTE}"
            ),
        },
        {
            "id": "8",
            "filename": "fig08_source_contribution.png",
            "title": "Primary source after exact deduplication",
            "caption": (
                "When the same sequence–target relationship appears in several databases, "
                "one source supplies the canonical scalar metadata while all contributing-source "
                "provenance is retained. These bars therefore show the primary metadata donor "
                "after deduplication, not the raw number of records originally downloaded from "
                "each database."
            ),
        },
        {
            "id": "9",
            "filename": "fig09_candidate_target_cap.png",
            "title": "How the target-cap choice affects retained corpus size",
            "caption": fig09,
        },
        {
            "id": "10",
            "filename": "fig10_corroboration.png",
            "title": "Independent source support per aptamer–target identity",
            "caption": (
                "Most identities are reported in only one contributing database; "
                f"{_comma(n_corr_gt1)} are independently represented in more than one source. "
                "Multiple-source corroboration preserves provenance but does not automatically "
                "upgrade the experimental evidence level."
            ),
        },
    ]
    for item in captions:
        assert_no_sequence_leak(item["caption"], label=f"figure {item['id']} caption")
        assert_no_sequence_leak(item["title"], label=f"figure {item['id']} title")
    return captions


def build_figure_pack_supervisor(assembly: S6Assembly) -> str:
    lines = [
        "# Supervisor figure pack",
        "",
        "Sequence-free consultation figures for CHECKPOINT-3. These figures accompany",
        "the supervisor briefing. They do not select a cap, balance the corpus, or",
        "start S7.",
        "",
    ]
    for item in build_figure_captions(assembly):
        lines.extend(
            [
                f"## Figure {item['id']} — {item['title']}",
                "",
                f"![Figure {item['id']}](figures/{item['filename']})",
                "",
                f"**Figure {item['id']} — {item['title']}.** {item['caption']}",
                "",
            ]
        )
    text = "\n".join(lines).rstrip() + "\n"
    assert_no_sequence_leak(text, label="figure_pack_supervisor.md")
    return text


def _source_regime_paragraph(assembly: S6Assembly) -> list[str]:
    bimo = assembly.bimodality
    means = [float(v) for v in bimo.get("component_means", [])]
    mean_short = fmt_float(means[0], 1) if len(means) > 1 else ""
    mean_long = fmt_float(means[1], 1) if len(means) > 1 else ""
    lines = [
        "The two length regimes are also associated with data source rather than being",
        "uniformly represented across databases. This suggests the apparent bimodality",
        "may partly reflect source/protocol differences — such as construct design or",
        "trimming conventions — as well as biological aptamer length. This matters when",
        "defining empirical length priors or null/reference distributions: a single pooled",
        "length distribution may inadvertently encode source-specific curation practices.",
        "",
        "Observed association (not a proven protocol cause): each distinct core is assigned",
        f"to the shorter (~{mean_short} nt) or longer (~{mean_long} nt) two-component GMM",
        "regime by maximum posterior probability. Length distributions differ strongly by",
        "source; this is consistent with source-associated experimental designs, construct",
        "definitions, or trimming conventions, but does not prove that those practices",
        "caused the modes.",
        "",
        _regime_pattern_sentence(assembly),
        "",
        *source_regime_bullet_lines(assembly),
        "",
        "A later modelling-stage decision can determine whether reference/null",
        "distributions need source or length-regime stratification. This is a modelling",
        "caveat, not a new CHECKPOINT-3 decision.",
        "",
    ]
    return lines


def build_corpus_profile_report(
    assembly: S6Assembly,
    *,
    s4_hashes: Mapping[str, str] | None = None,
    s5a_hashes: Mapping[str, str] | None = None,
    s5_final_hashes: Mapping[str, str] | None = None,
) -> str:
    h = assembly.headline
    n_id = int(h["n_scientific_identities"])
    n_core = int(h["n_distinct_sequence_core"])
    n_cl = int(h["n_final_clusters"])
    n_tg = int(h["n_canonical_targets"])
    ev = assembly.evidence
    src = assembly.source_stats
    uni = assembly.uniprot
    poly = assembly.polyspecificity
    cl = assembly.cluster_stats
    lic = assembly.licensing
    chem = assembly.chemistry
    aff = assembly.affinity
    length_out = assembly.length_outliers
    sparse = assembly.sparse_counts
    div = assembly.diversity
    bimo = assembly.bimodality
    ngf = _target_row(assembly, "NGF")
    unknown = _family_row(assembly, "unknown")
    unknown_n = int(unknown["n_scientific_identities"]) if unknown else 0
    unknown_targets = int(unknown["n_canonical_targets"]) if unknown else 0
    enzyme = _family_row(assembly, "enzyme")
    enzyme_n = int(enzyme["n_scientific_identities"]) if enzyme else int(h["n_enzyme_identities"])
    overall_core = next(
        row
        for row in assembly.length_rows
        if row["sequence_field"] == "sequence_core" and row["stratum_kind"] == "overall_identities"
    )
    overall_full = next(
        row
        for row in assembly.length_rows
        if row["sequence_field"] == "sequence_full" and row["stratum_kind"] == "overall_identities"
    )
    distinct_comp = next(
        row
        for row in assembly.composition_rows
        if row["weighting"] == "distinct_sequence_core" and row["stratum_kind"] == "overall"
    )
    identity_comp = next(
        row
        for row in assembly.composition_rows
        if row["weighting"] == "identity_weighted" and row["stratum_kind"] == "overall"
    )
    cmp_ = assembly.core_full_comparison
    ngf_id = int(ngf["n_scientific_identities"]) if ngf else int(h["largest_target_identities"])
    ngf_share = (ngf_id / n_id) if n_id else 0.0
    ngf_name = ngf["canonical_target_name"] if ngf else str(h["largest_target_name"])
    trigger = "not met" if not h["emergency_trigger_met"] else "MET"
    e2_pct = _pct(ev["n_e2"], n_id)
    e3_pct = _pct(ev["n_e3"], n_id)
    e4_pct = _pct(ev["n_e4"], n_id)
    top5 = assembly.target_rows[:5]
    captions = build_figure_captions(assembly)
    hash_lines: list[str] = []
    for label, payload in (
        ("S4 freeze", s4_hashes),
        ("S5A freeze", s5a_hashes),
        ("Final S5 freeze", s5_final_hashes),
    ):
        if not payload:
            continue
        hash_lines.append(f"### {label}")
        hash_lines.append("")
        for name, digest in payload.items():
            hash_lines.append(f"- `{name}`: `{digest}`")
        hash_lines.append("")

    donor_phrase = ", ".join(
        f"{source_display_name(name)} {count}" for name, count in src["donor_counts"].items() if int(count) > 0
    )
    means = [float(v) for v in bimo.get("component_means", [])]
    weights = [float(v) for v in bimo.get("component_weights", [])]
    cap_interp = {
        "0.02": "Broadest intervention; affects five targets." if n_id == 1281 else "Broadest listed intervention.",
        "0.03": "Primarily reduces NGF." if ngf else "Affects the largest target.",
        "0.05": "Current configuration default; not preselected.",
        "0.10": "Minimal intervention; NGF still near one tenth of the corpus."
        if ngf and n_id == 1281
        else "Minimal listed intervention.",
    }

    lines: list[str] = [
        "# Supervisor briefing: curated RNA aptamer corpus — decisions before final split",
        "",
        "## What we need from you",
        "",
        "The corpus has been curated and grouped to prevent closely related sequences",
        "from being separated across future datasets. It is ready for consultation, but",
        "it is **not yet balanced or split**. Please advise on the five choices below so",
        "we can freeze the final training, reference, and evaluation datasets (FT/REF/EVAL)",
        "and keep the fine-tuning timeline on track. No exact response deadline is assumed,",
        "but timely responses are needed to avoid delaying that next step.",
        "",
        *_md_table(
            ["Decision", "Question for supervisors", "Current context"],
            [
                [
                    "C3-01",
                    "What maximum share of the final corpus may any one target occupy: 2%, 3%, 5%, 10%, or another value?",
                    (
                        f"{ngf_name} is {ngf_id}/{_comma(n_id)} identities "
                        f"({100.0 * ngf_share:.2f}%); the current configuration's 5% value "
                        "is only a placeholder, not a decision."
                    ),
                ],
                [
                    "C3-02",
                    "Should there be balancing beyond the per-target cap?",
                    (
                        f"The planned split uses target family as a stratification variable, but "
                        f"{_comma(unknown_n)}/{_comma(n_id)} identities ({_pct(unknown_n, n_id, 1)}) "
                        "have family unknown; this severely limits meaningful family-based "
                        "balancing or stratification as written."
                    ),
                ],
                [
                    "C3-03",
                    "Keep the present minimum evidence standard, or include lower-confidence E5 records?",
                    (
                        f"The current corpus is E2–E4 only and already has {_comma(n_cl)} sequence "
                        "clusters, above the plan's ~500-cluster contingency trigger."
                    ),
                ],
                [
                    "C3-04",
                    "Keep the protein-only corpus, or include the separately parked non-protein records?",
                    "The present corpus is protein-only; adding non-proteins would change the biological scope and transfer framing.",
                ],
                [
                    "C3-05",
                    "What deterministic rule should select **whole sequence clusters** when enforcing C3-01?",
                    "The plan requires cluster-level capping but does not yet specify the denominator, ranking/tie-breaks, or treatment of clusters that touch multiple targets.",
                ],
            ],
        ),
        "",
        "**Standing note:** this report presents evidence and trade-offs; it does not recommend",
        "or silently select any option. Once the five choices are recorded, the remaining work",
        "is to apply the approved cap, assign whole clusters to FT/REF/EVAL, and create the",
        "fine-tuning train/validation split.",
        "",
        "## Executive summary",
        "",
        f"The curated primary RNA/protein corpus contains **{_comma(n_id)} curated aptamer–target identities**,",
        f"representing **{_comma(n_core)} distinct sequence cores**, in **{_comma(n_cl)} leakage-safe sequence clusters**,",
        f"across **{_comma(n_tg)} canonical protein targets**. Exact duplicate observations have already had their",
        "provenance merged; no balancing, target capping, partitioning, or train/validation split has yet occurred.",
        "",
        f"The corpus is viable at its current size: {_comma(n_cl)} clusters is above the plan's `<500`-cluster",
        f"trigger for considering broader inclusion criteria. The principal policy issue is target imbalance.",
        f"{ngf_name} contributes {ngf_id} identities ({100.0 * ngf_share:.2f}%); all other targets are much smaller.",
        f"The corpus also has a major limitation for the planned split: target-family labels are unresolved",
        f"(unknown) for **{_pct(unknown_n, n_id)}** of identities. Thus, a split nominally stratified by target",
        "family would be dominated by one unknown stratum, rather than providing broad, biologically informative",
        "family coverage.",
        "",
        f"Evidence is predominantly strong or directly measured: quantitative affinity (E2) {ev['n_e2']} ({e2_pct}),",
        f"qualitative binding (E3) {ev['n_e3']} ({e3_pct}), and selection/enrichment (E4) {ev['n_e4']} ({e4_pct});",
        "no E5 records are in the primary corpus. Sequence lengths show two substantial regimes",
        f"centred near {fmt_float(means[0], 0) if means else 'n/a'} and {fmt_float(means[1], 0) if len(means) > 1 else 'n/a'} nucleotides;",
        "this is a modelling/reference-distribution consideration, not a reason to remove records.",
        f"Licensing metadata are mostly unresolved ({_pct(lic['n_unknown'], n_id)}) with {_pct(lic['n_restricted'], n_id)} restricted;",
        "this is documented provenance, not a legal conclusion or an exclusion rule.",
        "",
        "## A short glossary",
        "",
        "- **Curated aptamer–target identity (scientific identity):** one curated relationship between one aptamer's standardised binding sequence (sequence core) and one canonical protein target.",
        f"  The report's main denominator is {_comma(n_id)} such relationships. The principal grain is one S5 scientific identity = one exact `(sequence_core, canonical_target_name)` relationship.",
        "- **Sequence core / full sequence:** the core is the standardised sequence used to compare and cluster aptamers. The full sequence retains construct context such as flanking regions where available.",
        "- **Sequence cluster / related-sequence cluster:** a group of similar sequence cores. Clusters are kept intact in later splits so related sequences cannot leak between FT, REF, and EVAL. The final grouping combines 90% sequence-similarity clustering with trusted ENA family links; not every pair within a final cluster must itself be 90% identical.",
        "- **Leakage-safe:** closely related sequences are assigned together, rather than being allowed to appear in both model development and evaluation datasets.",
        "- **Evidence level:** E2 means a reported quantitative affinity measurement (for example Kd, Ka, or IC50) against a named protein; E3 means a named qualitative binding assay without a quantitative constant; E4 means a published selection/enrichment result without an independent binding assay; E5 means a database/deposit target annotation without a traceable assay. The current inclusion threshold is E4 or stronger.",
        "- **Corroboration:** independent source databases supporting the same aptamer–target identity. It preserves provenance but does not upgrade the evidence level.",
        "- **FT / REF / EVAL:** future fine-tuning, reference, and evaluation partitions. They have not yet been assigned.",
        "",
        "## Corpus at a glance",
        "",
        *_md_table(
            ["Measure", "Result", "Plain-language meaning"],
            [
                ["Curated aptamer–target identities", _comma(n_id), "Curated sequence–target relationships available before balancing."],
                ["Distinct sequence cores", _comma(n_core), "Some cores bind more than one retained target."],
                ["Leakage-safe clusters", _comma(n_cl), "The independent units available for future partitioning."],
                ["Canonical protein targets", _comma(n_tg), "Nominal target breadth before accounting for imbalance."],
                [
                    "Singleton clusters",
                    f"{cl['n_singleton_clusters']}/{n_cl} ({100.0 * cl['singleton_fraction']:.1f}%)",
                    "Most clusters contain a single distinct core.",
                ],
                [
                    "Largest target",
                    f"{ngf_name}: {ngf_id} ({100.0 * ngf_share:.2f}%)",
                    "A target cap is needed if this concentration is undesirable.",
                ],
                [
                    "Quantitative-affinity evidence",
                    f"{ev['n_e2']}/{_comma(n_id)} ({e2_pct})",
                    "Most identities have a reported quantitative measurement.",
                ],
                [
                    "Target family unknown",
                    f"{_comma(unknown_n)}/{_comma(n_id)} ({_pct(unknown_n, n_id)})",
                    "Family-stratified splitting is currently weak.",
                ],
                [
                    "UniProt-resolved targets",
                    f"{uni['n_targets_with_uniprot']}/{n_tg} ({100.0 * uni['target_weighted_rate']:.2f}%)",
                    "Target annotation remains incomplete.",
                ],
            ],
        ),
        "",
        "## What the target distribution means",
        "",
        "The target counts are moderately concentrated rather than evenly spread:",
        "",
        f"- **Gini = {fmt_float(div['identity_count_gini'])}.** On a scale where 0 would mean every target has the same number of identities and 1 would mean extreme concentration, this indicates substantial imbalance.",
        f"- **Shannon entropy = {fmt_float(div['identity_count_shannon']['shannon_nats'])} nats; normalised Shannon = {fmt_float(div['identity_count_shannon']['shannon_normalised'])}.** These summarise diversity while giving less weight to rare targets than a simple target count.",
        f"- **Effective number of targets = {fmt_float(div['identity_count_shannon']['n_effective'], 2)}.** Put plainly, the observed distribution carries about as much target diversity as **{fmt_float(div['identity_count_shannon']['n_effective'], 0)} equally represented targets**, rather than {_comma(n_tg)} equally represented targets.",
        "",
    ]
    if len(top5) >= 2:
        rest = ", ".join(
            f"{row['canonical_target_name']} ({row['n_scientific_identities']}; {row['pct_identities']}%)"
            for row in top5[1:]
        )
        lines.append(
            f"{ngf_name} is the largest target at present; it is {100.0 * ngf_share:.2f}% of identities. "
            f"The next-largest targets are {rest}. There are {sparse['n_targets_one_identity']} targets "
            f"represented by only one identity and {sparse['n_targets_one_cluster']} represented by only one cluster."
        )
        lines.append("")
    lines.extend(
        [
            "### Target-family limitation for the planned split",
            "",
            f"The planned FT/REF/EVAL process stratifies by target family. However, {unknown_targets} of {n_tg} targets",
            f"and {_comma(unknown_n)} of {_comma(n_id)} identities have target family unknown. Known labels therefore",
            "cannot provide the intended biological coverage for most of the corpus without either accepting a dominant",
            "unknown stratum, enriching annotations in a bounded follow-up, or approving another explicit stratification",
            "approach. This is central to C3-02, not a minor metadata caveat.",
            "",
            *_md_table(
                ["Target family", "Identities", "Share"],
                [
                    [
                        family_display_name(row["target_family"]),
                        _comma(row["n_scientific_identities"]),
                        f"{row['pct_identities']}%",
                    ]
                    for row in assembly.family_rows
                ],
            ),
            "",
            "## C3-01: target-cap options",
            "",
            "These simulations are decision support only. They use the present identity denominator and show an",
            "idealised, record-wise result; the approved implementation must retain or remove **whole clusters**,",
            "so the final size will depend on C3-05.",
            "",
            *_md_table(
                [
                    "Maximum target share",
                    "Nominal threshold",
                    "Targets above threshold",
                    "Raw excess identities",
                    "Idealised retained size",
                    "Interpretation",
                ],
                [
                    [
                        f"{int(round(float(row['max_target_fraction']) * 100))}%",
                        row["nominal_identity_threshold"],
                        row["n_targets_above_threshold"],
                        row["raw_identity_excess"],
                        _comma(row["idealised_recordwise_capped_corpus_size"]),
                        cap_interp.get(row["max_target_fraction"], "Diagnostic comparison only."),
                    ]
                    for row in assembly.cap_rows
                ],
            ),
            "",
            "At each option, the overrepresented targets have enough identities in clusters that contain only that",
            "target to absorb the raw excess in principle. Removing every cluster that touches an overrepresented",
            "target would be much more conservative; those values illustrate a comparison range rather than a unique",
            "S7 output. Neither comparison is the final predicted corpus size.",
            "",
            "## Decisions requested at CHECKPOINT-3",
            "",
            "Human choice is blank. S6 does not recommend a final approved option.",
            "",
            "### C3-02 to C3-05: decision record",
            "",
            "**C3-02 — further balancing.** Decide among: no additional balancing; target-family balancing; or another documented scheme. The v1 plan defers family balancing beyond the target cap. No family-balancing simulation has been run, and the unresolved family share is the key constraint.",
            "",
            f"**C3-03 — evidence threshold.** Decide among: retain the E4 minimum; admit parked E5; or another documented threshold. Admitting E5 has not been simulated. The current corpus has E2 {ev['n_e2']}, E3 {ev['n_e3']}, E4 {ev['n_e4']}, E5 {ev['n_e5']}, and {_comma(n_cl)} clusters.",
            "",
            "**C3-04 — biological scope.** Decide among: retain the protein-only primary corpus; admit parked non-protein records; or another documented scope. Non-protein inclusion has not been simulated and would change the target-type mix.",
            "",
            "**C3-05 — cap-selection semantics.** Specify a deterministic cluster-level rule, including: whether the cap is calculated against the post-cap final denominator; floor/ceiling convention; how whole clusters are ranked and ties resolved; how multi-target clusters are handled; and whether collateral identities may be removed when a cluster is selected for an overrepresented target. Without this, S7 cannot produce a unique capped corpus size.",
            "",
            "## Evidence, sequence, and provenance considerations",
            "",
            "### Evidence standard (C3-03)",
            "",
            *_md_table(
                ["Evidence", "Identities", "Share", "Meaning"],
                [
                    ["Quantitative affinity (E2)", ev["n_e2"], e2_pct, "Quantitative affinity reported."],
                    ["Qualitative binding (E3)", ev["n_e3"], e3_pct, "Named qualitative binding assay."],
                    ["Selection / enrichment (E4)", ev["n_e4"], e4_pct, "Selection/enrichment evidence, no independent assay."],
                    ["Database/deposit-only (E5)", ev["n_e5"], _pct(ev["n_e5"], n_id), "Currently parked; not in this primary corpus."],
                ],
            ),
            "",
            f"The current corpus retains E2–E4 only. Since there are {_comma(n_cl)} clusters, the contingency threshold",
            f"for relaxing inclusion (`<500` clusters) is **{trigger}**. Admitting E5 would change the evidence mix and",
            "corpus composition; it has not been simulated or applied.",
            "",
            "### Sequence profile",
            "",
            f"Core lengths range from {overall_core['min']} to {overall_core['max']} nt (median {overall_core['median']}; mean {overall_core['mean']};",
            f"5th–95th percentile {overall_core['p05']}–{overall_core['p95']} nt). {length_out['n_identities_gt_100nt']} retained, upstream-reviewed",
            "identities exceed 100 nt. Distinct core lengths show material two-regime structure: the two-component model has",
            f"means of {fmt_float(means[0], 2) if means else 'n/a'} and {fmt_float(means[1], 2) if len(means) > 1 else 'n/a'} nt,",
            f"weights {fmt_float(weights[0], 3) if weights else 'n/a'} and {fmt_float(weights[1], 3) if len(weights) > 1 else 'n/a'},",
            f"and improves BIC by {fmt_float(bimo['delta_bic_1_minus_2'], 3)} over a one-component model. In plain terms, the corpus",
            "contains sizeable short- and longer-sequence populations; later modelling and reference distributions should",
            "reflect this rather than assume one typical length.",
            "",
            *_source_regime_paragraph(assembly),
            f"Distinct-core GC fraction has mean {distinct_comp['gc_mean']} (median {distinct_comp['gc_median']};",
            f"5th–95th percentile {distinct_comp['gc_p05']}–{distinct_comp['gc_p95']}). The stored alphabet is predominantly RNA,",
            "with a small amount of T retained as reported; this report does not reclassify chemistry.",
            "",
            "### Clustering and multi-target relationships",
            "",
            f"There are {cl['n_multi_sequence_clusters']} multi-sequence clusters, {cl['n_multi_target_clusters']} clusters that include more than one canonical target,",
            f"and {cl['n_multi_source_clusters']} clusters with more than one contributing source. Of {poly['n_shared_sequence_cores']} cores associated with multiple canonical targets,",
            f"{poly['n_multi_target_clusters_with_identical_shared_core']} create a cluster with an identical shared core and {poly['n_multi_target_clusters_near_sequence_only']} are multi-target only through near-sequence membership.",
            "These are retained relationships, not automatically claims of biological polyspecificity.",
            "",
        ]
    )
    largest = assembly.cluster_rows[:2]
    if len(largest) >= 2:
        lines.extend(
            [
                f"The largest cluster contains {largest[0]['n_distinct_sequence_core']} cores/{largest[0]['n_scientific_identities']} identities for {largest[0]['canonical_targets'].replace('|', ', ')};",
                f"the next contains {largest[1]['n_distinct_sequence_core']}, for {largest[1]['canonical_targets'].replace('|', ', ')}.",
                f"{cl['n_ena_must_link_union_clusters']} clusters were created or expanded by trusted ENA family must-links. This confirms why cap implementation must operate at cluster level and be explicit about multi-target clusters.",
                "",
            ]
        )
    lines.extend(
        [
            "### Sources, annotation, and redistribution",
            "",
            f"The primary-source distribution after exact deduplication is: {donor_phrase}.",
            "When the same sequence–target relationship appears in several databases, one source supplies the canonical",
            "scalar metadata while all contributing-source provenance is retained. A total of",
            f"{src['n_identities_corroborated_gt1']}/{_comma(n_id)} identities are supported by more than one source.",
            "",
            f"Redistribution metadata are unknown for {_comma(lic['n_unknown'])} identities ({_pct(lic['n_unknown'], n_id)}) and restricted for {lic['n_restricted']} ({_pct(lic['n_restricted'], n_id)});",
            "none are labelled permissive, and no restricted/unknown identity has independent permissive attestation. This is descriptive provenance only and is not a legal conclusion or a decision to exclude records.",
            "",
            "## Figure pack for the consultation",
            "",
            "Please circulate the figure pack with this briefing. Captions are written so the figures can be read",
            "without the technical appendix. The pack contains aggregate labels and counts, not sequences.",
            "",
        ]
    )
    for item in captions:
        lines.extend(
            [
                f"### Figure {item['id']} — {item['title']}",
                "",
                f"`{item['filename']}`",
                "",
                item["caption"],
                "",
            ]
        )
    lines.extend(
        [
            "## Next steps after decisions",
            "",
            "1. Record the five CHECKPOINT-3 choices, including a reproducible whole-cluster rule for C3-05.",
            "2. Apply the approved cap and any approved inclusion/balancing policy without splitting clusters.",
            "3. Verify the post-cap distribution against the approved final denominator.",
            "4. Assign whole clusters to FT, REF, and EVAL using the approved stratification policy; document the known target-family limitation or any approved alternative.",
            "5. Produce the final split corpus and then create the FT train/validation split.",
            "",
            "---",
            "",
            "# Technical appendix",
            "",
            "This appendix preserves audit and reproducibility context. It is not required for the supervisory decisions above.",
            "",
            "## A. Scope and data grain",
            "",
            "The final corpus was produced by canonical target normalisation, exact scientific deduplication, and leakage-safe clustering.",
            f"The main grain is one exact `(sequence_core, canonical_target_name)` relationship: {_comma(n_id)} curated aptamer–target identities,",
            f"{_comma(n_core)} distinct cores, and {_comma(n_cl)} final clusters. These are distinct from the 1,460 pre-dedup relationship/provenance",
            "observations and 1,429 source records. `scientific_identity_id` is unique at the S5 identity grain; source `record_id` is provenance and is not unique at that grain.",
            "",
            "The final cluster construction is frozen 90% corpus-wide MMseqs grouping unioned with trusted ENA positive family must-links.",
            "It must not be read as a statement that every pair in a final cluster is at least 90% identical.",
            f"There are {assembly.assertions['n_representatives']} scientific representatives, with none missing and none duplicated.",
            f"`partition` is blank for all {_comma(n_id)} identities.",
            "",
            "## B. Additional target and cluster diagnostics",
            "",
            f"Secondary target diagnostics: cluster-occupancy Gini {fmt_float(div['cluster_occupancy_gini'])}; cluster-majority Gini {fmt_float(div['cluster_majority_gini'])};",
            f"cluster-majority Shannon {fmt_float(div['cluster_majority_shannon']['shannon_nats'])} nats. Enzyme identities are {enzyme_n}/{_comma(n_id)} ({_pct(enzyme_n, n_id)}).",
            "No target has non-empty Pfam or InterPro annotation used for balancing.",
            "",
            "Final cluster core-count distribution: "
            + ", ".join(f"{size}={count}" for size, count in cl["core_size_distribution"].items())
            + ".",
            "",
            f"Clusters with ENA provenance: {cl['n_ena_provenance_clusters']}; clusters created/expanded by ENA union: {cl['n_ena_must_link_union_clusters']}.",
            "",
            "## C. Detailed sequence and metadata profile",
            "",
            f"Full-sequence lengths: n={overall_full['n']}; min {overall_full['min']}; p05 {overall_full['p05']}; p25 {overall_full['p25']}; median {overall_full['median']}; mean {overall_full['mean']}; p75 {overall_full['p75']}; p95 {overall_full['p95']}; max {overall_full['max']}.",
            f"Core lengths: n={overall_core['n']}; min {overall_core['min']}; p05 {overall_core['p05']}; p25 {overall_core['p25']}; median {overall_core['median']}; mean {overall_core['mean']}; p75 {overall_core['p75']}; p95 {overall_core['p95']}; max {overall_core['max']}.",
            f"Identity-grain core vs full: {cmp_.get('n_same_length', 0)}/{cmp_.get('n_identities', n_id)} identities have identical lengths "
            f"({100.0 * float(cmp_.get('pct_same_length', 0.0)):.1f}%); median full−core difference {fmt_float(float(cmp_.get('median_full_minus_core_nt', 0.0)), 1)} nt.",
            f"The full-sequence two-component diagnostic likewise reports `{bimo['full_construct_gmm']['conclusion']}` "
            f"(ΔBIC {fmt_float(bimo['full_construct_gmm']['delta_bic_1_minus_2'], 3)}).",
            "",
            f"Distinct-core composition: A {distinct_comp['frac_A']}, U {distinct_comp['frac_U']}, C {distinct_comp['frac_C']}, G {distinct_comp['frac_G']}, T {distinct_comp['frac_T']}, other {distinct_comp['frac_other']}.",
            f"Identity-weighted GC mean {identity_comp['gc_mean']}; median {identity_comp['gc_median']}.",
            "",
            "GMM source-regime assignment method: " + str(bimo.get("source_regime_method", "")),
            "",
            "chemistry: " + ", ".join(f"{k}={v}" for k, v in chem["chemistry"].items()),
            "",
            f"Canonical affinity is present for {aff['n_with_canonical_affinity']}/{_comma(n_id)} "
            f"({100.0 * aff['pct_with_canonical_affinity']:.2f}%). Measurements are not averaged across observations.",
            "",
            "## D. Source and evidence detail",
            "",
            *_md_table(
                ["Primary source", "Identities", "Contributing identities", "Unique identities", "Unique cores"],
                [
                    [
                        source_display_name(row["source_db"]),
                        row["n_identities_donor"],
                        row["n_identities_contributing"],
                        row["n_identities_unique_attestation"],
                        row["n_cores_unique_attestation"],
                    ]
                    for row in assembly.source_rows
                ],
            ),
            "",
            "Unspecified S7 cluster-selection items:",
            "",
        ]
    )
    lines.extend(f"- {item.replace('_', ' ')}" for item in S7_UNSPECIFIED_ITEMS)
    lines.extend(
        [
            "",
            "## E. Reproducibility freeze hashes",
            "",
            *hash_lines,
            "## F. Boundary of this report",
            "",
            "- S6 profile complete after this report is generated",
            "- CHECKPOINT-3 prepared, not decided or applied",
            "- no balancing",
            "- no target cap applied",
            "- no rows removed",
            "- no S7",
            "- no FT/REF/EVAL",
            "- no train/validation split",
            "- no S4/S5 science changed",
            "",
        ]
    )
    text = "\n".join(lines).rstrip() + "\n"
    assert_no_sequence_leak(text, label="corpus_profile_report.md")
    return text


def build_checkpoint3_summary(assembly: S6Assembly) -> str:
    h = assembly.headline
    n_id = int(h["n_scientific_identities"])
    lines = [
        "# CHECKPOINT-3 decision support",
        "",
        "Sequence-free supervisor package. Human decision fields are blank.",
        "S6 has not selected a cap, has not balanced, and has not started S7.",
        "",
        "## Corpus at review",
        "",
        f"- curated aptamer–target identities = {n_id}",
        f"- distinct sequence cores = {h['n_distinct_sequence_core']}",
        f"- final clusters = {h['n_final_clusters']}",
        f"- canonical targets = {h['n_canonical_targets']}",
        f"- target-family labels = {h['n_target_families']}",
        f"- largest target = {h['largest_target_name']} ({h['largest_target_identities']} identities)",
        f"- enzyme identity share = {100.0 * h['enzyme_identity_share']:.2f}%",
        f"- singleton-cluster fraction = {100.0 * h['singleton_cluster_fraction']:.1f}%",
        f"- `<500 clusters` trigger = {'met' if h['emergency_trigger_met'] else 'not met'}",
        "",
        "## Candidate cap (diagnostic, not executed)",
        "",
        "| fraction | threshold | targets above | excess | idealised record-wise size | union-removal remaining |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in assembly.cap_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["max_target_fraction"],
                    row["nominal_identity_threshold"],
                    row["n_targets_above_threshold"],
                    row["raw_identity_excess"],
                    row["idealised_recordwise_capped_corpus_size"],
                    row["cluster_union_upper_bound_remaining_identities"],
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Idealised record-wise size is not executable S7 output. Exact whole-cluster",
            "selection semantics are **not specified** in the current v1.4 plan/code.",
            "The two comparison series illustrate a range of consequences; they do not",
            "mathematically bound every possible S7 algorithm.",
            "",
            "## Decisions",
            "",
        ]
    )
    for row in assembly.checkpoint3_decisions:
        lines.extend(
            [
                f"### {row['decision_id']} — {row['title']}",
                "",
                row["question"],
                "",
                f"Options: {row['options'].replace('|', '; ')}",
                "",
                f"Human decision: _(blank)_",
                "",
            ]
        )
    text = "\n".join(lines).rstrip() + "\n"
    assert_no_sequence_leak(text, label="checkpoint3_summary.md")
    for row in assembly.checkpoint3_decisions:
        for field_name in HUMAN_CHECKPOINT_FIELDS:
            if row[field_name] != "":
                raise S6ProfileError("CHECKPOINT-3 human fields must be blank")
    return text


def _configure_matplotlib() -> Any:
    cache = Path(tempfile.gettempdir()) / "s6_mplconfig"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    matplotlib.rcParams.update(
        {
            "figure.dpi": 150,
            "savefig.dpi": 150,
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
            "figure.max_open_warning": 0,
            "axes.unicode_minus": False,
            "svg.hashsalt": "global_s6_profile",
        }
    )
    return plt


def _savefig(fig: Any, path: Path) -> None:
    fig.savefig(
        path,
        bbox_inches="tight",
        facecolor="white",
        metadata={"CreationDate": None, "Software": "global_s6_profile"},
    )
    try:
        from PIL import Image

        image = Image.open(path)
        image.save(path, format="PNG")
    except Exception:
        pass


def _plot_fig01(plt: Any, spec: Mapping[str, Any], path: Path) -> None:
    names = spec["names"]
    identities = spec["identities"]
    clusters = spec["clusters"]
    fig, ax = plt.subplots(figsize=(11.2, 9.2))
    y = list(range(len(names)))
    ax.barh(y, identities, color="#2c5f8a", height=0.72, label=spec["bar_label"], zorder=2)
    ax.scatter(
        clusters,
        y,
        s=64,
        color="#e39b00",
        edgecolors="#5a3a00",
        linewidths=0.8,
        zorder=3,
        label=spec["dot_label"],
    )
    ax.set_yticks(y, labels=names)
    ax.set_xlabel(spec["xlabel"])
    ax.set_title(spec["title"])
    xmax = max(identities) if identities else 1
    ax.set_xlim(0, xmax * 1.38)
    for item in spec["annotations"]:
        ax.text(
            item["x"] + xmax * 0.035,
            item["y_index"],
            item["text"],
            va="center",
            ha="left",
            fontsize=9,
            color="#1f3347",
            clip_on=False,
        )
    ax.legend(loc="lower right", frameon=True)
    ax.grid(axis="x", linestyle=":", alpha=0.4, zorder=0)
    fig.tight_layout()
    _savefig(fig, path)
    plt.close(fig)


def _plot_fig02(plt: Any, spec: Mapping[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    ax.bar(spec["labels"], spec["counts"], color="#3d7a5a")
    ax.set_ylabel(spec["ylabel"])
    ax.set_title(spec["title"])
    ax.tick_params(axis="x", rotation=28)
    for label in ax.get_xticklabels():
        label.set_ha("right")
    fig.tight_layout()
    _savefig(fig, path)
    plt.close(fig)


def _plot_fig03(plt: Any, spec: Mapping[str, Any], path: Path) -> None:
    sources = spec["sources"]
    n_cols = 4
    n_facet_rows = max(1, int(math.ceil(max(len(sources), 1) / n_cols)))
    fig = plt.figure(figsize=(12.2, 3.4 + 2.35 * n_facet_rows))
    gs = fig.add_gridspec(1 + n_facet_rows, n_cols, height_ratios=[1.25, *([1.0] * n_facet_rows)], hspace=0.55, wspace=0.28)
    ax_top = fig.add_subplot(gs[0, :])
    bins = spec["bins"]
    ax_top.hist(spec["overall_lengths"], bins=bins, color="#2c5f8a", edgecolor="white")
    ax_top.set_title("Overall binding-sequence length (distinct cores)")
    ax_top.set_xlabel(spec["overall_xlabel"])
    ax_top.set_ylabel(spec["overall_ylabel"])
    ax_top.set_xlim(*spec["x_range"])
    facet_axes: list[Any] = []
    for index in range(n_facet_rows * n_cols):
        row, col = divmod(index, n_cols)
        ax = fig.add_subplot(gs[1 + row, col])
        if index < len(sources):
            src = sources[index]
            values = spec["source_lengths"][src]
            ax.hist(values, bins=bins, density=True, color="#4d7ea8", edgecolor="white")
            ax.set_title(f"{spec['source_labels'][index]} (n={spec['source_n'][src]})", fontsize=11)
            facet_axes.append(ax)
        else:
            ax.axis("off")
            continue
        ax.set_xlim(*spec["x_range"])
        ax.set_xlabel("Length (nt)", fontsize=9)
        if col == 0:
            ax.set_ylabel(spec["facet_ylabel"], fontsize=9)
    if facet_axes:
        ymax = max(ax.get_ylim()[1] for ax in facet_axes)
        for ax in facet_axes:
            ax.set_ylim(0, ymax)
    fig.suptitle(spec["title"], y=0.995, fontsize=13)
    _savefig(fig, path)
    plt.close(fig)


def _plot_fig04(plt: Any, spec: Mapping[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.2, 5.0))
    bins = spec["bins"]
    ax.hist(
        spec["core_lengths"],
        bins=bins,
        histtype="step",
        linewidth=2.2,
        color="#2c5f8a",
        label=spec["core_label"],
    )
    ax.hist(
        spec["full_lengths"],
        bins=bins,
        histtype="step",
        linewidth=2.2,
        color="#8a3d3d",
        label=spec["full_label"],
    )
    ax.set_xlim(*spec["x_range"])
    ax.set_xlabel(spec["xlabel"])
    ax.set_ylabel(spec["ylabel"])
    ax.set_title(spec["title"])
    ax.legend(loc="upper right")
    note = (
        f"median core {fmt_float(spec['median_core_nt'], 1)} nt\n"
        f"median full {fmt_float(spec['median_full_nt'], 1)} nt\n"
        f"same length {100.0 * spec['pct_same_length']:.1f}%\n"
        f"median full − core {fmt_float(spec['median_full_minus_core_nt'], 1)} nt"
    )
    ax.text(
        0.98,
        0.70,
        note,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox={"facecolor": "white", "edgecolor": "#cccccc", "boxstyle": "round,pad=0.35"},
    )
    fig.tight_layout()
    _savefig(fig, path)
    plt.close(fig)


def _plot_fig05(plt: Any, spec: Mapping[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    ax.hist(spec["values"], bins=20, color="#1b7f7a", edgecolor="white")
    ax.set_title(spec["title"])
    ax.set_xlabel(spec["xlabel"])
    ax.set_ylabel(spec["ylabel"])
    fig.tight_layout()
    _savefig(fig, path)
    plt.close(fig)


def _plot_fig06(plt: Any, spec: Mapping[str, Any], path: Path) -> None:
    categories = spec["categories"]
    counts = spec["counts"]
    x = list(range(len(categories)))
    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    ax.bar(x, counts, color="#8a3d3d", zorder=2)
    ax.set_xticks(x, labels=[str(size) for size in categories])
    ax.set_yscale(spec["yscale"])
    ax.set_xlabel(spec["xlabel"])
    ax.set_ylabel(spec["ylabel"])
    ax.set_title(spec["title"])
    ymax = max(counts) if counts else 1
    ax.set_ylim(0.6, ymax * 3.0)
    for index, count in enumerate(counts):
        ax.text(index, count, str(count), ha="center", va="bottom", fontsize=9, zorder=3)
    if spec["annotations"]:
        note = "\n".join(item["label"] for item in spec["annotations"])
        ax.text(
            0.98,
            0.62,
            note,
            transform=ax.transAxes,
            ha="right",
            va="center",
            fontsize=9,
            bbox={"facecolor": "white", "edgecolor": "#cccccc", "boxstyle": "round,pad=0.35"},
        )
    ax.grid(axis="y", linestyle=":", alpha=0.4, which="both", zorder=0)
    fig.tight_layout()
    _savefig(fig, path)
    plt.close(fig)


def _plot_fig07(plt: Any, spec: Mapping[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    ax.bar(spec["labels"], spec["counts"], color="#c47b2c")
    ax.set_ylabel(spec["ylabel"])
    ax.set_title(spec["title"])
    ymax = max(spec["counts"]) if spec["counts"] else 1
    ax.set_ylim(0, ymax * 1.22)
    ax.text(
        0.99,
        0.97,
        textwrap.fill(spec["e5_note"], width=42),
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8.5,
        bbox={"facecolor": "white", "edgecolor": "#dddddd", "boxstyle": "round,pad=0.3"},
    )
    fig.tight_layout()
    _savefig(fig, path)
    plt.close(fig)


def _plot_fig08(plt: Any, spec: Mapping[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    ax.bar(spec["labels"], spec["counts"], color="#2c5f8a")
    ax.set_ylabel(spec["ylabel"])
    ax.set_xlabel(spec["xlabel"])
    ax.set_title(spec["title"])
    ax.tick_params(axis="x", rotation=20)
    for label in ax.get_xticklabels():
        label.set_ha("right")
    fig.tight_layout()
    _savefig(fig, path)
    plt.close(fig)


def _plot_fig09(plt: Any, spec: Mapping[str, Any], path: Path) -> None:
    x = list(range(len(spec["fractions"])))
    fig, ax = plt.subplots(figsize=(9.4, 6.0))
    ax.fill_between(
        x,
        spec["conservative"],
        spec["ideal"],
        color="#9bb7d4",
        alpha=0.28,
        label=spec["band_label"],
        zorder=1,
    )
    ax.plot(
        x,
        spec["ideal"],
        marker="o",
        color="#2c5f8a",
        linewidth=2.0,
        markersize=7,
        label=spec["ideal_label"],
        zorder=3,
    )
    ax.plot(
        x,
        spec["conservative"],
        marker="s",
        color="#8a3d3d",
        linewidth=2.0,
        markersize=7,
        label=spec["conservative_label"],
        zorder=4,
    )
    ax.axhline(
        spec["current_corpus"],
        color="#333333",
        linestyle="--",
        linewidth=1.2,
        label=spec["current_label"],
        zorder=2,
    )
    ax.set_xticks(x, labels=spec["tick_labels"])
    ax.set_xlabel(spec["xlabel"])
    ax.set_ylabel(spec["ylabel"])
    ax.set_title(spec["title"])
    ax.legend(loc="upper left", fontsize=8.5, framealpha=0.95)
    ymin = min([*spec["conservative"], *spec["ideal"], spec["current_corpus"]])
    ymax = max([*spec["conservative"], *spec["ideal"], spec["current_corpus"]])
    ax.set_ylim(ymin - max(30, 0.06 * ymax), ymax + max(50, 0.10 * ymax))
    note_bits = []
    if spec["targets_above"]:
        note_bits.append(f"At 2%, {spec['targets_above'][0]} targets exceed the nominal threshold.")
    if spec["only_ngf_from_3pct"]:
        note_bits.append(
            "From 3% upward, NGF is the only target above the nominal threshold. "
            "The conservative line is therefore flat because removing every cluster "
            f"that contains NGF removes the same {spec['ngf_clusters']} clusters under "
            "each of these candidate caps."
        )
    fig.tight_layout(rect=(0, 0.18 if note_bits else 0, 1, 1))
    if note_bits:
        fig.text(
            0.04,
            0.02,
            textwrap.fill(" ".join(note_bits), width=92),
            ha="left",
            va="bottom",
            fontsize=8.0,
        )
    _savefig(fig, path)
    plt.close(fig)


def _plot_fig10(plt: Any, spec: Mapping[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    ax.bar(spec["labels"], spec["counts"], color="#3d7a5a")
    ax.set_xlabel(spec["xlabel"])
    ax.set_ylabel(spec["ylabel"])
    ax.set_title(spec["title"])
    fig.tight_layout()
    _savefig(fig, path)
    plt.close(fig)


def plot_data_tables(assembly: S6Assembly) -> dict[str, list[dict[str, str]]]:
    spec03 = fig03_spec(assembly)
    spec04 = fig04_spec(assembly)
    spec06 = fig06_spec(assembly)
    spec07 = fig07_spec(assembly)
    spec09 = fig09_spec(assembly)
    fig03_rows = [
        {"source_db": "overall", "length": str(value), "n": str(count)}
        for value, count in sorted(Counter(assembly.core_lengths).items())
    ]
    for src in spec03["sources"]:
        for value, count in sorted(Counter(spec03["source_lengths"][src]).items()):
            fig03_rows.append({"source_db": src, "length": str(value), "n": str(count)})
    fig04_rows: list[dict[str, str]] = []
    for field, values in (("core", spec04["core_lengths"]), ("full", spec04["full_lengths"])):
        for value, count in sorted(Counter(values).items()):
            fig04_rows.append({"sequence_field": field, "length": str(value), "n": str(count)})
    return {
        "fig01_top30_targets.csv": [
            {
                "canonical_target_name": row["canonical_target_name"],
                "n_scientific_identities": row["n_scientific_identities"],
                "n_clusters": row["n_clusters"],
            }
            for row in assembly.target_rows[:TOP_N_TARGETS]
        ],
        "fig02_target_family.csv": [
            {
                "target_family": row["target_family"],
                "target_family_display": family_display_name(row["target_family"]),
                "n_scientific_identities": row["n_scientific_identities"],
            }
            for row in assembly.family_rows
        ],
        "fig03_sequence_core_length.csv": fig03_rows,
        "fig04_sequence_full_length.csv": fig04_rows,
        "fig05_gc_distribution.csv": [
            {"gc_fraction": fmt_float(value, 8)} for value in assembly.gc_values
        ],
        "fig06_cluster_size.csv": [
            {"n_distinct_sequence_core": str(size), "n_clusters": str(count)}
            for size, count in zip(spec06["categories"], spec06["counts"])
        ],
        "fig07_evidence_level.csv": [
            {
                "evidence_level": level,
                "display_label": label.replace("\n", " "),
                "n_scientific_identities": str(count),
            }
            for level, label, count in zip(spec07["levels"], spec07["labels"], spec07["counts"])
        ],
        "fig08_source_contribution.csv": [
            {
                "source_db": row["source_db"],
                "n_identities_donor": row["n_identities_donor"],
            }
            for row in assembly.source_rows
            if int(row["n_identities_donor"]) > 0
        ],
        "fig09_candidate_target_cap.csv": [
            {
                "max_target_fraction": row["max_target_fraction"],
                "idealised_recordwise_capped_corpus_size": row["idealised_recordwise_capped_corpus_size"],
                "cluster_union_upper_bound_remaining_identities": row[
                    "cluster_union_upper_bound_remaining_identities"
                ],
                "n_targets_above_threshold": row["n_targets_above_threshold"],
            }
            for row in assembly.cap_rows
        ],
        "fig10_corroboration.csv": [
            {"corroboration_count": key, "n_scientific_identities": str(value)}
            for key, value in assembly.source_stats["corroboration_count_distribution"].items()
        ],
        "fig04_core_full_comparison.csv": [
            {
                "n_identities": str(spec04["n_identities"]),
                "n_same_length": str(spec04["n_same_length"]),
                "pct_same_length": fmt_float(spec04["pct_same_length"]),
                "median_core_nt": fmt_float(spec04["median_core_nt"], 3),
                "median_full_nt": fmt_float(spec04["median_full_nt"], 3),
                "median_full_minus_core_nt": fmt_float(spec04["median_full_minus_core_nt"], 3),
            }
        ],
        "fig09_plot_spec.csv": [
            {
                "max_target_fraction": f"{frac:.2f}",
                "tick_label": label,
                "idealised_recordwise_capped_corpus_size": str(ideal),
                "cluster_union_upper_bound_remaining_identities": str(cons),
                "current_corpus": str(spec09["current_corpus"]),
                "n_targets_above_threshold": str(n_above),
            }
            for frac, label, ideal, cons, n_above in zip(
                spec09["fractions"],
                spec09["tick_labels"],
                spec09["ideal"],
                spec09["conservative"],
                spec09["targets_above"],
            )
        ],
    }


def write_figures(assembly: S6Assembly, figures_dir: Path) -> dict[str, str]:
    plt = _configure_matplotlib()
    figures_dir.mkdir(parents=True, exist_ok=True)
    writers = (
        ("fig01_top30_targets.png", _plot_fig01, fig01_spec),
        ("fig02_target_family.png", _plot_fig02, fig02_spec),
        ("fig03_sequence_core_length.png", _plot_fig03, fig03_spec),
        ("fig04_sequence_full_length.png", _plot_fig04, fig04_spec),
        ("fig05_gc_distribution.png", _plot_fig05, fig05_spec),
        ("fig06_cluster_size.png", _plot_fig06, fig06_spec),
        ("fig07_evidence_level.png", _plot_fig07, fig07_spec),
        ("fig08_source_contribution.png", _plot_fig08, fig08_spec),
        ("fig09_candidate_target_cap.png", _plot_fig09, fig09_spec),
        ("fig10_corroboration.png", _plot_fig10, fig10_spec),
    )
    written: dict[str, str] = {}
    for name, plotter, spec_fn in writers:
        path = figures_dir / name
        plotter(plt, spec_fn(assembly), path)
        written[name] = str(path)
        assert_not_frozen_s5_path(path)
    return written


def write_profile_tables(
    assembly: S6Assembly,
    profile_dir: Path,
) -> dict[str, Path]:
    profile_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    def write_csv(name: str, rows: Sequence[Mapping[str, str]], columns: Sequence[str] | None = None) -> None:
        path = profile_dir / name
        assert_not_frozen_s5_path(path)
        fieldnames = list(columns) if columns is not None else list(rows[0].keys() if rows else [])
        write_corpus_csv_atomic(path, rows, columns=fieldnames)
        paths[name] = path

    from adapters.s6_profile import (
        CAP_IMPACT_COLUMNS,
        CAP_TARGET_COLUMNS,
        CLUSTER_PROFILE_COLUMNS,
        COMPOSITION_COLUMNS,
        EVIDENCE_PROFILE_COLUMNS,
        FAMILY_PROFILE_COLUMNS,
        LENGTH_PROFILE_COLUMNS,
        LICENSING_COLUMNS,
        PFAM_PROFILE_COLUMNS,
        SOURCE_PROFILE_COLUMNS,
        SPARSE_TARGET_COLUMNS,
        TARGET_PROFILE_COLUMNS,
    )

    write_csv("target_profile.csv", assembly.target_rows, TARGET_PROFILE_COLUMNS)
    write_csv("target_family_profile.csv", assembly.family_rows, FAMILY_PROFILE_COLUMNS)
    write_csv("pfam_profile.csv", assembly.pfam_rows, PFAM_PROFILE_COLUMNS)
    write_csv("interpro_profile.csv", assembly.interpro_rows, PFAM_PROFILE_COLUMNS)
    write_csv("sparse_targets.csv", assembly.sparse_rows, SPARSE_TARGET_COLUMNS)
    write_csv("candidate_cap_impact.csv", assembly.cap_rows, CAP_IMPACT_COLUMNS)
    write_csv("candidate_cap_overrepresented_targets.csv", assembly.cap_target_rows, CAP_TARGET_COLUMNS)
    write_csv("length_profile.csv", assembly.length_rows, LENGTH_PROFILE_COLUMNS)
    write_csv("nucleotide_composition.csv", assembly.composition_rows, COMPOSITION_COLUMNS)
    write_csv("cluster_profile.csv", assembly.cluster_rows, CLUSTER_PROFILE_COLUMNS)
    write_csv("largest_clusters.csv", assembly.cluster_rows[:20], CLUSTER_PROFILE_COLUMNS)
    write_csv("source_profile.csv", assembly.source_rows, SOURCE_PROFILE_COLUMNS)
    write_csv(
        "s6_exact_overlap_matrix.csv",
        assembly.source_stats["overlap_matrix"],
        ("source_a", "source_b", "n_shared_scientific_identities", "n_shared_duplicate_groups"),
    )
    write_csv("evidence_profile.csv", assembly.evidence_rows, EVIDENCE_PROFILE_COLUMNS)
    write_csv("licensing_profile.csv", assembly.licensing_rows, LICENSING_COLUMNS)
    write_csv(
        "source_length_regime_summary.csv",
        assembly.source_regime_rows,
        SOURCE_REGIME_COLUMNS,
    )
    write_csv(
        "core_full_length_comparison.csv",
        [
            {
                "n_identities": str(assembly.core_full_comparison.get("n_identities", "")),
                "n_same_length": str(assembly.core_full_comparison.get("n_same_length", "")),
                "pct_same_length": fmt_float(float(assembly.core_full_comparison.get("pct_same_length", 0.0))),
                "median_core_nt": fmt_float(float(assembly.core_full_comparison.get("median_core_nt", 0.0)), 3),
                "median_full_nt": fmt_float(float(assembly.core_full_comparison.get("median_full_nt", 0.0)), 3),
                "median_full_minus_core_nt": fmt_float(
                    float(assembly.core_full_comparison.get("median_full_minus_core_nt", 0.0)), 3
                ),
                "mean_full_minus_core_nt": fmt_float(
                    float(assembly.core_full_comparison.get("mean_full_minus_core_nt", 0.0)), 3
                ),
            }
        ],
        CORE_FULL_COMPARISON_COLUMNS,
    )
    write_csv(
        "length_outliers_gt100nt.csv",
        assembly.length_outliers["outliers"],
        (
            "scientific_identity_id",
            "sequence_core_sha256",
            "cluster_id",
            "canonical_target_name",
            "source_db",
            "sequence_length_core",
            "sequence_length_full",
            "construct_scope",
            "alphabet_as_reported",
        ),
    )
    plot_tables = plot_data_tables(assembly)
    for name, rows in plot_tables.items():
        write_csv(name, rows, list(rows[0].keys()) if rows else None)

    write_json_atomic(profile_dir / "headline.json", _jsonable(assembly.headline))
    write_json_atomic(profile_dir / "diversity_metrics.json", _jsonable(assembly.diversity))
    write_json_atomic(profile_dir / "bimodality.json", _jsonable(assembly.bimodality))
    write_json_atomic(profile_dir / "uniprot_resolution.json", _jsonable(assembly.uniprot))
    write_json_atomic(profile_dir / "polyspecificity.json", _jsonable(assembly.polyspecificity))
    write_json_atomic(profile_dir / "affinity_profile.json", _jsonable(assembly.affinity))
    write_json_atomic(profile_dir / "chemistry_construct.json", _jsonable(assembly.chemistry))
    write_json_atomic(profile_dir / "qc_observations.json", _jsonable(assembly.qc))
    write_json_atomic(profile_dir / "scientific_payload.json", _jsonable(scientific_payload(assembly)))
    for name in (
        "headline.json",
        "diversity_metrics.json",
        "bimodality.json",
        "uniprot_resolution.json",
        "polyspecificity.json",
        "affinity_profile.json",
        "chemistry_construct.json",
        "qc_observations.json",
        "scientific_payload.json",
    ):
        paths[name] = profile_dir / name
        if name == "scientific_payload.json":
            continue
        text = paths[name].read_text(encoding="utf-8")
        assert_no_sequence_leak(text, label=name)
    return paths


def write_checkpoint3_package(assembly: S6Assembly, checkpoint_dir: Path) -> dict[str, Path]:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    summary_path = checkpoint_dir / "checkpoint3_summary.md"
    decisions_path = checkpoint_dir / "checkpoint3_decisions.csv"
    assert_not_frozen_s5_path(summary_path)
    assert_not_frozen_s5_path(decisions_path)
    write_text_atomic(summary_path, build_checkpoint3_summary(assembly))
    write_corpus_csv_atomic(
        decisions_path,
        assembly.checkpoint3_decisions,
        columns=CHECKPOINT3_DECISION_COLUMNS,
    )
    for path in (summary_path, decisions_path):
        assert_no_sequence_leak(path.read_text(encoding="utf-8"), label=path.name)
    return {"checkpoint3_summary.md": summary_path, "checkpoint3_decisions.csv": decisions_path}


__all__ = [
    "E5_PARKED_NOTE",
    "FIGURE_FILENAMES",
    "build_checkpoint3_summary",
    "build_corpus_profile_report",
    "build_figure_captions",
    "build_figure_pack_supervisor",
    "donor_facet_sources",
    "fig01_spec",
    "fig03_spec",
    "fig04_spec",
    "fig06_spec",
    "fig07_spec",
    "fig09_spec",
    "length_histogram_bins",
    "plot_data_tables",
    "write_checkpoint3_package",
    "write_figures",
    "write_profile_tables",
]
