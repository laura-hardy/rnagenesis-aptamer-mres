"""CPU-only tests for the inactive M6 pilot contract.

Synthetic values only. These tests do not read biological corpora, model
weights, accepted run directories, or a GPU.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import math
import os
import shutil
import tempfile
import unittest
from fractions import Fraction

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

ROOT = "/home/laura/rnagenesis-aptamer-mres"
CONFIG_PATH = os.path.join(ROOT, "config/experiments/D1_diffusion_pilot.yaml")
CONTRACT_PATH = os.path.join(ROOT, "scripts/modelling/m6_pilot_contract.py")

EXPECTED_LR_DECIMALS = (
    "1.5e-05",
    "3.0000000000000001e-05",
    "3.0000000000000001e-05",
    "2.9795419551040836e-05",
    "2.9187258625509518e-05",
    "2.8192106268097336e-05",
    "2.6837107640945904e-05",
    "2.5159223574386117e-05",
    "2.3204222371836409e-05",
    "2.1025431369794546e-05",
    "1.8682282307111988e-05",
    "1.6238690182084989e-05",
    "1.3761309817915017e-05",
    "1.1317717692888014e-05",
    "8.9745686302054618e-06",
    "6.7957776281635993e-06",
    "4.8407764256138869e-06",
    "3.162892359054098e-06",
    "1.8078937319026655e-06",
    "8.1274137449048048e-07",
    "2.0458044895916516e-07",
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = load_module("m6_pilot_contract_under_test", CONTRACT_PATH)


def independent_multiplier(position):
    """Independent transcription of the documented 21-update schedule."""
    total = 21
    warmup = 2
    if position == total + 1:
        return 0.0
    if position <= warmup:
        return position / float(warmup)
    progress = (position - warmup - 1) / float(total - warmup)
    return 0.5 * (1.0 + math.cos(math.pi * progress))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def state(update, mutate_last=False):
    values = {f"parameter_{index}": f"value-{update}-{index}" for index in range(5)}
    if mutate_last:
        values["parameter_4"] = "different"
    return values


def config(marker):
    return {"_name_or_path": marker, "_class_name": "UNet", "block": {"_name_or_path": "keep"}, "layers": 2}


def reload_proof(update, mutate_last=False, selection="complete", labelled_as_resume=False):
    return {
        "update": update,
        "fresh_object_constructed": True,
        "original_object_id": 1000 + update,
        "reloaded_object_id": 2000 + update,
        "labelled_as_resume": labelled_as_resume,
        "selection": selection,
        "saved_hashes": {name: digest(name + str(update)) for name in contract.CHECKPOINT_MEMBERS},
        "original_state": state(update),
        "reloaded_state": state(update, mutate_last),
        "original_config": config("original"),
        "reloaded_config": config("reloaded"),
    }


def validation_source(**overrides):
    source = {
        "loaded_from_accepted_artifacts": True,
        "regenerated": False,
        "timestep_shape": contract.VALIDATION_TIMESTEP_SHAPE,
        "noise_shape": contract.VALIDATION_NOISE_SHAPE,
        "timestep_sha256": contract.VALIDATION_TIMESTEPS_SHA256,
        "noise_sha256": contract.VALIDATION_NOISE_SHA256,
        "seed": contract.VALIDATION_DRAW_SEED,
    }
    source.update(overrides)
    return source


def observation(update, aggregate, initial=None):
    relative = None if update == 0 else contract.classify_validation_change(initial, aggregate, update)
    return {
        "aggregate_mse": contract.format_decimal(aggregate),
        "pair_count": 380,
        "relative_to_update_0": relative,
        "tensors_loaded": True,
        "tensors_regenerated": False,
        "update": update,
        "weight_variant": "raw",
    }


def snapshot(later=1.0):
    initial = 1.0
    reviews = [contract.classify_validation_change(initial, later if update == 7 else initial, update) for update in (7, 14, 21)]
    observations = [observation(0, initial)]
    for update in (7, 14, 21):
        value = later if update == 7 else initial
        observations.append(observation(update, value, initial))
    return {
        "opened_biological_data": False,
        "train_permutation_digest": contract.permutation_digest(list(range(contract.TRAIN_RECORD_COUNT))),
        "peak_allocated_bytes": 11,
        "peak_reserved_bytes": 13,
        "training_seconds": 1.25,
        "validation_seconds": 2.5,
        "train_updates": [
            {
                "update": update,
                "learning_rate": contract.applied_learning_rate(update),
                "training_loss": 0.5,
                "pre_clip_gradient_norm": 0.25,
                "applied_norm": 0.25,
                "clipped": False,
            }
            for update in range(1, 22)
        ],
        "validation_observations": observations,
        "validation_review_observations": reviews,
        "weight_checkpoints": [contract.prove_weight_reload(reload_proof(update)) for update in (7, 14, 21)],
    }


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CONFIG_PATH, "rb") as handle:
            cls.raw = handle.read()
        cls.config = contract.load_config_bytes(cls.raw)

    def test_checked_in_configuration_is_inactive_and_rejects_execution(self):
        contract.assert_inactive_text(self.raw.decode("utf-8"))
        contract.assert_inactive_configuration(self.config)
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.reject_inactive_before_execution(self.config)
        self.assertEqual(caught.exception.code, "execution_not_authorised")
        self.assertIsNone(self.config["execution"]["output_directory"])
        self.assertIsNone(self.config["execution"]["authorisation_id"])
        self.assertFalse(self.config["data"]["open_permitted"])

    def test_arithmetic_and_final_window_weights(self):
        report = contract.assert_pilot_arithmetic()
        self.assertEqual(report["microbatches"], 84)
        self.assertEqual(report["optimizer_updates"], 21)
        self.assertEqual(report["final_window"], (8, 8, 8, 5))
        self.assertEqual(report["final_window_examples"], 29)
        weights = report["final_weights"]
        self.assertEqual(weights, (Fraction(8, 29), Fraction(8, 29), Fraction(8, 29), Fraction(5, 29)))
        self.assertEqual(sum(weights, Fraction(0)), 1)
        self.assertEqual(math.fsum(contract.applied_float_scales((8, 8, 8, 5))), 1.0)
        full = contract.example_weighted_contributions((8, 8, 8, 8))
        self.assertEqual(sum(full, Fraction(0)), 1)

    def test_exact_applied_learning_rate_trace(self):
        trace = contract.applied_learning_rate_trace()
        self.assertEqual(len(trace), 21)
        self.assertTrue(all(value > 0.0 for value in trace))
        independent = tuple(contract.BASE_LEARNING_RATE * independent_multiplier(position) for position in range(1, 22))
        self.assertEqual(trace, independent)
        self.assertEqual(tuple(contract.format_decimal(value) for value in trace), EXPECTED_LR_DECIMALS)
        self.assertEqual(trace[0], contract.BASE_LEARNING_RATE * 0.5)
        self.assertEqual(trace[1], contract.BASE_LEARNING_RATE)
        self.assertEqual(trace[2], contract.BASE_LEARNING_RATE)
        post = contract.post_update_scheduler_position()
        self.assertEqual(post["position"], 22)
        self.assertEqual(post["multiplier"], 0.0)
        self.assertFalse(post["applied_to_optimizer"])
        self.assertEqual(independent_multiplier(22), 0.0)
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.applied_learning_rate(22)
        self.assertEqual(caught.exception.code, "learning_rate_zero_applied")

    def test_finite_acceptance_and_nonfinite_rejection(self):
        self.assertEqual(contract.assert_finite_training_loss(0.25), 0.25)
        contract.assert_finite_gradients(True)
        clipped = contract.clip_pre_clip_norm(2.5)
        self.assertTrue(clipped["clipped"])
        self.assertFalse(clipped["abort"])
        self.assertEqual(clipped["applied_norm"], 1.0)
        self.assertFalse(contract.clip_pre_clip_norm(0.4)["clipped"])
        for value in (float("nan"), float("inf")):
            with self.assertRaises(contract.M6PilotError) as caught:
                contract.assert_finite_training_loss(value)
            self.assertEqual(caught.exception.code, "non_finite_training_loss")
            with self.assertRaises(contract.M6PilotError) as caught:
                contract.clip_pre_clip_norm(value)
            self.assertEqual(caught.exception.code, "non_finite_pre_clip_gradient_norm")
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.assert_finite_gradients(False)
        self.assertEqual(caught.exception.code, "non_finite_trainable_gradient")
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.assert_finite_validation([float("nan")])
        self.assertEqual(caught.exception.code, "non_finite_validation")

    def test_frozen_optimizer_and_denoiser_change(self):
        snapshot_ok = {
            name: {"requires_grad": False, "trainable_count": 0, "changed": False} for name in contract.ENCDEC_COMPONENTS
        }
        contract.assert_encdec_frozen(snapshot_ok)
        broken = copy.deepcopy(snapshot_ok)
        broken["decoder"]["requires_grad"] = True
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.assert_encdec_frozen(broken)
        self.assertEqual(caught.exception.code, "modified_or_trainable_encdec")
        contract.assert_optimizer_membership(
            {
                "denoiser_parameter_names": ["denoiser.weight"],
                "encdec_parameter_names": ["encoder.weight"],
                "optimizer_parameter_names": ["denoiser.weight"],
            }
        )
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.assert_optimizer_membership(
                {
                    "denoiser_parameter_names": ["denoiser.weight"],
                    "encdec_parameter_names": ["encoder.weight"],
                    "optimizer_parameter_names": ["denoiser.weight", "encoder.weight"],
                }
            )
        self.assertEqual(caught.exception.code, "modified_or_trainable_encdec")
        before = digest("before")
        after = digest("after")
        contract.assert_denoiser_changed(before, after, contract.BASE_LEARNING_RATE)
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.assert_denoiser_changed(before, before, contract.BASE_LEARNING_RATE)
        self.assertEqual(caught.exception.code, "no_observed_denoiser_change")

    def test_validation_schedule_and_unequal_batch_aggregation(self):
        for update in (0, 7, 14, 21):
            contract.validation_updates_for(update)
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validation_updates_for(1)
        self.assertEqual(caught.exception.code, "validation_schedule_invalid")
        contract.assert_validation_source(validation_source())
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.assert_validation_source(validation_source(regenerated=True))
        self.assertEqual(caught.exception.code, "identity_mismatch")
        values = [0.0] * 379 + [380.0]
        split_a = [values[:379], values[379:]]
        split_b = [values[:1], values[1:]]
        self.assertEqual(contract.aggregate_pair_mse(split_a), 1.0)
        self.assertEqual(contract.aggregate_pair_mse(split_b), 1.0)
        self.assertNotEqual(contract.equal_batch_mean(split_a), contract.aggregate_pair_mse(split_a))
        self.assertNotEqual(len(split_a[0]), len(split_a[1]))

    def test_checkpoint_overwrite_complete_state_and_not_resume(self):
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.refuse_existing_checkpoint_directory(True)
        self.assertEqual(caught.exception.code, "checkpoint_overwrite_risk")
        proved = contract.prove_weight_reload(reload_proof(7))
        self.assertFalse(proved["weight_reload_is_training_resume"])
        self.assertEqual(proved["state_comparison"]["compared_parameter_count"], 5)
        self.assertEqual(proved["state_comparison"]["comparison_selection"], "complete")
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.prove_weight_reload(reload_proof(7, mutate_last=True))
        self.assertEqual(caught.exception.code, "checkpoint_save_reload_incompatibility")
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.compare_complete_denoiser_state(state(7), state(7), selection="first_three")
        self.assertEqual(caught.exception.code, "checkpoint_save_reload_incompatibility")
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.prove_weight_reload(reload_proof(7, labelled_as_resume=True))
        self.assertEqual(caught.exception.code, "checkpoint_save_reload_incompatibility")
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.prove_weight_reload(reload_proof(0))
        self.assertIn(caught.exception.code, ("checkpoint_save_reload_incompatibility", "checkpoint_overwrite_risk"))
        contract.assert_configuration_compatible(config("original"), config("reloaded"))
        changed = config("reloaded")
        changed = copy.deepcopy(changed)
        changed["block"] = {"_name_or_path": "changed"}
        with self.assertRaises(contract.M6PilotError):
            contract.assert_configuration_compatible(config("original"), changed)
        root = tempfile.mkdtemp(prefix="m6-contract-tmp-")
        try:
            first = os.path.join(root, "update-7")
            contract.create_checkpoint_directory_exclusive(first)
            with self.assertRaises(contract.M6PilotError) as caught:
                contract.create_checkpoint_directory_exclusive(first)
            self.assertEqual(caught.exception.code, "checkpoint_overwrite_risk")
            with self.assertRaises(contract.M6PilotError) as caught:
                contract.directory_creation_allowed("/home/laura/rnagenesis-mres-runs/m6-not-created")
            self.assertEqual(caught.exception.code, "execution_not_authorised")
        finally:
            shutil.rmtree(root)

    def test_interruption_restart_and_no_learning_rate_fallback(self):
        policy = contract.interruption_policy()
        self.assertFalse(policy["resume_supported"])
        self.assertFalse(policy["interrupted_attempt_can_continue"])
        self.assertTrue(policy["restart_requires_new_output_directory"])
        self.assertTrue(policy["restart_requires_new_single_use_authorisation"])
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.assert_restart_refused(True, False)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.resolve_learning_rate(True)
        self.assertEqual(caught.exception.code, "automatic_lr_change_rejected")
        self.assertEqual(contract.resolve_learning_rate(False), contract.BASE_LEARNING_RATE)

    def test_updates_7_and_14_are_not_selectable_and_diagnostics_stay_gated(self):
        candidates = [{"update": 7, "loss": 0.01}, {"update": 14, "loss": 0.02}, {"update": 21, "loss": 0.5}]
        eligible = [item["update"] for item in candidates if contract.selection_eligibility(item["update"])["eligible"]]
        self.assertEqual(eligible, [])
        self.assertIn("not_selectable", contract.selection_eligibility(7)["reason"])
        consequence = contract.diagnostic_guardrail_consequence(True)
        self.assertEqual(consequence["status"], contract.DIAGNOSTIC_GENERATION_STATUS)
        self.assertFalse(consequence["automatic_rerun"])
        self.assertFalse(consequence["automatic_learning_rate_fallback"])
        self.assertFalse(consequence["eligible_for_m7"])
        self.assertEqual(consequence["nearest_train_similarity"], "report_only_no_approved_threshold")
        worsened = contract.classify_validation_change(1.0, 2.0, 7)
        self.assertTrue(worsened["human_review_signal"])
        self.assertFalse(worsened["automatic_early_stop"])
        self.assertIsNone(worsened["numeric_cutoff"])

    def test_exact_prefix_normalization(self):
        raw = "11ACGU"
        accepted = contract.normalize_generated_output(raw)
        self.assertTrue(accepted["accepted"])
        self.assertIs(accepted["raw_string"], raw)
        self.assertEqual(accepted["removed_prefix"], "11")
        self.assertEqual(accepted["normalized_string"], "ACGU")
        self.assertEqual(accepted["raw_length"], 6)
        self.assertEqual(accepted["normalized_length"], 4)
        failures = {
            "1ACGU": "leading_prefix_not_exact_11",
            "12ACGU": "leading_prefix_not_exact_11",
            "111": "body_not_exact_acgu",
            "11ACGU1": "body_not_exact_acgu",
            "11ACGU2": "body_not_exact_acgu",
            "11acgu": "body_not_exact_acgu",
            "11ACGT": "body_not_exact_acgu",
            "11ACGN": "body_not_exact_acgu",
            "11ACGU ": "body_not_exact_acgu",
            " 11ACGU": "leading_prefix_not_exact_11",
            "11": "empty_body",
        }
        for raw, reason in failures.items():
            record = contract.normalize_generated_output(raw)
            self.assertFalse(record["accepted"], raw)
            self.assertEqual(record["failure_reason"], reason, raw)
            self.assertEqual(record["raw_string"], raw)
            self.assertIsNone(record["normalized_string"])

    def test_ref_eval_and_obsolete_paths_are_refused_before_open(self):
        def opener(_path):
            raise AssertionError("opener was called")

        cases = [
            ("/tmp/synthetic/ref.csv", "TRAIN_TEXT", None, "ref_or_eval_access"),
            ("/tmp/synthetic/eval.csv", "VALIDATION_CSV", None, "ref_or_eval_access"),
            ("/tmp/synthetic/sequences.txt", "REF", None, "ref_or_eval_access"),
            ("/tmp/synthetic/sequences.txt", "EVAL", None, "ref_or_eval_access"),
            (
                "/home/laura/rnagenesis-aptamer-mres/data/processed/corpus_final.txt",
                "TRAIN_TEXT",
                None,
                "unexpected_biological_path_or_role",
            ),
            ("/tmp/synthetic/sequences.txt", "TRAIN_TEXT", contract.REF_HASH_METADATA, "ref_or_eval_access"),
        ]
        for path, role, claimed, code in cases:
            with self.assertRaises(contract.M6PilotError) as caught:
                contract.consider_input_path(path, role, True, claimed, opener)
            self.assertEqual(caught.exception.code, code, path)
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.consider_input_path(contract.FUTURE_TRAIN_TEXT_PATH, "TRAIN_TEXT", False, None, opener)
        self.assertEqual(caught.exception.code, "execution_not_authorised")

    def test_manifest_is_deterministic_and_exact(self):
        manifest = contract.build_control_flow_manifest(snapshot(later=2.0))
        contract.validate_success_manifest(manifest)
        self.assertEqual(contract.canonical_json(manifest), contract.canonical_json(contract.build_control_flow_manifest(snapshot(later=2.0))))
        self.assertEqual(set(manifest), set(contract.MANIFEST_KEYS))
        self.assertFalse(manifest["resume_supported"])
        self.assertEqual(manifest["diagnostic_generation_status"], contract.DIAGNOSTIC_GENERATION_STATUS)
        self.assertEqual(manifest["validation_review"]["observations"][0]["human_review_signal"], True)
        self.assertFalse(manifest["validation_review"]["automatic_early_stop"])
        self.assertIsNone(manifest["run_id"])
        self.assertIsNone(manifest["gpu"]["physical_index"])
        extra = dict(manifest)
        extra["sequence"] = "ACGUACGU"
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validate_success_manifest(extra)
        self.assertEqual(caught.exception.code, "incomplete_evidence_or_manifest")
        missing = dict(manifest)
        del missing["resume_supported"]
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.validate_success_manifest(missing)
        self.assertEqual(caught.exception.code, "incomplete_evidence_or_manifest")

    def test_stop_registry_classifies_every_literal_code(self):
        helpers = {
            "M6PilotError": 0,
            "_exact_keys": 2,
            "_finite_float": 1,
            "_require_mapping": 1,
            "_sha40_text": 1,
        }
        discovered = set()
        for relative in ("scripts/modelling/m6_pilot_contract.py", "scripts/modelling/m6_pilot_runner.py"):
            with open(os.path.join(ROOT, relative), "r", encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                else:
                    continue
                if name not in helpers or len(node.args) <= helpers[name]:
                    continue
                argument = node.args[helpers[name]]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    discovered.add(argument.value)
        classified = set(contract.STOP_CONDITION_CODES) | set(contract.INACTIVE_CLI_ONLY_STOP_CODES)
        self.assertEqual(discovered, classified)
        self.assertFalse(set(contract.STOP_CONDITION_CODES) & set(contract.INACTIVE_CLI_ONLY_STOP_CODES))
        manifest = contract.build_control_flow_manifest(snapshot())
        self.assertEqual(set(manifest["stop_conditions"]), set(contract.STOP_CONDITION_CODES))
        for code in contract.STOP_CONDITION_CODES:
            self.assertEqual(manifest["stop_conditions"][code], {"fired": False})
        for code in contract.INACTIVE_CLI_ONLY_STOP_CODES:
            self.assertNotIn(code, manifest["stop_conditions"])
        with self.assertRaises(contract.M6PilotError) as caught:
            contract.failure_payload(contract.M6PilotError("cli_argument_rejected", "not a consumed failure"))
        self.assertEqual(caught.exception.code, "incomplete_evidence_or_manifest")


if __name__ == "__main__":
    unittest.main()
