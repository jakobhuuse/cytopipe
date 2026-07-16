"""Tests for the parquet concat guard rails (lossless repackaging)."""

import sqlite3
from pathlib import Path

import duckdb
import pytest

from cytopipe.convert import parquet
from cytopipe.convert.parquet import (
    _source_has_all_compartments,
    cellprofiler_to_parquet,
    concat_parquets,
)


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


def test_concat_parquets_recurses_into_subdirs(tmp_path):
    # concat_parquets globs recursively; parts nested under source dirs must be found.
    parts = tmp_path / "parts"
    (parts / "26157").mkdir(parents=True)
    (parts / "26158").mkdir()
    con = duckdb.connect()
    _write_parquet(con, parts / "26157" / "a.parquet", ["id", "label"], [(1, "x")])
    _write_parquet(con, parts / "26158" / "b.parquet", ["id", "label"], [(2, "y")])
    dest = tmp_path / "out.parquet"

    concat_parquets(parts, dest)

    n = con.execute("SELECT count(*) FROM read_parquet(?)", [str(dest)]).fetchone()[0]
    assert n == 2


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


def test_concat_parquets_accepts_threads(tmp_path):
    # threads bounds DuckDB's worker count so memory does not scale with host cores.
    parts = tmp_path / "parts"
    parts.mkdir()
    con = duckdb.connect()
    _write_parquet(con, parts / "a.parquet", ["id"], [(1,), (2,)])
    dest = tmp_path / "out.parquet"

    concat_parquets(parts, dest, threads=1)

    assert con.execute("SELECT count(*) FROM read_parquet(?)", [str(dest)]).fetchone()[0] == 2


