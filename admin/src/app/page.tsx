import { redirect } from "next/navigation";

import { prisma } from "@/lib/db";
import { getSessionUser } from "@/lib/auth";
import { StatsCards } from "@/components/dashboard/stats-cards";
import { RecentRuns } from "@/components/dashboard/recent-runs";
import { Leaderboard } from "@/components/dashboard/leaderboard";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const user = await getSessionUser();
  if (!user) {
    redirect("/login");
  }

  const [totalParamSets, bestSolarRun, bestLunarRun, recentRuns, doneRuns] =
    await Promise.all([
      prisma.paramSet.count(),

      prisma.run.findFirst({
        where: { status: "done", testType: "solar", detected: { not: null } },
        orderBy: { detected: "desc" },
        include: { paramSet: true },
      }),

      prisma.run.findFirst({
        where: { status: "done", testType: "lunar", detected: { not: null } },
        orderBy: { detected: "desc" },
        include: { paramSet: true },
      }),

      prisma.run.findMany({
        orderBy: { createdAt: "desc" },
        take: 10,
        select: {
          id: true,
          testType: true,
          status: true,
          totalEclipses: true,
          detected: true,
          paramSet: { select: { name: true } },
        },
      }),

      prisma.run.findMany({
        where: {
          status: "done",
          detected: { not: null },
          totalEclipses: { not: null },
        },
        include: { paramSet: { include: { owner: true } } },
      }),
    ]);

  const bestSolar =
    bestSolarRun && bestSolarRun.detected !== null && bestSolarRun.totalEclipses
      ? {
          name: bestSolarRun.paramSet.name,
          rate: bestSolarRun.detected / bestSolarRun.totalEclipses,
        }
      : null;

  const bestLunar =
    bestLunarRun && bestLunarRun.detected !== null && bestLunarRun.totalEclipses
      ? {
          name: bestLunarRun.paramSet.name,
          rate: bestLunarRun.detected / bestLunarRun.totalEclipses,
        }
      : null;

  // Group done runs by paramSet name, compute average detection rate
  const ratesByParamSet = new Map<
    string,
    { ownerName: string; rates: number[] }
  >();
  for (const run of doneRuns) {
    if (run.detected === null || run.totalEclipses === null) continue;
    const key = run.paramSet.name;
    if (!ratesByParamSet.has(key)) {
      ratesByParamSet.set(key, {
        ownerName: run.paramSet.owner.name,
        rates: [],
      });
    }
    ratesByParamSet
      .get(key)!
      .rates.push(run.detected / run.totalEclipses);
  }

  const leaderboardEntries = Array.from(ratesByParamSet.entries()).map(
    ([paramSetName, { ownerName, rates }]) => ({
      paramSetName,
      ownerName,
      avgRate: rates.reduce((a, b) => a + b, 0) / rates.length,
    })
  );

  return (
    <div className="flex flex-col gap-6 p-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      <StatsCards
        totalParamSets={totalParamSets}
        bestSolar={bestSolar}
        bestLunar={bestLunar}
      />

      <div className="grid grid-cols-2 gap-4">
        <RecentRuns runs={recentRuns} />
        <Leaderboard entries={leaderboardEntries} />
      </div>
    </div>
  );
}
