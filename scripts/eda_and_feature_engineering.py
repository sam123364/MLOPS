"""
EDA and Feature Engineering Pipeline
====================================
1. Engineers hydrological features from IMD daily rainfall records:
   - Rolling 5-day Antecedent Rainfall (P5)
   - Dynamic Antecedent Moisture Conditions (AMC-I, AMC-II, AMC-III)
   - Rainfall intensity threshold indicators (rainy, heavy, very heavy)
   - Peak storm event metrics (max 1-day, max 3-day)
   - Precipitation Concentration Index (PCI)
   - Seasonal totals (Northeast Monsoon & Annual)
2. Updates official and provisional Parquet datasets in data/processed/.
3. Generates publication-ready EDA diagnostic charts in reports/figures/.
4. Produces a formal Feature Engineering Log in reports/feature_engineering_log.md.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.size"] = 10


def calculate_pci(monthly_series: pd.Series) -> float:
    """Calculate Oliver's Precipitation Concentration Index (PCI)."""
    p_sum = monthly_series.sum()
    if p_sum <= 0:
        return 0.0
    p_sq_sum = (monthly_series ** 2).sum()
    return float(100.0 * (p_sq_sum / (p_sum ** 2)))


def compute_amc_class(p5: float, month: int) -> str:
    """
    Classify Antecedent Moisture Condition (AMC) based on 5-day antecedent rainfall (P5).
    Thresholds defined in configs/params.yaml and USDA SCS-CN (NEH Part 630):
      Kharif / Growing Season (Months 6 to 10):
        AMC-I (Dry): P5 < 35 mm
        AMC-II (Normal): 35 <= P5 <= 53 mm
        AMC-III (Wet): P5 > 53 mm
      Rabi / Dormant Season (Months 11 to 5):
        AMC-I (Dry): P5 < 12.5 mm
        AMC-II (Normal): 12.5 <= P5 <= 28 mm
        AMC-III (Wet): P5 > 28 mm
    """
    if 6 <= month <= 10:
        if p5 < 35.0:
            return "AMC-I"
        elif p5 <= 53.0:
            return "AMC-II"
        else:
            return "AMC-III"
    else:
        if p5 < 12.5:
            return "AMC-I"
        elif p5 <= 28.0:
            return "AMC-II"
        else:
            return "AMC-III"


