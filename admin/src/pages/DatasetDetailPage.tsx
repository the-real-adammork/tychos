import { useEffect, useState } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";

interface DatasetMeta {
  name: string;
  description: string | null;
  source_url: string | null;
  event_type: string;
  record_count: number;
}

interface DatasetResponse {
  dataset: DatasetMeta;
  eclipses: Record<string, unknown>[];
  total: number;
  page: number;
  page_size: number;
  event_type: string;
}

const PAGE_SIZE = 50;

function formatDate(dateStr: string) {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatDuration(seconds: number | null) {
  if (seconds == null) return "\u2014";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

function formatMinutes(mins: number | null) {
  if (mins == null) return "\u2014";
  return `${mins.toFixed(1)}`;
}

function formatCoord(val: number | null, pos: string, neg: string) {
  if (val == null) return "\u2014";
  return `${Math.abs(val)}${val >= 0 ? pos : neg}`;
}

function cell(val: unknown, fmt?: (v: number) => string) {
  if (val == null || val === "") return "\u2014";
  if (fmt && typeof val === "number") return fmt(val);
  return String(val);
}

export default function DatasetDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<DatasetResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const page = parseInt(searchParams.get("page") || "1", 10);
  const catalogFilter = searchParams.get("catalog") || "all";

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (catalogFilter !== "all") params.set("catalog_type", catalogFilter);

    fetch(`/api/datasets/${slug}?${params}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [slug, page, catalogFilter]);

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  const catalogTypes =
    data?.event_type === "solar_eclipse"
      ? ["all", "total", "annular", "partial", "hybrid"]
      : ["all", "total", "partial", "penumbral"];

  function setPage(p: number) {
    const next = new URLSearchParams(searchParams);
    next.set("page", String(p));
    setSearchParams(next);
  }

  function setCatalog(v: string) {
    const next = new URLSearchParams(searchParams);
    next.set("catalog", v);
    next.set("page", "1");
    setSearchParams(next);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold">{data?.dataset.name ?? "Dataset"}</h1>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            {data?.dataset.description && (
              <span>{data.dataset.description}</span>
            )}
            {data?.dataset.source_url && (
              <a
                href={data.dataset.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-500 hover:underline"
              >
                Source
              </a>
            )}
          </div>
        </div>
        {data && (
          <span className="text-sm text-muted-foreground">
            {data.total} eclipses
          </span>
        )}
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Type:</span>
          <Select value={catalogFilter} onValueChange={(v) => { if (v) setCatalog(v); }}>
            <SelectTrigger className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {catalogTypes.map((t) => (
                <SelectItem key={t} value={t}>
                  {t === "all" ? "All" : t.charAt(0).toUpperCase() + t.slice(1)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : !data || data.eclipses.length === 0 ? (
        <p className="text-sm text-muted-foreground">No eclipse data found.</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            {data.event_type === "solar_eclipse" ? (
              <SolarTable eclipses={data.eclipses} slug={slug ?? ""} />
            ) : (
              <LunarTable eclipses={data.eclipses} slug={slug ?? ""} />
            )}
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function SolarTable({ eclipses, slug }: { eclipses: Record<string, unknown>[]; slug: string }) {
  const navigate = useNavigate();
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Cat #</TableHead>
          <TableHead>Date</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Saros</TableHead>
          <TableHead>Luna #</TableHead>
          <TableHead>Gamma</TableHead>
          <TableHead>Mag.</TableHead>
          <TableHead>QLE</TableHead>
          <TableHead>Lat</TableHead>
          <TableHead>Lon</TableHead>
          <TableHead>Alt</TableHead>
          <TableHead>Width (km)</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead>Delta T (s)</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {eclipses.map((ecl) => (
          <TableRow
            key={ecl.id as number}
            className="cursor-pointer"
            onClick={() => navigate(`/datasets/${slug}/${ecl.id}`)}
          >
            <TableCell className="font-mono text-xs">{cell(ecl.catalog_number)}</TableCell>
            <TableCell className="whitespace-nowrap">{formatDate(ecl.date as string)}</TableCell>
            <TableCell>
              <Badge variant="secondary">{cell(ecl.type)}</Badge>
            </TableCell>
            <TableCell className="tabular-nums">{cell(ecl.saros_num)}</TableCell>
            <TableCell className="tabular-nums">{cell(ecl.luna_num)}</TableCell>
            <TableCell className="tabular-nums">{cell(ecl.gamma, (v) => v.toFixed(4))}</TableCell>
            <TableCell className="tabular-nums">{cell(ecl.magnitude, (v) => v.toFixed(4))}</TableCell>
            <TableCell className="font-mono text-xs">{cell(ecl.qle)}</TableCell>
            <TableCell className="tabular-nums">{formatCoord(ecl.lat as number | null, "N", "S")}</TableCell>
            <TableCell className="tabular-nums">{formatCoord(ecl.lon as number | null, "E", "W")}</TableCell>
            <TableCell className="tabular-nums">{cell(ecl.sun_alt_deg)}{ecl.sun_alt_deg != null ? "\u00b0" : ""}</TableCell>
            <TableCell className="tabular-nums">{cell(ecl.path_width_km)}</TableCell>
            <TableCell className="tabular-nums whitespace-nowrap">{formatDuration(ecl.duration_s as number | null)}</TableCell>
            <TableCell className="tabular-nums">{cell(ecl.delta_t_s)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function LunarTable({ eclipses, slug }: { eclipses: Record<string, unknown>[]; slug: string }) {
  const navigate = useNavigate();
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Cat #</TableHead>
          <TableHead>Date</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Saros</TableHead>
          <TableHead>Luna #</TableHead>
          <TableHead>Gamma</TableHead>
          <TableHead>Pen. Mag.</TableHead>
          <TableHead>Um. Mag.</TableHead>
          <TableHead>QSE</TableHead>
          <TableHead>Pen. (min)</TableHead>
          <TableHead>Par. (min)</TableHead>
          <TableHead>Total (min)</TableHead>
          <TableHead>Zenith Lat</TableHead>
          <TableHead>Zenith Lon</TableHead>
          <TableHead>Delta T (s)</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {eclipses.map((ecl) => (
          <TableRow
            key={ecl.id as number}
            className="cursor-pointer"
            onClick={() => navigate(`/datasets/${slug}/${ecl.id}`)}
          >
            <TableCell className="font-mono text-xs">{cell(ecl.catalog_number)}</TableCell>
            <TableCell className="whitespace-nowrap">{formatDate(ecl.date as string)}</TableCell>
            <TableCell>
              <Badge variant="secondary">{cell(ecl.type)}</Badge>
            </TableCell>
            <TableCell className="tabular-nums">{cell(ecl.saros_num)}</TableCell>
            <TableCell className="tabular-nums">{cell(ecl.luna_num)}</TableCell>
            <TableCell className="tabular-nums">{cell(ecl.gamma, (v) => v.toFixed(4))}</TableCell>
            <TableCell className="tabular-nums">{cell(ecl.pen_mag, (v) => v.toFixed(4))}</TableCell>
            <TableCell className="tabular-nums">{cell(ecl.um_mag, (v) => v.toFixed(4))}</TableCell>
            <TableCell className="font-mono text-xs">{cell(ecl.qse)}</TableCell>
            <TableCell className="tabular-nums">{formatMinutes(ecl.pen_duration_min as number | null)}</TableCell>
            <TableCell className="tabular-nums">{formatMinutes(ecl.par_duration_min as number | null)}</TableCell>
            <TableCell className="tabular-nums">{formatMinutes(ecl.total_duration_min as number | null)}</TableCell>
            <TableCell className="tabular-nums">{formatCoord(ecl.zenith_lat as number | null, "N", "S")}</TableCell>
            <TableCell className="tabular-nums">{formatCoord(ecl.zenith_lon as number | null, "E", "W")}</TableCell>
            <TableCell className="tabular-nums">{cell(ecl.delta_t_s)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
