"""
Unit tests for KSNDMC / Karnataka rainfall data schemas and validation.
"""

import pytest
from pathlib import Path
import pandas as pd
from src.utils.schemas import validate_dataframe, load_schemas

@pytest.fixture
def schemas():
    return load_schemas()

def test_schemas_yaml_loaded(schemas):
    assert "district_annual_long_schema" in schemas
    assert "district_annual_wide_schema" in schemas
    assert "district_seasonal_schema" in schemas
    assert "hobli_rainfall_schema" in schemas

def test_district_annual_long_validation():
    fpath = Path("data/processed/rainfall/karnataka_district_annual_rainfall_2021_2025_long.csv")
    assert fpath.exists(), f"File {fpath} does not exist"
    df = pd.read_csv(fpath)
    is_valid, errors = validate_dataframe(df, "district_annual_long_schema")
    assert is_valid, f"Validation failed with errors: {errors}"
    assert len(df) > 0
    assert set(df["year"].unique()).issubset({2021, 2022, 2024, 2025})

def test_district_annual_wide_validation():
    fpath = Path("data/processed/rainfall/karnataka_district_annual_rainfall_comparison_wide.csv")
    assert fpath.exists(), f"File {fpath} does not exist"
    df = pd.read_csv(fpath)
    is_valid, errors = validate_dataframe(df, "district_annual_wide_schema")
    assert is_valid, f"Validation failed with errors: {errors}"
    assert "normal_rainfall_mm" in df.columns
    assert "actual_rainfall_mm_2022" in df.columns

def test_district_seasonal_validation():
    fpath = Path("data/processed/rainfall/karnataka_district_seasonal_rainfall_2021_2025.csv")
    assert fpath.exists(), f"File {fpath} does not exist"
    df = pd.read_csv(fpath)
    is_valid, errors = validate_dataframe(df, "district_seasonal_schema")
    assert is_valid, f"Validation failed with errors: {errors}"
    assert "swm_actual_mm" in df.columns
    assert "nem_actual_mm" in df.columns

def test_hobli_clean_validation_2021():
    fpath = Path("data/processed/rainfall/karnataka_hobli_rainfall_2021_clean.csv")
    assert fpath.exists(), f"File {fpath} does not exist"
    df = pd.read_csv(fpath)
    is_valid, errors = validate_dataframe(df, "hobli_rainfall_schema")
    assert is_valid, f"Validation failed with errors: {errors}"
    # Verify forward-filled hierarchy
    hobli_rows = df[df["admin_level"] == "HOBLI"]
    assert hobli_rows["district_name"].notna().all(), "Hobli rows must have forward-filled district_name"
    assert hobli_rows["taluk_name"].notna().all(), "Hobli rows must have forward-filled taluk_name"

def test_hobli_clean_validation_2024():
    fpath = Path("data/processed/rainfall/karnataka_hobli_rainfall_2024_clean.csv")
    assert fpath.exists(), f"File {fpath} does not exist"
    df = pd.read_csv(fpath)
    is_valid, errors = validate_dataframe(df, "hobli_rainfall_schema")
    assert is_valid, f"Validation failed with errors: {errors}"
