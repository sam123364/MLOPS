"""
models/evaluate.py
───────────────────
Load a trained model and evaluate it on the test set.
Optionally generate a suitability map for rainwater harvesting locations.

Prerequisites:
    pip install scikit-learn mlflow pandas numpy joblib rasterio matplotlib

Usage (CLI):
    python -m src.models.evaluate --features data/processed/features.csv --model data/processed/models/random_forest_model.joblib
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

import joblib
import mlflow
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import LabelEncoder

from src.utils.config import load_config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def evaluate_model(
    features_path: Path,
    model_path: Path,
    output_dir: Optional[Path] = None,
) -> dict:
    """
    Evaluate a saved model on the full feature dataset and log metrics to MLflow.

    Args:
        features_path: Path to processed features CSV.
        model_path:    Path to saved joblib model.
        output_dir:    Directory for saving prediction CSV and plots.

    Returns:
        dict with R², MAE, RMSE metrics.
    """
    cfg = load_config()
    mlflow_cfg = cfg["params"]["mlflow"]
    feature_cols = cfg["params"]["model"]["features"]
    target_col = cfg["params"]["model"]["target"]

    df = pd.read_csv(features_path)

    for col in ["soil_hsg", "lulc_class"]:
        if col in df.columns:
            le = LabelEncoder()
            df[col] = le.fit_transform(df[col].astype(str))

    X = df[feature_cols]
    y = df[target_col]

    model = joblib.load(model_path)
    y_pred = model.predict(X)

    r2 = r2_score(y, y_pred)
    mae = mean_absolute_error(y, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y, y_pred)))

    logger.info("Evaluation — R²=%.4f  MAE=%.2f mm  RMSE=%.2f mm", r2, mae, rmse)

    # Compute yield estimates
    efficiency = cfg["params"]["yield_estimation"]["efficiency_factor"]
    catchment_area_default = 10_000   # 1 ha = 10,000 m²

    df["predicted_runoff_mm"] = y_pred
    df["actual_runoff_mm"] = y.values
    df["predicted_yield_m3"] = (y_pred / 1000.0) * catchment_area_default * efficiency

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        pred_path = output_dir / "predictions.csv"
        df.to_csv(pred_path, index=False)
        logger.info("Predictions saved to %s", pred_path)

    # Log to MLflow
    mlflow.set_tracking_uri(mlflow_cfg["tracking_uri"])
    mlflow.set_experiment(mlflow_cfg["experiment_name"])

    with mlflow.start_run(run_name="evaluation"):
        mlflow.log_metrics({
            "eval_r2": r2,
            "eval_mae_mm": mae,
            "eval_rmse_mm": rmse,
        })
        if output_dir:
            mlflow.log_artifact(str(pred_path))

    return {"r2": r2, "mae_mm": mae, "rmse_mm": rmse}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate rainwater yield model.")
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    metrics = evaluate_model(args.features, args.model, args.output_dir)
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")