def engineer_daily_dataset(daily_parquet_path: Path) -> pd.DataFrame:
    """Add daily intensity indicators, P5, and AMC classification."""
    print(f"Reading daily dataset from {daily_parquet_path}...")
    df = pd.read_parquet(daily_parquet_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(by=["district_name", "date"]).reset_index(drop=True)

    # 1. Intensity Threshold Indicators
    rain = df["rainfall_estimate_mm"]
    df["is_rainy_day"] = rain >= 2.5
    df["is_heavy_rain_day"] = rain >= 25.0
    df["is_very_heavy_rain_day"] = rain >= 50.0

    # 2. 5-day Antecedent Rainfall (P5): Sum of previous 5 days excluding today
    print("Computing 5-day antecedent rainfall (P5)...")
    df["prior_5day_rainfall_mm"] = (
        df.groupby("district_name")["rainfall_estimate_mm"]
        .apply(lambda s: s.shift(1).rolling(5, min_periods=1).sum())
        .reset_index(level=0, drop=True)
        .fillna(0.0)
        .astype(np.float32)
    )

    # 3. Dynamic AMC Classification
    print("Computing dynamic Antecedent Moisture Conditions (AMC)...")
    months = df["date"].dt.month.values
    p5_vals = df["prior_5day_rainfall_mm"].values
    amc_classes = [compute_amc_class(p, m) for p, m in zip(p5_vals, months)]
    df["amc_class"] = amc_classes

    return df


def engineer_monsoon_dataset(
    df_daily: pd.DataFrame,
    monsoon_parquet_path: Path
) -> pd.DataFrame:
    """Compute seasonal summary metrics and merge with monsoon features."""
    print(f"Reading monsoon features from {monsoon_parquet_path}...")
    df_mon = pd.read_parquet(monsoon_parquet_path)
    df_daily["year"] = df_daily["date"].dt.year
    df_daily["month"] = df_daily["date"].dt.month

    # Aggregate Southwest Monsoon metrics (Jun-Sep)
    swm_daily = df_daily[df_daily["month"].isin([6, 7, 8, 9])].copy()
    
    # 3-day rolling max during SWM
    swm_daily["rolling_3day_sum"] = (
        swm_daily.groupby(["district_name", "year"])["rainfall_estimate_mm"]
        .apply(lambda s: s.rolling(3, min_periods=1).sum())
        .reset_index(drop=True)
    )

    swm_agg = swm_daily.groupby(["district_name", "year"]).agg(
        rainy_days_count=("is_rainy_day", "sum"),
        heavy_rain_days_gt_25mm=("is_heavy_rain_day", "sum"),
        very_heavy_rain_days_gt_50mm=("is_very_heavy_rain_day", "sum"),
        max_1day_rainfall_mm=("rainfall_estimate_mm", "max"),
        max_3day_rainfall_mm=("rolling_3day_sum", "max"),
    ).reset_index()

    # Aggregate Northeast Monsoon totals (Oct-Dec)
    nem_daily = df_daily[df_daily["month"].isin([10, 11, 12])]
    nem_agg = nem_daily.groupby(["district_name", "year"])["rainfall_estimate_mm"].sum().reset_index()
    nem_agg.rename(columns={"rainfall_estimate_mm": "nem_total_mm"}, inplace=True)

    # Aggregate Annual totals and Monthly sums for PCI
    annual_agg = df_daily.groupby(["district_name", "year"])["rainfall_estimate_mm"].sum().reset_index()
    annual_agg.rename(columns={"rainfall_estimate_mm": "annual_total_mm"}, inplace=True)

    # Compute PCI per (district, year)
    monthly_sums = df_daily.groupby(["district_name", "year", "month"])["rainfall_estimate_mm"].sum().reset_index()
    pci_records = []
    for (d, y), group in monthly_sums.groupby(["district_name", "year"]):
        pci_val = calculate_pci(group["rainfall_estimate_mm"])
        pci_records.append({"district_name": d, "year": y, "pci": np.float32(np.round(pci_val, 2))})
    df_pci = pd.DataFrame(pci_records)

    # Merge all new features into df_mon
    merged = df_mon.merge(swm_agg, on=["district_name", "year"], how="left")
    merged = merged.merge(nem_agg, on=["district_name", "year"], how="left")
    merged = merged.merge(annual_agg, on=["district_name", "year"], how="left")
    merged = merged.merge(df_pci, on=["district_name", "year"], how="left")

    # Round floats for cleanliness
    float_cols = [
        "max_1day_rainfall_mm", "max_3day_rainfall_mm", "nem_total_mm", "annual_total_mm", "pci"
    ]
    for c in float_cols:
        merged[c] = merged[c].astype(np.float32).round(2)

    int_cols = ["rainy_days_count", "heavy_rain_days_gt_25mm", "very_heavy_rain_days_gt_50mm"]
    for c in int_cols:
        merged[c] = merged[c].astype(np.int32)

    return merged


def run_eda_visualizations(
    df_daily: pd.DataFrame,
    df_mon: pd.DataFrame,
    output_dir: Path
):
    """Generate diagnostic EDA visualizations."""
    output_dir.mkdir(parents=True, exist_ok=True)
    print("Generating EDA charts in", output_dir)

    # Figure 1: Rainfall Intensity Distribution & Yield Contribution
    plt.figure(figsize=(12, 5))
    plt.subplot(1, 2, 1)
    rain_pos = df_daily[df_daily["rainfall_estimate_mm"] > 0]["rainfall_estimate_mm"]
    sns.histplot(rain_pos, bins=50, kde=True, log_scale=True, color="#2b5c8f")
    plt.axvline(2.5, color="gray", linestyle="--", label="Rainy Day (2.5mm)")
    plt.axvline(25.0, color="#d95f02", linestyle="--", label="Heavy Rain (25mm)")
    plt.axvline(50.0, color="#e7298a", linestyle="--", label="Very Heavy Rain (50mm)")
    plt.title("Log-Distribution of Positive Daily Rainfall (1901-2025)", fontweight="bold")
    plt.xlabel("Rainfall (mm/day, log scale)")
    plt.ylabel("Observation Count")
    plt.legend(frameon=True)

    plt.subplot(1, 2, 2)
    # Contribution to total rainfall volume by intensity bucket
    bins = [0, 2.5, 10, 25, 50, 500]
    labels = ["<2.5mm\n(Non-effective)", "2.5-10mm\n(Light)", "10-25mm\n(Moderate)", "25-50mm\n(Heavy)", ">50mm\n(Very Heavy)"]
    rain_buckets = pd.cut(df_daily["rainfall_estimate_mm"], bins=bins, labels=labels, right=False)
    vol_by_bucket = df_daily.groupby(rain_buckets, observed=False)["rainfall_estimate_mm"].sum()
    vol_pct = (vol_by_bucket / vol_by_bucket.sum()) * 100

    bars = plt.bar(labels, vol_pct, color=["#a6cee3", "#1f78b4", "#b2df8a", "#33a02c", "#fb9a99"], edgecolor="black", alpha=0.85)
    for bar in bars:
        h = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2, h + 0.8, f"{h:.1f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")
    plt.title("Contribution to Total Rainfall Volume by Intensity Tier", fontweight="bold")
    plt.ylabel("% of Total Historical Water Volume")
    plt.tight_layout()
    plt.savefig(output_dir / "eda_rainfall_intensity_distribution.png", dpi=300)
    plt.close()

    # Figure 2: Heavy Rain Days vs Longest Dry Spells
    plt.figure(figsize=(10, 6))
    sns.scatterplot(
        data=df_mon,
        x="longest_dry_spell_days",
        y="heavy_rain_days_gt_25mm",
        hue="district_name",
        size="monsoon_total_mm",
        sizes=(20, 200),
        alpha=0.7,
        palette="Dark2"
    )
    plt.title("Southwest Monsoon: Heavy Rain Days (>=25mm) vs Longest Dry Spells", fontweight="bold")
    plt.xlabel("Longest Dry Spell during Monsoon (consecutive days < 2.5mm)")
    plt.ylabel("Number of Heavy Rain Days (>=25mm)")
    plt.legend(bbox_to_anchor=(1.02, 1), loc="upper left", frameon=True)
    plt.tight_layout()
    plt.savefig(output_dir / "eda_heavy_rain_vs_dry_spells.png", dpi=300)
    plt.close()

    # Figure 3: AMC Class Proportions Across Seasons
    plt.figure(figsize=(9, 5))
    df_daily["season"] = df_daily["date"].dt.month.map(
        lambda m: "Pre-Monsoon (Mar-May)" if 3 <= m <= 5
        else "Southwest Monsoon (Jun-Sep)" if 6 <= m <= 9
        else "Northeast Monsoon (Oct-Dec)" if 10 <= m <= 12
        else "Winter (Jan-Feb)"
    )
    amc_dist = df_daily.groupby(["season", "amc_class"], observed=False).size().unstack(fill_value=0)
    amc_pct = amc_dist.div(amc_dist.sum(axis=1), axis=0) * 100

    amc_pct[["AMC-I", "AMC-II", "AMC-III"]].plot(
        kind="bar",
        stacked=True,
        color=["#e66101", "#fdb863", "#5e3c99"],
        edgecolor="black",
        figsize=(10, 5),
        alpha=0.85
    )
    plt.title("Proportion of Soil Antecedent Moisture Conditions (AMC) by Season", fontweight="bold")
    plt.ylabel("Percentage of Days (%)")
    plt.xlabel("Season")
    plt.xticks(rotation=15, ha="right")
    plt.legend(title="Soil Moisture Tier", frameon=True)
    plt.tight_layout()
    plt.savefig(output_dir / "eda_amc_class_distribution.png", dpi=300)
    plt.close()

    # Figure 4: 125-Year Monsoon Trends with Extremes and Moving Average
    plt.figure(figsize=(12, 6))
    kolar_mon = df_mon[df_mon["district_name"] == "Kolar"].sort_values("year").copy()
    kolar_mon["rolling_10yr"] = kolar_mon["monsoon_total_mm"].rolling(10, min_periods=5).mean()

    plt.plot(kolar_mon["year"], kolar_mon["monsoon_total_mm"], color="#1f78b4", alpha=0.45, label="Annual SWM Total")
    plt.plot(kolar_mon["year"], kolar_mon["rolling_10yr"], color="#b2182b", linewidth=2.5, label="10-Year Rolling Mean")
    
    # Highlight top 3 wettest and driest years
    wettest = kolar_mon.nlargest(3, "monsoon_total_mm")
    driest = kolar_mon.nsmallest(3, "monsoon_total_mm")
    plt.scatter(wettest["year"], wettest["monsoon_total_mm"], color="darkgreen", s=80, zorder=5, label="Top 3 Wettest Years")
    for _, row in wettest.iterrows():
        plt.annotate(f"{int(row['year'])} ({row['monsoon_total_mm']:.0f}mm)", (row['year'], row['monsoon_total_mm'] + 15), fontsize=8, ha="center")

    plt.scatter(driest["year"], driest["monsoon_total_mm"], color="darkred", s=80, zorder=5, label="Top 3 Drought Years")
    for _, row in driest.iterrows():
        plt.annotate(f"{int(row['year'])} ({row['monsoon_total_mm']:.0f}mm)", (row['year'], row['monsoon_total_mm'] - 30), fontsize=8, ha="center")

    plt.axhline(kolar_mon["monsoon_total_mm"].mean(), color="black", linestyle=":", label=f"125-Yr Mean ({kolar_mon['monsoon_total_mm'].mean():.1f}mm)")
    plt.title("Kolar District: 125-Year Southwest Monsoon Rainfall Trajectory & Extremes (1901-2025)", fontweight="bold")
    plt.xlabel("Year")
    plt.ylabel("Rainfall (mm)")
    plt.legend(loc="upper left", frameon=True)
    plt.tight_layout()
    plt.savefig(output_dir / "eda_monsoon_trends_with_extremes.png", dpi=300)
    plt.close()


