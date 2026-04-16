import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Send } from "lucide-react";
import { ObjectiveChart } from "@/components/research/objective-chart";
import { Timeline } from "@/components/research/timeline";

interface ResearchJob {
  id: number;
  name: string;
  status: string;
  model: string;
  view_name: string;
  allowlist: string[];
  date_start: string | null;
  date_end: string | null;
  current_iteration: number;
  max_iterations: number;
  max_wall_clock_seconds: number;
  no_improvement_plateau: number;
  iterations_since_checkpoint: number;
  created_at: string;
}

interface Iteration {
  id: number;
  kind: string;
  objective: number | null;
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

export default function ResearchJobDetailPage() {
  const { id } = useParams();
  const jobId = Number(id);
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [iterations, setIterations] = useState<Iteration[]>([]);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);

  async function loadJob() {
    const res = await fetch(`/api/research/${jobId}`);
    if (res.ok) setJob(await res.json());
  }

  async function loadIterations() {
    const res = await fetch(`/api/research/${jobId}/iterations`);
    if (res.ok) setIterations(await res.json());
  }

  useEffect(() => {
    loadJob();
    loadIterations();
    const interval = setInterval(() => {
      loadJob();
      loadIterations();
    }, 5000);
    return () => clearInterval(interval);
  }, [jobId]);

  async function handleAction(action: string) {
    await fetch(`/api/research/${jobId}/${action}`, { method: "POST" });
    loadJob();
  }

  async function handleSend() {
    if (!message.trim()) return;
    setSending(true);
    await fetch(`/api/research/${jobId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: message }),
    });
    setMessage("");
    setSending(false);
  }

  if (!job) return <p className="text-muted-foreground">Loading…</p>;

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)]">
      {/* Header */}
      <div className="shrink-0 space-y-4 pb-4">
        <div className="flex items-center gap-3">
          <Link to="/research" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-2xl font-bold">{job.name}</h1>
          <StatusBadge status={job.status} />
          <div className="flex-1" />
          {job.status === "pending" && (
            <Button size="sm" onClick={() => handleAction("start")}>Start</Button>
          )}
          {job.status === "active" && (
            <Button size="sm" variant="outline" onClick={() => handleAction("pause")}>Pause</Button>
          )}
          {job.status === "paused" && (
            <Button size="sm" onClick={() => handleAction("resume")}>Resume</Button>
          )}
        </div>
        <div className="flex gap-4 text-xs text-muted-foreground">
          <span>Model: <span className="text-foreground">{job.model.includes("opus") ? "opus-4.6" : "sonnet-4.6"}</span></span>
          <span>View: <span className="text-foreground font-mono">{job.view_name}</span></span>
          <span>Iterations: <span className="text-foreground">{job.current_iteration}/{job.max_iterations}</span></span>
          <span>Plateau: <span className="text-foreground">{job.iterations_since_checkpoint}/{job.no_improvement_plateau}</span></span>
          {job.date_start && <span>Range: <span className="text-foreground">{job.date_start} → {job.date_end}</span></span>}
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {job.allowlist.map((a) => (
            <Badge key={a} variant="secondary" className="text-xs font-mono">{a}</Badge>
          ))}
        </div>

        {/* Chart */}
        <ObjectiveChart iterations={iterations} />
      </div>

      {/* Timeline (scrollable) */}
      <div className="flex-1 overflow-y-auto min-h-0 border rounded-lg bg-[#0a0a0a] px-4">
        <Timeline jobId={jobId} jobStatus={job.status} />
      </div>

      {/* Message input */}
      <div className="shrink-0 flex gap-2 pt-3">
        <Input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={job.status === "active" ? "Send guidance to the researcher agent…" : "Agent is not active"}
          disabled={job.status !== "active"}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          className="bg-[#111] border-[#333]"
        />
        <Button onClick={handleSend} disabled={sending || !message.trim() || job.status !== "active"} size="sm">
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
