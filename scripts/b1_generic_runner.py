#!/usr/bin/env python3
"""Non-executable M4 B1 Phase A runner.

The checked-in B1 configuration revokes an unconsumed physical GPU 0
Phase A authorisation. That authorisation produced no evidence. This
module constructs the Phase A plan, the future generation commands, and
the evidence writers. It does not import a model stack or Torch. The
current document fails closed before a directory is created, a GPU is
queried, a multi-gigabyte weight is hashed, the approved cleaner is
imported, or another Python process is started.

A future authorised preflight may name only physical GPU 1. It queries
that device and then confirms logical cuda:0 inside a child process.
That child is the only place Torch is imported. This process never treats
CUDA_VISIBLE_DEVICES, CUDA_DEVICE_ORDER, or nvidia-smi as confirmation
that logical device 0 is usable.

Phase A is a response-mapping experiment. It does not declare B1 eligible,
infer a Phase B length mapping, sample the development pool, or evaluate
corpus-dependent guardrails.
"""

from __future__ import annotations

import argparse
import collections.abc
import hashlib
import json
import os
import stat
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import yaml

MRES_ROOT = Path("/home/laura/rnagenesis-aptamer-mres")
RNAGENESIS_ROOT = Path("/home/laura/RNAGenesis")
RUNNER_RELATIVE = "scripts/b1_generic_runner.py"
RUNNER_PATH = MRES_ROOT / RUNNER_RELATIVE
B1_CONFIG_PATH = MRES_ROOT / "config/experiments/B1_generic_generation.yaml"
PINNED_PYTHON = "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python"
GENERATION_ENTRY = RNAGENESIS_ROOT / "generation.py"
APPROVED_CLEANER = RNAGENESIS_ROOT / "scripts/audit_generation_output.py"
# M0 environment manifest, 25 September 2026. The pinned generation path
# loads diffusers.models.attention.BasicTransformerBlock, which imports
# AdaLayerNorm from this installed file. The recorded SHA-256 is the M0
# patch hash; this module does not invent a replacement.
DIFFUSERS_PATCH_PATH = (
    "/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/"
    "site-packages/diffusers/models/normalization.py"
)
DIFFUSERS_PATCH_SHA256 = (
    "09bc632069f1d6e1dc1b1cb7f5b9ca096c83e3010835f11b8dc6c58b45aa13a5"
)
DIFFUSERS_PATCH_SIZE = 9516
PROHIBITED_CLEANER = MRES_ROOT / "scripts/clean_generated_sequences.py"
PROHIBITED_DIFFUSION = RNAGENESIS_ROOT / "checkpoints/Aptamer/diffusion"
GENERATION_CWD = str(RNAGENESIS_ROOT)
RUN_ROOT = Path("/home/laura/rnagenesis-mres-runs")

RNAGENESIS_HEAD = "e3b855bbf4d1af376f43747643fa30afd662828c"
RNAGENESIS_BRANCH = "mres-d1-diffusion-finetune"
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
GENERATION_SHA256 = (
    "d1b1fca9544ed1c85cf6fdd304b5acb965d76ca6c89a2f98e57224ac95e44367"
)
CLEANER_SHA256 = (
    "4d0c56a7d931a2c3c5c049cfeabd4937134b3d1125ef7a68b10472527d2fd2a2"
)
CONDITION_LABEL = "B1_generic_released_rnagenesis"
EXECUTABLE_DOCUMENT_STATUS = "APPROVED_FOR_SCIENTIFIC_EXECUTION"
NON_EXECUTABLE_DOCUMENT_STATUSES = frozenset(
    [
        "DRAFT_PENDING_HUMAN_APPROVAL",
        "APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION",
        "APPROVED_DESIGN_NOT_APPROVED_FOR_GPU_EXECUTION",
    ]
)
PHASE_A_EXECUTION_STATUS = "AUTHORISED_FOR_EXECUTION"
ACTIVE_UNCONSUMED_STATUS = "active_unconsumed"
# The next executable authorisation may name only this physical device.
# Logical cuda:0 is that device after visibility remapping.
PHYSICAL_GPU = 1
CUDA_DEVICE_ORDER = "PCI_BUS_ID"
MANIFEST_SCHEMA_VERSION = "m4-b1-phase-a-manifest-1"

REQUESTED_LENGTHS = (20, 30, 40, 50, 60, 70, 80, 90, 100, 112, 123)
BASE_SEED = 41000
ATTEMPTS_PER_CAP = 16
INVOCATION_COUNT = 33
TOTAL_ATTEMPTS = 528
BATCH_SIZE = 16
BATCH_NUM = 1
DDIM_STEPS = 50
ENCDEC_RELATIVE = "configs/rnagenesis/autoencoder"
DIFFUSION_RELATIVE = "configs/rnagenesis/diffusion"
CLASSIFIER_RELATIVE = "configs/rnagenesis/classifier/mlp_160_32.yaml"
DECODER_CONFIG_NAME = "config-progen2-small-rna_tokenizer_v2"

# generation.py marks these arguments required even when the enabling flags
# are absent. They do not turn guidance or search on. Guidance stays off
# because --guidance is not passed, so the classifier path is not read by
# the generation workflow.
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
        "--search_general",
        "--tree_search",
        "--tree-search",
        "--truncate",
        "--extend_input",
        "--extend-input",
        "--update_seq",
        "--update-sequence",
        "--update_sequence",
        "--save_latent_space",
        "--multiple_eos_tokens",
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
PROHIBITED_PATH_COMPONENTS = frozenset(["TRAIN", "VALIDATION", "REF", "EVAL"])
PROHIBITED_SUBSTITUTE_SHA256 = {
    "57035677145791f1789ef2ba01fa50d86b0487a4023cfc7bd4e860ea1f5b28bb": (
        "checkpoint-15000"
    ),
    "666f501700055e79b4f4f469d357752a7f110430db1bc9273376ebc55e0259c5": (
        "checkpoint-30000"
    ),
}

SCIENTIFIC_AUTHORISATION_KEYS = (
    "authorisation_id",
    "authorisation_active",
    "activation_status",
    "consumed",
    "authorises_b1_phase_a",
    "gpu_use_authorised",
    "physical_gpu",
    "executing_implementation_commit",
    "mres_branch",
    "condition",
    "phase",
    "output_directory",
    "evidence_directory",
    "success_claimed",
    "m4_complete",
    "b1_eligible",
    "phase_b_authorised",
    "development_pool_authorised",
)

OFFLINE_CONTROLS = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}

RAW_LEDGER_NAME = "phase_a_raw_attempts.jsonl"
AUDITED_LEDGER_NAME = "phase_a_audited_attempts.jsonl"
SUCCESS_MANIFEST_NAME = "phase_a_manifest.json"
FAILURE_MANIFEST_NAME = "phase_a_failure_manifest.json"
HASH_REPORT_NAME = "phase_a_manifest_sha256.json"
PYCACHE_DIRECTORY_NAME = "python_pycache"
RUNTIME_CACHE_DIRECTORY_NAME = "isolated_runtime_cache"
# Direct third-party imports of the pinned generation entry and its
# module-level import closure. Distribution name, then import name.
# ViennaRNA has no importlib.metadata distribution; the child probe reads
# RNA.__version__ only for that package.
GENERATION_CRITICAL_PACKAGES = (
    ("numpy", "numpy"),
    ("torch", "torch"),
    ("diffusers", "diffusers"),
    ("transformers", "transformers"),
    ("omegaconf", "omegaconf"),
    ("tokenizers", "tokenizers"),
    ("rna-fm", "fm"),
    ("ViennaRNA", "RNA"),
)
GENERATION_CRITICAL_DISTRIBUTIONS = tuple(
    distribution for distribution, _module_name in GENERATION_CRITICAL_PACKAGES
)
ATTEMPT_KEYS = (
    "invocation_index",
    "attempt_index",
    "attempt_within_candidate",
    "pairing_group",
    "requested_biological_length",
    "max_seq_len",
    "cap_offset",
    "seed",
    "raw_decoded_text",
    "raw_length",
    "cleaned_sequence",
    "cleaned_length",
    "leading_boundary_marker_run",
    "trailing_boundary_marker_run",
    "validity",
    "rejection_reason",
    "termination_observation",
)
# Raw ledger keeps generation metadata, the raw decoded output, and enough
# audit status to show that a rejected attempt was retained.
RAW_LEDGER_KEYS = (
    "invocation_index",
    "attempt_index",
    "attempt_within_candidate",
    "pairing_group",
    "requested_biological_length",
    "max_seq_len",
    "cap_offset",
    "seed",
    "raw_decoded_text",
    "raw_length",
    "validity",
    "rejection_reason",
)
AUDITED_LEDGER_KEYS = ATTEMPT_KEYS
CUDA_PROBE_KEYS = (
    "python_executable",
    "python_version",
    "torch_version",
    "cuda_version",
    "cuda_available",
    "device_count",
    "logical_device_index",
    "logical_device",
    "device_name",
    "logical_device_confirmed",
    "allocation_ok",
    "packages",
    "cuda_visible_devices",
    "cuda_device_order",
)


def _cuda_probe_lines():
    """Child-only probe text. This process never executes it."""
    lines = [
        "import importlib.metadata as importlib_metadata",
        "import json",
        "import sys",
        "payload = {",
        '    "python_executable": sys.executable,',
        '    "python_version": sys.version.split()[0],',
        '    "torch_version": None,',
        '    "cuda_version": None,',
        '    "cuda_available": False,',
        '    "device_count": 0,',
        '    "logical_device_index": None,',
        '    "logical_device": None,',
        '    "device_name": None,',
        '    "logical_device_confirmed": False,',
        '    "allocation_ok": False,',
        '    "packages": {},',
        '    "cuda_visible_devices": __import__("os").environ.get("CUDA_VISIBLE_DEVICES"),',
        '    "cuda_device_order": __import__("os").environ.get("CUDA_DEVICE_ORDER"),',
        "}",
        "def package_version(distribution, module_name):",
        "    try:",
        "        return importlib_metadata.version(distribution)",
        "    except importlib_metadata.PackageNotFoundError:",
        "        if distribution != 'ViennaRNA':",
        "            raise",
        "        module = __import__(module_name)",
        "        version = getattr(module, '__version__', None)",
        "        if not isinstance(version, str) or version.strip() == '':",
        "            raise",
        "        return version",
        "try:",
        "    import torch",
        "except Exception:",
        '    payload["import_error"] = "torch_import_failed"',
        "    sys.stdout.write(json.dumps(payload, sort_keys=True))",
        '    sys.stdout.write("\\n")',
        "    raise SystemExit(1)",
        'payload["torch_version"] = torch.__version__',
        "try:",
        "    if package_version('torch', 'torch') != torch.__version__:",
        "        raise RuntimeError('torch version mismatch')",
    ]
    for distribution, module_name in GENERATION_CRITICAL_PACKAGES:
        lines.append(
            "    payload['packages'][{0!r}] = package_version({0!r}, {1!r})".format(
                distribution,
                module_name,
            )
        )
    lines.extend(
        [
            "except Exception:",
            '    payload["import_error"] = "package_version_failed"',
            "    sys.stdout.write(json.dumps(payload, sort_keys=True))",
            '    sys.stdout.write("\\n")',
            "    raise SystemExit(1)",
            'payload["cuda_version"] = torch.version.cuda',
            'payload["cuda_available"] = True if torch.cuda.is_available() else False',
            "if payload['cuda_available']:",
            '    payload["device_count"] = int(torch.cuda.device_count())',
            "if payload['cuda_available'] and payload['device_count'] == 1:",
            "    try:",
            '        tensor = torch.zeros(1, device="cuda:0")',
            "        torch.cuda.synchronize(0)",
            "        del tensor",
            '        payload["logical_device_index"] = 0',
            '        payload["logical_device"] = "cuda:0"',
            '        payload["device_name"] = torch.cuda.get_device_name(0)',
            '        payload["logical_device_confirmed"] = True',
            '        payload["allocation_ok"] = True',
            "    except Exception:",
            '        payload["allocation_ok"] = False',
            '        payload["logical_device_confirmed"] = False',
            "sys.stdout.write(json.dumps(payload, sort_keys=True))",
            'sys.stdout.write("\\n")',
        ]
    )
    return lines


