#!/usr/bin/env python3
"""M6 pilot runner.

The production entry point accepts ``--help`` and no other arguments. The
checked-in configuration is rejected before torch, Accelerate, Diffusers,
RNAGenesis, biological data, validation tensors, CUDA, or a directory
create. A future authorisation-only commit can satisfy the active schema in
the contract. After that schema, the repository, and the bound paths pass,
the parent starts the production child with its working directory set to
the pinned RNAGenesis root. The child confirms that resolved directory
before it imports the training stack. Synthetic tests call
``run_synthetic_control_flow`` or pass an in-process worker. Neither path
is reachable from the CLI or from environment variables. A zero child exit
is accepted only after the parent reopens and validates the success
manifest. The final production CUDA RNG read fails closed and does not
reuse the initial state. An ordinary exception after consumption keeps the
latest stage, update, and microbatch, and records only the exception class.
It does not record the exception message or a traceback.

Position 22 is recorded as the next unapplied schedule position. The worker
does not step a PyTorch learning-rate scheduler and does not store that
position as ``last_epoch``.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

MRES_ROOT = "/home/laura/rnagenesis-aptamer-mres"
CONFIG_PATH = os.path.join(MRES_ROOT, "config/experiments/D1_diffusion_pilot.yaml")
FORBIDDEN_ENVIRONMENT = (
    "M6_AUTHORISATION_ID",
    "M6_CONFIG_PATH",
    "M6_DATA_PATH",
    "M6_ENABLE_EXECUTION",
    "M6_OUTPUT_DIRECTORY",
    "M6_PILOT_BACKEND",
)
HELP_TEXT = """\
M6 diffusion pilot runner.

The checked-in configuration is not executable. This entry point accepts
no arguments other than --help. It does not accept repository, data, model,
configuration, or output paths.
"""


def _load_contract():
    path = os.path.join(MRES_ROOT, "scripts/modelling/m6_pilot_contract.py")
    spec = importlib.util.spec_from_file_location("m6_pilot_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = _load_contract()


def _reject_environment(environ):
    for name in FORBIDDEN_ENVIRONMENT:
        if environ.get(name):
            raise contract.M6PilotError(
                "environment_injection_rejected",
                "environment variables cannot enable execution or inject paths",
            )


def production_main(argv=None):
    """Fixed entry. Inactive configuration fails before any heavy work."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--help"], ["-h"]):
        sys.stdout.write(HELP_TEXT)
        return 0
    if arguments:
        raise contract.M6PilotError(
            "cli_argument_rejected",
            "the production entry accepts no path, data, model, configuration, or output override",
        )
    _reject_environment(os.environ)
    with open(CONFIG_PATH, "rb") as handle:
        raw = handle.read()
    return evaluate_configuration(raw)


def evaluate_configuration(raw, observation=None, worker=None, importer=None, run_root=None):
    """Classify the pinned document. Heavy imports happen only after an active pass."""
    _reject_environment(os.environ)
    config = contract.load_config_bytes(raw)
    kind = contract.classify_configuration(config)
    if kind == "inactive":
        contract.assert_inactive_text(raw.decode("utf-8"))
        contract.reject_inactive_before_execution(config)
    if observation is None:
        observation = live_repository_observation(config)
    authorisation = contract.validate_active_execution(config, observation, contract.RUN_ROOT if run_root is None else run_root)
    if worker is not None:
        return worker(authorisation)
    if importer is not None:
        stack = load_training_stack(authorisation, importer=importer)
        return execute_authorized_worker(authorisation, stack, run_root=run_root)
    return launch_isolated_worker(authorisation, run_root=run_root)


def load_training_stack(authorisation, importer=None):
    """Import the pinned stack only after active authorisation has passed."""
    if not isinstance(authorisation, contract.ValidatedActiveAuthorisation):
        raise contract.M6PilotError(
            "execution_not_authorised",
            "refusing torch, Accelerate, Diffusers, and RNAGenesis imports",
        )
    if importer is None:
        importer = _import_pinned_training_stack
    return importer()


def _git(repo, args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True)


