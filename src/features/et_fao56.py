"""
features/et_fao56.py
──────────────────────
Compute FAO-56 Penman-Monteith reference evapotranspiration (ET0)
from NASA POWER daily meteorological data.

Reference:
  Allen et al. (1998) — FAO Irrigation and Drainage Paper No. 56
  https://www.fao.org/3/x0490e/x0490e00.htm

Prerequisites:
    pip install numpy pandas

Usage (library):
    from src.features.et_fao56 import compute_et0_series
    et0 = compute_et0_series(df, lat=13.13)
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_et0_daily(
    row: pd.Series,
    lat_deg: float,
    elevation_m: float = 600.0,
) -> float:
    """
    Compute FAO-56 Penman-Monteith ET0 for a single day.

    Args:
        row:          pd.Series with keys:
                        T2M       — mean temperature (°C)
                        T2M_MAX   — max temperature (°C)
                        T2M_MIN   — min temperature (°C)
                        ALLSKY_SFC_SW_DWN — solar radiation (MJ m⁻² day⁻¹)
                        RH2M      — relative humidity (%)
                        WS2M      — wind speed at 2m (m s⁻¹)
        lat_deg:      Latitude in decimal degrees.
        elevation_m:  Elevation above sea level (m). Used for atm. pressure.

    Returns:
        ET0 in mm/day.
    """
    try:
        T_mean = float(row["T2M"])
        T_max = float(row["T2M_MAX"])
        T_min = float(row["T2M_MIN"])
        Rs = float(row["ALLSKY_SFC_SW_DWN"])    # MJ m-2 day-1
        RH = float(row["RH2M"])
        u2 = float(row["WS2M"])
        doy = int(row.name.day_of_year) if hasattr(row.name, "day_of_year") else 180
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("Missing met data: %s", exc)
        return float("nan")

    # Return NaN if any required input is NaN (not just missing keys)
    import math as _math
    if any(_math.isnan(v) for v in [T_mean, T_max, T_min, Rs, RH, u2]):
        return float("nan")

    # Atmospheric pressure (kPa) from elevation
    P_kPa = 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26

    # Psychrometric constant γ (kPa °C⁻¹)
    gamma = 0.000665 * P_kPa

    # Saturation vapour pressure (kPa)
    e_s_max = 0.6108 * math.exp(17.27 * T_max / (T_max + 237.3))
    e_s_min = 0.6108 * math.exp(17.27 * T_min / (T_min + 237.3))
    e_s = (e_s_max + e_s_min) / 2.0

    # Actual vapour pressure (kPa)
    e_a = (RH / 100.0) * e_s

    # Slope of saturation vapour pressure curve (kPa °C⁻¹)
    delta = 4098 * (0.6108 * math.exp(17.27 * T_mean / (T_mean + 237.3))) / (T_mean + 237.3) ** 2

    # Extraterrestrial radiation (Ra) — FAO-56 Eq. 21
    lat_rad = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    delta_s = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(-math.tan(lat_rad) * math.tan(delta_s))
    Ra = (24 * 60 / math.pi) * 0.0820 * dr * (
        ws * math.sin(lat_rad) * math.sin(delta_s)
        + math.cos(lat_rad) * math.cos(delta_s) * math.sin(ws)
    )

    # Clear-sky solar radiation
    Rso = (0.75 + 2e-5 * elevation_m) * Ra

    # Net shortwave radiation (Rns)
    alpha = 0.23   # reference grass albedo
    Rns = (1 - alpha) * Rs

    # Net longwave radiation (Rnl) — FAO-56 Eq. 39
    sigma = 4.903e-9  # Stefan-Boltzmann [MJ K-4 m-2 day-1]
    T_max_K = T_max + 273.16
    T_min_K = T_min + 273.16
    ratio = min(Rs / Rso, 1.0) if Rso > 0 else 1.0
    Rnl = sigma * ((T_max_K**4 + T_min_K**4) / 2) * (0.34 - 0.14 * math.sqrt(max(e_a, 0))) * (1.35 * ratio - 0.35)

    # Net radiation (Rn)
    Rn = Rns - Rnl

    # Soil heat flux G ≈ 0 for daily calculation (FAO-56 assumption)
    G = 0.0

    # FAO-56 Penman-Monteith ET0 (mm day⁻¹) — Eq. 6
    numerator = (0.408 * delta * (Rn - G)) + gamma * (900 / (T_mean + 273)) * u2 * (e_s - e_a)
    denominator = delta + gamma * (1 + 0.34 * u2)

    ET0 = numerator / denominator if denominator != 0 else float("nan")
    return max(0.0, ET0)


def compute_et0_series(
    df: pd.DataFrame,
    lat_deg: float,
    elevation_m: float = 600.0,
    date_col: Optional[str] = "date",
) -> pd.DataFrame:
    """
    Compute daily ET0 for a DataFrame of NASA POWER meteorological data.

    Args:
        df:          DataFrame with met columns (T2M, T2M_MAX, T2M_MIN,
                     ALLSKY_SFC_SW_DWN, RH2M, WS2M) and a date column or DatetimeIndex.
        lat_deg:     Latitude (decimal degrees).
        elevation_m: Elevation in metres (default 600m, typical for Kolar plateau).
        date_col:    Name of the date column. Set to None if df already has DatetimeIndex.

    Returns:
        Original DataFrame with an added 'ET0_mm' column.
    """
    if date_col and date_col in df.columns:
        df = df.set_index(pd.to_datetime(df[date_col])).drop(columns=[date_col])

    df = df.copy()
    df["ET0_mm"] = df.apply(
        lambda row: compute_et0_daily(row, lat_deg, elevation_m),
        axis=1,
    )

    logger.info(
        "Computed ET0 for %d days. Mean=%.2f mm/day, Annual total=%.1f mm",
        len(df),
        df["ET0_mm"].mean(),
        df["ET0_mm"].sum(),
    )

    return df
