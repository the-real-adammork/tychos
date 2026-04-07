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
