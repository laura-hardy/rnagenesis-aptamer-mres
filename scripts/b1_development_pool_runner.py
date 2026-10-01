#!/usr/bin/env python3
"""M4 B1 development-pool diagnostic runner.

The checked-in B1 configuration is closed. A closed document is refused
before an output path is accepted, a length vector is opened, a GPU is
queried, a weight is hashed, or generation starts. A later authorization
commit must have exactly one parent, and that parent must be the accepted
implementation commit. The authorization block stores
authorization_parent_commit and executing_implementation_commit. It does
not store its own hash. The runner computes authorization_commit from live
HEAD. An authorised run measures provenance from live files, loads the
approved cleaner from hash-verified source, and executes generation.py in
an isolated child environment. The child sees logical cuda:0. The physical
index, UUID, and PCI bus come only from the authorisation.
"""

from __future__ import annotations

import argparse
import collections.abc
import hashlib
import importlib.metadata as importlib_metadata
import json
import os
import stat
import subprocess
import sys
import types
from pathlib import Path

MRES_ROOT = Path("/home/laura/rnagenesis-aptamer-mres")
RNAGENESIS_ROOT = Path("/home/laura/RNAGenesis")
RUNNER_RELATIVE = "scripts/b1_development_pool_runner.py"
RUNNER_PATH = MRES_ROOT / RUNNER_RELATIVE
CONFIG_RELATIVE = "config/experiments/B1_generic_generation.yaml"
B1_CONFIG_PATH = MRES_ROOT / CONFIG_RELATIVE
METRICS_PATH = MRES_ROOT / "scripts/modelling/m4_diagnostic_metrics.py"
METRICS_CONFIG_PATH = MRES_ROOT / "config/modelling/validation_metrics_v1.yaml"
PINNED_PYTHON = "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python"
GENERATION_ENTRY = RNAGENESIS_ROOT / "generation.py"
APPROVED_CLEANER = RNAGENESIS_ROOT / "scripts/audit_generation_output.py"
CLEANER_SHA256 = "4d0c56a7d931a2c3c5c049cfeabd4937134b3d1125ef7a68b10472527d2fd2a2"
GENERATION_SHA256 = "d1b1fca9544ed1c85cf6fdd304b5acb965d76ca6c89a2f98e57224ac95e44367"
RECORDED_B1_WEIGHT_SHA256 = "c268021b6cab37423e3bffd495b139bb69698d8d11c7b96477fbfb239b0cff26"
RNAGENESIS_BRANCH = "mres-d1-diffusion-finetune"
RNAGENESIS_HEAD = "e3b855bbf4d1af376f43747643fa30afd662828c"
# Exact porcelain-v1 untracked paths from the reviewed RNAGenesis worktree.
# These assets are intentionally untracked. The set must match exactly.
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
CONDITION_LABEL = "B1_generic_released_rnagenesis"
EXECUTABLE_DOCUMENT_STATUS = "APPROVED_FOR_SCIENTIFIC_EXECUTION"
POOL_EXECUTION_STATUS = "AUTHORISED_FOR_EXECUTION"
ACTIVE_UNCONSUMED_STATUS = "active_unconsumed"
AUTHORISATION_NAME = "development_pool_scientific_execution_authorisation"
CUDA_DEVICE_ORDER = "PCI_BUS_ID"
LOGICAL_DEVICE = "cuda:0"
SCHEDULE_SCHEMA = "m4-b1-development-pool-schedule-1"
MANIFEST_SCHEMA = "m4-b1-development-pool-manifest-1"
SOURCE_COUNT = 669
ATTEMPT_COUNT = 1000
SAMPLING_SEED = 43000
GENERATION_SEED_BASE = 44000
MAX_CHUNK = 16
BATCH_NUM = 1
MAX_SEQ_LEN_OFFSET = 1
ORDER_RULE = "preserve_supplied_order_do_not_reorder_before_sampling"
DDIM_STEPS = 50
ENCDEC_RELATIVE = "configs/rnagenesis/autoencoder"
DIFFUSION_RELATIVE = "configs/rnagenesis/diffusion"
CLASSIFIER_RELATIVE = "configs/rnagenesis/classifier/mlp_160_32.yaml"
DECODER_CONFIG_NAME = "config-progen2-small-rna_tokenizer_v2"
GENERATION_CWD = str(RNAGENESIS_ROOT)
PYCACHE_DIRECTORY_NAME = "python_pycache"
RUNTIME_CACHE_DIRECTORY_NAME = "isolated_runtime_cache"

SCHEDULE_NAME = "development_pool_schedule.json"
SCHEDULE_HASH_NAME = "development_pool_schedule_sha256.json"
RAW_LEDGER_NAME = "development_pool_raw_attempts.jsonl"
INVOCATION_OUTPUT_MANIFEST_NAME = "development_pool_invocation_outputs.json"
AUDITED_LEDGER_NAME = "development_pool_audited_attempts.jsonl"
METRICS_NAME = "development_pool_metrics.json"
SUCCESS_MANIFEST_NAME = "development_pool_manifest.json"
FAILURE_MANIFEST_NAME = "development_pool_failure_manifest.json"
HASH_REPORT_NAME = "development_pool_manifest_sha256.json"

# authorization_commit is computed from live HEAD at runtime. It is not a
# schema field: the authorization commit cannot contain its own hash.
AUTHORISATION_KEYS = (
    "authorisation_id",
    "authorisation_active",
    "activation_status",
    "consumed",
    "authorises_b1_development_pool",
    "gpu_use_authorised",
    "physical_gpu",
    "gpu_uuid",
    "pci_bus",
    "authorization_parent_commit",
    "executing_implementation_commit",
    "mres_branch",
    "condition",
    "phase",
    "output_directory",
    "evidence_directory",
    "schedule_sha256",
    "success_claimed",
    "m4_complete",
    "b1_eligible",
    "exact_length_accepted_pool_declared",
    "final_production_mapping_declared",
    "final_m8_production_protocol_declared",
)

RAW_ATTEMPT_FIELDS = (
    "original_attempt_index",
    "invocation_index",
    "batch_position",
    "requested_target_length",
    "max_seq_len",
    "invocation_seed",
    "raw_decoded_text",
)

ATTEMPT_FIELDS = RAW_ATTEMPT_FIELDS + (
    "raw_length",
    "leading_boundary_marker_run",
    "trailing_boundary_marker_run",
    "cleaned_sequence",
    "cleaned_length",
    "validity",
    "invalid_reason",
    "eos_marker_observed",
    "early_eos",
    "exact_length_hit",
    "length_delta",
)

RAW_INVOCATION_FIELDS = (
    "invocation_index",
    "raw_file_path",
    "byte_count",
    "line_count",
    "sha256",
    "invocation_seed",
    "target_length",
    "actual_chunk_size",
    "original_attempt_indexes",
)

MODEL_INPUTS = (
    ("generation.py", GENERATION_SHA256, False),
    ("scripts/audit_generation_output.py", CLEANER_SHA256, False),
    ("configs/rnagenesis/autoencoder/config.json", "ab309231b75405af3e2ef6fe49e4e74c1b96021ef2a4f61b46e5796b8799378a", False),
    ("configs/rnagenesis/diffusion/model_index.json", "05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e", False),
    ("configs/rnagenesis/diffusion/scheduler/scheduler_config.json", "6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396", False),
    ("configs/rnagenesis/diffusion/unet/config.json", "3a9975ff165bbd5ca82923e6ed1c5ed7eb383a23f4f3f55db713c995031f8ee3", False),
    ("configs/rnagenesis/diffusion/unet/diffusion_pytorch_model.safetensors", RECORDED_B1_WEIGHT_SHA256, True),
    ("models/autoencoder/decoder/progen_configs/config-progen2-small-rna_tokenizer_v2.json", "42f15517e05ce96d78337fbc1bf20ffc580424fe88cbfcb2c81550b17cc7283e", False),
    ("configs/rnagenesis/classifier/mlp_160_32.yaml", "9014f4594b90867a393da9212545ea1d322a8bffd23bfb25690999a55ac4a97d", False),
)

INERT_REQUIRED_ARGUMENTS = (
    ("--target_class", "0"),
    ("--guidance_scale", "1.0"),
    ("--classifier_loss_type", "l2"),
    ("--recurrence_step", "1"),
    ("--guidance_start_step", "0"),
    ("--guidance_stop_step", "50"),
    ("--search_goal", "similarity"),
    ("--active_size", "1"),
    ("--branch_size", "1"),
)

PROHIBITED_ARGV_OPTIONS = frozenset(
    [
        "--guidance",
        "--search",
        "--truncate",
        "--extend_input",
        "--update_seq",
        "--save_latent_space",
    ]
)
PROHIBITED_PATH_MARKERS = (
    "checkpoints/Aptamer/diffusion",
    "clean_generated_sequences.py",
    "ft_train.csv",
    "ft_validation.csv",
    "ref.csv",
    "eval.csv",
)
OFFLINE_CONTROLS = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}
PACKAGE_DISTRIBUTIONS = ("numpy", "torch", "diffusers", "transformers", "tokenizers")


