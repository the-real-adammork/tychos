---
job: solar-sim-03
dataset: solar_eclipse
base_param_version: v1-original/v1
allowlist:
  - sun.*
  - sun_def.*
  - earth.*
---

# Research job: solar-sim-03

## Goal
Lower `mean(sqrt(sun_dRA² + sun_dDec²))` — the mean angular distance between
Tychos Sun and JPL Sun at JPL's moment of minimum separation — across the
full solar eclipse catalog (452 events, 1900–2100). Lower is better.

**Objective mode: `solar_position`** — only the Sun's positional accuracy
matters; Moon deltas are ignored.

## The loop
1. Form a hypothesis about which allowlisted parameter(s) to change and why.
2. Edit `current.json` (only keys in the allowlist).
3. Run `./research.sh iterate solar-sim-03` and read `objective: <n>`.
   The output includes per-eclipse signed ΔRA and ΔDec vs JPL sorted worst-first.
   Use the sign pattern to guide your hypothesis:
   - Positive sun_dRA = Tychos Sun is **east** of JPL Sun
   - Positive sun_dDec = Tychos Sun is **north** of JPL Sun
   - If most eclipses have the same sign in ΔRA → systematic RA bias → adjust `sun.start_pos` or `sun.speed`
   - If ΔRA changes sign over time → drift → adjust `sun.speed`
   - If ΔDec is consistently off → adjust `sun_def.orbit_tilt_*`
4. If lower than current best: keep. If worse, revert and try a different change.
5. Repeat until the wall-clock budget is exhausted.

## Joint search (use this for coupled parameters)

Single-parameter grinding gets stuck at coordinate-wise minima. When you
identify **2–6 coupled parameters**, hand them to Nelder-Mead:

```
./research.sh search solar-sim-03 \
    --params sun.start_pos,sun.speed,sun_def.start_pos \
    --budget 60
```

Guidelines: 2–6 params at a time; budget ≈ 10× the number of params;
run `iterate` first to know the starting objective.

## Constraints
- Only edit `current.json`. Never touch `baseline.json`, `subset.json`, or
  any other file.
- Only edit allowlisted keys (`sun.*`, `sun_def.*`, `earth.*`). The CLI
  hard-fails otherwise.
- For joint moves, prefer `search` over hand-editing several fields at once.

---

## Background: the Tychos model

### A. Geometry
Tychos is **geo-heliocentric**: Earth sits near the barycenter, the Sun
orbits Earth once per year. Each body has 8 fields: `orbit_radius`,
`orbit_center_a/b/c` (Cartesian offsets encoding eccentricity-like
displacements), `orbit_tilt_a/b` (two-axis inclination), `start_pos`
(initial phase in **degrees**), `speed` (angular rate — `sun.speed = 2π`
means one orbit per year).

### B. Sun-specific parameters
- **`sun.start_pos`** — initial ecliptic longitude. 1° ≈ 4 min of RA shift.
- **`sun.speed`** — orbital angular rate. Controls secular drift over
  the catalog's 200-yr span.
- **`sun.orbit_center_*`** — offsets the Sun's orbit center from Earth,
  encoding the solar equation of center (±2° longitude variation over
  the year).
- **`sun.orbit_tilt_*`** — inclination of the Sun's orbital plane.
  Affects declination.
- **`sun_def.*`** — a deferent circle layered on the Sun's primary orbit.
  Adjusts longitude sub-annually.
- **`earth.speed`** — PVP orbit rate (25,344-yr period). Negligible over
  200 yr — **do not waste iterations on it**.

### C. Reading the per-eclipse output
Each `iterate` prints every eclipse sorted worst-first:
```
                  date     error    sun_dRA   sun_dDec
   1903-09-21T04:39:52     27.25     +23.32     -14.09
```
- `error` = sqrt(dRA² + dDec²) in arcmin
- `sun_dRA` / `sun_dDec` = signed delta in arcmin (Tychos − JPL)
- Look for **systematic patterns**: all positive dRA → Sun is ahead in RA;
  sign flip around a date → speed is off; dDec consistently negative → tilt
