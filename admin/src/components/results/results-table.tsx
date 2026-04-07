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
  minSeparationArcmin: number | null
  tychosErrorArcmin: number | null
  jplErrorArcmin: number | null
  timingOffsetMin: number | null
}

interface ApiStats {
  total: number
  mean_tychos_error: number | null
  mean_jpl_error: number | null
  median_tychos_error: number | null
  median_jpl_error: number | null
  max_tychos_error: number | null
  max_jpl_error: number | null
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

function ErrorStatsBar({ stats }: { stats: ApiStats }) {
  if (stats.total === 0) return null
  const fmt = (v: number | null) => (v != null ? `${v.toFixed(1)}'` : "—")
  return (
    <div className="grid grid-cols-2 gap-4 text-sm">
      <div className="space-y-1">
        <div className="text-muted-foreground font-medium">Tychos Error</div>
        <div className="font-mono">
          Mean: {fmt(stats.mean_tychos_error)} · Median: {fmt(stats.median_tychos_error)} · Max: {fmt(stats.max_tychos_error)}
        </div>
      </div>
      <div className="space-y-1">
        <div className="text-muted-foreground font-medium">JPL Error</div>
        <div className="font-mono">
          Mean: {fmt(stats.mean_jpl_error)} · Median: {fmt(stats.median_jpl_error)} · Max: {fmt(stats.max_jpl_error)}
        </div>
      </div>
    </div>
  )
}

const emptyStats: ApiStats = {
  total: 0,
  mean_tychos_error: null,
  mean_jpl_error: null,
  median_tychos_error: null,
  median_jpl_error: null,
  max_tychos_error: null,
  max_jpl_error: null,
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
  const minError = searchParams.get("min_error") || ""
  const maxError = searchParams.get("max_error") || ""

  function setPage(p: number) {
    setSearchParams(prev => { prev.set("page", String(p)); return prev }, { replace: true })
  }
  function setTypeFilter(v: string) {
    setSearchParams(prev => { prev.set("type", v); prev.set("page", "1"); return prev }, { replace: true })
  }
  function setMinError(v: string) {
    setSearchParams(prev => {
      if (v) prev.set("min_error", v); else prev.delete("min_error")
      prev.set("page", "1")
      return prev
    }, { replace: true })
  }
  function setMaxError(v: string) {
    setSearchParams(prev => {
      if (v) prev.set("max_error", v); else prev.delete("max_error")
      prev.set("page", "1")
      return prev
    }, { replace: true })
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  useEffect(() => {
    setLoading(true)
    setError(null)

    const params = new URLSearchParams()
    params.set("page", String(page))
    if (typeFilter !== "all") params.set("catalog_type", typeFilter)
    if (minError) params.set("min_tychos_error", minError)
    if (maxError) params.set("max_tychos_error", maxError)

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
          minSeparationArcmin: r.min_separation_arcmin,
          tychosErrorArcmin: r.tychos_error_arcmin,
          jplErrorArcmin: r.jpl_error_arcmin,
          timingOffsetMin: r.timing_offset_min,
        })) as EclipseResult[]
        setResults(mapped)
        setTotal(data.total)
        setStats(data.stats ?? emptyStats)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Unknown error")
      })
      .finally(() => setLoading(false))
  }, [runId, page, typeFilter, minError, maxError])

  function handleTypeChange(value: string | null) {
    setTypeFilter(value ?? "all")
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Stats bar */}
      {!loading && !error && stats.total > 0 && (
        <ErrorStatsBar stats={stats} />
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
          <span className="text-sm text-muted-foreground">Tychos Error</span>
          <input
            type="number"
            placeholder="min"
            value={minError}
            onChange={(e) => setMinError(e.target.value)}
            className="w-20 px-2 py-1 text-sm border rounded"
            step="0.1"
          />
          <span className="text-xs text-muted-foreground">–</span>
          <input
            type="number"
            placeholder="max"
            value={maxError}
            onChange={(e) => setMaxError(e.target.value)}
            className="w-20 px-2 py-1 text-sm border rounded"
            step="0.1"
          />
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
              <TableHead className="text-right">Tychos Sep</TableHead>
              <TableHead className="text-right">Tychos Error</TableHead>
              <TableHead className="text-right">JPL Error</TableHead>
              <TableHead className="text-right">Timing Offset</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.map((row) => (
              <TableRow
                key={row.id}
                className="cursor-pointer"
                onClick={() => navigate(`/results/${runId}/${row.id}`)}
              >
                <TableCell>{row.date}</TableCell>
                <TableCell className="capitalize">{row.catalogType}</TableCell>
                <TableCell>{row.magnitude.toFixed(2)}</TableCell>
                <TableCell className="text-right font-mono">{formatSeparation(row.minSeparationArcmin)}</TableCell>
                <TableCell className="text-right font-mono">{formatSeparation(row.tychosErrorArcmin)}</TableCell>
                <TableCell className="text-right font-mono">{formatSeparation(row.jplErrorArcmin)}</TableCell>
                <TableCell className="text-right font-mono">{formatTimingOffset(row.timingOffsetMin)}</TableCell>
              </TableRow>
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
