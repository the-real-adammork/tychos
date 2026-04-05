import { useState, useEffect } from "react";
import { StatsCards } from "@/components/dashboard/stats-cards";
import { RecentRuns } from "@/components/dashboard/recent-runs";
import { Leaderboard } from "@/components/dashboard/leaderboard";

interface DashboardData {
  total_param_sets: number;
  best_solar: { name: string; rate: number } | null;
  best_lunar: { name: string; rate: number } | null;
  recent_runs: Array<{
    id: number;
    test_type: string;
    status: string;
    total_eclipses: number | null;
    detected: number | null;
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

  useEffect(() => {
    fetch("/api/dashboard")
      .then((r) => r.json())
      .then(setData);
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

      <div className="grid grid-cols-2 gap-4">
        <RecentRuns
          runs={data.recent_runs.map((r) => ({
            id: r.id,
            testType: r.test_type,
            status: r.status,
            totalEclipses: r.total_eclipses,
            detected: r.detected,
            paramSet: { name: r.param_set_name },
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
