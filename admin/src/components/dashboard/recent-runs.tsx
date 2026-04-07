import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface RecentRunsProps {
  runs: Array<{
    id: number;
    datasetName: string;
    status: string;
    totalEclipses: number | null;
    detected: number | null;
    paramSet: { name: string };
  }>;
}

export function RecentRuns({ runs }: RecentRunsProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Runs</CardTitle>
      </CardHeader>
      <CardContent>
        {runs.length === 0 ? (
          <p className="text-muted-foreground text-sm">No runs yet</p>
        ) : (
          <ul className="space-y-2">
            {runs.map((run) => (
              <li key={run.id} className="flex items-center justify-between">
                <span className="text-sm">
                  {run.paramSet.name} / {run.datasetName}
                </span>
                <span className="text-sm">
                  {run.status === "done" &&
                  run.detected !== null &&
                  run.totalEclipses !== null ? (
                    <span className="tabular-nums">
                      {run.detected}/{run.totalEclipses}
                    </span>
                  ) : (
                    <Badge
                      variant={
                        run.status === "error" ? "destructive" : "secondary"
                      }
                    >
                      {run.status}
                    </Badge>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
