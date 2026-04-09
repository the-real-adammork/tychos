import * as React from "react";
import { useNavigate } from "react-router-dom";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ParamForm } from "./param-form";

interface LatestRun {
  dataset_slug: string;
  status: string;
  total_eclipses: number | null;
  mean_tychos_error: number | null;
  mean_sun_diff: number | null;
  mean_moon_diff: number | null;
  mean_timing_offset: number | null;
}

interface ParamSetRow {
  id: number;
  name: string;
  owner_name: string;
  created_at: string;
  latest_runs: LatestRun[];
}

function findRun(runs: LatestRun[], datasetSlug: string): LatestRun | undefined {
  return runs.find((r) => r.dataset_slug === datasetSlug && r.status === "done");
}

function fmtArc(val: number | null | undefined): string {
  return val != null ? `${val.toFixed(1)}'` : "—";
}

function fmtMin(val: number | null | undefined): string {
  return val != null ? `${val.toFixed(1)} min` : "—";
}

export function ParamList() {
  const navigate = useNavigate();
  const [paramSets, setParamSets] = React.useState<ParamSetRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/params");
      if (!res.ok) throw new Error("Failed to load");
      const data: ParamSetRow[] = await res.json();
      setParamSets(data);
    } catch {
      setError("Failed to load parameter sets");
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    load();
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <ParamForm onCreated={(id) => navigate(`/parameters/${id}`)} />
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {!loading && !error && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Owner</TableHead>
              <TableHead>Sun Diff</TableHead>
              <TableHead>Moon Diff</TableHead>
              <TableHead>Timing</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paramSets.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  No parameter sets yet
                </TableCell>
              </TableRow>
            )}
            {paramSets.map((ps) => {
              const solar = findRun(ps.latest_runs, "solar_eclipse");
              const lunar = findRun(ps.latest_runs, "lunar_eclipse");
              return (
                <TableRow
                  key={ps.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/parameters/${ps.id}`)}
                >
                  <TableCell className="font-medium">{ps.name}</TableCell>
                  <TableCell>{ps.owner_name}</TableCell>
                  <TableCell className="tabular-nums">
                    {fmtArc(solar?.mean_sun_diff ?? lunar?.mean_sun_diff)}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {fmtArc(solar?.mean_moon_diff ?? lunar?.mean_moon_diff)}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {fmtMin(solar?.mean_timing_offset ?? lunar?.mean_timing_offset)}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {new Date(ps.created_at).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
