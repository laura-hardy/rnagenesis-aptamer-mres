#!/usr/bin/env python3
"""Export a poster-ready ViennaRNA secondary-structure figure for one example sequence.

Selects one representative folded RNA sequence from the unadapted RNAGenesis Stage 1
poster-config run. The figure is illustrative only: it shows what one generated RNA
candidate looks like after folding, not a validated aptamer or binding candidate.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Selection parameters (deterministic, documented in metadata).
GC_TARGET = 0.6165  # Aptadiff A reference mean GC fraction
MIN_PAIRED_BASES = 4
MFE_PERCENTILE_LOW = 0.10
MFE_PERCENTILE_HIGH = 0.25
VALID_RNA_BASES = frozenset("AUCG")

SELECTION_RULE = (
    "Example folded unadapted RNAGenesis sequence selected from the Stage 1 poster-config "
    "run using a deterministic rule: (1) load stage1_all_sequences.csv; "
    "(2) when a condition column is present, keep only rows with an explicit label containing "
    "'unadapted' and 'rnagenesis' (exclude rows with missing condition values); "
    "(3) prefer stage1_pass == True; (4) require valid A/C/G/U alphabet and non-empty sequence; "
    "(5) require non-trivial dot-bracket structure with at least four '(' and four ')'; "
    "(6) among passing sequences, sort by normalised_mfe ascending (more negative first); "
    "(7) take the 10th–25th percentile slice by normalised_mfe to avoid the single most "
    "extreme outlier; (8) within that slice, choose the sequence with smallest absolute "
    "distance from GC target 0.6165, breaking ties by sequence_id ascending."
)

DESCRIPTION = (
    "Example folded unadapted RNAGenesis sequence selected from the Stage 1 poster-config run."
)


@dataclass
class SelectedSequence:
    """One sequence chosen for structure export."""

    sequence_id: str
    condition: str
    cleaned_sequence: str
    cleaned_length: int
    gc_fraction: float
    mfe: float
    normalised_mfe: float
    mfe_structure: str
    stage1_pass: bool
    stage1_failure_reasons: str | None
    source_csv: str
    selection_rule: str
    description: str
    paired_base_count: int
    gc_percent: float
    mfe_recomputed: float | None = None
    mfe_structure_recomputed: str | None = None
    mfe_verification_match: bool | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export a poster-ready ViennaRNA secondary-structure figure for one "
            "example unadapted RNAGenesis sequence."
        )
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=PROJECT_ROOT
        / "results"
        / "aim3_stage1_unadapted_30k_poster_config"
        / "stage1_all_sequences.csv",
        help="Stage 1 all-sequences CSV from the poster-config unadapted RNAGenesis run.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results" / "aim3_poster_figures",
        help="Directory for PNG/SVG outputs and metadata.",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=650,
        help="Poster PNG canvas width in pixels.",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        default=1100,
        help="Poster PNG canvas height in pixels.",
    )
    parser.add_argument(
        "--basename",
        default="example_rnagenesis_structure",
        help="Base filename stem for exported files.",
    )
    parser.add_argument(
        "--verify-mfe",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Recompute MFE with ViennaRNA Python module to verify CSV values "
            "(default: on)."
        ),
    )
    return parser.parse_args()


def try_import_rna() -> Any:
    """Import ViennaRNA Python module or exit with a clear message."""
    try:
        import RNA  # noqa: PLC0415

        return RNA
    except ImportError as exc:
        raise SystemExit(
            "ViennaRNA Python module 'RNA' is required. "
            "Activate the rnagenesis-mac conda environment or install viennarna."
        ) from exc


def parse_bool(value: Any) -> bool:
    """Convert CSV booleans that may be strings or numbers."""
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "t"}


def is_valid_rna_sequence(sequence: Any) -> bool:
    """Return True when sequence uses only A/C/G/U."""
    if sequence is None or pd.isna(sequence):
        return False
    text = str(sequence).strip().upper()
    return bool(text) and set(text) <= VALID_RNA_BASES


def count_paired_bases(dot_bracket: Any) -> int:
    """Return the number of paired bases implied by dot-bracket notation."""
    if dot_bracket is None or pd.isna(dot_bracket):
        return 0
    text = str(dot_bracket)
    return min(text.count("("), text.count(")"))


def has_nontrivial_structure(dot_bracket: Any) -> bool:
    """Require at least MIN_PAIRED_BASES paired bases in the structure."""
    return count_paired_bases(dot_bracket) >= MIN_PAIRED_BASES


def is_unadapted_rnagenesis_condition(condition: Any) -> bool:
    """Return True only for explicit unadapted RNAGenesis condition labels."""
    if condition is None or pd.isna(condition):
        return False
    text = str(condition).lower()
    return "unadapted" in text and "rnagenesis" in text


def load_stage1_table(csv_path: Path) -> pd.DataFrame:
    """Load the Stage 1 all-sequences CSV."""
    if not csv_path.is_file():
        raise SystemExit(f"Input CSV not found: {csv_path}")
    return pd.read_csv(csv_path)


def select_example_sequence(df: pd.DataFrame, source_csv: Path) -> SelectedSequence:
    """Apply the deterministic selection rule and return one representative row."""
    working = df.copy()

    if "condition" in working.columns:
        working = working[working["condition"].apply(is_unadapted_rnagenesis_condition)]

    if "stage1_pass" in working.columns:
        passed = working[working["stage1_pass"].apply(parse_bool)].copy()
        if passed.empty:
            raise SystemExit("No Stage 1 passing sequences found after condition filtering.")
        working = passed

    working = working[working["cleaned_sequence"].apply(is_valid_rna_sequence)]
    working = working[working["mfe_structure"].apply(has_nontrivial_structure)]
    if working.empty:
        raise SystemExit(
            "No valid sequences with non-trivial structure found among Stage 1 passing rows."
        )

    working["gc_distance"] = (working["gc_fraction"] - GC_TARGET).abs()
    working = working.sort_values(
        ["normalised_mfe", "sequence_id"],
        ascending=[True, True],
    )

    total = len(working)
    low_index = int(total * MFE_PERCENTILE_LOW)
    high_index = max(low_index + 1, int(total * MFE_PERCENTILE_HIGH))
    candidates = working.iloc[low_index:high_index].copy()
    if candidates.empty:
        raise SystemExit("MFE percentile slice was empty; check selection thresholds.")

    candidates = candidates.sort_values(
        ["gc_distance", "sequence_id"],
        ascending=[True, True],
    )
    row = candidates.iloc[0]

    failure_reasons = row.get("stage1_failure_reasons")
    if pd.isna(failure_reasons):
        failure_reasons = None
    else:
        failure_reasons = str(failure_reasons).strip() or None

    sequence = str(row["cleaned_sequence"]).upper()
    gc_fraction = float(row["gc_fraction"])

    return SelectedSequence(
        sequence_id=str(row["sequence_id"]),
        condition=str(row.get("condition", "")),
        cleaned_sequence=sequence,
        cleaned_length=int(row.get("cleaned_length", len(sequence))),
        gc_fraction=gc_fraction,
        mfe=float(row["mfe"]),
        normalised_mfe=float(row["normalised_mfe"]),
        mfe_structure=str(row["mfe_structure"]),
        stage1_pass=parse_bool(row.get("stage1_pass", True)),
        stage1_failure_reasons=failure_reasons,
        source_csv=str(source_csv.resolve()),
        selection_rule=SELECTION_RULE,
        description=DESCRIPTION,
        paired_base_count=count_paired_bases(row["mfe_structure"]),
        gc_percent=round(gc_fraction * 100.0, 4),
    )


def verify_mfe_with_vienna(
    selected: SelectedSequence,
    rna_module: Any,
) -> SelectedSequence:
    """Optionally refold the sequence and record whether CSV values match."""
    structure, mfe = rna_module.fold(selected.cleaned_sequence)
    recomputed_mfe = float(mfe)
    recomputed_structure = str(structure)
    mfe_match = abs(recomputed_mfe - selected.mfe) < 1e-3
    structure_match = recomputed_structure == selected.mfe_structure
    selected.mfe_recomputed = recomputed_mfe
    selected.mfe_structure_recomputed = recomputed_structure
    selected.mfe_verification_match = mfe_match and structure_match
    return selected


def render_structure_svg_viennarna(
    sequence: str,
    structure: str,
    output_svg: Path,
    rna_module: Any,
) -> None:
    """Write a ViennaRNA SVG structure plot using the Python bindings."""
    output_svg.parent.mkdir(parents=True, exist_ok=True)
    result = rna_module.plot_structure_svg(str(output_svg), sequence, structure)
    if not output_svg.is_file() or output_svg.stat().st_size == 0:
        raise RuntimeError(
            f"ViennaRNA plot_structure_svg failed to create a non-empty SVG at {output_svg} "
            f"(return code {result})."
        )


def render_structure_svg_rnaplot_cli(
    sequence: str,
    structure: str,
    output_svg: Path,
) -> None:
    """Fallback: call the RNAplot command-line tool to produce SVG."""
    rnaplot = shutil.which("RNAplot")
    if rnaplot is None:
        raise RuntimeError(
            "RNAplot command not found on PATH. Install ViennaRNA or use the rnagenesis-mac env."
        )

    output_svg.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rnagenesis_structure_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_text = f">structure\n{sequence}\n{structure}\n"
        completed = subprocess.run(
            [rnaplot, "--output-format=svg"],
            input=input_text,
            text=True,
            cwd=tmp_path,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "RNAplot failed:\n"
                f"stdout: {completed.stdout}\n"
                f"stderr: {completed.stderr}"
            )

        generated_candidates = sorted(tmp_path.glob("*_ss.svg"))
        if not generated_candidates:
            generated_candidates = sorted(tmp_path.glob("*.svg"))
        if not generated_candidates:
            raise RuntimeError(f"RNAplot did not produce an SVG file in {tmp_path}.")

        shutil.copyfile(generated_candidates[0], output_svg)


def sanitize_viennarna_svg(svg_path: Path) -> None:
    """Remove interactive script blocks; keep ViennaRNA drawing elements only."""
    tree = ET.parse(svg_path)
    root = tree.getroot()
    for element in list(root):
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "script":
            root.remove(element)
    tree.write(svg_path, encoding="utf-8", xml_declaration=True)


def _parse_points(points_text: str) -> list[tuple[float, float]]:
    """Parse SVG polyline points into (x, y) pairs."""
    numbers = [float(value) for value in re.findall(r"-?\d+\.?\d*", points_text)]
    if len(numbers) % 2 != 0:
        raise ValueError(
            f"SVG polyline points must be x/y pairs; found {len(numbers)} coordinates."
        )
    return list(zip(numbers[0::2], numbers[1::2], strict=True))


def _parse_transform(transform_text: str) -> tuple[float, float, float, float]:
    """Parse scale(...) translate(...) from ViennaRNA SVG group transforms."""
    scale_match = re.search(
        r"scale\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)",
        transform_text,
    )
    translate_match = re.search(
        r"translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)",
        transform_text,
    )
    scale_x = float(scale_match.group(1)) if scale_match else 1.0
    scale_y = float(scale_match.group(2)) if scale_match else 1.0
    translate_x = float(translate_match.group(1)) if translate_match else 0.0
    translate_y = float(translate_match.group(2)) if translate_match else 0.0
    return scale_x, scale_y, translate_x, translate_y


def rasterize_viennarna_svg_with_pil(svg_path: Path) -> Any:
    """Minimal rasterizer for ViennaRNA SVG when external converters are unavailable."""
    from PIL import Image, ImageDraw

    tree = ET.parse(svg_path)
    root = tree.getroot()

    width = float(root.attrib.get("width", "452"))
    height = float(root.attrib.get("height", "452"))
    image = Image.new("RGBA", (int(width), int(height)), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)

    for group in root.iter():
        tag = group.tag.rsplit("}", 1)[-1]
        if tag != "g":
            continue
        transform = group.attrib.get("transform", "")
        scale_x, scale_y, translate_x, translate_y = _parse_transform(transform)

        def to_canvas(x: float, y: float) -> tuple[float, float]:
            return (x * scale_x + translate_x, y * scale_y + translate_y)

        for child in group:
            child_tag = child.tag.rsplit("}", 1)[-1]
            if child_tag == "polyline":
                points = [_parse_points(child.attrib.get("points", ""))]
                flat_points = points[0]
                if flat_points:
                    canvas_points = [to_canvas(x, y) for x, y in flat_points]
                    draw.line(canvas_points, fill=(128, 128, 128, 255), width=3)
            elif child_tag == "g":
                for line in child:
                    line_tag = line.tag.rsplit("}", 1)[-1]
                    if line_tag != "line":
                        continue
                    x1 = float(line.attrib["x1"])
                    y1 = float(line.attrib["y1"])
                    x2 = float(line.attrib["x2"])
                    y2 = float(line.attrib["y2"])
                    start = to_canvas(x1, y1)
                    end = to_canvas(x2, y2)
                    draw.line([start, end], fill=(220, 0, 0, 255), width=4)

    return image


def svg_to_png_bytes(svg_path: Path) -> bytes:
    """Convert SVG to PNG bytes using the first available converter."""
    try:
        import cairosvg  # noqa: PLC0415

        return cairosvg.svg2png(url=str(svg_path))
    except ImportError:
        pass

    for command_name in ("rsvg-convert", "inkscape"):
        converter = shutil.which(command_name)
        if converter is None:
            continue
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_png:
            tmp_png_path = Path(tmp_png.name)
        try:
            if command_name == "rsvg-convert":
                cmd = [converter, str(svg_path), "-o", str(tmp_png_path)]
            else:
                cmd = [
                    converter,
                    str(svg_path),
                    "--export-type=png",
                    f"--export-filename={tmp_png_path}",
                ]
            completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if completed.returncode == 0 and tmp_png_path.is_file():
                return tmp_png_path.read_bytes()
        finally:
            if tmp_png_path.is_file():
                tmp_png_path.unlink()

    # Last resort: rasterize the ViennaRNA SVG drawing primitives with Pillow.
    from PIL import Image

    image = rasterize_viennarna_svg_with_pil(svg_path)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def fit_image_to_canvas(
    png_bytes: bytes,
    canvas_width: int,
    canvas_height: int,
    background: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> Any:
    """Scale an image to fit within a fixed canvas and centre it."""
    from PIL import Image

    image = Image.open(BytesIO(png_bytes)).convert("RGBA")
    scale = min(canvas_width / image.width, canvas_height / image.height)
    new_width = max(1, int(round(image.width * scale)))
    new_height = max(1, int(round(image.height * scale)))
    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (canvas_width, canvas_height), background)
    offset_x = (canvas_width - new_width) // 2
    offset_y = (canvas_height - new_height) // 2
    canvas.paste(resized, (offset_x, offset_y), resized)
    return canvas


def write_metadata(
    selected: SelectedSequence,
    output_dir: Path,
    basename: str,
    png_path: Path,
    svg_path: Path,
    canvas_width: int,
    canvas_height: int,
) -> tuple[Path, Path]:
    """Write human-readable and JSON metadata sidecars."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_txt = output_dir / f"{basename}_metadata.txt"
    metadata_json = output_dir / f"{basename}_metadata.json"

    png_size = None
    if png_path.is_file():
        from PIL import Image

        with Image.open(png_path) as image:
            png_size = {"width_px": image.width, "height_px": image.height}

    payload = {
        "description": selected.description,
        "sequence_id": selected.sequence_id,
        "condition": selected.condition,
        "cleaned_sequence": selected.cleaned_sequence,
        "length": selected.cleaned_length,
        "gc_fraction": selected.gc_fraction,
        "gc_percent": selected.gc_percent,
        "mfe_kcal_per_mol": selected.mfe,
        "normalised_mfe": selected.normalised_mfe,
        "dot_bracket_structure": selected.mfe_structure,
        "paired_base_count": selected.paired_base_count,
        "stage1_pass": selected.stage1_pass,
        "stage1_failure_reasons": selected.stage1_failure_reasons,
        "source_csv": selected.source_csv,
        "selection_rule": selected.selection_rule,
        "selection_parameters": {
            "gc_target": GC_TARGET,
            "min_paired_bases": MIN_PAIRED_BASES,
            "mfe_percentile_low": MFE_PERCENTILE_LOW,
            "mfe_percentile_high": MFE_PERCENTILE_HIGH,
        },
        "mfe_verification": {
            "recomputed_mfe_kcal_per_mol": selected.mfe_recomputed,
            "recomputed_dot_bracket_structure": selected.mfe_structure_recomputed,
            "csv_values_match_recomputed": selected.mfe_verification_match,
        },
        "output_files": {
            "png": str(png_path.resolve()),
            "svg": str(svg_path.resolve()) if svg_path.is_file() else None,
            "metadata_txt": str(metadata_txt.resolve()),
            "metadata_json": str(metadata_json.resolve()),
        },
        "figure_settings": {
            "canvas_width_px": canvas_width,
            "canvas_height_px": canvas_height,
            "title": None,
            "caption": None,
        },
        "png_dimensions": png_size,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/export_example_structure.py",
    }

    lines = [
        "Example folded unadapted RNAGenesis structure export",
        "=" * 60,
        f"Description: {selected.description}",
        "",
        "Selected sequence",
        "-" * 60,
        f"Sequence ID: {selected.sequence_id}",
        f"Condition: {selected.condition}",
        f"Sequence (A/C/G/U): {selected.cleaned_sequence}",
        f"Length (nt): {selected.cleaned_length}",
        f"GC fraction: {selected.gc_fraction:.6f}",
        f"GC percent: {selected.gc_percent:.4f}%",
        f"MFE (kcal/mol): {selected.mfe:.6f}",
        f"Normalised MFE: {selected.normalised_mfe:.6f}",
        f"Dot-bracket structure: {selected.mfe_structure}",
        f"Paired bases in structure: {selected.paired_base_count}",
        f"Stage 1 pass: {selected.stage1_pass}",
        f"Stage 1 failure reasons: {selected.stage1_failure_reasons or 'none'}",
        "",
        "Provenance",
        "-" * 60,
        f"Source CSV: {selected.source_csv}",
        "",
        "Selection rule",
        "-" * 60,
        selected.selection_rule,
        "",
        "Output files",
        "-" * 60,
        f"PNG: {png_path.resolve()}",
        f"SVG: {svg_path.resolve() if svg_path.is_file() else 'not written'}",
        f"Metadata JSON: {metadata_json.resolve()}",
    ]
    if png_size is not None:
        lines.extend(
            [
                "",
                "PNG dimensions",
                "-" * 60,
                f"Width: {png_size['width_px']} px",
                f"Height: {png_size['height_px']} px",
            ]
        )
    if selected.mfe_recomputed is not None:
        lines.extend(
            [
                "",
                "ViennaRNA verification",
                "-" * 60,
                f"Recomputed MFE (kcal/mol): {selected.mfe_recomputed:.6f}",
                f"Recomputed structure: {selected.mfe_structure_recomputed}",
                f"CSV matches recomputed values: {selected.mfe_verification_match}",
            ]
        )

    metadata_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    metadata_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return metadata_txt, metadata_json