class DevelopmentPoolError(Exception):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        self.secondary_failure = None
        super().__init__(code + ": " + detail)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _is_sha40(value):
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_sha256(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _path_within(path, root):
    try:
        return os.path.commonpath([os.path.normpath(path), os.path.normpath(root)]) == os.path.normpath(root)
    except ValueError:
        return False


def load_metrics_from_verified_source(source_bytes):
    """Compile and execute the preflight byte string. Do not reread the file."""
    if not isinstance(source_bytes, (bytes, bytearray)):
        raise DevelopmentPoolError("metrics_import_failed", "diagnostic metrics source bytes are required")
    payload = bytes(source_bytes)
    if payload.startswith(b"\xef\xbb\xbf") or b"\x00" in payload:
        raise DevelopmentPoolError("metrics_import_failed", "diagnostic metrics source is not accepted")
    try:
        code = compile(payload, str(METRICS_PATH), "exec", dont_inherit=True)
    except (SyntaxError, ValueError):
        raise DevelopmentPoolError("metrics_import_failed", "diagnostic metrics source could not be compiled")
    module = types.ModuleType("m4_diagnostic_metrics_verified")
    module.__file__ = str(METRICS_PATH)
    module.__package__ = ""
    try:
        exec(code, module.__dict__)
    except DevelopmentPoolError:
        raise
    except Exception:
        raise DevelopmentPoolError("metrics_import_failed", "diagnostic metrics source could not be executed")
    required = (
        "summarise_attempts",
        "evaluate_hard_guardrails",
        "GUARDRAIL_THRESHOLDS",
        "HARD_GUARDRAIL_IDS",
        "LARGEST_DUPLICATE_SHARE_NUMERATOR",
        "LARGEST_DUPLICATE_SHARE_DENOMINATOR",
    )
    for name in required:
        if not hasattr(module, name):
            raise DevelopmentPoolError("metrics_import_failed", "diagnostic metrics API is missing")
    if "largest_duplicate_share" not in module.HARD_GUARDRAIL_IDS:
        raise DevelopmentPoolError("metrics_import_failed", "largest_duplicate_share is not an eligibility guardrail")
    return module


def assert_bound_metrics_configuration(module, raw):
    """Bind the metrics configuration bytes to the compiled module."""
    if not isinstance(raw, (bytes, bytearray)):
        raise DevelopmentPoolError("metrics_configuration_invalid", "metrics configuration bytes are required")
    payload = bytes(raw)
    if payload.startswith(b"\xef\xbb\xbf") or b"\r" in payload:
        raise DevelopmentPoolError("metrics_configuration_invalid", "metrics configuration encoding is refused")
    import yaml

    try:
        loaded = yaml.safe_load(payload.decode("utf-8"))
    except Exception:
        raise DevelopmentPoolError("metrics_configuration_invalid", "metrics configuration could not be parsed")
    thresholds = (loaded or {}).get("hard_guardrails", {})
    if isinstance(thresholds, dict):
        thresholds = thresholds.get("thresholds")
    if not isinstance(thresholds, list):
        raise DevelopmentPoolError("metrics_configuration_invalid", "hard guardrail thresholds are missing")
    rule = None
    for item in thresholds:
        if isinstance(item, dict) and item.get("id") == "largest_duplicate_share":
            rule = item
            break
    if rule is None:
        raise DevelopmentPoolError("metrics_configuration_invalid", "largest_duplicate_share is missing")
    expected = module.GUARDRAIL_THRESHOLDS["largest_duplicate_share"]
    if rule.get("maximum") != expected["threshold"] or expected["comparison"] != "maximum":
        raise DevelopmentPoolError("metrics_configuration_invalid", "largest_duplicate_share threshold drifted")
    if rule.get("maximum") != module.LARGEST_DUPLICATE_SHARE_MAXIMUM:
        raise DevelopmentPoolError("metrics_configuration_invalid", "largest_duplicate_share maximum drifted")
    if rule.get("numerator") != module.LARGEST_DUPLICATE_SHARE_NUMERATOR:
        raise DevelopmentPoolError("metrics_configuration_invalid", "largest_duplicate_share numerator drifted")
    if rule.get("denominator") != module.LARGEST_DUPLICATE_SHARE_DENOMINATOR:
        raise DevelopmentPoolError("metrics_configuration_invalid", "largest_duplicate_share denominator drifted")
    return payload


def load_config_bytes(raw):
    if not isinstance(raw, (bytes, bytearray)):
        raise DevelopmentPoolError("config_encoding", "configuration bytes are required")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise DevelopmentPoolError("config_encoding", "configuration must be UTF-8 without a BOM or carriage return")
    import yaml

    try:
        loaded = yaml.safe_load(bytes(raw).decode("utf-8"))
    except Exception:
        raise DevelopmentPoolError("config_parse", "configuration could not be parsed")
    if not isinstance(loaded, dict):
        raise DevelopmentPoolError("config_shape", "configuration root must be a mapping")
    return loaded


def assert_configuration_consumable(config):
    """Closed documents stop here, before path, GPU, schedule, or model work."""
    if not isinstance(config, dict):
        raise DevelopmentPoolError("configuration_not_consumable", "configuration root must be a mapping")
    if config.get("consumable_by_executable_workflow") is not True:
        raise DevelopmentPoolError(
            "configuration_not_consumable",
            "consumable_by_executable_workflow is not true",
        )
    if config.get("document_status") != EXECUTABLE_DOCUMENT_STATUS:
        raise DevelopmentPoolError(
            "configuration_not_consumable",
            "document_status is not {}".format(EXECUTABLE_DOCUMENT_STATUS),
        )
    execution = config.get("execution")
    if not isinstance(execution, dict) or execution.get("authorised") is not True:
        raise DevelopmentPoolError("configuration_not_consumable", "execution.authorised is not true")
    if execution.get("gpu_authorised_by_this_approval") is not True:
        raise DevelopmentPoolError(
            "configuration_not_consumable",
            "execution.gpu_authorised_by_this_approval is not true",
        )
    pool = config.get("development_pool_execution")
    if not isinstance(pool, dict) or pool.get("executable_now") is not True:
        raise DevelopmentPoolError(
            "configuration_not_consumable",
            "development_pool_execution.executable_now is not true",
        )
    if pool.get("status") != POOL_EXECUTION_STATUS:
        raise DevelopmentPoolError(
            "configuration_not_consumable",
            "development_pool_execution.status is not {}".format(POOL_EXECUTION_STATUS),
        )
    return True


def parse_physical_gpu_argument(value):
    """Accept an explicitly supplied physical index. Do not choose one."""
    if type(value) is not str or not value.isdigit():
        raise DevelopmentPoolError("physical_gpu_argument_invalid", "physical GPU must be an explicit decimal index")
    if len(value) > 1 and value.startswith("0"):
        raise DevelopmentPoolError("physical_gpu_argument_invalid", "physical GPU must not have leading zeros")
    return int(value)


def assert_development_pool_authorisation(config, physical_gpu, output_directory):
    block = config.get(AUTHORISATION_NAME)
    if not isinstance(block, dict):
        raise DevelopmentPoolError("authorisation_missing", "development-pool authorisation is missing")
    if set(block) != set(AUTHORISATION_KEYS):
        raise DevelopmentPoolError("authorisation_shape_invalid", "development-pool authorisation fields drifted")
    if block["authorisation_active"] is not True or block["activation_status"] != ACTIVE_UNCONSUMED_STATUS:
        raise DevelopmentPoolError("authorisation_inactive", "development-pool authorisation is not active_unconsumed")
    if block["consumed"] is not False:
        raise DevelopmentPoolError("authorisation_consumed", "development-pool authorisation is consumed")
    if block["authorises_b1_development_pool"] is not True or block["gpu_use_authorised"] is not True:
        raise DevelopmentPoolError("authorisation_inactive", "development-pool GPU use is not authorised")
    if type(block["physical_gpu"]) is not int or block["physical_gpu"] != physical_gpu:
        raise DevelopmentPoolError("gpu_binding_mismatch", "authorisation physical GPU does not match the argument")
    if not isinstance(block["gpu_uuid"], str) or block["gpu_uuid"].strip() == "":
        raise DevelopmentPoolError("gpu_binding_mismatch", "authorisation GPU UUID is missing")
    if not isinstance(block["pci_bus"], str) or block["pci_bus"].strip() == "":
        raise DevelopmentPoolError("gpu_binding_mismatch", "authorisation PCI bus is missing")
    if not _is_sha40(block["authorization_parent_commit"]) or not _is_sha40(block["executing_implementation_commit"]):
        raise DevelopmentPoolError("authorisation_commit_invalid", "authorisation commits must be lowercase SHA-1")
    if block["mres_branch"] != "main" or block["condition"] != CONDITION_LABEL or block["phase"] != "development_pool":
        raise DevelopmentPoolError("authorisation_scope_invalid", "authorisation scope is not the B1 development pool")
    if block["output_directory"] != output_directory or block["evidence_directory"] != output_directory:
        raise DevelopmentPoolError("authorisation_evidence_mismatch", "authorisation output directory does not match")
    if not _is_sha256(block["schedule_sha256"]):
        raise DevelopmentPoolError("schedule_hash_mismatch", "authorisation schedule hash is missing")
    for key in (
        "success_claimed",
        "m4_complete",
        "b1_eligible",
        "exact_length_accepted_pool_declared",
        "final_production_mapping_declared",
        "final_m8_production_protocol_declared",
    ):
        if block[key] is not False:
            raise DevelopmentPoolError("authorisation_overbroad", key + " must be false")
    if not isinstance(block["authorisation_id"], str) or block["authorisation_id"].strip() == "":
        raise DevelopmentPoolError("authorisation_missing", "authorisation_id is missing")
    return {key: block[key] for key in AUTHORISATION_KEYS}


def physical_gpu_query_argv(physical_gpu):
    """Describe the preflight query. Callers decide whether to run it."""
    if type(physical_gpu) is not int or physical_gpu < 0:
        raise DevelopmentPoolError("physical_gpu_argument_invalid", "physical GPU index is invalid")
    return [
        "nvidia-smi",
        "--query-gpu=index,uuid,pci.bus_id",
        "--format=csv,noheader",
        "-i",
        str(physical_gpu),
    ]


def parse_gpu_probe(text, physical_gpu):
    if not isinstance(text, str):
        raise DevelopmentPoolError("gpu_probe_invalid", "GPU probe text is missing")
    lines = [line for line in text.splitlines() if line.strip() != ""]
    if len(lines) != 1:
        raise DevelopmentPoolError("unauthorized_gpu", "GPU query did not return one device")
    parts = [part.strip() for part in lines[0].split(",")]
    if len(parts) != 3:
        raise DevelopmentPoolError("gpu_probe_invalid", "GPU query was incomplete")
    index_text, uuid, pci_bus = parts
    if index_text != str(physical_gpu) or uuid == "" or uuid.upper() == "N/A" or pci_bus == "" or pci_bus.upper() == "N/A":
        raise DevelopmentPoolError("unauthorized_gpu", "GPU query identity is incomplete")
    return {
        "physical_index": physical_gpu,
        "uuid": uuid,
        "pci_bus": pci_bus,
        "logical_device": LOGICAL_DEVICE,
        "device_type": "cuda",
        "cuda_device_count": 1,
        "cpu_fallback": False,
        "other_gpu_fallback": False,
    }


def assert_gpu_probe(probe, physical_gpu, authorisation):
    if not isinstance(probe, dict):
        raise DevelopmentPoolError("gpu_probe_invalid", "GPU probe is missing")
    if probe.get("physical_index") != physical_gpu:
        raise DevelopmentPoolError("unauthorized_gpu", "probe physical GPU does not match the authorisation")
    if probe.get("uuid") != authorisation["gpu_uuid"] or probe.get("pci_bus") != authorisation["pci_bus"]:
        raise DevelopmentPoolError("unauthorized_gpu", "probe UUID or PCI bus does not match the authorisation")
    if probe.get("logical_device") != LOGICAL_DEVICE or probe.get("device_type") != "cuda":
        raise DevelopmentPoolError("gpu_fallback_prohibited", "logical device must be cuda:0")
    if probe.get("cuda_device_count") != 1:
        raise DevelopmentPoolError("gpu_fallback_prohibited", "exactly one visible CUDA device is required")
    if probe.get("cpu_fallback") is not False or probe.get("other_gpu_fallback") is not False:
        raise DevelopmentPoolError("gpu_fallback_prohibited", "CPU and other-GPU fallback are prohibited")
    return True


def assert_parent_cuda(parent, physical_gpu):
    if not isinstance(parent, collections.abc.Mapping) or isinstance(parent, (str, bytes, bytearray)):
        raise DevelopmentPoolError("cuda_environment_invalid", "parent environment is missing")
    if "CUDA_VISIBLE_DEVICES" not in parent or "CUDA_DEVICE_ORDER" not in parent:
        raise DevelopmentPoolError("cuda_environment_invalid", "parent CUDA variables are missing")
    visible = parent["CUDA_VISIBLE_DEVICES"]
    order = parent["CUDA_DEVICE_ORDER"]
    if type(visible) is not str or visible != str(physical_gpu):
        raise DevelopmentPoolError(
            "cuda_environment_invalid",
            "parent CUDA_VISIBLE_DEVICES must equal the authorised physical GPU",
        )
    if type(order) is not str or order != CUDA_DEVICE_ORDER:
        raise DevelopmentPoolError("cuda_environment_invalid", "parent CUDA_DEVICE_ORDER must be PCI_BUS_ID")
    if visible in ("", "-1"):
        raise DevelopmentPoolError("gpu_fallback_prohibited", "CPU fallback is prohibited")
    return True


def runtime_isolation_paths(evidence_dir):
    evidence = os.path.abspath(os.path.normpath(str(evidence_dir)))
    cache_root = os.path.join(evidence, RUNTIME_CACHE_DIRECTORY_NAME)
    huggingface = os.path.join(cache_root, "huggingface")
    hub = os.path.join(huggingface, "hub")
    return {
        "PYTHONPYCACHEPREFIX": os.path.join(evidence, PYCACHE_DIRECTORY_NAME),
        "HF_HOME": huggingface,
        "HUGGINGFACE_HUB_CACHE": hub,
        "HF_HUB_CACHE": hub,
        "HF_ASSETS_CACHE": os.path.join(huggingface, "assets"),
        "HF_MODULES_CACHE": os.path.join(huggingface, "modules"),
        "TRANSFORMERS_CACHE": hub,
        "TORCH_HOME": os.path.join(cache_root, "torch"),
        "XDG_CACHE_HOME": cache_root,
    }


def assert_runtime_isolation(evidence_dir, realpath=None):
    if realpath is None:
        realpath = os.path.realpath
    evidence = os.path.abspath(os.path.normpath(str(evidence_dir)))
    if not evidence.startswith("/"):
        raise DevelopmentPoolError("runtime_cache_not_isolated", "evidence directory is not absolute")
    resolved_evidence = realpath(evidence)
    resolved_rna = realpath(str(RNAGENESIS_ROOT))
    rna_root = os.path.normpath(str(RNAGENESIS_ROOT))
    rna_cache = os.path.normpath(os.path.join(rna_root, ".cache"))
    if _path_within(resolved_evidence, resolved_rna):
        raise DevelopmentPoolError("runtime_cache_not_isolated", "evidence directory resolves inside RNAGenesis")
    paths = runtime_isolation_paths(evidence)
    for path in paths.values():
        if not os.path.isabs(path) or _path_within(os.path.normpath(path), rna_root):
            raise DevelopmentPoolError("runtime_cache_not_isolated", "runtime cache path is inside RNAGenesis")
        resolved = realpath(path)
        if not _path_within(resolved, resolved_evidence):
            raise DevelopmentPoolError("runtime_cache_not_isolated", "runtime cache escaped the evidence directory")
        if _path_within(resolved, resolved_rna) or os.path.normpath(resolved) == rna_cache:
            raise DevelopmentPoolError("runtime_cache_not_isolated", "runtime cache resolves to an RNAGenesis cache")
    return paths


def build_child_environment(parent, physical_gpu, evidence_dir, realpath=None):
    assert_parent_cuda(parent, physical_gpu)
    original_items = list(parent.items())
    child = dict(parent.items())
    child.pop("PYTHONDONTWRITEBYTECODE", None)
    child.update(OFFLINE_CONTROLS)
    child["CUDA_VISIBLE_DEVICES"] = str(physical_gpu)
    child["CUDA_DEVICE_ORDER"] = CUDA_DEVICE_ORDER
    child.update(assert_runtime_isolation(evidence_dir, realpath))
    if list(parent.items()) != original_items:
        raise DevelopmentPoolError("parent_environment_mutated", "parent environment was modified")
    assert_parent_cuda(child, physical_gpu)
    if child["CUDA_VISIBLE_DEVICES"] != str(physical_gpu):
        raise DevelopmentPoolError("gpu_fallback_prohibited", "child CUDA device drifted")
    for path in child.values():
        if isinstance(path, str) and _path_within(os.path.normpath(path), os.path.join(str(RNAGENESIS_ROOT), ".cache")):
            raise DevelopmentPoolError("runtime_cache_not_isolated", "child environment uses an RNAGenesis cache")
    return child


def assert_output_directory_absent(path, lstat=None):
    if not isinstance(path, str) or not path.startswith("/") or path.endswith("/"):
        raise DevelopmentPoolError("output_directory_invalid", "output directory must be an absolute path without a trailing slash")
    checker = os.lstat if lstat is None else lstat
    try:
        observed = checker(path)
    except FileNotFoundError:
        return True
    if stat.S_ISLNK(observed.st_mode):
        raise DevelopmentPoolError("output_directory_symlink", "refusing a symlinked evidence directory")
    raise DevelopmentPoolError("output_directory_exists", "refusing to overwrite or resume an evidence directory")


def source_vector_identity(ordered_lengths):
    if not isinstance(ordered_lengths, (list, tuple)) or not ordered_lengths:
        raise DevelopmentPoolError("source_vector_invalid", "ordered length vector is missing")
    values = []
    for value in ordered_lengths:
        if type(value) is not int or value < 1:
            raise DevelopmentPoolError("source_vector_invalid", "length vector contains a non-positive integer")
        values.append(value)
    payload = json.dumps(values, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"
    return {
        "count": len(values),
        "sha256": _sha256(payload),
        "order_rule": ORDER_RULE,
        "values": values,
    }


def _bound_numpy_version():
    import numpy

    distribution = importlib_metadata.version("numpy")
    if type(numpy.__version__) is not str or numpy.__version__ == "" or numpy.__version__ != distribution:
        raise DevelopmentPoolError("numpy_version_unbound", "NumPy version is not the installed distribution version")
    return numpy.__version__


def sample_target_lengths(ordered_lengths, seed=SAMPLING_SEED, size=ATTEMPT_COUNT, rng_factory=None):
    """One Generator.choice call. The supplied order is the sampling population."""
    identity = source_vector_identity(ordered_lengths)
    import numpy

    factory = numpy.random.default_rng if rng_factory is None else rng_factory
    generator = factory(seed)
    population = numpy.asarray(identity["values"], dtype=numpy.int64)
    if population.shape != (identity["count"],) or population.tolist() != identity["values"]:
        raise DevelopmentPoolError("source_vector_invalid", "sampling population reordered the source vector")
    drawn = generator.choice(population, size=size, replace=True)
    if getattr(drawn, "shape", None) != (size,):
        raise DevelopmentPoolError("sampling_invalid", "target-length sample does not have size {}".format(size))
    return [int(value) for value in drawn.tolist()]


def chunk_indexes(indexes, limit=MAX_CHUNK):
    if not isinstance(indexes, list) or not indexes:
        raise DevelopmentPoolError("schedule_invalid", "a target-length group is empty")
    chunks = []
    for start in range(0, len(indexes), limit):
        chunk = list(indexes[start : start + limit])
        if not chunk or len(chunk) > limit:
            raise DevelopmentPoolError("schedule_invalid", "chunk size escaped the limit")
        chunks.append(chunk)
    if sum(len(chunk) for chunk in chunks) != len(indexes):
        raise DevelopmentPoolError("schedule_invalid", "chunking dropped or duplicated an attempt")
    return chunks


def build_schedule(ordered_lengths, require_source_count=SOURCE_COUNT, rng_factory=None):
    identity = source_vector_identity(ordered_lengths)
    if require_source_count is not None and identity["count"] != require_source_count:
        raise DevelopmentPoolError(
            "source_vector_invalid",
            "ordered length vector count is not {}".format(require_source_count),
        )
    numpy_version = _bound_numpy_version()
    sampled = sample_target_lengths(identity["values"], rng_factory=rng_factory)
    if len(sampled) != ATTEMPT_COUNT:
        raise DevelopmentPoolError("schedule_invalid", "sampled attempt count is not 1000")
    grouped = {}
    for original_index, length in enumerate(sampled):
        grouped.setdefault(length, []).append(original_index)
    invocations = []
    seen = []
    for length in sorted(grouped):
        indexes = grouped[length]
        if indexes != sorted(indexes):
            raise DevelopmentPoolError("schedule_invalid", "original attempt order was not preserved")
        for chunk in chunk_indexes(indexes):
            invocation_index = len(invocations)
            invocations.append(
                {
                    "invocation_index": invocation_index,
                    "invocation_seed": GENERATION_SEED_BASE + invocation_index,
                    "target_length": length,
                    "actual_chunk_size": len(chunk),
                    "max_seq_len": length + MAX_SEQ_LEN_OFFSET,
                    "batch_num": BATCH_NUM,
                    "original_attempt_indexes": chunk,
                    "expected_batch_positions": list(range(len(chunk))),
                }
            )
            seen.extend(chunk)
    if sorted(seen) != list(range(ATTEMPT_COUNT)) or len(seen) != len(set(seen)):
        raise DevelopmentPoolError("schedule_invalid", "attempt identities are not a permutation of 0..999")
    return {
        "schema_version": SCHEDULE_SCHEMA,
        "source_ordered_length_vector": {
            "count": identity["count"],
            "sha256": identity["sha256"],
            "order_rule": identity["order_rule"],
        },
        "numpy_version": numpy_version,
        "sampler": "numpy.random.default_rng",
        "sampling_seed": SAMPLING_SEED,
        "sampling_operation": {
            "method": "Generator.choice",
            "size": ATTEMPT_COUNT,
            "replace": True,
            "operation_count": 1,
        },
        "sampled_target_lengths": sampled,
        "original_attempt_index_origin": 0,
        "original_attempt_index_inclusive_end": ATTEMPT_COUNT - 1,
        "invocations": invocations,
        "total_attempts": ATTEMPT_COUNT,
        "invocation_count": len(invocations),
        "max_chunk_size": MAX_CHUNK,
        "batch_num": BATCH_NUM,
        "generation_seed_base": GENERATION_SEED_BASE,
        "seed_formula": "44000 + invocation_index",
        "max_seq_len_formula": "sampled_target_length + 1",
        "independent_biological_replicates": False,
        "diagnostic_generation_sample": True,
        "reusable_by_later_d1_generation": True,
        "padding": False,
        "duplication": False,
        "replacement_of_attempts": False,
        "rejection": False,
        "resampling": False,
        "dropping": False,
    }


def canonical_schedule_bytes(document):
    if not isinstance(document, dict):
        raise DevelopmentPoolError("schedule_invalid", "schedule must be a mapping")
    if "schedule_sha256" in document or "sha256" in document:
        raise DevelopmentPoolError("schedule_invalid", "schedule body must exclude its own hash")
    text = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    raw = (text + "\n").encode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or raw.count(b"\n") != 1 or not raw.endswith(b"\n"):
        raise DevelopmentPoolError("schedule_invalid", "schedule serialization is not canonical")
    return raw


def schedule_sha256(document):
    return _sha256(canonical_schedule_bytes(document))


def load_cleaner_from_verified_source(source_bytes):
    if not isinstance(source_bytes, (bytes, bytearray)):
        raise DevelopmentPoolError("cleaner_import_failed", "approved cleaner source bytes are required")
    payload = bytes(source_bytes)
    if _sha256(payload) != CLEANER_SHA256:
        raise DevelopmentPoolError("provenance_mismatch", "cleaner hash does not match the approved cleaner")
    try:
        code = compile(payload, str(APPROVED_CLEANER), "exec", dont_inherit=True)
    except (SyntaxError, ValueError):
        raise DevelopmentPoolError("cleaner_import_failed", "approved cleaner source could not be compiled")
    module = types.ModuleType("b1_development_pool_approved_audit_generation_output")
    module.__file__ = str(APPROVED_CLEANER)
    module.__package__ = ""
    try:
        exec(code, module.__dict__)
    except DevelopmentPoolError:
        raise
    except Exception:
        raise DevelopmentPoolError("cleaner_import_failed", "approved cleaner source could not be executed")
    if not hasattr(module, "audit_line") or not hasattr(module, "split_raw_records"):
        raise DevelopmentPoolError("cleaner_import_failed", "approved cleaner API is missing")
    return module


def map_invocation_output(payload, invocation, cleaner):
    if cleaner is None or not hasattr(cleaner, "audit_line") or not hasattr(cleaner, "split_raw_records"):
        raise DevelopmentPoolError("cleaner_import_failed", "approved cleaner is not loaded")
    if not isinstance(payload, (bytes, bytearray)):
        raise DevelopmentPoolError("malformed_output", "generation output bytes are required")
    raw_bytes = bytes(payload)
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise DevelopmentPoolError("malformed_output", "generation output is not UTF-8")
    if b"\x00" in raw_bytes:
        raise DevelopmentPoolError("malformed_output", "generation output contains a NUL")
    lines = cleaner.split_raw_records(text)
    expected = invocation["original_attempt_indexes"]
    if len(lines) != invocation["actual_chunk_size"] or len(lines) != len(expected):
        raise DevelopmentPoolError(
            "output_line_count_mismatch",
            "decoded output count does not equal the actual chunk size",
        )
    if invocation["expected_batch_positions"] != list(range(len(expected))):
        raise DevelopmentPoolError("schedule_invalid", "expected batch positions drifted")
    records = []
    for position, raw in enumerate(lines):
        audited = cleaner.audit_line(position + 1, raw)
        if audited.get("raw") != raw:
            raise DevelopmentPoolError("unreconciled_output", "cleaner raw field does not match the decoded line")
        requested = invocation["target_length"]
        cleaned = audited["cleaned"]
        valid = audited["accepted"] is True
        cleaned_length = len(cleaned)
        prefix = audited["removed_prefix"]
        suffix = audited["removed_suffix"]
        eos_marker = "2" in prefix or "2" in suffix
        early = bool(valid and eos_marker and cleaned_length < requested)
        records.append(
            {
                "original_attempt_index": expected[position],
                "invocation_index": invocation["invocation_index"],
                "batch_position": position,
                "requested_target_length": requested,
                "max_seq_len": invocation["max_seq_len"],
                "invocation_seed": invocation["invocation_seed"],
                "raw_decoded_text": raw,
                "raw_length": len(raw),
                "leading_boundary_marker_run": prefix,
                "trailing_boundary_marker_run": suffix,
                "cleaned_sequence": cleaned,
                "cleaned_length": cleaned_length,
                "validity": valid,
                "invalid_reason": None if valid else audited["reason"],
                "eos_marker_observed": eos_marker,
                "early_eos": early,
                "exact_length_hit": bool(valid and cleaned_length == requested),
                "length_delta": cleaned_length - requested,
            }
        )
    if [record["batch_position"] for record in records] != invocation["expected_batch_positions"]:
        raise DevelopmentPoolError("unreconciled_output", "batch positions do not match the schedule")
    if [record["original_attempt_index"] for record in records] != expected:
        raise DevelopmentPoolError("unreconciled_output", "original attempt indexes do not match the schedule")
    return records


def assert_attempt_accounting(attempts, schedule):
    expected = []
    for invocation in schedule["invocations"]:
        expected.extend(invocation["original_attempt_indexes"])
    observed = [attempt["original_attempt_index"] for attempt in attempts]
    if sorted(observed) != sorted(expected) or len(observed) != len(set(observed)):
        raise DevelopmentPoolError("attempt_accounting_invalid", "attempt identities are missing or duplicated")
    if schedule.get("total_attempts") == ATTEMPT_COUNT and sorted(expected) != list(range(ATTEMPT_COUNT)):
        raise DevelopmentPoolError("attempt_accounting_invalid", "the diagnostic schedule is not a permutation of 0..999")
    by_invocation = {}
    for attempt in attempts:
        by_invocation.setdefault(attempt["invocation_index"], []).append(attempt)
    if len(by_invocation) != schedule["invocation_count"]:
        raise DevelopmentPoolError("attempt_accounting_invalid", "invocation output count does not match the schedule")
    for invocation in schedule["invocations"]:
        rows = by_invocation.get(invocation["invocation_index"])
        if rows is None:
            raise DevelopmentPoolError("missing_invocation_output", "an invocation produced no mapped output")
        rows = sorted(rows, key=lambda row: row["batch_position"])
        if [row["original_attempt_index"] for row in rows] != invocation["original_attempt_indexes"]:
            raise DevelopmentPoolError("unreconciled_output", "mapped attempts do not match the invocation")
        if len(rows) != invocation["actual_chunk_size"]:
            raise DevelopmentPoolError("output_line_count_mismatch", "mapped rows do not match the chunk")
    return True


def technical_failure_reasons(attempts, schedule, raw_verified, provenance_matched, manifests_exclusive):
    """Length mismatch, early EOS, invalid sequences, and duplicates are not reasons."""
    reasons = []
    try:
        assert_attempt_accounting(attempts, schedule)
    except DevelopmentPoolError as exc:
        reasons.append(exc.code)
    if len(attempts) != schedule["total_attempts"]:
        reasons.append("raw_output_count_mismatch")
    if raw_verified is not True:
        reasons.append("raw_output_verification_failed")
    if provenance_matched is not True:
        reasons.append("provenance_mismatch")
    if manifests_exclusive is not True:
        reasons.append("manifest_collision")
    return reasons


def diagnostic_run_succeeded(**kwargs):
    return technical_failure_reasons(**kwargs) == []


def canonical_json_bytes(document):
    text = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return (text + "\n").encode("utf-8")


def serialize_jsonl(records, fields, order_key):
    lines = []
    ordered = sorted(records, key=lambda record: record[order_key])
    for record in ordered:
        if tuple(record) != fields:
            raise DevelopmentPoolError("attempt_record_invalid", "record fields drifted")
        lines.append(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
    return ("\n".join(lines) + "\n").encode("utf-8")


def invocation_folder(invocation):
    return "invocation_{:04d}".format(invocation["invocation_index"])


def invocation_remark(invocation):
    return "_pool_i{:04d}_seed{}_cap{}".format(
        invocation["invocation_index"],
        invocation["invocation_seed"],
        invocation["max_seq_len"],
    )


def predicted_generation_filename(invocation):
    count = invocation["actual_chunk_size"] * invocation["batch_num"]
    return "seqs_wo_guidance_top_p=0.95_2_{}{}.txt".format(count, invocation_remark(invocation))


def predicted_generation_path(evidence_dir, invocation):
    return (
        Path(evidence_dir)
        / "rnagenesis_generation_output"
        / invocation_folder(invocation)
        / predicted_generation_filename(invocation)
    )


def build_generation_argv(invocation):
    if invocation["batch_num"] != BATCH_NUM:
        raise DevelopmentPoolError("schedule_invalid", "batch_num is not 1")
    if invocation["max_seq_len"] != invocation["target_length"] + MAX_SEQ_LEN_OFFSET:
        raise DevelopmentPoolError("schedule_invalid", "max_seq_len is not the sampled target length plus 1")
    if invocation["actual_chunk_size"] < 1 or invocation["actual_chunk_size"] > MAX_CHUNK:
        raise DevelopmentPoolError("schedule_invalid", "actual chunk size is outside 1..16")
    argv = [
        PINNED_PYTHON,
        str(GENERATION_ENTRY),
        "--enc_dec_file",
        ENCDEC_RELATIVE,
        "--dm_file",
        DIFFUSION_RELATIVE,
        "--decoder_config",
        DECODER_CONFIG_NAME,
        "--num_inference_steps",
        str(DDIM_STEPS),
        "--batch_size",
        str(invocation["actual_chunk_size"]),
        "--batch_num",
        str(BATCH_NUM),
        "--seed",
        str(invocation["invocation_seed"]),
        "--eta",
        "0",
        "--guidance_classifier_model_config",
        CLASSIFIER_RELATIVE,
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
    ]
    for flag, value in INERT_REQUIRED_ARGUMENTS:
        argv.extend([flag, value])
    for option in PROHIBITED_ARGV_OPTIONS:
        if option in argv:
            raise DevelopmentPoolError("prohibited_generation_option", option)
    for element in argv:
        for marker in PROHIBITED_PATH_MARKERS:
            if marker in element.replace("\\", "/"):
                raise DevelopmentPoolError("prohibited_generation_path", marker)
    if argv[argv.index("--device") + 1] != LOGICAL_DEVICE:
        raise DevelopmentPoolError("gpu_fallback_prohibited", "generation device is not cuda:0")
    if "--cpu" in argv:
        raise DevelopmentPoolError("gpu_fallback_prohibited", "CPU generation is prohibited")
    return argv


def build_generation_command(invocation, evidence_dir, parent, physical_gpu, realpath=None):
    argv = build_generation_argv(invocation)
    argv.extend(
        [
            "--superfolder",
            str(Path(evidence_dir) / "rnagenesis_generation_output"),
            "--mid_folder",
            invocation_folder(invocation),
        ]
    )
    return {
        "argv": argv,
        "cwd": GENERATION_CWD,
        "env": build_child_environment(parent, physical_gpu, evidence_dir, realpath),
        "shell": False,
    }


def _git_text(git, repo, args):
    text = git(repo, args)
    if not isinstance(text, str):
        raise DevelopmentPoolError("git_status_unreadable", "git output is not text")
    return text


def _git_line(git, repo, args):
    return _git_text(git, repo, args).strip()


def _porcelain_lines(porcelain):
    if not isinstance(porcelain, str):
        raise DevelopmentPoolError("git_status_unreadable", "git status porcelain could not be read")
    return [line for line in porcelain.splitlines() if line != ""]


def _split_porcelain(line):
    if len(line) < 4 or line[2] != " ":
        raise DevelopmentPoolError("git_status_unreadable", "git status porcelain could not be read")
    return line[0], line[1], line[3:]


def reviewed_rnagenesis_porcelain():
    """Live git-status shape for the reviewed untracked asset directories."""
    return "".join("?? {}\n".format(path) for path in KNOWN_RNAGENESIS_UNTRACKED)


def _normalise_untracked_path(path):
    normalised = path.replace("\\", "/").strip()
    if normalised.startswith("./"):
        normalised = normalised[2:]
    if len(normalised) >= 2 and normalised[0] == '"' and normalised[-1] == '"':
        normalised = normalised[1:-1]
    return normalised


def _assert_rnagenesis_worktree(porcelain):
    """Require the pinned branch's exact untracked asset fingerprint.

    An empty porcelain result is refused. The required RNAGenesis assets are
    intentionally untracked. Missing, additional, and renamed paths are refused.
    """
    observed = []
    for line in _porcelain_lines(porcelain):
        index_status, worktree_status, path = _split_porcelain(line)
        if index_status == "?" and worktree_status == "?":
            observed.append(_normalise_untracked_path(path))
            continue
        if index_status not in (" ", "?"):
            raise DevelopmentPoolError("provenance_mismatch", "RNAGenesis staged changes are present")
        raise DevelopmentPoolError("provenance_mismatch", "RNAGenesis tracked changes are present")
    if sorted(observed) != sorted(KNOWN_RNAGENESIS_UNTRACKED):
        raise DevelopmentPoolError(
            "provenance_mismatch",
            "untracked path is not the known RNAGenesis asset fingerprint",
        )


def measure_provenance(authorisation, deps):
    """Hash and inspect the live files. Caller-supplied hashes are not accepted."""
    config_bytes = deps.read_bytes(B1_CONFIG_PATH)
    runner_bytes = deps.read_bytes(RUNNER_PATH)
    cleaner_bytes = deps.read_bytes(APPROVED_CLEANER)
    metrics_bytes = deps.read_bytes(METRICS_PATH)
    metrics_config_bytes = deps.read_bytes(METRICS_CONFIG_PATH)
    if _sha256(cleaner_bytes) != CLEANER_SHA256:
        raise DevelopmentPoolError("provenance_mismatch", "cleaner hash does not match the approved cleaner")
    mres_head = _git_line(deps.git, MRES_ROOT, ["rev-parse", "HEAD"])
    mres_branch = _git_line(deps.git, MRES_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"])
    mres_porcelain = deps.git(MRES_ROOT, ["status", "--porcelain=v1"])
    origin_main = _git_line(deps.git, MRES_ROOT, ["rev-parse", "origin/main"])
    if not _is_sha40(mres_head) or not _is_sha40(origin_main):
        raise DevelopmentPoolError("provenance_mismatch", "MRes HEAD is not a lowercase SHA-1")
    if mres_branch != authorisation["mres_branch"] or mres_branch != "main":
        raise DevelopmentPoolError("provenance_mismatch", "MRes branch is not the authorised branch")
    if _porcelain_lines(mres_porcelain):
        raise DevelopmentPoolError("provenance_mismatch", "MRes worktree or index is not clean")
    if mres_head != origin_main:
        raise DevelopmentPoolError("provenance_mismatch", "local HEAD is not origin/main")
    parents = [
        line.strip()
        for line in _git_text(deps.git, MRES_ROOT, ["rev-parse", "HEAD^@"]).splitlines()
        if line.strip() != ""
    ]
    if len(parents) > 1:
        raise DevelopmentPoolError("provenance_mismatch", "merge commits are refused")
    if len(parents) != 1 or not _is_sha40(parents[0]):
        raise DevelopmentPoolError("provenance_mismatch", "live HEAD does not have exactly one parent")
    parent = parents[0]
    if parent != authorisation["authorization_parent_commit"]:
        raise DevelopmentPoolError(
            "provenance_mismatch",
            "authorization parent is not the parent of live HEAD",
        )
    implementation = authorisation["executing_implementation_commit"]
    if implementation != parent:
        raise DevelopmentPoolError(
            "provenance_mismatch",
            "executing_implementation_commit is not the accepted parent",
        )
    implementation_blob = _git_line(
        deps.git,
        MRES_ROOT,
        ["rev-parse", "{}:{}".format(implementation, RUNNER_RELATIVE)],
    )
    worktree_blob = _git_line(deps.git, MRES_ROOT, ["hash-object", "--", str(RUNNER_PATH)])
    if not _is_sha40(implementation_blob) or implementation_blob != worktree_blob:
        raise DevelopmentPoolError("provenance_mismatch", "runner bytes do not match the implementation commit")
    shown = _git_text(deps.git, MRES_ROOT, ["show", "HEAD:" + CONFIG_RELATIVE])
    if shown.encode("utf-8") != bytes(config_bytes):
        raise DevelopmentPoolError("provenance_mismatch", "active authorisation is not the live HEAD blob")
    head_config = load_config_bytes(shown.encode("utf-8"))
    head_block = head_config.get(AUTHORISATION_NAME)
    if not isinstance(head_block, dict) or set(head_block) != set(AUTHORISATION_KEYS):
        raise DevelopmentPoolError("provenance_mismatch", "active authorisation is not the live HEAD blob")
    if any(head_block[key] != authorisation[key] for key in AUTHORISATION_KEYS):
        raise DevelopmentPoolError("provenance_mismatch", "active authorisation is not the live HEAD blob")
    rna_head = _git_line(deps.git, RNAGENESIS_ROOT, ["rev-parse", "HEAD"])
    rna_branch = _git_line(deps.git, RNAGENESIS_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"])
    rna_porcelain = deps.git(RNAGENESIS_ROOT, ["status", "--porcelain=v1"])
    if rna_branch != RNAGENESIS_BRANCH or rna_head != RNAGENESIS_HEAD:
        raise DevelopmentPoolError("provenance_mismatch", "RNAGenesis branch or commit drifted")
    _assert_rnagenesis_worktree(rna_porcelain)
    metrics_module = load_metrics_from_verified_source(metrics_bytes)
    assert_bound_metrics_configuration(metrics_module, metrics_config_bytes)
    model_inputs = []
    for relative, expected, _large in MODEL_INPUTS:
        path = RNAGENESIS_ROOT / relative
        digest = deps.sha256_file(path)
        if digest != expected:
            raise DevelopmentPoolError("provenance_mismatch", "model input hash drifted: " + relative)
        model_inputs.append({"path": str(path), "sha256": digest, "relative_path": relative})
    if not os.path.isfile(PINNED_PYTHON):
        raise DevelopmentPoolError("provenance_mismatch", "pinned interpreter is missing")
    packages = {}
    for distribution in PACKAGE_DISTRIBUTIONS:
        try:
            packages[distribution] = importlib_metadata.version(distribution)
        except importlib_metadata.PackageNotFoundError:
            packages[distribution] = None
    numpy_version = _bound_numpy_version()
    if packages["numpy"] != numpy_version:
        raise DevelopmentPoolError("numpy_version_unbound", "recorded NumPy version drifted")
    return {
        "configuration": {"path": str(B1_CONFIG_PATH), "byte_count": len(config_bytes), "sha256": _sha256(config_bytes)},
        "runner": {"path": str(RUNNER_PATH), "byte_count": len(runner_bytes), "sha256": _sha256(runner_bytes)},
        "approved_cleaner": {"path": str(APPROVED_CLEANER), "byte_count": len(cleaner_bytes), "sha256": _sha256(cleaner_bytes)},
        "diagnostic_metrics_module": {"path": str(METRICS_PATH), "byte_count": len(metrics_bytes), "sha256": _sha256(metrics_bytes)},
        "metrics_configuration": {
            "path": str(METRICS_CONFIG_PATH),
            "byte_count": len(metrics_config_bytes),
            "sha256": _sha256(metrics_config_bytes),
        },
        "metrics_module": metrics_module,
        "metrics_source_bytes": bytes(metrics_bytes),
        "metrics_configuration_bytes": bytes(metrics_config_bytes),
        "model_inputs": model_inputs,
        "model_weight_sha256": RECORDED_B1_WEIGHT_SHA256,
        "interpreter": {
            "executable": sys.executable,
            "version": sys.version.split()[0],
            "pinned_generation_interpreter": PINNED_PYTHON,
        },
        "mres": {
            "branch": mres_branch,
            "head": mres_head,
            "clean": True,
            "origin_main": origin_main,
            "authorization_commit": mres_head,
            "authorization_parent_commit": parent,
            "executing_implementation_commit": implementation,
        },
        "rnagenesis": {
            "branch": rna_branch,
            "commit": rna_head,
            "tracked_and_staged_clean": True,
            "untracked_fingerprint": list(KNOWN_RNAGENESIS_UNTRACKED),
            "runner_modified_repository": False,
        },
        "packages": packages,
        "numpy_version": numpy_version,
        "cleaner_source_bytes": cleaner_bytes,
    }


def parse_length_vector(raw):
    if not isinstance(raw, (bytes, bytearray)):
        raise DevelopmentPoolError("source_vector_invalid", "length vector bytes are required")
    try:
        loaded = json.loads(bytes(raw).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DevelopmentPoolError("source_vector_invalid", "length vector is not JSON")
    if not isinstance(loaded, list):
        raise DevelopmentPoolError("source_vector_invalid", "length vector must be a JSON list")
    return loaded


def _exclusive_write(path, data):
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        descriptor = os.open(str(path), flags, 0o644)
    except FileExistsError:
        raise DevelopmentPoolError("output_directory_exists", "refusing to overwrite " + os.path.basename(str(path)))
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written == 0:
                raise DevelopmentPoolError("evidence_write_failed", "short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.path.dirname(str(path))
    if directory:
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def _path_exists(path, lstat):
    try:
        lstat(path)
    except FileNotFoundError:
        return False
    return True


def _safe_detail(detail):
    text = "" if detail is None else str(detail)
    run = 0
    for character in text:
        if character in "ACGUacgu":
            run += 1
            if run >= 8:
                return "failure detail omitted"
        else:
            run = 0
    return text


def normalize_evidence_error(exc):
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return exc
    if isinstance(exc, DevelopmentPoolError):
        safe = _safe_detail(exc.detail)
        if safe == exc.detail:
            return exc
        replacement = DevelopmentPoolError(exc.code, safe)
        replacement.secondary_failure = exc.secondary_failure
        return replacement
    if isinstance(exc, UnicodeDecodeError):
        return DevelopmentPoolError("malformed_output", "generation output is not valid UTF-8")
    if isinstance(exc, FileNotFoundError):
        return DevelopmentPoolError("output_file_missing", "expected generation output is missing")
    if isinstance(exc, subprocess.SubprocessError):
        return DevelopmentPoolError("generation_process_failed", "generation subprocess failed")
    if isinstance(exc, OSError):
        return DevelopmentPoolError("filesystem_error", "filesystem operation failed")
    if isinstance(exc, Exception):
        return DevelopmentPoolError("unexpected_runtime_failure", "unexpected runtime failure")
    return exc


def verify_regular_file(path, expected, deps, cleaner, expected_bytes=None):
    """lstat, require a regular non-symlink file, and reread it before success."""
    try:
        observed = deps.lstat(path)
    except FileNotFoundError:
        raise DevelopmentPoolError("raw_output_deleted", "raw evidence was deleted before success")
    except OSError:
        raise DevelopmentPoolError("raw_output_verification_failed", "raw evidence could not be inspected")
    if stat.S_ISLNK(observed.st_mode):
        raise DevelopmentPoolError("raw_output_symlink", "raw evidence was replaced by a symlink")
    if not stat.S_ISREG(observed.st_mode):
        raise DevelopmentPoolError("raw_output_not_regular", "raw evidence is not a regular file")
    if observed.st_size < expected["byte_count"]:
        raise DevelopmentPoolError("raw_output_truncated", "raw evidence was truncated")
    if observed.st_size != expected["byte_count"]:
        raise DevelopmentPoolError("raw_output_replaced", "raw evidence size changed")
    try:
        payload = deps.read_bytes(path)
    except FileNotFoundError:
        raise DevelopmentPoolError("raw_output_deleted", "raw evidence was deleted before it could be reread")
    except OSError:
        raise DevelopmentPoolError("raw_output_verification_failed", "raw evidence could not be reread")
    if not isinstance(payload, (bytes, bytearray)):
        raise DevelopmentPoolError("raw_output_verification_failed", "raw evidence is not bytes")
    data = bytes(payload)
    if len(data) < expected["byte_count"]:
        raise DevelopmentPoolError("raw_output_truncated", "reread raw evidence was truncated")
    if len(data) != expected["byte_count"]:
        raise DevelopmentPoolError("raw_output_replaced", "reread raw evidence size changed")
    if _sha256(data) != expected["sha256"]:
        raise DevelopmentPoolError("raw_output_mutated", "raw evidence hash drifted")
    if expected_bytes is not None and data != bytes(expected_bytes):
        raise DevelopmentPoolError("raw_output_mutated", "raw evidence bytes drifted")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise DevelopmentPoolError("raw_output_mutated", "raw evidence is no longer UTF-8")
    if cleaner is None:
        line_count = text.count("\n")
    else:
        line_count = len(cleaner.split_raw_records(text))
    if line_count != expected["line_count"]:
        raise DevelopmentPoolError("raw_output_count_drift", "raw evidence line count drifted")
    return data


def verify_bound_evidence_file(path, expected_bytes, deps):
    """lstat and reread one evidence file against the bytes that were written."""
    if not isinstance(expected_bytes, (bytes, bytearray)):
        raise DevelopmentPoolError("evidence_verification_failed", "expected evidence bytes are missing")
    expected_raw = bytes(expected_bytes)
    try:
        observed = deps.lstat(path)
    except FileNotFoundError:
        raise DevelopmentPoolError("evidence_verification_failed", "evidence file is missing")
    except OSError:
        raise DevelopmentPoolError("evidence_verification_failed", "evidence file could not be inspected")
    if stat.S_ISLNK(observed.st_mode):
        raise DevelopmentPoolError("evidence_verification_failed", "evidence file is a symlink")
    if not stat.S_ISREG(observed.st_mode):
        raise DevelopmentPoolError("evidence_verification_failed", "evidence file is not a regular file")
    if observed.st_size != len(expected_raw):
        raise DevelopmentPoolError("evidence_verification_failed", "evidence file size drifted")
    try:
        payload = deps.read_bytes(path)
    except FileNotFoundError:
        raise DevelopmentPoolError("evidence_verification_failed", "evidence file is missing")
    except OSError:
        raise DevelopmentPoolError("evidence_verification_failed", "evidence file could not be reread")
    data = bytes(payload)
    if data != expected_raw or len(data) != len(expected_raw):
        raise DevelopmentPoolError("evidence_verification_failed", "evidence file bytes drifted")
    if _sha256(data) != _sha256(expected_raw):
        raise DevelopmentPoolError("evidence_verification_failed", "evidence file hash drifted")
    if data.count(b"\n") != expected_raw.count(b"\n"):
        raise DevelopmentPoolError("evidence_verification_failed", "evidence file line count drifted")
    return data


def reverify_bound_source(path, expected_bytes, deps, code):
    """Reread a preflight file without executing a replacement."""
    if not isinstance(expected_bytes, (bytes, bytearray)):
        raise DevelopmentPoolError(code, "bound source bytes are missing")
    expected_raw = bytes(expected_bytes)
    try:
        observed = deps.lstat(path)
    except OSError:
        raise DevelopmentPoolError(code, "bound source could not be inspected")
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise DevelopmentPoolError(code, "bound source is not a regular file")
    if observed.st_size != len(expected_raw):
        raise DevelopmentPoolError(code, "bound source drifted after preflight")
    try:
        payload = deps.read_bytes(path)
    except OSError:
        raise DevelopmentPoolError(code, "bound source could not be reread")
    if bytes(payload) != expected_raw or _sha256(bytes(payload)) != _sha256(expected_raw):
        raise DevelopmentPoolError(code, "bound source drifted after preflight")


def raw_attempt_record(attempt):
    """Keep the generation identity and raw text. Omit cleaner-derived fields."""
    return {field: attempt[field] for field in RAW_ATTEMPT_FIELDS}


def _raw_invocation_record(path, payload, invocation, cleaner):
    text = bytes(payload).decode("utf-8")
    line_count = len(cleaner.split_raw_records(text))
    return {
        "invocation_index": invocation["invocation_index"],
        "raw_file_path": str(path),
        "byte_count": len(payload),
        "line_count": line_count,
        "sha256": _sha256(payload),
        "invocation_seed": invocation["invocation_seed"],
        "target_length": invocation["target_length"],
        "actual_chunk_size": invocation["actual_chunk_size"],
        "original_attempt_indexes": list(invocation["original_attempt_indexes"]),
    }


def _write_failure(evidence_dir, code, detail, deps):
    path = os.path.join(evidence_dir, FAILURE_MANIFEST_NAME)
    success = os.path.join(evidence_dir, SUCCESS_MANIFEST_NAME)
    if _path_exists(success, deps.lstat) or _path_exists(path, deps.lstat):
        raise DevelopmentPoolError("manifest_collision", "success and failure manifests must be mutually exclusive")
    document = {
        "schema_version": MANIFEST_SCHEMA,
        "status": "failed",
        "code": code,
        "detail": _safe_detail(detail),
        "m4_complete": False,
        "exact_length_accepted_pool_declared": False,
        "final_production_mapping_declared": False,
        "final_m8_production_protocol_declared": False,
    }
    deps.write_exclusive(path, canonical_json_bytes(document))


def _run_invocation(evidence_dir, invocation, parent, physical_gpu, deps, cleaner):
    command = build_generation_command(invocation, evidence_dir, parent, physical_gpu, deps.realpath)
    if command["shell"] is not False or command["cwd"] != GENERATION_CWD:
        raise DevelopmentPoolError("generation_cwd_rejected", "generation working directory is not RNAGenesis")
    if command["argv"][0] != PINNED_PYTHON or command["argv"][1] != str(GENERATION_ENTRY):
        raise DevelopmentPoolError("python_interpreter_rejected", "generation command is not the pinned interpreter")
    if command["argv"][command["argv"].index("--device") + 1] != LOGICAL_DEVICE:
        raise DevelopmentPoolError("gpu_fallback_prohibited", "generation device is not cuda:0")
    predicted = predicted_generation_path(evidence_dir, invocation)
    try:
        deps.lstat(predicted)
    except FileNotFoundError:
        pass
    else:
        raise DevelopmentPoolError("output_directory_exists", "invocation output already exists")
    folder = os.path.join(evidence_dir, "rnagenesis_generation_output", invocation_folder(invocation))
    if not _path_exists(folder, deps.lstat):
        deps.mkdir(folder)
    completed = deps.subprocess_run(command["argv"], cwd=command["cwd"], env=command["env"], shell=False)
    returncode = getattr(completed, "returncode", None)
    if type(returncode) is not int or returncode != 0:
        raise DevelopmentPoolError("generation_process_failed", "generation.py exited {}".format(returncode))
    payload = deps.read_bytes(predicted)
    if not isinstance(payload, (bytes, bytearray)):
        raise DevelopmentPoolError("malformed_output", "generation output bytes are required")
    data = bytes(payload)
    records = map_invocation_output(data, invocation, cleaner)
    metadata = _raw_invocation_record(predicted, data, invocation, cleaner)
    if metadata["line_count"] != invocation["actual_chunk_size"]:
        raise DevelopmentPoolError("output_line_count_mismatch", "raw line count does not match the chunk")
    return records, metadata, data


def _create_cache_directories(evidence_dir):
    paths = assert_runtime_isolation(evidence_dir)
    for path in sorted(set(paths.values()), key=len):
        os.makedirs(path, exist_ok=True)
    return paths


def execute_authorised(context, deps, cleaner):
    evidence_dir = context["output_directory"]
    schedule = context["schedule"]
    parent_before = list(deps.environ.items())
    _create_cache_directories(evidence_dir)
    writer = deps.write_exclusive
    schedule_hash_bytes = canonical_json_bytes(
        {"schedule_sha256": context["schedule_sha256"], "schema_version": SCHEDULE_SCHEMA}
    )
    writer(os.path.join(evidence_dir, SCHEDULE_NAME), context["schedule_bytes"])
    writer(os.path.join(evidence_dir, SCHEDULE_HASH_NAME), schedule_hash_bytes)
    deps.mkdir(os.path.join(evidence_dir, "rnagenesis_generation_output"))
    attempts = []
    raw_attempt_records = []
    invocation_records = []
    raw_payloads = []
    for invocation in schedule["invocations"]:
        mapped, metadata, payload = _run_invocation(
            evidence_dir,
            invocation,
            deps.environ,
            context["physical_gpu"],
            deps,
            cleaner,
        )
        attempts.extend(mapped)
        raw_attempt_records.extend(raw_attempt_record(row) for row in mapped)
        invocation_records.append({field: metadata[field] for field in RAW_INVOCATION_FIELDS})
        raw_payloads.append((metadata, payload))
    if list(deps.environ.items()) != parent_before:
        raise DevelopmentPoolError("parent_environment_mutated", "parent environment was modified")
    assert_attempt_accounting(attempts, schedule)
    stored_schedule = deps.read_bytes(os.path.join(evidence_dir, SCHEDULE_NAME))
    if stored_schedule != context["schedule_bytes"] or _sha256(stored_schedule) != context["schedule_sha256"]:
        raise DevelopmentPoolError("schedule_hash_mismatch", "schedule bytes changed after they were written")
    audited = serialize_jsonl(attempts, ATTEMPT_FIELDS, "original_attempt_index")
    raw_ledger = serialize_jsonl(raw_attempt_records, RAW_ATTEMPT_FIELDS, "original_attempt_index")
    if raw_ledger == audited:
        raise DevelopmentPoolError("ledger_not_distinct", "raw and audited ledgers must be semantically distinct")
    if len(raw_attempt_records) != ATTEMPT_COUNT or raw_ledger.count(b"\n") != ATTEMPT_COUNT:
        raise DevelopmentPoolError("attempt_accounting_invalid", "raw ledger line count is not 1000")
    if len(attempts) != ATTEMPT_COUNT or audited.count(b"\n") != ATTEMPT_COUNT:
        raise DevelopmentPoolError("attempt_accounting_invalid", "audited ledger line count is not 1000")
    if len(invocation_records) != schedule["invocation_count"]:
        raise DevelopmentPoolError("attempt_accounting_invalid", "invocation output count does not match the schedule")
    invocation_manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "role": "invocation_output_manifest",
        "invocation_count": len(invocation_records),
        "invocations": invocation_records,
    }
    invocation_bytes = canonical_json_bytes(invocation_manifest)
    writer(os.path.join(evidence_dir, RAW_LEDGER_NAME), raw_ledger)
    writer(os.path.join(evidence_dir, AUDITED_LEDGER_NAME), audited)
    metrics = context["metrics_module"].summarise_attempts(attempts)
    metrics_file_bytes = canonical_json_bytes(metrics)
    writer(os.path.join(evidence_dir, METRICS_NAME), metrics_file_bytes)
    writer(os.path.join(evidence_dir, INVOCATION_OUTPUT_MANIFEST_NAME), invocation_bytes)
    provenance = dict(context["provenance"])
    provenance.pop("cleaner_source_bytes", None)
    provenance.pop("metrics_module", None)
    provenance.pop("metrics_source_bytes", None)
    provenance.pop("metrics_configuration_bytes", None)
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "status": "complete",
        "condition": CONDITION_LABEL,
        "schedule_sha256": context["schedule_sha256"],
        "invocation_count": schedule["invocation_count"],
        "raw_attempts": ATTEMPT_COUNT,
        "independent_biological_replicates": False,
        "diagnostic_generation_sample": True,
        "exact_hit_rate_is_execution_success_requirement": False,
        "early_eos_is_a_technical_failure": False,
        "length_mismatch_is_a_technical_failure": False,
        "invalid_accounted_output_is_a_technical_failure": False,
        "duplicate_output_is_a_technical_failure": False,
        "exact_length_accepted_pool_declared": False,
        "final_production_mapping_declared": False,
        "final_m8_production_protocol_declared": False,
        "m4_complete": False,
        "metrics": metrics,
        "provenance": provenance,
        "physical_gpu": context["physical_gpu"],
        "gpu_uuid": context["authorisation"]["gpu_uuid"],
        "pci_bus": context["authorisation"]["pci_bus"],
        "logical_device": LOGICAL_DEVICE,
        "reusable_by_later_d1_generation": True,
        "raw_ledger_sha256": _sha256(raw_ledger),
        "audited_ledger_sha256": _sha256(audited),
        "invocation_output_manifest_sha256": _sha256(invocation_bytes),
    }
    manifest_bytes = canonical_json_bytes(manifest)
    hash_report_bytes = canonical_json_bytes(
        {
            "development_pool_manifest_sha256": _sha256(manifest_bytes),
            "development_pool_schedule_sha256": context["schedule_sha256"],
            "development_pool_raw_attempts_sha256": _sha256(raw_ledger),
            "development_pool_audited_attempts_sha256": _sha256(audited),
            "development_pool_metrics_sha256": _sha256(metrics_file_bytes),
            "development_pool_invocation_outputs_sha256": _sha256(invocation_bytes),
        }
    )
    writer(os.path.join(evidence_dir, HASH_REPORT_NAME), hash_report_bytes)
    verify_bound_evidence_file(os.path.join(evidence_dir, SCHEDULE_NAME), context["schedule_bytes"], deps)
    verify_bound_evidence_file(os.path.join(evidence_dir, SCHEDULE_HASH_NAME), schedule_hash_bytes, deps)
    for metadata, payload in raw_payloads:
        verify_regular_file(metadata["raw_file_path"], metadata, deps, cleaner, expected_bytes=payload)
    verify_bound_evidence_file(
        os.path.join(evidence_dir, INVOCATION_OUTPUT_MANIFEST_NAME),
        invocation_bytes,
        deps,
    )
    verify_bound_evidence_file(os.path.join(evidence_dir, RAW_LEDGER_NAME), raw_ledger, deps)
    verify_bound_evidence_file(os.path.join(evidence_dir, AUDITED_LEDGER_NAME), audited, deps)
    verify_bound_evidence_file(os.path.join(evidence_dir, METRICS_NAME), metrics_file_bytes, deps)
    verify_bound_evidence_file(os.path.join(evidence_dir, HASH_REPORT_NAME), hash_report_bytes, deps)
    reverify_bound_source(
        METRICS_PATH,
        context["metrics_source_bytes"],
        deps,
        "metrics_source_drift",
    )
    reverify_bound_source(
        METRICS_CONFIG_PATH,
        context["metrics_configuration_bytes"],
        deps,
        "metrics_configuration_drift",
    )
    success_path = os.path.join(evidence_dir, SUCCESS_MANIFEST_NAME)
    failure_path = os.path.join(evidence_dir, FAILURE_MANIFEST_NAME)
    if _path_exists(failure_path, deps.lstat) or _path_exists(success_path, deps.lstat):
        raise DevelopmentPoolError("manifest_collision", "success and failure manifests must be mutually exclusive")
    writer(success_path, manifest_bytes)
    if _path_exists(failure_path, deps.lstat):
        raise DevelopmentPoolError("manifest_collision", "success and failure manifests must be mutually exclusive")
    return {"status": "success", "schedule_sha256": context["schedule_sha256"], "metrics": metrics}


def after_directory_created(evidence_dir, deps, operation):
    try:
        return operation()
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        error = normalize_evidence_error(exc)
        if not isinstance(error, DevelopmentPoolError):
            error = DevelopmentPoolError("unexpected_runtime_failure", "unexpected runtime failure")
        if _path_exists(os.path.join(evidence_dir, SUCCESS_MANIFEST_NAME), deps.lstat):
            raise error
        try:
            _write_failure(evidence_dir, error.code, error.detail, deps)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as secondary:
            error.secondary_failure = getattr(secondary, "code", None) or "failure_manifest_write_failed"
        raise error


def run(output_directory, physical_gpu_argument, length_vector_path, deps):
    """Refuse a closed configuration before GPU queries and length-vector access."""
    config_bytes = deps.read_bytes(B1_CONFIG_PATH)
    config = load_config_bytes(config_bytes)
    assert_configuration_consumable(config)
    physical_gpu = parse_physical_gpu_argument(physical_gpu_argument)
    authorisation = assert_development_pool_authorisation(config, physical_gpu, output_directory)
    assert_output_directory_absent(output_directory, deps.lstat)
    assert_parent_cuda(deps.environ, physical_gpu)
    provenance = measure_provenance(authorisation, deps)
    probe = deps.gpu_preflight(deps.environ, physical_gpu)
    assert_gpu_probe(probe, physical_gpu, authorisation)
    ordered_lengths = parse_length_vector(deps.read_bytes(length_vector_path))
    schedule = build_schedule(ordered_lengths, require_source_count=SOURCE_COUNT)
    if schedule["numpy_version"] != provenance["numpy_version"]:
        raise DevelopmentPoolError("numpy_version_unbound", "schedule NumPy version drifted from the measured version")
    body = canonical_schedule_bytes(schedule)
    digest = _sha256(body)
    if digest != authorisation["schedule_sha256"]:
        raise DevelopmentPoolError("schedule_hash_mismatch", "materialised schedule hash does not match the authorisation")
    metrics_module = provenance.pop("metrics_module")
    metrics_source_bytes = provenance.pop("metrics_source_bytes")
    metrics_configuration_bytes = provenance.pop("metrics_configuration_bytes")
    cleaner = load_cleaner_from_verified_source(provenance["cleaner_source_bytes"])
    deps.mkdir(output_directory)
    context = {
        "output_directory": output_directory,
        "physical_gpu": physical_gpu,
        "authorisation": authorisation,
        "provenance": provenance,
        "schedule": schedule,
        "schedule_bytes": body,
        "schedule_sha256": digest,
        "metrics_module": metrics_module,
        "metrics_source_bytes": metrics_source_bytes,
        "metrics_configuration_bytes": metrics_configuration_bytes,
    }
    return after_directory_created(
        output_directory,
        deps,
        lambda: execute_authorised(context, deps, cleaner),
    )


def default_read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def default_sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_git(repo, args):
    argv = ["git", "-C", str(repo)]
    argv.extend(list(args))
    completed = subprocess.run(argv, shell=False, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise DevelopmentPoolError("git_status_unreadable", completed.stderr.strip() or "git command failed")
    return completed.stdout


def default_subprocess_run(argv, cwd, env, shell=False):
    if shell is not False:
        raise DevelopmentPoolError("shell_prohibited", "subprocess shell must stay false")
    if not isinstance(argv, list) or not argv or argv[0] != PINNED_PYTHON:
        raise DevelopmentPoolError("python_interpreter_rejected", "generation interpreter is not the pinned Python")
    if cwd != GENERATION_CWD:
        raise DevelopmentPoolError("generation_cwd_rejected", "generation working directory is not RNAGenesis")
    completed = subprocess.run(argv, cwd=cwd, env=env, shell=False, check=False, capture_output=True)
    return completed


def default_gpu_preflight(parent, physical_gpu):
    assert_parent_cuda(parent, physical_gpu)
    completed = subprocess.run(
        physical_gpu_query_argv(physical_gpu),
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise DevelopmentPoolError("unauthorized_gpu", "GPU query failed")
    return parse_gpu_probe(completed.stdout, physical_gpu)


class RunnerDependencies(object):
    def __init__(
        self,
        read_bytes=None,
        lstat=None,
        realpath=None,
        sha256_file=None,
        environ=None,
        git=None,
        gpu_preflight=None,
        mkdir=None,
        write_exclusive=None,
        subprocess_run=None,
    ):
        self.read_bytes = read_bytes or default_read_bytes
        self.lstat = lstat or os.lstat
        self.realpath = realpath or os.path.realpath
        self.sha256_file = sha256_file or default_sha256_file
        self.environ = os.environ if environ is None else environ
        self.git = git or default_git
        self.gpu_preflight = gpu_preflight or default_gpu_preflight
        self.mkdir = mkdir or os.mkdir
        self.write_exclusive = write_exclusive or _exclusive_write
        self.subprocess_run = subprocess_run or default_subprocess_run


def production_dependencies():
    return RunnerDependencies()


def build_parser():
    parser = argparse.ArgumentParser(description="B1 development-pool diagnostic runner")
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--physical-gpu", required=True)
    parser.add_argument("--length-vector", required=True)
    return parser


def main(argv=None):
    """Construct production dependencies and refuse a closed configuration first."""
    deps = production_dependencies()
    parser = build_parser()
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 2
        return int(code)
    try:
        config = load_config_bytes(deps.read_bytes(B1_CONFIG_PATH))
        assert_configuration_consumable(config)
    except DevelopmentPoolError as exc:
        print(exc.code + ": " + exc.detail, file=sys.stderr)
        return 2
    try:
        run(args.output_directory, args.physical_gpu, args.length_vector, deps)
    except DevelopmentPoolError as exc:
        message = exc.code + ": " + exc.detail
        if exc.secondary_failure:
            message += " secondary: " + exc.secondary_failure
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
