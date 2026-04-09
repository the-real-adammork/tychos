"""CLI command implementations for `python -m server.research`."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from server.research.sandbox import (
    JobPaths,
    write_json,
    load_json,
    append_log,
    params_hash,
    read_log_tail,
)
from server.research.program_md import render_template, parse_frontmatter
from server.research.subset import (
    select_subset,
    load_eclipses_for_dataset,
    get_dataset_scan_window,
)
from server.research.allowlist import (
    check_diff_against_allowlist,
    AllowlistViolation,
)
from server.research.objective import (
    compute_objective,
    per_eclipse_detail,
    aux_stats,
    EmptyResults,
    NoScorableResults,
)
from server.research.search import run_search, SearchResult

# Map short --dataset arg to the dataset slug used in the DB and in scanner dispatch.
_DATASET_SLUG = {
    "solar": "solar_eclipse",
    "lunar": "lunar_eclipse",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_base_params(base_arg: str) -> dict:
    """Load the params dict from a versioned param file.

    `base_arg` is like 'v1-original/v2'. Resolves to params/<dir>/<file>.json.
    """
    repo_root = Path(__file__).parent.parent.parent
    parts = base_arg.split("/")
    if len(parts) != 2:
        raise ValueError(f"--base must be like 'v1-original/v2', got {base_arg!r}")
    version_dir, version_file = parts
    path = repo_root / "params" / version_dir / f"{version_file}.json"
    if not path.exists():
        raise FileNotFoundError(f"Base param version not found: {path}")
    raw = load_json(path)
    if "params" not in raw:
        raise ValueError(f"Param file {path} missing top-level 'params' key")
    return raw["params"]


def cmd_init(args) -> int:
    paths = JobPaths.for_job(args.job)
    if paths.root.exists():
        print(f"error: job directory already exists: {paths.root}", file=sys.stderr)
        return 2

    dataset_slug = _DATASET_SLUG[args.dataset]
    base_params = _resolve_base_params(args.base)

    paths.root.mkdir(parents=True, exist_ok=False)

    # baseline.json + current.json — identical at init time
    write_json(paths.baseline_json, base_params)
    write_json(paths.current_json, base_params)

    # subset.json — full catalog (subsets removed — scans are fast enough now)
    catalog = load_eclipses_for_dataset(dataset_slug)
    if not catalog:
        print(f"error: no eclipses found for dataset {dataset_slug}", file=sys.stderr)
        return 3

    # Scan window: CLI override wins, otherwise use the dataset's stored default.
    scan_window_hours = args.scan_window_hours
    if scan_window_hours is None:
        scan_window_hours = get_dataset_scan_window(dataset_slug)

    mode = getattr(args, "mode", "combined")

    write_json(paths.subset_json, {
        "dataset_slug": dataset_slug,
        "mode": mode,
        "scan_window_hours": scan_window_hours,
        "selected_at": _now_iso(),
        "events": catalog,
    })

    # program.md — render from template
    paths.program_md.write_text(
        render_template(
            job_name=args.job,
            dataset_slug=dataset_slug,
            base_param_version=args.base,
        )
    )

    # log.jsonl — empty file (touch)
    paths.log_jsonl.touch()

    print(f"Initialized job at {paths.root}")
    print(f"  dataset: {dataset_slug}")
    print(f"  mode:    {mode}")
    print(f"  base:    {args.base}")
    print(f"  events:  {len(catalog)} (full catalog)")
    print(f"  window:  ±{scan_window_hours}h")
    print()
    print(f"Next: open `claude` in this repo and point it at:")
    print(f"  {paths.program_md}")
    return 0


def _load_job_state(job_name: str):
    """Load all sandbox files needed for iterate/validate. Returns a tuple."""
    paths = JobPaths.for_job(job_name)
    if not paths.root.exists():
        raise FileNotFoundError(
            f"Job directory not found: {paths.root}. Run `init` first."
        )
    current = load_json(paths.current_json)
    baseline = load_json(paths.baseline_json)
    program_md = paths.program_md.read_text()
    frontmatter = parse_frontmatter(program_md)
    subset_blob = load_json(paths.subset_json)
    return paths, current, baseline, frontmatter, subset_blob


def _load_jpl_reference_for_subset(dataset_slug: str, eclipses: list[dict]) -> dict:
    """Return {catalog_jd: jpl_row} for the given subset events.

    Needed so the scanner can sample Tychos body positions at JPL's best_jd,
    and so the enrichment step can compute per-body positional deltas.
    """
    from server.db import get_db

    jds = [ecl["julian_day_tt"] for ecl in eclipses]
    if not jds:
        return {}
    placeholders = ",".join(["?"] * len(jds))
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT jr.julian_day_tt, jr.best_jd,
                   jr.sun_ra_rad, jr.sun_dec_rad, jr.moon_ra_rad, jr.moon_dec_rad
              FROM jpl_reference jr
              JOIN datasets d ON d.id = jr.dataset_id
             WHERE d.slug = ? AND jr.julian_day_tt IN ({placeholders})
            """,
            (dataset_slug, *jds),
        ).fetchall()
    return {row["julian_day_tt"]: dict(row) for row in rows}


