import { useState, useEffect, useRef } from "react";
import { ParamDiff } from "./param-diff";
import { RunCard } from "./run-card";
import { SearchResultCard } from "./search-result-card";

interface LogEntry {
  id: number;
  research_job_id: number;
  research_iteration_id: number | null;
  role: string;
  content: string | null;
  tool_name: string | null;
  token_count: number | null;
  created_at: string;
}

interface TimelineProps {
  jobId: number;
  jobStatus: string;
}

export function Timeline({ jobId, jobStatus }: TimelineProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const sseRef = useRef<EventSource | null>(null);

  useEffect(() => {
    fetch(`/api/research/${jobId}/logs?limit=500`)
      .then((r) => r.json())
      .then((data) => {
        setLogs(data);
        setLoading(false);
      });
  }, [jobId]);

  useEffect(() => {
    const es = new EventSource(`/api/research/${jobId}/logs/stream`);
    sseRef.current = es;
    es.addEventListener("log", (e) => {
      try {
        const entry: LogEntry = JSON.parse(e.data);
        setLogs((prev) => {
          if (prev.some((l) => l.id === entry.id)) return prev;
          return [...prev, entry];
        });
      } catch {}
    });
    return () => { es.close(); sseRef.current = null; };
  }, [jobId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  if (loading) return <p className="text-sm text-muted-foreground py-4">Loading timeline…</p>;

  const grouped = groupLogs(logs);

  return (
    <div className="flex flex-col gap-3 py-4">
      {grouped.map((group, idx) => (
        <TimelineEvent key={group.id} group={group} prevGroup={grouped[idx - 1]} />
      ))}
      {logs.length === 0 && (
        <p className="text-center text-muted-foreground py-8">
          {jobStatus === "pending" ? "Job not started yet" : "No events yet"}
        </p>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

interface EventGroup {
  id: number;
  type: "assistant" | "tool" | "checkpoint" | "restore" | "user_inject" | "system";
  role: string;
  content: string | null;
  toolName: string | null;
  toolInput: Record<string, unknown> | null;
  toolResult: Record<string, unknown> | null;
  created_at: string;
}

function groupLogs(logs: LogEntry[]): EventGroup[] {
  const groups: EventGroup[] = [];
  let i = 0;
  while (i < logs.length) {
    const log = logs[i];

    if (log.role === "tool_call") {
      const resultLog = logs[i + 1]?.role === "tool_result" && logs[i + 1]?.tool_name === log.tool_name
        ? logs[i + 1]
        : null;

      let toolInput: Record<string, unknown> | null = null;
      let toolResult: Record<string, unknown> | null = null;
      try { toolInput = JSON.parse(log.content || "{}"); } catch {}
      if (resultLog) {
        try {
          const parsed = JSON.parse(resultLog.content || "{}");
          const resultStr = parsed.result || resultLog.content;
          toolResult = typeof resultStr === "string" ? JSON.parse(resultStr) : resultStr;
        } catch {}
      }

      if (log.tool_name === "checkpoint") {
        groups.push({
          id: log.id, type: "checkpoint", role: log.role,
          content: null, toolName: log.tool_name,
          toolInput, toolResult, created_at: log.created_at,
        });
      } else if (log.tool_name === "restore") {
        groups.push({
          id: log.id, type: "restore", role: log.role,
          content: null, toolName: log.tool_name,
          toolInput, toolResult, created_at: log.created_at,
        });
      } else {
        groups.push({
          id: log.id, type: "tool", role: log.role,
          content: log.content, toolName: log.tool_name,
          toolInput, toolResult, created_at: log.created_at,
        });
      }
      i += resultLog ? 2 : 1;
    } else {
      groups.push({
        id: log.id,
        type: log.role === "user_inject" ? "user_inject"
          : log.role === "system" ? "system"
          : "assistant",
        role: log.role,
        content: log.content,
        toolName: null,
        toolInput: null,
        toolResult: null,
        created_at: log.created_at,
      });
      i++;
    }
  }
  return groups;
}

function TimelineEvent({ group, prevGroup }: { group: EventGroup; prevGroup?: EventGroup }) {
  if (group.type === "system") {
    return (
      <div className="text-center text-xs text-muted-foreground py-1">
        {group.content}
      </div>
    );
  }

  if (group.type === "checkpoint") {
    const versionId = group.toolInput?.input
      ? (group.toolInput.input as Record<string, unknown>).version_id
      : group.toolInput?.version_id;
    const obj = group.toolResult?.objective ?? group.toolResult?.ok;
    return (
      <div className="flex items-center gap-2 py-1">
        <div className="flex-1 h-px bg-gradient-to-r from-transparent via-green-500/50 to-transparent" />
        <span className="text-green-400 text-xs font-semibold whitespace-nowrap">
          ✓ Checkpoint v{String(versionId)}{obj && typeof obj === "number" ? ` — obj: ${obj.toFixed(2)}` : ""}
        </span>
        <div className="flex-1 h-px bg-gradient-to-r from-transparent via-green-500/50 to-transparent" />
      </div>
    );
  }

  if (group.type === "restore") {
    const versionId = group.toolInput?.input
      ? (group.toolInput.input as Record<string, unknown>).version_id
      : group.toolInput?.version_id;
    return (
      <div className="flex items-center gap-2 py-1">
        <div className="flex-1 h-px bg-gradient-to-r from-transparent via-yellow-500/50 to-transparent" />
        <span className="text-yellow-400 text-xs font-semibold whitespace-nowrap">
          ↩ Restored from v{String(versionId)}
        </span>
        <div className="flex-1 h-px bg-gradient-to-r from-transparent via-yellow-500/50 to-transparent" />
      </div>
    );
  }

  if (group.type === "user_inject") {
    return (
      <div className="flex gap-2.5 justify-end">
        <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg px-3.5 py-2.5 max-w-[75%]">
          <div className="text-blue-400 text-[10px] mb-1">You</div>
          <div className="text-sm whitespace-pre-wrap">{group.content}</div>
        </div>
        <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center shrink-0 text-[11px] font-semibold text-white">U</div>
      </div>
    );
  }

  if (group.type === "tool" && group.toolName === "propose_params") {
    const result = group.toolResult || {};
    const prevObj = prevGroup?.toolResult?.objective as number | undefined;
    return (
      <div className="flex gap-2.5">
        <div className="w-7 h-7 rounded-full bg-purple-600 flex items-center justify-center shrink-0 text-[11px] font-semibold text-white">AI</div>
        <div className="flex-1 max-w-[85%]">
          <div className="bg-accent/50 border border-border rounded-lg px-3.5 py-2.5">
            <span className="text-muted-foreground text-xs">🔧 propose_params</span>
          </div>
          {result.run_id && (
            <RunCard
              runId={result.run_id as number}
              objective={result.objective as number | null}
              nScored={result.n_scored as number | null}
              prevObjective={prevObj}
            />
          )}
        </div>
      </div>
    );
  }

  if (group.type === "tool" && group.toolName === "search") {
    const result = group.toolResult || {};
    const input = group.toolInput?.input as Record<string, unknown> | undefined;
    return (
      <div className="flex gap-2.5">
        <div className="w-7 h-7 rounded-full bg-purple-600 flex items-center justify-center shrink-0 text-[11px] font-semibold text-white">AI</div>
        <div className="flex-1 max-w-[85%]">
          <div className="bg-accent/50 border border-border rounded-lg px-3.5 py-2.5">
            <span className="text-purple-400 text-xs">🔍 search</span>
            <div className="bg-[#0d1117] border border-[#1c2333] rounded-md px-3 py-2 mt-1.5 font-mono text-xs">
              <div className="text-muted-foreground">
                Nelder-Mead · budget={String(input?.budget ?? "?")} · scale={String(input?.scale ?? "?")}
              </div>
              <div className="text-purple-400">
                params: {Array.isArray(input?.param_keys) ? (input.param_keys as string[]).join(", ") : "?"}
              </div>
            </div>
          </div>
          {result.starting_objective != null && (
            <SearchResultCard
              startingObjective={result.starting_objective as number}
              bestObjective={result.best_objective as number}
              nEvals={result.n_evals as number}
              improved={result.improved as boolean}
              winnerVersionId={result.winner_version_id as number | null}
              winnerRunId={result.winner_run_id as number | null}
            />
          )}
        </div>
      </div>
    );
  }

  // Default: assistant message
  return (
    <div className="flex gap-2.5">
      <div className="w-7 h-7 rounded-full bg-purple-600 flex items-center justify-center shrink-0 text-[11px] font-semibold text-white">AI</div>
      <div className="bg-accent/50 border border-border rounded-lg px-3.5 py-2.5 max-w-[85%]">
        <div className="text-sm whitespace-pre-wrap">{group.content}</div>
      </div>
    </div>
  );
}
