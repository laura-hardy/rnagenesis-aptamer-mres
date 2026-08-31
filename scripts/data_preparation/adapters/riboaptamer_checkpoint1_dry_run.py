"""RiboAptamer CHECKPOINT-1 application dry-run (preview only).

Uses the same ``apply_riboaptamer_checkpoint1_package`` transformation as a
future real apply. Writes nothing that the pipeline treats as a closed
checkpoint or S4 handoff.
"""

from __future__ import annotations

DRY_RUN_BANNER = (
    "DRY-RUN PREVIEW. NOT AUTHORITATIVE. CHECKPOINT-1 IS NOT APPLIED. "
    "S4 REMAINS BLOCKED."
)