def _make_cp_sqlite(path: Path, *, objects: int, compartments=("Cells", "Nuclei", "Cytoplasm")):
    """Minimal CellProfiler-style SQLite: 1 image row plus `objects` rows per compartment."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE Per_Image (ImageNumber INTEGER)")
    con.execute("INSERT INTO Per_Image VALUES (1)")
    # Per_Experiment always has one row and must never count as a compartment.
    con.execute("CREATE TABLE Per_Experiment (note TEXT)")
    con.execute("INSERT INTO Per_Experiment VALUES ('x')")
    for name in compartments:
        con.execute(f"CREATE TABLE Per_{name} (ImageNumber INTEGER, ObjectNumber INTEGER)")
        for i in range(1, objects + 1):
            con.execute(f"INSERT INTO Per_{name} VALUES (1, ?)", (i,))
    con.commit()
    con.close()


def test_source_has_all_compartments_true(tmp_path):
    db = tmp_path / "chunk.sqlite"
    _make_cp_sqlite(db, objects=3)
    assert _source_has_all_compartments(db) is True


def test_source_has_all_compartments_false_when_one_empty(tmp_path):
    # Cells populated but cytoplasm empty: CytoTable would crash, so not convertible.
    db = tmp_path / "chunk.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE Per_Cells (ImageNumber INTEGER, ObjectNumber INTEGER)")
    con.execute("INSERT INTO Per_Cells VALUES (1, 1)")
    con.execute("CREATE TABLE Per_Nuclei (ImageNumber INTEGER, ObjectNumber INTEGER)")
    con.execute("INSERT INTO Per_Nuclei VALUES (1, 1)")
    con.execute("CREATE TABLE Per_Cytoplasm (ImageNumber INTEGER, ObjectNumber INTEGER)")
    con.commit()
    con.close()
    assert _source_has_all_compartments(db) is False


def test_source_has_all_compartments_false_when_table_missing(tmp_path):
    db = tmp_path / "chunk.sqlite"
    _make_cp_sqlite(db, objects=2, compartments=("Cells", "Nuclei"))  # no Per_Cytoplasm
    assert _source_has_all_compartments(db) is False


def test_convert_to_parquet_casts_features_to_float32(tmp_path, monkeypatch):
    # Single-cell features are written as float32 to halve downstream pandas memory
    # (notably pycytominer aggregate, which loads a plate's whole single-cell table).
    seen = {}
    monkeypatch.setattr(parquet, "convert", lambda **kwargs: seen.update(kwargs))

    parquet.convert_to_parquet(
        tmp_path / "src", tmp_path / "out.parquet", "deepprofiler", threads=1
    )

    assert seen["data_type_cast_map"] == {"float": "float32"}


def test_convert_to_parquet_cast_map_is_overridable(tmp_path, monkeypatch):
    # A caller-supplied cast map wins over the float32 default.
    seen = {}
    monkeypatch.setattr(parquet, "convert", lambda **kwargs: seen.update(kwargs))

    parquet.convert_to_parquet(
        tmp_path / "src",
        tmp_path / "out.parquet",
        "deepprofiler",
        data_type_cast_map={"integer": "int32"},
    )

    assert seen["data_type_cast_map"] == {"integer": "int32"}


def test_convert_to_parquet_cast_map_can_be_disabled(tmp_path, monkeypatch):
    # An explicit None must survive the setdefault, not be replaced by float32.
    seen = {}
    monkeypatch.setattr(parquet, "convert", lambda **kwargs: seen.update(kwargs))

    parquet.convert_to_parquet(
        tmp_path / "src",
        tmp_path / "out.parquet",
        "deepprofiler",
        data_type_cast_map=None,
    )

    assert seen["data_type_cast_map"] is None


def test_deepprofiler_to_parquet_disables_cast_map(tmp_path, monkeypatch):
    # .npz is non-tabular: CytoTable returns a [None] column sentinel for it, and
    # any non-None data_type_cast_map makes _prep_cast_column_data_types map the
    # cast over that sentinel and raise TypeError. Passing a cast map here is a
    # crash, not a preference.
    seen = {}

    def fake_convert_to_parquet(source_path, dest_path, preset, *, threads=2, **kwargs):
        seen.update(kwargs)
        Path(dest_path).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(parquet, "convert_to_parquet", fake_convert_to_parquet)
    monkeypatch.setattr(parquet, "concat_parquets", lambda *a, **k: None)

    parquet.deepprofiler_to_parquet(tmp_path / "src", tmp_path / "out.parquet")

    assert seen["data_type_cast_map"] is None


def test_cellprofiler_to_parquet_raises_without_sqlites(tmp_path):
    measurement = tmp_path / "measurement"
    measurement.mkdir()
    with pytest.raises(FileNotFoundError):
        cellprofiler_to_parquet(measurement, tmp_path / "out.parquet")


def test_cellprofiler_to_parquet_all_empty_writes_nothing(tmp_path, monkeypatch):
    measurement = tmp_path / "measurement"
    measurement.mkdir()
    _make_cp_sqlite(measurement / "26162.1.sqlite", objects=0)
    dest = tmp_path / "26162.parquet"

    def fail(*args, **kwargs):
        raise AssertionError("CytoTable must not run when every compartment is empty")

    monkeypatch.setattr(parquet, "convert_to_parquet", fail)

    result = cellprofiler_to_parquet(measurement, dest, threads=1)

    assert result.produced_output is False
    assert [p.name for p in result.skipped] == ["26162.1.sqlite"]
    assert not dest.exists()


def test_cellprofiler_to_parquet_all_populated_passes_source_dir(tmp_path, monkeypatch):
    measurement = tmp_path / "measurement"
    measurement.mkdir()
    _make_cp_sqlite(measurement / "plate.1.sqlite", objects=2)
    _make_cp_sqlite(measurement / "plate.2.sqlite", objects=5)
    dest = tmp_path / "out.parquet"
    seen = {}

    def fake_convert(source_path, dest_path, preset, *, threads=2, **kwargs):
        seen["source"] = Path(source_path)
        Path(dest_path).write_bytes(b"")

    monkeypatch.setattr(parquet, "convert_to_parquet", fake_convert)

    result = cellprofiler_to_parquet(measurement, dest, threads=1)

    # Nothing excluded: the original dir is handed straight to CytoTable.
    assert seen["source"] == measurement
    assert result.produced_output is True
    assert result.skipped == []


def test_cellprofiler_to_parquet_skips_empty_source(tmp_path, monkeypatch):
    measurement = tmp_path / "measurement"
    measurement.mkdir()
    _make_cp_sqlite(measurement / "plate.1.sqlite", objects=3)  # populated
    _make_cp_sqlite(measurement / "plate.2.sqlite", objects=0)  # empty well/site
    dest = tmp_path / "out.parquet"
    seen = {}

    def fake_convert(source_path, dest_path, preset, *, threads=2, **kwargs):
        seen["staged"] = sorted(p.name for p in Path(source_path).iterdir())
        Path(dest_path).write_bytes(b"")

    monkeypatch.setattr(parquet, "convert_to_parquet", fake_convert)

    result = cellprofiler_to_parquet(measurement, dest, threads=1)

    # Only the populated source is staged for CytoTable; the empty one is dropped.
    assert seen["staged"] == ["plate.1.sqlite"]
    assert [p.name for p in result.converted] == ["plate.1.sqlite"]
    assert [p.name for p in result.skipped] == ["plate.2.sqlite"]
    assert result.produced_output is True


def test_cellprofiler_joins_aliases_plate_and_well_to_canonical_names():
    # CytoTable's cellprofiler_sqlite preset selects Image_Metadata_Plate/Well; the join
    # override must alias them to the canonical Metadata_ names pycytominer expects.
    joins = parquet._cellprofiler_joins()
    assert "per_image.Image_Metadata_Well AS Metadata_Well," in joins
    assert "per_image.Image_Metadata_Plate AS Metadata_Plate," in joins
    # The un-aliased selections must be gone so the parquet never keeps the Image_ prefix.
    assert "per_image.Image_Metadata_Well," not in joins
    assert "per_image.Image_Metadata_Plate," not in joins


def test_cellprofiler_joins_raises_when_preset_stops_selecting_column(monkeypatch):
    import cytotable.presets

    stub = {"cellprofiler_sqlite": {"CONFIG_JOINS": "SELECT per_image.Metadata_ImageNumber"}}
    monkeypatch.setattr(cytotable.presets, "config", stub)
    with pytest.raises(RuntimeError, match="no longer selects"):
        parquet._cellprofiler_joins()
