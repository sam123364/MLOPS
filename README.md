# Rainwater Yield Estimation — Eastern Karnataka MLOps Project

> **Study area:** Kolar district (configurable: Chikkaballapur, Bengaluru Rural, Tumakuru)
> **Team size:** 4 members | **Stack:** Python 3.10+, DVC, MLflow

---

## Project Overview

An end-to-end MLOps pipeline for estimating rainwater yield potential and identifying suitable rainwater harvesting (RWH) locations on agricultural land in the Eastern Karnataka dry belt, using:

| Pillar | Method |
|---|---|
| **Rainfall** | IMD 0.25° daily gridded + CHIRPS 0.05° cross-validation |
| **Runoff** | USDA SCS-CN method (CN lookup × Hydrologic Soil Group × LULC) |
| **Terrain** | CartoDEM 30m → slope, flow accumulation, drainage lines |
| **Soil** | SoilGrids texture → HSG (A/B/C/D) |
| **Land cover** | Sentinel-2 NDVI/NDWI → LULC classification |
| **Evapotranspiration** | FAO-56 Penman-Monteith via NASA POWER |
| **MLOps** | DVC pipeline versioning + MLflow experiment tracking |

---

## Quick Start

### 1. Set up the environment

```bash
# Clone and install
git clone <repo-url>
cd rainwater-yield-kolar

python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
```

### 2. Initialise DVC

```bash
dvc init
git add .dvc .gitignore
git commit -m "chore: initialise DVC"

# Optional: configure a remote (shared team storage)
dvc remote add -d myremote s3://your-bucket/dvc-cache
```

### 3. Run the full pipeline

```bash
# Run all stages end-to-end (will skip cached stages)
dvc repro

# Run a specific stage only
dvc repro train
```

### 4. View experiment results

```bash
# Open MLflow UI
mlflow ui --backend-store-uri mlruns

# Compare DVC metrics
dvc metrics show
dvc plots show
```

---

## Project Structure

```
MLOPS/
├── configs/
│   ├── study_area.yaml       # District bounding boxes (Kolar default)
│   ├── data_sources.yaml     # All dataset URLs, directories, parameters
│   └── params.yaml           # SCS-CN table, HSG thresholds, ML hyperparams
│
├── src/
│   ├── ingestion/
│   │   ├── imd_rainfall.py   # IMD binary rainfall via imdlib
│   │   ├── chirps_rainfall.py# CHIRPS daily GeoTIFFs from UCSB server
│   │   ├── soilgrids_fetch.py# SoilGrids REST API point sampling
│   │   └── nasa_power_fetch.py# NASA POWER daily met data
│   ├── preprocessing/
│   │   ├── terrain_analysis.py # Slope, aspect, flow accumulation (pysheds)
│   │   └── soil_hsg.py        # SoilGrids fractions → USDA HSG (A/B/C/D)
│   ├── features/
│   │   ├── curve_number.py    # SCS-CN lookup, runoff formula, yield (m³)
│   │   └── et_fao56.py        # FAO-56 Penman-Monteith ET0
│   ├── models/
│   │   ├── train.py           # RandomForest + MLflow tracking
│   │   └── evaluate.py        # Evaluation, predictions CSV, MLflow logging
│   └── utils/
│       └── config.py          # YAML loader, bbox helpers, path resolution
│
├── scripts/
│   └── build_features.py     # Assembles final feature matrix CSV
│
├── tests/
│   └── unit/
│       ├── test_curve_number.py
│       ├── test_et_fao56.py
│       └── test_soil_hsg.py
│
├── dvc.yaml                   # 9-stage DVC pipeline
├── configs/params.yaml        # Tracked by DVC for experiment reproducibility
└── pyproject.toml             # All dependencies
```

---

## DVC Pipeline Stages

```
ingest_imd ──┐
ingest_chirps─┤
ingest_soilgrids ──► soil_hsg ──┐
ingest_nasa_power               │
                                ├──► build_features ──► train ──► evaluate
terrain_analysis ───────────────┘
```

| Stage | Input | Output |
|---|---|---|
| `ingest_imd` | IMD FTP | `data/raw/rainfall/imd/` |
| `ingest_chirps` | UCSB HTTP | `data/raw/rainfall/chirps/` |
| `ingest_soilgrids` | ISRIC REST API | `data/raw/soil/soilgrids_samples.jsonl` |
| `ingest_nasa_power` | NASA POWER API | `data/raw/climate/` |
| `terrain_analysis` | CartoDEM GeoTIFF | slope, aspect, flow accumulation rasters |
| `soil_hsg` | soilgrids_samples.jsonl | `data/interim/soil/hsg_points.csv` |
| `build_features` | All interim data | `data/processed/features.csv` |
| `train` | features.csv | model.joblib + MLflow run |
| `evaluate` | features.csv + model | predictions.csv + metrics.json |

---

## Dataset Access Notes

| Dataset | Access | Notes |
|---|---|---|
| IMD Rainfall | [imdpune.gov.in](https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html) | Use `imdlib` to download; requires year-by-year download |
| CHIRPS | UCSB public HTTP (no auth) | Automated in `chirps_rainfall.py` |
| KSNDMC | [data.opencity.in](https://data.opencity.in/) | Manual download; CSV format |
| CartoDEM | [Bhuvan NRSC](https://bhuvan-app3.nrsc.gov.in/data/download/) | Free Bhuvan account required |
| SRTM | [USGS EarthExplorer](https://earthexplorer.usgs.gov/) | Login required; fallback for CartoDEM |
| SoilGrids | REST API (automated) | Rate-limited; `soilgrids_fetch.py` adds delays |
| Sentinel-2 | [Copernicus Dataspace](https://dataspace.copernicus.eu/) | Free account; use `eodag` for automation |
| NASA POWER | [power.larc.nasa.gov](https://power.larc.nasa.gov/) | No auth needed; automated |

---

## Team Roles (Suggested)

| Member | Focus area | Key files |
|---|---|---|
| **A — Data Engineer** | Ingestion pipelines, DVC setup, remote storage | `src/ingestion/`, `dvc.yaml`, cloud remote config |
| **B — Hydrology/GIS** | DEM processing, SCS-CN, terrain analysis | `src/preprocessing/`, `src/features/curve_number.py` |
| **C — ML Engineer** | Feature building, model training, spatial CV | `scripts/build_features.py`, `src/models/` |
| **D — MLOps/Platform** | MLflow, CI/CD, testing, Sentinel-2 LULC | `tests/`, `.github/`, `src/features/et_fao56.py` |

---

## Expanding to Other Districts

Edit `configs/study_area.yaml`:

```yaml
active_district: "chikkaballapur"   # change from "kolar"
```

All stages automatically use the new bounding box. Re-run with `dvc repro`.

---

## Running Tests

```bash
pytest tests/unit/ -v
pytest tests/unit/test_curve_number.py -v --tb=short
```

---

## Key References

- NRCS NEH Part 630, Ch. 9 — Curve Number method
- Allen et al. (1998) — FAO-56 Penman-Monteith ET0
- USDA HSG classification — NRCS Part 630, Ch. 7
- imdlib documentation — [github.com/imdlib](https://github.com/iamsaswata/imdlib)
- CHIRPS data — [chc.ucsb.edu](https://www.chc.ucsb.edu/data/chirps)
