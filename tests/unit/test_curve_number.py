"""
tests/unit/test_curve_number.py
────────────────────────────────
Unit tests for the SCS-CN runoff estimation module.

Run with: pytest tests/unit/test_curve_number.py -v
"""

import numpy as np
import pytest

from src.features.curve_number import (
    lookup_cn,
    compute_runoff_mm,
    compute_annual_runoff,
    compute_yield_m3,
    amc2_to_amc1,
    amc2_to_amc3,
)


class TestCNLookup:
    def test_cropland_hsg_b(self):
        cn = lookup_cn("cropland", "B")
        assert cn == 78.0

    def test_forest_hsg_a(self):
        cn = lookup_cn("forest", "A")
        assert cn == 25.0

    def test_waterbody_all_groups(self):
        for hsg in ["A", "B", "C", "D"]:
            assert lookup_cn("waterbody", hsg) == 100.0

    def test_amc1_lower_than_amc2(self):
        cn2 = lookup_cn("cropland", "B", amc="II")
        cn1 = lookup_cn("cropland", "B", amc="I")
        assert cn1 < cn2

    def test_amc3_higher_than_amc2(self):
        cn2 = lookup_cn("cropland", "B", amc="II")
        cn3 = lookup_cn("cropland", "B", amc="III")
        assert cn3 > cn2

    def test_unknown_lulc_returns_default(self):
        # Should not raise; returns default CN=75
        cn = lookup_cn("unknown_class", "B")
        assert cn == 75.0

    def test_case_insensitive(self):
        assert lookup_cn("CROPLAND", "b") == lookup_cn("cropland", "B")


class TestRunoffCalculation:
    def test_zero_rainfall_zero_runoff(self):
        q = compute_runoff_mm(0.0, 75.0)
        assert q == 0.0

    def test_below_initial_abstraction_zero_runoff(self):
        # S = (25400/75) - 254 = 84.67mm; Ia = 0.2 * 84.67 = 16.93mm
        # Rainfall of 10mm < Ia → Q = 0
        q = compute_runoff_mm(10.0, 75.0)
        assert q == 0.0

    def test_runoff_increases_with_rainfall(self):
        cn = 78.0
        q1 = compute_runoff_mm(50.0, cn)
        q2 = compute_runoff_mm(100.0, cn)
        assert q2 > q1 > 0

    def test_runoff_increases_with_cn(self):
        rain = 50.0
        q_low_cn = compute_runoff_mm(rain, 50.0)
        q_high_cn = compute_runoff_mm(rain, 90.0)
        assert q_high_cn > q_low_cn

    def test_waterbody_runoff_equals_rainfall(self):
        q = compute_runoff_mm(50.0, 100.0)
        assert q == pytest.approx(50.0)

    def test_vectorised_array_input(self):
        rain = np.array([0.0, 10.0, 50.0, 100.0, 200.0])
        cn = 78.0
        q = compute_runoff_mm(rain, cn)
        assert q.shape == rain.shape
        assert q[0] == 0.0
        assert np.all(np.diff(q) >= 0)

    def test_runoff_never_exceeds_rainfall(self):
        rain = np.linspace(0, 500, 100)
        q = compute_runoff_mm(rain, 85.0)
        assert np.all(q <= rain + 1e-9)

    def test_lambda_effect(self):
        # Lower lambda (0.1) means lower initial abstraction → more runoff
        q_02 = compute_runoff_mm(30.0, 80.0, lambda_=0.2)
        q_01 = compute_runoff_mm(30.0, 80.0, lambda_=0.1)
        assert q_01 >= q_02


class TestAnnualRunoff:
    def test_annual_runoff_structure(self):
        import pandas as pd
        daily = pd.Series(
            [0.0] * 300 + [50.0] * 30 + [100.0] * 35,
            index=pd.date_range("2022-01-01", periods=365),
        )
        result = compute_annual_runoff(daily, cn=78.0)
        assert "annual_runoff_mm" in result
        assert "annual_rainfall_mm" in result
        assert "n_runoff_events" in result
        assert "runoff_coefficient" in result
        assert result["annual_runoff_mm"] > 0
        assert 0 < result["runoff_coefficient"] <= 1.0

    def test_zero_rainfall_zero_annual_runoff(self):
        import pandas as pd
        daily = pd.Series(np.zeros(365), index=pd.date_range("2022-01-01", periods=365))
        result = compute_annual_runoff(daily, cn=78.0)
        assert result["annual_runoff_mm"] == 0.0
        assert result["n_runoff_events"] == 0


class TestYieldEstimation:
    def test_yield_calculation(self):
        # 100mm runoff, 1 ha = 10,000 m², 75% efficiency
        yield_m3 = compute_yield_m3(100.0, 10_000.0, 0.75)
        expected = (100.0 / 1000.0) * 10_000.0 * 0.75
        assert yield_m3 == pytest.approx(expected)

    def test_zero_runoff_zero_yield(self):
        assert compute_yield_m3(0.0, 10_000.0, 0.75) == 0.0

    def test_efficiency_scales_linearly(self):
        y1 = compute_yield_m3(50.0, 5_000.0, 0.5)
        y2 = compute_yield_m3(50.0, 5_000.0, 1.0)
        assert y2 == pytest.approx(y1 * 2.0)
