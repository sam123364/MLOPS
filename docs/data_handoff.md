# Data Provider Handoff Documentation

This document serves as the formal data handoff specification from **Workstream B (Data Acquisition & Preprocessing)** to downstream teammates (**Workstream C: Exploration & Features**, and **Workstream D: Baselines & Evaluation**).

---

## 1. Quick Reference: Dataset Paths & Roles

| Dataset | Local File Path | Recommended Downstream Use | Format | Records |
|---|---|---|---|---|
| **Primary Grid Daily Rainfall** | [`data/processed/imd_rainfall_daily_grid.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_rainfall_daily_grid.parquet) | **RECOMMENDED FOR MODELING & FEATURE ENGINEERING:** Cell-level daily time-series, spatial interpolation, lag features, and point/farm catchment analysis. | Parquet | 3,285,072 |
| **Official District Daily Rainfall (Area-Weighted)** | [`data/processed/imd_rainfall_daily_district_official.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_rainfall_daily_district_official.parquet) | **RECOMMENDED FOR DISTRICT-LEVEL EDA & VALIDATION:** Area-weighted daily means based on official Survey of India / Census 2011 district polygons (`provisional_flag = false`). | Parquet | 136,878 |
| **Official Monsoon Seasonal Features** | [`data/processed/imd_monsoon_features_official.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_monsoon_features_official.parquet) | **RECOMMENDED FOR SEASONAL BASELINES:** Annual June–Sept totals and longest dry spells at 2.5 mm threshold using official area-weighting (`provisional_flag = false`). | Parquet | 375 |
| **Provisional District Daily Rainfall (BBox)** | [`data/processed/imd_rainfall_daily_district.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_rainfall_daily_district.parquet) | **Retained for comparison:** Unweighted arithmetic means across bounding-box grid cells (`provisional_flag = true`). | Parquet | 136,878 |
| **Provisional Monsoon Seasonal Features** | [`data/processed/imd_monsoon_features.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_monsoon_features.parquet) | **Retained for comparison:** Baseline targets and seasonal features from bounding-box AOI (`provisional_flag = true`). | Parquet | 375 |
| **Official District Boundaries** | [`data/raw/boundaries/kolar_chikkaballapur_tumakuru_districts.geojson`](file:///C:/Users/user/Desktop/MLOPS/data/raw/boundaries/kolar_chikkaballapur_tumakuru_districts.geojson) | Official administrative polygons (Survey of India / Census 2011 in EPSG:4326). | GeoJSON | 3 features |
| **Dataset Metadata Profile** | [`data/metadata/imd_dataset_profile.json`](file:///C:/Users/user/Desktop/MLOPS/data/metadata/imd_dataset_profile.json) | Complete provenance, cell coordinate mappings, bounding boxes, and processing parameters. | JSON | — |
| **Official Boundary Intersection Profile** | [`data/metadata/official_district_boundary_profile.json`](file:///C:/Users/user/Desktop/MLOPS/data/metadata/official_district_boundary_profile.json) | Cell centroid counts, total overlapping cells, and normalized polygon area weights. | JSON | — |
| **KSNDMC Clean Master** | [`data/processed/rainfall/karnataka_rainfall_master_clean.xlsx`](file:///C:/Users/user/Desktop/MLOPS/data/processed/rainfall/karnataka_rainfall_master_clean.xlsx) | **Sanity check & secondary benchmark.** Multi-sheet administrative comparison (annual & hobli). **Do not train models on this.** | Excel | 5 sheets |
| **KSNDMC Flagged Anomalies** | [`data/processed/ksndmc_flagged_records.csv`](file:///C:/Users/user/Desktop/MLOPS/data/processed/ksndmc_flagged_records.csv) | Full register of 22 flagged administrative data quality issues (including the 19 shifted 2025 districts). | CSV | 22 rows |
| **Official KSNDMC 2025 Seasonal Reports** | `data/raw/ksndmc/SouthWest%20Monsoon%20Seasonal%20Report_2025.pdf` | Direct official PDF bulletins from KSNDMC confirming official 2025 values (Kolar SWM = 382 mm). | PDF | 2 files |

---

## 2. Verified Measured Specifications

All values below were verified by inspecting actual files on disk, not assumed.

### 2.1 IMD Daily Grid Dataset (`imd_rainfall_daily_grid.parquet`)
- **Source:** India Meteorological Department (IMD), High-Resolution Gridded Daily Rainfall (`imdweb_nSbYRBgK.nc`).
- **Spatial Coverage:** 72 discrete 0.25° grid points intersecting the study-area bounding polygon.
  - Latitudes: `[12.5, 12.75, 13.0, 13.25, 13.5, 13.75, 14.0, 14.25]` (8 latitudes)
  - Longitudes: `[76.75, 77.0, 77.25, 77.5, 77.75, 78.0, 78.25, 78.5, 78.75]` (9 longitudes)
- **Temporal Coverage:** 1901-01-31 to 2025-12-31 (45,626 consecutive days; exactly 125 years).
- **Physical Units:** `mm/day` (variable `rainfall_mm`).
- **Schema & Data Types:**
  - `date`: `datetime64[ns]`
  - `latitude`: `float32`
  - `longitude`: `float32`
  - `rainfall_mm`: `float32`
- **Quality Metrics:**
  - Total Rows: **3,285,072** ($72\text{ cells} \times 45,626\text{ days}$)
  - Missing Values: **0 (0.0%)**
  - Negative Values: **0**
  - Duplicate Keys (`date`, `latitude`, `longitude`): **0**
  - Range: `[0.0, 289.89] mm/day`, Mean: `2.0122 mm/day`

### 2.2 IMD Daily District Dataset (`imd_rainfall_daily_district.parquet`)
- **Target Districts:** Kolar, Chikkaballapur, Tumakuru (45,626 days per district).
- **Schema & Data Types:**
  - `district_name`: `object` (`Kolar`, `Chikkaballapur`, `Tumakuru`)
  - `date`: `datetime64[ns]`
  - `rainfall_estimate_mm`: `float32`
  - `grid_cell_count`: `int32` (Kolar: 16 cells, Chikkaballapur: 6 cells, Tumakuru: 20 cells)
  - `aggregation_method`: `object` (`"provisional_unweighted_mean"`)
  - `provisional_flag`: `bool` (All records: `True`)
- **Quality Metrics:**
  - Total Rows: **136,878** ($3\text{ districts} \times 45,626\text{ days}$)
  - Missing Values: **0 (0.0%)**
  - Duplicate Keys (`district_name`, `date`): **0**
  - Range: `[0.0, 128.32] mm/day`, Mean: `1.9088 mm/day`

### 2.3 IMD Monsoon Seasonal Features (`imd_monsoon_features.parquet`)
- **Definition:** Southwest Monsoon season (June 1 to September 30 = 122 days per year) for each year from 1901 to 2025.
- **Dry-Day Threshold:** Configured at $< 2.5\text{ mm/day}$ per IMD standard definition.
- **Schema & Data Types:**
  - `district_name`: `object`
  - `year`: `int64` (1901 to 2025, 125 years per district)
  - `season_name`: `object` (`"Southwest Monsoon"`)
  - `monsoon_total_mm`: `float32` (Range: `[145.02, 787.52] mm`, Mean: `362.71 mm`)
  - `longest_dry_spell_days`: `int32` (Range: `[7, 58] days`, Mean: `22.50 days`)
  - `dry_day_threshold_mm`: `float32` (`2.5`)
  - `total_monsoon_days`: `int32` (`122`)
  - `missing_days_count`: `int32` (`0` across all years)
  - `provisional_flag`: `bool` (`True`)
- **Quality Metrics:**
  - Total Rows: **375** ($3\text{ districts} \times 125\text{ years}$)
  - Missing Values: **0 (0.0%)**
  - Duplicate Keys (`district_name`, `year`): **0**

---

## 3. Critical Limitations & Caveats

> [!WARNING]
> ### 1. District Boundaries are PROVISIONAL (Not Official Statistics)
> The file [`data/raw/boundaries/approx_kolar_chikkaballapur_tumakuru_aoi.geojson`](file:///C:/Users/user/Desktop/MLOPS/data/raw/boundaries/approx_kolar_chikkaballapur_tumakuru_aoi.geojson) is an **approximate combined bounding envelope**, NOT official district administrative boundaries.
> - Grid-to-district mappings rely on bounding boxes (`configs/study_area.yaml`).
> - Estimates are unweighted arithmetic means across cells.
> - **Do NOT cite or publish these estimates as official district rainfall records.**
> - All district records carry `provisional_flag = True`.
> - Exact district area-weighting is blocked pending official Survey of India / KGIS polygons.

> [!CAUTION]
> ### 2. KSNDMC 2025 Seasonal Records Must NOT Be Used for Training
> - In `data/raw/ksndmc/ka_dist_rainfall_2025.csv`, rows 6–22 and 24 exhibit an uncorrected **source-level column shift** between seasonal columns and district names.
> - Kolar lists Kodagu's seasonal values (SWM actual 2,176 mm vs reported annual 927 mm).
> - All 22 affected records are logged in [`data/processed/ksndmc_flagged_records.csv`](file:///C:/Users/user/Desktop/MLOPS/data/processed/ksndmc_flagged_records.csv).
> - **Never silently correct or realign these numbers.**
> - KSNDMC annual totals are usable for macro comparisons, but 2025 seasonal splits remain invalid until an official corrigendum is provided.

> [!NOTE]
> ### 3. Absence of Year 2023 in KSNDMC
> The KSNDMC archive lacks the year 2023 (available years: 2021, 2022, 2024, 2025). Do not attempt continuous time-series modeling on KSNDMC.

---

## 4. Recommendations for Downstream Workstreams

### For Samiksha (Workstream C: EDA & Feature Engineering)
1. **Primary Data Source:** Use [`data/processed/imd_rainfall_daily_grid.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_rainfall_daily_grid.parquet).
2. **Feature Engineering Targets:**
   - Pre-monsoon rainfall (March–May total).
   - Southwest monsoon rainfall (June–September total).
   - Northeast monsoon rainfall (October–December total) — especially vital for Kolar and Chikkaballapur.
   - Longest dry spell (consecutive days $< 2.5\text{ mm}$).
   - Multi-year rolling averages (e.g., 3-year and 5-year precipitation index).
