import { PrismaClient } from "@/generated/prisma/client";
import { join } from "path";

const DB_PATH = join(process.cwd(), "..", "results", "tychos_results.db");
const DB_URL = `file:${DB_PATH}`;

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient({
  datasourceUrl: DB_URL,
});

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
