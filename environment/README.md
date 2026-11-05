# Environment records and CPU checks

This directory preserves environment snapshots from the MRes work. The selected
CPU tests below can be run without model checkpoints, GPU access or private
corpus inputs.

## Recorded environments

| File | Role |
| --- | --- |
| `mac_environment.yml` | Historical Mac development environment, named `rnagenesis-mac`. |
| `mac_pip_freeze.txt` | Companion package inventory for the Mac environment. |
| `environment_a6000.yml` | Historical A6000 execution environment. |
| `environment_h200.yml` | Historical H200 execution environment, named `rnagenesis-h200`. |

These exports include platform-specific builds and local paths. They are records
of the original machines, rather than portable installation instructions.

The [frozen H200 environment manifest](../docs/fine_tuning/environment_manifest.md)
records the fine-tuning environment, including the required local diffusers
compatibility patch. Matching the diffusers package version alone does not
reproduce that patch. Required external model assets and their hashes are in the
[model asset manifest](../docs/fine_tuning/model_asset_manifest.md).

The [A6000 rebuild procedure](../docs/a6000_reinstall_procedure.md) is retained as
a historical execution record. Target preparation has its own
[environment and reproduction instructions](../target/README.md).

## Selected CPU tests

From the repository root, in an environment with `pytest`, `pandas` and `numpy`:

```bash
python -m pytest -q tests/data_preparation/test_aptaindex_sequence_parser.py tests/test_stage1_hard_filter.py
```

ViennaRNA's Python module `RNA` enables the MFE tests in the Stage 1 module;
those tests skip if it is unavailable. The AptaIndex parser tests use invented
chemical notation and do not require the source dataset.

For the target-preparation unit tests, run from `target/`:

```bash
python -m unittest -v test_prepare_ndm1_target.py
```

On 1 November 2026, a clean snapshot at commit
`4e6647f21c919f663df8999059689054d0171fb7` passed 75 tests in the first command
and 7 target-preparation tests in the existing Mac environment:

| Component | Observed version |
| --- | --- |
| Python | 3.10.18 |
| pytest | 9.1.0 |
| pandas | 2.3.3 |
| numpy | 1.26.4 |
| ViennaRNA | 2.7.2 |

Other tests include integration checks against source snapshots or fixtures
under ignored `data/` paths. Running the entire suite without those inputs can
produce missing-file errors. The selected checks above do not establish a clean
GPU environment rebuild or reproduce training and generation.
