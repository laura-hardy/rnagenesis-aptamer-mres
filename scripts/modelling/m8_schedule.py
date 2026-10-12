#!/usr/bin/env python3
"""Deterministic M8 raw-attempt schedule.

Pure functions only. This module does not import a model, query a GPU,
read a biological sequence, or write a run directory. The accepted length
vector is a list of integer lengths. Importing this module does not open it.
"""

from __future__ import annotations

import functools
import hashlib
import json

SOURCE_COUNT = 669
RAW_ATTEMPT_TOTAL = 30000
BLOCK_ATTEMPT_TOTAL = 15000
MINIMUM_BIOLOGICAL_LENGTH = 20
MAXIMUM_BIOLOGICAL_LENGTH = 123
EXPECTED_UNIQUE_LENGTHS = 89
FULL_BATCH_SIZE = 16
SEED_BASE_A = 800000
SEED_BASE_B = 900000
EXPECTED_INVOCATIONS_A = 163
EXPECTED_INVOCATIONS_B = 164
EXPECTED_NUCLEOTIDES_A = 830348
EXPECTED_NUCLEOTIDES_B = 830404
LENGTH_VECTOR_SHA256 = "7e6cb523a85116fc38788c336ef50c26e0eccc343712aaea89956a73c485bd3c"
LENGTH_VECTOR_PATH = (
    "/home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1/"
    "ordered_train_length_vector.json"
)

HISTOGRAM_SCHEMA = "m8-empirical-histogram-1"
QUOTA_SCHEMA = "m8-quota-allocation-1"
MASTER_MAP_SCHEMA = "m8-master-attempt-map-1"
INVOCATION_SCHEMA = "m8-invocation-schedule-1"

# Generation-seed namespaces already used by earlier milestones. M8 seeds
# must be disjoint from every one of them.
PROHIBITED_SEED_NAMESPACES = (
    ("validation_draw", (1,)),
    ("excluded_or_training_seeds", (42, 43, 44)),
    ("b0_chunk_seeds", tuple(range(4200, 4300))),
    ("m4_sampling_seed", (43000,)),
    ("m4_m6_m7_invocation_seeds", tuple(range(44000, 44112))),
)


class M8ScheduleError(Exception):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def canonical_bytes(value):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return (text + "\n").encode("utf-8")


def sha256_bytes(data):
    if not isinstance(data, (bytes, bytearray)):
        raise M8ScheduleError("schedule_invalid", "a digest input is not bytes")
    return hashlib.sha256(bytes(data)).hexdigest()


def _require_int(value, detail):
    if isinstance(value, bool) or not isinstance(value, int):
        raise M8ScheduleError("length_vector_invalid", detail)
    return value


