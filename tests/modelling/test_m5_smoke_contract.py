"""CPU-only tests for the inactive M5 synthetic-smoke contract.

These tests use temporary synthetic files. They do not read frozen
biological corpora, protected M4 evidence, model weights, a GPU,
or a run evidence directory.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

ROOT = Path("/home/laura/rnagenesis-aptamer-mres")
CONFIG_PATH = ROOT / "config/experiments/D1_diffusion_smoke.yaml"
CONTRACT_PATH = ROOT / "scripts/modelling/m5_smoke_contract.py"
HARNESS_PATH = ROOT / "scripts/modelling/m5_smoke_harness.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = load_module("m5_smoke_contract_under_test", CONTRACT_PATH)
PARENT = "a" * 40
HEAD = "b" * 40
OUTPUT = "/home/laura/rnagenesis-mres-runs/m5-synthetic-contract-test-not-created"


class _Stat:
    def __init__(self, mode, size):
        self.st_mode = mode
        self.st_size = size


def reload_proof(raw_equal=True, normalized_equal=True):
    saved = {
        "model_index.json": "1" * 64,
        "scheduler/scheduler_config.json": "2" * 64,
        "unet/config.json": "3" * 64,
        "unet/diffusion_pytorch_model.safetensors": "4" * 64,
    }
    raw_original = "6" * 64
    raw_reloaded = raw_original if raw_equal else "7" * 64
    normalized_original = "e" * 64
    normalized_reloaded = normalized_original if normalized_equal else "f" * 64
    original_ignored = "source-original"
    reloaded_ignored = "source-original" if raw_equal else "source-reloaded"
    return {
        "saved_file_hashes": saved,
        "fresh_load_succeeded": True,
        "original_denoiser_id": 11,
        "reloaded_denoiser_id": 22,
        "tensor_digest_comparisons": [{"name": "weight", "saved": "5" * 64, "reloaded": "5" * 64, "match": True}],
        "original_config_sha256": raw_original,
        "reloaded_config_sha256": raw_reloaded,
        "raw_config_sha256_equal": raw_original == raw_reloaded,
        "configuration_compatibility": {
            "ignored_top_level_keys": ["_name_or_path"],
            "original_ignored_values": {"_name_or_path": original_ignored},
            "reloaded_ignored_values": {"_name_or_path": reloaded_ignored},
            "original_normalized_config_sha256": normalized_original,
            "reloaded_normalized_config_sha256": normalized_reloaded,
            "normalized_config_sha256_equal": normalized_original == normalized_reloaded,
        },
        "configuration_compatible": normalized_original == normalized_reloaded,
    }


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def activate(config, **overrides):
    active = copy.deepcopy(config)
    active["document_status"] = contract.EXECUTABLE_DOCUMENT_STATUS
    active["consumable_by_executable_workflow"] = True
    active["execution"]["authorised"] = True
    active["execution"]["gpu_authorised_by_this_approval"] = True
    active["smoke_execution"]["executable_now"] = True
    active["smoke_execution"]["status"] = contract.ACTIVE_SMOKE_STATUS
    block = dict(active[contract.AUTHORISATION_NAME])
    block.update(
        {
            "authorisation_id": "m5_synthetic_test_authorisation",
            "authorisation_active": True,
            "activation_status": contract.ACTIVE_UNCONSUMED_STATUS,
            "consumed": False,
            "single_use_run_id": "m5_synthetic_test_run",
            "authorization_parent_commit": PARENT,
            "executing_implementation_commit": PARENT,
            "implementation_config_sha256": sha256_file(CONFIG_PATH),
            "output_directory": OUTPUT,
            "evidence_directory": OUTPUT,
            "authorisation_timestamp": "2026-10-02T00:00:00+00:00",
            "scope": "synthetic smoke only",
            "gpu_use_authorised": True,
            "authorises_m5_synthetic_smoke": True,
            "physical_gpu": 3,
            "gpu_uuid": "GPU-test-uuid",
            "pci_bus": "00000000:99:00.0",
        }
    )
    block.update(overrides)
    active[contract.AUTHORISATION_NAME] = block
    return active


class FakeGate:
    def __init__(self, config_bytes, porcelain="", file_porcelain=None, rna_head=None, digests=None, environ=None, probe=None, output=OUTPUT):
        self.config_bytes = config_bytes
        self.porcelain = porcelain
        self.file_porcelain = contract.reviewed_rnagenesis_porcelain() if file_porcelain is None else file_porcelain
        self.rna_head = contract.RNAGENESIS_HEAD if rna_head is None else rna_head
        self.digests = {relative: digest for relative, digest, _size, _role in contract.REQUIRED_MODEL_FILES}
        if digests:
            self.digests.update(digests)
        self.environ = {} if environ is None else environ
        self.probe = "3, GPU-test-uuid, 00000000:99:00.0, Test GPU\n" if probe is None else probe
        self.output_directory = output
        self.physical_gpu = 3
        self.gpu_calls = []
        self.hashed_paths = []
        self.require_absent_output = True

    def read_bytes(self, path):
        if Path(path) == contract.CONFIG_PATH:
            return self.config_bytes
        if Path(path) == contract.FIXTURE_PATH:
            return contract.FIXTURE_PATH.read_bytes()
        return Path(path).read_bytes()

    def git(self, repo, args):
        if Path(repo) == contract.RNAGENESIS_ROOT:
            if args == ["rev-parse", "HEAD"]:
                return self.rna_head + "\n"
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return contract.RNAGENESIS_BRANCH + "\n"
            if args == ["status", "--porcelain=v1"]:
                return contract.reviewed_rnagenesis_porcelain()
            if args == ["status", "--porcelain=v1", "-uall"]:
                return self.file_porcelain
        if args == ["rev-parse", "HEAD"]:
            return HEAD + "\n"
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return "main\n"
        if args == ["rev-parse", "origin/main"]:
            return HEAD + "\n"
        if args == ["status", "--porcelain=v1"]:
            return self.porcelain
        if args == ["rev-parse", "HEAD^@"]:
            return PARENT + "\n"
        if args == ["diff", "--name-only", PARENT, HEAD]:
            return contract.CONFIG_RELATIVE + "\n"
        if args == ["show", PARENT + ":" + contract.CONFIG_RELATIVE]:
            return CONFIG_PATH.read_text(encoding="utf-8")
        if args == ["show", "HEAD:" + contract.CONFIG_RELATIVE]:
            return self.config_bytes.decode("utf-8")
        if args[:2] == ["rev-parse", PARENT + ":" + contract.CONTRACT_RELATIVE] or args == ["hash-object", "--", str(contract.CONTRACT_PATH)]:
            return "1" * 40 + "\n"
        if args[:2] == ["rev-parse", PARENT + ":" + contract.HARNESS_RELATIVE] or args == ["hash-object", "--", str(contract.HARNESS_PATH)]:
            return "2" * 40 + "\n"
        raise AssertionError("unexpected git call " + " ".join(args))

    def sha256_file(self, path):
        text = str(path)
        if text == contract.DIFFUSERS_PATCH_PATH:
            self.hashed_paths.append(text)
            return contract.DIFFUSERS_PATCH_SHA256
        relative = str(Path(text).relative_to(contract.RNAGENESIS_ROOT))
        self.hashed_paths.append(relative)
        if relative not in self.digests:
            raise AssertionError("unexpected model hash " + relative)
        return self.digests[relative]

    def lstat(self, path):
        text = str(path)
        if text == str(contract.FIXTURE_PATH) or text == contract.PINNED_PYTHON:
            return os.lstat(text)
        if text == self.output_directory:
            raise FileNotFoundError(text)
        if text == contract.DIFFUSERS_PATCH_PATH:
            return _Stat(stat.S_IFREG | 0o644, contract.DIFFUSERS_PATCH_SIZE)
        relative = str(Path(text).relative_to(contract.RNAGENESIS_ROOT))
        for item_relative, _digest, size, _role in contract.REQUIRED_MODEL_FILES:
            if relative == item_relative:
                return _Stat(stat.S_IFREG | 0o644, size)
        raise FileNotFoundError(text)

    def run_argv(self, argv):
        self.gpu_calls.append(list(argv))
        return self.probe


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = CONFIG_PATH.read_bytes()
        cls.config = contract.load_config_bytes(cls.raw)
        cls.contract_bytes = CONTRACT_PATH.read_bytes()
        cls.harness_bytes = HARNESS_PATH.read_bytes()

    def test_checked_in_configuration_is_inactive(self):
        contract.assert_inactive_configuration(self.config, self.contract_bytes, self.harness_bytes)
        self.assertNotIn("physical_gpu", self.config[contract.AUTHORISATION_NAME])
        self.assertNotIn("gpu_uuid", self.config[contract.AUTHORISATION_NAME])
        self.assertNotIn("pci_bus", self.config[contract.AUTHORISATION_NAME])
        self.assertIsNone(self.config["unresolved_d1_decisions"]["physical_microbatch"])
        self.assertIsNone(self.config["unresolved_d1_decisions"]["m6_seed"])
        self.assertIsNone(self.config["unresolved_d1_decisions"]["m7_seeds"])
        self.assertNotIn("physical_gpu", self.raw.decode("utf-8"))

    def test_inactive_configuration_is_rejected_before_gpu_or_assets(self):
        gate = FakeGate(self.raw)
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.evaluate_parent_gate(gate)
        self.assertEqual(caught.exception.code, "configuration_not_consumable")
        self.assertEqual(gate.gpu_calls, [])
        self.assertEqual(gate.hashed_paths, [])

    def test_missing_authorisation_field_is_rejected(self):
        active = activate(self.config)
        del active[contract.AUTHORISATION_NAME]["single_use_run_id"]
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_active_authorisation(active, 3, OUTPUT)
        self.assertEqual(caught.exception.code, "authorisation_field_missing")

    def test_wrong_commits_and_dirty_trees_are_rejected(self):
        active = activate(self.config, executing_implementation_commit="c" * 40)
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_active_authorisation(active, 3, OUTPUT)
        self.assertEqual(caught.exception.code, "authorisation_commit_invalid")
        gate = FakeGate(self._dump(activate(self.config)), porcelain=" M scripts/modelling/m5_smoke_contract.py\n")
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.evaluate_parent_gate(gate)
        self.assertEqual(caught.exception.code, "provenance_mismatch")
        self.assertEqual(gate.gpu_calls, [])

    def test_wrong_rnagenesis_commit_is_rejected(self):
        gate = FakeGate(self._dump(activate(self.config)), rna_head="d" * 40)
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.evaluate_parent_gate(gate)
        self.assertEqual(caught.exception.code, "provenance_mismatch")
        self.assertEqual(gate.hashed_paths, [])

    def test_unexpected_untracked_source_and_configuration_are_rejected(self):
        extra = contract.reviewed_rnagenesis_porcelain() + "?? evil.py\n"
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_no_unexpected_untracked_source(extra)
        self.assertEqual(caught.exception.code, "unexpected_untracked_source")
        yaml_extra = contract.reviewed_rnagenesis_porcelain() + "?? configs/evil.yaml\n"
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_no_unexpected_untracked_source(yaml_extra)
        self.assertEqual(caught.exception.code, "unexpected_untracked_source")
        gate = FakeGate(self._dump(activate(self.config)), file_porcelain=extra)
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.evaluate_parent_gate(gate)
        self.assertEqual(caught.exception.code, "unexpected_untracked_source")

    def test_wrong_asset_identity_and_b0_substitution_are_rejected(self):
        digests = {relative: digest for relative, digest, _size, _role in contract.REQUIRED_MODEL_FILES}
        digests["configs/rnagenesis/diffusion/unet/config.json"] = "e" * 64
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_model_assets(digests)
        self.assertEqual(caught.exception.code, "asset_identity_mismatch")
        digests["configs/rnagenesis/diffusion/unet/config.json"] = contract.B0_UNET_CONFIG_SHA256
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_model_assets(digests)
        self.assertEqual(caught.exception.code, "b0_substituted_for_b1")
        weight = "configs/rnagenesis/diffusion/unet/diffusion_pytorch_model.safetensors"
        digests["configs/rnagenesis/diffusion/unet/config.json"] = [
            item[1] for item in contract.REQUIRED_MODEL_FILES if item[3] == "b1_unet_config"
        ][0]
        digests[weight] = contract.B0_UNET_WEIGHT_SHA256
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_model_assets(digests)
        self.assertEqual(caught.exception.code, "b0_substituted_for_b1")

    def test_fixture_path_basename_hash_symlink_and_nonregular_file_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            regular = root / contract.FIXTURE_BASENAME
            regular.write_bytes(contract.FIXTURE_PATH.read_bytes())

            def read_bytes(path):
                with open(path, "rb") as handle:
                    return handle.read()

            link = root / "link.txt"
            link.symlink_to(regular)
            with self.assertRaises(contract.M5SmokeError) as caught:
                contract.assert_fixture_file(str(link), contract.FIXTURE_RELATIVE, contract.FIXTURE_SHA256, read_bytes, os.lstat)
            self.assertEqual(caught.exception.code, "fixture_rejected")
            with self.assertRaises(contract.M5SmokeError):
                contract.assert_fixture_file(str(root), contract.FIXTURE_RELATIVE, contract.FIXTURE_SHA256, read_bytes, os.lstat)
            wrong_name = root / "other.txt"
            wrong_name.write_bytes(contract.FIXTURE_PATH.read_bytes())
            with self.assertRaises(contract.M5SmokeError):
                contract.assert_fixture_file(str(wrong_name), contract.FIXTURE_RELATIVE, contract.FIXTURE_SHA256, read_bytes, os.lstat)
            mutated = root / contract.FIXTURE_BASENAME
            mutated.write_text("ACGU\n", encoding="utf-8")
            with self.assertRaises(contract.M5SmokeError):
                contract.assert_fixture_file(str(mutated), contract.FIXTURE_RELATIVE, contract.FIXTURE_SHA256, read_bytes, os.lstat)
            with self.assertRaises(contract.M5SmokeError):
                contract.assert_fixture_file(str(regular), "other/path.txt", contract.FIXTURE_SHA256, read_bytes, os.lstat)

    def test_denied_biological_names_and_hashes_are_rejected_without_opening_them(self):
        for name in ("corpus_final.txt", "ft_train.csv", "ft_validation.csv", "ref.csv", "eval.csv"):
            self.assertTrue(contract.path_denied("/tmp/" + name, None))
        for component in ("TRAIN", "VALIDATION", "REF", "EVAL"):
            self.assertTrue(contract.path_denied("/tmp/" + component + "/synthetic.txt", None))
        for digest in contract.DENIED_HASHES:
            with self.assertRaises(contract.M5SmokeError) as caught:
                contract.assert_not_denied_input("/tmp/synthetic.txt", digest)
            self.assertEqual(caught.exception.code, "denied_input")
        claimed = {
            "opened_paths": [contract.FIXTURE_RELATIVE],
            "dynamic_file_open_audit_performed": False,
        }
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.derive_data_access(claimed, {"rnagenesis_commit": contract.RNAGENESIS_HEAD})
        self.assertEqual(caught.exception.code, "denied_input")

    def test_existing_output_and_conflicting_gpu_selection_are_rejected(self):
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_output_isolated("/tmp/m5-outside-the-run-root")
        self.assertEqual(caught.exception.code, "output_directory_invalid")
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_output_isolated(str(contract.RUN_ROOT))
        self.assertEqual(caught.exception.code, "output_directory_invalid")
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_output_isolated(OUTPUT + "/")
        self.assertEqual(caught.exception.code, "output_directory_invalid")
        with tempfile.TemporaryDirectory() as tmp:
            link = os.path.join(tmp, "linked-run-root")
            os.symlink(str(contract.RUN_ROOT), link)
            with self.assertRaises(contract.M5SmokeError) as caught:
                contract.assert_output_isolated(link + "/m5-child")
            self.assertEqual(caught.exception.code, "output_directory_symlink")
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_output_directory_absent(OUTPUT, lambda path: _Stat(stat.S_IFREG | 0o644, 0))
        self.assertEqual(caught.exception.code, "output_directory_exists")
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_inherited_cuda({"CUDA_VISIBLE_DEVICES": "4"}, 3)
        self.assertEqual(caught.exception.code, "conflicting_cuda_visible_devices")
        gate = FakeGate(self._dump(activate(self.config)), environ={"CUDA_VISIBLE_DEVICES": "4"})
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.evaluate_parent_gate(gate)
        self.assertEqual(caught.exception.code, "conflicting_cuda_visible_devices")
        self.assertEqual(len(gate.gpu_calls), 1)

    def test_gpu_identity_mismatch_and_logical_device_are_enforced(self):
        authorisation = activate(self.config)[contract.AUTHORISATION_NAME]
        probe = contract.parse_gpu_probe("3, GPU-other, 00000000:99:00.0, Test GPU\n", 3)
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_gpu_probe(probe, 3, authorisation)
        self.assertEqual(caught.exception.code, "gpu_identity_mismatch")
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_logical_device(
                {
                    "cuda_device_count": 2,
                    "device": contract.LOGICAL_DEVICE,
                    "logical_index": 0,
                    "cuda_visible_devices": "3",
                    "cpu_fallback": False,
                    "other_gpu_fallback": False,
                },
                3,
            )
        self.assertEqual(caught.exception.code, "logical_device_rejected")

    def test_authorised_plan_uses_argument_arrays_and_isolated_caches(self):
        gate = FakeGate(self._dump(activate(self.config)))
        plan = contract.evaluate_parent_gate(gate)
        self.assertFalse(plan["shell"])
        self.assertEqual(plan["argv"][1], "-B")
        self.assertEqual(plan["argv"][0], contract.PINNED_PYTHON)
        self.assertNotIn("shell", plan["argv"])
        self.assertEqual(plan["env"]["CUDA_VISIBLE_DEVICES"], "3")
        self.assertEqual(plan["env"]["CUDA_DEVICE_ORDER"], "PCI_BUS_ID")
        self.assertEqual(plan["env"]["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(plan["env"]["HF_HUB_OFFLINE"], "1")
        self.assertEqual(plan["env"]["TRANSFORMERS_OFFLINE"], "1")
        self.assertEqual(plan["env"]["HF_DATASETS_OFFLINE"], "1")
        for key in ("HF_HOME", "TRANSFORMERS_CACHE", "TORCH_HOME", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX"):
            self.assertTrue(plan["env"][key].startswith(OUTPUT))
        model_paths = [path for path in gate.hashed_paths if path != contract.DIFFUSERS_PATCH_PATH]
        self.assertIn(contract.DIFFUSERS_PATCH_PATH, gate.hashed_paths)
        self.assertIn(contract.BIOMAP_CONFIG_RELATIVE, model_paths)
        self.assertTrue(all(path.startswith("configs/rnagenesis/") or path.startswith("models/autoencoder/") for path in model_paths))
        self.assertNotIn("checkpoints/Aptamer/diffusion/unet/diffusion_pytorch_model.safetensors", gate.hashed_paths)

    def test_exclusive_directory_creation_does_not_use_exist_ok(self):
        source = CONTRACT_PATH.read_text(encoding="utf-8") + HARNESS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("exist_ok=True", source)
        self.assertNotIn("exist_ok = True", source)
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.create_directory_exclusive("/tmp/m5-evidence-outside-root")
        self.assertEqual(caught.exception.code, "output_directory_invalid")
        self.assertFalse(os.path.lexists(OUTPUT))
        original_mkdir = os.mkdir

        def refuse_second(path, mode=0o777):
            del mode
            raise FileExistsError(path)

        os.mkdir = refuse_second
        try:
            with self.assertRaises(contract.M5SmokeError) as caught:
                contract.create_directory_exclusive(OUTPUT)
            self.assertEqual(caught.exception.code, "output_directory_exists")
        finally:
            os.mkdir = original_mkdir
        self.assertFalse(os.path.lexists(OUTPUT))

    def test_reusable_sources_do_not_hard_code_a_physical_gpu(self):
        for path in (CONFIG_PATH, CONTRACT_PATH, HARNESS_PATH):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("physical_gpu: 0", text)
            self.assertNotIn("physical_gpu: 1", text)
            self.assertNotIn("PHYSICAL_GPU = 0", text)
            self.assertNotIn("PHYSICAL_GPU = 1", text)
            self.assertNotIn("cuda:1", text)

    def test_importing_the_contract_does_not_import_heavy_modules(self):
        script = (
            "import importlib.util, os, sys\n"
            "os.environ['CUDA_VISIBLE_DEVICES'] = ''\n"
            "spec = importlib.util.spec_from_file_location('m5c', %r)\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(module)\n"
            "banned = [name for name in sys.modules if name.split('.')[0] in ('torch', 'accelerate', 'diffusers') or name == 'generation' or name.startswith('models.')]\n"
            "sys.stdout.write(','.join(banned))\n"
        ) % str(CONTRACT_PATH)
        completed = subprocess.run(
            [os.environ.get("M5_TEST_PYTHON", "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python"), "-B", "-c", script],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": "", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_authorisation_delta_rejects_a_smoke_setting_change(self):
        active = activate(self.config)
        contract.assert_authorisation_delta(self.config, active)
        changed = copy.deepcopy(active)
        changed["smoke_only"] = dict(changed["smoke_only"])
        changed["smoke_only"]["learning_rate"] = "1.0e-5"
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_authorisation_delta(self.config, changed)
        self.assertEqual(caught.exception.code, "authorisation_delta_invalid")

    def test_missing_or_wrong_diffusers_patch_and_biomap_config_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch = root / "normalization.py"
            patch.write_bytes(b"not-the-patch")

            def read_hash(path):
                return sha256_file(path)

            with self.assertRaises(contract.M5SmokeError) as caught:
                contract.assert_regular_hashed_file(
                    str(patch),
                    contract.DIFFUSERS_PATCH_SIZE,
                    contract.DIFFUSERS_PATCH_SHA256,
                    os.lstat,
                    read_hash,
                    "diffusers_normalization_patch",
                )
            self.assertEqual(caught.exception.code, "asset_identity_mismatch")
            missing = root / "missing-normalization.py"
            with self.assertRaises(contract.M5SmokeError) as caught:
                contract.assert_regular_hashed_file(
                    str(missing),
                    contract.DIFFUSERS_PATCH_SIZE,
                    contract.DIFFUSERS_PATCH_SHA256,
                    os.lstat,
                    read_hash,
                    "diffusers_normalization_patch",
                )
            self.assertEqual(caught.exception.code, "asset_identity_mismatch")
            biomap = root / "config.json"
            biomap.write_bytes(b"{}")
            link = root / "config-link.json"
            link.symlink_to(biomap)
            with self.assertRaises(contract.M5SmokeError) as caught:
                contract.assert_regular_hashed_file(
                    str(link),
                    1369,
                    "bf7ef6843232f370f3f7fc37d608f85cb0ff0d75291eed35cef52213e34978f7",
                    os.lstat,
                    read_hash,
                    "biomap_encoder_config",
                )
            self.assertEqual(caught.exception.code, "asset_identity_mismatch")
            with self.assertRaises(contract.M5SmokeError) as caught:
                contract.assert_regular_hashed_file(
                    str(biomap),
                    1369,
                    "bf7ef6843232f370f3f7fc37d608f85cb0ff0d75291eed35cef52213e34978f7",
                    os.lstat,
                    read_hash,
                    "biomap_encoder_config",
                )
            self.assertEqual(caught.exception.code, "asset_identity_mismatch")

    def test_overfit_trajectory_uses_the_loss_after_the_final_update(self):
        rule = contract.EXPECTED_SMOKE_ONLY["loss_pass_rule"]
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_overfit([1.0, 0.8, 0.5, 0.2], rule, "0", 4)
        self.assertEqual(caught.exception.code, "overfit_failed")
        with self.assertRaises(contract.M5SmokeError) as caught:
            contract.assert_overfit([1.0, 0.2, 0.2, 0.2, 1.0], rule, "0", 4)
        self.assertEqual(caught.exception.code, "overfit_failed")
        self.assertTrue(contract.assert_overfit([1.0, 0.8, 0.6, 0.4, 0.2], rule, "0", 4))

    def test_manifest_schema_matches_the_worker_field_order(self):
        text = (ROOT / "docs/fine_tuning/run_manifest_schema.md").read_text(encoding="utf-8")
        field_block = text.split("MANIFEST_FIELD_ORDER\n", 1)[1].split("\nEND_MANIFEST_FIELD_ORDER", 1)[0]
        hash_block = text.split("OBSERVED_FILE_HASH_KEYS\n", 1)[1].split("\nEND_OBSERVED_FILE_HASH_KEYS", 1)[0]
        self.assertEqual(tuple(field_block.splitlines()), contract.MANIFEST_KEYS)
        self.assertEqual(tuple(hash_block.splitlines()), contract.OBSERVED_FILE_HASH_KEYS)
        reload_block = text.split("CHECKPOINT_RELOAD_FIELD_ORDER\n", 1)[1].split("\nEND_CHECKPOINT_RELOAD_FIELD_ORDER", 1)[0]
        compatibility_block = text.split("CONFIGURATION_COMPATIBILITY_FIELD_ORDER\n", 1)[1].split(
            "\nEND_CONFIGURATION_COMPATIBILITY_FIELD_ORDER", 1
        )[0]
        self.assertEqual(tuple(reload_block.splitlines()), contract.CHECKPOINT_RELOAD_FIELD_ORDER)
        self.assertEqual(tuple(compatibility_block.splitlines()), contract.CONFIGURATION_COMPATIBILITY_FIELD_ORDER)
        self.assertNotIn("actual_input_paths", contract.MANIFEST_KEYS)
        self.assertNotIn("manifest_sha256", contract.MANIFEST_KEYS)

    def test_configuration_compatibility_requires_raw_digests_and_exact_allowlist(self):
        proof = reload_proof()
        self.assertTrue(contract.assert_checkpoint_reload(proof))
        differing_raw = reload_proof(raw_equal=False)
        self.assertNotEqual(differing_raw["original_config_sha256"], differing_raw["reloaded_config_sha256"])
        self.assertFalse(differing_raw["raw_config_sha256_equal"])
        self.assertTrue(contract.assert_checkpoint_reload(differing_raw))
        self.assertEqual(
            contract.CONFIGURATION_COMPATIBILITY_IGNORED_TOP_LEVEL_KEYS,
            ("_name_or_path",),
        )
        b1_config = [row for row in contract.REQUIRED_MODEL_FILES if row[3] == "b1_unet_config"]
        self.assertEqual(
            b1_config,
            [
                (
                    "configs/rnagenesis/diffusion/unet/config.json",
                    "3a9975ff165bbd5ca82923e6ed1c5ed7eb383a23f4f3f55db713c995031f8ee3",
                    531,
                    "b1_unet_config",
                )
            ],
        )

        def reject(sample, detail):
            with self.assertRaises(contract.M5SmokeError) as caught:
                contract.assert_checkpoint_reload(sample)
            self.assertEqual(caught.exception.code, "checkpoint_reload_mismatch")
            self.assertEqual(caught.exception.detail, detail)

        missing_record = reload_proof()
        del missing_record["configuration_compatibility"]
        reject(missing_record, "checkpoint configuration compatibility evidence is missing")
        missing_raw = reload_proof()
        del missing_raw["original_config_sha256"]
        reject(missing_raw, "raw configuration digests are missing")
        missing_normalized = reload_proof()
        del missing_normalized["configuration_compatibility"]["original_normalized_config_sha256"]
        reject(missing_normalized, "checkpoint configuration compatibility evidence is missing")
        malformed_raw = reload_proof()
        malformed_raw["original_config_sha256"] = "g" * 64
        reject(malformed_raw, "raw configuration digest is malformed")
        malformed_normalized = reload_proof()
        malformed_normalized["configuration_compatibility"]["reloaded_normalized_config_sha256"] = "e" * 63
        reject(malformed_normalized, "normalized configuration digest is malformed")
        uppercase = reload_proof()
        uppercase["reloaded_config_sha256"] = "A" * 64
        reject(uppercase, "raw configuration digest is malformed")

        extra_key = reload_proof()
        extra_key["configuration_compatibility"]["ignored_top_level_keys"] = ["_name_or_path", "in_channels"]
        extra_key["configuration_compatibility"]["original_ignored_values"]["in_channels"] = 160
        extra_key["configuration_compatibility"]["reloaded_ignored_values"]["in_channels"] = 160
        reject(extra_key, "configuration normalization ignores an extra key")
        wildcard = reload_proof()
        wildcard["configuration_compatibility"]["ignored_top_level_keys"] = ["*"]
        reject(wildcard, "configuration normalization must not be recursive or wildcarded")
        recursive = reload_proof()
        recursive["configuration_compatibility"]["ignored_top_level_keys"] = ["layers._name_or_path"]
        reject(recursive, "configuration normalization must not be recursive or wildcarded")
        recursive_flag = reload_proof()
        recursive_flag["configuration_compatibility"]["recursive"] = True
        reject(recursive_flag, "checkpoint configuration compatibility record is malformed")
        class_name = reload_proof()
        class_name["configuration_compatibility"]["ignored_top_level_keys"] = ["_class_name"]
        reject(class_name, "configuration normalization must not ignore _class_name or _diffusers_version")
        diffusers_version = reload_proof()
        diffusers_version["configuration_compatibility"]["ignored_top_level_keys"] = ["_diffusers_version"]
        reject(diffusers_version, "configuration normalization must not ignore _class_name or _diffusers_version")
        unobserved = reload_proof()
        unobserved["configuration_compatibility"]["original_ignored_values"] = {}
        reject(unobserved, "ignored configuration values were not observed")

        raw_flag = reload_proof(raw_equal=False)
        raw_flag["raw_config_sha256_equal"] = True
        reject(raw_flag, "raw configuration equality does not match the recorded digests")
        raw_flag_false = reload_proof()
        raw_flag_false["raw_config_sha256_equal"] = False
        reject(raw_flag_false, "raw configuration equality does not match the recorded digests")
        normalized_flag = reload_proof(normalized_equal=False)
        normalized_flag["configuration_compatibility"]["normalized_config_sha256_equal"] = True
        normalized_flag["configuration_compatible"] = True
        reject(normalized_flag, "normalized configuration equality does not match the recorded digests")
        claimed_compatible = reload_proof(normalized_equal=False)
        claimed_compatible["configuration_compatible"] = True
        reject(claimed_compatible, "configuration compatibility does not match the allowlist and normalized digests")
        functional_mismatch = reload_proof(normalized_equal=False)
        reject(functional_mismatch, "reloaded configuration is not compatible")

    def test_parsed_checkpoint_mappings_accept_any_insertion_order(self):
        def reorder(mapping):
            return {key: mapping[key] for key in reversed(tuple(mapping))}

        def lexicographic(mapping):
            return {key: mapping[key] for key in sorted(mapping)}

        def reject(sample, detail):
            with self.assertRaises(contract.M5SmokeError) as caught:
                contract.assert_checkpoint_reload(sample)
            self.assertEqual(caught.exception.code, "checkpoint_reload_mismatch")
            self.assertEqual(caught.exception.detail, detail)

        worker_order = reload_proof()
        self.assertEqual(tuple(worker_order), contract.CHECKPOINT_RELOAD_FIELD_ORDER)
        self.assertEqual(
            tuple(worker_order["configuration_compatibility"]),
            contract.CONFIGURATION_COMPATIBILITY_FIELD_ORDER,
        )
        self.assertTrue(contract.assert_checkpoint_reload(worker_order))

        reversed_proof = reorder(worker_order)
        reversed_proof["configuration_compatibility"] = reorder(worker_order["configuration_compatibility"])
        self.assertNotEqual(tuple(reversed_proof), contract.CHECKPOINT_RELOAD_FIELD_ORDER)
        self.assertNotEqual(
            tuple(reversed_proof["configuration_compatibility"]),
            contract.CONFIGURATION_COMPATIBILITY_FIELD_ORDER,
        )
        self.assertTrue(contract.assert_checkpoint_reload(reversed_proof))

        parsed_order = lexicographic(worker_order)
        parsed_order["configuration_compatibility"] = lexicographic(worker_order["configuration_compatibility"])
        self.assertNotEqual(tuple(parsed_order), contract.CHECKPOINT_RELOAD_FIELD_ORDER)
        self.assertTrue(contract.assert_checkpoint_reload(parsed_order))

        missing_nested = reload_proof()
        del missing_nested["configuration_compatibility"]["reloaded_ignored_values"]
        reject(missing_nested, "checkpoint configuration compatibility evidence is missing")
        missing_top = reload_proof()
        del missing_top["saved_file_hashes"]
        reject(missing_top, "checkpoint inventory is missing")

        unexpected_nested = reload_proof()
        unexpected_nested["configuration_compatibility"]["recursive"] = True
        reject(unexpected_nested, "checkpoint configuration compatibility record is malformed")
        unexpected_top = reload_proof()
        unexpected_top["generation_object_id"] = 99
        reject(unexpected_top, "checkpoint reload record has an unexpected field")

        raw_flag = reload_proof(raw_equal=False)
        raw_flag["raw_config_sha256_equal"] = True
        reject(raw_flag, "raw configuration equality does not match the recorded digests")
        normalized_flag = reload_proof(normalized_equal=False)
        normalized_flag["configuration_compatibility"]["normalized_config_sha256_equal"] = True
        normalized_flag["configuration_compatible"] = True
        reject(normalized_flag, "normalized configuration equality does not match the recorded digests")

        extra_ignored = reload_proof()
        extra_ignored["configuration_compatibility"]["ignored_top_level_keys"] = ["_name_or_path", "in_channels"]
        extra_ignored["configuration_compatibility"]["original_ignored_values"]["in_channels"] = 160
        extra_ignored["configuration_compatibility"]["reloaded_ignored_values"]["in_channels"] = 160
        reject(extra_ignored, "configuration normalization ignores an extra key")
        wildcard = reload_proof()
        wildcard["configuration_compatibility"]["ignored_top_level_keys"] = ["*"]
        reject(wildcard, "configuration normalization must not be recursive or wildcarded")
        nested_exclusion = reload_proof()
        nested_exclusion["configuration_compatibility"]["ignored_top_level_keys"] = ["mid_block._name_or_path"]
        reject(nested_exclusion, "configuration normalization must not be recursive or wildcarded")
        functional_mismatch = reload_proof(normalized_equal=False)
        reject(functional_mismatch, "reloaded configuration is not compatible")

    def _dump(self, config):
        import yaml

        return yaml.safe_dump(config, sort_keys=False).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
