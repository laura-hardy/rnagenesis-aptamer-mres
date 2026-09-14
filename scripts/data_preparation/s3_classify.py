#!/usr/bin/env python3
"""S3: per-source eligibility classification and CHECKPOINT-1 artefacts.

Consumes S2 normalised output, source-metadata, leakage exclusion set and target
aliases. Assigns provisional accept/park/reject decisions and stops before S4.
Does not perform target normalisation, UniProt mapping, evidence scoring,
affinity interpretation, deduplication, clustering, balancing or partitioning.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    LEAKAGE_MATCH_COLUMNS,
    LOCAL_DETAIL_COLUMNS,
    REASON_COUNT_COLUMNS,
    AptaBaseS3Error,
    AptaBaseS3Stats,
    assert_no_legacy_cleaner_import,
    build_local_detail_row,
    classify_aptabase_record,
    update_stats_from_row,
)
from adapters.aptadb_s2 import load_aptadb_policy  # noqa: E402
from adapters.aptadb_s3 import (  # noqa: E402
    DECISION_COLUMNS as APTADB_DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS as APTADB_LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS as APTADB_PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_NON_PROTEIN,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    REASON_COUNT_COLUMNS as APTADB_REASON_COUNT_COLUMNS,
    REJECTION_COLUMNS as APTADB_REJECTION_COLUMNS,
    AptaDBS3Error,
    AptaDBS3Stats,
    apply_random_accept_audit as apply_aptadb_random_accept_audit,
    assert_aptadb_accept_invariants,
    assert_aptadb_reject_park_invariants,
    build_local_detail_row as build_aptadb_local_detail_row,
    build_unlinked_rejection_row,
    classify_aptadb_record,
    index_constant_proposals,
    refresh_stats_after_audit as refresh_aptadb_stats_after_audit,
    update_stats_from_row as update_aptadb_stats_from_row,
)
from adapters.riboaptamer_s3 import (  # noqa: E402
    DECISION_COLUMNS as RIBOAPTAMER_DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS as RIBOAPTAMER_LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS as RIBOAPTAMER_PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE as RIBOAPTAMER_PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT as RIBOAPTAMER_PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA as RIBOAPTAMER_PRIMARY_ROUTE_SSDNA,
    REASON_COUNT_COLUMNS as RIBOAPTAMER_REASON_COUNT_COLUMNS,
    REASON_PRIORITY_RULE,
    REJECTION_COLUMNS as RIBOAPTAMER_REJECTION_COLUMNS,
    RiboAptamerS3Error,
    RiboAptamerS3Stats,
    apply_random_accept_audit as apply_riboaptamer_random_accept_audit,
    assert_riboaptamer_accept_invariants,
    assert_riboaptamer_reject_park_invariants,
    build_local_detail_row as build_riboaptamer_local_detail_row,
    classify_riboaptamer_record,
    index_constant_proposals as index_riboaptamer_constant_proposals,
    refresh_stats_after_audit as refresh_riboaptamer_stats_after_audit,
    update_stats_from_row as update_riboaptamer_stats_from_row,
)
from adapters.aptaindex_s3 import (  # noqa: E402
    DECISION_COLUMNS as APTAINDEX_DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS as APTAINDEX_LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS as APTAINDEX_PARK_COLUMNS,
    PRIMARY_ROUTE_CHEMISTRY_REVIEW as APTAINDEX_PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_ELIGIBLE as APTAINDEX_PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT as APTAINDEX_PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA as APTAINDEX_PRIMARY_ROUTE_SSDNA,
    REASON_COUNT_COLUMNS as APTAINDEX_REASON_COUNT_COLUMNS,
    REJECTION_COLUMNS as APTAINDEX_REJECTION_COLUMNS,
    AptaIndexS3Error,
    AptaIndexS3Stats,
    apply_random_accept_audit as apply_aptaindex_random_accept_audit,
    assert_aptaindex_accept_invariants,
    assert_aptaindex_reject_park_invariants,
    build_local_detail_row as build_aptaindex_local_detail_row,
    classify_aptaindex_record,
    count_multi_target_sequences,
    index_constant_proposals as index_aptaindex_constant_proposals,
    refresh_stats_after_audit as refresh_aptaindex_stats_after_audit,
    update_stats_from_row as update_aptaindex_stats_from_row,
)
from adapters.ena_s3 import (  # noqa: E402
    DECISION_COLUMNS as ENA_DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS as ENA_LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS as ENA_PARK_COLUMNS,
    PRIMARY_ROUTE_CONSTRUCT as ENA_PRIMARY_ROUTE_CONSTRUCT,
    PRIMARY_ROUTE_ELIGIBLE as ENA_PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT as ENA_PRIMARY_ROUTE_REJECT,
    REASON_COUNT_COLUMNS as ENA_REASON_COUNT_COLUMNS,
    REJECTION_COLUMNS as ENA_REJECTION_COLUMNS,
    EnaS3Error,
    EnaS3Stats,
    apply_duplicate_sequence_diagnostic,
    apply_random_accept_audit as apply_ena_random_accept_audit,
    assert_ena_accept_invariants,
    assert_ena_reject_park_invariants,
    build_local_detail_row as build_ena_local_detail_row,
    classify_ena_record,
    duplicate_sequence_full_ids,
    index_constant_proposals as index_ena_constant_proposals,
    refresh_stats_after_audit as refresh_ena_stats_after_audit,
    update_stats_from_row as update_ena_stats_from_row,
)
from adapters.aptamerbase_s3 import (  # noqa: E402
    DECISION_COLUMNS as APTAMERBASE_DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS as APTAMERBASE_LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS as APTAMERBASE_PARK_COLUMNS,
    PRIMARY_ROUTE_CHEMISTRY_REVIEW as APTAMERBASE_PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_CONSTRUCT as APTAMERBASE_PRIMARY_ROUTE_CONSTRUCT,
    PRIMARY_ROUTE_ELIGIBLE as APTAMERBASE_PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE as APTAMERBASE_PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT as APTAMERBASE_PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA as APTAMERBASE_PRIMARY_ROUTE_SSDNA,
    REASON_COUNT_COLUMNS as APTAMERBASE_REASON_COUNT_COLUMNS,
    REJECTION_COLUMNS as APTAMERBASE_REJECTION_COLUMNS,
    AptamerBaseS3Error,
    AptamerBaseS3Stats,
    apply_random_accept_audit as apply_aptamerbase_random_accept_audit,
    assert_aptamerbase_accept_invariants,
    assert_aptamerbase_reject_park_invariants,
    build_local_detail_row as build_aptamerbase_local_detail_row,
    classify_aptamerbase_record,
    index_constant_proposals as index_aptamerbase_constant_proposals,
    refresh_stats_after_audit as refresh_aptamerbase_stats_after_audit,
    update_stats_from_row as update_aptamerbase_stats_from_row,
)
from adapters.aptadiff_s3 import (  # noqa: E402
    DECISION_COLUMNS as APTADIFF_DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS as APTADIFF_LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS as APTADIFF_PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE as APTADIFF_PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT as APTADIFF_PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA as APTADIFF_PRIMARY_ROUTE_SSDNA,
    REASON_COUNT_COLUMNS as APTADIFF_REASON_COUNT_COLUMNS,
    REJECTION_COLUMNS as APTADIFF_REJECTION_COLUMNS,
    AptaDiffS3Error,
    AptaDiffS3Stats,
    apply_random_accept_audit as apply_aptadiff_random_accept_audit,
    assert_aptadiff_accept_invariants,
    assert_aptadiff_reject_park_invariants,
    build_local_detail_row as build_aptadiff_local_detail_row,
    classify_aptadiff_record,
    expected_documented_target as aptadiff_expected_documented_target,
    refresh_stats_after_audit as refresh_aptadiff_stats_after_audit,
    update_stats_from_row as update_aptadiff_stats_from_row,
)
from adapters.aptadiff import SOURCE_PROFILES as APTADIFF_SOURCE_PROFILES  # noqa: E402
from adapters.utexas_s3 import (  # noqa: E402
    DECISION_COLUMNS as UTEXAS_DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS as UTEXAS_LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS as UTEXAS_PARK_COLUMNS,
    REASON_COUNT_COLUMNS as UTEXAS_REASON_COUNT_COLUMNS,
    REJECTION_COLUMNS as UTEXAS_REJECTION_COLUMNS,
    UTexasS3Error,
    UTexasS3Stats,
    apply_random_accept_audit,
    assert_utexas_accept_invariants,
    assert_utexas_reject_park_invariants,
    build_local_detail_row as build_utexas_local_detail_row,
    classify_utexas_record,
    refresh_stats_after_audit,
    update_stats_from_row as update_utexas_stats_from_row,
)
from adapters.ncbi_nuc_s3 import (  # noqa: E402
    DECISION_COLUMNS as NCBI_NUC_DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS as NCBI_NUC_LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS as NCBI_NUC_PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE as NCBI_NUC_PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE as NCBI_NUC_PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT as NCBI_NUC_PRIMARY_ROUTE_REJECT,
    REASON_COUNT_COLUMNS as NCBI_NUC_REASON_COUNT_COLUMNS,
    REJECTION_COLUMNS as NCBI_NUC_REJECTION_COLUMNS,
    APPROVED_DNA_ACCESSIONS as NCBI_NUC_APPROVED_DNA,
    APPROVED_RNA_ACCESSIONS as NCBI_NUC_APPROVED_RNA,
    NcbiNucS3Error,
    NcbiNucS3Stats,
    apply_random_accept_audit as apply_ncbi_nuc_random_accept_audit,
    assert_ncbi_nuc_accept_invariants,
    assert_ncbi_nuc_reject_park_invariants,
    build_local_detail_row as build_ncbi_nuc_local_detail_row,
    classify_ncbi_nuc_record,
    index_constant_proposals as index_ncbi_nuc_constant_proposals,
    read_constant_proposals as read_ncbi_nuc_constant_proposals,
    refresh_stats_after_audit as refresh_ncbi_nuc_stats_after_audit,
    update_stats_from_row as update_ncbi_nuc_stats_from_row,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    CorpusSchemaError,
    validate_column_order,
    write_corpus_csv_atomic,
)
from common.eligibility import (  # noqa: E402
    EligibilityError,
    load_eligibility_policy,
    load_sequence_leakage_index,
    load_target_alias_rules,
    review_sort_key,
)
from s0_build_registry import find_repo_root  # noqa: E402

EXPECTED_APTADB_RAW_SHA256 = {
    "interaction.csv": (
        "6dbd97f20fa6f98d359d697713c43032d5a6a3c1a400d80ef28a150d676dff86"
    ),
    "aptamer.csv": (
        "9d3ab029d1de4408d2406051a68bc0e6da347ee1be1838aee9c938ca3f3fb464"
    ),
    "protein.csv": (
        "4de0d8b105b3318c9704ff64819089f5e17b5c735f0730724052f3e808325f79"
    ),
}
EXPECTED_APTABASE_ROWS = 610
EXPECTED_UTEXAS_ROWS = 1894
EXPECTED_APTADB_ROWS = 1350
EXPECTED_APTADB_UNLINKED = 37
EXPECTED_RIBOAPTAMER_ROWS = 509
EXPECTED_RIBOAPTAMER_SOURCE_DATASET = "riboaptamer_full_2026-08"
EXPECTED_RIBOAPTAMER_RAW_SHA256 = (
    "721d8c5ea81476c1f371ef8bfa814743f364eaf004c0a6eda2aabd6dc5d9a9fd"
)
EXPECTED_APTAINDEX_ROWS = 1050
EXPECTED_APTAINDEX_SOURCE_DATASET = "aptaindex_export_2026-07-22"
EXPECTED_APTAINDEX_RAW_SHA256 = (
    "912b8e554fa2bb2ed3a9e9bdf1cfbe4f757d8c7a00c401629e5bcb5e5c2877a8"
)
EXPECTED_APTAINDEX_S2_HASH = (
    "4a41c90c102d5dc5b9d9e469c6b636014d27c428868d1b3230b8fb2b1c4412da"
)
EXPECTED_ENA_ROWS = 679
EXPECTED_ENA_SOURCE_DATASET = "ena_selected_v2_2026-08"
EXPECTED_ENA_RAW_SHA256 = (
    "d1069b96c2bcf5eba02d7d7907b3bcc33e041bf80aac6345e7295715e45c5a35"
)
EXPECTED_ENA_S2_HASH = (
    "4e88f44a07cfee89014eae17d68b90f70acc23d6a6792f29c8ee8f622e2aa8ca"
)
EXPECTED_APTAMERBASE_ROWS = 2128
EXPECTED_APTAMERBASE_SOURCE_DATASET = "aptamerbase_export_2026-06-24"
EXPECTED_APTAMERBASE_RAW_CSV_SHA256 = (
    "40b329551b225a29ee2c656cf6b59b98ff686a981968b856685cdc7c222a784c"
)
EXPECTED_APTAMERBASE_RAW_RDF_SHA256 = (
    "3ab9340ee1fcb6a0910532a6e8d4cf5cc62579c3b21d85355c48d473e372006c"
)
EXPECTED_APTAMERBASE_S1_CANONICAL_SHA256 = (
    "0bb0282033ba0561b2c8d8de1358ae6e5a4e8fa47bfb640c56dc87b177552896"
)
EXPECTED_APTAMERBASE_S1_SIDECAR_SHA256 = (
    "47a49f7495648bb11105a77eee9cbcfeabeb7b7b05f357dc433d3edb779f41b7"
)
EXPECTED_APTAMERBASE_S2_HASH = (
    "69bcfb97592255bc0d70727991bd68d7bf5dc18f1c47db532b182461ba6d81f8"
)
EXPECTED_APTADIFF_A_ROWS = 13803
EXPECTED_APTADIFF_B_ROWS = 11547
EXPECTED_APTADIFF_A_SOURCE_DATASET = "aptadiff_a_igfbp3_p6_2026-06-22"
EXPECTED_APTADIFF_B_SOURCE_DATASET = "aptadiff_b_ptk7_p6_2026-06-22"
EXPECTED_APTADIFF_A_RAW_SHA256 = (
    "ec970c478aaba1aa089ecbaf7f5bc8aa7a11f6eacd0f7b3d3c418de6a27e8c77"
)
EXPECTED_APTADIFF_B_RAW_SHA256 = (
    "546de810e34035731502caf6476c73cc06feab8156ec8178efaade2d21bf4d72"
)
EXPECTED_APTADIFF_A_RAW_PATH = "data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv"
EXPECTED_APTADIFF_B_RAW_PATH = "data/raw/Aptadiff_otherdata/datasetB_PTK7_P6.csv"
EXPECTED_APTADIFF_A_S1_CANONICAL_SHA256 = (
    "22bd7357311ce5d9d0a000c20f75fc439942b16c37105a71509fb8329ee7b083"
)
EXPECTED_APTADIFF_A_S1_SIDECAR_SHA256 = (
    "ec0453c50205854dc1648c833a2f96a40b691ee39b8c49433d0024480c9314ea"
)
EXPECTED_APTADIFF_B_S1_CANONICAL_SHA256 = (
    "321ef00b4e7a78834f431b4335bf21e89752c8e596523480676f2d5ac2e50921"
)
EXPECTED_APTADIFF_B_S1_SIDECAR_SHA256 = (
    "3f7183e5999d2f729b1fd1d225287b3515414cec2d7b91e44de46cf84a5ec4a0"
)
EXPECTED_APTADIFF_A_S2_HASH = (
    "c88e6f12dea4d60377a1c5a7a95861fcc666e47be27920a234f828b70df6ca55"
)
EXPECTED_APTADIFF_B_S2_HASH = (
    "c40bc662f4c79fcc24c161c5a82e74c2d58f96fbb6ca74fbb84b105bf8bc98f6"
)
EXPECTED_APTADIFF_A_PARKED = 13802
EXPECTED_APTADIFF_A_REJECT = 1
EXPECTED_APTADIFF_B_PARKED = 11532
EXPECTED_APTADIFF_B_REJECT = 15
EXPECTED_APTADB_MOLECULE = {"RNA": 289, "ssDNA": 1061}
EXPECTED_UTEXAS_MISSING = 399
EXPECTED_UTEXAS_NONEMPTY = 1495
EXPECTED_UTEXAS_MOLECULE = {"RNA": 583, "ssDNA": 896, "DNA": 13, "unknown": 402}
EXPECTED_RAW_SHA256 = (
    "b5a66beb58d30c5c3d2f36a29ea2cc3678e7d4a6b1bb1a97efc1e166a49fd15c"
)

PIPELINE_STOP_STATEMENT = (
    "PIPELINE STOP: AptaBase CHECKPOINT-1 is awaiting manual review.\n"
    "No record is authorised to proceed to S4."
)
UTEXAS_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No record authorised for S4 yet."
)
APTADB_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No AptaDB record is authorised for S4 yet.\n"
    "The pipeline is stopped awaiting Laura CHECKPOINT-1 review."
)
RIBOAPTAMER_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No RiboAptamer record is authorised for S4 yet.\n"
    "The pipeline is stopped awaiting Laura CHECKPOINT-1 review."
)
APTAINDEX_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No AptaIndex record is authorised for S4 yet.\n"
    "The pipeline is stopped awaiting Laura CHECKPOINT-1 review."
)
ENA_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No ENA record is authorised for S4 yet.\n"
    "The pipeline is stopped awaiting Laura CHECKPOINT-1 review.\n"
    "Global S4 has not been run."
)
APTAMERBASE_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No AptamerBase record is authorised for S4 yet.\n"
    "The pipeline is stopped awaiting Laura CHECKPOINT-1 review.\n"
    "Global S4 has not been run."
)
APTADIFF_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No AptaDiff record is authorised for S4 yet.\n"
    "The pipeline is stopped awaiting Laura CHECKPOINT-1 review.\n"
    "Dataset-A replication remains deferred.\n"
    "Global S4 has not been run."
)
NCBI_NUC_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No NCBI Nucleotide record is authorised for S4 yet.\n"
    "The pipeline is stopped awaiting Laura CHECKPOINT-1 review.\n"
    "Global S4 has not been run."
)
EXPECTED_NCBI_NUC_ROWS = 18
EXPECTED_NCBI_NUC_SOURCE_DATASET = "ncbi_nuc_genbank_2026-07-27"
EXPECTED_NCBI_NUC_MOLECULE = {"RNA": 5, "DNA": 1, "unknown": 12}
EXPECTED_NCBI_NUC_S1_CANONICAL_SHA256 = (
    "329f518e94e0813080545fe61d823ad44607ec8a193e14498fc62a91d647e9dc"
)
EXPECTED_NCBI_NUC_S1_SIDECAR_SHA256 = (
    "f1d003f64e7a9619d94b7025838e229b4ec7655fa93f9bda2bf34e2ba0021fe1"
)
EXPECTED_NCBI_NUC_S2_HASH = (
    "965cd5a88426c40f54b43afb9fbe7fdb9688c16ff53fad3ef8858ee9ef86824c"
)
EXPECTED_NCBI_NUC_S2_QC_SHA256 = (
    "6639c15db9752370f3bd65702d8740776d50e0082aa9724181fdea7aa6729342"
)
EXPECTED_NCBI_NUC_RAW_SHA256: dict[str, str] = {
    "data/raw/NCBI_nucleotide/sequence (1).gb": (
        "0cfcbb085f86501c541bdf5eb5a3b7344d0554319db3f2e0a97509e28cb5c05a"
    ),
    "data/raw/NCBI_nucleotide/sequence (10).gb": (
        "d47bb0d8ab74f202ff3b4a336ac49abc8a0e29d9cde67b710896b0234acbab3f"
    ),
    "data/raw/NCBI_nucleotide/sequence (11).gb": (
        "950b13e83474ad066360bacd4a4d2ef1c7e8f4219259d50079a862c6771ce080"
    ),
    "data/raw/NCBI_nucleotide/sequence (12).gb": (
        "a27b6cddb546565055911873fce2fdde1bd29d064435d8badf2754af6fac055c"
    ),
    "data/raw/NCBI_nucleotide/sequence (13).gb": (
        "0b74ea872b31e09af5d10ef4ead998e1874c83e975c846b30e15e24d3bbed2fb"
    ),
    "data/raw/NCBI_nucleotide/sequence (14).gb": (
        "3490c7e66ba22df5f451ce0a05ec86cbee6a8cdef446ea9fa73eb15679b7f56c"
    ),
    "data/raw/NCBI_nucleotide/sequence (15).gb": (
        "a49fb40c880af0ea16662d9c88305264276ef5182a51bc40830d67416bc1ff5f"
    ),
    "data/raw/NCBI_nucleotide/sequence (16).gb": (
        "d2275cbd2e1134ad7de5f9e687297179d936059470e8357f1dce446a33571db2"
    ),
    "data/raw/NCBI_nucleotide/sequence (17).gb": (
        "78289052d3d0cc769bd2318af269f0ab6e4652cea7b4fd068733aa9456cf1ec4"
    ),
    "data/raw/NCBI_nucleotide/sequence (2).gb": (
        "b34e78d3754b7f1147df984d3f796f8bdb9bfad288287d318fd49e6a20c83be8"
    ),
    "data/raw/NCBI_nucleotide/sequence (3).gb": (
        "7d58262d81ddfc4af5899cc78341794948ecac826513c339b8bb2de4dd137227"
    ),
    "data/raw/NCBI_nucleotide/sequence (4).gb": (
        "62431cd2b251c63b0ccf96b99ecdd2b814397be2b40d50722dabf77175778380"
    ),
    "data/raw/NCBI_nucleotide/sequence (5).gb": (
        "3cf2cf0193095d3b74ed07617c28fc55222ad7ccba8d31a5a602c1d892172228"
    ),
    "data/raw/NCBI_nucleotide/sequence (6).gb": (
        "3d4227ef665d9f4fe210b4999654e8bccbee38c6d4b2ed2a93ed194fbfdd8562"
    ),
    "data/raw/NCBI_nucleotide/sequence (7).gb": (
        "9114ec869c8401a54cc88219b2920bc8910275748c0d2bce2df06b33ea258647"
    ),
    "data/raw/NCBI_nucleotide/sequence (8).gb": (
        "22e417676d8fdff7ca6fbdc3f887d34eac3f19d3906d7100f1c9d0d600dd038f"
    ),
    "data/raw/NCBI_nucleotide/sequence (9).gb": (
        "2d866410f1ee6748b4256d34ffb6231b019ed2c3261fd46e42b68120ef1b158f"
    ),
    "data/raw/NCBI_nucleotide/sequence.gb": (
        "59f078113f4e3b2bdb6cd0c2cc14b76bf542c9b3042b34a71a47a2ef10c02ede"
    ),
}


class S3ClassifyError(ValueError):
    """Hard failure during S3 eligibility orchestration."""


@dataclass(frozen=True)
class S3RunResult:
    """Aggregate outcome of one S3 classification run."""

    source_key: str
    stats: (
        AptaBaseS3Stats
        | UTexasS3Stats
        | AptaDBS3Stats
        | RiboAptamerS3Stats
        | AptaIndexS3Stats
        | EnaS3Stats
        | AptamerBaseS3Stats
        | AptaDiffS3Stats
        | NcbiNucS3Stats
    )
    output_canonical: Path
    output_decisions: Path
    output_review: Path
    output_local_detail: Path
    output_summary: Path
    output_reason_counts: Path
    output_leakage_matches: Path | None
    s2_hash_before: str
    s2_hash_after: str
    qc_hash_before: str
    qc_hash_after: str
    sidecar_hash_before: str
    sidecar_hash_after: str
    inputs_unchanged: bool
    deterministic_rerun_ok: bool | None
    s2_integrity_ok: bool
    output_rejected: Path | None = None
    output_parks: Path | None = None
    output_parked_ssdna: Path | None = None
    output_parked_non_protein: Path | None = None
    output_parked_molecule_unresolved: Path | None = None
    output_parked_construct: Path | None = None
    raw_sha_before: str = ""
    raw_sha_after: str = ""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_output_dir_allowed(repo_root: Path, output_dir: Path) -> Path:
    resolved = output_dir if output_dir.is_absolute() else (repo_root / output_dir)
    resolved = resolved.resolve()
    interim_root = (repo_root / "data" / "interim").resolve()
    try:
        resolved.relative_to(interim_root)
    except ValueError as exc:
        raise S3ClassifyError(
            "S3 output directory must lie beneath data/interim/: "
            f"{output_dir}"
        ) from exc
    raw_root = (repo_root / "data" / "raw").resolve()
    try:
        resolved.relative_to(raw_root)
    except ValueError:
        pass
    else:
        raise S3ClassifyError(
            f"Refusing to write S3 outputs under data/raw/: {output_dir}"
        )
    return resolved


def _relative_display(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def write_csv_atomic(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, str]],
    *,
    quoting: int = csv.QUOTE_MINIMAL,
) -> None:
    """Atomically write a CSV with Unix newlines and a trailing newline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(fieldnames),
                lineterminator="\n",
                extrasaction="raise",
                quoting=quoting,
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({col: row.get(col, "") for col in fieldnames})
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def _read_corpus_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise S3ClassifyError(f"S2 canonical CSV has no header: {path.name}")
        validate_column_order(list(reader.fieldnames))
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        for column in CORPUS_COLUMNS:
            value = row.get(column)
            if value is None:
                raise S3ClassifyError(
                    f"S2 row {index} missing column {column!r}"
                )
            row[column] = value
    return rows


def _read_sidecar_csv(path: Path, *, label: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise S3ClassifyError(f"{label} CSV has no header: {path.name}")
        if "record_id" not in reader.fieldnames:
            raise S3ClassifyError(f"{label} CSV missing record_id")
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        if not row.get("record_id"):
            raise S3ClassifyError(f"{label} row {index} has blank record_id")
        for key, value in list(row.items()):
            row[key] = "" if value is None else value
    return rows


def _match_sidecar_one_to_one(
    canonical_rows: Sequence[dict[str, str]],
    sidecar_rows: Sequence[dict[str, str]],
    *,
    label: str,
) -> list[dict[str, str]]:
    """Return sidecar rows aligned to canonical order; hard-fail on mismatch."""
    if len(canonical_rows) != len(sidecar_rows):
        raise S3ClassifyError(
            f"S2 canonical and {label} row counts must match: "
            f"{len(canonical_rows)} vs {len(sidecar_rows)}"
        )

    by_id: dict[str, dict[str, str]] = {}
    for row in sidecar_rows:
        record_id = row["record_id"]
        if record_id in by_id:
            raise S3ClassifyError(
                f"Duplicate {label} record_id: {record_id!r}"
            )
        by_id[record_id] = row

    aligned: list[dict[str, str]] = []
    for canonical in canonical_rows:
        record_id = canonical["record_id"]
        if record_id not in by_id:
            raise S3ClassifyError(
                f"Missing {label} row for record_id={record_id!r}"
            )
        aligned.append(by_id[record_id])

    extra = set(by_id) - {row["record_id"] for row in canonical_rows}
    if extra:
        raise S3ClassifyError(
            f"Extra {label} record_id values not in canonical: {len(extra)}"
        )
    return aligned


def _count_sorted(mapping: Mapping[str, int]) -> list[tuple[str, int]]:
    return sorted(mapping.items(), key=lambda item: item[0])


def _nested_count_lines(
    mapping: Mapping[str, Mapping[str, int]],
) -> list[str]:
    lines: list[str] = []
    for decision in sorted(mapping):
        inner = mapping[decision]
        for key, count in _count_sorted(inner):
            lines.append(f"- `{decision}` / `{key}`: `{count}`")
    if not lines:
        lines.append("- (none)")
    return lines


def build_aptabase_checkpoint1_summary(
    *,
    repo_root: Path,
    result: S3RunResult,
    policy_path: Path,
    leakage_path: Path,
    aliases_path: Path,
) -> str:
    """Build an aggregate-only Markdown CHECKPOINT-1 summary (no sequences)."""
    stats = result.stats
    lines = [
        "# AptaBase CHECKPOINT-1 summary",
        "",
        "## Totals",
        "",
        f"- Total records: `{stats.s3_rows}`",
        f"- Unique record IDs: `{stats.unique_record_ids}`",
        f"- S2 order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        "",
        "## Proposed decisions",
        "",
    ]
    for name, count in _count_sorted(stats.decision_counts):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(["", "## Primary reasons", ""])
    for name, count in _count_sorted(stats.primary_reason_counts):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(["", "## Review priorities", ""])
    for name, count in _count_sorted(stats.review_priority_counts):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(
        [
            "",
            "## Manual review queue",
            "",
            f"- `manual_review_required=true`: "
            f"`{stats.manual_review_required_true_count}`",
            f"- `manual_review_required=false`: "
            f"`{stats.manual_review_required_false_count}`",
            f"- Mechanical missing-sequence rejects excluded from manual review: "
            f"`{stats.missing_sequence_excluded_from_review_count}`",
            "",
            "## Leakage",
            "",
            f"- Sequence leakage matches: `{stats.sequence_leakage_count}`",
            f"- Target leakage matches: `{stats.target_leakage_count}`",
            f"- Both sequence and target leakage: `{stats.both_leakage_count}`",
            "",
            "## Condition tallies",
            "",
            f"- Missing sequences: `{stats.missing_sequence_count}`",
            f"- Source-invalid records: `{stats.source_invalid_count}`",
            f"- Core below minimum: `{stats.core_below_minimum_count}`",
            f"- Invalid sequences: `{stats.invalid_sequence_count}`",
            f"- Ambiguous sequences: `{stats.ambiguous_sequence_count}`",
            f"- Mixed T/U: `{stats.mixed_t_u_count}`",
            f"- Trim/construct review: `{stats.trim_review_count}`",
            f"- Core above maximum: `{stats.core_above_maximum_count}`",
            f"- ssDNA: `{stats.ssdna_count}`",
            f"- Unknown molecule type: `{stats.unknown_molecule_count}`",
            f"- Missing targets: `{stats.missing_target_count}`",
            f"- Technically eligible RNA: `{stats.technically_eligible_rna_count}`",
            f"- Records with multiple eligibility reasons: "
            f"`{stats.multiple_reasons_count}`",
            "",
            "## Molecule type by decision",
            "",
        ]
    )
    lines.extend(_nested_count_lines(stats.molecule_type_by_decision))

    lines.extend(["", "## Alphabet by decision", ""])
    lines.extend(_nested_count_lines(stats.alphabet_by_decision))

    lines.extend(["", "## Core-length bucket by decision", ""])
    lines.extend(_nested_count_lines(stats.core_length_bucket_by_decision))

    lines.extend(
        [
            "",
            "## Invalid / ambiguous / mixed by decision",
            "",
            "### Invalid character",
            "",
        ]
    )
    for name, count in _count_sorted(stats.invalid_by_decision):
        lines.append(f"- `{name}`: `{count}`")
    if not stats.invalid_by_decision:
        lines.append("- (none)")

    lines.extend(["", "### Ambiguous base", ""])
    for name, count in _count_sorted(stats.ambiguous_by_decision):
        lines.append(f"- `{name}`: `{count}`")
    if not stats.ambiguous_by_decision:
        lines.append("- (none)")

    lines.extend(["", "### Mixed T/U", ""])
    for name, count in _count_sorted(stats.mixed_by_decision):
        lines.append(f"- `{name}`: `{count}`")
    if not stats.mixed_by_decision:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"- S2 canonical hash before: `{result.s2_hash_before}`",
            f"- S2 canonical hash after: `{result.s2_hash_after}`",
            f"- S2 QC hash before: `{result.qc_hash_before}`",
            f"- S2 QC hash after: `{result.qc_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            f"- S2 input integrity: "
            f"`{'pass' if result.s2_integrity_ok else 'fail'}`",
            f"- Inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            "",
            "## Inputs",
            "",
            f"- Eligibility policy: `{_relative_display(policy_path, repo_root)}`",
            f"- Leakage exclusion set: "
            f"`{_relative_display(leakage_path, repo_root)}`",
            f"- Target aliases: `{_relative_display(aliases_path, repo_root)}`",
            "",
            "## Outputs",
            "",
            f"- Canonical: `{_relative_display(result.output_canonical, repo_root)}`",
            f"- Decisions: `{_relative_display(result.output_decisions, repo_root)}`",
            f"- Checkpoint review (sequence-free index): "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Checkpoint local detail (sequence-bearing scientific review): "
            f"`{_relative_display(result.output_local_detail, repo_root)}`",
            f"- Reason counts: "
            f"`{_relative_display(result.output_reason_counts, repo_root)}`",
            f"- Leakage matches: "
            f"`{_relative_display(result.output_leakage_matches, repo_root)}`",
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            "## Local-detail warning",
            "",
            "WARNING: `aptabase_checkpoint1_local_detail.csv` contains source "
            "and canonical sequences for manual scientific review. It must "
            "remain beneath ignored `data/` and must never be staged or tracked.",
            "",
            "## Pipeline stop",
            "",
            PIPELINE_STOP_STATEMENT,
            "",
        ]
    )
    return "\n".join(lines)


def _assert_accept_invariants(decision_rows: Sequence[Mapping[str, str]]) -> None:
    """Hard-fail if any proposed accept violates RNA eligibility invariants."""
    for row in decision_rows:
        if row["proposed_decision"] != "proposed_accept":
            continue
        if row["molecule_type"] != "RNA":
            raise S3ClassifyError("proposed accept contains non-RNA molecule_type")
        if row["primary_reason"] != "technically_eligible_rna":
            raise S3ClassifyError(
                "proposed accept primary_reason must be technically_eligible_rna"
            )
        if row["sequence_leakage_match"] == "true":
            raise S3ClassifyError("proposed accept matched sequence leakage")
        if row["target_leakage_match"] == "true":
            raise S3ClassifyError("proposed accept matched target leakage")
        flags = {part for part in row["qc_flags"].split("|") if part}
        if flags & {
            "invalid_character",
            "ambiguous_base",
            "mixed_t_u",
            "trim_requires_review",
            "known_promoter_detected",
        }:
            raise S3ClassifyError(
                "proposed accept has unresolved sequence/trim QC flags"
            )
        if row["trim_status"] == "review_required":
            raise S3ClassifyError("proposed accept has trim_status=review_required")
        try:
            core_len = int(row["sequence_length_core"])
        except ValueError as exc:
            raise S3ClassifyError(
                "proposed accept has non-integer sequence_length_core"
            ) from exc
        if not (20 <= core_len <= 100):
            raise S3ClassifyError(
                "proposed accept core length outside 20–100 nt policy"
            )
        if row["molecule_type"] in {"ssDNA", "unknown"}:
            raise S3ClassifyError("ssDNA/unknown must never be accepted")


def _assert_reject_park_invariants(decision_rows: Sequence[Mapping[str, str]]) -> None:
    for row in decision_rows:
        decision = row["proposed_decision"]
        primary = row["primary_reason"]
        if primary == "missing_sequence" and decision != "proposed_reject":
            raise S3ClassifyError("missing sequence must never be accepted or parked")
        if primary == "core_below_minimum" and decision != "proposed_reject":
            raise S3ClassifyError("core below minimum must never be accepted or parked")
        if primary == "core_above_maximum_requires_review" and decision == (
            "proposed_accept"
        ):
            raise S3ClassifyError("core above maximum must never be accepted")
        if decision == "proposed_accept" and primary in {
            "ssdna_not_eligible_for_rna_training",
            "molecule_type_unresolved",
            "invalid_sequence_requires_review",
            "ambiguous_sequence_requires_review",
            "mixed_t_u_requires_review",
        }:
            raise S3ClassifyError(
                f"Invalid accept for primary_reason={primary}"
            )
        if row["checkpoint_status"] != "pending_checkpoint_1_review":
            raise S3ClassifyError("Unexpected checkpoint_status at S3")


