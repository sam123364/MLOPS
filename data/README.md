# Project Data Catalog & Directory Structure

This document outlines the organization, schemas, and purpose of all directories and files within the `data/` directory.

---

## 1. Directory Layout Overview

```
data/
├── raw/                      # Immutable raw source datasets (read-only)
│   ├── boundaries/           # Official & provisional GIS boundaries (GeoJSON)
│   ├── ksndmc/               # Original downloaded KSNDMC tabular CSVs & official PDF bulletins
│   ├── rainfall/             # Master raw rainfall files
│   │   └── ksndmc/           # Original consolidated raw Excel workbook
│   ├── dem/                  # Elevation & slope rasters (CartoDEM / SRTM) [Phase 2]
│   ├── soil/                 # Soil texture rasters & tables (SoilGrids) [Phase 2]
│   └── sentinel2/            # Multi-spectral satellite rasters (LULC) [Phase 3]
│
├── processed/                # Curated, validated, analysis-ready datasets (tracked in Git)
│   ├── imd_rainfall_*.parquet # Primary IMD gridded & district time-series (1901–2025)
│   ├── ksndmc_flagged_records.csv # Audit flags & anomaly register (22 records)
│   └── rainfall/             # Clean standardized KSNDMC tables (District & Hobli)
│
├── metadata/                 # Machine-readable provenance profiles & spatial mappings
│   ├── imd_dataset_profile.json
│   └── official_district_boundary_profile.json
│
├── interim/                  # Temporary staging for intermediate pipeline steps
└── external/                 # Ancillary reference lookups (e.g., USDA CN tables, FAO-56 Kc)
```

---

## 2. Directory Contents & Specifications

### 2.1 `data/raw/` — Raw Ingestion Sources
All files here are strictly preserved in their original state. **Never edit raw files in place.**

- **`data/raw/boundaries/`**
  - [`kolar_chikkaballapur_tumakuru_districts.geojson`](file:///C:/Users/user/Desktop/MLOPS/data/raw/boundaries/kolar_chikkaballapur_tumakuru_districts.geojson) (1.77 MB): Target 3-district official administrative polygons in WGS84 (`EPSG:4326`).
  - [`karnataka_districts_official.geojson`](file:///C:/Users/user/Desktop/MLOPS/data/raw/boundaries/karnataka_districts_official.geojson) (6.37 MB): Full state 30-district polygon boundary layer (Census 2011 / Survey of India / LGD).
  - [`karnataka_districts_provenance.json`](file:///C:/Users/user/Desktop/MLOPS/data/raw/boundaries/karnataka_districts_provenance.json): Metadata, authority attribution, and vintage documentation.
  - [`approx_kolar_chikkaballapur_tumakuru_aoi.geojson`](file:///C:/Users/user/Desktop/MLOPS/data/raw/boundaries/approx_kolar_chikkaballapur_tumakuru_aoi.geojson) (0.9 KB): Provisional bounding box polygon (used for baseline comparison).
- **`data/raw/ksndmc/`**
  - Downloaded annual/seasonal raw CSV files (`ka_dist_rainfall_2025.csv`, `0ec5ad8d...csv`, etc.).
  - Official seasonal PDF reports: `SouthWest_Monsoon_Seasonal_Report_2025.pdf` and `NorthEast_Monsoon_Seasonal_Report_2025.pdf`.
- **`data/raw/rainfall/ksndmc/`**
  - `karnataka_rainfall_master.xlsx`: Raw uncleaned multi-sheet workbook containing original tables.
- **Root Raw IMD File:**
  - `imdweb_nSbYRBgK.nc` (28.22 MB): India Meteorological Department 0.25° gridded daily NetCDF-4 dataset (1901–2025, 45,626 days).

---

### 2.2 `data/processed/` — Curated Analysis-Ready Datasets
These are the files that downstream teammates (**Workstream C: Features** and **Workstream D: Modeling**) should consume.

| File Path | Format | Records | Purpose & Key Features |
|---|---|---|---|
| [`imd_rainfall_daily_grid.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_rainfall_daily_grid.parquet) | Parquet | 3,285,072 | **PRIMARY MODELING DATASET:** 72 IMD grid cells $\times$ 45,626 days (`rainfall_mm`). |
| [`imd_rainfall_daily_district_official.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_rainfall_daily_district_official.parquet) | Parquet | 136,878 | **OFFICIAL DISTRICT DAILY (14 cols):** Area-weighted daily rainfall with antecedent $P_5$, dynamic AMC classes (`AMC-I/II/III`), and rainy/heavy event flags. |
| [`imd_monsoon_features_official.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_monsoon_features_official.parquet) | Parquet | 375 | **SEASONAL TARGETS & EXTREMES (18 cols):** 125 years of SWM totals, longest dry spells, peak 1-day/3-day storms, heavy rain days ($\ge 25\text{mm}$, $\ge 50\text{mm}$), NEM totals, and PCI. *(See `reports/feature_engineering_log.md`)* |
| [`imd_rainfall_daily_district.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_rainfall_daily_district.parquet) | Parquet | 136,878 | Bounding-box daily averages with $P_5$, AMC, and threshold flags (retained baseline). |
| [`imd_monsoon_features.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_monsoon_features.parquet) | Parquet | 375 | Bounding-box seasonal features with peak storm metrics and PCI (retained baseline). |
| [`ksndmc_flagged_records.csv`](file:///C:/Users/user/Desktop/MLOPS/data/processed/ksndmc_flagged_records.csv) | CSV | 22 | Data quality issue register (19 shifted districts, unit mislabels, boundary shifts). |

- **`data/processed/rainfall/`** (Clean KSNDMC Tables):
  - `karnataka_rainfall_master_clean.xlsx`: Clean multi-sheet workbook.
  - `karnataka_district_annual_rainfall_2021_2025_long.csv`: Long-format annual records.
  - `karnataka_district_annual_rainfall_comparison_wide.csv`: Wide-format annual comparison across districts.
  - `karnataka_district_seasonal_rainfall_2021_2025.csv`: Seasonal totals per district.
  - `karnataka_hobli_rainfall_2021_clean.csv`: Sub-district hobli-level seasonal totals.
  - `karnataka_hobli_rainfall_2024_clean.csv`: 2024 hobli-level rainfall totals.

---

### 2.3 `data/metadata/` — Provenance & Spatial Parameters
- [`imd_dataset_profile.json`](file:///C:/Users/user/Desktop/MLOPS/data/metadata/imd_dataset_profile.json): Full profile of the raw IMD NetCDF (extents, timestamps, missingness audit, 72 selected cell lat/lon list).
- [`official_district_boundary_profile.json`](file:///C:/Users/user/Desktop/MLOPS/data/metadata/official_district_boundary_profile.json): Official polygon weights, centroid counts, and overlapping cell fractions.

---

## 3. Maintenance Rules for Teammates
1. **Never commit raw NetCDF/TIFF rasters directly to Git:** Large rasters must be handled via DVC.
2. **Processed Parquet & Clean CSVs:** Processed files are curated, compact (~15 MB total), and pushed to Git so teammates can pull and immediately begin feature engineering without running raw ingestion.
3. **Data Immutability:** Any transformations must output to `data/interim/` or `data/processed/`, never altering files in `data/raw/`.
