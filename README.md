# cytopipe

CytoTable-based data-management / glue layer for a Nextflow-orchestrated cell-painting
feature-extraction pipeline. Packaged as a container image and consumed by the pipeline repo,
[cell-painting-pipeline](https://github.com/jakobhuuse/cell-painting-pipeline).

## CLI

- `cytopipe loaddata` — build a CellProfiler LoadData CSV (plus per-chunk CSVs) from a plate's raw images
- `cytopipe bridge`   — turn CellProfiler output into DeepProfiler inputs (locations + index.csv)
- `cytopipe convert`  — CytoTable conversion of CellProfiler/DeepProfiler output to single-cell parquet
- `cytopipe report`   — render the standard Cell Painting QC figures from published profiles

CellProfiler, DeepProfiler, and pycytominer run via their own images in the pipeline, not
through this CLI.

## Develop

```bash
uv sync                 # install deps (incl. dev: ruff, pytest)
uv run ruff check .     # lint
uv run pytest           # tests
uv run cytopipe --help  # CLI
```

## Container

```bash
docker build -t cytopipe:dev .
```

Published to `ghcr.io/jakobhuuse/cytopipe` on tag (see
[.github/workflows/release.yml](.github/workflows/release.yml)); the pipeline references it via
`params.cytopipe_image`.
