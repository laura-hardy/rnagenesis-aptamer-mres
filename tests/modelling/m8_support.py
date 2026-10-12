"""Shared loaders for the inactive M8 tests. Not collected as a test module."""

from __future__ import annotations

import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELLING = os.path.join(ROOT, "scripts", "modelling")
if MODELLING not in sys.path:
    sys.path.insert(0, MODELLING)

schedule = importlib.import_module("m8_schedule")
generation = importlib.import_module("m8_generation")
assemble = importlib.import_module("m8_assemble")


def pinned_vector_bytes():
    with open(schedule.LENGTH_VECTOR_PATH, "rb") as handle:
        return handle.read()


EXPLICIT_CONFIGURATION_RAW_SHA256 = "cd" * 32


def controller_observation():
    return {
        "executable": generation.PINNED_PYTHON,
        "proc_self_exe": generation.PINNED_RESOLVED_PYTHON,
        "proc_self_exe_resolved": generation.PINNED_RESOLVED_PYTHON,
        "python_version": generation.ACCEPTED_RUNTIME_VERSIONS["python"],
        "resolved_path": generation.PINNED_RESOLVED_PYTHON,
        "sha256": generation.PINNED_INTERPRETER_SHA256,
    }


def child_observation():
    return {
        "executable": generation.PINNED_PYTHON,
        "python_version": generation.ACCEPTED_RUNTIME_VERSIONS["python"],
        "resolved_path": generation.PINNED_RESOLVED_PYTHON,
        "sha256": generation.PINNED_INTERPRETER_SHA256,
    }


def implementation_file_hashes():
    return {
        "scripts/modelling/m8_assemble.py": "11" * 32,
        "scripts/modelling/m8_generation.py": "22" * 32,
        "scripts/modelling/m8_schedule.py": "33" * 32,
    }


def generation_entry(arm, directory, run_root):
    spec = generation.ARMS[arm]
    authorisation_id = os.path.basename(directory)
    return {
        "activation_status": "active_unconsumed",
        "active_configuration_sha256": "ab" * 32,
        "arm": arm,
        "asset_kind": spec["asset_kind"],
        "authorisation_id": authorisation_id,
        "authorization_parent_commit": "a" * 40,
        "condition_id": spec["condition_id"],
        "consumed": False,
        "d1_training_seed": spec["d1_training_seed"],
        "executing_implementation_commit": "b" * 40,
        "gpu_sharing_policy": generation.GPU_SHARING_EXCLUSIVE,
        "gpu_uuid": "GPU-test",
        "implementation_file_hashes": implementation_file_hashes(),
        "interpreter_path": generation.PINNED_PYTHON,
        "interpreter_resolved_path": generation.PINNED_RESOLVED_PYTHON,
        "interpreter_sha256": generation.PINNED_INTERPRETER_SHA256,
        "ld_library_path": None,
        "library_versions": dict(generation.ACCEPTED_RUNTIME_VERSIONS),
        "logical_device": "cuda:0",
        "minimum_free_filesystem_bytes": 1024,
        "minimum_free_gpu_memory_bytes": 1024,
        "output_directory": directory,
        "pci_bus": "0000:00:00.0",
        "physical_gpu": 1,
        "reuse_permitted": False,
        "run_id": authorisation_id,
        "run_root": run_root,
        "single_use": True,
        "technical_block": spec["technical_block"],
    }


def repository_observation(entry=None):
    import m5_smoke_contract as m5

    porcelain = m5.reviewed_rnagenesis_porcelain()
    hashes = implementation_file_hashes() if entry is None else dict(entry["implementation_file_hashes"])
    parent = "a" * 40 if entry is None else entry["authorization_parent_commit"]
    executing = "b" * 40 if entry is None else entry["executing_implementation_commit"]
    head = "d" * 40
    configuration = ("config/experiments/M8_raw_generation.yaml",)
    if parent == executing:
        revision_range = ({"changed_files": configuration, "commit": head, "parents": (executing,)},)
    else:
        revision_range = (
            {"changed_files": configuration, "commit": parent, "parents": (executing,)},
            {"changed_files": configuration, "commit": head, "parents": (parent,)},
        )
    return {
        "changed_files": configuration,
        "executing_implementation_is_ancestor": True,
        "file_sha256_at_implementation": hashes,
        "file_sha256_working_tree": dict(hashes),
        "mres_branch": "main",
        "mres_head": head,
        "mres_origin_main": head,
        "mres_parents": (parent,),
        "mres_porcelain": "",
        "revision_range": revision_range,
        "rnagenesis_branch": generation.RNAGENESIS_BRANCH,
        "rnagenesis_directory_porcelain": porcelain,
        "rnagenesis_file_porcelain": porcelain,
        "rnagenesis_head": generation.RNAGENESIS_COMMIT,
    }


