#!/usr/bin/env python3
"""Apply completed CHECKPOINT-2 reviews and write authoritative global S4 output.

Does not mutate combined input or review CSVs. Does not start S5.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.checkpoint2_apply import (  # noqa: E402
    PARKED_AUDIT_COLUMNS,
    RECORD_MAP_COLUMNS,
    REVIEWED_DICTIONARY_COLUMNS,
    REVIEWED_RELATIONSHIP_COLUMNS,
    apply_checkpoint2_reviews,
)
from adapters.checkpoint2_evidence import EVIDENCE_CONSISTENCY_FILE  # noqa: E402
from adapters.s4_leakage_proposal import load_leakage_resources  # noqa: E402
from adapters.s4_scientific_common import (  # noqa: E402
    ScientificProposalError,
    assert_no_sequence_leak,
    write_json_atomic,
)
from checkpoint2_validate_review import validate_checkpoint2_package  # noqa: E402
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

ROUTING_SUMMARY_COLUMNS = (
    "grain",
    "source_db",
    "category",
    "n",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _resolve(root: Path, relative: str) -> Path:
    return (root / relative).resolve()


def _git_working_state(root: Path) -> dict[str, str | bool]:
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
    ).strip()
    porcelain = subprocess.check_output(
        ["git", "status", "--porcelain"],
        cwd=root,
        text=True,
    )
    return {
        "git_head": head,
        "working_tree_dirty": bool(porcelain.strip()),
        "working_tree_status_sha256": hashlib.sha256(
            porcelain.encode("utf-8")
        ).hexdigest(),
    }


def _verify_hashes(root: Path, expected: Mapping[str, Sequence[str]]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for name, spec in expected.items():
        rel, digest = spec
        path = _resolve(root, rel)
        got = sha256_file(path)
        observed[name] = got
        if got != digest:
            raise ScientificProposalError(
                f"{name} SHA-256 mismatch: expected {digest}, got {got}"
            )
    return observed


def _routing_summary_rows(counts: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for category, n in sorted((counts.get("source_record_outcomes") or {}).items()):
        rows.append(
            {
                "grain": "source_record",
                "source_db": "all",
                "category": category,
                "n": str(n),
            }
        )
    for source, cat_counts in (counts.get("source_record_outcomes_by_source") or {}).items():
        for category, n in sorted(cat_counts.items()):
            rows.append(
                {
                    "grain": "source_record",
                    "source_db": source,
                    "category": category,
                    "n": str(n),
                }
            )
    for category, n in sorted((counts.get("relationship_routing") or {}).items()):
        rows.append(
            {
                "grain": "reviewed_relationship",
                "source_db": "all",
                "category": category,
                "n": str(n),
            }
        )
    for source, cat_counts in (counts.get("relationship_routing_by_source") or {}).items():
        for category, n in sorted(cat_counts.items()):
            rows.append(
                {
                    "grain": "reviewed_relationship",
                    "source_db": source,
                    "category": category,
                    "n": str(n),
                }
            )
    return rows


def apply_global_s4_checkpoint2(
    *,
    apply_config: Path,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config = json.loads(_resolve(root, str(apply_config)).read_text(encoding="utf-8"))
    hashes_before = _verify_hashes(root, config["expected_hashes"])
    combined_path = _resolve(root, config["combined_input_csv"])
    if hashes_before["combined_input"] != config["expected_hashes"]["combined_input"][1]:
        raise ScientificProposalError("combined input hash drifted before application")

    package_dir = _resolve(root, config["checkpoint2_dir"])
    validator = validate_checkpoint2_package(package_dir)
    if not validator.get("ready_for_application"):
        raise ScientificProposalError(
            "CHECKPOINT-2 package is not ready_for_application=true"
        )
    if validator.get("unresolved_decisions"):
        raise ScientificProposalError("unresolved CHECKPOINT-2 decisions remain")
    if validator.get("n_evidence_affinity_inconsistencies"):
        raise ScientificProposalError("evidence-affinity inconsistencies remain")
    if validator.get("errors"):
        raise ScientificProposalError(
            "CHECKPOINT-2 validator errors: " + "; ".join(validator["errors"])
        )

    proposal_config = json.loads(
        _resolve(root, config["proposal_config"]).read_text(encoding="utf-8")
    )
    leak_index, alias_rules = load_leakage_resources(
        exclusion_set=_resolve(root, proposal_config["leakage_exclusion_set"]),
        alias_csv=_resolve(root, proposal_config["leakage_target_aliases"]),
    )

    combined_rows = _read_csv(combined_path)
    application = apply_checkpoint2_reviews(
        combined_rows=combined_rows,
        machine_relationship_rows=_read_csv(
            _resolve(root, proposal_config["outputs"]["relationship_scientific_csv"])
        ),
        dictionary_rows=_read_csv(
            _resolve(root, proposal_config["outputs"]["enriched_dictionary_csv"])
        ),
        evidence_rows=_read_csv(
            _resolve(root, proposal_config["outputs"]["evidence_affinity_csv"])
        ),
        target_review_rows=_read_csv(
            package_dir / "checkpoint2_target_dictionary_review.csv"
        ),
        relationship_review_rows=_read_csv(
            package_dir / "checkpoint2_relationship_review.csv"
        ),
        evidence_review_rows=_read_csv(
            package_dir / "checkpoint2_evidence_review.csv"
        ),
        evidence_consistency_rows=_read_csv(
            package_dir / EVIDENCE_CONSISTENCY_FILE
        ),
        affinity_review_rows=_read_csv(
            package_dir / "checkpoint2_affinity_review.csv"
        ),
        leakage_review_rows=_read_csv(
            package_dir / "checkpoint2_leakage_review.csv"
        ),
        leakage_index=leak_index,
        alias_rules=alias_rules,
        expected_combined_records=int(config["expected_combined_records"]),
        expected_reviewed_resolved_targets=int(
            config["expected_reviewed_resolved_targets"]
        ),
        require_camp_identity=True,
    )
    if not application.validation.get("ok"):
        raise ScientificProposalError(
            "application validation failed: "
            + "; ".join(application.validation.get("errors") or [])
        )

    outputs = config["outputs"]
    out_rel = _resolve(root, outputs["reviewed_relationships_csv"])
    out_dict = _resolve(root, outputs["reviewed_dictionary_csv"])
    out_map = _resolve(root, outputs["record_map_csv"])
    out_audit = _resolve(root, outputs["parked_audit_csv"])
    out_route = _resolve(root, outputs["routing_summary_csv"])
    out_summary = _resolve(root, outputs["application_summary_json"])
    out_manifest = _resolve(root, outputs["application_manifest_json"])
    for path in (out_rel, out_dict, out_map, out_audit, out_route, out_summary, out_manifest):
        if path.resolve() == combined_path.resolve():
            raise ScientificProposalError("refusing to overwrite combined input")

    write_corpus_csv_atomic(
        out_rel, application.reviewed_relationships, columns=REVIEWED_RELATIONSHIP_COLUMNS
    )
    write_corpus_csv_atomic(
        out_dict, application.reviewed_dictionary, columns=REVIEWED_DICTIONARY_COLUMNS
    )
    write_corpus_csv_atomic(
        out_map, application.record_map, columns=RECORD_MAP_COLUMNS
    )
    write_corpus_csv_atomic(
        out_audit, application.parked_audit, columns=PARKED_AUDIT_COLUMNS
    )
    write_corpus_csv_atomic(
        out_route, _routing_summary_rows(application.counts), columns=ROUTING_SUMMARY_COLUMNS
    )

    hashes_after = _verify_hashes(root, config["expected_hashes"])
    if hashes_after != hashes_before:
        raise ScientificProposalError("input/review hashes changed during application")

    output_hashes = {
        "reviewed_relationships": sha256_file(out_rel),
        "reviewed_dictionary": sha256_file(out_dict),
        "record_map": sha256_file(out_map),
        "parked_audit": sha256_file(out_audit),
        "routing_summary": sha256_file(out_route),
    }
    git_state = _git_working_state(root)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = {
        "contract_id": config["contract_id"],
        "timestamp_utc": timestamp,
        "ready_for_application": True,
        "checkpoint2_applied": True,
        "global_s4_complete": True,
        "s5_started": False,
        "s5_operations_run": False,
        "s5_operations_not_run": application.counts.get("s5_operations_not_run"),
        "validator": {
            "ready_for_application": validator.get("ready_for_application"),
            "unresolved_decisions": validator.get("unresolved_decisions"),
            "n_evidence_affinity_inconsistencies": validator.get(
                "n_evidence_affinity_inconsistencies"
            ),
            "errors": validator.get("errors"),
        },
        "counts": application.counts,
        "validation": application.validation,
        "input_hashes": hashes_before,
        "output_hashes": output_hashes,
        "git": git_state,
    }
    assert_no_sequence_leak(json.dumps(summary), label="application summary")
    write_json_atomic(out_summary, summary)
    manifest = {
        "contract_id": config["contract_id"],
        "milestone": config["milestone"],
        "timestamp_utc": timestamp,
        "ready_for_application": True,
        "checkpoint2_applied": True,
        "global_s4_complete": True,
        "s5_started": False,
        "s5_operations_run": False,
        "combined_input_sha256": hashes_before["combined_input"],
        "review_hashes": {
            key: hashes_before[key]
            for key in (
                "target_review",
                "relationship_review",
                "evidence_review",
                "affinity_review",
                "evidence_consistency_review",
                "leakage_review",
            )
        },
        "machine_proposal_hashes": {
            key: hashes_before[key]
            for key in (
                "relationship_scientific",
                "target_dictionary",
                "evidence_affinity",
            )
        },
        "output_hashes": output_hashes,
        "row_counts": {
            "combined_records": application.counts.get("n_combined_records"),
            "reviewed_relationships": application.counts.get(
                "n_reviewed_relationship_rows"
            ),
            "reviewed_resolved_targets": application.counts.get(
                "n_reviewed_resolved_targets"
            ),
            "effective_dictionary_entries": application.counts.get(
                "n_effective_dictionary_entries"
            ),
            "record_map": len(application.record_map),
            "parked_audit": len(application.parked_audit),
        },
        "routing_counts": {
            "source_record": application.counts.get("source_record_outcomes"),
            "reviewed_relationship": application.counts.get("relationship_routing"),
        },
        "leakage_counts": {
            "n_leakage_excluded_records": application.counts.get(
                "n_leakage_excluded_records"
            )
        },
        "git": git_state,
        "outputs": config["outputs"],
        "scientific_boundary": config["scientific_boundary"],
    }
    assert_no_sequence_leak(json.dumps(manifest), label="application manifest")
    write_json_atomic(out_manifest, manifest)

    rerun = apply_checkpoint2_reviews(
        combined_rows=combined_rows,
        machine_relationship_rows=_read_csv(
            _resolve(root, proposal_config["outputs"]["relationship_scientific_csv"])
        ),
        dictionary_rows=_read_csv(
            _resolve(root, proposal_config["outputs"]["enriched_dictionary_csv"])
        ),
        evidence_rows=_read_csv(
            _resolve(root, proposal_config["outputs"]["evidence_affinity_csv"])
        ),
        target_review_rows=_read_csv(
            package_dir / "checkpoint2_target_dictionary_review.csv"
        ),
        relationship_review_rows=_read_csv(
            package_dir / "checkpoint2_relationship_review.csv"
        ),
        evidence_review_rows=_read_csv(
            package_dir / "checkpoint2_evidence_review.csv"
        ),
        evidence_consistency_rows=_read_csv(
            package_dir / EVIDENCE_CONSISTENCY_FILE
        ),
        affinity_review_rows=_read_csv(
            package_dir / "checkpoint2_affinity_review.csv"
        ),
        leakage_review_rows=_read_csv(
            package_dir / "checkpoint2_leakage_review.csv"
        ),
        leakage_index=leak_index,
        alias_rules=alias_rules,
        expected_combined_records=int(config["expected_combined_records"]),
        expected_reviewed_resolved_targets=int(
            config["expected_reviewed_resolved_targets"]
        ),
        require_camp_identity=True,
    )
    write_corpus_csv_atomic(
        out_rel, rerun.reviewed_relationships, columns=REVIEWED_RELATIONSHIP_COLUMNS
    )
    write_corpus_csv_atomic(
        out_dict, rerun.reviewed_dictionary, columns=REVIEWED_DICTIONARY_COLUMNS
    )
    write_corpus_csv_atomic(
        out_map, rerun.record_map, columns=RECORD_MAP_COLUMNS
    )
    write_corpus_csv_atomic(
        out_audit, rerun.parked_audit, columns=PARKED_AUDIT_COLUMNS
    )
    write_corpus_csv_atomic(
        out_route, _routing_summary_rows(rerun.counts), columns=ROUTING_SUMMARY_COLUMNS
    )
    rerun_hashes = {
        "reviewed_relationships": sha256_file(out_rel),
        "reviewed_dictionary": sha256_file(out_dict),
        "record_map": sha256_file(out_map),
        "parked_audit": sha256_file(out_audit),
        "routing_summary": sha256_file(out_route),
    }
    if rerun_hashes != output_hashes:
        raise ScientificProposalError(
            "application is not deterministic: output hashes changed on rerun"
        )
    hashes_final = _verify_hashes(root, config["expected_hashes"])
    if hashes_final != hashes_before:
        raise ScientificProposalError("input/review hashes changed during determinism rerun")
    ls_files_data = subprocess.check_output(
        ["git", "ls-files", "data"],
        cwd=root,
        text=True,
    ).strip()
    if ls_files_data:
        raise ScientificProposalError("git ls-files data is not empty")

    summary["determinism"] = {"repeat_output_hashes": rerun_hashes, "identical": True}
    write_json_atomic(out_summary, summary)
    manifest["determinism"] = summary["determinism"]
    write_json_atomic(out_manifest, manifest)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply completed CHECKPOINT-2 reviews to global S4"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/global_s4_checkpoint2_apply.json"),
    )
    args = parser.parse_args()
    result = apply_global_s4_checkpoint2(apply_config=args.config)
    print(json.dumps(
        {
            "ok": True,
            "reviewed_relationships": result["counts"]["n_reviewed_relationship_rows"],
            "reviewed_resolved_targets": result["counts"]["n_reviewed_resolved_targets"],
            "source_record_outcomes": result["counts"]["source_record_outcomes"],
            "relationship_routing": result["counts"]["relationship_routing"],
            "output_hashes": result["output_hashes"],
            "determinism": result.get("determinism"),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
