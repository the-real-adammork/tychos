import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface ResultDetail {
  id: number;
  run_id: number;
  julian_day_tt: number;
  date: string;
  catalog_type: string;
  magnitude: number;
  detected: boolean | number;
  threshold_arcmin: number;
  min_separation_arcmin: number | null;
  timing_offset_min: number | null;
  best_jd: number | null;
  sun_ra_rad: number | null;
  sun_dec_rad: number | null;
  moon_ra_rad: number | null;
  moon_dec_rad: number | null;
  test_type: string;
  version_number: number;
  param_set_id: number;
  param_set_name: string;
}

// Mean angular radii in arcminutes
const SUN_RADIUS_ARCMIN = 16.0;
const MOON_RADIUS_ARCMIN = 15.55;
const UMBRA_RADIUS_ARCMIN = 42.0;
const PENUMBRA_RADIUS_ARCMIN = 78.0;

function radToHMS(rad: number): string {
  const hours = (rad * 12) / Math.PI;
  const h = Math.floor(hours);
  const m = Math.floor((hours - h) * 60);
  const s = ((hours - h) * 60 - m) * 60;
  return `${h}h ${m.toString().padStart(2, "0")}m ${s.toFixed(1).padStart(4, "0")}s`;
}

function radToDMS(rad: number): string {
  const deg = (rad * 180) / Math.PI;
  const sign = deg >= 0 ? "+" : "-";
  const absDeg = Math.abs(deg);
  const d = Math.floor(absDeg);
  const m = Math.floor((absDeg - d) * 60);
  const s = ((absDeg - d) * 60 - m) * 60;
  return `${sign}${d}\u00B0 ${m.toString().padStart(2, "0")}' ${s.toFixed(1).padStart(4, "0")}"`;
}

function SkyPositionDiagram({ result }: { result: ResultDetail }) {
  const sunRa = result.sun_ra_rad;
  const sunDec = result.sun_dec_rad;
  const moonRa = result.moon_ra_rad;
  const moonDec = result.moon_dec_rad;

  if (sunRa == null || sunDec == null || moonRa == null || moonDec == null) {
    return <p className="text-sm text-muted-foreground">No position data</p>;
  }

  // Full sky: RA 0-24h (0 to 2π), Dec -90° to +90° (-π/2 to π/2)
  const svgW = 400;
  const svgH = 200;
  const pad = 30;
  const plotW = svgW - pad * 2;
  const plotH = svgH - pad * 2;

  // Map RA (0 to 2π) → x, reversed so RA increases right-to-left (sky convention)
  const raToX = (ra: number) => pad + plotW - (ra / (2 * Math.PI)) * plotW;
  // Map Dec (-π/2 to π/2) → y, flipped so +Dec is up
  const decToY = (dec: number) => pad + plotH / 2 - (dec / (Math.PI / 2)) * (plotH / 2);

  const sunX = raToX(sunRa);
  const sunY = decToY(sunDec);
  const moonX = raToX(moonRa);
  const moonY = decToY(moonDec);

  // Ecliptic: approximate as sinusoidal with obliquity 23.44°
  const obliquity = 23.44 * (Math.PI / 180);
  const eclipticPoints: string[] = [];
  for (let i = 0; i <= 100; i++) {
    const ra = (i / 100) * 2 * Math.PI;
    const dec = Math.asin(Math.sin(obliquity) * Math.sin(ra));
    eclipticPoints.push(`${raToX(ra)},${decToY(dec)}`);
  }

  // RA hour labels
  const raLabels = [0, 3, 6, 9, 12, 15, 18, 21];

  return (
    <div className="flex flex-col gap-2">
      <svg width={svgW} height={svgH} className="border rounded-lg bg-zinc-950">
        {/* Dec grid lines */}
        {[-60, -30, 0, 30, 60].map(d => {
          const decRad = d * (Math.PI / 180);
          const y = decToY(decRad);
          return (
            <g key={d}>
              <line x1={pad} y1={y} x2={svgW - pad} y2={y} stroke="rgba(255,255,255,0.07)" strokeWidth={1} />
              <text x={pad - 4} y={y + 3} textAnchor="end" fill="rgba(255,255,255,0.25)" fontSize={8}>{d}°</text>
            </g>
          );
        })}

        {/* RA grid lines */}
        {raLabels.map(h => {
          const ra = h * (Math.PI / 12);
          const x = raToX(ra);
          return (
            <g key={h}>
              <line x1={x} y1={pad} x2={x} y2={svgH - pad} stroke="rgba(255,255,255,0.07)" strokeWidth={1} />
              <text x={x} y={svgH - pad + 12} textAnchor="middle" fill="rgba(255,255,255,0.25)" fontSize={8}>{h}h</text>
            </g>
          );
        })}

        {/* Ecliptic */}
        <polyline points={eclipticPoints.join(" ")} fill="none" stroke="rgba(255,200,50,0.15)" strokeWidth={1} />

        {/* Celestial equator */}
        <line x1={pad} y1={decToY(0)} x2={svgW - pad} y2={decToY(0)} stroke="rgba(100,150,255,0.15)" strokeWidth={1} />

        {/* Sun */}
        <circle cx={sunX} cy={sunY} r={6} fill="rgba(255,200,50,0.4)" stroke="rgba(255,200,50,0.8)" strokeWidth={1.5} />
        <text x={sunX} y={sunY - 9} textAnchor="middle" fill="rgba(255,200,50,0.7)" fontSize={9}>Sun</text>

        {/* Moon */}
        <circle cx={moonX} cy={moonY} r={5} fill="rgba(180,180,180,0.3)" stroke="rgba(180,180,180,0.8)" strokeWidth={1.5} />
        <text x={moonX} y={moonY - 9} textAnchor="middle" fill="rgba(200,200,200,0.7)" fontSize={9}>Moon</text>

        {/* Connection line */}
        <line x1={sunX} y1={sunY} x2={moonX} y2={moonY} stroke="rgba(255,100,100,0.3)" strokeWidth={1} strokeDasharray="2 2" />
      </svg>

      {/* Text readout below */}
      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
        <div>
          <span className="text-muted-foreground">Sun  RA:</span> {radToHMS(sunRa)}
        </div>
        <div>
          <span className="text-muted-foreground">Dec:</span> {radToDMS(sunDec)}
        </div>
        <div>
          <span className="text-muted-foreground">Moon RA:</span> {radToHMS(moonRa)}
        </div>
        <div>
          <span className="text-muted-foreground">Dec:</span> {radToDMS(moonDec)}
        </div>
      </div>
    </div>
  );
}

