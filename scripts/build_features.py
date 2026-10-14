"""
scripts/build_features.py
──────────────────────────
Build the final pixel-level feature matrix (data/processed/features.csv)
by combining:
  - Annual rainfall statistics from IMD NetCDF
  - Terrain attributes (slope) from interim DEM
  - Soil HSG from interim CSV
  - Curve Number derived from LULC + HSG
  - Yield estimate per pixel

This script is invoked by the 'build_features' DVC stage.

Prerequisites:
    pip install numpy pandas rasterio xarray netCDF4 pyyaml

Usage:
    python scripts/build_features.py
    python scripts/build_features.py --year 2022 --amc II
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import rowcol

from src.utils.config import load_config, get_data_dir, get_active_district
from src.features.curve_number import lookup_cn, compute_annual_runoff, compute_yield_m3

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def load_slope_at_points(
    slope_tif: Path,
    lats: np.ndarray,
    lons: np.ndarray,
) -> np.ndarray:
    """
    Sample slope values at given lat/lon points from a slope GeoTIFF.

    Returns:
        1D numpy array of slope values (degrees), NaN where outside raster.
    """
    with rasterio.open(slope_tif) as src:
        transform = src.transform
        rows, cols = rowcol(transform, lons, lats)
        rows = np.clip(rows, 0, src.height - 1)
        cols = np.clip(cols, 0, src.width - 1)
        data = src.read(1)
        nodata = src.nodata or -9999
        vals = data[rows, cols].astype(float)
        vals[vals == nodata] = np.nan
    return vals


def load_elevation_at_points(
    dem_tif: Path,
    lats: np.ndarray,
    lons: np.ndarray,
) -> np.ndarray:
    """Sample elevation at lat/lon points from DEM GeoTIFF."""
    with rasterio.open(dem_tif) as src:
        transform = src.transform
        rows, cols = rowcol(transform, lons, lats)
        rows = np.clip(rows, 0, src.height - 1)
        cols = np.clip(cols, 0, src.width - 1)
        data = src.read(1)
        nodata = src.nodata or -9999
        vals = data[rows, cols].astype(float)
        vals[vals == nodata] = np.nan
    return vals


def load_imd_annual_stats(
    imd_nc_dir: Path,
    year: int,
    lats: np.ndarray,
    lons: np.ndarray,
) -> pd.DataFrame:
    """
    Load IMD annual rainfall stats for a set of lat/lon points from NetCDF files.

    Returns:
        DataFrame with columns: annual_rainfall_mm, max_daily_mm, rainy_days.
    """
    import xarray as xr
    from pathlib import Path

    nc_files = list(imd_nc_dir.glob(f"imd_rf_{year}*.nc"))
    if not nc_files:
        logger.warning("No IMD NetCDF file found for year %d in %s", year, imd_nc_dir)
        n = len(lats)
        return pd.DataFrame({
            "annual_rainfall_mm": np.full(n, np.nan),
            "max_daily_mm": np.full(n, np.nan),
            "rainy_days": np.full(n, np.nan),
        })

    ds = xr.open_dataset(nc_files[0])
    rain_var = "rain" if "rain" in ds else list(ds.data_vars)[0]

    records = []
    for lat, lon in zip(lats, lons):
        try:
            pt = ds[rain_var].sel(lat=lat, lon=lon, method="nearest")
            vals = pt.values
            vals = np.where(np.isnan(vals), 0, vals)
            records.append({
                "annual_rainfall_mm": float(vals.sum()),
                "max_daily_mm": float(vals.max()),
                "rainy_days": int((vals >= 2.5).sum()),
            })
        except Exception:
            records.append({
                "annual_rainfall_mm": np.nan,
                "max_daily_mm": np.nan,
                "rainy_days": np.nan,
            })

    return pd.DataFrame(records)


def build_feature_matrix(year: int = 2022, amc: str = "II") -> pd.DataFrame:
    """
    Assemble the full feature matrix from all interim data sources.

    Returns:
        DataFrame written to data/processed/features.csv.
    """
    cfg = load_config()
    district = get_active_district(cfg)
    params = cfg["params"]

    # Paths
    soil_hsg_path = Path("data/interim/soil/hsg_points.csv")
    slope_tif = Path("data/interim/dem/slope_deg.tif")
    dem_tif = list(Path("data/raw/dem/cartodem").glob("*.tif"))
    imd_nc_dir = get_data_dir(cfg, "imd", stage="raw")
    output_path = Path("data/processed/features.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Load HSG points ───────────────────────────────────────────────────────
    if not soil_hsg_path.exists():
        raise FileNotFoundError(
            f"HSG points CSV not found: {soil_hsg_path}. Run 'soil_hsg' DVC stage first."
        )
    hsg_df = pd.read_csv(soil_hsg_path)
    logger.info("Loaded %d HSG points", len(hsg_df))

    lats = hsg_df["lat"].values
    lons = hsg_df["lon"].values

    # ── Slope ─────────────────────────────────────────────────────────────────
    if slope_tif.exists():
        hsg_df["slope_deg"] = load_slope_at_points(slope_tif, lats, lons)
    else:
        logger.warning("Slope raster not found. Setting slope=NaN.")
        hsg_df["slope_deg"] = np.nan

    # ── Elevation ─────────────────────────────────────────────────────────────
    if dem_tif:
        hsg_df["elevation_m"] = load_elevation_at_points(dem_tif[0], lats, lons)
    else:
        logger.warning("DEM raster not found. Setting elevation=NaN.")
        hsg_df["elevation_m"] = np.nan

    # ── Annual Rainfall ───────────────────────────────────────────────────────
    rainfall_df = load_imd_annual_stats(imd_nc_dir, year, lats, lons)
    hsg_df = pd.concat([hsg_df.reset_index(drop=True), rainfall_df.reset_index(drop=True)], axis=1)

    # ── LULC (placeholder — assign 'cropland' as default for agricultural land) ─
    # Replace with actual LULC classification results from Sentinel-2 when available
    hsg_df["lulc_class"] = "cropland"

    # ── Curve Number ──────────────────────────────────────────────────────────
    lambda_ = params["curve_number"]["lambda_"]
    hsg_df["curve_number"] = hsg_df.apply(
        lambda row: lookup_cn(row["lulc_class"], row["hsg"], amc=amc),
        axis=1,
    )

    # ── Daily Runoff via SCS-CN → Annual total ────────────────────────────────
    # Approximation using mean-storm approach (use actual daily series when available)
    # Annual runoff computed from annual rainfall using modified CN approach
    from src.features.curve_number import compute_runoff_mm
    hsg_df["annual_runoff_mm"] = compute_runoff_mm(
        hsg_df["annual_rainfall_mm"].fillna(0).values,
        hsg_df["curve_number"].values,
        lambda_=lambda_,
    )

    # ── NDVI placeholder ──────────────────────────────────────────────────────
    hsg_df["ndvi_mean_kharif"] = 0.35   # Replace with Sentinel-2 derived values

    # ── Yield estimate ────────────────────────────────────────────────────────
    efficiency = params["yield_estimation"]["efficiency_factor"]
    min_area_ha = params["yield_estimation"]["min_catchment_area_ha"]
    catchment_area_m2 = min_area_ha * 10_000

    hsg_df["annual_yield_m3"] = hsg_df["annual_runoff_mm"].apply(
        lambda q: compute_yield_m3(q, catchment_area_m2, efficiency)
    )

    # ── Final columns ──────────────────────────────────────────────────────────
    cols = [
        "lat", "lon",
        "elevation_m", "slope_deg",
        "clay_pct", "sand_pct", "silt_pct", "hsg",
        "lulc_class", "curve_number",
        "annual_rainfall_mm", "max_daily_mm", "rainy_days",
        "ndvi_mean_kharif",
        "annual_runoff_mm", "annual_yield_m3",
    ]
    cols = [c for c in cols if c in hsg_df.columns]
    out_df = hsg_df[cols].dropna(subset=["annual_runoff_mm"])

    out_df.to_csv(output_path, index=False)
    logger.info("Feature matrix saved: %s  (%d rows, %d cols)", output_path, len(out_df), len(out_df.columns))

    return out_df


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build pixel-level feature matrix.")
    parser.add_argument("--year", type=int, default=2022)
    parser.add_argument("--amc", type=str, default="II", choices=["I", "II", "III"])
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    df = build_feature_matrix(year=args.year, amc=args.amc)
    print(f"\nFeature matrix: {df.shape[0]} pixels × {df.shape[1]} features")
    print(df.describe().to_string())
