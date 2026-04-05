import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const aParam = searchParams.get("a");
  const bParam = searchParams.get("b");
  const type = searchParams.get("type") ?? "solar";

  if (!aParam || !bParam) {
    return Response.json(
      { error: "Query params 'a' and 'b' (paramSetId) are required" },
      { status: 400 }
    );
  }

  if (type !== "solar" && type !== "lunar") {
    return Response.json(
      { error: "type must be \"solar\" or \"lunar\"" },
      { status: 400 }
    );
  }

  const aId = parseInt(aParam, 10);
  const bId = parseInt(bParam, 10);

  if (isNaN(aId) || isNaN(bId)) {
    return Response.json({ error: "Invalid paramSetId" }, { status: 400 });
  }

  // Find the latest done run for each paramSet+testType
  const [runA, runB] = await Promise.all([
    prisma.run.findFirst({
      where: { paramSetId: aId, testType: type, status: "done" },
      orderBy: { createdAt: "desc" },
      include: {
        paramSet: {
          select: {
            name: true,
            paramsJson: true,
            owner: { select: { name: true } },
          },
        },
      },
    }),
    prisma.run.findFirst({
      where: { paramSetId: bId, testType: type, status: "done" },
      orderBy: { createdAt: "desc" },
      include: {
        paramSet: {
          select: {
            name: true,
            paramsJson: true,
            owner: { select: { name: true } },
          },
        },
      },
    }),
  ]);

  if (!runA || !runB) {
    return Response.json(
      {
        error: "One or both param sets have no completed run for the given type",
      },
      { status: 404 }
    );
  }

  // Fetch all eclipse results for both runs
  const [resultsA, resultsB] = await Promise.all([
    prisma.eclipseResult.findMany({
      where: { runId: runA.id },
      orderBy: { julianDayTt: "asc" },
    }),
    prisma.eclipseResult.findMany({
      where: { runId: runB.id },
      orderBy: { julianDayTt: "asc" },
    }),
  ]);

  // Index B results by julianDayTt for fast lookup
  const bByJd = new Map(resultsB.map((r) => [r.julianDayTt, r]));

  // Find changed eclipses: same julianDayTt but differing detected status
  const changed = resultsA
    .filter((rA) => {
      const rB = bByJd.get(rA.julianDayTt);
      return rB !== undefined && rA.detected !== rB.detected;
    })
    .map((rA) => {
      const rB = bByJd.get(rA.julianDayTt)!;
      return {
        date: rA.date,
        catalogType: rA.catalogType,
        aDetected: rA.detected,
        bDetected: rB.detected,
        aSep: rA.minSeparationArcmin,
        bSep: rB.minSeparationArcmin,
      };
    });

  return Response.json({
    runA: {
      id: runA.id,
      paramSet: runA.paramSet,
      totalEclipses: runA.totalEclipses,
      detected: runA.detected,
    },
    runB: {
      id: runB.id,
      paramSet: runB.paramSet,
      totalEclipses: runB.totalEclipses,
      detected: runB.detected,
    },
    changed,
  });
}
