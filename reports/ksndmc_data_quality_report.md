# KSNDMC Rainfall Dataset Quality Audit Report

**Project:** AI-Powered Rainwater Harvesting Decision Support (Eastern Karnataka)  
**Study Districts:** Kolar, Chikkaballapur, Tumakuru  
**Audit Target:** `data/processed/rainfall/karnataka_rainfall_master_clean.xlsx` & `data/raw/ksndmc/`  
**Audit Date:** 2026-10-14  
**Audit Status:** Completed — Critical data-shift anomalies flagged  

---

## 1. Executive Summary

An in-depth data quality audit was conducted on the KSNDMC (Karnataka State Natural Disaster Monitoring Centre) rainfall records compiled from the OpenCity public data portal. The dataset spans four years (**2021, 2022, 2024, and 2025**; year **2023 is absent**).

### Primary Findings:
1. **Critical Column Shift Anomaly in 2025 Data:**  
   In `ka_dist_rainfall_2025.csv` (and sheet `2025_District_Seasonal`), rows 6 through 24 have their seasonal rainfall columns (Pre-Monsoon, Southwest Monsoon, Northeast Monsoon) shifted by district.
   - For **Kolar** (row 19), reported annual rainfall is **927 mm**, but Southwest Monsoon (SWM) rainfall is reported as **2,176 mm** and Pre-Monsoon as **750.2 mm**. Their seasonal sum is **3,169.2 mm** (a discrepancy of **+2,242.2 mm**).
   - This audit confirmed that the seasonal numbers in row 19 actually belong to **Kodagu** (row 18, a high-rainfall Western Ghats district with annual actual = 3,169 mm).
   - Kolar's true seasonal numbers (Pre-Monsoon: 262.1 mm, SWM: 382 mm, NEM: 283 mm, summing to 927.1 mm) were mistakenly placed in row 20 under **Koppala**.
2. **2024 Header Unit Mislabel:**  
   In `f28d92e7-7e61-4d58-84a7-52e2ab6ee469.csv` (sheet `2024_District_Seasonal`), Pre-Monsoon columns are labeled as `Pre-Monsoon Normal (%)` and `Pre-Monsoon Actual (%)` despite containing rainfall depths in **millimeters (mm)**.
3. **Missing Year Gap:**  
   Year **2023 is completely missing** from the collection, preventing continuous annual model backtesting.
4. **Administrative Boundary Evolution:**  
   2021 records contain 30 districts, whereas 2024/2025 records contain 31 districts, reflecting the official creation of **Vijayanagar district** on October 2, 2021 (carved out of Ballari).
5. **Validation Readiness Verdict:**  
   **KSNDMC is NOT currently ready for automated validation of 2025.** However, 2021, 2022, and 2024 annual district totals are mathematically consistent and can serve as manual sanity checks once the 2025 column shift is resolved with KSNDMC.

---

## 2. Sheet-by-Sheet Inspection of Master Workbook

Workbook: `data/processed/rainfall/karnataka_rainfall_master_clean.xlsx`

| Sheet Name | Rows | Columns | Geo Coverage | Year Coverage | Health Status |
|---|---|---|---|---|---|
| **`District_Annual_Comparison`** | 31 | 10 | All 31 Districts | 2021, 2022, 2024, 2025 | Valid (wide format; compares annual totals) |
| **`District_Annual_Long`** | 124 | 6 | All 31 Districts | 2021, 2022, 2024, 2025 | Valid (long format; standardized IMD departure classes) |
| **`District_Seasonal_MultiYear`** | 92 | 15 | All 31 Districts | 2021, 2024, 2025 | **Contains 2025 column-shift anomaly** |
| **`2024_Hobli_Taluk_Clean`** | 1,122 | 9 | 31 Districts, 227 Taluks, 850+ Hoblis | 2024 | Valid (forward-filled hierarchy) |
| **`2021_Hobli_Taluk_Clean`** | 1,134 | 18 | 30 Districts, 220+ Taluks, 850 Hoblis | 2021 | Valid (complete seasonal & annual breakdown; 0 sum mismatches) |

---

## 3. Deep-Dive: The Kolar 2025 Anomaly

