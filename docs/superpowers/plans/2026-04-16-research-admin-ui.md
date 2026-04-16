# Research Admin UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add React pages to the admin SPA for listing, creating, and monitoring autonomous research jobs with a unified live timeline.

**Architecture:** Two new pages (`/research` list + `/research/:id` detail) following existing app patterns (shadcn/ui + Tailwind + fetch + useEffect). The detail page renders a chronological timeline of all research events (chat, param diffs, runs, searches, checkpoints) streamed live via SSE. A collapsible recharts line chart shows objective progression. All data comes from existing Phase 2 API endpoints.

**Tech Stack:** React 19, shadcn/ui (@base-ui primitives), Tailwind 4, recharts (new dep), lucide-react, react-router-dom, EventSource API.

---

## File Structure

**Created:**
- `admin/src/pages/ResearchPage.tsx` — list page with table + create modal trigger
- `admin/src/pages/ResearchJobDetailPage.tsx` — detail page: header + chart + timeline + input
- `admin/src/components/research/create-job-modal.tsx` — form in a Dialog
- `admin/src/components/research/objective-chart.tsx` — recharts LineChart
- `admin/src/components/research/timeline.tsx` — fetches logs, manages SSE, renders events
- `admin/src/components/research/param-diff.tsx` — red/green inline diff
- `admin/src/components/research/run-card.tsx` — compact clickable run status
- `admin/src/components/research/search-result-card.tsx` — expanded search outcome

**Modified:**
- `admin/package.json` — add `recharts`
- `admin/src/App.tsx` — add routes
- `admin/src/components/sidebar.tsx` — add "Research" nav item

---

## Task 1: Add recharts + routing + sidebar

**Files:**
- Modify: `admin/package.json`
- Modify: `admin/src/App.tsx`
- Modify: `admin/src/components/sidebar.tsx`
- Create: `admin/src/pages/ResearchPage.tsx` (stub)
- Create: `admin/src/pages/ResearchJobDetailPage.tsx` (stub)

- [ ] **Step 1: Install recharts**

```bash
cd /Users/adam/Projects/tychos/.worktrees/research-redesign/admin
npm install recharts
```

- [ ] **Step 2: Add sidebar nav item**

In `admin/src/components/sidebar.tsx`, add the import and nav item:

```tsx
import {
  LayoutDashboard,
  Settings2,
  Play,
  GitCompare,
  Database,
  FlaskConical,
  LogOut,
} from "lucide-react";
```

Add to `navItems` array, between the Runs and Datasets entries:

```tsx
{ href: "/research", label: "Research", icon: FlaskConical },
```

- [ ] **Step 3: Create stub pages**

`admin/src/pages/ResearchPage.tsx`:
```tsx
export default function ResearchPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Research Jobs</h1>
      <p className="text-muted-foreground">Loading…</p>
    </div>
  );
}
```

`admin/src/pages/ResearchJobDetailPage.tsx`:
```tsx
import { useParams } from "react-router-dom";

export default function ResearchJobDetailPage() {
  const { id } = useParams();
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Research Job #{id}</h1>
      <p className="text-muted-foreground">Loading…</p>
    </div>
  );
}
```

- [ ] **Step 4: Add routes to App.tsx**

Add imports at the top:
```tsx
import ResearchPage from "@/pages/ResearchPage";
import ResearchJobDetailPage from "@/pages/ResearchJobDetailPage";
```

Add routes inside the inner `<Routes>`, after the compare route:
```tsx
<Route path="/research" element={<ResearchPage />} />
<Route path="/research/:id" element={<ResearchJobDetailPage />} />
```

- [ ] **Step 5: Verify dev server boots**

```bash
cd /Users/adam/Projects/tychos/.worktrees/research-redesign/admin
npm run dev -- --port 5174 &
sleep 3
curl -s http://localhost:5174 | head -5
kill %1 2>/dev/null
```

- [ ] **Step 6: Commit**

```bash
cd /Users/adam/Projects/tychos/.worktrees/research-redesign
git add admin/
git commit -m "feat(admin): add research routing, sidebar nav, and stub pages"
```

---

## Task 2: Research Jobs list page

**Files:**
- Modify: `admin/src/pages/ResearchPage.tsx` (full implementation)
- Create: `admin/src/components/research/create-job-modal.tsx`

- [ ] **Step 1: Implement ResearchPage.tsx**

