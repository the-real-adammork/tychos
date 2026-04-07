import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface StatsCardsProps {
  totalParamSets: number;
  bestSolar: { name: string; mean_error: number } | null;
  bestLunar: { name: string; mean_error: number } | null;
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
          <CardTitle>Best Solar Error</CardTitle>
        </CardHeader>
        <CardContent>
          {bestSolar ? (
            <>
              <p className="text-4xl font-bold">
                {bestSolar.mean_error.toFixed(1)}'
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
          <CardTitle>Best Lunar Error</CardTitle>
        </CardHeader>
        <CardContent>
          {bestLunar ? (
            <>
              <p className="text-4xl font-bold">
                {bestLunar.mean_error.toFixed(1)}'
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
