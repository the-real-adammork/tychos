import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import { getSessionUser } from "@/lib/auth";

const paramSetInclude = {
  paramSet: {
    select: {
      id: true,
      name: true,
      owner: { select: { name: true } },
    },
  },
};

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const paramSetIdParam = searchParams.get("paramSetId");
  const status = searchParams.get("status");

  const where: Record<string, unknown> = {};
  if (paramSetIdParam) {
    const paramSetId = parseInt(paramSetIdParam, 10);
    if (!isNaN(paramSetId)) where.paramSetId = paramSetId;
  }
  if (status) where.status = status;

  const runs = await prisma.run.findMany({
    where,
    include: paramSetInclude,
    orderBy: { createdAt: "desc" },
    take: 100,
  });

  return Response.json(runs);
}

export async function POST(request: NextRequest) {
  const user = await getSessionUser();
  if (!user) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json();
  const { paramSetId, testType } = body ?? {};

  if (paramSetId === undefined || paramSetId === null || !testType) {
    return Response.json(
      { error: "paramSetId and testType are required" },
      { status: 400 }
    );
  }

  if (testType !== "solar" && testType !== "lunar") {
    return Response.json(
      { error: "testType must be \"solar\" or \"lunar\"" },
      { status: 400 }
    );
  }

  const paramSet = await prisma.paramSet.findUnique({
    where: { id: Number(paramSetId) },
  });
  if (!paramSet) {
    return Response.json({ error: "ParamSet not found" }, { status: 404 });
  }

  const run = await prisma.run.create({
    data: {
      paramSetId: Number(paramSetId),
      testType,
      status: "queued",
    },
    include: paramSetInclude,
  });

  return Response.json(run, { status: 201 });
}
