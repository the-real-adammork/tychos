# Tychos vs JPL Overlay Diagram

## Goal

Add a new visualization to the Result Detail page that overlays Tychos and JPL positions on a single sky chart, so the relative positions of Sun/shadow and Moon from both engines can be compared directly at the moment of minimum separation.

## Context

`admin/src/pages/ResultDetailPage.tsx` currently shows three side-by-side 400×400 diagrams: Predicted (catalog), Tychos, and JPL (DE440s). Each `EclipseDiagram` is rendered independently with its own center. Users can eyeball differences between Tychos and JPL but cannot see the offset between the two engines directly — and the offset is often sub-arcminute.

All required data is already present on the `ResultDetail` interface: `sun_ra_rad`, `sun_dec_rad`, `moon_ra_rad`, `moon_dec_rad`, `moon_ra_vel`, `moon_dec_vel`, and the matching `jpl_*` fields, plus `min_separation_arcmin`, `jpl_separation_arcmin`, `moon_apparent_radius_arcmin`, `sun_apparent_radius_arcmin`, `umbra_radius_arcmin`, `penumbra_radius_arcmin`. No backend or API changes needed.

## Design

### Placement

A new full-width `Card` titled **"Tychos vs JPL (Overlay)"**, inserted in `ResultDetailPage.tsx` immediately below the existing three-diagram `grid grid-cols-3` row and above the Measurements card. The existing row is unchanged.

### Component

Extract to a new file: `admin/src/components/eclipse/overlay-diagram.tsx`, exporting an `OverlayDiagram` component. `ResultDetailPage.tsx` is already ~440 lines; extraction keeps it from growing further and matches the pattern already used for `PredictedDiagram` and `SarosContext`.

### Props

```ts
interface OverlayDiagramProps {
  testType: string; // "solar" | "lunar"
  // Tychos
  tychosSunRa: number | null;
  tychosSunDec: number | null;
  tychosMoonRa: number | null;
  tychosMoonDec: number | null;
  tychosMoonRaVel: number | null;
  tychosMoonDecVel: number | null;
  tychosSeparationArcmin: number | null;
  // JPL
  jplSunRa: number | null;
  jplSunDec: number | null;
  jplMoonRa: number | null;
  jplMoonDec: number | null;
  jplMoonRaVel: number | null;
  jplMoonDecVel: number | null;
  jplSeparationArcmin: number | null;
  // Shared geometry
  moonRadiusArcmin: number;
  sunRadiusArcmin: number | null;
  umbraRadiusArcmin: number | null;
  penumbraRadiusArcmin: number | null;
}
```

### Canvas

- SVG 700×700, same `border rounded-lg bg-zinc-950` styling as `EclipseDiagram`.
- `viewExtent`: 100 arcmin for lunar, 60 arcmin for solar (matches existing).
- Background grid lines, 10-arcmin scale bar bottom-left, yellow dashed detection threshold reference circle centered on the chart origin — all carried over from `EclipseDiagram`.

### Centering

- **Solar:** origin = midpoint of Tychos Sun and JPL Sun (`(ra+ra)/2`, `(dec+dec)/2`).
- **Lunar:** origin = midpoint of the two anti-solar shadow points (each anti-solar point computed as `(sunRa + π) mod 2π`, `-sunDec`, same as `EclipseDiagram`).

Midpoint centering keeps both engines near the visual center without privileging either. All plotted positions are converted to (dx, dy) arcmin offsets from this origin using `dx = (ra − centerRa) * cos(avgDec) * (180/π) * 60`, `dy = (dec − centerDec) * (180/π) * 60`, with `avgDec` per-object (matching existing convention).

### Rendered Elements

For each engine, in its color:

- **Tychos:** cyan/blue — stroke `rgba(100,200,255,0.8)`, fill `rgba(100,200,255,0.18)`
- **JPL:** amber/orange — stroke `rgba(255,180,80,0.8)`, fill `rgba(255,180,80,0.18)`

