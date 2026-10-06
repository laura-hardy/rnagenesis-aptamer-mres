#!/usr/bin/env python3
"""M7 replicate runner (inactive).

The checked-in entry point accepts ``--help`` and ``--schema`` and nothing
else. It does not read the configuration, open a path, or import torch,
Accelerate, Diffusers or RNAGenesis. The launcher, the worker and the
five-epoch loop below are the machinery a later authorisation-only package will
wire up. They are exercised here only with CPU stand-ins and mocks.

A later launcher accepts one authorisation id. It resolves that id to one
entry, validates it, checks free space, consumes that entry's own output
directory, builds a strict allow-listed child environment, and starts one worker
subprocess for one seed. A seed is a process: the worker refuses to run a
second replicate, so no model, optimizer, scheduler or RNG state crosses seeds.

After consumption every ``BaseException`` (including ``KeyboardInterrupt`` and
``SystemExit``) becomes a message-safe failure record holding the seed, epoch,
update, substage, candidate, and partial-checkpoint state. If that record cannot
be written the original error is kept and the secondary failure is reported.
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import subprocess
import sys
import time

MRES_ROOT = "/home/laura/rnagenesis-aptamer-mres"


def _load_sibling(name, relative):
    path = os.path.join(MRES_ROOT, relative)
    existing = sys.modules.get(name)
    if existing is not None and os.path.realpath(getattr(existing, "__file__", "")) == os.path.realpath(path):
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


common = _load_sibling("m7_common", "scripts/modelling/m7_common.py")
contract = _load_sibling("m7_replicate_contract", "scripts/modelling/m7_replicate_contract.py")
M7Error = common.M7Error
# The accepted M6 runner is loaded by its tracked path and reused unchanged. Its
# private contract copy is replaced by the shared one, so both modules raise one
# error class and read one set of constants. The tracked file is not modified.
m6r = _load_sibling("m6_pilot_runner_for_m7", common.M6_RUNNER_RELATIVE)
m6r.contract = common.m6_contract()
m6 = common.m6_contract()

CONFIG_PATH = os.path.join(MRES_ROOT, contract.CONFIG_RELATIVE)
HELP_TEXT = """\
M7 final D1 replicate runner (inactive).