def run_aptabase_s3(
    *,
    repo_root: Path,
    input_dir: Path,
    source_metadata_dir: Path,
    leakage_set: Path,
    target_aliases: Path,
    eligibility_policy: Path,
    output_dir: Path,
    expected_rows: int | None = EXPECTED_APTABASE_ROWS,
    check_deterministic_rerun: bool = False,
) -> S3RunResult:
    """Execute AptaBase S3 eligibility classification and CHECKPOINT-1."""
    assert_no_legacy_cleaner_import()
    repo_root = repo_root.resolve()
    input_dir = (
        input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    ).resolve()
    source_metadata_dir = (
        source_metadata_dir
        if source_metadata_dir.is_absolute()
        else (repo_root / source_metadata_dir)
    ).resolve()
    leakage_set = (
        leakage_set if leakage_set.is_absolute() else (repo_root / leakage_set)
    ).resolve()
    target_aliases = (
        target_aliases
        if target_aliases.is_absolute()
        else (repo_root / target_aliases)
    ).resolve()
    eligibility_policy = (
        eligibility_policy
        if eligibility_policy.is_absolute()
        else (repo_root / eligibility_policy)
    ).resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    canonical_path = input_dir / "aptabase_normalised.csv"
    qc_path = input_dir / "aptabase_s2_qc.csv"
    sidecar_path = source_metadata_dir / "aptabase_source_metadata.csv"
    for path, label in (
        (canonical_path, "S2 canonical"),
        (qc_path, "S2 QC"),
        (sidecar_path, "source-metadata"),
    ):
        if not path.is_file():
            raise S3ClassifyError(f"Missing {label} input: {path.name}")

    s2_hash_before = _sha256_file(canonical_path)
    qc_hash_before = _sha256_file(qc_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    policy = load_eligibility_policy(eligibility_policy)
    if policy.source_key != "aptabase":
        raise S3ClassifyError(
            f"Eligibility policy source_key must be aptabase; got {policy.source_key!r}"
        )
    leakage_index = load_sequence_leakage_index(leakage_set)
    alias_rules = load_target_alias_rules(target_aliases)

    canonical_rows = _read_corpus_csv(canonical_path)
    qc_rows = _read_sidecar_csv(qc_path, label="S2 QC")
    sidecar_rows = _read_sidecar_csv(sidecar_path, label="source-metadata")
    aligned_qc = _match_sidecar_one_to_one(
        canonical_rows, qc_rows, label="S2 QC"
    )
    aligned_sidecar = _match_sidecar_one_to_one(
        canonical_rows, sidecar_rows, label="source-metadata"
    )

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S3ClassifyError(
            f"S2 row count must be {expected_rows}; got {len(canonical_rows)}"
        )

    stats = AptaBaseS3Stats()
    stats.s2_rows = len(canonical_rows)
    stats.order_preserved = True

    s3_canonical: list[dict[str, str]] = []
    decision_rows: list[dict[str, str]] = []
    leakage_rows: list[dict[str, str]] = []
    # Parallel list aligned to S2/canonical order; reordered later for review.
    local_detail_by_id: dict[str, dict[str, str]] = {}

    for s2_row, qc_row, meta_row in zip(
        canonical_rows, aligned_qc, aligned_sidecar, strict=True
    ):
        result = classify_aptabase_record(
            s2_row,
            qc_row,
            meta_row,
            policy=policy,
            leakage_index=leakage_index,
            target_alias_rules=alias_rules,
        )
        if result.canonical["record_id"] != s2_row["record_id"]:
            stats.order_preserved = False
            raise S3ClassifyError("S3 altered record_id or row identity")
        for column in CORPUS_COLUMNS:
            if result.canonical[column] != s2_row[column]:
                raise S3ClassifyError(
                    f"S3 altered S2 canonical field {column!r}"
                )
        s3_canonical.append(result.canonical)
        decision_rows.append(result.decision)
        leakage_rows.extend(result.leakage_rows)
        local_detail_by_id[result.canonical["record_id"]] = build_local_detail_row(
            canonical=result.canonical,
            s2_qc=qc_row,
            source_metadata=meta_row,
            decision=result.decision,
        )
        update_stats_from_row(stats, result)

    stats.s3_rows = len(s3_canonical)
    stats.unique_record_ids = len({row["record_id"] for row in s3_canonical})

    if expected_rows == EXPECTED_APTABASE_ROWS:
        if stats.s3_rows != EXPECTED_APTABASE_ROWS:
            raise S3ClassifyError(
                f"S3 must preserve {EXPECTED_APTABASE_ROWS} rows; got {stats.s3_rows}"
            )
        if stats.unique_record_ids != EXPECTED_APTABASE_ROWS:
            raise S3ClassifyError("S3 record_id values are not unique")
        if len(decision_rows) != EXPECTED_APTABASE_ROWS:
            raise S3ClassifyError("Decision row count mismatch")

    if len({row["record_id"] for row in decision_rows}) != len(decision_rows):
        raise S3ClassifyError("Decision sidecar contains duplicate record_id values")

    for row in decision_rows:
        if row["proposed_decision"] not in {
            "proposed_accept",
            "proposed_park",
            "proposed_reject",
        }:
            raise S3ClassifyError(
                f"Unknown proposed_decision {row['proposed_decision']!r}"
            )
        if not row["primary_reason"]:
            raise S3ClassifyError("Decision row missing primary_reason")

    _assert_accept_invariants(decision_rows)
    _assert_reject_park_invariants(decision_rows)

    # Leakage file must reconcile to decision leakage flags.
    seq_leak_decisions = sum(
        1 for row in decision_rows if row["sequence_leakage_match"] == "true"
    )
    tgt_leak_decisions = sum(
        1 for row in decision_rows if row["target_leakage_match"] == "true"
    )
    seq_leak_file = sum(1 for row in leakage_rows if row["match_scope"] == "sequence")
    tgt_leak_file = sum(1 for row in leakage_rows if row["match_scope"] == "target")
    if seq_leak_decisions != seq_leak_file or seq_leak_decisions != (
        stats.sequence_leakage_count
    ):
        raise S3ClassifyError("Sequence leakage counts do not reconcile")
    if tgt_leak_decisions != tgt_leak_file or tgt_leak_decisions != (
        stats.target_leakage_count
    ):
        raise S3ClassifyError("Target leakage counts do not reconcile")

    # Reason counts must reconcile to total rows.
    reason_count_rows: list[dict[str, str]] = []
    combo_counts: dict[tuple[str, str], int] = {}
    for row in decision_rows:
        key = (row["proposed_decision"], row["primary_reason"])
        combo_counts[key] = combo_counts.get(key, 0) + 1
    for (decision, reason), count in sorted(combo_counts.items()):
        reason_count_rows.append(
            {
                "proposed_decision": decision,
                "primary_reason": reason,
                "record_count": str(count),
            }
        )
    if sum(int(row["record_count"]) for row in reason_count_rows) != len(decision_rows):
        raise S3ClassifyError("Reason counts do not reconcile to decision rows")

    review_rows = sorted(decision_rows, key=review_sort_key)
    if len(review_rows) != len(decision_rows):
        raise S3ClassifyError("Checkpoint review row count mismatch")

    # Local-detail rows follow the same review ordering as the sequence-free index.
    local_detail_rows: list[dict[str, str]] = []
    for review_row in review_rows:
        record_id = review_row["record_id"]
        if record_id not in local_detail_by_id:
            raise S3ClassifyError(
                f"Missing local-detail row for record_id={record_id!r}"
            )
        local_detail_rows.append(local_detail_by_id[record_id])
    if len(local_detail_rows) != len(decision_rows):
        raise S3ClassifyError("Local-detail row count mismatch")
    for review_row, detail_row in zip(review_rows, local_detail_rows, strict=True):
        if review_row["record_id"] != detail_row["record_id"]:
            raise S3ClassifyError(
                "Local-detail ordering does not match sequence-free review"
            )

    # Guard: no sequence columns in review/decision artefacts.
    forbidden_seq_cols = {
        "sequence_raw",
        "sequence_full",
        "sequence_core",
        "sequence_compare_full",
        "sequence_compare_core",
    }
    for col in forbidden_seq_cols:
        if col in DECISION_COLUMNS or col in LEAKAGE_MATCH_COLUMNS:
            raise S3ClassifyError(f"Sequence column leaked into sidecar schema: {col}")
    for col in ("sequence_raw", "sequence_full", "sequence_core"):
        if col not in LOCAL_DETAIL_COLUMNS:
            raise S3ClassifyError(
                f"Local-detail schema missing required sequence column: {col}"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_canonical = output_dir / "aptabase_s3_canonical.csv"
    out_decisions = output_dir / "aptabase_s3_decisions.csv"
    out_review = output_dir / "aptabase_checkpoint1_review.csv"
    out_local_detail = output_dir / "aptabase_checkpoint1_local_detail.csv"
    out_reason_counts = output_dir / "aptabase_checkpoint1_reason_counts.csv"
    out_leakage = output_dir / "aptabase_leakage_matches.csv"
    out_summary = output_dir / "aptabase_checkpoint1_summary.md"

    write_corpus_csv_atomic(out_canonical, s3_canonical)
    write_csv_atomic(out_decisions, DECISION_COLUMNS, decision_rows)
    write_csv_atomic(out_review, DECISION_COLUMNS, review_rows)
    write_csv_atomic(out_local_detail, LOCAL_DETAIL_COLUMNS, local_detail_rows)
    write_csv_atomic(out_reason_counts, REASON_COUNT_COLUMNS, reason_count_rows)
    write_csv_atomic(out_leakage, LEAKAGE_MATCH_COLUMNS, leakage_rows)

    s2_hash_after = _sha256_file(canonical_path)
    qc_hash_after = _sha256_file(qc_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    inputs_unchanged = (
        s2_hash_before == s2_hash_after
        and qc_hash_before == qc_hash_after
        and sidecar_hash_before == sidecar_hash_after
    )
    if not inputs_unchanged:
        raise S3ClassifyError("S2/source inputs were modified during S3 execution")

    s2_integrity_ok = True
    # Canonical output must be byte-identical to S2 input.
    if _sha256_file(out_canonical) != s2_hash_before:
        raise S3ClassifyError(
            "S3 canonical output is not byte-identical to S2 normalised input"
        )

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "canonical": _sha256_file(out_canonical),
            "decisions": _sha256_file(out_decisions),
            "review": _sha256_file(out_review),
            "local_detail": _sha256_file(out_local_detail),
            "reason_counts": _sha256_file(out_reason_counts),
            "leakage": _sha256_file(out_leakage),
        }
        second = run_aptabase_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            leakage_set=leakage_set,
            target_aliases=target_aliases,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["canonical"] == _sha256_file(second.output_canonical)
            and first_hashes["decisions"] == _sha256_file(second.output_decisions)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["local_detail"]
            == _sha256_file(second.output_local_detail)
            and first_hashes["reason_counts"]
            == _sha256_file(second.output_reason_counts)
            and first_hashes["leakage"] == _sha256_file(second.output_leakage_matches)
        )
        if not deterministic_ok:
            raise S3ClassifyError(
                "S3 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S3RunResult(
        source_key="aptabase",
        stats=stats,
        output_canonical=out_canonical,
        output_decisions=out_decisions,
        output_review=out_review,
        output_local_detail=out_local_detail,
        output_summary=out_summary,
        output_reason_counts=out_reason_counts,
        output_leakage_matches=out_leakage,
        s2_hash_before=s2_hash_before,
        s2_hash_after=s2_hash_after,
        qc_hash_before=qc_hash_before,
        qc_hash_after=qc_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        s2_integrity_ok=s2_integrity_ok,
    )
    summary_text = build_aptabase_checkpoint1_summary(
        repo_root=repo_root,
        result=run_result,
        policy_path=eligibility_policy,
        leakage_path=leakage_set,
        aliases_path=target_aliases,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must not contain absolute repository paths"
        )
    if PIPELINE_STOP_STATEMENT not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing pipeline stop statement")
    _write_text_atomic(out_summary, summary_text)
    return run_result


def _core_length_bucket_from_raw(raw: str) -> str:
    text = (raw or "").strip()
    if text == "":
        return "missing"
    length = int(text)
    if length < 20:
        return "below_20"
    if length <= 100:
        return "20_to_100"
    if length <= 200:
        return "101_to_200"
    return "above_200"


def _assert_utexas_s2_invariants(canonical_rows: Sequence[dict[str, str]]) -> None:
    """Hard-fail if the UTexas S2 starting invariants no longer reconcile."""
    if len(canonical_rows) != EXPECTED_UTEXAS_ROWS:
        raise S3ClassifyError(
            f"S3 input rows must be {EXPECTED_UTEXAS_ROWS}; got {len(canonical_rows)}"
        )
    record_ids = [row["record_id"] for row in canonical_rows]
    native_ids = [row["native_id"] for row in canonical_rows]
    if len(set(record_ids)) != EXPECTED_UTEXAS_ROWS:
        raise S3ClassifyError("S2 record_id values are not unique")
    if len(set(native_ids)) != EXPECTED_UTEXAS_ROWS:
        raise S3ClassifyError("S2 native_id values are not unique")

    missing = sum(1 for row in canonical_rows if row.get("sequence_core", "") == "")
    nonempty = len(canonical_rows) - missing
    if missing != EXPECTED_UTEXAS_MISSING or nonempty != EXPECTED_UTEXAS_NONEMPTY:
        raise S3ClassifyError(
            "S2 missing/nonempty sequence counts drifted: "
            f"missing={missing} nonempty={nonempty}"
        )

    molecule_counts: dict[str, int] = {}
    for row in canonical_rows:
        molecule = row.get("molecule_type") or ""
        molecule_counts[molecule] = molecule_counts.get(molecule, 0) + 1
        for field_name in (
            "target_name",
            "target_type",
            "binding_evidence_score",
            "affinity_value",
            "cluster_id",
            "partition",
        ):
            if row.get(field_name):
                raise S3ClassifyError(
                    f"S2 canonical unexpectedly populated {field_name}"
                )

    if molecule_counts != EXPECTED_UTEXAS_MOLECULE:
        raise S3ClassifyError(
            f"S2 molecule_type counts drifted: {molecule_counts}"
        )
    # Alphabet recoveries and subsequent approved trims may legitimately
    # change core-length, alphabet-QC, construct-scope and trim tallies.
    # Those are reported from the rerun rather than pinned to the pre-recovery
    # S2 snapshot.


def build_utexas_checkpoint1_summary(
    *,
    repo_root: Path,
    result: S3RunResult,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown CHECKPOINT-1 summary (no sequences)."""
    stats = result.stats
    if not isinstance(stats, UTexasS3Stats):
        raise S3ClassifyError("UTexas summary requires UTexasS3Stats")

    def _count(mapping: Mapping[str, int], key: str) -> int:
        return int(mapping.get(key, 0))

    lines = [
        "# UTexas CHECKPOINT-1 summary",
        "",
        "## Input",
        "",
        f"- S3 input rows = `{stats.s2_rows}`",
        f"- Unique record IDs: `{stats.unique_record_ids}`",
        f"- Unique native IDs: `{stats.unique_native_ids}`",
        f"- S2 order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        "",
        "## Primary decisions",
        "",
        f"- `proposed_accept` = `{_count(stats.decision_counts, 'proposed_accept')}`",
        f"- `proposed_park` = `{_count(stats.decision_counts, 'proposed_park')}`",
        f"- `proposed_reject` = `{_count(stats.decision_counts, 'proposed_reject')}`",
        f"- Reconciliation: `"
        f"{sum(stats.decision_counts.values())} = "
        f"{stats.s3_rows}`",
        "",
        "## Reject counts by reason",
        "",
        f"- `missing_sequence`: `{_count(stats.primary_reason_counts, 'missing_sequence')}`",
        f"- `mixed_T_and_U`: `{_count(stats.primary_reason_counts, 'mixed_T_and_U')}`",
        f"- `ambiguous_bases`: `{_count(stats.primary_reason_counts, 'ambiguous_bases')}`",
        f"- `invalid_alphabet`: `{_count(stats.primary_reason_counts, 'invalid_alphabet')}`",
        f"- `alignment_gaps`: `{_count(stats.primary_reason_counts, 'alignment_gaps')}`",
        f"- `length_out_of_range`: `{_count(stats.primary_reason_counts, 'length_out_of_range')}`",
        "",
        "Condition tallies (a record may contribute to more than one):",
        "",
        f"- missing-sequence condition: `{stats.missing_sequence_count}`",
        f"- mixed T/U condition: `{stats.mixed_t_u_count}`",
        f"- ambiguous-bases condition: `{stats.ambiguous_bases_count}`",
        f"- invalid-alphabet condition: `{stats.invalid_alphabet_count}`",
        f"- alignment-gaps condition: `{stats.alignment_gaps_count}`",
        f"- length-out-of-range condition: `{stats.length_out_of_range_count}`",
        "",
        "## Park counts",
        "",
        f"- explicit DNA/ssDNA (`non_rna_molecule` primary): "
        f"`{_count(stats.primary_reason_counts, 'non_rna_molecule')}`",
        f"- unresolved molecule (`molecule_type_unresolved` primary): "
        f"`{_count(stats.primary_reason_counts, 'molecule_type_unresolved')}`",
        f"- trim/construct unresolved (`trim_construct_unresolved` primary): "
        f"`{_count(stats.primary_reason_counts, 'trim_construct_unresolved')}`",
        "",
        "Condition tallies (a record may contribute to more than one):",
        "",
        f"- explicit DNA/ssDNA condition: `{stats.non_rna_molecule_count}`",
        f"- unresolved-molecule condition: `{stats.unknown_molecule_count}`",
        f"- trim/construct-unresolved condition: "
        f"`{stats.trim_construct_unresolved_count}`",
        "",
        "## Proposed accepts",
        "",
        f"- `technically_eligible_rna` primary: "
        f"`{_count(stats.primary_reason_counts, 'technically_eligible_rna')}`",
        f"- technically eligible RNA condition: "
        f"`{stats.technically_eligible_rna_count}`",
        "",
        "## Review queue",
        "",
        f"- `manual_review_required=true`: "
        f"`{stats.manual_review_required_true_count}`",
        f"- `manual_review_required=false` (mechanical / no-review): "
        f"`{stats.manual_review_required_false_count}`",
        f"- Mechanical missing-sequence rejects excluded from manual review: "
        f"`{stats.missing_sequence_excluded_from_review_count}`",
        "",
        "### Counts by review batch",
        "",
    ]
    for batch in (
        "01_reject_review",
        "02_accept_with_diagnostics",
        "03_park_unresolved_molecule",
        "04_park_trim_construct",
        "05_repair_alignment_gaps",
    ):
        lines.append(f"- `{batch}`: `{_count(stats.review_batch_counts, batch)}`")
    extra_batches = sorted(
        name
        for name in stats.review_batch_counts
        if name
        not in {
            "01_reject_review",
            "02_accept_with_diagnostics",
            "03_park_unresolved_molecule",
            "04_park_trim_construct",
            "05_repair_alignment_gaps",
        }
    )
    for batch in extra_batches:
        lines.append(f"- `{batch}`: `{stats.review_batch_counts[batch]}`")

    lines.extend(
        [
            "",
            "## Trim context",
            "",
            "Under the UTexas source-specific eligibility judgement, unresolved "
            "trim/construct QC is retained as provenance and does not by itself "
            "prevent technically valid RNA from being proposed accept.",
            "",
            f"- medium-confidence trim condition: `{stats.medium_trim_count}`",
            f"- medium-trim rows in the active review queue: "
            f"`{stats.medium_trim_review_count}`",
            f"- trim/construct-unresolved condition: "
            f"`{stats.trim_construct_unresolved_count}`",
            f"- trim/construct unresolved primary parks: "
            f"`{_count(stats.primary_reason_counts, 'trim_construct_unresolved')}`",
            f"- `trim_combined_exceeds_40pct` condition: "
            f"`{stats.trim_combined_exceeds_40pct_count}`",
            "",
            "Explicit DNA/ssDNA records remain mechanical parks even when they "
            "also carry a medium-confidence trim diagnostic. Those diagnostics "
            "are retained on the decision sidecar; they are not queued as "
            "ssDNA confirmation reviews.",
            "",
            "## Length",
            "",
            f"- length-out-of-range primary rejects: "
            f"`{_count(stats.primary_reason_counts, 'length_out_of_range')}`",
            f"- full-passed / core-failed (`trim_pushed_length_out_of_range`): "
            f"`{stats.trim_pushed_length_count}`",
            f"- lower-boundary (20–25 nt) condition: `{stats.boundary_low_count}`",
            f"- upper-boundary (90–100 nt) condition: `{stats.boundary_high_count}`",
            f"- boundary-length rows in the active review queue: "
            f"`{stats.boundary_review_count}`",
            "",
            "### Core-length bucket by decision",
            "",
        ]
    )
    lines.extend(_nested_count_lines(stats.core_length_bucket_by_decision))

    lines.extend(
        [
            "",
            "## Random accept audit",
            "",
            f"- requested sample size: `30`",
            f"- clean non-review accept pool: "
            f"`{stats.random_accept_audit_pool_size}`",
            f"- sampled: `{stats.random_accept_audit_count}`",
            f"- shortfall: `{stats.random_accept_audit_shortfall}`",
            "",
            "## Primary reasons (all)",
            "",
        ]
    )
    for name, count in _count_sorted(stats.primary_reason_counts):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(["", "## Molecule type by decision", ""])
    lines.extend(_nested_count_lines(stats.molecule_type_by_decision))
    lines.extend(["", "## Chemistry by decision", ""])
    lines.extend(_nested_count_lines(stats.chemistry_by_decision))
    lines.extend(["", "## Alphabet by decision", ""])
    lines.extend(_nested_count_lines(stats.alphabet_by_decision))

    lines.extend(
        [
            "",
            "## Target/evidence boundary",
            "",
            "UTexas target type was not inferred in S3 because the source "
            "provides free-text target names only.",
            "Target normalisation, protein/non-protein classification and "
            "evidence eligibility are deferred to global S4.",
            "",
            "- Target type inferred: `no`",
            "- Evidence scored: `no`",
            "- Kd / Affinity parsed: `no`",
            "- Leakage exclusions applied: `no`",
            "- S4 started: `no`",
            "",
            "## Integrity",
            "",
            f"- S2 canonical hash before: `{result.s2_hash_before}`",
            f"- S2 canonical hash after: `{result.s2_hash_after}`",
            f"- S2 QC hash before: `{result.qc_hash_before}`",
            f"- S2 QC hash after: `{result.qc_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            f"- S2 input integrity: "
            f"`{'pass' if result.s2_integrity_ok else 'fail'}`",
            f"- Inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            f"- Raw workbook SHA-256 before: `{result.raw_sha_before or 'not_checked'}`",
            f"- Raw workbook SHA-256 after: `{result.raw_sha_after or 'not_checked'}`",
            "",
            "## Inputs",
            "",
            f"- Eligibility policy: `{_relative_display(policy_path, repo_root)}`",
            "",
            "## Outputs",
            "",
            f"- Canonical: `{_relative_display(result.output_canonical, repo_root)}`",
            f"- Decisions: `{_relative_display(result.output_decisions, repo_root)}`",
            f"- Checkpoint review (sequence-free index of all rows): "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Checkpoint local detail (sequence-bearing scientific review): "
            f"`{_relative_display(result.output_local_detail, repo_root)}`",
            f"- Reason counts: "
            f"`{_relative_display(result.output_reason_counts, repo_root)}`",
        ]
    )
    if result.output_rejected is not None:
        lines.append(
            f"- Rejection log: `{_relative_display(result.output_rejected, repo_root)}`"
        )
    if result.output_parks is not None:
        lines.append(
            f"- Park sidecar: `{_relative_display(result.output_parks, repo_root)}`"
        )
    lines.extend(
        [
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            "## Local-detail warning",
            "",
            "WARNING: `utexas_checkpoint1_local_detail.csv` and "
            "`rejected_utexas.csv` contain source sequences. They must remain "
            "beneath ignored `data/` and must never be staged or tracked.",
            "",
            "## Pipeline stop",
            "",
            UTEXAS_PIPELINE_STOP_STATEMENT,
            "",
            "CHECKPOINT-1 generated = yes",
            "CHECKPOINT-1 human decisions applied = no",
            "records authorised_for_s4 = 0",
            "",
        ]
    )
    return "\n".join(lines)


def run_utexas_s3(
    *,
    repo_root: Path,
    input_dir: Path,
    source_metadata_dir: Path,
    eligibility_policy: Path,
    output_dir: Path,
    expected_rows: int | None = EXPECTED_UTEXAS_ROWS,
    check_deterministic_rerun: bool = False,
) -> S3RunResult:
    """Execute UTexas S3 technical eligibility classification and CHECKPOINT-1."""
    repo_root = repo_root.resolve()
    input_dir = (
        input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    ).resolve()
    source_metadata_dir = (
        source_metadata_dir
        if source_metadata_dir.is_absolute()
        else (repo_root / source_metadata_dir)
    ).resolve()
    eligibility_policy = (
        eligibility_policy
        if eligibility_policy.is_absolute()
        else (repo_root / eligibility_policy)
    ).resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    canonical_path = input_dir / "utexas_normalised.csv"
    qc_path = input_dir / "utexas_s2_qc.csv"
    sidecar_path = source_metadata_dir / "utexas_source_metadata.csv"
    for path, label in (
        (canonical_path, "S2 canonical"),
        (qc_path, "S2 QC"),
        (sidecar_path, "source-metadata"),
    ):
        if not path.is_file():
            raise S3ClassifyError(f"Missing {label} input: {path.name}")

    raw_path = (
        repo_root
        / "data"
        / "raw"
        / "UTexas_aptamer_dataset"
        / "UTexas Aptamer Database dataset_Sept2023.xlsx"
    )
    raw_sha_before = ""
    check_raw = expected_rows == EXPECTED_UTEXAS_ROWS and raw_path.is_file()
    if expected_rows == EXPECTED_UTEXAS_ROWS:
        if not raw_path.is_file():
            raise S3ClassifyError("Missing registered UTexas raw workbook")
        raw_sha_before = _sha256_file(raw_path)
        if raw_sha_before != EXPECTED_RAW_SHA256:
            raise S3ClassifyError(
                "UTexas raw workbook SHA-256 does not match registry expectation"
            )

    s2_hash_before = _sha256_file(canonical_path)
    qc_hash_before = _sha256_file(qc_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    policy = load_eligibility_policy(eligibility_policy)
    if policy.source_key != "utexas":
        raise S3ClassifyError(
            f"Eligibility policy source_key must be utexas; got {policy.source_key!r}"
        )
    if not policy.defer_target_classification or not policy.defer_evidence_scoring:
        raise S3ClassifyError(
            "UTexas S3 policy must defer target classification and evidence scoring"
        )
    if (
        policy.sequence_leakage_matching_enabled
        or policy.target_leakage_matching_enabled
        or not policy.defer_leakage_exclusion
    ):
        raise S3ClassifyError("UTexas S3 must not apply leakage exclusions")

    canonical_rows = _read_corpus_csv(canonical_path)
    qc_rows = _read_sidecar_csv(qc_path, label="S2 QC")
    sidecar_rows = _read_sidecar_csv(sidecar_path, label="source-metadata")
    aligned_qc = _match_sidecar_one_to_one(
        canonical_rows, qc_rows, label="S2 QC"
    )
    aligned_sidecar = _match_sidecar_one_to_one(
        canonical_rows, sidecar_rows, label="source-metadata"
    )

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S3ClassifyError(
            f"S2 row count must be {expected_rows}; got {len(canonical_rows)}"
        )
    if expected_rows == EXPECTED_UTEXAS_ROWS:
        _assert_utexas_s2_invariants(canonical_rows)

    stats = UTexasS3Stats()
    stats.s2_rows = len(canonical_rows)
    stats.order_preserved = True

    s3_canonical: list[dict[str, str]] = []
    decision_rows: list[dict[str, str]] = []
    rejection_rows: list[dict[str, str]] = []
    park_rows: list[dict[str, str]] = []
    local_detail_by_id: dict[str, dict[str, str]] = {}

    for s2_row, qc_row, meta_row in zip(
        canonical_rows, aligned_qc, aligned_sidecar, strict=True
    ):
        classified = classify_utexas_record(
            s2_row,
            qc_row,
            meta_row,
            policy=policy,
        )
        if classified.canonical["record_id"] != s2_row["record_id"]:
            stats.order_preserved = False
            raise S3ClassifyError("S3 altered record_id or row identity")
        for column in CORPUS_COLUMNS:
            if classified.canonical[column] != s2_row[column]:
                raise S3ClassifyError(
                    f"S3 altered S2 canonical field {column!r}"
                )
        s3_canonical.append(classified.canonical)
        decision_rows.append(classified.decision)
        if classified.rejection_row is not None:
            rejection_rows.append(classified.rejection_row)
        if classified.park_row is not None:
            park_rows.append(classified.park_row)
        local_detail_by_id[classified.canonical["record_id"]] = (
            build_utexas_local_detail_row(
                canonical=classified.canonical,
                s2_qc=qc_row,
                decision=classified.decision,
            )
        )
        update_utexas_stats_from_row(stats, classified)

    sampled, pool, shortfall = apply_random_accept_audit(
        decision_rows,
        local_detail_by_id,
        seed=policy.random_seed,
        sample_size=policy.random_accept_audit_size,
    )
    stats.random_accept_audit_pool_size = pool
    stats.random_accept_audit_shortfall = shortfall
    refresh_stats_after_audit(stats, decision_rows)

    stats.s3_rows = len(s3_canonical)
    stats.unique_record_ids = len({row["record_id"] for row in s3_canonical})
    stats.unique_native_ids = len({row["native_id"] for row in s3_canonical})

    if stats.s3_rows != len(canonical_rows):
        raise S3ClassifyError("S3 must preserve every S2 row")
    if stats.unique_record_ids != len(s3_canonical):
        raise S3ClassifyError("S3 record_id values are not unique")
    if len({row["record_id"] for row in decision_rows}) != len(decision_rows):
        raise S3ClassifyError("Decision sidecar contains duplicate record_id values")
    accept_n = stats.decision_counts.get("proposed_accept", 0)
    park_n = stats.decision_counts.get("proposed_park", 0)
    reject_n = stats.decision_counts.get("proposed_reject", 0)
    if accept_n + park_n + reject_n != stats.s3_rows:
        raise S3ClassifyError("accept + park + reject does not equal S3 rows")
    if len(rejection_rows) != reject_n:
        raise S3ClassifyError("Rejection log count does not match proposed_reject")
    if len(park_rows) != park_n:
        raise S3ClassifyError("Park sidecar count does not match proposed_park")
    if sampled != stats.random_accept_audit_count:
        raise S3ClassifyError("Random-accept audit count mismatch")

    for row in decision_rows:
        if not row["primary_reason"]:
            raise S3ClassifyError("Decision row missing primary_reason")

    assert_utexas_accept_invariants(
        decision_rows,
        unresolved_trim_blocks_eligibility=policy.unresolved_trim_blocks_eligibility,
    )
    assert_utexas_reject_park_invariants(decision_rows)

    reason_count_rows: list[dict[str, str]] = []
    combo_counts: dict[tuple[str, str], int] = {}
    for row in decision_rows:
        key = (row["proposed_decision"], row["primary_reason"])
        combo_counts[key] = combo_counts.get(key, 0) + 1
    for (decision, reason), count in sorted(combo_counts.items()):
        reason_count_rows.append(
            {
                "proposed_decision": decision,
                "primary_reason": reason,
                "record_count": str(count),
            }
        )
    if sum(int(row["record_count"]) for row in reason_count_rows) != len(decision_rows):
        raise S3ClassifyError("Reason counts do not reconcile to decision rows")

    review_rows = sorted(decision_rows, key=review_sort_key)
    local_detail_rows: list[dict[str, str]] = []
    for review_row in review_rows:
        record_id = review_row["record_id"]
        if record_id not in local_detail_by_id:
            raise S3ClassifyError(
                f"Missing local-detail row for record_id={record_id!r}"
            )
        local_detail_rows.append(local_detail_by_id[record_id])
    for review_row, detail_row in zip(review_rows, local_detail_rows, strict=True):
        if review_row["record_id"] != detail_row["record_id"]:
            raise S3ClassifyError(
                "Local-detail ordering does not match sequence-free review"
            )
        if review_row["review_batch"] != detail_row.get("review_batch", ""):
            raise S3ClassifyError("Local-detail review_batch mismatch")

    forbidden_seq_cols = {"sequence_raw", "sequence_full", "sequence_core"}
    for col in forbidden_seq_cols:
        if col in UTEXAS_DECISION_COLUMNS or col in UTEXAS_PARK_COLUMNS:
            raise S3ClassifyError(f"Sequence column leaked into sidecar schema: {col}")
    for col in ("sequence_raw", "sequence_full", "sequence_core"):
        if col not in UTEXAS_LOCAL_DETAIL_COLUMNS:
            raise S3ClassifyError(
                f"Local-detail schema missing required sequence column: {col}"
            )
        if col not in UTEXAS_REJECTION_COLUMNS and col != "sequence_raw":
            continue

    output_dir.mkdir(parents=True, exist_ok=True)
    out_canonical = output_dir / "utexas_s3_canonical.csv"
    out_decisions = output_dir / "utexas_s3_decisions.csv"
    out_review = output_dir / "utexas_checkpoint1_review.csv"
    out_local_detail = output_dir / "utexas_checkpoint1_local_detail.csv"
    out_reason_counts = output_dir / "utexas_checkpoint1_reason_counts.csv"
    out_rejected = output_dir / "rejected_utexas.csv"
    out_parks = output_dir / "utexas_s3_parks.csv"
    out_summary = output_dir / "utexas_checkpoint1_summary.md"

    write_corpus_csv_atomic(out_canonical, s3_canonical)
    write_csv_atomic(out_decisions, UTEXAS_DECISION_COLUMNS, decision_rows)
    write_csv_atomic(out_review, UTEXAS_DECISION_COLUMNS, review_rows)
    write_csv_atomic(out_local_detail, UTEXAS_LOCAL_DETAIL_COLUMNS, local_detail_rows)
    write_csv_atomic(out_reason_counts, UTEXAS_REASON_COUNT_COLUMNS, reason_count_rows)
    write_csv_atomic(out_rejected, UTEXAS_REJECTION_COLUMNS, rejection_rows)
    write_csv_atomic(out_parks, UTEXAS_PARK_COLUMNS, park_rows)

    s2_hash_after = _sha256_file(canonical_path)
    qc_hash_after = _sha256_file(qc_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    raw_sha_after = raw_sha_before
    if check_raw:
        raw_sha_after = _sha256_file(raw_path)
        if raw_sha_after != EXPECTED_RAW_SHA256:
            raise S3ClassifyError("UTexas raw workbook SHA-256 changed during S3")
    inputs_unchanged = (
        s2_hash_before == s2_hash_after
        and qc_hash_before == qc_hash_after
        and sidecar_hash_before == sidecar_hash_after
        and (not check_raw or raw_sha_before == raw_sha_after)
    )
    if not inputs_unchanged:
        raise S3ClassifyError("S2/source inputs were modified during S3 execution")

    s2_integrity_ok = True
    if _sha256_file(out_canonical) != s2_hash_before:
        raise S3ClassifyError(
            "S3 canonical output is not byte-identical to S2 normalised input"
        )

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "canonical": _sha256_file(out_canonical),
            "decisions": _sha256_file(out_decisions),
            "review": _sha256_file(out_review),
            "local_detail": _sha256_file(out_local_detail),
            "reason_counts": _sha256_file(out_reason_counts),
            "rejected": _sha256_file(out_rejected),
            "parks": _sha256_file(out_parks),
        }
        second = run_utexas_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["canonical"] == _sha256_file(second.output_canonical)
            and first_hashes["decisions"] == _sha256_file(second.output_decisions)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["local_detail"]
            == _sha256_file(second.output_local_detail)
            and first_hashes["reason_counts"]
            == _sha256_file(second.output_reason_counts)
            and first_hashes["rejected"] == _sha256_file(second.output_rejected)
            and first_hashes["parks"] == _sha256_file(second.output_parks)
        )
        if not deterministic_ok:
            raise S3ClassifyError(
                "S3 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S3RunResult(
        source_key="utexas",
        stats=stats,
        output_canonical=out_canonical,
        output_decisions=out_decisions,
        output_review=out_review,
        output_local_detail=out_local_detail,
        output_summary=out_summary,
        output_reason_counts=out_reason_counts,
        output_leakage_matches=None,
        s2_hash_before=s2_hash_before,
        s2_hash_after=s2_hash_after,
        qc_hash_before=qc_hash_before,
        qc_hash_after=qc_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        s2_integrity_ok=s2_integrity_ok,
        output_rejected=out_rejected,
        output_parks=out_parks,
        raw_sha_before=raw_sha_before,
        raw_sha_after=raw_sha_after,
    )
    summary_text = build_utexas_checkpoint1_summary(
        repo_root=repo_root,
        result=run_result,
        policy_path=eligibility_policy,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must not contain absolute repository paths"
        )
    if UTEXAS_PIPELINE_STOP_STATEMENT not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing pipeline stop statement")
    if "UTexas target type was not inferred in S3" not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing target-type deferral")
    _write_text_atomic(out_summary, summary_text)
    return run_result


def _read_plain_csv(path: Path, *, label: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise S3ClassifyError(f"{label} CSV has no header: {path.name}")
        rows = list(reader)
    for row in rows:
        for key, value in list(row.items()):
            row[key] = "" if value is None else value
    return rows


def _assert_aptadb_s2_invariants(canonical_rows: Sequence[dict[str, str]]) -> None:
    """Hard-fail if the AptaDB S2 starting invariants no longer reconcile."""
    if len(canonical_rows) != EXPECTED_APTADB_ROWS:
        raise S3ClassifyError(
            f"S3 input rows must be {EXPECTED_APTADB_ROWS}; got {len(canonical_rows)}"
        )
    record_ids = [row["record_id"] for row in canonical_rows]
    native_ids = [row["native_id"] for row in canonical_rows]
    if len(set(record_ids)) != EXPECTED_APTADB_ROWS:
        raise S3ClassifyError("S2 record_id values are not unique")
    if len(set(native_ids)) != EXPECTED_APTADB_ROWS:
        raise S3ClassifyError("S2 native_id values are not unique")

    molecule_counts: dict[str, int] = {}
    for row in canonical_rows:
        molecule = row.get("molecule_type") or ""
        molecule_counts[molecule] = molecule_counts.get(molecule, 0) + 1
        if row.get("sequence_core") != row.get("sequence_full"):
            raise S3ClassifyError(
                "AptaDB S2 starting state requires sequence_core == sequence_full"
            )
        if (row.get("trim_confidence") or "") not in {"", "n/a"}:
            raise S3ClassifyError(
                "AptaDB S2 starting state requires trim_confidence n/a; "
                "unapplied proposals must not be written as applied trims"
            )
        for field_name in (
            "target_name",
            "target_type",
            "target_type_source",
            "binding_evidence_score",
            "affinity_value",
            "cluster_id",
            "partition",
            "pdb_id",
        ):
            if row.get(field_name):
                raise S3ClassifyError(
                    f"S2 canonical unexpectedly populated {field_name}"
                )
    if molecule_counts != EXPECTED_APTADB_MOLECULE:
        raise S3ClassifyError(
            f"S2 molecule_type counts drifted: {molecule_counts}"
        )


def build_aptadb_checkpoint1_summary(
    *,
    repo_root: Path,
    result: S3RunResult,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown CHECKPOINT-1 summary (no sequences)."""
    stats = result.stats
    if not isinstance(stats, AptaDBS3Stats):
        raise S3ClassifyError("AptaDB summary requires AptaDBS3Stats")

    def _count(mapping: Mapping[str, int], key: str) -> int:
        return int(mapping.get(key, 0))

    rejected = _count(stats.primary_route_counts, PRIMARY_ROUTE_REJECT)
    parked_ssdna = _count(stats.primary_route_counts, PRIMARY_ROUTE_SSDNA)
    parked_non_protein = _count(stats.primary_route_counts, PRIMARY_ROUTE_NON_PROTEIN)
    eligible = _count(stats.primary_route_counts, PRIMARY_ROUTE_ELIGIBLE)
    routed_sum = rejected + parked_ssdna + parked_non_protein + eligible

    lines = [
        "# AptaDB S3 / CHECKPOINT-1 summary",
        "",
        "## Interaction reconciliation",
        "",
        f"- rows in = `{stats.s2_rows}`",
        f"- technical rejects = `{rejected}`",
        f"- parked ssDNA = `{parked_ssdna}`",
        f"- parked non-protein RNA = `{parked_non_protein}`",
        f"- RNA-protein technically eligible = `{eligible}`",
        f"- sum = `{routed_sum}`",
        f"- Unique record IDs: `{stats.unique_record_ids}`",
        f"- Unique native IDs: `{stats.unique_native_ids}`",
        f"- S2 order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        "",
        "## Technical rejection breakdown",
        "",
        f"- `missing_sequence`: `{_count(stats.primary_reason_counts, 'missing_sequence')}`",
        f"- `length_out_of_range`: `{_count(stats.primary_reason_counts, 'length_out_of_range')}`",
        f"- `mixed_T_and_U`: `{_count(stats.primary_reason_counts, 'mixed_T_and_U')}`",
        f"- `alignment_gaps`: `{_count(stats.primary_reason_counts, 'alignment_gaps')}`",
        f"- `invalid_alphabet`: `{_count(stats.primary_reason_counts, 'invalid_alphabet')}`",
        f"- `ambiguous_bases`: `{_count(stats.primary_reason_counts, 'ambiguous_bases')}`",
        f"- `primer_like`: `{_count(stats.primary_reason_counts, 'primer_like')}`",
        f"- `library_template`: `{_count(stats.primary_reason_counts, 'library_template')}`",
        f"- `truncated_sequence`: `{_count(stats.primary_reason_counts, 'truncated_sequence')}`",
        "",
        "Condition tallies (a record may contribute to more than one):",
        "",
        f"- missing-sequence condition: `{stats.missing_sequence_count}`",
        f"- mixed T/U condition: `{stats.mixed_t_u_count}`",
        f"- alignment-gaps condition: `{stats.alignment_gaps_count}`",
        f"- invalid-alphabet condition: `{stats.invalid_alphabet_count}`",
        f"- ambiguous-bases condition: `{stats.ambiguous_bases_count}`",
        f"- length-out-of-range condition: `{stats.length_out_of_range_count}`",
        f"- primer_like condition: `{stats.primer_like_count}`",
        f"- library_template condition: `{stats.library_template_count}`",
        f"- truncated_sequence condition: `{stats.truncated_sequence_count}`",
        "",
        "## Source-level reconciliation",
        "",
        f"- unlinked aptamers = `{stats.unlinked_aptamers}`",
        f"- missing_target rejection entries = `{stats.unlinked_missing_target_rejects}`",
        f"- chemistry split: DNA `{stats.unlinked_dna}` / RNA `{stats.unlinked_rna}`",
        "- Unlinked identities use `aptadb:unlinked:{Apta_index}` and are not",
        "  interaction Index IDs. Stage = `S3_source_reconciliation`.",
        "- These 37 source-level exclusions are additional to the 1,350-row",
        "  interaction stream and are not parked.",
        "",
        "## Parking",
        "",
        f"- source ssDNA total before technical rejection = `{stats.source_ssdna_before_technical}`",
        f"- technically rejected ssDNA = `{stats.technically_rejected_ssdna}`",
        f"- actually parked ssDNA = `{parked_ssdna}`",
        f"- RNA non-protein interactions before technical rejection = "
        f"`{stats.rna_non_protein_before_technical}`",
        f"- technically rejected RNA non-protein = "
        f"`{stats.technically_rejected_rna_non_protein}`",
        f"- actually parked RNA non-protein = `{parked_non_protein}`",
        "",
        "## Eligible corpus lane",
        "",
        f"- RNA Protein interactions before technical rejection = "
        f"`{stats.rna_protein_before_technical}`",
        f"- technically rejected RNA Protein interactions = "
        f"`{stats.technically_rejected_rna_protein}`",
        f"- final technically eligible RNA Protein interactions = `{eligible}`",
        "",
        "## CHECKPOINT-1",
        "",
        f"- unique review records: `{stats.unique_checkpoint_review_records}`",
        f"- judgement-dependent technical records: "
        f"`{stats.judgement_dependent_review_count}`",
        f"- constant-proposal records in review: `{stats.constant_review_count}`",
        f"- records associated with group-consensus proposals: "
        f"`{stats.constant_proposal_record_count}`",
        f"- records associated with known-motif proposals: "
        f"`{stats.known_motif_proposal_record_count}`",
        f"- boundary-length records in review: `{stats.boundary_review_count}`",
        f"- lower-boundary (20–25 nt) condition: `{stats.boundary_low_count}`",
        f"- upper-boundary (90–100 nt) condition: `{stats.boundary_high_count}`",
        f"- random kept audit sampled: `{stats.random_accept_audit_count}`",
        f"- random kept audit pool: `{stats.random_accept_audit_pool_size}`",
        f"- random kept audit shortfall: `{stats.random_accept_audit_shortfall}`",
        "",
        "### Counts by checkpoint review reason",
        "",
    ]
    if stats.checkpoint_review_reason_counts:
        for name, count in _count_sorted(stats.checkpoint_review_reason_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")

    lines.extend(["", "### Counts by review batch", ""])
    for batch in (
        "01_judgement_dependent_technical",
        "02_constant_region_proposal",
        "03_length_boundary",
        "04_random_kept_audit",
    ):
        lines.append(f"- `{batch}`: `{_count(stats.review_batch_counts, batch)}`")

    lines.extend(
        [
            "",
            "## Deferred to global S4",
            "",
            "AptaDB S3 does not classify Binding Conditions/Buffer + PMID as E3.",
            "Evidence mapping and thresholding (`no_binding_evidence`,",
            "`evidence_below_threshold`) remain deferred to global S4. This is",
            "an architecture decision, not an accidental omission of the plan",
            "wording.",
            "",
            "Target canonicalisation, Molecule/Cell/Other name resolution,",
            "UniProt lookup, target-family assignment, NDM-1/KPC/OXA/HSA",
            "leakage exclusion, PDB canonical-field population, cross-source",
            "deduplication, clustering, balancing and FT/REF/EVAL partitioning",
            "also remain deferred.",
            "",
            "- Target type inferred: `no`",
            "- Evidence scored: `no`",
            "- Leakage exclusions applied: `no`",
            "- Constant-region proposals applied: `no`",
            "- Human CHECKPOINT-1 decisions applied: `no`",
            "- S4 started: `no`",
            "",
            "## Integrity",
            "",
            f"- S2 canonical hash before: `{result.s2_hash_before}`",
            f"- S2 canonical hash after: `{result.s2_hash_after}`",
            f"- S2 QC hash before: `{result.qc_hash_before}`",
            f"- S2 QC hash after: `{result.qc_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            f"- S2 input integrity: "
            f"`{'pass' if result.s2_integrity_ok else 'fail'}`",
            f"- Inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            f"- Raw SHA-256 before: `{result.raw_sha_before or 'not_checked'}`",
            f"- Raw SHA-256 after: `{result.raw_sha_after or 'not_checked'}`",
            "",
            "## Inputs",
            "",
            f"- Eligibility policy: `{_relative_display(policy_path, repo_root)}`",
            "",
            "## Outputs",
            "",
            f"- Canonical: `{_relative_display(result.output_canonical, repo_root)}`",
            f"- Decisions: `{_relative_display(result.output_decisions, repo_root)}`",
            f"- Checkpoint review (sequence-free index of all rows): "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Checkpoint local detail (sequence-bearing scientific review): "
            f"`{_relative_display(result.output_local_detail, repo_root)}`",
            f"- Reason counts: "
            f"`{_relative_display(result.output_reason_counts, repo_root)}`",
        ]
    )
    if result.output_rejected is not None:
        lines.append(
            f"- Rejection log: `{_relative_display(result.output_rejected, repo_root)}`"
        )
    if result.output_parked_ssdna is not None:
        lines.append(
            f"- Parked ssDNA: "
            f"`{_relative_display(result.output_parked_ssdna, repo_root)}`"
        )
    if result.output_parked_non_protein is not None:
        lines.append(
            f"- Parked non-protein RNA: "
            f"`{_relative_display(result.output_parked_non_protein, repo_root)}`"
        )
    lines.extend(
        [
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            "## Local-detail warning",
            "",
            "WARNING: `aptadb_checkpoint1_local_detail.csv` and",
            "`rejected_aptadb.csv` contain source sequences. They must remain",
            "beneath ignored `data/` and must never be staged or tracked.",
            "",
            "## Pipeline stop",
            "",
            APTADB_PIPELINE_STOP_STATEMENT,
            "",
            "CHECKPOINT-1 generated = yes",
            "CHECKPOINT-1 human decisions applied = no",
            "records authorised_for_s4 = 0",
            "",
        ]
    )
    return "\n".join(lines)


def run_aptadb_s3(
    *,
    repo_root: Path,
    input_dir: Path,
    source_metadata_dir: Path,
    eligibility_policy: Path,
    output_dir: Path,
    expected_rows: int | None = EXPECTED_APTADB_ROWS,
    expected_unlinked_rows: int | None = None,
    check_deterministic_rerun: bool = False,
) -> S3RunResult:
    """Execute AptaDB S3 technical eligibility, parking, and CHECKPOINT-1."""
    repo_root = repo_root.resolve()
    input_dir = (
        input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    ).resolve()
    source_metadata_dir = (
        source_metadata_dir
        if source_metadata_dir.is_absolute()
        else (repo_root / source_metadata_dir)
    ).resolve()
    eligibility_policy = (
        eligibility_policy
        if eligibility_policy.is_absolute()
        else (repo_root / eligibility_policy)
    ).resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    if expected_unlinked_rows is None and expected_rows == EXPECTED_APTADB_ROWS:
        expected_unlinked_rows = EXPECTED_APTADB_UNLINKED

    canonical_path = input_dir / "aptadb_normalised.csv"
    qc_path = input_dir / "aptadb_s2_qc.csv"
    sidecar_path = source_metadata_dir / "aptadb_source_metadata.csv"
    proposals_path = input_dir / "aptadb_constant_region_proposals.csv"
    unlinked_path = source_metadata_dir / "aptadb_unlinked_aptamers.csv"
    for path, label in (
        (canonical_path, "S2 canonical"),
        (qc_path, "S2 QC"),
        (sidecar_path, "source-metadata"),
        (proposals_path, "S2 constant-region proposals"),
    ):
        if not path.is_file():
            raise S3ClassifyError(f"Missing {label} input: {path.name}")
    if expected_unlinked_rows and not unlinked_path.is_file():
        raise S3ClassifyError(f"Missing unlinked-aptamer input: {unlinked_path.name}")

    raw_dir = repo_root / "data" / "raw" / "AptaDB"
    raw_paths = {name: raw_dir / name for name in EXPECTED_APTADB_RAW_SHA256}
    raw_sha_before = ""
    check_raw = expected_rows == EXPECTED_APTADB_ROWS
    if check_raw:
        parts = []
        for name, path in raw_paths.items():
            if not path.is_file():
                raise S3ClassifyError(f"Missing registered AptaDB raw file: {name}")
            digest = _sha256_file(path)
            if digest != EXPECTED_APTADB_RAW_SHA256[name]:
                raise S3ClassifyError(
                    f"AptaDB raw {name} SHA-256 does not match registry expectation"
                )
            parts.append(f"{name}={digest}")
        raw_sha_before = ";".join(parts)

    s2_hash_before = _sha256_file(canonical_path)
    qc_hash_before = _sha256_file(qc_path)
    sidecar_hash_before = _sha256_file(sidecar_path)
    proposals_hash_before = _sha256_file(proposals_path)
    unlinked_hash_before = (
        _sha256_file(unlinked_path) if unlinked_path.is_file() else ""
    )

    policy = load_eligibility_policy(eligibility_policy)
    if policy.source_key != "aptadb":
        raise S3ClassifyError(
            f"Eligibility policy source_key must be aptadb; got {policy.source_key!r}"
        )
    if not policy.defer_target_classification or not policy.defer_evidence_scoring:
        raise S3ClassifyError(
            "AptaDB S3 policy must defer target classification and evidence scoring"
        )
    if (
        policy.sequence_leakage_matching_enabled
        or policy.target_leakage_matching_enabled
        or not policy.defer_leakage_exclusion
    ):
        raise S3ClassifyError("AptaDB S3 must not apply leakage exclusions")

    s2_policy_path = repo_root / "config" / "source_normalisation" / "aptadb.json"
    grouping_mode = "target_name_raw_plus_publication"
    if s2_policy_path.is_file():
        grouping_mode = load_aptadb_policy(s2_policy_path).group_inference_key

    canonical_rows = _read_corpus_csv(canonical_path)
    qc_rows = _read_sidecar_csv(qc_path, label="S2 QC")
    sidecar_rows = _read_sidecar_csv(sidecar_path, label="source-metadata")
    proposal_rows = _read_plain_csv(proposals_path, label="S2 constant-region proposals")
    aligned_qc = _match_sidecar_one_to_one(
        canonical_rows, qc_rows, label="S2 QC"
    )
    aligned_sidecar = _match_sidecar_one_to_one(
        canonical_rows, sidecar_rows, label="source-metadata"
    )
    proposal_index = index_constant_proposals(
        canonical_rows, proposal_rows, grouping_mode=grouping_mode
    )

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S3ClassifyError(
            f"S2 row count must be {expected_rows}; got {len(canonical_rows)}"
        )
    if expected_rows == EXPECTED_APTADB_ROWS:
        _assert_aptadb_s2_invariants(canonical_rows)

    unlinked_rows: list[dict[str, str]] = []
    if unlinked_path.is_file():
        unlinked_rows = _read_plain_csv(unlinked_path, label="unlinked aptamers")
    if expected_unlinked_rows is not None and len(unlinked_rows) != (
        expected_unlinked_rows
    ):
        raise S3ClassifyError(
            f"Unlinked aptamer count must be {expected_unlinked_rows}; "
            f"got {len(unlinked_rows)}"
        )

    stats = AptaDBS3Stats()
    stats.s2_rows = len(canonical_rows)
    stats.order_preserved = True

    s3_canonical: list[dict[str, str]] = []
    decision_rows: list[dict[str, str]] = []
    rejection_rows: list[dict[str, str]] = []
    parked_ssdna_rows: list[dict[str, str]] = []
    parked_non_protein_rows: list[dict[str, str]] = []
    local_detail_by_id: dict[str, dict[str, str]] = {}
    source_dataset = canonical_rows[0]["source_dataset"] if canonical_rows else ""
    core_by_id = {row["record_id"]: row["sequence_core"] for row in canonical_rows}

    for s2_row, qc_row, meta_row in zip(
        canonical_rows, aligned_qc, aligned_sidecar, strict=True
    ):
        classified = classify_aptadb_record(
            s2_row,
            qc_row,
            meta_row,
            policy=policy,
            proposals=proposal_index.get(s2_row["record_id"], ()),
        )
        if classified.canonical["record_id"] != s2_row["record_id"]:
            stats.order_preserved = False
            raise S3ClassifyError("S3 altered record_id or row identity")
        for column in CORPUS_COLUMNS:
            if classified.canonical[column] != s2_row[column]:
                raise S3ClassifyError(
                    f"S3 altered S2 canonical field {column!r}"
                )
        s3_canonical.append(classified.canonical)
        decision_rows.append(classified.decision)
        if classified.rejection_row is not None:
            rejection_rows.append(classified.rejection_row)
        if classified.park_row is not None:
            if classified.primary_route == PRIMARY_ROUTE_SSDNA:
                parked_ssdna_rows.append(classified.park_row)
            elif classified.primary_route == PRIMARY_ROUTE_NON_PROTEIN:
                parked_non_protein_rows.append(classified.park_row)
            else:
                raise S3ClassifyError(
                    f"Park row has unexpected primary_route {classified.primary_route}"
                )
        local_detail_by_id[classified.canonical["record_id"]] = (
            build_aptadb_local_detail_row(
                canonical=classified.canonical,
                s2_qc=qc_row,
                source_metadata=meta_row,
                decision=classified.decision,
            )
        )
        update_aptadb_stats_from_row(stats, classified)

    sampled, pool, shortfall = apply_aptadb_random_accept_audit(
        decision_rows,
        local_detail_by_id,
        seed=policy.random_seed,
        sample_size=policy.random_accept_audit_size,
    )
    stats.random_accept_audit_pool_size = pool
    stats.random_accept_audit_shortfall = shortfall
    refresh_aptadb_stats_after_audit(stats, decision_rows)

    unlinked_rejection_rows: list[dict[str, str]] = []
    unlinked_ids: set[str] = set()
    unlinked_dna = 0
    unlinked_rna = 0
    for unlinked in unlinked_rows:
        rejection = build_unlinked_rejection_row(
            unlinked, source_dataset=source_dataset
        )
        if rejection["record_id"] in unlinked_ids:
            raise S3ClassifyError(
                f"Duplicate unlinked rejection id {rejection['record_id']!r}"
            )
        unlinked_ids.add(rejection["record_id"])
        unlinked_rejection_rows.append(rejection)
        chemistry = (unlinked.get("aptamer_chemistry") or "").strip()
        if chemistry == "DNA":
            unlinked_dna += 1
        elif chemistry == "RNA":
            unlinked_rna += 1
    stats.unlinked_aptamers = len(unlinked_rows)
    stats.unlinked_missing_target_rejects = len(unlinked_rejection_rows)
    stats.unlinked_dna = unlinked_dna
    stats.unlinked_rna = unlinked_rna
    rejection_rows.extend(unlinked_rejection_rows)

    stats.s3_rows = len(s3_canonical)
    stats.unique_record_ids = len({row["record_id"] for row in s3_canonical})
    stats.unique_native_ids = len({row["native_id"] for row in s3_canonical})

    if stats.s3_rows != len(canonical_rows):
        raise S3ClassifyError("S3 must preserve every S2 row")
    if stats.unique_record_ids != len(s3_canonical):
        raise S3ClassifyError("S3 record_id values are not unique")
    if len({row["record_id"] for row in decision_rows}) != len(decision_rows):
        raise S3ClassifyError("Decision sidecar contains duplicate record_id values")

    rejected_n = stats.primary_route_counts.get(PRIMARY_ROUTE_REJECT, 0)
    parked_ssdna_n = stats.primary_route_counts.get(PRIMARY_ROUTE_SSDNA, 0)
    parked_non_protein_n = stats.primary_route_counts.get(PRIMARY_ROUTE_NON_PROTEIN, 0)
    eligible_n = stats.primary_route_counts.get(PRIMARY_ROUTE_ELIGIBLE, 0)
    if rejected_n + parked_ssdna_n + parked_non_protein_n + eligible_n != stats.s3_rows:
        raise S3ClassifyError(
            "technical_rejects + parked_ssdna + parked_non_protein + "
            "technically_eligible does not equal S3 rows"
        )
    interaction_rejects = [row for row in rejection_rows if row["stage"] == "S3"]
    if len(interaction_rejects) != rejected_n:
        raise S3ClassifyError(
            "Interaction rejection log count does not match technical_reject route"
        )
    if len(parked_ssdna_rows) != parked_ssdna_n:
        raise S3ClassifyError("Parked ssDNA count does not match parked_ssdna route")
    if len(parked_non_protein_rows) != parked_non_protein_n:
        raise S3ClassifyError(
            "Parked non-protein count does not match parked_non_protein route"
        )
    if sampled != stats.random_accept_audit_count:
        raise S3ClassifyError("Random-accept audit count mismatch")
    if stats.unlinked_missing_target_rejects != len(unlinked_rows):
        raise S3ClassifyError("Unlinked aptamers must each receive a missing_target log")
    parked_ssdna_ids = {row["record_id"] for row in parked_ssdna_rows}
    parked_non_protein_ids = {row["record_id"] for row in parked_non_protein_rows}
    if parked_ssdna_ids & parked_non_protein_ids:
        raise S3ClassifyError(
            "A record must not appear in both ssDNA and non-protein park files"
        )
    if unlinked_ids & {row["record_id"] for row in decision_rows}:
        raise S3ClassifyError("Unlinked rejection IDs collided with interaction IDs")

    for row in decision_rows:
        if not row["primary_reason"]:
            raise S3ClassifyError("Decision row missing primary_reason")

    assert_aptadb_accept_invariants(decision_rows)
    assert_aptadb_reject_park_invariants(decision_rows)

    reason_count_rows: list[dict[str, str]] = []
    combo_counts: dict[tuple[str, str], int] = {}
    for row in decision_rows:
        key = (row["proposed_decision"], row["primary_reason"])
        combo_counts[key] = combo_counts.get(key, 0) + 1
    for (decision, reason), count in sorted(combo_counts.items()):
        reason_count_rows.append(
            {
                "proposed_decision": decision,
                "primary_reason": reason,
                "record_count": str(count),
            }
        )
    if sum(int(row["record_count"]) for row in reason_count_rows) != len(decision_rows):
        raise S3ClassifyError("Reason counts do not reconcile to decision rows")

    review_rows = sorted(decision_rows, key=review_sort_key)
    local_detail_rows: list[dict[str, str]] = []
    for review_row in review_rows:
        record_id = review_row["record_id"]
        if record_id not in local_detail_by_id:
            raise S3ClassifyError(
                f"Missing local-detail row for record_id={record_id!r}"
            )
        detail = local_detail_by_id[record_id]
        if detail["sequence_core"] != core_by_id[record_id]:
            raise S3ClassifyError("CHECKPOINT-1 must not apply constant-region trims")
        if detail.get("manual_decision"):
            raise S3ClassifyError("Local-detail must not pre-fill manual_decision")
        for field_name in (
            "manual_sequence_corrected",
            "manual_molecule_type_override",
            "manual_trim_action",
        ):
            if detail.get(field_name):
                raise S3ClassifyError(
                    f"Local-detail must not pre-fill {field_name}"
                )
        local_detail_rows.append(detail)
    for review_row, detail_row in zip(review_rows, local_detail_rows, strict=True):
        if review_row["record_id"] != detail_row["record_id"]:
            raise S3ClassifyError(
                "Local-detail ordering does not match sequence-free review"
            )
        if review_row["review_batch"] != detail_row.get("review_batch", ""):
            raise S3ClassifyError("Local-detail review_batch mismatch")

    forbidden_seq_cols = {"sequence_raw", "sequence_full", "sequence_core"}
    for col in forbidden_seq_cols:
        if col in APTADB_DECISION_COLUMNS or col in APTADB_PARK_COLUMNS:
            raise S3ClassifyError(f"Sequence column leaked into sidecar schema: {col}")
    for col in ("sequence_raw", "sequence_full", "sequence_core"):
        if col not in APTADB_LOCAL_DETAIL_COLUMNS:
            raise S3ClassifyError(
                f"Local-detail schema missing required sequence column: {col}"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_canonical = output_dir / "aptadb_s3_canonical.csv"
    out_decisions = output_dir / "aptadb_s3_decisions.csv"
    out_review = output_dir / "aptadb_checkpoint1_review.csv"
    out_local_detail = output_dir / "aptadb_checkpoint1_local_detail.csv"
    out_reason_counts = output_dir / "aptadb_checkpoint1_reason_counts.csv"
    out_rejected = output_dir / "rejected_aptadb.csv"
    out_parked_ssdna = output_dir / "aptadb_s3_parked_ssdna.csv"
    out_parked_non_protein = output_dir / "aptadb_s3_parked_non_protein.csv"
    out_summary = output_dir / "aptadb_checkpoint1_summary.md"

    write_corpus_csv_atomic(out_canonical, s3_canonical)
    write_csv_atomic(out_decisions, APTADB_DECISION_COLUMNS, decision_rows)
    write_csv_atomic(out_review, APTADB_DECISION_COLUMNS, review_rows)
    write_csv_atomic(out_local_detail, APTADB_LOCAL_DETAIL_COLUMNS, local_detail_rows)
    write_csv_atomic(out_reason_counts, APTADB_REASON_COUNT_COLUMNS, reason_count_rows)
    write_csv_atomic(out_rejected, APTADB_REJECTION_COLUMNS, rejection_rows)
    write_csv_atomic(out_parked_ssdna, APTADB_PARK_COLUMNS, parked_ssdna_rows)
    write_csv_atomic(
        out_parked_non_protein, APTADB_PARK_COLUMNS, parked_non_protein_rows
    )

    s2_hash_after = _sha256_file(canonical_path)
    qc_hash_after = _sha256_file(qc_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    proposals_hash_after = _sha256_file(proposals_path)
    unlinked_hash_after = (
        _sha256_file(unlinked_path) if unlinked_path.is_file() else ""
    )
    raw_sha_after = raw_sha_before
    if check_raw:
        after_parts = []
        for name, path in raw_paths.items():
            digest = _sha256_file(path)
            if digest != EXPECTED_APTADB_RAW_SHA256[name]:
                raise S3ClassifyError(f"AptaDB raw {name} SHA-256 changed during S3")
            after_parts.append(f"{name}={digest}")
        raw_sha_after = ";".join(after_parts)
    inputs_unchanged = (
        s2_hash_before == s2_hash_after
        and qc_hash_before == qc_hash_after
        and sidecar_hash_before == sidecar_hash_after
        and proposals_hash_before == proposals_hash_after
        and unlinked_hash_before == unlinked_hash_after
        and (not check_raw or raw_sha_before == raw_sha_after)
    )
    if not inputs_unchanged:
        raise S3ClassifyError("S2/source inputs were modified during S3 execution")

    s2_integrity_ok = True
    if _sha256_file(out_canonical) != s2_hash_before:
        raise S3ClassifyError(
            "S3 canonical output is not byte-identical to S2 normalised input"
        )

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "canonical": _sha256_file(out_canonical),
            "decisions": _sha256_file(out_decisions),
            "review": _sha256_file(out_review),
            "local_detail": _sha256_file(out_local_detail),
            "reason_counts": _sha256_file(out_reason_counts),
            "rejected": _sha256_file(out_rejected),
            "parked_ssdna": _sha256_file(out_parked_ssdna),
            "parked_non_protein": _sha256_file(out_parked_non_protein),
        }
        second = run_aptadb_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=expected_rows,
            expected_unlinked_rows=expected_unlinked_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["canonical"] == _sha256_file(second.output_canonical)
            and first_hashes["decisions"] == _sha256_file(second.output_decisions)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["local_detail"]
            == _sha256_file(second.output_local_detail)
            and first_hashes["reason_counts"]
            == _sha256_file(second.output_reason_counts)
            and first_hashes["rejected"] == _sha256_file(second.output_rejected)
            and first_hashes["parked_ssdna"]
            == _sha256_file(second.output_parked_ssdna)
            and first_hashes["parked_non_protein"]
            == _sha256_file(second.output_parked_non_protein)
        )
        if not deterministic_ok:
            raise S3ClassifyError(
                "S3 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S3RunResult(
        source_key="aptadb",
        stats=stats,
        output_canonical=out_canonical,
        output_decisions=out_decisions,
        output_review=out_review,
        output_local_detail=out_local_detail,
        output_summary=out_summary,
        output_reason_counts=out_reason_counts,
        output_leakage_matches=None,
        s2_hash_before=s2_hash_before,
        s2_hash_after=s2_hash_after,
        qc_hash_before=qc_hash_before,
        qc_hash_after=qc_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        s2_integrity_ok=s2_integrity_ok,
        output_rejected=out_rejected,
        output_parks=None,
        output_parked_ssdna=out_parked_ssdna,
        output_parked_non_protein=out_parked_non_protein,
        raw_sha_before=raw_sha_before,
        raw_sha_after=raw_sha_after,
    )
    summary_text = build_aptadb_checkpoint1_summary(
        repo_root=repo_root,
        result=run_result,
        policy_path=eligibility_policy,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must not contain absolute repository paths"
        )
    if APTADB_PIPELINE_STOP_STATEMENT not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing pipeline stop statement")
    if "Evidence mapping and thresholding" not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing evidence deferral")
    _write_text_atomic(out_summary, summary_text)
    return run_result


def _assert_riboaptamer_s2_invariants(
    canonical_rows: Sequence[dict[str, str]],
) -> None:
    """Hard-fail if the RiboAptamer S2 starting invariants no longer reconcile."""
    if len(canonical_rows) != EXPECTED_RIBOAPTAMER_ROWS:
        raise S3ClassifyError(
            f"S3 input rows must be {EXPECTED_RIBOAPTAMER_ROWS}; "
            f"got {len(canonical_rows)}"
        )
    record_ids = [row["record_id"] for row in canonical_rows]
    if len(set(record_ids)) != EXPECTED_RIBOAPTAMER_ROWS:
        raise S3ClassifyError("RiboAptamer S2 record_id values are not unique")
    molecule_counts: dict[str, int] = {}
    chemistry_counts: dict[str, int] = {}
    for row in canonical_rows:
        if row.get("source_db") != "riboaptamer":
            raise S3ClassifyError("S2 row source_db must be riboaptamer")
        if row.get("source_dataset") != EXPECTED_RIBOAPTAMER_SOURCE_DATASET:
            raise S3ClassifyError(
                "S2 row source_dataset must be "
                f"{EXPECTED_RIBOAPTAMER_SOURCE_DATASET}"
            )
        if row.get("sequence_core") != row.get("sequence_full"):
            raise S3ClassifyError(
                "RiboAptamer S2 must enter S3 with sequence_core == sequence_full"
            )
        molecule = row.get("molecule_type") or "unknown"
        molecule_counts[molecule] = molecule_counts.get(molecule, 0) + 1
        chemistry = row.get("chemistry") or "unknown"
        chemistry_counts[chemistry] = chemistry_counts.get(chemistry, 0) + 1
    if molecule_counts != {"RNA": EXPECTED_RIBOAPTAMER_ROWS}:
        raise S3ClassifyError(
            f"S2 molecule_type counts drifted: {molecule_counts}"
        )
    if chemistry_counts != {"RNA": EXPECTED_RIBOAPTAMER_ROWS}:
        raise S3ClassifyError(
            f"S2 chemistry counts drifted: {chemistry_counts}"
        )


def build_riboaptamer_checkpoint1_summary(
    *,
    repo_root: Path,
    result: S3RunResult,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown CHECKPOINT-1 summary (no sequences)."""
    stats = result.stats
    if not isinstance(stats, RiboAptamerS3Stats):
        raise S3ClassifyError("RiboAptamer summary requires RiboAptamerS3Stats")

    def _count(mapping: Mapping[str, int], key: str) -> int:
        return int(mapping.get(key, 0))

    rejected = _count(stats.primary_route_counts, RIBOAPTAMER_PRIMARY_ROUTE_REJECT)
    parked_ssdna = _count(stats.primary_route_counts, RIBOAPTAMER_PRIMARY_ROUTE_SSDNA)
    eligible = _count(stats.primary_route_counts, RIBOAPTAMER_PRIMARY_ROUTE_ELIGIBLE)
    routed_sum = rejected + parked_ssdna + eligible

    lines = [
        "# RiboAptamer S3 / CHECKPOINT-1 summary",
        "",
        "## Reconciliation",
        "",
        f"- rows in = `{stats.s2_rows}`",
        f"- technical rejects = `{rejected}`",
        f"- parked ssDNA = `{parked_ssdna}`",
        f"- parked non-protein = `{stats.non_protein_parked_count}`",
        f"- technically eligible RNA = `{eligible}`",
        f"- pending human review (unique records) = "
        f"`{stats.unique_checkpoint_review_records}`",
        f"- sum of primary routes = `{routed_sum}`",
        f"- Unique record IDs: `{stats.unique_record_ids}`",
        f"- Unique native IDs: `{stats.unique_native_ids}`",
        f"- S2 order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        "",
        "Judgement-dependent records are provisional technical rejects and also",
        "enter CHECKPOINT-1. They are counted once in the reject route and once",
        "in the unique review-record count; they are not a separate disappearing",
        "bucket. Automatic-only rejects do not enter CHECKPOINT-1.",
        "",
        f"`{stats.s2_rows}` = `{rejected}` rejected + `{parked_ssdna}` parked + "
        f"`{eligible}` eligible.",
        "",
        "## Reason-priority rule",
        "",
        REASON_PRIORITY_RULE,
        "",
        "A single canonical `rejection_reason` is emitted. Overlaps are retained",
        "in `secondary_reasons`, `qc_flags`, and `checkpoint_review_reasons`.",
        "",
        "## Technical rejection breakdown (primary reason)",
        "",
        f"- `missing_sequence`: `{_count(stats.primary_reason_counts, 'missing_sequence')}`",
        f"- `length_out_of_range`: `{_count(stats.primary_reason_counts, 'length_out_of_range')}`",
        f"- `mixed_T_and_U`: `{_count(stats.primary_reason_counts, 'mixed_T_and_U')}`",
        f"- `alignment_gaps`: `{_count(stats.primary_reason_counts, 'alignment_gaps')}`",
        f"- `invalid_alphabet`: `{_count(stats.primary_reason_counts, 'invalid_alphabet')}`",
        f"- `ambiguous_bases`: `{_count(stats.primary_reason_counts, 'ambiguous_bases')}`",
        f"- `primer_like`: `{_count(stats.primary_reason_counts, 'primer_like')}`",
        f"- `library_template`: `{_count(stats.primary_reason_counts, 'library_template')}`",
        f"- `truncated_sequence`: `{_count(stats.primary_reason_counts, 'truncated_sequence')}`",
        "",
        "Condition tallies (a record may contribute to more than one):",
        "",
        f"- missing-sequence condition: `{stats.missing_sequence_count}`",
        f"- mixed T/U condition: `{stats.mixed_t_u_count}`",
        f"- alignment-gaps condition: `{stats.alignment_gaps_count}`",
        f"- invalid-alphabet condition: `{stats.invalid_alphabet_count}`",
        f"- ambiguous-bases condition: `{stats.ambiguous_bases_count}`",
        f"- length-out-of-range condition: `{stats.length_out_of_range_count}`",
        f"  - actual core `<20`: `{stats.length_below_min_count}`",
        f"  - actual core `>100`: `{stats.length_above_max_count}`",
        f"- primer_like condition: `{stats.primer_like_count}`",
        f"- library_template condition: `{stats.library_template_count}`",
        f"- truncated_sequence condition: `{stats.truncated_sequence_count}`",
        "",
        "## Overlaps",
        "",
        f"- invalid alphabet AND length out of range: `{stats.invalid_and_length_count}`",
        f"- truncated AND invalid alphabet: `{stats.truncated_and_invalid_count}`",
        f"- truncated AND alignment gaps: `{stats.truncated_and_alignment_count}`",
        f"- ambiguous bases AND length out of range: `{stats.ambiguous_and_length_count}`",
        f"- length-boundary records with another technical failure: "
        f"`{stats.boundary_with_other_technical_count}`",
        f"- trim-pushed length out of range: `{stats.trim_pushed_length_count}`",
        f"- known-motif detections inside 20–100 nt: "
        f"`{stats.known_motif_in_length_window_count}`",
        f"- records with more than one reason: `{stats.multiple_reasons_count}`",
        "",
        "Length is computed from `len(sequence_core)`, not from S2",
        "`core_above_max_length` / `core_below_min_length` flags. Invalid-alphabet",
        "rows that returned early from the S2 normaliser are still length-checked.",
        "",
        "## Parking",
        "",
        f"- parked ssDNA = `{parked_ssdna}`",
        f"- parked non-protein (source Type unused) = `{stats.non_protein_parked_count}`",
        f"- source Type used for parking: `{str(stats.source_type_used_for_parking).lower()}`",
        "",
        "Source `Type` is review-context metadata only. Empty `target_name_raw`",
        "does not reject. Canonical target type is not populated.",
        "",
        "## CHECKPOINT-1",
        "",
        f"- unique review records: `{stats.unique_checkpoint_review_records}`",
        f"- judgement-dependent technical records: "
        f"`{stats.judgement_dependent_review_count}`",
        f"- constant-proposal / known-motif records in review: "
        f"`{stats.constant_review_count}`",
        f"- known-motif proposal records: `{stats.known_motif_proposal_record_count}`",
        f"- group-consensus proposal records: "
        f"`{stats.group_consensus_proposal_record_count}`",
        f"- trim-induced length failures presented: `{stats.trim_pushed_length_count}`",
        f"- boundary-length records in review: `{stats.boundary_review_count}`",
        f"- lower-boundary (20–25 nt) condition: `{stats.boundary_low_count}`",
        f"- upper-boundary (90–100 nt) condition: `{stats.boundary_high_count}`",
        f"- random kept audit sampled: `{stats.random_accept_audit_count}`",
        f"- random kept audit pool: `{stats.random_accept_audit_pool_size}`",
        f"- random kept audit shortfall: `{stats.random_accept_audit_shortfall}`",
        "",
        "Overlapping review reasons share one review row. A record is not",
        "duplicated across batches; the primary batch follows judgement >",
        "constant-region > length-boundary > random-kept-audit.",
        "",
        "### Counts by checkpoint review reason",
        "",
    ]
    if stats.checkpoint_review_reason_counts:
        for name, count in _count_sorted(stats.checkpoint_review_reason_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")

    lines.extend(["", "### Counts by review batch", ""])
    for batch in (
        "01_judgement_dependent_technical",
        "02_constant_region_proposal",
        "03_length_boundary",
        "04_random_kept_audit",
    ):
        lines.append(f"- `{batch}`: `{_count(stats.review_batch_counts, batch)}`")

    lines.extend(
        [
            "",
            "## Constant-region / T7 status",
            "",
            "- Group-wise constant-region inference was disabled for the",
            "  RiboAptamer S2/S3 run.",
            "- Known T7 motif detections are unapplied proposals.",
            "- `sequence_core` has not been trimmed.",
            "- Detection confidence is the configured approved-motif library",
            "  (`t7_promoter_minimal`), not a medium-confidence consensus.",
            f"- known-motif proposal count: `{stats.known_motif_proposal_record_count}`",
            f"- group-consensus proposal count: "
            f"`{stats.group_consensus_proposal_record_count}`",
            "",
            "## Deferred to S4 / CHECKPOINT-2",
            "",
            "Target identity, canonical target type, source `Type` protein vs",
            "non-protein routing, evidence/affinity scoring, the E4 threshold,",
            "and leakage exclusion remain deferred. This is an architecture",
            "decision, not an accidental omission.",
            "",
            "- Target type inferred: `no`",
            "- Evidence scored: `no`",
            "- Leakage exclusions applied: `no`",
            "- Constant-region proposals applied: `no`",
            "- Human CHECKPOINT-1 decisions applied: `no`",
            "- S4 started: `no`",
            "",
            "## Integrity",
            "",
            f"- S2 canonical hash before: `{result.s2_hash_before}`",
            f"- S2 canonical hash after: `{result.s2_hash_after}`",
            f"- S2 QC hash before: `{result.qc_hash_before}`",
            f"- S2 QC hash after: `{result.qc_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            f"- S2 input integrity: "
            f"`{'pass' if result.s2_integrity_ok else 'fail'}`",
            f"- Inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            f"- Raw SHA-256 before: `{result.raw_sha_before or 'not_checked'}`",
            f"- Raw SHA-256 after: `{result.raw_sha_after or 'not_checked'}`",
            "",
            "## Inputs",
            "",
            f"- Eligibility policy: `{_relative_display(policy_path, repo_root)}`",
            "",
            "## Outputs",
            "",
            f"- Canonical: `{_relative_display(result.output_canonical, repo_root)}`",
            f"- Decisions: `{_relative_display(result.output_decisions, repo_root)}`",
            f"- Checkpoint review (sequence-free index of all rows): "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Checkpoint local detail (sequence-bearing scientific review): "
            f"`{_relative_display(result.output_local_detail, repo_root)}`",
            f"- Reason counts: "
            f"`{_relative_display(result.output_reason_counts, repo_root)}`",
        ]
    )
    if result.output_rejected is not None:
        lines.append(
            f"- Rejection log: `{_relative_display(result.output_rejected, repo_root)}`"
        )
    if result.output_parked_ssdna is not None:
        lines.append(
            f"- Parked ssDNA: "
            f"`{_relative_display(result.output_parked_ssdna, repo_root)}`"
        )
    lines.extend(
        [
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            "## Local-detail warning",
            "",
            "WARNING: `riboaptamer_checkpoint1_local_detail.csv` and",
            "`rejected_riboaptamer.csv` contain source sequences. They must remain",
            "beneath ignored `data/` and must never be staged or tracked.",
            "",
            "## Pipeline stop",
            "",
            RIBOAPTAMER_PIPELINE_STOP_STATEMENT,
            "",
            "CHECKPOINT-1 generated = yes",
            "CHECKPOINT-1 human decisions applied = no",
            "records authorised_for_s4 = 0",
            "",
        ]
    )
    return "\n".join(lines)


def run_riboaptamer_s3(
    *,
    repo_root: Path,
    input_dir: Path,
    source_metadata_dir: Path,
    eligibility_policy: Path,
    output_dir: Path,
    expected_rows: int | None = EXPECTED_RIBOAPTAMER_ROWS,
    check_deterministic_rerun: bool = False,
) -> S3RunResult:
    """Execute RiboAptamer S3 technical eligibility and CHECKPOINT-1."""
    repo_root = repo_root.resolve()
    input_dir = (
        input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    ).resolve()
    source_metadata_dir = (
        source_metadata_dir
        if source_metadata_dir.is_absolute()
        else (repo_root / source_metadata_dir)
    ).resolve()
    eligibility_policy = (
        eligibility_policy
        if eligibility_policy.is_absolute()
        else (repo_root / eligibility_policy)
    ).resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    canonical_path = input_dir / "riboaptamer_normalised.csv"
    qc_path = input_dir / "riboaptamer_s2_qc.csv"
    sidecar_path = source_metadata_dir / "riboaptamer_source_metadata.csv"
    proposals_path = input_dir / "detected_constants_riboaptamer.csv"
    for path, label in (
        (canonical_path, "S2 canonical"),
        (qc_path, "S2 QC"),
        (sidecar_path, "source-metadata"),
        (proposals_path, "S2 constant-region proposals"),
    ):
        if not path.is_file():
            raise S3ClassifyError(f"Missing {label} input: {path.name}")

    raw_path = repo_root / "data" / "raw" / "riboaptamer" / "all_sequences_509_rows.csv"
    raw_sha_before = ""
    check_raw = expected_rows == EXPECTED_RIBOAPTAMER_ROWS
    if check_raw:
        if not raw_path.is_file():
            raise S3ClassifyError("Missing registered RiboAptamer raw file")
        raw_sha_before = _sha256_file(raw_path)
        if raw_sha_before != EXPECTED_RIBOAPTAMER_RAW_SHA256:
            raise S3ClassifyError(
                "RiboAptamer raw SHA-256 does not match registry expectation"
            )

    s2_hash_before = _sha256_file(canonical_path)
    qc_hash_before = _sha256_file(qc_path)
    sidecar_hash_before = _sha256_file(sidecar_path)
    proposals_hash_before = _sha256_file(proposals_path)

    policy = load_eligibility_policy(eligibility_policy)
    if policy.source_key != "riboaptamer":
        raise S3ClassifyError(
            f"Eligibility policy source_key must be riboaptamer; "
            f"got {policy.source_key!r}"
        )
    if not policy.defer_target_classification or not policy.defer_evidence_scoring:
        raise S3ClassifyError(
            "RiboAptamer S3 policy must defer target classification and "
            "evidence scoring"
        )
    if (
        policy.sequence_leakage_matching_enabled
        or policy.target_leakage_matching_enabled
        or not policy.defer_leakage_exclusion
    ):
        raise S3ClassifyError("RiboAptamer S3 must not apply leakage exclusions")

    canonical_rows = _read_corpus_csv(canonical_path)
    qc_rows = _read_sidecar_csv(qc_path, label="S2 QC")
    sidecar_rows = _read_sidecar_csv(sidecar_path, label="source-metadata")
    proposal_rows = _read_plain_csv(proposals_path, label="S2 constant-region proposals")
    aligned_qc = _match_sidecar_one_to_one(
        canonical_rows, qc_rows, label="S2 QC"
    )
    aligned_sidecar = _match_sidecar_one_to_one(
        canonical_rows, sidecar_rows, label="source-metadata"
    )
    proposal_index = index_riboaptamer_constant_proposals(
        canonical_rows, proposal_rows
    )

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S3ClassifyError(
            f"S2 row count must be {expected_rows}; got {len(canonical_rows)}"
        )
    if expected_rows == EXPECTED_RIBOAPTAMER_ROWS:
        _assert_riboaptamer_s2_invariants(canonical_rows)

    stats = RiboAptamerS3Stats()
    stats.s2_rows = len(canonical_rows)
    stats.order_preserved = True
    stats.group_inference_disabled = True
    stats.source_type_used_for_parking = False

    s3_canonical: list[dict[str, str]] = []
    decision_rows: list[dict[str, str]] = []
    rejection_rows: list[dict[str, str]] = []
    parked_ssdna_rows: list[dict[str, str]] = []
    local_detail_by_id: dict[str, dict[str, str]] = {}
    core_by_id = {row["record_id"]: row["sequence_core"] for row in canonical_rows}

    for s2_row, qc_row, meta_row in zip(
        canonical_rows, aligned_qc, aligned_sidecar, strict=True
    ):
        classified = classify_riboaptamer_record(
            s2_row,
            qc_row,
            meta_row,
            policy=policy,
            proposals=proposal_index.get(s2_row["record_id"], ()),
        )
        if classified.canonical["record_id"] != s2_row["record_id"]:
            stats.order_preserved = False
            raise S3ClassifyError("S3 altered record_id or row identity")
        for column in CORPUS_COLUMNS:
            if classified.canonical[column] != s2_row[column]:
                raise S3ClassifyError(
                    f"S3 altered S2 canonical field {column!r}"
                )
        s3_canonical.append(classified.canonical)
        decision_rows.append(classified.decision)
        if classified.rejection_row is not None:
            rejection_rows.append(classified.rejection_row)
        if classified.park_row is not None:
            raise S3ClassifyError(
                "RiboAptamer S3 must not emit park rows under the RNA contract"
            )
        local_detail_by_id[classified.canonical["record_id"]] = (
            build_riboaptamer_local_detail_row(
                canonical=classified.canonical,
                s2_qc=qc_row,
                source_metadata=meta_row,
                decision=classified.decision,
            )
        )
        update_riboaptamer_stats_from_row(stats, classified)

    sampled, pool, shortfall = apply_riboaptamer_random_accept_audit(
        decision_rows,
        local_detail_by_id,
        seed=policy.random_seed,
        sample_size=policy.random_accept_audit_size,
    )
    stats.random_accept_audit_pool_size = pool
    stats.random_accept_audit_shortfall = shortfall
    refresh_riboaptamer_stats_after_audit(stats, decision_rows)

    stats.s3_rows = len(s3_canonical)
    stats.unique_record_ids = len({row["record_id"] for row in s3_canonical})
    stats.unique_native_ids = len({row["native_id"] for row in s3_canonical})

    if stats.s3_rows != len(canonical_rows):
        raise S3ClassifyError("S3 must preserve every S2 row")
    if stats.unique_record_ids != len(s3_canonical):
        raise S3ClassifyError("S3 record_id values are not unique")
    if len({row["record_id"] for row in decision_rows}) != len(decision_rows):
        raise S3ClassifyError("Decision sidecar contains duplicate record_id values")

    rejected_n = stats.primary_route_counts.get(RIBOAPTAMER_PRIMARY_ROUTE_REJECT, 0)
    parked_ssdna_n = stats.primary_route_counts.get(RIBOAPTAMER_PRIMARY_ROUTE_SSDNA, 0)
    eligible_n = stats.primary_route_counts.get(RIBOAPTAMER_PRIMARY_ROUTE_ELIGIBLE, 0)
    if rejected_n + parked_ssdna_n + eligible_n != stats.s3_rows:
        raise S3ClassifyError(
            "technical_rejects + parked_ssdna + technically_eligible "
            "does not equal S3 rows"
        )
    if len(rejection_rows) != rejected_n:
        raise S3ClassifyError(
            "Rejection log count does not match technical_reject route"
        )
    if parked_ssdna_n != 0 or parked_ssdna_rows:
        raise S3ClassifyError("RiboAptamer S3 ssDNA parking must remain zero")
    if stats.non_protein_parked_count != 0:
        raise S3ClassifyError("RiboAptamer S3 must not park from source Type")
    if sampled != stats.random_accept_audit_count:
        raise S3ClassifyError("Random-accept audit count mismatch")
    if stats.trim_pushed_length_count != 0:
        raise S3ClassifyError(
            "RiboAptamer S3 unexpectedly found trim-pushed length failures"
        )
    if stats.group_consensus_proposal_record_count != 0:
        raise S3ClassifyError(
            "RiboAptamer S3 unexpectedly found group-consensus proposals"
        )

    for row in decision_rows:
        if not row["primary_reason"]:
            raise S3ClassifyError("Decision row missing primary_reason")
        if row.get("primary_reason") == "missing_target":
            raise S3ClassifyError("RiboAptamer S3 must not reject missing_target")

    assert_riboaptamer_accept_invariants(decision_rows)
    assert_riboaptamer_reject_park_invariants(decision_rows)

    reason_count_rows: list[dict[str, str]] = []
    combo_counts: dict[tuple[str, str], int] = {}
    for row in decision_rows:
        key = (row["proposed_decision"], row["primary_reason"])
        combo_counts[key] = combo_counts.get(key, 0) + 1
    for (decision, reason), count in sorted(combo_counts.items()):
        reason_count_rows.append(
            {
                "proposed_decision": decision,
                "primary_reason": reason,
                "record_count": str(count),
            }
        )
    if sum(int(row["record_count"]) for row in reason_count_rows) != len(decision_rows):
        raise S3ClassifyError("Reason counts do not reconcile to decision rows")

    review_rows = sorted(decision_rows, key=review_sort_key)
    local_detail_rows: list[dict[str, str]] = []
    for review_row in review_rows:
        record_id = review_row["record_id"]
        if record_id not in local_detail_by_id:
            raise S3ClassifyError(
                f"Missing local-detail row for record_id={record_id!r}"
            )
        detail = local_detail_by_id[record_id]
        if detail["sequence_core"] != core_by_id[record_id]:
            raise S3ClassifyError("CHECKPOINT-1 must not apply constant-region trims")
        if detail.get("manual_decision"):
            raise S3ClassifyError("Local-detail must not pre-fill manual_decision")
        for field_name in (
            "manual_sequence_corrected",
            "manual_molecule_type_override",
            "manual_trim_action",
        ):
            if detail.get(field_name):
                raise S3ClassifyError(
                    f"Local-detail must not pre-fill {field_name}"
                )
        local_detail_rows.append(detail)
    for review_row, detail_row in zip(review_rows, local_detail_rows, strict=True):
        if review_row["record_id"] != detail_row["record_id"]:
            raise S3ClassifyError(
                "Local-detail ordering does not match sequence-free review"
            )
        if review_row["review_batch"] != detail_row.get("review_batch", ""):
            raise S3ClassifyError("Local-detail review_batch mismatch")

    forbidden_seq_cols = {"sequence_raw", "sequence_full", "sequence_core"}
    for col in forbidden_seq_cols:
        if col in RIBOAPTAMER_DECISION_COLUMNS or col in RIBOAPTAMER_PARK_COLUMNS:
            raise S3ClassifyError(f"Sequence column leaked into sidecar schema: {col}")
    for col in ("sequence_raw", "sequence_full", "sequence_core"):
        if col not in RIBOAPTAMER_LOCAL_DETAIL_COLUMNS:
            raise S3ClassifyError(
                f"Local-detail schema missing required sequence column: {col}"
            )

    review_ids = [
        row["record_id"]
        for row in review_rows
        if row.get("manual_review_required") == "true"
    ]
    if len(review_ids) != len(set(review_ids)):
        raise S3ClassifyError("CHECKPOINT-1 review rows are duplicated")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_canonical = output_dir / "riboaptamer_s3_canonical.csv"
    out_decisions = output_dir / "riboaptamer_s3_decisions.csv"
    out_review = output_dir / "riboaptamer_checkpoint1_review.csv"
    out_local_detail = output_dir / "riboaptamer_checkpoint1_local_detail.csv"
    out_reason_counts = output_dir / "riboaptamer_checkpoint1_reason_counts.csv"
    out_rejected = output_dir / "rejected_riboaptamer.csv"
    out_parked_ssdna = output_dir / "riboaptamer_s3_parked_ssdna.csv"
    out_summary = output_dir / "riboaptamer_checkpoint1_summary.md"

    write_corpus_csv_atomic(out_canonical, s3_canonical)
    write_csv_atomic(out_decisions, RIBOAPTAMER_DECISION_COLUMNS, decision_rows)
    write_csv_atomic(out_review, RIBOAPTAMER_DECISION_COLUMNS, review_rows)
    write_csv_atomic(
        out_local_detail, RIBOAPTAMER_LOCAL_DETAIL_COLUMNS, local_detail_rows
    )
    write_csv_atomic(
        out_reason_counts, RIBOAPTAMER_REASON_COUNT_COLUMNS, reason_count_rows
    )
    write_csv_atomic(out_rejected, RIBOAPTAMER_REJECTION_COLUMNS, rejection_rows)
    write_csv_atomic(out_parked_ssdna, RIBOAPTAMER_PARK_COLUMNS, parked_ssdna_rows)

    s2_hash_after = _sha256_file(canonical_path)
    qc_hash_after = _sha256_file(qc_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    proposals_hash_after = _sha256_file(proposals_path)
    raw_sha_after = raw_sha_before
    if check_raw:
        raw_sha_after = _sha256_file(raw_path)
        if raw_sha_after != EXPECTED_RIBOAPTAMER_RAW_SHA256:
            raise S3ClassifyError("RiboAptamer raw SHA-256 changed during S3")
    inputs_unchanged = (
        s2_hash_before == s2_hash_after
        and qc_hash_before == qc_hash_after
        and sidecar_hash_before == sidecar_hash_after
        and proposals_hash_before == proposals_hash_after
        and (not check_raw or raw_sha_before == raw_sha_after)
    )
    if not inputs_unchanged:
        raise S3ClassifyError("S2/source inputs were modified during S3 execution")

    s2_integrity_ok = True
    if _sha256_file(out_canonical) != s2_hash_before:
        raise S3ClassifyError(
            "S3 canonical output is not byte-identical to S2 normalised input"
        )

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "canonical": _sha256_file(out_canonical),
            "decisions": _sha256_file(out_decisions),
            "review": _sha256_file(out_review),
            "local_detail": _sha256_file(out_local_detail),
            "reason_counts": _sha256_file(out_reason_counts),
            "rejected": _sha256_file(out_rejected),
            "parked_ssdna": _sha256_file(out_parked_ssdna),
        }
        second = run_riboaptamer_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        second_hashes = {
            "canonical": _sha256_file(second.output_canonical),
            "decisions": _sha256_file(second.output_decisions),
            "review": _sha256_file(second.output_review),
            "local_detail": _sha256_file(second.output_local_detail),
            "reason_counts": _sha256_file(second.output_reason_counts),
            "rejected": _sha256_file(second.output_rejected),
            "parked_ssdna": _sha256_file(second.output_parked_ssdna),
        }
        deterministic_ok = first_hashes == second_hashes
        if not deterministic_ok:
            raise S3ClassifyError(
                "S3 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S3RunResult(
        source_key="riboaptamer",
        stats=stats,
        output_canonical=out_canonical,
        output_decisions=out_decisions,
        output_review=out_review,
        output_local_detail=out_local_detail,
        output_summary=out_summary,
        output_reason_counts=out_reason_counts,
        output_leakage_matches=None,
        s2_hash_before=s2_hash_before,
        s2_hash_after=s2_hash_after,
        qc_hash_before=qc_hash_before,
        qc_hash_after=qc_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        s2_integrity_ok=s2_integrity_ok,
        output_rejected=out_rejected,
        output_parks=None,
        output_parked_ssdna=out_parked_ssdna,
        output_parked_non_protein=None,
        raw_sha_before=raw_sha_before,
        raw_sha_after=raw_sha_after,
    )
    summary_text = build_riboaptamer_checkpoint1_summary(
        repo_root=repo_root,
        result=run_result,
        policy_path=eligibility_policy,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must not contain absolute repository paths"
        )
    if RIBOAPTAMER_PIPELINE_STOP_STATEMENT not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing pipeline stop statement")
    if "group-wise constant-region inference was disabled" not in summary_text.lower():
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must state that group-wise inference was disabled"
        )
    if "Evidence scored" not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing evidence deferral")
    _write_text_atomic(out_summary, summary_text)
    return run_result


def _assert_aptaindex_s2_invariants(
    canonical_rows: Sequence[dict[str, str]],
) -> None:
    """Hard-fail if the AptaIndex S2 starting invariants no longer reconcile."""
    if len(canonical_rows) != EXPECTED_APTAINDEX_ROWS:
        raise S3ClassifyError(
            f"S3 input rows must be {EXPECTED_APTAINDEX_ROWS}; "
            f"got {len(canonical_rows)}"
        )
    record_ids = [row["record_id"] for row in canonical_rows]
    if len(set(record_ids)) != EXPECTED_APTAINDEX_ROWS:
        raise S3ClassifyError("AptaIndex S2 record_id values are not unique")
    for row in canonical_rows:
        if row.get("source_db") != "aptaindex":
            raise S3ClassifyError("S2 row source_db must be aptaindex")
        if row.get("source_dataset") != EXPECTED_APTAINDEX_SOURCE_DATASET:
            raise S3ClassifyError(
                "S2 row source_dataset must be "
                f"{EXPECTED_APTAINDEX_SOURCE_DATASET}"
            )
        if row.get("sequence_core") != row.get("sequence_full"):
            raise S3ClassifyError(
                "AptaIndex S2 must enter S3 with sequence_core == sequence_full"
            )
        for field_name in (
            "target_type",
            "target_name",
            "binding_evidence_score",
            "affinity_value",
            "affinity_units",
            "cluster_id",
            "partition",
        ):
            if (row.get(field_name) or "") != "":
                raise S3ClassifyError(
                    f"S2 canonical unexpectedly populated {field_name}"
                )


def build_aptaindex_checkpoint1_summary(
    *,
    repo_root: Path,
    result: S3RunResult,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown CHECKPOINT-1 summary (no sequences)."""
    stats = result.stats
    if not isinstance(stats, AptaIndexS3Stats):
        raise S3ClassifyError("AptaIndex summary requires AptaIndexS3Stats")

    def _count(mapping: Mapping[str, int], key: str) -> int:
        return int(mapping.get(key, 0))

    rejected = _count(stats.primary_route_counts, APTAINDEX_PRIMARY_ROUTE_REJECT)
    parked_ssdna = _count(stats.primary_route_counts, APTAINDEX_PRIMARY_ROUTE_SSDNA)
    parked_chemistry = _count(
        stats.primary_route_counts, APTAINDEX_PRIMARY_ROUTE_CHEMISTRY_REVIEW
    )
    eligible = _count(stats.primary_route_counts, APTAINDEX_PRIMARY_ROUTE_ELIGIBLE)
    routed_sum = rejected + parked_ssdna + parked_chemistry + eligible

    lines = [
        "# AptaIndex S3 / CHECKPOINT-1 summary",
        "",
        "## Reconciliation",
        "",
        f"- rows in = `{stats.s2_rows}`",
        f"- technically eligible RNA/2F-RNA = `{eligible}`",
        f"- parked ssDNA = `{parked_ssdna}`",
        f"- parked chemistry-review = `{parked_chemistry}`",
        f"- automatically rejected = `{rejected}`",
        f"- peptide / non-nucleic-acid molecules = `{stats.peptide_molecule_count}`",
        f"- unique CHECKPOINT-1 review records = "
        f"`{stats.unique_checkpoint_review_records}`",
        f"- sum of primary routes = `{routed_sum}`",
        f"- Unique record IDs: `{stats.unique_record_ids}`",
        f"- Unique native IDs: `{stats.unique_native_ids}`",
        f"- S2 order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        "",
        "Chemistry-review parks and judgement-dependent mixed T/U rejects also",
        "enter CHECKPOINT-1. They are counted once in their primary route and",
        "once in the unique review-record count. Automatic-only rejects",
        "(missing sequence, peptide molecules, ordinary length-out-of-range,",
        "automatic alphabet failures without chemistry judgement) do not enter",
        "CHECKPOINT-1.",
        "",
        f"`{stats.s2_rows}` = `{eligible}` eligible + `{parked_ssdna}` parked "
        f"ssDNA + `{parked_chemistry}` chemistry-review parks + `{rejected}` "
        "rejected.",
        "",
        "## Technical rejection breakdown (primary reason)",
        "",
        f"- `missing_sequence`: `{_count(stats.primary_reason_counts, 'missing_sequence')}`",
        f"- `non_nucleic_acid_molecule`: "
        f"`{_count(stats.primary_reason_counts, 'non_nucleic_acid_molecule')}`",
        f"- `length_out_of_range`: `{_count(stats.primary_reason_counts, 'length_out_of_range')}`",
        f"- `mixed_T_and_U`: `{_count(stats.primary_reason_counts, 'mixed_T_and_U')}`",
        f"- `alignment_gaps`: `{_count(stats.primary_reason_counts, 'alignment_gaps')}`",
        f"- `invalid_alphabet`: `{_count(stats.primary_reason_counts, 'invalid_alphabet')}`",
        f"- `ambiguous_bases`: `{_count(stats.primary_reason_counts, 'ambiguous_bases')}`",
        f"- `missing_target`: `{_count(stats.primary_reason_counts, 'missing_target')}`",
        "",
        "Condition tallies (a record may contribute to more than one):",
        "",
        f"- missing-sequence condition: `{stats.missing_sequence_count}`",
        f"- non-nucleic-acid peptide molecule: `{stats.non_nucleic_acid_count}`",
        f"- mixed T/U condition: `{stats.mixed_t_u_count}`",
        f"- mixed T/U in CHECKPOINT-1: `{stats.mixed_t_u_review_count}`",
        f"- alignment-gaps condition: `{stats.alignment_gaps_count}`",
        f"- invalid-alphabet condition: `{stats.invalid_alphabet_count}`",
        f"- ambiguous-bases condition: `{stats.ambiguous_bases_count}`",
        f"- length-out-of-range condition: `{stats.length_out_of_range_count}`",
        f"- length <20: `{stats.length_below_min_count}`",
        f"- length >100: `{stats.length_above_max_count}`",
        "",
        "## Parking / excluded categories",
        "",
        f"- parked ssDNA = `{parked_ssdna}`",
        f"- parked chemistry-review = `{parked_chemistry}`",
        f"- peptide molecules rejected as `non_nucleic_acid_molecule` = "
        f"`{stats.peptide_molecule_count}`",
        f"- non-protein target parks = `{stats.non_protein_parked_count}`",
        "- Peptide molecules are source Type Peptide aptamers, not peptide",
        "  targets. They are rejected with an explicit non-nucleic-acid reason,",
        "  not parked as `non_protein_target_parked` or `ssdna_parked`, and not",
        "  labelled `invalid_alphabet`.",
        "",
        "## Target handling (deferred)",
        "",
        f"- blank raw Target count = `{stats.missing_target_raw_count}`",
        f"- S3 `missing_target` rejects = `{stats.missing_target_rejected_count}`",
        f"- nonempty `sequence_core` values with >1 distinct raw Target = "
        f"`{stats.multi_target_sequence_count}`",
        f"- nonempty `sequence_raw` values with >1 distinct raw Target = "
        f"`{stats.multi_target_raw_sequence_count}`",
        f"- treated as S3 target conflict: "
        f"`{'yes' if stats.multi_target_treated_as_conflict else 'no'}`",
        "- The preflight figure of 25 counted raw Sequence strings. After S2",
        "  parsing, distinct notations can collapse onto one nucleotide core,",
        "  so the canonical-core count can differ. Neither count is an S3",
        "  error under the `(sequence, target)` grain.",
        f"- Target Type Peptide without peptide molecule = "
        f"`{stats.peptide_target_type_alone_count}`",
        "- Blank Target is deferred to global S4 because AptaIndex has an",
        "  explicit Target column but the current S3 architecture for",
        "  classified source rows (AptaDB interaction stream / UTexas /",
        "  RiboAptamer) does not auto-reject blank `target_name_raw`.",
        "- Protein/non-protein Target Type routing is deferred to global S4.",
        f"- Target canonicalised: `{stats.target_canonicalised_count}`",
        f"- Evidence scored: `{stats.evidence_scored_count}`",
        f"- Affinity normalised: `{stats.affinity_normalised_count}`",
        "",
        "## Source Type disposition",
        "",
    ]
    for name, count in _count_sorted(stats.source_type_counts):
        label = name if name != "(blank)" else "(blank)"
        lines.append(f"- `{label}`: `{count}`")
    lines.extend(["", "### Source Type by primary route", ""])
    lines.extend(_nested_count_lines(stats.source_type_by_route))

    lines.extend(
        [
            "",
            "## CHECKPOINT-1",
            "",
            f"- unique review records: `{stats.unique_checkpoint_review_records}`",
            f"- judgement-dependent records: "
            f"`{stats.judgement_dependent_review_count}`",
            f"- unsupported chemical notation: `{stats.unsupported_notation_count}`",
            f"- L-RNA review condition: `{stats.l_rna_review_count}`",
            f"- L-DNA review condition: `{stats.l_dna_review_count}`",
            f"- Chimeric review condition: `{stats.chimeric_review_count}`",
            f"- Type/token disagreement: `{stats.type_token_disagreement_count}`",
            f"- constant-proposal records in review: `{stats.constant_review_count}`",
            f"- known-motif proposals: `{stats.known_motif_proposal_record_count}`",
            f"- group-consensus proposals: "
            f"`{stats.group_consensus_proposal_record_count}`",
            f"- boundary-length records in review: `{stats.boundary_review_count}`",
            f"- lower-boundary (20–25 nt) condition: `{stats.boundary_low_count}`",
            f"- upper-boundary (90–100 nt) condition: `{stats.boundary_high_count}`",
            f"- random kept audit sampled: `{stats.random_accept_audit_count}`",
            f"- random kept audit pool: `{stats.random_accept_audit_pool_size}`",
            f"- random kept audit shortfall: `{stats.random_accept_audit_shortfall}`",
            "",
            "One review row per record. Higher-priority batches win; all",
            "applicable `checkpoint_review_reasons` are preserved.",
            "",
            "### Counts by checkpoint review reason",
            "",
        ]
    )
    if stats.checkpoint_review_reason_counts:
        for name, count in _count_sorted(stats.checkpoint_review_reason_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")

    lines.extend(["", "### Counts by judgement subcategory", ""])
    if stats.judgement_subcategory_counts:
        for name, count in _count_sorted(stats.judgement_subcategory_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")

    lines.extend(["", "### Counts by review batch", ""])
    for batch in (
        "01_judgement_dependent_technical",
        "02_constant_region_proposal",
        "03_length_boundary",
        "04_random_kept_audit",
    ):
        lines.append(f"- `{batch}`: `{_count(stats.review_batch_counts, batch)}`")

    lines.extend(
        [
            "",
            "## Mixed T/U policy",
            "",
            "Shared eligibility still classifies mixed T/U after chemical",
            "parsing (`mixed_T_and_U`). Mixed T/U rows enter CHECKPOINT-1:",
            "chemistry-review when a higher-precedence chemistry reason is",
            "present, otherwise a judgement-dependent `mixed_T_and_U` reject.",
            "They are not automatic-only rejects. No silent T↔U conversion is",
            "applied at S3.",
            "",
            "## Deferred to global S4",
            "",
            "Target canonicalisation, Target Type protein/non-protein routing,",
            "evidence ladder (E1–E5), affinity numeric normalisation, leakage",
            "exclusion, cross-source deduplication, clustering, balancing and",
            "FT/REF/EVAL partitioning remain deferred.",
            "",
            "- Target type inferred: `no`",
            "- Evidence scored: `no`",
            "- Affinity normalised: `no`",
            "- Leakage exclusions applied: `no`",
            "- Constant-region proposals applied: `no`",
            "- Human CHECKPOINT-1 decisions applied: `no`",
            "- S4 started: `no`",
            "- Group-wise constant-region inference was disabled",
            "",
            "## Integrity",
            "",
            f"- S2 canonical hash before: `{result.s2_hash_before}`",
            f"- S2 canonical hash after: `{result.s2_hash_after}`",
            f"- S2 QC hash before: `{result.qc_hash_before}`",
            f"- S2 QC hash after: `{result.qc_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            f"- S2 input integrity: "
            f"`{'pass' if result.s2_integrity_ok else 'fail'}`",
            f"- Inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            f"- Raw SHA-256 before: `{result.raw_sha_before or 'not_checked'}`",
            f"- Raw SHA-256 after: `{result.raw_sha_after or 'not_checked'}`",
            "",
            "## Inputs",
            "",
            f"- Eligibility policy: `{_relative_display(policy_path, repo_root)}`",
            "",
            "## Outputs",
            "",
            f"- Canonical: `{_relative_display(result.output_canonical, repo_root)}`",
            f"- Decisions: `{_relative_display(result.output_decisions, repo_root)}`",
            f"- Checkpoint review (sequence-free index of all rows): "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Checkpoint local detail (sequence-bearing scientific review): "
            f"`{_relative_display(result.output_local_detail, repo_root)}`",
            f"- Reason counts: "
            f"`{_relative_display(result.output_reason_counts, repo_root)}`",
        ]
    )
    if result.output_rejected is not None:
        lines.append(
            f"- Rejection log: `{_relative_display(result.output_rejected, repo_root)}`"
        )
    if result.output_parked_ssdna is not None:
        lines.append(
            f"- Parked ssDNA: "
            f"`{_relative_display(result.output_parked_ssdna, repo_root)}`"
        )
    if result.output_parks is not None:
        lines.append(
            f"- Chemistry-review parks: "
            f"`{_relative_display(result.output_parks, repo_root)}`"
        )
    lines.extend(
        [
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            "WARNING: `aptaindex_checkpoint1_local_detail.csv` and",
            "`rejected_aptaindex.csv` contain source sequences. They must remain",
            "untracked under `data/`. AptaIndex is restricted.",
            "",
            APTAINDEX_PIPELINE_STOP_STATEMENT,
        ]
    )
    return "\n".join(lines) + "\n"


def run_aptaindex_s3(
    *,
    repo_root: Path,
    input_dir: Path,
    source_metadata_dir: Path,
    eligibility_policy: Path,
    output_dir: Path,
    expected_rows: int | None = EXPECTED_APTAINDEX_ROWS,
    check_deterministic_rerun: bool = False,
) -> S3RunResult:
    """Execute AptaIndex S3 technical eligibility and CHECKPOINT-1."""
    repo_root = repo_root.resolve()
    input_dir = (
        input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    ).resolve()
    source_metadata_dir = (
        source_metadata_dir
        if source_metadata_dir.is_absolute()
        else (repo_root / source_metadata_dir)
    ).resolve()
    eligibility_policy = (
        eligibility_policy
        if eligibility_policy.is_absolute()
        else (repo_root / eligibility_policy)
    ).resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    canonical_path = input_dir / "aptaindex_normalised.csv"
    qc_path = input_dir / "aptaindex_s2_qc.csv"
    sidecar_path = source_metadata_dir / "aptaindex_source_metadata.csv"
    proposals_path = input_dir / "detected_constants_aptaindex.csv"
    for path, label in (
        (canonical_path, "S2 canonical"),
        (qc_path, "S2 QC"),
        (sidecar_path, "source-metadata"),
        (proposals_path, "S2 constant-region proposals"),
    ):
        if not path.is_file():
            raise S3ClassifyError(f"Missing {label} input: {path.name}")

    raw_path = (
        repo_root / "data" / "raw" / "AptaIndex" / "aptamers-export-2026-07-22.csv"
    )
    raw_sha_before = ""
    check_raw = expected_rows == EXPECTED_APTAINDEX_ROWS
    if check_raw:
        if not raw_path.is_file():
            raise S3ClassifyError("Missing registered AptaIndex raw file")
        raw_sha_before = _sha256_file(raw_path)
        if raw_sha_before != EXPECTED_APTAINDEX_RAW_SHA256:
            raise S3ClassifyError(
                "AptaIndex raw SHA-256 does not match registry expectation"
            )

    s2_hash_before = _sha256_file(canonical_path)
    qc_hash_before = _sha256_file(qc_path)
    sidecar_hash_before = _sha256_file(sidecar_path)
    proposals_hash_before = _sha256_file(proposals_path)
    if check_raw and s2_hash_before != EXPECTED_APTAINDEX_S2_HASH:
        raise S3ClassifyError(
            "AptaIndex S2 normalised hash does not match the completed S2 milestone"
        )

    policy = load_eligibility_policy(eligibility_policy)
    if policy.source_key != "aptaindex":
        raise S3ClassifyError(
            f"Eligibility policy source_key must be aptaindex; "
            f"got {policy.source_key!r}"
        )
    if not policy.defer_target_classification or not policy.defer_evidence_scoring:
        raise S3ClassifyError(
            "AptaIndex S3 policy must defer target classification and "
            "evidence scoring"
        )
    if (
        policy.sequence_leakage_matching_enabled
        or policy.target_leakage_matching_enabled
        or not policy.defer_leakage_exclusion
    ):
        raise S3ClassifyError("AptaIndex S3 must not apply leakage exclusions")

    canonical_rows = _read_corpus_csv(canonical_path)
    qc_rows = _read_sidecar_csv(qc_path, label="S2 QC")
    sidecar_rows = _read_sidecar_csv(sidecar_path, label="source-metadata")
    proposal_rows = _read_plain_csv(proposals_path, label="S2 constant-region proposals")
    aligned_qc = _match_sidecar_one_to_one(
        canonical_rows, qc_rows, label="S2 QC"
    )
    aligned_sidecar = _match_sidecar_one_to_one(
        canonical_rows, sidecar_rows, label="source-metadata"
    )
    proposal_index = index_aptaindex_constant_proposals(
        canonical_rows, proposal_rows
    )

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S3ClassifyError(
            f"S2 row count must be {expected_rows}; got {len(canonical_rows)}"
        )
    if expected_rows == EXPECTED_APTAINDEX_ROWS:
        _assert_aptaindex_s2_invariants(canonical_rows)

    stats = AptaIndexS3Stats()
    stats.s2_rows = len(canonical_rows)
    stats.order_preserved = True
    stats.group_inference_disabled = True
    stats.multi_target_sequence_count = count_multi_target_sequences(canonical_rows)
    stats.multi_target_raw_sequence_count = count_multi_target_sequences(
        canonical_rows, sequence_field="sequence_raw"
    )
    stats.multi_target_treated_as_conflict = False

    s3_canonical: list[dict[str, str]] = []
    decision_rows: list[dict[str, str]] = []
    rejection_rows: list[dict[str, str]] = []
    parked_ssdna_rows: list[dict[str, str]] = []
    parked_chemistry_rows: list[dict[str, str]] = []
    local_detail_by_id: dict[str, dict[str, str]] = {}
    core_by_id = {row["record_id"]: row["sequence_core"] for row in canonical_rows}

    for s2_row, qc_row, meta_row in zip(
        canonical_rows, aligned_qc, aligned_sidecar, strict=True
    ):
        classified = classify_aptaindex_record(
            s2_row,
            qc_row,
            meta_row,
            policy=policy,
            proposals=proposal_index.get(s2_row["record_id"], ()),
        )
        if classified.canonical["record_id"] != s2_row["record_id"]:
            stats.order_preserved = False
            raise S3ClassifyError("S3 altered record_id or row identity")
        for column in CORPUS_COLUMNS:
            if classified.canonical[column] != s2_row[column]:
                raise S3ClassifyError(
                    f"S3 altered S2 canonical field {column!r}"
                )
        s3_canonical.append(classified.canonical)
        decision_rows.append(classified.decision)
        if classified.rejection_row is not None:
            rejection_rows.append(classified.rejection_row)
        if classified.park_row is not None:
            if classified.primary_route == APTAINDEX_PRIMARY_ROUTE_SSDNA:
                parked_ssdna_rows.append(classified.park_row)
            elif classified.primary_route == APTAINDEX_PRIMARY_ROUTE_CHEMISTRY_REVIEW:
                parked_chemistry_rows.append(classified.park_row)
            else:
                raise S3ClassifyError(
                    f"Park row has unexpected primary_route {classified.primary_route}"
                )
        local_detail_by_id[classified.canonical["record_id"]] = (
            build_aptaindex_local_detail_row(
                canonical=classified.canonical,
                s2_qc=qc_row,
                source_metadata=meta_row,
                decision=classified.decision,
            )
        )
        update_aptaindex_stats_from_row(stats, classified)

    sampled, pool, shortfall = apply_aptaindex_random_accept_audit(
        decision_rows,
        local_detail_by_id,
        seed=policy.random_seed,
        sample_size=policy.random_accept_audit_size,
    )
    stats.random_accept_audit_pool_size = pool
    stats.random_accept_audit_shortfall = shortfall
    refresh_aptaindex_stats_after_audit(stats, decision_rows)

    stats.s3_rows = len(s3_canonical)
    stats.unique_record_ids = len({row["record_id"] for row in s3_canonical})
    stats.unique_native_ids = len({row["native_id"] for row in s3_canonical})

    if stats.s3_rows != len(canonical_rows):
        raise S3ClassifyError("S3 must preserve every S2 row")
    if stats.unique_record_ids != len(s3_canonical):
        raise S3ClassifyError("S3 record_id values are not unique")
    if len({row["record_id"] for row in decision_rows}) != len(decision_rows):
        raise S3ClassifyError("Decision sidecar contains duplicate record_id values")

    rejected_n = stats.primary_route_counts.get(APTAINDEX_PRIMARY_ROUTE_REJECT, 0)
    parked_ssdna_n = stats.primary_route_counts.get(APTAINDEX_PRIMARY_ROUTE_SSDNA, 0)
    parked_chemistry_n = stats.primary_route_counts.get(
        APTAINDEX_PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0
    )
    eligible_n = stats.primary_route_counts.get(APTAINDEX_PRIMARY_ROUTE_ELIGIBLE, 0)
    if (
        rejected_n + parked_ssdna_n + parked_chemistry_n + eligible_n
        != stats.s3_rows
    ):
        raise S3ClassifyError(
            "technical_rejects + parked_ssdna + parked_chemistry_review + "
            "technically_eligible does not equal S3 rows"
        )
    if len(rejection_rows) != rejected_n:
        raise S3ClassifyError(
            "Rejection log count does not match technical_reject route"
        )
    if len(parked_ssdna_rows) != parked_ssdna_n:
        raise S3ClassifyError("Parked ssDNA count does not match parked_ssdna route")
    if len(parked_chemistry_rows) != parked_chemistry_n:
        raise S3ClassifyError(
            "Chemistry-review park count does not match parked_chemistry_review"
        )
    if sampled != stats.random_accept_audit_count:
        raise S3ClassifyError("Random-accept audit count mismatch")
    if stats.non_protein_parked_count != 0:
        raise S3ClassifyError(
            "AptaIndex S3 must not park from non-protein target routing"
        )
    if stats.missing_target_rejected_count != 0:
        raise S3ClassifyError("AptaIndex S3 must not emit missing_target rejects")
    if stats.group_consensus_proposal_record_count != 0:
        raise S3ClassifyError(
            "AptaIndex S3 unexpectedly found group-consensus proposals"
        )
    if stats.target_canonicalised_count or stats.evidence_scored_count:
        raise S3ClassifyError("AptaIndex S3 must not canonicalise target or evidence")
    if stats.affinity_normalised_count:
        raise S3ClassifyError("AptaIndex S3 must not normalise affinity")
    parked_ssdna_ids = {row["record_id"] for row in parked_ssdna_rows}
    parked_chemistry_ids = {row["record_id"] for row in parked_chemistry_rows}
    if parked_ssdna_ids & parked_chemistry_ids:
        raise S3ClassifyError(
            "A record must not appear in both ssDNA and chemistry-review park files"
        )

    for row in decision_rows:
        if not row["primary_reason"]:
            raise S3ClassifyError("Decision row missing primary_reason")
        if row.get("primary_reason") == "missing_target":
            raise S3ClassifyError("AptaIndex S3 must not reject missing_target")
        if row.get("primary_reason") == "non_protein_target_parked":
            raise S3ClassifyError(
                "AptaIndex S3 must not park peptide molecules as non-protein targets"
            )

    assert_aptaindex_accept_invariants(decision_rows)
    assert_aptaindex_reject_park_invariants(decision_rows)

    reason_count_rows: list[dict[str, str]] = []
    combo_counts: dict[tuple[str, str], int] = {}
    for row in decision_rows:
        key = (row["proposed_decision"], row["primary_reason"])
        combo_counts[key] = combo_counts.get(key, 0) + 1
    for (decision, reason), count in sorted(combo_counts.items()):
        reason_count_rows.append(
            {
                "proposed_decision": decision,
                "primary_reason": reason,
                "record_count": str(count),
            }
        )
    if sum(int(row["record_count"]) for row in reason_count_rows) != len(decision_rows):
        raise S3ClassifyError("Reason counts do not reconcile to decision rows")

    review_rows = sorted(decision_rows, key=review_sort_key)
    local_detail_rows: list[dict[str, str]] = []
    for review_row in review_rows:
        record_id = review_row["record_id"]
        if record_id not in local_detail_by_id:
            raise S3ClassifyError(
                f"Missing local-detail row for record_id={record_id!r}"
            )
        detail = local_detail_by_id[record_id]
        if detail["sequence_core"] != core_by_id[record_id]:
            raise S3ClassifyError("CHECKPOINT-1 must not apply constant-region trims")
        if detail.get("manual_decision"):
            raise S3ClassifyError("Local-detail must not pre-fill manual_decision")
        for field_name in (
            "manual_sequence_corrected",
            "manual_molecule_type_override",
            "manual_trim_action",
        ):
            if detail.get(field_name):
                raise S3ClassifyError(
                    f"Local-detail must not pre-fill {field_name}"
                )
        local_detail_rows.append(detail)
    for review_row, detail_row in zip(review_rows, local_detail_rows, strict=True):
        if review_row["record_id"] != detail_row["record_id"]:
            raise S3ClassifyError(
                "Local-detail ordering does not match sequence-free review"
            )
        if review_row["review_batch"] != detail_row.get("review_batch", ""):
            raise S3ClassifyError("Local-detail review_batch mismatch")

    forbidden_seq_cols = {"sequence_raw", "sequence_full", "sequence_core"}
    for col in forbidden_seq_cols:
        if col in APTAINDEX_DECISION_COLUMNS or col in APTAINDEX_PARK_COLUMNS:
            raise S3ClassifyError(f"Sequence column leaked into sidecar schema: {col}")
    for col in ("sequence_raw", "sequence_full", "sequence_core"):
        if col not in APTAINDEX_LOCAL_DETAIL_COLUMNS:
            raise S3ClassifyError(
                f"Local-detail schema missing required sequence column: {col}"
            )

    review_ids = [
        row["record_id"]
        for row in review_rows
        if row.get("manual_review_required") == "true"
    ]
    if len(review_ids) != len(set(review_ids)):
        raise S3ClassifyError("CHECKPOINT-1 review rows are duplicated")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_canonical = output_dir / "aptaindex_s3_canonical.csv"
    out_decisions = output_dir / "aptaindex_s3_decisions.csv"
    out_review = output_dir / "aptaindex_checkpoint1_review.csv"
    out_local_detail = output_dir / "aptaindex_checkpoint1_local_detail.csv"
    out_reason_counts = output_dir / "aptaindex_checkpoint1_reason_counts.csv"
    out_rejected = output_dir / "rejected_aptaindex.csv"
    out_parked_ssdna = output_dir / "aptaindex_s3_parked_ssdna.csv"
    out_parks = output_dir / "aptaindex_s3_parks.csv"
    out_summary = output_dir / "aptaindex_checkpoint1_summary.md"

    write_corpus_csv_atomic(out_canonical, s3_canonical, quoting=csv.QUOTE_ALL)
    write_csv_atomic(
        out_decisions, APTAINDEX_DECISION_COLUMNS, decision_rows, quoting=csv.QUOTE_ALL
    )
    write_csv_atomic(
        out_review, APTAINDEX_DECISION_COLUMNS, review_rows, quoting=csv.QUOTE_ALL
    )
    write_csv_atomic(
        out_local_detail,
        APTAINDEX_LOCAL_DETAIL_COLUMNS,
        local_detail_rows,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        out_reason_counts, APTAINDEX_REASON_COUNT_COLUMNS, reason_count_rows
    )
    write_csv_atomic(
        out_rejected, APTAINDEX_REJECTION_COLUMNS, rejection_rows, quoting=csv.QUOTE_ALL
    )
    write_csv_atomic(
        out_parked_ssdna, APTAINDEX_PARK_COLUMNS, parked_ssdna_rows, quoting=csv.QUOTE_ALL
    )
    write_csv_atomic(
        out_parks, APTAINDEX_PARK_COLUMNS, parked_chemistry_rows, quoting=csv.QUOTE_ALL
    )

    s2_hash_after = _sha256_file(canonical_path)
    qc_hash_after = _sha256_file(qc_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    proposals_hash_after = _sha256_file(proposals_path)
    raw_sha_after = raw_sha_before
    if check_raw:
        raw_sha_after = _sha256_file(raw_path)
        if raw_sha_after != EXPECTED_APTAINDEX_RAW_SHA256:
            raise S3ClassifyError("AptaIndex raw SHA-256 changed during S3")
    inputs_unchanged = (
        s2_hash_before == s2_hash_after
        and qc_hash_before == qc_hash_after
        and sidecar_hash_before == sidecar_hash_after
        and proposals_hash_before == proposals_hash_after
        and (not check_raw or raw_sha_before == raw_sha_after)
    )
    if not inputs_unchanged:
        raise S3ClassifyError("S2/source inputs were modified during S3 execution")

    s2_integrity_ok = True
    if _sha256_file(out_canonical) != s2_hash_before:
        raise S3ClassifyError(
            "S3 canonical output is not byte-identical to S2 normalised input"
        )

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "canonical": _sha256_file(out_canonical),
            "decisions": _sha256_file(out_decisions),
            "review": _sha256_file(out_review),
            "local_detail": _sha256_file(out_local_detail),
            "reason_counts": _sha256_file(out_reason_counts),
            "rejected": _sha256_file(out_rejected),
            "parked_ssdna": _sha256_file(out_parked_ssdna),
            "parks": _sha256_file(out_parks),
        }
        second = run_aptaindex_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        second_hashes = {
            "canonical": _sha256_file(second.output_canonical),
            "decisions": _sha256_file(second.output_decisions),
            "review": _sha256_file(second.output_review),
            "local_detail": _sha256_file(second.output_local_detail),
            "reason_counts": _sha256_file(second.output_reason_counts),
            "rejected": _sha256_file(second.output_rejected),
            "parked_ssdna": _sha256_file(second.output_parked_ssdna),
            "parks": _sha256_file(second.output_parks),
        }
        deterministic_ok = first_hashes == second_hashes
        if not deterministic_ok:
            raise S3ClassifyError(
                "S3 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S3RunResult(
        source_key="aptaindex",
        stats=stats,
        output_canonical=out_canonical,
        output_decisions=out_decisions,
        output_review=out_review,
        output_local_detail=out_local_detail,
        output_summary=out_summary,
        output_reason_counts=out_reason_counts,
        output_leakage_matches=None,
        s2_hash_before=s2_hash_before,
        s2_hash_after=s2_hash_after,
        qc_hash_before=qc_hash_before,
        qc_hash_after=qc_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        s2_integrity_ok=s2_integrity_ok,
        output_rejected=out_rejected,
        output_parks=out_parks,
        output_parked_ssdna=out_parked_ssdna,
        output_parked_non_protein=None,
        raw_sha_before=raw_sha_before,
        raw_sha_after=raw_sha_after,
    )
    summary_text = build_aptaindex_checkpoint1_summary(
        repo_root=repo_root,
        result=run_result,
        policy_path=eligibility_policy,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must not contain absolute repository paths"
        )
    if APTAINDEX_PIPELINE_STOP_STATEMENT not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing pipeline stop statement")
    if "group-wise constant-region inference was disabled" not in summary_text.lower():
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must state that group-wise inference was disabled"
        )
    if "Evidence scored" not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing evidence deferral")
    _write_text_atomic(out_summary, summary_text)
    return run_result


def _assert_ena_s2_invariants(canonical_rows: Sequence[dict[str, str]]) -> None:
    """Hard-fail if the ENA S2 starting invariants no longer reconcile."""
    if len(canonical_rows) != EXPECTED_ENA_ROWS:
        raise S3ClassifyError(
            f"S3 input rows must be {EXPECTED_ENA_ROWS}; got {len(canonical_rows)}"
        )
    record_ids = [row["record_id"] for row in canonical_rows]
    if len(set(record_ids)) != EXPECTED_ENA_ROWS:
        raise S3ClassifyError("S2 record_id values are not unique")
    molecule_counts: dict[str, int] = {}
    chemistry_counts: dict[str, int] = {}
    t_to_u = 0
    for row in canonical_rows:
        if row.get("source_db") != "ena":
            raise S3ClassifyError("S2 row source_db must be ena")
        if row.get("source_dataset") != EXPECTED_ENA_SOURCE_DATASET:
            raise S3ClassifyError(
                f"S2 source_dataset must be {EXPECTED_ENA_SOURCE_DATASET}"
            )
        molecule = row.get("molecule_type") or ""
        chemistry = row.get("chemistry") or ""
        molecule_counts[molecule] = molecule_counts.get(molecule, 0) + 1
        chemistry_counts[chemistry] = chemistry_counts.get(chemistry, 0) + 1
        if row.get("sequence_core") != row.get("sequence_full"):
            raise S3ClassifyError("ENA S2 must have sequence_core == sequence_full")
        if (row.get("t_to_u_applied") or "").lower() == "true":
            t_to_u += 1
        for field_name in (
            "target_name",
            "target_uniprot",
            "target_type",
            "binding_evidence_score",
            "cluster_id",
            "partition",
        ):
            if row.get(field_name):
                raise S3ClassifyError(
                    f"ENA S2 must not populate later-stage field {field_name}"
                )
    if molecule_counts != {"RNA": EXPECTED_ENA_ROWS}:
        raise S3ClassifyError(f"ENA S2 molecule_type invariant failed: {molecule_counts}")
    if chemistry_counts != {"RNA": EXPECTED_ENA_ROWS}:
        raise S3ClassifyError(f"ENA S2 chemistry invariant failed: {chemistry_counts}")
    if t_to_u != 5:
        raise S3ClassifyError(f"ENA S2 T→U count must be 5; got {t_to_u}")


def build_ena_checkpoint1_summary(
    *,
    repo_root: Path,
    result: S3RunResult,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown CHECKPOINT-1 summary (no sequences)."""
    stats = result.stats
    if not isinstance(stats, EnaS3Stats):
        raise S3ClassifyError("ENA summary requires EnaS3Stats")

    def _count(mapping: Mapping[str, int], key: str) -> int:
        return int(mapping.get(key, 0))

    rejected = _count(stats.primary_route_counts, ENA_PRIMARY_ROUTE_REJECT)
    parked = _count(stats.primary_route_counts, ENA_PRIMARY_ROUTE_CONSTRUCT)
    eligible = _count(stats.primary_route_counts, ENA_PRIMARY_ROUTE_ELIGIBLE)
    routed_sum = rejected + parked + eligible
    rel_policy = _relative_display(policy_path, repo_root)
    lines = [
        "# ENA S3 / CHECKPOINT-1 summary",
        "",
        "## Reconciliation",
        "",
        f"- S3 input = `{stats.s2_rows}`",
        f"- S3 route total = `{stats.s3_rows}`",
        f"- unique record_id = `{stats.unique_record_ids}`",
        f"- proposed_accept = `{_count(stats.decision_counts, 'proposed_accept')}`",
        f"- proposed_park = `{_count(stats.decision_counts, 'proposed_park')}`",
        f"- proposed_reject = `{_count(stats.decision_counts, 'proposed_reject')}`",
        f"- technically eligible RNA = `{eligible}`",
        f"- parked construct/trim review = `{parked}`",
        f"- automatically rejected = `{rejected}`",
        f"- sum of primary routes = `{routed_sum}`",
        f"- S2 order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        "",
        f"`{stats.s2_rows}` = `{eligible}` proposed_accept + `{parked}` "
        f"proposed_park + `{rejected}` proposed_reject.",
        "",
        "## Primary reasons",
        "",
    ]
    for reason, count in sorted(stats.primary_reason_counts.items()):
        lines.append(f"- `{reason}`: `{count}`")
    lines.extend(
        [
            "",
            "## Secondary reason counts",
            "",
        ]
    )
    if stats.secondary_reason_counts:
        for reason, count in sorted(stats.secondary_reason_counts.items()):
            lines.append(f"- `{reason}`: `{count}`")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Technical conditions",
            "",
            f"- missing sequence: `{stats.missing_sequence_count}`",
            f"- mixed T/U: `{stats.mixed_t_u_count}`",
            f"- ambiguous bases: `{stats.ambiguous_bases_count}`",
            f"- invalid alphabet: `{stats.invalid_alphabet_count}`",
            f"- alignment gaps: `{stats.alignment_gaps_count}`",
            f"- length out of range: `{stats.length_out_of_range_count}`",
            f"- length <20: `{stats.length_below_20_count}`",
            f"- length >100: `{stats.length_above_100_count}`",
            f"- unresolved construct/trim: `{stats.trim_construct_unresolved_count}`",
            f"- group-consensus records: `{stats.group_consensus_record_count}`",
            f"- group-covered parks: `{stats.group_covered_park_count}`",
            f"- source promoter/template concerns: `{stats.source_promoter_count}`",
            f"- source promoter without group proposal: "
            f"`{stats.source_promoter_without_group_count}`",
            f"- source promoter overlapping group proposal: "
            f"`{stats.source_promoter_with_group_count}`",
            f"- T-transcribed RNA records: `{stats.t_to_u_count}`",
            f"- T-transcribed proposed accepts: `{stats.t_to_u_accept_count}`",
            f"- ssDNA parks: `{stats.ssdna_parked_count}`",
            f"- chemistry parks: `{stats.chemistry_park_count}`",
            f"- non-RNA parks: `{stats.non_rna_park_count}`",
            "",
            "## Length-boundary audit",
            "",
            f"- 20–25 nt: `{stats.boundary_low_count}`",
            f"- 90–100 nt: `{stats.boundary_high_count}`",
            "",
            "## Exact sequence_full duplicate diagnostic",
            "",
            f"- duplicated `sequence_full` values: `{stats.duplicate_sequence_full_values}`",
            f"- records involved: `{stats.duplicate_sequence_full_records}`",
            "- label: `diagnostic only — no deduplication performed`",
            "",
            "## Random kept audit",
            "",
            f"- selected: `{stats.random_accept_audit_count}`",
            f"- pool: `{stats.random_accept_audit_pool_size}`",
            f"- shortfall: `{stats.random_accept_audit_shortfall}`",
            "- seed: `42`",
            "",
            "## Review batches (record-level)",
            "",
        ]
    )
    for batch in (
        "01_judgement_dependent_technical",
        "02_transcription_or_reconciliation_audit",
        "03_length_boundary",
        "04_random_kept_audit",
    ):
        lines.append(f"- `{batch}`: `{stats.review_batch_counts.get(batch, 0)}`")
    lines.extend(
        [
            "",
            f"- unique record-level CHECKPOINT review records: "
            f"`{stats.unique_checkpoint_review_records}`",
            "",
            "## Deferred work",
            "",
            "- Canonical scientific fields unchanged from S2.",
            "- Applied trims remain 0. No constant-region trim was applied.",
            "- Source target metadata remains provenance; "
            f"unresolved_target=`{stats.unresolved_target_count}`; "
            f"genuine_target_conflict=`{stats.genuine_target_conflict_count}`.",
            "- Evidence was not classified onto E1–E5.",
            "- Leakage matching was not run.",
            "- Exact deduplication was not performed.",
            "- Near-duplicate families were not used for routing.",
            "- Global S4 has not been started.",
            "",
            f"- Eligibility policy: `{rel_policy}`",
            "",
            ENA_PIPELINE_STOP_STATEMENT,
            "",
            "WARNING: `ena_checkpoint1_local_detail.csv` and `rejected_ena.csv` "
            "contain source sequences. They must remain under ignored `data/`.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_ena_s3(
    *,
    repo_root: Path,
    input_dir: Path,
    source_metadata_dir: Path,
    eligibility_policy: Path,
    output_dir: Path,
    expected_rows: int | None = EXPECTED_ENA_ROWS,
    check_deterministic_rerun: bool = False,
) -> S3RunResult:
    """Execute ENA S3 technical eligibility and CHECKPOINT-1 artefacts."""
    repo_root = repo_root.resolve()
    input_dir = (
        input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    ).resolve()
    source_metadata_dir = (
        source_metadata_dir
        if source_metadata_dir.is_absolute()
        else (repo_root / source_metadata_dir)
    ).resolve()
    eligibility_policy = (
        eligibility_policy
        if eligibility_policy.is_absolute()
        else (repo_root / eligibility_policy)
    ).resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    canonical_path = input_dir / "ena_normalised.csv"
    qc_path = input_dir / "ena_s2_qc.csv"
    sidecar_path = source_metadata_dir / "ena_source_metadata.csv"
    proposals_path = input_dir / "ena_constant_region_proposals.csv"
    membership_path = input_dir / "ena_constant_region_membership.csv"
    for path, label in (
        (canonical_path, "S2 canonical"),
        (qc_path, "S2 QC"),
        (sidecar_path, "source-metadata"),
        (proposals_path, "S2 constant-region proposals"),
    ):
        if not path.is_file():
            raise S3ClassifyError(f"Missing {label} input: {path.name}")

    raw_path = (
        repo_root
        / "data"
        / "raw"
        / "ENA"
        / "review_v2"
        / "ena_selected_after_manual_review.csv"
    )
    check_raw = expected_rows == EXPECTED_ENA_ROWS
    raw_sha_before = ""
    if check_raw:
        if not raw_path.is_file():
            raise S3ClassifyError("Missing registered ENA raw selected file")
        raw_sha_before = _sha256_file(raw_path)
        if raw_sha_before != EXPECTED_ENA_RAW_SHA256:
            raise S3ClassifyError(
                "ENA raw SHA-256 does not match registry expectation"
            )

    s2_hash_before = _sha256_file(canonical_path)
    qc_hash_before = _sha256_file(qc_path)
    sidecar_hash_before = _sha256_file(sidecar_path)
    proposals_hash_before = _sha256_file(proposals_path)
    membership_hash_before = (
        _sha256_file(membership_path) if membership_path.is_file() else ""
    )
    if check_raw and s2_hash_before != EXPECTED_ENA_S2_HASH:
        raise S3ClassifyError("ENA S2 canonical SHA-256 does not match accepted S2")

    policy = load_eligibility_policy(eligibility_policy)
    if policy.source_key != "ena":
        raise S3ClassifyError(
            f"Eligibility policy source_key must be ena; got {policy.source_key!r}"
        )
    if not policy.defer_target_classification or not policy.defer_evidence_scoring:
        raise S3ClassifyError(
            "ENA S3 policy must defer target classification and evidence scoring"
        )
    if (
        policy.sequence_leakage_matching_enabled
        or policy.target_leakage_matching_enabled
        or not policy.defer_leakage_exclusion
    ):
        raise S3ClassifyError("ENA S3 must not apply leakage exclusions")
    if not policy.unresolved_trim_blocks_eligibility:
        raise S3ClassifyError(
            "ENA S3 must park unresolved medium-confidence construct/trim cases"
        )

    canonical_rows = _read_corpus_csv(canonical_path)
    qc_rows = _read_sidecar_csv(qc_path, label="S2 QC")
    sidecar_rows = _read_sidecar_csv(sidecar_path, label="source-metadata")
    proposal_rows = _read_plain_csv(proposals_path, label="S2 constant-region proposals")
    membership_rows: list[dict[str, str]] = []
    if membership_path.is_file():
        membership_rows = _read_plain_csv(
            membership_path, label="S2 constant-region membership"
        )
    aligned_qc = _match_sidecar_one_to_one(canonical_rows, qc_rows, label="S2 QC")
    aligned_sidecar = _match_sidecar_one_to_one(
        canonical_rows, sidecar_rows, label="source-metadata"
    )
    proposal_index = index_ena_constant_proposals(
        aligned_qc, proposal_rows, membership_rows
    )

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S3ClassifyError(
            f"S2 row count must be {expected_rows}; got {len(canonical_rows)}"
        )
    if expected_rows == EXPECTED_ENA_ROWS:
        _assert_ena_s2_invariants(canonical_rows)

    stats = EnaS3Stats()
    stats.s2_rows = len(canonical_rows)
    stats.order_preserved = True
    unresolved = 0
    conflict = 0
    for meta in aligned_sidecar:
        if (meta.get("unresolved_target") or "").strip() not in {"", "0", "false"}:
            unresolved += 1
        if (meta.get("genuine_target_conflict") or "").strip() not in {
            "",
            "0",
            "false",
        }:
            conflict += 1
    stats.unresolved_target_count = unresolved
    stats.genuine_target_conflict_count = conflict

    s3_canonical: list[dict[str, str]] = []
    decision_rows: list[dict[str, str]] = []
    rejection_rows: list[dict[str, str]] = []
    parked_rows: list[dict[str, str]] = []
    local_detail_by_id: dict[str, dict[str, str]] = {}
    core_by_id = {row["record_id"]: row["sequence_core"] for row in canonical_rows}

    for s2_row, qc_row, meta_row in zip(
        canonical_rows, aligned_qc, aligned_sidecar, strict=True
    ):
        classified = classify_ena_record(
            s2_row,
            qc_row,
            meta_row,
            policy=policy,
            proposals=proposal_index.get(s2_row["record_id"], ()),
        )
        if classified.canonical["record_id"] != s2_row["record_id"]:
            stats.order_preserved = False
            raise S3ClassifyError("S3 altered record_id or row identity")
        for column in CORPUS_COLUMNS:
            if classified.canonical[column] != s2_row[column]:
                raise S3ClassifyError(f"S3 altered S2 canonical field {column!r}")
        s3_canonical.append(classified.canonical)
        decision_rows.append(classified.decision)
        if classified.rejection_row is not None:
            rejection_rows.append(classified.rejection_row)
        if classified.park_row is not None:
            if classified.primary_route != ENA_PRIMARY_ROUTE_CONSTRUCT:
                raise S3ClassifyError(
                    f"Park row has unexpected primary_route {classified.primary_route}"
                )
            parked_rows.append(classified.park_row)
        local_detail_by_id[classified.canonical["record_id"]] = (
            build_ena_local_detail_row(
                canonical=classified.canonical,
                s2_qc=qc_row,
                source_metadata=meta_row,
                decision=classified.decision,
            )
        )
        update_ena_stats_from_row(stats, classified)

    duplicate_ids, n_values, n_records = duplicate_sequence_full_ids(canonical_rows)
    stats.duplicate_sequence_full_values = n_values
    stats.duplicate_sequence_full_records = n_records
    apply_duplicate_sequence_diagnostic(
        decision_rows, local_detail_by_id, duplicate_ids
    )
    sampled, pool, shortfall = apply_ena_random_accept_audit(
        decision_rows,
        local_detail_by_id,
        seed=policy.random_seed,
        sample_size=policy.random_accept_audit_size,
    )
    stats.random_accept_audit_pool_size = pool
    stats.random_accept_audit_shortfall = shortfall
    refresh_ena_stats_after_audit(stats, decision_rows)
    parked_by_id = {row["record_id"]: row for row in parked_rows}
    for decision in decision_rows:
        park = parked_by_id.get(decision["record_id"])
        if park is None:
            continue
        park["manual_review_required"] = decision["manual_review_required"]
        park["review_batch"] = decision["review_batch"]
        park["secondary_reasons"] = decision["secondary_reasons"]

    stats.s3_rows = len(s3_canonical)
    stats.unique_record_ids = len({row["record_id"] for row in s3_canonical})
    stats.unique_native_ids = len({row["native_id"] for row in s3_canonical})
    if stats.s3_rows != len(canonical_rows):
        raise S3ClassifyError("S3 must preserve every S2 row")
    if stats.unique_record_ids != len(s3_canonical):
        raise S3ClassifyError("S3 record_id values are not unique")

    rejected_n = stats.primary_route_counts.get(ENA_PRIMARY_ROUTE_REJECT, 0)
    parked_n = stats.primary_route_counts.get(ENA_PRIMARY_ROUTE_CONSTRUCT, 0)
    eligible_n = stats.primary_route_counts.get(ENA_PRIMARY_ROUTE_ELIGIBLE, 0)
    if rejected_n + parked_n + eligible_n != stats.s3_rows:
        raise S3ClassifyError(
            "proposed_accept + proposed_park + proposed_reject does not equal S3 rows"
        )
    if len(rejection_rows) != rejected_n:
        raise S3ClassifyError(
            "Rejection log count does not match technical_reject route"
        )
    if len(parked_rows) != parked_n:
        raise S3ClassifyError("Park count does not match parked_construct_review route")
    if sampled != stats.random_accept_audit_count:
        raise S3ClassifyError("Random-accept audit count mismatch")
    if expected_rows == EXPECTED_ENA_ROWS and stats.length_below_20_count != 4:
        raise S3ClassifyError(
            f"ENA S3 expected 4 records <20 nt; got {stats.length_below_20_count}"
        )
    if expected_rows == EXPECTED_ENA_ROWS and stats.length_above_100_count != 0:
        raise S3ClassifyError("ENA S3 must have zero records >100 nt")
    if expected_rows == EXPECTED_ENA_ROWS and stats.ssdna_parked_count != 0:
        raise S3ClassifyError("ENA S3 must not create ssDNA parks")
    if expected_rows == EXPECTED_ENA_ROWS and n_values != 3:
        raise S3ClassifyError(
            f"ENA S3 expected 3 duplicated sequence_full values; got {n_values}"
        )
    if expected_rows == EXPECTED_ENA_ROWS and n_records != 6:
        raise S3ClassifyError(
            f"ENA S3 expected 6 duplicate-involved records; got {n_records}"
        )
    if expected_rows == EXPECTED_ENA_ROWS and stats.group_consensus_record_count != 92:
        raise S3ClassifyError(
            "ENA S3 expected 92 group-consensus records; got "
            f"{stats.group_consensus_record_count}"
        )

    for row in decision_rows:
        if not row["primary_reason"]:
            raise S3ClassifyError("Decision row missing primary_reason")

    assert_ena_accept_invariants(decision_rows)
    assert_ena_reject_park_invariants(decision_rows)

    reason_count_rows: list[dict[str, str]] = []
    combo_counts: dict[tuple[str, str], int] = {}
    for row in decision_rows:
        key = (row["proposed_decision"], row["primary_reason"])
        combo_counts[key] = combo_counts.get(key, 0) + 1
    for (decision, reason), count in sorted(combo_counts.items()):
        reason_count_rows.append(
            {
                "proposed_decision": decision,
                "primary_reason": reason,
                "record_count": str(count),
            }
        )
    if sum(int(row["record_count"]) for row in reason_count_rows) != len(decision_rows):
        raise S3ClassifyError("Reason counts do not reconcile to decision rows")

    review_rows = sorted(decision_rows, key=review_sort_key)
    local_detail_rows: list[dict[str, str]] = []
    for review_row in review_rows:
        record_id = review_row["record_id"]
        if record_id not in local_detail_by_id:
            raise S3ClassifyError(
                f"Missing local-detail row for record_id={record_id!r}"
            )
        detail = local_detail_by_id[record_id]
        if detail["sequence_core"] != core_by_id[record_id]:
            raise S3ClassifyError("CHECKPOINT-1 must not apply constant-region trims")
        if detail.get("manual_decision"):
            raise S3ClassifyError("Local-detail must not pre-fill manual_decision")
        local_detail_rows.append(detail)
    for review_row, detail_row in zip(review_rows, local_detail_rows, strict=True):
        if review_row["record_id"] != detail_row["record_id"]:
            raise S3ClassifyError(
                "Local-detail ordering does not match sequence-free review"
            )
        if review_row["review_batch"] != detail_row.get("review_batch", ""):
            raise S3ClassifyError("Local-detail review_batch mismatch")

    forbidden_seq_cols = {"sequence_raw", "sequence_full", "sequence_core"}
    for col in forbidden_seq_cols:
        if col in ENA_DECISION_COLUMNS or col in ENA_PARK_COLUMNS:
            raise S3ClassifyError(f"Sequence column leaked into sidecar schema: {col}")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_canonical = output_dir / "ena_s3_canonical.csv"
    out_decisions = output_dir / "ena_s3_decisions.csv"
    out_review = output_dir / "ena_checkpoint1_review.csv"
    out_local_detail = output_dir / "ena_checkpoint1_local_detail.csv"
    out_reason_counts = output_dir / "ena_checkpoint1_reason_counts.csv"
    out_rejected = output_dir / "rejected_ena.csv"
    out_parks = output_dir / "ena_s3_parked_construct.csv"
    out_summary = output_dir / "ena_checkpoint1_summary.md"

    write_corpus_csv_atomic(out_canonical, s3_canonical)
    write_csv_atomic(out_decisions, ENA_DECISION_COLUMNS, decision_rows)
    write_csv_atomic(out_review, ENA_DECISION_COLUMNS, review_rows)
    write_csv_atomic(out_local_detail, ENA_LOCAL_DETAIL_COLUMNS, local_detail_rows)
    write_csv_atomic(out_reason_counts, ENA_REASON_COUNT_COLUMNS, reason_count_rows)
    write_csv_atomic(out_rejected, ENA_REJECTION_COLUMNS, rejection_rows)
    write_csv_atomic(out_parks, ENA_PARK_COLUMNS, parked_rows)

    s2_hash_after = _sha256_file(canonical_path)
    qc_hash_after = _sha256_file(qc_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    proposals_hash_before_after = _sha256_file(proposals_path)
    if proposals_hash_before != proposals_hash_before_after:
        raise S3ClassifyError("S2 proposal artefacts were modified during S3")
    membership_hash_after = (
        _sha256_file(membership_path) if membership_path.is_file() else ""
    )
    if membership_hash_before != membership_hash_after:
        raise S3ClassifyError("S2 membership artefacts were modified during S3")
    raw_sha_after = raw_sha_before
    if check_raw:
        raw_sha_after = _sha256_file(raw_path)
        if raw_sha_after != EXPECTED_ENA_RAW_SHA256:
            raise S3ClassifyError("ENA raw SHA-256 changed during S3")
    inputs_unchanged = (
        s2_hash_before == s2_hash_after
        and qc_hash_before == qc_hash_after
        and sidecar_hash_before == sidecar_hash_after
        and proposals_hash_before == proposals_hash_before_after
        and membership_hash_before == membership_hash_after
        and (not check_raw or raw_sha_before == raw_sha_after)
    )
    if not inputs_unchanged:
        raise S3ClassifyError("S2/source inputs were modified during S3 execution")
    if _sha256_file(out_canonical) != s2_hash_before:
        raise S3ClassifyError(
            "S3 canonical output is not byte-identical to S2 normalised input"
        )
    s2_integrity_ok = True

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "canonical": _sha256_file(out_canonical),
            "decisions": _sha256_file(out_decisions),
            "review": _sha256_file(out_review),
            "local_detail": _sha256_file(out_local_detail),
            "reason_counts": _sha256_file(out_reason_counts),
            "rejected": _sha256_file(out_rejected),
            "parks": _sha256_file(out_parks),
        }
        second = run_ena_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["canonical"] == _sha256_file(second.output_canonical)
            and first_hashes["decisions"] == _sha256_file(second.output_decisions)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["local_detail"]
            == _sha256_file(second.output_local_detail)
            and first_hashes["reason_counts"]
            == _sha256_file(second.output_reason_counts)
            and first_hashes["rejected"] == _sha256_file(second.output_rejected)
            and first_hashes["parks"] == _sha256_file(second.output_parks)
        )
        if not deterministic_ok:
            raise S3ClassifyError(
                "S3 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S3RunResult(
        source_key="ena",
        stats=stats,
        output_canonical=out_canonical,
        output_decisions=out_decisions,
        output_review=out_review,
        output_local_detail=out_local_detail,
        output_summary=out_summary,
        output_reason_counts=out_reason_counts,
        output_leakage_matches=None,
        s2_hash_before=s2_hash_before,
        s2_hash_after=s2_hash_after,
        qc_hash_before=qc_hash_before,
        qc_hash_after=qc_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        s2_integrity_ok=s2_integrity_ok,
        output_rejected=out_rejected,
        output_parks=out_parks,
        raw_sha_before=raw_sha_before,
        raw_sha_after=raw_sha_after,
    )
    summary_text = build_ena_checkpoint1_summary(
        repo_root=repo_root,
        result=run_result,
        policy_path=eligibility_policy,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must not contain absolute repository paths"
        )
    if ENA_PIPELINE_STOP_STATEMENT not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing pipeline stop statement")
    if "Evidence was not classified" not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing evidence deferral")
    if "no deduplication performed" not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing duplicate diagnostic label")
    _write_text_atomic(out_summary, summary_text)
    return run_result


def _assert_aptamerbase_s2_invariants(canonical_rows: Sequence[dict[str, str]]) -> None:
    """Hard-fail if the AptamerBase S2 starting contract is broken."""
    if len(canonical_rows) != EXPECTED_APTAMERBASE_ROWS:
        raise S3ClassifyError(
            f"S3 input rows must be {EXPECTED_APTAMERBASE_ROWS}; "
            f"got {len(canonical_rows)}"
        )
    record_ids = [row["record_id"] for row in canonical_rows]
    if len(set(record_ids)) != EXPECTED_APTAMERBASE_ROWS:
        raise S3ClassifyError("AptamerBase S2 record_id values are not unique")
    for row in canonical_rows:
        if row.get("source_db") != "aptamerbase":
            raise S3ClassifyError("S2 row source_db must be aptamerbase")
        if row.get("source_dataset") != EXPECTED_APTAMERBASE_SOURCE_DATASET:
            raise S3ClassifyError(
                "S2 row source_dataset must be "
                f"{EXPECTED_APTAMERBASE_SOURCE_DATASET}"
            )
        if row.get("sequence_core") != row.get("sequence_full"):
            raise S3ClassifyError(
                "AptamerBase S2 sequence_core must equal sequence_full"
            )
        for field_name in (
            "target_name",
            "target_uniprot",
            "target_type",
            "target_family",
            "target_pfam",
            "pdb_id",
            "binding_evidence_type",
            "binding_evidence_score",
            "affinity_value",
            "cluster_id",
            "partition",
        ):
            if row.get(field_name):
                raise S3ClassifyError(
                    f"AptamerBase S2 must leave {field_name} empty"
                )
        if row.get("target_name_raw"):
            raise S3ClassifyError("AptamerBase S2 must leave target_name_raw empty")


def build_aptamerbase_checkpoint1_summary(
    *,
    repo_root: Path,
    result: S3RunResult,
    policy_path: Path,
) -> str:
    """Sequence-free AptamerBase S3 / CHECKPOINT-1 report."""
    stats = result.stats
    assert isinstance(stats, AptamerBaseS3Stats)

    def _count(mapping: Mapping[str, int], key: str) -> int:
        return int(mapping.get(key, 0))

    rejected = _count(stats.primary_route_counts, APTAMERBASE_PRIMARY_ROUTE_REJECT)
    parked_ssdna = _count(stats.primary_route_counts, APTAMERBASE_PRIMARY_ROUTE_SSDNA)
    parked_molecule = _count(
        stats.primary_route_counts, APTAMERBASE_PRIMARY_ROUTE_MOLECULE
    )
    parked_chemistry = _count(
        stats.primary_route_counts, APTAMERBASE_PRIMARY_ROUTE_CHEMISTRY_REVIEW
    )
    parked_construct = _count(
        stats.primary_route_counts, APTAMERBASE_PRIMARY_ROUTE_CONSTRUCT
    )
    eligible = _count(stats.primary_route_counts, APTAMERBASE_PRIMARY_ROUTE_ELIGIBLE)
    route_sum = (
        rejected
        + parked_ssdna
        + parked_molecule
        + parked_chemistry
        + parked_construct
        + eligible
    )
    lines = [
        "# AptamerBase S3 technical eligibility and CHECKPOINT-1",
        "",
        "## Source reconciliation",
        "",
        f"- Physical S2/S3 rows: `{stats.s2_rows}` / `{stats.s3_rows}`",
        f"- Unique `record_id`: `{stats.unique_record_ids}`",
        f"- Unique `native_id`: `{stats.unique_native_ids}`",
        f"- Unique Freebase IDs (from S2 grain): `{stats.unique_freebase_ids}`",
        f"- Order preserved: `{'yes' if stats.order_preserved else 'no'}`",
        f"- Group-wise constant-region inference: "
        f"`{'disabled' if stats.group_inference_disabled else 'enabled'}`",
        f"- Applied trims: `{stats.applied_trim_count}`",
        f"- `sequence_core` differs from `sequence_full`: "
        f"`{stats.core_differs_from_full}`",
        "",
        "Source object types:",
        "",
    ]
    for name, count in _count_sorted(stats.source_object_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "Primary routes (exactly one per row):",
            "",
            f"- technical/source rejects: `{rejected}`",
            f"- parked ssDNA: `{parked_ssdna}`",
            f"- parked molecule unknown: `{parked_molecule}`",
            f"- parked chemistry review: `{parked_chemistry}`",
            f"- parked unresolved construct: `{parked_construct}`",
            f"- technically eligible RNA/2F-RNA: `{eligible}`",
            f"- route total: `{route_sum}`",
            "",
            "### Source object type by primary route",
            "",
        ]
    )
    lines.extend(_nested_count_lines(stats.source_object_by_route))
    lines.extend(
        [
            "",
            "## Technical rejections",
            "",
            "Primary reasons:",
            "",
            f"- `non_aptamer_source_object`: "
            f"`{_count(stats.primary_reason_counts, 'non_aptamer_source_object')}`",
            f"- `missing_sequence`: "
            f"`{_count(stats.primary_reason_counts, 'missing_sequence')}`",
            f"- `mixed_T_and_U`: "
            f"`{_count(stats.primary_reason_counts, 'mixed_T_and_U')}`",
            f"- `ambiguous_bases`: "
            f"`{_count(stats.primary_reason_counts, 'ambiguous_bases')}`",
            f"- `alignment_gaps`: "
            f"`{_count(stats.primary_reason_counts, 'alignment_gaps')}`",
            f"- `invalid_alphabet`: "
            f"`{_count(stats.primary_reason_counts, 'invalid_alphabet')}`",
            f"- `length_out_of_range`: "
            f"`{_count(stats.primary_reason_counts, 'length_out_of_range')}`",
            "",
            "Overlapping condition tallies (a record may contribute to more than one):",
            "",
            f"- non-aptamer source objects: `{stats.non_aptamer_source_object_count}`",
            f"- structure-topic rows: `{stats.structure_topic_rows}`",
            f"- structure-topic nonempty sequence: "
            f"`{stats.structure_topic_nonempty_sequence}`",
            f"- missing-sequence condition: `{stats.missing_sequence_count}`",
            f"- missing sequence on structure topics: "
            f"`{stats.missing_sequence_structure_count}`",
            f"- missing sequence on aptamer topics: "
            f"`{stats.missing_sequence_aptamer_count}`",
            f"- mixed T/U condition: `{stats.mixed_t_u_count}`",
            f"- ambiguous-bases condition: `{stats.ambiguous_bases_count}`",
            f"- alignment-gaps condition: `{stats.alignment_gaps_count}`",
            f"- invalid-alphabet condition: `{stats.invalid_alphabet_count}`",
            f"- length-out-of-range condition: `{stats.length_out_of_range_count}`",
            f"- actual length <20: `{stats.length_below_min_count}`",
            f"- actual length >100: `{stats.length_above_max_count}`",
            "",
            "## Parking",
            "",
            f"- source ssDNA rows: `{stats.ssdna_source_count}`",
            f"- parked ssDNA (primary route): `{parked_ssdna}`",
            f"- source molecule unknown: `{stats.molecule_unknown_source_count}`",
            f"- molecule unknown on structure topics: "
            f"`{stats.molecule_unknown_structure_count}`",
            f"- molecule unknown on aptamer topics: "
            f"`{stats.molecule_unknown_aptamer_count}`",
            f"- parked unresolved molecule (primary route): `{parked_molecule}`",
            f"- parked chemistry review (primary route): `{parked_chemistry}`",
            f"- Spiegelmer/L-RNA QC condition: `{stats.spiegelmer_count}`",
            f"- parked unresolved construct (primary route): `{parked_construct}`",
            "",
            "Chemistry class counts (all rows):",
            "",
        ]
    )
    for name, count in _count_sorted(stats.chemistry_class_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Technically eligible",
            "",
            f"- technically eligible primary route: `{eligible}`",
            f"- RNA chemistry: `{stats.eligible_rna_chemistry_count}`",
            f"- 2F-RNA chemistry: `{stats.eligible_twof_chemistry_count}`",
            "- Invariants: aptamer source object; molecule_type=RNA; chemistry",
            "  RNA or 2F-RNA; nonempty valid RNA core; 20–100 nt; no unresolved",
            "  syntax, molecule, chemistry, or known-motif blocker; S4 fields empty.",
            "- `target_name_raw` is not required at S3.",
            "",
            "## Source conflicts",
            "",
            f"- RDF DNA × U/RNA alphabet conflicts: `{stats.dna_u_conflict_count}`",
            "- These remain parked ssDNA (`t_to_u_applied=false`).",
            "- No automatic reclassification to RNA.",
            "",
            "## Construct review",
            "",
            f"- known-motif proposal records: "
            f"`{stats.known_motif_proposal_record_count}`",
            f"- known-motif proposal rows: `{stats.known_motif_proposal_row_count}`",
            f"- group-consensus proposals: "
            f"`{stats.group_consensus_proposal_record_count}`",
            f"- applied trims: `{stats.applied_trim_count}`",
            "- Group-wise constant-region inference was disabled.",
            "",
            "## CHECKPOINT-1",
            "",
            f"- unique active review records: "
            f"`{stats.unique_checkpoint_review_records}`",
            f"- sequence/source-conflict review: "
            f"`{stats.sequence_notation_review_count}`",
            f"- DNA×U source-conflict review: "
            f"`{stats.source_conflict_review_count}`",
            f"- construct/known-motif review: `{stats.constant_review_count}`",
            f"- length-boundary audit (20–25 and 90–100 among accepts): "
            f"`{stats.boundary_review_count}`",
            f"- lower-boundary condition: `{stats.boundary_low_count}`",
            f"- upper-boundary condition: `{stats.boundary_high_count}`",
            f"- random-kept audit sampled: `{stats.random_accept_audit_count}`",
            f"- random-kept audit pool: `{stats.random_accept_audit_pool_size}`",
            f"- random-kept audit shortfall: "
            f"`{stats.random_accept_audit_shortfall}`",
            "- Human decision fields are blank.",
            "- Machine recommendations are stored separately.",
            "- `ready_for_application = 0` until Laura completes review.",
            "",
            "Active review batches:",
            "",
        ]
    )
    for batch, count in _count_sorted(stats.review_batch_counts):
        lines.append(f"- `{batch}`: `{count}`")
    lines.extend(
        [
            "",
            "## Deferred",
            "",
            f"- blank `target_name_raw`: `{stats.missing_target_raw_count}`",
            f"- S3 `missing_target` rejects: `{stats.missing_target_rejected_count}`",
            f"- Target canonicalised: `{stats.target_canonicalised_count}`",
            f"- Evidence scored: `{stats.evidence_scored_count}`",
            f"- Affinity normalised: `{stats.affinity_normalised_count}`",
            f"- Sequence leakage: `{stats.sequence_leakage_count}`",
            f"- Target leakage: `{stats.target_leakage_count}`",
            "- Target extraction from `label`, interactions, experiments,",
            "  PMID, PDB, UniProt/Pfam, leakage, deduplication, Freebase-ID",
            "  collapse, exact-sequence collapse, clustering, and global S4",
            "  were not run.",
            "- Duplicate Freebase IDs and minimal-aptamer relationships are",
            "  retained for later S5 clustering validation.",
            "",
            "## Integrity",
            "",
            f"- S2 canonical SHA-256: `{result.s2_hash_before}`",
            f"- S3 canonical SHA-256 equals S2: "
            f"`{'yes' if result.s2_integrity_ok else 'no'}`",
            f"- Inputs unchanged during S3: "
            f"`{'yes' if result.inputs_unchanged else 'no'}`",
            f"- Deterministic rerun: "
            f"`{result.deterministic_rerun_ok if result.deterministic_rerun_ok is not None else 'not_requested'}`",
            f"- Eligibility policy: `{_relative_display(policy_path, repo_root)}`",
            "",
            "Outputs (gitignored under `data/`):",
            "",
            f"- `{_relative_display(result.output_canonical, repo_root)}`",
            f"- `{_relative_display(result.output_decisions, repo_root)}`",
            f"- `{_relative_display(result.output_review, repo_root)}`",
            f"- `{_relative_display(result.output_local_detail, repo_root)}`",
            f"- `{_relative_display(result.output_reason_counts, repo_root)}`",
        ]
    )
    if result.output_rejected is not None:
        lines.append(f"- `{_relative_display(result.output_rejected, repo_root)}`")
    if result.output_parked_ssdna is not None:
        lines.append(
            f"- `{_relative_display(result.output_parked_ssdna, repo_root)}`"
        )
    if result.output_parked_molecule_unresolved is not None:
        lines.append(
            f"- `{_relative_display(result.output_parked_molecule_unresolved, repo_root)}`"
        )
    if result.output_parks is not None:
        lines.append(f"- `{_relative_display(result.output_parks, repo_root)}`")
    if result.output_parked_construct is not None:
        lines.append(
            f"- `{_relative_display(result.output_parked_construct, repo_root)}`"
        )
    lines.extend(
        [
            f"- `{_relative_display(result.output_summary, repo_root)}`",
            "",
            APTAMERBASE_PIPELINE_STOP_STATEMENT,
        ]
    )
    return "\n".join(lines) + "\n"


def run_aptamerbase_s3(
    *,
    repo_root: Path,
    input_dir: Path,
    source_metadata_dir: Path,
    eligibility_policy: Path,
    output_dir: Path,
    expected_rows: int | None = EXPECTED_APTAMERBASE_ROWS,
    check_deterministic_rerun: bool = False,
) -> S3RunResult:
    """Execute AptamerBase S3 technical eligibility and CHECKPOINT-1."""
    repo_root = repo_root.resolve()
    input_dir = (
        input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    ).resolve()
    source_metadata_dir = (
        source_metadata_dir
        if source_metadata_dir.is_absolute()
        else (repo_root / source_metadata_dir)
    ).resolve()
    eligibility_policy = (
        eligibility_policy
        if eligibility_policy.is_absolute()
        else (repo_root / eligibility_policy)
    ).resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    canonical_path = input_dir / "aptamerbase_normalised.csv"
    qc_path = input_dir / "aptamerbase_s2_qc.csv"
    sidecar_path = source_metadata_dir / "aptamerbase_source_metadata.csv"
    proposals_path = input_dir / "detected_constants_aptamerbase.csv"
    for path, label in (
        (canonical_path, "S2 canonical"),
        (qc_path, "S2 QC"),
        (sidecar_path, "source-metadata"),
        (proposals_path, "S2 known-motif proposals"),
    ):
        if not path.is_file():
            raise S3ClassifyError(f"Missing {label} input: {path.name}")

    raw_path = (
        repo_root / "data" / "raw" / "aptamerbase" / "aptamerbase_aptamers.csv"
    )
    rdf_path = (
        repo_root
        / "data"
        / "raw"
        / "aptamerbase"
        / "aptamerbase.freebase.extract.nt.gz"
    )
    s1_path = source_metadata_dir / "aptamerbase_extracted.csv"
    raw_sha_before = ""
    rdf_sha_before = ""
    s1_sha_before = ""
    s1_sidecar_sha_before = ""
    check_raw = expected_rows == EXPECTED_APTAMERBASE_ROWS
    if check_raw:
        if not raw_path.is_file():
            raise S3ClassifyError("Missing registered AptamerBase raw CSV")
        raw_sha_before = _sha256_file(raw_path)
        if raw_sha_before != EXPECTED_APTAMERBASE_RAW_CSV_SHA256:
            raise S3ClassifyError(
                "AptamerBase raw CSV SHA-256 does not match registry expectation"
            )
        if rdf_path.is_file():
            rdf_sha_before = _sha256_file(rdf_path)
            if rdf_sha_before != EXPECTED_APTAMERBASE_RAW_RDF_SHA256:
                raise S3ClassifyError(
                    "AptamerBase RDF SHA-256 does not match registry expectation"
                )
        if s1_path.is_file():
            s1_sha_before = _sha256_file(s1_path)
            if s1_sha_before != EXPECTED_APTAMERBASE_S1_CANONICAL_SHA256:
                raise S3ClassifyError(
                    "AptamerBase S1 canonical SHA-256 does not match the frozen S1"
                )
        s1_sidecar_sha_before = _sha256_file(sidecar_path)
        if s1_sidecar_sha_before != EXPECTED_APTAMERBASE_S1_SIDECAR_SHA256:
            raise S3ClassifyError(
                "AptamerBase S1 sidecar SHA-256 does not match the frozen S1"
            )

    s2_hash_before = _sha256_file(canonical_path)
    qc_hash_before = _sha256_file(qc_path)
    sidecar_hash_before = _sha256_file(sidecar_path)
    proposals_hash_before = _sha256_file(proposals_path)
    if check_raw and s2_hash_before != EXPECTED_APTAMERBASE_S2_HASH:
        raise S3ClassifyError(
            "AptamerBase S2 normalised hash does not match the completed S2 milestone"
        )

    policy = load_eligibility_policy(eligibility_policy)
    if policy.source_key != "aptamerbase":
        raise S3ClassifyError(
            f"Eligibility policy source_key must be aptamerbase; "
            f"got {policy.source_key!r}"
        )
    if not policy.defer_target_classification or not policy.defer_evidence_scoring:
        raise S3ClassifyError(
            "AptamerBase S3 policy must defer target classification and "
            "evidence scoring"
        )
    if (
        policy.sequence_leakage_matching_enabled
        or policy.target_leakage_matching_enabled
        or not policy.defer_leakage_exclusion
    ):
        raise S3ClassifyError("AptamerBase S3 must not apply leakage exclusions")
    if not policy.unresolved_trim_blocks_eligibility:
        raise S3ClassifyError(
            "AptamerBase S3 must park unresolved known-motif/construct cases"
        )

    canonical_rows = _read_corpus_csv(canonical_path)
    qc_rows = _read_sidecar_csv(qc_path, label="S2 QC")
    sidecar_rows = _read_sidecar_csv(sidecar_path, label="source-metadata")
    proposal_rows = _read_plain_csv(proposals_path, label="S2 known-motif proposals")
    aligned_qc = _match_sidecar_one_to_one(
        canonical_rows, qc_rows, label="S2 QC"
    )
    aligned_sidecar = _match_sidecar_one_to_one(
        canonical_rows, sidecar_rows, label="source-metadata"
    )
    proposal_index = index_aptamerbase_constant_proposals(
        canonical_rows, proposal_rows
    )

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S3ClassifyError(
            f"S2 row count must be {expected_rows}; got {len(canonical_rows)}"
        )
    if expected_rows == EXPECTED_APTAMERBASE_ROWS:
        _assert_aptamerbase_s2_invariants(canonical_rows)

    stats = AptamerBaseS3Stats()
    stats.s2_rows = len(canonical_rows)
    stats.order_preserved = True
    stats.group_inference_disabled = True
    stats.unique_freebase_ids = len(
        {
            (meta.get("aptamerbase_id") or row["native_id"])
            for row, meta in zip(canonical_rows, aligned_sidecar, strict=True)
        }
    )

    s3_canonical: list[dict[str, str]] = []
    decision_rows: list[dict[str, str]] = []
    rejection_rows: list[dict[str, str]] = []
    parked_ssdna_rows: list[dict[str, str]] = []
    parked_molecule_rows: list[dict[str, str]] = []
    parked_chemistry_rows: list[dict[str, str]] = []
    parked_construct_rows: list[dict[str, str]] = []
    local_detail_by_id: dict[str, dict[str, str]] = {}
    core_by_id = {row["record_id"]: row["sequence_core"] for row in canonical_rows}

    for s2_row, qc_row, meta_row in zip(
        canonical_rows, aligned_qc, aligned_sidecar, strict=True
    ):
        classified = classify_aptamerbase_record(
            s2_row,
            qc_row,
            meta_row,
            policy=policy,
            proposals=proposal_index.get(s2_row["record_id"], ()),
        )
        if classified.canonical["record_id"] != s2_row["record_id"]:
            stats.order_preserved = False
            raise S3ClassifyError("S3 altered record_id or row identity")
        for column in CORPUS_COLUMNS:
            if classified.canonical[column] != s2_row[column]:
                raise S3ClassifyError(
                    f"S3 altered S2 canonical field {column!r}"
                )
        s3_canonical.append(classified.canonical)
        decision_rows.append(classified.decision)
        if classified.rejection_row is not None:
            rejection_rows.append(classified.rejection_row)
        if classified.park_row is not None:
            if classified.primary_route == APTAMERBASE_PRIMARY_ROUTE_SSDNA:
                parked_ssdna_rows.append(classified.park_row)
            elif classified.primary_route == APTAMERBASE_PRIMARY_ROUTE_MOLECULE:
                parked_molecule_rows.append(classified.park_row)
            elif classified.primary_route == APTAMERBASE_PRIMARY_ROUTE_CHEMISTRY_REVIEW:
                parked_chemistry_rows.append(classified.park_row)
            elif classified.primary_route == APTAMERBASE_PRIMARY_ROUTE_CONSTRUCT:
                parked_construct_rows.append(classified.park_row)
            else:
                raise S3ClassifyError(
                    f"Park row has unexpected primary_route {classified.primary_route}"
                )
        local_detail_by_id[classified.canonical["record_id"]] = (
            build_aptamerbase_local_detail_row(
                canonical=classified.canonical,
                s2_qc=qc_row,
                source_metadata=meta_row,
                decision=classified.decision,
            )
        )
        update_aptamerbase_stats_from_row(stats, classified)

    sampled, pool, shortfall = apply_aptamerbase_random_accept_audit(
        decision_rows,
        local_detail_by_id,
        seed=policy.random_seed,
        sample_size=policy.random_accept_audit_size,
    )
    stats.random_accept_audit_pool_size = pool
    stats.random_accept_audit_shortfall = shortfall
    refresh_aptamerbase_stats_after_audit(stats, decision_rows)

    stats.s3_rows = len(s3_canonical)
    stats.unique_record_ids = len({row["record_id"] for row in s3_canonical})
    stats.unique_native_ids = len({row["native_id"] for row in s3_canonical})

    if stats.s3_rows != len(canonical_rows):
        raise S3ClassifyError("S3 must preserve every S2 row")
    if stats.unique_record_ids != len(s3_canonical):
        raise S3ClassifyError("S3 record_id values are not unique")
    if len({row["record_id"] for row in decision_rows}) != len(decision_rows):
        raise S3ClassifyError("Decision sidecar contains duplicate record_id values")

    rejected_n = stats.primary_route_counts.get(APTAMERBASE_PRIMARY_ROUTE_REJECT, 0)
    parked_ssdna_n = stats.primary_route_counts.get(APTAMERBASE_PRIMARY_ROUTE_SSDNA, 0)
    parked_molecule_n = stats.primary_route_counts.get(
        APTAMERBASE_PRIMARY_ROUTE_MOLECULE, 0
    )
    parked_chemistry_n = stats.primary_route_counts.get(
        APTAMERBASE_PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0
    )
    parked_construct_n = stats.primary_route_counts.get(
        APTAMERBASE_PRIMARY_ROUTE_CONSTRUCT, 0
    )
    eligible_n = stats.primary_route_counts.get(APTAMERBASE_PRIMARY_ROUTE_ELIGIBLE, 0)
    if (
        rejected_n
        + parked_ssdna_n
        + parked_molecule_n
        + parked_chemistry_n
        + parked_construct_n
        + eligible_n
        != stats.s3_rows
    ):
        raise S3ClassifyError(
            "technical_rejects + parked lanes + technically_eligible "
            "does not equal S3 rows"
        )
    if len(rejection_rows) != rejected_n:
        raise S3ClassifyError(
            "Rejection log count does not match technical_reject route"
        )
    if len(parked_ssdna_rows) != parked_ssdna_n:
        raise S3ClassifyError("Parked ssDNA count does not match parked_ssdna route")
    if len(parked_molecule_rows) != parked_molecule_n:
        raise S3ClassifyError(
            "Unresolved-molecule park count does not match parked_molecule_unresolved"
        )
    if len(parked_chemistry_rows) != parked_chemistry_n:
        raise S3ClassifyError(
            "Chemistry-review park count does not match parked_chemistry_review"
        )
    if len(parked_construct_rows) != parked_construct_n:
        raise S3ClassifyError(
            "Construct-review park count does not match parked_construct_review"
        )
    if sampled != stats.random_accept_audit_count:
        raise S3ClassifyError("Random-accept audit count mismatch")
    if stats.group_consensus_proposal_record_count != 0:
        raise S3ClassifyError(
            "AptamerBase S3 unexpectedly found group-consensus proposals"
        )
    if stats.target_canonicalised_count or stats.evidence_scored_count:
        raise S3ClassifyError(
            "AptamerBase S3 must not canonicalise target or evidence"
        )
    if stats.affinity_normalised_count:
        raise S3ClassifyError("AptamerBase S3 must not normalise affinity")
    if stats.missing_target_rejected_count != 0:
        raise S3ClassifyError("AptamerBase S3 must not emit missing_target rejects")
    if stats.applied_trim_count != 0 or stats.core_differs_from_full != 0:
        raise S3ClassifyError("AptamerBase S3 must not apply a trim")

    park_id_sets = [
        {row["record_id"] for row in parked_ssdna_rows},
        {row["record_id"] for row in parked_molecule_rows},
        {row["record_id"] for row in parked_chemistry_rows},
        {row["record_id"] for row in parked_construct_rows},
    ]
    for i, left in enumerate(park_id_sets):
        for right in park_id_sets[i + 1 :]:
            if left & right:
                raise S3ClassifyError(
                    "A record must not appear in more than one park sidecar"
                )

    for row in decision_rows:
        if not row["primary_reason"]:
            raise S3ClassifyError("Decision row missing primary_reason")
        if row.get("primary_reason") == "missing_target":
            raise S3ClassifyError("AptamerBase S3 must not reject missing_target")
        if row.get("target_name_raw"):
            raise S3ClassifyError("AptamerBase S3 must leave target_name_raw empty")

    assert_aptamerbase_accept_invariants(decision_rows)
    assert_aptamerbase_reject_park_invariants(decision_rows)

    reason_count_rows: list[dict[str, str]] = []
    combo_counts: dict[tuple[str, str], int] = {}
    for row in decision_rows:
        key = (row["proposed_decision"], row["primary_reason"])
        combo_counts[key] = combo_counts.get(key, 0) + 1
    for (decision, reason), count in sorted(combo_counts.items()):
        reason_count_rows.append(
            {
                "proposed_decision": decision,
                "primary_reason": reason,
                "record_count": str(count),
            }
        )
    if sum(int(row["record_count"]) for row in reason_count_rows) != len(decision_rows):
        raise S3ClassifyError("Reason counts do not reconcile to decision rows")

    review_rows = sorted(decision_rows, key=review_sort_key)
    local_detail_rows: list[dict[str, str]] = []
    for review_row in review_rows:
        record_id = review_row["record_id"]
        if record_id not in local_detail_by_id:
            raise S3ClassifyError(
                f"Missing local-detail row for record_id={record_id!r}"
            )
        detail = local_detail_by_id[record_id]
        if detail["sequence_core"] != core_by_id[record_id]:
            raise S3ClassifyError("CHECKPOINT-1 must not apply constant-region trims")
        if detail.get("manual_decision"):
            raise S3ClassifyError("Local-detail must not pre-fill manual_decision")
        for field_name in (
            "manual_sequence_corrected",
            "manual_molecule_type_override",
            "manual_trim_action",
        ):
            if detail.get(field_name):
                raise S3ClassifyError(
                    f"Local-detail must not pre-fill {field_name}"
                )
        local_detail_rows.append(detail)
    for review_row, detail_row in zip(review_rows, local_detail_rows, strict=True):
        if review_row["record_id"] != detail_row["record_id"]:
            raise S3ClassifyError(
                "Local-detail ordering does not match sequence-free review"
            )
        if review_row["review_batch"] != detail_row.get("review_batch", ""):
            raise S3ClassifyError("Local-detail review_batch mismatch")

    forbidden_seq_cols = {"sequence_raw", "sequence_full", "sequence_core"}
    for col in forbidden_seq_cols:
        if col in APTAMERBASE_DECISION_COLUMNS or col in APTAMERBASE_PARK_COLUMNS:
            raise S3ClassifyError(f"Sequence column leaked into sidecar schema: {col}")
    for col in ("sequence_raw", "sequence_full", "sequence_core"):
        if col not in APTAMERBASE_LOCAL_DETAIL_COLUMNS:
            raise S3ClassifyError(
                f"Local-detail schema missing required sequence column: {col}"
            )

    review_ids = [
        row["record_id"]
        for row in review_rows
        if row.get("manual_review_required") == "true"
    ]
    if len(review_ids) != len(set(review_ids)):
        raise S3ClassifyError("CHECKPOINT-1 review rows are duplicated")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_canonical = output_dir / "aptamerbase_s3_canonical.csv"
    out_decisions = output_dir / "aptamerbase_s3_decisions.csv"
    out_review = output_dir / "aptamerbase_checkpoint1_review.csv"
    out_local_detail = output_dir / "aptamerbase_checkpoint1_local_detail.csv"
    out_reason_counts = output_dir / "aptamerbase_checkpoint1_reason_counts.csv"
    out_rejected = output_dir / "rejected_aptamerbase.csv"
    out_parked_ssdna = output_dir / "aptamerbase_s3_parked_ssdna.csv"
    out_parked_molecule = (
        output_dir / "aptamerbase_s3_parked_molecule_unresolved.csv"
    )
    out_parks = output_dir / "aptamerbase_s3_parked_chemistry_review.csv"
    out_parked_construct = output_dir / "aptamerbase_s3_parked_construct_review.csv"
    out_summary = output_dir / "aptamerbase_checkpoint1_summary.md"

    write_corpus_csv_atomic(out_canonical, s3_canonical)
    write_csv_atomic(
        out_decisions, APTAMERBASE_DECISION_COLUMNS, decision_rows, quoting=csv.QUOTE_ALL
    )
    write_csv_atomic(
        out_review, APTAMERBASE_DECISION_COLUMNS, review_rows, quoting=csv.QUOTE_ALL
    )
    write_csv_atomic(
        out_local_detail,
        APTAMERBASE_LOCAL_DETAIL_COLUMNS,
        local_detail_rows,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        out_reason_counts, APTAMERBASE_REASON_COUNT_COLUMNS, reason_count_rows
    )
    write_csv_atomic(
        out_rejected, APTAMERBASE_REJECTION_COLUMNS, rejection_rows, quoting=csv.QUOTE_ALL
    )
    write_csv_atomic(
        out_parked_ssdna,
        APTAMERBASE_PARK_COLUMNS,
        parked_ssdna_rows,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        out_parked_molecule,
        APTAMERBASE_PARK_COLUMNS,
        parked_molecule_rows,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        out_parks, APTAMERBASE_PARK_COLUMNS, parked_chemistry_rows, quoting=csv.QUOTE_ALL
    )
    write_csv_atomic(
        out_parked_construct,
        APTAMERBASE_PARK_COLUMNS,
        parked_construct_rows,
        quoting=csv.QUOTE_ALL,
    )

    s2_hash_after = _sha256_file(canonical_path)
    qc_hash_after = _sha256_file(qc_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    proposals_hash_after = _sha256_file(proposals_path)
    raw_sha_after = raw_sha_before
    if check_raw:
        raw_sha_after = _sha256_file(raw_path)
        if raw_sha_after != EXPECTED_APTAMERBASE_RAW_CSV_SHA256:
            raise S3ClassifyError("AptamerBase raw SHA-256 changed during S3")
        if rdf_path.is_file() and _sha256_file(rdf_path) != rdf_sha_before:
            raise S3ClassifyError("AptamerBase RDF SHA-256 changed during S3")
        if s1_path.is_file() and _sha256_file(s1_path) != s1_sha_before:
            raise S3ClassifyError("AptamerBase S1 canonical SHA-256 changed during S3")
    inputs_unchanged = (
        s2_hash_before == s2_hash_after
        and qc_hash_before == qc_hash_after
        and sidecar_hash_before == sidecar_hash_after
        and proposals_hash_before == proposals_hash_after
        and (not check_raw or raw_sha_before == raw_sha_after)
    )
    if not inputs_unchanged:
        raise S3ClassifyError("S2/source inputs were modified during S3 execution")

    s2_integrity_ok = True
    if _sha256_file(out_canonical) != s2_hash_before:
        raise S3ClassifyError(
            "S3 canonical output is not byte-identical to S2 normalised input"
        )

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "canonical": _sha256_file(out_canonical),
            "decisions": _sha256_file(out_decisions),
            "review": _sha256_file(out_review),
            "local_detail": _sha256_file(out_local_detail),
            "reason_counts": _sha256_file(out_reason_counts),
            "rejected": _sha256_file(out_rejected),
            "parked_ssdna": _sha256_file(out_parked_ssdna),
            "parked_molecule": _sha256_file(out_parked_molecule),
            "parks": _sha256_file(out_parks),
            "parked_construct": _sha256_file(out_parked_construct),
        }
        second = run_aptamerbase_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        second_hashes = {
            "canonical": _sha256_file(second.output_canonical),
            "decisions": _sha256_file(second.output_decisions),
            "review": _sha256_file(second.output_review),
            "local_detail": _sha256_file(second.output_local_detail),
            "reason_counts": _sha256_file(second.output_reason_counts),
            "rejected": _sha256_file(second.output_rejected),
            "parked_ssdna": _sha256_file(second.output_parked_ssdna),
            "parked_molecule": _sha256_file(second.output_parked_molecule_unresolved),
            "parks": _sha256_file(second.output_parks),
            "parked_construct": _sha256_file(second.output_parked_construct),
        }
        deterministic_ok = first_hashes == second_hashes
        if not deterministic_ok:
            raise S3ClassifyError(
                "S3 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S3RunResult(
        source_key="aptamerbase",
        stats=stats,
        output_canonical=out_canonical,
        output_decisions=out_decisions,
        output_review=out_review,
        output_local_detail=out_local_detail,
        output_summary=out_summary,
        output_reason_counts=out_reason_counts,
        output_leakage_matches=None,
        s2_hash_before=s2_hash_before,
        s2_hash_after=s2_hash_after,
        qc_hash_before=qc_hash_before,
        qc_hash_after=qc_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        s2_integrity_ok=s2_integrity_ok,
        output_rejected=out_rejected,
        output_parks=out_parks,
        output_parked_ssdna=out_parked_ssdna,
        output_parked_non_protein=None,
        output_parked_molecule_unresolved=out_parked_molecule,
        output_parked_construct=out_parked_construct,
        raw_sha_before=raw_sha_before,
        raw_sha_after=raw_sha_after,
    )
    summary_text = build_aptamerbase_checkpoint1_summary(
        repo_root=repo_root,
        result=run_result,
        policy_path=eligibility_policy,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must not contain absolute repository paths"
        )
    if APTAMERBASE_PIPELINE_STOP_STATEMENT not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing pipeline stop statement")
    if "group-wise constant-region inference was disabled" not in summary_text.lower():
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must state that group-wise inference was disabled"
        )
    if "Evidence scored" not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing evidence deferral")
    _write_text_atomic(out_summary, summary_text)
    return run_result


def _aptadiff_production_profile(source_key: str) -> dict[str, object]:
    if source_key == "aptadiff_a":
        return {
            "expected_rows": EXPECTED_APTADIFF_A_ROWS,
            "source_dataset": EXPECTED_APTADIFF_A_SOURCE_DATASET,
            "raw_path": EXPECTED_APTADIFF_A_RAW_PATH,
            "raw_sha256": EXPECTED_APTADIFF_A_RAW_SHA256,
            "s1_canonical_sha256": EXPECTED_APTADIFF_A_S1_CANONICAL_SHA256,
            "s1_sidecar_sha256": EXPECTED_APTADIFF_A_S1_SIDECAR_SHA256,
            "s2_hash": EXPECTED_APTADIFF_A_S2_HASH,
            "parked": EXPECTED_APTADIFF_A_PARKED,
            "rejected": EXPECTED_APTADIFF_A_REJECT,
        }
    if source_key == "aptadiff_b":
        return {
            "expected_rows": EXPECTED_APTADIFF_B_ROWS,
            "source_dataset": EXPECTED_APTADIFF_B_SOURCE_DATASET,
            "raw_path": EXPECTED_APTADIFF_B_RAW_PATH,
            "raw_sha256": EXPECTED_APTADIFF_B_RAW_SHA256,
            "s1_canonical_sha256": EXPECTED_APTADIFF_B_S1_CANONICAL_SHA256,
            "s1_sidecar_sha256": EXPECTED_APTADIFF_B_S1_SIDECAR_SHA256,
            "s2_hash": EXPECTED_APTADIFF_B_S2_HASH,
            "parked": EXPECTED_APTADIFF_B_PARKED,
            "rejected": EXPECTED_APTADIFF_B_REJECT,
        }
    raise S3ClassifyError(
        f"Unknown AptaDiff S3 source_key={source_key!r}; expected "
        "aptadiff_a or aptadiff_b"
    )


def _assert_aptadiff_s2_invariants(
    canonical_rows: Sequence[Mapping[str, str]],
    *,
    source_key: str,
) -> None:
    profile = APTADIFF_SOURCE_PROFILES[source_key]
    molecule_counts: dict[str, int] = {}
    chemistry_counts: dict[str, int] = {}
    alphabet_counts: dict[str, int] = {}
    t_to_u = 0
    core_differs = 0
    nonempty_target = 0
    nonempty_forbidden = 0
    length_36 = 0
    for row in canonical_rows:
        if row.get("source_db") != source_key:
            raise S3ClassifyError(
                f"S2 source_db must be {source_key}; got {row.get('source_db')!r}"
            )
        molecule = row.get("molecule_type") or "unknown"
        molecule_counts[molecule] = molecule_counts.get(molecule, 0) + 1
        chemistry = row.get("chemistry") or "unknown"
        chemistry_counts[chemistry] = chemistry_counts.get(chemistry, 0) + 1
        alphabet = row.get("alphabet_as_reported") or "missing"
        alphabet_counts[alphabet] = alphabet_counts.get(alphabet, 0) + 1
        if row.get("t_to_u_applied") == "true":
            t_to_u += 1
        if row.get("sequence_core") != row.get("sequence_full"):
            core_differs += 1
        if row.get("target_name_raw"):
            nonempty_target += 1
        if any(row.get(field) for field in (
            "target_name",
            "target_uniprot",
            "target_type",
            "binding_evidence_type",
            "binding_evidence_score",
            "affinity_value",
            "affinity_unit",
            "affinity_type",
        )):
            nonempty_forbidden += 1
        if row.get("sequence_length_core") == "36":
            length_36 += 1
        if row.get("construct_scope") != "random_region_only":
            raise S3ClassifyError(
                "AptaDiff S2 construct_scope must remain random_region_only"
            )
    if molecule_counts != {"ssDNA": profile.expected_input_rows}:
        raise S3ClassifyError(f"S2 molecule_type counts drifted: {molecule_counts}")
    if chemistry_counts != {"DNA": profile.expected_input_rows}:
        raise S3ClassifyError(f"S2 chemistry counts drifted: {chemistry_counts}")
    if alphabet_counts.get("DNA_T", 0) != profile.expected_acgt_only:
        raise S3ClassifyError(f"S2 DNA_T count drifted: {alphabet_counts}")
    if alphabet_counts.get("ambiguous", 0) != profile.expected_n_containing:
        raise S3ClassifyError(f"S2 ambiguous count drifted: {alphabet_counts}")
    if t_to_u != 0:
        raise S3ClassifyError("AptaDiff S2 must not have applied T→U")
    if core_differs != 0:
        raise S3ClassifyError("AptaDiff S2 must keep sequence_core == sequence_full")
    if nonempty_target != 0:
        raise S3ClassifyError("AptaDiff S2 must keep target_name_raw empty")
    if nonempty_forbidden != 0:
        raise S3ClassifyError("AptaDiff S2 must not populate deferred S4 fields")
    if length_36 != profile.expected_length_36:
        raise S3ClassifyError("AptaDiff S2 length-36 count drifted")


def build_aptadiff_checkpoint1_summary(
    *,
    repo_root: Path,
    result: S3RunResult,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown CHECKPOINT-1 summary (no sequences)."""
    stats = result.stats
    if not isinstance(stats, AptaDiffS3Stats):
        raise S3ClassifyError("AptaDiff summary requires AptaDiffS3Stats")
    source_key = result.source_key
    label = "Dataset A" if source_key == "aptadiff_a" else "Dataset B"

    def _count(mapping: Mapping[str, int], key: str) -> int:
        return int(mapping.get(key, 0))

    rejected = _count(stats.primary_route_counts, APTADIFF_PRIMARY_ROUTE_REJECT)
    parked_ssdna = _count(stats.primary_route_counts, APTADIFF_PRIMARY_ROUTE_SSDNA)
    eligible = _count(stats.primary_route_counts, APTADIFF_PRIMARY_ROUTE_ELIGIBLE)
    routed_sum = rejected + parked_ssdna + eligible
    documented = aptadiff_expected_documented_target(source_key)

    lines = [
        f"# AptaDiff {label} S3 / CHECKPOINT-1 summary",
        "",
        "## Reconciliation",
        "",
        f"- source_key = `{source_key}`",
        f"- experimental molecule = `ssDNA`",
        f"- chemistry = `DNA`",
        f"- rows in = `{stats.s2_rows}`",
        f"- technical rejects = `{rejected}`",
        f"- parked ssDNA = `{parked_ssdna}`",
        f"- technically eligible RNA = `{eligible}`",
        f"- sum = `{routed_sum}`",
        f"- Unique record IDs: `{stats.unique_record_ids}`",
        f"- Unique native IDs: `{stats.unique_native_ids}`",
        f"- S2 order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        "",
        "Technical sequence failure is applied before ordinary ssDNA parking.",
        "A malformed DNA record is a technical failure, not a hidden DNA park.",
        "",
        "## Technical rejection breakdown",
        "",
        f"- `ambiguous_bases`: `{_count(stats.primary_reason_counts, 'ambiguous_bases')}`",
        f"- `missing_sequence`: `{_count(stats.primary_reason_counts, 'missing_sequence')}`",
        f"- `length_out_of_range`: `{_count(stats.primary_reason_counts, 'length_out_of_range')}`",
        f"- `mixed_T_and_U`: `{_count(stats.primary_reason_counts, 'mixed_T_and_U')}`",
        f"- `alignment_gaps`: `{_count(stats.primary_reason_counts, 'alignment_gaps')}`",
        f"- `invalid_alphabet`: `{_count(stats.primary_reason_counts, 'invalid_alphabet')}`",
        "",
        "Condition tallies (a record may contribute to more than one):",
        "",
        f"- ambiguous-bases condition: `{stats.ambiguous_bases_count}`",
        f"- missing-sequence condition: `{stats.missing_sequence_count}`",
        f"- mixed T/U condition: `{stats.mixed_t_u_count}`",
        f"- alignment-gaps condition: `{stats.alignment_gaps_count}`",
        f"- invalid-alphabet condition: `{stats.invalid_alphabet_count}`",
        f"- length-out-of-range condition: `{stats.length_out_of_range_count}`",
        "",
        "## Parking",
        "",
        f"- source ssDNA total before technical rejection = `{stats.source_ssdna_before_technical}`",
        f"- technically rejected ssDNA = `{stats.technically_rejected_ssdna}`",
        f"- actually parked ssDNA = `{parked_ssdna}`",
        f"- ordinary clean ssDNA parks do not require manual scientific review",
        "",
        "## Eligible corpus lane",
        "",
        f"- technically eligible RNA = `{eligible}`",
        "- No RNA records are technically eligible because the source contract is ssDNA.",
        "",
        "## CHECKPOINT-1",
        "",
        f"- unique review records: `{stats.unique_checkpoint_review_records}`",
        f"- judgement-dependent technical records: "
        f"`{stats.judgement_dependent_review_count}`",
        f"- constant-proposal records in review: `{stats.constant_review_count}`",
        f"- boundary-length records in review: `{stats.boundary_review_count}`",
        f"- random kept audit sampled: `{stats.random_accept_audit_count}`",
        f"- random kept audit pool: `{stats.random_accept_audit_pool_size}`",
        f"- random kept audit shortfall: `{stats.random_accept_audit_shortfall}`",
        "- Zero technically eligible RNA means no fabricated random-kept audit.",
        "",
        "### Counts by checkpoint review reason",
        "",
    ]
    if stats.checkpoint_review_reason_counts:
        for name, count in _count_sorted(stats.checkpoint_review_reason_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")

    lines.extend(["", "### Counts by review batch", ""])
    for batch in (
        "01_judgement_dependent_technical",
        "02_constant_region_proposal",
        "03_length_boundary",
        "04_random_kept_audit",
    ):
        lines.append(f"- `{batch}`: `{_count(stats.review_batch_counts, batch)}`")

    lines.extend(
        [
            "",
            "## Deferred / not performed",
            "",
            f"- Documented sidecar target ({documented}) remains provenance only.",
            "- Canonical `target_name_raw` remains empty.",
            "- Target canonicalisation, UniProt, target type/family, evidence,",
            "  affinity, leakage, capping, clustering, balancing and partitioning",
            "  remain deferred. `p6` is preserved uninterpreted and is not a gate.",
            "- Constant-region inference remains disabled. Applied trims = 0.",
            "- Dataset-A replication (`corpus_replication_datasetA.csv`) is not",
            "  built here. Whether a later replication file should preserve all",
            "  P6 rows or the x_z 13,802-row consumed set is deferred.",
            "",
            "- Target type inferred: `no`",
            "- Evidence scored: `no`",
            "- Leakage exclusions applied: `no`",
            "- Constant-region proposals applied: `no`",
            "- T→U applied: `no`",
            "- Human CHECKPOINT-1 decisions applied: `no`",
            "- S4 started: `no`",
            "- authorised_for_s4: `0`",
            "",
            "## Integrity",
            "",
            f"- S2 canonical hash before: `{result.s2_hash_before}`",
            f"- S2 canonical hash after: `{result.s2_hash_after}`",
            f"- S2 QC hash before: `{result.qc_hash_before}`",
            f"- S2 QC hash after: `{result.qc_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            f"- S2 input integrity: "
            f"`{'pass' if result.s2_integrity_ok else 'fail'}`",
            f"- Inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            f"- Raw SHA-256 before: `{result.raw_sha_before or 'not_checked'}`",
            f"- Raw SHA-256 after: `{result.raw_sha_after or 'not_checked'}`",
            "",
            "## Inputs",
            "",
            f"- Eligibility policy: `{_relative_display(policy_path, repo_root)}`",
            "",
            "## Outputs",
            "",
            f"- Canonical: `{_relative_display(result.output_canonical, repo_root)}`",
            f"- Decisions: `{_relative_display(result.output_decisions, repo_root)}`",
            f"- Checkpoint review (sequence-free index of all rows): "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Checkpoint local detail (sequence-bearing scientific review): "
            f"`{_relative_display(result.output_local_detail, repo_root)}`",
            f"- Reason counts: "
            f"`{_relative_display(result.output_reason_counts, repo_root)}`",
        ]
    )
    if result.output_rejected is not None:
        lines.append(
            f"- Rejection log: `{_relative_display(result.output_rejected, repo_root)}`"
        )
    if result.output_parked_ssdna is not None:
        lines.append(
            f"- Parked ssDNA: "
            f"`{_relative_display(result.output_parked_ssdna, repo_root)}`"
        )
    lines.extend(
        [
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            "## Local-detail warning",
            "",
            f"WARNING: `{source_key}_checkpoint1_local_detail.csv` and",
            f"`rejected_{source_key}.csv` contain source sequences. They must",
            "remain beneath ignored `data/` and must never be staged or tracked.",
            "",
            "## Pipeline stop",
            "",
            APTADIFF_PIPELINE_STOP_STATEMENT,
            "",
            "CHECKPOINT-1 generated = yes",
            "CHECKPOINT-1 human decisions applied = no",
            "records authorised_for_s4 = 0",
            "",
        ]
    )
    return "\n".join(lines)


def run_aptadiff_s3(
    *,
    repo_root: Path,
    source_key: str,
    input_dir: Path,
    source_metadata_dir: Path,
    eligibility_policy: Path,
    output_dir: Path,
    expected_rows: int | None = None,
    check_deterministic_rerun: bool = False,
) -> S3RunResult:
    """Execute AptaDiff A or B S3 technical eligibility and CHECKPOINT-1."""
    if source_key not in {"aptadiff_a", "aptadiff_b"}:
        raise S3ClassifyError(
            f"Unknown AptaDiff S3 source_key={source_key!r}; expected "
            "aptadiff_a or aptadiff_b"
        )
    profile = _aptadiff_production_profile(source_key)
    if expected_rows is None:
        expected_rows = int(profile["expected_rows"])

    repo_root = repo_root.resolve()
    input_dir = (
        input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    ).resolve()
    source_metadata_dir = (
        source_metadata_dir
        if source_metadata_dir.is_absolute()
        else (repo_root / source_metadata_dir)
    ).resolve()
    eligibility_policy = (
        eligibility_policy
        if eligibility_policy.is_absolute()
        else (repo_root / eligibility_policy)
    ).resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    canonical_path = input_dir / f"{source_key}_normalised.csv"
    qc_path = input_dir / f"{source_key}_s2_qc.csv"
    sidecar_path = source_metadata_dir / f"{source_key}_source_metadata.csv"
    s1_canonical_path = source_metadata_dir / f"{source_key}_extracted.csv"
    for path, label in (
        (canonical_path, "S2 canonical"),
        (qc_path, "S2 QC"),
        (sidecar_path, "source-metadata"),
    ):
        if not path.is_file():
            raise S3ClassifyError(f"Missing {label} input: {path.name}")

    raw_path = repo_root / str(profile["raw_path"])
    raw_sha_before = ""
    check_raw = expected_rows == profile["expected_rows"]
    if check_raw:
        if not raw_path.is_file():
            raise S3ClassifyError(f"Missing registered {source_key} raw file")
        digest = _sha256_file(raw_path)
        if digest != profile["raw_sha256"]:
            raise S3ClassifyError(
                f"{source_key} raw SHA-256 does not match registry expectation"
            )
        raw_sha_before = digest
        if s1_canonical_path.is_file():
            s1_digest = _sha256_file(s1_canonical_path)
            if s1_digest != profile["s1_canonical_sha256"]:
                raise S3ClassifyError(
                    f"{source_key} S1 canonical SHA-256 does not match freeze"
                )
        sidecar_s1 = _sha256_file(sidecar_path)
        if sidecar_s1 != profile["s1_sidecar_sha256"]:
            raise S3ClassifyError(
                f"{source_key} S1 sidecar SHA-256 does not match freeze"
            )
        s2_digest = _sha256_file(canonical_path)
        if s2_digest != profile["s2_hash"]:
            raise S3ClassifyError(
                f"{source_key} S2 canonical SHA-256 does not match freeze"
            )

    s2_hash_before = _sha256_file(canonical_path)
    qc_hash_before = _sha256_file(qc_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    policy = load_eligibility_policy(eligibility_policy)
    if policy.source_key != source_key:
        raise S3ClassifyError(
            f"Eligibility policy source_key must be {source_key}; "
            f"got {policy.source_key!r}"
        )
    if not policy.defer_target_classification or not policy.defer_evidence_scoring:
        raise S3ClassifyError(
            "AptaDiff S3 policy must defer target classification and evidence scoring"
        )
    if (
        policy.sequence_leakage_matching_enabled
        or policy.target_leakage_matching_enabled
        or not policy.defer_leakage_exclusion
    ):
        raise S3ClassifyError("AptaDiff S3 must not apply leakage exclusions")
    if policy.explicit_non_rna_requires_manual_review:
        raise S3ClassifyError(
            "AptaDiff S3 must not require manual review of ordinary ssDNA parks"
        )

    canonical_rows = _read_corpus_csv(canonical_path)
    qc_rows = _read_sidecar_csv(qc_path, label="S2 QC")
    sidecar_rows = _read_sidecar_csv(sidecar_path, label="source-metadata")
    aligned_qc = _match_sidecar_one_to_one(
        canonical_rows, qc_rows, label="S2 QC"
    )
    aligned_sidecar = _match_sidecar_one_to_one(
        canonical_rows, sidecar_rows, label="source-metadata"
    )

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S3ClassifyError(
            f"S2 row count must be {expected_rows}; got {len(canonical_rows)}"
        )
    if expected_rows == profile["expected_rows"]:
        _assert_aptadiff_s2_invariants(canonical_rows, source_key=source_key)

    documented_target = aptadiff_expected_documented_target(source_key)
    stats = AptaDiffS3Stats()
    stats.s2_rows = len(canonical_rows)
    stats.order_preserved = True

    s3_canonical: list[dict[str, str]] = []
    decision_rows: list[dict[str, str]] = []
    rejection_rows: list[dict[str, str]] = []
    parked_ssdna_rows: list[dict[str, str]] = []
    local_detail_by_id: dict[str, dict[str, str]] = {}
    core_by_id = {row["record_id"]: row["sequence_core"] for row in canonical_rows}

    for s2_row, qc_row, meta_row in zip(
        canonical_rows, aligned_qc, aligned_sidecar, strict=True
    ):
        if check_raw and meta_row.get("aptadiff_documented_target") != documented_target:
            raise S3ClassifyError(
                f"Documented target must remain {documented_target}"
            )
        classified = classify_aptadiff_record(
            s2_row,
            qc_row,
            meta_row,
            policy=policy,
        )
        if classified.canonical["record_id"] != s2_row["record_id"]:
            stats.order_preserved = False
            raise S3ClassifyError("S3 altered record_id or row identity")
        for column in CORPUS_COLUMNS:
            if classified.canonical[column] != s2_row[column]:
                raise S3ClassifyError(
                    f"S3 altered S2 canonical field {column!r}"
                )
        s3_canonical.append(classified.canonical)
        decision_rows.append(classified.decision)
        if classified.rejection_row is not None:
            rejection_rows.append(classified.rejection_row)
        if classified.park_row is not None:
            if classified.primary_route == APTADIFF_PRIMARY_ROUTE_SSDNA:
                parked_ssdna_rows.append(classified.park_row)
            else:
                raise S3ClassifyError(
                    f"Park row has unexpected primary_route {classified.primary_route}"
                )
        local_detail_by_id[classified.canonical["record_id"]] = (
            build_aptadiff_local_detail_row(
                canonical=classified.canonical,
                s2_qc=qc_row,
                source_metadata=meta_row,
                decision=classified.decision,
            )
        )
        update_aptadiff_stats_from_row(stats, classified)

    sampled, pool, shortfall = apply_aptadiff_random_accept_audit(
        decision_rows,
        local_detail_by_id,
        seed=policy.random_seed,
        sample_size=policy.random_accept_audit_size,
    )
    stats.random_accept_audit_pool_size = pool
    stats.random_accept_audit_shortfall = shortfall
    refresh_aptadiff_stats_after_audit(stats, decision_rows)

    stats.s3_rows = len(s3_canonical)
    stats.unique_record_ids = len({row["record_id"] for row in s3_canonical})
    stats.unique_native_ids = len({row["native_id"] for row in s3_canonical})
    stats.constant_region_proposals = 0

    if stats.s3_rows != len(canonical_rows):
        raise S3ClassifyError("S3 must preserve every S2 row")
    if stats.unique_record_ids != len(s3_canonical):
        raise S3ClassifyError("S3 record_id values are not unique")
    if len({row["record_id"] for row in decision_rows}) != len(decision_rows):
        raise S3ClassifyError("Decision sidecar contains duplicate record_id values")

    rejected_n = stats.primary_route_counts.get(APTADIFF_PRIMARY_ROUTE_REJECT, 0)
    parked_ssdna_n = stats.primary_route_counts.get(APTADIFF_PRIMARY_ROUTE_SSDNA, 0)
    eligible_n = stats.primary_route_counts.get(APTADIFF_PRIMARY_ROUTE_ELIGIBLE, 0)
    if rejected_n + parked_ssdna_n + eligible_n != stats.s3_rows:
        raise S3ClassifyError(
            "technical_rejects + parked_ssdna + technically_eligible "
            "does not equal S3 rows"
        )
    if len(rejection_rows) != rejected_n:
        raise S3ClassifyError(
            "Rejection log count does not match technical_reject route"
        )
    if len(parked_ssdna_rows) != parked_ssdna_n:
        raise S3ClassifyError("Parked ssDNA count does not match parked_ssdna route")
    if sampled != stats.random_accept_audit_count:
        raise S3ClassifyError("Random-accept audit count mismatch")
    if eligible_n != 0 and pool == 0:
        raise S3ClassifyError("RNA-eligible rows exist but audit pool is empty")
    if eligible_n == 0 and sampled != 0:
        raise S3ClassifyError(
            "Zero technically eligible RNA must not fabricate a random-kept audit"
        )
    if stats.t_to_u_applied_count != 0:
        raise S3ClassifyError("AptaDiff S3 must not apply T→U")
    if stats.applied_trims != 0:
        raise S3ClassifyError("AptaDiff S3 must not apply trims")
    if stats.sequence_repaired_count != 0:
        raise S3ClassifyError("AptaDiff S3 must not repair N-containing sequences")
    if stats.nonempty_canonical_target_fields != 0:
        raise S3ClassifyError("AptaDiff S3 must not populate deferred S4 fields")
    if stats.sequence_leakage_count != 0 or stats.target_leakage_count != 0:
        raise S3ClassifyError("AptaDiff S3 must not apply leakage exclusions")

    if expected_rows == profile["expected_rows"]:
        if parked_ssdna_n != profile["parked"]:
            raise S3ClassifyError(
                f"{source_key} parked ssDNA must be {profile['parked']}; "
                f"got {parked_ssdna_n}"
            )
        if rejected_n != profile["rejected"]:
            raise S3ClassifyError(
                f"{source_key} technical rejects must be {profile['rejected']}; "
                f"got {rejected_n}"
            )
        if eligible_n != 0:
            raise S3ClassifyError(
                f"{source_key} technically eligible RNA must be 0; got {eligible_n}"
            )
        if stats.unique_checkpoint_review_records != profile["rejected"]:
            raise S3ClassifyError(
                f"{source_key} active CHECKPOINT review must be "
                f"{profile['rejected']}; got {stats.unique_checkpoint_review_records}"
            )
        if stats.random_accept_audit_count != 0:
            raise S3ClassifyError(
                f"{source_key} random-kept audit must be 0; "
                f"got {stats.random_accept_audit_count}"
            )
        if stats.random_accept_audit_pool_size != 0:
            raise S3ClassifyError(
                f"{source_key} random-kept audit pool must be 0"
            )
        if stats.constant_review_count != 0 or stats.boundary_review_count != 0:
            raise S3ClassifyError(
                f"{source_key} must not create trim or length-boundary review"
            )

    for row in decision_rows:
        if not row["primary_reason"]:
            raise S3ClassifyError("Decision row missing primary_reason")

    assert_aptadiff_accept_invariants(decision_rows)
    assert_aptadiff_reject_park_invariants(decision_rows)

    reason_count_rows: list[dict[str, str]] = []
    combo_counts: dict[tuple[str, str], int] = {}
    for row in decision_rows:
        key = (row["proposed_decision"], row["primary_reason"])
        combo_counts[key] = combo_counts.get(key, 0) + 1
    for (decision, reason), count in sorted(combo_counts.items()):
        reason_count_rows.append(
            {
                "proposed_decision": decision,
                "primary_reason": reason,
                "record_count": str(count),
            }
        )
    if sum(int(row["record_count"]) for row in reason_count_rows) != len(decision_rows):
        raise S3ClassifyError("Reason counts do not reconcile to decision rows")

    review_rows = sorted(decision_rows, key=review_sort_key)
    local_detail_rows: list[dict[str, str]] = []
    for review_row in review_rows:
        record_id = review_row["record_id"]
        if record_id not in local_detail_by_id:
            raise S3ClassifyError(
                f"Missing local-detail row for record_id={record_id!r}"
            )
        detail = local_detail_by_id[record_id]
        if detail["sequence_core"] != core_by_id[record_id]:
            raise S3ClassifyError("CHECKPOINT-1 must not apply constant-region trims")
        if detail.get("manual_decision"):
            raise S3ClassifyError("Local-detail must not pre-fill manual_decision")
        for field_name in (
            "manual_sequence_corrected",
            "manual_molecule_type_override",
            "manual_trim_action",
            "manual_notes",
        ):
            if detail.get(field_name):
                raise S3ClassifyError(
                    f"Local-detail must not pre-fill {field_name}"
                )
        local_detail_rows.append(detail)
    for review_row, detail_row in zip(review_rows, local_detail_rows, strict=True):
        if review_row["record_id"] != detail_row["record_id"]:
            raise S3ClassifyError(
                "Local-detail ordering does not match sequence-free review"
            )
        if review_row["review_batch"] != detail_row.get("review_batch", ""):
            raise S3ClassifyError("Local-detail review_batch mismatch")

    forbidden_seq_cols = {"sequence_raw", "sequence_full", "sequence_core"}
    for col in forbidden_seq_cols:
        if col in APTADIFF_DECISION_COLUMNS or col in APTADIFF_PARK_COLUMNS:
            raise S3ClassifyError(f"Sequence column leaked into sidecar schema: {col}")
    for col in ("sequence_raw", "sequence_full", "sequence_core"):
        if col not in APTADIFF_LOCAL_DETAIL_COLUMNS:
            raise S3ClassifyError(
                f"Local-detail schema missing required sequence column: {col}"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_canonical = output_dir / f"{source_key}_s3_canonical.csv"
    out_decisions = output_dir / f"{source_key}_s3_decisions.csv"
    out_review = output_dir / f"{source_key}_checkpoint1_review.csv"
    out_local_detail = output_dir / f"{source_key}_checkpoint1_local_detail.csv"
    out_reason_counts = output_dir / f"{source_key}_checkpoint1_reason_counts.csv"
    out_rejected = output_dir / f"rejected_{source_key}.csv"
    out_parked_ssdna = output_dir / f"{source_key}_s3_parked_ssdna.csv"
    out_summary = output_dir / f"{source_key}_checkpoint1_summary.md"

    write_corpus_csv_atomic(out_canonical, s3_canonical)
    write_csv_atomic(out_decisions, APTADIFF_DECISION_COLUMNS, decision_rows)
    write_csv_atomic(out_review, APTADIFF_DECISION_COLUMNS, review_rows)
    write_csv_atomic(out_local_detail, APTADIFF_LOCAL_DETAIL_COLUMNS, local_detail_rows)
    write_csv_atomic(out_reason_counts, APTADIFF_REASON_COUNT_COLUMNS, reason_count_rows)
    write_csv_atomic(out_rejected, APTADIFF_REJECTION_COLUMNS, rejection_rows)
    write_csv_atomic(out_parked_ssdna, APTADIFF_PARK_COLUMNS, parked_ssdna_rows)

    s2_hash_after = _sha256_file(canonical_path)
    qc_hash_after = _sha256_file(qc_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    raw_sha_after = raw_sha_before
    if check_raw:
        digest = _sha256_file(raw_path)
        if digest != profile["raw_sha256"]:
            raise S3ClassifyError(f"{source_key} raw SHA-256 changed during S3")
        raw_sha_after = digest
        if s1_canonical_path.is_file():
            if _sha256_file(s1_canonical_path) != profile["s1_canonical_sha256"]:
                raise S3ClassifyError(f"{source_key} S1 canonical hash changed during S3")
        if _sha256_file(sidecar_path) != profile["s1_sidecar_sha256"]:
            raise S3ClassifyError(f"{source_key} S1 sidecar hash changed during S3")
    inputs_unchanged = (
        s2_hash_before == s2_hash_after
        and qc_hash_before == qc_hash_after
        and sidecar_hash_before == sidecar_hash_after
        and (not check_raw or raw_sha_before == raw_sha_after)
    )
    if not inputs_unchanged:
        raise S3ClassifyError("S2/source inputs were modified during S3 execution")

    s2_integrity_ok = True
    if _sha256_file(out_canonical) != s2_hash_before:
        raise S3ClassifyError(
            "S3 canonical output is not byte-identical to S2 normalised input"
        )

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "canonical": _sha256_file(out_canonical),
            "decisions": _sha256_file(out_decisions),
            "review": _sha256_file(out_review),
            "local_detail": _sha256_file(out_local_detail),
            "reason_counts": _sha256_file(out_reason_counts),
            "rejected": _sha256_file(out_rejected),
            "parked_ssdna": _sha256_file(out_parked_ssdna),
        }
        second = run_aptadiff_s3(
            repo_root=repo_root,
            source_key=source_key,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        second_hashes = {
            "canonical": _sha256_file(second.output_canonical),
            "decisions": _sha256_file(second.output_decisions),
            "review": _sha256_file(second.output_review),
            "local_detail": _sha256_file(second.output_local_detail),
            "reason_counts": _sha256_file(second.output_reason_counts),
            "rejected": _sha256_file(second.output_rejected)
            if second.output_rejected
            else "",
            "parked_ssdna": _sha256_file(second.output_parked_ssdna)
            if second.output_parked_ssdna
            else "",
        }
        if first_hashes != second_hashes:
            raise S3ClassifyError("Deterministic AptaDiff S3 rerun is not byte-identical")
        deterministic_ok = True

    run_result = S3RunResult(
        source_key=source_key,
        stats=stats,
        output_canonical=out_canonical,
        output_decisions=out_decisions,
        output_review=out_review,
        output_local_detail=out_local_detail,
        output_summary=out_summary,
        output_reason_counts=out_reason_counts,
        output_leakage_matches=None,
        s2_hash_before=s2_hash_before,
        s2_hash_after=s2_hash_after,
        qc_hash_before=qc_hash_before,
        qc_hash_after=qc_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        s2_integrity_ok=s2_integrity_ok,
        output_rejected=out_rejected,
        output_parked_ssdna=out_parked_ssdna,
        raw_sha_before=raw_sha_before,
        raw_sha_after=raw_sha_after,
    )
    summary_text = build_aptadiff_checkpoint1_summary(
        repo_root=repo_root,
        result=run_result,
        policy_path=eligibility_policy,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must not contain absolute repository paths"
        )
    if APTADIFF_PIPELINE_STOP_STATEMENT not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing pipeline stop statement")
    if "authorised_for_s4: `0`" not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary must keep authorised_for_s4 at 0")
    if "Evidence scored: `no`" not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing evidence deferral")
    _write_text_atomic(out_summary, summary_text)
    return run_result


def _ncbi_nuc_raw_hashes(repo_root: Path) -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in EXPECTED_NCBI_NUC_RAW_SHA256.items():
        path = repo_root / relative
        if not path.is_file():
            raise S3ClassifyError(f"Missing registered NCBI Nucleotide file: {relative}")
        digest = _sha256_file(path)
        if digest != expected:
            raise S3ClassifyError(
                f"NCBI Nucleotide raw SHA-256 does not match registry for {relative}"
            )
        observed[relative] = digest
    return observed


def _assert_ncbi_nuc_s2_invariants(canonical_rows: Sequence[dict[str, str]]) -> None:
    """Hard-fail if the accepted NCBI S2 starting invariants drifted."""
    if len(canonical_rows) != EXPECTED_NCBI_NUC_ROWS:
        raise S3ClassifyError(
            f"S3 input rows must be {EXPECTED_NCBI_NUC_ROWS}; got {len(canonical_rows)}"
        )
    record_ids = [row["record_id"] for row in canonical_rows]
    native_ids = [row["native_id"] for row in canonical_rows]
    if len(set(record_ids)) != EXPECTED_NCBI_NUC_ROWS:
        raise S3ClassifyError("S2 record_id values are not unique")
    if len(set(native_ids)) != EXPECTED_NCBI_NUC_ROWS:
        raise S3ClassifyError("S2 native_id values are not unique")
    molecule_counts: dict[str, int] = {}
    rna_ids: set[str] = set()
    dna_ids: set[str] = set()
    for row in canonical_rows:
        molecule = row.get("molecule_type") or ""
        molecule_counts[molecule] = molecule_counts.get(molecule, 0) + 1
        if row.get("sequence_core") != row.get("sequence_full"):
            raise S3ClassifyError(
                "ncbi_nuc S2 starting state requires sequence_core == sequence_full"
            )
        if row.get("source_db") != "ncbi_nuc":
            raise S3ClassifyError("S2 source_db must be ncbi_nuc")
        if row.get("source_dataset") != EXPECTED_NCBI_NUC_SOURCE_DATASET:
            raise S3ClassifyError(
                f"S2 source_dataset must be {EXPECTED_NCBI_NUC_SOURCE_DATASET}"
            )
        if row.get("target_name_raw"):
            raise S3ClassifyError("ncbi_nuc S2 must leave target_name_raw empty")
        for field_name in (
            "target_name",
            "target_type",
            "target_type_source",
            "binding_evidence_score",
            "affinity_value",
            "cluster_id",
            "partition",
            "pdb_id",
        ):
            if row.get(field_name):
                raise S3ClassifyError(
                    f"S2 canonical unexpectedly populated {field_name}"
                )
        native = row.get("native_id") or ""
        if molecule == "RNA":
            rna_ids.add(native)
        elif molecule == "DNA":
            dna_ids.add(native)
    if molecule_counts != EXPECTED_NCBI_NUC_MOLECULE:
        raise S3ClassifyError(f"S2 molecule_type counts drifted: {molecule_counts}")
    if rna_ids != NCBI_NUC_APPROVED_RNA:
        raise S3ClassifyError("Approved RNA ACCESSION set drifted at S3 entry")
    if dna_ids != NCBI_NUC_APPROVED_DNA:
        raise S3ClassifyError("Approved DNA ACCESSION set drifted at S3 entry")


def build_ncbi_nuc_checkpoint1_summary(
    *,
    repo_root: Path,
    result: S3RunResult,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown CHECKPOINT-1 summary (no sequences)."""
    stats = result.stats
    if not isinstance(stats, NcbiNucS3Stats):
        raise S3ClassifyError("NCBI Nucleotide summary requires NcbiNucS3Stats")

    def _count(mapping: Mapping[str, int], key: str) -> int:
        return int(mapping.get(key, 0))

    rejected = _count(stats.primary_route_counts, NCBI_NUC_PRIMARY_ROUTE_REJECT)
    parked = _count(stats.primary_route_counts, NCBI_NUC_PRIMARY_ROUTE_MOLECULE)
    eligible = _count(stats.primary_route_counts, NCBI_NUC_PRIMARY_ROUTE_ELIGIBLE)
    routed_sum = rejected + parked + eligible
    accept_n = _count(stats.decision_counts, "proposed_accept")
    park_n = _count(stats.decision_counts, "proposed_park")
    reject_n = _count(stats.decision_counts, "proposed_reject")

    lines = [
        "# NCBI Nucleotide S3 / CHECKPOINT-1 summary",
        "",
        "Aggregate counts only. Deposited sequences are not included.",
        "",
        "## Reconciliation",
        "",
        f"- Source key: `ncbi_nuc`",
        f"- Source dataset: `{EXPECTED_NCBI_NUC_SOURCE_DATASET}`",
        f"- S2 input rows: `{stats.s2_rows}`",
        f"- S3 output rows: `{stats.s3_rows}`",
        f"- Unique record IDs: `{stats.unique_record_ids}`",
        f"- Unique native IDs: `{stats.unique_native_ids}`",
        f"- proposed_accept: `{accept_n}`",
        f"- proposed_park: `{park_n}`",
        f"- proposed_reject: `{reject_n}`",
        f"- input = eligible + parked + rejected: `{stats.s3_rows} = {eligible} + {parked} + {rejected}`",
        f"- primary-route sum: `{routed_sum}`",
        f"- S2 order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        f"- applied trims: `{stats.applied_trims}`",
        f"- sequence_core == sequence_full: `{stats.core_equals_full}/{stats.s3_rows}`",
        f"- nonempty target_name_raw: `{stats.nonempty_target_name_raw}`",
        f"- nonempty S4 fields: `{stats.nonempty_s4_fields}`",
        f"- authorised_for_s4: `0`",
        "",
        "## Primary reasons",
        "",
    ]
    for reason, count in sorted(stats.primary_reason_counts.items()):
        lines.append(f"- `{reason}`: `{count}`")
    lines.extend(
        [
            "",
            "## Secondary technical conditions",
            "",
            "A record may contribute to more than one condition.",
            "",
            f"- length_out_of_range: `{stats.length_out_of_range_count}`",
            f"- ambiguous_bases: `{stats.ambiguous_bases_count}`",
            f"- primer_like: `{stats.primer_like_count}`",
            f"- non_aptamer_source_object: `{stats.non_aptamer_source_object_count}`",
            f"- molecule_type_unresolved: `{stats.molecule_type_unresolved_count}`",
            f"- trim/construct diagnostic: `{stats.trim_construct_unresolved_count}`",
            f"- known-motif proposal: `{stats.known_motif_proposal_count}`",
            f"- mixed T/U: `{stats.mixed_t_u_count}`",
            f"- alignment gaps: `{stats.alignment_gaps_count}`",
            f"- invalid alphabet: `{stats.invalid_alphabet_count}`",
            f"- missing sequence: `{stats.missing_sequence_count}`",
            "",
            "## CHECKPOINT-1 review",
            "",
            f"- manual_review_required true: `{stats.manual_review_required_true_count}`",
            f"- unique active review records: `{stats.unique_checkpoint_review_records}`",
            f"- random-audit pool: `{stats.random_accept_audit_pool_size}`",
            f"- random-audit sample: `{stats.random_accept_audit_count}`",
            f"- random-audit shortfall: `{stats.random_accept_audit_shortfall}`",
            f"- length-boundary audits: `{stats.boundary_review_count}`",
            f"- judgement-dependent reviews: `{stats.judgement_dependent_review_count}`",
            f"- molecule-unresolved reviews: `{stats.molecule_review_count}`",
            f"- construct/motif reviews: `{stats.construct_review_count}`",
            "",
            "Review batches:",
            "",
        ]
    )
    for batch, count in sorted(stats.review_batch_counts.items()):
        lines.append(f"- `{batch}`: `{count}`")
    lines.extend(
        [
            "",
            "Checkpoint review reasons:",
            "",
        ]
    )
    for reason, count in sorted(stats.checkpoint_review_reason_counts.items()):
        lines.append(f"- `{reason}`: `{count}`")
    lines.extend(
        [
            "",
            "## Scientific boundary",
            "",
            "- Target extraction/canonicalisation: deferred.",
            "- Evidence scored: `no`.",
            "- Affinity normalisation: `no`.",
            "- Leakage exclusion: `no`.",
            "- NCBI↔ENA deduplication: `no`.",
            "- Global S4: not run.",
            "- Human fields: blank. Machine recommendations are not decisions.",
            "",
            "## Integrity",
            "",
            f"- Eligibility policy: `{_relative_display(policy_path, repo_root)}`",
            f"- S2 canonical hash: `{result.s2_hash_after}`",
            f"- S2 QC hash: `{result.qc_hash_after}`",
            f"- S1 sidecar hash: `{result.sidecar_hash_after}`",
            f"- Inputs unchanged: `{'pass' if result.inputs_unchanged else 'fail'}`",
            f"- Deterministic rerun: "
            f"`{'pass' if result.deterministic_rerun_ok else ('n/a' if result.deterministic_rerun_ok is None else 'fail')}`",
            "",
            NCBI_NUC_PIPELINE_STOP_STATEMENT,
            "",
        ]
    )
    return "\n".join(lines)


def run_ncbi_nuc_s3(
    *,
    repo_root: Path,
    input_dir: Path,
    source_metadata_dir: Path,
    eligibility_policy: Path,
    output_dir: Path,
    expected_rows: int | None = EXPECTED_NCBI_NUC_ROWS,
    check_deterministic_rerun: bool = False,
) -> S3RunResult:
    """Execute NCBI Nucleotide S3 technical eligibility and CHECKPOINT-1."""
    repo_root = repo_root.resolve()
    input_dir = (
        input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    ).resolve()
    source_metadata_dir = (
        source_metadata_dir
        if source_metadata_dir.is_absolute()
        else (repo_root / source_metadata_dir)
    ).resolve()
    eligibility_policy = (
        eligibility_policy
        if eligibility_policy.is_absolute()
        else (repo_root / eligibility_policy)
    ).resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    canonical_path = input_dir / "ncbi_nuc_normalised.csv"
    qc_path = input_dir / "ncbi_nuc_s2_qc.csv"
    sidecar_path = source_metadata_dir / "ncbi_nuc_source_metadata.csv"
    s1_canonical_path = source_metadata_dir / "ncbi_nuc_extracted.csv"
    proposals_path = input_dir / "detected_constants_ncbi_nuc.csv"
    for path, label in (
        (canonical_path, "S2 canonical"),
        (qc_path, "S2 QC"),
        (sidecar_path, "source-metadata"),
    ):
        if not path.is_file():
            raise S3ClassifyError(f"Missing {label} input: {path.name}")

    check_raw = expected_rows == EXPECTED_NCBI_NUC_ROWS
    raw_sha_before = ""
    if check_raw:
        observed_raw = _ncbi_nuc_raw_hashes(repo_root)
        raw_sha_before = ";".join(
            f"{path}={digest}" for path, digest in sorted(observed_raw.items())
        )
        if s1_canonical_path.is_file():
            s1_digest = _sha256_file(s1_canonical_path)
            if s1_digest != EXPECTED_NCBI_NUC_S1_CANONICAL_SHA256:
                raise S3ClassifyError(
                    "ncbi_nuc S1 canonical SHA-256 does not match freeze"
                )
        sidecar_s1 = _sha256_file(sidecar_path)
        if sidecar_s1 != EXPECTED_NCBI_NUC_S1_SIDECAR_SHA256:
            raise S3ClassifyError("ncbi_nuc S1 sidecar SHA-256 does not match freeze")
        s2_digest = _sha256_file(canonical_path)
        if s2_digest != EXPECTED_NCBI_NUC_S2_HASH:
            raise S3ClassifyError("ncbi_nuc S2 canonical SHA-256 does not match freeze")
        qc_digest = _sha256_file(qc_path)
        if qc_digest != EXPECTED_NCBI_NUC_S2_QC_SHA256:
            raise S3ClassifyError("ncbi_nuc S2 QC SHA-256 does not match freeze")

    s2_hash_before = _sha256_file(canonical_path)
    qc_hash_before = _sha256_file(qc_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    policy = load_eligibility_policy(eligibility_policy)
    if policy.source_key != "ncbi_nuc":
        raise S3ClassifyError(
            f"Eligibility policy source_key must be ncbi_nuc; got {policy.source_key!r}"
        )
    if not policy.defer_target_classification or not policy.defer_evidence_scoring:
        raise S3ClassifyError(
            "ncbi_nuc S3 policy must defer target classification and evidence scoring"
        )
    if (
        policy.sequence_leakage_matching_enabled
        or policy.target_leakage_matching_enabled
        or not policy.defer_leakage_exclusion
    ):
        raise S3ClassifyError("ncbi_nuc S3 must not apply leakage exclusions")

    canonical_rows = _read_corpus_csv(canonical_path)
    qc_rows = _read_sidecar_csv(qc_path, label="S2 QC")
    sidecar_rows = _read_sidecar_csv(sidecar_path, label="source-metadata")
    aligned_qc = _match_sidecar_one_to_one(canonical_rows, qc_rows, label="S2 QC")
    aligned_sidecar = _match_sidecar_one_to_one(
        canonical_rows, sidecar_rows, label="source-metadata"
    )
    proposals = (
        read_ncbi_nuc_constant_proposals(proposals_path)
        if proposals_path.is_file()
        else []
    )
    proposals_by_record = index_ncbi_nuc_constant_proposals(proposals)

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S3ClassifyError(
            f"S2 row count must be {expected_rows}; got {len(canonical_rows)}"
        )
    if expected_rows == EXPECTED_NCBI_NUC_ROWS:
        _assert_ncbi_nuc_s2_invariants(canonical_rows)

    stats = NcbiNucS3Stats()
    stats.s2_rows = len(canonical_rows)
    stats.order_preserved = True

    s3_canonical: list[dict[str, str]] = []
    decision_rows: list[dict[str, str]] = []
    rejection_rows: list[dict[str, str]] = []
    park_rows: list[dict[str, str]] = []
    local_detail_by_id: dict[str, dict[str, str]] = {}
    core_by_id = {row["record_id"]: row["sequence_core"] for row in canonical_rows}

    for s2_row, qc_row, meta_row in zip(
        canonical_rows, aligned_qc, aligned_sidecar, strict=True
    ):
        classified = classify_ncbi_nuc_record(
            s2_row,
            qc_row,
            meta_row,
            policy=policy,
            proposals=proposals_by_record.get(s2_row["record_id"], ()),
        )
        if classified.canonical["record_id"] != s2_row["record_id"]:
            stats.order_preserved = False
            raise S3ClassifyError("S3 altered record_id or row identity")
        for column in CORPUS_COLUMNS:
            if classified.canonical[column] != s2_row[column]:
                raise S3ClassifyError(f"S3 altered S2 canonical field {column!r}")
        s3_canonical.append(classified.canonical)
        decision_rows.append(classified.decision)
        if classified.rejection_row is not None:
            rejection_rows.append(classified.rejection_row)
        if classified.park_row is not None:
            park_rows.append(classified.park_row)
        local_detail_by_id[classified.canonical["record_id"]] = (
            build_ncbi_nuc_local_detail_row(
                canonical=classified.canonical,
                s2_qc=qc_row,
                decision=classified.decision,
            )
        )
        update_ncbi_nuc_stats_from_row(stats, classified)

    sampled, pool, shortfall = apply_ncbi_nuc_random_accept_audit(
        decision_rows,
        local_detail_by_id,
        seed=policy.random_seed,
        sample_size=policy.random_accept_audit_size,
    )
    stats.random_accept_audit_pool_size = pool
    stats.random_accept_audit_shortfall = shortfall
    refresh_ncbi_nuc_stats_after_audit(stats, decision_rows)

    stats.s3_rows = len(s3_canonical)
    stats.unique_record_ids = len({row["record_id"] for row in s3_canonical})
    stats.unique_native_ids = len({row["native_id"] for row in s3_canonical})

    if stats.s3_rows != len(canonical_rows):
        raise S3ClassifyError("S3 must preserve every S2 row")
    if stats.unique_record_ids != len(s3_canonical):
        raise S3ClassifyError("S3 record_id values are not unique")
    accept_n = stats.decision_counts.get("proposed_accept", 0)
    park_n = stats.decision_counts.get("proposed_park", 0)
    reject_n = stats.decision_counts.get("proposed_reject", 0)
    if accept_n + park_n + reject_n != stats.s3_rows:
        raise S3ClassifyError("accept + park + reject does not equal S3 rows")
    if len(rejection_rows) != reject_n:
        raise S3ClassifyError("Rejection log count does not match proposed_reject")
    if len(park_rows) != park_n:
        raise S3ClassifyError("Park sidecar count does not match proposed_park")
    if sampled != stats.random_accept_audit_count:
        raise S3ClassifyError("Random-accept audit count mismatch")
    if sampled > pool:
        raise S3ClassifyError("Random-accept audit fabricated rows beyond the pool")
    if stats.applied_trims != 0:
        raise S3ClassifyError("ncbi_nuc S3 must not apply trims")
    if stats.nonempty_target_name_raw != 0:
        raise S3ClassifyError("ncbi_nuc S3 must not populate target_name_raw")
    if stats.nonempty_s4_fields != 0:
        raise S3ClassifyError("ncbi_nuc S3 must not populate S4 fields")

    for row in decision_rows:
        if not row["primary_reason"]:
            raise S3ClassifyError("Decision row missing primary_reason")

    assert_ncbi_nuc_accept_invariants(decision_rows)
    assert_ncbi_nuc_reject_park_invariants(decision_rows)

    reason_count_rows: list[dict[str, str]] = []
    combo_counts: dict[tuple[str, str], int] = {}
    for row in decision_rows:
        key = (row["proposed_decision"], row["primary_reason"])
        combo_counts[key] = combo_counts.get(key, 0) + 1
    for (decision, reason), count in sorted(combo_counts.items()):
        reason_count_rows.append(
            {
                "proposed_decision": decision,
                "primary_reason": reason,
                "record_count": str(count),
            }
        )
    if sum(int(row["record_count"]) for row in reason_count_rows) != len(decision_rows):
        raise S3ClassifyError("Reason counts do not reconcile to decision rows")

    review_rows = sorted(decision_rows, key=review_sort_key)
    local_detail_rows: list[dict[str, str]] = []
    for review_row in review_rows:
        record_id = review_row["record_id"]
        if record_id not in local_detail_by_id:
            raise S3ClassifyError(f"Missing local-detail row for record_id={record_id!r}")
        detail = local_detail_by_id[record_id]
        if detail["sequence_core"] != core_by_id[record_id]:
            raise S3ClassifyError("CHECKPOINT-1 must not apply trims")
        if detail.get("manual_decision"):
            raise S3ClassifyError("Local-detail must not pre-fill manual_decision")
        local_detail_rows.append(detail)
    for review_row, detail_row in zip(review_rows, local_detail_rows, strict=True):
        if review_row["record_id"] != detail_row["record_id"]:
            raise S3ClassifyError(
                "Local-detail ordering does not match sequence-free review"
            )
        if review_row["review_batch"] != detail_row.get("review_batch", ""):
            raise S3ClassifyError("Local-detail review_batch mismatch")

    forbidden_seq_cols = {"sequence_raw", "sequence_full", "sequence_core"}
    for col in forbidden_seq_cols:
        if col in NCBI_NUC_DECISION_COLUMNS or col in NCBI_NUC_PARK_COLUMNS:
            raise S3ClassifyError(f"Sequence column leaked into sidecar schema: {col}")
    for col in ("sequence_raw", "sequence_full", "sequence_core"):
        if col not in NCBI_NUC_LOCAL_DETAIL_COLUMNS:
            raise S3ClassifyError(
                f"Local-detail schema missing required sequence column: {col}"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_canonical = output_dir / "ncbi_nuc_s3_canonical.csv"
    out_decisions = output_dir / "ncbi_nuc_s3_decisions.csv"
    out_review = output_dir / "ncbi_nuc_checkpoint1_review.csv"
    out_local_detail = output_dir / "ncbi_nuc_checkpoint1_local_detail.csv"
    out_reason_counts = output_dir / "ncbi_nuc_checkpoint1_reason_counts.csv"
    out_rejected = output_dir / "rejected_ncbi_nuc.csv"
    out_parked = output_dir / "ncbi_nuc_s3_parked.csv"
    out_summary = output_dir / "ncbi_nuc_checkpoint1_summary.md"

    write_corpus_csv_atomic(out_canonical, s3_canonical)
    write_csv_atomic(out_decisions, NCBI_NUC_DECISION_COLUMNS, decision_rows)
    write_csv_atomic(out_review, NCBI_NUC_DECISION_COLUMNS, review_rows)
    write_csv_atomic(out_local_detail, NCBI_NUC_LOCAL_DETAIL_COLUMNS, local_detail_rows)
    write_csv_atomic(out_reason_counts, NCBI_NUC_REASON_COUNT_COLUMNS, reason_count_rows)
    write_csv_atomic(out_rejected, NCBI_NUC_REJECTION_COLUMNS, rejection_rows)
    write_csv_atomic(out_parked, NCBI_NUC_PARK_COLUMNS, park_rows)

    s2_hash_after = _sha256_file(canonical_path)
    qc_hash_after = _sha256_file(qc_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    raw_sha_after = raw_sha_before
    if check_raw:
        observed_after = _ncbi_nuc_raw_hashes(repo_root)
        raw_sha_after = ";".join(
            f"{path}={digest}" for path, digest in sorted(observed_after.items())
        )
        if s1_canonical_path.is_file():
            if _sha256_file(s1_canonical_path) != EXPECTED_NCBI_NUC_S1_CANONICAL_SHA256:
                raise S3ClassifyError("ncbi_nuc S1 canonical hash changed during S3")
        if _sha256_file(sidecar_path) != EXPECTED_NCBI_NUC_S1_SIDECAR_SHA256:
            raise S3ClassifyError("ncbi_nuc S1 sidecar hash changed during S3")
        if _sha256_file(canonical_path) != EXPECTED_NCBI_NUC_S2_HASH:
            raise S3ClassifyError("ncbi_nuc S2 canonical hash changed during S3")
        if _sha256_file(qc_path) != EXPECTED_NCBI_NUC_S2_QC_SHA256:
            raise S3ClassifyError("ncbi_nuc S2 QC hash changed during S3")
    inputs_unchanged = (
        s2_hash_before == s2_hash_after
        and qc_hash_before == qc_hash_after
        and sidecar_hash_before == sidecar_hash_after
        and (not check_raw or raw_sha_before == raw_sha_after)
    )
    if not inputs_unchanged:
        raise S3ClassifyError("S2/source inputs were modified during S3 execution")

    s2_integrity_ok = True
    if _sha256_file(out_canonical) != s2_hash_before:
        raise S3ClassifyError(
            "S3 canonical output is not byte-identical to S2 normalised input"
        )

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "canonical": _sha256_file(out_canonical),
            "decisions": _sha256_file(out_decisions),
            "review": _sha256_file(out_review),
            "local_detail": _sha256_file(out_local_detail),
            "reason_counts": _sha256_file(out_reason_counts),
            "rejected": _sha256_file(out_rejected),
            "parked": _sha256_file(out_parked),
        }
        second = run_ncbi_nuc_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["canonical"] == _sha256_file(second.output_canonical)
            and first_hashes["decisions"] == _sha256_file(second.output_decisions)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["local_detail"] == _sha256_file(second.output_local_detail)
            and first_hashes["reason_counts"] == _sha256_file(second.output_reason_counts)
            and first_hashes["rejected"] == _sha256_file(second.output_rejected)
            and first_hashes["parked"] == _sha256_file(second.output_parks)
        )
        if not deterministic_ok:
            raise S3ClassifyError(
                "S3 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S3RunResult(
        source_key="ncbi_nuc",
        stats=stats,
        output_canonical=out_canonical,
        output_decisions=out_decisions,
        output_review=out_review,
        output_local_detail=out_local_detail,
        output_summary=out_summary,
        output_reason_counts=out_reason_counts,
        output_leakage_matches=None,
        s2_hash_before=s2_hash_before,
        s2_hash_after=s2_hash_after,
        qc_hash_before=qc_hash_before,
        qc_hash_after=qc_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        s2_integrity_ok=s2_integrity_ok,
        output_rejected=out_rejected,
        output_parks=out_parked,
        raw_sha_before=raw_sha_before,
        raw_sha_after=raw_sha_after,
    )
    summary_text = build_ncbi_nuc_checkpoint1_summary(
        repo_root=repo_root,
        result=run_result,
        policy_path=eligibility_policy,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must not contain absolute repository paths"
        )
    if NCBI_NUC_PIPELINE_STOP_STATEMENT not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing pipeline stop statement")
    if "authorised_for_s4: `0`" not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary must keep authorised_for_s4 at 0")
    if "Evidence scored: `no`" not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing evidence deferral")
    _write_text_atomic(out_summary, summary_text)
    return run_result


def run_s3_classification(
    *,
    repo_root: Path,
    source_key: str,
    input_dir: Path,
    source_metadata_dir: Path,
    leakage_set: Path,
    target_aliases: Path,
    eligibility_policy: Path,
    output_dir: Path,
    expected_rows: int | None = None,
    check_deterministic_rerun: bool = False,
) -> S3RunResult:
    """Dispatch S3 classification for one source key."""
    if source_key == "aptabase":
        return run_aptabase_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            leakage_set=leakage_set,
            target_aliases=target_aliases,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=(
                EXPECTED_APTABASE_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "utexas":
        return run_utexas_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=(
                EXPECTED_UTEXAS_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "aptadb":
        return run_aptadb_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=(
                EXPECTED_APTADB_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "riboaptamer":
        return run_riboaptamer_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=(
                EXPECTED_RIBOAPTAMER_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "aptaindex":
        return run_aptaindex_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=(
                EXPECTED_APTAINDEX_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "ena":
        return run_ena_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=(
                EXPECTED_ENA_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "aptamerbase":
        return run_aptamerbase_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=(
                EXPECTED_APTAMERBASE_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key in {"aptadiff_a", "aptadiff_b"}:
        return run_aptadiff_s3(
            repo_root=repo_root,
            source_key=source_key,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=expected_rows,
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "ncbi_nuc":
        return run_ncbi_nuc_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=(
                EXPECTED_NCBI_NUC_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    raise S3ClassifyError(f"Unknown S3 source_key={source_key!r}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "S3: classify normalised source records into provisional "
            "accept/park/reject decisions and emit CHECKPOINT-1 artefacts."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source key to classify (e.g. aptabase)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Directory containing S2 outputs (default: data/interim/normalised)",
    )
    parser.add_argument(
        "--source-metadata-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing S1 source-metadata sidecar "
            "(default: data/interim/extracted)"
        ),
    )
    parser.add_argument(
        "--leakage-set",
        type=Path,
        default=None,
        help="Leakage exclusion set CSV",
    )
    parser.add_argument(
        "--target-aliases",
        type=Path,
        default=None,
        help="Tracked target-alias CSV",
    )
    parser.add_argument(
        "--eligibility-policy",
        type=Path,
        default=None,
        help="Source-specific eligibility policy JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory beneath data/interim "
            "(default: data/interim/checkpoints/aptabase_cp1)"
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detected)",
    )
    parser.add_argument(
        "--expected-rows",
        type=int,
        default=None,
        help="Override expected row count (tests only)",
    )
    parser.add_argument(
        "--check-deterministic-rerun",
        action="store_true",
        help="Re-run once and require byte-identical outputs",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        repo_root = (
            args.repo_root.resolve()
            if args.repo_root is not None
            else find_repo_root(Path(__file__).resolve())
        )
        if not repo_root.is_dir():
            raise S3ClassifyError(f"Repository root does not exist: {repo_root}")

        input_dir = (
            args.input_dir
            if args.input_dir is not None
            else Path("data/interim/normalised")
        )
        source_metadata_dir = (
            args.source_metadata_dir
            if args.source_metadata_dir is not None
            else Path("data/interim/extracted")
        )
        leakage_set = (
            args.leakage_set
            if args.leakage_set is not None
            else Path("data/interim/leakage_exclusion_set.csv")
        )
        target_aliases = (
            args.target_aliases
            if args.target_aliases is not None
            else Path("config/leakage_target_aliases.csv")
        )
        if args.eligibility_policy is not None:
            policy_path = args.eligibility_policy
        elif args.source == "aptabase":
            policy_path = Path("config/source_eligibility/aptabase.json")
        elif args.source == "utexas":
            policy_path = Path("config/source_eligibility/utexas.json")
        elif args.source == "aptadb":
            policy_path = Path("config/source_eligibility/aptadb.json")
        elif args.source == "riboaptamer":
            policy_path = Path("config/source_eligibility/riboaptamer.json")
        elif args.source == "aptaindex":
            policy_path = Path("config/source_eligibility/aptaindex.json")
        elif args.source == "ena":
            policy_path = Path("config/source_eligibility/ena.json")
        elif args.source == "aptamerbase":
            policy_path = Path("config/source_eligibility/aptamerbase.json")
        elif args.source == "aptadiff_a":
            policy_path = Path("config/source_eligibility/aptadiff_a.json")
        elif args.source == "aptadiff_b":
            policy_path = Path("config/source_eligibility/aptadiff_b.json")
        elif args.source == "ncbi_nuc":
            policy_path = Path("config/source_eligibility/ncbi_nuc.json")
        else:
            raise S3ClassifyError(
                "--eligibility-policy is required for unknown sources"
            )
        if args.output_dir is not None:
            output_dir = args.output_dir
        elif args.source == "utexas":
            output_dir = Path("data/interim/checkpoints/utexas_cp1")
        elif args.source == "aptadb":
            output_dir = Path("data/interim/checkpoints/aptadb_cp1")
        elif args.source == "riboaptamer":
            output_dir = Path("data/interim/checkpoints/riboaptamer_cp1")
        elif args.source == "aptaindex":
            output_dir = Path("data/interim/checkpoints/aptaindex_cp1")
        elif args.source == "ena":
            output_dir = Path("data/interim/checkpoints/ena_cp1")
        elif args.source == "aptamerbase":
            output_dir = Path("data/interim/checkpoints/aptamerbase_cp1")
        elif args.source == "aptadiff_a":
            output_dir = Path("data/interim/checkpoints/aptadiff_a_cp1")
        elif args.source == "aptadiff_b":
            output_dir = Path("data/interim/checkpoints/aptadiff_b_cp1")
        elif args.source == "ncbi_nuc":
            output_dir = Path("data/interim/checkpoints/ncbi_nuc_cp1")
        else:
            output_dir = Path("data/interim/checkpoints/aptabase_cp1")

        result = run_s3_classification(
            repo_root=repo_root,
            source_key=args.source,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            leakage_set=leakage_set,
            target_aliases=target_aliases,
            eligibility_policy=policy_path,
            output_dir=output_dir,
            expected_rows=args.expected_rows,
            check_deterministic_rerun=args.check_deterministic_rerun,
        )
    except (
        S3ClassifyError,
        AptaBaseS3Error,
        UTexasS3Error,
        AptaDBS3Error,
        RiboAptamerS3Error,
        AptaIndexS3Error,
        EnaS3Error,
        AptamerBaseS3Error,
        AptaDiffS3Error,
        NcbiNucS3Error,
        EligibilityError,
        CorpusSchemaError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    stats = result.stats
    # Aggregate counts only — never print sequence values.
    print(
        f"source={result.source_key}\n"
        f"s2_rows={stats.s2_rows}\n"
        f"s3_rows={stats.s3_rows}\n"
        f"unique_record_ids={stats.unique_record_ids}\n"
        f"proposed_accept={stats.decision_counts.get('proposed_accept', 0)}\n"
        f"proposed_park={stats.decision_counts.get('proposed_park', 0)}\n"
        f"proposed_reject={stats.decision_counts.get('proposed_reject', 0)}\n"
        f"sequence_leakage={getattr(stats, 'sequence_leakage_count', 0)}\n"
        f"target_leakage={getattr(stats, 'target_leakage_count', 0)}\n"
        f"both_leakage={getattr(stats, 'both_leakage_count', 0)}\n"
        f"manual_review_required={getattr(stats, 'manual_review_required_true_count', 0)}\n"
        f"multiple_reasons={getattr(stats, 'multiple_reasons_count', 0)}\n"
        f"inputs_unchanged={'pass' if result.inputs_unchanged else 'fail'}\n"
        f"s2_integrity={'pass' if result.s2_integrity_ok else 'fail'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
