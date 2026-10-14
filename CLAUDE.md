# CLAUDE.md — Agent Instructions (Read at the start of every session)

Read this file fully at the start of every session.
Then read docs/PROJECT_STATE.md (current status) before doing any work.
Update docs/PROJECT_STATE.md at the end of every session.

## 1. Project context

**What:** A decision-support system that estimates how much rainwater a farm can harvest and what storage size would help, for farmers in Karnataka's eastern dry belt (Kolar, Chikkaballapur, Tumakuru districts).

**Why it exists:** Team course project for an MLOps course at RV College of Engineering (RVCE), Bengaluru. The project must follow the full MLOps lifecycle at every step (data versioning, experiment tracking, testing, CI/CD, deployment, monitoring, retraining).

**Team (4):** Samarth, Sambhav, Samiksha, Samith. Humans create accounts, credentials and logins. The agent writes code.

**Current status:** Phase 1 is being implemented. See docs/PROJECT_STATE.md for the up-to-date status.

## 2. Problem statement

Farmers in Karnataka's eastern dry belt (Kolar, Chikkaballapur, Tumakuru) depend on erratic rainfall and declining groundwater. Many want to harvest rainwater but cannot tell how much water their land will actually yield in a normal year versus a dry year, how much storage is worth building given their available space, or whether the stored water will cover their crop's needs through the dry period. Without these estimates, farmers either over-invest in storage that never fills or under-invest and run short. Existing guidance is generic and does not account for an individual farm's size, location, soil, crop or space constraints.

## 3. Proposed solution

A location-aware decision-support system that estimates harvestable rainwater and recommends storage for an individual farm. The farmer provides a map location, plot boundary, crop and sowing month, irrigation method and available storage space. The system then:

1. Retrieves local conditions automatically: historical rainfall (IMD gridded data, calibrated with KSNDMC records), terrain and slope (DEM), and soil type.
2. Models rainfall probabilistically, producing normal-year and dry-year scenarios and dry-spell lengths, using statistical and ML methods on the historical record.
3. Estimates runoff and harvestable volume from the plot's catchment using the SCS Curve Number method adapted to local soil and land use.
4. Computes crop water demand using FAO-56 evapotranspiration and crop coefficients, adjusted for the chosen irrigation method.
5. Runs a monthly water balance to show supply, storage and demand over the season, and identify when and by how much a shortfall appears.
6. Recommends a storage size that fits the farmer's space limit and closes as much of the dry-period gap as possible.
7. Supports "what if" changes (e.g. switch to drip irrigation, smaller tank).

Results are shown in simple, local-language terms (litres, acres, guntas; 1 acre = 40 guntas) with uncertainty stated plainly.

**Out of scope for this version:** exact pond placement; regions outside the eastern dry belt.

## 4. Key decisions already made (do not reopen without asking the team)

1. Single problem chosen: rainwater yield estimation.
2. Region: eastern dry belt only. Build the code location-agnostic (coordinates in, data fetched for that point).
3. ML component = rainfall. The ML model produces probabilistic seasonal rainfall and dry-spell estimates. Runoff, crop demand and water balance are deterministic physical/agronomic modules.
4. Do not promise a forecast of next year's rain. Present normal-year and dry-year scenarios (percentiles) and dry-spell statistics.
5. Always keep a baseline. Evaluate with time-based splits only, never random splits.
6. Simulating retraining: replay history (train to year N, "release" year N+1, monitor drift, retrain, repeat).
7. Uncertainty is part of the output. Carry low/high choices through the pipeline and show a range.

## 5. Pipeline design

### 5.1 Farmer inputs
Location · plot boundary/area · crop and sowing month · irrigation method · available storage space.

### 5.2 Farmer outputs
- Harvestable water in a normal year and in a dry year (1-in-5).
- Crop water need over the season.
- Monthly gap between supply and demand.
- Storage size recommendation.
- Share of crop demand that rainwater can cover.

### 5.3 Modules

| Module | Method | Notes |
|---|---|---|
| Rainfall scenarios | Statistical + ML on IMD (calibrated with KSNDMC) | The ML piece. |
| Runoff | SCS Curve Number | Weakest link; show a range. |
| Crop demand | FAO-56 (ET0 × Kc), adjusted for irrigation method | |
| Water balance | Monthly step simulation | |
| Storage recommendation | Smallest storage closing dry-period gap | |

### 5.4 SCS Curve Number

S = 25400/CN - 254; Ia = 0.2*S; Q = (P-Ia)² / (P-Ia+S) for P > Ia, else Q = 0.

Volume: 1 mm over 1 m² = 1 litre; 1 acre ≈ 4,047 m².

**Sanity check values (use in unit tests):**
- CN 75, P=50 mm → Q ≈ 9 mm
- CN 85, P=50 mm → Q ≈ 20 mm
- CN 85, P=100 mm → Q ≈ 61 mm

## 6. Data sources

See docs/data_sources.md. Never invent a dataset URL. Verify links before relying on them.

