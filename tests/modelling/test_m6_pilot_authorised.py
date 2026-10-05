"""CPU/mock tests for the M6 authorised path.

These tests do not open biological corpora, model weights, accepted run
directories, or a GPU. Torch is used only for tiny CPU tensors.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

import torch

ROOT = "/home/laura/rnagenesis-aptamer-mres"
RNAGENESIS = "/home/laura/RNAGenesis"
CONFIG_PATH = os.path.join(ROOT, "config/experiments/D1_diffusion_pilot.yaml")
CONTRACT_PATH = os.path.join(ROOT, "scripts/modelling/m6_pilot_contract.py")
RUNNER_PATH = os.path.join(ROOT, "scripts/modelling/m6_pilot_runner.py")
HEAD = "a" * 40
PARENT = "b" * 40
GPU_UUID = "GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f"
PCI = "00000000:61:00.0"
RNA_MESSAGE = "ACGUACGUACGUACGU"
ORDINARY_DETAIL = "authorized worker failed; exception_class=RuntimeError"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_module("m6_authorised_runner", RUNNER_PATH)
contract = runner.contract


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_hashes():
    return {path: digest(path) for path in contract.IMPLEMENTATION_FILE_PATHS}


def load_inactive():
    with open(CONFIG_PATH, "rb") as handle:
        raw = handle.read()
    return contract.load_config_bytes(raw)


def active_from(inactive, run_root, name="m6-unit"):
    config = copy.deepcopy(inactive)
    output = run_root.rstrip("/") + "/" + name
    config["document_status"] = contract.ACTIVE_DOCUMENT_STATUS
    config["consumable_by_executable_workflow"] = True
    execution = config["execution"]
    execution["authorised"] = True
    execution["biological_paths_permitted"] = True
    execution["gpu_identity_bound"] = True
    execution["output_directory"] = output
    execution["evidence_directory"] = output
    execution["authorisation_id"] = "m6_unit_authorisation"
    execution["authorization_parent_commit"] = PARENT
    execution["executing_implementation_commit"] = PARENT
    block = config["pilot_execution_authorisation"]
    block.update(
        {
            "activation_status": "active_unconsumed",
            "authorisation_id": "m6_unit_authorisation",
            "authorisation_timestamp": "2026-10-03T13:00:00+10:00",
            "authorization_parent_commit": PARENT,
            "b1_relative_path": contract.B1_RELATIVE_PATH,
            "b1_unet_config_sha256": contract.B1_UNET_CONFIG_SHA256,
            "b1_weight_sha256": contract.B1_WEIGHT_SHA256,
            "cuda_visible_devices": "1",
            "evidence_directory": output,
            "executing_implementation_commit": PARENT,
            "gpu_uuid": GPU_UUID,
            "implementation_file_hashes": file_hashes(),
            "logical_device": "cuda:0",
            "output_directory": output,
            "pci_bus": PCI,
            "permitted_roles": list(contract.ACTIVE_ROLES),
            "phase": contract.ACTIVE_PHASE,
            "physical_gpu_index": 1,
            "scope": contract.ACTIVE_SCOPE,
            "train_record_count": contract.TRAIN_RECORD_COUNT,
            "train_text_path": contract.FUTURE_TRAIN_TEXT_PATH,
            "train_text_sha256": contract.TRAIN_TEXT_SHA256,
            "validation_artifact_directory": contract.ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY,
            "validation_artifact_sha256": {
                "draw_manifest": contract.VALIDATION_DRAW_MANIFEST_SHA256,
                "noise": contract.VALIDATION_NOISE_SHA256,
                "order_artifact": contract.VALIDATION_ORDER_ARTIFACT_SHA256,
                "sequence_order": contract.VALIDATION_SEQUENCE_ORDER_SHA256,
                "timesteps": contract.VALIDATION_TIMESTEPS_SHA256,
            },
            "validation_csv_path": contract.FUTURE_VALIDATION_CSV_PATH,
            "validation_csv_sha256": contract.VALIDATION_CSV_SHA256,
            "validation_record_count": contract.VALIDATION_SEQUENCE_COUNT,
        }
    )
    block["session"]["consumption_event"] = contract.CONSUMPTION_EVENT
    return config


def observation(inactive, hashes, file_porcelain="?? .cache/huggingface/hub/version.txt\n", directory_porcelain=None):
    if directory_porcelain is None:
        directory_porcelain = contract.m5_contract().reviewed_rnagenesis_porcelain()
    return {
        "changed_files": list(contract.PERMITTED_AUTHORIZATION_FILES),
        "component_symlink": False,
        "file_sha256_at_parent": hashes,
        "file_sha256_working_tree": dict(hashes),
        "gpu_probe": {
            "cuda_visible_devices": "1",
            "logical_device": "cuda:0",
            "pci_bus": PCI,
            "physical_index": 1,
            "uuid": GPU_UUID,
        },
        "implementation_config": inactive,
        "mres_head": HEAD,
        "mres_parents": [PARENT],
        "mres_porcelain": "",
        "output_exists": False,
        "output_symlink": False,
        "rnagenesis_branch": contract.RNAGENESIS_BRANCH,
        "rnagenesis_directory_porcelain": directory_porcelain,
        "rnagenesis_file_porcelain": file_porcelain,
        "rnagenesis_head": contract.RNAGENESIS_COMMIT,
    }


def binding():
    return {
        "authorization_commit": HEAD,
        "authorization_parent_commit": PARENT,
        "cuda_visible_devices": "1",
        "executing_implementation_commit": PARENT,
        "gpu_uuid": GPU_UUID,
        "pci_bus": PCI,
        "physical_gpu_index": 1,
    }


def production_manifest():
    snapshot = {
        "opened_biological_data": False,
        "peak_allocated_bytes": 3,
        "peak_reserved_bytes": 5,
        "train_permutation_digest": contract.permutation_digest(list(range(contract.TRAIN_RECORD_COUNT))),
        "train_updates": [
            {
                "applied_norm": 0.2,
                "clipped": False,
                "learning_rate": contract.applied_learning_rate(update),
                "pre_clip_gradient_norm": 0.2,
                "training_loss": 0.4,
                "update": update,
            }
            for update in range(1, 22)
        ],
        "training_seconds": 1.0,
        "validation_observations": [],
        "validation_review_observations": [],
        "validation_seconds": 1.0,
        "weight_checkpoints": [],
    }
    initial = 0.5
    observations = []
    reviews = []
    for update in contract.VALIDATION_UPDATES:
        later = 0.6 if update == 7 else initial
        relative = None if update == 0 else contract.classify_validation_change(initial, later, update)
        if update != 0:
            reviews.append(relative)
        observations.append(
            {
                "aggregate_mse": contract.format_decimal(later if update != 0 else initial),
                "pair_count": 380,
                "relative_to_update_0": relative,
                "tensors_loaded": True,
                "tensors_regenerated": False,
                "update": update,
                "weight_variant": "raw",
            }
        )
    snapshot["validation_observations"] = observations
    snapshot["validation_review_observations"] = reviews
    snapshot["weight_checkpoints"] = [
        contract.prove_weight_reload(
            {
                "fresh_object_constructed": True,
                "labelled_as_resume": False,
                "original_config": {"_name_or_path": "original", "_class_name": "UNet", "layers": 2},
                "original_object_id": 10 + update,
                "original_state": {f"parameter_{index}": f"value-{update}-{index}" for index in range(5)},
                "reloaded_config": {"_name_or_path": "saved", "_class_name": "UNet", "layers": 2},
                "reloaded_object_id": 50 + update,
                "reloaded_state": {f"parameter_{index}": f"value-{update}-{index}" for index in range(5)},
                "saved_hashes": {name: digest(name + str(update)) for name in contract.CHECKPOINT_MEMBERS},
                "selection": "complete",
                "update": update,
            }
        )
        for update in (7, 14, 21)
    ]
    manifest = contract.build_control_flow_manifest(snapshot)
    manifest["completion_state"] = "pilot_completed"
    manifest["production_identities"] = True
    manifest["warnings"] = []
    manifest["failure_state"] = None
    manifest["deviations"] = [{"id": item} for item in contract.DOCUMENTED_DEVIATIONS]
    manifest["post_update_21_scheduler_position"] = {
        "applied_to_optimizer": False,
        "multiplier": "0",
        "position": 22,
        "pytorch_scheduler_last_epoch": None,
        "role": "next_unapplied_schedule_position",
    }
    manifest["authorisation"] = {
        "authorisation_id": "m6_unit_authorisation",
        "authorization_commit": HEAD,
        "authorization_parent_commit": PARENT,
        "consumption_state": "consumed_successfully",
        "evidence_origin": "observed",
        "executing_implementation_commit": PARENT,
        "reuse_permitted": False,
        "single_use": True,
    }
    manifest["gpu"] = {
        "cuda_visible_devices": "1",
        "evidence_origin": "observed",
        "hardcoded_physical_index": False,
        "logical_device": "cuda:0",
        "pci_bus": PCI,
        "physical_index": 1,
        "uuid": GPU_UUID,
    }
    m5 = contract.m5_contract()
    versions = {key: value for key, value in m5.ACCEPTED_RUNTIME_VERSIONS.items()}
    runtime = {
        "accelerate": versions["accelerate"],
        "diffusers": versions["diffusers"],
        "evidence_origin": "observed",
        "executable": m5.PINNED_PYTHON,
        "observation_method": "module_attribute",
        "python": versions["python"],
        "torch": versions["torch"],
        "transformers": versions["transformers"],
    }
    assets = {}
    for relative, file_digest, size, role_name in m5.REQUIRED_MODEL_FILES:
        assets[role_name] = _asset_record(role_name, os.path.join(str(m5.RNAGENESIS_ROOT), relative), size, file_digest)
    assets["diffusers_normalization_patch"] = _asset_record(
        "diffusers_normalization_patch",
        m5.DIFFUSERS_PATCH_PATH,
        m5.DIFFUSERS_PATCH_SIZE,
        m5.DIFFUSERS_PATCH_SHA256,
    )
    artifact_files = {}
    artifact_sizes = {
        "validation_draw_manifest.json": 11,
        "validation_draw_manifest_sha256.json": 22,
        "validation_noise.float32": 33,
        "validation_order_artifact.csv": 44,
        "validation_timesteps.int64": 55,
    }
    artifact_hashes = {
        "validation_draw_manifest.json": contract.VALIDATION_DRAW_MANIFEST_SHA256,
        "validation_draw_manifest_sha256.json": contract.VALIDATION_HASH_REPORT_SHA256,
        "validation_noise.float32": contract.VALIDATION_NOISE_SHA256,
        "validation_order_artifact.csv": contract.VALIDATION_ORDER_ARTIFACT_SHA256,
        "validation_timesteps.int64": contract.VALIDATION_TIMESTEPS_SHA256,
    }
    for name, file_digest in artifact_hashes.items():
        artifact_files[name] = _asset_record(name, name, artifact_sizes[name], file_digest)
    artifact_bytes = sum(artifact_sizes.values())

    def role(name, path, expected_hash, count, opened, observed_hash, observed_count, observed_byte_size, method):
        return {
            "evidence_origin": "observed",
            "expected_count": count,
            "expected_sha256": expected_hash,
            "observation_method": method,
            "observed_byte_size": observed_byte_size,
            "observed_count": observed_count,
            "observed_sha256": observed_hash,
            "opened": opened,
            "path": path,
            "role": name,
        }

    manifest["run_id"] = "m6_unit_authorisation"
    manifest["data_roles"] = {
        "eval": role("EVAL", None, contract.EVAL_HASH_METADATA, None, False, None, 0, None, "not_opened"),
        "ref": role("REF", None, contract.REF_HASH_METADATA, None, False, None, 0, None, "not_opened"),
        "train_text": role(
            "TRAIN_TEXT",
            contract.FUTURE_TRAIN_TEXT_PATH,
            contract.TRAIN_TEXT_SHA256,
            669,
            True,
            contract.TRAIN_TEXT_SHA256,
            669,
            424242,
            "streamed_sha256",
        ),
        "validation_artifacts": role(
            "VALIDATION_ARTIFACT",
            contract.ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY,
            artifact_hashes,
            5,
            True,
            artifact_hashes,
            5,
            artifact_bytes,
            "streamed_sha256",
        ),
        "validation_csv": role(
            "VALIDATION_CSV",
            contract.FUTURE_VALIDATION_CSV_PATH,
            contract.VALIDATION_CSV_SHA256,
            95,
            True,
            contract.VALIDATION_CSV_SHA256,
            95,
            434343,
            "streamed_sha256",
        ),
    }
    manifest["b1_identity"] = {
        "copied_at_update_0": False,
        "evidence_origin": "observed",
        "initialization": "immutable_B1_generic_diffusion_checkpoint",
        "observed_assets": assets,
        "unet_config_sha256": assets["b1_unet_config"]["sha256"],
        "weight_bytes": assets["b1_unet_weights"]["byte_size"],
        "weight_sha256": assets["b1_unet_weights"]["sha256"],
    }
    manifest["environment"] = {
        "accelerate_version": runtime["accelerate"],
        "bytecode_disabled": True,
        "cache_isolation": m5.runtime_isolation_paths("/tmp/m6-manifest-evidence"),
        "datasets_offline": True,
        "diffusers_version": runtime["diffusers"],
        "evidence_origin": "observed",
        "executable": runtime["executable"],
        "expected_python": versions["python"],
        "expected_versions": versions,
        "hub_offline": True,
        "numpy_called_by_pilot": False,
        "numpy_used_by_pinned_artifact_loader": True,
        "package_versions_observed": runtime,
        "pinned_python": m5.PINNED_PYTHON,
        "python_version": runtime["python"],
        "runtime_isolation_verified": True,
        "torch_version": runtime["torch"],
        "transformers_offline": True,
        "transformers_version": runtime["transformers"],
    }
    manifest["optimizer"]["evidence_origin"] = "observed"
    manifest["optimizer"]["mixed_precision"] = "no"
    manifest["optimizer"]["precision"] = "fp32"
    manifest["denoiser_update_evidence"]["evidence_origin"] = "observed"
    manifest["rng"] = {
        "diffusion_generator_final_digest": digest("diffusion-final"),
        "diffusion_generator_initial_digest": digest("diffusion-initial"),
        "diffusion_stream": "dedicated_cpu_diffusion_generator",
        "numpy_called_by_pilot": False,
        "permutation_generator_final_digest": digest("permutation-final"),
        "permutation_generator_initial_digest": digest("permutation-initial"),
        "permutation_stream": "dedicated_cpu_train_permutation_generator",
        "python_rng_final_digest": digest("python-final"),
        "python_rng_initial_digest": digest("python-initial"),
        "streams_are_distinct": True,
        "torch_cpu_final_digest": digest("cpu-final"),
        "torch_cpu_initial_digest": digest("cpu-initial"),
        "torch_cuda_final_digest": digest("cuda-final"),
        "torch_cuda_initial_digest": digest("cuda-initial"),
        "train_permutation_digest": contract.permutation_digest(list(range(669))),
        "train_permutation_seed": 42,
        "validation_artifacts_regenerated": False,
        "validation_draw_seed": 1,
    }
    manifest["repository"] = {
        "authorization_commit": HEAD,
        "evidence_origin": "observed",
        "executing_implementation_commit": PARENT,
        "mres_index_clean": True,
        "mres_tracked_clean": True,
        "mres_untracked_clean": True,
        "rnagenesis_branch": contract.RNAGENESIS_BRANCH,
        "rnagenesis_commit": contract.RNAGENESIS_COMMIT,
        "rnagenesis_tracked_clean": True,
        "rnagenesis_untracked_preserved": True,
    }
    manifest["memory"] = {"evidence_origin": "observed", "peak_allocated_bytes": 11, "peak_reserved_bytes": 13}
    manifest["timing"] = {
        "checkpoint_save_reload_seconds": [
            {"seconds": "1", "update": update} for update in contract.RETAINED_WEIGHT_UPDATES
        ],
        "checkpoint_time_excluded_from_training_and_validation": True,
        "evidence_origin": "observed",
        "synchronization": "cuda_synchronize_before_and_after_each_region",
        "training_seconds": "21",
        "training_update_seconds": ["1"] * contract.OPTIMIZER_UPDATES,
        "validation_excluded_from_training_updates": True,
        "validation_seconds": "4",
        "validation_update_seconds": [
            {"seconds": "1", "update": update} for update in contract.VALIDATION_UPDATES
        ],
    }
    manifest["validation_artifacts"] = {
        "draw_manifest_sha256": artifact_files["validation_draw_manifest.json"]["sha256"],
        "draws": contract.VALIDATION_DRAWS,
        "evidence_origin": "observed",
        "hash_report_sha256": artifact_files["validation_draw_manifest_sha256.json"]["sha256"],
        "noise_sha256": artifact_files["validation_noise.float32"]["sha256"],
        "noise_shape": list(contract.VALIDATION_NOISE_SHAPE),
        "observation_method": "streamed_sha256",
        "observed_files": artifact_files,
        "order_artifact_sha256": artifact_files["validation_order_artifact.csv"]["sha256"],
        "sequence_count": contract.VALIDATION_SEQUENCE_COUNT,
        "sequence_order_sha256": contract.VALIDATION_SEQUENCE_ORDER_SHA256,
        "sequence_order_source": "loaded_manifest",
        "timestep_sha256": artifact_files["validation_timesteps.int64"]["sha256"],
        "timestep_shape": list(contract.VALIDATION_TIMESTEP_SHAPE),
        "validation_csv_sha256": contract.VALIDATION_CSV_SHA256,
    }
    manifest["train_update_observations"] = []
    for update in range(1, 22):
        manifest["train_update_observations"].append(
            {
                "applied_clip_norm": contract.format_decimal(0.2),
                "clipped": False,
                "denoiser_change": {
                    "changed": True,
                    "finite_nonzero_gradient": True,
                    "flat_index": 3,
                    "gradient": contract.format_decimal(-0.01),
                    "parameter_name": "weight",
                    "value_after": contract.format_decimal(0.2),
                    "value_before": contract.format_decimal(0.1),
                },
                "evidence_origin": "observed",
                "learning_rate": contract.format_decimal(contract.applied_learning_rate(update)),
                "learning_rate_recorded_before_optimizer_step": True,
                "pre_clip_gradient_norm": contract.format_decimal(0.2),
                "stop_fired": False,
                "training_loss": contract.format_decimal(0.4),
                "update": update,
            }
        )
    manifest["validation_observations"] = []
    for item in observations:
        copied = dict(item)
        copied["evidence_origin"] = "observed"
        manifest["validation_observations"].append(copied)
    for item in manifest["weight_checkpoints"]:
        item["evidence_origin"] = "observed"
    parameter_digest = digest("encdec-parameters")
    buffer_digest = digest("encdec-buffers")
    manifest["frozen_state"] = {
        "all_frozen": True,
        "components": list(contract.ENCDEC_COMPONENTS),
        "encdec_buffers_absent_from_optimizer": True,
        "encdec_eval_mode": True,
        "encdec_parameters_absent_from_optimizer": True,
        "encdec_parameter_digest_after_update_14": parameter_digest,
        "encdec_parameter_digest_after_update_21": parameter_digest,
        "encdec_parameter_digest_after_update_7": parameter_digest,
        "encdec_parameter_digest_at_initialization": parameter_digest,
        "encdec_persistent_buffer_digest_after_update_14": buffer_digest,
        "encdec_persistent_buffer_digest_after_update_21": buffer_digest,
        "encdec_persistent_buffer_digest_after_update_7": buffer_digest,
        "encdec_persistent_buffer_digest_at_initialization": buffer_digest,
        "encdec_requires_grad_false": True,
        "evidence_origin": "observed",
        "optimizer_contains_encdec": False,
        "optimizer_contains_only_denoiser": True,
        "optimizer_parameter_ids_equal_trainable_denoiser": True,
        "rotary_cache_names": ["decoder._cos_cached"],
        "rotary_caches_excluded_from_persistent_buffer_digest": True,
    }
    return manifest


def _pilot_assets():
    """Accepted asset and runtime records. This does not open model files."""
    m5 = contract.m5_contract()
    assets = {}
    for relative, file_digest, size, role in m5.REQUIRED_MODEL_FILES:
        assets[role] = _asset_record(role, os.path.join(str(m5.RNAGENESIS_ROOT), relative), size, file_digest)
    assets["diffusers_normalization_patch"] = _asset_record(
        "diffusers_normalization_patch",
        m5.DIFFUSERS_PATCH_PATH,
        m5.DIFFUSERS_PATCH_SIZE,
        m5.DIFFUSERS_PATCH_SHA256,
    )
    versions = m5.ACCEPTED_RUNTIME_VERSIONS
    runtime = {
        "accelerate": versions["accelerate"],
        "diffusers": versions["diffusers"],
        "evidence_origin": "observed",
        "executable": m5.PINNED_PYTHON,
        "observation_method": "module_attribute",
        "python": versions["python"],
        "torch": versions["torch"],
        "transformers": versions["transformers"],
    }
    return assets, runtime


def _asset_record(role, path, size, file_digest):
    return {
        "byte_size": size,
        "evidence_origin": "observed",
        "expected_byte_size": size,
        "expected_sha256": file_digest,
        "observation_method": "streamed_sha256",
        "path": path,
        "regular_file": True,
        "role": role,
        "sha256": file_digest,
        "symlink": False,
    }


class AuthorisedPathTests(unittest.TestCase):
    def setUp(self):
        self.inactive = load_inactive()
        self.hashes = file_hashes()
        self.temp = tempfile.mkdtemp(prefix="m6-auth-")
        self.active = active_from(self.inactive, self.temp)
        self.observation = observation(self.inactive, self.hashes)

    def tearDown(self):
        shutil.rmtree(self.temp)

    def test_checked_in_file_has_no_authorization_commit_key(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("\nauthorization_commit:", "\n" + text)
        self.assertFalse(contract._contains_key(self.inactive, "authorization_commit"))
        self.assertEqual(self.inactive["document_status"], "M6_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED")

    def test_inactive_rejection_happens_before_the_worker(self):
        calls = []
        with open(CONFIG_PATH, "rb") as handle:
            raw = handle.read()
        with self.assertRaises(contract.M6PilotError) as caught:
            runner.evaluate_configuration(raw, worker=lambda auth: calls.append(auth))
        self.assertEqual(caught.exception.code, "execution_not_authorised")
        self.assertEqual(calls, [])

    def test_valid_active_authorisation_reaches_injected_worker_without_imports(self):
        import sys

        before = set(sys.modules)
        reached = []
        authorisation = contract.validate_active_execution(self.active, self.observation, self.temp)
        result = runner.evaluate_configuration(
            __import__("yaml").safe_dump(self.active).encode("utf-8"),
            observation=self.observation,
            worker=lambda auth: reached.append(auth["authorisation_id"]) or "reached",
            run_root=self.temp,
        )
        self.assertEqual(result, "reached")
        self.assertEqual(reached, ["m6_unit_authorisation"])
        self.assertEqual(authorisation["authorization_commit"], HEAD)
        self.assertNotIn("authorization_commit", self.active["pilot_execution_authorisation"])
        imported = {name.split(".")[0] for name in set(sys.modules) - before}
        self.assertFalse(imported & {"torch", "accelerate", "diffusers", "train_diffusion_mres"})

    def test_malformed_active_authorisations_fail_before_creation(self):
        created = []
        original = os.mkdir
        os.mkdir = lambda path, *args, **kwargs: created.append(path)
        cases = []
        missing_gpu = copy.deepcopy(self.active)
        del missing_gpu["pilot_execution_authorisation"]["physical_gpu_index"]
        cases.append(missing_gpu)
        consumed = copy.deepcopy(self.active)
        consumed["pilot_execution_authorisation"]["consumed"] = True
        cases.append(consumed)
        mismatch = copy.deepcopy(self.active)
        mismatch["pilot_execution_authorisation"]["authorization_parent_commit"] = "c" * 40
        mismatch["execution"]["authorization_parent_commit"] = "c" * 40
        cases.append(mismatch)
        bad_uuid = copy.deepcopy(self.active)
        bad_uuid["pilot_execution_authorisation"]["gpu_uuid"] = "not-a-uuid"
        cases.append(bad_uuid)
        bad_logical = copy.deepcopy(self.active)
        bad_logical["pilot_execution_authorisation"]["logical_device"] = "cuda:1"
        cases.append(bad_logical)
        bad_visible = copy.deepcopy(self.active)
        bad_visible["pilot_execution_authorisation"]["cuda_visible_devices"] = "0"
        cases.append(bad_visible)
        nested = copy.deepcopy(self.active)
        nested["pilot_execution_authorisation"]["output_directory"] = self.temp + "/nested/child"
        nested["pilot_execution_authorisation"]["evidence_directory"] = nested["pilot_execution_authorisation"]["output_directory"]
        nested["execution"]["output_directory"] = nested["pilot_execution_authorisation"]["output_directory"]
        nested["execution"]["evidence_directory"] = nested["execution"]["output_directory"]
        cases.append(nested)
        ref_role = copy.deepcopy(self.active)
        ref_role["pilot_execution_authorisation"]["permitted_roles"] = list(contract.ACTIVE_ROLES) + ["REF"]
        cases.append(ref_role)
        self_key = copy.deepcopy(self.active)
        self_key["pilot_execution_authorisation"]["authorization_commit"] = HEAD
        cases.append(self_key)
        try:
            for config in cases:
                with self.assertRaises(contract.M6PilotError):
                    contract.validate_active_execution(config, self.observation, self.temp)
            self.assertEqual(created, [])
        finally:
            os.mkdir = original

    def test_parent_and_changed_path_checks(self):
        changed = copy.deepcopy(self.active)
        changed["pilot_decisions"]["learning_rate"] = 1e-5
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validate_active_execution(changed, self.observation, self.temp)
        self.assertEqual(caught.exception.code, "authorisation_delta_invalid")
        dirty = copy.deepcopy(self.observation)
        dirty["changed_files"] = ["config/experiments/D1_diffusion_pilot.yaml", "scripts/modelling/m6_pilot_runner.py"]
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validate_active_execution(self.active, dirty, self.temp)
        self.assertEqual(caught.exception.code, "authorisation_delta_invalid")
        two_parents = copy.deepcopy(self.observation)
        two_parents["mres_parents"] = [PARENT, "c" * 40]
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validate_active_execution(self.active, two_parents, self.temp)
        self.assertEqual(caught.exception.code, "authorisation_commit_invalid")
        mres_dirty = copy.deepcopy(self.observation)
        mres_dirty["mres_porcelain"] = "?? unexpected.py\n"
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validate_active_execution(self.active, mres_dirty, self.temp)
        self.assertEqual(caught.exception.code, "provenance_mismatch")
        tracked = copy.deepcopy(self.observation)
        tracked["rnagenesis_file_porcelain"] = " M train_diffusion_mres.py\n"
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validate_active_execution(self.active, tracked, self.temp)
        self.assertEqual(caught.exception.code, "provenance_mismatch")
        loose = copy.deepcopy(self.observation)
        loose["rnagenesis_file_porcelain"] = "?? unexpected.py\n"
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validate_active_execution(self.active, loose, self.temp)
        self.assertEqual(caught.exception.code, "provenance_mismatch")
        source = copy.deepcopy(self.observation)
        source["rnagenesis_file_porcelain"] = "?? models/evil.py\n"
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validate_active_execution(self.active, source, self.temp)
        self.assertEqual(caught.exception.code, "provenance_mismatch")
        config_file = copy.deepcopy(self.observation)
        config_file["rnagenesis_file_porcelain"] = "?? configs/evil.yaml\n"
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validate_active_execution(self.active, config_file, self.temp)
        self.assertEqual(caught.exception.code, "provenance_mismatch")
        directory = copy.deepcopy(self.observation)
        directory["rnagenesis_directory_porcelain"] = "?? models/\n"
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validate_active_execution(self.active, directory, self.temp)
        self.assertEqual(caught.exception.code, "provenance_mismatch")
        preserved = copy.deepcopy(self.observation)
        preserved["rnagenesis_file_porcelain"] = (
            "?? checkpoints/Aptamer/diffusion/unet/config.json\n?? zenodo_downloads/SHA256SUMS.txt\n"
        )
        contract.validate_active_execution(self.active, preserved, self.temp)
        drifted = copy.deepcopy(self.observation)
        drifted["file_sha256_working_tree"] = dict(self.hashes)
        drifted["file_sha256_working_tree"][contract.IMPLEMENTATION_FILE_PATHS[0]] = digest("other")
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validate_active_execution(self.active, drifted, self.temp)
        self.assertEqual(caught.exception.code, "provenance_mismatch")

    def test_self_referential_head_is_rejected(self):
        planted = copy.deepcopy(self.active)
        planted["pilot_execution_authorisation"]["authorisation_id"] = HEAD
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.assert_no_self_referential_authorization_commit(planted, HEAD)
        self.assertEqual(caught.exception.code, "authorisation_commit_invalid")

    def test_exclusive_consumption_and_failure_record(self):
        authorisation = contract.validate_active_execution(self.active, self.observation, self.temp)
        path = contract.consume_bound_output_directory(authorisation, self.temp)
        self.assertTrue(os.path.isdir(path))
        self.assertTrue(os.path.isfile(os.path.join(path, contract.CONSUMPTION_RECORD_NAME)))
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.consume_bound_output_directory(authorisation, self.temp)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.consume_bound_output_directory(authorisation, self.temp)
        contract.write_failure_record(path, caught.exception)
        self.assertTrue(os.path.isfile(os.path.join(path, contract.FAILURE_RECORD_NAME)))
        self.assertFalse(os.path.exists(os.path.join(path, contract.SUCCESS_MANIFEST_NAME)))

        class Stack(object):
            production_identities = True

            def torch(self):
                return torch

        other = active_from(self.inactive, self.temp, name="m6-cuda-hidden")
        other_auth = contract.validate_active_execution(other, self.observation, self.temp)
        with self.assertRaises(contract.M6PilotError) as caught:
            runner.execute_authorized_worker(other_auth, Stack(), run_root=self.temp)
        self.assertEqual(caught.exception.code, "identity_mismatch")
        failed = other["execution"]["output_directory"]
        failure_path = os.path.join(failed, contract.FAILURE_RECORD_NAME)
        self.assertTrue(os.path.isfile(failure_path))
        with open(failure_path, "r", encoding="utf-8") as handle:
            failure = json.loads(handle.read())
        self.assertEqual(failure["authorization_commit"], HEAD)
        self.assertEqual(failure["executing_implementation_commit"], PARENT)
        self.assertEqual(failure["failure_code"], "identity_mismatch")
        self.assertEqual(failure["fired_stop_condition"], "identity_mismatch")
        self.assertEqual(failure["stage"], "runtime_identity")
        self.assertTrue(failure["non_resumable"])
        self.assertFalse(failure["resume_supported"])
        self.assertFalse(failure["pilot_completed"])
        self.assertFalse(failure["scientific_run_completed"])
        self.assertFalse(failure["retained_checkpoints_exist"])
        self.assertEqual(failure["completion_state"], "consumed_failed")
        self.assertNotIn("ACGU", json.dumps(failure))
        self.assertFalse(os.path.exists(os.path.join(failed, contract.SUCCESS_MANIFEST_NAME)))
        with self.assertRaises(contract.M6PilotError) as caught:
            runner.execute_authorized_worker(other_auth, Stack(), run_root=self.temp)
        self.assertEqual(caught.exception.code, "authorization_reuse")

    def test_bound_file_identity_checks_happen_before_the_reader(self):
        calls = []

        def reader(path):
            calls.append(path)
            return ["ACGUACGU", "ACGUACGA"]

        directory = os.path.join(self.temp, "inputs")
        os.mkdir(directory)
        payload = b"ACGUACGU\nACGUACGA\n"
        path = os.path.join(directory, "corpus_final.txt")
        with open(path, "wb") as handle:
            handle.write(payload)
        opened = contract.verify_bound_file(path, "TRAIN_TEXT", contract.sha256_bytes(payload), 2, path, reader)
        self.assertEqual(calls, [path])
        self.assertEqual(opened["count"], 2)
        calls.clear()
        with self.assertRaises(contract.M6PilotError):
            contract.verify_bound_file(path, "TRAIN_TEXT", digest("wrong"), 2, path, reader)
        self.assertEqual(calls, [])
        link = os.path.join(directory, "link.txt")
        os.symlink(path, link)
        with self.assertRaises(contract.M6PilotError):
            contract.verify_bound_file(link, "TRAIN_TEXT", contract.sha256_bytes(payload), 2, link, reader)
        self.assertEqual(calls, [])
        with self.assertRaises(contract.M6PilotError):
            contract.verify_bound_file(os.path.join(directory, "ref.csv"), "TRAIN_TEXT", digest("x"), 1, path, reader)
        with self.assertRaises(contract.M6PilotError):
            contract.verify_bound_file(
                "/home/laura/rnagenesis-aptamer-mres/data/processed/corpus_final.txt",
                "TRAIN_TEXT",
                digest("x"),
                1,
                path,
                reader,
            )
        self.assertEqual(calls, [])
        odd = os.path.join(directory, "notes.txt")
        with open(odd, "wb") as handle:
            handle.write(payload)
        with self.assertRaises(contract.M6PilotError):
            contract.verify_bound_file(odd, "TRAIN_TEXT", contract.sha256_bytes(payload), 2, path, reader)
        self.assertEqual(calls, [])

    def test_artifact_loader_is_not_the_builder(self):
        directory = os.path.join(self.temp, "artifacts")
        os.mkdir(directory)
        expected = {}
        for name in contract.VALIDATION_ARTIFACT_FILES:
            blob = name.encode("ascii")
            with open(os.path.join(directory, name), "wb") as handle:
                handle.write(blob)
            expected[name] = contract.sha256_bytes(blob)
        calls = []

        def loader(path):
            calls.append(path)
            return {"loaded": True}

        loaded = contract.verify_artifact_directory(directory, directory, expected, loader)
        self.assertEqual(loaded["loaded"]["loaded"], True)
        self.assertEqual(loaded["observed_files"]["validation_noise.float32"]["sha256"], expected["validation_noise.float32"])
        self.assertEqual(loaded["observed_files"]["validation_noise.float32"]["observation_method"], "streamed_sha256")
        self.assertEqual(calls, [directory])
        calls.clear()
        expected["validation_noise.float32"] = digest("tampered")
        with self.assertRaises(contract.M6PilotError):
            contract.verify_artifact_directory(directory, directory, expected, loader)
        self.assertEqual(calls, [])
        with open(RUNNER_PATH, "r", encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("load_verified_artifacts", source)
        self.assertNotIn("build_draw_tensors", source)
        self.assertNotIn("build_fixed_validation_draws", source)

    def test_tracked_rnagenesis_signatures_and_adamw(self):
        with open(os.path.join(RNAGENESIS, "train_diffusion_mres.py"), "r", encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for name, expected in contract.EXPECTED_RNAGENESIS_SIGNATURES.items():
            if name == "load_tokenizer":
                continue
            arguments = tuple(arg.arg for arg in functions[name].args.args)
            self.assertEqual(arguments, expected, name)
        with open(os.path.join(RNAGENESIS, "models/autoencoder/encoder/biomap/rna_tokens.py"), encoding="utf-8") as handle:
            tokens = ast.parse(handle.read())
        tokenizer = [node for node in tokens.body if isinstance(node, ast.FunctionDef) and node.name == "load_tokenizer"][0]
        self.assertEqual(tuple(arg.arg for arg in tokenizer.args.args), ())
        adam = functions["build_adamw"]
        calls = [node for node in ast.walk(adam) if isinstance(node, ast.Call)]
        call = [node for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "AdamW"][0]
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        betas = keywords["betas"]
        self.assertEqual([item.id for item in betas.elts], ["ADAM_BETA1", "ADAM_BETA2"])
        self.assertEqual(keywords["weight_decay"].id, "ADAM_WEIGHT_DECAY")
        self.assertEqual(keywords["eps"].id, "ADAM_EPSILON")
        assigned = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant):
                assigned[node.targets[0].id] = node.value.value
        self.assertEqual(assigned["ADAM_BETA1"], contract.ADAMW_BETA1)
        self.assertEqual(assigned["ADAM_BETA2"], contract.ADAMW_BETA2)
        self.assertEqual(assigned["ADAM_WEIGHT_DECAY"], contract.ADAMW_WEIGHT_DECAY)
        self.assertEqual(assigned["ADAM_EPSILON"], contract.ADAMW_EPSILON)
        with open(os.path.join(RNAGENESIS, "models/autoencoder/encdec.py"), encoding="utf-8") as handle:
            encdec = ast.parse(handle.read())
        methods = {}
        for node in encdec.body:
            if isinstance(node, ast.ClassDef) and node.name == "EncDec":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        methods[item.name] = tuple(arg.arg for arg in item.args.args)
        self.assertEqual(methods["freeze"], ("self",))
        self.assertEqual(methods["get_latent"], ("self", "input_ids", "attention_mask"))
        with open(os.path.join(RNAGENESIS, "scripts/audit_generation_output.py"), encoding="utf-8") as handle:
            audit = ast.parse(handle.read())
        audit_names = {node.name for node in audit.body if isinstance(node, ast.FunctionDef)}
        self.assertIn("audit_line", audit_names)
        self.assertIn("sha256_file", audit_names)

    def test_gradient_equivalence_uses_the_production_scale(self):
        self.assertEqual(contract.PRODUCTION_ACCELERATOR_GRADIENT_ACCUMULATION_STEPS, 1)
        self.assertEqual(contract.production_loss_scale(0.25), 0.25)

        def compare(count, sizes):
            torch.manual_seed(0)
            source = torch.nn.Linear(4, 1)
            data = torch.randn(count, 4)
            target = torch.randn(count, 1)
            full = torch.nn.Linear(4, 1)
            full.load_state_dict(source.state_dict())
            loss = torch.nn.functional.mse_loss(full(data), target)
            (loss * contract.production_loss_scale(1.0)).backward()
            split = torch.nn.Linear(4, 1)
            split.load_state_dict(source.state_dict())
            offset = 0
            for size, scale in zip(sizes, contract.applied_float_scales(tuple(sizes))):
                chunk_data = data[offset:offset + size]
                chunk_target = target[offset:offset + size]
                offset += size
                micro = torch.nn.functional.mse_loss(split(chunk_data), chunk_target)
                (micro * contract.production_loss_scale(scale)).backward()
            for left, right in zip(full.parameters(), split.parameters()):
                self.assertTrue(torch.allclose(left.grad, right.grad, rtol=1e-5, atol=1e-6))

        compare(32, (8, 8, 8, 8))
        compare(29, (8, 8, 8, 5))

    def test_applied_learning_rate_is_assigned_before_each_step(self):
        layer = torch.nn.Linear(2, 1)
        optimizer = torch.optim.AdamW(
            layer.parameters(),
            lr=1.0,
            betas=(contract.ADAMW_BETA1, contract.ADAMW_BETA2),
            weight_decay=contract.ADAMW_WEIGHT_DECAY,
            eps=contract.ADAMW_EPSILON,
        )
        seen = []
        for update in range(1, 22):
            learning_rate = contract.assign_applied_learning_rate(optimizer, update)
            self.assertEqual(optimizer.param_groups[0]["lr"], learning_rate)
            seen.append(learning_rate)
            optimizer.step()
        self.assertEqual(tuple(seen), contract.applied_learning_rate_trace())
        post = contract.post_update_scheduler_position()
        self.assertEqual(post["position"], 22)
        self.assertFalse(post["applied_to_optimizer"])
        self.assertFalse(hasattr(optimizer, "last_epoch"))

    def test_permutation_and_diffusion_streams_are_distinct(self):
        permutation = torch.Generator(device="cpu")
        diffusion = torch.Generator(device="cpu")
        permutation.manual_seed(contract.PILOT_SEED)
        diffusion.manual_seed(contract.PILOT_SEED)
        self.assertTrue(torch.equal(permutation.get_state(), diffusion.get_state()))
        initial_permutation = contract.state_entry_digest("permutation", permutation.get_state())
        initial_diffusion = contract.state_entry_digest("diffusion", diffusion.get_state())
        self.assertNotEqual(initial_permutation, initial_diffusion)
        torch.randperm(contract.TRAIN_RECORD_COUNT, generator=permutation)
        torch.randn(8, 32, 160, generator=diffusion)
        final_permutation = contract.state_entry_digest("permutation", permutation.get_state())
        final_diffusion = contract.state_entry_digest("diffusion", diffusion.get_state())
        self.assertNotEqual(final_permutation, final_diffusion)
        self.assertFalse(torch.equal(permutation.get_state(), diffusion.get_state()))
        self.assertNotEqual(final_permutation, initial_permutation)
        self.assertNotEqual("dedicated_cpu_train_permutation_generator", "dedicated_cpu_diffusion_generator")
        state = __import__("random").getstate()
        self.assertEqual(contract.python_rng_digest(state), contract.python_rng_digest(state))

    def test_parameter_identity_frozen_digest_and_element_change(self):
        encdec = torch.nn.Linear(2, 2)
        denoiser = torch.nn.Linear(2, 2)
        for parameter in encdec.parameters():
            parameter.requires_grad_(False)
        encdec.eval()
        optimizer = torch.optim.AdamW(denoiser.parameters(), lr=1e-2)
        proof = runner.live_parameter_identity_proof(optimizer, denoiser, encdec)
        self.assertTrue(proof["optimizer_parameter_ids_equal_trainable_denoiser"])
        self.assertTrue(proof["encdec_parameters_absent_from_optimizer"])
        self.assertTrue(proof["encdec_buffers_absent_from_optimizer"])
        before = runner.frozen_parameter_digest(encdec)
        data = torch.ones(4, 2)
        loss = torch.nn.functional.mse_loss(denoiser(data), torch.zeros(4, 2))
        (loss * contract.production_loss_scale(1.0)).backward()
        selected = runner.select_denoiser_change(torch, list(denoiser.named_parameters()))
        optimizer.step()
        change = runner.finish_denoiser_change(selected)
        self.assertTrue(change["changed"])
        self.assertNotEqual(change["value_before"], change["value_after"])
        self.assertEqual(runner.frozen_parameter_digest(encdec), before)
        poisoned = torch.optim.AdamW(list(denoiser.parameters()) + list(encdec.parameters()), lr=1e-2)
        with self.assertRaises(contract.M6PilotError):
            runner.live_parameter_identity_proof(poisoned, denoiser, encdec)

    def test_tensor_state_mismatch_outside_the_first_three_entries(self):
        names = ["a", "b", "c", "d", "e"]
        original = {name: torch.arange(4).float() + index for index, name in enumerate(names)}
        reloaded = {name: value.clone() for name, value in original.items()}
        compared = contract.compare_complete_denoiser_state(original, reloaded)
        self.assertEqual(compared["tensor_comparison"], "torch.equal")
        self.assertEqual(compared["compared_parameter_count"], 5)
        self.assertEqual(len(compared["entry_digests"]), 5)
        again = contract.compare_complete_denoiser_state(original, {name: value.clone() for name, value in original.items()})
        self.assertEqual(compared["aggregate_digest"], again["aggregate_digest"])
        reloaded["e"] = reloaded["e"] + 1
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.compare_complete_denoiser_state(original, reloaded)
        self.assertIn("e", caught.exception.detail)
        self.assertNotIn("mismatch: a", caught.exception.detail)

    def test_production_manifest_rejects_synthetic_and_incomplete_evidence(self):
        manifest = production_manifest()
        contract.validate_production_success_manifest(manifest, binding())
        synthetic_observations = []
        for item in manifest["validation_observations"]:
            synthetic_observations.append({key: value for key, value in item.items() if key != "evidence_origin"})
        synthetic = contract.build_control_flow_manifest(
            {
                "opened_biological_data": False,
                "peak_allocated_bytes": 1,
                "peak_reserved_bytes": 2,
                "train_permutation_digest": contract.permutation_digest(list(range(669))),
                "train_updates": [
                    {
                        "applied_norm": 0.2,
                        "clipped": False,
                        "learning_rate": contract.applied_learning_rate(update),
                        "pre_clip_gradient_norm": 0.2,
                        "training_loss": 0.4,
                        "update": update,
                    }
                    for update in range(1, 22)
                ],
                "training_seconds": 1.0,
                "validation_observations": synthetic_observations,
                "validation_review_observations": [
                    contract.classify_validation_change(0.5, 0.6 if update == 7 else 0.5, update) for update in (7, 14, 21)
                ],
                "validation_seconds": 1.0,
                "weight_checkpoints": [
                    {key: value for key, value in item.items() if key != "evidence_origin"}
                    for item in production_manifest()["weight_checkpoints"]
                ],
            }
        )
        with self.assertRaises(contract.M6PilotError):
            contract.validate_production_success_manifest(synthetic, binding())
        hardcoded = copy.deepcopy(manifest)
        hardcoded["environment"]["evidence_origin"] = "hardcoded"
        with self.assertRaises(contract.M6PilotError):
            contract.validate_production_success_manifest(hardcoded, binding())
        incomplete = copy.deepcopy(manifest)
        incomplete["train_update_observations"] = incomplete["train_update_observations"][:-1]
        with self.assertRaises(contract.M6PilotError):
            contract.validate_production_success_manifest(incomplete, binding())
        negative = copy.deepcopy(manifest)
        negative["timing"]["training_seconds"] = "-1"
        with self.assertRaises(contract.M6PilotError):
            contract.validate_production_success_manifest(negative, binding())
        unopened = copy.deepcopy(manifest)
        unopened["data_roles"]["validation_artifacts"]["opened"] = False
        with self.assertRaises(contract.M6PilotError):
            contract.validate_production_success_manifest(unopened, binding())
        gpu = copy.deepcopy(manifest)
        gpu["gpu"]["uuid"] = "GPU-00000000-0000-0000-0000-000000000000"
        with self.assertRaises(contract.M6PilotError):
            contract.validate_production_success_manifest(gpu, binding())
        failed = copy.deepcopy(manifest)
        failed["failure_state"] = {"failure_code": "non_finite_training_loss"}
        with self.assertRaises(contract.M6PilotError):
            contract.validate_production_success_manifest(failed, binding())

    def test_production_manifest_rejects_each_section_mutation(self):
        manifest = production_manifest()
        contract.validate_production_success_manifest(manifest, binding())
        fabricated = copy.deepcopy(manifest)
        fabricated["b1_identity"]["observed_assets"]["b1_unet_weights"]["observation_method"] = "expected_constant"
        with self.assertRaises(contract.M6PilotError):
            contract.validate_production_success_manifest(fabricated, binding())
        labelled = copy.deepcopy(manifest)
        labelled["data_roles"]["train_text"]["observation_method"] = "expected_constant"
        labelled["data_roles"]["train_text"]["observed_sha256"] = contract.TRAIN_TEXT_SHA256
        with self.assertRaises(contract.M6PilotError):
            contract.validate_production_success_manifest(labelled, binding())
        metadata = copy.deepcopy(manifest)
        metadata["environment"]["package_versions_observed"]["observation_method"] = "importlib_metadata"
        with self.assertRaises(contract.M6PilotError):
            contract.validate_production_success_manifest(metadata, binding())
        mutations = []

        def add(mutate):
            mutations.append(mutate)

        add(lambda item: item.__setitem__("manifest_schema_version", "other"))
        add(lambda item: item.__setitem__("schema_version", "other"))
        add(lambda item: item.__setitem__("config_version", "other"))
        add(lambda item: item.__setitem__("experiment_id", "other"))
        add(lambda item: item["b1_identity"]["observed_assets"]["b1_unet_weights"].__setitem__("sha256", digest("drift")))
        add(lambda item: item["b1_identity"]["observed_assets"]["encdec_weights"].__setitem__("byte_size", 1))
        add(lambda item: item["environment"].__setitem__("executable", "/tmp/python"))
        add(lambda item: item["environment"]["package_versions_observed"].__setitem__("torch", "2.1.2"))
        add(lambda item: item["environment"]["package_versions_observed"].__setitem__("python", "3.9.0"))
        add(lambda item: item["environment"]["package_versions_observed"].__setitem__("diffusers", "0.27.2"))
        add(lambda item: item["environment"]["package_versions_observed"].__setitem__("accelerate", "0.26.0"))
        add(lambda item: item["environment"]["package_versions_observed"].__setitem__("transformers", "4.38.2"))
        add(lambda item: item["environment"].__setitem__("hub_offline", False))
        add(lambda item: item["environment"].__setitem__("transformers_offline", False))
        add(lambda item: item["environment"].__setitem__("datasets_offline", False))
        add(lambda item: item["environment"]["cache_isolation"].__setitem__("PYTHONPYCACHEPREFIX", "/tmp/not-isolated"))
        add(lambda item: item["b1_identity"]["observed_assets"]["diffusers_normalization_patch"].__setitem__("sha256", digest("patch")))
        add(lambda item: item["microbatch_accounting"].__setitem__("final_window_microbatch_sizes", [8, 8, 8, 8]))
        add(lambda item: item["microbatch_accounting"].__setitem__("microbatch_count", 80))
        add(lambda item: item["optimizer"].__setitem__("beta1", "0"))
        add(lambda item: item["optimizer"].__setitem__("precision", "fp16"))
        add(lambda item: item["optimizer"].__setitem__("ema_enabled", True))
        add(lambda item: item["optimizer"].__setitem__("weight_variant", "ema"))
        add(lambda item: item["optimizer"].__setitem__("gradient_clip_norm", "0"))
        add(lambda item: item["applied_learning_rate_trace"].__setitem__(0, "0"))
        add(lambda item: item["denoiser_update_evidence"].__setitem__("applied_updates_checked", 20))
        add(lambda item: item["validation_artifacts"].__setitem__("hash_report_sha256", digest("report")))
        add(lambda item: item["validation_artifacts"].__setitem__("sequence_order_source", "expected_constant"))
        add(lambda item: item["validation_artifacts"].__setitem__("noise_shape", [1]))
        add(lambda item: item["timing"].__setitem__("validation_seconds", "100"))
        add(lambda item: item["validation_observations"][0].__setitem__("pair_count", 1))
        add(lambda item: item["validation_review"].__setitem__("automatic_early_stop", True))
        add(lambda item: item["validation_review"].__setitem__("automatic_learning_rate_change", True))
        add(lambda item: item["restart_policy"].__setitem__("resume_supported", True))
        add(lambda item: item.__setitem__("resume_supported", True))
        add(lambda item: item["weight_checkpoints"][0]["saved_hashes"].__setitem__(contract.CHECKPOINT_MEMBERS[0], "not-a-sha256"))
        add(lambda item: item["weight_checkpoints"][0].__setitem__("state_scope", "parameters_only"))
        add(lambda item: item["weight_checkpoints"][0]["state_comparison"].__setitem__("includes_persistent_buffers", False))
        add(lambda item: item["frozen_state"].__setitem__("encdec_parameter_digest_after_update_21", digest("changed")))
        add(lambda item: item["frozen_state"].__setitem__("buffer_digest", digest("denoiser")))
        add(lambda item: item["data_roles"]["ref"].__setitem__("opened", True))
        add(lambda item: item["ref_eval_access"].__setitem__("eval_opened", True))
        add(lambda item: item["repository"].__setitem__("rnagenesis_commit", "c" * 40))
        add(lambda item: item["gpu"].__setitem__("physical_index", 0))
        add(lambda item: item["authorisation"].__setitem__("consumption_state", "not_issued"))
        add(lambda item: item["authorisation"].__setitem__("reuse_permitted", True))
        for code in contract.STOP_CONDITION_CODES:
            add(lambda item, fired=code: item["stop_conditions"][fired].__setitem__("fired", True))
        self.assertGreaterEqual(len(mutations), 40)
        for mutate in mutations:
            candidate = copy.deepcopy(manifest)
            mutate(candidate)
            with self.assertRaises(contract.M6PilotError):
                contract.validate_production_success_manifest(candidate, binding())

    def test_production_manifest_rejects_contradictory_nested_evidence(self):
        manifest = production_manifest()
        contract.validate_production_success_manifest(manifest, binding())
        mutations = []

        def add(mutate):
            mutations.append(mutate)

        add(lambda item: item["validation_observations"][0].__setitem__("relative_to_update_0", {"update": 0}))
        add(lambda item: item["validation_observations"][1]["relative_to_update_0"].__setitem__("delta", "9"))
        add(lambda item: item["validation_observations"][1]["relative_to_update_0"].__setitem__("finite_worsening", False))
        add(lambda item: item["validation_observations"][1]["relative_to_update_0"].__setitem__("human_review_signal", False))
        add(lambda item: item["validation_observations"][1]["relative_to_update_0"].__setitem__("automatic_early_stop", True))
        add(lambda item: item["validation_observations"][1]["relative_to_update_0"].__setitem__("automatic_learning_rate_change", True))
        add(lambda item: item["validation_observations"][1]["relative_to_update_0"].__setitem__("numeric_cutoff", "1"))
        add(lambda item: item["validation_review"]["observations"][0].__setitem__("later", "9"))
        add(lambda item: item["weight_checkpoints"][0]["configuration"].__setitem__("raw_sha256_equal", True))
        add(lambda item: item["weight_checkpoints"][0]["configuration"].__setitem__("configuration_compatible", False))
        add(lambda item: item["weight_checkpoints"][0]["configuration"].__setitem__("original_raw_sha256", "not-a-sha256"))
        add(
            lambda item: item["weight_checkpoints"][0]["state_comparison"].__setitem__(
                "aggregate_digest",
                digest("aggregate"),
            )
        )
        add(
            lambda item: item["weight_checkpoints"][0]["state_comparison"].__setitem__(
                "parameter_names_sha256",
                digest("names"),
            )
        )
        self.assertGreaterEqual(len(mutations), 13)
        for mutate in mutations:
            candidate = copy.deepcopy(manifest)
            mutate(candidate)
            with self.assertRaises(contract.M6PilotError):
                contract.validate_production_success_manifest(candidate, binding())

    def test_asset_and_runtime_drift_fail_closed(self):
        m5 = contract.m5_contract()
        table = {}
        for relative, file_digest, size, role in m5.REQUIRED_MODEL_FILES:
            table[os.path.join("/tmp/m6-assets", relative)] = (size, file_digest, role)
        patch = m5.DIFFUSERS_PATCH_PATH
        table[patch] = (m5.DIFFUSERS_PATCH_SIZE, m5.DIFFUSERS_PATCH_SHA256, "diffusers_normalization_patch")

        class Info(object):
            def __init__(self, size, mode):
                self.st_size = size
                self.st_mode = mode

        def observe(symlink_path=None, directory_path=None, size_path=None, hash_path=None):
            def lstat(path):
                if path not in table:
                    raise FileNotFoundError(path)
                size, _digest, _role = table[path]
                mode = stat.S_IFREG
                if symlink_path == path:
                    mode = stat.S_IFLNK
                elif directory_path == path:
                    mode = stat.S_IFDIR
                extra = 1 if size_path == path else 0
                return Info(size + extra, mode)

            def hash_file(path):
                _size, file_digest, _role = table[path]
                if hash_path == path:
                    return digest("drifted")
                return file_digest

            return contract.observe_required_assets(root="/tmp/m6-assets", lstat=lstat, hash_file=hash_file)

        records = observe()
        self.assertEqual(set(records), set(contract._accepted_asset_table()))
        weight_path = os.path.join("/tmp/m6-assets", [item[0] for item in m5.REQUIRED_MODEL_FILES if item[3] == "b1_unet_weights"][0])
        self.assertEqual(records["b1_unet_weights"]["sha256"], table[weight_path][1])
        self.assertEqual(records["b1_unet_weights"]["byte_size"], table[weight_path][0])
        self.assertEqual(records["diffusers_normalization_patch"]["path"], patch)
        self.assertEqual(records["b1_unet_weights"]["observation_method"], "streamed_sha256")
        with self.assertRaises(contract.M6PilotError):
            observe(hash_path=weight_path)
        with self.assertRaises(contract.M6PilotError):
            observe(size_path=weight_path)
        with self.assertRaises(contract.M6PilotError):
            observe(symlink_path=weight_path)
        with self.assertRaises(contract.M6PilotError):
            observe(directory_path=weight_path)
        with self.assertRaises(contract.M6PilotError):
            observe(hash_path=patch)

        def missing(path):
            raise FileNotFoundError(path)

        with self.assertRaises(contract.M6PilotError):
            contract.observe_required_assets(root="/tmp/m6-assets", lstat=missing, hash_file=lambda path: digest("x"))
        calls = []

        def regular(path):
            calls.append(path)
            return Info(1, stat.S_IFREG)

        with self.assertRaises(contract.M6PilotError):
            contract.assert_pinned_python_file("/tmp/other-python", lstat=regular)
        self.assertEqual(calls, [])
        with self.assertRaises(contract.M6PilotError):
            contract.assert_pinned_python_file(m5.PINNED_PYTHON, lstat=lambda path: Info(1, stat.S_IFDIR))
        runtime = {
            "accelerate": m5.ACCEPTED_RUNTIME_VERSIONS["accelerate"],
            "diffusers": m5.ACCEPTED_RUNTIME_VERSIONS["diffusers"],
            "evidence_origin": "observed",
            "executable": m5.PINNED_PYTHON,
            "observation_method": "module_attribute",
            "python": m5.ACCEPTED_RUNTIME_VERSIONS["python"],
            "torch": m5.ACCEPTED_RUNTIME_VERSIONS["torch"],
            "transformers": m5.ACCEPTED_RUNTIME_VERSIONS["transformers"],
        }
        self.assertIs(contract.assert_observed_runtime(runtime), runtime)
        for key, drifted in (
            ("python", "3.11.0"),
            ("torch", "2.1.2"),
            ("diffusers", "0.27.2"),
            ("accelerate", "1.0.0"),
            ("transformers", "4.38.2"),
            ("executable", "/tmp/python"),
        ):
            candidate = dict(runtime)
            candidate[key] = drifted
            with self.assertRaises(contract.M6PilotError):
                contract.assert_observed_runtime(candidate)
        module_runtime = runner.observe_module_runtime(
            _Version("2.1.2+cu121"),
            _Version("0.25.0"),
            _Version("0.25.0"),
            _Version("4.36.2"),
        )
        self.assertEqual(module_runtime["torch"], "2.1.2+cu121")
        self.assertEqual(module_runtime["observation_method"], "module_attribute")
        self.assertEqual(module_runtime["executable"], sys.executable)

    def test_prepared_runtime_fp32_and_validation_context(self):
        class Accelerator(object):
            def __init__(self, processes=1, device="cuda:0", accumulation=1, precision="no"):
                self.num_processes = processes
                self.device = device
                self.gradient_accumulation_steps = accumulation
                self.mixed_precision = precision

        runner.assert_prepared_runtime(Accelerator(), torch, 1)
        for accelerator, count in (
            (Accelerator(processes=2), 1),
            (Accelerator(), 2),
            (Accelerator(device="cuda:1"), 1),
            (Accelerator(accumulation=4), 1),
            (Accelerator(precision="fp16"), 1),
        ):
            with self.assertRaises(contract.M6PilotError):
                runner.assert_prepared_runtime(accelerator, torch, count)

        class Mixed(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(torch.ones(2, dtype=torch.float32))
                self.register_buffer("half_scale", torch.ones(2, dtype=torch.float16))

            @property
            def dtype(self):
                return torch.float32

        with self.assertRaises(contract.M6PilotError) as caught:
            runner.assert_denoiser_fp32(torch, Mixed())
        self.assertIn("half_scale", caught.exception.detail)
        clean = torch.nn.Linear(2, 2).float()
        clean.register_buffer("index", torch.zeros(1, dtype=torch.int64))
        runner.assert_denoiser_fp32(torch, clean)

        seen = []

        class Denoiser(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(torch.ones(1))

            def forward(self, noisy, timesteps):
                return noisy

        class Stack(object):
            def collate_sequences(self, examples, tokenizer):
                return {"input_ids": torch.zeros(1, 2, dtype=torch.long), "attention_mask": torch.ones(1, 2)}

            def extract_latents(self, encdec, input_ids, attention_mask):
                return torch.ones(1, 2)

            def denoising_mse(self, model, scheduler, latents, noise, timesteps):
                seen.append((torch.is_grad_enabled(), bool(model.training), str(latents.dtype), str(noise.dtype), str(timesteps.dtype)))
                return torch.nn.functional.mse_loss(latents.float() * model.weight, noise.float())

            def place(self, tensor, device):
                return tensor

        denoiser = Denoiser()
        denoiser.train()
        encdec = torch.nn.Linear(1, 1)
        sequences = ["ACGU"] * contract.VALIDATION_SEQUENCE_COUNT
        loaded = {
            "timesteps": torch.zeros(contract.VALIDATION_SEQUENCE_COUNT, contract.VALIDATION_DRAWS, dtype=torch.int64),
            "noise": torch.zeros(contract.VALIDATION_SEQUENCE_COUNT, contract.VALIDATION_DRAWS, 2),
        }
        runner._validation_aggregate(Stack(), Accelerator(), denoiser, encdec, None, sequences, loaded, None, torch)
        self.assertEqual(len(seen), contract.VALIDATION_PAIR_COUNT)
        self.assertTrue(all(item[0] is False and item[1] is False for item in seen))
        self.assertTrue(denoiser.training)
        original = torch.no_grad

        class Open(object):
            def __enter__(self):
                return None

            def __exit__(self, exc_type, exc, traceback):
                return False

        torch.no_grad = lambda: Open()
        try:
            with self.assertRaises(contract.M6PilotError) as caught:
                runner._validation_aggregate(Stack(), Accelerator(), denoiser, encdec, None, sequences, loaded, None, torch)
            self.assertIn("gradients enabled", caught.exception.detail)
        finally:
            torch.no_grad = original
        self.assertTrue(denoiser.training)

    def test_synchronized_clock_orders_sync_before_time(self):
        order = []

        class Cuda(object):
            def is_available(self):
                return True

            def synchronize(self):
                order.append("sync")

        class TorchModule(object):
            def __init__(self):
                self.cuda = Cuda()

        values = iter([10.0, 12.5, 20.0])
        original = runner.time.perf_counter
        runner.time.perf_counter = lambda: next(values)
        try:
            clock = runner.SynchronizedClock(TorchModule())
            self.assertEqual(clock.stamp(), 10.0)
            self.assertEqual(clock.stamp(), 12.5)
        finally:
            runner.time.perf_counter = original
        self.assertEqual(order, ["sync", "sync"])
        hidden = runner.SynchronizedClock(type("Hidden", (), {"cuda": type("Cuda", (), {"is_available": staticmethod(lambda: False)})()})())
        with self.assertRaises(contract.M6PilotError):
            hidden.stamp()

    def test_artifact_loader_ignores_cwd_and_decoy(self):
        previous = os.getcwd()
        os.chdir(self.temp)
        try:
            nested = os.path.join(self.temp, "scripts", "modelling")
            os.makedirs(nested)
            with open(os.path.join(nested, "build_validation_artifacts.py"), "w", encoding="utf-8") as handle:
                handle.write("LOADED = 'decoy'\n")
            module = runner.load_artifact_loader()
            self.assertEqual(os.path.realpath(module.__file__), os.path.realpath(contract.ARTIFACT_LOADER_PATH))
            self.assertFalse(hasattr(module, "LOADED"))
            self.assertTrue(callable(module.load_verified_artifacts))
        finally:
            os.chdir(previous)

    def test_launch_consumes_once_and_records_worker_failure(self):
        seen = {"assets": 0, "python": 0}

        def assets():
            seen["assets"] += 1

        def python_file():
            seen["python"] += 1

        def spawn(argv, env, cwd):
            self.assertEqual(argv[0], contract.m5_contract().PINNED_PYTHON)
            self.assertIn("-B", argv)
            self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
            self.assertEqual(env["HF_HUB_OFFLINE"], "1")
            self.assertEqual(env["TRANSFORMERS_OFFLINE"], "1")
            self.assertEqual(env["HF_DATASETS_OFFLINE"], "1")
            self.assertTrue(env["PYTHONPYCACHEPREFIX"].endswith(contract.m5_contract().PYCACHE_DIRECTORY_NAME))
            self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "1")
            return type("Completed", (), {"returncode": 1})()

        parent = {key: value for key, value in os.environ.items() if key != "CUDA_VISIBLE_DEVICES"}
        authorisation = contract.validate_active_execution(self.active, self.observation, self.temp)
        with self.assertRaises(contract.M6PilotError):
            runner.launch_isolated_worker(
                authorisation,
                run_root=self.temp,
                spawn=spawn,
                asset_observer=assets,
                python_observer=python_file,
                environ=parent,
            )
        self.assertEqual(seen, {"assets": 1, "python": 1})
        failed = self.active["execution"]["output_directory"]
        self.assertTrue(os.path.isfile(os.path.join(failed, contract.FAILURE_RECORD_NAME)))
        with self.assertRaises(contract.M6PilotError) as caught:
            runner.launch_isolated_worker(
                authorisation,
                run_root=self.temp,
                spawn=spawn,
                asset_observer=assets,
                python_observer=python_file,
                environ=parent,
            )
        self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertEqual(seen["assets"], 2)

    def test_cpu_stand_in_authorised_pilot(self):
        authorisation = contract.validate_active_execution(self.active, self.observation, self.temp)
        directory = contract.consume_bound_output_directory(authorisation, self.temp)
        m5 = contract.m5_contract()
        assets = {}
        for relative, file_digest, size, role in m5.REQUIRED_MODEL_FILES:
            assets[role] = _asset_record(role, os.path.join(str(m5.RNAGENESIS_ROOT), relative), size, file_digest)
        assets["diffusers_normalization_patch"] = _asset_record(
            "diffusers_normalization_patch",
            m5.DIFFUSERS_PATCH_PATH,
            m5.DIFFUSERS_PATCH_SIZE,
            m5.DIFFUSERS_PATCH_SHA256,
        )
        versions = m5.ACCEPTED_RUNTIME_VERSIONS
        runtime = {
            "accelerate": versions["accelerate"],
            "diffusers": versions["diffusers"],
            "evidence_origin": "observed",
            "executable": m5.PINNED_PYTHON,
            "observation_method": "module_attribute",
            "python": versions["python"],
            "torch": versions["torch"],
            "transformers": versions["transformers"],
        }
        stack = _CpuStandIn(assets, runtime)
        caches = m5.runtime_isolation_paths(directory)
        previous = {key: os.environ.get(key) for key in caches}
        for key, value in caches.items():
            os.environ[key] = value
        original_verify = contract.verify_bound_file
        original_artifacts = contract.verify_artifact_directory
        original_pinned = contract.pinned_artifact_file_sha256
        pinned_calls = []

        def reject_pinned():
            pinned_calls.append("called")
            raise AssertionError("expected artifact hash was used as an observation")

        def verify_bound(path, role, expected_sha256, expected_count, bound_path, reader):
            return {
                "byte_size": 424242 if role == "TRAIN_TEXT" else 434343,
                "count": expected_count,
                "evidence_origin": "observed",
                "expected_count": expected_count,
                "expected_sha256": expected_sha256,
                "observation_method": "streamed_sha256",
                "opened": ["ACGUACGU"] * expected_count,
                "path": os.path.abspath(path),
                "role": role,
                "sha256": expected_sha256,
            }

        def verify_artifacts(path, bound_path, expected_hashes, loader):
            observed = {}
            for index, name in enumerate(contract.VALIDATION_ARTIFACT_FILES, start=1):
                observed[name] = _asset_record(name, os.path.join(path, name), 1000 + index, expected_hashes[name])
            return {
                "loaded": {
                    "manifest": {"validation_sequence_order_sha256": authorisation["validation_artifact_sha256"]["sequence_order"]},
                    "noise": torch.zeros(contract.VALIDATION_NOISE_SHAPE),
                    "timesteps": torch.zeros(contract.VALIDATION_TIMESTEP_SHAPE, dtype=torch.int64),
                },
                "observed_files": observed,
            }

        contract.verify_bound_file = verify_bound
        contract.verify_artifact_directory = verify_artifacts
        contract.pinned_artifact_file_sha256 = reject_pinned
        try:
            manifest = runner.run_authorized_pilot(authorisation, stack, directory)
        finally:
            contract.verify_bound_file = original_verify
            contract.verify_artifact_directory = original_artifacts
            contract.pinned_artifact_file_sha256 = original_pinned
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertEqual(pinned_calls, [])
        contract.validate_production_success_manifest(manifest, binding())
        self.assertEqual(stack.training_sizes[-4:], [8, 8, 8, 5])
        self.assertEqual(len(stack.training_sizes), contract.MICROBATCH_COUNT)
        self.assertEqual(sum(stack.training_sizes), contract.TRAIN_RECORD_COUNT)
        self.assertEqual(len(stack.validation_flags), contract.VALIDATION_PAIR_COUNT * len(contract.VALIDATION_UPDATES))
        self.assertTrue(all(enabled is False and training is False for enabled, training in stack.validation_flags))
        self.assertEqual(len(stack.training_flags), contract.MICROBATCH_COUNT)
        self.assertTrue(all(item is True for item in stack.training_flags))
        self.assertTrue(stack.denoiser.training)
        self.assertEqual([item["update"] for item in manifest["validation_observations"]], list(contract.VALIDATION_UPDATES))
        self.assertEqual(len(manifest["weight_checkpoints"]), 3)
        self.assertIs(manifest["b1_identity"]["observed_assets"], assets)
        self.assertIs(manifest["environment"]["package_versions_observed"], runtime)
        self.assertEqual(manifest["data_roles"]["train_text"]["observed_byte_size"], 424242)
        self.assertEqual(manifest["data_roles"]["validation_csv"]["observed_byte_size"], 434343)
        self.assertEqual(manifest["validation_artifacts"]["sequence_order_source"], "loaded_manifest")
        self.assertEqual(manifest["timing"]["training_seconds"], "21")
        self.assertEqual(manifest["timing"]["validation_seconds"], "4")
        self.assertEqual(len(manifest["timing"]["training_update_seconds"]), 21)
        self.assertEqual(len(manifest["timing"]["validation_update_seconds"]), 4)
        self.assertNotIn("buffer_digest", manifest["frozen_state"])
        parameter = manifest["frozen_state"]["encdec_parameter_digest_at_initialization"]
        buffer = manifest["frozen_state"]["encdec_persistent_buffer_digest_at_initialization"]
        for update in ("7", "14", "21"):
            self.assertEqual(manifest["frozen_state"]["encdec_parameter_digest_after_update_" + update], parameter)
            self.assertEqual(manifest["frozen_state"]["encdec_persistent_buffer_digest_after_update_" + update], buffer)
        self.assertIn("decoder._cos_cached", manifest["frozen_state"]["rotary_cache_names"])
        self.assertEqual(stack.fake_clock.syncs, 56)

    def _parent_environ(self):
        return {key: value for key, value in os.environ.items() if key != "CUDA_VISIBLE_DEVICES"}

    def _consumed_observation(self):
        observed = copy.deepcopy(self.observation)
        observed["output_exists"] = True
        observed["output_symlink"] = False
        return observed

    def _launch(self, name, spawn):
        config = active_from(self.inactive, self.temp, name=name)
        authorisation = contract.validate_active_execution(config, self.observation, self.temp)
        try:
            result = runner.launch_isolated_worker(
                authorisation,
                run_root=self.temp,
                spawn=spawn,
                asset_observer=lambda: None,
                python_observer=lambda: None,
                environ=self._parent_environ(),
            )
        except contract.M6PilotError as exc:
            return exc, config
        return result, config

    def _failure_document(self, config):
        path = os.path.join(config["execution"]["output_directory"], contract.FAILURE_RECORD_NAME)
        self.assertTrue(os.path.isfile(path))
        self.assertFalse(os.path.islink(path))
        with open(path, "rb") as handle:
            return json.loads(handle.read().decode("utf-8"))

    def test_child_pretraining_failures_keep_their_cause(self):
        def identity_worker(directory, _commit):
            runner.worker_main(
                directory,
                "c" * 40,
                config_loader=lambda: config,
                observation_loader=lambda _loaded: self._consumed_observation(),
                stack_loader=lambda _authorisation: (_ for _ in ()).throw(AssertionError("stack was imported")),
            )

        config = active_from(self.inactive, self.temp, name="m6-child-identity")

        def spawn(argv, env, cwd):
            saved = {key: os.environ.get(key) for key in env}
            os.environ.update(env)
            try:
                try:
                    identity_worker(argv[-2], argv[-1])
                    return type("Completed", (), {"returncode": 0})()
                except contract.M6PilotError:
                    return type("Completed", (), {"returncode": 1})()
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        caught, launched_config = self._launch("m6-child-identity", spawn)
        self.assertEqual(caught.code, "authorisation_commit_invalid")
        failure = self._failure_document(launched_config)
        self.assertEqual(failure["failure_code"], "authorisation_commit_invalid")
        self.assertEqual(failure["fired_stop_condition"], "authorisation_commit_invalid")
        self.assertEqual(failure["stage"], "authorisation_commit")
        self.assertEqual(failure["authorization_commit"], HEAD)
        self.assertEqual(failure["authorization_parent_commit"], PARENT)
        self.assertEqual(failure["executing_implementation_commit"], PARENT)
        self.assertNotEqual(failure["detail"], "worker exited without a passing manifest")
        self.assertFalse(os.path.exists(os.path.join(config["execution"]["output_directory"], contract.SUCCESS_MANIFEST_NAME)))

        def import_worker(directory, commit):
            def stack_loader(_authorisation):
                raise ImportError("pinned stack unavailable")

            runner.worker_main(
                directory,
                commit,
                config_loader=lambda: import_config,
                observation_loader=lambda _loaded: self._consumed_observation(),
                stack_loader=stack_loader,
            )

        import_config = active_from(self.inactive, self.temp, name="m6-child-import")

        def import_spawn(argv, env, cwd):
            saved = {key: os.environ.get(key) for key in env}
            os.environ.update(env)
            try:
                try:
                    import_worker(argv[-2], argv[-1])
                    return type("Completed", (), {"returncode": 0})()
                except contract.M6PilotError:
                    return type("Completed", (), {"returncode": 1})()
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        imported, _unused = self._launch("m6-child-import", import_spawn)
        import_failure = self._failure_document(import_config)
        self.assertEqual(imported.code, "training_stack_import_failed")
        self.assertEqual(import_failure["failure_code"], "training_stack_import_failed")
        self.assertEqual(import_failure["fired_stop_condition"], "training_stack_import_failed")
        self.assertEqual(import_failure["stage"], "training_stack_import")
        self.assertEqual(import_failure["authorization_commit"], HEAD)
        self.assertEqual(import_failure["authorization_parent_commit"], PARENT)
        self.assertEqual(import_failure["executing_implementation_commit"], PARENT)
        self.assertNotEqual(import_failure["failure_code"], "incomplete_evidence_or_manifest")
        self.assertFalse(os.path.exists(os.path.join(import_config["execution"]["output_directory"], contract.SUCCESS_MANIFEST_NAME)))

    def test_parent_reopens_and_validates_claimed_success(self):
        def zero(spawn_body):
            def spawn(argv, env, cwd):
                spawn_body(argv[-2])
                return type("Completed", (), {"returncode": 0})()

            return spawn

        missing, missing_config = self._launch("m6-zero-missing", zero(lambda directory: None))
        self.assertEqual(missing.code, "incomplete_evidence_or_manifest")
        self.assertEqual(self._failure_document(missing_config)["failure_code"], "incomplete_evidence_or_manifest")
        self.assertEqual(self._failure_document(missing_config)["stage"], "worker_success_verification")
        self.assertFalse(os.path.exists(os.path.join(missing_config["execution"]["output_directory"], contract.SUCCESS_MANIFEST_NAME)))

        def write_malformed(directory):
            with open(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME), "wb") as handle:
                handle.write(b"{")

        malformed, malformed_config = self._launch("m6-zero-malformed", zero(write_malformed))
        self.assertEqual(malformed.code, "incomplete_evidence_or_manifest")
        self.assertIn("not valid JSON", self._failure_document(malformed_config)["detail"])
        self.assertFalse(os.path.exists(os.path.join(malformed_config["execution"]["output_directory"], contract.SUCCESS_MANIFEST_NAME)))

        def write_noncanonical(directory):
            blob = json.dumps(production_manifest()).encode("utf-8")
            with open(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME), "wb") as handle:
                handle.write(blob)

        noncanonical, noncanonical_config = self._launch("m6-zero-noncanonical", zero(write_noncanonical))
        self.assertEqual(noncanonical.code, "incomplete_evidence_or_manifest")
        self.assertIn("not canonical JSON", self._failure_document(noncanonical_config)["detail"])
        self.assertFalse(os.path.exists(os.path.join(noncanonical_config["execution"]["output_directory"], contract.SUCCESS_MANIFEST_NAME)))

        def write_both(directory):
            authorisation = contract.validate_active_execution(
                active_from(self.inactive, self.temp, name="m6-zero-both"),
                self.observation,
                self.temp,
            )
            contract.write_atomic_json(directory, contract.SUCCESS_MANIFEST_NAME, production_manifest())
            contract.write_failure_record(
                directory,
                contract.M6PilotError("identity_mismatch", "child identity failed before the parent", stage="consumed_authorisation"),
                authorisation=authorisation,
            )

        both, both_config = self._launch("m6-zero-both", zero(write_both))
        both_failure = self._failure_document(both_config)
        self.assertEqual(both.code, "identity_mismatch")
        self.assertEqual(both_failure["failure_code"], "identity_mismatch")
        self.assertEqual(both_failure["stage"], "consumed_authorisation")
        self.assertEqual(both_failure["detail"], "child identity failed before the parent")
        self.assertNotEqual(both_failure["failure_code"], "incomplete_evidence_or_manifest")
        self.assertFalse(os.path.exists(os.path.join(both_config["execution"]["output_directory"], contract.SUCCESS_MANIFEST_NAME)))

        def write_rejected(directory):
            rejected = production_manifest()
            rejected["resume_supported"] = True
            contract.write_atomic_json(directory, contract.SUCCESS_MANIFEST_NAME, rejected)

        rejected_error, rejected_config = self._launch("m6-zero-rejected", zero(write_rejected))
        self.assertEqual(rejected_error.code, "incomplete_evidence_or_manifest")
        self.assertFalse(os.path.exists(os.path.join(rejected_config["execution"]["output_directory"], contract.SUCCESS_MANIFEST_NAME)))
        self.assertTrue(os.path.isfile(os.path.join(rejected_config["execution"]["output_directory"], contract.FAILURE_RECORD_NAME)))

        def write_valid(directory):
            contract.write_atomic_json(directory, contract.SUCCESS_MANIFEST_NAME, production_manifest())

        passed, passed_config = self._launch("m6-zero-valid", zero(write_valid))
        self.assertEqual(passed, passed_config["execution"]["output_directory"])
        manifest_path = os.path.join(passed_config["execution"]["output_directory"], contract.SUCCESS_MANIFEST_NAME)
        self.assertTrue(os.path.isfile(manifest_path))
        self.assertFalse(os.path.islink(manifest_path))
        self.assertFalse(os.path.exists(os.path.join(passed_config["execution"]["output_directory"], contract.FAILURE_RECORD_NAME)))
        with open(manifest_path, "rb") as handle:
            raw = handle.read()
        parsed = json.loads(raw.decode("utf-8"))
        self.assertEqual(contract.canonical_json(parsed), raw)
        contract.validate_production_success_manifest(parsed, binding())

    def _assert_ordinary_failure(self, config, exc, stage, update=None, microbatch=None):
        self.assertEqual(exc.code, "incomplete_evidence_or_manifest")
        self.assertEqual(exc.detail, ORDINARY_DETAIL)
        self.assertEqual(exc.stage, stage)
        self.assertEqual(exc.update, update)
        self.assertEqual(exc.microbatch, microbatch)
        failure = self._failure_document(config)
        self.assertEqual(failure["failure_code"], "incomplete_evidence_or_manifest")
        self.assertEqual(failure["fired_stop_condition"], "incomplete_evidence_or_manifest")
        self.assertEqual(failure["detail"], ORDINARY_DETAIL)
        self.assertEqual(failure["stage"], stage)
        self.assertEqual(failure["update"], update)
        self.assertEqual(failure["microbatch"], microbatch)
        self.assertEqual(failure["completion_state"], "consumed_failed")
        self.assertEqual(failure["consumption_state"], "consumed_failed")
        self.assertTrue(failure["non_resumable"])
        self.assertFalse(failure["resume_supported"])
        self.assertFalse(failure["pilot_completed"])
        self.assertFalse(failure["scientific_run_completed"])
        self.assertFalse(failure["manifest_written"])
        self.assertFalse(failure["retained_checkpoints_exist"])
        rendered = json.dumps(failure)
        self.assertNotIn(RNA_MESSAGE, rendered)
        self.assertNotIn(RNA_MESSAGE, exc.detail)
        self.assertNotIn("Traceback", rendered)
        directory = config["execution"]["output_directory"]
        self.assertFalse(os.path.exists(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)))
        for _root, _dirs, filenames in os.walk(directory):
            for filename in filenames:
                self.assertNotIn("traceback", filename.lower())
        return failure

    def _install_input_stubs(self, authorisation, bound):
        original_verify = contract.verify_bound_file
        original_artifacts = contract.verify_artifact_directory

        def verify_bound(path, role, expected_sha256, expected_count, bound_path, reader):
            if bound is not None:
                return bound(path, role, expected_sha256, expected_count, bound_path, reader)
            return {
                "byte_size": 8,
                "count": expected_count,
                "evidence_origin": "observed",
                "expected_count": expected_count,
                "expected_sha256": expected_sha256,
                "observation_method": "streamed_sha256",
                "opened": ["ACGUACGU"] * expected_count,
                "path": os.path.abspath(path),
                "role": role,
                "sha256": expected_sha256,
            }

        def verify_artifacts(path, bound_path, expected_hashes, loader):
            observed = {}
            for index, name in enumerate(contract.VALIDATION_ARTIFACT_FILES, start=1):
                observed[name] = _asset_record(name, os.path.join(path, name), 1000 + index, expected_hashes[name])
            return {
                "loaded": {
                    "manifest": {
                        "validation_sequence_order_sha256": authorisation["validation_artifact_sha256"]["sequence_order"]
                    },
                    "noise": torch.zeros(contract.VALIDATION_NOISE_SHAPE),
                    "timesteps": torch.zeros(contract.VALIDATION_TIMESTEP_SHAPE, dtype=torch.int64),
                },
                "observed_files": observed,
            }

        contract.verify_bound_file = verify_bound
        contract.verify_artifact_directory = verify_artifacts
        return original_verify, original_artifacts

    def _restore_input_stubs(self, originals):
        contract.verify_bound_file, contract.verify_artifact_directory = originals

    def test_generic_runtime_identity_failure_records_class_and_stage(self):
        config = active_from(self.inactive, self.temp, name="m6-generic-runtime")
        authorisation = contract.validate_active_execution(config, self.observation, self.temp)
        directory = config["execution"]["output_directory"]

        class Stack(object):
            production_identities = True
            cpu_stand_in = True

            def torch(self):
                with open(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME), "wb") as handle:
                    handle.write(b"{}\n")
                raise RuntimeError(RNA_MESSAGE)

        with self.assertRaises(contract.M6PilotError) as caught:
            runner.execute_authorized_worker(authorisation, Stack(), run_root=self.temp)
        failure = self._assert_ordinary_failure(config, caught.exception, "runtime_identity")
        failure_path = os.path.join(directory, contract.FAILURE_RECORD_NAME)
        with open(failure_path, "rb") as handle:
            preserved = handle.read()
        with self.assertRaises(contract.M6PilotError) as reuse:
            runner.execute_authorized_worker(authorisation, Stack(), run_root=self.temp)
        self.assertEqual(reuse.exception.code, "authorization_reuse")
        with open(failure_path, "rb") as handle:
            self.assertEqual(handle.read(), preserved)
        self.assertEqual(failure["stage"], "runtime_identity")
        self.assertIsNone(failure["update"])
        self.assertIsNone(failure["microbatch"])

    def test_generic_asset_and_biological_input_failures_keep_their_stage(self):
        assets, runtime = _pilot_assets()

        class AssetStack(object):
            production_identities = True
            cpu_stand_in = True

            def torch(self):
                return torch

            def observe_assets(self):
                raise RuntimeError(RNA_MESSAGE)

        asset_config = active_from(self.inactive, self.temp, name="m6-generic-assets")
        asset_auth = contract.validate_active_execution(asset_config, self.observation, self.temp)
        with self.assertRaises(contract.M6PilotError) as asset_caught:
            runner.execute_authorized_worker(asset_auth, AssetStack(), run_root=self.temp)
        self._assert_ordinary_failure(asset_config, asset_caught.exception, "asset_identity")

        class BiologicalStack(object):
            production_identities = True
            cpu_stand_in = True

            def torch(self):
                return torch

            def observe_assets(self):
                return assets

            def observe_runtime(self):
                return runtime

            def read_train_sequences(self, path):
                raise AssertionError("biological reader was called")

            def read_validation_cores(self, path):
                raise AssertionError("biological reader was called")

            def load_verified_artifacts(self, path):
                raise AssertionError("artifact loader was called")

        biological_config = active_from(self.inactive, self.temp, name="m6-generic-biological")
        biological_auth = contract.validate_active_execution(biological_config, self.observation, self.temp)

        def reject_bound(*_args):
            raise RuntimeError(RNA_MESSAGE)

        originals = self._install_input_stubs(biological_auth, reject_bound)
        try:
            with self.assertRaises(contract.M6PilotError) as biological_caught:
                runner.execute_authorized_worker(biological_auth, BiologicalStack(), run_root=self.temp)
        finally:
            self._restore_input_stubs(originals)
        self._assert_ordinary_failure(biological_config, biological_caught.exception, "biological_inputs")

    def test_generic_model_load_and_microbatch_failures_keep_context(self):
        assets, runtime = _pilot_assets()

        class ModelStack(object):
            production_identities = True
            cpu_stand_in = True

            def torch(self):
                return torch

            def observe_assets(self):
                return assets

            def observe_runtime(self):
                return runtime

            def read_train_sequences(self, path):
                raise AssertionError("biological reader was called")

            def read_validation_cores(self, path):
                raise AssertionError("biological reader was called")

            def load_verified_artifacts(self, path):
                raise AssertionError("artifact loader was called")

            def load_frozen_encdec(self, path):
                raise RuntimeError(RNA_MESSAGE)

        model_config = active_from(self.inactive, self.temp, name="m6-generic-model")
        model_auth = contract.validate_active_execution(model_config, self.observation, self.temp)
        originals = self._install_input_stubs(model_auth, None)
        try:
            with self.assertRaises(contract.M6PilotError) as model_caught:
                runner.execute_authorized_worker(model_auth, ModelStack(), run_root=self.temp)
        finally:
            self._restore_input_stubs(originals)
        self._assert_ordinary_failure(model_config, model_caught.exception, "model_load")

        class MicrobatchStack(_CpuStandIn):
            enforce_runtime_isolation = False

            def denoising_mse(self, model, scheduler, latents, noise, timesteps):
                if model.training:
                    raise RuntimeError(RNA_MESSAGE)
                return _CpuStandIn.denoising_mse(self, model, scheduler, latents, noise, timesteps)

        micro_config = active_from(self.inactive, self.temp, name="m6-generic-microbatch")
        micro_auth = contract.validate_active_execution(micro_config, self.observation, self.temp)
        originals = self._install_input_stubs(micro_auth, None)
        try:
            with self.assertRaises(contract.M6PilotError) as micro_caught:
                runner.execute_authorized_worker(
                    micro_auth,
                    MicrobatchStack(assets, runtime),
                    run_root=self.temp,
                )
        finally:
            self._restore_input_stubs(originals)
        self._assert_ordinary_failure(micro_config, micro_caught.exception, "microbatch", update=1, microbatch=1)

    def test_precise_pilot_error_context_is_not_rewritten(self):
        config = active_from(self.inactive, self.temp, name="m6-precise-context")
        authorisation = contract.validate_active_execution(config, self.observation, self.temp)

        class Stack(object):
            production_identities = True

            def torch(self):
                raise contract.M6PilotError(
                    "identity_mismatch",
                    "the bound runtime identity drifted",
                    stage="runtime_identity",
                    update=9,
                    microbatch=3,
                )

        with self.assertRaises(contract.M6PilotError) as caught:
            runner.execute_authorized_worker(authorisation, Stack(), run_root=self.temp)
        self.assertEqual(caught.exception.code, "identity_mismatch")
        self.assertEqual(caught.exception.detail, "the bound runtime identity drifted")
        self.assertEqual(caught.exception.stage, "runtime_identity")
        self.assertEqual(caught.exception.update, 9)
        self.assertEqual(caught.exception.microbatch, 3)
        failure = self._failure_document(config)
        self.assertEqual(failure["failure_code"], "identity_mismatch")
        self.assertEqual(failure["fired_stop_condition"], "identity_mismatch")
        self.assertEqual(failure["detail"], "the bound runtime identity drifted")
        self.assertEqual(failure["stage"], "runtime_identity")
        self.assertEqual(failure["update"], 9)
        self.assertEqual(failure["microbatch"], 3)
        self.assertNotIn("exception_class=", failure["detail"])
        self.assertNotIn(RNA_MESSAGE, json.dumps(failure))
        self.assertFalse(os.path.exists(os.path.join(config["execution"]["output_directory"], contract.SUCCESS_MANIFEST_NAME)))

    def test_parent_preserves_child_generic_failure_record(self):
        config = active_from(self.inactive, self.temp, name="m6-child-generic")

        def stack_loader(_authorisation):
            class Stack(object):
                cpu_stand_in = True

                def torch(self):
                    raise RuntimeError(RNA_MESSAGE)

            return Stack()

        def worker(directory, commit):
            runner.worker_main(
                directory,
                commit,
                config_loader=lambda: config,
                observation_loader=lambda _loaded: self._consumed_observation(),
                stack_loader=stack_loader,
            )

        captured = {}

        def spawn(argv, env, cwd):
            saved = {key: os.environ.get(key) for key in env}
            os.environ.update(env)
            try:
                try:
                    worker(argv[-2], argv[-1])
                    return type("Completed", (), {"returncode": 0})()
                except contract.M6PilotError:
                    path = os.path.join(argv[-2], contract.FAILURE_RECORD_NAME)
                    with open(path, "rb") as handle:
                        captured["record"] = handle.read()
                    return type("Completed", (), {"returncode": 1})()
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        caught, launched = self._launch("m6-child-generic", spawn)
        directory = launched["execution"]["output_directory"]
        failure_path = os.path.join(directory, contract.FAILURE_RECORD_NAME)
        with open(failure_path, "rb") as handle:
            preserved = handle.read()
        self.assertEqual(preserved, captured["record"])
        self.assertEqual(caught.code, "incomplete_evidence_or_manifest")
        self.assertEqual(caught.detail, ORDINARY_DETAIL)
        self.assertEqual(caught.stage, "runtime_identity")
        self.assertIsNone(caught.update)
        self.assertIsNone(caught.microbatch)
        self.assertNotEqual(caught.detail, "worker exited without a passing manifest")
        self.assertNotEqual(caught.stage, "worker_launch")
        failure = json.loads(preserved.decode("utf-8"))
        self.assertEqual(failure["failure_code"], "incomplete_evidence_or_manifest")
        self.assertEqual(failure["detail"], ORDINARY_DETAIL)
        self.assertEqual(failure["stage"], "runtime_identity")
        self.assertIsNone(failure["update"])
        self.assertIsNone(failure["microbatch"])
        self.assertNotIn(RNA_MESSAGE, preserved.decode("utf-8"))
        self.assertNotIn("Traceback", preserved.decode("utf-8"))
        self.assertFalse(os.path.exists(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)))
        for _root, _dirs, filenames in os.walk(directory):
            for filename in filenames:
                self.assertNotIn("traceback", filename.lower())

    def test_final_cuda_rng_read_fails_closed(self):
        proxy_cuda = _RaisingCuda()
        proxy = _ProxyTorch(proxy_cuda)
        initial = torch.zeros(4, dtype=torch.uint8)
        with self.assertRaises(contract.M6PilotError) as direct:
            runner._final_stream_digests(proxy, {"read_cuda_rng": True, "torch_cuda_state": initial})
        self.assertEqual(direct.exception.code, "cuda_rng_final_observation_failed")
        self.assertEqual(direct.exception.stage, "rng_final_observation")
        self.assertEqual(proxy_cuda.reads, 1)
        self.assertFalse(hasattr(direct.exception, "torch_cuda_final_digest"))

        authorisation = contract.validate_active_execution(self.active, self.observation, self.temp)
        directory = self.active["execution"]["output_directory"]
        m5 = contract.m5_contract()
        assets = {}
        for relative, file_digest, size, role in m5.REQUIRED_MODEL_FILES:
            assets[role] = _asset_record(role, os.path.join(str(m5.RNAGENESIS_ROOT), relative), size, file_digest)
        assets["diffusers_normalization_patch"] = _asset_record(
            "diffusers_normalization_patch",
            m5.DIFFUSERS_PATCH_PATH,
            m5.DIFFUSERS_PATCH_SIZE,
            m5.DIFFUSERS_PATCH_SHA256,
        )
        versions = m5.ACCEPTED_RUNTIME_VERSIONS
        runtime = {
            "accelerate": versions["accelerate"],
            "diffusers": versions["diffusers"],
            "evidence_origin": "observed",
            "executable": m5.PINNED_PYTHON,
            "observation_method": "module_attribute",
            "python": versions["python"],
            "torch": versions["torch"],
            "transformers": versions["transformers"],
        }
        integrated_cuda = _RaisingCuda()
        stack = _FailingFinalCuda(assets, runtime, _ProxyTorch(integrated_cuda))
        caches = m5.runtime_isolation_paths(directory)
        previous = {key: os.environ.get(key) for key in caches}
        for key, value in caches.items():
            os.environ[key] = value
        original_verify = contract.verify_bound_file
        original_artifacts = contract.verify_artifact_directory
        original_pinned = contract.pinned_artifact_file_sha256

        def verify_bound(path, role, expected_sha256, expected_count, bound_path, reader):
            return {
                "byte_size": 8,
                "count": expected_count,
                "evidence_origin": "observed",
                "expected_count": expected_count,
                "expected_sha256": expected_sha256,
                "observation_method": "streamed_sha256",
                "opened": ["ACGUACGU"] * expected_count,
                "path": os.path.abspath(path),
                "role": role,
                "sha256": expected_sha256,
            }

        def verify_artifacts(path, bound_path, expected_hashes, loader):
            observed = {}
            for index, name in enumerate(contract.VALIDATION_ARTIFACT_FILES, start=1):
                observed[name] = _asset_record(name, os.path.join(path, name), 1000 + index, expected_hashes[name])
            return {
                "loaded": {
                    "manifest": {"validation_sequence_order_sha256": authorisation["validation_artifact_sha256"]["sequence_order"]},
                    "noise": torch.zeros(contract.VALIDATION_NOISE_SHAPE),
                    "timesteps": torch.zeros(contract.VALIDATION_TIMESTEP_SHAPE, dtype=torch.int64),
                },
                "observed_files": observed,
            }

        contract.verify_bound_file = verify_bound
        contract.verify_artifact_directory = verify_artifacts
        contract.pinned_artifact_file_sha256 = lambda: (_ for _ in ()).throw(AssertionError("pinned hash used as observation"))
        try:
            with self.assertRaises(contract.M6PilotError) as caught:
                runner.execute_authorized_worker(authorisation, stack, run_root=self.temp)
        finally:
            contract.verify_bound_file = original_verify
            contract.verify_artifact_directory = original_artifacts
            contract.pinned_artifact_file_sha256 = original_pinned
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertEqual(caught.exception.code, "cuda_rng_final_observation_failed")
        self.assertEqual(caught.exception.stage, "rng_final_observation")
        self.assertEqual(integrated_cuda.reads, 1)
        failure = self._failure_document(self.active)
        self.assertEqual(failure["failure_code"], "cuda_rng_final_observation_failed")
        self.assertEqual(failure["fired_stop_condition"], "cuda_rng_final_observation_failed")
        self.assertEqual(failure["stage"], "rng_final_observation")
        self.assertNotIn("torch_cuda_final_digest", json.dumps(failure))
        self.assertFalse(os.path.exists(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)))

    def test_pinned_adapter_rejects_strings_at_every_path_boundary(self):
        trainer = _PathRejectingTrainer()
        artifacts = _ConvertingArtifactLoader("a" * 64)
        stack = runner.PinnedTrainingStack(trainer, artifacts, object())
        root = Path(self.temp) / "adapter-boundary"
        samples = {
            "read_train_sequences": root / "train.txt",
            "read_validation_cores": root / "validation.csv",
            "load_frozen_encdec": root / "encdec",
            "load_b1_denoiser": root / "b1",
            "load_scheduler": root / "scheduler",
            "save_diffusers_checkpoint": root / "checkpoint",
            "reload_denoiser": root / "reload",
            "load_verified_artifacts": root / "artifacts",
        }
        stack.read_train_sequences(str(samples["read_train_sequences"]))
        stack.read_validation_cores(str(samples["read_validation_cores"]))
        stack.load_frozen_encdec(str(samples["load_frozen_encdec"]))
        stack.load_b1_denoiser(str(samples["load_b1_denoiser"]))
        stack.load_scheduler(str(samples["load_scheduler"]))
        stack.save_checkpoint(object(), object(), str(samples["save_diffusers_checkpoint"]))
        reloaded = stack.reload_denoiser(str(samples["reload_denoiser"]))
        loaded = stack.load_verified_artifacts(str(samples["load_verified_artifacts"]))
        self.assertIs(stack.load_verified_artifacts.__func__, _ConvertingArtifactLoader.load_verified_artifacts)
        self.assertIs(stack.load_verified_artifacts.__self__, artifacts)
        self.assertEqual(loaded, {"converted": True})
        self.assertIsInstance(reloaded, _TinyDenoiser)
        self.assertEqual(
            [item[0] for item in trainer.received],
            [
                "read_train_sequences",
                "read_validation_cores",
                "load_frozen_encdec",
                "load_b1_denoiser",
                "load_scheduler",
                "save_diffusers_checkpoint",
                "TransformerDenoiser.from_pretrained",
            ],
        )
        for name, received in (
            ("read_train_sequences", trainer.received[0]),
            ("read_validation_cores", trainer.received[1]),
            ("load_frozen_encdec", trainer.received[2]),
            ("load_b1_denoiser", trainer.received[3]),
            ("load_scheduler", trainer.received[4]),
            ("save_diffusers_checkpoint", trainer.received[5]),
            ("TransformerDenoiser.from_pretrained", trainer.received[6]),
        ):
            self.assertIsInstance(received[1], Path)
            self.assertEqual(received[1], samples[name if name != "TransformerDenoiser.from_pretrained" else "reload_denoiser"])
        self.assertEqual(trainer.received[0][2], True)
        self.assertEqual(trainer.received[1][2], True)
        self.assertEqual(trainer.received[6][2], "unet")
        self.assertEqual(artifacts.converted, [samples["load_verified_artifacts"]])
        self.assertIsInstance(artifacts.converted[0], Path)
        with self.assertRaises(AttributeError):
            trainer.read_train_sequences(str(samples["read_train_sequences"]), True)
        with self.assertRaises(AttributeError):
            trainer.read_validation_cores(str(samples["read_validation_cores"]), True)
        with self.assertRaises(AttributeError):
            trainer.load_frozen_encdec(str(samples["load_frozen_encdec"]))
        with self.assertRaises(AttributeError):
            trainer.load_b1_denoiser(str(samples["load_b1_denoiser"]))
        with self.assertRaises(AttributeError):
            trainer.load_scheduler(str(samples["load_scheduler"]))
        with self.assertRaises(AttributeError):
            trainer.save_diffusers_checkpoint(object(), object(), str(samples["save_diffusers_checkpoint"]))
        with self.assertRaises(AttributeError):
            trainer.TransformerDenoiser.from_pretrained(str(samples["reload_denoiser"]), subfolder="unet")
        stack.load_verified_artifacts(samples["load_verified_artifacts"])
        self.assertEqual(artifacts.converted[-1], samples["load_verified_artifacts"])
        self.assertEqual(trainer.opened_paths, [])

    def test_mocked_pilot_reaches_checkpoint_save_with_path_objects(self):
        config = active_from(self.inactive, self.temp, name="m6-path-boundary")
        authorisation = contract.validate_active_execution(config, self.observation, self.temp)
        directory = contract.consume_bound_output_directory(authorisation, self.temp)
        assets, runtime = _pilot_assets()
        trainer = _PathRejectingTrainer()
        artifacts = _ConvertingArtifactLoader(authorisation["validation_artifact_sha256"]["sequence_order"])
        stack = _PathBoundaryStack(trainer, artifacts, assets, runtime)
        caches = contract.m5_contract().runtime_isolation_paths(directory)
        previous = {key: os.environ.get(key) for key in caches}
        for key, value in caches.items():
            os.environ[key] = value
        original_verify = contract.verify_bound_file
        original_artifacts = contract.verify_artifact_directory

        def verify_bound(path, role, expected_sha256, expected_count, bound_path, reader):
            opened = reader(path)
            self.assertEqual(len(opened), expected_count)
            return {
                "byte_size": 424242 if role == "TRAIN_TEXT" else 434343,
                "count": expected_count,
                "evidence_origin": "observed",
                "expected_count": expected_count,
                "expected_sha256": expected_sha256,
                "observation_method": "streamed_sha256",
                "opened": opened,
                "path": os.path.abspath(path),
                "role": role,
                "sha256": expected_sha256,
            }

        def verify_artifacts(path, bound_path, expected_hashes, loader):
            loaded = loader(path)
            observed = {}
            for index, name in enumerate(contract.VALIDATION_ARTIFACT_FILES, start=1):
                observed[name] = _asset_record(name, os.path.join(path, name), 1000 + index, expected_hashes[name])
            return {"loaded": loaded, "observed_files": observed}

        contract.verify_bound_file = verify_bound
        contract.verify_artifact_directory = verify_artifacts
        try:
            manifest = runner.run_authorized_pilot(authorisation, stack, directory)
        finally:
            contract.verify_bound_file = original_verify
            contract.verify_artifact_directory = original_artifacts
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        contract.validate_production_success_manifest(manifest, binding())
        self.assertEqual(
            [item[0] for item in trainer.received[:5]],
            [
                "read_train_sequences",
                "read_validation_cores",
                "load_frozen_encdec",
                "load_b1_denoiser",
                "load_scheduler",
            ],
        )
        saves = [item for item in trainer.received if item[0] == "save_diffusers_checkpoint"]
        reloads = [item for item in trainer.received if item[0] == "TransformerDenoiser.from_pretrained"]
        self.assertEqual(len(saves), 3)
        self.assertEqual(len(reloads), 3)
        for item in trainer.received:
            self.assertIsInstance(item[1], Path)
        self.assertEqual(trainer.received[0][2], True)
        self.assertEqual(trainer.received[1][2], True)
        self.assertTrue(all(item[2] == "unet" for item in reloads))
        self.assertEqual(artifacts.converted, [Path(authorisation["validation_artifact_directory"])])
        self.assertEqual(trainer.opened_paths, [])
        self.assertEqual(len(manifest["weight_checkpoints"]), 3)
        self.assertFalse(os.path.exists(os.path.join(directory, contract.FAILURE_RECORD_NAME)))


class _Version(object):
    def __init__(self, version):
        self.__version__ = version


class _Sample(object):
    def __init__(self, value):
        self.sample = value


class _CpuStandIn(object):
    production_identities = True
    cpu_stand_in = True
    enforce_runtime_isolation = True

    def __init__(self, assets, runtime):
        self.assets = assets
        self.runtime = runtime
        self.denoiser = _TinyDenoiser()
        self.encdec = _TinyEncDec()
        self.training_sizes = []
        self.validation_flags = []
        self.training_flags = []
        self.fake_clock = _FakeClock()

    def torch(self):
        return torch

    def clock(self):
        return self.fake_clock

    def observe_assets(self):
        return self.assets

    def observe_runtime(self):
        return self.runtime

    def cuda_device_count(self):
        return 1

    def place(self, tensor, device):
        return tensor

    def cuda_rng_state(self):
        return torch.zeros(4, dtype=torch.uint8)

    def accelerator(self):
        return _Accelerator()

    def load_frozen_encdec(self, path):
        return self.encdec

    def load_b1_denoiser(self, path):
        return self.denoiser

    def load_scheduler(self, path):
        return type("Scheduler", (), {"config": type("Config", (), {"num_train_timesteps": 1000})()})()

    def build_adamw(self, denoiser, learning_rate):
        return torch.optim.AdamW(
            denoiser.parameters(),
            lr=learning_rate,
            betas=(contract.ADAMW_BETA1, contract.ADAMW_BETA2),
            eps=contract.ADAMW_EPSILON,
            weight_decay=contract.ADAMW_WEIGHT_DECAY,
        )

    def read_train_sequences(self, path):
        raise AssertionError("biological reader was called")

    def read_validation_cores(self, path):
        raise AssertionError("biological reader was called")

    def load_verified_artifacts(self, path):
        raise AssertionError("artifact loader was called")

    def load_tokenizer(self):
        return object()

    def collate_sequences(self, examples, tokenizer):
        size = len(examples)
        if size != 1:
            self.training_sizes.append(size)
        return {
            "input_ids": torch.zeros(size, 4, dtype=torch.long),
            "attention_mask": torch.ones(size, 4, dtype=torch.bool),
        }

    def extract_latents(self, encdec, input_ids, attention_mask):
        encdec.decoder._cos_cached.add_(1)
        return torch.ones(input_ids.shape[0], 32, 160)

    def sample_train_diffusion(self, batch_size, generator, num_train_timesteps, device):
        timesteps = torch.zeros(batch_size, dtype=torch.long)
        noise = torch.zeros(batch_size, 32, 160)
        return timesteps, noise

    def denoising_mse(self, model, scheduler, latents, noise, timesteps):
        if model.training:
            self.training_flags.append(torch.is_grad_enabled())
        else:
            self.validation_flags.append((torch.is_grad_enabled(), bool(model.training)))
        if latents.dtype != torch.float32 or noise.dtype != torch.float32 or timesteps.dtype != torch.int64:
            raise AssertionError("validation dtype drifted")
        prediction = latents.float() * (
            model.w1.sum() + model.w2.sum() + model.w3.sum() + model.w4.sum()
        )
        return torch.nn.functional.mse_loss(prediction, noise.float())

    def save_checkpoint(self, denoiser, scheduler, directory):
        for name in contract.CHECKPOINT_MEMBERS:
            target = os.path.join(directory, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(name.encode("ascii"))

    def reload_denoiser(self, directory):
        fresh = _TinyDenoiser()
        fresh.load_state_dict(self.denoiser.state_dict())
        fresh.config = {"_name_or_path": "saved", "_class_name": "UNet", "layers": 2}
        return fresh


class _TinyDenoiser(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.w1 = torch.nn.Parameter(torch.tensor([0.2, 0.3, 0.4, 0.5]))
        self.w2 = torch.nn.Parameter(torch.tensor([0.2, 0.3]))
        self.w3 = torch.nn.Parameter(torch.tensor([0.4, 0.5]))
        self.w4 = torch.nn.Parameter(torch.tensor([0.6]))
        self.register_buffer("scale", torch.ones(2))
        self.register_buffer("index", torch.zeros(1, dtype=torch.int64))
        self.config = {"_name_or_path": "original", "_class_name": "UNet", "layers": 2}


class _TinyEncDec(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = torch.nn.Linear(2, 2)
        for parameter in self.parameters():
            parameter.requires_grad_(False)
        self.decoder = torch.nn.Identity()
        self.register_buffer("persistent_scale", torch.ones(2))
        self.decoder.register_buffer("_cos_cached", torch.zeros(2))
        self.eval()


class _Accelerator(object):
    num_processes = 1
    gradient_accumulation_steps = 1
    mixed_precision = "no"
    device = "cuda:0"

    def prepare(self, denoiser, optimizer):
        return denoiser, optimizer

    def backward(self, loss):
        loss.backward()

    def unwrap_model(self, model):
        return model


class _FakeClock(object):
    def __init__(self):
        self.now = 0.0
        self.syncs = 0

    def stamp(self):
        self.syncs += 1
        self.now += 1.0
        return self.now


class _PathRejectingTrainer(object):
    """Pinned-interface stand-in. Path methods reject strings and record the object."""

    def __init__(self):
        self.received = []
        self.opened_paths = []
        self.denoiser = _TinyDenoiser()
        self.encdec = _TinyEncDec()
        self.training_sizes = []
        self.validation_flags = []
        self.training_flags = []
        outer = self

        class TransformerDenoiser(object):
            @staticmethod
            def from_pretrained(directory, subfolder=None):
                outer._require_path(directory)
                outer.received.append(("TransformerDenoiser.from_pretrained", directory, subfolder))
                fresh = _TinyDenoiser()
                fresh.load_state_dict(outer.denoiser.state_dict())
                fresh.config = {"_name_or_path": "saved", "_class_name": "UNet", "layers": 2}
                return fresh

        self.TransformerDenoiser = TransformerDenoiser

    def _require_path(self, path):
        if not isinstance(path, Path):
            path.is_absolute()
            raise TypeError("pinned path was not pathlib.Path")

    def read_train_sequences(self, path, enforce_frozen_hash):
        self._require_path(path)
        self.received.append(("read_train_sequences", path, enforce_frozen_hash))
        return ["ACGUACGU"] * contract.TRAIN_RECORD_COUNT

    def read_validation_cores(self, path, enforce_frozen_hash):
        self._require_path(path)
        self.received.append(("read_validation_cores", path, enforce_frozen_hash))
        return ["ACGUACGU"] * contract.VALIDATION_SEQUENCE_COUNT

    def load_frozen_encdec(self, path):
        self._require_path(path)
        self.received.append(("load_frozen_encdec", path))
        return self.encdec

    def load_b1_denoiser(self, path):
        self._require_path(path)
        self.received.append(("load_b1_denoiser", path))
        return self.denoiser

    def load_scheduler(self, path):
        self._require_path(path)
        self.received.append(("load_scheduler", path))
        return type("Scheduler", (), {"config": type("Config", (), {"num_train_timesteps": 1000})()})()

    def save_diffusers_checkpoint(self, denoiser, scheduler, directory):
        if not isinstance(directory, Path):
            directory.mkdir(parents=True, exist_ok=True)
        self.received.append(("save_diffusers_checkpoint", directory))
        for name in contract.CHECKPOINT_MEMBERS:
            target = directory.joinpath(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(name.encode("ascii"))

    def build_adamw(self, denoiser, learning_rate):
        return torch.optim.AdamW(
            denoiser.parameters(),
            lr=learning_rate,
            betas=(contract.ADAMW_BETA1, contract.ADAMW_BETA2),
            eps=contract.ADAMW_EPSILON,
            weight_decay=contract.ADAMW_WEIGHT_DECAY,
        )

    def assert_optimizer_membership(self, optimizer, denoiser, encdec):
        return True

    def collate_sequences(self, examples, tokenizer):
        size = len(examples)
        if size != 1:
            self.training_sizes.append(size)
        return {
            "input_ids": torch.zeros(size, 4, dtype=torch.long),
            "attention_mask": torch.ones(size, 4, dtype=torch.bool),
        }

    def extract_latents(self, encdec, input_ids, attention_mask):
        encdec.decoder._cos_cached.add_(1)
        return torch.ones(input_ids.shape[0], 32, 160)

    def sample_train_diffusion(self, batch_size, generator, num_train_timesteps, device):
        timesteps = torch.zeros(batch_size, dtype=torch.long)
        noise = torch.zeros(batch_size, 32, 160)
        return timesteps, noise

    def denoising_mse(self, model, scheduler, latents, noise, timesteps, dtype=None):
        if model.training:
            self.training_flags.append(torch.is_grad_enabled())
        else:
            self.validation_flags.append((torch.is_grad_enabled(), bool(model.training)))
        if latents.dtype != torch.float32 or noise.dtype != torch.float32 or timesteps.dtype != torch.int64:
            raise AssertionError("validation dtype drifted")
        prediction = latents.float() * (model.w1.sum() + model.w2.sum() + model.w3.sum() + model.w4.sum())
        return torch.nn.functional.mse_loss(prediction, noise.float())


class _ConvertingArtifactLoader(object):
    """Stand-in for the loader's existing ``Path(directory)`` conversion."""

    def __init__(self, sequence_order):
        self.sequence_order = sequence_order
        self.converted = []

    def load_verified_artifacts(self, directory, expected_source_sha256=None):
        root = Path(directory)
        self.converted.append(root)
        if self.sequence_order == "a" * 64:
            return {"converted": True}
        return {
            "manifest": {"validation_sequence_order_sha256": self.sequence_order},
            "noise": torch.zeros(contract.VALIDATION_NOISE_SHAPE),
            "timesteps": torch.zeros(contract.VALIDATION_TIMESTEP_SHAPE, dtype=torch.int64),
        }


