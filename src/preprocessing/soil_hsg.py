"""
preprocessing/soil_hsg.py
──────────────────────────
Derive USDA Hydrologic Soil Groups (HSG: A/B/C/D) from SoilGrids
clay, sand, and silt fractions.

HSG assignment rules (USDA NRCS Part 630, Ch. 7):
    A: Sandy, loamy sand, or sandy loam soils; low runoff potential
    B: Silt loam or loam soils; moderate runoff potential
    C: Sandy clay loam soils; moderately high runoff potential
    D: Clay loam, silty clay loam, sandy clay, silty clay, or clay; high runoff potential

Prerequisites:
    pip install pandas numpy pyyaml

Usage (library):
    from src.preprocessing.soil_hsg import derive_hsg_from_fractions
    hsg = derive_hsg_from_fractions(clay_pct=35, sand_pct=20, silt_pct=45)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def derive_hsg_from_fractions(
    clay_pct: float,
    sand_pct: float,
    silt_pct: float,
) -> str:
    """
    Assign USDA Hydrologic Soil Group (A/B/C/D) from soil texture fractions.

    Rules based on USDA NRCS textural triangle with simplified thresholds
    appropriate for the SCS-CN method:

    Args:
        clay_pct:  Clay content (%).
        sand_pct:  Sand content (%).
        silt_pct:  Silt content (%).

    Returns:
        HSG string: 'A', 'B', 'C', or 'D'.
    """
    # Normalise (fractions may not sum to exactly 100 due to coarse fraction)
    total = clay_pct + sand_pct + silt_pct
    if total > 0:
        clay_pct = clay_pct / total * 100
        sand_pct = sand_pct / total * 100

    # Group D: Heavy clays
    if clay_pct >= 40:
        return "D"

    # Group C: Sandy clay loam (clay 20–35%, sand 45–80%)
    if 20 <= clay_pct < 40 and sand_pct >= 45:
        return "C"

    # Group A: Sandy soils (sand > 70%, clay < 18%)
    if sand_pct >= 70 and clay_pct < 18:
        return "A"

    # Group B: Loam / silt loam / silty clay loam
    if clay_pct < 20:
        return "B"

    # Default for ambiguous mid-range textures
    if clay_pct < 30:
        return "C"

    return "D"


def process_soilgrids_jsonl(
    jsonl_path: Path,
    output_path: Optional[Path] = None,
    depth: str = "0-5cm",
) -> pd.DataFrame:
    """
    Load SoilGrids JSONL (from ingestion/soilgrids_fetch.py) and derive HSG
    for each sampled point.

    Args:
        jsonl_path:  Path to soilgrids_samples.jsonl.
        output_path: If given, save the resulting DataFrame to CSV.
        depth:       Soil depth to use ('0-5cm', '5-15cm', '15-30cm').

    Returns:
        DataFrame with columns: lat, lon, clay_pct, sand_pct, silt_pct, hsg.
    """
    records = []

    with open(jsonl_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            lat = obj["lat"]
            lon = obj["lon"]

            props = obj.get("data", {}).get("properties", {}).get("layers", [])

            clay = sand = silt = None
            for layer in props:
                prop_name = layer.get("name", "")
                for depth_data in layer.get("depths", []):
                    if depth_data.get("label") != depth:
                        continue
                    val = depth_data.get("values", {}).get("mean")
                    if val is None:
                        continue
                    if prop_name == "clay":
                        clay = val / 10.0   # SoilGrids returns g/kg (×0.1 = %)
                    elif prop_name == "sand":
                        sand = val / 10.0
                    elif prop_name == "silt":
                        silt = val / 10.0

            if clay is not None and sand is not None and silt is not None:
                hsg = derive_hsg_from_fractions(clay, sand, silt)
                records.append({
                    "lat": lat,
                    "lon": lon,
                    "clay_pct": round(clay, 2),
                    "sand_pct": round(sand, 2),
                    "silt_pct": round(silt, 2),
                    "hsg": hsg,
                })

    df = pd.DataFrame(records)
    logger.info("Derived HSG for %d points from %s", len(df), jsonl_path)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info("Saved HSG data to %s", output_path)

    return df


def hsg_summary(df: pd.DataFrame) -> pd.Series:
    """Return HSG value counts (percentage distribution) for the district."""
    counts = df["hsg"].value_counts()
    pct = (counts / counts.sum() * 100).round(1)
    return pct
