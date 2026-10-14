"""
Clean, standardize, and structure all Karnataka rainfall datasets.
Produces clean CSVs with explicit schemas and standardized attribute names.
"""

from pathlib import Path
import pandas as pd
import numpy as np

def clean_name(s):
    if pd.isna(s):
        return ""
    val = str(s).strip()
    # Remove surrounding quotes, clean multiple spaces
    val = " ".join(val.split())
    return val

def standardize_district(name):
    norm = clean_name(name).upper()
    # Normalize known aliases
    aliases = {
        "BENGALURU URBAN": "Bengaluru Urban",
        "BENGALURU RURAL": "Bengaluru Rural",
        "RAMANAGARA": "Ramanagara",
        "KOLAR": "Kolar",
        "CHIKKABALLAPURA": "Chikkaballapura",
        "TUMAKURU": "Tumakuru",
        "CHITRADURGA": "Chitradurga",
        "DAVANAGERE": "Davanagere",
        "CHAMARAJANAGARA": "Chamarajanagara",
        "MYSURU": "Mysuru",
        "MANDYA": "Mandya",
        "BALLARI": "Ballari",
        "KOPPALA": "Koppala",
        "RAICHUR": "Raichur",
        "KALABURAGI": "Kalaburagi",
        "BIDAR": "Bidar",
        "BELAGAVI": "Belagavi",
        "BAGALKOTE": "Bagalkote",
        "VIJAYAPURA": "Vijayapura",
        "GADAG": "Gadag",
        "HAVERI": "Haveri",
        "DHARWAD": "Dharwad",
        "SHIVAMOGGA": "Shivamogga",
        "HASSAN": "Hassan",
        "CHIKKAMAGALURU": "Chikkamagaluru",
        "KODAGU": "Kodagu",
        "DAKSHINA KANNADA": "Dakshina Kannada",
        "UDUPI": "Udupi",
        "UTTARA KANNADA": "Uttara Kannada",
        "UTTARA": "Uttara Kannada",
        "YADGIR": "Yadgir",
        "VIJAYANAGAR": "Vijayanagar"
    }
    return aliases.get(norm, clean_name(name).title())

def classify_departure(dep_pct):
    """
    Standard IMD rainfall departure classification:
    Large Excess (LE): +60% or more
    Excess (E): +20% to +59%
    Normal (N): -19% to +19%
    Deficient (D): -20% to -59%
    Large Deficient (LD): -60% to -99%
    No Rain (NR): -100%
    """
    if pd.isna(dep_pct):
        return "Unknown"
    try:
        val = float(dep_pct)
        if val >= 60.0:
            return "Large Excess"
        elif val >= 20.0:
            return "Excess"
        elif val >= -19.0:
            return "Normal"
        elif val >= -59.0:
            return "Deficient"
        elif val > -100.0:
            return "Large Deficient"
        else:
            return "No Rain"
    except (ValueError, TypeError):
        return "Unknown"

def process_hobli_hierarchy(df, level_col, name_col, year):
    """
    Forward-fill district and taluk names across hierarchical hobli rows.
    """
    records = []
    current_district = None
    current_taluk = None

    for _, row in df.iterrows():
        level = str(row[level_col]).strip().upper() if pd.notna(row[level_col]) else ""
        raw_name = clean_name(row[name_col])
        if not raw_name:
            continue

        if level == "D":
            current_district = standardize_district(raw_name)
            current_taluk = None
            admin_level = "DISTRICT"
            item_name = current_district
        elif level == "T":
            current_taluk = raw_name.title()
            admin_level = "TALUK"
            item_name = current_taluk
        elif level == "H":
            admin_level = "HOBLI"
            item_name = raw_name
        else:
            # Regional averages or State rows
            admin_level = "REGION"
            item_name = raw_name

        rec = {
            "year": int(year),
            "admin_level": admin_level,
            "district_name": current_district,
            "taluk_name": current_taluk,
            "location_name": item_name
        }
        records.append((rec, row))
    return records