def _enrich_with_deltas(results: list[dict], jpl_by_jd: dict) -> None:
    """Mutate `results` in place to add sun_/moon_delta_ra/dec_arcmin fields.

    Uses the tychos_*_at_jpl_rad values the scanner already produced and the
    JPL Sun/Moon RA/Dec at that same JD. Rows without a matching JPL entry
    get None for all four fields.
    """
    import math
    k = (180.0 / math.pi) * 60.0
    for r in results:
        jpl = jpl_by_jd.get(r["julian_day_tt"])
        if (
            jpl
            and r.get("tychos_sun_ra_at_jpl_rad") is not None
            and jpl.get("sun_ra_rad") is not None
            and jpl.get("moon_ra_rad") is not None
        ):
            cos_s = math.cos(jpl["sun_dec_rad"])
            cos_m = math.cos(jpl["moon_dec_rad"])
            r["sun_delta_ra_arcmin"] = round(
                (r["tychos_sun_ra_at_jpl_rad"] - jpl["sun_ra_rad"]) * cos_s * k, 4
            )
            r["sun_delta_dec_arcmin"] = round(
                (r["tychos_sun_dec_at_jpl_rad"] - jpl["sun_dec_rad"]) * k, 4
            )
            r["moon_delta_ra_arcmin"] = round(
                (r["tychos_moon_ra_at_jpl_rad"] - jpl["moon_ra_rad"]) * cos_m * k, 4
            )
            r["moon_delta_dec_arcmin"] = round(
                (r["tychos_moon_dec_at_jpl_rad"] - jpl["moon_dec_rad"]) * k, 4
            )
        else:
            r["sun_delta_ra_arcmin"] = None
            r["sun_delta_dec_arcmin"] = None
            r["moon_delta_ra_arcmin"] = None
            r["moon_delta_dec_arcmin"] = None


def _run_scan(
    dataset_slug: str,
    params: dict,
    eclipses: list[dict],
    half_window_hours: float = 2.0,
) -> list[dict]:
    """Dispatch to the right scanner for the dataset."""
    from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses

    jpl_by_jd = _load_jpl_reference_for_subset(dataset_slug, eclipses)
    jpl_best_lookup = {
        jd: row["best_jd"] for jd, row in jpl_by_jd.items() if row["best_jd"] is not None
    }

    if dataset_slug == "solar_eclipse":
        results = scan_solar_eclipses(
            params, eclipses, half_window_hours=half_window_hours,
            jpl_best_jd_by_catalog_jd=jpl_best_lookup,
        )
    elif dataset_slug == "lunar_eclipse":
        results = scan_lunar_eclipses(
            params, eclipses, half_window_hours=half_window_hours,
            jpl_best_jd_by_catalog_jd=jpl_best_lookup,
        )
    else:
        raise ValueError(f"Unknown dataset_slug: {dataset_slug}")

    _enrich_with_deltas(results, jpl_by_jd)
    return results


def _next_iter_number(log_path) -> int:
    tail = read_log_tail(log_path, n=1)
    if not tail:
        return 1
    return int(tail[0].get("iter", 0)) + 1


def _print_per_eclipse(results: list[dict], mode: str) -> None:
    """Print per-eclipse detail sorted worst-first for the AI agent."""
    details = per_eclipse_detail(results, mode)
    if not details:
        return
    print(f"\n--- per-eclipse detail (worst first, {len(details)} events) ---")
    if mode == "solar_position":
        print(f"{'date':>22s}  {'error':>8s}  {'sun_dRA':>9s}  {'sun_dDec':>9s}")
        for d in details:
            print(f"{d['date']:>22s}  {d['error']:8.2f}  {d['sun_dRA']:+9.2f}  {d['sun_dDec']:+9.2f}")
    elif mode == "lunar_position":
        print(f"{'date':>22s}  {'error':>8s}  {'moon_dRA':>9s}  {'moon_dDec':>9s}")
        for d in details:
            print(f"{d['date']:>22s}  {d['error']:8.2f}  {d['moon_dRA']:+9.2f}  {d['moon_dDec']:+9.2f}")
    else:
        print(f"{'date':>22s}  {'error':>8s}  {'sun_dRA':>9s}  {'sun_dDec':>9s}  {'moon_dRA':>9s}  {'moon_dDec':>9s}")
        for d in details:
            print(f"{d['date']:>22s}  {d['error']:8.2f}  {d['sun_dRA']:+9.2f}  {d['sun_dDec']:+9.2f}  {d['moon_dRA']:+9.2f}  {d['moon_dDec']:+9.2f}")
    print("---")


