import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface Dataset {
  id: number;
  slug: string;
  name: string;
  event_type: string;
  source_url: string | null;
  description: string | null;
  record_count: number;
}

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    fetch("/api/datasets")
      .then((r) => r.json())
      .then((d) => {
        setDatasets(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Datasets</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {datasets.map((ds) => (
          <Card
            key={ds.id}
            className="cursor-pointer transition-colors hover:bg-accent/50"
            onClick={() => navigate(`/datasets/${ds.slug}`)}
          >
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                {ds.name}
                <Badge variant="secondary" className="tabular-nums">
                  {ds.record_count} records
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {ds.description && (
                <p className="text-sm text-muted-foreground">{ds.description}</p>
              )}
              <div className="flex items-center gap-2">
                <Badge>{ds.event_type}</Badge>
                {ds.source_url && (
                  <a
                    href={ds.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-500 hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Source
                  </a>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
