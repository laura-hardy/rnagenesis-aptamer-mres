#!/usr/bin/env python3
"""M7 shared primitives (inactive package).

Importing this module imports only the standard library. It does not import
torch, Accelerate, Diffusers, or RNAGenesis, and it does not open biological
data, model weights, a run directory, or a GPU. Nothing here is reachable from a
command line.

The module holds what the three M7 stages share: the error type, canonical
JSON, bounded streaming digests, REF/EVAL and sibling-evidence denial before any
filesystem open, symlink-safe ancestry, atomic writes with parent-directory
``fsync``, message-safe failure records, a strict allow-listed child
environment with a fixed PATH, a fixed ``CUDA_MODULE_LOADING=LAZY`` control,
absolute validated ``git`` and ``nvidia-smi`` executables, the free-space
budget, and the strict checkpoint-tree observation.
The accepted M6 contract is loaded by its tracked path and reused. Nothing in
M5 or M6 is changed.

Residual limitation, recorded and not solved here: a path is hashed and later
opened by name. A file replaced between those two operations is detected only
where a signature is compared before and after the open (the checkpoint tree
and the streamed digest). The documented hash-to-open TOCTOU window is not
closed.
"""

from __future__ import annotations

import collections.abc
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import subprocess
import sys
import unicodedata

MRES_ROOT = "/home/laura/rnagenesis-aptamer-mres"
RNAGENESIS_ROOT = "/home/laura/RNAGenesis"
RUN_ROOT = "/home/laura/rnagenesis-mres-runs"
PINNED_PYTHON = "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python"
RNAGENESIS_BRANCH = "mres-d1-diffusion-finetune"
RNAGENESIS_COMMIT = "e3b855bbf4d1af376f43747643fa30afd662828c"
MRES_BASE_COMMIT = "a58528d61c775cb5208ddb7efb3988dc3bd3fe88"
LOGICAL_CUDA_DEVICE = "cuda:0"
M6_CONTRACT_RELATIVE = "scripts/modelling/m6_pilot_contract.py"
M6_RUNNER_RELATIVE = "scripts/modelling/m6_pilot_runner.py"

# The M6 attempt-6 weights. They are recorded in tracked documents. They are
# forbidden as an M7 initialisation, resume input, or saved-checkpoint identity.
M6_FORBIDDEN_WEIGHT_SHA256 = {
    "7f1cdbd854c1d26c5b8bfe68469bc7e59f5d7293c4a105d724c1c63c83a32f10": "m6_update_7",
    "0a2fa065f962adaf54e63b797974367915a6552382a8db76c3fbd0c6a0078901": "m6_update_14",
    "47b2dc9b392ea766eee7e947f0f92f5a039c42ac714326104e719352d20b5924": "m6_update_21",
}
M6_EVIDENCE_NAME_PATTERN = re.compile(r"(^|/)m6_d1_[a-z0-9_]*(attempt[0-9]+|diffusion_pilot)[a-z0-9_]*(/|$)")
M6_CHECKPOINT_NAME_PATTERN = re.compile(r"seed-42__update-(7|14|21)__")

CONSUMPTION_RECORD_NAME = "authorization_consumption.json"
FAILURE_RECORD_NAME = "authorization_failure.json"
DIRECTORY_FSYNC_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
STREAM_CHUNK_BYTES = 1024 * 1024
MEBIBYTE = 1024 * 1024
GIBIBYTE = 1024 * MEBIBYTE

CHECKPOINT_MEMBERS = (
    "model_index.json",
    "scheduler/scheduler_config.json",
    "unet/config.json",
    "unet/diffusion_pytorch_model.safetensors",
)
WEIGHT_MEMBER = "unet/diffusion_pytorch_model.safetensors"
SEQUENCE_TEXT_KEYS = {
    "sequence",
    "sequence_core",
    "sequence_text",
    "raw_string",
    "raw_output",
    "raw_decoded_text",
    "normalized_string",
    "cleaned_sequence",
}
BODY_PATTERN = re.compile(r"^[ACGU]+$")
SEQUENCE_RUN_PATTERN = re.compile(r"[ACGUacgu]{8,}")

# Every failure code a consumed record or a rejection may carry. A code outside
# this registry is itself a defect and is recorded as incomplete evidence.
FAILURE_CODES = (
    "attempt_accounting_invalid",
    "asset_inspection_unsafe",
    "attempt_ledger_invalid",
    "authorisation_commit_invalid",
    "authorisation_delta_invalid",
    "authorisation_evidence_mismatch",
    "authorisation_field_missing",
    "authorisation_inactive",
    "authorisation_scope_invalid",
    "authorisation_shape_invalid",
    "authorization_reuse",
    "automatic_lr_change_rejected",
    "checkpoint_ancestry_unsafe",
    "checkpoint_overwrite_risk",
    "checkpoint_save_reload_incompatibility",
    "cleaner_import_failed",
    "cli_argument_rejected",
    "config_encoding",
    "config_parse",
    "config_shape",
    "configuration_not_consumable",
    "cross_seed_state",
    "cuda_environment_invalid",
    "cuda_rng_final_observation_failed",
    "environment_rejected",
    "execution_not_authorised",
    "filesystem_error",
    "generation_cwd_rejected",
    "fold_unavailable",
    "generation_process_failed",
    "git_status_unreadable",
    "gpu_fallback_prohibited",
    "gpu_probe_invalid",
    "guardrail_manifest_invalid",
    "identity_mismatch",
    "incomplete_evidence_or_manifest",
    "insufficient_free_space",
    "interpreter_rejected",
    "interrupted",
    "learning_rate_schedule_invalid",
    "learning_rate_zero_applied",
    "m6_checkpoint_forbidden",
    "malformed_output",
    "metrics_configuration_invalid",
    "microbatch_arithmetic_invalid",
    "missing_invocation_output",
    "modified_or_trainable_encdec",
    "no_observed_denoiser_change",
    "non_finite_pre_clip_gradient_norm",
    "non_finite_trainable_gradient",
    "non_finite_training_loss",
    "non_finite_validation",
    "output_line_count_mismatch",
    "provenance_mismatch",
    "python_interpreter_rejected",
    "raw_output_count_mismatch",
    "ref_or_eval_access",
    "schedule_hash_mismatch",
    "schedule_invalid",
    "selection_invalid",
    "sibling_evidence_access",
    "train_identity_mismatch",
    "train_reference_invalid",
    "training_stack_import_failed",
    "unauthorized_gpu",
    "unexpected_biological_path_or_role",
    "unexpected_output_normalization",
    "unexpected_runtime_failure",
    "unexpected_seed",
    "unreconciled_output",
    "validation_schedule_invalid",
)


class M7Error(Exception):
    """A message-safe M7 failure. The detail never carries sequence or tensor content."""

    def __init__(self, code, detail, stage=None, seed=None, epoch=None, update=None, microbatch=None, candidate=None):
        self.code = code
        self.detail = detail
        self.stage = stage
        self.seed = seed
        self.epoch = epoch
        self.update = update
        self.microbatch = microbatch
        self.candidate = candidate
        self.secondary_failure = None
        super().__init__(code + ": " + detail)


