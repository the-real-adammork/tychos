import { useEffect, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface EclipseResult {
  id: number
  julianDayTt: number
  date: string
  catalogType: string
  magnitude: number
  detected: number
  thresholdArcmin: number
  minSeparationArcmin: number | null
  timingOffsetMin: number | null
  bestJd: number | null
  sunRaRad: number | null
  sunDecRad: number | null
  moonRaRad: number | null
  moonDecRad: number | null
  moonErrorArcmin: number | null
  status: "pass" | "fail"
  thresholdPass: boolean
  jplRescued: boolean
}

interface ApiStats {
  threshold_pass: number
  threshold_fail: number
  jpl_rescued: number
  overall_pass: number
  overall_fail: number
  total: number
}

interface ApiResponse {
  results: EclipseResult[]
  total: number
  page: number
  pageSize: number
  stats: ApiStats
}

interface ResultsTableProps {
  runId: string
}

function formatTimingOffset(val: number | null): string {
  if (val === null) return "—"
  return (val >= 0 ? "+" : "") + val.toFixed(1)
}

function formatSeparation(val: number | null): string {
  if (val === null) return "—"
  return val.toFixed(2)
}

function formatMoonError(val: number | null): string {
  if (val === null) return "—"
  return val.toFixed(1)
}

interface StatsBarProps {
  stats: ApiStats
}

function StatsBar({ stats }: StatsBarProps) {
  const total = stats.total
  if (total === 0) return null

  const thresholdPct = (stats.threshold_pass / total) * 100
  const rescuedPct = (stats.jpl_rescued / total) * 100
  const failPct = (stats.overall_fail / total) * 100

  return (
    <div className="flex flex-col gap-1">
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
        {thresholdPct > 0 && (
          <div
            className="bg-green-600"
            style={{ width: `${thresholdPct}%` }}
            title={`Threshold Pass: ${stats.threshold_pass}`}
          />
        )}
        {rescuedPct > 0 && (
          <div
            className="bg-blue-500"
            style={{ width: `${rescuedPct}%` }}
            title={`JPL Rescued: ${stats.jpl_rescued}`}
          />
        )}
        {failPct > 0 && (
          <div
            className="bg-red-600"
            style={{ width: `${failPct}%` }}
            title={`Fail: ${stats.overall_fail}`}
          />
        )}
      </div>
      <div className="flex gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-green-600" />
          Threshold Pass: {stats.threshold_pass}
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-blue-500" />
          JPL Rescued: {stats.jpl_rescued}
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-red-600" />
          Fail: {stats.overall_fail}
        </span>
      </div>
    </div>
  )
}

const emptyStats: ApiStats = {
  threshold_pass: 0,
  threshold_fail: 0,
  jpl_rescued: 0,
  overall_pass: 0,
  overall_fail: 0,
  total: 0,
}

export function ResultsTable({ runId }: ResultsTableProps) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [results, setResults] = useState<EclipseResult[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<ApiStats>(emptyStats)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Read state from URL
  const page = parseInt(searchParams.get("page") || "1")
  const pageSize = 50
  const typeFilter = searchParams.get("type") || "all"
  const statusFilter = searchParams.get("status") || "all"

  function setPage(p: number) {
    setSearchParams(prev => { prev.set("page", String(p)); return prev }, { replace: true })
  }
  function setTypeFilter(v: string) {
    setSearchParams(prev => { prev.set("type", v); prev.set("page", "1"); return prev }, { replace: true })
  }
  function setStatusFilter(v: string) {
    setSearchParams(prev => { prev.set("status", v); prev.set("page", "1"); return prev }, { replace: true })
  }

  // Expanded rows
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  useEffect(() => {
    setLoading(true)
    setError(null)

    const params = new URLSearchParams()
    params.set("page", String(page))
    if (typeFilter !== "all") params.set("catalog_type", typeFilter)
    if (statusFilter !== "all") params.set("status", statusFilter)

    fetch(`/api/results/${runId}?${params.toString()}`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch results")
        return res.json() as Promise<{ results: Record<string, unknown>[]; total: number; page: number; pageSize: number; stats: ApiStats }>
      })
      .then((data) => {
        const mapped = data.results.map((r: Record<string, unknown>) => ({
          id: r.id,
          julianDayTt: r.julian_day_tt,
          date: r.date,
          catalogType: r.catalog_type,
          magnitude: r.magnitude,
          detected: r.detected,
          thresholdArcmin: r.threshold_arcmin,
          minSeparationArcmin: r.min_separation_arcmin,
          timingOffsetMin: r.timing_offset_min,
          bestJd: r.best_jd,
          sunRaRad: r.sun_ra_rad,
          sunDecRad: r.sun_dec_rad,
          moonRaRad: r.moon_ra_rad,
          moonDecRad: r.moon_dec_rad,
          moonErrorArcmin: r.moon_error_arcmin,
          status: r.status,
          thresholdPass: r.threshold_pass,
          jplRescued: r.jpl_rescued,
        })) as EclipseResult[]
        setResults(mapped)
        setTotal(data.total)
        setStats(data.stats ?? emptyStats)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Unknown error")
      })
      .finally(() => setLoading(false))
  }, [runId, page, typeFilter, statusFilter])

  function handleTypeChange(value: string | null) {
    setTypeFilter(value ?? "all")
    setPage(1)
    setExpandedRows(new Set())
  }

  function handleStatusChange(value: string | null) {
    setStatusFilter(value ?? "all")
    setPage(1)
    setExpandedRows(new Set())
  }

  function toggleRow(id: number) {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Stats bar */}
      {!loading && !error && stats.total > 0 && (
        <StatsBar stats={stats} />
      )}

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Type</span>
          <Select value={typeFilter} onValueChange={handleTypeChange}>
            <SelectTrigger className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All types</SelectItem>
              <SelectItem value="total">Total</SelectItem>
              <SelectItem value="annular">Annular</SelectItem>
              <SelectItem value="partial">Partial</SelectItem>
              <SelectItem value="hybrid">Hybrid</SelectItem>
              <SelectItem value="penumbral">Penumbral</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Status</span>
          <Select value={statusFilter} onValueChange={handleStatusChange}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="pass">Pass</SelectItem>
              <SelectItem value="fail">Fail</SelectItem>
              <SelectItem value="threshold_pass">Threshold Pass</SelectItem>
              <SelectItem value="threshold_fail">Threshold Fail</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <span className="ml-auto text-sm text-muted-foreground">
          {total} eclipse{total !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Table */}
      {error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : results.length === 0 ? (
        <p className="text-sm text-muted-foreground">No results found.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Magnitude</TableHead>
              <TableHead>Threshold</TableHead>
              <TableHead>JPL Check</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Min Separation (arcmin)</TableHead>
              <TableHead>Timing Offset (min)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.map((row) => (
              <>
                <TableRow
                  key={row.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/results/${runId}/${row.id}`)}
                >
                  <TableCell>{row.date}</TableCell>
                  <TableCell className="capitalize">{row.catalogType}</TableCell>
                  <TableCell>{row.magnitude.toFixed(2)}</TableCell>
                  <TableCell>
                    {row.detected === 1 ? (
                      <Badge className="bg-green-600 text-white hover:bg-green-700">pass</Badge>
                    ) : (
                      <Badge variant="destructive">fail</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {row.detected !== 0 ? (
                      <span className="text-muted-foreground">—</span>
                    ) : row.moonErrorArcmin !== null && row.moonErrorArcmin < 60 ? (
                      <span className="flex items-center gap-1">
                        <Badge className="bg-green-600 text-white hover:bg-green-700">rescued</Badge>
                        <span className="text-xs text-muted-foreground">{formatMoonError(row.moonErrorArcmin)}</span>
                      </span>
                    ) : (
                      <span className="flex items-center gap-1">
                        <Badge variant="destructive">fail</Badge>
                        <span className="text-xs text-muted-foreground">{formatMoonError(row.moonErrorArcmin)}</span>
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    {row.status === "pass" ? (
                      <Badge className="bg-green-600 text-white hover:bg-green-700">pass</Badge>
                    ) : (
                      <Badge variant="destructive">fail</Badge>
                    )}
                  </TableCell>
                  <TableCell>{formatSeparation(row.minSeparationArcmin)}</TableCell>
                  <TableCell>{formatTimingOffset(row.timingOffsetMin)}</TableCell>
                </TableRow>
                {expandedRows.has(row.id) && (
                  <TableRow key={`${row.id}-expand`} className="bg-muted/30">
                    <TableCell colSpan={8} className="text-xs font-mono text-muted-foreground">
                      <div className="grid grid-cols-2 gap-x-8 gap-y-1 p-1">
                        <span>
                          Sun RA:{" "}
                          {row.sunRaRad !== null ? row.sunRaRad.toFixed(4) : "—"}
                        </span>
                        <span>
                          Sun Dec:{" "}
                          {row.sunDecRad !== null ? row.sunDecRad.toFixed(4) : "—"}
                        </span>
                        <span>
                          Moon RA:{" "}
                          {row.moonRaRad !== null ? row.moonRaRad.toFixed(4) : "—"}
                        </span>
                        <span>
                          Moon Dec:{" "}
                          {row.moonDecRad !== null ? row.moonDecRad.toFixed(4) : "—"}
                        </span>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </>
            ))}
          </TableBody>
        </Table>
      )}

      {/* Pagination */}
      {!loading && !error && results.length > 0 && (
        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage(Math.max(1, page - 1))}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage(Math.min(totalPages, page + 1))}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  )
}
