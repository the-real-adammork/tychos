import { useState, useEffect } from "react";
import { useParams, useNavigate, Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ResultsTable } from "@/components/results/results-table";

interface RunInfo {
  id: number;
  datasetSlug: string;
  datasetName: string;
  status: string;
  totalEclipses: number | null;
  paramSetId: number;
  paramSetName: string;
  versionNumber: number;
  paramVersionId: number;
}

interface RunStats {
  total: number;
  mean_tychos_error: number | null;
  mean_jpl_error: number | null;
  median_tychos_error: number | null;
  median_jpl_error: number | null;
  max_tychos_error: number | null;
  max_jpl_error: number | null;
  mean_sun_diff: number | null;
  mean_moon_diff: number | null;
  mean_timing_offset: number | null;
}

export default function ResultsPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = useState<RunInfo | null>(null);
  const [stats, setStats] = useState<RunStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    // Fetch run info and first page of results (for stats)
    Promise.all([
      fetch(`/api/runs/${runId}`).then((r) => (r.ok ? r.json() : null)),
      fetch(`/api/results/${runId}?page=1`).then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([runData, resultsData]) => {
        if (!runData) {
          setNotFound(true);
          return;
        }
        setRun({
          id: runData.id,
          datasetSlug: runData.dataset_slug,
          datasetName: runData.dataset_name,
          status: runData.status,
          totalEclipses: runData.total_eclipses,
          paramSetId: runData.param_set_id,
          paramSetName: runData.param_set_name,
          versionNumber: runData.version_number,
          paramVersionId: runData.param_version_id,
        });
        if (resultsData?.stats) {
          setStats(resultsData.stats);
        }
      })
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) return null;
  if (notFound || !run) return <Navigate to="/" />;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold">
            {run.paramSetName} — v{run.versionNumber}
          </h1>
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span>
              Dataset:{" "}
              <span className="font-medium capitalize text-foreground">
                {run.datasetName}
              </span>
            </span>
            <span>
              Status:{" "}
              <span className="font-medium capitalize text-foreground">
                {run.status}
              </span>
            </span>
            {stats && stats.mean_sun_diff != null && (
              <span>
                Sun diff:{" "}
                <span className="font-medium text-foreground">
                  {stats.mean_sun_diff.toFixed(1)}'
                </span>
              </span>
            )}
            {stats && stats.mean_moon_diff != null && (
              <span>
                Moon diff:{" "}
                <span className="font-medium text-foreground">
                  {stats.mean_moon_diff.toFixed(1)}'
                </span>
              </span>
            )}
            {stats && stats.mean_timing_offset != null && (
              <span>
                Timing offset:{" "}
                <span className="font-medium text-foreground">
                  {stats.mean_timing_offset.toFixed(1)} min
                </span>
              </span>
            )}
            {run.totalEclipses !== null && (
              <span>
                Total eclipses:{" "}
                <span className="font-medium text-foreground">
                  {run.totalEclipses}
                </span>
              </span>
            )}
          </div>
        </div>
        <Button
          variant="outline"
          onClick={() => navigate(`/parameters/${run.paramSetId}/versions/${run.paramVersionId}`)}
        >
          View Version Detail
        </Button>
      </div>

      <ResultsTable runId={runId!} />
    </div>
  );
}