# ------------------------------------------------------------------ hashing and JSON


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical_json(value):
    """UTF-8 JSON, sorted keys, compact separators, one trailing LF, no NaN or Infinity."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n"
    except (TypeError, ValueError, OverflowError):
        raise M7Error("incomplete_evidence_or_manifest", "value is not canonical JSON evidence")


def format_decimal(value):
    return format(float(value), ".17g")


def is_sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def is_sha40(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def require_mapping(value, code, detail):
    if not isinstance(value, dict):
        raise M7Error(code, detail)
    return value


def exact_keys(mapping, expected, code):
    mapping = require_mapping(mapping, code, "expected a mapping")
    expected_set = set(expected)
    missing = sorted(expected_set - set(mapping))
    unexpected = sorted(set(mapping) - expected_set)
    if missing or unexpected:
        raise M7Error(code, "missing " + ",".join(missing) + " unexpected " + ",".join(unexpected))
    return mapping


def finite_float(value, code):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise M7Error(code, "value is not a real number")
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise M7Error(code, "value is not finite")
    return number


def finite_decimal_string(value, code="incomplete_evidence_or_manifest"):
    if isinstance(value, bool) or not isinstance(value, str) or value.strip() == "":
        raise M7Error(code, "numeric evidence must be a decimal string")
    try:
        number = float(value)
    except ValueError:
        raise M7Error(code, "numeric evidence is not a decimal string")
    if math.isnan(number) or math.isinf(number):
        raise M7Error(code, "numeric evidence is not finite")
    return number


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            for pair in walk(item):
                yield pair
    elif isinstance(value, (list, tuple)):
        for item in value:
            for pair in walk(item):
                yield pair


def contains_key(value, wanted):
    return any(key == wanted for key, _item in walk(value))


def reject_sequence_text(value):
    """Refuse sequence or tensor payloads in manifests, records, and failure text."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in SEQUENCE_TEXT_KEYS:
                raise M7Error("incomplete_evidence_or_manifest", "evidence contains sequence text")
            reject_sequence_text(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_sequence_text(item)
    elif isinstance(value, str):
        if BODY_PATTERN.fullmatch(value) is not None and len(value) >= 8:
            raise M7Error("incomplete_evidence_or_manifest", "evidence contains sequence text")
    return True


# ------------------------------------------------------------------ reused M6 contract

_M6_CONTRACT = None


def m6_contract():
    """Load the accepted M6 contract by its tracked path. Constants are not copied."""
    global _M6_CONTRACT
    if _M6_CONTRACT is None:
        path = os.path.join(MRES_ROOT, M6_CONTRACT_RELATIVE)
        spec = importlib.util.spec_from_file_location("m6_pilot_contract_for_m7", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if os.path.realpath(module.__file__) != os.path.realpath(path):
            raise M7Error("identity_mismatch", "M6 contract did not resolve to the tracked file")
        _M6_CONTRACT = module
    return _M6_CONTRACT


def translate_m6(operation):
    """Run an M6 operation and re-raise its error as an M7 error with the same code."""
    contract = m6_contract()
    try:
        return operation()
    except contract.M6PilotError as exc:
        raise M7Error(exc.code, exc.detail, stage=exc.stage, update=exc.update, microbatch=exc.microbatch)


def load_config_bytes(raw):
    return translate_m6(lambda: m6_contract().load_config_bytes(raw))


# ------------------------------------------------------------------ path denial


def normalise_path_text(path):
    text = unicodedata.normalize("NFKC", str(path)).replace("\\", "/")
    return text


def path_is_ref_or_eval(path):
    """Case-insensitive REF and EVAL denial on the path text. No filesystem access."""
    for part in normalise_path_text(path).split("/"):
        folded = part.casefold()
        if folded == "":
            continue
        if folded in ("ref.csv", "eval.csv"):
            return True
        tokens = [token for token in re.split(r"[._\-\s]+", folded) if token != ""]
        if any(token in ("ref", "eval") for token in tokens):
            return True
    return False


def path_is_obsolete_repository_local(path):
    return m6_contract().path_is_obsolete_repository_local(normalise_path_text(path))


def _within(path, root):
    path = os.path.normpath(path)
    root = os.path.normpath(root)
    return path == root or path.startswith(root.rstrip("/") + "/")


def path_is_sibling_evidence(path, bound_output=None, allowed=(), run_root=RUN_ROOT):
    """True for a run-root path that is neither the bound output nor an allowed input."""
    text = os.path.normpath(normalise_path_text(path))
    if not _within(text, run_root):
        return False
    if bound_output is not None and _within(text, bound_output):
        return False
    for root in allowed:
        if _within(text, root):
            return False
    return True


def role_path_table():
    contract = m6_contract()
    return {
        "TRAIN_TEXT": ("exact", contract.FUTURE_TRAIN_TEXT_PATH),
        "VALIDATION_CSV": ("exact", contract.FUTURE_VALIDATION_CSV_PATH),
        "VALIDATION_ARTIFACT": ("tree", contract.ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY),
        "B1_INITIALISATION": ("tree", os.path.join(RNAGENESIS_ROOT, contract.B1_RELATIVE_PATH)),
        "FROZEN_ENCDEC": ("tree", os.path.join(RNAGENESIS_ROOT, contract.ENCDEC_RELATIVE_PATH)),
        "OWN_OUTPUT": ("bound", None),
    }


def assert_path_permitted(path, role, bound_output=None, realpath=None, run_root=RUN_ROOT):
    """Refuse a forbidden path before any filesystem open.

    REF and EVAL (any case, any spelling the tokenizer reads), obsolete
    repository-local data, and sibling evidence directories are refused on the
    path text and again on its resolved form. ``realpath`` does not open the
    target. A path must then match the single location its role allows.
    """
    if role in ("REF", "EVAL"):
        raise M7Error("ref_or_eval_access", "REF and EVAL are refused before open")
    candidates = [normalise_path_text(path)]
    if realpath is not None:
        resolved = normalise_path_text(realpath(str(path)))
        if resolved not in candidates:
            candidates.append(resolved)
    table = role_path_table()
    if role not in table:
        raise M7Error("unexpected_biological_path_or_role", "the role is not an M7 input")
    kind, expected = table[role]
    allowed_inputs = (table["VALIDATION_ARTIFACT"][1],) if role == "VALIDATION_ARTIFACT" else ()
    for text in candidates:
        if path_is_ref_or_eval(text):
            raise M7Error("ref_or_eval_access", "REF and EVAL are refused before open")
        if path_is_obsolete_repository_local(text):
            raise M7Error("unexpected_biological_path_or_role", "obsolete repository-local data is refused before open")
        if M6_EVIDENCE_NAME_PATTERN.search(text) is not None:
            raise M7Error("sibling_evidence_access", "M6 and sibling evidence is refused before open")
        if path_is_sibling_evidence(text, bound_output, allowed_inputs, run_root):
            raise M7Error("sibling_evidence_access", "a sibling evidence directory is refused before open")
        if kind == "exact" and os.path.normpath(text) != expected:
            raise M7Error("unexpected_biological_path_or_role", "the path is not the pinned input")
        if kind == "tree" and not _within(text, expected):
            raise M7Error("unexpected_biological_path_or_role", "the path is outside the pinned input")
        if kind == "bound" and (bound_output is None or not _within(text, bound_output)):
            raise M7Error("unexpected_biological_path_or_role", "the path is outside the bound output")
    return os.path.normpath(candidates[0])


def open_after_denial(path, role, opener, bound_output=None, realpath=None, run_root=RUN_ROOT):
    """The only route to an input open. ``opener`` is not called when denial fires."""
    assert_path_permitted(path, role, bound_output, realpath, run_root)
    return opener(path)


def assert_initialisation_input(path, weight_sha256=None):
    """M6 checkpoints are never an M7 initialisation or resume input."""
    text = normalise_path_text(path)
    if M6_EVIDENCE_NAME_PATTERN.search(text) is not None or M6_CHECKPOINT_NAME_PATTERN.search(text) is not None:
        raise M7Error("m6_checkpoint_forbidden", "an M6 checkpoint is not an M7 initialisation or resume input")
    if path_is_ref_or_eval(text):
        raise M7Error("ref_or_eval_access", "REF and EVAL are refused before open")
    if weight_sha256 in M6_FORBIDDEN_WEIGHT_SHA256:
        raise M7Error("m6_checkpoint_forbidden", "the weight hash is a forbidden M6 checkpoint")
    return True


def assert_not_m6_weight(weight_sha256):
    if weight_sha256 in M6_FORBIDDEN_WEIGHT_SHA256:
        raise M7Error("m6_checkpoint_forbidden", "the weight hash is a forbidden M6 checkpoint")
    return True


# ------------------------------------------------------------------ filesystem safety


def assert_no_symlink_ancestry(path, lstat=None, must_exist=True, code="checkpoint_ancestry_unsafe"):
    """Every component from the root to ``path`` must be a real directory (or the leaf).

    ``lstat`` never follows a link. A missing leaf is allowed only when
    ``must_exist`` is false; a missing ancestor never is.
    """
    lstat = os.lstat if lstat is None else lstat
    absolute = os.path.abspath(path)
    components = []
    current = absolute
    while True:
        components.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    components.reverse()
    for index, component in enumerate(components):
        last = index == len(components) - 1
        try:
            measured = lstat(component)
        except FileNotFoundError:
            if last and not must_exist:
                return absolute
            raise M7Error(code, "a path component is missing")
        if stat.S_ISLNK(measured.st_mode):
            raise M7Error(code, "a path component is a symlink")
        if not last and not stat.S_ISDIR(measured.st_mode):
            raise M7Error(code, "a path ancestor is not a directory")
    return absolute


def file_signature(measured):
    """The identity of a file as ``lstat`` reports it: size, mtime, inode, device and link count."""
    return {
        "device": int(measured.st_dev),
        "inode": int(measured.st_ino),
        "link_count": int(measured.st_nlink),
        "mtime_ns": int(measured.st_mtime_ns),
        "size": int(measured.st_size),
    }


def inspect_regular_file(path, lstat=None, require_single_link=False, expected_size=None):
    """Symlink-safe identity of one file, taken before it is read or hashed.

    Every ancestor must be a real directory, the leaf must be a regular file and
    not a symlink (``lstat`` never follows), and its size must match the pin when
    one is given. ``require_single_link`` applies the single-hard-link policy used
    for evidence this package writes or consumes (checkpoint members and the
    sealed replicate manifest); external pinned assets may be hard-linked, as a
    conda environment's are, and their link count is recorded and rechecked.
    The returned signature is compared again after use with ``recheck_file``.
    """
    lstat = os.lstat if lstat is None else lstat
    assert_no_symlink_ancestry(os.path.dirname(path), lstat, code="asset_inspection_unsafe")
    try:
        measured = lstat(path)
    except FileNotFoundError:
        raise M7Error("asset_inspection_unsafe", "a required file is missing")
    if stat.S_ISLNK(measured.st_mode):
        raise M7Error("asset_inspection_unsafe", "a required file is a symlink")
    if not stat.S_ISREG(measured.st_mode):
        raise M7Error("asset_inspection_unsafe", "a required file is not a regular file")
    signature = file_signature(measured)
    if require_single_link and signature["link_count"] != 1:
        raise M7Error("asset_inspection_unsafe", "a required file has more than one hard link")
    if expected_size is not None and signature["size"] != int(expected_size):
        raise M7Error("asset_inspection_unsafe", "a required file does not have its pinned size")
    return signature


def recheck_file(path, signature, lstat=None):
    """The file must still be exactly what ``inspect_regular_file`` saw."""
    lstat = os.lstat if lstat is None else lstat
    try:
        measured = lstat(path)
    except FileNotFoundError:
        raise M7Error("asset_inspection_unsafe", "a required file disappeared while it was in use")
    if stat.S_ISLNK(measured.st_mode) or not stat.S_ISREG(measured.st_mode) or file_signature(measured) != signature:
        raise M7Error("asset_inspection_unsafe", "a required file changed while it was in use")
    return True


def hash_regular_file(path, lstat=None, hash_file=None, require_single_link=False, expected_size=None):
    """Inspect, hash, and recheck one file. Returns its digest and signature."""
    signature = inspect_regular_file(path, lstat, require_single_link, expected_size)
    digest = (hash_file or stream_sha256)(path)
    recheck_file(path, signature, lstat)
    return digest, signature


def read_regular_file(path, lstat=None, read_bytes=None, require_single_link=False, expected_size=None, expected_sha256=None):
    """Inspect, read and recheck one file. The bytes must match the pinned size and hash."""
    signature = inspect_regular_file(path, lstat, require_single_link, expected_size)

    def default_read(target):
        with open(target, "rb") as handle:
            return handle.read()

    data = bytes((read_bytes or default_read)(path))
    recheck_file(path, signature, lstat)
    if len(data) != signature["size"]:
        raise M7Error("asset_inspection_unsafe", "a required file changed size while it was read")
    if expected_sha256 is not None and sha256_bytes(data) != expected_sha256:
        raise M7Error("asset_inspection_unsafe", "a required file does not have its pinned hash")
    return data, signature


def stream_sha256(path, chunk_bytes=STREAM_CHUNK_BYTES, require_single_link=False):
    """Bounded streaming digest of one regular, non-symlink file.

    The file is opened with ``O_NOFOLLOW``. Its descriptor must name a regular
    file. The size, modification time and inode must not change while it is
    read. No chunk larger than ``chunk_bytes`` is held, so a multi-gigabyte
    weight file is never one bytes object.
    """
    if isinstance(chunk_bytes, bool) or not isinstance(chunk_bytes, int) or chunk_bytes <= 0 or chunk_bytes > 64 * MEBIBYTE:
        raise M7Error("filesystem_error", "digest chunk size is not bounded")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise M7Error("filesystem_error", "a file could not be opened without following a link")
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise M7Error("checkpoint_ancestry_unsafe", "digest target is not a regular file")
        if require_single_link and before.st_nlink != 1:
            raise M7Error("checkpoint_ancestry_unsafe", "digest target has more than one hard link")
        hasher = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, chunk_bytes)
            if not chunk:
                break
            total += len(chunk)
            hasher.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (before.st_size, before.st_mtime_ns, before.st_ino, before.st_dev) != (after.st_size, after.st_mtime_ns, after.st_ino, after.st_dev):
        raise M7Error("checkpoint_save_reload_incompatibility", "a file changed while it was hashed")
    if total != before.st_size:
        raise M7Error("checkpoint_save_reload_incompatibility", "a file was not read completely")
    return hasher.hexdigest()


def fsync_checkpoint_tree(checkpoint_dir):
    """Flush every checkpoint file and directory. A read-only descriptor is enough to ``fsync`` a file."""
    expected = _checkpoint_expected_layout()
    for head in sorted(expected):
        base = checkpoint_dir if head == "" else os.path.join(checkpoint_dir, head)
        for leaf in expected[head]:
            descriptor = os.open(os.path.join(base, leaf), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        fsync_directory(base)
    fsync_directory(os.path.dirname(checkpoint_dir))


def fsync_directory(path):
    """Flush a directory entry. A rename or create is durable only after this."""
    descriptor = os.open(path, DIRECTORY_FSYNC_FLAGS)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_atomic_bytes(directory, name, blob, sync_directory=True):
    """Write one file through an exclusive temporary, ``fsync``, ``replace``, directory ``fsync``.

    A short ``os.write`` continues until every byte is written. Any failure,
    including ``KeyboardInterrupt``, removes the temporary file; the target is
    never left half written.
    """
    target = os.path.join(directory, name)
    temporary = target + ".partial"
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        try:
            view = memoryview(blob)
            while len(view) > 0:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short write made no progress")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, target)
        if sync_directory:
            fsync_directory(directory)
    except BaseException:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise
    return target


def write_atomic_json(directory, name, payload, sync_directory=True):
    return write_atomic_bytes(directory, name, canonical_json(payload), sync_directory)


def assert_output_directory_shape(path, run_root=RUN_ROOT):
    if not isinstance(path, str) or path != os.path.normpath(path):
        raise M7Error("execution_not_authorised", "output directory is not a normalised absolute path")
    prefix = run_root.rstrip("/") + "/"
    if not path.startswith(prefix):
        raise M7Error("execution_not_authorised", "output directory is not under the run root")
    name = path[len(prefix):]
    if name == "" or "/" in name or name in (".", ".."):
        raise M7Error("execution_not_authorised", "output directory is not a direct child of the run root")
    if path_is_ref_or_eval(path) or M6_EVIDENCE_NAME_PATTERN.search(path) is not None:
        raise M7Error("sibling_evidence_access", "output directory name collides with REF, EVAL, or M6 evidence")
    return name


def consume_output_directory(output_directory, payload, run_root=RUN_ROOT, lstat=None):
    """Create the one bound directory, record consumption, and make both durable.

    ``os.mkdir`` fails on an existing path, so a second use of the same output
    directory is refused. The consumption record, the directory, and the run
    root are flushed before this returns.
    """
    assert_output_directory_shape(output_directory, run_root)
    lstat = os.lstat if lstat is None else lstat
    assert_no_symlink_ancestry(os.path.dirname(output_directory), lstat, must_exist=True)
    try:
        lstat(output_directory)
    except FileNotFoundError:
        pass
    else:
        raise M7Error("authorization_reuse", "the bound output directory already exists")
    try:
        os.mkdir(output_directory)
    except FileExistsError:
        raise M7Error("authorization_reuse", "the bound output directory already exists")
    try:
        write_atomic_json(output_directory, CONSUMPTION_RECORD_NAME, payload)
        fsync_directory(os.path.dirname(output_directory))
    except BaseException as exc:
        # The directory now exists, so the entry is consumed. Mark the error so a
        # caller records a failure inside it. An interrupt is never swallowed.
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            exc.directory_created = True
            raise
        error = M7Error("authorization_reuse", "the bound directory was created but consumption could not be recorded")
        error.directory_created = True
        raise error
    return output_directory


# ------------------------------------------------------------------ strict checkpoint tree


def _checkpoint_expected_layout():
    expected = {}
    for member in CHECKPOINT_MEMBERS:
        head, _, tail = member.rpartition("/")
        expected.setdefault(head, []).append(tail)
    return expected


def observe_checkpoint_tree_strict(checkpoint_dir, bound_output=None, lstat=None, listdir=None, check_device=True):
    """Exact checkpoint inventory with symlink, hard-link, and device checks.

    The checkpoint must be a direct child of the bound output when one is
    given. Every ancestor is a real directory. The root and each expected
    subdirectory are real directories on one device. Each leaf is a regular,
    non-symlink file with ``st_nlink == 1`` on that device. An extra, missing,
    or special entry fails. Messages never name the offending entry. The
    returned signature (size, mtime_ns, inode, device, link count) lets a later
    call detect a change.
    """
    lstat = os.lstat if lstat is None else lstat
    listdir = os.listdir if listdir is None else listdir
    absolute = assert_no_symlink_ancestry(checkpoint_dir, lstat)
    if bound_output is not None and os.path.dirname(absolute) != os.path.abspath(bound_output):
        raise M7Error("checkpoint_overwrite_risk", "checkpoint directory is not a direct child of the bound output")
    root = lstat(absolute)
    if not stat.S_ISDIR(root.st_mode):
        raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint root is not a real directory")
    if bound_output is not None and check_device and lstat(os.path.abspath(bound_output)).st_dev != root.st_dev:
        raise M7Error("checkpoint_ancestry_unsafe", "checkpoint root is on another device than the bound output")
    expected = _checkpoint_expected_layout()
    top = set(expected.get("", [])) | {name for name in expected if name != ""}
    if set(listdir(absolute)) != top:
        raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint tree has an unexpected or missing entry")
    signatures = {}
    for head in sorted(expected):
        base = absolute if head == "" else os.path.join(absolute, head)
        if head != "":
            measured_directory = lstat(base)
            if not stat.S_ISDIR(measured_directory.st_mode):
                raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint subdirectory is not a real directory")
            if check_device and measured_directory.st_dev != root.st_dev:
                raise M7Error("checkpoint_ancestry_unsafe", "checkpoint subdirectory is on another device")
            if set(listdir(base)) != set(expected[head]):
                raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint subdirectory has an unexpected or missing entry")
        for leaf in expected[head]:
            try:
                measured = lstat(os.path.join(base, leaf))
            except FileNotFoundError:
                raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint tree is missing a member")
            if stat.S_ISLNK(measured.st_mode) or not stat.S_ISREG(measured.st_mode):
                raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint member is not a regular file")
            if measured.st_nlink != 1:
                raise M7Error("checkpoint_ancestry_unsafe", "checkpoint member has more than one hard link")
            if check_device and measured.st_dev != root.st_dev:
                raise M7Error("checkpoint_ancestry_unsafe", "checkpoint member is on another device")
            member = leaf if head == "" else head + "/" + leaf
            signatures[member] = (
                int(measured.st_size),
                int(measured.st_mtime_ns),
                int(measured.st_ino),
                int(measured.st_dev),
                int(measured.st_nlink),
            )
    return signatures


# ------------------------------------------------------------------ free space


def free_space_budget(path, checkpoint_count, weight_bytes=None, statvfs=None):
    """Free-space budget for one seed. The calculation is integer arithmetic.

    Per checkpoint: the weight file plus a metadata allowance. For the seed:
    that times the checkpoint count, plus a log and manifest allowance. The
    requirement adds ten percent and a fixed reserve. ``statvfs`` reports the
    space available to an unprivileged writer.
    """
    contract = m6_contract()
    statvfs = os.statvfs if statvfs is None else statvfs
    if weight_bytes is None:
        weight_bytes = contract.B1_WEIGHT_BYTES
    if isinstance(checkpoint_count, bool) or not isinstance(checkpoint_count, int) or checkpoint_count < 1:
        raise M7Error("insufficient_free_space", "checkpoint count is invalid")
    per_checkpoint = int(weight_bytes) + 4 * MEBIBYTE
    log_allowance = 2 * GIBIBYTE
    subtotal = per_checkpoint * checkpoint_count + log_allowance
    reserve = 20 * GIBIBYTE
    required = subtotal + subtotal // 10 + reserve
    measured = statvfs(path)
    available = int(measured.f_bavail) * int(measured.f_frsize)
    return {
        "available_bytes": available,
        "checkpoint_count": checkpoint_count,
        "log_allowance_bytes": log_allowance,
        "per_checkpoint_bytes": per_checkpoint,
        "required_bytes": required,
        "reserve_bytes": reserve,
        "sufficient": available >= required,
        "weight_bytes": int(weight_bytes),
    }


def assert_free_space(path, checkpoint_count, weight_bytes=None, statvfs=None):
    budget = free_space_budget(path, checkpoint_count, weight_bytes, statvfs)
    if budget["sufficient"] is not True:
        raise M7Error("insufficient_free_space", "free space is below the checkpoint budget")
    return budget


# ------------------------------------------------------------------ environment

# Only these parent variables reach a child. Every other name is dropped. The one
# exception is LD_LIBRARY_PATH, and only as the exact value an authorisation
# binds (see ``resolve_ld_library_path``); an ambient value is never inherited.
# PATH is deliberately absent: the child PATH is the constant ``FIXED_CHILD_PATH``
# and parent PATH text is never copied.
# CUDA_MODULE_LOADING is deliberately absent. The child sets the fixed control
# below itself; an ambient parent value is never copied and cannot replace it.
ENVIRONMENT_ALLOW_LIST = ("LANG", "LC_ALL", "LC_CTYPE", "TZ")
# Pinned PyTorch 2.1.2+cu121 assigns this exact value during CUDA lazy
# initialisation when the variable is absent. The child sets it first, so that
# assignment is not a stray name. The worker allow-list admits the name only
# after ``assert_fixed_child_environment_controls`` has required this value.
CUDA_MODULE_LOADING_NAME = "CUDA_MODULE_LOADING"
CUDA_MODULE_LOADING_VALUE = "LAZY"
FIXED_CHILD_ENVIRONMENT_CONTROLS = {
    CUDA_MODULE_LOADING_NAME: CUDA_MODULE_LOADING_VALUE,
}
UNEXPECTED_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,64}$")
UNEXPECTED_ENVIRONMENT_NAME_LIMIT = 8
LD_LIBRARY_PATH_NAME = "LD_LIBRARY_PATH"
LD_LIBRARY_PATH_MAXIMUM_LENGTH = 4096
LD_LIBRARY_PATH_COMPONENT = re.compile(r"^/[A-Za-z0-9._+@=,%/\-]*$")
LD_LIBRARY_PATH_RECORD_KEYS = ("bound", "passed_to_child", "sha256")
REJECTED_ENVIRONMENT_EXACT = (
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "PYTHONINSPECT",
    "PYTHONUSERBASE",
    "PYTHONEXECUTABLE",
    "PYTHONBREAKPOINT",
    "LD_PRELOAD",
    "LD_AUDIT",
    "DYLD_INSERT_LIBRARIES",
)
REJECTED_ENVIRONMENT_CREDENTIAL_EXACT = (
    "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
    "HUGGINGFACE_HUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "WANDB_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AZURE_CLIENT_SECRET",
    "SSH_PRIVATE_KEY",
)
REJECTED_ENVIRONMENT_CREDENTIAL_PATTERN = re.compile(
    r"(^|_)(TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?|APIKEY|API_KEY|ACCESS_KEY|PRIVATE_KEY)(_|$)", re.IGNORECASE
)
REJECTED_ENVIRONMENT_PREFIXES = ("AWS_", "AZURE_", "GCP_", "GOOGLE_CLOUD_")
BENIGN_GIT_VARIABLES = ("GIT_EDITOR", "GIT_SEQUENCE_EDITOR", "GIT_TERMINAL_PROMPT")
OFFLINE_CONTROLS = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1"}
CUDA_DEVICE_ORDER = "PCI_BUS_ID"
ISOLATED_DIRECTORIES = (
    "isolated_home",
    "isolated_tmp",
    "isolated_runtime_cache",
    "python_pycache",
)


def assert_parent_environment(parent, physical_gpu=None):
    """Refuse an ambient variable that could redirect imports, git, or leak a credential."""
    if not isinstance(parent, dict):
        raise M7Error("environment_rejected", "parent environment is missing")
    for name in parent:
        upper = name.upper()
        if name in REJECTED_ENVIRONMENT_EXACT or upper in REJECTED_ENVIRONMENT_EXACT:
            raise M7Error("environment_rejected", "an import- or library-redirecting variable is set")
        if upper.startswith("GIT_") and upper not in BENIGN_GIT_VARIABLES:
            raise M7Error("environment_rejected", "a git redirecting variable is set")
        if upper in REJECTED_ENVIRONMENT_CREDENTIAL_EXACT or REJECTED_ENVIRONMENT_CREDENTIAL_PATTERN.search(upper) is not None:
            raise M7Error("environment_rejected", "a credential variable is set")
        if any(upper.startswith(prefix) for prefix in REJECTED_ENVIRONMENT_PREFIXES):
            raise M7Error("environment_rejected", "a cloud credential variable is set")
    if physical_gpu is not None:
        if "CUDA_VISIBLE_DEVICES" in parent and parent["CUDA_VISIBLE_DEVICES"] != str(physical_gpu):
            raise M7Error("environment_rejected", "inherited CUDA_VISIBLE_DEVICES conflicts with the authorisation")
        if "CUDA_DEVICE_ORDER" in parent and parent["CUDA_DEVICE_ORDER"] != CUDA_DEVICE_ORDER:
            raise M7Error("environment_rejected", "inherited CUDA_DEVICE_ORDER is not PCI_BUS_ID")
    return True


def assert_ld_library_path_value(value):
    """An authorisation-bound ``LD_LIBRARY_PATH`` value, judged on its text alone.

    Every colon-separated component is an absolute, normalised path. An empty
    component (which the loader reads as the working directory), a relative or
    ``..`` component, a space, a variable expansion, a REF or EVAL path, or an
    RNAGenesis cache path is refused. No filesystem access happens here.
    """
    if (
        not isinstance(value, str)
        or value == ""
        or len(value) > LD_LIBRARY_PATH_MAXIMUM_LENGTH
        or value != value.strip()
    ):
        raise M7Error("environment_rejected", "the LD_LIBRARY_PATH binding is not a bounded non-empty string")
    cache = os.path.join(RNAGENESIS_ROOT, ".cache")
    for component in value.split(":"):
        if component == "" or LD_LIBRARY_PATH_COMPONENT.fullmatch(component) is None or os.path.normpath(component) != component:
            raise M7Error("environment_rejected", "an LD_LIBRARY_PATH component is not an absolute normalised path")
        if path_is_ref_or_eval(component) or _within(component, cache):
            raise M7Error("environment_rejected", "an LD_LIBRARY_PATH component names a forbidden location")
    return value


def assert_ld_library_path_binding(value):
    """The entry field: ``None`` (no value reaches the child) or one exact value."""
    if value is None:
        return None
    return assert_ld_library_path_value(value)


def ld_library_path_digest(value):
    """SHA-256 of the exact UTF-8 value. The manifest records this, never the text."""
    return sha256_bytes(assert_ld_library_path_value(value).encode("utf-8"))


def unbound_ld_library_path_record():
    return {"bound": False, "passed_to_child": False, "sha256": None}


def assert_ld_library_path_record(record):
    record = exact_keys(record, LD_LIBRARY_PATH_RECORD_KEYS, "environment_rejected")
    if record["bound"] is False:
        if record["passed_to_child"] is not False or record["sha256"] is not None:
            raise M7Error("environment_rejected", "an unbound LD_LIBRARY_PATH record carries a value")
    elif record["bound"] is True:
        if record["passed_to_child"] is not True or not is_sha256(record["sha256"]):
            raise M7Error("environment_rejected", "a bound LD_LIBRARY_PATH record lacks its digest")
    else:
        raise M7Error("environment_rejected", "LD_LIBRARY_PATH record flags are not boolean")
    return record


def resolve_ld_library_path(parent, expected):
    """Match the live value against the authorisation binding and return its record.

    ``expected`` is ``None`` when the authorisation binds no value: nothing
    reaches the child and an ambient value is dropped. Otherwise the live value
    must be present and exactly equal to ``expected``; only then may that exact
    value enter the child. An absent, unexpected or changed value is refused.
    The error text never carries either value.
    """
    if not isinstance(parent, collections.abc.Mapping):
        raise M7Error("environment_rejected", "parent environment is missing")
    parent = dict(parent)
    if expected is None:
        return unbound_ld_library_path_record()
    assert_ld_library_path_value(expected)
    live = parent.get(LD_LIBRARY_PATH_NAME)
    if live is None:
        raise M7Error("environment_rejected", "LD_LIBRARY_PATH is required by the authorisation but is absent")
    if live != expected:
        raise M7Error("environment_rejected", "LD_LIBRARY_PATH differs from the authorisation binding")
    return {"bound": True, "passed_to_child": True, "sha256": ld_library_path_digest(expected)}


def observe_child_ld_library_path(environ, expected):
    """Worker-side counterpart. An unbound authorisation lets no value through."""
    if not isinstance(environ, collections.abc.Mapping):
        raise M7Error("environment_rejected", "child environment is missing")
    environ = dict(environ)
    if expected is None:
        if LD_LIBRARY_PATH_NAME in environ:
            raise M7Error("environment_rejected", "an unbound LD_LIBRARY_PATH reached the child")
        return unbound_ld_library_path_record()
    return resolve_ld_library_path(environ, expected)


# ------------------------------------------------------------------ pinned interpreter

PINNED_ENVIRONMENT_PREFIX = "/home/laura/miniconda3/envs/rnagenesis-h200"
PINNED_INTERPRETER_NAME = "python3.8"
INTERPRETER_KEYS = ("path", "resolved_path", "sha256", "size")


def assert_interpreter_binding(value):
    """The entry field: the exact interpreter path and the identity of the file it resolves to.

    The path must be the pinned RNAGenesis H200 interpreter. It may be a symlink
    inside that environment, but it must resolve to a ``python3.8`` file inside
    the same environment. The identity is the resolved path, the SHA-256 and the
    size of that file. Judged on text alone; nothing is opened here.
    """
    value = exact_keys(value, INTERPRETER_KEYS, "interpreter_rejected")
    if value["path"] != PINNED_PYTHON:
        raise M7Error("interpreter_rejected", "the interpreter path is not the pinned RNAGenesis H200 interpreter")
    resolved = value["resolved_path"]
    if (
        not isinstance(resolved, str)
        or os.path.normpath(resolved) != resolved
        or not _within(resolved, PINNED_ENVIRONMENT_PREFIX)
        or os.path.basename(resolved) != PINNED_INTERPRETER_NAME
    ):
        raise M7Error("interpreter_rejected", "the interpreter does not resolve to python3.8 in the pinned environment")
    if not is_sha256(value["sha256"]) or isinstance(value["size"], bool) or not isinstance(value["size"], int) or value["size"] <= 0:
        raise M7Error("interpreter_rejected", "the interpreter identity is incomplete")
    return value


def observe_interpreter(path=None, lstat=None, realpath=None, hash_file=None):
    """Observe the interpreter that would run the scientific code (mocked in tests).

    The path must equal the pinned path exactly. It is resolved, the resolution
    is judged against the pinned environment before any open, the ancestry of the
    resolved file is walked with ``lstat``, the leaf must be a regular file, and
    its size and hash are recorded and rechecked.
    """
    path = PINNED_PYTHON if path is None else path
    if path != PINNED_PYTHON:
        raise M7Error("interpreter_rejected", "the interpreter path is not the pinned RNAGenesis H200 interpreter")
    resolved = (realpath or os.path.realpath)(path)
    assert_interpreter_binding({"path": path, "resolved_path": resolved, "sha256": "0" * 64, "size": 1})
    digest, signature = hash_regular_file(resolved, lstat, hash_file)
    return {"path": path, "resolved_path": resolved, "sha256": digest, "size": signature["size"]}


def assert_interpreter_matches(observed, bound):
    """An observation must equal the authorised binding exactly. The text never repeats either."""
    assert_interpreter_binding(observed)
    assert_interpreter_binding(bound)
    if dict(observed) != dict(bound):
        raise M7Error("interpreter_rejected", "the interpreter is not the one the authorisation binds")
    return True


# ------------------------------------------------------------------ fixed PATH and trusted executables

# The child PATH is a constant. It never inherits the parent PATH text, and no
# ambient PATH component from the invoking shell is carried into it. The
# deliberately pinned environment's bin directory comes first, so a by-name lookup
# made by the pinned interpreter finds that environment's own tools; /usr/bin and
# /bin follow. Every component is absolute and normalised, and /usr/local/bin is
# absent. The pinned environment is the only user-space component, and it is
# pinned on purpose.
FIXED_CHILD_PATH = PINNED_ENVIRONMENT_PREFIX + "/bin:/usr/bin:/bin"
# Git and nvidia-smi are always invoked by these absolute paths, never by name.
GIT_EXECUTABLE = "/usr/bin/git"
NVIDIA_SMI_EXECUTABLE = "/usr/bin/nvidia-smi"
TRUSTED_EXECUTABLES = (GIT_EXECUTABLE, NVIDIA_SMI_EXECUTABLE)
TRUSTED_DIRECTORIES = ("/usr", "/usr/bin")
GPU_QUERY_FIELDS = "--query-gpu=index,uuid,pci.bus_id"
GPU_QUERY_FORMAT = "--format=csv,noheader"


def assert_fixed_path(value):
    """``PATH`` must be the fixed constant: absolute, normalised components, nothing else."""
    if value != FIXED_CHILD_PATH:
        raise M7Error("environment_rejected", "PATH is not the fixed child PATH")
    for component in value.split(":"):
        if component == "" or not component.startswith("/") or os.path.normpath(component) != component:
            raise M7Error("environment_rejected", "a fixed PATH component is not an absolute normalised path")
    return value


def pin_process_path(environ=None):
    """Replace ``PATH`` of this process (or of the given mapping) with the fixed constant.

    A launcher calls this after its inactive gate, so any accepted upstream code
    that still starts ``git`` or ``nvidia-smi`` by name resolves it through the
    fixed directories and not through the invoking shell's text.
    """
    target = os.environ if environ is None else environ
    target["PATH"] = FIXED_CHILD_PATH
    return FIXED_CHILD_PATH


def tool_environment():
    """A fresh environment for a trusted tool. Nothing is copied from the parent."""
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": FIXED_CHILD_PATH,
    }


