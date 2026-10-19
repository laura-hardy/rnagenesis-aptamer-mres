#!/usr/bin/env python3
"""Section 6 summaries of an already exported AptaRank composite.

Higher aptamer-likeness is favourable. Exported scores must be finite and
inside the closed interval [0, 1]. This module does not recompute the five
Tier 1 components, the composite, dinucleotide shuffles, or shuffle p-values.
No deployed AptaRank component-artifact schema has been observed or frozen.
A document that declares the expected scorer and role strings stays unverified,
and the production five-component table stays unavailable. The deployed
AptaRank UI remains the scorer.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from fractions import Fraction

import aptarank_section6_blinding as blinding
import aptarank_section6_uniform as uniform

Section6Error = uniform.Section6Error
BOOTSTRAP_DOMAIN = "aptarank-section6-bootstrap-v1"
BOOTSTRAP_REPLICATES = 10000
BOOTSTRAP_SEED = 42
MINIMUM_DEFINED_REPLICATES = 9500
INCOMPLETENESS_PAIRS = "fewer_than_two_complete_pairs_from_at_least_two_clusters"
INCOMPLETENESS_REPLICATES = "fewer_than_9500_defined_bootstrap_replicates"
VARIANCE_FORMULA = "n(n+1)(2n+1)/24 - sum(t^3-t)/48"
FIVE_COMPONENT_FIELDS = (
    "normalized_mfe",
    "ensemble_defect",
    "positional_entropy",
    "stem_fraction",
    "gc_fraction",
)
COMPONENT_ARTIFACT_ROLE = "aptarank_five_component_export"
COMPONENT_SCORER = "deployed AptaRank UI"
POPULATED_COMPONENT_STATUS = "populated_from_verified_artifact"
FIVE_COMPONENT_POLICY = (
    "production_table_unavailable_until_a_deployed_component_artifact_schema_is_observed_and_frozen"
)
COMPONENT_ACCEPTANCE_WHEN = "the deployed AptaRank UI exposes component values"
COMPONENT_ACCEPTANCE_STEPS = (
    "capture and hash the untouched artifact",
    "review and freeze its real schema",
    "enforce unique candidate ids and reconciliation against the analyzed export and private key",
    "compute a compact class-level descriptive table from the exported component values",
)
COMPONENT_DEFECT_ORDER = (
    "self_declared_schema",
    "duplicate_candidate_id",
    "unexpected_candidate_id",
    "incomplete_component_row",
    "schema_not_observed",
)
RECOMPUTE_REQUESTS = (
    "normalized_mfe",
    "ensemble_defect",
    "positional_entropy",
    "stem_fraction",
    "gc_fraction",
    "empirical_ref_calibration",
    "composite",
    "composite_aptamer_likeness",
    "aptamer_likeness",
    "dinucleotide_shuffle",
    "shuffle_p_value",
)
BOOTSTRAP_TARGETS = (
    "paired_median_difference",
    "auroc",
    "real_shuffle_pass_rate",
    "control_shuffle_pass_rate",
    "paired_shuffle_pass_difference",
)


def refuse_local_recomputation(request):
    """The UI owns scoring. Local code only summarizes exported fields."""
    raise Section6Error(
        "local_recompute_refused",
        "the deployed AptaRank UI remains the scorer; %s is not recomputed" % request,
    )


def render_fraction(value):
    """Render an exact fraction as a terminating decimal or a reduced ratio."""
    value = Fraction(value)
    if value < 0:
        return "-" + render_fraction(-value)
    if value.denominator == 1:
        return str(value.numerator)
    denominator = value.denominator
    twos = 0
    fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return "%d/%d" % (value.numerator, value.denominator)
    places = max(twos, fives)
    scaled = value.numerator * (10**places) // value.denominator
    digits = str(scaled).zfill(places + 1)
    return digits[:-places] + "." + digits[-places:]


def quantile_type7(values, probability):
    """Hyndman–Fan type 7 quantile. ``probability`` is an exact fraction."""
    if type(probability) is not Fraction or probability < 0 or probability > 1:
        raise Section6Error("quantile_invalid", "a type-7 probability is not an exact fraction in [0, 1]")
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        raise Section6Error("quantile_undefined", "a type-7 quantile has no values")
    if count == 1:
        return ordered[0]
    position = 1 + (count - 1) * probability
    lower = int(position)
    if position.denominator == 1:
        return ordered[lower - 1]
    fraction = position - lower
    return ordered[lower - 1] + fraction * (ordered[lower] - ordered[lower - 1])


def _score_fraction(token):
    arp1 = blinding.load_arp1()
    if arp1.classify_likeness(token) != "finite":
        raise Section6Error(
            "score_token_rejected",
            "an aptamer-likeness token is not a finite decimal. Reviewed rerun lineage is required.",
            rerun_lineage_required=True,
        )
    score = Fraction(Decimal(token))
    if score < 0 or score > 1:
        raise Section6Error(
            "aptamer_likeness_out_of_range",
            "an exported aptamer-likeness score is outside the closed interval [0, 1]. "
            "Reviewed rerun lineage is required.",
            rerun_lineage_required=True,
        )
    return score


def signed_rank_test(differences):
    """Two-sided Wilcoxon signed-rank test on real-minus-control differences.

    Zeros are discarded (``zero_method="wilcox"``). Tied absolute differences
    use average ranks. The normal approximation uses no continuity correction.
    The variance is ``n(n+1)(2n+1)/24 - sum(t^3-t)/48``. That quantity equals
    the sum of the squared average ranks divided by 4. The reported statistic
    is the sum of the ranks of the strictly positive differences.
    When every difference is zero the statistic is 0, the p-value is 1, and
    the disposition is ``all_zero_differences``.
    """
    if not differences:
        raise Section6Error("wilcoxon_undefined", "the signed-rank test has no differences")
    zero_count = sum(1 for value in differences if value == 0)
    nonzero = [value for value in differences if value != 0]
    base = {
        "zero_method": "wilcox",
        "tie_method": "average_ranks",
        "approximation": "normal",
        "continuity_correction": False,
        "alternative": "two-sided",
        "variance_formula": VARIANCE_FORMULA,
        "variance": None,
        "zero_count": zero_count,
        "nonzero_count": len(nonzero),
    }
    if not nonzero:
        base.update(
            {
                "statistic": "0",
                "p_value": 1.0,
                "disposition": "all_zero_differences",
            }
        )
        return base
    order = sorted(range(len(nonzero)), key=lambda index: abs(nonzero[index]))
    ranks = [None] * len(nonzero)
    tie_term = 0
    cursor = 0
    while cursor < len(nonzero):
        end = cursor
        while end + 1 < len(nonzero) and abs(nonzero[order[end + 1]]) == abs(nonzero[order[cursor]]):
            end += 1
        average = Fraction((cursor + 1) + (end + 1), 2)
        for position in range(cursor, end + 1):
            ranks[order[position]] = average
        group = end - cursor + 1
        tie_term += group**3 - group
        cursor = end + 1
    statistic = sum(
        (ranks[index] for index in range(len(nonzero)) if nonzero[index] > 0),
        Fraction(0),
    )
    count = len(nonzero)
    mean = Fraction(count * (count + 1), 4)
    variance = Fraction(count * (count + 1) * (2 * count + 1), 24) - Fraction(tie_term, 48)
    if variance <= 0:
        raise Section6Error("wilcoxon_undefined", "the signed-rank variance is not positive")
    z_score = (float(statistic) - float(mean)) / math.sqrt(float(variance))
    p_value = math.erfc(abs(z_score) / math.sqrt(2.0))
    base.update(
        {
            "statistic": render_fraction(statistic),
            "variance": render_fraction(variance),
            "p_value": p_value,
            "disposition": "wilcoxon_signed_rank",
        }
    )
    return base


def auroc(real_scores, control_scores):
    """Mann–Whitney AUROC. Ties between a real score and a control score earn 1/2.

    The positive class is the real membership. A value below 1/2 is preserved.
    """
    if not real_scores or not control_scores:
        return None
    controls = sorted(control_scores)
    credit = Fraction(0)
    for score in real_scores:
        left = 0
        right = len(controls)
        while left < right:
            mid = (left + right) // 2
            if controls[mid] <= score:
                left = mid + 1
            else:
                right = mid
        upper = left
        left = 0
        right = len(controls)
        while left < right:
            mid = (left + right) // 2
            if controls[mid] < score:
                left = mid + 1
            else:
                right = mid
        credit += left + Fraction(upper - left, 2)
    return credit / (len(real_scores) * len(controls))


def _population(cluster_ids):
    unique = sorted(set(cluster_ids))
    if not unique:
        raise Section6Error("clusters_missing", "bootstrap resampling has no cluster ids")
    return tuple(unique)


def bootstrap_index(replicate, draw, modulus):
    """Unbiased cluster index from the domain-separated SHA-256 stream."""
    if type(replicate) is not int or type(draw) is not int or type(modulus) is not int:
        raise Section6Error("bootstrap_index_invalid", "a bootstrap index is not an integer")
    if replicate < 0 or draw < 0 or modulus < 1:
        raise Section6Error("bootstrap_index_invalid", "a bootstrap index is out of range")
    if modulus == 1:
        return 0
    span = 1 << 256
    limit = (span // modulus) * modulus
    block = 0
    while True:
        payload = uniform.length_delimited_bytes(
            [
                BOOTSTRAP_DOMAIN,
                uniform.canonical_decimal(BOOTSTRAP_SEED),
                uniform.canonical_decimal(replicate),
                uniform.canonical_decimal(draw),
                uniform.canonical_decimal(block),
            ]
        )
        value = int.from_bytes(hashlib.sha256(payload).digest(), "big")
        if value < limit:
            return value % modulus
        block += 1


def resampled_cluster_ids(cluster_ids, replicate):
    """Draw the observed number of unique clusters with replacement."""
    population = _population(cluster_ids)
    modulus = len(population)
    return tuple(population[bootstrap_index(replicate, draw, modulus)] for draw in range(modulus))


def expand_cluster_members(members_by_cluster, drawn_ids):
    """Include every member of a drawn cluster once per draw."""
    expanded = []
    for cluster_id in drawn_ids:
        expanded.extend(members_by_cluster.get(cluster_id, ()))
    return expanded


def _defined_pair_sample(expanded):
    if len(expanded) < 2:
        return False
    return len({pair["cluster_id"] for pair in expanded}) >= 2


def _rate(flags):
    if not flags:
        return None
    return Fraction(sum(flags), len(flags))


def _paired_pass_difference(pairs):
    if not pairs:
        return None
    return Fraction(sum(pair["real_pass"] - pair["control_pass"] for pair in pairs), len(pairs))


def _interval(values):
    if len(values) < MINIMUM_DEFINED_REPLICATES:
        return None
    ordered = values
    return {
        "low": render_fraction(quantile_type7(ordered, Fraction(1, 40))),
        "high": render_fraction(quantile_type7(ordered, Fraction(39, 40))),
        "level": "0.95",
        "quantile": "hyndman_fan_type_7",
        "probabilities": ["0.025", "0.975"],
    }


def _empty_bootstrap(reason):
    return {
        name: {
            "point": None,
            "interval": None,
            "technical_incompleteness": reason,
            "replicates": None,
            "defined_replicates": None,
            "undefined_replicates": None,
            "imputed_replicates": 0,
        }
        for name in BOOTSTRAP_TARGETS
    }


def _bootstrap(cluster_ids, complete_pairs, real_flags, control_flags):
    if not _defined_pair_sample(complete_pairs):
        return _empty_bootstrap(INCOMPLETENESS_PAIRS)
    pairs_by_cluster = {}
    real_by_cluster = {}
    control_by_cluster = {}
    for pair in complete_pairs:
        pairs_by_cluster.setdefault(pair["cluster_id"], []).append(pair)
    for cluster_id, flags in real_flags.items():
        real_by_cluster[cluster_id] = list(flags)
    for cluster_id, flags in control_flags.items():
        control_by_cluster[cluster_id] = list(flags)
    collected = {name: [] for name in BOOTSTRAP_TARGETS}
    undefined = {name: 0 for name in BOOTSTRAP_TARGETS}
    population = _population(cluster_ids)
    for replicate in range(BOOTSTRAP_REPLICATES):
        drawn = resampled_cluster_ids(population, replicate)
        expanded = expand_cluster_members(pairs_by_cluster, drawn)
        if not _defined_pair_sample(expanded):
            for name in BOOTSTRAP_TARGETS:
                undefined[name] += 1
            continue
        differences = [pair["difference"] for pair in expanded]
        collected["paired_median_difference"].append(quantile_type7(differences, Fraction(1, 2)))
        collected["auroc"].append(
            auroc([pair["real_score"] for pair in expanded], [pair["control_score"] for pair in expanded])
        )
        real_sample = expand_cluster_members(real_by_cluster, drawn)
        control_sample = expand_cluster_members(control_by_cluster, drawn)
        real_rate = _rate(real_sample)
        control_rate = _rate(control_sample)
        paired_rate = _paired_pass_difference(expanded)
        for name, value in (
            ("real_shuffle_pass_rate", real_rate),
            ("control_shuffle_pass_rate", control_rate),
            ("paired_shuffle_pass_difference", paired_rate),
        ):
            if value is None:
                undefined[name] += 1
            else:
                collected[name].append(value)
    results = {}
    for name in BOOTSTRAP_TARGETS:
        defined = collected[name]
        missing = undefined[name]
        if len(defined) + missing != BOOTSTRAP_REPLICATES:
            raise Section6Error("bootstrap_accounting_invalid", "a bootstrap replicate was dropped")
        interval = _interval(defined)
        reason = None if interval is not None else INCOMPLETENESS_REPLICATES
        results[name] = {
            "interval": interval,
            "technical_incompleteness": reason,
            "replicates": BOOTSTRAP_REPLICATES,
            "defined_replicates": len(defined),
            "undefined_replicates": missing,
            "imputed_replicates": 0,
        }
    return results


def _class_summary(scores):
    if not scores:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "q1": None,
            "q3": None,
            "iqr": None,
            "undefined": True,
        }
    q1 = quantile_type7(scores, Fraction(1, 4))
    q3 = quantile_type7(scores, Fraction(3, 4))
    return {
        "count": len(scores),
        "mean": render_fraction(sum(scores, Fraction(0)) / len(scores)),
        "median": render_fraction(quantile_type7(scores, Fraction(1, 2))),
        "q1": render_fraction(q1),
        "q3": render_fraction(q3),
        "iqr": render_fraction(q3 - q1),
        "undefined": False,
    }


def _raise_validator(errors):
    first = errors.items[0]
    raise Section6Error(
        first["code"],
        first["detail"] + " Reviewed rerun lineage is required.",
        rerun_lineage_required=True,
    )


def _parse_upload(payload):
    arp1 = blinding.load_arp1()
    errors = arp1.ErrorList()
    rows = arp1.parse_csv_rows(payload, arp1.CANDIDATE_COLUMNS, errors, "candidate upload")
    if rows is not None:
        arp1._check_candidate_rows(rows, errors)
    if errors.items:
        _raise_validator(errors)
    return rows


def _parse_export(payload):
    arp1 = blinding.load_arp1()
    errors = arp1.ErrorList()
    rows = arp1.parse_csv_rows(payload, arp1.SHORTLIST_COLUMNS, errors, "shortlist")
    profile = {
        "compatibility_allowed_tokens": arp1.COMPATIBILITY_TOKENS,
        "shuffle_allowed_tokens": arp1.SHUFFLE_TOKENS,
    }
    if rows is not None:
        arp1._check_shortlist_rows(rows, errors, profile)
    if errors.items:
        _raise_validator(errors)
    for row in rows:
        if row["compatibility"] != "not evaluated":
            raise Section6Error(
                "compatibility_token_rejected",
                "a target-free export compatibility token is not 'not evaluated'. "
                "Reviewed rerun lineage is required.",
                rerun_lineage_required=True,
            )
        if row["shuffle"] not in ("pass", "fail"):
            raise Section6Error(
                "shuffle_token_rejected",
                "a target-free export shuffle token is not pass or fail. Reviewed rerun lineage is required.",
                rerun_lineage_required=True,
            )
    return rows


def _identifier(value):
    return type(value) is str and bool(value) and not any(character.isspace() for character in value)


def validate_private_key(private_key):
    """Fail closed unless the restricted key matches the Section 6 pair rule.

    The document must carry the package, schema, and restricted markers. Each
    candidate id is ``cand_`` plus 32 lowercase hex characters, and each source
    digest is lowercase SHA-256. Candidate ids and source digests are unique.
    Each pair contains exactly one ``eval_core`` and one ``paired_uniform_shuffle``
    sharing ``parent_core_id``, ``cluster_id``, and ``length``.
    """
    if type(private_key) is bytes:
        try:
            document = json.loads(private_key.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Section6Error("private_key_invalid", "the private key is not a JSON object") from exc
    elif type(private_key) is dict:
        document = private_key
    else:
        raise Section6Error("private_key_invalid", "the private key must be bytes or an object")
    if type(document) is not dict or set(document) != set(blinding.PRIVATE_KEY_MARKERS):
        raise Section6Error("private_key_invalid", "the private key markers are missing or unexpected")
    if document["package_id"] != blinding.PACKAGE_ID or type(document["package_id"]) is not str:
        raise Section6Error("private_key_invalid", "the private key package marker is not Section 6")
    if document["schema_version"] != blinding.SCHEMA_VERSION or type(document["schema_version"]) is not str:
        raise Section6Error("private_key_invalid", "the private key schema marker is not Section 6")
    if document["restricted"] is not True:
        raise Section6Error("private_key_invalid", "the private key is not marked restricted")
    rows = document["candidates"]
    if type(rows) is not list or not rows:
        raise Section6Error("private_key_invalid", "the private key has no candidates")
    seen_ids = set()
    seen_digests = set()
    grouped = {}
    for row in rows:
        if type(row) is not dict or tuple(row) != blinding.PRIVATE_KEY_FIELDS:
            raise Section6Error("private_key_invalid", "a private-key row does not match the restricted fields")
        if row["class_label"] not in blinding.CLASS_LABELS:
            raise Section6Error(
                "private_key_invalid",
                "a private-key class label is not eval_core or paired_uniform_shuffle",
            )
        if blinding.CANDIDATE_ID_RE.fullmatch(row["candidate_id"]) is None:
            raise Section6Error(
                "private_key_invalid",
                "a private-key candidate id is not cand_ plus 32 lowercase hex characters",
            )
        if not uniform.is_sha256_text(row["source_digest"]):
            raise Section6Error("private_key_invalid", "a private-key source digest is not a lowercase SHA-256 digest")
        if type(row["length"]) is not int or row["length"] < 1:
            raise Section6Error("private_key_invalid", "a private-key length is not a positive integer")
        for field in ("pair_id", "parent_core_id", "cluster_id"):
            if not _identifier(row[field]):
                raise Section6Error("private_key_invalid", "a private-key identifier is empty")
        if row["candidate_id"] in seen_ids:
            raise Section6Error("duplicate_candidate_id", "a private-key candidate id is duplicated")
        if row["source_digest"] in seen_digests:
            raise Section6Error("duplicate_source_digest", "a private-key source digest is duplicated")
        seen_ids.add(row["candidate_id"])
        seen_digests.add(row["source_digest"])
        grouped.setdefault(row["pair_id"], []).append(row)
    for members in grouped.values():
        labels = sorted(member["class_label"] for member in members)
        if labels != sorted(blinding.CLASS_LABELS):
            raise Section6Error(
                "pair_conflict",
                "a pair does not contain exactly one eval_core and one paired_uniform_shuffle",
            )
        if len({member["parent_core_id"] for member in members}) != 1:
            raise Section6Error("pair_conflict", "a pair does not share parent_core_id")
        if len({member["cluster_id"] for member in members}) != 1:
            raise Section6Error("pair_conflict", "a pair does not share cluster_id")
        if len({member["length"] for member in members}) != 1:
            raise Section6Error("pair_conflict", "a pair does not share length")
    return rows


def _validate_export_ranks(export_rows, scores_by_id, *, complete):
    """Check rank values. Physical CSV order is not the ordering key.

    A complete export must use ranks 1 through N. When technical failures
    leave gaps, increasing rank must still follow non-increasing score and,
    for an equal score, ascending candidate id.
    """
    ranked = []
    for row in export_rows:
        rank = int(row["rank"])
        candidate_id = row["candidate"]
        ranked.append((rank, scores_by_id[candidate_id], candidate_id))
    if complete:
        observed = sorted(item[0] for item in ranked)
        if observed != list(range(1, len(ranked) + 1)):
            raise Section6Error(
                "rank_sequence_invalid",
                "a complete export does not use ranks 1 through N. Reviewed rerun lineage is required.",
                rerun_lineage_required=True,
            )
    ordered = sorted(ranked, key=lambda item: item[0])
    for previous, current in zip(ordered, ordered[1:]):
        _previous_rank, previous_score, previous_id = previous
        _rank, score, candidate_id = current
        if score > previous_score or (score == previous_score and candidate_id <= previous_id):
            raise Section6Error(
                "rank_order_invalid",
                "increasing rank does not follow non-increasing aptamer-likeness and ascending candidate id. "
                "Reviewed rerun lineage is required.",
                rerun_lineage_required=True,
            )


def _artifact_role(value):
    return type(value) is str and bool(value) and not any(character.isspace() for character in value)


def capture_raw_artifacts(artifacts):
    """Hash every available raw run artifact and record the unavailable ones.

    ``artifacts`` lists every role the caller knows about. An available role
    carries its bytes and is hashed. An unavailable role is recorded and is
    not replaced. Paths are refused.
    """
    if isinstance(artifacts, (str, bytes, bytearray)) or callable(getattr(artifacts, "__fspath__", None)):
        raise Section6Error("filesystem_path_refused", "a filesystem path argument is refused")
    if type(artifacts) is not list:
        raise Section6Error(
            "raw_artifacts_invalid",
            "raw run artifacts must list every available and unavailable artifact",
        )
    captured = []
    unavailable = []
    available_payloads = []
    seen = set()
    for index, item in enumerate(artifacts, start=1):
        if type(item) is not dict or set(item) - {"role", "available", "payload"} or "role" not in item or "available" not in item:
            raise Section6Error("raw_artifacts_invalid", "raw run artifact %d is not an availability record" % index)
        role = item["role"]
        available = item["available"]
        if not _artifact_role(role):
            raise Section6Error("raw_artifacts_invalid", "a raw run artifact role is empty")
        if type(available) is not bool:
            raise Section6Error("raw_artifacts_invalid", "raw run artifact availability must be boolean")
        if role in seen:
            raise Section6Error("raw_artifacts_invalid", "a raw run artifact role is duplicated")
        seen.add(role)
        payload = item.get("payload")
        if available:
            if type(payload) is not bytes:
                raise Section6Error("raw_artifacts_invalid", "an available raw run artifact has no bytes")
            digest = hashlib.sha256(payload).hexdigest()
            captured.append({"role": role, "sha256": digest, "byte_count": len(payload)})
            available_payloads.append((role, digest, payload))
        elif "payload" in item and payload is not None:
            raise Section6Error("raw_artifacts_invalid", "an unavailable raw run artifact must not carry bytes")
        else:
            unavailable.append({"role": role, "reason": "unavailable"})
    captured.sort(key=lambda row: row["role"])
    unavailable.sort(key=lambda row: row["role"])
    public = {
        "captured": captured,
        "unavailable": unavailable,
        "captured_count": len(captured),
        "unavailable_count": len(unavailable),
    }
    return public, available_payloads


def exact_byte_record(payload):
    """SHA-256 and byte count of one exact byte string."""
    if type(payload) is not bytes:
        raise Section6Error("input_type_invalid", "an analyzed byte record requires bytes")
    return {"sha256": hashlib.sha256(payload).hexdigest(), "byte_count": len(payload)}


def component_acceptance_gate():
    """Future gate. It does not freeze a schema that has not been observed."""
    return {
        "status": "future",
        "schema_observed": False,
        "schema_frozen": False,
        "when": COMPONENT_ACCEPTANCE_WHEN,
        "steps": list(COMPONENT_ACCEPTANCE_STEPS),
        "summarizing_exported_values": "allowed",
        "recomputing_component_values": "refused",
    }


def _component_row_defects(rows, analyzed_candidate_ids):
    defects = set()
    if type(rows) is not list or not rows:
        defects.add("incomplete_component_row")
        return defects
    seen = set()
    for row in rows:
        if type(row) is not dict:
            defects.add("incomplete_component_row")
            continue
        candidate_id = row.get("candidate_id")
        if type(candidate_id) is not str or blinding.CANDIDATE_ID_RE.fullmatch(candidate_id) is None:
            defects.add("incomplete_component_row")
        else:
            if candidate_id in seen:
                defects.add("duplicate_candidate_id")
            seen.add(candidate_id)
            if analyzed_candidate_ids is not None and candidate_id not in analyzed_candidate_ids:
                defects.add("unexpected_candidate_id")
        for field in FIVE_COMPONENT_FIELDS:
            value = row.get(field)
            if field not in row or type(value) is not str or not value.strip():
                defects.add("incomplete_component_row")
                break
    return defects


def _component_claim_defects(payload, analyzed_candidate_ids):
    """Classify a synthetic component-like document. Matching labels do not verify it."""
    if type(payload) is not bytes:
        return None
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if type(document) is not dict:
        return None
    declared = (
        document.get("scorer") == COMPONENT_SCORER and document.get("artifact_role") == COMPONENT_ARTIFACT_ROLE
    )
    marked = document.get("scorer") == COMPONENT_SCORER or document.get("artifact_role") == COMPONENT_ARTIFACT_ROLE
    rows = document.get("rows")
    has_component_field = False
    if type(rows) is list:
        for row in rows:
            if type(row) is dict and any(field in row for field in FIVE_COMPONENT_FIELDS):
                has_component_field = True
                break
    if not marked and not has_component_field:
        return None
    defects = set()
    if declared:
        defects.add("self_declared_schema")
    defects.update(_component_row_defects(rows, analyzed_candidate_ids))
    defects.add("schema_not_observed")
    return [name for name in COMPONENT_DEFECT_ORDER if name in defects]


def five_component_table(available_payloads, *, analyzed_candidate_ids=None):
    """Leave the production five-component table unavailable.

    No deployed component-artifact schema has been observed or frozen, so a
    JSON document is not verified by declaring the expected scorer and role
    strings. Duplicate, unexpected, incomplete, and merely self-declared rows
    stay unverified. This does not copy component values and does not
    recompute them.
    """
    if analyzed_candidate_ids is not None and type(analyzed_candidate_ids) not in (set, frozenset):
        raise Section6Error("component_ids_invalid", "analyzed candidate ids must be a set")
    inspected = []
    for role, digest, payload in available_payloads:
        defects = _component_claim_defects(payload, analyzed_candidate_ids)
        if defects is None:
            continue
        inspected.append(
            {
                "role": role,
                "sha256": digest,
                "verification": "unverified",
                "defects": defects,
            }
        )
    table = {
        "policy": FIVE_COMPONENT_POLICY,
        "acceptance_gate": component_acceptance_gate(),
        "schema_observed": False,
        "schema_frozen": False,
        "recomputed": False,
        "local_recomputation": "not_attempted",
        "status": "unavailable",
        "source_role": None,
        "source_sha256": None,
        "rows": None,
    }
    if inspected:
        table.update(
            {
                "verification": "unverified",
                "reason": "unverified_component_artifact",
                "inspected": inspected,
            }
        )
    else:
        table.update(
            {
                "verification": "not_presented",
                "reason": "component_artifact_unavailable",
                "inspected": [],
            }
        )
    if table["status"] == POPULATED_COMPONENT_STATUS or table["rows"] is not None:
        raise Section6Error(
            "component_schema_not_frozen",
            "the production five-component table is unavailable until a deployed schema is observed and frozen",
        )
    return table


def _failure_map(failures, expected_ids):
    if failures is None:
        return {}
    if type(failures) is not list:
        raise Section6Error("failure_record_invalid", "technical failures must be a list")
    mapped = {}
    for item in failures:
        if type(item) is not dict or set(item) != {"candidate_id", "reason"}:
            raise Section6Error("failure_record_invalid", "a technical failure record is malformed")
        candidate_id = item["candidate_id"]
        reason = item["reason"]
        if type(candidate_id) is not str or candidate_id not in expected_ids:
            raise Section6Error("failure_record_invalid", "a technical failure id is not an expected candidate")
        if type(reason) is not str or not reason.strip():
            raise Section6Error("failure_record_invalid", "a technical failure needs a nonempty reason")
        if candidate_id in mapped:
            raise Section6Error("failure_record_invalid", "a technical failure id is duplicated")
        mapped[candidate_id] = reason
    return mapped


def summarize_section6(upload, private_key, export, *, failures=None, run_sheet=None, raw_artifacts):
    """Join by candidate id and summarize exported scores. Row order is not a key.

    The exact candidate-upload bytes and exact downloaded-export bytes are
    hashed on every summary, including when ``raw_artifacts`` is empty.
    ``raw_artifacts`` lists optional run artifacts only. Available optional
    payloads are hashed, and unavailable roles are recorded.
    """
    for value in (upload, private_key, export, failures, run_sheet, raw_artifacts):
        if callable(getattr(value, "__fspath__", None)):
            raise Section6Error("filesystem_path_refused", "a filesystem path argument is refused")
    if type(upload) is not bytes or type(export) is not bytes:
        raise Section6Error("input_type_invalid", "upload and export inputs must be bytes")
    analyzed_bytes = {
        "candidate_upload": exact_byte_record(upload),
        "downloaded_export": exact_byte_record(export),
    }
    artifact_record, artifact_payloads = capture_raw_artifacts(raw_artifacts)
    blinding.load_pinned_contract()
    if run_sheet is not None:
        blinding.check_run_sheet(run_sheet)
    upload_rows = _parse_upload(upload)
    export_rows = _parse_export(export)
    private_rows = validate_private_key(private_key)
    expected = {}
    for row in private_rows:
        if row["candidate_id"] in expected:
            raise Section6Error("duplicate_candidate_id", "a private-key candidate id is duplicated")
        expected[row["candidate_id"]] = row
    upload_by_id = {}
    for row in upload_rows:
        if row["id"] in upload_by_id:
            raise Section6Error("duplicate_candidate_id", "an upload candidate id is duplicated")
        upload_by_id[row["id"]] = row
    if set(upload_by_id) != set(expected):
        raise Section6Error("join_mismatch", "the upload ids and the private-key ids differ")
    failure_map = _failure_map(failures, set(expected))
    export_by_id = {}
    for row in export_rows:
        candidate_id = row["candidate"]
        if candidate_id in export_by_id:
            raise Section6Error("duplicate_candidate_id", "an export candidate id is duplicated")
        export_by_id[candidate_id] = row
    if set(export_by_id) & set(failure_map):
        raise Section6Error("disposition_conflict", "a candidate is both exported and a technical failure")
    missing = set(expected) - set(export_by_id) - set(failure_map)
    extra = set(export_by_id) - set(expected)
    if missing or extra:
        raise Section6Error("unaccounted_candidate", "an expected candidate has no export row and no technical failure")
    component_table = five_component_table(
        artifact_payloads,
        analyzed_candidate_ids=set(export_by_id),
    )
    joined = {}
    for candidate_id, private_row in expected.items():
        uploaded = upload_by_id[candidate_id]
        if uniform.core_digest(uploaded["sequence"]) != private_row["source_digest"]:
            raise Section6Error("sequence_digest_mismatch", "an upload sequence does not match its private-key digest")
        if len(uploaded["sequence"]) != private_row["length"]:
            raise Section6Error("length_mismatch", "an upload length does not match the private key")
        if candidate_id in failure_map:
            joined[candidate_id] = {
                "score": None,
                "passed": None,
                "failure": True,
                "private": private_row,
            }
            continue
        exported = export_by_id[candidate_id]
        if exported["sequence"] != uploaded["sequence"]:
            raise Section6Error("sequence_round_trip_failed", "an export sequence does not match the upload sequence")
        if int(exported["len"]) != private_row["length"] or len(exported["sequence"]) != private_row["length"]:
            raise Section6Error("length_mismatch", "an export length does not match the private key")
        joined[candidate_id] = {
            "score": _score_fraction(exported["aptamer-likeness"]),
            "passed": 1 if exported["shuffle"] == "pass" else 0,
            "failure": False,
            "private": private_row,
        }
    _validate_export_ranks(
        export_rows,
        {candidate_id: item["score"] for candidate_id, item in joined.items() if item["score"] is not None},
        complete=not failure_map,
    )
    pairs = {}
    for item in joined.values():
        private_row = item["private"]
        slot = pairs.setdefault(
            private_row["pair_id"],
            {"pair_id": private_row["pair_id"], "cluster_id": private_row["cluster_id"], "members": {}},
        )
        if slot["cluster_id"] != private_row["cluster_id"]:
            raise Section6Error("pair_conflict", "a pair does not share one cluster")
        if private_row["class_label"] in slot["members"]:
            raise Section6Error("pair_conflict", "a pair has two members of one class")
        slot["members"][private_row["class_label"]] = item
    complete = []
    incomplete = 0
    for slot in pairs.values():
        members = slot["members"]
        if set(members) != set(blinding.CLASS_LABELS):
            raise Section6Error(
                "pair_conflict",
                "a pair does not contain exactly one eval_core and one paired_uniform_shuffle",
            )
        real = members[blinding.CLASS_EVAL_CORE]
        control = members[blinding.CLASS_PAIRED_UNIFORM]
        if real["score"] is None or control["score"] is None:
            incomplete += 1
            continue
        complete.append(
            {
                "cluster_id": slot["cluster_id"],
                "real_score": real["score"],
                "control_score": control["score"],
                "difference": real["score"] - control["score"],
                "real_pass": real["passed"],
                "control_pass": control["passed"],
            }
        )
    scores = {blinding.CLASS_EVAL_CORE: [], blinding.CLASS_PAIRED_UNIFORM: []}
    shuffle_flags = {blinding.CLASS_EVAL_CORE: [], blinding.CLASS_PAIRED_UNIFORM: []}
    shuffle_by_cluster = {blinding.CLASS_EVAL_CORE: {}, blinding.CLASS_PAIRED_UNIFORM: {}}
    failure_count = 0
    for item in joined.values():
        label = item["private"]["class_label"]
        cluster_id = item["private"]["cluster_id"]
        if item["failure"]:
            failure_count += 1
            continue
        scores[label].append(item["score"])
        if item["passed"] is not None:
            shuffle_flags[label].append(item["passed"])
            shuffle_by_cluster[label].setdefault(cluster_id, []).append(item["passed"])
    paired_ready = _defined_pair_sample(complete)
    if paired_ready:
        differences = [pair["difference"] for pair in complete]
        paired = {
            "count": len(complete),
            "direction": "eval_core_minus_paired_uniform_shuffle",
            "median_difference": render_fraction(quantile_type7(differences, Fraction(1, 2))),
            "mean_difference": render_fraction(sum(differences, Fraction(0)) / len(differences)),
            "technical_incompleteness": None,
        }
        auroc_value = auroc([pair["real_score"] for pair in complete], [pair["control_score"] for pair in complete])
        secondary = signed_rank_test(differences)
        secondary["technical_incompleteness"] = None
    else:
        paired = {
            "count": len(complete),
            "direction": "eval_core_minus_paired_uniform_shuffle",
            "median_difference": None,
            "mean_difference": None,
            "technical_incompleteness": INCOMPLETENESS_PAIRS,
        }
        auroc_value = None
        secondary = {
            "statistic": None,
            "p_value": None,
            "zero_count": None,
            "nonzero_count": None,
            "disposition": None,
            "technical_incompleteness": INCOMPLETENESS_PAIRS,
        }
    real_rate = _rate(shuffle_flags[blinding.CLASS_EVAL_CORE])
    control_rate = _rate(shuffle_flags[blinding.CLASS_PAIRED_UNIFORM])
    paired_shuffle = _paired_pass_difference(complete) if complete else None
    bootstrap = _bootstrap(
        [row["cluster_id"] for row in private_rows],
        complete,
        shuffle_by_cluster[blinding.CLASS_EVAL_CORE],
        shuffle_by_cluster[blinding.CLASS_PAIRED_UNIFORM],
    )
    if paired_ready:
        bootstrap["paired_median_difference"]["point"] = paired["median_difference"]
        bootstrap["auroc"]["point"] = render_fraction(auroc_value)
        bootstrap["real_shuffle_pass_rate"]["point"] = None if real_rate is None else render_fraction(real_rate)
        bootstrap["control_shuffle_pass_rate"]["point"] = (
            None if control_rate is None else render_fraction(control_rate)
        )
        bootstrap["paired_shuffle_pass_difference"]["point"] = (
            None if paired_shuffle is None else render_fraction(paired_shuffle)
        )
    defined_counts = {
        name: value["defined_replicates"] for name, value in bootstrap.items()
    }
    undefined_counts = {
        name: value["undefined_replicates"] for name, value in bootstrap.items()
    }
    return {
        "package_id": blinding.PACKAGE_ID,
        "schema_version": blinding.SCHEMA_VERSION,
        "synthetic": True,
        "scientific_result": False,
        "scores_recomputed": False,
        "scorer_owner": "deployed AptaRank UI",
        "favourable_direction": "higher_aptamer_likeness",
        "denominators": {
            "input_candidates": len(private_rows),
            "evaluable_scores": sum(len(items) for items in scores.values()),
            "evaluable_scores_by_class": {label: len(items) for label, items in scores.items()},
            "technical_failures": failure_count,
            "complete_score_pairs": len(complete),
            "incomplete_score_pairs": incomplete,
            "pre_rejection_clusters": len({row["cluster_id"] for row in private_rows}),
            "clusters_with_complete_score_pairs": len({pair["cluster_id"] for pair in complete}),
            "shuffle_valid_by_class": {label: len(items) for label, items in shuffle_flags.items()},
            "shuffle_pass_by_class": {label: sum(items) for label, items in shuffle_flags.items()},
            "paired_shuffle_pairs": len(complete),
            "bootstrap_replicates": None if not paired_ready else BOOTSTRAP_REPLICATES,
            "bootstrap_defined_replicates": defined_counts,
            "bootstrap_undefined_replicates": undefined_counts,
            "imputed_replicates": 0,
        },
        "class_summaries": {label: _class_summary(items) for label, items in scores.items()},
        "paired": paired,
        "auroc": {
            "value": None if auroc_value is None else render_fraction(auroc_value),
            "positive_class": blinding.CLASS_EVAL_CORE,
            "tie_credit": "0.5",
            "complete_pairs": len(complete),
            "technical_incompleteness": None if paired_ready else INCOMPLETENESS_PAIRS,
        },
        "shuffle": {
            "real_pass_rate": None if real_rate is None else render_fraction(real_rate),
            "control_pass_rate": None if control_rate is None else render_fraction(control_rate),
            "paired_pass_difference": None if paired_shuffle is None else render_fraction(paired_shuffle),
            "paired_direction": "eval_core_minus_paired_uniform_shuffle",
        },
        "secondary_test": secondary,
        "bootstrap": bootstrap,
        "analyzed_bytes": analyzed_bytes,
        "raw_run_artifacts": artifact_record,
        "five_component_table": component_table,
    }