# Executed only in the pinned child interpreter. This process does not import Torch.
CUDA_PROBE_SOURCE = "\n".join(_cuda_probe_lines()) + "\n"
EOS_OBSERVED = "eos_marker_observed"
TERMINATION_NOT_OBSERVABLE = "not_observable_from_decoded_text"
ACCESS_DECLARATION = {
    "train_opened": False,
    "validation_opened": False,
    "ref_opened": False,
    "eval_opened": False,
    "biological_sequence_data_opened": False,
    "classifier_read_by_generation_workflow": False,
    "guidance_enabled": False,
    "development_pool_sampled": False,
    "phase_b_executed": False,
    "corpus_dependent_guardrails": "not_evaluated",
    "exact_train_match_rate": "not_evaluated",
    "b1_eligibility": "not_declared",
    "m4_complete": False,
}


class B1RunnerError(Exception):
    """Fail-closed error. Detail must not contain generated sequence text."""

    def __init__(self, code, detail):
        self.code = str(code)
        self.detail = str(detail)
        self.secondary_failure = None
        super().__init__("{}: {}".format(self.code, self.detail))


class PinnedFile(object):
    def __init__(self, relative, size, sha256, role, large, absolute=None):
        self.relative = relative
        self.size = size
        self.sha256 = sha256
        self.role = role
        self.large = large
        self.absolute = absolute

    def absolute_path(self):
        if self.absolute is not None:
            return Path(self.absolute)
        return RNAGENESIS_ROOT / self.relative


def _pin(relative, size, sha256, role, large=False, absolute=None):
    return PinnedFile(relative, size, sha256, role, large, absolute)


PINNED_FILES = (
    _pin(
        "generation.py",
        None,
        GENERATION_SHA256,
        "generation_entry",
    ),
    _pin(
        "scripts/audit_generation_output.py",
        None,
        CLEANER_SHA256,
        "approved_cleaner",
    ),
    _pin(
        "configs/rnagenesis/autoencoder/config.json",
        530,
        "ab309231b75405af3e2ef6fe49e4e74c1b96021ef2a4f61b46e5796b8799378a",
        "encdec_config",
    ),
    _pin(
        "configs/rnagenesis/autoencoder/pytorch_model.bin",
        3476049782,
        "3c4e34f7626c94416d504c16569b5f3f785fffe77889b9886344477b95e74c68",
        "encdec_weights",
        True,
    ),
    _pin(
        "configs/rnagenesis/diffusion/model_index.json",
        217,
        "05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e",
        "diffusion_model_index",
    ),
    _pin(
        "configs/rnagenesis/diffusion/scheduler/scheduler_config.json",
        492,
        "6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396",
        "diffusion_scheduler_config",
    ),
    _pin(
        "configs/rnagenesis/diffusion/unet/config.json",
        531,
        "3a9975ff165bbd5ca82923e6ed1c5ed7eb383a23f4f3f55db713c995031f8ee3",
        "diffusion_unet_config",
    ),
    _pin(
        "configs/rnagenesis/diffusion/unet/diffusion_pytorch_model.safetensors",
        7847725416,
        "c268021b6cab37423e3bffd495b139bb69698d8d11c7b96477fbfb239b0cff26",
        "diffusion_unet_weights",
        True,
    ),
    _pin(
        "models/autoencoder/encoder/biomap/config.json",
        1369,
        "bf7ef6843232f370f3f7fc37d608f85cb0ff0d75291eed35cef52213e34978f7",
        "biomap_encoder_config",
    ),
    _pin(
        "models/autoencoder/decoder/progen_configs/config-progen2-small-rna_tokenizer_v2.json",
        915,
        "42f15517e05ce96d78337fbc1bf20ffc580424fe88cbfcb2c81550b17cc7283e",
        "decoder_config",
    ),
    _pin(
        "models/autoencoder/decoder/progen_configs/tokenizer_rna_v2.json",
        1317,
        "6d8a20879cec3544cf0f33b0d481fbd5ead6a2bead2dbf1649449172c8336921",
        "rna_tokenizer",
    ),
    _pin(
        CLASSIFIER_RELATIVE,
        None,
        "9014f4594b90867a393da9212545ea1d322a8bffd23bfb25690999a55ac4a97d",
        "classifier_inert",
    ),
    _pin(
        "diffusers/models/normalization.py",
        DIFFUSERS_PATCH_SIZE,
        DIFFUSERS_PATCH_SHA256,
        "diffusers_normalization_patch",
        absolute=DIFFUSERS_PATCH_PATH,
    ),
)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="b1_generic_runner",
        description=(
            "M4 B1 Phase A response-mapping runner. "
            "The current configuration is not executable."
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Authorised Phase A evidence directory. Relative paths are refused.",
    )
    return parser


def load_config_bytes(raw):
    if not isinstance(raw, (bytes, bytearray)):
        raise B1RunnerError("config_encoding", "configuration bytes are required")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise B1RunnerError(
            "config_encoding",
            "configuration must be UTF-8 without a BOM or carriage return",
        )
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        raise B1RunnerError("config_encoding", "configuration is not valid UTF-8")
    try:
        loaded = yaml.safe_load(text)
    except Exception:
        raise B1RunnerError("config_parse", "configuration could not be parsed")
    if not isinstance(loaded, dict):
        raise B1RunnerError("config_shape", "configuration root must be a mapping")
    return loaded


def _require_mapping(value, code, detail):
    if not isinstance(value, dict):
        raise B1RunnerError(code, detail)
    return value


def _is_sha40(value):
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def evidence_directory_for_commit(commit):
    if not _is_sha40(commit):
        raise B1RunnerError(
            "authorisation_commit_invalid",
            "executing_implementation_commit is not a 40-character lowercase SHA-1",
        )
    sha12 = commit[:12]
    return (
        "/home/laura/rnagenesis-mres-runs/"
        "m4_b1_generic_generation_B1_generic_released_rnagenesis_"
        + sha12
        + "_phaseA"
    )


def assert_document_gates(config):
    """Cheap document gates. No directory, GPU, hash, import, or subprocess."""
    if "consumable_by_executable_workflow" not in config:
        raise B1RunnerError(
            "configuration_not_consumable",
            "consumable_by_executable_workflow is missing",
        )
    if config["consumable_by_executable_workflow"] is not True:
        raise B1RunnerError(
            "configuration_not_consumable",
            "consumable_by_executable_workflow is not true",
        )
    if "document_status" not in config:
        raise B1RunnerError(
            "configuration_not_consumable",
            "document_status is missing",
        )
    status = config["document_status"]
    if status in NON_EXECUTABLE_DOCUMENT_STATUSES or status != EXECUTABLE_DOCUMENT_STATUS:
        raise B1RunnerError(
            "configuration_not_consumable",
            "document_status is not {}".format(EXECUTABLE_DOCUMENT_STATUS),
        )

    phase = _require_mapping(
        config.get("phase_a"),
        "phase_a_not_authorised",
        "phase_a is missing",
    )
    if "executable_now" not in phase:
        raise B1RunnerError(
            "phase_a_not_authorised",
            "phase_a.executable_now is missing",
        )
    if phase["executable_now"] is not True:
        raise B1RunnerError(
            "phase_a_not_authorised",
            "phase_a.executable_now is not true",
        )
    if "status" not in phase:
        raise B1RunnerError(
            "phase_a_not_authorised",
            "phase_a.status is missing",
        )
    if phase["status"] != PHASE_A_EXECUTION_STATUS:
        raise B1RunnerError(
            "phase_a_not_authorised",
            "phase_a.status is not {}".format(PHASE_A_EXECUTION_STATUS),
        )

    execution = _require_mapping(
        config.get("execution"),
        "gpu_not_authorised",
        "execution is missing",
    )
    if "gpu_authorised_by_this_approval" not in execution:
        raise B1RunnerError(
            "gpu_not_authorised",
            "execution.gpu_authorised_by_this_approval is missing",
        )
    if execution["gpu_authorised_by_this_approval"] is not True:
        raise B1RunnerError(
            "gpu_not_authorised",
            "execution.gpu_authorised_by_this_approval is not true",
        )
    if "authorised" not in execution:
        raise B1RunnerError(
            "execution_not_authorised",
            "execution.authorised is missing",
        )
    if execution["authorised"] is not True:
        raise B1RunnerError(
            "execution_not_authorised",
            "execution.authorised is not true",
        )

    if "scientific_execution_authorisation" not in config:
        raise B1RunnerError(
            "scientific_authorisation_missing",
            "scientific_execution_authorisation is missing",
        )
    block = config["scientific_execution_authorisation"]
    if not isinstance(block, dict):
        raise B1RunnerError(
            "scientific_authorisation_missing",
            "scientific_execution_authorisation is missing",
        )
    if set(block) != set(SCIENTIFIC_AUTHORISATION_KEYS):
        missing = [key for key in SCIENTIFIC_AUTHORISATION_KEYS if key not in block]
        unexpected = sorted(set(block) - set(SCIENTIFIC_AUTHORISATION_KEYS))
        if missing:
            raise B1RunnerError(
                "scientific_authorisation_incomplete",
                "scientific_execution_authorisation.{} is missing".format(missing[0]),
            )
        raise B1RunnerError(
            "scientific_authorisation_incomplete",
            "scientific_execution_authorisation has unexpected fields: {}".format(
                ", ".join(unexpected)
            ),
        )
    snapshot = _validate_scientific_authorisation(block, config)
    return snapshot


def _require_text(block, key):
    value = block[key]
    if not isinstance(value, str) or value.strip() == "":
        raise B1RunnerError(
            "scientific_authorisation_incomplete",
            "scientific_execution_authorisation.{} is missing".format(key),
        )
    return value


def _validate_scientific_authorisation(block, config):
    if block["authorisation_active"] is not True:
        raise B1RunnerError(
            "scientific_authorisation_inactive",
            "authorisation_active is not true",
        )
    if block["activation_status"] != ACTIVE_UNCONSUMED_STATUS:
        raise B1RunnerError(
            "scientific_authorisation_inactive",
            "activation_status is not active_unconsumed",
        )
    if block["consumed"] is not False:
        raise B1RunnerError(
            "scientific_authorisation_consumed",
            "scientific authorisation is not unconsumed",
        )
    if block["authorises_b1_phase_a"] is not True:
        raise B1RunnerError(
            "phase_a_not_authorised",
            "authorises_b1_phase_a is not true",
        )
    if block["phase"] != "A":
        raise B1RunnerError(
            "phase_a_not_authorised",
            "authorisation phase is not A",
        )
    if block["gpu_use_authorised"] is not True:
        raise B1RunnerError(
            "gpu_not_authorised",
            "gpu_use_authorised is not true",
        )
    if type(block["physical_gpu"]) is not int or block["physical_gpu"] != PHYSICAL_GPU:
        raise B1RunnerError(
            "gpu_not_authorised",
            "authorisation does not name physical GPU {}".format(PHYSICAL_GPU),
        )
    commit = _require_text(block, "executing_implementation_commit")
    if not _is_sha40(commit):
        raise B1RunnerError(
            "authorisation_commit_invalid",
            "executing_implementation_commit is not a 40-character lowercase SHA-1",
        )
    if block["mres_branch"] != "main":
        raise B1RunnerError(
            "mres_branch_not_main",
            "authorisation mres_branch is not main",
        )
    if block["condition"] != CONDITION_LABEL:
        raise B1RunnerError(
            "scientific_authorisation_incomplete",
            "authorisation condition is not B1_generic_released_rnagenesis",
        )
    if config.get("condition_manifest_label") != CONDITION_LABEL:
        raise B1RunnerError(
            "scientific_authorisation_incomplete",
            "condition_manifest_label is not B1_generic_released_rnagenesis",
        )
    _require_text(block, "authorisation_id")
    expected_directory = evidence_directory_for_commit(commit)
    if (
        block["output_directory"] != expected_directory
        or block["evidence_directory"] != expected_directory
    ):
        raise B1RunnerError(
            "authorisation_evidence_mismatch",
            "authorisation does not bind B1 Phase A to the exact evidence directory",
        )
    if block["success_claimed"] is not False:
        raise B1RunnerError(
            "scientific_authorisation_incomplete",
            "success_claimed must be false before execution",
        )
    if block["m4_complete"] is not False:
        raise B1RunnerError(
            "scientific_authorisation_incomplete",
            "m4_complete must be false",
        )
    if block["b1_eligible"] is not False:
        raise B1RunnerError(
            "b1_eligibility_not_claimable",
            "Phase A cannot declare B1 eligible",
        )
    if block["phase_b_authorised"] is not False:
        raise B1RunnerError(
            "phase_b_not_authorised",
            "Phase B is not authorised by a Phase A run",
        )
    if block["development_pool_authorised"] is not False:
        raise B1RunnerError(
            "development_pool_not_authorised",
            "the development pool is not authorised",
        )
    snapshot = {}
    for key in SCIENTIFIC_AUTHORISATION_KEYS:
        snapshot[key] = block[key]
    return snapshot


