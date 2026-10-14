"""
ingestion/soilgrids_fetch.py
─────────────────────────────
Fetch SoilGrids v2.0 soil property data via the ISRIC REST API
for the active study district bounding box.

Properties fetched: clay, sand, silt, bdod, ocd
Depths: 0-5cm, 5-15cm, 15-30cm

Prerequisites:
    pip install requests pyyaml numpy pandas

Usage (CLI):
    python -m src.ingestion.soilgrids_fetch

Usage (library):
    from src.ingestion.soilgrids_fetch import fetch_soilgrids_bbox
    df = fetch_soilgrids_bbox()
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.utils.config import load_config, get_active_district_bbox, get_data_dir

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SOILGRIDS_API = "https://rest.soilgrids.org/soilgrids/v2.0/properties/query"
MAX_RETRIES = 3
RETRY_DELAY_S = 5


def _query_point(
    lat: float,
    lon: float,
    properties: List[str],
    depths: List[str],
) -> Dict[str, Any]:
    """
    Query SoilGrids REST API for a single lat/lon point.

    Returns:
        JSON response dict (or empty dict on error).
    """
    params = {
        "lat": lat,
        "lon": lon,
        "property": properties,
        "depth": depths,
        "value": "mean",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(SOILGRIDS_API, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.warning("Attempt %d/%d failed for (%.4f, %.4f): %s", attempt, MAX_RETRIES, lat, lon, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_S * attempt)

    return {}


def fetch_soilgrids_bbox(
    bbox: Optional[Tuple[float, float, float, float]] = None,
    grid_step_deg: float = 0.1,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Sample SoilGrids at a regular grid over the bounding box.

    Since SoilGrids REST API is point-based, we sample at grid_step_deg
    intervals and save results to JSONL for downstream processing.

    Args:
        bbox:          (west, south, east, north). If None, uses active district.
        grid_step_deg: Sampling interval in degrees (default 0.1° ≈ 11km).
        output_dir:    Where to save output JSONL.

    Returns:
        Path to saved JSONL file.
    """
    import numpy as np

    cfg = load_config()

    if bbox is None:
        _bbox = get_active_district_bbox(cfg)
        bbox = (_bbox["west"], _bbox["south"], _bbox["east"], _bbox["north"])

    if output_dir is None:
        output_dir = get_data_dir(cfg, "soilgrids", stage="raw")

    output_dir.mkdir(parents=True, exist_ok=True)

    properties = cfg["data_sources"]["soilgrids"]["properties"]
    depths = cfg["data_sources"]["soilgrids"]["depths"]

    west, south, east, north = bbox
    lats = np.arange(south, north + grid_step_deg, grid_step_deg)
    lons = np.arange(west, east + grid_step_deg, grid_step_deg)

    total_points = len(lats) * len(lons)
    logger.info(
        "Sampling SoilGrids at %d points (%.2f° grid) over bbox %s",
        total_points, grid_step_deg, bbox,
    )

    out_path = output_dir / "soilgrids_samples.jsonl"
    count = 0

    with open(out_path, "w", encoding="utf-8") as fh:
        for lat in lats:
            for lon in lons:
                result = _query_point(lat, lon, properties, depths)
                if result:
                    record = {
                        "lat": round(float(lat), 6),
                        "lon": round(float(lon), 6),
                        "data": result,
                    }
                    fh.write(json.dumps(record) + "\n")
                    count += 1
                    time.sleep(0.3)  # rate-limit: respect ISRIC fair-use policy

    logger.info("Saved %d soil records to %s", count, out_path)
    return out_path


if __name__ == "__main__":
    output = fetch_soilgrids_bbox()
    print(f"SoilGrids data saved to: {output}")
