"""Shared CPU/mock support for the M7 tests (not a test module).

It provides a tiny CPU training stack, a harness that drives the real M7 worker
over it, and a cache of two successful single-seed runs. It does not open
biological corpora, model weights, accepted run directories, or a GPU. Torch is
used only for tiny CPU tensors.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import types
from unittest import mock

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

import torch

ROOT = "/home/laura/rnagenesis-aptamer-mres"
HERE = os.path.join(ROOT, "tests/modelling")
RUNNER_PATH = os.path.join(ROOT, "scripts/modelling/m7_replicate_runner.py")
SAFE_PARENT_ENVIRONMENT = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
BIOLOGICAL_PREFIXES = ("/home/laura/rnagenesis-mres-data", "/home/laura/rnagenesis-mres-runs", "/home/laura/RNAGenesis")
RNA_MESSAGE = "ACGUACGUACGUACGU"
TRAIN_COUNT = 669
VALIDATION_COUNT = 95


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_module("m7_runner_for_support", RUNNER_PATH)
contract = runner.contract
common = runner.common
m6 = runner.m6
m6r = runner.m6r
helpers = load_module("m7_contract_test_helpers", os.path.join(HERE, "test_m7_replicate_contract.py"))
_REAL_REALPATH = os.path.realpath


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_realpath(path, *args, **kwargs):
    """Never resolve a biological path. It is returned unchanged, so no metadata is read."""
    text = os.fspath(path)
    if text.startswith(BIOLOGICAL_PREFIXES):
        return text
    return _REAL_REALPATH(text, *args, **kwargs)


def asset_record(role, path, size, file_digest):
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


def accepted_assets_and_runtime():
    m5 = m6.m5_contract()
    assets = {}
    for relative, file_digest, size, role in m5.REQUIRED_MODEL_FILES:
        assets[role] = asset_record(role, os.path.join(str(m5.RNAGENESIS_ROOT), relative), size, file_digest)
    assets["diffusers_normalization_patch"] = asset_record(
        "diffusers_normalization_patch", m5.DIFFUSERS_PATCH_PATH, m5.DIFFUSERS_PATCH_SIZE, m5.DIFFUSERS_PATCH_SHA256
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


class TinyDenoiser(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.w1 = torch.nn.Parameter(torch.tensor([0.2, 0.3, 0.4, 0.5]))
        self.w2 = torch.nn.Parameter(torch.tensor([0.2, 0.3]))
        self.w3 = torch.nn.Parameter(torch.tensor([0.4, 0.5]))
        self.w4 = torch.nn.Parameter(torch.tensor([0.6]))
        self.register_buffer("scale", torch.ones(2))
        self.register_buffer("index", torch.zeros(1, dtype=torch.int64))
        self.config = {"_name_or_path": "original", "_class_name": "UNet", "layers": 2}


class TinyEncDec(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = torch.nn.Linear(2, 2)
        for parameter in self.parameters():
            parameter.requires_grad_(False)
        self.decoder = torch.nn.Identity()
        self.register_buffer("persistent_scale", torch.ones(2))
        self.decoder.register_buffer("_cos_cached", torch.zeros(2))
        self.eval()


class Accelerator(object):
    num_processes = 1
    gradient_accumulation_steps = 1
    mixed_precision = "no"
    device = "cuda:0"

    def __init__(self, stack):
        self.stack = stack

    def prepare(self, denoiser, optimizer):
        return denoiser, optimizer

    def backward(self, loss):
        self.stack.backward_values.append(float(loss.detach()))
        loss.backward()


class FakeClock(object):
    def __init__(self):
        self.now = 0.0

    def stamp(self):
        self.now += 1.0
        return self.now


class RecordingAdamW(torch.optim.AdamW):
    steps = None

    def step(self, *arguments, **keywords):
        if self.steps is not None:
            self.steps.append(float(self.param_groups[0]["lr"]))
        return super().step(*arguments, **keywords)


class StandIn(object):
    """A tiny CPU stack with the call surface of the pinned training stack."""

    production_identities = True
    cpu_stand_in = True
    enforce_runtime_isolation = True

    def __init__(
        self,
        assets,
        runtime,
        gpu_observation,
        fail_microbatch=None,
        save_mode="normal",
        reload_mode="normal",
        available_bytes=10**15,
        shared_denoiser=None,
        fail_exception=None,
    ):
        self.assets = assets
        self.runtime = runtime
        self.gpu_observation = gpu_observation
        self.fail_microbatch = fail_microbatch
        self.save_mode = save_mode
        self.reload_mode = reload_mode
        self.available_bytes = available_bytes
        self.shared_denoiser = shared_denoiser
        self.fail_exception = fail_exception
        self.fake_clock = FakeClock()
        self.encdec = TinyEncDec()
        self.denoisers = []
        self.train_batches = []
        self.backward_values = []
        self.raw_losses = []
        self.optimizer_steps = []
        self.validation_flags = []
        self.training_microbatches = 0
        self.reads = []
        self.saved_epochs = 0

    def statvfs(self, path):
        return types.SimpleNamespace(f_bavail=self.available_bytes // 4096, f_frsize=4096)

    def torch(self):
        return torch

    def clock(self):
        return self.fake_clock

    def observe_assets(self):
        return self.assets

    def observe_runtime(self):
        return self.runtime

    def observe_gpu_identity(self):
        return dict(self.gpu_observation)

    def cuda_device_count(self):
        return 1

    def place(self, tensor, device):
        return tensor

    def cuda_rng_state(self):
        return torch.zeros(4, dtype=torch.uint8)

    def accelerator(self):
        return Accelerator(self)

    def load_frozen_encdec(self, path):
        return self.encdec

    def load_b1_denoiser(self, path):
        if self.shared_denoiser is not None:
            return self.shared_denoiser
        denoiser = TinyDenoiser()
        self.denoisers.append(denoiser)
        return denoiser

    def load_scheduler(self, path):
        return types.SimpleNamespace(config=types.SimpleNamespace(num_train_timesteps=1000))

    def build_adamw(self, denoiser, learning_rate):
        optimizer = RecordingAdamW(
            denoiser.parameters(),
            lr=learning_rate,
            betas=(m6.ADAMW_BETA1, m6.ADAMW_BETA2),
            eps=m6.ADAMW_EPSILON,
            weight_decay=m6.ADAMW_WEIGHT_DECAY,
        )
        optimizer.steps = self.optimizer_steps
        return optimizer

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
        values = [int(example["sequence"]) for example in examples]
        if size != 1:
            self.train_batches.append(values)
        return {
            "input_ids": torch.tensor(values, dtype=torch.long).reshape(size, 1).expand(size, 4).clone(),
            "attention_mask": torch.ones(size, 4, dtype=torch.bool),
        }

    def extract_latents(self, encdec, input_ids, attention_mask):
        encdec.decoder._cos_cached.add_(1)
        base = input_ids[:, 0].float() / 1000.0 + 1.0
        return base.reshape(-1, 1, 1).expand(-1, 32, 160).clone()

    def sample_train_diffusion(self, batch_size, generator, num_train_timesteps, device):
        return torch.zeros(batch_size, dtype=torch.long), torch.zeros(batch_size, 32, 160)

    def denoising_mse(self, model, scheduler, latents, noise, timesteps):
        if model.training:
            self.training_microbatches += 1
            if self.fail_microbatch is not None and self.training_microbatches == self.fail_microbatch:
                raise self.fail_exception if self.fail_exception is not None else RuntimeError("fixture failure " + RNA_MESSAGE)
        else:
            self.validation_flags.append((torch.is_grad_enabled(), bool(model.training)))
        if latents.dtype != torch.float32 or noise.dtype != torch.float32 or timesteps.dtype != torch.int64:
            raise AssertionError("dtype drifted")
        latents = latents.float()
        prediction = latents * model.w1.sum() + latents * latents * (model.w2.sum() + model.w3.sum() + model.w4.sum())
        loss = torch.nn.functional.mse_loss(prediction, noise.float())
        if model.training:
            self.raw_losses.append(float(loss.detach()))
        return loss

    def save_checkpoint(self, denoiser, scheduler, directory):
        self.saved_epochs += 1
        buffer = io.BytesIO()
        torch.save({key: value.detach().clone() for key, value in denoiser.state_dict().items()}, buffer)
        weight = buffer.getvalue()
        if self.save_mode == "constant_weight":
            weight = b"FORBIDDEN-FIXTURE"
        for name in common.CHECKPOINT_MEMBERS:
            target = os.path.join(directory, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(weight if name == common.WEIGHT_MEMBER else name.encode("ascii"))
        if self.save_mode == "hardlink":
            os.link(os.path.join(directory, "model_index.json"), os.path.join(os.path.dirname(directory), "stray_link_%d" % self.saved_epochs))
        elif self.save_mode == "extra_member":
            with open(os.path.join(directory, "optimizer.pt"), "wb") as handle:
                handle.write(b"x")
        elif self.save_mode == "symlink_leaf":
            leaf = os.path.join(directory, "model_index.json")
            os.remove(leaf)
            os.symlink(os.path.join(directory, "unet", "config.json"), leaf)

    def reload_denoiser(self, directory):
        if self.reload_mode == "same_object":
            return self.denoisers[-1] if self.denoisers else self.shared_denoiser
        fresh = TinyDenoiser()
        source = self.denoisers[-1] if self.denoisers else self.shared_denoiser
        fresh.load_state_dict(source.state_dict())
        fresh.config = {"_name_or_path": "saved", "_class_name": "UNet", "layers": 2}
        if self.reload_mode == "mutate_buffer":
            fresh.index.add_(1)
        elif self.reload_mode == "mutate_parameter":
            with torch.no_grad():
                fresh.w4.add_(1e-3)
        elif self.reload_mode == "bad_config":
            fresh.config = {"_name_or_path": "saved", "_class_name": "UNet", "layers": 3}
        return fresh


def loaded_artifacts(entry):
    return {
        "manifest": {"validation_sequence_order_sha256": entry["validation_artifact_sha256"]["sequence_order"]},
        "noise": torch.zeros(m6.VALIDATION_NOISE_SHAPE),
        "timesteps": torch.zeros(m6.VALIDATION_TIMESTEP_SHAPE, dtype=torch.int64),
    }


class Harness(object):
    """One temporary run root, an active two-entry document, and the real worker over a stand-in."""

    def __init__(self, seeds=(43, 44), ld_library_path=None):
        self.temp = _REAL_REALPATH(tempfile.mkdtemp(prefix="m7test"))
        self.ld_library_path = ld_library_path
        self.raw, self.inactive = helpers.load_inactive()
        self.config = helpers.active_from(self.inactive, self.temp, seeds=seeds, ld_library_path=ld_library_path)
        self.entries = contract.assert_active_configuration(self.config, self.temp)
        self.verify_calls = []
        self.artifact_calls = []

    def close(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def observation(self, seed, consumed=False):
        entry = self.entries[seed]
        observed = helpers.observation(self.raw, self.inactive, entry)
        if consumed:
            observed["output_exists"] = True
        return observed

    def validated(self, seed):
        entry = self.entries[seed]
        return contract.validate_active_execution(self.config, entry["authorisation_id"], self.observation(seed), self.temp)

    def make_stack(self, seed, **faults):
        assets, runtime = accepted_assets_and_runtime()
        entry = self.entries[seed]
        gpu = {
            "cuda_visible_devices": entry["cuda_visible_devices"],
            "device_count": 1,
            "logical_device": "cuda:0",
            "pci_bus": entry["pci_bus"],
            "physical_index": entry["physical_gpu_index"],
            "source": "nvidia_smi_physical_index",
            "uuid": entry["gpu_uuid"],
        }
        gpu.update(faults.pop("gpu", {}))
        return StandIn(assets, runtime, gpu, **faults)

    def _verify_bound(self, path, role, expected_sha256, expected_count, bound_path, reader):
        self.verify_calls.append(role)
        return {
            "byte_size": 424242 if role == "TRAIN_TEXT" else 434343,
            "count": expected_count,
            "evidence_origin": "observed",
            "expected_count": expected_count,
            "expected_sha256": expected_sha256,
            "observation_method": "streamed_sha256",
            "opened": ["%04d" % index for index in range(expected_count)] if role == "TRAIN_TEXT" else ["%04d" % (1000 + index) for index in range(expected_count)],
            "path": os.path.abspath(path),
            "role": role,
            "sha256": expected_sha256,
        }

    def _verify_artifacts(self, path, bound_path, expected_hashes, loader):
        self.artifact_calls.append(path)
        entry = next(iter(self.entries.values()))
        return {
            "loaded": loaded_artifacts(entry),
            "observed_files": {
                name: asset_record(name, os.path.join(path, name), 1000 + index, expected_hashes[name])
                for index, name in enumerate(m6.VALIDATION_ARTIFACT_FILES, start=1)
            },
        }

    @contextlib.contextmanager
    def patched(self, child_environment):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, child_environment, clear=True))
            stack.enter_context(mock.patch.object(m6, "verify_bound_file", self._verify_bound))
            stack.enter_context(mock.patch.object(m6, "verify_artifact_directory", self._verify_artifacts))
            stack.enter_context(mock.patch.object(os.path, "realpath", safe_realpath))
            yield

    def consume(self, seed):
        entry = self.validated(seed)
        directory = contract.consume_entry(entry, self.temp)
        common.create_isolated_directories(directory)
        env = common.build_child_environment(self.parent_environment(), entry["physical_gpu_index"], directory, entry["ld_library_path"])
        return entry, directory, env

    def interpreter_observer(self, seed):
        """A mock interpreter observation equal to the bound identity. The live interpreter is never inspected."""
        return lambda path: dict(self.entries[seed]["interpreter"])

    def parent_environment(self):
        parent = dict(SAFE_PARENT_ENVIRONMENT)
        if self.ld_library_path is not None:
            parent["LD_LIBRARY_PATH"] = self.ld_library_path
        return parent

    def run_worker(self, seed, stack):
        """Consume one entry and run the real ``worker_main`` over the stand-in. Returns (directory, error)."""
        entry, directory, env = self.consume(seed)
        runner.reset_process_claim_for_tests()
        error = None
        with self.patched(env):
            try:
                runner.worker_main(
                    directory,
                    entry["authorisation_id"],
                    config_loader=lambda: self.config,
                    observation_loader=lambda config, selected: self.observation(seed, consumed=True),
                    stack_loader=lambda authorised: stack,
                    interpreter_observer=self.interpreter_observer(seed),
                )
            except BaseException as exc:
                error = exc
        return directory, error

    def run_direct(self, seed, stack, entry=None, extra_env=None):
        """Consume one entry and call the run function directly. Returns (manifest, progress, error, directory)."""
        authorised, directory, env = self.consume(seed)
        env = dict(env, **(extra_env or {}))
        entry = authorised if entry is None else entry
        progress = common.new_progress(seed, "replicate")
        runner.reset_process_claim_for_tests()
        manifest = None
        error = None
        with self.patched(env):
            try:
                manifest = runner.run_authorised_replicate(entry, stack, directory, progress=progress)
            except BaseException as exc:
                error = exc
        return manifest, progress, error, directory


_CACHE = {}


def successful_run(seed):
    """Two real mock runs, one per seed, kept for the life of the test process."""
    if not _CACHE:
        harness = Harness()
        runs = {}
        for each in (43, 44):
            stack = harness.make_stack(each)
            directory, error = harness.run_worker(each, stack)
            if error is not None:
                raise error
            with open(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME), "rb") as handle:
                blob = handle.read()
            runs[each] = {"blob": blob, "directory": directory, "manifest": json.loads(blob.decode("utf-8")), "stack": stack}
        _CACHE["harness"] = harness
        _CACHE["runs"] = runs
    return _CACHE["runs"][seed]


def cached_harness():
    successful_run(43)
    return _CACHE["harness"]


def cleanup_cache():
    harness = _CACHE.pop("harness", None)
    _CACHE.pop("runs", None)
    if harness is not None:
        harness.close()


def reseal(manifest):
    """Canonical bytes for a manifest dictionary."""
    return common.canonical_json(manifest)


def variant(manifest, mse_by_epoch=None, weight_salt=None):
    """A valid replicate manifest with other fixed-draw validation values (and re-hashed weights).

    The ranking is recomputed from the new values, so the variant stays internally
    consistent and passes the replicate validator.
    """
    changed = copy.deepcopy(manifest)
    if mse_by_epoch is not None:
        for row in changed["validation_observations"]:
            if row["update"] != 0:
                row["aggregate_mse"] = common.format_decimal(mse_by_epoch[row["epoch"]])
        values = {row["epoch"]: row["aggregate_mse"] for row in changed["validation_observations"] if row["candidate"]}
        order = common.rank_validation_candidates(values)
        changed["validation_ranking"]["ranked_candidates"] = [
            {"aggregate_mse": values[epoch], "epoch": epoch, "rank": position, "update": contract.epoch_update_range(epoch)[1]}
            for position, epoch in enumerate(order, start=1)
        ]
    if weight_salt is not None:
        for item in changed["checkpoints"]:
            for member in list(item["saved_hashes"]):
                item["saved_hashes"][member] = digest("%s:%s:%s" % (weight_salt, item["epoch"], member))
            item["weight_sha256"] = item["saved_hashes"][common.WEIGHT_MEMBER]
    contract.validate_replicate_manifest(changed)
    return changed


# ------------------------------------------------------------------ guardrail and selection fixtures

guardrails = load_module("m7_guardrails_for_support", os.path.join(ROOT, "scripts/modelling/m7_candidate_guardrails.py"))
selection = load_module("m7_selection_for_support", os.path.join(ROOT, "scripts/modelling/m7_selection.py"))

PASSING_VALUES = {
    "valid_nonempty_acgu_fraction": 1.0,
    "empty_or_unparseable_fraction": 0.0,
    "unique_fraction": 1.0,
    "exact_train_match_rate": 0.0,
    "largest_duplicate_share": 0.001,
}
FAILING_VALUES = dict(PASSING_VALUES, unique_fraction=0.5)
DIAGNOSTICS = {
    "edit_similarity_definition": guardrails.diagnostic().EDIT_SIMILARITY_DEFINITION,
    "edit_similarity_is_sequence_identity": False,
    "effect_on_ranking_or_thresholds": "none",
    "file": guardrails.REPORT_ONLY_DIAGNOSTICS_NAME,
    "headline": {
        "dinucleotide_total_variation_to_train": 0.31,
        "maximum_edit_similarity_to_train": 0.44,
        "mfe_median": -7.5,
        "mfe_per_nt_median": -0.21,
        "nearest_train_normalized_edit_distance_median": 0.62,
        "nucleotide_total_variation_to_train": 0.12,
        "paired_fraction_median": 0.55,
    },
    "sha256": digest("ledger:report_only_diagnostics_sha256"),
    "thresholds_defined": False,
}
INTERPRETER = {
    "path": common.PINNED_PYTHON,
    "resolved_path": common.PINNED_ENVIRONMENT_PREFIX + "/bin/python3.8",
    "sha256": digest("pinned interpreter executable"),
    "size": 17000000,
}
REPORT_ONLY = {
    "diagnostics": DIAGNOSTICS,
    "early_eos_count": 29,
    "eligibility_effect": "none",
    "gross_length_behaviour": {"mean_length_delta": "-0.5"},
    "requested_length_exact_hit_rate": "0.971",
    "requested_length_matching": {"exact_hits": 971},
    "thresholds_defined": False,
}


LEDGER_HASHES = {key: digest("ledger:" + key) for key in guardrails.LEDGER_FILES}


def implementation_hashes():
    return {path: digest(path) for path in guardrails.IMPLEMENTATION_FILE_PATHS}


def ranking_hash(manifest):
    return selection._ranking_sha256(manifest["validation_ranking"])


def guardrail_entry(manifest, epoch, position, preceding):
    seed = manifest["seed"]
    return {
        "authorisation_id": "m7_unit_seed%d_epoch%d_candidate" % (seed, epoch),
        "authorization_commit": manifest["authorisation"]["authorization_commit"],
        "authorization_parent_commit": manifest["authorisation"]["authorization_parent_commit"],
        "candidate_epoch": epoch,
        "candidate_seed": seed,
        "executing_implementation_commit": manifest["authorisation"]["executing_implementation_commit"],
        "preceding_candidates": list(preceding),
        "ranking_position": position,
    }


def guardrail_blob(manifest, replicate_blob, epoch, passed, position, preceding):
    """Canonical bytes for one candidate-guardrail manifest bound to a replicate manifest."""
    checkpoint = next(item for item in manifest["checkpoints"] if item["epoch"] == epoch)
    values = next(row["aggregate_mse"] for row in manifest["validation_observations"] if row["epoch"] == epoch)
    entry = guardrail_entry(manifest, epoch, position, preceding)
    weight = checkpoint["weight_sha256"]
    built = guardrails.build_candidate_manifest(
        entry,
        {
            "epoch": epoch,
            "replicate_manifest_sha256": common.sha256_bytes(replicate_blob),
            "seed": manifest["seed"],
            "validation_mse": values,
            "validation_ranking_sha256": ranking_hash(manifest),
            "weight_sha256": weight,
        },
        {
            "directory_name": checkpoint["directory_name"],
            "members_sha256": dict(checkpoint["saved_hashes"]),
            "tree_unchanged_across_generation": True,
            "weight_sha256": weight,
            "weights_sha256_after_generation": weight,
            "weights_sha256_before_generation": weight,
        },
        guardrails.evaluate_guardrail_values(PASSING_VALUES if passed else FAILING_VALUES),
        dict(REPORT_ONLY),
        {
            "cleaner_sha256": guardrails.CLEANER_SHA256,
            "invocation_count": 112,
            "raw_attempts": 1000,
            "schedule_sha256": m6.PAIRED_SCHEDULE_SHA256,
            "valid_outputs": 1000 if passed else 700,
        },
        {"cuda_visible_devices": "1", "logical_device": "cuda:0", "pci_bus": "00000000:61:00.0", "physical_index": 1, "uuid": "GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f"},
        {"interpreter": dict(INTERPRETER), "ld_library_path": common.unbound_ld_library_path_record()},
        dict(LEDGER_HASHES),
        guardrails.provenance_block(implementation_hashes()),
    )
    return common.canonical_json(built)


def scenario(seed, mse, outcomes, salt=None):
    """(replicate blob, [guardrail blobs]) for one seed.

    ``outcomes`` are the pass/fail results of the candidates in ranking order;
    they cover a prefix of the ranking, as lazy evaluation requires.
    """
    base = successful_run(seed)["manifest"]
    manifest = variant(base, mse_by_epoch=mse, weight_salt=salt if salt is not None else "seed%d" % seed)
    blob = common.canonical_json(manifest)
    order = [item["epoch"] for item in manifest["validation_ranking"]["ranked_candidates"]]
    blobs = []
    preceding = []
    for position, passed in enumerate(outcomes, start=1):
        epoch = order[position - 1]
        blob_i = guardrail_blob(manifest, blob, epoch, passed, position, list(preceding))
        blobs.append(blob_i)
        if not passed:
            preceding.append({"epoch": epoch, "manifest_sha256": common.sha256_bytes(blob_i), "outcome": "failed"})
    return blob, blobs, manifest


def deviation_blob(replicate_blob, manifest, decision_time="2026-10-08T15:30:00+11:00", **changes):
    seconds = manifest["timing"]["end_to_end_seconds"]
    projected = selection.project_completion(decision_time, seconds)
    record = {
        "completed_seeds": [43],
        "decision_time": decision_time,
        "depends_on_scientific_results": False,
        "deviation_id": "m7_deviation_seed44_omitted_unit",
        "kind": selection.DEVIATION_KIND,
        "m8_generation_started": False,
        "measured_seed_43_end_to_end_seconds": seconds,
        "omitted_seed": 44,
        "projected_completion_time": projected.replace(microsecond=0).isoformat(),
        "projected_exceeds_hard_target": True,
        "recorded_before_m8_generation": True,
        "rule": dict(selection.RULE_RECORD),
        "schema_version": selection.DEVIATION_SCHEMA_VERSION,
        "sealed": True,
        "sealed_at": "2026-10-08T15:45:00+11:00",
        "sealed_by": "human_operator",
        "seed_43_replicate_manifest_sha256": common.sha256_bytes(replicate_blob),
    }
    record.update(changes)
    return common.canonical_json(selection.seal_deviation(record))
