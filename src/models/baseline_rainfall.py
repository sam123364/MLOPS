"""
src/models/baseline_rainfall.py
───────────────────────────────
Reproducible baseline rainfall and dry-spell forecasting models for Kolar,
Chikkaballapur, and Tumakuru, Karnataka.

Evaluates:
  1. Climatology Baseline (historical expanding training mean per district)
  2. Persistence Baseline (last year's observed value)
  3. Linear Regression (lagged seasonal and hydrological features)
  4. Random Forest Regressor (comparison model fitted on training features)
  5. Empirical Quantiles (10th, 50th, 90th percentiles for held-out coverage)

Targets:
  - Primary (CLAUDE.md):
      * target_next_year_swm_mm (Southwest monsoon total rainfall in mm)
      * target_next_year_longest_dry_spell_days (max consecutive dry days < 2.5 mm in SWM)
  - Secondary (Teammate comparison):
      * target_next_year_annual_mm (Annual total rainfall in mm)

Validation:
  Strict chronological split:
    Train: Target years <= 2019 (1902 to 2019)
    Test:  Target years >= 2020 (2020 to 2025; n = 18 held-out instances)
    No future-data leakage; all scalers and encoders fitted on train only.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def build_modeling_dataset(
    monsoon_df: pd.DataFrame,
    daily_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construct district-year modeling table with lagged features and targets.
    Ensures that for target year t+1, only observations up to year t are used.
    """
    # 1. Ensure date and types
    daily = daily_df.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily["year"] = daily["date"].dt.year
    daily["month"] = daily["date"].dt.month

    # Pre-monsoon total (March-May) per district-year
    pre_monsoon = (
        daily[daily["month"].isin([3, 4, 5])]
        .groupby(["district_name", "year"])["rainfall_estimate_mm"]
        .sum()
        .reset_index()
        .rename(columns={"rainfall_estimate_mm": "pre_monsoon_total_mm"})
    )

    # 3-day max during SWM per district-year
    swm_daily = daily[daily["month"].isin([6, 7, 8, 9])].copy()
    swm_daily = swm_daily.sort_values(["district_name", "date"]).reset_index(drop=True)
    swm_daily["rolling_3day"] = (
        swm_daily.groupby(["district_name", "year"])["rainfall_estimate_mm"]
        .rolling(3, min_periods=1)
        .sum()
        .reset_index(drop=True)
    )
    swm_max_3day = (
        swm_daily.groupby(["district_name", "year"])["rolling_3day"]
        .max()
        .reset_index()
        .rename(columns={"rolling_3day": "swm_max_3day_rainfall_mm"})
    )

    # Base table from monsoon features
    df = monsoon_df.copy()
    # Merge pre-monsoon and swm_max_3day
    df = df.merge(pre_monsoon, on=["district_name", "year"], how="left")
    if "swm_max_3day_rainfall_mm" not in df.columns:
        df = df.merge(swm_max_3day, on=["district_name", "year"], how="left")

    df = df.sort_values(["district_name", "year"]).reset_index(drop=True)

    # Standardize column names
    if "monsoon_total_mm" in df.columns and "sw_monsoon_total_mm" not in df.columns:
        df["sw_monsoon_total_mm"] = df["monsoon_total_mm"]

    # Create next-year targets strictly by shifting -1 within each district
    df["target_year"] = df.groupby("district_name")["year"].shift(-1)
    df["target_next_year_swm_mm"] = df.groupby("district_name")["sw_monsoon_total_mm"].shift(-1)
    df["target_next_year_longest_dry_spell_days"] = df.groupby("district_name")["longest_dry_spell_days"].shift(-1)
    df["target_next_year_annual_mm"] = df.groupby("district_name")["annual_total_mm"].shift(-1)

    # Drop the final year where future target is unknown
    df_clean = df.dropna(
        subset=[
            "target_year",
            "target_next_year_swm_mm",
            "target_next_year_longest_dry_spell_days",
            "target_next_year_annual_mm",
        ]
    ).copy()
    df_clean["target_year"] = df_clean["target_year"].astype(int)

    return df_clean


def evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    climatology_mae: float,
) -> Dict[str, float]:
    """Compute MAE, RMSE, R2, and Skill Score vs Climatology."""
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))

    # Handle R2 edge case for small sample sizes
    if len(y_true) < 2 or np.var(y_true) == 0:
        r2 = float("nan")
    else:
        r2 = float(r2_score(y_true, y_pred))

    # Skill Score relative to Climatology MAE
    if climatology_mae > 0:
        skill_score = float(1.0 - (mae / climatology_mae))
    else:
        skill_score = 0.0

    return {
        "mae_mm": round(mae, 3),
        "rmse_mm": round(rmse, 3),
        "r2": round(r2, 4),
        "skill_score_vs_climatology": round(skill_score, 4),
    }


