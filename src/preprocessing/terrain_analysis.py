"""
preprocessing/terrain_analysis.py
───────────────────────────────────
Derive terrain attributes from a DEM GeoTIFF:
  - Slope (degrees)
  - Aspect (degrees)
  - Flow direction (D8)
  - Flow accumulation
  - Drainage lines (thresholded flow accumulation)

Prerequisites:
    pip install rasterio numpy scipy pysheds

Usage (CLI):
    python -m src.preprocessing.terrain_analysis --dem data/raw/dem/cartodem/kolar.tif

Usage (library):
    from src.preprocessing.terrain_analysis import run_terrain_analysis
    outputs = run_terrain_analysis(dem_path)
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import rasterio
from rasterio import features
from rasterio.transform import from_bounds

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def compute_slope_aspect(
    elevation: np.ndarray,
    cell_size_m: float = 30.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute slope (degrees) and aspect (degrees from North) from an elevation array.

    Args:
        elevation:   2D numpy array of elevation in metres.
        cell_size_m: Pixel/cell size in metres.

    Returns:
        (slope_deg, aspect_deg) — both 2D numpy arrays matching elevation shape.
    """
    # Gradient (dz/dx, dz/dy) using numpy gradient
    dz_dy, dz_dx = np.gradient(elevation, cell_size_m, cell_size_m)

    # Slope in degrees
    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    slope_deg = np.degrees(slope_rad)

    # Aspect in degrees (measured clockwise from North)
    aspect_rad = np.arctan2(-dz_dx, dz_dy)
    aspect_deg = np.degrees(aspect_rad)
    aspect_deg[aspect_deg < 0] += 360.0

    return slope_deg, aspect_deg


def save_raster(
    array: np.ndarray,
    profile: dict,
    out_path: Path,
    nodata: float = -9999.0,
) -> None:
    """Write a 2D numpy array as a GeoTIFF."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    profile = profile.copy()
    profile.update(
        dtype=rasterio.float32,
        count=1,
        nodata=nodata,
        compress="lzw",
        driver="GTiff",
    )
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(array.astype(np.float32), 1)
    logger.info("Saved raster: %s  shape=%s", out_path.name, array.shape)


def run_terrain_analysis(
    dem_path: Path,
    output_dir: Optional[Path] = None,
    drain_threshold: int = 500,
) -> Dict[str, Path]:
    """
    Run the full terrain analysis pipeline on a DEM GeoTIFF.

    Args:
        dem_path:        Path to input DEM GeoTIFF.
        output_dir:      Directory for output rasters. Defaults to interim/dem/.
        drain_threshold: Flow-accumulation cell count to define drainage lines.

    Returns:
        Dict mapping product name → output path.
    """
    from src.utils.config import load_config, get_data_dir

    cfg = load_config()

    if output_dir is None:
        output_dir = get_data_dir(cfg, "cartodem", stage="interim")

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Opening DEM: %s", dem_path)
    with rasterio.open(dem_path) as src:
        elevation = src.read(1).astype(np.float64)
        profile = src.profile
        transform = src.transform

        # Infer cell size from transform (assumes projected CRS in metres)
        cell_size_m = abs(transform.a)
        if cell_size_m > 1:
            logger.info("Cell size: %.1f m (projected CRS assumed)", cell_size_m)
        else:
            # Geographic CRS — approximate degrees to metres at study area latitude
            cell_size_m = cell_size_m * 111_320
            logger.info("Cell size: ~%.1f m (geographic CRS, converted at equator approx.)", cell_size_m)

    # Replace nodata with NaN
    nodata_val = profile.get("nodata", -9999)
    elevation[elevation == nodata_val] = np.nan

    outputs: Dict[str, Path] = {}

    # ── Slope & Aspect ────────────────────────────────────────────────────────
    slope_deg, aspect_deg = compute_slope_aspect(elevation, cell_size_m)

    slope_path = output_dir / "slope_deg.tif"
    aspect_path = output_dir / "aspect_deg.tif"
    save_raster(slope_deg, profile, slope_path)
    save_raster(aspect_deg, profile, aspect_path)
    outputs["slope"] = slope_path
    outputs["aspect"] = aspect_path

    # ── Flow Accumulation (via pysheds) ───────────────────────────────────────
    try:
        from pysheds.grid import Grid

        grid = Grid.from_raster(str(dem_path))
        dem_py = grid.read_raster(str(dem_path))

        # Fill pits and depressions
        pit_filled = grid.fill_pits(dem_py)
        flooded = grid.fill_depressions(pit_filled)
        inflated = grid.resolve_flats(flooded)

        # D8 flow direction
        fdir = grid.flowdir(inflated)
        fdir_path = output_dir / "flow_direction.tif"
        grid.to_raster(fdir, str(fdir_path))
        outputs["flow_direction"] = fdir_path

        # Flow accumulation
        acc = grid.accumulation(fdir)
        acc_path = output_dir / "flow_accumulation.tif"
        grid.to_raster(acc, str(acc_path))
        outputs["flow_accumulation"] = acc_path

        # Drainage lines (thresholded)
        acc_array = np.array(acc)
        drainage = (acc_array >= drain_threshold).astype(np.uint8)
        drain_path = output_dir / "drainage_lines.tif"
        drain_profile = profile.copy()
        drain_profile.update(dtype=rasterio.uint8, nodata=0, count=1, compress="lzw")
        with rasterio.open(drain_path, "w", **drain_profile) as dst:
            dst.write(drainage, 1)
        outputs["drainage_lines"] = drain_path
        logger.info("Drainage lines saved (threshold=%d cells)", drain_threshold)

    except ImportError:
        logger.warning("pysheds not installed. Skipping flow accumulation. Install with: pip install pysheds")

    logger.info("Terrain analysis complete. Outputs: %s", list(outputs.keys()))
    return outputs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Terrain analysis from DEM GeoTIFF.")
    parser.add_argument("--dem", type=Path, required=True, help="Path to input DEM GeoTIFF")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--drain-threshold", type=int, default=500)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    outputs = run_terrain_analysis(args.dem, args.output_dir, args.drain_threshold)
    for name, path in outputs.items():
        print(f"  {name}: {path}")