def _require_exact(mapping, key, expected, code, detail):
    if key not in mapping or mapping[key] != expected:
        raise B1RunnerError(code, detail)


def build_phase_a_plan(config):
    """Build the 33-invocation plan from the approved YAML invariants."""
    phase = _require_mapping(
        config.get("phase_a"),
        "phase_a_plan_invalid",
        "phase_a is missing",
    )
    if "target_biological_lengths" not in phase:
        raise B1RunnerError(
            "phase_a_plan_invalid",
            "target_biological_lengths is missing",
        )
    if list(phase["target_biological_lengths"]) != list(REQUESTED_LENGTHS):
        raise B1RunnerError(
            "phase_a_plan_invalid",
            "requested lengths do not match the approved Phase A list",
        )
    _require_exact(
        phase,
        "candidate_max_seq_len_for_each_target",
        ["target", "target_plus_1", "target_plus_2"],
        "phase_a_plan_invalid",
        "candidate caps are not target, target+1, and target+2",
    )
    _require_exact(
        phase,
        "raw_attempts_per_candidate",
        ATTEMPTS_PER_CAP,
        "phase_a_plan_invalid",
        "raw_attempts_per_candidate is not 16",
    )
    _require_exact(
        phase,
        "invocations",
        INVOCATION_COUNT,
        "phase_a_plan_invalid",
        "invocations is not 33",
    )
    _require_exact(
        phase,
        "total_raw_attempts",
        TOTAL_ATTEMPTS,
        "phase_a_plan_invalid",
        "total_raw_attempts is not 528",
    )
    _require_exact(
        phase,
        "distinct_seeds",
        11,
        "phase_a_plan_invalid",
        "distinct_seeds is not 11",
    )
    _require_exact(
        phase,
        "base_seed",
        BASE_SEED,
        "phase_a_plan_invalid",
        "base_seed is not 41000",
    )
    _require_exact(
        phase,
        "first_seed",
        41000,
        "phase_a_plan_invalid",
        "first_seed is not 41000",
    )
    _require_exact(
        phase,
        "last_seed",
        41010,
        "phase_a_plan_invalid",
        "last_seed is not 41010",
    )
    if phase.get("same_seed_for_target_and_target_plus_1_and_target_plus_2") is not True:
        raise B1RunnerError(
            "phase_a_plan_invalid",
            "the three caps for one requested length must share a seed",
        )
    shape = phase.get("proposed_invocation_shape")
    if (
        not isinstance(shape, dict)
        or shape.get("batch_size") != BATCH_SIZE
        or shape.get("batch_num") != BATCH_NUM
    ):
        raise B1RunnerError(
            "phase_a_plan_invalid",
            "invocation shape is not batch_size 16 and batch_num 1",
        )
    shared = _require_mapping(
        config.get("shared_generation_settings"),
        "phase_a_plan_invalid",
        "shared_generation_settings is missing",
    )
    if "guidance" not in shared or shared["guidance"] is not False:
        raise B1RunnerError(
            "guidance_not_disabled",
            "shared_generation_settings.guidance is not false",
        )
    checks = (
        ("ddim_steps", DDIM_STEPS, "ddim_steps is not 50"),
        ("eta", 0, "eta is not 0"),
        ("top_p", 0.95, "top_p is not 0.95"),
        ("top_k", 0, "top_k is not 0"),
        ("do_sample", True, "do_sample is not true"),
        ("bos_token", 1, "bos_token is not 1"),
        ("eos_token", 2, "eos_token is not 2"),
        ("batch_size_where_memory_permits", BATCH_SIZE, "batch size is not 16"),
        ("automatic_batch_size_fallback", False, "automatic batch fallback is enabled"),
        ("cpu_fallback", False, "cpu fallback is enabled"),
        ("other_gpu_fallback", False, "other GPU fallback is enabled"),
        ("visible_python_device", "cuda:0", "visible device is not cuda:0"),
        ("physical_gpu_selected_by_this_document", False, "shared settings select a physical GPU"),
        (
            "cuda_device_order",
            CUDA_DEVICE_ORDER,
            "configured CUDA_DEVICE_ORDER is not {}".format(CUDA_DEVICE_ORDER),
        ),
    )
    if shared.get("physical_gpu") is not None or shared.get("cuda_visible_devices") is not None:
        raise B1RunnerError(
            "phase_a_plan_invalid",
            "shared settings must not hard-code a physical GPU",
        )
    historical = _require_mapping(
        config.get("historical_consumed_phase_a_and_phase_b_device"),
        "phase_a_plan_invalid",
        "historical consumed device binding is missing",
    )
    if (
        type(historical.get("physical_gpu")) is not int
        or historical.get("physical_gpu") != PHYSICAL_GPU
        or historical.get("cuda_visible_devices") != str(PHYSICAL_GPU)
        or historical.get("selects_a_device_for_the_development_pool") is not False
    ):
        raise B1RunnerError(
            "phase_a_plan_invalid",
            "historical consumed device binding drifted",
        )
    for key, expected, detail in checks:
        if key not in shared or shared[key] != expected:
            code = (
                "cpu_fallback_prohibited"
                if key in ("cpu_fallback", "other_gpu_fallback")
                else "phase_a_plan_invalid"
            )
            if key == "guidance":
                code = "guidance_not_disabled"
            raise B1RunnerError(code, detail)

    invocations = []
    for index, target in enumerate(REQUESTED_LENGTHS):
        seed = BASE_SEED + index
        for offset in (0, 1, 2):
            invocations.append(
                {
                    "invocation_index": len(invocations),
                    "requested_biological_length": target,
                    "max_seq_len": target + offset,
                    "cap_offset": offset,
                    "seed": seed,
                    "batch_size": BATCH_SIZE,
                    "batch_num": BATCH_NUM,
                    "attempt_index_first": 0,
                    "attempt_index_last": ATTEMPTS_PER_CAP - 1,
                    "fresh_process": True,
                }
            )
    if len(invocations) != INVOCATION_COUNT:
        raise B1RunnerError("phase_a_plan_invalid", "plan did not contain 33 invocations")
    if len(invocations) * ATTEMPTS_PER_CAP != TOTAL_ATTEMPTS:
        raise B1RunnerError("phase_a_plan_invalid", "plan did not contain 528 attempts")
    return invocations


def assert_cuda_environment(environ):
    """Refuse any parent or child environment that is not physical GPU 1.

    Both variables must match exactly. This runs before GPU preflight.
    """
    if not isinstance(environ, collections.abc.Mapping) or "CUDA_VISIBLE_DEVICES" not in environ:
        raise B1RunnerError(
            "cuda_visible_devices_missing",
            "CUDA_VISIBLE_DEVICES is not set",
        )
    visible = environ["CUDA_VISIBLE_DEVICES"]
    if type(visible) is not str or visible != str(PHYSICAL_GPU):
        raise B1RunnerError(
            "cuda_visible_devices_refused",
            'CUDA_VISIBLE_DEVICES must be exactly "{}"'.format(PHYSICAL_GPU),
        )
    if "CUDA_DEVICE_ORDER" not in environ:
        raise B1RunnerError(
            "cuda_device_order_missing",
            "CUDA_DEVICE_ORDER is not set",
        )
    order = environ["CUDA_DEVICE_ORDER"]
    if type(order) is not str or order != CUDA_DEVICE_ORDER:
        raise B1RunnerError(
            "cuda_device_order_refused",
            'CUDA_DEVICE_ORDER must be exactly "{}"'.format(CUDA_DEVICE_ORDER),
        )


def assert_output_directory(supplied, snapshot, lstat, realpath):
    expected = snapshot["evidence_directory"]
    if type(supplied) is not str or supplied != expected:
        raise B1RunnerError(
            "output_path_mismatch",
            "output directory is not the authorised Phase A evidence directory",
        )
    try:
        observed = lstat(supplied)
    except FileNotFoundError:
        observed = None
    if observed is not None and stat.S_ISLNK(observed.st_mode):
        raise B1RunnerError(
            "output_path_symlink",
            "output directory is a symlink",
        )
    if realpath(supplied) != supplied:
        raise B1RunnerError(
            "output_path_symlink",
            "output directory is a symlink or path alias",
        )
    if observed is not None:
        raise B1RunnerError(
            "output_path_exists",
            "output directory already exists",
        )


def _porcelain_lines(porcelain):
    if not isinstance(porcelain, str):
        raise B1RunnerError("git_status_unreadable", "git status porcelain could not be read")
    return [line for line in porcelain.splitlines() if line != ""]


def _split_porcelain(line):
    if len(line) < 4 or line[2] != " ":
        raise B1RunnerError("git_status_unreadable", "git status porcelain could not be read")
    return line[0], line[1], line[3:]


def _assert_mres_worktree_clean(porcelain):
    """Runtime MRes must have no tracked, staged, or untracked changes."""
    for line in _porcelain_lines(porcelain):
        index_status, worktree_status, _path = _split_porcelain(line)
        staged = index_status not in (" ", "?")
        tracked = worktree_status not in (" ", "?")
        untracked = index_status == "?" and worktree_status == "?"
        if untracked:
            raise B1RunnerError("mres_worktree_dirty", "untracked files are present")
        if staged and tracked:
            raise B1RunnerError(
                "mres_worktree_dirty",
                "staged and unstaged tracked changes are present",
            )
        if staged:
            raise B1RunnerError("mres_worktree_dirty", "staged changes are present")
        if tracked:
            raise B1RunnerError("mres_worktree_dirty", "tracked changes are present")
        raise B1RunnerError("mres_worktree_dirty", "the worktree is not clean")


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
    """Require the reviewed untracked fingerprint. Refuse tracked or staged changes.

    An empty porcelain result is refused. The required RNAGenesis assets are
    intentionally untracked, so their paths must be present exactly. Missing,
    additional, and renamed untracked paths are refused.
    """
    observed = []
    for line in _porcelain_lines(porcelain):
        index_status, worktree_status, path = _split_porcelain(line)
        if index_status == "?" and worktree_status == "?":
            observed.append(_normalise_untracked_path(path))
            continue
        if index_status not in (" ", "?"):
            raise B1RunnerError(
                "rnagenesis_worktree_dirty",
                "staged changes are present",
            )
        raise B1RunnerError(
            "rnagenesis_worktree_dirty",
            "tracked changes are present",
        )
    if sorted(observed) != sorted(KNOWN_RNAGENESIS_UNTRACKED):
        raise B1RunnerError(
            "rnagenesis_untracked_refused",
            "untracked path is not the known RNAGenesis asset fingerprint",
        )


def _git_line(git, repo, args):
    return git(repo, list(args)).strip()


