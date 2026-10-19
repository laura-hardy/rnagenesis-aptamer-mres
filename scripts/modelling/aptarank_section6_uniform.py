#!/usr/bin/env python3
"""Section 6 exact-length uniform controls.

The stream is platform-independent SHA-256. It does not use Python's
``random`` module, NumPy, or a filesystem. Production role files are not
opened. The deployed AptaRank UI remains the scorer.
"""

from __future__ import annotations

import hashlib

UNIFORM_DOMAIN = "aptarank-section6-uniform-v1"
MASTER_SEED = 42
NUCLEOTIDES = "ACGU"
REJECTION_THRESHOLD = 252
ATTEMPT_CAP = 10000
DIGEST_ALPHABET = "0123456789abcdef"


class Section6Error(ValueError):
    """Fail-closed Section 6 method error."""

    def __init__(self, code, detail, *, rerun_lineage_required=False):
        self.code = code
        self.detail = detail
        self.rerun_lineage_required = rerun_lineage_required
        super().__init__(code + ": " + detail)


def length_delimited_bytes(components):
    """Encode text as uint32-be lengths plus UTF-8 bytes.

    The layout matches the M9B-2 encoder for text components. Integers enter
    only after canonical decimal rendering, with no sign and no leading zeros.
    """
    chunks = []
    for component in components:
        if type(component) is not str:
            raise Section6Error("encoding_invalid", "a length-delimited component is not text")
        blob = component.encode("utf-8")
        if len(blob) > 0xFFFFFFFF:
            raise Section6Error("encoding_invalid", "a length-delimited component is too long")
        chunks.append(len(blob).to_bytes(4, "big"))
        chunks.append(blob)
    return b"".join(chunks)


def canonical_decimal(value):
    """Render a nonnegative integer without a sign or leading zeros."""
    if type(value) is not int or value < 0:
        raise Section6Error("encoding_invalid", "a counter component is not a nonnegative integer")
    return str(value)


def nucleotide_from_byte(value):
    """Map one digest byte. Bytes 252-255 are discarded so ``byte % 4`` is unbiased."""
    if type(value) is not int or value < 0 or value > 255:
        raise Section6Error("byte_invalid", "a stream byte is outside 0-255")
    if value >= REJECTION_THRESHOLD:
        return None
    return NUCLEOTIDES[value % 4]


def core_digest(sequence):
    """SHA-256 of a canonical uppercase A/C/G/U sequence, as lowercase hex."""
    if type(sequence) is not str or not sequence or any(base not in NUCLEOTIDES for base in sequence):
        raise Section6Error("sequence_invalid", "a sequence is not canonical uppercase A, C, G and U")
    return hashlib.sha256(sequence.encode("utf-8")).hexdigest()


def _digest_text(value):
    return (
        type(value) is str
        and len(value) == 64
        and all(character in DIGEST_ALPHABET for character in value)
    )


def is_sha256_text(value):
    """True when ``value`` is 64 lowercase hexadecimal characters."""
    return _digest_text(value)


def stream_digest(parent_digest, attempt, block):
    """One SHA-256 block for a parent, attempt, and block counter."""
    if not _digest_text(parent_digest):
        raise Section6Error("parent_digest_invalid", "the parent sequence_core_sha256 is not lowercase hex")
    payload = length_delimited_bytes(
        [
            UNIFORM_DOMAIN,
            canonical_decimal(MASTER_SEED),
            parent_digest,
            canonical_decimal(attempt),
            canonical_decimal(block),
        ]
    )
    return hashlib.sha256(payload).digest()


def draw_attempt(parent_digest, attempt, length):
    """Draw one exact-length string. Discarded bytes are not mapped."""
    if type(length) is not int or length < 1:
        raise Section6Error("length_invalid", "a control length must be a positive integer")
    if type(attempt) is not int or attempt < 0 or attempt >= ATTEMPT_CAP:
        raise Section6Error("attempt_invalid", "an attempt index is outside 0-9999")
    nucleotides = []
    block = 0
    while len(nucleotides) < length:
        for value in stream_digest(parent_digest, attempt, block):
            nucleotide = nucleotide_from_byte(value)
            if nucleotide is None:
                continue
            nucleotides.append(nucleotide)
            if len(nucleotides) == length:
                break
        block += 1
    return "".join(nucleotides)


