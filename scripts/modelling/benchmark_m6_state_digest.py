"""CPU-only benchmark of the M6 checkpoint state-digest primitives.

This script measures synthetic tensors only. It opens no biological data, model
weights, run directory, or GPU. CUDA is hidden, so device-transfer time is not
measured and is reported as such.

For each dtype it separates: equality (``torch.equal``), byte extraction, SHA-256
hashing, and the complete entry digest. The legacy extraction
(``bytes(untyped_storage())`` then a slice) is kept here only as the reference
whose output the streaming extraction must reproduce byte for byte. Each timed
case runs in a fresh subprocess so that the peak resident-set increase over the
allocated tensors is attributable to that case.

Run:  python scripts/modelling/benchmark_m6_state_digest.py > benchmark.json
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import resource
import subprocess
import sys
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACT_PATH = os.path.join(HERE, "m6_pilot_contract.py")
DTYPES = ("float32", "float16", "bfloat16", "int64", "bool")
LEGACY_MIB = 2
STREAMING_MIB = 256
LAYOUTS = ("contiguous", "non_contiguous", "nonzero_offset", "empty", "larger_storage")


def load_contract():
    spec = importlib.util.spec_from_file_location("m6_pilot_contract_bench", CONTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy_cpu_bytes(value):
    cpu = value.detach().to(device="cpu").contiguous()
    raw = bytes(cpu.untyped_storage())
    offset = int(cpu.storage_offset()) * int(cpu.element_size())
    return raw[offset:offset + int(cpu.nbytes)]


def legacy_entry_digest(contract, name, value):
    payload = {"dtype": str(value.dtype), "kind": "tensor", "name": name, "shape": [int(dim) for dim in value.shape]}
    return hashlib.sha256(contract.canonical_json(payload) + legacy_cpu_bytes(value)).hexdigest()


def make_tensor(torch, dtype_name, mebibytes, layout="contiguous"):
    dtype = getattr(torch, dtype_name)
    size = int(torch.empty(0, dtype=dtype).element_size())
    count = max(1, mebibytes * 1024 * 1024 // size)
    generator = torch.Generator().manual_seed(7)
    if dtype_name == "bool":
        base = torch.randint(0, 2, (count,), generator=generator).to(torch.bool)
    elif dtype_name == "int64":
        base = torch.randint(-1000, 1000, (count,), generator=generator, dtype=torch.int64)
    else:
        base = torch.randn(count, generator=generator).to(dtype)
    if layout == "contiguous":
        return base
    if layout == "non_contiguous":
        side = max(1, int(count ** 0.5))
        return base[: side * side].reshape(side, side).t()
    if layout == "nonzero_offset":
        return base[3:]
    if layout == "empty":
        return base[:0]
    if layout == "larger_storage":
        return base[: max(1, count // 4)]
    raise ValueError(layout)


def timed(function):
    start = time.perf_counter()
    result = function()
    return result, time.perf_counter() - start


def run_case(kind, dtype_name, mebibytes):
    import torch

    contract = load_contract()
    tensor = make_tensor(torch, dtype_name, mebibytes)
    other = tensor.clone()
    nbytes = int(tensor.nbytes)
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    record = {"kind": kind, "dtype": dtype_name, "nbytes": nbytes}
    # CUDA is hidden. A device transfer is not measurable and is not estimated.
    record["device_transfer_seconds"] = None
    record["device_transfer_note"] = "not_measured_no_gpu"
    _, record["equality_seconds"] = timed(lambda: bool(torch.equal(tensor, other)))
    if kind == "legacy":
        raw, record["extraction_seconds"] = timed(lambda: legacy_cpu_bytes(tensor))
        _, record["hash_seconds"] = timed(lambda: hashlib.sha256(raw).hexdigest())
        digest, record["entry_digest_seconds"] = timed(lambda: legacy_entry_digest(contract, "w", tensor))
    else:
        def extract():
            total = 0
            for chunk in contract._tensor_cpu_byte_chunks(tensor):
                total += len(chunk)
            return total

        _, record["extraction_seconds"] = timed(extract)

        def hash_only():
            hasher = hashlib.sha256()
            for chunk in contract._tensor_cpu_byte_chunks(tensor):
                hasher.update(chunk)
            return hasher.hexdigest()

        _, record["hash_seconds"] = timed(hash_only)
        digest, record["entry_digest_seconds"] = timed(lambda: contract.state_entry_digest("w", tensor))
    record["digest"] = digest
    record["peak_rss_increase_mib"] = round((resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before) / 1024.0, 2)
    seconds = record["entry_digest_seconds"]
    record["entry_digest_mib_per_second"] = round(nbytes / 1048576.0 / seconds, 2) if seconds > 0 else None
    return record


def equivalence_cases(torch, contract):
    rows = []
    for dtype_name in DTYPES:
        for layout in LAYOUTS:
            tensor = make_tensor(torch, dtype_name, 1, layout)
            rows.append(
                {
                    "dtype": dtype_name,
                    "layout": layout,
                    "legacy_equals_streaming": legacy_entry_digest(contract, "w", tensor) == contract.state_entry_digest("w", tensor),
                    "storage_nbytes": int(tensor.untyped_storage().nbytes()),
                    "view_nbytes": int(tensor.nbytes),
                }
            )
    return rows


def main():
    if len(sys.argv) == 4 and sys.argv[1] in ("legacy", "streaming"):
        print(json.dumps(run_case(sys.argv[1], sys.argv[2], int(sys.argv[3]))))
        return 0
    import torch

    contract = load_contract()
    cases = []
    for kind, mebibytes in (("legacy", LEGACY_MIB), ("streaming", LEGACY_MIB), ("streaming", STREAMING_MIB)):
        for dtype_name in DTYPES:
            completed = subprocess.run(
                [sys.executable, "-B", os.path.abspath(__file__), kind, dtype_name, str(mebibytes)],
                check=True,
                stdout=subprocess.PIPE,
                universal_newlines=True,
            )
            row = json.loads(completed.stdout)
            row["tensor_mib"] = mebibytes
            cases.append(row)
    report = {
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "cases": cases,
        "equivalence": equivalence_cases(torch, contract),
        "torch": torch.__version__,
    }
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
