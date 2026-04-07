# Tychos Eclipse Prediction Test Suite

![Eclipse geometry detail page showing predicted, Tychos, and JPL diagrams side by side](docs/images/eclipse-geometry-detail.png)

![Results detail table showing eclipse error metrics](docs/images/results-detail.png)

This project tests the [Tychos model](https://www.tychos.space/)'s ability to predict historical solar and lunar eclipses. For each eclipse in NASA's authoritative catalogs, it computes Sun and Moon positions in both the Tychos geometric model and the standard JPL ephemeris, derives a **predicted reference geometry** directly from the catalog's published gamma and magnitude, and reports each model's angular error against that reference.

## How It Works

1. **Get the eclipse catalogs.** Parse [NASA's Five Millennium Canon](docs/datasets.md#nasa-five-millennium-canon-of-eclipse-catalogs) of solar and lunar eclipses (1901–2100) into JSON, giving us ~900 eclipses with exact times in Julian Day (TT), plus per-eclipse `gamma`, magnitude, and Saros series number.

2. **Derive a predicted reference geometry.** For each catalog eclipse, [`server/services/predicted_geometry.py`](docs/methodology.md#predicted-reference-geometry) converts the published gamma and magnitude into the expected Sun-Moon (or Moon-to-shadow) angular separation and disk/shadow radii — pure geometry, no Skyfield, no Tychos. This becomes the per-eclipse ground-truth reference stored in the `predicted_reference` table.

3. **Set up two models via Skyfield.** Initialize the [Tychos geometric model](docs/architecture.md#tychos_skyfield-submodule) (`tychos_skyfield`) and the standard [heliocentric model](docs/datasets.md#jpl-de440s-planetary-ephemeris) (JPL DE440s ephemeris via Skyfield). Both produce Sun and Moon RA/Dec positions in the ICRF/J2000 frame.

4. **Scan each model for closest approach.** For each catalog eclipse, [scan for minimum Sun-Moon separation](docs/methodology.md#how-eclipse-detection-works) in the Tychos model around the catalog time, and record the corresponding JPL geometry at the same instant.

5. **Score against the predicted reference.** Compute `tychos_error_arcmin` and `jpl_error_arcmin` as the angular distance between each model's predicted Sun-Moon separation and the catalog-derived reference separation. There is no pass/fail — the metric is continuous.

6. **Store and visualize.** Results go into a SQLite database. The [admin dashboard](docs/visualizations.md#admin-dashboard) provides per-eclipse [geometry diagrams](docs/visualizations.md) (predicted / tychos / jpl side-by-side), error-based filtering, [Saros-series grouping](docs/visualizations.md#saros-analysis), and dataset browsing.

## Documentation

| Doc | Topic |
|---|---|
| [Methodology](docs/methodology.md) | Predicted reference geometry, eclipse detection scan, error metrics |
| [Datasets](docs/datasets.md) | NASA Five Millennium Canon catalogs and JPL DE440s ephemeris |
| [Architecture & Dependencies](docs/architecture.md) | tychos_skyfield, Skyfield, NumPy, SciPy, FastAPI |
| [Visualizations & Dashboard](docs/visualizations.md) | Eclipse diagrams, Saros analysis, admin UI walkthrough |
| [Roadmap](docs/roadmap.md) | Open questions and future goals |

## Quick Start

Local development (FastAPI server + worker + admin SPA dev server):

```bash
git clone --recurse-submodules https://github.com/the-real-adammork/tychos.git
cd tychos
python3 -m venv tychos_skyfield/.venv
source tychos_skyfield/.venv/bin/activate
pip install -r server/requirements.txt -r tychos_skyfield/requirements.txt -r requirements.txt
(cd admin && npm install)

# First boot only — required to seed the initial admin user
export TYCHOS_ADMIN_USER=you@example.com
export TYCHOS_ADMIN_PASSWORD='something-strong'

./dev.sh
```

This starts the API at <http://localhost:8000>, the admin UI at <http://localhost:5173>, and the background worker. Hit `/login` with the credentials you exported above. The first boot runs migrations, downloads `de440s.bsp`, parses the NASA catalogs, derives the predicted reference geometry, and queues the seeded parameter sets for runs — give it a minute.

For deploying as a long-lived service behind Cloudflare Tunnel + Access, see [`local_deploy/README.md`](local_deploy/README.md).

> ⚠️ **The bare API server has open registration and no built-in access control.** It's only safe to expose publicly behind an external auth gate. The local deploy uses Cloudflare Access with an email allowlist.

## Project Layout

| Path | What it is |
|---|---|
| [`server/`](server/README.md) | FastAPI backend, SQLite migrations, the background worker, and the eclipse scanner |
| [`admin/`](admin/README.md) | React + Vite single-page admin UI |
| [`tests/`](tests/README.md) | Pytest suite for the scanner, predicted geometry, and helper math |
| [`tychos_skyfield/`](https://github.com/mindaugl/tychos_skyfield) | Submodule — the Python implementation of the Tychos model |
| [`scripts/`](scripts/) | One-off scripts (currently just the NASA catalog parser) |
| [`local_deploy/`](local_deploy/README.md) | Cloudflare Tunnel + Access deploy scripts and launchd plists |
| [`params/`](params/README.md) | On-disk parameter sets that get seeded into the database on first boot |
| [`docs/`](docs/) | Methodology, architecture, datasets, visualizations, and roadmap |

## License

GPL v2. See [`LICENSE`](LICENSE). The `tychos_skyfield` submodule is also GPL v2.
