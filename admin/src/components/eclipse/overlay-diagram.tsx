interface OverlayDiagramProps {
  testType: string;
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

function antiSolar(ra: number, dec: number): [number, number] {
  return [(ra + Math.PI) % (2 * Math.PI), -dec];
}

export function OverlayDiagram(props: OverlayDiagramProps) {
  const {
    testType,
    tychosSunRa, tychosSunDec, tychosMoonRa, tychosMoonDec,
    tychosMoonRaVel, tychosMoonDecVel, tychosSeparationArcmin,
    jplSunRa, jplSunDec, jplMoonRa, jplMoonDec,
    jplMoonRaVel, jplMoonDecVel, jplSeparationArcmin,
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

  const viewExtent = isLunar ? 100 : 60;
  const svgSize = 700;
  const scale = svgSize / (viewExtent * 2);
  const cx = svgSize / 2;
  const cy = svgSize / 2;
  const thresholdArcmin = isLunar ? 90 : 48;

  const toScreen = ([dx, dy]: [number, number]): [number, number] => [cx + dx * scale, cy - dy * scale];

  const [tCx, tCy] = toScreen(project(tCenterRa, tCenterDec));
  const [jCx, jCy] = toScreen(project(jCenterRa, jCenterDec));
  const [tMx, tMy] = toScreen(project(tychosMoonRa, tychosMoonDec));
  const [jMx, jMy] = toScreen(project(jplMoonRa, jplMoonDec));

  // Moon-to-moon delta in arcmin (Euclidean in projected plane)
  const [tMdx, tMdy] = project(tychosMoonRa, tychosMoonDec);
  const [jMdx, jMdy] = project(jplMoonRa, jplMoonDec);
  const moonDeltaArcmin = Math.sqrt((tMdx - jMdx) ** 2 + (tMdy - jMdy) ** 2);

  const sunR = (sunRadiusArcmin ?? 16) * scale;
  const umbraR = (umbraRadiusArcmin ?? 42) * scale;
  const penumbraR = (penumbraRadiusArcmin ?? 78) * scale;
  const moonR = moonRadiusArcmin * scale;

  const renderVelocity = (
    mx: number, my: number, dec: number,
    raVel: number | null, decVel: number | null,
    color: string,
    key: string,
  ) => {
    if (raVel == null || decVel == null) return null;
    const velDx = raVel * Math.cos(dec) * (180 / Math.PI) * 60 * 3;
    const velDy = decVel * (180 / Math.PI) * 60 * 3;
    const ex = mx + velDx * scale;
    const ey = my - velDy * scale;
    const len = Math.sqrt((ex - mx) ** 2 + (ey - my) ** 2);
    if (len < 2) return null;
    const ang = Math.atan2(ey - my, ex - mx);
    const headLen = 7;
    const h1x = ex - headLen * Math.cos(ang - 0.4);
    const h1y = ey - headLen * Math.sin(ang - 0.4);
    const h2x = ex - headLen * Math.cos(ang + 0.4);
    const h2y = ey - headLen * Math.sin(ang + 0.4);
    return (
      <g key={key}>
        <line x1={mx} y1={my} x2={ex} y2={ey} stroke={color} strokeWidth={1.5} />
        <polygon points={`${ex},${ey} ${h1x},${h1y} ${h2x},${h2y}`} fill={color} />
      </g>
    );
  };

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={svgSize} height={svgSize} className="border rounded-lg bg-zinc-950">
        {/* Grid */}
        {[-80, -60, -40, -20, 0, 20, 40, 60, 80].filter(v => Math.abs(v) <= viewExtent).map(v => (
          <g key={v}>
            <line x1={cx + v * scale} y1={0} x2={cx + v * scale} y2={svgSize} stroke="rgba(255,255,255,0.05)" strokeWidth={1} />
            <line x1={0} y1={cy - v * scale} x2={svgSize} y2={cy - v * scale} stroke="rgba(255,255,255,0.05)" strokeWidth={1} />
          </g>
        ))}

        {/* Threshold reference at origin */}
        <circle cx={cx} cy={cy} r={thresholdArcmin * scale} fill="none" stroke="rgba(255,255,100,0.3)" strokeWidth={1} strokeDasharray="4 4" />

        {/* Tychos Sun/shadow */}
        {isLunar ? (
          <>
            <circle cx={tCx} cy={tCy} r={penumbraR} fill="none" stroke={TYCHOS_SUN_STROKE} strokeWidth={1} strokeDasharray="2 3" opacity={0.6} />
            <circle cx={tCx} cy={tCy} r={umbraR} fill={TYCHOS_SUN_FILL} stroke={TYCHOS_SUN_STROKE} strokeWidth={1.5} />
          </>
        ) : (
          <circle cx={tCx} cy={tCy} r={sunR} fill={TYCHOS_SUN_FILL} stroke={TYCHOS_SUN_STROKE} strokeWidth={1.5} />
        )}

        {/* JPL Sun/shadow */}
        {isLunar ? (
          <>
            <circle cx={jCx} cy={jCy} r={penumbraR} fill="none" stroke={JPL_SUN_STROKE} strokeWidth={1} strokeDasharray="2 3" opacity={0.6} />
            <circle cx={jCx} cy={jCy} r={umbraR} fill={JPL_SUN_FILL} stroke={JPL_SUN_STROKE} strokeWidth={1.5} />
          </>
        ) : (
          <circle cx={jCx} cy={jCy} r={sunR} fill={JPL_SUN_FILL} stroke={JPL_SUN_STROKE} strokeWidth={1.5} />
        )}

        {/* Tychos center→Moon line */}
        <line x1={tCx} y1={tCy} x2={tMx} y2={tMy} stroke={TYCHOS_MOON_STROKE} strokeWidth={1} strokeDasharray="3 3" />
        {/* JPL center→Moon line */}
        <line x1={jCx} y1={jCy} x2={jMx} y2={jMy} stroke={JPL_MOON_STROKE} strokeWidth={1} strokeDasharray="3 3" />

        {/* Tychos Moon */}
        <circle cx={tMx} cy={tMy} r={moonR} fill={TYCHOS_MOON_FILL} stroke={TYCHOS_MOON_STROKE} strokeWidth={1.5} />
        {/* JPL Moon */}
        <circle cx={jMx} cy={jMy} r={moonR} fill={JPL_MOON_FILL} stroke={JPL_MOON_STROKE} strokeWidth={1.5} />

        {/* Velocity arrows */}
        {renderVelocity(tMx, tMy, tychosMoonDec, tychosMoonRaVel, tychosMoonDecVel, TYCHOS_MOON_STROKE, "tvel")}
        {renderVelocity(jMx, jMy, jplMoonDec, jplMoonRaVel, jplMoonDecVel, JPL_MOON_STROKE, "jvel")}

        {/* Separation labels */}
        {tychosSeparationArcmin != null && (
          <text x={(tCx + tMx) / 2 + 8} y={(tCy + tMy) / 2 - 8} fill={TYCHOS_MOON_STROKE} fontSize={11} fontFamily="monospace">
            {tychosSeparationArcmin.toFixed(1)}'
          </text>
        )}
        {jplSeparationArcmin != null && (
          <text x={(jCx + jMx) / 2 + 8} y={(jCy + jMy) / 2 + 14} fill={JPL_MOON_STROKE} fontSize={11} fontFamily="monospace">
            {jplSeparationArcmin.toFixed(1)}'
          </text>
        )}

        {/* Tychos↔JPL Moon delta */}
        <line x1={tMx} y1={tMy} x2={jMx} y2={jMy} stroke="rgba(255,255,255,0.7)" strokeWidth={1} strokeDasharray="2 2" />
        <text x={(tMx + jMx) / 2 + 6} y={(tMy + jMy) / 2 - 6} fill="rgba(255,255,255,0.85)" fontSize={11} fontFamily="monospace">
          Δ {moonDeltaArcmin.toFixed(2)}'
        </text>

        {/* Threshold label */}
        <text x={svgSize - 5} y={15} textAnchor="end" fill="rgba(255,255,100,0.5)" fontSize={9}>
          - - - reference ({thresholdArcmin.toFixed(0)}')
        </text>

        {/* Legend */}
        <g>
          <rect x={svgSize - 150} y={25} width={140} height={74} rx={4} fill="rgba(0,0,0,0.5)" stroke="rgba(255,255,255,0.15)" />
          <text x={svgSize - 140} y={42} fill="rgba(220,220,220,0.7)" fontSize={10} fontWeight="bold">Tychos</text>
          <circle cx={svgSize - 90} cy={39} r={5} fill={TYCHOS_SUN_FILL} stroke={TYCHOS_SUN_STROKE} strokeWidth={1.5} />
          <text x={svgSize - 80} y={42} fill="rgba(220,220,220,0.9)" fontSize={10}>Sun</text>
          <circle cx={svgSize - 50} cy={39} r={5} fill={TYCHOS_MOON_FILL} stroke={TYCHOS_MOON_STROKE} strokeWidth={1.5} />
          <text x={svgSize - 40} y={42} fill="rgba(220,220,220,0.9)" fontSize={10}>Moon</text>
          <text x={svgSize - 140} y={62} fill="rgba(220,220,220,0.7)" fontSize={10} fontWeight="bold">JPL</text>
          <circle cx={svgSize - 90} cy={59} r={5} fill={JPL_SUN_FILL} stroke={JPL_SUN_STROKE} strokeWidth={1.5} />
          <text x={svgSize - 80} y={62} fill="rgba(220,220,220,0.9)" fontSize={10}>Sun</text>
          <circle cx={svgSize - 50} cy={59} r={5} fill={JPL_MOON_FILL} stroke={JPL_MOON_STROKE} strokeWidth={1.5} />
          <text x={svgSize - 40} y={62} fill="rgba(220,220,220,0.9)" fontSize={10}>Moon</text>
          <line x1={svgSize - 140} y1={82} x2={svgSize - 120} y2={82} stroke="rgba(255,255,255,0.7)" strokeWidth={1} strokeDasharray="2 2" />
          <text x={svgSize - 115} y={86} fill="rgba(220,220,220,0.9)" fontSize={10}>Δ Moon offset</text>
        </g>

        {/* Scale bar */}
        <line x1={10} y1={svgSize - 15} x2={10 + 10 * scale} y2={svgSize - 15} stroke="rgba(255,255,255,0.4)" strokeWidth={2} />
        <text x={10} y={svgSize - 5} fill="rgba(255,255,255,0.4)" fontSize={9}>10 arcmin</text>
      </svg>
      <p className="text-xs text-muted-foreground">
        Centered on {isLunar ? "Earth shadow" : "Sun"} midpoint · N↑ E←
      </p>
    </div>
  );
}
