#!/usr/bin/env python3
"""Inactive M8 raw-pool assembly.

Assembly is CPU-only and has its own authorisation list. Existing generation
files do not make it runnable. While the checked-in configuration is inactive,
``--authorisation-id`` refuses before any manifest, raw file, environment,
Git, GPU, or output inspection.

An authorised assembly accepts exactly two sealed arm manifests for one
condition, re-checks every bound hash, and writes a canonical ledger sorted
only by master attempt index. It does not parse, clean, filter, classify,
deduplicate, or compute a metric.

Historical ``m8-arm-manifest-1`` arms remain valid when they record exclusive
use and zero compute processes. ``m8-arm-manifest-2`` arms must record the
authorised sharing policy and the single pre-consumption compute-app
observation. Assembly does not probe the GPU again. A positive pre-existing
count is accepted only for ``shared_allowed`` when that evidence agrees and
the recorded free-memory threshold passed. A selected-GPU row whose PID is
empty, non-decimal, zero, negative, ``[N/A]``, or ``[Not Found]`` is refused
by the shared evidence validator. An indeterminate row for another GPU is not
counted. Pre-existing processes are not treated as generated-model processes.
"""

from __future__ import annotations

import os
import sys

import m8_generation as generation
import m8_schedule as schedule

M8Error = generation.M8Error
MANIFEST_NAME = "m8_assembly_manifest.json"
LEDGER_NAME = "m8_combined_raw_attempt_ledger.jsonl"
ASSEMBLY_ENTRY_KEYS = (
    "activation_status",
    "authorisation_id",
    "condition_id",
    "consumed",
    "output_directory",
    "reuse_permitted",
    "run_root",
    "single_use",
    "sources",
)
SOURCE_KEYS = ("block", "byte_count", "path", "sha256")
ARM_MANIFEST_KEYS = (
    "asset_verification",
    "authorization",
    "block",
    "cleaner_invoked",
    "completion_state",
    "condition_id",
    "d1_training_seed",
    "environment",
    "filtering_performed",
    "gpu",
    "invocation_ledger",
    "later_evaluation_required",
    "manifest_schema_version",
    "model_assets",
    "raw_attempt_count",
    "raw_attempt_ledger_byte_count",
    "raw_attempt_ledger_sha256",
    "raw_output_hashes",
    "replacement_or_replenishment_performed",
    "repository_identity",
    "reuse_prohibited",
    "run_id",
    "sampler",
    "schedule",
    "schema_version",
    "selected_set_evidence",
    "sequence_access",
    "storage",
    "timestamps",
)
INVOCATION_ROW_KEYS = (
    "batch_num",
    "batch_size",
    "generation_seed",
    "invocation_index",
    "kind",
    "line_count",
    "relative_path",
    "sha256",
)
AUTHORIZATION_KEYS = (
    "active_configuration_raw_sha256",
    "active_configuration_sha256",
    "authorisation_id",
    "authorization_commit",
    "authorization_parent_commit",
    "executing_implementation_commit",
    "implementation_file_hashes",
    "origin_main",
    "reuse_permitted",
    "single_use",
)
FORBIDDEN_RECORD_KEYS = frozenset(
    [
        "accepted",
        "biological",
        "cleaned_sequence",
        "cluster",
        "deduplicated",
        "filtered",
        "invalid",
        "mfe",
        "parsed",
        "rejected",
        "valid",
        "validity",
    ]
)


