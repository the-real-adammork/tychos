import { useState } from "react";

type HoverFilter = "suns" | "moons" | "tychos" | "jpl" | null;

interface OverlayDiagramProps {
  testType: string;
  // Tychos positions at JPL's best_jd
  tychosSunRa: number | null;
  tychosSunDec: number | null;
  tychosMoonRa: number | null;
  tychosMoonDec: number | null;
  // JPL positions at JPL's best_jd
  jplSunRa: number | null;
  jplSunDec: number | null;
  jplMoonRa: number | null;
  jplMoonDec: number | null;
  // Shared geometry
  moonRadiusArcmin: number;
  sunRadiusArcmin: number | null;
  umbraRadiusArcmin: number | null;
  penumbraRadiusArcmin: number | null;
}

// Tychos: blue family — Sun = bright cyan, Moon = deeper indigo
const TYCHOS_SUN_STROKE = "rgba(120,220,255,0.9)";
const TYCHOS_SUN_FILL = "rgba(120,220,255,0.18)";
const TYCHOS_MOON_STROKE = "rgba(140,140,255,0.9)";
const TYCHOS_MOON_FILL = "rgba(140,140,255,0.22)";
// JPL: warm family — Sun = yellow-amber, Moon = red-orange
const JPL_SUN_STROKE = "rgba(255,210,90,0.9)";
const JPL_SUN_FILL = "rgba(255,210,90,0.18)";
const JPL_MOON_STROKE = "rgba(255,130,90,0.9)";
const JPL_MOON_FILL = "rgba(255,130,90,0.22)";

// Standard zoom levels for the reference circles (arcmin)
const ZOOM_LEVELS = [30, 45, 60, 75, 90, 120, 150];

function antiSolar(ra: number, dec: number): [number, number] {
  return [(ra + Math.PI) % (2 * Math.PI), -dec];
}

