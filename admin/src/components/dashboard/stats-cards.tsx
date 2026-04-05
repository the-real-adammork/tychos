import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface StatsCardsProps {
  totalParamSets: number;
  bestSolar: { name: string; rate: number } | null;
  bestLunar: { name: string; rate: number } | null;
}

export function StatsCards({
  totalParamSets,
  bestSolar,
  bestLunar,
}: StatsCardsProps) {
  return (
    <div className="grid grid-cols-3 gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Parameter Versions</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-4xl font-bold">{totalParamSets}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Best Solar Detection</CardTitle>
        </CardHeader>
        <CardContent>
          {bestSolar ? (
            <>
              <p className="text-4xl font-bold text-teal-400">
                {(bestSolar.rate * 100).toFixed(1)}%
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                {bestSolar.name}
              </p>
            </>
          ) : (
            <p className="text-muted-foreground">No runs yet</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Best Lunar Detection</CardTitle>
        </CardHeader>
        <CardContent>
          {bestLunar ? (
            <>
              <p className="text-4xl font-bold text-teal-400">
                {(bestLunar.rate * 100).toFixed(1)}%
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                {bestLunar.name}
              </p>
            </>
          ) : (
            <p className="text-muted-foreground">No runs yet</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
