# Project State & Progress Log

## Current Status: Phase 1 (Data Acquisition & Ingestion)

### Accomplished in this session:
1. **KSNDMC Rainfall Data Consolidation:**
   - Ingested multi-year Karnataka rainfall records provided by user (covering 2021, 2022, 2024, and 2025).
   - Cleaned duplicate copy files from `data/raw/ksndmc/`.
   - Processed and merged all tables into a unified master Excel file:
     [`data/raw/rainfall/ksndmc/karnataka_rainfall_master.xlsx`](file:///C:/Users/user/Desktop/MLOPS/data/raw/rainfall/ksndmc/karnataka_rainfall_master.xlsx)
   - Built a **`District_MultiYear_Summary`** sheet comparing District rainfall across 2021, 2022, 2024, and 2025.
   - Structured year-by-year sheets:
     - `2025_District_Seasonal`
     - `2024_District_Seasonal`
     - `2024_Hobli_Taluk_Annual` (1,122 rows covering all Hoblis/Taluks)
     - `2022_District_Annual`
     - `2021_District_Annual`
     - `2021_Hobli_Taluk_Seasonal` (1,134 rows covering all Hoblis/Taluks with seasonal splits)

### Next Steps:
1. Add CartoDEM GeoTIFF to `data/raw/dem/cartodem/`.
2. Run IMD binary ingestion script (`python -m src.ingestion.imd_rainfall --year 2022`).
3. Run SoilGrids fetch script (`python -m src.ingestion.soilgrids_fetch`).
4. Run NASA POWER fetch script (`python -m src.ingestion.nasa_power_fetch --year 2022`).
