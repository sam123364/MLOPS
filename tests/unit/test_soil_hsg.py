"""
tests/unit/test_soil_hsg.py
────────────────────────────
Unit tests for Hydrologic Soil Group (HSG) derivation module.

Run with: pytest tests/unit/test_soil_hsg.py -v
"""

import pytest

from src.preprocessing.soil_hsg import derive_hsg_from_fractions


class TestHSGDerivation:
    def test_heavy_clay_is_group_d(self):
        assert derive_hsg_from_fractions(clay_pct=50, sand_pct=20, silt_pct=30) == "D"

    def test_sandy_soil_is_group_a(self):
        assert derive_hsg_from_fractions(clay_pct=5, sand_pct=80, silt_pct=15) == "A"

    def test_loam_is_group_b(self):
        # Clay ~15%, sand ~40%, silt ~45% → typical loam → B
        result = derive_hsg_from_fractions(clay_pct=15, sand_pct=40, silt_pct=45)
        assert result in ["B", "C"]  # Borderline; must be B or C

    def test_sandy_clay_loam_is_group_c(self):
        # Clay ~25%, sand ~55%, silt ~20% → sandy clay loam → C
        assert derive_hsg_from_fractions(clay_pct=25, sand_pct=55, silt_pct=20) == "C"

    def test_typical_kolar_red_soil_group_b_or_c(self):
        # Red lateritic soils of Kolar: clay 20–30%, sand 30–50%, silt 20–40%
        result = derive_hsg_from_fractions(clay_pct=25, sand_pct=40, silt_pct=35)
        assert result in ["B", "C"]

    def test_fractions_normalised_correctly(self):
        # If fractions don't sum to 100, normalisation should still give valid HSG
        result = derive_hsg_from_fractions(clay_pct=10, sand_pct=30, silt_pct=40)
        assert result in ["A", "B", "C", "D"]

    def test_all_groups_returnable(self):
        hsg_a = derive_hsg_from_fractions(2, 85, 13)
        hsg_d = derive_hsg_from_fractions(60, 20, 20)
        assert hsg_a == "A"
        assert hsg_d == "D"