The checked-in configuration is not executable. This entry point accepts
--help, --schema and --authorisation-id <id>. The last reads only the tracked
configuration and refuses (execution_not_authorised) while it is inactive,
before any directory is created or any data, asset or weight is touched. It
accepts no seed, path, data, model, GPU, learning rate, environment or output
argument. A later authorisation-only commit that activates one entry launches
exactly that entry's seed through this same path.
"""
_PROCESS_CLAIM = {"seed": None}
_WORKER_BOOTSTRAP = """
import importlib.util
import sys
spec = importlib.util.spec_from_file_location("m7_worker", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules["m7_worker"] = module
spec.loader.exec_module(module)
module.worker_main(sys.argv[2], sys.argv[3])
"""


# ------------------------------------------------------------------ entry point


def schema_document():
    """Static schema inspection. No file is read and nothing is imported."""
    return {
        "authorisation_schema": contract.authorisation_schema(),
        "document_status": contract.DOCUMENT_STATUS,
        "entry_keys": list(contract.ACTIVE_ENTRY_KEYS),
        "failure_record_keys": list(common.FAILURE_KEYS),
        "manifest_keys": list(contract.MANIFEST_KEYS),
        "manifest_schema_version": contract.MANIFEST_SCHEMA_VERSION,
        "schema_version": contract.SCHEMA_VERSION,
    }


def production_main(argv=None, stdout=None):
    stdout = sys.stdout if stdout is None else stdout
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--help"], ["-h"]):
        stdout.write(HELP_TEXT)
        return 0
    if arguments == ["--schema"]:
        stdout.write(common.canonical_json(schema_document()).decode("utf-8"))
        return 0
    if len(arguments) == 2 and arguments[0] == "--authorisation-id":
        authorisation_id = contract.parse_launcher_argv(arguments)
        launch_authorised_entry(authorisation_id)
        return 0
    raise M7Error("cli_argument_rejected", "the entry point accepts only --help, --schema and --authorisation-id <id>")


def main(argv=None):
    try:
        return production_main(argv)
    except M7Error as exc:
        common.print_error(exc)
        return 2 if exc.code in ("cli_argument_rejected", "execution_not_authorised") else 1


# ------------------------------------------------------------------ process claim


def claim_process_for_seed(seed):
    """One process runs one replicate. A second claim is a cross-seed state hazard."""
    contract.assert_seed(seed)
    if _PROCESS_CLAIM["seed"] is not None:
        raise M7Error("cross_seed_state", "this process already ran a replicate; each seed needs its own process")
    _PROCESS_CLAIM["seed"] = seed
    return seed


def reset_process_claim_for_tests():
    _PROCESS_CLAIM["seed"] = None


# ------------------------------------------------------------------ pinned stack


class PinnedReplicateStack(m6r.PinnedTrainingStack):
    """The accepted M6 call surface plus the runtime GPU identity read."""

    def observe_gpu_identity(self):
        torch = self.torch()
        if torch.cuda.is_available() is not True:
            raise M7Error("identity_mismatch", "the authorised worker requires the bound CUDA device")
        count = int(torch.cuda.device_count())
        if count != 1 or int(torch.cuda.current_device()) != 0:
            raise M7Error("identity_mismatch", "the worker must see exactly one CUDA device as logical cuda:0")
        probe = common.live_gpu_probe()
        return {
            "cuda_visible_devices": probe["cuda_visible_devices"],
            "device_count": count,
            "logical_device": common.LOGICAL_CUDA_DEVICE,
            "pci_bus": probe["pci_bus"],
            "physical_index": probe["physical_index"],
            "source": "nvidia_smi_physical_index",
            "uuid": probe["uuid"],
        }


def import_pinned_training_stack():
    """Import RNAGenesis only after the gate and isolation, from the pinned directory."""
    m6r.assert_production_worker_directory()
    root = common.RNAGENESIS_ROOT
    encoder = os.path.join(root, "models", "autoencoder", "encoder")
    for path in (root, encoder):
        if path not in sys.path:
            sys.path.insert(0, path)
    import importlib

    trainer = importlib.import_module("train_diffusion_mres")
    artifacts = m6r.load_artifact_loader()
    accelerate = importlib.import_module("accelerate")
    return PinnedReplicateStack(trainer, artifacts, accelerate)


# ------------------------------------------------------------------ repository observation


def _git(repo, args):
    """``git`` through the fixed absolute executable and environment, never by name."""
    return common.run_git(repo, args)


def _sha256_file(path):
    return common.stream_sha256(path)


def live_repository_observation(config, entry):
    """Stdlib repository, path and GPU observation. It imports no training stack."""
    head = _git(common.MRES_ROOT, ["rev-parse", "HEAD"]).strip()
    parents = [line.strip() for line in _git(common.MRES_ROOT, ["rev-parse", "HEAD^@"]).splitlines() if line.strip()]
    parent = parents[0]
    implementation_raw = common.run_git_bytes(common.MRES_ROOT, ["show", parent + ":" + contract.CONFIG_RELATIVE])
    changed = [line.strip() for line in _git(common.MRES_ROOT, ["diff", "--name-only", parent, "HEAD"]).splitlines() if line.strip()]
    parent_hashes = {}
    working_hashes = {}
    for relative in contract.IMPLEMENTATION_FILE_PATHS:
        blob = common.run_git_bytes(common.MRES_ROOT, ["show", parent + ":" + relative])
        parent_hashes[relative] = common.sha256_bytes(blob)
        working_hashes[relative] = _sha256_file(os.path.join(common.MRES_ROOT, relative))
    output = entry["output_directory"]
    return {
        "changed_files": changed,
        "component_symlink": _component_is_symlink(os.path.dirname(output)),
        "file_sha256_at_parent": parent_hashes,
        "file_sha256_working_tree": working_hashes,
        "gpu_probe": common.live_gpu_probe(),
        "implementation_config": common.load_config_bytes(implementation_raw),
        "implementation_config_bytes": implementation_raw,
        "mres_branch": _git(common.MRES_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"]).strip(),
        "mres_head": head,
        "mres_origin_main": _git(common.MRES_ROOT, ["rev-parse", "origin/main"]).strip(),
        "mres_parents": parents,
        "mres_porcelain": _git(common.MRES_ROOT, ["status", "--porcelain=v1", "--untracked-files=all"]),
        "output_exists": os.path.lexists(output),
        "output_symlink": os.path.islink(output),
        "rnagenesis_branch": _git(common.RNAGENESIS_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"]).strip(),
        "rnagenesis_directory_porcelain": _git(common.RNAGENESIS_ROOT, ["status", "--porcelain=v1"]),
        "rnagenesis_file_porcelain": _git(common.RNAGENESIS_ROOT, ["status", "--porcelain=v1", "--untracked-files=all"]),
        "rnagenesis_head": _git(common.RNAGENESIS_ROOT, ["rev-parse", "HEAD"]).strip(),
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


# ------------------------------------------------------------------ authorised launcher and entry point


def _binding(entry):
    return {
        "authorisation_id": entry["authorisation_id"],
        "authorization_commit": entry["authorization_commit"],
        "authorization_parent_commit": entry["authorization_parent_commit"],
        "executing_implementation_commit": entry["executing_implementation_commit"],
        "interpreter": dict(entry["interpreter"]),
        "ld_library_path_sha256": None if entry["ld_library_path"] is None else common.ld_library_path_digest(entry["ld_library_path"]),
        "seed": entry["seed"],
    }


def _context(entry):
    return {
        "authorisation_id": entry["authorisation_id"],
        "authorization_commit": entry["authorization_commit"],
        "authorization_parent_commit": entry["authorization_parent_commit"],
        "executing_implementation_commit": entry["executing_implementation_commit"],
        "output_directory": entry["output_directory"],
    }


def _default_spawn(argv, env, cwd):
    return subprocess.run(argv, cwd=cwd, env=env, check=False, shell=False)


def _error_from_preserved_failure(directory):
    path = os.path.join(directory, common.FAILURE_RECORD_NAME)
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as handle:
            parsed = json.loads(handle.read().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict) or parsed.get("code") not in common.FAILURE_CODES:
        return None
    detail = parsed.get("detail")
    if not isinstance(detail, str) or detail == "":
        detail = "worker failure record preserved"
    return M7Error(
        parsed["code"],
        detail,
        stage=parsed.get("stage"),
        seed=parsed.get("seed"),
        epoch=parsed.get("epoch"),
        update=parsed.get("update"),
        microbatch=parsed.get("microbatch"),
        candidate=parsed.get("candidate"),
    )


def require_worker_success_manifest(directory, entry):
    """Reopen the child's claimed success and accept only a validated canonical manifest."""
    if os.path.lexists(os.path.join(directory, common.FAILURE_RECORD_NAME)):
        raise M7Error("incomplete_evidence_or_manifest", "worker claimed success while a failure record exists", stage="worker_success_verification")
    path = os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)
    if os.path.islink(path) or not os.path.isfile(path):
        raise M7Error("incomplete_evidence_or_manifest", "worker exited without a regular success manifest", stage="worker_success_verification")
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise M7Error("incomplete_evidence_or_manifest", "worker success manifest is not valid JSON", stage="worker_success_verification")
    if not isinstance(parsed, dict) or common.canonical_json(parsed) != raw:
        raise M7Error("incomplete_evidence_or_manifest", "worker success manifest is not canonical JSON", stage="worker_success_verification")
    contract.validate_replicate_manifest(parsed, _binding(entry))
    return parsed


def _fail_consumed(directory, exc, entry, progress):
    """Record the failure for any ``BaseException`` and re-raise it, interrupts unchanged."""
    error = common.record_consumed_failure(directory, exc, _context(entry), progress, contract.SUCCESS_MANIFEST_NAME)
    preserved = _error_from_preserved_failure(directory)
    if preserved is not None and error.secondary_failure is None:
        error = preserved
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        raise exc
    raise error from None


