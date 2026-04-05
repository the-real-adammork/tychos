interface ParamDiffProps {
  paramsJsonA: string;
  paramsJsonB: string;
}

interface BodyDiff {
  body: string;
  changes: Array<{ key: string; oldVal: unknown; newVal: unknown }>;
}

function parseParams(json: string): Record<string, Record<string, unknown>> {
  try {
    const parsed = JSON.parse(json);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      return parsed as Record<string, Record<string, unknown>>;
    }
  } catch {
    // fall through
  }
  return {};
}

export function ParamDiff({ paramsJsonA, paramsJsonB }: ParamDiffProps) {
  const paramsA = parseParams(paramsJsonA);
  const paramsB = parseParams(paramsJsonB);

  const allBodies = Array.from(
    new Set([...Object.keys(paramsA), ...Object.keys(paramsB)])
  ).sort();

  const diffs: BodyDiff[] = [];

  for (const body of allBodies) {
    const bodyA = paramsA[body] ?? {};
    const bodyB = paramsB[body] ?? {};
    const allKeys = Array.from(
      new Set([...Object.keys(bodyA), ...Object.keys(bodyB)])
    ).sort();

    const changes: BodyDiff["changes"] = [];
    for (const key of allKeys) {
      const valA = bodyA[key];
      const valB = bodyB[key];
      if (JSON.stringify(valA) !== JSON.stringify(valB)) {
        changes.push({ key, oldVal: valA, newVal: valB });
      }
    }

    if (changes.length > 0) {
      diffs.push({ body, changes });
    }
  }

  const totalBodiesChanged = diffs.length;
  const totalValuesModified = diffs.reduce((sum, d) => sum + d.changes.length, 0);

  if (diffs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Parameters are identical between these two versions.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        className="rounded-md overflow-auto"
        style={{ backgroundColor: "#1a1a1a", fontFamily: "monospace" }}
      >
        {diffs.map((bodyDiff) => (
          <div key={bodyDiff.body} className="p-4 border-b border-zinc-700 last:border-0">
            <div className="text-zinc-300 font-semibold mb-2 text-sm">
              {bodyDiff.body}
            </div>
            {bodyDiff.changes.map((change) => (
              <div key={change.key} className="text-sm leading-6">
                <div style={{ color: "#f87171" }}>
                  {"- "}
                  {change.key}: {JSON.stringify(change.oldVal)}
                </div>
                <div style={{ color: "#4ade80" }}>
                  {"+ "}
                  {change.key}: {JSON.stringify(change.newVal)}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        {totalBodiesChanged} {totalBodiesChanged === 1 ? "body" : "bodies"} changed,{" "}
        {totalValuesModified} {totalValuesModified === 1 ? "value" : "values"} modified
      </p>
    </div>
  );
}
