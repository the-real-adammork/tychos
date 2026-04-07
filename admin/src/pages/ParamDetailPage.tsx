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
  dataset_slug: string;
  dataset_name: string;
  status: RunStatus;
  total_eclipses: number | null;
  detected: number | null;
  created_at: string;
}

interface VersionRow {
  id: number;
  version_number: number;
  parent_version_id: number | null;
  params_md5: string;
  notes: string | null;
  created_at: string;
}

interface StatResult {
  overall_pass: number;
  total_eclipses: number;
  version_number: number;
}

interface ParamDetail {
  id: number;
  name: string;
  description: string | null;
  owner_id: number;
  owner_name: string;
  created_at: string;
  solar_eclipse_stats: StatResult | null;
  lunar_eclipse_stats: StatResult | null;
  latest_version_runs: RunRow[];
  versions: VersionRow[];
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

function StatCard({
  title,
  stats,
}: {
  title: string;
  stats: StatResult | null;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {stats ? (
          <>
            <p className="text-3xl font-bold text-teal-400">
              {stats.total_eclipses === 0
                ? "0%"
                : `${Math.round((stats.overall_pass / stats.total_eclipses) * 100)}%`}
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              {stats.overall_pass}/{stats.total_eclipses} pass
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              <span className="font-medium">Version:</span> v{stats.version_number}
            </p>
          </>
        ) : (
          <p className="text-muted-foreground text-sm">No runs yet</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function ParamDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<ParamDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [savingName, setSavingName] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    fetch(`/api/params/${id}`)
      .then((r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "Not found" : "Failed to load");
        return r.json();
      })
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleDelete() {
    if (!id || !data) return;
    if (!confirm(`Delete "${data.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      const res = await fetch(`/api/params/${id}`, { method: "DELETE" });
      if (res.ok) {
        navigate("/parameters");
      } else {
        const body = await res.json();
        alert(body.detail ?? "Delete failed");
      }
    } catch {
      alert("Network error");
    } finally {
      setDeleting(false);
    }
  }

  async function handleDownload() {
    if (!id || !data || data.versions.length === 0) return;
    const latestVersion = data.versions[0]; // newest first
    const res = await fetch(`/api/params/${id}/versions/${latestVersion.id}`);
    if (!res.ok) return;
    const ver = await res.json();
    const payload = {
      name: data.name,
      description: data.description,
      params_json: ver.params_json,
      notes: ver.notes,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${data.name}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleFork() {
    if (!id || !data) return;
    try {
      const res = await fetch(`/api/params/${id}/fork`, { method: "POST" });
      if (res.ok) {
        const forked = await res.json();
        navigate(`/parameters/${forked.id}`);
      } else {
        const body = await res.json();
        alert(body.detail ?? "Fork failed");
      }
    } catch {
      alert("Network error");
    }
  }

  async function handleSaveName() {
    if (!id || !data || !nameValue.trim()) return;
    setSavingName(true);
    try {
      const res = await fetch(`/api/params/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameValue.trim() }),
      });
      if (res.ok) {
        setData({ ...data, name: nameValue.trim() });
        setEditingName(false);
      }
    } finally {
      setSavingName(false);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data) return null;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          {editingName ? (
            <div className="flex items-center gap-2">
              <input
                className="text-2xl font-bold bg-background border border-input rounded px-2 py-0.5"
                value={nameValue}
                onChange={(e) => setNameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSaveName();
                  if (e.key === "Escape") { setEditingName(false); setNameValue(data.name); }
                }}
                autoFocus
              />
              <Button size="sm" onClick={handleSaveName} disabled={savingName || !nameValue.trim()}>
                {savingName ? "Saving…" : "Save"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => { setEditingName(false); setNameValue(data.name); }}>
                Cancel
              </Button>
            </div>
          ) : (
            <h1
              className="text-2xl font-bold cursor-pointer hover:text-muted-foreground transition-colors"
              onClick={() => { setNameValue(data.name); setEditingName(true); }}
              title="Click to rename"
            >
              {data.name}
            </h1>
          )}
          {data.description && (
            <p className="text-sm text-muted-foreground mt-1">{data.description}</p>
          )}
          <p className="text-xs text-muted-foreground mt-0.5">
            Owner: {data.owner_name} &middot; Created{" "}
            {new Date(data.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="outline" onClick={handleDownload}>
            Download JSON
          </Button>
          <Button variant="outline" onClick={handleFork}>
            Fork
          </Button>
          <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
            {deleting ? "Deleting…" : "Delete"}
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4">
        <StatCard title="Best Solar Detection" stats={data.solar_eclipse_stats} />
        <StatCard title="Best Lunar Detection" stats={data.lunar_eclipse_stats} />
      </div>

      {/* Latest Runs */}
      <section>
        <h2 className="text-lg font-semibold mb-3">
          Latest Runs{data.versions.length > 0 && ` — v${data.versions[0].version_number}`}
        </h2>
        {data.latest_version_runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No runs yet</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Dataset</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Detection</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.latest_version_runs.map((run) => (
                <TableRow
                  key={run.id}
                  className={run.status === "done" ? "cursor-pointer" : undefined}
                  onClick={
                    run.status === "done"
                      ? () => navigate(`/results/${run.id}`)
                      : undefined
                  }
                >
                  <TableCell className="capitalize">{run.dataset_name}</TableCell>
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

      {/* Version History */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Version History</h2>
        {data.versions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No versions</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Version</TableHead>
                <TableHead>Based On</TableHead>
                <TableHead>Notes</TableHead>
                <TableHead>MD5</TableHead>
                <TableHead>Created</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.versions.map((v) => {
                const parent = v.parent_version_id
                  ? data.versions.find((p) => p.id === v.parent_version_id)
                  : null;
                return (
                  <TableRow
                    key={v.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/parameters/${id}/versions/${v.id}`)}
                  >
                    <TableCell className="font-medium">v{v.version_number}</TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {parent ? `v${parent.version_number}` : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-48 truncate">
                      {v.notes || "—"}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {v.params_md5.slice(0, 12)}…
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {format(new Date(v.created_at), "MMM d, yyyy HH:mm")}
                    </TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/parameters/${id}/versions/${v.id}`);
                        }}
                      >
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  );
}
