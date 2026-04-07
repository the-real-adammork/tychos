from server.research.subset import select_subset


def _eclipse(jd, type_, mag=1.0):
    return {"julian_day_tt": jd, "date": f"jd-{jd}", "type": type_, "magnitude": mag}


def _spread_catalog(n=200):
    """Build a synthetic catalog spanning JDs 2000000..2200000 with mixed types."""
    types = ["total", "partial", "annular"]
    return [
        _eclipse(2000000 + i * 1000, types[i % 3])
        for i in range(n)
    ]


def test_subset_size_matches_request():
    cat = _spread_catalog()
    out = select_subset(cat, n=25, seed=42)
    assert len(out) == 25


def test_subset_is_deterministic():
    cat = _spread_catalog()
    a = select_subset(cat, n=25, seed=42)
    b = select_subset(cat, n=25, seed=42)
    assert [r["julian_day_tt"] for r in a] == [r["julian_day_tt"] for r in b]


def test_subset_changes_with_seed():
    cat = _spread_catalog()
    a = select_subset(cat, n=25, seed=42)
    b = select_subset(cat, n=25, seed=99)
    assert [r["julian_day_tt"] for r in a] != [r["julian_day_tt"] for r in b]


def test_subset_stratifies_by_date():
    """Each subset element should come from a distinct equal-width JD bucket."""
    cat = _spread_catalog()
    out = select_subset(cat, n=10, seed=42)
    jd_min = min(r["julian_day_tt"] for r in cat)
    jd_max = max(r["julian_day_tt"] for r in cat)
    bucket_width = (jd_max - jd_min) / 10
    bucket_indices = {
        min(int((r["julian_day_tt"] - jd_min) / bucket_width), 9)
        for r in out
    }
    assert len(bucket_indices) == 10  # one per bucket


def test_subset_smaller_than_n_returns_all():
    cat = _spread_catalog(n=5)
    out = select_subset(cat, n=25, seed=42)
    assert len(out) == 5


def test_subset_sorted_by_jd():
    cat = _spread_catalog()
    out = select_subset(cat, n=25, seed=42)
    jds = [r["julian_day_tt"] for r in out]
    assert jds == sorted(jds)