class _PathBoundaryStack(runner.PinnedTrainingStack):
    """Real path adapter with CPU stand-ins for assets, runtime, and CUDA."""

    cpu_stand_in = True

    def __init__(self, trainer, artifacts, assets, runtime):
        super().__init__(trainer, artifacts, object())
        self._assets = assets
        self._runtime = runtime
        self.fake_clock = _FakeClock()

    def torch(self):
        return torch

    def clock(self):
        return self.fake_clock

    def observe_assets(self):
        return self._assets

    def observe_runtime(self):
        return self._runtime

    def cuda_device_count(self):
        return 1

    def place(self, tensor, device):
        return tensor

    def cuda_rng_state(self):
        return torch.zeros(4, dtype=torch.uint8)

    def accelerator(self):
        return _Accelerator()

    def load_tokenizer(self):
        return object()


class _RaisingCuda(object):
    def __init__(self):
        self.reads = 0

    def is_available(self):
        return True

    def manual_seed_all(self, seed):
        return None

    def get_rng_state(self):
        self.reads += 1
        raise RuntimeError("final CUDA RNG state could not be read")


class _ProxyTorch(object):
    def __init__(self, cuda):
        self.cuda = cuda

    def __getattr__(self, name):
        return getattr(torch, name)


class _FailingFinalCuda(_CpuStandIn):
    cpu_stand_in = False

    def __init__(self, assets, runtime, proxy):
        super(_FailingFinalCuda, self).__init__(assets, runtime)
        self.proxy = proxy

    def torch(self):
        return self.proxy


if __name__ == "__main__":
    unittest.main()
