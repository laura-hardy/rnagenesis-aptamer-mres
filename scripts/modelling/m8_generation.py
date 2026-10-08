#!/usr/bin/env python3
"""Inactive M8 raw-generation runner.

The checked-in configuration is not executable. ``--help`` and ``--schema``
only print static text. ``--authorisation-id`` reads that configuration and
refuses before any environment, Git, GPU, checkpoint, biological, run-root,
or output inspection while the document is inactive.

A future active entry describes exactly one of the four arms. This module
does not call an M7 guardrail, a TRAIN-copy diagnostic, or the output cleaner.
``generation.py`` is invoked and is not modified.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import sys

import m8_schedule as schedule

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
CONFIG_RELATIVE = "config/experiments/M8_raw_generation.yaml"
RNAGENESIS_ROOT = "/home/laura/RNAGenesis"
CANONICAL_RUN_ROOT = "/home/laura/rnagenesis-mres-runs"
RUN_ROOT = CANONICAL_RUN_ROOT
MRES_ROOT = "/home/laura/rnagenesis-aptamer-mres"
GENERATION_ENTRY = os.path.join(RNAGENESIS_ROOT, "generation.py")
PINNED_PYTHON = "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python"
PINNED_RESOLVED_PYTHON = "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python3.8"
PINNED_INTERPRETER_SHA256 = "058a393acc1b0ee5d0564a6dca1e36f6602b4686b369ad957eca2b359d145059"
PINNED_ENVIRONMENT_PREFIX = "/home/laura/miniconda3/envs/rnagenesis-h200"
FIXED_CHILD_PATH = PINNED_ENVIRONMENT_PREFIX + "/bin:/usr/bin:/bin"
LOGICAL_DEVICE = "cuda:0"
CUDA_DEVICE_ORDER = "PCI_BUS_ID"
EVALUATION_WORKTREE = "/home/laura/rnagenesis-mres-worktrees/generator-eval-prep"
LIVE_M7_SEED44_AUTHORISATION_ID = "m7_d1_final_replicate_seed44_2cb1b6a26391_gpu1_attempt1"

DOCUMENT_STATUS = "M8_RAW_GENERATION_READY_FOR_REVIEW_NOT_AUTHORISED"
ACTIVE_DOCUMENT_STATUS = "M8_RAW_GENERATION_AUTHORISED_FOR_SINGLE_USE_EXECUTION"
ACTIVE_ASSEMBLY_STATUS = "M8_RAW_ASSEMBLY_AUTHORISED_FOR_SINGLE_USE_EXECUTION"
SCHEMA_VERSION = "m8-raw-generation-config-1"
MANIFEST_SCHEMA_VERSION = "m8-arm-manifest-1"
ASSEMBLY_MANIFEST_SCHEMA_VERSION = "m8-assembly-manifest-1"
RECORD_SCHEMA_VERSION = "m8-raw-attempt-1"
EXPERIMENT_ID = "M8_raw_generation"
MRES_COMMIT = "d0f9a397b536c64ca1b22662cc9ae36aea0101f6"
MRES_BRANCH = "main"
RNAGENESIS_COMMIT = "e3b855bbf4d1af376f43747643fa30afd662828c"
RNAGENESIS_BRANCH = "mres-d1-diffusion-finetune"

SELECTED_SET_SHA256 = "af0c0e555a8b878feadeb17fcbde18d8b780819a42d9e0cc547d2fc0c6895f8f"
FINAL_SELECTION_MANIFEST_SHA256 = "49b218e3df74825e1931148e2f65b25aae057c822e2ab32d44c2960b1587c91c"
FINAL_SELECTION_MANIFEST_BYTES = 13124
FINAL_SELECTION_MANIFEST_PATH = (
    "/home/laura/rnagenesis-mres-runs/m7_d1_final_selection_b5de24327ed5_attempt1/"
    "m7_final_selection_manifest.json"
)
IMPLEMENTATION_FILES = (
    "scripts/modelling/m8_assemble.py",
    "scripts/modelling/m8_generation.py",
    "scripts/modelling/m8_schedule.py",
)
PERMITTED_AUTHORIZATION_DELTA = ("config/experiments/M8_raw_generation.yaml",)
GENERATION_PY_SHA256 = "d1b1fca9544ed1c85cf6fdd304b5acb965d76ca6c89a2f98e57224ac95e44367"
RETENTION_MINIMUM_DATE = "2026-11-01"

B1_WEIGHT_SHA256 = "c268021b6cab37423e3bffd495b139bb69698d8d11c7b96477fbfb239b0cff26"
B1_UNET_CONFIG_SHA256 = "3a9975ff165bbd5ca82923e6ed1c5ed7eb383a23f4f3f55db713c995031f8ee3"
ENCDEC_CONFIG_SHA256 = "ab309231b75405af3e2ef6fe49e4e74c1b96021ef2a4f61b46e5796b8799378a"
ENCDEC_WEIGHT_SHA256 = "3c4e34f7626c94416d504c16569b5f3f785fffe77889b9886344477b95e74c68"
D1_UNET_CONFIG_SHA256 = "42c864c81e35ef1a0c7964a3642492fba95c9e24a153407f9fd98855b20d9d70"
PIPELINE_INDEX_SHA256 = "05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e"
SCHEDULER_SHA256 = "6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396"

D1_CHECKPOINTS = {
    43: {
        "checkpoint_name": (
            "D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-43__epoch-5__update-105__"
            "git-c150894b9982d7afebfb2b3390b0797a4da146b5"
        ),
        "parent_directory_name": "m7_d1_final_replicate_seed43_c150894b9982_gpu1_attempt2",
        "weight_sha256": "c0797888bde9033cc15b056c8c09e70b9f7fba0fb21b1f3840a4f1efb77031ab",
    },
    44: {
        "checkpoint_name": (
            "D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-44__epoch-5__update-105__"
            "git-2cb1b6a26391ed36754ec21685a4501d659d50ef"
        ),
        "parent_directory_name": "m7_d1_final_replicate_seed44_2cb1b6a26391_gpu1_attempt1",
        "weight_sha256": "d0fcb5174230b8bbbc6bfe59eabda9b37687c03800012bc1a6981cc215469ed5",
    },
}
CHECKPOINT_MEMBERS = (
    "model_index.json",
    "scheduler/scheduler_config.json",
    "unet/config.json",
    "unet/diffusion_pytorch_model.safetensors",
)
WEIGHT_MEMBER = "unet/diffusion_pytorch_model.safetensors"

CONDITION_B1 = "B1_generic_released_rnagenesis"
CONDITION_D1 = "D1_mres_curated_aptamer_diffusion_adapted"
ARMS = {
    "b1_block_a": {"condition_id": CONDITION_B1, "technical_block": "A", "d1_training_seed": None, "asset_kind": "b1"},
    "b1_block_b": {"condition_id": CONDITION_B1, "technical_block": "B", "d1_training_seed": None, "asset_kind": "b1"},
    "d1_seed43_block_a": {"condition_id": CONDITION_D1, "technical_block": "A", "d1_training_seed": 43, "asset_kind": "d1"},
    "d1_seed44_block_b": {"condition_id": CONDITION_D1, "technical_block": "B", "d1_training_seed": 44, "asset_kind": "d1"},
}

EXECUTION_FLAGS = (
    "assembly_authorised",
    "authorised",
    "biological_paths_permitted",
    "generation_authorised",
    "gpu_identity_bound",
)
GENERATION_EXECUTION = {
    "assembly_authorised": False,
    "authorised": True,
    "biological_paths_permitted": False,
    "generation_authorised": True,
    "gpu_identity_bound": True,
}
ASSEMBLY_EXECUTION = {
    "assembly_authorised": True,
    "authorised": True,
    "biological_paths_permitted": False,
    "generation_authorised": False,
    "gpu_identity_bound": False,
}
ROOT_KEYS = (
    "arms",
    "assembly_authorisation_entries",
    "assembly_manifest_schema_version",
    "authorisation_entries",
    "checkpoints",
    "closure",
    "consumable_by_executable_workflow",
    "deletion_implemented",
    "denied",
    "document_status",
    "execution",
    "experiment_id",
    "manifest_schema_version",
    "pairing",
    "record_schema",
    "repository_identity",
    "retention_minimum_date",
    "retry_rule",
    "sampler",
    "schedule_hashes",
    "schema_version",
    "selected_set_identity",
)
RECORD_SCHEMA = {
    "classification_fields": "none",
    "raw_bytes_authoritative": True,
    "raw_decoded_text_rule": "deterministic_utf8_else_latin1",
    "schema_version": RECORD_SCHEMA_VERSION,
}
CLOSURE_KEYS = (
    "cleaner_invoked",
    "execution_authorised",
    "filtering_performed",
    "later_evaluation_required",
    "m8_execution_authorised",
    "replacement_or_replenishment_performed",
)
SAMPLER_CONTRACT = {
    "ddim_steps": 50,
    "do_sample": True,
    "encdec": "frozen",
    "eta": "0",
    "guidance_enabled": False,
    "max_seq_len_rule": "requested_biological_length_plus_1",
    "top_k": 0,
    "top_p": "0.95",
    "weights": "raw",
}
REPOSITORY_IDENTITY = {
    "mres_branch": MRES_BRANCH,
    "mres_commit": MRES_COMMIT,
    "rnagenesis_branch": RNAGENESIS_BRANCH,
    "rnagenesis_commit": RNAGENESIS_COMMIT,
}
SELECTED_SET_IDENTITY = {
    "final_selection_manifest_sha256": FINAL_SELECTION_MANIFEST_SHA256,
    "selected_set_sha256": SELECTED_SET_SHA256,
}
ARM_NAMES = (
    "b1_block_a",
    "b1_block_b",
    "d1_seed43_block_a",
    "d1_seed44_block_b",
)
PAIRING_CONTRACT = {
    "b1_block_a": "d1_seed43_block_a",
    "b1_block_b": "d1_seed44_block_b",
}
DENIED_CONTRACT = {
    "evaluation_worktree": "prohibited",
    "live_m7_seed44_authorisation_is_not_m8_authority": LIVE_M7_SEED44_AUTHORISATION_ID,
    "roles": ["REF", "EVAL", "VALIDATION", "TRAIN"],
    "sequence_basenames": ["corpus_final.txt", "ft_train.csv", "ft_validation.csv", "ref.csv", "eval.csv"],
}
B1_CHECKPOINT_KEYS = (
    "diffusion_relative",
    "encdec_config_sha256",
    "encdec_weight_sha256",
    "identity",
    "unet_config_sha256",
    "weight_sha256",
)
D1_CHECKPOINT_KEYS = ("checkpoint_name", "members_sha256", "weight_sha256")
SHA256_TEXT = re.compile(r"^[0-9a-f]{64}$")
SHA40_TEXT = re.compile(r"^[0-9a-f]{40}$")
PCI_BUS_TEXT = re.compile(r"^[0-9A-Fa-f]{4,8}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}\.[0-7]$")
LD_LIBRARY_PATH_COMPONENT = re.compile(r"^/[A-Za-z0-9._+@=,%/\-]*$")
SELECTED_ROW_KEYS = ("checkpoint_name", "epoch", "members_sha256", "seed", "update", "validation_mse", "weight_sha256")
INACTIVE_FORBIDDEN_KEYS = frozenset(
    [
        "authorisation_timestamp",
        "authorization_commit",
        "cuda_visible_devices",
        "evidence_directory",
        "gpu_uuid",
        "interpreter",
        "ld_library_path",
        "output_directory",
        "pci_bus",
        "physical_gpu",
    ]
)
M7_CONFIG_BASENAMES = frozenset(
    [
        "B1_generic_generation.yaml",
        "D1_candidate_guardrails.yaml",
        "D1_diffusion_pilot.yaml",
        "D1_diffusion_smoke.yaml",
        "D1_final_replicates.yaml",
        "D1_final_selection.yaml",
        "D1_update21_diagnostic_generation.yaml",
    ]
)
DENIED_BASENAMES = frozenset(["corpus_final.txt", "eval.csv", "ft_train.csv", "ft_validation.csv", "ref.csv"])
DENIED_COMPONENTS = frozenset(["EVAL", "REF", "TRAIN", "VALIDATION"])
RAW_RECORD_KEYS = (
    "authorization_id",
    "batch_number",
    "checkpoint_identity",
    "condition_id",
    "d1_training_seed",
    "generation_seed",
    "invocation_index",
    "line_index",
    "master_attempt_index",
    "max_seq_len",
    "raw_decoded_text",
    "record_id",
    "requested_biological_length",
    "run_id",
    "schema_version",
    "source_raw_file_relative_path",
    "source_raw_file_sha256",
    "technical_block",
    "within_batch_position",
)
PROHIBITED_ARGV = frozenset(
    ["--cpu", "--extend_input", "--guidance", "--save_latent_space", "--search", "--truncate", "--update_seq"]
)
ENVIRONMENT_ALLOW_LIST = ("LANG", "LC_ALL", "LC_CTYPE", "TZ")
OFFLINE_CONTROLS = {"HF_DATASETS_OFFLINE": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
FIXED_CHILD_ENVIRONMENT_CONTROLS = {"CUDA_MODULE_LOADING": "LAZY"}
ACCEPTED_RUNTIME_VERSIONS = {
    "accelerate": "0.25.0",
    "diffusers": "0.25.0",
    "python": "3.8.13",
    "torch": "2.1.2+cu121",
    "transformers": "4.36.2",
}
CONTROLLER_OBSERVATION_KEYS = (
    "executable",
    "proc_self_exe",
    "proc_self_exe_resolved",
    "python_version",
    "resolved_path",
    "sha256",
)
CHILD_OBSERVATION_KEYS = (
    "executable",
    "python_version",
    "resolved_path",
    "sha256",
)
MANIFEST_SAMPLER = {
    "ddim_steps": 50,
    "do_sample": True,
    "encdec": "frozen",
    "eta": 0,
    "guidance_enabled": False,
    "top_k": 0,
    "top_p": 0.95,
    "weights": "raw",
}
SEQUENCE_ACCESS_DENIAL = {"EVAL": False, "REF": False, "TRAIN": False, "VALIDATION": False}
# Reviewed RNAGenesis untracked fingerprint. Duplicated here so launch does not import m6_pilot_contract.
KNOWN_RNAGENESIS_UNTRACKED = (
    ".cache/",
    "__pycache__/",
    "checkpoints/",
    "configs/",
    "generation_sequences/",
    "models/autoencoder/__pycache__/",
    "models/autoencoder/decoder/checkpoints/",
    "models/autoencoder/decoder/progen/progen2/models/progen/__pycache__/",
    "models/autoencoder/encoder/biomap/__pycache__/",
    "models/autoencoder/encoder/esm/__pycache__/",
    "models/diffusion_models/__pycache__/",
    "tests/__pycache__/",
    "zenodo_downloads/",
)
KNOWN_UNTRACKED_CONFIG_FILES = (
    "configs/rnagenesis/autoencoder/config.yaml",
    "configs/rnagenesis/classifier/mlp_160_32.yaml",
)
SOURCE_SUFFIXES = frozenset([".py"])
CONFIG_SUFFIXES = frozenset([".yaml", ".yml"])
PROHIBITED_RESOLVED_ROOTS = (MRES_ROOT, RNAGENESIS_ROOT, EVALUATION_WORKTREE)
REVISION_ROW_KEYS = ("changed_files", "commit", "parents")
TIMESTAMP_TEXT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+]00:00$")
CONSUMPTION_NAME = "authorization_consumption.json"
FAILURE_NAME = "authorization_failure.json"
LEDGER_NAME = "m8_raw_attempt_ledger.jsonl"
INVOCATION_LEDGER_NAME = "m8_invocation_ledger.json"
MANIFEST_NAME = "m8_arm_manifest.json"
DETAIL_PATTERN = re.compile(r"^[A-Za-z0-9_ .:/-]{1,180}$")
SEQUENCE_RUN = re.compile(r"[ACGUacgu]{8,}")
ENTRY_KEYS = (
    "activation_status",
    "active_configuration_sha256",
    "arm",
    "asset_kind",
    "authorisation_id",
    "authorization_parent_commit",
    "condition_id",
    "consumed",
    "d1_training_seed",
    "executing_implementation_commit",
    "gpu_uuid",
    "implementation_file_hashes",
    "interpreter_path",
    "interpreter_resolved_path",
    "interpreter_sha256",
    "ld_library_path",
    "library_versions",
    "logical_device",
    "minimum_free_filesystem_bytes",
    "minimum_free_gpu_memory_bytes",
    "output_directory",
    "pci_bus",
    "physical_gpu",
    "reuse_permitted",
    "run_id",
    "run_root",
    "single_use",
    "technical_block",
)
INTERPRETER_BINDING_KEYS = ("path", "resolved_path", "sha256")
PROVENANCE_KEYS = (
    "active_configuration_raw_sha256",
    "active_configuration_sha256",
    "authorization_commit",
    "authorization_parent_commit",
    "executing_implementation_commit",
    "implementation_file_hashes",
    "origin_main",
)


class M8Error(Exception):
    def __init__(self, code, detail, stage="configuration"):
        self.code = code
        self.detail = safe_detail(detail)
        self.stage = stage
        super().__init__(self.code + ": " + self.detail)


def safe_detail(detail):
    if not isinstance(detail, str) or DETAIL_PATTERN.fullmatch(detail) is None:
        return "the failure detail was withheld"
    if "Traceback" in detail or SEQUENCE_RUN.search(detail) is not None:
        return "the failure detail was withheld"
    lowered = detail.lower()
    if any(marker in lowered for marker in ("token", "password", "secret", "ld_library_path", "cuda_visible")):
        return "the failure detail was withheld"
    return detail


def canonical_bytes(value):
    return schedule.canonical_bytes(value)


def canonical_json(value):
    return canonical_bytes(value)


def sha256_bytes(data):
    return schedule.sha256_bytes(data)


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def config_path():
    return os.path.join(REPO_ROOT, CONFIG_RELATIVE)


def reject_authorisation_id(authorisation_id):
    if not isinstance(authorisation_id, str) or authorisation_id == "":
        raise M8Error("cli_argument_rejected", "the authorisation id is empty")
    if authorisation_id == LIVE_M7_SEED44_AUTHORISATION_ID or authorisation_id.startswith("m7_"):
        raise M8Error("m7_authority_rejected", "an m7_ authorisation id is not M8 authority", "authority")
    if not authorisation_id.startswith("m8_") or not re.fullmatch(r"m8_[A-Za-z0-9_]+", authorisation_id):
        raise M8Error("cli_argument_rejected", "the authorisation id is not an m8 id")
    return authorisation_id


def reject_configuration_path(path):
    """Refuse an M7 configuration path before any open."""
    if not isinstance(path, str) or path.strip() == "":
        raise M8Error("m7_authority_rejected", "the configuration path is not the M8 document", "authority")
    normalised = path.replace("\\", "/")
    base = os.path.basename(os.path.normpath(normalised))
    if base in M7_CONFIG_BASENAMES or base.startswith("m7") or "D1_" in base or "M7" in base:
        raise M8Error("m7_authority_rejected", "an M7 configuration path is not M8 authority", "authority")
    if base != "M8_raw_generation.yaml":
        raise M8Error("configuration_rejected", "the configuration path is not the M8 document", "authority")
    return True


def assert_not_prohibited(path, bound_output=None, role="unspecified"):
    """String-only denial. This function does not open, list, or stat the path."""
    if not isinstance(path, str) or path.strip() == "":
        raise M8Error("prohibited_input", "a path is empty", "input_denial")
    normalised = os.path.normpath(path.replace("\\", "/"))
    if normalised != path.replace("\\", "/") and ".." in path.replace("\\", "/").split("/"):
        raise M8Error("prohibited_input", "a path is not normalised", "input_denial")
    parts = [part for part in normalised.split("/") if part not in ("", ".")]
    if any(part in DENIED_COMPONENTS for part in parts):
        raise M8Error("prohibited_input", "a REF EVAL VALIDATION or TRAIN path was refused", "input_denial")
    if parts and parts[-1] in DENIED_BASENAMES:
        raise M8Error("prohibited_input", "a biological sequence basename was refused", "input_denial")
    if normalised == EVALUATION_WORKTREE or normalised.startswith(EVALUATION_WORKTREE + "/"):
        raise M8Error("prohibited_input", "the evaluation worktree was refused", "input_denial")
    if "generator-eval-prep" in parts:
        raise M8Error("prohibited_input", "the evaluation worktree was refused", "input_denial")
    if role == "length_vector":
        if normalised != schedule.LENGTH_VECTOR_PATH:
            raise M8Error("prohibited_input", "the length vector path is not the accepted pin", "input_denial")
        return True
    if role == "final_selection":
        if normalised != FINAL_SELECTION_MANIFEST_PATH:
            raise M8Error("prohibited_input", "the final-selection manifest path is not the approved pin", "input_denial")
        return True
    if role == "asset":
        if normalised.startswith(RNAGENESIS_ROOT + "/"):
            return True
        for pin in D1_CHECKPOINTS.values():
            prefix = RUN_ROOT + "/" + pin["parent_directory_name"] + "/" + pin["checkpoint_name"]
            if normalised == prefix or normalised.startswith(prefix + "/"):
                return True
        raise M8Error("prohibited_input", "an asset path is not a pinned B1 or D1 member", "input_denial")
    if role == "sealed_arm":
        allowed = os.path.normpath(bound_output) if bound_output else ""
        if allowed and (normalised == allowed or normalised.startswith(allowed + "/")):
            return True
        raise M8Error("prohibited_input", "a sealed arm path is outside its bound directory", "input_denial")
    under_runs = normalised == RUN_ROOT or normalised.startswith(RUN_ROOT + "/")
    if under_runs:
        if role == "bound_output" and bound_output is not None:
            bound = os.path.normpath(bound_output)
            if normalised == bound or normalised.startswith(bound + "/"):
                return True
        raise M8Error("prohibited_input", "sibling run evidence was refused", "input_denial")
    return True


def refuse_before_open(path, opener, bound_output=None, role="unspecified"):
    assert_not_prohibited(path, bound_output, role)
    return opener(path)


def _walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            for nested in _walk_keys(item):
                yield nested
    elif isinstance(value, list):
        for item in value:
            for nested in _walk_keys(item):
                yield nested


def parse_config(raw):
    if not isinstance(raw, (bytes, bytearray)):
        raise M8Error("configuration_not_consumable", "configuration bytes are missing")
    try:
        import yaml
    except ImportError:
        raise M8Error("configuration_not_consumable", "the YAML parser is unavailable")
    try:
        loaded = yaml.safe_load(bytes(raw).decode("utf-8"))
    except (UnicodeDecodeError, Exception):
        raise M8Error("configuration_not_consumable", "the configuration is not UTF-8 YAML")
    if not isinstance(loaded, dict):
        raise M8Error("configuration_not_consumable", "the configuration root is not a mapping")
    return loaded


def reject_m7_document(document):
    if not isinstance(document, dict):
        raise M8Error("m7_authority_rejected", "an M7 document is not M8 authority", "authority")
    schema = document.get("schema_version")
    manifest = document.get("manifest_schema_version")
    status = document.get("document_status")
    if isinstance(schema, str) and schema.startswith("m7-"):
        raise M8Error("m7_authority_rejected", "an M7 schema version is not M8 authority", "authority")
    if isinstance(manifest, str) and manifest.startswith("m7-"):
        raise M8Error("m7_authority_rejected", "an M7 schema version is not M8 authority", "authority")
    if isinstance(status, str) and status.startswith("M7_"):
        raise M8Error("m7_authority_rejected", "an M7 document status is not M8 authority", "authority")
    entries = document.get("authorisation_entries")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                authorisation_id = entry.get("authorisation_id")
                if authorisation_id == LIVE_M7_SEED44_AUTHORISATION_ID or (
                    isinstance(authorisation_id, str) and authorisation_id.startswith("m7_")
                ):
                    raise M8Error("m7_authority_rejected", "an m7_ authorisation id is not M8 authority", "authority")
    return True


def _require_hashes(mapping, expected, detail):
    if not isinstance(mapping, dict):
        raise M8Error("configuration_not_consumable", detail)
    if set(mapping) != set(expected):
        raise M8Error("configuration_not_consumable", detail)
    for key, value in expected.items():
        if mapping.get(key) != value:
            raise M8Error("configuration_not_consumable", detail)
    return True


def _exact_mapping(mapping, expected, detail):
    if not isinstance(mapping, dict) or tuple(sorted(mapping)) != tuple(sorted(expected)):
        raise M8Error("configuration_not_consumable", detail)
    return mapping


def assert_shared_scientific_contract(document):
    """Immutable scientific sections. Status, execution flags, and entries are not part of this check."""
    reject_m7_document(document)
    if not isinstance(document, dict) or tuple(sorted(document)) != ROOT_KEYS:
        raise M8Error("configuration_not_consumable", "the configuration has an unknown or missing field")
    if document.get("schema_version") != SCHEMA_VERSION or document.get("experiment_id") != EXPERIMENT_ID:
        raise M8Error("configuration_not_consumable", "schema or experiment identity drifted")
    if document.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        raise M8Error("configuration_not_consumable", "manifest schema drifted")
    if document.get("assembly_manifest_schema_version") != ASSEMBLY_MANIFEST_SCHEMA_VERSION:
        raise M8Error("configuration_not_consumable", "assembly schema drifted")
    identity = _exact_mapping(document.get("repository_identity"), REPOSITORY_IDENTITY, "repository identity drifted")
    if dict(identity) != REPOSITORY_IDENTITY:
        raise M8Error("configuration_not_consumable", "repository identity drifted")
    selection = _exact_mapping(document.get("selected_set_identity"), SELECTED_SET_IDENTITY, "selected-set identity drifted")
    if dict(selection) != SELECTED_SET_IDENTITY:
        raise M8Error("configuration_not_consumable", "selected-set identity drifted")
    _require_hashes(document.get("schedule_hashes"), schedule.EXPECTED_SCHEDULE_HASHES, "schedule hashes drifted")
    _assert_checkpoint_pins(document.get("checkpoints"))
    if document.get("sampler") != SAMPLER_CONTRACT:
        raise M8Error("configuration_not_consumable", "sampler settings drifted")
    if list(document.get("arms")) != list(ARM_NAMES):
        raise M8Error("configuration_not_consumable", "the arm list drifted")
    if document.get("pairing") != PAIRING_CONTRACT:
        raise M8Error("configuration_not_consumable", "arm pairing drifted")
    if document.get("record_schema") != RECORD_SCHEMA:
        raise M8Error("configuration_not_consumable", "the record schema drifted")
    if document.get("retry_rule") != "new_id_authorisation_and_directory":
        raise M8Error("configuration_not_consumable", "retry rule drifted")
    if document.get("retention_minimum_date") != RETENTION_MINIMUM_DATE or document.get("deletion_implemented") is not False:
        raise M8Error("configuration_not_consumable", "retention rule drifted")
    if document.get("denied") != DENIED_CONTRACT:
        raise M8Error("configuration_not_consumable", "the denial contract drifted")
    closure = _exact_mapping(document.get("closure"), CLOSURE_KEYS, "closure fields drifted")
    if closure.get("filtering_performed") is not False or closure.get("cleaner_invoked") is not False:
        raise M8Error("configuration_not_consumable", "closure claims filtering or a cleaner")
    if closure.get("replacement_or_replenishment_performed") is not False or closure.get("later_evaluation_required") is not True:
        raise M8Error("configuration_not_consumable", "closure accounting drifted")
    return True


def assert_inactive_configuration(document):
    assert_shared_scientific_contract(document)
    if document.get("document_status") != DOCUMENT_STATUS or document.get("consumable_by_executable_workflow") is not False:
        raise M8Error("configuration_not_consumable", "document status is not the inactive M8 status")
    execution = _exact_mapping(document.get("execution"), EXECUTION_FLAGS, "execution flags drifted")
    if any(execution[key] is not False for key in EXECUTION_FLAGS):
        raise M8Error("configuration_not_consumable", "execution flags must stay closed")
    if document.get("authorisation_entries") != [] or document.get("assembly_authorisation_entries") != []:
        raise M8Error("configuration_not_consumable", "an inactive document holds no authorisation entry")
    closure = document.get("closure")
    if closure.get("execution_authorised") is not False or closure.get("m8_execution_authorised") is not False:
        raise M8Error("configuration_not_consumable", "closure does not keep execution unauthorised")
    for key in _walk_keys(document):
        if key in INACTIVE_FORBIDDEN_KEYS:
            raise M8Error("configuration_not_consumable", "inactive configuration carries a binding key")
    return True


def _member_map(weight):
    return {
        "model_index.json": PIPELINE_INDEX_SHA256,
        "scheduler/scheduler_config.json": SCHEDULER_SHA256,
        "unet/config.json": D1_UNET_CONFIG_SHA256,
        WEIGHT_MEMBER: weight,
    }


def _assert_checkpoint_pins(checkpoints):
    if not isinstance(checkpoints, dict) or tuple(sorted(checkpoints)) != ("b1_generic", "d1_seed_43", "d1_seed_44"):
        raise M8Error("configuration_not_consumable", "checkpoint pins are missing")
    generic = checkpoints.get("b1_generic")
    if not isinstance(generic, dict) or tuple(sorted(generic)) != B1_CHECKPOINT_KEYS:
        raise M8Error("configuration_not_consumable", "B1 checkpoint fields drifted")
    if generic.get("weight_sha256") != B1_WEIGHT_SHA256:
        raise M8Error("configuration_not_consumable", "B1 weight pin drifted")
    if generic.get("unet_config_sha256") != B1_UNET_CONFIG_SHA256:
        raise M8Error("configuration_not_consumable", "B1 configuration pin drifted")
    if generic.get("encdec_weight_sha256") != ENCDEC_WEIGHT_SHA256:
        raise M8Error("configuration_not_consumable", "EncDec weight pin drifted")
    if generic.get("encdec_config_sha256") != ENCDEC_CONFIG_SHA256:
        raise M8Error("configuration_not_consumable", "EncDec configuration pin drifted")
    if generic.get("identity") != "b1_generic_released" or generic.get("diffusion_relative") != "configs/rnagenesis/diffusion":
        raise M8Error("configuration_not_consumable", "B1 checkpoint identity drifted")
    for seed, pin in D1_CHECKPOINTS.items():
        observed = checkpoints.get("d1_seed_{}".format(seed))
        if not isinstance(observed, dict) or tuple(sorted(observed)) != D1_CHECKPOINT_KEYS:
            raise M8Error("configuration_not_consumable", "a D1 checkpoint pin is missing")
        if observed.get("checkpoint_name") != pin["checkpoint_name"]:
            raise M8Error("configuration_not_consumable", "a D1 checkpoint name drifted")
        if observed.get("weight_sha256") != pin["weight_sha256"]:
            raise M8Error("configuration_not_consumable", "a D1 weight pin drifted")
        if observed.get("members_sha256") != _member_map(pin["weight_sha256"]):
            raise M8Error("configuration_not_consumable", "a D1 member pin drifted")
    return True


def classify_configuration(document):
    """A status flag is only a claim. Active documents still require the exact validators."""
    reject_m7_document(document)
    if not isinstance(document, dict):
        raise M8Error("configuration_not_consumable", "configuration is neither inactive nor a single-use active authorisation")
    status = document.get("document_status")
    consumable = document.get("consumable_by_executable_workflow")
    if status == DOCUMENT_STATUS and consumable is False:
        return "inactive"
    if status == ACTIVE_DOCUMENT_STATUS and consumable is True:
        return "generation_claim"
    if status == ACTIVE_ASSEMBLY_STATUS and consumable is True:
        return "assembly_claim"
    raise M8Error("configuration_not_consumable", "configuration is neither inactive nor a single-use active authorisation")


def _sha256_text(value, detail):
    if not isinstance(value, str) or SHA256_TEXT.fullmatch(value) is None:
        raise M8Error("authorisation_field_missing", detail)
    return value


def _sha40_text(value, detail):
    if not isinstance(value, str) or SHA40_TEXT.fullmatch(value) is None:
        raise M8Error("authorisation_commit_invalid", detail)
    return value


def _positive_int(value, detail):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise M8Error("authorisation_field_missing", detail)
    return value


def assert_ld_library_path_binding(value):
    """None passes no value. A string is an exact future binding, not a value chosen by this proposal."""
    if value is None:
        return None
    if not isinstance(value, str) or value == "" or len(value) > 4096 or value != value.strip():
        raise M8Error("environment_rejected", "the LD_LIBRARY_PATH binding is not null or one exact value", "runtime_identity")
    for component in value.split(":"):
        if component == "" or LD_LIBRARY_PATH_COMPONENT.fullmatch(component) is None or os.path.normpath(component) != component:
            raise M8Error("environment_rejected", "an LD_LIBRARY_PATH component is not an absolute normalised path", "runtime_identity")
        if ".." in component.split("/"):
            raise M8Error("environment_rejected", "an LD_LIBRARY_PATH component is not an absolute normalised path", "runtime_identity")
        assert_not_prohibited(component)
    return value


def assert_implementation_file_hashes(value):
    if not isinstance(value, dict) or tuple(sorted(value)) != IMPLEMENTATION_FILES:
        raise M8Error("provenance_mismatch", "implementation file hashes do not name the execution files")
    for path in IMPLEMENTATION_FILES:
        _sha256_text(value[path], "an implementation file hash is missing")
    return value


def active_configuration_identity(document):
    """SHA-256 of the active document with every active-configuration digest replaced by null.

    The digest cannot be a hash of the bytes that already contain it. Launch
    also records the SHA-256 of the exact raw bytes that were parsed.
    """
    projected = copy.deepcopy(document)

    def scrub(value):
        if isinstance(value, dict):
            for key in value:
                if key == "active_configuration_sha256":
                    value[key] = None
                else:
                    scrub(value[key])
        elif isinstance(value, list):
            for item in value:
                scrub(item)

    scrub(projected)
    return sha256_bytes(canonical_bytes(projected))


def assert_canonical_output_directory(path, run_root, authorisation_id):
    """String-only. The output must be a normalised direct child of the canonical run root."""
    if run_root != RUN_ROOT or RUN_ROOT != os.path.normpath(RUN_ROOT):
        raise M8Error("authorisation_scope_invalid", "the run root is not the canonical run root")
    if not isinstance(path, str) or not os.path.isabs(path) or os.path.normpath(path) != path:
        raise M8Error("authorisation_scope_invalid", "the output directory is not an absolute normalised path")
    if os.path.dirname(path) != run_root or os.path.basename(path) in ("", ".", ".."):
        raise M8Error("authorisation_scope_invalid", "the output directory is not a direct child of the run root")
    if os.path.basename(path) != authorisation_id:
        raise M8Error("authorisation_scope_invalid", "the output directory is not bound to the authorisation id")
    for root in (MRES_ROOT, RNAGENESIS_ROOT, EVALUATION_WORKTREE):
        if path == root or path.startswith(root + "/") or run_root == root or run_root.startswith(root + "/"):
            raise M8Error("prohibited_input", "an output path resolves inside a repository or the evaluation worktree", "input_denial")
    assert_not_prohibited(path, path, role="bound_output")
    return path


def assert_interpreter_binding(entry):
    if entry.get("interpreter_path") != PINNED_PYTHON:
        raise M8Error("python_interpreter_rejected", "the interpreter path is not the pinned interpreter")
    if entry.get("interpreter_resolved_path") != PINNED_RESOLVED_PYTHON:
        raise M8Error("python_interpreter_rejected", "the interpreter does not resolve to the pinned python3.8")
    if entry.get("interpreter_sha256") != PINNED_INTERPRETER_SHA256:
        raise M8Error("python_interpreter_rejected", "the interpreter hash is not the accepted digest")
    return {
        "path": PINNED_PYTHON,
        "resolved_path": PINNED_RESOLVED_PYTHON,
        "sha256": PINNED_INTERPRETER_SHA256,
    }


def assert_controller_interpreter(observed):
    """The running controller, including /proc/self/exe when that link exists."""
    if not isinstance(observed, dict) or tuple(sorted(observed)) != CONTROLLER_OBSERVATION_KEYS:
        raise M8Error("python_interpreter_rejected", "the controller interpreter observation is incomplete", "runtime_identity")
    if observed["executable"] not in (PINNED_PYTHON, PINNED_RESOLVED_PYTHON):
        raise M8Error("python_interpreter_rejected", "the controller is not running the pinned interpreter", "runtime_identity")
    if observed["resolved_path"] != PINNED_RESOLVED_PYTHON or observed["sha256"] != PINNED_INTERPRETER_SHA256:
        raise M8Error("python_interpreter_rejected", "the controller executable is not the pinned interpreter", "runtime_identity")
    if observed["python_version"] != ACCEPTED_RUNTIME_VERSIONS["python"]:
        raise M8Error("python_interpreter_rejected", "the controller Python version is not the pinned version", "runtime_identity")
    proc_target = observed["proc_self_exe"]
    proc_resolved = observed["proc_self_exe_resolved"]
    if proc_target is None and proc_resolved is None:
        return True
    if not isinstance(proc_target, str) or proc_target == "" or proc_resolved != PINNED_RESOLVED_PYTHON:
        raise M8Error("python_interpreter_rejected", "the controller proc identity does not match the pinned interpreter", "runtime_identity")
    return True


def assert_child_interpreter(observed):
    """Machine-readable result of the bound child interpreter probe."""
    if not isinstance(observed, dict) or tuple(sorted(observed)) != CHILD_OBSERVATION_KEYS:
        raise M8Error("python_interpreter_rejected", "the child interpreter observation is incomplete", "runtime_identity")
    if observed["executable"] not in (PINNED_PYTHON, PINNED_RESOLVED_PYTHON):
        raise M8Error("python_interpreter_rejected", "the child probe is not the pinned interpreter", "runtime_identity")
    if observed["resolved_path"] != PINNED_RESOLVED_PYTHON or observed["sha256"] != PINNED_INTERPRETER_SHA256:
        raise M8Error("python_interpreter_rejected", "the child executable is not the pinned interpreter", "runtime_identity")
    if observed["python_version"] != ACCEPTED_RUNTIME_VERSIONS["python"]:
        raise M8Error("python_interpreter_rejected", "the child Python version is not the pinned version", "runtime_identity")
    return True


def assert_generation_entry_schema(entry):
    """Pure entry schema. This does not stat an output directory or open a repository."""
    if not isinstance(entry, dict) or tuple(sorted(entry)) != ENTRY_KEYS:
        raise M8Error("authorisation_field_missing", "the generation entry fields drifted")
    if entry["consumed"] is not False or entry["single_use"] is not True or entry["reuse_permitted"] is not False:
        raise M8Error("authorisation_scope_invalid", "the entry is not a single unconsumed use")
    if entry["activation_status"] != "active_unconsumed":
        raise M8Error("authorisation_scope_invalid", "the entry is not active and unconsumed")
    arm = ARMS.get(entry["arm"])
    if arm is None:
        raise M8Error("authorisation_scope_invalid", "the entry does not name one M8 arm")
    if entry["condition_id"] != arm["condition_id"] or entry["technical_block"] != arm["technical_block"]:
        raise M8Error("authorisation_scope_invalid", "the entry condition or block does not match the arm")
    if entry["d1_training_seed"] != arm["d1_training_seed"] or entry["asset_kind"] != arm["asset_kind"]:
        raise M8Error("authorisation_scope_invalid", "the entry seed or asset kind does not match the arm")
    if isinstance(entry["physical_gpu"], bool) or not isinstance(entry["physical_gpu"], int) or entry["physical_gpu"] < 0:
        raise M8Error("authorisation_scope_invalid", "the physical GPU index is invalid")
    if entry["logical_device"] != LOGICAL_DEVICE:
        raise M8Error("authorisation_scope_invalid", "the logical device is not cuda:0")
    if not isinstance(entry["gpu_uuid"], str) or entry["gpu_uuid"] == "" or len(entry["gpu_uuid"]) > 80:
        raise M8Error("authorisation_scope_invalid", "the GPU UUID is missing")
    if not isinstance(entry["pci_bus"], str) or PCI_BUS_TEXT.fullmatch(entry["pci_bus"]) is None:
        raise M8Error("authorisation_scope_invalid", "the PCI bus identity is not exact")
    assert_interpreter_binding(entry)
    if entry.get("library_versions") != ACCEPTED_RUNTIME_VERSIONS:
        raise M8Error("runtime_identity", "library versions do not match the accepted runtime")
    assert_ld_library_path_binding(entry.get("ld_library_path"))
    _positive_int(entry.get("minimum_free_gpu_memory_bytes"), "the free-memory threshold is missing")
    _positive_int(entry.get("minimum_free_filesystem_bytes"), "the free-space threshold is missing")
    _sha256_text(entry.get("active_configuration_sha256"), "the active configuration identity is missing")
    _sha40_text(entry.get("authorization_parent_commit"), "the authorization parent commit is missing")
    _sha40_text(entry.get("executing_implementation_commit"), "the executing implementation commit is missing")
    assert_implementation_file_hashes(entry.get("implementation_file_hashes"))
    reject_authorisation_id(entry["authorisation_id"])
    if entry["run_id"] != entry["authorisation_id"]:
        raise M8Error("authorisation_scope_invalid", "the run id is not the authorisation id")
    assert_canonical_output_directory(entry["output_directory"], entry["run_root"], entry["authorisation_id"])
    return entry


def assert_active_closure(document):
    closure = document.get("closure")
    if closure.get("execution_authorised") is not True or closure.get("m8_execution_authorised") is not True:
        raise M8Error("configuration_not_consumable", "an active closure does not authorise its single use")
    return True


def assert_active_generation_document(document):
    """Exact generation authorisation. Status and consumable alone are not enough. No filesystem access."""
    assert_shared_scientific_contract(document)
    if document.get("document_status") != ACTIVE_DOCUMENT_STATUS or document.get("consumable_by_executable_workflow") is not True:
        raise M8Error("configuration_not_consumable", "document status is not an active generation authorisation")
    execution = _exact_mapping(document.get("execution"), EXECUTION_FLAGS, "execution flags drifted")
    if dict(execution) != GENERATION_EXECUTION:
        raise M8Error("configuration_not_consumable", "execution flags are not the generation authorisation")
    assert_active_closure(document)
    entries = document.get("authorisation_entries")
    if not isinstance(entries, list) or len(entries) != 1:
        raise M8Error("authorisation_scope_invalid", "an active document must hold exactly one generation entry")
    if document.get("assembly_authorisation_entries") != []:
        raise M8Error("authorisation_scope_invalid", "a generation authorisation also activates assembly")
    entry = assert_generation_entry_schema(entries[0])
    if entry["active_configuration_sha256"] != active_configuration_identity(document):
        raise M8Error("provenance_mismatch", "the active configuration identity does not match the document")
    return entry


def assert_assembly_entry_schema(entry):
    from_keys = (
        "activation_status",
        "active_configuration_sha256",
        "authorisation_id",
        "authorization_parent_commit",
        "condition_id",
        "consumed",
        "executing_implementation_commit",
        "implementation_file_hashes",
        "ld_library_path",
        "output_directory",
        "reuse_permitted",
        "run_root",
        "single_use",
        "sources",
    )
    if not isinstance(entry, dict) or tuple(sorted(entry)) != from_keys:
        raise M8Error("authorisation_field_missing", "the assembly entry fields drifted", "assembly")
    for forbidden in ("gpu_uuid", "logical_device", "pci_bus", "physical_gpu", "cuda_visible_devices", "interpreter_path"):
        if forbidden in entry:
            raise M8Error("authorisation_scope_invalid", "an assembly authorisation binds a GPU", "assembly")
    if entry["consumed"] is not False or entry["single_use"] is not True or entry["reuse_permitted"] is not False:
        raise M8Error("authorisation_scope_invalid", "the assembly entry is not a single unconsumed use", "assembly")
    if entry["activation_status"] != "active_unconsumed":
        raise M8Error("authorisation_scope_invalid", "the assembly entry is not active and unconsumed", "assembly")
    if entry["condition_id"] not in (CONDITION_B1, CONDITION_D1):
        raise M8Error("assembly_invalid", "the condition is not B1 or D1", "assembly")
    if entry.get("ld_library_path") is not None:
        raise M8Error("authorisation_scope_invalid", "CPU assembly does not bind a library path", "assembly")
    _sha256_text(entry.get("active_configuration_sha256"), "the active configuration identity is missing")
    _sha40_text(entry.get("authorization_parent_commit"), "the authorization parent commit is missing")
    _sha40_text(entry.get("executing_implementation_commit"), "the executing implementation commit is missing")
    assert_implementation_file_hashes(entry.get("implementation_file_hashes"))
    reject_authorisation_id(entry["authorisation_id"])
    sources = entry["sources"]
    if not isinstance(sources, list) or len(sources) != 2:
        raise M8Error("assembly_invalid", "assembly requires exactly two arm manifests", "assembly")
    blocks = [source.get("block") if isinstance(source, dict) else None for source in sources]
    if sorted(blocks) != ["A", "B"]:
        raise M8Error("assembly_invalid", "assembly requires block A and block B", "assembly")
    assert_canonical_output_directory(entry["output_directory"], entry["run_root"], entry["authorisation_id"])
    return entry


def assert_active_assembly_document(document):
    """Exact CPU assembly authorisation. No GPU flag and no generation entry are accepted."""
    assert_shared_scientific_contract(document)
    if document.get("document_status") != ACTIVE_ASSEMBLY_STATUS or document.get("consumable_by_executable_workflow") is not True:
        raise M8Error("configuration_not_consumable", "document status is not an active assembly authorisation")
    execution = _exact_mapping(document.get("execution"), EXECUTION_FLAGS, "execution flags drifted")
    if dict(execution) != ASSEMBLY_EXECUTION:
        raise M8Error("configuration_not_consumable", "execution flags are not the CPU assembly authorisation")
    if execution["gpu_identity_bound"] is not False or execution["generation_authorised"] is not False:
        raise M8Error("authorisation_scope_invalid", "an assembly authorisation binds a GPU", "assembly")
    assert_active_closure(document)
    if document.get("authorisation_entries") != []:
        raise M8Error("authorisation_scope_invalid", "an assembly authorisation also activates generation", "assembly")
    entries = document.get("assembly_authorisation_entries")
    if not isinstance(entries, list) or len(entries) != 1:
        raise M8Error("authorisation_scope_invalid", "an active assembly document must hold exactly one entry", "assembly")
    entry = assert_assembly_entry_schema(entries[0])
    if entry["active_configuration_sha256"] != active_configuration_identity(document):
        raise M8Error("provenance_mismatch", "the active configuration identity does not match the document", "assembly")
    return entry


def read_m8_config_bytes():
    path = config_path()
    reject_configuration_path(path)
    with open(path, "rb") as handle:
        return handle.read()


def d1_member_hashes(seed):
    pin = D1_CHECKPOINTS[seed]
    return _member_map(pin["weight_sha256"])


def checkpoint_identity(entry):
    if entry["asset_kind"] == "b1":
        return "b1_generic_released:" + B1_WEIGHT_SHA256
    pin = D1_CHECKPOINTS[entry["d1_training_seed"]]
    return pin["checkpoint_name"]


def b1_asset_table():
    root = RNAGENESIS_ROOT
    rows = [
        (os.path.join(root, "generation.py"), GENERATION_PY_SHA256, "generation_py"),
        (os.path.join(root, "configs/rnagenesis/diffusion/model_index.json"), PIPELINE_INDEX_SHA256, "b1_pipeline_index"),
        (os.path.join(root, "configs/rnagenesis/diffusion/scheduler/scheduler_config.json"), SCHEDULER_SHA256, "b1_scheduler"),
        (os.path.join(root, "configs/rnagenesis/diffusion/unet/config.json"), B1_UNET_CONFIG_SHA256, "b1_unet_config"),
        (
            os.path.join(root, "configs/rnagenesis/diffusion/unet/diffusion_pytorch_model.safetensors"),
            B1_WEIGHT_SHA256,
            "b1_unet_weights",
        ),
        (os.path.join(root, "configs/rnagenesis/autoencoder/config.json"), ENCDEC_CONFIG_SHA256, "encdec_config"),
        (os.path.join(root, "configs/rnagenesis/autoencoder/pytorch_model.bin"), ENCDEC_WEIGHT_SHA256, "encdec_weights"),
        (
            os.path.join(root, "models/autoencoder/encoder/biomap/config.json"),
            "bf7ef6843232f370f3f7fc37d608f85cb0ff0d75291eed35cef52213e34978f7",
            "biomap_encoder_config",
        ),
        (
            os.path.join(root, "models/autoencoder/decoder/progen_configs/config-progen2-small-rna_tokenizer_v2.json"),
            "42f15517e05ce96d78337fbc1bf20ffc580424fe88cbfcb2c81550b17cc7283e",
            "decoder_config",
        ),
        (
            os.path.join(root, "models/autoencoder/decoder/progen_configs/tokenizer_rna_v2.json"),
            "6d8a20879cec3544cf0f33b0d481fbd5ead6a2bead2dbf1649449172c8336921",
            "tokenizer",
        ),
    ]
    return rows


def d1_asset_table(seed):
    pin = D1_CHECKPOINTS[seed]
    directory = os.path.join(RUN_ROOT, pin["parent_directory_name"], pin["checkpoint_name"])
    members = d1_member_hashes(seed)
    rows = [(os.path.join(directory, member), digest, "d1_" + member) for member, digest in members.items()]
    rows.extend(row for row in b1_asset_table() if row[2] in ("generation_py", "encdec_config", "encdec_weights", "biomap_encoder_config", "decoder_config", "tokenizer"))
    return rows


def asset_table(entry):
    if entry["asset_kind"] == "b1":
        return b1_asset_table()
    return d1_asset_table(entry["d1_training_seed"])


def _signature(measured):
    return (measured.st_mode, measured.st_size, measured.st_nlink, getattr(measured, "st_ino", None), getattr(measured, "st_dev", None))


def inspect_asset(path, expected_hash, deps):
    assert_not_prohibited(path, role="asset")
    before = deps.lstat(path)
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise M8Error("asset_inspection_unsafe", "a pinned asset is not a regular file", "asset_verification")
    digest = deps.hash_file(path)
    after = deps.lstat(path)
    if _signature(before) != _signature(after):
        raise M8Error("asset_inspection_unsafe", "a pinned asset changed while it was hashed", "asset_verification")
    if digest != expected_hash:
        raise M8Error("asset_mismatch", "a pinned asset hash is not the expected digest", "asset_verification")
    return digest


def verify_assets(entry, deps):
    observed = {}
    for path, expected, role in asset_table(entry):
        observed[role] = inspect_asset(path, expected, deps)
    return observed


def diffusion_argument(entry):
    if entry["asset_kind"] == "b1":
        return "configs/rnagenesis/diffusion"
    pin = D1_CHECKPOINTS[entry["d1_training_seed"]]
    return os.path.join(RUN_ROOT, pin["parent_directory_name"], pin["checkpoint_name"])


def invocation_remark(invocation):
    return "_m8_i{:04d}_seed{}_len{}".format(
        invocation["invocation_index"], invocation["generation_seed"], invocation["requested_biological_length"]
    )


def invocation_folder(invocation):
    return "invocation_{:04d}".format(invocation["invocation_index"])


def predicted_filename(invocation):
    return "seqs_wo_guidance_top_p=0.95_2_{}{}.txt".format(invocation["line_count"], invocation_remark(invocation))


def relative_raw_path(invocation):
    return "raw/" + invocation_folder(invocation) + "/" + predicted_filename(invocation)


def build_generation_argv(invocation, interpreter, diffusion_path):
    if interpreter != PINNED_PYTHON or not os.path.isabs(interpreter):
        raise M8Error("python_interpreter_rejected", "the child command does not start with the absolute pinned interpreter")
    if invocation["batch_size"] <= 0 or invocation["batch_num"] <= 0:
        raise M8Error("invocation_invalid", "a zero-size invocation was requested", "generation_invocation_command")
    if invocation["batch_num"] > 1 and not (invocation["batch_size"] == 16 and invocation["kind"] == "full_group"):
        raise M8Error("invocation_invalid", "batch_num above 1 is only valid for a complete group of 16", "generation_invocation_command")
    if invocation["kind"] == "remainder" and (invocation["batch_num"] != 1 or invocation["batch_size"] >= 16):
        raise M8Error("invocation_invalid", "a remainder invocation is padded", "generation_invocation_command")
    if invocation["max_seq_len"] != invocation["requested_biological_length"] + 1:
        raise M8Error("invocation_invalid", "max_seq_len is not the requested length plus 1", "generation_invocation_command")
    argv = [
        interpreter,
        GENERATION_ENTRY,
        "--enc_dec_file",
        "configs/rnagenesis/autoencoder",
        "--dm_file",
        diffusion_path,
        "--decoder_config",
        "config-progen2-small-rna_tokenizer_v2",
        "--num_inference_steps",
        "50",
        "--batch_size",
        str(invocation["batch_size"]),
        "--batch_num",
        str(invocation["batch_num"]),
        "--seed",
        str(invocation["generation_seed"]),
        "--eta",
        "0",
        "--guidance_classifier_model_config",
        "configs/rnagenesis/classifier/mlp_160_32.yaml",
        "--max_seq_len",
        str(invocation["max_seq_len"]),
        "--do_sample",
        "--top_p",
        "0.95",
        "--top_k",
        "0",
        "--eos_token",
        "2",
        "--bos_token",
        "1",
        "--remark",
        invocation_remark(invocation),
        "--device",
        LOGICAL_DEVICE,
        "--target_class",
        "0",
        "--guidance_scale",
        "1.0",
        "--classifier_loss_type",
        "l2",
        "--recurrence_step",
        "1",
        "--guidance_start_step",
        "0",
        "--guidance_stop_step",
        "50",
        "--search_goal",
        "similarity",
        "--active_size",
        "1",
        "--branch_size",
        "1",
    ]
    for option in PROHIBITED_ARGV:
        if option in argv:
            raise M8Error("prohibited_generation_option", "a prohibited generation option is present", "generation_invocation_command")
    if "--truncate" in argv or "--guidance" in argv or "--do_sample" not in argv:
        raise M8Error("prohibited_generation_option", "sampler flags drifted", "generation_invocation_command")
    return argv


def resolve_ld_library_path(parent, expected):
    """The live parent value must equal the bound value. None drops any ambient value."""
    assert_ld_library_path_binding(expected)
    if not isinstance(parent, dict):
        raise M8Error("environment_rejected", "parent environment is missing", "runtime_identity")
    live = parent.get("LD_LIBRARY_PATH")
    if expected is None:
        return {"bound": False, "passed_to_child": False, "sha256": None}
    if live is None:
        raise M8Error("environment_rejected", "LD_LIBRARY_PATH is required by the authorisation but is absent", "runtime_identity")
    if live != expected:
        raise M8Error("environment_rejected", "LD_LIBRARY_PATH differs from the authorisation binding", "runtime_identity")
    return {"bound": True, "passed_to_child": True, "sha256": sha256_bytes(expected.encode("utf-8"))}


def build_child_environment(parent, physical_gpu, output_directory, ld_library_path=None):
    if not isinstance(parent, dict):
        raise M8Error("environment_rejected", "parent environment is missing", "runtime_identity")
    if not isinstance(physical_gpu, int) or isinstance(physical_gpu, bool) or physical_gpu < 0:
        raise M8Error("environment_rejected", "the physical GPU index is invalid", "runtime_identity")
    for name in parent:
        upper = name.upper()
        if upper in ("PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_AUDIT") or upper.startswith("GIT_"):
            if upper not in ("GIT_EDITOR", "GIT_SEQUENCE_EDITOR", "GIT_TERMINAL_PROMPT"):
                raise M8Error("environment_rejected", "a redirecting variable is set", "runtime_identity")
        if re.search(r"(TOKEN|SECRET|PASSWORD|CREDENTIAL|API_KEY)", upper):
            raise M8Error("environment_rejected", "a credential variable is set", "runtime_identity")
    library = resolve_ld_library_path(parent, ld_library_path)
    child = {}
    for name in ENVIRONMENT_ALLOW_LIST:
        if name in parent:
            child[name] = parent[name]
    child["PATH"] = FIXED_CHILD_PATH
    if library["bound"] is True:
        child["LD_LIBRARY_PATH"] = ld_library_path
    child["PYTHONDONTWRITEBYTECODE"] = "1"
    child["PYTHONNOUSERSITE"] = "1"
    child.update(OFFLINE_CONTROLS)
    child["CUDA_VISIBLE_DEVICES"] = str(physical_gpu)
    child["CUDA_DEVICE_ORDER"] = CUDA_DEVICE_ORDER
    child.update(dict(isolated_runtime_paths(output_directory)))
    child.update(FIXED_CHILD_ENVIRONMENT_CONTROLS)
    if ld_library_path is None:
        if "LD_LIBRARY_PATH" in child:
            raise M8Error("environment_rejected", "an unbound library path reached the child", "runtime_identity")
    elif child.get("LD_LIBRARY_PATH") != ld_library_path:
        raise M8Error("environment_rejected", "the child library path differs from the authorisation binding", "runtime_identity")
    return child


def decode_raw_line(blob):
    if not isinstance(blob, (bytes, bytearray)):
        raise M8Error("raw_output_invalid", "a raw line is not bytes", "output_mapping")
    try:
        return bytes(blob).decode("utf-8")
    except UnicodeDecodeError:
        return bytes(blob).decode("latin-1")


def map_invocation_lines(entry, invocation, raw_bytes):
    if not isinstance(raw_bytes, (bytes, bytearray)) or not bytes(raw_bytes).endswith(b"\n"):
        raise M8Error("raw_output_line_count", "raw output does not end with a newline", "output_read")
    lines = bytes(raw_bytes).split(b"\n")[:-1]
    expected = invocation["line_count"]
    if len(lines) != expected:
        raise M8Error("raw_output_line_count", "raw output line count does not match the invocation", "output_read")
    masters = invocation["master_attempt_indexes"]
    if len(masters) != expected:
        raise M8Error("raw_output_line_count", "master indexes do not match the invocation", "output_mapping")
    relative = relative_raw_path(invocation)
    digest = sha256_bytes(raw_bytes)
    records = []
    batch_size = invocation["batch_size"]
    for index, line in enumerate(lines):
        text = decode_raw_line(line)
        record = {
            "authorization_id": entry["authorisation_id"],
            "batch_number": index // batch_size,
            "checkpoint_identity": checkpoint_identity(entry),
            "condition_id": entry["condition_id"],
            "d1_training_seed": entry["d1_training_seed"],
            "generation_seed": invocation["generation_seed"],
            "invocation_index": invocation["invocation_index"],
            "line_index": index,
            "master_attempt_index": masters[index],
            "max_seq_len": invocation["max_seq_len"],
            "raw_decoded_text": text,
            "record_id": "m8:{}:master:{:05d}".format(entry["condition_id"], masters[index]),
            "requested_biological_length": invocation["requested_biological_length"],
            "run_id": entry["run_id"],
            "schema_version": RECORD_SCHEMA_VERSION,
            "source_raw_file_relative_path": relative,
            "source_raw_file_sha256": digest,
            "technical_block": entry["technical_block"],
            "within_batch_position": index % batch_size,
        }
        if tuple(sorted(record)) != RAW_RECORD_KEYS:
            raise M8Error("attempt_record_invalid", "a raw record field set drifted", "output_mapping")
        for forbidden in ("accepted", "biological", "cleaned_sequence", "filtered", "invalid", "rejected", "valid", "validity"):
            if forbidden in record:
                raise M8Error("attempt_record_invalid", "a raw record carries a classification field", "output_mapping")
        records.append(record)
    return records


def validate_generation_entry(entry):
    assert_generation_entry_schema(entry)
    if os.path.lexists(entry["output_directory"]):
        raise M8Error("output_directory_exists", "an active entry names an existing output directory", "output_directory")
    return entry


def _contains_value(value, wanted):
    if value == wanted:
        return True
    if isinstance(value, dict):
        return any(_contains_value(item, wanted) for item in value.values())
    if isinstance(value, list):
        return any(_contains_value(item, wanted) for item in value)
    return False


def _porcelain_lines(porcelain):
    if not isinstance(porcelain, str):
        raise M8Error("provenance_mismatch", "git status porcelain could not be read", "provenance")
    return [line for line in porcelain.splitlines() if line != ""]


def _split_porcelain(line):
    if len(line) < 4 or line[2] != " ":
        raise M8Error("provenance_mismatch", "git status porcelain could not be read", "provenance")
    return line[0], line[1], line[3:]


def _normalise_untracked_path(path):
    normalised = path.replace("\\", "/").strip()
    if normalised.startswith("./"):
        normalised = normalised[2:]
    if len(normalised) >= 2 and normalised[0] == '"' and normalised[-1] == '"':
        normalised = normalised[1:-1]
    return normalised


def assert_mres_repository_clean(porcelain):
    """Local clean-tree policy. This does not import the M6 contract."""
    if _porcelain_lines(porcelain):
        raise M8Error("provenance_mismatch", "MRes tracked state is not clean", "provenance")
    return True


def _under_known_rnagenesis_prefix(path):
    for prefix in KNOWN_RNAGENESIS_UNTRACKED:
        if path == prefix or path.startswith(prefix):
            return True
    return False


def assert_rnagenesis_repository(directory_porcelain, file_porcelain):
    """Exact reviewed untracked fingerprint, then rejection of unexpected source and configuration files."""
    if not isinstance(file_porcelain, str):
        raise M8Error("provenance_mismatch", "RNAGenesis file porcelain is required", "provenance")
    observed = []
    for line in _porcelain_lines(directory_porcelain):
        index_status, worktree_status, path = _split_porcelain(line)
        if index_status == "?" and worktree_status == "?":
            observed.append(_normalise_untracked_path(path))
            continue
        raise M8Error("provenance_mismatch", "RNAGenesis tracked changes are present", "provenance")
    if sorted(observed) != sorted(KNOWN_RNAGENESIS_UNTRACKED):
        raise M8Error("provenance_mismatch", "untracked path is not the known RNAGenesis asset fingerprint", "provenance")
    for line in _porcelain_lines(file_porcelain):
        index_status, worktree_status, raw_path = _split_porcelain(line)
        if index_status == "?" and worktree_status == "?":
            path = _normalise_untracked_path(raw_path)
        else:
            raise M8Error("provenance_mismatch", "RNAGenesis tracked changes are present", "provenance")
        if not _under_known_rnagenesis_prefix(path):
            raise M8Error("provenance_mismatch", "untracked path is outside the reviewed fingerprint", "provenance")
        suffix = os.path.splitext(path)[1].lower()
        if suffix in SOURCE_SUFFIXES and "__pycache__/" not in path:
            raise M8Error("provenance_mismatch", "unexpected untracked source file", "provenance")
        if suffix in CONFIG_SUFFIXES and path not in KNOWN_UNTRACKED_CONFIG_FILES:
            raise M8Error("provenance_mismatch", "unexpected untracked configuration file", "provenance")
    return True


def _revision_row(row):
    if not isinstance(row, dict) or tuple(sorted(row)) != REVISION_ROW_KEYS:
        raise M8Error("authorisation_commit_invalid", "the authorization history was not observed", "provenance")
    commit = _sha40_text(row.get("commit"), "an authorization history commit is missing")
    parents = row.get("parents")
    if not isinstance(parents, (list, tuple)) or len(parents) != 1:
        raise M8Error("authorisation_commit_invalid", "the authorization history is not linear", "provenance")
    parent = _sha40_text(parents[0], "an authorization history parent is missing")
    changed = row.get("changed_files")
    if isinstance(changed, list):
        changed = tuple(changed)
    if not isinstance(changed, tuple) or any(not isinstance(item, str) for item in changed):
        raise M8Error("authorisation_delta_invalid", "an authorization history file list is missing", "provenance")
    return commit, parent, changed


def assert_linear_authorization_range(entry, observation, head):
    """Every commit after the implementation commit, not only the final parent-to-HEAD delta."""
    rows = observation.get("revision_range")
    if not isinstance(rows, (list, tuple)) or len(rows) < 1:
        raise M8Error("authorisation_commit_invalid", "the authorization history was not observed", "provenance")
    expected_parent = entry["executing_implementation_commit"]
    last_changed = None
    for row in rows:
        commit, parent, changed = _revision_row(row)
        if parent != expected_parent:
            raise M8Error("authorisation_commit_invalid", "the authorization history is not linear", "provenance")
        if changed != PERMITTED_AUTHORIZATION_DELTA:
            raise M8Error(
                "authorisation_delta_invalid",
                "a commit after the implementation changes a file other than the M8 configuration",
                "provenance",
            )
        expected_parent = commit
        last_changed = changed
    if expected_parent != head:
        raise M8Error("authorisation_commit_invalid", "the authorization history does not end at live HEAD", "provenance")
    observed_changed = observation.get("changed_files")
    if isinstance(observed_changed, list):
        observed_changed = tuple(observed_changed)
    if observed_changed != last_changed:
        raise M8Error("authorisation_delta_invalid", "the authorization commit changes a file other than the M8 configuration", "provenance")
    return True


def assert_repository_binding(entry, observation):
    """Live HEAD is the authorization commit. It is not required to equal the proposal base."""
    if not isinstance(observation, dict):
        raise M8Error("provenance_mismatch", "repository observation is missing", "provenance")
    if observation.get("mres_branch") != MRES_BRANCH:
        raise M8Error("provenance_mismatch", "the MRes branch is not main", "provenance")
    head = _sha40_text(observation.get("mres_head"), "the live authorization commit is missing")
    parents = observation.get("mres_parents")
    if not isinstance(parents, (list, tuple)) or len(parents) != 1:
        raise M8Error("authorisation_commit_invalid", "live HEAD must have exactly one parent", "provenance")
    parent = _sha40_text(parents[0], "the live parent commit is missing")
    if parent != entry["authorization_parent_commit"]:
        raise M8Error("authorisation_commit_invalid", "live HEAD parent is not the bound authorization parent", "provenance")
    if head == parent:
        raise M8Error("authorisation_commit_invalid", "the authorization commit and its parent are the same", "provenance")
    executing = _sha40_text(entry["executing_implementation_commit"], "the executing implementation commit is missing")
    if executing == head:
        raise M8Error("authorisation_commit_invalid", "the executing implementation commit is the authorization commit", "provenance")
    if observation.get("executing_implementation_is_ancestor") is not True:
        raise M8Error("authorisation_commit_invalid", "the executing implementation commit is not an ancestor of live HEAD", "provenance")
    if observation.get("mres_origin_main") != head:
        raise M8Error("provenance_mismatch", "origin/main is not the live authorization commit", "provenance")
    assert_linear_authorization_range(entry, observation, head)
    assert_mres_repository_clean(observation.get("mres_porcelain"))
    assert_rnagenesis_repository(
        observation.get("rnagenesis_directory_porcelain"),
        observation.get("rnagenesis_file_porcelain"),
    )
    if observation.get("rnagenesis_branch") != RNAGENESIS_BRANCH or observation.get("rnagenesis_head") != RNAGENESIS_COMMIT:
        raise M8Error("provenance_mismatch", "RNAGenesis branch or commit does not match the pin", "provenance")
    at_commit = observation.get("file_sha256_at_implementation")
    working = observation.get("file_sha256_working_tree")
    if not isinstance(at_commit, dict) or not isinstance(working, dict):
        raise M8Error("provenance_mismatch", "implementation file hashes were not observed", "provenance")
    for path, digest in entry["implementation_file_hashes"].items():
        if at_commit.get(path) != digest or working.get(path) != digest:
            raise M8Error("provenance_mismatch", "an execution file hash does not match the implementation commit", "provenance")
    if _contains_value(entry, head):
        raise M8Error("authorisation_commit_invalid", "the tracked authorisation contains the live authorization commit", "provenance")
    return head


def _call_lstat(deps, path):
    method = getattr(deps, "path_lstat", None)
    if method is None:
        return os.lstat(path)
    return method(path)


def _call_realpath(deps, path):
    method = getattr(deps, "realpath", None)
    if method is None:
        return os.path.realpath(path)
    return method(path)


def assert_no_symlinked_ancestor(path, deps, stage="path_safety"):
    """Reject a symlink at the path or any existing ancestor. Missing leaves are skipped."""
    current = os.path.abspath(path)
    while True:
        try:
            measured = _call_lstat(deps, current)
        except FileNotFoundError:
            parent = os.path.dirname(current)
            if parent == current:
                return True
            current = parent
            continue
        if stat.S_ISLNK(measured.st_mode):
            raise M8Error("path_unsafe", "a path ancestor is a symlink", stage)
        parent = os.path.dirname(current)
        if parent == current:
            return True
        current = parent


def assert_run_root_is_real(run_root, deps):
    """Production requires the canonical run root to resolve to itself. A symlinked root is refused."""
    if run_root != RUN_ROOT or not isinstance(run_root, str) or os.path.normpath(run_root) != run_root:
        raise M8Error("authorisation_scope_invalid", "the run root is not the canonical run root", "path_safety")
    try:
        measured = _call_lstat(deps, run_root)
    except FileNotFoundError:
        raise M8Error("path_unsafe", "the run root is not a real directory", "path_safety")
    if stat.S_ISLNK(measured.st_mode) or not stat.S_ISDIR(measured.st_mode):
        raise M8Error("path_unsafe", "the run root is not a real directory", "path_safety")
    resolved = _call_realpath(deps, run_root)
    if RUN_ROOT == CANONICAL_RUN_ROOT and (run_root != CANONICAL_RUN_ROOT or resolved != CANONICAL_RUN_ROOT):
        raise M8Error("path_unsafe", "the run root is not the canonical run root", "path_safety")
    return resolved


def assert_output_parent_is_safe(entry, deps):
    """The output must be a missing direct child whose resolved parent cannot enter a repository."""
    output = entry["output_directory"]
    run_root = entry["run_root"]
    try:
        _call_lstat(deps, output)
    except FileNotFoundError:
        pass
    else:
        raise M8Error("output_directory_exists", "an active entry names an existing output directory", "output_directory")
    if os.path.dirname(output) != run_root:
        raise M8Error("authorisation_scope_invalid", "the output directory is not a direct child of the run root", "path_safety")
    resolved_parent = _call_realpath(deps, run_root)
    if resolved_parent != _call_realpath(deps, os.path.dirname(output)):
        raise M8Error("path_unsafe", "the output parent does not resolve to the run root", "path_safety")
    for prohibited in PROHIBITED_RESOLVED_ROOTS:
        if resolved_parent == prohibited or resolved_parent.startswith(prohibited + os.sep):
            raise M8Error("prohibited_input", "an output path resolves inside a repository or the evaluation worktree", "path_safety")
    return True


def assert_generation_filesystem_preflight(entry, deps):
    """Real path checks. Active-document validation stays free of filesystem access."""
    assert_run_root_is_real(entry["run_root"], deps)
    assert_output_parent_is_safe(entry, deps)
    assert_no_symlinked_ancestor(entry["run_root"], deps)
    if entry["asset_kind"] == "d1":
        assert_no_symlinked_ancestor(FINAL_SELECTION_MANIFEST_PATH, deps)
        directory = diffusion_argument(entry)
        assert_no_symlinked_ancestor(directory, deps)
        for relative in CHECKPOINT_MEMBERS:
            assert_no_symlinked_ancestor(os.path.join(directory, relative.replace("/", os.sep)), deps)
    for path, _digest, _role in asset_table(entry):
        assert_no_symlinked_ancestor(path, deps)
    return True


def assert_assembly_filesystem_preflight(entry, deps):
    assert_run_root_is_real(entry["run_root"], deps)
    assert_output_parent_is_safe(entry, deps)
    assert_no_symlinked_ancestor(entry["run_root"], deps)
    for source in entry["sources"]:
        path = source["path"]
        arm_directory = os.path.dirname(path)
        assert_no_symlinked_ancestor(arm_directory, deps)
        assert_no_symlinked_ancestor(path, deps)
    return True


def assert_resolved_inside_directory(path, directory, deps):
    assert_no_symlinked_ancestor(path, deps, stage="assembly")
    resolved_directory = _call_realpath(deps, directory)
    resolved_path = _call_realpath(deps, path)
    prefix = resolved_directory if resolved_directory.endswith(os.sep) else resolved_directory + os.sep
    if resolved_path != resolved_directory and not resolved_path.startswith(prefix):
        raise M8Error("assembly_invalid", "a raw file resolves outside its arm directory", "assembly")
    return resolved_path


def assert_gpu_and_storage(entry, probe):
    """Stop when identity or availability differs. This does not terminate or move any process."""
    required = (
        "compute_processes",
        "cuda_visible_devices",
        "filesystem_free_bytes",
        "logical_device",
        "memory_free_bytes",
        "memory_total_bytes",
        "pci_bus",
        "physical_gpu",
        "uuid",
    )
    if not isinstance(probe, dict) or tuple(sorted(probe)) != required:
        raise M8Error("gpu_probe_invalid", "the GPU and storage probe is incomplete", "gpu_probe")
    if probe["logical_device"] != LOGICAL_DEVICE or probe["physical_gpu"] != entry["physical_gpu"]:
        raise M8Error("gpu_probe_invalid", "the GPU probe does not match the authorisation", "gpu_probe")
    if probe["uuid"] != entry["gpu_uuid"]:
        raise M8Error("gpu_probe_invalid", "the GPU UUID does not match the authorisation", "gpu_probe")
    if probe["pci_bus"] != entry["pci_bus"]:
        raise M8Error("gpu_probe_invalid", "the PCI bus identity does not match the authorisation", "gpu_probe")
    if str(probe["cuda_visible_devices"]) != str(entry["physical_gpu"]):
        raise M8Error("gpu_probe_invalid", "the logical mapping is not cuda:0 on the selected GPU", "gpu_probe")
    processes = probe["compute_processes"]
    if isinstance(processes, bool) or not isinstance(processes, int) or processes != 0:
        raise M8Error("gpu_probe_invalid", "the selected GPU has a compute process", "gpu_probe")
    for key in ("memory_free_bytes", "memory_total_bytes", "filesystem_free_bytes"):
        if isinstance(probe[key], bool) or not isinstance(probe[key], int) or probe[key] < 0:
            raise M8Error("gpu_probe_invalid", "a capacity reading is not an integer byte count", "gpu_probe")
    if probe["memory_free_bytes"] > probe["memory_total_bytes"]:
        raise M8Error("gpu_probe_invalid", "free GPU memory exceeds the device total", "gpu_probe")
    if probe["memory_free_bytes"] < entry["minimum_free_gpu_memory_bytes"]:
        raise M8Error("gpu_probe_invalid", "free GPU memory is below the authorised threshold", "gpu_probe")
    if probe["filesystem_free_bytes"] < entry["minimum_free_filesystem_bytes"]:
        raise M8Error("insufficient_free_space", "free space at the run root is below the authorised threshold", "storage_probe")
    return dict(probe)


def _selected_set_digest(rows):
    ordered = sorted(rows, key=lambda row: row["seed"])
    return sha256_bytes(canonical_bytes(ordered))


def verify_selected_set(entry, deps):
    """Reopen the sealed final-selection manifest. Do not rewrite it."""
    if entry["asset_kind"] != "d1":
        return None
    blob = refuse_before_open(FINAL_SELECTION_MANIFEST_PATH, deps.read_bytes, role="final_selection")
    if not isinstance(blob, (bytes, bytearray)):
        raise M8Error("selected_set_mismatch", "the final-selection manifest was not read as bytes", "selected_set")
    blob = bytes(blob)
    if len(blob) != FINAL_SELECTION_MANIFEST_BYTES or sha256_bytes(blob) != FINAL_SELECTION_MANIFEST_SHA256:
        raise M8Error("selected_set_mismatch", "the final-selection manifest identity does not match the pin", "selected_set")
    again = refuse_before_open(FINAL_SELECTION_MANIFEST_PATH, deps.read_bytes, role="final_selection")
    if bytes(again) != blob:
        raise M8Error("selected_set_mismatch", "the final-selection manifest changed while it was read", "selected_set")
    try:
        manifest = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise M8Error("selected_set_mismatch", "the final-selection manifest is not UTF-8 JSON", "selected_set")
    if not isinstance(manifest, dict) or manifest.get("selection_outcome") != "selected_set_complete":
        raise M8Error("selected_set_mismatch", "the final-selection outcome is not the approved set", "selected_set")
    rows = manifest.get("selected_set")
    if not isinstance(rows, list) or len(rows) != 2:
        raise M8Error("selected_set_mismatch", "the final-selection manifest does not hold two selections", "selected_set")
    normalised = []
    for row in rows:
        if not isinstance(row, dict) or tuple(sorted(row)) != SELECTED_ROW_KEYS:
            raise M8Error("selected_set_mismatch", "a selected-set row field set drifted", "selected_set")
        normalised.append({key: (dict(row[key]) if key == "members_sha256" else row[key]) for key in SELECTED_ROW_KEYS})
    if _selected_set_digest(normalised) != manifest.get("selected_set_sha256"):
        raise M8Error("selected_set_mismatch", "the selected-set digest does not match its rows", "selected_set")
    if manifest.get("selected_set_sha256") != SELECTED_SET_SHA256:
        raise M8Error("selected_set_mismatch", "the selected-set digest is not the approved digest", "selected_set")
    seed = entry["d1_training_seed"]
    matches = [row for row in normalised if row["seed"] == seed]
    if len(matches) != 1:
        raise M8Error("selected_set_mismatch", "the requested seed is not one approved selection", "selected_set")
    pin = D1_CHECKPOINTS[seed]
    chosen = matches[0]
    if chosen["checkpoint_name"] != pin["checkpoint_name"] or chosen["weight_sha256"] != pin["weight_sha256"]:
        raise M8Error("selected_set_mismatch", "the requested checkpoint is not the approved selection", "selected_set")
    if chosen["members_sha256"] != d1_member_hashes(seed):
        raise M8Error("selected_set_mismatch", "the requested member hashes are not the approved selection", "selected_set")
    if chosen["epoch"] != 5 or chosen["update"] != 105:
        raise M8Error("selected_set_mismatch", "the requested checkpoint is not epoch 5 update 105", "selected_set")
    return {
        "byte_count": len(blob),
        "checkpoint_name": chosen["checkpoint_name"],
        "epoch": chosen["epoch"],
        "manifest_sha256": sha256_bytes(blob),
        "members_sha256": dict(chosen["members_sha256"]),
        "path": FINAL_SELECTION_MANIFEST_PATH,
        "seed": seed,
        "selected_set_sha256": manifest.get("selected_set_sha256"),
        "update": chosen["update"],
    }


def not_applicable_selected_set():
    return {"applicable": False}


def selected_set_evidence(entry, verified):
    """D1 stores the successful verification. B1 stores an explicit not-applicable record."""
    if entry["asset_kind"] != "d1":
        if verified is not None:
            raise M8Error("selected_set_mismatch", "B1 recorded a selected set", "selected_set")
        return not_applicable_selected_set()
    if not isinstance(verified, dict):
        raise M8Error("selected_set_mismatch", "D1 selected-set evidence is missing", "selected_set")
    return {
        "applicable": True,
        "byte_count": verified["byte_count"],
        "checkpoint_name": verified["checkpoint_name"],
        "epoch": verified["epoch"],
        "manifest_path": verified["path"],
        "manifest_sha256": verified["manifest_sha256"],
        "members_sha256": dict(verified["members_sha256"]),
        "seed": verified["seed"],
        "selected_set_sha256": verified["selected_set_sha256"],
        "update": verified["update"],
    }


def pinned_d1_selected_set_evidence(seed):
    """Approved pins for a synthetic sealed arm. This does not open the sealed manifest."""
    pin = D1_CHECKPOINTS[seed]
    return {
        "applicable": True,
        "byte_count": FINAL_SELECTION_MANIFEST_BYTES,
        "checkpoint_name": pin["checkpoint_name"],
        "epoch": 5,
        "manifest_path": FINAL_SELECTION_MANIFEST_PATH,
        "manifest_sha256": FINAL_SELECTION_MANIFEST_SHA256,
        "members_sha256": d1_member_hashes(seed),
        "seed": seed,
        "selected_set_sha256": SELECTED_SET_SHA256,
        "update": 105,
    }


def expected_asset_inventory(condition_id, block):
    if condition_id == CONDITION_B1:
        rows = b1_asset_table()
    elif condition_id == CONDITION_D1:
        rows = d1_asset_table(43 if block == "A" else 44)
    else:
        raise M8Error("assembly_invalid", "the condition is not B1 or D1", "assembly")
    return {role: digest for _path, digest, role in rows}


def runtime_repository_identity(authorization_commit):
    """mres_commit is the observed authorization HEAD. The proposal base is a separate field."""
    _sha40_text(authorization_commit, "the live authorization commit is missing")
    return {
        "mres_branch": MRES_BRANCH,
        "mres_commit": authorization_commit,
        "proposal_base_commit": MRES_COMMIT,
        "rnagenesis_branch": RNAGENESIS_BRANCH,
        "rnagenesis_commit": RNAGENESIS_COMMIT,
    }


def isolated_runtime_paths(output_directory):
    base = os.path.abspath(output_directory)
    cache = os.path.join(base, "isolated_runtime_cache")
    return (
        ("HOME", os.path.join(base, "isolated_home")),
        ("TMPDIR", os.path.join(base, "isolated_tmp")),
        ("XDG_CACHE_HOME", cache),
        ("PYTHONPYCACHEPREFIX", os.path.join(base, "python_pycache")),
        ("HF_HOME", os.path.join(cache, "huggingface")),
        ("TORCH_HOME", os.path.join(cache, "torch")),
        ("TRITON_CACHE_DIR", os.path.join(cache, "triton")),
        ("CUDA_CACHE_PATH", os.path.join(cache, "cuda")),
        ("MPLCONFIGDIR", os.path.join(cache, "matplotlib")),
    )


def create_isolated_runtime_directories(output_directory):
    """Create every bound runtime directory inside the consumed output, including TMPDIR."""
    resolved_output = os.path.realpath(output_directory)
    created = {}
    for name, path in isolated_runtime_paths(output_directory):
        os.mkdir(path, 0o700)
        measured = os.lstat(path)
        if stat.S_ISLNK(measured.st_mode) or not stat.S_ISDIR(measured.st_mode):
            raise M8Error("environment_rejected", "an isolated runtime directory is not a real directory", "runtime_identity")
        resolved = os.path.realpath(path)
        if resolved != path or not resolved.startswith(resolved_output + os.sep):
            raise M8Error("environment_rejected", "an isolated runtime directory resolves outside the output directory", "runtime_identity")
        created[name] = path
    temporary = created["TMPDIR"]
    if not os.path.isdir(temporary) or os.path.islink(temporary):
        raise M8Error("environment_rejected", "TMPDIR does not exist inside the output directory", "runtime_identity")
    return created


def assert_d1_checkpoint_inventory(entry, deps):
    """The checkpoint directory contains exactly the four expected regular single-link members."""
    directory = diffusion_argument(entry)
    assert_not_prohibited(directory, role="asset")
    listdir = deps.listdir
    root_names = set(listdir(directory))
    if root_names != {"model_index.json", "scheduler", "unet"}:
        raise M8Error("asset_inspection_unsafe", "the D1 checkpoint tree is not the four-member layout", "asset_verification")
    if set(listdir(os.path.join(directory, "scheduler"))) != {"scheduler_config.json"}:
        raise M8Error("asset_inspection_unsafe", "the D1 scheduler directory is not the expected member", "asset_verification")
    if set(listdir(os.path.join(directory, "unet"))) != {"config.json", "diffusion_pytorch_model.safetensors"}:
        raise M8Error("asset_inspection_unsafe", "the D1 unet directory is not the expected members", "asset_verification")
    for relative in CHECKPOINT_MEMBERS:
        path = os.path.join(directory, relative.replace("/", os.sep))
        measured = deps.lstat(path)
        if stat.S_ISLNK(measured.st_mode) or not stat.S_ISREG(measured.st_mode) or measured.st_nlink != 1:
            raise M8Error("asset_inspection_unsafe", "a D1 checkpoint member is not a single regular file", "asset_verification")
    return directory


def provenance_from_entry(entry, head, raw_sha256):
    return {
        "active_configuration_raw_sha256": raw_sha256,
        "active_configuration_sha256": entry["active_configuration_sha256"],
        "authorization_commit": head,
        "authorization_parent_commit": entry["authorization_parent_commit"],
        "executing_implementation_commit": entry["executing_implementation_commit"],
        "implementation_file_hashes": dict(entry["implementation_file_hashes"]),
        "origin_main": head,
    }


def _fsync_directory(path):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    handle = os.open(path, flags)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


def write_atomic_bytes(directory, name, blob):
    """Write every byte, fsync the file, rename, fsync the directory, and remove the temporary on any failure."""
    if not isinstance(name, str) or "/" in name or name.startswith("."):
        raise M8Error("evidence_write_failed", "an evidence name is not a single safe path segment", "evidence_write")
    final = os.path.join(directory, name)
    temporary = os.path.join(directory, "." + name + ".tmp")
    if os.path.lexists(final) or os.path.lexists(temporary):
        raise M8Error("evidence_write_failed", "an evidence file already exists", "evidence_write")
    view = blob if isinstance(blob, bytes) else blob.encode("utf-8")
    if not isinstance(view, bytes):
        raise M8Error("evidence_write_failed", "evidence bytes are missing", "evidence_write")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        try:
            pending = memoryview(view)
            while len(pending) > 0:
                written = os.write(descriptor, pending)
                if written <= 0:
                    raise OSError("short write made no progress")
                pending = pending[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, final)
        _fsync_directory(directory)
    except BaseException:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise
    measured = os.lstat(final)
    if stat.S_ISLNK(measured.st_mode) or not stat.S_ISREG(measured.st_mode) or measured.st_nlink != 1:
        raise M8Error("evidence_write_failed", "an evidence file is not a single regular file", "evidence_write")
    return final


def _consume_directory(entry, provenance):
    output = entry["output_directory"]
    os.mkdir(output, 0o755)
    _fsync_directory(os.path.dirname(output))
    payload = {
        "active_configuration_raw_sha256": provenance["active_configuration_raw_sha256"],
        "active_configuration_sha256": provenance["active_configuration_sha256"],
        "authorisation_id": entry["authorisation_id"],
        "authorization_commit": provenance["authorization_commit"],
        "authorization_parent_commit": provenance["authorization_parent_commit"],
        "consumed": True,
        "consumption_state": "consumed_output_created",
        "executing_implementation_commit": provenance["executing_implementation_commit"],
        "implementation_file_hashes": dict(provenance["implementation_file_hashes"]),
        "origin_main": provenance["origin_main"],
        "resumable": False,
        "reuse_permitted": False,
        "schema_version": "m8-consumption-record-1",
    }
    write_atomic_bytes(output, CONSUMPTION_NAME, canonical_bytes(payload))
    return payload


def _failure_payload(entry, error, provenance, progress):
    completed = 0 if progress is None else progress.get("completed_invocation_count")
    failing = None if progress is None else progress.get("failing_invocation_index")
    if not isinstance(completed, int) or isinstance(completed, bool) or completed < 0:
        completed = 0
    if failing is not None and (isinstance(failing, bool) or not isinstance(failing, int)):
        failing = None
    payload = {
        "active_configuration_raw_sha256": None if provenance is None else provenance.get("active_configuration_raw_sha256"),
        "active_configuration_sha256": None if provenance is None else provenance.get("active_configuration_sha256"),
        "authorisation_id": entry.get("authorisation_id"),
        "authorization_commit": None if provenance is None else provenance.get("authorization_commit"),
        "authorization_parent_commit": None if provenance is None else provenance.get("authorization_parent_commit"),
        "code": error.code,
        "completed_invocation_count": completed,
        "completion_state": "consumed_failed",
        "consumed": True,
        "detail": error.detail,
        "executing_implementation_commit": None if provenance is None else provenance.get("executing_implementation_commit"),
        "failing_invocation_index": failing,
        "implementation_file_hashes": None if provenance is None else dict(provenance.get("implementation_file_hashes") or {}),
        "manifest_written": False,
        "origin_main": None if provenance is None else provenance.get("origin_main"),
        "raw_attempt_count": None,
        "resumable": False,
        "reuse_permitted": False,
        "schema_version": "m8-failure-record-1",
        "stage": error.stage,
    }
    if SEQUENCE_RUN.search(payload["detail"]) is not None:
        payload["detail"] = "the failure detail was withheld"
    return payload


def record_consumed_failure(entry, error, provenance=None, progress=None):
    output = entry["output_directory"]
    if not os.path.isdir(output):
        return None
    if os.path.lexists(os.path.join(output, MANIFEST_NAME)):
        raise M8Error("evidence_write_failed", "a failed arm already has a success manifest", "evidence_write")
    safe = error if isinstance(error, M8Error) else M8Error("generation_failed", "an unexpected failure was contained")
    payload = _failure_payload(entry, safe, provenance, progress)
    if not os.path.lexists(os.path.join(output, FAILURE_NAME)):
        write_atomic_bytes(output, FAILURE_NAME, canonical_bytes(payload))
    return payload


def _load_schedule(deps):
    raw = refuse_before_open(schedule.LENGTH_VECTOR_PATH, deps.read_bytes, role="length_vector")
    lengths = schedule.assert_pinned_length_vector(raw)
    built = schedule.build_schedule(lengths)
    if dict(built["hashes"], source_length_vector_sha256=schedule.LENGTH_VECTOR_SHA256) != schedule.EXPECTED_SCHEDULE_HASHES:
        raise M8Error("schedule_invalid", "the recomputed schedule hashes are not the pinned hashes", "schedule")
    return built


def _run_invocation(entry, invocation, child_env, deps):
    folder = os.path.join(entry["output_directory"], "raw", invocation_folder(invocation))
    os.makedirs(folder)
    argv = build_generation_argv(invocation, entry["interpreter_path"], diffusion_argument(entry))
    argv.extend(["--superfolder", os.path.join(entry["output_directory"], "raw"), "--mid_folder", invocation_folder(invocation)])
    if "--truncate" in argv:
        raise M8Error("prohibited_generation_option", "truncate was requested", "generation_invocation_command")
    completed = deps.subprocess_run(argv, cwd=RNAGENESIS_ROOT, env=child_env, shell=False)
    if getattr(completed, "returncode", 1) != 0:
        raise M8Error("generation_process_failed", "generation.py exited nonzero", "generation_invocation_spawn")
    relative = relative_raw_path(invocation)
    path = os.path.join(entry["output_directory"], relative.replace("/", os.sep))
    assert_not_prohibited(path, entry["output_directory"], role="bound_output")
    measured = os.lstat(path)
    if stat.S_ISLNK(measured.st_mode) or not stat.S_ISREG(measured.st_mode) or measured.st_nlink != 1:
        raise M8Error("raw_output_invalid", "a raw output is not a single regular file", "output_read")
    with open(path, "rb") as handle:
        blob = handle.read()
    if sha256_bytes(blob) != _sha256_file(path):
        raise M8Error("raw_output_invalid", "a raw output changed while it was read", "output_read")
    records = map_invocation_lines(entry, invocation, blob)
    return {
        "argv": argv,
        "bytes": blob,
        "env": child_env,
        "records": records,
        "relative_path": relative,
        "sha256": sha256_bytes(blob),
    }


def _reverify_raw(entry, outputs):
    for output in outputs:
        path = os.path.join(entry["output_directory"], output["relative_path"].replace("/", os.sep))
        with open(path, "rb") as handle:
            blob = handle.read()
        if blob != output["bytes"] or sha256_bytes(blob) != output["sha256"]:
            raise M8Error("raw_output_changed", "a raw output changed before the manifest was sealed", "output_reverify")
    return True


def _manifest(
    entry,
    built,
    outputs,
    records,
    before_assets,
    after_assets,
    started,
    finished,
    elapsed,
    child_env,
    versions,
    probe=None,
    provenance=None,
    library_record=None,
    controller_interpreter=None,
    child_interpreter=None,
    selected_evidence=None,
):
    if len(records) != schedule.BLOCK_ATTEMPT_TOTAL:
        raise M8Error("attempt_record_invalid", "an arm does not hold 15000 raw attempts", "manifest")
    if probe is None:
        probe = {
            "compute_processes": 0,
            "filesystem_free_bytes": entry["minimum_free_filesystem_bytes"],
            "memory_free_bytes": entry["minimum_free_gpu_memory_bytes"],
            "memory_total_bytes": entry["minimum_free_gpu_memory_bytes"],
        }
    if provenance is None:
        raise M8Error("provenance_mismatch", "manifest provenance is missing", "manifest")
    if controller_interpreter is None or child_interpreter is None or selected_evidence is None:
        raise M8Error("runtime_identity", "manifest runtime observations are missing", "manifest")
    assert_controller_interpreter(controller_interpreter)
    assert_child_interpreter(child_interpreter)
    if library_record is None:
        library_record = {"bound": entry.get("ld_library_path") is not None, "passed_to_child": False, "sha256": None}
    ledger = b"".join(canonical_bytes(record) for record in records)
    invocation_ledger = []
    for output, invocation in zip(outputs, built["invocations"][entry["technical_block"]]["invocations"]):
        invocation_ledger.append(
            {
                "batch_num": invocation["batch_num"],
                "batch_size": invocation["batch_size"],
                "generation_seed": invocation["generation_seed"],
                "invocation_index": invocation["invocation_index"],
                "kind": invocation["kind"],
                "line_count": invocation["line_count"],
                "relative_path": output["relative_path"],
                "sha256": output["sha256"],
            }
        )
    block = entry["technical_block"]
    other = "B" if block == "A" else "A"
    document = {
        "asset_verification": {
            "after": after_assets,
            "before": before_assets,
            "before_equals_after": before_assets == after_assets,
            "members_copied": False,
        },
        "authorization": {
            "active_configuration_raw_sha256": provenance["active_configuration_raw_sha256"],
            "active_configuration_sha256": provenance["active_configuration_sha256"],
            "authorisation_id": entry["authorisation_id"],
            "authorization_commit": provenance["authorization_commit"],
            "authorization_parent_commit": provenance["authorization_parent_commit"],
            "executing_implementation_commit": provenance["executing_implementation_commit"],
            "implementation_file_hashes": dict(provenance["implementation_file_hashes"]),
            "origin_main": provenance["origin_main"],
            "reuse_permitted": False,
            "single_use": True,
        },
        "block": block,
        "cleaner_invoked": False,
        "completion_state": "consumed_successfully",
        "condition_id": entry["condition_id"],
        "d1_training_seed": entry["d1_training_seed"],
        "environment": {
            "child_interpreter": child_interpreter,
            "controller_interpreter": controller_interpreter,
            "cuda_module_loading": child_env.get("CUDA_MODULE_LOADING"),
            "cuda_visible_devices": child_env.get("CUDA_VISIBLE_DEVICES"),
            "interpreter_path": entry["interpreter_path"],
            "interpreter_resolved_path": entry["interpreter_resolved_path"],
            "interpreter_sha256": entry["interpreter_sha256"],
            "ld_library_path_bound": library_record["bound"],
            "ld_library_path_passed": "LD_LIBRARY_PATH" in child_env,
            "ld_library_path_sha256": library_record["sha256"],
            "library_versions": versions,
            "offline_controls": True,
            "path": child_env.get("PATH"),
        },
        "filtering_performed": False,
        "gpu": {
            "compute_processes": probe["compute_processes"],
            "logical_device": LOGICAL_DEVICE,
            "memory_free_bytes": probe["memory_free_bytes"],
            "memory_total_bytes": probe["memory_total_bytes"],
            "minimum_free_memory_bytes": entry["minimum_free_gpu_memory_bytes"],
            "pci_bus": entry["pci_bus"],
            "physical_gpu": entry["physical_gpu"],
            "uuid": entry["gpu_uuid"],
        },
        "invocation_ledger": invocation_ledger,
        "later_evaluation_required": True,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "model_assets": {
            "checkpoint_identity": checkpoint_identity(entry),
            "kind": entry["asset_kind"],
        },
        "raw_attempt_count": len(records),
        "raw_attempt_ledger_byte_count": len(ledger),
        "raw_attempt_ledger_sha256": sha256_bytes(ledger),
        "raw_output_hashes": [output["sha256"] for output in outputs],
        "replacement_or_replenishment_performed": False,
        "repository_identity": runtime_repository_identity(provenance["authorization_commit"]),
        "reuse_prohibited": True,
        "run_id": entry["run_id"],
        "sampler": dict(MANIFEST_SAMPLER),
        "schedule": {
            "block_invocation_schedule_sha256": built["hashes"]["block_{}_invocation_schedule_sha256".format(block.lower())],
            "empirical_histogram_sha256": built["hashes"]["empirical_histogram_sha256"],
            "master_attempt_map_sha256": built["hashes"]["master_attempt_map_sha256"],
            "paired_block_invocation_schedule_sha256": built["hashes"]["block_{}_invocation_schedule_sha256".format(other.lower())],
            "quota_allocation_sha256": built["hashes"]["quota_allocation_sha256"],
            "source_length_vector_sha256": schedule.LENGTH_VECTOR_SHA256,
        },
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "selected_set_evidence": selected_evidence,
        "sequence_access": dict(SEQUENCE_ACCESS_DENIAL),
        "storage": {
            "filesystem_free_bytes": probe["filesystem_free_bytes"],
            "minimum_free_bytes": entry["minimum_free_filesystem_bytes"],
            "run_root": entry["run_root"],
        },
        "timestamps": {"elapsed_seconds": elapsed, "finished_at": finished, "started_at": started},
    }
    if document["raw_attempt_count"] != 15000 or document["filtering_performed"] is not False:
        raise M8Error("attempt_record_invalid", "the arm manifest accounting drifted", "manifest")
    if document["cleaner_invoked"] is not False or document["replacement_or_replenishment_performed"] is not False:
        raise M8Error("attempt_record_invalid", "the arm manifest claims replacement or a cleaner", "manifest")
    return document, ledger


def run_authorised_arm(entry, deps, raw_config_sha256=None):
    """Run one future arm. Interpreter, repository, path, and GPU gates run before output consumption."""
    assert_generation_entry_schema(entry)
    assert_interpreter_binding(entry)
    if raw_config_sha256 is None:
        raise M8Error("provenance_mismatch", "the active configuration raw digest is missing", "provenance")
    _sha256_text(raw_config_sha256, "the active configuration raw digest is missing")
    controller_interpreter = deps.observe_interpreter()
    assert_controller_interpreter(controller_interpreter)
    child_interpreter = deps.observe_child_interpreter()
    assert_child_interpreter(child_interpreter)
    observation = deps.repository_observation(entry)
    head = assert_repository_binding(entry, observation)
    versions = deps.library_versions()
    if versions != ACCEPTED_RUNTIME_VERSIONS or versions != entry["library_versions"]:
        raise M8Error("runtime_identity", "library versions do not match the accepted runtime", "runtime_identity")
    library_record = resolve_ld_library_path(deps.environ, entry["ld_library_path"])
    assert_generation_filesystem_preflight(entry, deps)
    probe = assert_gpu_and_storage(entry, deps.gpu_probe(deps.environ))
    if os.path.lexists(entry["output_directory"]):
        raise M8Error("output_directory_exists", "an active entry names an existing output directory", "output_directory")
    verified_selection = verify_selected_set(entry, deps)
    selected_evidence = selected_set_evidence(entry, verified_selection)
    if entry["asset_kind"] == "d1":
        assert_d1_checkpoint_inventory(entry, deps)
    before_assets = verify_assets(entry, deps)
    built = _load_schedule(deps)
    child_env = build_child_environment(deps.environ, entry["physical_gpu"], entry["output_directory"], entry["ld_library_path"])
    if child_env["PATH"] != FIXED_CHILD_PATH or child_env["CUDA_VISIBLE_DEVICES"] != str(entry["physical_gpu"]):
        raise M8Error("environment_rejected", "the child environment drifted", "runtime_identity")
    if entry["ld_library_path"] is None and "LD_LIBRARY_PATH" in child_env:
        raise M8Error("environment_rejected", "an unbound library path reached the child", "runtime_identity")
    if entry["ld_library_path"] is not None and child_env.get("LD_LIBRARY_PATH") != entry["ld_library_path"]:
        raise M8Error("environment_rejected", "the child library path differs from the authorisation binding", "runtime_identity")
    if child_env.get("TMPDIR") != os.path.join(os.path.abspath(entry["output_directory"]), "isolated_tmp"):
        raise M8Error("environment_rejected", "TMPDIR is not bound inside the output directory", "runtime_identity")
    provenance = provenance_from_entry(entry, head, raw_config_sha256)
    outputs = []
    records = []
    progress = {"completed_invocation_count": 0, "failing_invocation_index": None}
    try:
        _consume_directory(entry, provenance)
        create_isolated_runtime_directories(entry["output_directory"])
        started = deps.now()
        start_tick = deps.monotonic()
        for invocation in built["invocations"][entry["technical_block"]]["invocations"]:
            progress["failing_invocation_index"] = invocation["invocation_index"]
            result = _run_invocation(entry, invocation, child_env, deps)
            outputs.append(result)
            records.extend(result["records"])
            progress["completed_invocation_count"] += 1
            progress["failing_invocation_index"] = None
        after_assets = verify_assets(entry, deps)
        if after_assets != before_assets:
            raise M8Error("asset_mismatch", "a pinned asset hash changed after generation", "asset_verification")
        hook = getattr(deps, "before_raw_reverify", None)
        if hook is not None:
            hook(entry, outputs)
        _reverify_raw(entry, outputs)
        finished = deps.now()
        elapsed = deps.monotonic() - start_tick
        document, ledger = _manifest(
            entry,
            built,
            outputs,
            records,
            before_assets,
            after_assets,
            started,
            finished,
            elapsed,
            child_env,
            versions,
            probe,
            provenance,
            library_record,
            controller_interpreter,
            child_interpreter,
            selected_evidence,
        )
        write_atomic_bytes(entry["output_directory"], LEDGER_NAME, ledger)
        write_atomic_bytes(entry["output_directory"], INVOCATION_LEDGER_NAME, canonical_bytes(invocation_rows_public(outputs, built, entry)))
        write_atomic_bytes(entry["output_directory"], MANIFEST_NAME, canonical_bytes(document))
        _fsync_directory(entry["output_directory"])
        return document
    except M8Error as exc:
        record_consumed_failure(entry, exc, provenance, progress)
        raise
    except BaseException as exc:
        contained = M8Error("generation_failed", "an unexpected failure was contained", "generation_invocation")
        record_consumed_failure(entry, contained, provenance, progress)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise contained


def invocation_rows_public(outputs, built, entry):
    rows = []
    for output, invocation in zip(outputs, built["invocations"][entry["technical_block"]]["invocations"]):
        rows.append(
            {
                "invocation_index": invocation["invocation_index"],
                "relative_path": output["relative_path"],
                "sha256": output["sha256"],
            }
        )
    return {"rows": rows, "schema_version": "m8-invocation-ledger-1"}


def launch_authorised_generation(authorisation_id, config_bytes=None, deps=None):
    reject_authorisation_id(authorisation_id)
    raw = read_m8_config_bytes() if config_bytes is None else config_bytes
    if not isinstance(raw, (bytes, bytearray)):
        raise M8Error("configuration_not_consumable", "configuration bytes are missing")
    document = parse_config(raw)
    reject_m7_document(document)
    claim = classify_configuration(document)
    if claim != "generation_claim":
        if claim == "inactive":
            assert_inactive_configuration(document)
        raise M8Error("execution_not_authorised", "the checked-in M8 configuration is not executable", "inactive_gate")
    entry = assert_active_generation_document(document)
    if entry["authorisation_id"] != authorisation_id:
        raise M8Error("authorisation_field_missing", "no single entry carries that authorisation id")
    if deps is None:
        deps = ProductionDeps()
    return run_authorised_arm(entry, deps, raw_config_sha256=sha256_bytes(bytes(raw)))


HELP_TEXT = """\
M8 raw generation is ready for review and is not authorised.