def _sha256_file(path):
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def live_repository_observation(config):
    """Stdlib repository, path, and GPU observation. No training import."""
    head = _git(contract.MRES_ROOT, ["rev-parse", "HEAD"]).strip()
    parents = [line.strip() for line in _git(contract.MRES_ROOT, ["rev-parse", "HEAD^@"]).splitlines() if line.strip()]
    parent = parents[0]
    implementation_raw = subprocess.check_output(["git", "show", parent + ":" + contract.CONFIG_RELATIVE], cwd=contract.MRES_ROOT)
    changed = [line.strip() for line in _git(contract.MRES_ROOT, ["diff", "--name-only", parent, "HEAD"]).splitlines() if line.strip()]
    file_sha_parent = {}
    file_sha_work = {}
    for relative in contract.IMPLEMENTATION_FILE_PATHS:
        blob = subprocess.check_output(["git", "show", parent + ":" + relative], cwd=contract.MRES_ROOT)
        file_sha_parent[relative] = contract.sha256_bytes(blob)
        file_sha_work[relative] = _sha256_file(os.path.join(contract.MRES_ROOT, relative))
    output = config["pilot_execution_authorisation"]["output_directory"]
    return {
        "changed_files": changed,
        "component_symlink": _component_is_symlink(output),
        "file_sha256_at_parent": file_sha_parent,
        "file_sha256_working_tree": file_sha_work,
        "gpu_probe": live_gpu_probe(),
        "implementation_config": contract.load_config_bytes(implementation_raw),
        "mres_head": head,
        "mres_parents": parents,
        "mres_porcelain": _git(contract.MRES_ROOT, ["status", "--porcelain=v1", "--untracked-files=all"]),
        "output_exists": os.path.lexists(output),
        "output_symlink": os.path.islink(output),
        "rnagenesis_branch": _git(contract.RNAGENESIS_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"]).strip(),
        "rnagenesis_directory_porcelain": _git(contract.RNAGENESIS_ROOT, ["status", "--porcelain=v1"]),
        "rnagenesis_file_porcelain": _git(contract.RNAGENESIS_ROOT, ["status", "--porcelain=v1", "--untracked-files=all"]),
        "rnagenesis_head": _git(contract.RNAGENESIS_ROOT, ["rev-parse", "HEAD"]).strip(),
    }


def _component_is_symlink(path):
    current = os.path.abspath(path)
    while True:
        if os.path.islink(current):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def live_gpu_probe():
    """Read the authorised device with nvidia-smi before a CUDA training import."""
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    completed = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,uuid,pci.bus_id", "--format=csv,noheader"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or visible is None:
        raise contract.M6PilotError("identity_mismatch", "physical GPU probe failed before training imports")
    rows = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            continue
        rows.append({"index": int(parts[0]), "uuid": parts[1], "pci_bus": parts[2]})
    if visible not in {str(row["index"]) for row in rows}:
        raise contract.M6PilotError("identity_mismatch", "CUDA_VISIBLE_DEVICES does not name a probed GPU")
    selected = [row for row in rows if str(row["index"]) == visible][0]
    return {
        "cuda_visible_devices": visible,
        "logical_device": contract.LOGICAL_CUDA_DEVICE,
        "pci_bus": selected["pci_bus"],
        "physical_index": selected["index"],
        "uuid": selected["uuid"],
    }


def load_artifact_loader():
    """Load the tracked artifact loader by absolute path, independent of cwd and sys.path."""
    path = contract.ARTIFACT_LOADER_PATH
    spec = importlib.util.spec_from_file_location("m6_pinned_validation_artifact_loader", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resolved = os.path.realpath(getattr(module, "__file__", ""))
    if resolved != os.path.realpath(path):
        raise contract.M6PilotError("identity_mismatch", "artifact loader did not resolve to the tracked file")
    return module


def _pinned_path(path):
    """Return a pathlib.Path for one pinned RNAGenesis path argument.

    The pinned readers call ``path.is_absolute()``, B1 loading calls
    ``path.resolve()``, and checkpoint save calls ``directory.mkdir()``.
    A string has none of those methods. The remaining pinned path arguments
    accept ``Path`` through ``str()`` or ``os.PathLike``.
    """
    if isinstance(path, Path):
        return path
    return Path(path)


def assert_production_worker_directory():
    """Fail closed unless the resolved cwd is the pinned RNAGenesis root.

    The production child is launched with that root as its working directory,
    which is the accepted M5 execution behaviour. This check does not change
    the working directory. It runs before the training stack is imported.

    The pinned biomap RNA EncDec constructor opens two files through the
    relative ``ProGenPath`` prefix ``models/autoencoder/decoder/progen_configs``:
    ``<decoder_config>.json`` and ``<rna_tokenizer_config>.json``. With the
    released EncDec config those are the already hashed decoder configuration
    and tokenizer. The biomap encoder config and the xTrimo vocabulary are
    resolved from ``__file__``. ``DATA_CACHE_DIR`` is unused.
    ``XDG_CACHE_HOME = ".cache"`` is assigned only by ``generation.py`` and
    ``models/guidance/classifier.py``, which this worker does not import.
    ``pipeline_ddim`` imports ``ProGenPath`` and does not open it.
    """
    observed = os.path.realpath(os.getcwd())
    expected = os.path.realpath(contract.RNAGENESIS_ROOT)
    if observed != expected:
        raise contract.M6PilotError(
            "identity_mismatch",
            "production worker working directory is not the pinned RNAGenesis root",
            stage="production_worker_directory",
        )
    return expected


def _import_pinned_training_stack():
    """Import RNAGenesis and the artifact loader. Called only after the gate and isolation."""
    assert_production_worker_directory()
    root = contract.RNAGENESIS_ROOT
    encoder = os.path.join(root, "models", "autoencoder", "encoder")
    for path in (root, encoder):
        if path not in sys.path:
            sys.path.insert(0, path)
    trainer = importlib.import_module("train_diffusion_mres")
    artifacts = load_artifact_loader()
    accelerate = importlib.import_module("accelerate")
    return PinnedTrainingStack(trainer, artifacts, accelerate)


class PinnedTrainingStack(object):
    """Real call surface. Validation draws are loaded, never rebuilt."""

    identity = "pinned-rnagenesis-e3b855bbf4d1af376f43747643fa30afd662828c"
    production_identities = True
    enforce_runtime_isolation = True

    def __init__(self, trainer, artifacts, accelerate):
        self.trainer = trainer
        self.artifacts = artifacts
        self.accelerate = accelerate
        self.load_verified_artifacts = artifacts.load_verified_artifacts

    def read_train_sequences(self, path):
        return self.trainer.read_train_sequences(_pinned_path(path), True)

    def read_validation_cores(self, path):
        return self.trainer.read_validation_cores(_pinned_path(path), True)

    def load_tokenizer(self):
        tokens = importlib.import_module("models.autoencoder.encoder.biomap.rna_tokens")
        return tokens.load_tokenizer()

    def collate_sequences(self, examples, tokenizer):
        return self.trainer.collate_sequences(examples, tokenizer)

    def sequence_dataset(self, sequences):
        return self.trainer.SequenceIndexDataset(sequences)

    def load_frozen_encdec(self, path):
        return self.trainer.load_frozen_encdec(_pinned_path(path))

    def load_b1_denoiser(self, path):
        return self.trainer.load_b1_denoiser(_pinned_path(path))

    def load_scheduler(self, path):
        return self.trainer.load_scheduler(_pinned_path(path))

    def build_adamw(self, denoiser, learning_rate):
        optimizer = self.trainer.build_adamw(denoiser, learning_rate)
        _assert_adamw_hyperparameters(optimizer)
        return optimizer

    def assert_optimizer_membership(self, optimizer, denoiser, encdec):
        return self.trainer.assert_optimizer_membership(optimizer, denoiser, encdec)

    def extract_latents(self, encdec, input_ids, attention_mask):
        return self.trainer.extract_latents(encdec, input_ids, attention_mask)

    def sample_train_diffusion(self, batch_size, generator, num_train_timesteps, device):
        return self.trainer.sample_train_diffusion(batch_size, generator, num_train_timesteps, device)

    def denoising_mse(self, model, scheduler, latents, noise, timesteps):
        return self.trainer.denoising_mse(model, scheduler, latents, noise, timesteps, dtype=self.torch().float32)

    def save_checkpoint(self, denoiser, scheduler, directory):
        return self.trainer.save_diffusers_checkpoint(denoiser, scheduler, _pinned_path(directory))

    def reload_denoiser(self, directory):
        denoiser = self.trainer.TransformerDenoiser.from_pretrained(_pinned_path(directory), subfolder="unet")
        if denoiser is None:
            raise contract.M6PilotError("checkpoint_save_reload_incompatibility", "fresh denoiser reload returned nothing")
        return denoiser

    def accelerator(self):
        return self.accelerate.Accelerator(
            gradient_accumulation_steps=contract.PRODUCTION_ACCELERATOR_GRADIENT_ACCUMULATION_STEPS,
            mixed_precision="no",
        )

    def torch(self):
        return importlib.import_module("torch")

    def clock(self):
        return SynchronizedClock(self.torch())

    def observe_assets(self):
        return contract.observe_required_assets()

    def observe_runtime(self):
        torch = self.torch()
        diffusers = importlib.import_module("diffusers")
        accelerate = importlib.import_module("accelerate")
        transformers = importlib.import_module("transformers")
        return observe_module_runtime(torch, diffusers, accelerate, transformers)


def _assert_adamw_hyperparameters(optimizer):
    defaults = optimizer.defaults
    expected = {
        "betas": (contract.ADAMW_BETA1, contract.ADAMW_BETA2),
        "eps": contract.ADAMW_EPSILON,
        "weight_decay": contract.ADAMW_WEIGHT_DECAY,
    }
    for key, value in expected.items():
        if defaults.get(key) != value:
            raise contract.M6PilotError("identity_mismatch", "AdamW parameter drifted: " + key)
    return True


class SynchronizedClock(object):
    """Stamp wall time only after CUDA work that was already queued has finished."""

    def __init__(self, torch_module):
        self.torch = torch_module

    def stamp(self):
        cuda = getattr(self.torch, "cuda", None)
        if cuda is None or cuda.is_available() is not True:
            raise contract.M6PilotError("identity_mismatch", "CUDA synchronization is unavailable")
        cuda.synchronize()
        return time.perf_counter()


def observe_module_runtime(torch_module, diffusers, accelerate, transformers):
    """Read versions from the imported modules. Torch keeps the +cu121 local suffix."""
    import platform

    return {
        "accelerate": accelerate.__version__,
        "diffusers": diffusers.__version__,
        "evidence_origin": "observed",
        "executable": sys.executable,
        "observation_method": "module_attribute",
        "python": platform.python_version(),
        "torch": torch_module.__version__,
        "transformers": transformers.__version__,
    }


def assert_denoiser_fp32(torch_module, denoiser):
    """Reject a mixed-dtype denoiser even when the module-level dtype reports float32."""
    for name, parameter in denoiser.named_parameters():
        if parameter.is_floating_point() and parameter.dtype != torch_module.float32:
            raise contract.M6PilotError("identity_mismatch", "denoiser parameter is not float32: " + name)
    for module_name, module in denoiser.named_modules():
        nonpersistent = set(getattr(module, "_non_persistent_buffers_set", ()))
        for name, buffer in module.named_buffers(recurse=False):
            if name in nonpersistent:
                continue
            if buffer.is_floating_point() and buffer.dtype != torch_module.float32:
                qualified = name if module_name == "" else module_name + "." + name
                raise contract.M6PilotError("identity_mismatch", "denoiser buffer is not float32: " + qualified)
    return True


def _normalize_logical_cuda_device(device, torch_module):
    """Accept Accelerate's unindexed ``torch.device("cuda")`` only when it is logical cuda:0.

    Accelerate 0.25 ``PartialState.default_device`` returns ``torch.device("cuda")``
    when CUDA is available. ``str`` of that object is ``cuda``, its type is
    ``cuda``, and its index is ``None``. ``str(torch.device("cuda", 0))`` is
    the canonical ``cuda:0``. An explicit index must already be 0. A missing
    index is resolved with ``torch.cuda.current_device`` and must also be 0.
    """
    try:
        resolved = torch_module.device(device)
    except contract.M6PilotError:
        raise
    except Exception:
        raise contract.M6PilotError("identity_mismatch", "logical device is not cuda:0")
    if getattr(resolved, "type", None) != "cuda":
        raise contract.M6PilotError("identity_mismatch", "logical device is not cuda:0")
    index = getattr(resolved, "index", None)
    if index is None:
        try:
            index = torch_module.cuda.current_device()
        except contract.M6PilotError:
            raise
        except Exception:
            raise contract.M6PilotError("identity_mismatch", "logical device is not cuda:0")
    if isinstance(index, bool):
        raise contract.M6PilotError("identity_mismatch", "logical device is not cuda:0")
    try:
        numeric_index = int(index)
    except Exception:
        raise contract.M6PilotError("identity_mismatch", "logical device is not cuda:0")
    if numeric_index != 0:
        raise contract.M6PilotError("identity_mismatch", "logical device is not cuda:0")
    normalized = torch_module.device("cuda", 0)
    if str(normalized) != contract.LOGICAL_CUDA_DEVICE or getattr(normalized, "index", None) != 0:
        raise contract.M6PilotError("identity_mismatch", "logical device is not cuda:0")
    return normalized


def assert_prepared_runtime(accelerator, torch_module, device_count):
    if int(getattr(accelerator, "num_processes", 0)) != 1:
        raise contract.M6PilotError("identity_mismatch", "Accelerate must run as exactly one process")
    if int(device_count) != 1:
        raise contract.M6PilotError("identity_mismatch", "the worker must see exactly one CUDA device")
    logical_device = _normalize_logical_cuda_device(getattr(accelerator, "device", None), torch_module)
    if accelerator.gradient_accumulation_steps != 1 or accelerator.mixed_precision != "no":
        raise contract.M6PilotError("microbatch_arithmetic_invalid", "Accelerate would divide the manual accumulation again")
    return logical_device


def _rotary_cache(name):
    leaf = name.split(".")[-1]
    return leaf in contract.m5_contract().ROTARY_CACHE_ATTRIBUTES


def _persistent_buffer_rows(module):
    rows = []
    rotary = []
    for module_name, submodule in module.named_modules():
        nonpersistent = set(getattr(submodule, "_non_persistent_buffers_set", ()))
        for name, buffer in submodule.named_buffers(recurse=False):
            qualified = name if module_name == "" else module_name + "." + name
            if _rotary_cache(qualified):
                rotary.append(qualified)
                continue
            if name in nonpersistent:
                continue
            rows.append({"digest": contract.state_entry_digest(qualified, buffer.detach()), "name": qualified})
    rows.sort(key=lambda item: item["name"])
    rotary.sort()
    return rows, rotary


def encdec_frozen_digests(module):
    """Parameter digest plus persistent-buffer digest. Rotary runtime caches are excluded."""
    parameter_rows = []
    for name, parameter in module.named_parameters():
        parameter_rows.append({"digest": contract.state_entry_digest(name, parameter.detach()), "name": name})
    parameter_rows.sort(key=lambda item: item["name"])
    buffer_rows, rotary = _persistent_buffer_rows(module)
    return {
        "parameter_digest": contract.sha256_bytes(contract.canonical_json(parameter_rows)),
        "persistent_buffer_digest": contract.sha256_bytes(contract.canonical_json(buffer_rows)),
        "rotary_cache_names": rotary,
    }


def frozen_parameter_digest(module):
    return encdec_frozen_digests(module)["parameter_digest"]


def live_parameter_identity_proof(optimizer, denoiser, encdec):
    """Prove membership with live parameter and buffer identities."""
    optimizer_ids = [id(parameter) for group in optimizer.param_groups for parameter in group["params"]]
    trainable_ids = [id(parameter) for parameter in denoiser.parameters() if parameter.requires_grad]
    encdec_ids = [id(parameter) for parameter in encdec.parameters()]
    encdec_buffer_ids = [id(buffer) for buffer in encdec.buffers()]
    if set(optimizer_ids) != set(trainable_ids) or len(optimizer_ids) != len(set(trainable_ids)):
        raise contract.M6PilotError("modified_or_trainable_encdec", "optimizer parameters are not the complete trainable denoiser")
    if set(optimizer_ids) & set(encdec_ids):
        raise contract.M6PilotError("modified_or_trainable_encdec", "an EncDec parameter is in the optimizer")
    if set(optimizer_ids) & set(encdec_buffer_ids):
        raise contract.M6PilotError("modified_or_trainable_encdec", "an EncDec buffer is in the optimizer")
    if any(parameter.requires_grad for _name, parameter in encdec.named_parameters()):
        raise contract.M6PilotError("modified_or_trainable_encdec", "an EncDec parameter requires grad")
    if encdec.training:
        raise contract.M6PilotError("modified_or_trainable_encdec", "EncDec is not in evaluation mode")
    return {
        "encdec_buffers_absent_from_optimizer": True,
        "encdec_eval_mode": True,
        "encdec_parameters_absent_from_optimizer": True,
        "encdec_requires_grad_false": True,
        "optimizer_contains_only_denoiser": True,
        "optimizer_parameter_ids_equal_trainable_denoiser": True,
    }


def select_denoiser_change(torch_module, named_parameters):
    """First sorted parameter element with a finite nonzero gradient."""
    for name, parameter in sorted(named_parameters, key=lambda item: item[0]):
        if parameter.grad is None:
            continue
        flat_gradient = parameter.grad.detach().reshape(-1)
        hits = torch_module.nonzero(torch_module.isfinite(flat_gradient) & flat_gradient.ne(0), as_tuple=False)
        if hits.numel() == 0:
            continue
        index = int(hits[0])
        before = parameter.detach().reshape(-1)[index].clone()
        return {
            "flat_index": index,
            "gradient": flat_gradient[index].clone(),
            "parameter": parameter,
            "parameter_name": name,
            "value_before": before,
        }
    raise contract.M6PilotError("no_observed_denoiser_change", "no denoiser element had a finite nonzero gradient")


def finish_denoiser_change(selected):
    after = selected["parameter"].detach().reshape(-1)[selected["flat_index"]]
    before = selected["value_before"]
    gradient = selected["gradient"]
    if not bool(before.isfinite()) or not bool(after.isfinite()) or not bool(gradient.isfinite()):
        raise contract.M6PilotError("no_observed_denoiser_change", "denoiser change is not finite")
    if float(before) == float(after) or float(gradient) == 0.0:
        raise contract.M6PilotError("no_observed_denoiser_change", "the selected denoiser element did not change")
    return {
        "changed": True,
        "finite_nonzero_gradient": True,
        "flat_index": selected["flat_index"],
        "gradient": contract.format_decimal(float(gradient)),
        "parameter_name": selected["parameter_name"],
        "value_after": contract.format_decimal(float(after)),
        "value_before": contract.format_decimal(float(before)),
    }


def _binding_from_authorisation(authorisation):
    return {
        "authorization_commit": authorisation["authorization_commit"],
        "authorization_parent_commit": authorisation["authorization_parent_commit"],
        "cuda_visible_devices": authorisation["cuda_visible_devices"],
        "executing_implementation_commit": authorisation["executing_implementation_commit"],
        "gpu_uuid": authorisation["gpu_uuid"],
        "pci_bus": authorisation["pci_bus"],
        "physical_gpu_index": authorisation["physical_gpu_index"],
    }


def _create_isolated_caches(evidence):
    m5 = contract.m5_contract()
    cache_root = os.path.join(evidence, m5.RUNTIME_CACHE_DIRECTORY_NAME)
    huggingface = os.path.join(cache_root, "huggingface")
    for path in (
        os.path.join(evidence, m5.PYCACHE_DIRECTORY_NAME),
        cache_root,
        huggingface,
        os.path.join(huggingface, "hub"),
        os.path.join(huggingface, "assets"),
        os.path.join(huggingface, "modules"),
        os.path.join(cache_root, "torch"),
    ):
        os.mkdir(path)


def _default_spawn(argv, env, cwd):
    return subprocess.run(argv, cwd=cwd, env=env, check=False, shell=False)


_WORKER_BOOTSTRAP = """
import importlib.util
import sys
spec = importlib.util.spec_from_file_location("m6_worker", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.worker_main(sys.argv[2], sys.argv[3])
"""


def _remove_claimed_success_manifest(directory):
    manifest_path = os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)
    if not os.path.lexists(manifest_path):
        return
    if os.path.isdir(manifest_path) and not os.path.islink(manifest_path):
        return
    os.remove(manifest_path)


def _controlled_exception_class_name(exc):
    """Return a safe exception class token. The message and traceback are not used."""
    name = getattr(type(exc), "__name__", "")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
    if not isinstance(name, str) or not 1 <= len(name) <= 128 or name[0].isdigit():
        return "Exception"
    if name[0] not in alphabet or any(character not in alphabet for character in name):
        return "Exception"
    if contract.BODY_PATTERN.fullmatch(name) is not None:
        return "Exception"
    return name


def _controlled_exception_detail(exc):
    return "authorized worker failed; exception_class=" + _controlled_exception_class_name(exc)


def _record_consumed_failure(directory, exc, authorisation, progress):
    """Write one consumed failure. An existing child record stays authoritative.

    A precise ``M6PilotError`` keeps its code, detail, and context. An ordinary
    exception is recorded as ``incomplete_evidence_or_manifest`` with the latest
    stage, update, and microbatch, and with its class name only. The exception
    message, traceback, and any sequence or tensor payload are not serialized.
    A claimed success manifest cannot remain beside the failure record.
    """
    _remove_claimed_success_manifest(directory)
    if isinstance(exc, contract.M6PilotError):
        if exc.stage is None and progress is not None:
            exc.stage = progress.get("stage")
            exc.update = progress.get("update")
            exc.microbatch = progress.get("microbatch")
        recorded = exc
    else:
        recorded = contract.M6PilotError(
            "incomplete_evidence_or_manifest",
            _controlled_exception_detail(exc),
            stage=None if progress is None else progress.get("stage"),
            update=None if progress is None else progress.get("update"),
            microbatch=None if progress is None else progress.get("microbatch"),
        )
    failure_path = os.path.join(directory, contract.FAILURE_RECORD_NAME)
    if os.path.islink(failure_path):
        os.remove(failure_path)
    if not os.path.isfile(failure_path):
        retained = [] if progress is None else list(progress.get("retained_checkpoints", []))
        contract.write_failure_record(
            directory,
            recorded,
            authorisation=authorisation,
            retained_checkpoints=retained,
        )


def _error_from_preserved_failure(directory):
    """Return the child failure when a regular failure record is already present."""
    path = os.path.join(directory, contract.FAILURE_RECORD_NAME)
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as handle:
            parsed = json.loads(handle.read().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    code = parsed.get("failure_code")
    if code not in contract.STOP_CONDITION_CODES:
        return None
    detail = parsed.get("detail")
    if not isinstance(detail, str) or detail == "":
        detail = "worker failure record preserved"
    return contract.M6PilotError(
        code,
        detail,
        stage=parsed.get("stage"),
        update=parsed.get("update"),
        microbatch=parsed.get("microbatch"),
    )


def _raise_consumed_failure(directory, exc, fallback_stage):
    preserved = _error_from_preserved_failure(directory)
    if preserved is not None:
        raise preserved from None
    if isinstance(exc, contract.M6PilotError):
        raise exc from None
    raise contract.M6PilotError(
        "incomplete_evidence_or_manifest",
        _controlled_exception_detail(exc),
        stage=fallback_stage,
    ) from None


def _require_worker_success_manifest(directory, authorisation):
    """Reopen the child's claimed success and accept only a validated manifest."""
    failure_path = os.path.join(directory, contract.FAILURE_RECORD_NAME)
    if os.path.lexists(failure_path):
        raise contract.M6PilotError(
            "incomplete_evidence_or_manifest",
            "worker claimed success while a failure record exists",
            stage="worker_success_verification",
        )
    path = os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)
    if os.path.islink(path) or not os.path.isfile(path):
        raise contract.M6PilotError(
            "incomplete_evidence_or_manifest",
            "worker exited without a regular success manifest",
            stage="worker_success_verification",
        )
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise contract.M6PilotError(
            "incomplete_evidence_or_manifest",
            "worker success manifest is not valid JSON",
            stage="worker_success_verification",
        )
    if not isinstance(parsed, dict) or contract.canonical_json(parsed) != raw:
        raise contract.M6PilotError(
            "incomplete_evidence_or_manifest",
            "worker success manifest is not canonical JSON",
            stage="worker_success_verification",
        )
    contract.validate_production_success_manifest(parsed, _binding_from_authorisation(authorisation))
    return parsed


def launch_isolated_worker(authorisation, run_root=None, spawn=None, asset_observer=None, python_observer=None, environ=None):
    """Consume the directory once, then start the isolated worker. Reuse stays closed."""
    if asset_observer is None:
        asset_observer = contract.observe_required_assets
    if python_observer is None:
        python_observer = lambda: contract.assert_pinned_python_file(contract.m5_contract().PINNED_PYTHON)
    asset_observer()
    python_observer()
    root = contract.RUN_ROOT if run_root is None else run_root
    directory = contract.consume_bound_output_directory(authorisation, root)
    progress = {"microbatch": None, "retained_checkpoints": [], "stage": "worker_launch", "update": None}
    try:
        _create_isolated_caches(directory)
        parent = os.environ if environ is None else environ
        env = contract.isolation_environment(parent, authorisation["physical_gpu_index"], directory)
        if spawn is None:
            spawn = _default_spawn
        argv = [
            contract.m5_contract().PINNED_PYTHON,
            "-B",
            "-c",
            _WORKER_BOOTSTRAP,
            os.path.join(contract.MRES_ROOT, contract.RUNNER_RELATIVE),
            directory,
            authorisation["authorization_commit"],
        ]
        completed = spawn(argv, env, contract.RNAGENESIS_ROOT)
        if getattr(completed, "returncode", 1) != 0:
            raise contract.M6PilotError(
                "incomplete_evidence_or_manifest",
                "worker exited without a passing manifest",
                stage="worker_launch",
            )
        progress["stage"] = "worker_success_verification"
        _require_worker_success_manifest(directory, authorisation)
        return directory
    except Exception as exc:
        _record_consumed_failure(directory, exc, authorisation, progress)
        _raise_consumed_failure(directory, exc, progress.get("stage") or "worker_launch")


def worker_main(output_directory, authorization_commit, config_loader=None, observation_loader=None, stack_loader=None):
    """Child entry. The parent already consumed the directory and set the cache environment.

    Optional loaders are the in-process test seam. The production bootstrap
    calls this function with the output directory and authorisation commit only.
    That production path confirms the resolved working directory is the pinned
    RNAGenesis root before it imports the training stack. An injected
    ``stack_loader`` remains a test seam and does not replace that production check.
    """
    authorisation = None
    progress = {"microbatch": None, "retained_checkpoints": [], "stage": "worker_isolation", "update": None}
    try:
        contract.assert_isolation_environment(os.environ, output_directory)
        progress["stage"] = "configuration_load"
        if config_loader is None:
            with open(CONFIG_PATH, "rb") as handle:
                raw = handle.read()
            config = contract.load_config_bytes(raw)
        else:
            config = config_loader()
        progress["stage"] = "repository_observation"
        if observation_loader is None:
            observation_loader = live_repository_observation
        observation = observation_loader(config)
        progress["stage"] = "consumed_authorisation"
        authorisation = contract.validate_consumed_worker(config, observation, output_directory)
        progress["stage"] = "authorisation_commit"
        if authorisation["authorization_commit"] != authorization_commit:
            raise contract.M6PilotError(
                "authorisation_commit_invalid",
                "worker authorization commit drifted",
                stage="authorisation_commit",
            )
        if stack_loader is None:
            progress["stage"] = "production_worker_directory"
            assert_production_worker_directory()
        progress["stage"] = "training_stack_import"
        try:
            if stack_loader is None:
                stack = load_training_stack(authorisation)
            else:
                stack = stack_loader(authorisation)
        except contract.M6PilotError:
            raise
        except Exception:
            raise contract.M6PilotError(
                "training_stack_import_failed",
                "the pinned training stack could not be imported",
                stage="training_stack_import",
            )
        progress["stage"] = "worker_start"
        stack.pilot_progress = progress
        manifest = run_authorized_pilot(authorisation, stack, output_directory)
        contract.validate_production_success_manifest(manifest, _binding_from_authorisation(authorisation))
        contract.write_atomic_json(output_directory, contract.SUCCESS_MANIFEST_NAME, manifest)
        return manifest
    except Exception as exc:
        _record_consumed_failure(output_directory, exc, authorisation, progress)
        _raise_consumed_failure(output_directory, exc, progress.get("stage") or "worker_start")


def execute_authorized_worker(authorisation, stack, run_root=None):
    """Create the bound directory, then run an injected stack or leave it consumed."""
    if not isinstance(authorisation, contract.ValidatedActiveAuthorisation):
        raise contract.M6PilotError("execution_not_authorised", "the worker requires a validated active authorisation")
    if getattr(stack, "production_identities", False) is not True:
        raise contract.M6PilotError("execution_not_authorised", "refusing a non-production training stack")
    root = contract.RUN_ROOT if run_root is None else run_root
    directory = contract.consume_bound_output_directory(authorisation, root)
    progress = {"microbatch": None, "retained_checkpoints": [], "stage": "consumed", "update": None}
    stack.pilot_progress = progress
    try:
        if getattr(stack, "enforce_runtime_isolation", False) is True:
            _create_isolated_caches(directory)
            contract.assert_isolation_environment(os.environ, directory)
        manifest = run_authorized_pilot(authorisation, stack, directory)
        contract.validate_production_success_manifest(manifest, _binding_from_authorisation(authorisation))
        contract.write_atomic_json(directory, contract.SUCCESS_MANIFEST_NAME, manifest)
        return manifest
    except Exception as exc:
        _record_consumed_failure(directory, exc, authorisation, progress)
        _raise_consumed_failure(directory, exc, progress.get("stage") or "consumed")


def _progress_stage(stack, name, update=None, microbatch=None):
    progress = getattr(stack, "pilot_progress", None)
    if progress is None:
        return
    progress["stage"] = name
    progress["update"] = update
    progress["microbatch"] = microbatch


def _place(stack, tensor, device):
    if hasattr(stack, "place"):
        return stack.place(tensor, device)
    return tensor.to(device)


def _cuda_device_count(stack, torch_module):
    if hasattr(stack, "cuda_device_count"):
        return int(stack.cuda_device_count())
    return int(torch_module.cuda.device_count())


def run_authorized_pilot(authorisation, stack, directory):
    """One non-resumable pilot. Identity is closed before any biological open."""
    _progress_stage(stack, "runtime_identity")
    torch = stack.torch()
    if getattr(stack, "cpu_stand_in", False) is not True and torch.cuda.is_available() is not True:
        raise contract.M6PilotError(
            "identity_mismatch",
            "the authorised worker requires the bound CUDA device",
            stage="runtime_identity",
        )
    if getattr(stack, "enforce_runtime_isolation", False) is True:
        contract.assert_isolation_environment(os.environ, directory)
    _progress_stage(stack, "asset_identity")
    assets = stack.observe_assets()
    runtime = contract.assert_observed_runtime(stack.observe_runtime())
    accepted = contract._accepted_asset_table()
    if set(assets) != set(accepted):
        raise contract.M6PilotError("identity_mismatch", "observed model assets do not match the accepted set", stage="asset_identity")
    for role, spec in accepted.items():
        contract._require_streamed_asset(assets[role], role, spec)
    _progress_stage(stack, "biological_inputs")
    train_path = authorisation["train_text_path"]
    validation_path = authorisation["validation_csv_path"]
    artifact_path = authorisation["validation_artifact_directory"]
    train_open = contract.verify_bound_file(
        train_path,
        "TRAIN_TEXT",
        authorisation["train_text_sha256"],
        authorisation["train_record_count"],
        train_path,
        stack.read_train_sequences,
    )
    validation_open = contract.verify_bound_file(
        validation_path,
        "VALIDATION_CSV",
        authorisation["validation_csv_sha256"],
        authorisation["validation_record_count"],
        validation_path,
        stack.read_validation_cores,
    )
    train_sequences = train_open["opened"]
    validation_sequences = validation_open["opened"]
    if len(train_sequences) != contract.TRAIN_RECORD_COUNT or len(validation_sequences) != contract.VALIDATION_SEQUENCE_COUNT:
        raise contract.M6PilotError("identity_mismatch", "reader counts drifted after the bound open", stage="biological_inputs")
    loaded = _open_artifacts(authorisation, stack, artifact_path)
    _progress_stage(stack, "model_load")
    encdec_path = os.path.join(contract.RNAGENESIS_ROOT, contract.ENCDEC_RELATIVE_PATH)
    denoiser_path = os.path.join(contract.RNAGENESIS_ROOT, authorisation["b1_relative_path"])
    encdec = stack.load_frozen_encdec(encdec_path)
    denoiser = stack.load_b1_denoiser(denoiser_path)
    scheduler = stack.load_scheduler(denoiser_path)
    assert_denoiser_fp32(torch, denoiser)
    optimizer = stack.build_adamw(denoiser, contract.applied_learning_rate(1))
    _assert_adamw_hyperparameters(optimizer)
    accelerator = stack.accelerator()
    denoiser, optimizer = accelerator.prepare(denoiser, optimizer)
    logical_device = assert_prepared_runtime(accelerator, torch, _cuda_device_count(stack, torch))
    encdec = _place(stack, encdec, logical_device)
    encdec.eval()
    denoiser.train()
    membership = live_parameter_identity_proof(optimizer, denoiser, encdec)
    if hasattr(stack, "assert_optimizer_membership"):
        stack.assert_optimizer_membership(optimizer, denoiser, encdec)
    clock = stack.clock() if hasattr(stack, "clock") else SynchronizedClock(torch)
    rng = _initialise_streams(torch, stack)
    order = torch.randperm(len(train_sequences), generator=rng["permutation_generator"]).tolist()
    contract.permutation_digest(order)
    ordered = [train_sequences[index] for index in order]
    tokenizer = stack.load_tokenizer()
    frozen_rows = {0: encdec_frozen_digests(encdec)}
    validation_values = {}
    validation_durations = []
    _progress_stage(stack, "validation", update=0)

    def validate(update):
        _progress_stage(stack, "validation", update=update)
        started_at = clock.stamp()
        aggregate = _validation_aggregate(
            stack, accelerator, denoiser, encdec, scheduler, validation_sequences, loaded, tokenizer, torch, logical_device
        )
        validation_durations.append({"seconds": clock.stamp() - started_at, "update": update})
        return aggregate

    validation_values[0] = validate(0)
    train_rows = []
    train_durations = []
    checkpoint_durations = []
    checkpoints = []
    offset = 0
    for update, window in enumerate(contract.accumulation_windows(), start=1):
        _progress_stage(stack, "training_update", update=update)
        started_at = clock.stamp()
        learning_rate = contract.assign_applied_learning_rate(optimizer, update)
        scales = contract.applied_float_scales(window)
        window_loss = 0.0
        optimizer.zero_grad(set_to_none=True)
        for microbatch_index, (size, scale) in enumerate(zip(window, scales), start=1):
            _progress_stage(stack, "microbatch", update=update, microbatch=microbatch_index)
            batch_sequences = ordered[offset:offset + size]
            offset += size
            examples = [{"index": index, "sequence": sequence} for index, sequence in enumerate(batch_sequences)]
            batch = stack.collate_sequences(examples, tokenizer)
            latent = stack.extract_latents(
                encdec,
                _place(stack, batch["input_ids"], logical_device),
                _place(stack, batch["attention_mask"], logical_device),
            )
            timesteps, noise = stack.sample_train_diffusion(
                latent.shape[0], rng["diffusion_generator"], int(scheduler.config.num_train_timesteps), latent.device
            )
            loss = stack.denoising_mse(denoiser, scheduler, latent, noise, timesteps)
            contract.assert_finite_training_loss(float(loss.detach()))
            accelerator.backward(loss * contract.production_loss_scale(scale))
            window_loss += float(loss.detach()) * scale
        contract.assert_finite_training_loss(window_loss)
        parameters = [parameter for parameter in denoiser.parameters() if parameter.requires_grad]
        if not all(parameter.grad is not None and bool(torch.isfinite(parameter.grad).all()) for parameter in parameters):
            raise contract.M6PilotError("non_finite_trainable_gradient", "a trainable gradient is not finite", stage="training_update", update=update)
        selected = select_denoiser_change(torch, list(denoiser.named_parameters()))
        pre_clip = float(torch.nn.utils.clip_grad_norm_(parameters, contract.GRADIENT_CLIP_NORM))
        clip = contract.clip_pre_clip_norm(pre_clip)
        optimizer.step()
        change = finish_denoiser_change(selected)
        optimizer.zero_grad(set_to_none=True)
        train_durations.append(clock.stamp() - started_at)
        train_rows.append(
            {
                "applied_clip_norm": contract.format_decimal(clip["applied_norm"]),
                "clipped": clip["clipped"],
                "denoiser_change": change,
                "evidence_origin": "observed",
                "learning_rate": contract.format_decimal(learning_rate),
                "learning_rate_recorded_before_optimizer_step": True,
                "pre_clip_gradient_norm": contract.format_decimal(clip["pre_clip_gradient_norm"]),
                "stop_fired": False,
                "training_loss": contract.format_decimal(window_loss),
                "update": update,
            }
        )
        if update in contract.RETAINED_WEIGHT_UPDATES:
            _progress_stage(stack, "checkpoint", update=update)
            checkpoint_started = clock.stamp()
            checkpoints.append(
                _save_and_reload(stack, denoiser, scheduler, directory, update, denoiser, authorisation["executing_implementation_commit"])
            )
            checkpoint_durations.append({"seconds": clock.stamp() - checkpoint_started, "update": update})
            progress = getattr(stack, "pilot_progress", None)
            if progress is not None:
                progress["retained_checkpoints"].append(update)
        if update in (7, 14, 21):
            frozen_rows[update] = encdec_frozen_digests(encdec)
            if frozen_rows[update]["parameter_digest"] != frozen_rows[0]["parameter_digest"]:
                raise contract.M6PilotError("modified_or_trainable_encdec", "EncDec parameters changed", stage="frozen_check", update=update)
            if frozen_rows[update]["persistent_buffer_digest"] != frozen_rows[0]["persistent_buffer_digest"]:
                raise contract.M6PilotError("modified_or_trainable_encdec", "EncDec persistent buffers changed", stage="frozen_check", update=update)
            validation_values[update] = validate(update)
    if offset != contract.TRAIN_RECORD_COUNT or len(train_rows) != contract.OPTIMIZER_UPDATES:
        raise contract.M6PilotError("microbatch_arithmetic_invalid", "the worker did not consume 669 records in 21 updates")
    if [item["update"] for item in validation_durations] != list(contract.VALIDATION_UPDATES):
        raise contract.M6PilotError("validation_schedule_invalid", "validation timing is not updates 0, 7, 14, and 21")
    _progress_stage(stack, "rng_final_observation")
    rng_final = _final_stream_digests(torch, rng)
    return _assemble_production_manifest(
        authorisation,
        directory,
        rng,
        rng_final,
        order,
        train_rows,
        validation_values,
        checkpoints,
        frozen_rows,
        membership,
        runtime,
        assets,
        train_durations,
        validation_durations,
        checkpoint_durations,
        loaded,
        train_open,
        validation_open,
    )


def _initialise_streams(torch, stack):
    random.seed(contract.PILOT_SEED)
    torch.manual_seed(contract.PILOT_SEED)
    if getattr(stack, "cpu_stand_in", False) is not True:
        torch.cuda.manual_seed_all(contract.PILOT_SEED)
    permutation = torch.Generator(device="cpu")
    permutation.manual_seed(contract.PILOT_SEED)
    diffusion = torch.Generator(device="cpu")
    diffusion.manual_seed(contract.PILOT_SEED)
    cuda_state = stack.cuda_rng_state() if hasattr(stack, "cuda_rng_state") else torch.cuda.get_rng_state()
    return {
        "diffusion_generator": diffusion,
        "diffusion_initial": contract.state_entry_digest("diffusion", diffusion.get_state()),
        "permutation_generator": permutation,
        "permutation_initial": contract.state_entry_digest("permutation", permutation.get_state()),
        "python_initial": contract.python_rng_digest(random.getstate()),
        "torch_cpu_initial": contract.state_entry_digest("torch_cpu", torch.get_rng_state()),
        "read_cuda_rng": getattr(stack, "cpu_stand_in", False) is not True,
        "torch_cuda_initial": contract.state_entry_digest("torch_cuda", cuda_state),
        "torch_cuda_state": cuda_state,
    }


def _final_stream_digests(torch, rng):
    """Digest the final streams.

    The production path reads ``torch.cuda.get_rng_state`` and fails closed.
    The CPU stand-in keeps ``read_cuda_rng`` false and uses its explicit
    stand-in state. A failed production read is not replaced with that state.
    """
    if rng.get("read_cuda_rng") is True:
        try:
            cuda_state = torch.cuda.get_rng_state()
        except contract.M6PilotError:
            raise
        except Exception:
            raise contract.M6PilotError(
                "cuda_rng_final_observation_failed",
                "final CUDA RNG state could not be read",
                stage="rng_final_observation",
            )
    else:
        cuda_state = rng["torch_cuda_state"]
    return {
        "diffusion_final": contract.state_entry_digest("diffusion", rng["diffusion_generator"].get_state()),
        "permutation_final": contract.state_entry_digest("permutation", rng["permutation_generator"].get_state()),
        "python_final": contract.python_rng_digest(random.getstate()),
        "torch_cpu_final": contract.state_entry_digest("torch_cpu", torch.get_rng_state()),
        "torch_cuda_final": contract.state_entry_digest("torch_cuda", cuda_state),
    }


def _open_artifacts(authorisation, stack, artifact_path):
    logical = authorisation["validation_artifact_sha256"]
    expected = {
        "validation_draw_manifest.json": logical["draw_manifest"],
        "validation_draw_manifest_sha256.json": contract.VALIDATION_HASH_REPORT_SHA256,
        "validation_noise.float32": logical["noise"],
        "validation_order_artifact.csv": logical["order_artifact"],
        "validation_timesteps.int64": logical["timesteps"],
    }
    verified = contract.verify_artifact_directory(artifact_path, artifact_path, expected, stack.load_verified_artifacts)
    loaded = verified["loaded"]
    loaded["observed_files"] = verified["observed_files"]
    timesteps = loaded["timesteps"]
    noise = loaded["noise"]
    if tuple(getattr(timesteps, "shape", ())) != contract.VALIDATION_TIMESTEP_SHAPE:
        raise contract.M6PilotError("identity_mismatch", "loaded timestep shape drifted")
    if tuple(getattr(noise, "shape", ())) != contract.VALIDATION_NOISE_SHAPE:
        raise contract.M6PilotError("identity_mismatch", "loaded noise shape drifted")
    manifest = loaded.get("manifest")
    if not isinstance(manifest, dict) or manifest.get("validation_sequence_order_sha256") != logical["sequence_order"]:
        raise contract.M6PilotError("identity_mismatch", "logical sequence-order hash was not loaded from the artifact")
    loaded["observed_sequence_order_sha256"] = manifest["validation_sequence_order_sha256"]
    return loaded


def _validation_aggregate(stack, accelerator, denoiser, encdec, scheduler, sequences, loaded, tokenizer, torch, logical_device):
    """Evaluate the same prepared denoiser, then restore its training flag."""
    was_training = bool(denoiser.training)
    denoiser.eval()
    pair_losses = []
    try:
        with torch.no_grad():
            if torch.is_grad_enabled():
                raise contract.M6PilotError("identity_mismatch", "validation ran with gradients enabled")
            for index, sequence in enumerate(sequences):
                batch = stack.collate_sequences([{"index": 0, "sequence": sequence}], tokenizer)
                latent = stack.extract_latents(
                    encdec,
                    _place(stack, batch["input_ids"], logical_device),
                    _place(stack, batch["attention_mask"], logical_device),
                )
                for draw in range(contract.VALIDATION_DRAWS):
                    timestep = loaded["timesteps"][index, draw]
                    noise = loaded["noise"][index, draw]
                    if noise.dim() == latent.dim() - 1:
                        noise = noise.unsqueeze(0)
                    timestep = timestep.reshape(1)
                    device_type = "cuda" if getattr(latent, "is_cuda", False) else "cpu"
                    with torch.autocast(device_type=device_type, enabled=False):
                        if latent.dtype != torch.float32 or noise.dtype != torch.float32:
                            raise contract.M6PilotError("identity_mismatch", "validation latent or noise is not float32")
                        if timestep.dtype != torch.int64:
                            raise contract.M6PilotError("identity_mismatch", "validation timestep is not int64")
                        loss = stack.denoising_mse(denoiser, scheduler, latent, noise, timestep)
                        if loss.dtype != torch.float32:
                            raise contract.M6PilotError("identity_mismatch", "validation MSE is not float32")
                    pair_losses.append(float(loss.detach()))
    finally:
        denoiser.train(was_training)
    return contract.aggregate_pair_mse(pair_losses)


class _CheckpointStages(object):
    """Track the checkpoint substage and translate unexpected failures.

    A precise ``M6PilotError`` keeps its code and detail and gains the substage
    and update when it has none. Any other exception becomes
    ``checkpoint_save_reload_incompatibility`` with the exception class name only.
    The exception message, traceback, tensor values, and paths are not recorded.
    """

    def __init__(self, stack, update):
        self.stack = stack
        self.update = update
        self.current = "checkpoint"

    def enter(self, name):
        if name == self.current:
            return
        self.current = name
        _progress_stage(self.stack, name, update=self.update)

    def translate(self, exc):
        if isinstance(exc, contract.M6PilotError):
            if exc.stage is None:
                exc.stage = self.current
            if exc.update is None:
                exc.update = self.update
            return exc
        return contract.M6PilotError(
            "checkpoint_save_reload_incompatibility",
            "checkpoint operation failed; exception_class=" + _controlled_exception_class_name(exc),
            stage=self.current,
            update=self.update,
        )


def _save_and_reload(stack, model, scheduler, directory, update, training_object, implementation_commit):
    stages = _CheckpointStages(stack, update)
    try:
        stages.enter("checkpoint_directory")
        checkpoint_dir = os.path.join(directory, contract.checkpoint_child_name(update, implementation_commit))
        contract.create_checkpoint_directory_exclusive(checkpoint_dir, directory)
        stages.enter("checkpoint_save")
        stack.save_checkpoint(model, scheduler, checkpoint_dir)
        stages.enter("checkpoint_inventory")
        tree = contract.observe_checkpoint_tree(checkpoint_dir)
        stages.enter("checkpoint_hash")
        saved = {}
        for name in contract.CHECKPOINT_MEMBERS:
            saved[name] = contract.sha256_file(os.path.join(checkpoint_dir, name))
        stages.enter("checkpoint_reload")
        reloaded = stack.reload_denoiser(checkpoint_dir)
        if reloaded is training_object or id(reloaded) == id(training_object):
            raise contract.M6PilotError("checkpoint_save_reload_incompatibility", "reload reused the training object")
        original_state = model.state_dict()
        reloaded_state = reloaded.state_dict()
        stages.enter("checkpoint_inventory")
        if contract.observe_checkpoint_tree(checkpoint_dir) != tree:
            raise contract.M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint tree changed during hashing or reload")
        stages.enter("checkpoint_config_proof")
        proof = contract.prove_weight_reload(
            {
                "fresh_object_constructed": True,
                "labelled_as_resume": False,
                "original_config": _config_mapping(model),
                "original_object_id": id(training_object),
                "original_state": original_state,
                "reloaded_config": _config_mapping(reloaded),
                "reloaded_object_id": id(reloaded),
                "reloaded_state": reloaded_state,
                "saved_hashes": saved,
                "selection": "complete",
                "update": update,
            },
            stage_hook=stages.enter,
        )
    except Exception as exc:
        raise stages.translate(exc) from None
    proof["evidence_origin"] = "observed"
    return proof


def _config_mapping(module):
    config = module.config
    if hasattr(config, "to_dict"):
        mapping = config.to_dict()
    else:
        mapping = dict(config)
    return mapping


def _assemble_production_manifest(
    authorisation,
    directory,
    rng,
    rng_final,
    order,
    train_rows,
    validation_values,
    checkpoints,
    frozen_rows,
    membership,
    runtime,
    assets,
    train_durations,
    validation_durations,
    checkpoint_durations,
    loaded,
    train_open,
    validation_open,
):
    observations = []
    skeleton_observations = []
    for update in contract.VALIDATION_UPDATES:
        relative = None
        if update != 0:
            relative = contract.classify_validation_change(validation_values[0], validation_values[update], update)
        skeleton = {
            "aggregate_mse": contract.format_decimal(validation_values[update]),
            "pair_count": contract.VALIDATION_PAIR_COUNT,
            "relative_to_update_0": relative,
            "tensors_loaded": True,
            "tensors_regenerated": False,
            "update": update,
            "weight_variant": "raw",
        }
        skeleton_observations.append(skeleton)
        observed = dict(skeleton)
        observed["evidence_origin"] = "observed"
        observations.append(observed)
    training_total = 0.0
    for duration in train_durations:
        training_total += duration
    validation_total = 0.0
    for item in validation_durations:
        validation_total += item["seconds"]
    manifest = contract.build_control_flow_manifest(
        {
            "opened_biological_data": False,
            "peak_allocated_bytes": 0,
            "peak_reserved_bytes": 0,
            "train_permutation_digest": contract.permutation_digest(order),
            "train_updates": [
                {
                    "applied_norm": float(row["applied_clip_norm"]),
                    "clipped": row["clipped"],
                    "learning_rate": float(row["learning_rate"]),
                    "pre_clip_gradient_norm": float(row["pre_clip_gradient_norm"]),
                    "training_loss": float(row["training_loss"]),
                    "update": row["update"],
                }
                for row in train_rows
            ],
            "training_seconds": training_total,
            "validation_observations": skeleton_observations,
            "validation_review_observations": [
                contract.classify_validation_change(validation_values[0], validation_values[update], update) for update in (7, 14, 21)
            ],
            "validation_seconds": validation_total,
            "weight_checkpoints": checkpoints,
        }
    )
    manifest["completion_state"] = "pilot_completed"
    manifest["production_identities"] = True
    manifest["failure_state"] = None
    manifest["warnings"] = []
    manifest["run_id"] = authorisation["authorisation_id"]
    manifest["deviations"] = [{"id": item} for item in contract.DOCUMENTED_DEVIATIONS]
    manifest["applied_learning_rate_trace"] = [contract.format_decimal(value) for value in contract.applied_learning_rate_trace()]
    manifest["post_update_21_scheduler_position"] = {
        "applied_to_optimizer": False,
        "multiplier": "0",
        "position": contract.POST_UPDATE_POSITION,
        "pytorch_scheduler_last_epoch": None,
        "role": "next_unapplied_schedule_position",
    }
    manifest["authorisation"] = {
        "authorisation_id": authorisation["authorisation_id"],
        "authorization_commit": authorisation["authorization_commit"],
        "authorization_parent_commit": authorisation["authorization_parent_commit"],
        "consumption_state": "consumed_successfully",
        "evidence_origin": "observed",
        "executing_implementation_commit": authorisation["executing_implementation_commit"],
        "reuse_permitted": False,
        "single_use": True,
    }
    manifest["train_update_observations"] = train_rows
    manifest["validation_observations"] = observations
    manifest["denoiser_update_evidence"]["evidence_origin"] = "observed"
    probe = authorisation["gpu_probe"]
    manifest["gpu"] = {
        "cuda_visible_devices": probe["cuda_visible_devices"],
        "evidence_origin": "observed",
        "hardcoded_physical_index": False,
        "logical_device": probe["logical_device"],
        "pci_bus": probe["pci_bus"],
        "physical_index": probe["physical_index"],
        "uuid": probe["uuid"],
    }
    weights = assets["b1_unet_weights"]
    manifest["b1_identity"] = {
        "copied_at_update_0": False,
        "evidence_origin": "observed",
        "initialization": "immutable_B1_generic_diffusion_checkpoint",
        "observed_assets": assets,
        "unet_config_sha256": assets["b1_unet_config"]["sha256"],
        "weight_bytes": weights["byte_size"],
        "weight_sha256": weights["sha256"],
    }
    manifest["data_roles"] = _production_roles(authorisation, train_open, validation_open, loaded["observed_files"])
    m5 = contract.m5_contract()
    caches = {}
    for key in m5.runtime_isolation_paths(directory):
        caches[key] = os.environ.get(key)
    manifest["environment"] = {
        "accelerate_version": runtime["accelerate"],
        "bytecode_disabled": os.environ.get("PYTHONDONTWRITEBYTECODE") == "1",
        "cache_isolation": caches,
        "datasets_offline": os.environ.get("HF_DATASETS_OFFLINE") == "1",
        "diffusers_version": runtime["diffusers"],
        "evidence_origin": "observed",
        "executable": runtime["executable"],
        "expected_python": m5.ACCEPTED_RUNTIME_VERSIONS["python"],
        "expected_versions": {key: value for key, value in m5.ACCEPTED_RUNTIME_VERSIONS.items()},
        "hub_offline": os.environ.get("HF_HUB_OFFLINE") == "1",
        "numpy_called_by_pilot": False,
        "numpy_used_by_pinned_artifact_loader": True,
        "package_versions_observed": runtime,
        "pinned_python": m5.PINNED_PYTHON,
        "python_version": runtime["python"],
        "runtime_isolation_verified": True,
        "torch_version": runtime["torch"],
        "transformers_offline": os.environ.get("TRANSFORMERS_OFFLINE") == "1",
        "transformers_version": runtime["transformers"],
    }
    manifest["optimizer"]["evidence_origin"] = "observed"
    manifest["optimizer"]["mixed_precision"] = "no"
    manifest["optimizer"]["precision"] = "fp32"
    manifest["rng"] = {
        "diffusion_generator_final_digest": rng_final["diffusion_final"],
        "diffusion_generator_initial_digest": rng["diffusion_initial"],
        "diffusion_stream": "dedicated_cpu_diffusion_generator",
        "numpy_called_by_pilot": False,
        "permutation_generator_final_digest": rng_final["permutation_final"],
        "permutation_generator_initial_digest": rng["permutation_initial"],
        "permutation_stream": "dedicated_cpu_train_permutation_generator",
        "python_rng_final_digest": rng_final["python_final"],
        "python_rng_initial_digest": rng["python_initial"],
        "streams_are_distinct": rng_final["permutation_final"] != rng_final["diffusion_final"],
        "torch_cpu_final_digest": rng_final["torch_cpu_final"],
        "torch_cpu_initial_digest": rng["torch_cpu_initial"],
        "torch_cuda_final_digest": rng_final["torch_cuda_final"],
        "torch_cuda_initial_digest": rng["torch_cuda_initial"],
        "train_permutation_digest": contract.permutation_digest(order),
        "train_permutation_seed": contract.PILOT_SEED,
        "validation_artifacts_regenerated": False,
        "validation_draw_seed": contract.VALIDATION_DRAW_SEED,
    }
    observed_repository = dict(authorisation["repository_observation"])
    manifest["repository"] = {
        "authorization_commit": authorisation["authorization_commit"],
        "evidence_origin": "observed",
        "executing_implementation_commit": authorisation["executing_implementation_commit"],
        "mres_index_clean": observed_repository["mres_index_clean"],
        "mres_tracked_clean": observed_repository["mres_tracked_clean"],
        "mres_untracked_clean": observed_repository["mres_untracked_clean"],
        "rnagenesis_branch": observed_repository["rnagenesis_branch"],
        "rnagenesis_commit": observed_repository["rnagenesis_commit"],
        "rnagenesis_tracked_clean": observed_repository["rnagenesis_tracked_clean"],
        "rnagenesis_untracked_preserved": observed_repository["rnagenesis_untracked_preserved"],
    }
    manifest["memory"] = {
        "evidence_origin": "observed",
        "peak_allocated_bytes": int(torch_memory("allocated")),
        "peak_reserved_bytes": int(torch_memory("reserved")),
    }
    manifest["timing"] = {
        "checkpoint_save_reload_seconds": [
            {"seconds": contract.format_decimal(item["seconds"]), "update": item["update"]} for item in checkpoint_durations
        ],
        "checkpoint_time_excluded_from_training_and_validation": True,
        "evidence_origin": "observed",
        "synchronization": "cuda_synchronize_before_and_after_each_region",
        "training_seconds": contract.format_decimal(training_total),
        "training_update_seconds": [contract.format_decimal(item) for item in train_durations],
        "validation_excluded_from_training_updates": True,
        "validation_seconds": contract.format_decimal(validation_total),
        "validation_update_seconds": [
            {"seconds": contract.format_decimal(item["seconds"]), "update": item["update"]} for item in validation_durations
        ],
    }
    files = loaded["observed_files"]
    manifest["validation_artifacts"] = {
        "draw_manifest_sha256": files["validation_draw_manifest.json"]["sha256"],
        "draws": contract.VALIDATION_DRAWS,
        "evidence_origin": "observed",
        "hash_report_sha256": files["validation_draw_manifest_sha256.json"]["sha256"],
        "noise_sha256": files["validation_noise.float32"]["sha256"],
        "noise_shape": list(contract.VALIDATION_NOISE_SHAPE),
        "observation_method": "streamed_sha256",
        "observed_files": files,
        "order_artifact_sha256": files["validation_order_artifact.csv"]["sha256"],
        "sequence_count": contract.VALIDATION_SEQUENCE_COUNT,
        "sequence_order_sha256": loaded["observed_sequence_order_sha256"],
        "sequence_order_source": "loaded_manifest",
        "timestep_sha256": files["validation_timesteps.int64"]["sha256"],
        "timestep_shape": list(contract.VALIDATION_TIMESTEP_SHAPE),
        "validation_csv_sha256": validation_open["sha256"],
    }
    final_rotary = frozen_rows[21]["rotary_cache_names"]
    manifest["frozen_state"] = {
        "all_frozen": True,
        "components": list(contract.ENCDEC_COMPONENTS),
        "encdec_buffers_absent_from_optimizer": membership["encdec_buffers_absent_from_optimizer"],
        "encdec_eval_mode": membership["encdec_eval_mode"],
        "encdec_parameters_absent_from_optimizer": membership["encdec_parameters_absent_from_optimizer"],
        "encdec_parameter_digest_after_update_14": frozen_rows[14]["parameter_digest"],
        "encdec_parameter_digest_after_update_21": frozen_rows[21]["parameter_digest"],
        "encdec_parameter_digest_after_update_7": frozen_rows[7]["parameter_digest"],
        "encdec_parameter_digest_at_initialization": frozen_rows[0]["parameter_digest"],
        "encdec_persistent_buffer_digest_after_update_14": frozen_rows[14]["persistent_buffer_digest"],
        "encdec_persistent_buffer_digest_after_update_21": frozen_rows[21]["persistent_buffer_digest"],
        "encdec_persistent_buffer_digest_after_update_7": frozen_rows[7]["persistent_buffer_digest"],
        "encdec_persistent_buffer_digest_at_initialization": frozen_rows[0]["persistent_buffer_digest"],
        "encdec_requires_grad_false": membership["encdec_requires_grad_false"],
        "evidence_origin": "observed",
        "optimizer_contains_encdec": False,
        "optimizer_contains_only_denoiser": membership["optimizer_contains_only_denoiser"],
        "optimizer_parameter_ids_equal_trainable_denoiser": membership["optimizer_parameter_ids_equal_trainable_denoiser"],
        "rotary_cache_names": list(final_rotary),
        "rotary_caches_excluded_from_persistent_buffer_digest": True,
    }
    return manifest


def torch_memory(kind):
    if os.environ.get("CUDA_VISIBLE_DEVICES", None) == "":
        return 0
    torch = importlib.import_module("torch")
    if not torch.cuda.is_available():
        return 0
    if kind == "allocated":
        return torch.cuda.max_memory_allocated()
    return torch.cuda.max_memory_reserved()


def _production_roles(authorisation, train_open, validation_open, artifact_files):
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

    observed_hashes = {name: record["sha256"] for name, record in artifact_files.items()}
    artifact_bytes = 0
    for record in artifact_files.values():
        artifact_bytes += int(record["byte_size"])
    return {
        "eval": role("EVAL", None, contract.EVAL_HASH_METADATA, None, False, None, 0, None, "not_opened"),
        "ref": role("REF", None, contract.REF_HASH_METADATA, None, False, None, 0, None, "not_opened"),
        "train_text": role(
            "TRAIN_TEXT",
            train_open["path"],
            train_open["expected_sha256"],
            train_open["expected_count"],
            True,
            train_open["sha256"],
            train_open["count"],
            train_open["byte_size"],
            train_open["observation_method"],
        ),
        "validation_artifacts": role(
            "VALIDATION_ARTIFACT",
            authorisation["validation_artifact_directory"],
            observed_hashes,
            len(artifact_files),
            True,
            observed_hashes,
            len(artifact_files),
            artifact_bytes,
            "streamed_sha256",
        ),
        "validation_csv": role(
            "VALIDATION_CSV",
            validation_open["path"],
            validation_open["expected_sha256"],
            validation_open["expected_count"],
            True,
            validation_open["sha256"],
            validation_open["count"],
            validation_open["byte_size"],
            validation_open["observation_method"],
        ),
    }



def _require_synthetic(backend):
    _reject_environment(os.environ)
    if getattr(backend, "mode", None) != "synthetic-cpu-test":
        raise contract.M6PilotError("execution_not_authorised", "production execution is closed")
    if getattr(backend, "opens_biological_files", True) is not False:
        raise contract.M6PilotError("unexpected_biological_path_or_role", "synthetic backend must not open biological files")


def _validation_observation(update, aggregate, initial):
    relative = None
    if update != 0:
        relative = contract.classify_validation_change(initial, aggregate, update)
    return {
        "aggregate_mse": contract.format_decimal(aggregate),
        "pair_count": contract.VALIDATION_PAIR_COUNT,
        "relative_to_update_0": relative,
        "tensors_loaded": True,
        "tensors_regenerated": False,
        "update": update,
        "weight_variant": "raw",
    }


def _run_control_flow(backend):
    _require_synthetic(backend)
    arithmetic = contract.assert_pilot_arithmetic()
    events = []
    indices = backend.cpu_permutation(contract.TRAIN_RECORD_COUNT, contract.PILOT_SEED)
    digest = contract.permutation_digest(indices)
    events.append(("permutation", digest))
    contract.assert_encdec_frozen(backend.encdec_snapshot())
    contract.assert_optimizer_membership(backend.optimizer_membership())
    contract.assert_validation_source(backend.validation_source())
    if backend.validation_source().get("regenerated") is not False:
        raise contract.M6PilotError("identity_mismatch", "validation tensors were regenerated")

    def validate(update):
        contract.validation_updates_for(update)
        aggregate = contract.aggregate_pair_mse(backend.validation_pair_batches(update))
        events.append(("validation", update))
        return aggregate

    aggregates = {0: validate(0)}
    train_updates = []
    checkpoints = []
    microbatch_total = 0
    windows = contract.accumulation_windows()
    for update, window in enumerate(windows, start=1):
        learning_rate = contract.applied_learning_rate(update)
        events.append(("learning_rate_recorded", update, learning_rate))
        scales = contract.applied_float_scales(window)
        before = backend.denoiser_digest(update, "before")
        window_loss = 0.0
        for micro_index, (size, scale) in enumerate(zip(window, scales)):
            loss = contract.assert_finite_training_loss(backend.training_loss(update, micro_index, size))
            window_loss += loss * scale
            events.append(("microbatch_backward", update, size, scale, loss))
            microbatch_total += 1
        contract.assert_finite_training_loss(window_loss)
        contract.assert_finite_gradients(backend.gradients_finite(update))
        clip = contract.clip_pre_clip_norm(backend.pre_clip_gradient_norm(update))
        events.append(("gradient_clipped", update, clip["clipped"], clip["abort"]))
        events.append(("optimizer_step", update))
        after = backend.denoiser_digest(update, "after")
        contract.assert_denoiser_changed(before, after, learning_rate)
        contract.assert_encdec_frozen(backend.encdec_snapshot())
        train_updates.append(
            {
                "update": update,
                "learning_rate": learning_rate,
                "training_loss": window_loss,
                "pre_clip_gradient_norm": clip["pre_clip_gradient_norm"],
                "applied_norm": clip["applied_norm"],
                "clipped": clip["clipped"],
            }
        )
        if update in contract.RETAINED_WEIGHT_UPDATES:
            contract.refuse_existing_checkpoint_directory(backend.checkpoint_exists(update))
            checkpoints.append(contract.prove_weight_reload(backend.checkpoint_proof(update)))
            events.append(("checkpoint_saved", update))
        if update in contract.VALIDATION_UPDATES:
            aggregates[update] = validate(update)
    if microbatch_total != arithmetic["microbatches"] or len(train_updates) != contract.OPTIMIZER_UPDATES:
        raise contract.M6PilotError("microbatch_arithmetic_invalid", "the control flow did not run 84 microbatches and 21 updates")
    if [event[1] for event in events if event[0] == "validation"] != list(contract.VALIDATION_UPDATES):
        raise contract.M6PilotError("validation_schedule_invalid", "validation was not limited to updates 0, 7, 14, and 21")
    observations = [_validation_observation(update, aggregates[update], aggregates[0]) for update in contract.VALIDATION_UPDATES]
    review = [contract.classify_validation_change(aggregates[0], aggregates[update], update) for update in (7, 14, 21)]
    memory = backend.memory()
    timing = backend.timing()
    manifest = contract.build_control_flow_manifest(
        {
            "opened_biological_data": False,
            "train_updates": train_updates,
            "train_permutation_digest": digest,
            "peak_allocated_bytes": memory["peak_allocated_bytes"],
            "peak_reserved_bytes": memory["peak_reserved_bytes"],
            "training_seconds": timing["training_seconds"],
            "validation_seconds": timing["validation_seconds"],
            "validation_observations": observations,
            "validation_review_observations": review,
            "weight_checkpoints": checkpoints,
        }
    )
    if manifest["completion_state"] == "pilot_completed" or manifest["resume_supported"] is not False:
        raise contract.M6PilotError("execution_not_authorised", "synthetic control flow must not claim a completed resumable pilot")
    events.append(("manifest_published",))
    backend.recorded_manifest = manifest
    backend.recorded_failure = None
    return {"events": events, "manifest": manifest, "failure": None}


def run_synthetic_control_flow(backend):
    """CPU/mock control flow. Failures publish no success manifest."""
    try:
        return _run_control_flow(backend)
    except contract.M6PilotError as exc:
        failure = {
            "detail": exc.detail,
            "failure_code": exc.code,
            "manifest_written": False,
            "resume_supported": False,
            "scientific_run_completed": False,
        }
        backend.recorded_failure = failure
        backend.recorded_manifest = None
        raise


def main(argv=None):
    try:
        return production_main(argv)
    except contract.M6PilotError as exc:
        sys.stderr.write(exc.code + ": " + exc.detail + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
