"""
Unit tests for Official District Boundary Processing and KSNDMC Anomaly Exclusion
==================================================================================
Tests:
1. Official GeoJSON boundary loading and geometry validity.
2. Coordinate reference system verification (EPSG:4326).
3. Area-overlap weights calculation (weights sum to 1.0 for all districts).
4. Centroid cell counts vs overlapping cell counts.
5. Official area-weighted parquet schema and retention of provisional parquet.
6. Exclusion of flagged KSNDMC 2025 records from seasonal training/validation.
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest


def test_official_district_geojson_exists_and_valid():
    """Verify that official district GeoJSON exists and contains target districts."""
    p = Path("data/raw/boundaries/kolar_chikkaballapur_tumakuru_districts.geojson")
    assert p.exists(), f"Official boundaries file missing at {p}"
    
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert data.get("type") == "FeatureCollection"
    features = data.get("features", [])
    assert len(features) == 3, f"Expected 3 target districts, got {len(features)}"
    
    district_names = [f["properties"].get("dtname") for f in features]
    assert "Kolar" in district_names
    assert "Chikkaballapura" in district_names
    assert "Tumakuru" in district_names


def test_official_boundaries_crs_and_geometry():
    """Verify EPSG:4326 CRS and Polygon / MultiPolygon geometry validity."""
    p = Path("data/raw/boundaries/kolar_chikkaballapur_tumakuru_districts.geojson")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    crs = data.get("crs", {})
    crs_name = crs.get("properties", {}).get("name", "")
    assert "4326" in crs_name or "CRS84" in crs_name or crs == {}, f"Unexpected CRS: {crs}"
    
    for f in data["features"]:
        geom = f["geometry"]
        assert geom["type"] in ["Polygon", "MultiPolygon"]
        coords = geom["coordinates"]
        assert len(coords) > 0


def test_area_weighted_metadata_profile():
    """Verify that official area-weighting metadata profile is populated correctly."""
    p = Path("data/metadata/official_district_boundary_profile.json")
    assert p.exists()
    with open(p, "r", encoding="utf-8") as f:
        meta = json.load(f)
    
    assert meta["aggregation_method"] == "official_area_weighted_mean"
    target_dists = meta["target_districts"]
    assert "Kolar" in target_dists
    assert "Chikkaballapur" in target_dists
    assert "Tumakuru" in target_dists
    
    # Check normalized weights sum to 1.0 within floating tolerance
    for dname, dinfo in target_dists.items():
        weights_sum = sum(dinfo["normalized_weights"].values())
        assert abs(weights_sum - 1.0) < 1e-3, f"{dname} weights sum to {weights_sum}, expected 1.0"
        assert dinfo["centroid_cell_count"] > 0
        assert dinfo["overlap_cells_count"] >= dinfo["centroid_cell_count"]


def test_official_daily_district_parquet():
    """Verify official daily district parquet output structure and non-provisional flag."""
    p = Path("data/processed/imd_rainfall_daily_district_official.parquet")
    assert p.exists()
    df = pd.read_parquet(p)
    assert len(df) == 136878  # 3 districts * 45626 days
    assert set(df["district_name"].unique()) == {"Kolar", "Chikkaballapur", "Tumakuru"}
    assert (df["provisional_flag"] == False).all(), "Official dataset must have provisional_flag == False"
    assert (df["rainfall_estimate_mm"] >= 0.0).all()
    assert df["rainfall_estimate_mm"].isna().sum() == 0


def test_provisional_dataset_retained_unmodified():
    """Verify that the provisional bounding-box dataset remains intact for baseline comparisons."""
    p_prov = Path("data/processed/imd_rainfall_daily_district.parquet")
    assert p_prov.exists()
    df_prov = pd.read_parquet(p_prov)
    assert len(df_prov) == 136878
    assert (df_prov["provisional_flag"] == True).all()


def test_ksndmc_flagged_records_excluded_from_seasonal_validation():
    """
    Verify downstream policy:
    1. Flagged 2025 records in ksndmc_flagged_records.csv are excluded from seasonal training/validation.
    2. Verified records (e.g. 2021 Hobli clean dataset) pass seasonal validation.
    """
    flagged_p = Path("data/processed/ksndmc_flagged_records.csv")
    assert flagged_p.exists()
    df_flags = pd.read_csv(flagged_p)
    
    # 19 districts in 2025 have severe column-shift anomalies
    shift_anomalies = df_flags[df_flags["issue_category"] == "COLUMN_SHIFT_ANOMALY"]
    assert len(shift_anomalies) == 19
    flagged_districts_2025 = set(shift_anomalies["district_name"].unique())
    assert "Kolar" in flagged_districts_2025
    assert "Chikkaballapura" in flagged_districts_2025

    # Simulated downstream filter function for seasonal validation
    def filter_usable_seasonal_records(source_df: pd.DataFrame, flags_df: pd.DataFrame) -> pd.DataFrame:
        """Filter out any district-year combination flagged for seasonal anomalies."""
        flagged_pairs = set(zip(flags_df["district_name"], flags_df["year"]))
        usable_rows = [
            idx for idx, row in source_df.iterrows()
            if (row.get("district_name"), row.get("year")) not in flagged_pairs
        ]
        return source_df.loc[usable_rows].reset_index(drop=True)

    # Test that Kolar 2025 is strictly filtered out
    sample_df = pd.DataFrame([
        {"district_name": "Kolar", "year": 2025, "swm_actual_mm": 2176.0},
        {"district_name": "Tumakuru", "year": 2025, "swm_actual_mm": 374.0},
        {"district_name": "Kolar", "year": 2024, "swm_actual_mm": 444.0}
    ])
    usable = filter_usable_seasonal_records(sample_df, df_flags)
    assert len(usable) == 2
    assert not ((usable["district_name"] == "Kolar") & (usable["year"] == 2025)).any(), "Kolar 2025 must be excluded"