Per engine, draw:
1. **Sun disk** (solar) using `sunRadiusArcmin`, OR **umbra + penumbra** pair of circles (lunar) using `umbraRadiusArcmin` / `penumbraRadiusArcmin`, centered at that engine's Sun (solar) or anti-solar point (lunar).
2. **Moon disk** at that engine's Moon position, using `moonRadiusArcmin`.
3. **Velocity arrow** from its Moon using `moonRaVel` / `moonDecVel`, same 3× scaling as `EclipseDiagram`.
4. **Dashed center→Moon separation line** in the engine's color.
5. **Separation label** (arcmin, 1 decimal) near the midpoint of the separation line.

Shared overlays:

6. **Yellow dashed threshold reference circle** at the chart origin, radius = 48' (solar) or 90' (lunar). Same as `EclipseDiagram`.
7. **Delta line** — a white dashed line connecting Tychos Moon ↔ JPL Moon, labeled with the Moon-position delta in arcmin (computed as Euclidean distance in the already-projected dx/dy plane). Labeled with 2 decimals since the offset is often sub-arcminute.
8. **Legend** in the top-right: two small swatches reading "Tychos" / "JPL".
9. **10 arcmin scale bar** bottom-left.
10. **Caption** below the SVG: `"Centered on {Sun | Earth shadow} midpoint · N↑ E←"`.

### Empty State

If any of the eight required fields (`tychosSunRa`, `tychosSunDec`, `tychosMoonRa`, `tychosMoonDec`, `jplSunRa`, `jplSunDec`, `jplMoonRa`, `jplMoonDec`) is null, render `<p className="text-sm text-muted-foreground">No overlay data available</p>` — same pattern as existing `EclipseDiagram`.

### Integration

In `ResultDetailPage.tsx`, import `OverlayDiagram` and add after the `grid grid-cols-3` row:

```tsx
<Card>
  <CardHeader>
    <CardTitle className="text-sm font-medium text-muted-foreground">
      Tychos vs JPL (Overlay)
    </CardTitle>
  </CardHeader>
  <CardContent className="flex justify-center">
    <OverlayDiagram
      testType={result.test_type}
      tychosSunRa={result.sun_ra_rad}
      tychosSunDec={result.sun_dec_rad}
      tychosMoonRa={result.moon_ra_rad}
      tychosMoonDec={result.moon_dec_rad}
      tychosMoonRaVel={result.moon_ra_vel}
      tychosMoonDecVel={result.moon_dec_vel}
      tychosSeparationArcmin={result.min_separation_arcmin}
      jplSunRa={result.jpl_sun_ra_rad}
      jplSunDec={result.jpl_sun_dec_rad}
      jplMoonRa={result.jpl_moon_ra_rad}
      jplMoonDec={result.jpl_moon_dec_rad}
      jplMoonRaVel={result.jpl_moon_ra_vel}
      jplMoonDecVel={result.jpl_moon_dec_vel}
      jplSeparationArcmin={result.jpl_separation_arcmin}
      moonRadiusArcmin={moonR}
      sunRadiusArcmin={result.sun_apparent_radius_arcmin}
      umbraRadiusArcmin={result.umbra_radius_arcmin}
      penumbraRadiusArcmin={result.penumbra_radius_arcmin}
    />
  </CardContent>
</Card>
```

## Testing

The component is pure and deterministic given props. If the admin test suite has precedent for diagram-component tests (check for tests on `PredictedDiagram` / `EclipseDiagram`), follow the same pattern with a minimal render-smoke test covering:
- Solar case with all data present
- Lunar case with all data present
- Empty state when a required field is null

If no such precedent exists, skip tests for this PR and rely on visual verification — matching current practice in the admin UI.

## Out of Scope

- Toggles to hide/show individual engines
- Zoom/pan controls
- Animation or time-scrubbing
- Any backend or API changes
