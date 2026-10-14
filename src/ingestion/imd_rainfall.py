"""
ingestion/imd_rainfall.py
─────────────────────────
Download and parse IMD 0.25° gridded daily rainfall binary (.bin) files
for the active study district.

Prerequisites:
    pip install imdlib pyyaml numpy netCDF4

Usage (CLI):
    python -m src.ingestion.imd_rainfall --year 2022
    python -m src.ingestion.imd_rainfall --year 2022 --save-nc

Usage (library):
    from src.ingestion.imd_rainfall import fetch_imd_rainfall
    ds = fetch_imd_rainfall(year=2022, bbox=(77.70, 12.90, 78.60, 13.90))
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional, Tuple

import imdlib
import numpy as np

from src.utils.config import load_config, get_active_district_bbox, get_data_dir

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def fetch_imd_rainfall(
    year: int,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    save_nc: bool = False,
    output_dir: Optional[Path] = None,
) -> "imdlib.RainfallData":
    """
    Download and optionally clip IMD daily rainfall for a given year.

    Args:
        year:       Calendar year (e.g., 2022).
        bbox:       (west, south, east, north) in WGS84 degrees.
                    If None, uses the active district bbox from config.
        save_nc:    If True, export clipped data as NetCDF4 to output_dir.
        output_dir: Directory to save output files.

    Returns:
        imdlib RainfallData object with daily rainfall grids.
    """
    cfg = load_config()

    if bbox is None:
        _bbox = get_active_district_bbox(cfg)
        bbox = (_bbox["west"], _bbox["south"], _bbox["east"], _bbox["north"])

    if output_dir is None:
        output_dir = get_data_dir(cfg, "imd", stage="raw")

    output_dir.mkdir(parents=True, exist_ok=True)
    west, south, east, north = bbox

    logger.info("Fetching IMD rainfall for year=%d, bbox=%s", year, bbox)

    # imdlib.get_data downloads the binary file from IMD FTP/HTTP
    data = imdlib.get_data(
        variable="rain",
        start_yr=year,
        end_yr=year,
        fn_format="yearwise",
        file_dir=str(output_dir),
    )

    logger.info("Downloaded %d daily slices for year %d", len(data.data), year)

    # Clip to bounding box
    data_clipped = data.get_xarray().sel(
        lat=slice(south, north),
        lon=slice(west, east),
    )

    logger.info(
        "Clipped grid shape: %s (lat × lon × time)", data_clipped["rain"].shape
    )

    if save_nc:
        nc_path = output_dir / f"imd_rf_{year}_kolar.nc"
        data_clipped.to_netcdf(nc_path)
        logger.info("Saved NetCDF to %s", nc_path)

    return data_clipped


def summarise_annual(ds) -> dict:
    """
    Compute annual rainfall statistics from an xarray Dataset.

    Args:
        ds: xarray Dataset/DataArray with daily rainfall values.

    Returns:
        dict with keys: total_mm, mean_mm, max_mm, rainy_days (threshold=2.5mm).
    """
    values = ds["rain"].values  # shape: (time, lat, lon)
    total = float(np.nansum(values))
    mean_px = float(np.nanmean(values.sum(axis=0)))   # total per pixel, averaged
    max_daily = float(np.nanmax(values))
    rainy_days = int((values >= 2.5).sum())

    stats = {
        "total_mm": total,
        "mean_annual_mm_per_pixel": mean_px,
        "max_daily_mm": max_daily,
        "rainy_days_grid": rainy_days,
    }
    logger.info("Annual stats: %s", stats)
    return stats


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download IMD gridded rainfall for the active study district."
    )
    parser.add_argument("--year", type=int, required=True, help="Year to download (e.g., 2022)")
    parser.add_argument(
        "--save-nc",
        action="store_true",
        default=False,
        help="Save clipped output as NetCDF4 file",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ds = fetch_imd_rainfall(year=args.year, save_nc=args.save_nc)
    stats = summarise_annual(ds)
    print("\n=== Annual Rainfall Summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v:.2f}" if isinstance(v, float) else f"  {k}: {v}")