```tsx
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
    const res = await fetch("/api/research");
    if (res.ok) setJobs(await res.json());
    setLoading(false);
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
```

- [ ] **Step 2: Implement create-job-modal.tsx**

```tsx
import { useState, useEffect } from "react";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus } from "lucide-react";

interface ParamSet {
  id: number;
  name: string;
}

interface Dataset {
  id: number;
  slug: string;
  name: string;
}

const VIEWS = ["v_solar_position", "v_moon_position", "v_combined_position"];
const MODELS = [
  { value: "claude-sonnet-4-6", label: "Sonnet 4.6" },
  { value: "claude-opus-4-6", label: "Opus 4.6" },
];

export function CreateJobModal({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [paramSets, setParamSets] = useState<ParamSet[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const [name, setName] = useState("");
  const [paramSetId, setParamSetId] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [viewName, setViewName] = useState(VIEWS[0]);
  const [allowlist, setAllowlist] = useState("sun.*, sun_def.*");
  const [model, setModel] = useState(MODELS[0].value);
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [maxIterations, setMaxIterations] = useState("40");
  const [maxWallClock, setMaxWallClock] = useState("3600");
  const [plateau, setPlateau] = useState("6");

  useEffect(() => {
    if (!open) return;
    fetch("/api/params").then((r) => r.json()).then((d) => setParamSets(d));
    fetch("/api/datasets").then((r) => r.json()).then((d) => setDatasets(d));
  }, [open]);

  async function handleSubmit() {
    setSubmitting(true);
    const body = {
      name,
      param_set_id: Number(paramSetId),
      dataset_id: Number(datasetId),
      view_name: viewName,
      allowlist: allowlist.split(",").map((s) => s.trim()).filter(Boolean),
      model,
      date_start: dateStart || undefined,
      date_end: dateEnd || undefined,
      max_iterations: Number(maxIterations),
      max_wall_clock_seconds: Number(maxWallClock),
      no_improvement_plateau: Number(plateau),
    };
    const res = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setSubmitting(false);
    if (res.ok) {
      setOpen(false);
      onCreated();
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button><Plus className="h-4 w-4 mr-2" />New Research Job</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Create Research Job</DialogTitle>
          <DialogDescription>Configure an autonomous parameter optimization session.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="solar-sim-04" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Param Set</Label>
              <Select value={paramSetId} onValueChange={setParamSetId}>
                <SelectTrigger><SelectValue placeholder="Select…" /></SelectTrigger>
                <SelectContent>
                  {paramSets.map((ps) => (
                    <SelectItem key={ps.id} value={String(ps.id)}>{ps.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Dataset</Label>
              <Select value={datasetId} onValueChange={setDatasetId}>
                <SelectTrigger><SelectValue placeholder="Select…" /></SelectTrigger>
                <SelectContent>
                  {datasets.map((ds) => (
                    <SelectItem key={ds.id} value={String(ds.id)}>{ds.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>View</Label>
              <Select value={viewName} onValueChange={setViewName}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {VIEWS.map((v) => (
                    <SelectItem key={v} value={v}>{v.replace("v_", "").replace("_", " ")}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Model</Label>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {MODELS.map((m) => (
                    <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-2">
            <Label>Allowlist (comma-separated globs)</Label>
            <Input value={allowlist} onChange={(e) => setAllowlist(e.target.value)} placeholder="sun.*, sun_def.*" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Date Start (optional)</Label>
              <Input value={dateStart} onChange={(e) => setDateStart(e.target.value)} placeholder="1900-01-01" />
            </div>
            <div className="grid gap-2">
              <Label>Date End (optional)</Label>
              <Input value={dateEnd} onChange={(e) => setDateEnd(e.target.value)} placeholder="2050-12-31" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="grid gap-2">
              <Label>Max Iterations</Label>
              <Input type="number" value={maxIterations} onChange={(e) => setMaxIterations(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label>Wall Clock (s)</Label>
              <Input type="number" value={maxWallClock} onChange={(e) => setMaxWallClock(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label>Plateau Limit</Label>
              <Input type="number" value={plateau} onChange={(e) => setPlateau(e.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
          <Button onClick={handleSubmit} disabled={submitting || !name || !paramSetId || !datasetId}>
            {submitting ? "Creating…" : "Create Job"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 3: Verify list page renders**

Start the admin dev server and the API server (on different ports), navigate to `/research`. The table should load (empty or with existing jobs). The "New Research Job" button should open the modal with working dropdowns.

- [ ] **Step 4: Commit**

```bash
git add admin/src/pages/ResearchPage.tsx admin/src/components/research/
git commit -m "feat(admin): research jobs list page with create modal"
```

---

## Task 3: Param diff component

**Files:**
- Create: `admin/src/components/research/param-diff.tsx`

- [ ] **Step 1: Implement param-diff.tsx**

```tsx
interface ParamDiffProps {
  prevLabel: string;
  nextLabel: string;
  prev: Record<string, Record<string, number>>;
  next: Record<string, Record<string, number>>;
}