def assert_trusted_executable(path, lstat=None):
    """The fixed absolute path of ``git`` or ``nvidia-smi``, validated by ``lstat`` alone.

    Nothing is executed. The path must be one of the two constants. Every
    ancestor must be a real, root-owned directory that is not group- or
    world-writable. The leaf must be a regular, non-symlink, root-owned,
    executable file that is not group- or world-writable.
    """
    if path not in TRUSTED_EXECUTABLES:
        raise M7Error("environment_rejected", "the executable is not one of the fixed trusted tools")
    lstat = os.lstat if lstat is None else lstat
    assert_no_symlink_ancestry(os.path.dirname(path), lstat, code="environment_rejected")
    for directory in TRUSTED_DIRECTORIES:
        measured = lstat(directory)
        if measured.st_uid != 0 or measured.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise M7Error("environment_rejected", "a trusted tool directory is not root-owned and closed to other writers")
    try:
        measured = lstat(path)
    except FileNotFoundError:
        raise M7Error("environment_rejected", "a fixed trusted tool is missing")
    if stat.S_ISLNK(measured.st_mode) or not stat.S_ISREG(measured.st_mode):
        raise M7Error("environment_rejected", "a fixed trusted tool is not a regular file")
    if measured.st_uid != 0 or measured.st_mode & (stat.S_IWGRP | stat.S_IWOTH) or not measured.st_mode & stat.S_IXUSR:
        raise M7Error("environment_rejected", "a fixed trusted tool is not a root-owned executable closed to other writers")
    return file_signature(measured)


