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

interface Ancestor {
  id: number;
  version_number: number;
  parent_version_id: number | null;
  params_md5: string;
  notes: string | null;
  created_at: string;
  solar_detected: number | null;
  solar_total: number | null;
  lunar_detected: number | null;
  lunar_total: number | null;
}

interface VersionDetail {
  id: number;
  version_number: number;
  parent_version_id: number | null;
  params_md5: string;
  params_json: string;
  notes: string | null;
  created_at: string;
  runs: RunRow[];
  ancestors: Ancestor[];
}

function StatusBadge({ status }: { status: RunStatus }) {
  if (status === "done")
    return <Badge className="bg-green-500/15 text-green-600 border-transparent dark:text-green-400">done</Badge>;
  if (status === "running")
    return <Badge className="bg-yellow-500/15 text-yellow-600 border-transparent dark:text-yellow-400">running</Badge>;
  if (status === "queued") return <Badge variant="secondary">queued</Badge>;
  return <Badge variant="destructive">failed</Badge>;
}

function detectionLabel(detected: number | null, total: number | null): string {
  if (detected === null || total === null) return "—";
  const pct = total === 0 ? 0 : Math.round((detected / total) * 100);
  return `${detected}/${total} (${pct}%)`;
}

function StatCard({ title, run, notes }: { title: string; run: RunRow | null; notes?: string | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {run && run.detected !== null && run.total_eclipses !== null ? (
          <>
            <p className="text-3xl font-bold text-teal-400">
              {run.total_eclipses === 0 ? "0%" : `${Math.round((run.detected / run.total_eclipses) * 100)}%`}
            </p>
            <p className="text-sm text-muted-foreground mt-1">{run.detected}/{run.total_eclipses} detected</p>
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
  const [paramSetName, setParamSetName] = useState("");
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

  if (loading) return <p className="text-sm text-muted-foreground">Loading...</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data) return null;

  const solarRun = data.runs.find((r) => r.test_type === "solar" && r.status === "done") ?? null;
  const lunarRun = data.runs.find((r) => r.test_type === "lunar" && r.status === "done") ?? null;

  const [editingNotes, setEditingNotes] = useState(false);
  const [notesValue, setNotesValue] = useState(data.notes || "");
  const [savingNotes, setSavingNotes] = useState(false);

  async function handleSaveNotes() {
    setSavingNotes(true);
    try {
      const res = await fetch(`/api/params/${id}/versions/${versionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notesValue || null }),
      });
      if (res.ok) {
        setData({ ...data, notes: notesValue || null });
        setEditingNotes(false);
      }
    } finally {
      setSavingNotes(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header + Notes */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <h1 className="text-2xl font-bold">
            {paramSetName ? `${paramSetName} — ` : ""}Version {data.version_number}
          </h1>
          <p className="text-xs text-muted-foreground mt-1 font-mono">MD5: {data.params_md5}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Created {format(new Date(data.created_at), "MMM d, yyyy HH:mm")}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2 max-w-sm">
          {editingNotes ? (
            <div className="w-full flex flex-col gap-1">
              <textarea
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                rows={2}
                value={notesValue}
                onChange={(e) => setNotesValue(e.target.value)}
              />
              <div className="flex gap-1 justify-end">
                <Button size="sm" variant="outline" onClick={() => { setEditingNotes(false); setNotesValue(data.notes || ""); }}>
                  Cancel
                </Button>
                <Button size="sm" onClick={handleSaveNotes} disabled={savingNotes}>
                  {savingNotes ? "Saving..." : "Save"}
                </Button>
              </div>
            </div>
          ) : (
            <div
              className="bg-muted/50 rounded-md px-3 py-2 text-sm text-muted-foreground cursor-pointer hover:bg-muted/80 w-full min-h-[2.5rem]"
              onClick={() => setEditingNotes(true)}
              title="Click to edit notes"
            >
              {data.notes || "Add notes..."}
            </div>
          )}
          <Button variant="outline" onClick={() => navigate(`/parameters/${id}`)}>
            Back to Param Set
          </Button>
        </div>
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
                  onClick={run.status === "done" ? () => navigate(`/results/${run.id}`) : undefined}
                >
                  <TableCell className="capitalize">{run.test_type}</TableCell>
                  <TableCell><StatusBadge status={run.status} /></TableCell>
                  <TableCell className="tabular-nums">{detectionLabel(run.detected, run.total_eclipses)}</TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {format(new Date(run.created_at), "MMM d, yyyy HH:mm")}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      {/* Ancestors */}
      {data.ancestors.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-3">Ancestor Versions</h2>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Version</TableHead>
                <TableHead>Based On</TableHead>
                <TableHead>Solar</TableHead>
                <TableHead>Lunar</TableHead>
                <TableHead>Notes</TableHead>
                <TableHead>Created</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.ancestors.map((anc) => (
                <TableRow key={anc.id}>
                  <TableCell className="font-medium">v{anc.version_number}</TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {anc.parent_version_id
                      ? `v${data.ancestors.find((a) => a.id === anc.parent_version_id)?.version_number ?? "?"}`
                      : "—"}
                  </TableCell>
                  <TableCell className="tabular-nums text-xs">
                    {detectionLabel(anc.solar_detected, anc.solar_total)}
                  </TableCell>
                  <TableCell className="tabular-nums text-xs">
                    {detectionLabel(anc.lunar_detected, anc.lunar_total)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-48 truncate">
                    {anc.notes || "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {format(new Date(anc.created_at), "MMM d, yyyy HH:mm")}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button size="sm" variant="outline" onClick={() => navigate(`/parameters/${id}/versions/${anc.id}`)}>
                        View
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => navigate(`/parameters/${id}/edit?from=${anc.id}`)}>
                        Edit
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      )}
    </div>
  );
}
