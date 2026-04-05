import { useState, useEffect } from "react";
import { StatsCards } from "@/components/dashboard/stats-cards";
import { RecentRuns } from "@/components/dashboard/recent-runs";
import { Leaderboard } from "@/components/dashboard/leaderboard";

interface DashboardData {
  totalParamSets: number;
  bestSolar: { name: string; rate: number } | null;
  bestLunar: { name: string; rate: number } | null;
  recentRuns: Array<{
    id: number;
    testType: string;
    status: string;
    totalEclipses: number | null;
    detected: number | null;
    paramSet: { name: string };
  }>;
  leaderboard: Array<{
    paramSetName: string;
    ownerName: string;
    avgRate: number;
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
        totalParamSets={data.totalParamSets}
        bestSolar={data.bestSolar}
        bestLunar={data.bestLunar}
      />

      <div className="grid grid-cols-2 gap-4">
        <RecentRuns runs={data.recentRuns} />
        <Leaderboard entries={data.leaderboard} />
      </div>
    </div>
  );
}
