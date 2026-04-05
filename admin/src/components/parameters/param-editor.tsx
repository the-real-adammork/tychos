import * as React from "react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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
  owner: { id: number; name: string };
}

interface ParamEditorProps {
  id: string;
}

export function ParamEditor({ id }: ParamEditorProps) {
  const [meta, setMeta] = React.useState<ParamSetMeta | null>(null);
  const [values, setValues] = React.useState<ParamsData>({});
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState(false);

  React.useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/params/${id}`);
        if (!res.ok) {
          setError(res.status === 404 ? "Parameter set not found" : "Failed to load");
          return;
        }
        const raw = await res.json();
        const data: ParamSetMeta = {
          id: raw.id,
          name: raw.name,
          description: raw.description,
          paramsJson: raw.params_json,
          owner: { id: raw.owner_id, name: raw.owner_name },
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
          setError("paramsJson is not valid JSON");
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
        body: JSON.stringify({ params_json: paramsJson }),
      });
      if (!res.ok) {
        const data = await res.json();
        setSaveError(data.error ?? "Failed to save");
        return;
      }
      setSaved(true);
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
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="sticky left-0 bg-background">Body</TableHead>
              {PARAM_FIELDS.map((f) => (
                <TableHead key={f} className="whitespace-nowrap text-xs">
                  {f}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {bodies.length === 0 && (
              <TableRow>
                <TableCell colSpan={PARAM_FIELDS.length + 1} className="text-center text-muted-foreground">
                  No bodies found in paramsJson
                </TableCell>
              </TableRow>
            )}
            {bodies.map((body) => (
              <TableRow key={body}>
                <TableCell className="sticky left-0 bg-background font-medium capitalize">
                  {body}
                </TableCell>
                {PARAM_FIELDS.map((field) => (
                  <TableCell key={field} className="p-1">
                    <input
                      className="h-7 w-24 rounded border border-input bg-background px-2 text-xs font-mono"
                      value={values[body]?.[field] ?? ""}
                      onChange={(e) => handleChange(body, field, e.target.value)}
                    />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
