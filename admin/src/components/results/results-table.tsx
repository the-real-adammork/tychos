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
  detected: boolean
  thresholdArcmin: number
  minSeparationArcmin: number | null
  timingOffsetMin: number | null
  bestJd: number | null
  sunRaRad: number | null
  sunDecRad: number | null
  moonRaRad: number | null
  moonDecRad: number | null
  moonErrorArcmin: number | null
  accuracy: "pass" | "close" | "fail" | "unknown"
}

interface ApiResponse {
  results: EclipseResult[]
  total: number
  page: number
  pageSize: number
  stats: { pass: number; close: number; fail: number }
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

function AccuracyBadge({ accuracy }: { accuracy: EclipseResult["accuracy"] }) {
  if (accuracy === "pass") {
    return <Badge className="bg-green-600 text-white hover:bg-green-700">pass</Badge>
  }
  if (accuracy === "close") {
    return <Badge className="bg-yellow-500 text-white hover:bg-yellow-600">close</Badge>
  }
  if (accuracy === "fail") {
    return <Badge variant="destructive">fail</Badge>
  }
  return <Badge variant="secondary">unknown</Badge>
}

interface StatsBarProps {
  stats: { pass: number; close: number; fail: number }
}

function StatsBar({ stats }: StatsBarProps) {
  const total = stats.pass + stats.close + stats.fail
  if (total === 0) return null

  const passPct = (stats.pass / total) * 100
  const closePct = (stats.close / total) * 100
  const failPct = (stats.fail / total) * 100

  return (
    <div className="flex flex-col gap-1">
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
        {passPct > 0 && (
          <div
            className="bg-green-600"
            style={{ width: `${passPct}%` }}
            title={`Pass: ${stats.pass}`}
          />
        )}
        {closePct > 0 && (
          <div
            className="bg-yellow-500"
            style={{ width: `${closePct}%` }}
            title={`Close: ${stats.close}`}
          />
        )}
        {failPct > 0 && (
          <div
            className="bg-red-600"
            style={{ width: `${failPct}%` }}
            title={`Fail: ${stats.fail}`}
          />
        )}
      </div>
      <div className="flex gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-green-600" />
          Pass: {stats.pass}
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-yellow-500" />
          Close: {stats.close}
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-red-600" />
          Fail: {stats.fail}
        </span>
      </div>
    </div>
  )
}

export function ResultsTable({ runId }: ResultsTableProps) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [results, setResults] = useState<EclipseResult[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<{ pass: number; close: number; fail: number }>({ pass: 0, close: 0, fail: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Read state from URL
  const page = parseInt(searchParams.get("page") || "1")
  const pageSize = 50
  const typeFilter = searchParams.get("type") || "all"
  const accuracyFilter = searchParams.get("accuracy") || "all"

  function setPage(p: number) {
    setSearchParams(prev => { prev.set("page", String(p)); return prev }, { replace: true })
  }
  function setTypeFilter(v: string) {
    setSearchParams(prev => { prev.set("type", v); prev.set("page", "1"); return prev }, { replace: true })
  }
  function setAccuracyFilter(v: string) {
    setSearchParams(prev => { prev.set("accuracy", v); prev.set("page", "1"); return prev }, { replace: true })
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
    if (accuracyFilter !== "all") params.set("accuracy", accuracyFilter)

    fetch(`/api/results/${runId}?${params.toString()}`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch results")
        return res.json() as Promise<ApiResponse>
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
          accuracy: r.accuracy,
        })) as EclipseResult[]
        setResults(mapped)
        setTotal(data.total)
        setStats(data.stats ?? { pass: 0, close: 0, fail: 0 })
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Unknown error")
      })
      .finally(() => setLoading(false))
  }, [runId, page, typeFilter, accuracyFilter])

  function handleTypeChange(value: string | null) {
    setTypeFilter(value ?? "all")
    setPage(1)
    setExpandedRows(new Set())
  }

  function handleAccuracyChange(value: string | null) {
    setAccuracyFilter(value ?? "all")
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
      {!loading && !error && (stats.pass + stats.close + stats.fail > 0) && (
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
          <span className="text-sm text-muted-foreground">Accuracy</span>
          <Select value={accuracyFilter} onValueChange={handleAccuracyChange}>
            <SelectTrigger className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="pass">Pass</SelectItem>
              <SelectItem value="close">Close</SelectItem>
              <SelectItem value="close+fail">Close + Fail</SelectItem>
              <SelectItem value="fail">Fail</SelectItem>
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
              <TableHead>Moon Error (arcmin)</TableHead>
              <TableHead>Accuracy</TableHead>
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
                    {row.detected ? (
                      <Badge className="bg-green-600 text-white hover:bg-green-700">
                        Yes
                      </Badge>
                    ) : (
                      <Badge variant="destructive">No</Badge>
                    )}
                  </TableCell>
                  <TableCell>{formatMoonError(row.moonErrorArcmin)}</TableCell>
                  <TableCell>
                    <AccuracyBadge accuracy={row.accuracy} />
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
