"""Mocked CPU tests for the M5 smoke harness.

The resume comparison uses a tiny CPU model. It does not load B1, EncDec,
biological data, or a visible CUDA device.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
import unittest

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

ROOT = "/home/laura/rnagenesis-aptamer-mres"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = load_module("m5_smoke_harness_under_test", ROOT + "/scripts/modelling/m5_smoke_harness.py")
contract = harness.contract


def shapes(batch=8):
    return {
        "input_ids_dtype": "int64",
        "attention_mask_dtype": "bool",
        "input_ids_shape": [batch, 32],
        "attention_mask_shape": [batch, 32],
        "latent_shape": [batch, 32, 160],
        "latent_dtype": "float32",
        "noise_shape": [batch, 32, 160],
        "noise_dtype": "float32",
        "timestep_shape": [batch],
        "timestep_dtype": "int64",
        "loss_shape": [],
        "loss_dtype": "float32",
    }


def batch_accounting(batch=8):
    return {
        "requested_microbatch": 8,
        "measured_microbatch": batch,
        "requested_accumulation": 4,
        "measured_accumulation": 4,
        "requested_effective_batch": 32,
        "measured_effective_batch": batch * 4,
        "actual_batch_shape": [batch, 32],
    }


def rng_block(restored_with):
    digest = "c" * 64
    return {
        "setstate_called": True,
        "restored_with": restored_with,
        "disturbed_before_restore": True,
        "digest_before": digest,
        "digest_after": digest,
        "final_reset_after_verification": True,
    }


def checkpoint_proof():
    saved = {
        "model_index.json": "1" * 64,
        "scheduler/scheduler_config.json": "2" * 64,
        "unet/config.json": "3" * 64,
        "unet/diffusion_pytorch_model.safetensors": "4" * 64,
    }
    digest = "5" * 64
    config = "6" * 64
    normalized = "e" * 64
    ignored = {"_name_or_path": "observed-load-source"}
    return {
        "saved_file_hashes": saved,
        "fresh_load_succeeded": True,
        "original_denoiser_id": 11,
        "reloaded_denoiser_id": 22,
        "tensor_digest_comparisons": [{"name": "weight", "saved": digest, "reloaded": digest, "match": True}],
        "original_config_sha256": config,
        "reloaded_config_sha256": config,
        "raw_config_sha256_equal": True,
        "configuration_compatibility": {
            "ignored_top_level_keys": ["_name_or_path"],
            "original_ignored_values": dict(ignored),
            "reloaded_ignored_values": dict(ignored),
            "original_normalized_config_sha256": normalized,
            "reloaded_normalized_config_sha256": normalized,
            "normalized_config_sha256_equal": True,
        },
        "configuration_compatible": True,
    }


def resume_proof():
    keys = list(contract.RESUME_STATE_FIELDS)
    return {
        "original_denoiser_id": 11,
        "reloaded_denoiser_id": 22,
        "fresh_object_identity": True,
        "weight_digest_comparisons": [{"name": "weight", "saved": "a" * 64, "reloaded": "a" * 64, "match": True}],
        "optimizer_parameter_ids": [101],
        "original_parameter_ids": [201],
        "reloaded_parameter_ids": [101, 102],
        "optimizer_bound_to_reloaded_denoiser": True,
        "optimizer_moment_count": 1,
        "optimizer_moments_present": True,
        "scheduler_last_epoch_saved": 0,
        "scheduler_last_epoch_restored": 0,
        "scheduler_position_restored": True,
        "learning_rate_saved": 3e-5,
        "learning_rate_restored_value": 3e-5,
        "learning_rate_restored": True,
        "global_step_saved": 1,
        "global_step_reread": 1,
        "global_step_after_restore": 1,
        "next_update_index": 2,
        "restored_global_step_is_next_step": True,
        "python_rng": rng_block("random.setstate"),
        "torch_cpu_rng": rng_block("torch.set_rng_state"),
        "torch_cuda_rng": rng_block("torch.cuda.set_rng_state"),
        "diffusion_generator": rng_block("generator.set_state"),
        "numpy_rng": {"status": "not_applicable", "randomness_used": False},
        "rng_restored": True,
        "subsequent_loss": 0.5,
        "subsequent_gradients_finite": True,
        "subsequent_parameter_name": "weight",
        "subsequent_update_max_abs_delta": 0.01,
        "subsequent_update_succeeded": True,
        "weights_reloaded": True,
        "resumed_checkpoint_generation_compatible": True,
        "generation_object_id": 33,
        "generation_used_mutated_training_object": False,
        "weight_only_reload_counted_as_resume": False,
        "observed_sidecar_keys": keys,
        "sidecar_fields": list(keys),
        "sidecar_fields_source": "reread_sidecar_keys",
    }


def file_hashes():
    inventory = checkpoint_proof()["saved_file_hashes"]
    starting = {relative: digest for relative, digest, _size, _role in contract.REQUIRED_MODEL_FILES}
    starting[contract.DIFFUSERS_PATCH_PATH] = contract.DIFFUSERS_PATCH_SHA256
    return {
        "configuration": "7" * 64,
        "fixture": contract.FIXTURE_SHA256,
        "implementation_contract": "8" * 64,
        "implementation_harness": "9" * 64,
        "starting_assets": starting,
        "checkpoint_inventory": inventory,
        "resume_sidecar": "a" * 64,
        "generation_output": "d" * 64,
    }


def accumulation_proof():
    return {
        "backward_microsteps": 4,
        "optimizer_updates_in_window": 1,
        "loss_scale": contract.LOSS_SCALE_NAME,
        "deterministic_record_reuse": True,
        "reused_records": 8,
        "effective_batch": 32,
        "adamw_moments_allocated_before_training_memory_measurement": True,
    }


def bf16_record(supported=True, finite=True, fp32_loss=1.25, bf16_loss=1.5):
    value = bf16_loss if supported and finite else None
    if supported and not finite:
        value = float("nan")
    return harness.observe_bf16_diagnostic(
        supported,
        fp32_loss,
        value,
        {"allocated_bytes": 10, "reserved_bytes": 20} if supported else None,
    )


def phase_records():
    paired = bf16_record()
    return harness._phase_records(8, 4, 32, paired["fp32_loss"], paired, accumulation_proof())


def ema_inspection():
    return {
        "inspected_directory": "configs/rnagenesis/diffusion",
        "exact_inspected_inventory": list(contract.B1_DIFFUSION_DIRECTORY_INVENTORY),
        "ema_artifact_present": False,
        "ema_compatibility": "not_applicable_absent",
        "selects_ema_policy": False,
    }


def generation_proof():
    inventory = checkpoint_proof()["saved_file_hashes"]
    saved = "5" * 64
    mutated = "e" * 64
    observation = contract.derive_training_release(
        [{"label": label, "dead": True} for label in contract.TRAINING_RELEASE_LABELS]
    )
    return {
        "reloaded": True,
        "count": 2,
        "loader": "GuidedDDIMPipeline1D.from_pretrained",
        "imported_generation_py": False,
        "output_sha256": "d" * 64,
        "generation_checkpoint": "original_one_update_smoke_checkpoint",
        "selected_checkpoint_path": "/home/laura/rnagenesis-mres-runs/example/smoke_generation_checkpoint",
        "selected_checkpoint_inventory": inventory,
        "selected_checkpoint_hash_set": dict(inventory),
        "on_disk_hashes_recorded_before_generation": True,
        "on_disk_hashes_at_generation_reload": dict(inventory),
        "pre_generation_reloaded_tensor_digests": [
            {
                "name": "weight",
                "saved_checkpoint_digest": saved,
                "reloaded_digest": saved,
                "mutated_training_digest": mutated,
                "match_saved_checkpoint": True,
                "match_mutated_training_object": False,
            }
        ],
        "generation_object_matches_on_disk_checkpoint": True,
        "generation_used_mutated_training_object": False,
        "training_release_observation": observation,
        "training_objects_released_before_generation_reload": observation["training_objects_released_before_generation_reload"],
        "released_training_object_names": list(observation["released_training_object_names"]),
        "separation_basis": contract.GENERATION_SEPARATION_BASIS,
        "python_object_id_is_sufficient": False,
        "generation_object_id": 33,
        "mutated_training_object_id": 22,
    }


def memory_peaks(training_allocated=100, training_reserved=200, overall_allocated=150, overall_reserved=250):
    return {
        "training_allocated_bytes": training_allocated,
        "training_reserved_bytes": training_reserved,
        "overall_allocated_bytes": overall_allocated,
        "overall_reserved_bytes": overall_reserved,
        "accounting": {
            "adamw_moments_allocated_before_training_measurement": True,
            "training_peak_captured_before_checkpoint_reload_resume_generation": True,
            "overall_peak_includes_checkpoint_reload_resume_generation": True,
            "training_allocated_bytes": training_allocated,
            "training_reserved_bytes": training_reserved,
            "overall_allocated_bytes": overall_allocated,
            "overall_reserved_bytes": overall_reserved,
        },
    }


def repository_commits():
    return {
        "mres_implementation_commit": "a" * 40,
        "mres_authorization_commit": "b" * 40,
        "rnagenesis_commit": contract.RNAGENESIS_HEAD,
    }


def data_audit():
    return {
        "declared_scientific_data_inputs": [contract.FIXTURE_RELATIVE],
        "validated_required_asset_paths": contract.validated_required_asset_paths(),
        "cli_scientific_data_arguments": [],
        "dynamic_file_open_audit_performed": False,
        "data_access_guard_basis": {
            "closed_cli": True,
            "pinned_constant_fixture_path": contract.FIXTURE_RELATIVE,
            "pinned_call_graph": True,
            "denied_role_names": sorted(contract.DENIED_BASENAMES),
            "denied_role_hashes": dict(contract.DENIED_HASHES),
            "repository_commits": repository_commits(),
        },
    }


def membership_evidence():
    return {
        "evidence_basis": contract.OPTIMIZER_MEMBERSHIP_EVIDENCE_BASIS,
        "replacement_optimizer_used": False,
        "encdec_parameter_ids": [1, 2],
        "optimizers": [
            {
                "name": "proof_optimizer",
                "optimizer_class": "AdamW",
                "parameter_ids": [11, 12],
                "disjoint_from_encdec": True,
            },
            {
                "name": "restored_optimizer",
                "optimizer_class": "AdamW",
                "parameter_ids": [21, 22],
                "disjoint_from_encdec": True,
            },
        ],
        "both_disjoint_from_every_encdec_parameter": True,
    }


def frozen():
    evidence = membership_evidence()
    return {
        "eval_mode": True,
        "requires_grad_all_false": True,
        "optimizer_membership_empty": True,
        "parameter_gradients_absent": True,
        "versions_unchanged": True,
        "sentinels_bit_identical": True,
        "rotary_warmup_completed": True,
        "rotary_caches_excluded_from_sentinels": True,
        "baseline_taken_after_warmup": True,
        "sentinel_components": {name: "ab" * 32 for name in contract.FROZEN_SENTINEL_COMPONENTS},
        "optimizer_membership_evidence_basis": evidence["evidence_basis"],
        "optimizer_membership_evidence": evidence,
    }


def update(delta=0.1):
    return {
        "parameter_name": "denoiser.weight",
        "indices": [0, 1, 2, 3],
        "before_digest": "a" * 64,
        "after_digest": "b" * 64,
        "max_abs_delta": delta,
        "passed": delta > 0,
        "used_version_as_sole_proof": False,
        "version_before": 1,
        "version_after": 2,
    }


def report():
    document = {key: True for key in contract.MANIFEST_KEYS}
    document.update(
        {
            "manifest_schema_version": contract.MANIFEST_SCHEMA_VERSION,
            "schema_version": contract.SCHEMA_VERSION,
            "experiment_id": contract.EXPERIMENT_ID,
            "run_id": "m5_synthetic_test_run",
            "synthetic_only": True,
            "authorisation_id": "m5_synthetic_test_authorisation",
            "authorisation_consumption_state": "single_use_exercised_output_created",
            "failure_state": None,
            "completion_state": "incomplete",
            "m5_milestone_complete": False,
            "smoke_measurements_are_not_d1_decisions": True,
            "mres_implementation_commit": "a" * 40,
            "mres_authorization_commit": "b" * 40,
            "rnagenesis_commit": contract.RNAGENESIS_HEAD,
            "overfit_pass_rule": contract.EXPECTED_SMOKE_ONLY["loss_pass_rule"],
            "precision_used": "float32",
            "ema_enabled": False,
            "generation_weight_variant": "raw",
            "warnings": ["software_behaviour_check_not_biological_learning"],
            "deviations": ["production decisions remain unresolved"],
        }
    )
    return document


def observed():
    return {
        "shapes": shapes(),
        "loss": 1.0,
        "gradients": [
            {"name": "denoiser.weight", "trainable": True, "finite": True, "nonzero": True, "has_gradient": True, "encdec": False},
            {"name": "encoder.weight", "trainable": False, "finite": True, "nonzero": False, "has_gradient": False, "encdec": True},
        ],
        "batch_accounting": batch_accounting(),
        "frozen_after_backward": frozen(),
        "update": update(),
        "frozen_after_update": frozen(),
        "frozen_final": frozen(),
        "checkpoint": checkpoint_proof(),
        "resume": resume_proof(),
        "overfit_losses": [1.0, 0.8, 0.6, 0.4, 0.2],
        "phase_records": phase_records(),
        "starting_ema_inspection": ema_inspection(),
        "file_hashes": file_hashes(),
        "package_runtime": {
            "python": "3.8.13",
            "executable": contract.PINNED_PYTHON,
            "torch": "2.1.2+cu121",
            "diffusers": "0.25.0",
            "accelerate": "0.25.0",
            "transformers": "4.36.2",
        },
        "data_input_audit": data_audit(),
        "generation": generation_proof(),
        "generation_output": {
            "path": "/home/laura/rnagenesis-mres-runs/example/smoke_generation_sequences.txt",
            "sha256": "d" * 64,
            "count": 2,
        },
        "memory_peaks": memory_peaks(),
        "report": report(),
    }


class HarnessMockTests(unittest.TestCase):
    def test_complete_observation_emits_a_manifest(self):
        manifest, failure = harness.execute_observed(observed(), contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(failure)
        self.assertEqual(manifest["completion_state"], "correctness_phase_passed")
        self.assertIsNone(manifest["failure_state"])
        self.assertFalse(manifest["m5_milestone_complete"])
        self.assertTrue(manifest["smoke_measurements_are_not_d1_decisions"])
        self.assertEqual(manifest["overfit_trajectory"], [1.0, 0.8, 0.6, 0.4, 0.2])
        self.assertNotIn("manifest_sha256", manifest)
        self.assertNotIn("manifest", manifest["file_hashes"])

    def test_nonfinite_loss_suppresses_the_manifest(self):
        sample = observed()
        sample["loss"] = float("nan")
        manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "loss_not_finite")
        self.assertFalse(failure["final_manifest_emitted"])

    def test_nonfinite_missing_and_zero_gradients_fail(self):
        sample = observed()
        sample["gradients"][0]["finite"] = False
        manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "gradient_not_finite")
        sample = observed()
        sample["gradients"] = [dict(sample["gradients"][1])]
        _manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertEqual(failure["failure_state"], "gradient_missing")
        sample = observed()
        sample["gradients"][0]["nonzero"] = False
        _manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertEqual(failure["failure_state"], "gradient_all_zero")

    def test_frozen_component_and_update_failures(self):
        sample = observed()
        sample["frozen_after_backward"] = dict(frozen())
        sample["frozen_after_backward"]["sentinels_bit_identical"] = False
        _manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertEqual(failure["failure_state"], "frozen_component_failed")
        sample = observed()
        sample["gradients"][1]["has_gradient"] = True
        _manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertEqual(failure["failure_state"], "frozen_component_failed")
        sample = observed()
        sample["update"] = update(0)
        _manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertEqual(failure["failure_state"], "denoiser_not_updated")
        sample = observed()
        sample["update"] = update()
        sample["update"]["used_version_as_sole_proof"] = True
        sample["update"]["max_abs_delta"] = 0
        sample["update"]["before_digest"] = sample["update"]["after_digest"]
        _manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertEqual(failure["failure_state"], "denoiser_not_updated")

    def test_checkpoint_mismatch_and_overfit_failure_suppress_the_manifest(self):
        sample = observed()
        sample["checkpoint"] = checkpoint_proof()
        sample["checkpoint"]["tensor_digest_comparisons"] = [
            {"name": "weight", "saved": "5" * 64, "reloaded": "e" * 64, "match": False}
        ]
        manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "checkpoint_reload_mismatch")
        sample = observed()
        sample["overfit_losses"] = [0.2, 0.4, 0.8, 1.0, 1.2]
        manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "overfit_failed")
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.build_final_manifest({"completion_state": "failed", "failure_state": "overfit_failed"})
        self.assertEqual(caught.exception.code, "manifest_suppressed")

    def test_cpu_resume_matches_within_the_documented_tolerance(self):
        result = harness.compare_cpu_resume()
        self.assertEqual(result["tolerance"], 0.0)
        self.assertLessEqual(result["max_abs_delta"], 0.0)
        self.assertFalse(result["weight_only_reload_counted_as_resume"])
        self.assertTrue(result["weight_only_diverged"])
        self.assertEqual(result["cuda_device_count"], 0)

    def test_real_backend_does_not_import_torch_before_authorisation(self):
        backend = harness.RealSmokeBackend({"smoke_only": contract.EXPECTED_SMOKE_ONLY}, "/tmp/m5-not-created")
        with self.assertRaises(contract.M5SmokeError) as caught:
            backend.run_observed()
        self.assertEqual(caught.exception.code, "worker_not_authorised")

    def test_direct_frozen_snapshot_separates_qformer_from_query_tokens(self):
        import torch

        if torch.cuda.is_available() or torch.cuda.device_count() != 0:
            self.fail("frozen snapshot test saw a CUDA device")

        class FakeEncDec(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.encoder = torch.nn.Linear(2, 2, bias=False)
                self.qt = torch.nn.Module()
                self.qt.encoder = torch.nn.Module()
                self.qt.encoder.query_embeddings = torch.nn.Embedding(4, 2)
                self.qt.encoder.layer = torch.nn.ModuleList([torch.nn.Linear(2, 2, bias=False)])
                self.transform = torch.nn.Linear(2, 2, bias=False)
                self.decoder = torch.nn.Linear(2, 2, bias=False)

        module = FakeEncDec()
        module.eval()
        for parameter in module.parameters():
            parameter.requires_grad_(False)
        self.assertEqual(harness._component_for("qt.encoder.query_embeddings.weight"), "query_tokens")
        self.assertEqual(harness._component_for("qt.encoder.layer.0.weight"), "qformer")
        self.assertEqual(harness._component_for("qt.encoder.emb_layer_norm_after.weight"), "qformer")
        self.assertNotEqual(harness._component_for("qt.encoder.layer.0.weight"), "query_tokens")
        sentinels = {}
        versions = {}
        for name, parameter in module.named_parameters():
            versions[name] = int(parameter._version)
            component = harness._component_for(name)
            if component is not None and component not in sentinels:
                sentinels[component] = harness._digest_tensor(parameter.detach().flatten()[:8])
        self.assertEqual(set(sentinels), set(contract.FROZEN_SENTINEL_COMPONENTS))
        outsider = torch.nn.Parameter(torch.zeros(1))
        optimizer = torch.optim.SGD([outsider], lr=0.1)
        snapshot = harness._frozen_snapshot(
            torch,
            module,
            optimizer,
            {"sentinels": sentinels, "versions": versions, "warmup_completed": True},
            [],
        )
        contract.assert_frozen_snapshot(snapshot)
        member = next(module.decoder.parameters())
        member.requires_grad_(True)
        joined = torch.optim.SGD([member], lr=0.1)
        joined_snapshot = harness._frozen_snapshot(
            torch,
            module,
            joined,
            {"sentinels": sentinels, "versions": versions, "warmup_completed": True},
            [],
        )
        self.assertFalse(joined_snapshot["optimizer_membership_empty"])
        rows = []
        for name, parameter in module.named_parameters():
            rows.append(
                {
                    "component": harness._component_for(name),
                    "numel": int(parameter.numel()),
                    "dtype": "float32",
                    "requires_grad": bool(parameter.requires_grad),
                }
            )
        table = contract.component_parameter_table(rows)
        self.assertGreater(table["qformer"]["total"], 0)
        self.assertGreater(table["query_tokens"]["total"], 0)
        self.assertNotEqual(table["qformer"]["total"], table["query_tokens"]["total"])

    def test_configured_microbatch_rejects_a_batch_other_than_eight(self):
        sample = observed()
        sample["shapes"] = shapes(4)
        sample["batch_accounting"] = batch_accounting(4)
        manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "microbatch_mismatch")

    def test_fresh_resume_changes_the_reloaded_module_and_restores_python_rng(self):
        import random

        result = harness.demonstrate_fresh_denoiser_resume()
        self.assertNotEqual(result["original_denoiser_id"], result["reloaded_denoiser_id"])
        self.assertTrue(result["fresh_object_identity"])
        self.assertTrue(all(row["match"] for row in result["weight_digest_comparisons"]))
        self.assertTrue(result["optimizer_bound_to_reloaded_denoiser"])
        self.assertGreater(result["optimizer_moment_count"], 0)
        self.assertEqual(result["scheduler_last_epoch_saved"], result["scheduler_last_epoch_restored"])
        self.assertEqual(result["learning_rate_saved"], result["learning_rate_restored_value"])
        self.assertEqual(result["global_step_saved"], result["global_step_reread"])
        self.assertEqual(result["python_rng"]["restored_with"], "random.setstate")
        self.assertEqual(result["python_rng"]["digest_before"], result["python_rng"]["digest_after"])
        self.assertTrue(result["python_rng"]["final_reset_after_verification"])
        self.assertEqual(result["torch_cpu_rng"]["digest_before"], result["torch_cpu_rng"]["digest_after"])
        self.assertTrue(result["torch_cpu_rng"]["final_reset_after_verification"])
        self.assertEqual(result["diffusion_generator"]["restored_with"], "generator.set_state")
        self.assertTrue(result["diffusion_generator"]["final_reset_after_verification"])
        self.assertEqual(result["numpy_rng"]["status"], "not_applicable")
        self.assertFalse(result["numpy_rng"]["randomness_used"])
        self.assertGreater(result["subsequent_update_max_abs_delta"], 0)
        self.assertTrue(result["subsequent_gradients_finite"])
        self.assertEqual(result["cuda_device_count"], 0)
        saved_python = random.getstate()
        python_rng = harness.observe_python_rng_restore(saved_python)
        self.assertEqual(python_rng["digest_before"], python_rng["digest_after"])
        self.assertTrue(python_rng["disturbed_before_restore"])
        self.assertTrue(python_rng["final_reset_after_verification"])
        self.assertEqual(random.getstate(), saved_python)

    def test_hard_coded_resume_flags_and_post_resume_failures_are_rejected(self):
        hardcoded = {
            "weights_reloaded": True,
            "restored_global_step_is_next_step": True,
            "optimizer_moments_present": True,
            "scheduler_position_restored": True,
            "learning_rate_restored": True,
            "rng_restored": True,
            "subsequent_update_succeeded": True,
            "resumed_checkpoint_generation_compatible": True,
            "weight_only_reload_counted_as_resume": False,
            "sidecar_fields": contract.RESUME_STATE_FIELDS,
        }
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_resume_proof(hardcoded)
        self.assertEqual(caught.exception.code, "resume_proof_failed")
        for field, value in (
            ("subsequent_loss", float("nan")),
            ("subsequent_gradients_finite", False),
            ("subsequent_update_max_abs_delta", 0),
        ):
            sample = observed()
            sample["resume"] = resume_proof()
            sample["resume"][field] = value
            if field == "subsequent_update_max_abs_delta":
                sample["resume"]["subsequent_update_succeeded"] = False
            manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
            self.assertIsNone(manifest)
            self.assertEqual(failure["failure_state"], "resume_proof_failed")

    def test_final_frozen_snapshot_is_required_after_generation(self):
        sample = observed()
        sample["frozen_final"] = dict(frozen())
        sample["frozen_final"]["sentinels_bit_identical"] = False
        manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "frozen_component_failed")

    def test_incomplete_checkpoint_and_missing_hashes_are_rejected(self):
        sample = observed()
        sample["checkpoint"] = checkpoint_proof()
        del sample["checkpoint"]["saved_file_hashes"]["unet/config.json"]
        manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "checkpoint_reload_mismatch")
        inventory_only = checkpoint_proof()
        inventory_only["tensor_digest_comparisons"] = []
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_checkpoint_reload(inventory_only)
        self.assertEqual(caught.exception.code, "checkpoint_reload_mismatch")
        for key in ("resume_sidecar", "generation_output"):
            sample = observed()
            sample["file_hashes"] = file_hashes()
            sample["file_hashes"][key] = "short"
            manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
            self.assertIsNone(manifest)
            self.assertEqual(failure["failure_state"], "provenance_mismatch")
        incomplete = observed()
        incomplete["file_hashes"] = file_hashes()
        incomplete["file_hashes"]["checkpoint_inventory"] = {"model_index.json": "1" * 64}
        manifest, failure = harness.execute_observed(incomplete, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "checkpoint_reload_mismatch")
        short_inventory = observed()
        short_inventory["file_hashes"] = file_hashes()
        short_inventory["file_hashes"]["checkpoint_inventory"] = {"model_index.json": "short"}
        manifest, failure = harness.execute_observed(short_inventory, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "provenance_mismatch")

    def test_exact_b1_inventory_records_absent_ema_and_rejects_extra_members(self):
        expected = list(contract.B1_DIFFUSION_DIRECTORY_INVENTORY)

        def accepted_walk(_root):
            yield "/unused", ["scheduler", "unet"], ["model_index.json"]
            yield "/unused/scheduler", [], ["scheduler_config.json"]
            yield "/unused/unet", [], ["config.json", "diffusion_pytorch_model.safetensors"]

        inspection = harness.inspect_starting_ema("/unused", accepted_walk)
        self.assertEqual(inspection["exact_inspected_inventory"], expected)
        self.assertFalse(inspection["ema_artifact_present"])
        self.assertEqual(inspection["ema_compatibility"], "not_applicable_absent")
        self.assertFalse(inspection["selects_ema_policy"])
        self.assertNotIn("compatible_starting_ema_state_exists", inspection)

        def extra_walk(_root):
            yield "/unused", ["scheduler", "unet", "unet_ema"], ["model_index.json"]
            yield "/unused/scheduler", [], ["scheduler_config.json"]
            yield "/unused/unet", [], ["config.json", "diffusion_pytorch_model.safetensors"]
            yield "/unused/unet_ema", [], ["diffusion_pytorch_model.safetensors"]

        with self.assertRaises(contract.M5SmokeError) as caught:
            harness.inspect_starting_ema("/unused", extra_walk)
        self.assertEqual(caught.exception.code, "asset_identity_mismatch")

    def test_accumulation_microbatch_failure_bf16_and_memory_peaks(self):
        import torch

        if torch.cuda.is_available() or torch.cuda.device_count() != 0:
            self.fail("accumulation test saw a CUDA device")
        reference = torch.nn.Linear(4, 1, bias=False)
        model = torch.nn.Linear(4, 1, bias=False)
        with torch.no_grad():
            model.weight.copy_(reference.weight)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-2)
        records = torch.randn(8, 4)
        seen = []

        def forward_loss():
            seen.append(records.data_ptr())
            return (model(records) ** 2).mean()

        reference_loss = (reference(records) ** 2).mean()
        reference_loss.backward()
        microstep_losses = harness.run_scaled_accumulation(forward_loss, 8, 4, 8)
        self.assertEqual(len(microstep_losses), 4)
        self.assertEqual(len(set(seen)), 1)
        self.assertTrue(torch.allclose(model.weight.grad, reference.weight.grad))
        self.assertEqual(optimizer.state_dict()["state"], {})
        optimizer.step()
        moment_count = sum(1 for slot in optimizer.state_dict()["state"].values() if "exp_avg" in slot)
        self.assertGreater(moment_count, 0)
        proof = accumulation_proof()
        proof["adamw_moments_allocated_before_training_memory_measurement"] = moment_count >= 1
        self.assertTrue(contract.assert_accumulation_exercise(proof))
        failed = {
            "candidate_microbatch": 8,
            "attempted_microbatches": [8],
            "fallback_attempted": False,
            "sweep": False,
            "succeeded": False,
            "measured_physical_microbatch": None,
            "derived_accumulation": None,
        }
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_physical_microbatch_candidate(failed)
        self.assertEqual(caught.exception.code, "physical_microbatch_candidate_failed")
        swept = dict(failed)
        swept["attempted_microbatches"] = [8, 16]
        swept["fallback_attempted"] = True
        swept["succeeded"] = True
        swept["measured_physical_microbatch"] = 16
        swept["derived_accumulation"] = 2
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_physical_microbatch_candidate(swept)
        self.assertEqual(caught.exception.code, "physical_microbatch_candidate_failed")
        self.assertEqual(contract.assert_physical_microbatch_candidate(phase_records()["physical_microbatch_feasibility"]), 8)
        finite = bf16_record()
        nonfinite = bf16_record(finite=False)
        unsupported = bf16_record(supported=False)
        self.assertFalse(finite["selects_production_precision"])
        self.assertIsNone(finite["pass_tolerance"])
        self.assertIsNone(finite["production_precision_selected"])
        self.assertTrue(nonfinite["result_finite"] is False)
        self.assertIsNone(nonfinite["absolute_difference"])
        self.assertIsNone(unsupported["bf16_loss"])
        self.assertIsNone(unsupported["result_finite"])
        selected = bf16_record()
        selected["selects_production_precision"] = True
        with self.assertRaises(contract.M5SmokeError):
            contract.assert_bf16_observation(selected)
        tolerated = bf16_record()
        tolerated["pass_tolerance"] = 0.01
        with self.assertRaises(contract.M5SmokeError):
            contract.assert_bf16_observation(tolerated)
        manifest, failure = harness.execute_observed(observed(), contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(failure)
        self.assertEqual(manifest["precision_used"], "float32")
        self.assertFalse(manifest["phase_records"]["bf16_numerical_observation"]["selects_production_precision"])
        self.assertIsNone(manifest["phase_records"]["bf16_numerical_observation"]["pass_tolerance"])
        self.assertEqual(manifest["peak_training_allocated_bytes"], 100)
        self.assertEqual(manifest["peak_allocated_bytes"], 150)
        self.assertGreater(manifest["peak_allocated_bytes"], manifest["peak_training_allocated_bytes"])
        self.assertTrue(manifest["memory_peak_accounting"]["adamw_moments_allocated_before_training_measurement"])
        self.assertTrue(manifest["memory_peak_accounting"]["overall_peak_includes_checkpoint_reload_resume_generation"])
        swapped = observed()
        swapped["memory_peaks"] = memory_peaks(overall_allocated=50, overall_reserved=40)
        _manifest, failure = harness.execute_observed(swapped, contract.EXPECTED_SMOKE_ONLY)
        self.assertEqual(failure["failure_state"], "memory_peak_accounting_invalid")

    def test_generation_reloads_the_saved_checkpoint_and_rejects_the_mutated_object(self):
        proof = generation_proof()
        self.assertTrue(contract.assert_immutable_generation(proof, 2, proof["selected_checkpoint_inventory"]))
        mutated = generation_proof()
        mutated["generation_used_mutated_training_object"] = True
        mutated["generation_object_id"] = mutated["mutated_training_object_id"]
        mutated["pre_generation_reloaded_tensor_digests"][0]["reloaded_digest"] = mutated["pre_generation_reloaded_tensor_digests"][0]["mutated_training_digest"]
        mutated["pre_generation_reloaded_tensor_digests"][0]["match_saved_checkpoint"] = False
        mutated["pre_generation_reloaded_tensor_digests"][0]["match_mutated_training_object"] = True
        mutated["generation_object_matches_on_disk_checkpoint"] = False
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_immutable_generation(mutated, 2, mutated["selected_checkpoint_inventory"])
        self.assertEqual(caught.exception.code, "generation_proof_failed")
        sample = observed()
        sample["generation"] = mutated
        manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "generation_proof_failed")
        resumed_object = observed()
        resumed_object["resume"] = resume_proof()
        resumed_object["resume"]["generation_object_id"] = resumed_object["resume"]["reloaded_denoiser_id"]
        resumed_object["resume"]["generation_used_mutated_training_object"] = True
        manifest, failure = harness.execute_observed(resumed_object, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "resume_proof_failed")

    def test_data_access_guard_is_not_an_observed_open_audit(self):
        derived = contract.derive_data_access(data_audit(), repository_commits())
        self.assertEqual(derived["declared_scientific_data_inputs"], [contract.FIXTURE_RELATIVE])
        self.assertEqual(derived["cli_scientific_data_arguments"], [])
        self.assertFalse(derived["dynamic_file_open_audit_performed"])
        self.assertNotIn("opened_paths", derived)
        self.assertEqual(derived["conclusion"], "TRAIN_VALIDATION_REF_EVAL_unreachable_through_authorized_cli_and_pinned_worker")
        self.assertTrue(derived["train_not_accessed"])
        self.assertTrue(derived["validation_not_accessed"])
        self.assertTrue(derived["ref_not_accessed"])
        self.assertTrue(derived["eval_not_accessed"])
        claimed_audit = data_audit()
        claimed_audit["dynamic_file_open_audit_performed"] = True
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.derive_data_access(claimed_audit, repository_commits())
        self.assertEqual(caught.exception.code, "denied_input")
        opened = data_audit()
        opened["opened_paths"] = [contract.FIXTURE_RELATIVE]
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.derive_data_access(opened, repository_commits())
        self.assertEqual(caught.exception.code, "denied_input")

    def test_rng_helpers_reset_after_the_verification_draw(self):
        import random
        import torch

        if torch.cuda.is_available() or torch.cuda.device_count() != 0:
            self.fail("RNG reset test saw a CUDA device")
        saved_python = random.getstate()
        python_rng = harness.observe_python_rng_restore(saved_python)
        self.assertTrue(python_rng["final_reset_after_verification"])
        self.assertEqual(random.getstate(), saved_python)
        saved_cpu = torch.get_rng_state().clone()
        cpu_rng = harness.observe_torch_cpu_rng_restore(torch, saved_cpu)
        self.assertTrue(cpu_rng["final_reset_after_verification"])
        self.assertTrue(torch.equal(torch.get_rng_state(), saved_cpu))
        generator = torch.Generator(device="cpu")
        generator.manual_seed(11)
        saved_generator = generator.get_state().clone()
        generator_rng = harness.observe_generator_restore(torch, generator, saved_generator)
        self.assertTrue(generator_rng["final_reset_after_verification"])
        self.assertTrue(torch.equal(generator.get_state(), saved_generator))
        missing = resume_proof()
        missing["torch_cpu_rng"] = rng_block("torch.set_rng_state")
        missing["torch_cpu_rng"]["final_reset_after_verification"] = False
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_resume_proof(missing)
        self.assertEqual(caught.exception.code, "resume_proof_failed")

    def test_tensor_bearing_sidecar_and_parameter_dictionaries_prevent_release(self):
        import gc
        import weakref

        import torch

        if torch.cuda.is_available() or torch.cuda.device_count() != 0:
            self.fail("release test saw a CUDA device")
        denoiser = torch.nn.Linear(2, 2, bias=False)
        resumed = torch.nn.Linear(2, 2, bias=False)
        proof_optimizer = torch.optim.AdamW(denoiser.parameters(), lr=1e-3)
        restored_optimizer = torch.optim.AdamW(resumed.parameters(), lr=1e-3)
        (denoiser.weight ** 2).sum().backward()
        proof_optimizer.step()
        (resumed.weight ** 2).sum().backward()
        restored_optimizer.step()
        proof_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(proof_optimizer, T_max=2)
        restored_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(restored_optimizer, T_max=2)
        parameter_dictionary = {
            "original": dict(denoiser.named_parameters()),
            "resumed": dict(resumed.named_parameters()),
        }
        sidecar = {"optimizer_state": proof_optimizer.state_dict()}
        loaded_sidecar = {"optimizer_state": restored_optimizer.state_dict()}
        holders = {
            "original_denoiser": denoiser,
            "resumed_denoiser": resumed,
            "representative_original_parameter": parameter_dictionary["original"]["weight"],
            "representative_resumed_parameter": parameter_dictionary["resumed"]["weight"],
            "proof_optimizer": proof_optimizer,
            "restored_optimizer": restored_optimizer,
            "proof_scheduler": proof_scheduler,
            "restored_scheduler": restored_scheduler,
            "saved_pipeline": torch.nn.Linear(1, 1, bias=False),
            "resumed_pipeline": torch.nn.Linear(1, 1, bias=False),
            "in_memory_sidecar_tensor": harness._state_tensor(sidecar),
            "loaded_sidecar_tensor": harness._state_tensor(loaded_sidecar),
            "resume_loss": torch.zeros(()),
            "step_loss": torch.zeros(()),
            "microstep_loss": torch.zeros(()),
            "fp32_loss_tensor": torch.zeros(()),
            "fixed_latent": torch.zeros(2, 2),
            "fixed_noise": torch.zeros(2, 2),
            "fixed_timesteps": torch.zeros(2, dtype=torch.long),
            "batch_input_ids": torch.zeros(8, 4, dtype=torch.long),
        }
        named = {label: weakref.ref(holders[label]) for label in contract.TRAINING_RELEASE_LABELS}
        del holders, denoiser, resumed, proof_optimizer, restored_optimizer, proof_scheduler, restored_scheduler
        gc.collect()
        blocked = harness.observe_training_object_release(named)
        self.assertFalse(blocked["training_objects_released_before_generation_reload"])
        for label in (
            "representative_original_parameter",
            "representative_resumed_parameter",
            "in_memory_sidecar_tensor",
            "loaded_sidecar_tensor",
        ):
            self.assertIn(label, blocked["live_training_object_names"])
            self.assertNotIn(label, blocked["released_training_object_names"])
        self.assertFalse(blocked["python_object_id_is_release_proof"])
        leaked_proof = generation_proof()
        leaked_proof["training_release_observation"] = blocked
        leaked_proof["training_objects_released_before_generation_reload"] = True
        leaked_proof["released_training_object_names"] = list(contract.TRAINING_RELEASE_LABELS)
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_immutable_generation(leaked_proof, 2, leaked_proof["selected_checkpoint_inventory"])
        self.assertEqual(caught.exception.code, "generation_proof_failed")
        del parameter_dictionary, sidecar, loaded_sidecar
        gc.collect()
        released = harness.observe_training_object_release(named)
        self.assertTrue(released["training_objects_released_before_generation_reload"])
        self.assertEqual(released["released_training_object_names"], list(contract.TRAINING_RELEASE_LABELS))
        self.assertEqual(released["live_training_object_names"], [])

    def test_generation_requires_observed_weakref_release(self):
        proof = generation_proof()
        self.assertTrue(contract.assert_immutable_generation(proof, 2, proof["selected_checkpoint_inventory"]))
        self.assertFalse(proof["training_release_observation"]["python_object_id_is_release_proof"])
        self.assertNotEqual(proof["generation_object_id"], proof["mutated_training_object_id"])
        missing = generation_proof()
        del missing["training_release_observation"]
        missing["training_objects_released_before_generation_reload"] = True
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_immutable_generation(missing, 2, missing["selected_checkpoint_inventory"])
        self.assertEqual(caught.exception.code, "generation_proof_failed")
        referents = [{"label": label, "dead": True} for label in contract.TRAINING_RELEASE_LABELS]
        referents[0] = {"label": referents[0]["label"], "dead": False}
        partial = contract.derive_training_release(referents)
        self.assertFalse(partial["training_objects_released_before_generation_reload"])
        self.assertNotIn(referents[0]["label"], partial["released_training_object_names"])
        live = generation_proof()
        live["training_release_observation"] = partial
        live["training_objects_released_before_generation_reload"] = partial["training_objects_released_before_generation_reload"]
        live["released_training_object_names"] = list(partial["released_training_object_names"])
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_immutable_generation(live, 2, live["selected_checkpoint_inventory"])
        self.assertEqual(caught.exception.code, "generation_proof_failed")
        sample = observed()
        sample["generation"] = live
        manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "generation_proof_failed")
        claimed = generation_proof()
        claimed["training_release_observation"]["python_object_id_is_release_proof"] = True
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_immutable_generation(claimed, 2, claimed["selected_checkpoint_inventory"])
        self.assertEqual(caught.exception.code, "generation_proof_failed")

    def test_dummy_optimizer_membership_evidence_is_rejected(self):
        import torch

        if torch.cuda.is_available() or torch.cuda.device_count() != 0:
            self.fail("membership test saw a CUDA device")
        encdec = torch.nn.Linear(2, 2, bias=False)
        denoiser = torch.nn.Linear(2, 2, bias=False)
        fresh = torch.nn.Linear(2, 2, bias=False)
        proof_optimizer = torch.optim.AdamW(denoiser.parameters(), lr=1e-5)
        restored_optimizer = torch.optim.AdamW(fresh.parameters(), lr=1e-5)
        evidence = harness.observe_live_adamw_membership(
            encdec,
            (("proof_optimizer", proof_optimizer), ("restored_optimizer", restored_optimizer)),
        )
        self.assertEqual(evidence["evidence_basis"], contract.OPTIMIZER_MEMBERSHIP_EVIDENCE_BASIS)
        self.assertFalse(evidence["replacement_optimizer_used"])
        self.assertTrue(evidence["both_disjoint_from_every_encdec_parameter"])
        encdec_ids = set(evidence["encdec_parameter_ids"])
        for row in evidence["optimizers"]:
            self.assertEqual(row["optimizer_class"], "AdamW")
            self.assertTrue(set(row["parameter_ids"]).isdisjoint(encdec_ids))
        self.assertTrue(contract.assert_optimizer_membership_evidence(evidence))
        dummy = torch.optim.SGD([torch.nn.Parameter(torch.zeros(1))], lr=0.1)
        with self.assertRaises(contract.M5SmokeError) as caught:
            harness.observe_live_adamw_membership(encdec, (("proof_optimizer", proof_optimizer), ("restored_optimizer", dummy)))
        self.assertEqual(caught.exception.code, "frozen_component_failed")
        boolean_only = frozen()
        del boolean_only["optimizer_membership_evidence"]
        del boolean_only["optimizer_membership_evidence_basis"]
        self.assertTrue(boolean_only["optimizer_membership_empty"])
        self.assertTrue(contract.assert_frozen_snapshot(boolean_only))
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_post_generation_frozen_snapshot(boolean_only)
        self.assertEqual(caught.exception.code, "frozen_component_failed")
        fabricated = frozen()
        fabricated["optimizer_membership_evidence_basis"] = "replacement_sgd_optimizer"
        fabricated["optimizer_membership_evidence"] = {
            "evidence_basis": "replacement_sgd_optimizer",
            "replacement_optimizer_used": True,
            "encdec_parameter_ids": [1, 2],
            "optimizers": [
                {"name": "proof_optimizer", "optimizer_class": "SGD", "parameter_ids": [9], "disjoint_from_encdec": True},
                {"name": "restored_optimizer", "optimizer_class": "SGD", "parameter_ids": [8], "disjoint_from_encdec": True},
            ],
            "both_disjoint_from_every_encdec_parameter": True,
        }
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_post_generation_frozen_snapshot(fabricated)
        self.assertEqual(caught.exception.code, "frozen_component_failed")
        sample = observed()
        sample["frozen_final"] = fabricated
        manifest, failure = harness.execute_observed(sample, contract.EXPECTED_SMOKE_ONLY)
        self.assertIsNone(manifest)
        self.assertEqual(failure["failure_state"], "frozen_component_failed")

    def test_bf16_runtime_exception_is_not_a_nonfinite_result(self):
        def explode():
            raise RuntimeError("bf16 kernel rejected")

        with self.assertRaises(contract.M5SmokeError) as caught:
            harness.run_bf16_diagnostic(True, explode, 1.25)
        self.assertEqual(caught.exception.code, "bf16_forward_failed")
        unsupported = harness.run_bf16_diagnostic(False, explode, 1.25)
        self.assertIsNone(unsupported["bf16_loss"])
        self.assertIsNone(unsupported["result_finite"])
        self.assertIsNone(unsupported["absolute_difference"])

        def returns_nan():
            return float("nan"), None

        nonfinite = harness.run_bf16_diagnostic(True, returns_nan, 1.25)
        self.assertIs(nonfinite["result_finite"], False)
        self.assertIsNone(nonfinite["bf16_loss"])

        def returns_loss():
            return 1.5, {"allocated_bytes": 3, "reserved_bytes": 4}

        finite = harness.run_bf16_diagnostic(True, returns_loss, 1.25)
        self.assertIs(finite["result_finite"], True)
        self.assertEqual(finite["bf16_loss"], 1.5)
        self.assertFalse(finite["selects_production_precision"])
        source = pathlib.Path(ROOT + "/scripts/modelling/m5_smoke_harness.py").read_text(encoding="utf-8")
        self.assertNotIn('bf16_value = float("nan")', source)
        self.assertNotIn("torch.optim.SGD", source)
        self.assertNotIn('"training_objects_released_before_generation_reload": True', source)

    def test_harness_source_does_not_hard_code_resume_or_access_flags(self):
        source = pathlib.Path(ROOT + "/scripts/modelling/m5_smoke_harness.py").read_text(encoding="utf-8")
        self.assertNotIn("for _name, parameter in encdec.parameters()", source)
        self.assertIn("for parameter in encdec.parameters()", source)
        self.assertNotIn('"train_not_accessed": True', source)
        self.assertNotIn('"rng_restored": True', source)
        self.assertNotIn("sidecar_fields\": contract.RESUME_STATE_FIELDS", source)
        self.assertIn("random.setstate", source)
        self.assertIn("torch.cuda.set_rng_state", source)
        self.assertIn("generator.set_state", source)
        destinations = {action.dest for action in harness.build_parser()._actions}
        self.assertTrue({"train_data", "validation_data", "ref", "eval", "fixture"}.isdisjoint(destinations))

    def test_harness_import_does_not_import_heavy_modules(self):
        script = (
            "import importlib.util, os, sys\n"
            "os.environ['CUDA_VISIBLE_DEVICES'] = ''\n"
            "spec = importlib.util.spec_from_file_location('m5h', %r)\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(module)\n"
            "banned = [name for name in sys.modules if name.split('.')[0] in ('torch', 'accelerate', 'diffusers') or name == 'generation' or name.startswith('models.')]\n"
            "sys.stdout.write(','.join(banned))\n"
        ) % (ROOT + "/scripts/modelling/m5_smoke_harness.py")
        completed = subprocess.run(
            ["/home/laura/miniconda3/envs/rnagenesis-h200/bin/python", "-B", "-c", script],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": "", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_configuration_compatibility_ignores_only_top_level_name_or_path(self):
        import sys

        original_source = "../../checkpoint-27500"
        reloaded_source = "/home/laura/RNAGenesis/configs/rnagenesis/diffusion"
        for path in (ROOT + "/scripts/modelling/m5_smoke_contract.py", ROOT + "/scripts/modelling/m5_smoke_harness.py"):
            source = pathlib.Path(path).read_text(encoding="utf-8")
            self.assertNotIn(original_source, source)
            self.assertNotIn(reloaded_source, source)

        def mapping(name_or_path, **overrides):
            payload = {
                "_class_name": "UNet1DModel",
                "_diffusers_version": "0.25.0",
                "_name_or_path": name_or_path,
                "in_channels": 160,
                "layers_per_block": 2,
                "attention_head_dim": 8,
                "block_out_channels": [32, 64],
                "down_block_types": ["DownBlock1D", "AttnDownBlock1D"],
                "mid_block": {"_name_or_path": "nested-source", "attention_head_dim": 8},
            }
            payload.update(overrides)
            return payload

        def independent_digest(payload, drop_name):
            copied = dict(payload)
            if drop_name and "_name_or_path" in copied:
                del copied["_name_or_path"]
            return contract.sha256_bytes(contract.canonical_json(copied))

        def proof_for(original, reloaded):
            observed = harness.observe_configuration_compatibility(original, reloaded)
            saved = checkpoint_proof()["saved_file_hashes"]
            digest = "5" * 64
            return harness.build_checkpoint_reload_proof(
                saved,
                True,
                11,
                22,
                [{"name": "weight", "saved": digest, "reloaded": digest, "match": True}],
                observed,
            )

        original = mapping(original_source)
        reloaded = mapping(reloaded_source)
        observed = harness.observe_configuration_compatibility(original, reloaded)
        compatibility = observed["configuration_compatibility"]
        self.assertEqual(observed["original_config_sha256"], independent_digest(original, False))
        self.assertEqual(observed["reloaded_config_sha256"], independent_digest(reloaded, False))
        self.assertNotEqual(observed["original_config_sha256"], observed["reloaded_config_sha256"])
        self.assertFalse(observed["raw_config_sha256_equal"])
        self.assertEqual(compatibility["ignored_top_level_keys"], ["_name_or_path"])
        self.assertEqual(compatibility["original_ignored_values"], {"_name_or_path": original_source})
        self.assertEqual(compatibility["reloaded_ignored_values"], {"_name_or_path": reloaded_source})
        self.assertEqual(compatibility["original_normalized_config_sha256"], independent_digest(original, True))
        self.assertEqual(compatibility["reloaded_normalized_config_sha256"], independent_digest(reloaded, True))
        self.assertEqual(compatibility["original_normalized_config_sha256"], compatibility["reloaded_normalized_config_sha256"])
        self.assertNotEqual(observed["original_config_sha256"], compatibility["original_normalized_config_sha256"])
        self.assertTrue(compatibility["normalized_config_sha256_equal"])
        self.assertTrue(observed["configuration_compatible"])
        self.assertEqual(tuple(compatibility), contract.CONFIGURATION_COMPATIBILITY_FIELD_ORDER)
        passing = proof_for(original, reloaded)
        self.assertEqual(tuple(passing), contract.CHECKPOINT_RELOAD_FIELD_ORDER)
        self.assertTrue(contract.assert_checkpoint_reload(passing))
        self.assertEqual(original["_name_or_path"], original_source)
        self.assertEqual(reloaded["_name_or_path"], reloaded_source)

        class ToDictConfig:
            def __init__(self, name_or_path):
                self.name_or_path = name_or_path

            def to_dict(self):
                return mapping(self.name_or_path)

        to_dict_observed = harness.observe_configuration_compatibility(ToDictConfig(original_source), ToDictConfig(reloaded_source))
        self.assertEqual(to_dict_observed["original_config_sha256"], observed["original_config_sha256"])
        self.assertTrue(to_dict_observed["configuration_compatible"])

        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        before = set(sys.modules)
        from diffusers.configuration_utils import FrozenDict

        added = [name for name in sys.modules if name not in before]
        self.assertFalse(any(name == "generation" or name.startswith("models.") for name in added))
        torch_module = sys.modules.get("torch")
        if torch_module is not None:
            self.assertFalse(torch_module.cuda.is_initialized())
            self.assertEqual(torch_module.cuda.device_count(), 0)
        frozen_original = FrozenDict(list(original.items()))
        frozen_reloaded = FrozenDict(list(reloaded.items()))
        self.assertIs(type(frozen_original), FrozenDict)
        frozen_observed = harness.observe_configuration_compatibility(frozen_original, frozen_reloaded)
        self.assertEqual(frozen_observed["original_config_sha256"], observed["original_config_sha256"])
        self.assertEqual(frozen_observed["reloaded_config_sha256"], observed["reloaded_config_sha256"])
        self.assertTrue(frozen_observed["configuration_compatible"])
        self.assertEqual(frozen_original["_name_or_path"], original_source)
        self.assertTrue(contract.assert_checkpoint_reload(proof_for(frozen_original, frozen_reloaded)))

        def reject_change(**overrides):
            changed = mapping(reloaded_source, **overrides)
            changed_observed = harness.observe_configuration_compatibility(original, changed)
            self.assertNotEqual(
                changed_observed["configuration_compatibility"]["original_normalized_config_sha256"],
                changed_observed["configuration_compatibility"]["reloaded_normalized_config_sha256"],
            )
            self.assertFalse(changed_observed["configuration_compatibility"]["normalized_config_sha256_equal"])
            self.assertFalse(changed_observed["configuration_compatible"])
            with self.assertRaises(contract.M5SmokeError) as caught:
                contract.assert_checkpoint_reload(proof_for(original, changed))
            self.assertEqual(caught.exception.code, "checkpoint_reload_mismatch")
            self.assertEqual(caught.exception.detail, "reloaded configuration is not compatible")

        reject_change(in_channels=128)
        reject_change(layers_per_block=3)
        reject_change(attention_head_dim=16)
        reject_change(block_out_channels=[32, 32])
        reject_change(_class_name="OtherUNet")
        reject_change(_diffusers_version="0.26.0")
        reject_change(mid_block={"_name_or_path": "different-nested-source", "attention_head_dim": 8})
        nested_attention = mapping(reloaded_source)
        nested_attention["mid_block"] = {"_name_or_path": "nested-source", "attention_head_dim": 4}
        reject_change(mid_block=nested_attention["mid_block"])

        absent = mapping(original_source)
        del absent["_name_or_path"]
        absent_observed = harness.observe_configuration_compatibility(original, absent)
        self.assertNotIn("_name_or_path", absent_observed["configuration_compatibility"]["reloaded_ignored_values"])
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_checkpoint_reload(proof_for(original, absent))
        self.assertEqual(caught.exception.detail, "ignored configuration values were not observed")

        second_key = proof_for(original, reloaded)
        second_key["configuration_compatibility"]["ignored_top_level_keys"] = ["_name_or_path", "in_channels"]
        second_key["configuration_compatibility"]["original_ignored_values"]["in_channels"] = 160
        second_key["configuration_compatibility"]["reloaded_ignored_values"]["in_channels"] = 160
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_checkpoint_reload(second_key)
        self.assertEqual(caught.exception.detail, "configuration normalization ignores an extra key")

    def test_config_sha256_accepts_frozendict_and_rejects_unsupported_values(self):
        import sys
        import traceback
        from collections.abc import Mapping

        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        before = set(sys.modules)
        from diffusers.configuration_utils import FrozenDict

        added = [name for name in sys.modules if name not in before]
        self.assertFalse(any(name == "generation" or name.startswith("models.") for name in added))
        torch_module = sys.modules.get("torch")
        if torch_module is not None:
            self.assertFalse(torch_module.cuda.is_initialized())
            self.assertEqual(torch_module.cuda.device_count(), 0)

        payload = {"sample_size": 32, "in_channels": 160, "layers": {"b": 2, "a": 1}}
        frozen = FrozenDict([("layers", {"b": 2, "a": 1}), ("in_channels", 160), ("sample_size", 32)])
        reordered = FrozenDict([("sample_size", 32), ("in_channels", 160), ("layers", {"a": 1, "b": 2})])
        plain = {"in_channels": 160, "sample_size": 32, "layers": {"a": 1, "b": 2}}
        self.assertIs(type(frozen), FrozenDict)
        self.assertFalse(hasattr(FrozenDict, "to_dict"))
        frozen_digest = harness._config_sha256(frozen)
        self.assertEqual(frozen_digest, harness._config_sha256(plain))
        self.assertEqual(frozen_digest, harness._config_sha256(dict(payload)))
        self.assertEqual(frozen_digest, harness._config_sha256(reordered))
        self.assertEqual(harness._config_sha256({"b": 1, "a": 2}), harness._config_sha256({"a": 2, "b": 1}))

        class ToDictConfig:
            def to_dict(self):
                return {"layers": {"b": 2, "a": 1}, "sample_size": 32, "in_channels": 160}

        self.assertEqual(harness._config_sha256(ToDictConfig()), frozen_digest)

        class ReturnsFrozenDict:
            def to_dict(self):
                return FrozenDict([("b", 1), ("a", 2)])

        self.assertEqual(harness._config_sha256(ReturnsFrozenDict()), harness._config_sha256({"a": 2, "b": 1}))

        class Unsupported:
            pass

        with self.assertRaises(contract.M5SmokeError) as caught:
            harness._config_sha256(Unsupported())
        self.assertEqual(caught.exception.code, "checkpoint_reload_mismatch")
        self.assertEqual(caught.exception.detail, "denoiser configuration is not a supported representation")

        class NonMappingToDict:
            def to_dict(self):
                return ["not", "a", "mapping"]

        with self.assertRaises(contract.M5SmokeError) as caught:
            harness._config_sha256(NonMappingToDict())
        self.assertEqual(caught.exception.code, "checkpoint_reload_mismatch")
        self.assertEqual(caught.exception.detail, "denoiser configuration to_dict() did not return a mapping")

        def assert_traceback_hides(config, detail, secret):
            with self.assertRaises(contract.M5SmokeError) as caught:
                harness._config_sha256(config)
            self.assertEqual(caught.exception.code, "checkpoint_reload_mismatch")
            self.assertEqual(caught.exception.detail, detail)
            formatted = "".join(
                traceback.format_exception(
                    type(caught.exception),
                    caught.exception,
                    caught.exception.__traceback__,
                    chain=True,
                )
            )
            self.assertNotIn(secret, formatted)
            self.assertNotIn(secret, str(caught.exception))

        to_dict_secret = "sensitive configuration text"

        class FailingToDict:
            def to_dict(self):
                raise RuntimeError(to_dict_secret)

        assert_traceback_hides(FailingToDict(), "denoiser configuration to_dict() failed", to_dict_secret)

        mapping_secret = "sensitive mapping conversion text"

        class BrokenMapping(Mapping):
            def __getitem__(self, key):
                raise RuntimeError(mapping_secret)

            def __iter__(self):
                raise RuntimeError(mapping_secret)

            def __len__(self):
                return 1

        assert_traceback_hides(
            BrokenMapping(),
            "denoiser configuration could not be converted with dict()",
            mapping_secret,
        )

        canonical_secret = "sensitive canonical json text"

        class SensitiveSortKey(str):
            def __lt__(self, other):
                raise RuntimeError(canonical_secret)

        class UnserializableToDict:
            def to_dict(self):
                return {SensitiveSortKey("b"): 1, SensitiveSortKey("a"): 2}

        assert_traceback_hides(
            UnserializableToDict(),
            "denoiser configuration could not be serialized as canonical JSON",
            canonical_secret,
        )


if __name__ == "__main__":
    unittest.main()
