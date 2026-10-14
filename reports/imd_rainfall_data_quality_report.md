# IMD Historical Rainfall Data-Quality & Inspection Report

**Project:** AI-Powered Rainwater Harvesting Decision Support (Eastern Karnataka)  
**Study Districts:** Kolar, Chikkaballapur, Tumakuru  
**Dataset Examined:** `imdweb_nSbYRBgK.nc`  
**Processing Timestamp:** 2026-10-14  
**Pipeline Module:** [`src/data/process_imd_rainfall.py`](file:///C:/Users/user/Desktop/MLOPS/src/data/process_imd_rainfall.py)

---

## 1. Executive Summary

A raw high-resolution gridded daily rainfall dataset (`imdweb_nSbYRBgK.nc`) provided in NetCDF-4 format was inspected, physically validated, and processed. The dataset covers **125 continuous years** (1901-01-31 to 2025-12-31, exactly 45,626 daily time steps) at **0.25° × 0.25° spatial resolution** over Southern India. 

All 3,650,080 spatial-temporal data points were audited:
- **Missing values:** 0 (0.00%)
- **Negative values:** 0
- **Daily temporal continuity:** 100% continuous without gaps or duplicate timestamps
- **Plausibility:** Maximum daily rainfall observed was 289.89 mm/day; mean daily rainfall was 2.07 mm/day.

---

## 2. Raw Dataset Profiling (Phase 1)

| Attribute | Value / Specification |
|---|---|
| **Source File** | `imdweb_nSbYRBgK.nc` (29.58 MB) |
| **Data Format** | NetCDF-4 / HDF5 (CF-1.7 compliant) |
| **Variable Name** | `rain` (long name: `Rainfall`) |
| **Units** | `mm/day` |
| **Dimensions** | `time`: 45,626 \| `lat`: 8 \| `lon`: 10 |
| **Total Grid Cells** | 80 cells (raw extent) |
| **Latitude Range** | 12.50°N to 14.25°N (step: 0.25°) |
| **Longitude Range** | 76.75°E to 79.00°E (step: 0.25°) |
| **Time Units** | `days since 1901-01-01` |
| **Start Date** | `1901-01-31` |
| **End Date** | `2025-12-31` |
| **Spatial Reference** | WGS 84 (`EPSG:4326`) |

---

## 3. Geographic Filtering & Boundary Status (Phase 2)

> [!WARNING]
> **Boundary File Status: Approximate Combined AOI GeoJSON Integrated (NOT Official District Boundaries)**
> An approximate boundary file was provided at [`data/raw/boundaries/approx_kolar_chikkaballapur_tumakuru_aoi.geojson`](file:///C:/Users/user/Desktop/MLOPS/data/raw/boundaries/approx_kolar_chikkaballapur_tumakuru_aoi.geojson).
> - **GeoJSON Type:** `FeatureCollection` containing a single `Polygon` (5 vertices forming a rectangular bounding envelope: `Lon: [76.70°, 78.95°]`, `Lat: [12.40°, 14.25°]`).
> - **Embedded Property Note:** *"Approximate bounding polygon only; not official district boundaries. It includes surrounding areas. Use for rough IMD grid selection, then spatially filter with official boundaries for analysis."*
> - **Crucial Limitation:** This GeoJSON does **not** delineate individual district borders between Kolar, Chikkaballapur, and Tumakuru. It was used strictly as a provisional study-area filter. All district aggregates retain `provisional_flag = true`.

### Selected IMD Grid Cells (0.25° resolution):
1. **Total Selected by Study-Area GeoJSON Polygon:** **72 cells** (out of 80 raw cells).
   - Only 8 cells at longitude 79.00° fall outside the eastern extent (78.95°).
   - All 72 cells are preserved in `data/processed/imd_rainfall_daily_grid.parquet`.

2. **District-Level Provisional Subsets (from Bounding Boxes within AOI):**
   - **Kolar District** (BBox: W: 77.70°, S: 12.90°, E: 78.60°, N: 13.90°): **16 cells**
   - **Chikkaballapur District** (BBox: W: 77.55°, S: 13.20°, E: 78.20°, N: 13.90°): **6 cells**
   - **Tumakuru District** (BBox: W: 76.60°, S: 12.90°, E: 77.60°, N: 14.10°): **20 cells**
   - **Union of District BBoxes:** 36 unique cells (6 cells overlap between Kolar and Chikkaballapur).

**Total Unique Selected Grid Cells:** 36 cells across the three target districts.

### Caveats & Limitations:
- **Spatial Overlap:** Because Chikkaballapur was historically carved out of northern Kolar in 2007, rectangular bounding boxes overlap between the two districts. Cells `(13.25, 77.75)`, `(13.25, 78.0)`, `(13.5, 77.75)`, `(13.5, 78.0)`, `(13.75, 77.75)`, `(13.75, 78.0)` fall in both bounding boxes.
- **Scale Discrepancy:** A 0.25° IMD grid cell covers approximately **27.5 km × 27.5 km (~750 km²)**. A single grid cell cannot be treated as a farm-level rainfall observation. It represents a spatially smoothed areal average.
- **Aggregation:** District estimates are currently computed as a **provisional unweighted arithmetic mean** across all cells intersecting the bounding box. When exact district shapefiles are added, area-weighted averaging should replace this method.

---

## 4. Processed Artifacts (Phase 3)

The pipeline produced three analysis-ready Parquet files and one metadata document:

1. **[`data/processed/imd_rainfall_daily_grid.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_rainfall_daily_grid.parquet)**:
   - **Rows:** 1,642,536 (36 grid cells × 45,626 days)
   - **Columns:** `date`, `latitude`, `longitude`, `rainfall_mm`
   - **Format:** PyArrow Parquet, Snappy compressed (6.6 MB)

2. **[`data/processed/imd_rainfall_daily_district.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_rainfall_daily_district.parquet)**:
   - **Rows:** 136,878 (3 districts × 45,626 days)
   - **Columns:** `district_name`, `date`, `rainfall_estimate_mm`, `grid_cell_count`, `aggregation_method`, `provisional_flag`
   - **Format:** PyArrow Parquet (1.0 MB)

3. **[`data/processed/imd_monsoon_features.parquet`](file:///C:/Users/user/Desktop/MLOPS/data/processed/imd_monsoon_features.parquet)**:
   - **Rows:** 375 (3 districts × 125 monsoon seasons from 1901 to 2025)
   - **Columns:** `district_name`, `year`, `season_name`, `monsoon_total_mm`, `longest_dry_spell_days`, `dry_day_threshold_mm`, `total_monsoon_days`, `missing_days_count`, `provisional_flag`
   - **Methodology:** June 1 to September 30 (122 days/season). Dry day defined as `< 2.5 mm/day`.

4. **[`data/metadata/imd_dataset_profile.json`](file:///C:/Users/user/Desktop/MLOPS/data/metadata/imd_dataset_profile.json)**:
   - Complete machine-readable audit trail, timestamps, and parameters.

---

## 5. Diagnostic Figures (Phase 4)

The diagnostic plots are saved in `reports/figures/`:
1. `reports/figures/annual_rainfall_trends.png`: Annual total rainfall series (1901–2025) with 10-year rolling decadal climate trends.
2. `reports/figures/monsoon_rainfall_distribution.png`: Box plots and jittered scatter showing the Southwest Monsoon total distribution by district.
3. `reports/figures/longest_dry_spell_distribution.png`: Density histogram of the longest consecutive dry spell (< 2.5 mm/day) during the monsoon.
4. `reports/figures/missing_data_profile.png`: Heatmap demonstrating complete zero-missing observations across all 125 years.

---

## 6. How to Reproduce the Pipeline (Phase 5)

Run the reproducible pipeline script from the root workspace:

```bash
# Direct Python execution:
python -m src.data.process_imd_rainfall \
  --input imdweb_nSbYRBgK.nc \
  --config configs/study_area.yaml \
  --output-dir data/processed \
  --metadata-dir data/metadata \
  --figures-dir reports/figures \
  --dry-threshold 2.5

# Or execute unit tests:
pytest tests/unit/test_imd_processing.py -v
```

---

## 7. Unresolved Issues & Next Steps Before ML Training

1. **Obtain Official Administrative Boundaries (GeoJSON):**  
   Download Karnataka district boundaries (from Survey of India or KGIS) into `data/raw/boundaries/karnataka_districts.geojson` to compute exact polygon intersection percentages and transition from unweighted mean to area-weighted mean.
2. **Northeast Monsoon Feature Extraction:**  
   Currently, features cover the Southwest Monsoon (Jun–Sep). In Kolar and Chikkaballapur, the Northeast Monsoon (Oct–Dec) contributes 25–35% of annual rainfall and should be added as a distinct seasonal feature set before training.
3. **Climatological Baseline Benchmarking:**  
   As specified in `CLAUDE.md`, baseline models (climatology, 30-year rolling mean, persistence) must be trained and evaluated using time-based splits (e.g. train on 1901–2010, test on 2011–2025) before running ML models.
