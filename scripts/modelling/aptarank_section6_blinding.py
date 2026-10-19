#!/usr/bin/env python3
"""Section 6 blinding, upload bytes, and production count gates.

The caller supplies one 32-byte secret. Candidate ids and upload order are
domain-separated HMACs under that same secret. This module does not accept
a second ordering key, does not embed a production secret, does not write
under ``results/``, and does not open TRAIN, VALIDATION, REF, or EVAL.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
import re
import sys

import aptarank_section6_uniform as uniform

PACKAGE_ID = "SECTION6-METHOD"
SCHEMA_VERSION = "aptarank-section6-method-v1"
STATUS = "SECTION6_METHOD_FROZEN_SYNTHETIC_ONLY_PRODUCTION_UNAUTHORIZED"
CONTRACT_RELATIVE = "config/modelling/aptarank_section6_method_contract.json"
CONTRACT_SHA256 = "50652795985ddec6d93925715c7a6a50462a215ed830c54ccd7faf9a7c84e555"
PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_5.md"
PLAN_SHA256 = "ebb0e66dd35c7ed20abecacf710ea7a90dd0e2737ba1973af66e8f0753e22c9d"
IO_SPEC_RELATIVE = "config/modelling/aptarank_io_spec.json"
IO_SPEC_SHA256 = "46ba6c8be873dad4c086e9f6b889b51702ba31212fa502d00f26e267a22da732"
IO_MODULE_RELATIVE = "scripts/modelling/aptarank_io_preflight.py"
IO_MODULE_SHA256 = "eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01"
ID_DOMAIN = "aptarank-section6-id-v1"
ORDER_DOMAIN = "aptarank-section6-order-v1"
ID_PREFIX = "cand_"
KEY_LENGTH = 32
TRUNCATION_BYTES = 16
ATTEMPT3_REFERENCE_SHA256 = "5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6"
PRODUCTION_REAL_MEMBERSHIPS = 154
PRODUCTION_CONTROLS = 154
PRODUCTION_PAIRS = 154
PRODUCTION_UPLOAD_SEQUENCES = 308
PRODUCTION_CLUSTERS = 79
RUN_SHEET_KEYS = (
    "reference_upload_sha256",
    "reference_publication_attempt",
    "preset",
    "seed",
    "candidate_shuffles",
    "ensemble_samples",
    "protein_target",
    "expected_compatibility_token",
)
PRIVATE_KEY_FIELDS = (
    "candidate_id",
    "class_label",
    "pair_id",
    "parent_core_id",
    "cluster_id",
    "length",
    "source_digest",
)
CLASS_EVAL_CORE = "eval_core"
CLASS_PAIRED_UNIFORM = "paired_uniform_shuffle"
CLASS_LABELS = (CLASS_EVAL_CORE, CLASS_PAIRED_UNIFORM)
CANDIDATE_ID_RE = re.compile(r"^cand_[0-9a-f]{32}\Z")
PRIVATE_KEY_MARKERS = ("package_id", "schema_version", "restricted", "candidates")
Section6Error = uniform.Section6Error
_ARP1 = None


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=False).encode("utf-8") + b"\n"


def _read_regular(relative):
    path = os.path.join(repo_root(), relative)
    if os.path.islink(path) or not os.path.isfile(path):
        raise Section6Error("pin_mismatch", relative + " is not a regular pinned file")
    with open(path, "rb") as handle:
        return handle.read()


def load_arp1():
    """Load the pinned ARP-1 validator. Its hash and token behavior stay unchanged."""
    global _ARP1
    if _ARP1 is not None:
        return _ARP1
    payload = _read_regular(IO_MODULE_RELATIVE)
    if sha256_bytes(payload) != IO_MODULE_SHA256:
        raise Section6Error("pin_mismatch", "the ARP-1 module digest changed")
    spec_payload = _read_regular(IO_SPEC_RELATIVE)
    if sha256_bytes(spec_payload) != IO_SPEC_SHA256:
        raise Section6Error("pin_mismatch", "the ARP-1 specification digest changed")
    spec = importlib.util.spec_from_file_location(
        "aptarank_io_preflight_section6",
        os.path.join(repo_root(), IO_MODULE_RELATIVE),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.CANDIDATE_COLUMNS != ("id", "sequence"):
        raise Section6Error("validator_drift", "ARP-1 candidate columns changed")
    if module.COMPATIBILITY_TOKENS != ("not evaluated",):
        raise Section6Error("validator_drift", "ARP-1 target-free compatibility tokens changed")
    if module.SHUFFLE_TOKENS != ("pass", "fail"):
        raise Section6Error("validator_drift", "ARP-1 target-free shuffle tokens changed")
    _ARP1 = module
    return module


def load_pinned_contract():
    payload = _read_regular(CONTRACT_RELATIVE)
    if sha256_bytes(payload) != CONTRACT_SHA256:
        raise Section6Error("pin_mismatch", "the Section 6 contract digest changed")
    plan = _read_regular(PLAN_RELATIVE)
    if sha256_bytes(plan) != PLAN_SHA256:
        raise Section6Error("pin_mismatch", "the v3.5 plan digest changed")
    document = json.loads(payload.decode("utf-8"))
    if document.get("package_id") != PACKAGE_ID or document.get("schema_version") != SCHEMA_VERSION:
        raise Section6Error("spec_invalid", "the Section 6 contract identity changed")
    if document.get("governing_plan", {}).get("sha256") != PLAN_SHA256:
        raise Section6Error("spec_invalid", "the Section 6 contract does not cite v3.5")
    if document.get("historical_m9b_tier1_draft", {}).get("modified_by_section6") is not False:
        raise Section6Error("spec_invalid", "the historical Tier 1 draft pin changed")
    load_arp1()
    return document


def require_secret(secret):
    if secret is None:
        raise Section6Error("secret_missing", "a caller-supplied 32-byte secret is required")
    if type(secret) is not bytes or len(secret) != KEY_LENGTH:
        raise Section6Error("secret_malformed", "the blinding secret must be exactly 32 bytes")
    return secret


def _hmac(domain, sequence, secret):
    payload = uniform.length_delimited_bytes([domain, sequence])
    return hmac.new(secret, payload, hashlib.sha256).digest()


def candidate_id(sequence, secret):
    """HMAC-SHA-256 truncated to 16 bytes, as ``cand_`` plus 32 lowercase hex characters."""
    require_secret(secret)
    uniform.core_digest(sequence)
    return ID_PREFIX + _hmac(ID_DOMAIN, sequence, secret)[:TRUNCATION_BYTES].hex()


def order_key(sequence, secret):
    """Domain-separated ordering HMAC under the same caller-supplied secret."""
    require_secret(secret)
    uniform.core_digest(sequence)
    return _hmac(ORDER_DOMAIN, sequence, secret)


def reject_duplicate_ids(pairs):
    """Fail closed when two sequences share a truncated candidate id."""
    owners = {}
    for sequence, identifier in pairs:
        previous = owners.get(identifier)
        if previous is not None and previous != sequence:
            raise Section6Error(
                "opaque_id_collision",
                "a truncated candidate id collision fails closed and the id is not lengthened",
            )
        owners[identifier] = sequence
    return owners


def reject_duplicate_order_keys(pairs):
    """Fail closed when two sequences share an ordering digest."""
    owners = {}
    for sequence, key in pairs:
        previous = owners.get(key)
        if previous is not None and previous != sequence:
            raise Section6Error(
                "order_key_collision",
                "an upload-order digest collision fails closed",
            )
        owners[key] = sequence
    return owners


def run_sheet_template():
    """Target-free Section 6 run sheet. It contains no candidate sequence."""
    return {
        "reference_upload_sha256": ATTEMPT3_REFERENCE_SHA256,
        "reference_publication_attempt": 3,
        "preset": "Standard",
        "seed": 42,
        "candidate_shuffles": 20,
        "ensemble_samples": 100,
        "protein_target": None,
        "expected_compatibility_token": "not evaluated",
    }


def check_run_sheet(document):
    """Fail closed on any discrepancy from the frozen target-free template."""
    expected = run_sheet_template()
    if type(document) is not dict or set(document) != set(RUN_SHEET_KEYS):
        raise Section6Error(
            "run_sheet_discrepancy",
            "the run sheet keys differ from the target-free template. Reviewed rerun lineage is required.",
            rerun_lineage_required=True,
        )
    for key in RUN_SHEET_KEYS:
        if key not in document or document[key] != expected[key] or type(document[key]) is not type(expected[key]):
            raise Section6Error(
                "run_sheet_discrepancy",
                "the run sheet field %s differs from the target-free template. Reviewed rerun lineage is required."
                % key,
                rerun_lineage_required=True,
            )
    return expected


def production_count_report(real_count, control_count, pair_count, unique_sequences, cluster_count):
    return {
        "real_memberships": real_count,
        "controls": control_count,
        "complete_pairs": pair_count,
        "unique_upload_sequences": unique_sequences,
        "pre_rejection_clusters": cluster_count,
    }


def assert_production_counts(report):
    expected = {
        "real_memberships": PRODUCTION_REAL_MEMBERSHIPS,
        "controls": PRODUCTION_CONTROLS,
        "complete_pairs": PRODUCTION_PAIRS,
        "unique_upload_sequences": PRODUCTION_UPLOAD_SEQUENCES,
        "pre_rejection_clusters": PRODUCTION_CLUSTERS,
    }
    if report != expected:
        raise Section6Error(
            "production_count_mismatch",
            "the synthetic production gate expected 154 real memberships, 154 controls, "
            "154 complete pairs, 308 unique upload sequences, and 79 pre-rejection clusters",
        )
    return expected


def _candidate_rows(parents, controls, secret):
    rows = []
    id_pairs = []
    order_pairs = []
    for parent, control in zip(parents, controls):
        pair_id = "pair_" + parent["source_digest"]
        members = (
            (CLASS_EVAL_CORE, parent["sequence"], parent["source_digest"]),
            (CLASS_PAIRED_UNIFORM, control["sequence"], control["source_digest"]),
        )
        for class_label, sequence, digest in members:
            identifier = candidate_id(sequence, secret)
            key = order_key(sequence, secret)
            id_pairs.append((sequence, identifier))
            order_pairs.append((sequence, key))
            rows.append(
                {
                    "sequence": sequence,
                    "order_key": key,
                    "private": {
                        "candidate_id": identifier,
                        "class_label": class_label,
                        "pair_id": pair_id,
                        "parent_core_id": parent["parent_core_id"],
                        "cluster_id": parent["cluster_id"],
                        "length": len(sequence),
                        "source_digest": digest,
                    },
                }
            )
    reject_duplicate_ids(id_pairs)
    reject_duplicate_order_keys(order_pairs)
    rows.sort(key=lambda row: row["order_key"])
    return rows


def _upload_bytes(rows):
    lines = ["id,sequence"]
    for row in rows:
        identifier = row["private"]["candidate_id"]
        sequence = row["sequence"]
        if "," in identifier or "," in sequence or "\n" in identifier or "\n" in sequence:
            raise Section6Error("upload_encoding_invalid", "an upload field contains a delimiter")
        lines.append(identifier + "," + sequence)
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    arp1 = load_arp1()
    errors = arp1.ErrorList()
    parsed = arp1.parse_csv_rows(payload, arp1.CANDIDATE_COLUMNS, errors, "candidate upload")
    if parsed is not None:
        arp1._check_candidate_rows(parsed, errors)
    if errors.items:
        raise Section6Error(errors.items[0]["code"], errors.items[0]["detail"])
    if [row["id"] for row in parsed] != [row["private"]["candidate_id"] for row in rows]:
        raise Section6Error("upload_order_mismatch", "the validated upload order changed")
    return payload, parsed


def _assert_secret_absent(secret, blobs):
    forbidden = (secret, secret.hex().encode("ascii"))
    for payload in blobs:
        for item in forbidden:
            if item in payload:
                raise Section6Error("secret_embedded", "the blinding secret appeared in an output")


def prepare_section6_upload(parents, inventory_digests, secret, *, enforce_production_counts=False):
    """Build blinded upload bytes and a restricted private key from in-memory parents.

    ``enforce_production_counts`` exercises the 154/154/154/308/79 gate. This
    function still returns synthetic bytes only and does not authorize production.
    """
    if type(enforce_production_counts) is not bool:
        raise Section6Error("gate_flag_invalid", "the production-count flag must be a boolean")
    key = require_secret(secret)
    load_pinned_contract()
    ordered_parents, controls = uniform.generate_uniform_controls(parents, inventory_digests)
    rows = _candidate_rows(ordered_parents, controls, key)
    sequences = [row["sequence"] for row in rows]
    if len(sequences) != len(set(sequences)):
        raise Section6Error("duplicate_upload_sequence", "upload sequences are not globally unique")
    upload, parsed = _upload_bytes(rows)
    if any(set(row) != {"id", "sequence"} for row in parsed):
        raise Section6Error("upload_field_forbidden", "the upload carries a field other than id and sequence")
    private_rows = [row["private"] for row in rows]
    private_rows_stored = sorted(private_rows, key=lambda row: (row["pair_id"], row["class_label"]))
    for row in private_rows_stored:
        if tuple(row) != PRIVATE_KEY_FIELDS:
            raise Section6Error("private_key_field_invalid", "the private key fields changed")
    private_document = {
        "package_id": PACKAGE_ID,
        "schema_version": SCHEMA_VERSION,
        "restricted": True,
        "candidates": private_rows_stored,
    }
    private_bytes = canonical_json_bytes(private_document)
    pairs = {row["pair_id"] for row in private_rows_stored}
    clusters = {row["cluster_id"] for row in private_rows_stored}
    classes = {}
    for row in private_rows_stored:
        classes[row["class_label"]] = classes.get(row["class_label"], 0) + 1
    report = production_count_report(
        classes.get(CLASS_EVAL_CORE, 0),
        classes.get(CLASS_PAIRED_UNIFORM, 0),
        len(pairs),
        len(set(sequences)),
        len(clusters),
    )
    gate = "not_applied"
    if enforce_production_counts:
        assert_production_counts(report)
        gate = "passed_synthetic_fixture"
    manifest = {
        "package_id": PACKAGE_ID,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "synthetic": True,
        "production_authorized": False,
        "production_secret_embedded": False,
        "production_upload_instantiated": False,
        "results_written": False,
        "aptarank_executed": False,
        "scientific_result": False,
        "sequences_embedded": False,
        "candidate_ids_embedded": False,
        "secret_embedded": False,
        "production_count_gate": gate,
        "counts": report,
        "candidate_upload_sha256": sha256_bytes(upload),
        "private_key_sha256": sha256_bytes(private_bytes),
        "uniform_domain": uniform.UNIFORM_DOMAIN,
        "id_domain": ID_DOMAIN,
        "order_domain": ORDER_DOMAIN,
        "master_seed": uniform.MASTER_SEED,
        "contract_sha256": CONTRACT_SHA256,
    }
    manifest_bytes = canonical_json_bytes(manifest)
    _assert_secret_absent(key, (upload, private_bytes, manifest_bytes))
    if b"cand_" in manifest_bytes:
        raise Section6Error("manifest_identifier_embedded", "the manifest contains a candidate id")
    return {
        "candidate_upload": upload,
        "private_key": private_document,
        "private_key_bytes": private_bytes,
        "manifest": manifest,
        "manifest_bytes": manifest_bytes,
        "parents_in_draw_order": [
            {key: parent[key] for key in ("parent_core_id", "cluster_id", "source_digest", "length")}
            for parent in ordered_parents
        ],
        "controls": controls,
    }


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        raise Section6Error("production_runner_refused", "Section 6 method freeze has no production runner")
    load_pinned_contract()
    sys.stdout.write(STATUS + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Section6Error as exc:
        sys.stderr.write(exc.code + ": " + exc.detail + "\n")
        raise SystemExit(1)
