---
job: solar-sim-03
dataset: solar_eclipse
base_param_version: v1-original/v1
allowlist:
  - moon.*
  - moon_def_a.*
  - moon_def_b.*
  - sun.*
  - sun_def.*
  - earth.*
---

# Research job: solar-sim-03

## Goal
Lower `mean(|timing_offset_min|)` on the solar_eclipse subset by editing
`params/research/solar-sim-03/current.json`. Lower is better.

## The loop
1. Form a hypothesis about which allowlisted parameter(s) to change and why.
2. Edit `current.json` (only keys in the allowlist).
3. Run `python -m server.research iterate solar-sim-03` and read `objective: <n>`.
4. If lower than current best: run `python -m server.research validate solar-sim-03`
   and keep only if the `validation_objective` is also lower than the previous
   best validation (otherwise revert — subset overfit).
5. If worse, revert and try a different change.
6. Repeat until the wall-clock budget is exhausted.

## Joint search (use this for coupled parameters)

Single-parameter grinding gets stuck at coordinate-wise minima. When you
identify **2–6 coupled parameters**, hand them to Nelder-Mead instead:

```
python -m server.research search solar-sim-03 \
    --params moon.start_pos,moon_def_a.speed,moon_def_a.start_pos \
    --budget 60
```

It only overwrites `current.json` if it finds a strictly better joint
assignment. Guidelines: 2–6 params at a time; budget ≈ 10× the number of
params; don't mix highly- and barely-sensitive params in one call; run
`iterate` first to know the starting objective; `validate` after a win.

## Constraints
- Only edit `current.json`. Never touch `baseline.json`, `subset.json`, or
  any other file.
- Only edit allowlisted keys. The CLI hard-fails otherwise.
- For joint moves, prefer `search` over hand-editing several fields at once.

---

## Background: the Tychos model

> Parts A & B are **objective-agnostic** geometry. Part C and below are
> **specific to the current objective `mean(|timing_offset_min|)`** — if
> you change the objective, re-derive C from the physics.

### A. Geometry (objective-agnostic)
Tychos is **geo-heliocentric**: Earth sits near the barycenter, the Sun
orbits Earth once per year (carrying Mercury and Venus), and the outer
planets orbit the Sun. Earth itself is not static — it crawls along a
large circular **PVP (Polaris–Vega–Polaris) orbit**, radius ~56.6 Mkm,
period **25,344 years** (the "Tychos Great Year"), opposite in sense to
the Sun. Earth's rotation + PVP translation traces a **prolate trochoid**
on the celestial sphere. The Moon orbits Earth on a ~381,547 km-radius
circle (sidereal 27.322 d, synodic ~29.22 d). Eclipses happen when the
Moon's orbit crosses the Earth–Sun line; the book does not give an
explicit eclipse-mechanics derivation, so the mechanism is inferred from
pure moon+sun geometry around Earth.

### B. Parameters & deferents (objective-agnostic)
Each body has 8 fields: `orbit_radius`, `orbit_center_a/b/c` (Cartesian
offsets that encode eccentricity-like displacements), `orbit_tilt_a/b`
(two-axis inclination), `start_pos` (initial phase; **degrees** in JSON,
radians internally), `speed` (angular rate per Tychos time unit — since
`sun.speed = 2π`, the base unit is one year).

Tychosium layers **deferent** carrier-circles on the primary orbit to
reproduce lunar/solar corrections without Keplerian ellipses:
- **`moon_def_a`** encodes the **8.85-year apsidal precession of the
  Moon's perigee** (the book cites 0.1114°/day, stated as a 3:1 ratio
  against Earth's PVP motion). Its `speed` ≈ 2π/8.85 rad/yr.
- **`moon_def_b`** — a smaller deferent most plausibly encoding the
  **evection** (~31.8-day, ±1.274°, ~14,070 km lateral displacement,
  attributed in the book to PVP geometry). Mapping inferred — the book
  doesn't name this parameter.
- **`sun_def`** — the solar equation-of-center analogue; shifts the
  Sun's apparent longitude by up to ±2° over the year.

---

### C. Leverage analysis — **objective: `mean(|timing_offset_min|)`**

> ⚠️ This entire section is specific to the timing objective. If you are
> optimizing a different metric (separation, detection rate, directional
> error), **re-derive from Parts A–B** — the rankings below don't apply.

**Sign convention (timing only):** catalog times are **Julian Date in TT**;
`timing_offset_min = (best_jd − catalog_jd) × 1440`. Positive = tychos
predicts alignment **later** than catalog → moon needs to be further
along in its orbit at t=0 → **decrease** `moon.start_pos` (in degrees).

**High leverage:**
- **`moon.start_pos`** — direct linear: 1° ≈ 109 min of timing shift on
  every eclipse. Highest per-degree leverage. Start here.
- **`moon.speed`** — secular drift proportional to elapsed time; small
  error becomes large over 100-yr baselines. *(Empirically at a local
  minimum in v1-original/v1.)*
- **`moon_def_a.{speed,start_pos}`** — modulates timing by a few minutes
  on the 8.85-yr perigee cycle. Essential for multi-decade fits.
- **`moon_def_b`** — evection-scale modulation (~±1 min, 31.8-day period).

**Medium leverage:**
- **`sun.start_pos` / `sun.speed` / `sun_def.*`** — 1° in sun longitude ≈
  2 hr of timing shift (via ~12°/day synodic rate). Smaller per-degree
  than `moon.start_pos` but still non-trivial.
- **`sun.orbit_center_*`** — solar equation of center; biases timing
  seasonally.

**Low / no leverage on timing:**
- **`earth.speed` (PVP rate)** — 25,344-yr period; over 100–200 yr Earth
  moves only a few thousand km along PVP. **Empirically: a 40% change
  produced zero detectable objective change on a 20-event 1909–2100
  subset. Do not waste iterations probing it.**
- **`moon.orbit_tilt_*`, `moon.orbit_radius`** — mostly affect separation
  and whether a syzygy lands on the ecliptic, not *when* closest approach
  happens. Expect movement in `mean_separation_arcmin`, not `objective`.

### D. Prior findings — base: **v1-original/v1**, window 6h
Hand-probing results from an earlier session. Re-verify if your base
differs. **Timing-objective-specific — see Part C warning.**
- `moon.start_pos` optimum near **260.95** (−0.25° from 261.2).
- `moon_def_a.speed` responds to ~**+1e-5** positive adjustments; +1e-4
  overshoots.
- After phase tuning, residuals show a **concave-down hump centered near
  1950** (+150 to +190 min in 1944/53/63; −105 to −109 in 1912/2044).
  No single parameter reshapes it. **Try `search` with joint
  `{moon.start_pos, moon_def_a.speed, moon_def_a.start_pos}`** before
  reporting a structural limit.
