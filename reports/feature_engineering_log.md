# Feature Engineering Log & Parameter Rationale

**Document Version:** 1.0.0  
**Updated:** 2026-10-14  
**Pipeline Stage:** Phase 1 Feature Engineering & EDA  
**Target Study Area:** Eastern Karnataka Dry Belt (Kolar, Chikkaballapur, Tumakuru)  
**Primary Target Variable:** Surface Runoff ($Q$ in mm) and Harvestable Yield ($V$ in $\text{m}^3$)

---

## 1. Overview of Changes

To overcome the non-linear limitations of simple annual rainfall totals in predicting agricultural runoff via the USDA SCS-CN (Soil Conservation Service Curve Number) methodology, new dynamic hydrological features were engineered and persisted directly into the processed Parquet datasets in `data/processed/`.

The updated Parquet artifacts include:
1. `data/processed/imd_rainfall_daily_district_official.parquet` (136,878 rows $\times$ 14 columns)
2. `data/processed/imd_monsoon_features_official.parquet` (375 rows $\times$ 18 columns)
3. `data/processed/imd_rainfall_daily_district.parquet` (136,878 rows $\times$ 11 columns, retained baseline)
4. `data/processed/imd_monsoon_features.parquet` (375 rows $\times$ 17 columns, retained baseline)

---

## 2. Newly Added Daily Features (`imd_rainfall_daily_district_official.parquet`)

| Feature Name | Data Type | Physical Unit | Mathematical Definition | Why Added & How It Aids ML Model Training |
|---|---|---|---|---|
| `prior_5day_rainfall_mm` ($P_5$) | `float32` | `mm` | $\sum_{k=1}^5 P_{t-k}$ (5-day backward rolling sum, shifted by 1 day) | **Essential for SCS-CN AMC:** Soil infiltration capacity drops sharply after prior rain. Standard SCS-CN equations require $P_5$ to determine antecedent soil moisture. Training an ML model without $P_5$ forces it to treat dry soil and saturated soil identically, leading to large under/over-prediction errors. |
| `amc_class` | `string` | Categorical | `AMC-I` (Dry), `AMC-II` (Normal), `AMC-III` (Wet) based on $P_5$ & season | **Encapsulates Non-Linear Runoff Switching:** In USDA SCS-CN, Curve Number switches dynamically: $CN(I) < CN(II) < CN(III)$. Giving the model this discrete regime indicator allows tree-based models (Random Forest, Gradient Boosting) to make clean split decisions for infiltration vs immediate surface runoff. |
| `is_rainy_day` | `bool` | Boolean | $P_t \ge 2.5\text{ mm}$ | **Filters Ineffective Precipitation:** Drizzle below $2.5\text{ mm}$ evaporates quickly from canopy/ground depression storage and produces zero runoff. This binary flag helps models ignore background noise. |
| `is_heavy_rain_day` | `bool` | Boolean | $P_t \ge 25.0\text{ mm}$ | **Runoff Initiation Indicator:** In semi-arid red sandy loam soils (HSG B/C), initial abstraction $I_a$ is typically $15\text{--}25\text{ mm}$. Runoff is rarely initiated until daily rain exceeds this threshold. This feature serves as an activation flag for runoff. |
| `is_very_heavy_rain_day`| `bool` | Boolean | $P_t \ge 50.0\text{ mm}$ | **High-Yield & Overflow Event Identifier:** Days $\ge 50\text{ mm}$ generate over 60% of annual harvestable surface runoff volume. Identifying these extreme events allows the model to predict peak pond inflow and prevent under-sizing storage capacity. |

---

## 3. Newly Added Seasonal & Annual Features (`imd_monsoon_features_official.parquet`)

