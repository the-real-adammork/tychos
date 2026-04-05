import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const runId = parseInt(id, 10);

  if (isNaN(runId)) {
    return Response.json({ error: "Invalid run id" }, { status: 400 });
  }

  const run = await prisma.run.findUnique({
    where: { id: runId },
    include: {
      paramSet: {
        select: {
          id: true,
          name: true,
          owner: { select: { name: true } },
        },
      },
    },
  });

  if (!run) {
    return Response.json({ error: "Run not found" }, { status: 404 });
  }

  return Response.json(run);
}
