"""
Smoke tests: verify helpers and TychosSystem basics work before
running the full eclipse suite.
"""
import numpy as np
import pytest
from tychos_skyfield import baselib as T
from helpers import angular_separation, scan_min_separation, scan_lunar_eclipse


class TestAngularSeparation:
    def test_identical_points(self):
        assert angular_separation(1.0, 0.5, 1.0, 0.5) == 0.0

    def test_90_degrees(self):
        sep = angular_separation(0, 0, np.pi / 2, 0)
        assert abs(sep - np.pi / 2) < 1e-10

    def test_180_degrees(self):
        sep = angular_separation(0, 0, np.pi, 0)
        assert abs(sep - np.pi) < 1e-10

    def test_near_zero_stable(self):
        sep = angular_separation(1.0, 0.5, 1.001, 0.5)
        assert sep > 0
        assert not np.isnan(sep)

    def test_poles(self):
        sep = angular_separation(0, np.pi / 2, np.pi, np.pi / 2)
        assert abs(sep) < 1e-10  # both at north pole


class TestTychosSystemSanity:
    def test_sun_radec_at_default_time(self):
        system = T.TychosSystem()
        ra, dec, dist = system['sun'].radec_direct(
            system['earth'], epoch='j2000', formatted=False)
        assert not np.isnan(ra)
        assert not np.isnan(dec)
        assert dist > 0
        # Sun RA should be somewhere in 0-2pi
        assert 0 <= ra < 2 * np.pi

    def test_moon_radec_at_default_time(self):
        system = T.TychosSystem()
        ra, dec, dist = system['moon'].radec_direct(
            system['earth'], epoch='j2000', formatted=False)
        assert not np.isnan(ra)
        assert not np.isnan(dec)
        assert dist > 0

    def test_scan_runs(self):
        system = T.TychosSystem()
        min_sep, best_jd, *_ = scan_min_separation(system, 2451717.0, half_window_hours=0.5)
        assert min_sep > 0
        assert not np.isnan(min_sep)

    def test_lunar_scan_runs(self):
        system = T.TychosSystem()
        min_sep, best_jd, *_ = scan_lunar_eclipse(system, 2451717.0, half_window_hours=0.5)
        assert min_sep > 0
        assert not np.isnan(min_sep)


class TestFalsePositives:
    """Non-eclipse new/full moon dates — thresholds should NOT be met."""

    # 5 new moons that are NOT solar eclipses (well away from eclipse dates)
    NEW_MOONS_NO_ECLIPSE = [
        2451930.5,   # 2001-01-24
        2452281.5,   # 2002-01-13
        2452635.5,   # 2003-01-02
        2453371.5,   # 2005-01-10
        2454102.5,   # 2007-01-19
    ]

    # 5 full moons that are NOT lunar eclipses
    FULL_MOONS_NO_ECLIPSE = [
        2451944.5,   # 2001-02-08
        2452295.5,   # 2002-01-28
        2452649.5,   # 2003-01-18
        2453385.5,   # 2005-01-25
        2454116.5,   # 2007-02-02
    ]

    @pytest.mark.parametrize("jd", NEW_MOONS_NO_ECLIPSE)
    def test_no_solar_eclipse(self, jd):
        from helpers import SOLAR_DETECTION_THRESHOLD
        system = T.TychosSystem()
        min_sep, *_ = scan_min_separation(system, jd, half_window_hours=1)
        assert min_sep > SOLAR_DETECTION_THRESHOLD, (
            f"False positive solar eclipse at JD {jd}: sep={np.degrees(min_sep):.2f} deg")

    @pytest.mark.parametrize("jd", FULL_MOONS_NO_ECLIPSE)
    def test_no_lunar_eclipse(self, jd):
        from helpers import LUNAR_PENUMBRAL_RADIUS, MOON_MEAN_ANGULAR_RADIUS
        threshold = LUNAR_PENUMBRAL_RADIUS + MOON_MEAN_ANGULAR_RADIUS
        system = T.TychosSystem()
        min_sep, *_ = scan_lunar_eclipse(system, jd, half_window_hours=1)
        assert min_sep > threshold, (
            f"False positive lunar eclipse at JD {jd}: sep={np.degrees(min_sep):.2f} deg")
