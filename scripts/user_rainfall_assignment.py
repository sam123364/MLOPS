from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(".")
OUT = ROOT / "reports" / "user_assignment"
OUT.mkdir(parents=True, exist_ok=True)

DAILY_FILE = ROOT / "data/processed/imd_rainfall_daily_district_official.parquet"
MONSOON_FILE = ROOT / "data/processed/imd_monsoon_features_official.parquet"

DISTRICTS = ["Kolar", "Tumakuru", "Chikkaballapur"]

# 1. Load the existing datasets
daily = pd.read_parquet(DAILY_FILE)
monsoon = pd.read_parquet(MONSOON_FILE)

daily["date"] = pd.to_datetime(daily["date"])
daily = daily[daily["district_name"].isin(DISTRICTS)].copy()
daily = daily.sort_values(["district_name", "date"]).reset_index(drop=True)
daily["year"] = daily["date"].dt.year
daily["month"] = daily["date"].dt.month

monsoon = monsoon[monsoon["district_name"].isin(DISTRICTS)].copy()

# 2. Metadata and missing-value reports
metadata_rows = []
missing_rows = []

for dataset_name, df in [
    ("daily_rainfall", daily),
    ("monsoon_features", monsoon),
]:
    for col in df.columns:
        missing = int(df[col].isna().sum())
        metadata_rows.append({
            "dataset": dataset_name,
            "rows": len(df),
            "columns": len(df.columns),
            "column": col,
            "dtype": str(df[col].dtype),
            "unique_values": int(df[col].nunique(dropna=True)),
            "missing_count": missing,
            "missing_percent": round(100 * missing / len(df), 2) if len(df) else 0,
        })
        missing_rows.append({
            "dataset": dataset_name,
            "column": col,
            "missing_count": missing,
            "missing_percent": round(100 * missing / len(df), 2) if len(df) else 0,
            "handling_decision": (
                "Investigate and reconstruct if possible"
                if missing else "No missing values detected"
            ),
        })

pd.DataFrame(metadata_rows).to_csv(OUT / "metadata_report.csv", index=False)
pd.DataFrame(missing_rows).to_csv(OUT / "missing_values_report.csv", index=False)

# 3. Create daily rainfall features
rain = pd.to_numeric(daily["rainfall_estimate_mm"], errors="coerce")

daily["rainy_day"] = (rain >= 2.5).astype("int8")
daily["heavy_rain_day"] = (rain >= 25).astype("int8")
daily["very_heavy_rain_day"] = (rain >= 50).astype("int8")

# Calendar coverage: only complete years will be used for annual comparisons
coverage = daily.groupby(["district_name", "year"]).agg(
    observed_days=("date", "nunique"),
    first_date=("date", "min"),
    last_date=("date", "max"),
).reset_index()

coverage["expected_days"] = np.where(
    pd.to_datetime(coverage["year"].astype(str) + "-12-31").dt.is_leap_year,
    366, 365
)
coverage["complete_calendar_year"] = (
    (coverage["observed_days"] == coverage["expected_days"])
    & (coverage["first_date"].dt.month == 1)
    & (coverage["first_date"].dt.day == 1)
    & (coverage["last_date"].dt.month == 12)
    & (coverage["last_date"].dt.day == 31)
)
coverage.to_csv(OUT / "daily_coverage_by_year.csv", index=False)

# 4. Annual features
annual = daily.groupby(["district_name", "year"]).agg(
    annual_total_mm=("rainfall_estimate_mm", "sum"),
    rainy_days_count=("rainy_day", "sum"),
    heavy_rain_days_count=("heavy_rain_day", "sum"),
    very_heavy_rain_days_count=("very_heavy_rain_day", "sum"),
    max_1day_rainfall_mm=("rainfall_estimate_mm", "max"),
    observed_days=("date", "nunique"),
).reset_index()

# 5. Seasonal rainfall features
daily["season"] = np.select(
    [
        daily["month"].between(3, 5),
        daily["month"].between(6, 9),
        daily["month"].between(10, 12),
    ],
    ["pre_monsoon", "sw_monsoon", "ne_monsoon"],
    default="winter",
)

seasonal = daily.pivot_table(
    index=["district_name", "year"],
    columns="season",
    values="rainfall_estimate_mm",
    aggfunc="sum",
)
seasonal.columns = [f"{c}_total_mm" for c in seasonal.columns]
seasonal = seasonal.reset_index()

# 6. Recalculate maximum 3-day rainfall independently within June-September
sw = daily[daily["month"].isin([6, 7, 8, 9])].copy()
sw["rolling_3day_mm"] = sw.groupby(
    ["district_name", "year"]
)["rainfall_estimate_mm"].transform(
    lambda s: s.rolling(window=3, min_periods=3).sum()
)

