#!/usr/bin/env python3
"""CPU-only builder and loader for the fixed VALIDATION draw artifacts.

The production entry point reads the approved VALIDATION CSV, verifies its
bytes, and derives the 95 first-occurrence cores. Arbitrary cores do not
inherit that CSV hash. Loading reconstructs the stored tensors and does not
resample them. This module does not open REF or EVAL and does not initialise
CUDA.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata as importlib_metadata
import io
import json
import os
import subprocess
import sys
from pathlib import Path

MRES_ROOT = Path("/home/laura/rnagenesis-aptamer-mres")
RNAGENESIS_ROOT = Path("/home/laura/RNAGenesis")
BUILDER_RELATIVE = "scripts/modelling/build_validation_artifacts.py"
BUILDER_PATH = MRES_ROOT / BUILDER_RELATIVE
SCHEDULER_CONFIG_PATH = RNAGENESIS_ROOT / "configs/rnagenesis/diffusion/scheduler/scheduler_config.json"
APPROVED_VALIDATION_CSV = Path("/home/laura/rnagenesis-mres-data/development/ft_validation.csv")
SCHEMA_VERSION = "m4-validation-draw-artifacts-1"
ROLE = "VALIDATION"
SEQUENCE_COUNT = 95
DRAWS_PER_SEQUENCE = 4
SEED = 1
NUM_TRAIN_TIMESTEPS = 1000
LATENT_SHAPE = (32, 160)
ORDER_HEADER = "role,zero_based_frozen_index,sequence_core_sha256,biological_length"
VALIDATION_CSV_SHA256 = "cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd"
SCHEDULER_IDENTITY = "DDIMScheduler"
SCHEDULER_PREDICTION = "epsilon"
SCHEDULER_CONFIG_SHA256 = "6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396"
PROHIBITED_NAME_PARTS = (
    "ref.csv",
    "eval.csv",
    "ft_train.csv",
)
ORDER_NAME = "validation_order_artifact.csv"
TIMESTEP_NAME = "validation_timesteps.int64"
NOISE_NAME = "validation_noise.float32"
MANIFEST_NAME = "validation_draw_manifest.json"
HASH_REPORT_NAME = "validation_draw_manifest_sha256.json"


class ValidationArtifactError(Exception):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _is_sha40(value):
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _refuse_prohibited_path(path):
    text = str(path).replace("\\", "/")
    base = os.path.basename(text).lower()
    if base == "ft_validation.csv":
        return
    for part in PROHIBITED_NAME_PARTS:
        if part in text.lower():
            raise ValidationArtifactError(
                "prohibited_biological_path",
                "refusing a TRAIN, REF, or EVAL path",
            )


def _csv_field(value):
    text = str(value)
    if any(character in text for character in [",", '"', "\n", "\r"]):
        return '"' + text.replace('"', '""') + '"'
    return text


def _canonical_core(core):
    return isinstance(core, str) and core != "" and all(character in "ACGU" for character in core)


def sequence_order_bytes(cores):
    """ASCII cores in frozen order, each followed by one LF. No extra record."""
    chunks = []
    for core in cores:
        if not isinstance(core, str) or core == "":
            raise ValidationArtifactError("core_invalid", "sequence core must be a nonempty string")
        try:
            encoded = core.encode("ascii")
        except UnicodeEncodeError:
            raise ValidationArtifactError("core_invalid", "sequence core is not ASCII")
        if b"\n" in encoded or b"\r" in encoded:
            raise ValidationArtifactError("core_invalid", "sequence core contains a line break")
        chunks.append(encoded + b"\n")
    return b"".join(chunks)


def first_occurrence_cores(rows, require_count=None, require_canonical=False):
    """Keep the first row for each sequence core. Do not sort."""
    if not isinstance(rows, list):
        raise ValidationArtifactError("core_order_invalid", "rows must be a list")
    cores = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or "sequence_core" not in row:
            raise ValidationArtifactError("core_order_invalid", "row lacks sequence_core")
        core = row["sequence_core"]
        if not isinstance(core, str):
            raise ValidationArtifactError("core_invalid", "sequence core is not text")
        if core in seen:
            continue
        seen.add(core)
        if require_canonical and not _canonical_core(core):
            raise ValidationArtifactError("core_invalid", "sequence core is not canonical A/C/G/U")
        if "biological_length" in row and row["biological_length"] != len(core):
            raise ValidationArtifactError(
                "core_order_invalid",
                "biological_length does not match the core",
            )
        cores.append(core)
    if len(cores) != len(set(cores)):
        raise ValidationArtifactError("core_count_invalid", "first-occurrence cores are not unique")
    if require_count is not None and len(cores) != require_count:
        raise ValidationArtifactError(
            "core_count_invalid",
            "expected {} first-occurrence cores and observed {}".format(require_count, len(cores)),
        )
    return cores


def cores_from_validation_csv(raw, require_count=SEQUENCE_COUNT, require_canonical=True):
    """Derive cores in file order. Duplicate cores keep the first row only."""
    if not isinstance(raw, (bytes, bytearray)):
        raise ValidationArtifactError("validation_source_invalid", "VALIDATION bytes are required")
    payload = bytes(raw)
    if payload.startswith(b"\xef\xbb\xbf") or b"\r" in payload:
        raise ValidationArtifactError("validation_source_invalid", "VALIDATION CSV must be UTF-8 without a BOM or CR")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise ValidationArtifactError("validation_source_invalid", "VALIDATION CSV is not UTF-8")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "sequence_core" not in reader.fieldnames:
        raise ValidationArtifactError("validation_source_invalid", "VALIDATION CSV lacks sequence_core")
    rows = []
    for row in reader:
        core = row.get("sequence_core")
        item = {"sequence_core": core}
        if "sequence_length_core" in row and row["sequence_length_core"] not in (None, ""):
            try:
                item["biological_length"] = int(row["sequence_length_core"])
            except ValueError:
                raise ValidationArtifactError("core_order_invalid", "sequence_length_core is not an integer")
        rows.append(item)
    return first_occurrence_cores(rows, require_count=require_count, require_canonical=require_canonical)


def _paths_match(path, expected):
    try:
        return os.path.realpath(str(path)) == os.path.realpath(str(expected))
    except OSError:
        return os.path.abspath(str(path)) == os.path.abspath(str(expected))


def source_record_from_bytes(path, raw):
    """Measure the source that was actually read. Do not copy a stored hash."""
    _refuse_prohibited_path(path)
    if not isinstance(raw, (bytes, bytearray)):
        raise ValidationArtifactError("validation_source_invalid", "VALIDATION bytes are required")
    payload = bytes(raw)
    digest = _sha256(payload)
    approved_path = _paths_match(path, APPROVED_VALIDATION_CSV)
    if approved_path and digest != VALIDATION_CSV_SHA256:
        raise ValidationArtifactError(
            "validation_source_hash_mismatch",
            "approved VALIDATION CSV hash does not match the measured bytes",
        )
    approved = approved_path and digest == VALIDATION_CSV_SHA256
    return {
        "path": str(path),
        "byte_count": len(payload),
        "sha256": digest,
        "approved_validation_source": approved,
        "validation_csv_sha256": digest if approved else None,
        "approved_validation_csv_sha256_inherited": False,
    }


def order_rows_from_cores(cores, role=ROLE):
    rows = []
    for index, core in enumerate(cores):
        rows.append(
            {
                "role": role,
                "zero_based_frozen_index": index,
                "sequence_core_sha256": _sha256(core.encode("ascii")),
                "biological_length": len(core),
            }
        )
    return rows


def serialize_order_artifact(rows):
    """UTF-8 CSV with the approved header and no sequence text."""
    if not isinstance(rows, list) or not rows:
        raise ValidationArtifactError("order_artifact_invalid", "order rows are required")
    lines = [ORDER_HEADER]
    expected_fields = {
        "role",
        "zero_based_frozen_index",
        "sequence_core_sha256",
        "biological_length",
    }
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != expected_fields:
            raise ValidationArtifactError(
                "order_artifact_invalid",
                "order row fields must be exactly the no-sequence provenance fields",
            )
        if row["role"] != ROLE or row["zero_based_frozen_index"] != index:
            raise ValidationArtifactError("order_artifact_invalid", "frozen order was not preserved")
        digest = row["sequence_core_sha256"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValidationArtifactError("order_artifact_invalid", "core hash is not lowercase SHA-256")
        if type(row["biological_length"]) is not int or row["biological_length"] < 1:
            raise ValidationArtifactError("order_artifact_invalid", "biological_length is invalid")
        lines.append(
            ",".join(
                [
                    _csv_field(row["role"]),
                    str(row["zero_based_frozen_index"]),
                    digest,
                    str(row["biological_length"]),
                ]
            )
        )
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise ValidationArtifactError("order_artifact_invalid", "BOM or carriage return in order artifact")
    if raw.count(b"\n") != len(rows) + 1:
        raise ValidationArtifactError("order_artifact_invalid", "order artifact line count drifted")
    return raw


def build_draw_tensors(
    sequence_count=SEQUENCE_COUNT,
    draws_per_sequence=DRAWS_PER_SEQUENCE,
    seed=SEED,
    num_train_timesteps=NUM_TRAIN_TIMESTEPS,
):
    """One CPU generator, seed 1 by default. No global RNG and no CUDA."""
    import torch

    if torch.cuda.is_initialized():
        raise ValidationArtifactError("cuda_initialized", "CUDA was already initialised")
    if sequence_count < 1 or draws_per_sequence < 1:
        raise ValidationArtifactError("draw_shape_invalid", "sequence and draw counts must be positive")
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    timesteps = torch.empty((sequence_count, draws_per_sequence), dtype=torch.int64)
    noise = torch.empty(
        (sequence_count, draws_per_sequence, LATENT_SHAPE[0], LATENT_SHAPE[1]),
        dtype=torch.float32,
    )
    for sequence_index in range(sequence_count):
        for draw_index in range(draws_per_sequence):
            step = torch.randint(
                0,
                num_train_timesteps,
                (1,),
                generator=generator,
                dtype=torch.int64,
            )
            sample = torch.randn(LATENT_SHAPE, generator=generator, dtype=torch.float32)
            timesteps[sequence_index, draw_index] = step[0]
            noise[sequence_index, draw_index] = sample
    if timesteps.dtype != torch.int64 or noise.dtype != torch.float32:
        raise ValidationArtifactError("draw_dtype_invalid", "draw dtypes drifted")
    if timesteps.device.type != "cpu" or noise.device.type != "cpu":
        raise ValidationArtifactError("draw_device_invalid", "draw tensors are not CPU tensors")
    if torch.cuda.is_initialized():
        raise ValidationArtifactError("cuda_initialized", "building draws initialised CUDA")
    return timesteps, noise


def tensor_payload(tensor):
    if tensor.device.type != "cpu" or not tensor.is_contiguous():
        raise ValidationArtifactError("tensor_payload_invalid", "tensor must be contiguous CPU data")
    array = tensor.detach().cpu().numpy()
    if str(array.dtype.byteorder) == ">":
        raise ValidationArtifactError("tensor_payload_invalid", "tensor byte order is not little-endian")
    return array.tobytes()


def bind_stored_draws(timesteps, noise):
    """Return the stored tensors for every checkpoint. Do not resample."""

    def for_checkpoint(checkpoint_id):
        if not isinstance(checkpoint_id, str) or checkpoint_id.strip() == "":
            raise ValidationArtifactError("checkpoint_id_invalid", "checkpoint id is required")
        return timesteps, noise

    return for_checkpoint


def canonical_manifest_bytes(document):
    if "manifest_sha256" in document:
        raise ValidationArtifactError("manifest_invalid", "manifest body must not contain its own hash")
    text = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    raw = (text + "\n").encode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise ValidationArtifactError("manifest_invalid", "manifest serialization drifted")
    return raw


def _package_version(distribution):
    try:
        return importlib_metadata.version(distribution)
    except importlib_metadata.PackageNotFoundError:
        return None


def _builder_provenance():
    builder_bytes = BUILDER_PATH.read_bytes()
    completed = subprocess.run(
        ["git", "-C", str(MRES_ROOT), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ValidationArtifactError("builder_commit_unreadable", "builder commit could not be read")
    commit = completed.stdout.strip()
    if not _is_sha40(commit):
        raise ValidationArtifactError("builder_commit_unreadable", "builder commit is not a lowercase SHA-1")
    branch = subprocess.run(
        ["git", "-C", str(MRES_ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    porcelain = subprocess.run(
        ["git", "-C", str(MRES_ROOT), "status", "--porcelain=v1"],
        check=False,
        capture_output=True,
        text=True,
    )
    if branch.returncode != 0 or porcelain.returncode != 0:
        raise ValidationArtifactError("builder_commit_unreadable", "builder repository state could not be read")
    import numpy
    import torch

    return {
        "path": str(BUILDER_PATH),
        "sha256": _sha256(builder_bytes),
        "commit": commit,
        "branch": branch.stdout.strip(),
        "worktree_clean": porcelain.stdout.strip() == "",
        "interpreter": {"executable": sys.executable, "version": sys.version.split()[0]},
        "packages": {
            "numpy": numpy.__version__,
            "torch": torch.__version__,
            "numpy_distribution": _package_version("numpy"),
            "torch_distribution": _package_version("torch"),
        },
    }


def _porcelain_lines(porcelain):
    if not isinstance(porcelain, str):
        raise ValidationArtifactError("builder_commit_unreadable", "git status porcelain could not be read")
    return [line for line in porcelain.splitlines() if line != ""]


def _git_stdout(args, binary=False):
    completed = subprocess.run(
        ["git", "-C", str(MRES_ROOT), *list(args)],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ValidationArtifactError("builder_commit_unreadable", "git command failed")
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8")


def measure_scheduler(read_bytes=None):
    """Read the released training scheduler and require the approved identity."""
    reader = read_bytes or (lambda path: Path(path).read_bytes())
    raw = reader(SCHEDULER_CONFIG_PATH)
    if not isinstance(raw, (bytes, bytearray)):
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler configuration bytes are required")
    payload = bytes(raw)
    digest = _sha256(payload)
    if digest != SCHEDULER_CONFIG_SHA256:
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler configuration hash drifted")
    try:
        loaded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler configuration could not be parsed")
    if not isinstance(loaded, dict):
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler configuration is not a mapping")
    if loaded.get("_class_name") != SCHEDULER_IDENTITY:
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler class drifted")
    if loaded.get("prediction_type") != SCHEDULER_PREDICTION:
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler prediction type drifted")
    if loaded.get("num_train_timesteps") != NUM_TRAIN_TIMESTEPS:
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler timestep count drifted")
    return {
        "path": str(SCHEDULER_CONFIG_PATH),
        "sha256": digest,
        "class_name": SCHEDULER_IDENTITY,
        "prediction_type": SCHEDULER_PREDICTION,
        "num_train_timesteps": NUM_TRAIN_TIMESTEPS,
    }


def assert_production_materialisation(git=None, read_bytes=None):
    """Production writes require main, a clean MRes tree, and the HEAD builder blob.

    This does not create artifacts. Callers that materialise the approved
    VALIDATION draws must pass this gate first.
    """
    query = git or _git_stdout
    reader = read_bytes or (lambda path: Path(path).read_bytes())
    branch = query(["rev-parse", "--abbrev-ref", "HEAD"])
    if not isinstance(branch, str) or branch.strip() != "main":
        raise ValidationArtifactError("builder_branch_refused", "production materialisation requires main")
    porcelain = query(["status", "--porcelain=v1"])
    if not isinstance(porcelain, str) or _porcelain_lines(porcelain):
        raise ValidationArtifactError(
            "builder_worktree_dirty",
            "production materialisation requires a clean tracked, staged, and untracked MRes worktree",
        )
    head = query(["rev-parse", "HEAD"])
    if not isinstance(head, str) or not _is_sha40(head.strip()):
        raise ValidationArtifactError("builder_commit_unreadable", "HEAD is not a lowercase SHA-1")
    head = head.strip()
    blob = query(["rev-parse", "{}:{}".format(head, BUILDER_RELATIVE)])
    worktree_blob = query(["hash-object", "--", str(BUILDER_PATH)])
    if not isinstance(blob, str) or not isinstance(worktree_blob, str):
        raise ValidationArtifactError("builder_blob_mismatch", "builder blob identity could not be read")
    blob = blob.strip()
    worktree_blob = worktree_blob.strip()
    if blob == "" or blob != worktree_blob:
        raise ValidationArtifactError(
            "builder_blob_mismatch",
            "builder bytes do not match the accepted HEAD blob",
        )
    blob_bytes = query(["cat-file", "blob", blob], binary=True)
    if isinstance(blob_bytes, str):
        blob_bytes = blob_bytes.encode("utf-8")
    if not isinstance(blob_bytes, (bytes, bytearray)):
        raise ValidationArtifactError("builder_blob_mismatch", "builder blob bytes could not be read")
    file_bytes = reader(BUILDER_PATH)
    if not isinstance(file_bytes, (bytes, bytearray)) or bytes(file_bytes) != bytes(blob_bytes):
        raise ValidationArtifactError(
            "builder_blob_mismatch",
            "builder bytes do not match the accepted HEAD blob",
        )
    scheduler = measure_scheduler(reader)
    return {
        "branch": "main",
        "commit": head,
        "git_blob": blob,
        "builder_sha256": _sha256(bytes(file_bytes)),
        "scheduler": scheduler,
    }


def _builder_file_at_commit(commit):
    if not _is_sha40(commit):
        raise ValidationArtifactError("builder_blob_mismatch", "builder commit is not a lowercase SHA-1")
    completed = subprocess.run(
        ["git", "-C", str(MRES_ROOT), "cat-file", "blob", "{}:{}".format(commit, BUILDER_RELATIVE)],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0 or not completed.stdout:
        raise ValidationArtifactError("builder_blob_mismatch", "builder blob is missing at the recorded commit")
    return completed.stdout


def build_manifest(order_artifact, sequence_order, timestep_payload, noise_payload, sequence_count, draws_per_sequence, source):
    if not isinstance(source, dict):
        raise ValidationArtifactError("validation_source_invalid", "source provenance is missing")
    if source.get("approved_validation_csv_sha256_inherited") is not False:
        raise ValidationArtifactError(
            "validation_source_invalid",
            "an arbitrary source inherited the approved CSV hash",
        )
    approved = source.get("approved_validation_source") is True
    if approved:
        if source.get("sha256") != VALIDATION_CSV_SHA256 or source.get("validation_csv_sha256") != VALIDATION_CSV_SHA256:
            raise ValidationArtifactError(
                "validation_source_hash_mismatch",
                "approved source hash drifted",
            )
    elif source.get("validation_csv_sha256") == VALIDATION_CSV_SHA256:
        raise ValidationArtifactError(
            "validation_source_invalid",
            "an unapproved source inherited the approved CSV hash",
        )
    if sys.byteorder != "little":
        raise ValidationArtifactError("tensor_payload_invalid", "artifact byte order must be little-endian")
    provenance = _builder_provenance()
    scheduler = measure_scheduler()
    document = {
        "schema_version": SCHEMA_VERSION,
        "role": ROLE,
        "sequence_count": sequence_count,
        "draws_per_sequence": draws_per_sequence,
        "seed": SEED,
        "generator": "torch.Generator",
        "generator_device": "cpu",
        "global_rng_used": False,
        "cuda_used": False,
        "scheduler_identity": scheduler["class_name"],
        "scheduler_prediction_type": scheduler["prediction_type"],
        "num_train_timesteps": scheduler["num_train_timesteps"],
        "scheduler": scheduler,
        "timestep_dtype": "int64",
        "noise_dtype": "float32",
        "timestep_numpy_dtype": "<i8",
        "noise_numpy_dtype": "<f4",
        "byte_order": "little",
        "timestep_shape": [sequence_count, draws_per_sequence],
        "noise_shape": [sequence_count, draws_per_sequence, LATENT_SHAPE[0], LATENT_SHAPE[1]],
        "timestep_byte_count": len(timestep_payload),
        "noise_byte_count": len(noise_payload),
        "timestep_domain": [0, NUM_TRAIN_TIMESTEPS - 1],
        "source": source,
        "validation_csv_sha256": source.get("validation_csv_sha256"),
        "validation_csv_sha256_does_not_substitute_for_ordering_hashes": True,
        "approved_validation_csv_sha256_inherited": False,
        "validation_sequence_order_sha256": _sha256(sequence_order),
        "validation_order_artifact_sha256": _sha256(order_artifact),
        "order_artifact_byte_count": len(order_artifact),
        "timestep_tensor_sha256": _sha256(timestep_payload),
        "noise_tensor_sha256": _sha256(noise_payload),
        "order_artifact_contains_sequence_text": False,
        "regeneration_during_a_training_run": False,
        "reused_at_initialization_and_every_checkpoint": True,
        "contains_sequence_text": False,
        "builder": provenance,
        "resampled_on_load": False,
    }
    return document


def _exclusive_write(path, data):
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    descriptor = os.open(str(path), flags, 0o644)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written == 0:
                raise ValidationArtifactError("artifact_write_failed", "short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path):
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_exact(path):
    with open(path, "rb") as handle:
        return handle.read()


def write_artifacts(
    output_directory,
    cores,
    sequence_count=SEQUENCE_COUNT,
    draws_per_sequence=DRAWS_PER_SEQUENCE,
    source=None,
):
    """Write a new artifact directory. The manifest is the last file."""
    _refuse_prohibited_path(output_directory)
    if len(cores) != sequence_count:
        raise ValidationArtifactError(
            "core_count_invalid",
            "expected {} cores and observed {}".format(sequence_count, len(cores)),
        )
    if source is None:
        source = {
            "path": None,
            "byte_count": None,
            "sha256": None,
            "approved_validation_source": False,
            "validation_csv_sha256": None,
            "approved_validation_csv_sha256_inherited": False,
        }
    output = Path(output_directory)
    if output.exists() or output.is_symlink():
        raise ValidationArtifactError("output_exists", "refusing to overwrite an artifact directory")
    rows = order_rows_from_cores(cores)
    order_artifact = serialize_order_artifact(rows)
    sequence_order = sequence_order_bytes(cores)
    timesteps, noise = build_draw_tensors(sequence_count, draws_per_sequence)
    timestep_payload = tensor_payload(timesteps)
    noise_payload = tensor_payload(noise)
    manifest = build_manifest(
        order_artifact,
        sequence_order,
        timestep_payload,
        noise_payload,
        sequence_count,
        draws_per_sequence,
        source,
    )
    manifest_bytes = canonical_manifest_bytes(manifest)
    hash_report = {
        "schema_version": SCHEMA_VERSION,
        "validation_draw_manifest_sha256": _sha256(manifest_bytes),
        "validation_order_artifact_sha256": _sha256(order_artifact),
        "timestep_tensor_sha256": _sha256(timestep_payload),
        "noise_tensor_sha256": _sha256(noise_payload),
    }
    hash_report_bytes = canonical_manifest_bytes(hash_report)
    os.mkdir(output)
    try:
        _exclusive_write(output / ORDER_NAME, order_artifact)
        _exclusive_write(output / TIMESTEP_NAME, timestep_payload)
        _exclusive_write(output / NOISE_NAME, noise_payload)
        _fsync_directory(output)
        if _read_exact(output / ORDER_NAME) != order_artifact:
            raise ValidationArtifactError("artifact_verification_failed", "order artifact changed before commit")
        if _read_exact(output / TIMESTEP_NAME) != timestep_payload:
            raise ValidationArtifactError("artifact_verification_failed", "timestep payload changed before commit")
        if _read_exact(output / NOISE_NAME) != noise_payload:
            raise ValidationArtifactError("artifact_verification_failed", "noise payload changed before commit")
        if (output / HASH_REPORT_NAME).exists() or (output / MANIFEST_NAME).exists():
            raise ValidationArtifactError("manifest_invalid", "refusing to replace an existing manifest")
        _exclusive_write(output / HASH_REPORT_NAME, hash_report_bytes)
        if _read_exact(output / HASH_REPORT_NAME) != hash_report_bytes:
            raise ValidationArtifactError("artifact_verification_failed", "manifest hash report changed before commit")
        _exclusive_write(output / MANIFEST_NAME, manifest_bytes)
        _fsync_directory(output)
        if _read_exact(output / MANIFEST_NAME) != manifest_bytes:
            raise ValidationArtifactError("artifact_verification_failed", "manifest changed after commit")
    except (KeyboardInterrupt, SystemExit):
        raise
    except ValidationArtifactError:
        raise
    except OSError as exc:
        raise ValidationArtifactError("artifact_write_failed", "artifact write failed: {}".format(exc.errno))
    stored = bind_stored_draws(timesteps, noise)
    return {
        "manifest": manifest,
        "manifest_sha256": _sha256(manifest_bytes),
        "stored_draws": stored,
        "timesteps": timesteps,
        "noise": noise,
    }


def write_artifacts_from_validation_bytes(output_directory, path, raw):
    """Bind artifacts to the measured CSV bytes and the cores they contain."""
    source = source_record_from_bytes(path, raw)
    require_count = SEQUENCE_COUNT if source["approved_validation_source"] else None
    cores = cores_from_validation_csv(
        raw,
        require_count=require_count if require_count is not None else SEQUENCE_COUNT,
        require_canonical=True,
    )
    if len(cores) != SEQUENCE_COUNT or len(set(cores)) != SEQUENCE_COUNT:
        raise ValidationArtifactError("core_count_invalid", "expected 95 unique first-occurrence cores")
    return write_artifacts(output_directory, cores, source=source)


def _reconstruct(payload, dtype, shape):
    import numpy
    import torch

    array = numpy.frombuffer(payload, dtype=numpy.dtype(dtype))
    expected = 1
    for item in shape:
        expected *= int(item)
    if array.shape != (expected,):
        raise ValidationArtifactError("artifact_verification_failed", "tensor byte count does not match the shape")
    if array.dtype.str != dtype:
        raise ValidationArtifactError("artifact_verification_failed", "tensor dtype drifted")
    copied = numpy.array(array, dtype=numpy.dtype(dtype), copy=True)
    tensor = torch.from_numpy(copied)
    if tuple(tensor.shape) == tuple(shape):
        return tensor
    return tensor.reshape(tuple(shape))


def _require_manifest_contract(manifest):
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValidationArtifactError("artifact_verification_failed", "schema version drifted")
    if manifest.get("role") != ROLE:
        raise ValidationArtifactError("artifact_verification_failed", "role drifted")
    if manifest.get("sequence_count") != SEQUENCE_COUNT or manifest.get("draws_per_sequence") != DRAWS_PER_SEQUENCE:
        raise ValidationArtifactError("artifact_verification_failed", "sequence or draw count drifted")
    if manifest.get("seed") != SEED:
        raise ValidationArtifactError("artifact_verification_failed", "seed drifted")
    if manifest.get("timestep_shape") != [SEQUENCE_COUNT, DRAWS_PER_SEQUENCE]:
        raise ValidationArtifactError("artifact_verification_failed", "timestep shape drifted")
    if manifest.get("noise_shape") != [SEQUENCE_COUNT, DRAWS_PER_SEQUENCE, LATENT_SHAPE[0], LATENT_SHAPE[1]]:
        raise ValidationArtifactError("artifact_verification_failed", "noise shape drifted")
    if manifest.get("byte_order") != "little":
        raise ValidationArtifactError("artifact_verification_failed", "byte order is not little-endian")
    if manifest.get("timestep_dtype") != "int64" or manifest.get("noise_dtype") != "float32":
        raise ValidationArtifactError("artifact_verification_failed", "dtype drifted")
    if manifest.get("timestep_numpy_dtype") != "<i8" or manifest.get("noise_numpy_dtype") != "<f4":
        raise ValidationArtifactError("artifact_verification_failed", "numpy dtype drifted")
    scheduler = manifest.get("scheduler")
    if not isinstance(scheduler, dict):
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler provenance is missing")
    if scheduler.get("path") != str(SCHEDULER_CONFIG_PATH):
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler path drifted")
    if scheduler.get("sha256") != SCHEDULER_CONFIG_SHA256:
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler hash drifted")
    if scheduler.get("class_name") != SCHEDULER_IDENTITY or manifest.get("scheduler_identity") != SCHEDULER_IDENTITY:
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler class drifted")
    if scheduler.get("prediction_type") != SCHEDULER_PREDICTION or manifest.get("scheduler_prediction_type") != SCHEDULER_PREDICTION:
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler prediction type drifted")
    if scheduler.get("num_train_timesteps") != NUM_TRAIN_TIMESTEPS or manifest.get("num_train_timesteps") != NUM_TRAIN_TIMESTEPS:
        raise ValidationArtifactError("scheduler_configuration_drift", "scheduler timestep count drifted")
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ValidationArtifactError("validation_source_invalid", "manifest source is missing")
    if source.get("approved_validation_source") is not True:
        raise ValidationArtifactError("wrong_validation_source", "artifacts are not bound to the approved VALIDATION source")
    if source.get("approved_validation_csv_sha256_inherited") is not False:
        raise ValidationArtifactError("validation_source_invalid", "approved CSV hash was inherited")
    if source.get("sha256") != VALIDATION_CSV_SHA256 or source.get("validation_csv_sha256") != VALIDATION_CSV_SHA256:
        raise ValidationArtifactError("validation_source_hash_mismatch", "approved source hash drifted")
    if manifest.get("validation_csv_sha256") != VALIDATION_CSV_SHA256:
        raise ValidationArtifactError("validation_source_hash_mismatch", "manifest CSV hash drifted")
    if not _paths_match(source.get("path"), APPROVED_VALIDATION_CSV):
        raise ValidationArtifactError("validation_source_hash_mismatch", "approved source path drifted")
    builder = manifest.get("builder")
    if not isinstance(builder, dict) or not _is_sha40(builder.get("commit")):
        raise ValidationArtifactError("builder_blob_mismatch", "builder commit is missing")
    if not isinstance(builder.get("sha256"), str) or len(builder.get("sha256")) != 64:
        raise ValidationArtifactError("builder_blob_mismatch", "builder hash is missing")
    if _sha256(_builder_file_at_commit(builder["commit"])) != builder["sha256"]:
        raise ValidationArtifactError("builder_blob_mismatch", "builder hash does not match the recorded commit blob")


def load_verified_artifacts(directory, expected_source_sha256=None):
    """Reconstruct the stored tensors. Do not draw new timesteps or noise."""
    root = Path(directory)
    report_path = root / HASH_REPORT_NAME
    manifest_path = root / MANIFEST_NAME
    if not report_path.is_file() or report_path.is_symlink():
        raise ValidationArtifactError("manifest_hash_report_missing", "manifest hash report is missing")
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValidationArtifactError("manifest_invalid", "verified manifest is missing")
    report_bytes = _read_exact(report_path)
    manifest_bytes = _read_exact(manifest_path)
    try:
        report = json.loads(report_bytes.decode("utf-8"))
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValidationArtifactError("manifest_invalid", "manifest could not be parsed")
    if not isinstance(report, dict) or not isinstance(manifest, dict):
        raise ValidationArtifactError("manifest_invalid", "manifest root must be a mapping")
    if canonical_manifest_bytes(report) != report_bytes:
        raise ValidationArtifactError("manifest_tampered", "manifest hash report is not canonical")
    if report.get("validation_draw_manifest_sha256") != _sha256(manifest_bytes):
        raise ValidationArtifactError("manifest_tampered", "canonical manifest hash does not match the report")
    if canonical_manifest_bytes(manifest) != manifest_bytes:
        raise ValidationArtifactError("manifest_tampered", "manifest is not canonical")
    if manifest.get("resampled_on_load") is not False:
        raise ValidationArtifactError("artifact_verification_failed", "loader must not resample")
    _require_manifest_contract(manifest)
    source = manifest["source"]
    if expected_source_sha256 is not None and source.get("sha256") != expected_source_sha256:
        raise ValidationArtifactError("wrong_validation_source", "artifact source hash does not match the requested source")
    order_bytes = _read_exact(root / ORDER_NAME)
    timestep_bytes = _read_exact(root / TIMESTEP_NAME)
    noise_bytes = _read_exact(root / NOISE_NAME)
    expected = {
        ORDER_NAME: (
            order_bytes,
            manifest.get("validation_order_artifact_sha256"),
            manifest.get("order_artifact_byte_count"),
            "validation_order_artifact_sha256",
        ),
        TIMESTEP_NAME: (
            timestep_bytes,
            manifest.get("timestep_tensor_sha256"),
            manifest.get("timestep_byte_count"),
            "timestep_tensor_sha256",
        ),
        NOISE_NAME: (
            noise_bytes,
            manifest.get("noise_tensor_sha256"),
            manifest.get("noise_byte_count"),
            "noise_tensor_sha256",
        ),
    }
    for name, (payload, digest, count, report_key) in expected.items():
        if report.get(report_key) != digest or _sha256(payload) != digest:
            raise ValidationArtifactError("artifact_tampered", name + " hash or byte count drifted")
        if type(count) is not int or len(payload) != count:
            raise ValidationArtifactError("artifact_tampered", name + " hash or byte count drifted")
    timestep_shape = tuple(manifest.get("timestep_shape") or [])
    noise_shape = tuple(manifest.get("noise_shape") or [])
    timesteps = _reconstruct(timestep_bytes, "<i8", timestep_shape)
    noise = _reconstruct(noise_bytes, "<f4", noise_shape)
    if tensor_payload(timesteps) != timestep_bytes or tensor_payload(noise) != noise_bytes:
        raise ValidationArtifactError("artifact_verification_failed", "reconstructed tensors do not match the file bytes")
    return {
        "manifest": manifest,
        "timesteps": timesteps,
        "noise": noise,
        "stored_draws": bind_stored_draws(timesteps, noise),
    }


def build_parser():
    parser = argparse.ArgumentParser(description="Build fixed VALIDATION draw artifacts")
    parser.add_argument("--output-directory", required=True)
    return parser


def main(argv):
    """Read the approved VALIDATION CSV. Do not accept a substitute cores file."""
    if any(str(item).startswith("--cores-json") for item in argv):
        raise ValidationArtifactError(
            "validation_source_invalid",
            "arbitrary cores JSON cannot inherit the approved CSV",
        )
    parser = build_parser()
    args = parser.parse_args(argv)
    _refuse_prohibited_path(args.output_directory)
    assert_production_materialisation()
    raw = APPROVED_VALIDATION_CSV.read_bytes()
    write_artifacts_from_validation_bytes(args.output_directory, APPROVED_VALIDATION_CSV, raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
