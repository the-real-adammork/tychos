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
  detected: number;
}

interface ChangedEclipse {
  date: string;
  catalogType: string;
  aDetected: boolean;
  bDetected: boolean;
  aSep: number | null;
  bSep: number | null;
}

interface CompareResult {
  runA: CompareRun;
  runB: CompareRun;
  changed: ChangedEclipse[];
}

function DetectionBar({ detected, total }: { detected: number; total: number }) {
  const pct = total > 0 ? (detected / total) * 100 : 0;
  return (
    <div className="flex flex-col gap-1">
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${pct.toFixed(1)}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground">
        {detected} / {total} ({pct.toFixed(1)}%)
      </span>
    </div>
  );
}

export default function CompareView() {
  const [paramSets, setParamSets] = React.useState<ParamSet[]>([]);
  const [aId, setAId] = React.useState<string>("");
  const [bId, setBId] = React.useState<string>("");
  const [datasetSlug, setDatasetSlug] = React.useState<string>("solar_eclipse");
  const [result, setResult] = React.useState<CompareResult | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Fetch param sets on mount
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

  // Fetch comparison when all selections are made
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
            const ps = run.param_set as Record<string, unknown> | undefined;
            return {
              id: run.id as number,
              paramSet: {
                name: (ps?.name ?? run.param_set_name) as string,
                paramsJson: (ps?.params_json ?? ps?.paramsJson ?? run.params_json) as string,
                owner: (ps?.owner ?? { name: "" }) as { name: string },
              },
              totalEclipses: (run.total_eclipses ?? run.totalEclipses) as number,
              detected: run.detected as number,
            };
          }
          function mapChanged(c: Record<string, unknown>): ChangedEclipse {
            return {
              date: c.date as string,
              catalogType: (c.catalog_type ?? c.catalogType) as string,
              aDetected: (c.a_detected ?? c.aDetected) as boolean,
              bDetected: (c.b_detected ?? c.bDetected) as boolean,
              aSep: (c.a_sep ?? c.aSep ?? null) as number | null,
              bSep: (c.b_sep ?? c.bSep ?? null) as number | null,
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

  const rateA =
    result && result.runA.totalEclipses > 0
      ? (result.runA.detected / result.runA.totalEclipses) * 100
      : null;
  const rateB =
    result && result.runB.totalEclipses > 0
      ? (result.runB.detected / result.runB.totalEclipses) * 100
      : null;
  const delta =
    rateA != null && rateB != null ? rateB - rateA : null;

  return (
    <div className="flex flex-col gap-6">
      {/* Selectors */}
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

      {/* Detection Rate Comparison */}
      {result && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-3">
                Detection Rate Comparison
                {delta != null && (
                  <Badge
                    className={
                      delta > 0
                        ? "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30"
                        : delta < 0
                        ? ""
                        : "bg-muted text-muted-foreground"
                    }
                    variant={delta < 0 ? "destructive" : "outline"}
                  >
                    {delta > 0 ? "+" : ""}
                    {delta.toFixed(2)}%
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
                    <span className="text-sm text-muted-foreground">
                      {rateA?.toFixed(1)}%
                    </span>
                  </div>
                  <DetectionBar
                    detected={result.runA.detected}
                    total={result.runA.totalEclipses}
                  />
                </div>

                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">
                      B: {result.runB.paramSet.name}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      {rateB?.toFixed(1)}%
                    </span>
                  </div>
                  <DetectionBar
                    detected={result.runB.detected}
                    total={result.runB.totalEclipses}
                  />
                </div>
              </div>

              <div className="text-sm text-muted-foreground">
                A: {result.runA.detected} detected of {result.runA.totalEclipses} eclipses
                {" · "}
                B: {result.runB.detected} detected of {result.runB.totalEclipses} eclipses
              </div>
            </CardContent>
          </Card>

          {/* Changed Eclipses */}
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

          {/* Parameter Diff */}
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
