# Architecture & Dependencies

[← Back to README](../README.md)

## tychos_skyfield (Submodule)

The core Tychos model implementation in Python. Included as a git submodule at `tychos_skyfield/`.

- **`baselib.py`** — The complete Tychos solar system model. Implements `TychosSystem`, which positions all planets (Sun, Moon, Mercury through Neptune, and several minor bodies) using the Tychos geometric model with deferent/epicycle-style orbital mechanics. Computes RA/Dec in the ICRF/J2000 frame. Orbital parameters are loaded from `orbital_params.json`, which was originally derived from the [Tychosium](https://www.tychos.space/tychosium/) JavaScript 3D simulator's `celestial-settings.json`.

- **`skyfieldlib.py`** — An adapter that wraps Tychos objects as [Skyfield](https://rhodesmill.org/skyfield/) `VectorFunction` objects, allowing Tychos-computed positions to be used interchangeably with JPL ephemeris data within the Skyfield API. This enables direct RA/Dec comparisons between Tychos and the standard (heliocentric) model.

**Source:** Private submodule (contact the Tychos project for access)

## Skyfield

[Skyfield](https://rhodesmill.org/skyfield/) is a Python library for positional astronomy by Brandon Rhodes. It computes positions of stars, planets, and satellites using high-accuracy numerical data from NASA's Jet Propulsion Laboratory (JPL).

- **Used for:** Computing JPL reference positions of the Sun and Moon at each catalog eclipse time, serving as the "standard model" baseline for comparison.
- **Ephemeris file:** [`de440s.bsp`](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/) — The compact version of JPL's DE440 planetary ephemeris, covering 1849–2150 CE.
- **Reference:** [rhodesmill.org/skyfield](https://rhodesmill.org/skyfield/)
- **PyPI:** [skyfield](https://pypi.org/project/skyfield/)

## NumPy

Used throughout for trigonometric calculations (angular separation, coordinate transforms) and array operations.

- **Reference:** [numpy.org](https://numpy.org/)

## SciPy

Used in `baselib.py` for `scipy.spatial.transform.Rotation` — 3D rotation algebra for orbit tilts, coordinate frame transformations, and RA/Dec computation from Cartesian positions.

- **Reference:** [scipy.org](https://www.scipy.org/)

## FastAPI + aiosqlite

The admin server uses [FastAPI](https://fastapi.tiangolo.com/) for the API layer and [aiosqlite](https://pypi.org/project/aiosqlite/) for async SQLite access. Results are stored in `results/tychos_results.db`.
