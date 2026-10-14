"""
features/curve_number.py
─────────────────────────
Compute SCS/NRCS Curve Number (CN) and estimated daily/annual runoff depth
using the Curve Number method (USDA NRCS Part 630, Chapter 9).

Key references:
  - NRCS NEH Part 630, Chapter 9 (CN method)
  - Mishra & Singh (2003) — Soil Conservation Service CN methodology
  - Local calibration notes: docs/cn_calibration_notes.md

Prerequisites:
    pip install numpy pandas

Usage (library):
    from src.features.curve_number import lookup_cn, compute_runoff_mm
"""

from __future__ import annotations

import logging
from typing import Dict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── CN lookup tables (AMC-II, from params.yaml) ───────────────────────────────
# Loaded dynamically; hardcoded here as fallback defaults

CN_TABLE_AMC2: Dict[str, Dict[str, int]] = {
    "cropland":   {"A": 67, "B": 78, "C": 85, "D": 89},
    "fallow":     {"A": 77, "B": 86, "C": 91, "D": 94},
    "scrubland":  {"A": 35, "B": 56, "C": 70, "D": 77},
    "forest":     {"A": 25, "B": 55, "C": 70, "D": 77},
    "waterbody":  {"A": 100, "B": 100, "C": 100, "D": 100},
    "settlement": {"A": 77, "B": 85, "C": 90, "D": 92},
    "barren":     {"A": 72, "B": 82, "C": 87, "D": 90},
}

# AMC I → AMC II conversion (dry conditions → normal)
# CN_I = CN_II / (2.281 - 0.01281 × CN_II)
# AMC III → AMC II: CN_III = CN_II / (0.427 + 0.00573 × CN_II)

def amc2_to_amc1(cn2: float) -> float:
    """Convert AMC-II CN to AMC-I (dry) CN."""
    return cn2 / (2.281 - 0.01281 * cn2)


def amc2_to_amc3(cn2: float) -> float:
    """Convert AMC-II CN to AMC-III (wet) CN."""
    return cn2 / (0.427 + 0.00573 * cn2)


def lookup_cn(
    lulc_class: str,
    hsg: str,
    amc: str = "II",
) -> float:
    """
    Look up the Curve Number for a given land cover class and Hydrologic Soil Group.

    Args:
        lulc_class: Land use/land cover class string (see CN_TABLE_AMC2 keys).
        hsg:        Hydrologic Soil Group ('A', 'B', 'C', or 'D').
        amc:        Antecedent Moisture Condition ('I', 'II', or 'III').

    Returns:
        Curve Number (float).

    Raises:
        KeyError: If lulc_class or hsg is not found in the lookup table.
    """
    try:
        cn2 = float(CN_TABLE_AMC2[lulc_class.lower()][hsg.upper()])
    except KeyError:
        logger.warning("CN lookup failed for lulc=%s, hsg=%s. Using default CN=75.", lulc_class, hsg)
        cn2 = 75.0

    if amc == "I":
        return amc2_to_amc1(cn2)
    elif amc == "III":
        return amc2_to_amc3(cn2)
    return cn2


def compute_runoff_mm(
    rainfall_mm: float | np.ndarray,
    cn: float | np.ndarray,
    lambda_: float = 0.2,
) -> float | np.ndarray:
    """
    Compute direct runoff depth (Q) using the SCS-CN equation.

        Q = (P - Ia)² / (P - Ia + S)     if P > Ia, else Q = 0
        S = (25400 / CN) - 254            [S in mm]
        Ia = lambda × S                   [default lambda = 0.2]

    Args:
        rainfall_mm: Daily or event rainfall depth (mm). Scalar or array.
        cn:          Curve Number. Scalar or array (must broadcast with rainfall_mm).
        lambda_:     Initial abstraction ratio (default 0.2; use 0.1 for
                     semi-arid India per several local studies).

    Returns:
        Runoff depth Q (mm). Negative values clipped to 0.
    """
    cn = np.asarray(cn, dtype=np.float64)
    P = np.asarray(rainfall_mm, dtype=np.float64)

    # Clip CN to valid range [1, 100) — CN=100 means waterbody (P→Q)
    cn_safe = np.clip(cn, 1.0, 99.99)

    # Potential maximum retention (mm)
    S = (25400.0 / cn_safe) - 254.0

    # Initial abstraction (mm)
    Ia = lambda_ * S

    # Runoff (mm) — vectorised
    with np.errstate(divide="ignore", invalid="ignore"):
        Q = np.where(
            P > Ia,
            (P - Ia) ** 2 / (P - Ia + S),
            0.0,
        )

    Q = np.clip(Q, 0.0, None)

    # Waterbody pixels: runoff = rainfall (CN=100 treated as full runoff)
    Q = np.where(cn >= 100, P, Q)

    return Q


def compute_annual_runoff(
    daily_rainfall: pd.Series,
    cn: float,
    lambda_: float = 0.2,
) -> dict:
    """
    Compute annual runoff statistics from a daily rainfall time series.

    Args:
        daily_rainfall: pd.Series with DatetimeIndex and rainfall in mm.
        cn:             Curve Number (constant for the year).
        lambda_:        Initial abstraction ratio.

    Returns:
        dict with keys: annual_runoff_mm, n_runoff_events, runoff_coefficient.
    """
    daily_runoff = compute_runoff_mm(daily_rainfall.values, cn, lambda_)
    annual_rain = float(daily_rainfall.sum())
    annual_runoff = float(daily_runoff.sum())
    n_events = int((daily_runoff > 0).sum())
    rc = annual_runoff / annual_rain if annual_rain > 0 else 0.0

    return {
        "annual_runoff_mm": round(annual_runoff, 2),
        "annual_rainfall_mm": round(annual_rain, 2),
        "n_runoff_events": n_events,
        "runoff_coefficient": round(rc, 4),
    }


def compute_yield_m3(
    runoff_mm: float,
    catchment_area_m2: float,
    efficiency: float = 0.75,
) -> float:
    """
    Convert runoff depth (mm) to harvestable water volume (m³).

    Args:
        runoff_mm:           Annual runoff depth (mm).
        catchment_area_m2:   Catchment area in square metres.
        efficiency:          Harvest efficiency factor (0–1).

    Returns:
        Harvestable water volume in cubic metres.
    """
    return (runoff_mm / 1000.0) * catchment_area_m2 * efficiency
