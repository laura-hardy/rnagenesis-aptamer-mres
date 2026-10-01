"""CPU-only tests for the restored B1 development-pool diagnostic contract.

These tests do not query a GPU, initialise CUDA, load model weights, run
generation.py, materialise the biological 1,000-target schedule, or write
the scientific validation artifacts.
"""

from __future__ import annotations

import collections.abc
import hashlib
import importlib.util
import inspect
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path("/home/laura/rnagenesis-aptamer-mres")
B1_CONFIG = ROOT / "config/experiments/B1_generic_generation.yaml"
PHASE_A = Path(
    "/home/laura/rnagenesis-mres-runs/"
    "m4_b1_generic_generation_B1_generic_released_rnagenesis_de60793a66d1_phaseA"
)
PHASE_B = Path(
    "/home/laura/rnagenesis-mres-runs/"
    "m4_b1_generic_generation_B1_generic_released_rnagenesis_688b18f88f21_phaseB"
)
B2_ATTEMPT2 = Path("/home/laura/rnagenesis-mres-runs/m4_b2_empirical_null_6f82878_attempt2")
B0_CHECKSUM = ROOT / "results/phase4_1_unadapted_rnagenesis_30k/checksums/sha256_raw_generated_files.txt"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_module("b1_development_pool_runner", ROOT / "scripts/b1_development_pool_runner.py")
metrics = load_module("m4_diagnostic_metrics", ROOT / "scripts/modelling/m4_diagnostic_metrics.py")
artifacts = load_module(
    "build_validation_artifacts",
    ROOT / "scripts/modelling/build_validation_artifacts.py",
)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def synthetic_lengths():
    return [20 + (index % 17) for index in range(runner.SOURCE_COUNT)]


def approved_cleaner():
    return runner.load_cleaner_from_verified_source(runner.APPROVED_CLEANER.read_bytes())


CLEANER = approved_cleaner()


class Environment(collections.abc.Mapping):
    def __init__(self, data):
        self._data = dict(data)

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


def probe_for(physical_gpu):
    return {
        "physical_index": physical_gpu,
        "uuid": "GPU-test-{}".format(physical_gpu),
        "pci_bus": "0000:aa:00.0",
        "logical_device": "cuda:0",
        "device_type": "cuda",
        "cuda_device_count": 1,
        "cpu_fallback": False,
        "other_gpu_fallback": False,
    }


def parent_for(physical_gpu):
    return Environment(
        {
            "CUDA_VISIBLE_DEVICES": str(physical_gpu),
            "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
            "HF_HOME": "/home/laura/RNAGenesis/.cache/huggingface",
        }
    )


def authorised_config(output_directory, physical_gpu, schedule_hash):
    authorisation = {
        "authorisation_id": "test-development-pool",
        "authorisation_active": True,
        "activation_status": "active_unconsumed",
        "consumed": False,
        "authorises_b1_development_pool": True,
        "gpu_use_authorised": True,
        "physical_gpu": physical_gpu,
        "gpu_uuid": "GPU-test-{}".format(physical_gpu),
        "pci_bus": "0000:aa:00.0",
        "authorization_commit": "a" * 40,
        "executing_implementation_commit": "b" * 40,
        "mres_branch": "main",
        "condition": runner.CONDITION_LABEL,
        "phase": "development_pool",
        "output_directory": output_directory,
        "evidence_directory": output_directory,
        "schedule_sha256": schedule_hash,
        "success_claimed": False,
        "m4_complete": False,
        "b1_eligible": False,
        "exact_length_accepted_pool_declared": False,
        "final_production_mapping_declared": False,
        "final_m8_production_protocol_declared": False,
    }
    return {
        "document_status": runner.EXECUTABLE_DOCUMENT_STATUS,
        "consumable_by_executable_workflow": True,
        "condition_manifest_label": runner.CONDITION_LABEL,
        "execution": {"authorised": True, "gpu_authorised_by_this_approval": True},
        "development_pool_execution": {
            "executable_now": True,
            "status": runner.POOL_EXECUTION_STATUS,
        },
        "development_pool_scientific_execution_authorisation": authorisation,
    }


def exact_line(length):
    return "11" + ("ACGU" * 40)[:length] + "2"


def payload_for(invocation, mutator=None):
    lines = []
    for position, original in enumerate(invocation["original_attempt_indexes"]):
        if mutator is None:
            lines.append(exact_line(invocation["target_length"]))
        else:
            lines.append(mutator(invocation, position, original))
    return ("\n".join(lines) + "\n").encode("utf-8")


class ScheduleTests(unittest.TestCase):
    def test_schedule_is_deterministic_and_accounts_for_every_attempt(self):
        lengths = synthetic_lengths()
        first = runner.build_schedule(lengths)
        second = runner.build_schedule(lengths)
        import numpy

        self.assertEqual(first, second)
        self.assertEqual(len(first["sampled_target_lengths"]), 1000)
        self.assertEqual(first["sampled_target_lengths"][0], first["sampled_target_lengths"][0])
        self.assertEqual(first["numpy_version"], numpy.__version__)
        self.assertEqual(first["sampling_seed"], 43000)
        self.assertEqual(first["sampling_operation"]["operation_count"], 1)
        self.assertIs(first["sampling_operation"]["replace"], True)
        self.assertEqual(first["source_ordered_length_vector"]["count"], 669)
        self.assertEqual(first["source_ordered_length_vector"]["order_rule"], runner.ORDER_RULE)
        self.assertIs(first["independent_biological_replicates"], False)
        self.assertIs(first["padding"], False)
        self.assertIs(first["rejection"], False)
        self.assertIs(first["resampling"], False)
        self.assertIs(first["dropping"], False)
        seen = []
        for index, invocation in enumerate(first["invocations"]):
            self.assertEqual(invocation["invocation_index"], index)
            self.assertEqual(invocation["invocation_seed"], 44000 + index)
            self.assertEqual(invocation["batch_num"], 1)
            self.assertLessEqual(invocation["actual_chunk_size"], 16)
            self.assertGreaterEqual(invocation["actual_chunk_size"], 1)
            self.assertEqual(invocation["max_seq_len"], invocation["target_length"] + 1)
            self.assertEqual(
                invocation["original_attempt_indexes"],
                sorted(invocation["original_attempt_indexes"]),
            )
            self.assertEqual(
                invocation["expected_batch_positions"],
                list(range(invocation["actual_chunk_size"])),
            )
            seen.extend(invocation["original_attempt_indexes"])
        self.assertEqual(sorted(seen), list(range(1000)))
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(sum(item["actual_chunk_size"] for item in first["invocations"]), 1000)

    def test_sampling_uses_one_unreordered_choice(self):
        import numpy

        population = [30, 20, 30, 40]
        calls = []

        def factory(seed):
            class Generator(object):
                def choice(self, values, size, replace):
                    calls.append((list(values), size, replace, seed))
                    return numpy.random.default_rng(seed).choice(values, size=size, replace=replace)

            return Generator()

        sampled = runner.sample_target_lengths(population, rng_factory=factory)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], population)
        self.assertNotEqual(calls[0][0], sorted(population))
        self.assertEqual(calls[0][1], 1000)
        self.assertIs(calls[0][2], True)
        self.assertEqual(calls[0][3], 43000)
        self.assertEqual(len(sampled), 1000)
        again = runner.sample_target_lengths(population)
        self.assertEqual(sampled, again)

    def test_chunking_uses_actual_sizes_without_padding(self):
        self.assertEqual(
            [len(chunk) for chunk in runner.chunk_indexes(list(range(17)))],
            [16, 1],
        )
        self.assertEqual(
            [len(chunk) for chunk in runner.chunk_indexes(list(range(16)))],
            [16],
        )
        self.assertEqual(runner.chunk_indexes([4]), [[4]])

    def test_canonical_schedule_excludes_its_own_hash(self):
        schedule = runner.build_schedule(synthetic_lengths())
        raw = runner.canonical_schedule_bytes(schedule)
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", raw)
        self.assertEqual(raw.count(b"\n"), 1)
        self.assertTrue(raw.endswith(b"\n"))
        parsed = json.loads(raw.decode("utf-8"))
        self.assertNotIn("schedule_sha256", parsed)
        self.assertEqual(runner.schedule_sha256(schedule), hashlib.sha256(raw).hexdigest())
        self.assertEqual(raw, runner.canonical_schedule_bytes(parsed))


