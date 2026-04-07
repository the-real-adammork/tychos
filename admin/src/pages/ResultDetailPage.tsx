import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PredictedDiagram } from "@/components/eclipse/predicted-diagram";
import { SarosContext, type SarosNeighbor } from "@/components/eclipse/saros-context";

interface ResultDetail {
  id: number;
  run_id: number;
  julian_day_tt: number;
  date: string;
  test_type: string;
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
  jpl_sun_ra_rad: number | null;
  jpl_sun_dec_rad: number | null;
  jpl_moon_ra_rad: number | null;
  jpl_moon_dec_rad: number | null;
  jpl_separation_arcmin: number | null;
  jpl_moon_ra_vel: number | null;
  jpl_moon_dec_vel: number | null;
  moon_ra_vel: number | null;
  moon_dec_vel: number | null;
  expected_separation_arcmin: number | null;
  moon_apparent_radius_arcmin: number | null;
  sun_apparent_radius_arcmin: number | null;
  umbra_radius_arcmin: number | null;
  penumbra_radius_arcmin: number | null;
  approach_angle_deg: number | null;
  pred_gamma: number | null;
  pred_catalog_magnitude: number | null;
  tychos_error_arcmin: number | null;
  jpl_error_arcmin: number | null;
  dataset_slug: string;
  dataset_name: string;
  version_number: number;
  param_set_id: number;
  param_set_name: string;
  saros_num: number | null;
  saros_position: number | null;
  saros_total: number | null;
  saros_year_start: string | null;
  saros_year_end: string | null;
  saros_neighbors: SarosNeighbor[];
}

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

interface DiagramProps {
  testType: string;
  sunRa: number | null;
  sunDec: number | null;
  moonRa: number | null;
  moonDec: number | null;
  moonRaVel: number | null;
  moonDecVel: number | null;
  separationArcmin: number | null;
  errorArcmin: number | null;
  moonRadiusArcmin: number;
  sunRadiusArcmin: number | null;
  umbraRadiusArcmin: number | null;
  penumbraRadiusArcmin: number | null;
}