3. **Data Leakage Safeguard:** Ensure all lag features and rolling windows use strictly preceding years ($< t$), never the year being predicted ($t$).

### For Samith (Workstream D: Baselines & Evaluation)
1. **Baseline Targets:** Use [`data/processed/imd_monsoon_features.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_monsoon_features.parquet) for quick benchmark testing.
2. **Required Baselines:**
   - Long-term mean (climatology)
   - Empirical quantile distribution
   - 1-year lag persistence
   - Linear / Quantile Regression
3. **Splitting Constraint:** Always use expanding-window time-based splits (e.g., train 1901–1990, evaluate 1991–2025). **Never use random k-fold cross-validation on time-series.**

---

## 5. Pipeline Reproduction Command

The complete preprocessing and feature generation pipeline can be re-executed from the raw NetCDF file using:

```powershell
python -m src.data.process_imd_rainfall --input imdweb_nSbYRBgK.nc --geojson data/raw/boundaries/approx_kolar_chikkaballapur_tumakuru_aoi.geojson --config configs/study_area.yaml --output-dir data/processed --metadata-dir data/metadata --figures-dir reports/figures --dry-threshold 2.5
```

Or via DVC:
```powershell
dvc repro process_imd_rainfall
```

---

## 6. Verification Test Command & Results

Run the full data acquisition, schema validation, and audit test suite:

```powershell
python -m pytest tests/unit/test_imd_processing.py tests/unit/test_rainfall_schemas.py tests/unit/test_ksndmc_audit.py -v
```

**Measured Test Result:**
```
======================= 25 passed, 13 warnings in 6.83s =======================
```
All 25 tests passed with zero failures.
