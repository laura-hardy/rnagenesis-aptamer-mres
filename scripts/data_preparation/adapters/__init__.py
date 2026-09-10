"""Source adapters for S1 verbatim extraction.

Adapters map a registered raw/cleaned source table into the canonical corpus
schema plus a complete source-metadata sidecar. They must not perform S2
normalisation, filtering, parking, or deduplication.
"""

from __future__ import annotations

from typing import Final

# Recognised S1 adapter keys. Dispatch lives in s1_extract.py.
ADAPTER_KEYS: Final[frozenset[str]] = frozenset(
    {
        "aptabase",
        "utexas",
        "aptadb",
        "riboaptamer",
        "aptaindex",
        "ena",
        "aptamerbase",
        "aptadiff_a",
        "aptadiff_b",
    }
)
