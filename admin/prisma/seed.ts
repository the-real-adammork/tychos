import { PrismaClient } from "../src/generated/prisma/client";
import bcrypt from "bcryptjs";
import { readFileSync } from "fs";
import { join } from "path";
import { createHash } from "crypto";

const prisma = new PrismaClient();

async function main() {
  // Create admin user
  const passwordHash = await bcrypt.hash("admin", 10);
  const user = await prisma.user.upsert({
    where: { email: "admin@tychos.local" },
    update: {},
    create: { email: "admin@tychos.local", name: "Admin", passwordHash },
  });

  // Import v1-original params
  const paramsPath = join(process.cwd(), "..", "params", "v1-original.json");
  const paramsJson = readFileSync(paramsPath, "utf-8");
  const parsed = JSON.parse(paramsJson);
  const canonical = JSON.stringify(parsed, Object.keys(parsed).sort());
  const md5 = createHash("md5").update(canonical).digest("hex");

  // Upsert by name: find existing or create
  const existing = await prisma.paramSet.findFirst({
    where: { name: "v1-original" },
  });

  if (!existing) {
    await prisma.paramSet.create({
      data: { name: "v1-original", paramsJson, paramsMd5: md5, ownerId: user.id },
    });
  }

  console.log("Seed complete: admin user + v1-original params");
}

main()
  .catch(console.error)
  .finally(() => prisma.$disconnect());
