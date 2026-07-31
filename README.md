# cytopipe

[![CI](https://github.com/jakobhuuse/cytopipe/actions/workflows/ci.yml/badge.svg)](https://github.com/jakobhuuse/cytopipe/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jakobhuuse/cytopipe/graph/badge.svg)](https://codecov.io/gh/jakobhuuse/cytopipe)
[![Python](https://img.shields.io/badge/python-3.13%2B-3776ab.svg)](https://www.python.org/downloads/)

cytopipe is the data-management and glue layer for a Nextflow-orchestrated cell-painting feature-extraction pipeline. It is packaged as a container image and consumed by the pipeline repo, [cell-paint-pipeline](https://github.com/jakobhuuse/cell-paint-pipeline).

## Installation

cytopipe ships as a container image, and the pipeline pulls it automatically, so most users never install it directly. To pull the published image:

```bash
docker pull ghcr.io/jakobhuuse/cytopipe:1.2.2
```

To install the CLI from source for local work:

```bash
uv sync
uv run cytopipe --help
```

### Requirements

- Python 3.13 or newer and [uv](https://docs.astral.sh/uv/) for source installs.
- Docker to build or run the container image.

## Usage

The CLI exposes seven subcommands.

- `cytopipe loaddata` builds a CellProfiler LoadData CSV (plus per-chunk CSVs) from a plate's raw images.
- `cytopipe loaddata-filter` drops QC-excluded (Plate, Well, Site) image sets from an already-built LoadData CSV.
- `cytopipe bridge` turns CellProfiler output into DeepProfiler inputs (locations and index.csv).
- `cytopipe convert` runs the CytoTable conversion of CellProfiler or DeepProfiler output to single-cell parquet, and concatenates parquet parts back into one file.
- `cytopipe aggregate` collapses single-cell parquet to well-level median profiles, a memory-bounded streaming replacement for `pycytominer aggregate` (see below).
- `cytopipe qc` scans a plate's CellProfiler QC output and builds a self-contained HTML gallery for reviewing image quality by eye, with a button to download an exclusion list.
- `cytopipe report` renders the standard Cell Painting QC figures from published profiles.

CellProfiler, DeepProfiler, and the rest of pycytominer (annotate, normalize, feature selection, consensus) run via their own images in the pipeline, not through this CLI.

### Channel mapping

`cytopipe loaddata` assigns each filename's `w<N>` channel number to a Cell Painting stain via a table (`CHANNEL_BY_NUMBER` in [scan.py](src/cytopipe/loaddata/scan.py)), currently `w1=DNA, w2=Mito, w3=AGP, w4=RNA, w5=ER`. That is the expected ordering for the acquisition setup this was written against. An instrument, protocol, or filter configuration that numbers its channels differently needs that table updated to match, since cytopipe reads the ordering from it rather than from the images.

### Why aggregate lives here

`pycytominer aggregate` reads the whole single-cell table into pandas and upcasts every feature to float64 before the groupby-median, so its peak memory is several times the input and scales with cell count, which OOM-kills on large plates. `cytopipe aggregate` computes the same median in DuckDB, streaming from parquet with a bounded `--memory-limit` and spilling to `--temp-directory` instead of holding the plate in RAM. Values are cast to double before the median so the arithmetic itself runs at pycytominer's precision, NaN is skipped like pandas `median(skipna=True)`, and groups are ordered by strata. It reads `--features infer` (CellProfiler compartment prefixes) or an explicit comma-separated list (the DeepProfiler embedding columns). Note this isn't a guarantee of bit-exact parity with a pycytominer run end to end, the CellProfiler branch's single-cell parquet was already downcast to float32 during the earlier CytoTable conversion, so results are float32-precision-limited going in even though the median math over them is exact.

Run any subcommand with `--help` to see its options:

```bash
uv run cytopipe loaddata --help
```

## Testing

The suite runs under pytest (see [tests/](tests/)). It needs only the dev dependencies, no Docker.

```bash
uv sync                 # install dev deps (pytest, pytest-cov, ruff)
uv run pytest           # run the tests
uv run pytest --cov     # run with a coverage report
```

This is what CI runs on every push and PR, alongside `uv run ruff check .` (see [.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Support

Open an issue on the [issue tracker](https://github.com/jakobhuuse/cytopipe/issues) for questions or bug reports.

## Acknowledgments

The `convert` command is built on [CytoTable](https://github.com/cytomining/CytoTable). cytopipe interoperates with the [CellProfiler](https://cellprofiler.org/), [DeepProfiler](https://github.com/cytomining/DeepProfiler), and [pycytominer](https://github.com/cytomining/pycytominer) tooling from the cytomining ecosystem by reading and writing their file formats.

## License

Licensed under the [BSD 3-Clause License](LICENSE). Copyright (c) 2026 Jakob Huuse, SINTEF Industri.