def run_trusted_tool(argv, cwd=None, run=None, lstat=None):
    """Run ``git`` or ``nvidia-smi`` by its absolute path, in a fresh environment, with no shell."""
    if not isinstance(argv, (list, tuple)) or not argv or any(not isinstance(item, str) for item in argv):
        raise M7Error("environment_rejected", "a trusted tool command is not a list of text")
    assert_trusted_executable(argv[0], lstat)
    runner = subprocess.run if run is None else run
    return runner(
        list(argv),
        cwd=cwd,
        env=tool_environment(),
        shell=False,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _git_completed(repo, args, run=None, lstat=None):
    if not isinstance(repo, str) or not repo.startswith("/") or os.path.normpath(repo) != repo:
        raise M7Error("git_status_unreadable", "the repository path is not an absolute normalised path")
    completed = run_trusted_tool([GIT_EXECUTABLE, "-C", repo] + [str(item) for item in args], None, run, lstat)
    if getattr(completed, "returncode", 1) != 0:
        raise M7Error("git_status_unreadable", "a git command failed")
    return completed.stdout


def run_git_bytes(repo, args, run=None, lstat=None):
    """Raw ``git`` standard output. The message of a failure never carries git's own text."""
    return bytes(_git_completed(repo, args, run, lstat))


def run_git(repo, args, run=None, lstat=None):
    """``git`` standard output as UTF-8 text, through the fixed absolute executable."""
    try:
        return run_git_bytes(repo, args, run, lstat).decode("utf-8")
    except UnicodeDecodeError:
        raise M7Error("git_status_unreadable", "git output is not UTF-8")


def nvidia_smi_query_argv(physical_gpu=None):
    """The accepted B1 GPU query with the executable replaced by its absolute path."""
    argv = [NVIDIA_SMI_EXECUTABLE, GPU_QUERY_FIELDS, GPU_QUERY_FORMAT]
    if physical_gpu is not None:
        if type(physical_gpu) is not int or physical_gpu < 0:
            raise M7Error("gpu_probe_invalid", "the physical GPU index is invalid")
        argv += ["-i", str(physical_gpu)]
    return argv


def live_gpu_probe(environ=None, run=None, lstat=None):
    """Read the authorised device with the absolute ``nvidia-smi``. Same result as the accepted M6 probe.

    Used in place of the accepted M6 probe, which starts ``nvidia-smi`` by name.
    ``run`` is injected by every test, so no test executes the tool.
    """
    environ = os.environ if environ is None else environ
    visible = environ.get("CUDA_VISIBLE_DEVICES")
    completed = run_trusted_tool(nvidia_smi_query_argv(None), None, run, lstat)
    if getattr(completed, "returncode", 1) != 0 or visible is None:
        raise M7Error("identity_mismatch", "physical GPU probe failed before training imports")
    try:
        text = bytes(completed.stdout).decode("utf-8")
    except UnicodeDecodeError:
        raise M7Error("gpu_probe_invalid", "the GPU probe output is not UTF-8")
    rows = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            rows.append({"index": int(parts[0]), "uuid": parts[1], "pci_bus": parts[2]})
        except ValueError:
            raise M7Error("gpu_probe_invalid", "a GPU probe row has no integer index")
    if visible not in {str(row["index"]) for row in rows}:
        raise M7Error("identity_mismatch", "CUDA_VISIBLE_DEVICES does not name a probed GPU")
    selected = [row for row in rows if str(row["index"]) == visible][0]
    return {
        "cuda_visible_devices": visible,
        "logical_device": LOGICAL_CUDA_DEVICE,
        "pci_bus": selected["pci_bus"],
        "physical_index": selected["index"],
        "uuid": selected["uuid"],
    }


def assert_pinned_interpreter_argv(argv):
    """A child command starts with the absolute pinned interpreter, never a name resolved through PATH."""
    if not isinstance(argv, (list, tuple)) or not argv or argv[0] != PINNED_PYTHON or not os.path.isabs(argv[0]):
        raise M7Error("python_interpreter_rejected", "the child command does not start with the absolute pinned interpreter")
    return True


def isolated_paths(output_directory):
    base = os.path.abspath(os.path.normpath(str(output_directory)))
    home = os.path.join(base, "isolated_home")
    cache = os.path.join(base, "isolated_runtime_cache")
    huggingface = os.path.join(cache, "huggingface")
    hub = os.path.join(huggingface, "hub")
    return {
        "HOME": home,
        "TMPDIR": os.path.join(base, "isolated_tmp"),
        "TEMP": os.path.join(base, "isolated_tmp"),
        "TMP": os.path.join(base, "isolated_tmp"),
        "XDG_CONFIG_HOME": os.path.join(home, ".config"),
        "XDG_DATA_HOME": os.path.join(home, ".local", "share"),
        "XDG_CACHE_HOME": cache,
        "PYTHONPYCACHEPREFIX": os.path.join(base, "python_pycache"),
        "HF_HOME": huggingface,
        "HUGGINGFACE_HUB_CACHE": hub,
        "HF_HUB_CACHE": hub,
        "HF_ASSETS_CACHE": os.path.join(huggingface, "assets"),
        "HF_MODULES_CACHE": os.path.join(huggingface, "modules"),
        "TRANSFORMERS_CACHE": hub,
        "TORCH_HOME": os.path.join(cache, "torch"),
        "TRITON_CACHE_DIR": os.path.join(cache, "triton"),
        "CUDA_CACHE_PATH": os.path.join(cache, "cuda"),
        "MPLCONFIGDIR": os.path.join(cache, "matplotlib"),
    }


def build_child_environment(parent, physical_gpu, output_directory, ld_library_path=None):
    """A fresh environment from an allow-list. The parent mapping is never copied wholesale.

    ``ld_library_path`` is the authorisation-bound value, or ``None``. The live
    parent value must match it exactly before it is passed on.
    ``CUDA_MODULE_LOADING`` is not read from the parent. The fixed control is
    assigned here, after every other child assignment, so an ambient value
    cannot replace it.
    """
    assert_parent_environment(parent, physical_gpu)
    resolve_ld_library_path(parent, ld_library_path)
    resolved_output = os.path.realpath(output_directory)
    for root in (MRES_ROOT, RNAGENESIS_ROOT):
        if _within(resolved_output, os.path.realpath(root)):
            raise M7Error("environment_rejected", "output directory resolves inside a git repository")
    child = {}
    for name in ENVIRONMENT_ALLOW_LIST:
        if name in parent and name not in FIXED_CHILD_ENVIRONMENT_CONTROLS:
            child[name] = parent[name]
    child["PATH"] = FIXED_CHILD_PATH
    if ld_library_path is not None:
        child[LD_LIBRARY_PATH_NAME] = ld_library_path
    child["PYTHONDONTWRITEBYTECODE"] = "1"
    child["PYTHONNOUSERSITE"] = "1"
    child.update(OFFLINE_CONTROLS)
    child["CUDA_VISIBLE_DEVICES"] = str(physical_gpu)
    child["CUDA_DEVICE_ORDER"] = CUDA_DEVICE_ORDER
    paths = isolated_paths(output_directory)
    for key, value in paths.items():
        resolved = os.path.realpath(value)
        if not _within(resolved, resolved_output):
            raise M7Error("environment_rejected", "an isolated path escaped the output directory")
        child[key] = value
    for name, value in FIXED_CHILD_ENVIRONMENT_CONTROLS.items():
        child[name] = value
    return child


def assert_fixed_child_environment_controls(environ):
    """Require each fixed control to be present with exactly its constant value.

    A missing name, a non-text value, an empty value, a differently cased value
    and any alternative value fail closed. The observed value is never repeated.
    This is the only check that admits the control name to the worker allow-list.
    """
    if not isinstance(environ, collections.abc.Mapping):
        raise M7Error("environment_rejected", "child environment is missing")
    for name, expected in FIXED_CHILD_ENVIRONMENT_CONTROLS.items():
        if name not in environ:
            raise M7Error("environment_rejected", "fixed child control is missing: " + name)
        value = environ[name]
        if not isinstance(value, str):
            raise M7Error("environment_rejected", "fixed child control is not text: " + name)
        if value == "":
            raise M7Error("environment_rejected", "fixed child control is empty: " + name)
        if value != expected and value.casefold() == expected.casefold():
            raise M7Error("environment_rejected", "fixed child control differs in case: " + name)
        if value != expected:
            raise M7Error("environment_rejected", "fixed child control is not the required value: " + name)
    return True


def unexpected_environment_detail(names):
    """A rejection detail that names stray variables without their values.

    Names are sorted. At most ``UNEXPECTED_ENVIRONMENT_NAME_LIMIT`` are listed.
    A name that is not a short identifier, or that looks like sequence text, is
    replaced by a placeholder. Further names are counted and not listed. The
    accepted environment is unchanged: every name outside the allow-list still
    fails.
    """
    ordered = sorted(names, key=lambda item: "" if item is None else str(item))
    shown = []
    for name in ordered[:UNEXPECTED_ENVIRONMENT_NAME_LIMIT]:
        text = name if isinstance(name, str) else ""
        if UNEXPECTED_ENVIRONMENT_NAME.fullmatch(text) is None or SEQUENCE_RUN_PATTERN.search(text) is not None:
            shown.append("<omitted-name>")
        else:
            shown.append(text)
    detail = "the worker environment holds " + str(len(ordered)) + " names outside the allow-list"
    if shown:
        detail += ": " + ",".join(shown)
    hidden = len(ordered) - len(shown)
    if hidden > 0:
        detail += " +" + str(hidden)
    return detail


def assert_child_environment(environ, output_directory, ld_library_path=None, ld_library_path_pending=False):
    """Worker-side check that the allow-listed, isolated environment is in force.

    ``ld_library_path`` is the bound value when it is known. A worker that
    checks isolation before it has read its entry passes
    ``ld_library_path_pending=True``: the name is then tolerated if its value is
    well formed, and ``observe_child_ld_library_path`` makes the exact check once
    the entry is known.
    """
    if environ.get("PYTHONDONTWRITEBYTECODE") != "1" or environ.get("PYTHONNOUSERSITE") != "1":
        raise M7Error("environment_rejected", "bytecode writing or the user site is not disabled")
    for key, value in OFFLINE_CONTROLS.items():
        if environ.get(key) != value:
            raise M7Error("environment_rejected", "Hugging Face offline control is not set: " + key)
    for key, value in isolated_paths(output_directory).items():
        if environ.get(key) != value:
            raise M7Error("environment_rejected", "runtime location is not isolated: " + key)
    assert_fixed_child_environment_controls(environ)
    allowed = set(ENVIRONMENT_ALLOW_LIST) | set(OFFLINE_CONTROLS) | set(isolated_paths(output_directory))
    allowed |= {"PATH", "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE", "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER"}
    allowed |= set(FIXED_CHILD_ENVIRONMENT_CONTROLS)
    assert_fixed_path(environ.get("PATH"))
    if ld_library_path is not None:
        observe_child_ld_library_path(environ, ld_library_path)
        allowed.add(LD_LIBRARY_PATH_NAME)
    elif ld_library_path_pending and LD_LIBRARY_PATH_NAME in environ:
        assert_ld_library_path_value(environ[LD_LIBRARY_PATH_NAME])
        allowed.add(LD_LIBRARY_PATH_NAME)
    stray = sorted(name for name in environ if name not in allowed)
    if stray:
        raise M7Error("environment_rejected", unexpected_environment_detail(stray))
    return True


def create_isolated_directories(output_directory):
    """Create the isolated directories inside the bound output. Called only after consumption."""
    paths = isolated_paths(output_directory)
    for path in sorted(set(paths.values()), key=lambda item: (item.count(os.sep), item)):
        os.makedirs(path, exist_ok=True)
    return sorted(paths.values())


# ------------------------------------------------------------------ GPU binding


def assert_runtime_gpu_binding(entry, observation):
    """Compare a runtime observation with the authorised device binding.

    The observation names the logical device, the visible-device selection, the
    device count, and the identity (UUID and PCI bus) the worker read. All must
    equal the bound entry. The logical device is always ``cuda:0``.
    """
    observation = exact_keys(
        observation,
        ("cuda_visible_devices", "device_count", "logical_device", "pci_bus", "physical_index", "source", "uuid"),
        "identity_mismatch",
    )
    if observation["logical_device"] != LOGICAL_CUDA_DEVICE or entry["logical_device"] != LOGICAL_CUDA_DEVICE:
        raise M7Error("identity_mismatch", "logical device is not cuda:0")
    if observation["device_count"] != 1:
        raise M7Error("identity_mismatch", "the worker must see exactly one CUDA device")
    if observation["cuda_visible_devices"] != entry["cuda_visible_devices"] or str(entry["physical_gpu_index"]) != entry["cuda_visible_devices"]:
        raise M7Error("identity_mismatch", "CUDA_VISIBLE_DEVICES does not match the authorisation")
    if observation["physical_index"] != entry["physical_gpu_index"]:
        raise M7Error("identity_mismatch", "physical GPU index does not match the authorisation")
    if observation["uuid"] != entry["gpu_uuid"]:
        raise M7Error("identity_mismatch", "GPU UUID does not match the authorisation")
    if observation["pci_bus"] != entry["pci_bus"]:
        raise M7Error("identity_mismatch", "GPU PCI bus does not match the authorisation")
    if observation["source"] not in ("nvidia_smi_physical_index", "torch_device_properties"):
        raise M7Error("identity_mismatch", "GPU identity source is not recognised")
    return True


# ------------------------------------------------------------------ failures


def controlled_exception_class_name(exc):
    """A safe exception class token. The message and traceback are never used."""
    name = getattr(type(exc), "__name__", "")
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name) is None or SEQUENCE_RUN_PATTERN.search(name) is not None:
        return "Exception"
    return name


