import os
from pathlib import Path
import pandas as pd
import io

def generate_excel():
    # Read the raw data file if exists, or write and parse directly
    raw_file = Path("data/raw/rainfall/ksndmc/raw_rainfall_data.csv")
    out_file = Path("data/raw/rainfall/ksndmc/karnataka_rainfall_compiled.xlsx")
    out_file.parent.mkdir(parents=True, exist_ok=True)

    print("Reading and partitioning dataset blocks...")
    if not raw_file.exists():
        print(f"File {raw_file} not found yet. Creating from source...")

if __name__ == "__main__":
    generate_excel()
