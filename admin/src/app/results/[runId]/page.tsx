import { redirect } from "next/navigation";
import { prisma } from "@/lib/db";
import { getSessionUser } from "@/lib/auth";
import { ResultsTable } from "@/components/results/results-table";

export const dynamic = "force-dynamic";

export default async function ResultsPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const user = await getSessionUser();
  if (!user) {
    redirect("/login");
  }

  const { runId } = await params;
  const runIdNum = parseInt(runId, 10);

  if (isNaN(runIdNum)) {
    redirect("/");
  }

  const run = await prisma.run.findUnique({
    where: { id: runIdNum },
    include: {
      paramSet: {
        select: { id: true, name: true },
      },
    },
  });

  if (!run) {
    redirect("/");
  }

  const detectionRate =
    run.detected !== null && run.totalEclipses
      ? ((run.detected / run.totalEclipses) * 100).toFixed(1) + "%"
      : "—";

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">
          Results: {run.paramSet.name}
        </h1>
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span>
            Test type:{" "}
            <span className="font-medium capitalize text-foreground">
              {run.testType}
            </span>
          </span>
          <span>
            Status:{" "}
            <span className="font-medium capitalize text-foreground">
              {run.status}
            </span>
          </span>
          <span>
            Detection rate:{" "}
            <span className="font-medium text-foreground">{detectionRate}</span>
          </span>
          {run.totalEclipses !== null && (
            <span>
              Total eclipses:{" "}
              <span className="font-medium text-foreground">
                {run.totalEclipses}
              </span>
            </span>
          )}
        </div>
      </div>

      <ResultsTable runId={runId} />
    </div>
  );
}
