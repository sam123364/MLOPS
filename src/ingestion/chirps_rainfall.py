"""
ingestion/chirps_rainfall.py
────────────────────────────
Download and clip CHIRPS 0.05° daily/monthly rainfall GeoTIFFs for the
active study district via the CHIRPS public HTTP server.

Prerequisites:
    pip install requests rasterio numpy pyyaml

Usage (CLI):
    python -m src.ingestion.chirps_rainfall --year 2022 --month 7
    python -m src.ingestion.chirps_rainfall --year 2022  # full year

Usage (library):
    from src.ingestion.chirps_rainfall import fetch_chirps_year
    arr, profile = fetch_chirps_year(year=2022)
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np
import requests
import rasterio
from rasterio.mask import mask as rio_mask
from rasterio.crs import CRS
from shapely.geometry import box

from src.utils.config import load_config, get_active_district_bbox, get_data_dir

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# CHIRPS v2.0 global daily GeoTIFF base URL
CHIRPS_BASE_URL = (
    "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05"
)


def _chirps_url(year: int, month: int, day: int) -> str:
    """Build CHIRPS daily GeoTIFF download URL for a specific date."""
    return (
        f"{CHIRPS_BASE_URL}/{year}/"
        f"chirps-v2.0.{year}.{month:02d}.{day:02d}.tif.gz"
    )


def download_file(url: str, dest: Path, overwrite: bool = False) -> Path:
    """
    Download a file from url to dest.

    Returns:
        Path to downloaded file.
    """
    if dest.exists() and not overwrite:
        logger.debug("File already exists, skipping: %s", dest)
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading: %s", url)

    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    logger.info("Saved to: %s", dest)
    return dest


def clip_raster_to_bbox(
    src_path: Path,
    bbox: Tuple[float, float, float, float],
    out_path: Path,
) -> Path:
    """
    Clip a GeoTIFF raster to a bounding box and save.

    Args:
        src_path: Input GeoTIFF.
        bbox:     (west, south, east, north) in WGS84 degrees.
        out_path: Output GeoTIFF path.

    Returns:
        Path to clipped GeoTIFF.
    """
    west, south, east, north = bbox
    geom = [box(west, south, east, north).__geo_interface__]

    with rasterio.open(src_path) as src:
        out_image, out_transform = rio_mask(src, geom, crop=True)
        out_meta = src.meta.copy()

    out_meta.update(
        {
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
            "compress": "lzw",
        }
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **out_meta) as dest:
        dest.write(out_image)

    return out_path


def fetch_chirps_month(
    year: int,
    month: int,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    output_dir: Optional[Path] = None,
) -> List[Path]:
    """
    Download and clip all available CHIRPS daily GeoTIFFs for a given month.

    Args:
        year:       Calendar year.
        month:      Month (1–12).
        bbox:       (west, south, east, north). If None, uses active district.
        output_dir: Directory for downloaded files.

    Returns:
        List of paths to clipped GeoTIFF files.
    """
    import calendar
    import gzip
    import shutil

    cfg = load_config()

    if bbox is None:
        _bbox = get_active_district_bbox(cfg)
        bbox = (_bbox["west"], _bbox["south"], _bbox["east"], _bbox["north"])

    if output_dir is None:
        output_dir = get_data_dir(cfg, "chirps", stage="raw") / f"{year}" / f"{month:02d}"

    output_dir.mkdir(parents=True, exist_ok=True)
    clipped_files: List[Path] = []

    _, n_days = calendar.monthrange(year, month)

    for day in range(1, n_days + 1):
        url = _chirps_url(year, month, day)
        gz_dest = output_dir / Path(url).name
        tif_dest = gz_dest.with_suffix("")  # remove .gz
        clipped_dest = output_dir / f"chirps_clipped_{year}{month:02d}{day:02d}.tif"

        if clipped_dest.exists():
            clipped_files.append(clipped_dest)
            continue

        try:
            download_file(url, gz_dest)
            # Decompress .tif.gz
            with gzip.open(gz_dest, "rb") as f_in, open(tif_dest, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            gz_dest.unlink()

            clip_raster_to_bbox(tif_dest, bbox, clipped_dest)
            tif_dest.unlink()  # remove full-extent TIF
            clipped_files.append(clipped_dest)

        except requests.HTTPError as exc:
            logger.warning("Could not fetch %s: %s", url, exc)

    logger.info("Fetched %d daily files for %d-%02d", len(clipped_files), year, month)
    return clipped_files


def fetch_chirps_year(
    year: int,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    output_dir: Optional[Path] = None,
) -> List[Path]:
    """
    Download and clip all CHIRPS daily files for an entire year.

    Returns:
        List of paths to clipped daily GeoTIFFs (up to 365/366 files).
    """
    all_files: List[Path] = []
    for month in range(1, 13):
        monthly_files = fetch_chirps_month(year, month, bbox=bbox, output_dir=output_dir)
        all_files.extend(monthly_files)

    logger.info("Total CHIRPS files for %d: %d", year, len(all_files))
    return all_files


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download CHIRPS daily rainfall for the active study district."
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, default=None, help="Month (1–12). If omitted, downloads full year.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.month:
        files = fetch_chirps_month(args.year, args.month)
    else:
        files = fetch_chirps_year(args.year)
    print(f"\nDownloaded {len(files)} file(s).")