### 3.1 Cell Inspection
In `data/raw/ksndmc/ka_dist_rainfall_2025.csv`, Row 19:
- `Sl No`: 19
- `District`: Kolar
- `Annual Normal`: 735 mm
- `Annual Actual`: 927 mm
- `Annual Departure (%)`: +26%
- `Pre Monsoon Normal`: 252.9 mm *(Anomalous: Kolar normal is ~117 mm)*
- `Pre Monsoon Actual`: 750.2 mm *(Anomalous: 750 mm summer rain in semi-arid Kolar is unphysical)*
- `SWM Normal`: 2,188 mm *(Anomalous: Kolar SWM normal is ~399 mm)*
- `SWM Actual`: 2,176 mm *(Anomalous: exceeds Kolar annual rainfall by 1,249 mm)*
- `NEM Normal`: 288 mm
- `NEM Actual`: 243 mm

### 3.2 Mathematical Proof of Column Shift
The identity $\text{Pre-Monsoon Actual} + \text{SWM Actual} + \text{NEM Actual} \approx \text{Annual Actual}$ was tested:
- **Reported Annual Actual:** $927\text{ mm}$
- **Sum of Reported Seasons:** $750.2 + 2176 + 243 = 3169.2\text{ mm}$
- **Discrepancy:** $+2,242.2\text{ mm}$

Tracing across rows reveals that the seasonal columns between rows 6 and 24 are shifted:

| Row | District Listed | Annual Actual | Reported SWM Actual | True Owner of Reported Seasonal Numbers |
|---|---|---|---|---|
| 10 | Chitradurga | 515 mm | 1,255 mm | Chikkamagaluru (Malnad) |
| 11 | Dakshina Kannada | 4,910 mm | 233 mm | Chitradurga (Central dry belt) |
| 12 | Davanagere | 727 mm | 3,369 mm | Dakshina Kannada (Coastal) |
| 18 | Kodagu | 3,169 mm | 768 mm | Kalaburagi |
| **19** | **Kolar** | **927 mm** | **2,176 mm** | **Kodagu (Western Ghats)** |
| **20** | **Koppala** | **663 mm** | **382 mm** | **Kolar (Eastern dry belt: PM=262, SWM=382, NEM=283 $\rightarrow$ Sum = 927 mm!)** |

As per project guidelines, **neither value has been silently modified**. The original values are preserved, and all 19 affected district records have been cataloged in [`data/processed/ksndmc_flagged_records.csv`](file:///C:/Users/user/Desktop/MLOPS/data/processed/ksndmc_flagged_records.csv).

---

## 4. Comparison with IMD Gridded Dataset

| Feature | IMD Gridded Dataset (`imdweb_nSbYRBgK.nc`) | KSNDMC Public Portal Dataset |
|---|---|---|
| **Data Nature** | Direct physical interpolation from IMD surface observatories | Administrative aggregation of state telemetry rain gauges |
| **Granularity** | **Daily continuous time-series** | Seasonal & annual static totals |
| **Coverage Period** | 1901 to 2025 (45,626 consecutive days) | 2021, 2022, 2024, 2025 (4 discrete years) |
| **Spatial Unit** | 0.25° × 0.25° regular geographic grid cells | District, Taluk, Hobli administrative areas |
| **Data Integrity** | Zero missing values, zero physical violations | 2025 seasonal column shift across 19 districts; 2023 missing |
| **Role in Project** | **Core ML Model Training & Backtesting** | **Independent Benchmark / Sanity Check** |

---

## 5. Summary of Flagged Records

A total of **22 flagged records** were written to [`data/processed/ksndmc_flagged_records.csv`](file:///C:/Users/user/Desktop/MLOPS/data/processed/ksndmc_flagged_records.csv):
- **19 Critical Records:** 2025 district seasonal column shifts (Bidar, Chamarajanagara, Chikkaballapura, Chikkamagaluru, Chitradurga, Dakshina Kannada, Davanagere, Dharwad, Gadag, Hassan, Haveri, Kalaburagi, Kodagu, Kolar, Koppala, Mandya, Mysuru, Raichur, Ramanagara).
- **1 Moderate Record:** 2024 header unit label mislabeled as `(%)` instead of `mm`.
- **1 High Record:** Complete omission of calendar year 2023.
- **1 Low Record:** Vijayanagar district creation in late 2021 (30 vs 31 districts).

---

## 6. Readiness Verdict & Next Steps

### Verdict:
- **Annual Totals (2021, 2022, 2024, 2025):** **READY** for high-level sanity checking against IMD annual district averages.
- **2021 Hobli Data:** **READY** for local sub-district rainfall distribution studies (all 1,134 rows mathematically balanced).
- **2025 Seasonal Data:** **NOT READY.** Must not be used for model validation until KSNDMC releases a corrected file or the team approves a formal realignment mapping.