The checked-in configuration is inactive and non-consumable. This entry
point accepts only --help, --schema and --authorisation-id <id>. The last
reads only the M8 configuration and refuses with execution_not_authorised
before the environment, Git, a GPU, a checkpoint, a biological path, the
run root, or an output directory is inspected. It cannot execute.
"""


def schema_document():
    return {
        "arms": sorted(ARMS),
        "assembly_manifest_schema_version": ASSEMBLY_MANIFEST_SCHEMA_VERSION,
        "document_status": DOCUMENT_STATUS,
        "execution_authorised": False,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "raw_record_keys": list(RAW_RECORD_KEYS),
        "record_schema_version": RECORD_SCHEMA_VERSION,
        "schema_version": SCHEMA_VERSION,
    }


def production_main(argv=None, stdout=None, config_bytes=None, deps=None):
    stdout = sys.stdout if stdout is None else stdout
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--help"], ["-h"]):
        stdout.write(HELP_TEXT)
        return 0
    if arguments == ["--schema"]:
        stdout.write(canonical_json(schema_document()).decode("utf-8"))
        return 0
    if len(arguments) == 2 and arguments[0] == "--authorisation-id":
        launch_authorised_generation(arguments[1], config_bytes=config_bytes, deps=deps)
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


def observe_controller_interpreter():
    """Inspect this process. Do not hash only the configured path."""
    executable = sys.executable
    if not isinstance(executable, str) or executable == "":
        raise M8Error("python_interpreter_rejected", "the controller executable is missing", "runtime_identity")
    resolved = os.path.realpath(executable)
    proc_target = None
    proc_resolved = None
    proc_link = "/proc/self/exe"
    if os.path.lexists(proc_link):
        try:
            proc_target = os.readlink(proc_link)
            proc_resolved = os.path.realpath(proc_link)
        except OSError:
            proc_target = None
            proc_resolved = None
    observed = {
        "executable": executable,
        "proc_self_exe": proc_target,
        "proc_self_exe_resolved": proc_resolved,
        "python_version": "{}.{}.{}".format(sys.version_info[0], sys.version_info[1], sys.version_info[2]),
        "resolved_path": resolved,
        "sha256": _sha256_file(resolved),
    }
    assert_controller_interpreter(observed)
    return observed


def probe_child_interpreter():
    """Minimal subprocess of the pinned interpreter. No model stack, CUDA query, or run directory."""
    import subprocess

    script = "\n".join(
        [
            "import hashlib, json, os, sys",
            "resolved = os.path.realpath(sys.executable)",
            "digest = hashlib.sha256()",
            "handle = open(resolved, 'rb')",
            "try:",
            "    while True:",
            "        chunk = handle.read(1024 * 1024)",
            "        if not chunk:",
            "            break",
            "        digest.update(chunk)",
            "finally:",
            "    handle.close()",
            "version = '{}.{}.{}'.format(sys.version_info[0], sys.version_info[1], sys.version_info[2])",
            "print(json.dumps({'executable': sys.executable, 'python_version': version, 'resolved_path': resolved, 'sha256': digest.hexdigest()}))",
        ]
    )
    completed = subprocess.run(
        [PINNED_PYTHON, "-I", "-B", "-c", script],
        check=False,
        cwd="/tmp",
        env={
            "CUDA_VISIBLE_DEVICES": "",
            "HF_DATASETS_OFFLINE": "1",
            "HF_HUB_OFFLINE": "1",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": FIXED_CHILD_PATH,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise M8Error("python_interpreter_rejected", "the child interpreter probe failed", "runtime_identity")
    try:
        observed = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise M8Error("python_interpreter_rejected", "the child interpreter probe was not machine readable", "runtime_identity")
    assert_child_interpreter(observed)
    return observed


class ProductionDeps(object):
    """Live dependencies for a future authorised arm. Tests do not construct this."""

    def __init__(self):
        self.environ = dict(os.environ)
        self.before_raw_reverify = None

    def read_bytes(self, path):
        with open(path, "rb") as handle:
            return handle.read()

    def lstat(self, path):
        return os.lstat(path)

    def hash_file(self, path):
        return _sha256_file(path)

    def subprocess_run(self, argv, cwd, env, shell=False):
        import subprocess

        return subprocess.run(argv, cwd=cwd, env=env, shell=shell, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _git(self, repo, args):
        import subprocess

        completed = subprocess.run(
            ["/usr/bin/git", "-C", repo] + list(args),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": FIXED_CHILD_PATH, "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
        )
        if completed.returncode != 0:
            raise M8Error("git_status_unreadable", "git could not be read", "provenance")
        return completed.stdout

    def observe_interpreter(self):
        return observe_controller_interpreter()

    def observe_child_interpreter(self):
        return probe_child_interpreter()

    def path_lstat(self, path):
        return os.lstat(path)

    def realpath(self, path):
        return os.path.realpath(path)

    def listdir(self, path):
        return os.listdir(path)

    def repository_observation(self, entry):
        head = self._git(REPO_ROOT, ["rev-parse", "HEAD"]).decode("utf-8").strip()
        parents = [item for item in self._git(REPO_ROOT, ["rev-parse", "HEAD^@"]).decode("utf-8").split() if item]
        origin = self._git(REPO_ROOT, ["rev-parse", "origin/main"]).decode("utf-8").strip()
        branch = self._git(REPO_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"]).decode("utf-8").strip()
        porcelain = self._git(REPO_ROOT, ["status", "--porcelain", "--untracked-files=all"]).decode("utf-8")
        changed = [
            item
            for item in self._git(REPO_ROOT, ["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"]).decode("utf-8").splitlines()
            if item
        ]
        executing = entry["executing_implementation_commit"]
        import subprocess

        ancestor_completed = subprocess.run(
            ["/usr/bin/git", "-C", REPO_ROOT, "merge-base", "--is-ancestor", executing, head],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": FIXED_CHILD_PATH, "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
        )
        ancestor = ancestor_completed.returncode == 0
        listing = [
            item
            for item in self._git(REPO_ROOT, ["rev-list", "--reverse", "{}..{}".format(executing, head)]).decode("utf-8").split()
            if item
        ]
        revision_range = []
        for commit in listing:
            commit_parents = [
                item for item in self._git(REPO_ROOT, ["rev-parse", commit + "^@"]).decode("utf-8").split() if item
            ]
            commit_changed = [
                item
                for item in self._git(REPO_ROOT, ["diff-tree", "--no-commit-id", "--name-only", "-r", commit]).decode("utf-8").splitlines()
                if item
            ]
            revision_range.append({"changed_files": tuple(commit_changed), "commit": commit, "parents": tuple(commit_parents)})
        at_commit = {}
        working = {}
        for relative in IMPLEMENTATION_FILES:
            blob = self._git(REPO_ROOT, ["show", "{}:{}".format(executing, relative)])
            at_commit[relative] = sha256_bytes(blob)
            with open(os.path.join(REPO_ROOT, relative), "rb") as handle:
                working[relative] = sha256_bytes(handle.read())
        rna_branch = self._git(RNAGENESIS_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"]).decode("utf-8").strip()
        rna_head = self._git(RNAGENESIS_ROOT, ["rev-parse", "HEAD"]).decode("utf-8").strip()
        rna_directory = self._git(RNAGENESIS_ROOT, ["status", "--porcelain", "--untracked-files=normal"]).decode("utf-8")
        rna_files = self._git(RNAGENESIS_ROOT, ["status", "--porcelain", "--untracked-files=all"]).decode("utf-8")
        return {
            "changed_files": tuple(changed),
            "executing_implementation_is_ancestor": ancestor,
            "file_sha256_at_implementation": at_commit,
            "file_sha256_working_tree": working,
            "mres_branch": branch,
            "mres_head": head,
            "mres_origin_main": origin,
            "mres_parents": tuple(parents),
            "mres_porcelain": porcelain,
            "rnagenesis_branch": rna_branch,
            "rnagenesis_directory_porcelain": rna_directory,
            "revision_range": tuple(revision_range),
            "rnagenesis_file_porcelain": rna_files,
            "rnagenesis_head": rna_head,
        }

    def library_versions(self):
        import torch
        import importlib.metadata as importlib_metadata

        return {
            "accelerate": importlib_metadata.version("accelerate"),
            "diffusers": importlib_metadata.version("diffusers"),
            "python": "{}.{}.{}".format(sys.version_info[0], sys.version_info[1], sys.version_info[2]),
            "torch": torch.__version__,
            "transformers": importlib_metadata.version("transformers"),
        }

    def gpu_probe(self, environ):
        import subprocess

        query = subprocess.run(
            [
                "/usr/bin/nvidia-smi",
                "--query-gpu=index,uuid,pci.bus_id,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": FIXED_CHILD_PATH, "LC_ALL": "C"},
        )
        apps = subprocess.run(
            ["/usr/bin/nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": FIXED_CHILD_PATH, "LC_ALL": "C"},
        )
        if query.returncode != 0 or apps.returncode != 0:
            raise M8Error("gpu_probe_invalid", "the GPU probe failed", "gpu_probe")
        visible = environ.get("CUDA_VISIBLE_DEVICES")
        selected = None
        for line in query.stdout.decode("utf-8").splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 5:
                continue
            if parts[0] == visible:
                selected = parts
                break
        if selected is None:
            raise M8Error("gpu_probe_invalid", "the authorised GPU was not probed", "gpu_probe")
        uuid = selected[1]
        processes = 0
        for line in apps.stdout.decode("utf-8").splitlines():
            app_parts = [part.strip() for part in line.split(",")]
            if len(app_parts) >= 2 and app_parts[0] == uuid and app_parts[1] not in ("", "[N/A]"):
                processes += 1
        filesystem = os.statvfs(RUN_ROOT)
        return {
            "compute_processes": processes,
            "cuda_visible_devices": visible,
            "filesystem_free_bytes": int(filesystem.f_bavail) * int(filesystem.f_frsize),
            "logical_device": LOGICAL_DEVICE,
            "memory_free_bytes": int(selected[4]) * 1024 * 1024,
            "memory_total_bytes": int(selected[3]) * 1024 * 1024,
            "pci_bus": selected[2],
            "physical_gpu": int(selected[0]),
            "uuid": uuid,
        }

    def now(self):
        import datetime

        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    def monotonic(self):
        import time

        return time.monotonic()


if __name__ == "__main__":
    sys.exit(main())