def launch_authorised_entry(
    authorisation_id,
    run_root=None,
    spawn=None,
    asset_observer=None,
    python_observer=None,
    environ=None,
    config_bytes=None,
    observation=None,
    statvfs=None,
    interpreter_observer=None,
):
    """Resolve one authorisation id, consume that entry, and start its worker.

    The id is the only input. The seed, paths, GPU, interpreter and every
    scientific parameter come from the validated entry. With the checked-in
    inactive configuration this refuses with ``execution_not_authorised`` after
    reading only the tracked configuration file: no directory is created, the
    environment, git, a GPU, an interpreter, an asset or a weight is not
    touched. For an active entry the order is: exact schema, one entry, the
    repository (branch, clean tree and index, remote, single parent, permitted
    changed file, file hashes), the GPU identity, the output path and its
    ancestry, free space, ``LD_LIBRARY_PATH``, the pinned interpreter, the
    assets, and only then consumption of that one entry.
    """
    contract.parse_launcher_argv(["--authorisation-id", authorisation_id])
    parent = os.environ if environ is None else environ
    if config_bytes is None:
        with open(CONFIG_PATH, "rb") as handle:
            config_bytes = handle.read()
    config = common.load_config_bytes(config_bytes)
    kind = contract.classify_configuration(config)
    if kind == "inactive":
        contract.assert_inactive_text(config_bytes.decode("utf-8"))
        contract.reject_inactive_before_execution(config)
    common.assert_parent_environment(dict(parent))
    common.pin_process_path(parent)
    root = common.RUN_ROOT if run_root is None else run_root
    entries = contract.assert_active_configuration(config, root)
    selected = contract.find_entry(entries, authorisation_id)
    if observation is None:
        observation = live_repository_observation(config, selected)
    entry = contract.validate_active_execution(config, authorisation_id, observation, root)
    common.assert_free_space(os.path.dirname(entry["output_directory"]), contract.EPOCHS, statvfs=statvfs)
    # The inherited CUDA selection, LD_LIBRARY_PATH and interpreter must match the authorisation before the entry is consumed.
    common.assert_parent_environment(dict(parent), entry["physical_gpu_index"])
    common.resolve_ld_library_path(parent, entry["ld_library_path"])
    common.assert_interpreter_matches((interpreter_observer or common.observe_interpreter)(common.PINNED_PYTHON), entry["interpreter"])
    (asset_observer or m6.observe_required_assets)()
    (python_observer or (lambda: m6.assert_pinned_python_file(m6.m5_contract().PINNED_PYTHON)))()
    progress = common.new_progress(entry["seed"], "replicate")
    directory = None
    try:
        progress["stage"] = "consumption"
        directory = contract.consume_entry(entry, root)
        progress["stage"] = "worker_launch"
        common.create_isolated_directories(directory)
        env = common.build_child_environment(dict(parent), entry["physical_gpu_index"], directory, entry["ld_library_path"])
        argv = [
            entry["interpreter"]["path"],
            "-B",
            "-c",
            _WORKER_BOOTSTRAP,
            os.path.join(common.MRES_ROOT, contract.RUNNER_RELATIVE),
            directory,
            entry["authorisation_id"],
        ]
        common.assert_pinned_interpreter_argv(argv)
        completed = (spawn or _default_spawn)(argv, env, common.RNAGENESIS_ROOT)
        if getattr(completed, "returncode", 1) != 0:
            raise M7Error("incomplete_evidence_or_manifest", "worker exited without a passing manifest", stage="worker_launch")
        progress["stage"] = "worker_success_verification"
        require_worker_success_manifest(directory, entry)
        return directory
    except BaseException as exc:
        # A refusal before the directory was created (including an existing
        # directory from an earlier use) must not write into that directory.
        if directory is None and getattr(exc, "directory_created", False) is not True:
            raise
        _fail_consumed(entry["output_directory"], exc, entry, progress)


def worker_main(output_directory, authorisation_id, config_loader=None, observation_loader=None, stack_loader=None, started_at=None, interpreter_observer=None):
    """Child entry. The parent already consumed the directory and set the environment."""
    started = time.perf_counter() if started_at is None else started_at
    progress = common.new_progress(None, "replicate")
    progress["stage"] = "worker_isolation"
    entry = None
    try:
        common.assert_child_environment(os.environ, output_directory, ld_library_path_pending=True)
        progress["stage"] = "configuration_load"
        if config_loader is None:
            with open(CONFIG_PATH, "rb") as handle:
                config = common.load_config_bytes(handle.read())
        else:
            config = config_loader()
        entries = contract.assert_active_configuration(config, os.path.dirname(output_directory))
        selected = contract.find_entry(entries, authorisation_id)
        progress["seed"] = selected["seed"]
        progress["stage"] = "repository_observation"
        observation = (observation_loader or live_repository_observation)(config, selected)
        progress["stage"] = "consumed_authorisation"
        entry = contract.validate_active_execution(config, authorisation_id, observation, os.path.dirname(output_directory), consumed_worker=True)
        if entry["output_directory"] != output_directory:
            raise M7Error("authorization_reuse", "worker directory is not the bound output")
        common.observe_child_ld_library_path(os.environ, entry["ld_library_path"])
        progress["stage"] = "interpreter_identity"
        common.assert_interpreter_matches((interpreter_observer or common.observe_interpreter)(common.PINNED_PYTHON), entry["interpreter"])
        _require_consumption_record(output_directory, entry)
        claim_process_for_seed(entry["seed"])
        if stack_loader is None:
            progress["stage"] = "production_worker_directory"
            m6r.assert_production_worker_directory()
        progress["stage"] = "training_stack_import"
        try:
            stack = import_pinned_training_stack() if stack_loader is None else stack_loader(entry)
        except M7Error:
            raise
        except Exception:
            raise M7Error("training_stack_import_failed", "the pinned training stack could not be imported", stage="training_stack_import")
        progress["stage"] = "worker_start"
        manifest = run_authorised_replicate(entry, stack, output_directory, progress=progress, prelude_seconds=time.perf_counter() - started)
        contract.validate_replicate_manifest(manifest, _binding(entry))
        common.write_atomic_json(output_directory, contract.SUCCESS_MANIFEST_NAME, manifest)
        return manifest
    except BaseException as exc:
        context_entry = entry if entry is not None else {
            "authorisation_id": authorisation_id,
            "authorization_commit": None,
            "authorization_parent_commit": None,
            "executing_implementation_commit": None,
            "output_directory": output_directory,
        }
        _fail_consumed(output_directory, exc, context_entry, progress)


