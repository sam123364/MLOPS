"""
utils/config.py
───────────────
Central configuration loader for the Rainwater Yield Estimation project.

Usage:
    from src.utils.config import load_config, get_active_district_bbox

    cfg = load_config()
    bbox = get_active_district_bbox(cfg)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml


# Project root = two levels up from this file (src/utils/config.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = PROJECT_ROOT / "configs"


def load_yaml(path: Path) -> Dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_config() -> Dict[str, Any]:
    """
    Load and merge all configuration files into a single dict.

    Returns:
        Merged dict with keys: 'study_area', 'data_sources', 'params'
    """
    return {
        "study_area": load_yaml(CONFIGS_DIR / "study_area.yaml"),
        "data_sources": load_yaml(CONFIGS_DIR / "data_sources.yaml"),
        "params": load_yaml(CONFIGS_DIR / "params.yaml"),
    }


def get_active_district(cfg: Dict[str, Any]) -> str:
    """Return the active district key (e.g., 'kolar')."""
    return cfg["study_area"]["active_district"]


def get_active_district_bbox(cfg: Dict[str, Any]) -> Dict[str, float]:
    """
    Return the bounding box for the active district.

    Returns:
        dict with keys: west, south, east, north  (all float, WGS84 degrees)
    """
    district = get_active_district(cfg)
    return cfg["study_area"]["districts"][district]["bbox"]


def get_active_district_crs(cfg: Dict[str, Any]) -> str:
    """Return the projected CRS (e.g., 'EPSG:32643') for the active district."""
    district = get_active_district(cfg)
    return cfg["study_area"]["districts"][district]["utm_crs"]


def get_data_dir(cfg: Dict[str, Any], source: str, stage: str = "raw") -> Path:
    """
    Resolve the absolute path for a data directory.

    Args:
        cfg:    Full config dict (from load_config())
        source: Dataset key, e.g. 'imd', 'chirps', 'cartodem'
        stage:  'raw' | 'interim' | 'processed'

    Returns:
        Absolute Path object.
    """
    key = "raw_dir" if stage == "raw" else "interim_dir"
    rel_path = cfg["data_sources"][source][key]
    return (PROJECT_ROOT / rel_path).resolve()


def get_project_root() -> Path:
    """Return the absolute project root Path."""
    return PROJECT_ROOT
