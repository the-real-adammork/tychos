import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export interface SarosNeighbor {
  id: number;
  date: string;
  catalog_type: string;
  position: number;
  is_self: boolean;
  tychos_error_arcmin?: number | null;
  jpl_error_arcmin?: number | null;
}

interface SarosContextProps {
  sarosNum: number | null;
  sarosPosition: number | null;
  sarosTotal: number | null;
  yearStart: string | null;
  yearEnd: string | null;
  neighbors: SarosNeighbor[];
  /** Click handler for an individual neighbor */
  onNeighborClick: (neighborId: number) => void;
  /** Click handler for "view full series" */
  onViewFullSeries: (sarosNum: number) => void;
  /** Whether to show error columns (only for run results) */
  showErrors?: boolean;
}

export function SarosContext({
  sarosNum,
  sarosPosition,
  sarosTotal,
  yearStart,
  yearEnd,
  neighbors,
  onNeighborClick,
  onViewFullSeries,
  showErrors = false,
}: SarosContextProps) {
  if (sarosNum == null) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground flex items-center justify-between">
          <span>Saros {sarosNum}</span>
          <Button
            variant="ghost"
            size="sm"
            className="text-xs h-7"
            onClick={() => onViewFullSeries(sarosNum)}
          >
            View full series →
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="text-sm space-y-1">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Position in series</span>
            <span className="font-mono">
              {sarosPosition} of {sarosTotal}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Year span</span>
            <span className="font-mono">
              {yearStart}–{yearEnd}
            </span>
          </div>
        </div>

        <div className="border-t pt-3">
          <h4 className="text-xs font-medium text-muted-foreground uppercase mb-2">Neighbors</h4>
          <div className="space-y-1">
            {neighbors.map((n) => (
              <div
                key={n.id}
                onClick={() => !n.is_self && onNeighborClick(n.id)}
                className={`flex items-center justify-between text-xs px-2 py-1 rounded ${
                  n.is_self
                    ? "bg-blue-500/10 text-blue-700 dark:text-blue-400 font-medium"
                    : "cursor-pointer hover:bg-muted/50"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono text-muted-foreground w-8">#{n.position}</span>
                  <span className="font-mono">{n.date.split("T")[0]}</span>
                  <span className="capitalize text-muted-foreground">{n.catalog_type}</span>
                </div>
                {showErrors && n.tychos_error_arcmin != null && (
                  <span className="font-mono text-muted-foreground">
                    {n.tychos_error_arcmin.toFixed(1)}'
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