class MappingAndMetricTests(unittest.TestCase):
    def invocation(self):
        return {
            "invocation_index": 0,
            "invocation_seed": 44000,
            "target_length": 8,
            "actual_chunk_size": 4,
            "max_seq_len": 9,
            "batch_num": 1,
            "original_attempt_indexes": [3, 4, 9, 10],
            "expected_batch_positions": [0, 1, 2, 3],
        }

    def test_length_mismatch_early_eos_and_invalid_output_stay_mapped(self):
        invocation = self.invocation()
        lines = [
            exact_line(8),
            "11AC2",
            "11ACGU",
            "11ACGT2",
        ]
        records = runner.map_invocation_output(("\n".join(lines) + "\n").encode("utf-8"), invocation, CLEANER)
        self.assertEqual([row["original_attempt_index"] for row in records], [3, 4, 9, 10])
        self.assertTrue(records[0]["exact_length_hit"])
        self.assertTrue(records[0]["eos_marker_observed"])
        self.assertFalse(records[0]["early_eos"])
        self.assertTrue(records[1]["early_eos"])
        self.assertFalse(records[1]["exact_length_hit"])
        self.assertTrue(records[1]["validity"])
        self.assertFalse(records[2]["exact_length_hit"])
        self.assertFalse(records[2]["early_eos"])
        self.assertTrue(records[2]["validity"])
        self.assertFalse(records[3]["validity"])
        self.assertEqual(records[3]["invalid_reason"], "invalid_symbols")
        self.assertFalse(records[3]["early_eos"])
        summary = metrics.summarise_attempts(records)
        self.assertEqual(summary["raw_attempts"], 4)
        self.assertEqual(summary["parsed_outputs"], 4)
        self.assertEqual(summary["invalid_outputs"], 1)
        self.assertEqual(summary["valid_outputs"], 3)
        self.assertEqual(summary["early_eos_observations"], 1)
        self.assertGreaterEqual(summary["eos_marker_observations"], 1)
        self.assertEqual(summary["exact_hit_rate_denominator"], "raw_attempts")
        self.assertEqual(summary["exact_hit_rate"], 0.25)
        self.assertEqual(summary["exact_length_hits"], 1)
        diagnostic = summary["exact_hit_rate_valid_outputs_diagnostic"]
        self.assertEqual(diagnostic["label"], metrics.VALID_ONLY_EXACT_HIT_LABEL)
        self.assertEqual(diagnostic["denominator"], "valid_outputs")
        self.assertIs(diagnostic["replaces_approved_raw_attempt_metric"], False)
        self.assertNotEqual(diagnostic["rate"], summary["exact_hit_rate"])
        self.assertIs(summary["exact_hit_rate_is_execution_success_requirement"], False)
        self.assertIn("clustering_identity_threshold", summary["deferred_beyond_m4"])
        self.assertIn("frozen_representation_metrics", summary["deferred_beyond_m4"])
        self.assertNotIn("cluster", " ".join(summary["implemented_metric_ids"]))
        self.assertNotIn("representation", " ".join(summary["implemented_metric_ids"]))

    def test_line_count_and_duplicate_identity_are_technical_failures(self):
        invocation = self.invocation()
        with self.assertRaises(runner.DevelopmentPoolError) as caught:
            runner.map_invocation_output(b"11ACGUACGU2\n", invocation, CLEANER)
        self.assertEqual(caught.exception.code, "output_line_count_mismatch")
        with self.assertRaises(runner.DevelopmentPoolError) as extra:
            runner.map_invocation_output(((exact_line(8) + "\n") * 5).encode("utf-8"), invocation, CLEANER)
        self.assertEqual(extra.exception.code, "output_line_count_mismatch")
        schedule = {
            "invocation_count": 1,
            "total_attempts": 4,
            "invocations": [invocation],
        }
        duplicated = runner.map_invocation_output(
            ((exact_line(8) + "\n") * 4).encode("utf-8"),
            invocation,
            CLEANER,
        )
        duplicated[1]["original_attempt_index"] = duplicated[0]["original_attempt_index"]
        reasons = runner.technical_failure_reasons(
            duplicated,
            schedule,
            raw_verified=True,
            provenance_matched=True,
            manifests_exclusive=True,
        )
        self.assertIn("attempt_accounting_invalid", reasons)
        self.assertTrue(
            runner.diagnostic_run_succeeded(
                attempts=runner.map_invocation_output(
                    ((exact_line(8) + "\n") * 4).encode("utf-8"),
                    invocation,
                    CLEANER,
                ),
                schedule=schedule,
                raw_verified=True,
                provenance_matched=True,
                manifests_exclusive=True,
            )
        )

    def test_cleaner_is_loaded_from_hash_verified_source(self):
        source = (ROOT / "scripts/b1_development_pool_runner.py").read_text(encoding="utf-8")
        self.assertNotIn("def audit_generated_line", source)
        self.assertNotIn("def split_raw_records", source)
        self.assertNotIn("BOUNDARY_MARKERS", source)
        imported = load_module(
            "approved_audit_generation_output",
            runner.APPROVED_CLEANER,
        )
        for raw in ("11ACGU2", "11ACGT2", "1122", "ACGU", "11AC2"):
            approved = imported.audit_line(1, raw)
            loaded = CLEANER.audit_line(1, raw)
            self.assertEqual(loaded, approved)
        mutated = bytearray(runner.APPROVED_CLEANER.read_bytes())
        mutated[-1] = (mutated[-1] + 1) % 256
        with self.assertRaises(runner.DevelopmentPoolError) as caught:
            runner.load_cleaner_from_verified_source(bytes(mutated))
        self.assertEqual(caught.exception.code, "provenance_mismatch")

    def test_invalid_attempts_are_non_hits_and_guardrails_reject_inconsistent_flags(self):
        invocation = self.invocation()
        records = runner.map_invocation_output(
            ("\n".join([exact_line(8), "11AC2", "11ACGU", "11ACGT2"]) + "\n").encode("utf-8"),
            invocation,
            CLEANER,
        )
        summary = metrics.summarise_attempts(records)
        self.assertEqual(summary["exact_length_hits"], 1)
        self.assertEqual(summary["exact_hit_rate"], 1 / 4)
        self.assertEqual(summary["invalid_outputs"], 1)
        drifted = dict(records[3])
        drifted["validity"] = True
        with self.assertRaises(metrics.DiagnosticMetricError) as caught:
            metrics.summarise_attempts(records[:3] + [drifted])
        self.assertEqual(caught.exception.code, "ledger_inconsistent")
        evaluation = metrics.evaluate_hard_guardrails(records, {"ACGU"})
        self.assertIs(evaluation["exact_hit_rate_is_an_eligibility_threshold"], False)
        self.assertEqual(evaluation["approved_exact_hit_rate_denominator"], "raw_attempts")
        self.assertIs(evaluation["checkpoint_eligible"], False)
        ids = [item["id"] for item in evaluation["decisions"]]
        self.assertEqual(
            ids,
            [
                "valid_nonempty_acgu_fraction",
                "empty_or_unparseable_fraction",
                "unique_fraction",
                "exact_train_match_rate",
                "largest_duplicate_share",
            ],
        )
        share = next(item for item in evaluation["decisions"] if item["id"] == "largest_duplicate_share")
        self.assertFalse(share["passed"])
        self.assertFalse(evaluation["checkpoint_eligible"])

    def test_largest_duplicate_share_guardrail_matches_the_approved_configuration(self):
        document = yaml.safe_load((ROOT / "config/modelling/validation_metrics_v1.yaml").read_text(encoding="utf-8"))
        rule = next(
            item
            for item in document["hard_guardrails"]["thresholds"]
            if item["id"] == "largest_duplicate_share"
        )
        self.assertEqual(rule["maximum"], 0.01)
        self.assertEqual(rule["numerator"], "count_of_the_most_frequent_valid_output")
        self.assertEqual(rule["denominator"], "valid_outputs")
        self.assertEqual(rule["maximum"], metrics.LARGEST_DUPLICATE_SHARE_MAXIMUM)
        self.assertEqual(rule["numerator"], metrics.LARGEST_DUPLICATE_SHARE_NUMERATOR)
        self.assertEqual(rule["denominator"], metrics.LARGEST_DUPLICATE_SHARE_DENOMINATOR)
        self.assertEqual(
            metrics.GUARDRAIL_THRESHOLDS["largest_duplicate_share"],
            {"comparison": "maximum", "threshold": rule["maximum"]},
        )
        self.assertIn("largest_duplicate_share", metrics.HARD_GUARDRAIL_IDS)

        def sequence(index):
            alphabet = "ACGU"
            chars = []
            value = index
            for _ in range(8):
                chars.append(alphabet[value % 4])
                value //= 4
            return "".join(chars)

        def attempt(index, cleaned, valid=True):
            requested = 8
            raw = "11" + cleaned + "2"
            return {
                "original_attempt_index": index,
                "invocation_index": 0,
                "batch_position": index,
                "requested_target_length": requested,
                "max_seq_len": requested + 1,
                "invocation_seed": 44000,
                "raw_decoded_text": raw,
                "raw_length": len(raw),
                "leading_boundary_marker_run": "11",
                "trailing_boundary_marker_run": "2",
                "cleaned_sequence": cleaned,
                "cleaned_length": len(cleaned),
                "validity": valid,
                "invalid_reason": None if valid else "invalid_symbols",
                "eos_marker_observed": True,
                "early_eos": False,
                "exact_length_hit": bool(valid and len(cleaned) == requested),
                "length_delta": len(cleaned) - requested,
            }

        passing_rows = [attempt(index, sequence(index)) for index in range(100)]
        passing = metrics.evaluate_hard_guardrails(passing_rows, set())
        passing_share = next(item for item in passing["decisions"] if item["id"] == "largest_duplicate_share")
        self.assertEqual(passing_share["value"], 0.01)
        self.assertEqual(passing_share["threshold"], 0.01)
        self.assertTrue(passing_share["passed"])
        self.assertEqual(passing_share["status"], "evaluated")
        self.assertTrue(all(item["passed"] is True for item in passing["decisions"]))
        self.assertTrue(passing["checkpoint_eligible"])

        failing_rows = [attempt(index, sequence(0 if index == 99 else index)) for index in range(100)]
        failing = metrics.evaluate_hard_guardrails(failing_rows, set())
        failing_share = next(item for item in failing["decisions"] if item["id"] == "largest_duplicate_share")
        self.assertEqual(failing_share["value"], 0.02)
        self.assertFalse(failing_share["passed"])
        self.assertTrue(
            all(item["passed"] is True for item in failing["decisions"] if item["id"] != "largest_duplicate_share")
        )
        self.assertFalse(failing["checkpoint_eligible"])

        invalid = attempt(0, "", valid=False)
        invalid["cleaned_sequence"] = ""
        invalid["cleaned_length"] = 0
        invalid["raw_decoded_text"] = "11X2"
        invalid["raw_length"] = 4
        invalid["exact_length_hit"] = False
        invalid["early_eos"] = False
        invalid["length_delta"] = -8
        invalid["eos_marker_observed"] = True
        zero = metrics.evaluate_hard_guardrails([dict(invalid, original_attempt_index=index, batch_position=index) for index in range(4)], set())
        zero_share = next(item for item in zero["decisions"] if item["id"] == "largest_duplicate_share")
        self.assertIsNone(zero_share["value"])
        self.assertFalse(zero_share["passed"])
        self.assertEqual(zero_share["status"], "undefined_empty_valid_denominator")
        self.assertIsNone(zero["largest_duplicate_share"])
        self.assertEqual(zero["largest_duplicate_share_denominator"], "valid_outputs")
        self.assertFalse(zero["checkpoint_eligible"])


