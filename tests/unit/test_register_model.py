"""
tests/unit/test_register_model.py
─────────────────────────────────
Unit tests for the MLflow model registry and promotion pipeline (Workstream A & D).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import mlflow
from mlflow.tracking import MlflowClient

from src.models.register_model import (
    configure_mlflow,
    fetch_best_baseline_run,
    register_model_version,
    promote_to_production,
    run_pipeline,
    BENCHMARK_MAX_MAE_MM,
    BENCHMARK_MIN_COVERAGE_80PCT,
)


@pytest.fixture
def mlflow_test_env(tmp_path: Path):
    """Create isolated SQLite MLflow tracking registry."""
    db_path = tmp_path / "test_mlflow.db"
    tracking_uri = f"sqlite:///{db_path}"
    configure_mlflow(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)
    return client, tracking_uri, tmp_path


def test_seed_and_fetch_best_baseline_run(mlflow_test_env):
    client, tracking_uri, tmp_path = mlflow_test_env
    exp_name = "test_rainfall_baseline_evaluation"

    # Run pipeline to seed and register
    result = run_pipeline(
        tracking_uri=tracking_uri,
        experiment_name=exp_name,
        model_name="test_bengaluru_model",
        promote=False,
        repo_root=Path.cwd(),
    )

    assert result["model_name"] == "test_bengaluru_model"
    assert result["stage"] == "Staging"
    assert "git_commit" in result["tags"]
    assert "dvc_data_version" in result["tags"]
    assert result["tags"]["author"] == "Samiksha / Workstream A & D"

    # Verify best run selection
    best_run = fetch_best_baseline_run(client, experiment_name=exp_name)
    assert best_run.info.run_id == result["run_id"]


def test_promote_to_production_gate_fail(mlflow_test_env):
    client, tracking_uri, tmp_path = mlflow_test_env
    exp_name = "test_promotion_fail"

    # Baseline with MAE > 35 mm should stay in Staging
    result = run_pipeline(
        tracking_uri=tracking_uri,
        experiment_name=exp_name,
        model_name="test_bengaluru_model_fail",
        promote=True,
        repo_root=Path.cwd(),
    )

    assert result["stage"] == "Staging"
    assert result["promoted"] is False
    assert "NOT PROMOTED" in result["promotion_message"]


def test_promote_to_production_gate_success(mlflow_test_env):
    client, tracking_uri, tmp_path = mlflow_test_env
    exp_name = "test_promotion_pass"

    client.create_experiment(exp_name)
    exp = client.get_experiment_by_name(exp_name)

    # Log an exemplary model that meets benchmark: MAE < 35 mm and Coverage >= 75%
    with mlflow.start_run(experiment_id=exp.experiment_id, run_name="B4_quantile_regression") as run:
        mlflow.log_param("model_type", "B4_quantile_regression")
        mlflow.log_metric("mae_mm", 28.5)
        mlflow.log_metric("coverage_80pct", 82.0)

        # Artifact
        dummy_file = tmp_path / "model_spec.json"
        dummy_file.write_text(json.dumps({"name": "B4", "mae": 28.5}))
        mlflow.log_artifact(str(dummy_file), artifact_path="model")

    best_run = fetch_best_baseline_run(client, experiment_name=exp_name)
    model_name = "test_promoted_model"

    mv = register_model_version(client, best_run, model_name, repo_root=Path.cwd())
    assert mv.current_stage == "Staging"

    promoted, msg = promote_to_production(client, model_name, mv, run=best_run)
    assert promoted is True
    assert "PROMOTED" in msg

    updated_mv = client.get_model_version(model_name, mv.version)
    assert updated_mv.current_stage == "Production"
