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
  test_type: string;
  status: string;
  total_eclipses: number | null;
  detected: number | null;
}

interface ParamSetRow {
  id: number;
  name: string;
  owner_name: string;
  created_at: string;
  latest_runs: LatestRun[];
}

function detectionCell(runs: LatestRun[], testType: "solar" | "lunar"): string {
  const run = runs.find((r) => r.test_type === testType && r.status === "done");
  if (!run || run.detected === null || run.total_eclipses === null) return "—";
  const pct =
    run.total_eclipses === 0
      ? 0
      : Math.round((run.detected / run.total_eclipses) * 100);
  return `${run.detected}/${run.total_eclipses} (${pct}%)`;
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
              <TableHead>Solar Detection</TableHead>
              <TableHead>Lunar Detection</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paramSets.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No parameter sets yet
                </TableCell>
              </TableRow>
            )}
            {paramSets.map((ps) => (
              <TableRow
                key={ps.id}
                className="cursor-pointer"
                onClick={() => navigate(`/parameters/${ps.id}`)}
              >
                <TableCell className="font-medium">{ps.name}</TableCell>
                <TableCell>{ps.owner_name}</TableCell>
                <TableCell className="tabular-nums">
                  {detectionCell(ps.latest_runs, "solar")}
                </TableCell>
                <TableCell className="tabular-nums">
                  {detectionCell(ps.latest_runs, "lunar")}
                </TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {new Date(ps.created_at).toLocaleDateString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
