import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface LeaderboardProps {
  entries: Array<{
    paramSetName: string;
    ownerName: string;
    avgRate: number;
  }>;
}

export function Leaderboard({ entries }: LeaderboardProps) {
  const sorted = [...entries].sort((a, b) => b.avgRate - a.avgRate);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Leaderboard</CardTitle>
      </CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <p className="text-muted-foreground text-sm">No completed runs yet</p>
        ) : (
          <ul className="space-y-2">
            {sorted.map((entry, i) => (
              <li key={i} className="flex items-center justify-between">
                <span className="text-sm">
                  {entry.paramSetName}{" "}
                  <span className="text-muted-foreground">
                    by {entry.ownerName}
                  </span>
                </span>
                <span className="text-sm font-medium tabular-nums">
                  {(entry.avgRate * 100).toFixed(1)}%
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