def normalise_exception(exc):
    """Map any exception, including ``BaseException`` subclasses, to a message-safe M7 error."""
    if isinstance(exc, M7Error):
        return exc
    contract = m6_contract()
    if isinstance(exc, contract.M6PilotError):
        return M7Error(exc.code, exc.detail, stage=exc.stage, update=exc.update, microbatch=exc.microbatch)
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return M7Error("interrupted", "run interrupted by " + type(exc).__name__)
    if isinstance(exc, FileNotFoundError):
        return M7Error("filesystem_error", "an expected file is missing")
    if isinstance(exc, OSError):
        return M7Error("filesystem_error", "a filesystem operation failed")
    return M7Error("unexpected_runtime_failure", "unexpected runtime failure; exception_class=" + controlled_exception_class_name(exc))


FAILURE_KEYS = (
    "authorisation_id",
    "authorization_commit",
    "authorization_parent_commit",
    "candidate",
    "code",
    "completion_state",
    "consumption_state",
    "detail",
    "entry_kind",
    "epoch",
    "executing_implementation_commit",
    "m7_complete",
    "manifest_written",
    "microbatch",
    "output_directory",
    "partial_checkpoint",
    "resumable",
    "retained_checkpoint_epochs",
    "reuse_permitted",
    "schema_version",
    "scientific_run_completed",
    "seed",
    "stage",
    "status",
    "update",
)
FAILURE_SCHEMA_VERSION = "m7-failure-record-1"


