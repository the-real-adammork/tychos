import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
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
import { CreateJobModal } from "@/components/research/create-job-modal";

interface ResearchJob {
  id: number;
  name: string;
  status: string;
  model: string;
  view_name: string;
  current_iteration: number;
  max_iterations: number;
  updated_at: string | null;
  created_at: string;
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: "bg-green-500/15 text-green-600 border-transparent",
    paused: "bg-yellow-500/15 text-yellow-600 border-transparent",
    pending: "bg-gray-500/15 text-gray-400 border-transparent",
    completed: "bg-blue-500/15 text-blue-600 border-transparent",
  };
  return <Badge className={styles[status] || ""}>{status}</Badge>;
}

function modelShort(model: string): string {
  if (model.includes("opus")) return "opus-4.6";
  if (model.includes("sonnet")) return "sonnet-4.6";
  return model;
}

export default function ResearchPage() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const res = await fetch("/api/research");
      if (res.ok) setJobs(await res.json());
    } catch (err) {
      console.error("Failed to load research jobs:", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleAction(jobId: number, action: string) {
    await fetch(`/api/research/${jobId}/${action}`, { method: "POST" });
    load();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Research Jobs</h1>
        <CreateJobModal onCreated={() => load()} />
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!loading && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Model</TableHead>
              <TableHead>View</TableHead>
              <TableHead>Iterations</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.map((job) => (
              <TableRow
                key={job.id}
                className="cursor-pointer"
                onClick={() => navigate(`/research/${job.id}`)}
              >
                <TableCell className="font-medium">{job.name}</TableCell>
                <TableCell><StatusBadge status={job.status} /></TableCell>
                <TableCell className="text-muted-foreground">{modelShort(job.model)}</TableCell>
                <TableCell className="text-muted-foreground text-xs font-mono">{job.view_name}</TableCell>
                <TableCell>{job.current_iteration}/{job.max_iterations}</TableCell>
                <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                  {job.status === "pending" && (
                    <Button size="sm" variant="outline" onClick={() => handleAction(job.id, "start")}>Start</Button>
                  )}
                  {job.status === "active" && (
                    <Button size="sm" variant="outline" onClick={() => handleAction(job.id, "pause")}>Pause</Button>
                  )}
                  {job.status === "paused" && (
                    <Button size="sm" variant="outline" onClick={() => handleAction(job.id, "resume")}>Resume</Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {jobs.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                  No research jobs yet
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
