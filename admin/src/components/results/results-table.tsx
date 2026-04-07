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
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

type SortDir = "asc" | "desc"

interface SortHeadProps {
  column: string
  active: string
  direction: SortDir
  onSort: (column: string) => void
  className?: string
  children: React.ReactNode
}

function SortHead({ column, active, direction, onSort, className, children }: SortHeadProps) {
  const isActive = active === column
  const arrow = isActive ? (direction === "asc" ? " ↑" : " ↓") : ""
  return (
    <TableHead
      className={`cursor-pointer select-none hover:text-foreground ${className ?? ""}`}
      onClick={() => onSort(column)}
    >
      {children}
      <span className="text-muted-foreground">{arrow}</span>
    </TableHead>
  )
}

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

interface SarosGroup {
  saros_num: number
  count: number
  year_start: string
  year_end: string
  mean_tychos_error: number | null
  mean_jpl_error: number | null
  max_tychos_error: number | null
  max_jpl_error: number | null
}

export function ResultsTable({ runId }: ResultsTableProps) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [results, setResults] = useState<EclipseResult[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<ApiStats>(emptyStats)
  const [sarosGroups, setSarosGroups] = useState<SarosGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Read state from URL
  const page = parseInt(searchParams.get("page") || "1")
  const pageSize = 50
  const typeFilter = searchParams.get("type") || "all"
  const minError = searchParams.get("min_error") || ""
  const maxError = searchParams.get("max_error") || ""
  const sarosFilter = searchParams.get("saros") || ""
  const groupBySaros = searchParams.get("group") === "saros"
  const sortBy = searchParams.get("sort_by") || "date"
  const sortDir = (searchParams.get("sort_dir") || "asc") as SortDir

  // Saros view sort state (client-side, separate from per-eclipse sort)
  const [sarosSortBy, setSarosSortBy] = useState<string>("mean_tychos_error")
  const [sarosSortDir, setSarosSortDir] = useState<SortDir>("desc")

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
  function setGroupBySaros(on: boolean) {
    setSearchParams(prev => {
      if (on) prev.set("group", "saros"); else prev.delete("group")
      prev.set("page", "1")
      return prev
    }, { replace: true })
  }
  function clearSarosFilter() {
    setSearchParams(prev => {
      prev.delete("saros")
      prev.set("page", "1")
      return prev
    }, { replace: true })
  }
  function handleEclipseSort(column: string) {
    setSearchParams(prev => {
      const currentBy = prev.get("sort_by") || "date"
      const currentDir = prev.get("sort_dir") || "asc"
      if (currentBy === column) {
        prev.set("sort_dir", currentDir === "asc" ? "desc" : "asc")
      } else {
        prev.set("sort_by", column)
        prev.set("sort_dir", "asc")
      }
      prev.set("page", "1")
      return prev
    }, { replace: true })
  }
  function handleSarosSort(column: string) {
    if (sarosSortBy === column) {
      setSarosSortDir(sarosSortDir === "asc" ? "desc" : "asc")
    } else {
      setSarosSortBy(column)
      setSarosSortDir("desc")
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  useEffect(() => {
    setLoading(true)
    setError(null)

    const params = new URLSearchParams()
    if (typeFilter !== "all") params.set("catalog_type", typeFilter)
    if (minError) params.set("min_tychos_error", minError)
    if (maxError) params.set("max_tychos_error", maxError)

    if (groupBySaros) {
      // Saros grouped view
      fetch(`/api/results/${runId}/saros?${params.toString()}`)
        .then((res) => {
          if (!res.ok) throw new Error("Failed to fetch saros groups")
          return res.json() as Promise<{ groups: SarosGroup[] }>
        })
        .then((data) => {
          setSarosGroups(data.groups)
          setTotal(data.groups.length)
        })
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : "Unknown error")
        })
        .finally(() => setLoading(false))
      return
    }

    // Per-eclipse view
    params.set("page", String(page))
    if (sarosFilter) params.set("saros", sarosFilter)
    params.set("sort_by", sortBy)
    params.set("sort_dir", sortDir)

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
  }, [runId, page, typeFilter, minError, maxError, sarosFilter, groupBySaros, sortBy, sortDir])

  // Client-side sorted Saros groups
  const sortedSarosGroups = [...sarosGroups].sort((a, b) => {
    const av = (a as unknown as Record<string, unknown>)[sarosSortBy]
    const bv = (b as unknown as Record<string, unknown>)[sarosSortBy]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === "number" && typeof bv === "number") {
      return sarosSortDir === "asc" ? av - bv : bv - av
    }
    const as = String(av)
    const bs = String(bv)
    return sarosSortDir === "asc" ? as.localeCompare(bs) : bs.localeCompare(as)
  })

  function handleTypeChange(value: string | null) {
    setTypeFilter(value ?? "all")
  }

  function openSarosSeries(saros: number) {
    setSearchParams(prev => {
      prev.set("saros", String(saros))
      prev.delete("group")
      prev.set("page", "1")
      return prev
    }, { replace: true })
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Stats bar */}
      {!loading && !error && !groupBySaros && stats.total > 0 && (
        <ErrorStatsBar stats={stats} />
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">View</span>
          <Select value={groupBySaros ? "saros" : "eclipses"} onValueChange={(v) => setGroupBySaros(v === "saros")}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="eclipses">Per eclipse</SelectItem>
              <SelectItem value="saros">Group by Saros</SelectItem>
            </SelectContent>
          </Select>
        </div>

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

        {sarosFilter && !groupBySaros && (
          <Badge
            className="cursor-pointer bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/30"
            onClick={clearSarosFilter}
          >
            Saros {sarosFilter} ✕
          </Badge>
        )}

        <span className="ml-auto text-sm text-muted-foreground">
          {groupBySaros ? `${total} series` : `${total} eclipse${total !== 1 ? "s" : ""}`}
        </span>
      </div>

      {/* Table */}
      {error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : groupBySaros ? (
        sortedSarosGroups.length === 0 ? (
          <p className="text-sm text-muted-foreground">No Saros series found.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <SortHead column="saros_num" active={sarosSortBy} direction={sarosSortDir} onSort={handleSarosSort}>Saros #</SortHead>
                <SortHead column="count" active={sarosSortBy} direction={sarosSortDir} onSort={handleSarosSort} className="text-right">Eclipses</SortHead>
                <SortHead column="year_start" active={sarosSortBy} direction={sarosSortDir} onSort={handleSarosSort}>Year Span</SortHead>
                <SortHead column="mean_tychos_error" active={sarosSortBy} direction={sarosSortDir} onSort={handleSarosSort} className="text-right">Mean Tychos Error</SortHead>
                <SortHead column="max_tychos_error" active={sarosSortBy} direction={sarosSortDir} onSort={handleSarosSort} className="text-right">Max Tychos Error</SortHead>
                <SortHead column="mean_jpl_error" active={sarosSortBy} direction={sarosSortDir} onSort={handleSarosSort} className="text-right">Mean JPL Error</SortHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedSarosGroups.map((g) => (
                <TableRow
                  key={g.saros_num}
                  className="cursor-pointer"
                  onClick={() => openSarosSeries(g.saros_num)}
                >
                  <TableCell className="font-mono">{g.saros_num}</TableCell>
                  <TableCell className="text-right tabular-nums">{g.count}</TableCell>
                  <TableCell className="tabular-nums text-muted-foreground text-sm">
                    {g.year_start}–{g.year_end}
                  </TableCell>
                  <TableCell className="text-right font-mono">{formatSeparation(g.mean_tychos_error)}</TableCell>
                  <TableCell className="text-right font-mono">{formatSeparation(g.max_tychos_error)}</TableCell>
                  <TableCell className="text-right font-mono text-muted-foreground">{formatSeparation(g.mean_jpl_error)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )
      ) : results.length === 0 ? (
        <p className="text-sm text-muted-foreground">No results found.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <SortHead column="date" active={sortBy} direction={sortDir} onSort={handleEclipseSort}>Date</SortHead>
              <SortHead column="catalog_type" active={sortBy} direction={sortDir} onSort={handleEclipseSort}>Type</SortHead>
              <SortHead column="magnitude" active={sortBy} direction={sortDir} onSort={handleEclipseSort}>Magnitude</SortHead>
              <SortHead column="min_separation_arcmin" active={sortBy} direction={sortDir} onSort={handleEclipseSort} className="text-right">Tychos Sep</SortHead>
              <SortHead column="tychos_error_arcmin" active={sortBy} direction={sortDir} onSort={handleEclipseSort} className="text-right">Tychos Error</SortHead>
              <SortHead column="jpl_error_arcmin" active={sortBy} direction={sortDir} onSort={handleEclipseSort} className="text-right">JPL Error</SortHead>
              <SortHead column="timing_offset_min" active={sortBy} direction={sortDir} onSort={handleEclipseSort} className="text-right">Timing Offset</SortHead>
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

      {/* Pagination — only for per-eclipse view */}
      {!loading && !error && !groupBySaros && results.length > 0 && (
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