def run_baseline_experiments(
    df: pd.DataFrame,
    cfg: Dict[str, Any],
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Train and evaluate baselines across primary and secondary targets.
    """
    train_end = cfg.get("train_end_year", 2019)
    test_start = cfg.get("test_start_year", 2020)
    rf_params = cfg.get("random_forest", {"n_estimators": 100, "max_depth": 6, "random_state": 42})
    random_state = cfg.get("random_state", 42)

    # Chronological Split
    train_df = df[df["target_year"] <= train_end].copy()
    test_df = df[df["target_year"] >= test_start].copy()

    logger.info("Train instances: %d (target years %d to %d)", len(train_df), train_df["target_year"].min(), train_df["target_year"].max())
    logger.info("Test instances:  %d (target years %d to %d)", len(test_df), test_df["target_year"].min(), test_df["target_year"].max())

    feature_cols = [
        "district_name",
        "sw_monsoon_total_mm",
        "longest_dry_spell_days",
        "annual_total_mm",
        "nem_total_mm",
        "pre_monsoon_total_mm",
        "rainy_days_count",
        "heavy_rain_days_gt_25mm",
        "very_heavy_rain_days_gt_50mm",
        "max_1day_rainfall_mm",
        "pci",
    ]
    # Ensure available columns
    available_features = [c for c in feature_cols if c in df.columns]
    num_features = [c for c in available_features if c != "district_name"]

    targets = [
        ("target_next_year_swm_mm", "sw_monsoon_total_mm", "Primary: Next-Year SWM (mm)"),
        ("target_next_year_longest_dry_spell_days", "longest_dry_spell_days", "Primary: Next-Year Longest Dry Spell (days)"),
        ("target_next_year_annual_mm", "annual_total_mm", "Secondary: Next-Year Annual Rainfall (mm)"),
    ]

    all_predictions_rows = []
    eval_summary_rows = []
    detailed_metrics = {}

    for target_col, current_col, target_label in targets:
        logger.info("Evaluating target: %s", target_label)
        y_train = train_df[target_col].values
        y_test = test_df[target_col].values

        # 1. Climatology Baseline (Training Mean per district)
        district_means = train_df.groupby("district_name")[target_col].mean().to_dict()
        pred_climatology = test_df["district_name"].map(district_means).values

        # Climatology MAE for skill score
        clim_mae = mean_absolute_error(y_test, pred_climatology)

        # 2. Persistence Baseline (Current Year's Observed Value)
        pred_persistence = test_df[current_col].values

        # 3. Linear Regression (Ridge regularized to prevent overfitting on small feature set)
        preprocessor = ColumnTransformer(
            transformers=[
                ("cat", OneHotEncoder(handle_unknown="ignore", drop="first"), ["district_name"]),
                ("num", StandardScaler(), num_features),
            ]
        )
        linear_pipe = Pipeline([
            ("prep", preprocessor),
            ("model", Ridge(alpha=1.0, random_state=random_state)),
        ])
        linear_pipe.fit(train_df[available_features], y_train)
        pred_linear = linear_pipe.predict(test_df[available_features])

        # 4. Random Forest Regressor
        rf_pipe = Pipeline([
            ("prep", preprocessor),
            ("model", RandomForestRegressor(
                n_estimators=rf_params.get("n_estimators", 100),
                max_depth=rf_params.get("max_depth", 6),
                min_samples_leaf=rf_params.get("min_samples_leaf", 3),
                random_state=rf_params.get("random_state", random_state),
            )),
        ])
        rf_pipe.fit(train_df[available_features], y_train)
        pred_rf = rf_pipe.predict(test_df[available_features])

        # 5. Empirical Quantiles (10th, 50th, 90th percentile from training distribution per district)
        p10_map = train_df.groupby("district_name")[target_col].quantile(0.10).to_dict()
        p50_map = train_df.groupby("district_name")[target_col].quantile(0.50).to_dict()
        p90_map = train_df.groupby("district_name")[target_col].quantile(0.90).to_dict()

        pred_p10 = test_df["district_name"].map(p10_map).values
        pred_p50 = test_df["district_name"].map(p50_map).values
        pred_p90 = test_df["district_name"].map(p90_map).values

        # Calculate interval coverage on test set
        in_interval = ((y_test >= pred_p10) & (y_test <= pred_p90)).astype(int)
        coverage_80pct = float(np.mean(in_interval) * 100.0)

        # Record test predictions row-by-row
        for idx in range(len(test_df)):
            row = test_df.iloc[idx]
            all_predictions_rows.append({
                "district_name": row["district_name"],
                "target_year": int(row["target_year"]),
                "target_name": target_col,
                "actual_value": round(float(y_test[idx]), 2),
                "pred_climatology": round(float(pred_climatology[idx]), 2),
                "pred_persistence": round(float(pred_persistence[idx]), 2),
                "pred_linear": round(float(pred_linear[idx]), 2),
                "pred_random_forest": round(float(pred_rf[idx]), 2),
                "pred_quantile_10": round(float(pred_p10[idx]), 2),
                "pred_quantile_50": round(float(pred_p50[idx]), 2),
                "pred_quantile_90": round(float(pred_p90[idx]), 2),
            })

        # Calculate metrics for each model
        models_dict = {
            "Climatology Baseline": pred_climatology,
            "Persistence Baseline": pred_persistence,
            "Linear Regression (Ridge)": pred_linear,
            "Random Forest Regressor": pred_rf,
            "Empirical Median (Q50)": pred_p50,
        }

        detailed_metrics[target_col] = {
            "target_label": target_label,
            "evaluation_note": (
                "Evaluated on held-out test years 2020-2025 (n = 18 district-year observations). "
                "Feature year 1901 has incomplete January coverage (Jan 1-30 missing in raw IMD) but does not contaminate test years."
            ),
            "test_sample_size": len(y_test),
            "train_sample_size": len(y_train),
            "empirical_historical_bounds": {
                "description": "Observed coverage of held-out test observations falling within historical 10th-90th percentiles. Not calibrated prediction intervals.",
                "nominal_percentile_range": "10th - 90th percentile (80% nominal)",
                "observed_test_in_bounds_count": int(np.sum(in_interval)),
                "observed_test_coverage_pct": round(coverage_80pct, 2),
            },
            "models": {},
        }

        for m_name, preds in models_dict.items():
            metrics = evaluate_predictions(y_test, preds, clim_mae)
            detailed_metrics[target_col]["models"][m_name] = metrics
            eval_summary_rows.append({
                "target": target_col,
                "target_label": target_label,
                "model": m_name,
                "mae": metrics["mae_mm"],
                "rmse": metrics["rmse_mm"],
                "r2": metrics["r2"],
                "skill_score_vs_climatology": metrics["skill_score_vs_climatology"],
            })

    pred_df = pd.DataFrame(all_predictions_rows)
    eval_df = pd.DataFrame(eval_summary_rows)

    return pred_df, eval_df, detailed_metrics


def main():
    parser = argparse.ArgumentParser(description="Baseline Rainfall and Dry-Spell Forecasting")
    parser.add_argument("--monsoon-data", type=Path, default=Path("data/processed/imd_monsoon_features_official.parquet"))
    parser.add_argument("--daily-data", type=Path, default=Path("data/processed/imd_rainfall_daily_district_official.parquet"))
    parser.add_argument("--config", type=Path, default=Path("configs/params.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    args = parser.parse_args()

    # Load configuration
    cfg = {}
    if args.config.exists():
        with open(args.config, "r", encoding="utf-8") as f:
            full_cfg = yaml.safe_load(f) or {}
            cfg = full_cfg.get("rainfall_baseline", {})

    logger.info("Loading inputs: %s and %s", args.monsoon_data, args.daily_data)
    monsoon_df = pd.read_parquet(args.monsoon_data)
    daily_df = pd.read_parquet(args.daily_data)

    df_model = build_modeling_dataset(monsoon_df, daily_df)

    pred_df, eval_df, detailed_metrics = run_baseline_experiments(df_model, cfg)

    # Save outputs
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.reports_dir.mkdir(parents=True, exist_ok=True)

    pred_path = args.output_dir / "rainfall_baseline_predictions.csv"
    eval_path = args.reports_dir / "rainfall_baseline_evaluation.csv"
    metrics_path = args.reports_dir / "rainfall_baseline_metrics.json"

    pred_df.to_csv(pred_path, index=False)
    eval_df.to_csv(eval_path, index=False)
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(detailed_metrics, f, indent=2)

    logger.info("Saved predictions to: %s", pred_path)
    logger.info("Saved evaluation summary to: %s", eval_path)
    logger.info("Saved detailed metrics to: %s", metrics_path)
    print("\n=== MODEL EVALUATION SUMMARY ===")
    print(eval_df.to_string(index=False))


if __name__ == "__main__":
    main()
