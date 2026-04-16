import { ParamDiff } from "./param-diff";
import { RunCard } from "./run-card";

interface SearchResultCardProps {
  startingObjective: number;
  bestObjective: number;
  nEvals: number;
  improved: boolean;
  winnerVersionId: number | null;
  winnerRunId: number | null;
  prevParams?: Record<string, Record<string, number>>;
  winnerParams?: Record<string, Record<string, number>>;
  prevLabel?: string;
  nextLabel?: string;
}

export function SearchResultCard({
  startingObjective,
  bestObjective,
  nEvals,
  improved,
  winnerVersionId,
  winnerRunId,
  prevParams,
  winnerParams,
  prevLabel = "",
  nextLabel = "",
}: SearchResultCardProps) {
  const delta = bestObjective - startingObjective;

  return (
    <div className="bg-muted/50 border border-purple-500/20 rounded-md p-3 mt-1">
      <div className="flex items-center gap-2.5 mb-2">
        <span className="text-purple-400 text-xs font-semibold">Search complete</span>
        <span className="text-muted-foreground text-xs">{nEvals} evals</span>
      </div>
      <div className="flex gap-4 text-xs mb-2">
        <div><span className="text-muted-foreground">start:</span>{" "}
          <span className="text-yellow-400">{startingObjective.toFixed(2)}</span></div>
        <div><span className="text-muted-foreground">best:</span>{" "}
          <span className={improved ? "text-green-400 font-semibold" : "text-muted-foreground"}>
            {bestObjective.toFixed(2)}
          </span></div>
        <div><span className="text-muted-foreground">Δ:</span>{" "}
          <span className={improved ? "text-green-400" : "text-muted-foreground"}>
            {delta.toFixed(2)} {improved ? "✓" : "(no improvement)"}
          </span></div>
      </div>
      {improved && prevParams && winnerParams && (
        <ParamDiff
          prevLabel={prevLabel}
          nextLabel={nextLabel}
          prev={prevParams}
          next={winnerParams}
        />
      )}
      {improved && winnerRunId && (
        <RunCard
          runId={winnerRunId}
          objective={bestObjective}
          nScored={null}
          prevObjective={startingObjective}
        />
      )}
    </div>
  );
}
