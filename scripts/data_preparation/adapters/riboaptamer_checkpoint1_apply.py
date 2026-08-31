"""RiboAptamer CHECKPOINT-1 real application helpers.

Uses the same simulation/transform as the dry-run. Does not start S4.
"""

from __future__ import annotations

RIBOAPTAMER_CHECKPOINT_CLOSED_STATEMENT = (
    "CHECKPOINT-1 CLOSED: human review has been applied and validated.\n"
    "Only records with authorised_for_s4=true may proceed to a future "
    "global S4 handoff.\n"
    "authorised_for_s4 means RNA technical eligibility after RiboAptamer "
    "CHECKPOINT-1. It does not mean target canonicalisation, UniProt "
    "resolution, evidence mapping, leakage filtering, merge, deduplication, "
    "clustering, balancing, partitioning, or S4 execution."
)
