"""
models/train.py
────────────────
Train and evaluate a machine learning model for rainwater yield estimation.
Tracks experiments with MLflow, using params.yaml for hyperparameters.

Model: RandomForest baseline (configurable in params.yaml)

Prerequisites:
    pip install scikit-learn mlflow pandas numpy pyyaml

Usage (CLI):
    python -m src.models.train --features data/processed/features.csv

Usage (DVC):
    Invoked by the 'train' stage in dvc.yaml
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import LabelEncoder

from src.utils.config import load_config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def load_features(features_path: Path) -> tuple[pd.DataFrame, pd.Series]:
    """
    Load feature matrix and target variable from a CSV file.

    Expected CSV columns include:
        annual_rainfall_mm, slope_deg, curve_number, soil_hsg, lulc_class,
        elevation_m, ndvi_mean_kharif, annual_runoff_mm (target)

    Returns:
        (X, y) tuple.
    """
    df = pd.read_csv(features_path)
    cfg = load_config()
    target_col = cfg["params"]["model"]["target"]
    feature_cols = cfg["params"]["model"]["features"]

    # Encode categorical columns
    for col in ["soil_hsg", "lulc_class"]:
        if col in df.columns:
            le = LabelEncoder()
            df[col] = le.fit_transform(df[col].astype(str))

    missing = [c for c in feature_cols + [target_col] if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in features CSV: {missing}")

    X = df[feature_cols]
    y = df[target_col]

    logger.info("Loaded %d samples, %d features, target='%s'", len(df), len(feature_cols), target_col)
    return X, y


def train_model(
    features_path: Path,
    model_output_dir: Optional[Path] = None,
) -> None:
    """
    Train a RandomForest regressor with MLflow experiment tracking.

    Args:
        features_path:    Path to processed features CSV.
        model_output_dir: Where to save the trained model artifact.
    """
    cfg = load_config()
    mlflow_cfg = cfg["params"]["mlflow"]
    rf_cfg = cfg["params"]["model"]["random_forest"]
    cv_folds = cfg["params"]["model"]["cv_folds"]
    scoring = cfg["params"]["model"]["scoring_metric"]
    efficiency = cfg["params"]["yield_estimation"]["efficiency_factor"]

    # Configure MLflow
    mlflow.set_tracking_uri(mlflow_cfg["tracking_uri"])
    mlflow.set_experiment(mlflow_cfg["experiment_name"])

    X, y = load_features(features_path)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.2,
        random_state=rf_cfg["random_state"],
    )

    model = RandomForestRegressor(
        n_estimators=rf_cfg["n_estimators"],
        max_depth=rf_cfg["max_depth"],
        min_samples_leaf=rf_cfg["min_samples_leaf"],
        random_state=rf_cfg["random_state"],
        n_jobs=-1,
    )

    with mlflow.start_run() as run:
        run_id = run.info.run_id
        logger.info("MLflow run ID: %s", run_id)

        # Log parameters
        mlflow.log_params({
            "n_estimators": rf_cfg["n_estimators"],
            "max_depth": rf_cfg["max_depth"],
            "min_samples_leaf": rf_cfg["min_samples_leaf"],
            "random_state": rf_cfg["random_state"],
            "cv_folds": cv_folds,
            "efficiency_factor": efficiency,
            "n_train": len(X_train),
            "n_test": len(X_test),
        })

        # Cross-validation on training set
        cv_scores = cross_val_score(model, X_train, y_train, cv=cv_folds, scoring=scoring)
        mlflow.log_metric("cv_r2_mean", float(np.mean(cv_scores)))
        mlflow.log_metric("cv_r2_std", float(np.std(cv_scores)))
        logger.info("CV R²: %.4f ± %.4f", np.mean(cv_scores), np.std(cv_scores))

        # Train on full training set
        model.fit(X_train, y_train)

        # Evaluation on test set
        y_pred = model.predict(X_test)
        test_r2 = r2_score(y_test, y_pred)
        test_mae = mean_absolute_error(y_test, y_pred)
        test_rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))

        mlflow.log_metrics({
            "test_r2": test_r2,
            "test_mae_mm": test_mae,
            "test_rmse_mm": test_rmse,
        })

        logger.info("Test R²=%.4f  MAE=%.2f mm  RMSE=%.2f mm", test_r2, test_mae, test_rmse)

        # Feature importance
        feat_imp = dict(zip(X.columns, model.feature_importances_))
        logger.info("Feature importances: %s", {k: f"{v:.3f}" for k, v in sorted(feat_imp.items(), key=lambda x: -x[1])})
        mlflow.log_dict(feat_imp, "feature_importance.json")

        # Log and register model
        mlflow.sklearn.log_model(model, "random_forest_model")

        if model_output_dir:
            model_output_dir.mkdir(parents=True, exist_ok=True)
            import joblib
            model_path = model_output_dir / "random_forest_model.joblib"
            joblib.dump(model, model_path)
            mlflow.log_artifact(str(model_path))
            logger.info("Model saved to %s", model_path)

    return


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train rainwater yield model.")
    parser.add_argument(
        "--features",
        type=Path,
        default=Path("data/processed/features.csv"),
        help="Path to features CSV",
    )
    parser.add_argument(
        "--model-output-dir",
        type=Path,
        default=Path("data/processed/models"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    train_model(args.features, args.model_output_dir)