def assert_repository_pins(snapshot, git):
    """Separate the implementation commit from the runtime authorization commit.

    executing_implementation_commit names the commit that contains the accepted
    runner and that names the evidence directory. Runtime HEAD may be that
    commit or a later descendant that carries the active authorization. The
    runner file at runtime must still be byte-identical to the implementation
    blob. Local origin/main must already equal runtime HEAD. This function
    only reads git state.
    """
    implementation_commit = snapshot["executing_implementation_commit"]
    mres_head = _git_line(git, MRES_ROOT, ["rev-parse", "HEAD"])
    mres_branch = _git_line(git, MRES_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"])
    mres_porcelain = git(MRES_ROOT, ["status", "--porcelain=v1"])
    origin_main = _git_line(git, MRES_ROOT, ["rev-parse", "origin/main"])
    if mres_branch != "main":
        raise B1RunnerError("mres_branch_not_main", "MRes repository is not on main")
    if not _is_sha40(mres_head):
        raise B1RunnerError(
            "mres_head_invalid",
            "runtime MRes HEAD is not a 40-character lowercase SHA-1",
        )
    _assert_mres_worktree_clean(mres_porcelain)
    if origin_main != mres_head:
        raise B1RunnerError(
            "mres_origin_main_mismatch",
            "local origin/main does not equal runtime HEAD",
        )
    merge_base = _git_line(
        git,
        MRES_ROOT,
        ["merge-base", implementation_commit, "HEAD"],
    )
    if merge_base != implementation_commit:
        raise B1RunnerError(
            "mres_implementation_not_ancestor",
            "executing_implementation_commit is not an ancestor of runtime HEAD",
        )
    implementation_blob = _git_line(
        git,
        MRES_ROOT,
        ["rev-parse", "{}:{}".format(implementation_commit, RUNNER_RELATIVE)],
    )
    worktree_blob = _git_line(
        git,
        MRES_ROOT,
        ["hash-object", "--", str(RUNNER_PATH)],
    )
    if implementation_blob == "" or implementation_blob != worktree_blob:
        raise B1RunnerError(
            "runner_bytes_mismatch",
            "scripts/b1_generic_runner.py is not byte-identical to the implementation commit",
        )
    rna_head = _git_line(git, RNAGENESIS_ROOT, ["rev-parse", "HEAD"])
    rna_branch = _git_line(git, RNAGENESIS_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"])
    rna_porcelain = git(RNAGENESIS_ROOT, ["status", "--porcelain=v1"])
    if rna_branch != RNAGENESIS_BRANCH:
        raise B1RunnerError(
            "rnagenesis_branch_mismatch",
            "RNAGenesis branch is not mres-d1-diffusion-finetune",
        )
    if rna_head != RNAGENESIS_HEAD:
        raise B1RunnerError(
            "rnagenesis_head_mismatch",
            "RNAGenesis HEAD is not the pinned commit",
        )
    _assert_rnagenesis_worktree(rna_porcelain)
    return {
        "mres": {
            "root": str(MRES_ROOT),
            "branch": mres_branch,
            "head": mres_head,
            "runtime_head": mres_head,
            "authorization_commit": mres_head,
            "implementation_commit": implementation_commit,
            "origin_main": origin_main,
            "runner_worktree_blob": worktree_blob,
            "runner_implementation_blob": implementation_blob,
            "runner_bytes_match_implementation": True,
            "dirty_tree_porcelain": mres_porcelain,
            "runner_modified_repository": False,
        },
        "rnagenesis": {
            "root": str(RNAGENESIS_ROOT),
            "branch": rna_branch,
            "head": rna_head,
            "dirty_tree_porcelain": rna_porcelain,
            "dirty_tree_description": (
                "Read-only git status --porcelain=v1. "
                "The untracked path set must equal the reviewed RNAGenesis asset fingerprint. "
                "An empty porcelain result is refused because those assets are intentionally untracked. "
                "Tracked and staged state must be clean. "
                "The runner does not fetch, checkout, clean, restore, stage, "
                "or otherwise modify RNAGenesis."
            ),
            "runner_modified_repository": False,
        },
    }


def assert_cleaner_allowed(path):
    """Reject the prohibited cleaner with no authorisation override."""
    text = os.path.normpath(str(path))
    prohibited = os.path.normpath(str(PROHIBITED_CLEANER))
    base = os.path.basename(text)
    if text == prohibited or base == "clean_generated_sequences.py":
        raise B1RunnerError(
            "prohibited_cleaner",
            "clean_generated_sequences.py is rejected",
        )


def assert_encdec_selection(relative):
    if "checkpoint-15000" in relative or "checkpoint-30000" in relative:
        raise B1RunnerError(
            "encdec_substitute_rejected",
            "adjacent EncDec subcheckpoint weights are rejected",
        )
    if relative != ENCDEC_RELATIVE:
        raise B1RunnerError(
            "encdec_selection_rejected",
            "EncDec selection is not configs/rnagenesis/autoencoder",
        )


def assert_diffusion_selection(relative):
    normalised = relative.replace("\\", "/").rstrip("/")
    prohibited = "checkpoints/Aptamer/diffusion"
    if normalised == prohibited or normalised.endswith("/" + prohibited):
        raise B1RunnerError(
            "prohibited_diffusion",
            "checkpoints/Aptamer/diffusion is prohibited",
        )
    absolute = os.path.normpath(str(RNAGENESIS_ROOT / normalised))
    if absolute == os.path.normpath(str(PROHIBITED_DIFFUSION)):
        raise B1RunnerError(
            "prohibited_diffusion",
            "checkpoints/Aptamer/diffusion is prohibited",
        )
    if normalised != DIFFUSION_RELATIVE:
        raise B1RunnerError(
            "diffusion_selection_rejected",
            "diffusion selection is not configs/rnagenesis/diffusion",
        )


def verify_asset(asset, lstat, sha256_file):
    if "checkpoint-15000" in asset.relative or "checkpoint-30000" in asset.relative:
        raise B1RunnerError(
            "encdec_substitute_rejected",
            "adjacent EncDec subcheckpoint weights are rejected",
        )
    path = asset.absolute_path()
    try:
        observed = lstat(path)
    except FileNotFoundError:
        raise B1RunnerError("pinned_file_missing", asset.relative)
    if stat.S_ISLNK(observed.st_mode):
        raise B1RunnerError("pinned_file_symlink", asset.relative)
    if not stat.S_ISREG(observed.st_mode):
        raise B1RunnerError("pinned_file_not_regular", asset.relative)
    if asset.size is not None and observed.st_size != asset.size:
        raise B1RunnerError("pinned_file_size_mismatch", asset.relative)
    digest = sha256_file(path)
    if (
        asset.role == "encdec_weights"
        and digest in PROHIBITED_SUBSTITUTE_SHA256
    ):
        substitute = PROHIBITED_SUBSTITUTE_SHA256[digest]
        raise B1RunnerError(
            "encdec_substitute_rejected",
            "EncDec weight matches prohibited {}".format(substitute),
        )
    if digest != asset.sha256:
        raise B1RunnerError("pinned_file_hash_mismatch", asset.relative)
    return {
        "role": asset.role,
        "path": str(path),
        "relative_path": asset.relative,
        "size": observed.st_size,
        "sha256": digest,
        "large": asset.large,
    }


def verify_pinned_assets(lstat, sha256_file, large):
    results = []
    for asset in PINNED_FILES:
        if asset.large is not large:
            continue
        results.append(verify_asset(asset, lstat, sha256_file))
    return results


def _argv_value(argv, flag):
    try:
        index = argv.index(flag)
    except ValueError:
        raise B1RunnerError("argv_incomplete", "{} is missing".format(flag))
    if index + 1 >= len(argv):
        raise B1RunnerError("argv_incomplete", "{} is missing a value".format(flag))
    return argv[index + 1]


def assert_argv_prohibitions(argv):
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
        raise B1RunnerError("argv_type", "argv must be a list of strings")
    for option in PROHIBITED_ARGV_OPTIONS:
        if option in argv:
            raise B1RunnerError("prohibited_generation_option", option)
    for element in argv:
        normalised = element.replace("\\", "/")
        for marker in PROHIBITED_PATH_MARKERS:
            if marker in normalised:
                raise B1RunnerError("prohibited_generation_path", marker)
        for component in normalised.split("/"):
            if component in PROHIBITED_PATH_COMPONENTS:
                raise B1RunnerError("prohibited_generation_path", component)
    if "--do_sample" not in argv:
        raise B1RunnerError("sampling_not_enabled", "sampling must be enabled")
    if "--guidance" in argv:
        raise B1RunnerError("guidance_not_disabled", "--guidance was passed")


def invocation_mid_folder(invocation):
    return "invocation_{:02d}".format(invocation["invocation_index"])


def invocation_remark(invocation):
    return "_phaseA_i{:02d}_seed{}_cap{}".format(
        invocation["invocation_index"],
        invocation["seed"],
        invocation["max_seq_len"],
    )


def predicted_generation_filename(remark):
    return "seqs_wo_guidance_top_p=0.95_2_16{}.txt".format(remark)


def predicted_generation_path(evidence_dir, invocation):
    remark = invocation_remark(invocation)
    return (
        Path(evidence_dir)
        / "rnagenesis_generation_output"
        / invocation_mid_folder(invocation)
        / predicted_generation_filename(remark)
    )


def build_generation_argv(invocation, evidence_dir, guidance_enabled):
    if guidance_enabled is not False:
        raise B1RunnerError(
            "guidance_not_disabled",
            "guidance must be disabled",
        )
    assert_encdec_selection(ENCDEC_RELATIVE)
    assert_diffusion_selection(DIFFUSION_RELATIVE)
    assert_cleaner_allowed(APPROVED_CLEANER)
    remark = invocation_remark(invocation)
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
        str(BATCH_SIZE),
        "--batch_num",
        str(BATCH_NUM),
        "--seed",
        str(invocation["seed"]),
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
        remark,
        "--device",
        "cuda:0",
        "--superfolder",
        str(Path(evidence_dir) / "rnagenesis_generation_output"),
        "--mid_folder",
        invocation_mid_folder(invocation),
    ]
    for flag, value in INERT_REQUIRED_ARGUMENTS:
        argv.extend([flag, value])
    assert_argv_prohibitions(argv)
    if _argv_value(argv, "--enc_dec_file") != ENCDEC_RELATIVE:
        raise B1RunnerError("encdec_selection_rejected", "EncDec argv drifted")
    if _argv_value(argv, "--dm_file") != DIFFUSION_RELATIVE:
        raise B1RunnerError("diffusion_selection_rejected", "diffusion argv drifted")
    if _argv_value(argv, "--device") != "cuda:0":
        raise B1RunnerError("cpu_fallback_prohibited", "device is not cuda:0")
    if argv.count("--max_seq_len") != 1:
        raise B1RunnerError(
            "phase_a_plan_invalid",
            "an invocation must carry exactly one max_seq_len",
        )
    return argv


def _path_within(path, root):
    try:
        return os.path.commonpath(
            [os.path.normpath(path), os.path.normpath(root)]
        ) == os.path.normpath(root)
    except ValueError:
        return False


def runtime_isolation_paths(evidence_dir):
    """Per-run bytecode and library cache locations under the evidence directory.

    generation.py assigns XDG_CACHE_HOME to the relative path ".cache" before
    importing huggingface, diffusers, or torch. Those libraries prefer
    HF_HOME and TORCH_HOME when those variables are already set, so the
    child points them at this directory instead of RNAGenesis/.cache.
    """
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
    }


def assert_runtime_isolation(evidence_dir, realpath=None):
    if realpath is None:
        realpath = os.path.realpath
    evidence = os.path.abspath(os.path.normpath(str(evidence_dir)))
    if not evidence.startswith("/"):
        raise B1RunnerError(
            "runtime_cache_not_isolated",
            "evidence directory is not absolute",
        )
    resolved_evidence = realpath(evidence)
    resolved_rna = realpath(str(RNAGENESIS_ROOT))
    if resolved_evidence != evidence:
        raise B1RunnerError(
            "runtime_cache_not_isolated",
            "evidence directory path is not stable",
        )
    if _path_within(resolved_evidence, resolved_rna):
        raise B1RunnerError(
            "runtime_cache_not_isolated",
            "evidence directory resolves inside RNAGenesis",
        )
    rna_root = os.path.normpath(str(RNAGENESIS_ROOT))
    rna_cache = os.path.normpath(os.path.join(rna_root, ".cache"))
    paths = runtime_isolation_paths(evidence)
    for path in paths.values():
        if not os.path.isabs(path) or _path_within(os.path.normpath(path), rna_root):
            raise B1RunnerError(
                "runtime_cache_not_isolated",
                "runtime cache path is inside RNAGenesis",
            )
        resolved = realpath(path)
        if not _path_within(resolved, resolved_evidence):
            raise B1RunnerError(
                "runtime_cache_not_isolated",
                "runtime cache escaped the evidence directory",
            )
        if (
            _path_within(resolved, resolved_rna)
            or _path_within(resolved, rna_cache)
            or os.path.normpath(resolved) == rna_cache
        ):
            raise B1RunnerError(
                "runtime_cache_not_isolated",
                "runtime cache resolves to an RNAGenesis cache",
            )
    return paths


def build_child_environment(parent, evidence_dir, realpath=None):
    assert_cuda_environment(parent)
    original_items = list(parent.items())
    child = dict(parent)
    child.update(OFFLINE_CONTROLS)
    child["PYTHONDONTWRITEBYTECODE"] = "1"
    child.update(assert_runtime_isolation(evidence_dir, realpath))
    if list(parent.items()) != original_items:
        raise B1RunnerError(
            "parent_environment_mutated",
            "parent environment was modified",
        )
    assert_cuda_environment(child)
    if child.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise B1RunnerError(
            "runtime_cache_not_isolated",
            "child bytecode writing was not disabled",
        )
    return child


def build_subprocess_invocation(invocation, evidence_dir, parent_env, realpath=None):
    argv = build_generation_argv(
        invocation,
        evidence_dir,
        guidance_enabled=False,
    )
    return {
        "argv": argv,
        "cwd": GENERATION_CWD,
        "env": build_child_environment(parent_env, evidence_dir, realpath),
        "shell": False,
    }


def physical_gpu_query_argv():
    return [
        "nvidia-smi",
        "--query-gpu=index,uuid,pci.bus_id,name,memory.total,compute_mode",
        "--format=csv,noheader,nounits",
        "-i",
        str(PHYSICAL_GPU),
    ]


