import { createHash } from "crypto";
import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import { getSessionUser } from "@/lib/auth";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const paramSetId = parseInt(id, 10);

  const paramSet = await prisma.paramSet.findUnique({
    where: { id: paramSetId },
    include: {
      owner: { select: { id: true, name: true } },
      forkedFrom: { select: { id: true, name: true } },
    },
  });

  if (!paramSet) {
    return Response.json({ error: "Not found" }, { status: 404 });
  }

  return Response.json(paramSet);
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const user = await getSessionUser();
  if (!user) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  const paramSetId = parseInt(id, 10);

  const existing = await prisma.paramSet.findUnique({
    where: { id: paramSetId },
  });

  if (!existing) {
    return Response.json({ error: "Not found" }, { status: 404 });
  }

  if (existing.ownerId !== user.id) {
    return Response.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await request.json();
  const { name, description, paramsJson } = body ?? {};

  const updateData: {
    name?: string;
    description?: string | null;
    paramsJson?: string;
    paramsMd5?: string;
  } = {};

  if (name !== undefined) updateData.name = name;
  if (description !== undefined) updateData.description = description;

  if (paramsJson !== undefined) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(paramsJson);
    } catch {
      return Response.json({ error: "paramsJson is not valid JSON" }, { status: 400 });
    }

    updateData.paramsJson = paramsJson;
    updateData.paramsMd5 = createHash("md5")
      .update(JSON.stringify(parsed, Object.keys(parsed as object).sort()))
      .digest("hex");
  }

  const paramSet = await prisma.paramSet.update({
    where: { id: paramSetId },
    data: updateData,
    include: {
      owner: { select: { id: true, name: true } },
      forkedFrom: { select: { id: true, name: true } },
    },
  });

  return Response.json(paramSet);
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const user = await getSessionUser();
  if (!user) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  const paramSetId = parseInt(id, 10);

  const existing = await prisma.paramSet.findUnique({
    where: { id: paramSetId },
  });

  if (!existing) {
    return Response.json({ error: "Not found" }, { status: 404 });
  }

  if (existing.ownerId !== user.id) {
    return Response.json({ error: "Forbidden" }, { status: 403 });
  }

  await prisma.paramSet.delete({ where: { id: paramSetId } });

  return new Response(null, { status: 204 });
}
