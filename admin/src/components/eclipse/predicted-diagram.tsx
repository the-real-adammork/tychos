interface PredictedDiagramProps {
  testType: string;
  expectedSeparationArcmin: number;
  approachAngleDeg: number | null;
  moonRadiusArcmin: number;
  sunRadiusArcmin: number | null;
  umbraRadiusArcmin: number | null;
  penumbraRadiusArcmin: number | null;
}

export function PredictedDiagram({
  testType,
  expectedSeparationArcmin,
  approachAngleDeg,
  moonRadiusArcmin,
  sunRadiusArcmin,
  umbraRadiusArcmin,
  penumbraRadiusArcmin,
}: PredictedDiagramProps) {
  const isLunar = testType === "lunar";
  const viewExtent = isLunar ? 100 : 60;
  const svgSize = 400;
  const scale = svgSize / (viewExtent * 2);
  const cx = svgSize / 2;
  const cy = svgSize / 2;
  const thresholdArcmin = isLunar ? 90 : 48;

  const angle = ((approachAngleDeg ?? 90) * Math.PI) / 180;
  const dx = expectedSeparationArcmin * Math.cos(angle);
  const dy = expectedSeparationArcmin * Math.sin(angle);
  const moonX = cx + dx * scale;
  const moonY = cy - dy * scale;

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={svgSize} height={svgSize} className="border rounded-lg bg-zinc-950">
        {[-40, -30, -20, -10, 0, 10, 20, 30, 40].filter(v => Math.abs(v) <= viewExtent).map(v => (
          <g key={v}>
            <line x1={cx + v * scale} y1={0} x2={cx + v * scale} y2={svgSize} stroke="rgba(255,255,255,0.05)" strokeWidth={1} />
            <line x1={0} y1={cy - v * scale} x2={svgSize} y2={cy - v * scale} stroke="rgba(255,255,255,0.05)" strokeWidth={1} />
          </g>
        ))}

        {/* Detection threshold reference circle */}
        <circle cx={cx} cy={cy} r={thresholdArcmin * scale} fill="none" stroke="rgba(255,255,100,0.3)" strokeWidth={1} strokeDasharray="4 4" />

        {isLunar ? (
          <>
            <circle cx={cx} cy={cy} r={(penumbraRadiusArcmin ?? 78) * scale} fill="rgba(100,100,100,0.15)" stroke="rgba(150,150,150,0.3)" strokeWidth={1} />
            <circle cx={cx} cy={cy} r={(umbraRadiusArcmin ?? 42) * scale} fill="rgba(50,50,50,0.3)" stroke="rgba(200,100,100,0.5)" strokeWidth={1.5} />
            <text x={cx} y={cy + 4} textAnchor="middle" fill="rgba(200,200,200,0.4)" fontSize={10}>Shadow</text>
          </>
        ) : (
          <>
            <circle cx={cx} cy={cy} r={(sunRadiusArcmin ?? 16) * scale} fill="rgba(255,200,50,0.2)" stroke="rgba(255,200,50,0.6)" strokeWidth={1.5} />
            <text x={cx} y={cy + 4} textAnchor="middle" fill="rgba(255,200,50,0.5)" fontSize={10}>Sun</text>
          </>
        )}

        <circle cx={moonX} cy={moonY} r={moonRadiusArcmin * scale} fill="rgba(180,180,180,0.2)" stroke="rgba(180,180,180,0.7)" strokeWidth={1.5} />
        <text x={moonX} y={moonY + 4} textAnchor="middle" fill="rgba(200,200,200,0.6)" fontSize={10}>Moon</text>

        <line x1={cx} y1={cy} x2={moonX} y2={moonY} stroke="rgba(255,100,100,0.5)" strokeWidth={1} strokeDasharray="3 3" />
        <text x={(cx + moonX) / 2 + 8} y={(cy + moonY) / 2 - 8} fill="rgba(255,150,150,0.8)" fontSize={11} fontFamily="monospace">
          {expectedSeparationArcmin.toFixed(1)}'
        </text>

        <text x={svgSize - 5} y={15} textAnchor="end" fill="rgba(255,255,100,0.5)" fontSize={9}>
          - - - reference ({thresholdArcmin.toFixed(0)}')
        </text>

        <line x1={10} y1={svgSize - 15} x2={10 + 10 * scale} y2={svgSize - 15} stroke="rgba(255,255,255,0.4)" strokeWidth={2} />
        <text x={10} y={svgSize - 5} fill="rgba(255,255,255,0.4)" fontSize={9}>10 arcmin</text>
      </svg>
      <p className="text-xs text-muted-foreground">
        {isLunar ? "Centered on Earth shadow" : "Centered on Sun"} · Catalog-derived
      </p>
    </div>
  );
}