def _load_json_bytes(blob, detail):
    if not isinstance(blob, (bytes, bytearray)):
        raise M8Error("assembly_invalid", detail, "assembly")
    try:
        import json

        parsed = json.loads(bytes(blob).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise M8Error("assembly_invalid", detail, "assembly")
    if not isinstance(parsed, dict):
        raise M8Error("assembly_invalid", detail, "assembly")
    return parsed


def _signature(measured):
    return (
        measured.st_mode,
        measured.st_size,
        measured.st_nlink,
        getattr(measured, "st_ino", None),
        getattr(measured, "st_dev", None),
        getattr(measured, "st_mtime_ns", None),
    )


def assert_arm_manifest_path(path, run_root):
    """The manifest path is fixed. Its parent directory is not taken from an arbitrary source path."""
    if not isinstance(path, str) or not os.path.isabs(path) or os.path.normpath(path) != path:
        raise M8Error("assembly_invalid", "an arm manifest path is not a normalised absolute path", "assembly")
    if os.path.basename(path) != generation.MANIFEST_NAME:
        raise M8Error("assembly_invalid", "an arm source is not the M8 arm manifest", "assembly")
    arm_directory = os.path.dirname(path)
    if os.path.dirname(arm_directory) != run_root:
        raise M8Error("assembly_invalid", "an arm manifest is not a direct child of the canonical run root", "assembly")
    generation.assert_canonical_output_directory(arm_directory, run_root, os.path.basename(arm_directory))
    return arm_directory


def _read_exact(path, expected_bytes, expected_hash, arm_directory, deps):
    generation.assert_not_prohibited(path, arm_directory, role="sealed_arm")
    if os.path.normpath(path) != path:
        raise M8Error("assembly_invalid", "a bound path is not normalised", "assembly")
    generation.assert_resolved_inside_directory(path, arm_directory, deps)
    before = deps.lstat(path)
    if generation.stat.S_ISLNK(before.st_mode) or not generation.stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise M8Error("assembly_invalid", "a bound file is not a single regular file", "assembly")
    if expected_bytes is not None and before.st_size != expected_bytes:
        raise M8Error("assembly_invalid", "a bound file does not match its byte count or SHA-256", "assembly")
    blob = deps.read_bytes(path)
    if not isinstance(blob, (bytes, bytearray)):
        raise M8Error("assembly_invalid", "a bound file was not read as bytes", "assembly")
    blob = bytes(blob)
    after = deps.lstat(path)
    if _signature(before) != _signature(after) or len(blob) != before.st_size:
        raise M8Error("assembly_invalid", "a bound file changed while it was read", "assembly")
    digest = generation.sha256_bytes(blob)
    if expected_hash is not None and digest != expected_hash:
        raise M8Error("assembly_invalid", "a bound file does not match its byte count or SHA-256", "assembly")
    if expected_bytes is not None and len(blob) != expected_bytes:
        raise M8Error("assembly_invalid", "a bound file does not match its byte count or SHA-256", "assembly")
    again = deps.read_bytes(path)
    if bytes(again) != blob or _signature(deps.lstat(path)) != _signature(after):
        raise M8Error("assembly_invalid", "a bound file changed while it was read", "assembly")
    return blob


def _expected_seed(condition_id, block):
    if condition_id == generation.CONDITION_B1:
        return None
    if condition_id == generation.CONDITION_D1:
        return 43 if block == "A" else 44
    raise M8Error("assembly_invalid", "the condition is not B1 or D1", "assembly")


def _ledger_records(blob):
    if not blob.endswith(b"\n"):
        raise M8Error("assembly_invalid", "a raw ledger does not end with a newline", "assembly")
    records = []
    for line in blob.split(b"\n")[:-1]:
        try:
            import json

            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise M8Error("assembly_invalid", "a raw ledger line is not JSON", "assembly")
        if not isinstance(record, dict) or tuple(sorted(record)) != generation.RAW_RECORD_KEYS:
            raise M8Error("assembly_invalid", "a raw ledger record field set drifted", "assembly")
        if FORBIDDEN_RECORD_KEYS.intersection(record):
            raise M8Error("assembly_invalid", "a raw record carries a classification field", "assembly")
        records.append(record)
    return records


def _require_sha256(value, detail):
    if not isinstance(value, str) or generation.SHA256_TEXT.fullmatch(value) is None:
        raise M8Error("assembly_invalid", detail, "assembly")
    return value


def _validate_selected_set_chain(manifest, condition_id, block):
    evidence = manifest.get("selected_set_evidence")
    assets = manifest.get("model_assets")
    if not isinstance(assets, dict) or tuple(sorted(assets)) != ("checkpoint_identity", "kind"):
        raise M8Error("assembly_invalid", "an arm model-asset block drifted", "assembly")
    expected_seed = _expected_seed(condition_id, block)
    pseudo = {"asset_kind": "b1" if condition_id == generation.CONDITION_B1 else "d1", "d1_training_seed": expected_seed}
    if assets.get("checkpoint_identity") != generation.checkpoint_identity(pseudo):
        raise M8Error("assembly_invalid", "an arm checkpoint identity drifted", "assembly")
    if condition_id == generation.CONDITION_B1:
        if evidence != {"applicable": False} or assets.get("kind") != "b1":
            raise M8Error("assembly_invalid", "B1 selected-set evidence is not the not-applicable record", "assembly")
        return True
    keys = (
        "applicable",
        "byte_count",
        "checkpoint_name",
        "epoch",
        "manifest_path",
        "manifest_sha256",
        "members_sha256",
        "seed",
        "selected_set_sha256",
        "update",
    )
    if not isinstance(evidence, dict) or tuple(sorted(evidence)) != keys or evidence.get("applicable") is not True:
        raise M8Error("assembly_invalid", "D1 selected-set evidence is incomplete", "assembly")
    pin = generation.D1_CHECKPOINTS[expected_seed]
    if assets.get("kind") != "d1":
        raise M8Error("assembly_invalid", "a D1 arm does not name the D1 asset kind", "assembly")
    if evidence.get("seed") != expected_seed or evidence.get("epoch") != 5 or evidence.get("update") != 105:
        raise M8Error("assembly_invalid", "a D1 block is not tied to epoch 5 update 105 of its seed", "assembly")
    if evidence.get("checkpoint_name") != pin["checkpoint_name"] or assets.get("checkpoint_identity") != pin["checkpoint_name"]:
        raise M8Error("assembly_invalid", "a D1 block is not tied to its selected checkpoint", "assembly")
    if evidence.get("members_sha256") != generation.d1_member_hashes(expected_seed):
        raise M8Error("assembly_invalid", "a D1 block member hash does not match the selected checkpoint", "assembly")
    if evidence.get("manifest_path") != generation.FINAL_SELECTION_MANIFEST_PATH:
        raise M8Error("assembly_invalid", "D1 selected-set evidence does not name the approved manifest", "assembly")
    if evidence.get("byte_count") != generation.FINAL_SELECTION_MANIFEST_BYTES:
        raise M8Error("assembly_invalid", "D1 selected-set evidence does not match the approved byte count", "assembly")
    if evidence.get("manifest_sha256") != generation.FINAL_SELECTION_MANIFEST_SHA256:
        raise M8Error("assembly_invalid", "D1 selected-set evidence does not match the approved manifest hash", "assembly")
    if evidence.get("selected_set_sha256") != generation.SELECTED_SET_SHA256:
        raise M8Error("assembly_invalid", "D1 selected-set evidence does not match the approved selected-set hash", "assembly")
    return True


def _arm_schema_version(manifest):
    version = manifest.get("manifest_schema_version")
    if version not in (generation.HISTORICAL_MANIFEST_SCHEMA_VERSION, generation.MANIFEST_SCHEMA_VERSION):
        raise M8Error("assembly_invalid", "an arm manifest schema drifted", "assembly")
    if manifest.get("schema_version") != version:
        raise M8Error("assembly_invalid", "an arm manifest schema drifted", "assembly")
    return version


def _require_nonnegative_int(value, detail):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise M8Error("assembly_invalid", detail, "assembly")
    return value


def _validate_arm_gpu(gpu, environment, schema_version):
    """Accept historical exclusive evidence, or a complete sharing-policy record.

    A historical manifest has no sharing-policy field. That absence is the
    exclusive contract and requires a zero compute-process count. It is not
    rewritten and it is not treated as shared use.
    """
    if not isinstance(gpu, dict) or gpu.get("logical_device") != generation.LOGICAL_DEVICE:
        raise M8Error("assembly_invalid", "arm GPU provenance drifted", "assembly")
    if schema_version == generation.HISTORICAL_MANIFEST_SCHEMA_VERSION:
        if tuple(sorted(gpu)) != generation.HISTORICAL_GPU_KEYS:
            raise M8Error("assembly_invalid", "arm GPU provenance drifted", "assembly")
        if isinstance(gpu.get("compute_processes"), bool) or gpu.get("compute_processes") != 0:
            raise M8Error("assembly_invalid", "an arm manifest records a compute process", "assembly")
        memory_keys = ("memory_free_bytes", "memory_total_bytes", "minimum_free_memory_bytes")
    elif schema_version == generation.MANIFEST_SCHEMA_VERSION:
        if tuple(sorted(gpu)) != generation.ARM_GPU_KEYS:
            raise M8Error("assembly_invalid", "arm GPU provenance drifted", "assembly")
        policy = gpu.get("gpu_sharing_policy")
        if policy not in generation.GPU_SHARING_POLICIES:
            raise M8Error("assembly_invalid", "an arm GPU sharing policy is missing or unknown", "assembly")
        count = gpu.get("preexisting_compute_process_count")
        observed = gpu.get("preexisting_compute_applications_observed")
        try:
            generation.assert_compute_app_evidence(
                gpu.get("compute_app_snapshot"),
                gpu.get("compute_app_snapshot_sha256"),
                gpu.get("uuid"),
                count,
                observed,
            )
        except M8Error as exc:
            raise M8Error("assembly_invalid", exc.detail, "assembly")
        if generation.TIMESTAMP_TEXT.fullmatch(str(gpu.get("observation_timestamp"))) is None:
            raise M8Error("assembly_invalid", "an arm GPU observation timestamp is not exact", "assembly")
        if policy == generation.GPU_SHARING_EXCLUSIVE and count != 0:
            raise M8Error("assembly_invalid", "an exclusive arm records a pre-existing compute process", "assembly")
        memory_keys = ("memory_free_bytes", "memory_total_bytes", "memory_used_bytes", "minimum_free_memory_bytes")
    else:
        raise M8Error("assembly_invalid", "an arm manifest schema drifted", "assembly")
    if isinstance(gpu.get("physical_gpu"), bool) or not isinstance(gpu.get("physical_gpu"), int) or gpu.get("physical_gpu") < 0:
        raise M8Error("assembly_invalid", "an arm GPU index is not a nonnegative integer", "assembly")
    if not isinstance(gpu.get("uuid"), str) or gpu.get("uuid") == "" or len(gpu.get("uuid")) > 80:
        raise M8Error("assembly_invalid", "an arm GPU identity is missing", "assembly")
    if not isinstance(gpu.get("pci_bus"), str) or generation.PCI_BUS_TEXT.fullmatch(gpu.get("pci_bus")) is None:
        raise M8Error("assembly_invalid", "an arm PCI identity is not exact", "assembly")
    if str(environment.get("cuda_visible_devices")) != str(gpu.get("physical_gpu")):
        raise M8Error("assembly_invalid", "an arm logical mapping does not match its GPU index", "assembly")
    for key in memory_keys:
        _require_nonnegative_int(gpu.get(key), "an arm GPU memory reading is not an integer byte count")
    if gpu["minimum_free_memory_bytes"] < 1 or gpu["memory_free_bytes"] > gpu["memory_total_bytes"]:
        raise M8Error("assembly_invalid", "an arm GPU memory relationship is impossible", "assembly")
    if "memory_used_bytes" in gpu and gpu["memory_used_bytes"] > gpu["memory_total_bytes"]:
        raise M8Error("assembly_invalid", "an arm GPU memory relationship is impossible", "assembly")
    if gpu["memory_free_bytes"] < gpu["minimum_free_memory_bytes"]:
        raise M8Error("assembly_invalid", "an arm GPU memory reading is below its threshold", "assembly")
    return True


def _check_arm(manifest, records, raw_by_relative, condition_id, block, built, arm_directory):
    if tuple(sorted(manifest)) != ARM_MANIFEST_KEYS:
        raise M8Error("assembly_invalid", "an arm manifest schema drifted", "assembly")
    schema_version = _arm_schema_version(manifest)
    if manifest.get("completion_state") != "consumed_successfully":
        raise M8Error("assembly_invalid", "an arm manifest is not a successful seal", "assembly")
    if manifest.get("condition_id") != condition_id or manifest.get("block") != block:
        raise M8Error("assembly_invalid", "an arm condition or block does not match the assembly", "assembly")
    expected_seed = _expected_seed(condition_id, block)
    if manifest.get("d1_training_seed") != expected_seed:
        raise M8Error("assembly_invalid", "a D1 seed or block pairing does not match", "assembly")
    if manifest.get("filtering_performed") is not False or manifest.get("cleaner_invoked") is not False:
        raise M8Error("assembly_invalid", "an arm manifest claims filtering or a cleaner", "assembly")
    if manifest.get("replacement_or_replenishment_performed") is not False or manifest.get("later_evaluation_required") is not True:
        raise M8Error("assembly_invalid", "an arm manifest claims replacement or skips later evaluation", "assembly")
    if manifest.get("reuse_prohibited") is not True:
        raise M8Error("assembly_invalid", "an arm manifest permits reuse", "assembly")
    if manifest.get("raw_attempt_count") != schedule.BLOCK_ATTEMPT_TOTAL or len(records) != schedule.BLOCK_ATTEMPT_TOTAL:
        raise M8Error("assembly_invalid", "an arm does not hold 15000 raw attempts", "assembly")
    assets = manifest.get("asset_verification")
    if not isinstance(assets, dict) or assets.get("before_equals_after") is not True or assets.get("before") != assets.get("after"):
        raise M8Error("assembly_invalid", "arm asset observations are not equal", "assembly")
    if assets.get("members_copied") is not False:
        raise M8Error("assembly_invalid", "an arm manifest copied checkpoint members", "assembly")
    environment = manifest.get("environment")
    environment_keys = (
        "child_interpreter",
        "controller_interpreter",
        "cuda_module_loading",
        "cuda_visible_devices",
        "interpreter_path",
        "interpreter_resolved_path",
        "interpreter_sha256",
        "ld_library_path_bound",
        "ld_library_path_passed",
        "ld_library_path_sha256",
        "library_versions",
        "offline_controls",
        "path",
    )
    if not isinstance(environment, dict) or tuple(sorted(environment)) != environment_keys:
        raise M8Error("assembly_invalid", "arm environment provenance drifted", "assembly")
    if environment.get("interpreter_path") != generation.PINNED_PYTHON:
        raise M8Error("assembly_invalid", "an arm interpreter path drifted", "assembly")
    if environment.get("interpreter_resolved_path") != generation.PINNED_RESOLVED_PYTHON:
        raise M8Error("assembly_invalid", "an arm resolved interpreter drifted", "assembly")
    if environment.get("interpreter_sha256") != generation.PINNED_INTERPRETER_SHA256:
        raise M8Error("assembly_invalid", "an arm interpreter hash drifted", "assembly")
    if environment.get("library_versions") != generation.ACCEPTED_RUNTIME_VERSIONS:
        raise M8Error("assembly_invalid", "an arm library version set drifted", "assembly")
    if environment.get("cuda_module_loading") != "LAZY" or environment.get("offline_controls") is not True:
        raise M8Error("assembly_invalid", "an arm offline or module-loading claim drifted", "assembly")
    if environment.get("path") != generation.FIXED_CHILD_PATH:
        raise M8Error("assembly_invalid", "an arm PATH claim is not the fixed child path", "assembly")
    try:
        generation.assert_controller_interpreter(environment.get("controller_interpreter"))
        generation.assert_child_interpreter(environment.get("child_interpreter"))
    except M8Error as exc:
        raise M8Error("assembly_invalid", exc.detail, "assembly")
    bound_library = environment.get("ld_library_path_bound")
    passed_library = environment.get("ld_library_path_passed")
    library_digest = environment.get("ld_library_path_sha256")
    if bound_library is True:
        if passed_library is not True:
            raise M8Error("assembly_invalid", "a bound library path was not passed to the child", "assembly")
        _require_sha256(library_digest, "a bound library path has no digest")
    elif bound_library is False and passed_library is False and library_digest is None:
        pass
    else:
        raise M8Error("assembly_invalid", "an arm library-path claim is contradictory", "assembly")
    _validate_arm_gpu(manifest.get("gpu"), environment, schema_version)
    storage = manifest.get("storage")
    if not isinstance(storage, dict) or tuple(sorted(storage)) != ("filesystem_free_bytes", "minimum_free_bytes", "run_root"):
        raise M8Error("assembly_invalid", "arm storage provenance drifted", "assembly")
    if storage.get("run_root") != os.path.dirname(arm_directory) or storage.get("run_root") != generation.RUN_ROOT:
        raise M8Error("assembly_invalid", "an arm storage root is not the bound run root", "assembly")
    for key in ("filesystem_free_bytes", "minimum_free_bytes"):
        if isinstance(storage.get(key), bool) or not isinstance(storage.get(key), int) or storage.get(key) < 0:
            raise M8Error("assembly_invalid", "an arm free-space reading is not an integer byte count", "assembly")
    if storage["minimum_free_bytes"] < 1 or storage["filesystem_free_bytes"] < storage["minimum_free_bytes"]:
        raise M8Error("assembly_invalid", "an arm free-space reading is below its threshold", "assembly")
    authorisation = manifest.get("authorization")
    if not isinstance(authorisation, dict) or tuple(sorted(authorisation)) != AUTHORIZATION_KEYS:
        raise M8Error("assembly_invalid", "arm authorisation provenance drifted", "assembly")
    if authorisation.get("single_use") is not True or authorisation.get("reuse_permitted") is not False:
        raise M8Error("assembly_invalid", "an arm authorisation is not single-use", "assembly")
    generation._sha40_text(authorisation.get("authorization_commit"), "an arm authorization commit is missing")
    generation._sha40_text(authorisation.get("authorization_parent_commit"), "an arm authorization parent is missing")
    generation._sha40_text(authorisation.get("executing_implementation_commit"), "an arm implementation commit is missing")
    generation.assert_implementation_file_hashes(authorisation.get("implementation_file_hashes"))
    _require_sha256(authorisation.get("active_configuration_sha256"), "an arm configuration identity is missing")
    _require_sha256(authorisation.get("active_configuration_raw_sha256"), "an arm configuration raw digest is missing")
    if authorisation.get("origin_main") != authorisation.get("authorization_commit"):
        raise M8Error("assembly_invalid", "an arm origin identity is not its authorization commit", "assembly")
    if manifest.get("run_id") != authorisation.get("authorisation_id"):
        raise M8Error("assembly_invalid", "an arm run id is not its authorisation id", "assembly")
    if os.path.basename(arm_directory) != manifest.get("run_id"):
        raise M8Error("assembly_invalid", "an arm directory is not the authorised run id", "assembly")
    if os.path.dirname(arm_directory) != generation.RUN_ROOT:
        raise M8Error("assembly_invalid", "an arm directory is not a direct child of the run root", "assembly")
    generation.reject_authorisation_id(authorisation.get("authorisation_id"))
    if manifest.get("repository_identity") != generation.runtime_repository_identity(authorisation.get("authorization_commit")):
        raise M8Error("assembly_invalid", "arm repository provenance is not the observed authorization commit", "assembly")
    if manifest.get("sampler") != generation.MANIFEST_SAMPLER:
        raise M8Error("assembly_invalid", "an arm sampler setting drifted", "assembly")
    if manifest.get("sequence_access") != generation.SEQUENCE_ACCESS_DENIAL:
        raise M8Error("assembly_invalid", "an arm sequence-access claim drifted", "assembly")
    timestamps = manifest.get("timestamps")
    if not isinstance(timestamps, dict) or tuple(sorted(timestamps)) != ("elapsed_seconds", "finished_at", "started_at"):
        raise M8Error("assembly_invalid", "an arm timestamp block drifted", "assembly")
    elapsed = timestamps.get("elapsed_seconds")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or elapsed < 0:
        raise M8Error("assembly_invalid", "an arm elapsed duration is negative", "assembly")
    if generation.TIMESTAMP_TEXT.fullmatch(str(timestamps.get("started_at"))) is None:
        raise M8Error("assembly_invalid", "an arm start timestamp is not exact", "assembly")
    if generation.TIMESTAMP_TEXT.fullmatch(str(timestamps.get("finished_at"))) is None:
        raise M8Error("assembly_invalid", "an arm finish timestamp is not exact", "assembly")
    if timestamps["finished_at"] < timestamps["started_at"]:
        raise M8Error("assembly_invalid", "an arm finish timestamp precedes its start", "assembly")
    _validate_selected_set_chain(manifest, condition_id, block)
    if tuple(sorted(assets)) != ("after", "before", "before_equals_after", "members_copied"):
        raise M8Error("assembly_invalid", "arm asset observations drifted", "assembly")
    expected_inventory = generation.expected_asset_inventory(condition_id, block)
    if assets.get("before") != expected_inventory or assets.get("after") != expected_inventory:
        raise M8Error("assembly_invalid", "arm asset roles or hashes are not the expected inventory", "assembly")
    schedule_block = manifest.get("schedule")
    schedule_keys = (
        "block_invocation_schedule_sha256",
        "empirical_histogram_sha256",
        "master_attempt_map_sha256",
        "paired_block_invocation_schedule_sha256",
        "quota_allocation_sha256",
        "source_length_vector_sha256",
    )
    hash_key = "block_{}_invocation_schedule_sha256".format(block.lower())
    if not isinstance(schedule_block, dict) or tuple(sorted(schedule_block)) != schedule_keys:
        raise M8Error("assembly_invalid", "an arm schedule block is missing", "assembly")
    other = "b" if block == "A" else "a"
    paired_key = "block_{}_invocation_schedule_sha256".format(other)
    if schedule_block.get("block_invocation_schedule_sha256") != schedule.EXPECTED_SCHEDULE_HASHES[hash_key]:
        raise M8Error("assembly_invalid", "an arm schedule hash is not the paired schedule", "assembly")
    if schedule_block.get("paired_block_invocation_schedule_sha256") != schedule.EXPECTED_SCHEDULE_HASHES[paired_key]:
        raise M8Error("assembly_invalid", "an arm paired-block schedule hash drifted", "assembly")
    if schedule_block.get("master_attempt_map_sha256") != schedule.EXPECTED_SCHEDULE_HASHES["master_attempt_map_sha256"]:
        raise M8Error("assembly_invalid", "an arm master-map hash drifted", "assembly")
    if schedule_block.get("source_length_vector_sha256") != schedule.LENGTH_VECTOR_SHA256:
        raise M8Error("assembly_invalid", "an arm length-vector hash drifted", "assembly")
    if schedule_block.get("empirical_histogram_sha256") != built["hashes"]["empirical_histogram_sha256"]:
        raise M8Error("assembly_invalid", "an arm histogram hash drifted", "assembly")
    if schedule_block.get("quota_allocation_sha256") != built["hashes"]["quota_allocation_sha256"]:
        raise M8Error("assembly_invalid", "an arm quota hash drifted", "assembly")
    invocations = built["invocations"][block]["invocations"]
    by_index = {}
    for row in manifest.get("invocation_ledger") or []:
        if not isinstance(row, dict) or tuple(sorted(row)) != INVOCATION_ROW_KEYS:
            raise M8Error("assembly_invalid", "an invocation ledger row drifted", "assembly")
        index = row["invocation_index"]
        if index in by_index:
            raise M8Error("assembly_invalid", "an invocation reference is duplicated", "assembly")
        by_index[index] = row
    expected_indexes = [item["invocation_index"] for item in invocations]
    if sorted(by_index) != expected_indexes:
        raise M8Error("assembly_invalid", "invocation references are missing or extra", "assembly")
    ordered_hashes = [by_index[index]["sha256"] for index in expected_indexes]
    if manifest.get("raw_output_hashes") != ordered_hashes:
        raise M8Error("assembly_invalid", "raw output hashes do not match the invocation ledger", "assembly")
    masters = {row["master_attempt_index"]: row for row in built["master_attempt_map"]["rows"] if row["block"] == block}
    located = {}
    for invocation in invocations:
        ledger_row = by_index[invocation["invocation_index"]]
        relative = generation.relative_raw_path(invocation)
        if ledger_row["relative_path"] != relative or ledger_row["generation_seed"] != invocation["generation_seed"]:
            raise M8Error("assembly_invalid", "an invocation ledger row does not match the schedule", "assembly")
        if ledger_row["batch_num"] != invocation["batch_num"] or ledger_row["batch_size"] != invocation["batch_size"]:
            raise M8Error("assembly_invalid", "an invocation ledger row does not match the schedule", "assembly")
        if ledger_row["line_count"] != invocation["line_count"] or ledger_row["kind"] != invocation["kind"]:
            raise M8Error("assembly_invalid", "an invocation ledger row does not match the schedule", "assembly")
        blob = raw_by_relative.get(relative)
        if blob is None or generation.sha256_bytes(blob) != ledger_row["sha256"]:
            raise M8Error("assembly_invalid", "a raw invocation hash does not match the manifest", "assembly")
        for offset, master in enumerate(invocation["master_attempt_indexes"]):
            located[master] = (invocation, offset, relative, ledger_row["sha256"])
    pseudo = {"asset_kind": "b1" if condition_id == generation.CONDITION_B1 else "d1", "d1_training_seed": expected_seed}
    expected_checkpoint = generation.checkpoint_identity(pseudo)
    if manifest.get("model_assets", {}).get("checkpoint_identity") != expected_checkpoint:
        raise M8Error("assembly_invalid", "an arm checkpoint identity drifted", "assembly")
    expected_kind = "b1" if condition_id == generation.CONDITION_B1 else "d1"
    if manifest.get("model_assets", {}).get("kind") != expected_kind:
        raise M8Error("assembly_invalid", "an arm model-asset kind drifted", "assembly")
    seen = []
    covered = {}
    for record in records:
        master = record["master_attempt_index"]
        if master not in masters or master not in located:
            raise M8Error("assembly_invalid", "a raw record master index is not in the schedule", "assembly")
        scheduled = masters[master]
        invocation, offset, relative, digest = located[master]
        if record["condition_id"] != condition_id or record["technical_block"] != block or scheduled["block"] != block:
            raise M8Error("assembly_invalid", "a raw record condition or block does not match its arm", "assembly")
        if record["d1_training_seed"] != expected_seed:
            raise M8Error("assembly_invalid", "a raw record seed does not match its block", "assembly")
        if record["schema_version"] != generation.RECORD_SCHEMA_VERSION:
            raise M8Error("assembly_invalid", "a raw record schema drifted", "assembly")
        if record["checkpoint_identity"] != expected_checkpoint:
            raise M8Error("assembly_invalid", "a raw record checkpoint identity drifted", "assembly")
        if record["requested_biological_length"] != scheduled["requested_biological_length"]:
            raise M8Error("assembly_invalid", "a raw record length does not match the schedule", "assembly")
        if record["max_seq_len"] != record["requested_biological_length"] + 1 or record["max_seq_len"] != invocation["max_seq_len"]:
            raise M8Error("assembly_invalid", "a raw record max_seq_len is not the requested length plus 1", "assembly")
        if record["invocation_index"] != invocation["invocation_index"] or record["generation_seed"] != invocation["generation_seed"]:
            raise M8Error("assembly_invalid", "a raw record invocation or seed does not match the schedule", "assembly")
        if record["line_index"] != offset:
            raise M8Error("assembly_invalid", "a raw record line index does not match the schedule", "assembly")
        if record["batch_number"] != offset // invocation["batch_size"] or record["within_batch_position"] != offset % invocation["batch_size"]:
            raise M8Error("assembly_invalid", "a raw record batch position does not match the schedule", "assembly")
        expected_id = "m8:{}:master:{:05d}".format(condition_id, master)
        if record["record_id"] != expected_id:
            raise M8Error("assembly_invalid", "a raw record id is not the deterministic master id", "assembly")
        if record["authorization_id"] != authorisation["authorisation_id"] or record["run_id"] != manifest["run_id"]:
            raise M8Error("assembly_invalid", "a raw record authorisation or run id drifted", "assembly")
        if record["source_raw_file_relative_path"] != relative or record["source_raw_file_sha256"] != digest:
            raise M8Error("assembly_invalid", "a raw record source path or hash drifted", "assembly")
        blob = raw_by_relative[relative]
        lines = blob.split(b"\n")[:-1]
        if generation.decode_raw_line(lines[offset]) != record["raw_decoded_text"]:
            raise M8Error("assembly_invalid", "the decoded representation does not match the retained raw bytes", "assembly")
        covered[invocation["invocation_index"]] = covered.get(invocation["invocation_index"], 0) + 1
        seen.append(master)
    for invocation in invocations:
        if covered.get(invocation["invocation_index"]) != invocation["line_count"]:
            raise M8Error("assembly_invalid", "invocation references are missing or extra", "assembly")
    if seen != sorted(seen) or seen != sorted(masters):
        raise M8Error("assembly_invalid", "an arm ledger is not the scheduled master-index order", "assembly")
    return seen


def _load_arm(source, condition_id, run_root, built, deps):
    if not isinstance(source, dict) or tuple(sorted(source)) != SOURCE_KEYS:
        raise M8Error("assembly_invalid", "an arm binding field set drifted", "assembly")
    block = source["block"]
    if block not in ("A", "B"):
        raise M8Error("assembly_invalid", "an arm block is not A or B", "assembly")
    path = source["path"]
    arm_directory = assert_arm_manifest_path(path, run_root)
    blob = _read_exact(path, source["byte_count"], source["sha256"], arm_directory, deps)
    manifest = _load_json_bytes(blob, "an arm manifest is not a JSON object")
    if generation.canonical_bytes(manifest) != blob:
        raise M8Error("assembly_invalid", "an arm manifest is not canonical JSON", "assembly")
    ledger_path = os.path.join(arm_directory, generation.LEDGER_NAME)
    ledger_hash = manifest.get("raw_attempt_ledger_sha256")
    ledger_bytes = manifest.get("raw_attempt_ledger_byte_count")
    ledger_blob = _read_exact(ledger_path, ledger_bytes, ledger_hash, arm_directory, deps)
    records = _ledger_records(ledger_blob)
    raw_by_relative = {}
    referenced = []
    for row in manifest.get("invocation_ledger") or []:
        relative = row.get("relative_path") if isinstance(row, dict) else None
        if not isinstance(relative, str) or relative.startswith("/") or ".." in relative.split("/") or os.path.normpath(relative) != relative:
            raise M8Error("assembly_invalid", "an invocation path is not a safe relative path", "assembly")
        if relative in raw_by_relative:
            raise M8Error("assembly_invalid", "an invocation reference is duplicated", "assembly")
        raw_path = os.path.normpath(os.path.join(arm_directory, relative.replace("/", os.sep)))
        raw_blob = _read_exact(raw_path, None, row.get("sha256"), arm_directory, deps)
        raw_by_relative[relative] = raw_blob
        referenced.append(relative)
    indexes = _check_arm(manifest, records, raw_by_relative, condition_id, block, built, arm_directory)
    return {
        "block": block,
        "byte_count": source["byte_count"],
        "indexes": indexes,
        "manifest": manifest,
        "manifest_sha256": source["sha256"],
        "path": path,
        "records": records,
        "run_id": manifest["run_id"],
    }


def validate_assembly_entry(entry):
    generation.assert_assembly_entry_schema(entry)
    if os.path.lexists(entry["output_directory"]):
        raise M8Error("output_directory_exists", "an active entry names an existing output directory", "output_directory")
    return entry


def _record_assembly_failure(entry, error, provenance):
    output = entry["output_directory"]
    if not os.path.isdir(output):
        return None
    if os.path.lexists(os.path.join(output, MANIFEST_NAME)):
        raise M8Error("evidence_write_failed", "a failed assembly already has a success manifest", "evidence_write")
    safe = error if isinstance(error, M8Error) else M8Error("assembly_invalid", "an unexpected failure was contained", "assembly")
    payload = generation._failure_payload(entry, safe, provenance, {"completed_invocation_count": 0, "failing_invocation_index": None})
    if not os.path.lexists(os.path.join(output, generation.FAILURE_NAME)):
        generation.write_atomic_bytes(output, generation.FAILURE_NAME, generation.canonical_bytes(payload))
    return payload


def assemble_authorised(entry, deps, raw_config_sha256=None):
    generation.assert_assembly_entry_schema(entry)
    if raw_config_sha256 is None:
        raise M8Error("provenance_mismatch", "the active configuration raw digest is missing", "assembly")
    generation._sha256_text(raw_config_sha256, "the active configuration raw digest is missing")
    observation = deps.repository_observation(entry)
    head = generation.assert_repository_binding(entry, observation)
    provenance = generation.provenance_from_entry(entry, head, raw_config_sha256)
    if provenance["active_configuration_raw_sha256"] != raw_config_sha256:
        raise M8Error("provenance_mismatch", "the active configuration raw digest was replaced", "assembly")
    generation.assert_assembly_filesystem_preflight(entry, deps)
    built = generation._load_schedule(deps)
    loaded = [_load_arm(source, entry["condition_id"], entry["run_root"], built, deps) for source in entry["sources"]]
    by_block = {item["block"]: item for item in loaded}
    if set(by_block) != {"A", "B"}:
        raise M8Error("assembly_invalid", "assembly did not load both blocks", "assembly")
    combined = by_block["A"]["records"] + by_block["B"]["records"]
    if len(combined) != schedule.RAW_ATTEMPT_TOTAL:
        raise M8Error("assembly_invalid", "a condition does not hold 30000 raw attempts", "assembly")
    indexes = [record["master_attempt_index"] for record in combined]
    if sorted(indexes) != list(range(schedule.RAW_ATTEMPT_TOTAL)) or len(set(indexes)) != schedule.RAW_ATTEMPT_TOTAL:
        raise M8Error("assembly_invalid", "master indexes are missing, duplicated, or out of range", "assembly")
    ordered = sorted(combined, key=lambda record: record["master_attempt_index"])
    if [record["master_attempt_index"] for record in ordered] != list(range(schedule.RAW_ATTEMPT_TOTAL)):
        raise M8Error("assembly_invalid", "the combined ledger is not ordered by master index", "assembly")
    for record in ordered:
        if FORBIDDEN_RECORD_KEYS.intersection(record):
            raise M8Error("assembly_invalid", "assembly introduced a classification field", "assembly")
    if entry["condition_id"] == generation.CONDITION_D1:
        seeds = {record["d1_training_seed"] for record in ordered}
        counts = {seed: sum(1 for record in ordered if record["d1_training_seed"] == seed) for seed in (43, 44)}
        if seeds != {43, 44} or counts[43] != 15000 or counts[44] != 15000:
            raise M8Error("assembly_invalid", "D1 is not split 15000/15000 by training seed", "assembly")
    ledger = b"".join(generation.canonical_bytes(record) for record in ordered)
    if os.path.lexists(entry["output_directory"]):
        raise M8Error("output_directory_exists", "an active entry names an existing output directory", "output_directory")
    try:
        generation._consume_directory(entry, provenance)
        started = deps.now() if hasattr(deps, "now") else "1970-01-01T00:00:00+00:00"
        generation.write_atomic_bytes(entry["output_directory"], LEDGER_NAME, ledger)
        finished = deps.now() if hasattr(deps, "now") else "1970-01-01T00:00:01+00:00"
        manifest = {
            "authorization": {
                "active_configuration_raw_sha256": provenance["active_configuration_raw_sha256"],
                "active_configuration_sha256": provenance["active_configuration_sha256"],
                "authorisation_id": entry["authorisation_id"],
                "authorization_commit": provenance["authorization_commit"],
                "authorization_parent_commit": provenance["authorization_parent_commit"],
                "executing_implementation_commit": provenance["executing_implementation_commit"],
                "implementation_file_hashes": dict(provenance["implementation_file_hashes"]),
                "origin_main": provenance["origin_main"],
            },
            "cleaner_invoked": False,
            "combined_ledger_byte_count": len(ledger),
            "combined_ledger_sha256": generation.sha256_bytes(ledger),
            "condition_id": entry["condition_id"],
            "deduplication_performed": False,
            "filtering_performed": False,
            "later_evaluation_required": True,
            "manifest_schema_version": generation.ASSEMBLY_MANIFEST_SCHEMA_VERSION,
            "metric_computation_performed": False,
            "parsing_performed": False,
            "raw_attempt_count": schedule.RAW_ATTEMPT_TOTAL,
            "replacement_or_replenishment_performed": False,
            "repository_identity": generation.runtime_repository_identity(provenance["authorization_commit"]),
            "reuse_prohibited": True,
            "run_id": entry["authorisation_id"],
            "schedule": {
                "block_a_invocation_schedule_sha256": schedule.EXPECTED_SCHEDULE_HASHES["block_a_invocation_schedule_sha256"],
                "block_b_invocation_schedule_sha256": schedule.EXPECTED_SCHEDULE_HASHES["block_b_invocation_schedule_sha256"],
                "master_attempt_map_sha256": schedule.EXPECTED_SCHEDULE_HASHES["master_attempt_map_sha256"],
                "source_length_vector_sha256": schedule.LENGTH_VECTOR_SHA256,
            },
            "schema_version": generation.ASSEMBLY_MANIFEST_SCHEMA_VERSION,
            "sequence_access": {"EVAL": False, "REF": False, "TRAIN": False, "VALIDATION": False},
            "source_arm_manifests": [
                {
                    "block": "A",
                    "byte_count": by_block["A"]["byte_count"],
                    "path": by_block["A"]["path"],
                    "run_id": by_block["A"]["run_id"],
                    "sha256": by_block["A"]["manifest_sha256"],
                },
                {
                    "block": "B",
                    "byte_count": by_block["B"]["byte_count"],
                    "path": by_block["B"]["path"],
                    "run_id": by_block["B"]["run_id"],
                    "sha256": by_block["B"]["manifest_sha256"],
                },
            ],
            "timestamps": {"finished_at": finished, "started_at": started},
        }
        generation.write_atomic_bytes(entry["output_directory"], MANIFEST_NAME, generation.canonical_bytes(manifest))
    except M8Error as exc:
        _record_assembly_failure(entry, exc, provenance)
        raise
    except BaseException as exc:
        contained = M8Error("assembly_invalid", "an unexpected failure was contained", "assembly")
        _record_assembly_failure(entry, contained, provenance)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise contained
    return {"ledger": ledger, "manifest": manifest, "records": ordered}


def launch_authorised_assembly(authorisation_id, config_bytes=None, deps=None):
    generation.reject_authorisation_id(authorisation_id)
    raw = generation.read_m8_config_bytes() if config_bytes is None else config_bytes
    if not isinstance(raw, (bytes, bytearray)):
        raise M8Error("configuration_not_consumable", "configuration bytes are missing")
    document = generation.parse_config(raw)
    generation.reject_m7_document(document)
    claim = generation.classify_configuration(document)
    if claim != "assembly_claim":
        if claim == "inactive":
            generation.assert_inactive_configuration(document)
        raise M8Error("execution_not_authorised", "the checked-in M8 configuration is not executable", "inactive_gate")
    entry = generation.assert_active_assembly_document(document)
    if entry.get("authorisation_id") != authorisation_id:
        raise M8Error("authorisation_field_missing", "no single entry carries that authorisation id", "assembly")
    if deps is None:
        deps = generation.ProductionDeps()
    return assemble_authorised(entry, deps, raw_config_sha256=generation.sha256_bytes(bytes(raw)))


HELP_TEXT = """\
M8 raw-pool assembly is ready for review and is not authorised.

Assembly does not run because generation files exist. This entry point
accepts only --help, --schema and --authorisation-id <id>. While the
checked-in configuration is inactive it refuses before any manifest, raw
file, environment, Git, GPU, or output inspection. It cannot execute.
"""


def schema_document():
    return {
        "assembly_manifest_schema_version": generation.ASSEMBLY_MANIFEST_SCHEMA_VERSION,
        "document_status": generation.DOCUMENT_STATUS,
        "execution_authorised": False,
        "sort": "master_attempt_index_only",
    }


def production_main(argv=None, stdout=None, config_bytes=None, deps=None):
    stdout = sys.stdout if stdout is None else stdout
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--help"], ["-h"]):
        stdout.write(HELP_TEXT)
        return 0
    if arguments == ["--schema"]:
        stdout.write(generation.canonical_json(schema_document()).decode("utf-8"))
        return 0
    if len(arguments) == 2 and arguments[0] == "--authorisation-id":
        launch_authorised_assembly(arguments[1], config_bytes=config_bytes, deps=deps)
        return 0
    raise M8Error("cli_argument_rejected", "the entry point accepts only --help, --schema and --authorisation-id <id>")


def main(argv=None):
    try:
        return production_main(argv)
    except M8Error as exc:
        sys.stderr.write(exc.code + ": " + exc.detail + "\n")
        if exc.code in ("cli_argument_rejected", "execution_not_authorised", "m7_authority_rejected"):
            return 2
        return 1


if __name__ == "__main__":
    sys.exit(main())
