#!/usr/bin/env python3
"""Non-executable M4 B1 Phase B runner.

The checked-in B1 configuration is closed. This module builds the frozen
89-length invocation plan and the future evidence writers. It does not
import a model stack or Torch, and it does not select physical GPU 0 or
physical GPU 1. A later phase_b_scientific_execution_authorisation must
bind one of those devices. The consumed Phase A authorisation is never
accepted as that binding.

For the checked-in configuration the process refuses with
configuration_not_consumable before it inspects an output path, creates a
directory, inspects a repository, queries a GPU, hashes a weight, loads
the cleaner, reads biological data, or builds a generation subprocess.
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
RUNNER_RELATIVE = "scripts/b1_phase_b_runner.py"
RUNNER_PATH = MRES_ROOT / RUNNER_RELATIVE
B1_CONFIG_PATH = MRES_ROOT / "config/experiments/B1_generic_generation.yaml"
PINNED_PYTHON = "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python"
GENERATION_ENTRY = RNAGENESIS_ROOT / "generation.py"
APPROVED_CLEANER = RNAGENESIS_ROOT / "scripts/audit_generation_output.py"
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
PHASE_B_EXECUTION_STATUS = "AUTHORISED_FOR_EXECUTION"
ACTIVE_UNCONSUMED_STATUS = "active_unconsumed"
PHASE_B_AUTHORISATION_NAME = "phase_b_scientific_execution_authorisation"
PHASE_A_AUTHORISATION_NAME = "scientific_execution_authorisation"
# Neither device is selected here. A later authorisation binds one of them.
SUPPORTED_PHYSICAL_GPUS = (0, 1)
CUDA_DEVICE_ORDER = "PCI_BUS_ID"
MANIFEST_SCHEMA_VERSION = "m4-b1-phase-b-manifest-1"
CANDIDATE_STATUS = (
    "APPROVED_CANDIDATE_FOR_PHASE_B_EVALUATION_NOT_FINAL_PRODUCTION_MAPPING"
)
CANDIDATE_FORMULA = "max_seq_len = requested_biological_length + 1"
M3_REPORT = "docs/fine_tuning/m3_frozen_corpus_loader_and_modelling_interface.md"
M3_SUMMARY_SHA256 = (
    "8862ecb066fac12ae80529737a2398322227f8789af07c2de2d375279896638c"
)
M3_TOKENIZER_AUDIT_SHA256 = (
    "063a068187e5b34c598b1ef4a294f924f3167538aec824786d6e9fac01d4eb9f"
)
TRAIN_CORE_COUNT = 669
LENGTH_COUNT = 89
LENGTH_MINIMUM = 20
LENGTH_MAXIMUM = 123
BASE_SEED = 42000
FIRST_SEED = 42000
LAST_SEED = 42088
ATTEMPTS_PER_LENGTH = 16
INVOCATION_COUNT = 89
TOTAL_ATTEMPTS = 1424
BATCH_SIZE = 16
BATCH_NUM = 1
DDIM_STEPS = 50
PROVISIONAL_AGGREGATE = 0.90
PROVISIONAL_PER_LENGTH_FLOOR = 0.50
ENCDEC_RELATIVE = "configs/rnagenesis/autoencoder"
DIFFUSION_RELATIVE = "configs/rnagenesis/diffusion"
CLASSIFIER_RELATIVE = "configs/rnagenesis/classifier/mlp_160_32.yaml"
DECODER_CONFIG_NAME = "config-progen2-small-rna_tokenizer_v2"
RUNNER_CONFIG_PATH = "scripts/b1_phase_b_runner.py"

FROZEN_TRAIN_LENGTHS = (
    20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
    30, 31, 32, 33, 34, 35, 36, 37, 38, 39,
    40, 41, 42, 43, 44, 45, 46, 47, 48, 49,
    50, 51, 52, 53, 54, 55, 56, 57, 58, 59,
    60, 61, 62, 63, 64, 65, 66, 67, 68, 69,
    70, 71, 72, 73, 74, 75, 76, 77, 78, 79,
    80, 81, 82, 83, 84, 85, 86, 87, 88, 89,
    90, 91, 92, 93, 95, 96, 97, 98, 99, 100,
    104, 106, 107, 109, 112, 114, 116, 117, 123,
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
    "tokenizer_audit",
    "m3_audit",
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

PHASE_B_AUTHORISATION_KEYS = (
    "authorisation_id",
    "authorisation_active",
    "activation_status",
    "consumed",
    "authorises_b1_phase_b",
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
    "development_pool_authorised",
    "final_production_mapping_declared",
    "rejection_or_resampling_algorithm_declared",
)

OFFLINE_CONTROLS = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}

RAW_LEDGER_NAME = "phase_b_raw_attempts.jsonl"
AUDITED_LEDGER_NAME = "phase_b_audited_attempts.jsonl"
SUCCESS_MANIFEST_NAME = "phase_b_manifest.json"
FAILURE_MANIFEST_NAME = "phase_b_failure_manifest.json"
HASH_REPORT_NAME = "phase_b_manifest_sha256.json"
PYCACHE_DIRECTORY_NAME = "python_pycache"
RUNTIME_CACHE_DIRECTORY_NAME = "isolated_runtime_cache"
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
    "attempt_within_length",
    "requested_biological_length",
    "max_seq_len",
    "seed",
    "raw_decoded_text",
    "raw_length",
    "leading_boundary_marker_run",
    "trailing_boundary_marker_run",
    "cleaned_sequence",
    "cleaned_length",
    "validity",
    "rejection_reason",
    "termination_observation",
    "exact_length",
)
RAW_LEDGER_KEYS = (
    "invocation_index",
    "attempt_index",
    "attempt_within_length",
    "requested_biological_length",
    "max_seq_len",
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


CUDA_PROBE_SOURCE = "\n".join(_cuda_probe_lines()) + "\n"
EOS_OBSERVED = "eos_marker_observed"
TERMINATION_NOT_OBSERVABLE = "not_observable_from_decoded_text"
ACCESS_DECLARATION = {
    "train_opened": False,
    "validation_opened": False,
    "ref_opened": False,
    "eval_opened": False,
    "m3_audit_csv_opened": False,
    "m3_report_opened": False,
    "biological_sequence_data_opened": False,
    "classifier_read_by_generation_workflow": False,
    "guidance_enabled": False,
    "development_pool_sampled": False,
    "development_pool_authorised": False,
    "development_pool_executed": False,
    "b1_eligibility": "not_declared",
    "b1_eligible": False,
    "m4_complete": False,
    "final_production_mapping_declared": False,
    "rejection_or_resampling_algorithm_declared": False,
    "phase_a_authorisation_accepted_for_phase_b": False,
}


class PhaseBRunnerError(Exception):
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
    _pin("generation.py", None, GENERATION_SHA256, "generation_entry"),
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
        prog="b1_phase_b_runner",
        description=(
            "M4 B1 Phase B candidate-mapping runner. "
            "The current configuration is not executable. "
            "Physical GPU 0 and physical GPU 1 are both supported, "
            "and neither is selected by this implementation."
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Authorised Phase B evidence directory. Relative paths are refused.",
    )
    parser.add_argument(
        "--physical-gpu",
        required=True,
        help="Physical GPU index, exactly 0 or 1. The implementation does not choose it.",
    )
    return parser


def load_config_bytes(raw):
    if not isinstance(raw, (bytes, bytearray)):
        raise PhaseBRunnerError("config_encoding", "configuration bytes are required")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise PhaseBRunnerError(
            "config_encoding",
            "configuration must be UTF-8 without a BOM or carriage return",
        )
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        raise PhaseBRunnerError("config_encoding", "configuration is not valid UTF-8")
    try:
        loaded = yaml.safe_load(text)
    except Exception:
        raise PhaseBRunnerError("config_parse", "configuration could not be parsed")
    if not isinstance(loaded, dict):
        raise PhaseBRunnerError("config_shape", "configuration root must be a mapping")
    return loaded


def _require_mapping(value, code, detail):
    if not isinstance(value, dict):
        raise PhaseBRunnerError(code, detail)
    return value


def _is_sha40(value):
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_exact(mapping, key, expected, code, detail):
    if key not in mapping or mapping[key] != expected:
        raise PhaseBRunnerError(code, detail)


def evidence_directory_for_commit(commit):
    if not _is_sha40(commit):
        raise PhaseBRunnerError(
            "authorisation_commit_invalid",
            "executing_implementation_commit is not a 40-character lowercase SHA-1",
        )
    return (
        "/home/laura/rnagenesis-mres-runs/"
        "m4_b1_generic_generation_B1_generic_released_rnagenesis_"
        + commit[:12]
        + "_phaseB"
    )


def assert_configuration_consumable(config):
    """Closed documents stop here. No path, repository, GPU, or model work."""
    if not isinstance(config, dict):
        raise PhaseBRunnerError(
            "configuration_not_consumable",
            "configuration root must be a mapping",
        )
    if config.get("consumable_by_executable_workflow") is not True:
        raise PhaseBRunnerError(
            "configuration_not_consumable",
            "consumable_by_executable_workflow is not true",
        )
    status = config.get("document_status")
    if status in NON_EXECUTABLE_DOCUMENT_STATUSES or status != EXECUTABLE_DOCUMENT_STATUS:
        raise PhaseBRunnerError(
            "configuration_not_consumable",
            "document_status is not {}".format(EXECUTABLE_DOCUMENT_STATUS),
        )
    phase = config.get("phase_b")
    if not isinstance(phase, dict) or phase.get("executable_now") is not True:
        raise PhaseBRunnerError(
            "configuration_not_consumable",
            "phase_b.executable_now is not true",
        )
    if phase.get("status") != PHASE_B_EXECUTION_STATUS:
        raise PhaseBRunnerError(
            "configuration_not_consumable",
            "phase_b.status is not {}".format(PHASE_B_EXECUTION_STATUS),
        )
    execution = config.get("execution")
    if not isinstance(execution, dict):
        raise PhaseBRunnerError(
            "configuration_not_consumable",
            "execution is missing",
        )
    if execution.get("authorised") is not True:
        raise PhaseBRunnerError(
            "configuration_not_consumable",
            "execution.authorised is not true",
        )
    if execution.get("gpu_authorised_by_this_approval") is not True:
        raise PhaseBRunnerError(
            "configuration_not_consumable",
            "execution.gpu_authorised_by_this_approval is not true",
        )
    return True


def parse_physical_gpu_argument(value):
    """Accept only the exact CLI tokens 0 and 1. Do not choose between them."""
    if type(value) is not str or value not in ("0", "1"):
        raise PhaseBRunnerError(
            "unsupported_physical_gpu",
            "physical GPU must be exactly 0 or 1",
        )
    parsed = int(value)
    if parsed not in SUPPORTED_PHYSICAL_GPUS:
        raise PhaseBRunnerError(
            "unsupported_physical_gpu",
            "physical GPU must be exactly 0 or 1",
        )
    return parsed


def _phase_a_block_cannot_authorise(config):
    block = config.get(PHASE_A_AUTHORISATION_NAME)
    if isinstance(block, dict):
        raise PhaseBRunnerError(
            "phase_a_authorisation_cannot_authorise_phase_b",
            "the consumed Phase A scientific_execution_authorisation cannot authorise Phase B",
        )
    raise PhaseBRunnerError(
        "phase_b_authorisation_missing",
        "phase_b_scientific_execution_authorisation is missing",
    )


def _looks_like_phase_a_authorisation(block):
    if not isinstance(block, dict):
        return False
    if block.get("phase") == "A":
        return True
    if "authorises_b1_phase_a" in block:
        return True
    if "authorises_b1_phase_b" not in block and "phase_b_authorised" in block:
        return True
    return False


def assert_phase_b_authorisation(config, physical_gpu):
    """Require a separate active Phase B authorisation for this physical GPU.

    The Phase A scientific_execution_authorisation is ignored as a grant.
    It cannot satisfy this function, including when it is copied into the
    Phase B block.
    """
    if type(physical_gpu) is not int or physical_gpu not in SUPPORTED_PHYSICAL_GPUS:
        raise PhaseBRunnerError(
            "unsupported_physical_gpu",
            "physical GPU must be exactly 0 or 1",
        )
    if PHASE_B_AUTHORISATION_NAME not in config:
        _phase_a_block_cannot_authorise(config)
    block = config[PHASE_B_AUTHORISATION_NAME]
    if not isinstance(block, dict):
        _phase_a_block_cannot_authorise(config)
    if _looks_like_phase_a_authorisation(block):
        raise PhaseBRunnerError(
            "phase_a_authorisation_cannot_authorise_phase_b",
            "a Phase A authorisation cannot authorise Phase B",
        )
    if set(block) != set(PHASE_B_AUTHORISATION_KEYS):
        extra = sorted(set(block) - set(PHASE_B_AUTHORISATION_KEYS))
        if extra:
            raise PhaseBRunnerError(
                "phase_b_authorisation_overbroad",
                "Phase B authorisation has unexpected fields: {}".format(", ".join(extra)),
            )
        missing = [key for key in PHASE_B_AUTHORISATION_KEYS if key not in block]
        raise PhaseBRunnerError(
            "phase_b_authorisation_missing",
            "phase_b_scientific_execution_authorisation.{} is missing".format(missing[0]),
        )
    consumed_is_unconsumed = block["consumed"] is False
    if consumed_is_unconsumed is not True:
        raise PhaseBRunnerError(
            "phase_b_authorisation_consumed",
            "Phase B authorisation consumed is not false",
        )
    if (
        block["authorisation_active"] is not True
        or block["activation_status"] != ACTIVE_UNCONSUMED_STATUS
    ):
        raise PhaseBRunnerError(
            "phase_b_authorisation_inactive",
            "Phase B authorisation is not active_unconsumed",
        )
    if block["phase"] != "B":
        raise PhaseBRunnerError(
            "phase_b_wrong_phase",
            "Phase B authorisation phase is not B",
        )
    if block["authorises_b1_phase_b"] is not True:
        raise PhaseBRunnerError(
            "phase_b_authorisation_missing",
            "authorises_b1_phase_b is not true",
        )
    if block["gpu_use_authorised"] is not True:
        raise PhaseBRunnerError(
            "phase_b_gpu_mismatch",
            "gpu_use_authorised is not true",
        )
    if type(block["physical_gpu"]) is not int or block["physical_gpu"] != physical_gpu:
        raise PhaseBRunnerError(
            "phase_b_gpu_mismatch",
            "authorisation physical_gpu does not match the required physical GPU",
        )
    commit = block["executing_implementation_commit"]
    if not _is_sha40(commit):
        raise PhaseBRunnerError(
            "authorisation_commit_invalid",
            "executing_implementation_commit is not a 40-character lowercase SHA-1",
        )
    if block["mres_branch"] != "main":
        raise PhaseBRunnerError(
            "mres_branch_not_main",
            "authorisation mres_branch is not main",
        )
    if block["condition"] != CONDITION_LABEL or config.get("condition_manifest_label") != CONDITION_LABEL:
        raise PhaseBRunnerError(
            "phase_b_authorisation_overbroad",
            "authorisation condition is not B1_generic_released_rnagenesis",
        )
    authorisation_id = block["authorisation_id"]
    if not isinstance(authorisation_id, str) or authorisation_id.strip() == "":
        raise PhaseBRunnerError(
            "phase_b_authorisation_missing",
            "authorisation_id is missing",
        )
    expected_directory = evidence_directory_for_commit(commit)
    if (
        block["output_directory"] != expected_directory
        or block["evidence_directory"] != expected_directory
    ):
        raise PhaseBRunnerError(
            "authorisation_evidence_mismatch",
            "authorisation does not bind Phase B to the exact evidence directory",
        )
    overbroad = (
        ("success_claimed", False),
        ("m4_complete", False),
        ("b1_eligible", False),
        ("development_pool_authorised", False),
        ("final_production_mapping_declared", False),
        ("rejection_or_resampling_algorithm_declared", False),
    )
    for key, expected in overbroad:
        if block[key] is not expected:
            raise PhaseBRunnerError(
                "phase_b_authorisation_overbroad",
                "{} must be false".format(key),
            )
    snapshot = {}
    for key in PHASE_B_AUTHORISATION_KEYS:
        snapshot[key] = block[key]
    snapshot["selected_physical_gpu"] = physical_gpu
    return snapshot


def _assert_ascending_unique(lengths):
    if lengths != sorted(lengths):
        raise PhaseBRunnerError(
            "phase_b_plan_invalid",
            "frozen biological lengths are not strictly ascending",
        )
    if len(lengths) != len(set(lengths)):
        raise PhaseBRunnerError(
            "phase_b_plan_invalid",
            "frozen biological lengths are duplicated",
        )


def build_phase_b_plan(config):
    """Validate the frozen 89-row plan in memory. This has no side effects."""
    phase = _require_mapping(
        config.get("phase_b"),
        "phase_b_plan_invalid",
        "phase_b is missing",
    )
    if "frozen_biological_lengths" not in phase:
        raise PhaseBRunnerError(
            "phase_b_plan_invalid",
            "frozen biological lengths are missing",
        )
    lengths = list(phase["frozen_biological_lengths"])
    _assert_ascending_unique(lengths)
    if lengths != list(FROZEN_TRAIN_LENGTHS):
        raise PhaseBRunnerError(
            "phase_b_plan_invalid",
            "frozen biological lengths do not match the approved 89-length list",
        )
    if len(lengths) != LENGTH_COUNT or lengths[0] != LENGTH_MINIMUM or lengths[-1] != LENGTH_MAXIMUM:
        raise PhaseBRunnerError(
            "phase_b_plan_invalid",
            "frozen biological lengths do not have 89 entries from 20 through 123",
        )
    provenance = _require_mapping(
        phase.get("frozen_train_length_provenance"),
        "phase_b_plan_invalid",
        "frozen TRAIN length provenance is missing",
    )
    _require_exact(provenance, "m3_report", M3_REPORT, "phase_b_plan_invalid", "M3 report path drifted")
    _require_exact(
        provenance,
        "accepted_m3_summary_sha256",
        M3_SUMMARY_SHA256,
        "phase_b_plan_invalid",
        "accepted M3 summary hash drifted",
    )
    _require_exact(
        provenance,
        "accepted_m3_tokenizer_audit_sha256",
        M3_TOKENIZER_AUDIT_SHA256,
        "phase_b_plan_invalid",
        "accepted M3 tokenizer-audit hash drifted",
    )
    _require_exact(
        provenance,
        "train_core_count",
        TRAIN_CORE_COUNT,
        "phase_b_plan_invalid",
        "TRAIN core count is not 669",
    )
    _require_exact(
        provenance,
        "distinct_train_length_count",
        LENGTH_COUNT,
        "phase_b_plan_invalid",
        "distinct TRAIN length count is not 89",
    )
    _require_exact(provenance, "minimum", LENGTH_MINIMUM, "phase_b_plan_invalid", "minimum length is not 20")
    _require_exact(provenance, "maximum", LENGTH_MAXIMUM, "phase_b_plan_invalid", "maximum length is not 123")
    if provenance.get("source_files_opened_by_runner") is not False:
        raise PhaseBRunnerError(
            "phase_b_plan_invalid",
            "the runner must not open M3 or corpus source files",
        )
    schedule = _require_mapping(
        phase.get("frozen_schedule"),
        "phase_b_plan_invalid",
        "frozen schedule is missing",
    )
    _require_exact(schedule, "candidate_status", CANDIDATE_STATUS, "phase_b_plan_invalid", "candidate status drifted")
    _require_exact(
        schedule,
        "max_seq_len_formula",
        CANDIDATE_FORMULA,
        "phase_b_plan_invalid",
        "max_seq_len formula drifted",
    )
    _require_exact(schedule, "max_seq_len_offset", 1, "phase_b_plan_invalid", "max_seq_len offset is not 1")
    _require_exact(
        schedule,
        "final_production_mapping",
        False,
        "phase_b_plan_invalid",
        "the plus-one mapping is not final",
    )
    _require_exact(schedule, "invocations", INVOCATION_COUNT, "phase_b_plan_invalid", "invocations is not 89")
    _require_exact(
        schedule,
        "raw_attempts_per_length",
        ATTEMPTS_PER_LENGTH,
        "phase_b_plan_invalid",
        "raw attempt count is not 16",
    )
    _require_exact(
        schedule,
        "total_raw_attempts",
        TOTAL_ATTEMPTS,
        "phase_b_plan_invalid",
        "total raw attempts is not 1424",
    )
    _require_exact(schedule, "batch_size", BATCH_SIZE, "phase_b_plan_invalid", "batch_size is not 16")
    _require_exact(schedule, "batch_num", BATCH_NUM, "phase_b_plan_invalid", "batch_num is not 1")
    _require_exact(
        schedule,
        "invocation_order",
        "ascending_biological_length",
        "phase_b_plan_invalid",
        "invocation order is not ascending biological length",
    )
    _require_exact(schedule, "base_seed", BASE_SEED, "phase_b_plan_invalid", "base seed is not 42000")
    _require_exact(
        schedule,
        "seed_formula",
        "42000 + zero_based_length_index",
        "phase_b_plan_invalid",
        "seed formula drifted",
    )
    _require_exact(schedule, "first_seed", FIRST_SEED, "phase_b_plan_invalid", "first seed is not 42000")
    _require_exact(schedule, "last_seed", LAST_SEED, "phase_b_plan_invalid", "last seed is not 42088")
    for key in (
        "one_seed_per_length",
        "seed_confounded_with_length",
        "early_eos_outputs_recorded_as_raw_attempts",
        "invalid_outputs_remain_in_denominators",
        "duplicate_outputs_remain_in_denominators",
        "plan_validated_before_side_effects",
        "runner_reads_lengths_from_this_configuration",
    ):
        if schedule.get(key) is not True:
            raise PhaseBRunnerError("phase_b_plan_invalid", "{} is not true".format(key))
    if schedule.get("independent_replicate") is not False:
        raise PhaseBRunnerError(
            "phase_b_plan_invalid",
            "the length seed is not an independent replicate",
        )
    for key in ("rejection", "resampling", "trimming", "padding", "deduplication", "replacement"):
        if schedule.get(key) is not False:
            raise PhaseBRunnerError("phase_b_plan_invalid", "{} is not false".format(key))
    closed = schedule.get("runner_must_not_open")
    if list(closed or []) != ["m3_audit_csv", "TRAIN", "VALIDATION", "REF", "EVAL"]:
        raise PhaseBRunnerError(
            "phase_b_plan_invalid",
            "the runner must not open the M3 audit CSV, TRAIN, VALIDATION, REF, or EVAL",
        )
    _require_exact(phase, "raw_attempts_per_length", ATTEMPTS_PER_LENGTH, "phase_b_plan_invalid", "raw attempt count is not 16")
    _require_exact(phase, "base_seed", BASE_SEED, "phase_b_plan_invalid", "base seed is not 42000")
    _require_exact(phase, "first_seed", FIRST_SEED, "phase_b_plan_invalid", "first seed is not 42000")
    _require_exact(phase, "last_seed", LAST_SEED, "phase_b_plan_invalid", "last seed is not 42088")
    _require_exact(
        phase,
        "distinct_train_lengths_recorded_by_m3",
        LENGTH_COUNT,
        "phase_b_plan_invalid",
        "distinct TRAIN length count is not 89",
    )
    _require_exact(
        phase,
        "proposed_total_raw_attempts_if_89_lengths",
        TOTAL_ATTEMPTS,
        "phase_b_plan_invalid",
        "total raw attempts is not 1424",
    )
    shape = phase.get("proposed_invocation_shape")
    if (
        not isinstance(shape, dict)
        or shape.get("batch_size") != BATCH_SIZE
        or shape.get("batch_num") != BATCH_NUM
    ):
        raise PhaseBRunnerError(
            "phase_b_plan_invalid",
            "invocation shape is not batch_size 16 and batch_num 1",
        )
    mapping = _require_mapping(
        phase.get("approved_candidate_mapping"),
        "phase_b_plan_invalid",
        "approved candidate mapping is missing",
    )
    _require_exact(mapping, "status", CANDIDATE_STATUS, "phase_b_plan_invalid", "candidate status drifted")
    _require_exact(mapping, "formula", CANDIDATE_FORMULA, "phase_b_plan_invalid", "max_seq_len formula drifted")
    _require_exact(mapping, "max_seq_len_offset", 1, "phase_b_plan_invalid", "max_seq_len offset is not 1")
    _require_exact(
        mapping,
        "final_production_mapping",
        False,
        "phase_b_plan_invalid",
        "the plus-one mapping is not final",
    )
    record = _require_mapping(
        phase.get("implementation_record"),
        "phase_b_plan_invalid",
        "implementation record is missing",
    )
    _require_exact(
        record,
        "runner",
        RUNNER_CONFIG_PATH,
        "phase_b_plan_invalid",
        "Phase B runner path drifted",
    )
    _require_exact(
        record,
        "authorisation_block",
        PHASE_B_AUTHORISATION_NAME,
        "phase_b_plan_invalid",
        "Phase B authorisation block name drifted",
    )
    gpu_selection = _require_mapping(
        phase.get("physical_gpu_selection"),
        "phase_b_plan_invalid",
        "physical GPU selection contract is missing",
    )
    if gpu_selection.get("selected_by_implementation") is not False:
        raise PhaseBRunnerError(
            "phase_b_plan_invalid",
            "the implementation must not select the physical GPU",
        )
    if list(gpu_selection.get("supported_physical_gpus") or []) != list(SUPPORTED_PHYSICAL_GPUS):
        raise PhaseBRunnerError(
            "phase_b_plan_invalid",
            "supported physical GPUs are not 0 and 1",
        )
    _require_exact(
        gpu_selection,
        "cuda_device_order",
        CUDA_DEVICE_ORDER,
        "phase_b_plan_invalid",
        "CUDA_DEVICE_ORDER is not PCI_BUS_ID",
    )
    _require_exact(gpu_selection, "logical_device", "cuda:0", "phase_b_plan_invalid", "logical device is not cuda:0")
    _require_exact(gpu_selection, "visible_torch_devices", 1, "phase_b_plan_invalid", "visible Torch device count is not 1")
    if gpu_selection.get("cpu_fallback") is not False or gpu_selection.get("other_physical_gpu_fallback") is not False:
        raise PhaseBRunnerError("phase_b_plan_invalid", "GPU fallback is enabled")
    if gpu_selection.get("phase_a_authorisation_accepted") is not False:
        raise PhaseBRunnerError(
            "phase_b_plan_invalid",
            "Phase A authorisation must not be accepted for Phase B",
        )
    diagnostics = _require_mapping(
        phase.get("provisional_diagnostics"),
        "phase_b_plan_invalid",
        "provisional diagnostics contract is missing",
    )
    _require_exact(
        diagnostics,
        "per_length_exact_hit_floor",
        PROVISIONAL_PER_LENGTH_FLOOR,
        "phase_b_plan_invalid",
        "per-length floor drifted",
    )
    _require_exact(
        diagnostics,
        "aggregate_exact_hit_diagnostic",
        PROVISIONAL_AGGREGATE,
        "phase_b_plan_invalid",
        "aggregate diagnostic drifted",
    )
    _require_exact(
        diagnostics,
        "zero_valid_outputs_exact_hit_rate",
        0.0,
        "phase_b_plan_invalid",
        "zero-valid exact-hit rate drifted",
    )
    for key in (
        "failing_a_diagnostic_is_an_implementation_crash",
        "passing_a_diagnostic_declares_b1_eligible",
        "declares_final_plus_one_mapping",
        "declares_rejection_or_resampling_algorithm",
        "authorises_development_pool",
        "executes_development_pool",
        "claims_m4_complete",
    ):
        if diagnostics.get(key) is not False:
            raise PhaseBRunnerError("phase_b_plan_invalid", "{} is not false".format(key))
    shared = _require_mapping(
        config.get("shared_generation_settings"),
        "phase_b_plan_invalid",
        "shared_generation_settings is missing",
    )
    if shared.get("guidance") is not False:
        raise PhaseBRunnerError("guidance_not_disabled", "shared_generation_settings.guidance is not false")
    shared_checks = (
        ("ddim_steps", DDIM_STEPS, "ddim_steps is not 50"),
        ("eta", 0, "eta is not 0"),
        ("top_p", 0.95, "top_p is not 0.95"),
        ("top_k", 0, "top_k is not 0"),
        ("do_sample", True, "do_sample is not true"),
        ("bos_token", 1, "bos_token is not 1"),
        ("eos_token", 2, "eos_token is not 2"),
        ("silent_truncation", False, "silent truncation is enabled"),
        ("batch_size_where_memory_permits", BATCH_SIZE, "batch size is not 16"),
        ("automatic_batch_size_fallback", False, "automatic batch fallback is enabled"),
        ("cpu_fallback", False, "cpu fallback is enabled"),
        ("other_gpu_fallback", False, "other GPU fallback is enabled"),
        ("visible_python_device", "cuda:0", "visible device is not cuda:0"),
        ("cuda_device_order", CUDA_DEVICE_ORDER, "configured CUDA_DEVICE_ORDER is not PCI_BUS_ID"),
    )
    for key, expected, detail in shared_checks:
        if shared.get(key) != expected:
            raise PhaseBRunnerError("phase_b_plan_invalid", detail)
    selection = _require_mapping(
        config.get("immutable_model_selection"),
        "phase_b_plan_invalid",
        "immutable_model_selection is missing",
    )
    _require_exact(selection, "encdec", ENCDEC_RELATIVE, "phase_b_plan_invalid", "EncDec selection drifted")
    _require_exact(selection, "diffusion", DIFFUSION_RELATIVE, "phase_b_plan_invalid", "diffusion selection drifted")
    _require_exact(
        selection,
        "prohibited_diffusion",
        "checkpoints/Aptamer/diffusion",
        "phase_b_plan_invalid",
        "prohibited diffusion path drifted",
    )
    _require_exact(selection, "generation_entry", "generation.py", "phase_b_plan_invalid", "generation entry drifted")
    _require_exact(
        selection,
        "cleaner",
        "scripts/audit_generation_output.py",
        "phase_b_plan_invalid",
        "cleaner selection drifted",
    )
    _require_exact(
        selection,
        "prohibited_cleaner",
        "scripts/clean_generated_sequences.py",
        "phase_b_plan_invalid",
        "prohibited cleaner drifted",
    )
    invocations = []
    for index, length in enumerate(lengths):
        seed = BASE_SEED + index
        invocations.append(
            {
                "invocation_index": index,
                "requested_biological_length": length,
                "max_seq_len": length + 1,
                "cap_offset": 1,
                "seed": seed,
                "batch_size": BATCH_SIZE,
                "batch_num": BATCH_NUM,
                "attempt_index_first": 0,
                "attempt_index_last": ATTEMPTS_PER_LENGTH - 1,
                "attempt_index_global_first": index * ATTEMPTS_PER_LENGTH,
                "attempt_index_global_last": index * ATTEMPTS_PER_LENGTH + ATTEMPTS_PER_LENGTH - 1,
                "seed_confounded_with_length": True,
                "independent_replicate": False,
                "fresh_process": True,
            }
        )
    if len(invocations) != INVOCATION_COUNT:
        raise PhaseBRunnerError("phase_b_plan_invalid", "plan did not contain 89 invocations")
    if invocations[0]["seed"] != FIRST_SEED or invocations[-1]["seed"] != LAST_SEED:
        raise PhaseBRunnerError("phase_b_plan_invalid", "plan seeds are not 42000 through 42088")
    if len(invocations) * ATTEMPTS_PER_LENGTH != TOTAL_ATTEMPTS:
        raise PhaseBRunnerError("phase_b_plan_invalid", "plan did not contain 1424 attempts")
    previous = None
    for invocation in invocations:
        length = invocation["requested_biological_length"]
        if previous is not None and length <= previous:
            raise PhaseBRunnerError(
                "phase_b_plan_invalid",
                "frozen biological lengths are not strictly ascending",
            )
        previous = length
        if invocation["max_seq_len"] != length + 1:
            raise PhaseBRunnerError("phase_b_plan_invalid", "max_seq_len is not length + 1")
        if invocation["seed"] != BASE_SEED + invocation["invocation_index"]:
            raise PhaseBRunnerError("phase_b_plan_invalid", "seed does not match 42000 + index")
    return invocations


def assert_cuda_environment(environ, physical_gpu):
    """Parent and child visibility must name the selected physical GPU exactly."""
    if type(physical_gpu) is not int or physical_gpu not in SUPPORTED_PHYSICAL_GPUS:
        raise PhaseBRunnerError(
            "unsupported_physical_gpu",
            "physical GPU must be exactly 0 or 1",
        )
    if not isinstance(environ, collections.abc.Mapping) or "CUDA_VISIBLE_DEVICES" not in environ:
        raise PhaseBRunnerError(
            "cuda_visible_devices_missing",
            "CUDA_VISIBLE_DEVICES is not set",
        )
    visible = environ["CUDA_VISIBLE_DEVICES"]
    if type(visible) is not str or visible != str(physical_gpu):
        raise PhaseBRunnerError(
            "cuda_visible_devices_refused",
            "CUDA_VISIBLE_DEVICES does not match the selected physical GPU",
        )
    if "CUDA_DEVICE_ORDER" not in environ:
        raise PhaseBRunnerError(
            "cuda_device_order_missing",
            "CUDA_DEVICE_ORDER is not set",
        )
    order = environ["CUDA_DEVICE_ORDER"]
    if type(order) is not str or order != CUDA_DEVICE_ORDER:
        raise PhaseBRunnerError(
            "cuda_device_order_refused",
            'CUDA_DEVICE_ORDER must be exactly "{}"'.format(CUDA_DEVICE_ORDER),
        )


def assert_output_directory(supplied, snapshot, lstat, realpath):
    expected = snapshot["evidence_directory"]
    if type(supplied) is not str or supplied != expected or not supplied.startswith("/"):
        raise PhaseBRunnerError(
            "output_path_mismatch",
            "output directory is not the authorised Phase B evidence directory",
        )
    try:
        observed = lstat(supplied)
    except FileNotFoundError:
        observed = None
    if observed is not None and stat.S_ISLNK(observed.st_mode):
        raise PhaseBRunnerError("output_path_symlink", "output directory is a symlink")
    if realpath(supplied) != supplied:
        raise PhaseBRunnerError(
            "output_path_symlink",
            "output directory is a symlink or path alias",
        )
    if observed is not None:
        raise PhaseBRunnerError("output_path_exists", "output directory already exists")


def _porcelain_lines(porcelain):
    if not isinstance(porcelain, str):
        raise PhaseBRunnerError("git_status_unreadable", "git status porcelain could not be read")
    return [line for line in porcelain.splitlines() if line != ""]


def _split_porcelain(line):
    if len(line) < 4 or line[2] != " ":
        raise PhaseBRunnerError("git_status_unreadable", "git status porcelain could not be read")
    return line[0], line[1], line[3:]


def _assert_mres_worktree_clean(porcelain):
    for line in _porcelain_lines(porcelain):
        index_status, worktree_status, _path = _split_porcelain(line)
        staged = index_status not in (" ", "?")
        tracked = worktree_status not in (" ", "?")
        untracked = index_status == "?" and worktree_status == "?"
        if untracked:
            raise PhaseBRunnerError("mres_worktree_dirty", "untracked files are present")
        if staged and tracked:
            raise PhaseBRunnerError(
                "mres_worktree_dirty",
                "staged and unstaged tracked changes are present",
            )
        if staged:
            raise PhaseBRunnerError("mres_worktree_dirty", "staged changes are present")
        if tracked:
            raise PhaseBRunnerError("mres_worktree_dirty", "tracked changes are present")
        raise PhaseBRunnerError("mres_worktree_dirty", "the worktree is not clean")


def _known_rnagenesis_untracked(path):
    normalised = path.replace("\\", "/").strip()
    if normalised.startswith("./"):
        normalised = normalised[2:]
    candidate = normalised if normalised.endswith("/") else normalised + "/"
    for prefix in KNOWN_RNAGENESIS_UNTRACKED:
        if candidate == prefix or candidate.startswith(prefix):
            return True
    return False


def _assert_rnagenesis_worktree(porcelain):
    for line in _porcelain_lines(porcelain):
        index_status, worktree_status, path = _split_porcelain(line)
        if index_status == "?" and worktree_status == "?":
            if not _known_rnagenesis_untracked(path):
                raise PhaseBRunnerError(
                    "rnagenesis_untracked_refused",
                    "untracked path is not a known RNAGenesis asset",
                )
            continue
        if index_status not in (" ", "?"):
            raise PhaseBRunnerError("rnagenesis_worktree_dirty", "staged changes are present")
        raise PhaseBRunnerError("rnagenesis_worktree_dirty", "tracked changes are present")


def _git_line(git, repo, args):
    return git(repo, list(args)).strip()


def assert_repository_pins(snapshot, git):
    """Allow a later clean authorisation commit above the implementation commit."""
    implementation_commit = snapshot["executing_implementation_commit"]
    mres_head = _git_line(git, MRES_ROOT, ["rev-parse", "HEAD"])
    mres_branch = _git_line(git, MRES_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"])
    mres_porcelain = git(MRES_ROOT, ["status", "--porcelain=v1"])
    origin_main = _git_line(git, MRES_ROOT, ["rev-parse", "origin/main"])
    if mres_branch != "main":
        raise PhaseBRunnerError("mres_branch_not_main", "MRes repository is not on main")
    if not _is_sha40(mres_head):
        raise PhaseBRunnerError(
            "mres_head_invalid",
            "runtime MRes HEAD is not a 40-character lowercase SHA-1",
        )
    _assert_mres_worktree_clean(mres_porcelain)
    if origin_main != mres_head:
        raise PhaseBRunnerError(
            "mres_origin_main_mismatch",
            "local origin/main does not equal runtime HEAD",
        )
    merge_base = _git_line(git, MRES_ROOT, ["merge-base", implementation_commit, "HEAD"])
    if merge_base != implementation_commit:
        raise PhaseBRunnerError(
            "mres_implementation_not_ancestor",
            "executing_implementation_commit is not an ancestor of runtime HEAD",
        )
    implementation_blob = _git_line(
        git,
        MRES_ROOT,
        ["rev-parse", "{}:{}".format(implementation_commit, RUNNER_RELATIVE)],
    )
    worktree_blob = _git_line(git, MRES_ROOT, ["hash-object", "--", str(RUNNER_PATH)])
    if implementation_blob == "" or implementation_blob != worktree_blob:
        raise PhaseBRunnerError(
            "runner_bytes_mismatch",
            "scripts/b1_phase_b_runner.py is not byte-identical to the implementation commit",
        )
    rna_head = _git_line(git, RNAGENESIS_ROOT, ["rev-parse", "HEAD"])
    rna_branch = _git_line(git, RNAGENESIS_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"])
    rna_porcelain = git(RNAGENESIS_ROOT, ["status", "--porcelain=v1"])
    if rna_branch != RNAGENESIS_BRANCH:
        raise PhaseBRunnerError(
            "rnagenesis_branch_mismatch",
            "RNAGenesis branch is not mres-d1-diffusion-finetune",
        )
    if rna_head != RNAGENESIS_HEAD:
        raise PhaseBRunnerError(
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
            "runner_modified_repository": False,
        },
    }


def assert_not_biological_data_path(path):
    text = str(path).replace("\\", "/")
    base = os.path.basename(text)
    if base in ("ft_train.csv", "ft_validation.csv", "ref.csv", "eval.csv"):
        raise PhaseBRunnerError(
            "biological_data_access_refused",
            "biological sequence data is refused",
        )
    lowered = base.lower()
    if "tokenizer_audit" in lowered or "m3_audit" in lowered or lowered.endswith("_audit.csv"):
        raise PhaseBRunnerError(
            "biological_data_access_refused",
            "M3 audit data is refused",
        )
    for component in text.split("/"):
        if component in PROHIBITED_PATH_COMPONENTS:
            raise PhaseBRunnerError(
                "biological_data_access_refused",
                "biological sequence data is refused",
            )


def assert_cleaner_allowed(path):
    text = os.path.normpath(str(path))
    prohibited = os.path.normpath(str(PROHIBITED_CLEANER))
    if text == prohibited or os.path.basename(text) == "clean_generated_sequences.py":
        raise PhaseBRunnerError(
            "prohibited_cleaner",
            "clean_generated_sequences.py is rejected",
        )


def assert_encdec_selection(relative):
    if "checkpoint-15000" in relative or "checkpoint-30000" in relative:
        raise PhaseBRunnerError(
            "encdec_substitute_rejected",
            "adjacent EncDec subcheckpoint weights are rejected",
        )
    if relative != ENCDEC_RELATIVE:
        raise PhaseBRunnerError(
            "encdec_selection_rejected",
            "EncDec selection is not configs/rnagenesis/autoencoder",
        )


def assert_diffusion_selection(relative):
    normalised = relative.replace("\\", "/").rstrip("/")
    prohibited = "checkpoints/Aptamer/diffusion"
    if normalised == prohibited or normalised.endswith("/" + prohibited):
        raise PhaseBRunnerError(
            "prohibited_diffusion",
            "checkpoints/Aptamer/diffusion is prohibited",
        )
    absolute = os.path.normpath(str(RNAGENESIS_ROOT / normalised))
    if absolute == os.path.normpath(str(PROHIBITED_DIFFUSION)):
        raise PhaseBRunnerError(
            "prohibited_diffusion",
            "checkpoints/Aptamer/diffusion is prohibited",
        )
    if normalised != DIFFUSION_RELATIVE:
        raise PhaseBRunnerError(
            "diffusion_selection_rejected",
            "diffusion selection is not configs/rnagenesis/diffusion",
        )


def verify_asset(asset, lstat, sha256_file):
    if "checkpoint-15000" in asset.relative or "checkpoint-30000" in asset.relative:
        raise PhaseBRunnerError(
            "encdec_substitute_rejected",
            "adjacent EncDec subcheckpoint weights are rejected",
        )
    path = asset.absolute_path()
    assert_not_biological_data_path(path)
    try:
        observed = lstat(path)
    except FileNotFoundError:
        raise PhaseBRunnerError("pinned_file_missing", asset.relative)
    if stat.S_ISLNK(observed.st_mode):
        raise PhaseBRunnerError("pinned_file_symlink", asset.relative)
    if not stat.S_ISREG(observed.st_mode):
        raise PhaseBRunnerError("pinned_file_not_regular", asset.relative)
    if asset.size is not None and observed.st_size != asset.size:
        raise PhaseBRunnerError("pinned_file_size_mismatch", asset.relative)
    digest = sha256_file(path)
    if asset.role == "encdec_weights" and digest in PROHIBITED_SUBSTITUTE_SHA256:
        substitute = PROHIBITED_SUBSTITUTE_SHA256[digest]
        raise PhaseBRunnerError(
            "encdec_substitute_rejected",
            "EncDec weight matches prohibited {}".format(substitute),
        )
    if digest != asset.sha256:
        raise PhaseBRunnerError("pinned_file_hash_mismatch", asset.relative)
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
        raise PhaseBRunnerError("argv_incomplete", "{} is missing".format(flag))
    if index + 1 >= len(argv):
        raise PhaseBRunnerError("argv_incomplete", "{} is missing a value".format(flag))
    return argv[index + 1]


def assert_argv_prohibitions(argv):
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
        raise PhaseBRunnerError("argv_type", "argv must be a list of strings")
    for option in PROHIBITED_ARGV_OPTIONS:
        if option in argv:
            raise PhaseBRunnerError("prohibited_generation_option", option)
    for element in argv:
        normalised = element.replace("\\", "/")
        for marker in PROHIBITED_PATH_MARKERS:
            if marker in normalised:
                raise PhaseBRunnerError("prohibited_generation_path", marker)
        for component in normalised.split("/"):
            if component in PROHIBITED_PATH_COMPONENTS:
                raise PhaseBRunnerError("prohibited_generation_path", component)
    if "--do_sample" not in argv:
        raise PhaseBRunnerError("sampling_not_enabled", "sampling must be enabled")
    if "--guidance" in argv:
        raise PhaseBRunnerError("guidance_not_disabled", "--guidance was passed")


def invocation_mid_folder(invocation):
    return "invocation_{:02d}".format(invocation["invocation_index"])


def invocation_remark(invocation):
    return "_phaseB_i{:02d}_seed{}_cap{}".format(
        invocation["invocation_index"],
        invocation["seed"],
        invocation["max_seq_len"],
    )


def predicted_generation_filename(remark):
    return "seqs_wo_guidance_top_p=0.95_2_16{}.txt".format(remark)


def predicted_generation_path(evidence_dir, invocation):
    return (
        Path(evidence_dir)
        / "rnagenesis_generation_output"
        / invocation_mid_folder(invocation)
        / predicted_generation_filename(invocation_remark(invocation))
    )


def build_generation_argv(invocation, evidence_dir, guidance_enabled):
    if guidance_enabled is not False:
        raise PhaseBRunnerError("guidance_not_disabled", "guidance must be disabled")
    assert_encdec_selection(ENCDEC_RELATIVE)
    assert_diffusion_selection(DIFFUSION_RELATIVE)
    assert_cleaner_allowed(APPROVED_CLEANER)
    if invocation["max_seq_len"] != invocation["requested_biological_length"] + 1:
        raise PhaseBRunnerError("phase_b_plan_invalid", "max_seq_len is not length + 1")
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
        invocation_remark(invocation),
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
        raise PhaseBRunnerError("encdec_selection_rejected", "EncDec argv drifted")
    if _argv_value(argv, "--dm_file") != DIFFUSION_RELATIVE:
        raise PhaseBRunnerError("diffusion_selection_rejected", "diffusion argv drifted")
    if _argv_value(argv, "--device") != "cuda:0":
        raise PhaseBRunnerError("cpu_fallback_prohibited", "device is not cuda:0")
    if argv.count("--max_seq_len") != 1:
        raise PhaseBRunnerError("phase_b_plan_invalid", "an invocation must carry exactly one max_seq_len")
    return argv


def _path_within(path, root):
    try:
        return os.path.commonpath(
            [os.path.normpath(path), os.path.normpath(root)]
        ) == os.path.normpath(root)
    except ValueError:
        return False


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
    }


def assert_runtime_isolation(evidence_dir, realpath=None):
    if realpath is None:
        realpath = os.path.realpath
    evidence = os.path.abspath(os.path.normpath(str(evidence_dir)))
    if not evidence.startswith("/"):
        raise PhaseBRunnerError("runtime_cache_not_isolated", "evidence directory is not absolute")
    resolved_evidence = realpath(evidence)
    resolved_rna = realpath(str(RNAGENESIS_ROOT))
    if resolved_evidence != evidence:
        raise PhaseBRunnerError("runtime_cache_not_isolated", "evidence directory path is not stable")
    if _path_within(resolved_evidence, resolved_rna):
        raise PhaseBRunnerError(
            "runtime_cache_not_isolated",
            "evidence directory resolves inside RNAGenesis",
        )
    rna_root = os.path.normpath(str(RNAGENESIS_ROOT))
    rna_cache = os.path.normpath(os.path.join(rna_root, ".cache"))
    paths = runtime_isolation_paths(evidence)
    for path in paths.values():
        if not os.path.isabs(path) or _path_within(os.path.normpath(path), rna_root):
            raise PhaseBRunnerError(
                "runtime_cache_not_isolated",
                "runtime cache path is inside RNAGenesis",
            )
        resolved = realpath(path)
        if not _path_within(resolved, resolved_evidence):
            raise PhaseBRunnerError(
                "runtime_cache_not_isolated",
                "runtime cache escaped the evidence directory",
            )
        if _path_within(resolved, resolved_rna) or os.path.normpath(resolved) == rna_cache:
            raise PhaseBRunnerError(
                "runtime_cache_not_isolated",
                "runtime cache resolves to an RNAGenesis cache",
            )
    return paths


def build_child_environment(parent, evidence_dir, physical_gpu, realpath=None):
    assert_cuda_environment(parent, physical_gpu)
    original_items = list(parent.items())
    child = dict(parent)
    child.update(OFFLINE_CONTROLS)
    child["PYTHONDONTWRITEBYTECODE"] = "1"
    child["CUDA_VISIBLE_DEVICES"] = str(physical_gpu)
    child["CUDA_DEVICE_ORDER"] = CUDA_DEVICE_ORDER
    child.update(assert_runtime_isolation(evidence_dir, realpath))
    if list(parent.items()) != original_items:
        raise PhaseBRunnerError("parent_environment_mutated", "parent environment was modified")
    assert_cuda_environment(child, physical_gpu)
    return child


def build_subprocess_invocation(invocation, evidence_dir, parent_env, physical_gpu, realpath=None):
    argv = build_generation_argv(invocation, evidence_dir, guidance_enabled=False)
    return {
        "argv": argv,
        "cwd": GENERATION_CWD,
        "env": build_child_environment(parent_env, evidence_dir, physical_gpu, realpath),
        "shell": False,
    }


def physical_gpu_query_argv(physical_gpu):
    if type(physical_gpu) is not int or physical_gpu not in SUPPORTED_PHYSICAL_GPUS:
        raise PhaseBRunnerError(
            "unsupported_physical_gpu",
            "physical GPU must be exactly 0 or 1",
        )
    return [
        "nvidia-smi",
        "--query-gpu=index,uuid,pci.bus_id,name,memory.total,compute_mode",
        "--format=csv,noheader,nounits",
        "-i",
        str(physical_gpu),
    ]


def cuda_probe_argv():
    if PINNED_PYTHON != "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python":
        raise PhaseBRunnerError(
            "python_interpreter_rejected",
            "generation interpreter is not the pinned rnagenesis-h200 Python",
        )
    return [PINNED_PYTHON, "-c", CUDA_PROBE_SOURCE]


def build_cuda_probe_command(child_env, physical_gpu):
    assert_cuda_environment(child_env, physical_gpu)
    return {
        "argv": cuda_probe_argv(),
        "cwd": GENERATION_CWD,
        "env": child_env,
        "shell": False,
    }


def parse_gpu_identity(text, physical_gpu):
    lines = [line for line in text.splitlines() if line.strip() != ""]
    if len(lines) != 1:
        raise PhaseBRunnerError(
            "gpu_identity_mismatch",
            "physical GPU query did not return one device",
        )
    parts = [part.strip() for part in lines[0].split(",")]
    if len(parts) != 6:
        raise PhaseBRunnerError("gpu_identity_mismatch", "physical GPU query was incomplete")
    index_text, uuid, pci_bus_id, name, memory, compute_mode = parts
    if index_text != str(physical_gpu) or uuid == "" or uuid.upper() == "N/A":
        raise PhaseBRunnerError(
            "gpu_identity_mismatch",
            "physical GPU query identity does not match the selected device",
        )
    if (
        pci_bus_id == ""
        or pci_bus_id.upper() == "N/A"
        or name == ""
        or memory == ""
        or compute_mode == ""
    ):
        raise PhaseBRunnerError("gpu_identity_mismatch", "physical GPU identity was incomplete")
    return {
        "index": physical_gpu,
        "uuid": uuid,
        "pci_bus_id": pci_bus_id,
        "name": name,
        "memory": memory,
        "compute_mode": compute_mode,
        "physical_gpu": physical_gpu,
        "cpu_fallback": False,
    }


def parse_cuda_probe_json(text):
    if not isinstance(text, str) or text.strip() == "":
        raise PhaseBRunnerError("cuda_probe_malformed", "CUDA probe did not return JSON")
    try:
        payload = json.loads(text)
    except Exception:
        raise PhaseBRunnerError("cuda_probe_malformed", "CUDA probe did not return JSON")
    if not isinstance(payload, dict) or any(key not in payload for key in CUDA_PROBE_KEYS):
        raise PhaseBRunnerError("cuda_probe_malformed", "CUDA probe JSON is incomplete")
    return payload


def _resolved_python(path, resolve_python):
    if not isinstance(path, str) or path.strip() == "":
        raise PhaseBRunnerError(
            "cuda_probe_mismatch",
            "CUDA probe interpreter did not match the pinned Python",
        )
    return resolve_python(path)


def validate_cuda_probe(payload, physical_identity, physical_gpu, resolve_python=None):
    if resolve_python is None:
        resolve_python = os.path.realpath
    if type(payload.get("cuda_available")) is not bool:
        raise PhaseBRunnerError("cuda_probe_malformed", "CUDA probe availability was not a boolean")
    if payload["cuda_available"] is not True:
        raise PhaseBRunnerError("cuda_unavailable", "Torch CUDA is not available")
    if type(payload.get("device_count")) is not int:
        raise PhaseBRunnerError("cuda_probe_malformed", "CUDA probe device count was not an integer")
    if payload["device_count"] == 0:
        raise PhaseBRunnerError("cuda_device_count", "expected exactly one visible CUDA device")
    if payload["device_count"] != 1:
        raise PhaseBRunnerError("cuda_device_count", "expected exactly one visible CUDA device")
    if payload.get("allocation_ok") is not True or payload.get("logical_device_index") != 0:
        raise PhaseBRunnerError(
            "cuda_allocation_failed",
            "logical CUDA device 0 could not allocate a tensor",
        )
    if payload.get("logical_device") != "cuda:0" or payload.get("logical_device_confirmed") is not True:
        raise PhaseBRunnerError("cuda_probe_mismatch", "logical CUDA device 0 was not confirmed")
    if payload.get("cuda_visible_devices") != str(physical_gpu):
        raise PhaseBRunnerError(
            "cuda_probe_mismatch",
            "CUDA probe did not observe the selected physical GPU",
        )
    if payload.get("cuda_device_order") != CUDA_DEVICE_ORDER:
        raise PhaseBRunnerError(
            "cuda_probe_mismatch",
            "CUDA probe did not observe CUDA_DEVICE_ORDER={}".format(CUDA_DEVICE_ORDER),
        )
    if (
        type(physical_identity.get("index")) is not int
        or physical_identity.get("index") != physical_gpu
        or physical_identity.get("physical_gpu") != physical_gpu
        or physical_identity.get("cpu_fallback") is not False
    ):
        raise PhaseBRunnerError(
            "gpu_identity_mismatch",
            "physical GPU identity was not confirmed",
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
        raise PhaseBRunnerError("gpu_identity_mismatch", "physical GPU identity was incomplete")
    device_name = payload.get("device_name")
    if not isinstance(device_name, str) or device_name.strip() == "":
        raise PhaseBRunnerError("cuda_probe_malformed", "CUDA probe device name was missing")
    if device_name != physical_identity["name"]:
        raise PhaseBRunnerError(
            "gpu_identity_mismatch",
            "Torch device name did not match the selected physical GPU",
        )
    pinned_resolved = _resolved_python(PINNED_PYTHON, resolve_python)
    observed_resolved = _resolved_python(payload.get("python_executable"), resolve_python)
    if observed_resolved != pinned_resolved:
        raise PhaseBRunnerError(
            "cuda_probe_mismatch",
            "CUDA probe interpreter did not match the pinned Python",
        )
    python_version = payload.get("python_version")
    torch_version = payload.get("torch_version")
    if not isinstance(python_version, str) or python_version.strip() == "":
        raise PhaseBRunnerError("cuda_probe_malformed", "Python version was missing")
    if not isinstance(torch_version, str) or torch_version.strip() == "":
        raise PhaseBRunnerError("cuda_probe_malformed", "Torch version was missing")
    packages = payload.get("packages")
    if not isinstance(packages, dict) or set(packages) != set(GENERATION_CRITICAL_DISTRIBUTIONS):
        raise PhaseBRunnerError("cuda_probe_malformed", "package versions were missing")
    recorded = {}
    for name in GENERATION_CRITICAL_DISTRIBUTIONS:
        version = packages.get(name)
        if not isinstance(version, str) or version.strip() == "":
            raise PhaseBRunnerError("cuda_probe_malformed", "package versions were missing")
        recorded[name] = version
    if recorded["torch"] != torch_version:
        raise PhaseBRunnerError("cuda_probe_malformed", "package versions were missing")
    return {
        "index": physical_gpu,
        "physical_gpu": physical_gpu,
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
        "cuda_visible_devices": str(physical_gpu),
        "cuda_device_order": CUDA_DEVICE_ORDER,
    }


def preflight_gpu(child_env, physical_gpu, query_text, probe_text, resolve_python=None):
    assert_cuda_environment(child_env, physical_gpu)
    identity = parse_gpu_identity(query_text(), physical_gpu)
    if identity.get("logical_device_confirmed") is True:
        raise PhaseBRunnerError(
            "cuda_probe_mismatch",
            "physical GPU query cannot confirm the logical CUDA device",
        )
    payload = parse_cuda_probe_json(probe_text())
    confirmed = validate_cuda_probe(payload, identity, physical_gpu, resolve_python)
    identity.update(confirmed)
    if identity["physical_gpu"] != physical_gpu or identity["index"] != physical_gpu:
        raise PhaseBRunnerError(
            "gpu_identity_mismatch",
            "manifest physical GPU does not match the selected device",
        )
    return identity


def default_query_gpu_text(physical_gpu):
    completed = subprocess.run(
        physical_gpu_query_argv(physical_gpu),
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or completed.stdout.strip() == "":
        raise PhaseBRunnerError("gpu_identity_mismatch", "physical GPU query failed")
    return completed.stdout


def default_cuda_probe(child_env, physical_gpu):
    command = build_cuda_probe_command(child_env, physical_gpu)
    if command["shell"] is not False or command["argv"][0] != PINNED_PYTHON:
        raise PhaseBRunnerError(
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
        raise PhaseBRunnerError("cuda_probe_failed", "CUDA probe subprocess failed")
    return completed.stdout


def default_gpu_preflight(child_env, physical_gpu, gates_passed=False):
    if gates_passed is not True:
        raise PhaseBRunnerError(
            "gpu_preflight_before_authorisation",
            "GPU preflight is refused before document and authorisation gates",
        )
    return preflight_gpu(
        child_env,
        physical_gpu,
        lambda: default_query_gpu_text(physical_gpu),
        lambda: default_cuda_probe(child_env, physical_gpu),
    )


def production_gpu_preflight(child_env, physical_gpu):
    return default_gpu_preflight(child_env, physical_gpu, gates_passed=True)


def termination_observation(removed_prefix, removed_suffix):
    """Record an observed EOS marker without classifying it as early EOS.

    A leading or trailing ``2`` is ``eos_marker_observed``. Cleaned length
    is not consulted here, so an exact-length output can still carry the marker.
    """
    boundary = "{}{}".format(removed_prefix, removed_suffix)
    if "2" in boundary:
        return EOS_OBSERVED
    return TERMINATION_NOT_OBSERVABLE


def early_eos_event(attempt):
    """True only for a valid cleaned output that is shorter than requested.

    An EOS marker on an exact-length output is not early EOS. An invalid
    output stays invalid and is not reclassified as an early-EOS observation.
    """
    if attempt.get("termination_observation") != EOS_OBSERVED:
        return False
    if attempt.get("validity") is not True:
        return False
    requested = attempt.get("requested_biological_length")
    cleaned_length = attempt.get("cleaned_length")
    if type(requested) is not int or type(cleaned_length) is not int:
        return False
    return cleaned_length < requested


def adapt_audited_line(raw, audited, invocation, attempt_within_length):
    prefix = audited["removed_prefix"]
    suffix = audited["removed_suffix"]
    accepted = audited["accepted"] is True
    rejection_reason = None if accepted else audited["reason"]
    requested = invocation["requested_biological_length"]
    cleaned = audited["cleaned"]
    record = {
        "invocation_index": invocation["invocation_index"],
        "attempt_index": invocation["invocation_index"] * ATTEMPTS_PER_LENGTH + attempt_within_length,
        "attempt_within_length": attempt_within_length,
        "requested_biological_length": requested,
        "max_seq_len": invocation["max_seq_len"],
        "seed": invocation["seed"],
        "raw_decoded_text": raw,
        "raw_length": len(raw),
        "leading_boundary_marker_run": prefix,
        "trailing_boundary_marker_run": suffix,
        "cleaned_sequence": cleaned,
        "cleaned_length": len(cleaned),
        "validity": accepted,
        "rejection_reason": rejection_reason,
        "termination_observation": termination_observation(prefix, suffix),
        "exact_length": accepted and len(cleaned) == requested,
    }
    if tuple(record) != ATTEMPT_KEYS:
        raise PhaseBRunnerError("attempt_record_invalid", "attempt fields drifted")
    return record


def audit_invocation_output(text, split_raw_records, audit_line, invocation):
    lines = split_raw_records(text)
    if len(lines) != ATTEMPTS_PER_LENGTH:
        raise PhaseBRunnerError(
            "invocation_output_line_count",
            "expected 16 output lines and observed {}".format(len(lines)),
        )
    records = []
    for attempt_within_length, raw in enumerate(lines):
        audited = audit_line(attempt_within_length + 1, raw)
        if audited.get("raw") != raw:
            raise PhaseBRunnerError(
                "audit_raw_mismatch",
                "cleaner raw field does not match the decoded line",
            )
        records.append(adapt_audited_line(raw, audited, invocation, attempt_within_length))
    return records


def _exact_hit_rate(exact_hits, valid_outputs):
    if valid_outputs == 0:
        return 0.0
    return exact_hits / valid_outputs


def _rate(numerator, denominator):
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _numeric_distribution(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [{"value": value, "count": counts[value]} for value in sorted(counts)]


def _text_distribution(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [{"value": value, "count": counts[value]} for value in sorted(counts)]


def phase_b_diagnostics(attempts):
    """Report provisional length diagnostics. Do not change eligibility.

    ``eos_marker_observed`` counts every attempt whose termination
    observation is the EOS marker. ``early_eos`` counts only the subset
    that is also a valid cleaned output strictly shorter than requested.
    Both rates use raw attempts, so invalid outputs stay in the denominator.
    """
    by_length = {}
    valid_sequences = []
    valid = 0
    invalid = 0
    exact = 0
    parsed = 0
    eos_marker_total = 0
    early_eos_total = 0
    for attempt in attempts:
        length = attempt["requested_biological_length"]
        bucket = by_length.setdefault(
            length,
            {
                "raw_attempts": 0,
                "parsed_outputs": 0,
                "valid_outputs": 0,
                "invalid_outputs": 0,
                "exact_hits": 0,
                "eos_marker_observed_count": 0,
                "early_eos_count": 0,
                "cleaned_lengths": [],
                "leading_runs": [],
                "trailing_runs": [],
                "valid_sequences": [],
            },
        )
        bucket["raw_attempts"] += 1
        if isinstance(attempt.get("raw_decoded_text"), str):
            parsed += 1
            bucket["parsed_outputs"] += 1
        is_valid = attempt.get("validity") is True
        if is_valid:
            valid += 1
            bucket["valid_outputs"] += 1
            sequence = attempt.get("cleaned_sequence")
            bucket["valid_sequences"].append(sequence)
            valid_sequences.append(sequence)
            if attempt.get("exact_length") is True or (
                attempt.get("cleaned_length") == length and attempt.get("exact_length") is not False
            ):
                if attempt.get("cleaned_length") == length:
                    exact += 1
                    bucket["exact_hits"] += 1
        else:
            invalid += 1
            bucket["invalid_outputs"] += 1
        bucket["cleaned_lengths"].append(attempt.get("cleaned_length"))
        bucket["leading_runs"].append(attempt.get("leading_boundary_marker_run", ""))
        bucket["trailing_runs"].append(attempt.get("trailing_boundary_marker_run", ""))
        if attempt.get("termination_observation") == EOS_OBSERVED:
            bucket["eos_marker_observed_count"] += 1
            eos_marker_total += 1
        if early_eos_event(attempt):
            bucket["early_eos_count"] += 1
            early_eos_total += 1
    per_length = []
    below_floor = 0
    for length in sorted(by_length):
        bucket = by_length[length]
        rate = _exact_hit_rate(bucket["exact_hits"], bucket["valid_outputs"])
        if rate < PROVISIONAL_PER_LENGTH_FLOOR:
            below_floor += 1
        unique_valid = len(set(bucket["valid_sequences"]))
        per_length.append(
            {
                "requested_biological_length": length,
                "raw_attempts": bucket["raw_attempts"],
                "parsed_outputs": bucket["parsed_outputs"],
                "valid_outputs": bucket["valid_outputs"],
                "invalid_outputs": bucket["invalid_outputs"],
                "unique_valid_outputs": unique_valid,
                "duplicate_outputs": bucket["valid_outputs"] - unique_valid,
                "exact_hits": bucket["exact_hits"],
                "exact_hit_rate": rate,
                "eos_marker_observed_count": bucket["eos_marker_observed_count"],
                "eos_marker_observed_rate": _rate(
                    bucket["eos_marker_observed_count"],
                    bucket["raw_attempts"],
                ),
                "early_eos_count": bucket["early_eos_count"],
                "early_eos_rate": _rate(bucket["early_eos_count"], bucket["raw_attempts"]),
                "cleaned_length_distribution": _numeric_distribution(bucket["cleaned_lengths"]),
                "leading_boundary_distribution": _text_distribution(bucket["leading_runs"]),
                "trailing_boundary_distribution": _text_distribution(bucket["trailing_runs"]),
            }
        )
    unique_valid = len(set(valid_sequences))
    overall_rate = _exact_hit_rate(exact, valid)
    return {
        "role": "provisional_diagnostic_not_an_eligibility_gate",
        "provisional_until_human_review": True,
        "raw_attempts": len(attempts),
        "parsed_outputs": parsed,
        "valid_outputs": valid,
        "invalid_outputs": invalid,
        "unique_valid_outputs": unique_valid,
        "duplicate_outputs": valid - unique_valid,
        "exact_hits": exact,
        "valid_fraction": _rate(valid, len(attempts)),
        "overall_exact_hit_rate": overall_rate,
        "exact_hit_rate_denominator": "valid_outputs",
        "eos_marker_observed_count": eos_marker_total,
        "eos_marker_observed_rate": _rate(eos_marker_total, len(attempts)),
        "early_eos_count": early_eos_total,
        "early_eos_rate": _rate(early_eos_total, len(attempts)),
        "eos_marker_and_early_eos_rate_denominator": "raw_attempts",
        "invalid_outputs_remain_in_raw_denominator": True,
        "duplicate_outputs_remain_in_valid_denominator": True,
        "lengths_below_provisional_0_50_floor": below_floor,
        "provisional_aggregate_0_90_diagnostic_reached": overall_rate >= PROVISIONAL_AGGREGATE,
        "per_length": per_length,
        "complete_per_length_table": [row["requested_biological_length"] for row in per_length]
        == list(FROZEN_TRAIN_LENGTHS),
        "provisional_thresholds": {
            "overall_exact_hit_threshold": PROVISIONAL_AGGREGATE,
            "per_length_exact_hit_threshold": PROVISIONAL_PER_LENGTH_FLOOR,
            "applied_as_b1_eligibility_gate": False,
        },
        "final_production_mapping_declared": False,
        "rejection_or_resampling_algorithm_declared": False,
        "b1_eligibility": "not_declared",
        "b1_eligible": False,
        "development_pool_authorised": False,
        "development_pool_executed": False,
        "m4_complete": False,
        "eligibility_decision": "not_made",
    }


def canonical_json_bytes(document):
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True)
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def project_attempt(record, keys):
    if tuple(record) != ATTEMPT_KEYS:
        raise PhaseBRunnerError("attempt_record_invalid", "attempt fields drifted")
    projected = {}
    for key in keys:
        if key not in record:
            raise PhaseBRunnerError("attempt_record_invalid", "attempt fields drifted")
        projected[key] = record[key]
    return projected


def serialize_jsonl(records, keys):
    lines = []
    for record in records:
        projected = project_attempt(record, keys)
        lines.append(
            json.dumps(projected, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        )
    if not lines:
        return b""
    return ("\n".join(lines) + "\n").encode("utf-8")


def _assert_attempt_matches_plan(attempt, invocation, position):
    if attempt["attempt_within_length"] != position:
        raise PhaseBRunnerError(
            "attempt_plan_mismatch",
            "attempt_within_length does not match the invocation plan",
        )
    expected_index = invocation["invocation_index"] * ATTEMPTS_PER_LENGTH + position
    if attempt["attempt_index"] != expected_index:
        raise PhaseBRunnerError(
            "attempt_plan_mismatch",
            "attempt_index does not match the invocation plan",
        )
    checks = (
        ("invocation_index", invocation["invocation_index"]),
        ("requested_biological_length", invocation["requested_biological_length"]),
        ("max_seq_len", invocation["max_seq_len"]),
        ("seed", invocation["seed"]),
    )
    for key, expected in checks:
        if attempt[key] != expected:
            raise PhaseBRunnerError(
                "attempt_plan_mismatch",
                "attempt {} does not match the invocation plan".format(key),
            )
    if attempt["max_seq_len"] != attempt["requested_biological_length"] + 1:
        raise PhaseBRunnerError("attempt_plan_mismatch", "max_seq_len is not length + 1")
    if attempt["exact_length"] is True and attempt["validity"] is not True:
        raise PhaseBRunnerError(
            "attempt_plan_mismatch",
            "an invalid attempt cannot be an exact-length hit",
        )


def _assert_complete_attempts(attempts, plan):
    if len(attempts) != TOTAL_ATTEMPTS:
        raise PhaseBRunnerError(
            "success_manifest_refused",
            "incomplete attempt ledger cannot be a success manifest",
        )
    if not isinstance(plan, list) or len(plan) != INVOCATION_COUNT:
        raise PhaseBRunnerError("success_manifest_refused", "the frozen invocation plan is unavailable")
    grouped = {}
    for attempt in attempts:
        if tuple(attempt) != ATTEMPT_KEYS:
            raise PhaseBRunnerError("attempt_record_invalid", "attempt fields drifted")
        grouped.setdefault(attempt["invocation_index"], []).append(attempt)
    if set(grouped) != set(range(INVOCATION_COUNT)):
        raise PhaseBRunnerError("success_manifest_refused", "success requires 89 invocations")
    plan_by_index = {}
    for invocation in plan:
        index = invocation["invocation_index"]
        if index in plan_by_index:
            raise PhaseBRunnerError("attempt_plan_mismatch", "the invocation plan repeats an index")
        plan_by_index[index] = invocation
    if set(plan_by_index) != set(range(INVOCATION_COUNT)):
        raise PhaseBRunnerError("success_manifest_refused", "success requires 89 invocations")
    seen = []
    for invocation_index in range(INVOCATION_COUNT):
        invocation = plan_by_index[invocation_index]
        group = grouped[invocation_index]
        if len(group) != ATTEMPTS_PER_LENGTH:
            raise PhaseBRunnerError(
                "success_manifest_refused",
                "invocation {} does not contain 16 attempts".format(invocation_index),
            )
        ordered = sorted(group, key=lambda item: item["attempt_within_length"])
        for position, attempt in enumerate(ordered):
            _assert_attempt_matches_plan(attempt, invocation, position)
            seen.append(attempt["attempt_index"])
    if seen != list(range(TOTAL_ATTEMPTS)):
        raise PhaseBRunnerError(
            "attempt_plan_mismatch",
            "attempt indexes are not the frozen 1424-attempt plan",
        )


def file_content_record(path, data):
    if not isinstance(data, (bytes, bytearray)):
        raise PhaseBRunnerError("evidence_hash_invalid", "hash input must be bytes")
    payload = bytes(data)
    return {"path": str(path), "byte_count": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def _contains_key(value, key):
    if isinstance(value, dict):
        if key in value:
            return True
        return any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def manifest_hashes(context):
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
        raise PhaseBRunnerError(
            "manifest_hash_recursive",
            "a manifest body must not contain its own hash",
        )
    return hashes


def manifest_progress(context):
    return {
        "completed_invocation_indexes": list(context.get("completed_invocation_indexes") or []),
        "attempt_count": context.get("attempt_count") or 0,
        "command_count": len(context.get("commands") or []),
        "raw_output_count": len(context.get("raw_outputs") or []),
    }


def _authorization_view(snapshot):
    if not isinstance(snapshot, dict):
        snapshot = {}
    keys = (
        "authorisation_id",
        "authorisation_active",
        "activation_status",
        "consumed",
        "authorises_b1_phase_b",
        "physical_gpu",
        "executing_implementation_commit",
        "condition",
        "phase",
        "evidence_directory",
    )
    return {key: snapshot.get(key) for key in keys}


def _child_environment_controls(evidence_dir, physical_gpu):
    controls = {
        "CUDA_VISIBLE_DEVICES": str(physical_gpu),
        "CUDA_DEVICE_ORDER": CUDA_DEVICE_ORDER,
        "physical_gpu": physical_gpu,
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
    physical_gpu,
):
    document = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "status": status,
        "experiment_id": None if not isinstance(config, dict) else config.get("experiment_id"),
        "condition_identifier": CONDITION_LABEL,
        "phase": "B",
        "purpose": "evaluate_candidate_mapping_across_frozen_train_lengths",
        "candidate_mapping_status": CANDIDATE_STATUS,
        "final_production_mapping_declared": False,
        "rejection_or_resampling_algorithm_declared": False,
        "b1_eligibility": "not_declared",
        "b1_eligible": False,
        "eligibility_decision": "not_made",
        "m4_complete": False,
        "development_pool_authorised": False,
        "development_pool_executed": False,
        "phase_a_authorisation_accepted_for_phase_b": False,
        "authorization": _authorization_view(snapshot),
        "authorization_runtime_commit": None
        if not isinstance(provenance, dict) or not isinstance(provenance.get("mres"), dict)
        else provenance["mres"].get("authorization_commit"),
        "selected_physical_gpu": physical_gpu,
        "repository_provenance": provenance,
        "progress": progress,
        "pinned_inputs": pins,
        "commands": commands,
        "child_environment_controls": _child_environment_controls(evidence_dir, physical_gpu),
        "final_raw_output_verification": raw_output_verification
        if isinstance(raw_output_verification, dict)
        else {"passed": False, "file_count": 0},
        "gpu_identity": gpu,
        "invocation_schedule": plan,
        "access_declaration": ACCESS_DECLARATION,
        "sequence_only_diagnostics": diagnostics,
        "hashes": hashes,
        "failure": failure,
        "timestamps": timestamps,
        "hostname": hostname,
    }
    if _contains_key(document, "manifest_sha256"):
        raise PhaseBRunnerError(
            "manifest_hash_recursive",
            "a manifest body must not contain its own hash",
        )
    return document


def _assert_diagnostics_do_not_authorise(diagnostics):
    if not isinstance(diagnostics, dict):
        raise PhaseBRunnerError("success_manifest_refused", "diagnostics are unavailable")
    checks = (
        ("eligibility_decision", "not_made"),
        ("b1_eligibility", "not_declared"),
        ("b1_eligible", False),
        ("final_production_mapping_declared", False),
        ("rejection_or_resampling_algorithm_declared", False),
        ("development_pool_authorised", False),
        ("development_pool_executed", False),
        ("m4_complete", False),
    )
    for key, expected in checks:
        if diagnostics.get(key) != expected:
            raise PhaseBRunnerError(
                "success_manifest_refused",
                "provisional diagnostics must not change eligibility or authorisation",
            )
    thresholds = diagnostics.get("provisional_thresholds")
    if not isinstance(thresholds, dict) or thresholds.get("applied_as_b1_eligibility_gate") is not False:
        raise PhaseBRunnerError(
            "success_manifest_refused",
            "provisional length thresholds are not eligibility gates",
        )
    if diagnostics.get("raw_attempts") != TOTAL_ATTEMPTS:
        raise PhaseBRunnerError("success_manifest_refused", "diagnostics do not cover 1424 attempts")
    per_length = diagnostics.get("per_length")
    if not isinstance(per_length, list) or len(per_length) != INVOCATION_COUNT:
        raise PhaseBRunnerError("success_manifest_refused", "the per-length table is incomplete")
    observed = [row.get("requested_biological_length") for row in per_length]
    if observed != list(FROZEN_TRAIN_LENGTHS):
        raise PhaseBRunnerError("success_manifest_refused", "the per-length table is not the frozen list")
    if type(diagnostics.get("provisional_aggregate_0_90_diagnostic_reached")) is not bool:
        raise PhaseBRunnerError("success_manifest_refused", "aggregate diagnostic was not reported")
    if type(diagnostics.get("lengths_below_provisional_0_50_floor")) is not int:
        raise PhaseBRunnerError("success_manifest_refused", "per-length floor count was not reported")


def build_success_manifest(context):
    attempts = context["attempts"]
    _assert_complete_attempts(attempts, context.get("plan"))
    diagnostics = context["diagnostics"]
    _assert_diagnostics_do_not_authorise(diagnostics)
    physical_gpu = context["selected_physical_gpu"]
    gpu = context["gpu"]
    snapshot = context["snapshot"]
    if (
        type(physical_gpu) is not int
        or gpu.get("physical_gpu") != physical_gpu
        or gpu.get("index") != physical_gpu
        or snapshot.get("physical_gpu") != physical_gpu
        or gpu.get("cuda_visible_devices") != str(physical_gpu)
        or gpu.get("logical_device") != "cuda:0"
        or gpu.get("logical_device_confirmed") is not True
    ):
        raise PhaseBRunnerError(
            "gpu_identity_mismatch",
            "manifest physical GPU does not match the selected device",
        )
    progress = manifest_progress(context)
    if progress["completed_invocation_indexes"] != list(range(INVOCATION_COUNT)):
        raise PhaseBRunnerError("success_manifest_refused", "success requires 89 completed invocations")
    if progress["attempt_count"] != TOTAL_ATTEMPTS or progress["raw_output_count"] != INVOCATION_COUNT:
        raise PhaseBRunnerError(
            "success_manifest_refused",
            "success requires 1424 attempts and 89 raw outputs",
        )
    raw_hash = context.get("raw_ledger_sha256")
    audited_hash = context.get("audited_ledger_sha256")
    if not raw_hash or not audited_hash or raw_hash == audited_hash:
        raise PhaseBRunnerError(
            "success_manifest_refused",
            "raw and audited ledger hashes must differ",
        )
    document = _identity_document(
        status="complete",
        config=context["config"],
        snapshot=snapshot,
        provenance=context["provenance"],
        pins=context["pins"],
        commands=context["commands"],
        gpu=gpu,
        plan=context["plan"],
        diagnostics=diagnostics,
        hashes=manifest_hashes(context),
        failure=None,
        timestamps=context["timestamps"],
        hostname=context["hostname"],
        progress=progress,
        evidence_dir=context.get("output_dir"),
        raw_output_verification=context.get("final_raw_output_verification"),
        physical_gpu=physical_gpu,
    )
    verification = document["final_raw_output_verification"]
    if verification.get("passed") is not True or verification.get("file_count") != INVOCATION_COUNT:
        raise PhaseBRunnerError(
            "success_manifest_refused",
            "final raw-output verification did not pass",
        )
    return document


def build_failure_manifest(context, error):
    physical_gpu = context.get("selected_physical_gpu")
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
            "completed_invocation_indexes": list(context.get("completed_invocation_indexes") or []),
            "attempt_count": context.get("attempt_count") or 0,
            "raw_outputs": list(context.get("raw_outputs") or []),
        },
        timestamps=context.get("timestamps") or {},
        hostname=context.get("hostname"),
        progress=manifest_progress(context),
        evidence_dir=context.get("output_dir"),
        raw_output_verification=context.get("final_raw_output_verification"),
        physical_gpu=physical_gpu,
    )
    document["status"] = "failed"
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
                raise PhaseBRunnerError("evidence_write_failed", "short write")
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
    assert_not_biological_data_path(path)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_read_bytes(path):
    assert_not_biological_data_path(path)
    with open(path, "rb") as handle:
        return handle.read()


def default_git(repo, args):
    argv = ["git", "-C", str(repo)]
    argv.extend(list(args))
    completed = subprocess.run(argv, shell=False, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise PhaseBRunnerError("git_pin_failed", completed.stderr.strip() or "git pin command failed")
    return completed.stdout


def default_subprocess_run(argv, cwd, env, shell=False):
    if shell is not False:
        raise PhaseBRunnerError("shell_prohibited", "subprocess shell must stay false")
    if not isinstance(argv, list) or not argv or argv[0] != PINNED_PYTHON:
        raise PhaseBRunnerError(
            "python_interpreter_rejected",
            "generation interpreter is not the pinned rnagenesis-h200 Python",
        )
    assert_argv_prohibitions(argv)
    if cwd != GENERATION_CWD:
        raise PhaseBRunnerError("generation_cwd_rejected", "generation working directory is not RNAGenesis")
    completed = subprocess.run(argv, cwd=cwd, env=env, shell=False, check=False, capture_output=True)
    if completed.returncode != 0:
        raise PhaseBRunnerError(
            "generation_process_failed",
            "generation.py exited {}".format(completed.returncode),
        )
    return completed


def verified_cleaner_source(read_bytes):
    assert_cleaner_allowed(APPROVED_CLEANER)
    try:
        data = read_bytes(APPROVED_CLEANER)
    except PhaseBRunnerError:
        raise
    except OSError as exc:
        raise normalize_evidence_error(exc)
    if not isinstance(data, (bytes, bytearray)):
        raise PhaseBRunnerError("cleaner_import_failed", "approved cleaner source bytes are required")
    payload = bytes(data)
    if hashlib.sha256(payload).hexdigest() != CLEANER_SHA256:
        raise PhaseBRunnerError("pinned_file_hash_mismatch", "scripts/audit_generation_output.py")
    return payload


def load_cleaner_from_verified_source(source_bytes):
    assert_cleaner_allowed(APPROVED_CLEANER)
    if not isinstance(source_bytes, (bytes, bytearray)):
        raise PhaseBRunnerError("cleaner_import_failed", "approved cleaner source bytes are required")
    payload = bytes(source_bytes)
    if hashlib.sha256(payload).hexdigest() != CLEANER_SHA256:
        raise PhaseBRunnerError("pinned_file_hash_mismatch", "scripts/audit_generation_output.py")
    try:
        code = compile(payload, str(APPROVED_CLEANER), "exec", dont_inherit=True)
    except (SyntaxError, ValueError):
        raise PhaseBRunnerError("cleaner_import_failed", "approved cleaner source could not be compiled")
    module = types.ModuleType("b1_phase_b_approved_audit_generation_output")
    module.__file__ = str(APPROVED_CLEANER)
    module.__package__ = ""
    try:
        exec(code, module.__dict__)
    except PhaseBRunnerError:
        raise
    except Exception:
        raise PhaseBRunnerError("cleaner_import_failed", "approved cleaner source could not be executed")
    if not hasattr(module, "audit_line") or not hasattr(module, "split_raw_records"):
        raise PhaseBRunnerError("cleaner_import_failed", "approved cleaner API is missing audit_line")
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
    if isinstance(exc, PhaseBRunnerError):
        safe = _safe_detail(exc.detail)
        if safe == exc.detail:
            return exc
        return PhaseBRunnerError(exc.code, safe)
    if isinstance(exc, UnicodeDecodeError):
        return PhaseBRunnerError("output_decode_failed", "generation output is not valid UTF-8")
    if isinstance(exc, FileNotFoundError):
        return PhaseBRunnerError("output_file_missing", "expected generation output is missing")
    if isinstance(exc, subprocess.SubprocessError):
        return PhaseBRunnerError("generation_process_failed", "generation subprocess failed")
    if isinstance(exc, OSError):
        return PhaseBRunnerError("filesystem_error", "filesystem operation failed")
    if isinstance(exc, Exception):
        return PhaseBRunnerError("unexpected_runtime_failure", "unexpected runtime failure")
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
    except PhaseBRunnerError:
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
        "max_seq_len": invocation["max_seq_len"],
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
        context["selected_physical_gpu"],
        realpath=deps.realpath,
    )
    if command["shell"] is not False or command["cwd"] != GENERATION_CWD:
        raise PhaseBRunnerError(
            "generation_cwd_rejected",
            "generation working directory is not RNAGenesis",
        )
    if command["argv"][0] != PINNED_PYTHON:
        raise PhaseBRunnerError(
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
        raise PhaseBRunnerError("output_path_exists", "invocation output already exists")
    try:
        deps.subprocess_run(command["argv"], cwd=command["cwd"], env=command["env"], shell=False)
    except PhaseBRunnerError:
        raise
    except subprocess.SubprocessError as exc:
        raise normalize_evidence_error(exc)
    except OSError as exc:
        raise normalize_evidence_error(exc)
    try:
        raw_bytes = deps.read_bytes(predicted)
    except PhaseBRunnerError:
        raise
    except (FileNotFoundError, OSError) as exc:
        raise normalize_evidence_error(exc)
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raise PhaseBRunnerError("output_decode_failed", "generation output is not bytes")
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
        raise PhaseBRunnerError("parent_environment_mutated", "parent environment was modified")
    context["raw_outputs"].append(_raw_output_metadata(predicted, bytes(raw_bytes), records, invocation))
    context["attempts"].extend(records)
    context["completed_invocation_indexes"].append(invocation["invocation_index"])
    context["attempt_count"] = len(context["attempts"])


def verify_retained_raw_outputs(context, deps, cleaner):
    """Re-read every raw file and compare path, size, hash, and line count."""
    outputs = list(context.get("raw_outputs") or [])
    plan = list(context.get("plan") or [])
    if len(outputs) != INVOCATION_COUNT or len(plan) != INVOCATION_COUNT:
        raise PhaseBRunnerError("raw_output_verification_failed", "expected 89 raw outputs")
    plan_by_index = {item["invocation_index"]: item for item in plan}
    seen_paths = []
    for item in outputs:
        invocation = plan_by_index.get(item.get("invocation_index"))
        if invocation is None:
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output is not in the plan")
        expected_path = str(predicted_generation_path(context["output_dir"], invocation))
        path = item.get("path")
        if path != expected_path:
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output path changed")
        seen_paths.append(path)
        try:
            observed = deps.lstat(path)
        except FileNotFoundError:
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output is missing")
        except OSError:
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output could not be inspected")
        if stat.S_ISLNK(observed.st_mode):
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output is a symlink")
        if not stat.S_ISREG(observed.st_mode):
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output is not a regular file")
        if observed.st_size != item.get("byte_count"):
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output byte count changed")
        try:
            data = deps.read_bytes(path)
        except PhaseBRunnerError:
            raise
        except FileNotFoundError:
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output is missing")
        except OSError:
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output could not be read")
        if not isinstance(data, (bytes, bytearray)):
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output is not bytes")
        payload = bytes(data)
        if len(payload) != item.get("byte_count"):
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output byte count changed")
        if _sha256_bytes(payload) != item.get("sha256"):
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output hash changed")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output is not valid UTF-8")
        line_count = len(cleaner.split_raw_records(text))
        if line_count != item.get("line_count") or line_count != ATTEMPTS_PER_LENGTH:
            raise PhaseBRunnerError("raw_output_verification_failed", "raw output line count changed")
    if len(set(seen_paths)) != INVOCATION_COUNT:
        raise PhaseBRunnerError("raw_output_verification_failed", "raw output paths are not distinct")
    context["final_raw_output_verification"] = {"passed": True, "file_count": INVOCATION_COUNT}
    return context["final_raw_output_verification"]


def _finalize_evidence(context, deps, cleaner):
    output_dir = Path(context["output_dir"])
    attempts = context["attempts"]
    _assert_complete_attempts(attempts, context.get("plan"))
    verify_retained_raw_outputs(context, deps, cleaner)
    context["diagnostics"] = phase_b_diagnostics(attempts)
    _assert_diagnostics_do_not_authorise(context["diagnostics"])
    raw_payload = serialize_jsonl(attempts, RAW_LEDGER_KEYS)
    audited_payload = serialize_jsonl(attempts, AUDITED_LEDGER_KEYS)
    if raw_payload == audited_payload:
        raise PhaseBRunnerError("success_manifest_refused", "raw and audited ledgers must differ")
    _write_evidence(deps, output_dir / RAW_LEDGER_NAME, raw_payload)
    context["raw_ledger_sha256"] = _sha256_bytes(raw_payload)
    _write_evidence(deps, output_dir / AUDITED_LEDGER_NAME, audited_payload)
    context["audited_ledger_sha256"] = _sha256_bytes(audited_payload)
    context["timestamps"] = {"started_at": context["started_at"], "finished_at": deps.clock()}
    context["hostname"] = deps.hostname()
    manifest = build_success_manifest(context)
    manifest_bytes = canonical_json_bytes(manifest)
    report = {
        "manifest_path": SUCCESS_MANIFEST_NAME,
        "manifest_sha256": _sha256_bytes(manifest_bytes),
        "raw_ledger_sha256": context["raw_ledger_sha256"],
        "audited_ledger_sha256": context["audited_ledger_sha256"],
        "excluded_from_manifest_body": "manifest_sha256",
    }
    _write_evidence(deps, output_dir / HASH_REPORT_NAME, canonical_json_bytes(report))
    success_path = output_dir / SUCCESS_MANIFEST_NAME
    failure_path = output_dir / FAILURE_MANIFEST_NAME
    if _path_exists(failure_path):
        raise PhaseBRunnerError(
            "failure_manifest_exists",
            "refusing to write a success manifest beside a failure manifest",
        )
    if _path_exists(success_path):
        raise PhaseBRunnerError("success_marker_present", "refusing to overwrite the success manifest")
    _write_evidence(deps, success_path, manifest_bytes)
    if _path_exists(failure_path):
        raise PhaseBRunnerError(
            "failure_manifest_exists",
            "success and failure manifests must not coexist",
        )
    return manifest


def execute_phase_b(prepared, deps):
    context = _ensure_live_context(prepared)
    parent_before = list(deps.environ.items())
    cleaner = deps.load_cleaner(context.get("cleaner_source_bytes"))
    for invocation in context["plan"]:
        _run_invocation(context, deps, cleaner, invocation, parent_before)
    if list(deps.environ.items()) != parent_before:
        raise PhaseBRunnerError("parent_environment_mutated", "parent environment was modified")
    return _finalize_evidence(context, deps, cleaner)


def record_failure(output_dir, error, deps, context):
    success = Path(output_dir) / SUCCESS_MANIFEST_NAME
    failure = Path(output_dir) / FAILURE_MANIFEST_NAME
    if _path_exists(success):
        raise PhaseBRunnerError(
            "success_marker_present",
            "refusing to write a failure manifest after the success marker",
        )
    if _path_exists(failure):
        raise PhaseBRunnerError("failure_manifest_exists", "refusing to overwrite the failure manifest")
    error = normalize_evidence_error(error)
    if not isinstance(error, PhaseBRunnerError):
        error = PhaseBRunnerError("unexpected_runtime_failure", "unexpected runtime failure")
    original = error
    if not context.get("output_dir"):
        context["output_dir"] = str(output_dir)
    timestamps = dict(context.get("timestamps") or {})
    timestamps["failed_at"] = deps.clock()
    context["timestamps"] = timestamps
    if context.get("hostname") is None:
        context["hostname"] = deps.hostname()
    document = build_failure_manifest(context, original)
    if document["status"] != "failed" or document["failure"]["code"] != original.code:
        raise PhaseBRunnerError(
            "success_manifest_refused",
            "a failed run cannot produce a success manifest",
        )
    if _path_exists(success) or _path_exists(failure):
        raise PhaseBRunnerError(
            "success_marker_present",
            "refusing to write a failure manifest after another marker exists",
        )
    try:
        deps.write_exclusive(failure, canonical_json_bytes(document))
    except FileExistsError:
        raise PhaseBRunnerError("failure_manifest_exists", "refusing to overwrite the failure manifest")
    except PhaseBRunnerError:
        raise
    except Exception:
        raise PhaseBRunnerError("failure_manifest_write_failed", "failure evidence could not be written")
    if _path_exists(success):
        raise PhaseBRunnerError(
            "success_marker_present",
            "success and failure manifests must not coexist",
        )
    return document


def after_directory_created(output_dir, deps, operation, context):
    try:
        return operation()
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        error = normalize_evidence_error(exc)
        if not isinstance(error, PhaseBRunnerError):
            error = PhaseBRunnerError("unexpected_runtime_failure", "unexpected runtime failure")
        if _path_exists(Path(output_dir) / SUCCESS_MANIFEST_NAME):
            raise error
        try:
            record_failure(output_dir, error, deps, context)
        except Exception as secondary:
            if isinstance(secondary, PhaseBRunnerError):
                error.secondary_failure = secondary.code
            else:
                error.secondary_failure = "failure_manifest_write_failed"
        raise error


def run(output_dir, physical_gpu_argument, deps):
    """Refuse a closed configuration before every side effect.

    An opened configuration validates the 89-row plan before output-path
    inspection, repository inspection, asset hashing, GPU queries, directory
    creation, or generation.
    """
    config_bytes = deps.read_bytes(B1_CONFIG_PATH)
    config = load_config_bytes(config_bytes)
    assert_configuration_consumable(config)
    physical_gpu = parse_physical_gpu_argument(physical_gpu_argument)
    plan = build_phase_b_plan(config)
    snapshot = assert_phase_b_authorisation(config, physical_gpu)
    assert_cuda_environment(deps.environ, physical_gpu)
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
    child_env = build_child_environment(deps.environ, output_dir, physical_gpu, deps.realpath)
    gpu = deps.gpu_preflight(child_env, physical_gpu)
    if gpu.get("physical_gpu") != physical_gpu or gpu.get("index") != physical_gpu:
        raise PhaseBRunnerError(
            "gpu_identity_mismatch",
            "GPU preflight does not match the selected physical GPU",
        )
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
        "selected_physical_gpu": physical_gpu,
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
        lambda: execute_phase_b(prepared, deps),
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
        run(args.output_dir, args.physical_gpu, deps)
    except PhaseBRunnerError as exc:
        message = "error: {}: {}".format(exc.code, exc.detail)
        if exc.secondary_failure:
            message += " secondary: {}".format(exc.secondary_failure)
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
