# cytopipe

[![CI](https://github.com/jakobhuuse/cytopipe/actions/workflows/ci.yml/badge.svg)](https://github.com/jakobhuuse/cytopipe/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jakobhuuse/cytopipe/graph/badge.svg)](https://codecov.io/gh/jakobhuuse/cytopipe)
[![Python](https://img.shields.io/badge/python-3.13%2B-3776ab.svg)](https://www.python.org/downloads/)

cytopipe is the data-management and glue layer for a Nextflow-orchestrated cell-painting
feature-extraction pipeline. It is packaged as a container image and consumed by the pipeline
repo, [cell-paint-pipeline](https://github.com/jakobhuuse/cell-paint-pipeline). It is the only
bespoke code in the stack.

## Installation

cytopipe ships as a container image, and the pipeline pulls it automatically, so most users never
install it directly. To pull the published image:

```bash
docker pull ghcr.io/jakobhuuse/cytopipe:1.0.0
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

The CLI exposes five subcommands:

- `cytopipe loaddata` builds a CellProfiler LoadData CSV (plus per-chunk CSVs) from a plate's raw
  images.
- `cytopipe bridge` turns CellProfiler output into DeepProfiler inputs (locations and index.csv).
- `cytopipe convert` runs the CytoTable conversion of CellProfiler or DeepProfiler output to
  single-cell parquet.
- `cytopipe aggregate` collapses single-cell parquet to well-level median profiles, a
  memory-bounded streaming replacement for `pycytominer aggregate` (see below).
- `cytopipe report` renders the standard Cell Painting QC figures from published profiles.

CellProfiler, DeepProfiler, and the rest of pycytominer (annotate, normalize, feature selection,
consensus) run via their own images in the pipeline, not through this CLI.

### Why aggregate lives here

`pycytominer aggregate` reads the whole single-cell table into pandas and upcasts every feature to
float64 before the groupby-median, so its peak memory is several times the input and scales with
cell count, which OOM-kills on large plates. `cytopipe aggregate` computes the same median in
DuckDB, streaming from parquet with a bounded `--memory-limit` and spilling to `--temp-directory`
instead of holding the plate in RAM. It is a faithful drop-in: values are cast to double to match
pycytominer's precision, NaN is skipped like pandas `median(skipna=True)`, and groups are ordered
by strata. It reads `--features infer` (CellProfiler compartment prefixes) or an explicit
comma-separated list (the DeepProfiler embedding columns).

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

This is what CI runs on every push and PR, alongside `uv run ruff check .` (see
[.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Support

Open an issue on the [issue tracker](https://github.com/jakobhuuse/cytopipe/issues) for questions
or bug reports.

## Acknowledgments

The `convert` command is built on [CytoTable](https://github.com/cytomining/CytoTable). cytopipe
interoperates with the [CellProfiler](https://cellprofiler.org/),
[DeepProfiler](https://github.com/cytomining/DeepProfiler), and
[pycytominer](https://github.com/cytomining/pycytominer) tooling from the cytomining ecosystem by
reading and writing their file formats.

## License

Licensed under the [BSD 3-Clause License](LICENSE). Copyright (c) 2026 Jakob Huuse, SINTEF Industri.
