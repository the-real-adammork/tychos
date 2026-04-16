interface ParamDiffProps {
  prevLabel: string;
  nextLabel: string;
  prev: Record<string, Record<string, number>>;
  next: Record<string, Record<string, number>>;
}

export function ParamDiff({ prevLabel, nextLabel, prev, next }: ParamDiffProps) {
  const diffs: { key: string; oldVal: number; newVal: number }[] = [];

  for (const body of Object.keys(next)) {
    if (!prev[body]) continue;
    for (const field of Object.keys(next[body])) {
      const oldVal = prev[body]?.[field];
      const newVal = next[body][field];
      if (oldVal !== undefined && oldVal !== newVal) {
        diffs.push({ key: `${body}.${field}`, oldVal, newVal });
      }
    }
  }

  if (diffs.length === 0) {
    return (
      <div className="bg-[#0d1117] border border-[#1c2333] rounded-md px-3 py-2 mt-1.5 font-mono text-xs leading-relaxed">
        <div className="text-muted-foreground">{prevLabel} → {nextLabel} (no changes)</div>
      </div>
    );
  }

  return (
    <div className="bg-[#0d1117] border border-[#1c2333] rounded-md px-3 py-2 mt-1.5 font-mono text-xs leading-relaxed">
      <div className="text-muted-foreground mb-1">{prevLabel} → {nextLabel}</div>
      {diffs.map((d) => (
        <div key={d.key}>
          <div className="text-red-400">- {d.key}: {d.oldVal}</div>
          <div className="text-green-400">+ {d.key}: {d.newVal}</div>
        </div>
      ))}
    </div>
  );
}