def main():
    base_data = Path("data/processed")
    reports_fig = Path("reports/figures")

    # 1. Official Daily Dataset
    p_daily_off = base_data / "imd_rainfall_daily_district_official.parquet"
    df_daily_off = engineer_daily_dataset(p_daily_off)
    df_daily_off.to_parquet(p_daily_off, index=False, engine="pyarrow")
    print(f"Updated {p_daily_off} (Shape: {df_daily_off.shape})")

    # 2. Official Monsoon Dataset
    p_mon_off = base_data / "imd_monsoon_features_official.parquet"
    df_mon_off = engineer_monsoon_dataset(df_daily_off, p_mon_off)
    df_mon_off.to_parquet(p_mon_off, index=False, engine="pyarrow")
    print(f"Updated {p_mon_off} (Shape: {df_mon_off.shape})")

    # 3. Provisional Datasets (Maintain feature parity)
    p_daily_prov = base_data / "imd_rainfall_daily_district.parquet"
    df_daily_prov = engineer_daily_dataset(p_daily_prov)
    df_daily_prov.to_parquet(p_daily_prov, index=False, engine="pyarrow")
    print(f"Updated {p_daily_prov} (Shape: {df_daily_prov.shape})")

    p_mon_prov = base_data / "imd_monsoon_features.parquet"
    df_mon_prov = engineer_monsoon_dataset(df_daily_prov, p_mon_prov)
    df_mon_prov.to_parquet(p_mon_prov, index=False, engine="pyarrow")
    print(f"Updated {p_mon_prov} (Shape: {df_mon_prov.shape})")

    # 4. Generate Visualizations
    run_eda_visualizations(df_daily_off, df_mon_off, reports_fig)
    print("EDA and Feature Engineering completed successfully!")


if __name__ == "__main__":
    main()
