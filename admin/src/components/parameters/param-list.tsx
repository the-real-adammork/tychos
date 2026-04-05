import * as React from "react";
import { Link } from "react-router-dom";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ParamForm } from "./param-form";

interface RunSummary {
  testType: string;
  totalEclipses: number | null;
  detected: number | null;
}

interface ParamSet {
  id: number;
  name: string;
  description: string | null;
  createdAt: string;
  owner: { id: number; name: string };
  forkedFrom: { id: number; name: string } | null;
  runs: RunSummary[];
}

function detectionSummary(runs: RunSummary[], type: "solar" | "lunar"): string {
  const doneRuns = runs.filter(
    (r) => r.testType === type && r.detected !== null && r.totalEclipses !== null
  );
  if (doneRuns.length === 0) return "—";
  const last = doneRuns[doneRuns.length - 1];
  return `${last.detected}/${last.totalEclipses}`;
}

export function ParamList() {
  const [paramSets, setParamSets] = React.useState<ParamSet[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/params");
      if (!res.ok) throw new Error("Failed to load");
      const data: any[] = await res.json();
      setParamSets(data.map((ps) => ({
        id: ps.id,
        name: ps.name,
        description: ps.description,
        createdAt: ps.created_at,
        owner: { id: ps.owner_id, name: ps.owner_name },
        forkedFrom: ps.forked_from_name ? { id: ps.forked_from_id, name: ps.forked_from_name } : null,
        runs: (ps.latest_runs || []).map((r: any) => ({
          testType: r.test_type,
          totalEclipses: r.total_eclipses,
          detected: r.detected,
        })),
      })));
    } catch {
      setError("Failed to load parameter sets");
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    load();
  }, []);

  async function handleFork(id: number) {
    const res = await fetch(`/api/params/${id}/fork`, { method: "POST" });
    if (res.ok) load();
  }

  async function handleDelete(id: number) {
    if (!confirm("Delete this parameter set?")) return;
    const res = await fetch(`/api/params/${id}`, { method: "DELETE" });
    if (res.ok) load();
  }

  async function handleRun(paramSetId: number, testType: "solar" | "lunar") {
    await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paramSetId, testType }),
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <ParamForm onCreated={load} />
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {!loading && !error && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Owner</TableHead>
              <TableHead>Forked From</TableHead>
              <TableHead>Solar Detection</TableHead>
              <TableHead>Lunar Detection</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paramSets.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground">
                  No parameter sets yet
                </TableCell>
              </TableRow>
            )}
            {paramSets.map((ps) => (
              <TableRow key={ps.id}>
                <TableCell className="font-medium">{ps.name}</TableCell>
                <TableCell>{ps.owner.name}</TableCell>
                <TableCell>{ps.forkedFrom?.name ?? "—"}</TableCell>
                <TableCell className="tabular-nums">
                  {detectionSummary(ps.runs, "solar")}
                </TableCell>
                <TableCell className="tabular-nums">
                  {detectionSummary(ps.runs, "lunar")}
                </TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {new Date(ps.createdAt).toLocaleDateString()}
                </TableCell>
                <TableCell>
                  <div className="flex gap-1 flex-wrap">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleFork(ps.id)}
                    >
                      Fork
                    </Button>
                    <Link
                      to={`/parameters/${ps.id}`}
                      className={buttonVariants({ size: "sm", variant: "outline" })}
                    >
                      Edit
                    </Link>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleRun(ps.id, "solar")}
                    >
                      Run Solar
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleRun(ps.id, "lunar")}
                    >
                      Run Lunar
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => handleDelete(ps.id)}
                    >
                      Delete
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
