import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";

const PARAM_FIELDS = [
  "orbit_radius",
  "orbit_center_a",
  "orbit_center_b",
  "orbit_center_c",
  "orbit_tilt_a",
  "orbit_tilt_b",
  "start_pos",
  "speed",
] as const;

type ParamField = (typeof PARAM_FIELDS)[number];
type BodyParams = Partial<Record<ParamField, string>>;
type ParamsData = Record<string, BodyParams>;

interface ParamSetMeta {
  id: number;
  name: string;
  description: string | null;
  paramsJson: string;
  latestVersionId: number;
  owner: { id: number; name: string };
}

interface ParamEditorProps {
  id: string;
  versionId?: string;  // if editing from a specific version
  onSaved?: () => void;
}

export function ParamEditor({ id, versionId, onSaved }: ParamEditorProps) {
  const navigate = useNavigate();
  const [meta, setMeta] = React.useState<ParamSetMeta | null>(null);
  const [values, setValues] = React.useState<ParamsData>({});
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState(false);
  const [notes, setNotes] = React.useState("");

  React.useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        // Get the param set detail
        const detailRes = await fetch(`/api/params/${id}`);
        if (!detailRes.ok) {
          setError(detailRes.status === 404 ? "Parameter set not found" : "Failed to load");
          return;
        }
        const detail = await detailRes.json();

        const versions: Array<{ id: number; version_number: number }> = detail.versions ?? [];
        if (versions.length === 0) {
          setError("No versions found for this parameter set");
          return;
        }

        // If editing a specific version, use that. Otherwise use latest.
        const targetVersionId = versionId ? parseInt(versionId) : versions[0].id;

        const verRes = await fetch(`/api/params/${id}/versions/${targetVersionId}`);
        if (!verRes.ok) {
          setError("Failed to load parameter version");
          return;
        }
        const verData = await verRes.json();

        const data: ParamSetMeta = {
          id: detail.id,
          name: detail.name,
          description: detail.description,
          paramsJson: verData.params_json,
          latestVersionId: targetVersionId,
          owner: { id: detail.owner_id, name: detail.owner_name },
        };
        setMeta(data);
        try {
          const parsed = JSON.parse(data.paramsJson) as Record<string, Record<string, unknown>>;
          const stringified: ParamsData = {};
          for (const [body, fields] of Object.entries(parsed)) {
            stringified[body] = {};
            for (const field of PARAM_FIELDS) {
              const val = fields[field];
              stringified[body][field] = val !== undefined ? String(val) : "";
            }
          }
          setValues(stringified);
        } catch {
          setError("params_json is not valid JSON");
        }
      } catch {
        setError("Network error");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  function handleChange(body: string, field: ParamField, value: string) {
    setValues((prev) => ({
      ...prev,
      [body]: { ...prev[body], [field]: value },
    }));
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      // Reconstruct JSON: parse numbers where possible
      const reconstructed: Record<string, Record<string, unknown>> = {};
      for (const [body, fields] of Object.entries(values)) {
        reconstructed[body] = {};
        for (const field of PARAM_FIELDS) {
          const raw = fields[field] ?? "";
          const num = Number(raw);
          reconstructed[body][field] = raw !== "" && !isNaN(num) ? num : raw;
        }
      }
      const paramsJson = JSON.stringify(reconstructed);
      const res = await fetch(`/api/params/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ params_json: paramsJson, parent_version_id: meta?.latestVersionId, notes: notes || null }),
      });
      if (!res.ok) {
        const errData = await res.json();
        setSaveError(errData.error ?? "Failed to save");
        return;
      }
      const result = await res.json();
      setSaved(true);
      onSaved?.();
      // Navigate to new version detail if one was created, otherwise back to param set
      if (result.new_version_id) {
        navigate(`/parameters/${id}/versions/${result.new_version_id}`);
      } else {
        navigate(`/parameters/${id}`);
      }
    } catch {
      setSaveError("Network error");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }
  if (!meta) return null;

  const bodies = Object.keys(values);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{meta.name}</h1>
          {meta.description && (
            <p className="text-sm text-muted-foreground mt-1">{meta.description}</p>
          )}
          <p className="text-xs text-muted-foreground mt-0.5">
            Owner: {meta.owner.name}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {saved && (
            <span className="text-sm text-green-600">Saved</span>
          )}
          {saveError && (
            <span className="text-sm text-destructive">{saveError}</span>
          )}
          <Button variant="outline" onClick={() => navigate(`/parameters/${id}`)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      <div>
        <label className="text-sm font-medium">Version Notes</label>
        <textarea
          className="mt-1 w-full rounded border border-input bg-background px-3 py-2 text-sm"
          rows={2}
          placeholder="Describe what changed in this version..."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      <div className="space-y-4">
        {bodies.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">No bodies found</p>
        )}
        {bodies.map((body) => (
          <div key={body} className="border rounded-lg overflow-hidden">
            <div className="px-4 py-2 bg-muted/30 font-medium capitalize text-sm">
              {body}
            </div>
            <div className="px-4 py-3 grid grid-cols-4 gap-x-4 gap-y-2">
              {PARAM_FIELDS.map((field) => (
                <div key={field}>
                  <label className="text-xs text-muted-foreground">{field}</label>
                  <input
                    className="mt-0.5 w-full h-8 rounded border border-input bg-background px-2 text-sm font-mono"
                    value={values[body]?.[field] ?? ""}
                    onChange={(e) => handleChange(body, field, e.target.value)}
                  />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