def clean_datasets():
    ksndmc_raw = Path("data/raw/ksndmc")
    out_dir = Path("data/processed/rainfall")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("--- 1. Processing 2021 Hobli & Taluk Seasonal ---")
    f_2021_h = ksndmc_raw / "741349d2-9f58-45ae-9744-b6d5c10a8b7f.csv"
    df21 = pd.read_csv(f_2021_h)
    
    # Columns in df21:
    # 'District(D)/Taluk(T)/Hobli(H)', 'Sl No', 'District/Taluk/Hobli',
    # 'Pre-monsoon Normal (mm)', 'Pre-Monsoon Actual (mm)', '%DEP',
    # 'Southwest Monsoon Normal(mm)', 'SWM Actual(mm)', '%DEP.1',
    # 'North East Monsoon Normal(mm)', 'NEM Actual MM(mm)', '%DEP.2',
    # 'Annual Normal(mm)', 'Annual Actual (mm)', '%DEP.3'
    
    rec_tuples = process_hobli_hierarchy(df21, "District(D)/Taluk(T)/Hobli(H)", "District/Taluk/Hobli", 2021)
    cleaned_rows_2021 = []
    for meta, r in rec_tuples:
        row_dict = {
            **meta,
            "pre_monsoon_normal_mm": pd.to_numeric(r["Pre-monsoon Normal (mm)"], errors="coerce"),
            "pre_monsoon_actual_mm": pd.to_numeric(r["Pre-Monsoon Actual (mm)"], errors="coerce"),
            "pre_monsoon_dep_pct": pd.to_numeric(r["%DEP"], errors="coerce"),
            "swm_normal_mm": pd.to_numeric(r["Southwest Monsoon Normal(mm)"], errors="coerce"),
            "swm_actual_mm": pd.to_numeric(r["SWM Actual(mm)"], errors="coerce"),
            "swm_dep_pct": pd.to_numeric(r["%DEP.1"], errors="coerce"),
            "nem_normal_mm": pd.to_numeric(r["North East Monsoon Normal(mm)"], errors="coerce"),
            "nem_actual_mm": pd.to_numeric(r["NEM Actual MM(mm)"], errors="coerce"),
            "nem_dep_pct": pd.to_numeric(r["%DEP.2"], errors="coerce"),
            "annual_normal_mm": pd.to_numeric(r["Annual Normal(mm)"], errors="coerce"),
            "annual_actual_mm": pd.to_numeric(r["Annual Actual (mm)"], errors="coerce"),
            "annual_dep_pct": pd.to_numeric(r["%DEP.3"], errors="coerce"),
        }
        row_dict["annual_classification"] = classify_departure(row_dict["annual_dep_pct"])
        cleaned_rows_2021.append(row_dict)

    df_2021_clean = pd.DataFrame(cleaned_rows_2021)
    csv_2021 = out_dir / "karnataka_hobli_rainfall_2021_clean.csv"
    df_2021_clean.to_csv(csv_2021, index=False)
    print(f"Saved: {csv_2021} ({len(df_2021_clean)} rows)")

    print("--- 2. Processing 2024 Hobli & Taluk Annual ---")
    f_2024_h = ksndmc_raw / "0ec5ad8d-be55-4e92-a942-6918c025735b.csv"
    df24 = pd.read_csv(f_2024_h)
    
    rec_tuples_24 = process_hobli_hierarchy(df24, "District(D)/Taluk(T)/Hobli(H)", "Name", 2024)
    cleaned_rows_2024 = []
    for meta, r in rec_tuples_24:
        row_dict = {
            **meta,
            "annual_normal_mm": pd.to_numeric(r["Normal (mm)"], errors="coerce"),
            "annual_actual_mm": pd.to_numeric(r["Actual (mm)"], errors="coerce"),
            "annual_dep_pct": pd.to_numeric(r["Departure (%)"], errors="coerce"),
        }
        row_dict["annual_classification"] = classify_departure(row_dict["annual_dep_pct"])
        cleaned_rows_2024.append(row_dict)

    df_2024_clean = pd.DataFrame(cleaned_rows_2024)
    csv_2024 = out_dir / "karnataka_hobli_rainfall_2024_clean.csv"
    df_2024_clean.to_csv(csv_2024, index=False)
    print(f"Saved: {csv_2024} ({len(df_2024_clean)} rows)")

    print("--- 3. Processing Parent Yearly District Rainfalls (2021, 2022, 2024, 2025) ---")
    # 2021 District
    d21 = pd.read_csv(ksndmc_raw / "97abb95d-1fdf-4b6c-950f-0b0fe5982614.csv")
    rows_dist_21 = []
    for _, r in d21.iterrows():
        dname = clean_name(r["District"])
        if not dname or "STATE" in dname.upper() or dname.startswith(("1.", "2.", "3.", "4.")):
            continue
        norm = pd.to_numeric(r["Annual Normal (mm)"], errors="coerce")
        act = pd.to_numeric(r["Annual Actual (mm)"], errors="coerce")
        dep = pd.to_numeric(r["%DEP"], errors="coerce")
        rows_dist_21.append({
            "year": 2021,
            "district_name": standardize_district(dname),
            "annual_normal_mm": norm,
            "annual_actual_mm": act,
            "annual_dep_pct": dep,
            "classification": classify_departure(dep)
        })

    # 2022 District
    d22 = pd.read_csv(ksndmc_raw / "ea869db4-2f50-4b13-8c94-eaa0aafb36b5.csv")
    rows_dist_22 = []
    for _, r in d22.iterrows():
        dname = clean_name(r["District"])
        if not dname or "STATE" in dname.upper():
            continue
        norm = pd.to_numeric(r["Normal (mm)"], errors="coerce")
        act = pd.to_numeric(r["Actual (mm)"], errors="coerce")
        dep = pd.to_numeric(r["Departure (%)"], errors="coerce")
        rows_dist_22.append({
            "year": 2022,
            "district_name": standardize_district(dname),
            "annual_normal_mm": norm,
            "annual_actual_mm": act,
            "annual_dep_pct": dep,
            "classification": classify_departure(dep)
        })

    # 2024 District
    d24 = pd.read_csv(ksndmc_raw / "f28d92e7-7e61-4d58-84a7-52e2ab6ee469.csv")
    rows_dist_24 = []
    for _, r in d24.iterrows():
        dname = clean_name(r["District"])
        if not dname or "STATE" in dname.upper():
            continue
        norm = pd.to_numeric(r["Total Normal (mm)"], errors="coerce")
        act = pd.to_numeric(r["Total Actual (mm)"], errors="coerce")
        dep = pd.to_numeric(r["Total Departure (%)"], errors="coerce")
        rows_dist_24.append({
            "year": 2024,
            "district_name": standardize_district(dname),
            "annual_normal_mm": norm,
            "annual_actual_mm": act,
            "annual_dep_pct": dep,
            "classification": classify_departure(dep)
        })

    # 2025 District
    d25 = pd.read_csv(ksndmc_raw / "ka_dist_rainfall_2025.csv")
    rows_dist_25 = []
    for _, r in d25.iterrows():
        dname = clean_name(r["District"])
        if not dname or "STATE" in dname.upper():
            continue
        norm = pd.to_numeric(r["Annual Normal"], errors="coerce")
        act = pd.to_numeric(r["Annual Actual"], errors="coerce")
        dep = pd.to_numeric(r["Annual Departure (%)"], errors="coerce")
        rows_dist_25.append({
            "year": 2025,
            "district_name": standardize_district(dname),
            "annual_normal_mm": norm,
            "annual_actual_mm": act,
            "annual_dep_pct": dep,
            "classification": classify_departure(dep)
        })

    df_district_all = pd.concat([
        pd.DataFrame(rows_dist_21),
        pd.DataFrame(rows_dist_22),
        pd.DataFrame(rows_dist_24),
        pd.DataFrame(rows_dist_25)
    ], ignore_index=True)

    df_district_all = df_district_all.sort_values(by=["district_name", "year"]).reset_index(drop=True)
    csv_dist_long = out_dir / "karnataka_district_annual_rainfall_2021_2025_long.csv"
    df_district_all.to_csv(csv_dist_long, index=False)
    print(f"Saved Long-format District History: {csv_dist_long} ({len(df_district_all)} rows)")

    # Wide-format District Comparison
    piv_act = df_district_all.pivot(index="district_name", columns="year", values="annual_actual_mm").add_prefix("actual_rainfall_mm_")
    piv_dep = df_district_all.pivot(index="district_name", columns="year", values="annual_dep_pct").add_prefix("departure_pct_")
    piv_norm = df_district_all.groupby("district_name")["annual_normal_mm"].first().rename("normal_rainfall_mm")

    df_district_wide = pd.concat([piv_norm, piv_act, piv_dep], axis=1).reset_index()
    csv_dist_wide = out_dir / "karnataka_district_annual_rainfall_comparison_wide.csv"
    df_district_wide.to_csv(csv_dist_wide, index=False)
    print(f"Saved Wide-format District History: {csv_dist_wide} ({len(df_district_wide)} rows)")

    # 4. District Seasonal Breakdowns (2021, 2024, 2025 combined)
    seasonal_rows = []
    # From 2021
    d21_dist_only = df_2021_clean[df_2021_clean["admin_level"] == "DISTRICT"]
    for _, r in d21_dist_only.iterrows():
        seasonal_rows.append({
            "year": 2021,
            "district_name": r["district_name"],
            "pre_monsoon_normal_mm": r["pre_monsoon_normal_mm"],
            "pre_monsoon_actual_mm": r["pre_monsoon_actual_mm"],
            "pre_monsoon_dep_pct": r["pre_monsoon_dep_pct"],
            "swm_normal_mm": r["swm_normal_mm"],
            "swm_actual_mm": r["swm_actual_mm"],
            "swm_dep_pct": r["swm_dep_pct"],
            "nem_normal_mm": r["nem_normal_mm"],
            "nem_actual_mm": r["nem_actual_mm"],
            "nem_dep_pct": r["nem_dep_pct"],
            "annual_normal_mm": r["annual_normal_mm"],
            "annual_actual_mm": r["annual_actual_mm"],
            "annual_dep_pct": r["annual_dep_pct"],
            "classification": r["annual_classification"]
        })

    # From 2024
    for _, r in d24.iterrows():
        dname = clean_name(r["District"])
        if not dname or "STATE" in dname.upper():
            continue
        seasonal_rows.append({
            "year": 2024,
            "district_name": standardize_district(dname),
            "pre_monsoon_normal_mm": pd.to_numeric(r["Pre-Monsoon Normal (%)"], errors="coerce"),
            "pre_monsoon_actual_mm": pd.to_numeric(r["Pre-Monsoon Actual (%)"], errors="coerce"),
            "pre_monsoon_dep_pct": pd.to_numeric(r["Pre-Monsoon Departure (%)"], errors="coerce"),
            "swm_normal_mm": pd.to_numeric(r["SWM Normal"], errors="coerce"),
            "swm_actual_mm": pd.to_numeric(r["SWM Actual"], errors="coerce"),
            "swm_dep_pct": pd.to_numeric(r["SWM Departure (%)"], errors="coerce"),
            "nem_normal_mm": pd.to_numeric(r["NEM Normal (mm)"], errors="coerce"),
            "nem_actual_mm": pd.to_numeric(r["NEM Actual (mm)"], errors="coerce"),
            "nem_dep_pct": pd.to_numeric(r["NEM Departure(%)"], errors="coerce"),
            "annual_normal_mm": pd.to_numeric(r["Total Normal (mm)"], errors="coerce"),
            "annual_actual_mm": pd.to_numeric(r["Total Actual (mm)"], errors="coerce"),
            "annual_dep_pct": pd.to_numeric(r["Total Departure (%)"], errors="coerce"),
            "classification": classify_departure(pd.to_numeric(r["Total Departure (%)"], errors="coerce"))
        })

    # From 2025
    for _, r in d25.iterrows():
        dname = clean_name(r["District"])
        if not dname or "STATE" in dname.upper():
            continue
        seasonal_rows.append({
            "year": 2025,
            "district_name": standardize_district(dname),
            "pre_monsoon_normal_mm": pd.to_numeric(r["Pre Monsoon Normal"], errors="coerce"),
            "pre_monsoon_actual_mm": pd.to_numeric(r["Pre Monsoon Actual"], errors="coerce"),
            "pre_monsoon_dep_pct": pd.to_numeric(r["Pre Monsoon Dep (%)"], errors="coerce"),
            "swm_normal_mm": pd.to_numeric(r["SWM Normal"], errors="coerce"),
            "swm_actual_mm": pd.to_numeric(r["SWM Actual"], errors="coerce"),
            "swm_dep_pct": pd.to_numeric(r["SWM Departure"], errors="coerce"),
            "nem_normal_mm": pd.to_numeric(r["NEM Normal"], errors="coerce"),
            "nem_actual_mm": pd.to_numeric(r["NEM Actual"], errors="coerce"),
            "nem_dep_pct": pd.to_numeric(r["NEM Departure"], errors="coerce"),
            "annual_normal_mm": pd.to_numeric(r["Annual Normal"], errors="coerce"),
            "annual_actual_mm": pd.to_numeric(r["Annual Actual"], errors="coerce"),
            "annual_dep_pct": pd.to_numeric(r["Annual Departure (%)"], errors="coerce"),
            "classification": classify_departure(pd.to_numeric(r["Annual Departure (%)"], errors="coerce"))
        })

    df_seasonal = pd.DataFrame(seasonal_rows).sort_values(by=["district_name", "year"]).reset_index(drop=True)
    csv_seasonal = out_dir / "karnataka_district_seasonal_rainfall_2021_2025.csv"
    df_seasonal.to_csv(csv_seasonal, index=False)
    print(f"Saved District Seasonal History: {csv_seasonal} ({len(df_seasonal)} rows)")

    # Write master Excel with clean formatted sheets
    master_excel = Path("data/processed/rainfall/karnataka_rainfall_master_clean.xlsx")
    with pd.ExcelWriter(master_excel, engine="openpyxl") as writer:
        df_district_wide.to_excel(writer, sheet_name="District_Annual_Comparison", index=False)
        df_district_all.to_excel(writer, sheet_name="District_Annual_Long", index=False)
        df_seasonal.to_excel(writer, sheet_name="District_Seasonal_MultiYear", index=False)
        df_2024_clean.to_excel(writer, sheet_name="2024_Hobli_Taluk_Clean", index=False)
        df_2021_clean.to_excel(writer, sheet_name="2021_Hobli_Taluk_Clean", index=False)
    print(f"Updated Master Excel: {master_excel}")

if __name__ == "__main__":
    clean_datasets()
