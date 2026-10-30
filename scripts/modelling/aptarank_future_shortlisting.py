#!/usr/bin/env python3
"""Build the final Tier-1-led future-shortlisting hand-off.

This adapter does not run AptaRank or change any closed Section 10 artifact.
It revalidates the closed Section 10 lineage, selects existing Tier 1 ranks
1--50, and carries Tier 2 and shuffle outputs forward as annotations only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    from scripts.modelling import aptarank_section10_analyze_and_build_review_pool as section10
except ModuleNotFoundError:
    import aptarank_section10_analyze_and_build_review_pool as section10


SCHEMA_VERSION = "mres-aptarank-future-shortlisting-v1"
STATUS = "FUTURE_SHORTLISTING_SET_SCIENTIFICALLY_COMMITTED"
PLAN_RELATIVE = "docs/evaluation/aptarank_full_mres_thesis_evaluation_plan_v3_10.md"
PLAN_SHA256 = "08b019ce00ea87485dee1c1d436eca3d1b9780d3506ad8c88716cf089f53c020"
CLOSURE_RELATIVE = (
    "results/aptarank/evaluation/section10_d1_full_pool_ndm1_evaluation_preset_v1/"
    "closure/section10_computational_pool_closure_record.json"
)
CLOSURE_SHA256 = "305367b52eee1cfa56892200db053f67c5652bdb1832ff342b957a16fe1040ee"
OUTPUT_RELATIVE = "results/aptarank/evaluation/future_shortlisting_sequences"
SOURCE_ARTIFACT_SHA256 = "cedcc36133f5dfb3678e1560c6d6bab703136fe89e512e939b9f93a9a6361de9"
CANDIDATE_ID = re.compile(r"cand_[0-9a-f]{32}\Z")
RNA = re.compile(r"[ACGU]+\Z")


class FutureShortlistingError(RuntimeError):
    """Raised when a future-shortlisting invariant fails."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_pinned(path: Path, expected: str, role: str) -> bytes:
    payload = path.read_bytes()
    observed = sha256_bytes(payload)
    if observed != expected:
        raise FutureShortlistingError(
            f"{role} hash mismatch: expected {expected}, observed {observed}"
        )
    return payload


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def jsonl_bytes(rows: list[dict[str, object]]) -> bytes:
    return (
        "".join(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n" for row in rows)
    ).encode("utf-8")


def decimal_value(text: str, role: str, *, unit_interval: bool = False) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise FutureShortlistingError(f"{role} is not a decimal") from exc
    if not value.is_finite() or (unit_interval and not Decimal(0) <= value <= Decimal(1)):
        raise FutureShortlistingError(f"{role} is outside its valid range")
    return value


def parse_private_membership(payload: bytes) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for line in payload.decode("utf-8").splitlines():
        row = json.loads(line)
        candidate = str(row.get("candidate_id"))
        if candidate in rows:
            raise FutureShortlistingError("duplicate candidate in private membership key")
        rows[candidate] = row
    if len(rows) != 30000:
        raise FutureShortlistingError("private membership denominator drifted")
    return rows


def parse_source_key(payload: bytes) -> dict[str, dict[str, object]]:
    document = json.loads(payload.decode("utf-8"))
    memberships = document.get("memberships")
    if not isinstance(memberships, list) or len(memberships) != 30000:
        raise FutureShortlistingError("source candidate key denominator drifted")
    rows: dict[str, dict[str, object]] = {}
    for row in memberships:
        if not isinstance(row, dict):
            raise FutureShortlistingError("source candidate key contains a non-object row")
        candidate = str(row.get("candidate_id"))
        if candidate in rows:
            raise FutureShortlistingError("duplicate candidate in source candidate key")
        rows[candidate] = row
    return rows


def select_and_enrich(
    full_rows: list[dict[str, str]],
    exact_rows: list[dict[str, str]],
    source_by_id: dict[str, dict[str, object]],
    private_by_id: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    if len(full_rows) != 29583 or len(exact_rows) != 1000:
        raise FutureShortlistingError("closed export denominator drifted")
    selected = full_rows[:50]
    if [int(row["rank"]) for row in selected] != list(range(1, 51)):
        raise FutureShortlistingError("future-shortlisting ranks are not exactly 1 through 50")
    output: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, (full, exact) in enumerate(zip(selected, exact_rows[:50]), start=1):
        candidate = full["candidate"]
        if not CANDIDATE_ID.fullmatch(candidate) or candidate in seen:
            raise FutureShortlistingError("candidate ID is malformed or duplicated")
        seen.add(candidate)
        sequence = full["sequence"]
        if not RNA.fullmatch(sequence):
            raise FutureShortlistingError("candidate sequence is not canonical RNA")
        try:
            rank = int(full["rank"])
            length = int(full["len"])
            exact_rank = int(exact["rank"])
            exact_index = int(exact[""])
        except ValueError as exc:
            raise FutureShortlistingError("rank, index or length is not an integer") from exc
        tier1 = decimal_value(full["aptamer-likeness"], "Tier 1 score", unit_interval=True)
        exact_tier1 = decimal_value(exact["tier1"], "exact Tier 1 score", unit_interval=True)
        percentile = decimal_value(exact["control_percentile"], "Tier 2 percentile", unit_interval=True)
        mismatch = decimal_value(exact["mismatch"], "Tier 2 mismatch")
        expected_band = "strong" if percentile >= Decimal("0.95") else "moderate" if percentile >= Decimal("0.75") else "weak"
        if (
            rank != index
            or exact_rank != rank
            or exact_index != index - 1
            or exact["candidate"] != candidate
            or exact_tier1 != tier1
            or exact["band"] != full["compatibility"]
            or exact["band"] != expected_band
            or full["shuffle"] not in {"pass", "fail"}
            or length != len(sequence)
        ):
            raise FutureShortlistingError("full and exact exports do not reconcile")
        source = source_by_id.get(candidate)
        private = private_by_id.get(candidate)
        if source is None or private is None:
            raise FutureShortlistingError("candidate lacks restricted provenance")
        sequence_digest = sha256_bytes(sequence.encode("ascii"))
        source_record_ids = source.get("source_record_ids")
        occurrences = private.get("source_occurrences")
        if (
            source.get("condition") != "D1"
            or private.get("condition") != "D1"
            or source.get("sequence_sha256") != sequence_digest
            or source.get("length") != length
            or private.get("length") != length
            or source.get("multiplicity") != 1
            or private.get("multiplicity") != 1
            or not isinstance(source_record_ids, list)
            or len(source_record_ids) != 1
            or not isinstance(occurrences, list)
            or len(occurrences) != 1
        ):
            raise FutureShortlistingError("candidate sequence or multiplicity does not reconcile")
        occurrence = occurrences[0]
        if not isinstance(occurrence, dict) or occurrence.get("source_identity") != source_record_ids[0]:
            raise FutureShortlistingError("source identity does not reconcile")
        provenance = occurrence.get("provenance")
        if not isinstance(provenance, dict):
            raise FutureShortlistingError("provenance is not an object")
        seed = provenance.get("d1_training_seed")
        block = provenance.get("technical_block")
        if seed not in {43, 44} or block != ({43: "A", 44: "B"}[seed]):
            raise FutureShortlistingError("D1 seed/block provenance is invalid")
        requested_length = provenance.get("requested_biological_length")
        if (
            not isinstance(requested_length, int)
            or requested_length <= 0
            or provenance.get("source_artifact_id") != "d1:m8-combined-raw-attempt-ledger"
            or provenance.get("source_artifact_sha256") != SOURCE_ARTIFACT_SHA256
        ):
            raise FutureShortlistingError("D1 source-artifact provenance drifted")
        output.append({
            "future_shortlisting_order": index,
            "aptarank_candidate_id": candidate,
            "d1_source_candidate_id": source.get("source_candidate_id"),
            "sequence": sequence,
            "sequence_sha256": sequence_digest,
            "length_nt": length,
            "aptarank_tier1_rank": rank,
            "aptarank_tier1_score": full["aptamer-likeness"],
            "shuffle_annotation": full["shuffle"],
            "tier2_control_percentile_annotation": exact["control_percentile"],
            "tier2_geometric_mismatch_annotation": exact["mismatch"],
            "tier2_band_annotation": exact["band"],
            "d1_provenance": {
                "d1_training_seed": seed,
                "technical_block": block,
                "source_record_id": source_record_ids[0],
                "checkpoint_identity": provenance.get("checkpoint_identity"),
                "generation_seed": provenance.get("generation_seed"),
                "invocation_index": provenance.get("invocation_index"),
                "master_attempt_index": provenance.get("master_attempt_index"),
                "requested_biological_length": requested_length,
                "requested_length_differs_from_realised_sequence": requested_length != length,
                "source_artifact_id": provenance.get("source_artifact_id"),
                "source_artifact_sha256": provenance.get("source_artifact_sha256"),
            },
        })
    return output


def render_fasta(rows: list[dict[str, object]]) -> bytes:
    lines: list[str] = []
    for row in rows:
        provenance = row["d1_provenance"]
        lines.append(
            f">rank={row['aptarank_tier1_rank']}|candidate={row['aptarank_candidate_id']}|"
            f"source={row['d1_source_candidate_id']}|seed={provenance['d1_training_seed']}|"
            f"block={provenance['technical_block']}"
        )
        lines.append(str(row["sequence"]))
    return ("\n".join(lines) + "\n").encode("ascii")


def build_outputs(rows: list[dict[str, object]], input_records: dict[str, dict[str, object]]) -> dict[str, bytes]:
    shuffle = Counter(str(row["shuffle_annotation"]) for row in rows)
    bands = Counter(str(row["tier2_band_annotation"]) for row in rows)
    seeds = Counter(str(row["d1_provenance"]["d1_training_seed"]) for row in rows)
    requested_length_mismatches = sum(
        bool(row["d1_provenance"]["requested_length_differs_from_realised_sequence"])
        for row in rows
    )
    both = sum(
        row["shuffle_annotation"] == "pass" and row["tier2_band_annotation"] in {"strong", "moderate"}
        for row in rows
    )
    decision = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "decision_date": "2026-10-30",
        "decision_source": "explicit project-owner instruction following biology-supervisor consultation",
        "active_plan": {"path": PLAN_RELATIVE, "sha256": PLAN_SHA256},
        "historical_section10_closure": {"path": CLOSURE_RELATIVE, "sha256": CLOSURE_SHA256},
        "candidate_specific_manual_review_performed": False,
        "advanced_to_experimental_validation": 0,
        "retained_as_progressing_towards_future_shortlisting": 50,
        "selection_rule": {
            "primary_and_only_selection_metric": "AptaRank Tier 1 rank",
            "source_review_option": "previously prepared Tier-1-only top 100",
            "retained_ranks": [1, 50],
            "shuffle_role": "coarse annotation only",
            "tier2_role": "coarse annotation only",
            "combined_score_created": False,
            "aptarank_rerun": False,
        },
        "scientific_reasoning": [
            "The selected NDM-1 cavity has a material geometry warning.",
            "Tier 2 and the shuffled-control check had limited validation evidence in the completed evaluation.",
            "D1 did not establish a decisive advantage over the B2 TRAIN-matched non-neural null model across the sequence and structural evaluation.",
        ],
        "claim_boundary": (
            "These 50 sequences are progressing towards shortlisting for experimental validation in future work. "
            "They are not experimentally selected, validated, predicted NDM-1 binders or approved for laboratory progression."
        ),
        "ndm1_target_geometry_warning": section10.CAVITY_WARNING,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "inputs": input_records,
        "selection": {
            "valid_scored_input": 29583,
            "sensitivity_review_pool": 100,
            "retained": len(rows),
            "aptarank_tier1_ranks": [1, 50],
            "shuffle_annotation_counts": dict(sorted(shuffle.items())),
            "tier2_band_annotation_counts": dict(sorted(bands.items())),
            "pass_and_moderate_or_strong_annotation": both,
            "d1_training_seed_counts": dict(sorted(seeds.items())),
            "length_nt": {
                "minimum": min(int(row["length_nt"]) for row in rows),
                "maximum": max(int(row["length_nt"]) for row in rows),
            },
            "requested_length_differs_from_realised_sequence": requested_length_mismatches,
        },
        "checks": {
            "closed_section10_lineage_revalidated": True,
            "ranks_are_exactly_1_through_50": True,
            "full_and_exact_exports_reconcile": True,
            "sequence_hashes_and_lengths_reconcile": True,
            "opaque_and_source_identifiers_reconcile": True,
            "d1_provenance_complete": True,
            "shuffle_and_tier2_not_used_as_gates_or_ordering": True,
            "no_score_recomputed": True,
            "no_aptarank_rerun": True,
            "no_candidate_advanced_to_experimental_validation": True,
        },
    }
    readme = f"""# Future shortlisting sequences

Status: `{STATUS}`

This result contains the 50 highest Tier 1 ranked D1 candidates from the already validated Section 10 AptaRank export. It implements evaluation-plan v3.10 after biology-supervisor consultation. No AptaRank run or score recomputation occurred.

## Final disposition

No sequence is advanced to experimental validation within the MRes thesis. These 50 sequences are retained as **candidates progressing towards shortlisting for experimental validation** in future work, after a better computational prioritisation and evaluation approach has been developed.

## Selection

- Source: the previously prepared Tier-1-only top-100 sensitivity option.
- Retained: AptaRank Tier 1 ranks 1–50, without replacement or manual reordering.
- Primary and only selection metric: Tier 1 rank.
- Shuffle token: coarse annotation only ({shuffle.get('pass', 0)} pass; {shuffle.get('fail', 0)} fail).
- Tier 2 band: coarse annotation only ({bands.get('strong', 0)} strong; {bands.get('moderate', 0)} moderate; {bands.get('weak', 0)} weak).
- Candidates carrying both shuffle-pass and moderate/strong annotations: {both}/50. This count did not affect retention.

The original closed Section 10 result remains unchanged: its earlier gates produced 137 jointly eligible candidates and a 100-candidate review pool. Version 3.10 is a later, outcome-aware final-disposition amendment and is recorded separately rather than rewriting that historical result.

## Files

- `future_shortlisting_candidates.jsonl`: sequence, AptaRank scores/ranks/annotations, identifiers and complete D1 provenance for each candidate.
- `future_shortlisting_sequences.fasta`: sequence hand-off with rank and principal identifiers in the headers.
- `dashboard_candidate_numbers.txt`: AptaRank dashboard candidate numbers/ranks 1–50.
- `future_shortlisting_manifest.json`: input hashes, denominators, annotation counts and validation checks.
- `future_shortlisting_decision_record.json`: supervisor-informed final methodology and claim boundary.

## Interpretation boundary

Tier 2 and shuffle outputs are retained for traceability but are not validated binding evidence and did not determine selection. The selected NDM-1 cavity carries the following warning:

> {section10.CAVITY_WARNING}

The output is not a validated binder set, an experimental shortlist or evidence of NDM-1 affinity, specificity, inhibition or function.
"""
    return {
        "README.md": readme.encode("utf-8"),
        "future_shortlisting_candidates.jsonl": jsonl_bytes(rows),
        "future_shortlisting_sequences.fasta": render_fasta(rows),
        "dashboard_candidate_numbers.txt": ("\n".join(str(index) for index in range(1, 51)) + "\n").encode("ascii"),
        "future_shortlisting_manifest.json": canonical_json(manifest),
        "future_shortlisting_decision_record.json": canonical_json(decision),
    }


def build(repo: Path, private_root: Path) -> dict[str, bytes]:
    adapter = Path(__file__).resolve().read_bytes()
    plan = read_pinned(repo / PLAN_RELATIVE, PLAN_SHA256, "v3.10 plan")
    closure = read_pinned(repo / CLOSURE_RELATIVE, CLOSURE_SHA256, "Section 10 closure")
    # Re-run the closed fail-closed lineage validation before deriving the new hand-off.
    section10.build_analysis(repo, private_root)
    result_root = repo / section10.RESULT_RELATIVE
    private_package = private_root / section10.PRIVATE_RELATIVE
    full_payload = read_pinned(
        result_root / "raw/run_d1_ndm1_125_shortlist.csv",
        section10.RAW_PINS["raw/run_d1_ndm1_125_shortlist.csv"],
        "full scored export",
    )
    exact_payload = read_pinned(
        result_root / "raw/tier1_tier2_exact_d1_ndm1_125.csv",
        section10.RAW_PINS["raw/tier1_tier2_exact_d1_ndm1_125.csv"],
        "exact Tier 2 export",
    )
    source_payload = read_pinned(
        private_package / "source_candidate_key.json",
        section10.PRIVATE_PINS["source_candidate_key.json"],
        "source candidate key",
    )
    membership_payload = read_pinned(
        private_package / "m9b2_private_membership_key.jsonl",
        section10.PRIVATE_PINS["m9b2_private_membership_key.jsonl"],
        "private membership key",
    )
    full_rows = section10.parse_csv(full_payload, section10.FULL_FIELDS, "full scored export")
    exact_rows = section10.parse_csv(exact_payload, section10.EXACT_FIELDS, "exact Tier 2 export")
    rows = select_and_enrich(
        full_rows,
        exact_rows,
        parse_source_key(source_payload),
        parse_private_membership(membership_payload),
    )
    inputs = {
        "analysis_adapter": {"sha256": sha256_bytes(adapter), "byte_count": len(adapter)},
        "v3_10_plan": {"path": PLAN_RELATIVE, "sha256": sha256_bytes(plan), "byte_count": len(plan)},
        "section10_closure": {"path": CLOSURE_RELATIVE, "sha256": sha256_bytes(closure), "byte_count": len(closure)},
        "full_scored_export": {"sha256": sha256_bytes(full_payload), "byte_count": len(full_payload)},
        "exact_tier2_export": {"sha256": sha256_bytes(exact_payload), "byte_count": len(exact_payload)},
        "source_candidate_key": {"sha256": sha256_bytes(source_payload), "byte_count": len(source_payload)},
        "private_membership_key": {"sha256": sha256_bytes(membership_payload), "byte_count": len(membership_payload)},
    }
    return build_outputs(rows, inputs)


def write_outputs(output_dir: Path, outputs: dict[str, bytes]) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, payload in outputs.items():
        (output_dir / name).write_bytes(payload)
    checksum_lines = [
        f"{sha256_bytes(payload)}  {name}"
        for name, payload in sorted(outputs.items())
    ]
    (output_dir / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or args.repo / OUTPUT_RELATIVE
    outputs = build(args.repo.resolve(), args.private_root.resolve())
    write_outputs(output_dir.resolve(), outputs)
    manifest = json.loads(outputs["future_shortlisting_manifest.json"])
    print(json.dumps({
        "status": STATUS,
        "output_dir": str(output_dir.resolve()),
        "retained": manifest["selection"]["retained"],
        "shuffle_annotations": manifest["selection"]["shuffle_annotation_counts"],
        "tier2_annotations": manifest["selection"]["tier2_band_annotation_counts"],
        "training_seeds": manifest["selection"]["d1_training_seed_counts"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
