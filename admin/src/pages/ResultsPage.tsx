import { useState, useEffect } from "react";
import { useParams, useNavigate, Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ResultsTable } from "@/components/results/results-table";

interface RunInfo {
  id: number;
  testType: string;
  status: string;
  totalEclipses: number | null;
  detected: number | null;
  paramSetId: number;
  paramSetName: string;
  versionNumber: number;
  paramVersionId: number;
}

export default function ResultsPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = useState<RunInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    fetch(`/api/runs/${runId}`)
      .then((r) => {
        if (!r.ok) {
          setNotFound(true);
          return null;
        }
        return r.json();
      })
      .then((data) => {
        if (data) {
          setRun({
            id: data.id,
            testType: data.test_type,
            status: data.status,
            totalEclipses: data.total_eclipses,
            detected: data.detected,
            paramSetId: data.param_set_id,
            paramSetName: data.param_set_name,
            versionNumber: data.version_number,
            paramVersionId: data.param_version_id,
          });
        }
      })
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) return null;
  if (notFound || !run) return <Navigate to="/" />;

  const detectionRate =
    run.detected !== null && run.totalEclipses
      ? ((run.detected / run.totalEclipses) * 100).toFixed(1) + "%"
      : "\u2014";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold">
            {run.paramSetName} — v{run.versionNumber}
          </h1>
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span>
              Test type:{" "}
              <span className="font-medium capitalize text-foreground">
                {run.testType}
              </span>
            </span>
            <span>
              Status:{" "}
              <span className="font-medium capitalize text-foreground">
                {run.status}
              </span>
            </span>
            <span>
              Detection rate:{" "}
              <span className="font-medium text-foreground">{detectionRate}</span>
            </span>
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