def _require_consumption_record(directory, entry):
    path = os.path.join(directory, common.CONSUMPTION_RECORD_NAME)
    if os.path.islink(path) or not os.path.isfile(path):
        raise M7Error("authorization_reuse", "consumption record is missing")
    with open(path, "rb") as handle:
        record = json.loads(handle.read().decode("utf-8"))
    for key in ("authorisation_id", "authorization_commit", "seed"):
        if record.get(key) != entry[key]:
            raise M7Error("authorization_reuse", "consumption record does not match the live authorisation")
    if record.get("reuse_permitted") is not False:
        raise M7Error("authorization_reuse", "consumption record permits reuse")
    return record


# ------------------------------------------------------------------ the five-epoch loop


def _stage(progress, name, epoch=None, update=None, microbatch=None, candidate=None):
    if progress is None:
        return
    progress["stage"] = name
    progress["epoch"] = epoch
    progress["update"] = update
    progress["microbatch"] = microbatch
    progress["candidate"] = candidate


def _place(stack, tensor, device):
    if hasattr(stack, "place"):
        return stack.place(tensor, device)
    return tensor.to(device)


def _cuda_device_count(stack, torch_module):
    if hasattr(stack, "cuda_device_count"):
        return int(stack.cuda_device_count())
    return int(torch_module.cuda.device_count())


def initial_state_digest(module):
    """Aggregate digest of the freshly loaded ``state_dict``: parameters and persistent buffers."""
    entry_digests = {}
    for name, value in module.state_dict().items():
        entry_digests[name] = m6.state_entry_digest(name, value.detach() if hasattr(value, "detach") else value)
    inventory = m6.state_inventory_digests(entry_digests)
    return {
        "initial_state_aggregate_digest": inventory["aggregate_digest"],
        "initial_state_entry_count": len(entry_digests),
        "initial_state_parameter_names_sha256": inventory["parameter_names_sha256"],
    }


def initialise_streams(torch, stack, seed):
    """Seed every stream from the training seed. Python, torch CPU and CUDA RNG are re-seeded per process."""
    contract.assert_seed(seed)
    random.seed(seed)
    torch.manual_seed(seed)
    if getattr(stack, "cpu_stand_in", False) is not True:
        torch.cuda.manual_seed_all(seed)
    permutation = torch.Generator(device="cpu")
    permutation.manual_seed(seed)
    diffusion = torch.Generator(device="cpu")
    diffusion.manual_seed(seed)
    cuda_state = stack.cuda_rng_state() if hasattr(stack, "cuda_rng_state") else torch.cuda.get_rng_state()
    return {
        "diffusion_generator": diffusion,
        "diffusion_initial": m6.state_entry_digest("diffusion", diffusion.get_state()),
        "permutation_generator": permutation,
        "permutation_initial": m6.state_entry_digest("permutation", permutation.get_state()),
        "python_initial": m6.python_rng_digest(random.getstate()),
        "read_cuda_rng": getattr(stack, "cpu_stand_in", False) is not True,
        "torch_cpu_initial": m6.state_entry_digest("torch_cpu", torch.get_rng_state()),
        "torch_cuda_initial": m6.state_entry_digest("torch_cuda", cuda_state),
        "torch_cuda_state": cuda_state,
    }


def final_stream_digests(torch, rng):
    """Final streams. A failed production CUDA read fails closed and never reuses the initial state."""
    if rng.get("read_cuda_rng") is True:
        try:
            cuda_state = torch.cuda.get_rng_state()
        except M7Error:
            raise
        except Exception:
            raise M7Error("cuda_rng_final_observation_failed", "final CUDA RNG state could not be read", stage="rng_final_observation")
    else:
        cuda_state = rng["torch_cuda_state"]
    return {
        "diffusion_final": m6.state_entry_digest("diffusion", rng["diffusion_generator"].get_state()),
        "permutation_final": m6.state_entry_digest("permutation", rng["permutation_generator"].get_state()),
        "python_final": m6.python_rng_digest(random.getstate()),
        "torch_cpu_final": m6.state_entry_digest("torch_cpu", torch.get_rng_state()),
        "torch_cuda_final": m6.state_entry_digest("torch_cuda", cuda_state),
    }


def _config_mapping(module):
    config = module.config
    return config.to_dict() if hasattr(config, "to_dict") else dict(config)


def save_and_prove_epoch(stack, denoiser, scheduler, directory, entry, epoch, progress):
    """Save one raw-weight checkpoint, reload it fresh, and prove the complete state equal.

    The checkpoint directory is an exclusive direct child of the bound output.
    The inventory is exact, symlink-safe, single-link and same-device. Members
    are hashed with bounded streaming digests and flushed. The tree signature
    must not change across hashing and reload. The weight hash may never equal
    a forbidden M6 checkpoint.
    """
    update = contract.epoch_update_range(epoch)[1]
    name = contract.checkpoint_child_name(entry["seed"], epoch, entry["executing_implementation_commit"])
    path = os.path.join(directory, name)
    partial = progress["partial_checkpoint"]
    current = ["checkpoint_directory"]

    def enter(substage):
        current[0] = substage
        _stage(progress, substage, epoch=epoch, update=update)

    try:
        enter("checkpoint_directory")
        common.assert_path_permitted(path, "OWN_OUTPUT", bound_output=directory)
        common.translate_m6(lambda: m6.assert_checkpoint_child(path, directory))
        os.mkdir(path)
        common.fsync_directory(directory)
        partial.update({"directory_name": name, "epoch": epoch, "state": "directory_created"})
        enter("checkpoint_save")
        stack.save_checkpoint(denoiser, scheduler, path)
        partial["state"] = "saved_unverified"
        enter("checkpoint_flush")
        common.fsync_checkpoint_tree(path)
        enter("checkpoint_inventory")
        tree = common.observe_checkpoint_tree_strict(path, directory)
        enter("checkpoint_hash")
        saved = {}
        for member in common.CHECKPOINT_MEMBERS:
            saved[member] = common.stream_sha256(os.path.join(path, member), require_single_link=True)
        common.assert_not_m6_weight(saved[common.WEIGHT_MEMBER])
        enter("checkpoint_reload")
        reloaded = stack.reload_denoiser(path)
        if reloaded is denoiser or id(reloaded) == id(denoiser):
            raise M7Error("checkpoint_save_reload_incompatibility", "reload reused the training object")
        original_state = denoiser.state_dict()
        reloaded_state = reloaded.state_dict()
        enter("checkpoint_inventory")
        if common.observe_checkpoint_tree_strict(path, directory) != tree:
            raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint tree changed during hashing or reload")
        enter("checkpoint_config_proof")
        proof = contract.prove_epoch_reload(
            {
                "directory_name": name,
                "epoch": epoch,
                "fresh_object_constructed": True,
                "inventory": {
                    "all_leaf_link_counts_one": True,
                    "all_regular_non_symlink_files": True,
                    "ancestry_symlink_free": True,
                    "member_count": len(common.CHECKPOINT_MEMBERS),
                    "same_device": True,
                    "tree_unchanged_across_hash_and_reload": True,
                },
                "labelled_as_resume": False,
                "original_config": _config_mapping(denoiser),
                "original_object_id": id(denoiser),
                "original_state": original_state,
                "reloaded_config": _config_mapping(reloaded),
                "reloaded_object_id": id(reloaded),
                "reloaded_state": reloaded_state,
                "saved_hashes": saved,
                "selection": "complete",
                "update": update,
            },
            stage_hook=enter,
        )
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        if isinstance(exc, M7Error):
            if exc.stage is None:
                exc.stage = current[0]
            if exc.epoch is None:
                exc.epoch = epoch
            if exc.update is None:
                exc.update = update
            if exc.seed is None:
                exc.seed = entry["seed"]
            raise
        error = M7Error(
            "checkpoint_save_reload_incompatibility",
            "checkpoint operation failed; exception_class=" + common.controlled_exception_class_name(exc),
            stage=current[0],
            seed=entry["seed"],
            epoch=epoch,
            update=update,
        )
        raise error from None
    partial["state"] = "verified"
    progress["retained_checkpoint_epochs"].append(epoch)
    return proof


