import { useEffect, useState } from "react"
import { useNavigate, Link } from "react-router-dom"
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
import { Button } from "@/components/ui/button"

type RunStatus = "queued" | "running" | "done" | "failed"

interface Run {
  id: number
  datasetSlug: string
  datasetName: string
  status: RunStatus
  totalEclipses: number | null
  meanTychosError: number | null
  meanSunDiff: number | null
  meanMoonDiff: number | null
  meanTimingOffset: number | null
  createdAt: string
  versionNumber: number | null
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

function fmtStat(run: Run, val: number | null, suffix: string = "'"): string {
  if (run.status !== "done") return "—"
  if (val === null) return "—"
  return `${val.toFixed(1)}${suffix}`
}

type FilterStatus = "all" | RunStatus

export default function RunTable() {
  const navigate = useNavigate()
  const [runs, setRuns] = useState<Run[]>([])
  const [filter, setFilter] = useState<FilterStatus>("all")
  const [loading, setLoading] = useState(true)
  const [rerunningId, setRerunningId] = useState<number | null>(null)
  const [openMenuId, setOpenMenuId] = useState<number | null>(null)

  useEffect(() => {
    if (openMenuId === null) return
    const close = () => setOpenMenuId(null)
    window.addEventListener("click", close)
    return () => window.removeEventListener("click", close)
  }, [openMenuId])

  const loadRuns = () => {
    fetch("/api/runs")
      .then((r) => r.json())
      .then((data: any[]) => {
        setRuns(data.map((r) => ({
          id: r.id,
          datasetSlug: r.dataset_slug,
          datasetName: r.dataset_name,
          status: r.status,
          totalEclipses: r.total_eclipses,
          meanTychosError: r.mean_tychos_error ?? null,
          meanSunDiff: r.mean_sun_diff ?? null,
          meanMoonDiff: r.mean_moon_diff ?? null,
          meanTimingOffset: r.mean_timing_offset ?? null,
          createdAt: r.created_at,
          versionNumber: r.version_number ?? null,
          paramSet: {
            id: r.param_version_id,
            name: r.param_set_name,
            owner: { name: r.owner_name },
          },
        })))
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }

  useEffect(() => {
    loadRuns()
  }, [])

  async function handleRerun(runId: number) {
    if (!window.confirm(
      "Force re-run this run? This will delete the existing eclipse results and re-queue the run with the same param version + dataset."
    )) return
    setRerunningId(runId)
    try {
      const res = await fetch(`/api/runs/${runId}/rerun`, { method: "POST" })
      if (!res.ok) throw new Error(await res.text())
      loadRuns()
    } catch (e) {
      window.alert(`Re-run failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setRerunningId(null)
    }
  }

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
              <TableHead>Dataset</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Sun Diff</TableHead>
              <TableHead>Moon Diff</TableHead>
              <TableHead>Timing (min)</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="w-24"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((run) => (
              <TableRow
                key={run.id}
                className={run.status === "done" ? "cursor-pointer" : undefined}
                onClick={
                  run.status === "done"
                    ? () => navigate(`/results/${run.id}`)
                    : undefined
                }
              >
                <TableCell className="font-medium">
                  {run.paramSet.name}
                  {run.versionNumber != null && (
                    <span className="ml-1 text-xs text-muted-foreground">v{run.versionNumber}</span>
                  )}
                </TableCell>
                <TableCell>{run.paramSet.owner.name}</TableCell>
                <TableCell>
                  <Link
                    to={`/datasets/${run.datasetSlug}`}
                    className="text-sm text-blue-500 hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {run.datasetName}
                  </Link>
                </TableCell>
                <TableCell>
                  <StatusBadge status={run.status} />
                </TableCell>
                <TableCell className="tabular-nums">{fmtStat(run, run.meanSunDiff)}</TableCell>
                <TableCell className="tabular-nums">{fmtStat(run, run.meanMoonDiff)}</TableCell>
                <TableCell className="tabular-nums">{fmtStat(run, run.meanTimingOffset, "")}</TableCell>
                <TableCell className="text-muted-foreground">
                  {format(new Date(run.createdAt), "MMM d, yyyy HH:mm")}
                </TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <div className="relative inline-block">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 w-8 p-0"
                      aria-label="Row actions"
                      onClick={(e) => {
                        e.stopPropagation()
                        setOpenMenuId(openMenuId === run.id ? null : run.id)
                      }}
                    >
                      ⋯
                    </Button>
                    {openMenuId === run.id && (
                      <div
                        className="absolute right-0 z-20 mt-1 w-44 rounded-md border bg-popover text-popover-foreground shadow-md"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          type="button"
                          className="w-full px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground disabled:opacity-50 disabled:cursor-not-allowed"
                          disabled={
                            rerunningId === run.id ||
                            run.status === "queued" ||
                            run.status === "running"
                          }
                          onClick={() => {
                            setOpenMenuId(null)
                            handleRerun(run.id)
                          }}
                        >
                          {rerunningId === run.id ? "Re-running…" : "Force re-run"}
                        </button>
                      </div>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
