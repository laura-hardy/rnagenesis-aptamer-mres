"""Read-only M0 checks; never opens REF/EVAL or runs curation/model code.

This is a data gate, not a trainer. Future training entry points must call the
checks before constructing an optimizer. Only the standard library is needed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

CORPUS_COMMIT = "10aac629bb0ef0337107c3d628b23e1897962af9"
SOURCE_CONFIG = "config/global_s7d_final_build.json"
SOURCE_CONFIG_SHA256 = "abd3e1b29f422848aabd309ab0bb985731b9fb3941ddfbd2ec0f43d31a98b475"
TRAIN_TEXT_SHA256 = "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d"
CONTRACT_PATH = "config/modelling/frozen_data_contract.json"
DEVELOPMENT_ROLES = {"TRAIN", "TRAIN_TEXT", "VALIDATION"}
ALLOWED_USES = {
    "TRAIN": ["fit"],
    "TRAIN_TEXT": ["fit"],
    "VALIDATION": ["development_evaluate", "checkpoint_select"],
    "REF": ["aptarank_calibrate"],
    "EVAL": ["final_evaluate_after_unlock"],
}


class ContractError(ValueError):
    """A frozen input or experimental boundary failed verification."""


def require(condition, message):
    if not condition:
        raise ContractError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(data):
    return json.loads(data, object_pairs_hook=unique_keys)


def expected_contract(source):
    """Materialize metadata from the pinned closure config, never from new curation."""
    roles = {}
    for role, input_key, filename in (
        ("TRAIN", "s7c_train", "ft_train.csv"),
        ("VALIDATION", "s7c_validation", "ft_validation.csv"),
        ("REF", "s7b_ref", "ref.csv"),
        ("EVAL", "s7b_eval", "eval.csv"),
    ):
        frozen = source["frozen_inputs"][input_key]
        prefix = role.lower()
        counts = source["expected_counts"]
        roles[role] = {
            "path": f"data/processed/{filename}",
            "sha256": frozen["sha256"],
            "allowed": ALLOWED_USES[role],
            "available_during_generator_development": role in DEVELOPMENT_ROLES,
            "counts": {
                "identities": counts[f"n_{prefix}"],
                "cores": counts[f"n_{prefix}_cores"],
                "clusters": counts[f"n_{prefix}_clusters"],
            },
            "identity_set_hash": frozen["identity_set_hash"],
            "cluster_set_hash": frozen["cluster_set_hash"],
        }
        if role in ("TRAIN", "VALIDATION"):
            roles[role]["counts"]["targets"] = counts[f"n_{prefix}_targets"]
            roles[role]["partition"] = "FT"
            roles[role]["ft_split"] = role
    roles["TRAIN_TEXT"] = {
        "path": "data/processed/corpus_final.txt",
        "sha256": TRAIN_TEXT_SHA256,
        "allowed": ALLOWED_USES["TRAIN_TEXT"],
        "available_during_generator_development": True,
        "counts": {"lines": 669, "unique_cores": 669},
        "source_role": "TRAIN",
        "order": "first_occurrence_in_frozen_ft_train_csv",
        "authoritative_rnagenesis_fitting_input": True,
    }
    return {
        "schema_version": 1,
        "contract_id": "rnagenesis_corrected_669_core_m0",
        "corpus_commit": CORPUS_COMMIT,
        "corpus_commit_subject": "Complete corrective corpus revision for RNA modelling alphabet gate",
        "corpus_commit_supersedes": "095236dfb13d1d3b13f11bbb34c2e48319c10184",
        "provenance": {
            "source_config": SOURCE_CONFIG,
            "source_config_sha256": SOURCE_CONFIG_SHA256,
            "s7d_repository_head_baseline": source["repository_head_baseline"],
            "baseline_is_not_corpus_closure": True,
            "corpus_manifest_path": "data/processed/corpus_manifest.json",
            "corpus_manifest_sha256": "08da8d5e44413ea9ab57c128dbe4ef7986dab7a2bfa794cfef6fb4724577565f",
        },
        "roles": roles,
        "sequence_policy": {
            "column": "sequence_core",
            "training_grain": "one_distinct_TRAIN_sequence_core",
            "validation_grain": "one_distinct_VALIDATION_sequence_core",
            "alphabet_regex": "^[ACGU]+$",
            "silent_t_to_u": False,
            "whitespace_or_case_normalisation": False,
            "new_length_filter_or_truncation": False,
            "chemistry_metadata_is_not_a_model_input": True,
        },
        "split_policy": {
            "immutable_roles": True,
            "rerun_curation": False,
            "random_resplit": False,
            "merge_validation_into_train": False,
            "require_zero_core_cluster_identity_overlap": True,
            "all_role_leakage_evidence": "corrective_S7D_closure_not_recomputed_at_M0",
        },
        "length_regime": {
            "source": "frozen_s6_two_component_gmm",
            "refit": False,
            "counts_source": SOURCE_CONFIG + "#expected_length_regime_cores",
            "TRAIN": source["expected_length_regime_cores"]["TRAIN"],
            "VALIDATION": source["expected_length_regime_cores"]["VALIDATION"],
        },
        "access_policy": {
            "development_read_allowlist": ["TRAIN", "TRAIN_TEXT", "VALIDATION"],
            "development_transfer_allowlist": ["TRAIN", "TRAIN_TEXT", "VALIDATION"],
            "ref_requires_generator_freeze": True,
            "eval_locked": True,
            "eval_unlock_requires": ["M9C_complete_pipeline_freeze", "explicit_EVAL_unlock_record"],
            "restricted_hashes_are_metadata_only": True,
            "do_not_transfer_combined_corpus_or_interim_curation_data": True,
        },
    }


def load_contract(repo_root, contract_path):
    source_bytes = (repo_root / SOURCE_CONFIG).read_bytes()
    require(digest(source_bytes) == SOURCE_CONFIG_SHA256, "Frozen S7D metadata changed")
    recorded = subprocess.check_output(
        ["git", "-C", str(repo_root), "show", f"{CORPUS_COMMIT}:{SOURCE_CONFIG}"],
        stderr=subprocess.PIPE,
    )
    require(digest(recorded) == SOURCE_CONFIG_SHA256, "Closure commit metadata mismatch")
    ancestor = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", CORPUS_COMMIT, "HEAD"],
        capture_output=True,
    )
    require(ancestor.returncode == 0, "Corrected closure is not an ancestor of HEAD")
    contract = parse_json(contract_path.read_bytes())
    expected = expected_contract(parse_json(source_bytes))
    require(contract == expected, "Contract differs from the pinned corrected corpus or role policy")
    return contract


def read_authorized(contract, role, purpose, data_dir):
    """Deny restricted roles/purposes before resolving or opening any data path.

    The caller must first obtain the contract with load_contract. REF calibration
    and EVAL unlocking need separate, later-stage entry points; this M0 helper
    deliberately has no unlock switch.
    """
    require(role in DEVELOPMENT_ROLES, f"{role}: prohibited during generator development")
    require(purpose in ALLOWED_USES[role], f"{role}: purpose {purpose!r} is prohibited")
    spec = contract["roles"][role]
    require(spec["allowed"] == ALLOWED_USES[role], f"{role}: invalid role permissions")
    require(spec["available_during_generator_development"] is True, f"{role}: locked")
    path = data_dir / Path(spec["path"]).name
    require(not path.is_symlink(), f"{role}: input symlinks are prohibited")
    raw = path.read_bytes()
    require(digest(raw) == spec["sha256"], f"{role}: SHA256 mismatch; do not rewrite the corpus")
    return raw


def check_development_directory(contract, data_dir):
    """Inspect directory entries only; do not read unexpected/restricted files.

    This proves isolation of the named input directory, not an entire server.
    """
    allowed = {Path(contract["roles"][r]["path"]).name for r in DEVELOPMENT_ROLES}
    entries = list(data_dir.iterdir())
    require({p.name for p in entries} == allowed,
            "Development data directory must contain exactly TRAIN CSV, TRAIN text and VALIDATION CSV")
    require(all(p.is_file() and not p.is_symlink() for p in entries),
            "Development inputs must be regular files without symlinks")


def check_csv(raw, role, spec):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""))
    required = {"scientific_identity_id", "sequence_core", "sequence_core_sha256",
                "sequence_length_core", "cluster_id", "canonical_target_name", "partition", "ft_split"}
    require(required <= set(reader.fieldnames or []), f"{role}: missing metadata columns")
    rows = list(reader)
    require(bool(rows), f"{role}: empty CSV")
    for number, row in enumerate(rows, 2):
        require(all(row.get(key) for key in required), f"{role}: incomplete row {number}")
        core = row["sequence_core"]
        require(re.fullmatch(r"[ACGU]+", core) is not None, f"{role}: invalid alphabet at row {number}")
        require(row["partition"] == "FT" and row["ft_split"] == role,
                f"{role}: role assignment mismatch at row {number}")
        require(row["sequence_core_sha256"] == digest(core.encode()), f"{role}: core digest mismatch at row {number}")
        require(int(row["sequence_length_core"]) == len(core), f"{role}: length mismatch at row {number}")
    counts = {
        "identities": len({r["scientific_identity_id"] for r in rows}),
        "cores": len({r["sequence_core"] for r in rows}),
        "clusters": len({r["cluster_id"] for r in rows}),
        "targets": len({r["canonical_target_name"] for r in rows}),
    }
    require(counts == spec["counts"], f"{role}: count mismatch")
    require(len(rows) == counts["identities"], f"{role}: repeated scientific identity")
    identities = "\n".join(
        f'{r["scientific_identity_id"]}\t{r["cluster_id"]}\t{r["sequence_core_sha256"]}'
        for r in sorted(rows, key=lambda row: row["scientific_identity_id"])
    )
    clusters = "\n".join(sorted({r["cluster_id"] for r in rows}))
    require(digest(identities.encode()) == spec["identity_set_hash"], f"{role}: identity freeze mismatch")
    require(digest(clusters.encode()) == spec["cluster_set_hash"], f"{role}: cluster freeze mismatch")
    return rows


def check_train_text(raw, train_rows, spec):
    lines = raw.decode("utf-8").splitlines()
    require(len(lines) == spec["counts"]["lines"], "TRAIN_TEXT: wrong line count")
    require(len(set(lines)) == spec["counts"]["unique_cores"], "TRAIN_TEXT: repeated cores")
    require(all(re.fullmatch(r"[ACGU]+", s) for s in lines), "TRAIN_TEXT: invalid alphabet")
    expected = list(dict.fromkeys(r["sequence_core"] for r in train_rows))
    require(lines == expected, "TRAIN_TEXT: does not match TRAIN cores in frozen order")
    return lines


def check_overlap(train_rows, validation_rows):
    result = {}
    for column in ("sequence_core", "cluster_id", "scientific_identity_id"):
        overlap = {r[column] for r in train_rows} & {r[column] for r in validation_rows}
        result[column] = len(overlap)
        require(not overlap, f"TRAIN/VALIDATION overlap in {column}")
    return result


def length_summary(cores):
    lengths = list(map(len, cores))
    return {"grain": "distinct_sequence_core", "min": min(lengths), "max": max(lengths),
            "median": statistics.median(lengths), "mean": statistics.mean(lengths),
            "histogram": dict(sorted(Counter(lengths).items()))}


def verify(contract, data_dir, profile):
    require(profile in ("local-corpus", "development"), "Unknown verification profile")
    if profile == "development":
        check_development_directory(contract, data_dir)
    train_raw = read_authorized(contract, "TRAIN", "fit", data_dir)
    text_raw = read_authorized(contract, "TRAIN_TEXT", "fit", data_dir)
    validation_raw = read_authorized(contract, "VALIDATION", "development_evaluate", data_dir)
    train = check_csv(train_raw, "TRAIN", contract["roles"]["TRAIN"])
    validation = check_csv(validation_raw, "VALIDATION", contract["roles"]["VALIDATION"])
    cores = check_train_text(text_raw, train, contract["roles"]["TRAIN_TEXT"])
    overlap = check_overlap(train, validation)
    return {
        "status": "PASS", "scope": "M0_local_data_contract_only", "profile": profile,
        "corpus_commit": contract["corpus_commit"],
        "verified_hashes": {r: contract["roles"][r]["sha256"] for r in sorted(DEVELOPMENT_ROLES)},
        "counts": {r: contract["roles"][r]["counts"] for r in sorted(DEVELOPMENT_ROLES)},
        "train_validation_overlap": overlap,
        "alphabet": "ACGU_only", "train_order_matches_frozen_csv": True,
        "lengths": {"TRAIN": length_summary(cores),
                    "VALIDATION": length_summary(set(r["sequence_core"] for r in validation))},
        "restricted_role_files_opened": [],
        "ref_eval_hashes": "recorded_metadata_only_not_rehashed",
        "all_role_leakage": "inherited_from_corrective_closure_not_recomputed",
        "input_directory_isolation": "PASS" if profile == "development" else "NOT_CHECKED_local_curation_store",
        "entire_h200_training_workspace_isolation": "NOT_CHECKED",
        "m0_complete": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--profile", choices=("local-corpus", "development"), default="local-corpus")
    args = parser.parse_args()
    try:
        repo_root = args.repo_root.resolve()
        contract_path = args.contract or repo_root / CONTRACT_PATH
        contract = load_contract(repo_root, contract_path)
        data_dir = args.data_dir or repo_root / "data/processed"
        result = verify(contract, data_dir, args.profile)
        result["contract_sha256"] = digest(contract_path.read_bytes())
        print(json.dumps(result, indent=2))
    except (ContractError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        # Do not echo data-bearing decoder/parser exceptions or raw subprocess output.
        message = str(exc) if isinstance(exc, ContractError) else type(exc).__name__
        print(json.dumps({"status": "FAIL", "error": message}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