def cuda_probe_argv():
    if PINNED_PYTHON != "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python":
        raise B1RunnerError(
            "python_interpreter_rejected",
            "generation interpreter is not the pinned rnagenesis-h200 Python",
        )
    return [PINNED_PYTHON, "-c", CUDA_PROBE_SOURCE]


def build_cuda_probe_command(child_env):
    """Probe command. Uses the same interpreter and child environment as generation."""
    assert_cuda_environment(child_env)
    return {
        "argv": cuda_probe_argv(),
        "cwd": GENERATION_CWD,
        "env": child_env,
        "shell": False,
    }


def parse_gpu_identity(text):
    lines = [line for line in text.splitlines() if line.strip() != ""]
    if len(lines) != 1:
        raise B1RunnerError(
            "cpu_fallback_prohibited",
            "physical GPU {} query did not return one device".format(PHYSICAL_GPU),
        )
    parts = [part.strip() for part in lines[0].split(",")]
    if len(parts) != 6:
        raise B1RunnerError(
            "cpu_fallback_prohibited",
            "physical GPU {} query was incomplete".format(PHYSICAL_GPU),
        )
    index_text, uuid, pci_bus_id, name, memory, compute_mode = parts
    if index_text != str(PHYSICAL_GPU) or uuid == "" or uuid.upper() == "N/A":
        raise B1RunnerError(
            "cpu_fallback_prohibited",
            "physical GPU {} did not report a usable identity".format(PHYSICAL_GPU),
        )
    if (
        pci_bus_id == ""
        or pci_bus_id.upper() == "N/A"
        or name == ""
        or memory == ""
        or compute_mode == ""
    ):
        raise B1RunnerError(
            "cpu_fallback_prohibited",
            "physical GPU {} identity was incomplete".format(PHYSICAL_GPU),
        )
    return {
        "index": PHYSICAL_GPU,
        "uuid": uuid,
        "pci_bus_id": pci_bus_id,
        "name": name,
        "memory": memory,
        "compute_mode": compute_mode,
        "physical_gpu": PHYSICAL_GPU,
        "cpu_fallback": False,
    }


def parse_cuda_probe_json(text):
    if not isinstance(text, str) or text.strip() == "":
        raise B1RunnerError(
            "cuda_probe_malformed",
            "CUDA probe did not return JSON",
        )
    try:
        payload = json.loads(text)
    except Exception:
        raise B1RunnerError(
            "cuda_probe_malformed",
            "CUDA probe did not return JSON",
        )
    if not isinstance(payload, dict):
        raise B1RunnerError(
            "cuda_probe_malformed",
            "CUDA probe did not return a JSON object",
        )
    missing = [key for key in CUDA_PROBE_KEYS if key not in payload]
    if missing:
        raise B1RunnerError(
            "cuda_probe_malformed",
            "CUDA probe JSON is incomplete",
        )
    return payload


def _resolved_python(path, resolve_python):
    if not isinstance(path, str) or path.strip() == "":
        raise B1RunnerError(
            "cuda_probe_mismatch",
            "CUDA probe interpreter did not match the pinned Python",
        )
    return resolve_python(path)


def validate_cuda_probe(payload, physical_identity, resolve_python=None):
    """Accept a probe only after logical cuda:0 has run a synchronized tensor.

    nvidia-smi identity and CUDA_VISIBLE_DEVICES do not set
    logical_device_confirmed.
    """
    if resolve_python is None:
        resolve_python = os.path.realpath
    if type(payload.get("cuda_available")) is not bool:
        raise B1RunnerError(
            "cuda_probe_malformed",
            "CUDA probe availability was not a boolean",
        )
    if payload["cuda_available"] is not True:
        raise B1RunnerError("cuda_unavailable", "Torch CUDA is not available")
    if type(payload.get("device_count")) is not int:
        raise B1RunnerError(
            "cuda_probe_malformed",
            "CUDA probe device count was not an integer",
        )
    if payload["device_count"] != 1:
        raise B1RunnerError(
            "cuda_device_count",
            "expected exactly one visible CUDA device",
        )
    if payload.get("allocation_ok") is not True or payload.get("logical_device_index") != 0:
        raise B1RunnerError(
            "cuda_allocation_failed",
            "logical CUDA device 0 could not allocate a tensor",
        )
    if (
        payload.get("logical_device") != "cuda:0"
        or payload.get("logical_device_confirmed") is not True
    ):
        raise B1RunnerError(
            "cuda_probe_mismatch",
            "logical CUDA device 0 was not confirmed",
        )
    if payload.get("cuda_visible_devices") != str(PHYSICAL_GPU):
        raise B1RunnerError(
            "cuda_probe_mismatch",
            "CUDA probe did not observe CUDA_VISIBLE_DEVICES={}".format(PHYSICAL_GPU),
        )
    if payload.get("cuda_device_order") != CUDA_DEVICE_ORDER:
        raise B1RunnerError(
            "cuda_probe_mismatch",
            "CUDA probe did not observe CUDA_DEVICE_ORDER={}".format(CUDA_DEVICE_ORDER),
        )
    if (
        type(physical_identity.get("index")) is not int
        or physical_identity.get("index") != PHYSICAL_GPU
        or physical_identity.get("physical_gpu") != PHYSICAL_GPU
        or physical_identity.get("cpu_fallback") is not False
    ):
        raise B1RunnerError(
            "cpu_fallback_prohibited",
            "physical GPU {} identity was not confirmed".format(PHYSICAL_GPU),
        )
    pci_bus_id = physical_identity.get("pci_bus_id")
    uuid = physical_identity.get("uuid")
    if (
        not isinstance(pci_bus_id, str)
        or pci_bus_id.strip() == ""
        or pci_bus_id.upper() == "N/A"
        or not isinstance(uuid, str)
        or uuid.strip() == ""
        or uuid.upper() == "N/A"
    ):
        raise B1RunnerError(
            "cpu_fallback_prohibited",
            "physical GPU {} identity was incomplete".format(PHYSICAL_GPU),
        )
    device_name = payload.get("device_name")
    if not isinstance(device_name, str) or device_name.strip() == "":
        raise B1RunnerError("cuda_probe_malformed", "CUDA probe device name was missing")
    if device_name != physical_identity["name"]:
        raise B1RunnerError(
            "cuda_probe_mismatch",
            "Torch device name did not match physical GPU {}".format(PHYSICAL_GPU),
        )
    pinned_resolved = _resolved_python(PINNED_PYTHON, resolve_python)
    observed_resolved = _resolved_python(payload.get("python_executable"), resolve_python)
    if observed_resolved != pinned_resolved:
        raise B1RunnerError(
            "cuda_probe_mismatch",
            "CUDA probe interpreter did not match the pinned Python",
        )
    python_version = payload.get("python_version")
    torch_version = payload.get("torch_version")
    if not isinstance(python_version, str) or python_version.strip() == "":
        raise B1RunnerError("cuda_probe_malformed", "Python version was missing")
    if not isinstance(torch_version, str) or torch_version.strip() == "":
        raise B1RunnerError("cuda_probe_malformed", "Torch version was missing")
    packages = payload.get("packages")
    if not isinstance(packages, dict):
        raise B1RunnerError("cuda_probe_malformed", "package versions were missing")
    if set(packages) != set(GENERATION_CRITICAL_DISTRIBUTIONS):
        raise B1RunnerError("cuda_probe_malformed", "package versions were missing")
    recorded = {}
    for name in GENERATION_CRITICAL_DISTRIBUTIONS:
        version = packages.get(name)
        if not isinstance(version, str) or version.strip() == "":
            raise B1RunnerError("cuda_probe_malformed", "package versions were missing")
        recorded[name] = version
    if recorded["torch"] != torch_version:
        raise B1RunnerError("cuda_probe_malformed", "package versions were missing")
    return {
        "index": PHYSICAL_GPU,
        "physical_gpu": PHYSICAL_GPU,
        "uuid": uuid,
        "pci_bus_id": pci_bus_id,
        "logical_device": "cuda:0",
        "logical_device_index": 0,
        "logical_device_confirmed": True,
        "device_count": 1,
        "device_name": device_name,
        "python_executable": PINNED_PYTHON,
        "python_resolved_path": pinned_resolved,
        "python_version": python_version,
        "torch_version": torch_version,
        "cuda_version": payload.get("cuda_version"),
        "packages": recorded,
        "cpu_fallback": False,
        "cuda_visible_devices": str(PHYSICAL_GPU),
        "cuda_device_order": CUDA_DEVICE_ORDER,
    }


def preflight_gpu(child_env, query_text, probe_text, resolve_python=None):
    """Query physical GPU 1, then confirm logical cuda:0 in the child probe.

    query_text and probe_text run only after the child environment is already
    CUDA_VISIBLE_DEVICES=1 and CUDA_DEVICE_ORDER=PCI_BUS_ID. Neither callback
    is Torch. logical_device_confirmed is taken only from a probe that
    allocated and synchronized a tensor on cuda:0.
    """
    assert_cuda_environment(child_env)
    identity = parse_gpu_identity(query_text())
    if identity.get("logical_device_confirmed") is True:
        raise B1RunnerError(
            "cuda_probe_mismatch",
            "physical GPU query cannot confirm the logical CUDA device",
        )
    payload = parse_cuda_probe_json(probe_text())
    confirmed = validate_cuda_probe(payload, identity, resolve_python)
    identity.update(confirmed)
    return identity


