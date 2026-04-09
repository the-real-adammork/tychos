---
job: lunar-sim-01
dataset: solar_eclipse
base_param_version: v1-original/v1
allowlist:
  - moon.*
  - moon_def_a.*
  - moon_def_b.*
---

# Research job: lunar-sim-01

## Goal
Lower `mean(sqrt(moon_dRA² + moon_dDec²))` — the mean angular distance between
Tychos Moon and JPL Moon at JPL's moment of minimum separation — across the
full solar eclipse catalog (452 events, 1900–2100). Lower is better.

**Objective mode: `lunar_position`** — only the Moon's positional accuracy
matters; Sun deltas are ignored.

## The loop
1. Form a hypothesis about which allowlisted parameter(s) to change and why.
2. Edit `current.json` (only keys in the allowlist).
3. Run `./research.sh iterate lunar-sim-01` and read `objective: <n>`.
   The output includes per-eclipse signed ΔRA and ΔDec vs JPL sorted worst-first.
   Use the sign pattern to guide your hypothesis:
   - Positive moon_dRA = Tychos Moon is **east** of JPL Moon
   - Positive moon_dDec = Tychos Moon is **north** of JPL Moon
   - If most eclipses have the same sign in ΔRA → systematic RA bias → adjust `moon.start_pos` or `moon.speed`
   - If ΔRA changes sign over time → drift → adjust `moon.speed`
   - If ΔDec is consistently off → adjust `moon.orbit_tilt_*` or `moon_def_b.orbit_tilt_*`
4. If lower than current best: keep. If worse, revert and try a different change.
5. Repeat until the wall-clock budget is exhausted.

## Joint search (use this for coupled parameters)

Single-parameter grinding gets stuck at coordinate-wise minima. When you
identify **2–6 coupled parameters**, hand them to Nelder-Mead:

```
./research.sh search lunar-sim-01 \
    --params moon.start_pos,moon.speed,moon_def_a.speed \
    --budget 60
```

Guidelines: 2–6 params at a time; budget ≈ 10× the number of params;
run `iterate` first to know the starting objective.

## Constraints
- Only edit `current.json`. Never touch `baseline.json`, `subset.json`, or
  any other file.
- Only edit allowlisted keys (`moon.*`, `moon_def_a.*`, `moon_def_b.*`). The CLI
  hard-fails otherwise.
- For joint moves, prefer `search` over hand-editing several fields at once.

---

## Background: the Tychos model

### A. Geometry
Tychos is **geo-heliocentric**: Earth sits near the barycenter, the Sun
orbits Earth once per year. Each body has 8 fields: `orbit_radius`,
`orbit_center_a/b/c` (Cartesian offsets encoding eccentricity-like
displacements), `orbit_tilt_a/b` (two-axis inclination), `start_pos`
(initial phase in **degrees**), `speed` (angular rate).

### B. Moon-specific parameters
- **`moon.start_pos`** — initial ecliptic longitude (degrees).
- **`moon.speed`** — orbital angular rate. ~83.29 rad/yr ≈ 13.37 orbits/yr.
  Controls secular drift over the catalog's 200-yr span.
- **`moon.orbit_center_*`** — offsets the Moon's orbit center from Earth,
  encoding the lunar equation of center (~±6° longitude variation).
- **`moon.orbit_tilt_*`** — inclination of the Moon's orbital plane.
  Affects declination. The Moon's orbital plane is tilted ~5.15° to the ecliptic.
- **`moon_def_a.*`** — a deferent circle layered on the Moon's primary orbit.
  Adjusts position sub-monthly (evection, variation corrections).
- **`moon_def_b.*`** — a second deferent for additional lunar perturbations.
  The orbit_tilt fields on this deferent can encode nodal regression effects.

### C. Reading the per-eclipse output
Each `iterate` prints every eclipse sorted worst-first:
```
                  date     error   moon_dRA  moon_dDec
   1903-09-21T04:39:52     27.25     +23.32     -14.09
```
- `error` = sqrt(dRA² + dDec²) in arcmin
- `moon_dRA` / `moon_dDec` = signed delta in arcmin (Tychos − JPL)
- Look for **systematic patterns**: all positive dRA → Moon is ahead in RA;
  sign flip around a date → speed is off; dDec consistently negative → tilt
