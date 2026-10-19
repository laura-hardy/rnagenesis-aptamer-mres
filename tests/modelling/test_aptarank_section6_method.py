"""Synthetic checks for the Section 6 method freeze.

Sequences and secrets in this module are invented in memory. No production
secret is stored. No TRAIN, VALIDATION, REF, EVAL, or results file is opened.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import sys
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from fractions import Fraction
from io import StringIO

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELLING = os.path.join(ROOT, "scripts", "modelling")
if MODELLING not in sys.path:
    sys.path.insert(0, MODELLING)

import aptarank_section6_analysis as analysis
import aptarank_section6_blinding as blinding
import aptarank_section6_uniform as uniform

HISTORICAL_SHA256 = {
    "config/modelling/aptarank_tier1_analysis_spec.json":
        "5065112af2de0668f3ed240242dacbdd73ccadfccc15d288769353bafadda03e",
    "scripts/modelling/aptarank_tier1_analysis.py":
        "127d20a1e14d8f72dca1913a596be0a812cba1be25c310d5ca7c1c86c32a7f6c",
    "config/modelling/aptarank_candidate_preparation_contract.json":
        "3bcfbdf14cd7e777a0b2746f91d0335ba4876195f5012610157e5aa23e083096",
    "config/modelling/aptarank_reference_upload_contract.json":
        "34912929e77a0a835a01e36ba0291160b49b60dcdfb12a2d2aeb57090c794d02",
    "config/modelling/aptarank_io_spec.json":
        "46ba6c8be873dad4c086e9f6b889b51702ba31212fa502d00f26e267a22da732",
    "scripts/modelling/aptarank_io_preflight.py":
        "eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01",
    "docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md":
        "b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe",
    "docs/aptarank_full_mres_thesis_evaluation_plan_v3_4.md":
        "1f3a73bc294a75c527e11f074c6d3265786c8e7e70d41eacf3ea83d3cf512941",
    "docs/aptarank_full_mres_thesis_evaluation_plan_v3_5.md":
        "ebb0e66dd35c7ed20abecacf710ea7a90dd0e2737ba1973af66e8f0753e22c9d",
}


def file_sha256(relative):
    with open(os.path.join(ROOT, relative), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def byte_record(payload):
    return {"sha256": hashlib.sha256(payload).hexdigest(), "byte_count": len(payload)}


def scientific_view(summary):
    """Scientific summary without the exact upload and export byte identity."""
    view = dict(summary)
    view.pop("analyzed_bytes")
    return view


def synthetic_secret(label):
    """Derive an ephemeral test key. This is not a production secret."""
    return hashlib.sha256(b"section6-synthetic-test\0" + label.encode("ascii")).digest()


def sequence_for(index, length):
    alphabet = "ACGU"
    value = index
    characters = []
    for _ in range(length):
        characters.append(alphabet[value % 4])
        value //= 4
    if value:
        raise AssertionError("sequence space exhausted")
    return "".join(characters)


def parents_for(count, clusters, length=20):
    if count < clusters or count > 2 * clusters:
        raise AssertionError("cluster allocation is outside the test helper")
    paired = count - clusters
    sizes = [2] * paired + [1] * (clusters - paired)
    parents = []
    index = 0
    for cluster_number, size in enumerate(sizes):
        for _ in range(size):
            parents.append(
                {
                    "parent_core_id": "synthetic-parent-%03d" % index,
                    "cluster_id": "synthetic-cluster-%02d" % cluster_number,
                    "sequence": sequence_for(index, length),
                }
            )
            index += 1
    return parents


def reference_draw(parent_digest, attempt, length):
    nucleotides = []
    block = 0
    while len(nucleotides) < length:
        payload = uniform.length_delimited_bytes(
            [
                uniform.UNIFORM_DOMAIN,
                "42",
                parent_digest,
                str(attempt),
                str(block),
            ]
        )
        digest = hashlib.sha256(payload).digest()
        block += 1
        for value in digest:
            if value >= 252:
                continue
            nucleotides.append("ACGU"[value % 4])
            if len(nucleotides) == length:
                break
    return "".join(nucleotides)


def export_bytes(private_key, upload, assignments, failed_ids):
    upload_sequences = {}
    for line in upload.decode("utf-8").splitlines()[1:]:
        identifier, sequence = line.split(",")
        upload_sequences[identifier] = sequence
    rows = []
    failures = []
    for candidate in private_key["candidates"]:
        identifier = candidate["candidate_id"]
        if identifier in failed_ids:
            failures.append({"candidate_id": identifier, "reason": "synthetic technical failure"})
            continue
        score, shuffle = assignments[(candidate["parent_core_id"], candidate["class_label"])]
        rows.append(
            {
                "candidate": identifier,
                "score": score,
                "shuffle": shuffle,
                "sequence": upload_sequences[identifier],
                "length": candidate["length"],
            }
        )
    rows.sort(key=lambda row: (-Fraction(Decimal(row["score"])), row["candidate"]))
    lines = ["rank,candidate,aptamer-likeness,compatibility,shuffle,len,sequence"]
    for rank, row in enumerate(rows, start=1):
        lines.append(
            "%d,%s,%s,not evaluated,%s,%d,%s"
            % (rank, row["candidate"], row["score"], row["shuffle"], row["length"], row["sequence"])
        )
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    return payload, failures


def shuffled_export(payload):
    lines = payload.decode("utf-8").splitlines()
    data = list(reversed(lines[1:]))
    return ("\n".join([lines[0]] + data) + "\n").encode("utf-8")


def render_export(rows):
    lines = ["rank,candidate,aptamer-likeness,compatibility,shuffle,len,sequence"]
    for row in rows:
        lines.append(
            "%d,%s,%s,not evaluated,%s,%d,%s"
            % (row["rank"], row["candidate"], row["score"], row["shuffle"], row["length"], row["sequence"])
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


class Section6MethodTests(unittest.TestCase):
    def test_historical_contracts_and_draft_are_unchanged(self):
        for relative, digest in HISTORICAL_SHA256.items():
            self.assertEqual(file_sha256(relative), digest, relative)
        contract = blinding.load_pinned_contract()
        self.assertEqual(contract["governing_plan"]["version"], "3.5")
        self.assertFalse(contract["historical_m9b_tier1_draft"]["modified_by_section6"])
        self.assertFalse(contract["historical_m9b_tier1_draft"]["production_ready"])
        self.assertEqual(contract["scorer_owner"], "deployed AptaRank UI")
        self.assertEqual(
            contract["statistics"]["secondary_test"]["variance_formula"],
            "n(n+1)(2n+1)/24 - sum(t^3-t)/48",
        )
        self.assertEqual(contract["statistics"]["secondary_test"]["variance_formula"], analysis.VARIANCE_FORMULA)
        resolved = {item["id"]: item for item in contract["m9c_deployment_resolution"]["resolved"]}
        self.assertFalse(resolved["tier2_bank_realized_count"]["used_by_section6_tier1"])
        self.assertEqual(resolved["tier2_bank_realized_count"]["status"], "provenance_only_unused_by_section6_tier1")
        self.assertFalse(resolved["band_thresholds"]["used_by_section6_tier1"])
        self.assertIn("same caller-supplied 32-byte secret", contract["blinding"]["order_secret"])
        self.assertTrue(contract["analyzed_bytes"]["separate_from_optional_run_artifacts"])
        self.assertIn("optional raw-artifact list is empty", contract["analyzed_bytes"]["when_optional_artifacts_empty"])
        artifacts = contract["raw_run_artifacts"]
        self.assertFalse(artifacts["production_schema_observed"])
        self.assertFalse(artifacts["production_schema_frozen"])
        self.assertEqual(artifacts["self_declared_scorer_and_role"], "unverified")
        self.assertEqual(artifacts["component_acceptance_gate"], analysis.component_acceptance_gate())
        self.assertEqual(
            artifacts["component_acceptance_gate"]["summarizing_exported_values"],
            "allowed",
        )
        self.assertEqual(
            artifacts["component_acceptance_gate"]["recomputing_component_values"],
            "refused",
        )

    def test_byte_mapping_is_unbiased_and_length_delimited_layout_matches_m9b2(self):
        import aptarank_candidate_preparation as preparation

        counts = {"A": 0, "C": 0, "G": 0, "U": 0}
        discarded = 0
        for value in range(256):
            nucleotide = uniform.nucleotide_from_byte(value)
            if nucleotide is None:
                discarded += 1
            else:
                counts[nucleotide] += 1
        self.assertEqual(discarded, 4)
        self.assertEqual(counts, {"A": 63, "C": 63, "G": 63, "U": 63})
        self.assertEqual([uniform.nucleotide_from_byte(value) for value in range(4)], ["A", "C", "G", "U"])
        self.assertIsNone(uniform.nucleotide_from_byte(252))
        self.assertIsNone(uniform.nucleotide_from_byte(255))
        components = ["aptarank-section6-uniform-v1", "42", "ab" * 32, "0", "3"]
        self.assertEqual(
            uniform.length_delimited_bytes(components),
            preparation.length_delimited_bytes(components),
        )
        exercised = False
        for index in range(80):
            digest = uniform.core_digest(sequence_for(index, 8))
            if any(value >= 252 for value in uniform.stream_digest(digest, 0, 0)):
                exercised = True
                self.assertEqual(uniform.draw_attempt(digest, 0, 8), reference_draw(digest, 0, 8))
                break
        self.assertTrue(exercised)

    def test_controls_are_deterministic_exact_length_and_reject_collisions(self):
        parents = parents_for(5, 3, length=8)
        inventory = [uniform.core_digest(parent["sequence"]) for parent in parents]
        first_parents, first_controls = uniform.generate_uniform_controls(parents, inventory)
        second_parents, second_controls = uniform.generate_uniform_controls(list(reversed(parents)), inventory)
        self.assertEqual(first_parents, second_parents)
        self.assertEqual(first_controls, second_controls)
        for parent, control in zip(first_parents, first_controls):
            self.assertEqual(control["length"], parent["length"])
            self.assertEqual(len(control["sequence"]), parent["length"])
            self.assertNotEqual(control["source_digest"], parent["source_digest"])
            self.assertEqual(control["accepted_attempt"], 0)
        lone = uniform.core_digest("ACGUACGU")
        accepted = uniform.draw_uniform_control(lone, 6, set())
        rejected = uniform.draw_uniform_control(lone, 6, {accepted["source_digest"]})
        self.assertNotEqual(rejected["sequence"], accepted["sequence"])
        self.assertGreaterEqual(rejected["accepted_attempt"], 1)
        self.assertEqual(len(rejected["sequence"]), 6)
        collision = None
        for left in range(48):
            for right in range(left + 1, 48):
                left_sequence = sequence_for(left, 3)
                right_sequence = sequence_for(right, 3)
                left_digest = uniform.core_digest(left_sequence)
                right_digest = uniform.core_digest(right_sequence)
                earlier, later = (left_digest, right_digest) if left_digest < right_digest else (right_digest, left_digest)
                earlier_draw = uniform.draw_attempt(earlier, 0, 3)
                later_draw = uniform.draw_attempt(later, 0, 3)
                if later_draw == earlier_draw and uniform.core_digest(earlier_draw) not in {earlier, later}:
                    collision = (earlier, later)
                    break
            if collision is not None:
                break
        self.assertIsNotNone(collision)
        earlier, later = collision
        parent_rows = []
        for digest, label in ((earlier, "earlier"), (later, "later")):
            sequence = None
            for index in range(48):
                candidate = sequence_for(index, 3)
                if uniform.core_digest(candidate) == digest:
                    sequence = candidate
                    break
            parent_rows.append({"parent_core_id": label, "cluster_id": "cluster", "sequence": sequence})
        ordered, controls = uniform.generate_uniform_controls(parent_rows, [earlier, later])
        self.assertEqual([row["source_digest"] for row in ordered], [earlier, later])
        self.assertEqual(controls[0]["accepted_attempt"], 0)
        self.assertGreaterEqual(controls[1]["accepted_attempt"], 1)
        self.assertNotEqual(controls[1]["sequence"], controls[0]["sequence"])

    def test_attempt_cap_fails_closed(self):
        inventory = {uniform.core_digest(base) for base in "ACGU"}
        with self.assertRaises(uniform.Section6Error) as caught:
            uniform.draw_uniform_control(uniform.core_digest("ACGUACGUACGUACGUACGU"), 1, inventory)
        self.assertEqual(caught.exception.code, "attempt_cap_exhausted")
        self.assertIn("10000", caught.exception.detail)
        self.assertNotIn("sequence", caught.exception.detail)

    def test_blinding_order_collision_and_secret_absence(self):
        secret = synthetic_secret("blinding")
        other = synthetic_secret("other")
        parents = parents_for(4, 2, length=20)
        inventory = [uniform.core_digest(parent["sequence"]) for parent in parents]
        prepared = blinding.prepare_section6_upload(parents, inventory, secret)
        reversed_input = blinding.prepare_section6_upload(list(reversed(parents)), inventory, secret)
        self.assertEqual(prepared["candidate_upload"], reversed_input["candidate_upload"])
        self.assertEqual(prepared["private_key_bytes"], reversed_input["private_key_bytes"])
        other_prepared = blinding.prepare_section6_upload(parents, inventory, other)
        self.assertNotEqual(prepared["candidate_upload"], other_prepared["candidate_upload"])
        lines = prepared["candidate_upload"].decode("utf-8").splitlines()
        self.assertEqual(lines[0], "id,sequence")
        sequences = []
        for line in lines[1:]:
            identifier, sequence = line.split(",")
            self.assertRegex(identifier, r"^cand_[0-9a-f]{32}$")
            self.assertEqual(identifier, blinding.candidate_id(sequence, secret))
            sequences.append(sequence)
        self.assertEqual(sequences, sorted(sequences, key=lambda sequence: blinding.order_key(sequence, secret)))
        order_payload = uniform.length_delimited_bytes([blinding.ORDER_DOMAIN, sequences[0]])
        self.assertEqual(
            blinding.order_key(sequences[0], secret),
            hmac.new(secret, order_payload, hashlib.sha256).digest(),
        )
        labels = sorted(row["class_label"] for row in prepared["private_key"]["candidates"])
        self.assertEqual(labels, ["eval_core"] * 4 + ["paired_uniform_shuffle"] * 4)
        self.assertNotEqual(sequences, sorted(sequences))
        self.assertNotIn(b"class", prepared["candidate_upload"])
        self.assertNotIn(b"pair", prepared["candidate_upload"])
        self.assertNotIn(b"cluster", prepared["candidate_upload"])
        self.assertNotIn(b"target", prepared["candidate_upload"])
        for row in prepared["private_key"]["candidates"]:
            self.assertEqual(tuple(row), blinding.PRIVATE_KEY_FIELDS)
            self.assertNotIn("sequence", row)
        secret_blobs = (
            prepared["candidate_upload"],
            prepared["private_key_bytes"],
            prepared["manifest_bytes"],
        )
        for blob in secret_blobs:
            self.assertNotIn(secret, blob)
            self.assertNotIn(secret.hex().encode("ascii"), blob)
        self.assertTrue(prepared["manifest"]["synthetic"])
        self.assertFalse(prepared["manifest"]["production_authorized"])
        self.assertFalse(prepared["manifest"]["secret_embedded"])
        with self.assertRaises(uniform.Section6Error) as caught:
            blinding.reject_duplicate_ids([("AAAA", "cand_" + "ab" * 16), ("CCCC", "cand_" + "ab" * 16)])
        self.assertEqual(caught.exception.code, "opaque_id_collision")
        with self.assertRaises(uniform.Section6Error) as caught:
            blinding.reject_duplicate_order_keys([("AAAA", b"same-order-key"), ("CCCC", b"same-order-key")])
        self.assertEqual(caught.exception.code, "order_key_collision")
        original = blinding.candidate_id
        blinding.candidate_id = lambda sequence, key: "cand_" + "cd" * 16
        try:
            with self.assertRaises(uniform.Section6Error) as caught:
                blinding.prepare_section6_upload(parents[:2], inventory[:2], secret)
            self.assertEqual(caught.exception.code, "opaque_id_collision")
        finally:
            blinding.candidate_id = original

    def test_production_count_gate_on_synthetic_308(self):
        secret = synthetic_secret("gate")
        parents = parents_for(154, 79, length=20)
        inventory = [uniform.core_digest(parent["sequence"]) for parent in parents]
        prepared = blinding.prepare_section6_upload(
            parents,
            inventory,
            secret,
            enforce_production_counts=True,
        )
        self.assertEqual(
            prepared["manifest"]["counts"],
            {
                "real_memberships": 154,
                "controls": 154,
                "complete_pairs": 154,
                "unique_upload_sequences": 308,
                "pre_rejection_clusters": 79,
            },
        )
        self.assertEqual(prepared["manifest"]["production_count_gate"], "passed_synthetic_fixture")
        self.assertFalse(prepared["manifest"]["production_upload_instantiated"])
        body = prepared["candidate_upload"].decode("utf-8").splitlines()
        self.assertEqual(len(body), 309)
        self.assertEqual(len({line.split(",")[1] for line in body[1:]}), 308)
        small = parents_for(3, 2, length=20)
        with self.assertRaises(uniform.Section6Error) as caught:
            blinding.prepare_section6_upload(
                small,
                [uniform.core_digest(parent["sequence"]) for parent in small],
                secret,
                enforce_production_counts=True,
            )
        self.assertEqual(caught.exception.code, "production_count_mismatch")

    def test_run_sheet_and_target_free_token_rejection(self):
        template = blinding.run_sheet_template()
        self.assertEqual(blinding.check_run_sheet(template)["protein_target"], None)
        self.assertEqual(template["expected_compatibility_token"], "not evaluated")
        self.assertEqual(template["preset"], "Standard")
        self.assertEqual(template["candidate_shuffles"], 20)
        self.assertEqual(template["ensemble_samples"], 100)
        self.assertEqual(template["seed"], 42)
        for field, value in (
            ("protein_target", "5ZGX"),
            ("preset", "quick"),
            ("candidate_shuffles", 99),
            ("reference_upload_sha256", "0" * 64),
        ):
            mutated = dict(template)
            mutated[field] = value
            with self.assertRaises(uniform.Section6Error) as caught:
                blinding.check_run_sheet(mutated)
            self.assertEqual(caught.exception.code, "run_sheet_discrepancy")
            self.assertTrue(caught.exception.rerun_lineage_required)
        secret = synthetic_secret("tokens")
        parents = parents_for(2, 2, length=20)
        inventory = [uniform.core_digest(parent["sequence"]) for parent in parents]
        prepared = blinding.prepare_section6_upload(parents, inventory, secret)
        assignments = {
            (row["parent_core_id"], row["class_label"]): ("0.5", "pass")
            for row in prepared["private_key"]["candidates"]
        }
        export, failures = export_bytes(prepared["private_key"], prepared["candidate_upload"], assignments, set())
        text = export.decode("utf-8").replace("not evaluated", "strong")
        with self.assertRaises(uniform.Section6Error) as caught:
            analysis.summarize_section6(
                prepared["candidate_upload"],
                prepared["private_key"],
                text.encode("utf-8"),
                failures=failures,
                run_sheet=template,
                raw_artifacts=[],
            )
        self.assertEqual(caught.exception.code, "invalid_compatibility")
        self.assertTrue(caught.exception.rerun_lineage_required)
        bad_header = prepared["candidate_upload"].decode("utf-8").replace("id,sequence", "id,sequence,class", 1)
        with self.assertRaises(uniform.Section6Error) as caught:
            analysis.summarize_section6(
                bad_header.encode("utf-8"),
                prepared["private_key"],
                export,
                raw_artifacts=[],
            )
        self.assertEqual(caught.exception.code, "schema_mismatch")
        self.assertTrue(caught.exception.rerun_lineage_required)

    def test_id_join_is_stable_when_export_rows_are_shuffled(self):
        secret = synthetic_secret("join")
        parents = parents_for(3, 2, length=20)
        inventory = [uniform.core_digest(parent["sequence"]) for parent in parents]
        prepared = blinding.prepare_section6_upload(parents, inventory, secret)
        assignments = {
            ("synthetic-parent-000", "eval_core"): ("0.8", "pass"),
            ("synthetic-parent-000", "paired_uniform_shuffle"): ("0.1", "fail"),
            ("synthetic-parent-001", "eval_core"): ("0.9", "pass"),
            ("synthetic-parent-001", "paired_uniform_shuffle"): ("0.2", "fail"),
            ("synthetic-parent-002", "eval_core"): ("0.4", "pass"),
            ("synthetic-parent-002", "paired_uniform_shuffle"): ("0.4", "pass"),
        }
        failed = {
            row["candidate_id"]
            for row in prepared["private_key"]["candidates"]
            if row["parent_core_id"] == "synthetic-parent-000" and row["class_label"] == "paired_uniform_shuffle"
        }
        export, failures = export_bytes(prepared["private_key"], prepared["candidate_upload"], assignments, failed)
        first = analysis.summarize_section6(
            prepared["candidate_upload"],
            prepared["private_key"],
            export,
            failures=failures,
            run_sheet=blinding.run_sheet_template(),
            raw_artifacts=[],
        )
        second = analysis.summarize_section6(
            prepared["candidate_upload"],
            prepared["private_key_bytes"],
            shuffled_export(export),
            failures=failures,
            run_sheet=blinding.run_sheet_template(),
            raw_artifacts=[],
        )
        self.assertEqual(scientific_view(first), scientific_view(second))
        self.assertEqual(first["analyzed_bytes"]["candidate_upload"], byte_record(prepared["candidate_upload"]))
        self.assertEqual(second["analyzed_bytes"]["candidate_upload"], first["analyzed_bytes"]["candidate_upload"])
        self.assertEqual(first["analyzed_bytes"]["downloaded_export"], byte_record(export))
        self.assertEqual(second["analyzed_bytes"]["downloaded_export"], byte_record(shuffled_export(export)))
        self.assertNotEqual(
            first["analyzed_bytes"]["downloaded_export"]["sha256"],
            second["analyzed_bytes"]["downloaded_export"]["sha256"],
        )
        denominators = first["denominators"]
        self.assertEqual(denominators["input_candidates"], 6)
        self.assertEqual(denominators["evaluable_scores"], 5)
        self.assertEqual(denominators["technical_failures"], 1)
        self.assertEqual(denominators["complete_score_pairs"], 2)
        self.assertEqual(denominators["incomplete_score_pairs"], 1)
        self.assertEqual(denominators["pre_rejection_clusters"], 2)
        self.assertEqual(
            denominators["shuffle_valid_by_class"],
            {"eval_core": 3, "paired_uniform_shuffle": 2},
        )
        self.assertEqual(
            denominators["shuffle_pass_by_class"],
            {"eval_core": 3, "paired_uniform_shuffle": 1},
        )
        self.assertEqual(denominators["paired_shuffle_pairs"], 2)
        self.assertEqual(denominators["imputed_replicates"], 0)
        self.assertEqual(first["class_summaries"]["eval_core"]["median"], "0.8")
        self.assertEqual(first["class_summaries"]["eval_core"]["mean"], "0.7")
        self.assertEqual(first["class_summaries"]["eval_core"]["q1"], "0.6")
        self.assertEqual(first["class_summaries"]["eval_core"]["q3"], "0.85")
        self.assertEqual(first["paired"]["median_difference"], "0.35")
        self.assertEqual(first["paired"]["mean_difference"], "0.35")
        self.assertEqual(first["auroc"]["value"], "0.875")
        self.assertEqual(first["shuffle"]["real_pass_rate"], "1")
        self.assertEqual(first["shuffle"]["control_pass_rate"], "0.5")
        self.assertEqual(first["shuffle"]["paired_pass_difference"], "0.5")
        self.assertFalse(first["scores_recomputed"])
        self.assertEqual(first["favourable_direction"], "higher_aptamer_likeness")

    def test_auroc_ties_and_wilcoxon_zero_and_tied_cases(self):
        self.assertEqual(analysis.render_fraction(analysis.auroc([Fraction(1), Fraction(2)], [Fraction(2), Fraction(2)])), "0.25")
        self.assertEqual(analysis.render_fraction(analysis.auroc([Fraction(2), Fraction(2)], [Fraction(2), Fraction(2)])), "0.5")
        self.assertEqual(analysis.render_fraction(analysis.auroc([Fraction(1), Fraction(1)], [Fraction(2), Fraction(3)])), "0")
        all_zero = analysis.signed_rank_test([Fraction(0), Fraction(0)])
        self.assertEqual(all_zero["statistic"], "0")
        self.assertEqual(all_zero["p_value"], 1.0)
        self.assertEqual(all_zero["disposition"], "all_zero_differences")
        self.assertEqual(all_zero["zero_count"], 2)
        self.assertEqual(all_zero["nonzero_count"], 0)
        tied = analysis.signed_rank_test([Fraction(1), Fraction(1)])
        tied_ranks = [Fraction(3, 2), Fraction(3, 2)]
        tied_variance = sum(rank * rank for rank in tied_ranks) / 4
        self.assertEqual(tied["statistic"], "3")
        self.assertEqual(tied["variance"], analysis.render_fraction(tied_variance))
        self.assertEqual(tied["zero_method"], "wilcox")
        self.assertFalse(tied["continuity_correction"])
        tied_z = (3 - 1.5) / math.sqrt(float(tied_variance))
        self.assertAlmostEqual(tied["p_value"], math.erfc(abs(tied_z) / math.sqrt(2.0)))
        opposite = analysis.signed_rank_test([Fraction(0), Fraction(1), Fraction(-1)])
        self.assertEqual(opposite["statistic"], "1.5")
        self.assertEqual(opposite["p_value"], 1.0)
        self.assertEqual(opposite["zero_count"], 1)
        self.assertEqual(opposite["nonzero_count"], 2)
        self.assertEqual(opposite["disposition"], "wilcoxon_signed_rank")
        quartiles = analysis.quantile_type7([Fraction(1), Fraction(2), Fraction(3), Fraction(4)], Fraction(1, 4))
        self.assertEqual(quartiles, Fraction(7, 4))

    def test_cluster_multiplicity_and_bootstrap_accounting(self):
        population = ["c1", "c0"]
        first = analysis.resampled_cluster_ids(population, 0)
        self.assertEqual(first, analysis.resampled_cluster_ids(["c0", "c1"], 0))
        self.assertEqual(len(first), 2)
        repeated = None
        for replicate in range(100):
            drawn = analysis.resampled_cluster_ids(population, replicate)
            if drawn[0] == drawn[1]:
                repeated = drawn
                break
        self.assertIsNotNone(repeated)
        expanded = analysis.expand_cluster_members({"c0": ["pair-c0"], "c1": ["pair-c1"]}, repeated)
        self.assertEqual(expanded, ["pair-" + repeated[0], "pair-" + repeated[0]])
        secret = synthetic_secret("bootstrap")
        parents = parents_for(2, 2, length=20)
        inventory = [uniform.core_digest(parent["sequence"]) for parent in parents]
        prepared = blinding.prepare_section6_upload(parents, inventory, secret)
        assignments = {
            (row["parent_core_id"], row["class_label"]): (
                "0.7" if row["class_label"] == "eval_core" else "0.3",
                "pass",
            )
            for row in prepared["private_key"]["candidates"]
        }
        export, failures = export_bytes(prepared["private_key"], prepared["candidate_upload"], assignments, set())
        sparse = analysis.summarize_section6(
            prepared["candidate_upload"],
            prepared["private_key"],
            export,
            failures=failures,
            raw_artifacts=[],
        )
        repeated_report = analysis.summarize_section6(
            prepared["candidate_upload"],
            prepared["private_key"],
            shuffled_export(export),
            failures=failures,
            raw_artifacts=[],
        )
        self.assertEqual(scientific_view(sparse), scientific_view(repeated_report))
        self.assertEqual(sparse["analyzed_bytes"]["candidate_upload"], byte_record(prepared["candidate_upload"]))
        self.assertEqual(sparse["analyzed_bytes"]["downloaded_export"], byte_record(export))
        self.assertEqual(repeated_report["analyzed_bytes"]["downloaded_export"], byte_record(shuffled_export(export)))
        median_interval = sparse["bootstrap"]["paired_median_difference"]
        self.assertEqual(median_interval["point"], "0.4")
        self.assertIsNone(median_interval["interval"])
        self.assertEqual(median_interval["technical_incompleteness"], analysis.INCOMPLETENESS_REPLICATES)
        self.assertEqual(
            median_interval["defined_replicates"] + median_interval["undefined_replicates"],
            10000,
        )
        self.assertGreater(median_interval["undefined_replicates"], 0)
        self.assertLess(median_interval["defined_replicates"], 9500)
        self.assertEqual(median_interval["imputed_replicates"], 0)
        wide_parents = parents_for(20, 20, length=20)
        wide_inventory = [uniform.core_digest(parent["sequence"]) for parent in wide_parents]
        wide = blinding.prepare_section6_upload(wide_parents, wide_inventory, secret)
        wide_assignments = {
            (row["parent_core_id"], row["class_label"]): (
                "0.8" if row["class_label"] == "eval_core" else "0.2",
                "pass" if row["class_label"] == "eval_core" else "fail",
            )
            for row in wide["private_key"]["candidates"]
        }
        wide_export, wide_failures = export_bytes(wide["private_key"], wide["candidate_upload"], wide_assignments, set())
        first_wide = analysis.summarize_section6(
            wide["candidate_upload"],
            wide["private_key"],
            wide_export,
            failures=wide_failures,
            raw_artifacts=[],
        )
        second_wide = analysis.summarize_section6(
            wide["candidate_upload"],
            wide["private_key"],
            shuffled_export(wide_export),
            failures=wide_failures,
            raw_artifacts=[],
        )
        self.assertEqual(scientific_view(first_wide), scientific_view(second_wide))
        self.assertEqual(first_wide["analyzed_bytes"]["downloaded_export"], byte_record(wide_export))
        self.assertEqual(second_wide["analyzed_bytes"]["downloaded_export"], byte_record(shuffled_export(wide_export)))
        self.assertNotEqual(
            first_wide["analyzed_bytes"]["downloaded_export"]["sha256"],
            second_wide["analyzed_bytes"]["downloaded_export"]["sha256"],
        )
        interval = first_wide["bootstrap"]["paired_median_difference"]["interval"]
        self.assertEqual(interval["low"], "0.6")
        self.assertEqual(interval["high"], "0.6")
        self.assertGreaterEqual(first_wide["bootstrap"]["auroc"]["defined_replicates"], 9500)
        self.assertEqual(
            first_wide["bootstrap"]["auroc"]["defined_replicates"]
            + first_wide["bootstrap"]["auroc"]["undefined_replicates"],
            10000,
        )
        self.assertEqual(first_wide["bootstrap"]["auroc"]["imputed_replicates"], 0)
        self.assertIsNone(first_wide["bootstrap"]["auroc"]["technical_incompleteness"])

    def test_local_recomputation_and_production_runner_are_refused(self):
        with self.assertRaises(uniform.Section6Error) as caught:
            analysis.refuse_local_recomputation("composite_aptamer_likeness")
        self.assertEqual(caught.exception.code, "local_recompute_refused")
        for name in ("normalized_mfe", "ensemble_defect", "positional_entropy", "stem_fraction", "gc_fraction", "shuffle_p_value"):
            with self.assertRaises(uniform.Section6Error):
                analysis.refuse_local_recomputation(name)
        buffer = StringIO()
        with redirect_stdout(buffer):
            self.assertEqual(blinding.main([]), 0)
        self.assertIn("SECTION6_METHOD_FROZEN_SYNTHETIC_ONLY_PRODUCTION_UNAUTHORIZED", buffer.getvalue())
        with self.assertRaises(uniform.Section6Error) as caught:
            blinding.main(["results/not-a-run"])
        self.assertEqual(caught.exception.code, "production_runner_refused")
        with self.assertRaises(uniform.Section6Error) as caught:
            blinding.prepare_section6_upload("/tmp/parents.json", [], synthetic_secret("path"))
        self.assertEqual(caught.exception.code, "filesystem_path_refused")
        for name in ("aptarank_section6_analysis.py", "aptarank_section6_uniform.py", "aptarank_section6_blinding.py"):
            with open(os.path.join(MODELLING, name), encoding="utf-8") as handle:
                self.assertNotIn("scipy", handle.read().lower())

    def test_tied_rank_variance_matches_sum_of_squared_ranks(self):
        differences = [Fraction(1), Fraction(-1), Fraction(2), Fraction(-4), Fraction(4), Fraction(4)]
        ranks = [Fraction(3, 2), Fraction(3, 2), Fraction(3), Fraction(5), Fraction(5), Fraction(5)]
        expected = sum(rank * rank for rank in ranks) / 4
        result = analysis.signed_rank_test(differences)
        self.assertEqual(result["variance"], analysis.render_fraction(expected))
        self.assertEqual(result["variance_formula"], "n(n+1)(2n+1)/24 - sum(t^3-t)/48")
        untied_ranks = [Fraction(1), Fraction(2), Fraction(3)]
        untied = analysis.signed_rank_test([Fraction(1), Fraction(-2), Fraction(3)])
        self.assertEqual(
            untied["variance"],
            analysis.render_fraction(sum(rank * rank for rank in untied_ranks) / 4),
        )

    def test_missing_parent_digest_is_refused(self):
        parents = parents_for(2, 2, length=8)
        inventory = [uniform.core_digest(parents[0]["sequence"])]
        with self.assertRaises(uniform.Section6Error) as caught:
            uniform.generate_uniform_controls(parents, inventory)
        self.assertEqual(caught.exception.code, "missing_parent_digest")
        self.assertNotIn(parents[1]["sequence"], caught.exception.detail)

    def test_aptamer_likeness_closed_interval(self):
        secret = synthetic_secret("interval")
        parents = parents_for(2, 2, length=20)
        inventory = [uniform.core_digest(parent["sequence"]) for parent in parents]
        prepared = blinding.prepare_section6_upload(parents, inventory, secret)

        def assignments(low, high):
            mapped = {}
            for row in prepared["private_key"]["candidates"]:
                score = high if row["class_label"] == "eval_core" else low
                mapped[(row["parent_core_id"], row["class_label"])] = (score, "pass")
            return mapped

        for low, high in (("0", "1"), ("0.0", "1.0")):
            export, failures = export_bytes(
                prepared["private_key"],
                prepared["candidate_upload"],
                assignments(low, high),
                set(),
            )
            summary = analysis.summarize_section6(
                prepared["candidate_upload"],
                prepared["private_key"],
                export,
                failures=failures,
                raw_artifacts=[],
            )
            self.assertEqual(summary["denominators"]["evaluable_scores"], 4)
        export, failures = export_bytes(
            prepared["private_key"],
            prepared["candidate_upload"],
            assignments("0.5", "0.5"),
            set(),
        )
        for token in ("-0.1", "1.1", "-1", "2"):
            mutated = export.replace(b",0.5,", ("," + token + ",").encode("ascii"), 1)
            with self.assertRaises(uniform.Section6Error) as caught:
                analysis.summarize_section6(
                    prepared["candidate_upload"],
                    prepared["private_key"],
                    mutated,
                    failures=failures,
                    raw_artifacts=[],
                )
            self.assertEqual(caught.exception.code, "aptamer_likeness_out_of_range")
            self.assertTrue(caught.exception.rerun_lineage_required)

    def test_private_key_ingestion_fails_closed(self):
        secret = synthetic_secret("private-key")
        parents = parents_for(2, 2, length=12)
        inventory = [uniform.core_digest(parent["sequence"]) for parent in parents]
        prepared = blinding.prepare_section6_upload(parents, inventory, secret)
        self.assertEqual(
            analysis.validate_private_key(prepared["private_key_bytes"]),
            prepared["private_key"]["candidates"],
        )

        def clone():
            return json.loads(json.dumps(prepared["private_key"]))

        def expect(document, code):
            with self.assertRaises(uniform.Section6Error) as caught:
                analysis.validate_private_key(document)
            self.assertEqual(caught.exception.code, code)

        bad = clone()
        bad["package_id"] = "OTHER"
        expect(bad, "private_key_invalid")
        bad = clone()
        bad["schema_version"] = "other-schema"
        expect(bad, "private_key_invalid")
        bad = clone()
        bad["restricted"] = False
        expect(bad, "private_key_invalid")
        bad = clone()
        del bad["restricted"]
        expect(bad, "private_key_invalid")
        bad = clone()
        bad["candidates"][0]["candidate_id"] = "cand_" + "G" * 32
        expect(bad, "private_key_invalid")
        bad = clone()
        bad["candidates"][0]["source_digest"] = "A" * 64
        expect(bad, "private_key_invalid")
        bad = clone()
        bad["candidates"][1]["candidate_id"] = bad["candidates"][0]["candidate_id"]
        expect(bad, "duplicate_candidate_id")
        bad = clone()
        bad["candidates"][1]["source_digest"] = bad["candidates"][0]["source_digest"]
        expect(bad, "duplicate_source_digest")
        bad = clone()
        first = bad["candidates"][0]
        mate = next(
            row
            for row in bad["candidates"]
            if row["pair_id"] == first["pair_id"] and row["candidate_id"] != first["candidate_id"]
        )
        mate["class_label"] = first["class_label"]
        expect(bad, "pair_conflict")
        bad = clone()
        first = bad["candidates"][0]
        mate = next(
            row
            for row in bad["candidates"]
            if row["pair_id"] == first["pair_id"] and row["candidate_id"] != first["candidate_id"]
        )
        mate["parent_core_id"] = "other-parent"
        expect(bad, "pair_conflict")
        bad = clone()
        first = bad["candidates"][0]
        mate = next(
            row
            for row in bad["candidates"]
            if row["pair_id"] == first["pair_id"] and row["candidate_id"] != first["candidate_id"]
        )
        mate["cluster_id"] = "other-cluster"
        expect(bad, "pair_conflict")
        bad = clone()
        first = bad["candidates"][0]
        mate = next(
            row
            for row in bad["candidates"]
            if row["pair_id"] == first["pair_id"] and row["candidate_id"] != first["candidate_id"]
        )
        mate["length"] = first["length"] + 1
        expect(bad, "pair_conflict")

    def test_export_ranks_ignore_physical_order(self):
        secret = synthetic_secret("ranks")
        parents = parents_for(2, 2, length=16)
        inventory = [uniform.core_digest(parent["sequence"]) for parent in parents]
        prepared = blinding.prepare_section6_upload(parents, inventory, secret)
        upload_sequences = {}
        for line in prepared["candidate_upload"].decode("utf-8").splitlines()[1:]:
            identifier, sequence = line.split(",")
            upload_sequences[identifier] = sequence
        candidates = prepared["private_key"]["candidates"]
        ordered_ids = sorted(row["candidate_id"] for row in candidates)
        tied = sorted(ordered_ids[1:3])
        score_by_id = {
            ordered_ids[0]: "0.9",
            ordered_ids[1]: "0.4",
            ordered_ids[2]: "0.4",
            ordered_ids[3]: "0.1",
        }
        rank_by_id = {ordered_ids[0]: 1, tied[0]: 2, tied[1]: 3, ordered_ids[3]: 4}

        def rows_for(rank_map, omitted=()):
            built = []
            for row in candidates:
                candidate_id = row["candidate_id"]
                if candidate_id in omitted:
                    continue
                built.append(
                    {
                        "rank": rank_map[candidate_id],
                        "candidate": candidate_id,
                        "score": score_by_id[candidate_id],
                        "shuffle": "pass",
                        "length": row["length"],
                        "sequence": upload_sequences[candidate_id],
                    }
                )
            return built

        def summarize(export, failures):
            return analysis.summarize_section6(
                prepared["candidate_upload"],
                prepared["private_key"],
                export,
                failures=failures,
                raw_artifacts=[],
            )

        forward_export = render_export(rows_for(rank_by_id))
        backward_export = render_export(list(reversed(rows_for(rank_by_id))))
        forward = summarize(forward_export, [])
        backward = summarize(backward_export, [])
        self.assertEqual(scientific_view(forward), scientific_view(backward))
        self.assertEqual(forward["analyzed_bytes"]["candidate_upload"], byte_record(prepared["candidate_upload"]))
        self.assertEqual(forward["analyzed_bytes"]["downloaded_export"], byte_record(forward_export))
        self.assertEqual(backward["analyzed_bytes"]["downloaded_export"], byte_record(backward_export))
        self.assertNotEqual(
            forward["analyzed_bytes"]["downloaded_export"]["sha256"],
            backward["analyzed_bytes"]["downloaded_export"]["sha256"],
        )
        gapped_numbers = dict(rank_by_id)
        gapped_numbers[ordered_ids[3]] = 5
        with self.assertRaises(uniform.Section6Error) as caught:
            summarize(render_export(rows_for(gapped_numbers)), [])
        self.assertEqual(caught.exception.code, "rank_sequence_invalid")
        swapped = dict(rank_by_id)
        swapped[ordered_ids[0]] = rank_by_id[ordered_ids[3]]
        swapped[ordered_ids[3]] = rank_by_id[ordered_ids[0]]
        with self.assertRaises(uniform.Section6Error) as caught:
            summarize(render_export(rows_for(swapped)), [])
        self.assertEqual(caught.exception.code, "rank_order_invalid")
        wrong_tie = dict(rank_by_id)
        wrong_tie[tied[0]] = rank_by_id[tied[1]]
        wrong_tie[tied[1]] = rank_by_id[tied[0]]
        with self.assertRaises(uniform.Section6Error) as caught:
            summarize(render_export(rows_for(wrong_tie)), [])
        self.assertEqual(caught.exception.code, "rank_order_invalid")
        omitted = tied[0]
        failures = [{"candidate_id": omitted, "reason": "synthetic technical failure"}]
        retained = summarize(render_export(rows_for(rank_by_id, omitted=(omitted,))), failures)
        self.assertEqual(retained["denominators"]["technical_failures"], 1)
        loose = {ordered_ids[0]: 2, tied[1]: 4, ordered_ids[3]: 7}
        loose_summary = summarize(render_export(rows_for(loose, omitted=(omitted,))), failures)
        self.assertEqual(loose_summary["denominators"]["technical_failures"], 1)
        bad_gap = {ordered_ids[0]: 4, tied[1]: 3, ordered_ids[3]: 1}
        with self.assertRaises(uniform.Section6Error) as caught:
            summarize(render_export(rows_for(bad_gap, omitted=(omitted,))), failures)
        self.assertEqual(caught.exception.code, "rank_order_invalid")

    def test_raw_artifacts_are_hashed_and_components_are_not_recomputed(self):
        secret = synthetic_secret("artifacts")
        parents = parents_for(2, 2, length=12)
        inventory = [uniform.core_digest(parent["sequence"]) for parent in parents]
        prepared = blinding.prepare_section6_upload(parents, inventory, secret)
        assignments = {
            (row["parent_core_id"], row["class_label"]): ("0.5", "pass")
            for row in prepared["private_key"]["candidates"]
        }
        export, failures = export_bytes(prepared["private_key"], prepared["candidate_upload"], assignments, set())
        log_bytes = b"synthetic-ui-log"
        partial = json.dumps(
            {
                "scorer": "deployed AptaRank UI",
                "artifact_role": "aptarank_five_component_export",
                "rows": [
                    {
                        "candidate_id": prepared["private_key"]["candidates"][0]["candidate_id"],
                        "sequence": "ACGUACGUACGU",
                        "normalized_mfe": "0.1",
                    }
                ],
            }
        ).encode("utf-8")
        summary = analysis.summarize_section6(
            prepared["candidate_upload"],
            prepared["private_key"],
            export,
            failures=failures,
            raw_artifacts=[
                {"role": "ui_log", "available": True, "payload": log_bytes},
                {"role": "component_export", "available": True, "payload": partial},
                {"role": "pdf", "available": False},
            ],
        )
        captured = {row["role"]: row for row in summary["raw_run_artifacts"]["captured"]}
        self.assertEqual(set(captured), {"component_export", "ui_log"})
        self.assertEqual(captured["ui_log"]["sha256"], hashlib.sha256(log_bytes).hexdigest())
        self.assertEqual(captured["component_export"]["sha256"], hashlib.sha256(partial).hexdigest())
        self.assertEqual(captured["ui_log"]["byte_count"], len(log_bytes))
        self.assertEqual(summary["raw_run_artifacts"]["unavailable"], [{"role": "pdf", "reason": "unavailable"}])
        self.assertEqual(summary["raw_run_artifacts"]["captured_count"], 2)
        self.assertEqual(summary["raw_run_artifacts"]["unavailable_count"], 1)
        self.assertEqual(summary["analyzed_bytes"]["candidate_upload"], byte_record(prepared["candidate_upload"]))
        self.assertEqual(summary["analyzed_bytes"]["downloaded_export"], byte_record(export))
        table = summary["five_component_table"]
        self.assertEqual(table["status"], "unavailable")
        self.assertNotEqual(table["status"], analysis.POPULATED_COMPONENT_STATUS)
        self.assertEqual(table["verification"], "unverified")
        self.assertEqual(table["reason"], "unverified_component_artifact")
        self.assertFalse(table["schema_observed"])
        self.assertFalse(table["schema_frozen"])
        self.assertIsNone(table["rows"])
        self.assertFalse(table["recomputed"])
        self.assertEqual(table["local_recomputation"], "not_attempted")
        self.assertEqual(
            table["inspected"],
            [
                {
                    "role": "component_export",
                    "sha256": hashlib.sha256(partial).hexdigest(),
                    "verification": "unverified",
                    "defects": ["self_declared_schema", "incomplete_component_row", "schema_not_observed"],
                }
            ],
        )
        self.assertNotIn("ACGUACGUACGU", json.dumps(summary))
        empty = analysis.five_component_table([])
        self.assertEqual(empty["status"], "unavailable")
        self.assertEqual(empty["reason"], "component_artifact_unavailable")
        self.assertEqual(empty["verification"], "not_presented")
        self.assertFalse(empty["recomputed"])
        self.assertIsNone(empty["rows"])
        with self.assertRaises(uniform.Section6Error) as caught:
            analysis.capture_raw_artifacts("/tmp/section6-artifacts.json")
        self.assertEqual(caught.exception.code, "filesystem_path_refused")

    def test_empty_optional_artifacts_still_record_upload_and_export_hashes(self):
        secret = synthetic_secret("empty-artifacts")
        parents = parents_for(2, 2, length=12)
        inventory = [uniform.core_digest(parent["sequence"]) for parent in parents]
        prepared = blinding.prepare_section6_upload(parents, inventory, secret)
        assignments = {
            (row["parent_core_id"], row["class_label"]): ("0.5", "pass")
            for row in prepared["private_key"]["candidates"]
        }
        upload = prepared["candidate_upload"]
        export, failures = export_bytes(prepared["private_key"], upload, assignments, set())
        summary = analysis.summarize_section6(
            upload,
            prepared["private_key"],
            export,
            failures=failures,
            raw_artifacts=[],
        )
        self.assertEqual(summary["raw_run_artifacts"]["captured"], [])
        self.assertEqual(summary["raw_run_artifacts"]["unavailable"], [])
        self.assertEqual(summary["raw_run_artifacts"]["captured_count"], 0)
        self.assertEqual(summary["raw_run_artifacts"]["unavailable_count"], 0)
        self.assertNotIn("candidate_upload", summary["raw_run_artifacts"])
        self.assertNotIn("downloaded_export", summary["raw_run_artifacts"])
        self.assertEqual(summary["analyzed_bytes"]["candidate_upload"], byte_record(upload))
        self.assertEqual(summary["analyzed_bytes"]["downloaded_export"], byte_record(export))
        self.assertEqual(summary["analyzed_bytes"]["candidate_upload"]["byte_count"], len(upload))
        self.assertEqual(summary["analyzed_bytes"]["downloaded_export"]["byte_count"], len(export))
        self.assertNotEqual(
            summary["analyzed_bytes"]["candidate_upload"]["sha256"],
            hashlib.sha256(upload + b"\n").hexdigest(),
        )
        self.assertNotEqual(
            summary["analyzed_bytes"]["downloaded_export"]["sha256"],
            hashlib.sha256(export[:-1]).hexdigest(),
        )

    def test_unverified_component_rows_cannot_populate_the_production_table(self):
        secret = synthetic_secret("component-rows")
        parents = parents_for(2, 2, length=12)
        inventory = [uniform.core_digest(parent["sequence"]) for parent in parents]
        prepared = blinding.prepare_section6_upload(parents, inventory, secret)
        assignments = {
            (row["parent_core_id"], row["class_label"]): ("0.5", "pass")
            for row in prepared["private_key"]["candidates"]
        }
        upload = prepared["candidate_upload"]
        export, failures = export_bytes(prepared["private_key"], upload, assignments, set())
        known_ids = [row["candidate_id"] for row in prepared["private_key"]["candidates"]]
        foreign_id = "cand_" + ("ab" * 16)
        self.assertNotIn(foreign_id, known_ids)

        def component_row(candidate_id):
            return {
                "candidate_id": candidate_id,
                "sequence": "ACGUACGUACGU",
                "normalized_mfe": "0.125",
                "ensemble_defect": "0.25",
                "positional_entropy": "0.5",
                "stem_fraction": "0.75",
                "gc_fraction": "0.875",
            }

        def component_bytes(rows):
            return json.dumps(
                {
                    "scorer": "deployed AptaRank UI",
                    "artifact_role": "aptarank_five_component_export",
                    "rows": rows,
                }
            ).encode("utf-8")

        duplicate = component_bytes([component_row(known_ids[0]), component_row(known_ids[0])])
        unexpected = component_bytes([component_row(foreign_id)])
        incomplete_row = component_row(known_ids[0])
        del incomplete_row["gc_fraction"]
        incomplete = component_bytes([incomplete_row])
        self_declared = component_bytes([component_row(candidate_id) for candidate_id in known_ids])
        cases = (
            ("duplicate_candidate_id", duplicate),
            ("unexpected_candidate_id", unexpected),
            ("incomplete_component_row", incomplete),
            ("self_declared_schema", self_declared),
        )
        for defect, payload in cases:
            summary = analysis.summarize_section6(
                upload,
                prepared["private_key"],
                export,
                failures=failures,
                raw_artifacts=[{"role": "components", "available": True, "payload": payload}],
            )
            table = summary["five_component_table"]
            self.assertNotEqual(table["status"], "populated_from_verified_artifact", defect)
            self.assertEqual(table["status"], "unavailable", defect)
            self.assertEqual(table["verification"], "unverified", defect)
            self.assertEqual(table["reason"], "unverified_component_artifact", defect)
            self.assertFalse(table["schema_observed"], defect)
            self.assertFalse(table["schema_frozen"], defect)
            self.assertIsNone(table["rows"], defect)
            self.assertIsNone(table["source_role"], defect)
            self.assertIsNone(table["source_sha256"], defect)
            self.assertFalse(table["recomputed"], defect)
            self.assertEqual(table["local_recomputation"], "not_attempted", defect)
            self.assertEqual(table["inspected"][0]["verification"], "unverified", defect)
            self.assertIn(defect, table["inspected"][0]["defects"], defect)
            self.assertIn("schema_not_observed", table["inspected"][0]["defects"], defect)
            self.assertNotIn("0.125", json.dumps(table), defect)
            self.assertNotIn("ACGUACGUACGU", json.dumps(summary), defect)
            self.assertEqual(summary["analyzed_bytes"]["candidate_upload"], byte_record(upload), defect)
            self.assertEqual(summary["analyzed_bytes"]["downloaded_export"], byte_record(export), defect)
        paired = analysis.five_component_table(
            [
                ("one", hashlib.sha256(self_declared).hexdigest(), self_declared),
                ("two", hashlib.sha256(self_declared).hexdigest(), self_declared),
            ],
            analyzed_candidate_ids=set(known_ids),
        )
        self.assertEqual(paired["status"], "unavailable")
        self.assertNotEqual(paired["status"], "populated_from_verified_artifact")
        self.assertEqual(len(paired["inspected"]), 2)
        self.assertTrue(all(item["verification"] == "unverified" for item in paired["inspected"]))
        self.assertIsNone(paired["rows"])


if __name__ == "__main__":
    unittest.main()
