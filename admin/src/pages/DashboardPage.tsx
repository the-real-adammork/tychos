import { useState, useEffect } from "react";
import { StatsCards } from "@/components/dashboard/stats-cards";
import { RecentRuns } from "@/components/dashboard/recent-runs";
import { Leaderboard } from "@/components/dashboard/leaderboard";
import { DatasetSummary } from "@/components/dashboard/dataset-summary";

interface DatasetBreakdown {
  catalog_type: string;
  count: number;
}

interface DatasetSummaryData {
  total: number;
  breakdown: DatasetBreakdown[];
}

interface DashboardData {
  total_param_sets: number;
  best_solar: { name: string; rate: number } | null;
  best_lunar: { name: string; rate: number } | null;
  recent_runs: Array<{
    id: number;
    dataset_slug: string;
    dataset_name: string;
    status: string;
    total_eclipses: number | null;
    detected: number | null;
    overall_pass: number | null;
    version_number: number | null;
    param_set_name: string;
  }>;
  leaderboard: Array<{
    param_set_name: string;
    owner_name: string;
    avg_rate: number;
  }>;
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [datasetSummary, setDatasetSummary] = useState<Record<string, DatasetSummaryData> | null>(null);

  useEffect(() => {
    fetch("/api/dashboard")
      .then((r) => r.json())
      .then(setData);
    fetch("/api/datasets/summary")
      .then((r) => r.json())
      .then(setDatasetSummary);
  }, []);

  if (!data) return null;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      <StatsCards
        totalParamSets={data.total_param_sets}
        bestSolar={data.best_solar}
        bestLunar={data.best_lunar}
      />

      {datasetSummary && (
        <DatasetSummary datasets={datasetSummary} />
      )}

      <div className="grid grid-cols-2 gap-4">
        <RecentRuns
          runs={data.recent_runs.map((r) => ({
            id: r.id,
            datasetName: r.dataset_name,
            status: r.status,
            totalEclipses: r.total_eclipses,
            detected: r.overall_pass ?? r.detected,
            paramSet: { name: `${r.param_set_name} v${r.version_number}` },
          }))}
        />
        <Leaderboard
          entries={data.leaderboard.map((e) => ({
            paramSetName: e.param_set_name,
            ownerName: e.owner_name,
            avgRate: e.avg_rate,
          }))}
        />
      </div>
    </div>
  );
}