def subprocess_result(code):
    class Completed(object):
        def __init__(self, returncode):
            self.returncode = returncode

    return Completed(code)


def build_deps(config, length_path, lengths, physical_gpu, line_fn=None, crash=None):
    config_bytes = yaml.safe_dump(config, sort_keys=False).encode("utf-8")
    events = []
    written = []

    source_reads = {"metrics": 0, "metrics_config": 0}

    def read_bytes(path):
        events.append(("read", str(path)))
        text = str(path)
        if text == str(runner.B1_CONFIG_PATH):
            return config_bytes
        if text == length_path:
            return (json.dumps(lengths) + "\n").encode("utf-8")
        if text == str(runner.METRICS_PATH):
            source_reads["metrics"] += 1
            payload = Path(path).read_bytes()
            if crash == "metrics-drift" and source_reads["metrics"] > 1:
                return b"this is not python\n"
            return payload
        if text == str(runner.METRICS_CONFIG_PATH):
            source_reads["metrics_config"] += 1
            payload = Path(path).read_bytes()
            if crash == "metrics-config-drift" and source_reads["metrics_config"] > 1:
                return payload + b"\n# drifted\n"
            return payload
        return Path(path).read_bytes()

    def sha256_file(path):
        if str(path).endswith("diffusion_pytorch_model.safetensors"):
            return runner.RECORDED_B1_WEIGHT_SHA256
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def git(repo, args):
        if str(repo) == str(runner.MRES_ROOT):
            if args == ["rev-parse", "HEAD"]:
                return "a" * 40 + "\n"
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return "main\n"
            if args == ["status", "--porcelain=v1"]:
                return ""
            if args[0] == "merge-base":
                return "b" * 40 + "\n"
            if args[0] in ("rev-parse", "hash-object"):
                return "c" * 40 + "\n"
        if str(repo) == str(runner.RNAGENESIS_ROOT):
            if args == ["rev-parse", "HEAD"]:
                return runner.RNAGENESIS_HEAD + "\n"
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return runner.RNAGENESIS_BRANCH + "\n"
            if args == ["status", "--porcelain=v1"]:
                return runner.reviewed_rnagenesis_porcelain()
        raise AssertionError((repo, args))

    def gpu(parent, physical):
        events.append(("gpu", physical))
        return probe_for(physical)

    def subprocess_run(argv, cwd, env, shell=False):
        events.append(("subprocess", cwd, shell))
        if crash == "keyboard":
            raise KeyboardInterrupt()
        if crash == "system":
            raise SystemExit(7)
        if crash == "runtime":
            raise RuntimeError("boom")
        if shell is not False or cwd != runner.GENERATION_CWD:
            raise AssertionError((shell, cwd))
        if argv[0] != runner.PINNED_PYTHON or argv[1] != str(runner.GENERATION_ENTRY):
            raise AssertionError(argv[:2])
        if argv[argv.index("--device") + 1] != "cuda:0":
            raise AssertionError(argv)
        if env["CUDA_VISIBLE_DEVICES"] != str(physical_gpu) or env["CUDA_DEVICE_ORDER"] != "PCI_BUS_ID":
            raise AssertionError(env["CUDA_VISIBLE_DEVICES"])
        evidence = os.path.dirname(env["PYTHONPYCACHEPREFIX"])
        for key in (
            "PYTHONPYCACHEPREFIX",
            "HF_HOME",
            "TRANSFORMERS_CACHE",
            "HF_HUB_CACHE",
            "HUGGINGFACE_HUB_CACHE",
            "TORCH_HOME",
        ):
            if not env[key].startswith(evidence + os.sep):
                raise AssertionError(env[key])
            if env[key].startswith(str(runner.RNAGENESIS_ROOT)):
                raise AssertionError(env[key])
        remark = argv[argv.index("--remark") + 1]
        invocation_index = int(remark.split("_i")[1].split("_")[0])
        batch = int(argv[argv.index("--batch_size") + 1])
        target = int(argv[argv.index("--max_seq_len") + 1]) - 1
        path = Path(argv[argv.index("--superfolder") + 1]) / argv[argv.index("--mid_folder") + 1]
        path = path / "seqs_wo_guidance_top_p=0.95_2_{}{}.txt".format(batch, remark)
        lines = []
        for position in range(batch):
            if line_fn is None:
                lines.append(exact_line(target))
            else:
                lines.append(line_fn(invocation_index, position, target))
        path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        if crash == "mutate-schedule" and invocation_index == 0:
            schedule_path = Path(evidence) / runner.SCHEDULE_NAME
            with schedule_path.open("ab") as handle:
                handle.write(b" ")
        if crash == "symlink" and invocation_index == 1:
            first = next((Path(evidence) / "rnagenesis_generation_output" / "invocation_0000").glob("*.txt"))
            held = first.with_name(first.name + ".held")
            first.rename(held)
            first.symlink_to(held)
        if crash == "delete" and invocation_index == 1:
            first = next((Path(evidence) / "rnagenesis_generation_output" / "invocation_0000").glob("*.txt"))
            first.unlink()
        if crash == "truncate" and invocation_index == 1:
            first = next((Path(evidence) / "rnagenesis_generation_output" / "invocation_0000").glob("*.txt"))
            first.write_bytes(first.read_bytes()[:4])
        if crash == "mutate" and invocation_index == 1:
            first = next((Path(evidence) / "rnagenesis_generation_output" / "invocation_0000").glob("*.txt"))
            payload = bytearray(first.read_bytes())
            payload[0] ^= 1
            first.write_bytes(payload)
        if crash == "nonzero":
            return subprocess_result(3)
        return subprocess_result(0)

    def write_exclusive(path, data):
        written.append(os.path.basename(str(path)))
        if crash == "failure-write" and os.path.basename(str(path)) == runner.FAILURE_MANIFEST_NAME:
            raise OSError("failure manifest disk")
        return runner._exclusive_write(path, data)

    deps = runner.RunnerDependencies(
        read_bytes=read_bytes,
        sha256_file=sha256_file,
        git=git,
        gpu_preflight=gpu,
        environ=parent_for(physical_gpu),
        subprocess_run=subprocess_run,
        write_exclusive=write_exclusive,
    )
    deps.events = events
    deps.written = written
    return deps