def _production_data_roles(entry, train_open, validation_open, artifact_files):
    return m6r._production_roles(entry, train_open, validation_open, artifact_files)


def run_authorised_replicate(entry, stack, directory, progress=None, prelude_seconds=0.0):
    """One non-resumable replicate for one seed. Identity is closed before any biological open.

    ``prelude_seconds`` is the worker time spent before this call (configuration,
    repository observation, stack import). The end-to-end time is that plus the
    synchronized span of this call, so one measured number covers a whole seed.
    """
    seed = contract.assert_seed(entry["seed"])
    progress = common.new_progress(seed, "replicate") if progress is None else progress
    progress["seed"] = seed
    _stage(progress, "runtime_identity")
    torch = stack.torch()
    clock = stack.clock() if hasattr(stack, "clock") else m6r.SynchronizedClock(torch)
    first_stamp = clock.stamp()
    stand_in = getattr(stack, "cpu_stand_in", False) is True
    if not stand_in and torch.cuda.is_available() is not True:
        raise M7Error("identity_mismatch", "the authorised worker requires the bound CUDA device", stage="runtime_identity", seed=seed)
    if getattr(stack, "enforce_runtime_isolation", False) is True:
        common.assert_child_environment(os.environ, directory, entry["ld_library_path"])
    gpu_observation = stack.observe_gpu_identity()
    common.assert_runtime_gpu_binding(entry, gpu_observation)
    _stage(progress, "free_space")
    budget = common.assert_free_space(directory, contract.EPOCHS, statvfs=getattr(stack, "statvfs", None))
    _stage(progress, "asset_identity")
    assets = stack.observe_assets()
    runtime = common.translate_m6(lambda: m6.assert_observed_runtime(stack.observe_runtime()))
    accepted = m6._accepted_asset_table()
    if set(assets) != set(accepted):
        raise M7Error("identity_mismatch", "observed model assets do not match the accepted set", stage="asset_identity", seed=seed)
    for role, spec in accepted.items():
        common.translate_m6(lambda: m6._require_streamed_asset(assets[role], role, spec))
    common.assert_not_m6_weight(assets["b1_unet_weights"]["sha256"])
    _stage(progress, "biological_inputs")
    train_path = entry["train_text_path"]
    validation_path = entry["validation_csv_path"]
    artifact_path = entry["validation_artifact_directory"]
    common.assert_path_permitted(train_path, "TRAIN_TEXT", bound_output=directory, realpath=os.path.realpath)
    common.assert_path_permitted(validation_path, "VALIDATION_CSV", bound_output=directory, realpath=os.path.realpath)
    common.assert_path_permitted(artifact_path, "VALIDATION_ARTIFACT", bound_output=directory, realpath=os.path.realpath)
    train_open = common.translate_m6(
        lambda: m6.verify_bound_file(train_path, "TRAIN_TEXT", entry["train_text_sha256"], entry["train_record_count"], train_path, stack.read_train_sequences)
    )
    validation_open = common.translate_m6(
        lambda: m6.verify_bound_file(
            validation_path, "VALIDATION_CSV", entry["validation_csv_sha256"], entry["validation_record_count"], validation_path, stack.read_validation_cores
        )
    )
    train_sequences = train_open["opened"]
    validation_sequences = validation_open["opened"]
    if len(train_sequences) != m6.TRAIN_RECORD_COUNT or len(validation_sequences) != m6.VALIDATION_SEQUENCE_COUNT:
        raise M7Error("identity_mismatch", "reader counts drifted after the bound open", stage="biological_inputs", seed=seed)
    loaded = common.translate_m6(lambda: m6r._open_artifacts(entry, stack, artifact_path))
    _stage(progress, "model_load")
    encdec_path = os.path.join(common.RNAGENESIS_ROOT, m6.ENCDEC_RELATIVE_PATH)
    denoiser_path = os.path.join(common.RNAGENESIS_ROOT, entry["b1_relative_path"])
    common.assert_path_permitted(encdec_path, "FROZEN_ENCDEC", bound_output=directory)
    common.assert_path_permitted(denoiser_path, "B1_INITIALISATION", bound_output=directory)
    common.assert_initialisation_input(denoiser_path)
    encdec = stack.load_frozen_encdec(encdec_path)
    denoiser = stack.load_b1_denoiser(denoiser_path)
    scheduler = stack.load_scheduler(denoiser_path)
    common.translate_m6(lambda: m6r.assert_denoiser_fp32(torch, denoiser))
    _stage(progress, "initial_state_digest")
    b1_state = initial_state_digest(denoiser)
    optimizer = stack.build_adamw(denoiser, contract.applied_learning_rate(1))
    common.translate_m6(lambda: m6r._assert_adamw_hyperparameters(optimizer))
    accelerator = stack.accelerator()
    denoiser, optimizer = accelerator.prepare(denoiser, optimizer)
    logical_device = common.translate_m6(lambda: m6r.assert_prepared_runtime(accelerator, torch, _cuda_device_count(stack, torch)))
    encdec = _place(stack, encdec, logical_device)
    encdec.eval()
    denoiser.train()
    membership = common.translate_m6(lambda: m6r.live_parameter_identity_proof(optimizer, denoiser, encdec))
    if hasattr(stack, "assert_optimizer_membership"):
        stack.assert_optimizer_membership(optimizer, denoiser, encdec)
    rng = initialise_streams(torch, stack, seed)
    tokenizer = stack.load_tokenizer()
    windows = contract.epoch_windows()
    frozen_rows = {0: m6r.encdec_frozen_digests(encdec)}
    validation_values = {}
    validation_durations = []

    def validate(update):
        _stage(progress, "validation", epoch=None if update == 0 else contract.epoch_of_update(update), update=update)
        began = clock.stamp()
        aggregate = common.translate_m6(
            lambda: m6r._validation_aggregate(stack, accelerator, denoiser, encdec, scheduler, validation_sequences, loaded, tokenizer, torch, logical_device)
        )
        validation_durations.append({"seconds": clock.stamp() - began, "update": update})
        return aggregate

    validation_values[0] = validate(0)
    train_rows = []
    train_durations = []
    checkpoint_durations = []
    checkpoints = []
    epoch_plan = []
    for epoch in contract.CANDIDATE_EPOCHS:
        first_update, last_update = contract.epoch_update_range(epoch)
        order = torch.randperm(len(train_sequences), generator=rng["permutation_generator"]).tolist()
        epoch_digest = contract.permutation_digest(order)
        ordered = [train_sequences[index] for index in order]
        epoch_plan.append(
            {
                "epoch": epoch,
                "final_window_microbatch_sizes": list(contract.FINAL_WINDOW),
                "first_update": first_update,
                "last_update": last_update,
                "microbatches": contract.MICROBATCHES_PER_EPOCH,
                "optimizer_updates": contract.UPDATES_PER_EPOCH,
                "permutation_digest": epoch_digest,
            }
        )
        offset = 0
        for local_index, window in enumerate(windows, start=1):
            update = first_update + local_index - 1
            _stage(progress, "training_update", epoch=epoch, update=update)
            began = clock.stamp()
            learning_rate = contract.assign_applied_learning_rate(optimizer, update)
            scales = common.translate_m6(lambda: m6.applied_float_scales(window))
            window_loss = 0.0
            optimizer.zero_grad(set_to_none=True)
            for microbatch_index, (size, scale) in enumerate(zip(window, scales), start=1):
                _stage(progress, "microbatch", epoch=epoch, update=update, microbatch=microbatch_index)
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
                common.translate_m6(lambda: m6.assert_finite_training_loss(float(loss.detach())))
                accelerator.backward(loss * common.translate_m6(lambda: m6.production_loss_scale(scale)))
                window_loss += float(loss.detach()) * scale
            common.translate_m6(lambda: m6.assert_finite_training_loss(window_loss))
            parameters = [parameter for parameter in denoiser.parameters() if parameter.requires_grad]
            if not all(parameter.grad is not None and bool(torch.isfinite(parameter.grad).all()) for parameter in parameters):
                raise M7Error("non_finite_trainable_gradient", "a trainable gradient is not finite", stage="training_update", seed=seed, epoch=epoch, update=update)
            selected = common.translate_m6(lambda: m6r.select_denoiser_change(torch, list(denoiser.named_parameters())))
            pre_clip = float(torch.nn.utils.clip_grad_norm_(parameters, m6.GRADIENT_CLIP_NORM))
            clip = common.translate_m6(lambda: m6.clip_pre_clip_norm(pre_clip))
            optimizer.step()
            change = common.translate_m6(lambda: m6r.finish_denoiser_change(selected))
            optimizer.zero_grad(set_to_none=True)
            train_durations.append(clock.stamp() - began)
            train_rows.append(
                {
                    "applied_clip_norm": common.format_decimal(clip["applied_norm"]),
                    "clipped": clip["clipped"],
                    "denoiser_change": change,
                    "epoch": epoch,
                    "learning_rate": common.format_decimal(learning_rate),
                    "learning_rate_recorded_before_optimizer_step": True,
                    "pre_clip_gradient_norm": common.format_decimal(clip["pre_clip_gradient_norm"]),
                    "training_loss": common.format_decimal(window_loss),
                    "update": update,
                }
            )
        if offset != m6.TRAIN_RECORD_COUNT:
            raise M7Error("microbatch_arithmetic_invalid", "an epoch did not consume 669 records", stage="training_update", seed=seed, epoch=epoch)
        _stage(progress, "checkpoint", epoch=epoch, update=last_update)
        began = clock.stamp()
        checkpoints.append(save_and_prove_epoch(stack, denoiser, scheduler, directory, entry, epoch, progress))
        checkpoint_durations.append({"epoch": epoch, "seconds": clock.stamp() - began})
        _stage(progress, "frozen_check", epoch=epoch, update=last_update)
        frozen_rows[last_update] = m6r.encdec_frozen_digests(encdec)
        if frozen_rows[last_update]["parameter_digest"] != frozen_rows[0]["parameter_digest"]:
            raise M7Error("modified_or_trainable_encdec", "EncDec parameters changed", stage="frozen_check", seed=seed, epoch=epoch, update=last_update)
        if frozen_rows[last_update]["persistent_buffer_digest"] != frozen_rows[0]["persistent_buffer_digest"]:
            raise M7Error("modified_or_trainable_encdec", "EncDec persistent buffers changed", stage="frozen_check", seed=seed, epoch=epoch, update=last_update)
        validation_values[last_update] = validate(last_update)
    if len(train_rows) != contract.TOTAL_UPDATES or [item["update"] for item in validation_durations] != list(contract.VALIDATION_UPDATES):
        raise M7Error("validation_schedule_invalid", "the worker did not complete 105 updates and six validations", seed=seed)
    _stage(progress, "rng_final_observation")
    rng_final = final_stream_digests(torch, rng)
    _stage(progress, "manifest_assembly")
    finished = clock.stamp()
    return _assemble_manifest(
        entry=entry,
        directory=directory,
        seed=seed,
        runtime=runtime,
        assets=assets,
        b1_state=b1_state,
        gpu_observation=gpu_observation,
        budget=budget,
        rng=rng,
        rng_final=rng_final,
        epoch_plan=epoch_plan,
        train_rows=train_rows,
        validation_values=validation_values,
        checkpoints=checkpoints,
        frozen_rows=frozen_rows,
        membership=membership,
        train_durations=train_durations,
        validation_durations=validation_durations,
        checkpoint_durations=checkpoint_durations,
        loaded=loaded,
        train_open=train_open,
        validation_open=validation_open,
        end_to_end_seconds=float(prelude_seconds) + (finished - first_stamp),
    )


