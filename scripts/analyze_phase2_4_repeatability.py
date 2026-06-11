"""Analyze Phase 2.4 H200 seed repeatability outputs and write a markdown report."""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunOutput:
    """One repeatability run and its copied project-repo destination."""

    label: str
    source_dir: Path
    source_file: Path
    copied_file: Path
    line_count: int
    sha256: str


def find_single_txt_file(output_dir: Path) -> Path:
    """Return the single .txt file in output_dir or raise a clear error."""
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Output directory missing: {output_dir}")

    matches = sorted(output_dir.glob("*.txt"))
    if not matches:
        raise FileNotFoundError(
            f"No .txt output file found in {output_dir}"
        )
    if len(matches) > 1:
        listed = "\n".join(f"  - {path}" for path in matches)
        raise ValueError(
            f"Expected one .txt file in {output_dir}, found {len(matches)}:\n{listed}"
        )
    return matches[0]


def copy_output(src: Path, dest: Path) -> None:
    """Copy one generated output file into the project repo."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def count_lines(path: Path) -> int:
    """Count lines in a text file (equivalent to wc -l)."""
    with path.open(encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def sha256_file(path: Path) -> str:
    """Return the SHA256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files_identical(path1: Path, path2: Path) -> bool:
    """Return whether two files are byte-identical."""
    return filecmp.cmp(path1, path2, shallow=False)


def comparison_label(identical: bool) -> str:
    """Convert a boolean comparison result to a report label."""
    return "identical" if identical else "different"


def same_seed_interpretation(identical: bool) -> str:
    """Explain the same-seed repeatability outcome."""
    if identical:
        return (
            "Fixed-seed generation appears exactly repeatable for this small "
            "H200 workload."
        )
    return (
        "Fixed-seed generation is not byte-identical under the current H200 "
        "GPU/software stack; reproducibility should be assessed by "
        "distributional metrics."
    )


def different_seed_interpretation(identical: bool) -> str:
    """Explain the different-seed comparison outcome."""
    if identical:
        return (
            "Changing the seed did not change sampled outputs for this "
            "workload; this is unexpected and should be investigated."
        )
    return "Changing the seed changes sampled outputs as expected."


