"""
Parser to convert pasted Karnataka multi-year rainfall text datasets
into a structured multi-sheet Excel file.
"""
from pathlib import Path
import pandas as pd
import io

def parse_and_export():
    raw_path = Path("data/raw/rainfall/ksndmc/raw_pasted_data.txt")
    if not raw_path.exists():
        print(f"Error: {raw_path} does not exist.")
        return

    content = raw_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Find the split markers based on headers
    # Block 1: "District(D)/Taluk(T)/Hobli(H),Sl No,District/Taluk/Hobli..."
    # Block 2: "District,Annual Normal (mm),Annual Actual (mm),%DEP,Excess/Normal/Large Excess/Deficienct/Large Deficient"
    # Block 3: "Sl. No,District,Normal (mm),Actual (mm),Departure (%)"
    # Block 4: "District(D)/Taluk(T)/Hobli(H),Name,Normal (mm),Actual (mm),Departure (%)"
    # Block 5: "District,Pre-Monsoon Normal (%),Pre-Monsoon Actual (%),Pre-Monsoon Departure (%),SWM Normal..."

    headers = [
        "District(D)/Taluk(T)/Hobli(H),Sl No,District/Taluk/Hobli",
        "District,Annual Normal (mm),Annual Actual (mm),%DEP,Excess/Normal/Large Excess/Deficienct/Large Deficient",
        "Sl. No,District,Normal (mm),Actual (mm),Departure (%)",
        "District(D)/Taluk(T)/Hobli(H),Name,Normal (mm),Actual (mm),Departure (%)",
        "District,Pre-Monsoon Normal (%),Pre-Monsoon Actual (%),Pre-Monsoon Departure (%)"
    ]

    header_indices = []
    for idx, line in enumerate(lines):
        clean_line = line.strip().lstrip('\ufeff')
        for h_idx, h in enumerate(headers):
            if clean_line.startswith(h):
                header_indices.append((idx, h_idx))
                break

    print(f"Identified headers at lines: {header_indices}")

    excel_path = Path("data/raw/rainfall/ksndmc/karnataka_rainfall_compiled.xlsx")
    excel_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        for i in range(len(header_indices)):
            start_line, h_type = header_indices[i]
            end_line = header_indices[i+1][0] if i + 1 < len(header_indices) else len(lines)
            
            block_lines = lines[start_line:end_line]
            block_text = "\n".join(block_lines)
            
            df = pd.read_csv(io.StringIO(block_text))
            
            sheet_names = [
                "Hobli_Taluk_Detailed_S1",
                "District_Annual_Summary_1",
                "District_Rankings_2022",
                "Hobli_Taluk_Annual_S2",
                "District_Seasonal_Summary_2"
            ]
            sheet_name = sheet_names[h_type]
            print(f"Writing sheet: {sheet_name} with shape {df.shape}")
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"Successfully compiled all tables into {excel_path}!")

if __name__ == "__main__":
    parse_and_export()