def _assemble_manifest(
    entry,
    directory,
    seed,
    runtime,
    assets,
    b1_state,
    gpu_observation,
    budget,
    rng,
    rng_final,
    epoch_plan,
    train_rows,
    validation_values,
    checkpoints,
    frozen_rows,
    membership,
    train_durations,
    validation_durations,
    checkpoint_durations,
    loaded,
    train_open,
    validation_open,
    end_to_end_seconds,
):
    candidate_values = {}
    rows = []
    for update in contract.VALIDATION_UPDATES:
        candidate = update != 0
        epoch = contract.epoch_of_update(update) if candidate else None
        value = common.format_decimal(validation_values[update])
        if candidate:
            candidate_values[epoch] = value
        rows.append(
            {
                "aggregate_mse": value,
                "candidate": candidate,
                "epoch": epoch,
                "pair_count": m6.VALIDATION_PAIR_COUNT,
                "tensors_loaded": True,
                "tensors_regenerated": False,
                "update": update,
                "weight_variant": "raw",
            }
        )
    order = common.rank_validation_candidates(candidate_values)
    ranking = {
        "excludes_update_0": True,
        "ranked_candidates": [
            {"aggregate_mse": candidate_values[epoch], "epoch": epoch, "rank": position, "update": contract.epoch_update_range(epoch)[1]}
            for position, epoch in enumerate(order, start=1)
        ],
        "rule": common.RANKING_RULE,
    }
    training_total = sum(train_durations)
    validation_total = sum(item["seconds"] for item in validation_durations)
    trace = contract.trace_strings()
    weights = assets["b1_unet_weights"]
    repository = dict(entry["repository_observation"])
    isolated = common.isolated_paths(directory)
    environment = {
        "allow_listed_child_environment": True,
        "bytecode_disabled": os.environ.get("PYTHONDONTWRITEBYTECODE") == "1",
        "cache_isolation": {key: os.environ.get(key) for key in sorted(isolated)},
        "datasets_offline": os.environ.get("HF_DATASETS_OFFLINE") == "1",
        "hub_offline": os.environ.get("HF_HUB_OFFLINE") == "1",
        "interpreter": dict(entry["interpreter"]),
        "ld_library_path": common.observe_child_ld_library_path(os.environ, entry["ld_library_path"]),
        "package_versions_observed": runtime,
        "stray_environment_names": 0,
        "transformers_offline": os.environ.get("TRANSFORMERS_OFFLINE") == "1",
    }
    final_update = contract.TOTAL_UPDATES
    parameter_digests = {str(update): frozen_rows[update]["parameter_digest"] for update in contract.VALIDATION_UPDATES}
    buffer_digests = {str(update): frozen_rows[update]["persistent_buffer_digest"] for update in contract.VALIDATION_UPDATES}
    manifest = {
        "accounting": {
            "drop_last": False,
            "epochs": contract.EPOCHS,
            "final_window_examples": 29,
            "final_window_microbatch_sizes": list(contract.FINAL_WINDOW),
            "full_window_examples": m6.INTENDED_EFFECTIVE_BATCH,
            "gradient_accumulation": m6.GRADIENT_ACCUMULATION,
            "intended_effective_batch": m6.INTENDED_EFFECTIVE_BATCH,
            "microbatches_per_epoch": contract.MICROBATCHES_PER_EPOCH,
            "optimizer_updates_per_epoch": contract.UPDATES_PER_EPOCH,
            "physical_microbatch": m6.PHYSICAL_MICROBATCH,
            "total_microbatches": contract.TOTAL_MICROBATCHES,
            "total_optimizer_updates": contract.TOTAL_UPDATES,
            "train_records": m6.TRAIN_RECORD_COUNT,
        },
        "applied_learning_rate_trace": trace,
        "authorisation": {
            "authorisation_id": entry["authorisation_id"],
            "authorization_commit": entry["authorization_commit"],
            "authorization_parent_commit": entry["authorization_parent_commit"],
            "consumption_state": "consumed_successfully",
            "executing_implementation_commit": entry["executing_implementation_commit"],
            "reuse_permitted": False,
            "seed": seed,
            "single_use": True,
        },
        "b1_identity": {
            "initial_state_aggregate_digest": b1_state["initial_state_aggregate_digest"],
            "initial_state_entry_count": b1_state["initial_state_entry_count"],
            "initial_state_parameter_names_sha256": b1_state["initial_state_parameter_names_sha256"],
            "observed_assets": assets,
            "unet_config_sha256": assets["b1_unet_config"]["sha256"],
            "weight_bytes": weights["byte_size"],
            "weight_sha256": weights["sha256"],
        },
        "checkpoints": checkpoints,
        "closure": dict(contract.CLOSURE),
        "completion_state": "replicate_completed",
        "config_version": contract.SCHEMA_VERSION,
        "configuration": {
            "implementation_config_sha256": entry["implementation_config_sha256"],
            "implementation_file_hashes": dict(entry["implementation_file_hashes"]),
        },
        "data_roles": _production_data_roles(entry, train_open, validation_open, loaded["observed_files"]),
        "deviations": [{"id": item} for item in contract.DOCUMENTED_DEVIATIONS],
        "environment": environment,
        "epoch_plan": epoch_plan,
        "experiment_id": contract.EXPERIMENT_ID,
        "free_space": budget,
        "frozen_state": {
            "encdec_buffers_absent_from_optimizer": membership["encdec_buffers_absent_from_optimizer"],
            "encdec_eval_mode": membership["encdec_eval_mode"],
            "encdec_parameters_absent_from_optimizer": membership["encdec_parameters_absent_from_optimizer"],
            "encdec_requires_grad_false": membership["encdec_requires_grad_false"],
            "optimizer_contains_only_denoiser": membership["optimizer_contains_only_denoiser"],
            "optimizer_parameter_ids_equal_trainable_denoiser": membership["optimizer_parameter_ids_equal_trainable_denoiser"],
            "parameter_digests_by_update": parameter_digests,
            "persistent_buffer_digests_by_update": buffer_digests,
            "rotary_cache_names": list(frozen_rows[final_update]["rotary_cache_names"]),
        },
        "gpu": dict(gpu_observation),
        "initialisation_isolation": {
            "b1_loaded_fresh_for_this_seed": True,
            "cross_seed_state_reused": False,
            "forbidden_weight_sha256": sorted(common.M6_FORBIDDEN_WEIGHT_SHA256),
            "initialisation_relative_path": m6.B1_RELATIVE_PATH,
            "m6_checkpoint_loaded": False,
            "saved_weights_equal_a_forbidden_m6_hash": any(item["weight_sha256"] in common.M6_FORBIDDEN_WEIGHT_SHA256 for item in checkpoints),
        },
        "manifest_schema_version": contract.MANIFEST_SCHEMA_VERSION,
        "memory": {
            "peak_allocated_bytes": int(m6r.torch_memory("allocated")),
            "peak_reserved_bytes": int(m6r.torch_memory("reserved")),
        },
        "optimizer": {
            "automatic_learning_rate_change": False,
            "beta1": common.format_decimal(m6.ADAMW_BETA1),
            "beta2": common.format_decimal(m6.ADAMW_BETA2),
            "ema_enabled": False,
            "epsilon": common.format_decimal(m6.ADAMW_EPSILON),
            "gradient_clip_norm": common.format_decimal(m6.GRADIENT_CLIP_NORM),
            "learning_rate": common.format_decimal(contract.BASE_LEARNING_RATE),
            "learning_rate_sweep": False,
            "name": "AdamW",
            "precision": "fp32",
            "weight_decay": common.format_decimal(m6.ADAMW_WEIGHT_DECAY),
            "weight_variant": "raw",
        },
        "post_schedule_position": {
            "applied_to_optimizer": False,
            "multiplier": "0",
            "position": contract.POST_SCHEDULE_POSITION,
            "pytorch_scheduler_last_epoch": None,
            "role": "next_unapplied_schedule_position",
        },
        "ref_eval_access": {
            "eval_hash_metadata_only": m6.EVAL_HASH_METADATA,
            "eval_opened": False,
            "ref_hash_metadata_only": m6.REF_HASH_METADATA,
            "ref_opened": False,
        },
        "repository": {
            "authorization_commit": entry["authorization_commit"],
            "executing_implementation_commit": entry["executing_implementation_commit"],
            "mres_index_clean": repository["mres_index_clean"],
            "mres_tracked_clean": repository["mres_tracked_clean"],
            "mres_untracked_clean": repository["mres_untracked_clean"],
            "rnagenesis_branch": repository["rnagenesis_branch"],
            "rnagenesis_commit": repository["rnagenesis_commit"],
            "rnagenesis_tracked_clean": repository["rnagenesis_tracked_clean"],
            "rnagenesis_untracked_preserved": repository["rnagenesis_untracked_preserved"],
        },
        "residual_limitations": list(contract.RESIDUAL_LIMITATIONS),
        "restart_policy": dict(contract.RESTART_POLICY),
        "resume_supported": False,
        "rng": {
            "diffusion_generator_final_digest": rng_final["diffusion_final"],
            "diffusion_generator_initial_digest": rng["diffusion_initial"],
            "diffusion_stream": "dedicated_cpu_diffusion_generator",
            "numpy_called_by_replicate": False,
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
            "training_seed": seed,
            "validation_artifacts_regenerated": False,
            "validation_draw_seed": contract.VALIDATION_DRAW_SEED,
        },
        "run_id": entry["authorisation_id"],
        "schedule": {
            "applied_learning_rate_trace_sha256": contract.trace_sha256(trace),
            "applied_optimizer_updates": contract.TOTAL_UPDATES,
            "diffusers_constructor_used": False,
            "name": "explicit_applied_update_cosine",
            "update_1_multiplier": "0.1",
            "warmup_updates": contract.WARMUP_UPDATES,
        },
        "schema_version": contract.SCHEMA_VERSION,
        "seed": seed,
        "timing": {
            "checkpoint_seconds": [{"epoch": item["epoch"], "seconds": common.format_decimal(item["seconds"])} for item in checkpoint_durations],
            "end_to_end_seconds": common.format_decimal(end_to_end_seconds),
            "synchronization": "cuda_synchronize_before_and_after_each_region",
            "training_seconds": common.format_decimal(training_total),
            "training_update_seconds": [common.format_decimal(item) for item in train_durations],
            "validation_seconds": common.format_decimal(validation_total),
            "validation_update_seconds": [
                {"seconds": common.format_decimal(item["seconds"]), "update": item["update"]} for item in validation_durations
            ],
        },
        "train_update_observations": train_rows,
        "validation_artifacts": _validation_artifacts_record(loaded, validation_open),
        "validation_observations": rows,
        "validation_ranking": ranking,
        "warnings": [],
    }
    return manifest


def _validation_artifacts_record(loaded, validation_open):
    files = loaded["observed_files"]
    return {
        "draw_manifest_sha256": files["validation_draw_manifest.json"]["sha256"],
        "draws": m6.VALIDATION_DRAWS,
        "hash_report_sha256": files["validation_draw_manifest_sha256.json"]["sha256"],
        "noise_sha256": files["validation_noise.float32"]["sha256"],
        "noise_shape": list(m6.VALIDATION_NOISE_SHAPE),
        "observed_files": files,
        "order_artifact_sha256": files["validation_order_artifact.csv"]["sha256"],
        "sequence_count": m6.VALIDATION_SEQUENCE_COUNT,
        "sequence_order_sha256": loaded["observed_sequence_order_sha256"],
        "timestep_sha256": files["validation_timesteps.int64"]["sha256"],
        "timestep_shape": list(m6.VALIDATION_TIMESTEP_SHAPE),
        "validation_csv_sha256": validation_open["sha256"],
    }


if __name__ == "__main__":
    sys.exit(main())