def new_progress(seed=None, entry_kind="replicate"):
    return {
        "candidate": None,
        "entry_kind": entry_kind,
        "epoch": None,
        "microbatch": None,
        "partial_checkpoint": {"directory_name": None, "epoch": None, "state": "none"},
        "retained_checkpoint_epochs": [],
        "seed": seed,
        "stage": "launch",
        "update": None,
    }


def failure_payload(error, context, progress):
    """The failure record body. It carries codes and counters, never message text from a library."""
    code = error.code if error.code in FAILURE_CODES else "incomplete_evidence_or_manifest"
    detail = error.detail if SEQUENCE_RUN_PATTERN.search(error.detail) is None else "failure detail omitted"
    retained = sorted(int(item) for item in progress.get("retained_checkpoint_epochs", []))
    payload = {
        "authorisation_id": context.get("authorisation_id"),
        "authorization_commit": context.get("authorization_commit"),
        "authorization_parent_commit": context.get("authorization_parent_commit"),
        "candidate": error.candidate if error.candidate is not None else progress.get("candidate"),
        "code": code,
        "completion_state": "consumed_failed",
        "consumption_state": "consumed_failed",
        "detail": detail,
        "entry_kind": progress.get("entry_kind"),
        "epoch": error.epoch if error.epoch is not None else progress.get("epoch"),
        "executing_implementation_commit": context.get("executing_implementation_commit"),
        "m7_complete": False,
        "manifest_written": False,
        "microbatch": error.microbatch if error.microbatch is not None else progress.get("microbatch"),
        "output_directory": context.get("output_directory"),
        "partial_checkpoint": dict(progress.get("partial_checkpoint", {})),
        "resumable": False,
        "retained_checkpoint_epochs": retained,
        "reuse_permitted": False,
        "schema_version": FAILURE_SCHEMA_VERSION,
        "scientific_run_completed": False,
        "seed": error.seed if error.seed is not None else progress.get("seed"),
        "stage": error.stage if error.stage is not None else progress.get("stage"),
        "status": "failed",
        "update": error.update if error.update is not None else progress.get("update"),
    }
    reject_sequence_text(payload)
    return payload