function EclipseDiagram({ testType, sunRa, sunDec, moonRa, moonDec, moonRaVel, moonDecVel, separationArcmin, errorArcmin, moonRadiusArcmin, sunRadiusArcmin, umbraRadiusArcmin, penumbraRadiusArcmin }: DiagramProps) {
  const isLunar = testType === "lunar";

  if (sunRa == null || sunDec == null || moonRa == null || moonDec == null) {
    return <p className="text-sm text-muted-foreground">No position data available</p>;
  }

  let centerRa: number, centerDec: number;
  if (isLunar) {
    centerRa = (sunRa + Math.PI) % (2 * Math.PI);
    centerDec = -sunDec;
  } else {
    centerRa = sunRa;
    centerDec = sunDec;
  }

  const avgDec = (centerDec + moonDec) / 2;
  const dx = (moonRa - centerRa) * Math.cos(avgDec) * (180 / Math.PI) * 60;
  const dy = (moonDec - centerDec) * (180 / Math.PI) * 60;

  const viewExtent = isLunar ? 100 : 60;
  const svgSize = 400;
  const scale = svgSize / (viewExtent * 2);
  const cx = svgSize / 2;
  const cy = svgSize / 2;
  const thresholdArcmin = isLunar ? 90 : 48;

  const moonX = cx + dx * scale;
  const moonY = cy - dy * scale;

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={svgSize} height={svgSize} className="border rounded-lg bg-zinc-950">
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

        {/* Threshold label */}
        <text x={svgSize - 5} y={15} textAnchor="end" fill="rgba(255,255,100,0.5)" fontSize={9}>
          - - - reference ({thresholdArcmin.toFixed(0)}')
        </text>

        {moonRaVel != null && moonDecVel != null && (
          (() => {
            const avgDec2 = moonDec ?? 0;
            const velDx = moonRaVel * Math.cos(avgDec2) * (180 / Math.PI) * 60 * 3;
            const velDy = moonDecVel * (180 / Math.PI) * 60 * 3;
            const arrowEndX = moonX + velDx * scale;
            const arrowEndY = moonY - velDy * scale;
            const arrowLen = Math.sqrt((arrowEndX - moonX) ** 2 + (arrowEndY - moonY) ** 2);
            if (arrowLen < 2) return null;
            const angle = Math.atan2(arrowEndY - moonY, arrowEndX - moonX);
            const headLen = 6;
            const h1x = arrowEndX - headLen * Math.cos(angle - 0.4);
            const h1y = arrowEndY - headLen * Math.sin(angle - 0.4);
            const h2x = arrowEndX - headLen * Math.cos(angle + 0.4);
            const h2y = arrowEndY - headLen * Math.sin(angle + 0.4);
            return (
              <g>
                <line x1={moonX} y1={moonY} x2={arrowEndX} y2={arrowEndY} stroke="rgba(100,200,255,0.7)" strokeWidth={1.5} />
                <polygon points={`${arrowEndX},${arrowEndY} ${h1x},${h1y} ${h2x},${h2y}`} fill="rgba(100,200,255,0.7)" />
              </g>
            );
          })()
        )}

        <line x1={cx} y1={cy} x2={moonX} y2={moonY} stroke="rgba(255,100,100,0.5)" strokeWidth={1} strokeDasharray="3 3" />

        {separationArcmin != null && (
          <text
            x={(cx + moonX) / 2 + 8}
            y={(cy + moonY) / 2 - 8}
            fill="rgba(255,150,150,0.8)"
            fontSize={11}
            fontFamily="monospace"
          >
            {separationArcmin.toFixed(1)}'
          </text>
        )}

        <line x1={10} y1={svgSize - 15} x2={10 + 10 * scale} y2={svgSize - 15} stroke="rgba(255,255,255,0.4)" strokeWidth={2} />
        <text x={10} y={svgSize - 5} fill="rgba(255,255,255,0.4)" fontSize={9}>10 arcmin</text>

        {errorArcmin != null && (
          <text x={svgSize - 5} y={svgSize - 5} textAnchor="end" fill="rgba(255,150,150,0.8)" fontSize={11} fontFamily="monospace">
            error: {errorArcmin.toFixed(1)}'
          </text>
        )}
      </svg>
      <p className="text-xs text-muted-foreground">
        {isLunar ? "Centered on Earth shadow (anti-solar point)" : "Centered on Sun"} · N↑ E←
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

  const moonR = result.moon_apparent_radius_arcmin ?? 15.5;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">
            Eclipse: {result.date.split("T")[0]}
          </h1>
          <div className="flex items-center gap-3 mt-1">
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

      {/* Three diagrams */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Predicted (Catalog)</CardTitle>
          </CardHeader>
          <CardContent>
            {result.expected_separation_arcmin != null ? (
              <PredictedDiagram
                testType={result.test_type}
                expectedSeparationArcmin={result.expected_separation_arcmin}
                approachAngleDeg={result.approach_angle_deg}
                moonRadiusArcmin={moonR}
                sunRadiusArcmin={result.sun_apparent_radius_arcmin}
                umbraRadiusArcmin={result.umbra_radius_arcmin}
                penumbraRadiusArcmin={result.penumbra_radius_arcmin}
              />
            ) : (
              <p className="text-sm text-muted-foreground">No predicted data</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Tychos</CardTitle>
          </CardHeader>
          <CardContent>
            <EclipseDiagram
              testType={result.test_type}
              sunRa={result.sun_ra_rad}
              sunDec={result.sun_dec_rad}
              moonRa={result.moon_ra_rad}
              moonDec={result.moon_dec_rad}
              moonRaVel={result.moon_ra_vel}
              moonDecVel={result.moon_dec_vel}
              separationArcmin={result.min_separation_arcmin}
              errorArcmin={result.tychos_error_arcmin}
              moonRadiusArcmin={moonR}
              sunRadiusArcmin={result.sun_apparent_radius_arcmin}
              umbraRadiusArcmin={result.umbra_radius_arcmin}
              penumbraRadiusArcmin={result.penumbra_radius_arcmin}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">JPL (DE440s)</CardTitle>
          </CardHeader>
          <CardContent>
            <EclipseDiagram
              testType={result.test_type}
              sunRa={result.jpl_sun_ra_rad}
              sunDec={result.jpl_sun_dec_rad}
              moonRa={result.jpl_moon_ra_rad}
              moonDec={result.jpl_moon_dec_rad}
              moonRaVel={result.jpl_moon_ra_vel}
              moonDecVel={result.jpl_moon_dec_vel}
              separationArcmin={result.jpl_separation_arcmin}
              errorArcmin={result.jpl_error_arcmin}
              moonRadiusArcmin={moonR}
              sunRadiusArcmin={result.sun_apparent_radius_arcmin}
              umbraRadiusArcmin={result.umbra_radius_arcmin}
              penumbraRadiusArcmin={result.penumbra_radius_arcmin}
            />
          </CardContent>
        </Card>
      </div>

      {/* Measurements */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Measurements</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-6 text-sm">
            <div className="space-y-2">
              <h4 className="font-medium text-xs text-muted-foreground uppercase">Predicted</h4>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Expected Separation</span>
                <span className="font-mono">{result.expected_separation_arcmin?.toFixed(2) ?? "—"} arcmin</span>
              </div>
              {result.approach_angle_deg != null && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Approach Angle</span>
                  <span className="font-mono">{result.approach_angle_deg.toFixed(1)}°</span>
                </div>
              )}
              {result.pred_gamma != null && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Gamma</span>
                  <span className="font-mono">{result.pred_gamma.toFixed(3)}</span>
                </div>
              )}
            </div>
            <div className="space-y-2">
              <h4 className="font-medium text-xs text-muted-foreground uppercase">Tychos</h4>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Separation</span>
                <span className="font-mono">{result.min_separation_arcmin?.toFixed(2) ?? "—"} arcmin</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Error vs Predicted</span>
                <span className="font-mono">{result.tychos_error_arcmin?.toFixed(2) ?? "—"} arcmin</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Timing Offset</span>
                <span className="font-mono">{result.timing_offset_min != null ? `${result.timing_offset_min > 0 ? "+" : ""}${result.timing_offset_min.toFixed(1)} min` : "—"}</span>
              </div>
              {result.sun_ra_rad != null && (
                <>
                  <div className="flex justify-between font-mono text-xs">
                    <span className="text-muted-foreground">Sun</span>
                    <span>{radToHMS(result.sun_ra_rad)} {radToDMS(result.sun_dec_rad!)}</span>
                  </div>
                  <div className="flex justify-between font-mono text-xs">
                    <span className="text-muted-foreground">Moon</span>
                    <span>{radToHMS(result.moon_ra_rad!)} {radToDMS(result.moon_dec_rad!)}</span>
                  </div>
                </>
              )}
            </div>
            <div className="space-y-2">
              <h4 className="font-medium text-xs text-muted-foreground uppercase">JPL (DE440s)</h4>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Separation</span>
                <span className="font-mono">{result.jpl_separation_arcmin?.toFixed(2) ?? "—"} arcmin</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Error vs Predicted</span>
                <span className="font-mono">{result.jpl_error_arcmin?.toFixed(2) ?? "—"} arcmin</span>
              </div>
              {result.jpl_sun_ra_rad != null && (
                <>
                  <div className="flex justify-between font-mono text-xs">
                    <span className="text-muted-foreground">Sun</span>
                    <span>{radToHMS(result.jpl_sun_ra_rad)} {radToDMS(result.jpl_sun_dec_rad!)}</span>
                  </div>
                  <div className="flex justify-between font-mono text-xs">
                    <span className="text-muted-foreground">Moon</span>
                    <span>{radToHMS(result.jpl_moon_ra_rad!)} {radToDMS(result.jpl_moon_dec_rad!)}</span>
                  </div>
                </>
              )}
            </div>
          </div>
          <div className="mt-4 pt-3 border-t space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Catalog Date</span>
              <span className="font-mono">{result.date}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Julian Day (TT)</span>
              <span className="font-mono">{result.julian_day_tt}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Saros context */}
      {result.saros_num != null && (
        <SarosContext
          sarosNum={result.saros_num}
          sarosPosition={result.saros_position}
          sarosTotal={result.saros_total}
          yearStart={result.saros_year_start}
          yearEnd={result.saros_year_end}
          neighbors={result.saros_neighbors}
          showErrors={true}
          onNeighborClick={(neighborId) => navigate(`/results/${runId}/${neighborId}`)}
          onViewFullSeries={(sarosNum) => navigate(`/results/${runId}?saros=${sarosNum}`)}
        />
      )}
    </div>
  );
}
