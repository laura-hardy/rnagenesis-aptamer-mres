#!/usr/bin/env python3
"""M5 synthetic-smoke parent and worker.

The parent validates the inactive-or-active contract before it imports a
model stack. The checked-in configuration fails that gate. A later
authorisation commit can open the gate. The worker, and only the worker,
imports torch and the RNAGenesis trainer, then calls the trainer's public
functions. generation.py is not imported: it assigns XDG_CACHE_HOME.
Generation reload uses GuidedDDIMPipeline1D.from_pretrained directly.

Nothing in this module selects a physical GPU. The physical index, UUID,
and PCI bus come from the authorisation. After visibility remapping the
worker is required to see one device and to use logical cuda:0.
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import os
import subprocess
import sys
import time
import weakref
from pathlib import Path

MRES_ROOT = Path("/home/laura/rnagenesis-aptamer-mres")


def _load_contract():
    path = MRES_ROOT / "scripts/modelling/m5_smoke_contract.py"
    spec = importlib.util.spec_from_file_location("m5_smoke_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = _load_contract()


class ParentDependencies:
    def __init__(self, output_directory, physical_gpu, environ=None, run_argv=None, spawn=None):
        self.output_directory = output_directory
        self.physical_gpu = physical_gpu
        self.environ = os.environ if environ is None else environ
        self.run_argv = run_argv or _default_run_argv
        self.spawn = spawn or _default_spawn
        self.require_absent_output = True

    def read_bytes(self, path):
        with open(path, "rb") as handle:
            return handle.read()

    def git(self, repo, args):
        completed = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
        if completed.returncode != 0:
            raise contract.M5SmokeError("git_status_unreadable", "git command failed")
        return completed.stdout

    def sha256_file(self, path):
        digest = __import__("hashlib").sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def lstat(self, path):
        return os.lstat(path)


def _default_run_argv(argv):
    completed = subprocess.run(argv, check=False, capture_output=True, text=True, shell=False)
    if completed.returncode != 0:
        raise contract.M5SmokeError("gpu_probe_invalid", "GPU query failed")
    return completed.stdout


def _default_spawn(argv, env, cwd):
    return subprocess.run(argv, cwd=cwd, env=env, check=False, shell=False)


def _mkdir(path):
    try:
        os.mkdir(path)
    except FileExistsError:
        raise contract.M5SmokeError("output_directory_exists", "refusing to overwrite " + os.path.basename(path))


def _create_cache_directories(evidence):
    cache_root = os.path.join(evidence, contract.RUNTIME_CACHE_DIRECTORY_NAME)
    huggingface = os.path.join(cache_root, "huggingface")
    for path in (
        os.path.join(evidence, contract.PYCACHE_DIRECTORY_NAME),
        cache_root,
        huggingface,
        os.path.join(huggingface, "hub"),
        os.path.join(huggingface, "assets"),
        os.path.join(huggingface, "modules"),
        os.path.join(cache_root, "torch"),
    ):
        _mkdir(path)


def run_parent(deps):
    """Validate, create one evidence directory, and spawn the worker."""
    plan = contract.evaluate_parent_gate(deps)
    contract.create_directory_exclusive(plan["evidence_directory"])
    try:
        _create_cache_directories(plan["evidence_directory"])
        gate_path = os.path.join(plan["evidence_directory"], "parent_gate.json")
        contract.publish_exclusive(gate_path, contract.canonical_json({"authorization_commit": plan["authorization_commit"]}))
        completed = deps.spawn(plan["argv"], plan["env"], plan["cwd"])
    except contract.M5SmokeError as exc:
        _write_failure(plan["evidence_directory"], exc)
        raise
    if completed.returncode != 0:
        failure_path = os.path.join(plan["evidence_directory"], "m5_smoke_failure_record.json")
        if not os.path.exists(failure_path):
            _write_failure(
                plan["evidence_directory"],
                contract.M5SmokeError("worker_failed", "worker exited without a passing manifest"),
            )
        raise contract.M5SmokeError("worker_failed", "worker exited without a passing manifest")
    return plan


def _write_failure(evidence, exc):
    path = os.path.join(evidence, "m5_smoke_failure_record.json")
    if os.path.exists(path):
        return
    contract.publish_exclusive(path, contract.canonical_json(contract.failure_record(exc.code, exc.detail)))


def execute_observed(observed, smoke_only):
    """Apply the smoke assertions. A failure returns no final manifest."""
    try:
        manifest = perform_smoke(observed, smoke_only)
    except contract.M5SmokeError as exc:
        return None, contract.failure_record(exc.code, exc.detail)
    return manifest, None


def perform_smoke(observed, smoke_only):
    contract.assert_smoke_only(smoke_only)
    contract.assert_shape_observation(observed["shapes"])
    contract.assert_microbatch_accounting(observed["shapes"], smoke_only, observed["batch_accounting"])
    contract.assert_loss_finite(observed["loss"])
    contract.assert_gradient_summaries(observed["gradients"])
    contract.assert_frozen_snapshot(observed["frozen_after_backward"])
    contract.assert_denoiser_update(observed["update"])
    contract.assert_frozen_snapshot(observed["frozen_after_update"])
    contract.assert_post_generation_frozen_snapshot(observed["frozen_final"])
    contract.assert_checkpoint_reload(observed["checkpoint"])
    contract.assert_resume_proof(observed["resume"])
    contract.assert_overfit(
        observed["overfit_losses"],
        smoke_only["loss_pass_rule"],
        smoke_only["loss_decrease_tolerance"],
        smoke_only["overfit_optimizer_updates"],
    )
    contract.assert_observed_file_hashes(observed["file_hashes"])
    contract.assert_generation_proof(
        observed["generation"],
        smoke_only["generation_count"],
        observed["file_hashes"]["checkpoint_inventory"],
    )
    contract.assert_phase_records(observed["phase_records"])
    contract.assert_starting_ema_inspection(observed["starting_ema_inspection"])
    contract.assert_package_runtime(observed["package_runtime"])
    report = dict(observed["report"])
    access = contract.derive_data_access(
        observed["data_input_audit"],
        {
            "mres_implementation_commit": report["mres_implementation_commit"],
            "mres_authorization_commit": report["mres_authorization_commit"],
            "rnagenesis_commit": report["rnagenesis_commit"],
        },
    )
    accounting = observed["batch_accounting"]
    peaks = observed["memory_peaks"]
    report["declared_scientific_data_inputs"] = access["declared_scientific_data_inputs"]
    report["validated_required_asset_paths"] = access["validated_required_asset_paths"]
    report["data_input_audit"] = {
        "declared_scientific_data_inputs": access["declared_scientific_data_inputs"],
        "validated_required_asset_paths": access["validated_required_asset_paths"],
        "cli_scientific_data_arguments": access["cli_scientific_data_arguments"],
        "data_access_guard_basis": access["data_access_guard_basis"],
        "dynamic_file_open_audit_performed": access["dynamic_file_open_audit_performed"],
        "conclusion": access["conclusion"],
    }
    report["permitted_input_paths"] = [contract.FIXTURE_RELATIVE]
    report["train_not_accessed"] = access["train_not_accessed"]
    report["validation_not_accessed"] = access["validation_not_accessed"]
    report["ref_not_accessed"] = access["ref_not_accessed"]
    report["eval_not_accessed"] = access["eval_not_accessed"]
    report["requested_microbatch"] = accounting["requested_microbatch"]
    report["measured_microbatch"] = accounting["measured_microbatch"]
    report["actual_batch_shape"] = list(observed["shapes"]["input_ids_shape"])
    report["requested_accumulation"] = accounting["requested_accumulation"]
    report["measured_accumulation"] = accounting["measured_accumulation"]
    report["requested_effective_batch"] = accounting["requested_effective_batch"]
    report["measured_effective_batch"] = accounting["measured_effective_batch"]
    report["phase_records"] = observed["phase_records"]
    report["starting_ema_inspection"] = observed["starting_ema_inspection"]
    report["file_hashes"] = observed["file_hashes"]
    report["package_runtime"] = observed["package_runtime"]
    report["frozen_state"] = {
        "after_backward": observed["frozen_after_backward"],
        "after_update": observed["frozen_after_update"],
        "after_generation": observed["frozen_final"],
    }
    report["checkpoint_reload"] = observed["checkpoint"]
    report["resume_proof"] = observed["resume"]
    report["loss_finite"] = True
    report["gradients_finite"] = True
    report["overfit_trajectory"] = list(observed["overfit_losses"])
    report["overfit_pass_rule"] = smoke_only["loss_pass_rule"]
    report["overfit_passed"] = True
    report["completion_state"] = "correctness_phase_passed"
    report["failure_state"] = None
    report["m5_milestone_complete"] = False
    report["smoke_measurements_are_not_d1_decisions"] = True
    report["precision_used"] = smoke_only["smoke_precision"]
    report["ema_enabled"] = False
    report["generation_weight_variant"] = smoke_only["generation_weights"]
    report["generation_reload"] = observed["generation"]
    report["generation_output"] = observed["generation_output"]
    report["peak_training_allocated_bytes"] = peaks["training_allocated_bytes"]
    report["peak_training_reserved_bytes"] = peaks["training_reserved_bytes"]
    report["peak_allocated_bytes"] = peaks["overall_allocated_bytes"]
    report["peak_reserved_bytes"] = peaks["overall_reserved_bytes"]
    report["memory_peak_accounting"] = peaks["accounting"]
    return contract.build_final_manifest(report)


def compare_cpu_resume(steps_before=1, steps_after=2, tolerance=0.0):
    """Compare an uninterrupted CPU Adam run with save, reload, and resume.

    Tolerance 0 is justified because both paths run the same float32 CPU
    operations, from the same initial weights, on a dedicated generator.
    This is a software-behaviour check on a tiny fake model. It is not a
    claim about the RNAGenesis denoiser. Weight-only reload is not resume.
    """
    import torch

    if torch.cuda.is_available() or torch.cuda.device_count() != 0:
        raise contract.M5SmokeError("logical_device_rejected", "CPU resume comparison saw a CUDA device")
    initial_generator = torch.Generator(device="cpu")
    initial_generator.manual_seed(1234)
    initial_weight = torch.randn(1, 4, generator=initial_generator)
    initial_bias = torch.randn(1, generator=initial_generator)

    def fresh_model():
        model = torch.nn.Linear(4, 1, bias=True)
        with torch.no_grad():
            model.weight.copy_(initial_weight)
            model.bias.copy_(initial_bias)
        return model

    def data_generator():
        generator = torch.Generator(device="cpu")
        generator.manual_seed(99)
        return generator

    def one_step(model, optimizer, scheduler, generator):
        optimizer.zero_grad(set_to_none=True)
        inputs = torch.randn(8, 4, generator=generator)
        loss = (model(inputs) ** 2).mean()
        loss.backward()
        optimizer.step()
        scheduler.step()
        return float(loss.detach())

    def build(model):
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-2)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=steps_before + steps_after)
        return optimizer, scheduler

    uninterrupted = fresh_model()
    uninterrupted_optimizer, uninterrupted_scheduler = build(uninterrupted)
    uninterrupted_generator = data_generator()
    for _ in range(steps_before + steps_after):
        one_step(uninterrupted, uninterrupted_optimizer, uninterrupted_scheduler, uninterrupted_generator)

    resumed = fresh_model()
    resumed_optimizer, resumed_scheduler = build(resumed)
    resumed_generator = data_generator()
    for _ in range(steps_before):
        one_step(resumed, resumed_optimizer, resumed_scheduler, resumed_generator)
    saved_weights = {name: value.detach().cpu().clone() for name, value in resumed.state_dict().items()}
    sidecar = {
        "optimizer_state": resumed_optimizer.state_dict(),
        "scheduler_state": resumed_scheduler.state_dict(),
        "global_optimizer_step": steps_before,
        "phase": "cpu_resume_comparison",
        "python_rng": __import__("random").getstate(),
        "numpy_rng": None,
        "torch_cpu_rng": torch.get_rng_state(),
        "torch_cuda_rng": None,
        "diffusion_generator": resumed_generator.get_state(),
        "scaler_state": None,
        "ema_state": None,
        "configuration_identity": "cpu-fake-model",
        "implementation_identity": "cpu-fake-model",
    }
    if not sidecar["optimizer_state"]["state"]:
        raise contract.M5SmokeError("resume_proof_failed", "optimizer moments were not present before resume")
    restored = fresh_model()
    restored.load_state_dict(saved_weights)
    restored_optimizer, restored_scheduler = build(restored)
    restored_optimizer.load_state_dict(sidecar["optimizer_state"])
    restored_scheduler.load_state_dict(sidecar["scheduler_state"])
    restored_generator = data_generator()
    restored_generator.set_state(sidecar["diffusion_generator"])
    if restored_scheduler.get_last_lr() != resumed_scheduler.get_last_lr():
        raise contract.M5SmokeError("resume_proof_failed", "scheduler learning rate was not restored")
    for _ in range(steps_after):
        one_step(restored, restored_optimizer, restored_scheduler, restored_generator)
    weight_only = fresh_model()
    weight_only.load_state_dict(saved_weights)
    weight_only_optimizer, weight_only_scheduler = build(weight_only)
    weight_only_generator = data_generator()
    for _ in range(steps_after):
        one_step(weight_only, weight_only_optimizer, weight_only_scheduler, weight_only_generator)
    max_abs_delta = 0.0
    for name, value in uninterrupted.state_dict().items():
        delta = float((value.detach().cpu() - restored.state_dict()[name].detach().cpu()).abs().max())
        if delta > max_abs_delta:
            max_abs_delta = delta
    weight_only_delta = 0.0
    for name, value in uninterrupted.state_dict().items():
        delta = float((value.detach().cpu() - weight_only.state_dict()[name].detach().cpu()).abs().max())
        if delta > weight_only_delta:
            weight_only_delta = delta
    if not max_abs_delta <= float(tolerance):
        raise contract.M5SmokeError("resume_proof_failed", "resumed CPU model exceeded the tolerance")
    if not weight_only_delta > 0:
        raise contract.M5SmokeError("resume_proof_failed", "weight-only reload matched resume and was not distinguished")
    return {
        "tolerance": float(tolerance),
        "tolerance_justification": "identical float32 CPU ops and a restored dedicated generator",
        "max_abs_delta": max_abs_delta,
        "weight_only_reload_counted_as_resume": False,
        "weight_only_diverged": True,
        "optimizer_moments_present": True,
        "cuda_device_count": torch.cuda.device_count(),
    }


def observe_python_rng_restore(saved_state):
    """Restore the Python RNG with random.setstate and compare the next draw."""
    import random

    random.setstate(saved_state)
    expected = random.random()
    random.seed(909091)
    disturbed = random.random()
    if disturbed == expected:
        raise contract.M5SmokeError("resume_proof_failed", "Python RNG disturbance did not change the draw")
    random.setstate(saved_state)
    restored = random.random()
    random.setstate(saved_state)
    return {
        "setstate_called": True,
        "restored_with": "random.setstate",
        "disturbed_before_restore": True,
        "digest_before": contract.sha256_bytes(repr(float(expected)).encode("ascii")),
        "digest_after": contract.sha256_bytes(repr(float(restored)).encode("ascii")),
        "final_reset_after_verification": random.getstate() == saved_state,
    }


def observe_torch_cpu_rng_restore(torch, saved_state):
    saved = saved_state.clone()
    torch.set_rng_state(saved.clone())
    expected = torch.rand(1)
    torch.manual_seed(909091)
    disturbed = torch.rand(1)
    if bool(torch.equal(disturbed, expected)):
        raise contract.M5SmokeError("resume_proof_failed", "torch CPU RNG disturbance did not change the draw")
    torch.set_rng_state(saved.clone())
    restored = torch.rand(1)
    torch.set_rng_state(saved.clone())
    return {
        "setstate_called": True,
        "restored_with": "torch.set_rng_state",
        "disturbed_before_restore": True,
        "digest_before": _digest_tensor(expected),
        "digest_after": _digest_tensor(restored),
        "final_reset_after_verification": bool(torch.equal(torch.get_rng_state(), saved)),
    }


def observe_torch_cuda_rng_restore(torch, device, saved_state):
    saved = saved_state.clone()
    torch.cuda.set_rng_state(saved.clone(), device)
    expected = torch.rand(1, device=device)
    torch.cuda.manual_seed(909091)
    disturbed = torch.rand(1, device=device)
    if bool(torch.equal(disturbed, expected)):
        raise contract.M5SmokeError("resume_proof_failed", "torch CUDA RNG disturbance did not change the draw")
    torch.cuda.set_rng_state(saved.clone(), device)
    restored = torch.rand(1, device=device)
    torch.cuda.set_rng_state(saved.clone(), device)
    return {
        "setstate_called": True,
        "restored_with": "torch.cuda.set_rng_state",
        "disturbed_before_restore": True,
        "digest_before": _digest_tensor(expected),
        "digest_after": _digest_tensor(restored),
        "final_reset_after_verification": bool(torch.equal(torch.cuda.get_rng_state(device), saved)),
    }


def observe_generator_restore(torch, generator, saved_state):
    saved = saved_state.clone()
    generator.set_state(saved.clone())
    expected = torch.rand(1, generator=generator)
    generator.manual_seed(909091)
    disturbed = torch.rand(1, generator=generator)
    if bool(torch.equal(disturbed, expected)):
        raise contract.M5SmokeError("resume_proof_failed", "diffusion generator disturbance did not change the draw")
    generator.set_state(saved.clone())
    restored = torch.rand(1, generator=generator)
    generator.set_state(saved.clone())
    return {
        "setstate_called": True,
        "restored_with": "generator.set_state",
        "disturbed_before_restore": True,
        "digest_before": _digest_tensor(expected),
        "digest_after": _digest_tensor(restored),
        "final_reset_after_verification": bool(torch.equal(generator.get_state(), saved)),
    }


def _rng_block_matches(block):
    return (
        isinstance(block, dict)
        and block.get("setstate_called") is True
        and block.get("disturbed_before_restore") is True
        and block.get("final_reset_after_verification") is True
        and block.get("digest_before") == block.get("digest_after")
    )


def demonstrate_fresh_denoiser_resume():
    """CPU proof that resume loads a new module and continues from its optimizer state."""
    import random
    import torch

    if torch.cuda.is_available() or torch.cuda.device_count() != 0:
        raise contract.M5SmokeError("logical_device_rejected", "fresh resume demonstration saw a CUDA device")
    generator = torch.Generator(device="cpu")
    generator.manual_seed(17)
    initial_weight = torch.randn(1, 4, generator=generator)
    initial_bias = torch.randn(1, generator=generator)

    def fresh():
        model = torch.nn.Linear(4, 1, bias=True)
        with torch.no_grad():
            model.weight.copy_(initial_weight)
            model.bias.copy_(initial_bias)
        return model

    def one_step(model, optimizer, scheduler, data_generator):
        optimizer.zero_grad(set_to_none=True)
        inputs = torch.randn(8, 4, generator=data_generator)
        loss = (model(inputs) ** 2).mean()
        loss.backward()
        finite_loss = contract.assert_loss_finite(float(loss.detach()))
        finite_grad = bool(torch.isfinite(model.weight.grad).all().item())
        before = model.weight.detach().flatten()[:4].clone()
        optimizer.step()
        scheduler.step()
        after = model.weight.detach().flatten()[:4]
        delta = float((after - before).abs().max())
        return float(loss.detach()), finite_loss, finite_grad, delta

    original = fresh()
    data_generator = torch.Generator(device="cpu")
    data_generator.manual_seed(23)
    optimizer = torch.optim.Adam(original.parameters(), lr=1e-2)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=4)
    one_step(original, optimizer, scheduler, data_generator)
    saved_weights = {name: value.detach().cpu().clone() for name, value in original.state_dict().items()}
    saved_optimizer = optimizer.state_dict()
    saved_scheduler = scheduler.state_dict()
    completed_steps = 1
    python_state = random.getstate()
    cpu_state = torch.get_rng_state().clone()
    generator_state = data_generator.get_state()
    if not saved_optimizer["state"]:
        raise contract.M5SmokeError("resume_proof_failed", "optimizer moments were not present before reload")
    reloaded = fresh()
    reloaded.load_state_dict(saved_weights)
    if reloaded is original or id(reloaded) == id(original):
        raise contract.M5SmokeError("resume_proof_failed", "reloaded module is not a fresh object")
    comparisons = []
    for name, value in saved_weights.items():
        reloaded_value = reloaded.state_dict()[name].detach().cpu()
        saved_digest = _digest_tensor(value)
        reloaded_digest = _digest_tensor(reloaded_value)
        comparisons.append(
            {"name": name, "saved": saved_digest, "reloaded": reloaded_digest, "match": saved_digest == reloaded_digest}
        )
    restored_optimizer = torch.optim.Adam(reloaded.parameters(), lr=1e-2)
    restored_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(restored_optimizer, T_max=4)
    restored_optimizer.load_state_dict(saved_optimizer)
    restored_scheduler.load_state_dict(saved_scheduler)
    restored_epoch = int(restored_scheduler.state_dict()["last_epoch"])
    restored_lr = float(restored_scheduler.get_last_lr()[0])
    moment_count = sum(1 for slot in restored_optimizer.state_dict()["state"].values() if "exp_avg" in slot)
    optimizer_ids = [id(parameter) for group in restored_optimizer.param_groups for parameter in group["params"]]
    original_ids = [id(parameter) for parameter in original.parameters()]
    reloaded_ids = [id(parameter) for parameter in reloaded.parameters()]
    bound = (not set(optimizer_ids).isdisjoint(reloaded_ids)) and set(optimizer_ids).isdisjoint(original_ids)
    python_rng = observe_python_rng_restore(python_state)
    torch_cpu_rng = observe_torch_cpu_rng_restore(torch, cpu_state)
    diffusion_rng = observe_generator_restore(torch, data_generator, generator_state)
    loss_value, _finite_loss, finite_grad, delta = one_step(reloaded, restored_optimizer, restored_scheduler, data_generator)
    return {
        "fresh_object_identity": id(reloaded) != id(original),
        "original_denoiser_id": id(original),
        "reloaded_denoiser_id": id(reloaded),
        "weight_digest_comparisons": comparisons,
        "optimizer_bound_to_reloaded_denoiser": bound,
        "optimizer_parameter_ids": optimizer_ids,
        "original_parameter_ids": original_ids,
        "reloaded_parameter_ids": reloaded_ids,
        "optimizer_moment_count": moment_count,
        "optimizer_moments_present": moment_count > 0,
        "scheduler_last_epoch_saved": int(saved_scheduler["last_epoch"]),
        "scheduler_last_epoch_restored": restored_epoch,
        "learning_rate_saved": float(scheduler.get_last_lr()[0]),
        "learning_rate_restored_value": restored_lr,
        "global_step_saved": completed_steps,
        "global_step_reread": completed_steps,
        "python_rng": python_rng,
        "torch_cpu_rng": torch_cpu_rng,
        "diffusion_generator": diffusion_rng,
        "numpy_rng": {"status": "not_applicable", "randomness_used": False},
        "subsequent_loss": loss_value,
        "subsequent_gradients_finite": finite_grad,
        "subsequent_update_max_abs_delta": delta,
        "cuda_device_count": torch.cuda.device_count(),
    }


class RealSmokeBackend:
    """Authorized worker backend. Methods import torch only after the gate."""

    def __init__(self, plan, evidence_dir):
        self.plan = plan
        self.evidence_dir = evidence_dir
        self.worker_authorised = False

    def run_observed(self):
        if self.worker_authorised is not True:
            raise contract.M5SmokeError("worker_not_authorised", "heavy imports are closed")
        torch, trainer, pipeline_cls = _import_worker_stack()
        return _run_real_smoke(torch, trainer, pipeline_cls, self.plan, self.evidence_dir)


def _import_worker_stack():
    root = str(contract.RNAGENESIS_ROOT)
    encoder = os.path.join(root, "models", "autoencoder", "encoder")
    for path in (encoder, root):
        if path not in sys.path:
            sys.path.insert(0, path)
    os.chdir(root)
    import torch
    import train_diffusion_mres as trainer
    from models.diffusion_models.pipeline_ddim import GuidedDDIMPipeline1D

    if "generation" in sys.modules:
        raise contract.M5SmokeError("generation_proof_failed", "generation.py must not be imported")
    return torch, trainer, GuidedDDIMPipeline1D


def _digest_tensor(tensor):
    import hashlib

    array = tensor.detach().cpu().contiguous().numpy()
    return hashlib.sha256(array.tobytes()).hexdigest()


def _component_for(name):
    """Split EncDec parameters. The whole qt module is not the query-token table."""
    if name.startswith("encoder."):
        return "encoder"
    if ".query_embeddings." in name or name.endswith(".query_embeddings.weight"):
        return "query_tokens"
    if name.startswith("qt."):
        return "qformer"
    if name.startswith("transform."):
        return "latent_projection"
    if name.startswith("decoder."):
        return "decoder"
    return None


def _frozen_snapshot(torch, encdec, optimizer, baseline, rotary_names):
    del torch
    current = {}
    versions = {}
    for name, parameter in encdec.named_parameters():
        versions[name] = int(parameter._version)
        component = _component_for(name)
        if component is None or component in current:
            continue
        current[component] = _digest_tensor(parameter.detach().flatten()[:8])
    sentinel_ok = all(current.get(name) == baseline["sentinels"][name] for name in contract.FROZEN_SENTINEL_COMPONENTS)
    versions_ok = versions == baseline["versions"]
    gradients_absent = all(parameter.grad is None for _name, parameter in encdec.named_parameters())
    optimizer_ids = {id(parameter) for group in optimizer.param_groups for parameter in group["params"]}
    encdec_ids = {id(parameter) for parameter in encdec.parameters()}
    warmup_completed = baseline.get("warmup_completed") is True
    return {
        "eval_mode": encdec.training is False,
        "requires_grad_all_false": all(not parameter.requires_grad for parameter in encdec.parameters()),
        "optimizer_membership_empty": optimizer_ids.isdisjoint(encdec_ids),
        "parameter_gradients_absent": gradients_absent,
        "versions_unchanged": versions_ok,
        "sentinels_bit_identical": sentinel_ok,
        "rotary_warmup_completed": warmup_completed,
        "rotary_caches_excluded_from_sentinels": all(name not in current for name in rotary_names),
        "baseline_taken_after_warmup": warmup_completed,
        "sentinel_components": {name: baseline["sentinels"][name] for name in contract.FROZEN_SENTINEL_COMPONENTS},
        "rotary_cache_names": list(rotary_names),
    }


def _post_generation_frozen_snapshot(torch, encdec, membership_evidence, baseline, rotary_names):
    """Freeze the live EncDec and carry the AdamW identity observation. No new optimizer is built."""
    contract.assert_optimizer_membership_evidence(membership_evidence)
    current = {}
    versions = {}
    for name, parameter in encdec.named_parameters():
        versions[name] = int(parameter._version)
        component = _component_for(name)
        if component is None or component in current:
            continue
        current[component] = _digest_tensor(parameter.detach().flatten()[:8])
    sentinel_ok = all(current.get(name) == baseline["sentinels"][name] for name in contract.FROZEN_SENTINEL_COMPONENTS)
    versions_ok = versions == baseline["versions"]
    gradients_absent = all(parameter.grad is None for _name, parameter in encdec.named_parameters())
    warmup_completed = baseline.get("warmup_completed") is True
    return {
        "eval_mode": encdec.training is False,
        "requires_grad_all_false": all(not parameter.requires_grad for parameter in encdec.parameters()),
        "optimizer_membership_empty": membership_evidence["both_disjoint_from_every_encdec_parameter"] is True,
        "parameter_gradients_absent": gradients_absent,
        "versions_unchanged": versions_ok,
        "sentinels_bit_identical": sentinel_ok,
        "rotary_warmup_completed": warmup_completed,
        "rotary_caches_excluded_from_sentinels": all(name not in current for name in rotary_names),
        "baseline_taken_after_warmup": warmup_completed,
        "sentinel_components": {name: baseline["sentinels"][name] for name in contract.FROZEN_SENTINEL_COMPONENTS},
        "rotary_cache_names": list(rotary_names),
        "optimizer_membership_evidence_basis": membership_evidence["evidence_basis"],
        "optimizer_membership_evidence": membership_evidence,
    }


def observe_live_adamw_membership(encdec, named_optimizers):
    """Record parameter identities while both real AdamW optimizers are alive."""
    if not isinstance(named_optimizers, tuple) or len(named_optimizers) != 2:
        raise contract.M5SmokeError("frozen_component_failed", "membership evidence requires both live AdamW optimizers")
    encdec_ids = [id(parameter) for parameter in encdec.parameters()]
    rows = []
    for label, optimizer in named_optimizers:
        if type(optimizer).__name__ != "AdamW":
            raise contract.M5SmokeError("frozen_component_failed", "a fabricated replacement optimizer is not membership evidence")
        parameter_ids = [id(parameter) for group in optimizer.param_groups for parameter in group["params"]]
        disjoint = set(parameter_ids).isdisjoint(encdec_ids)
        rows.append(
            {
                "name": label,
                "optimizer_class": "AdamW",
                "parameter_ids": parameter_ids,
                "disjoint_from_encdec": disjoint,
            }
        )
    evidence = {
        "evidence_basis": contract.OPTIMIZER_MEMBERSHIP_EVIDENCE_BASIS,
        "replacement_optimizer_used": False,
        "encdec_parameter_ids": encdec_ids,
        "optimizers": rows,
        "both_disjoint_from_every_encdec_parameter": all(row["disjoint_from_encdec"] is True for row in rows),
    }
    contract.assert_optimizer_membership_evidence(evidence)
    return evidence


def _state_tensor(sidecar):
    state = sidecar["optimizer_state"]["state"]
    for slot in state.values():
        if isinstance(slot, dict) and hasattr(slot.get("exp_avg"), "detach"):
            return slot["exp_avg"]
    raise contract.M5SmokeError("resume_proof_failed", "optimizer state tensor was not available to observe release")


def observe_training_object_release(named_weakrefs):
    """Derive release from weak references. A live referent stays out of the released-name list."""
    if not isinstance(named_weakrefs, dict):
        raise contract.M5SmokeError("generation_proof_failed", "training release weak references are missing")
    referents = []
    for label in contract.TRAINING_RELEASE_LABELS:
        ref = named_weakrefs.get(label)
        if type(ref) is not weakref.ref:
            raise contract.M5SmokeError("generation_proof_failed", "training release is missing the weak reference " + label)
        referents.append({"label": label, "dead": ref() is None})
    return contract.derive_training_release(referents)


def _select_update_slice(torch, denoiser):
    for name, parameter in denoiser.named_parameters():
        if parameter.requires_grad is not True or parameter.grad is None:
            continue
        gradient = parameter.grad.detach()
        if torch.isfinite(gradient).all().item() is not True:
            continue
        flat_gradient = gradient.flatten()
        nonzero = torch.nonzero(flat_gradient, as_tuple=False).flatten()
        if nonzero.numel() == 0:
            continue
        start = int(nonzero[0].item())
        stop = min(start + 8, int(flat_gradient.numel()))
        indices = list(range(start, stop))
        values = parameter.detach().flatten()[indices].detach().cpu().contiguous().clone()
        return name, indices, values, int(parameter._version)
    raise contract.M5SmokeError("gradient_all_zero", "no finite non-zero trainable gradient was available for the update slice")


def _gradient_rows(torch, denoiser, encdec):
    encdec_ids = {id(parameter) for parameter in encdec.parameters()}
    rows = []
    for module, prefix in ((denoiser, "denoiser"), (encdec, "encdec")):
        for name, parameter in module.named_parameters():
            gradient = parameter.grad
            finite = True if gradient is None else bool(torch.isfinite(gradient).all().item())
            nonzero = False if gradient is None else bool(torch.count_nonzero(gradient).item() > 0)
            rows.append(
                {
                    "name": prefix + "." + name,
                    "trainable": bool(parameter.requires_grad),
                    "finite": finite,
                    "nonzero": nonzero,
                    "has_gradient": gradient is not None,
                    "encdec": id(parameter) in encdec_ids,
                }
            )
    return rows


def _inventory(root):
    import hashlib

    records = {}
    for directory, _dirs, files in os.walk(root):
        for name in sorted(files):
            path = os.path.join(directory, name)
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            relative = os.path.relpath(path, root)
            records[relative] = digest.hexdigest()
    return records


def inspect_starting_ema(diffusion_dir, walk):
    """List the accepted B1 diffusion files. This does not open weight bytes.

    The accepted inventory has no EMA artifact. An extra checkpoint or EMA
    member fails asset identity. Absence is not_applicable_absent and does
    not select an EMA policy.
    """
    observed = []
    for directory, _dirs, files in walk(diffusion_dir):
        for name in files:
            relative = os.path.relpath(os.path.join(directory, name), diffusion_dir).replace("\\", "/")
            observed.append(relative)
    expected = list(contract.B1_DIFFUSION_DIRECTORY_INVENTORY)
    if sorted(observed) != sorted(expected) or len(observed) != len(expected):
        raise contract.M5SmokeError("asset_identity_mismatch", "B1 diffusion directory inventory drifted")
    return {
        "inspected_directory": "configs/rnagenesis/diffusion",
        "exact_inspected_inventory": expected,
        "ema_artifact_present": False,
        "ema_compatibility": "not_applicable_absent",
        "selects_ema_policy": False,
    }


def _configuration_mapping(config):
    """Return a plain mapping for a denoiser config.

    A callable to_dict() is used when present. Otherwise a mapping, including
    Diffusers FrozenDict, is converted with dict(config). Unsupported objects,
    a non-mapping to_dict() result, and conversion failures fail closed.
    The returned mapping is a shallow copy and is not mutated.
    """
    from collections.abc import Mapping

    to_dict = getattr(config, "to_dict", None)
    if callable(to_dict):
        try:
            payload = to_dict()
        except contract.M5SmokeError:
            raise
        except Exception:
            raise contract.M5SmokeError("checkpoint_reload_mismatch", "denoiser configuration to_dict() failed") from None
        if not isinstance(payload, Mapping):
            raise contract.M5SmokeError(
                "checkpoint_reload_mismatch",
                "denoiser configuration to_dict() did not return a mapping",
            )
    elif isinstance(config, Mapping):
        try:
            payload = dict(config)
        except contract.M5SmokeError:
            raise
        except Exception:
            raise contract.M5SmokeError(
                "checkpoint_reload_mismatch",
                "denoiser configuration could not be converted with dict()",
            ) from None
        if not isinstance(payload, Mapping):
            raise contract.M5SmokeError(
                "checkpoint_reload_mismatch",
                "denoiser configuration conversion did not return a mapping",
            )
    else:
        raise contract.M5SmokeError(
            "checkpoint_reload_mismatch",
            "denoiser configuration is not a supported representation",
        )
    try:
        return dict(payload)
    except contract.M5SmokeError:
        raise
    except Exception:
        raise contract.M5SmokeError(
            "checkpoint_reload_mismatch",
            "denoiser configuration could not be converted with dict()",
        ) from None


def _hash_configuration_mapping(mapping):
    try:
        encoded = contract.canonical_json(mapping)
    except contract.M5SmokeError:
        raise
    except Exception:
        raise contract.M5SmokeError(
            "checkpoint_reload_mismatch",
            "denoiser configuration could not be serialized as canonical JSON",
        ) from None
    return contract.sha256_bytes(encoded)


def _config_sha256(config):
    """Hash a denoiser config as deterministic canonical JSON.

    This is the full raw digest. It keeps every field, including `_name_or_path`.
    """
    return _hash_configuration_mapping(_configuration_mapping(config))


def _allowlist_or_reject():
    allowlist = contract.CONFIGURATION_COMPATIBILITY_IGNORED_TOP_LEVEL_KEYS
    if allowlist != ("_name_or_path",):
        raise contract.M5SmokeError(
            "checkpoint_reload_mismatch",
            "configuration compatibility allowlist is not exactly ['_name_or_path']",
        )
    return allowlist


def _observed_ignored_values(mapping, allowlist):
    """Read allowlisted top-level values from the live mapping."""
    return {key: mapping[key] for key in allowlist if key in mapping}


def _normalized_configuration(mapping, allowlist):
    """Drop the allowlisted top-level keys. Nested mappings are not walked."""
    return {key: value for key, value in mapping.items() if key not in allowlist}


def observe_configuration_compatibility(original_config, reloaded_config):
    """Record raw configuration digests and top-level `_name_or_path` compatibility.

    Both raw digests use canonical JSON of the complete mappings. The
    normalized digests remove only the top-level key `_name_or_path`.
    `_class_name`, `_diffusers_version`, nested `_name_or_path`, and every
    other field remain in the normalized digest. Ignored values are read
    from the live mappings.
    """
    allowlist = _allowlist_or_reject()
    original = _configuration_mapping(original_config)
    reloaded = _configuration_mapping(reloaded_config)
    original_raw = _hash_configuration_mapping(original)
    reloaded_raw = _hash_configuration_mapping(reloaded)
    original_normalized = _normalized_configuration(original, allowlist)
    reloaded_normalized = _normalized_configuration(reloaded, allowlist)
    original_normalized_sha = _hash_configuration_mapping(original_normalized)
    reloaded_normalized_sha = _hash_configuration_mapping(reloaded_normalized)
    normalized_equal = original_normalized_sha == reloaded_normalized_sha
    compatibility = {
        "ignored_top_level_keys": list(allowlist),
        "original_ignored_values": _observed_ignored_values(original, allowlist),
        "reloaded_ignored_values": _observed_ignored_values(reloaded, allowlist),
        "original_normalized_config_sha256": original_normalized_sha,
        "reloaded_normalized_config_sha256": reloaded_normalized_sha,
        "normalized_config_sha256_equal": normalized_equal,
    }
    if tuple(compatibility) != contract.CONFIGURATION_COMPATIBILITY_FIELD_ORDER:
        raise contract.M5SmokeError("checkpoint_reload_mismatch", "configuration compatibility field order drifted")
    return {
        "original_config_sha256": original_raw,
        "reloaded_config_sha256": reloaded_raw,
        "raw_config_sha256_equal": original_raw == reloaded_raw,
        "configuration_compatibility": compatibility,
        "configuration_compatible": normalized_equal,
    }


def build_checkpoint_reload_proof(
    saved_file_hashes,
    fresh_load_succeeded,
    original_denoiser_id,
    reloaded_denoiser_id,
    tensor_digest_comparisons,
    configuration,
):
    """Assemble checkpoint reload evidence in the documented field order."""
    proof = {
        "saved_file_hashes": saved_file_hashes,
        "fresh_load_succeeded": fresh_load_succeeded,
        "original_denoiser_id": original_denoiser_id,
        "reloaded_denoiser_id": reloaded_denoiser_id,
        "tensor_digest_comparisons": tensor_digest_comparisons,
        "original_config_sha256": configuration["original_config_sha256"],
        "reloaded_config_sha256": configuration["reloaded_config_sha256"],
        "raw_config_sha256_equal": configuration["raw_config_sha256_equal"],
        "configuration_compatibility": configuration["configuration_compatibility"],
        "configuration_compatible": configuration["configuration_compatible"],
    }
    if tuple(proof) != contract.CHECKPOINT_RELOAD_FIELD_ORDER:
        raise contract.M5SmokeError("checkpoint_reload_mismatch", "checkpoint reload field order drifted")
    return proof


def _sha256_path(path):
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_runtime(torch):
    import platform

    import accelerate
    import diffusers
    import transformers

    runtime = {
        "python": platform.python_version(),
        "executable": sys.executable,
        "torch": torch.__version__,
        "diffusers": diffusers.__version__,
        "accelerate": accelerate.__version__,
        "transformers": transformers.__version__,
    }
    contract.assert_package_runtime(runtime)
    return runtime


def run_scaled_accumulation(forward_loss, microbatch, accumulation, record_count):
    """Run four scaled backwards on the same records. The caller performs the optimizer step."""
    if microbatch != contract.PHYSICAL_MICROBATCH_CANDIDATE or accumulation != contract.ACCUMULATION_MICROSTEPS:
        raise contract.M5SmokeError("physical_microbatch_candidate_failed", "refusing a microbatch other than 8 or an accumulation other than 4")
    if record_count != contract.PHYSICAL_MICROBATCH_CANDIDATE or microbatch * accumulation != contract.INTENDED_EFFECTIVE_BATCH:
        raise contract.M5SmokeError("microbatch_mismatch", "effective batch is not microbatch 8 times accumulation 4")
    losses = []
    for _step_index in range(accumulation):
        loss = forward_loss()
        (loss / float(accumulation)).backward()
        losses.append(loss)
    return losses


def observe_bf16_diagnostic(autocast_supported, fp32_loss, bf16_value, memory_observation):
    """Pair one BF16 forward with the FP32 forward. Do not choose a production precision."""
    record = {
        "status": "observed",
        "autocast_supported": autocast_supported is True,
        "same_fixed_latent": True,
        "same_fixed_timestep": True,
        "same_fixed_noise": True,
        "fp32_loss": fp32_loss,
        "selects_production_precision": False,
        "pass_tolerance": None,
        "production_precision_selected": None,
        "memory_observation": memory_observation,
    }
    if autocast_supported is not True:
        record["result_finite"] = None
        record["bf16_loss"] = None
        record["absolute_difference"] = None
        record["relative_difference"] = None
    elif isinstance(bf16_value, bool) or not isinstance(bf16_value, (int, float)) or bf16_value != bf16_value or bf16_value in (float("inf"), float("-inf")):
        record["result_finite"] = False
        record["bf16_loss"] = None
        record["absolute_difference"] = None
        record["relative_difference"] = None
    else:
        absolute = abs(float(fp32_loss) - float(bf16_value))
        relative = None if float(fp32_loss) == 0.0 else absolute / abs(float(fp32_loss))
        record["result_finite"] = True
        record["bf16_loss"] = float(bf16_value)
        record["absolute_difference"] = absolute
        record["relative_difference"] = relative
    contract.assert_bf16_observation(record)
    return record


def run_bf16_diagnostic(autocast_supported, forward, fp32_loss):
    """Record an unsupported device, a returned loss, or fail closed on an exception.

    A raised forward is not rewritten as a non-finite BF16 result.
    """
    if autocast_supported is not True:
        return observe_bf16_diagnostic(False, fp32_loss, None, None)
    try:
        bf16_value, memory_observation = forward()
    except contract.M5SmokeError:
        raise
    except Exception as exc:
        raise contract.M5SmokeError("bf16_forward_failed", "BF16 forward raised " + type(exc).__name__)
    return observe_bf16_diagnostic(True, fp32_loss, bf16_value, memory_observation)


def _phase_records(measured_microbatch, measured_accumulation, measured_effective, fp32_loss, bf16_observation, accumulation_proof):
    feasibility = {
        "status": "observed",
        "candidate_microbatch": contract.PHYSICAL_MICROBATCH_CANDIDATE,
        "attempted_microbatches": [contract.PHYSICAL_MICROBATCH_CANDIDATE],
        "fallback_attempted": False,
        "sweep": False,
        "fail_closed": True,
        "succeeded": measured_microbatch == contract.PHYSICAL_MICROBATCH_CANDIDATE and measured_accumulation == contract.ACCUMULATION_MICROSTEPS,
        "measured_physical_microbatch": measured_microbatch,
        "derived_accumulation": measured_accumulation,
        "intended_effective_batch": contract.INTENDED_EFFECTIVE_BATCH,
    }
    contract.assert_physical_microbatch_candidate(feasibility)
    contract.assert_accumulation_exercise(accumulation_proof)
    accumulation = dict(accumulation_proof)
    accumulation["status"] = "observed"
    return {
        "correctness": {
            "status": "observed",
            "microbatch": measured_microbatch,
            "accumulation": measured_accumulation,
            "effective_batch": measured_effective,
            "precision": "float32",
        },
        "physical_microbatch_feasibility": feasibility,
        "gradient_accumulation": accumulation,
        "fp32_observation": {
            "status": "observed",
            "precision": "float32",
            "loss": fp32_loss,
            "selects_production_precision": False,
        },
        "bf16_numerical_observation": bf16_observation,
        "generation_weight_state": {"raw": "used", "ema": "not_used"},
    }


def _run_real_smoke(torch, trainer, pipeline_cls, plan, evidence_dir):
    evidence = _collect_training_evidence(torch, trainer, pipeline_cls, plan, evidence_dir)
    gc.collect()
    gc.collect()
    torch.cuda.empty_cache()
    release_weakrefs = evidence.pop("release_weakrefs")
    release = observe_training_object_release(release_weakrefs)
    del release_weakrefs
    if release["training_objects_released_before_generation_reload"] is not True:
        raise contract.M5SmokeError(
            "generation_proof_failed",
            "training objects were still live before generation reload: " + ", ".join(release["live_training_object_names"]),
        )
    return _generate_from_released_checkpoint(torch, pipeline_cls, plan, evidence_dir, evidence, release)


def _collect_training_evidence(torch, trainer, pipeline_cls, plan, evidence_dir):
    """Train, checkpoint, resume, and overfit without returning a GPU training object.

    The frozen EncDec is the only module returned. Weak references are taken
    while the training objects are live. The caller collects garbage and
    empties the CUDA cache before reading them.
    """
    smoke = plan["smoke_only"]
    runtime = _package_runtime(torch)
    device = torch.device(contract.LOGICAL_DEVICE)
    torch.cuda.reset_peak_memory_stats(device)
    timings = {}
    started = time.perf_counter()
    fixture_sequences = trainer.read_train_sequences(contract.FIXTURE_PATH, enforce_frozen_hash=False)
    if len(fixture_sequences) != int(smoke["fixture_record_count"]):
        raise contract.M5SmokeError("fixture_rejected", "fixture record count drifted from the smoke plan")
    requested_microbatch = int(smoke["smoke_microbatch"])
    requested_accumulation = int(smoke["smoke_gradient_accumulation"])
    if requested_microbatch != contract.PHYSICAL_MICROBATCH_CANDIDATE or requested_accumulation != contract.ACCUMULATION_MICROSTEPS:
        raise contract.M5SmokeError("physical_microbatch_candidate_failed", "refusing a microbatch other than 8 or an accumulation other than 4")
    if len(fixture_sequences) != requested_microbatch:
        raise contract.M5SmokeError("microbatch_mismatch", "fixture record count is not the microbatch-8 candidate")
    tokenizer = trainer.load_tokenizer()
    dataset = trainer.SequenceIndexDataset(fixture_sequences)
    batch = trainer.collate_sequences([dataset[index] for index in range(requested_microbatch)], tokenizer)
    measured_microbatch = int(batch["input_ids"].shape[0])
    if measured_microbatch != requested_microbatch:
        raise contract.M5SmokeError("microbatch_mismatch", "collated batch does not equal the requested microbatch")
    starting_ema = inspect_starting_ema(str(trainer.B1_DIFFUSION_DIR), os.walk)
    encdec = trainer.load_frozen_encdec(trainer.ENCDEC_DIR)
    denoiser = trainer.load_b1_denoiser(trainer.B1_DIFFUSION_DIR)
    ddim = trainer.load_scheduler(trainer.B1_DIFFUSION_DIR)
    encdec.to(device)
    denoiser.to(device)
    input_ids = batch["input_ids"].to(device)
    attention_mask = batch["attention_mask"].to(device)
    latent = trainer.extract_latents(encdec, input_ids, attention_mask)
    fixed_latent = latent.detach().clone()
    rotary_names = []
    for module_name, module in encdec.named_modules():
        if all(hasattr(module, attribute) for attribute in contract.ROTARY_CACHE_ATTRIBUTES):
            rotary_names.append(module_name)
    sentinels = {}
    versions = {}
    for name, parameter in encdec.named_parameters():
        versions[name] = int(parameter._version)
        component = _component_for(name)
        if component is not None and component not in sentinels:
            sentinels[component] = _digest_tensor(parameter.detach().flatten()[:8])
    missing_sentinels = [name for name in contract.FROZEN_SENTINEL_COMPONENTS if name not in sentinels]
    if missing_sentinels:
        raise contract.M5SmokeError("frozen_component_failed", "frozen baseline is missing " + missing_sentinels[0])
    baseline = {"sentinels": sentinels, "versions": versions, "warmup_completed": True}
    generator = torch.Generator(device="cpu")
    generator.manual_seed(int(smoke["overfit_noise_seed"]))
    fixed_noise = torch.randn(fixed_latent.shape, generator=generator, dtype=torch.float32).to(device)
    if int(smoke["overfit_fixed_timestep"]) >= int(ddim.config.num_train_timesteps):
        raise contract.M5SmokeError("smoke_settings_invalid", "fixed timestep is outside the scheduler range")
    fixed_timesteps = torch.full((fixed_latent.shape[0],), int(smoke["overfit_fixed_timestep"]), dtype=torch.long, device=device)
    learning_rate = float(smoke["learning_rate"])
    optimizer = trainer.build_adamw(denoiser, learning_rate)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=int(smoke["overfit_optimizer_updates"]) + 2,
    )
    trainer.assert_optimizer_membership(optimizer, denoiser, encdec)
    step_started = time.perf_counter()
    optimizer.zero_grad(set_to_none=True)

    def _forward_reused_microbatch():
        return trainer.denoising_mse(denoiser, ddim, fixed_latent, fixed_noise, fixed_timesteps)

    try:
        microstep_losses = run_scaled_accumulation(
            _forward_reused_microbatch,
            measured_microbatch,
            requested_accumulation,
            len(fixture_sequences),
        )
    except contract.M5SmokeError:
        raise
    except Exception as exc:
        out_of_memory = type(exc).__name__ == "OutOfMemoryError" or (
            isinstance(exc, RuntimeError) and "out of memory" in str(exc).lower()
        )
        if out_of_memory:
            raise contract.M5SmokeError(
                "physical_microbatch_candidate_failed",
                "microbatch 8 failed; evidence is preserved and 16 or 32 is not attempted",
            )
        raise
    proof_backward_count = len(microstep_losses)
    loss_value = sum(float(item.detach().cpu()) for item in microstep_losses) / float(proof_backward_count)
    timings["proof_forward_backward_seconds"] = time.perf_counter() - step_started
    gradient_rows = _gradient_rows(torch, denoiser, encdec)
    gradient_square = 0.0
    for parameter in denoiser.parameters():
        if parameter.requires_grad and parameter.grad is not None:
            gradient_square += float(parameter.grad.detach().float().pow(2).sum().cpu())
    gradient_norm = gradient_square ** 0.5
    contract.assert_loss_finite(loss_value)
    contract.assert_gradient_summaries(gradient_rows)
    parameter_name, indices, before_values, version_before = _select_update_slice(torch, denoiser)
    frozen_after_backward = _frozen_snapshot(torch, encdec, optimizer, baseline, rotary_names)
    contract.assert_frozen_snapshot(frozen_after_backward)
    torch.nn.utils.clip_grad_norm_(denoiser.parameters(), trainer.GRADIENT_CLIP_NORM)
    optimizer.step()
    scheduler.step()
    proof_optimizer_steps = 1
    if proof_backward_count != requested_accumulation or proof_optimizer_steps != 1:
        raise contract.M5SmokeError("microbatch_mismatch", "proof step did not consume four backward microsteps and one optimizer update")
    moment_count_after_step = sum(
        1 for slot in optimizer.state_dict()["state"].values() if isinstance(slot, dict) and "exp_avg" in slot
    )
    if moment_count_after_step < 1:
        raise contract.M5SmokeError("microbatch_mismatch", "AdamW moments were not allocated before the training-memory measurement")
    training_allocated_bytes = int(torch.cuda.max_memory_allocated(device))
    training_reserved_bytes = int(torch.cuda.max_memory_reserved(device))
    measured_accumulation = proof_backward_count // proof_optimizer_steps
    measured_effective = measured_microbatch * measured_accumulation
    requested_effective = requested_microbatch * requested_accumulation
    if measured_effective != requested_effective or measured_effective != int(smoke["smoke_effective_batch"]):
        raise contract.M5SmokeError("microbatch_mismatch", "measured effective batch does not equal the smoke plan")
    parameter = dict(denoiser.named_parameters())[parameter_name]
    after_values = parameter.detach().flatten()[indices].detach().cpu().contiguous()
    max_abs_delta = float((after_values - before_values).abs().max())
    update = {
        "parameter_name": parameter_name,
        "indices": indices,
        "before_digest": _digest_tensor(before_values),
        "after_digest": _digest_tensor(after_values),
        "max_abs_delta": max_abs_delta,
        "passed": max_abs_delta > 0,
        "used_version_as_sole_proof": False,
        "version_before": version_before,
        "version_after": int(parameter._version),
    }
    frozen_after_update = _frozen_snapshot(torch, encdec, optimizer, baseline, rotary_names)
    with torch.no_grad():
        fp32_paired = trainer.denoising_mse(denoiser, ddim, fixed_latent, fixed_noise, fixed_timesteps)
    fp32_paired_loss = float(fp32_paired.detach().cpu())
    contract.assert_loss_finite(fp32_paired_loss)
    bf16_supported = bool(torch.cuda.is_bf16_supported())

    def _bf16_forward():
        allocated_before = int(torch.cuda.memory_allocated(device))
        with torch.no_grad():
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                bf16_tensor = trainer.denoising_mse(denoiser, ddim, fixed_latent, fixed_noise, fixed_timesteps)
        value = float(bf16_tensor.detach().float().cpu())
        memory = {
            "allocated_bytes": int(torch.cuda.memory_allocated(device)),
            "reserved_bytes": int(torch.cuda.memory_reserved(device)),
            "allocated_delta_bytes": int(torch.cuda.memory_allocated(device)) - allocated_before,
        }
        return value, memory

    bf16_observation = run_bf16_diagnostic(bf16_supported, _bf16_forward, fp32_paired_loss)
    accumulation_proof = {
        "backward_microsteps": proof_backward_count,
        "optimizer_updates_in_window": proof_optimizer_steps,
        "loss_scale": contract.LOSS_SCALE_NAME,
        "deterministic_record_reuse": True,
        "reused_records": len(fixture_sequences),
        "effective_batch": measured_microbatch * proof_backward_count,
        "adamw_moments_allocated_before_training_memory_measurement": True,
    }
    saved_separation_name = parameter_name
    saved_separation_digest = _digest_tensor(dict(denoiser.named_parameters())[saved_separation_name].detach())
    checkpoint_dir = os.path.join(evidence_dir, "smoke_generation_checkpoint")
    _mkdir(checkpoint_dir)
    saved_pipeline = trainer.DDIMPipeline1D(unet=denoiser, scheduler=ddim)
    saved_pipeline.save_pretrained(checkpoint_dir, safe_serialization=True)
    saved_inventory = _inventory(checkpoint_dir)
    contract.assert_checkpoint_members(saved_inventory)
    completed_steps = proof_optimizer_steps
    sidecar = {
        "optimizer_state": optimizer.state_dict(),
        "scheduler_state": scheduler.state_dict(),
        "global_optimizer_step": completed_steps,
        "phase": "after_proof_update",
        "python_rng": __import__("random").getstate(),
        "numpy_rng": {"status": "not_applicable", "randomness_used": False},
        "torch_cpu_rng": torch.get_rng_state(),
        "torch_cuda_rng": torch.cuda.get_rng_state(device),
        "diffusion_generator": generator.get_state(),
        "scaler_state": None,
        "ema_state": None,
        "configuration_identity": plan["config_sha256"],
        "implementation_identity": plan["authorisation"]["implementation_contract_sha256"],
    }
    sidecar_path = os.path.join(evidence_dir, "resume_sidecar.pt")
    descriptor = os.open(sidecar_path + contract.PARTIAL_SUFFIX, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            torch.save(sidecar, handle)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        raise
    os.link(sidecar_path + contract.PARTIAL_SUFFIX, sidecar_path)
    os.unlink(sidecar_path + contract.PARTIAL_SUFFIX)
    sidecar_sha256 = _sha256_path(sidecar_path)
    loaded_sidecar = torch.load(sidecar_path)
    observed_sidecar_keys = list(loaded_sidecar.keys())
    reloaded = pipeline_cls.from_pretrained(
        checkpoint_dir,
        classifier_model_config=None,
        loss_type="l2",
        encdec=encdec,
        guidance_scale=1.0,
    )
    fresh = reloaded.unet
    fresh.to(device)
    fresh_load_succeeded = fresh is not None and fresh is reloaded.unet and id(fresh) != id(denoiser)
    if fresh_load_succeeded is not True:
        raise contract.M5SmokeError("checkpoint_reload_mismatch", "fresh denoiser was not loaded from the smoke checkpoint")
    selected_names = [name for name, _parameter in denoiser.named_parameters()][:3]
    if not selected_names:
        raise contract.M5SmokeError("checkpoint_reload_mismatch", "saved denoiser has no parameters to compare")
    fresh_parameters = dict(fresh.named_parameters())
    original_parameters = dict(denoiser.named_parameters())
    tensor_comparisons = []
    for name in selected_names:
        saved_digest = _digest_tensor(original_parameters[name])
        reloaded_digest = _digest_tensor(fresh_parameters[name])
        tensor_comparisons.append(
            {"name": name, "saved": saved_digest, "reloaded": reloaded_digest, "match": saved_digest == reloaded_digest}
        )
    configuration = observe_configuration_compatibility(denoiser.config, fresh.config)
    configuration_compatible = configuration["configuration_compatible"]
    restored_optimizer = trainer.build_adamw(fresh, learning_rate)
    restored_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        restored_optimizer,
        T_max=int(smoke["overfit_optimizer_updates"]) + 2,
    )
    restored_optimizer.load_state_dict(loaded_sidecar["optimizer_state"])
    restored_scheduler.load_state_dict(loaded_sidecar["scheduler_state"])
    saved_epoch = int(scheduler.state_dict()["last_epoch"])
    restored_epoch = int(restored_scheduler.state_dict()["last_epoch"])
    saved_lr = float(scheduler.get_last_lr()[0])
    restored_lr = float(restored_scheduler.get_last_lr()[0])
    scheduler_position_restored = saved_epoch == restored_epoch
    learning_rate_restored = saved_lr == restored_lr
    reread_step = int(loaded_sidecar["global_optimizer_step"])
    restored_step = reread_step
    next_update_index = restored_step + 1
    global_step_restored = reread_step == completed_steps and restored_step == reread_step and next_update_index == reread_step + 1
    original_parameter_ids = [id(parameter) for parameter in denoiser.parameters()]
    reloaded_parameter_ids = [id(parameter) for parameter in fresh.parameters()]
    optimizer_parameter_ids = [id(parameter) for group in restored_optimizer.param_groups for parameter in group["params"]]
    optimizer_bound = (not set(optimizer_parameter_ids).isdisjoint(reloaded_parameter_ids)) and set(optimizer_parameter_ids).isdisjoint(original_parameter_ids)
    moment_count = sum(1 for slot in restored_optimizer.state_dict()["state"].values() if isinstance(slot, dict) and "exp_avg" in slot)
    membership_evidence = observe_live_adamw_membership(
        encdec,
        (("proof_optimizer", optimizer), ("restored_optimizer", restored_optimizer)),
    )
    python_rng = observe_python_rng_restore(loaded_sidecar["python_rng"])
    torch_cpu_rng = observe_torch_cpu_rng_restore(torch, loaded_sidecar["torch_cpu_rng"])
    torch_cuda_rng = observe_torch_cuda_rng_restore(torch, device, loaded_sidecar["torch_cuda_rng"])
    diffusion_rng = observe_generator_restore(torch, generator, loaded_sidecar["diffusion_generator"])
    numpy_rng = loaded_sidecar["numpy_rng"]
    rng_restored = _rng_block_matches(python_rng) and _rng_block_matches(torch_cpu_rng) and _rng_block_matches(torch_cuda_rng) and _rng_block_matches(diffusion_rng)
    restored_optimizer.zero_grad(set_to_none=True)
    resume_loss = trainer.denoising_mse(fresh, ddim, fixed_latent, fixed_noise, fixed_timesteps)
    resume_loss_value = float(resume_loss.detach().cpu())
    resume_loss_finite = resume_loss_value == resume_loss_value and resume_loss_value != float("inf") and resume_loss_value != float("-inf")
    resume_loss.backward()
    resume_gradients_finite = all(
        parameter.grad is None or bool(torch.isfinite(parameter.grad).all().item())
        for parameter in fresh.parameters()
        if parameter.requires_grad
    )
    resume_name, resume_indices, resume_before, _resume_version = _select_update_slice(torch, fresh)
    restored_optimizer.step()
    restored_scheduler.step()
    resume_parameter = dict(fresh.named_parameters())[resume_name]
    resume_after = resume_parameter.detach().flatten()[resume_indices].detach().cpu().contiguous()
    resume_delta = float((resume_after - resume_before).abs().max())
    weights_reloaded = fresh_load_succeeded and configuration_compatible and all(row["match"] is True for row in tensor_comparisons)
    resume = {
        "original_denoiser_id": id(denoiser),
        "reloaded_denoiser_id": id(fresh),
        "fresh_object_identity": id(fresh) != id(denoiser),
        "weight_digest_comparisons": tensor_comparisons,
        "optimizer_parameter_ids": optimizer_parameter_ids,
        "original_parameter_ids": original_parameter_ids,
        "reloaded_parameter_ids": reloaded_parameter_ids,
        "optimizer_bound_to_reloaded_denoiser": optimizer_bound,
        "optimizer_moment_count": moment_count,
        "optimizer_moments_present": moment_count > 0,
        "scheduler_last_epoch_saved": saved_epoch,
        "scheduler_last_epoch_restored": restored_epoch,
        "scheduler_position_restored": scheduler_position_restored,
        "learning_rate_saved": saved_lr,
        "learning_rate_restored_value": restored_lr,
        "learning_rate_restored": learning_rate_restored,
        "global_step_saved": completed_steps,
        "global_step_reread": reread_step,
        "global_step_after_restore": restored_step,
        "next_update_index": next_update_index,
        "restored_global_step_is_next_step": global_step_restored,
        "python_rng": python_rng,
        "torch_cpu_rng": torch_cpu_rng,
        "torch_cuda_rng": torch_cuda_rng,
        "diffusion_generator": diffusion_rng,
        "numpy_rng": numpy_rng,
        "rng_restored": rng_restored,
        "subsequent_loss": resume_loss_value,
        "subsequent_loss_finite": resume_loss_finite,
        "subsequent_gradients_finite": resume_gradients_finite,
        "subsequent_parameter_name": resume_name,
        "subsequent_update_max_abs_delta": resume_delta,
        "subsequent_update_succeeded": resume_loss_finite and resume_gradients_finite and resume_delta > 0,
        "weights_reloaded": weights_reloaded,
        "resumed_checkpoint_generation_compatible": fresh is reloaded.unet,
        "generation_used_mutated_training_object": False,
        "weight_only_reload_counted_as_resume": False,
        "observed_sidecar_keys": observed_sidecar_keys,
        "sidecar_fields": list(observed_sidecar_keys),
        "sidecar_fields_source": "reread_sidecar_keys",
    }
    checkpoint_proof = build_checkpoint_reload_proof(
        saved_inventory,
        fresh_load_succeeded,
        id(denoiser),
        id(fresh),
        tensor_comparisons,
        configuration,
    )

    def measured_loss():
        with torch.no_grad():
            value = trainer.denoising_mse(fresh, ddim, fixed_latent, fixed_noise, fixed_timesteps)
        return float(value.detach().cpu())

    losses = [measured_loss()]
    overfit_started = time.perf_counter()
    for _ in range(int(smoke["overfit_optimizer_updates"])):
        restored_optimizer.zero_grad(set_to_none=True)
        step_loss = trainer.denoising_mse(fresh, ddim, fixed_latent, fixed_noise, fixed_timesteps)
        step_loss.backward()
        restored_optimizer.step()
        restored_scheduler.step()
        losses.append(measured_loss())
    timings["overfit_seconds"] = time.perf_counter() - overfit_started
    mutated_training_object_id = id(fresh)
    mutated_training_digest = _digest_tensor(fresh_parameters[saved_separation_name].detach())
    if mutated_training_digest == saved_separation_digest:
        raise contract.M5SmokeError("generation_proof_failed", "resume and overfit did not mutate the training denoiser")
    shapes = {
        "input_ids_dtype": "int64",
        "attention_mask_dtype": "bool",
        "input_ids_shape": list(input_ids.shape),
        "attention_mask_shape": list(attention_mask.shape),
        "latent_shape": list(fixed_latent.shape),
        "latent_dtype": "float32",
        "noise_shape": list(fixed_noise.shape),
        "noise_dtype": "float32",
        "timestep_shape": list(fixed_timesteps.shape),
        "timestep_dtype": "int64",
        "loss_shape": [],
        "loss_dtype": "float32",
    }
    release_weakrefs = {
        "original_denoiser": weakref.ref(denoiser),
        "resumed_denoiser": weakref.ref(fresh),
        "representative_original_parameter": weakref.ref(original_parameters[saved_separation_name]),
        "representative_resumed_parameter": weakref.ref(fresh_parameters[saved_separation_name]),
        "proof_optimizer": weakref.ref(optimizer),
        "restored_optimizer": weakref.ref(restored_optimizer),
        "proof_scheduler": weakref.ref(scheduler),
        "restored_scheduler": weakref.ref(restored_scheduler),
        "saved_pipeline": weakref.ref(saved_pipeline),
        "resumed_pipeline": weakref.ref(reloaded),
        "in_memory_sidecar_tensor": weakref.ref(_state_tensor(sidecar)),
        "loaded_sidecar_tensor": weakref.ref(_state_tensor(loaded_sidecar)),
        "resume_loss": weakref.ref(resume_loss),
        "step_loss": weakref.ref(step_loss),
        "microstep_loss": weakref.ref(microstep_losses[0]),
        "fp32_loss_tensor": weakref.ref(fp32_paired),
        "fixed_latent": weakref.ref(fixed_latent),
        "fixed_noise": weakref.ref(fixed_noise),
        "fixed_timesteps": weakref.ref(fixed_timesteps),
        "batch_input_ids": weakref.ref(input_ids),
    }
    evidence = {
        "encdec": encdec,
        "baseline": baseline,
        "rotary_names": rotary_names,
        "runtime": runtime,
        "timings": timings,
        "started": started,
        "starting_ema": starting_ema,
        "measured_microbatch": measured_microbatch,
        "requested_microbatch": requested_microbatch,
        "requested_accumulation": requested_accumulation,
        "measured_accumulation": measured_accumulation,
        "measured_effective": measured_effective,
        "requested_effective": requested_effective,
        "loss_value": loss_value,
        "gradient_rows": gradient_rows,
        "gradient_norm": gradient_norm,
        "update": update,
        "frozen_after_backward": frozen_after_backward,
        "frozen_after_update": frozen_after_update,
        "fp32_paired_loss": fp32_paired_loss,
        "bf16_observation": bf16_observation,
        "accumulation_proof": accumulation_proof,
        "saved_separation_name": saved_separation_name,
        "saved_separation_digest": saved_separation_digest,
        "checkpoint_dir": checkpoint_dir,
        "saved_inventory": saved_inventory,
        "sidecar_sha256": sidecar_sha256,
        "resume": resume,
        "checkpoint_proof": checkpoint_proof,
        "losses": losses,
        "mutated_training_object_id": mutated_training_object_id,
        "mutated_training_digest": mutated_training_digest,
        "membership_evidence": membership_evidence,
        "shapes": shapes,
        "moment_count_after_step": moment_count_after_step,
        "training_allocated_bytes": training_allocated_bytes,
        "training_reserved_bytes": training_reserved_bytes,
        "release_weakrefs": release_weakrefs,
    }
    del measured_loss, _bf16_forward
    del original_parameters, fresh_parameters, sidecar, loaded_sidecar
    del resume_loss, resume_parameter, resume_before, resume_after, step_loss
    del microstep_losses, fp32_paired, before_values, after_values, parameter
    del denoiser, fresh, optimizer, restored_optimizer, scheduler, restored_scheduler
    del saved_pipeline, reloaded, ddim, generator
    del fixed_latent, fixed_noise, fixed_timesteps, input_ids, attention_mask, latent, batch
    return evidence


def _generate_from_released_checkpoint(torch, pipeline_cls, plan, evidence_dir, evidence, release):
    """Load generation only after the training scope has returned and its weak references are dead."""
    smoke = plan["smoke_only"]
    device = torch.device(contract.LOGICAL_DEVICE)
    encdec = evidence["encdec"]
    checkpoint_dir = evidence["checkpoint_dir"]
    saved_inventory = evidence["saved_inventory"]
    saved_separation_name = evidence["saved_separation_name"]
    saved_separation_digest = evidence["saved_separation_digest"]
    mutated_training_digest = evidence["mutated_training_digest"]
    mutated_training_object_id = evidence["mutated_training_object_id"]
    timings = evidence["timings"]
    resume = evidence["resume"]
    generation_inventory = _inventory(checkpoint_dir)
    if generation_inventory != saved_inventory:
        raise contract.M5SmokeError("generation_proof_failed", "on-disk checkpoint hashes changed before generation reload")
    generation_pipeline = pipeline_cls.from_pretrained(
        checkpoint_dir,
        classifier_model_config=None,
        loss_type="l2",
        encdec=encdec,
        guidance_scale=1.0,
    )
    generation_unet = generation_pipeline.unet
    generation_unet.to(device)
    generation_digest = _digest_tensor(dict(generation_unet.named_parameters())[saved_separation_name].detach())
    generation_started = time.perf_counter()
    generation_generator = torch.Generator(device=device)
    generation_generator.manual_seed(int(smoke["smoke_generation_seed"]))
    with torch.no_grad():
        generated_latent = generation_pipeline(
            batch_size=int(smoke["generation_count"]),
            generator=generation_generator,
            eta=float(smoke["generation_eta"]),
            num_inference_steps=int(smoke["generation_ddim_steps"]),
            num_query_tokens=encdec.config.num_query_tokens,
            guidance=False,
            target_class=0,
            update_seq=False,
            verbose=False,
            max_seq_len=int(smoke["smoke_max_seq_len"]),
            do_sample=False,
            top_k=50,
            top_p=1.0,
            eos_token="<|eos|>",
            bos_token="<|bos|>",
            truncate=False,
            extend_input=False,
            multiple_eos_tokens=False,
        )
        _logits, sequences = encdec.generate(
            generated_latent,
            max_seq_len=int(smoke["smoke_max_seq_len"]),
            do_sample=False,
            truncate=False,
            extend_input=False,
            multiple_eos_tokens=False,
        )
    timings["generation_seconds"] = time.perf_counter() - generation_started
    generation_proof = {
        "reloaded": True,
        "count": int(smoke["generation_count"]),
        "loader": "GuidedDDIMPipeline1D.from_pretrained",
        "imported_generation_py": False,
        "generation_checkpoint": "original_one_update_smoke_checkpoint",
        "selected_checkpoint_path": checkpoint_dir,
        "selected_checkpoint_inventory": saved_inventory,
        "selected_checkpoint_hash_set": dict(saved_inventory),
        "on_disk_hashes_recorded_before_generation": True,
        "on_disk_hashes_at_generation_reload": generation_inventory,
        "pre_generation_reloaded_tensor_digests": [
            {
                "name": saved_separation_name,
                "saved_checkpoint_digest": saved_separation_digest,
                "reloaded_digest": generation_digest,
                "mutated_training_digest": mutated_training_digest,
                "match_saved_checkpoint": generation_digest == saved_separation_digest,
                "match_mutated_training_object": generation_digest == mutated_training_digest,
            }
        ],
        "generation_object_matches_on_disk_checkpoint": generation_digest == saved_separation_digest and generation_inventory == saved_inventory,
        "generation_used_mutated_training_object": generation_digest == mutated_training_digest or id(generation_unet) == mutated_training_object_id,
        "training_release_observation": release,
        "training_objects_released_before_generation_reload": release["training_objects_released_before_generation_reload"],
        "released_training_object_names": list(release["released_training_object_names"]),
        "separation_basis": contract.GENERATION_SEPARATION_BASIS,
        "python_object_id_is_sufficient": False,
        "generation_object_id": id(generation_unet),
        "mutated_training_object_id": mutated_training_object_id,
    }
    resume["generation_object_id"] = generation_proof["generation_object_id"]
    resume["generation_used_mutated_training_object"] = generation_proof["generation_used_mutated_training_object"]
    frozen_final = _post_generation_frozen_snapshot(
        torch,
        encdec,
        evidence["membership_evidence"],
        evidence["baseline"],
        evidence["rotary_names"],
    )
    output_path = os.path.join(evidence_dir, "smoke_generation_sequences.txt")
    payload = "".join(str(sequence) + "\n" for sequence in sequences).encode("utf-8")
    contract.publish_exclusive(output_path, payload)
    generation_sha256 = _sha256_path(output_path)
    if generation_sha256 != contract.sha256_bytes(payload):
        raise contract.M5SmokeError("generation_proof_failed", "reread generation hash does not match the written bytes")
    generation_proof["output_sha256"] = generation_sha256
    generation_proof["count"] = len(sequences)
    rows = []
    for module, component_name in ((encdec, None), (generation_unet, "denoiser")):
        for name, parameter in module.named_parameters():
            component = component_name or _component_for(name)
            if component is None:
                continue
            rows.append(
                {
                    "component": component,
                    "numel": int(parameter.numel()),
                    "dtype": str(parameter.dtype).replace("torch.", ""),
                    "requires_grad": bool(parameter.requires_grad),
                }
            )
    shapes = evidence["shapes"]
    timings["total_seconds"] = time.perf_counter() - evidence["started"]
    starting_assets = dict(plan["model_digests"])
    starting_assets[contract.DIFFUSERS_PATCH_PATH] = plan["patch_sha256"]
    file_hashes = {
        "configuration": plan["config_sha256"],
        "fixture": plan["fixture_sha256"],
        "implementation_contract": plan["implementation_hashes"]["implementation_contract"],
        "implementation_harness": plan["implementation_hashes"]["implementation_harness"],
        "starting_assets": starting_assets,
        "checkpoint_inventory": saved_inventory,
        "resume_sidecar": evidence["sidecar_sha256"],
        "generation_output": generation_sha256,
    }
    batch_accounting = {
        "requested_microbatch": evidence["requested_microbatch"],
        "measured_microbatch": evidence["measured_microbatch"],
        "requested_accumulation": evidence["requested_accumulation"],
        "measured_accumulation": evidence["measured_accumulation"],
        "requested_effective_batch": evidence["requested_effective"],
        "measured_effective_batch": evidence["measured_effective"],
        "actual_batch_shape": list(shapes["input_ids_shape"]),
    }
    overall_allocated_bytes = int(torch.cuda.max_memory_allocated(device))
    overall_reserved_bytes = int(torch.cuda.max_memory_reserved(device))
    repository_commits = {
        "mres_implementation_commit": plan["implementation_commit"],
        "mres_authorization_commit": plan["authorization_commit"],
        "rnagenesis_commit": plan["rnagenesis_commit"],
    }
    data_input_audit = {
        "declared_scientific_data_inputs": [contract.FIXTURE_RELATIVE],
        "validated_required_asset_paths": list(plan["observed_model_paths"]) + list(plan["observed_environment_paths"]),
        "cli_scientific_data_arguments": [],
        "dynamic_file_open_audit_performed": False,
        "data_access_guard_basis": {
            "closed_cli": True,
            "pinned_constant_fixture_path": contract.FIXTURE_RELATIVE,
            "pinned_call_graph": True,
            "denied_role_names": sorted(contract.DENIED_BASENAMES),
            "denied_role_hashes": dict(contract.DENIED_HASHES),
            "repository_commits": repository_commits,
        },
    }
    report = _manifest_report(
        plan,
        evidence_dir,
        rows,
        shapes,
        evidence["loss_value"],
        evidence["update"],
        resume,
        evidence["losses"],
        smoke,
    )
    report["gradient_norm"] = evidence["gradient_norm"]
    report["timings"] = timings
    report["denoiser_update"] = evidence["update"]
    report["mres_implementation_commit"] = plan["implementation_commit"]
    report["mres_authorization_commit"] = plan["authorization_commit"]
    report["rnagenesis_commit"] = plan["rnagenesis_commit"]
    observed = {
        "shapes": shapes,
        "batch_accounting": batch_accounting,
        "loss": evidence["loss_value"],
        "gradients": evidence["gradient_rows"],
        "frozen_after_backward": evidence["frozen_after_backward"],
        "update": evidence["update"],
        "frozen_after_update": evidence["frozen_after_update"],
        "frozen_final": frozen_final,
        "checkpoint": evidence["checkpoint_proof"],
        "resume": resume,
        "overfit_losses": evidence["losses"],
        "generation": generation_proof,
        "generation_output": {"path": output_path, "sha256": generation_sha256, "count": len(sequences)},
        "phase_records": _phase_records(
            evidence["measured_microbatch"],
            evidence["measured_accumulation"],
            evidence["measured_effective"],
            evidence["fp32_paired_loss"],
            evidence["bf16_observation"],
            evidence["accumulation_proof"],
        ),
        "starting_ema_inspection": evidence["starting_ema"],
        "file_hashes": file_hashes,
        "package_runtime": evidence["runtime"],
        "data_input_audit": data_input_audit,
        "memory_peaks": {
            "training_allocated_bytes": evidence["training_allocated_bytes"],
            "training_reserved_bytes": evidence["training_reserved_bytes"],
            "overall_allocated_bytes": overall_allocated_bytes,
            "overall_reserved_bytes": overall_reserved_bytes,
            "accounting": {
                "adamw_moments_allocated_before_training_measurement": evidence["moment_count_after_step"] >= 1,
                "training_peak_captured_before_checkpoint_reload_resume_generation": True,
                "overall_peak_includes_checkpoint_reload_resume_generation": overall_allocated_bytes >= evidence["training_allocated_bytes"] and overall_reserved_bytes >= evidence["training_reserved_bytes"],
                "training_allocated_bytes": evidence["training_allocated_bytes"],
                "training_reserved_bytes": evidence["training_reserved_bytes"],
                "overall_allocated_bytes": overall_allocated_bytes,
                "overall_reserved_bytes": overall_reserved_bytes,
            },
        },
        "report": report,
    }
    manifest = perform_smoke(observed, smoke)
    manifest_path = os.path.join(evidence_dir, "m5_smoke_manifest.json")
    contract.publish_exclusive(manifest_path, contract.canonical_json(manifest))
    external_hash = _sha256_path(manifest_path)
    contract.publish_exclusive(
        os.path.join(evidence_dir, contract.EXTERNAL_MANIFEST_HASH_NAME),
        (external_hash + "\n").encode("ascii"),
    )
    return manifest


def _manifest_report(plan, evidence_dir, rows, shapes, loss, update, resume, losses, smoke):
    authorisation = plan["authorisation"]
    return {
        "manifest_schema_version": contract.MANIFEST_SCHEMA_VERSION,
        "schema_version": contract.SCHEMA_VERSION,
        "experiment_id": contract.EXPERIMENT_ID,
        "run_id": authorisation["single_use_run_id"],
        "synthetic_only": True,
        "authorisation_id": authorisation["authorisation_id"],
        "authorisation_consumption_state": "single_use_exercised_output_created",
        "mres_implementation_commit": plan["implementation_commit"],
        "mres_authorization_commit": plan["authorization_commit"],
        "rnagenesis_commit": plan["rnagenesis_commit"],
        "tracked_clean": True,
        "untracked_state": list(contract.KNOWN_RNAGENESIS_UNTRACKED),
        "file_hashes": None,
        "permitted_input_paths": [contract.FIXTURE_RELATIVE],
        "declared_scientific_data_inputs": None,
        "validated_required_asset_paths": None,
        "data_input_audit": None,
        "physical_gpu_index": authorisation["physical_gpu"],
        "gpu_uuid": authorisation["gpu_uuid"],
        "pci_bus": authorisation["pci_bus"],
        "gpu_model": plan["probe"]["model_name"],
        "logical_device_mapping": {
            "logical_device": contract.LOGICAL_DEVICE,
            "cuda_visible_devices": str(authorisation["physical_gpu"]),
            "cuda_device_order": contract.CUDA_DEVICE_ORDER,
        },
        "package_runtime": None,
        "parameter_table": contract.component_parameter_table(rows),
        "shapes_dtypes": shapes,
        "optimizer_state": {"name": "AdamW", "moments_present": resume["optimizer_moments_present"], "moment_count": resume["optimizer_moment_count"]},
        "scheduler_state": {
            "name": "cosine_smoke_only",
            "position_restored": resume["scheduler_position_restored"],
            "last_epoch": resume["scheduler_last_epoch_restored"],
            "learning_rate": resume["learning_rate_restored_value"],
        },
        "requested_microbatch": None,
        "measured_microbatch": None,
        "actual_batch_shape": None,
        "requested_accumulation": None,
        "measured_accumulation": None,
        "requested_effective_batch": None,
        "measured_effective_batch": None,
        "phase_records": None,
        "precision_used": smoke["smoke_precision"],
        "ema_enabled": False,
        "starting_ema_inspection": None,
        "generation_weight_variant": smoke["generation_weights"],
        "m5_milestone_complete": False,
        "loss_finite": loss == loss,
        "gradients_finite": True,
        "gradient_norm": None,
        "frozen_state": None,
        "denoiser_update": update,
        "checkpoint_reload": None,
        "resume_proof": resume,
        "overfit_trajectory": losses,
        "overfit_pass_rule": smoke["loss_pass_rule"],
        "overfit_passed": False,
        "generation_reload": None,
        "generation_output": None,
        "peak_training_allocated_bytes": None,
        "peak_training_reserved_bytes": None,
        "peak_allocated_bytes": None,
        "peak_reserved_bytes": None,
        "memory_peak_accounting": None,
        "timings": {},
        "warnings": ["software_behaviour_check_not_biological_learning"],
        "deviations": [
            "synthetic_sequence_uses_physical_microbatch_8_and_accumulation_4",
            "bf16_observation_does_not_select_production_precision",
            "production_precision_accumulation_and_ema_policy_remain_unresolved",
            "m5_completion_remains_a_human_gate",
        ],
        "failure_state": None,
        "completion_state": "incomplete",
        "smoke_measurements_are_not_d1_decisions": True,
        "evidence_directory": evidence_dir,
    }


def worker_main(output_directory, physical_gpu, authorization_sha256):
    deps = ParentDependencies(output_directory, physical_gpu)
    deps.require_absent_output = False
    plan = contract.evaluate_parent_gate(deps)
    expected = contract.sha256_bytes(contract.canonical_json(plan["authorisation"]))
    if expected != authorization_sha256:
        raise contract.M5SmokeError("authorisation_delta_invalid", "worker authorization digest does not match")
    torch, trainer, pipeline_cls = _import_worker_stack()
    observation = {
        "cuda_device_count": int(torch.cuda.device_count()),
        "device": contract.LOGICAL_DEVICE,
        "logical_index": int(torch.cuda.current_device()),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "cpu_fallback": False,
        "other_gpu_fallback": False,
    }
    contract.assert_logical_device(observation, physical_gpu)
    backend = RealSmokeBackend(plan, output_directory)
    backend.worker_authorised = True
    try:
        return backend.run_observed()
    except contract.M5SmokeError as exc:
        _write_failure(output_directory, exc)
        raise


def build_parser():
    parser = argparse.ArgumentParser(description="M5 synthetic smoke parent. The checked-in configuration is not executable.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--physical-gpu", required=True)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--authorization-sha256")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    physical_gpu = contract.parse_physical_gpu_argument(args.physical_gpu)
    if args.worker:
        if not contract._is_sha256(args.authorization_sha256):
            raise contract.M5SmokeError("authorisation_field_missing", "worker authorization digest is missing")
        worker_main(args.output_dir, physical_gpu, args.authorization_sha256)
        return 0
    deps = ParentDependencies(args.output_dir, physical_gpu)
    run_parent(deps)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except contract.M5SmokeError as exc:
        sys.stderr.write(exc.code + ": " + exc.detail + "\n")
        raise SystemExit(1)