def load_length_vector_bytes(raw):
    """Validate the raw JSON bytes of the length-only vector.

    The returned list preserves the file order. Canonical schedule documents
    are built from the multiset of lengths, so that order does not change
    them. The source hash is the hash of these exact bytes.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise M8ScheduleError("length_vector_invalid", "the length vector is not bytes")
    try:
        parsed = json.loads(bytes(raw).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise M8ScheduleError("length_vector_invalid", "the length vector is not UTF-8 JSON")
    if not isinstance(parsed, list):
        raise M8ScheduleError("length_vector_invalid", "the length vector is not a JSON list")
    if len(parsed) != SOURCE_COUNT:
        raise M8ScheduleError("length_vector_invalid", "the length vector does not hold 669 lengths")
    lengths = []
    for item in parsed:
        length = _require_int(item, "a length is not an integer")
        if length < MINIMUM_BIOLOGICAL_LENGTH or length > MAXIMUM_BIOLOGICAL_LENGTH:
            raise M8ScheduleError("length_vector_invalid", "a length is outside 20..123")
        lengths.append(length)
    if len(set(lengths)) != EXPECTED_UNIQUE_LENGTHS:
        raise M8ScheduleError("length_vector_invalid", "the length vector does not have 89 distinct lengths")
    return lengths


def assert_pinned_length_vector(raw):
    digest = sha256_bytes(raw)
    if digest != LENGTH_VECTOR_SHA256:
        raise M8ScheduleError("length_vector_invalid", "the length vector SHA-256 is not the accepted pin")
    return load_length_vector_bytes(raw)


def empirical_histogram(lengths):
    if not isinstance(lengths, list) or len(lengths) != SOURCE_COUNT:
        raise M8ScheduleError("histogram_invalid", "the histogram input is not 669 lengths")
    counts = {}
    for length in lengths:
        length = _require_int(length, "a length is not an integer")
        counts[length] = counts.get(length, 0) + 1
    if sum(counts.values()) != SOURCE_COUNT:
        raise M8ScheduleError("histogram_invalid", "empirical counts do not sum to 669")
    if len(counts) != EXPECTED_UNIQUE_LENGTHS:
        raise M8ScheduleError("histogram_invalid", "the histogram does not have 89 lengths")
    rows = []
    for length in sorted(counts):
        if length < MINIMUM_BIOLOGICAL_LENGTH or length > MAXIMUM_BIOLOGICAL_LENGTH:
            raise M8ScheduleError("histogram_invalid", "a histogram length is outside 20..123")
        rows.append({"biological_length": length, "empirical_count": counts[length]})
    return rows


def histogram_document(lengths):
    rows = empirical_histogram(lengths)
    return {
        "lengths": rows,
        "schema_version": HISTOGRAM_SCHEMA,
        "source_count": SOURCE_COUNT,
        "unique_length_count": len(rows),
    }


def allocate_largest_remainder(count_rows, total, denominator):
    """Hamilton quotas for an explicit length histogram.

    numerator = total * empirical_count. floor is integer division by the
    denominator and remainder is the modulus. Leftover seats go to the
    largest remainders. An exact remainder tie goes to the smaller
    biological length.
    """
    if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
        raise M8ScheduleError("quota_invalid", "the attempt total is not a positive integer")
    if isinstance(denominator, bool) or not isinstance(denominator, int) or denominator <= 0:
        raise M8ScheduleError("quota_invalid", "the quota denominator is not a positive integer")
    rows = []
    floor_total = 0
    for item in count_rows:
        count = item["empirical_count"]
        numerator = total * count
        floor_quota = numerator // denominator
        remainder = numerator % denominator
        rows.append(
            {
                "biological_length": item["biological_length"],
                "empirical_count": count,
                "floor_quota": floor_quota,
                "numerator": numerator,
                "received_extra_seat": False,
                "remainder": remainder,
            }
        )
        floor_total += floor_quota
    seats = total - floor_total
    if seats < 0 or seats > len(rows):
        raise M8ScheduleError("quota_invalid", "the largest-remainder seat count is outside the length set")
    order = sorted(range(len(rows)), key=lambda index: (-rows[index]["remainder"], rows[index]["biological_length"]))
    for seat, index in enumerate(order):
        if seat >= seats:
            break
        rows[index]["received_extra_seat"] = True
    for row in rows:
        row["quota"] = row["floor_quota"] + (1 if row["received_extra_seat"] else 0)
    if sum(row["quota"] for row in rows) != total:
        raise M8ScheduleError("quota_invalid", "quotas do not sum to the attempt total")
    return rows


def largest_remainder_quotas(lengths, total=RAW_ATTEMPT_TOTAL, denominator=SOURCE_COUNT):
    return allocate_largest_remainder(empirical_histogram(lengths), total, denominator)


def split_block_counts(quota_rows):
    """Split each quota into blocks A and B without requiring a 15000 total.

    Even quotas split equally. Odd strata are visited in ascending biological
    length and the extra attempt alternates A, B, A, B, starting with A.
    """
    if not isinstance(quota_rows, list) or not quota_rows:
        raise M8ScheduleError("allocation_invalid", "there are no quota rows")
    rows = []
    give_extra_to_a = True
    expected_length = None
    for source in quota_rows:
        length = _require_int(source["biological_length"], "a quota length is not an integer")
        quota = _require_int(source["quota"], "a quota is not an integer")
        if quota < 0:
            raise M8ScheduleError("allocation_invalid", "a quota is negative")
        if expected_length is not None and length <= expected_length:
            raise M8ScheduleError("allocation_invalid", "quota rows are not strictly ascending by length")
        expected_length = length
        if quota % 2 == 0:
            block_a = quota // 2
            block_b = quota // 2
        else:
            base = quota // 2
            if give_extra_to_a:
                block_a = base + 1
                block_b = base
            else:
                block_a = base
                block_b = base + 1
            give_extra_to_a = not give_extra_to_a
        if abs(block_a - block_b) > 1 or block_a + block_b != quota:
            raise M8ScheduleError("allocation_invalid", "a length split is not balanced")
        row = dict(source)
        row["block_a_count"] = block_a
        row["block_b_count"] = block_b
        rows.append(row)
    return rows


def allocate_blocks(quota_rows):
    rows = split_block_counts(quota_rows)
    if sum(row["block_a_count"] for row in rows) != BLOCK_ATTEMPT_TOTAL:
        raise M8ScheduleError("allocation_invalid", "block A does not total 15000")
    if sum(row["block_b_count"] for row in rows) != BLOCK_ATTEMPT_TOTAL:
        raise M8ScheduleError("allocation_invalid", "block B does not total 15000")
    return rows


def quota_document(lengths):
    rows = allocate_blocks(largest_remainder_quotas(lengths))
    histogram_hash = sha256_bytes(canonical_bytes(histogram_document(lengths)))
    return {
        "block_a_total": BLOCK_ATTEMPT_TOTAL,
        "block_b_total": BLOCK_ATTEMPT_TOTAL,
        "block_rule": "even_equal_odd_strata_ascending_alternate_A_then_B",
        "denominator": SOURCE_COUNT,
        "histogram_sha256": histogram_hash,
        "quota_rule": "largest_remainder_tie_smaller_biological_length",
        "quota_total": RAW_ATTEMPT_TOTAL,
        "rows": rows,
        "schema_version": QUOTA_SCHEMA,
    }


def master_attempt_rows(lengths):
    """30000 rows ordered by length, then block A stratum positions, then block B.

    ``block_stratum_position`` is the index inside that length and block.
    ``block_local_attempt_index`` numbers the block across lengths in this
    same order.
    """
    allocation = quota_document(lengths)["rows"]
    rows = []
    local = {"A": 0, "B": 0}
    for item in allocation:
        length = item["biological_length"]
        for block, count in (("A", item["block_a_count"]), ("B", item["block_b_count"])):
            for position in range(count):
                rows.append(
                    {
                        "block": block,
                        "block_local_attempt_index": local[block],
                        "block_stratum_position": position,
                        "master_attempt_index": len(rows),
                        "requested_biological_length": length,
                    }
                )
                local[block] += 1
    if len(rows) != RAW_ATTEMPT_TOTAL:
        raise M8ScheduleError("master_map_invalid", "the master map does not hold 30000 rows")
    if local["A"] != BLOCK_ATTEMPT_TOTAL or local["B"] != BLOCK_ATTEMPT_TOTAL:
        raise M8ScheduleError("master_map_invalid", "a block-local index range is not 15000")
    return rows


def master_attempt_document(lengths):
    rows = master_attempt_rows(lengths)
    return {
        "order": [
            "requested_biological_length_ascending",
            "block_a_stratum_positions",
            "block_b_stratum_positions",
        ],
        "quota_allocation_sha256": sha256_bytes(canonical_bytes(quota_document(lengths))),
        "rows": rows,
        "row_count": len(rows),
        "schema_version": MASTER_MAP_SCHEMA,
    }


def _invocation_row(block, index, length, batch_size, batch_num, kind, master_indexes):
    if batch_size <= 0 or batch_num <= 0:
        raise M8ScheduleError("invocation_invalid", "a zero-size invocation was requested")
    if kind == "full_group":
        if batch_size != FULL_BATCH_SIZE:
            raise M8ScheduleError("invocation_invalid", "a full group is not batch size 16")
    elif kind == "remainder":
        if batch_num != 1 or batch_size >= FULL_BATCH_SIZE:
            raise M8ScheduleError("invocation_invalid", "a remainder is padded or is not a single batch")
    else:
        raise M8ScheduleError("invocation_invalid", "an invocation kind is unknown")
    if len(master_indexes) != batch_size * batch_num:
        raise M8ScheduleError("invocation_invalid", "an invocation does not cover its line count")
    seed_base = SEED_BASE_A if block == "A" else SEED_BASE_B
    return {
        "batch_num": batch_num,
        "batch_size": batch_size,
        "block": block,
        "generation_seed": seed_base + index,
        "invocation_index": index,
        "kind": kind,
        "line_count": batch_size * batch_num,
        "master_attempt_indexes": list(master_indexes),
        "max_seq_len": length + 1,
        "requested_biological_length": length,
    }


def invocation_rows(lengths, block):
    if block not in ("A", "B"):
        raise M8ScheduleError("invocation_invalid", "the block is not A or B")
    grouped = {}
    order = []
    for row in master_attempt_rows(lengths):
        if row["block"] != block:
            continue
        length = row["requested_biological_length"]
        if length not in grouped:
            grouped[length] = []
            order.append(length)
        grouped[length].append(row["master_attempt_index"])
    if order != sorted(order):
        raise M8ScheduleError("invocation_invalid", "invocation lengths are not ascending")
    invocations = []
    for length in order:
        indexes = grouped[length]
        full_batches, remainder = divmod(len(indexes), FULL_BATCH_SIZE)
        offset = 0
        if full_batches > 0:
            take = full_batches * FULL_BATCH_SIZE
            invocations.append(
                _invocation_row(
                    block,
                    len(invocations),
                    length,
                    FULL_BATCH_SIZE,
                    full_batches,
                    "full_group",
                    indexes[offset : offset + take],
                )
            )
            offset += take
        if remainder > 0:
            invocations.append(
                _invocation_row(
                    block,
                    len(invocations),
                    length,
                    remainder,
                    1,
                    "remainder",
                    indexes[offset:],
                )
            )
    expected = EXPECTED_INVOCATIONS_A if block == "A" else EXPECTED_INVOCATIONS_B
    if len(invocations) != expected:
        raise M8ScheduleError("invocation_invalid", "the invocation count is not the approved count")
    covered = [index for invocation in invocations for index in invocation["master_attempt_indexes"]]
    if len(covered) != BLOCK_ATTEMPT_TOTAL or len(set(covered)) != BLOCK_ATTEMPT_TOTAL:
        raise M8ScheduleError("invocation_invalid", "a block invocation schedule does not cover 15000 attempts")
    return invocations


def invocation_document(lengths, block):
    rows = invocation_rows(lengths, block)
    seed_base = SEED_BASE_A if block == "A" else SEED_BASE_B
    return {
        "block": block,
        "invocations": rows,
        "invocation_count": len(rows),
        "master_attempt_map_sha256": sha256_bytes(canonical_bytes(master_attempt_document(lengths))),
        "schema_version": INVOCATION_SCHEMA,
        "seed_base": seed_base,
        "seed_first": rows[0]["generation_seed"],
        "seed_last": rows[-1]["generation_seed"],
    }


def nucleotide_total(lengths, block):
    field = "block_a_count" if block == "A" else "block_b_count"
    return sum(row["biological_length"] * row[field] for row in quota_document(lengths)["rows"])


def prohibited_generation_seeds():
    seeds = set()
    for _name, values in PROHIBITED_SEED_NAMESPACES:
        seeds.update(values)
    return seeds


def assert_seed_namespaces(invocations_by_block):
    used = []
    for block in ("A", "B"):
        for invocation in invocations_by_block[block]["invocations"]:
            used.append(invocation["generation_seed"])
    if len(used) != len(set(used)):
        raise M8ScheduleError("seed_namespace_invalid", "generation seeds are not unique")
    if prohibited_generation_seeds().intersection(used):
        raise M8ScheduleError("seed_namespace_invalid", "a generation seed uses a prohibited namespace")
    block_a = [invocation["generation_seed"] for invocation in invocations_by_block["A"]["invocations"]]
    block_b = [invocation["generation_seed"] for invocation in invocations_by_block["B"]["invocations"]]
    if block_a != list(range(SEED_BASE_A, SEED_BASE_A + EXPECTED_INVOCATIONS_A)):
        raise M8ScheduleError("seed_namespace_invalid", "block A seeds are not 800000..800162")
    if block_b != list(range(SEED_BASE_B, SEED_BASE_B + EXPECTED_INVOCATIONS_B)):
        raise M8ScheduleError("seed_namespace_invalid", "block B seeds are not 900000..900163")
    if set(block_a).intersection(block_b):
        raise M8ScheduleError("seed_namespace_invalid", "block seed namespaces are not disjoint")
    return True


def _identity_from_documents(histogram, quota, master, block_a, block_b):
    return {
        "block_a_invocation_schedule_sha256": sha256_bytes(canonical_bytes(block_a)),
        "block_b_invocation_schedule_sha256": sha256_bytes(canonical_bytes(block_b)),
        "empirical_histogram_sha256": sha256_bytes(canonical_bytes(histogram)),
        "master_attempt_map_sha256": sha256_bytes(canonical_bytes(master)),
        "quota_allocation_sha256": sha256_bytes(canonical_bytes(quota)),
    }


@functools.lru_cache(maxsize=4)
def _build_schedule_cached(lengths_tuple):
    lengths = list(lengths_tuple)
    histogram = histogram_document(lengths)
    quota = quota_document(lengths)
    master = master_attempt_document(lengths)
    block_a = invocation_document(lengths, "A")
    block_b = invocation_document(lengths, "B")
    invocations = {"A": block_a, "B": block_b}
    assert_seed_namespaces(invocations)
    if nucleotide_total(lengths, "A") != EXPECTED_NUCLEOTIDES_A:
        raise M8ScheduleError("allocation_invalid", "block A nucleotide total is not 830348")
    if nucleotide_total(lengths, "B") != EXPECTED_NUCLEOTIDES_B:
        raise M8ScheduleError("allocation_invalid", "block B nucleotide total is not 830404")
    return {
        "hashes": _identity_from_documents(histogram, quota, master, block_a, block_b),
        "histogram": histogram,
        "invocations": invocations,
        "master_attempt_map": master,
        "quota_allocation": quota,
    }


def build_schedule(lengths):
    if not isinstance(lengths, list):
        raise M8ScheduleError("schedule_invalid", "lengths are not a list")
    for length in lengths:
        _require_int(length, "a length is not an integer")
    return _build_schedule_cached(tuple(lengths))


def schedule_hashes(lengths):
    return dict(build_schedule(lengths)["hashes"])


def hashes_for_pinned_bytes(raw):
    lengths = assert_pinned_length_vector(raw)
    identity = {"source_length_vector_sha256": LENGTH_VECTOR_SHA256}
    identity.update(schedule_hashes(lengths))
    return identity


# Computed from the pinned 669-length vector. Literals so an inactive check
# can compare configuration text without opening the vector.
EXPECTED_SCHEDULE_HASHES = {
    "block_a_invocation_schedule_sha256": "491c47d8df603e6b9277464611ba27da94dc15134b5e8b2290d91962c45cd13e",
    "block_b_invocation_schedule_sha256": "7b66e5f79f5ce9bb44a896371715c707b7093883e40b8adf5963abf49e135b8f",
    "empirical_histogram_sha256": "dc599c637dafa455447551a78b0234c818262d82a86989cc863e09136abcaee3",
    "master_attempt_map_sha256": "a99ac979d430c2145f47f696822ec6cc06627142032aaf2f9c5766ffa1cdc14a",
    "quota_allocation_sha256": "d477d1ffc1d8f3df6f9124b0c613e3beb8891ffa8100b6a5744ac8f9d51aa721",
    "source_length_vector_sha256": LENGTH_VECTOR_SHA256,
}