def cmd_iterate(args) -> int:
    try:
        paths, current, baseline, frontmatter, subset_blob = _load_job_state(args.job)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Guardrail: allowlist diff
    try:
        check_diff_against_allowlist(
            current,
            baseline,
            allowlist_globs=frontmatter.get("allowlist", []),
            known_bodies=list(baseline.keys()),
        )
    except AllowlistViolation as e:
        print(f"error: allowlist violation: {e}", file=sys.stderr)
        return 4

    # Guardrail: hash dedup
    h = params_hash(current)
    tail = read_log_tail(paths.log_jsonl, n=1)
    if tail and tail[0].get("params_hash") == h and tail[0].get("kind") == "iterate":
        cached = tail[0]
        print(f"objective: {cached['objective']}")
        print(f"mean_sun_error_arcmin: {cached.get('mean_sun_error_arcmin')}")
        print(f"mean_moon_error_arcmin: {cached.get('mean_moon_error_arcmin')}")
        print(f"n_total: {cached.get('n_total')}")
        print("(cached — current.json identical to last iterate)")
        return 0

    dataset_slug = subset_blob["dataset_slug"]
    mode = subset_blob.get("mode", "combined")
    window = float(subset_blob.get("scan_window_hours", 2.0))

    # Always scan the full catalog (fast enough with selective body init)
    eclipses = load_eclipses_for_dataset(dataset_slug)
    if not eclipses:
        print(f"error: no eclipses found for dataset {dataset_slug}", file=sys.stderr)
        return 3

    try:
        results = _run_scan(dataset_slug, current, eclipses, half_window_hours=window)
        objective = compute_objective(results, mode=mode)
    except (EmptyResults, NoScorableResults) as e:
        print(f"error: {e}", file=sys.stderr)
        return 5

    aux = aux_stats(results)

    entry = {
        "iter": _next_iter_number(paths.log_jsonl),
        "ts": _now_iso(),
        "kind": "iterate",
        "params_hash": h,
        "objective": round(objective, 4),
        "mode": mode,
        **aux,
    }
    append_log(paths.log_jsonl, entry)

    print(f"objective: {entry['objective']}")
    print(f"mode: {mode}")
    print(f"mean_sun_error_arcmin: {aux['mean_sun_error_arcmin']}")
    print(f"mean_moon_error_arcmin: {aux['mean_moon_error_arcmin']}")
    print(f"n_total: {aux['n_total']}")
    _print_per_eclipse(results, mode)
    return 0


def cmd_validate(args) -> int:
    try:
        paths, current, baseline, frontmatter, subset_blob = _load_job_state(args.job)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Same guardrails as iterate
    try:
        check_diff_against_allowlist(
            current,
            baseline,
            allowlist_globs=frontmatter.get("allowlist", []),
            known_bodies=list(baseline.keys()),
        )
    except AllowlistViolation as e:
        print(f"error: allowlist violation: {e}", file=sys.stderr)
        return 4

    dataset_slug = subset_blob["dataset_slug"]
    mode = subset_blob.get("mode", "combined")
    window = float(subset_blob.get("scan_window_hours", 2.0))
    full_catalog = load_eclipses_for_dataset(dataset_slug)
    if not full_catalog:
        print(f"error: no eclipses found for dataset {dataset_slug}", file=sys.stderr)
        return 3

    try:
        results = _run_scan(dataset_slug, current, full_catalog, half_window_hours=window)
        objective = compute_objective(results, mode=mode)
    except (EmptyResults, NoScorableResults) as e:
        print(f"error: {e}", file=sys.stderr)
        return 5

    aux = aux_stats(results)

    entry = {
        "iter": _next_iter_number(paths.log_jsonl),
        "ts": _now_iso(),
        "kind": "validate",
        "params_hash": params_hash(current),
        "validation_objective": round(objective, 4),
        "mode": mode,
        **aux,
    }
    append_log(paths.log_jsonl, entry)

    print(f"validation_objective: {entry['validation_objective']}")
    print(f"mode: {mode}")
    print(f"mean_sun_error_arcmin: {aux['mean_sun_error_arcmin']}")
    print(f"mean_moon_error_arcmin: {aux['mean_moon_error_arcmin']}")
    print(f"n_total: {aux['n_total']}")
    _print_per_eclipse(results, mode)
    return 0


