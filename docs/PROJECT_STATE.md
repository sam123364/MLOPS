# Project State & Progress Log

## Current Status: Phase 1 (Data Acquisition & Ingestion)

### Accomplished in this session:
1. **IMD Gridded Historical Rainfall Dataset Preprocessing (`imdweb_nSbYRBgK.nc`):**
   - Located and inspected raw NetCDF file (`imdweb_nSbYRBgK.nc`, 29.58 MB) with zero overwrites.
   - Profiled raw dataset: 45,626 continuous daily observations (1901-01-31 to 2025-12-31, 125 years) at 0.25° grid across 8 latitudes × 10 longitudes (80 raw cells).
   - Audited data quality: 0 missing values (0.0%), 0 negative values, 100% daily temporal continuity.
   - Integrated provisional GeoJSON boundary: [`data/raw/boundaries/approx_kolar_chikkaballapur_tumakuru_aoi.geojson`](file:///C:/Users/user/Desktop/MLOPS/data/raw/boundaries/approx_kolar_chikkaballapur_tumakuru_aoi.geojson).
     - Verified: This is an approximate combined bounding envelope (`Lon: [76.70°, 78.95°]`, `Lat: [12.40°, 14.25°]`), NOT official district boundaries.
     - Documented: Does not delineate individual district borders; all district estimates retain `provisional_flag = true`.
     - Filtered IMD grid: Selected **72 cells** intersecting the study-area polygon.
     - Mapped district provisional bboxes: Kolar (16 cells), Chikkaballapur (6 cells), Tumakuru (20 cells).
   - Produced 3 Parquet datasets and 1 JSON profile:
     - `data/processed/imd_rainfall_daily_grid.parquet` (3,285,072 records: 72 cells × 45,626 days)
     - `data/processed/imd_rainfall_daily_district.parquet` (136,878 records)
     - `data/processed/imd_monsoon_features.parquet` (375 records: June-Sept totals and longest dry spells at 2.5 mm threshold)
     - `data/metadata/imd_dataset_profile.json`
   - Generated 4 diagnostic figures in `reports/figures/` (annual trends, monsoon distributions, dry-spell histograms, missingness audit).
   - Authored readable data-quality report: [`reports/imd_rainfall_data_quality_report.md`](file:///C:/Users/user/Desktop/MLOPS/reports/imd_rainfall_data_quality_report.md).
   - Added automated tests in [`tests/unit/test_imd_processing.py`](file:///C:/Users/user/Desktop/MLOPS/tests/unit/test_imd_processing.py) (all 12 tests passing).
   - Integrated `process_imd_rainfall` stage with GeoJSON dependency into `dvc.yaml`.

2. **KSNDMC Rainfall Data Consolidation & Schemas:**
   - Consolidated 2021-2025 multi-year KSNDMC data into master CSVs and Excel.
   - Formal schemas in `configs/rainfall_schemas.yaml` and validation in `src/utils/schemas.py`.

3. **KSNDMC Dataset Quality Audit & Verification Completed:**
   - Conducted full audit across all sheets in `karnataka_rainfall_master_clean.xlsx` and raw files in `data/raw/ksndmc/`.
   - **Verification-Only Follow-Up Confirmed:**
     - **Origin of 2025 Anomaly:** Verified verbatim in raw file `data/raw/ksndmc/ka_dist_rainfall_2025.csv` (line 20) and master sheet `2025_District_Seasonal` (row 20). It was present in the source bulletin, NOT introduced by data cleaning or preprocessing.
     - **Independent Recalculation:** Evaluated `|(Pre-Monsoon + SWM + NEM) - Annual|` for all 31 districts in 2025 without assuming shift patterns. Exactly 19 districts (rows 6–22 and row 24) have large discrepancies (>10 mm, up to 4,396 mm). Exactly 12 districts match within 10 mm (Bagalkote, Ballari, Belagavi, Bengaluru Rural, Raichur, Shivamogga, Tumakuru, Udupi, Uttara Kannada, Vijayanagar, Vijayapura, Yadgir).
     - **Flagged Records Reconciliation:** Verified exact reconciliation of all 22 records in `data/processed/ksndmc_flagged_records.csv`:
       - 19 records: 2025 seasonal-vs-annual mismatch districts (`COLUMN_SHIFT_ANOMALY`).
       - 1 record: 2024 Pre-Monsoon header unit mislabel (`(%)` instead of `mm`).
       - 1 record: Missing calendar year 2023 (`MISSING_YEAR_GAP`).
       - 1 record: 2021 Vijayanagar district creation (Ballari bifurcation).
     - **Data Provenance Cleaned:** Explicitly updated `docs/data_sources.md` to designate CHIRPS, CartoDEM, SoilGrids, NASA POWER, and Sentinel-2 as *Proposed Future Sources / Not Yet Acquired*. Only IMD and KSNDMC are verified acquired sources.
     - **Readiness Assessed:** 2021 Hobli data verified mathematically consistent (100% seasonal sums equal annual actual). Annual district series (2021, 2022, 2024, 2025) verified internally, but 2023 is missing and 2025 seasonal splits remain unusable without authoritative bulletin correction.
   - Preserved all raw values with zero modifications or synthetic corrections.
   - Updated test suite in `tests/unit/test_ksndmc_audit.py` to validate audit calculations; full unit test suite passing (59/59 tests passing).

4. **Data Provider Handoff & Blocker Resolutions (Workstream B):**
   - **BLOCKER 1 RESOLVED — Official District Boundaries Acquired & Integrated:**
     - Acquired authoritative administrative boundary dataset: [`data/raw/boundaries/karnataka_districts_official.geojson`](file:///C:/Users/user/Desktop/MLOPS/data/raw/boundaries/karnataka_districts_official.geojson) (Census 2011 / LGD vector data in EPSG:4326).
     - Extracted 3 target districts into [`data/raw/boundaries/kolar_chikkaballapur_tumakuru_districts.geojson`](file:///C:/Users/user/Desktop/MLOPS/data/raw/boundaries/kolar_chikkaballapur_tumakuru_districts.geojson) with verified valid Polygon / MultiPolygon geometries.
     - Implemented reproducible intersection pipeline in [`src/data/process_official_district_rainfall.py`](file:///C:/Users/user/Desktop/MLOPS/src/data/process_official_district_rainfall.py).
     - Calculated exact spatial intersections with the IMD 0.25° grid:
       - **Chikkaballapur:** 5 centroid cells, 15 total overlapping cells.
       - **Kolar:** 6 centroid cells, 12 total overlapping cells.
       - **Tumakuru:** 10 centroid cells, 23 total overlapping cells.
     - Generated official area-weighted datasets (`provisional_flag = false`):
       - `data/processed/imd_rainfall_daily_district_official.parquet` (136,878 rows)
       - `data/processed/imd_monsoon_features_official.parquet` (375 rows)
       - `data/metadata/official_district_boundary_profile.json` (normalized area weights summing to 1.0)
     - Preserved all provisional bounding-box datasets intact for comparative analysis.

   - **BLOCKER 2 RESOLVED — KSNDMC 2025 Seasonal Anomaly Verified via Official Bulletins:**
     - Downloaded official KSNDMC seasonal bulletins directly from `https://ksndmc.org/en/Reports/Seasonal`:
       - `data/raw/ksndmc/SouthWest Monsoon Seasonal Report_2025.pdf`
       - `data/raw/ksndmc/NorthEast Monsoon Seasonal Report_2025.pdf`
     - Verified verbatim from the official bulletin table (`Stream 44`):
       - **Kolar SWM 2025 Official:** Normal = **399 mm**, Actual = **382 mm** (-4% departure).
       - **Chikkaballapura SWM 2025 Official:** Normal = **416 mm**, Actual = **401 mm** (-4% departure).
       - **Tumakuru SWM 2025 Official:** Normal = **358 mm**, Actual = **374 mm** (+5% departure).
       - **Kodagu SWM 2025 Official:** Normal = **2,188 mm**, Actual = **2,176 mm** (-1% departure).
     - Confirmed that the 2,176 mm value reported under Kolar in `ka_dist_rainfall_2025.csv` was an artifact of CSV column misalignment where Kolar was mapped to Kodagu's row.
     - **Downstream Safeguard Implemented:** Original raw CSVs remain completely unmodified. Flagged 2025 seasonal rows are programmatically excluded from downstream seasonal model validation (proven by unit tests).

   - **Full Test Suite Status:** 65/65 unit tests passing across all suites (`tests/unit/`).

### Next Steps & Remaining Work:
1. Extract Northeast Monsoon (Oct-Dec) features for Kolar and Chikkaballapur from IMD grid.
2. Build Phase 1 baseline rainfall models (climatology, empirical distribution, persistence, quantile regression) with time-based splits.
3. Ingest CartoDEM / SRTM elevation data into `data/raw/dem/`.
4. Ingest SoilGrids texture fractions for SCS Curve Number hydrologic soil group classification.
