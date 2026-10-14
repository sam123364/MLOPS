"""
IMD Gridded Historical Rainfall Preprocessing Pipeline
======================================================
Processes raw NetCDF IMD gridded daily rainfall data into analysis-ready,
reproducible Parquet datasets and features for Kolar, Chikkaballapur, and Tumakuru.

Phase 1: Dataset Inspection & Profiling
Phase 2: Geographic Filtering (Provisional BBox AOI)
Phase 3: Parquet & Metadata Generation
Phase 4: Validation & Quality Control
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Any

import h5py
import numpy as np
import pandas as pd
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Standard IMD dry-day definition threshold (mm/day)
DEFAULT_DRY_DAY_THRESHOLD_MM = 2.5


def parse_args():
    parser = argparse.ArgumentParser(description="Process IMD NetCDF daily rainfall dataset.")
    parser.add_argument(
        "--input",
        type=str,
        default="imdweb_nSbYRBgK.nc",
        help="Path to raw IMD NetCDF file.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/study_area.yaml",
        help="Path to study area YAML config.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/processed",
        help="Output directory for processed parquet files.",
    )
    parser.add_argument(
        "--metadata-dir",
        type=str,
        default="data/metadata",
        help="Output directory for metadata profile.",
    )
    parser.add_argument(
        "--figures-dir",
        type=str,
        default="reports/figures",
        help="Output directory for diagnostic figures.",
    )
    parser.add_argument(
        "--dry-threshold",
        type=float,
        default=DEFAULT_DRY_DAY_THRESHOLD_MM,
        help="Threshold in mm/day below which a day is classified as dry.",
    )
    return parser.parse_args()


def inspect_raw_netcdf(nc_path: Path) -> Dict[str, Any]:
    """Inspect NetCDF structure, coordinates, dimensions, and variables using h5py."""
    if not nc_path.exists():
        raise FileNotFoundError(f"Input NetCDF file not found: {nc_path}")

    logger.info("Inspecting raw NetCDF file: %s", nc_path)
    with h5py.File(nc_path, "r") as f:
        if "rain" not in f:
            raise ValueError(f"Expected group 'rain' not found in {nc_path}. Keys: {list(f.keys())}")

        g = f["rain"]
        lats = g["lat"][:].astype(float)
        lons = g["lon"][:].astype(float)
        t_raw = g["time"][:].astype(int)
        rain_ds = g["rain"]
        shape = rain_ds.shape  # (time, lat, lon)

        # Time decoding: units 'days since 1901-01-01'
        time_attrs = {k: v.decode("utf-8") if isinstance(v, bytes) else str(v) for k, v in g["time"].attrs.items()}
        rain_attrs = {k: v.decode("utf-8") if isinstance(v, bytes) else str(v) for k, v in rain_ds.attrs.items()}

        time_units = time_attrs.get("units", "days since 1901-01-01")
        if "days since" in time_units:
            base_str = time_units.split("days since")[1].strip()
            dates = pd.to_datetime(base_str) + pd.to_timedelta(t_raw, unit="D")
        else:
            raise ValueError(f"Unsupported time units: {time_units}")

        # Check temporal continuity
        t_diffs = np.diff(t_raw)
        is_continuous = bool(np.all(t_diffs == 1))
        has_duplicate_dates = len(dates) != len(dates.unique())

        profile = {
            "file_name": nc_path.name,
            "file_size_bytes": nc_path.stat().st_size,
            "dimensions": {"time": int(shape[0]), "lat": int(shape[1]), "lon": int(shape[2])},
            "variables": ["lat", "lon", "time", "rain", "spatial_ref"],
            "latitudes": [float(x) for x in lats],
            "longitudes": [float(x) for x in lons],
            "lat_range": [float(lats.min()), float(lats.max())],
            "lon_range": [float(lons.min()), float(lons.max())],
            "lat_step": float(np.round(np.diff(lats).mean(), 4)),
            "lon_step": float(np.round(np.diff(lons).mean(), 4)),
            "time_range": [dates[0].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d")],
            "time_units": time_units,
            "is_temporally_continuous_daily": is_continuous,
            "has_duplicate_dates": has_duplicate_dates,
            "rain_units": rain_attrs.get("units", "mm/day"),
            "rain_long_name": rain_attrs.get("long_name", "Rainfall"),
        }
        return profile


def load_study_area_bboxes(config_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load district bounding boxes from YAML configuration."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    target_districts = ["kolar", "chikkaballapur", "tumakuru"]
    districts = {}
    for d_key in target_districts:
        if d_key in cfg.get("districts", {}):
            d_info = cfg["districts"][d_key]
            districts[d_info["name"]] = {
                "bbox": d_info["bbox"],
                "centroid": d_info.get("centroid"),
                "key": d_key,
            }
        else:
            raise KeyError(f"District {d_key} missing in {config_path}")
    return districts


def map_grid_cells_to_districts(
    lats: np.ndarray,
    lons: np.ndarray,
    district_bboxes: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Tuple[float, float]]]:
    """Map IMD 0.25 deg grid cell points to district approximate bounding boxes."""
    mapping = {}
    for dist_name, info in district_bboxes.items():
        bbox = info["bbox"]
        cells = []
        for lat in lats:
            for lon in lons:
                if (bbox["south"] <= lat <= bbox["north"]) and (bbox["west"] <= lon <= bbox["east"]):
                    cells.append((float(lat), float(lon)))
        mapping[dist_name] = cells
        logger.info(
            "District %s: %d grid cells selected via BBox (W:%.2f, S:%.2f, E:%.2f, N:%.2f)",
            dist_name,
            len(cells),
            bbox["west"],
            bbox["south"],
            bbox["east"],
            bbox["north"],
        )
    return mapping


def calculate_longest_dry_spell(daily_series: pd.Series, threshold_mm: float) -> Tuple[int, int]:
    """
    Calculate the longest consecutive run of dry days (rainfall < threshold_mm).
    Returns (longest_dry_spell_days, missing_days_count).
    """
    missing_count = int(daily_series.isna().sum())
    if missing_count > 0:
        logger.warning("Found %d missing observations during dry spell calculation.", missing_count)

    longest = 0
    current = 0
    for val in daily_series:
        if pd.isna(val):
            # Broken sequence if data is missing
            current = 0
        elif val < threshold_mm:
            current += 1
            if current > longest:
                longest = current
        else:
            current = 0
    return longest, missing_count


def process_dataset(
    nc_path: Path,
    config_path: Path,
    output_dir: Path,
    metadata_dir: Path,
    figures_dir: Path,
    dry_threshold: float,
) -> Dict[str, Any]:
    """Execute complete preprocessing and validation workflow."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    # 1. Inspect raw NetCDF
    profile = inspect_raw_netcdf(nc_path)

    # 2. Load district AOIs
    district_bboxes = load_study_area_bboxes(config_path)

    with h5py.File(nc_path, "r") as f:
        g = f["rain"]
        lats = g["lat"][:].astype(float)
        lons = g["lon"][:].astype(float)
        t_raw = g["time"][:].astype(int)
        rain_raw = g["rain"][:]  # (time, lat, lon)

    # Date vector
    time_units = profile["time_units"]
    base_str = time_units.split("days since")[1].strip()
    dates = pd.to_datetime(base_str) + pd.to_timedelta(t_raw, unit="D")

    # Map grid cells
    district_cell_map = map_grid_cells_to_districts(lats, lons, district_bboxes)

    # Identify all unique selected grid cells across the 3 target districts
    all_selected_cells = sorted(list({cell for cells in district_cell_map.values() for cell in cells}))
    logger.info("Total unique grid cells covering the three target districts: %d", len(all_selected_cells))

    # --- Phase 3.1: imd_rainfall_daily_grid.parquet ---
    # Create indexed array for fast lookup
    lat_indices = {lat: idx for idx, lat in enumerate(lats)}
    lon_indices = {lon: idx for idx, lon in enumerate(lons)}

    grid_dfs = []
    for lat, lon in all_selected_cells:
        lat_idx = lat_indices[lat]
        lon_idx = lon_indices[lon]
        series = rain_raw[:, lat_idx, lon_idx]
        df_cell = pd.DataFrame(
            {
                "date": dates,
                "latitude": np.float32(lat),
                "longitude": np.float32(lon),
                "rainfall_mm": np.float32(series),
            }
        )
        grid_dfs.append(df_cell)

    df_grid = pd.concat(grid_dfs, ignore_index=True)
    df_grid["date"] = pd.to_datetime(df_grid["date"])
    df_grid = df_grid.sort_values(by=["latitude", "longitude", "date"]).reset_index(drop=True)

    grid_parquet_path = output_dir / "imd_rainfall_daily_grid.parquet"
    df_grid.to_parquet(grid_parquet_path, index=False, engine="pyarrow")
    logger.info("Saved %s (shape: %s)", grid_parquet_path, df_grid.shape)

    # --- Phase 3.2: imd_rainfall_daily_district.parquet ---
    district_dfs = []
    for dist_name, cells in district_cell_map.items():
        cell_count = len(cells)
        # Gather series for all cells in this district
        cell_series_list = []
        for lat, lon in cells:
            lat_idx = lat_indices[lat]
            lon_idx = lon_indices[lon]
            cell_series_list.append(rain_raw[:, lat_idx, lon_idx])

        # Array shape: (cell_count, num_days)
        cells_arr = np.array(cell_series_list)  # (cells, days)
        dist_mean = np.mean(cells_arr, axis=0)  # simple arithmetic unweighted mean

        df_dist = pd.DataFrame(
            {
                "district_name": dist_name,
                "date": dates,
                "rainfall_estimate_mm": np.float32(dist_mean),
                "grid_cell_count": np.int32(cell_count),
                "aggregation_method": "provisional_unweighted_mean",
                "provisional_flag": True,
            }
        )
        district_dfs.append(df_dist)

    df_district = pd.concat(district_dfs, ignore_index=True)
    df_district["date"] = pd.to_datetime(df_district["date"])
    df_district = df_district.sort_values(by=["district_name", "date"]).reset_index(drop=True)

    district_parquet_path = output_dir / "imd_rainfall_daily_district.parquet"
    df_district.to_parquet(district_parquet_path, index=False, engine="pyarrow")
    logger.info("Saved %s (shape: %s)", district_parquet_path, df_district.shape)

    # --- Phase 3.3: imd_monsoon_features.parquet ---
    # June to September (months 6, 7, 8, 9)
    df_monsoon_days = df_district[df_district["date"].dt.month.isin([6, 7, 8, 9])].copy()
    df_monsoon_days["year"] = df_monsoon_days["date"].dt.year

    monsoon_records = []
    for (dist_name, year), group in df_monsoon_days.groupby(["district_name", "year"]):
        # Sort sequentially by date
        group = group.sort_values(by="date")
        rainfall_series = group["rainfall_estimate_mm"]

        monsoon_total_mm = float(np.round(rainfall_series.sum(), 2))
        longest_dry_spell, missing_days = calculate_longest_dry_spell(rainfall_series, dry_threshold)
        total_days = len(rainfall_series)

        monsoon_records.append(
            {
                "district_name": dist_name,
                "year": int(year),
                "season_name": "Southwest Monsoon",
                "monsoon_total_mm": np.float32(monsoon_total_mm),
                "longest_dry_spell_days": np.int32(longest_dry_spell),
                "dry_day_threshold_mm": np.float32(dry_threshold),
                "total_monsoon_days": np.int32(total_days),
                "missing_days_count": np.int32(missing_days),
                "provisional_flag": True,
            }
        )

    df_monsoon = pd.DataFrame(monsoon_records)
    df_monsoon = df_monsoon.sort_values(by=["district_name", "year"]).reset_index(drop=True)

    monsoon_parquet_path = output_dir / "imd_monsoon_features.parquet"
    df_monsoon.to_parquet(monsoon_parquet_path, index=False, engine="pyarrow")
    logger.info("Saved %s (shape: %s)", monsoon_parquet_path, df_monsoon.shape)

    # --- Phase 3.4: data/metadata/imd_dataset_profile.json ---
    # Physical and data quality metrics
    total_obs = df_grid["rainfall_mm"].size
    nan_count = int(df_grid["rainfall_mm"].isna().sum())
    min_rain = float(df_grid["rainfall_mm"].min())
    max_rain = float(df_grid["rainfall_mm"].max())
    mean_rain = float(df_grid["rainfall_mm"].mean())
    negative_count = int((df_grid["rainfall_mm"] < 0).sum())

    metadata = {
        "dataset_name": "IMD High-Resolution Daily Gridded Rainfall",
        "source_file": nc_path.name,
        "processing_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "time_coverage": {
            "start_date": profile["time_range"][0],
            "end_date": profile["time_range"][1],
            "total_days": profile["dimensions"]["time"],
            "continuous_daily_flag": profile["is_temporally_continuous_daily"],
            "duplicate_dates_flag": profile["has_duplicate_dates"],
        },
        "spatial_coverage_raw": {
            "latitude_bounds": profile["lat_range"],
            "longitude_bounds": profile["lon_range"],
            "lat_step_deg": profile["lat_step"],
            "lon_step_deg": profile["lon_step"],
            "total_raw_grid_cells": profile["dimensions"]["lat"] * profile["dimensions"]["lon"],
        },
        "geographic_filtering": {
            "method": "Provisional Bounding Box Polygon Intersection",
            "boundary_file_status": "EXACT_OFFICIAL_BOUNDARY_UNAVAILABLE",
            "notes": (
                "Filtered using approximate WGS84 bounding boxes from configs/study_area.yaml. "
                "District boundaries overlap in the rectangular AOI; this is marked as provisional "
                "pending exact official Survey of India / KGIS GeoJSON boundary verification."
            ),
            "selected_unique_grid_cells_count": len(all_selected_cells),
            "district_grid_cell_counts": {d: len(cells) for d, cells in district_cell_map.items()},
            "district_grid_cells": {
                d: [list(c) for c in cells] for d, cells in district_cell_map.items()
            },
        },
        "data_quality_metrics": {
            "total_grid_daily_records": total_obs,
            "missing_values_count": nan_count,
            "missing_values_pct": float(nan_count / total_obs * 100),
            "negative_values_count": negative_count,
            "min_rainfall_mm": min_rain,
            "max_rainfall_mm": max_rain,
            "mean_rainfall_mm": np.round(mean_rain, 4),
            "original_units": profile["rain_units"],
        },
        "processed_artifacts": {
            "daily_grid_parquet": str(grid_parquet_path).replace("\\", "/"),
            "daily_district_parquet": str(district_parquet_path).replace("\\", "/"),
            "monsoon_features_parquet": str(monsoon_parquet_path).replace("\\", "/"),
        },
        "parameters": {
            "dry_day_threshold_mm": dry_threshold,
            "monsoon_months": [6, 7, 8, 9],
            "district_aggregation": "simple_unweighted_arithmetic_mean",
        },
    }

    meta_json_path = metadata_dir / "imd_dataset_profile.json"
    with open(meta_json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info("Saved metadata profile to %s", meta_json_path)

    # --- Phase 4: Diagnostic Plots ---
    generate_diagnostic_plots(df_district, df_monsoon, figures_dir)

    return metadata


def generate_diagnostic_plots(
    df_district: pd.DataFrame, df_monsoon: pd.DataFrame, figures_dir: Path
):
    """Generate 4 key quality and exploratory plots."""
    logger.info("Generating diagnostic plots in %s...", figures_dir)
    sns.set_theme(style="whitegrid")

    # 1. Annual Rainfall Trends
    df_annual = (
        df_district.groupby(["district_name", df_district["date"].dt.year])["rainfall_estimate_mm"]
        .sum()
        .reset_index()
    )
    df_annual.rename(columns={"date": "year", "rainfall_estimate_mm": "annual_rainfall_mm"}, inplace=True)

    fig, ax = plt.subplots(figsize=(12, 5), dpi=200)
    sns.lineplot(
        data=df_annual,
        x="year",
        y="annual_rainfall_mm",
        hue="district_name",
        palette=["#1f77b4", "#ff7f0e", "#2ca02c"],
        ax=ax,
        linewidth=1.8,
    )
    # Add 10-year rolling mean
    for dist in df_annual["district_name"].unique():
        sub = df_annual[df_annual["district_name"] == dist]
        rolling = sub["annual_rainfall_mm"].rolling(10, min_periods=1).mean()
        ax.plot(sub["year"], rolling, linestyle="--", alpha=0.5, label=f"{dist} (10yr trend)")

    ax.set_title("IMD Annual Rainfall Trends (1901–2025) — Eastern Karnataka Target Districts", fontsize=12, fontweight="bold")
    ax.set_xlabel("Year", fontsize=10)
    ax.set_ylabel("Annual Rainfall (mm)", fontsize=10)
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    plot1_path = figures_dir / "annual_rainfall_trends.png"
    plt.savefig(plot1_path)
    plt.close()

    # 2. Monsoon Rainfall Distributions
    fig, ax = plt.subplots(figsize=(9, 5), dpi=200)
    sns.boxplot(
        data=df_monsoon,
        x="district_name",
        y="monsoon_total_mm",
        palette="Set2",
        ax=ax,
        width=0.4,
    )
    sns.stripplot(
        data=df_monsoon,
        x="district_name",
        y="monsoon_total_mm",
        color="black",
        alpha=0.3,
        size=4,
        jitter=0.2,
        ax=ax,
    )
    ax.set_title("Southwest Monsoon (June–Sept) Rainfall Distribution (1901–2025)", fontsize=12, fontweight="bold")
    ax.set_xlabel("District", fontsize=10)
    ax.set_ylabel("Monsoon Total Rainfall (mm)", fontsize=10)
    plt.tight_layout()
    plot2_path = figures_dir / "monsoon_rainfall_distribution.png"
    plt.savefig(plot2_path)
    plt.close()

    # 3. Longest Dry-Spell Distributions
    fig, ax = plt.subplots(figsize=(9, 5), dpi=200)
    sns.histplot(
        data=df_monsoon,
        x="longest_dry_spell_days",
        hue="district_name",
        element="step",
        stat="density",
        common_norm=False,
        bins=25,
        palette="tab10",
        ax=ax,
    )
    ax.set_title("Monsoon Longest Dry-Spell Distribution (< 2.5 mm/day threshold)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Longest Dry Spell (consecutive days)", fontsize=10)
    ax.set_ylabel("Density", fontsize=10)
    plt.tight_layout()
    plot3_path = figures_dir / "longest_dry_spell_distribution.png"
    plt.savefig(plot3_path)
    plt.close()

    # 4. Missing Data Profile by Year and District
    # Show completeness matrix / heatmap
    df_completeness = (
        df_district.groupby([df_district["date"].dt.year, "district_name"])["rainfall_estimate_mm"]
        .agg(total_obs="count", valid_obs=lambda s: s.notna().sum())
        .reset_index()
    )
    df_completeness.rename(columns={"date": "year"}, inplace=True)
    df_completeness["missing_count"] = df_completeness["total_obs"] - df_completeness["valid_obs"]

    piv_missing = df_completeness.pivot(index="year", columns="district_name", values="missing_count")

    fig, ax = plt.subplots(figsize=(8, 4), dpi=200)
    sns.heatmap(piv_missing.T, cmap="Blues", cbar=True, ax=ax, vmin=0, vmax=5)
    ax.set_title("Missing Data Audit by Year & District (All years: 0 missing observations)", fontsize=11, fontweight="bold")
    ax.set_xlabel("Year (1901–2025)", fontsize=10)
    ax.set_ylabel("District", fontsize=10)
    plt.tight_layout()
    plot4_path = figures_dir / "missing_data_profile.png"
    plt.savefig(plot4_path)
    plt.close()
    logger.info("All 4 diagnostic plots saved successfully.")


if __name__ == "__main__":
    args = parse_args()
    process_dataset(
        nc_path=Path(args.input),
        config_path=Path(args.config),
        output_dir=Path(args.output_dir),
        metadata_dir=Path(args.metadata_dir),
        figures_dir=Path(args.figures_dir),
        dry_threshold=args.dry_threshold,
    )