def cmd_search(args) -> int:
    """Joint multi-parameter Nelder-Mead search over the subset.

    Reads `--params` (comma-separated body.field keys), validates each
    against the job's allowlist, builds an objective that runs the
    scanner against the frozen subset, and lets Nelder-Mead explore up
    to `--budget` evaluations. If the best found state is strictly
    better than the starting state, writes it to current.json and
    logs a summary entry. Otherwise leaves current.json alone.
    """
    try:
        paths, current, baseline, frontmatter, subset_blob = _load_job_state(args.job)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Current state must already be allowlist-clean before we start searching.
    try:
        check_diff_against_allowlist(
            current,
            baseline,
            allowlist_globs=frontmatter.get("allowlist", []),
            known_bodies=list(baseline.keys()),
        )
    except AllowlistViolation as e:
        print(f"error: allowlist violation in current.json: {e}", file=sys.stderr)
        return 4

    param_keys = [k.strip() for k in args.params.split(",") if k.strip()]
    if not param_keys:
        print("error: --params must list at least one body.field key", file=sys.stderr)
        return 6

    # Every key must be in the allowlist (or we'd be searching into
    # forbidden territory the agent couldn't reach by hand).
    from server.research.allowlist import expand_globs
    allowed = expand_globs(
        frontmatter.get("allowlist", []),
        list(baseline.keys()),
    )
    forbidden = [k for k in param_keys if k not in allowed]
    if forbidden:
        print(
            f"error: search params not in allowlist: {forbidden}",
            file=sys.stderr,
        )
        return 4

    dataset_slug = subset_blob["dataset_slug"]
    mode = subset_blob.get("mode", "combined")
    window = float(subset_blob.get("scan_window_hours", 2.0))

    # Search uses full catalog too
    eclipses = load_eclipses_for_dataset(dataset_slug)
    if not eclipses:
        print(f"error: no eclipses found for dataset {dataset_slug}", file=sys.stderr)
        return 3

    def _evaluate(candidate: dict) -> float:
        results = _run_scan(
            dataset_slug, candidate, eclipses, half_window_hours=window
        )
        return compute_objective(results, mode=mode)

    print(f"search: {len(param_keys)} params, budget={args.budget}, "
          f"scale={args.scale}")
    print(f"        {', '.join(param_keys)}")

    try:
        result: SearchResult = run_search(
            current=current,
            param_keys=param_keys,
            evaluate=_evaluate,
            budget=args.budget,
            scale=args.scale,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 6

    improved = result.best_objective < result.starting_objective
    delta = result.best_objective - result.starting_objective

    # Log a single summary entry regardless of outcome.
    log_entry = {
        "iter": _next_iter_number(paths.log_jsonl),
        "ts": _now_iso(),
        "kind": "search",
        "param_keys": param_keys,
        "budget": args.budget,
        "scale": args.scale,
        "n_evals": result.n_evals,
        "starting_objective": round(result.starting_objective, 4),
        "best_objective": round(result.best_objective, 4),
        "delta": round(delta, 4),
        "improved": improved,
        "converged": result.converged,
    }
    append_log(paths.log_jsonl, log_entry)

    if improved:
        # Compute a final aux stats printout on the best params so the
        # agent sees detection rate + separation alongside the new objective.
        best_results = _run_scan(
            dataset_slug, result.best_params, eclipses, half_window_hours=window
        )
        best_aux = aux_stats(best_results)
        write_json(paths.current_json, result.best_params)
        print(f"starting_objective: {round(result.starting_objective, 4)}")
        print(f"best_objective:     {round(result.best_objective, 4)}")
        print(f"delta:              {round(delta, 4)}  (improved)")
        print(f"n_evals:            {result.n_evals}")
        print(f"mean_sun_error_arcmin: {best_aux['mean_sun_error_arcmin']}")
        print(f"mean_moon_error_arcmin: {best_aux['mean_moon_error_arcmin']}")
        print(f"n_total: {best_aux['n_total']}")
        print(f"current.json updated with best found state.")
    else:
        print(f"starting_objective: {round(result.starting_objective, 4)}")
        print(f"best_objective:     {round(result.best_objective, 4)}")
        print(f"delta:              {round(delta, 4)}  (no improvement)")
        print(f"n_evals:            {result.n_evals}")
        print(f"current.json unchanged.")

    return 0
