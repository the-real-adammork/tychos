# Visualizations & Admin Dashboard

[← Back to README](../README.md)

The admin dashboard renders eclipse geometry as inline SVGs and provides a UI for browsing parameter sets, runs, results, and Saros-grouped analysis.

## Eclipse Geometry Diagram (per-result detail page)

Each eclipse result page shows three side-by-side diagrams: **Predicted** (catalog-derived) on the left, **Tychos** in the middle, and **JPL** on the right. The same predicted diagram is also shown on each catalog detail page (under the dataset browser), so you can inspect the expected geometry of any eclipse without running a model.

**Solar eclipses** are centered on the Sun:

![Solar eclipse geometry diagram](images/solar-diagram.png)

- A yellow circle represents the Sun's disk (radius from catalog magnitude when available, otherwise the mean ~16 arcminute solar radius)
- A gray circle represents the Moon's disk
- A dashed red line connects Sun center to Moon center with the separation labeled
- An arrow on the Moon shows its velocity direction (RA/Dec velocity extrapolated over 3 hours)
- Grid lines at 10-arcminute intervals provide scale

**Lunar eclipses** are centered on the anti-solar point (Earth's shadow):

![Lunar eclipse geometry diagram](images/lunar-diagram.png)

- A dark gray filled circle represents the umbral shadow (radius derived from the catalog's umbral magnitude and gamma)
- A lighter gray circle represents the penumbral shadow (derived from the penumbral magnitude)
- The Moon disk, separation line, and velocity arrow are drawn identically

The predicted diagram is rendered from the [predicted reference geometry](methodology.md#predicted-reference-geometry) alone. The Tychos and JPL diagrams use positions computed from `tychos_skyfield` and `de440s.bsp` respectively at the catalog moment, so all three can be visually compared against the same geometry.

## Admin Dashboard

The web-based admin interface (`admin/` + `server/`) provides:

- **Parameter management** — Create, edit, version, and fork orbital parameter sets
- **Run management** — Queue eclipse test runs against any parameter version and dataset; a background worker executes them
- **Datasets browser** — List of every catalog (slug, name, description, source) with a per-dataset detail page that walks through every eclipse and its predicted geometry
- **Results browsing** — Paginated tables with error columns (`tychos_error_arcmin`, `jpl_error_arcmin`), filtering by catalog type, error range, and Saros series. Aggregate error stats live-update as filters change.
- **Stats bar** — Mean Tychos and JPL error across the current filter, replacing the old pass/fail breakdown
- **Comparison view** — Side-by-side diff of two parameter versions using error metrics, plus a Saros analysis card highlighting series-level differences
- **Per-result detail** — Three-diagram layout (predicted / Tychos / JPL), position readouts, error metrics, and a Saros context card showing position in series and chronological neighbors

## Saros Analysis

The [Saros cycle](https://en.wikipedia.org/wiki/Saros_(astronomy)) is the ~18-year periodicity that produces families of geometrically similar eclipses. Each NASA catalog record carries a `saros_num`, and the dashboard exposes that as a first-class lens on results:

- **Filter by series** — Any results table or dataset page can be narrowed to a single Saros series via the `saros` query param.
- **Group by Saros** — A dedicated view aggregates a run's results by `saros_num`, returning per-series counts, year span, and mean/max Tychos and JPL error, sorted worst-first so systematic series-level errors surface immediately.
- **Saros context card** — Result and catalog detail pages show the eclipse's position within its series (e.g. "12 of 71"), the series year span, and ±5 chronological neighbors for quick navigation.
- **Saros card on the compare page** — When diffing two parameter versions, a Saros card highlights which series moved most.

Series-level analysis is the cleanest way to spot systematic model errors that follow eclipse periodicity rather than per-eclipse noise.