def synthetic_selection_manifest():
    """A fake final-selection document. It is not the sealed manifest and contains no sequences."""
    rows = []
    for seed, pin in generation.D1_CHECKPOINTS.items():
        rows.append(
            {
                "checkpoint_name": pin["checkpoint_name"],
                "epoch": 5,
                "members_sha256": generation.d1_member_hashes(seed),
                "seed": seed,
                "update": 105,
                "validation_mse": "0.1",
                "weight_sha256": pin["weight_sha256"],
            }
        )
    rows.sort(key=lambda row: row["seed"])
    digest = generation.sha256_bytes(generation.canonical_bytes(rows))
    document = {
        "closure": {"human_gate_required": True, "m7_complete": False, "m8_generation_performed": False},
        "selected_set": rows,
        "selected_set_sha256": digest,
        "selection_outcome": "selected_set_complete",
    }
    blob = generation.canonical_bytes(document)
    return blob, digest


def text_for_master(master_index):
    if master_index == 0:
        return ""
    if master_index == 1:
        return "hello"
    return "ACGU"


def materialise_arm(directory, arm, text_for=text_for_master):
    """Write one sealed arm from the real schedule without generation.py."""
    os.makedirs(directory)
    lengths = schedule.assert_pinned_length_vector(pinned_vector_bytes())
    built = schedule.build_schedule(lengths)
    entry = generation_entry(arm, directory, os.path.dirname(directory))
    block = entry["technical_block"]
    outputs = []
    records = []
    for invocation in built["invocations"][block]["invocations"]:
        lines = [text_for(master) for master in invocation["master_attempt_indexes"]]
        blob = "".join(line + "\n" for line in lines).encode("utf-8")
        relative = generation.relative_raw_path(invocation)
        path = os.path.join(directory, relative.replace("/", os.sep))
        os.makedirs(os.path.dirname(path))
        with open(path, "wb") as handle:
            handle.write(blob)
        records.extend(generation.map_invocation_lines(entry, invocation, blob))
        outputs.append({"bytes": blob, "relative_path": relative, "sha256": generation.sha256_bytes(blob)})
    child = {
        "CUDA_MODULE_LOADING": "LAZY",
        "CUDA_VISIBLE_DEVICES": "1",
        "PATH": generation.FIXED_CHILD_PATH,
    }
    inventory = generation.expected_asset_inventory(entry["condition_id"], entry["technical_block"])
    if entry["asset_kind"] == "d1":
        selected = generation.pinned_d1_selected_set_evidence(entry["d1_training_seed"])
    else:
        selected = generation.not_applicable_selected_set()
    document, ledger = generation._manifest(
        entry,
        built,
        outputs,
        records,
        inventory,
        inventory,
        "2026-10-08T00:00:00+00:00",
        "2026-10-08T00:00:01+00:00",
        1,
        child,
        dict(generation.ACCEPTED_RUNTIME_VERSIONS),
        provenance=generation.provenance_from_entry(entry, "d" * 40, EXPLICIT_CONFIGURATION_RAW_SHA256),
        controller_interpreter=controller_observation(),
        child_interpreter=child_observation(),
        selected_evidence=selected,
    )
    generation.write_atomic_bytes(directory, generation.LEDGER_NAME, ledger)
    generation.write_atomic_bytes(directory, generation.MANIFEST_NAME, generation.canonical_bytes(document))
    manifest_path = os.path.join(directory, generation.MANIFEST_NAME)
    with open(manifest_path, "rb") as handle:
        blob = handle.read()
    return {
        "block": block,
        "byte_count": len(blob),
        "path": manifest_path,
        "records": records,
        "sha256": generation.sha256_bytes(blob),
    }


class ByteDeps(object):
    def read_bytes(self, path):
        with open(path, "rb") as handle:
            return handle.read()

    def lstat(self, path):
        return os.lstat(path)

    def repository_observation(self, entry=None):
        return repository_observation(entry)

    def now(self):
        return "2026-10-08T00:00:00+00:00"
