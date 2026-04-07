"""Tests for catalog-derived predicted eclipse geometry."""
import math
import pytest

from server.services.predicted_geometry import (
    expected_separation_from_gamma,
    solar_disk_radii,
    lunar_shadow_radii,
    approach_angle_from_gamma,
)

# --- Constants for reference ---
# Mean Moon distance ~384400 km, Earth radius ~6371 km
# arctan(1.0 * 6371 / 384400) ≈ 0.949° ≈ 56.9'


class TestExpectedSeparationFromGamma:
    def test_zero_gamma(self):
        """Gamma=0 means perfect alignment, separation should be ~0."""
        sep = expected_separation_from_gamma(0.0)
        assert sep == pytest.approx(0.0, abs=0.01)

    def test_gamma_one(self):
        """Gamma=1.0 should give ~57 arcminutes."""
        sep = expected_separation_from_gamma(1.0)
        assert 50 < sep < 65  # approximately 57'

    def test_negative_gamma(self):
        """Sign doesn't affect separation magnitude."""
        sep_pos = expected_separation_from_gamma(0.5)
        sep_neg = expected_separation_from_gamma(-0.5)
        assert sep_pos == pytest.approx(sep_neg, abs=0.01)

    def test_small_gamma(self):
        """Small gamma should give small separation, roughly linear."""
        sep = expected_separation_from_gamma(0.1)
        assert 3 < sep < 8  # roughly 5.7'


class TestSolarDiskRadii:
    def test_total_eclipse(self):
        """magnitude > 1 means Moon is larger than Sun."""
        moon_r, sun_r = solar_disk_radii(magnitude=1.05)
        assert moon_r > sun_r
        assert 14 < moon_r < 18
        assert 14 < sun_r < 18

    def test_annular_eclipse(self):
        """magnitude < 1 means Moon is smaller than Sun."""
        moon_r, sun_r = solar_disk_radii(magnitude=0.92)
        assert moon_r < sun_r

    def test_magnitude_one(self):
        """magnitude = 1 means equal sizes."""
        moon_r, sun_r = solar_disk_radii(magnitude=1.0)
        assert moon_r == pytest.approx(sun_r, abs=0.1)


class TestLunarShadowRadii:
    def test_total_lunar(self):
        """Total lunar eclipse with known magnitudes."""
        umbra_r, penumbra_r, moon_r = lunar_shadow_radii(
            um_mag=1.19, pen_mag=2.16, gamma=0.37
        )
        assert umbra_r > 0
        assert penumbra_r > umbra_r
        assert moon_r > 0
        assert 14 < moon_r < 18

    def test_penumbral_only(self):
        """Penumbral eclipse: um_mag is negative (Moon doesn't enter umbra)."""
        umbra_r, penumbra_r, moon_r = lunar_shadow_radii(
            um_mag=-0.03, pen_mag=1.04, gamma=-1.01
        )
        assert umbra_r > 0  # umbra still exists, Moon just doesn't enter it
        assert penumbra_r > umbra_r


class TestApproachAngle:
    def test_positive_gamma_north(self):
        """Positive gamma means Moon passes north of center."""
        angle = approach_angle_from_gamma(0.5)
        assert 0 < angle < 180

    def test_negative_gamma_south(self):
        """Negative gamma means Moon passes south of center."""
        angle = approach_angle_from_gamma(-0.5)
        assert 180 < angle < 360

    def test_zero_gamma(self):
        """Zero gamma — approach angle is arbitrary (dead center)."""
        angle = approach_angle_from_gamma(0.0)
        assert 0 <= angle < 360