function EclipseDiagram({ result }: { result: ResultDetail }) {
  const isLunar = result.test_type === "lunar";
  const sunRa = result.sun_ra_rad;
  const sunDec = result.sun_dec_rad;
  const moonRa = result.moon_ra_rad;
  const moonDec = result.moon_dec_rad;

  if (sunRa == null || sunDec == null || moonRa == null || moonDec == null) {
    return <p className="text-sm text-muted-foreground">No position data available</p>;
  }

  // For solar: center on Sun, show Moon relative
  // For lunar: center on anti-solar point (Earth shadow), show Moon relative
  let centerRa: number, centerDec: number;
  if (isLunar) {
    centerRa = (sunRa + Math.PI) % (2 * Math.PI);
    centerDec = -sunDec;
  } else {
    centerRa = sunRa;
    centerDec = sunDec;
  }

  const avgDec = (centerDec + moonDec) / 2;
  const dx = (moonRa - centerRa) * Math.cos(avgDec) * (180 / Math.PI) * 60; // arcmin
  const dy = (moonDec - centerDec) * (180 / Math.PI) * 60; // arcmin

  // SVG setup
  const viewExtent = isLunar ? 100 : 50; // arcmin from center
  const svgSize = 400;
  const scale = svgSize / (viewExtent * 2);
  const cx = svgSize / 2;
  const cy = svgSize / 2;

  const moonX = cx + dx * scale;
  const moonY = cy - dy * scale; // flip Y for screen coords

  const thresholdR = result.threshold_arcmin * scale;

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={svgSize} height={svgSize} className="border rounded-lg bg-zinc-950">
        {/* Grid lines */}
        {[-40, -30, -20, -10, 0, 10, 20, 30, 40].filter(v => Math.abs(v) <= viewExtent).map(v => (
          <g key={v}>
            <line
              x1={cx + v * scale} y1={0} x2={cx + v * scale} y2={svgSize}
              stroke="rgba(255,255,255,0.05)" strokeWidth={1}
            />
            <line
              x1={0} y1={cy - v * scale} x2={svgSize} y2={cy - v * scale}
              stroke="rgba(255,255,255,0.05)" strokeWidth={1}
            />
          </g>
        ))}

        {/* Detection threshold circle */}
        <circle cx={cx} cy={cy} r={thresholdR} fill="none" stroke="rgba(255,255,100,0.3)" strokeWidth={1} strokeDasharray="4 4" />

        {isLunar ? (
          <>
            {/* Penumbra */}
            <circle cx={cx} cy={cy} r={PENUMBRA_RADIUS_ARCMIN * scale} fill="rgba(100,100,100,0.15)" stroke="rgba(150,150,150,0.3)" strokeWidth={1} />
            {/* Umbra */}
            <circle cx={cx} cy={cy} r={UMBRA_RADIUS_ARCMIN * scale} fill="rgba(50,50,50,0.3)" stroke="rgba(200,100,100,0.5)" strokeWidth={1.5} />
            {/* Earth shadow center label */}
            <text x={cx} y={cy + 4} textAnchor="middle" fill="rgba(200,200,200,0.4)" fontSize={10}>Shadow</text>
          </>
        ) : (
          <>
            {/* Sun disk */}
            <circle cx={cx} cy={cy} r={SUN_RADIUS_ARCMIN * scale} fill="rgba(255,200,50,0.2)" stroke="rgba(255,200,50,0.6)" strokeWidth={1.5} />
            <text x={cx} y={cy + 4} textAnchor="middle" fill="rgba(255,200,50,0.5)" fontSize={10}>Sun</text>
          </>
        )}

        {/* Moon disk */}
        <circle cx={moonX} cy={moonY} r={MOON_RADIUS_ARCMIN * scale} fill="rgba(180,180,180,0.2)" stroke="rgba(180,180,180,0.7)" strokeWidth={1.5} />
        <text x={moonX} y={moonY + 4} textAnchor="middle" fill="rgba(200,200,200,0.6)" fontSize={10}>Moon</text>

        {/* Separation line */}
        <line x1={cx} y1={cy} x2={moonX} y2={moonY} stroke="rgba(255,100,100,0.5)" strokeWidth={1} strokeDasharray="3 3" />

        {/* Separation label */}
        {result.min_separation_arcmin != null && (
          <text
            x={(cx + moonX) / 2 + 8}
            y={(cy + moonY) / 2 - 8}
            fill="rgba(255,150,150,0.8)"
            fontSize={11}
            fontFamily="monospace"
          >
            {result.min_separation_arcmin.toFixed(1)}'
          </text>
        )}

        {/* Scale bar */}
        <line x1={10} y1={svgSize - 15} x2={10 + 10 * scale} y2={svgSize - 15} stroke="rgba(255,255,255,0.4)" strokeWidth={2} />
        <text x={10} y={svgSize - 5} fill="rgba(255,255,255,0.4)" fontSize={9}>10 arcmin</text>

        {/* Legend */}
        <text x={svgSize - 5} y={15} textAnchor="end" fill="rgba(255,255,100,0.5)" fontSize={9}>
          - - - threshold ({result.threshold_arcmin.toFixed(0)}')
        </text>
      </svg>
      <p className="text-xs text-muted-foreground">
        {isLunar ? "Centered on Earth shadow (anti-solar point)" : "Centered on Sun"} · Scale in arcminutes · N↑ E←
      </p>
    </div>
  );
}