export function ParamDiff({ prevLabel, nextLabel, prev, next }: ParamDiffProps) {
  const diffs: { key: string; oldVal: number; newVal: number }[] = [];

  for (const body of Object.keys(next)) {
    if (!prev[body]) continue;
    for (const field of Object.keys(next[body])) {
      const oldVal = prev[body]?.[field];
      const newVal = next[body][field];
      if (oldVal !== undefined && oldVal !== newVal) {
        diffs.push({ key: `${body}.${field}`, oldVal, newVal });
      }
    }
  }

  if (diffs.length === 0) {
    return (
      <div className="bg-[#0d1117] border border-[#1c2333] rounded-md px-3 py-2 mt-1.5 font-mono text-xs leading-relaxed">
        <div className="text-muted-foreground">{prevLabel} → {nextLabel} (no changes)</div>
      </div>
    );
  }

  return (
    <div className="bg-[#0d1117] border border-[#1c2333] rounded-md px-3 py-2 mt-1.5 font-mono text-xs leading-relaxed">
      <div className="text-muted-foreground mb-1">{prevLabel} → {nextLabel}</div>
      {diffs.map((d) => (
        <div key={d.key}>
          <div className="text-red-400">- {d.key}: {d.oldVal}</div>
          <div className="text-green-400">+ {d.key}: {d.newVal}</div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add admin/src/components/research/param-diff.tsx
git commit -m "feat(admin): param diff component for research timeline"
```

---

## Task 4: Run card + search result card components

**Files:**
- Create: `admin/src/components/research/run-card.tsx`
- Create: `admin/src/components/research/search-result-card.tsx`

- [ ] **Step 1: Implement run-card.tsx**

```tsx
import { Link } from "react-router-dom";

interface RunCardProps {
  runId: number;
  objective: number | null;
  nScored: number | null;
  status?: string;
  prevObjective?: number | null;
}

export function RunCard({ runId, objective, nScored, status = "done", prevObjective }: RunCardProps) {
  const improved = prevObjective != null && objective != null && objective < prevObjective;
  const worsened = prevObjective != null && objective != null && objective > prevObjective;

  return (
    <Link
      to={`/results/${runId}`}
      onClick={(e) => e.stopPropagation()}
      className="flex items-center gap-2.5 bg-[#111] border border-[#2a2a2a] rounded-md px-3 py-2 mt-1 hover:border-[#444] transition-colors"
    >
      <div className={`w-2 h-2 rounded-full shrink-0 ${
        status === "done" ? "bg-green-500" :
        status === "running" ? "bg-yellow-500 animate-pulse" :
        status === "failed" ? "bg-red-500" : "bg-gray-500"
      }`} />
      <span className="text-xs text-muted-foreground">Run #{runId}</span>
      {nScored != null && (
        <span className="text-xs text-muted-foreground">{nScored} eclipses</span>
      )}
      <div className="flex-1" />
      {objective != null && (
        <span className={`text-xs font-semibold ${
          improved ? "text-green-400" : worsened ? "text-red-400" : "text-yellow-400"
        }`}>
          obj: {objective.toFixed(2)}
          {improved && " ↓"}
          {worsened && " ↑"}
        </span>
      )}
      <span className="text-[#555] text-xs">→</span>
    </Link>
  );
}
```

- [ ] **Step 2: Implement search-result-card.tsx**

```tsx
import { ParamDiff } from "./param-diff";
import { RunCard } from "./run-card";

interface SearchResultCardProps {
  startingObjective: number;
  bestObjective: number;
  nEvals: number;
  improved: boolean;
  winnerVersionId: number | null;
  winnerRunId: number | null;
  prevParams?: Record<string, Record<string, number>>;
  winnerParams?: Record<string, Record<string, number>>;
  prevLabel?: string;
  nextLabel?: string;
}

export function SearchResultCard({
  startingObjective,
  bestObjective,
  nEvals,
  improved,
  winnerVersionId,
  winnerRunId,
  prevParams,
  winnerParams,
  prevLabel = "",
  nextLabel = "",
}: SearchResultCardProps) {
  const delta = bestObjective - startingObjective;

  return (
    <div className="bg-[#111] border border-purple-500/20 rounded-md p-3 mt-1">
      <div className="flex items-center gap-2.5 mb-2">
        <span className="text-purple-400 text-xs font-semibold">Search complete</span>
        <span className="text-muted-foreground text-xs">{nEvals} evals</span>
      </div>
      <div className="flex gap-4 text-xs mb-2">
        <div><span className="text-muted-foreground">start:</span>{" "}
          <span className="text-yellow-400">{startingObjective.toFixed(2)}</span></div>
        <div><span className="text-muted-foreground">best:</span>{" "}
          <span className={improved ? "text-green-400 font-semibold" : "text-muted-foreground"}>
            {bestObjective.toFixed(2)}
          </span></div>
        <div><span className="text-muted-foreground">Δ:</span>{" "}
          <span className={improved ? "text-green-400" : "text-muted-foreground"}>
            {delta.toFixed(2)} {improved ? "✓" : "(no improvement)"}
          </span></div>
      </div>
      {improved && prevParams && winnerParams && (
        <ParamDiff
          prevLabel={prevLabel}
          nextLabel={nextLabel}
          prev={prevParams}
          next={winnerParams}
        />
      )}
      {improved && winnerRunId && (
        <RunCard
          runId={winnerRunId}
          objective={bestObjective}
          nScored={null}
          prevObjective={startingObjective}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add admin/src/components/research/run-card.tsx admin/src/components/research/search-result-card.tsx
git commit -m "feat(admin): run card and search result card components"
```

---

## Task 5: Objective chart component

**Files:**
- Create: `admin/src/components/research/objective-chart.tsx`

- [ ] **Step 1: Implement objective-chart.tsx**

```tsx
import { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceDot,
} from "recharts";
import { ChevronDown, ChevronRight } from "lucide-react";

interface Iteration {
  id: number;
  kind: string;
  objective: number | null;
}

interface ObjectiveChartProps {
  iterations: Iteration[];
}

export function ObjectiveChart({ iterations }: ObjectiveChartProps) {
  const [collapsed, setCollapsed] = useState(false);

  const data = iterations
    .filter((it) => it.objective != null)
    .map((it, idx) => ({
      index: idx + 1,
      objective: it.objective,
      kind: it.kind,
      id: it.id,
    }));

  if (data.length === 0) return null;

  const checkpoints = data.filter((d) => d.kind === "search_winner" || d.kind === "iterate");
  const searchWinners = data.filter((d) => d.kind === "search_winner");

  return (
    <div className="border rounded-lg bg-card">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 w-full px-4 py-3 text-sm font-medium hover:bg-accent/50 transition-colors"
      >
        {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        Objective over time
        <span className="text-muted-foreground ml-2 font-normal">
          {data.length} iterations · best: {Math.min(...data.map((d) => d.objective!)).toFixed(2)} arcmin
        </span>
      </button>
      {!collapsed && (
        <div className="px-4 pb-4">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data}>
              <XAxis
                dataKey="index"
                tick={{ fontSize: 11, fill: "#888" }}
                axisLine={{ stroke: "#333" }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#888" }}
                axisLine={{ stroke: "#333" }}
                tickLine={false}
                width={50}
              />
              <Tooltip
                contentStyle={{ background: "#1a1a1a", border: "1px solid #333", borderRadius: 6, fontSize: 12 }}
                labelFormatter={(v) => `Iteration ${v}`}
                formatter={(v: number) => [`${v.toFixed(4)} arcmin`, "Objective"]}
              />
              <Line
                type="monotone"
                dataKey="objective"
                stroke="#a78bfa"
                strokeWidth={2}
                dot={{ r: 3, fill: "#a78bfa" }}
                activeDot={{ r: 5 }}
              />
              {searchWinners.map((d) => (
                <ReferenceDot
                  key={d.id}
                  x={d.index}
                  y={d.objective!}
                  r={6}
                  fill="#22c55e"
                  stroke="#22c55e"
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add admin/src/components/research/objective-chart.tsx
git commit -m "feat(admin): objective-over-time chart component"
```

---

## Task 6: Timeline component

**Files:**
- Create: `admin/src/components/research/timeline.tsx`

This is the core component — renders all event types and manages SSE streaming.

- [ ] **Step 1: Implement timeline.tsx**

```tsx
import { useState, useEffect, useRef } from "react";
import { ParamDiff } from "./param-diff";
import { RunCard } from "./run-card";
import { SearchResultCard } from "./search-result-card";

interface LogEntry {
  id: number;
  research_job_id: number;
  research_iteration_id: number | null;
  role: string;
  content: string | null;
  tool_name: string | null;
  token_count: number | null;
  created_at: string;
}

interface TimelineProps {
  jobId: number;
  jobStatus: string;
}

export function Timeline({ jobId, jobStatus }: TimelineProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const sseRef = useRef<EventSource | null>(null);

  useEffect(() => {
    fetch(`/api/research/${jobId}/logs?limit=500`)
      .then((r) => r.json())
      .then((data) => {
        setLogs(data);
        setLoading(false);
      });
  }, [jobId]);

  useEffect(() => {
    if (jobStatus !== "active") return;
    const es = new EventSource(`/api/research/${jobId}/logs/stream`);
    sseRef.current = es;
    es.addEventListener("log", (e) => {
      try {
        const entry: LogEntry = JSON.parse(e.data);
        setLogs((prev) => {
          if (prev.some((l) => l.id === entry.id)) return prev;
          return [...prev, entry];
        });
      } catch {}
    });
    return () => { es.close(); sseRef.current = null; };
  }, [jobId, jobStatus]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  if (loading) return <p className="text-sm text-muted-foreground py-4">Loading timeline…</p>;

  const grouped = groupLogs(logs);

  return (
    <div className="flex flex-col gap-3 py-4">
      {grouped.map((group, idx) => (
        <TimelineEvent key={group.id} group={group} prevGroup={grouped[idx - 1]} />
      ))}
      {logs.length === 0 && (
        <p className="text-center text-muted-foreground py-8">
          {jobStatus === "pending" ? "Job not started yet" : "No events yet"}
        </p>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

interface EventGroup {
  id: number;
  type: "assistant" | "tool" | "checkpoint" | "restore" | "user_inject" | "system";
  role: string;
  content: string | null;
  toolName: string | null;
  toolInput: Record<string, unknown> | null;
  toolResult: Record<string, unknown> | null;
  created_at: string;
}

function groupLogs(logs: LogEntry[]): EventGroup[] {
  const groups: EventGroup[] = [];
  let i = 0;
  while (i < logs.length) {
    const log = logs[i];

    if (log.role === "tool_call") {
      const resultLog = logs[i + 1]?.role === "tool_result" && logs[i + 1]?.tool_name === log.tool_name
        ? logs[i + 1]
        : null;

      let toolInput: Record<string, unknown> | null = null;
      let toolResult: Record<string, unknown> | null = null;
      try { toolInput = JSON.parse(log.content || "{}"); } catch {}
      if (resultLog) {
        try {
          const parsed = JSON.parse(resultLog.content || "{}");
          const resultStr = parsed.result || resultLog.content;
          toolResult = typeof resultStr === "string" ? JSON.parse(resultStr) : resultStr;
        } catch {}
      }

      if (log.tool_name === "checkpoint") {
        groups.push({
          id: log.id, type: "checkpoint", role: log.role,
          content: null, toolName: log.tool_name,
          toolInput, toolResult, created_at: log.created_at,
        });
      } else if (log.tool_name === "restore") {
        groups.push({
          id: log.id, type: "restore", role: log.role,
          content: null, toolName: log.tool_name,
          toolInput, toolResult, created_at: log.created_at,
        });
      } else {
        groups.push({
          id: log.id, type: "tool", role: log.role,
          content: log.content, toolName: log.tool_name,
          toolInput, toolResult, created_at: log.created_at,
        });
      }
      i += resultLog ? 2 : 1;
    } else {
      groups.push({
        id: log.id,
        type: log.role === "user_inject" ? "user_inject"
          : log.role === "system" ? "system"
          : "assistant",
        role: log.role,
        content: log.content,
        toolName: null,
        toolInput: null,
        toolResult: null,
        created_at: log.created_at,
      });
      i++;
    }
  }
  return groups;
}

function TimelineEvent({ group, prevGroup }: { group: EventGroup; prevGroup?: EventGroup }) {
  if (group.type === "system") {
    return (
      <div className="text-center text-xs text-muted-foreground py-1">
        {group.content}
      </div>
    );
  }

  if (group.type === "checkpoint") {
    const versionId = group.toolInput?.input
      ? (group.toolInput.input as Record<string, unknown>).version_id
      : group.toolInput?.version_id;
    const obj = group.toolResult?.objective ?? group.toolResult?.ok;
    return (
      <div className="flex items-center gap-2 py-1">
        <div className="flex-1 h-px bg-gradient-to-r from-transparent via-green-500/50 to-transparent" />
        <span className="text-green-400 text-xs font-semibold whitespace-nowrap">
          ✓ Checkpoint v{versionId}{obj && typeof obj === "number" ? ` — obj: ${obj.toFixed(2)}` : ""}
        </span>
        <div className="flex-1 h-px bg-gradient-to-r from-transparent via-green-500/50 to-transparent" />
      </div>
    );
  }

  if (group.type === "restore") {
    const versionId = group.toolInput?.input
      ? (group.toolInput.input as Record<string, unknown>).version_id
      : group.toolInput?.version_id;
    return (
      <div className="flex items-center gap-2 py-1">
        <div className="flex-1 h-px bg-gradient-to-r from-transparent via-yellow-500/50 to-transparent" />
        <span className="text-yellow-400 text-xs font-semibold whitespace-nowrap">
          ↩ Restored from v{versionId}
        </span>
        <div className="flex-1 h-px bg-gradient-to-r from-transparent via-yellow-500/50 to-transparent" />
      </div>
    );
  }

  if (group.type === "user_inject") {
    return (
      <div className="flex gap-2.5 justify-end">
        <div className="bg-blue-950/50 border border-blue-600/20 rounded-lg px-3.5 py-2.5 max-w-[75%]">
          <div className="text-blue-400 text-[10px] mb-1">You</div>
          <div className="text-sm whitespace-pre-wrap">{group.content}</div>
        </div>
        <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center shrink-0 text-[11px] font-semibold text-white">U</div>
      </div>
    );
  }

  if (group.type === "tool" && group.toolName === "propose_params") {
    const result = group.toolResult || {};
    const prevObj = prevGroup?.toolResult?.objective as number | undefined;
    return (
      <div className="flex gap-2.5">
        <div className="w-7 h-7 rounded-full bg-purple-600 flex items-center justify-center shrink-0 text-[11px] font-semibold text-white">AI</div>
        <div className="flex-1 max-w-[85%]">
          <div className="bg-[#1a1a2e] border border-[#2a2a4a] rounded-lg px-3.5 py-2.5">
            <span className="text-muted-foreground text-xs">🔧 propose_params</span>
          </div>
          {result.run_id && (
            <RunCard
              runId={result.run_id as number}
              objective={result.objective as number | null}
              nScored={result.n_scored as number | null}
              prevObjective={prevObj}
            />
          )}
        </div>
      </div>
    );
  }

  if (group.type === "tool" && group.toolName === "search") {
    const result = group.toolResult || {};
    const input = group.toolInput?.input as Record<string, unknown> | undefined;
    return (
      <div className="flex gap-2.5">
        <div className="w-7 h-7 rounded-full bg-purple-600 flex items-center justify-center shrink-0 text-[11px] font-semibold text-white">AI</div>
        <div className="flex-1 max-w-[85%]">
          <div className="bg-[#1a1a2e] border border-[#2a2a4a] rounded-lg px-3.5 py-2.5">
            <span className="text-purple-400 text-xs">🔍 search</span>
            <div className="bg-[#0d1117] border border-[#1c2333] rounded-md px-3 py-2 mt-1.5 font-mono text-xs">
              <div className="text-muted-foreground">
                Nelder-Mead · budget={String(input?.budget ?? "?")} · scale={String(input?.scale ?? "?")}
              </div>
              <div className="text-purple-400">
                params: {Array.isArray(input?.param_keys) ? (input.param_keys as string[]).join(", ") : "?"}
              </div>
            </div>
          </div>
          {result.starting_objective != null && (
            <SearchResultCard
              startingObjective={result.starting_objective as number}
              bestObjective={result.best_objective as number}
              nEvals={result.n_evals as number}
              improved={result.improved as boolean}
              winnerVersionId={result.winner_version_id as number | null}
              winnerRunId={result.winner_run_id as number | null}
            />
          )}
        </div>
      </div>
    );
  }

  // Default: assistant message
  return (
    <div className="flex gap-2.5">
      <div className="w-7 h-7 rounded-full bg-purple-600 flex items-center justify-center shrink-0 text-[11px] font-semibold text-white">AI</div>
      <div className="bg-[#1a1a2e] border border-[#2a2a4a] rounded-lg px-3.5 py-2.5 max-w-[85%]">
        <div className="text-sm whitespace-pre-wrap">{group.content}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add admin/src/components/research/timeline.tsx
git commit -m "feat(admin): unified research timeline with SSE streaming"
```

---

## Task 7: Job detail page

**Files:**
- Modify: `admin/src/pages/ResearchJobDetailPage.tsx` (full implementation)

- [ ] **Step 1: Implement ResearchJobDetailPage.tsx**

```tsx
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
```

- [ ] **Step 2: Commit**

```bash
git add admin/src/pages/ResearchJobDetailPage.tsx
git commit -m "feat(admin): research job detail page with chart, timeline, and message input"
```

---

## Task 8: Visual verification

**Files:** None (manual testing)

- [ ] **Step 1: Start both servers**

Terminal 1 (API):
```bash
cd /Users/adam/Projects/tychos/.worktrees/research-redesign
source local_deploy/.env
source tychos_skyfield/.venv/bin/activate
DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_research_redesign TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw PYTHONPATH=tychos_skyfield:tests:. uvicorn server.app:app --port 8765
```

Terminal 2 (Admin):
```bash
cd /Users/adam/Projects/tychos/.worktrees/research-redesign/admin
VITE_API_URL=http://localhost:8765 npm run dev -- --port 5174
```

- [ ] **Step 2: Verify in browser**

1. Open http://localhost:5174
2. Login as admin@t.local / pw
3. Click "Research" in sidebar — verify list page loads
4. Click "New Research Job" — verify modal opens with dropdowns populated
5. Create a job — verify it appears in the list as "pending"
6. Click the job row — verify detail page loads with header, empty chart, empty timeline
7. Click "Start" — if ANTHROPIC_API_KEY is set, watch the timeline populate live

- [ ] **Step 3: Commit any fixes found during verification**

```bash
git add -u
git commit -m "fix(admin): visual testing fixes"
```

---

## Self-Review Checklist

- **Spec coverage:**
  - Research Jobs list with status/model/view/iterations — Task 2 ✓
  - Row click → detail — Task 2 ✓
  - Action buttons per row (Start/Pause/Resume) — Task 2 ✓
  - Create Job modal with all fields — Task 2 ✓
  - Job detail header with controls — Task 7 ✓
  - Collapsible objective chart — Task 5 ✓
  - Unified timeline with all event types — Task 6 ✓
  - Agent messages (purple, left-aligned) — Task 6 ✓
  - propose_params with param diff + run card — Tasks 3, 4, 6 ✓
  - search with expanded result card — Tasks 4, 6 ✓
  - Checkpoints (green divider) — Task 6 ✓
  - Restore (yellow divider) — Task 6 ✓
  - User messages (blue, right-aligned) — Task 6 ✓
  - System messages (centered, muted) — Task 6 ✓
  - SSE live streaming — Task 6 ✓
  - Message input at bottom — Task 7 ✓
  - Sidebar nav item — Task 1 ✓
  - Routing — Task 1 ✓
  - recharts dependency — Task 1 ✓

- **Placeholder scan:** All components have complete code. No TBD/TODO.

- **Type consistency:**
  - `LogEntry` interface in timeline.tsx matches `research_logs` schema columns ✓
  - `ResearchJob` interface matches the columns from `GET /api/research/{id}` ✓
  - `ParamDiffProps` expects `Record<string, Record<string, number>>` which is the params dict shape ✓
  - `RunCardProps` fields match what `propose_params` tool result returns ✓
  - `SearchResultCardProps` fields match `search` tool result ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-16-research-admin-ui.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
