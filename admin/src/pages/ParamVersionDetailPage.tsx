import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { format } from "date-fns";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type RunStatus = "queued" | "running" | "done" | "failed";

interface RunRow {
  id: number;
  test_type: string;
  status: RunStatus;
  total_eclipses: number | null;
  detected: number | null;
  created_at: string;
}

interface VersionDetail {
  id: number;
  version_number: number;
  params_md5: string;
  params_json: string;
  created_at: string;
  param_set_name?: string;
  runs: RunRow[];
}

function StatusBadge({ status }: { status: RunStatus }) {
  if (status === "done")
    return (
      <Badge className="bg-green-500/15 text-green-600 border-transparent dark:text-green-400">
        done
      </Badge>
    );
  if (status === "running")
    return (
      <Badge className="bg-yellow-500/15 text-yellow-600 border-transparent dark:text-yellow-400">
        running
      </Badge>
    );
  if (status === "queued") return <Badge variant="secondary">queued</Badge>;
  return <Badge variant="destructive">failed</Badge>;
}

function detectionLabel(detected: number | null, total: number | null): string {
  if (detected === null || total === null) return "—";
  const pct = total === 0 ? 0 : Math.round((detected / total) * 100);
  return `${detected}/${total} (${pct}%)`;
}

function computeSolarStats(runs: RunRow[]) {
  return runs.find((r) => r.test_type === "solar" && r.status === "done") ?? null;
}

function computeLunarStats(runs: RunRow[]) {
  return runs.find((r) => r.test_type === "lunar" && r.status === "done") ?? null;
}

function StatCard({
  title,
  run,
}: {
  title: string;
  run: RunRow | null;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {run && run.detected !== null && run.total_eclipses !== null ? (
          <>
            <p className="text-3xl font-bold text-teal-400">
              {run.total_eclipses === 0
                ? "0%"
                : `${Math.round((run.detected / run.total_eclipses) * 100)}%`}
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              {run.detected}/{run.total_eclipses} detected
            </p>
          </>
        ) : (
          <p className="text-muted-foreground text-sm">No runs yet</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function ParamVersionDetailPage() {
  const { id, versionId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<VersionDetail | null>(null);
  const [paramSetName, setParamSetName] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id || !versionId) return;
    setLoading(true);
    setError(null);

    Promise.all([
      fetch(`/api/params/${id}/versions/${versionId}`).then((r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "Not found" : "Failed to load");
        return r.json() as Promise<VersionDetail>;
      }),
      fetch(`/api/params/${id}`).then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([versionData, paramSetData]) => {
        setData(versionData);
        if (paramSetData?.name) setParamSetName(paramSetData.name);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id, versionId]);

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data) return null;

  const solarRun = computeSolarStats(data.runs);
  const lunarRun = computeLunarStats(data.runs);

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">
            {paramSetName ? `${paramSetName} — ` : ""}Version {data.version_number}
          </h1>
          <p className="text-xs text-muted-foreground mt-1 font-mono">
            MD5: {data.params_md5}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Created {format(new Date(data.created_at), "MMM d, yyyy HH:mm")}
          </p>
        </div>
        <Button variant="outline" onClick={() => navigate(`/parameters/${id}`)}>
          Back to Param Set
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4">
        <StatCard title="Solar Detection" run={solarRun} />
        <StatCard title="Lunar Detection" run={lunarRun} />
      </div>

      {/* Runs */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Runs</h2>
        {data.runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No runs for this version</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Test Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Detection</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.runs.map((run) => (
                <TableRow
                  key={run.id}
                  className={run.status === "done" ? "cursor-pointer" : undefined}
                  onClick={
                    run.status === "done"
                      ? () => navigate(`/results/${run.id}`)
                      : undefined
                  }
                >
                  <TableCell className="capitalize">{run.test_type}</TableCell>
                  <TableCell>
                    <StatusBadge status={run.status} />
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {detectionLabel(run.detected, run.total_eclipses)}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {format(new Date(run.created_at), "MMM d, yyyy HH:mm")}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  );
}
