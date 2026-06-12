# cytopipe

CytoTable-based data-management / glue layer for a Nextflow-orchestrated cell-painting
feature-extraction pipeline. It is packaged as a container image and consumed by the
pipeline repo, [cell-painting-pipeline](https://github.com/jakobhuuse/cell-painting-pipeline).

> ⚠️ Skeleton / work in progress — CLI surface is defined, stage logic is stubbed.

## CLI

- `cytopipe convert` — CytoTable conversion of CellProfiler output → single-cell parquet
- `cytopipe bridge`  — CellProfiler → DeepProfiler metadata/segmentation handoff

CellProfiler, DeepProfiler, and pycytominer run via their own images in the pipeline, not
through this CLI.

## Develop

```bash
uv sync                       # install deps (incl. dev: ruff, pytest)
uv run ruff check .           # lint
uv run ruff format .          # format
uv run pytest                 # tests
uv run cytopipe --help        # CLI
```

## Container

```bash
docker build -t cytopipe:dev .
```

The image is published to `ghcr.io/jakobhuuse/cytopipe` on tag (see
[.github/workflows/release.yml](.github/workflows/release.yml)); the pipeline references it
via `params.cytopipe_image`.