export function OverlayDiagram(props: OverlayDiagramProps) {
  const {
    testType,
    tychosSunRa, tychosSunDec, tychosMoonRa, tychosMoonDec,
    jplSunRa, jplSunDec, jplMoonRa, jplMoonDec,
    moonRadiusArcmin, sunRadiusArcmin, umbraRadiusArcmin, penumbraRadiusArcmin,
  } = props;

  const isLunar = testType === "lunar";

  if (
    tychosSunRa == null || tychosSunDec == null || tychosMoonRa == null || tychosMoonDec == null ||
    jplSunRa == null || jplSunDec == null || jplMoonRa == null || jplMoonDec == null
  ) {
    return <p className="text-sm text-muted-foreground">No overlay data available</p>;
  }

  // Per-engine center (Sun for solar, anti-solar shadow point for lunar)
  const [tCenterRa, tCenterDec] = isLunar ? antiSolar(tychosSunRa, tychosSunDec) : [tychosSunRa, tychosSunDec];
  const [jCenterRa, jCenterDec] = isLunar ? antiSolar(jplSunRa, jplSunDec) : [jplSunRa, jplSunDec];

  // Origin = midpoint of the two centers
  const originRa = (tCenterRa + jCenterRa) / 2;
  const originDec = (tCenterDec + jCenterDec) / 2;

  const project = (ra: number, dec: number): [number, number] => {
    const avgDec = (originDec + dec) / 2;
    const dx = (ra - originRa) * Math.cos(avgDec) * (180 / Math.PI) * 60;
    const dy = (dec - originDec) * (180 / Math.PI) * 60;
    return [dx, dy];
  };

  // Project all four objects to find the bounding extent
  const projected = [
    project(tCenterRa, tCenterDec),
    project(jCenterRa, jCenterDec),
    project(tychosMoonRa, tychosMoonDec),
    project(jplMoonRa, jplMoonDec),
  ];
  const maxExtent = Math.max(
    ...projected.map(([dx, dy]) => Math.max(Math.abs(dx), Math.abs(dy)))
  );

  // Pick a zoom level that fits all objects with padding for the body radii
  const bodyPad = Math.max(moonRadiusArcmin, sunRadiusArcmin ?? 16, umbraRadiusArcmin ?? 0) + 5;
  const neededExtent = maxExtent + bodyPad;
  // Pick the smallest ZOOM_LEVELS entry that contains everything
  const viewExtent = ZOOM_LEVELS.find(z => z >= neededExtent) ?? Math.ceil(neededExtent / 15) * 15;
  // Which zoom levels fit within the view
  const visibleZooms = ZOOM_LEVELS.filter(z => z <= viewExtent);

  const svgSize = 700;
  const scale = svgSize / (viewExtent * 2);
  const cx = svgSize / 2;
  const cy = svgSize / 2;

  const toScreen = ([dx, dy]: [number, number]): [number, number] => [cx + dx * scale, cy - dy * scale];

  const [tCx, tCy] = toScreen(project(tCenterRa, tCenterDec));
  const [jCx, jCy] = toScreen(project(jCenterRa, jCenterDec));
  const [tMx, tMy] = toScreen(project(tychosMoonRa, tychosMoonDec));
  const [jMx, jMy] = toScreen(project(jplMoonRa, jplMoonDec));

  // Sun-to-Sun and Moon-to-Moon deltas in arcmin
  const [tSdx, tSdy] = project(tCenterRa, tCenterDec);
  const [jSdx, jSdy] = project(jCenterRa, jCenterDec);
  const sunDeltaArcmin = Math.sqrt((tSdx - jSdx) ** 2 + (tSdy - jSdy) ** 2);
  const [tMdx, tMdy] = project(tychosMoonRa, tychosMoonDec);
  const [jMdx, jMdy] = project(jplMoonRa, jplMoonDec);
  const moonDeltaArcmin = Math.sqrt((tMdx - jMdx) ** 2 + (tMdy - jMdy) ** 2);

  const sunR = (sunRadiusArcmin ?? 16) * scale;
  const umbraR = (umbraRadiusArcmin ?? 42) * scale;
  const penumbraR = (penumbraRadiusArcmin ?? 78) * scale;
  const moonR = moonRadiusArcmin * scale;

  const [hover, setHover] = useState<HoverFilter>(null);

  // Visibility: when hovering a filter button, only matching objects are fully opaque
  const showTychosSun = hover === null || hover === "suns" || hover === "tychos";
  const showTychosMoon = hover === null || hover === "moons" || hover === "tychos";
  const showJplSun = hover === null || hover === "suns" || hover === "jpl";
  const showJplMoon = hover === null || hover === "moons" || hover === "jpl";

  const filterBtns: { label: string; value: HoverFilter }[] = [
    { label: "Suns", value: "suns" },
    { label: "Moons", value: "moons" },
    { label: "Tychos", value: "tychos" },
    { label: "JPL", value: "jpl" },
  ];

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="flex gap-2">
        {filterBtns.map(b => (
          <button
            key={b.value}
            type="button"
            className="px-3 py-1 text-xs font-medium rounded border border-border bg-secondary text-secondary-foreground hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
            onMouseEnter={() => setHover(b.value)}
            onMouseLeave={() => setHover(null)}
          >
            {b.label}
          </button>
        ))}
      </div>
      <svg width={svgSize} height={svgSize} className="border rounded-lg bg-zinc-950">
        {/* Grid lines */}
        {[-120, -90, -75, -60, -45, -30, -15, 0, 15, 30, 45, 60, 75, 90, 120].filter(v => Math.abs(v) <= viewExtent).map(v => (
          <g key={v}>
            <line x1={cx + v * scale} y1={0} x2={cx + v * scale} y2={svgSize} stroke="rgba(255,255,255,0.05)" strokeWidth={1} />
            <line x1={0} y1={cy - v * scale} x2={svgSize} y2={cy - v * scale} stroke="rgba(255,255,255,0.05)" strokeWidth={1} />
          </g>
        ))}

        {/* Reference zoom circles (dotted) */}
        {visibleZooms.map(z => (
          <g key={`zoom-${z}`}>
            <circle cx={cx} cy={cy} r={z * scale} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth={1} strokeDasharray="4 4" />
            <text
              x={cx + z * scale + 3} y={cy - 3}
              fill="rgba(255,255,255,0.25)" fontSize={9} fontFamily="monospace"
            >
              {z}'
            </text>
          </g>
        ))}

        {/* Tychos Sun/shadow */}
        <g opacity={showTychosSun ? 1 : 0.08} style={{ transition: "opacity 0.15s" }}>
          {isLunar ? (
            <>
              <circle cx={tCx} cy={tCy} r={penumbraR} fill="none" stroke={TYCHOS_SUN_STROKE} strokeWidth={1} strokeDasharray="2 3" opacity={0.6} />
              <circle cx={tCx} cy={tCy} r={umbraR} fill={TYCHOS_SUN_FILL} stroke={TYCHOS_SUN_STROKE} strokeWidth={1.5} />
            </>
          ) : (
            <circle cx={tCx} cy={tCy} r={sunR} fill={TYCHOS_SUN_FILL} stroke={TYCHOS_SUN_STROKE} strokeWidth={1.5} />
          )}
        </g>

        {/* JPL Sun/shadow */}
        <g opacity={showJplSun ? 1 : 0.08} style={{ transition: "opacity 0.15s" }}>
          {isLunar ? (
            <>
              <circle cx={jCx} cy={jCy} r={penumbraR} fill="none" stroke={JPL_SUN_STROKE} strokeWidth={1} strokeDasharray="2 3" opacity={0.6} />
              <circle cx={jCx} cy={jCy} r={umbraR} fill={JPL_SUN_FILL} stroke={JPL_SUN_STROKE} strokeWidth={1.5} />
            </>
          ) : (
            <circle cx={jCx} cy={jCy} r={sunR} fill={JPL_SUN_FILL} stroke={JPL_SUN_STROKE} strokeWidth={1.5} />
          )}
        </g>

        {/* Tychos center→Moon line + Moon */}
        <g opacity={showTychosMoon && showTychosSun ? 1 : 0.08} style={{ transition: "opacity 0.15s" }}>
          <line x1={tCx} y1={tCy} x2={tMx} y2={tMy} stroke={TYCHOS_MOON_STROKE} strokeWidth={1} strokeDasharray="3 3" />
        </g>
        <g opacity={showTychosMoon ? 1 : 0.08} style={{ transition: "opacity 0.15s" }}>
          <circle cx={tMx} cy={tMy} r={moonR} fill={TYCHOS_MOON_FILL} stroke={TYCHOS_MOON_STROKE} strokeWidth={1.5} />
        </g>

        {/* JPL center→Moon line + Moon */}
        <g opacity={showJplMoon && showJplSun ? 1 : 0.08} style={{ transition: "opacity 0.15s" }}>
          <line x1={jCx} y1={jCy} x2={jMx} y2={jMy} stroke={JPL_MOON_STROKE} strokeWidth={1} strokeDasharray="3 3" />
        </g>
        <g opacity={showJplMoon ? 1 : 0.08} style={{ transition: "opacity 0.15s" }}>
          <circle cx={jMx} cy={jMy} r={moonR} fill={JPL_MOON_FILL} stroke={JPL_MOON_STROKE} strokeWidth={1.5} />
        </g>

        {/* Sun↔Sun delta (visible when both suns shown) */}
        <g opacity={showTychosSun && showJplSun ? 1 : 0} style={{ transition: "opacity 0.15s" }}>
          {sunDeltaArcmin > 0.01 && (
            <>
              <line x1={tCx} y1={tCy} x2={jCx} y2={jCy} stroke="rgba(255,255,255,0.5)" strokeWidth={1} strokeDasharray="2 2" />
              <text x={(tCx + jCx) / 2 + 6} y={(tCy + jCy) / 2 - 6} fill="rgba(255,255,255,0.7)" fontSize={10} fontFamily="monospace">
                Δ☉ {sunDeltaArcmin.toFixed(2)}'
              </text>
            </>
          )}
        </g>

        {/* Moon↔Moon delta (visible when both moons shown) */}
        <g opacity={showTychosMoon && showJplMoon ? 1 : 0} style={{ transition: "opacity 0.15s" }}>
          <line x1={tMx} y1={tMy} x2={jMx} y2={jMy} stroke="rgba(255,255,255,0.7)" strokeWidth={1} strokeDasharray="2 2" />
          <text x={(tMx + jMx) / 2 + 6} y={(tMy + jMy) / 2 - 6} fill="rgba(255,255,255,0.85)" fontSize={10} fontFamily="monospace">
            Δ☽ {moonDeltaArcmin.toFixed(2)}'
          </text>
        </g>

        {/* Legend */}
        <g>
          <rect x={svgSize - 150} y={10} width={140} height={60} rx={4} fill="rgba(0,0,0,0.5)" stroke="rgba(255,255,255,0.15)" />
          <text x={svgSize - 140} y={27} fill="rgba(220,220,220,0.7)" fontSize={10} fontWeight="bold">Tychos</text>
          <circle cx={svgSize - 90} cy={24} r={5} fill={TYCHOS_SUN_FILL} stroke={TYCHOS_SUN_STROKE} strokeWidth={1.5} />
          <text x={svgSize - 80} y={27} fill="rgba(220,220,220,0.9)" fontSize={10}>Sun</text>
          <circle cx={svgSize - 50} cy={24} r={5} fill={TYCHOS_MOON_FILL} stroke={TYCHOS_MOON_STROKE} strokeWidth={1.5} />
          <text x={svgSize - 40} y={27} fill="rgba(220,220,220,0.9)" fontSize={10}>Moon</text>
          <text x={svgSize - 140} y={47} fill="rgba(220,220,220,0.7)" fontSize={10} fontWeight="bold">JPL</text>
          <circle cx={svgSize - 90} cy={44} r={5} fill={JPL_SUN_FILL} stroke={JPL_SUN_STROKE} strokeWidth={1.5} />
          <text x={svgSize - 80} y={47} fill="rgba(220,220,220,0.9)" fontSize={10}>Sun</text>
          <circle cx={svgSize - 50} cy={44} r={5} fill={JPL_MOON_FILL} stroke={JPL_MOON_STROKE} strokeWidth={1.5} />
          <text x={svgSize - 40} y={47} fill="rgba(220,220,220,0.9)" fontSize={10}>Moon</text>
          <text x={svgSize - 140} y={63} fill="rgba(255,255,255,0.5)" fontSize={9}>at JPL's best_jd</text>
        </g>

        {/* Scale bar */}
        <line x1={10} y1={svgSize - 15} x2={10 + 10 * scale} y2={svgSize - 15} stroke="rgba(255,255,255,0.4)" strokeWidth={2} />
        <text x={10} y={svgSize - 5} fill="rgba(255,255,255,0.4)" fontSize={9}>10 arcmin</text>
      </svg>
      <p className="text-xs text-muted-foreground">
        Both models at JPL's moment of minimum separation · Centered on {isLunar ? "shadow" : "Sun"} midpoint · N↑ E←
      </p>
    </div>
  );
}
