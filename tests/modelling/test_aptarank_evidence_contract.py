"""Synthetic checks for the frozen M9B-1 AptaRank evidence contract.

No TRAIN, VALIDATION, REF, EVAL, production ledger, model, or checkpoint is
opened. The camera-ready sample is not reread here; its recorded hashes are
pins, not scientific outcomes.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import os
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTRACT_SHA256 = "0494ea740b1a2402032bfa695c23a422b142cda6a2bc043d1da87dbb9ddb092b"
PLAN_SHA256 = "b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe"
PAPER_SHA256 = "aaf40af707acc236639dccb8ecbf1f3fb522143f0a447e71f490168896af433d"
CSV_SHA256 = "447ce90b4fdf8fab7bbd5a4fcda1824fc91d3b7b697c6cfc7fbe466e16400852"
PNG_SHA256 = "ffbc22abfd874af242623536ce516f35a8eda17bbc4b52048c39cae63e5c1e63"
INSPECTED_COMMIT = "bd934ca54a6649eb8cf241f56a95d5903c873d91"
COMPARISON_COMMIT = "49a85609e3529adace60d3267ee88550159bba29"


def _load(filename):
    path = os.path.join(ROOT, "scripts", "modelling", filename)
    spec = importlib.util.spec_from_file_location(filename[: -len(".py")], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = _load("aptarank_evidence_contract.py")
arp1 = _load("aptarank_io_preflight.py")


class EvidenceContractTests(unittest.TestCase):
    def test_contract_identity_plan_digest_and_evidence_pins(self):
        document, payload = contract.load_contract()
        self.assertEqual(hashlib.sha256(payload).hexdigest(), CONTRACT_SHA256)
        with open(contract.contract_path(), "rb") as handle:
            self.assertEqual(hashlib.sha256(handle.read()).hexdigest(), CONTRACT_SHA256)
        self.assertEqual(document["status"], contract.STATUS)
        self.assertEqual(document["governing_plan"]["path"], contract.PLAN_RELATIVE)
        self.assertEqual(document["governing_plan"]["sha256"], PLAN_SHA256)
        with open(os.path.join(ROOT, contract.PLAN_RELATIVE), "rb") as handle:
            self.assertEqual(hashlib.sha256(handle.read()).hexdigest(), PLAN_SHA256)
        evidence = {item["filename"]: item for item in document["external_evidence"]}
        self.assertEqual(evidence["aptarank_paper.pdf"]["sha256"], PAPER_SHA256)
        self.assertEqual(evidence["aptarank_paper.pdf"]["bytes"], 1254624)
        self.assertEqual(evidence["example_shortlist.csv"]["sha256"], CSV_SHA256)
        self.assertEqual(evidence["example_shortlist.csv"]["bytes"], 280)
        self.assertEqual(evidence["example_results_screenshot.png"]["sha256"], PNG_SHA256)
        self.assertEqual(evidence["example_results_screenshot.png"]["bytes"], 492122)
        for item in document["external_evidence"]:
            self.assertIs(item["adopt_as_mres_outcome"], False)
            self.assertIs(item["adopt_as_mres_target"], False)

    def test_public_code_is_separate_from_deployment_verification(self):
        document, _payload = contract.load_contract()
        repository = document["public_repository"]
        self.assertEqual(repository["url"], "https://github.com/alishahsvnd/AptaRank")
        self.assertEqual(repository["inspected_commit"], INSPECTED_COMMIT)
        self.assertEqual(repository["comparison_commit"], COMPARISON_COMMIT)
        self.assertIs(repository["comparison_commit_available"], True)
        self.assertIs(repository["implementation_code_changed"], False)
        self.assertIs(repository["is_live_deployment"], False)
        self.assertIs(document["public_commit_is_live_deployment"], False)
        self.assertIs(document["deployment_verified"], False)
        self.assertTrue(repository["retrieved_utc"].startswith("2026-10-12"))
        public_facts = [
            fact for fact in document["facts"] if "established_by_public_implementation" in fact["levels"]
        ]
        self.assertTrue(public_facts)
        for fact in public_facts:
            self.assertIs(fact["deployment_verified"], False)

    def test_no_ref_or_control_bank_identity_and_no_scientific_result(self):
        document, _payload = contract.load_contract()
        unresolved = document["unresolved_deployment_items"]
        for key in (
            "accepted_ref_count",
            "dropped_ref_count",
            "bank_id",
            "bank_sha256",
            "bank_realized_count",
        ):
            self.assertIsNone(unresolved[key])
        for item in unresolved["items"]:
            self.assertEqual(item["status"], "unresolved")
            self.assertIsNone(item["value"])
        bank = next(item for item in document["conditional_algorithms"] if item["id"] == "bank_allocation")
        self.assertIsNone(bank["realized_count"])
        self.assertIn("not_a_realized_bank_count", bank["configured_bank_size_default_label"])
        self.assertIs(bank["production_value_instantiated"], False)
        self.assertIs(document["scientific_result"], False)
        self.assertIs(document["camera_ready_sample_is_mres_protocol"], False)
        excluded = document["excluded_from_mres_protocol"]
        self.assertIs(excluded["paper_evaluation_outcomes"], True)
        self.assertIs(excluded["sample_target_choices"], True)
        self.assertIs(excluded["sample_scores_as_outcomes"], True)
        for fact in document["facts"]:
            self.assertIs(fact["scientific_result"], False)

    def test_no_overlap_or_leakage_workflow(self):
        document, _payload = contract.load_contract()
        self.assertIs(document["overlap_leakage_workflow"], False)
        self.assertIs(document["excluded_from_mres_protocol"]["overlap_or_leakage"], True)
        text = "\n".join(document["prohibited_m9b_actions"])
        self.assertIn("overlap", text)
        self.assertIn("leakage", text)
        self.assertIn("nearest-TRAIN", text)
        self.assertIn("REF", text)
        self.assertIn("EVAL", text)

    def test_evidence_levels_are_closed(self):
        document, _payload = contract.load_contract()
        self.assertEqual(tuple(document["evidence_levels"]), contract.EVIDENCE_LEVELS)
        seen = set()
        for fact in document["facts"]:
            self.assertTrue(set(fact["levels"]) <= set(contract.EVIDENCE_LEVELS))
            seen.update(fact["levels"])
        self.assertEqual(seen, set(contract.EVIDENCE_LEVELS))

    def test_schema_and_dependency_pins_fail_closed(self):
        document, _payload = contract.load_contract()
        mutations = []

        extra = copy.deepcopy(document)
        extra["unexpected"] = True
        mutations.append(extra)

        missing = copy.deepcopy(document)
        del missing["status"]
        mutations.append(missing)

        status = copy.deepcopy(document)
        status["status"] = "DEPLOYMENT_VERIFIED"
        mutations.append(status)

        verified = copy.deepcopy(document)
        verified["deployment_verified"] = True
        mutations.append(verified)

        scientific = copy.deepcopy(document)
        scientific["scientific_result"] = True
        mutations.append(scientific)

        overlap = copy.deepcopy(document)
        overlap["overlap_leakage_workflow"] = True
        mutations.append(overlap)

        live = copy.deepcopy(document)
        live["public_commit_is_live_deployment"] = True
        mutations.append(live)

        protocol = copy.deepcopy(document)
        protocol["camera_ready_sample_is_mres_protocol"] = True
        mutations.append(protocol)

        adopted = copy.deepcopy(document)
        adopted["arp1_adopts_public_normalization"] = True
        mutations.append(adopted)

        bank = copy.deepcopy(document)
        bank["unresolved_deployment_items"]["bank_id"] = "bank-production"
        mutations.append(bank)

        accepted = copy.deepcopy(document)
        accepted["unresolved_deployment_items"]["accepted_ref_count"] = 113
        mutations.append(accepted)

        level = copy.deepcopy(document)
        level["facts"][0]["levels"] = ["guessed"]
        mutations.append(level)

        resolved = copy.deepcopy(document)
        resolved["conflicts"][0]["resolved"] = True
        mutations.append(resolved)

        produced = copy.deepcopy(document)
        produced["conditional_algorithms"][0]["production_value_instantiated"] = True
        mutations.append(produced)

        plan = copy.deepcopy(document)
        plan["governing_plan"]["sha256"] = "0" * 64
        mutations.append(plan)

        for mutated in mutations:
            with self.assertRaises(contract.EvidenceContractError):
                contract.validate_document(mutated)

    def test_arp1_still_rejects_public_normalization(self):
        document, _payload = contract.load_contract()
        self.assertIs(document["arp1_adopts_public_normalization"], False)
        normalization = next(item for item in document["facts"] if item["id"] == "sequence_normalization")
        self.assertIn("established_by_public_implementation", normalization["levels"])
        self.assertIs(normalization["deployment_verified"], False)

        accepted = arp1.ErrorList()
        self.assertIs(arp1._check_sequence("ACGU", accepted, "row", "candidate"), True)
        self.assertEqual(accepted.items, [])

        thymine = arp1.ErrorList()
        self.assertIs(arp1._check_sequence("ACGT", thymine, "row", "candidate"), False)
        self.assertEqual(thymine.items[0]["code"], "sequence_alphabet")

        lowered = arp1.ErrorList()
        self.assertIs(arp1._check_sequence("acgu", lowered, "row", "candidate"), False)
        self.assertEqual(lowered.items[0]["code"], "sequence_alphabet")

        spec, _spec_bytes = arp1.load_spec()
        self.assertIn("does not apply the public implementation", spec["rules"]["sequence_alphabet"])
        self.assertIn("not adopted by ARP-1", spec["rules"]["sequence_alphabet"])
        self.assertIn("canonical uppercase", spec["rules"]["sequence_alphabet"])
        self.assertIn("Silent normalization is not relied upon", spec["rules"]["sequence_alphabet"])
        self.assertIn("deliberate stricter MRes input policy", spec["rules"]["sequence_alphabet"])
        self.assertIn("does not claim live-deployment verification", spec["rules"]["sequence_alphabet"])
        provenance = spec["rules"]["nullable_target_pdb_id"]
        self.assertIn("five reference columns are retained for provenance and auditability", provenance)
        self.assertIn("deliberate stricter MRes provenance policy", provenance)
        self.assertIn("technically requires only sequence", provenance)
        self.assertIn("does not claim live-deployment verification", provenance)
        self.assertIs(spec["deployment_verified"], False)
        self.assertIsNone(spec["synthetic_run_profiles"]["target_free_rigorous_style"]["preset_value"])
        self.assertEqual(
            spec["synthetic_run_profiles"]["target_free_rigorous_style"]["compatibility_allowed_tokens"],
            ["not evaluated"],
        )
        self.assertEqual(
            spec["synthetic_run_profiles"]["target_free_rigorous_style"]["shuffle_allowed_tokens"],
            ["pass", "fail"],
        )

    def test_tier1_records_public_algorithms_without_resolving_them(self):
        arp2 = _load("aptarank_tier1_analysis.py")
        spec, _spec_bytes = arp2.load_spec()
        self.assertIs(spec["deployment_verified"], False)
        self.assertIs(spec["provisional_camera_ready_formula_adopted"], False)
        self.assertIs(spec["scientific_result"], False)
        by_id = {item["id"]: item for item in spec["unresolved_register"]}
        self.assertEqual(by_id["U1"]["status"], "unresolved")
        self.assertIsNone(by_id["U1"]["value"])
        self.assertIn("one pooled empirical REF distribution per criterion", by_id["U1"]["note"])
        self.assertIn("does not choose or implement a competing short/long calibration", by_id["U1"]["note"])
        self.assertIn("Local recomputation of AptaRank calibration remains disabled", by_id["U1"]["note"])
        self.assertIn("M9C", by_id["U1"]["note"])
        self.assertNotIn("unchosen", by_id["U1"]["note"])
        for index in range(2, 22):
            item = by_id["U%d" % index]
            self.assertEqual(item["status"], "unresolved")
            self.assertIsNone(item["value"])
            self.assertIn("public implementation definition is established", item["note"])
            self.assertIn("unverified", item["note"])
            self.assertIn("Local scorer reimplementation remains disabled", item["note"])
        self.assertEqual(by_id["U2"]["status"], "unresolved")
        self.assertIsNone(by_id["U2"]["value"])
        self.assertIn("M9B evidence contract", by_id["U2"]["note"])
        self.assertIsNone(by_id["U14"]["value"])
        self.assertIn("unverified", by_id["U14"]["note"])
        self.assertIn("30", by_id["U14"]["note"])
        self.assertNotIn("dense", by_id["U28"]["note"])
        self.assertIn("deterministic consecutive 1-based ordinal position", by_id["U28"]["note"])
        self.assertIn("statistical minimum rank", by_id["U28"]["note"])
        self.assertIs(spec["scoring_boundary"]["local_recompute_empirical_ref_calibration"], False)

    def test_reclassified_items_stay_out_of_the_conflict_list(self):
        document, _payload = contract.load_contract()
        policies = {item["id"]: item for item in document["project_input_policies"]}
        self.assertEqual(
            list(policies),
            ["canonical_uppercase_acgu", "five_column_ref_provenance"],
        )
        for item in policies.values():
            self.assertEqual(item["classification"], "deliberate_stricter_mres_input_provenance_policy")
            self.assertIs(item["public_behavior_recorded"], True)
            self.assertIs(item["compatible_with_inspected_public_loader"], True)
            self.assertIs(item["deployment_verified"], False)
            self.assertIs(item["scientific_or_deployment_conflict"], False)
            self.assertIs(item["claims_live_deployment_verification"], False)
        self.assertIn("Silent normalization is not relied upon", policies["canonical_uppercase_acgu"]["statement"])
        self.assertIn("provenance and auditability", policies["five_column_ref_provenance"]["statement"])
        self.assertIn("requires only sequence", policies["five_column_ref_provenance"]["statement"])
        conflict_ids = [item["id"] for item in document["conflicts"]]
        self.assertEqual(conflict_ids, ["strong_band_equality", "quick_preset_sample_count"])
        for item in document["conflicts"]:
            self.assertIs(item["resolved"], False)
            self.assertIs(item["deployment_verified"], False)
        self.assertNotIn("normalization_versus_arp1", conflict_ids)
        self.assertNotIn("reference_column_enforcement", conflict_ids)
        self.assertNotIn("two_sided_clip", conflict_ids)
        detail = document["non_material_implementation_details"][0]
        self.assertEqual(detail["id"], "two_sided_clip")
        self.assertIs(detail["requires_m9c_resolution"], False)
        self.assertIs(detail["unresolved_conflict"], False)
        self.assertIn("already in [0, 1]", detail["statement"])
        unresolved_ids = [item["id"] for item in document["unresolved_deployment_items"]["items"]]
        for retained in (
            "live_deployment_identity",
            "effective_preset",
            "accepted_and_dropped_ref_counts",
            "bank_identity_and_count",
            "runtime",
            "live_export_behavior",
            "band_equality",
            "folding_tool_versions",
        ):
            self.assertIn(retained, unresolved_ids)
        self.assertNotIn("two_sided_clip", unresolved_ids)
        calibration = next(item for item in document["facts"] if item["id"] == "empirical_calibration")
        self.assertIn("one pooled empirical REF distribution per criterion", calibration["statement"])
        self.assertIn("does not choose or implement a competing short/long calibration", calibration["statement"])
        self.assertNotIn("unchosen", calibration["statement"])
        rank = next(item for item in document["facts"] if item["id"] == "rank_direction")
        self.assertIn("deterministic consecutive 1-based ordinal position", rank["statement"])
        self.assertIn("ascending candidate ID", rank["statement"])
        self.assertIn("statistical minimum rank", rank["statement"])
        self.assertNotIn("dense", rank["statement"])
        normalization = next(item for item in document["facts"] if item["id"] == "sequence_normalization")
        self.assertIn("strips whitespace, uppercases, and rewrites T as U", normalization["statement"])
        reference = next(item for item in document["facts"] if item["id"] == "reference_upload_fields")
        self.assertIn("required column is sequence only", reference["statement"])

        relabelled = copy.deepcopy(document)
        relabelled["project_input_policies"][0]["scientific_or_deployment_conflict"] = True
        with self.assertRaises(contract.EvidenceContractError):
            contract.validate_document(relabelled)


if __name__ == "__main__":
    unittest.main()