| Dataset | Purpose | Link | Caveats |
|---|---|---|---|
| IMD gridded daily rainfall (0.25°, 1901–present) | Main rainfall record | https://imdpune.gov.in | Binary .grd files; ~25 km grid |
| KSNDMC rainfall (taluk/hobli) | Local calibration | https://data.opencity.in/dataset/karnataka-annual-rainfall-districts-taluks-and-hoblis | Mostly annual; ask for daily |
| CHIRPS daily (0.05°) | Finer rainfall comparison | GEE: UCSB-CHG/CHIRPS/DAILY | Via Earth Engine |
| NASA POWER daily | Temperature/radiation for ET0 | https://power.larc.nasa.gov/ | Starts 01/01/1981 |
| SRTM DEM (~30 m) | Slope, catchment | https://earthexplorer.usgs.gov | Free account needed |
| CartoDEM (ISRO) | Indian alternative DEM | https://bhuvan-app3.nrsc.gov.in/data | Free Bhuvan registration |
| Sentinel-2 | Land-use classification | https://dataspace.copernicus.eu/ | Free Copernicus account |
| SoilGrids 250 m | Soil texture → HSG | https://soilgrids.org | Global model, weaker in India |
| NBSS&LUP / Sujala | Finer local soils | https://krishi.icar.gov.in | Coverage for target districts TBD |
| FAO-56 | ET0 method and Kc tables | https://www.fao.org/3/x0490E/x0490e00.htm | |
| USDA NEH Part 630 Ch. 9 | CN tables | https://directives.nrcs.usda.gov | US-derived; calibrate |

## 7. MLOps toolchain

| Stage | Tools |
|---|---|
| Planning | GitHub Issues/Projects, Markdown docs |
| Ingestion | Python: xarray, rasterio, geopandas, pandas |
| Validation | Pandera |
| Data versioning | DVC (remote: Google Drive or DagsHub) |
| Pipelines | DVC pipelines (dvc.yaml) |
| Modelling | scikit-learn, statsmodels, XGBoost/LightGBM |
| Tracking/registry | MLflow (local mlruns first) |
| Testing/quality | pytest, ruff, pre-commit |
| CI/CD | GitHub Actions |
| Serving | FastAPI, Docker |
| Frontend | Streamlit or Gradio with folium |
| Monitoring | Evidently AI (drift) |

**Phase 1 uses only:** Git, DVC, MLflow, Pandera, pytest, ruff.

## 8. Phase 1 scope

**Deliverables:** dataset acquisition; data exploration; feature engineering; baseline models; Git repository; DVC dataset versioning; MLflow experiment tracking; initial model evaluation.

**Phase 1 prediction task:** For IMD grid cells covering Kolar, Chikkaballapur and Tumakuru, estimate seasonal rainfall total and longest dry spell for the next season, as a distribution (quantiles). Start with SW monsoon (June–September).

**Baselines every later model must beat:**
- (a) Long-term mean (climatology)
- (b) Empirical distribution of past seasons
- (c) Persistence (last year's value)
- (d) Linear or quantile regression on engineered features

**Features (reproducible script, not a notebook):** lagged seasonal totals, pre-monsoon (Mar–May) rainfall, rain-day counts, longest dry spell, rolling multi-year means. Write tests that prove no feature uses information from the year being predicted.

**Evaluation:** expanding-window time-based backtest. Metrics: MAE for point estimate; pinball loss and prediction-interval coverage for quantiles; skill score versus climatology. Log everything to MLflow with the git commit and the DVC data hash.

### Work split

| Member | Workstream | Phase 1 tasks |
|---|---|---|
| Samarth | A. Repo and MLOps infrastructure | Git, DVC, MLflow, CI skeleton, params.yaml |
| Sambhav | B. Data acquisition | IMD + NASA POWER scripts, Pandera validation |
| Samiksha | C. Exploration and features | EDA, feature engineering, leakage tests |
| Samith | D. Baselines and evaluation | Metrics, backtest harness, baselines, MLflow logging |

## 9. Repository layout (target)

```
.
├── CLAUDE.md
├── README.md
├── params.yaml
├── dvc.yaml
├── data/raw/
├── data/processed/
├── src/
│   ├── ingest/
│   ├── features/
│   ├── models/
│   └── evaluation/
├── tests/
├── notebooks/
└── docs/
    ├── data_sources.md
    ├── PROJECT_STATE.md
    └── decisions_log.md
```

## 10. Rules for the agent

1. **Secrets:** never read, print or commit .env or any credential.
2. Ask before installing packages, deleting files, force-pushing, or changing decisions in section 4.
3. Never invent data, dataset URLs, metrics or results.
4. **Time-based splits only.** Check for leakage in every feature.
5. Write tests with code; run them before committing.
6. Commit small and often, with clear messages.
7. Configuration in params.yaml, pipelines in dvc.yaml, every run logged to MLflow with git commit and DVC data hash.
8. Style: Python, type hints where practical, ruff clean, short docstrings.
9. **Honesty in reporting:** if the model does not beat the baseline, say so.
10. At the end of each session, update docs/PROJECT_STATE.md.

## 11. Open questions for the team

1. Which season(s) to model first (SW monsoon only, or also NE monsoon)?
2. Does KSNDMC provide daily hobli data on request?
3. Does Sujala/NBSS soil coverage exist for our three districts?
4. How to model evaporation and seepage losses from storage?
5. Which crops to support first in the crop water demand module?
6. Which DVC remote (Google Drive or DagsHub)?