def record_consumed_failure(directory, exc, context, progress, success_manifest_name, writer=None):
    """Write one consumed failure for any ``BaseException`` and return the normalised error.

    A claimed success manifest is removed first, because a failure record and a
    success manifest are mutually exclusive. An existing failure record stays
    authoritative. If the failure record cannot be written, the original error
    is kept and the secondary failure is recorded on it, so the caller can
    still report both. The caller re-raises ``KeyboardInterrupt`` and
    ``SystemExit`` after this returns.
    """
    writer = write_atomic_json if writer is None else writer
    error = normalise_exception(exc)
    manifest_path = os.path.join(directory, success_manifest_name)
    failure_path = os.path.join(directory, FAILURE_RECORD_NAME)
    try:
        if os.path.lexists(manifest_path) and not os.path.isdir(manifest_path):
            os.remove(manifest_path)
        if os.path.islink(failure_path):
            os.remove(failure_path)
        if not os.path.exists(failure_path):
            writer(directory, FAILURE_RECORD_NAME, failure_payload(error, context, progress))
    except BaseException as secondary:
        if isinstance(secondary, (KeyboardInterrupt, SystemExit)) and not isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        error.secondary_failure = {
            "class": controlled_exception_class_name(secondary),
            "code": getattr(secondary, "code", None) or "failure_record_write_failed",
        }
    return error


