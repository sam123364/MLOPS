"""
ingestion/nasa_power_fetch.py
──────────────────────────────
Fetch NASA POWER daily meteorological data for the active district centroid.
Used for FAO-56 reference evapotranspiration (ET0) calculation.

Parameters fetched: T2M, T2M_MAX, T2M_MIN, ALLSKY_SFC_SW_DWN, RH2M, WS2M

Prerequisites:
    pip install requests pandas pyyaml

Usage (CLI):
    python -m src.ingestion.nasa_power_fetch --year 2022

Usage (library):
    from src.ingestion.nasa_power_fetch import fetch_nasa_power
    df = fetch_nasa_power(lat=13.13, lon=78.13, year=2022)
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from src.utils.config import load_config, get_active_district, get_data_dir

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

NASA_POWER_API = "https://power.larc.nasa.gov/api/temporal/daily/point"


def fetch_nasa_power(
    lat: float,
    lon: float,
    year: int,
    parameters: Optional[list] = None,
    output_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Download NASA POWER daily data for a point location and year.

    Args:
        lat:        Latitude in decimal degrees.
        lon:        Longitude in decimal degrees.
        year:       Calendar year.
        parameters: List of POWER parameter codes. If None, uses config defaults.
        output_dir: Directory to save CSV output.

    Returns:
        DataFrame with columns: date + one column per parameter.
    """
    cfg = load_config()

    if parameters is None:
        parameters = cfg["data_sources"]["nasa_power"]["parameters"]

    if output_dir is None:
        raw_dir = cfg["data_sources"]["nasa_power"].get("raw_dir", "data/raw/climate/nasa_power")
        from src.utils.config import get_project_root
        output_dir = (get_project_root() / raw_dir).resolve()

    output_dir.mkdir(parents=True, exist_ok=True)

    district = get_active_district(cfg)
    csv_path = output_dir / f"nasa_power_{district}_{year}.csv"

    if csv_path.exists():
        logger.info("Loading cached NASA POWER data from %s", csv_path)
        return pd.read_csv(csv_path, parse_dates=["date"])

    start_date = f"{year}0101"
    end_date = f"{year}1231"

    params = {
        "parameters": ",".join(parameters),
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": start_date,
        "end": end_date,
        "format": "JSON",
    }

    logger.info("Fetching NASA POWER data for (%.4f, %.4f), year=%d", lat, lon, year)

    resp = requests.get(NASA_POWER_API, params=params, timeout=120)
    resp.raise_for_status()
    payload = resp.json()

    # Extract parameter time series
    parameter_data = payload["properties"]["parameter"]

    df = pd.DataFrame(parameter_data)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "date"
    df = df.reset_index()

    # Replace fill value (-999) with NaN
    df = df.replace(-999.0, float("nan"))

    df.to_csv(csv_path, index=False)
    logger.info("Saved %d rows to %s", len(df), csv_path)

    return df


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch NASA POWER daily met data for the active study district centroid."
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--lat", type=float, default=None, help="Latitude (default: active district centroid)")
    parser.add_argument("--lon", type=float, default=None, help="Longitude (default: active district centroid)")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    cfg = load_config()
    district = get_active_district(cfg)
    centroid = cfg["study_area"]["districts"][district]["centroid"]

    lat = args.lat if args.lat else centroid["lat"]
    lon = args.lon if args.lon else centroid["lon"]

    df = fetch_nasa_power(lat=lat, lon=lon, year=args.year)
    print(df.head(10).to_string())
    print(f"\nShape: {df.shape}")
