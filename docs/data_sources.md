# Dataset Sources & Provenance Registry

This document records the verified data sources, temporal/spatial resolutions, physical units, known quality limitations, and intended use in the MLOps Rainwater Yield Estimation project.

---

## 1. IMD Gridded Historical Rainfall (High Resolution)

| Property | Verified Value |
|---|---|
| **Source Agency** | India Meteorological Department (IMD), Pune |
| **Local File** | `imdweb_nSbYRBgK.nc` (Processed into `data/processed/imd_rainfall_*.parquet`) |
| **Data Format** | NetCDF-4 / HDF5 (CF-1.7 compliant) |
| **Variable Name** | `rain` (`Rainfall`) |
| **Physical Units** | `mm/day` |
| **Spatial Resolution** | 0.25° × 0.25° (~27.5 km × 27.5 km grid cell) |
| **Spatial Extent** | Lat: 12.50°N – 14.25°N (8 points); Lon: 76.75°E – 79.00°E (10 points); 80 raw grid cells |
| **Temporal Range** | 1901-01-31 to 2025-12-31 (45,626 consecutive days; 125 full years) |
| **Temporal Continuity** | 100% daily continuity; zero missing days; zero negative values |
| **Intended Role** | **Primary training & backtesting dataset** for probabilistic seasonal rainfall modeling and dry-spell distributions. |
| **Limitations & Caveats** | 0.25° resolution smooths local convective storms; cannot be treated as a point farm observation without downscaling or local validation. |

---

## 2. KSNDMC Karnataka Rainfall Records (OpenCity / KSNDMC)

| Property | Verified Value |
|---|---|
| **Source Agency** | Karnataka State Natural Disaster Monitoring Centre (KSNDMC) / OpenCity portal |
| **Local Files** | `data/raw/ksndmc/` (Raw CSVs and Official PDFs) and `data/processed/rainfall/karnataka_rainfall_master_clean.xlsx` |
| **Official PDF Bulletins** | `SouthWest Monsoon Seasonal Report_2025.pdf` & `NorthEast Monsoon Seasonal Report_2025.pdf` (Downloaded directly from `https://ksndmc.org/en/Reports/Seasonal`) |
| **Data Format** | Tabular CSV / Multi-sheet Excel / Official PDF Bulletins |
| **Temporal Resolution** | Annual and Seasonal aggregates only (Pre-Monsoon, SWM, NEM, Annual); **no daily series** |
| **Years Available** | **2021, 2022, 2024, 2025** (Note: Year **2023 is missing**) |
| **Spatial Resolution** | Administrative: District (31 districts), Taluk (~227 taluks), Hobli (~850 hoblis) |
| **Physical Units** | Rainfall in `mm`; departures in `%` |
| **Intended Role** | **Independent validation & sanity check benchmark** for IMD grid aggregates at district and taluk scales. |
| **Official Anomaly Verification** |
| 1. **Column Shift Anomaly (2025):** | In `ka_dist_rainfall_2025.csv`, rows 6–22 and 24 suffered a CSV column misalignment where Kolar was erroneously assigned Kodagu's actual (2,176 mm). Inspection of official KSNDMC PDF bulletin (`Stream 44`) reveals official values: **Kolar SWM Normal = 399 mm, Actual = 382 mm (-4% departure)**; **Chikkaballapura SWM Normal = 416 mm, Actual = 401 mm (-4% departure)**; **Tumakuru SWM Normal = 358 mm, Actual = 374 mm (+5% departure)**. |
| 2. **Downstream Policy:** | Unrealigned raw rows remain strictly flagged in `data/processed/ksndmc_flagged_records.csv` and are programmatically excluded from seasonal model validation. |

---

## 3. Official Administrative Boundaries (Survey of India / Census 2011)

| Property | Verified Value |
|---|---|
| **Source Agency** | Survey of India / Census of India (harmonized GIS administrative vector dataset) |
| **Local File** | `data/raw/boundaries/kolar_chikkaballapur_tumakuru_districts.geojson` (Extracted from `karnataka_districts_official.geojson`) |
| **Spatial Vintage** | Census 2011 / LGD (30 districts in Karnataka) |
| **CRS** | EPSG:4326 (WGS84 geographic lat/lon) |
| **Geometry Types** | Polygon (Kolar, Chikkaballapura), MultiPolygon (Tumakuru) |
| **Grid Intersection** | Chikkaballapur: 5 centroid / 15 overlapping cells; Kolar: 6 centroid / 12 overlapping cells; Tumakuru: 10 centroid / 23 overlapping cells |
| **Usage** | Produces `data/processed/imd_rainfall_daily_district_official.parquet` via polygon area-weighted averaging (`provisional_flag = false`). |

---

## 3. Comparison: IMD vs. KSNDMC

| Dimension | IMD Gridded Dataset | KSNDMC Tabular Dataset |
|---|---|---|
| **Nature of Data** | Objective spatial interpolation from rain-gauge network | Station-aggregated administrative reports (hobli/taluk rain gauges) |
| **Temporal Resolution** | Daily (continuous time-series) | Seasonal and annual totals only |
| **Historical Depth** | 125 continuous years (1901–2025) | 4 fragmented recent years (2021, 2022, 2024, 2025) |
| **Spatial Geometry** | Fixed 0.25° regular latitude/longitude grid | Irregular administrative boundaries (District / Taluk / Hobli) |
| **Missing Values** | 0 (complete coverage across all dates) | Complete within recorded years, but 2023 entirely missing |
| **Machine Learning Readiness** | Ready for probabilistic seasonal modeling | **Not ready for training;** suitable solely as an independent test/sanity check after resolving the 2025 column-shift anomaly |

---

## 4. Proposed Future Sources (Not Yet Acquired / Not Ingested)

The following datasets are planned for future project phases (Phases 2–4) but **have not yet been downloaded, ingested, or verified** in the repository:

- **CHIRPS Daily (0.05°):** *Status: Not acquired.* Planned alternative high-resolution satellite-gauge rainfall for spatial comparison against IMD.
- **CartoDEM 30m / SRTM GeoTIFF:** *Status: Not acquired.* Planned elevation and slope derivation for SCS Curve Number slope adjustments and runoff direction.
- **SoilGrids 250m:** *Status: Not acquired.* Planned sand, silt, and clay fraction retrieval via REST API to infer USDA Hydrologic Soil Groups (A, B, C, D).
- **NASA POWER:** *Status: Not acquired.* Planned daily temperature, solar radiation, relative humidity, and wind speed for FAO-56 Penman-Monteith reference evapotranspiration (ET₀).
- **Copernicus Sentinel-2:** *Status: Not acquired.* Planned multi-spectral imagery for NDVI-based land-use and land-cover (LULC) classification.
