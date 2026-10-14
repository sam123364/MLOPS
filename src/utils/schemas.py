"""
Rainfall Schema Validation Engine.
Provides programmatic validation against YAML schema contracts for:
- District annual rainfall (Long & Wide formats)
- District seasonal rainfall
- Hobli & Taluk sub-district rainfall
"""

from pathlib import Path
from typing import Dict, List, Tuple
import yaml
import pandas as pd
import numpy as np

def load_schemas() -> dict:
    """Load schema definitions from configs/rainfall_schemas.yaml."""
    schema_path = Path("configs/rainfall_schemas.yaml")
    if not schema_path.exists():
        # Fallback if executing from a subdirectory
        schema_path = Path(__file__).resolve().parents[2] / "configs" / "rainfall_schemas.yaml"
    with open(schema_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def validate_dataframe(df: pd.DataFrame, schema_key: str) -> Tuple[bool, List[str]]:
    """
    Validate a pandas DataFrame against a named schema in configs/rainfall_schemas.yaml.
    
    Args:
        df: DataFrame to validate
        schema_key: Key in rainfall_schemas.yaml (e.g. 'district_annual_long_schema')
        
    Returns:
        (is_valid: bool, errors: List[str])
    """
    schemas = load_schemas()
    if schema_key not in schemas:
        return False, [f"Schema key '{schema_key}' not found in configs/rainfall_schemas.yaml"]

    schema = schemas[schema_key]
    col_defs = schema.get("columns", {})
    errors = []

    # 1. Check required columns
    for col_name, col_meta in col_defs.items():
        if col_name not in df.columns:
            errors.append(f"Missing required column: '{col_name}'")
            continue

        series = df[col_name]

        # 2. Nullability check
        if not col_meta.get("nullable", True):
            null_count = series.isna().sum()
            if null_count > 0:
                errors.append(f"Column '{col_name}' has {null_count} null values (nullable=False)")

        # 3. Allowed categorical values
        allowed = col_meta.get("allowed_values")
        if allowed:
            non_null = series.dropna()
            invalid_vals = set(non_null.unique()) - set(allowed)
            if invalid_vals:
                errors.append(f"Column '{col_name}' contains unexpected values: {invalid_vals}")

        # 4. Numeric Range check
        num_range = col_meta.get("range")
        if num_range and pd.api.types.is_numeric_dtype(series):
            min_val, max_val = num_range
            out_of_bounds = series[(series < min_val) | (series > max_val)]
            if len(out_of_bounds) > 0:
                errors.append(
                    f"Column '{col_name}' has {len(out_of_bounds)} values outside range [{min_val}, {max_val}]"
                )

    # 5. Primary Key check
    pk = schema.get("primary_key")
    if pk and all(col in df.columns for col in pk):
        dups = df.duplicated(subset=pk).sum()
        if dups > 0:
            errors.append(f"Primary key {pk} has {dups} duplicate entries")

    is_valid = len(errors) == 0
    return is_valid, errors

def validate_all_rainfall_csvs() -> Dict[str, Tuple[bool, List[str]]]:
    """Validate all generated clean rainfall CSVs and return a status report dictionary."""
    results = {}
    base_dir = Path("data/processed/rainfall")

    checks = [
        (base_dir / "karnataka_district_annual_rainfall_2021_2025_long.csv", "district_annual_long_schema"),
        (base_dir / "karnataka_district_annual_rainfall_comparison_wide.csv", "district_annual_wide_schema"),
        (base_dir / "karnataka_district_seasonal_rainfall_2021_2025.csv", "district_seasonal_schema"),
        (base_dir / "karnataka_hobli_rainfall_2021_clean.csv", "hobli_rainfall_schema"),
        (base_dir / "karnataka_hobli_rainfall_2024_clean.csv", "hobli_rainfall_schema")
    ]

    for fpath, s_key in checks:
        if not fpath.exists():
            results[fpath.name] = (False, [f"File {fpath} does not exist."])
            continue
        df = pd.read_csv(fpath)
        valid, errs = validate_dataframe(df, s_key)
        results[fpath.name] = (valid, errs)

    return results

if __name__ == "__main__":
    report = validate_all_rainfall_csvs()
    print("=" * 60)
    print("RAINFALL DATASET SCHEMA VALIDATION REPORT")
    print("=" * 60)
    for fname, (is_valid, errors) in report.items():
        status = "PASSED [OK]" if is_valid else "FAILED [X]"
        print(f"{fname:55} {status}")
        if not is_valid:
            for e in errors:
                print(f"  -> {e}")