sw_max3 = sw.groupby(["district_name", "year"])["rolling_3day_mm"].max().reset_index()
sw_max3 = sw_max3.rename(columns={"rolling_3day_mm": "sw_max_3day_rainfall_mm"})

# 7. Precipitation Concentration Index (PCI)
monthly = daily.groupby(["district_name", "year", "month"])[
    "rainfall_estimate_mm"
].sum().reset_index()

pci = monthly.groupby(["district_name", "year"]).agg(
    monthly_squared_sum=("rainfall_estimate_mm", lambda s: (s ** 2).sum()),
    annual_from_months=("rainfall_estimate_mm", "sum"),
).reset_index()

pci["pci"] = np.where(
    pci["annual_from_months"] > 0,
    100 * pci["monthly_squared_sum"] / (pci["annual_from_months"] ** 2),
    np.nan,
)
pci = pci[["district_name", "year", "pci"]]

# 8. Merge all engineered features
features = annual.merge(seasonal, on=["district_name", "year"], how="left")
features = features.merge(sw_max3, on=["district_name", "year"], how="left")
features = features.merge(pci, on=["district_name", "year"], how="left")
features = features.merge(
    coverage[["district_name", "year", "expected_days", "complete_calendar_year"]],
    on=["district_name", "year"],
    how="left",
)

# 9. Compare recalculated 3-day feature with existing monsoon feature
comparison = features[["district_name", "year", "sw_max_3day_rainfall_mm"]].merge(
    monsoon[["district_name", "year", "max_3day_rainfall_mm"]],
    on=["district_name", "year"],
    how="left",
)
comparison["existing_feature_missing"] = comparison["max_3day_rainfall_mm"].isna()
comparison["recalculated_feature_missing"] = comparison["sw_max_3day_rainfall_mm"].isna()
comparison["absolute_difference_mm"] = (
    comparison["sw_max_3day_rainfall_mm"] - comparison["max_3day_rainfall_mm"]
).abs()
comparison.to_csv(OUT / "three_day_feature_quality_check.csv", index=False)

# 10. Explain the handling decisions; do not invent missing rainfall values
features["data_quality_note"] = np.where(
    features["complete_calendar_year"],
    "Complete calendar year",
    "Incomplete calendar year; exclude from full-year comparisons",
)
features.to_csv(OUT / "engineered_district_year_features.csv", index=False)

# 11. Summary report
with open(OUT / "analysis_report.md", "w", encoding="utf-8") as f:
    f.write("# Rainfall Data Cleaning and Feature Engineering Report\n\n")
    f.write("## Input datasets\n")
    f.write(f"- Daily rainfall rows analysed: {len(daily):,}\n")
    f.write(f"- Monsoon feature rows analysed: {len(monsoon):,}\n")
    f.write(f"- Districts: {', '.join(DISTRICTS)}\n\n")
    f.write("## Missing values\n")
    f.write("- See `metadata_report.csv` and `missing_values_report.csv`.\n")
    f.write("- Missing three-day rainfall features were investigated by recalculating a three-day rolling rainfall total from daily observations during June–September.\n")
    f.write("- Recalculated values are kept as a separate feature; the original monsoon dataset is not overwritten.\n")
    f.write("- Missing values are not automatically replaced with zero.\n\n")
    f.write("## Engineered features\n")
    f.write("- Annual rainfall total, rainy-day count, heavy-rain-day count, very-heavy-rain-day count, maximum one-day rainfall.\n")
    f.write("- Pre-monsoon, southwest monsoon, northeast monsoon and winter rainfall totals.\n")
    f.write("- Maximum three-day southwest monsoon rainfall and precipitation concentration index (PCI).\n\n")
    f.write("## Data quality\n")
    f.write("- Calendar completeness is recorded for each district-year.\n")
    f.write("- Incomplete calendar years should not be directly compared with complete annual totals.\n")
    f.write("- Review `three_day_feature_quality_check.csv` to assess agreement between existing and recalculated values.\n\n")
    f.write("## Output dataset\n")
    f.write("- `engineered_district_year_features.csv` contains one row per district-year.\n")
    f.write("- Original input files were not modified.\n")
    f.write("- A recalculated feature is not considered validated until its comparison with existing values has been reviewed.\n")

print("Analysis completed.")
print(f"Daily rows analysed: {len(daily):,}")
print(f"Monsoon rows analysed: {len(monsoon):,}")
print(f"Output folder: {OUT}")
print("\nGenerated files:")
for path in sorted(OUT.glob("*")):
    if path.is_file():
        print(f"- {path}")