class ExecutionGateTests(unittest.TestCase):
    def test_checked_in_configuration_refuses_before_side_effects(self):
        config = yaml.safe_load(B1_CONFIG.read_text(encoding="utf-8"))
        with self.assertRaises(runner.DevelopmentPoolError) as caught:
            runner.assert_configuration_consumable(config)
        self.assertEqual(caught.exception.code, "configuration_not_consumable")
        template = config["development_pool_scientific_execution_authorisation"]
        self.assertIs(template["authorisation_active"], False)
        self.assertIs(template["consumed"], False)
        self.assertIsNone(template["physical_gpu"])
        self.assertIs(template["authorises_b1_development_pool"], False)
        course = config["m4_course_change_1_october_2026"]
        approach = course["approach_a_fixed_full_retry_table_r32"]
        self.assertIs(approach["superseded_before_implementation"], True)
        self.assertIs(approach["implemented"], False)
        self.assertIs(approach["executed"], False)
        self.assertIs(approach["schedule_exists"], False)
        self.assertEqual(course["active_m4_design"], "restored_stage_1_diagnostic_contract")
        self.assertIs(course["exact_length_accepted_pool_declared"], False)
        self.assertIs(config["limited_development_pool"]["development_pool_authorised"], False)
        self.assertIsNone(config["shared_generation_settings"]["physical_gpu"])
        self.assertIs(config["shared_generation_settings"]["physical_gpu_selected_by_this_document"], False)
        self.assertEqual(config["shared_generation_settings"]["child_logical_device"], "cuda:0")
        self.assertEqual(config["historical_consumed_phase_a_and_phase_b_device"]["physical_gpu"], 1)
        self.assertIs(config["length_algorithm"]["rejection"], False)
        self.assertIs(config["length_algorithm"]["replacement"], False)
        self.assertIs(config["length_algorithm"]["resampling"], False)
        self.assertEqual(
            config["length_algorithm"]["active_m4_design"],
            "restored_stage_1_diagnostic_contract",
        )
        opened = []
        output = tempfile.mkdtemp(prefix="b1-pool-closed-")
        os.rmdir(output)
        length_path = output + ".json"

        def factory():
            deps = runner.RunnerDependencies()
            real_read = deps.read_bytes

            def read_bytes(path):
                opened.append(str(path))
                return real_read(path)

            deps.read_bytes = read_bytes

            def query(*args):
                opened.append("gpu")
                raise AssertionError(args)

            deps.gpu_preflight = query
            return deps

        original = runner.production_dependencies
        runner.production_dependencies = factory
        try:
            code = runner.main(["--output-directory", output, "--physical-gpu", "4", "--length-vector", length_path])
        finally:
            runner.production_dependencies = original
        self.assertEqual(code, 2)
        self.assertNotIn(length_path, opened)
        self.assertNotIn("gpu", opened)
        self.assertEqual(list(inspect.signature(runner.main).parameters), ["argv"])
        self.assertNotIn("generate", inspect.signature(runner.main).parameters)
        self.assertFalse(os.path.exists(output))

    def test_runtime_gpu_is_not_hardcoded_and_must_match_the_authorisation(self):
        source = (ROOT / "scripts/b1_development_pool_runner.py").read_text(encoding="utf-8")
        self.assertNotIn("PHYSICAL_GPU = 0", source)
        self.assertNotIn("PHYSICAL_GPU = 1", source)
        self.assertNotIn('default="0"', source)
        self.assertNotIn('default="1"', source)
        self.assertEqual(runner.parse_physical_gpu_argument("0"), 0)
        self.assertEqual(runner.parse_physical_gpu_argument("1"), 1)
        self.assertEqual(runner.parse_physical_gpu_argument("4"), 4)
        with self.assertRaises(runner.DevelopmentPoolError):
            runner.parse_physical_gpu_argument("01")
        self.assertEqual(runner.physical_gpu_query_argv(4)[-1], "4")
        with tempfile.TemporaryDirectory() as tmp:
            evidence = os.path.join(tmp, "evidence")
            parent = parent_for(4)
            before = list(parent.items())
            child = runner.build_child_environment(parent, 4, evidence)
            self.assertEqual(list(parent.items()), before)
            self.assertEqual(child["CUDA_VISIBLE_DEVICES"], "4")
            self.assertEqual(child["CUDA_DEVICE_ORDER"], "PCI_BUS_ID")
            self.assertTrue(child["PYTHONPYCACHEPREFIX"].startswith(evidence + "/"))
            self.assertTrue(child["HF_HOME"].startswith(evidence + "/"))
            self.assertTrue(child["TRANSFORMERS_CACHE"].startswith(evidence + "/"))
            self.assertTrue(child["TORCH_HOME"].startswith(evidence + "/"))
            self.assertFalse(child["HF_HOME"].startswith("/home/laura/RNAGenesis"))
            self.assertNotEqual(child["HF_HOME"], parent["HF_HOME"])
        saved_visible = os.environ.get("CUDA_VISIBLE_DEVICES")
        saved_order = os.environ.get("CUDA_DEVICE_ORDER")
        os.environ["CUDA_VISIBLE_DEVICES"] = "4"
        os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        try:
            runner.assert_parent_cuda(os.environ, 4)
        finally:
            if saved_visible is None:
                os.environ.pop("CUDA_VISIBLE_DEVICES", None)
            else:
                os.environ["CUDA_VISIBLE_DEVICES"] = saved_visible
            if saved_order is None:
                os.environ.pop("CUDA_DEVICE_ORDER", None)
            else:
                os.environ["CUDA_DEVICE_ORDER"] = saved_order
        with self.assertRaises(runner.DevelopmentPoolError) as non_string:
            runner.assert_parent_cuda(
                Environment({"CUDA_VISIBLE_DEVICES": 4, "CUDA_DEVICE_ORDER": "PCI_BUS_ID"}),
                4,
            )
        self.assertEqual(non_string.exception.code, "cuda_environment_invalid")
        with self.assertRaises(runner.DevelopmentPoolError) as mismatch:
            runner.build_child_environment(parent_for(0), 4, evidence)
        self.assertEqual(mismatch.exception.code, "cuda_environment_invalid")
        invocation = runner.build_schedule(synthetic_lengths())["invocations"][0]
        argv = runner.build_generation_argv(invocation)
        self.assertEqual(argv[argv.index("--device") + 1], "cuda:0")
        self.assertEqual(argv[argv.index("--batch_size") + 1], str(invocation["actual_chunk_size"]))
        self.assertEqual(argv[argv.index("--batch_num") + 1], "1")
        self.assertNotIn("--cpu", argv)
        with self.assertRaises(runner.DevelopmentPoolError) as fallback:
            runner.assert_gpu_probe(
                dict(probe_for(4), device_type="cpu", logical_device="cpu"),
                4,
                {"gpu_uuid": "GPU-test-4", "pci_bus": "0000:aa:00.0"},
            )
        self.assertEqual(fallback.exception.code, "gpu_fallback_prohibited")

    def test_existing_path_and_hash_mismatch_refuse_before_writing(self):
        lengths = synthetic_lengths()
        schedule_hash = runner.schedule_sha256(runner.build_schedule(lengths))
        with tempfile.TemporaryDirectory() as tmp:
            existing = os.path.join(tmp, "evidence")
            os.mkdir(existing)
            deps = build_deps(authorised_config(existing, 4, schedule_hash), existing + ".json", lengths, 4)
            with self.assertRaises(runner.DevelopmentPoolError) as caught:
                runner.run(existing, "4", existing + ".json", deps)
            self.assertEqual(caught.exception.code, "output_directory_exists")
            self.assertFalse(any(event[0] == "gpu" for event in deps.events))
            self.assertFalse(any(event[0] == "read" and event[1].endswith(".json") for event in deps.events))
            self.assertFalse(os.path.exists(os.path.join(existing, runner.SUCCESS_MANIFEST_NAME)))
            self.assertFalse(os.path.exists(os.path.join(existing, runner.FAILURE_MANIFEST_NAME)))
            fresh = os.path.join(tmp, "fresh")
            bad = build_deps(authorised_config(fresh, 4, "c" * 64), fresh + ".json", lengths, 4)
            with self.assertRaises(runner.DevelopmentPoolError) as hashed:
                runner.run(fresh, "4", fresh + ".json", bad)
            self.assertEqual(hashed.exception.code, "schedule_hash_mismatch")
            self.assertTrue(any(event[0] == "gpu" for event in bad.events))
            self.assertTrue(any(event[1] == fresh + ".json" for event in bad.events if event[0] == "read"))
            gpu_at = next(index for index, event in enumerate(bad.events) if event[0] == "gpu")
            length_at = next(index for index, event in enumerate(bad.events) if event[0] == "read" and event[1] == fresh + ".json")
            self.assertLess(gpu_at, length_at)
            self.assertFalse(os.path.exists(fresh))

    def _run_entry(self, output, lengths, digest, line_fn=None, crash=None):
        deps = build_deps(authorised_config(output, 4, digest), output + ".json", lengths, 4, line_fn, crash)
        original = runner.production_dependencies
        runner.production_dependencies = lambda: deps
        try:
            code = runner.main(["--output-directory", output, "--physical-gpu", "4", "--length-vector", output + ".json"])
        finally:
            runner.production_dependencies = original
        return code, deps

    def test_production_entry_point_executes_the_command_and_keeps_ledgers_distinct(self):
        lengths = synthetic_lengths()
        digest = runner.schedule_sha256(runner.build_schedule(lengths))

        def mixed(invocation_index, position, target):
            if invocation_index == 0 and position == 0:
                return "11AC2"
            if invocation_index == 0 and position == 1:
                return "11ACGT2"
            if invocation_index == 0 and position in (2, 3):
                return "11ACGUACGU2"
            return exact_line(target)

        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "evidence")
            code, deps = self._run_entry(output, lengths, digest, mixed)
            self.assertEqual(code, 0)
            self.assertGreater(len([event for event in deps.events if event[0] == "subprocess"]), 0)
            self.assertEqual(deps.written[-1], runner.SUCCESS_MANIFEST_NAME)
            self.assertLess(deps.written.index(runner.HASH_REPORT_NAME), deps.written.index(runner.SUCCESS_MANIFEST_NAME))
            self.assertLess(deps.written.index(runner.RAW_LEDGER_NAME), deps.written.index(runner.HASH_REPORT_NAME))
            self.assertLess(deps.written.index(runner.AUDITED_LEDGER_NAME), deps.written.index(runner.HASH_REPORT_NAME))
            manifest = json.loads((Path(output) / runner.SUCCESS_MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertEqual(manifest["metrics"]["raw_attempts"], 1000)
            self.assertEqual(manifest["metrics"]["exact_hit_rate_denominator"], "raw_attempts")
            self.assertGreater(manifest["metrics"]["invalid_outputs"], 0)
            self.assertGreater(manifest["metrics"]["early_eos_observations"], 0)
            self.assertLess(manifest["metrics"]["exact_length_hits"], 1000)
            self.assertGreater(manifest["metrics"]["duplicates"], 0)
            self.assertEqual(manifest["provenance"]["numpy_version"], runner._bound_numpy_version())
            self.assertEqual(manifest["provenance"]["mres"]["authorization_commit"], "a" * 40)
            self.assertEqual(manifest["provenance"]["rnagenesis"]["commit"], runner.RNAGENESIS_HEAD)
            self.assertEqual(manifest["provenance"]["approved_cleaner"]["sha256"], runner.CLEANER_SHA256)
            self.assertEqual(manifest["logical_device"], "cuda:0")
            raw_lines = (Path(output) / runner.RAW_LEDGER_NAME).read_text(encoding="utf-8").splitlines()
            audited_lines = (Path(output) / runner.AUDITED_LEDGER_NAME).read_text(encoding="utf-8").splitlines()
            self.assertNotEqual(raw_lines, audited_lines)
            self.assertEqual(len(audited_lines), 1000)
            self.assertEqual(len(raw_lines), 1000)
            sample = json.loads(raw_lines[0])
            self.assertEqual(set(sample), set(runner.RAW_ATTEMPT_FIELDS))
            for forbidden in (
                "raw_length",
                "cleaned_sequence",
                "cleaned_length",
                "validity",
                "invalid_reason",
                "eos_marker_observed",
                "early_eos",
                "exact_length_hit",
                "length_delta",
                "leading_boundary_marker_run",
                "trailing_boundary_marker_run",
                "raw_file_path",
                "byte_count",
                "line_count",
                "sha256",
            ):
                self.assertNotIn(forbidden, sample)
            self.assertIn("raw_decoded_text", sample)
            self.assertIsInstance(sample["invocation_seed"], int)
            self.assertIsInstance(sample["max_seq_len"], int)
            audited_sample = json.loads(audited_lines[0])
            self.assertIn("cleaned_sequence", audited_sample)
            self.assertIn("validity", audited_sample)
            invocation_manifest = json.loads(
                (Path(output) / runner.INVOCATION_OUTPUT_MANIFEST_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(len(invocation_manifest["invocations"]), manifest["invocation_count"])
            invocation = invocation_manifest["invocations"][0]
            self.assertIn("raw_file_path", invocation)
            self.assertIsInstance(invocation["byte_count"], int)
            self.assertIsInstance(invocation["line_count"], int)
            self.assertEqual(len(invocation["sha256"]), 64)
            self.assertLess(
                deps.written.index(runner.INVOCATION_OUTPUT_MANIFEST_NAME),
                deps.written.index(runner.HASH_REPORT_NAME),
            )
            indexes = [json.loads(line)["original_attempt_index"] for line in audited_lines]
            self.assertEqual(indexes, list(range(1000)))
            raw_indexes = [json.loads(line)["original_attempt_index"] for line in raw_lines]
            self.assertEqual(raw_indexes, list(range(1000)))
            self.assertFalse((Path(output) / runner.FAILURE_MANIFEST_NAME).exists())
            self.assertEqual(hashlib.sha256((Path(output) / runner.SCHEDULE_NAME).read_bytes()).hexdigest(), digest)

    def test_raw_file_drift_and_exception_policy(self):
        lengths = synthetic_lengths()
        digest = runner.schedule_sha256(runner.build_schedule(lengths))
        with tempfile.TemporaryDirectory() as tmp:
            cases = (
                ("failed", "nonzero", "generation_process_failed"),
                ("runtime", "runtime", "unexpected_runtime_failure"),
                ("mutated", "mutate-schedule", "schedule_hash_mismatch"),
                ("symlink", "symlink", "raw_output_symlink"),
                ("deleted", "delete", "raw_output_deleted"),
                ("truncated", "truncate", "raw_output_truncated"),
                ("changed", "mutate", "raw_output_mutated"),
                ("metrics-source", "metrics-drift", "metrics_source_drift"),
                ("metrics-config", "metrics-config-drift", "metrics_configuration_drift"),
            )
            for name, crash, code_name in cases:
                output = os.path.join(tmp, name)
                code, _deps = self._run_entry(output, lengths, digest, crash=crash)
                self.assertEqual(code, 1, name)
                self.assertTrue((Path(output) / runner.FAILURE_MANIFEST_NAME).exists(), name)
                self.assertFalse((Path(output) / runner.SUCCESS_MANIFEST_NAME).exists(), name)
                failure = json.loads((Path(output) / runner.FAILURE_MANIFEST_NAME).read_text(encoding="utf-8"))
                self.assertEqual(failure["code"], code_name, name)
            preserved = os.path.join(tmp, "preserved")
            deps = build_deps(
                authorised_config(preserved, 4, digest),
                preserved + ".json",
                lengths,
                4,
                crash="failure-write",
            )
            deps.subprocess_run = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
            with self.assertRaises(runner.DevelopmentPoolError) as original:
                runner.run(preserved, "4", preserved + ".json", deps)
            self.assertEqual(original.exception.code, "unexpected_runtime_failure")
            self.assertEqual(original.exception.secondary_failure, "failure_manifest_write_failed")
            interrupted = os.path.join(tmp, "interrupted")
            with self.assertRaises(KeyboardInterrupt):
                self._run_entry(interrupted, lengths, digest, crash="keyboard")
            self.assertFalse((Path(interrupted) / runner.FAILURE_MANIFEST_NAME).exists())
            exited = os.path.join(tmp, "exited")
            with self.assertRaises(SystemExit):
                self._run_entry(exited, lengths, digest, crash="system")
            self.assertFalse((Path(exited) / runner.FAILURE_MANIFEST_NAME).exists())
            counted = os.path.join(tmp, "counted.txt")
            payload = b"AA\nBB\n"
            Path(counted).write_bytes(payload)
            record = {
                "byte_count": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "line_count": 1,
            }
            with self.assertRaises(runner.DevelopmentPoolError) as drift:
                runner.verify_regular_file(counted, record, runner.production_dependencies(), CLEANER)
            self.assertEqual(drift.exception.code, "raw_output_count_drift")

    def test_rnagenesis_fingerprint_is_exact_and_shared(self):
        generic = load_module("b1_generic_runner_fingerprint", ROOT / "scripts/b1_generic_runner.py")
        phase_b = load_module("b1_phase_b_runner_fingerprint", ROOT / "scripts/b1_phase_b_runner.py")
        self.assertEqual(runner.KNOWN_RNAGENESIS_UNTRACKED, generic.KNOWN_RNAGENESIS_UNTRACKED)
        self.assertEqual(runner.KNOWN_RNAGENESIS_UNTRACKED, phase_b.KNOWN_RNAGENESIS_UNTRACKED)
        live = runner.reviewed_rnagenesis_porcelain()
        self.assertTrue(all(line.startswith("?? ") and line.endswith("/") for line in live.splitlines()))
        runner._assert_rnagenesis_worktree(live)
        runner._assert_rnagenesis_worktree(
            "".join("?? {}\n".format(path) for path in reversed(runner.KNOWN_RNAGENESIS_UNTRACKED))
        )
        for status in (
            "",
            live + "?? notes.txt\n",
            "".join("?? {}\n".format(path) for path in runner.KNOWN_RNAGENESIS_UNTRACKED[:-1]),
            live.replace("?? configs/\n", "?? config_renamed/\n", 1),
        ):
            with self.assertRaises(runner.DevelopmentPoolError) as caught:
                runner._assert_rnagenesis_worktree(status)
            self.assertEqual(caught.exception.code, "provenance_mismatch")
            self.assertIn("known RNAGenesis", caught.exception.detail)


class ValidationAndEvidenceTests(unittest.TestCase):
    def test_validation_draws_are_deterministic_cpu_tensors(self):
        import numpy
        import torch

        torch.manual_seed(1)
        numpy.random.seed(1)
        first_steps, first_noise = artifacts.build_draw_tensors()
        torch.manual_seed(99)
        numpy.random.seed(99)
        second_steps, second_noise = artifacts.build_draw_tensors()
        self.assertTrue(torch.equal(first_steps, second_steps))
        self.assertTrue(torch.equal(first_noise, second_noise))
        self.assertEqual(tuple(first_steps.shape), (95, 4))
        self.assertEqual(tuple(first_noise.shape), (95, 4, 32, 160))
        self.assertEqual(first_steps.dtype, torch.int64)
        self.assertEqual(first_noise.dtype, torch.float32)
        self.assertEqual(first_steps.device.type, "cpu")
        self.assertEqual(first_noise.device.type, "cpu")
        self.assertFalse(torch.cuda.is_initialized())
        self.assertTrue(int(first_steps.min()) >= 0)
        self.assertTrue(int(first_steps.max()) < 1000)
        stored = artifacts.bind_stored_draws(first_steps, first_noise)
        initial_steps, initial_noise = stored("initialization")
        checkpoint_steps, checkpoint_noise = stored("checkpoint-7")
        self.assertEqual(initial_steps.data_ptr(), first_steps.data_ptr())
        self.assertEqual(checkpoint_steps.data_ptr(), first_steps.data_ptr())
        self.assertEqual(initial_noise.data_ptr(), checkpoint_noise.data_ptr())

    def test_order_artifact_has_no_sequence_text_and_refuses_real_paths(self):
        cores = ["SEQMARKER{:03d}".format(index) for index in range(95)]
        rows = [
            {"sequence_core": cores[0], "biological_length": len(cores[0])},
            {"sequence_core": cores[0], "biological_length": len(cores[0])},
            {"sequence_core": cores[1], "biological_length": len(cores[1])},
        ]
        self.assertEqual(artifacts.first_occurrence_cores(rows), [cores[0], cores[1]])
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "artifacts")
            written = artifacts.write_artifacts(output, cores)
            blob = b"".join(path.read_bytes() for path in Path(output).iterdir())
            self.assertNotIn(b"SEQMARKER", blob)
            order = (Path(output) / "validation_order_artifact.csv").read_bytes()
            self.assertTrue(order.startswith(b"role,zero_based_frozen_index,sequence_core_sha256,biological_length\n"))
            self.assertEqual(order.count(b"\n"), 96)
            self.assertNotIn(b"\r", order)
            self.assertEqual(
                written["manifest"]["validation_order_artifact_sha256"],
                hashlib.sha256(order).hexdigest(),
            )
            self.assertEqual(written["manifest"]["sequence_count"], 95)
            self.assertIs(written["manifest"]["global_rng_used"], False)
            self.assertIs(written["manifest"]["cuda_used"], False)
            self.assertIs(written["manifest"]["order_artifact_contains_sequence_text"], False)
            with self.assertRaises(artifacts.ValidationArtifactError):
                artifacts.write_artifacts(output, cores)
            with self.assertRaises(artifacts.ValidationArtifactError):
                artifacts._refuse_prohibited_path(os.path.join(tmp, "ref.csv"))

    def test_approved_validation_source_is_bound_and_artifacts_reload_exactly(self):
        raw = artifacts.APPROVED_VALIDATION_CSV.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), artifacts.VALIDATION_CSV_SHA256)
        cores = artifacts.cores_from_validation_csv(raw)
        self.assertEqual(len(cores), 95)
        self.assertEqual(len(set(cores)), 95)
        self.assertTrue(all(re.fullmatch(r"[ACGU]+", core) for core in cores))
        self.assertEqual(artifacts.cores_from_validation_csv(raw), cores)
        with tempfile.TemporaryDirectory() as tmp:
            synthetic = Path(tmp) / "synthetic.csv"
            synthetic.write_text("sequence_core,sequence_length_core\nACGU,4\n", encoding="utf-8")
            rejected = Path(tmp) / "rejected"
            with self.assertRaises(artifacts.ValidationArtifactError) as counted:
                artifacts.write_artifacts_from_validation_bytes(rejected, synthetic, synthetic.read_bytes())
            self.assertEqual(counted.exception.code, "core_count_invalid")
            self.assertFalse(rejected.exists())
            source = artifacts.source_record_from_bytes(synthetic, synthetic.read_bytes())
            self.assertIsNone(source["validation_csv_sha256"])
            self.assertNotEqual(source["sha256"], artifacts.VALIDATION_CSV_SHA256)
            self.assertIs(source["approved_validation_source"], False)
            inherited = dict(source)
            inherited["validation_csv_sha256"] = artifacts.VALIDATION_CSV_SHA256
            with self.assertRaises(artifacts.ValidationArtifactError) as inherited_error:
                artifacts.write_artifacts(Path(tmp) / "inherited", ["ACGU"], sequence_count=1, source=inherited)
            self.assertEqual(inherited_error.exception.code, "validation_source_invalid")
            directory = Path(tmp) / "artifacts"
            artifacts.write_artifacts(directory, ["ACGU"], sequence_count=1, source=source)
            manifest = json.loads((directory / "validation_draw_manifest.json").read_text(encoding="utf-8"))
            self.assertIsNone(manifest["source"]["validation_csv_sha256"])
            self.assertEqual(manifest["source"]["sha256"], source["sha256"])
            self.assertNotEqual(manifest["validation_csv_sha256"], artifacts.VALIDATION_CSV_SHA256)
            self.assertIs(manifest["source"]["approved_validation_csv_sha256_inherited"], False)
            self.assertEqual(manifest["builder"]["sha256"], hashlib.sha256(artifacts.BUILDER_PATH.read_bytes()).hexdigest())
            self.assertEqual(manifest["timestep_numpy_dtype"], "<i8")
            self.assertEqual(manifest["noise_numpy_dtype"], "<f4")
            self.assertEqual(manifest["byte_order"], "little")
            self.assertEqual(manifest["scheduler_identity"], "DDIMScheduler")
            self.assertEqual(manifest["scheduler"]["class_name"], "DDIMScheduler")
            self.assertEqual(manifest["scheduler"]["prediction_type"], "epsilon")
            self.assertEqual(manifest["scheduler"]["num_train_timesteps"], 1000)
            self.assertEqual(manifest["scheduler"]["sha256"], artifacts.SCHEDULER_CONFIG_SHA256)
            self.assertEqual(manifest["scheduler"]["path"], str(artifacts.SCHEDULER_CONFIG_PATH))
            report = json.loads((directory / artifacts.HASH_REPORT_NAME).read_text(encoding="utf-8"))
            self.assertEqual(
                report["validation_draw_manifest_sha256"],
                hashlib.sha256((directory / "validation_draw_manifest.json").read_bytes()).hexdigest(),
            )
            with self.assertRaises(artifacts.ValidationArtifactError) as refused:
                artifacts.load_verified_artifacts(directory)
            self.assertEqual(refused.exception.code, "artifact_verification_failed")
            blocked = Path(tmp) / "blocked"
            original_write = artifacts._exclusive_write

            def fail_manifest(path, payload_bytes):
                if Path(path).name == "validation_draw_manifest.json":
                    raise OSError("manifest refused")
                return original_write(path, payload_bytes)

            artifacts._exclusive_write = fail_manifest
            try:
                with self.assertRaises(artifacts.ValidationArtifactError) as failed_write:
                    artifacts.write_artifacts(blocked, ["ACGU"], sequence_count=1, source=source)
            finally:
                artifacts._exclusive_write = original_write
            self.assertEqual(failed_write.exception.code, "artifact_write_failed")
            self.assertFalse((blocked / "validation_draw_manifest.json").exists())
            self.assertTrue((blocked / "validation_noise.float32").exists())
        with self.assertRaises(artifacts.ValidationArtifactError) as rejected_cli:
            artifacts.main(["--cores-json", "[]", "--output-directory", "/tmp/unused-validation-artifacts"])
        self.assertEqual(rejected_cli.exception.code, "validation_source_invalid")

    def test_production_materialisation_requires_main_a_clean_tree_and_the_head_blob(self):
        builder = artifacts.BUILDER_PATH.read_bytes()
        scheduler = artifacts.SCHEDULER_CONFIG_PATH.read_bytes()
        head = "c" * 40
        blob = "ab" * 20

        def reader(path):
            text = str(path)
            if text == str(artifacts.BUILDER_PATH):
                return builder
            if text == str(artifacts.SCHEDULER_CONFIG_PATH):
                return scheduler
            raise AssertionError(text)

        def git_for(porcelain, head_blob, worktree_blob, blob_bytes, branch="main"):
            def git(args, binary=False):
                if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                    return branch + "\n"
                if args == ["status", "--porcelain=v1"]:
                    return porcelain
                if args == ["rev-parse", "HEAD"]:
                    return head + "\n"
                if args == ["rev-parse", "{}:{}".format(head, artifacts.BUILDER_RELATIVE)]:
                    return head_blob + "\n"
                if args[:2] == ["hash-object", "--"]:
                    return worktree_blob + "\n"
                if args == ["cat-file", "blob", head_blob]:
                    return blob_bytes if binary else blob_bytes.decode("utf-8")
                raise AssertionError(args)

            return git

        for porcelain in (" M scripts/modelling/build_validation_artifacts.py\n", "M  scripts/modelling/build_validation_artifacts.py\n", "?? notes.txt\n"):
            with self.assertRaises(artifacts.ValidationArtifactError) as dirty:
                artifacts.assert_production_materialisation(
                    git=git_for(porcelain, blob, blob, builder),
                    read_bytes=reader,
                )
            self.assertEqual(dirty.exception.code, "builder_worktree_dirty")
        with self.assertRaises(artifacts.ValidationArtifactError) as wrong_id:
            artifacts.assert_production_materialisation(
                git=git_for("", blob, "cd" * 20, builder),
                read_bytes=reader,
            )
        self.assertEqual(wrong_id.exception.code, "builder_blob_mismatch")
        with self.assertRaises(artifacts.ValidationArtifactError) as wrong_bytes:
            artifacts.assert_production_materialisation(
                git=git_for("", blob, blob, b"different-builder-bytes"),
                read_bytes=reader,
            )
        self.assertEqual(wrong_bytes.exception.code, "builder_blob_mismatch")
        accepted = artifacts.assert_production_materialisation(
            git=git_for("", blob, blob, builder),
            read_bytes=reader,
        )
        self.assertEqual(accepted["branch"], "main")
        self.assertEqual(accepted["commit"], head)
        self.assertEqual(accepted["git_blob"], blob)
        self.assertEqual(accepted["builder_sha256"], hashlib.sha256(builder).hexdigest())
        self.assertEqual(accepted["scheduler"]["path"], str(artifacts.SCHEDULER_CONFIG_PATH))
        self.assertEqual(accepted["scheduler"]["sha256"], artifacts.SCHEDULER_CONFIG_SHA256)
        self.assertEqual(accepted["scheduler"]["class_name"], "DDIMScheduler")
        self.assertEqual(accepted["scheduler"]["prediction_type"], "epsilon")
        self.assertEqual(accepted["scheduler"]["num_train_timesteps"], 1000)

        def drifted_reader(path):
            if str(path) == str(artifacts.SCHEDULER_CONFIG_PATH):
                return scheduler.replace(b'"epsilon"', b'"sample"')
            return reader(path)

        with self.assertRaises(artifacts.ValidationArtifactError) as drifted:
            artifacts.assert_production_materialisation(
                git=git_for("", blob, blob, builder),
                read_bytes=drifted_reader,
            )
        self.assertEqual(drifted.exception.code, "scheduler_configuration_drift")

    def test_loader_detects_manifest_scheduler_and_coherent_payload_tampering(self):
        import shutil
        import torch

        raw = artifacts.APPROVED_VALIDATION_CSV.read_bytes()
        cores = artifacts.cores_from_validation_csv(raw)
        source = artifacts.source_record_from_bytes(artifacts.APPROVED_VALIDATION_CSV, raw)
        original_blob = artifacts._builder_file_at_commit

        def matching_blob(commit):
            if not artifacts._is_sha40(commit):
                raise artifacts.ValidationArtifactError("builder_blob_mismatch", "commit")
            return artifacts.BUILDER_PATH.read_bytes()

        artifacts._builder_file_at_commit = matching_blob
        try:
            with tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp) / "artifacts"
                artifacts.write_artifacts(directory, cores, source=source)
                calls = {"count": 0}
                original_draw = artifacts.build_draw_tensors

                def counted(*args, **kwargs):
                    calls["count"] += 1
                    return original_draw(*args, **kwargs)

                artifacts.build_draw_tensors = counted
                try:
                    loaded = artifacts.load_verified_artifacts(directory)
                finally:
                    artifacts.build_draw_tensors = original_draw
                self.assertEqual(calls["count"], 0)
                expected_steps, expected_noise = artifacts.build_draw_tensors()
                self.assertTrue(torch.equal(loaded["timesteps"], expected_steps))
                self.assertTrue(torch.equal(loaded["noise"], expected_noise))
                manifest = loaded["manifest"]
                self.assertEqual(manifest["schema_version"], artifacts.SCHEMA_VERSION)
                self.assertEqual(manifest["role"], "VALIDATION")
                self.assertEqual(manifest["sequence_count"], 95)
                self.assertEqual(manifest["draws_per_sequence"], 4)
                self.assertEqual(manifest["seed"], 1)
                self.assertEqual(manifest["timestep_shape"], [95, 4])
                self.assertEqual(manifest["noise_shape"], [95, 4, 32, 160])
                self.assertEqual(manifest["byte_order"], "little")
                self.assertEqual(manifest["timestep_dtype"], "int64")
                self.assertEqual(manifest["noise_dtype"], "float32")
                self.assertEqual(manifest["source"]["sha256"], artifacts.VALIDATION_CSV_SHA256)
                self.assertEqual(manifest["source"]["path"], str(artifacts.APPROVED_VALIDATION_CSV))
                self.assertEqual(len(manifest["builder"]["commit"]), 40)
                self.assertEqual(len(manifest["builder"]["sha256"]), 64)
                report_path = directory / artifacts.HASH_REPORT_NAME
                manifest_path = directory / artifacts.MANIFEST_NAME
                report = json.loads(report_path.read_text(encoding="utf-8"))
                self.assertEqual(report["validation_draw_manifest_sha256"], hashlib.sha256(manifest_path.read_bytes()).hexdigest())
                with self.assertRaises(artifacts.ValidationArtifactError) as wrong:
                    artifacts.load_verified_artifacts(directory, expected_source_sha256="0" * 64)
                self.assertEqual(wrong.exception.code, "wrong_validation_source")

                def copy_case(name):
                    destination = Path(tmp) / name
                    shutil.copytree(directory, destination)
                    return destination

                manifest_case = copy_case("manifest")
                rewritten = json.loads((manifest_case / artifacts.MANIFEST_NAME).read_text(encoding="utf-8"))
                rewritten["seed"] = 2
                (manifest_case / artifacts.MANIFEST_NAME).write_bytes(artifacts.canonical_manifest_bytes(rewritten))
                with self.assertRaises(artifacts.ValidationArtifactError) as manifest_error:
                    artifacts.load_verified_artifacts(manifest_case)
                self.assertEqual(manifest_error.exception.code, "manifest_tampered")

                scheduler_case = copy_case("scheduler")
                scheduler_document = json.loads((scheduler_case / artifacts.MANIFEST_NAME).read_text(encoding="utf-8"))
                scheduler_document["scheduler_prediction_type"] = "sample"
                scheduler_document["scheduler"]["prediction_type"] = "sample"
                scheduler_bytes = artifacts.canonical_manifest_bytes(scheduler_document)
                (scheduler_case / artifacts.MANIFEST_NAME).write_bytes(scheduler_bytes)
                scheduler_report = json.loads((scheduler_case / artifacts.HASH_REPORT_NAME).read_text(encoding="utf-8"))
                scheduler_report["validation_draw_manifest_sha256"] = hashlib.sha256(scheduler_bytes).hexdigest()
                (scheduler_case / artifacts.HASH_REPORT_NAME).write_bytes(artifacts.canonical_manifest_bytes(scheduler_report))
                with self.assertRaises(artifacts.ValidationArtifactError) as scheduler_error:
                    artifacts.load_verified_artifacts(scheduler_case)
                self.assertEqual(scheduler_error.exception.code, "scheduler_configuration_drift")

                coherent_case = copy_case("coherent")
                noise_path = coherent_case / "validation_noise.float32"
                noise_payload = bytearray(noise_path.read_bytes())
                noise_payload[-1] ^= 0xFF
                noise_path.write_bytes(noise_payload)
                coherent_document = json.loads((coherent_case / artifacts.MANIFEST_NAME).read_text(encoding="utf-8"))
                coherent_document["noise_tensor_sha256"] = hashlib.sha256(bytes(noise_payload)).hexdigest()
                coherent_document["noise_byte_count"] = len(noise_payload)
                coherent_manifest_bytes = artifacts.canonical_manifest_bytes(coherent_document)
                (coherent_case / artifacts.MANIFEST_NAME).write_bytes(coherent_manifest_bytes)
                self.assertEqual(
                    coherent_document["noise_tensor_sha256"],
                    hashlib.sha256(noise_path.read_bytes()).hexdigest(),
                )
                stale_report = json.loads((coherent_case / artifacts.HASH_REPORT_NAME).read_text(encoding="utf-8"))
                self.assertNotEqual(
                    stale_report["validation_draw_manifest_sha256"],
                    hashlib.sha256(coherent_manifest_bytes).hexdigest(),
                )
                with self.assertRaises(artifacts.ValidationArtifactError) as coherent_error:
                    artifacts.load_verified_artifacts(coherent_case)
                self.assertEqual(coherent_error.exception.code, "manifest_tampered")

                builder_case = copy_case("builder")
                artifacts._builder_file_at_commit = lambda commit: b"not-the-accepted-builder"
                try:
                    with self.assertRaises(artifacts.ValidationArtifactError) as builder_error:
                        artifacts.load_verified_artifacts(builder_case)
                finally:
                    artifacts._builder_file_at_commit = matching_blob
                self.assertEqual(builder_error.exception.code, "builder_blob_mismatch")

                payload_case = copy_case("payload")
                payload_path = payload_case / "validation_noise.float32"
                flipped = bytearray(payload_path.read_bytes())
                flipped[0] ^= 0xFF
                payload_path.write_bytes(flipped)
                with self.assertRaises(artifacts.ValidationArtifactError) as payload_error:
                    artifacts.load_verified_artifacts(payload_case)
                self.assertEqual(payload_error.exception.code, "artifact_tampered")
        finally:
            artifacts._builder_file_at_commit = original_blob

    def test_clustering_is_deferred_and_prior_evidence_is_unchanged(self):
        source = (ROOT / "scripts/modelling/m4_diagnostic_metrics.py").read_text(encoding="utf-8")
        self.assertIn("DEFERRED_BEYOND_M4", source)
        self.assertNotIn("def cluster", source)
        self.assertNotIn("embedding", source)
        config = yaml.safe_load(B1_CONFIG.read_text(encoding="utf-8"))
        expected = {
            PHASE_A / "phase_a_manifest.json": "582fe16d622660c5d305cd4763b1fd8091c3c773798fbf94f0ec723d8322c47a",
            PHASE_A / "phase_a_manifest_sha256.json": "79d43c43d42539eb9da2339b1f0dd8917b108c28c64da22059e43ec0ebbcbfe1",
            PHASE_A / "phase_a_raw_attempts.jsonl": "650bcc01eea4cfd0f33feb7fbd3569f4d0c176b750ab8aec9f61f5c97c01c0dc",
            PHASE_A / "phase_a_audited_attempts.jsonl": "a9e153fc47bf71b7839c3c1880d33f7d6655eb7a2defccda9d8bea38ee607f3c",
            PHASE_B / "phase_b_manifest.json": "49cd5b773a0701606ba63f9b28c03cfb6a4aee32865e7f65a4e849481d628de7",
            PHASE_B / "phase_b_manifest_sha256.json": "c81f628389e257bb1e5bb7577e3450c55348ececbb44c2a11b15a299fb0a088e",
            PHASE_B / "phase_b_raw_attempts.jsonl": "bc8baf3f1dd8f9f1e21efd4a8489a0ccec9908f5ed9a6723cab60a2f68366c9b",
            PHASE_B / "phase_b_audited_attempts.jsonl": "a20911c33d647fb3de1fdc0c8a32d944e33e124e37ab76dd481631cbde52259a",
            B2_ATTEMPT2 / "b2_empirical_null_raw.jsonl": "bbe35f448db0d7fc02ad0156865798382b0b41e9ad047b4e52eddf7cff740c83",
            B2_ATTEMPT2 / "manifest.json": "31c07fb966c462263307569b383b112ecfb39725adb9b1b2fd2f93a95d3d8baa",
            B0_CHECKSUM: "ad3a75fe157248be50427757357cbc5c060be3ddb664d3be64ef178ac90b85c3",
        }
        for path, digest in expected.items():
            self.assertEqual(sha256_file(path), digest)
        self.assertEqual(
            config["phase_a_evidence_acceptance"]["evidence_sha256"]["phase_a_manifest_json"],
            expected[PHASE_A / "phase_a_manifest.json"],
        )
        self.assertEqual(
            config["phase_b_evidence_acceptance"]["evidence_sha256"]["phase_b_manifest_json"],
            expected[PHASE_B / "phase_b_manifest.json"],
        )
        self.assertFalse((ROOT / "scripts/exact_length_schedule.py").exists())
        self.assertFalse((ROOT / "tests/test_exact_length_schedule.py").exists())


if __name__ == "__main__":
    unittest.main()
