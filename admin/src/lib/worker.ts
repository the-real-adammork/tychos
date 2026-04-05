import { spawn } from "child_process";
import { writeFileSync, unlinkSync, mkdtempSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";
import { PrismaClient } from "@/generated/prisma/client";

const REPO_ROOT = join(process.cwd(), "..");
const DB_PATH = join(process.cwd(), "..", "results", "tychos_results.db");
const DB_URL = `file:${DB_PATH}`;

let running = false;

async function poll() {
  if (running) return;

  const prisma = new PrismaClient({
    datasourceUrl: DB_URL,
  });
  try {
    // Find the oldest queued run
    const run = await prisma.run.findFirst({
      where: { status: "queued" },
      orderBy: { createdAt: "asc" },
      include: { paramSet: true },
    });

    if (!run) return;

    running = true;

    // Mark as running
    await prisma.run.update({
      where: { id: run.id },
      data: { status: "running", startedAt: new Date() },
    });

    // Write params to a temp file
    const tmpDir = mkdtempSync(join(tmpdir(), "tychos-run-"));
    const paramsFile = join(tmpDir, "params.json");
    writeFileSync(paramsFile, run.paramSet.paramsJson, "utf-8");

    const scriptPath = join(REPO_ROOT, "tests", "run_eclipses.py");
    const venvPython = join(REPO_ROOT, "tychos_skyfield", ".venv", "bin", "python3");

    await new Promise<void>((resolve) => {
      const child = spawn(
        venvPython,
        [
          scriptPath,
          paramsFile,
          "--db",
          DB_PATH,
          "--run-id",
          String(run.id),
          "--test-type",
          run.testType,
          "--force",
        ],
        {
          env: {
            ...process.env,
            PYTHONPATH:
              join(REPO_ROOT, "tychos_skyfield") +
              ":" +
              join(REPO_ROOT, "tests"),
          },
        }
      );

      let stderr = "";
      child.stderr.on("data", (chunk: Buffer) => {
        stderr += chunk.toString();
      });

      child.on("close", async (code) => {
        // Clean up temp file
        try {
          unlinkSync(paramsFile);
        } catch {
          // ignore
        }

        const completedAt = new Date();

        if (code === 0) {
          const totalEclipses = await prisma.eclipseResult.count({
            where: { runId: run.id },
          });
          const detected = await prisma.eclipseResult.count({
            where: { runId: run.id, detected: true },
          });
          await prisma.run.update({
            where: { id: run.id },
            data: {
              status: "done",
              totalEclipses,
              detected,
              completedAt,
            },
          });
        } else {
          await prisma.run.update({
            where: { id: run.id },
            data: {
              status: "failed",
              error: stderr.slice(0, 2000),
              completedAt,
            },
          });
        }

        resolve();
      });
    });
  } finally {
    running = false;
    await prisma.$disconnect();
  }
}

export function startWorker() {
  setInterval(() => {
    poll().catch((err) => {
      console.error("[worker] poll error:", err);
      running = false;
    });
  }, 10_000);
}