def write_report(
    *,
    report_path: Path,
    run_date: str,
    host: str,
    conda_env: str,
    cuda_visible_devices: str,
    rnagenesis_commit: str,
    run_a: RunOutput,
    run_b: RunOutput,
    run_c: RunOutput,
    same_seed_identical: bool,
    different_seed_identical: bool,
) -> None:
    """Write the Phase 2.4 repeatability markdown report."""
    same_seed_result = comparison_label(same_seed_identical)
    different_seed_result = comparison_label(different_seed_identical)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "\n".join(
            [
                "# H200 Phase 2.4 — fix random seeds and confirm repeatability",
                "",
                "## Stage",
                "",
                "Phase 2.4 — fix random seeds and confirm repeatability",
                "",
                "## Purpose",
                "",
                (
                    "Test whether RNAGenesis aptamer generation is repeatable under "
                    "a fixed seed on the H200 server, and whether changing the "
                    "seed changes the generated outputs."
                ),
                "",
                "## Run metadata",
                "",
                f"- Date: {run_date}",
                f"- Host: {host}",
                f"- Conda environment: {conda_env}",
                f"- CUDA_VISIBLE_DEVICES: {cuda_visible_devices}",
                f"- RNAGenesis commit: {rnagenesis_commit}",
                "",
                "## Generation settings",
                "",
                "- num_inference_steps: 20",
                "- batch_size: 8",
                "- batch_num: 1",
                "- seeds tested: 42 (replicate A), 42 (replicate B), 43 (different-seed comparison)",
                "- max_seq_len: 37",
                "- top_p: 0.95",
                "- top_k: 0",
                "- enc_dec_file: configs/rnagenesis/autoencoder",
                "- dm_file: checkpoints/Aptamer/diffusion",
                "- decoder_config: config-progen2-small-rna_tokenizer_v2",
                "- guidance: off",
                "- tree/search: off",
                "",
                "## RNAGenesis source output files",
                "",
                f"- `{run_a.source_file}`",
                f"- `{run_b.source_file}`",
                f"- `{run_c.source_file}`",
                "",
                "## Project copied output files",
                "",
                f"- `{run_a.copied_file}`",
                f"- `{run_b.copied_file}`",
                f"- `{run_c.copied_file}`",
                "",
                "## Line counts",
                "",
                "| File | Lines |",
                "| --- | ---: |",
                f"| {run_a.copied_file.name} | {run_a.line_count} |",
                f"| {run_b.copied_file.name} | {run_b.line_count} |",
                f"| {run_c.copied_file.name} | {run_c.line_count} |",
                "",
                "## SHA256 hashes",
                "",
                "| File | SHA256 |",
                "| --- | --- |",
                f"| {run_a.copied_file.name} | `{run_a.sha256}` |",
                f"| {run_b.copied_file.name} | `{run_b.sha256}` |",
                f"| {run_c.copied_file.name} | `{run_c.sha256}` |",
                "",
                "## Same-seed comparison result",
                "",
                f"Comparison: {run_a.copied_file.name} vs {run_b.copied_file.name}",
                "",
                f"Result: **{same_seed_result}**",
                "",
                "## Different-seed comparison result",
                "",
                f"Comparison: {run_a.copied_file.name} vs {run_c.copied_file.name}",
                "",
                f"Result: **{different_seed_result}**",
                "",
                "## Interpretation",
                "",
                f"- Same-seed repeatability: {same_seed_interpretation(same_seed_identical)}",
                f"- Different-seed behaviour: {different_seed_interpretation(different_seed_identical)}",
                "",
                "## Next step",
                "",
                (
                    "Proceed to cleaning, merging, deduplicating, and characterising "
                    "the 30,080-sequence unadapted RNAGenesis baseline pool."
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


def process_run(
    *,
    rnagenesis_repo: Path,
    results_dir: Path,
    output_folder: str,
    label: str,
) -> RunOutput:
    """Locate, copy, and summarize one repeatability output."""
    source_dir = rnagenesis_repo / "generation_sequences" / output_folder
    source_file = find_single_txt_file(source_dir)
    copied_file = results_dir / f"{label}.txt"

    copy_output(source_file, copied_file)
    line_count = count_lines(copied_file)
    sha256 = sha256_file(copied_file)

    return RunOutput(
        label=label,
        source_dir=source_dir,
        source_file=source_file,
        copied_file=copied_file,
        line_count=line_count,
        sha256=sha256,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Copy Phase 2.4 repeatability outputs into the project repo, "
            "compare them, and write a markdown report."
        )
    )
    parser.add_argument("--rnagenesis-repo", type=Path, required=True)
    parser.add_argument("--project-repo", type=Path, required=True)
    parser.add_argument("--output-folder-a", required=True)
    parser.add_argument("--output-folder-b", required=True)
    parser.add_argument("--output-folder-c", required=True)
    parser.add_argument("--label-a", required=True)
    parser.add_argument("--label-b", required=True)
    parser.add_argument("--label-c", required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--run-date", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--conda-env", required=True)
    parser.add_argument("--cuda-visible-devices", required=True)
    parser.add_argument("--rnagenesis-commit", required=True)
    return parser.parse_args()


def main() -> int:
    """Run the Phase 2.4 repeatability analysis workflow."""
    args = parse_args()

    run_a = process_run(
        rnagenesis_repo=args.rnagenesis_repo,
        results_dir=args.results_dir,
        output_folder=args.output_folder_a,
        label=args.label_a,
    )
    run_b = process_run(
        rnagenesis_repo=args.rnagenesis_repo,
        results_dir=args.results_dir,
        output_folder=args.output_folder_b,
        label=args.label_b,
    )
    run_c = process_run(
        rnagenesis_repo=args.rnagenesis_repo,
        results_dir=args.results_dir,
        output_folder=args.output_folder_c,
        label=args.label_c,
    )

    same_seed_identical = files_identical(run_a.copied_file, run_b.copied_file)
    different_seed_identical = files_identical(run_a.copied_file, run_c.copied_file)

    write_report(
        report_path=args.report_path,
        run_date=args.run_date,
        host=args.host,
        conda_env=args.conda_env,
        cuda_visible_devices=args.cuda_visible_devices,
        rnagenesis_commit=args.rnagenesis_commit,
        run_a=run_a,
        run_b=run_b,
        run_c=run_c,
        same_seed_identical=same_seed_identical,
        different_seed_identical=different_seed_identical,
    )

    print("Copied outputs:")
    for run in (run_a, run_b, run_c):
        print(f"  {run.label}: {run.copied_file}")

    print("\nLine counts:")
    for run in (run_a, run_b, run_c):
        print(f"  {run.copied_file.name}: {run.line_count}")

    print("\nSHA256 hashes:")
    for run in (run_a, run_b, run_c):
        print(f"  {run.copied_file.name}: {run.sha256}")

    print(
        "\nSame-seed comparison "
        f"({run_a.copied_file.name} vs {run_b.copied_file.name}): "
        f"{comparison_label(same_seed_identical)}"
    )
    print(
        "Different-seed comparison "
        f"({run_a.copied_file.name} vs {run_c.copied_file.name}): "
        f"{comparison_label(different_seed_identical)}"
    )
    print(f"\nReport written to: {args.report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
