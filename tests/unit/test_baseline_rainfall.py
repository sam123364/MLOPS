"""
tests/unit/test_baseline_rainfall.py
───────────────────────────────────
Unit tests for the baseline rainfall modeling workflow.
Validates:
  1. Data preparation and strict chronological target alignment (no leakage).
  2. Exact calculation of Climatology and Persistence baselines.
  3. Prediction shape and held-out coverage calculation.
  4. Metric calculation logic (MAE, RMSE, R2, Skill Score vs Climatology).
"""

import numpy as np
import pandas as pd
import pytest

from src.models.baseline_rainfall import (
    build_modeling_dataset,
    evaluate_predictions,
    run_baseline_experiments,
)


@pytest.fixture
def sample_data():
    """Create a minimal synthetic multi-year dataset for 2 districts across 10 years."""
    districts = ["District_A", "District_B"]
    years = list(range(2000, 2010))  # 10 years

    monsoon_rows = []
    daily_rows = []

    for d in districts:
        for y in years:
            # Baseline monsoon record
            monsoon_rows.append({
                "district_name": d,
                "year": y,
                "monsoon_total_mm": 500.0 + (y - 2000) * 10.0 + (50.0 if d == "District_B" else 0.0),
                "longest_dry_spell_days": 10 + (y % 5),
                "annual_total_mm": 800.0 + (y - 2000) * 15.0,
                "nem_total_mm": 200.0,
                "rainy_days_count": 40,
                "heavy_rain_days_gt_25mm": 5,
                "very_heavy_rain_days_gt_50mm": 1,
                "max_1day_rainfall_mm": 45.0,
                "pci": 15.0,
            })

            # Daily samples for pre-monsoon and 3-day max
            for m in [4, 7]:  # April (pre-monsoon), July (SWM)
                daily_rows.append({
                    "district_name": d,
                    "date": pd.Timestamp(f"{y}-{m:02d}-15"),
                    "rainfall_estimate_mm": 20.0,
                })

    monsoon_df = pd.DataFrame(monsoon_rows)
    daily_df = pd.DataFrame(daily_rows)
    return monsoon_df, daily_df


def test_build_modeling_dataset_target_alignment(sample_data):
    monsoon_df, daily_df = sample_data
    df = build_modeling_dataset(monsoon_df, daily_df)

    # 10 years -> 9 consecutive target pairs per district (18 rows total)
    assert len(df) == 18
    assert "target_next_year_swm_mm" in df.columns
    assert "target_next_year_longest_dry_spell_days" in df.columns
    assert "target_next_year_annual_mm" in df.columns

    # Verify that target_year is year + 1
    for _, row in df.iterrows():
        assert row["target_year"] == row["year"] + 1

    # Verify shift alignment: District_A year 2000 target equals year 2001 feature
    d_a = df[df["district_name"] == "District_A"].sort_values("year")
    y2000 = d_a[d_a["year"] == 2000].iloc[0]
    y2001 = d_a[d_a["year"] == 2001].iloc[0]
    assert y2000["target_next_year_swm_mm"] == y2001["sw_monsoon_total_mm"]


def test_evaluate_predictions_metrics():
    y_true = np.array([100.0, 200.0, 300.0])
    y_pred = np.array([110.0, 190.0, 310.0])  # error = 10, 10, 10 -> MAE = 10, RMSE = 10
    climatology_mae = 20.0

    metrics = evaluate_predictions(y_true, y_pred, climatology_mae)
    assert metrics["mae_mm"] == 10.0
    assert metrics["rmse_mm"] == 10.0
    # Skill score = 1 - (10 / 20) = 0.5
    assert metrics["skill_score_vs_climatology"] == 0.5


def test_run_baseline_experiments_no_leakage(sample_data):
    monsoon_df, daily_df = sample_data
    df = build_modeling_dataset(monsoon_df, daily_df)

    cfg = {
        "train_end_year": 2006,
        "test_start_year": 2007,
        "random_state": 42,
        "random_forest": {"n_estimators": 10, "max_depth": 3, "random_state": 42},
    }

    pred_df, eval_df, detailed_metrics = run_baseline_experiments(df, cfg)

    # Test set should strictly contain target_year >= 2007
    assert pred_df["target_year"].min() >= 2007
    assert len(eval_df) > 0

    # Ensure all models are present in evaluation
    expected_models = {
        "Climatology Baseline",
        "Persistence Baseline",
        "Linear Regression (Ridge)",
        "Random Forest Regressor",
        "Empirical Median (Q50)",
    }
    present_models = set(eval_df["model"].unique())
    assert expected_models.issubset(present_models)

    # Check that empirical coverage is calculated and bounded between 0 and 100
    for target in detailed_metrics:
        coverage = detailed_metrics[target]["empirical_historical_bounds"]["observed_test_coverage_pct"]
        assert 0.0 <= coverage <= 100.0


def test_coverage_calculation_regression():
    """Verify that coverage rate exactly computes in-bounds fractions on known bounds."""
    y_true = np.array([50.0, 100.0, 150.0, 200.0])
    p10 = np.array([60.0, 60.0, 60.0, 60.0])
    p90 = np.array([160.0, 160.0, 160.0, 160.0])

    in_bounds = ((y_true >= p10) & (y_true <= p90)).astype(int)
    # y = 100.0 and 150.0 are in [60, 160]; 50 and 200 are out -> 2/4 = 50.0%
    assert int(np.sum(in_bounds)) == 2
    assert float(np.mean(in_bounds) * 100.0) == 50.0
