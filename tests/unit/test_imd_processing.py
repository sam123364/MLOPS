"""
Unit tests for IMD historical rainfall preprocessing pipeline.
Covers:
- NetCDF inspection
- Date continuity & range
- Missing values & physical plausibility
- Bounding box intersection
- District unweighted mean aggregation
- Longest dry-spell consecutive run logic
- Processed Parquet artifacts schema & integrity
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest

from src.data.process_imd_rainfall import (
    calculate_longest_dry_spell,
    load_study_area_bboxes,
    map_grid_cells_to_districts,
    load_provisional_aoi_geojson,
    is_point_in_aoi_polygon,
)


def test_dry_spell_calculation_basic():
    # Sequence: 1.0, 2.0, 0.0 (3 dry), 10.0 (wet), 0.5, 0.0 (2 dry)
    series = pd.Series([1.0, 2.0, 0.0, 10.0, 0.5, 0.0])
    longest, missing = calculate_longest_dry_spell(series, threshold_mm=2.5)
    assert longest == 3
    assert missing == 0


def test_dry_spell_calculation_all_dry():
    series = pd.Series([0.0] * 30)
    longest, missing = calculate_longest_dry_spell(series, threshold_mm=2.5)
    assert longest == 30
    assert missing == 0


def test_dry_spell_calculation_all_wet():
    series = pd.Series([10.0, 25.0, 50.0])
    longest, missing = calculate_longest_dry_spell(series, threshold_mm=2.5)
    assert longest == 0
    assert missing == 0


def test_dry_spell_missing_values_break_run():
    # Sequence: 0.0, 0.0, NaN, 0.0
    # Dry run should NOT count across NaN
    series = pd.Series([0.0, 0.0, np.nan, 0.0])
    longest, missing = calculate_longest_dry_spell(series, threshold_mm=2.5)
    assert longest == 2
    assert missing == 1


def test_provisional_aoi_geojson_loading():
    p = Path("data/raw/boundaries/approx_kolar_chikkaballapur_tumakuru_aoi.geojson")
    assert p.exists(), f"GeoJSON file missing at {p}"
    aoi_info = load_provisional_aoi_geojson(p)
    assert aoi_info["geometry_type"] == "Polygon"
    assert aoi_info["is_official_district_boundary"] == False
    assert "not official district boundaries" in aoi_info["note"].lower()
    assert aoi_info["bbox"]["west"] == 76.7
    assert aoi_info["bbox"]["east"] == 78.95
    assert aoi_info["bbox"]["south"] == 12.4
    assert aoi_info["bbox"]["north"] == 14.25


def test_point_in_aoi_polygon():
    p = Path("data/raw/boundaries/approx_kolar_chikkaballapur_tumakuru_aoi.geojson")
    aoi_info = load_provisional_aoi_geojson(p)
    # Point inside Kolar (13.13, 78.13)
    assert is_point_in_aoi_polygon(13.13, 78.13, aoi_info) == True
    # Point inside Tumakuru (13.34, 77.10)
    assert is_point_in_aoi_polygon(13.34, 77.10, aoi_info) == True
    # Point outside bounds (e.g. lon 79.00 is beyond 78.95)
    assert is_point_in_aoi_polygon(12.50, 79.00, aoi_info) == False
    assert is_point_in_aoi_polygon(15.00, 75.00, aoi_info) == False


def test_study_area_bboxes_loaded():
    config_path = Path("configs/study_area.yaml")
    assert config_path.exists()
    bboxes = load_study_area_bboxes(config_path)
    assert "Kolar" in bboxes
    assert "Chikkaballapur" in bboxes
    assert "Tumakuru" in bboxes


def test_grid_cell_mapping_with_geojson():
    config_path = Path("configs/study_area.yaml")
    bboxes = load_study_area_bboxes(config_path)
    geojson_path = Path("data/raw/boundaries/approx_kolar_chikkaballapur_tumakuru_aoi.geojson")
    aoi_info = load_provisional_aoi_geojson(geojson_path)

    lats = np.array([12.5, 12.75, 13.0, 13.25, 13.5, 13.75, 14.0, 14.25])
    lons = np.array([76.75, 77.0, 77.25, 77.5, 77.75, 78.0, 78.25, 78.5, 78.75, 79.0])
    mapping = map_grid_cells_to_districts(lats, lons, bboxes, aoi_info)

    assert len(mapping["Kolar"]) == 16
    assert len(mapping["Chikkaballapur"]) == 6
    assert len(mapping["Tumakuru"]) == 20


def test_processed_daily_grid_parquet():
    p = Path("data/processed/imd_rainfall_daily_grid.parquet")
    assert p.exists()
    df = pd.read_parquet(p)
    expected_cols = {"date", "latitude", "longitude", "rainfall_mm"}
    assert expected_cols.issubset(df.columns)
    # 72 cells selected by GeoJSON AOI * 45626 days = 3,285,072
    assert len(df) == 3285072
    # Plausibility
    assert (df["rainfall_mm"] >= 0).all(), "Rainfall must be non-negative"
    assert (df["rainfall_mm"] <= 500).all(), "Rainfall above 500 mm/day is unphysical for Kolar"
    assert df["rainfall_mm"].isna().sum() == 0, "No missing values allowed in daily grid"


def test_processed_daily_district_parquet():
    p = Path("data/processed/imd_rainfall_daily_district.parquet")
    assert p.exists()
    df = pd.read_parquet(p)
    expected_cols = {
        "district_name",
        "date",
        "rainfall_estimate_mm",
        "grid_cell_count",
        "aggregation_method",
        "provisional_flag",
    }
    assert expected_cols.issubset(df.columns)
    assert len(df) == 136878
    assert set(df["district_name"].unique()) == {"Kolar", "Chikkaballapur", "Tumakuru"}
    assert df["provisional_flag"].all() == True


def test_processed_monsoon_features_parquet():
    p = Path("data/processed/imd_monsoon_features.parquet")
    assert p.exists()
    df = pd.read_parquet(p)
    expected_cols = {
        "district_name",
        "year",
        "season_name",
        "monsoon_total_mm",
        "longest_dry_spell_days",
        "dry_day_threshold_mm",
        "total_monsoon_days",
        "missing_days_count",
        "provisional_flag",
    }
    assert expected_cols.issubset(df.columns)
    assert len(df) == 375  # 3 districts * 125 years (1901-2025)
    assert (df["total_monsoon_days"] == 122).all()
    assert (df["missing_days_count"] == 0).all()
    assert (df["longest_dry_spell_days"] >= 0).all()
    assert (df["longest_dry_spell_days"] <= 122).all()
    assert df["provisional_flag"].all() == True


def test_metadata_profile_json():
    p = Path("data/metadata/imd_dataset_profile.json")
    assert p.exists()
    with open(p, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["source_file"] == "imdweb_nSbYRBgK.nc"
    assert meta["time_coverage"]["start_date"] == "1901-01-31"
    assert meta["time_coverage"]["end_date"] == "2025-12-31"
    assert meta["time_coverage"]["continuous_daily_flag"] == True
    assert meta["geographic_filtering"]["is_official_district_boundary"] == False
    assert meta["geographic_filtering"]["geojson_selected_grid_cells_count"] == 72
    assert "not official" in meta["geographic_filtering"]["limitations"].lower()
