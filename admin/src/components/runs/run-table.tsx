"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { format } from "date-fns"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

type RunStatus = "queued" | "running" | "done" | "failed"

interface Run {
  id: number
  testType: string
  status: RunStatus
  totalEclipses: number | null
  detected: number | null
  createdAt: string
  paramSet: {
    id: number
    name: string
    owner: { name: string }
  }
}

function StatusBadge({ status }: { status: RunStatus }) {
  if (status === "done") {
    return (
      <Badge className="bg-green-500/15 text-green-600 border-transparent dark:text-green-400">
        done
      </Badge>
    )
  }
  if (status === "running") {
    return (
      <Badge className="bg-yellow-500/15 text-yellow-600 border-transparent dark:text-yellow-400">
        running
      </Badge>
    )
  }
  if (status === "queued") {
    return (
      <Badge variant="secondary">
        queued
      </Badge>
    )
  }
  return (
    <Badge variant="destructive">
      failed
    </Badge>
  )
}

function detectionRate(run: Run): string {
  if (run.status !== "done") return "—"
  if (run.detected === null || run.totalEclipses === null) return "—"
  const pct =
    run.totalEclipses === 0
      ? 0
      : Math.round((run.detected / run.totalEclipses) * 100)
  return `${run.detected}/${run.totalEclipses} (${pct}%)`
}

type FilterStatus = "all" | RunStatus

export default function RunTable() {
  const router = useRouter()
  const [runs, setRuns] = useState<Run[]>([])
  const [filter, setFilter] = useState<FilterStatus>("all")
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/runs")
      .then((r) => r.json())
      .then((data) => {
        setRuns(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const filtered =
    filter === "all" ? runs : runs.filter((r) => r.status === filter)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Filter by status:</span>
        <Select
          value={filter}
          onValueChange={(v) => setFilter(v as FilterStatus)}
        >
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="queued">Queued</SelectItem>
            <SelectItem value="running">Running</SelectItem>
            <SelectItem value="done">Done</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">No runs found.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Param Set</TableHead>
              <TableHead>Owner</TableHead>
              <TableHead>Test Type</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Detection Rate</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((run) => (
              <TableRow
                key={run.id}
                className={run.status === "done" ? "cursor-pointer" : undefined}
                onClick={
                  run.status === "done"
                    ? () => router.push(`/results/${run.id}`)
                    : undefined
                }
              >
                <TableCell className="font-medium">{run.paramSet.name}</TableCell>
                <TableCell>{run.paramSet.owner.name}</TableCell>
                <TableCell>{run.testType}</TableCell>
                <TableCell>
                  <StatusBadge status={run.status} />
                </TableCell>
                <TableCell className="tabular-nums">
                  {detectionRate(run)}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {format(new Date(run.createdAt), "MMM d, yyyy HH:mm")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
