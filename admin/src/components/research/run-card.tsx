import { Link } from "react-router-dom";

interface RunCardProps {
  runId: number;
  objective: number | null;
  nScored: number | null;
  status?: string;
  prevObjective?: number | null;
}

export function RunCard({ runId, objective, nScored, status = "done", prevObjective }: RunCardProps) {
  const improved = prevObjective != null && objective != null && objective < prevObjective;
  const worsened = prevObjective != null && objective != null && objective > prevObjective;

  return (
    <Link
      to={`/results/${runId}`}
      onClick={(e) => e.stopPropagation()}
      className="flex items-center gap-2.5 bg-muted/50 border border-border rounded-md px-3 py-2 mt-1 hover:border-ring transition-colors"
    >
      <div className={`w-2 h-2 rounded-full shrink-0 ${
        status === "done" ? "bg-green-500" :
        status === "running" ? "bg-yellow-500 animate-pulse" :
        status === "failed" ? "bg-red-500" : "bg-gray-500"
      }`} />
      <span className="text-xs text-muted-foreground">Run #{runId}</span>
      {nScored != null && (
        <span className="text-xs text-muted-foreground">{nScored} eclipses</span>
      )}
      <div className="flex-1" />
      {objective != null && (
        <span className={`text-xs font-semibold ${
          improved ? "text-green-400" : worsened ? "text-red-400" : "text-yellow-400"
        }`}>
          obj: {objective.toFixed(2)}
          {improved && " ↓"}
          {worsened && " ↑"}
        </span>
      )}
      <span className="text-muted-foreground text-xs">→</span>
    </Link>
  );
}
