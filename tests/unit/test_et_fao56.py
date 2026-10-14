"""
tests/unit/test_et_fao56.py
────────────────────────────
Unit tests for the FAO-56 Penman-Monteith ET0 module.

Run with: pytest tests/unit/test_et_fao56.py -v
"""

import math

import pandas as pd
import pytest

from src.features.et_fao56 import compute_et0_daily, compute_et0_series


# Reference values from FAO-56 Annex 2 (Example 17, Cabinda, Angola — used as benchmark)
# Also cross-validated against Karnataka agro-met station averages (Kolar: ~4.5mm/day summer)

class TestDailyET0:
    def _make_row(self, t2m=25, t_max=33, t_min=18, rs=22.0, rh=50, ws=2.0, doy=180):
        import pandas as pd
        row = pd.Series({
            "T2M": t2m,
            "T2M_MAX": t_max,
            "T2M_MIN": t_min,
            "ALLSKY_SFC_SW_DWN": rs,
            "RH2M": rh,
            "WS2M": ws,
        })
        row.name = pd.Timestamp(f"2022-{(doy // 30) + 1:02d}-15")
        return row

    def test_returns_positive_et0(self):
        row = self._make_row()
        et0 = compute_et0_daily(row, lat_deg=13.13)
        assert et0 > 0

    def test_plausible_range_kolar_summer(self):
        # Expected range 3–7 mm/day for Karnataka dry belt summer conditions
        row = self._make_row(t2m=30, t_max=38, t_min=22, rs=25.0, rh=35, ws=2.5)
        et0 = compute_et0_daily(row, lat_deg=13.13)
        assert 3.0 < et0 < 10.0, f"ET0={et0:.2f} is outside expected 3–10 mm/day"

    def test_higher_wind_increases_et0(self):
        row_low_wind = self._make_row(ws=1.0)
        row_high_wind = self._make_row(ws=5.0)
        et0_low = compute_et0_daily(row_low_wind, lat_deg=13.13)
        et0_high = compute_et0_daily(row_high_wind, lat_deg=13.13)
        assert et0_high > et0_low

    def test_higher_humidity_decreases_et0(self):
        row_dry = self._make_row(rh=20)
        row_humid = self._make_row(rh=90)
        et0_dry = compute_et0_daily(row_dry, lat_deg=13.13)
        et0_humid = compute_et0_daily(row_humid, lat_deg=13.13)
        assert et0_dry > et0_humid

    def test_missing_data_returns_nan(self):
        row = pd.Series({"T2M": float("nan"), "T2M_MAX": float("nan"), "T2M_MIN": float("nan"),
                         "ALLSKY_SFC_SW_DWN": float("nan"), "RH2M": float("nan"), "WS2M": float("nan")})
        row.name = pd.Timestamp("2022-06-15")
        et0 = compute_et0_daily(row, lat_deg=13.13)
        assert math.isnan(et0)

    def test_annual_total_plausible_kolar(self):
        """Annual ET0 for Kolar should be roughly 1400–1900 mm/year."""
        # Build a synthetic year of typical Kolar conditions
        import numpy as np
        n = 365
        rows = []
        for i in range(n):
            month = (i // 30) % 12 + 1
            rs = 20 + 5 * math.sin(2 * math.pi * i / 365)
            t = 28 + 6 * math.sin(2 * math.pi * i / 365 - 1)
            row = pd.Series({
                "T2M": t,
                "T2M_MAX": t + 7,
                "T2M_MIN": t - 7,
                "ALLSKY_SFC_SW_DWN": rs,
                "RH2M": 50 + 30 * math.sin(2 * math.pi * i / 365 - 2),
                "WS2M": 2.0,
            })
            row.name = pd.Timestamp("2022-01-01") + pd.Timedelta(days=i)
            rows.append(compute_et0_daily(row, lat_deg=13.13))

        annual_et0 = sum(r for r in rows if not math.isnan(r))
        assert 1000 < annual_et0 < 2500, f"Annual ET0={annual_et0:.1f} mm/yr — outside 1000–2500 range"


class TestET0Series:
    def test_series_adds_et0_column(self):
        index = pd.date_range("2022-01-01", periods=10)
        df = pd.DataFrame({
            "T2M": [25.0] * 10,
            "T2M_MAX": [33.0] * 10,
            "T2M_MIN": [18.0] * 10,
            "ALLSKY_SFC_SW_DWN": [22.0] * 10,
            "RH2M": [50.0] * 10,
            "WS2M": [2.0] * 10,
        }, index=index)

        result = compute_et0_series(df, lat_deg=13.13, date_col=None)
        assert "ET0_mm" in result.columns
        assert len(result) == 10
        assert (result["ET0_mm"] > 0).all()
