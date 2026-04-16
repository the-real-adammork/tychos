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
      <DialogTrigger render={<Button />}>
        <Plus className="h-4 w-4 mr-2" />New Research Job
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
          <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
          <Button onClick={handleSubmit} disabled={submitting || !name || !paramSetId || !datasetId}>
            {submitting ? "Creating…" : "Create Job"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
