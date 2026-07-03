FROM python:3.13-slim

# procps provides `ps`, which Nextflow needs to collect per-task metrics
# for trace/report logging.
RUN apt-get update && apt-get install -y --no-install-recommends \
        procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

ENTRYPOINT ["cytopipe"]
CMD ["--help"]
