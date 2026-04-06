import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";

interface ParamFormProps {
  onCreated: (id: number) => void;
}

interface ParamSetOption {
  id: number;
  name: string;
  versions: { id: number; version_number: number }[];
}

type SourceMode = "existing" | "upload" | "manual";

export function ParamForm({ onCreated }: ParamFormProps) {
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [paramsJson, setParamsJson] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [jsonError, setJsonError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  const [sourceMode, setSourceMode] = React.useState<SourceMode>("existing");
  const [paramSets, setParamSets] = React.useState<ParamSetOption[]>([]);
  const [selectedSetId, setSelectedSetId] = React.useState<string>("");
  const [selectedVersionId, setSelectedVersionId] = React.useState<string>("");
  const [loadingParams, setLoadingParams] = React.useState(false);

  // Load param sets when dialog opens
  React.useEffect(() => {
    if (!open) return;
    fetch("/api/params")
      .then((r) => r.json())
      .then((sets: Array<Record<string, unknown>>) => {
        // For each set, fetch its versions
        Promise.all(
          sets.map((s) =>
            fetch(`/api/params/${s.id}`)
              .then((r) => r.json())
              .then((detail: Record<string, unknown>) => ({
                id: s.id as number,
                name: s.name as string,
                versions: ((detail.versions as Array<Record<string, unknown>>) || []).map(
                  (v) => ({
                    id: v.id as number,
                    version_number: v.version_number as number,
                  })
                ),
              }))
          )
        ).then(setParamSets);
      });
  }, [open]);

  // Load params when selection changes
  React.useEffect(() => {
    if (!selectedSetId || !selectedVersionId) {
      if (sourceMode === "existing") setParamsJson("");
      return;
    }
    setLoadingParams(true);
    setJsonError(null);
    fetch(`/api/params/${selectedSetId}/versions/${selectedVersionId}`)
      .then((r) => r.json())
      .then((ver: Record<string, unknown>) => {
        const json = ver.params_json as string;
        setParamsJson(json);
        validateJson(json);
      })
      .finally(() => setLoadingParams(false));
  }, [selectedSetId, selectedVersionId]);

  // Auto-select latest version when param set changes
  React.useEffect(() => {
    if (!selectedSetId) {
      setSelectedVersionId("");
      return;
    }
    const set = paramSets.find((s) => String(s.id) === selectedSetId);
    if (set && set.versions.length > 0) {
      setSelectedVersionId(String(set.versions[0].id));
    } else {
      setSelectedVersionId("");
    }
  }, [selectedSetId, paramSets]);

  function validateJson(json: string): boolean {
    if (!json.trim()) {
      setJsonError(null);
      return false;
    }
    try {
      const parsed = JSON.parse(json);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        setJsonError("Must be a JSON object with body keys (e.g. earth, sun, moon)");
        return false;
      }
      // Check structure: should have at least one body with param fields
      const bodies = Object.keys(parsed);
      if (bodies.length === 0) {
        setJsonError("Empty object — needs at least one body (e.g. earth, sun)");
        return false;
      }
      for (const body of bodies) {
        if (typeof parsed[body] !== "object" || parsed[body] === null) {
          setJsonError(`"${body}" must be an object with parameter fields`);
          return false;
        }
      }
      setJsonError(null);
      return true;
    } catch (e) {
      const msg = e instanceof SyntaxError ? e.message : "Invalid JSON";
      setJsonError(msg);
      return false;
    }
  }

  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = reader.result as string;
      try {
        const parsed = JSON.parse(text);
        // Support both raw params and the download format {name, params_json, ...}
        if (parsed.params_json) {
          if (parsed.name && !name) setName(parsed.name);
          if (parsed.description && !description) setDescription(parsed.description);
          if (parsed.notes && !notes) setNotes(parsed.notes);
          const json = typeof parsed.params_json === "string" ? parsed.params_json : JSON.stringify(parsed.params_json, null, 2);
          setParamsJson(json);
          validateJson(json);
        } else {
          // Assume it's raw params JSON
          const json = JSON.stringify(parsed, null, 2);
          setParamsJson(json);
          validateJson(json);
        }
      } catch (err) {
        const msg = err instanceof SyntaxError ? err.message : "Invalid JSON file";
        setJsonError(msg);
        setParamsJson(text);
      }
    };
    reader.readAsText(file);
    // Reset input so the same file can be re-selected
    e.target.value = "";
  }

  function handleJsonChange(value: string) {
    setParamsJson(value);
    validateJson(value);
  }

  const isValid = name.trim() && paramsJson.trim() && !jsonError;

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!isValid) return;
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/params", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: description || undefined,
          params_json: paramsJson,
          notes: notes || undefined,
        }),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail ?? data.error ?? "Failed to create param set");
        return;
      }
      const created = await res.json();
      // Reset form
      setName("");
      setDescription("");
      setNotes("");
      setParamsJson("");
      setJsonError(null);
      setSelectedSetId("");
      setSelectedVersionId("");
      setOpen(false);
      onCreated(created.id);
    } catch {
      setError("Network error");
    } finally {
      setSubmitting(false);
    }
  }

  const selectedSet = paramSets.find((s) => String(s.id) === selectedSetId);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>Create New</DialogTrigger>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create Parameter Set</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ps-name">Name</Label>
            <Input
              id="ps-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="my-params-v1"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ps-description">Description</Label>
            <Input
              id="ps-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
            />
          </div>

          {/* Source selector */}
          <div className="flex flex-col gap-2">
            <Label>Parameter Source</Label>
            <div className="flex gap-1">
              {(["existing", "upload", "manual"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
                    sourceMode === mode
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-background border-input hover:bg-muted"
                  }`}
                  onClick={() => {
                    setSourceMode(mode);
                    setJsonError(null);
                    if (mode !== "existing") {
                      setSelectedSetId("");
                      setSelectedVersionId("");
                    }
                  }}
                >
                  {mode === "existing" ? "From Existing" : mode === "upload" ? "Upload JSON" : "Manual"}
                </button>
              ))}
            </div>
          </div>

          {/* Existing param set picker */}
          {sourceMode === "existing" && (
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ps-source-set">Parameter Set</Label>
                <select
                  id="ps-source-set"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  value={selectedSetId}
                  onChange={(e) => setSelectedSetId(e.target.value)}
                >
                  <option value="">Select a parameter set...</option>
                  {paramSets.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
              {selectedSet && selectedSet.versions.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="ps-source-version">Version</Label>
                  <select
                    id="ps-source-version"
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    value={selectedVersionId}
                    onChange={(e) => setSelectedVersionId(e.target.value)}
                  >
                    {selectedSet.versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        v{v.version_number}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {loadingParams && (
                <p className="text-xs text-muted-foreground">Loading parameters...</p>
              )}
            </div>
          )}

          {/* File upload */}
          {sourceMode === "upload" && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ps-file">JSON File</Label>
              <input
                id="ps-file"
                type="file"
                accept=".json,application/json"
                onChange={handleFileUpload}
                className="w-full text-sm file:mr-3 file:rounded-md file:border file:border-input file:bg-background file:px-3 file:py-1.5 file:text-sm file:cursor-pointer hover:file:bg-muted"
              />
              <p className="text-xs text-muted-foreground">
                Accepts raw params JSON or the download format from this app.
              </p>
            </div>
          )}

          {/* JSON textarea — always shown, editable in manual mode, readonly for existing/upload */}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ps-json">
              Parameters JSON
              {paramsJson && !jsonError && (
                <span className="ml-2 text-xs text-green-600 font-normal">Valid</span>
              )}
            </Label>
            <textarea
              id="ps-json"
              value={paramsJson}
              onChange={(e) => handleJsonChange(e.target.value)}
              readOnly={sourceMode === "existing"}
              rows={8}
              placeholder='{"earth": {"orbit_radius": 1.0, ...}, ...}'
              className={`w-full rounded-md border bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring resize-y ${
                jsonError ? "border-destructive" : ""
              } ${sourceMode === "existing" ? "opacity-60" : ""}`}
            />
            {jsonError && (
              <p className="text-sm text-destructive">{jsonError}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ps-notes">Notes</Label>
            <Input
              id="ps-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Optional version notes"
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="submit" disabled={submitting || !isValid}>
              {submitting ? "Creating..." : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
