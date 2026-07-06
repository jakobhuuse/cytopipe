"""
Tests for cytopipe.bridge.source.
Plate-map loading and joining onto the index.
 """

import pandas as pd
import pytest

from cytopipe.bridge.source import resolve_measurement, resolve_plate


def test_resolve_plate_from_image_table_metadata():
    table = pd.DataFrame({"Metadata_Plate": ["26159", "26159"]})
    assert resolve_plate(table, measurement=None) == "26159"


def test_resolve_plate_multiple_plates_errors():
    table = pd.DataFrame({"Metadata_Plate": ["26159", "26160"]})
    with pytest.raises(ValueError, match="multiple plates"):
        resolve_plate(table, measurement=None)


def test_resolve_plate_falls_back_to_dir_name(tmp_path):
    measurement = tmp_path / "26159" / "measurement"
    measurement.mkdir(parents=True)
    table = pd.DataFrame({"Metadata_Well": ["A02"]})  # no Metadata_Plate column
    assert resolve_plate(table, measurement) == "26159"


def test_resolve_measurement_rejects_non_measurement_dir(tmp_path):
    with pytest.raises(FileNotFoundError, match="measurement"):
        resolve_measurement(tmp_path)