def print_summary(selected: SelectedSequence, png_path: Path) -> None:
    """Print the selected sequence details and PNG confirmation."""
    print("Selected example structure")
    print("-" * 40)
    print(f"Sequence ID: {selected.sequence_id}")
    print(f"Sequence: {selected.cleaned_sequence}")
    print(f"Length: {selected.cleaned_length}")
    print(f"GC content: {selected.gc_fraction:.6f} ({selected.gc_percent:.4f}%)")
    print(f"MFE (kcal/mol): {selected.mfe:.6f}")
    print(f"Normalised MFE: {selected.normalised_mfe:.6f}")
    print(f"Dot-bracket structure: {selected.mfe_structure}")
    print(f"Stage 1 pass: {selected.stage1_pass}")
    print(f"Output PNG: {png_path.resolve()}")

    if png_path.is_file():
        from PIL import Image

        with Image.open(png_path) as image:
            print(f"PNG exists: yes")
            print(f"PNG dimensions: {image.width} x {image.height} px")
    else:
        print("PNG exists: no")


def main() -> int:
    args = parse_args()
    input_csv = args.input_csv.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    basename = args.basename

    png_path = output_dir / f"{basename}.png"
    svg_path = output_dir / f"{basename}.svg"

    df = load_stage1_table(input_csv)
    selected = select_example_sequence(df, input_csv)

    rna_module = try_import_rna()
    if args.verify_mfe:
        selected = verify_mfe_with_vienna(selected, rna_module)

    try:
        render_structure_svg_viennarna(
            selected.cleaned_sequence,
            selected.mfe_structure,
            svg_path,
            rna_module,
        )
    except RuntimeError:
        render_structure_svg_rnaplot_cli(
            selected.cleaned_sequence,
            selected.mfe_structure,
            svg_path,
        )

    sanitize_viennarna_svg(svg_path)

    try:
        png_bytes = svg_to_png_bytes(svg_path)
    except Exception as exc:
        raise SystemExit(
            "ViennaRNA SVG was written, but PNG conversion failed. "
            f"SVG path: {svg_path}. "
            "Install cairosvg (pip install cairosvg) or rsvg-convert/Inkscape, "
            "or ensure Pillow is available for the ViennaRNA SVG fallback rasterizer. "
            f"Original error: {exc}"
        ) from exc

    poster_image = fit_image_to_canvas(
        png_bytes,
        canvas_width=args.max_width,
        canvas_height=args.max_height,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    poster_image.save(png_path, format="PNG")

    write_metadata(
        selected=selected,
        output_dir=output_dir,
        basename=basename,
        png_path=png_path,
        svg_path=svg_path,
        canvas_width=args.max_width,
        canvas_height=args.max_height,
    )

    print_summary(selected, png_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
