import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

const PAGE_SIZE = 50;

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> }
) {
  const { runId: runIdParam } = await params;
  const runId = parseInt(runIdParam, 10);

  if (isNaN(runId)) {
    return Response.json({ error: "Invalid runId" }, { status: 400 });
  }

  const { searchParams } = request.nextUrl;
  const pageParam = searchParams.get("page");
  const catalogType = searchParams.get("catalogType");
  const detectedParam = searchParams.get("detected");

  const page = pageParam ? Math.max(1, parseInt(pageParam, 10)) : 1;

  const where: Record<string, unknown> = { runId };
  if (catalogType) where.catalogType = catalogType;
  if (detectedParam !== null) {
    where.detected = detectedParam === "true";
  }

  const [results, total] = await prisma.$transaction([
    prisma.eclipseResult.findMany({
      where,
      orderBy: { julianDayTt: "asc" },
      skip: (page - 1) * PAGE_SIZE,
      take: PAGE_SIZE,
    }),
    prisma.eclipseResult.count({ where }),
  ]);

  return Response.json({ results, total, page, pageSize: PAGE_SIZE });
}
