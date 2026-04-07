import pytest

from server.research.allowlist import (
    expand_globs,
    check_diff_against_allowlist,
    AllowlistViolation,
)

ALL_FIELDS = (
    "orbit_radius",
    "orbit_center_a",
    "orbit_center_b",
    "orbit_center_c",
    "orbit_tilt_a",
    "orbit_tilt_b",
    "start_pos",
    "speed",
)


def _params(moon_speed=83.0, sun_speed=6.28, mars_speed=-3.34):
    return {
        "moon": {f: 0.0 for f in ALL_FIELDS} | {"speed": moon_speed},
        "sun": {f: 0.0 for f in ALL_FIELDS} | {"speed": sun_speed},
        "mars": {f: 0.0 for f in ALL_FIELDS} | {"speed": mars_speed},
    }


def test_expand_globs_expands_body_wildcard():
    expanded = expand_globs(["moon.*"], bodies=["moon", "sun", "mars"])
    assert set(expanded) == {f"moon.{f}" for f in ALL_FIELDS}


def test_expand_globs_passes_through_explicit_keys():
    expanded = expand_globs(["moon.speed", "sun.start_pos"], bodies=["moon", "sun"])
    assert set(expanded) == {"moon.speed", "sun.start_pos"}


def test_expand_globs_combines_glob_and_explicit():
    expanded = expand_globs(["moon.*", "sun.speed"], bodies=["moon", "sun"])
    assert "moon.orbit_radius" in expanded
    assert "moon.speed" in expanded
    assert "sun.speed" in expanded
    assert "sun.start_pos" not in expanded


def test_check_diff_accepts_change_inside_allowlist():
    baseline = _params(moon_speed=83.0)
    current = _params(moon_speed=83.5)
    check_diff_against_allowlist(
        current, baseline, allowlist_globs=["moon.*"], known_bodies=list(baseline.keys())
    )


def test_check_diff_rejects_change_outside_allowlist():
    baseline = _params(mars_speed=-3.34)
    current = _params(mars_speed=-3.40)
    with pytest.raises(AllowlistViolation) as exc:
        check_diff_against_allowlist(
            current, baseline, allowlist_globs=["moon.*"], known_bodies=list(baseline.keys())
        )
    assert "mars.speed" in str(exc.value)


def test_check_diff_rejects_added_key():
    baseline = _params()
    current = _params()
    current["moon"]["new_field"] = 1.0
    with pytest.raises(AllowlistViolation) as exc:
        check_diff_against_allowlist(
            current, baseline, allowlist_globs=["moon.*"], known_bodies=list(baseline.keys())
        )
    assert "added" in str(exc.value).lower()


def test_check_diff_rejects_removed_key():
    baseline = _params()
    current = _params()
    del current["moon"]["start_pos"]
    with pytest.raises(AllowlistViolation) as exc:
        check_diff_against_allowlist(
            current, baseline, allowlist_globs=["moon.*"], known_bodies=list(baseline.keys())
        )
    assert "removed" in str(exc.value).lower()


def test_check_diff_rejects_added_body():
    baseline = _params()
    current = _params()
    current["pluto"] = {f: 0.0 for f in ALL_FIELDS}
    with pytest.raises(AllowlistViolation):
        check_diff_against_allowlist(
            current, baseline, allowlist_globs=["moon.*"], known_bodies=list(baseline.keys())
        )


def test_check_diff_rejects_non_numeric_value():
    baseline = _params()
    current = _params()
    current["moon"]["speed"] = "fast"
    with pytest.raises(AllowlistViolation) as exc:
        check_diff_against_allowlist(
            current, baseline, allowlist_globs=["moon.*"], known_bodies=list(baseline.keys())
        )
    assert "numeric" in str(exc.value).lower() or "number" in str(exc.value).lower()
