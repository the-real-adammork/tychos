import { createHash } from "crypto";
import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import { getSessionUser } from "@/lib/auth";

export async function GET() {
  const paramSets = await prisma.paramSet.findMany({
    orderBy: { createdAt: "desc" },
    include: {
      owner: { select: { id: true, name: true } },
      forkedFrom: { select: { id: true, name: true } },
      runs: {
        where: { status: "done" },
        select: { testType: true, totalEclipses: true, detected: true },
      },
    },
  });

  return Response.json(paramSets);
}

export async function POST(request: NextRequest) {
  const user = await getSessionUser();
  if (!user) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json();
  const { name, description, paramsJson } = body ?? {};

  if (!name || !paramsJson) {
    return Response.json(
      { error: "name and paramsJson are required" },
      { status: 400 }
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(paramsJson);
  } catch {
    return Response.json({ error: "paramsJson is not valid JSON" }, { status: 400 });
  }

  const paramsMd5 = createHash("md5")
    .update(JSON.stringify(parsed, Object.keys(parsed as object).sort()))
    .digest("hex");

  const paramSet = await prisma.paramSet.create({
    data: {
      name,
      description: description ?? null,
      paramsJson,
      paramsMd5,
      ownerId: user.id,
    },
    include: {
      owner: { select: { id: true, name: true } },
      forkedFrom: { select: { id: true, name: true } },
    },
  });

  return Response.json(paramSet, { status: 201 });
}
