"""Deterministic stratified subset selection for research jobs."""
import random

from server.db import get_db


def select_subset(catalog: list[dict], n: int, seed: int) -> list[dict]:
    """Pick `n` eclipses from `catalog` using deterministic stratified sampling.

    Strategy:
      1. If catalog has <= n entries, return all of them sorted by JD.
      2. Sort catalog by julian_day_tt.
      3. Divide the JD range into `n` equal-width buckets.
      4. Within each bucket, prefer type-diversity by round-robin: pick the
         entry whose type has been picked least so far; tie-break with the
         seeded RNG.
      5. If a bucket is empty, fall back to picking the nearest unpicked
         entry from an adjacent bucket.
      6. Return the picked entries sorted by JD.

    Always deterministic for a given (catalog contents, n, seed).
    """
    if not catalog:
        return []
    cat = sorted(catalog, key=lambda r: r["julian_day_tt"])
    if len(cat) <= n:
        return cat

    rng = random.Random(seed)

    jd_min = cat[0]["julian_day_tt"]
    jd_max = cat[-1]["julian_day_tt"]
    span = jd_max - jd_min
    if span == 0:
        return sorted(rng.sample(cat, n), key=lambda r: r["julian_day_tt"])

    buckets: list[list[dict]] = [[] for _ in range(n)]
    for r in cat:
        idx = int((r["julian_day_tt"] - jd_min) / span * n)
        if idx >= n:
            idx = n - 1
        buckets[idx].append(r)

    type_counts: dict[str, int] = {}
    picked: list[dict] = []

    def _pick_from(candidates: list[dict]) -> dict:
        if not candidates:
            raise RuntimeError("internal: _pick_from called with empty list")
        min_count = min(type_counts.get(c["type"], 0) for c in candidates)
        best = [c for c in candidates if type_counts.get(c["type"], 0) == min_count]
        return rng.choice(best)

    for i in range(n):
        if buckets[i]:
            chosen = _pick_from(buckets[i])
            buckets[i].remove(chosen)
        else:
            chosen = None
            for offset in range(1, n):
                left = i - offset
                right = i + offset
                if left >= 0 and buckets[left]:
                    chosen = _pick_from(buckets[left])
                    buckets[left].remove(chosen)
                    break
                if right < n and buckets[right]:
                    chosen = _pick_from(buckets[right])
                    buckets[right].remove(chosen)
                    break
            if chosen is None:
                break
        picked.append(chosen)
        type_counts[chosen["type"]] = type_counts.get(chosen["type"], 0) + 1

    return sorted(picked, key=lambda r: r["julian_day_tt"])


def load_eclipses_for_dataset(dataset_slug: str) -> list[dict]:
    """Load all eclipse_catalog rows for a dataset slug from the live DB.

    `dataset_slug` is 'solar_eclipse' or 'lunar_eclipse'. Returns rows in
    the same shape scanner.load_eclipse_catalog uses.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM datasets WHERE slug = ?", (dataset_slug,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown dataset slug: {dataset_slug}")
        dataset_id = row["id"]
        rows = conn.execute(
            "SELECT julian_day_tt, date, type, magnitude "
            "FROM eclipse_catalog WHERE dataset_id = ? ORDER BY julian_day_tt",
            (dataset_id,),
        ).fetchall()
    return [dict(r) for r in rows]