def format_error_line(error):
    """One message-safe line, including any secondary failure."""
    line = error.code + ": " + error.detail
    if error.secondary_failure:
        line += " | secondary_failure=" + str(error.secondary_failure.get("code")) + ":" + str(error.secondary_failure.get("class"))
    return line


def print_error(error, stream=None):
    stream = sys.stderr if stream is None else stream
    stream.write(format_error_line(error) + "\n")


# ------------------------------------------------------------------ candidate ranking

CANDIDATE_EPOCHS = (1, 2, 3, 4, 5)


def is_candidate_epoch(value):
    """An integer epoch 1 through 5. A bool or a float such as 1.0 is not an epoch."""
    return not isinstance(value, bool) and isinstance(value, int) and value in CANDIDATE_EPOCHS


RANKING_RULE = "fixed_draw_validation_mse_ascending_then_earlier_epoch_on_exact_tie"


def rank_validation_candidates(mse_by_epoch):
    """Order candidate epochs by fixed-draw VALIDATION MSE, then by earlier epoch.

    The input maps each candidate epoch (1 through 5, never update 0) to a
    finite decimal string or number. Only an exact tie falls to the earlier
    epoch. An extra, missing, or non-integer epoch is refused, so update 0 can
    never enter the ranking.
    """
    mapping = require_mapping(mse_by_epoch, "validation_schedule_invalid", "candidate validation values are missing")
    if set(mapping) != set(CANDIDATE_EPOCHS):
        raise M7Error("validation_schedule_invalid", "candidate epochs are not exactly 1 through 5")
    keyed = []
    for epoch, value in mapping.items():
        if isinstance(epoch, bool) or not isinstance(epoch, int):
            raise M7Error("validation_schedule_invalid", "candidate epoch is not an integer")
        number = finite_decimal_string(value, "non_finite_validation") if isinstance(value, str) else finite_float(value, "non_finite_validation")
        keyed.append((number, epoch))
    keyed.sort()
    return [epoch for _number, epoch in keyed]