export default function ResultDetailPage() {
  const { runId, resultId } = useParams();
  const navigate = useNavigate();
  const [result, setResult] = useState<ResultDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/results/${runId}/${resultId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setResult)
      .finally(() => setLoading(false));
  }, [runId, resultId]);

  if (loading) return <p className="text-sm text-muted-foreground">Loading...</p>;
  if (!result) return <p className="text-sm text-destructive">Result not found</p>;

  const detected = result.detected === true || result.detected === 1;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">
            Eclipse: {result.date.split("T")[0]}
          </h1>
          <div className="flex items-center gap-3 mt-1">
            <Badge className={`capitalize ${detected
              ? "bg-green-500/15 text-green-600 border-transparent"
              : "bg-red-500/15 text-red-600 border-transparent"
            }`}>
              {detected ? "Detected" : "Missed"}
            </Badge>
            <span className="text-sm text-muted-foreground capitalize">{result.catalog_type}</span>
            <span className="text-sm text-muted-foreground">Magnitude: {result.magnitude}</span>
            <span className="text-sm text-muted-foreground">
              {result.param_set_name} v{result.version_number}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(`/parameters/${result.param_set_id}/versions/${result.run_id}`)}>
            View Version
          </Button>
          <Button variant="outline" onClick={() => navigate(`/results/${runId}`)}>
            Back to Results
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Diagram */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {result.test_type === "lunar" ? "Lunar Eclipse Geometry" : "Solar Eclipse Geometry"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <EclipseDiagram result={result} />
          </CardContent>
        </Card>

        {/* Data */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">Measurements</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Min Separation</span>
                <span className="font-mono">{result.min_separation_arcmin?.toFixed(2) ?? "—"} arcmin</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Detection Threshold</span>
                <span className="font-mono">{result.threshold_arcmin.toFixed(2)} arcmin</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Timing Offset</span>
                <span className="font-mono">{result.timing_offset_min != null ? `${result.timing_offset_min > 0 ? "+" : ""}${result.timing_offset_min.toFixed(1)} min` : "—"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Catalog Date</span>
                <span className="font-mono">{result.date}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Julian Day (TT)</span>
                <span className="font-mono">{result.julian_day_tt}</span>
              </div>
              {result.best_jd != null && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Predicted Best JD</span>
                  <span className="font-mono">{result.best_jd.toFixed(6)}</span>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">Predicted Positions (J2000)</CardTitle>
            </CardHeader>
            <CardContent>
              <SkyPositionDiagram result={result} />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
