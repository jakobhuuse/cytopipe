"""Tests for the parquet concat guard rails (lossless repackaging)."""

from pathlib import Path

import duckdb
import pytest

from cytopipe.parquet import concat_parquets


def _write_parquet(con: duckdb.DuckDBPyConnection, path: Path, columns, rows) -> None:
    col_list = ", ".join(columns)
    values = ", ".join("(" + ", ".join(repr(v) for v in row) + ")" for row in rows)
    con.execute(
        f"COPY (SELECT * FROM (VALUES {values}) AS t({col_list})) TO '{path}' (FORMAT PARQUET)"
    )


def test_concat_parquets_is_lossless(tmp_path):
    parts = tmp_path / "parts"
    parts.mkdir()
    con = duckdb.connect()
    _write_parquet(con, parts / "a.parquet", ["id", "label"], [(1, "x"), (2, "y")])
    _write_parquet(con, parts / "b.parquet", ["id", "label"], [(3, "z")])
    dest = tmp_path / "out.parquet"

    concat_parquets(parts, dest)

    n = con.execute("SELECT count(*) FROM read_parquet(?)", [str(dest)]).fetchone()[0]
    peek = con.execute("SELECT * FROM read_parquet(?) LIMIT 0", [str(dest)])
    cols = {c[0] for c in peek.description}
    assert n == 3
    assert cols == {"id", "label"}


def test_concat_parquets_tolerates_column_reordering(tmp_path):
    # Identical column *set*, different order — union_by_name must still be lossless.
    parts = tmp_path / "parts"
    parts.mkdir()
    con = duckdb.connect()
    _write_parquet(con, parts / "a.parquet", ["id", "label"], [(1, "x")])
    _write_parquet(con, parts / "b.parquet", ["label", "id"], [("y", 2)])
    dest = tmp_path / "out.parquet"

    concat_parquets(parts, dest)

    n = con.execute("SELECT count(*) FROM read_parquet(?)", [str(dest)]).fetchone()[0]
    assert n == 2


def test_concat_parquets_schema_mismatch_raises(tmp_path):
    parts = tmp_path / "parts"
    parts.mkdir()
    con = duckdb.connect()
    _write_parquet(con, parts / "a.parquet", ["id", "label"], [(1, "x")])
    _write_parquet(con, parts / "b.parquet", ["id", "other"], [(2, 9)])
    dest = tmp_path / "out.parquet"

    with pytest.raises(ValueError, match="schema mismatch"):
        concat_parquets(parts, dest)


def test_concat_parquets_empty_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        concat_parquets(tmp_path, tmp_path / "out.parquet")
