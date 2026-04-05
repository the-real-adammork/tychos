import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import { getSessionUser } from "@/lib/auth";

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const user = await getSessionUser();
  if (!user) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  const sourceId = parseInt(id, 10);

  const source = await prisma.paramSet.findUnique({
    where: { id: sourceId },
  });

  if (!source) {
    return Response.json({ error: "Not found" }, { status: 404 });
  }

  const forked = await prisma.paramSet.create({
    data: {
      name: `${source.name} (fork)`,
      description: source.description,
      paramsJson: source.paramsJson,
      paramsMd5: source.paramsMd5,
      ownerId: user.id,
      forkedFromId: source.id,
    },
    include: {
      owner: { select: { id: true, name: true } },
      forkedFrom: { select: { id: true, name: true } },
    },
  });

  return Response.json(forked, { status: 201 });
}