def default_query_gpu_text():
    completed = subprocess.run(
        physical_gpu_query_argv(),
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or completed.stdout.strip() == "":
        raise B1RunnerError(
            "cpu_fallback_prohibited",
            "physical GPU {} query failed".format(PHYSICAL_GPU),
        )
    return completed.stdout


def default_cuda_probe(child_env):
    """Run the Torch probe in the pinned interpreter. Do not import Torch here."""
    command = build_cuda_probe_command(child_env)
    if command["shell"] is not False:
        raise B1RunnerError("shell_prohibited", "subprocess shell must stay false")
    if command["argv"][0] != PINNED_PYTHON:
        raise B1RunnerError(
            "python_interpreter_rejected",
            "generation interpreter is not the pinned rnagenesis-h200 Python",
        )
    completed = subprocess.run(
        command["argv"],
        cwd=command["cwd"],
        env=command["env"],
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or completed.stdout.strip() == "":
        raise B1RunnerError("cuda_probe_failed", "CUDA probe subprocess failed")
    return completed.stdout


def default_gpu_preflight(child_env, gates_passed=False):
    if gates_passed is not True:
        raise B1RunnerError(
            "gpu_preflight_before_authorisation",
            "GPU preflight is refused before document and authorisation gates",
        )
    return preflight_gpu(
        child_env,
        default_query_gpu_text,
        lambda: default_cuda_probe(child_env),
    )


def production_gpu_preflight(child_env):
    return default_gpu_preflight(child_env, gates_passed=True)


def termination_observation(removed_prefix, removed_suffix):
    """EOS is recorded only from decoded leading or trailing boundary markers.

    Output length is not evidence that max_seq_len caused termination.
    """
    boundary = "{}{}".format(removed_prefix, removed_suffix)
    if "2" in boundary:
        return EOS_OBSERVED
    return TERMINATION_NOT_OBSERVABLE


def adapt_audited_line(raw, audited, invocation, attempt_within_candidate):
    prefix = audited["removed_prefix"]
    suffix = audited["removed_suffix"]
    accepted = audited["accepted"] is True
    if accepted:
        rejection_reason = None
    else:
        rejection_reason = audited["reason"]
    requested = invocation["requested_biological_length"]
    record = {
        "invocation_index": invocation["invocation_index"],
        "attempt_index": (
            invocation["invocation_index"] * ATTEMPTS_PER_CAP + attempt_within_candidate
        ),
        "attempt_within_candidate": attempt_within_candidate,
        "pairing_group": requested,
        "requested_biological_length": requested,
        "max_seq_len": invocation["max_seq_len"],
        "cap_offset": invocation["cap_offset"],
        "seed": invocation["seed"],
        "raw_decoded_text": raw,
        "raw_length": len(raw),
        "cleaned_sequence": audited["cleaned"],
        "cleaned_length": len(audited["cleaned"]),
        "leading_boundary_marker_run": prefix,
        "trailing_boundary_marker_run": suffix,
        "validity": accepted,
        "rejection_reason": rejection_reason,
        "termination_observation": termination_observation(prefix, suffix),
    }
    if tuple(record) != ATTEMPT_KEYS:
        raise B1RunnerError("attempt_record_invalid", "attempt fields drifted")
    return record


def audit_invocation_output(text, split_raw_records, audit_line, invocation):
    lines = split_raw_records(text)
    if len(lines) != ATTEMPTS_PER_CAP:
        raise B1RunnerError(
            "invocation_output_line_count",
            "expected 16 output lines and observed {}".format(len(lines)),
        )
    records = []
    for attempt_within_candidate, raw in enumerate(lines):
        audited = audit_line(attempt_within_candidate + 1, raw)
        if audited.get("raw") != raw:
            raise B1RunnerError(
                "audit_raw_mismatch",
                "cleaner raw field does not match the decoded line",
            )
        records.append(
            adapt_audited_line(raw, audited, invocation, attempt_within_candidate)
        )
    return records


def _exact_hit_rate(exact_hits, valid_outputs):
    if valid_outputs == 0:
        return 0.0
    return exact_hits / valid_outputs


def _numeric_distribution(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [
        {"value": value, "count": counts[value]}
        for value in sorted(counts)
    ]


def _text_distribution(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [
        {"value": value, "count": counts[value]}
        for value in sorted(counts)
    ]


def _empty_count_bucket():
    return {
        "raw_attempts": 0,
        "valid_outputs": 0,
        "invalid_outputs": 0,
        "exact_hits": 0,
        "cleaned_lengths": [],
        "leading_runs": [],
        "trailing_runs": [],
        "eos_marker_observed_count": 0,
    }


def sequence_only_diagnostics(attempts):
    """Length diagnostics from generated attempts only.

    Cap-level rows characterize each (requested length, max_seq_len) candidate.
    They do not select a cap and they do not infer the Phase B mapping. The
    0.90 and 0.50 figures are provisional diagnostics. They are not B1
    eligibility gates, and this function does not read a corpus.
    """
    by_length = {}
    by_candidate = {}
    valid = 0
    invalid = 0
    exact = 0
    for attempt in attempts:
        length = attempt["requested_biological_length"]
        bucket = by_length.setdefault(length, _empty_count_bucket())
        bucket["raw_attempts"] += 1
        is_valid = attempt["validity"] is True
        if is_valid:
            valid += 1
            bucket["valid_outputs"] += 1
            if attempt["cleaned_length"] == length:
                exact += 1
                bucket["exact_hits"] += 1
        else:
            invalid += 1
            bucket["invalid_outputs"] += 1
        cap = attempt.get("max_seq_len")
        if cap is None:
            continue
        candidate = by_candidate.setdefault((length, cap), _empty_count_bucket())
        candidate["raw_attempts"] += 1
        candidate["cleaned_lengths"].append(attempt.get("cleaned_length"))
        candidate["leading_runs"].append(attempt.get("leading_boundary_marker_run", ""))
        candidate["trailing_runs"].append(attempt.get("trailing_boundary_marker_run", ""))
        if attempt.get("termination_observation") == EOS_OBSERVED:
            candidate["eos_marker_observed_count"] += 1
        if is_valid:
            candidate["valid_outputs"] += 1
            if attempt.get("cleaned_length") == length:
                candidate["exact_hits"] += 1
        else:
            candidate["invalid_outputs"] += 1
    per_length = []
    for length in sorted(by_length):
        bucket = by_length[length]
        per_length.append(
            {
                "requested_biological_length": length,
                "raw_attempts": bucket["raw_attempts"],
                "valid_outputs": bucket["valid_outputs"],
                "invalid_outputs": bucket["invalid_outputs"],
                "exact_hits": bucket["exact_hits"],
                "exact_hit_rate": _exact_hit_rate(
                    bucket["exact_hits"],
                    bucket["valid_outputs"],
                ),
            }
        )
    per_candidate = []
    for length, cap in sorted(by_candidate):
        bucket = by_candidate[(length, cap)]
        per_candidate.append(
            {
                "requested_biological_length": length,
                "max_seq_len": cap,
                "raw_attempts": bucket["raw_attempts"],
                "valid_outputs": bucket["valid_outputs"],
                "invalid_outputs": bucket["invalid_outputs"],
                "exact_hits": bucket["exact_hits"],
                "exact_hit_rate": _exact_hit_rate(
                    bucket["exact_hits"],
                    bucket["valid_outputs"],
                ),
                "cleaned_length_distribution": _numeric_distribution(
                    bucket["cleaned_lengths"]
                ),
                "leading_boundary_distribution": _text_distribution(bucket["leading_runs"]),
                "trailing_boundary_distribution": _text_distribution(
                    bucket["trailing_runs"]
                ),
                "eos_marker_observed_count": bucket["eos_marker_observed_count"],
            }
        )
    return {
        "role": "characterization_diagnostic_not_an_eligibility_gate",
        "cap_selection": "not_made",
        "phase_b_mapping": "not_inferred",
        "raw_attempts": len(attempts),
        "valid_outputs": valid,
        "invalid_outputs": invalid,
        "exact_hits": exact,
        "overall_exact_hit_rate": _exact_hit_rate(exact, valid),
        "per_requested_length": per_length,
        "per_candidate": per_candidate,
        "provisional_thresholds": {
            "overall_exact_hit_threshold": "0.90",
            "per_length_exact_hit_threshold": "0.50",
            "applied_as_b1_eligibility_gate": False,
        },
        "eligibility_decision": "not_made",
        "b1_eligibility": "not_declared",
        "corpus_dependent_guardrails": "not_evaluated",
        "exact_train_match_rate": "not_evaluated",
    }


def canonical_json_bytes(document):
    text = json.dumps(
        document,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
    )
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def project_attempt(record, keys):
    if tuple(record) != ATTEMPT_KEYS:
        raise B1RunnerError("attempt_record_invalid", "attempt fields drifted")
    projected = {}
    for key in keys:
        if key not in record:
            raise B1RunnerError("attempt_record_invalid", "attempt fields drifted")
        projected[key] = record[key]
    return projected


def serialize_jsonl(records, keys=None):
    selected = ATTEMPT_KEYS if keys is None else keys
    lines = []
    for record in records:
        projected = project_attempt(record, selected)
        lines.append(
            json.dumps(
                projected,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
        )
    if not lines:
        return b""
    return ("\n".join(lines) + "\n").encode("utf-8")


def _assert_attempt_matches_plan(attempt, invocation, position):
    if attempt["attempt_within_candidate"] != position:
        raise B1RunnerError(
            "attempt_plan_mismatch",
            "attempt_within_candidate does not match the invocation plan",
        )
    expected_index = invocation["invocation_index"] * ATTEMPTS_PER_CAP + position
    if attempt["attempt_index"] != expected_index:
        raise B1RunnerError(
            "attempt_plan_mismatch",
            "attempt_index does not match the invocation plan",
        )
    requested = invocation["requested_biological_length"]
    checks = (
        ("invocation_index", invocation["invocation_index"]),
        ("pairing_group", requested),
        ("requested_biological_length", requested),
        ("max_seq_len", invocation["max_seq_len"]),
        ("cap_offset", invocation["cap_offset"]),
        ("seed", invocation["seed"]),
    )
    for key, expected in checks:
        if attempt[key] != expected:
            raise B1RunnerError(
                "attempt_plan_mismatch",
                "attempt {} does not match the invocation plan".format(key),
            )
    if attempt["pairing_group"] != attempt["requested_biological_length"]:
        raise B1RunnerError(
            "attempt_plan_mismatch",
            "pairing_group is not the requested biological length",
        )


def _assert_complete_attempts(attempts, plan):
    if len(attempts) != TOTAL_ATTEMPTS:
        raise B1RunnerError(
            "success_manifest_refused",
            "incomplete attempt ledger cannot be a success manifest",
        )
    if not isinstance(plan, list) or len(plan) != INVOCATION_COUNT:
        raise B1RunnerError(
            "success_manifest_refused",
            "the frozen invocation plan is unavailable",
        )
    grouped = {}
    for attempt in attempts:
        if tuple(attempt) != ATTEMPT_KEYS:
            raise B1RunnerError("attempt_record_invalid", "attempt fields drifted")
        grouped.setdefault(attempt["invocation_index"], []).append(attempt)
    if set(grouped) != set(range(INVOCATION_COUNT)):
        raise B1RunnerError(
            "success_manifest_refused",
            "success requires 33 invocations",
        )
    seen = []
    plan_by_index = {}
    for invocation in plan:
        index = invocation["invocation_index"]
        if index in plan_by_index:
            raise B1RunnerError(
                "attempt_plan_mismatch",
                "the invocation plan repeats an index",
            )
        plan_by_index[index] = invocation
    if set(plan_by_index) != set(range(INVOCATION_COUNT)):
        raise B1RunnerError(
            "success_manifest_refused",
            "success requires 33 invocations",
        )
    for invocation_index in range(INVOCATION_COUNT):
        invocation = plan_by_index[invocation_index]
        group = grouped[invocation_index]
        if len(group) != ATTEMPTS_PER_CAP:
            raise B1RunnerError(
                "success_manifest_refused",
                "invocation {} does not contain 16 attempts".format(invocation_index),
            )
        ordered = sorted(group, key=lambda item: item["attempt_within_candidate"])
        for position, attempt in enumerate(ordered):
            _assert_attempt_matches_plan(attempt, invocation, position)
            seen.append(attempt["attempt_index"])
    if seen != list(range(TOTAL_ATTEMPTS)):
        raise B1RunnerError(
            "attempt_plan_mismatch",
            "attempt indexes are not the frozen 528-attempt plan",
        )


def file_content_record(path, data):
    if not isinstance(data, (bytes, bytearray)):
        raise B1RunnerError("evidence_hash_invalid", "hash input must be bytes")
    payload = bytes(data)
    return {
        "path": str(path),
        "byte_count": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _contains_key(value, key):
    if isinstance(value, dict):
        if key in value:
            return True
        return any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def manifest_hashes(context):
    """Hash evidence inputs. The manifest body is not an input to itself."""
    gpu = context.get("gpu") if isinstance(context.get("gpu"), dict) else {}
    stored = context.get("input_hashes") if isinstance(context.get("input_hashes"), dict) else {}
    packages = gpu.get("packages") if isinstance(gpu.get("packages"), dict) else {}
    hashes = {
        "configuration": stored.get("configuration"),
        "runner": stored.get("runner"),
        "python": {
            "executable": PINNED_PYTHON,
            "resolved_path": gpu.get("python_resolved_path"),
            "version": gpu.get("python_version"),
        },
        "packages": packages,
        "raw_outputs": list(context.get("raw_outputs") or []),
        "pinned_assets": list(context.get("pins") or []),
        "raw_ledger_sha256": context.get("raw_ledger_sha256"),
        "audited_ledger_sha256": context.get("audited_ledger_sha256"),
    }
    if _contains_key(hashes, "manifest_sha256"):
        raise B1RunnerError(
            "manifest_hash_recursive",
            "a manifest body must not contain its own hash",
        )
    return hashes


def manifest_progress(context):
    return {
        "completed_invocation_indexes": list(
            context.get("completed_invocation_indexes") or []
        ),
        "attempt_count": context.get("attempt_count") or 0,
        "command_count": len(context.get("commands") or []),
        "raw_output_count": len(context.get("raw_outputs") or []),
    }


def _authorization_runtime_commit(provenance):
    if not isinstance(provenance, dict):
        return None
    mres = provenance.get("mres")
    if not isinstance(mres, dict):
        return None
    return mres.get("authorization_commit")


def _authorization_view(snapshot):
    if not isinstance(snapshot, dict):
        snapshot = {}
    keys = (
        "authorisation_id",
        "authorisation_active",
        "activation_status",
        "consumed",
        "authorises_b1_phase_a",
        "physical_gpu",
        "executing_implementation_commit",
        "condition",
        "phase",
        "evidence_directory",
    )
    return {key: snapshot.get(key) for key in keys}


def _child_environment_controls(evidence_dir):
    controls = {
        "CUDA_VISIBLE_DEVICES": str(PHYSICAL_GPU),
        "CUDA_DEVICE_ORDER": CUDA_DEVICE_ORDER,
        "physical_gpu": PHYSICAL_GPU,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "working_directory": GENERATION_CWD,
        "shell": False,
        "parent_environment_mutated": False,
    }
    if isinstance(evidence_dir, str) and evidence_dir != "":
        controls.update(runtime_isolation_paths(evidence_dir))
    return controls


def _raw_output_verification_record(value):
    if isinstance(value, dict) and value.get("passed") is True:
        return {
            "passed": True,
            "file_count": value.get("file_count"),
        }
    return {
        "passed": False,
        "file_count": 0 if not isinstance(value, dict) else value.get("file_count") or 0,
    }


def _identity_document(
    status,
    config,
    snapshot,
    provenance,
    pins,
    commands,
    gpu,
    plan,
    diagnostics,
    hashes,
    failure,
    timestamps,
    hostname,
    progress,
    evidence_dir,
    raw_output_verification,
):
    document = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "status": status,
        "experiment_id": None if not isinstance(config, dict) else config.get("experiment_id"),
        "condition_identifier": CONDITION_LABEL,
        "phase": "A",
        "purpose": "characterize_max_seq_len_versus_cleaned_length",
        "b1_eligibility": "not_declared",
        "eligibility_decision": "not_made",
        "m4_complete": False,
        "phase_b_executed": False,
        "development_pool_sampled": False,
        "length_matching_algorithm_declared": False,
        "authorization": _authorization_view(snapshot),
        "authorization_runtime_commit": _authorization_runtime_commit(provenance),
        "repository_provenance": provenance,
        "progress": progress,
        "pinned_inputs": pins,
        "commands": commands,
        "child_environment_controls": _child_environment_controls(evidence_dir),
        "final_raw_output_verification": _raw_output_verification_record(
            raw_output_verification
        ),
        "gpu_identity": gpu,
        "invocation_schedule": plan,
        "access_declaration": ACCESS_DECLARATION,
        "sequence_only_diagnostics": diagnostics,
        "corpus_dependent_guardrails": "not_evaluated",
        "hashes": hashes,
        "failure": failure,
        "timestamps": timestamps,
        "hostname": hostname,
    }
    if _contains_key(document, "manifest_sha256"):
        raise B1RunnerError(
            "manifest_hash_recursive",
            "a manifest body must not contain its own hash",
        )
    return document


def build_success_manifest(context):
    attempts = context["attempts"]
    _assert_complete_attempts(attempts, context.get("plan"))
    diagnostics = context["diagnostics"]
    if diagnostics["eligibility_decision"] != "not_made":
        raise B1RunnerError(
            "success_manifest_refused",
            "a length diagnostic cannot make an eligibility decision",
        )
    if diagnostics["b1_eligibility"] != "not_declared":
        raise B1RunnerError(
            "success_manifest_refused",
            "Phase A cannot declare B1 eligible",
        )
    if diagnostics.get("cap_selection") != "not_made":
        raise B1RunnerError(
            "success_manifest_refused",
            "Phase A cannot select a decoder cap",
        )
    if diagnostics.get("phase_b_mapping") != "not_inferred":
        raise B1RunnerError(
            "success_manifest_refused",
            "Phase A cannot infer the Phase B mapping",
        )
    if diagnostics["provisional_thresholds"]["applied_as_b1_eligibility_gate"] is not False:
        raise B1RunnerError(
            "success_manifest_refused",
            "provisional length thresholds are not eligibility gates",
        )
    if diagnostics["corpus_dependent_guardrails"] != "not_evaluated":
        raise B1RunnerError(
            "success_manifest_refused",
            "corpus-dependent guardrails were not left unevaluated",
        )
    progress = manifest_progress(context)
    if progress["completed_invocation_indexes"] != list(range(INVOCATION_COUNT)):
        raise B1RunnerError(
            "success_manifest_refused",
            "success requires 33 completed invocations",
        )
    if progress["attempt_count"] != TOTAL_ATTEMPTS or progress["raw_output_count"] != INVOCATION_COUNT:
        raise B1RunnerError(
            "success_manifest_refused",
            "success requires 528 attempts and 33 raw outputs",
        )
    raw_hash = context.get("raw_ledger_sha256")
    audited_hash = context.get("audited_ledger_sha256")
    if not raw_hash or not audited_hash:
        raise B1RunnerError(
            "success_manifest_refused",
            "ledger hashes are unavailable",
        )
    if raw_hash == audited_hash:
        raise B1RunnerError(
            "success_manifest_refused",
            "raw and audited ledger hashes must differ",
        )
    document = _identity_document(
        status="complete",
        config=context["config"],
        snapshot=context["snapshot"],
        provenance=context["provenance"],
        pins=context["pins"],
        commands=context["commands"],
        gpu=context["gpu"],
        plan=context["plan"],
        diagnostics=diagnostics,
        hashes=manifest_hashes(context),
        failure=None,
        timestamps=context["timestamps"],
        hostname=context["hostname"],
        progress=progress,
        evidence_dir=context.get("output_dir"),
        raw_output_verification=context.get("final_raw_output_verification"),
    )
    verification = document["final_raw_output_verification"]
    if verification["passed"] is not True or verification["file_count"] != INVOCATION_COUNT:
        raise B1RunnerError(
            "success_manifest_refused",
            "final raw-output verification did not pass",
        )
    if document["status"] != "complete":
        raise B1RunnerError("success_manifest_refused", "status drifted")
    return document


def build_failure_manifest(context, error):
    document = _identity_document(
        status="failed",
        config=context.get("config") or {},
        snapshot=context.get("snapshot") or {},
        provenance=context.get("provenance"),
        pins=context.get("pins"),
        commands=context.get("commands") or [],
        gpu=context.get("gpu"),
        plan=context.get("plan"),
        diagnostics=context.get("diagnostics"),
        hashes=manifest_hashes(context),
        failure={
            "code": error.code,
            "detail": error.detail,
            "scientific_run_completed": False,
            "completed_invocation_indexes": list(
                context.get("completed_invocation_indexes") or []
            ),
            "attempt_count": context.get("attempt_count") or 0,
            "raw_outputs": list(context.get("raw_outputs") or []),
        },
        timestamps=context.get("timestamps") or {},
        hostname=context.get("hostname"),
        progress=manifest_progress(context),
        evidence_dir=context.get("output_dir"),
        raw_output_verification=context.get("final_raw_output_verification"),
    )
    document["status"] = "failed"
    if document["status"] == "complete":
        raise B1RunnerError(
            "success_manifest_refused",
            "a failed run cannot produce a success manifest",
        )
    return document


def write_exclusive_bytes(path, data):
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        descriptor = os.open(str(path), flags, 0o644)
    except FileExistsError:
        raise
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written == 0:
                raise B1RunnerError("evidence_write_failed", "short write")
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


def default_sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def default_git(repo, args):
    argv = ["git", "-C", str(repo)]
    argv.extend(list(args))
    completed = subprocess.run(
        argv,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise B1RunnerError(
            "git_pin_failed",
            completed.stderr.strip() or "git pin command failed",
        )
    return completed.stdout


def default_subprocess_run(argv, cwd, env, shell=False):
    if shell is not False:
        raise B1RunnerError("shell_prohibited", "subprocess shell must stay false")
    if not isinstance(argv, list) or not argv:
        raise B1RunnerError("argv_type", "argv must be a list")
    if argv[0] != PINNED_PYTHON:
        raise B1RunnerError(
            "python_interpreter_rejected",
            "generation interpreter is not the pinned rnagenesis-h200 Python",
        )
    assert_argv_prohibitions(argv)
    if cwd != GENERATION_CWD:
        raise B1RunnerError(
            "generation_cwd_rejected",
            "generation working directory is not RNAGenesis",
        )
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        shell=False,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise B1RunnerError(
            "generation_process_failed",
            "generation.py exited {}".format(completed.returncode),
        )
    return completed


def verified_cleaner_source(read_bytes):
    """Hash the cleaner bytes that will be compiled. Do not use a bytecode loader."""
    assert_cleaner_allowed(APPROVED_CLEANER)
    try:
        data = read_bytes(APPROVED_CLEANER)
    except B1RunnerError:
        raise
    except OSError as exc:
        raise normalize_evidence_error(exc)
    if not isinstance(data, (bytes, bytearray)):
        raise B1RunnerError(
            "cleaner_import_failed",
            "approved cleaner source bytes are required",
        )
    payload = bytes(data)
    if hashlib.sha256(payload).hexdigest() != CLEANER_SHA256:
        raise B1RunnerError(
            "pinned_file_hash_mismatch",
            "scripts/audit_generation_output.py",
        )
    return payload


def load_cleaner_from_verified_source(source_bytes):
    """Compile already hash-verified source in a fresh module namespace."""
    assert_cleaner_allowed(APPROVED_CLEANER)
    if not isinstance(source_bytes, (bytes, bytearray)):
        raise B1RunnerError(
            "cleaner_import_failed",
            "approved cleaner source bytes are required",
        )
    payload = bytes(source_bytes)
    if hashlib.sha256(payload).hexdigest() != CLEANER_SHA256:
        raise B1RunnerError(
            "pinned_file_hash_mismatch",
            "scripts/audit_generation_output.py",
        )
    try:
        code = compile(
            payload,
            str(APPROVED_CLEANER),
            "exec",
            dont_inherit=True,
        )
    except (SyntaxError, ValueError):
        raise B1RunnerError(
            "cleaner_import_failed",
            "approved cleaner source could not be compiled",
        )
    module = types.ModuleType("b1_approved_audit_generation_output")
    module.__file__ = str(APPROVED_CLEANER)
    module.__package__ = ""
    try:
        exec(code, module.__dict__)
    except B1RunnerError:
        raise
    except Exception:
        raise B1RunnerError(
            "cleaner_import_failed",
            "approved cleaner source could not be executed",
        )
    if not hasattr(module, "audit_line") or not hasattr(module, "split_raw_records"):
        raise B1RunnerError(
            "cleaner_import_failed",
            "approved cleaner API is missing audit_line",
        )
    return module


def default_load_cleaner(source_bytes=None):
    if source_bytes is None:
        source_bytes = verified_cleaner_source(default_read_bytes)
    return load_cleaner_from_verified_source(source_bytes)


def default_clock():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_hostname():
    return os.uname().nodename


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
        load_cleaner=None,
        clock=None,
        hostname=None,
    ):
        self.read_bytes = read_bytes or default_read_bytes
        self.lstat = lstat or os.lstat
        self.realpath = realpath or os.path.realpath
        self.sha256_file = sha256_file or default_sha256_file
        self.environ = os.environ if environ is None else environ
        self.git = git or default_git
        self.gpu_preflight = gpu_preflight or production_gpu_preflight
        self.mkdir = mkdir or os.mkdir
        self.write_exclusive = write_exclusive or write_exclusive_bytes
        self.subprocess_run = subprocess_run or default_subprocess_run
        self.load_cleaner = load_cleaner or default_load_cleaner
        self.clock = clock or default_clock
        self.hostname = hostname or default_hostname


def production_dependencies():
    return RunnerDependencies()


def _public_command(command, invocation):
    return {
        "invocation_index": invocation["invocation_index"],
        "argv": list(command["argv"]),
        "cwd": command["cwd"],
        "shell": False,
    }


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


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
    """Map expected operational failures to safe B1RunnerError values."""
    if isinstance(exc, B1RunnerError):
        safe = _safe_detail(exc.detail)
        if safe == exc.detail:
            return exc
        return B1RunnerError(exc.code, safe)
    if isinstance(exc, UnicodeDecodeError):
        return B1RunnerError(
            "output_decode_failed",
            "generation output is not valid UTF-8",
        )
    if isinstance(exc, FileNotFoundError):
        return B1RunnerError(
            "output_file_missing",
            "expected generation output is missing",
        )
    if isinstance(exc, subprocess.SubprocessError):
        return B1RunnerError(
            "generation_process_failed",
            "generation subprocess failed",
        )
    if isinstance(exc, OSError):
        return B1RunnerError("filesystem_error", "filesystem operation failed")
    if isinstance(exc, Exception):
        return B1RunnerError(
            "unexpected_runtime_failure",
            "unexpected runtime failure",
        )
    return exc


def _path_exists(path):
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _write_evidence(deps, path, data):
    try:
        deps.write_exclusive(path, data)
    except B1RunnerError:
        raise
    except OSError as exc:
        raise normalize_evidence_error(exc)


def _raw_output_metadata(path, raw_bytes, records, invocation):
    return {
        "path": str(path),
        "byte_count": len(raw_bytes),
        "sha256": _sha256_bytes(raw_bytes),
        "line_count": len(records),
        "requested_biological_length": invocation["requested_biological_length"],
        "cap": invocation["max_seq_len"],
        "seed": invocation["seed"],
        "invocation_index": invocation["invocation_index"],
    }


def _ensure_live_context(context):
    context.setdefault("commands", [])
    context.setdefault("raw_outputs", [])
    context.setdefault("completed_invocation_indexes", [])
    context.setdefault("attempts", [])
    context["attempt_count"] = len(context["attempts"])
    return context


def _run_invocation(context, deps, cleaner, invocation, parent_before):
    command = build_subprocess_invocation(
        invocation,
        context["output_dir"],
        deps.environ,
        realpath=deps.realpath,
    )
    if command["shell"] is not False or command["cwd"] != GENERATION_CWD:
        raise B1RunnerError(
            "generation_cwd_rejected",
            "generation working directory is not RNAGenesis",
        )
    if command["argv"][0] != PINNED_PYTHON or command["argv"][0] != cuda_probe_argv()[0]:
        raise B1RunnerError(
            "python_interpreter_rejected",
            "generation interpreter is not the pinned rnagenesis-h200 Python",
        )
    context["commands"].append(_public_command(command, invocation))
    predicted = predicted_generation_path(context["output_dir"], invocation)
    try:
        deps.lstat(predicted)
    except FileNotFoundError:
        pass
    else:
        raise B1RunnerError(
            "output_path_exists",
            "invocation output already exists",
        )
    try:
        deps.subprocess_run(
            command["argv"],
            cwd=command["cwd"],
            env=command["env"],
            shell=False,
        )
    except B1RunnerError:
        raise
    except subprocess.SubprocessError as exc:
        raise normalize_evidence_error(exc)
    except OSError as exc:
        raise normalize_evidence_error(exc)
    try:
        raw_bytes = deps.read_bytes(predicted)
    except B1RunnerError:
        raise
    except (FileNotFoundError, OSError) as exc:
        raise normalize_evidence_error(exc)
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raise B1RunnerError("output_decode_failed", "generation output is not bytes")
    try:
        text = bytes(raw_bytes).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise normalize_evidence_error(exc)
    records = audit_invocation_output(
        text,
        cleaner.split_raw_records,
        cleaner.audit_line,
        invocation,
    )
    if list(deps.environ.items()) != parent_before:
        raise B1RunnerError(
            "parent_environment_mutated",
            "parent environment was modified",
        )
    context["raw_outputs"].append(
        _raw_output_metadata(predicted, bytes(raw_bytes), records, invocation)
    )
    context["attempts"].extend(records)
    context["completed_invocation_indexes"].append(invocation["invocation_index"])
    context["attempt_count"] = len(context["attempts"])


def verify_retained_raw_outputs(context, deps, cleaner):
    """Re-read every raw file and compare it with the post-invocation metadata."""
    outputs = list(context.get("raw_outputs") or [])
    if len(outputs) != INVOCATION_COUNT:
        raise B1RunnerError(
            "raw_output_verification_failed",
            "expected 33 raw outputs",
        )
    for item in outputs:
        path = item.get("path")
        try:
            observed = deps.lstat(path)
        except FileNotFoundError:
            raise B1RunnerError(
                "raw_output_verification_failed",
                "raw output is missing",
            )
        except OSError:
            raise B1RunnerError(
                "raw_output_verification_failed",
                "raw output could not be inspected",
            )
        if stat.S_ISLNK(observed.st_mode):
            raise B1RunnerError(
                "raw_output_verification_failed",
                "raw output is a symlink",
            )
        if not stat.S_ISREG(observed.st_mode):
            raise B1RunnerError(
                "raw_output_verification_failed",
                "raw output is not a regular file",
            )
        if observed.st_size != item.get("byte_count"):
            raise B1RunnerError(
                "raw_output_verification_failed",
                "raw output byte count changed",
            )
        try:
            data = deps.read_bytes(path)
        except B1RunnerError:
            raise
        except FileNotFoundError:
            raise B1RunnerError(
                "raw_output_verification_failed",
                "raw output is missing",
            )
        except OSError:
            raise B1RunnerError(
                "raw_output_verification_failed",
                "raw output could not be read",
            )
        if not isinstance(data, (bytes, bytearray)):
            raise B1RunnerError(
                "raw_output_verification_failed",
                "raw output is not bytes",
            )
        payload = bytes(data)
        if len(payload) != item.get("byte_count"):
            raise B1RunnerError(
                "raw_output_verification_failed",
                "raw output byte count changed",
            )
        digest = _sha256_bytes(payload)
        if digest != item.get("sha256"):
            raise B1RunnerError(
                "raw_output_verification_failed",
                "raw output hash changed",
            )
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            raise B1RunnerError(
                "raw_output_verification_failed",
                "raw output is not valid UTF-8",
            )
        line_count = len(cleaner.split_raw_records(text))
        if line_count != item.get("line_count") or line_count != ATTEMPTS_PER_CAP:
            raise B1RunnerError(
                "raw_output_verification_failed",
                "raw output line count changed",
            )
    context["final_raw_output_verification"] = {
        "passed": True,
        "file_count": INVOCATION_COUNT,
    }
    return context["final_raw_output_verification"]


def _finalize_evidence(context, deps, cleaner):
    """Write ledgers, the hash report, and the success manifest last.

    The success-manifest SHA-256 is the hash of the finalized bytes. The hash
    report is written before those bytes. Nothing fallible runs after the
    success marker is written.
    """
    output_dir = Path(context["output_dir"])
    attempts = context["attempts"]
    raw_payload = serialize_jsonl(attempts, RAW_LEDGER_KEYS)
    audited_payload = serialize_jsonl(attempts, AUDITED_LEDGER_KEYS)
    if raw_payload == audited_payload:
        raise B1RunnerError(
            "success_manifest_refused",
            "raw and audited ledgers must differ",
        )
    _write_evidence(deps, output_dir / RAW_LEDGER_NAME, raw_payload)
    context["raw_ledger_sha256"] = _sha256_bytes(raw_payload)
    _write_evidence(deps, output_dir / AUDITED_LEDGER_NAME, audited_payload)
    context["audited_ledger_sha256"] = _sha256_bytes(audited_payload)
    context["diagnostics"] = sequence_only_diagnostics(attempts)
    context["timestamps"] = {
        "started_at": context["started_at"],
        "finished_at": deps.clock(),
    }
    context["hostname"] = deps.hostname()
    verify_retained_raw_outputs(context, deps, cleaner)
    manifest = build_success_manifest(context)
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_sha = _sha256_bytes(manifest_bytes)
    report = {
        "manifest_path": SUCCESS_MANIFEST_NAME,
        "manifest_sha256": manifest_sha,
        "raw_ledger_sha256": context["raw_ledger_sha256"],
        "audited_ledger_sha256": context["audited_ledger_sha256"],
        "excluded_from_manifest_body": "manifest_sha256",
    }
    _write_evidence(deps, output_dir / HASH_REPORT_NAME, canonical_json_bytes(report))
    success_path = output_dir / SUCCESS_MANIFEST_NAME
    failure_path = output_dir / FAILURE_MANIFEST_NAME
    if _path_exists(failure_path):
        raise B1RunnerError(
            "failure_manifest_exists",
            "refusing to write a success manifest beside a failure manifest",
        )
    if _path_exists(success_path):
        raise B1RunnerError(
            "success_marker_present",
            "refusing to overwrite the success manifest",
        )
    _write_evidence(deps, success_path, manifest_bytes)
    return manifest


def execute_phase_a(prepared, deps):
    context = _ensure_live_context(prepared)
    parent_before = list(deps.environ.items())
    cleaner = deps.load_cleaner(context.get("cleaner_source_bytes"))
    for invocation in context["plan"]:
        _run_invocation(context, deps, cleaner, invocation, parent_before)
    if list(deps.environ.items()) != parent_before:
        raise B1RunnerError(
            "parent_environment_mutated",
            "parent environment was modified",
        )
    return _finalize_evidence(context, deps, cleaner)


def record_failure(output_dir, error, deps, context):
    success = Path(output_dir) / SUCCESS_MANIFEST_NAME
    failure = Path(output_dir) / FAILURE_MANIFEST_NAME
    if _path_exists(success):
        raise B1RunnerError(
            "success_marker_present",
            "refusing to write a failure manifest after the success marker",
        )
    if _path_exists(failure):
        raise B1RunnerError(
            "failure_manifest_exists",
            "refusing to overwrite the failure manifest",
        )
    error = normalize_evidence_error(error)
    if not isinstance(error, B1RunnerError):
        error = B1RunnerError(
            "unexpected_runtime_failure",
            "unexpected runtime failure",
        )
    if not context.get("output_dir"):
        context["output_dir"] = str(output_dir)
    timestamps = dict(context.get("timestamps") or {})
    timestamps["failed_at"] = deps.clock()
    context["timestamps"] = timestamps
    if context.get("hostname") is None:
        context["hostname"] = deps.hostname()
    document = build_failure_manifest(context, error)
    if document["status"] != "failed":
        raise B1RunnerError(
            "success_manifest_refused",
            "a failed run cannot produce a success manifest",
        )
    if _path_exists(success) or _path_exists(failure):
        raise B1RunnerError(
            "success_marker_present",
            "refusing to write a failure manifest after another marker exists",
        )
    try:
        deps.write_exclusive(failure, canonical_json_bytes(document))
    except FileExistsError:
        raise B1RunnerError(
            "failure_manifest_exists",
            "refusing to overwrite the failure manifest",
        )
    except B1RunnerError:
        raise
    except Exception:
        raise B1RunnerError(
            "failure_manifest_write_failed",
            "failure evidence could not be written",
        )
    if _path_exists(success):
        raise B1RunnerError(
            "success_marker_present",
            "success and failure manifests must not coexist",
        )
    return document


def after_directory_created(output_dir, deps, operation, context):
    try:
        return operation()
    except Exception as exc:
        error = normalize_evidence_error(exc)
        if not isinstance(error, B1RunnerError):
            error = B1RunnerError(
                "unexpected_runtime_failure",
                "unexpected runtime failure",
            )
        if _path_exists(Path(output_dir) / SUCCESS_MANIFEST_NAME):
            raise error
        try:
            record_failure(output_dir, error, deps, context)
        except Exception as secondary:
            if isinstance(secondary, B1RunnerError):
                error.secondary_failure = secondary.code
            else:
                error.secondary_failure = "failure_manifest_write_failed"
        raise error


def run(output_dir, deps):
    """Execute only after every cheap gate has passed.

    Gate order is deliberate: document and authorisation fields, the Phase A
    plan, CUDA_VISIBLE_DEVICES and CUDA_DEVICE_ORDER, the output path,
    repository pins, small file pins, then multi-gigabyte weights, the runner
    bytes, the physical GPU query, and the pinned-interpreter CUDA probe.
    Directory creation happens only after those gates. The CUDA probe is the
    last gate before mkdir.
    """
    config_bytes = deps.read_bytes(B1_CONFIG_PATH)
    config = load_config_bytes(config_bytes)
    snapshot = assert_document_gates(config)
    plan = build_phase_a_plan(config)
    assert_cuda_environment(deps.environ)
    assert_output_directory(output_dir, snapshot, deps.lstat, deps.realpath)
    provenance = assert_repository_pins(snapshot, deps.git)
    assert_cleaner_allowed(APPROVED_CLEANER)
    assert_encdec_selection(ENCDEC_RELATIVE)
    assert_diffusion_selection(DIFFUSION_RELATIVE)
    pins = []
    pins.extend(verify_pinned_assets(deps.lstat, deps.sha256_file, large=False))
    pins.extend(verify_pinned_assets(deps.lstat, deps.sha256_file, large=True))
    cleaner_source_bytes = verified_cleaner_source(deps.read_bytes)
    runner_bytes = deps.read_bytes(RUNNER_PATH)
    child_env = build_child_environment(deps.environ, output_dir, deps.realpath)
    gpu = deps.gpu_preflight(child_env)
    input_hashes = {
        "configuration": file_content_record(B1_CONFIG_PATH, config_bytes),
        "runner": file_content_record(RUNNER_PATH, runner_bytes),
    }
    deps.mkdir(output_dir)
    prepared = {
        "output_dir": output_dir,
        "config": config,
        "snapshot": snapshot,
        "plan": plan,
        "provenance": provenance,
        "pins": pins,
        "gpu": gpu,
        "input_hashes": input_hashes,
        "cleaner_source_bytes": cleaner_source_bytes,
        "started_at": deps.clock(),
        "commands": [],
        "raw_outputs": [],
        "completed_invocation_indexes": [],
        "attempts": [],
        "attempt_count": 0,
        "diagnostics": None,
        "raw_ledger_sha256": None,
        "audited_ledger_sha256": None,
    }
    return after_directory_created(
        output_dir,
        deps,
        lambda: execute_phase_a(prepared, deps),
        prepared,
    )


def main(argv=None, deps=None):
    if deps is None:
        deps = production_dependencies()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 2
        return int(code)
    try:
        run(args.output_dir, deps)
    except B1RunnerError as exc:
        message = "error: {}: {}".format(exc.code, exc.detail)
        if exc.secondary_failure:
            message += " secondary: {}".format(exc.secondary_failure)
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