def normalize_inventory(inventory):
    """Copy a caller-supplied digest inventory. Paths and sequences are refused."""
    if inventory is None or isinstance(inventory, (str, bytes, bytearray)):
        raise Section6Error("inventory_invalid", "the known-core inventory must be a collection of digests")
    if callable(getattr(inventory, "__fspath__", None)):
        raise Section6Error("filesystem_path_refused", "a filesystem path argument is refused")
    digests = []
    for item in inventory:
        if not _digest_text(item):
            raise Section6Error(
                "inventory_digest_invalid",
                "an inventory entry is not a lowercase SHA-256 digest",
            )
        digests.append(item)
    return set(digests)


def draw_uniform_control(parent_digest, length, rejected_digests):
    """Accept the first attempt whose digest is outside the rejection set.

    Attempts are 0 through 9999. The rejection set is the caller-supplied
    known-core inventory plus controls already accepted by the caller. After
    10000 rejected attempts the draw fails closed and returns no sequence.
    """
    rejected = set(rejected_digests)
    for attempt in range(ATTEMPT_CAP):
        sequence = draw_attempt(parent_digest, attempt, length)
        digest = core_digest(sequence)
        if digest in rejected:
            continue
        return {
            "sequence": sequence,
            "source_digest": digest,
            "accepted_attempt": attempt,
            "length": length,
        }
    raise Section6Error(
        "attempt_cap_exhausted",
        "uniform control generation failed closed after 10000 attempts",
    )


def generate_uniform_controls(parents, inventory):
    """Draw one control per parent, in ascending parent-digest order.

    The caller-supplied inventory must already contain every parent digest.
    Input order does not change the accepted controls. A later control that
    copies an earlier accepted control is resampled. This function does not
    read a role file and does not emit an overlap table.
    """
    if isinstance(parents, (str, bytes, bytearray)) or callable(getattr(parents, "__fspath__", None)):
        raise Section6Error("filesystem_path_refused", "a filesystem path argument is refused")
    if type(parents) is not list or not parents:
        raise Section6Error("parents_invalid", "parents must be a nonempty list of records")
    known = normalize_inventory(inventory)
    prepared = []
    seen_digests = set()
    seen_ids = set()
    for index, parent in enumerate(parents, start=1):
        if type(parent) is not dict:
            raise Section6Error("parents_invalid", "parent %d is not a record" % index)
        sequence = parent.get("sequence")
        digest = core_digest(sequence)
        parent_id = parent.get("parent_core_id")
        cluster_id = parent.get("cluster_id")
        if type(parent_id) is not str or not parent_id or any(character.isspace() for character in parent_id):
            raise Section6Error("parent_id_invalid", "parent %d has no parent-core identifier" % index)
        if type(cluster_id) is not str or not cluster_id or any(character.isspace() for character in cluster_id):
            raise Section6Error("cluster_id_invalid", "parent %d has no cluster identifier" % index)
        if digest in seen_digests:
            raise Section6Error("duplicate_parent_sequence", "a parent sequence is duplicated")
        if parent_id in seen_ids:
            raise Section6Error("duplicate_parent_core", "a parent-core identifier is duplicated")
        seen_digests.add(digest)
        seen_ids.add(parent_id)
        prepared.append(
            {
                "parent_core_id": parent_id,
                "cluster_id": cluster_id,
                "sequence": sequence,
                "source_digest": digest,
                "length": len(sequence),
            }
        )
    prepared.sort(key=lambda row: row["source_digest"])
    omitted = [row["source_digest"] for row in prepared if row["source_digest"] not in known]
    if omitted:
        raise Section6Error(
            "missing_parent_digest",
            "the known-core inventory does not contain every input parent source digest",
        )
    rejected = set(known)
    controls = []
    for parent in prepared:
        drawn = draw_uniform_control(parent["source_digest"], parent["length"], rejected)
        rejected.add(drawn["source_digest"])
        controls.append(drawn)
    return prepared, controls
