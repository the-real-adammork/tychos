import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PredictedDiagram } from "@/components/eclipse/predicted-diagram";
import { SarosContext, type SarosNeighbor } from "@/components/eclipse/saros-context";

interface EclipseRecord {
  id: number;
  catalog_number: string;
  julian_day_tt: number;
  date: string;
  delta_t_s: number | null;
  luna_num: number | null;
  saros_num: number | null;
  type_raw: string;
  type: string;
  gamma: number | null;
  magnitude: number;
  // Solar
  qle: string | null;
  lat: number | null;
  lon: number | null;
  sun_alt_deg: number | null;
  path_width_km: number | null;
  duration_s: number | null;
  // Lunar
  qse: string | null;
  pen_mag: number | null;
  um_mag: number | null;
  pen_duration_min: number | null;
  par_duration_min: number | null;
  total_duration_min: number | null;
  zenith_lat: number | null;
  zenith_lon: number | null;
  // Predicted
  expected_separation_arcmin: number | null;
  moon_apparent_radius_arcmin: number | null;
  sun_apparent_radius_arcmin: number | null;
  umbra_radius_arcmin: number | null;
  penumbra_radius_arcmin: number | null;
  approach_angle_deg: number | null;
  // Saros context
  saros_total: number | null;
  saros_position: number | null;
  saros_year_start: string | null;
  saros_year_end: string | null;
  saros_neighbors: SarosNeighbor[];
}

interface EclipseDetailResponse {
  dataset: { name: string; slug: string; event_type: string };
  test_type: string;
  eclipse: EclipseRecord;
}

function fmt(val: number | string | null | undefined, digits = 4): string {
  if (val == null || val === "") return "—";
  if (typeof val === "number") return val.toFixed(digits);
  return String(val);
}

function fmtCoord(val: number | null, pos: string, neg: string): string {
  if (val == null) return "—";
  return `${Math.abs(val)}${val >= 0 ? pos : neg}`;
}

function fmtDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}

