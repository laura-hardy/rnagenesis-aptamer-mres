"""CPU/mock tests for the inactive M6 pilot runner.

The production entry is exercised in a subprocess so heavy imports would be
visible. Synthetic control flow uses an in-memory backend and does not open
biological files, checkpoints, or CUDA.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import sys
import textwrap
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

ROOT = "/home/laura/rnagenesis-aptamer-mres"
RUNNER_PATH = os.path.join(ROOT, "scripts/modelling/m6_pilot_runner.py")
CONFIG_PATH = os.path.join(ROOT, "config/experiments/D1_diffusion_pilot.yaml")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_module("m6_pilot_runner_under_test", RUNNER_PATH)
contract = runner.contract


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SyntheticBackend:
    mode = "synthetic-cpu-test"
    opens_biological_files = False

    def __init__(self, loss=1.0, norm=0.5, validation=0.2, checkpoint_exists=False, mutate_reload=False, finite_gradients=True):
        self.loss = loss
        self.norm = norm
        self.validation = validation
        self._checkpoint_exists = checkpoint_exists
        self.mutate_reload = mutate_reload
        self._finite_gradients = finite_gradients
        self.recorded_manifest = None
        self.recorded_failure = None
        self.opened = []

    def cpu_permutation(self, count, seed):
        if count != 669 or seed != 42:
            raise AssertionError("unexpected permutation request")
        return list(range(1, count)) + [0]

    def encdec_snapshot(self):
        return {name: {"requires_grad": False, "trainable_count": 0, "changed": False} for name in contract.ENCDEC_COMPONENTS}

    def optimizer_membership(self):
        return {
            "denoiser_parameter_names": ["denoiser.weight"],
            "encdec_parameter_names": ["encoder.weight", "decoder.weight"],
            "optimizer_parameter_names": ["denoiser.weight"],
        }

    def validation_source(self):
        return {
            "loaded_from_accepted_artifacts": True,
            "regenerated": False,
            "timestep_shape": contract.VALIDATION_TIMESTEP_SHAPE,
            "noise_shape": contract.VALIDATION_NOISE_SHAPE,
            "timestep_sha256": contract.VALIDATION_TIMESTEPS_SHA256,
            "noise_sha256": contract.VALIDATION_NOISE_SHA256,
            "seed": 1,
        }

    def validation_pair_batches(self, update):
        value = 0.5 if update == 7 else self.validation
        return [[value] * 300, [value] * 80]

    def training_loss(self, update, micro_index, size):
        del micro_index, size
        if isinstance(self.loss, dict):
            return self.loss.get(update, 1.0)
        return self.loss

    def gradients_finite(self, update):
        del update
        return self._finite_gradients

    def pre_clip_gradient_norm(self, update):
        if isinstance(self.norm, dict):
            return self.norm.get(update, 0.5)
        return self.norm

    def denoiser_digest(self, update, when):
        return digest(f"{update}-{when}")

    def checkpoint_exists(self, update):
        del update
        return self._checkpoint_exists

    def checkpoint_proof(self, update):
        original = {f"parameter_{index}": f"value-{update}-{index}" for index in range(5)}
        reloaded = dict(original)
        if self.mutate_reload:
            reloaded["parameter_4"] = "mismatch"
        return {
            "update": update,
            "fresh_object_constructed": True,
            "original_object_id": 10 + update,
            "reloaded_object_id": 50 + update,
            "labelled_as_resume": False,
            "selection": "complete",
            "saved_hashes": {name: digest(f"{name}-{update}") for name in contract.CHECKPOINT_MEMBERS},
            "original_state": original,
            "reloaded_state": reloaded,
            "original_config": {"_name_or_path": "original", "_class_name": "UNet", "layers": 2},
            "reloaded_config": {"_name_or_path": "saved", "_class_name": "UNet", "layers": 2},
        }

    def memory(self):
        return {"peak_allocated_bytes": 42, "peak_reserved_bytes": 64}

    def timing(self):
        return {"training_seconds": 3.5, "validation_seconds": 1.25}


class RunnerTests(unittest.TestCase):
    def test_source_has_no_heavy_import(self):
        with open(RUNNER_PATH, "r", encoding="utf-8") as handle:
            text = handle.read()
        for line in text.splitlines():
            stripped = line.strip()
            self.assertFalse(stripped.startswith("import torch"))
            self.assertFalse(stripped.startswith("import accelerate"))
            self.assertFalse(stripped.startswith("import diffusers"))
            self.assertNotIn("import train_diffusion_mres", stripped)
            self.assertNotIn("clean_generated_sequences", stripped)

    def test_help_and_overrides_do_not_open_files(self):
        opened = []
        real_open = open

        def tracking_open(path, *args, **kwargs):
            opened.append(os.fspath(path))
            return real_open(path, *args, **kwargs)

        import builtins

        original = builtins.open
        builtins.open = tracking_open
        try:
            self.assertEqual(runner.production_main(["--help"]), 0)
            self.assertEqual(opened, [])
            with self.assertRaises(contract.M6PilotError) as caught:
                runner.production_main(["--output-dir", "/tmp/m6-not-created"])
            self.assertEqual(caught.exception.code, "cli_argument_rejected")
            self.assertEqual(opened, [])
            os.environ["M6_OUTPUT_DIRECTORY"] = "/tmp/m6-not-created"
            try:
                with self.assertRaises(contract.M6PilotError) as caught:
                    runner.production_main([])
                self.assertEqual(caught.exception.code, "environment_injection_rejected")
                self.assertEqual(opened, [])
            finally:
                del os.environ["M6_OUTPUT_DIRECTORY"]
        finally:
            builtins.open = original

    def test_inactive_configuration_rejects_before_resources(self):
        opened = []
        real_open = open

        def tracking_open(path, *args, **kwargs):
            opened.append(os.fspath(path))
            text = os.fspath(path)
            if text != CONFIG_PATH:
                raise AssertionError("unexpected open " + text)
            return real_open(path, *args, **kwargs)

        import builtins

        original = builtins.open
        builtins.open = tracking_open
        mkdir_calls = []
        original_mkdir = os.mkdir
        os.mkdir = lambda path, *args, **kwargs: mkdir_calls.append(path)
        try:
            with self.assertRaises(contract.M6PilotError) as caught:
                runner.production_main([])
            self.assertEqual(caught.exception.code, "execution_not_authorised")
            self.assertEqual(opened, [CONFIG_PATH])
            self.assertEqual(mkdir_calls, [])
            with self.assertRaises(contract.M6PilotError) as caught:
                runner.load_training_stack({"heavy_imports_authorised": True})
            self.assertEqual(caught.exception.code, "execution_not_authorised")
        finally:
            builtins.open = original
            os.mkdir = original_mkdir

    def test_subprocess_rejects_without_heavy_imports(self):
        probe = textwrap.dedent(
            """\
            import importlib.util
            import sys
            spec = importlib.util.spec_from_file_location("m6_probe", sys.argv[1])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            code = module.main([])
            heavy = [
                name for name in sys.modules
                if name.split(".")[0] in {"torch", "accelerate", "diffusers", "train_diffusion_mres"}
            ]
            print("EXIT", code)
            print("HEAVY", ",".join(heavy))
            """
        )
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["CUDA_VISIBLE_DEVICES"] = ""
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        env["HF_DATASETS_OFFLINE"] = "1"
        completed = subprocess.run(
            [sys.executable, "-c", probe, RUNNER_PATH],
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("EXIT 1", completed.stdout)
        self.assertIn("HEAVY \n", completed.stdout)
        self.assertIn("execution_not_authorised", completed.stderr)

    def test_synthetic_control_flow_schedule_memory_and_manifest(self):
        backend = SyntheticBackend(norm={3: 2.5}, validation=0.2)
        result = runner.run_synthetic_control_flow(backend)
        events = result["events"]
        self.assertEqual([event[1] for event in events if event[0] == "validation"], [0, 7, 14, 21])
        self.assertEqual(len([event for event in events if event[0] == "optimizer_step"]), 21)
        self.assertEqual(len([event for event in events if event[0] == "microbatch_backward"]), 84)
        self.assertEqual([event[1] for event in events if event[0] == "checkpoint_saved"], [7, 14, 21])
        learning_rates = [event for event in events if event[0] == "learning_rate_recorded"]
        steps = [event for event in events if event[0] == "optimizer_step"]
        self.assertEqual(len(learning_rates), 21)
        self.assertTrue(all(event[2] > 0.0 for event in learning_rates))
        for recorded, step in zip(learning_rates, steps):
            self.assertLess(events.index(recorded), events.index(step))
            self.assertEqual(recorded[1], step[1])
        self.assertLess(events.index(("validation", 0)), events.index(steps[0]))
        clip = [event for event in events if event[0] == "gradient_clipped" and event[1] == 3][0]
        self.assertTrue(clip[2])
        self.assertFalse(clip[3])
        manifest = result["manifest"]
        self.assertIsNone(result["failure"])
        self.assertFalse(manifest["resume_supported"])
        self.assertFalse(any(item["weight_reload_is_training_resume"] for item in manifest["weight_checkpoints"]))
        self.assertEqual(manifest["memory"]["peak_allocated_bytes"], 42)
        self.assertEqual(manifest["memory"]["peak_reserved_bytes"], 64)
        self.assertNotEqual(manifest["memory"]["peak_allocated_bytes"], manifest["memory"]["peak_reserved_bytes"])
        self.assertTrue(manifest["validation_review"]["observations"][0]["human_review_signal"])
        self.assertFalse(manifest["validation_review"]["automatic_early_stop"])
        self.assertEqual(manifest["diagnostic_generation_status"], contract.DIAGNOSTIC_GENERATION_STATUS)
        self.assertEqual(manifest["stop_conditions"]["non_finite_training_loss"]["fired"], False)
        self.assertNotIn("finite_gradient_norm_above_clip", manifest["stop_conditions"])
        sizes = [event[2] for event in events if event[0] == "microbatch_backward"]
        self.assertEqual(sizes[-4:], [8, 8, 8, 5])
        repeated = runner.run_synthetic_control_flow(SyntheticBackend(norm={3: 2.5}, validation=0.2))
        self.assertEqual(contract.canonical_json(manifest), contract.canonical_json(repeated["manifest"]))

    def test_failures_do_not_publish_a_manifest(self):
        cases = [
            SyntheticBackend(loss=float("nan")),
            SyntheticBackend(finite_gradients=False),
            SyntheticBackend(norm=float("inf")),
            SyntheticBackend(validation=float("nan")),
            SyntheticBackend(checkpoint_exists=True),
            SyntheticBackend(mutate_reload=True),
        ]
        codes = [
            "non_finite_training_loss",
            "non_finite_trainable_gradient",
            "non_finite_pre_clip_gradient_norm",
            "non_finite_validation",
            "checkpoint_overwrite_risk",
            "checkpoint_save_reload_incompatibility",
        ]
        for backend, code in zip(cases, codes):
            with self.assertRaises(contract.M6PilotError) as caught:
                runner.run_synthetic_control_flow(backend)
            self.assertEqual(caught.exception.code, code)
            self.assertIsNone(backend.recorded_manifest)
            self.assertFalse(backend.recorded_failure["manifest_written"])
            self.assertFalse(backend.recorded_failure["resume_supported"])


if __name__ == "__main__":
    unittest.main()
