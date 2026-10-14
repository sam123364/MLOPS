"""
Unit tests for KSNDMC dataset audit, anomaly detection, and flagged records.
"""

from pathlib import Path
import pandas as pd
import pytest


def test_ksndmc_flagged_records_csv_exists():
    p = Path("data/processed/ksndmc_flagged_records.csv")
    assert p.exists(), f"Flagged records CSV missing at {p}"
    df = pd.read_csv(p)
    assert len(df) > 0
    assert "issue_category" in df.columns
    assert "district_name" in df.columns


def test_kolar_2025_anomaly_flagged():
    p = Path("data/processed/ksndmc_flagged_records.csv")
    df = pd.read_csv(p)
    kolar_flags = df[(df["district_name"] == "Kolar") & (df["year"] == 2025)]
    assert len(kolar_flags) > 0, "Kolar 2025 anomaly must be recorded in flagged records"
    rec = kolar_flags.iloc[0]
    assert rec["issue_category"] == "COLUMN_SHIFT_ANOMALY"
    assert rec["severity"] == "CRITICAL"


def test_kolar_2025_seasonal_sum_discrepancy_detected():
    """Verify that Kolar 2025 raw values exhibit the reported discrepancy without modifying them."""
    fpath = Path("data/raw/ksndmc/ka_dist_rainfall_2025.csv")
    assert fpath.exists()
    df = pd.read_csv(fpath)
    kolar_row = df[df["District"].str.strip().str.upper() == "KOLAR"].iloc[0]

    annual_actual = float(kolar_row["Annual Actual"])
    swm_actual = float(kolar_row["SWM Actual"])
    pm_actual = float(kolar_row["Pre Monsoon Actual"])
    nem_actual = float(kolar_row["NEM Actual"])

    assert annual_actual == 927.0
    assert swm_actual == 2176.0

    seasonal_sum = pm_actual + swm_actual + nem_actual
    discrepancy = seasonal_sum - annual_actual

    # The discrepancy is massive (> 2000 mm) due to column shift
    assert discrepancy > 2000.0, f"Expected discrepancy > 2000 mm, got {discrepancy}"


def test_2021_hobli_data_seasonal_sums_consistent():
    """Verify that 2021 Hobli seasonal values consistently sum to annual totals."""
    fpath = Path("data/processed/rainfall/karnataka_hobli_rainfall_2021_clean.csv")
    assert fpath.exists()
    df = pd.read_csv(fpath)
    # Check that pre_monsoon + swm + nem == annual across all records within rounding tolerance
    sum_calc = df["pre_monsoon_actual_mm"] + df["swm_actual_mm"] + df["nem_actual_mm"]
    diff = (sum_calc - df["annual_actual_mm"]).abs()
    assert (diff <= 1.0).all(), "All 2021 Hobli rows must have seasonal sum equal to annual actual"


def test_2025_seasonal_vs_annual_discrepancy_counts():
    """Verify that independent mathematical calculation flags exactly 19 districts in 2025 with >10mm discrepancy."""
    fpath = Path("data/raw/ksndmc/ka_dist_rainfall_2025.csv")
    assert fpath.exists()
    df = pd.read_csv(fpath)
    
    # Filter to only individual district rows (exclude STATE total row)
    districts_df = df[df["District"].str.strip().str.upper() != "STATE"].copy()
    assert len(districts_df) == 31, f"Expected 31 individual districts, got {len(districts_df)}"
    
    # Calculate seasonal sum: Pre Monsoon + SWM + NEM
    calc_sum = districts_df["Pre Monsoon Actual"] + districts_df["SWM Actual"] + districts_df["NEM Actual"]
    discrepancy = (calc_sum - districts_df["Annual Actual"]).abs()
    
    # Exactly 19 districts have discrepancy > 10 mm
    flagged_districts = districts_df[discrepancy > 10.0]
    matched_districts = districts_df[discrepancy <= 10.0]
    
    assert len(flagged_districts) == 19, f"Expected 19 mismatched districts, got {len(flagged_districts)}"
    assert len(matched_districts) == 12, f"Expected 12 matched districts, got {len(matched_districts)}"


def test_flagged_records_reconciliation_total():
    """Verify that flagged records CSV contains exactly 22 entries: 19 shift + 1 unit mislabel + 1 missing year + 1 admin boundary change."""
    p = Path("data/processed/ksndmc_flagged_records.csv")
    df = pd.read_csv(p)
    assert len(df) == 22, f"Expected 22 flagged records, got {len(df)}"
    
    shift_flags = df[df["issue_category"] == "COLUMN_SHIFT_ANOMALY"]
    assert len(shift_flags) == 19, f"Expected 19 shift flags, got {len(shift_flags)}"
    
    unit_flags = df[df["issue_category"] == "HEADER_UNIT_MISLABEL"]
    assert len(unit_flags) == 1, f"Expected 1 unit mislabel flag, got {len(unit_flags)}"
    
    missing_flags = df[df["issue_category"] == "MISSING_YEAR_GAP"]
    assert len(missing_flags) == 1, f"Expected 1 missing year flag, got {len(missing_flags)}"
    
    boundary_flags = df[df["issue_category"] == "ADMINISTRATIVE_BOUNDARY_CHANGE"]
    assert len(boundary_flags) == 1, f"Expected 1 boundary change flag, got {len(boundary_flags)}"


def test_data_sources_md_documentation():
    p = Path("docs/data_sources.md")
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "IMD Gridded Historical Rainfall" in content
    assert "KSNDMC Karnataka Rainfall Records" in content
    assert "Column Shift Anomaly" in content
    assert "Proposed Future Sources (Not Yet Acquired / Not Ingested)" in content