export default function EclipseCatalogDetailPage() {
  const { slug, eclipseId } = useParams<{ slug: string; eclipseId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<EclipseDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug || !eclipseId) return;
    setLoading(true);
    setError(null);
    fetch(`/api/datasets/${slug}/${eclipseId}`)
      .then((r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "Eclipse not found" : "Failed to load");
        return r.json() as Promise<EclipseDetailResponse>;
      })
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [slug, eclipseId]);

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data) return null;

  const ecl = data.eclipse;
  const isLunar = data.test_type === "lunar";
  const dateStr = ecl.date.split("T")[0];

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">
            {isLunar ? "Lunar" : "Solar"} Eclipse: {dateStr}
          </h1>
          <div className="flex items-center gap-3 mt-1">
            <Badge variant="secondary" className="capitalize">{ecl.type}</Badge>
            <span className="text-sm text-muted-foreground font-mono">#{ecl.catalog_number}</span>
            <span className="text-sm text-muted-foreground">{data.dataset.name}</span>
          </div>
        </div>
        <Button variant="outline" onClick={() => navigate(`/datasets/${slug}`)}>
          Back to Catalog
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Predicted diagram */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Predicted Geometry (Catalog)</CardTitle>
          </CardHeader>
          <CardContent>
            {ecl.expected_separation_arcmin != null ? (
              <PredictedDiagram
                testType={data.test_type}
                expectedSeparationArcmin={ecl.expected_separation_arcmin}
                approachAngleDeg={ecl.approach_angle_deg}
                moonRadiusArcmin={ecl.moon_apparent_radius_arcmin ?? 15.5}
                sunRadiusArcmin={ecl.sun_apparent_radius_arcmin}
                umbraRadiusArcmin={ecl.umbra_radius_arcmin}
                penumbraRadiusArcmin={ecl.penumbra_radius_arcmin}
              />
            ) : (
              <p className="text-sm text-muted-foreground">No predicted geometry available</p>
            )}
          </CardContent>
        </Card>

        {/* Catalog data */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Catalog Data</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <h4 className="text-xs font-medium text-muted-foreground uppercase mb-2">Identification</h4>
              <Field label="Date (TT)" value={ecl.date} />
              <Field label="Julian Day (TT)" value={fmt(ecl.julian_day_tt, 6)} />
              <Field label="Catalog #" value={ecl.catalog_number} />
              <Field label="Saros" value={fmt(ecl.saros_num, 0)} />
              <Field label="Lunation" value={fmt(ecl.luna_num, 0)} />
              <Field label="ΔT (s)" value={fmt(ecl.delta_t_s, 0)} />
              <Field label="Type code" value={ecl.type_raw} />
            </div>

            <div className="space-y-1">
              <h4 className="text-xs font-medium text-muted-foreground uppercase mb-2">Geometry</h4>
              <Field label="Gamma" value={fmt(ecl.gamma)} />
              <Field label="Magnitude" value={fmt(ecl.magnitude)} />
              {isLunar ? (
                <>
                  <Field label="Penumbral magnitude" value={fmt(ecl.pen_mag)} />
                  <Field label="Umbral magnitude" value={fmt(ecl.um_mag)} />
                </>
              ) : null}
              {ecl.expected_separation_arcmin != null && (
                <Field label="Expected separation" value={`${ecl.expected_separation_arcmin.toFixed(2)}'`} />
              )}
              {ecl.moon_apparent_radius_arcmin != null && (
                <Field label="Moon radius" value={`${ecl.moon_apparent_radius_arcmin.toFixed(2)}'`} />
              )}
              {!isLunar && ecl.sun_apparent_radius_arcmin != null && (
                <Field label="Sun radius" value={`${ecl.sun_apparent_radius_arcmin.toFixed(2)}'`} />
              )}
              {isLunar && ecl.umbra_radius_arcmin != null && (
                <Field label="Umbra radius" value={`${ecl.umbra_radius_arcmin.toFixed(2)}'`} />
              )}
              {isLunar && ecl.penumbra_radius_arcmin != null && (
                <Field label="Penumbra radius" value={`${ecl.penumbra_radius_arcmin.toFixed(2)}'`} />
              )}
              {ecl.approach_angle_deg != null && (
                <Field label="Approach angle" value={`${ecl.approach_angle_deg.toFixed(1)}°`} />
              )}
            </div>

            {!isLunar && (
              <div className="space-y-1">
                <h4 className="text-xs font-medium text-muted-foreground uppercase mb-2">Greatest Eclipse</h4>
                <Field label="Latitude" value={fmtCoord(ecl.lat, "N", "S")} />
                <Field label="Longitude" value={fmtCoord(ecl.lon, "E", "W")} />
                <Field label="Sun altitude" value={ecl.sun_alt_deg != null ? `${ecl.sun_alt_deg}°` : "—"} />
                <Field label="Path width" value={ecl.path_width_km != null ? `${ecl.path_width_km} km` : "—"} />
                <Field label="Max duration" value={fmtDuration(ecl.duration_s)} />
                <Field label="QLE" value={ecl.qle ?? "—"} />
              </div>
            )}

            {isLunar && (
              <div className="space-y-1">
                <h4 className="text-xs font-medium text-muted-foreground uppercase mb-2">Sub-zenith / Durations</h4>
                <Field label="Zenith latitude" value={fmtCoord(ecl.zenith_lat, "N", "S")} />
                <Field label="Zenith longitude" value={fmtCoord(ecl.zenith_lon, "E", "W")} />
                <Field label="Penumbral duration" value={ecl.pen_duration_min != null ? `${ecl.pen_duration_min.toFixed(1)} min` : "—"} />
                <Field label="Partial duration" value={ecl.par_duration_min != null ? `${ecl.par_duration_min.toFixed(1)} min` : "—"} />
                <Field label="Total duration" value={ecl.total_duration_min != null ? `${ecl.total_duration_min.toFixed(1)} min` : "—"} />
                <Field label="QSE" value={ecl.qse ?? "—"} />
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Saros context */}
      {ecl.saros_num != null && (
        <SarosContext
          sarosNum={ecl.saros_num}
          sarosPosition={ecl.saros_position}
          sarosTotal={ecl.saros_total}
          yearStart={ecl.saros_year_start}
          yearEnd={ecl.saros_year_end}
          neighbors={ecl.saros_neighbors}
          showErrors={false}
          onNeighborClick={(neighborId) => navigate(`/datasets/${slug}/${neighborId}`)}
          onViewFullSeries={(sarosNum) => navigate(`/datasets/${slug}?saros=${sarosNum}`)}
        />
      )}
    </div>
  );
}
