"""Load and validate Stage 1 hard-filter JSON configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Stage1Config:
    """Stage 1 hard-filter settings."""

    strip_leading_11: bool = True
    enforce_rna_alphabet: bool = True
    min_length: int | None = None
    max_length: int | None = None
    enforce_exact_deduplication: bool = True
    homopolymer_max_run_fail_threshold: int = 5
    enforce_homopolymer_filter: bool = True
    min_gc_fraction: float | None = None
    max_gc_fraction: float | None = None
    max_normalised_mfe: float | None = None
    near_dedup_max_edit_distance: int | None = None
    write_passed_fasta: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Stage1Config:
        """Build config from a parsed JSON object."""
        field_names = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        unknown = set(data) - field_names
        if unknown:
            raise ValueError(f"Unknown config keys: {sorted(unknown)}")
        kwargs = {name: data[name] for name in field_names if name in data}
        return cls(**kwargs)

    def length_filter_enabled(self) -> bool:
        return self.min_length is not None or self.max_length is not None

    def gc_filter_enabled(self) -> bool:
        return self.min_gc_fraction is not None or self.max_gc_fraction is not None

    def mfe_filter_enabled(self) -> bool:
        return self.max_normalised_mfe is not None


def load_stage1_config(path: Path) -> Stage1Config:
    """Load Stage 1 config from a JSON file."""
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a JSON object: {path}")
    return Stage1Config.from_dict(data)
