---
job: solar-sim-02
dataset: solar_eclipse
base_param_version: solar-sim-01/v1
allowlist:
  - moon.*
  - moon_def_a.*
  - moon_def_b.*
  - sun.*
  - sun_def.*
  - earth.*
---

# Research job: solar-sim-02

Successor to `solar-sim-01`. Starts from `solar-sim-01/v1` (the snapshot
of sim-01's `current.json` after 33 iterations — objective 12.948 on the
seed-42 random subset, validation 16.079 on the full catalog).

## What's new in sim-02

sim-01 used a single static random subset of 25 events. sim-02 adds
**experimental design** to the loop: the training data is structured
around Saros cycles so that parameters can be disentangled by
construction, not by hoping the optimizer sorts it out.

Three training subsets, each probing a different class of parameter,
plus a locked test set and a lunar-eclipse generalization check.

## Goal
Lower `mean(|timing_offset_min|)` by editing
`params/research/solar-sim-02/current.json`. Lower is better.

## The loop
1. Decide which parameter class you're probing (see "Subset selection" below).
2. Swap `subset.json` to the matching training cohort (or leave it as-is
   if you're sticking with the current cohort).
3. Form a hypothesis, edit `current.json` (allowlisted keys only).
4. `./research iterate solar-sim-02` → read `objective: <n>`.
5. If lower than current best on that cohort: `./research validate solar-sim-02`
   (solar full-catalog). Keep only if `validation_objective` also improved
   over the previous best validation.
6. Every ~5 wins, run the lunar generalization check (see below). If
   lunar objective worsened while solar improved, you overfit one node —
   revert the last change and try a less moon-geometry-intensive move.
7. Only touch `test.json` at session end. It does not inform iteration.

## Subset selection

There are three training cohorts. `subset.json` is whichever one is
currently active — switch by overwriting it from one of the
`subset_*.json` siblings (e.g. `cp subset_phase.json subset.json`).

Always record which cohort you were on in your hypothesis notes, because
`log.jsonl` does not yet carry a `subset` field.

### `subset_saros.json` — Saros 136, 12 events, 1901–2099  (default)
A single Saros series. Successive events are separated by 18 yr 11 d
with Sun–Moon–node geometry held nearly constant. Residual *differences*
across the series are almost pure secular-rate error.

**Use this to tune:** `moon.speed`, `moon_def_a.speed`, `earth.speed`
(the PVP rate — sim-01 found it flat on random data, but a Saros series
is the setup where it *could* show up if it matters). Also exposes any
linear-in-time drift from `moon_def_a.start_pos` misalignment.

**Do not use this to tune phase parameters** (`moon.start_pos`,
`sun.start_pos`) — they shift every event by the same amount here, so
the cohort can't distinguish a phase error from a constant offset that
validation will punish.

### `subset_phase.json` — 12 events, 1990–2005, one per distinct Saros
Every event is within a ~15 yr window, so secular drift contributes
almost nothing to the spread. What varies is the Saros (i.e. the
geometry at the moment of alignment). Residual differences across events
probe *phase and geometry*, not rates.

**Use this to tune:** `moon.start_pos`, `moon_def_a.start_pos`,
`moon_def_b.*` (evection phase), `sun.start_pos`, `sun_def.*`,
`sun.orbit_center_*`, and `moon.orbit_center_*` / `moon.orbit_radius`
(see Part C finding below).

### `subset_regression.json` — sim-01 seed-42 random 25, verbatim
Kept as a frozen regression cohort so sim-01 and sim-02 results stay
directly comparable. Do not tune against it — if sim-02's regression
objective ever beats sim-01's 12.948 while *also* beating sim-01's
validation 16.079, sim-02 has dominated sim-01 on the old regime.

## Joint search (use this for coupled parameters)

```
./research search solar-sim-02 \
    --params moon.start_pos,moon_def_a.speed,moon_def_a.start_pos \
    --budget 60 --scale 0.01
```

Same rules as sim-01: 2–6 params at a time, budget ≈ 10× n_params, don't
mix high- and low-sensitivity params in one call. **New guidance on
`--scale`:** sim-01 hardcoded 0.01 everywhere. Vary it — when a search
stalls at "converged: true" but you suspect a larger basin, restart with
`--scale 0.05`. When you're polishing a near-optimum, drop to
`--scale 0.005`. Coarse-then-fine restarts often escape local minima
that 0.01 can't cross.

## Lunar generalization check  (orthogonal validation)

Solar eclipses happen at one lunar node; lunar eclipses happen at the
other. A moon-geometry tune that's overfit to the solar subset will
typically degrade the lunar residual. So the lunar full catalog is the
most honest generalization signal available without spending fresh
solar events.

Because the current CLI only knows about `subset.json`, run the check
manually by swapping subsets:

```bash
cp subset.json /tmp/sim02_solar_subset.json      # stash active cohort
cp subset_lunar_val.json subset.json
./research iterate solar-sim-02                  # this is the lunar check
cp /tmp/sim02_solar_subset.json subset.json      # restore
```

**Interpretation:**
- Solar val ↓ and lunar val ↓ → genuine geometry improvement.
- Solar val ↓ and lunar val ↑ → single-node overfit. Revert.
- Solar val ↓ and lunar val ≈ flat → secular-rate improvement
  (rates affect both nodes similarly). Safe.

Record the lunar number manually in your session notes — log.jsonl will
just show it as another `iterate` entry.

## Locked test set  (`test.json`, 50 events)

Sampled with `seed=2002`, disjoint from every training cohort. **Do not
look at this during iteration.** At session end, stash `subset.json`,
copy `test.json` in, run one `iterate`, record the number, restore.
That is the only honest "how good is this really" signal — `validate`
will drift toward being a second training set as you use it to gate
moves.

## Constraints
- Only edit `current.json`. Never touch `baseline.json`, `subset_*.json`,
  `test.json`, or any sibling file.
- Only edit allowlisted keys. The CLI hard-fails otherwise.
- For joint moves, prefer `search` over hand-editing several fields at once.
- When you swap `subset.json`, your next `iterate` will produce a number
  that is *not* comparable to the previous iterate — note the swap
  explicitly so you don't later think a single change caused a 4-min
  jump.

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

**High leverage (phase cohort is the right setup):**
- **`moon.start_pos`** — direct linear: 1° ≈ 109 min of timing shift on
  every eclipse. Highest per-degree leverage. Best tuned on `phase`.
- **`moon_def_a.{speed,start_pos}`** — modulates timing by a few minutes
  on the 8.85-yr perigee cycle. `.speed` belongs on `saros`, `.start_pos`
  on `phase`.
- **`moon_def_b`** — evection-scale modulation (~±1 min, 31.8-day period).
  Phase cohort.
- **`moon.orbit_center_*` / `moon.orbit_radius`** — sim-01 iter 32 found
  a joint search on these four keys reduced objective by 0.16 on the
  random cohort, which contradicts the "only affects separation"
  assumption that sim-01 started with. The mechanism is likely that
  these offsets shift the apparent moon longitude at alignment (a
  small eccentricity-like bias). Treat as **medium-leverage phase
  parameters** and tune on `phase`.

**High leverage (saros cohort is the right setup):**
- **`moon.speed`** — secular drift proportional to elapsed time; small
  error becomes large over 100-yr baselines. sim-01 reported a local
  minimum at baseline on random data, but the saros cohort is the first
  time its effect shows up cleanly — re-probe it here.
- **`moon_def_a.speed`** — same story; the 8.85-yr perigee rate
  accumulates across a Saros series.

**Medium leverage:**
- **`sun.start_pos` / `sun.speed` / `sun_def.*`** — 1° in sun longitude ≈
  2 hr of timing shift (via ~12°/day synodic rate). Smaller per-degree
  than `moon.start_pos` but still non-trivial. Phase cohort.
- **`sun.orbit_center_*`** — solar equation of center; biases timing
  seasonally. Phase cohort.

**Low / no leverage on timing (sim-01 empirical):**
- **`earth.speed` (PVP rate)** — 25,344-yr period; over 100–200 yr Earth
  moves only a few thousand km along PVP. sim-01 found a 40% change
  produced zero detectable objective change on a 20-event 1909–2100
  random subset. **Re-probe on `saros` before declaring dead** — a
  single-Saros cohort is the cleanest place for any secular effect to
  emerge, if it exists at all.
- **`moon.orbit_tilt_*`** — mostly affect separation and whether a syzygy
  lands on the ecliptic, not *when* closest approach happens. Expect
  movement in `mean_separation_arcmin`, not `objective`.

### D. Prior findings carried over from solar-sim-01
Hand-probing results from sim-01 on `v1-original/v1` base, random
seed-42 subset, 6h window. Your base is sim-01's end state
(`solar-sim-01/v1`), so these are *starting points* for sim-02, not
endpoints — re-verify each before building on it.

- `moon.start_pos` optimum near **260.95** on the random cohort
  (−0.25° from v1-original/v1's 261.2). Probably drifted further in
  sim-02's base.
- `moon_def_a.speed` responds to ~**+1e-5** positive adjustments; +1e-4
  overshoots.
- Residual hump centered near 1950 (+150 to +190 min in 1944/53/63;
  −105 to −109 in 1912/2044) observed on the random cohort. **Open
  question:** does this hump persist on the Saros cohort? If it's
  primarily a secular-rate artifact, Saros should expose it directly.
  If it's primarily a phase artifact, Saros won't see it and `phase`
  will.
- sim-01 iter 32 joint-search on `moon.orbit_center_{a,b,c}` +
  `moon.orbit_radius` improved random-cohort objective by 0.16. See
  Part C above.
