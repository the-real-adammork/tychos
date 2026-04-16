import { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceDot,
} from "recharts";
import { ChevronDown, ChevronRight } from "lucide-react";

interface Iteration {
  id: number;
  kind: string;
  objective: number | null;
}

interface ObjectiveChartProps {
  iterations: Iteration[];
}

export function ObjectiveChart({ iterations }: ObjectiveChartProps) {
  const [collapsed, setCollapsed] = useState(false);

  const data = iterations
    .filter((it) => it.objective != null)
    .map((it, idx) => ({
      index: idx + 1,
      objective: it.objective,
      kind: it.kind,
      id: it.id,
    }));

  if (data.length === 0) return null;

  const checkpoints = data.filter((d) => d.kind === "search_winner" || d.kind === "iterate");
  const searchWinners = data.filter((d) => d.kind === "search_winner");

  return (
    <div className="border rounded-lg bg-card">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 w-full px-4 py-3 text-sm font-medium hover:bg-accent/50 transition-colors"
      >
        {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        Objective over time
        <span className="text-muted-foreground ml-2 font-normal">
          {data.length} iterations · best: {Math.min(...data.map((d) => d.objective!)).toFixed(2)} arcmin
        </span>
      </button>
      {!collapsed && (
        <div className="px-4 pb-4">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data}>
              <XAxis
                dataKey="index"
                tick={{ fontSize: 11, fill: "#888" }}
                axisLine={{ stroke: "#333" }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#888" }}
                axisLine={{ stroke: "#333" }}
                tickLine={false}
                width={50}
              />
              <Tooltip
                contentStyle={{ background: "#1a1a1a", border: "1px solid #333", borderRadius: 6, fontSize: 12 }}
                labelFormatter={(v) => `Iteration ${v}`}
                formatter={(v: number) => [`${v.toFixed(4)} arcmin`, "Objective"]}
              />
              <Line
                type="monotone"
                dataKey="objective"
                stroke="#a78bfa"
                strokeWidth={2}
                dot={{ r: 3, fill: "#a78bfa" }}
                activeDot={{ r: 5 }}
              />
              {searchWinners.map((d) => (
                <ReferenceDot
                  key={d.id}
                  x={d.index}
                  y={d.objective!}
                  r={6}
                  fill="#22c55e"
                  stroke="#22c55e"
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
