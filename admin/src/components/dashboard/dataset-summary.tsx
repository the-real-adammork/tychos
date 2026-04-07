import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface DatasetBreakdown {
  catalog_type: string;
  count: number;
}

interface DatasetSummaryData {
  total: number;
  breakdown: DatasetBreakdown[];
}

interface DatasetSummaryProps {
  datasets: Record<string, DatasetSummaryData>;
}

const DISPLAY_NAMES: Record<string, string> = {
  solar_eclipse: "Solar Eclipses",
  lunar_eclipse: "Lunar Eclipses",
};

function DatasetCard({
  slug,
  title,
  data,
}: {
  slug: string;
  title: string;
  data: DatasetSummaryData;
}) {
  const navigate = useNavigate();

  return (
    <Card
      className="cursor-pointer transition-colors hover:bg-accent/50"
      onClick={() => navigate(`/datasets/${slug}`)}
    >
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          {title}
          <span className="text-2xl font-bold tabular-nums">{data.total}</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {data.breakdown.map((b) => (
            <Badge key={b.catalog_type} variant="secondary" className="tabular-nums">
              {b.catalog_type}: {b.count}
            </Badge>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export function DatasetSummary({ datasets }: DatasetSummaryProps) {
  const entries = Object.entries(datasets);
  if (entries.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-4">
      {entries.map(([slug, data]) => (
        <DatasetCard
          key={slug}
          slug={slug}
          title={DISPLAY_NAMES[slug] ?? slug}
          data={data}
        />
      ))}
    </div>
  );
}
