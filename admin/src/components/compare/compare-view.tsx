import * as React from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ChangedEclipses } from "./changed-eclipses";
import { ParamDiff } from "./param-diff";

interface ParamSet {
  id: number;
  name: string;
  paramsJson: string;
  owner: { name: string };
}

interface CompareRun {
  id: number;
  paramSet: {
    name: string;
    paramsJson: string;
    owner: { name: string };
  };
  totalEclipses: number;
  meanTychosError: number | null;
}

interface ChangedEclipse {
  date: string;
  catalogType: string;
  aError: number | null;
  bError: number | null;
  aSep: number | null;
  bSep: number | null;
  errorDelta: number;
}

interface CompareResult {
  runA: CompareRun;
  runB: CompareRun;
  changed: ChangedEclipse[];
}

export default function CompareView() {
  const [paramSets, setParamSets] = React.useState<ParamSet[]>([]);
  const [aId, setAId] = React.useState<string>("");
  const [bId, setBId] = React.useState<string>("");
  const [datasetSlug, setDatasetSlug] = React.useState<string>("solar_eclipse");
  const [result, setResult] = React.useState<CompareResult | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    fetch("/api/params")
      .then((r) => r.json())
      .then((data: Record<string, unknown>[]) => {
        const mapped: ParamSet[] = data.map((ps) => ({
          id: ps.id as number,
          name: ps.name as string,
          paramsJson: (ps.params_json ?? ps.paramsJson) as string,
          owner: ps.owner as { name: string },
        }));
        setParamSets(mapped);
      })
      .catch(() => setError("Failed to load parameter sets"));
  }, []);

  React.useEffect(() => {
    if (!aId || !bId) {
      setResult(null);
      setError(null);
      return;
    }
    if (aId === bId) {
      setError("Select two different parameter sets to compare");
      setResult(null);
      return;
    }
    setLoading(true);
    setError(null);
    fetch(`/api/compare?a=${aId}&b=${bId}&dataset=${datasetSlug}`)
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) {
          setError(data.error ?? "Comparison failed");
          setResult(null);
        } else {
          function mapRun(run: Record<string, unknown>): CompareRun {
            return {
              id: run.id as number,
              paramSet: {
                name: run.param_set_name as string,
                paramsJson: run.params_json as string,
                owner: { name: "" },
              },
              totalEclipses: run.total_eclipses as number,
              meanTychosError: (run.mean_tychos_error as number | null) ?? null,
            };
          }
          function mapChanged(c: Record<string, unknown>): ChangedEclipse {
            return {
              date: c.date as string,
              catalogType: (c.catalog_type ?? c.catalogType) as string,
              aError: (c.a_error as number | null) ?? null,
              bError: (c.b_error as number | null) ?? null,
              aSep: (c.a_sep ?? c.aSep ?? null) as number | null,
              bSep: (c.b_sep ?? c.bSep ?? null) as number | null,
              errorDelta: c.error_delta as number,
            };
          }
          setResult({
            runA: mapRun(data.run_a ?? data.runA),
            runB: mapRun(data.run_b ?? data.runB),
            changed: ((data.changed ?? []) as Record<string, unknown>[]).map(mapChanged),
          });
        }
      })
      .catch(() => setError("Network error"))
      .finally(() => setLoading(false));
  }, [aId, bId, datasetSlug]);

  const errorA = result?.runA.meanTychosError ?? null;
  const errorB = result?.runB.meanTychosError ?? null;
  const delta = errorA != null && errorB != null ? errorB - errorA : null;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Select Versions</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-4 items-end">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Version A</label>
              <Select value={aId} onValueChange={(v) => setAId(v ?? "")}>
                <SelectTrigger className="w-52">
                  <SelectValue placeholder="Select param set" />
                </SelectTrigger>
                <SelectContent>
                  {paramSets.map((ps) => (
                    <SelectItem key={ps.id} value={String(ps.id)}>
                      {ps.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Version B</label>
              <Select value={bId} onValueChange={(v) => setBId(v ?? "")}>
                <SelectTrigger className="w-52">
                  <SelectValue placeholder="Select param set" />
                </SelectTrigger>
                <SelectContent>
                  {paramSets.map((ps) => (
                    <SelectItem key={ps.id} value={String(ps.id)}>
                      {ps.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Dataset</label>
              <Tabs
                value={datasetSlug}
                onValueChange={(v) => setDatasetSlug(v)}
              >
                <TabsList>
                  <TabsTrigger value="solar_eclipse">Solar</TabsTrigger>
                  <TabsTrigger value="lunar_eclipse">Lunar</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
          {loading && <p className="text-sm text-muted-foreground">Loading comparison…</p>}
        </CardContent>
      </Card>

      {result && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-3">
                Mean Error Comparison
                {delta != null && (
                  <Badge
                    className={
                      delta < 0
                        ? "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30"
                        : delta > 0
                        ? "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30"
                        : "bg-muted text-muted-foreground"
                    }
                  >
                    {delta > 0 ? "+" : ""}
                    {delta.toFixed(2)}'
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">
                      A: {result.runA.paramSet.name}
                    </span>
                    <span className="text-sm text-muted-foreground tabular-nums">
                      {errorA != null ? `${errorA.toFixed(1)}'` : "—"}
                    </span>
                  </div>
                </div>

                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">
                      B: {result.runB.paramSet.name}
                    </span>
                    <span className="text-sm text-muted-foreground tabular-nums">
                      {errorB != null ? `${errorB.toFixed(1)}'` : "—"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="text-sm text-muted-foreground">
                A: {result.runA.totalEclipses} eclipses · B: {result.runB.totalEclipses} eclipses
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>
                Changed Eclipses
                {result.changed.length > 0 && (
                  <Badge variant="secondary" className="ml-2">
                    {result.changed.length}
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ChangedEclipses changed={result.changed} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Parameter Diff</CardTitle>
            </CardHeader>
            <CardContent>
              <ParamDiff
                paramsJsonA={result.runA.paramSet.paramsJson}
                paramsJsonB={result.runB.paramSet.paramsJson}
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
