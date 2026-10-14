# Rainfall Data Quality Analysis and Feature Engineering Report

## 1. Objective
Analyse daily rainfall data for Chikkaballapur, Kolar and Tumakuru, investigate missing values, engineer district-year features and assess data quality.

## 2. Input datasets
- Daily rainfall records analysed: 136,878
- Existing monsoon feature records analysed: 375
- Districts: Chikkaballapur, Kolar and Tumakuru
- Coverage: 1901-2025

## 3. Missing-value analysis
The original monsoon feature `max_3day_rainfall_mm` contains 249 missing values out of 375 records (66.4%).
- Chikkaballapur: 0 missing values
- Kolar: 124 missing values
- Tumakuru: 125 missing values

Missing rainfall values were not automatically replaced with zero because missing data does not necessarily mean that no rainfall occurred.

The recalculated three-day feature is retained separately from the existing feature. Its agreement with the original feature remains unresolved and requires further investigation before either feature is treated as authoritative.

See `missing_values_report.csv` and `metadata_report.csv`.

## 4. Feature engineering
The engineered district-year dataset includes:
- Annual rainfall total
- Rainy-day, heavy-rain-day and very-heavy-rain-day counts
- Maximum one-day rainfall
- Pre-monsoon, southwest monsoon, northeast monsoon and winter rainfall totals
- Recalculated maximum three-day southwest monsoon rainfall
- Precipitation Concentration Index (PCI)
- Observed and expected calendar days
- Calendar-year completeness indicator

Rainy-day and heavy-rain thresholds are defined in the analysis script.

## 5. Data-quality validation
- Engineered dataset: 375 rows and 17 columns
- Missing values in the engineered dataset: 0
- Duplicate rows: 0
- Duplicate district-year keys: 0
- Negative values in the checked annual and maximum rainfall features: 0
- Incomplete calendar years: 3, corresponding to 1901 for the three districts

The incomplete year must not be compared directly with complete annual totals.

The zero-missing-value result applies to the engineered dataset and does not mean the original source feature has no missing values.

## 6. Three-day rainfall feature limitation
The existing and recalculated three-day rainfall features differ in many records. The recalculated feature uses a three-observation rolling window within each district and year for June-September data.

This calculation requires three observations, but three observations alone do not prove that the dates are consecutive. Date continuity and the definition used to produce the existing feature must be verified before the recalculated feature replaces it.

See `three_day_feature_quality_check.csv`.

## 7. Output files
- `engineered_district_year_features.csv`: engineered district-year dataset
- `missing_values_report.csv`: missing-value summary
- `metadata_report.csv`: dataset metadata
- `daily_coverage_by_year.csv`: yearly coverage information
- `three_day_feature_quality_check.csv`: comparison of existing and recalculated three-day rainfall features
- `analysis_report.md`: this report

## 8. Conclusion
The initial data-quality analysis and feature engineering have been completed. The engineered dataset passed basic checks for missing values, duplicate records and negative values in the selected rainfall features.

The three-day rainfall discrepancy remains unresolved. The dataset should undergo further validation before being used for model training. Original input datasets were not intentionally modified by this analysis script.