| Feature Name | Data Type | Physical Unit | Mathematical Definition | Why Added & How It Aids ML Model Training |
|---|---|---|---|---|
| `rainy_days_count` | `int32` | Count | Count of days in SWM (Jun–Sep) where $P \ge 2.5\text{ mm}$ | **Distinguishes Event Frequency from Volume:** Differentiates between a monsoon with frequent moderate rain vs a dry monsoon with one flash storm. Improves model generalization for crop water availability. |
| `heavy_rain_days_gt_25mm` | `int32` | Count | Count of days in SWM where $P \ge 25.0\text{ mm}$ | **Direct Correlate of Harvestable Volume:** Historical data proves that annual runoff volume is more strongly correlated ($r > 0.85$) with the count of heavy rain days than with total seasonal rainfall. |
| `very_heavy_rain_days_gt_50mm` | `int32` | Count | Count of days in SWM where $P \ge 50.0\text{ mm}$ | **Flood & Check Dam Sizing Proxy:** Captures catastrophic storm frequency that fills check dams and reservoirs in single events. |
| `max_1day_rainfall_mm` | `float32` | `mm` | $\max_{t \in \text{SWM}} P_t$ | **Peak Intensity Metric:** Peak 24-hour storm intensity dictates the required spillway dimensions and embankment safety for farm ponds. |
| `max_3day_rainfall_mm` | `float32` | `mm` | $\max \sum_{k=0}^2 P_{t+k}$ during SWM | **Soil Saturation & Runoff Coefficient Multiplier:** Multi-day continuous storms saturate even Group A/B sandy soils, driving runoff coefficients close to 0.7–0.8. |
| `nem_total_mm` | `float32` | `mm` | $\sum_{t \in \text{Oct--Dec}} P_t$ | **Captures Bimodal Rainfall in Eastern Karnataka:** Kolar and Chikkaballapur receive up to 35% of annual rainfall from the Northeast (retreating) Monsoon. Models relying solely on SWM fail to capture the complete annual water budget. |
| `annual_total_mm` | `float32` | `mm` | $\sum_{t \in \text{Jan--Dec}} P_t$ | **Global Ground Truth Scale:** Provides the master annual rainfall benchmark across 125 continuous years (1901–2025). |
| `pci` (Precipitation Concentration Index) | `float32` | Index (0–100) | $100 \times \frac{\sum_{m=1}^{12} P_m^2}{(\sum_{m=1}^{12} P_m)^2}$ | **Quantifies Intra-Annual Seasonality:** $\text{PCI} < 10$ = uniform; $11\text{--}15$ = moderate; $16\text{--}20$ = irregular; $> 20$ = strongly concentrated. Higher PCI means rain arrives in narrow windows, demanding higher storage capacity to prevent waste. |

---

## 4. EDA Diagnostic Figures Generated

The automated pipeline generated 4 high-resolution diagnostic visualizations saved to `reports/figures/`:

1. **`reports/figures/eda_rainfall_intensity_distribution.png`**:
   - Demonstrates the heavy right skew of daily precipitation in Eastern Karnataka.
   - Highlights that while days $> 25\text{ mm}$ account for $< 6\%$ of all calendar days, they contribute **over 52% of total cumulative water volume**.
2. **`reports/figures/eda_heavy_rain_vs_dry_spells.png`**:
   - Shows the bivariate distribution of monsoon dry spells vs heavy rain counts.
   - Identifies high-risk agricultural years characterized by long dry spells punctuated by sudden high-intensity storms.
3. **`reports/figures/eda_amc_class_distribution.png`**:
   - Maps the seasonal breakdown of Antecedent Moisture Conditions.
   - Reveals that in Pre-Monsoon (Summer), $> 92\%$ of days are AMC-I (dry soil, high initial abstraction), whereas during peak Southwest Monsoon (July–August), AMC-II and AMC-III dominate.
4. **`reports/figures/eda_monsoon_trends_with_extremes.png`**:
   - 125-year historical time series (1901–2025) for Kolar with 10-year rolling means, identifying multi-year drought cycles and record wet years (e.g., 1988, 1998, 2021).
