# Roadmap

[← Back to README](../README.md)

This document collects what we know is still uncertain about the model and the metric (Open Questions), and what we'd like to build next (Future Goals).

## Open Questions

### Accuracy and Calibration

1. **Predicted reference fidelity.** The catalog-derived predicted geometry uses mean Earth-Moon distance and clamps lunar shadow radii to reasonable minimums. Eclipses near apogee/perigee or with extreme gamma may have predicted separations that differ from the true geometry by amounts comparable to the model errors we're trying to measure. A sensitivity study against a higher-fidelity geometry (e.g. Besselian elements) would quantify this.

2. **Timing offset distribution.** The timing offsets recorded for each result (how many minutes the Tychos minimum-separation moment differs from the catalog time) have not been rigorously analyzed for systematic bias. A consistent positive or negative offset could indicate a drift in the model's time calibration.

### Dependencies and Data Integrity

3. **Vincenty formula edge cases.** The angular separation uses the Vincenty formula, which is well-behaved for small angles (unlike the cosine formula). However, the implementation has not been tested against a reference implementation for edge cases near the poles or at exactly 0°/180° separation beyond the basic smoke tests.

### Model Questions

4. **J2000 quaternion hardcoding.** The `baselib.py` RA/Dec calculation uses a hardcoded quaternion (`[-0.1420..., 0.6927..., -0.1451..., 0.6919...]`) for the J2000 epoch frame transformation. The code comments state this was "obtained by manually getting rotation quaternion of polar axis for the date 2000/01/01 12:00." The derivation of this quaternion and its sensitivity to the polar axis model parameters have not been independently verified.

5. **Parameter sensitivity.** The system supports multiple parameter sets, but the relationship between individual orbital parameters (orbit radius, tilt, speed, center offsets) and eclipse detection accuracy has not been systematically mapped. Small changes to Moon deferent parameters likely dominate eclipse detection, but this hasn't been quantified.

## Future Goals

1. **Verify Skyfield and tychos_skyfield accuracy.** Confirm that both the Skyfield/JPL pipeline and the tychos_skyfield Python model produce positions with sufficient accuracy for meaningful comparison. This means validating Skyfield output against known reference positions and ensuring tychos_skyfield faithfully reproduces the Tychosium JavaScript simulator's results.

2. **Verify eclipse catalog data.** Audit the NASA Five Millennium Canon eclipse data to confirm it is reliable and high-accuracy — that the eclipse times, types, and magnitudes we are testing against are themselves trustworthy. Cross-reference against independent sources (e.g., Meeus's tables, USNO data) where possible.

3. **Automated parameter optimization.** With a continuous, catalog-grounded error metric now in place, brute-force search for Tychos orbital parameters that minimize mean Tychos error becomes well-defined. Next step is a fast-enough evaluation loop to make large parameter sweeps practical.

4. **Test against additional celestial events.** Extend beyond eclipses to other observable phenomena that constrain the model: planetary conjunctions, oppositions, transits of Mercury and Venus, lunar occultations of bright stars, and solstice/equinox timing.

5. **Live Tychosium preview with modified parameters.** Add a way to load modified parameter sets into the Tychosium 3D simulator so that the visual effect of parameter changes can be inspected interactively, not just measured numerically.
