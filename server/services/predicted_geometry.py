"""Compute predicted eclipse geometry from NASA catalog parameters.

All derivations use pure geometry — no Skyfield, no Tychos.
"""
import math

# Mean values
R_EARTH_KM = 6371.0
D_MOON_MEAN_KM = 384400.0
SUN_MEAN_RADIUS_ARCMIN = 16.0  # mean solar angular radius


def expected_separation_from_gamma(gamma: float) -> float:
    """Derive expected Sun-Moon angular separation from gamma.

    Gamma is the distance of the shadow axis from Earth's center
    in Earth radii. Returns separation in arcminutes.
    """
    if gamma == 0.0:
        return 0.0
    rad = math.atan(abs(gamma) * R_EARTH_KM / D_MOON_MEAN_KM)
    return math.degrees(rad) * 60


def solar_disk_radii(magnitude: float) -> tuple[float, float]:
    """Derive Moon and Sun apparent radii from solar eclipse magnitude.

    For central eclipses, magnitude = D_moon / D_sun = R_moon / R_sun.
    Returns (moon_radius_arcmin, sun_radius_arcmin).
    """
    sun_r = SUN_MEAN_RADIUS_ARCMIN
    moon_r = magnitude * sun_r
    return moon_r, sun_r


def lunar_shadow_radii(
    um_mag: float, pen_mag: float, gamma: float
) -> tuple[float, float, float]:
    """Derive umbral radius, penumbral radius, and Moon radius from lunar catalog data.

    Umbral magnitude = fraction of Moon diameter inside umbra.
    Penumbral magnitude = fraction of Moon diameter inside penumbra.

    Geometry:
        um_mag = (R_umbra + R_moon - d) / D_moon
        pen_mag = (R_penumbra + R_moon - d) / D_moon

    where d = Moon-to-shadow-center distance (from gamma).

    Returns (umbra_radius_arcmin, penumbra_radius_arcmin, moon_radius_arcmin).
    """
    d = expected_separation_from_gamma(gamma)
    moon_r = 15.5  # mean Moon angular radius in arcminutes
    d_moon = 2 * moon_r

    umbra_r = um_mag * d_moon - moon_r + d
    penumbra_r = pen_mag * d_moon - moon_r + d

    # Clamp to reasonable minimums
    umbra_r = max(umbra_r, 5.0)
    penumbra_r = max(penumbra_r, umbra_r + 5.0)

    return umbra_r, penumbra_r, moon_r


def approach_angle_from_gamma(gamma: float) -> float:
    """Derive the Moon's approach angle from gamma sign.

    Positive gamma: Moon passes north of center → ~66.6°
    Negative gamma: Moon passes south → ~293.4°
    Zero: dead center, use 90° as default.

    Returns angle in degrees (0-360), measured counter-clockwise from East.
    """
    ecliptic_tilt = 23.44

    if gamma == 0.0:
        return 90.0

    if gamma > 0:
        return 90.0 - ecliptic_tilt
    else:
        return 270.0 + ecliptic_tilt
